# Đối chiếu log với metadata trong Spring Batch

Khi một Spring Batch Job chạy theo lịch hoặc được gọi qua API, hệ thống thường có hai dấu vết của cùng một lần thực thi: **log ứng dụng** và **metadata của `JobRepository`**. Log mô tả các sự kiện mà mã nguồn, listener và hạ tầng quan sát đã ghi nhận; metadata lưu danh tính, trạng thái và số liệu thực thi của `JobInstance`, `JobExecution` và `StepExecution`.

Hai nguồn này bổ sung cho nhau nhưng không nhất thiết được cập nhật cùng một thời điểm. Log “job completed” có thể xuất hiện trước khi bản cập nhật cuối được commit vào repository; một Job `COMPLETED` có thể không còn log do mất kết nối tới hệ thống thu thập; và khi JVM bị dừng đột ngột, metadata có thể vẫn là `STARTED` dù tiến trình thực tế không còn chạy.

**Đối chiếu log với metadata** là quá trình nối đúng các bản ghi, đọc chúng trong ngữ cảnh thời gian và kiểm tra xem chúng có phản ánh cùng một lần xử lý hay không. Việc này hỗ trợ điều tra lỗi, kiểm tra restart, phát hiện thiếu sự kiện quan sát, xây dựng dashboard và chuẩn bị quy trình phục hồi.

Bài học thuộc nhóm **Logging** của **Spring Batch Core Processing**. Nội dung triển khai từ mô hình định danh, cách thu thập dữ liệu, truy vấn Spring Batch, quy tắc đối chiếu đến ví dụ kiểm thử và vận hành.

## 1. Hai nguồn dữ liệu phản ánh những gì?

### 1.1. Log ứng dụng

Một dòng log có thể xuất hiện khi scheduler yêu cầu chạy Job, khi listener nhận callback hoặc khi Step phát sinh lỗi. Ví dụ:

```text
2026-11-16T02:00:00.042Z INFO  batch.job.launch.requested
  jobName=importInvoicesJob businessDate=2026-11-16 trigger=scheduler requestId=rq-91

2026-11-16T02:00:00.108Z INFO  batch.job.started
  jobName=importInvoicesJob jobInstanceId=51 jobExecutionId=7001

2026-11-16T02:00:04.214Z INFO  batch.step.finished
  jobExecutionId=7001 stepExecutionId=9101 stepName=readInvoices
  batchStatus=COMPLETED readCount=120 writeCount=120

2026-11-16T02:00:06.793Z INFO  batch.job.finished
  jobName=importInvoicesJob jobInstanceId=51 jobExecutionId=7001
  batchStatus=COMPLETED exitCode=COMPLETED
```

Các giá trị trên chỉ là dữ liệu minh họa. Log trả lời câu hỏi **đã quan sát thấy sự kiện nào, ở tiến trình nào và vào thời điểm nào**. Log còn có thể ghi trace ID, nguyên nhân lỗi, thông tin scheduler và các sự kiện nghiệp vụ nằm ngoài metadata Batch.

Một dòng log không tự bảo đảm rằng database đã commit mọi thay đổi hoặc Job không tiếp tục chạy sau khi sự kiện đó được gửi tới logger.

### 1.2. Metadata Spring Batch

`JobRepository` lưu trạng thái có cấu trúc của các lần chạy để quản lý `JobInstance`, `JobExecution`, `StepExecution` và hỗ trợ restart. Với repository dùng cơ sở dữ liệu quan hệ, metadata thường nằm trong các bảng bắt đầu bằng `BATCH_`.

Ví dụ sau khi Job hoàn thành:

```text
BATCH_JOB_INSTANCE
  JOB_INSTANCE_ID=51
  JOB_NAME=importInvoicesJob

BATCH_JOB_EXECUTION
  JOB_EXECUTION_ID=7001
  JOB_INSTANCE_ID=51
  STATUS=COMPLETED
  EXIT_CODE=COMPLETED

BATCH_STEP_EXECUTION
  STEP_EXECUTION_ID=9101
  JOB_EXECUTION_ID=7001
  STEP_NAME=readInvoices
  STATUS=COMPLETED
  READ_COUNT=120
  WRITE_COUNT=120
```

Metadata trả lời câu hỏi **Spring Batch đã ghi nhận lần thực thi nào và trạng thái/bộ đếm nào được lưu**. Đây là điểm tham chiếu quan trọng cho lifecycle và restart, nhưng metadata không chứa tất cả nghiệp vụ, mọi dòng log hoặc đầy đủ stack trace như log collector.

### 1.3. Không xem hai nguồn là bản sao của nhau

| Góc nhìn | Log | Metadata Spring Batch |
| --- | --- | --- |
| Được tạo bởi | Scheduler, launcher, listener, Step, hệ thống logging | Spring Batch thông qua `JobRepository` |
| Định danh chính | Event ID, trace/request ID và các Batch ID được đưa vào log | Job name, JobInstance ID, JobExecution ID, StepExecution ID |
| Trạng thái Job | Ảnh chụp tại thời điểm log | Giá trị được lưu và cập nhật qua các transaction |
| Nội dung lỗi | Có thể có message, exception type hoặc stack trace đã lọc | Status, exit code/description và dữ liệu liên quan trong repository |
| Bộ đếm item | Chỉ có nếu ứng dụng log | Các trường `READ_COUNT`, `WRITE_COUNT`, `SKIP_COUNT`, v.v. |
| Trường hợp mất dữ liệu | Log chưa được gửi hoặc bị drop/rotate | Transaction chưa commit, DB lỗi, metadata bị dọn |
| Dùng cho restart | Hỗ trợ điều tra | Metadata và execution context là cơ sở của cơ chế restart |

**Đối chiếu** nhằm xác định phần giao nhau hợp lệ, không ép tất cả trường của log phải xuất hiện trong metadata.

## 2. Khóa nối dữ liệu: JobInstance ID và JobExecution ID

Trước khi so sánh trạng thái, phải nối đúng các bản ghi. Trong Spring Batch:

- `Job` là định nghĩa công việc, ví dụ `importInvoicesJob`.
- `JobInstance` biểu diễn một đơn vị công việc logic, xác định bằng **tên Job + identifying JobParameters**.
- `JobExecution` là một lần cố gắng chạy JobInstance.
- `StepExecution` là một lần thực thi Step trong phạm vi JobExecution.

