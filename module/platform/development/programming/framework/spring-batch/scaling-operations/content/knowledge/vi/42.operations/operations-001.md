# Start, Stop, Pause và Resume Job trong Spring Batch

## 1. Bối cảnh vận hành

Trong module **SPRING_BATCH_SCALING_OPERATIONS**, chúng ta học cách mở rộng Spring Batch để xử lý workload dữ liệu lớn bằng **multi-threaded step, parallel steps, partitioning** và các mô hình phân tán. Một job chạy hàng giờ không thể chỉ được đánh giá bằng tốc độ: người vận hành còn phải biết **khởi chạy đúng đầu vào, dừng có kiểm soát, xử lý yêu cầu tạm ngưng, tiếp tục sau sự cố và kiểm tra dữ liệu đã commit**.

Ví dụ một job nhập 20 triệu giao dịch chạy bằng 8 partition. Sau 40 phút, database nguồn bắt đầu quá tải. Người vận hành cần giảm áp lực, giữ phần dữ liệu đã xử lý, sau đó hoàn thành phần còn lại khi hệ thống ổn định. Nếu tùy tiện hủy process, chạy lại bằng tham số khác hoặc xóa metadata để “chạy từ đầu”, có thể tạo trùng giao dịch hay bỏ sót bản ghi.

Spring Batch cung cấp các thành phần:

- `JobLauncher`: yêu cầu khởi chạy một `Job` với `JobParameters`.
- `JobRepository`: lưu trạng thái job, step, execution context và checkpoint.
- `JobExplorer`: tra cứu metadata thực thi để theo dõi và điều tra.
- `JobOperator`: các thao tác vận hành như start, stop, restart và truy vấn execution.
- `JobExecution` và `StepExecution`: đại diện cho **một lần thực thi** của job/step.
- `TaskExecutor`: có thể làm job launcher bất đồng bộ hoặc chạy worker đồng thời, tùy vị trí được cấu hình.

**Điểm cần nhớ trước tiên:** Spring Batch có **start**, yêu cầu **stop** và **restart**; **không có API pause/resume tức thời hay `BatchStatus.PAUSED` chung cho mọi job**. Trong nhiều trường hợp, yêu cầu “pause” được hiện thực thành **dừng có kiểm soát, chờ đạt `STOPPED`, rồi restart cùng `JobInstance`**. Đây là phục hồi từ checkpoint, không phải đóng băng rồi đánh thức cùng một thread/transaction.

## 2. Mô hình JobInstance, JobExecution và StepExecution

Muốn vận hành đúng, cần phân biệt ba thực thể:

| Thực thể | Định danh và vai trò | Khi restart |
| --- | --- | --- |
| `JobInstance` | Kết hợp tên job với **identifying JobParameters**, đại diện cho một lần xử lý logic. | Giữ nguyên khi restart một instance đã dừng/thất bại. |
| `JobExecution` | Một **lần thử chạy** của JobInstance, có execution ID, start/end time, status. | Tạo **JobExecution mới**, không tái sử dụng execution ID cũ. |
| `StepExecution` | Lần thực thi một step trong JobExecution; có read/write/skip counts và `ExecutionContext`. | Spring Batch quyết định step cần chạy lại, tiếp tục hoặc bỏ qua theo metadata và cấu hình. |

Ví dụ:

```text
Job name: importOrders
Identifying parameter: batchId=2026-11-26

JobInstance #57
  ├─ JobExecution #801  -> STOPPED
  │    ├─ StepExecution readOrders -> COMPLETED
  │    └─ StepExecution writeOrders -> STOPPED
  └─ JobExecution #804  -> COMPLETED (restart)
       ├─ readOrders được bỏ qua nếu đủ điều kiện
       └─ writeOrders chạy tiếp theo checkpoint

JobInstance #58
  └─ batchId=2026-11-27 -> lần xử lý logic khác
```

Trong chunk-oriented processing, `ExecutionContext` thường lưu trạng thái reader/writer ở các lần commit để hỗ trợ restart. Lưu trạng thái **không bảo đảm exactly-once cho mọi side effect**: HTTP request hay message đã gửi ra ngoài transaction có thể bị lặp khi retry/restart.

### Identifying và non-identifying parameters

`JobParameters` được dùng để phân biệt JobInstance. Chẳng hạn `batchId` thường là identifying, vì đại diện cho một tập dữ liệu đầu vào cố định. Một thuộc tính như `requestedBy` hoặc correlation ID có thể là non-identifying nếu yêu cầu nghiệp vụ và cách truy vết phù hợp.

**Không thêm timestamp hoặc random run ID chỉ để né lỗi “job instance already complete” khi đang muốn resume.** Làm vậy tạo JobInstance mới, có thể đọc lại toàn bộ dữ liệu thay vì tiếp tục công việc trước đó. Nếu chủ đích chạy một batch nghiệp vụ mới, hãy cấp identifying parameters mới một cách rõ ràng.

## 3. Hiểu BatchStatus trước khi gọi thao tác

Các trạng thái quan trọng của `BatchStatus`:

