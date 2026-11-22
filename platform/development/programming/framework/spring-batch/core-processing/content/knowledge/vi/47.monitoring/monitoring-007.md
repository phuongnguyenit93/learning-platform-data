# Tỷ lệ failure theo job trong Spring Batch

## 1. Tỷ lệ failure theo job cho biết điều gì?

Trong hệ thống Spring Batch, một job có thể chạy hàng trăm lần mỗi ngày, chỉ một lần mỗi đêm, hoặc chỉ khi có sự kiện. Việc nhìn thấy một `JobExecution` mang trạng thái `FAILED` rất hữu ích để điều tra một sự cố cụ thể. Tuy nhiên, để đánh giá **độ ổn định của từng job theo thời gian**, chúng ta cần một chỉ số tổng hợp: **tỷ lệ failure theo job** (*job failure rate*).

Ví dụ, trong 24 giờ gần nhất:

| Job | Lần chạy hoàn tất thành công | Lần chạy thất bại | Tỷ lệ failure |
| --- | ---: | ---: | ---: |
| `importOrdersJob` | 90 | 10 | 10% |
| `settlePaymentsJob` | 19 | 1 | 5% |
| `exportReportsJob` | 1 | 0 | 0% |
| `monthEndClosingJob` | 0 | 0 | Không đủ dữ liệu |

Mặc dù `exportReportsJob` có tỷ lệ 0%, dữ liệu chỉ có một lần chạy. Không thể kết luận rằng nó đáng tin cậy hơn một job chạy 100 lần. Với `monthEndClosingJob`, không có lần chạy nào trong cửa sổ 24 giờ; phải hiển thị **N/A**, không được quy đổi thành 0%.

Trong ngữ cảnh **Spring Batch Core Processing → Monitoring**, bài học này tập trung vào việc:

1. Xác định mẫu số và ý nghĩa của một “lần chạy thất bại”.
2. Lấy kết quả thực thi từ `JobRepository` hoặc Micrometer.
3. Tính toán, trực quan hóa và đặt cảnh báo cho tỷ lệ failure của **mỗi job**.
4. Tránh sai lệch do restart, retry, các trạng thái chưa kết thúc, thiếu dữ liệu hoặc cửa sổ quan sát quá ngắn.
5. Kiểm thử cách đo để biểu đồ thực sự phản ánh hành vi của batch job.

Một tỷ lệ được định nghĩa rõ ràng là điều kiện tiên quyết để đặt ngưỡng SLO, so sánh phiên bản triển khai và quyết định thời điểm cần xử lý sự cố.

## 2. Hiểu đúng JobInstance, JobExecution và trạng thái

### 2.1. Một job logic có thể có nhiều execution

Trong Spring Batch:

- `Job` là định nghĩa công việc, ví dụ `importOrdersJob`.
- `JobInstance` là một lần xử lý logic, được nhận diện bằng tên job cùng **identifying `JobParameters`**.
- `JobExecution` là một lần cố gắng chạy `JobInstance` đó. Một instance có thể có nhiều execution nếu lần đầu thất bại rồi được restart.
- `StepExecution` lưu trạng thái từng step; một job gồm nhiều step có thể thất bại ở bất kỳ step nào.

```text
Job: importOrdersJob
 |
 +-- JobInstance: businessDate=2026-11-15
 |      |
 |      +-- JobExecution #101 -> FAILED
 |      +-- JobExecution #102 -> COMPLETED (restart thành công)
 |
 +-- JobInstance: businessDate=2026-11-16
        |
        +-- JobExecution #103 -> COMPLETED
```

Nếu đếm theo **execution**, có 3 lần thử, 1 failure: tỷ lệ bằng **33,33%**. Nếu đánh giá **kết quả cuối cùng của mỗi instance**, có 2 instance cuối cùng thành công: tỷ lệ cuối cùng bằng **0%**. Cả hai phép tính đều có ích nhưng trả lời **hai câu hỏi khác nhau**:

| Thước đo | Câu hỏi chính | Cách hiểu |
| --- | --- | --- |
| *Execution failure rate* | Bao nhiêu lần cố gắng chạy kết thúc bằng failure? | Sức khỏe vận hành, số lần cần can thiệp/restart |
| *Final instance failure rate* | Bao nhiêu công việc logic cuối cùng vẫn không hoàn tất? | Khả năng hoàn thành công việc sau khi cho phép khôi phục |
| *First-attempt failure rate* | Bao nhiêu công việc thất bại ở lần chạy đầu? | Độ tin cậy ban đầu, mức độ phụ thuộc retry/restart |
| *Consecutive failures* | Job đã thất bại liên tiếp bao nhiêu lần? | Phát hiện xu hướng sự cố ngay cả khi số mẫu nhỏ |

Khi nói “tỷ lệ failure theo job” mà không chỉ rõ đơn vị đếm, hai nhóm có thể báo cáo những con số khác nhau dù truy cập cùng một `JobRepository`. Bài này lấy **execution failure rate** làm chỉ số chính và trình bày các chỉ số khác khi cần.

### 2.2. Phân biệt BatchStatus và ExitStatus

Spring Batch có hai nhóm trạng thái cần phân biệt:

