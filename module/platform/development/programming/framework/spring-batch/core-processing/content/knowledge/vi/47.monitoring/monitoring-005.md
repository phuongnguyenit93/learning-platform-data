# Theo dõi step duration trong Spring Batch

## 1. Step duration là gì và vì sao cần theo dõi?

Trong Spring Batch, mỗi **step** là một đơn vị xử lý có trạng thái, thống kê và lịch sử thực thi riêng. **Step duration** là khoảng thời gian một `StepExecution` tiêu tốn từ khi bắt đầu đến khi kết thúc. Đây là một chỉ số nền tảng để nhận biết việc nhập dữ liệu chậm bất thường, kiểm tra hiệu quả tối ưu hóa và dự đoán khi nào job sẽ hoàn tất.

Ví dụ, job `dailyImport` gồm ba step:

```text
dailyImport
  |
  +-- downloadFile       00:00:18
  |
  +-- validateRows       00:01:42
  |
  +-- writeToDatabase    00:12:30
                         --------
  Tổng thời gian từng step: 00:14:30
```

Nếu các step chạy tuần tự và không có thời gian chờ đáng kể giữa chúng, tổng duration gần với thời gian chạy job. Nhưng với **parallel steps, partitioning, remote processing** hoặc thời gian chờ giữa hai step, cộng duration của tất cả step không nhất thiết bằng tổng thời gian job.

Khi `writeToDatabase` tăng từ 12 phút lên 50 phút, chỉ nhìn `JobExecution=COMPLETED` có thể khiến người vận hành bỏ qua vấn đề. Duration giúp trả lời: step nào tăng thời gian, tăng bao nhiêu, do khối lượng dữ liệu lớn hơn hay do tốc độ xử lý giảm?

### Mục tiêu của bài

Sau bài học, bạn có thể:

- Đọc `startTime`, `endTime` và `BatchStatus` từ `StepExecution` để tính thời lượng của **một lần chạy step**.
- Hiểu ý nghĩa của Micrometer Timer và LongTaskTimer trong Spring Batch.
- Phân biệt step đã kết thúc với step vẫn đang chạy, cũng như step retry/restart và step chạy song song.
- Thiết kế dashboard/alert theo thời lượng, số lượng bản ghi và throughput.
- Viết test ổn định cho mã tính duration mà không cần `Thread.sleep(...)`.
- Truy vết step chậm bằng `JobExplorer`, `JobRepository`, metric và log.

**Phiên bản áp dụng trong ví dụ:** Spring Batch 5.2.x, Spring Boot 3.x, Java 17+ và Micrometer. Các phiên bản Spring Batch 6.x có thay đổi về package/API, nên cần đối chiếu chữ ký theo phiên bản thực tế của dự án.

## 2. Phân biệt các loại thời gian trong batch

Từ “thời gian chạy” có thể chỉ nhiều thứ khác nhau.

| Chỉ số | Khoảng đo | Dùng để trả lời |
|---|---|---|
| **Job duration** | Từ lúc `JobExecution` bắt đầu đến khi kết thúc | Toàn bộ lượt chạy job mất bao lâu? |
| **Step duration** | Từ `StepExecution.startTime` đến `endTime` | Step cụ thể mất bao lâu? |
| **Active step duration** | Từ lúc step bắt đầu đến thời điểm hiện tại | Step còn chạy đã kéo dài bao lâu? |
| **Chunk duration** | Xử lý một đơn vị chunk | Có phải transaction/chunk đang chậm? |
| **Item read duration** | Lời gọi reader | Đọc từ DB/API/file có chậm không? |
| **Item process duration** | Lời gọi processor | Logic biến đổi có tốn CPU hoặc gọi dịch vụ ngoài lâu không? |
| **Chunk write duration** | Lời gọi writer | Ghi database/file/broker có chậm không? |
| **Scheduler delay** | Từ lúc lịch dự kiến đến lúc job thực sự bắt đầu | Job bị trễ lịch vì queue, khóa hay tài nguyên? |

**Không đồng nhất step duration với tổng thời gian xử lý từng item.** Step có thể mất thời gian để khởi tạo tài nguyên, mở/đóng reader, quản lý transaction, ghi checkpoint, retry/backoff hoặc chờ I/O.

Ví dụ:

```text
StepExecution importOrders
startTime = 01:00:00
endTime   = 01:05:00
duration  = 5 phút

Trong 5 phút:
  item read       40 giây
  item process    60 giây
  chunk write    140 giây
  transaction     35 giây
  mở/đóng I/O      5 giây
  xử lý khác      20 giây
```

Phân rã minh họa này không phải công thức mà Spring Batch bảo đảm cộng khớp trong mọi trường hợp. Một số công đoạn và phép đo có thể chồng lấp nhau, nhất là khi có multithreading hoặc đo callback bên trong transaction.

## 3. Nguồn dữ liệu chính: `StepExecution`

Spring Batch lưu thông tin mỗi lần chạy step trong `StepExecution` và `JobRepository`. Với Spring Batch 5.x, các thuộc tính thời gian tiêu biểu có kiểu `LocalDateTime`:

```java
StepExecution stepExecution = ...;

LocalDateTime started = stepExecution.getStartTime();
LocalDateTime ended = stepExecution.getEndTime();

BatchStatus status = stepExecution.getStatus();
String stepName = stepExecution.getStepName();
Long stepExecutionId = stepExecution.getId();
```

Một số thông tin liên quan:

| Thuộc tính / counter | Ý nghĩa |
|---|---|
| `getId()` | ID của lần thực thi step |
| `getStepName()` | Tên step trong job |
| `getJobExecutionId()` | ID lượt chạy job chứa step |
| `getStartTime()` | Mốc thời gian bắt đầu step |
| `getEndTime()` | Mốc thời gian kết thúc; có thể `null` khi còn chạy |
| `getStatus()` | `STARTED`, `COMPLETED`, `FAILED`, `STOPPED`, ... |
| `getReadCount()` | Số item reader đã đọc thành công |
| `getWriteCount()` | Số item writer đã ghi theo thống kê batch |
| `getFilterCount()` | Số item processor lọc bằng cách trả `null` |
| `getReadSkipCount()` / `getProcessSkipCount()` / `getWriteSkipCount()` | Số item thực sự bị skip ở từng giai đoạn |
| `getCommitCount()` / `getRollbackCount()` | Hoạt động commit/rollback trong step |

Một `StepExecution` thường gắn với **một lần chạy step trong một `JobExecution`**. Nếu job bị dừng hoặc lỗi rồi được restart, step có thể có `StepExecution` mới. Vì vậy, khi phân tích lịch sử, cần lưu cả **`stepName` và `stepExecutionId`**, không chỉ tên step.

### 3.1. Tính duration sau khi step kết thúc

Một hàm tính đơn giản có thể xử lý trường hợp chưa có đủ mốc thời gian:

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.springframework.batch.core.StepExecution;

public final class StepDurationCalculator {

    private StepDurationCalculator() {
    }

    public static Optional<Duration> completedDuration(
            StepExecution execution) {

        LocalDateTime start = execution.getStartTime();
        LocalDateTime end = execution.getEndTime();

        if (start == null || end == null) {
            return Optional.empty();
        }

        Duration duration = Duration.between(start, end);

        if (duration.isNegative()) {
            // Không diễn giải một timestamp bất thường là thời lượng hợp lệ.
            return Optional.empty();
        }

        return Optional.of(duration);
    }
}
```

Dùng hàm:

```java
StepDurationCalculator.completedDuration(stepExecution)
        .ifPresent(duration -> {
            long elapsedMillis = duration.toMillis();

            System.out.println(
                    "step=" + stepExecution.getStepName()
                    + ", durationMs=" + elapsedMillis
            );
        });
