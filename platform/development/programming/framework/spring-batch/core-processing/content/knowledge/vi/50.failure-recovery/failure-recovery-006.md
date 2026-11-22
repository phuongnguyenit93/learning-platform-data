# Process bị kill trong Spring Batch: nhận diện sự cố và phục hồi an toàn

## 1. Bối cảnh: batch job đang chạy thì process biến mất

Giả sử job `dailyOrderImportJob` đang nhập 2 triệu đơn hàng. Nó đã xử lý được khoảng 1,2 triệu bản ghi thì JVM bị hệ điều hành hoặc nền tảng triển khai dừng đột ngột. Khi ứng dụng được khởi động lại, câu hỏi không chỉ là **chạy job lần nữa**: cần xác định những dữ liệu nào đã commit, checkpoint nào còn được lưu, metadata nào chưa kịp cập nhật và lần chạy cũ có thật sự chấm dứt hay không.

Trong Spring Batch, *process bị kill* là tình huống khác với việc một step ném exception và kết thúc có kiểm soát. Một lỗi thông thường đi qua cơ chế xử lý exception của framework, cho phép nó cập nhật `BatchStatus.FAILED` vào `JobRepository`. Khi JVM/process chết trước khi thực hiện cleanup, repository có thể vẫn ghi nhận job là `STARTED` dù không còn chương trình nào đang chạy.

Các nguyên nhân thường gặp:

- `kill -9 <pid>` trên Linux hoặc lệnh dừng cưỡng bức tương đương.
- Container nhận `SIGKILL`, bị OOM kill, hoặc bị xóa sau khi hết thời gian graceful termination.
- Host/máy ảo bị mất điện, kernel panic, node bị lỗi.
- JVM crash, runtime bị chấm dứt mà không chạy được shutdown hooks.
- Hệ thống điều phối tự restart pod/process do liveness probe thất bại, vượt memory limit hoặc chính sách triển khai.

Mục tiêu *failure recovery* trong chương này là: **khôi phục khả năng chạy lại mà không giả định dữ liệu đã commit hay metadata đã nhất quán, đồng thời tránh chạy trùng một công việc**.

```text
JobExecution #5100: STARTED
    |
    +-- Step A: COMPLETED
    |
    +-- Step B: STARTED
            |
            +-- chunk 1...N đã commit
            +-- chunk N+1 đang xử lý
                    |
                 SIGKILL
                    X

Process mới khởi động
    |
    +-- JobRepository vẫn có thể báo STARTED
    +-- Step B có checkpoint đến lần commit gần nhất
    +-- Cần xác minh process cũ đã chết và quyết định phục hồi
    +-- Sau đó mới restart đúng JobInstance
```

## 2. Phân biệt dừng mềm và kill cưỡng bức

| Tình huống | Điều xảy ra | Metadata mong đợi | Có thể restart ngay? |
|---|---|---|---|
| Step ném exception và được framework bắt | Spring Batch kết thúc luồng lỗi, dọn tài nguyên, cập nhật repository | Thường `FAILED` | Có thể, nếu job/step restartable và dữ liệu hợp lệ. |
| `JobOperator.stop(...)` khi process còn sống | Yêu cầu dừng **có hợp tác**, framework hoàn thành điểm dừng phù hợp | Thường chuyển qua `STOPPING` rồi `STOPPED` | Sau khi thực sự `STOPPED`, nếu job cho phép. |
| `SIGTERM` và shutdown có kiểm soát | Có cơ hội chạy hook và đóng Spring context | Tùy phiên bản và cấu hình; không tự bảo đảm `STOPPED` | Chỉ khi trạng thái repository và checkpoint cho phép. |
| `SIGKILL` / OOM kill / crash | Không có cơ hội chạy `finally`, callback kết thúc, hook | Có thể kẹt `STARTED`/`STARTING`/`STOPPING` | Không, phải xác minh và phục hồi metadata trước. |
| Máy vẫn chạy nhưng một step block rất lâu | Process và job có thể đang thực sự hoạt động | Có thể vẫn `STARTED` | Không được tự coi là job chết. |

`SIGTERM` là tín hiệu yêu cầu process kết thúc và thường cho phép cleanup; `SIGKILL` buộc kernel dừng process và không thể được JVM bắt hoặc trì hoãn. Tuy nhiên, một ứng dụng nhận `SIGTERM` vẫn có thể bị ép kết thúc trước khi framework ghi xong trạng thái, đặc biệt khi đang block ở I/O hoặc xử lý một chunk lâu.

**`JobOperator.stop` không tương đương lệnh kill của OS.** Nó là yêu cầu dừng batch có kiểm soát. Nếu mã nghiệp vụ đang ở trong vòng lặp không trả quyền điều khiển hoặc đợi một request không có timeout, dừng có thể bị trì hoãn. Không suy diễn từ việc gọi thành công `stop(...)` rằng repository đã chuyển sang `STOPPED`.

## 3. Trạng thái nào tồn tại trong `JobRepository` sau crash?

Với JDBC `JobRepository`, Spring Batch lưu metadata qua các bảng `BATCH_*`. Những bảng cần xem khi điều tra gồm:

| Bảng | Dữ liệu liên quan đến phục hồi |
|---|---|
| `BATCH_JOB_INSTANCE` | Tên job, định danh instance dựa vào identifying parameters. |
| `BATCH_JOB_EXECUTION` | Lần thực thi, `STATUS`, `EXIT_CODE`, thời điểm bắt đầu/kết thúc, `LAST_UPDATED`. |
| `BATCH_JOB_EXECUTION_PARAMS` | Các `JobParameters` đã sử dụng khi launch. |
| `BATCH_JOB_EXECUTION_CONTEXT` | `ExecutionContext` cấp job. |
| `BATCH_STEP_EXECUTION` | Tình trạng từng step, read/write/skip/commit/rollback counts. |
| `BATCH_STEP_EXECUTION_CONTEXT` | Checkpoint và trạng thái restart cấp step. |

Một ví dụ minh họa:

```text
BATCH_JOB_EXECUTION
JOB_EXECUTION_ID  STATUS   EXIT_CODE  END_TIME
5100              STARTED  UNKNOWN    NULL

BATCH_STEP_EXECUTION
STEP_EXECUTION_ID  STEP_NAME       STATUS     READ_COUNT
7100               downloadFiles   COMPLETED  0
7101               importOrders    STARTED    1200000
```

Các giá trị ở trên chỉ để minh họa. **`STATUS=STARTED` trong database không chứng minh process còn sống.** Repository chỉ biết những cập nhật mà ứng dụng đã kịp ghi trước khi chết, và không có cơ chế phổ quát tự nhận biết tín hiệu `SIGKILL` trên mọi node.

### 3.1. Các trạng thái liên quan

| `BatchStatus` | Ý nghĩa vận hành chính |
|---|---|
| `STARTING` | Framework đã tạo lần thực thi nhưng chưa hoàn tất bước chuyển sang xử lý. |
| `STARTED` | Theo metadata, job hoặc step đang hoạt động. Có thể là trạng thái tồn đọng sau crash. |
| `STOPPING` | Đã nhận yêu cầu dừng; chưa chắc đã hoàn tất dừng. |
| `STOPPED` | Đã dừng có kiểm soát, có thể restart nếu cấu hình cho phép. |
| `FAILED` | Lần thực thi thất bại; có thể restart nếu dữ liệu restart hợp lệ. |
| `COMPLETED` | Lần thực thi hoàn thành, instance tương ứng thường không được chạy lại bằng cùng identifying parameters. |
| `ABANDONED` | Đã quyết định từ bỏ execution; không thể restart execution đó theo cơ chế thông thường. |
| `UNKNOWN` | Trạng thái không rõ ràng, cần điều tra trước khi restart. |

`BatchStatus` khác `ExitStatus`: `BatchStatus` thể hiện trạng thái thực thi, còn `ExitStatus` là mã kết thúc có thể được dùng cho transition của job. Khi process chết, cả hai đều có khả năng chưa phản ánh kết quả cuối. Không sửa `EXIT_CODE='COMPLETED'` chỉ để một dashboard hết cảnh báo.

### 3.2. Truy vấn metadata chỉ đọc

Các câu SQL dưới đây minh họa cho schema mặc định của Spring Batch 5.x. Tên bảng/cột có thể khác theo phiên bản hoặc `tablePrefix` tùy chỉnh.

```sql
SELECT
    ji.JOB_NAME,
    ji.JOB_INSTANCE_ID,
    je.JOB_EXECUTION_ID,
    je.STATUS,
    je.EXIT_CODE,
    je.START_TIME,
    je.END_TIME,
    je.LAST_UPDATED
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON je.JOB_INSTANCE_ID = ji.JOB_INSTANCE_ID
WHERE je.STATUS IN ('STARTING', 'STARTED', 'STOPPING')
ORDER BY je.LAST_UPDATED;
```

Truy vấn step của một execution:

```sql
SELECT
    STEP_EXECUTION_ID,
    STEP_NAME,
    STATUS,
    EXIT_CODE,
    READ_COUNT,
    WRITE_COUNT,
    COMMIT_COUNT,
    ROLLBACK_COUNT,
    LAST_UPDATED
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
```

`:jobExecutionId` đại diện cho bind parameter của công cụ truy vấn hoặc JDBC; tùy SQL client có thể dùng `?`. Chỉ dùng ID của execution đã xác định trong môi trường cần điều tra. **Không xem `LAST_UPDATED` lâu không đổi là bằng chứng duy nhất rằng process chết**: một tasklet dài, xử lý block hoặc mất kết nối metadata cũng có thể không cập nhật cột này thường xuyên.

## 4. Tác động tới transaction và dữ liệu nghiệp vụ

### 4.1. Chunk nào được giữ lại?

Trong một chunk-oriented step, Spring Batch thực hiện các thao tác đọc/xử lý/ghi trong ranh giới transaction của chunk. Với cơ sở dữ liệu transactional và transaction manager được cấu hình đúng:

```text
Chunk 1 (1..100)   -> COMMIT
Chunk 2 (101..200) -> COMMIT
Chunk 3 (201..300) -> JVM bị kill trước COMMIT

Kỳ vọng chung:
  - Các thay đổi DB của chunk 1 và 2 còn tồn tại.
  - Các thay đổi DB chưa commit của chunk 3 thường rollback
    khi kết nối/transaction bị đóng hoặc DB phát hiện session chết.
  - Checkpoint gần nhất giúp reader tiếp tục từ vị trí đã lưu.
```

Đây là một mô hình cơ bản, **không phải cam kết mọi loại writer đều exactly-once**. Kết quả còn phụ thuộc transaction, database engine, connection pool, cách reader/writer và `ExecutionContext` được lưu, cũng như thời điểm crash. Nếu writer gửi HTTP, ghi tệp, gọi Kafka hoặc ghi vào một datasource khác không nằm trong cùng transaction, tác dụng phụ đó có thể đã xảy ra dù transaction metadata bị rollback.

### 4.2. Bốn thời điểm kill khác nhau

| Thời điểm kill | Hậu quả có thể xảy ra |
|---|---|
| Trước khi bắt đầu một chunk | Các chunk trước vẫn giữ kết quả đã commit; trạng thái cuối chưa được ghi. |
| Đang đọc/xử lý item trong chunk | Work đang thực hiện bị ngắt; với DB transactional, phần chưa commit thường rollback. |
| Trong lúc commit | Kết quả commit có thể chưa rõ từ góc nhìn ứng dụng; cần kiểm chứng trực tiếp ở DB thay vì đoán. |
| Sau khi side effect ngoài DB hoàn tất, trước khi checkpoint/metadata được ghi | Khi restart, cùng item có thể bị xử lý lại và lặp side effect. |

Một failure recovery đáng tin cậy phải được thiết kế để xử lý được **khoảng không chắc chắn giữa side effect và checkpoint**. Đặc biệt, nếu job gửi email hoặc gọi API thanh toán, không nên dựa vào mỗi `readCount` để quyết định thao tác đó đã được thực hiện hay chưa.

### 4.3. `ExecutionContext` không phải bộ đếm trực tiếp của tiến độ hiện tại