| Trạng thái | Ý nghĩa vận hành | Hành động thường gặp |
| --- | --- | --- |
| `STARTING` | Execution đang khởi tạo, chưa thực sự chạy xong giai đoạn bắt đầu. | Theo dõi chuyển sang STARTED hoặc lỗi khởi chạy. |
| `STARTED` | Job đang chạy. | Quan sát tiến độ; có thể yêu cầu stop nếu cần. |
| `STOPPING` | Đã ghi nhận yêu cầu dừng; job chưa kết thúc hoàn toàn. | Chờ chuyển sang STOPPED hoặc điều tra lỗi. |
| `STOPPED` | Job dừng có kiểm soát. | Có thể restart khi job cho phép và metadata hợp lệ. |
| `FAILED` | Job thực thi thất bại. | Điều tra nguyên nhân, sửa lỗi rồi restart nếu được phép. |
| `COMPLETED` | Job instance đã kết thúc thành công. | Không restart lại cùng instance; muốn xử lý đợt khác cần instance khác. |
| `ABANDONED` | Execution bị đánh dấu bỏ qua, không tiếp tục theo luồng restart thông thường. | Điều tra và áp dụng runbook quản trị. |
| `UNKNOWN` | Không xác định được trạng thái an toàn. | Điều tra trước khi tác động; tránh tự động restart mù quáng. |

Một đường đi có thể xảy ra:

```text
STARTING -> STARTED -> COMPLETED

STARTING -> STARTED -> STOPPING -> STOPPED
                                    |
                            restart cùng JobInstance
                                    |
                         STARTING -> STARTED -> COMPLETED

STARTED -> FAILED
             |
       restart hợp lệ
             |
         STARTING -> STARTED -> COMPLETED
```

Mỗi nhánh **restart** trên sơ đồ tạo **JobExecution mới** của cùng JobInstance. Execution cũ vẫn mang status `STOPPED` hoặc `FAILED` trong JobRepository.

`BatchStatus` mô tả trạng thái kỹ thuật; `ExitStatus` và exit code mô tả kết quả hoặc quyết định flow. Hai khái niệm có liên hệ nhưng **không được giả định là một giá trị**. Khi điều tra, đọc cả `BatchStatus`, `ExitStatus`, exception, step counts và log theo execution ID.

## 4. START: bắt đầu một job như thế nào?

API thường dùng để khởi chạy:

```java
JobExecution execution = jobLauncher.run(job, jobParameters);
Long executionId = execution.getId();
```

Trước khi start, hệ thống phải xác định:

1. **Job nào** được chạy, đã có `Job` bean và cấu hình repository/transaction phù hợp.
2. **Bộ dữ liệu nào** được xử lý, định danh bằng các identifying parameters ổn định.
3. **Có instance trùng đang chạy/đã hoàn tất không**; JobRepository quản lý các ràng buộc này, nhưng ứng dụng vẫn cần xử lý exception và tính idempotent ở tầng API.
4. **Nguồn dữ liệu đã sẵn sàng chưa**: file đã upload xong, batch staging đã chốt, upstream đã bàn giao.
5. **Tài nguyên**: DB connection, CPU, heap, số worker, downstream rate limit và job khác đang chạy.

Ví dụ tạo tham số kiểu rõ ràng bằng `JobParametersBuilder` (Spring Batch 5.x):

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("batchId", "2026-11-26", true)     // identifying
    .addString("requestedBy", "scheduler", false) // non-identifying
    .toJobParameters();

JobExecution execution = jobLauncher.run(importOrdersJob, parameters);
System.out.println(execution.getId());
```

Khi start một instance đã `COMPLETED` với cùng identifying parameters, Spring Batch không coi đây là lần chạy mới hợp lệ. Nếu instance đang chạy, yêu cầu chạy trùng cũng bị từ chối theo cơ chế repository. Tầng điều phối nên chuyển các exception này thành thông báo vận hành rõ ràng, ví dụ “đợt xử lý này đã hoàn tất” hoặc “đang có một execution chạy”.

### Start bằng JobOperator

`JobOperator` cũng cung cấp chức năng `start(jobName, parameters)` và `startNextInstance(jobName)`. Các API này cần khả năng tìm job theo tên qua cấu hình/registry tương ứng; cách truyền `Properties` và quy tắc chuyển đổi parameter có thể khác giữa các phiên bản. Với job name do người dùng gửi, phải giới hạn theo danh sách job được phép và validate parameters trước khi gọi.

**`startNextInstance` khác `restart`.** `startNextInstance` dựa trên cơ chế tăng tham số, chẳng hạn `JobParametersIncrementer`, để tạo lần xử lý logic mới. Nó không phải nút “resume” cho một execution bị dừng.

## 5. JobLauncher đồng bộ và bất đồng bộ

Một khó khăn vận hành thường gặp: nếu gọi `JobLauncher.run` đồng bộ trong request HTTP, request có thể phải đợi đến khi job hoàn tất mới trả kết quả. Việc mở một endpoint stop khác vẫn có thể hoạt động, nhưng luồng start bị chiếm trong thời gian dài và khó trả execution ID sớm cho client.

Spring Batch 5.x có `TaskExecutorJobLauncher`. Launcher này thực thi việc chạy job thông qua `TaskExecutor` đã được gán. Khi executor chạy bất đồng bộ, lời gọi start có thể trả về trước khi job hoàn thành.

Ví dụ cấu hình:

```java
@Configuration
public class JobLaunchConfig {

