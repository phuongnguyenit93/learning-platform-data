# JobOperator và thao tác điều khiển trong Spring Batch

## 1. JobOperator giải quyết bài toán gì?

Trong hệ thống xử lý batch, khởi chạy một Job chỉ là bước đầu tiên. Khi đưa Job vào vận hành, người quản trị hoặc một bộ lập lịch còn cần biết Job nào đang chạy, chủ động dừng một lần chạy, tiếp tục công việc bị lỗi, bắt đầu lô kế tiếp hoặc xử lý một execution bị kẹt sau sự cố máy chủ.

`JobOperator` là API điều khiển vòng đời Job của **Spring Batch**. Nó phối hợp với hạ tầng metadata để thực hiện các thao tác ở mức Job, thay vì gọi trực tiếp từng Tasklet, ItemReader, ItemProcessor hoặc ItemWriter.

Sau bài này, bạn có thể:

- Phân biệt `start`, `restart` và `startNextInstance`.
- Hiểu vì sao `stop` là yêu cầu **dừng có kiểm soát** chứ không phải lệnh ngắt thread tức thì.
- Xử lý `FAILED`, `STOPPED`, `ABANDONED` và tình huống execution còn `STARTED` sau khi tiến trình chết.
- Đọc trạng thái từ `JobRepository` và nhận biết khác biệt giữa `BatchStatus` và `ExitStatus`.
- Triển khai một lớp điều khiển Job bằng **Spring Batch 6.x**, đồng thời chuyển đổi tư duy sang các API của **Spring Batch 5.2.x**.
- Thiết kế thao tác điều hành an toàn trong ứng dụng có scheduler, HTTP API và nhiều worker.

## 2. JobOperator trong kiến trúc Spring Batch

~~~text
Scheduler / REST Admin / CLI / JMX
                   |
                   v
              JobOperator
                   |
        +----------+-----------+
        |          |           |
        v          v           v
   JobRegistry  JobRepository  Job / Steps
    (Job nào     (Metadata,     (Thực hiện
    có thể chạy)  checkpoint)    nghiệp vụ)
                   |
                   v
             BATCH_* tables
                   |
                   v
             JobExecution
              StepExecution
             ExecutionContext
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm |
| --- | --- |
| `Job` | Định nghĩa công việc và luồng Step. |
| `JobOperator` | Điều khiển chạy mới, khởi động lại, dừng, bỏ qua hoặc phục hồi execution tùy API phiên bản. |
| `JobRepository` | Lưu và truy vấn JobInstance, JobExecution, StepExecution, trạng thái và checkpoint. |
| `JobRegistry` | Quản lý các định nghĩa Job có sẵn theo tên, hỗ trợ điều khiển nhiều Job. |
| `JobParameters` | Thông tin đầu vào, trong đó các tham số `identifying` xác định danh tính JobInstance. |
| `JobExecution` | Một lần cố gắng thực thi JobInstance; lưu ID, trạng thái, thời gian và lỗi. |
| `ExecutionContext` | Trạng thái cần lưu giữa các execution, đặc biệt khi restart Step. |

**Khác biệt giữa hai dòng phiên bản quan trọng:**

- **Spring Batch 5.2.x:** `JobOperator` được thiết kế như giao diện điều hành dùng tên Job, execution ID và dữ liệu đơn giản; ví dụ `start(String, Properties)`, `restart(long)`, `stop(long)`. `JobLauncher` là API riêng thường dùng để khởi chạy Job từ code ứng dụng.
- **Spring Batch 6.x:** `JobOperator` còn **extends `JobLauncher`** và hỗ trợ các thao tác có kiểu mạnh: `start(Job, JobParameters)`, `restart(JobExecution)`, `stop(JobExecution)`, `abandon(JobExecution)`, `startNextInstance(Job)`. Các hàm cũ nhận ID hoặc tên Job có thể còn hiện diện nhưng đã bị **deprecated**. Những truy vấn metadata nên thực hiện qua `JobRepository` và danh sách Job qua `JobRegistry`.

Vì các API khác nhau, phần ví dụ Java chính bên dưới chọn **Spring Batch 6.x**, còn phần cuối chỉ rõ cách áp dụng trên 5.2.

## 3. Hiểu danh tính trước khi điều khiển Job

Để vận hành đúng, phải phân biệt **JobInstance** và **JobExecution**.

~~~text
Job name = importOrders
Identifying JobParameters = businessDate: 2026-11-16
                       |
                       v
                 JobInstance #52
                    /       \
                   v         v
      JobExecution #400   JobExecution #401
         FAILED               COMPLETED
         lần đầu              restart
~~~

Với cùng tên Job và cùng **tập identifying JobParameters**, Spring Batch xác định cùng một JobInstance. Lần restart tạo JobExecution mới cho JobInstance cũ, không tạo lô dữ liệu mới.

Ví dụ:

~~~java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
~~~

`businessDate` là tham số định danh; `requestedBy` chỉ là metadata đầu vào không định danh. Thay đổi `businessDate` có nghĩa là yêu cầu xử lý một JobInstance khác. Thay đổi một tham số không định danh không làm khác identity của JobInstance, nhưng vẫn phải xem các ràng buộc nghiệp vụ của Job.

**Không thêm timestamp hoặc `run.id` định danh tùy tiện vào lần restart.** Làm vậy tạo JobInstance mới và có thể chạy lại dữ liệu đã xử lý trước đó. Khi muốn tiếp tục cùng lô thất bại, hãy dùng API `restart` trên execution phù hợp.

## 4. Các thao tác chính của JobOperator