`ItemStream` có các callback `open`, `update` và `close`. Reader/writer có state có thể dùng `ExecutionContext` để khôi phục vị trí. Framework gọi `update(...)` để lưu trạng thái trước commit phù hợp với vòng đời chunk. Khi restart cùng `JobInstance`, trạng thái của step có thể được nạp lại từ lần thực thi trước.

```text
StepExecutionContext đã lưu:
  reader.current.count = 200

Process bị kill lúc đã đọc đến item 240 trong chunk tiếp theo.

Khi restart:
  reader sử dụng checkpoint đã persist,
  không được giả định có thể tiếp tục chính xác từ item 240.
```

Tên key thực tế phụ thuộc implementation reader và tên stream. Một `FlatFileItemReader`, `JdbcCursorItemReader` hay `JdbcPagingItemReader` có yêu cầu restart khác nhau; cần kiểm tra `saveState`, tên instance, sort key ổn định, behavior khi dữ liệu nguồn thay đổi và việc reader được đăng ký như một `ItemStream`.

Checkpoint không đồng nghĩa “đã xử lý chính xác N bản ghi nghiệp vụ”; retry/skip, rollback, filter và side effect bên ngoài có thể làm số item `read`/`write` chênh lệch.

## 5. Vì sao chỉ khởi động lại application chưa đủ?

Khi application chạy lại, Spring Batch không mặc định kiểm tra tất cả `STARTED` cũ rồi tự biến chúng thành `FAILED`. Repository có thể vẫn tin rằng execution trước đó đang chạy. Nếu cùng job name và **identifying `JobParameters`** được yêu cầu lần nữa, kết quả có thể là `JobExecutionAlreadyRunningException` hoặc lỗi restart liên quan trạng thái metadata.

Quan hệ cần nhớ:

```text
JobInstance = jobName + identifying JobParameters

JobInstance #100 (dailyOrdersJob, businessDate=2026-11-16)
    |
    +-- JobExecution #5100 -> STARTED (process đã chết)

Khi gọi lại với cùng businessDate:
    -> Repository phát hiện execution cũ được ghi là running
    -> Không tự tạo lượt restart an toàn
```

Việc thêm `run.id=System.currentTimeMillis()` để “chạy được ngay” thường tạo **JobInstance mới**, bỏ qua tính kế thừa checkpoint của instance trước và làm tăng nguy cơ ghi kết quả trùng. Điều đó chỉ phù hợp khi nghiệp vụ thật sự muốn một đợt xử lý mới, đã có chiến lược idempotency hoặc dọn kết quả trước; không phải cách sửa mặc định cho process bị kill.

## 6. Runbook khi phát hiện process bị kill

Một quy trình phục hồi nên phân biệt **phát hiện**, **xác minh**, **đánh giá dữ liệu**, **ra quyết định** và **khởi chạy lại**.

### Bước 1: Xác minh process cũ đã kết thúc

Thu thập các tín hiệu phù hợp với môi trường:

- Trên host: process/PID, exit code, OOM killer, nhật ký systemd, JVM crash log nếu còn.
- Trên Kubernetes: pod status, container `lastState.terminated.reason`, exit code, sự kiện `OOMKilled`, log của container cũ, node events.
- Với scheduler: job nào được phát lệnh, có bao nhiêu replica/scheduler, lịch chạy tiếp theo là khi nào.
- Với DB: session/transaction/lock còn tồn tại, worker process khác có thể vẫn thực hiện cùng công việc hay không.

Đừng đánh dấu execution là `FAILED` chỉ vì một pod không còn thấy trên dashboard: có thể có replica khác hoặc worker phân tán tiếp tục xử lý. Với partitioning/remote chunking, cần kiểm tra cả worker nodes và hàng đợi thông điệp.

### Bước 2: Khoanh vùng đúng `JobInstance` và `JobExecution`

Ghi lại `jobName`, identifying parameters, `jobInstanceId`, `jobExecutionId`, các step execution IDs và trạng thái hiện lưu. Nên tham chiếu metadata qua `JobExplorer` hoặc SQL chỉ đọc; nếu cần snapshot phục vụ điều tra, thực hiện theo quy trình vận hành và quyền dữ liệu của hệ thống.

Ví dụ với Spring Batch 5.x:

```java
JobExecution execution = jobExplorer.getJobExecution(5100L);

if (execution == null) {
    throw new IllegalArgumentException("Unknown job execution ID");
}

System.out.println("Job: "
        + execution.getJobInstance().getJobName());
System.out.println("Status: " + execution.getStatus());
System.out.println("Instance ID: "
        + execution.getJobInstance().getInstanceId());
```

Đây là ví dụ đọc, giả định một bean `JobExplorer` đã được inject; nó không sửa metadata. Tránh in trực tiếp toàn bộ `JobParameters` và `ExecutionContext` vào log vận hành vì chúng có thể chứa dữ liệu nhạy cảm.

### Bước 3: Đánh giá checkpoint và kết quả đã commit

Đối chiếu ba nguồn thông tin:

1. **Metadata:** `StepExecution`, counts, `ExecutionContext`, phiên bản cấu hình/job khi job bắt đầu.
2. **Dữ liệu nghiệp vụ:** những rows/file/messages đã thật sự được ghi, khóa duy nhất, trạng thái xử lý, bảng đối soát.
3. **Hệ thống bên ngoài:** call API, message đã phát, file đã upload, email đã gửi, transaction ID hoặc idempotency key.

Nếu những tác vụ bên ngoài không có cơ chế deduplication, việc restart có thể tạo side effect trùng. Khi không chắc chắn, cần xác minh bằng dữ liệu đầu ra và thiết kế một hành động khôi phục phù hợp trước khi tiếp tục.

### Bước 4: Chặn việc phát lệnh trùng trong thời gian xử lý sự cố

Nếu scheduler còn hoạt động, một cron trigger khác có thể phát lại cùng công việc trong lúc đang sửa metadata. Trong hệ thống nhiều instance, cần cơ chế điều phối chỉ cho một hành động recovery chạy trên một khóa nghiệp vụ. Có thể tạm dừng lịch theo runbook vận hành hoặc dùng distributed lock/lease/claim table được thiết kế cho hệ thống; đừng suy luận rằng một process chết nghĩa là mọi lock ứng dụng đã tự biến mất.

