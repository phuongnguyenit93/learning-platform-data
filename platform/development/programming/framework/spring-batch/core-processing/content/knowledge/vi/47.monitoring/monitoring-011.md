# Alert job không tiến triển trong Spring Batch

## 1. Mục tiêu: phát hiện job bị kẹt trước khi vi phạm SLA

Một Spring Batch job có thể ở trạng thái `STARTED` rất lâu mà không xử lý thêm dữ liệu. Ví dụ, job nhập 2 triệu giao dịch chạy bình thường trong 20 phút, sau đó `ItemReader` bị chặn vô hạn bởi kết nối mạng, không có bản ghi nào mới được commit. Vì job chưa ném exception, `JobRepository` có thể vẫn ghi nhận nó đang chạy. Nếu hệ thống chỉ gửi cảnh báo khi `BatchStatus.FAILED`, sự cố này có thể không được phát hiện cho tới khi nghiệp vụ nhận ra dữ liệu chưa sẵn sàng.

**Alert job không tiến triển** (*stalled job alert*) nhằm phát hiện một execution còn được coi là đang chạy nhưng **không có tín hiệu tiến triển đáng tin cậy trong khoảng thời gian vượt ngưỡng**. Đây là một bài toán của nhóm *Monitoring* trong module *Spring Batch Core Processing*.

Sau bài học, bạn có thể:

- Phân biệt **job chạy lâu**, **job chậm**, **job không tiến triển** và **job không được kích hoạt đúng lịch**.
- Đọc metadata qua `JobExplorer` để nhận biết execution và các bộ đếm của `StepExecution`.
- Thiết kế tín hiệu tiến triển từ counter, checkpoint, heartbeat và trạng thái nguồn dữ liệu.
- Chọn ngưỡng cảnh báo riêng theo job/step và hạn chế cảnh báo giả.
- Viết bộ phát hiện stall có thể unit test bằng `Clock`/`Instant`.
- Kết hợp Micrometer, Prometheus, Alertmanager hoặc hệ thống observability tương đương để gửi, khử trùng lặp và đóng cảnh báo.
- Xây dựng runbook xử lý an toàn, tránh restart tự động khi chưa biết trạng thái side effect.

Các ví dụ Java tập trung vào **Java 17, Spring Boot 3.x và Spring Batch 5.2.x**. Khi dùng Spring Batch 6.x cần đối chiếu thay đổi package và API theo phiên bản.

---

## 2. “Không tiến triển” nghĩa là gì?

Không phải cứ `readCount` đứng yên là batch hỏng. Một job có thể đang:

- Khởi động JVM, nạp cấu hình hoặc tạo partition.
- Chạy truy vấn SQL lớn trong một `ItemReader`.
- Xử lý một item mất nhiều phút do gọi API ngoài.
- Đang chờ nguồn dữ liệu mà nghiệp vụ cho phép tạm thời rỗng.
- Tính toán trong một `Tasklet` không có item reader/writer.
- Cố tình chờ tới một cửa sổ thời gian đã định.
- Xử lý retry/backoff có kiểm soát.

Vì vậy, định nghĩa thực tế phải gồm **tiến triển mong đợi của từng loại step** và **mức chậm tối đa được chấp nhận**.

| Tình huống | Tín hiệu quan sát | Có nên alert stalled ngay? |
|---|---|---|
| Job chạy 3 giờ, `writeCount` đều tăng | Tiến triển bình thường nhưng tổng thời gian lớn | Không theo quy tắc stall; có thể cảnh báo riêng về SLA/duration |
| Job `STARTED`, read/write không tăng trong 15 phút, bình thường mỗi phút phải commit | Khả năng stall cao | Có, nếu vượt ngưỡng và không có lý do hợp lệ |
| Chunk 50.000 item mất 12 phút, chưa commit | Metadata có thể chưa đổi dù CPU đang làm việc | Cần heartbeat/tiến triển nội bộ hoặc ngưỡng theo chunk |
| Tasklet gửi một yêu cầu xử lý rồi chờ kết quả 30 phút | Không có counters item | Dùng heartbeat/phase và SLA chuyên biệt |
| Job `FAILED` | Đã kết thúc với lỗi | Gửi alert failure riêng, không phân loại stalled |
| Job không xuất hiện vào giờ bắt buộc | Không có execution mới | Gửi alert missing schedule, không phải stalled |
| Job `STARTED` trong DB, JVM đã chết | Trạng thái metadata bị bỏ lại | Cảnh báo suspected orphan, kiểm tra tiến trình/lease |
| Job được `STOPPING` có chủ đích | Trạng thái đang dừng | Theo dõi timeout dừng, không dùng cùng ngưỡng stall thông thường |

Một định nghĩa vận hành hữu ích:

> Một step được xem là **nghi ngờ không tiến triển** khi nó còn trong trạng thái cần xử lý, không có tiến triển nghiệp vụ hay checkpoint mới trong khoảng thời gian vượt ngưỡng dành cho step đó, và các ngoại lệ hợp lệ (grace period, chờ dữ liệu, maintenance, backoff) đã được xét đến.

Từ **nghi ngờ** rất quan trọng: các counter chỉ là bằng chứng quan sát, chưa tự khẳng định nguyên nhân.

### 2.1. Bốn loại cảnh báo khác nhau

1. **Not started / missing execution:** lịch yêu cầu job phải bắt đầu, nhưng không có `JobExecution` cho kỳ dữ liệu.
2. **Slow / SLA risk:** job vẫn tiến triển nhưng dự đoán kết thúc sau hạn.
3. **Stalled progress:** job còn chạy nhưng dữ liệu/phase không tiến triển theo kỳ vọng.
4. **Orphan / dead worker:** repository vẫn hiển thị trạng thái chạy, nhưng process hoặc worker không còn hoạt động.

Nên dùng các loại alert khác nhau hoặc ít nhất gắn trường `reason` khác nhau. Nhờ vậy người trực vận hành biết cần kiểm tra scheduler, performance, dependency hay hạ tầng.

---

## 3. Kiến trúc giám sát cơ bản

Một hệ thống phát hiện stall có thể chia thành bốn phần:

```text
Spring Batch worker
  ├── Job / Step executions
  ├── JobRepository (metadata đã commit)
  ├── Micrometer (thời gian, số lần gọi, metrics)
  └── optional ProgressHeartbeat (phase, checkpoint, timestamp)
                   │
                   ▼
       Dữ liệu quan sát tập trung
   JobExplorer + metrics + heartbeat store
                   │
                   ▼
         Stall detection service
  ├── trạng thái execution
  ├── lần tiến triển gần nhất
  ├── ngưỡng theo job/step
  ├── grace period / suppression
  └── kiểm tra liên tiếp / deduplication
                   │
                   ▼
           Alerting backend
     Prometheus / Alertmanager / Ops
                   │
                   ▼
         Người trực và runbook
  kiểm tra → xác định nguyên nhân → khắc phục
```

Có hai cách tổ chức:

- **Theo dõi từ cùng tiến trình batch:** đơn giản, có thể đọc counters in-memory; nhưng nếu JVM treo hoặc chết, chính bộ giám sát cũng dừng.
- **Theo dõi từ tiến trình riêng:** tra `JobRepository`/metrics/heartbeat store qua mạng; có thể phát hiện worker biến mất. Khi đó cần quản lý quyền đọc, khoảng trễ dữ liệu và kết nối tới đúng repository.

Với job quan trọng, một bộ giám sát **độc lập với tiến trình batch** giúp phát hiện cả sự cố process. Nhưng monitor cũng cần được giám sát: nếu không truy vấn được repository, đó phải là alert **monitoring failure/unknown**, không phải kết luận “mọi job đều đã hoàn tất”.

---

## 4. Những tín hiệu có sẵn trong Spring Batch

### 4.1. JobExecution và StepExecution

Spring Batch lưu metadata qua `JobRepository`. Tại mức job có:

- `JobExecution.getId()`, `getStatus()`, `getStartTime()`, `getEndTime()`.
- `JobExecution.getLastUpdated()`: thời điểm metadata execution được persist cập nhật gần nhất.
- `JobExecution.getStepExecutions()`: các lần thực thi step được gắn với execution.

Tại mức step có:

| Tín hiệu | Getter của StepExecution | Ý nghĩa quan sát |
|---|---|---|
| Đã đọc | `getReadCount()` | Số item được ghi nhận đã đọc |
| Đã ghi | `getWriteCount()` | Số item được ghi nhận đã ghi |
| Lọc | `getFilterCount()` | Item processor trả `null` để lọc |
| Skip khi đọc | `getReadSkipCount()` | Item đọc lỗi nhưng được skip |
| Skip khi xử lý | `getProcessSkipCount()` | Item xử lý lỗi nhưng được skip |
| Skip khi ghi | `getWriteSkipCount()` | Item ghi lỗi nhưng được skip |
| Commit | `getCommitCount()` | Số lần commit step transaction |
| Rollback | `getRollbackCount()` | Số lần rollback |
| Bắt đầu/kết thúc | `getStartTime()`, `getEndTime()` | Mốc vòng đời step |
| Lần cập nhật | `getLastUpdated()` | Mốc metadata step được cập nhật/persist |
| Trạng thái | `getStatus()` | `STARTED`, `FAILED`, `COMPLETED`... |

**Điểm quan trọng:** các bộ đếm trong repository thường phản ánh công việc **đã đi qua ranh giới cập nhật/commit**. Trong lúc một chunk đang chạy, số item đang được xử lý có thể chưa được persist. Vì vậy counter không đổi chưa chứng minh thread ngừng hoạt động.

Ví dụ, với `chunk(1000)` và một lần đọc API mất 18 phút, `readCount` có thể đứng yên trong 18 phút, mặc dù reader vẫn đang đợi kết quả theo một timeout hợp lệ. Nếu SLO chỉ cho phép 5 phút không có **output đã commit**, đây vẫn có thể là cảnh báo có ích; nếu yêu cầu là “process thực sự treo”, cần thêm tín hiệu.

### 4.2. lastUpdated có phải heartbeat không?

**Không.** `StepExecution.getLastUpdated()` và `JobExecution.getLastUpdated()` phản ánh lần đối tượng metadata được update/persist, không phải cam kết có một tín hiệu heartbeat định kỳ mỗi N giây.

Hệ quả:

- Một step xử lý CPU trong một chunk dài có thể hoạt động nhưng `lastUpdated` không đổi.
- Một execution còn `STARTED` có thể đã chết đột ngột trước khi kịp ghi trạng thái `FAILED`.
- Việc cập nhật metadata có thể diễn ra mà số lượng output hữu ích chưa tăng (ví dụ rollback/retry).
- Timestamp API có thể là `LocalDateTime` không chứa timezone; không tự giả định đây là UTC rồi tính độ trễ nếu chưa kiểm tra chính sách ghi/đọc của hệ thống.

Sử dụng `lastUpdated` làm **tín hiệu hỗ trợ**, kết hợp với counters, heartbeat và trạng thái worker. Đừng định nghĩa `now() - lastUpdated > 5m` là bằng chứng duy nhất của deadlock.

### 4.3. Đọc các execution đang chạy qua JobExplorer

API Spring Batch 5.2:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

Set<JobExecution> running =
        jobExplorer.findRunningJobExecutions("dailyImportJob");

