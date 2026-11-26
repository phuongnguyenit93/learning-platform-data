# Đã thiết lập metrics và alert cho Spring Batch production

> **Chương:** Checklist production  
> **Module:** `SPRING_BATCH_SCALING_OPERATIONS` — mở rộng Spring Batch cho dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và mô hình xử lý phân tán. Bài này tập trung vào khả năng đo nút thắt, quan sát retry/restart, bảo đảm dữ liệu đúng và vận hành job an toàn khi tăng số worker.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Định nghĩa thế nào là **đã thiết lập metrics và alert** và biết cách chứng minh cảnh báo thực sự hoạt động trên production.
2. Chọn tín hiệu quan sát cho scheduler, `JobExecution`, `StepExecution`, chunk, partition, worker, broker, database và dữ liệu nghiệp vụ.
3. Thiết lập Micrometer, Spring Boot Actuator và một nguồn giám sát bền vững đọc metadata từ `JobRepository`.
4. Viết alert về job lỗi, trễ hạn, mắc kẹt, backlog, retry bất thường và đối soát dữ liệu thất bại.
5. Tạo dashboard, ngưỡng SLO, runbook, kiểm thử cảnh báo và chính sách phân quyền phù hợp trước khi go-live.

## 1. Checklist này được coi là hoàn thành khi nào?

Hệ thống có trang `/actuator/prometheus` hoặc có vài biểu đồ CPU **chưa đủ** để đánh dấu mục “Đã thiết lập metrics và alert”. Với Spring Batch, người vận hành phải trả lời được bốn câu hỏi:

1. **Công việc có được khởi chạy đúng lịch không?** Có batch nào bị bỏ lỡ hay vô tình chạy trùng?
2. **Tiến độ và lỗi nằm ở đâu?** Job, step, partition, worker, database hay broker?
3. **Kết quả có đúng không?** Có record thiếu/thừa/trùng, tổng tiền lệch hoặc downstream chưa xác nhận không?
4. **Ai được thông báo và xử lý thế nào?** Cảnh báo được gửi tới người trực đúng lúc, có tài liệu ứng cứu và điều kiện đóng sự cố.

Một checklist đạt production cần có **metric được thu thập ổn định, dashboard hữu dụng, alert gắn SLO, đầu mối chịu trách nhiệm, runbook và bằng chứng thử alert thành công**. Mỗi tín hiệu phải có định nghĩa rõ ràng; số liệu đẹp nhưng không thể dẫn đến hành động thực tế là số liệu ít giá trị.

### Các lớp quan sát không thể thay thế cho nhau

| Lớp | Trả lời câu hỏi | Không đủ để kết luận |
|---|---|---|
| **Metrics** | Tỷ lệ lỗi, duration, throughput, backlog, saturation thay đổi ra sao? | Business record nào bị sai |
| **Logs** | Execution/partition nào lỗi, mã lỗi gì, release nào? | Toàn bộ luồng phân tán nếu thiếu correlation |
| **Traces** | Request qua manager, broker, worker, DB chậm ở đâu? | Dữ liệu đầu ra đã đủ và đúng |
| **`JobRepository` metadata** | `JobExecution`/`StepExecution` có trạng thái và số đếm gì? | External side effect và dữ liệu nghiệp vụ đã commit chính xác |
| **Đối soát nghiệp vụ** | Snapshot đầu vào và dữ liệu đích có cùng khóa, số lượng, giá trị không? | Nguyên nhân kỹ thuật gây ra sai lệch |

Vì vậy cần **metrics vận hành + metadata Batch + đối soát độc lập**. Một job trả về `COMPLETED` vẫn có thể sinh dữ liệu sai nếu logic filter/writer có lỗi; một worker ghi thành công rồi chết trước khi ack có thể dẫn đến redelivery mà chỉ nhìn số message sẽ không thấy dữ liệu trùng.

## 2. Xác định SLI và SLO trước khi đặt alert

**SLI (Service Level Indicator)** là chỉ số đo mức đáp ứng thực tế; **SLO (Service Level Objective)** là mục tiêu đã cam kết đối với chỉ số ấy. Không dùng ngưỡng chung cho mọi batch.

Ví dụ một job settlement chạy hàng ngày:

| Mục tiêu nghiệp vụ | SLI tương ứng | SLO minh họa |
|---|---|---|
| Dữ liệu có đủ trước giờ mở sổ | Thời điểm batch **đã đối soát** so với deadline của kỳ | Hoàn tất trước 06:00 theo lịch nghiệp vụ |
| Không mất hoặc trùng giao dịch | Missing/extra/duplicate business key, value mismatch | Bằng 0 trước khi publish |
| Job hoạt động ổn định | Tỷ lệ `JobExecution` hoàn tất sau retry/restart hợp lệ | Ngưỡng do nhóm xác định từ baseline |
| Không có xử lý kéo dài bất thường | Thời gian job/step/partition và tiến độ gần nhất | Theo p95/p99 và deadline thực |
| Tăng tải không gây nghẽn downstream | Queue age, pool wait, CPU/heap, DB lock wait | Không vượt ngân sách tài nguyên |
| Có thể phát hiện và ứng cứu | Thời gian từ điều kiện lỗi đến cảnh báo tới on-call | Trong khoảng đã diễn tập |

Các giá trị trong bảng là **ví dụ**. Với job không chạy cuối tuần, không được tạo cảnh báo “24 giờ chưa chạy” vào Chủ nhật nếu lịch không có job. Với job theo kỳ/tháng, deadline phải lấy từ lịch kinh doanh, timezone, ngày nghỉ và điều kiện upstream thay vì suy bằng một phép trừ thời gian cố định.

### 2.1. Đo latency nào?

Phân biệt ít nhất:

- **Schedule delay:** thời điểm thực sự launch trừ thời điểm được lên lịch.
- **Queue wait:** từ khi công việc được dispatch tới lúc worker bắt đầu xử lý.
- **Processing duration:** từ bắt đầu tới kết thúc job/step/chunk/partition.
- **End-to-end freshness:** từ snapshot/cutoff nguồn tới lúc kết quả downstream **được đối soát và cho phép dùng**.

Nếu job xử lý xong lúc 04:00 nhưng downstream chỉ xác nhận hoàn tất lúc 07:00, việc báo “SLO hoàn thành trước 06:00 đạt” là sai nếu SLO quy định dữ liệu dùng được trước 06:00.

### 2.2. Chọn ngưỡng theo baseline

