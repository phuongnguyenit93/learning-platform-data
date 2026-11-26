# Job duration và step duration trong Spring Batch

Trong Spring Batch, một job xử lý khối lượng dữ liệu lớn có thể chậm vì truy vấn database, ghi qua mạng, chờ kết nối, retry hoặc phân phối công việc không đều giữa các worker. **`Job duration`** cho biết toàn bộ một lần thực thi job mất bao lâu; **`step duration`** giúp khoanh vùng phần việc nào tiêu tốn thời gian. Đây là hai chỉ số thời gian nền tảng khi đánh giá hiệu quả **multi-threaded step**, **parallel steps**, **partitioning** và xử lý phân tán trong module `SPRING_BATCH_SCALING_OPERATIONS`.

Không nên kết luận rằng nhiều thread hơn luôn khiến job nhanh hơn. Ta phải đo thời gian thực tế, nhận biết các phần chạy đồng thời, xác định nút thắt và so sánh trên khối lượng dữ liệu tương đương.

## 1. Định nghĩa và đơn vị đo

Một lần chạy job trong Spring Batch được biểu diễn bằng `JobExecution`; mỗi lần chạy step được biểu diễn bằng `StepExecution`. Các đối tượng này có thông tin thời điểm bắt đầu, kết thúc, trạng thái và các bộ đếm xử lý.

| Chỉ số | Phạm vi | Công thức khi đã kết thúc | Ý nghĩa |
| --- | --- | --- | --- |
| **Job duration** | Một `JobExecution` | `jobEndTime - jobStartTime` | Thời gian thực trôi qua từ lúc job bắt đầu chạy đến lúc kết thúc |
| **Step duration** | Một `StepExecution` | `stepEndTime - stepStartTime` | Thời gian thực trôi qua trong một lần thực thi step |
| **Worker/partition duration** | Một worker `StepExecution` | `workerEndTime - workerStartTime` | Phân vùng cụ thể đã mất bao lâu |
| **Job end-to-end latency** | Từ khi yêu cầu chạy được tiếp nhận đến khi có kết quả | `resultTime - requestedTime` | Có thể bao gồm thời gian chờ scheduler, message queue và khởi động ứng dụng |
| **Throughput** | Job hoặc step trong khoảng đo | `số bản ghi hoàn tất / số giây` | Khối lượng công việc trên một đơn vị thời gian |

`Job duration` và `step duration` là **wall-clock time** (*thời gian thực trôi qua*), không phải CPU time. Nếu worker chờ JDBC connection 20 giây, ngủ 5 giây do backoff và xử lý CPU 3 giây, duration có thể gần 28 giây dù CPU chỉ sử dụng khoảng 3 giây. Chính sự khác biệt này giúp phát hiện nút thắt ngoài CPU.

Nên thống nhất đơn vị khi hiển thị: giây cho số liệu kỹ thuật, phút cho dashboard vận hành. Ví dụ, `75000 ms = 75 s = 1 phút 15 giây`. Khi báo cáo nhiều lần chạy, dùng p50, p95 hoặc p99 theo cửa sổ thời gian; một giá trị trung bình đơn lẻ dễ che giấu các lần chạy rất chậm.

### Không nhầm `JobInstance` và `JobExecution`

- **`JobInstance`** định danh một lần xử lý logic theo tên job và bộ *identifying job parameters*.
- **`JobExecution`** là một lần thử chạy của `JobInstance`. Một `JobInstance` có thể có nhiều `JobExecution` nếu job thất bại rồi được restart.
- **`StepExecution`** thuộc về một `JobExecution`. Step có thể chạy lại khi restart; mỗi lần chạy là một execution khác.

Ví dụ: job xử lý dữ liệu ngày 20/11 thất bại sau 4 phút, sau đó restart thành công sau 3 phút. Đây có thể là **hai job duration riêng: 4 phút và 3 phút**, không phải một lần chạy 7 phút. Nếu nghiệp vụ muốn đo *thời gian hoàn thành từ lần chạy đầu đến khi cuối cùng thành công*, cần định nghĩa thêm một metric ở cấp `JobInstance` hoặc quy trình xử lý; không dùng nhầm duration của lần `JobExecution` cuối.

## 2. Cách hiểu duration khi có nhiều step

### Job chạy tuần tự

