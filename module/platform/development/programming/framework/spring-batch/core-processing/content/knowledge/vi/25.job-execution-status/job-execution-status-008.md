# Status khi operator stop job

Trong Spring Batch, operator có thể yêu cầu dừng một job đang chạy thông qua `JobOperator.stop(executionId)`. Đây là một yêu cầu dừng có kiểm soát: framework đánh dấu execution đang trong quá trình dừng, sau đó step đang chạy nhận biết tín hiệu ở một điểm an toàn và kết thúc theo lifecycle của nó. Job thường chuyển qua trạng thái `STOPPING` rồi kết thúc ở `STOPPED`.

`STOPPING` và `STOPPED` có ý nghĩa khác nhau. `STOPPING` cho biết yêu cầu dừng đã được ghi nhận nhưng job có thể vẫn đang xử lý. `STOPPED` là trạng thái cuối sau khi luồng thực thi đã dừng. Vì vậy, kết quả `true` từ lệnh stop chỉ nên được hiểu là yêu cầu đã được chấp nhận theo API; ứng dụng vẫn cần quan sát `JobExecution` để xác nhận job thực sự đạt `STOPPED`.

Operator stop thường là graceful stop, không phải lệnh kill thread hoặc hủy tức thời một câu SQL, một lời gọi HTTP hay một processor đang chạy. Với chunk step, framework thường dừng ở ranh giới chunk sau khi xử lý transaction hiện tại. Với tasklet, tín hiệu thường được xử lý tại điểm lặp an toàn sau khi lần gọi `execute` hiện tại kết thúc. Do đó, thời gian từ lúc gửi yêu cầu tới lúc job dừng phụ thuộc vào thời gian xử lý hiện tại và khả năng phản hồi của các resource bên ngoài.

## JobOperator và JobExecution

`JobOperator` là API vận hành job, cung cấp các thao tác như khởi chạy, restart, stop và truy vấn execution. Khi operator muốn dừng một job, cần truyền **JobExecution ID** của lần chạy đang hoạt động.

```java
@Service
public class BatchControlService {

    private final JobOperator jobOperator;

    public BatchControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long jobExecutionId) throws Exception {
        return jobOperator.stop(jobExecutionId);
    }
}
```

`jobExecutionId` là ID của một lần thực thi cụ thể, không phải `JobInstance` ID, `Job` ID hoặc `StepExecution` ID. Một `JobInstance` có thể có nhiều `JobExecution` do restart; muốn dừng lần đang chạy, phải dùng đúng execution ID đang hoạt động.

Trong ứng dụng thực tế, nên kiểm tra quyền vận hành và xác nhận execution thuộc job nào trước khi cho phép stop. Không nên nhận một ID tùy ý từ request rồi gọi operator mà không kiểm tra quyền truy cập.

## Vòng đời trạng thái khi operator stop

Một job đang chạy thường có chuỗi trạng thái khái quát:

```text
STARTING
   |
   v
STARTED
   |
   | JobOperator.stop(executionId)
   v
STOPPING       <- yêu cầu dừng đã được ghi nhận
   |
   | step nhận tín hiệu ở điểm an toàn
   v
STOPPED        <- execution đã kết thúc
```

Trạng thái `STOPPING` có thể tồn tại trong một khoảng thời gian. Ví dụ, processor đang xử lý một item lâu hoặc writer đang ghi một chunk lớn. Operator không nên báo người dùng rằng job đã dừng hoàn toàn chỉ vì API stop trả về thành công.

| `BatchStatus` | Ý nghĩa trong tình huống stop |
| --- | --- |
| `STARTED` | Job đang thực thi bình thường |
| `STOPPING` | Có yêu cầu dừng; job chưa hoàn tất việc dừng |
| `STOPPED` | Job đã dừng theo yêu cầu và có thể được restart nếu cấu hình cho phép |
| `COMPLETED` | Job hoàn tất bình thường trước khi yêu cầu stop có hiệu lực hoặc không còn công việc cần dừng |
| `FAILED` | Job kết thúc do lỗi thực thi, không đơn thuần là một graceful stop |
| `ABANDONED` | Execution được đánh dấu bỏ qua/không tiếp tục theo quy trình restart thông thường |
| `UNKNOWN` | Trạng thái không xác định hoặc cần điều tra metadata/resource |

