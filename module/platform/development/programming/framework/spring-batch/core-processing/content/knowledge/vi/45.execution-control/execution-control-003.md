# Stop job đang chạy trong Spring Batch

## 1. Hiểu đúng thao tác dừng một job đang chạy

Trong Spring Batch, **dừng job đang chạy** là thao tác yêu cầu hệ thống kết thúc một `JobExecution` theo cách có kiểm soát, để có thể giữ trạng thái xử lý, quan sát nguyên nhân và — nếu job hỗ trợ restart — tiếp tục từ dữ liệu checkpoint đã lưu.

Giả sử job `importOrders` đang đọc 10 triệu đơn hàng. Người vận hành phát hiện file nguồn sai và muốn dừng việc nhập tiếp. Nếu tắt cưỡng bức JVM, dữ liệu đã ghi có thể còn đó nhưng trạng thái `JobRepository` có thể chưa được cập nhật. Nếu gửi lệnh `JobOperator.stop(executionId)`, Spring Batch sẽ ghi nhận **yêu cầu dừng**, đợi job trả quyền điều khiển về framework và kết thúc execution khi có điều kiện an toàn.

Phân biệt ba hành động:

| Hành động | Mục tiêu | Kết quả thường gặp |
|---|---|---|
| **Stop** | Yêu cầu execution đang chạy ngừng có kiểm soát | `STARTED → STOPPING → STOPPED` khi dừng thành công |
| **Restart** | Khởi chạy lại một `JobInstance` đã thất bại hoặc bị dừng | Tạo **`JobExecution` mới**, dùng checkpoint và identifying parameters cũ |
| **Kill process / crash** | Dừng tiến trình hệ điều hành ngay lập tức | Không bảo đảm callback và checkpoint hoàn tất; metadata có thể còn `STARTED` |

**Điểm cốt lõi:** `stop` **không phải** thao tác hủy thread ngay lập tức. Nó là **tín hiệu hợp tác**. Nếu reader đang chờ I/O, tasklet chạy vòng lặp rất lâu hoặc service nghiệp vụ không trả về, thời gian dừng có thể dài.

### Phạm vi phiên bản

Các ví dụ Java chính dưới đây dùng **Spring Batch 5.2.x, Spring Boot 3.x và Java 17+**. Ở Spring Batch 5.2, API điều khiển bằng ID là `JobOperator.stop(long executionId)`; trong Spring Batch 6, API ưu tiên `stop(JobExecution)` và overload nhận `long` đã bị đánh dấu deprecated. Các package và lớp domain cũng thay đổi ở một số bản 6.x. Khi dùng phiên bản khác, cần áp dụng chữ ký/import của phiên bản đó.

## 2. JobInstance, JobExecution và StepExecution khác nhau thế nào?

Để dừng đúng job, trước tiên cần biết đối tượng mà thao tác nhắm tới.

- **`Job`** là định nghĩa xử lý, ví dụ `importOrders`, gồm các step và flow.
- **`JobInstance`** là một lần xử lý logic được xác định bởi tên job và các **identifying `JobParameters`**. Ví dụ `importOrders` với `businessDate=2025-05-12`.
- **`JobExecution`** là một lượt chạy cụ thể của `JobInstance`. Restart tạo một execution mới.
- **`StepExecution`** là lượt chạy của từng step trong một job execution.

Ví dụ:

```text
Job: importOrders
└── JobInstance: businessDate=2025-05-12
    ├── JobExecution id=101, status=STOPPED
    │   └── StepExecution(importStep), status=STOPPED
    └── JobExecution id=117, status=COMPLETED
        └── StepExecution(importStep), status=COMPLETED
```

Muốn dừng lượt đang chạy số `101`, dùng **`jobExecutionId=101`**. Không truyền `jobInstanceId`, `stepExecutionId` hoặc tên job vào phương thức `stop(long)`.

Có thể có nhiều `JobExecution` chạy đồng thời cho các `JobInstance` khác nhau của cùng một tên job. Vì vậy màn hình quản trị nên hiển thị đồng thời `jobName`, `jobExecutionId`, `JobParameters` và `BatchStatus` trước khi cho phép dừng.

## 3. Các trạng thái khi dừng

Spring Batch dùng `BatchStatus` cho trạng thái thực thi và `ExitStatus` cho kết quả có thể tham gia điều khiển flow. Chúng có vai trò khác nhau.

Một đường đi thường gặp:

```text
STARTING
   |
   v
STARTED
   |  JobOperator.stop(executionId)
   v
STOPPING       <-- yêu cầu đã được gửi; job có thể vẫn đang xử lý
   |
   |  thành phần đang chạy trả quyền điều khiển cho Spring Batch
   v
STOPPED        <-- trạng thái dừng cuối cùng, có thể xem xét restart
```