    @Bean
    public ThreadPoolTaskExecutor jobLaunchExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("batch-launch-");
        executor.initialize();
        return executor;
    }

    @Bean
    public TaskExecutorJobLauncher asyncJobLauncher(
            JobRepository jobRepository,
            @Qualifier("jobLaunchExecutor") TaskExecutor executor)
            throws Exception {

        TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
        launcher.setJobRepository(jobRepository);
        launcher.setTaskExecutor(executor);
        launcher.afterPropertiesSet();
        return launcher;
    }
}
```

Lưu ý:

- `TaskExecutorJobLauncher` **không tự làm chunk hoặc partition chạy song song**. Nó quyết định luồng gọi job. Concurrency của các step phải cấu hình riêng.
- Nếu executor là `SyncTaskExecutor`, `run` vẫn chạy trên luồng gọi. Muốn API start trả sớm phải dùng một executor bất đồng bộ thật sự.
- Execution ID có thể được trả về khi status còn `STARTING`/`STARTED`; client cần dùng endpoint trạng thái thay vì coi HTTP 202 là job đã thành công.
- Launcher pool và worker pool nên được định cỡ theo **ngân sách tài nguyên tổng**, vì nhiều job chạy đồng thời có thể nhân lên số partition/worker.
- Nếu dùng Spring Boot và muốn chỉ khởi chạy bằng API hoặc scheduler riêng, cần kiểm tra cấu hình auto-run, thường có `spring.batch.job.enabled=false`.

Một API vận hành thường trả `202 Accepted` kèm execution ID cho yêu cầu start đã được chấp nhận, rồi cung cấp endpoint xem trạng thái. Điều này là một **hợp đồng API ứng dụng**, không phải cam kết kết quả `COMPLETED` từ Spring Batch.

## 6. Ví dụ service vận hành với JobLauncher, JobOperator và JobExplorer

Ví dụ dưới đây cho thấy sự tách biệt giữa **yêu cầu điều khiển** và **đọc trạng thái thực tế**. Các bean `JobOperator` và `JobExplorer` phải được cấu hình sẵn trong Spring Batch context. Mẫu sử dụng API phổ biến của Spring Batch 5.x và lược import cho dễ đọc.

```java
@Service
public class BatchJobControlService {

    private final JobLauncher launcher;
    private final Job importOrdersJob;
    private final JobOperator operator;
    private final JobExplorer explorer;

    public BatchJobControlService(
            @Qualifier("asyncJobLauncher") JobLauncher launcher,
            @Qualifier("importOrdersJob") Job importOrdersJob,
            JobOperator operator,
            JobExplorer explorer) {
        this.launcher = launcher;
        this.importOrdersJob = importOrdersJob;
        this.operator = operator;
        this.explorer = explorer;
    }

    public long start(String batchId) throws Exception {
        if (batchId == null || batchId.isBlank()) {
            throw new IllegalArgumentException("batchId is required");
        }

        JobParameters params = new JobParametersBuilder()
            .addString("batchId", batchId, true)
            .toJobParameters();

        JobExecution execution = launcher.run(importOrdersJob, params);
        return execution.getId();
    }

    public boolean requestStop(long executionId) throws Exception {
        return operator.stop(executionId);
    }

    public long restart(long previousExecutionId) throws Exception {
        return operator.restart(previousExecutionId);
    }

    public BatchStatus getStatus(long executionId) {
        JobExecution execution = explorer.getJobExecution(executionId);
        if (execution == null) {
            throw new IllegalArgumentException(
                "Unknown job execution: " + executionId
            );
        }
        return execution.getStatus();
    }
}
```

Cần đọc ví dụ đúng phạm vi:

- `start(batchId)` tạo/yêu cầu chạy JobInstance logic theo `batchId`.
- `requestStop(executionId)` **gửi yêu cầu dừng** đến execution hiện hành. Boolean trả về **không có nghĩa** đã đạt trạng thái `STOPPED`; phải đọc lại trạng thái.
- `restart(previousExecutionId)` khởi chạy một `JobExecution` mới cho instance cũ nếu điều kiện restart hợp lệ; nó **trả về ID mới**, không dùng lại ID cũ.
- `getStatus(executionId)` đọc metadata; trong hệ phân tán phải tính tới độ trễ quan sát và kết quả cập nhật bất đồng bộ.
- Exception từ repository/operator cần được map thành mã lỗi và log thích hợp, không nên trả stack trace hoặc chi tiết kết nối DB cho caller.

Để triển khai endpoint thực tế, thêm phân quyền thao tác, giới hạn job được start, validate `batchId`, ghi audit (ai làm, khi nào, execution ID nào, lý do gì), và xử lý những request lặp do client retry. Không nên cho phép mọi người gọi stop/restart vào execution bất kỳ.

## 7. STOP: dừng có kiểm soát

Spring Batch cung cấp:

```java
boolean requested = jobOperator.stop(executionId);
```

Về nguyên tắc, thao tác này **yêu cầu** job đang chạy dừng lại. JobExecution có thể đi qua `STOPPING` rồi kết thúc ở `STOPPED` khi công việc đang thực thi nhận thấy yêu cầu dừng và thoát thích hợp.

```text
Operator gửi STOP execution #801
             |
      repository đánh dấu STOPPING
             |
      worker nhận thấy tín hiệu dừng
             |
     hoàn thành/rollback phần cần thiết
             |
       giải phóng tài nguyên
             |
          STOPPED