### Bước 5: Quyết định `FAILED` để restart hay `ABANDONED` để từ bỏ

| Quyết định | Khi nào phù hợp? | Hệ quả |
|---|---|---|
| Phục hồi execution để restart | Process chắc chắn đã chết, checkpoint có thể tin cậy, side effect được xử lý an toàn, job restartable | Cho phép tạo `JobExecution` mới của **cùng JobInstance**. |
| Đánh dấu `ABANDONED` | Lần chạy không thể/không nên tiếp tục theo cơ chế restart hoặc đã chọn phương án xử lý nghiệp vụ khác | Execution bị từ bỏ, không restart qua cơ chế thông thường. |
| Giữ nguyên để tiếp tục điều tra | Chưa xác định trạng thái process, transaction, side effect hoặc dữ liệu chưa nhất quán | Không phát lệnh xử lý mới cho cùng khóa nghiệp vụ. |

**Không nên tự động quyết định chỉ dựa trên tuổi của `LAST_UPDATED`.** Một job xử lý lâu vẫn có thể hoạt động, và chỉ người vận hành/hệ thống có đủ bằng chứng mới được thực hiện hành động thay đổi trạng thái ở repository.

### Bước 6: Restart đúng instance và xác minh sau recovery

Sau khi trạng thái đã được phục hồi theo API/quy trình phù hợp với phiên bản Spring Batch, khởi chạy lại bằng **cùng identifying parameters** và theo dõi `JobExecution` mới. Kiểm tra step nào được skip vì đã hoàn thành, step nào tiếp tục từ checkpoint, và đối chiếu kết quả nghiệp vụ với dữ liệu đã có trước crash.

## 7. Spring Batch 5.x: xử lý execution bị kẹt `STARTED`

Trong Spring Batch 5.2.x, `JobOperator` có `stop(long executionId)`, `restart(long executionId)` và `abandon(long executionId)`, nhưng **chưa có** `recover(JobExecution)` của dòng 6.x.

```java
// Spring Batch 5.x: chỉ thực hiện khi execution đã ở trạng thái
// FAILED hoặc STOPPED và đủ điều kiện restart.
long newExecutionId = jobOperator.restart(failedExecutionId);
```

Nếu execution sau crash vẫn là `STARTED`, chỉ gọi `restart(...)` là chưa đủ. Tài liệu Spring Batch 5.2 yêu cầu người vận hành xác định process thật sự đã chết và thực hiện thay đổi trạng thái thủ công thành `FAILED` khi dữ liệu restart hợp lệ, hoặc `ABANDONED` nếu chọn từ bỏ. Một công cụ quản trị riêng cần xử lý **nhất quán trạng thái job/step, transaction và metadata** thông qua `JobRepository`/cơ chế đã được kiểm soát cho đúng phiên bản.

Không coi một câu SQL như dưới đây là quy trình phục hồi hoàn chỉnh:

```sql
-- Ví dụ thao tác KHÔNG đầy đủ, không dùng làm runbook:
-- UPDATE BATCH_JOB_EXECUTION SET STATUS = 'FAILED'
-- WHERE JOB_EXECUTION_ID = 5100;
```

Chỉ thay một cột có thể để `ExitStatus`, `StepExecution`, `LAST_UPDATED`, version dùng cho optimistic locking hoặc `ExecutionContext` ở trạng thái không nhất quán. Với các môi trường có job quan trọng, hãy xây dựng/duyệt công cụ vận hành đã kiểm tra đúng phiên bản thay vì chạy DML tuỳ ý trong production.

**Phân biệt `abandon` với `restart`:** `jobOperator.abandon(jobExecutionId)` là hành động đánh dấu execution bị từ bỏ, **không làm execution đó restartable**. Nếu mục tiêu là tiếp tục công việc còn dang dở, không dùng `ABANDONED` như một bước tự động trước `restart`. Khi phải xử lý lại từ đầu bằng một instance mới, đó là quyết định nghiệp vụ riêng liên quan đến idempotency và dữ liệu đầu ra.

## 8. Spring Batch 6.x: `JobOperator.recover(...)`

Từ **Spring Batch 6.0**, API bổ sung `JobOperator.recover(JobExecution)` để phục hồi một execution bị kẹt `STARTED` sau shutdown bất thường. Phương thức đánh dấu execution là `FAILED` và đặt cờ `recovered=true` vào execution context để cho phép xử lý restart theo cơ chế mới.

Ví dụ minh họa phần xử lý sau khi **đã xác nhận** process cũ không còn chạy, restart data hợp lệ và việc chạy lại an toàn:

```java
// Ví dụ dùng API Spring Batch 6.x.
// jobExplorer và jobOperator là các bean của Spring Batch.

JobExecution staleExecution = jobExplorer.getJobExecution(5100L);
if (staleExecution == null) {
    throw new IllegalArgumentException("Execution not found");
}

// Đây là thao tác quản trị có tác động, chỉ gọi sau khi điều tra.
JobExecution recovered = jobOperator.recover(staleExecution);
JobExecution restarted = jobOperator.restart(recovered);

System.out.println("Restarted execution ID: " + restarted.getId());
```

Đây không phải đoạn code để chạy tự động khi application startup. Cần đặt nó sau một lớp kiểm soát quyền, xác minh rằng không có process còn chạy và đảm bảo chỉ một người/worker thực hiện recovery cho một execution. Có thể tách hai hành động `recover` và `restart` để người vận hành xác nhận kết quả ở giữa.

Nếu execution đã ở `FAILED`/`STOPPED`, không cần gọi `recover` như bước mặc định; dùng đường restart tương ứng. Nếu metadata `UNKNOWN` hoặc checkpoint không hợp lệ, không ép restart bằng cách đổi trạng thái mà chưa giải quyết nguyên nhân.

### 8.1. Khác biệt API giữa 5.x và 6.x