Nếu job gặp lỗi trong lúc dừng, trạng thái cuối có thể là `FAILED` thay vì `STOPPED`. Nếu job kết thúc tự nhiên đồng thời với lệnh stop, kết quả còn tùy thời điểm; hệ thống quản trị cần kiểm tra lại trạng thái thực tế, không tự suy ra từ nút “Stop” đã được nhấn.

| `BatchStatus` | Ý nghĩa vận hành | Có nên nhận yêu cầu dừng mới? |
|---|---|---|
| `STARTING` / `STARTED` | Execution đang trong giai đoạn khởi động hoặc xử lý | Có thể thử stop |
| `STOPPING` | Đã có tín hiệu dừng, chưa kết thúc | Không gửi lệnh lặp vô hạn; theo dõi tiến độ |
| `STOPPED` | Đã dừng và ghi metadata | Có thể cân nhắc restart nếu cấu hình cho phép |
| `COMPLETED` | Execution đã hoàn thành | Không stop được lượt này |
| `FAILED` | Execution kết thúc vì lỗi | Đánh giá lỗi và khả năng restart |
| `ABANDONED` | Execution bị đánh dấu bỏ; framework không restart execution bị abandon | Không dùng để dừng mềm đang chạy |

Trạng thái `STOPPING` không chứng minh thread xử lý còn thực sự hoạt động. Nếu JVM chết giữa chừng, bản ghi metadata có thể bị kẹt. Muốn kết luận tiến trình còn sống phải kết hợp trạng thái trong `JobRepository` với telemetry của instance thực thi, log, heartbeat hoặc thông tin hạ tầng.

## 4. Gửi lệnh dừng bằng `JobOperator`

`JobOperator` là giao diện Spring Batch dành cho việc quan sát và điều khiển job, gồm các thao tác xem execution, `stop`, `restart` và một số chức năng khác. Khi sử dụng cấu hình Spring Batch tiêu chuẩn, bean `JobOperator` được cung cấp qua Batch infrastructure; nếu ứng dụng tự dựng hạ tầng batch, cần khai báo đầy đủ các thành phần mà `SimpleJobOperator` yêu cầu.

### 4.1. Dừng bằng execution ID

```java
import org.springframework.batch.core.launch.JobExecutionNotRunningException;
import org.springframework.batch.core.launch.NoSuchJobExecutionException;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BatchStopService {

    private final JobOperator jobOperator;

    public BatchStopService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long executionId)
            throws NoSuchJobExecutionException,
                   JobExecutionNotRunningException {

        // true = đã gửi tín hiệu dừng, chưa chắc execution đã STOPPED.
        return jobOperator.stop(executionId);
    }
}
```

Ví dụ gọi:

```java
boolean accepted = batchStopService.requestStop(101L);

if (accepted) {
    System.out.println("Đã gửi yêu cầu dừng execution 101");
}
```

Theo hợp đồng `JobOperator`:

- Giá trị `true` nghĩa là **tín hiệu dừng đã được gửi**, **không** bảo đảm job đã ngừng.
- `NoSuchJobExecutionException` nghĩa là không tồn tại execution với ID đã cung cấp.
- `JobExecutionNotRunningException` nghĩa là execution không còn ở trạng thái có thể dừng.
- Nếu phương thức trả `false`, hệ thống không nên hiển thị thành công; cần xem nguyên nhân và tình trạng metadata.

Không tự gọi `jobExecution.setStatus(BatchStatus.STOPPED)` trong API để giả vờ job đã ngừng. Thao tác cập nhật metadata đơn độc không buộc reader, writer hoặc tasklet dừng công việc.

### 4.2. Tìm các execution đang chạy theo tên job

Khi chưa biết ID, có thể liệt kê:

```java
import java.util.Set;
import org.springframework.batch.core.launch.JobOperator;

public class RunningJobFinder {

    private final JobOperator jobOperator;

    public RunningJobFinder(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public Set<Long> findRunningImportExecutions() throws Exception {
        return jobOperator.getRunningExecutions("importOrders");
    }
}
```

Nếu tập kết quả có nhiều ID, **đừng chọn `iterator().next()` một cách tùy tiện**. Hãy dùng `JobExplorer` đọc từng `JobExecution`, kiểm tra `JobParameters` và chọn đúng execution cần dừng.

Ví dụ trước khi gửi lệnh:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution == null) {
    throw new IllegalArgumentException("Execution không tồn tại: " + executionId);
}

System.out.println("executionId=" + execution.getId());
System.out.println("jobName=" + execution.getJobInstance().getJobName());
System.out.println("parameters=" + execution.getJobParameters());
System.out.println("status=" + execution.getStatus());
```

`JobExplorer` cung cấp giao diện đọc metadata; `JobRepository` quản lý dữ liệu execution và checkpoint. Nhiều ứng dụng cần dùng cả hai: `JobOperator` để gửi lệnh, `JobExplorer` để quan sát.

## 5. Theo dõi đến khi có trạng thái dừng cuối cùng

Sau khi gọi `stop`, bước tiếp theo là đọc lại trạng thái từ nguồn metadata có thể quan sát được:

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public class BatchStatusReader {

    private final JobExplorer jobExplorer;

    public BatchStatusReader(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public BatchStatus getStatus(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "Không tìm thấy JobExecution " + executionId);
        }

        return execution.getStatus();
    }
}
```