```

Không nên coi `stop()` như `Thread.stop()`, `SIGKILL` hoặc rollback tự động toàn bộ job. Spring Batch chủ yếu hỗ trợ **cooperative stop**:

- Ở một chunk-oriented step, tín hiệu dừng thường được phát hiện tại điểm kiểm tra giữa các lần xử lý. Chunk/transaction đang chạy có thể cần hoàn tất hoặc trả lỗi trước khi dừng.
- Nếu `ItemReader.read()`, `ItemWriter.write()` hay cuộc gọi API bị block không có timeout, job có thể ở `STOPPING` rất lâu.
- Một custom `Tasklet` có vòng lặp dài phải được thiết kế để kiểm tra yêu cầu kết thúc hoặc chia việc thành đơn vị có thể kiểm soát; không giả định framework ngắt được mọi vòng lặp tùy ý.
- Mỗi step/partition có transaction riêng. Những chunk đã commit **không bị rollback toàn cục** khi stop.
- Với remote partitioning, cần kiểm chứng cách manager/worker truyền và nhận yêu cầu dừng; tín hiệu ở manager không đồng nghĩa mọi worker ngoài process đã ngừng ngay.

**Tránh ép kill process để thực hiện stop thường lệ.** `SIGKILL`, máy chủ mất điện hoặc container bị hủy không đủ thời gian cleanup có thể để lại trạng thái metadata `STARTED`/`UNKNOWN` và side effect không được ghi nhận đầy đủ. Hãy dùng cơ chế graceful shutdown, timeout hợp lý và quan sát trạng thái cuối cùng.

### Hướng vận hành khi stop bị chậm

1. Kiểm tra `JobExecution` đang ở `STARTED`, `STOPPING` hay đã kết thúc.
2. Xác định step/partition còn chạy từ repository, log theo execution ID và thread dump/trace nếu cần.
3. Kiểm tra DB lock wait, connection wait, external HTTP timeout và worker heartbeat; tìm tác vụ bị block.
4. Chờ trong giới hạn thời gian vận hành đã đặt và dùng quy trình ứng cứu nếu quá hạn; ghi nhận dữ liệu đã commit trước khi can thiệp.
5. Chỉ restart sau khi xác minh execution cũ và mọi worker liên quan đã thật sự dừng, tránh hai lần xử lý cùng một dataset đồng thời.

Không đổi status thủ công bằng SQL như một bước xử lý thường nhật. Việc sửa metadata sai có thể đánh lừa cơ chế restart và tạo mất hoặc trùng dữ liệu.

## 8. PAUSE: Spring Batch không có nút tạm dừng phổ quát

Từ “pause” có thể mang ba ý nghĩa vận hành khác nhau:

| Ý định | Cách tiếp cận | Lưu ý |
| --- | --- | --- |
| Ngưng nhận **job mới** trong giờ cao điểm | Tạm tắt trigger scheduler hoặc đặt cờ admission control. | Job đang chạy vẫn tiếp tục, trừ khi được stop riêng. |
| Tạm ngưng job đang chạy rồi tiếp tục sau | Gọi stop, đợi `STOPPED`; sau đó `restart` cùng instance. | Tiếp tục từ checkpoint, có thể chạy lại công việc chưa commit. |
| Dừng logic tại một **ranh giới bước được thiết kế trước** | Thiết kế job flow với điều kiện stop và điểm restart dự định. | Có thể dừng ở step boundary, không phải pause tức thời giữa câu lệnh. |

Spring Batch không có trạng thái `PAUSED` trong enum `BatchStatus` và không có lệnh “đóng băng toàn bộ worker” có tính portable, an toàn transaction cho tất cả loại step. Nếu giao diện người dùng hiển thị “Paused”, đó phải là **trạng thái nghiệp vụ/tầng điều phối tự định nghĩa** và phải map rõ tới execution thực tế (ví dụ `STOPPING` hay `STOPPED`).

### Không dùng Thread.sleep để “pause” một chunk

Giữ các thread ngủ lâu ngay giữa chunk có thể kéo theo transaction đang mở, DB lock, connection bị giữ, timeout, job repository không có checkpoint mới, và mất khả năng scale. Một vòng lặp chờ cờ trong processor cũng làm hành vi restart khó kiểm chứng.

Nếu cần **tạm ngưng thực sự theo checkpoint**, lựa chọn đáng tin cậy thường là stop + restart. Nếu yêu cầu kinh doanh là trì hoãn xử lý, hãy đặt logic gating **trước khi khởi chạy** hoặc tại một điểm an toàn giữa các step/chunk và ghi rõ semantics. Không tự sáng tạo một “resume” bằng cách tiếp tục thread cũ khi đã mất process.

### Pause có điều phối

Một quy trình có thể định nghĩa cờ `operatorHold` theo `batchId`:

1. Khi operator chọn Pause, API lưu audit/cờ “đang yêu cầu tạm ngưng”, rồi gọi `JobOperator.stop(executionId)`.
2. Trạng thái giao diện chuyển `PAUSE_REQUESTED` (trạng thái do ứng dụng định nghĩa) cho đến khi repository báo `STOPPED`.
3. Sau khi `STOPPED`, giao diện hiển thị `PAUSED` theo nghĩa **đã dừng có thể restart**, miễn không có worker ngoài tiến trình còn chạy.
4. Khi operator chọn Resume, ứng dụng kiểm tra cờ hold, đầu vào vẫn hợp lệ và gọi `restart(previousExecutionId)`.
5. API lưu và trả **execution ID mới**, tiếp tục theo dõi đến `COMPLETED` hoặc `FAILED`.

Đây là thiết kế **điều phối và giao diện**, không phải status/API pause/resume có sẵn từ Spring Batch. Phải có quy tắc xử lý nếu stop chưa xong, job đã hoàn thành trước khi pause, hoặc một yêu cầu resume khác đang chạy.

## 9. RESUME thực tế là RESTART: điều kiện tiên quyết

Với job từng `FAILED` hoặc `STOPPED`, Spring Batch có thể khởi chạy lại một `JobExecution` của cùng `JobInstance`:

```java
long newExecutionId = jobOperator.restart(previousExecutionId);
```

Điều kiện cần kiểm tra:

- Execution trước đã kết thúc ở trạng thái phù hợp, không còn worker cũ đang hoạt động.
- Job có cho phép restart; chẳng hạn job có thể cấu hình không restartable bằng `preventRestart()`.
- Có metadata trong `JobRepository` cho instance và các step; không xóa hoặc ghi đè `BATCH_*` tùy ý.
- `ExecutionContext` và checkpoint của reader/writer còn hợp lệ.
- Tập dữ liệu nguồn được giữ ổn định; parameter định danh vẫn đại diện cho đúng dataset.
- Những side effect ngoài database có idempotency key hoặc cơ chế dedup/outbox.

Với step đã `COMPLETED`, Spring Batch thông thường không chạy lại step đó trong restart, trừ khi có cấu hình cho phép như `allowStartIfComplete(true)`. Một worker partition đã hoàn thành có thể được bỏ qua khi restart, trong khi partition lỗi tiếp tục theo metadata. Không mặc định toàn job sẽ chạy lại từ đầu, nhưng cũng **không mặc định luôn tiếp tục đúng item kế tiếp** nếu component không lưu checkpoint đúng.

### Restart có thể chạy lại một số item

Giả sử một chunk đọc 100 item. Sau khi xử lý 60 item, process chết và transaction chưa commit. Khi restart từ checkpoint của chunk đã commit trước đó, 60 item này có thể được xử lý lại. Đây là hành vi kỳ vọng của retry/restart theo ranh giới transaction.

Vì vậy writer và side effect phải bảo đảm xử lý lặp an toàn:

- Ghi DB qua khóa duy nhất/upsert theo `businessId` khi phù hợp.
- Ghi sự kiện với idempotency key; ưu tiên transactional outbox nếu cần nhất quán DB-message.
- Tránh gọi API có tác dụng tiền tệ/vận đơn nhiều lần mà không có dedup.
- Đối soát **tập khóa đầu vào với tập khóa kết quả** sau restart, không chỉ so số dòng.

### Restart khác start instance mới

| Tình huống | Thao tác đúng về mặt ngữ nghĩa |
| --- | --- |
| Job chưa từng chạy cho `batchId=2026-11-26` | `start` với bộ identifying parameters đó. |
| Job đang `STARTED`, cần ngưng tạm | `stop(executionId)`, sau đó chờ `STOPPED`. |
| Job đã `STOPPED`, muốn tiếp tục | `restart(previousExecutionId)` trên cùng JobInstance. |
| Job `FAILED` vì API timeout đã khắc phục | `restart(previousExecutionId)` nếu đáp ứng điều kiện. |
| Job đã `COMPLETED`, muốn xử lý `batchId=2026-11-27` | `start` instance mới với batch ID mới. |
| Job đã `COMPLETED`, người dùng bấm “Resume” | Trả thông báo đã hoàn tất; không gắn random timestamp để cố khởi chạy lại. |

Nếu muốn chủ đích **reprocess** cùng dataset đã hoàn tất, hãy thiết kế một quy trình nghiệp vụ riêng cho rerun (versioned run ID, cleanup/replace hay idempotent reconciliation). Đây không phải chức năng resume của execution cũ.

## 10. Stop/Restart trong multi-threaded step và parallel steps

Module học cách scale qua nhiều luồng; điều đó làm lệnh stop phức tạp hơn so với step tuần tự.

### Multi-threaded step

Với `StepBuilder.taskExecutor(...)`, nhiều chunk của **cùng step** có thể chạy đồng thời:

```text
Step import
   |
   +-- worker-1: chunk A -> COMMIT
   +-- worker-2: chunk B -> đang ghi
   +-- worker-3: chunk C -> đang gọi API
   +-- worker-4: chunk D -> COMMIT