```text
Job: importInvoicesJob
│
├── JobInstance #51 (businessDate=2026-11-16)
│   ├── JobExecution #7001 -> FAILED
│   │   ├── StepExecution #9101 -> COMPLETED
│   │   └── StepExecution #9102 -> FAILED
│   └── JobExecution #7002 -> COMPLETED (restart)
│       └── StepExecution #9103 -> COMPLETED
│
└── JobInstance #52 (businessDate=2026-11-17)
    └── JobExecution #7003 -> COMPLETED
```

Ở đây `7001` và `7002` cùng `jobInstanceId=51` nhưng là **hai lần chạy khác nhau**. Nếu chỉ lọc log theo `jobName` hoặc ngày nghiệp vụ, dễ gộp nhầm lỗi của lần trước với kết quả của lần restart.

Các trường nối được khuyến nghị:

| Cấp độ | Khóa nên dùng | Lưu ý |
| --- | --- | --- |
| Yêu cầu khởi chạy | `requestId` hoặc `triggerId` | Có thể có trước khi tạo được JobExecution. |
| Job logic | `jobName` + identifying parameters hoặc `jobInstanceId` | Nhóm các lần restart của cùng đơn vị công việc. |
| Một lần chạy | `jobExecutionId` | Khóa chính để so sánh log lifecycle với metadata JobExecution. |
| Một lần chạy Step | `stepExecutionId`, kèm `jobExecutionId` | Phân biệt Step cùng tên ở nhiều lần chạy, partition hoặc restart. |
| Tác vụ phân tán | `partitionId`/`workerId` kèm Batch ID | Hỗ trợ tập hợp log từ nhiều worker. |

**`jobExecutionId` là ID do repository cấp**, thường đủ để đối chiếu trong phạm vi một repository. Nếu có nhiều môi trường hoặc database độc lập, các ID số có thể trùng nhau. Trong log tập trung cần thêm **environment/service/repository identifier** để không nối nhầm bản ghi giữa development, staging, production hoặc những deployment có metadata riêng.

### Vì sao không thể chỉ dùng JobParameters?

Ví dụ hai yêu cầu:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("requestId", "rq-91", false)
        .toJobParameters();
```

Đoạn mã dùng Spring Batch 5.x. `businessDate` là identifying parameter; `requestId` được đánh dấu non-identifying. Nếu lần restart tạo một `requestId` mới nhưng giữ nguyên identifying parameters, nó vẫn thuộc cùng `JobInstance`.

Ngược lại, nếu ứng dụng thêm `run.id` mới ở chế độ identifying, mỗi lần khởi chạy có thể tạo JobInstance khác. Khi đối chiếu, phải kiểm tra cấu hình identifying parameters thực tế, không đoán quan hệ instance chỉ từ các giá trị tham số xuất hiện trong log.

## 3. Thiết kế log có thể đối chiếu

Một log dễ tìm kiếm nên dùng tên sự kiện thống nhất và các trường rõ ràng, ví dụ JSON:

```json
{
  "timestamp": "2026-11-16T02:00:06.793Z",
  "level": "INFO",
  "event": "batch.job.finished",
  "environment": "test",
  "service": "invoice-batch",
  "jobName": "importInvoicesJob",
  "jobInstanceId": 51,
  "jobExecutionId": 7001,
  "batchStatus": "COMPLETED",
  "exitCode": "COMPLETED",
  "durationMs": 6685
}
```

Tùy hệ thống, có thể ghi text log với các cặp `key=value` thay cho JSON. Quan trọng là giữ **tên trường và kiểu dữ liệu nhất quán**.

Bộ trường tối thiểu:

1. `event`: `batch.job.launch.requested`, `batch.job.started`, `batch.job.finished`, `batch.step.finished` hoặc `batch.job.launch.rejected`.
2. `jobName` và Batch ID hiện có ở thời điểm log.
3. `batchStatus` và `exitCode` ở sự kiện kết thúc.
4. `timestamp` có timezone rõ ràng, ưu tiên UTC khi log tập trung.
5. `environment`/`repositoryAlias` nếu nhiều repository cùng gửi vào một hệ thống log.

Trường bổ sung có ích: `traceId`, `requestId`, `trigger`, `stepName`, `stepExecutionId`, `durationMs`, `readCount`, `writeCount`, `skipCount`, `failureType`.

Không nên log mọi `JobParameters` hoặc toàn bộ `ExecutionContext`. Chúng có thể chứa thông tin cá nhân, token, đường dẫn nhạy cảm hoặc dữ liệu nội bộ. Chỉ đưa business key được phép công khai theo chính sách vào log.

### Phân biệt sự kiện accepted và finished

```text
Scheduler           JobLauncher              Worker/Step          JobRepository
   │                     │                       │                       │
   ├─ requested ────────>│                       │                       │
   │                     ├─ createExecution ────────────────────────────>│
   │<── accepted ────────┤                       │                       │
   │                     └────────── start ─────>│                       │
   │                                             ├─ STARTED ────────────>│
   │                                             ├─ process              │
   │                                             └─ COMPLETED ──────────>│
   │                                             └─ finished log         │
```

Với launcher bất đồng bộ, **`accepted` chỉ xác nhận yêu cầu đã được chấp nhận**, không nói rằng Job đã hoàn tất. Một lỗi trước khi tạo JobExecution có thể chỉ có `requested` và `rejected`, không có `jobExecutionId` mới để tra `BATCH_JOB_EXECUTION`.

Đây là điểm cần phân loại ngay khi thiết kế quy tắc đối chiếu để tránh báo “thiếu metadata” sai.

## 4. Những bảng metadata dùng để kiểm chứng

Với `JobRepository` dựa trên database quan hệ và prefix mặc định:

| Bảng | Các trường thường dùng | Phần log đối chiếu |
| --- | --- | --- |
| `BATCH_JOB_INSTANCE` | `JOB_INSTANCE_ID`, `JOB_NAME`, `JOB_KEY` | `jobInstanceId`, `jobName` |
| `BATCH_JOB_EXECUTION` | `JOB_EXECUTION_ID`, `JOB_INSTANCE_ID`, `STATUS`, `EXIT_CODE`, `CREATE_TIME`, `START_TIME`, `END_TIME` | `jobExecutionId`, `batchStatus`, `exitCode`, thời gian |
| `BATCH_JOB_EXECUTION_PARAMS` | Các tham số được lưu với execution | Business key được phép sử dụng để điều tra |
| `BATCH_JOB_EXECUTION_CONTEXT` | Context ở cấp JobExecution | Chẩn đoán restart/checkpoint khi được phép |
| `BATCH_STEP_EXECUTION` | `STEP_EXECUTION_ID`, `JOB_EXECUTION_ID`, `STEP_NAME`, `STATUS`, `READ_COUNT`, `WRITE_COUNT`, `SKIP_COUNT` | `stepExecutionId`, `stepName`, Step status, item counters |
| `BATCH_STEP_EXECUTION_CONTEXT` | Context ở cấp StepExecution | Dữ liệu checkpoint/restart |

Tên bảng có thể được thay đổi bằng `tablePrefix` và định nghĩa cột thay đổi giữa các phiên bản Spring Batch. SQL ví dụ dưới đây giả định schema quan hệ mặc định phù hợp với Spring Batch 5.x/6.x. Luôn tham chiếu DDL thực tế của repository đang dùng.

### SQL lấy trạng thái Job từ execution ID

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS AS BATCH_STATUS,
    je.EXIT_CODE,
    je.CREATE_TIME,
    je.START_TIME,
    je.END_TIME,
    je.LAST_UPDATED
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE je.JOB_EXECUTION_ID = :executionId;
```