```

**Ví dụ tính:** Step bắt đầu `2025-05-12T01:00:00` và kết thúc `2025-05-12T01:02:30` thì duration bằng **150 giây**, tức **150.000 mili-giây**.

### 3.2. Giới hạn của timestamp lấy từ metadata

`LocalDateTime` không chứa offset hoặc timezone. Nó phù hợp để biểu diễn metadata theo cách Spring Batch 5.x lưu trữ, nhưng khi tính **elapsed time cực kỳ chính xác**, cần lưu ý:

- Đồng hồ hệ điều hành có thể được điều chỉnh trong lúc job chạy.
- Múi giờ mặc định của tiến trình và cấu hình JDBC/database có thể ảnh hưởng cách diễn giải timestamp.
- Thời điểm đổi giờ mùa hè (DST) ở một số khu vực gây khó khăn khi dùng `LocalDateTime` làm thước đo elapsed tuyệt đối.
- Với step chạy nhiều ngày, thay đổi đồng hồ giữa hai mốc có thể khiến hiệu số thiếu tin cậy.

Để đo duration **trong một tiến trình đang chạy**, các hệ thống metrics như Micrometer thường đo bằng đồng hồ monotonic để tránh vấn đề đồng hồ lịch bị chỉnh. Để audit lịch sử và truy vấn khi process đã kết thúc, `startTime` và `endTime` trong `JobRepository` vẫn rất hữu ích, nhưng cần hiểu đây là phép tính từ timestamp của hệ thống.

**Không sửa `startTime`/`endTime` chỉ để “làm đẹp số liệu”.** Metadata là dữ liệu vận hành quan trọng để phân tích và restart.

## 4. Đọc step duration từ `JobExplorer`

`JobExplorer` là API đọc metadata Spring Batch. Khi đã có `jobExecutionId`, có thể lấy một execution và duyệt các step thuộc nó.

```java
import java.time.Duration;
import java.util.Comparator;
import java.util.List;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class StepDurationQueryService {

    private final JobExplorer explorer;

    public StepDurationQueryService(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public List<StepDurationRow> findByJobExecution(long jobExecutionId) {
        JobExecution job = explorer.getJobExecution(jobExecutionId);

        if (job == null) {
            throw new IllegalArgumentException(
                    "Unknown JobExecution: " + jobExecutionId
            );
        }

        return job.getStepExecutions().stream()
                .map(step -> new StepDurationRow(
                        step.getId(),
                        job.getId(),
                        step.getStepName(),
                        step.getStatus().toString(),
                        StepDurationCalculator
                                .completedDuration(step)
                                .map(Duration::toMillis)
                                .orElse(null),
                        step.getReadCount(),
                        step.getWriteCount()))
                .sorted(Comparator.comparing(
                        StepDurationRow::stepExecutionId))
                .toList();
    }

    public record StepDurationRow(
            Long stepExecutionId,
            Long jobExecutionId,
            String stepName,
            String status,
            Long durationMillis,
            long readCount,
            long writeCount
    ) {
    }
}
```

Đối với `STARTED` hoặc `STOPPING`, `durationMillis` trong ví dụ là `null` khi chưa có `endTime`. Điều đó biểu diễn **chưa có duration hoàn chỉnh**, thay vì trả về `0` hoặc coi job đã xong.

Màn hình vận hành có thể hiển thị:

| StepExecution ID | Step | Status | Duration | Read | Write |
|---:|---|---|---:|---:|---:|
| 1001 | `downloadFile` | COMPLETED | 18 s | 1 | 1 |
| 1002 | `validateRows` | COMPLETED | 102 s | 120.000 | 119.800 |
| 1003 | `writeToDatabase` | STARTED | Đang chạy | 70.000 | 65.000 |

Khi trang theo dõi hiển thị “đang chạy 8 phút”, thời lượng này là **ước lượng riêng của trang theo dõi dựa trên hiện tại**, không phải `endTime` được Spring Batch ghi. Nên hiển thị nhãn rõ ràng giữa **duration đã hoàn tất** và **elapsed tạm tính**.

### 4.1. Không lấy nhầm dữ liệu giữa các lần restart

Ví dụ:

```text
JobInstance: dailyImport, businessDate=2025-05-12
  ├── JobExecution 501
  │     └── StepExecution 1003, writeToDatabase, FAILED, 9 phút
  └── JobExecution 515 (restart)
        └── StepExecution 1042, writeToDatabase, COMPLETED, 7 phút
```

Nếu hỏi “step trong execution 515 mất bao lâu?”, đáp án là **7 phút**. Nếu hỏi “tổng thời gian xử lý step qua các attempt cho ngày đó?”, có thể tính **9 + 7 = 16 phút** như thời gian tiêu tốn cộng dồn, nhưng chỉ khi bạn muốn chỉ số đó. Nó **không phải duration của một execution**, và nếu các attempt chồng lấp, phép cộng không phản ánh thời gian lịch trôi qua.

## 5. Truy vấn metadata trong database

Spring Batch lưu lịch sử step trong bảng `BATCH_STEP_EXECUTION`; bảng job liên quan gồm `BATCH_JOB_EXECUTION` và `BATCH_JOB_INSTANCE`, với tiền tố mặc định `BATCH_`.

Một truy vấn đọc thông tin cơ bản:

```sql
SELECT
    i.JOB_NAME,
    s.JOB_EXECUTION_ID,
    s.STEP_EXECUTION_ID,
    s.STEP_NAME,
    s.START_TIME,
    s.END_TIME,
    s.STATUS,
    s.READ_COUNT,
    s.WRITE_COUNT,
    s.COMMIT_COUNT,
    s.ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION s
JOIN BATCH_JOB_EXECUTION j
    ON s.JOB_EXECUTION_ID = j.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE i
    ON j.JOB_INSTANCE_ID = i.JOB_INSTANCE_ID
WHERE s.JOB_EXECUTION_ID = :jobExecutionId
ORDER BY s.STEP_EXECUTION_ID;
```

`:jobExecutionId` đại diện cho bind parameter của ứng dụng, không phải cú pháp SQL được mọi công cụ chạy trực tiếp hỗ trợ. Có thể tính hiệu số thời gian trong Java sau khi đọc `START_TIME`/`END_TIME`, hoặc dùng phép toán timestamp của database thích hợp.

Nếu cần dashboard lịch sử:

```text
BATCH_JOB_INSTANCE
       |
       v
BATCH_JOB_EXECUTION
       |
       v
BATCH_STEP_EXECUTION
       |
       +-- STEP_NAME
       +-- STATUS
       +-- START_TIME / END_TIME
       +-- READ_COUNT / WRITE_COUNT
       +-- COMMIT_COUNT / ROLLBACK_COUNT
```

**Lưu ý khi đọc bảng trực tiếp:**

- Metadata do `JobRepository` cập nhật tại các mốc vòng đời và checkpoint; counter của step đang chạy không nhất thiết phản ánh item vừa xử lý trong thời điểm hiện tại.
- Nếu có cấu hình table prefix khác `BATCH_`, đổi tên bảng theo cấu hình thực tế.
- Không viết trực tiếp vào bảng metadata chỉ để cập nhật duration, vì có thể phá trạng thái phục vụ restart.
- Khi lưu trữ metadata theo retention policy, dữ liệu cũ có thể đã được purge; muốn báo cáo dài hạn thì cần xuất chỉ số sang hệ thống monitoring hoặc kho phân tích.

## 6. Theo dõi duration bằng Micrometer

Spring Batch có tích hợp Micrometer để thu thập metric tại các mốc xử lý batch. Trong những bản có hỗ trợ và khi Micrometer được bật, các meter đáng chú ý gồm:

| Meter name | Loại | Ý nghĩa |
|---|---|---|
| `spring.batch.job` | Timer | Duration các job execution đã hoàn tất |
| `spring.batch.job.active` | LongTaskTimer | Các job hiện đang thực thi |
| `spring.batch.step` | Timer | Duration các step execution đã hoàn tất |
| `spring.batch.step.active` | LongTaskTimer | Các step hiện đang thực thi |
| `spring.batch.item.read` | Timer | Thời gian đọc item |
| `spring.batch.item.process` | Timer | Thời gian xử lý item |
| `spring.batch.chunk.write` | Timer | Thời gian ghi chunk |

Tên meter, tag và cách auto-configure có thể thay đổi giữa các phiên bản Spring Batch/Micrometer. Kiểm tra những meter **thực sự xuất hiện** trong `/actuator/metrics` hoặc `/actuator/prometheus` trước khi xây dashboard hay alert.

### 6.1. Timer và LongTaskTimer khác nhau

**Timer** ghi nhận các operation **đã hoàn tất**: số lượt (count), tổng thời gian (total time) và có thể có bucket/histogram.

Ví dụ một `spring.batch.step` Timer có dữ liệu:

```text
step=writeToDatabase
status=COMPLETED
count=3
totalTime=35 phút
```

Trung bình = 35 / 3 ≈ 11,67 phút mỗi lượt. Đây chỉ là ví dụ, không phải output trực tiếp của một endpoint cụ thể.

**LongTaskTimer** theo dõi operation **vẫn đang chạy**, cho phép quan sát số lượng active và thời gian chạy hiện tại. Nó hữu ích khi step bị kẹt và không thể chờ đến lúc hoàn thành để timer thông thường ghi mẫu.

Ví dụ:

```text
spring.batch.step          -> lượt đã kết thúc
spring.batch.step.active   -> lượt đang chạy
```

Nếu một step treo 2 giờ, Timer của các lượt **đã hoàn tất** có thể trông hoàn toàn bình thường. Cần xem LongTaskTimer hoặc trạng thái `STARTED` cùng elapsed của execution đang chạy.

### 6.2. Cấu hình Spring Boot Actuator

Ví dụ Gradle dùng Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
```

Đây là những dependency liên quan đến Batch và metrics, chưa bao gồm JDBC driver/datasource cho `JobRepository` của ứng dụng.

Cấu hình ví dụ trong `application.yml`:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    distribution:
      percentiles-histogram:
        spring.batch.step: true
```

Với registry Prometheus và phiên bản phù hợp, có thể quan sát metric tại:

```text
GET /actuator/metrics
GET /actuator/metrics/spring.batch.step
GET /actuator/prometheus
```

`/actuator/metrics` giúp xem tên meter và tags đã xuất hiện trong process. `/actuator/prometheus` chứa cách biểu diễn cho Prometheus; Timer thường được xuất với đơn vị **giây** như `spring_batch_step_seconds_count` và `spring_batch_step_seconds_sum`. Nếu bật histogram và backend hỗ trợ, có thể có thêm các chuỗi `..._bucket`.

Nếu `/actuator/metrics/spring.batch.step` trống, cần kiểm tra xem step có thực sự chạy, Micrometer/Batch instrumentation có được kích hoạt, registry có được cấu hình và endpoint có được expose hay không. Không nên giả định mọi dự án Spring Boot đều xuất toàn bộ các meter trong bảng trên.

**Bảo mật:** Endpoint metrics có thể chứa tên job/step và thông tin vận hành. Chỉ expose tới mạng giám sát hoặc những tài khoản được phép; không mặc định công khai toàn bộ actuator trên internet.

## 7. Đọc biểu đồ duration và thiết kế dashboard

Với step chạy định kỳ, một dashboard nên giúp phân biệt **step chậm vì tải tăng** với **step chậm do hiệu suất giảm**.

Ví dụ chuỗi số liệu:

| Ngày nghiệp vụ | Step | Duration | Read count | Tốc độ đọc trung bình |
|---|---|---:|---:|---:|
| 12/05 | importOrders | 10 phút | 100.000 | 166,7 items/s |
| 13/05 | importOrders | 18 phút | 180.000 | 166,7 items/s |
| 14/05 | importOrders | 22 phút | 110.000 | 83,3 items/s |
| 15/05 | importOrders | 9 phút | 95.000 | 175,9 items/s |

Ngày 13/05, duration tăng 80% nhưng throughput gần như không đổi — tải tăng là nguyên nhân khả dĩ. Ngày 14/05, tải thấp hơn nhưng duration dài hơn: throughput giảm đáng kể, cần xem database locks, retry, lỗi I/O và hiệu năng hệ thống.

Tính throughput cơ bản:

```text
throughput = readCount / durationSeconds
```

Ví dụ 100.000 item trong 600 giây ⇒ khoảng 166,7 item/s. Với job có nhiều bước I/O không gắn với item, throughput này chỉ phản ánh **trung bình toàn step**; không thể đồng nhất nó với tốc độ reader thuần.

### 7.1. Các panel nên có

Một dashboard phục vụ vận hành có thể gồm:

1. **Duration theo tên step**: median/percentile hoặc duration từng execution.
2. **Tỉ lệ thành công/thất bại** theo step; đừng chỉ biểu diễn duration của `COMPLETED` mà bỏ qua `FAILED`.
3. **Active step count** và **active elapsed** cho step còn chạy.
4. **Read/write/filter/skip count** để so sánh tải và chất lượng dữ liệu.
5. **Commit/rollback count** để thấy transaction bị retry/rollback nhiều.
6. **Đường tới log/trace** bằng `jobExecutionId` và `stepExecutionId`.

Không nên dùng một dashboard duration duy nhất để suy diễn nguyên nhân gốc. Dữ liệu CPU, memory, GC, SQL latency, network, message broker và số retry có thể cần được đối chiếu khi có spike.

### 7.2. Prometheus: đo duration trung bình

Khi Micrometer Timer xuất các chuỗi Prometheus `spring_batch_step_seconds_sum` và `spring_batch_step_seconds_count`, ý tưởng tính trung bình theo tên step là:

```promql
sum by (name) (
  rate(spring_batch_step_seconds_sum[24h])
)
/
sum by (name) (
  rate(spring_batch_step_seconds_count[24h])
)
```

Công thức cho ra đơn vị **giây/lượt hoàn tất**, với điều kiện trong khoảng đo có số lần chạy đủ để tính. Tag thực tế có thể dùng tên khác `name` tùy phiên bản cấu hình, nên cần xem dữ liệu scrape trước khi áp dụng.

Với job mỗi ngày chạy một lần, khoảng `[5m]` thường quá ngắn và dễ không có dữ liệu; có thể dùng cửa sổ 24 giờ hoặc nhiều ngày để so sánh trend, hoặc dựa vào record từng execution trong `JobRepository`.

### 7.3. P95 và histogram

Nếu histogram đã bật và Prometheus có `spring_batch_step_seconds_bucket`, ví dụ biểu thức p95 theo step:

```promql
histogram_quantile(
  0.95,
  sum by (le, name) (
    rate(spring_batch_step_seconds_bucket[7d])
  )
)
```

Câu lệnh phụ thuộc nhãn `name` và metric thật trong Prometheus. Percentile chỉ có giá trị khi số mẫu đủ lớn; với một step chạy mỗi ngày đúng một lần, p95 trong 7 ngày rất ít mẫu và dễ gây hiểu sai. Đối với batch chạy hiếm, xem **thời lượng của từng execution** hoặc so sánh với baseline theo từng ngày/khối lượng có thể hữu ích hơn.

## 8. Phát hiện step chạy quá lâu khi chưa kết thúc

Một vấn đề thực tế: dashboard chỉ theo dõi Timer của execution hoàn tất sẽ không phát hiện step đang treo.

Giả sử bước `writeToDatabase` thường mất 10–20 phút, nhưng hôm nay đã `STARTED` 90 phút.

```text
01:00  Step STARTED
01:20  Chưa có kết quả cuối
01:45  Vẫn STARTED
02:30  Vẫn STARTED → cần kiểm tra
```

Với LongTaskTimer hoặc metadata `StepExecution.startTime`, hệ thống có thể cảnh báo khi elapsed hiện tại vượt ngưỡng. Tuy nhiên, **một dòng metadata `STARTED` không bảo đảm thread còn sống**: nếu worker chết đột ngột, `JobRepository` có thể còn trạng thái cũ.

Để cảnh báo đáng tin cậy:

- Kiểm tra trạng thái `STARTED`/`STOPPING`, thời lượng từ lúc bắt đầu, và có execution mới hay không.
- Đối chiếu worker/pod/process còn sống, checkpoint gần nhất hoặc heartbeat ứng dụng.
- Theo dõi timeout I/O và log lỗi của reader/processor/writer.
- Không tự chuyển `FAILED`/`STOPPED` chỉ vì ngưỡng thời gian bị vượt; đây là thao tác phục hồi metadata cần quy trình vận hành.

### 8.1. Ngưỡng duration phù hợp với tải

Một ngưỡng cố định “mọi step trên 5 phút đều chậm” thường không có giá trị. Ngưỡng nên theo từng step và đặc thù dữ liệu:

```text
downloadFile       > 3 phút     -> cảnh báo
validateRows       > 15 phút    -> cảnh báo
writeToDatabase    > 45 phút    -> cảnh báo
```

Đây là số minh họa. Khi khối lượng dữ liệu tăng đáng kể, ngưỡng cần điều chỉnh theo quy mô, ví dụ alert nếu **duration/10.000 items** vượt mức bình thường, hoặc throughput giảm quá mạnh trong điều kiện đầu vào tương đương.

Phân biệt hai loại cảnh báo:

- **Completed slow:** step đã kết thúc nhưng duration vượt SLO; kiểm tra hiệu năng và xu hướng.
- **Running too long:** step chưa có end time và elapsed vượt SLO; ưu tiên xác định tình trạng worker và tài nguyên đang bị kẹt.

## 9. Ghi log duration theo từng execution

Micrometer phù hợp với metric tổng hợp. Khi cần tra cứu một execution cụ thể, structured log có `jobExecutionId` và `stepExecutionId` thường hữu ích hơn việc đưa hai ID này vào labels của metrics.

Ví dụ một `JobExecutionListener` log tất cả step trong job sau khi job kết thúc:

```java
import java.time.Duration;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.batch.core.StepExecution;

public final class StepDurationLoggingListener
        implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepDurationLoggingListener.class);

    @Override
    public void afterJob(JobExecution jobExecution) {
        for (StepExecution step : jobExecution.getStepExecutions()) {
            StepDurationCalculator.completedDuration(step)
                    .ifPresentOrElse(
                            duration -> logCompleted(
                                    jobExecution,
                                    step,
                                    duration),
                            () -> log.warn(
                                    "Missing step duration: jobExecutionId={}, "
                                            + "stepExecutionId={}, stepName={}, status={}",
                                    jobExecution.getId(),
                                    step.getId(),
                                    step.getStepName(),
                                    step.getStatus())
                    );
        }
    }

    private void logCompleted(
            JobExecution job,
            StepExecution step,
            Duration duration) {

        log.info(
                "batch.step.finished jobName={} jobExecutionId={} "
                        + "stepExecutionId={} stepName={} status={} "
                        + "durationMs={} readCount={} writeCount={} "
                        + "filterCount={} rollbackCount={}",
                job.getJobInstance().getJobName(),
                job.getId(),
                step.getId(),
                step.getStepName(),
                step.getStatus(),
                duration.toMillis(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getRollbackCount()
        );
    }
}
```

Đăng ký listener ở cấu hình job:

```java
@Bean
Job importJob(
        JobRepository repository,
        Step downloadStep,
        Step processStep) {

    return new JobBuilder("importJob", repository)
            .start(downloadStep)
            .next(processStep)
            .listener(new StepDurationLoggingListener())
            .build();
}
```

`afterJob` chạy khi job tới pha kết thúc và có thể quan sát các `StepExecution` của **job execution hiện tại**. Nếu JVM crash trước callback, log không bảo đảm xuất hiện; metadata tồn tại trong `JobRepository` có thể được truy vấn để đối soát sau đó.

**Vì sao không ghi một mã ID riêng vào metric tags?** `jobExecutionId` và `stepExecutionId` thay đổi trên từng lần chạy; đặt vào tag gây **high cardinality**, khiến Prometheus/monitoring tiêu tốn nhiều bộ nhớ và khó truy vấn. Nên sử dụng tag ổn định như tên job, tên step, status; lưu ID cụ thể trong log/trace/audit.

## 10. Khi nào dùng `StepExecutionListener` tự đo thời gian?

Để bổ sung instrumentation cho **một step riêng**, có thể đo từ `beforeStep` tới `afterStep`:

```java
public class StepTimingListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution execution) {
        // Đánh dấu điểm bắt đầu đo.
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        // Ghi thời lượng và trả null nếu không cần đổi exit status.
        return null;
    }
}
```

Đoạn trên chỉ diễn tả điểm mở rộng. Trong thực tế, Spring Batch đã có metrics ở cấp step và `StepExecution` chứa timestamp, nên cần cân nhắc trước khi viết Timer custom trùng lặp.

Nếu yêu cầu riêng cần thời lượng ở độ phân giải cao hơn, nên dùng **đồng hồ monotonic**:

```java
long startNanos = System.nanoTime();