| Thao tác | Mục đích | Kết quả hoặc giới hạn quan trọng |
| --- | --- | --- |
| `start(Job, JobParameters)` (6.x) | Bắt đầu xử lý theo Job và tham số. | Trả về `JobExecution`; trường hợp có tham số/job instance trùng có thể bị từ chối hoặc đi theo chính sách hiện có. |
| `startNextInstance(Job)` | Bắt đầu JobInstance **mới** theo `JobParametersIncrementer`. | Dùng khi cần lô tiếp theo, **không** thay cho restart lô lỗi. |
| `restart(JobExecution)` | Tiếp tục JobInstance từ một execution `FAILED` hoặc `STOPPED`. | Sinh JobExecution mới; chỉ thành công nếu Job cho restart và metadata hợp lệ. |
| `stop(JobExecution)` | Gửi yêu cầu dừng Job đang chạy. | Trả về việc tín hiệu đã được chấp nhận; trạng thái có thể còn `STOPPING` trước khi sang `STOPPED`. |
| `abandon(JobExecution)` | Đánh dấu execution không còn được tiếp tục. | Sau khi thành `ABANDONED`, framework không restart execution này. |
| `recover(JobExecution)` (6.x) | Phục hồi metadata của execution bị kẹt `STARTED` sau shutdown đột ngột. | Đánh dấu `FAILED` và bổ sung cờ phục hồi để có thể restart khi an toàn. |
| Đọc `JobRepository` / `JobRegistry` | Kiểm trạng thái, lịch sử và Job đã đăng ký. | Trong 6.x nên ưu tiên các API này thay các hàm `get...` cũ trên JobOperator. |

Điều khiển Job là **thao tác trên trạng thái có lưu trữ**. Nếu database chứa các bảng `BATCH_*` mất dữ liệu, JobOperator không thể tự suy ra checkpoint còn lại từ các bảng nghiệp vụ.

## 5. Trạng thái BatchStatus và luồng điều khiển

`BatchStatus` mô tả trạng thái kỹ thuật của một execution.

| Trạng thái | Ý nghĩa | Hành động thường gặp |
| --- | --- | --- |
| `STARTING` | Framework đang chuẩn bị chạy. | Theo dõi; chưa gửi một lệnh chạy trùng. |
| `STARTED` | Execution đang hoạt động. | Theo dõi hoặc yêu cầu stop nếu cần. |
| `STOPPING` | Đã gửi yêu cầu dừng, nhưng Job chưa kết thúc. | Chờ trạng thái terminal; không restart vội. |
| `STOPPED` | Đã dừng có kiểm soát. | Có thể restart nếu Job cho phép. |
| `FAILED` | Execution kết thúc do lỗi. | Phân tích nguyên nhân, sửa dữ liệu/điều kiện và restart. |
| `COMPLETED` | Execution đã hoàn tất. | Không restart cùng JobInstance đã hoàn thành. |
| `ABANDONED` | Execution đã bị từ bỏ. | Không restart bằng cơ chế thông thường. |
| `UNKNOWN` | Metadata không xác định được trạng thái tin cậy. | Điều tra trước mọi thay đổi. |

Luồng phổ biến:

~~~text
               start
                 |
                 v
              STARTING
                 |
                 v
               STARTED
              /   |   \
             /    |    \
       success   error  stop request
           |      |          |
           v      v          v
        COMPLETED FAILED   STOPPING
                                 |
                                 v
                              STOPPED

    FAILED / STOPPED -- restart --> STARTING (execution mới)
    ABANDONED ---------X--------> restart
~~~

Cần phân biệt **`BatchStatus`** và **`ExitStatus`**:

- `BatchStatus` cho biết trạng thái vòng đời execution do framework quản lý.
- `ExitStatus` cho phép Step/Job phát tín hiệu kết thúc chi tiết hơn, chẳng hạn mã `COMPLETED WITH SKIPS` hoặc mã điều khiển flow được định nghĩa riêng.
- Một Job có `BatchStatus.COMPLETED` vẫn có thể có `ExitStatus` tùy biến; hệ thống điều hành không nên suy luận từ chuỗi exit code mà bỏ qua BatchStatus.

Trong HTTP endpoint hoặc dashboard, nên hiển thị cả status, exit code, execution ID, thời điểm bắt đầu/kết thúc và tóm tắt lỗi nếu có. Không dùng một giá trị boolean `running` duy nhất để mô tả tất cả trạng thái.

## 6. Thao tác start: bắt đầu Job

Với Spring Batch 6.x, kiểu API chủ đạo:

~~~java
JobExecution execution = jobOperator.start(importOrdersJob, params);
long executionId = execution.getId();
~~~

Trong đó:

- `importOrdersJob` là bean Job đã được cấu hình.
- `params` là JobParameters hợp lệ với validator của Job.
- `executionId` dùng để tra cứu và điều khiển **đúng lần chạy**; không nên điều khiển bằng cách lấy một execution ngẫu nhiên trong tất cả Job đang chạy.

**Chú ý khi dùng `JobParametersIncrementer`:** theo Javadoc Spring Batch 6, nếu Job định nghĩa incrementer, `start(Job, JobParameters)` có thể tính bộ tham số tiếp theo bằng incrementer và bỏ qua bộ tham số được truyền. Vì vậy, nếu nghiệp vụ yêu cầu điều khiển chính xác theo ngày xử lý, cần hiểu rõ cấu hình incrementer của Job và cách chọn tham số. Ví dụ `start` dùng businessDate ở đây giả định Job **không** gắn incrementer.

### Chạy đồng bộ và bất đồng bộ