`:executionId` là placeholder của công cụ truy vấn hoặc JDBC framework; khi dùng SQL console trực tiếp, thay bằng cú pháp bind parameter tương ứng.

Ví dụ nếu log có `jobExecutionId=7001`, query cần trả về một JobExecution thuộc đúng `jobName` và `jobInstanceId` đã ghi. Khi status trong metadata là `COMPLETED`, kết quả này là dữ liệu Batch đã lưu, nhưng vẫn cần xem thời điểm cập nhật nếu log vừa phát ra.

### SQL lấy StepExecution của một JobExecution

```sql
SELECT
    se.JOB_EXECUTION_ID,
    se.STEP_EXECUTION_ID,
    se.STEP_NAME,
    se.STATUS AS BATCH_STATUS,
    se.EXIT_CODE,
    se.READ_COUNT,
    se.WRITE_COUNT,
    se.FILTER_COUNT,
    se.SKIP_COUNT,
    se.COMMIT_COUNT,
    se.ROLLBACK_COUNT,
    se.START_TIME,
    se.END_TIME
FROM BATCH_STEP_EXECUTION se
WHERE se.JOB_EXECUTION_ID = :executionId
ORDER BY se.STEP_EXECUTION_ID;
```

Kết quả giúp giải thích tại sao Job `FAILED` hoặc vì sao tổng dữ liệu xử lý khác mong đợi. Không nên lấy một `stepName` chung cho mọi lần chạy rồi cộng bộ đếm vô điều kiện: cùng tên Step có thể xuất hiện ở lần restart khác hoặc có tên phân vùng riêng.

### SQL xem các lần chạy của một JobInstance

```sql
SELECT
    JOB_INSTANCE_ID,
    JOB_EXECUTION_ID,
    STATUS,
    EXIT_CODE,
    START_TIME,
    END_TIME
FROM BATCH_JOB_EXECUTION
WHERE JOB_INSTANCE_ID = :instanceId
ORDER BY JOB_EXECUTION_ID;
```

Một instance có nhiều execution là tình huống bình thường khi restart. Trong báo cáo đối chiếu, nhóm theo `JobInstance` để thấy toàn bộ lịch sử, nhưng so sánh trạng thái từng execution bằng **execution ID riêng**.

## 5. Đọc metadata qua `JobExplorer`

Trong code Java, `JobExplorer` là API chỉ đọc thích hợp để tra cứu lịch sử mà không buộc lớp quan sát phải thao tác SQL theo từng bảng.