// Đơn vị xử lý trong cùng process.
performWork();

long elapsedNanos = System.nanoTime() - startNanos;
```

`System.nanoTime()` dùng để đo **khoảng thời gian trôi qua**, không dùng làm timestamp lịch hoặc lưu checkpoint qua process restart. Đoạn code minh họa này không phải một implementation hoàn chỉnh của `StepExecutionListener`.

### 10.1. Tránh biến trạng thái của listener singleton thành nguồn lỗi

Không nên lưu `startNanos` vào một field dùng chung như sau:

```java
public class UnsafeTimingListener implements StepExecutionListener {

    private long startNanos;

    @Override
    public void beforeStep(StepExecution execution) {
        startNanos = System.nanoTime();
    }

    @Override
    public ExitStatus afterStep(StepExecution execution) {
        long elapsed = System.nanoTime() - startNanos;
        System.out.println(elapsed);
        return null;
    }
}
```

Nếu một bean listener singleton được đăng ký với nhiều step chạy song song, lần gọi `beforeStep` khác có thể ghi đè thời gian bắt đầu và làm số đo sai.

Các hướng an toàn hơn:

- Ưu tiên instrumentation mặc định của Spring Batch/Micrometer.
- Dùng `Timer.Sample` gắn với từng lần execution trong một cơ chế lưu trạng thái an toàn; giải phóng state khi kết thúc.
- Nếu cần bản ghi lịch sử, dựa vào metadata `StepExecution` và `JobRepository`.
- Tránh đưa `System.nanoTime()` từ JVM này sang JVM khác hoặc lưu vào `ExecutionContext` để dùng sau restart, vì giá trị monotonic chỉ có ý nghĩa trong cùng môi trường đo.

## 11. Kiểm thử logic tính duration

Một test đúng phải kiểm tra mốc thời gian rõ ràng thay vì đợi job chạy đủ một số mili-giây. Vì `StepExecution` đã cho phép lưu start/end time, unit test chỉ cần tạo đối tượng rồi tính hiệu.

### 11.1. Unit test với timestamp cố định

Ví dụ JUnit Jupiter và `spring-batch-test`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;

class StepDurationCalculatorTest {

    @Test
    void completedStepShouldReturn150Seconds() {
        StepExecution execution =
                MetaDataInstanceFactory.createStepExecution();

        execution.setStartTime(
                LocalDateTime.of(2025, 5, 12, 1, 0, 0)
        );
        execution.setEndTime(
                LocalDateTime.of(2025, 5, 12, 1, 2, 30)
        );

        Optional<Duration> elapsed =
                StepDurationCalculator.completedDuration(execution);

        assertEquals(
                Duration.ofSeconds(150),
                elapsed.orElseThrow()
        );
    }

    @Test
    void runningStepShouldNotHaveCompletedDuration() {
        StepExecution execution =
                MetaDataInstanceFactory.createStepExecution();

        execution.setStartTime(
                LocalDateTime.of(2025, 5, 12, 1, 0)
        );
        execution.setEndTime(null);

        assertTrue(
                StepDurationCalculator.completedDuration(execution)
                        .isEmpty()
        );
    }

    @Test
    void inconsistentTimestampsShouldNotProduceNegativeDuration() {
        StepExecution execution =
                MetaDataInstanceFactory.createStepExecution();

        execution.setStartTime(
                LocalDateTime.of(2025, 5, 12, 2, 0)
        );
        execution.setEndTime(
                LocalDateTime.of(2025, 5, 12, 1, 0)
        );

        assertTrue(
                StepDurationCalculator.completedDuration(execution)
                        .isEmpty()
        );
    }
}
```