Một Job có thể chạy ngay trên thread đang gọi hoặc được gửi sang `TaskExecutor`. Vì vậy thời điểm `start` trả về **không nhất thiết** là thời điểm Job đã hoàn tất:

~~~text
Synchronous execution:
request --> start --> Job chạy --> COMPLETED/FAILED --> response

Asynchronous execution:
request --> start --> JobExecution ID --> response
                   |
                   +--> TaskExecutor --> Job chạy --> trạng thái cuối
~~~

Trong Spring Batch 6, `TaskExecutorJobOperator` hỗ trợ thực thi qua TaskExecutor. Với executor đồng bộ, thao tác start có thể chặn tới khi Job chạy xong. Với executor bất đồng bộ, phản hồi có thể trả về trong lúc Job còn `STARTING` hoặc `STARTED`. Hãy cấu hình executor phù hợp với kiến trúc ứng dụng và **luôn kiểm tra lại trạng thái qua JobRepository** khi cần kết quả cuối.

Đối với một REST API khởi chạy bất đồng bộ, phản hồi hợp lý là **202 Accepted** cùng execution ID và URL theo dõi. Đừng trả “Job đã thành công” chỉ vì API `start` không ném exception.

## 7. Thao tác startNextInstance: tạo lô mới

`startNextInstance` sử dụng `JobParametersIncrementer` gắn với Job để sinh identifying parameters mới.

Ví dụ: một Job xử lý nhiều lô thử nghiệm liên tiếp và dùng `run.id` phân biệt các JobInstance:

~~~java
@Bean
Job demoJob(JobRepository repository, Step loadStep) {
    return new JobBuilder("demoJob", repository)
            .incrementer(new RunIdIncrementer())
            .start(loadStep)
            .build();
}
~~~

Khi Job đã có incrementer phù hợp:

~~~java
JobExecution next = jobOperator.startNextInstance(demoJob);
~~~

Phương thức này tạo **JobInstance mới** theo bộ tham số tiếp theo, kể cả khi instance trước đó thất bại. Nó không khôi phục trạng thái instance đã lỗi.

| Tình huống | Nên làm |
| --- | --- |
| Job ngày 16/11 bị lỗi sau khi ghi một phần dữ liệu | `restart` execution lỗi sau khi xử lý nguyên nhân. |
| Đã hoàn thành Job ngày 16/11, muốn chạy lô ngày 17/11 | `start` với businessDate mới hoặc `startNextInstance` nếu incrementer biết cách sinh ngày kế tiếp. |
| Job thí nghiệm cần chạy phiên tiếp theo `run.id=42` | `startNextInstance` với incrementer tăng run.id. |
| Dữ liệu cũ thất bại nhưng gọi startNextInstance để “khắc phục” | Nguy cơ tạo lô mới và ghi lại dữ liệu; cần kiểm soát duplicate/idempotency. |

Incrementer là **chiến lược nghiệp vụ**. Tăng run.id chỉ tạo danh tính mới, không làm dữ liệu nguồn tự thay đổi. Nếu Job thực sự xử lý theo ngày, cần incrementer theo ngày nghiệp vụ hoặc truyền businessDate rõ ràng.

## 8. Thao tác restart: tiếp tục JobInstance cũ

Khi JobExecution thứ nhất bị `FAILED` hoặc `STOPPED`, JobOperator có thể tạo một execution mới trong **cùng JobInstance**:

~~~java
JobExecution previous = jobRepository.getJobExecution(failedExecutionId);

if (previous == null) {
    throw new IllegalArgumentException("Unknown execution");
}

JobExecution retried = jobOperator.restart(previous);
~~~

Quá trình restart dựa vào metadata đã lưu trong `JobRepository`, bao gồm `ExecutionContext` của các Step có trạng thái khôi phục được. Theo mặc định, Step đã `COMPLETED` thường được bỏ qua khi restart; Step lỗi hoặc dừng sẽ được chạy tiếp theo logic Job/Step. Có ngoại lệ khi Step dùng `allowStartIfComplete(true)` hoặc cấu hình flow đặc biệt.

### Ví dụ checkpoint

Giả sử Job đọc 5 item và commit theo chunk 2 item:

~~~text
Execution #101:
  Item 1,2  -> COMMIT
  Item 3    -> lỗi trong processor
  Job       -> FAILED

Execution #102 sau restart:
  Mở reader từ checkpoint đã lưu
  Item 3,4  -> COMMIT
  Item 5    -> COMMIT
  Job       -> COMPLETED
~~~

Một Job restart đúng phải đảm bảo dữ liệu cuối cùng đủ, không ghi trùng; `JobExecution` mới có ID khác nhưng cùng `JobInstance` với lần đầu.

**Không coi restart là đảm bảo exactly-once ở mọi hệ thống.** Nếu writer gọi API, gửi email hoặc message broker nằm ngoài transaction metadata, side effect có thể đã thành công trước khi Job fail. Nên có idempotency key, unique constraint, outbox hoặc đối soát nếu kết quả phụ thuộc hệ thống khác.

### Những điều khiến restart thất bại

- Job đã hoàn thành với identifying JobParameters đó.
- Job được cấu hình không cho restart, chẳng hạn `preventRestart()`.
- JobExecution đang chạy hoặc đang trong quá trình `STOPPING`.
- Metadata hoặc ExecutionContext bị xóa, hỏng hoặc không còn phù hợp phiên bản code.
- Job cần khôi phục không còn được định nghĩa/đăng ký theo tên tương ứng.
- Một Step vượt `startLimit` hoặc gặp cấu hình bất tương thích khi restart.
- Execution đã `ABANDONED`.