Ví dụ Spring Batch 5.x:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class BatchExecutionSnapshotReader {

    private final JobExplorer jobExplorer;

    public BatchExecutionSnapshotReader(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void printExecution(long executionId) {
        JobExecution execution =
                jobExplorer.getJobExecution(executionId);

        if (execution == null) {
            System.out.println("Execution not found: " + executionId);
            return;
        }

        System.out.printf(
                "job=%s instance=%d execution=%d status=%s exitCode=%s%n",
                execution.getJobInstance().getJobName(),
                execution.getJobInstance().getInstanceId(),
                execution.getId(),
                execution.getStatus(),
                execution.getExitStatus().getExitCode()
        );

        for (StepExecution step : execution.getStepExecutions()) {
            System.out.printf(
                    "  step=%s stepExecution=%d status=%s "
                        + "read=%d write=%d skip=%d%n",
                    step.getStepName(),
                    step.getId(),
                    step.getStatus(),
                    step.getReadCount(),
                    step.getWriteCount(),
                    step.getSkipCount()
            );
        }
    }
}
```

`System.out` dùng ở đây để minh họa dữ liệu trả về. Khi đưa vào ứng dụng, nên thay bằng đối tượng DTO hoặc log theo format thống nhất, tránh in metadata bừa bãi ra stdout production.

**Lưu ý về phiên bản:** Spring Batch 5.x đặt `JobExecution` và `StepExecution` trong package `org.springframework.batch.core`. Spring Batch 6.x tổ chức các kiểu này vào các package con như `org.springframework.batch.core.job` và `org.springframework.batch.core.step`; chỉnh import tương ứng với dependency thực tế. Vai trò của `JobExplorer` trong việc truy vấn metadata vẫn là trọng tâm.

### Vì sao nên đọc lại từ repository?

`JobExecution` trả về từ launcher là đối tượng ở thời điểm khởi chạy. Nếu Job chạy bất đồng bộ, trạng thái trên đối tượng đó có thể đang `STARTING` hoặc `STARTED`. Một bản truy vấn mới bằng `JobExplorer.getJobExecution(id)` giúp đọc dữ liệu **đã được lưu** tại thời điểm kiểm tra.

Với quá trình đối chiếu tự động, đọc lại sau một khoảng chờ có timeout là hợp lý khi Job đang chạy. Không nên dùng vòng polling vô hạn hoặc `Thread.sleep(...)` cố định rồi mặc định mọi execution đã kết thúc.

## 6. Quy trình đối chiếu theo từng bước

Khi nhận được một cảnh báo hoặc một log `batch.job.finished`, làm theo thứ tự sau.

### Bước 1: Xác định nguồn và phạm vi

Lấy `environment`, `service`/`repositoryAlias`, `jobName`, `jobInstanceId`, `jobExecutionId`. Nếu log chưa có ID vì launch bị từ chối, chuyển sang quy trình kiểm tra lỗi khởi chạy (`requestId`, ngoại lệ, tham số nhận diện) thay vì tìm một execution chưa từng được tạo.

Trước khi truy vấn, xác minh công cụ đang trỏ đến **đúng datasource của JobRepository**. Ứng dụng có thể có một datasource nghiệp vụ khác với datasource metadata Batch.

### Bước 2: Tra metadata cùng execution ID

Sử dụng `JobExplorer.getJobExecution(executionId)` hoặc SQL join hai bảng Job. So sánh:

- `jobName` có đúng với log không?
- `jobInstanceId` có đúng không?
- `jobExecutionId` có tồn tại không?
- `BatchStatus` và `ExitStatus` hiện tại là gì?
- Execution đã có `END_TIME` hay vẫn đang chạy?
- `LAST_UPDATED` mới đến đâu so với thời điểm quan sát?

Nếu ID tồn tại ở nhiều database độc lập, phải chọn nguồn theo environment/repository trước khi kết luận.

### Bước 3: Phân biệt trạng thái trung gian và trạng thái cuối

Một dòng log `batch.job.started status=STARTED` cùng với metadata `COMPLETED` ở thời điểm sau **không mâu thuẫn**. Log mô tả trạng thái tại lúc bắt đầu; metadata là ảnh chụp mới hơn.

Chỉ đối chiếu `batch.job.finished` với trạng thái kết thúc tương ứng sau khi biết Job thực sự đã kết thúc và các thay đổi cuối được lưu.

Các trạng thái cuối thường gặp gồm `COMPLETED`, `FAILED`, `STOPPED`, và trong một số tình huống `ABANDONED`. `STARTING`, `STARTED`, `STOPPING` là những trạng thái chưa thể kết luận đã hoàn tất.

### Bước 4: Đối chiếu từng StepExecution

Nếu Job có nhiều Step, tra `BATCH_STEP_EXECUTION` hoặc `JobExecution.getStepExecutions()`; nối theo `stepExecutionId` và `jobExecutionId`. So sánh status, exit code và các bộ đếm đã log ở **cùng mốc kết thúc Step**.

Nếu Step có skip/filter, `readCount` và `writeCount` không nhất thiết bằng nhau. Nếu một Step không được thực thi do flow rẽ nhánh hoặc restart, không có StepExecution mới cũng có thể là hành vi đúng.

### Bước 5: Đối chiếu dữ liệu nghiệp vụ nếu cần

Metadata ghi bộ đếm framework, không chứng minh mọi side effect bên ngoài đã có hiệu lực đúng một lần. Nếu cần điều tra việc ghi dữ liệu, kiểm tra bảng kết quả, file xuất, message hoặc API đích theo **business key** và tính idempotent của quy trình.

### Bước 6: Ghi nhận loại chênh lệch và kết quả điều tra

Đừng gộp tất cả tình huống thành “log sai” hoặc “metadata sai”. Ghi rõ:

```text
reconciliation.status = matched | pending | mismatch | missing_log
                        | missing_metadata | unknown
reconciliation.reason = status_not_final | telemetry_delay | wrong_repo
                        | launch_rejected | crash_suspected | ...
```

Các giá trị này là gợi ý mô hình dữ liệu cho ứng dụng giám sát, không phải enum có sẵn của Spring Batch.

## 7. Đối chiếu trạng thái theo thời gian: xử lý eventual consistency

Log và metadata không được ghi trong một transaction chung với dịch vụ thu thập log. Ngay cả trong cùng process, thứ tự thời gian quan sát từ bên ngoài có thể khác nhau.

Ví dụ:

```text
T0  Job bắt đầu; repository ghi STARTED
T1  Step cuối hoàn tất
T2  afterJob callback ghi log "batch.job.finished status=COMPLETED"
T3  Framework cập nhật JobExecution vào repository, transaction commit
T4  Log collector nhận được event từ T2
T5  Dashboard truy vấn repository và thấy COMPLETED
```

Tùy triển khai, bước ghi log/commit có thể có thứ tự hoặc độ trễ khác. Vì vậy, nếu query ở ngay sau khi log đến mà thấy `STARTED`, cần cho phép **khoảng thời gian hội tụ có giới hạn** trước khi phân loại mismatch.

Cơ chế đơn giản:

1. Nhận `batch.job.finished` với `jobExecutionId`.
2. Query repository.
3. Nếu trạng thái chưa kết thúc, đánh dấu `pending` và retry theo chính sách.
4. Nếu sau timeout metadata trở thành kết quả phù hợp, đánh dấu `matched`.
5. Nếu hết timeout và vẫn khác, tạo cảnh báo chênh lệch với cả hai snapshot để điều tra.

Không có một khoảng chờ cố định phù hợp mọi hệ thống. Chọn timeout theo thời gian ghi metadata, độ trễ log pipeline và SLA quan sát của ứng dụng. **Không dùng timeout để che một Job treo vô hạn**; việc kiểm tra worker/JobExecution bị kẹt là luồng cảnh báo riêng.

### Timestamp cần cùng chuẩn

- Log nên có timestamp UTC kèm timezone rõ ràng.
- Bảng metadata của Spring Batch có thể dùng kiểu SQL timestamp không mang timezone; cách diễn giải phụ thuộc cấu hình JDBC/database.
- Không suy luận thứ tự tuyệt đối chỉ từ hai timestamp khi các máy có đồng hồ lệch nhau.
- Với tracking đáng tin cậy, kết hợp execution ID, trạng thái và thời điểm cập nhật; timestamp là dữ kiện bổ sung, không phải khóa nối chính.

## 8. `BatchStatus`, `ExitStatus` và log kết quả

`JobExecution.getStatus()` trả về `BatchStatus`; `getExitStatus()` trả về `ExitStatus` chứa `exitCode` và `exitDescription`.

Ví dụ:

```text
Metadata:
  STATUS    = COMPLETED
  EXIT_CODE = COMPLETED_WITH_WARNINGS

Log:
  batchStatus=COMPLETED
  exitCode=COMPLETED_WITH_WARNINGS
```

Đây có thể là kết quả **hoàn toàn hợp lệ** nếu ứng dụng dùng exit code tùy chỉnh để thể hiện cảnh báo nghiệp vụ. Không nên báo sai khác chỉ vì exit code không bằng chuỗi `COMPLETED` trong khi `BatchStatus` là `COMPLETED`.

Quy tắc đề xuất:

| Trường | Cách so sánh |
| --- | --- |
| `BatchStatus` | So sánh enum/status code của cùng execution tại trạng thái cuối. |
| `ExitStatus.getExitCode()` | So sánh chuỗi, bao gồm các mã tùy chỉnh. |
| `ExitStatus.getExitDescription()` | Thường dùng để điều tra, không nhất thiết so sánh nguyên văn vì có thể chứa nội dung biến đổi hoặc nhạy cảm. |
| `failureCount` trong log | Có thể do listener tính từ ngoại lệ; không mặc định tương ứng với một cột số lỗi trong metadata. |
| `durationMs` | So sánh theo ngưỡng hợp lý nếu timestamp có đủ độ chính xác, không đòi bằng tuyệt đối trong mọi triển khai. |

Với `StepExecution`, `STATUS` và `EXIT_CODE` cũng cần được phân biệt. Một Step `FAILED` có thể dẫn đến Job `COMPLETED` nếu flow cố ý bắt lỗi theo cấu hình transition. Do đó, không kết luận Job phải `FAILED` chỉ vì tìm được một Step thất bại.

## 9. So sánh bộ đếm Step và dữ liệu đầu ra

Các bộ đếm metadata phổ biến:

| Trường | Ý nghĩa |
| --- | --- |
| `READ_COUNT` | Số item đọc được theo cơ chế của Step. |
| `WRITE_COUNT` | Số item đã ghi theo thống kê của Step. |
| `FILTER_COUNT` | Số item bị processor lọc. |
| `SKIP_COUNT` | Tổng số item bị skip. |
| `READ_SKIP_COUNT`, `PROCESS_SKIP_COUNT`, `WRITE_SKIP_COUNT` | Skip được phân theo giai đoạn. |
| `COMMIT_COUNT`, `ROLLBACK_COUNT` | Thống kê commit/rollback của Step. |

Ví dụ Step đọc 100 bản ghi, filter 5 và skip 3 bản ghi lỗi, ghi thành công 92:

```text
Log:
  event=batch.step.finished
  jobExecutionId=7001 stepExecutionId=9101
  readCount=100 writeCount=92 filterCount=5 skipCount=3

Metadata:
  JOB_EXECUTION_ID=7001 STEP_EXECUTION_ID=9101
  READ_COUNT=100 WRITE_COUNT=92 FILTER_COUNT=5 SKIP_COUNT=3
```

Các số ở đây là fixture minh họa. Cách thống kê filter/skip cụ thể phụ thuộc cấu hình reader, processor, writer và retry/rollback; không lập quy tắc chung `readCount = writeCount + filterCount + skipCount` cho mọi Job.

### Chú ý khi so sánh

- Log lúc Step **đang chạy** có thể chứa bộ đếm tạm thời, khác bộ đếm cuối cùng trong metadata.
- Một Step retry nhiều lần hoặc rollback có thể phát ra log xử lý item nhiều lần, nhưng bộ đếm cuối của Step không phải phép đếm dòng log.
- Nếu log phát từ `ItemProcessor`/`ItemWriter`, số dòng log có thể chịu tác động của concurrency, retry, sampling và async appender.
- Với multi-threaded Step, thứ tự dòng log không bảo đảm tương ứng với thứ tự item.
- Nếu Step được partition, cần nối mỗi `StepExecution`/partition đúng ID và chỉ tổng hợp khi hiểu rõ mô hình partition của Job.

**`writeCount` không thay thế kiểm tra dữ liệu đích.** Đối với Job ghi ra API hoặc message broker không nằm trong transaction của Spring Batch, cần kiểm tra kết quả bên ngoài với business key để xác nhận không mất/trùng dữ liệu.

## 10. Restart: một JobInstance, nhiều JobExecution

Đây là tình huống đối chiếu đặc biệt quan trọng.

```text
Log:
  jobInstanceId=51 jobExecutionId=7001 batchStatus=FAILED
  jobInstanceId=51 jobExecutionId=7002 batchStatus=COMPLETED

Metadata:
  BATCH_JOB_INSTANCE: JOB_INSTANCE_ID=51
  BATCH_JOB_EXECUTION:
    7001 -> FAILED
    7002 -> COMPLETED
```

Cả hai lần chạy thuộc một đơn vị công việc logic. Nếu dashboard chỉ hiển thị “JobInstance #51 cuối cùng đã hoàn thành”, nó có thể bỏ qua lần thất bại trước đó. Nếu dashboard chỉ đếm `FAILED` trên tất cả JobExecution, nó có thể hiển thị một lỗi lịch sử dù lần restart đã giải quyết xong.

Vì vậy, cần phân biệt hai cách hỏi:

- **Theo execution:** “Lần chạy `7001` đã thất bại vì gì?” → lọc `jobExecutionId=7001`.
- **Theo instance:** “Đơn vị công việc `51` đã được xử lý xong chưa, sau bao nhiêu lần thử?” → nhóm các JobExecution của instance `51`.

Trong lần restart, Step đã hoàn thành trước đó có thể được bỏ qua theo cấu hình. Không giả định mọi StepExecution của lần đầu có một bản sao trong lần restart.

### Không cộng số liệu từ các lần chạy một cách máy móc

Nếu lần đầu đọc 80 item rồi lỗi, lần restart đọc tiếp 20 item, việc cộng `READ_COUNT` có thể phản ánh tổng số lần đọc; nhưng với rollback, retry, restart không đúng checkpoint hoặc item xử lý lại, tổng này không chắc bằng số bản ghi **duy nhất** trong hệ thống đích.

Khi báo cáo kết quả nghiệp vụ trên cả JobInstance, sử dụng định danh bản ghi nghiệp vụ và trạng thái output thực tế. Metadata StepExecution cung cấp dấu vết cần thiết để giải thích, không tự cung cấp số lượng unique entities.

## 11. Các tình huống sai khác thường gặp

| Tình huống quan sát | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Log `finished COMPLETED`, metadata vẫn `STARTED` ngay sau đó | Bản cập nhật cuối chưa commit hoặc đọc replica trễ | Chờ có timeout, đọc từ repository đúng nguồn, kiểm tra thời điểm cập nhật. |
| Metadata `COMPLETED`, không thấy log `finished` | Log collector mất event, logger bị tắt, async appender chưa flush, listener chưa được gắn | Kiểm tra cấu hình listener/appender, lọc đúng ID và khoảng thời gian. |
| Có log `launch.requested` nhưng không có execution | Yêu cầu bị từ chối trước khi tạo JobExecution hoặc lỗi repository | Tìm `launch.rejected` theo request ID và loại exception. |
| Cùng `jobName` có nhiều `jobExecutionId` | Các JobInstance khác nhau hoặc Job được restart | Đối chiếu từng ID, nhóm theo `jobInstanceId` khi cần. |
| Log nói `FAILED` nhưng metadata hiện `COMPLETED` | Log thuộc execution cũ, bước retry/restart sau đã thành công, hoặc log chụp trạng thái trung gian | Kiểm tra execution ID và timestamp. |
| Log Step có 100 lượt xử lý, `READ_COUNT` thấp hơn | Retry, rollback, log lặp hoặc đếm sự kiện ở tầng khác | So sánh `stepExecutionId` và thời điểm; xem retry/skip. |
| Metadata `STARTED` rất lâu, không có log mới | Job treo, process chết, worker mất kết nối hoặc logging bị lỗi | Xác minh process/worker, lock, JobRepository, checkpoint trước khi restart. |
| Không tìm thấy `jobExecutionId` trong database | Sai environment/repository, metadata bị cleanup/retention hoặc ID bị log sai | Xác minh datasource/prefix, chính sách xóa và trường log. |
| `BatchStatus` khớp nhưng exit code khác | Exit code tùy chỉnh, log sai thời điểm hoặc mapping bị lỗi | So sánh riêng `ExitStatus`, xem flow và listener. |
| Nhiều `batch.job.finished` cho một execution | Nhiều listener/log pipeline phát lặp hoặc bộ thu ingest at-least-once | Xem event ID/source, dùng dedup theo khóa sự kiện. |

**Không tự động sửa metadata cho khớp log.** Dữ liệu Batch là thành phần quản lý restart; việc cập nhật trạng thái bằng SQL tùy tiện có thể phá vỡ checkpoint hoặc lịch sử audit.

## 12. Điều tra tình huống JVM chết giữa chừng

Khi JVM bị kill hoặc máy chủ mất nguồn, callback listener có thể không chạy. Trong khi đó, repository có thể vẫn lưu:

```text
JOB_EXECUTION_ID = 7008
STATUS = STARTED
START_TIME = 2026-11-16 02:00:00
END_TIME = NULL
LAST_UPDATED = 2026-11-16 02:03:12
```

Nếu log dừng ở `02:03`, điều này chỉ cho thấy **không có thêm log được quan sát**. Nó chưa chứng minh process đã chết; log collector có thể đang lỗi hoặc Job đang block ở thao tác I/O.

Quy trình xác minh:

1. Xác định environment, node/pod, process ID và batch execution ID của bản ghi.
2. Kiểm tra tiến trình/worker còn sống, có thread bị block, connection pool cạn hay đang xử lý chunk dài không.
3. Kiểm tra metadata cuối cùng của JobExecution/StepExecution và trạng thái execution context.
4. Đối chiếu dữ liệu nghiệp vụ đã commit để đánh giá khả năng chạy lại.
5. Chỉ sau khi xác nhận execution cũ không còn hoạt động, thực hiện quy trình recovery/restart theo khả năng restart của Job.
6. Ghi nhận sự kiện sự cố và execution ID đã xử lý.

Không nên kết luận `FAILED` chỉ vì `END_TIME IS NULL`. Trong Spring Batch, một process chết đột ngột có thể để metadata `STARTED`; việc chuyển trạng thái phục vụ restart phải tuân thủ chính sách vận hành.

## 13. Ví dụ dịch vụ đối chiếu bằng `JobExplorer`

Phần này xây dựng một hàm nhỏ so sánh một sự kiện **job finished** đã được parse từ log với snapshot trong `JobRepository`. Ví dụ dùng Java 17 và API Spring Batch 5.x; những lớp Java `record` và `enum` là cấu trúc tự định nghĩa trong ứng dụng.

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;

public final class BatchLogReconciler {

    private final JobExplorer explorer;

    public BatchLogReconciler(JobExplorer explorer) {
        this.explorer = explorer;
    }

    public ReconciliationResult compare(FinishedJobLog event) {
        JobExecution execution =
                explorer.getJobExecution(event.jobExecutionId());

        if (execution == null) {
            return new ReconciliationResult(
                    Outcome.MISSING_METADATA,
                    "Execution ID is absent from this repository"
            );
        }

        String actualName =
                execution.getJobInstance().getJobName();
        Long actualInstanceId =
                execution.getJobInstance().getInstanceId();

        if (!actualName.equals(event.jobName())
                || !actualInstanceId.equals(event.jobInstanceId())) {
            return new ReconciliationResult(
                    Outcome.MISMATCH,
                    "Job identity differs"
            );
        }

        BatchStatus status = execution.getStatus();

        if (status == BatchStatus.STARTING
                || status == BatchStatus.STARTED
                || status == BatchStatus.STOPPING) {
            return new ReconciliationResult(
                    Outcome.PENDING,
                    "Job metadata has not reached a terminal state"
            );
        }

        String actualExitCode =
                execution.getExitStatus().getExitCode();

        boolean sameStatus =
                status.name().equals(event.batchStatus());
        boolean sameExitCode =
                actualExitCode.equals(event.exitCode());

        if (sameStatus && sameExitCode) {
            return new ReconciliationResult(
                    Outcome.MATCHED,
                    "Stored terminal status matches the log"
            );
        }

        return new ReconciliationResult(
                Outcome.MISMATCH,
                "Terminal status or exit code differs"
        );
    }

    public record FinishedJobLog(
            String jobName,
            Long jobInstanceId,
            Long jobExecutionId,
            String batchStatus,
            String exitCode) {
    }

    public record ReconciliationResult(
            Outcome outcome,
            String reason) {
    }

    public enum Outcome {
        MATCHED,
        PENDING,
        MISMATCH,
        MISSING_METADATA
    }
}
```

Hàm này minh họa **so sánh một snapshot**, chưa bao gồm cơ chế retry, giới hạn thời gian, nhận diện repository, phân loại `ABANDONED`, dedup log hay chính sách giữ dữ liệu. Trong production, lớp điều phối phía ngoài sẽ thực hiện:

- Chỉ truyền event `batch.job.finished` có schema hợp lệ và đúng environment.
- Đợi một khoảng hội tụ có giới hạn nếu kết quả `PENDING`.
- Phân loại missing metadata theo retention, repository và trạng thái launch.
- Ghi nhận lý do mismatch, thời điểm quan sát và chi tiết chênh lệch.
- Tránh dùng `jobExecutionId` làm metric tag vì mỗi execution tạo một giá trị mới.

Đây là đối chiếu metadata, **không tự động kết luận job đã thực hiện đúng nghiệp vụ**.

### Tại sao không so sánh timestamp bằng toán tử bằng?

Log thường có độ chính xác millisecond/nanosecond, trong khi cột timestamp database có thể làm tròn theo driver. Hai thời điểm được ghi ở hai lớp khác nhau. Nếu cần kiểm tra trật tự hoặc thời lượng, nên định nghĩa biên độ hợp lệ và phân biệt nguồn thời gian, thay vì yêu cầu `log.timestamp == metadata.END_TIME` tuyệt đối.

## 14. Tạo test chứng minh log và metadata khớp nhau

Một integration test có thể chạy Job thật, lấy `JobExecution`, rồi xác nhận log chứa cùng ID và status với metadata đọc lại từ `JobExplorer`.

Ví dụ dưới đây dùng **Spring Batch 5.x**, **JUnit Jupiter**, **Spring Boot Test** và **AssertJ**. Giả định ứng dụng có Job bean `importInvoicesJob`, listener phát sự kiện `batch.job.finished` với ID và trạng thái, cùng fixture đủ để Job chạy thành công:

```java
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ExtendWith(OutputCaptureExtension.class)
class BatchMetadataLogReconciliationIT {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobExplorer jobExplorer;

    @Autowired
    @Qualifier("importInvoicesJob")
    private Job importInvoicesJob;

    @Test
    void finishedLogShouldMatchStoredExecution(CapturedOutput output)
            throws Exception {
        jobLauncherTestUtils.setJob(importInvoicesJob);

        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16", true)
                .addString("testRunId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution launched =
                jobLauncherTestUtils.launchJob(parameters);

        assertThat(launched.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        JobExecution stored =
                jobExplorer.getJobExecution(launched.getId());

        assertThat(stored).isNotNull();
        assertThat(stored.getId()).isEqualTo(launched.getId());
        assertThat(stored.getJobInstance().getInstanceId())
                .isEqualTo(launched.getJobInstance().getInstanceId());
        assertThat(stored.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);
        assertThat(stored.getExitStatus().getExitCode())
                .isEqualTo("COMPLETED");

        assertThat(output.getOut())
                .contains("batch.job.finished")
                .contains("jobExecutionId=" + stored.getId())
                .contains("jobInstanceId="
                        + stored.getJobInstance().getInstanceId())
                .contains("batchStatus=" + stored.getStatus().name())
                .contains("exitCode="
                        + stored.getExitStatus().getExitCode());
    }
}
```

Điều kiện để bài test có ý nghĩa:

1. `importInvoicesJob` có listener ghi những trường dùng trong assertion.
2. Log được xuất qua appender mà `OutputCaptureExtension` bắt được.
3. Launcher trong test chạy **đồng bộ**. Nếu chạy async, cần chờ Job đạt trạng thái cuối và flush log trước khi assert.
4. Metadata và dữ liệu nghiệp vụ test được cô lập; `testRunId` là identifying parameter ở đây để mỗi test độc lập có instance riêng.
5. Dữ liệu fixture hợp lệ để Job thật sự `COMPLETED`; đoạn test chỉ minh họa đối chiếu, không tạo fixture cho ứng dụng cụ thể.

Không nên assert nguyên cả dòng log chứa timestamp, thread name, vị trí code hoặc duration. Những chi tiết đó không phải hợp đồng ổn định của cơ chế đối chiếu.

### Test trường hợp có restart

Thêm một test khác cố ý làm Job `FAILED` lần đầu, sửa điều kiện lỗi, rồi restart bằng **cùng identifying parameters**. Assert:

- `jobInstanceId` của hai lần chạy bằng nhau.
- `jobExecutionId` khác nhau.
- Log `finished` có hai sự kiện gắn với hai execution.
- Metadata có trạng thái riêng cho lần thất bại và lần thành công.
- Dữ liệu đích không bị ghi trùng sau restart.

Không dọn metadata ở giữa hai lần chạy trong bài test restart. Chỉ dọn sau khi mọi phép assert hoàn tất.

## 15. Theo dõi Step hoặc Job bất đồng bộ

Nếu Job chạy trên `TaskExecutor` bất đồng bộ, `JobLauncher.run(...)` có thể trả về trước khi Job hoàn thành. Trong khoảng thời gian đó:

```text
T0  Launcher trả về executionId=7001 status=STARTING
T1  Worker thực thi Step; metadata status=STARTED
T2  Step listener ghi log step.finished
T3  Repository lưu StepExecution
T4  Job listener ghi log job.finished
T5  Repository lưu JobExecution terminal status
```

Đây là timeline khái niệm; thứ tự commit và log phát sinh cụ thể phụ thuộc triển khai. Điểm quan trọng là **không so sánh trạng thái ban đầu của launcher với log kết thúc**.

Một cơ chế quan sát hợp lý:

```java
JobExecution snapshot = jobExplorer.getJobExecution(executionId);
if (snapshot != null) {
    BatchStatus status = snapshot.getStatus();

    if (status == BatchStatus.COMPLETED
            || status == BatchStatus.FAILED
            || status == BatchStatus.STOPPED) {
        // Ghi nhận snapshot trạng thái cuối để đối chiếu.
    } else {
        // Chờ/retry theo timeout đã cấu hình.
    }
}
```

Nếu cần kiểm tra Job hoàn thành trong integration test async, sử dụng polling có timeout, ví dụ Awaitility hoặc `Future.get(timeout, unit)` khi test kiểm soát worker. Khi polling repository, nên thực hiện một truy vấn mới cho mỗi lần kiểm tra để nhận dữ liệu đã lưu.

Với Step đa luồng hoặc partitioned Step, MDC trong logger có thể không tự truyền sang worker thread. Nên đưa `jobExecutionId`/`stepExecutionId` trực tiếp vào log hoặc cấu hình truyền context rõ ràng; tránh nối log dựa trên tên thread.

## 16. Log không có metadata và metadata không có log

### 16.1. Log có event nhưng metadata vắng mặt

Các nguyên nhân:

- Event `launch.requested` hoặc `launch.rejected` phát ra trước khi tạo `JobExecution`.
- Truy vấn nhầm datasource hoặc sai `tablePrefix`.
- Metadata đã được dọn bởi test, retention job hoặc thao tác bảo trì.
- Hệ thống logging tập trung nhiều environment với ID trùng.
- Một transaction tạo execution đã thất bại hoặc rollback.
- Trường ID trong log bị ghi sai hoặc bị biến đổi khi parse.

Các bước nên làm: kiểm tra event type, environment, JobRepository configuration, khoảng thời gian, chính sách cleanup và sự tồn tại của JobInstance.

### 16.2. Metadata có execution nhưng không có log

Các nguyên nhân:

- Listener logging chưa được đăng ký vào Job/Step.
- Logging level hoặc appender lọc mất event.
- JVM chết trước khi callback được gọi.
- Async appender chưa flush khi process bị kill.
- Collector bị mất kết nối, quá tải hoặc thay đổi retention.
- Bộ lọc log tìm nhầm thời gian, index hoặc field.
- Batch metadata được tạo hợp lệ nhưng tác vụ chưa đi vào pha phát log mong đợi.

Không nên tự động quy kết Job thất bại khi thiếu dòng log `finished`. Đọc metadata, trạng thái worker và output nghiệp vụ để hiểu tình trạng thật.

### 16.3. Nếu cần audit bền vững tuyệt đối

Log thông thường là tín hiệu quan sát, không bảo đảm tính giao dịch nguyên tử với metadata hoặc kết quả nghiệp vụ. Nếu yêu cầu kiểm toán nghiêm ngặt là **mỗi sự kiện kinh doanh bắt buộc phải được lưu** và phát ra một cách đáng tin cậy, cần thiết kế thêm bảng audit hoặc transactional outbox trong **cùng phạm vi transaction phù hợp** với thay đổi nghiệp vụ, sau đó chuyển sự kiện ra hệ thống ngoài bằng worker có retry/idempotency.

Ngay cả outbox cũng cần thiết kế dedup và xử lý lỗi; nó không biến metadata Spring Batch thành bản sao hoàn chỉnh của log. Nhu cầu audit phải được xác định ở tầng nghiệp vụ thay vì suy luận từ sự xuất hiện của một dòng log.

## 17. Quy tắc vận hành để tránh cảnh báo nhiễu

Một hệ thống đối chiếu tự động nên có chính sách rõ ràng:

| Quy tắc | Lý do |
| --- | --- |
| Nối theo `environment/repositoryAlias + jobExecutionId` | Tránh ghép nhầm execution ID từ nhiều repository độc lập. |
| Chỉ so sánh terminal event với terminal metadata | Tránh xem chuyển trạng thái hợp lệ là sai khác. |
| Có khoảng hội tụ với timeout | Cho phép log và database cập nhật khác thời điểm. |
| Phân biệt `launch.rejected` khỏi JobExecution `FAILED` | Lỗi khởi chạy có thể không tạo execution mới. |
| Phân biệt JobInstance và JobExecution | Không gộp mất lịch sử restart. |
| Giữ idempotent khi xử lý event log lặp | Log pipeline có thể gửi trùng cùng event. |
| Ghi nhận nguyên nhân missing metadata | Có thể do retention, cleanup hoặc sai datasource. |
| Giới hạn trường nhạy cảm và cardinality | Bảo vệ dữ liệu và khả năng vận hành hệ thống monitoring. |

Nếu hệ thống lưu sự kiện `batch.job.finished` vào message queue hoặc log pipeline cung cấp at-least-once delivery, một event có thể được nhận lại nhiều lần. Dùng khóa dedup như `environment + jobExecutionId + eventType` cùng một event ID nếu có. Với Step, thêm `stepExecutionId`. Không nên tăng bộ đếm “Job hoàn tất” mỗi lần cùng event được ingest lại.

Không dùng `jobExecutionId` làm tag metrics có cardinality lớn; thay vào đó dùng `jobName`, trạng thái và một số nhãn giới hạn. Lưu execution ID trong log hoặc hệ thống truy vấn chi tiết.

## 18. Bài tập thực hành

Xây dựng một Job `syncInventoryJob` xử lý dữ liệu tồn kho vào cuối mỗi giờ. Job có hai Step: `readStockStep` và `publishStockStep`. Thiết lập log có cấu trúc và một màn hình đối chiếu đọc metadata từ `JobExplorer`.

### Kịch bản A: Job hoàn thành

1. Cho Job xử lý 50 bản ghi tồn kho hợp lệ.
2. Ghi log `launch.requested`, `job.started`, `step.finished` và `job.finished` với các ID phù hợp.
3. Tra `BATCH_JOB_EXECUTION` theo `jobExecutionId` lấy từ log.
4. Tra `BATCH_STEP_EXECUTION`, đối chiếu `stepExecutionId`, trạng thái và số lượng item.
5. Kiểm tra dữ liệu đích có đúng 50 bản ghi hợp lệ theo business key.

### Kịch bản B: Job lỗi rồi restart

1. Tạo lỗi có kiểm soát khiến `publishStockStep` thất bại.
2. Ghi lại `jobInstanceId` và `jobExecutionId` của lần lỗi.
3. Khắc phục điều kiện lỗi rồi restart cùng identifying parameters.
4. Xác nhận hai `jobExecutionId` khác nhau nhưng cùng `jobInstanceId`.
5. Xem log theo instance để thấy cả lịch sử; xem theo execution để phân biệt lần lỗi với lần hoàn thành.
6. Kiểm tra dữ liệu đích không bị phát lại trùng.

### Kịch bản C: Log chậm hoặc vắng mặt

1. Tạo Job test có latch để kiểm soát thời điểm kết thúc.
2. Cho hệ thống đối chiếu đọc metadata khi Job chưa terminal: kết quả phải là `pending`, chưa báo mismatch.
3. Mở latch và chờ metadata cập nhật cuối cùng; đối chiếu lại thành `matched`.
4. Giả lập thiếu event log `finished`; hệ thống cần đánh dấu “thiếu log” sau timeout, đồng thời vẫn hiển thị trạng thái metadata thực tế.
5. Tạo event `launch.rejected` không có `jobExecutionId` mới; xác nhận hệ thống không cố truy vấn một execution không tồn tại.

Các câu hỏi tự kiểm tra:

- Nếu JobInstance có hai JobExecution, vì sao không thể dùng `jobInstanceId` một mình để so sánh log trạng thái cuối?
- Nếu `BATCH_JOB_EXECUTION.STATUS=COMPLETED` nhưng không thấy log `job.finished`, những nguyên nhân nào không liên quan đến lỗi nghiệp vụ?
- Nếu Step đã đọc 100 item nhưng log processor có 120 dòng, điều đó luôn có nghĩa metadata sai không?
- Nếu log `job.finished` đến trước commit metadata, cần phân loại kết quả tạm thời như thế nào?
- Nếu hai môi trường đều có `jobExecutionId=7001`, hệ thống log tập trung phải dùng thêm khóa nào?

## Tài liệu tham khảo

- [Spring Batch Reference – Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html): quan hệ giữa Job, JobInstance, JobExecution và StepExecution.
- [Spring Batch Reference – Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html): các bảng và cột metadata phục vụ đối chiếu.
- [Spring Batch Reference – Configuring a JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html): cách lưu thông tin thực thi.
- [Spring Batch Reference – JobExplorer](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): truy vấn lịch sử execution và JobInstance.
- [Spring Batch Reference – Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): quan sát Job/Step qua những tín hiệu ngoài log.
- [Spring Batch Reference – Testing](https://docs.spring.io/spring-batch/reference/testing.html): tạo kiểm thử tích hợp Job và kiểm tra kết quả.

