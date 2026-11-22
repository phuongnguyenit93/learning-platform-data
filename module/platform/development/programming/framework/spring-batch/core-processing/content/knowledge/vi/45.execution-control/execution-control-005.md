# Operator restart job failed — khởi động lại job thất bại trong Spring Batch

## 1. Bài toán: job đã FAILED, làm sao chạy tiếp đúng lần xử lý cũ?

Trong hệ thống batch, một lần chạy có thể thất bại vì mất kết nối database, tệp đầu vào chưa sẵn sàng, API bên ngoài quá tải, lỗi xác thực tạm thời hoặc dữ liệu không đáp ứng điều kiện kiểm tra. Sau khi sửa nguyên nhân, người vận hành cần quyết định **tiếp tục đúng công việc đã thất bại** hay **mở một đợt xử lý hoàn toàn mới**.

Spring Batch cung cấp interface **`JobOperator`** để quan sát và điều khiển job từ một entry point có thể dùng trong ứng dụng, lệnh quản trị hoặc hệ thống vận hành. Với Spring Batch 5.x, thao tác trọng tâm của bài này là:

```java
Long newExecutionId = jobOperator.restart(failedExecutionId);
```

Phương thức này yêu cầu framework **restart một `JobExecution` đang ở trạng thái thất bại hoặc đã dừng**. Spring Batch tìm metadata đã lưu, xác định `JobInstance` liên quan, kiểm tra điều kiện restart và tạo một `JobExecution` mới cho **cùng `JobInstance`**. Những step đã hoàn thành trước đó thường không bị chạy lại; step chưa hoàn thành có thể sử dụng `ExecutionContext` đã lưu để tiếp tục theo chính sách của step.

> **Phân biệt cốt lõi:** `restart` không phải “chạy lại mọi thứ từ đầu”. Nó là thao tác tiếp tục một `JobInstance` dựa vào lịch sử thực thi và metadata hiện có. Muốn bắt đầu một đợt xử lý độc lập, cần một `JobInstance` mới với identifying `JobParameters` khác.

Sau bài này, bạn có thể:

- Giải thích quan hệ giữa `JobInstance`, `JobExecution`, `StepExecution` và các tham số khi restart.
- Dùng `JobOperator.restart(long executionId)` trong Spring Batch 5.x với điều kiện và xử lý lỗi phù hợp.
- Xác định trạng thái nào restart được và trạng thái nào phải giải quyết trước.
- Kiểm tra việc bỏ qua step đã `COMPLETED`, khôi phục checkpoint cho step thất bại và giữ nguyên dữ liệu nghiệp vụ.
- Viết integration test restart thông qua `JobOperator` với metadata repository thật.
- Thiết kế luồng vận hành có thể quan sát, tránh khởi chạy trùng và hạn chế tác động khi job làm một phần công việc.
- Nhận diện khác biệt API trong Spring Batch 6.x.

Các ví dụ Java dùng **Java 17+, Spring Boot 3.x và Spring Batch 5.x**. Khi dùng Spring Batch 6.x, cần đổi API restart như ghi chú ở cuối bài.

---

## 2. Mô hình metadata quyết định hành vi restart

### 2.1. `JobInstance` là một đợt xử lý logic

Một `JobInstance` được định danh bởi **tên job** kết hợp với tập **identifying job parameters**.

Ví dụ:

```text
Job name:       invoiceImportJob
businessDate:   2026-11-16  (identifying)
tenantId:       company-A   (identifying)
traceId:        trace-7391 (non-identifying)

=> JobInstance #41
```

Nếu lần chạy cho `JobInstance #41` thất bại, ta có thể tạo thêm một `JobExecution` để tiếp tục xử lý đúng business date và tenant đó. Một lần chạy với identifying parameters khác thường tương ứng `JobInstance` mới.

**`JobExecution` không phải `JobInstance`.** Mỗi lần thực thi/restart được ghi thành một execution riêng:

```text
JobInstance #41: invoiceImportJob + businessDate + tenantId
    |
    +-- JobExecution #810 (FAILED)
    |      |
    |      +-- StepExecution prepareStep  (COMPLETED)
    |      +-- StepExecution importStep   (FAILED)
    |
    +-- JobExecution #811 (COMPLETED, sau restart)
           |
           +-- prepareStep: thường được bỏ qua
           +-- StepExecution importStep   (COMPLETED)
```

Ở đây, **`JobInstance` giữ nguyên**, **`JobExecution` mới được tạo**, và Spring Batch dựa vào trạng thái các step đã lưu trong repository để quyết định chạy tiếp.

### 2.2. Các thành phần tham gia

| Thành phần | Vai trò trong restart |
| --- | --- |
| `JobOperator` | Entry point vận hành: `restart`, `stop`, `getSummary`, `getRunningExecutions` và thao tác điều khiển khác |
| `JobRepository` | Lưu trạng thái job/step, liên kết instance và execution, quản lý persistence/checkpoint |
| `JobExplorer` | Đọc metadata để kiểm tra execution hiện tại và lịch sử chạy |
| `JobRegistry` / `JobLocator` | Giúp operator tìm lại định nghĩa `Job` theo tên đã lưu trong metadata |
| `JobLauncher` | Được hạ tầng dùng để khởi chạy job phù hợp |
| `ExecutionContext` | Lưu dữ liệu restart như reader offset, trang dữ liệu, checkpoint và trạng thái step |
| `ItemStream` | Khôi phục trạng thái ở `open()`, ghi checkpoint ở `update()` nếu được đăng ký với step |

Một lần restart yêu cầu **định nghĩa job vẫn sẵn có** và **metadata của lần chạy cũ vẫn còn và phù hợp**. Nếu mỗi lần ứng dụng khởi động lại dùng một in-memory repository mới, job sẽ mất lịch sử cần thiết để tiếp tục sau khi process cũ chết.

### 2.3. Restart so với chạy mới

| Thao tác | Đầu vào | `JobInstance` | `JobExecution` | Ý nghĩa |
| --- | --- | --- | --- | --- |
| `jobOperator.restart(failedExecutionId)` | ID execution thất bại/đã dừng | Giữ nguyên instance cũ | Tạo execution mới | Tiếp tục công việc trước đó theo metadata |
| `jobLauncher.run(job, sameParameters)` | `Job` + parameters cũ | Có thể cùng instance nếu restart hợp lệ | Tạo execution mới | Framework có thể restart nhưng caller phải có `Job`/parameters phù hợp |
| `jobOperator.startNextInstance(jobName)` | Tên job có incrementer | Tạo instance mới | Tạo execution mới | Chạy đợt tiếp theo với parameters mới |
| `jobLauncher.run(job, newParameters)` | `Job` + identifying parameters khác | Tạo instance mới | Tạo execution mới | Chạy công việc độc lập |
| `jobOperator.stop(executionId)` | ID execution đang chạy | Không đổi | Tác động execution hiện tại | Gửi yêu cầu dừng mềm, không phải restart |