Khi restart thất bại, phải đọc exception, trạng thái lưu trong JobRepository và lịch sử Step trước khi thử tiếp. Việc sinh identifying parameter mới có thể tạo JobInstance khác và che mất lỗi thực sự.

## 9. Thao tác stop: dừng có kiểm soát

Khi gọi:

~~~java
JobExecution running = jobRepository.getJobExecution(executionId);
boolean accepted = jobOperator.stop(running);
~~~

`accepted == true` chỉ xác nhận **tín hiệu dừng đã được gửi/chấp nhận**. Nó không chứng minh rằng Job đã kết thúc. Trong lúc framework xử lý tín hiệu, trạng thái có thể lần lượt là:

~~~text
STARTED -> STOPPING -> STOPPED
             |
             +-- reader / tasklet / writer hiện tại
                 có thể vẫn đang thực thi
~~~

Spring Batch thường chỉ kiểm tra tín hiệu stop tại những điểm framework lấy lại quyền điều khiển, chẳng hạn giữa các iteration/chunk hoặc sau khi Tasklet trả về. Nếu code nghiệp vụ đang gọi API mạng bị treo, chạy câu SQL dài hoặc chặn thread, Job có thể chưa dừng ngay. `stop` không tương đương `Thread.stop()`, `kill -9` hoặc rollback mọi side effect đã xảy ra.

Khi yêu cầu stop từ giao diện điều hành:

1. Lấy **đúng JobExecution ID** đang chạy.
2. Gọi `stop`; trả về “đã nhận yêu cầu” hoặc trạng thái `STOPPING` nếu có.
3. Tra cứu lại JobRepository sau đó (qua lịch kiểm tra, event hoặc endpoint status) cho đến trạng thái terminal như `STOPPED`.
4. Chỉ cho phép restart sau khi chắc chắn execution cũ đã dừng, dữ liệu đã commit/rollback ở trạng thái nhất quán.

Nếu cần dừng nhanh, hãy thiết kế Tasklet/reader/processor có timeout, đáp ứng interruption hoặc tự chia việc thành chunk ngắn; không cố giải quyết bằng cách buộc JobOperator giết luồng.

### Điều gì xảy ra với dữ liệu đã commit?

`stop` là dừng có kiểm soát, **không phải thao tác undo**. Các chunk đã commit vẫn còn. Khi restart, Step được thiết kế restartable có thể tiếp tục từ checkpoint. Với writer không hỗ trợ giao dịch hoặc side effect bên ngoài, phải có phương án idempotency.

## 10. Thao tác abandon: kết thúc không tiếp tục

`abandon` đánh dấu một JobExecution là `ABANDONED`. Framework không cho restart execution thuộc trường hợp đã bị bỏ qua theo chính sách này.

~~~java
JobExecution stale = jobRepository.getJobExecution(executionId);

// Chỉ thực hiện sau khi xác nhận execution không còn chạy.
JobExecution abandoned = jobOperator.abandon(stale);
~~~

Tình huống phù hợp là một lần xử lý không thể/không được tiếp tục theo quyết định vận hành, ví dụ dữ liệu nguồn đã hủy và phải xử lý bằng JobInstance khác có kiểm soát. Đây là quyết định nghiệp vụ có hệ quả, không phải bước cleanup mặc định.

**Không gọi abandon trên execution còn thực sự chạy.** API từ chối khi coi execution đang chạy; khi process đã chết nhưng metadata còn `STARTED` cần xử lý trạng thái theo quy trình phục hồi trước. Không dùng abandon như một cách “xóa lỗi” để dashboard trông sạch hơn. Dữ liệu nghiệp vụ đã ghi trước đó không tự bị đảo ngược.

Ngoài JobExecution, Spring Batch còn dùng `ABANDONED` ở mức **StepExecution** trong các trường hợp điều khiển flow và restart. Phải phân biệt đối tượng đang được thao tác, tránh suy luận một Step bị abandoned đồng nghĩa toàn bộ Job đã bị abandon.

## 11. Thao tác recover trong Spring Batch 6.x

Nếu JVM chết đột ngột, database hoặc container bị ngắt nguồn, có thể không có cơ hội cập nhật metadata từ `STARTED` sang `FAILED` hoặc `STOPPED`. Khi đó JobRepository vẫn thấy một execution có vẻ đang chạy, mặc dù process thực đã biến mất.

Spring Batch 6 bổ sung:

~~~java
JobExecution stuck = jobRepository.getJobExecution(executionId);

// Đã xác nhận process cũ thật sự dừng và checkpoint an toàn.
JobExecution recovered = jobOperator.recover(stuck);

// Sau đó mới quyết định chạy lại.
JobExecution resumed = jobOperator.restart(recovered);
~~~

Theo API 6.x, `recover` đánh dấu execution kẹt `STARTED` thành `FAILED` và ghi dấu `recovered=true` trong execution context để phục vụ khả năng restart.

**Các điều kiện trước khi recover:**

- Xác minh tiến trình/worker sở hữu execution **không còn chạy**; xem trạng thái pod, process, node, heartbeat hoặc lease đáng tin cậy.
- Xác nhận thao tác ghi dữ liệu của execution cũ đã kết thúc hoặc được xử lý nhất quán; tránh chạy song song cùng một JobInstance.
- Kiểm tra checkpoint và tác động ngoài transaction; các yêu cầu đã gửi sang hệ thống khác có thể đã thành công.
- Quyết định liệu phải restart cùng instance, abandon, hay khởi tạo quy trình đối soát thủ công.
- Lưu lại người thực hiện, lý do và execution ID cho audit.