Với các step tuần tự `extract -> transform -> load`, ta có:

```text
JobExecution:          |----------------------------- 110 s -----------------------------|
extract:               |---- 30 s ----|
transform:                             |----------- 55 s -----------|
load:                                                                |--- 20 s ---|
overhead / chuyển bước: tổng khoảng 5 s
```

Thời gian job thường **xấp xỉ** tổng duration các step tuần tự cộng overhead (khởi tạo, chuyển step, cập nhật metadata, listener...). Không mặc định bằng nhau tuyệt đối. Hơn nữa, `startTime` của job không phải thời điểm yêu cầu được đưa vào hàng đợi; muốn đo từ lúc nhận yêu cầu phải thu thập thời điểm đó riêng.

### Parallel steps: không cộng tất cả step duration

Giả sử job có `extract` 30 giây, hai step `transform-A` và `transform-B` chạy đồng thời trong 70 và 55 giây, rồi `publish` 12 giây. Thêm tổng cộng 8 giây overhead/chờ giữa các giai đoạn:

```text
Trục thời gian:  0         30                    100      108     120 (giây)
Job             |--------------------------------------------------------|
extract         |--- 30s --|
transform-A                |---------- 70s ----------|
transform-B                |------- 55s ------|
publish                                                   |-- 12s --|
```

Tổng `step duration = 30 + 70 + 55 + 12 = 167 giây`, trong khi **job duration chỉ là 120 giây**. Hai step transform chồng lên nhau, nên cộng các duration sẽ tính trùng thời gian. Đường thực thi chi phối thời điểm hoàn thành (*critical path*) đi qua `transform-A` dài hơn. Tăng tốc `transform-B` khi nó đã kết thúc sớm hơn A thường không làm job kết thúc sớm hơn.

### Partitioned step: manager và worker có khoảng thời gian lồng nhau

Một manager step giao ba partition cho worker. Giả sử các worker chạy cùng lúc:

| Thành phần | Duration | Ghi chú |
| --- | ---: | --- |
| Worker `partition-000` | 90 s | Partition chậm nhất |
| Worker `partition-001` | 45 s | Hoàn tất trước |
| Worker `partition-002` | 30 s | Hoàn tất trước |
| Manager step | 100 s | Bao gồm điều phối, chờ và thu thập kết quả |
| Toàn job | 104 s | Bao gồm thời gian ngoài manager step |

Tổng duration của ba worker là **165 giây**, nhưng manager chỉ mất 100 giây vì worker chạy chồng thời gian lên nhau. **Không cộng duration của manager với duration của các worker:** manager đang chờ các worker và các khoảng này lồng nhau. Thay vào đó, xem riêng thời gian manager, phân bố duration giữa các worker và thời gian chờ điều phối.

`gridSize` chỉ là số partition mục tiêu/được đề xuất. Nếu có 20 partition nhưng pool chỉ chạy 4 worker đồng thời thì thời gian manager còn bao gồm các đợt worker tiếp theo phải chờ. Với remote partitioning, thêm thời gian truyền message, chờ worker nhận việc, xử lý và trả kết quả. Không suy ra mức song song từ số partition được tạo.

## 3. Đo duration từ metadata của Spring Batch

`JobRepository` lưu thông tin execution; `JobExplorer` hỗ trợ truy xuất metadata để kiểm tra các lần chạy. Với một execution **đã kết thúc**, có thể lấy thời gian bắt đầu và kết thúc từ `JobExecution`/`StepExecution`.

Ví dụ dưới đây dùng API thời gian của **Spring Batch 5.x** (`LocalDateTime`):

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;

public final class BatchDurationReader {
    private BatchDurationReader() {}

    public static Optional<Duration> jobDuration(JobExecution execution) {
        return elapsed(execution.getStartTime(), execution.getEndTime());
    }

    public static Optional<Duration> stepDuration(StepExecution execution) {
        return elapsed(execution.getStartTime(), execution.getEndTime());
    }