`BatchStatus` mô tả trạng thái thực thi. `ExitStatus` là mã kết quả dùng cho flow và báo cáo. Với một lần stop bình thường, `ExitStatus` thường là `STOPPED`, nhưng khi điều tra nên đọc cả hai giá trị thay vì chỉ suy ra một giá trị từ giá trị còn lại.

## Stop request không phải stop tức thời

Spring Batch phối hợp dừng tại những điểm mà framework có thể kết thúc công việc và lưu trạng thái một cách an toàn. Điều này giúp tránh cắt ngang transaction hoặc để checkpoint phản ánh một phần công việc chưa commit.

### Với chunk-oriented step

Chunk step xử lý một nhóm item trong một transaction. Nếu stop request đến khi processor hoặc writer đang xử lý chunk, framework thường để chunk hiện tại đi tới ranh giới xử lý của nó. Nếu chunk hoàn tất thành công, writer và checkpoint được cập nhật rồi transaction commit; sau đó step nhận biết tín hiệu stop và không bắt đầu chunk tiếp theo.

```text
Chunk 1 -> COMMIT
Chunk 2 -> đang xử lý khi operator gửi stop
          |
          v
       hoàn tất chunk hiện tại
          |
          v
       cập nhật checkpoint
          |
          v
          COMMIT
          |
          v
       nhận stop signal
          |
          v
       step STOPPED
```

Đây là hành vi graceful stop điển hình. Nếu chunk hiện tại tự gặp exception, transaction có thể rollback theo rollback rule và step có thể kết thúc `FAILED` thay vì `STOPPED`. Kết quả cuối cùng phụ thuộc lỗi thực tế và thời điểm tín hiệu dừng được xử lý.

Chunk size lớn hoặc một item xử lý lâu có thể làm thời gian dừng kéo dài. Nếu yêu cầu vận hành cần dừng nhanh hơn, hãy xem xét giảm thời gian xử lý mỗi item, đặt timeout cho I/O và chọn commit interval phù hợp. Không nên giảm chunk size một cách máy móc nếu điều đó làm tăng overhead hoặc ảnh hưởng throughput.

### Với tasklet step

Trong `TaskletStep`, `Tasklet.execute(...)` là đơn vị công việc được gọi trong transaction của mỗi lần lặp. Nếu tasklet đang chạy một lần `execute` dài, stop request thường chỉ được xử lý sau khi lần gọi hiện tại trả về tại điểm kiểm tra tiếp theo.

Nếu tasklet có vòng lặp nội bộ rất dài mà không trả quyền điều khiển cho framework, thời gian dừng có thể lâu. Có thể chia công việc thành các đơn vị nhỏ, lưu checkpoint vào `ExecutionContext` và trả `RepeatStatus.CONTINUABLE` để framework có cơ hội kiểm tra tín hiệu dừng giữa các đơn vị.

```java
public class ProcessPagesTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context =
                contribution.getStepExecution().getExecutionContext();
        int page = context.getInt("nextPage", 0);

        processOnePage(page);
        context.putInt("nextPage", page + 1);

        return hasMorePages(page + 1)
                ? RepeatStatus.CONTINUABLE
                : RepeatStatus.FINISHED;
    }
}
```

Ví dụ xử lý một page mỗi lần gọi để tạo điểm kiểm tra giữa các đơn vị. `processOnePage` và `hasMorePages` là logic ứng dụng. Nếu stop request đến trong lúc xử lý page, page hiện tại cần hoàn tất hoặc rollback theo transaction trước khi tasklet dừng; checkpoint phải đại diện cho page đã commit.