Test không dựa trên `LocalDateTime.now()` hoặc `Thread.sleep()`. Nó kiểm tra **quy tắc tính từ metadata**, không chứng minh framework tự điền start/end time hoặc cập nhật counter đúng. Các hành vi đó thuộc integration test.

### 11.2. Test Timer mà không đợi thời gian thật

Nếu tự viết instrumentation bằng Micrometer, có thể dùng `MockClock` để đo chính xác mà không cần ngủ:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

import io.micrometer.core.instrument.MockClock;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleConfig;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.junit.jupiter.api.Test;

class StepTimerTest {

    @Test
    void timerShouldRecordThreeSecondsWithoutSleeping() {
        MockClock clock = new MockClock();

        try (SimpleMeterRegistry registry =
                     new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock)) {

            Timer timer = Timer.builder("custom.batch.step.duration")
                    .tag("step", "importOrders")
                    .register(registry);

            Timer.Sample sample = Timer.start(registry);

            // Điều khiển đồng hồ đo của Micrometer:
            clock.add(Duration.ofSeconds(3));

            sample.stop(timer);

            assertEquals(1L, timer.count());
            assertEquals(
                    3.0,
                    timer.totalTime(TimeUnit.SECONDS),
                    0.000001
            );
        }
    }
}
```

`MockClock` thuộc Micrometer, khác `java.time.Clock.fixed(...)`. Nó phù hợp để test metric do ứng dụng chủ động đo; cách test này không có nghĩa mọi meter tích hợp sẵn trong framework tự động nhận một `MockClock` được tạo trong test khác.

### 11.3. Integration test chạy step thật

Để xác nhận `StepExecution.startTime` và `endTime` được ghi khi framework thực thi step, có thể tạo test Spring Batch chạy một tasklet hữu hạn:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBatchTest
@SpringBootTest(
        classes = StepDurationIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class StepDurationIntegrationTest {

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Test
    void completedStepShouldHaveStartAndEndTime() throws Exception {
        JobExecution job = launcherTestUtils.launchStep("measuredStep");

        StepExecution step = job.getStepExecutions()
                .iterator()
                .next();

        assertEquals(BatchStatus.COMPLETED, step.getStatus());
        assertNotNull(step.getStartTime());
        assertNotNull(step.getEndTime());
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        Step measuredStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager) {

            return new StepBuilder("measuredStep", repository)
                    .tasklet((contribution, context) ->
                            RepeatStatus.FINISHED, transactionManager)
                    .build();
        }

        @Bean
        Job durationTestJob(
                JobRepository repository,
                Step measuredStep) {

            return new JobBuilder("durationTestJob", repository)
                    .start(measuredStep)
                    .build();
        }
    }
}
```