    private static Optional<Duration> elapsed(
            LocalDateTime start, LocalDateTime end) {
        if (start == null || end == null || end.isBefore(start)) {
            return Optional.empty();
        }
        return Optional.of(Duration.between(start, end));
    }
}
```

Một job/step đang chạy thường **chưa có `endTime`**. Không biến trường hợp này thành duration bằng `0` vì sẽ làm sai thống kê; dùng đồng hồ quan trắc cho *in-flight elapsed time* hoặc lấy `now - startTime` khi hiển thị tình trạng hiện tại. Để đo thời gian chính xác xuyên qua thay đổi múi giờ hoặc chỉnh đồng hồ, nên dùng timer/đồng hồ đơn điệu của hệ thống giám sát; phép trừ `LocalDateTime` trong metadata hữu ích để đối chiếu các execution đã ghi, với điều kiện thời gian lưu được quản lý nhất quán.

Trong Spring Batch 4.x, một số API thời gian dùng kiểu `Date`; ví dụ trên cần điều chỉnh tương ứng. Không mặc định một đoạn mã đúng cho mọi dòng phiên bản.

### Truy vấn metadata để điều tra các lần chạy

Spring Batch thường có các bảng metadata `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION`. Ví dụ SQL **PostgreSQL** sau tìm thời gian của những lần chạy đã kết thúc:

```sql
SELECT
    ji.JOB_NAME,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.START_TIME,
    je.END_TIME,
    EXTRACT(EPOCH FROM (je.END_TIME - je.START_TIME)) AS duration_seconds
FROM BATCH_JOB_EXECUTION AS je
JOIN BATCH_JOB_INSTANCE AS ji
    ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.START_TIME IS NOT NULL
  AND je.END_TIME IS NOT NULL
ORDER BY je.START_TIME DESC;
```

Tương tự, tra cứu step theo từng `JobExecution`:

```sql
SELECT
    se.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    EXTRACT(EPOCH FROM (se.END_TIME - se.START_TIME)) AS duration_seconds
FROM BATCH_STEP_EXECUTION AS se
WHERE se.JOB_EXECUTION_ID = :jobExecutionId
  AND se.START_TIME IS NOT NULL
  AND se.END_TIME IS NOT NULL