Ghi nhận cùng loại workload ở nhiều kỳ: số input, tỷ lệ filter/skip, kích thước partition, số worker, DB load, p50/p95/p99 duration và thời gian peak. Sau đó đặt threshold có **hành động tương ứng**. Ví dụ, tăng số worker từ 4 lên 8 mà throughput không tăng nhưng JDBC pool wait tăng mạnh là tín hiệu phải giảm concurrency hoặc tối ưu DB, không nhất thiết là lỗi JVM.

## 3. Danh mục metrics cần có ở từng lớp

Nên lập một **metric inventory** với các cột: metric, ý nghĩa, kiểu, đơn vị, owner, nguồn phát, nhãn, retention, dashboard, alert và runbook. Bảng dưới đây nêu các tín hiệu tối thiểu.

| Lớp | Metrics / trạng thái nên đo | Vì sao cần |
|---|---|---|
| Scheduler / JobLauncher | Giờ kỳ vọng, lần launch gần nhất, launch thất bại, job bị bỏ lịch, launch trùng | Job chưa chạy sẽ không sinh metric từ worker |
| `JobRepository` | Số job theo `STARTED`/`FAILED`/`COMPLETED`/`STOPPED`, thời gian chạy, lần thành công gần nhất | Theo dõi vòng đời thực thi và job treo |
| Step / chunk | Read/write/filter/skip counts, rollback, retry, chunk duration, commit rate | Phát hiện tiến độ và chỗ lỗi |
| Partition | Active/failed/completed partitions, p95/max partition duration, skew | Tìm partition treo hoặc chia dải lệch |
| TaskExecutor | Active threads, queue depth, rejected tasks | Phân biệt thiếu worker với pool đầy |
| Worker / JVM | CPU, heap, GC pause, thread count, restart/OOM | Phát hiện saturation cục bộ |
| Broker / messaging | Consumer count, lag/queue depth, message age, unacked, redelivery, DLQ, pending replies | Giám sát remote chunking/partitioning và drain |
| Database | Pool active/idle/pending, connection timeout, query/commit latency, lock wait | Nhận diện DB là nút thắt |
| External sink | API error/timeout, rate limit, downstream receipt/watermark | Xác nhận side effect ngoài transaction |
| Business reconciliation | Missing/extra/duplicate keys, mismatch value, totals, last matched batch | Chứng minh đầu ra đúng |
| Monitoring pipeline | Exporter `up`, scrape errors, dữ liệu cũ, mất series và alert delivery | Tránh trạng thái “không thấy lỗi vì không còn đo được” |

**Đừng nhân tất cả metric lên theo `jobExecutionId` hoặc business key.** Những định danh này có cardinality rất cao; nhiều metric backend tốn RAM/chi phí và khó phân tích. Execution ID là dữ liệu tốt cho log/tracing hoặc truy vấn JobRepository, còn label metric nên giữ số giá trị nhỏ, được kiểm soát.

## 4. Hiểu đúng số đếm của Spring Batch

Spring Batch ghi metadata ở cấp `JobExecution` và `StepExecution`. Khi vận hành, các trường thường hữu ích gồm:

| Trường | Có thể dùng để | Giới hạn |
|---|---|---|
| `readCount` | Đo số item đọc thành công trong một step execution | Không tự bằng số bản ghi nguồn trong snapshot |
| `writeCount` | Đo số item qua writer thành công theo thống kê Batch | Không tự bằng số dòng đã commit ở mọi hệ thống đích |
| `filterCount` | Quan sát số item processor loại bỏ, thường bằng cách trả `null` | Không tự chứng minh việc lọc đúng nghiệp vụ |
| `readSkipCount` | Phát hiện skip khi đọc | Cần xác định business record bị skip để đối soát |
| `processSkipCount` | Phát hiện skip khi xử lý | Chưa cho biết việc skip có được phê duyệt |
| `writeSkipCount` | Phát hiện skip khi ghi | Có thể liên quan retry/rollback hoặc lỗi sink |
| `rollbackCount` | Tín hiệu transaction rollback | Không đồng nghĩa bấy nhiêu item mất dữ liệu |
| `BatchStatus` / `ExitStatus` | Diễn giải trạng thái execution | `COMPLETED` chưa xác nhận toàn vẹn nghiệp vụ |

Khi restart, **một `JobInstance` có thể có nhiều `JobExecution`**. Không cộng tất cả `readCount`/`writeCount` qua mọi lần thử rồi coi đó là số business key duy nhất. Khi remote partitioning, cần lấy số đếm worker `StepExecution` đúng cấp; cộng thêm manager step có thể đếm đôi.

### 4.1. Đọc số liệu tại đúng ranh giới transaction

Một số external API hoặc broker không nằm trong cùng transaction với metadata và business DB. Worker có thể đã commit DB nhưng chết trước reply; job có thể retry và thực hiện lại cùng work item. Vì vậy hệ thống phải có:

1. **Khóa idempotency nghiệp vụ** ổn định qua retry/restart.
2. **Bằng chứng đích độc lập**, ví dụ row duy nhất theo business key hoặc receipt từ hệ thống ngoài.
3. **Reconciliation** theo input snapshot và rule version, phát cảnh báo khi missing/extra/value mismatch.

Không tuyên bố “exactly-once” chỉ vì chart write count bằng input count.

## 5. Khai báo tên, đơn vị và nhãn metric

Hãy tách **metric do thư viện phát ra** khỏi **metric do ứng dụng tự định nghĩa**. Tên và tag của metric có sẵn có thể khác theo phiên bản Spring Batch, Spring Boot, Micrometer hoặc exporter. Kiểm tra endpoint metric thật trong môi trường chạy trước khi viết dashboard/alert.

Ví dụ hợp đồng metrics **do hệ thống tự thiết kế**:

| Metric Prometheus minh họa | Kiểu / nguồn | Mục đích |
|---|---|---|
| `batch_job_executions_total` | Counter từ ứng dụng hoặc collector có semantics rõ | Đếm execution theo `job_name`, `outcome` |
| `batch_job_last_success_timestamp_seconds` | Gauge từ metadata bền vững | Kiểm tra độ tươi của thành công gần nhất |
| `batch_job_deadline_missed` | Gauge 0/1 từ scheduler + JobRepository | Phát hiện không hoàn thành đúng lịch |
| `batch_job_running_age_seconds` | Gauge từ JobRepository | Phát hiện execution chạy quá lâu |
| `batch_job_failed_executions_15m` | Gauge từ collector bền vững | Phát hiện execution vừa lỗi |
| `batch_partition_active` | Gauge từ worker metadata | Xem số partition đang chạy |
| `batch_partition_failed` | Gauge theo logical batch/step | Phát hiện partition lỗi chưa xử lý |
| `batch_worker_inflight` | Gauge của worker/broker | Đo công việc đã nhận chưa hoàn tất |
| `batch_queue_oldest_unacked_age_seconds` | Gauge từ broker/adapter | Phát hiện message treo lâu |
| `batch_worker_retries_total` | Counter từ worker | Đo retry theo lý do chuẩn hóa |
| `batch_reconciliation_unmatched_records` | Gauge từ bảng đối soát | Phát hiện thiếu/thừa/sai giá trị |
| `batch_reconciliation_last_match_timestamp_seconds` | Gauge từ kho đối soát | Kiểm tra freshness của kết quả đã khớp |

Đây **không phải** danh sách metric mặc định mà Spring Batch tự tạo. Ví dụ `batch_job_deadline_missed` và `batch_reconciliation_unmatched_records` phải được ứng dụng/collector thiết kế và cập nhật dựa trên dữ liệu đáng tin cậy.

### 5.1. Quy ước nhãn và cardinality

Nhãn hợp lý:

~~~text
job_name         = daily_settlement | invoice_export | customer_sync
step_name        = load | transform | persist
release          = blue | green | canary
outcome          = COMPLETED | FAILED | STOPPED
worker_group     = settlement | export
reason_code      = DB_TIMEOUT | INVALID_INPUT | BROKER_UNAVAILABLE
~~~

Nhãn nên tránh:

~~~text
job_execution_id = 821629283    # Tăng không giới hạn
transaction_id   = ...
customer_email   = ...
national_id      = ...
raw_exception    = ...          # Chứa text tùy ý / có thể chứa PII
~~~

Giữ metric name và label ổn định qua release. Dùng **seconds**, **bytes** và tên counter kết thúc bằng `_total` theo quy ước Prometheus. Histogram/timer giúp quan sát phân vị latency; một giá trị “trung bình” có thể che giấu partition chậm nhất.

### 5.2. Tách scope quan sát

Dashboard có thể chiếu `release` và `worker_group`; câu hỏi “job ngày D đã hoàn thành chưa?” nên được trả lời bởi **logical batch ID trong control store** hoặc metadata truy vấn, không biến mỗi `batchId` thành một Prometheus time series vô hạn. Với các execution đặc biệt, mở log theo correlation ID hoặc truy vấn `JobExplorer`/`JobRepository`.

## 6. Thu thập metrics bằng Micrometer và Spring Boot Actuator

Spring Batch có tích hợp quan sát dựa trên Micrometer ở các phiên bản hỗ trợ; Spring Boot Actuator có thể xuất metrics ra endpoint như Prometheus khi dependency/exporter được cấu hình. Một số timer Spring Batch thường gặp liên quan job, step, item read/process và chunk write; **tên thực tế và tag phải kiểm tra theo release**. Đừng cố đặt lại custom metric trùng tên với metric framework rồi cộng hai nguồn như một.

### 6.1. Ví dụ dependencies (Spring Boot + Prometheus)

~~~xml
<!-- Trích đoạn pom.xml minh họa; phiên bản được quản lý bởi BOM dự án. -->
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>io.micrometer</groupId>
        <artifactId>micrometer-registry-prometheus</artifactId>
    </dependency>
</dependencies>
~~~

### 6.2. Expose endpoint trong mạng quản trị

~~~yaml
# application.yml - minh họa khi dùng Spring Boot Actuator
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: settlement-batch
  endpoint:
    health:
      probes:
        enabled: true
~~~

Áp dụng **xác thực, network policy/ingress nội bộ hoặc mTLS** cho metrics endpoint; đừng mở công khai vì dữ liệu có thể tiết lộ cấu trúc dịch vụ, topology và tải hệ thống. Việc expose endpoint chỉ làm cho dữ liệu **có thể được scrape**; cần cấu hình Prometheus/agent thực sự thu thập, lưu, và kiểm tra `up`, scrape interval, target labels và retention.

Nếu job chạy xong rồi pod thoát sau vài phút, Prometheus có thể **không kịp scrape** lần phát metric hoặc series biến mất khi pod kết thúc. Không chỉ dựa vào in-memory counters của short-lived batch process để phát hiện job không chạy hoặc lỗi kỳ trước.

### 6.3. Thêm metric riêng bằng Micrometer

Ví dụ listener Java phát counter theo kết quả thực thi:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class BatchMetricConfiguration {

    @Bean
    JobExecutionListener jobResultMetrics(
            MeterRegistry registry,
            ReleaseMetadata releaseMetadata) {

        return new JobExecutionListener() {
            @Override
            public void afterJob(JobExecution jobExecution) {
                String jobName = jobExecution.getJobInstance().getJobName();
                String outcome = jobExecution.getStatus().name();

                registry.counter(
                        "batch.job.executions",
                        "job_name", jobName,
                        "outcome", outcome,
                        "release", releaseMetadata.releaseChannel()
                ).increment();
            }
        };
    }
}
~~~

`ReleaseMetadata` là abstraction của ứng dụng. Khi xuất qua Prometheus, một counter Micrometer tên `batch.job.executions` thường được chuẩn hóa thành metric dạng `batch_job_executions_total`; hãy **kiểm tra tên xuất thực tế** trên target đang dùng trước khi chốt PromQL.

Hạn chế quan trọng: nếu JVM bị kill trước khi `afterJob` chạy hoặc counter được scrape, sự cố có thể **không xuất hiện**. Listener hỗ trợ quan sát cục bộ; **source of truth cho trạng thái bền vững phải đến từ JobRepository và scheduler**, được đọc bởi một collector luôn hoạt động hoặc cơ chế thích hợp khác.

## 7. Giám sát bền vững bằng JobRepository và lịch chạy

Với job theo lịch, một vấn đề nguy hiểm là **“không có metric nghĩa là không có lỗi”**. Thực tế, không có metric có thể là job chưa được launch, process chết trước khi báo lỗi, collector mất kết nối hoặc dashboard đang lọc sai nhãn.

Kiến trúc gợi ý:

~~~mermaid
flowchart LR
    S[Scheduler / JobLauncher] --> J[Spring Batch job]
    J --> R[(JobRepository)]
    J --> B[(Business sink)]
    J --> Q[(Broker / remote worker)]
    R --> C[Batch control exporter\nprocess chạy bền vững]
    S --> C
    B --> D[Reconciliation service]
    Q --> E[Broker exporter]
    D --> C
    C --> P[(Prometheus / metrics backend)]
    E --> P
    J -. Micrometer scrape .-> P
    P --> G[Dashboard]
    P --> A[Alert rules]
    A --> N[On-call / incident channel]
~~~

**Collector** trong sơ đồ là thành phần ứng dụng tự xây dựng hoặc tích hợp hiện có. Nó định kỳ đọc:

- `JobRepository` / `JobExplorer`: execution gần nhất, status, duration, các step treo và trạng thái restart.
- Scheduler/control store: **job nào được kỳ vọng chạy**, cutoff, deadline, lịch nghỉ và instance ownership.
- Reconciliation store: batch nào matched, mismatched hoặc inconclusive.
- Broker/exporter: backlog, consumer, unacked, DLQ, pending reply.

Collector nên chạy **độc lập** với worker, có readiness và liveness được giám sát. Nếu collector chết hoặc mất quyền đọc JobRepository, phải có alert riêng về mất quan sát.

### 7.1. Minh họa truy vấn lần hoàn tất gần nhất

Với schema JDBC metadata tương ứng trong nhiều phiên bản Spring Batch, có thể lấy một số liệu tham khảo bằng truy vấn:

~~~sql
SELECT MAX(e.END_TIME) AS last_completed_at
FROM BATCH_JOB_INSTANCE i
JOIN BATCH_JOB_EXECUTION e
  ON e.JOB_INSTANCE_ID = i.JOB_INSTANCE_ID
WHERE i.JOB_NAME = :job_name
  AND e.STATUS = 'COMPLETED';
~~~

Trong hệ thống thật, ưu tiên API phù hợp như `JobExplorer` để đọc metadata khi có thể. Tên bảng/cột, kiểu thời gian và schema cần xác minh theo phiên bản đã triển khai. Metric này chỉ chứng minh **lần hoàn thành Batch**, chưa đủ cho `data_reconciled`. Không sửa các bảng metadata để giải quyết cảnh báo; cần xác định nguyên nhân thực tế.

### 7.2. Định nghĩa tín hiệu trễ hạn đúng lịch

Collector có thể tính metric **tự định nghĩa**:

~~~text
batch_job_deadline_missed{job_name="daily_settlement"} = 1

Khi:
  kỳ nghiệp vụ gần nhất có một execution được kỳ vọng theo lịch,
  thời hạn hoàn tất đã qua,
  và chưa có bằng chứng hoàn thành/đối soát đáp ứng định nghĩa SLO.

Giá trị = 0 khi kỳ chưa đến hạn hoặc đã đạt điều kiện thành công.
~~~

Đối với job không chạy cuối tuần, collector lấy lịch có hiệu lực để **không** phát alert sai. Với upstream dependency chưa đủ dữ liệu, xác định SLO có cho phép defer hay cần cảnh báo riêng “upstream late”; không tùy tiện chuyển mọi trường hợp trễ thành thành công.

### 7.3. Phát hiện job mắc kẹt

Một execution có `STARTED` kéo dài bất thường có thể là worker chưa dừng, thread deadlock, transaction DB chờ hoặc metadata không được cập nhật vì process chết. Alert cần kết hợp:

- `running age` so với thời gian dự kiến cho loại job và khối lượng thực.
- Tiến độ gần nhất: read/write count hoặc watermark xử lý đã tăng chưa.
- Liveness của pod/process và active threads/partitions.
- Connection pool, DB locks, broker unacked/pending replies.

**Không tự sửa `BATCH_JOB_EXECUTION.STATUS` sang `FAILED`** để xóa alert. Việc phục hồi execution phải theo runbook, có fencing worker cũ và xác nhận dữ liệu đã commit.

## 8. Metrics và alert theo mô hình scaling

### 8.1. Multi-threaded step

Đo active threads, queue của `TaskExecutor`, step/chunk duration, retry, rollback, JVM heap/GC, JDBC pool wait và output business key. Khi tăng concurrency, nếu read/write throughput không tăng nhưng pool wait hoặc lock contention tăng, **bottleneck ở downstream**.

Một step có thể có nhiều thread nhưng bộ đếm vẫn thuộc cùng `StepExecution`. Không giả định reader/writer stateful là thread-safe; metric output mismatch hoặc duplicate key có thể phản ánh race condition.

### 8.2. Parallel steps

Đo duration/status của từng nhánh và **critical path** hoàn tất job. Một nhánh thành công không có nghĩa tất cả nhánh đã sẵn sàng cho bước phụ thuộc. Cảnh báo step treo nên biết phụ thuộc: step cố ý đang đợi tín hiệu không nên bị đánh dấu lỗi chỉ vì số item xử lý bằng 0.

### 8.3. Local và remote partitioning

Đo số partition logic được giao, started/completed/failed, duration tối đa, p95, input/output per partition và các partition bị retry. Với remote partitioning, thêm độ trễ dispatch, heartbeat/liveness worker, assignment ownership, reply lag và khả năng mất worker.

Một partition lớn có thể chiếm 70% dữ liệu; vậy `90% partition completed` **không chứng minh** đã xử lý 90% item. Theo dõi remaining work theo count/weight từ manifest.

### 8.4. Remote chunking

Manager đọc và phát chunk request, worker xử lý/ghi và gửi reply. Cần đo:

- Request **đã phát** và reply **đã correlate** với execution.
- Message unacked, độ tuổi message lâu nhất, redelivery và DLQ.
- Số worker đang xử lý, chunk latency tại worker và round-trip latency.
- Số business row đã commit và trạng thái reconciliation.

Nếu worker đã commit DB nhưng reply thất lạc, queue/manager có thể báo chunk chưa xong trong khi output đã tồn tại. Không retry mù quáng khi writer/downstream chưa có idempotency key.

### 8.5. Tài nguyên downstream là một phần của alert

Khi worker scale từ 4 lên 24, hệ thống có thể tăng:

~~~text
worker concurrency
    -> active JDBC connections
    -> DB lock wait / connection pending
    -> chunk latency
    -> job duration / queue lag
~~~

Nếu chỉ alert CPU worker, nhóm có thể bỏ sót nguyên nhân gốc. Dashboard cần đặt **throughput cùng pool wait, DB timeouts, broker lag và latency downstream** trên cùng trục thời gian để nhìn thấy tác động của việc tăng số worker.