Một ứng dụng quản trị thường hiển thị:

```text
POST /batch/executions/101/stop
202 Accepted
{
  "executionId": 101,
  "message": "Stop requested"
}

GET /batch/executions/101
200 OK
{
  "executionId": 101,
  "batchStatus": "STOPPING"
}

GET /batch/executions/101
200 OK
{
  "executionId": 101,
  "batchStatus": "STOPPED"
}
```

Đây là **ví dụ hợp đồng REST tự xây dựng**, không phải endpoint Spring Batch tự tạo sẵn. HTTP `202 Accepted` phù hợp hơn `200 Stopped` vì công việc dừng diễn ra sau khi API trả về.

Khi client theo dõi, dùng polling với khoảng cách hợp lý và timeout. Cần cho phép hiển thị `STOPPING` trong một khoảng thời gian, sau đó báo trạng thái “yêu cầu dừng còn đang xử lý” hoặc “cần kiểm tra vận hành” nếu vượt thời gian quy định. **Không tự động gán `STOPPED` chỉ vì polling timeout.**

### 5.1. Một service nhỏ phục vụ trang quản trị

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class BatchExecutionControl {

    private final JobOperator operator;
    private final JobExplorer explorer;

    public BatchExecutionControl(JobOperator operator, JobExplorer explorer) {
        this.operator = operator;
        this.explorer = explorer;
    }

    public boolean stop(long executionId) throws Exception {
        return operator.stop(executionId);
    }

    public BatchStatus status(long executionId) {
        JobExecution execution = explorer.getJobExecution(executionId);

        if (execution == null) {
            throw new IllegalArgumentException(
                    "Unknown JobExecution: " + executionId);
        }

        return execution.getStatus();
    }
}
```

API/controller phía ngoài nên biến các exception thành phản hồi phù hợp: `404` cho ID không tồn tại, `409` cho execution đã kết thúc hoặc đang không thể stop, `202` khi tín hiệu đã được chấp nhận. Quyền dừng job phải được giới hạn cho người vận hành được ủy quyền và nên được ghi audit (ai yêu cầu, vào lúc nào, execution nào và lý do).

## 6. Vì sao stop có thể chậm?

Spring Batch kiểm soát được luồng xử lý **khi framework có cơ hội lấy lại quyền điều khiển**. Hành vi cụ thể phụ thuộc loại step.

### 6.1. Với chunk-oriented step

Luồng đơn giản:

```text
Đọc item → process → write chunk → commit/checkpoint
                         ↑
                 Có lệnh stop trong lúc xử lý
                         ↓
               Framework kiểm tra tín hiệu
                         ↓
                  Dừng tại điểm thích hợp
```

Khi chunk đang thực hiện, framework thường chờ công việc hiện tại đi qua điểm kiểm tra phù hợp. Đừng hiểu `stop` là rollback mọi thay đổi trước đây: các chunk **đã commit** có thể vẫn tồn tại. Chunk đang xử lý có thể commit hoặc rollback tùy thời điểm, exception, cấu hình transaction và thành phần được gọi. Cần kiểm tra `commitCount`, `rollbackCount` và dữ liệu thực tế thay vì giả định một kết quả chung.

Nếu `chunkSize` là 10.000 và mỗi item mất lâu, độ trễ dừng có thể lớn. Có thể điều chỉnh chunk size theo cân bằng giữa throughput, chi phí transaction và khả năng phản hồi khi dừng; không có một con số phù hợp cho mọi job.

**Ví dụ cấu hình step — Spring Batch 5.x:**

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, ProcessedOrder> orderProcessor,
        ItemWriter<ProcessedOrder> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(100, transactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

`Order` và `ProcessedOrder` là các kiểu nghiệp vụ minh họa. `chunk(100, ...)` chỉ thể hiện một điểm xuất phát để cấu hình; thay đổi theo hồ sơ tải và mục tiêu vận hành. Nếu writer gọi API ngoài với timeout 30 phút, chunk size nhỏ vẫn không giúp stop nhanh trong thời gian lời gọi API bị block.

### 6.2. Với `Tasklet` chạy lâu

Một `Tasklet` chứa vòng lặp vô hạn hoặc giữ quyền điều khiển quá lâu sẽ làm tín hiệu dừng phải đợi:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    while (true) {
        // Một tác vụ kéo dài không nhường quyền điều khiển
        // cho framework, khiến stop khó có hiệu lực.
        pollRemoteService();
    }
}
```