| Công việc | Spring Batch 5.2.x | Spring Batch 6.x |
|---|---|---|
| Dừng mềm execution | `JobOperator.stop(long)` | `JobOperator.stop(JobExecution)` (overload ID có thể deprecated). |
| Restart execution đã `FAILED`/`STOPPED` | `JobOperator.restart(long)` | `JobOperator.restart(JobExecution)` (overload ID có thể deprecated). |
| Phục hồi execution kẹt `STARTED` sau crash | Quy trình vận hành/quản trị cập nhật metadata có kiểm soát | `JobOperator.recover(JobExecution)` từ 6.0. |
| Bỏ execution không restart | `JobOperator.abandon(long)` | `JobOperator.abandon(JobExecution)` (overload ID có thể deprecated). |
| Shutdown hook dành riêng cho `JobExecution` | Không có `JobExecutionShutdownHook` của 6.x | Có `JobExecutionShutdownHook` từ 6.0. |

Khi sao chép ví dụ code, chú ý package đổi ở Spring Batch 6.x: `JobExecution` nằm trong `org.springframework.batch.core.job`; `JobParameters` dưới `org.springframework.batch.core.job.parameters`. Dòng 5.x vẫn có `org.springframework.batch.core.JobExecution` và `org.springframework.batch.core.JobParameters`.

## 9. Thiết kế job để sống sót qua process kill

### 9.1. Chia công việc thành chunk có kích thước hợp lý

Chunk processing giúp giới hạn số item nằm trong một transaction và tạo điểm lưu tiến độ. Với Spring Batch 5.x:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

`Order` và các bean reader/processor/writer là class ứng dụng. Chunk size 100 chỉ là ví dụ; giá trị hợp lý phụ thuộc độ nặng của mỗi item, transaction, lock, DB round trips và yêu cầu restart. Chunk quá lớn có thể làm nhiều work phải chạy lại sau kill; chunk quá nhỏ tăng overhead commit và cập nhật repository.

### 9.2. Reader/writer có trạng thái cần dùng `ItemStream`

Ví dụ reader đọc từ tệp thường cần nhớ số dòng/vị trí đã đọc. Các implementation `ItemStream` có thể lưu checkpoint trong step `ExecutionContext`. Đảm bảo:

- Reader/writer đã bật lưu trạng thái (`saveState=true` nếu implementation hỗ trợ và đây là điều mong muốn).
- Stream được đăng ký đúng với step; delegate `ItemStream` ẩn trong composite có thể cần `.stream(delegate)`.
- Key checkpoint ổn định giữa các lần chạy và không va chạm khi có nhiều reader/writer trong một step.
- Dữ liệu đầu vào có tính ổn định giữa lần đầu và lần restart; nếu file bị thay đổi/ghi đè, offset cũ có thể không còn đúng.
- Với paging, sort key là duy nhất/ổn định và cách đọc lại không bỏ sót hoặc nhân đôi rows khi dữ liệu bị thay đổi.

`ExecutionContext` giúp tiếp tục gần checkpoint đã lưu, nhưng không tự giải quyết duplicate side effect. Nếu reader đọc thêm nhưng writer chưa commit, replay của phần chưa hoàn tất có thể là hành vi đúng và cần được writer xử lý an toàn.

### 9.3. Phân biệt step đã hoàn thành và step cần chạy lại

Khi restart một job, những step có lần thực thi trước `COMPLETED` thường được bỏ qua, trừ khi cấu hình `.allowStartIfComplete(true)`. Step đang thực hiện dở sẽ được đánh giá theo trạng thái, restartability, start limit và flow.

```java
return new StepBuilder("validateInput", jobRepository)
        .tasklet(validateTasklet, transactionManager)
        .allowStartIfComplete(false)
        .build();
```

Trong ví dụ, `validateTasklet` là bean của ứng dụng. Đây là lựa chọn phổ biến khi việc kiểm tra đầu vào đã hoàn thành có thể bỏ qua. Với step cần luôn chạy lại (ví dụ xác minh file vẫn tồn tại), cân nhắc `allowStartIfComplete(true)` có chủ đích. Nếu đặt `.startLimit(1)`, một step đã được thử có thể không được phép chạy lần tiếp theo; cần đưa start limit vào kịch bản recovery.

### 9.4. Thiết kế idempotent writer

Một writer idempotent có thể nhận cùng input nhiều lần mà không tạo bản ghi hoặc side effect trùng ngoài ý định. Các kỹ thuật thường dùng:

- Unique constraint theo khóa nghiệp vụ (ví dụ `businessDate`, `orderId`) để ngăn insert trùng.
- Upsert/update có điều kiện với trạng thái được kiểm soát; hiểu rõ cú pháp và transaction của database mục tiêu.
- Bảng `processed_event`/`outbox` ghi định danh sự kiện cùng transaction với thay đổi nghiệp vụ.
- Với API ngoài, truyền idempotency key được service đích thực sự hỗ trợ.
- Với file output, ghi vào tên tạm, hoàn tất/flush rồi publish/rename theo quy tắc atomic của filesystem/storage nếu được hỗ trợ, và tránh ghi đè mù.

Ví dụ PostgreSQL (chỉ để minh họa phương pháp chống trùng insert):

```sql
CREATE TABLE imported_order (
    business_date DATE NOT NULL,
    order_id BIGINT NOT NULL,
    amount NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (business_date, order_id)
);

INSERT INTO imported_order (business_date, order_id, amount)
VALUES (:businessDate, :orderId, :amount)
ON CONFLICT (business_date, order_id)
DO NOTHING;
```

`DO NOTHING` phù hợp nếu record đã có được coi là xử lý xong và không cần cập nhật. Nếu cùng khóa nhưng giá trị khác là lỗi nghiệp vụ, **đừng dùng `DO NOTHING` để che giấu sai lệch**; cần so sánh nội dung, version hoặc dùng quy tắc reconciliation rõ ràng.

## 10. Giới hạn của exactly-once khi có side effect bên ngoài

Spring Batch giúp quản lý transaction/checkpoint, nhưng không thể bảo đảm mọi thao tác ngoài database được commit cùng nhau nếu chúng không dùng chung một transaction phối hợp.