ORDER BY se.START_TIME, se.STEP_EXECUTION_ID;
```

`:jobExecutionId` là tham số bind của ứng dụng/trình truy vấn, không phải cú pháp biến bắt buộc của PostgreSQL. Với database khác, đổi biểu thức tính chênh lệch thời gian theo dialect tương ứng. Trong hệ thống chạy lâu dài, ưu tiên phân trang/lọc theo khoảng thời gian và index phù hợp thay vì liên tục quét toàn bộ metadata.

**Chú ý trạng thái:** một execution `FAILED` có duration hợp lệ nhưng chưa hoàn thành nghiệp vụ. Đừng gộp các job thất bại rất nhanh với các job `COMPLETED` khi đánh giá SLA thời gian hoàn tất thành công. Nên hiển thị riêng duration theo `BatchStatus` và tỷ lệ thành công.

## 4. Thu thập duration qua Micrometer và Spring Boot Actuator

Metadata trong `JobRepository` phù hợp điều tra một lần chạy. Để nhìn xu hướng nhiều ngày, nhiều phiên bản ứng dụng hoặc nhiều worker, có thể dùng **Micrometer**, **Spring Boot Actuator** và hệ thống metrics như Prometheus/Grafana. Trong các phiên bản Spring Batch có tích hợp Micrometer, các timer liên quan thường mang tên **`spring.batch.job`** và **`spring.batch.step`** ở tầng Micrometer; cách hiển thị/export tên metric và các tag phụ thuộc phiên bản Spring Batch, Micrometer và registry đang dùng.

Ví dụ khai báo các dependency trong ứng dụng Spring Boot (cú pháp Gradle):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Cho phép các endpoint dùng để kiểm tra và thu thập metrics:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Đây là cấu hình tối thiểu mang tính minh họa. Cần bảo vệ endpoint bằng cấu hình mạng/xác thực tương ứng môi trường triển khai. Tùy phiên bản, metrics chỉ xuất hiện sau khi job/step được đo và hệ thống metrics đã được đăng ký; hãy xem danh sách tại `/actuator/metrics`, kiểm tra `/actuator/metrics/spring.batch.job` hoặc dữ liệu thực tại `/actuator/prometheus` trước khi viết truy vấn dashboard. Không giả định mọi phiên bản tự sinh cùng tên tag hoặc cùng các loại histogram.

### Timer khác gì đồng hồ theo dõi job đang chạy?

- **Timer cho các execution kết thúc**: cung cấp số lần đo (`count`), tổng thời gian (`totalTime`/`sum`) và thường có `max` theo chính sách registry. Có thể dùng để tính trung bình theo cửa sổ thời gian.
- **Long task timer hoặc gauge cho execution đang chạy**: cho biết có bao nhiêu job/step đang hoạt động và chúng đã chạy bao lâu, giúp phát hiện job treo trước khi nó kết thúc.
- **Histogram / percentile**: phục vụ câu hỏi “95% các job thành công kết thúc trong bao lâu?”. Histogram có thể cần bật riêng; không thấy chuỗi `_bucket` không có nghĩa là không có timer.

Ví dụ dạng truy vấn PromQL, **chỉ khi exporter thực tế phát metric** `spring_batch_job_seconds_bucket` và đã cấu hình histogram:

```promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(spring_batch_job_seconds_bucket[1h])
  )
)
```

Truy vấn mẫu này gộp tất cả job/status trong dữ liệu đầu vào. Trong dashboard thực tế, **lọc đúng job và trạng thái thành công** theo các label thực sự được exporter cung cấp, sau đó mới tính percentile. Không dùng nó nguyên xi để báo cáo SLA của một job cụ thể khi hệ thống có nhiều loại job với kích thước khác nhau. Với job chỉ chạy vài lần mỗi ngày, một cửa sổ một giờ có thể quá ít mẫu để p95 có ý nghĩa; dùng cửa sổ dài hơn hoặc hiển thị duration từng lần chạy.

### Đặt tag sao cho metric sử dụng được

Những tag thường có ích là tên job/step ở **mức nhóm ổn định**, trạng thái (`COMPLETED`, `FAILED`...) và môi trường triển khai. Hạn chế biến `jobExecutionId`, partition name động, `orderId`, tên file, tenant ID hoặc exception message thành tag của timer tổng hợp vì tạo **cardinality cao** và tốn tài nguyên hệ thống giám sát.

Để điều tra một partition riêng lẻ, lưu `jobExecutionId`, `stepExecutionId`, `stepName`, phạm vi partition và duration vào log có cấu trúc hoặc báo cáo truy vấn từ `JobRepository`. Nếu cần dashboard chi tiết theo partition, thiết kế nhóm tên ổn định hoặc chỉ mở độ chi tiết trong khoảng thời gian điều tra thay vì ghi một time series mới cho mọi execution.

## 5. Dùng duration để xác định nút thắt

Một duration lớn chỉ nói “mất nhiều thời gian”; phải so sánh với lượng dữ liệu và các tín hiệu tài nguyên để biết **vì sao**.

| Hiện tượng | Giả thuyết cần kiểm tra | Dữ liệu nên đo thêm |
| --- | --- | --- |
| Job duration tăng, step đọc chậm | Database scan, thiếu index, query plan đổi, nguồn quá tải | Query latency, I/O, DB CPU, rows/sec |
| Step xử lý lâu, CPU cao | Xử lý CPU-bound hoặc GC | CPU utilization, GC pause, heap, throughput |
| Writer lâu, rollback nhiều | Lock contention, transaction lớn, deadlock, hệ thống đích chậm | Commit/rollback count, lock wait, pool wait |
| Step duration tăng chủ yếu khi lỗi tạm thời | Retry/backoff làm tăng thời gian chờ | Số retry, loại lỗi, backoff time, HTTP 429/503 |
| Một worker partition kéo dài hơn phần còn lại | Chia dữ liệu không đều, partition có bản ghi “nặng” | Duration + item count/bytes mỗi partition |
| Worker đều ngắn nhưng manager job lâu | Chờ lịch, chờ thread, giới hạn pool, message queue/handshake | Queue wait, active thread, queue depth, pool utilization |
| Tăng số worker nhưng job không nhanh hơn | Bottleneck chuyển sang DB/API/network hoặc tranh chấp | Concurrency, CPU, DB throughput, connection/lock wait |

Đặc biệt với partitioning, nên xem **max worker duration**, p50/p95 worker duration, số bản ghi trên mỗi partition và khoảng thời gian manager chờ. Trong ví dụ trước, tăng tốc worker 30 giây không cải thiện mốc hoàn thành nếu worker 90 giây vẫn là phần chậm nhất.

### Duration cần đặt cạnh throughput

Giả sử hai ngày có số liệu:

| Ngày | Bản ghi đã xử lý | Job duration | Throughput xấp xỉ |
| --- | ---: | ---: | ---: |
| A | 1.000.000 | 10 phút | 1.667 bản ghi/giây |
| B | 3.000.000 | 20 phút | 2.500 bản ghi/giây |

Ngày B có duration dài hơn, nhưng throughput tốt hơn khoảng 50%. Không kết luận hệ thống xuống cấp khi khối lượng công việc đã tăng gấp ba. Khi so sánh các lần chạy, còn phải xét độ phức tạp mỗi bản ghi, kích thước file, số lần retry và tải của hệ thống đích. Nếu workload không đồng nhất, có thể dùng số byte, số item được chuẩn hóa theo loại hoặc các nhóm dữ liệu có chi phí tương tự.

### Tốc độ tăng khi mở rộng không phải tuyến tính

Gọi `T(1)` là duration với một worker và `T(N)` là duration với `N` worker hoạt động đồng thời trên **cùng workload**:

```text
Speedup(N)    = T(1) / T(N)
Efficiency(N) = Speedup(N) / N
```

Ví dụ `T(1) = 40 phút`, `T(4) = 15 phút` thì `speedup = 40 / 15 ≈ 2,67 lần`, `efficiency ≈ 66,7%`. Phần thời gian tuần tự, việc điều phối, truy cập tài nguyên chung và lệch tải giữa các partition khiến speedup thấp hơn số worker. Đây là lý do cần đo cả job duration và step/partition duration khi tinh chỉnh `gridSize`, thread pool và số worker từ xa.

## 6. Dashboard và cảnh báo vận hành

Dashboard phục vụ job dữ liệu lớn nên trả lời nhanh ba câu hỏi: **Job có hoàn thành đúng hạn không? Step nào đang kéo dài? Có dấu hiệu nghẽn tài nguyên hoặc thử lại quá nhiều không?**

| Nhóm hiển thị | Metric/biểu đồ đề xuất | Cách sử dụng |
| --- | --- | --- |
| Tổng quan job | Duration từng lần chạy, p50/p95 theo job và trạng thái | Theo dõi SLA, xu hướng chậm dần |
| Tính sẵn sàng | Số job chạy, `FAILED`, `STOPPED`, tỷ lệ hoàn thành | Tránh tình trạng job fail nhanh làm trung bình duration thấp đi |
| Phân tích step | Top step duration theo lần chạy; step read/write count | Xác định giai đoạn chiếm thời gian |
| Partitioning | Phân bố worker duration, max/min và item count/worker | Phát hiện worker kéo dài, phân phối dữ liệu lệch |
| Hạ tầng | CPU, RAM, GC, connection pool, DB wait, message queue | Phân biệt giới hạn tài nguyên với vấn đề thiết kế job |
| Phục hồi | Retry count, rollback count, restart count, backlog | Phát hiện lỗi tạm thời/đứt gãy trước khi ảnh hưởng SLA |

Một ngưỡng cảnh báo nên gắn với nhu cầu thực tế. Ví dụ, nếu job báo cáo sáng phải **hoàn thành trước 07:00**, chỉ cảnh báo `job duration > 20 phút` có thể bỏ sót trường hợp job bắt đầu muộn. Nên kết hợp deadline tuyệt đối, trạng thái hoàn thành và elapsed time của job đang chạy. Với job chạy lâu, cảnh báo khi duration đang chạy vượt **thời gian dự kiến có điều kiện theo khối lượng dữ liệu**; đừng chờ đến khi timer của lần chạy đã kết thúc mới phát hiện sự cố.

Để xác định nguyên nhân, một log hữu ích có thể chứa:

```text
job=nightlyOrders jobExecutionId=812 step=workerStep:partition-007
status=COMPLETED start=2026-11-26T01:00:00 end=2026-11-26T01:03:45
durationMs=225000 readCount=45000 writeCount=45000 rollbackCount=3
```

Các giá trị chỉ minh họa. Trong môi trường phân tán, đồng bộ thời gian giữa các máy, chuẩn hóa timezone trong log và thêm correlation ID để so sánh lịch sử manager/worker. Chỉ đưa định danh dữ liệu hoặc log chi tiết vào nơi được cấp quyền phù hợp.

## 7. Những sai lầm hay gặp khi đọc duration

1. **Cộng mọi step duration rồi so với job duration:** sai khi các step chạy song song hoặc manager chứa thời gian worker. Cần xem critical path và các đoạn chồng nhau.
2. **Cộng duration của manager với partition worker:** bị đếm kép. Dùng manager duration để theo dõi tổng phân phối và từng worker duration để phát hiện skew.
3. **Chỉ đo execution thành công:** bỏ lỡ thời gian thất bại/retry và số job bị treo. Phân tách `COMPLETED`/`FAILED`/`STOPPED` và active executions.
4. **Gán `duration = 0` cho job đang chạy:** làm trung bình sai và che mất job đang chờ vô hạn. In-flight job cần một phép đo elapsed hiện tại riêng.
5. **Nhầm duration một lần restart với tổng thời gian giải quyết công việc:** nhiều `JobExecution` có thể thuộc một `JobInstance`.
6. **So sánh duration mà không kiểm soát kích thước workload:** khó phân biệt chậm do nhiều bản ghi với giảm năng suất xử lý.
7. **Chỉ nhìn duration mà không theo dõi rollback, retry, pool wait và độ dài hàng đợi:** có thể xử lý nhầm nguyên nhân. Thêm worker khi database đã nghẽn đôi khi làm job chậm hơn.
8. **Gắn ID động lên mọi metric:** dễ làm tăng cardinality, giảm hiệu quả lưu trữ và truy vấn. Dùng log/metadata cho điều tra từng execution.

## 8. Bài tập phân tích duration

Một job chạy bốn worker partition với số liệu sau:

| Partition | Bản ghi | Worker duration |
| --- | ---: | ---: |
| P0 | 100.000 | 50 s |
| P1 | 100.000 | 55 s |
| P2 | 100.000 | 52 s |
| P3 | 100.000 | 140 s |

Manager step mất 150 giây; cả job mất 155 giây. Hãy trả lời:

- Có thể lấy `50 + 55 + 52 + 140` để nói job mất 297 giây không?
- Partition nào đang quyết định thời điểm hoàn tất?
- Nên tăng số worker ngay, hay điều tra đặc điểm dữ liệu, truy vấn và retry ở P3 trước?

**Gợi ý lời giải:** 297 giây là tổng duration worker nên có chồng lấn, không phải job duration. P3 kéo dài 140 giây khiến các worker khác chờ kết quả; cần xem số byte thực, loại bản ghi, retry/rollback, query plan và tranh chấp tại P3 trước khi tăng concurrency. Việc tăng từ 4 lên 8 worker không đảm bảo giảm duration nếu P3 tiếp tục xử lý một partition lớn/chậm mà không được chia lại.

## 9. Checklist trước khi kết luận cải thiện hiệu năng

- Xác nhận mọi phép so sánh dùng cùng **định nghĩa duration**, cùng phiên bản/cấu hình phù hợp và workload tương đương.
- Phân biệt duration của **một `JobExecution`**, nhiều lần restart và end-to-end latency theo lịch nghiệp vụ.
- Đọc duration theo `BatchStatus`, cả job đã hoàn thành và đang chạy.
- Với parallel steps/partitioning, xác định **critical path**, worker chậm nhất và thời gian chờ manager.
- Đặt duration cạnh read/write counts, throughput, rollback/retry, CPU, I/O, DB locks và connection pool.
- Đo lại sau khi đổi `gridSize`, thread pool hoặc chiến lược chia dữ liệu; xác nhận speedup và chi phí tài nguyên cùng thay đổi.
- Kiểm tra tên metric và tag trên hệ thống thực tế trước khi tạo biểu đồ/alert; lưu chi tiết từng execution trong metadata và log.

> **Ghi nhớ:** `Job duration` trả lời **“một lần chạy job hoàn thành trong bao lâu?”**; `step duration` trả lời **“phần nào đang mất thời gian?”**. Trong hệ thống Spring Batch mở rộng bằng chạy song song và partitioning, hãy phân tích duration theo *đường thực thi quyết định thời điểm hoàn thành*, kết hợp throughput và metric tài nguyên để chọn kiến trúc, mức đồng thời và chiến lược tối ưu phù hợp.