Đây là **mẫu cần tránh**, không phải đoạn code để đưa vào production. Nên chia công việc thành các đơn vị hữu hạn và trả về `RepeatStatus.CONTINUABLE` để framework có thể lặp lại tasklet, quản lý transaction và kiểm tra trạng thái.

```java
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

public class OnePageTasklet implements Tasklet {

    private final PageImporter importer;

    public OnePageTasklet(PageImporter importer) {
        this.importer = importer;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) throws Exception {

        boolean hasMorePages = importer.importNextPage();

        // Kết thúc một đơn vị công việc có thời gian hữu hạn.
        // Nếu tiếp tục, framework được lấy lại quyền điều khiển.
        return hasMorePages
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    }
}
```

Ở đây `PageImporter` là interface nghiệp vụ giả định: mỗi lần `importNextPage()` xử lý tối đa một trang và trả về có còn trang tiếp hay không. Muốn **restart** đúng, cursor/page index cũng cần được lưu bền vững (ví dụ qua `ExecutionContext` theo chu kỳ checkpoint), không chỉ lưu trong field của singleton bean.

### 6.3. I/O, khóa và timeout

Các nguyên nhân thường làm dừng chậm:

- Reader đang chờ network, file system hoặc database lock mà không có timeout.
- Writer thực hiện một request HTTP dài hoặc retry nội bộ quá nhiều lần.
- Tasklet giữ vòng lặp liên tục và không nhường quyền điều khiển.
- Transaction của chunk kéo dài; cơ sở dữ liệu đang chờ khóa.
- Job chạy ở worker/process khác và worker không thể cập nhật `JobRepository` kịp thời.

Một thiết kế có khả năng dừng tốt nên có timeout I/O hữu hạn, kích thước đơn vị công việc hợp lý, checkpoint có thể restart và log đủ để xác định bước nào đang chặn dừng. Đừng dùng `Thread.stop()` (đã deprecated/không an toàn) hoặc cưỡng bức chỉnh trạng thái metadata như cách “giải quyết” các vấn đề này.

## 7. Chủ động yêu cầu dừng từ bên trong step

Ngoài API điều hành từ bên ngoài, Spring Batch có `StepExecution.setTerminateOnly()`. Nó đánh dấu rằng **step đang thực thi muốn kết thúc**, để framework xử lý ở điểm phù hợp. Đây là cơ chế yêu cầu kết thúc phát sinh **bên trong cùng luồng execution**, khác với `JobOperator.stop(executionId)` từ console/API.

Ví dụ, listener kiểm tra rằng số lỗi nghiệp vụ đã vượt ngưỡng và muốn yêu cầu step dừng:

```java
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;

public class BusinessStopListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        // Có thể chuẩn bị trạng thái cần thiết.
    }

    public void requestStopIfNeeded(
            StepExecution stepExecution,
            boolean stopRequired) {

        if (stopRequired) {
            stepExecution.setTerminateOnly();
        }
    }
}
```

Đoạn trên minh họa primitive `setTerminateOnly()`; chính ứng dụng phải gọi `requestStopIfNeeded(...)` tại nơi có điều kiện nghiệp vụ. Không tự hiểu rằng Spring Batch sẽ gọi phương thức tùy ý này như callback.

Ở một `Tasklet` cần dừng theo điều kiện nghiệp vụ, có thể lấy `StepExecution` từ `StepContribution`:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext context) {

    if (maintenanceWindowReached()) {
        contribution.getStepExecution().setTerminateOnly();
        return RepeatStatus.FINISHED;
    }

    processOneUnit();
    return RepeatStatus.CONTINUABLE;
}
```

`maintenanceWindowReached()` và `processOneUnit()` là các hàm giả định của ứng dụng. Đặt cờ `terminateOnly` không đồng nghĩa thread kết thúc tức thì; framework còn cần xử lý transition/metadata. Cơ chế này không thể thay thế endpoint stop từ xa: đối tượng `StepExecution` trong bộ nhớ không nhất thiết tự cập nhật theo một bản ghi `JobExecution` vừa bị thay đổi bởi tiến trình khác.

**Phân biệt với việc tự ném exception:** Một exception nghiệp vụ không được xử lý có thể khiến step `FAILED`. Nếu yêu cầu là “tạm dừng để sau đó restart”, dùng cơ chế stop phù hợp sẽ diễn đạt đúng mục đích vận hành hơn việc cố tình tạo lỗi.

## 8. Stop, stopAndRestart, end, fail và abandon

Những cơ chế này dễ bị nhầm vì đều có thể kết thúc sớm một job nhưng ý nghĩa khác nhau.

| Cơ chế | Khi nào dùng | `BatchStatus` cuối | Khả năng tiếp tục |
|---|---|---|---|
| `JobOperator.stop(executionId)` | Người vận hành yêu cầu dừng một execution đang chạy | Thường `STOPPED` nếu dừng thành công | Có thể restart nếu job cho phép |
| `StepExecution.setTerminateOnly()` | Logic bên trong step yêu cầu dừng | Thường `STOPPED` qua framework | Tùy checkpoint và cấu hình |
| `stopAndRestart(nextStep)` | Flow dừng có chủ đích ở ranh giới step | `STOPPED` | Restart tại step định trước |
| `.end()` | Flow kết thúc và được xem là hoàn thành | `COMPLETED` | Cùng `JobInstance` đã hoàn thành không restart bình thường |
| `.fail()` | Flow chủ ý đánh dấu thất bại | `FAILED` | Có thể restart nếu điều kiện cho phép |
| `JobOperator.abandon(...)` | Đánh dấu execution đã không còn được tiếp tục | `ABANDONED` | Không restart execution đã abandon |

### 8.1. Stop có chủ đích tại ranh giới một step

Đôi khi cần job dừng sau bước kiểm tra dữ liệu, để người vận hành duyệt rồi cho phép chạy bước sau. Đó là **flow control đã định nghĩa trước**, không cần chờ bấm Stop giữa lúc step đang chạy.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
Job stagedImportJob(
        JobRepository jobRepository,
        Step validateStep,
        Step applyStep) {

    return new JobBuilder("stagedImportJob", jobRepository)
            .start(validateStep)
            .on("COMPLETED")
            .stopAndRestart(applyStep)
            .end()
            .build();
}
```