## Gửi stop bằng JobOperator

Một ứng dụng có thể lấy execution ID từ `JobExplorer` hoặc từ kết quả launch, sau đó gọi `JobOperator.stop`.

```java
public boolean stopExecution(
        JobOperator jobOperator,
        long executionId) throws Exception {

    return jobOperator.stop(executionId);
}
```

API có thể báo lỗi nếu không tìm thấy execution hoặc execution không còn ở trạng thái có thể dừng. Xử lý các trường hợp này riêng biệt:

- ID không tồn tại: không có execution tương ứng.
- Execution đã `COMPLETED`, `FAILED` hoặc `STOPPED`: không còn là execution đang chạy để gửi stop request.
- Execution đã `STOPPING`: yêu cầu dừng đã được gửi; tiếp tục theo dõi trạng thái thay vì gửi lặp liên tục.
- Execution đang chạy: yêu cầu stop có thể được chấp nhận và trạng thái sẽ chuyển tiếp theo lifecycle.

Tên exception cụ thể và chữ ký API cần đối chiếu phiên bản Spring Batch đang dùng. Các API thường khai báo những exception như `NoSuchJobExecutionException` hoặc `JobExecutionNotRunningException`.

### Lấy execution ID đang chạy

`JobOperator.getRunningExecutions(jobName)` có thể trả về các execution ID đang chạy của một job. `JobExplorer` cũng cung cấp API đọc các `JobExecution` và trạng thái liên quan.

```java
Set<Long> runningIds = jobOperator.getRunningExecutions("dailyImportJob");

for (Long executionId : runningIds) {
    JobExecution execution = jobExplorer.getJobExecution(executionId);
    if (execution != null) {
        log.info("executionId={}, status={}",
                executionId, execution.getStatus());
    }
}
```

Không nên dùng tên job đơn thuần để stop nếu có nhiều execution đồng thời. Cần xác định đúng execution ID, có thể dựa vào business date, identifying parameters hoặc correlation ID.

## Theo dõi STOPPING cho tới STOPPED

Sau khi gửi stop request, operator nên đọc lại metadata để biết execution đã thực sự dừng chưa. Đối tượng `JobExecution` trong memory có thể là snapshot cũ; hãy truy vấn lại qua `JobExplorer` để lấy trạng thái mới nhất từ repository.

```java
JobExecution current = jobExplorer.getJobExecution(executionId);
if (current != null) {
    BatchStatus status = current.getStatus();
    ExitStatus exitStatus = current.getExitStatus();

    log.info("executionId={}, batchStatus={}, exitStatus={}",
            executionId, status, exitStatus.getExitCode());
}
```

Một API quản trị có thể trả về trạng thái `STOPPING` ngay sau khi yêu cầu được chấp nhận, rồi client tiếp tục polling hoặc nhận event khi execution đạt trạng thái cuối. Nên dùng timeout hữu hạn cho màn hình/API chờ; nếu hết thời gian mà execution vẫn `STOPPING`, hiển thị trạng thái đang dừng và cho phép người vận hành kiểm tra tiếp.

Không nên tự cập nhật `BATCH_JOB_EXECUTION.STATUS` bằng SQL để chuyển `STOPPING` thành `STOPPED`. Việc này bỏ qua lifecycle của step, transaction, thread và repository, có thể tạo metadata không khớp với công việc thực tế vẫn đang chạy.

## JobExecution và StepExecution sau khi stop

Job có thể gồm nhiều step. Khi stop được xử lý, step đang chạy thường kết thúc ở trạng thái `STOPPED`; những step đã hoàn thành trước đó vẫn giữ `COMPLETED`. Các step chưa bắt đầu không có `StepExecution` hoàn tất.

Ví dụ:

| Step | Trạng thái khi parent job dừng |
| --- | --- |
| `validateInputStep` | `COMPLETED` |
| `importOrdersStep` đang chạy | `STOPPED` sau khi nhận stop ở điểm an toàn |
| `summaryStep` chưa chạy | Chưa có execution hoặc chưa bắt đầu |