`recover` không tự sửa dữ liệu nghiệp vụ, không đảo ngược một HTTP call đã hoàn thành, cũng không đảm bảo checkpoint an toàn nếu thiết kế writer không idempotent.

### Shutdown hook trong Spring Batch 6

Spring Batch 6 có `JobExecutionShutdownHook` để cố gắng gửi yêu cầu dừng khi JVM shutdown có kiểm soát:

~~~java
Thread hook = new JobExecutionShutdownHook(
        jobExecution, jobOperator);
Runtime.getRuntime().addShutdownHook(hook);
~~~

Hook này giúp trong các kịch bản shutdown mà JVM cho phép hook chạy. Nó không thể đảm bảo hoạt động khi process bị kill cưỡng bức (ví dụ SIGKILL), kernel panic hoặc mất điện. Đây là biện pháp hỗ trợ, không thay cho kế hoạch recovery và idempotency.

## 12. Ví dụ lớp điều khiển bằng Spring Batch 6.x

Ví dụ dưới đây giả định:

- Spring context đã có bean `JobOperator` và **JDBC JobRepository** phù hợp.
- Có Job bean tên `importOrdersJob`; Job này **không gắn JobParametersIncrementer** để `businessDate` được dùng như tham số định danh do người gọi cung cấp.
- Người gọi đã được xác thực và kiểm tra quyền thực hiện trước khi vào service. Ví dụ là lớp service, không phải REST endpoint.

**BatchControlService.java**:

~~~java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.JobExecution;
import org.springframework.batch.core.job.parameters.JobParameters;
import org.springframework.batch.core.job.parameters.JobParametersBuilder;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;

@Service
public class BatchControlService {

    private final JobOperator jobOperator;
    private final JobRepository jobRepository;
    private final Job importOrdersJob;

    public BatchControlService(
            JobOperator jobOperator,
            JobRepository jobRepository,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobOperator = jobOperator;
        this.jobRepository = jobRepository;
        this.importOrdersJob = importOrdersJob;
    }

    // Chạy lô được xác định bởi ngày nghiệp vụ.
    public JobExecution startForDate(String businessDate) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .toJobParameters();

        return jobOperator.start(importOrdersJob, parameters);
    }

    // Trả lại trạng thái đã được lưu (có thể thay đổi sau lời gọi).
    public BatchStatus status(long executionId) {
        return requireExecution(executionId).getStatus();
    }

    // Gửi yêu cầu stop; boolean không đồng nghĩa đã STOPPED.
    public boolean requestStop(long executionId) throws Exception {
        JobExecution execution = requireExecution(executionId);
        return jobOperator.stop(execution);
    }

    // Tạo JobExecution mới trong cùng JobInstance thất bại/đã dừng.
    public JobExecution restart(long executionId) throws Exception {
        JobExecution execution = requireExecution(executionId);
        BatchStatus status = execution.getStatus();

        if (status != BatchStatus.FAILED
                && status != BatchStatus.STOPPED) {
            throw new IllegalStateException(
                "Restart requires FAILED or STOPPED: " + status);
        }

        return jobOperator.restart(execution);
    }

    // Chỉ được gọi sau khi xác minh không còn worker đang thực thi.
    public JobExecution recoverAfterCrash(long executionId) {
        JobExecution execution = requireExecution(executionId);

        if (execution.getStatus() != BatchStatus.STARTED) {
            throw new IllegalStateException(
                "Recovery requires stale STARTED execution");
        }

        return jobOperator.recover(execution);
    }

    // Quyết định từ bỏ một execution đã hết khả năng tiếp tục.
    public JobExecution abandon(long executionId) throws Exception {
        JobExecution execution = requireExecution(executionId);
        return jobOperator.abandon(execution);
    }

    private JobExecution requireExecution(long executionId) {
        JobExecution execution = jobRepository.getJobExecution(executionId);
        if (execution == null) {
            throw new IllegalArgumentException(
                "Unknown JobExecution: " + executionId);
        }
        return execution;
    }
}
~~~

**Đọc đúng ví dụ:**

- `startForDate` phù hợp với Job có identity theo businessDate. Tránh thiết kế khiến mỗi request tạo `run.id` ngẫu nhiên khi nghiệp vụ cần chặn lô trùng.
- `status` đọc lại từ JobRepository; một đối tượng `JobExecution` từng được trả về có thể đã lỗi thời nếu Job đang thực thi bất đồng bộ.
- `requestStop` trả về **kết quả gửi tín hiệu**. Client phải có cơ chế kiểm lại để biết Job đã chuyển sang `STOPPED` hay chưa.
- `restart` kiểm tra trạng thái trước để tạo thông báo dễ hiểu. Việc xác minh thật sự vẫn thuộc framework, vì trạng thái có thể thay đổi giữa lần đọc và lời gọi (race condition).
- `recoverAfterCrash` chỉ kiểm kỹ thuật trạng thái `STARTED`. Việc xác minh worker cũ đã chết và dữ liệu an toàn **phải được thực hiện ở tầng điều hành** trước khi gọi phương thức này.
- `abandon` là thao tác có hệ quả; nên đặt sau bước phê duyệt/quy trình vận hành thích hợp nếu ứng dụng yêu cầu.
- Các phương thức `throws Exception` nhằm giữ ví dụ gọn; code thực nên ánh xạ từng nhóm lỗi Batch thành phản hồi nghiệp vụ có cấu trúc.

### Nếu cần chọn Job theo tên