Test dùng `launchStep` để kiểm tra **một step** và không cần đợi thời gian giả. Nó không giả định step nhất thiết mất hơn 10 ms, vì môi trường CI, JIT, CPU và kích thước tải khác nhau. Muốn kiểm tra thống kê metrics, cần test riêng việc registry nhận mẫu và tên meter/tag thực tế trên stack đang sử dụng.

Nếu muốn test listener log duration cấp job, dùng `launchJob(...)` vì listener cấp job gốc không nhất thiết được gọi khi `launchStep(...)` tạo wrapper job riêng.

## 12. Phân tích step chậm có hệ thống

Khi một step có duration tăng đột biến, nên đối chiếu các dữ liệu sau.

### 12.1. Khối lượng và throughput

```text
Baseline:
  duration    = 10 phút
  readCount   = 100.000
  read/sec    = 166,7

Hôm nay:
  duration    = 30 phút
  readCount   = 100.000
  read/sec    = 55,6
```

Vì khối lượng giống nhau mà throughput giảm còn một phần ba, kiểm tra I/O, lock, network, GC, tài nguyên CPU và concurrency. Nếu hôm nay đọc gấp ba lần dữ liệu nhưng throughput không đổi, cần cân nhắc capacity hoặc lịch chạy thay vì ngay lập tức quy kết hồi quy hiệu năng.