Ví dụ step gọi một payment API:

```text
1. Đọc order-25
2. Gửi request charge(order-25) -> phía API đã trừ tiền
3. JVM bị kill trước khi DB ghi processed=true
4. Restart đọc lại order-25
5. Gửi request charge(order-25) lần nữa -> nguy cơ trừ hai lần
```

Để phục hồi đúng, hệ thống cần hợp đồng idempotency với API, ví dụ `paymentRequestId` ổn định và được bên nhận thực thi. Chỉ thêm exception handler hay tăng số lần retry không giải quyết được tình huống yêu cầu bên ngoài **đã thành công nhưng bên gọi không kịp lưu kết quả**.

Mô hình *transactional outbox* thường hữu ích khi cần phát event sau thay đổi DB: cùng transaction ghi trạng thái nghiệp vụ và bản ghi outbox; một worker riêng gửi event, ghi nhận trạng thái gửi, và bên nhận cần hỗ trợ deduplication khi gửi lại. Cơ chế outbox giảm khoảng không chắc chắn giữa DB và message publishing nhưng vẫn cần idempotent consumer; không nên gọi nó là đảm bảo exactly-once tuyệt đối cho mọi hệ thống.

## 11. Phòng tránh kill không mong muốn khi triển khai

### 11.1. Kubernetes: `SIGTERM` và `terminationGracePeriodSeconds`

Kubernetes thường gửi tín hiệu chấm dứt tới container khi pod bị xóa, sau đó có thể dùng `SIGKILL` khi hết thời gian grace period. Ví dụ minh họa một pod/job workload:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: order-import
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 120
      containers:
        - name: batch
          image: example/order-import:1.0
          resources:
            requests:
              memory: 512Mi
            limits:
              memory: 1Gi