Trong hệ thống có nhiều Job, không nên lấy một bean Job tùy ý từ ApplicationContext. Hãy dùng `JobRegistry` để xác định Job đã đăng ký và dùng `JobRepository` để biết JobExecution hiện có.

Ở Spring Batch 6, các phương thức query `JobOperator.getJobNames()`, `getRunningExecutions(String)`, `getSummary(long)` và những phương thức tra cứu cũ đã bị deprecated; có thể dùng:

~~~java
// Các Job đang đăng ký, có thể dùng để khởi chạy:
var registeredNames = jobRegistry.getJobNames();

// Các JobExecution đang chạy theo metadata:
var running = jobRepository.findRunningJobExecutions("importOrdersJob");

// Tra cứu một execution từ ID:
var execution = jobRepository.getJobExecution(executionId);

// Lịch sử execution của một JobInstance:
var history = jobRepository.getJobExecutions(execution.getJobInstance());
~~~

Tùy sơ đồ triển khai, danh sách Job **đã đăng ký** có thể khác danh sách Job **từng chạy và có metadata**. Một Job có lịch sử trong database nhưng code/bean đã bị gỡ không nhất thiết khởi chạy lại được chỉ từ metadata.

## 13. Điều khiển từ REST API hoặc scheduler

Một ứng dụng quản trị có thể cung cấp tập endpoint như sau (chỉ là thiết kế giao diện, chưa phải controller hoàn chỉnh):

| HTTP | Đường dẫn ví dụ | Ý nghĩa | Phản hồi phù hợp |
| --- | --- | --- | --- |
| `POST` | `/admin/batch/jobs/import-orders/executions` | Start Job với businessDate. | 202 + executionId nếu bất đồng bộ; báo trạng thái thật khi đồng bộ. |
| `GET` | `/admin/batch/executions/{id}` | Đọc BatchStatus, ExitStatus, thời gian, lỗi. | 200 và dữ liệu đã đọc từ repository. |
| `POST` | `/admin/batch/executions/{id}/stop` | Gửi stop. | 202 / thông báo “đã nhận yêu cầu”; tiếp tục polling. |
| `POST` | `/admin/batch/executions/{id}/restart` | Restart execution FAILED/STOPPED. | 202 + executionId mới nếu xử lý bất đồng bộ. |
| `POST` | `/admin/batch/executions/{id}/abandon` | Đánh dấu từ bỏ. | Chỉ cho phép khi policy đồng ý và execution không chạy. |
| `POST` | `/admin/batch/executions/{id}/recover` | Phục hồi metadata bị kẹt. | Chỉ cho vai trò vận hành có quyền và sau xác minh worker đã chết. |

Một số quy tắc nên thiết kế ngay từ đầu:

1. **Xác thực và phân quyền** cho mọi thao tác thay đổi trạng thái. Quyền xem execution có thể rộng hơn quyền stop/restart/abandon/recover.
2. **Ghi audit log** với người gọi, Job name, execution ID, lý do, timestamp và kết quả. Không in dữ liệu nhạy cảm trong JobParameters ra log.
3. **Không dựa vào status vừa đọc làm khóa chống tranh chấp.** Hai admin có thể cùng nhấn restart; framework và database metadata phải là nơi bảo vệ trạng thái nhất quán.
4. **Định nghĩa chính sách trùng request.** Cùng businessDate không nên tạo nhiều JobInstance nếu nghiệp vụ chỉ cho phép một lô. HTTP retry cần idempotency.
5. **Trả lỗi rõ nghĩa.** Execution không tồn tại có thể ánh xạ thành 404; trạng thái không hợp lệ hoặc xung đột JobInstance thành 409; lỗi hạ tầng được ghi nhận tách với lỗi nghiệp vụ.
6. **Không mở endpoint kill thread theo Job ID.** Stop là thao tác điều khiển hợp tác; kill process là công việc cấp hạ tầng với hậu quả khác.

### Scheduler trong môi trường nhiều instance

Nếu nhiều node cùng điều khiển Job, tất cả phải dùng metadata store chung và cấu hình tương thích. JobRepository hỗ trợ ràng buộc tính duy nhất của JobInstance và phát hiện execution đang chạy theo metadata, nhưng không thay thế hoàn toàn điều phối scheduler, lease, leader election hoặc idempotency nghiệp vụ.

Ví dụ hai scheduler cùng yêu cầu xử lý businessDate giống nhau, chỉ một yêu cầu có thể tạo execution hợp lệ theo chính sách JobInstance; yêu cầu còn lại có thể gặp lỗi xung đột. Tầng scheduler cần bắt lỗi, không lập tức đổi `run.id` để “thử lại” nếu dữ liệu không dành cho hai lô độc lập.

## 14. Xử lý lỗi và trạng thái bất thường