### 12.2. Retry, skip và rollback

Một step có thể hoàn tất `COMPLETED` nhưng chậm vì nhiều lỗi đã được retry thành công:

- `rollbackCount` tăng có thể là dấu hiệu transaction lặp lại.
- `readSkipCount`, `processSkipCount`, `writeSkipCount` cho biết có item bị bỏ qua.
- `filterCount` tăng không có nghĩa lỗi; processor có thể chủ động lọc.
- Bộ đếm chỉ tổng hợp hành vi đã được framework ghi nhận, không cung cấp histogram thời lượng từng lần retry.

Nếu cần biết **retry nào chậm**, thêm metric/log phù hợp ở policy hoặc component tương ứng, tránh nhồi mọi trường dữ liệu vào metric tags.

### 12.3. DB và transaction

Step ghi database thường bị ảnh hưởng bởi:

- Lock contention và transaction isolation.
- Kích thước chunk/batch insert.
- Index maintenance, trigger, foreign key.
- Connection pool thiếu kết nối.
- Query plan thay đổi khi dữ liệu tăng.
- Commit hoặc deadlock retry.

Duration cấp step cho biết **có chậm**, còn SQL monitoring/tracing cho biết **chậm ở đâu**.

### 12.4. Remote service và file I/O

Nếu reader gọi HTTP hoặc tải file qua SFTP, latency tăng thường nằm ngoài CPU application. Cần timeout hữu hạn, retry có giới hạn, metric request latency và trace có correlation ID. Không nên chỉ tăng timeout vô hạn để che duration tăng.

## 13. Các trường hợp đặc biệt làm số liệu khó so sánh

### 13.1. Step chạy song song

Với parallel flows, hai step có thể cùng hoạt động:

```text
Timeline (đơn vị: phút)

Step A: |=========== 10 ===========|
Step B: |====== 6 ======|

Job wall-clock xấp xỉ 10 phút
Tổng step durations = 10 + 6 = 16 phút
```

Tổng 16 phút thể hiện tài nguyên/thời gian làm việc cộng dồn của hai step, không phải 16 phút thời gian trôi qua. Nếu hai step dùng tài nguyên chung, phân tích thêm mức concurrency và tình trạng tranh chấp.

### 13.2. Partitioned step

Manager step chia dữ liệu cho nhiều worker/partition. Mỗi partition có `StepExecution` riêng; duration manager và duration worker có thể chồng lấp. Cộng tất cả có thể hữu ích để hiểu tổng chi phí xử lý, nhưng **không** thể dùng làm end-to-end duration.

Một dashboard partitioning nên hiển thị:

- Duration manager.
- Duration từng partition và partition chậm nhất.
- Phân bố read/write count theo partition.
- Thời gian đợi phân phối, queue và worker.
- Tình trạng partition fail hoặc retry.

Phân phối dữ liệu lệch (data skew) thường khiến một partition chạy lâu hơn hẳn các partition còn lại dù tổng throughput tốt.

### 13.3. Restart

Sau khi job `FAILED` hoặc `STOPPED`, lần restart có thể tạo `StepExecution` mới. So sánh duration phải xác định rõ đang hỏi:

- Duration của execution mới nhất?
- Duration cộng dồn của các attempt?
- Thời gian từ khi lần đầu bắt đầu đến khi hoàn tất sau restart, gồm cả chờ người vận hành?

Đó là ba metric khác nhau. Mỗi loại phục vụ một câu hỏi vận hành khác nhau.

### 13.4. Step FAILED/STOPPED có được tính không?

Có, nếu bạn muốn đánh giá chi phí xử lý và sự cố. Một step thất bại sau 60 phút là thông tin quan trọng, dù nó không đóng góp vào duration trung bình của các lượt `COMPLETED`.

Khi vẽ biểu đồ, hãy tách status để người dùng hiểu dataset. Không nên loại bỏ mọi `FAILED` rồi kết luận hệ thống đang nhanh hơn; đây là một kiểu **survivorship bias** trong metrics.

### 13.5. Đồng hồ và timestamp

Không suy ra duration **từ cron dự kiến** và cũng không lấy thời gian xuất hiện dòng log cuối trừ thời gian scheduler gửi lệnh. Mốc đó có thể bao gồm queue delay, logging delay, network và khác biệt đồng hồ giữa các máy. Với dashboard cấp step, hãy dùng dữ liệu thực thi của `StepExecution` hoặc meter đo chính step.