## 9. Viết alert có điều kiện rõ ràng

### 9.1. Nguyên tắc

Một alert hữu ích nên có: **tín hiệu → điều kiện → mức ưu tiên → nơi nhận → runbook → tiêu chí hồi phục**. Phân biệt:

- **Page/P1:** sai dữ liệu, deadline nghiệp vụ quan trọng đã quá, lỗi không có đường phục hồi tự động.
- **Warning/P2:** retry/backlog/latency tăng, có nguy cơ trễ hoặc cạn tài nguyên nhưng vẫn có thời gian xử lý.
- **Info:** rollout thay đổi concurrency, partition skew nhẹ hoặc nhu cầu tune; không cần đánh thức on-call.

Giới hạn tần suất thông báo, nhóm theo job/team và **inhibit các cảnh báo hệ quả** khi một nguyên nhân gốc đã được xác nhận. Đừng tạo một page cho mỗi partition failed hoặc mỗi worker timeout; một sự cố DB có thể tạo hàng nghìn bản sao cảnh báo.

### 9.2. Ví dụ alert rules dạng Prometheus

Đoạn sau dùng **metric tự định nghĩa ở phần 5** và ngưỡng minh họa. Nó chỉ hoạt động khi collector/exporter đã thực sự xuất các series với đúng tên và label. Đây là phần `groups` của file rule Prometheus, không phải Kubernetes `PrometheusRule` CRD hoàn chỉnh.

~~~yaml
groups:
  - name: spring-batch-production
    rules:
      - alert: BatchJobDeadlineMissed
        expr: batch_job_deadline_missed{job_name="daily_settlement"} == 1
        for: 5m
        labels:
          severity: critical
          team: data-platform
        annotations:
          summary: "Batch daily_settlement đã quá deadline"
          description: "Kiểm tra scheduler, JobRepository, nguồn và trạng thái đối soát."
          runbook_url: "https://docs.example.invalid/runbook/batch-deadline"

      - alert: BatchJobFailedRecently
        expr: batch_job_failed_executions_15m{job_name="daily_settlement"} > 0
        for: 2m
        labels:
          severity: warning
          team: data-platform
        annotations:
          summary: "Batch daily_settlement có execution thất bại"
          runbook_url: "https://docs.example.invalid/runbook/batch-failed"

      - alert: BatchJobRunningTooLong
        expr: batch_job_running_age_seconds{job_name="daily_settlement"} > 14400
        for: 10m
        labels:
          severity: warning
          team: data-platform
        annotations:
          summary: "Batch daily_settlement chạy lâu hơn 4 giờ"
          runbook_url: "https://docs.example.invalid/runbook/batch-stuck"

      - alert: BatchReconciliationMismatch
        expr: batch_reconciliation_unmatched_records{job_name="daily_settlement"} > 0
        for: 2m
        labels:
          severity: critical
          team: data-platform
        annotations:
          summary: "Dữ liệu đầu ra của batch chưa khớp đầu vào"
          runbook_url: "https://docs.example.invalid/runbook/batch-reconciliation"

      - alert: BatchQueueUnackedTooOld
        expr: batch_queue_oldest_unacked_age_seconds{route="settlement"} > 900
        for: 10m
        labels:
          severity: warning
          team: data-platform
        annotations:
          summary: "Message settlement chưa ack quá ngưỡng"
          runbook_url: "https://docs.example.invalid/runbook/batch-broker"
~~~

Đường dẫn `example.invalid` là **placeholder**, phải thay bằng runbook nội bộ có quyền truy cập phù hợp. Những giá trị `4 giờ` và `900 giây` không phải khuyến cáo chung: partition có thể chạy hợp lệ lâu hơn ngưỡng đó. Điều chỉnh theo loại job và SLA, hoặc dùng tiến độ thực thay cho timeout thuần túy.

### 9.3. Alert khi mất dữ liệu quan sát

Mất metric đôi khi nguy hiểm không kém lỗi job. Cần thêm điều kiện:

~~~promql
# Ví dụ: series last-success của job quan trọng biến mất.
absent(batch_job_last_success_timestamp_seconds{job_name="daily_settlement"})

# Kiểm tra exporter ổn định không thể scrape:
up{job="batch-control-exporter"} == 0
~~~

`up == 0` chỉ bắt được target được biết đến nhưng scrape thất bại; nếu target biến mất khỏi service discovery, cũng cần cơ chế phát hiện **absent/upstream discovery**. Với metric dạng timestamp, thêm cảnh báo stale dữ liệu bằng thời gian cập nhật exporter hoặc freshness của snapshot. Không xem series biến mất là “job đã ổn”.

### 9.4. Tránh alert bắn sai sau khi restart

Micrometer counter trong JVM **reset khi process restart**. Prometheus có thể xử lý counter reset trong `rate()`/`increase()` khi series còn được scrape đầy đủ; nhưng với job ngắn hoặc pod chết giữa hai lần scrape, sự kiện vẫn có thể bị mất. Đối với quyết định paging về job đã lỗi, ưu tiên metric **được suy từ metadata bền vững**. Không dùng `sum(all StepExecution writeCount)` như counter tiến độ nếu restart có thể làm số lượng phình lên.

## 10. Dashboard tối thiểu phục vụ người trực

Một dashboard vận hành nên trả lời được **“job nào, ảnh hưởng dữ liệu gì, stuck ở đâu, nên làm gì trước?”** trong một lần mở.

| Khu vực | Panel gợi ý | Hành động hỗ trợ |
|---|---|---|
| **Batch overview** | Lần chạy kỳ vọng, last start/success, current status, deadline, release | Xem job trễ/lỗi |
| **Execution progress** | Step và partition status, read/write/filter/skip, elapsed vs baseline | Tìm bước nghẽn và phần việc còn lại |
| **Remote workflow** | Queue depth/age, consumer count, unacked, pending reply, DLQ | Phân biệt broker và worker |
| **Resources** | CPU, heap, GC, executor active/queued, JDBC pending, DB locks | Ra quyết định giảm/tăng concurrency |
| **Data correctness** | Missing, extra, duplicate keys, value mismatch, control totals, reconciliation status | Quyết định có được publish dữ liệu |
| **Incidents** | Alert đang firing, release gần đây, runbook link, last deploy/config | Định hướng điều tra và khôi phục |