| Tình huống | Nhận diện | Hướng xử lý |
| --- | --- | --- |
| Start Job đã hoàn tất với cùng identifying params | Lỗi JobInstance đã complete | Xác định có thực sự cần một lô mới; nếu có, cấp bộ identifying params hợp lệ mới. |
| Start/restart khi execution vẫn đang chạy | Lỗi running/conflict | Không mở execution song song; đọc lại trạng thái và xử lý yêu cầu trùng. |
| Restart Job không cho phép restart | `JobRestartException` hoặc exception cùng nhóm | Kiểm tra `preventRestart`, Step limit và cấu hình Job. |
| Stop trả về true nhưng trạng thái vẫn STARTED/STOPPING | Tasklet/chunk chưa trả quyền điều khiển | Theo dõi, kiểm timeout và khả năng đáp ứng stop của code nghiệp vụ. |
| Execution stuck STARTED sau crash | Worker đã chết nhưng metadata chưa được cập nhật | Xác minh môi trường; trên Batch 6 cân nhắc `recover` rồi `restart`. |
| Execution đã ABANDONED | JobInstance/execution không restart thông thường | Thực hiện chính sách vận hành/đối soát. |
| Không tìm được Job name để restart | JobRegistry không chứa Job định nghĩa | Đăng ký lại đúng Job code/version hoặc thực hiện quy trình migration tương thích. |
| ExecutionContext không đọc/deserialize được | Khác phiên bản serializer, schema hoặc cấu trúc data | Khôi phục tương thích metadata theo kế hoạch; không reset metadata tùy tiện. |
| Writer đã gọi hệ thống ngoài rồi Step lỗi | Side effect đã có nhưng metadata báo FAILED | Dùng idempotency/đối soát; chỉ restart sau khi hiểu hậu quả. |
| Job lỗi lặp lại cùng một bản ghi | Input vẫn sai hoặc policy skip/retry chưa phù hợp | Sửa nguồn/validation hoặc xử lý bản ghi lỗi theo quy trình, không spam restart. |

**Không tự thay đổi trực tiếp cột `STATUS` trong `BATCH_JOB_EXECUTION` như một thao tác thường nhật.** Metadata gồm nhiều bảng, version và context có thể phụ thuộc lẫn nhau. Nếu bắt buộc can thiệp thủ công trong tình huống bất thường, cần backup, xác định worker thực đã ngừng, đối soát transaction và có quy trình được kiểm soát.

## 15. So sánh API 5.2 và 6.x

| Nghiệp vụ | Spring Batch 5.2.x | Spring Batch 6.x |
| --- | --- | --- |
| Bắt đầu Job | `start(String jobName, Properties parameters)` | `start(Job job, JobParameters params)` |
| Restart | `restart(long executionId)`, trả execution ID | `restart(JobExecution previous)`, trả JobExecution |
| Stop | `stop(long executionId)` | `stop(JobExecution execution)` |
| Start lô kế | `startNextInstance(String jobName)` | `startNextInstance(Job job)` |
| Abandon | `abandon(long executionId)` | `abandon(JobExecution execution)` |
| Recover execution STARTED bị kẹt | Không có API `recover` mới của 6.x | `recover(JobExecution execution)` |
| Danh sách execution đang chạy | `getRunningExecutions(jobName)` trên JobOperator | Ưu tiên `JobRepository.findRunningJobExecutions(jobName)` |
| Tra cứu ID | `getSummary`, `getStepExecutionSummaries`, `JobExplorer` | Ưu tiên `JobRepository.getJobExecution` và các truy vấn repository |
| Danh sách Job sẵn sàng | `JobRegistry` hoặc `getJobNames()` | Ưu tiên `JobRegistry.getJobNames()` |
| JobLauncher | API tách biệt | JobOperator extends JobLauncher |

### Ví dụ dùng JobOperator trên Spring Batch 5.2

Trong Spring Batch 5.2, các thao tác nhận **tên Job** hoặc **execution ID**. Đoạn sau minh họa **những lời gọi riêng biệt**, không phải chuỗi lệnh gọi liên tiếp trên một execution:

~~~java
import java.util.Properties;
import org.springframework.batch.core.launch.JobOperator;

// Giả định Job "importOrders" đã có trong JobRegistry.
Properties properties = new Properties();
properties.setProperty("businessDate", "2026-11-16");

// Bắt đầu JobInstance với tham số đã khai báo:
Long startedId = jobOperator.start("importOrders", properties);

// Với một execution FAILED hoặc STOPPED có trước:
Long restartedId = jobOperator.restart(failedExecutionId);

// Gửi tín hiệu stop cho một execution đang chạy:
boolean accepted = jobOperator.stop(runningExecutionId);

// Tạo JobInstance mới dựa trên JobParametersIncrementer:
Long nextId = jobOperator.startNextInstance("importOrders");

// Đánh dấu bỏ một execution không còn chạy:
jobOperator.abandon(staleExecutionId);
~~~

Trong Batch 5.2, `JobOperator` được cung cấp qua cấu hình Batch phù hợp như `@EnableBatchProcessing` (từ Batch 5.0) hoặc cấu hình Spring Boot tương thích. Một Job cần được nhận diện/đăng ký đúng theo tên thì API start/restart theo tên mới hoạt động.

**Lưu ý khi nâng cấp:** API cũ nhận ID/tên có thể còn tồn tại trong Spring Batch 6.0 nhưng bị đánh dấu deprecated, dự kiến được loại bỏ ở dòng phiên bản tương lai. Khi xây hệ thống mới trên 6.x, dùng bản nhận `Job`/`JobExecution` và chuyển việc tra cứu sang repository/registry. Đừng đổi import giữa 5.2 và 6.x mà giữ nguyên chữ ký phương thức một cách máy móc.

## 16. Kiểm thử thao tác điều khiển

Một bộ test vận hành nên kiểm chứng đồng thời **status** và **dữ liệu thực**, không chỉ kiểm API gọi thành công.