Ví dụ: tăng `run.id` hoặc thêm timestamp định danh mới rồi chạy job không phải là restart, vì `JobInstance` mới sẽ không tự dùng checkpoint của instance cũ.

---

## 3. Những trạng thái nào cho phép restart?

Spring Batch quản lý trạng thái thực thi bằng enum `BatchStatus`. Operator cần kiểm tra trạng thái thực tế ở **metadata repository**, bởi metadata có thể khác với thông tin trên dashboard hoặc log đã trễ.

| `BatchStatus` | Ý nghĩa vận hành | Hướng xử lý |
| --- | --- | --- |
| `FAILED` | Execution thất bại | Có thể restart khi job cho phép, metadata hợp lệ và không có execution mới hơn đang chạy/đã hoàn thành |
| `STOPPED` | Execution đã dừng hợp lệ | Có thể restart theo chính sách flow/step |
| `COMPLETED` | Instance đã xử lý thành công | Không restart; nếu cần đợt mới, tạo instance mới |
| `STARTING` / `STARTED` | Execution đang khởi tạo/đang chạy | Không restart; kiểm tra tiến trình thật, chờ hoàn tất hoặc yêu cầu stop |
| `STOPPING` | Đã yêu cầu dừng nhưng chưa kết thúc | Chờ `STOPPED`; tín hiệu stop không đồng nghĩa dừng xong |
| `ABANDONED` | Execution bị đánh dấu bỏ qua/không tiếp tục | Không restart execution này theo framework |
| `UNKNOWN` | Trạng thái không xác định hoặc metadata bất thường | Điều tra metadata và tính an toàn; không tự động restart |

Điều kiện quan trọng: một execution cũ có `FAILED` nhưng **cùng instance đã có lần chạy sau `COMPLETED`** thì cũng không thể restart lại instance đó. Phải kiểm tra **lịch sử của cả `JobInstance`**, không chỉ một bản ghi cũ.

### 3.1. `BatchStatus` và `ExitStatus` không phải một

`BatchStatus` biểu diễn vòng đời thực thi; `ExitStatus` dùng để điều khiển flow và mô tả kết quả kết thúc step/job. Chẳng hạn một flow có transition `.end()` có thể kết thúc cả job với trạng thái `COMPLETED` dù trước đó một step đi theo nhánh lỗi. Khi job đã `COMPLETED`, operator không coi đó là job thất bại có thể restart.

Trong flow, cần phân biệt:

- `.end()`: chấm dứt flow với kết quả hoàn thành, **không thể restart instance đã completed**.
- `.fail()`: kết thúc job với `FAILED`, cho phép restart nếu job restartable.
- `.stopAndRestart(...)`: dừng flow và xác định bước tiếp theo để chạy khi restart theo cấu hình.

Do đó, một yêu cầu “job xử lý lỗi nghiệp vụ, hãy restart” phải dựa trên **metadata thực tế** và semantics của flow; không suy ra từ dòng log “ERROR”.

### 3.2. Tính restartable của `Job`

Có thể cấu hình job không được restart:

```java
@Bean
Job singleRunJob(JobRepository jobRepository, Step exportStep) {
    return new JobBuilder("singleRunJob", jobRepository)
        .start(exportStep)
        .preventRestart()
        .build();
}
```

Khi một job đã bị cấu hình `preventRestart()`, việc restart instance trước đó sẽ bị từ chối, thường bằng `JobRestartException`. Điều này có thể phù hợp cho job có side effect không thể đảo ngược, nhưng nếu nghiệp vụ yêu cầu tiếp tục sau lỗi, nên thiết kế checkpoint và tính idempotent để cho phép restart an toàn.

### 3.3. `startLimit` và `allowStartIfComplete` ở cấp step

Một step có thể đặt giới hạn số lần chạy:

```java
Step importStep = new StepBuilder("importStep", jobRepository)
    .tasklet(importTasklet, transactionManager)
    .startLimit(3)
    .build();
```

Nếu `startLimit` đã đạt ngưỡng, restart có thể thất bại khi step cần chạy lại.

Mặc định step đã `COMPLETED` trong cùng instance thường bị bỏ qua ở lần restart. Với step cần chạy lại dù từng hoàn thành, có thể cấu hình:

```java
Step checkInputStep = new StepBuilder("checkInputStep", jobRepository)
    .tasklet(checkInputTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
```

Không bật tùy chọn này theo thói quen; việc chạy lại step hoàn thành có thể nhân đôi side effect như gửi email, ghi file, phát sự kiện hoặc chuyển tiền.

---

## 4. API `JobOperator.restart` trong Spring Batch 5.x

### 4.1. Phương thức cốt lõi

```java
import org.springframework.batch.core.launch.JobOperator;

Long restartedExecutionId =
    jobOperator.restart(failedExecutionId);
```

**Tham số:** ID của **`JobExecution` cũ**, không phải `JobInstance ID`, không phải step ID, và không phải tên job. Ví dụ bảng metadata có `JOB_EXECUTION_ID = 810` thì truyền `810L`.

**Giá trị trả về:** ID của **`JobExecution mới được khởi chạy**; ví dụ `811L`. Không phải số lần retry, trạng thái `COMPLETED` hay ID của instance.

Phương thức sử dụng metadata của execution cũ để tìm job, parameters và lịch sử thực thi. Caller không cần tự ghép lại identifying parameters cho restart thông thường.

### 4.2. Vì sao không mặc định kết luận job đã hoàn tất?

`restart` trả về ID sau khi yêu cầu khởi chạy được xử lý. Tùy `JobLauncher` và `TaskExecutor`, job có thể chạy đồng bộ hoặc bất đồng bộ. Trong một cấu hình async, lúc operator trả về ID, execution có thể vẫn ở `STARTING` hoặc `STARTED`.

Do đó, quy trình điều khiển cần tách:

```text
Gửi restart
    |
    v
Nhận new JobExecution ID
    |
    v
Tra JobExplorer/JobRepository
    |
    +-- STARTING/STARTED/STOPPING --> tiếp tục giám sát
    |
    +-- COMPLETED ---------------> xác nhận thành công
    |
    +-- FAILED ------------------> thu thập nguyên nhân mới
    |
    +-- STOPPED -----------------> xem lại yêu cầu dừng