- `BatchStatus` mô tả vòng đời thực thi: `STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `FAILED`, `COMPLETED`, `ABANDONED`, `UNKNOWN`.
- `ExitStatus` biểu diễn kết quả/exit code mà luồng job sử dụng, có thể được ứng dụng tùy chỉnh, chẳng hạn `COMPLETED WITH SKIPS`.

Các trạng thái `STARTING`, `STARTED` và `STOPPING` cho thấy execution đang hoặc đang chuẩn bị thực thi. Chúng **chưa phải kết quả cuối** và không nên được đưa vào mẫu số của tỷ lệ thành công/thất bại đã hoàn tất.

`STOPPED` thường nghĩa là job đã được dừng có chủ đích hoặc dừng theo cơ chế điều phối; không mặc định đồng nghĩa với `FAILED`. `ABANDONED` và `UNKNOWN` cũng không nên tự động xếp vào một trong hai nhóm nếu chưa có chính sách vận hành rõ ràng.

| `BatchStatus` | Đưa vào mẫu số failure rate chuẩn? | Cách theo dõi |
| --- | --- | --- |
| `COMPLETED` | Có, nhóm thành công | Tính một execution thành công |
| `FAILED` | Có, nhóm failure | Tính một execution thất bại |
| `STOPPED` | Không, theo định nghĩa mặc định của bài | Theo dõi tỷ lệ dừng riêng |
| `ABANDONED` | Không | Theo dõi xử lý thủ công/các run bỏ dở |
| `UNKNOWN` | Không | Cảnh báo trạng thái không rõ, cần điều tra |
| `STARTED`, `STARTING`, `STOPPING` | Không | Theo dõi job đang chạy, chạy quá lâu, bị treo |

Một job có `BatchStatus.COMPLETED` nhưng có các item bị `skip` theo chính sách có thể vẫn là **thành công kỹ thuật**. Nếu nghiệp vụ yêu cầu “không bỏ sót hóa đơn nào”, cần thêm **chỉ số chất lượng xử lý**; không nên suy diễn mọi trường hợp `skipCount > 0` thành `FAILED`.

## 3. Công thức chuẩn và cách chọn mẫu số

Gọi:

- `F(J, W)`: số `JobExecution` của job `J` có `BatchStatus.FAILED` và kết thúc trong cửa sổ thời gian `W`.
- `C(J, W)`: số `JobExecution` của job `J` có `BatchStatus.COMPLETED` và kết thúc trong cửa sổ `W`.
- `N(J, W) = F(J, W) + C(J, W)`: số execution có kết quả hợp lệ cho phép tính.

Khi `N > 0`:

\[
\text{FailureRate}(J,W)=\frac{F(J,W)}{F(J,W)+C(J,W)}
\]

Tỷ lệ phần trăm:

\[
\text{FailureRatePct}(J,W)=100\times\text{FailureRate}(J,W)
\]

Nếu `N = 0`, kết quả **không xác định** (`NULL`/`N/A`). Chỉ số không phải 0%.

**Ví dụ:** `importOrdersJob` có 16 `COMPLETED`, 4 `FAILED` trong một ngày: `F=4`, `C=16`, `N=20`, vậy failure rate = `4/20 = 0,20 = 20%`.

Không lấy:

- `FAILED / tất cả bản ghi JobExecution` khi đang có nhiều execution `STARTED`.
- `FAILED / số dòng được ItemReader đọc`: đó là số item, không phải số lần chạy job.
- `FAILED / số JobInstance` nếu tử số vẫn đang đếm JobExecution: tử số và mẫu số thuộc hai đơn vị khác nhau.
- Trung bình không trọng số của các failure rate từng job rồi gọi là failure rate toàn hệ thống; mỗi job có tần suất chạy khác nhau.

### 3.1. Khi nào tính failure theo STOPPED?

Có tổ chức coi một lần `STOPPED` ngoài kế hoạch là sự cố cần tính vào SLO. Nếu như vậy, hãy đặt tên riêng, ví dụ:

\[
\text{UnsuccessfulRate}=\frac{FAILED+UNEXPECTED\_STOPPED}{COMPLETED+FAILED+UNEXPECTED\_STOPPED}
\]

Không đổi cách phân loại trong dashboard mà không ghi chú rõ, vì như thế số liệu trước/sau thay đổi không còn so sánh trực tiếp được. Một lần dừng bảo trì có kế hoạch và một lần dừng do lỗi hệ thống có thể cần hai nhãn nguyên nhân khác nhau.

### 3.2. Mức độ ổn định theo cỡ mẫu

Nếu một job chạy duy nhất một lần và thất bại, failure rate bằng 100%. Nếu job khác chạy 100 lần và thất bại một lần, tỷ lệ bằng 1%. Tỷ lệ của job đầu có thể phản ánh sự cố rất nghiêm trọng, nhưng không thể dùng một lần chạy để ước lượng độ tin cậy dài hạn.

Do đó dashboard nên hiển thị **F / N** cùng phần trăm. Khi đặt cảnh báo theo tỷ lệ, có thể yêu cầu tối thiểu một số lần chạy trong cửa sổ; với job chạy thưa, dùng **cảnh báo theo từng failure hoặc liên tiếp** thay vì chờ đủ mẫu.

## 4. Chọn cửa sổ thời gian để tính tỷ lệ

Một tỷ lệ failure không có cửa sổ thời gian sẽ khó diễn giải. Các cửa sổ thường dùng:

| Cửa sổ | Mục tiêu | Lưu ý |
| --- | --- | --- |
| 15 phút / 1 giờ | Phát hiện lỗi vừa xuất hiện ở job chạy thường xuyên | Không phù hợp với job chỉ chạy mỗi ngày |
| 24 giờ | Theo dõi vận hành hằng ngày | Các job chạy một lần/ngày có mẫu rất nhỏ |
| 7 ngày | Nhìn xu hướng cho job chạy hằng ngày | Có thể che khuất sự cố mới |
| 30 ngày | Theo dõi mục tiêu dài hạn / SLO | Cần metadata và metrics đủ thời gian retention |
| Theo `businessDate` | Đối soát chu kỳ nghiệp vụ | Có thể khác ngày job thực sự kết thúc |

Nên xác định execution thuộc cửa sổ theo **thời điểm kết thúc `END_TIME`** nếu muốn đo kết quả được ghi nhận trong thời gian đó. Ví dụ job bắt đầu lúc 23:58 và kết thúc lúc 00:03 sẽ thuộc ngày mới theo `END_TIME`, mặc dù đầu vào thuộc `businessDate` của ngày trước.

Với thời gian trong database, nên dùng khoảng nửa mở `[startInclusive, endExclusive)`:

```text
END_TIME >= 2026-11-15T00:00:00Z
END_TIME <  2026-11-16T00:00:00Z
```

Nếu dashboard dùng ngày theo một múi giờ nghiệp vụ, hãy chuyển ranh giới ngày từ `ZoneId` đã thống nhất sang timestamp phù hợp với database; không mặc định server SQL, JVM, dashboard và scheduler có cùng timezone.

**Cửa sổ không có lần chạy** cần một chỉ số riêng về *freshness/missing run*. Không có job nào chạy có thể do scheduler đã hỏng; biểu đồ failure rate đơn lẻ không phát hiện được tình huống này.

## 5. Nguồn dữ liệu 1: JobRepository và bảng metadata

`JobRepository` là nguồn lưu metadata các lần thực thi Spring Batch. Với repository JDBC thường gặp, hai bảng quan trọng là:

- `BATCH_JOB_INSTANCE`: có `JOB_INSTANCE_ID` và `JOB_NAME`.
- `BATCH_JOB_EXECUTION`: có `JOB_EXECUTION_ID`, `JOB_INSTANCE_ID`, `STATUS`, `CREATE_TIME`, `START_TIME`, `END_TIME` và thông tin kết thúc.

Để tính tỷ lệ **theo tên job**, join execution với instance qua `JOB_INSTANCE_ID`. Tránh truy vấn bảng step rồi đếm số step `FAILED` vì một job có thể có nhiều step; đơn vị cần đếm ở đây là **JobExecution**.

### 5.1. SQL tính failure rate theo job

Ví dụ dưới đây dùng cú pháp SQL phổ biến trên PostgreSQL, H2 và nhiều RDBMS khác; tham số `:fromTime` và `:toTime` là placeholder được công cụ truy vấn hoặc `NamedParameterJdbcTemplate` binding:

```sql
SELECT
    ji.JOB_NAME AS job_name,
    SUM(CASE WHEN je.STATUS = 'FAILED' THEN 1 ELSE 0 END) AS failed_runs,
    SUM(CASE WHEN je.STATUS = 'COMPLETED' THEN 1 ELSE 0 END) AS completed_runs,
    COUNT(*) AS terminal_runs,
    100.0 * SUM(CASE WHEN je.STATUS = 'FAILED' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS failure_pct
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.END_TIME >= :fromTime
  AND je.END_TIME < :toTime
  AND je.STATUS IN ('FAILED', 'COMPLETED')
GROUP BY ji.JOB_NAME
ORDER BY failure_pct DESC, terminal_runs DESC;
```

Ý nghĩa:

1. `WHERE ... END_TIME` chỉ lấy những execution **đã kết thúc trong cửa sổ đo**.
2. `STATUS IN ('FAILED', 'COMPLETED')` tạo mẫu số rõ ràng; `STOPPED` và các trạng thái chưa kết thúc được xử lý bằng metric riêng.
3. `COUNT(*)` đếm số execution đã có outcome được đưa vào chỉ số.
4. `NULLIF(COUNT(*),0)` bảo vệ phép chia nếu về sau sửa cấu trúc truy vấn; trong nhóm có hàng thì count vốn lớn hơn 0.
5. `ORDER BY` ưu tiên job có tỷ lệ failure cao, sau đó theo cỡ mẫu.

Query chỉ trả các job **có ít nhất một execution hợp lệ** trong cửa sổ. Để hiển thị các job không có lần chạy là **N/A**, hãy kết hợp kết quả với danh sách job được quản lý (job catalog hoặc cấu hình scheduler), thay vì tự gán 0%.

**Cẩn thận với database schema/version:** kiểu cột thời gian, tiền tố bảng, cách migration và quyền đọc có thể khác nhau theo cấu hình Spring Batch. Dùng schema thực tế của deployment. Truy vấn đọc metadata nên thực hiện trên cơ sở dữ liệu được cấp quyền phù hợp hoặc read replica nếu lượng truy vấn monitoring lớn.

### 5.2. Đọc bằng JobExplorer

Nếu cần API Java thay vì truy cập bảng trực tiếp, Spring Batch cung cấp `JobExplorer` để tra cứu `JobInstance` và `JobExecution`.

Ví dụ Java minh họa theo Spring Batch 5.x:

```java
import java.time.Instant;
import java.util.List;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.explore.JobExplorer;

public record FailureSummary(
        long failed, long completed, Double failureRate) {}

public final class JobFailureRateService {
    private final JobExplorer jobExplorer;

    public JobFailureRateService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public FailureSummary summarize(
            String jobName, Instant from, Instant to) {

        long failed = 0;
        long completed = 0;

        int offset = 0;
        int pageSize = 100;

        while (true) {
            List<JobInstance> instances =
                    jobExplorer.getJobInstances(jobName, offset, pageSize);
            if (instances.isEmpty()) {
                break;
            }

            for (JobInstance instance : instances) {
                for (JobExecution execution :
                        jobExplorer.getJobExecutions(instance)) {
                    if (execution.getEndTime() == null) {
                        continue;
                    }

                    Instant endedAt =
                            execution.getEndTime().toInstant(
                                    java.time.ZoneOffset.UTC);
                    // Lưu ý: xem giải thích về timezone bên dưới.
                    if (endedAt.isBefore(from) || !endedAt.isBefore(to)) {
                        continue;
                    }

                    if (execution.getStatus() == BatchStatus.FAILED) {
                        failed++;
                    } else if (execution.getStatus() == BatchStatus.COMPLETED) {
                        completed++;
                    }
                }
            }
            offset += instances.size();
            if (instances.size() < pageSize) {
                break;
            }
        }

        long total = failed + completed;
        Double rate = total == 0 ? null : (double) failed / total;
        return new FailureSummary(failed, completed, rate);
    }
}
```

Trong Spring Batch 5.x, `JobExecution.getEndTime()` trả về `LocalDateTime`, tức **không tự mang timezone**. Dòng `toInstant(ZoneOffset.UTC)` ở ví dụ chỉ đúng nếu hệ thống đã quy ước lưu và đọc metadata theo UTC. Nếu repository dùng timezone khác, phải chuyển theo đúng quy ước đó. Với dashboard vận hành, nên ưu tiên câu SQL dùng timestamp nhất quán với database và parameter binding được kiểm soát.

**Về hiệu năng:** cách duyệt tất cả instance từ đầu rồi lọc theo thời gian chỉ thích hợp để minh họa API hoặc với dữ liệu nhỏ. Với số lượng execution lớn, nó có thể rất tốn kém; một truy vấn SQL có điều kiện thời gian ở database hoặc hệ metrics đã tổng hợp thường phù hợp hơn.

> **Lưu ý phiên bản:** Các import `JobExecution`/`JobInstance` và một số API tổ chức package có thay đổi giữa Spring Batch 5 và 6. Ví dụ code ở trên sử dụng cấu trúc Spring Batch 5.x; khi dùng 6.x cần đối chiếu API theo phiên bản dự án.

## 6. Nguồn dữ liệu 2: Micrometer và hệ thống metrics

Trong ứng dụng Spring Batch kết hợp Micrometer/Spring Boot Actuator, metrics có thể được thu thập qua listener hoặc các metric được framework tích hợp sẵn. Spring Batch có timer/observation đo thực thi job, step và các hoạt động liên quan; **tên metric, tag và cách export phụ thuộc phiên bản Spring Batch/Micrometer, registry và cấu hình**.

Ví dụ metric kiểu timer do framework ghi nhận có thể cung cấp số lần đo sau khi exporter chuyển sang Prometheus bằng một chuỗi có hậu tố `_count`. Trước khi viết PromQL, hãy xem trực tiếp endpoint `/actuator/prometheus` hoặc dữ liệu scrape để xác định **metric và labels thực tế**. Không ghép tên từ trí nhớ rồi cho rằng mọi phiên bản đều sinh ra đúng chuỗi đó.

Nếu hệ thống muốn một metric tường minh, ổn định theo contract của đội vận hành, có thể tạo **counter cho mỗi outcome kết thúc** bằng `JobExecutionListener`.

### 6.1. Định nghĩa metric tùy chỉnh

Quy ước:

```text
Logical metric name: batch.job.executions
Metric type: Counter
Tags:
    job.name = importOrdersJob
    status   = COMPLETED | FAILED | STOPPED
```

Sau khi export sang Prometheus, metric và tên nhãn có thể được chuẩn hóa thành:

```text
batch_job_executions_total{
  job_name="importOrdersJob",
  status="FAILED"
}
```

Tên trên là **quy ước ví dụ do ứng dụng tự tạo**, không phải cam kết tên metric mặc định của mọi phiên bản Spring Batch.

### 6.2. Cài listener để ghi nhận kết quả

Ví dụ Spring Batch 5.x với Micrometer:

```java
import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class JobOutcomeMetricsListener implements JobExecutionListener {

    private final MeterRegistry registry;

    public JobOutcomeMetricsListener(MeterRegistry registry) {
        this.registry = registry;
    }

    @Override
    public void afterJob(JobExecution execution) {
        BatchStatus status = execution.getStatus();
        if (status != BatchStatus.COMPLETED
                && status != BatchStatus.FAILED
                && status != BatchStatus.STOPPED) {
            return;
        }

        String jobName = execution.getJobInstance().getJobName();

        Counter.builder("batch.job.executions")
                .description("Finished Spring Batch job executions")
                .tag("job.name", jobName)
                .tag("status", status.name())
                .register(registry)
                .increment();
    }
}
```

Listener phải được gắn vào **Job** thực sự:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobOutcomeMetricsListener metricsListener) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .listener(metricsListener)
            .start(importOrdersStep)
            .build();
}
```

Trong Spring Batch 5.x, `JobBuilder` ở package `org.springframework.batch.core.job.builder`. Với cấu hình annotation/custom builder khác, hãy đảm bảo listener không bị bỏ quên. Metric cần xuất hiện sau khi execution **kết thúc** và listener được gọi.

### 6.3. Giới hạn của afterJob và counter

`afterJob(...)` hữu ích cho monitoring gần thời gian thực nhưng **không phải một bản ghi transaction bất biến**:

- Nếu JVM bị kill, mất điện hoặc process crash trước khi listener chạy/scrape, event failure có thể không được xuất thành metric.
- Counter trong process có thể reset khi pod restart; Prometheus thường xử lý reset trong `increase(...)`, nhưng vẫn cần đủ mẫu scrape.
- Nếu một outcome được phát lại/ghi hai lần do cơ chế instrumentation khác, counter có thể bị tăng trùng. Cần bảo đảm một contract instrumentation rõ ràng cho mỗi `JobExecution`.
- Khi job chạy trong nhiều JVM, cần tổng hợp theo job và status xuyên tất cả instance; không đếm theo pod như những job riêng nếu mục tiêu là tỷ lệ chung.
- Metadata trong `JobRepository` là nguồn phù hợp để **đối soát** các khoảng bị mất do restart, crash hoặc thời gian không có metrics.

Không nhét `jobExecutionId`, `runId`, customer ID, mã giao dịch hoặc exception message vào **metric label**: cardinality sẽ tăng rất nhanh. Các thông tin chi tiết đó nên nằm trong log có cấu trúc, tracing hoặc database audit; metric chỉ cần nhãn có số lượng giá trị hữu hạn như `job.name` và `status`.

## 7. Tính tỷ lệ bằng PromQL

Giả sử exporter thực sự cung cấp counter:

```text
batch_job_executions_total{job_name="importOrdersJob",status="COMPLETED"}
batch_job_executions_total{job_name="importOrdersJob",status="FAILED"}
```

### 7.1. Số failure trong 24 giờ

```promql
sum by (job_name) (
  increase(batch_job_executions_total{status="FAILED"}[24h])
)
```

`increase(...)` tính mức tăng counter trong cửa sổ, có xử lý counter reset theo semantics của Prometheus. Nếu metric có thêm label như `instance`, `pod`, `application`, phép `sum by(job_name)` sẽ tổng hợp các series cho cùng job. Trong hệ đa môi trường, cần thêm nhãn `environment`, `service` hoặc namespace để không cộng lẫn production với staging.

### 7.2. Failure rate theo từng job

```promql
100 *
sum by (job_name) (
  increase(batch_job_executions_total{status="FAILED"}[24h])
)
/
sum by (job_name) (
  increase(
    batch_job_executions_total{status=~"COMPLETED|FAILED"}[24h]
  )
)
```

Đây là công thức `100 * F / (F+C)`. Khi mẫu số không có execution, dashboard nên hiển thị **N/A** hoặc “No runs”; cần cấu hình xử lý giá trị rỗng/không hiện diện, không tự chuyển thành 0%.

Trong Prometheus, một series chỉ xuất hiện khi đã từng được tạo và được scrape; ví dụ một job chưa từng thất bại có thể **không có series `status="FAILED"`**. Khi ấy tử số có thể trở thành vector rỗng, khiến biểu đồ thiếu job dù job có thành công. Nên **khởi tạo trước counters cho từng status của các job đã biết** hoặc kết hợp logic bù zero từ tập completed/failed một cách có kiểm soát. Với chỉ số SLO quan trọng, đối soát thêm từ `JobRepository` để phát hiện vùng dữ liệu bị thiếu.

Ngoài ra, `increase` nội suy từ các mẫu scrape và có thể trả số thập phân, dù số execution thực tế là số nguyên. Với lưu lượng thấp và metric mới xuất hiện gần đây, số liệu có thể lệch so với truy vấn metadata; đây là đặc điểm của phép ước lượng counter theo cửa sổ, không nhất thiết là lỗi của job.

### 7.3. Cảnh báo với số mẫu tối thiểu

Giả sử đội vận hành định nghĩa: **cảnh báo nếu failure rate trên 10% trong một giờ và có ít nhất 10 execution đã hoàn tất trong giờ đó**.

```promql
(
  sum by (job_name) (
    increase(batch_job_executions_total{status="FAILED"}[1h])
  )
  /
  sum by (job_name) (
    increase(
      batch_job_executions_total{status=~"FAILED|COMPLETED"}[1h]
    )
  )
) > 0.10
and on (job_name)
sum by (job_name) (
  increase(
    batch_job_executions_total{status=~"FAILED|COMPLETED"}[1h]
  )
) >= 10
```

Đây chỉ là **ngưỡng minh họa**. Chọn ngưỡng thực tế theo tần suất chạy, độ quan trọng của job, SLO và khả năng khôi phục. Một job thanh toán quan trọng có thể cần cảnh báo ngay với một `FAILED`; job thử nghiệm tần suất cao có thể được đánh giá theo xu hướng 1 giờ/24 giờ.

Với job chạy thưa, chỉ số theo tỷ lệ có thể không thỏa điều kiện mẫu tối thiểu. Hãy bổ sung alert theo **failure mới nhất**, **số lần thất bại liên tiếp** và **quá hạn chưa có run thành công**.

## 8. JobExecution failure rate và JobInstance final failure rate

Tỷ lệ theo execution có thể tăng cao trong khi job vẫn tự hồi phục bằng restart. Ví dụ:

| JobInstance | Execution 1 | Execution 2 | Kết quả cuối |
| --- | --- | --- | --- |
| Ngày D1 | FAILED | COMPLETED | Thành công |
| Ngày D2 | COMPLETED | — | Thành công |
| Ngày D3 | FAILED | FAILED | Chưa thành công |

Nếu đếm theo execution: `F=3`, `C=2`, tỷ lệ **60%**. Nếu đếm trạng thái mới nhất của từng instance: 1 instance thất bại trong 3 instance, tỷ lệ **33,33%**. Đây không phải mâu thuẫn; mỗi phép tính dùng đơn vị đo khác nhau.

### 8.1. SQL lấy trạng thái mới nhất của mỗi instance

Ví dụ sử dụng window function:

```sql
WITH ranked_executions AS (
    SELECT
        ji.JOB_NAME,
        je.JOB_INSTANCE_ID,
        je.JOB_EXECUTION_ID,
        je.STATUS,
        je.END_TIME,
        ROW_NUMBER() OVER (
            PARTITION BY je.JOB_INSTANCE_ID
            ORDER BY je.CREATE_TIME DESC, je.JOB_EXECUTION_ID DESC
        ) AS rn
    FROM BATCH_JOB_EXECUTION je
    JOIN BATCH_JOB_INSTANCE ji
      ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
),
latest AS (
    SELECT JOB_NAME, JOB_INSTANCE_ID, STATUS, END_TIME
    FROM ranked_executions
    WHERE rn = 1
)
SELECT
    JOB_NAME,
    SUM(CASE WHEN STATUS = 'FAILED' THEN 1 ELSE 0 END)
        AS failed_instances,
    SUM(CASE WHEN STATUS = 'COMPLETED' THEN 1 ELSE 0 END)
        AS completed_instances,
    COUNT(*) AS terminal_instances,
    100.0 * SUM(CASE WHEN STATUS = 'FAILED' THEN 1 ELSE 0 END)
        / NULLIF(COUNT(*), 0) AS final_failure_pct
FROM latest
WHERE END_TIME >= :fromTime
  AND END_TIME < :toTime
  AND STATUS IN ('FAILED', 'COMPLETED')
GROUP BY JOB_NAME;
```

Query lấy **execution mới nhất hiện tại** cho từng instance rồi xét thời điểm kết thúc của execution đó. Nó phục vụ ảnh chụp trạng thái hiện tại, nhưng **không tái hiện chính xác lịch sử tại một ngày trong quá khứ** nếu instance đó sau này đã được restart: ví dụ ngày thứ Hai thất bại và thứ Ba thành công, query chạy ngày thứ Tư sẽ nhìn thấy trạng thái mới nhất là thành công.

Nếu cần biểu đồ lịch sử bất biến cho final instance outcome, hãy định nghĩa thời điểm chốt (ví dụ hết business deadline), lưu snapshot kết quả hoặc lưu event chuyển trạng thái theo thời gian. Không âm thầm dùng query trạng thái hiện tại để viết lại biểu đồ quá khứ.

### 8.2. Khi nào cần cả hai tỷ lệ?

Với job tính tiền, một chu kỳ đã thất bại hai lần rồi tự restart thành công có thể vẫn đáp ứng kết quả nghiệp vụ đúng hạn, nhưng cần theo dõi vì nó tiêu tốn tài nguyên và gia tăng rủi ro. Dashboard lý tưởng có hai góc nhìn:

- **Execution failure rate:** độ ổn định của mỗi lần cố gắng chạy.
- **On-time completion rate per business period:** tỷ lệ chu kỳ nghiệp vụ được hoàn tất trước deadline.

Chỉ đo execution failure rate sẽ bỏ qua tình huống job chậm, đứng im hoặc không được scheduler khởi chạy. Chỉ đo completion cuối cùng lại có thể che giấu việc hệ thống liên tục thất bại rồi khôi phục.

## 9. Dashboard monitoring theo từng job

Một dashboard dễ đọc nên hiển thị ít nhất:

| Trường | Ý nghĩa |
| --- | --- |
| Tên job | Một tên ổn định, ví dụ `importOrdersJob` |
| Execution failures | Số lần `FAILED` trong cửa sổ |
| Completed executions | Số lần `COMPLETED` trong cửa sổ |
| Failure rate | `FAILED / (FAILED + COMPLETED)` |
| Last execution status | Trạng thái lần chạy mới nhất, kể cả chưa kết thúc |
| Last successful completion | Lần gần nhất có outcome `COMPLETED` |
| Time since last success | Phát hiện job đã lâu không chạy thành công |
| Duration / p95 | Xác định job ngày càng chậm trước khi thất bại |
| Đường dẫn runbook / log | Hỗ trợ điều tra theo `jobExecutionId` khi có sự cố |

Ví dụ bảng:

| Job | Failed / Terminal (24h) | Failure rate | Lần thành công gần nhất | Đánh giá |
| --- | ---: | ---: | --- | --- |
| `importOrdersJob` | 6 / 120 | 5% | 5 phút trước | Có lỗi lặp lại cần theo dõi |
| `settlePaymentsJob` | 1 / 1 | 100% | Hôm qua | Sự cố cần ưu tiên kiểm tra |
| `monthlyCloseJob` | 0 / 0 | N/A | Cuối tháng trước | Chưa đến kỳ; kiểm tra lịch |
| `syncCustomersJob` | 0 / 80 | 0% | 2 phút trước | Hoạt động bình thường |

Không dùng một **màu duy nhất** dựa trên phần trăm để phân loại mọi job. Với một job tài chính quan trọng chạy mỗi đêm, một lần thất bại có thể nghiêm trọng hơn 5% lỗi trên một job báo cáo phụ trợ chạy vài trăm lần mỗi giờ.

### Đồ thị nên có

1. **Bar chart:** tỷ lệ failure theo job trong 24 giờ, kèm `failed/total`.
2. **Time series:** số `FAILED` và `COMPLETED` theo giờ; giúp nhận biết regression sau deploy.
3. **Last-success age:** thời gian từ lần `COMPLETED` gần nhất.
4. **Job duration:** p50/p95, đặc biệt cho job có deadline.
5. **Phân rã lỗi:** step bị lỗi, mã lỗi có cấu trúc, phiên bản ứng dụng hoặc môi trường. Tránh dùng exception message làm metric label.

## 10. Cảnh báo theo tỷ lệ failure mà không gây nhiễu

### 10.1. Dựa trên tần suất chạy của job

| Loại job | Cảnh báo có ích | Vì sao |
| --- | --- | --- |
| Chạy mỗi vài giây/phút | Tỷ lệ failure 15 phút/1 giờ + điều kiện số mẫu | Đủ số lần chạy để đánh giá xu hướng |
| Chạy mỗi giờ | Một vài failure liên tiếp; tỷ lệ 24 giờ | Cửa sổ ngắn có ít mẫu |
| Chạy mỗi ngày | Một lần `FAILED` hoặc chưa `COMPLETED` trước deadline | Không thể chờ 10 lần chạy trong 1 giờ |
| Chạy cuối tháng | Không hoàn tất kỳ đóng sổ đúng hạn | Tỷ lệ theo ngày thường là N/A |
| Job cần tự restart | Tỷ lệ failure theo execution + số restart + completion trước deadline | Tránh bỏ sót sự cố lặp lại nhưng tự hồi phục |

### 10.2. Phối hợp tỷ lệ, freshness và duration

Một hệ thống monitoring batch cần ít nhất ba nhóm tín hiệu:

- **Outcome:** bao nhiêu lần chạy kết thúc `FAILED`?
- **Freshness:** job có chạy và hoàn tất đúng lịch không?
- **Latency:** job chạy có lâu bất thường hoặc vượt deadline không?

Ví dụ `importOrdersJob` không được khởi chạy trong 12 giờ. Failure rate bằng N/A vì không có execution trong cửa sổ, nhưng tình trạng đó có thể nguy hiểm hơn 2% failure. Cần cảnh báo “missing expected run” dựa trên lịch hoặc time since last successful completion.

Một job đang ở `STARTED` trong 8 giờ cũng chưa tạo thêm `FAILED`. Hãy theo dõi execution đang chạy quá ngưỡng thời gian, không chờ nó chuyển thành `FAILED` mới phát hiện.

### 10.3. Đề xuất chính sách cảnh báo minh họa

Giả sử một hệ thống xử lý đơn hàng thường xuyên có SLO failure rate dưới 1% theo tuần. Có thể dùng:

1. **Cảnh báo nhanh:** failure rate tăng trên một ngưỡng ngắn hạn, với số mẫu đủ lớn.
2. **Cảnh báo bền vững:** failure rate 24 giờ vượt ngưỡng; tránh chỉ dựa trên đột biến một vài phút.
3. **Cảnh báo theo kỳ:** job critical không có `COMPLETED` trước deadline.
4. **Cảnh báo trạng thái:** execution ở `STARTED` quá lâu, `UNKNOWN` hoặc `ABANDONED` ngoài kế hoạch.

Ngưỡng số học trong ví dụ là điểm khởi đầu cần được hiệu chỉnh theo lịch chạy, hệ số ảnh hưởng nghiệp vụ và mức nhiễu có thể chấp nhận. Nếu nhiều job chia sẻ cùng dashboard, mỗi nhóm job có thể cần policy khác nhau.

## 11. Theo dõi nguyên nhân failure để hành động được

Tỷ lệ failure cho biết **có vấn đề**; nó không đủ để giải thích **vì sao**. Khi một job có failure rate tăng, cần đi từ metric sang `JobExecution` cụ thể.

Luồng điều tra:

```text
Dashboard: importOrdersJob failure rate tăng
                 |
                 v
Tìm các JobExecution FAILED trong thời gian tăng
                 |
                 v
Đọc JOB_EXECUTION_ID, JobParameters, thời gian, ExitStatus
                 |
                 v
Tìm StepExecution FAILED và exception/stacktrace
                 |
                 +-- Lỗi input: dữ liệu không hợp lệ, file thiếu
                 +-- Lỗi database: connection, deadlock, unique constraint
                 +-- Lỗi dependency: API timeout, queue unavailable
                 +-- Lỗi logic: processor/writer exception
                 +-- Lỗi tài nguyên: memory, disk, thread pool
                 |
                 v
Khắc phục -> rerun/restart theo đúng contract -> theo dõi hồi phục
```

Với Spring Batch Java, `JobExecution` có thể cung cấp danh sách failure exceptions, và các `StepExecution` có status, exit status, các bộ đếm read/write/skip. Những thông tin này giúp liên hệ tỷ lệ failure với nguyên nhân cụ thể.

Trong hệ thống logs, một số trường có ích:

```text
jobName
jobInstanceId
jobExecutionId
stepName
stepExecutionId
businessDate
batchStatus
exitCode
durationMs
errorCategory
deploymentVersion
```

`errorCategory` nên là giá trị được chuẩn hóa có giới hạn số lượng, ví dụ `INPUT_VALIDATION`, `DATABASE`, `DEPENDENCY_TIMEOUT`. Chi tiết exception và stacktrace nên nằm trong log/trace thay vì làm nhãn metric.

### Lỗi ở cấp step có phải job failure?

Không phải mọi item bị skip hoặc một exception đã được xử lý đều tạo `JobExecution.FAILED`. Ngược lại, một step thất bại nhưng job flow được cấu hình để xử lý và vẫn `COMPLETED` có thể là hành vi chủ đích. Vì vậy:

- Tính **job failure rate** dựa trên outcome cấp job theo định nghĩa.
- Theo dõi **step failure, skip rate và retry count** bằng metric bổ sung.
- Nếu cần “business failure rate” (ví dụ hóa đơn xử lý không hợp lệ), định nghĩa riêng theo số item hoặc kỳ nghiệp vụ.

Một job `COMPLETED` không bảo đảm 100% bản ghi nghiệp vụ được xử lý thành công; SLO cần phản ánh cả chất lượng dữ liệu.

## 12. Cách kiểm thử tính đúng của metric failure rate

Việc kiểm thử monitoring có hai cấp: **hàm tính toán** và **integration với vòng đời batch**.

### 12.1. Unit test công thức

Viết hàm nhận số failed/completed:

```java
public final class FailureRate {
    private FailureRate() {}

    /**
     * Trả về null khi không có completed/failed execution.
     * Giá trị còn lại trong khoảng [0, 1].
     */
    public static Double calculate(long failed, long completed) {
        if (failed < 0 || completed < 0) {
            throw new IllegalArgumentException("Counts must be non-negative");
        }
        long total = Math.addExact(failed, completed);
        return total == 0 ? null : (double) failed / total;
    }
}
```

JUnit 5:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class FailureRateTest {

    @Test
    void allCompletedMeansZeroFailureRate() {
        assertEquals(0.0, FailureRate.calculate(0, 20));
    }

    @Test
    void fourFailuresInTwentyRunsMeansTwentyPercent() {
        assertEquals(0.20, FailureRate.calculate(4, 16));
    }

    @Test
    void allFailedMeansOneHundredPercent() {
        assertEquals(1.0, FailureRate.calculate(5, 0));
    }

    @Test
    void noRunsMeansUnknownRate() {
        assertNull(FailureRate.calculate(0, 0));
    }

    @Test
    void negativeCountsAreInvalid() {
        assertThrows(IllegalArgumentException.class,
                () -> FailureRate.calculate(-1, 4));
    }
}
```

Định nghĩa hàm dùng `null` để biểu diễn “không có dữ liệu” vì dễ minh họa. Trong code production, có thể dùng `OptionalDouble` hoặc một DTO chứa `failed`, `completed`, `total` và thuộc tính `rate` nullable; chọn một contract rõ ràng cho API/dashboard.

### 12.2. Unit test listener Micrometer

Ví dụ kiểm tra rằng một `JobExecution.FAILED` làm tăng đúng counter tương ứng:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;

class JobOutcomeMetricsListenerTest {

    @Test
    void failedExecutionIncrementsFailureCounter() {
        try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
            JobOutcomeMetricsListener listener =
                    new JobOutcomeMetricsListener(registry);
            JobExecution execution = mock(JobExecution.class);
            JobInstance instance = mock(JobInstance.class);

            when(execution.getStatus()).thenReturn(BatchStatus.FAILED);
            when(execution.getJobInstance()).thenReturn(instance);
            when(instance.getJobName()).thenReturn("importOrdersJob");

            listener.afterJob(execution);

            assertEquals(1.0,
                    registry.get("batch.job.executions")
                            .tag("job.name", "importOrdersJob")
                            .tag("status", "FAILED")
                            .counter()
                            .count());
        }
    }
}
```

Kiểm tra tương tự với `COMPLETED` và `STOPPED`; xác minh `STARTED` không tạo thêm outcome counter. Unit test không cần gọi Prometheus, và nó xác nhận chính xác metric contract mà ứng dụng đã đăng ký.

### 12.3. Integration test với JobRepository

Một kịch bản kiểm thử đơn giản:

1. Tạo database test chứa bảng metadata Spring Batch.
2. Chạy job A thành công 3 lần với các identifying parameters khác nhau.
3. Dùng một job/step giả lập lỗi có kiểm soát để tạo 1 execution `FAILED` cho job A.
4. Truy vấn `JobRepository` bằng SQL tổng hợp đã thiết kế, trong một cửa sổ bao trùm các lần chạy.
5. Xác minh `C=3`, `F=1`, tỷ lệ `25%`.
6. Tạo thêm một execution `STOPPED` rồi xác minh nó không tự làm thay đổi tử số/mẫu số của failure rate chuẩn.
7. Restart một `JobInstance` đã thất bại và cho thành công; xác minh **execution rate** và **instance-final rate** trả kết quả khác nhau theo đúng định nghĩa.

Với integration test thực sự cần kiểm chứng status và timestamps của `JobExecution`, không nên chỉ tự insert bản ghi SQL giả: để Spring Batch chạy với `JobRepository` giúp phát hiện lệch giữa thời điểm kết thúc, status và metadata.

Khi tạo test failure, nên dùng một step cố tình throw exception (chẳng hạn `IllegalStateException`) và config test riêng. Không dùng các dependency production hoặc API gửi dữ liệu thật cho bài kiểm thử.

### 12.4. Test dữ liệu lịch sử và thiếu dữ liệu

Tạo fixture hoặc query kiểm tra:

| Kịch bản | Kỳ vọng |
| --- | --- |
| `COMPLETED=8`, `FAILED=2` | Tỷ lệ 20% |
| `COMPLETED=0`, `FAILED=4` | Tỷ lệ 100% |
| `COMPLETED=0`, `FAILED=0` | N/A |
| Có thêm 5 `STARTED` | Tỷ lệ không đổi; có metric running riêng |
| Có thêm 1 `STOPPED` | Không đổi theo định nghĩa chuẩn |
| Failure lúc 23:59:59 | Đúng cửa sổ ngày trước |
| Failure đúng 00:00:00 | Đúng cửa sổ ngày sau |
| Một failed execution rồi restart completed | Đếm 2 executions, 1 JobInstance |
| Metric counter bị reset khi restart JVM | Dashboard không bị hiểu thành số âm |
| Job không chạy đúng lịch | Freshness alert, dù failure rate là N/A |

## 13. Các lỗi thường gặp khi triển khai monitoring

### Sai mẫu số do tính tất cả execution

Nếu có 10 `COMPLETED`, 2 `FAILED`, 8 `STARTED`:

- Sai: `2/(10+2+8) = 10%`.
- Đúng theo công thức bài học: `2/(10+2) = 16,67%`.

Các execution đang chạy cần được theo dõi ở metric **running/long-running**, không làm giảm tỷ lệ failure bằng cách thêm vào mẫu số.

### Mỗi step FAILED bị đếm thành một job FAILED

Một job có nhiều step, và một step có thể bị retry nhiều lần. Đếm hàng `BATCH_STEP_EXECUTION` hoặc số exception không tương đương số `JobExecution.FAILED`. Truy vấn đúng bảng execution và status cấp job.

### Restart thành công làm “xóa” lịch sử failure

Nếu chỉ nhìn trạng thái mới nhất theo `JobInstance`, một instance đã restart thành công có thể che đi số lần thất bại trước đó. Giữ riêng hai biểu đồ: attempt failure rate và final outcome rate.

### Không có run được hiển thị là 0%

Một job đáng lẽ chạy mỗi giờ nhưng scheduler ngừng hoạt động có thể không có execution mới. Tỷ lệ 0% sẽ khiến dashboard báo “healthy” sai. Dùng `N/A` và cảnh báo **missing run**.

### Query dựa trên START_TIME trong khi dashboard mô tả outcome theo giờ

Một job chạy qua ranh giới cửa sổ có thể bị gán sai ngày. Nếu định nghĩa dựa trên **kết quả đã kết thúc**, sử dụng `END_TIME`. Nếu muốn báo cáo theo business date, cần một trường hoặc JobParameter được xác định riêng.

### Đếm cả STOPPED mà không công bố policy

Ngừng job có chủ đích để bảo trì khác với failure. Theo dõi STOPPED riêng hoặc định nghĩa metric “unsuccessful rate” có giải thích.

### Counter từ listener bị thiếu khi JVM chết

Tiến trình có thể dừng trước khi afterJob được gọi, hoặc trước khi Prometheus kịp scrape. Đối soát `JobRepository` và quan sát thời gian không có scrape. Không coi missing series là healthy.

### Trộn metrics của các môi trường

Nếu cả staging và production cùng xuất job name `importOrdersJob`, tổng hợp thiếu label môi trường sẽ cho kết quả sai. Luôn xác định phạm vi dashboard trước khi `sum by(job_name)`.

### Nhãn metric có cardinality cao

Đưa execution ID, business date hoặc exception message vào label có thể tạo hàng trăm nghìn series. Giữ chi tiết ở log và dùng nhãn metric có giới hạn số lượng.

### Tỷ lệ failure giảm nhưng dữ liệu vẫn sai

Một job có thể đạt `COMPLETED` dù item bị filter/skip sai nghiệp vụ hoặc writer ghi sai dữ liệu. Kết hợp failure rate với freshness, record count, error/quarantine count, cân đối tổng tiền và kiểm tra đầu ra.

## 14. Bài tập áp dụng: xây bảng theo dõi failure rate

Giả sử hệ thống có ba job:

- `importOrdersJob` chạy mỗi 10 phút.
- `settlePaymentsJob` chạy hằng đêm.
- `monthlyCloseJob` chạy một lần mỗi tháng.

### Bài 1: thiết kế nguồn dữ liệu

Trong database test, tạo những `JobExecution` có `END_TIME`, `STATUS`, `JOB_NAME` rõ ràng. Viết query nhóm theo tên job, đếm `COMPLETED`/`FAILED` trong 24 giờ. Hiển thị cả số lần chạy và phần trăm.

Kỳ vọng: `importOrdersJob` có `FAILED=3` và `COMPLETED=27` thì rate là `10%`. `monthlyCloseJob` không chạy trong hôm nay thì là N/A.

### Bài 2: phân biệt execution và instance

Tạo `JobInstance` của `settlePaymentsJob` thất bại một lần rồi restart thành công. Chỉ ra rằng execution failure rate là `50%` trong hai lần cố gắng, còn final instance failure rate là `0%`.

### Bài 3: bổ sung metrics

Đăng ký `JobOutcomeMetricsListener`. Dùng `SimpleMeterRegistry` assert một run thất bại tạo một counter increment với tag `status=FAILED`. Sau đó xuất metrics qua hệ Prometheus của dự án, xác nhận tên metric và tag thực tế.

### Bài 4: định nghĩa cảnh báo

Chọn một ngưỡng phù hợp cho job chạy 10 phút/lần. Với job chạy hằng đêm, thiết kế alert khi job `FAILED` hoặc chưa có `COMPLETED` sau giờ deadline. Giải thích tại sao cùng một ngưỡng phần trăm không phù hợp cho cả hai.

### Bài 5: mô phỏng lỗi vận hành

Cho tiến trình đang chạy bị dừng đột ngột. Kiểm tra cách hệ thống quan sát trạng thái `STARTED` quá lâu hoặc thiếu lần hoàn tất, thay vì chỉ dựa vào counter failure từ `afterJob`. Bổ sung cơ chế cảnh báo hoặc đối soát dựa trên `JobRepository`.

## 15. Kết luận

**Tỷ lệ failure theo job** là tỷ lệ số `JobExecution.FAILED` trên tổng số execution `FAILED + COMPLETED` của một job trong cửa sổ được xác định rõ. Đây là chỉ số hữu ích để theo dõi độ ổn định và nhận diện regression, nhưng chỉ có ý nghĩa khi đi cùng **mẫu số, cửa sổ thời gian và quy tắc phân loại trạng thái**.

Trong Spring Batch, cần phân biệt một lần cố gắng chạy (`JobExecution`) với một công việc logic có thể restart (`JobInstance`). Dùng `JobRepository` để có lịch sử execution có thể truy vấn và đối soát; dùng Micrometer/Prometheus cho dashboard và cảnh báo gần thời gian thực. Bổ sung **last-success freshness**, **duration**, **trạng thái running**, **completion theo deadline** và **chất lượng dữ liệu đầu ra** để không bỏ sót các tình huống hệ thống không chạy, chạy quá chậm hoặc chạy “thành công” nhưng không đạt yêu cầu nghiệp vụ.

### Tài liệu tham khảo

- [Spring Batch Reference – Domain: Job, JobInstance và JobExecution](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html)
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Micrometer – Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html)
- [Prometheus – increase() và các hàm truy vấn](https://prometheus.io/docs/prometheus/latest/querying/functions/)