| Kịch bản | Cách test | Điều cần assert |
| --- | --- | --- |
| Start lần đầu | Start với identifying params cố định | Có JobInstance và JobExecution mới; metadata được lưu. |
| Start trùng một lô đã COMPLETED | Start lại cùng identity | Bị từ chối theo chính sách; không ghi dữ liệu hai lần. |
| Restart sau FAILED | Chèn lỗi khi xử lý dữ liệu, sửa điều kiện lỗi, restart | Hai JobExecution, một JobInstance; dữ liệu cuối đủ, không trùng. |
| Restart sau STOPPED | Dùng Step dài và gửi stop | Chỉ restart sau khi đã STOPPED; checkpoint hoạt động. |
| Stop không tức thì | Tasklet cố ý chạy dài, gửi stop khi đang làm | Có trạng thái chuyển tiếp và stop được quan sát sau khi code trả quyền điều khiển. |
| StartNextInstance | Job dùng incrementer | JobInstance mới, identifying params đã tăng theo dự kiến. |
| Abandon | Execution không còn chạy | Trạng thái ABANDONED; restart bị từ chối. |
| Recover (6.x) | Mô phỏng metadata STARTED sau khi process đã dừng | Recover cập nhật FAILED; restart tạo execution mới nếu dữ liệu an toàn. |
| Trùng request từ hai caller | Gửi đồng thời start/restart cùng identity | Không tạo hai tiến trình xử lý nghiệp vụ trùng ngoài chính sách. |
| Stop qua async executor | Start async rồi gửi stop | API trả tín hiệu trước khi terminal status; status cuối được đọc lại từ repository. |

Test `stop` và recovery cần có đồng bộ hóa có kiểm soát: ví dụ `CountDownLatch` để biết Tasklet đã bắt đầu, rồi gửi stop. Hạn chế `Thread.sleep` tùy ý khiến test thất thường. Không tự dùng force kill để giả lập một graceful stop.

Với bài kiểm thử **crash recovery thực tế**, sử dụng hai tiến trình và database bền vững. Test cùng một JVM chỉ chứng minh logic restart/status trong điều kiện hạ tầng test đang tồn tại.

## 17. Quy trình vận hành mẫu

Giả sử Job nhập đơn hàng ngày 16/11 chạy theo lịch:

~~~text
1. Scheduler start(importOrders, businessDate=2026-11-16)
   |
   v
2. Operator nhận executionId=500 và theo dõi qua repository
   |
   +-- COMPLETED --> chốt kết quả, lưu audit và metrics
   |
   +-- FAILED -----> xem Step/ExitStatus, xác minh dữ liệu
   |                   |
   |                   +-- sửa lỗi --> restart(execution #500)
   |                                       |
   |                                       +-- execution #501
   |
   +-- STARTED ----> cần bảo trì?
                       |
                       +-- stop(#500)
                              |
                              v
                           STOPPING
                              |
                              v
                           STOPPED
                              |
                              +-- restart(#500) khi sẵn sàng
~~~

Nếu node chết mà repository còn ghi `STARTED`, phải xác nhận execution không còn chạy và dữ liệu nhất quán; trên 6.x có thể dùng `recover`. Nếu lô bị hủy vĩnh viễn, sử dụng quy trình `abandon` có audit. Nếu muốn xử lý ngày 17/11, tạo **JobInstance mới** bằng tham số nghiệp vụ mới; không nhầm nó với restart ngày 16/11.

## 18. Bài tập thực hành

**Bài 1 — Viết service điều khiển.** Tạo một Job có tên `importOrdersJob`, nhận `businessDate`, xây service với start, status, stop và restart. Lưu execution ID và dùng JobRepository truy vấn trạng thái khi cần.

**Bài 2 — Kiểm điểm dừng.** Tạo một Step chunk-oriented xử lý 20 item, chunk size 5. Gửi stop sau khi đã commit ít nhất một chunk, quan sát trạng thái trung gian và kết quả restart. Xác nhận các item đã commit không bị ghi trùng.

**Bài 3 — Phân biệt lô mới và restart.** Cấu hình JobParametersIncrementer và gọi `startNextInstance` sau Job thất bại. So sánh JobInstance ID với kết quả `restart` cùng Job bị lỗi, giải thích khi nào nên dùng mỗi API.

**Bài 4 — Giả lập crash.** Trên database test bền vững, lưu metadata execution đang STARTED rồi chấm dứt tiến trình test một cách kiểm soát. Ở tiến trình thứ hai, xác minh tiến trình cũ thực đã kết thúc và kiểm tra phương án recover/restart trên Batch 6.

**Bài 5 — Dashboard vận hành.** Thiết kế giao diện hiển thị Job name, identifying JobParameters, execution ID, BatchStatus, ExitStatus và thời gian. Nút Stop chỉ hoạt động khi phù hợp; Restart chỉ hiển thị cho FAILED/STOPPED; thao tác có xác nhận/audit nếu môi trường yêu cầu.

**Bài 6 — Chống request trùng.** Cho hai client đồng thời yêu cầu chạy cùng businessDate. Quan sát phản hồi khi một request bị từ chối và đảm bảo hệ thống không tự sinh run.id mới để che xung đột.

Kết quả mong đợi của các bài tập là hiểu được **trạng thái persisted, identity của JobInstance, các ranh giới commit và quyền điều khiển của framework**, thay vì chỉ thực hiện được vài lời gọi API.

## 19. Tài liệu tham khảo chính thức

- [Spring Batch 6 — Advanced Metadata Usage: JobOperator, stop, recover, abandon](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch 6 — JobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html)
- [Spring Batch 6 — JobRepository API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/repository/JobRepository.html)
- [Spring Batch 6 — TaskExecutorJobOperator API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/support/TaskExecutorJobOperator.html)
- [Spring Batch 6 — JobExecutionShutdownHook API](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/support/JobExecutionShutdownHook.html)
- [Spring Batch 5.2 — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/5.2/job/advanced-meta-data.html)
- [Spring Batch 5.2 — JobOperator API](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/core/launch/JobOperator.html)