## 14. Checklist vận hành cho step duration

| Câu hỏi | Chỉ số / công cụ cần xem |
|---|---|
| Step đã kết thúc chưa? | `StepExecution.status` và `endTime` |
| Step cụ thể mất bao lâu? | `startTime`, `endTime`, hoặc `spring.batch.step` Timer |
| Step đang chạy lâu bất thường? | `spring.batch.step.active` hoặc `STARTED` + elapsed theo metadata |
| Lượng dữ liệu có tăng? | `readCount`, `writeCount`, business input count |
| Tốc độ xử lý có giảm? | Duration kết hợp item count và throughput |
| Có nhiều rollback/retry? | `rollbackCount`, log retry, error metrics |
| Bị chậm trong reader/process/writer? | `spring.batch.item.read`, `spring.batch.item.process`, `spring.batch.chunk.write` và traces |
| Đây là lượt restart hay lượt đầu? | `jobExecutionId`, `stepExecutionId`, `JobInstance` |
| Có partition chạy chậm nhất? | Duration theo partition và dữ liệu phân phối |
| Metadata thiếu endTime? | Trạng thái worker/process, crash, recovery procedure |

### Anti-pattern phổ biến

| Anti-pattern | Vấn đề | Thay bằng |
|---|---|---|
| Tính duration bằng `Thread.sleep` trong test | Test phụ thuộc thời gian thật và dễ flaky | Timestamp cố định hoặc Micrometer `MockClock` |
| Dùng `LocalDateTime.now()` hai lần rồi assert chênh chính xác | Dễ lệch vì thời gian trôi trong test | Inject clock hoặc đo có kiểm soát |
| Xem `STARTED` với `endTime=null` như duration 0 | Che giấu step chậm/đang treo | Hiển thị “đang chạy”, theo dõi active elapsed |
| Cộng duration step song song ra job duration | Đếm trùng thời gian chồng lấp | Dùng `JobExecution` cho wall-clock job |
| Đặt `stepExecutionId` vào Prometheus tags | Cardinality tăng theo số lượt chạy | Lưu ID trong log/traces |
| Chỉ theo dõi các step `COMPLETED` | Bỏ qua step thất bại chậm | Phân tách series theo status |
| Tin mọi `STARTED` đều còn xử lý | JVM có thể đã crash | Đối chiếu worker heartbeat/process |
| So duration giữa ngày có lượng dữ liệu khác nhau | Dễ kết luận sai về hồi quy | Kết hợp volume, throughput và p95 |
| Tự cập nhật bảng `BATCH_STEP_EXECUTION` | Có thể phá metadata/restart | Đọc qua `JobExplorer` hoặc query read-only |
| Chỉ quan sát timer các lượt đã xong | Không phát hiện step treo hiện tại | LongTaskTimer và active execution |

## 15. Bài tập thực hành

Xây dựng job `nightlyInvoiceImport` có ba step: `downloadInvoices`, `validateInvoices` và `persistInvoices`. Mỗi đêm, job xử lý dữ liệu cho một `businessDate` cố định.

Yêu cầu:

1. Bật Spring Boot Actuator và Micrometer, quan sát `spring.batch.step` sau khi job hoàn tất.
2. Viết service dùng `JobExplorer` trả danh sách step gồm `stepExecutionId`, `status`, `startTime`, `endTime`, `durationMillis`, `readCount` và `writeCount`.
3. Viết unit test cho hàm tính duration với ba tình huống: 150 giây, step đang chạy chưa có `endTime`, metadata có mốc ngược.
4. Viết integration test chạy step thật và xác nhận framework đã lưu thời điểm bắt đầu/kết thúc.
5. Tạo hai fixture: 100.000 invoice xử lý 10 phút và 180.000 invoice xử lý 18 phút. Giải thích vì sao duration tăng nhưng throughput không giảm.
6. Thiết kế dashboard có duration theo step, active duration, read/write count, rollbackCount và status.
7. Mô phỏng một partition mất 20 phút trong khi ba partition khác mất 5 phút; xác định partition bottleneck và giải thích vì sao không cộng cả bốn để ra wall-clock job.
8. Mô phỏng `persistInvoices` thất bại rồi được restart. Lưu riêng duration của từng `StepExecution` và một chỉ số tổng hợp qua các attempt.
9. Thiết lập cảnh báo khi `persistInvoices` đang chạy trên 45 phút. Nêu điều kiện cần kiểm tra trước khi kết luận worker bị treo.

**Câu hỏi ôn tập:** Nếu `spring.batch.step` cho thấy các lượt hoàn tất của `persistInvoices` đều dưới 15 phút nhưng một execution hiện vẫn `STARTED` sau 90 phút, hệ thống có đang bình thường không? **Chưa thể kết luận bình thường.** Cần theo dõi LongTaskTimer, kiểm tra worker hiện tại và các điểm nghẽn; Timer của các lượt đã hoàn tất không biểu diễn execution đang treo.

## 16. Tài liệu tham khảo

- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): tích hợp Micrometer, tên các meter và cách theo dõi job/step.
- [Spring Batch 5.2 — StepExecution API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/StepExecution.html): `getStartTime()`, `getEndTime()`, `getStatus()` và các counter.
- [Spring Batch 5.2 — JobExplorer API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/explore/JobExplorer.html): truy vấn metadata job/step execution.
- [Spring Batch — Metadata Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng `BATCH_JOB_EXECUTION` và `BATCH_STEP_EXECUTION`.
- [Spring Boot Reference — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): metrics endpoint, registry và phân phối duration.
- [Micrometer Reference — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer, LongTaskTimer và cách đo thời gian.
- [Prometheus Documentation — Histograms and Summaries](https://prometheus.io/docs/practices/histograms/): đọc histogram và percentile từ các mẫu duration.