Job `JobExecution` kết thúc `STOPPED` khi flow được dừng theo yêu cầu. Khi điều tra, cần xem các step execution riêng để biết phần nào đã hoàn thành, phần nào dừng và phần nào chưa chạy.

Với split/parallel flow, nhiều branch có thể đang hoạt động. Tín hiệu stop cần được xử lý bởi các luồng liên quan; branch đang ở giữa transaction có thể cần đạt điểm an toàn. Một branch đã commit không bị rollback chỉ vì branch khác nhận stop. Cần quan sát tất cả `StepExecution` và output thực tế trước khi restart.

## Stop và transaction/checkpoint

Graceful stop được thiết kế để giữ checkpoint tại ranh giới xử lý hợp lệ. Với chunk step, chunk đã commit trước stop vẫn tồn tại; chunk hiện tại thường được hoàn tất rồi mới dừng nếu không phát sinh lỗi. Với tasklet, mỗi lần `execute` có transaction riêng; state nên được cập nhật cùng đơn vị công việc đã commit.

```text
Chunk 1: COMMIT -> checkpoint 100
Chunk 2: COMMIT -> checkpoint 200
Chunk 3: stop request tới khi đang chạy
         -> hoàn tất/rollback theo kết quả chunk
         -> nếu commit: checkpoint 300
         -> step STOPPED

Restart: tiếp tục từ checkpoint cuối cùng đã commit
```

Không nên hiểu stop là rollback toàn bộ step. Dữ liệu của các chunk trước đã commit vẫn được giữ. Nếu stop đến sau khi step đã hoàn thành nhưng trước khi job kết thúc hoàn toàn, trạng thái cuối phụ thuộc thời điểm tín hiệu được xử lý trong flow.

### Side effect ngoài transaction

Stop không thu hồi các side effect đã được hệ thống ngoài tiếp nhận. Ví dụ, processor đã gửi HTTP request hoặc writer đã publish message trước khi stop được xử lý. Nếu chunk sau đó rollback hoặc job dừng, request/message có thể vẫn tồn tại.

Hãy dùng idempotency key, transactional outbox, staging file hoặc quy trình publish sau khi step hoàn tất. Khi restart, cùng một item có thể được xử lý lại nếu output chưa được xác nhận trong transaction metadata; side effect phải an toàn khi lặp.

## Restart sau STOPPED

Một job dừng bởi operator thường có thể được restart nếu job được cấu hình restartable và trạng thái metadata cho phép. Restart tạo `JobExecution` mới cho cùng `JobInstance`, sử dụng identifying parameters của lần chạy trước.

Có thể restart qua `JobOperator.restart(executionId)` hoặc chạy lại job bằng `JobLauncher` với cùng identifying `JobParameters`, tùy cách ứng dụng vận hành.

```java
long newExecutionId = jobOperator.restart(stoppedExecutionId);
```

API restart có thể ném exception nếu execution không tồn tại, job không restartable, instance đã hoàn tất hoặc trạng thái không cho phép restart. Hãy xử lý lỗi vận hành thay vì tạo parameters mới để né trạng thái hiện tại.

### Identifying parameters phải ổn định

Ví dụ job được khởi chạy với:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceFile", "orders-2026-11-15.csv", true)
        .toJobParameters();
