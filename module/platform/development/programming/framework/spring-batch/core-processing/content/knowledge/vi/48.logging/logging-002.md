# Log ở step listener trong Spring Batch

## 1. Tại sao cần ghi log trong step listener?

Một Spring Batch job thường gồm nhiều step như đọc dữ liệu, kiểm tra điều kiện, chuyển đổi và ghi kết quả. Khi job chạy theo lịch hoặc được vận hành trong hệ thống production, câu hỏi quan trọng không chỉ là *job đã chạy chưa* mà còn là:

- Step nào được bắt đầu, bắt đầu trong lần thực thi job nào?
- Step thành công, thất bại hay bị dừng? Exit code cụ thể là gì?
- Bao nhiêu bản ghi đã đọc, ghi, lọc hoặc bỏ qua?
- Thời gian xử lý là bao lâu? Có nhiều lần rollback/commit bất thường không?
- Cùng một step được chạy lại sau lỗi hay là một job instance mới?
- Khi step thất bại, cần tìm lỗi trong log của lần thực thi nào?

`StepExecutionListener` là một điểm mở rộng của Spring Batch được gọi ở **ranh giới vòng đời step**. Đây là nơi phù hợp để ghi những sự kiện như `batch.step.started`, `batch.step.finished` hoặc `batch.step.failed`, kèm theo metadata đủ để tra cứu.

```text
JobLauncher / JobOperator
          |
          v
      JobExecution
          |
          v
    StepExecution
          |
          +--> beforeStep(stepExecution)
          |         |
          |         +--> Log bắt đầu step
          |
          +--> Reader / Processor / Writer
          |         hoặc Tasklet
          |
          +--> afterStep(stepExecution)
                    |
                    +--> Log trạng thái và thống kê
```

**Phân biệt:** `StepExecutionListener` quan sát **một lần thực thi step**, không phải từng item. Muốn biết lỗi đọc một dòng, lỗi ghi một chunk hoặc nguyên nhân item bị skip, có thể phối hợp `ItemReadListener`, `ItemProcessListener`, `ItemWriteListener`, `SkipListener` hay `ChunkListener`. Việc gộp mọi log vào `StepExecutionListener` sẽ làm mất thông tin về nơi lỗi phát sinh.

## 2. Vòng đời `StepExecutionListener`

Giao diện trong Spring Batch 5.x có dạng:

```java
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class ExampleStepListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // Được gọi trước khi logic xử lý của step bắt đầu.
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        // Được gọi sau khi logic xử lý step kết thúc,
        // kể cả khi xử lý thất bại theo vòng đời thông thường.
        return null;
    }
}
```

Các điểm cần ghi nhớ:

| Callback | Thời điểm | Dữ liệu có thể ghi | Lưu ý |
|---|---|---|---|
| `beforeStep(StepExecution)` | Trước khi step xử lý dữ liệu | Job name, job execution ID, step name, step execution ID, thông tin lần chạy đã được kiểm soát | Các count cuối cùng chưa có; không log là step đã thành công. |
| `afterStep(StepExecution)` | Sau khi logic step hoàn tất hoặc thất bại trong luồng thực thi thông thường | `BatchStatus`, `ExitStatus`, read/write/filter/skip/commit/rollback counts, duration, thông tin lỗi | Đây là thời điểm thích hợp để log kết quả step. |

`afterStep` trả về `ExitStatus` để **có thể ảnh hưởng đến exit code** của step: Spring Batch kết hợp giá trị trả về với `ExitStatus` hiện có thông qua `ExitStatus.and(...)`. Nếu listener **chỉ ghi log**, nên `return null;` để không cố ý thay đổi exit code. Đừng trả `ExitStatus.COMPLETED` một cách máy móc vì rất dễ khiến người đọc nhầm mục đích listener, và có thể tác động tới quy tắc flow tùy cách kết hợp status.

Theo API Spring Batch 5.x/6.x, ngoại lệ phát sinh từ `afterStep` sẽ được framework ghi nhận/log chứ **không được truyền ra như một lỗi làm thất bại step**. Do vậy, không dùng `afterStep` làm nơi xác thực bắt buộc phải ném exception mới hủy được kết quả batch; hãy đảm bảo logic logging gọn, chịu lỗi và không phụ thuộc vào network call dễ thất bại.

`beforeStep` thuộc luồng khởi động step. Nếu callback này ném exception, quá trình xử lý có thể bị gián đoạn; vì vậy, đừng đặt trong `beforeStep` các công việc không cần thiết như truy vấn báo cáo nặng, gọi HTTP đồng bộ hay tải danh sách hàng triệu bản ghi.

**Giới hạn của callback:** Khi process bị kill, mất điện, JVM crash hoặc hạ tầng chấm dứt bất thường, `afterStep` có thể không được gọi. Muốn phát hiện job bị treo/mất heartbeat, cần quan sát thêm trạng thái repository, metrics và cơ chế giám sát bên ngoài; log listener không phải bảo đảm tuyệt đối về bản ghi kết thúc.

## 3. `StepExecution` cung cấp những thông tin gì?

Đối tượng `StepExecution` là nguồn dữ liệu chính khi ghi log trong step listener.