Dashboard tổng hợp nên có bộ lọc `job_name`, `worker_group`, `environment` và `release`. Khi cần drill-down theo execution, dùng link tới JobRepository viewer/log search đã phân quyền; đừng ép Prometheus mang mọi `jobExecutionId` vào labels.

### Tín hiệu phải đọc cùng nhau

Giả sử tăng worker từ 4 lên 12:

| Chỉ số | Trước | Sau | Diễn giải minh họa |
|---|---:|---:|---|
| Records/giây | 2.500 | 2.650 | Tăng rất ít |
| JDBC connection pending | 0 | 14 | Chờ pool |
| DB lock wait p95 | 20 ms | 160 ms | Contention tăng |
| Chunk p95 | 0,8 giây | 2,4 giây | Tail latency xấu |

Đây là số liệu **giả định** để học cách chẩn đoán. Nhiều worker hơn chưa chắc làm batch nhanh hơn; việc giảm số worker hoặc chỉnh query/pool phù hợp có thể tốt hơn scale tiếp.

## 11. Kiểm tra metrics với lịch chạy và vòng đời pod

### 11.1. Job dài

Với job chạy hàng giờ, có thể scrape process metrics liên tục và quan sát trạng thái worker, heap, GC, JDBC, backlog. Nếu pod bị kill, cần giải thích vì sao metric runtime biến mất và dựa vào JobRepository để biết execution nào chưa kết thúc hoặc cần restart.

### 11.2. Job ngắn hoặc chạy theo lịch

Với job chạy 30 giây mỗi ngày, chỉ cấu hình scrape interval 60 giây có thể bỏ lỡ toàn bộ quá trình. Các lựa chọn:

- Có **scheduler/JobRepository collector** luôn chạy để phát số liệu last-start, last-success, failed execution và deadline.
- Nếu sử dụng cơ chế push metric, phải nắm rõ lifecycle, cleanup nhóm và stale series; push không thay thế sự thật từ JobRepository.
- Ghi nhận outcome vào một control store bền vững, có reconciliation và khả năng truy vấn lại sau khi process kết thúc.

**Đừng đặt mục tiêu giám sát mission-critical chỉ trên `Counter` trong JVM ngắn hạn.** Một lỗi trước khi metric được scrape có thể biến mất hoàn toàn.

### 11.3. Monitoring cũng cần SLO

Theo dõi `scrape_success`, exporter liveness, alert evaluation, khả năng gửi tới on-call, thời gian lag, khả năng đọc JobRepository và giá trị mới nhất. Thử thao tác tạm dừng collector trong staging để xác nhận **cảnh báo mất quan sát** hoạt động.

## 12. Runbook khi alert phát ra

### Pha A — Xác nhận tín hiệu và phạm vi ảnh hưởng

1. Xác định `job_name`, kỳ nghiệp vụ, release, môi trường, mã cảnh báo và lúc bắt đầu.
2. Xem status thật trong JobRepository, scheduler và control store; xác nhận có job bị bỏ lịch, trùng launch hoặc nhiều execution đang chạy không.
3. Phân biệt **ảnh hưởng dữ liệu** (missing/duplicate/mismatch) với **ảnh hưởng hiệu năng** (chậm/lag).
4. Thu thập log/traces theo correlation ID và khoảng thời gian, không sao chép PII thô ra ticket hoặc metric label.

Nếu có dấu hiệu sai dữ liệu, cân nhắc **tạm chặn publish/downstream** theo policy trước khi tăng retry hoặc scale worker. Nếu chỉ có throughput thấp, tìm bottleneck trước khi đổi concurrency.

### Pha B — Khoanh vùng theo kiến trúc

| Triệu chứng | Kiểm tra ưu tiên | Điều cần tránh |
|---|---|---|
| Không thấy job bắt đầu | Scheduler, lịch, lock/leader, JobLauncher, repository | Tạo `run.id` mới khi chưa biết job đã chạy chưa |
| Job `STARTED` quá lâu | Liveness, step/partition progress, deadlock, DB locks | Sửa tay `BATCH_JOB_EXECUTION.STATUS` |
| Retry tăng nhưng CPU thấp | JDBC pending, broker latency, external API limit | Tăng thread không giới hạn |
| Queue lag tăng, worker rảnh | Consumer group/listener, routing, auth, prefetch | Tin readiness probe đã chứng minh consumer hoạt động |
| Worker đã ghi nhưng manager thiếu reply | In-flight, unacked, reply correlation, DB output | Replay không có idempotency |
| Partition chậm nhất kéo dài | Skew, manifest, phân bố dữ liệu, SQL | Đổi partition name/range giữa restart |
| Reconciliation mismatch | Source snapshot, missing/extra keys, skip/duplicate, sink watermark | Công bố dữ liệu chỉ vì job `COMPLETED` |

### Pha C — Khôi phục có kiểm soát

Với lỗi tạm thời, áp dụng bounded retry/backoff, giảm concurrency hoặc điều chỉnh pool khi có bằng chứng. Với execution lỗi, dùng đường restart của Spring Batch khi `JobInstance` restartable và worker cũ đã dừng; giữ nguyên snapshot, partition manifest và khóa idempotency.

Với remote chunking hoặc partitioning, phải xác định message nào đã commit nhưng chưa ack, pending reply và trạng thái DLQ trước khi phát lại. Khi rollback release, kiểm tra tương thích `ExecutionContext`, JobRepository schema, serializer và dữ liệu do release mới đã ghi.

### Pha D — Điều kiện đóng incident

- Trạng thái job/step/partition đã hợp lệ và các phần việc chưa rõ đã được phân loại.
- Backlog/retry/DLQ trở lại mức chấp nhận hoặc có incident theo dõi riêng.
- Đã đối soát source snapshot và sink về count, business keys, giá trị và ngoại lệ được phê duyệt.
- Alert đã hồi phục **vì điều kiện tốt lên**, không phải do tắt rule hoặc mất exporter.
- Timeline, root cause, hành động và điều kiện phòng tái diễn được ghi lại.

## 13. Kiểm thử alert bằng fault injection

Đối với production checklist, **cấu hình alert chưa đủ**; phải chứng minh nó phát ra đúng, đến đúng nơi, và tự hồi phục đúng điều kiện. Kiểm thử nên thực hiện trên staging gần production hoặc một cohort được kiểm soát.

