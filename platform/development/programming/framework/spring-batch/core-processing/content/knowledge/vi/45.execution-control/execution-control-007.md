# JobExplorer đọc metadata trong Spring Batch

## 1. Mục tiêu của bài học

Khi chạy batch trong môi trường thực tế, người vận hành cần biết **job nào đã chạy, lần chạy nào thất bại, step nào xử lý bao nhiêu bản ghi, job có đang chạy không và một job đã từng được restart bao nhiêu lần**. Những thông tin này không nằm trong đối tượng `Job` cấu hình nghiệp vụ mà nằm trong **metadata thực thi** do Spring Batch lưu và quản lý.

`JobExplorer` là API dành cho nhu cầu **đọc metadata** của các `JobInstance`, `JobExecution` và `StepExecution`. Trong nhóm kiến thức *Execution control* của module *Spring Batch Core Processing*, hiểu `JobExplorer` là nền tảng để xây dựng trang lịch sử chạy batch, API kiểm tra trạng thái, công cụ tra cứu sự cố và logic giám sát.

Sau bài này, bạn có thể:

- Phân biệt `Job`, `JobInstance`, `JobExecution`, `StepExecution` và các `ExecutionContext`.
- Truy vấn metadata qua các phương thức thường dùng của `JobExplorer`.
- Lấy danh sách lần chạy theo tên job, xem chi tiết một execution và các bộ đếm xử lý của từng step.
- Phân trang lịch sử, xem trạng thái chạy, phát hiện trường hợp metadata bị cũ và xử lý ID không tồn tại.
- Sử dụng `JobExplorer` trong Spring Boot, viết service/REST endpoint chỉ đọc và kiểm thử bằng repository thật.
- Hiểu ranh giới giữa **đọc metadata** và **điều khiển job** để chọn đúng API.

**Phiên bản cho mã ví dụ:** Java 17+, Spring Boot 3.x và Spring Batch 5.2.x. Ở Spring Batch 6.x, một số package và API metadata có thay đổi; mục cuối nêu cách kiểm tra khi nâng cấp.

---

## 2. Phân biệt Job, JobInstance, JobExecution và StepExecution

Trước khi gọi `JobExplorer`, cần hiểu bản chất của từng đối tượng metadata.

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| `Job` | Định nghĩa quy trình batch, gồm các step và luồng thực thi | `dailyInvoiceJob` |
| `JobParameters` | Tham số của một lần yêu cầu chạy job; tham số có thể được đánh dấu identifying hoặc non-identifying | `businessDate=2026-11-16`, `inputFile=...` |
| `JobInstance` | Một **định danh logic** của job, được quyết định bởi tên job và các **identifying JobParameters** | `dailyInvoiceJob` cho ngày nghiệp vụ `2026-11-16` |
| `JobExecution` | Một lần thử thực thi cụ thể của `JobInstance` | Chạy lần đầu thất bại, lần sau restart thành công |
| `StepExecution` | Bản ghi thực thi của một step trong một `JobExecution` | `invoiceStep` đọc 1.000 item, ghi 998 item |
| `ExecutionContext` | Dữ liệu trạng thái được lưu ở cấp job/step, thường dùng để tiếp tục hoặc chia sẻ trạng thái | Vị trí dòng đã đọc, khóa phân trang, cờ xử lý |
| `BatchStatus` | Trạng thái kỹ thuật của job/step | `STARTED`, `COMPLETED`, `FAILED` |
| `ExitStatus` | Mã kết quả giúp mô tả điều kiện kết thúc và điều hướng flow | `COMPLETED`, `FAILED` hoặc mã tùy chỉnh |

### Ví dụ một JobInstance có nhiều JobExecution

Giả sử `dailyInvoiceJob` xử lý `businessDate=2026-11-16`, và `businessDate` là identifying parameter:

```text
Job: dailyInvoiceJob
│
├── JobInstance #42
│   Identifying parameters: businessDate=2026-11-16
│   │
│   ├── JobExecution #7001  → FAILED
│   │   ├── StepExecution #8001: readInvoices  → COMPLETED
│   │   └── StepExecution #8002: exportInvoices → FAILED
│   │
│   └── JobExecution #7002  → COMPLETED   (restart)
│       └── StepExecution #8003: exportInvoices → COMPLETED
│
└── JobInstance #43
    Identifying parameters: businessDate=2026-11-17
    │
    └── JobExecution #7003  → COMPLETED
        ├── StepExecution #8004: readInvoices   → COMPLETED
        └── StepExecution #8005: exportInvoices → COMPLETED
```

Điều cần nhớ:

1. **Một JobInstance có thể có nhiều JobExecution.** Khi một lần thực thi thất bại và được restart hợp lệ, hệ thống tạo một `JobExecution` khác cho **cùng** `JobInstance`.
2. **Không phải mọi `JobParameters` đều xác định JobInstance.** Chỉ các tham số identifying mới tham gia nhận dạng instance. Non-identifying parameters vẫn có thể lưu trong lần chạy nhưng không tạo định danh logic mới.
3. **Một JobExecution có nhiều StepExecution.** Không phải mọi step đều xuất hiện ở mọi lần restart vì step đã hoàn tất có thể được bỏ qua theo cấu hình.
4. **JobExecution ID khác JobInstance ID.** Không dùng nhầm khi tìm detail hoặc khi truyền cho hệ thống vận hành.
5. `JobExplorer` đọc lại các đối tượng đã lưu, không trả về cùng Java object đang sống trong luồng xử lý.

Ví dụ trên có ba `JobExecution` nhưng chỉ hai `JobInstance`. Đây là lý do số instance, số lần chạy và số lần restart phải được hiểu riêng.

---

## 3. Metadata được lưu ở đâu?

Với JDBC `JobRepository` trong Spring Batch 5.x, metadata thường nằm ở các bảng có tiền tố mặc định `BATCH_`.

| Bảng | Nội dung chính |
|---|---|
| `BATCH_JOB_INSTANCE` | ID instance, tên job, key xác định instance |
| `BATCH_JOB_EXECUTION` | ID execution, instance tương ứng, trạng thái, thời điểm bắt đầu/kết thúc, exit code |
| `BATCH_JOB_EXECUTION_PARAMS` | Các JobParameters gắn với execution |
| `BATCH_STEP_EXECUTION` | Trạng thái, thời gian và các bộ đếm read/write/skip/commit/rollback cho từng step |
| `BATCH_JOB_EXECUTION_CONTEXT` | ExecutionContext cấp job đã được serialize |
| `BATCH_STEP_EXECUTION_CONTEXT` | ExecutionContext cấp step đã được serialize |
| Bảng sequence hỗ trợ ID | Cấp khóa chính tùy cơ chế database và schema Spring Batch |

Quan hệ logic:

```text
BATCH_JOB_INSTANCE
      │ 1
      │
      ▼ N
BATCH_JOB_EXECUTION ─────────────── BATCH_JOB_EXECUTION_PARAMS
      │                  1 ─── N
      │ 1
      ├──────────────────────────── BATCH_JOB_EXECUTION_CONTEXT
      │
      ▼ N
BATCH_STEP_EXECUTION
      │ 1
      ▼ 1
BATCH_STEP_EXECUTION_CONTEXT
```

`JobRepository` là thành phần ghi/cập nhật metadata trong vòng đời job và step. `JobExplorer` sử dụng các cấu trúc này để truy vấn lịch sử, kể cả khi phiên bản Java object khi chạy đã không còn trong bộ nhớ.

**Không nên truy vấn SQL trực tiếp cho mọi màn hình lịch sử** nếu `JobExplorer` đã cung cấp API phù hợp. API giúp ứng dụng không phải tự ánh xạ nhiều bảng, giải mã execution context và đồng bộ theo thay đổi của framework. Tuy nhiên, dashboard cần các truy vấn tổng hợp lớn vẫn có thể chọn một hệ thống phân tích/metric riêng nếu tải truy vấn vượt khả năng thiết kế của `JobExplorer`.

### Metadata không phải dữ liệu nghiệp vụ

Một `StepExecution` ghi `writeCount=998` chỉ nói rằng step đã ghi 998 item theo cách Spring Batch đếm; nó không chứng minh 998 invoice đã được đối soát, phát hành, gửi đi hoặc có trạng thái đúng trong hệ thống đích. Muốn xác nhận kết quả nghiệp vụ, cần đối chiếu output/database hay log chuyên dụng tương ứng.

---

## 4. JobExplorer khác JobRepository, JobLauncher và JobOperator như thế nào?

| Thành phần | Trách nhiệm chủ yếu | Loại thao tác |
|---|---|---|
| `JobExplorer` | Tra cứu các job/step execution đang chạy hoặc đã lưu lịch sử | Đọc metadata |
| `JobRepository` | Tạo, lưu và cập nhật metadata của Spring Batch | Ghi/quản lý trạng thái nền tảng |
| `JobLauncher` | Yêu cầu chạy một `Job` với `JobParameters` | Khởi chạy |
| `JobOperator` | API vận hành cấp cao như tìm, chạy, dừng, restart tùy phiên bản | Điều khiển và giám sát |
| `JobRegistry` | Quản lý các định nghĩa `Job` đang được đăng ký trong application context | Tra cứu job definition |

Ví dụ thao tác:

```java
// Đọc metadata (không khởi chạy job)
JobExecution execution = jobExplorer.getJobExecution(7001L);

// Khởi chạy job: thao tác khác, dùng một API khác
JobExecution launched = jobLauncher.run(dailyInvoiceJob, parameters);

// Dừng job: cần JobOperator, không phải JobExplorer
boolean stopRequested = jobOperator.stop(7002L);
```

Lời gọi `stop` là ví dụ minh họa API quản trị Spring Batch 5.x. Không dùng nó chỉ để “đánh dấu kết thúc” một execution bị treo: yêu cầu dừng bình thường cần tiến trình batch còn hoạt động để phản hồi.

**Ranh giới quan trọng:** `JobExplorer` không restart, không stop, không sửa `BatchStatus` và không ghi `ExecutionContext` vào repository. Nếu ứng dụng có trang quản trị, có thể xây dựng phần **xem lịch sử** bằng `JobExplorer`, còn các hành động thay đổi trạng thái cần luồng ủy quyền riêng qua `JobOperator` hoặc service điều phối đã kiểm soát quyền.

---

## 5. Các API đọc metadata của JobExplorer

Trong Spring Batch 5.2.x, interface:

```java
import org.springframework.batch.core.explore.JobExplorer;
```

Các phương thức thiết yếu:

| Phương thức | Kết quả | Tình huống sử dụng |
|---|---|---|
| `getJobNames()` | `List<String>` | Danh sách tên job từng có instance trong repository |
| `getJobInstanceCount(jobName)` | `long` | Tổng instance của job phục vụ phân trang |
| `getJobInstances(jobName, start, count)` | `List<JobInstance>` | Danh sách instance, mới hơn trước, theo offset |
| `findJobInstancesByJobName(jobName, start, count)` | `List<JobInstance>` | Tìm tên job theo tiêu chí tương tự LIKE/wildcard |
| `getLastJobInstance(jobName)` | `JobInstance` hoặc `null` | Instance mới nhất theo ID |
| `getJobInstance(instanceId)` | `JobInstance` hoặc `null` | Tra một instance bằng ID |
| `getJobInstance(jobName, jobParameters)` | `JobInstance` hoặc `null` | Tra instance xác định bởi tên và identifying parameters |
| `getJobExecutions(jobInstance)` | `List<JobExecution>` | Lịch sử các lần thử chạy của cùng một instance |
| `getLastJobExecution(jobInstance)` | `JobExecution` hoặc `null` | Lần thực thi mới nhất của instance |
| `getJobExecution(executionId)` | `JobExecution` hoặc `null` | Chi tiết một lần chạy bằng execution ID |
| `getStepExecution(jobExecutionId, stepExecutionId)` | `StepExecution` hoặc `null` | Chi tiết step và context tương ứng |
| `findRunningJobExecutions(jobName)` | `Set<JobExecution>` | Các lần thực thi được ghi nhận đang chạy cho job |

Các điểm cần chú ý:

- `start` trong `getJobInstances` là **offset bắt đầu từ 0**, `count` là kích thước trang, không phải ID hoặc số trang.
- Kết quả của `getJobInstances` được sắp theo thứ tự instance mới hơn trước, dựa trên thứ tự tạo/ID; **không đồng nghĩa** với thứ tự thời gian chạy cuối cùng của từng instance.
- `getJobInstanceCount(jobName)` có thể ném `NoSuchJobException` nếu tên job chưa có instance; không nên mặc định mọi tên đều trả `0`.
- Các phương thức tra ID thường có thể trả `null` nếu ID không có trong repository.
- Kết quả `findRunningJobExecutions` là `Set`: thứ tự không được đảm bảo, muốn hiển thị phải tự sắp xếp.
- `getJobExecutions` có thể trả về các step execution chưa được hydrate đầy đủ, đặc biệt là `ExecutionContext`. Khi thực sự cần context của step, gọi `getStepExecution(jobExecutionId, stepExecutionId)`.
- `getJobExecution(executionId)` thường tái tạo object graph của lần chạy, gồm các step và context theo hợp đồng của API, nhưng dữ liệu đã lưu có thể khác đối tượng sống tại thời điểm job còn chạy.

### Ví dụ ngắn: xem các job đã chạy

```java
for (String jobName : jobExplorer.getJobNames()) {
    long instanceCount = jobExplorer.getJobInstanceCount(jobName);
    System.out.printf("%s: %d instances%n", jobName, instanceCount);
}
```

Danh sách tên job đến từ **metadata đã lưu**, không nhất thiết trùng danh sách bean `Job` đang được deploy. Một job có thể tồn tại trong code nhưng chưa từng chạy; ngược lại, lịch sử trong DB có thể chứa tên job đã được gỡ khỏi phiên bản ứng dụng hiện tại.