| Giá trị | API Spring Batch 5.x | Ý nghĩa khi tìm log |
|---|---|---|
| Job name | `step.getJobExecution().getJobInstance().getJobName()` | Loại công việc đang chạy, ví dụ `dailySettlementJob`. |
| Job instance ID | `step.getJobExecution().getJobInstance().getInstanceId()` | Nhận diện instance logic của job. |
| Job execution ID | `step.getJobExecution().getId()` | Phân biệt các lần thực thi/restart của cùng instance. |
| Step name | `step.getStepName()` | Định danh step trong flow. |
| Step execution ID | `step.getId()` | Phân biệt lần thực thi step qua retry/restart và partition. |
| Batch status | `step.getStatus()` | Trạng thái framework như `COMPLETED`, `FAILED`, `STOPPED`. |
| Exit code | `step.getExitStatus().getExitCode()` | Mã kết quả mà flow transition có thể sử dụng. |
| Read count | `step.getReadCount()` | Số item được reader báo đã đọc. |
| Write count | `step.getWriteCount()` | Số item được writer báo đã ghi theo chunk. |
| Filter count | `step.getFilterCount()` | Số item được processor lọc bằng cách trả `null`. |
| Skip count | `step.getSkipCount()` | Tổng số skip ở các giai đoạn đọc, xử lý, ghi. |
| Commit count | `step.getCommitCount()` | Số lần commit trong step. |
| Rollback count | `step.getRollbackCount()` | Số lần rollback. |
| Failure exceptions | `step.getFailureExceptions()` | Các ngoại lệ framework đã ghi nhận cho lần thực thi step. |
| Start/end time | `step.getStartTime()`, `step.getEndTime()` | Tính khoảng thời gian thực thi khi hai mốc đều có giá trị. |

Các bộ đếm phản ánh cách Spring Batch cập nhật thống kê cho step. `readCount` không nhất thiết bằng `writeCount`: item có thể bị lọc, skip, hoặc có logic xử lý khác. Một **tasklet** tự chạy lệnh SQL `UPDATE` nhiều dòng cũng không tự làm `writeCount` tăng bằng số dòng SQL tác động. Hãy diễn giải count theo loại step thực tế.

`BatchStatus` và `ExitStatus` là hai khái niệm khác nhau:

```text
BatchStatus = trạng thái thực thi do framework ghi nhận
ExitStatus  = mã kết quả dùng cho flow/transition

Ví dụ:
  BatchStatus = COMPLETED
  ExitStatus  = COMPLETED WITH SKIPS
```

Không dùng `ExitStatus` thay thế hoàn toàn `BatchStatus` khi cần phân loại thành công/thất bại. Ngược lại, nếu flow có nhánh `.on("COMPLETED WITH SKIPS")`, chỉ log `BatchStatus.COMPLETED` có thể khiến người vận hành không hiểu tại sao job chuyển nhánh khác.

## 4. Ví dụ thực tế: listener ghi log bắt đầu và kết thúc step

Ví dụ sử dụng **Java 17+, SLF4J và Spring Batch 5.2.x**. Đối với dự án Spring Boot 3.x sử dụng starter thông thường, SLF4J API và Logback thường đã sẵn có, không cần tự gọi `System.out.println`.

```java
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public final class StepLoggingListener implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(StepLoggingListener.class);

    @Override
    public void beforeStep(StepExecution step) {
        log.info(
                "batch.step.started jobName={} jobExecutionId={} "
                        + "stepName={} stepExecutionId={}",
                jobName(step),
                step.getJobExecution().getId(),
                step.getStepName(),
                step.getId());
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        long durationMs = durationMillis(step);
        BatchStatus status = step.getStatus();
        String exitCode = step.getExitStatus().getExitCode();

        String message =
                "batch.step.finished jobName={} jobExecutionId={} "
                        + "stepName={} stepExecutionId={} status={} exitCode={} "
                        + "read={} written={} filtered={} skipped={} "
                        + "commits={} rollbacks={} durationMs={}";

        Object[] arguments = {
                jobName(step),
                step.getJobExecution().getId(),
                step.getStepName(),
                step.getId(),
                status,
                exitCode,
                step.getReadCount(),
                step.getWriteCount(),
                step.getFilterCount(),
                step.getSkipCount(),
                step.getCommitCount(),
                step.getRollbackCount(),
                durationMs
        };

        if (status == BatchStatus.COMPLETED) {
            log.info(message, arguments);
        } else {
            log.warn(message, arguments);
        }

        List<Throwable> failures = step.getFailureExceptions();
        if (!failures.isEmpty()) {
            Throwable firstFailure = failures.get(0);
            log.error(
                    "batch.step.error jobExecutionId={} stepExecutionId={} "
                            + "failureCount={} exceptionType={}",
                    step.getJobExecution().getId(),
                    step.getId(),
                    failures.size(),
                    firstFailure.getClass().getName(),
                    firstFailure);
        }

        return null; // Chỉ quan sát và ghi log, không thay đổi ExitStatus.
    }

    private static String jobName(StepExecution step) {
        return step.getJobExecution()
                .getJobInstance()
                .getJobName();
    }

    private static long durationMillis(StepExecution step) {
        LocalDateTime started = step.getStartTime();
        LocalDateTime ended = step.getEndTime();
        return (started != null && ended != null)
                ? Duration.between(started, ended).toMillis()
                : -1L;
    }
}
```

**Giải thích thiết kế:**

1. `LoggerFactory.getLogger(...)` tạo logger theo class để có thể cấu hình level riêng.
2. Dùng `{}` của SLF4J thay cho nối chuỗi liên tục; formatter chỉ cần xử lý các giá trị khi cấp log tương ứng được bật.
3. Luôn ghi **job execution ID** và **step execution ID** để tìm đúng lần chạy. Chỉ log `jobName`/`stepName` là chưa đủ vì cùng step có thể chạy lại nhiều lần.
4. Dùng `INFO` cho step hoàn thành, `WARN` cho trạng thái chưa hoàn thành bình thường; `ERROR` khi có ngoại lệ được lưu trong `StepExecution`.
5. Chỉ log exception đầu tiên và số lượng exception để tránh lặp stack trace quá nhiều trong một step bị lỗi nhiều item. Có thể chỉnh theo chính sách vận hành của hệ thống.
6. `durationMs = -1` trong ví dụ nghĩa là chưa có đủ start/end time để tính, thường gặp khi dựng metadata giả trong unit test. Không diễn giải `-1` là một duration thực.
7. `return null` bảo toàn mục đích quan sát, tránh vô tình thay đổi flow của job.