Operator: STOP request
   |
   +-- một số chunk đã commit
   +-- chunk đang chạy cần phản ứng/hoàn thành/rollback
   +-- stop chỉ được xác nhận khi step kết thúc phù hợp
```

**Không bảo đảm thứ tự commit** giữa chunk. Reader, processor, writer và checkpoint cần thread-safe trước cả khi xét restart. Nếu reader có mutable cursor được chia sẻ thiếu đồng bộ, việc stop/restart có thể phơi bày lỗi mất/trùng item.

### Parallel steps

Hai flow độc lập có thể chạy song song bằng `split(taskExecutor)`. Yêu cầu stop trên job cần chờ các flow/step liên quan đạt trạng thái kết thúc thích hợp. Không nên khởi chạy ngay job khác ghi cùng tập dữ liệu vì thấy **một** flow đã dừng trong khi flow còn lại đang chạy.

Nếu hai flow có phụ thuộc dữ liệu, không sử dụng parallel steps để tránh thứ tự; ranh giới dừng/restart cũng cần tôn trọng các phụ thuộc đó.

## 11. Stop/Restart trong local và remote partitioning

Trong partitioning, mỗi partition có `StepExecution` và `ExecutionContext` riêng; đây là lợi thế khi restart một workload lớn.

```text
Manager step: processInvoices
        |
    partition0 -> COMPLETED
    partition1 -> COMPLETED
    partition2 -> FAILED
    partition3 -> COMPLETED