| Kịch bản thử | Hành động kích hoạt | Bằng chứng PASS |
|---|---|---|
| **Job không chạy** | Ngăn scheduler launch kỳ test | Cảnh báo deadline theo lịch kỳ vọng |
| **Job thất bại** | Gây lỗi có chủ đích trong reader/writer | Alert từ trạng thái persisted, mở được runbook |
| **Job mắc kẹt** | Giữ partition lâu hơn ngưỡng test | Alert running age/progress, không cần kill pod mới phát |
| **Worker crash sau commit** | Gây lỗi ở điểm giữa commit và ack/reply | Phát hiện redelivery, dữ liệu không bị ghi trùng |
| **Queue unacked** | Dừng consumer hoặc giữ message | Alert queue age, phân biệt với lag hợp lệ |
| **DLQ tăng** | Gửi message lỗi hợp đồng trên môi trường test | Cảnh báo có owner, mẫu lỗi được redaction |
| **DB pool cạn** | Giới hạn pool hoặc tạo contention có kiểm soát | Warning bám pool pending/latency và job slowdown |
| **Partition skew** | Một partition chứa phần lớn công việc | Dashboard hiển thị max/p95 duration và remaining work |
| **Data mismatch** | Tạo thiếu/thừa một business key | Alert reconciliation và chặn publish |
| **Collector mất kết nối** | Tạm dừng exporter test | Alert mất quan sát, không chuyển sang trạng thái khỏe |
| **Alert recovery** | Sửa nguyên nhân hoặc cho kỳ test đạt SLO | Alert trở về resolved và lưu lịch sử |
| **Notification path** | Kích hoạt rule test có kiểm soát | Đúng người nhận, đúng mức độ, không nhân bản quá nhiều |

Kiểm tra cả **false positive**: job không chạy vào ngày nghỉ theo lịch; worker đang drain hợp lệ khi rolling deployment; queue có backlog nhất thời dưới SLA; job đang chờ upstream theo điều kiện đã phê duyệt. Alert cần phân biệt chậm hợp lệ với thất bại phải can thiệp.

### 13.1. Bằng chứng nghiệm thu

Lưu cho mỗi alert quan trọng:

~~~text
Tên alert:
Metric và nguồn phát:
SLO / điều kiện firing:
Mức độ:
Owner / kênh nhận:
Runbook URL:
Kịch bản tạo lỗi:
Thời điểm bắt đầu lỗi:
Thời điểm alert firing:
Thời điểm người trực nhận được:
Thời điểm resolved:
Bằng chứng dữ liệu/JobRepository đã đúng:
Ngày diễn tập gần nhất và phiên bản cấu hình:
~~~

Đây là mẫu vận hành để nhóm tự điền, không phải một cấu trúc dữ liệu Spring Batch có sẵn. Đối với cảnh báo critical, cần chứng minh toàn bộ chuỗi **phát hiện → gửi → con người có thể phản ứng → phục hồi**.

## 14. Lỗi thiết kế metrics/alert thường gặp

**1. Chỉ có CPU/heap dashboard.** Không biết job bị bỏ lịch, stuck, sai dữ liệu hay không.

**2. Alert theo `COMPLETED` mà bỏ qua reconciliation.** Batch status không thay thế kiểm tra missing/extra/value mismatch của business sink.

**3. Dùng metric in-memory của pod ngắn hạn làm nguồn duy nhất.** Pod kết thúc giữa hai lần scrape có thể không để lại bằng chứng trên dashboard.

**4. Gắn `jobExecutionId`, `customerId` hoặc `transactionId` làm label.** Cardinality bùng nổ, có nguy cơ lộ dữ liệu liên kết cá nhân.

**5. Cộng `writeCount` qua mọi lần restart rồi coi là output unique.** Cùng business key có thể được thử lại; phải đối soát dữ liệu đích.

**6. Dùng queue depth = 0 để kết luận đã drain.** Broker vẫn có message unacked, reply pending hoặc worker đang ghi.

**7. Đặt alert `job duration > 1h` cho mọi loại job.** SLA và kích thước dữ liệu khác nhau, dẫn đến nhiễu và bỏ qua cảnh báo.

**8. Tăng worker khi alert latency nhưng không xem DB pool/locks.** Có thể làm contention nặng hơn.

**9. Không giám sát collector hoặc scrape target.** Mất quan sát dễ bị hiểu nhầm là toàn hệ thống khỏe.

**10. Có alert nhưng không có runbook, owner hoặc kiểm thử notification.** Khi sự cố thật xảy ra, nhóm không biết mức độ ảnh hưởng và hành động an toàn.

**11. Dùng cảnh báo trên từng partition như một page độc lập.** Một outage DB có thể tạo hàng trăm thông báo; cần nhóm cảnh báo theo nguyên nhân và job.

**12. Log toàn bộ chunk request hoặc exception chứa PII để “dễ quan sát”.** Dữ liệu cá nhân có thể lan sang log/APM/DLQ; sử dụng mã lỗi an toàn và correlation được phân quyền.

## 15. Tình huống thực tế: cảnh báo khi tăng worker

Một hệ thống settlement chạy remote partitioning, xử lý **10 triệu giao dịch** mỗi đêm. Job được chia thành 80 partition, green release tăng worker từ 8 lên 24 để rút ngắn thời gian.

Sau rollout, dashboard ghi nhận các tín hiệu minh họa:

| Chỉ số | Trước rollout | Sau rollout |
|---|---:|---:|
| Worker active | 8 | 24 |
| Throughput | 3.200 record/giây | 3.350 record/giây |
| JDBC pending connections p95 | 0 | 16 |
| Chunk p95 duration | 1,1 giây | 3,8 giây |
| Retry do DB timeout / 15 phút | 2 | 145 |
| Failed partitions | 0 | 7 |
| Missing business keys | 0 | Chưa đối soát xong |

Số liệu trên chỉ để minh họa phương pháp suy luận. Đội vận hành thấy throughput gần như không cải thiện, trong khi JDBC pool và DB trở thành nút thắt. Các bước xử lý:

1. Không tăng worker tiếp; giữ snapshot và định danh execution để tìm đủ phạm vi ảnh hưởng.
2. Tạm ngừng dispatch mới hoặc giảm concurrency theo cơ chế manager, chờ xử lý in-flight phù hợp.
3. Kiểm tra pool size, query plan, lock wait và retry policy; tránh tạo retry storm.
4. Kiểm tra 7 partition lỗi có thể restart an toàn, worker cũ đã dừng và writer idempotent.
5. Chạy lại phần lỗi theo metadata/manifest, sau đó đối soát đủ 10 triệu input với kết quả.
6. Đánh giá rollout dựa trên **thời gian hoàn thành dữ liệu đã reconciled** thay vì chỉ đếm số pod.