`afterStep` có thể chạy **trước khi mọi cập nhật cuối của `ExitStatus`/metadata được lưu vào repository**, đặc biệt khi có nhiều listener cùng tham gia. Log ở callback này là ảnh chụp của trạng thái tại thời điểm callback; nếu cần bảo đảm trạng thái đã được persist và toàn job đã kết thúc, cần kiểm tra `JobExecution`/`JobRepository` ở nơi thích hợp.

### 4.1. Ví dụ log đầu ra

```text
INFO  StepLoggingListener - batch.step.started jobName=dailySettlementJob jobExecutionId=701 stepName=calculateFees stepExecutionId=820
INFO  StepLoggingListener - batch.step.finished jobName=dailySettlementJob jobExecutionId=701 stepName=calculateFees stepExecutionId=820 status=COMPLETED exitCode=COMPLETED read=1200 written=1180 filtered=20 skipped=0 commits=13 rollbacks=0 durationMs=5384
```

Nếu bước xử lý gặp lỗi:

```text
INFO  StepLoggingListener - batch.step.started jobName=dailySettlementJob jobExecutionId=702 stepName=calculateFees stepExecutionId=821
WARN  StepLoggingListener - batch.step.finished jobName=dailySettlementJob jobExecutionId=702 stepName=calculateFees stepExecutionId=821 status=FAILED exitCode=FAILED read=450 written=400 filtered=0 skipped=0 commits=5 rollbacks=1 durationMs=2750
ERROR StepLoggingListener - batch.step.error jobExecutionId=702 stepExecutionId=821 failureCount=1 exceptionType=java.lang.IllegalStateException
```

Đây là **log minh họa**; các con số tùy theo cơ chế chunk, transaction và dữ liệu thật. Trong log của một `TaskletStep` không xử lý item theo chunk, bộ đếm read/write có thể bằng 0 dù tasklet có làm việc với database.

## 5. Đăng ký listener với step

Việc tạo class `StepLoggingListener` hoặc gắn `@Component` **không tự bảo đảm listener được gọi**. Listener phải được đăng ký vào cấu hình step (trực tiếp hoặc qua cơ chế listener registration mà ứng dụng dùng).

### 5.1. Đăng ký bằng Java Configuration