```

Khi restart, dùng cùng các identifying parameters. Không thêm timestamp hoặc UUID identifying mới chỉ để khởi chạy lại; điều đó tạo `JobInstance` mới và có thể làm job đọc/ghi lại toàn bộ dữ liệu từ đầu.

Nếu source file hoặc output resource có thể thay đổi, hãy lưu version/checksum hoặc dùng resource immutable để restart tiếp tục đúng dữ liệu ban đầu.

### Step nào chạy lại?

Restart không nhất thiết chạy lại toàn bộ job:

- Step đã `COMPLETED` thường được bỏ qua theo restart semantics.
- Step bị `STOPPED` có thể được restart từ checkpoint đã lưu nếu step/job cho phép.
- Step chưa bắt đầu sẽ được chạy khi flow đi tới nó.
- `allowStartIfComplete(true)` có thể khiến step đã hoàn thành được chạy lại trong một lần restart.
- `startLimit` và cấu hình restartability có thể giới hạn số lần step được bắt đầu.

Vì vậy, cần xác nhận hành vi restart của từng step, nhất là step có side effect ngoài transaction. Không nên giả định operator stop sẽ khiến toàn bộ job chạy lại từ đầu.

## Phân biệt stop, fail, abandon và kill process

Các trạng thái và thao tác này có ý nghĩa khác nhau:

| Thao tác/trạng thái | Ý nghĩa | Restart |
| --- | --- | --- |
| `JobOperator.stop` | Yêu cầu dừng graceful một execution đang chạy | Thường có thể restart nếu cấu hình cho phép |
| `STOPPING` | Yêu cầu dừng đang được xử lý | Chưa phải trạng thái cuối |
| `STOPPED` | Execution đã dừng có kiểm soát | Thường restart được |
| `FAILED` | Execution thất bại do exception hoặc lỗi | Có thể restart tùy job/step |
| `JobOperator.abandon` / `ABANDONED` | Đánh dấu execution bị bỏ, không tiếp tục theo restart thông thường | Không restart như execution stopped/failed thông thường |
| Kill JVM/container | Dừng process đột ngột, không phải graceful stop | Cần xử lý execution không hoàn tất và phục hồi theo metadata/resource |

Không dùng `ABANDONED` như một cách thay thế `STOPPED`. Abandon là quyết định vận hành khác, thường dùng khi execution không nên tiếp tục. Cũng không coi việc kill process là operator stop; transaction đang mở có thể rollback khi resource bị đóng, nhưng thread và side effect ngoài database không được kết thúc theo lifecycle graceful.

## Stop khi job chạy bất đồng bộ

Để operator có thể gửi stop từ một thread hoặc request khác trong khi job đang chạy, ứng dụng thường khởi chạy job bất đồng bộ bằng `TaskExecutorJobLauncher` hoặc cấu hình launcher tương ứng. Nếu launcher đồng bộ giữ thread gọi cho tới khi job kết thúc, request quản trị có thể cần một kênh độc lập để gọi stop.

Ví dụ cấu hình launcher với executor:

```java
@Bean
TaskExecutorJobLauncher jobLauncher(
        JobRepository jobRepository,
        @Qualifier("jobExecutor") TaskExecutor jobExecutor) throws Exception {

    TaskExecutorJobLauncher launcher = new TaskExecutorJobLauncher();
    launcher.setJobRepository(jobRepository);
    launcher.setTaskExecutor(jobExecutor);
    launcher.afterPropertiesSet();
    return launcher;
}
```

Executor này quyết định thread khởi chạy job. Nó khác executor truyền vào `FlowBuilder.split(...)`, vốn điều phối parallel flow bên trong job. Không nên dùng chung một pool nhỏ cho job launcher và các flow lồng nhau mà không đánh giá nguy cơ thread starvation.

Với launcher bất đồng bộ, `JobLauncher.run(...)` có thể trả về khi job vẫn đang chạy. Caller nhận `JobExecution`/ID để theo dõi; operator dùng ID đó gửi stop request sau này.

## Stop khi processor hoặc I/O bị chặn

Operator stop không thể bảo đảm ngắt ngay một lời gọi Java đang chạy. Nếu processor chờ HTTP response, reader chờ database query hoặc writer chờ broker acknowledgement, job có thể vẫn ở `STOPPING` cho tới khi thao tác trả về hoặc ném lỗi.

Để stop có thể hoàn tất trong thời gian hợp lý:

- Đặt connect/read/request timeout cho HTTP client.
- Đặt query timeout phù hợp cho database statement.
- Cấu hình timeout cho message receive/send và acknowledgement.
- Chia tasklet dài thành các đơn vị nhỏ có checkpoint.
- Tránh vòng lặp nội bộ dài không có điểm kiểm tra trạng thái.
- Không dùng interrupt tùy tiện nếu thao tác không hỗ trợ hủy an toàn.

Nếu ứng dụng tự xây dựng vòng lặp dài trong tasklet, có thể chủ động kiểm tra cờ dừng hoặc interruption theo thiết kế, nhưng cần bảo đảm transaction và checkpoint không bị bỏ dở. Không tự thay thế cơ chế stop của Spring Batch bằng một biến `volatile` không được đồng bộ với execution metadata.

## Parallel flow và partition khi stop

Trong split flow hoặc partitioned step, một job có thể có nhiều worker đang xử lý. Operator stop nhắm tới `JobExecution` cha; việc dừng thực tế cần các step/worker liên quan nhận tín hiệu và đạt điểm an toàn.

Các điểm cần lưu ý:

- Worker đang ở giữa chunk có thể hoàn tất transaction hiện tại trước khi dừng.
- Branch đã hoàn thành vẫn giữ trạng thái `COMPLETED` và dữ liệu đã commit.
- Branch đang chạy có thể chuyển sang `STOPPED` sau khi nhận tín hiệu.
- Remote partition worker cần cơ chế truyền trạng thái/điều phối stop phù hợp với transport và handler.
- Side effect ở hệ thống ngoài có thể vẫn tồn tại sau khi job dừng.

Không nên giả định một stop request lập tức giết mọi worker thread. Hãy kiểm tra `JobExecution`, từng `StepExecution`, trạng thái partition và log của worker. Khi dùng remote partitioning, phải kiểm thử cả việc master gửi stop và worker nhận/hoàn tất stop.

## Stop trong parent job có JobStep

Nếu parent job có `JobStep` khởi chạy child job, cần xác định ranh giới điều phối. Stop parent không nên được xem là lệnh kill process child. Child job có execution và metadata riêng; khả năng stop child phụ thuộc cách `JobStep`, launcher và child execution được điều phối.

Với mô hình parent/child, hãy quan sát cả parent `JobExecution`, parent `StepExecution` của `JobStep` và child `JobExecution`. Nếu nghiệp vụ yêu cầu dừng cả hai cấp, ứng dụng cần có quy trình rõ ràng để xác định child execution ID và gửi stop phù hợp, đồng thời chờ trạng thái cuối của child trước khi kết luận toàn bộ quy trình đã dừng.

Không tự suy ra child đã `STOPPED` chỉ từ việc parent chuyển `STOPPED`. Kiểm tra metadata child qua `JobExplorer` hoặc `JobOperator`.

## Stop và listener

Listener có thể được gọi trong quá trình step/job chuyển trạng thái sau stop. Ví dụ `StepExecutionListener.afterStep` có thể quan sát trạng thái cuối và trả về `ExitStatus` bổ sung theo quy tắc flow. Tuy nhiên, listener không nên giả vờ biến một stop thành completion bằng cách ghi đè trạng thái mà không có quy tắc nghiệp vụ.

Nếu cần gửi thông báo khi job được operator stop, có thể dùng `JobExecutionListener.afterJob` hoặc cơ chế giám sát bên ngoài để đọc `BatchStatus.STOPPED`. Notification nên idempotent vì restart hoặc callback/lifecycle có thể được quan sát lại trong quy trình vận hành.

Không nên dùng `afterJob` để thực hiện công việc cần rollback cùng các chunk trước đó; callback này diễn ra ở giai đoạn lifecycle khác và không phải transaction bao trùm job.

## Kiểm thử operator stop

Kiểm thử stop cần chạy job trên một thread riêng để test thread có thể gửi yêu cầu dừng trong khi execution đang hoạt động. Dùng latch/barrier để điều khiển thời điểm, tránh `Thread.sleep` và race condition.

Một test integration có thể thực hiện:

1. Cấu hình job launcher bất đồng bộ hoặc khởi chạy job bằng executor riêng trong test.
2. Dùng tasklet/processor test double báo hiệu qua `CountDownLatch` khi đã bắt đầu.
3. Chờ tín hiệu bắt đầu bằng timeout hữu hạn.
4. Lấy `JobExecution` ID.
5. Gọi `jobOperator.stop(executionId)`.
6. Theo dõi `JobExplorer` tới khi trạng thái đạt `STOPPED` hoặc timeout test.
7. Kiểm tra `ExitStatus`, các `StepExecution`, checkpoint và business data.

Ví dụ phần điều phối test:

```java
@Test
void operatorStopEndsExecutionAsStopped() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("testRunId", UUID.randomUUID().toString(), true)
            .toJobParameters();

    JobExecution started = jobLauncher.run(job, parameters);
    long executionId = started.getId();

    assertTrue(taskStarted.await(5, TimeUnit.SECONDS));

    assertTrue(jobOperator.stop(executionId));

    await().atMost(Duration.ofSeconds(10)).untilAsserted(() -> {
        JobExecution current = jobExplorer.getJobExecution(executionId);
        assertNotNull(current);
        assertEquals(BatchStatus.STOPPED, current.getStatus());
    });
}
```

Ví dụ giả định `jobLauncher` được cấu hình bất đồng bộ, `taskStarted` là latch được tasklet test đếm xuống, và test dùng Awaitility để chờ trạng thái cuối. Cần bảo đảm tasklet test có điểm kết thúc sau khi stop được xử lý; không tạo một vòng lặp vô hạn hoặc một I/O không có timeout.

### Kiểm thử trạng thái trung gian STOPPING

Có thể quan sát `STOPPING` ngay sau khi gửi stop, nhưng không nên bắt buộc test luôn thấy trạng thái này vì job có thể dừng rất nhanh và trạng thái trung gian tồn tại quá ngắn. Assertion bền vững hơn là:

- Stop request được chấp nhận khi execution đang chạy.
- Execution cuối cùng đạt `STOPPED` trong timeout.
- Step đang chạy dừng theo semantics đã thiết kế.
- Step đã hoàn thành trước đó vẫn giữ kết quả.

### Kiểm thử chunk boundary

Đặt latch trong processor hoặc writer để test gửi stop khi chunk đang chạy. Sau khi release latch, xác nhận chunk hiện tại hoàn tất hoặc rollback theo fixture, checkpoint không vượt qua dữ liệu chưa commit và step không bắt đầu chunk mới sau khi stop được xử lý.

Không dùng test dựa trên thời gian xử lý thực tế để đo chính xác thời điểm stop. Đồng bộ hóa tường minh giúp kiểm soát trạng thái của chunk.

### Kiểm thử restart sau STOPPED

Sau khi job dừng:

- Lấy execution mới nhất và xác nhận trạng thái `STOPPED`.
- Restart bằng cùng identifying parameters hoặc `JobOperator.restart` theo API.
- Xác nhận job tạo `JobExecution` mới cho cùng `JobInstance`.
- Xác nhận step đã hoàn thành được xử lý theo restart policy, step stopped tiếp tục từ checkpoint.
- Đối chiếu business data để tránh duplicate/missing output.

### Kiểm thử stop không thể hoàn tất nhanh

Có thể mô phỏng một thao tác I/O có timeout dài hơn thời gian chờ test để xác nhận execution vẫn ở `STOPPING` trong lúc thao tác chưa trả về. Sau đó giải phóng thao tác hoặc để timeout xảy ra và xác nhận job đạt trạng thái cuối. Test cần cleanup thread/executor ngay cả khi assertion thất bại.

## Các lỗi vận hành thường gặp

### Thấy stop API trả true rồi báo job đã dừng

API xác nhận yêu cầu được chấp nhận; execution có thể vẫn `STOPPING`. Đọc lại trạng thái qua `JobExplorer` cho tới khi `STOPPED` hoặc trạng thái cuối khác.

### Dùng sai ID

`JobOperator.stop` cần `JobExecution ID`, không phải job instance ID hoặc step execution ID. Lấy ID từ lần launch hoặc `JobExplorer`.

### Mong stop ngắt processor ngay lập tức

Framework thường dừng ở điểm an toàn. Processor hoặc I/O bị chặn lâu sẽ làm thời gian dừng kéo dài. Đặt timeout và chia nhỏ công việc.

### Nhầm STOPPED với FAILED

`STOPPED` là kết quả của dừng có kiểm soát; `FAILED` phản ánh lỗi thực thi. Kiểm tra `BatchStatus`, `ExitStatus` và failure exceptions.

### Nhầm STOPPED với ABANDONED

Abandon là quyết định không tiếp tục execution theo restart semantics thông thường. Dùng stop cho graceful stop và chỉ abandon theo quy trình vận hành có chủ đích.

### Nghĩ toàn bộ dữ liệu đã rollback

Các chunk đã commit vẫn tồn tại. Kiểm tra checkpoint và business data trước khi restart hoặc chạy lại.

### Không theo dõi child/worker execution

Parent, child job, parallel flow hoặc remote worker có metadata riêng. Quan sát tất cả cấp liên quan trước khi kết luận toàn bộ quy trình đã dừng.

### Restart bằng parameters mới

Identifying parameters mới tạo `JobInstance` mới và có thể chạy lại từ đầu. Restart cùng logical job cần giữ identifying parameters ổn định.

## Nguyên tắc thiết kế graceful stop

Khi triển khai chức năng operator stop trong production, hãy xác định:

1. Người vận hành lấy đúng `JobExecution ID` từ đâu?
2. Quyền nào được phép gửi stop request?
3. API phản hồi phân biệt request accepted với execution stopped như thế nào?
4. Chunk/tasklet có điểm dừng an toàn và thời gian xử lý hữu hạn không?
5. Các lời gọi database, HTTP, broker có timeout phù hợp không?
6. Reader/writer có checkpoint để restart không?
7. Side effect ngoài transaction có idempotency hoặc outbox không?
8. Parallel branch, partition worker và child job được theo dõi/dừng ra sao?
9. Job restart có dùng cùng identifying parameters không?
10. Monitoring có cảnh báo execution ở `STOPPING` quá lâu không?

Một chức năng stop tốt nên có ba bước rõ ràng: gửi yêu cầu qua `JobOperator`, theo dõi trạng thái cho tới khi execution dừng thật sự, rồi cung cấp thông tin restart dựa trên checkpoint và identifying parameters. Không sửa trực tiếp metadata để ép trạng thái; hãy để Spring Batch hoàn tất lifecycle của step/job.

## Ghi nhớ

Operator dùng `JobOperator.stop(jobExecutionId)` để yêu cầu dừng một lần chạy cụ thể. Trạng thái thường đi từ `STARTED` sang `STOPPING`, rồi `STOPPED` khi step xử lý tín hiệu ở điểm an toàn. Stop là cooperative/graceful: chunk hiện tại hoặc lần `Tasklet.execute` hiện tại thường cần hoàn tất hoặc rollback trước khi step dừng; processor và I/O bị chặn lâu có thể kéo dài thời gian. `STOPPING` chưa phải trạng thái cuối và API accepted không đồng nghĩa job đã dừng. Các chunk đã commit vẫn tồn tại; restart thường dùng cùng identifying parameters và checkpoint đã lưu. Phân biệt `STOPPED` với `FAILED`, `ABANDONED` và kill process; với parallel flow hoặc parent/child job, kiểm tra mọi execution liên quan thay vì chỉ nhìn trạng thái parent.