for (JobExecution job : running) {
    System.out.println("Job execution: " + job.getId());
    System.out.println("Status: " + job.getStatus());

    for (StepExecution step : job.getStepExecutions()) {
        System.out.printf(
                "%s read=%d write=%d filter=%d commit=%d rollback=%d%n",
                step.getStepName(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getCommitCount(),
                step.getRollbackCount());
    }
}
```

`findRunningJobExecutions` tìm các execution mà **repository ghi nhận là running**. Tập trả về không bảo đảm thứ tự; khi muốn tìm chi tiết step hoặc `ExecutionContext` đầy đủ, có thể gọi:

```java
StepExecution detailed = jobExplorer.getStepExecution(
        jobExecutionId, stepExecutionId);
```

Lưu ý dữ liệu step lồng trong kết quả tìm running có thể chưa được hydrate đầy đủ tùy implementation. Các bộ đếm và status thường đủ cho tổng quan, nhưng cần đọc riêng khi muốn chắc chắn có execution context.

**Không dùng `JobExplorer` để ghi heartbeat hoặc cập nhật status.** Đây là API đọc metadata. Không thay `BatchStatus` trực tiếp trong database để “sửa” một job treo.

### 4.4. Kiểm tra một lần chạy đã FAILED hay chưa

`BatchStatus.isRunning()` trả true cho `STARTING`, `STARTED` và `STOPPING`. Tuy nhiên, bộ detector đọc tiến triển item nên thường chỉ theo dõi **StepExecution ở `STARTED`**. Một job đang `STARTING` mà chưa có step cần detector “startup timeout” riêng; `STOPPING` cần “stop timeout” riêng.

Để tránh đánh đồng các trạng thái:

```java
if (jobExecution.getStatus() == BatchStatus.FAILED) {
    // Alert job failure.
} else if (jobExecution.getStatus() == BatchStatus.STARTED) {
    // Kiểm tra progress, startup timeout, heartbeat.
} else if (jobExecution.getStatus() == BatchStatus.STOPPING) {
    // Kiểm tra stop timeout.
}
```

---

## 5. Built-in metrics, Micrometer và tín hiệu bổ sung

Spring Batch 5.2 tích hợp các metric dựa trên Micrometer dưới prefix `spring.batch`. Các metric thường gặp gồm:

| Meter | Kiểu | Giúp trả lời câu hỏi |
|---|---|---|
| `spring.batch.job` | Timer | Job hoàn tất trong bao lâu? |
| `spring.batch.job.active` | Long task timer | Có bao nhiêu job đang active trong tiến trình gắn metrics? |
| `spring.batch.step` | Timer | Thời gian thực thi step theo status |
| `spring.batch.step.active` | Long task timer | Step nào đang active và đã active bao lâu? |
| `spring.batch.item.read` | Timer | Thời gian đọc item, mức lỗi/độ trễ đọc |
| `spring.batch.item.process` | Timer | Thời gian xử lý item |
| `spring.batch.chunk.write` | Timer | Thời gian ghi chunk |
| `spring.batch.job.launch.count` | Counter | Số lần gọi launch job |

Tên meter ở trên là tên ở tầng Micrometer; Prometheus có thể chuyển dấu chấm thành dấu gạch dưới và thêm hậu tố theo kiểu meter/phiên bản registry. Khi viết PromQL, cần kiểm tra **tên series thực tế tại endpoint metrics**, tránh suy từ tên Java.

Spring Boot Actuator và Prometheus registry có thể được dùng để xuất metrics:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

Ví dụ cấu hình endpoint (chỉ expose qua mạng nội bộ có bảo vệ):

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
```

Ở Spring Batch 5.2, các built-in metrics được ghi vào Micrometer global registry; cách xuất và đồng bộ với registry phụ thuộc cấu hình Micrometer/Spring Boot đang dùng. Ở Spring Batch 6.x, cơ chế observability được cấu hình theo `ObservationRegistry`, vì vậy cần đọc đúng tài liệu phiên bản trước khi nâng cấp.

**Giới hạn:** `spring.batch.job.active` cho biết active duration ở process xuất metrics. Nó **không bảo đảm** item đang tiến triển. Nếu process bị kill, metric active từ process cũng có thể biến mất; cần thêm giám sát liveness của worker và kỳ chạy được mong đợi.

### 5.1. Tín hiệu “tiến triển” nào đủ tốt?

Tùy loại step:

| Loại step | Tín hiệu có ích | Tín hiệu dễ gây hiểu lầm |
|---|---|---|
| Chunk đọc/ghi CSV | `readCount`, `writeCount` sau commit; checkpoint mới | Chỉ nhìn `STARTED` |
| Xử lý có filter hợp lệ | `readCount` cùng `filterCount` | Chỉ nhìn `writeCount` và kết luận stall khi tất cả bị filter |
| Step retry nhiều lỗi | Số item thành công, retry count, rollback count | Coi rollback liên tục là tiến triển nghiệp vụ |
| Tasklet tính toán lâu | Phase, số đối tượng đã hoàn tất, heartbeat có giải thích | `readCount=0` kéo dài |
| Đọc hàng đợi/stream | Offset đã xác nhận, lag, heartbeat, tình trạng nguồn | Coi không có message là lỗi dù nguồn hợp lệ đang rỗng |
| Step ghi file lớn | Byte/chunk đã commit, output finalization phase | Coi file size đứng yên lúc đang buffer là stall |
| Partitioned step | Tiến triển của từng partition và tiến triển tổng | Chỉ xem master step trong khi một worker bị kẹt |

### 5.2. Heartbeat khác meaningful progress

Một heartbeat đơn giản có thể phát mỗi 30 giây dù thread chỉ lặp “still alive”. Khi đó nó chứng minh **worker còn sống** nhưng chưa chứng minh đang tạo ra kết quả.

Nên tách hai khái niệm:

- **Liveness heartbeat:** tại `Instant` nào worker/step còn kiểm tra được trạng thái của mình?
- **Progress watermark:** tại `Instant` nào bước xử lý đạt checkpoint/kết quả nghiệp vụ mới, ví dụ số record xử lý thành công, offset đã ACK hoặc phase đã hoàn tất?

Một worker có heartbeat mới nhưng progress không đổi trong 20 phút có thể đang chờ, deadlock một thành phần hoặc stuck trong retry loop. Hai tín hiệu kết hợp giúp chọn severity và hành động phù hợp.

---

## 6. Định nghĩa ngưỡng cảnh báo theo step và SLA

Một ngưỡng chung như “không tăng counter sau 5 phút” thường tạo quá nhiều cảnh báo giả. Thay vào đó, cần hiểu nhịp xử lý bình thường.

Giả sử:

- `dailyImportJob/importCsvStep` bình thường commit mỗi 20–40 giây; một commit đôi khi mất 3 phút.
- `dailyImportJob/exportRemoteStep` gọi API ngoài, mỗi request có timeout 4 phút và có retry/backoff.
- `monthlyClosingJob/calculateTaxStep` có một phase tính toán không có counter item, mất tới 25 phút.

Ngưỡng ví dụ ban đầu:

| Job / Step | Quan sát progress chính | Thời gian không tiến triển cần xem xét | Ghi chú |
|---|---|---|---|
| `importCsvStep` | Counters item sau commit | 10 phút | Vượt xa thời gian chunk bình thường |
| `exportRemoteStep` | Bản ghi đã ACK + phase | 15 phút | Tính cả timeout và backoff hợp lệ |
| `calculateTaxStep` | Heartbeat/phase marker | 35 phút | Không dùng read/write counters |
| Toàn bộ job | End-to-end deadline | 2 giờ | Alert SLA riêng, có thể xảy ra dù vẫn tiến triển |

Các giá trị trên chỉ là **minh họa**, không phải hằng số đúng cho mọi hệ thống. Trong thực tế nên xác định ngưỡng bằng latency percentile (p95/p99), kích thước chunk, throughput tối thiểu, độ trễ nguồn và cam kết SLA.

### 6.1. Các khoảng thời gian quan trọng

- **Startup grace:** chờ cho job tạo step, mở reader, kết nối tới nguồn dữ liệu.
- **Polling interval:** thời gian giữa hai lần đọc metadata, ví dụ 30 giây.
- **Stall threshold:** tối đa cho phép không có tiến triển, ví dụ 10 phút.
- **Confirmation:** yêu cầu điều kiện kéo dài hai hay ba lần poll hoặc dùng Alertmanager `for: 2m`.
- **Recovery condition:** phát hiện counters/phase tăng trở lại hoặc job kết thúc theo trạng thái thực.
- **Cooldown/dedup:** không phát cùng alert mỗi 30 giây cho cùng execution đã bị nghi stuck.

Ví dụ:

```text
09:00:00 step STARTED
09:00:30 detector nhìn thấy step lần đầu, read=1_000
09:01:30 read=2_000  → reset đồng hồ không tiến triển
09:05:30 read=2_000  → chưa vượt ngưỡng 10 phút
09:11:30 read=2_000  → đã 10 phút, candidate STALLED
09:13:30 vẫn không tăng → gửi critical alert sau confirmation
09:14:00 read=3_000  → đánh dấu recovered
```

### 6.2. Công thức

Với step `s`:

```text
progressSignature(s) =
    (readCount, writeCount, filterCount,
     readSkipCount, processSkipCount, writeSkipCount)

lastProgressObservedAt(s) =
    thời điểm monitor gần nhất chứng kiến signature đổi

idleDuration(s) =
    now - lastProgressObservedAt(s)

suspectedStall(s) =
    status(s) == STARTED
    AND idleDuration(s) >= threshold(s)
    AND NOT approvedWaiting(s)
    AND NOT inGracePeriod(s)
```

Ở đây, “signature đổi” là **dấu hiệu công việc đã qua ranh giới cập nhật metadata**. Với step có thể chuyển pha mà không tăng counters, cần thêm phase/heartbeat riêng.

Không dùng `rollbackCount` làm tiến triển thành công: rollback cứ tăng có thể phản ánh một vòng lỗi không thoát. Tương tự, `commitCount` liên tục tăng với chunk rỗng không nhất thiết chứng minh đã tiến triển nghiệp vụ. Có thể theo dõi các counter đó riêng để bổ sung chẩn đoán.

### 6.3. Ngưỡng theo dữ liệu

Một cách linh hoạt hơn là đo throughput:

```text
throughput = ΔwriteCount / Δtime

estimatedRemainingSeconds =
    max(0, expectedItems - writeCount) / max(throughput, epsilon)
```

Công thức này chỉ có ý nghĩa nếu có `expectedItems` đáng tin cậy và dữ liệu xử lý tương đối ổn định. Với input tăng động hoặc nhiều record bị filter, ước lượng có thể sai. Không cần định nghĩa stall dựa trên throughput nếu hệ thống chưa có expected workload hợp lệ.

---

## 7. Ví dụ Java: bộ phát hiện stalled StepExecution

Ví dụ này chia **thu thập dữ liệu** và **quy tắc phát hiện** thành hai lớp. Bộ detector dùng Java thuần, dễ test, không phụ thuộc đồng hồ thực. Watchdog sử dụng Spring Batch `JobExplorer` để lấy dữ liệu đã persist.

### 7.1. Pure Java detector

Tạo file `ProgressStallDetector.java` trong package `com.example.batch.monitoring`:

```java
package com.example.batch.monitoring;

import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class ProgressStallDetector {

    // ID riêng biệt cho từng StepExecution; restart tạo execution ID khác.
    private record Key(long jobExecutionId, long stepExecutionId) {}

    // Chỉ tính các dấu hiệu tiến triển item, không tính rollback.
    private record Signature(
            long read, long write, long filtered,
            long readSkip, long processSkip, long writeSkip) {}

    public record Snapshot(
            long jobExecutionId,
            long stepExecutionId,
            String jobName,
            String stepName,
            long readCount,
            long writeCount,
            long filterCount,
            long readSkipCount,
            long processSkipCount,
            long writeSkipCount) {

        private Key key() {
            return new Key(jobExecutionId, stepExecutionId);
        }

        private Signature signature() {
            return new Signature(
                    readCount, writeCount, filterCount,
                    readSkipCount, processSkipCount, writeSkipCount);
        }
    }

    public record StallAlert(
            long jobExecutionId,
            long stepExecutionId,
            String jobName,
            String stepName,
            Instant lastProgressObservedAt,
            Duration idle) {}

    private static final class State {
        private Signature lastSignature;
        private Instant lastProgressObservedAt;
        private boolean alertEmitted;

        private State(Signature signature, Instant observedAt) {
            this.lastSignature = signature;
            this.lastProgressObservedAt = observedAt;
        }
    }

    private final Duration idleThreshold;
    private final Map<Key, State> states = new HashMap<>();

    public ProgressStallDetector(Duration idleThreshold) {
        Objects.requireNonNull(idleThreshold, "idleThreshold");
        if (idleThreshold.isNegative() || idleThreshold.isZero()) {
            throw new IllegalArgumentException(
                    "idleThreshold must be positive");
        }
        this.idleThreshold = idleThreshold;
    }

    /**
     * Truyền toàn bộ StepExecution STARTED của một lần quét thành công.
     * Timestamp được inject từ Clock ở lớp gọi để dễ kiểm thử.
     */
    public synchronized List<StallAlert> inspect(
            Collection<Snapshot> running, Instant now) {

        Objects.requireNonNull(running, "running");
        Objects.requireNonNull(now, "now");

        Set<Key> seen = new HashSet<>();
        List<StallAlert> alerts = new ArrayList<>();

        for (Snapshot current : running) {
            Key key = current.key();

            // Bỏ dữ liệu trùng trong cùng một lượt thu thập.
            if (!seen.add(key)) {
                continue;
            }

            Signature signature = current.signature();
            State state = states.get(key);

            if (state == null) {
                // Chưa quan sát lần trước: bắt đầu tính từ lần poll này.
                states.put(key, new State(signature, now));
                continue;
            }

            if (!signature.equals(state.lastSignature)) {
                // Có progress mới: xóa trạng thái alert đang giữ.
                state.lastSignature = signature;
                state.lastProgressObservedAt = now;
                state.alertEmitted = false;
                continue;
            }

            Duration idle = Duration.between(
                    state.lastProgressObservedAt, now);

            // Sự cố đồng hồ đi lùi: không phát alert giả.
            if (idle.isNegative()) {
                state.lastProgressObservedAt = now;
                continue;
            }

            if (!state.alertEmitted
                    && idle.compareTo(idleThreshold) >= 0) {
                alerts.add(new StallAlert(
                        current.jobExecutionId(),
                        current.stepExecutionId(),
                        current.jobName(),
                        current.stepName(),
                        state.lastProgressObservedAt,
                        idle));
                state.alertEmitted = true;
            }
        }

        // Dữ liệu của step đã COMPLETED/FAILED/STOPPED không còn theo dõi.
        // Chỉ gọi inspect khi lượt quét metadata THÀNH CÔNG đầy đủ.
        states.keySet().retainAll(seen);

        return List.copyOf(alerts);
    }
}
```

**Đặc điểm của detector:**

- Dùng `(jobExecutionId, stepExecutionId)` làm khóa để phân biệt restart và lần chạy mới.
- Lần quan sát đầu tiên không tự suy đoán job đã đứng im từ lúc nào; thời điểm bắt đầu đo là lúc monitor nhìn thấy dữ liệu.
- Thấy counters đổi thì đặt lại `lastProgressObservedAt` và cho phép alert trở lại nếu lần sau thực sự kẹt.
- Phát **một tín hiệu** cho một giai đoạn không tiến triển; không lặp cảnh báo mỗi lần poll.
- Khi step không còn trong danh sách running, trạng thái theo dõi bị loại bỏ. Trong sản phẩm thật, hệ thống alert nên đóng trạng thái firing/recovery tương ứng.
- Nếu query repository thất bại, **không gọi `inspect(emptyList, now)`**. Việc đó có thể xóa toàn bộ lịch sử giám sát dù các job vẫn đang chạy.

Đây là implementation phục vụ giải thích, lưu trạng thái trong RAM và sử dụng cùng một ngưỡng cho mọi step. Một monitor production có nhiều replica hoặc có yêu cầu duy trì alert qua restart phải chuyển state sang storage tập trung hoặc dựa vào heartbeat/metric được persist.

### 7.2. Watchdog đọc JobExplorer và gọi detector

Tạo file `JobProgressWatchdog.java`:

```java
package com.example.batch.monitoring;

import java.time.Clock;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.example.batch.monitoring.ProgressStallDetector.Snapshot;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
class MonitoringConfiguration {

    @Bean
    Clock monitoringClock() {
        return Clock.systemUTC();
    }

    @Bean
    ProgressStallDetector progressStallDetector() {
        return new ProgressStallDetector(Duration.ofMinutes(10));
    }
}

@Component
public class JobProgressWatchdog {

    private static final Logger log =
            LoggerFactory.getLogger(JobProgressWatchdog.class);

    private final JobExplorer explorer;
    private final ProgressStallDetector detector;
    private final Clock clock;

    // Ví dụ: production nên lấy danh sách từ cấu hình có kiểm soát.
    private final List<String> monitoredJobs =
            List.of("dailyImportJob", "settlementJob");

    public JobProgressWatchdog(
            JobExplorer explorer,
            ProgressStallDetector detector,
            Clock monitoringClock) {
        this.explorer = explorer;
        this.detector = detector;
        this.clock = monitoringClock;
    }

    @Scheduled(
        fixedDelayString = "${app.batch.monitor.poll-ms:30000}"
    )
    public void poll() {
        List<Snapshot> snapshots = new ArrayList<>();

        try {
            for (String jobName : monitoredJobs) {
                for (JobExecution job :
                        explorer.findRunningJobExecutions(jobName)) {

                    Long jobId = job.getId();
                    if (jobId == null) {
                        continue;
                    }

                    for (StepExecution step : job.getStepExecutions()) {
                        Long stepId = step.getId();

                        // Startup/stop timeout được theo dõi ở detector khác.
                        if (stepId == null
                                || step.getStatus()
                                    != BatchStatus.STARTED) {
                            continue;
                        }

                        snapshots.add(new Snapshot(
                                jobId,
                                stepId,
                                jobName,
                                step.getStepName(),
                                step.getReadCount(),
                                step.getWriteCount(),
                                step.getFilterCount(),
                                step.getReadSkipCount(),
                                step.getProcessSkipCount(),
                                step.getWriteSkipCount()));
                    }
                }
            }
        } catch (RuntimeException metadataFailure) {
            log.error("Cannot inspect Spring Batch metadata",
                    metadataFailure);
            // Cần alert riêng về monitor/repository unavailable.
            // Không xóa trạng thái detector do một lượt poll thất bại.
            return;
        }

        for (var alert : detector.inspect(
                snapshots, clock.instant())) {
            log.warn(
                    "Suspected stalled step: job={}, step={}, "
                    + "jobExecutionId={}, stepExecutionId={}, "
                    + "lastProgressObservedAt={}, idleSeconds={}",
                    alert.jobName(),
                    alert.stepName(),
                    alert.jobExecutionId(),
                    alert.stepExecutionId(),
                    alert.lastProgressObservedAt(),
                    alert.idle().toSeconds());
        }
    }
}
```

**Điểm giới hạn cần hiểu của ví dụ:**

1. `@Scheduled` tạo watchdog chạy mỗi 30 giây, nhưng trong môi trường nhiều node có thể có **nhiều watchdog cùng quét và báo trùng**. Hệ thống thật cần leader/lock hoặc dedup tại alert backend.
2. Danh sách `monitoredJobs` được cố định để ví dụ ngắn gọn; nên đưa thành cấu hình khi triển khai.
3. Khi bước đang `STARTING` hoặc job chạy mà không có step ở `STARTED`, watchdog này **không phát alert**. Cần bổ sung detector startup, stopping hoặc orphan.
4. Tasklet không cập nhật item counters sẽ bị cảnh báo sau 10 phút kể cả khi đang làm việc. Chỉ bật detector dạng counter cho các step có tiến triển theo item.
5. Cảnh báo trong đoạn code mới là **log cảnh báo**. Hệ thống gửi pager/email/ticket nên lấy sự kiện từ sink có dedup và routing, không chỉ dựa vào một dòng log.
6. Bộ detector dùng giờ UTC `Instant` của máy monitor tại thời điểm **thấy counters đổi**. Nó không cố so sánh trực tiếp `LocalDateTime lastUpdated` từ repository với giờ UTC vì có thể khác quy ước timezone.
7. Lần chạy monitor đầu tiên chỉ có thể bắt đầu đo từ khi nó nhìn thấy execution. Nếu cần phát hiện ngay một job đã treo từ trước khi monitor restart, phải có heartbeat/checkpoint timestamp bền vững.

Trong hạ tầng lớn, thiết kế có thể tách `JobExplorer reader → ProgressObservation service → Alert publisher` thành các bean riêng; ví dụ kết hợp chỉ nhằm trình bày đầy đủ đường đi dữ liệu.

---

## 8. Unit test bộ phát hiện stall với thời gian giả

Tạo file `ProgressStallDetectorTest.java`, dùng JUnit Jupiter. Test chủ động truyền các `Instant` khác nhau; không dùng `Thread.sleep` hoặc chờ job chạy thật.

```java
package com.example.batch.monitoring;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;

import com.example.batch.monitoring.ProgressStallDetector.Snapshot;

class ProgressStallDetectorTest {

    private static Snapshot sample(long read, long write) {
        return new Snapshot(
                701L, 801L,
                "dailyImportJob", "importCsvStep",
                read, write, 0L, 0L, 0L, 0L);
    }

    @Test
    void alertsOnceAfterThresholdThenRecoversOnProgress() {
        var detector =
                new ProgressStallDetector(Duration.ofMinutes(10));

        Instant t0 = Instant.parse("2026-11-16T00:00:00Z");

        assertTrue(detector.inspect(
                List.of(sample(100, 100)), t0).isEmpty());

        assertTrue(detector.inspect(
                List.of(sample(100, 100)),
                t0.plus(Duration.ofMinutes(9))).isEmpty());

        var alerts = detector.inspect(
                List.of(sample(100, 100)),
                t0.plus(Duration.ofMinutes(10)));

        assertEquals(1, alerts.size());
        assertEquals(701L, alerts.get(0).jobExecutionId());
        assertEquals(Duration.ofMinutes(10), alerts.get(0).idle());

        // Cùng lần đứng im: không spam cảnh báo.
        assertTrue(detector.inspect(
                List.of(sample(100, 100)),
                t0.plus(Duration.ofMinutes(11))).isEmpty());

        // Counter đổi: mở lại cửa sổ quan sát.
        assertTrue(detector.inspect(
                List.of(sample(150, 140)),
                t0.plus(Duration.ofMinutes(12))).isEmpty());

        assertEquals(1, detector.inspect(
                List.of(sample(150, 140)),
                t0.plus(Duration.ofMinutes(22))).size());
    }

    @Test
    void completedStepIsRemovedFromTracking() {
        var detector =
                new ProgressStallDetector(Duration.ofMinutes(5));

        Instant t0 = Instant.parse("2026-11-16T00:00:00Z");

        detector.inspect(List.of(sample(0, 0)), t0);
        detector.inspect(List.of(), t0.plusSeconds(60));

        // Đây được hiểu là một lần quan sát mới, không báo cũ.
        assertTrue(detector.inspect(
                List.of(sample(0, 0)),
                t0.plus(Duration.ofMinutes(30))).isEmpty());
    }

    @Test
    void firstObservationDoesNotClaimHistoricalStall() {
        var detector =
                new ProgressStallDetector(Duration.ofMinutes(10));

        Instant firstSeen =
                Instant.parse("2026-11-16T12:00:00Z");

        // Không có bằng chứng về counters trước lần scan này.
        assertTrue(detector.inspect(
                List.of(sample(0, 0)), firstSeen).isEmpty());
    }
}
```

Bộ test này xác nhận state machine của detector. Nó **không chứng minh** `JobExplorer` trả dữ liệu đúng hoặc watcher chạy đúng lịch; các phần đó cần integration test và test triển khai hạ tầng riêng.

### 8.1. Các kịch bản cần mở rộng khi triển khai

| Kịch bản | Điều cần xác minh |
|---|---|
| Counters tăng mỗi 3 phút, ngưỡng 10 phút | Không alert |
| Counters không tăng đủ 10 phút | Alert một lần |
| Counters tăng sau alert | Phát recovery và cho phép cảnh báo lại |
| Job chuyển `COMPLETED` hoặc `FAILED` | Đóng cảnh báo stall; phát alert trạng thái cuối nếu cần |
| Restart cùng JobInstance | StepExecution ID mới phải có cửa sổ theo dõi mới |
| Repository query lỗi một poll | Không xóa baseline, phát tín hiệu monitor failure |
| Watchdog restart | Không suy đoán thời điểm progress cũ; lấy checkpoint/heartbeat bền vững nếu có |
| Nhiều step chạy song song | Mỗi step có trạng thái, ngưỡng, alert riêng |
| Tasklet không có item counter | Dùng phase/heartbeat, tránh false positive |
| Đồng hồ host nhảy lùi | Không phát idle duration âm |
| Gặp retry loop liên tục | Không coi rollback tăng mãi là meaningful progress |
| Hai watchdog phát cùng cảnh báo | Dedupe theo khóa alert và trạng thái bền vững |

---

## 9. Heartbeat và progress event cho công việc dài

Không phải mọi batch step có counter item được update đều. Một `Tasklet` nén file 30 GB trong một phương thức `execute()` có thể thực sự tiến triển nhưng `readCount=0`, `writeCount=0` từ đầu tới cuối.

Khi đó nên chủ động ghi event:

```text
jobExecutionId = 701
stepExecutionId = 801
phase           = "compressing"
lastHeartbeatAt = 2026-11-16T02:05:00Z
lastProgressAt  = 2026-11-16T02:04:40Z
processedBytes  = 4_294_967_296
totalBytes      = 32_212_254_720
workerId        = "batch-worker-3"
```

Cần phân biệt:

- `lastHeartbeatAt`: worker vừa gửi tín hiệu còn sống.
- `lastProgressAt`: byte/record/phase hữu ích đã tăng.
- `processedBytes`: mức tiến triển định lượng.
- `phase`: công việc đang ở pha nào để chọn ngưỡng.
- `workerId`: giúp đối chiếu với log, pod/container, JVM hoặc thread dump.

### 9.1. Giao diện ghi heartbeat

Một abstraction minh họa:

```java
public interface BatchProgressReporter {

    void heartbeat(long jobExecutionId,
                   long stepExecutionId,
                   String phase,
                   Instant observedAt);

    void progress(long jobExecutionId,
                  long stepExecutionId,
                  String phase,
                  long completedUnits,
                  Instant observedAt);
}
```

Tầng triển khai có thể ghi vào một bảng giám sát riêng, Redis hoặc hệ thống event/metrics. Không tự ý ghi trực tiếp vào các bảng `BATCH_*` của framework để tạo heartbeat: việc update metadata ngoài `JobRepository` có thể phá vỡ giả định checkpoint/version và gây lỗi restart.

### 9.2. Ghi heartbeat không gây tải quá mức

Nếu xử lý 100.000 item/giây, không nên gọi network/database mỗi item chỉ để heartbeat. Có thể báo mỗi 15–30 giây, mỗi 10.000 item, mỗi chunk đã commit hoặc khi chuyển phase.

Một mẫu thiết kế hữu ích:

```text
Tasklet/Processor
     │
     ├─ mỗi N giây → heartbeat(workerAlive)
     │
     └─ sau checkpoint thành công → progress(committedUnits)
                                    │
                                    ▼
                           Durable progress store
                                    │
                                    ▼
                    Independent monitor/alert engine
```

Nếu gửi tiến triển **trước** khi transaction batch commit, event có thể nói đã xử lý 1.000 item nhưng transaction thực tế rollback. Khi cần chính xác theo nghiệp vụ, nên gắn tiến triển với checkpoint/commit thành công hoặc đặt nhãn rõ đây chỉ là `attemptedUnits`.

### 9.3. Khi heartbeat vẫn tăng nhưng progress đứng yên

Tình huống này không còn là lỗi “worker biến mất”. Cần xem:

- Nguồn dữ liệu rỗng hợp lệ hay đã bị tắc?
- Thread đang đợi network timeout hay lock database?
- `retry/backoff` có giới hạn số lần và thời gian?
- Bước hiện tại có thể tiến triển bằng phase marker khác?
- Có queue backlog hay không?
- Có deadlock/livelock hoặc vòng lặp không sinh output?

Một tín hiệu `heartbeat_age_seconds` thấp và `progress_age_seconds` cao cần có thông điệp alert khác so với **cả heartbeat lẫn progress đều mất**.

---

## 10. Xuất tín hiệu cho Prometheus và tạo quy tắc cảnh báo

Một mô hình là monitor tính các metric cấp step/job:

```text
batch_step_running{job="dailyImportJob",step="importCsvStep",env="prod"} 1
batch_step_progress_age_seconds{job="dailyImportJob",step="importCsvStep",env="prod"} 683
batch_step_heartbeat_age_seconds{job="dailyImportJob",step="importCsvStep",env="prod"} 35
batch_monitor_last_success_timestamp_seconds{env="prod"} 1794790000
```

Các tên metric trên là **custom metrics do ứng dụng tự định nghĩa**, không phải những metric built-in mặc định của Spring Batch. Khi có nhiều execution cùng job/step, phải quyết định metric tổng hợp theo min/max/quantile hoặc thiết kế series per execution với chính sách cardinality; thường không nên đưa ID từng record, đường dẫn file hay user ID vào label.

### 10.1. Ví dụ alert rule

Ví dụ Prometheus (giả định collector đã xuất các metric custom với label như trên):

```yaml
groups:
  - name: spring-batch-progress
    rules:
      - alert: SpringBatchStepNoProgress
        expr: |
          (batch_step_progress_age_seconds{env="prod"} > 600)
          and on (job, step, env)
          (batch_step_running{env="prod"} == 1)
        for: 2m
        labels:
          severity: warning
          service: spring-batch
        annotations:
          summary: "Spring Batch step không tiến triển"
          description: >
            Job {{ $labels.job }}, step {{ $labels.step }}
            không có progress trên 10 phút.

      - alert: SpringBatchMonitorNotReporting
        expr: |
          absent(batch_monitor_last_success_timestamp_seconds{env="prod"})
          or
          (time() - batch_monitor_last_success_timestamp_seconds{env="prod"} > 120)
        for: 2m
        labels:
          severity: critical
          service: spring-batch
        annotations:
          summary: "Không nhận được tín hiệu monitor batch"
```

Đây là cấu hình **minh họa**: exporter phải thật sự cung cấp các series, và cần kiểm tra cách aggregate khi nhiều pod/job execution cùng xuất metric.

Lưu ý vận hành:

- `for: 2m` yêu cầu biểu thức tiếp tục đúng trong một khoảng thời gian mới firing.
- Cần xử lý riêng trường hợp **metric biến mất** vì process/exporter chết; Prometheus không tự coi metric mất là `0` hoặc “mọi step đều khỏe”.
- Nếu chỉ export `batch_step_running=1` khi job đang chạy và không có series khi job kết thúc, alert phải có recovery semantics phù hợp.
- Nếu collector mất kết nối DB, metric progress có thể đứng yên như job stall. Cần quan sát `monitor_last_success` hoặc `monitor_scrape_success` để tránh đưa ra kết luận sai.
- Label quá chi tiết tạo số lượng time series lớn; giữ label ổn định như job name, step name, environment, cluster. ID execution nên nằm trong alert context/event store để tìm sự cố cụ thể.

### 10.2. Chọn nơi giữ trạng thái

| Cơ chế | Ưu điểm | Giới hạn |
|---|---|---|
| HashMap trong watchdog | Dễ viết, unit test nhanh | Mất state khi restart, không hợp nhiều replica |
| Prometheus time series | Tính rate, lag, `for`, dashboard dễ | Mất series hoặc scrape failure cần rule riêng; không luôn giữ ID execution |
| Database progress/heartbeat | Lưu lịch sử và tìm execution chính xác | Chi phí ghi/đọc, cần TTL/cleanup và schema |
| Redis/kv có TTL | Đọc/ghi heartbeat nhanh, TTL hữu ích | Cần thiết kế durability và trạng thái alert |
| Central event stream | Hợp cho giám sát nhiều job, nhiều hệ thống | Cần consumer, late event và dedup |

Không có công cụ nào thay thế việc xác định **progress semantics** cho từng step. Một bộ metric đẹp nhưng chỉ có số CPU/RAM không thể tự kết luận job đã hoàn thành checkpoint nghiệp vụ.

---

## 11. Thiết kế alert chống spam và ưu tiên hành động

Một alert hữu ích phải cho người trực biết **công việc nào, tiến triển đứng ở đâu, bị ảnh hưởng bao lâu, có cần hành động ngay không**.

Thông tin sự kiện nên gồm:

```json
{
  "type": "SPRING_BATCH_STEP_STALLED",
  "severity": "warning",
  "environment": "prod",
  "jobName": "dailyImportJob",
  "jobInstanceId": 5301,
  "jobExecutionId": 7012,
  "stepName": "importCsvStep",
  "stepExecutionId": 8022,
  "status": "STARTED",
  "lastProgressObservedAt": "2026-11-16T02:15:00Z",
  "observedAt": "2026-11-16T02:28:00Z",
  "idleSeconds": 780,
  "thresholdSeconds": 600,
  "readCount": 150000,
  "writeCount": 149998,
  "filterCount": 2,
  "runbook": "https://internal.example/runbooks/batch-stalled"
}
```

Đây là dữ liệu minh họa. Nếu cung cấp link runbook, cần dùng địa chỉ nội bộ thật của tổ chức khi triển khai. Không ghi token, nội dung item nhạy cảm hoặc thông tin đăng nhập vào alert.

**Khóa dedup** thường gồm:

```text
environment + jobExecutionId + stepExecutionId + alertType
```

Ví dụ cùng execution stuck 30 phút thì alert một lần và nâng severity sau ngưỡng thứ hai; không gửi 60 email khi poll mỗi 30 giây.

### 11.1. Mức độ ưu tiên

| Tình huống | Hướng xử lý mức ưu tiên |
|---|---|
| Step không tiến triển 10 phút nhưng SLA còn 6 giờ | Warning, điều tra trong giờ làm việc |
| Step không tiến triển 20 phút, deadline 10 phút nữa | Critical hoặc page trực ca |
| Nhiều job cùng stall do database chung | Gộp theo dependency sự cố, tránh hàng loạt alert trùng |
| Job healthy trở lại | Phát recovery, đóng incident hoặc cập nhật timeline |
| Có maintenance window được phê duyệt | Silence tạm thời có thời hạn, vẫn lưu dữ liệu quan sát |
| Monitor không lấy được metadata | Alert monitor/data source failure riêng |

Severity cần gắn **tác động nghiệp vụ**, không chỉ elapsed time. Job chậm mà deadline còn xa có thể warning; cùng job đó sát kỳ đối soát hoặc ảnh hưởng khách hàng có thể critical.

### 11.2. Cooldown và escalation

Một state machine vận hành:

```text
HEALTHY
   │ không progress đủ ngưỡng
   ▼
SUSPECTED
   │ điều kiện vẫn kéo dài
   ▼
FIRING
   │ thêm thời gian hoặc gần SLA
   ▼
ESCALATED
   │ progress tăng trở lại / execution kết thúc
   ▼
RESOLVED
```

Một job chuyển `FAILED` trong lúc đang firing stall nên đóng alert stall và chuyển sang alert failure với thông tin liên kết. Tránh để hai cảnh báo tiếp tục cùng bắn sau khi incident đã chuyển trạng thái.

### 11.3. Missing schedule không phải stalled

Nếu cần chạy trước 02:30 mỗi ngày, nhưng không có `JobExecution` cho `businessDate` tương ứng, truy vấn running executions sẽ trả rỗng và bộ detector ở trên sẽ không báo gì. Đó là lỗi **job không được khởi chạy**.

Cần có bộ kiểm tra độc lập dựa trên lịch dự kiến, timezone nghiệp vụ, dữ liệu `JobInstance`/`JobExecution` và thời điểm deadline. Điều này đặc biệt quan trọng khi scheduler chạy trong cùng JVM đã chết trước giờ kích hoạt.

---

## 12. Runbook: xử lý alert step không tiến triển

Một cảnh báo stalled nên dẫn tới quy trình chẩn đoán có thứ tự, không tự động restart ngay.

### Bước 1 — Xác nhận sự cố

Ghi lại:

- `jobName`, `jobExecutionId`, `stepExecutionId` và `businessDate`.
- Trạng thái hiện tại trong `JobExplorer` và mốc `lastUpdated`/`startTime`.
- Counters trong hai hoặc nhiều lần quan sát, xem có thay đổi hay không.
- Ngưỡng stall của step và deadline/SLA liên quan.
- Thông tin triển khai: pod/host/worker/thread.

Kiểm tra xem monitor có đọc đúng database, schema, cluster và environment hay không. Một read replica chậm có thể khiến metadata bị stale trong khi job đang tiến triển ở primary.

### Bước 2 — Xem tín hiệu thực thi

Nếu execution vẫn `STARTED`:

- Worker/pod/JVM có còn sống không?
- CPU, memory, GC pause, thread dump có dấu hiệu deadlock hay busy loop không?
- Database có lock, connection pool saturation, deadlock hoặc slow query không?
- Network/API ngoài có timeout, retry storm, rate limit hoặc dịch vụ lỗi không?
- Source queue còn dữ liệu không? Consumer có bị backpressure hoặc đứng chờ hợp lệ không?
- File output có được flush/publish đúng phase không?
- Với partitioned step, có worker riêng lẻ bị kẹt trong khi tổng thể vẫn tăng không?

### Bước 3 — Phân loại nguyên nhân

| Nhóm nguyên nhân | Dấu hiệu | Thao tác điều tra |
|---|---|---|
| Reader bị chặn | Không có item mới, thread chờ I/O | Xem network timeout, DB cursor, source server |
| Processor lặp hoặc deadlock | CPU cao bất thường hoặc thread blocked | Thread dump, flame graph, code path, lock |
| Writer kẹt | Đọc xong chunk, write/commit không tiến triển | DB locks, storage full, remote API, transaction timeout |
| Retry không thoát | Rollback/retry tăng, output đứng yên | Kiểm tra backoff, retry limit, loại exception |
| Worker chết | Metadata còn `STARTED` nhưng không có process | So sánh infrastructure state và repository |
| False positive do chunk dài | Thread vẫn làm việc, counters chưa commit | Tăng độ tin cậy bằng heartbeat/phase hoặc đổi threshold |
| Chờ nguồn dữ liệu hợp lệ | Input hiện rỗng, đang poll đúng chính sách | Chuyển sang alert lag/deadline thay vì stall |

### Bước 4 — Quyết định khắc phục

- Nếu dependency bị lỗi, ưu tiên khắc phục dependency và chờ job phục hồi nếu thiết kế có retry an toàn.
- Nếu job vẫn đang chạy nhưng không hiệu quả, xem xét yêu cầu dừng **qua cơ chế điều khiển chuẩn** (như `JobOperator`) và theo dõi quá trình dừng; stop thường là yêu cầu hợp tác, không phải kill tức thời.
- Nếu worker đã chết, xác định metadata, transaction và checkpoint trước khi restart.
- Khi restart, sử dụng đúng `JobInstance`/`JobParameters` của kỳ dữ liệu cần xử lý, và đối soát output để tránh tạo side effect trùng.
- Nếu job không restartable hoặc output đã phát hành một phần, cần quy trình recovery/reprocess riêng.

**Không tự chỉnh `BATCH_JOB_EXECUTION.STATUS` hoặc `BATCH_STEP_EXECUTION.STATUS` bằng SQL chỉ để xóa alert.** Việc đó có thể làm repository và restart semantics không còn nhất quán. Việc can thiệp metadata thủ công chỉ nên xảy ra trong một quy trình vận hành chuyên biệt có hiểu rõ tác động.

### Bước 5 — Đóng sự cố và phòng ngừa

Sau khi job phục hồi hoặc kết thúc:

- Xác minh số lượng input/output, checkpoint và kết quả nghiệp vụ.
- Đóng alert stall, ghi nhận nguyên nhân và thời điểm khắc phục.
- Xem có kỳ dữ liệu tiếp theo đã bị lỡ hay chưa.
- Nếu ngưỡng tạo false positive, sửa ngưỡng theo phân tích workload chứ không tắt monitoring hoàn toàn.
- Thêm timeout, retry limit, circuit breaker, heartbeat đúng phase hoặc dashboard phụ trợ nếu cần.

---

## 13. Những trường hợp khó trong Spring Batch

### 13.1. Step có chunk rất dài

Trong chunk-oriented processing, `StepExecution` có thể chỉ được cập nhật khi hoàn tất một chunk/transaction. Một chunk cần 20 phút là thiết kế hợp lệ trong một số tác vụ, nhưng timeout stall 5 phút trên counter sẽ sai.

Hướng xử lý:

- Giảm kích thước chunk nếu phù hợp throughput/transaction.
- Giới hạn timeout với nguồn ngoài.
- Dùng progress event trong phase xử lý dài, phân biệt attempted và committed.
- Chọn threshold lớn hơn worst-case chunk bình thường.
- Với bước có SLA nghiêm ngặt, theo dõi thời gian của **một item/chunk đang chạy**, không chỉ counter tổng.

### 13.2. Step chỉ filter dữ liệu

Một processor có thể trả `null` cho nhiều record để loại bỏ chúng theo hợp đồng. Khi đó `writeCount` không tăng nhưng `readCount` và `filterCount` có thể tăng. Nếu detector chỉ dựa vào output count, nó sẽ báo false positive.

Dùng nhiều counters theo đúng semantics; kiểm tra filter ratio riêng nếu tỷ lệ lọc cao là bất thường.

### 13.3. Multi-threaded/partitioned step

Một bước master có thể đang tiến triển vì vài partition, trong khi một partition mắc kẹt vĩnh viễn. Nếu chỉ nhìn counter tổng, phần khỏe sẽ che phần lỗi.

Cần quan sát ở cấp **partition/worker StepExecution**. Khóa định danh và threshold nên tính riêng, sau đó tổng hợp kết quả cho job. Nếu một partition mắc kẹt làm job không thể hoàn tất, incident nên chỉ ra partition ID và nơi chạy worker.

### 13.4. Long-running Tasklet

`Tasklet` không nhất thiết có `readCount`/`writeCount`. Không mặc định tasklet bị stalled vì các counter bằng 0. Sử dụng phase marker, total units, heartbeat hoặc timeout của lời gọi ngoài. Nếu tác vụ chạy trong một lời gọi chặn không thể report, cần timeout/cancellation của dependency hoặc quan sát từ thread/process.

### 13.5. Retry storm

Một step liên tục rollback có thể vẫn cập nhật metadata. Nếu coi `lastUpdated` là progress, detector sẽ bỏ qua sự cố. Ngược lại, chỉ dùng counters hữu ích sẽ phát hiện “không tạo output”, nhưng cần thêm chỉ báo retry count, lỗi điển hình và backoff để chẩn đoán nguyên nhân.

### 13.6. Execution vẫn STARTED sau khi JVM chết

Một JVM bị kill/host mất điện có thể không cập nhật được trạng thái cuối. `JobExplorer.findRunningJobExecutions` dựa trên metadata và có thể trả về execution đó.

Để xác định “orphan”:

1. Kiểm tra worker/container có còn hoạt động không.
2. Đối chiếu heartbeat timestamp và trạng thái deploy.
3. Kiểm tra `lastUpdated` và commit cuối.
4. Tách alert orphan khỏi stall do tiến trình còn sống.
5. Xử lý recovery theo quy trình restart được hỗ trợ, không sửa metadata tùy tiện.

### 13.7. Job dùng hệ thống bên ngoài không giao dịch cùng DB

Một writer gọi REST, gửi message hoặc ghi object storage có thể tạo side effect trước khi metadata chunk được commit. Sau khi restart, một phần thao tác có thể bị lặp.

Do đó, trước khi tự động restart vì stall, cần biết cơ chế idempotency ở hệ thống đích, transaction boundary, outbox hoặc key chống trùng. Giám sát **không thể bảo đảm exactly-once** chỉ dựa vào trạng thái `JobRepository`.

---

## 14. Thiết kế kiểm thử tích hợp và thử sự cố

Bộ unit test của detector là cần thiết nhưng chưa đủ. Một hệ thống thực phải chứng minh tín hiệu đang lấy đúng từ `JobRepository` và alert backend.

### 14.1. Test metadata thật

Với `spring-batch-test`, viết integration test khởi chạy step có checkpoint, rồi dùng `JobExplorer` kiểm tra `JobExecution`/`StepExecution`. Có thể tạo fixture 5–10 item và bật processor có delay/lỗi có kiểm soát.

Các assertion nên kiểm tra:

- Step ở trạng thái `STARTED` trong lúc đang thực thi.
- Counters từ `JobExplorer` thay đổi sau những commit thành công.
- Không phát alert trước ngưỡng.
- Khi đóng băng tiến triển qua test hook, detector phát alert sau ngưỡng.
- Sau khi job hoàn tất, alert được resolve và không còn coi là running.
- Khi repository query hỏng, phát monitor failure thay vì báo stall giả.

Không nhất thiết cho test ngủ 10 phút: inject `Clock` hoặc truyền `Instant` để kiểm tra state machine; phần integration test chỉ cần xác nhận cách chuyển metadata thành snapshot.

### 14.2. Test worker chết

Trên môi trường test cô lập:

1. Khởi chạy một job test được phép dừng ở một checkpoint xác định.
2. Dừng đột ngột worker/container theo kịch bản đã thiết kế.
3. Quan sát `JobExplorer` và heartbeat store.
4. Xác nhận bộ giám sát phát hiện sự chênh lệch giữa metadata và worker liveness.
5. Chạy recovery và kiểm tra output không trùng/mất.

Không dùng cơ sở dữ liệu production hoặc job có tác động thật cho thí nghiệm này.

### 14.3. Test mất mạng/DB

Giả lập một khoảng thời gian monitor không đọc được repository:

- Không xóa baseline của những execution đang được theo dõi.
- Ghi rõ lỗi quan sát và tạo alert monitoring unavailable.
- Khi kết nối phục hồi, reconciliate state.
- Không kết luận job đã `COMPLETED` chỉ vì danh sách running rỗng do query lỗi.

### 14.4. Test không có dữ liệu nguồn

Nếu nguồn hàng đợi hợp lệ rỗng trong một giờ và job dự kiến polling:

- Heartbeat vẫn tăng.
- Lag/backlog có thể bằng 0.
- Không phát stalled theo tín hiệu “không có item” nếu chờ rỗng là hành vi đúng.
- Nếu nghiệp vụ kỳ vọng một tệp phải xuất hiện trước deadline, phát **missing input/SLA alert** thay vì stall.

### 14.5. Test restart và duplicate alert

Sau khi restart job:

- `JobExecutionId` và `StepExecutionId` có thể thay đổi.
- Dữ liệu tiến triển được theo dõi ở execution mới, không gán nhầm trạng thái stall cũ.
- Alert cũ phải được resolve/đóng đúng lúc.
- Nếu restart thất bại, alert failure riêng cần dẫn tới execution mới và liên kết incident cũ.

---

## 15. Triển khai production: độ tin cậy của chính hệ thống alert

Cơ chế phát hiện stalled job cũng là một thành phần vận hành quan trọng. Những yêu cầu dưới đây giúp tránh cảnh báo giả và bỏ sót sự cố.

| Vấn đề | Rủi ro | Biện pháp |
|---|---|---|
| Monitor chạy cùng process batch | JVM chết thì monitor cũng chết | Giám sát độc lập, health/missing heartbeat |
| Monitor nhiều replica | Gửi cảnh báo trùng | Leader election, lock hoặc dedup tại alert backend |
| Repository đọc từ replica trễ | Counters không cập nhật kịp | Theo dõi replication lag, điều chỉnh ngưỡng hoặc đọc primary khi cần |
| Metadata store quá tải | Monitoring làm batch chậm hơn | Giới hạn poll frequency, query chọn lọc, không nạp mọi execution context |
| Clock giữa các node lệch | Idle duration sai | Đồng bộ NTP, tính elapsed tại monitor và giữ dấu thời gian UTC rõ ràng |
| Poll bị trễ do GC/network | False positive | Grace/confirmation và đo sức khỏe monitor |
| Time series high-cardinality | Tốn memory và chi phí observability | Dùng tag job/step/environment ổn định, ID trong event context |
| Process crash xóa trạng thái in-memory | Mất baseline hoặc alert | Progress store bền vững hoặc metric history |
| Thời gian commit dao động | False positive | Ngưỡng theo step và checkpoint/heartbeat phù hợp |
| Không có runbook | Alert khó hành động | Gắn jobExecutionId, dashboard, log link, hướng khắc phục |
| Auto restart không an toàn | Trùng dữ liệu, side effects | Phân loại, phê duyệt hoặc kiểm tra idempotency/restart policy |

### 15.1. Security và dữ liệu nhạy cảm

Trong alert, chỉ nên đưa những thông tin cần thiết để xử lý:

- Job name, step name, execution IDs, environment, thời gian, counters.
- Severity, threshold, trạng thái và link tới dashboard nội bộ.
- Mã lỗi đã được chuẩn hóa hoặc hash dữ liệu khi cần.

Không đưa toàn bộ `JobParameters`, `ExecutionContext`, payload input, stack trace chứa secret hoặc đường dẫn nhạy cảm vào kênh thông báo rộng. Quyền đọc metadata nên giới hạn theo nhóm vận hành.

### 15.2. Những chỉ số để đánh giá hệ thống cảnh báo

- **Time to detect:** từ lúc thực sự không có tiến triển đến lúc alert firing.
- **False positive rate:** tỷ lệ alert nhưng job vẫn đang hoạt động theo chính sách.
- **Coverage:** bao nhiêu job/step quan trọng đã có progress signal và threshold.
- **Time to acknowledge / resolve:** thời gian trực ca phản hồi và khắc phục.
- **Missing monitoring duration:** thời gian không thu được dữ liệu vì monitor lỗi.
- **Alert noise:** số alert lặp cho cùng incident.

Không tối ưu chỉ một mục tiêu “alert sớm nhất”: ngưỡng quá thấp làm mất niềm tin ở hệ thống, còn ngưỡng quá cao bỏ lỡ SLA.

---

## 16. Bài tập thực hành

### Bài 1 — Xác định tín hiệu

Cho `StepExecution` có `readCount=1000`, `writeCount=0`, `filterCount=1000`. Giải thích vì sao chỉ theo dõi `writeCount` sẽ báo stalled sai. Nêu bộ counter nên theo dõi.

### Bài 2 — Ngưỡng theo chunk

Job import dùng `chunk(500)`, một chunk chậm nhất 4 phút, poll mỗi 30 giây. Đề xuất threshold và confirmation period, sau đó giải thích cách thay đổi khi chunk đôi khi mất 12 phút.

### Bài 3 — Cài detector

Dựa vào `ProgressStallDetector` trong bài, mở rộng để hỗ trợ ngưỡng riêng cho từng `(jobName, stepName)`, có startup grace và recovery event. Viết test ngưỡng, tiến triển trở lại và restart execution.

### Bài 4 — Tasklet không có item

Tạo một `Tasklet` nén tệp và báo `processedBytes` mỗi 15 giây. Thiết kế hai alert:

- Worker heartbeat mất trên 2 phút.
- Heartbeat vẫn có nhưng `processedBytes` không tăng trong 10 phút.

### Bài 5 — Quan sát với Micrometer

Bật Spring Boot Actuator và Prometheus registry trong môi trường thử nghiệm. Kiểm tra series thực sự của `spring.batch.step.active` và thêm custom metric `batch_step_progress_age_seconds`. Viết alert rule với `for` để giảm cảnh báo giả.

### Bài 6 — Worker bị kill

Khởi chạy một job test, kill worker khi đang chạy, rồi truy vấn `JobExplorer.findRunningJobExecutions(jobName)`. Giải thích vì sao `STARTED` trong repository chưa đủ chứng minh process còn sống và liệt kê bước recovery an toàn.

### Bài 7 — Missing schedule

Job đối soát phải có execution cho `businessDate` hôm trước trước 03:00 theo giờ Việt Nam. Thiết kế detector phát alert nếu **không có execution phù hợp** dù không có job `STARTED` nào. So sánh loại alert này với stalled.

### Bài 8 — Runbook và dedup

Tạo payload cảnh báo gồm job/step IDs, last progress time và counters. Thiết kế dedup key, escalation khi gần SLA, recovery khi progress tăng và hành động khi job chuyển `FAILED`.

---

## 17. Tài liệu tham khảo

- [Spring Batch 5.2 — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/5.2/monitoring-and-metrics.html): các metric Micrometer mặc định và ý nghĩa.
- [Spring Batch 5.2 — Domain Language](https://docs.spring.io/spring-batch/reference/5.2/domain.html): `JobExecution`, `StepExecution` và các counters.
- [Spring Batch 5.2 — JobExplorer Javadoc](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/explore/JobExplorer.html): đọc execution đang chạy và metadata lịch sử.
- [Spring Batch 5.2 — StepExecution Javadoc](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/StepExecution.html): read/write/skip/commit/rollback, status và `lastUpdated`.
- [Spring Batch — Observability (các phiên bản mới)](https://docs.spring.io/spring-batch/reference/spring-batch-observability/micrometer.html): `ObservationRegistry` và các thay đổi cấu hình khi dùng Spring Batch 6.x.
- [Spring Boot — Production-ready Monitoring](https://docs.spring.io/spring-boot/reference/actuator/index.html): Actuator, endpoint metrics, quan sát ứng dụng.
- [Prometheus — Alerting Rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/): biểu thức, `for`, labels và annotations.
- [Prometheus — Alertmanager](https://prometheus.io/docs/alerting/latest/alertmanager/): grouping, deduplication, routing và silences.

Một cảnh báo “job không tiến triển” chỉ đáng tin khi được xây trên **định nghĩa tiến triển cụ thể của step**. `JobExplorer` và các counter trong repository là điểm khởi đầu hữu ích, nhưng job có chunk dài, tasklet, retry, input rỗng hoặc worker chết cần thêm heartbeat, tín hiệu nguồn và trạng thái hạ tầng. Ghép các bằng chứng đó với ngưỡng được hiệu chỉnh, cơ chế khử trùng lặp, alert khi thiếu lịch và runbook sẽ giúp phát hiện sự cố sớm mà vẫn giữ được tính an toàn của dữ liệu khi khắc phục.