```

Các giá trị image/memory/time ở đây chỉ là ví dụ. `terminationGracePeriodSeconds` tạo **cơ hội** để dừng có kiểm soát, không đảm bảo một step xử lý 30 phút sẽ dừng trong 120 giây. Nếu quá thời hạn, container vẫn có thể bị kill. Với Java, phải bảo đảm shutdown hooks, bean lifecycle và cơ chế dừng job thực sự hoạt động với tín hiệu/entrypoint container.

`backoffLimit`/`restartPolicy` điều khiển cơ chế retry ở **cấp Kubernetes**, không tương đương `JobExecution` restart ở **cấp Spring Batch**. Một pod mới có thể khởi tạo cùng tham số trên cùng `JobRepository`, dẫn đến trường hợp `STARTED` tồn đọng. Nếu mỗi pod tạo identifying `run.id` ngẫu nhiên, nguy cơ xử lý trùng còn lớn hơn.

### 11.2. Spring Batch 6.x: shutdown hook cho job execution

Spring Batch 6.0 bổ sung `JobExecutionShutdownHook` hỗ trợ gửi tín hiệu dừng khi JVM thoát theo đường có thể xử lý shutdown:

```java
Thread hook = new JobExecutionShutdownHook(jobExecution, jobOperator);
Runtime.getRuntime().addShutdownHook(hook);
```

`jobExecution` là execution đang được theo dõi và `jobOperator` đã được cấu hình. Đây là ví dụ API 6.x; cần tổ chức đăng ký/hủy hook theo vòng đời launcher thật của ứng dụng. Hook **không thể chạy khi `SIGKILL`, OOM kill cấp kernel hoặc JVM crash không thực thi shutdown sequence**. Trên 5.x, cần thiết kế quy trình dừng phù hợp với hệ thống đang dùng; đừng sao chép class chỉ tồn tại từ 6.0.

### 11.3. `JobOperator.stop(...)` là yêu cầu dừng hợp tác

Với Spring Batch 5.x:

```java
boolean requested = jobOperator.stop(jobExecutionId);
// requested == true: tín hiệu đã được gửi, chưa bảo đảm job đã STOPPED.
```

Framework cần có cơ hội quay về điểm kiểm tra trạng thái để hoàn tất stop. Với code đang gọi API lâu, nên đặt timeout có kiểm soát, xử lý cancellation phù hợp và tránh các vòng lặp vô hạn không kiểm tra interruption. Khi dừng thành công, ghi nhận `STOPPED` cùng checkpoint trước khi cho phép restart.

### 11.4. Scheduling và nhiều replica

Nếu nhiều replica đều có `@Scheduled`, mỗi replica có thể phát lệnh cùng lúc. `JobRepository` có thể giúp từ chối job instance trùng đang chạy nhưng không thay thế hoàn toàn cơ chế điều phối, idempotency và khóa nghiệp vụ. Sau crash, scheduler có thể phát lại khi metadata đang kẹt, hoặc tạo instance mới nếu tham số định danh thay đổi.

Với Kubernetes `CronJob`, các chính sách `concurrencyPolicy: Forbid`/`Replace` kiểm soát các Job được controller nhìn thấy, **không bảo đảm exactly-once ở cấp dữ liệu nghiệp vụ**. Cần kết hợp với `JobRepository` và cơ chế chống xử lý trùng.

## 12. Kiểm thử tình huống process bị kill

### 12.1. Không kill JVM chạy JUnit của toàn dự án

`System.exit(...)`, `Runtime.getRuntime().halt(...)` hoặc kill PID của JVM chứa test runner sẽ chấm dứt cả quá trình test, làm mất báo cáo và khiến suite không thể hoàn tất. Để thử crash thật, hãy chạy batch trong **một process/container riêng** rồi kill **chỉ** process/container test đó.

Một bài test phục hồi thường chia hai cấp:

1. **Integration test thông thường:** gây exception trong processor/writer để framework tự đánh dấu `FAILED`; dùng API restart để kiểm chứng checkpoint và idempotency.
2. **Crash test ở process riêng:** kill cưỡng bức JVM trong lúc job chạy; đọc metadata từ database bền qua restart, thực hiện recovery theo phiên bản Spring Batch và chạy lại.

Cấp 1 kiểm tra logic restart trong trạng thái có kiểm soát. Cấp 2 mới kiểm chứng trường hợp metadata có thể kẹt `STARTED` do process biến mất.

### 12.2. Kịch bản test kill thực tế

Chuẩn bị môi trường test cô lập:

- Một database thử nghiệm có JDBC `JobRepository` và bảng nghiệp vụ, tồn tại qua hai lần khởi động process (không dùng H2 in-memory bị mất khi process chết, trừ khi H2 server nằm ngoài process đó).
- Một job cố định `jobName`/identifying `JobParameters`, reader/writer hỗ trợ restart.
- Dữ liệu đủ lớn hoặc một điểm chặn có kiểm soát giữa các chunk để biết khi nào process đang xử lý.
- Cách quan sát đã có ít nhất một chunk commit qua DB và các row output tương ứng.

Kịch bản gợi ý:

```text
1. Tạo database test sạch và nạp 1.000 records.
2. Launch JVM A với job=importOrders, businessDate=2026-11-16.
3. Chờ thấy một số chunk commit và metadata STARTED.
4. Gửi SIGKILL cho JVM A (môi trường test riêng).
5. Xác nhận JVM A không còn sống, connection cũ đã chấm dứt.
6. Đọc BATCH_JOB_EXECUTION, BATCH_STEP_EXECUTION, context, output rows.
7. Áp dụng recovery phù hợp Spring Batch 5.x hoặc 6.x.
8. Launch JVM B với cùng identifying parameters.
9. Kiểm tra job kết thúc, records đúng, không có duplicates.
10. Đối chiếu số JobExecution và các StepExecution trong cùng JobInstance.
```

Nếu muốn mô phỏng `SIGKILL` trong Linux/container test, có thể dùng `kill -9 <test-pid>` hoặc `docker kill --signal=KILL <test-container>`, **chỉ khi PID/container thuộc môi trường kiểm thử riêng**. Lệnh kill không nằm trong test Java và không được áp dụng với service production. Trong CI, đặt timeout/cleanup riêng để không để lại container hoặc database test nếu quá trình thử thất bại.

### 12.3. Assertion quan trọng sau restart

| Assertion | Điều muốn chứng minh |
|---|---|
| Không còn process cũ | Recovery không chạy song song với một worker đang sống. |
| `JobInstance` giữ nguyên | Restart đúng khóa nghiệp vụ, không tạo instance mới chỉ để vượt trạng thái cũ. |
| `JobExecution` mới được tạo | Lần chạy lại được ghi nhận riêng trong repository. |
| Các step đã `COMPLETED` được skip phù hợp cấu hình | Không lặp side effect của step hoàn thành. |
| Step dở dang nhận được checkpoint hợp lệ | Có thể tiếp tục từ trạng thái đã persist. |
| Output rows/files/events khớp nghiệp vụ | Không bỏ sót, không ghi trùng ngoài quy tắc cho phép. |
| `BatchStatus` cuối cùng đúng | Job thực sự hoàn thành hoặc thất bại có thể chẩn đoán. |

Với lỗi commit không rõ kết quả hoặc side effect ngoài DB, chỉ nhìn `COMPLETED` là chưa đủ; kiểm tra idempotency key, outbox và dữ liệu cuối cùng. Thực hiện crash test nhiều thời điểm (trước/đang/sau commit) sẽ phát hiện các khoảng rủi ro mà happy-path test bỏ qua.

## 13. Observability để phát hiện execution bị treo sau kill

Thông tin hữu ích nên được log/đo trước khi có sự cố:

| Tín hiệu | Mục đích |
|---|---|
| `jobName`, business key đã được phép log | Xác định công việc và kỳ dữ liệu. |
| `jobInstanceId`, `jobExecutionId`, `stepExecutionId` | Tương quan giữa logs, metrics và `JobRepository`. |
| `BatchStatus`, `ExitStatus` | Xem trạng thái lưu lần cuối. |
| `readCount`, `writeCount`, `commitCount`, `rollbackCount` | Ước lượng mức xử lý trong metadata. |
| Thời điểm `LAST_UPDATED` | Gợi ý thời điểm metadata cập nhật gần nhất; không phải bằng chứng process còn sống. |
| Heartbeat ở tầng ứng dụng/scheduler | Phân biệt process thực sự sống với trạng thái repository còn tồn đọng. |
| Pod exit code, OOM events, node status | Phân loại nguyên nhân dừng đột ngột. |
| DB lock/session và external side effects | Đánh giá khả năng chạy lại an toàn. |

Nếu cần cảnh báo stuck execution, có thể kết hợp điều kiện **status đang chạy**, **thời gian vượt SLA**, **heartbeat đã mất** và **không còn process/worker sở hữu execution**. Đừng tự động đổi trạng thái hoặc restart chỉ dựa vào một query như `STATUS='STARTED' AND LAST_UPDATED < NOW() - INTERVAL '10 minutes'`.

Với job chạy nhiều giờ, một step lâu không commit sẽ có khoảng trống metadata lớn; heartbeat riêng ở vùng không ảnh hưởng transaction nghiệp vụ giúp chẩn đoán tốt hơn. Tuy nhiên heartbeat cũng cần vòng đời/ownership rõ ràng để tránh ghi “alive” từ process khác sau khi execution đã kết thúc.

## 14. Những lỗi phổ biến khi phục hồi process bị kill

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Restart báo `JobExecutionAlreadyRunningException` dù process đã chết | `JobExecution` cũ kẹt `STARTED` | Xác minh process/worker chết thật, phục hồi metadata theo API/quy trình của phiên bản. |
| Không thấy `FAILED` sau `kill -9` | JVM không được chạy cleanup/finally | Đây là hành vi có thể xảy ra; kiểm tra repository và phục hồi có kiểm soát. |
| Restart tạo thêm job instance và ghi trùng | Thêm identifying `run.id`/timestamp để vượt lỗi | Dùng cùng identifying business parameters cho restart; thiết kế idempotency. |
| Job được restart nhưng xử lý lại chunk đã gửi API | Side effect ngoài DB không có transaction chung với checkpoint | Dùng idempotency key/outbox và reconciliation theo nghiệp vụ. |
| File reader đọc sai vị trí | Input file thay đổi hoặc `ItemStream`/checkpoint chưa cấu hình đúng | Giữ input bất biến, bật state và kiểm tra reader restart. |
| `JobRestartException` sau sửa metadata | Step status/ExecutionContext không nhất quán, job không restartable hoặc vượt start limit | Phục hồi qua công cụ hỗ trợ, đối chiếu metadata và cấu hình step. |
| `JobRepository` vẫn có lock/session | DB chưa nhận ra connection chết, transaction đang chờ hoặc có process khác | Xác minh session/transaction và chờ/giải quyết theo quy trình DBA trước khi retry. |
| Một step đã `COMPLETED` nhưng vẫn chạy lại | Cấu hình `allowStartIfComplete(true)` hoặc tạo JobInstance khác | Kiểm tra flow, identifying parameters và side effect của step. |
| `abandon` rồi không restart được | `ABANDONED` là từ bỏ, không phải trạng thái phục hồi | Chọn đúng quy trình `FAILED`/`recover` nếu restart là mục tiêu. |
| Job chạy tốt khi lỗi Java nhưng thất bại sau kill | Test thông thường chỉ đi qua exception handler; crash không ghi trạng thái cuối | Thêm crash test ở process riêng với DB bền. |
| Kubernetes tự tạo pod mới nhưng job không tiến triển | Process cũ chết, metadata kẹt `STARTED` | Điều phối recovery theo owner trước khi launch lại. |
| Log cuối step/job không xuất hiện | `afterStep`/`afterJob` không có cơ hội chạy | Dựa thêm vào repository, heartbeat, hệ thống logs của container. |

## 15. Quy trình thiết kế recovery cho production

Một hệ thống batch có nhiều job dài nên thống nhất các quyết định sau trước khi triển khai:

1. **Khóa công việc:** job name + identifying `JobParameters` thể hiện đúng kỳ dữ liệu, tenant hoặc input file nào?
2. **Persistence:** `JobRepository` có dùng database bền và schema đúng phiên bản không? Có thể truy cập metadata sau khi JVM chết không?
3. **Transaction:** reader/writer và metadata có nằm trong cùng transaction hợp lý hay có side effect ngoài DB?
4. **Checkpoint:** mỗi reader/writer có khả năng restart không, input có ổn định không, vị trí cuối được lưu khi nào?
5. **Idempotency:** thao tác nào có thể bị lặp, khóa chống trùng và reconciliation đặt ở đâu?
6. **Graceful shutdown:** có thể gửi `stop` và chờ `STOPPED` trong grace period không; API nào của Spring Batch được dùng?
7. **Stale execution:** ai có quyền xác nhận process đã chết, ai được quyết định `FAILED` hoặc `ABANDONED`?
8. **Version-specific recovery:** 5.x có quy trình metadata quản trị, 6.x có `JobOperator.recover` khi điều kiện phù hợp.
9. **Scheduler coordination:** làm sao không phát một đợt chạy mới trong lúc execution cũ còn đang xử lý hoặc đang phục hồi?
10. **Verification:** sau restart, kiểm tra trạng thái, checkpoint, số liệu nghiệp vụ và tác dụng phụ ngoài hệ thống.

### Bài tập thực hành

**Bài 1 — So sánh exception với process kill**

- Tạo một job có một chunk step đọc 200 bản ghi từ database test và ghi sang bảng đích.
- Ở lần chạy A, chủ động ném exception sau một số chunk để thấy `FAILED` và khả năng restart bình thường.
- Ở lần chạy B, chạy job trong JVM riêng, kill khi có một số chunk đã commit; quan sát status có thể vẫn `STARTED`.
- Giải thích vì sao hai tình huống đòi hỏi cách xử lý khác nhau.

**Bài 2 — Khôi phục đúng `JobInstance`**

- Chọn `businessDate` làm identifying parameter và `triggerSource` làm non-identifying.
- Quan sát lần chạy đầu bị kill rồi phục hồi; restart với cùng `businessDate`.
- Kiểm tra `JobInstance` không đổi nhưng `JobExecution` mới được tạo.
- Thử thêm `run.id` identifying và phân tích nguy cơ khởi tạo instance mới, mất checkpoint.

**Bài 3 — Side effect không nằm trong transaction**

- Mô phỏng writer gọi API bên ngoài trả thành công nhưng crash trước khi lưu `processed=true`.
- Tạo idempotency key ổn định theo business key và kiểm tra lần gọi lặp không tạo kết quả trùng.
- So sánh với writer chỉ ghi vào cùng một database transactional.

**Bài 4 — Recovery runbook**

- Thiết kế bảng ghi những bằng chứng cần có trước khi xác nhận execution đã chết.
- So sánh `FAILED`, `STOPPED`, `ABANDONED` và `STARTED` khi quyết định restart.
- Với Spring Batch 6.x, thực hành `JobOperator.recover(...)` trên database test riêng; với 5.x, mô tả thủ tục quản trị metadata đã được kiểm soát thay vì chạy SQL tùy tiện.
- Viết assertion kiểm tra kết quả DB cuối cùng, không chỉ kiểm tra `BatchStatus.COMPLETED`.

## 16. Tài liệu tham khảo chính thức

- [Spring Batch 5.2 — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html): dừng job, `JobOperator`, xử lý execution sau process chết và `ABANDONED`.
- [Spring Batch 6.x — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): graceful shutdown, `JobExecutionShutdownHook` và phục hồi với `JobOperator.recover`.
- [Spring Batch 6.x — `JobOperator` Javadoc](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html): hợp đồng các phương thức `stop`, `restart`, `recover`, `abandon`.
- [Spring Batch 5.2 — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/5.2/step/chunk-oriented-processing/restart.html): `startLimit`, `allowStartIfComplete` và hành vi restart step.
- [Spring Batch 5.2 — ItemStream](https://docs.spring.io/spring-batch/reference/5.2/readers-and-writers/item-stream.html): `open`, `update`, `close`, `ExecutionContext` và checkpoint.
- [Spring Batch — What's New in Version 6](https://docs.spring.io/spring-batch/reference/whatsnew.html): hỗ trợ graceful shutdown được bổ sung từ 6.0.