Khi `validateStep` thành công, job chuyển sang `STOPPED`. Lần restart sau sẽ bắt đầu từ `applyStep` theo flow đã cấu hình. Không nhầm điều này với `JobOperator.stop`: lệnh stop vận hành nhắm một **execution đang chạy**, còn `stopAndRestart` xác định đường đi của **job flow**.

### 8.2. Không dùng abandon để thay stop

`ABANDONED` thể hiện ý định **không restart** execution đó. Nó không phải lời gọi dừng mềm tiến trình đang hoạt động. Đặc biệt, nếu một JVM đã chết đột ngột và metadata vẫn `STARTED`, cần xác minh tiến trình thực sự không còn hoạt động và xem dữ liệu checkpoint trước khi sửa trạng thái. Việc chuyển sang `FAILED` hay `ABANDONED` là quyết định vận hành tùy khả năng phục hồi của dữ liệu, không nên tự động chỉ vì một timeout ngắn.

## 9. Restart sau khi STOPPED

Sau khi trạng thái đã thực sự thành `STOPPED`, có thể khởi chạy lại bằng `JobOperator.restart(executionId)` trong Spring Batch 5.2.

```java
import org.springframework.batch.core.launch.JobOperator;

public class BatchRestartService {

    private final JobOperator jobOperator;

    public BatchRestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public long restart(long stoppedExecutionId) throws Exception {
        // Trả về ID của JobExecution MỚI.
        return jobOperator.restart(stoppedExecutionId);
    }
}
```

Ví dụ:

```text
Trước khi stop:
  JobInstance=27, JobExecution=101, status=STARTED

Sau khi stop:
  JobInstance=27, JobExecution=101, status=STOPPED

Sau khi restart:
  JobInstance=27, JobExecution=101, status=STOPPED
  JobInstance=27, JobExecution=117, status=STARTED
```

**Restart không phải “resume thread cũ”.** Framework khởi chạy execution mới cho cùng `JobInstance`, dùng metadata và `ExecutionContext` đã lưu để xác định phần công việc cần tiếp tục.

Các điều kiện quan trọng:

1. `Job` phải được cấu hình restartable, và execution trước ở trạng thái hợp lệ cho restart.
2. `ItemReader`/`ItemWriter` có state cần lưu checkpoint đúng cách (ví dụ `ItemStream` và `ExecutionContext`).
3. Transaction và tác động ngoài database phải có cơ chế tránh ghi trùng. Đã commit 100 đơn hàng thì restart không được nhập lại tùy tiện 100 đơn đó.
4. Các identifying `JobParameters` của cùng job instance phải giữ nguyên. Nếu thay `businessDate` hoặc thêm một identifying `run.id`, có thể vô tình tạo `JobInstance` mới, nghĩa là chạy mới thay vì restart.
5. Khi job được cấu hình `preventRestart()` hoặc logic nghiệp vụ không restart an toàn, hệ thống phải hiển thị rõ trạng thái cần thao tác thủ công.

Với file reader, việc lưu số dòng đã đọc trong `ExecutionContext` chỉ có ích nếu file nguồn bất biến hoặc được định danh/kiểm tra checksum. Nếu file nguồn bị đổi giữa lúc stop và restart, đọc từ “dòng 5001” có thể không còn đúng bản ghi cũ.

## 10. Dừng trong hệ thống chạy phân tán

Một ứng dụng có thể có API quản trị trên instance A nhưng job thực thi trên worker B. Trường hợp này cần phân biệt:

```text
Operator / Admin UI
       |
       v
API (instance A)
       |
       | JobOperator.stop(jobExecutionId)
       v
JobRepository (database chung)
       |
       | lưu trạng thái/yêu cầu stop
       v
Worker (instance B)
       |
       | trả quyền cho Spring Batch tại điểm kiểm tra
       v
JobRepository: STOPPED
```

Mô hình trên mô tả **ý tưởng điều khiển qua metadata**, không phải bảo đảm mọi kiểu remote partitioning/scheduling đều tự lan truyền stop đến từng worker. Với remote chunking, partitioning, message consumer hoặc tác vụ gửi qua hệ thống khác, cần xác định rõ thành phần nào quản lý worker, cơ chế stop được truyền đến đâu và dữ liệu nào đã commit.

Điều kiện vận hành tối thiểu:

- API và worker trỏ đến đúng `JobRepository`/database và cùng môi trường; ID execution thường không có ý nghĩa toàn cục giữa các môi trường.
- Job có checkpoint và transaction phù hợp.
- Các tác vụ I/O có timeout; không để worker bị block vô hạn.
- Dữ liệu cấu hình và job definition đủ tương thích để restart.
- Có audit và phân quyền cho lệnh stop/restart/abandon.
- Có cơ chế phát hiện JVM/worker đã chết để tránh chờ `STOPPING` vô hạn.

Nếu job chạy trong container/Kubernetes, việc xóa Pod hoặc gửi `SIGKILL` không có nghĩa Spring Batch đã nhận được một lệnh `JobOperator.stop`. Shutdown graceful của hạ tầng cần thời gian cho ứng dụng đóng và cập nhật trạng thái, nhưng vẫn có thể thất bại nếu hết grace period. Ở Spring Batch 6, framework có thêm `JobExecutionShutdownHook` để hỗ trợ xử lý tín hiệu shutdown phù hợp; khi dùng 5.x, cần dựa trên cơ chế phiên bản và cách triển khai cụ thể.

## 11. Kiểm thử chức năng Stop job

Kiểm thử stop nên tách giữa **lệnh yêu cầu dừng** và **kết quả dừng thực tế**.

### 11.1. Unit test lớp điều khiển

Kiểm tra rằng service gửi chính xác execution ID tới `JobOperator`, và giữ đúng giá trị trả về hoặc exception.

```java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.launch.JobOperator;

class BatchStopServiceTest {

    @Test
    void shouldForwardStopRequestForSpecifiedExecution() throws Exception {
        JobOperator operator = org.mockito.Mockito.mock(JobOperator.class);
        BatchStopService service = new BatchStopService(operator);

        when(operator.stop(101L)).thenReturn(true);

        assertTrue(service.requestStop(101L));
        verify(operator).stop(101L);
    }

    @Test
    void shouldNotClaimSuccessWhenSignalWasNotSent() throws Exception {
        JobOperator operator = org.mockito.Mockito.mock(JobOperator.class);
        BatchStopService service = new BatchStopService(operator);

        when(operator.stop(102L)).thenReturn(false);

        assertFalse(service.requestStop(102L));
        verify(operator).stop(102L);
    }
}
```

Đây là unit test về **lời gọi tới API**. Nó chưa chứng minh Spring Batch thay `BatchStatus` thành `STOPPING` hay worker kết thúc thật.

### 11.2. Integration test với đồng bộ sự kiện thay cho ngủ cố định

Để kiểm tra vòng đời thật, hãy chạy một job trên thread khác, đặt một `Tasklet` có `CountDownLatch` để giữ tại điểm xác định, gửi `stop`, rồi giải phóng latch. Điều này giúp test chủ động điều khiển thứ tự:

```text
Test thread                    Job thread
-----------                    ----------
start job  ------------------>  tasklet bắt đầu
await(entered) <-------------  entered.countDown()
JobOperator.stop(id)            tasklet đang đợi
release.countDown() --------->  tasklet trả quyền điều khiển
đợi job kết thúc              -> framework hoàn tất STOPPED
assert STOPPED
```

Một test minh họa đầy đủ với Spring Boot 3.x / Spring Batch 5.x:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Set;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;

import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.StepContribution;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.scope.context.ChunkContext;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.repeat.RepeatStatus;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootTest(
        classes = StopJobIntegrationTest.TestApplication.class,
        properties = {
                "spring.batch.job.enabled=false",
                "spring.batch.jdbc.initialize-schema=always"
        }
)
class StopJobIntegrationTest {

    @Autowired JobLauncher launcher;
    @Autowired JobOperator operator;
    @Autowired Job job;
    @Autowired GateTasklet tasklet;