Ví dụ `TaskletStep` trong Spring Batch 5.x:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class ImportOrdersStepConfiguration {

    @Bean
    public StepLoggingListener stepLoggingListener() {
        return new StepLoggingListener();
    }

    @Bean
    public Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            StepLoggingListener loggingListener) {

        return new StepBuilder("importOrders", jobRepository)
                .tasklet((contribution, chunkContext) -> {
                    // Thay bằng logic nghiệp vụ phù hợp.
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .listener(loggingListener)
                .build();
    }
}
```

Một lời gọi tương tự có thể đặt trên `SimpleStepBuilder` của chunk-oriented step:

```java
return new StepBuilder("importOrders", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .listener(loggingListener)
        .build();
```

Đoạn thứ hai là **mẫu phần thân cấu hình bean**, giả định đã có `Order`, `orderReader`, `orderProcessor`, `orderWriter` và `loggingListener` với các kiểu tương thích. `JobRepository` và transaction manager phải được cấu hình phù hợp nếu step thực sự được chạy.

### 5.2. Dùng annotation `@BeforeStep` và `@AfterStep`

Thay vì triển khai interface, Spring Batch hỗ trợ các annotation dành cho callback:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.annotation.AfterStep;
import org.springframework.batch.core.annotation.BeforeStep;

public class AnnotatedStepLogCallbacks {

    private static final Logger log =
            LoggerFactory.getLogger(AnnotatedStepLogCallbacks.class);

    @BeforeStep
    public void onStart(StepExecution step) {
        log.info("batch.step.started stepName={} executionId={}",
                step.getStepName(), step.getId());
    }

    @AfterStep
    public ExitStatus onFinish(StepExecution step) {
        log.info("batch.step.finished stepName={} status={}",
                step.getStepName(), step.getStatus());
        return null;
    }
}
```

Với class chứa annotation callback, đăng ký instance vào step bằng overload phù hợp của `.listener(...)` để framework nhận diện annotation:

```java
AnnotatedStepLogCallbacks callbacks = new AnnotatedStepLogCallbacks();

// Khi tạo Step bằng builder:
new StepBuilder("importOrders", jobRepository)
        .tasklet(tasklet, transactionManager)
        .listener(callbacks)
        .build();
```

Trong dự án cần một listener dùng lại ở nhiều step, cách triển khai `StepExecutionListener` tường minh thường dễ tìm kiếm và bảo trì. Nếu một class đã có nhiều annotation lifecycle hoặc thuộc thành phần cần callback, dùng annotation có thể thuận tiện hơn. **Không đăng ký hai lần cùng callback** (chẳng hạn vừa qua interface vừa qua một cấu hình khác), vì có thể tạo log trùng.

## 6. Thiết kế cấu trúc thông điệp log

Một thông điệp log dễ tìm kiếm thường gồm **tên sự kiện cố định** và các trường ngữ cảnh thống nhất:

```text
batch.step.started  jobName=... jobExecutionId=... stepName=... stepExecutionId=...
batch.step.finished jobName=... jobExecutionId=... stepName=... stepExecutionId=... status=... exitCode=... read=... written=... durationMs=...
batch.step.error    jobExecutionId=... stepExecutionId=... exceptionType=...
```

Gợi ý trường log:

| Trường | Có nên có? | Lý do |
|---|---|---|
| `event`/tên sự kiện | Có | Tìm kiếm nhanh các log bắt đầu/kết thúc/lỗi. |
| `jobName` | Có | Tổng hợp theo loại batch. |
| `jobExecutionId` | Có | Truy vết một lượt thực thi job. |
| `stepName` | Có | Xác định vị trí trong flow. |
| `stepExecutionId` | Có | Phân biệt các lượt chạy lại hoặc partition. |
| `status`, `exitCode` | Có trong log kết thúc | Giải thích trạng thái và flow của step. |
| `read`, `written`, `filtered`, `skipped` | Có khi có item/chunk | Hỗ trợ đối soát dữ liệu. |
| `commits`, `rollbacks` | Có khi quan tâm transaction | Phát hiện rollback/retry bất thường. |
| `durationMs` | Nên có | Hỗ trợ điều tra hiệu năng. |
| `businessDate`/`tenantCode` | Tùy trường hợp | Chỉ log nếu không nhạy cảm và có quyền hiển thị. |
| Token, mật khẩu, thông tin khách hàng | Không | Tránh lộ dữ liệu trong hệ thống log. |

Không log nguyên `JobParameters`, nguyên `ExecutionContext`, item payload hay toàn bộ `StepExecution.toString()` theo mặc định. Các đối tượng này có thể chứa nội dung nhạy cảm, thông tin truy cập, đường dẫn riêng hoặc lượng dữ liệu quá lớn. Nếu muốn log ngày nghiệp vụ, hãy lấy **một key đã được phép hiển thị** và xác định rõ việc key đó có phải dữ liệu nhạy cảm trong hệ thống của bạn hay không.

### 6.1. INFO, WARN, ERROR và DEBUG

| Level | Nên dùng khi | Ví dụ |
|---|---|---|
| `INFO` | Một step bắt đầu hoặc hoàn thành thông thường | `batch.step.started`, `status=COMPLETED`. |
| `WARN` | Step không hoàn thành bình thường, skip tăng hoặc trạng thái cần theo dõi | `status=STOPPED`, `status=FAILED` trong log tổng kết. |
| `ERROR` | Thực sự có ngoại lệ/lỗi cần điều tra | `batch.step.error` kèm exception có kiểm soát. |
| `DEBUG` | Truy vết chi tiết phục vụ phát triển hoặc phân tích sự cố | Chi tiết chunk, thông số đã làm sạch dữ liệu nhạy cảm. |
| `TRACE` | Truy vết rất sâu, hiếm khi bật ở production | Thông tin tần suất cao dưới kiểm soát riêng. |

**Không log mỗi item ở `INFO`** trong một job hàng triệu bản ghi. Mẫu này tạo lượng log lớn, gây chi phí lưu trữ/thu thập và đôi khi làm chậm cả quá trình xử lý. Log tổng kết tại step listener và chỉ bổ sung chi tiết qua item/chunk listeners ở cấp phù hợp.

## 7. Cấu hình logging trong Spring Boot

Với Spring Boot 3.x, có thể đặt level riêng cho package chứa listener:

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: order-batch

logging:
  level:
    root: INFO
    com.example.batch.listener: INFO
    org.springframework.batch: INFO
```

Đổi `com.example.batch.listener` theo package thật. Spring Boot mặc định thường ghi log ra console và dùng Logback khi sử dụng starters thông dụng. Không cần tự thêm dependency logging mới nếu starter đã cung cấp SLF4J backend.

Khi cần kiểm tra sâu vấn đề trong môi trường test, có thể bật debug **chỉ ở profile test**:

```yaml
# src/test/resources/application-test.yml
logging:
  level:
    com.example.batch.listener: DEBUG
    org.springframework.batch.core: DEBUG
```

Nên cấu hình level tối thiểu đủ phục vụ chẩn đoán. Việc bật `DEBUG` toàn bộ framework hoặc SQL trong production có thể làm log nhiều dữ liệu hơn dự kiến.

### 7.1. Structured logging

Khi log được gửi đến hệ thống tập trung như Elastic Stack, OpenSearch, Loki hoặc một nền tảng observability, **JSON có trường cố định** thường thuận tiện hơn việc tách chuỗi thuần bằng regex.

Với các phiên bản Spring Boot hỗ trợ structured logging trực tiếp (chẳng hạn Boot 3.4+), có thể sử dụng:

```yaml
logging:
  structured:
    format:
      console: ecs
```

`ecs` biểu diễn định dạng Elastic Common Schema. Nếu môi trường dùng Logback encoder hoặc backend tùy chỉnh, cần cấu hình encoder phù hợp; property trên không nhất thiết có hiệu lực với mọi appender tự viết. Khi chạy trong container, ghi JSON ra stdout thường giúp log collector thu thập dễ dàng hơn so với quản lý file cục bộ bên trong container.

Tại cấp code, tên event và các key phải có ngữ nghĩa ổn định. Có thể dùng SLF4J 2 fluent API để cung cấp key-value pair khi backend/encoder được cấu hình hỗ trợ:

```java
log.atInfo()
        .addKeyValue("event", "batch.step.started")
        .addKeyValue("jobExecutionId", step.getJobExecution().getId())
        .addKeyValue("stepExecutionId", step.getId())
        .log("Step started");
```

Đoạn này sử dụng **SLF4J 2.x**. Tùy phiên bản logging backend, cấu hình encoder và hệ thống lưu trữ, các key-value pair có thể hiển thị dưới dạng trường JSON hoặc trong phần message. Cần xem log thực tế để xác nhận định dạng mong muốn.

## 8. Truy vết bằng MDC (Mapped Diagnostic Context)

Trong log tập trung, thường muốn lọc mọi dòng thuộc một `jobExecutionId` hoặc `stepExecutionId`. SLF4J `MDC` cho phép đặt một vài giá trị ngữ cảnh theo **thread hiện tại**; logging backend có thể đưa các giá trị này vào pattern hoặc JSON output.

Ví dụ dùng MDC đúng phạm vi một callback:

```java
import org.slf4j.MDC;

public void logStepStart(StepExecution step) {
    try (MDC.MDCCloseable jobId = MDC.putCloseable(
                 "jobExecutionId",
                 String.valueOf(step.getJobExecution().getId()));
         MDC.MDCCloseable stepId = MDC.putCloseable(
                 "stepExecutionId",
                 String.valueOf(step.getId()))) {

        log.info("batch.step.started jobName={} stepName={}",
                step.getJobExecution().getJobInstance().getJobName(),
                step.getStepName());
    }
}
```

Với Logback pattern logging, có thể hiển thị các key MDC:

```yaml
logging:
  pattern:
    console: "%d{yyyy-MM-dd HH:mm:ss.SSS} %-5level [%thread] jobExecutionId=%X{jobExecutionId} stepExecutionId=%X{stepExecutionId} %logger{36} - %msg%n"
```

Khi backend hỗ trợ JSON structured logging, MDC cũng có thể được đưa vào các trường của JSON tùy cấu hình.

**Cảnh báo quan trọng:** MDC thường là dữ liệu local của thread. Đặt MDC trong `beforeStep` rồi xóa trong `afterStep` không tự động truyền giá trị tới các thread của partitioned step, multi-threaded step hoặc asynchronous processor/writer. Cách đó còn dễ rò MDC nếu một callback không chạy như dự kiến. `MDC.putCloseable(...)` giới hạn ngữ cảnh trong một block rõ ràng. Nếu cần correlation xuyên thread, hãy thiết kế `TaskDecorator`/propagation riêng và dọn context sau khi task kết thúc. Đừng giả định MDC tự đi theo mọi luồng xử lý của Spring Batch.

### 8.1. Chọn khóa định danh phù hợp

- `jobName`/`stepName`: thuận tiện nhóm nhiều lượt chạy cùng loại.
- `jobExecutionId`: xác định một lần chạy job cụ thể; restart sinh execution mới.
- `stepExecutionId`: xác định một lần thực thi step cụ thể, kể cả partition hoặc restart.
- `jobInstanceId`: hữu ích khi muốn gom các lần retry/restart của cùng một job instance logic.
- `businessDate` hoặc business key: chỉ thêm khi được phép log; nên giữ key này tường minh và tránh ghi cả map tham số.

Một `jobExecutionId` có thể có nhiều step execution; một step name có thể xuất hiện ở nhiều job execution. Kết hợp các ID là cách đáng tin cậy hơn để điều tra luồng chạy.

## 9. Chọn listener phù hợp với loại sự kiện

`StepExecutionListener` nên tập trung vào bức tranh tổng thể của step. Các listener khác bổ sung thông tin tại ranh giới nhỏ hơn:

| Listener | Callback tiêu biểu | Dùng để log gì? |
|---|---|---|
| `StepExecutionListener` | `beforeStep`, `afterStep` | Bắt đầu/kết thúc step, counters, trạng thái. |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | Kết quả từng chunk, thời gian commit, lỗi chunk/transaction. |
| `ItemReadListener` | `beforeRead`, `afterRead`, `onReadError` | Vấn đề phát sinh ở reader. |
| `ItemProcessListener<I,O>` | `beforeProcess`, `afterProcess`, `onProcessError` | Lỗi chuyển đổi/validation của processor. |
| `ItemWriteListener<T>` | `beforeWrite`, `afterWrite`, `onWriteError` | Lỗi ghi dữ liệu của writer. |
| `SkipListener<T,S>` | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Các item bị bỏ qua theo chính sách fault tolerance. |
| `JobExecutionListener` | `beforeJob`, `afterJob` | Vòng đời toàn job và tổng hợp qua nhiều step. |

Ví dụ muốn log **số lượng item bị skip cuối step** mà không ghi từng item:

```java
@Override
public ExitStatus afterStep(StepExecution step) {
    if (step.getSkipCount() > 0) {
        log.warn(
                "batch.step.skipped stepExecutionId={} readSkips={} "
                        + "processSkips={} writeSkips={} totalSkips={}",
                step.getId(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount());
    }
    return null;
}
```

Đây là **một phương án callback thay thế/minh họa**, không nên bổ sung một `afterStep` thứ hai vào chính class `StepLoggingListener` đã có method cùng chữ ký. Nếu cần log thêm skip counters trong class ở mục 4, hãy ghép phần thân vào `afterStep` hiện có. Khi cần biết bản ghi nào bị skip, dùng `SkipListener` và chỉ ghi định danh kỹ thuật được phép hiển thị.

### 9.1. Không suy diễn các counter

Nếu `readCount=100`, `writeCount=80`, `filterCount=20`, có thể processor đã lọc 20 item. Nhưng nếu `skipCount>0` hoặc writer biến đổi logic, quan hệ giữa các counter có thể khác. Đừng đặt một cảnh báo tổng quát như “readCount khác writeCount là lỗi” cho mọi step; cần hiểu đặc điểm reader/processor/writer và chính sách skip/retry.

`rollbackCount` tăng chưa hẳn là job thất bại cuối cùng; với fault-tolerant step, một số rollback có thể xảy ra trong quá trình retry rồi step vẫn `COMPLETED`. Log count kết hợp với trạng thái và thời gian sẽ hữu ích hơn log mỗi count riêng lẻ.

## 10. Ghi log lỗi và exception an toàn

Khi `StepExecution` đã có `failureExceptions`, logging listener có thể ghi stack trace để phục vụ điều tra. Nhưng cần tránh ba sai lầm phổ biến:

1. **Log lặp ngoại lệ quá nhiều lần.** Nếu `ItemReadListener`, `ChunkListener`, catch block của tasklet và `StepExecutionListener` đều ghi cùng stack trace ở `ERROR`, hệ thống log sẽ nhiều dòng trùng nhau. Quy ước rõ nơi ghi log lỗi chi tiết; các callback khác có thể chỉ ghi mã lỗi và ID.
2. **Đưa dữ liệu nhạy cảm vào exception message.** SQL exception hoặc HTTP exception có thể chứa payload, connection details hay nội dung người dùng. Trước khi bật stack trace trong production, xác định chính sách masking/redaction ở logger/backend.
3. **Che giấu lỗi bằng catch rồi trả `COMPLETED`.** Nếu listener chỉ có trách nhiệm log, hãy trả `null`. Không âm thầm sửa `ExitStatus` của step để tránh báo lỗi.

Ví dụ ghi log lỗi tối giản, không in payload:

```java
List<Throwable> failures = step.getFailureExceptions();
if (!failures.isEmpty()) {
    Throwable cause = failures.get(0);
    log.error("batch.step.error jobExecutionId={} stepExecutionId={} type={}",
            step.getJobExecution().getId(),
            step.getId(),
            cause.getClass().getSimpleName());
}
```

Mẫu này chỉ log **loại exception**, không ghi stack trace. Khi cần stack trace phục vụ vận hành, thêm throwable ở đối số cuối như trong ví dụ mục 4 và bảo đảm hệ thống log được kiểm soát truy cập.

Nếu muốn bước batch thất bại vì kết quả kiểm tra nghiệp vụ không đạt, hãy thực hiện quyết định đó trong xử lý step hoặc thiết kế `ExitStatus`/flow một cách tường minh. Listener ghi log chỉ phản ánh trạng thái đã xảy ra; không nên khiến log trở thành nguồn quyết định thay cho business logic.

## 11. Log và transaction trong step

Một step chunk-oriented thường mở transaction cho từng chunk. Khi step listener ghi `batch.step.finished`, metadata có thể cho biết nhiều transaction đã commit và rollback. Tuy nhiên, **log và database transaction là hai hệ thống khác nhau**:

```text
Chunk 1: ghi database -> commit thành công
Chunk 2: ghi database -> rollback

Log ở stdout/appender có thể đã được ghi trước khi rollback.
```

Vì vậy, sự tồn tại của dòng `INFO: writer processed item 123` không chứng minh item 123 đã được commit vào database. Kiểm tra `writeCount`, `commitCount`, `rollbackCount` cùng trạng thái cuối và dữ liệu thực tế. Nếu một kết quả phải được phát sự kiện chính xác một lần sau commit, dùng cơ chế phù hợp như transactional outbox hoặc cơ chế event sau commit thay vì dựa vào thứ tự log.

Trong `afterStep`, tránh khởi động một transaction phức tạp để cập nhật lại dữ liệu nghiệp vụ chỉ nhằm “đánh dấu log”. Công việc nghiệp vụ cần nằm trong các thành phần xử lý step thích hợp để quản lý rollback/restart nhất quán.

## 12. Restart, partitioning và xử lý song song

### 12.1. Restart tạo log mới

Khi cùng một `JobInstance` được restart sau thất bại, thường có **`JobExecution` mới**. Một step cần chạy lại cũng có `StepExecution` mới, dù `jobName` và `stepName` giữ nguyên.

```text
jobName=dailySettlementJob jobInstanceId=50
  jobExecutionId=701
    stepName=calculateFees stepExecutionId=820 status=FAILED
  jobExecutionId=703
    stepName=calculateFees stepExecutionId=824 status=COMPLETED
```

Nếu chỉ tìm theo tên step, rất dễ nhầm kết quả của lần chạy cũ với lần chạy lại. Các log nên có execution ID rõ ràng. Khi truy vết restart xuyên nhiều execution, bổ sung `jobInstanceId` nếu chính sách observability có nhu cầu.

### 12.2. Partitioned step

Trong partitioning, manager step có thể chia công việc cho nhiều worker step executions. Tên step có thể kèm hậu tố phân vùng và các execution ID khác nhau. Nếu ghi log tại từng worker:

```text
batch.step.started stepName=loadCustomers:partition0 stepExecutionId=901
batch.step.started stepName=loadCustomers:partition1 stepExecutionId=902
batch.step.finished stepName=loadCustomers:partition0 stepExecutionId=901 status=COMPLETED
batch.step.finished stepName=loadCustomers:partition1 stepExecutionId=902 status=COMPLETED
```

Các dòng có thể xen kẽ do concurrency; đây không phải dấu hiệu lỗi. Cần truy vết bằng ID/partition key thay vì dựa vào thứ tự xuất hiện trên console. Với **remote partitioning**, worker có thể nằm trên JVM hoặc service khác nên cần log aggregator/trace id chung.

### 12.3. Multi-threaded step

Một `StepExecutionListener` có thể được gọi ở thread điều phối step, trong khi reader/processor/writer thực thi trên các thread khác. Đây là lý do không mặc định giữ metadata trong một biến instance mutable của singleton listener hay tin rằng MDC tự lan đến tất cả thread. Ưu tiên lấy metadata từ `StepExecution` được truyền vào callback. Với các callback item chạy song song, cần giải pháp correlation theo thread/task cụ thể.

### 12.4. Không suy luận thứ tự tuyệt đối từ timestamp

Khi log được thu thập từ nhiều replica, thread hoặc host, clock skew và độ trễ thu thập có thể làm thứ tự dòng log không phản ánh thứ tự nhân quả tuyệt đối. ID thực thi và sequence/sự kiện nghiệp vụ hỗ trợ điều tra tốt hơn so với chỉ nhìn giờ log.

## 13. Kiểm thử step listener ghi log

Vì `StepExecutionListener` nhận đối tượng metadata và không cần tự chạy batch, ta có thể unit test việc định dạng log bằng `MetaDataInstanceFactory` trong `spring-batch-test`.

### 13.1. Dependencies

Ví dụ Gradle Groovy trong Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot Starter Test có `OutputCaptureExtension` hỗ trợ bắt stdout/stderr được ghi bởi console logging trong test. Kết quả phụ thuộc cấu hình logger và appender thực tế: nếu test tắt console appender hoặc đặt level cao hơn `INFO`, cần điều chỉnh assertion/config cho phù hợp.

### 13.2. Unit test với `OutputCaptureExtension`

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertNull;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

@ExtendWith(OutputCaptureExtension.class)
class StepLoggingListenerTest {

    private final StepLoggingListener listener = new StepLoggingListener();

    @Test
    void logsStartAndFinishWithExecutionIds(CapturedOutput output) {
        StepExecution step = MetaDataInstanceFactory
                .createStepExecution("importOrders", 901L);
        step.setStatus(BatchStatus.COMPLETED);
        step.setReadCount(10);
        step.setWriteCount(9);
        step.setFilterCount(1);

        listener.beforeStep(step);
        assertNull(listener.afterStep(step));

        assertThat(output.getOut())
                .contains("batch.step.started")
                .contains("batch.step.finished")
                .contains("stepName=importOrders")
                .contains("stepExecutionId=901")
                .contains("read=10")
                .contains("written=9");
    }
}
```

Ở đây `MetaDataInstanceFactory` **chỉ dựng metadata giả**. `listener.beforeStep(...)` và `listener.afterStep(...)` được gọi trực tiếp; không có job hoặc reader thật chạy. `assertNull(...)` chứng minh listener không yêu cầu đổi exit code. Kiểm tra log ở unit test giúp bảo đảm tên event/các trường ID, nhưng không thay thế integration test xác nhận listener đã đăng ký đúng với step thật.

### 13.3. Integration test: listener thực sự được gọi khi chạy step

Khi test cần bảo đảm Spring Batch gọi listener qua step configuration, hãy sử dụng `@SpringBatchTest`, `@SpringBootTest`, `JobLauncherTestUtils` và database repository dành riêng cho test. Ví dụ phần cốt lõi:

```java
@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
class StepLoggingIntegrationTest {

    @Autowired
    JobLauncherTestUtils launcherTestUtils;

    @Autowired
    @Qualifier("importOrdersJob")
    Job job;

    @Test
    void stepRunsAndListenerIsInvoked() throws Exception {
        launcherTestUtils.setJob(job);

        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(params);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        // Bổ sung OutputCaptureExtension hoặc test appender nếu cần
        // khẳng định cụ thể sự kiện batch.step.started/finished.
    }
}
```

Đây là **khung test tích hợp**: giả định đã có bean job tên `importOrdersJob`, datasource test, metadata schema và các import Java tương ứng. Chỉ assertion `COMPLETED` chưa chứng minh message log được phát ra; muốn kiểm chứng log end-to-end, cần bắt log bằng `OutputCaptureExtension` hoặc appender test và assert nội dung mong muốn. Nếu chạy nhiều test có cùng identifying parameters trong một repository, cần cleanup metadata hoặc tách database để tránh `JobInstanceAlreadyCompleteException`.

## 14. Truy vết một lần chạy từ log đến database metadata

Log ở step listener có thể liên kết với bảng metadata của JDBC `JobRepository`. Ví dụ một dòng log có:

```text
jobExecutionId=701 stepExecutionId=820 status=FAILED
```

Trong Spring Batch 5.x, có thể truy vấn:

```sql
SELECT
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS,
    se.EXIT_CODE,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.ROLLBACK_COUNT,
    je.JOB_EXECUTION_ID,
    ji.JOB_NAME
FROM BATCH_STEP_EXECUTION se
JOIN BATCH_JOB_EXECUTION je
    ON se.JOB_EXECUTION_ID = je.JOB_EXECUTION_ID
JOIN BATCH_JOB_INSTANCE ji
    ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE se.STEP_EXECUTION_ID = 820;
```

Trong production, dùng prepared statements/bind parameters nếu nhận execution ID từ request hoặc script. Chỉ nên **đọc** metadata để điều tra; không sửa trực tiếp `BATCH_STEP_EXECUTION.STATUS`, `EXIT_CODE` hay `BATCH_*_CONTEXT` để cố làm log trông đúng. Các giá trị framework quản lý có thể liên quan đến version và quy tắc restart.

Một cách xử lý sự cố có hệ thống:

1. Lọc log `batch.step.finished` hoặc `batch.step.error` theo `jobName`, khoảng thời gian và môi trường.
2. Lấy `jobExecutionId` và `stepExecutionId`, tìm mọi log liên quan tới execution đó.
3. Xem `status`, `exitCode`, `read/write/skip`, `rollbackCount`, `durationMs` và exception type.
4. Truy vấn metadata/báo cáo vận hành tương ứng nếu cần xác nhận trạng thái đã lưu.
5. So sánh với dữ liệu đầu ra đã commit, và xác định có cần restart theo cùng identifying parameters hay không.

## 15. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
|---|---|---|
| Không thấy log `beforeStep`/`afterStep` | Listener chưa được đăng ký hoặc step không được chạy | Kiểm tra `.listener(...)`, job flow và logging level. |
| `@Component` có nhưng callback không chạy | Bean được tạo nhưng không liên kết với step | Đăng ký listener vào step cụ thể. |
| Chỉ thấy log bắt đầu, không thấy kết thúc | JVM/process bị dừng bất thường, callback không được gọi hoặc log collector mất dữ liệu | Kiểm tra repository, lifecycle ứng dụng và hạ tầng log. |
| Log cuối báo `COMPLETED` nhưng flow đi nhánh khác | `ExitStatus` có mã custom hoặc listener khác thay đổi exit code | Log cả `BatchStatus` và `ExitStatus`, kiểm tra thứ tự/cấu hình listener. |
| Step fail nhưng `afterStep` không ném lỗi ra ngoài | Exception trong `afterStep` chỉ được ghi log | Thực hiện validation có tác động đến status ở vị trí phù hợp, tránh đặt trong logging callback. |
| `readCount` khác `writeCount` | Có filter/skip hoặc semantics khác với đếm item | Kiểm tra processor và fault-tolerant policy. |
| `writeCount=0` dù SQL update nhiều dòng | Tasklet tự chạy SQL, không cập nhật batch item counters | Log thêm số row từ `JdbcTemplate.update(...)` trong logic phù hợp nếu cần. |
| Log trùng nhiều lần | Cùng listener được đăng ký lặp, hoặc nhiều listener cùng ghi một sự kiện | Rà soát cấu hình listener, thống nhất tên event và cấp log. |
| Không có `jobExecutionId` trong log của thread xử lý | MDC không tự truyền giữa thread | Gắn correlation tại boundary thích hợp, sử dụng cơ chế propagation. |
| Unit test không thấy log dù callback chạy | Logger/appender bị tắt hoặc level quá cao | Kiểm tra cấu hình `logging.level`, console appender và test capture. |
| Log làm job chậm | Ghi per-item quá nhiều hoặc appender đồng bộ có I/O chậm | Log theo step/chunk, dùng log level hợp lý và đánh giá logging pipeline. |
| Log lộ nội dung nhạy cảm | In toàn bộ `JobParameters`, context, payload hoặc exception message | Chỉ dùng allowlist metadata, masking, phân quyền log. |

## 16. Thực hành: thêm log vào một job có nhiều step

Giả sử job `nightlyImportJob` gồm ba step: `downloadFiles`, `validateRecords`, `saveRecords`.

**Bài 1 — Thêm log vòng đời:**

- Tạo `StepLoggingListener` triển khai `StepExecutionListener`.
- Ghi `jobName`, `jobExecutionId`, `stepName`, `stepExecutionId` trong `beforeStep`.
- Ghi trạng thái, exit code, read/write/filter/skip, commit/rollback và duration trong `afterStep`.
- Trả `null` ở `afterStep` để log không thay đổi kết quả nghiệp vụ.
- Đăng ký listener cho cả ba step, chạy job và quan sát ba cặp log bắt đầu/kết thúc.

**Bài 2 — Tình huống thất bại:**

- Cố ý làm `validateRecords` thất bại, quan sát `BatchStatus.FAILED` cùng exception trong `StepExecution`.
- So sánh `beforeStep`/`afterStep` với sự kiện `onProcessError` hoặc `onSkipInProcess` nếu dùng chunk-oriented step.
- Sửa điều kiện lỗi và restart job với cùng identifying parameters; quan sát `jobExecutionId`/`stepExecutionId` mới.

**Bài 3 — Chẩn đoán khi xử lý song song:**

- Cho `saveRecords` có hai partition hoặc nhiều thread (nếu ứng dụng hỗ trợ).
- Bổ sung correlation ID vào log và xác minh rằng các dòng có thể xen kẽ nhưng vẫn tìm được theo execution ID.
- Thử đặt MDC trong block `try-with-resources` và chứng minh metadata đó không tự xuất hiện ở thread khác nếu không có propagation.

**Bài 4 — Kiểm thử log tự động:**

- Dùng `MetaDataInstanceFactory` tạo `StepExecution` có `readCount=100`, `writeCount=95`, `filterCount=5`.
- Dùng `OutputCaptureExtension` xác minh các field được log đúng và `afterStep` trả `null`.
- Thử `BatchStatus.FAILED`, thiết lập một failure exception, rồi kiểm tra log level/tên event và thông tin lỗi có trong output.

## 17. Nguyên tắc áp dụng trong dự án thực tế

Một listener logging hữu ích thường tuân theo các nguyên tắc sau:

1. **Mỗi lần thực thi step có ID riêng trong log.** Nhờ đó có thể phân biệt lần chạy đầu, restart và partition.
2. **Tên event và key cố định.** Khi tìm kiếm/đặt alert, không phụ thuộc vào một câu văn có thể thay đổi tùy người viết code.
3. **Log số liệu tổng hợp ở cấp step.** Chỉ bật log theo item khi cần điều tra và đã tính đến chi phí.
4. **Không tác động đến điều khiển flow.** `afterStep` chỉ để log trả `null`; business decision nên có listener/logic riêng và được kiểm thử rõ ràng.
5. **Ghi cả status lẫn exit code.** Chúng có mục đích khác nhau khi job dùng conditional flow.
6. **Giới hạn dữ liệu xuất ra.** Không đẩy secret, dữ liệu người dùng hoặc toàn bộ context vào hệ thống log.
7. **Xem log là kênh quan sát, không phải transaction log.** Xác nhận commit và restart bằng repository, transaction và dữ liệu thực.
8. **Cân nhắc thất bại ngoài ý muốn.** `afterStep` không được bảo đảm trong trường hợp process crash; cần monitoring bên ngoài.
9. **Kiểm thử cả unit lẫn wiring khi cần.** Unit test định dạng log; integration test chứng minh listener thực sự được gắn vào step.

## 18. Tài liệu tham khảo chính thức

- [Spring Batch Reference — Intercepting Step Execution](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/intercepting-execution.html): giao diện `StepExecutionListener`, các callback `ChunkListener`, `Item*Listener` và `SkipListener`.
- [Spring Batch 5.2 — `StepExecutionListener` Javadoc](https://docs.spring.io/spring-batch/docs/5.2.7/api/org/springframework/batch/core/StepExecutionListener.html): hợp đồng `beforeStep`, `afterStep`, trả `null` và cách xử lý exception.
- [Spring Batch 6.x — `StepExecutionListener` Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/listener/StepExecutionListener.html): thay đổi package ở dòng Spring Batch 6.
- [Spring Batch Reference — Controlling Step Flow](https://docs.spring.io/spring-batch/reference/step/controlling-flow.html): sự khác biệt giữa `BatchStatus` và `ExitStatus`.
- [Spring Boot Reference — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): cấu hình log level, Logback, console appender và structured logging.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): các cách quan sát hoạt động batch bổ sung cho log listener.