```

Không nên trả thông báo “job đã thành công” ngay sau khi nhận một ID hợp lệ.

### 4.3. Ví dụ service điều khiển restart

Đoạn dưới giả định Spring đã cấu hình một `JobOperator` và `JobExplorer` cùng làm việc với metadata repository của ứng dụng:

```java
package example.batch.ops;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BatchRestartService {

    private final JobOperator jobOperator;
    private final JobExplorer jobExplorer;

    public BatchRestartService(
            JobOperator jobOperator,
            JobExplorer jobExplorer) {
        this.jobOperator = jobOperator;
        this.jobExplorer = jobExplorer;
    }

    public long restartFailedOrStopped(long oldExecutionId)
            throws Exception {

        JobExecution previous =
            jobExplorer.getJobExecution(oldExecutionId);

        if (previous == null) {
            throw new IllegalArgumentException(
                "No JobExecution: " + oldExecutionId
            );
        }

        BatchStatus status = previous.getStatus();
        if (status != BatchStatus.FAILED &&
            status != BatchStatus.STOPPED) {
            throw new IllegalStateException(
                "JobExecution " + oldExecutionId
                    + " has status " + status
                    + " and cannot be restarted"
            );
        }

        // JobOperator/JobRepository tiếp tục kiểm tra điều kiện
        // của toàn JobInstance, restartability và concurrency.
        Long newExecutionId = jobOperator.restart(oldExecutionId);
        return newExecutionId;
    }

    public JobExecution getExecution(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

Kiểm tra trạng thái trước khi gọi giúp báo lỗi dễ hiểu, **không phải một khóa chống race condition**. Ngay giữa lúc đọc `FAILED` và gửi restart, một node khác có thể đã restart cùng instance. `JobOperator` và repository vẫn phải chịu trách nhiệm bảo vệ tính hợp lệ; ứng dụng quản trị cần xử lý exception và yêu cầu trùng ở lớp service/API.

### 4.4. Có thể gọi từ scheduler, CLI hoặc API quản trị

Ví dụ một REST endpoint nội bộ gọi service:

```java
package example.batch.ops;

import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/internal/batch")
public class BatchOperationsController {

    private final BatchRestartService restartService;

    public BatchOperationsController(BatchRestartService restartService) {
        this.restartService = restartService;
    }

    @PostMapping("/executions/{executionId}/restart")
    public Map<String, Long> restart(@PathVariable long executionId)
            throws Exception {

        if (executionId <= 0) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "executionId must be positive"
            );
        }

        long newExecutionId =
            restartService.restartFailedOrStopped(executionId);

        return Map.of("newExecutionId", newExecutionId);
    }
}
```

Đây là **đường điều khiển tối giản** để minh họa lời gọi. Trong hệ thống thật, endpoint cần authentication/authorization cho quyền vận hành batch, cơ chế xác nhận thao tác, audit log, exception mapping phù hợp và chính sách chống yêu cầu trùng. Không nên mở endpoint restart công khai hoặc chấp nhận mọi ID của nhiều tenant mà không kiểm tra quyền truy cập.

---

## 5. Chuẩn bị hạ tầng để operator restart thành công

### 5.1. Những bean và dữ liệu bắt buộc

Với cách dùng `JobOperator` theo mô hình Spring Batch 5.x có JDBC metadata:

- `JobRepository` hoạt động trên **database metadata bền vững** và schema đúng phiên bản.
- `JobExplorer` đọc được các `JobInstance` và `JobExecution` đã lưu.
- `JobLauncher` có khả năng chạy định nghĩa job tương ứng.
- `JobRegistry` có đăng ký đúng tên `Job`, để operator tìm lại job sau khi đọc metadata.
- `JobOperator` đã được cấu hình để dùng các thành phần trên.
- Reader/writer cần restart có lưu checkpoint thích hợp qua `ExecutionContext` và `ItemStream`.

`@EnableBatchProcessing` của Spring Batch 5.x cung cấp nhiều infrastructure bean, bao gồm `JobOperator`. Với Spring Boot 3.x, bộ Batch auto-configuration tiêu chuẩn cũng có thể cung cấp hạ tầng; nên lựa chọn **một cơ chế cấu hình thống nhất**. Khi thêm `@EnableBatchProcessing` hoặc tự extend `DefaultBatchConfiguration`, một phần auto-configuration của Boot sẽ nhường quyền, bao gồm tùy chọn khởi tạo schema metadata tùy cấu hình.

### 5.2. Dependency Gradle cho ứng dụng và test

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'

    testRuntimeOnly 'com.h2database:h2'
}
```

Các dependency trên giả định project dùng Spring Boot BOM hoặc dependency management để đồng bộ phiên bản Spring Batch. H2 in-memory chỉ là database test: nếu mục tiêu là restart sau khi ứng dụng production khởi động lại, metadata phải ở **database không mất khi JVM kết thúc**.

### 5.3. Cấu hình test H2 đơn giản

Ví dụ `src/test/resources/application-operator-test.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  datasource:
    generate-unique-name: true
```

Với H2 trên test classpath và không cấu hình datasource khác, Spring Boot có thể tự tạo embedded datasource. `spring.batch.job.enabled=false` tắt cơ chế tự chạy job lúc application context khởi tạo; trong integration test, ta chủ động gọi launcher.

Đối với test restart trong cùng context, cả lần thất bại lẫn lần restart phải dùng **cùng H2 database còn sống**. Không thay datasource giữa hai lần chạy.

### 5.4. Metadata phải còn nguyên

Ví dụ một lần restart qua hai process:

```text
Process A                          Metadata DB
  JobExecution #810 FAILED   ----> BATCH_JOB_EXECUTION
  Step checkpoint = 80       ----> BATCH_STEP_EXECUTION_CONTEXT
  Process A tắt                         |
                                       |
Process B khởi động                     |
  JobOperator.restart(810) <-----------+
  JobExecution #811 STARTED
  ItemStream.open(checkpoint=80)
```

Nếu Process B trỏ sang database khác, metadata không tồn tại và operator không thể restart execution 810. Nếu H2 `jdbc:h2:mem:...` biến mất khi JVM chết, cũng không thể dựa vào nó để restart sang JVM mới.

---

## 6. Luồng xử lý một job thất bại

### 6.1. Tình huống giả định

Job nhập hóa đơn gồm hai step:

```text
invoiceImportJob
  |
  +-- validateInputStep
  |     status: COMPLETED
  |
  +-- importInvoicesStep
        đọc 1000 bản ghi, commit mỗi 100
        checkpoint lưu ở offset=600
        lỗi kết nối database khi đọc tiếp
        status: FAILED

JobExecution #2100: FAILED
```

Sau khi database khôi phục, operator được yêu cầu restart execution `2100`:

```java
long newId = jobOperator.restart(2100L);
```

Kết quả kỳ vọng:

- `JobInstance` giữ nguyên.
- Framework tạo một `JobExecution` mới.
- `validateInputStep` được bỏ qua theo chính sách mặc định vì đã `COMPLETED`.
- `importInvoicesStep` chạy lại với `ExecutionContext`/checkpoint đã lưu, nếu reader/writer được thiết kế restart đúng.
- Job kết thúc `COMPLETED` nếu phần xử lý còn lại thành công.
- Số bản ghi thực tế không mất/nhân đôi, dựa trên transaction và chính sách idempotency của writer.

### 6.2. Checkpoint không phải “dòng đang đọc cuối cùng”

`ExecutionContext` thường được cập nhật và persist theo ranh giới chunk/transaction. Khi lỗi giữa chunk:

```text
read 1..100   -> commit -> checkpoint 100
read 101..200 -> commit -> checkpoint 200
read 201..250 -> exception + rollback

ExecutionContext được persist để restart: offset=200
Biến offset bên trong reader lúc lỗi: có thể đã là 250
```

Nếu restart dựa trên 250 mà chunk 201–250 chưa được commit, dữ liệu có thể bị mất. Nếu writer đã thực hiện side effect ngoài transaction trước khi lỗi, dữ liệu có thể bị nhân đôi khi chạy lại 201–250.

Do đó test và quy trình vận hành phải quan tâm **checkpoint được persist**, không chỉ trạng thái object trong bộ nhớ trước exception.

### 6.3. ItemStream hỗ trợ lưu/khôi phục tiến độ

Ví dụ giản lược về contract checkpoint của một reader:

```java
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStream;

public class OffsetStream implements ItemStream {

    private static final String KEY = "invoice.reader.offset";

    private long offset;

    @Override
    public void open(ExecutionContext context) {
        offset = context.getLong(KEY, 0L);
    }

    public void onOneItemCommittedToProgress() {
        offset++;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(KEY, offset);
    }

    @Override
    public void close() {
        // Giải phóng resource nếu có.
    }
}
```

Đây là ví dụ mô tả API `ItemStream`. Trong reader thực, offset được điều chỉnh theo contract đọc/chunk và xử lý rollback của component, không gọi thủ công một method “committed” từ ngoài nếu chưa có cơ chế transactional chính xác. Framework gọi `open/update/close` nếu stream được đăng ký và quản lý đúng; dữ liệu `update` có thể được persist tại checkpoint.

Để restart hoạt động:

1. Step phải đăng ký/nhận diện stream. Với delegate ẩn bên trong wrapper, có thể cần `.stream(delegate)` khi build step.
2. Key lưu phải ổn định giữa hai lần chạy, tránh hai reader dùng trùng key.
3. Context phải chứa kiểu dữ liệu serialize được bởi repository.
4. Writer phải đảm bảo không tạo side effect sai khi chunk được xử lý lại.
5. Bộ identifying parameters không thay đổi giữa execution thất bại và execution restart.

---

## 7. Integration test: gọi `JobOperator.restart` và kiểm tra kết quả

Mục tiêu của test: tạo một job thật, cho một step thất bại ở lần đầu và thành công khi restart, rồi xác minh metadata được ghi đúng trong `JobRepository`.

### 7.1. Kịch bản

```text
retryableImportJob
    |
    +-- prepareStep       : tăng prepareCounter, luôn COMPLETED
    |
    +-- deliverStep       : lần đầu throw exception -> FAILED
                           lần sau -> COMPLETED

Test:
  launchJob(uniqueParameters) -> FAILED, JobExecution A
  jobOperator.restart(A.id)   -> JobExecution B, COMPLETED
  A.instanceId == B.instanceId
  A.id != B.id
  prepareCounter == 1 (step đã COMPLETED được bỏ qua)
  deliverCounter == 2 (step FAILED được chạy lại)
```

### 7.2. Java integration test

Dùng JUnit 5, Spring Batch 5.x, Spring Boot 3.x và H2:

```java
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(
    classes = OperatorRestartFailedTest.TestApplication.class
)
@ActiveProfiles("operator-test")
class OperatorRestartFailedTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobOperator jobOperator;

    @Autowired
    private JobExplorer jobExplorer;

    @Autowired
    private AtomicInteger prepareCounter;

    @Autowired
    private AtomicInteger deliverCounter;

    @Test
    void operatorRestartsFailedExecutionWithinSameInstance()
            throws Exception {

        JobParameters parameters = new JobParametersBuilder()
            .addString("test.requestId", UUID.randomUUID().toString())
            .toJobParameters();

        JobExecution first =
            jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(1, prepareCounter.get());
        assertEquals(1, deliverCounter.get());

        // JobOperator nhận JobExecution ID, trả về ID của execution mới.
        Long restartedId = jobOperator.restart(first.getId());

        // Mặc định launcher của test chạy đồng bộ. Nếu cấu hình
        // launcher bất đồng bộ, phải chờ execution kết thúc trước
        // khi assert trạng thái terminal.
        JobExecution restarted =
            jobExplorer.getJobExecution(restartedId);

        assertNotNull(restarted);
        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());

        assertEquals(
            first.getJobInstance().getId(),
            restarted.getJobInstance().getId()
        );
        assertNotEquals(first.getId(), restarted.getId());

        // Step đã COMPLETED trong lần đầu không bị chạy lại.
        assertEquals(1, prepareCounter.get());

        // Step FAILED chạy thêm một lần.
        assertEquals(2, deliverCounter.get());

        assertTrue(restarted.getStepExecutions().stream()
            .map(StepExecution::getStepName)
            .anyMatch("deliverStep"::equals));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(TestJobs.class)
    static class TestApplication {
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestJobs {

        @Bean
        AtomicBoolean failFirstDelivery() {
            return new AtomicBoolean(true);
        }

        @Bean
        AtomicInteger prepareCounter() {
            return new AtomicInteger();
        }

        @Bean
        AtomicInteger deliverCounter() {
            return new AtomicInteger();
        }

        @Bean
        Step prepareStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                AtomicInteger prepareCounter) {

            return new StepBuilder("prepareStep", repository)
                .tasklet((contribution, chunkContext) -> {
                    prepareCounter.incrementAndGet();
                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean
        Step deliverStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                AtomicInteger deliverCounter,
                AtomicBoolean failFirstDelivery) {

            return new StepBuilder("deliverStep", repository)
                .tasklet((contribution, chunkContext) -> {
                    deliverCounter.incrementAndGet();

                    if (failFirstDelivery.getAndSet(false)) {
                        throw new IllegalStateException(
                            "Simulated delivery failure"
                        );
                    }

                    return RepeatStatus.FINISHED;
                }, transactionManager)
                .build();
        }

        @Bean
        Job retryableImportJob(
                JobRepository repository,
                Step prepareStep,
                Step deliverStep) {

            return new JobBuilder("retryableImportJob", repository)
                .start(prepareStep)
                .next(deliverStep)
                .build();
        }
    }
}
```

File `src/test/resources/application-operator-test.yml` sử dụng nội dung ở mục 5.3.

**Diễn giải:**

- `AtomicBoolean` là fixture tạo lỗi đúng một lần; nó không phải giải pháp lưu trạng thái nghiệp vụ. Vì trạng thái này nằm trong test bean, fixture phải được reset/cách ly nếu mở rộng thành nhiều test method hoặc chạy song song.
- `JobLauncherTestUtils` chỉ có một `Job` trong context nên có thể xác định job mặc định. Nếu ứng dụng có nhiều job, dùng `setJob(jobUnderTest)` hoặc cấu hình chọn job rõ ràng.
- `prepareStep` hoàn thành ở execution đầu; trên restart, mặc định framework không chạy lại step này.
- `deliverStep` ném exception ở lần đầu, sau đó chạy thành công ở execution thứ hai.
- `jobOperator.restart(first.getId())` là thao tác đang được kiểm tra, khác với việc launch lần hai bằng parameters mới.
- `JobExplorer` đọc lại execution từ metadata repository giúp kiểm tra quan hệ instance/execution thực tế.
- Nếu `JobLauncher` cấu hình bất đồng bộ, cần chờ đến terminal status có timeout trước khi assert `COMPLETED`; không dùng một lần đọc ngay sau restart như bằng chứng job đã xong.

Trong project thật, test còn nên assert **dữ liệu nghiệp vụ** sau restart, ví dụ chỉ có một hóa đơn cho mỗi external ID, không bị lặp event và không mất record.

### 7.3. Kiểm tra kết quả trên metadata

Ngoài trạng thái trong test, ta có thể dùng `JobExplorer` kiểm tra dữ liệu:

```java
JobExecution oldExecution =
    jobExplorer.getJobExecution(first.getId());

JobExecution newExecution =
    jobExplorer.getJobExecution(restartedId);

assertNotNull(oldExecution);
assertNotNull(newExecution);

assertEquals(BatchStatus.FAILED, oldExecution.getStatus());
assertEquals(BatchStatus.COMPLETED, newExecution.getStatus());

assertEquals(
    oldExecution.getJobInstance().getId(),
    newExecution.getJobInstance().getId()
);
```

Nếu bài test cần kiểm tra **khôi phục checkpoint**, hãy đọc `StepExecution.getExecutionContext()` của execution thất bại từ repository, ghi lại giá trị reader nhận tại `ItemStream.open()` ở lần restart và so sánh. Chỉ nhìn `COMPLETED` không chứng minh reader đã bắt đầu tại đúng offset.

### 7.4. Chạy test với metadata database có persistence

Trong môi trường CI, H2 in-memory phù hợp để test cùng process. Để kiểm chứng restart sau **JVM hoặc container restart thực**, phải dùng JDBC metadata repository trên storage tồn tại qua lần khởi động sau: PostgreSQL, Oracle, SQL Server, H2 file mode hoặc database service test riêng.

---

## 8. Xử lý ngoại lệ khi gọi restart

`JobOperator.restart(long)` trong Spring Batch 5.x khai báo một số checked exception. Chúng mang ý nghĩa khác nhau, không nên bắt hết rồi lặp lại vô hạn.

| Ngoại lệ | Trường hợp thường gặp | Cách phản ứng |
| --- | --- | --- |
| `NoSuchJobExecutionException` | Execution ID không tồn tại trong repository đang dùng | Kiểm tra ID, datasource, môi trường và quyền xem metadata |
| `NoSuchJobException` | Metadata có execution nhưng định nghĩa job không tìm được trong registry hiện tại | Đảm bảo job name được đăng ký và phiên bản triển khai còn chứa job |
| `JobInstanceAlreadyCompleteException` | Instance đã hoàn thành qua một execution nào đó | Không restart instance; yêu cầu mới cần parameters mới |
| `JobRestartException` | Job đặt `preventRestart`, metadata không nhất quán, instance không ở trạng thái restart hợp lệ hoặc các điều kiện framework khác | Điều tra nguyên nhân, chính sách restart, tính nhất quán và step history |
| `JobParametersInvalidException` | Validator hiện tại từ chối parameters đã lưu | Kiểm tra thay đổi validator/contract khi triển khai phiên bản mới |

Những lỗi liên quan execution đang chạy, lỗi datasource, transaction hoặc infrastructure cũng có thể xuất hiện qua runtime exception/exception được bọc. Danh sách ngoại lệ chính thức cần đọc theo đúng phiên bản Spring Batch đang triển khai.

### 8.1. Ví dụ phân loại lỗi ở service

```java
import org.springframework.batch.core.launch.NoSuchJobException;
import org.springframework.batch.core.launch.NoSuchJobExecutionException;
import org.springframework.batch.core.launch.JobRestartException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.JobParametersInvalidException;

public long restartWithErrorClassification(long failedId)
        throws Exception {

    try {
        return jobOperator.restart(failedId);

    } catch (NoSuchJobExecutionException e) {
        // ID sai hoặc metadata repository không chứa execution.
        throw new IllegalArgumentException(
            "Unknown execution ID: " + failedId, e
        );

    } catch (NoSuchJobException e) {
        // Phiên bản ứng dụng hiện tại không có định nghĩa job cũ.
        throw new IllegalStateException(
            "Job definition is unavailable for execution " + failedId, e
        );

    } catch (JobInstanceAlreadyCompleteException e) {
        // Công việc logic của instance này đã hoàn tất.
        throw new IllegalStateException(
            "Job instance has already completed", e
        );

    } catch (JobParametersInvalidException e) {
        throw new IllegalStateException(
            "Stored parameters fail current validation", e
        );

    } catch (JobRestartException e) {
        throw new IllegalStateException(
            "Restart rejected by Spring Batch", e
        );
    }
}
```

Đoạn code là phần mở rộng minh họa cho service có `jobOperator`. Trong hệ thống production, nên dùng exception chuyên biệt của domain/API và map thành mã lỗi ổn định, ví dụ “execution not found”, “already completed”, “job not registered”, “restart rejected” hoặc “temporary infrastructure error”.

Một lỗi SQL tạm thời có thể retry ở tầng phù hợp, nhưng **retry việc gửi lệnh restart** phải kiểm tra xem một lần gửi trước đã tạo `JobExecution` mới hay chưa. Nếu trả lời từ hệ thống bị timeout sau khi lệnh đã khởi chạy, gửi lại ngay có thể tạo tranh chấp với execution đang chạy.

---

## 9. Quy trình vận hành trước và sau restart

### 9.1. Trước khi restart

Một operator có thể áp dụng quy trình:

1. **Xác định đúng execution:** ghi nhận `jobName`, `jobExecutionId`, `jobInstanceId`, identifying parameters, môi trường và tenant.
2. **Đọc metadata hiện tại:** xem `BatchStatus`, `ExitStatus`, failure exceptions, step history, checkpoint và execution mới hơn nếu có.
3. **Xác nhận không còn đang chạy:** kiểm tra scheduler, worker node, process/container, queue và trạng thái repository. Đặc biệt chú ý execution bị treo ở `STARTED` sau khi JVM chết.
4. **Tìm và khắc phục nguyên nhân lỗi:** database, input, API credential, mapping dữ liệu, quota hoặc timeout.
5. **Đánh giá side effect:** bản ghi đã commit, file đã ghi, thông báo đã gửi, quyền truy cập hệ thống ngoài; xác định khả năng chạy lại an toàn.
6. **Xác nhận job restartable và định nghĩa job tương thích:** job còn đăng ký trong registry, parameters còn hợp lệ, step names và checkpoint contract không bị thay đổi không tương thích.
7. **Gọi restart đúng execution ID:** ghi nhận người thực hiện, lý do và ID execution mới.

Ví dụ sử dụng API quan sát:

```java
String summary = jobOperator.getSummary(failedExecutionId);

var steps =
    jobOperator.getStepExecutionSummaries(failedExecutionId);

var runningIds =
    jobOperator.getRunningExecutions("invoiceImportJob");
```

Các API trên hỗ trợ thẩm định, nhưng không thay thế kiểm tra process bên ngoài khi metadata `STARTED` bị kẹt do sự cố máy chủ.

### 9.2. Sau khi restart

1. Ghi nhận **new `JobExecution ID`** do operator trả về.
2. Theo dõi status đến khi terminal: `COMPLETED`, `FAILED` hoặc `STOPPED`.
3. Kiểm tra `readCount`, `writeCount`, `skipCount`, `rollbackCount` và checkpoint ở các step liên quan.
4. Đối chiếu dữ liệu nghiệp vụ: số lượng, unique keys, checksum hoặc dấu vết side effect.
5. Ghi kết quả và nếu thất bại lần nữa, xử lý theo nguyên nhân mới; tránh vòng lặp restart vô hạn.

Với asynchronous launcher, dùng cơ chế giám sát có giới hạn thời gian hoặc scheduler/observability của hệ thống để kiểm tra trạng thái. Tránh viết logic tự gọi `restart` liên tục chỉ dựa vào việc status chưa `COMPLETED`.

### 9.3. Nhật ký vận hành gợi ý

```text
action            = RESTART_JOB_EXECUTION
requestedBy       = batch-operator
jobName           = invoiceImportJob
jobInstanceId     = 41
sourceExecutionId = 810
newExecutionId    = 811
reason            = external database recovered
requestedAt       = 2026-11-16T08:30:00+07:00
initialResult     = LAUNCHED
finalResult       = COMPLETED
```

Các trường trên chỉ là ví dụ audit; trong hệ thống thật, tránh ghi secrets, raw credentials và dữ liệu cá nhân từ job parameters hoặc execution context.

---

## 10. Tình huống đặc biệt: process chết nhưng repository vẫn STARTED

Trong một lần shutdown đột ngột như kill process, mất điện hoặc node bị xóa, ứng dụng có thể không cập nhật trạng thái execution cuối cùng vào database. Metadata còn `STARTED`, dù thực tế job không còn chạy.

```text
Spring Batch JVM #1:   process crashed
Metadata repository:  JobExecution #910 = STARTED
Spring Batch JVM #2:   sees STARTED, restart rejected
```

Đây là vấn đề **recovery trạng thái vận hành** trước khi restart. Không nên coi mọi bản ghi `STARTED` là stale: có thể node khác đang tiếp tục xử lý.

Với Spring Batch 5.x:

- Xác định chắc chắn không còn process/worker đang xử lý execution đó.
- Điều tra transaction nào đã commit và checkpoint nào được lưu.
- Đưa metadata về trạng thái phù hợp theo quy trình quản trị được kiểm soát nếu hệ thống cho phép, bảo đảm tính nhất quán. Không chỉnh sửa trực tiếp các cột status theo suy đoán, vì còn các version/counter/context/quan hệ khác.
- Chỉ sau khi trạng thái hợp lệ và an toàn mới dùng `JobOperator.restart(executionId)`.

Với **Spring Batch 6.x**, API `JobOperator.recover(JobExecution)` được bổ sung cho trường hợp execution bị kẹt ở `STARTED` sau shutdown đột ngột. Chỉ sử dụng khi đã xác nhận execution đó thực sự không còn chạy; xem chi tiết API của phiên bản tương ứng.

### 10.1. Khác nhau giữa stop, fail và abandon

- **Stop:** yêu cầu job đang chạy dừng có kiểm soát; nó có thể cần một khoảng thời gian để đến `STOPPED`. Một execution `STOPPED` có thể restart nếu job cho phép.
- **Fail:** execution kết thúc `FAILED` do lỗi, thường vẫn có khả năng restart sau khi xử lý nguyên nhân.
- **Abandon:** đánh dấu execution `ABANDONED` nhằm kết thúc việc theo dõi theo cách không cho restart execution đó. Đây không phải cách “làm cho job có thể chạy lại”.

`jobOperator.abandon(id)` là thao tác quản trị có tác động đến lifecycle và nên dùng có chủ đích. Không dùng nó như cách xóa một lỗi `FAILED` rồi hy vọng restart tự hoạt động.

---

## 11. Các rủi ro nghiệp vụ khi restart

### 11.1. Restart không tự bảo đảm exactly-once cho mọi side effect

Ví dụ job gồm:

```text
1. Gọi API gửi email
2. Ghi trạng thái SENT vào database
3. Commit metadata checkpoint
```

Nếu process chết sau bước 1 nhưng trước bước 2 hoặc 3, restart có thể gửi lại email lần nữa. Spring Batch điều phối transaction và checkpoint cho các resource tham gia, nhưng không thể tự biến một API không transactional thành exactly-once.

Cách giảm rủi ro:

- Dùng **idempotency key** từ business ID khi gọi hệ thống ngoài.
- Có unique constraint/UPSERT cho output nghiệp vụ.
- Dùng outbox pattern cho sự kiện giao dịch.
- Chia step theo ranh giới transaction rõ ràng.
- Đối chiếu dữ liệu đã commit trước khi tiếp tục, nếu business contract yêu cầu.

### 11.2. Không thay đổi identifying parameters trong restart

Nếu job xử lý ngày `2026-11-16` và tenant `A`, operator restart sẽ dựa trên parameters của instance cũ. Muốn xử lý ngày khác, hãy tạo instance mới có identifying parameters mới. Việc “sửa parameters để restart cho chạy” thường phá vỡ ý nghĩa checkpoint và khiến dữ liệu đầu ra lệch phạm vi.

### 11.3. Thay đổi định nghĩa job giữa các phiên bản

Restart thường xảy ra sau khi deploy một phiên bản mới. Nếu code thay đổi:

- Tên `Job` hoặc `Step`.
- Flow transitions, `startLimit` hoặc `allowStartIfComplete`.
- Key/kiểu dữ liệu trong `ExecutionContext`.
- Serializer hoặc metadata schema.
- Định dạng file/điều kiện lọc dữ liệu.

thì execution cũ có thể không còn tương thích với code mới.

Ví dụ checkpoint cũ lưu `reader.offset=500L` nhưng reader mới đòi key `source.page.index` có thể khiến job đọc lại từ đầu hoặc thất bại. Cần có chính sách tương thích checkpoint qua các phiên bản hoặc quyết định vận hành rõ ràng để chuyển đổi metadata.

### 11.4. Partitioning và remote processing

Một job có partitioned steps hoặc remote workers cần xét trạng thái từng partition, thứ tự commit và quyền sở hữu task. Việc restart ở cấp job không đồng nghĩa tất cả partition đều chạy lại; framework có thể dựa vào metadata để xác định phần cần xử lý tiếp.

Kiểm tra cả `StepExecution` của partition, trạng thái worker bên ngoài và đảm bảo không có worker cũ tiếp tục ghi dữ liệu khi execution mới khởi động.

### 11.5. Yêu cầu restart đồng thời

Hai operator hoặc hai node có thể cùng gửi restart một execution:

```text
operator A -> restart(810)
operator B -> restart(810) ngay sau đó
```

Database repository có cơ chế kiểm soát tạo execution và trạng thái, nhưng ứng dụng quản trị vẫn nên triển khai idempotency cho request, kiểm tra running execution mới và khóa/phân quyền điều khiển theo instance khi cần. Một trong hai yêu cầu có thể bị từ chối; caller phải báo rõ “đã có execution đang chạy” thay vì tự thử lại với parameters mới.

---

## 12. Các lỗi thường gặp khi vận hành `JobOperator.restart`

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| `NoSuchJobExecutionException` | Truyền nhầm JobInstance ID hoặc query nhầm database/environment | Kiểm tra ID trong `BATCH_JOB_EXECUTION` và cấu hình repository |
| `NoSuchJobException` | Job đổi tên, bean bị xóa, job không đăng ký vào `JobRegistry` | Kiểm tra tên job từ metadata và registry hiện tại |
| `JobInstanceAlreadyCompleteException` | Instance đã có execution thành công; operator đang dùng execution cũ | Kiểm tra toàn bộ execution của instance |
| `JobRestartException` vì không restartable | `.preventRestart()` hoặc chính sách job/step | Đọc định nghĩa Job, `startLimit`, status step |
| Trạng thái vẫn `STARTED` sau crash | JVM chết không kịp ghi metadata | Xác nhận process đã chết, điều tra recovery procedure |
| Restart chạy lại step đã hoàn thành | `allowStartIfComplete(true)` hoặc flow thay đổi | Xem cấu hình step và lịch sử execution |
| Restart đọc lại dữ liệu từ đầu | Stream không lưu/khôi phục checkpoint, key đổi, repository sai | Đọc `ExecutionContext` từ repository và kiểm tra `open/update` |
| Restart thành công nhưng output trùng | Side effect ngoài transaction, writer không idempotent | Đối chiếu unique key, transaction boundaries, outbox |
| Restart không thấy metadata khi chuyển node | H2 in-memory hoặc datasource khác, schema thiếu | Dùng metadata database dùng chung bền vững |
| Method trả về ID nhưng dashboard còn `STARTED` | JobLauncher chạy bất đồng bộ | Poll `JobExplorer` theo lịch có timeout; không kết luận đã thành công |
| Retry lệnh restart gây lỗi “already running” | Lệnh đầu đã launch job nhưng response timeout | Query các execution mới/running trước khi retry |
| Restart fail sau deploy | Job/step names hoặc context serialization đổi | Kiểm tra version compatibility, migration, checkpoint contract |

### 12.1. Dùng `JobExplorer` kiểm tra trước khi thao tác

```java
JobExecution failed = jobExplorer.getJobExecution(810L);

if (failed == null) {
    throw new IllegalArgumentException("Unknown execution ID");
}

System.out.println("Job: "
    + failed.getJobInstance().getJobName());

System.out.println("Instance: "
    + failed.getJobInstance().getId());

System.out.println("Execution status: " + failed.getStatus());
```

Không dùng output `System.out` này làm audit chính thức trong ứng dụng quản trị. Nó chỉ cho thấy thông tin cần thu thập; thực tế nên dùng structured logging với correlation ID, bảo vệ nội dung job parameters nhạy cảm và ghi lại thao tác của người vận hành.

### 12.2. Không nên “chữa” lỗi restart bằng một `JobInstance` mới ngay lập tức

Nếu job nhập 1.000 hóa đơn đã ghi 600 rồi thất bại, việc đổi `run.id` và chạy lại từ đầu có thể tạo 600 bản ghi trùng. Tạo instance mới chỉ hợp lý khi nghiệp vụ chủ động yêu cầu **một đợt xử lý mới từ đầu** và đã có cơ chế chống trùng hoặc dọn trạng thái cũ.

Nếu mục tiêu là hoàn thành công việc còn dang dở, tìm và sửa nguyên nhân khiến restart bị từ chối, thay vì lẩn tránh metadata lịch sử.

---

## 13. Kiểm thử các trường hợp bị từ chối

Ngoài happy path ở mục 7, nên có các kịch bản test riêng:

### 13.1. Restart execution đã COMPLETED

```java
JobExecution completed =
    jobLauncherTestUtils.launchJob(uniqueParameters);

// Với fixture đảm bảo job đã chạy thành công:
assertEquals(BatchStatus.COMPLETED, completed.getStatus());

assertThrows(
    JobInstanceAlreadyCompleteException.class,
    () -> jobOperator.restart(completed.getId())
);
```

Đây là mẫu assertion cho fixture thành công, khác với fixture cố tình lỗi một lần ở mục 7. Test này phải dùng job/job parameters được setup để hoàn thành ngay lần đầu.

### 13.2. Execution ID không tồn tại

```java
assertThrows(
    NoSuchJobExecutionException.class,
    () -> jobOperator.restart(nonExistingExecutionId)
);
```

Không dùng một số ID ngẫu nhiên rồi mặc định chưa tồn tại trong database chia sẻ. Tạo fixture repository riêng hoặc xác định chắc chắn ID đó không tồn tại trước khi assert.

### 13.3. Không cho restart

```java
Job noRestartJob = new JobBuilder("noRestartJob", repository)
    .start(stepThatWillFail)
    .preventRestart()
    .build();
```

Cho job này thất bại một lần, sau đó assert operator từ chối restart. Trong các bài test này, phải đảm bảo job thực sự đã có một execution `FAILED`: gọi restart một job chưa từng chạy không kiểm tra `preventRestart()`.

### 13.4. Job không còn đăng ký

Tạo metadata cho một job, sau đó khởi động một application context khác dùng cùng persistent metadata nhưng **không có job definition tương ứng**. Gọi restart và kiểm tra phản ứng `NoSuchJobException`. Đây là test cho wiring/deployment, không phải test “job processing”.

### 13.5. Async launcher

Dùng một `TaskExecutor` bất đồng bộ và một step có thời gian chạy đủ để quan sát. Assert `restart` trả về một execution ID, sau đó đợi `JobExplorer` báo terminal status bằng cơ chế polling có giới hạn thời gian. Tránh phép assert `COMPLETED` ngay sau khi nhận ID.

---

## 14. Khác biệt API Spring Batch 5 và Spring Batch 6

Từ Spring Batch 6.x, API operator đã có dạng thuận tiện hơn dựa trên object, trong khi một số API dùng primitive ID được đánh dấu deprecated.

| Công việc | Spring Batch 5.x | Spring Batch 6.x |
| --- | --- | --- |
| Restart từ execution thất bại | `Long newId = jobOperator.restart(oldId);` | `JobExecution newRun = jobOperator.restart(failedExecution);` |
| Truy cập execution trước restart | `jobExplorer.getJobExecution(id)` | Có thể lấy execution từ `JobRepository` theo API mới |
| Recover execution kẹt `STARTED` sau crash | Cần quy trình kiểm soát trạng thái metadata phù hợp phiên bản | `jobOperator.recover(jobExecution)` |
| API ID-based | Là API thông dụng | Nhiều overload dựa vào ID bị deprecated và dự kiến loại bỏ |
| Hạ tầng metadata | Thường dùng JDBC `JobRepository` | Có thể dùng nhiều loại repository; persistent repository vẫn cần thiết để restart qua process |

Ví dụ ý tưởng Spring Batch 6:

```java
JobExecution failedExecution = /* đọc từ metadata repository */;

JobExecution restartedExecution =
    jobOperator.restart(failedExecution);

long newExecutionId = restartedExecution.getId();
```

Nếu execution bị kẹt `STARTED` sau shutdown đột ngột và xác minh đã không còn chạy, Spring Batch 6 có API `jobOperator.recover(failedExecution)` để đưa trạng thái vào quy trình restart phù hợp. Không áp dụng mã Spring Batch 6 vào dự án Spring Batch 5 nếu chưa nâng cấp API.

Do khác biệt về package, exception và infrastructure giữa các phiên bản, ví dụ trong bài dùng **Spring Batch 5.x làm chuẩn** và nhấn mạnh các điểm cần sửa khi nâng cấp.

---

## 15. Bài thực hành

### Bài 1 — Restart một failed job qua operator

Tạo job `orderImportJob` gồm hai step:

1. `loadConfigStep` luôn `COMPLETED`.
2. `importOrdersStep` lần đầu ném `IllegalStateException`, lần hai thành công.

Tạo identifying parameters duy nhất. Dùng `JobLauncherTestUtils` chạy lần đầu và `JobOperator.restart(failedExecutionId)` chạy lần hai. Assert hai execution khác ID, cùng instance; `loadConfigStep` chỉ chạy một lần và job cuối `COMPLETED`.

### Bài 2 — Kiểm tra refusal theo trạng thái

Tạo execution có trạng thái `COMPLETED`, thử restart và kiểm tra `JobInstanceAlreadyCompleteException`. Tạo một execution ID không tồn tại, kiểm tra `NoSuchJobExecutionException`.

Giải thích vì sao không nên tự chuyển status từ `COMPLETED` sang `FAILED` để ép restart.

### Bài 3 — Khôi phục checkpoint

Tạo chunk job đọc 100 dòng, commit interval 20. Cố ý lỗi sau khi vài chunk đã commit. Kiểm tra `ExecutionContext` persisted của step thất bại; restart cùng instance bằng operator. Assert reader nhận checkpoint đã lưu khi `open()`, kết quả chứa đúng 100 dòng không lặp và execution cuối `COMPLETED`.

### Bài 4 — Giám sát async restart

Cấu hình launcher bất đồng bộ, gọi `restart` và lưu ID mới. Viết endpoint/query trạng thái dùng `JobExplorer`; xác định khi nào chuyển `STARTED → COMPLETED` hoặc `FAILED`. Không coi lời gọi restart thành công là toàn job thành công.

### Bài 5 — Thiết kế quy trình vận hành

Giả sử execution thất bại sau khi gửi 400 trong 1.000 email. Xây dựng kế hoạch restart an toàn có idempotency key, nơi lưu trạng thái đã gửi, cách đọc execution metadata, phương án xử lý phần gửi ngoài transaction và audit log sau restart.

---

## 16. Ghi nhớ khi triển khai

**`JobOperator.restart(failedExecutionId)` là thao tác tiếp tục `JobInstance` hiện hữu theo metadata đã lưu.** Nó tạo một `JobExecution` mới, áp dụng chính sách restart của job/step và có thể khôi phục checkpoint của step chưa hoàn thành. Muốn bảo đảm kết quả đúng, phải có metadata repository bền vững, job definition còn đăng ký, identifying parameters ổn định, reader/writer quản lý state và side effect được kiểm soát.

Mỗi lần restart cần được đánh giá qua ba kết quả độc lập:

- **Điều khiển:** operator chấp nhận lệnh và trả về new execution ID.
- **Framework:** execution mới kết thúc ở trạng thái mong muốn, step history/checkpoint đúng.
- **Nghiệp vụ:** dữ liệu cuối cùng đủ, không trùng, không phát sinh side effect sai.

Chỉ khi cả ba lớp điều kiện đều phù hợp, operator mới nên đánh dấu tác vụ khôi phục thành công.

## 17. Tài liệu tham khảo

- [Spring Batch 5.2 — JobOperator API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/JobOperator.html).
- [Spring Batch 5.2 — Advanced Metadata Usage / JobOperator](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html).
- [Spring Batch 5.2 — Configuring and Running a Job](https://docs.spring.io/spring-batch/reference/5.2/job/configuring.html).
- [Spring Batch 5.2 — Restarting a Job](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html).
- [Spring Batch 5.2 — `JobRepository` and `JobExplorer`](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html).
- [Spring Batch 5.2 — Testing](https://docs.spring.io/spring-batch/reference/5.2/testing.html).
- [Spring Batch 6 — JobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html).
- [Spring Batch 6 — Advanced Metadata Usage / Recovering a job](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html).