Restart:
    partition0/1/3: bỏ qua nếu đáp ứng quy tắc restart
    partition2: tiếp tục dựa trên checkpoint/ExecutionContext
```

Các điều kiện quan trọng:

1. **Partition name ổn định:** cùng tên phải đại diện cùng vùng dữ liệu khi restart; không tạo tên ngẫu nhiên.
2. **Tập dữ liệu không đổi:** range theo primary key, tenant, ngày hoặc shard không được thay đổi tùy tiện giữa các lần chạy cùng instance.
3. **Reader có scope phù hợp:** `@StepScope` để mỗi partition có reader và checkpoint riêng; không chia sẻ mutable reader giữa partition.
4. **Writer có thể lặp:** một partition đã commit vài chunk trước khi lỗi không được nhân đôi side effect khi tiếp tục.
5. **Manager và worker đã thực sự dừng:** `STOPPING` trên manager không chứng minh remote worker đã ngừng đọc/ghi.

Với **remote partitioning** hoặc **remote chunking**, cần thêm bước điều tra message broker, worker còn sống, in-flight message, deduplication và lệnh điều phối stop qua các process. Restart khi worker cũ còn đang xử lý cùng partition có thể gây ghi trùng hoặc xung đột khó tái hiện.

Nên có metric theo từng partition/worker, correlation ID, thời gian chunk cuối commit và timestamp heartbeat. Khả năng stop đúng thời điểm phụ thuộc contract của hệ thống messaging và worker, không chỉ cấu hình `JobOperator`.

## 12. Phân biệt graceful stop với crash và forced termination

Dưới đây là ba tình huống khác nhau:

| Tình huống | Điều gì thường xảy ra | Cách ứng phó |
| --- | --- | --- |
| `JobOperator.stop` | Yêu cầu dừng có kiểm soát, có thể qua `STOPPING` đến `STOPPED`. | Theo dõi trạng thái, chờ checkpoint và tài nguyên được giải phóng. |
| JVM/container nhận signal shutdown | Có thể có thời gian đóng tài nguyên; job chưa chắc đã tự chuyển thành `STOPPED`. | Quy trình preStop/grace period, yêu cầu stop trước khi shutdown khi có thể. |
| `SIGKILL`, mất điện, crash process | Không bảo đảm callback/checkpoint chạy; metadata có thể còn `STARTED`. | Xác minh worker đã chết, đối soát DB và metadata, áp dụng runbook recovery. |

Một `JobExecution` bị kẹt `STARTED` sau crash có thể làm repository từ chối khởi chạy lại cùng JobInstance vì hệ thống tưởng execution còn chạy. **Không tự động sửa `BATCH_JOB_EXECUTION.STATUS` thành `FAILED` bằng SQL rồi bấm restart**, trừ khi đã có quy trình kiểm soát và xác minh đầy đủ. Cần điều tra task còn hoạt động, transaction còn treo, heartbeat, JobRepository và dữ liệu thực tế; dùng cơ chế recovery phù hợp với phiên bản/hệ thống.

Ở Kubernetes, thời gian `terminationGracePeriodSeconds` cần phù hợp với thời gian hoàn thành chunk, network timeout và cleanup. Job chunk quá lớn hoặc gọi dịch vụ vô hạn timeout có thể vượt quá grace period. Hãy thiết kế chunk nhỏ vừa đủ, timeout rõ ràng và cơ chế shutdown phù hợp với SLA.

## 13. Quy trình vận hành mẫu: Pause rồi Resume an toàn

Tình huống: job đồng bộ 5 triệu giao dịch, chạy 6 partition, DB đang quá tải. Mục tiêu là giảm tải rồi tiếp tục từ phần đã commit.

### Giai đoạn A: Xác nhận job đang chạy

Ghi `jobName`, `JobInstanceId`, `JobExecutionId` hiện tại, identifying `JobParameters`, `BatchStatus` và tiến độ từng partition. Kiểm tra batch đầu vào đã chốt, không có worker bất thường.

```text
jobName: importTransactions
batchId: nightly-2026-11-26
jobInstanceId: 57
jobExecutionId: 801
status: STARTED
completedPartitions: 2/6
```

### Giai đoạn B: Gửi yêu cầu pause

Tầng ứng dụng lưu yêu cầu operator và gọi `JobOperator.stop(801)`. API có thể trả về “đã gửi yêu cầu” trong khi job vẫn `STOPPING`. Không hiển thị “Paused” như trạng thái chắc chắn cho đến khi `JobExplorer` xác nhận `STOPPED` và các worker liên quan đã dừng.

Theo dõi connection, transaction, worker heartbeat. Nếu quá thời hạn, điều tra nguyên nhân; không khởi chạy tiếp trong khi vẫn còn worker ghi vào DB.

### Giai đoạn C: Xác minh trạng thái và nguồn dữ liệu

Khi status là `STOPPED`, ghi lại số record commit, step/partition chưa hoàn tất, exception và thời điểm ngừng. Xác nhận bản staging/`batchId` vẫn có cùng tập dữ liệu; xác minh không có thao tác đang ghi dở ngoài transaction.

### Giai đoạn D: Resume bằng restart

Khi DB đã ổn, điều phối gọi:

```java
long resumedExecutionId = jobOperator.restart(801L);
```

Ví dụ repository tạo `JobExecutionId=809` trong **cùng JobInstance 57**. Theo dõi execution 809 đến trạng thái cuối cùng; không tiếp tục poll execution 801 để chờ nó đổi thành `COMPLETED`, vì execution 801 vẫn là `STOPPED`.

### Giai đoạn E: Đối soát sau khi hoàn tất

Đối chiếu tổng dòng đầu vào và đầu ra **theo tập khóa nghiệp vụ**, tổng số tiền/checksum phù hợp, lỗi skip/retry và kết quả từng partition. Kiểm tra không có bản ghi được xử lý hai lần ngoài chính sách. Chỉ đánh dấu nghiệp vụ `COMPLETED` sau khi cả trạng thái Spring Batch và đối soát dữ liệu đạt yêu cầu.

## 14. Giám sát, cảnh báo và audit cho job điều khiển được

Tối thiểu, dashboard cần hiển thị:

| Nhóm | Metric/trường nên có | Vì sao cần |
| --- | --- | --- |
| Định danh | Job name, instance ID, execution ID, batch ID, start/end time | Phân biệt chạy mới, chạy lại và restart. |
| Trạng thái | `BatchStatus`, `ExitStatus`, thời điểm thay đổi trạng thái | Biết start/stop/restart đang ở giai đoạn nào. |
| Tiến độ | `readCount`, `writeCount`, `skipCount`, `commitCount` theo step/partition | Đánh giá đã xử lý bao nhiêu và có tiến triển hay không. |
| Lỗi | Exception, retry, timeout, deadlock, rejected tasks | Phân biệt lỗi có thể retry với lỗi nghiệp vụ. |
| Executor | Active thread, queue depth, task rejection | Phát hiện quá tải lúc chạy nhiều job/partition. |
| Database/API | Connection wait, lock wait, latency, 429/503, pool utilization | Hiểu tác động của worker lên hệ thống khác. |
| Phục hồi | Restart count, last checkpoint, thời gian STOPPING, stuck execution | Tìm job không dừng hoặc không tiếp tục được. |
| Tính đúng đắn | Duplicate/missing business keys, reconciliation totals | Tránh tình huống job “xanh” nhưng dữ liệu sai. |

Audit cho mỗi thao tác nên có: **ai**, **khi nào**, **vì sao**, **job/execution nào**, **request ID**, **trạng thái trước/sau**, **execution ID mới nếu restart**. Khi thao tác điều khiển đến từ API, xác thực và phân quyền phải rõ ràng: quyền đọc status khác quyền start, stop hay restart.

Cảnh báo hữu ích không chỉ là `FAILED`: còn có `STOPPING` quá lâu, `STARTED` không tăng tiến độ trong khoảng thời gian bất thường, connection pool cạn, worker mất heartbeat, hoặc job hoàn thành nhưng đối soát dữ liệu thất bại.

## 15. Lỗi vận hành thường gặp và cách xử lý

### Lỗi 1: Gọi stop rồi lập tức gọi restart

`stop()` có thể mới chuyển execution sang `STOPPING`. Lúc đó step/partition vẫn đang xử lý; restart cùng instance có thể bị từ chối hoặc dẫn đến tranh chấp nếu thao tác điều phối sai.

**Cách xử lý:** đợi `STOPPED` và kiểm tra worker thực sự kết thúc trước khi restart.

### Lỗi 2: Dùng timestamp mới để “resume”

Thêm `run.id` hoặc timestamp identifying khi start sẽ tạo **JobInstance mới**, không tiếp tục checkpoint cũ.

**Cách xử lý:** dùng `JobOperator.restart(previousExecutionId)` trên execution thất bại/dừng hợp lệ; không đổi identifying parameters của instance.

### Lỗi 3: Tưởng stop rollback mọi bản ghi

Một số chunk/partition có thể đã commit trong khi chunk khác vẫn chạy. `STOPPED` chỉ mô tả trạng thái job, không xóa kết quả đã commit.

**Cách xử lý:** thiết kế writer idempotent và đối soát theo business key khi tiếp tục.

### Lỗi 4: Custom Tasklet chạy vòng lặp vô hạn không kiểm tra dừng

`STOPPING` có thể kéo dài vì code không đến điểm framework có thể kết thúc, hoặc đang block tại I/O không timeout.

**Cách xử lý:** chia việc thành đơn vị nhỏ, timeout rõ ràng, kiểm tra tín hiệu kết thúc ở điểm an toàn và không giữ transaction lâu.

### Lỗi 5: Pause bằng ngủ thread trong transaction

Transaction và DB lock tiếp tục bị giữ, checkpoint không được cập nhật, dễ gây timeout và deadlock.

**Cách xử lý:** dùng stop/restart, hoặc gating trước điểm bắt đầu một transaction mới.

### Lỗi 6: Không lưu execution ID mới sau restart

Hệ thống theo dõi execution cũ `STOPPED` và tưởng resume thất bại, trong khi execution mới đang chạy.

**Cách xử lý:** API restart trả về và lưu ID mới; tương quan bằng cùng JobInstance ID.

### Lỗi 7: Kill container và lập tức sửa trạng thái DB

Sau crash, execution có thể còn ghi `STARTED`, trong khi worker ngoài process hoặc transaction chưa chắc đã kết thúc.

**Cách xử lý:** điều tra tài nguyên còn hoạt động, xác minh dữ liệu và dùng runbook recovery an toàn; tránh cập nhật metadata tùy tiện.

### Lỗi 8: Retry/Restart làm gửi side effect hai lần

Một chunk gọi API thành công rồi transaction DB rollback; khi restart, API bị gọi lại.

**Cách xử lý:** idempotency key, unique constraint, outbox/dedup, tách side effect và reconciliation.

## 16. Bài thực hành: thiết kế API điều khiển job

Hãy giả định bạn có job `importPayments` chạy bằng local partitioning với một tập staging bất biến theo `batchId`.

**Bài 1 — Start:** tạo `JobParameters` chứa `batchId` là identifying, yêu cầu job chạy bất đồng bộ, trả execution ID. Thử gửi hai request start cùng `batchId` khi job đầu chưa kết thúc; giải thích repository và tầng API xử lý trùng như thế nào.

**Bài 2 — Stop:** đang ở `STARTED`, gọi `JobOperator.stop(executionId)`. Quan sát chuyển `STOPPING` rồi `STOPPED`; đo thời gian dừng khi chunk size là 100 và 5.000. Kiểm tra item đã commit, DB connections và log worker.

**Bài 3 — “Pause”:** thiết kế một endpoint `POST /jobs/{executionId}/pause`. Endpoint ghi audit và gửi stop; trạng thái hiển thị `PAUSE_REQUESTED` cho đến khi execution dừng. Giải thích vì sao không được lập tức hiển thị “PAUSED” nếu repository còn `STOPPING`.

**Bài 4 — Resume:** sau khi `STOPPED`, gọi restart, lưu execution ID mới và đối soát các partition đã commit. Chạy thêm một lần với lỗi ở giữa chunk và xác nhận writer không tạo duplicate.

**Bài 5 — Crash:** kill process trước khi một chunk commit. Kiểm tra metadata, trạng thái DB và những side effect đã xảy ra; đề xuất quy trình recovery mà không sửa SQL tùy tiện.

**Bài 6 — Kiến trúc phân tán:** giả định một remote worker mất kết nối khi manager nhận stop. Liệt kê tín hiệu cần kiểm tra (worker heartbeat, in-flight message, transaction, last checkpoint, idempotency) trước khi restart.

Tiêu chí đạt: mỗi thao tác có semantics rõ ràng, hoạt động dựa trên JobInstance/JobExecution đúng, có log/audit/timeout và khẳng định được tính đúng đắn của dữ liệu sau restart.

## 17. Checklist trước khi cung cấp nút Start/Stop/Pause/Resume cho operator

- [ ] Phân biệt rõ JobInstance, JobExecution, StepExecution và identifying parameters.
- [ ] Start dùng dataset đã chốt và từ chối/giải thích các execution trùng hợp lệ.
- [ ] Launcher bất đồng bộ được cấu hình rõ nếu API cần trả kết quả sớm.
- [ ] Stop là yêu cầu hợp tác; trạng thái `STOPPING` được theo dõi đến khi kết thúc.
- [ ] Pause được định nghĩa rõ bằng trạng thái ứng dụng; không giả định có `BatchStatus.PAUSED`.
- [ ] Resume dùng `restart` của execution cũ và lưu execution ID mới.
- [ ] Chunk/tasklet có timeout, điểm kiểm tra dừng và transaction boundary phù hợp.
- [ ] Reader/writer, partition, checkpoint, JobRepository và dữ liệu nguồn hỗ trợ restart.
- [ ] Writer và side effect bên ngoài có idempotency/dedup; đã thử crash/retry/restart.
- [ ] Có đối soát khóa nghiệp vụ, không chỉ kiểm tra `BatchStatus.COMPLETED`.
- [ ] Mức song song của job launcher, multi-threaded step, parallel flow, partition và worker được tính theo tài nguyên chung.
- [ ] Có dashboard, log, audit, phân quyền và runbook khi execution kẹt ở `STARTED`/`STOPPING`.
- [ ] Không có thao tác sửa metadata `BATCH_*` thủ công trong luồng vận hành thông thường.

## 18. Ghi nhớ

Vận hành Spring Batch là điều phối **vòng đời execution và dữ liệu đã commit**, không chỉ bật tắt thread. `JobLauncher` và `JobOperator` khởi chạy, gửi yêu cầu dừng và restart; `JobExplorer`/`JobRepository` cung cấp sự thật về trạng thái và checkpoint. `Stop` cần thời gian để đạt `STOPPED`, còn `Pause/Resume` thông thường là quy ước vận hành **stop rồi restart cùng JobInstance**, qua một JobExecution mới.

Khi job được mở rộng bằng nhiều luồng, parallel steps hay partitioning, quyết định dừng và tiếp tục phải dựa trên tình trạng **tất cả worker**, transaction, dữ liệu nguồn và cơ chế idempotency. Một runbook tốt luôn kiểm chứng hai điều sau cùng: **job đã tới trạng thái mong đợi** và **dữ liệu sau restart chính xác**.