    @Test
    void stopShouldFinishAsStoppedAfterTaskletReturnsControl()
            throws Exception {

        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<JobExecution> future = executor.submit(() ->
                    launcher.run(
                            job,
                            new JobParametersBuilder()
                                    .addLong("run.id", 1L)
                                    .toJobParameters()
                    )
            );

            assertTrue(tasklet.entered.await(5, TimeUnit.SECONDS));

            Set<Long> running = operator.getRunningExecutions("stoppableJob");
            assertEquals(1, running.size());

            long executionId = running.iterator().next();
            assertTrue(operator.stop(executionId));

            // Tasklet trả quyền cho framework, nơi xử lý stop.
            tasklet.release.countDown();

            JobExecution execution = future.get(10, TimeUnit.SECONDS);
            assertEquals(executionId, execution.getId().longValue());
            assertEquals(BatchStatus.STOPPED, execution.getStatus());
        } finally {
            // Đảm bảo giải phóng tasklet nếu assertion trước đó thất bại.
            tasklet.release.countDown();
            executor.shutdownNow();
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean GateTasklet gateTasklet() {
            return new GateTasklet();
        }

        @Bean
        Step stoppableStep(
                JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                GateTasklet tasklet) {

            return new StepBuilder("stoppableStep", jobRepository)
                    .tasklet(tasklet, transactionManager)
                    .build();
        }

        @Bean
        Job job(JobRepository jobRepository, Step stoppableStep) {
            return new JobBuilder("stoppableJob", jobRepository)
                    .start(stoppableStep)
                    .build();
        }
    }

    static class GateTasklet implements Tasklet {
        final CountDownLatch entered = new CountDownLatch(1);
        final CountDownLatch release = new CountDownLatch(1);

        @Override
        public RepeatStatus execute(
                StepContribution contribution,
                ChunkContext context) throws Exception {

            entered.countDown();

            if (!release.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Test gate timed out");
            }

            // Tạo thêm một lượt để framework xử lý tín hiệu stop.
            return RepeatStatus.CONTINUABLE;
        }
    }
}
```

Dữ liệu `run.id=1` ở đây chỉ phù hợp khi test dùng JobRepository độc lập và được tạo sạch cho từng trường hợp. Với test suite chung, dùng `JobParameters` định danh duy nhất hoặc dọn metadata test đúng cách để không bị lỗi job instance đã `COMPLETED`. Nếu môi trường dùng asynchronous `JobLauncher`, cần điều chỉnh chờ kết quả; ví dụ trên chủ động dùng `ExecutorService` ngoài để launch job.

Test trên minh họa cách kiểm chứng hợp tác dừng tại ranh giới tasklet. Nó không chứng minh stop sẽ kết thúc được I/O không timeout, không kiểm tra rollback của writer, và không thay thế integration test với reader/writer production.

### 11.3. Các tình huống nên kiểm tra thêm

| Tình huống | Điều cần khẳng định |
|---|---|
| Stop khi `STARTED` | Yêu cầu được nhận; trạng thái cuối được quan sát là `STOPPED` nếu execution xử lý stop |
| Stop khi `STOPPING` | API trả trạng thái phù hợp, tránh gọi lại vô hạn |
| Stop ID không tồn tại | Không trả thành công giả; mapping lỗi rõ ràng |
| Stop execution đã `COMPLETED` | Không thay đổi job đã hoàn thành |
| Stop giữa chunk | Dữ liệu commit/checkpoint nhất quán; không mất hoặc nhân đôi bản ghi khi restart |
| Stop lúc writer lỗi | Trạng thái cuối có thể là `FAILED`; báo cáo đúng nguyên nhân |
| Restart sau `STOPPED` | Tạo `JobExecution` mới trong cùng `JobInstance`, không xử lý lại các item đã commit ngoài ý muốn |
| Worker bị kill giữa chừng | Phát hiện metadata cũ và cần quy trình phục hồi; không giả định tự chuyển `STOPPED` |
| Hai người gửi stop gần nhau | Không phát sinh lệnh điều khiển trùng/khó hiểu; audit mỗi yêu cầu |

Khi test chạy thực sự bất đồng bộ, hãy dùng latch, future hoặc polling trạng thái với **giới hạn thời gian**. Tránh `Thread.sleep(5000)` làm cách dự đoán lúc job đã bắt đầu hoặc đã dừng; ngủ một thời lượng cố định vừa chậm vừa không bảo đảm điều kiện đúng.

## 12. Quy trình vận hành đề xuất

Một luồng thao tác an toàn khi phát hiện job nhập nhầm dữ liệu:

1. **Xác định execution.** Đọc danh sách job đang chạy, chọn đúng `jobExecutionId` và kiểm tra `JobParameters` để tránh dừng nhầm ngày nghiệp vụ.
2. **Gửi yêu cầu stop.** Ghi audit lý do và người thực hiện; gọi `JobOperator.stop(executionId)`.
3. **Theo dõi trạng thái.** Đọc lại từ `JobExplorer` đến khi `STOPPED`, `FAILED`, hoặc `COMPLETED`; nếu `STOPPING` quá lâu, kiểm tra tasklet, I/O, lock và sức khỏe worker.
4. **Kiểm tra dữ liệu.** Đối chiếu số item đọc/ghi, `commitCount`, `rollbackCount`, các side effect đã thực hiện và checkpoint của `ExecutionContext`.
5. **Xác nhận cách phục hồi.** Giữ nguồn dữ liệu phù hợp, xử lý nguyên nhân ban đầu và đánh giá idempotency trước khi restart.
6. **Restart hoặc kết thúc xử lý.** Chỉ gọi `restart` khi có trạng thái và điều kiện hợp lệ; nếu không thể tiếp tục an toàn, áp dụng quy trình phục hồi riêng thay vì tự đổi metadata.

Ví dụ log vận hành nên có các trường:

```text
event=batch.stop.requested
jobName=importOrders
jobExecutionId=101
businessDate=2025-05-12
requestedBy=ops-user
reason=source-file-invalid
requestAccepted=true