Nếu chỉ có metric CPU, sự cố có thể bị diễn giải sai là “worker còn rảnh, cần scale tiếp”. Bộ metrics đúng giúp chỉ ra **nút thắt nằm ở DB**, còn alert đúng giúp người trực chặn rủi ro mất deadline và sai dữ liệu.

## 16. Checklist nghiệm thu production

### A. Tín hiệu và nguồn dữ liệu

- [ ] Đã định nghĩa lịch chạy, deadline, loại workload, tiêu chí thành công và SLO theo từng job quan trọng.
- [ ] Có số liệu scheduler, lần start/success gần nhất, thất bại và job mắc kẹt từ nguồn bền vững.
- [ ] `JobExecution`/`StepExecution` status, duration, read/write/filter/skip/rollback được kiểm tra trên phiên bản đang triển khai.
- [ ] Có metric theo mô hình scaling: executor queue/thread, partition progress/skew, remote worker, broker unacked/DLQ/pending reply.
- [ ] Có chỉ số CPU/heap/GC, connection pool, DB wait và downstream timeout để xác định nút thắt.
- [ ] Có reconciliation theo snapshot/business key và trạng thái `MATCHED/MISMATCH/INCONCLUSIVE` do ứng dụng định nghĩa.

### B. Pipeline quan sát

- [ ] Actuator/Micrometer/exporter được cấu hình, có scrape target thành công và policy bảo vệ endpoint.
- [ ] Với job ngắn, có collector/controller bền vững dựa trên JobRepository và lịch chạy.
- [ ] Đã thử metric missing, collector down, stale series và mất target discovery.
- [ ] Metric name, unit, label/retention và owner được thống nhất; không có PII hoặc ID cardinality cao trong label.
- [ ] Dashboard có thể mở đúng release/job, drill-down tới logs/traces/metadata theo quyền phù hợp.

### C. Alert và phản ứng

- [ ] Có alert cho missed deadline, execution lỗi, stuck/no progress và dữ liệu chưa đối soát.
- [ ] Có warning cho backlog/message age, redelivery/DLQ, retry tăng, DB pool wait và resource saturation.
- [ ] Ngưỡng được lấy từ workload, lịch chạy và SLO; không sao chép con số mặc định thiếu kiểm chứng.
- [ ] Alert có severity, owner, kênh nhận, runbook URL, điều kiện firing/resolved và chính sách grouping/inhibition.
- [ ] Có cảnh báo khi mất observability; không coi mất series là trạng thái bình thường.
- [ ] Đã thử fault injection, notification path, false positive và recovery; lưu bằng chứng nghiệm thu.

### D. Bảo đảm dữ liệu và khả năng phục hồi

- [ ] Writer có idempotency hoặc cơ chế khôi phục an toàn khi retry/redelivery.
- [ ] Restart dựa trên metadata và checkpoint tương thích; không tự tạo `JobInstance` mới để “chạy lại”.
- [ ] Có runbook fencing, drain, xử lý pending reply/DLQ và rollback release khi cần.
- [ ] Có quy trình dừng publish nếu output mismatch hoặc chưa đủ dữ liệu để kết luận.
- [ ] Có người trực xác nhận data correctness trước khi đóng sự cố liên quan dữ liệu.

**Điều kiện go/no-go:** nếu không phát hiện được job trễ, không có bằng chứng alert đến người trực, hoặc không có cách xác nhận dữ liệu output đúng, mục checklist **“Đã thiết lập metrics và alert” chưa đạt** dù dashboard đã tồn tại.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một Spring Batch job có `/actuator/prometheus` vẫn có thể bị bỏ lịch mà không ai biết?

*Gợi ý:* Job chưa chạy sẽ không phát metric runtime; pod ngắn hạn có thể kết thúc trước scrape. Cần collector bền vững đọc scheduler và JobRepository.

**Câu 2.** Worker tăng từ 4 lên 16, throughput không tăng nhưng JDBC pending tăng mạnh. Nên alert điều gì?

*Gợi ý:* Pool wait, DB lock/timeout, chunk latency và throughput/SLO. Trước khi scale thêm, cần xác định DB contention.

**Câu 3.** Có thể dùng `writeCount=1000000` làm bằng chứng đích có đúng 1 triệu khóa duy nhất không?

*Gợi ý:* Không. Retry, restart và side effect ngoài transaction có thể làm thống kê khác business sink; cần đối soát theo key/value.

**Câu 4.** Tại sao không đưa `jobExecutionId` làm Prometheus label để dễ tìm lỗi?

*Gợi ý:* Cardinality tăng theo mỗi lần chạy, gây chi phí và rối truy vấn. Dùng nhãn job/release/outcome trên metric; dùng ID trong logs/tracing/JobRepository viewer.

**Câu 5.** Metric biến mất khi exporter chết, nhưng dashboard không còn hiện đường đỏ. Hệ thống đã khỏe chưa?

*Gợi ý:* Không. Cần alert mất quan sát: target không scrape được, series absent/stale, exporter không lấy được metadata.

**Câu 6.** Job báo `COMPLETED` nhưng reconciliation phát hiện 2 giao dịch thiếu. Alert nào cần ưu tiên?

*Gợi ý:* Cảnh báo data mismatch là trọng yếu; chặn publish/đóng sổ theo policy, điều tra snapshot, writer và retry, sửa có kiểm soát rồi đối soát lại.

## Kết luận

Metrics và alert chỉ thực sự sẵn sàng production khi hệ thống đo được **lịch chạy, trạng thái thực thi, tiến độ, nút thắt tài nguyên và tính đúng đắn của kết quả**, đồng thời biến các số liệu đó thành **cảnh báo có người xử lý và quy trình khôi phục đã diễn tập**. Với Spring Batch mở rộng qua nhiều thread, partition hoặc worker, hãy dùng Micrometer/Actuator để quan sát runtime, đọc JobRepository và scheduler qua nguồn bền vững để phát hiện job bị bỏ lỡ, theo dõi broker/DB để tìm nghẽn, và đối soát dữ liệu để chứng minh kết quả. Mục `“Đã thiết lập metrics và alert”` chỉ nên được đánh dấu đạt sau khi các kịch bản lỗi, thông báo và phục hồi đều có bằng chứng kiểm thử.