---

## 6. Cấu hình JobExplorer trong Spring Boot

### 6.1. Khai báo dependency

Với Spring Boot 3.x + Spring Batch 5.2.x, dependency Gradle ví dụ:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    runtimeOnly 'org.postgresql:postgresql' // Ví dụ DB production
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

`spring-boot-starter-web` chỉ cần nếu dùng REST API minh họa ở phần sau. Một batch worker dùng CLI/scheduler và chỉ xuất metric có thể không cần Spring MVC.

Khi Spring Batch infrastructure được cấu hình đúng, có thể inject `JobExplorer` vào bean như các dependency khác:

```java
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class BatchStatusReader {
    private final JobExplorer jobExplorer;

    public BatchStatusReader(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public long countInstances(String jobName)
            throws org.springframework.batch.core.launch.NoSuchJobException {
        return jobExplorer.getJobInstanceCount(jobName);
    }
}
```

Bạn cần một `JobRepository` JDBC trỏ vào metadata database đã có bảng Spring Batch. Nếu database vừa khởi tạo, hãy chạy schema initialization/migration trước khi tra cứu lịch sử. Nếu dùng nhiều datasource, cần bảo đảm `JobExplorer` **đọc cùng metadata store** với `JobRepository` đã dùng để thực thi job.

### 6.2. Cấu hình datasource ví dụ

Một ứng dụng Spring Boot dùng PostgreSQL có thể cấu hình:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/batchdb
    username: batch_app
    password: ${BATCH_DB_PASSWORD}
  batch:
    job:
      enabled: false
```

Trong snippet, `spring.batch.job.enabled=false` thích hợp cho ứng dụng giám sát hoặc khi bạn chủ động chạy job bằng scheduler/API. Phần cấu hình DB phải được điều chỉnh theo môi trường và quản lý secret thực tế. Các bảng `BATCH_*` cần được tạo theo schema đúng phiên bản.

### 6.3. Khi phải tự tạo JobExplorer

Trong cấu hình Spring Batch thủ công, có thể dùng `JobExplorerFactoryBean`. Chỉ thêm cấu hình này nếu hạ tầng hiện tại chưa cung cấp bean phù hợp:

```java
import javax.sql.DataSource;

import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.explore.support.JobExplorerFactoryBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class ExplorerConfiguration {

    @Bean
    JobExplorer jobExplorer(DataSource batchDataSource) throws Exception {
        JobExplorerFactoryBean factory = new JobExplorerFactoryBean();
        factory.setDataSource(batchDataSource);
        factory.setTablePrefix("BATCH_");
        factory.afterPropertiesSet();
        return factory.getObject();
    }
}
```

`BATCH_` chỉ là tiền tố mặc định trong ví dụ. Nếu repository dùng `SYSTEM.BATCH_` hoặc prefix khác, explorer phải dùng **cùng prefix**. Trong ứng dụng Spring Boot đã auto-configure `JobExplorer`, không tạo bean thứ hai cùng tên vì sẽ gây xung đột cấu hình hoặc nhầm datasource.

Một số hệ thống dùng serializer tùy biến cho `ExecutionContext`: explorer phải dùng serializer tương thích với repository để đọc đúng nội dung đã persist. Không tự thay serializer ở một bên mà không lập kế hoạch migration.

---

## 7. Ví dụ đầy đủ: service đọc lịch sử chạy job

Phần này xây dựng API Java chỉ đọc phục vụ màn hình vận hành. Dữ liệu trả về được chuyển thành DTO/record thay vì trả thẳng object Spring Batch qua JSON. Cách này giúp tránh vòng tham chiếu object, hạn chế lộ `ExecutionContext` và kiểm soát các trường xuất hiện trong response.

### 7.1. DTO hiển thị

Ví dụ package `com.example.batch.monitoring`:

```java
package com.example.batch.monitoring;

import java.time.LocalDateTime;
import java.util.List;
import org.springframework.batch.core.BatchStatus;

public final class BatchViews {
    private BatchViews() {}

    public record Page<T>(int page, int size, long total, List<T> items) {}

    public record InstanceView(
            long instanceId,
            String jobName,
            Long lastExecutionId,
            BatchStatus lastStatus,
            LocalDateTime lastStartTime) {}

    public record StepView(
            Long stepExecutionId,
            String stepName,
            BatchStatus status,
            String exitCode,
            long readCount,
            long writeCount,
            long filterCount,
            long readSkipCount,
            long processSkipCount,
            long writeSkipCount,
            long commitCount,
            long rollbackCount) {}

    public record ExecutionView(
            Long executionId,
            long instanceId,
            String jobName,
            BatchStatus status,
            String exitCode,
            LocalDateTime startTime,
            LocalDateTime endTime,
            List<StepView> steps) {}
}
```

Spring Batch 5.2 dùng `LocalDateTime` cho các mốc thời gian execution. Đây là dữ liệu **không mang offset/múi giờ**; màn hình cần thống nhất timezone của hạ tầng và cách diễn giải thời gian. Không tự áp `UTC` cho những giá trị chưa được xác nhận là UTC.

### 7.2. Service truy vấn

```java
package com.example.batch.monitoring;

import java.util.Comparator;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;

import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.NoSuchJobException;
import org.springframework.stereotype.Service;

import com.example.batch.monitoring.BatchViews.ExecutionView;
import com.example.batch.monitoring.BatchViews.InstanceView;
import com.example.batch.monitoring.BatchViews.Page;
import com.example.batch.monitoring.BatchViews.StepView;

@Service
public class BatchHistoryService {

    private final JobExplorer explorer;