event=batch.stop.observed
jobExecutionId=101
batchStatus=STOPPED
readCount=50000
writeCount=49750
commitCount=498
```

Các giá trị số là dữ liệu minh họa. Log cần được lấy từ execution thực tế, đồng thời tránh ghi token, mật khẩu hoặc dữ liệu cá nhân nhạy cảm.

### Khi stop “không có tác dụng”

Nếu mã vẫn chạy dù đã gọi `stop`, kiểm tra theo thứ tự nguyên nhân thực tế: đúng execution ID và `JobRepository` chưa, giá trị trả về lệnh stop là gì, `BatchStatus` có chuyển sang `STOPPING` không, worker đang ở step nào, công việc hiện tại có timeout không, và việc đọc checkpoint có bị khóa hay không. Một lỗi thường gặp là dừng từ một ứng dụng quản trị trỏ vào database test trong khi worker chạy trên database production.

Nếu process đã chết, không thể mong đợi một thread đã biến mất quay lại để đổi `STOPPING` thành `STOPPED`. Trạng thái metadata cần được đối chiếu với trạng thái hệ thống và xử lý theo quy trình recovery có kiểm soát.

## 13. Bài tập thực hành

Xây dựng job `archiveOrders` gồm hai step: `findExpiredOrders` và `writeArchive`. Bước thứ hai ghi mỗi lần tối đa 100 bản ghi trong một chunk. Yêu cầu:

1. Tạo API nhận `jobExecutionId` và gọi `JobOperator.stop(...)`. API trả `202 Accepted` khi nhận yêu cầu, kèm URL kiểm tra trạng thái.
2. Xây màn hình/truy vấn hiển thị tên job, `JobParameters`, `BatchStatus` và thời điểm cập nhật từ `JobExplorer`.
3. Dùng `CountDownLatch` trong integration test để gửi stop khi một chunk/tasklet đang hoạt động; xác nhận cuối cùng có `STOPPED`, đồng thời kiểm tra bản ghi đã commit.
4. Gọi `restart` từ ID execution đã `STOPPED` và chứng minh framework tạo một `JobExecution` mới cho cùng `JobInstance`.
5. Mô phỏng reader gọi API chậm: đặt timeout hợp lý, kiểm tra thời gian dừng không bị phụ thuộc vào chờ vô hạn.
6. Viết một flow dùng `stopAndRestart(nextStep)` sau bước kiểm tra, rồi giải thích vì sao đây là dạng dừng theo flow khác với người vận hành bấm Stop giữa chunk.

**Câu hỏi ôn tập:** Nếu `JobOperator.stop(101)` trả `true` và `JobExplorer` vẫn báo `STOPPING` sau 30 giây, có được kết luận batch đã dừng chưa? **Chưa.** Trạng thái này chỉ chứng minh tín hiệu dừng được ghi nhận; cần tiếp tục quan sát hoặc xử lý điểm nghẽn, tuyệt đối không tự đánh dấu `STOPPED` để che giấu công việc đang xử lý.

## 14. Tài liệu tham khảo

- [Spring Batch 5.2 — Advanced Metadata Usage: Stopping a Job](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html): dừng qua `JobOperator`, đặc tính graceful shutdown và cách xử lý execution bị bỏ dở.
- [Spring Batch 5.2 — JobOperator API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/launch/JobOperator.html): hợp đồng `stop(long)`, `getRunningExecutions`, `restart` và exception.
- [Spring Batch 5.2 — StepExecution API](https://docs.spring.io/spring-batch/docs/5.2.x/api/org/springframework/batch/core/StepExecution.html): `setTerminateOnly()` và `isTerminateOnly()`.
- [Spring Batch 5.2 — Controlling Step Flow](https://docs.spring.io/spring-batch/reference/5.2/step/controlling-flow.html): `stopAndRestart`, `end` và `fail`.
- [Spring Batch — Domain Language](https://docs.spring.io/spring-batch/reference/domain.html): `JobInstance`, `JobExecution`, `StepExecution`, `BatchStatus` và `ExecutionContext`.
- [Spring Batch 6 — JobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html): API `stop(JobExecution)` và trạng thái deprecated của overload nhận ID.