    public BatchHistoryService(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public List<String> jobNames() {
        return explorer.getJobNames();
    }

    public Page<InstanceView> instances(String jobName, int page, int size) {
        if (jobName == null || jobName.isBlank()) {
            throw new IllegalArgumentException("jobName is required");
        }
        if (page < 0 || size < 1 || size > 100) {
            throw new IllegalArgumentException(
                    "page must be >= 0 and size must be 1..100");
        }

        long offset = (long) page * size;
        if (offset > Integer.MAX_VALUE) {
            throw new IllegalArgumentException("page offset too large");
        }

        long total;
        try {
            total = explorer.getJobInstanceCount(jobName);
        } catch (NoSuchJobException notFound) {
            return new Page<>(page, size, 0L, List.of());
        }

        List<InstanceView> items = explorer
                .getJobInstances(jobName, (int) offset, size)
                .stream()
                .map(this::toInstanceView)
                .toList();

        return new Page<>(page, size, total, items);
    }

    public Optional<ExecutionView> execution(long executionId) {
        if (executionId <= 0) {
            throw new IllegalArgumentException("executionId must be positive");
        }
        JobExecution execution = explorer.getJobExecution(executionId);
        if (execution == null) {
            return Optional.empty();
        }
        return Optional.of(toExecutionView(execution));
    }

    public List<ExecutionView> executionsOf(long instanceId) {
        JobInstance instance = explorer.getJobInstance(instanceId);
        if (instance == null) {
            throw new NoSuchElementException(
                    "JobInstance does not exist: " + instanceId);
        }

        return explorer.getJobExecutions(instance).stream()
                .sorted(Comparator.comparing(
                        JobExecution::getId,
                        Comparator.nullsLast(Comparator.reverseOrder())))
                .map(this::toExecutionView)
                .toList();
    }

    private InstanceView toInstanceView(JobInstance instance) {
        JobExecution last = explorer.getLastJobExecution(instance);
        return new InstanceView(
                instance.getInstanceId(),
                instance.getJobName(),
                last == null ? null : last.getId(),
                last == null ? null : last.getStatus(),
                last == null ? null : last.getStartTime());
    }

    private ExecutionView toExecutionView(JobExecution execution) {
        List<StepView> steps = execution.getStepExecutions().stream()
                .sorted(Comparator.comparing(
                        StepExecution::getId,
                        Comparator.nullsLast(Comparator.naturalOrder())))
                .map(this::toStepView)
                .toList();

        return new ExecutionView(
                execution.getId(),
                execution.getJobInstance().getInstanceId(),
                execution.getJobInstance().getJobName(),
                execution.getStatus(),
                execution.getExitStatus().getExitCode(),
                execution.getStartTime(),
                execution.getEndTime(),
                steps);
    }

    private StepView toStepView(StepExecution step) {
        return new StepView(
                step.getId(),
                step.getStepName(),
                step.getStatus(),
                step.getExitStatus().getExitCode(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount());
    }
}
```

Giải thích các quyết định quan trọng:

- `getJobNames()` lấy danh sách tên job thực sự có metadata trong repository.
- `getJobInstanceCount()` đếm **instance**, không đếm các `JobExecution` của mỗi instance.
- Mỗi trang chỉ lấy tối đa 100 instance; offset dùng `long` trong tính toán rồi mới ép sang `int` sau kiểm tra biên.
- `NoSuchJobException` được chuyển thành trang rỗng vì đây là lựa chọn giao diện của ví dụ; ứng dụng khác có thể chọn HTTP 404.
- `getLastJobExecution(instance)` được gọi riêng cho từng instance, tạo kiểu truy vấn N+1 ở lớp danh sách. Với trang nhỏ có thể chấp nhận; khi cần dashboard lớn, nên cân nhắc cache, bảng tổng hợp hoặc truy vấn chuyên dụng.
- `getJobExecutions(instance)` cho lịch sử các lần thử chạy của **cùng instance**, hữu ích để nhận biết restart.
- `getJobExecution(executionId)` trả về `null` khi ID không tồn tại. `Optional.empty()` biểu diễn rõ kết quả không tìm thấy.
- Đoạn service đọc các bộ đếm từ metadata; nó không mở resource đầu vào, không chạy processor và không cập nhật tiến trình.
- `ExecutionContext` cùng thông tin exception thô được cố ý giữ ngoài DTO vì có thể chứa đường dẫn nội bộ, tên tài nguyên, thông tin giao dịch hoặc dữ liệu nhạy cảm.

**Quan sát về tính nhất quán:** một trang được tạo bằng nhiều truy vấn (count, list, last execution) có thể nhìn thấy trạng thái khác nhau nếu job bắt đầu hoặc hoàn tất trong lúc đang đọc. Đây là hành vi bình thường của hệ thống chạy đồng thời; số tổng và số bản ghi có thể lệch trong khoảnh khắc.

### 7.3. REST endpoint chỉ đọc

```java
package com.example.batch.monitoring;

import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import com.example.batch.monitoring.BatchViews.ExecutionView;
import com.example.batch.monitoring.BatchViews.InstanceView;
import com.example.batch.monitoring.BatchViews.Page;

@RestController
@RequestMapping("/internal/batch")
public class BatchHistoryController {

    private final BatchHistoryService service;

    public BatchHistoryController(BatchHistoryService service) {
        this.service = service;
    }

    @GetMapping("/jobs")
    public List<String> jobs() {
        return service.jobNames();
    }

    @GetMapping("/jobs/{jobName}/instances")
    public Page<InstanceView> instances(
            @PathVariable String jobName,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {
        return service.instances(jobName, page, size);
    }

    @GetMapping("/executions/{executionId}")
    public ResponseEntity<ExecutionView> execution(
            @PathVariable long executionId) {
        return service.execution(executionId)
                .map(ResponseEntity::ok)
                .orElseGet(() -> ResponseEntity.notFound().build());
    }
}
```

Ví dụ request:

```http
GET /internal/batch/jobs
GET /internal/batch/jobs/dailyInvoiceJob/instances?page=0&size=20
GET /internal/batch/executions/7002
```

Ví dụ response minh họa của endpoint execution:

```json
{
  "executionId": 7002,
  "instanceId": 42,
  "jobName": "dailyInvoiceJob",
  "status": "COMPLETED",
  "exitCode": "COMPLETED",
  "startTime": "2026-11-16T02:00:00",
  "endTime": "2026-11-16T02:01:12",
  "steps": [
    {
      "stepExecutionId": 8003,
      "stepName": "exportInvoices",
      "status": "COMPLETED",
      "exitCode": "COMPLETED",
      "readCount": 1000,
      "writeCount": 998,
      "filterCount": 2,
      "readSkipCount": 0,
      "processSkipCount": 0,
      "writeSkipCount": 0,
      "commitCount": 6,
      "rollbackCount": 0
    }
  ]
}
```

Đây là **dữ liệu ví dụ**, không phải dữ liệu thực từ repository. Mốc thời gian không chứa timezone nên client phải áp quy ước hệ thống trước khi chuyển đổi sang giờ địa phương.

REST example chưa bao gồm authentication, authorization, exception handler và cấu hình CORS. Trong ứng dụng vận hành thật, endpoint này nên được giới hạn người đọc có quyền; không đăng công khai thông tin đường dẫn, JobParameters hoặc `ExecutionContext`.

---

## 8. Truy vấn trực tiếp metadata cho các tình huống vận hành

### 8.1. Tìm lịch sử chạy của một job

```java
String name = "dailyInvoiceJob";
int offset = 0;
int pageSize = 10;

List<JobInstance> instances =
        jobExplorer.getJobInstances(name, offset, pageSize);

for (JobInstance instance : instances) {
    System.out.println("instance=" + instance.getInstanceId());

    for (JobExecution execution :
            jobExplorer.getJobExecutions(instance)) {
        System.out.println(
                "  execution=" + execution.getId()
                + " status=" + execution.getStatus());
    }
}
```

Đây là mô hình duyệt theo **instance trước rồi execution**. Nếu một instance được restart nhiều lần, nhiều execution cùng nằm dưới instance đó.

Đừng dùng `getJobInstances(name, 0, 1)` rồi coi kết quả là **JobExecution mới nhất của cả hệ thống** trong mọi tình huống. Instance cũ có thể vừa được restart và có execution mới hơn instance mới tạo. Muốn lấy “mới nhất theo thời điểm chạy” trên toàn bộ job, cần xét execution của các instance liên quan hoặc dùng một truy vấn tổng hợp khác phù hợp.

### 8.2. Tra chi tiết execution bằng ID

```java
JobExecution execution = jobExplorer.getJobExecution(7002L);

if (execution == null) {
    System.out.println("No execution found");
} else {
    System.out.println("Status: " + execution.getStatus());
    System.out.println("Exit code: "
            + execution.getExitStatus().getExitCode());
    System.out.println("Start: " + execution.getStartTime());
    System.out.println("End: " + execution.getEndTime());

    for (StepExecution step : execution.getStepExecutions()) {
        System.out.printf(
                "%s: read=%d, write=%d, skip=%d%n",
                step.getStepName(),
                step.getReadCount(),
                step.getWriteCount(),
                step.getSkipCount());
    }
}
```

Lưu ý `getStepCount` hay `getReadCount` không phải method của `JobExecution`; các bộ đếm item nằm ở `StepExecution`. Nếu job có nhiều step, phải quyết định **tổng hợp** theo định nghĩa nghiệp vụ nào. Ví dụ hai step lần lượt đọc cùng một tập record thì cộng hai `readCount` có thể đếm cùng một record hai lần.

### 8.3. Đọc chi tiết một StepExecution cụ thể

```java
Long jobExecutionId = 7002L;
Long stepExecutionId = 8003L;

StepExecution step = jobExplorer.getStepExecution(
        jobExecutionId,
        stepExecutionId);

if (step != null) {
    System.out.println(step.getStepName());
    System.out.println(step.getStatus());
    System.out.println(step.getExecutionContext());
}
```

Truyền **cả jobExecutionId và stepExecutionId** để lấy đúng step. Trường hợp muốn hiển thị tên trường, số item và thời gian, dùng các getter tương ứng. Tránh in toàn bộ `ExecutionContext` ra log production: có thể lộ secret hoặc dữ liệu vận hành nhạy cảm.

### 8.4. Tìm job được ghi nhận đang chạy

```java
Set<JobExecution> running =
        jobExplorer.findRunningJobExecutions("dailyInvoiceJob");

List<JobExecution> ordered = running.stream()
        .sorted(Comparator.comparing(
                JobExecution::getId,
                Comparator.nullsLast(Comparator.reverseOrder())))
        .toList();

for (JobExecution execution : ordered) {
    System.out.printf("running execution=%d, status=%s%n",
            execution.getId(), execution.getStatus());
}
```

Các import bổ sung:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Set;
import org.springframework.batch.core.JobExecution;
```

**“Đang chạy” ở đây là trạng thái metadata được repository ghi nhận, không phải heartbeat chắc chắn của JVM.** Nếu máy chủ bị tắt đột ngột, execution có thể còn `STARTED` dù không còn tiến trình xử lý. Cần thêm dấu hiệu giám sát tiến trình, `lastUpdated`, log hoặc metric để xác nhận thực sự còn chạy.

### 8.5. Phân biệt trạng thái kỹ thuật và kết quả flow

```java
BatchStatus batchStatus = execution.getStatus();
String exitCode = execution.getExitStatus().getExitCode();
String exitDescription =
        execution.getExitStatus().getExitDescription();
```

`BatchStatus` phục vụ vòng đời kỹ thuật; `ExitStatus` là kết quả do step/job có thể tùy chỉnh, thường được job flow dùng để xác định nhánh tiếp theo.

Ví dụ một step hoàn tất về mặt kỹ thuật có thể trả `ExitStatus` tùy chỉnh `COMPLETED_WITH_WARNINGS`. Vì vậy màn hình vận hành cần quyết định hiển thị cả hai thay vì suy luận rằng `BatchStatus.COMPLETED` luôn mang nghĩa “không có cảnh báo nghiệp vụ”.

---

## 9. Đọc ExecutionContext đúng cách

`ExecutionContext` là tập các cặp key/value được lưu qua job/step để hỗ trợ checkpoint, restart hoặc chia sẻ dữ liệu giữa các step.

| Phạm vi | Lấy từ | Loại dữ liệu điển hình |
|---|---|---|
| Job execution context | `jobExecution.getExecutionContext()` | Tổng số record xử lý, khóa tổng hợp, thông tin chia sẻ giữa các step |
| Step execution context | `stepExecution.getExecutionContext()` | Vị trí reader, trạng thái writer, offset của phân trang |

Ví dụ tra key có kiểm soát:

```java
JobExecution execution = jobExplorer.getJobExecution(7002L);
if (execution != null) {
    ExecutionContext context = execution.getExecutionContext();

    if (context.containsKey("processedBusinessDate")) {
        String value = context.getString("processedBusinessDate");
        System.out.println(value);
    }
}
```

Import:

```java
import org.springframework.batch.item.ExecutionContext;
```

Đừng giả định mọi key đều tồn tại, hay mọi giá trị đều có kiểu `String`. `ExecutionContext` có thể chứa các đối tượng đã được deserialize theo serializer được cấu hình, và việc đọc sai kiểu có thể gây exception.

### Vì sao có thể cần getStepExecution lần thứ hai?

Javadoc `JobExplorer.getJobExecutions(JobInstance)` cho biết các `StepExecution` đi kèm **có thể chưa được hydrate đầy đủ**. Đặc biệt, step execution context có thể thiếu trong object lồng ghép tùy implementation.

Nếu cần checkpoint để chẩn đoán:

```java
JobExecution jobExecution = jobExplorer.getJobExecution(7002L);
if (jobExecution != null) {
    for (StepExecution summary : jobExecution.getStepExecutions()) {
        StepExecution detailed = jobExplorer.getStepExecution(
                jobExecution.getId(), summary.getId());

        if (detailed != null) {
            ExecutionContext checkpoint = detailed.getExecutionContext();
            // Chỉ đọc các key đã được cho phép hiển thị.
        }
    }
}
```

Một truy vấn theo ID của một step thường rõ ràng hơn việc cố lấy thông tin từ object graph chưa hydrate trong một truy vấn danh sách. Không mutate `checkpoint` rồi mong tự động được lưu: `JobExplorer` được dùng cho **đọc** metadata, không commit trạng thái mới.

### Khi nào không nên expose ExecutionContext?

Không trả thẳng context trong REST API công khai. Context có thể chứa tên bucket, tên file nội bộ, token do code ứng dụng vô tình ghi vào, ID nghiệp vụ hoặc cấu trúc lớp Java. Nếu cần cung cấp cho nhân viên hỗ trợ, hãy thiết kế DTO chỉ có những key đã cho phép và mask giá trị nhạy cảm.

---

## 10. Các trạng thái JobExecution cần hiểu khi xem metadata

| BatchStatus | Ý nghĩa vận hành phổ biến |
|---|---|
| `STARTING` | Framework đã bắt đầu thủ tục khởi chạy |
| `STARTED` | Execution được ghi nhận đang thực thi |
| `STOPPING` | Có yêu cầu dừng, đang chờ job/step phản hồi |
| `STOPPED` | Execution đã dừng theo cơ chế dừng |
| `COMPLETED` | Execution hoàn tất về mặt batch framework |
| `FAILED` | Execution thất bại |
| `ABANDONED` | Bị đánh dấu bỏ qua/không tiếp tục theo cơ chế batch |
| `UNKNOWN` | Không thể xác định chắc trạng thái trong một số trường hợp |

Đừng biến bảng trên thành quy tắc tự động restart tất cả những job có `FAILED` hoặc `STOPPED`. Khả năng restart còn phụ thuộc cấu hình job, trạng thái step, dữ liệu đã commit và tính an toàn của tác vụ nghiệp vụ.

### Mối quan hệ giữa status và thời gian

- `getCreateTime()`: thời điểm bản ghi execution được tạo.
- `getStartTime()`: thời điểm job thực sự bắt đầu; có thể chưa có.
- `getEndTime()`: thời điểm kết thúc; thường là `null` nếu chưa kết thúc bình thường.
- `getLastUpdated()`: mốc metadata được cập nhật gần nhất theo repository.

Không phải lúc nào `endTime == null` cũng chứng minh job còn chạy; nó có thể bị mất tiến trình hoặc metadata cập nhật dở dang. Đối với hệ thống đa máy chủ, cần xem thêm scheduler, container/VM health và log.

---

## 11. Ứng dụng thực tế: tra cứu, cảnh báo, và restart

### 11.1. Dashboard lịch sử

Giao diện có thể có hai tầng:

1. **Danh sách instance**: `jobName`, `instanceId`, identifying business key, trạng thái execution cuối.
2. **Trang chi tiết instance/execution**: danh sách những lần chạy, các step, counters, lỗi và mốc thời gian.

Thiết kế này tránh hiển thị mỗi `JobExecution` như một “job hoàn toàn mới” và giúp người vận hành nhìn thấy việc restart.

### 11.2. Tìm các execution thất bại

`JobExplorer` không có một method tổng quát trong Spring Batch 5.2 để “lấy mọi FAILED execution ở toàn bộ repository theo ngày”. Một phương án ứng dụng đơn giản là lấy instance theo trang rồi lọc execution:

```java
List<JobInstance> instances =
        jobExplorer.getJobInstances("dailyInvoiceJob", 0, 100);

List<JobExecution> failed = instances.stream()
        .flatMap(instance ->
                jobExplorer.getJobExecutions(instance).stream())
        .filter(execution ->
                execution.getStatus() == BatchStatus.FAILED)
        .toList();
```

Đây chỉ tìm trong **100 instance đầu tiên**, không phải toàn bộ lịch sử. Khi cần bộ lọc toàn cục theo ngày/trạng thái với dữ liệu lớn, nên xây một truy vấn/report read model riêng trên metadata database, index phù hợp hoặc pipeline đẩy metric để tránh quét repository trên mỗi request.

### 11.3. Cảnh báo “job quá lâu”

Một heuristic vận hành có thể xét:

- `BatchStatus.STARTED`.
- `getStartTime()` đã cũ hơn ngưỡng thời gian của job đó.
- `getLastUpdated()` không tiến triển.
- Hệ thống tiến trình/scheduler xác nhận công việc còn chạy hay đã mất.

Nếu chỉ dựa vào `STARTED`, một job lỗi do JVM bị kill có thể bị coi là “đang chạy rất lâu”. Heuristic cảnh báo là **tín hiệu để điều tra**, không phải lý do tự ý cập nhật trạng thái hoặc restart khi chưa đánh giá tác động dữ liệu.

### 11.4. Cần dừng hoặc restart thì dùng API điều khiển

`JobExplorer` có thể tra ID chính xác, trạng thái và chi tiết execution làm dữ kiện quyết định. Sau khi xác định thao tác an toàn và có quyền, tầng vận hành có thể dùng `JobOperator`.

Luồng lý tưởng:

```text
Người vận hành chọn execution
           │
           ▼
JobExplorer đọc lại metadata mới nhất
           │
           ▼
Kiểm tra trạng thái, lịch sử, chính sách và quyền
           │
           ▼
JobOperator thực hiện stop/restart (nếu phù hợp)
           │
           ▼
JobExplorer truy vấn lại để hiển thị kết quả
```

Việc đọc rồi thao tác là **hai thời điểm khác nhau**; execution có thể đổi trạng thái ở giữa. Tầng điều khiển vẫn cần xử lý xung đột, không tin hoàn toàn dữ liệu vừa được xem trên giao diện.

---

## 12. Phân trang, hiệu năng và tính nhất quán

### 12.1. Phân trang là yêu cầu thiết kế

Với repository có hàng triệu job execution, gọi `getJobInstances(name, 0, Integer.MAX_VALUE)` gây tải lớn. Dùng page size hữu hạn và chặn giá trị bất hợp lý từ request.

```java
int page = 3;       // trang thứ tư, nếu đánh số từ 0
int size = 25;
int start = Math.multiplyExact(page, size);

List<JobInstance> items =
        jobExplorer.getJobInstances("dailyInvoiceJob", start, size);
```

Đặt `page >= 0`, `size > 0` và giới hạn trên size; `Math.multiplyExact` sẽ báo lỗi nếu tràn số nguyên. Kết quả `getJobInstances` chỉ đảm bảo thứ tự theo cơ chế truy vấn instance, **không có snapshot nhất quán tự động** qua nhiều request phân trang khi dữ liệu mới được chèn.

### 12.2. Vấn đề N+1

Để hiển thị `lastStatus` cho 100 instance, code gọi `getLastJobExecution(instance)` trong vòng lặp phát sinh nhiều truy vấn. Với số lượng vừa phải có thể chấp nhận; với dashboard nhiều người cùng mở:

- Chỉ trả những trường thực sự cần trên trang danh sách.
- Giảm page size và dùng cache ngắn nếu phù hợp độ trễ chấp nhận được.
- Tạo read model có tổng hợp trạng thái mới nhất nếu cần SLA cao.
- Giới hạn endpoint chẩn đoán sâu để tránh load mọi context cùng lúc.

### 12.3. Nguồn dữ liệu phải nhất quán

Một hệ thống chạy batch ở cluster A và hiển thị dashboard ở service B chỉ thấy metadata nếu hai bên đọc cùng repository hoặc bản sao đồng bộ. Nếu dashboard đọc read replica, có thể xuất hiện **replication lag**: job đã hoàn tất ở primary nhưng UI vẫn báo `STARTED` trong một khoảng thời gian.

### 12.4. Metadata retention

Một số hệ thống định kỳ xóa metadata cũ để giữ DB nhỏ. Khi đó `getJobInstance(...)` hoặc `getJobExecution(...)` có thể không tìm thấy lịch sử dù batch đã chạy trong quá khứ. Nếu có yêu cầu kiểm toán dài hạn, cần chính sách archive/report phù hợp, không phụ thuộc vô thời hạn vào bảng vận hành.

---

## 13. Kiểm thử code đọc metadata

Có hai lớp kiểm thử khác nhau.

### 13.1. Unit test service bằng mock JobExplorer

Unit test phù hợp để kiểm tra service xử lý ID thiếu, phân trang và lỗi. Ví dụ dùng Mockito (có trong `spring-boot-starter-test`):

```java
package com.example.batch.monitoring;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.explore.JobExplorer;
import java.util.List;

class BatchHistoryServiceTest {

    private final JobExplorer explorer = mock(JobExplorer.class);
    private final BatchHistoryService service =
            new BatchHistoryService(explorer);

    @Test
    void missingExecutionReturnsEmpty() {
        when(explorer.getJobExecution(999L)).thenReturn(null);

        assertTrue(service.execution(999L).isEmpty());
        verify(explorer).getJobExecution(999L);
    }

    @Test
    void emptyInstancePageWhenNoJobWasExecuted() throws Exception {
        when(explorer.getJobInstanceCount("neverRunJob"))
                .thenThrow(new org.springframework.batch.core.launch
                        .NoSuchJobException("neverRunJob"));

        var result = service.instances("neverRunJob", 0, 20);

        assertEquals(0L, result.total());
        assertEquals(List.of(), result.items());
        verify(explorer, never())
                .getJobInstances(anyString(), anyInt(), anyInt());
    }

    @Test
    void rejectsOversizedPage() {
        assertThrows(IllegalArgumentException.class,
                () -> service.instances("dailyInvoiceJob", 0, 1000));
    }
}
```

Unit test này chứng minh quy tắc ở tầng service, **không chứng minh** truy vấn database và quan hệ instance–execution thực sự hoạt động. Phần đó cần integration test.

### 13.2. Integration test với JobRepository thật

Ý tưởng là chạy một job test có một step đơn giản, sau đó dùng `JobExplorer` nạp lại metadata bằng ID được sinh ra. Đoạn sau là khung kiểm thử tích hợp; cần có `BatchTestApplication` và `sampleJob` đã được cấu hình trong project.

```java
@SpringBatchTest
@SpringBootTest(
    classes = BatchTestApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class JobExplorerIntegrationTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JobExplorer jobExplorer;

    @Test
    void canReadMetadataOfCompletedExecution() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution launched = jobLauncherTestUtils.launchJob(params);
        assertEquals(BatchStatus.COMPLETED, launched.getStatus());

        JobExecution stored =
                jobExplorer.getJobExecution(launched.getId());

        assertNotNull(stored);
        assertEquals(launched.getId(), stored.getId());
        assertEquals(BatchStatus.COMPLETED, stored.getStatus());
        assertNotNull(stored.getJobInstance());
        assertFalse(stored.getStepExecutions().isEmpty());

        for (StepExecution step : stored.getStepExecutions()) {
            StepExecution hydrated = jobExplorer.getStepExecution(
                    stored.getId(), step.getId());
            assertNotNull(hydrated);
            assertEquals(step.getStepName(), hydrated.getStepName());
        }
    }
}
```

Các import tiêu biểu:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
```

Nếu application context có nhiều `Job`, cần cấu hình `JobLauncherTestUtils` chọn đúng job; nếu test dùng H2, cần dependency H2 và schema initialization. Với job có nhiều step, các assertion nên phản ánh những step thực tế được kỳ vọng chạy.

### 13.3. Những test case nên có

| Tình huống | Assertion |
|---|---|
| Job chưa từng được chạy | `getJobNames()` chưa chứa tên đó; tùy API `getJobInstanceCount` có thể ném `NoSuchJobException` |
| Chạy job thành công | Có instance, có execution, status và các step đúng |
| Restart một job failed | Cùng JobInstance ID, có thêm JobExecution ID khác |
| Hai ngày nghiệp vụ identifying khác nhau | Hai JobInstance khác nhau |
| Một tham số non-identifying thay đổi | Không tạo instance mới chỉ do tham số đó |
| Tìm execution ID không tồn tại | `getJobExecution(id) == null` |
| Đọc chi tiết step | ID và metadata step khớp execution cha |
| Job đang chạy | `findRunningJobExecutions` phản ánh metadata trong thời điểm truy vấn |
| Nhiều execution cùng một instance | Lịch sử trả đủ lần chạy; có thể phân biệt failed và completed |
| Database không có schema/đọc nhầm datasource | Test integration phải thất bại rõ, không âm thầm trả kết quả rỗng |

**Quan trọng:** không cần tạo restart thật trong mọi unit test. Những kịch bản phụ thuộc transaction và metadata thì chạy integration test cô lập sẽ có giá trị hơn.

---

## 14. Những lỗi hay gặp khi dùng JobExplorer

| Dấu hiệu | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `NoSuchJobException` khi đếm instance | Tên job chưa từng tạo instance trong repository | Xác định yêu cầu UI: báo 404 hoặc trả trang rỗng |
| `getJobExecution(id)` trả `null` | Sai ID hoặc metadata đã bị xóa/không nằm trong datasource | Kiểm tra execution ID, DB và retention |
| Danh sách job rỗng dù code có định nghĩa job | Job chưa chạy; hoặc explorer đọc sai repository | Chạy job thử và đối chiếu datasource |
| Job đã kết thúc nhưng UI báo `STARTED` | Metadata còn cũ, replica lag, JVM bị kill hoặc trang đang cache | Kiểm tra DB primary, `lastUpdated`, process và log |
| Các bộ đếm step hiển thị thiếu | Đọc sai step, hoặc lấy object chưa hydrate đầy đủ | Gọi `getStepExecution(jobExecutionId, stepExecutionId)` |
| Lỗi bảng `BATCH_JOB_INSTANCE` không tồn tại | Schema chưa được khởi tạo hoặc table prefix sai | Kiểm tra schema và cấu hình repository/explorer |
| Không deserialize được `ExecutionContext` | Serializer, cấu hình hoặc kiểu dữ liệu thay đổi | Đối chiếu serializer và kế hoạch migration metadata |
| Dashboard chậm | Lấy quá nhiều instance, N+1 lookup hoặc quét toàn bộ lịch sử | Phân trang, giới hạn field, tối ưu read model |
| Status `COMPLETED` nhưng output không đúng | Metadata ghi nhận kết quả kỹ thuật, không kiểm chứng nội dung nghiệp vụ | Kiểm tra output, DB nghiệp vụ, checksum và đối soát |
| Hai service cho ra trạng thái khác nhau | Khác datasource/schema, replica delay hoặc cache | Cố định một nguồn metadata và quy ước freshness |
| Thấy mã job cũ trong danh sách | Metadata lịch sử vẫn còn, không phản ánh bean đang deploy | Phân biệt JobRegistry và JobExplorer |
| Không restart được dù execution cũ FAILED | Job không restartable, dữ liệu không an toàn hoặc trạng thái đã đổi | Kiểm tra chính sách restart và dùng API điều khiển phù hợp |

### Một quy trình chẩn đoán ngắn

```text
Không thấy job/execution mong muốn
    │
    ├─ Kiểm tra tên job và execution ID
    │
    ▼
Đúng datasource, schema, tablePrefix?
    │
    ├─ Không → sửa cấu hình metadata store
    │
    ▼
Metadata tồn tại trong BATCH_*?
    │
    ├─ Không → kiểm tra job đã chạy / retention / migration
    │
    ▼
Dùng API tra cứu đúng cấp chưa?
    │
    ├─ Sai → JobInstance vs JobExecution vs StepExecution
    │
    ▼
Status có bị cũ?
    │
    └─ Xem lastUpdated, scheduler, process, log, replica lag
```

---

## 15. Thiết kế quyền và dữ liệu vận hành

Dù `JobExplorer` là API chỉ đọc, metadata có thể chứa thông tin nội bộ:

- `JobParameters` có thể lộ đường dẫn file, định danh đối tác, tên bucket hoặc thông tin vận hành.
- `ExecutionContext` có thể chứa checkpoint, key nghiệp vụ hoặc dữ liệu do ứng dụng tự ghi.
- `ExitDescription` và exception đôi khi chứa stack trace hoặc nội dung record lỗi.
- Danh sách tên job có thể cho biết quy trình xử lý nhạy cảm của tổ chức.

Nên giới hạn API ở vai trò vận hành cần thiết, trả DTO theo allowlist, không xuất raw `ExecutionContext` và có audit cho các chức năng tra cứu nhạy cảm nếu quy định nội bộ yêu cầu.

Đọc metadata cũng tiêu tốn tài nguyên database. Dashboard polling quá dày có thể ảnh hưởng database đang dùng cho chính các job; hãy đặt tần suất refresh hợp lý và theo dõi tải truy vấn.

---

## 16. Bài tập thực hành

### Bài tập 1 — Danh sách JobInstance

Viết service nhận `jobName`, `page`, `size` và trả danh sách `instanceId`, tên job, `lastStatus`. Test các trường hợp `page=0`, `page=1`, job chưa từng chạy và size lớn hơn giới hạn.

### Bài tập 2 — Lịch sử restart

Tạo một job fail ở lần chạy đầu, rồi restart thành công. Dùng `JobExplorer` chứng minh:

1. `getJobInstances(jobName, ...)` chứa đúng một instance cho bộ identifying parameters đó.
2. `getJobExecutions(instance)` có ít nhất hai execution khác ID.
3. Trạng thái execution đầu là `FAILED`, execution sau là `COMPLETED`.
4. Các step có thể được thực thi lại khác nhau theo chính sách restart.

### Bài tập 3 — Chi tiết StepExecution

Cho `jobExecutionId` và `stepExecutionId`, xây endpoint trả tên step, `readCount`, `writeCount`, `skipCount`, `commitCount` và trạng thái. Xử lý ID không tồn tại bằng HTTP 404.

### Bài tập 4 — Dashboard trạng thái chạy

Mô phỏng job chạy lâu. Gọi `findRunningJobExecutions(jobName)` trong lúc chạy, sau khi hoàn tất và khi job bị dừng đột ngột. Giải thích vì sao kết quả truy vấn metadata chưa đủ để kết luận JVM thực sự còn sống.

### Bài tập 5 — Đánh giá hiệu năng

Giả lập repository có hàng chục nghìn instance. Đo số truy vấn của trang danh sách có gọi `getLastJobExecution` cho từng instance; thử giới hạn page size và cache kết quả tổng hợp, sau đó so sánh chi phí và độ trễ dữ liệu.

### Bài tập 6 — Không lộ dữ liệu nhạy cảm

Tạo một `ExecutionContext` có key nghiệp vụ nội bộ. Viết DTO chỉ trả các field đã được cho phép. Xác nhận REST API không serialize trực tiếp `ExecutionContext`, `JobParameters` hoặc exception stack trace.

---

## 17. Ghi chú khi nâng cấp Spring Batch 6.x

Các ví dụ chính trong bài theo **Spring Batch 5.2.x**. Trong Spring Batch 6.x, hệ thống package và một số API repository/explorer đã thay đổi; chẳng hạn các Javadoc Spring Batch 6 đặt `JobExplorer` trong nhánh package `org.springframework.batch.core.repository.explore` và thay đổi mối quan hệ giữa `JobRepository` và `JobExplorer`.

Do đó, khi nâng cấp:

1. Chọn phiên bản Spring Boot/Spring Batch hỗ trợ nhau; không ghép riêng thư viện Spring Batch 6.x vào ứng dụng Boot 3.x vốn dùng Spring Batch 5.x.
2. Kiểm tra Javadoc đúng phiên bản cho `JobExplorer`, `JobRepository`, `JobExecution`, `StepExecution` và các kiểu dữ liệu dùng trong DTO.
3. Rà soát API được đánh dấu `@Deprecated`, package import và migration SQL của metadata repository.
4. Kiểm tra khả năng tương thích serializer của `ExecutionContext` và cách đọc metadata lịch sử sau nâng cấp.
5. Chạy lại integration test đọc metadata đã được lưu và test các kịch bản restart.

Nội dung nền tảng vẫn giữ nguyên: cần biết đang tra **instance**, **execution** hay **step execution**, và không biến thao tác đọc metadata thành thao tác điều khiển job thiếu kiểm soát.

---

## 18. Tài liệu tham khảo

- [Spring Batch 5.2 — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html): `JobExplorer`, `JobOperator` và truy vấn repository.
- [JobExplorer API — Spring Batch 5.2.2](https://docs.spring.io/spring-batch/docs/5.2.2/api/org/springframework/batch/core/explore/JobExplorer.html): chữ ký API, pagination, running executions và các hành vi `null`.
- [Spring Batch 5.2 — Domain Language](https://docs.spring.io/spring-batch/reference/5.2/domain.html): quan hệ `JobInstance`, `JobExecution` và `StepExecution`.
- [Spring Batch 5.2 — Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/5.2/job/configuring-repository.html): cấu hình datasource, transaction và table prefix.
- [Spring Batch 5.2 — Metadata Schema](https://docs.spring.io/spring-batch/reference/5.2/schema-appendix.html): chi tiết bảng metadata.
- [JobExplorer API — Spring Batch 6.x](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/repository/explore/JobExplorer.html): kiểm tra API khi dùng phiên bản mới.

`JobExplorer` giúp biến metadata Spring Batch thành thông tin dễ hiểu cho con người và hệ thống giám sát. Một thiết kế tốt vừa phân biệt chính xác các cấp định danh, vừa thể hiện trạng thái và bộ đếm với đúng ngữ cảnh, phân trang hợp lý và luôn nhớ rằng lịch sử lưu trong repository là **ghi nhận trạng thái thực thi**, cần được đối chiếu với dữ liệu nghiệp vụ và tín hiệu vận hành khi ra quyết định.
