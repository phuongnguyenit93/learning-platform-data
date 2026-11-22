# Status khi job dừng có chủ đích

Trong Spring Batch, khi một Job được yêu cầu dừng có chủ đích, trạng thái thực thi thường chuyển qua `STOPPING` rồi kết thúc ở `STOPPED`. Đây là cách kết thúc có kiểm soát: Job ngừng nhận thêm công việc tại một điểm an toàn, lưu metadata cần thiết và có thể được restart sau đó nếu chính sách Job cho phép.

`STOPPED` khác với `COMPLETED` và `FAILED`. `COMPLETED` cho biết Job đã hoàn tất flow; `FAILED` cho biết quá trình thực thi thất bại; `STOPPED` cho biết Job đã được dừng trước khi hoàn tất. Một Job bị dừng có chủ đích thường vẫn có thể tiếp tục từ trạng thái đã lưu bằng cách restart cùng JobInstance.

## 1. Các trạng thái liên quan đến việc dừng Job

Spring Batch dùng `BatchStatus` để biểu diễn trạng thái vòng đời của JobExecution và StepExecution. Các trạng thái thường gặp:

| BatchStatus | Ý nghĩa |
|---|---|
| `STARTING` | JobExecution đang được khởi tạo. |
| `STARTED` | Job đang thực thi. |
| `STOPPING` | Đã nhận yêu cầu dừng; quá trình đang đi đến điểm dừng an toàn. |
| `STOPPED` | Job đã dừng có kiểm soát và không còn thực thi. |
| `COMPLETED` | Job hoàn tất bình thường theo flow. |
| `FAILED` | Job thất bại do exception hoặc điều kiện lỗi. |
| `ABANDONED` | Execution được đánh dấu bỏ hẳn, không tiếp tục theo cách restart thông thường. |
| `UNKNOWN` | Không thể xác định chắc chắn trạng thái thực thi. |

Luồng trạng thái điển hình khi yêu cầu dừng một Job đang chạy:

```text
STARTED
   |
   | JobOperator.stop(executionId)
   v
STOPPING
   |
   | Step đi đến điểm dừng an toàn
   v
STOPPED
   |
   +--> Có thể restart cùng JobInstance nếu chính sách cho phép
```

`STOPPING` thường là trạng thái trung gian. Yêu cầu dừng không đồng nghĩa thread đang chạy bị ngắt cưỡng bức ngay lập tức. Step cần có cơ hội hoàn thành đơn vị xử lý hiện tại hoặc kiểm tra tín hiệu dừng tại điểm an toàn.

## 2. Phân biệt STOPPED, COMPLETED và FAILED

Ba trạng thái này thể hiện ba kết quả khác nhau:

| Trạng thái | Nguyên nhân điển hình | Có thể restart cùng JobInstance? |
|---|---|---|
| `COMPLETED` | Các Step và flow đã hoàn tất bình thường. | Thông thường không; JobInstance đã hoàn tất. |
| `FAILED` | Exception không được xử lý hoặc một Step/flow thất bại. | Có thể, nếu Job và Step cho phép restart. |
| `STOPPED` | Người vận hành hoặc flow yêu cầu dừng có kiểm soát. | Có thể, nếu Job và Step cho phép restart. |
| `ABANDONED` | Execution được đánh dấu không tiếp tục. | Không theo quy trình restart thông thường. |

Ví dụ:

- Người vận hành cần tạm dừng import để bảo trì database: yêu cầu stop và Job kết thúc `STOPPED`.
- Reader gặp lỗi không thể xử lý: Job kết thúc `FAILED`.
- Tất cả dữ liệu đã được xử lý và các Step kết thúc: Job `COMPLETED`.
- Một execution cũ được xác định không thể tiếp tục và được quản trị viên abandon: `ABANDONED`.

Không nên đánh dấu một Job là `FAILED` chỉ vì người vận hành muốn dừng nó để bảo trì. Dùng cơ chế stop giúp thể hiện rõ đây là yêu cầu điều khiển có chủ đích, đồng thời giữ khả năng restart phù hợp.

## 3. Dừng Job đang chạy bằng JobOperator

API vận hành phổ biến để yêu cầu dừng một JobExecution đang chạy là `JobOperator.stop(executionId)`. Phương thức này gửi yêu cầu dừng dựa trên ID của JobExecution, thay vì trực tiếp giết thread đang chạy.

Ví dụ service nhận yêu cầu dừng:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class JobControlService {

    private final JobOperator jobOperator;

    public JobControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long executionId) throws Exception {
        return jobOperator.stop(executionId);
    }
}
```

Giá trị boolean cho biết yêu cầu stop đã được chấp nhận theo API. Nó không có nghĩa Job đã chuyển sang `STOPPED` ngay tại thời điểm phương thức trả về. Ứng dụng cần tiếp tục theo dõi JobExecution cho đến khi trạng thái cuối là `STOPPED`, `COMPLETED` hoặc `FAILED`.

ID truyền vào phải là JobExecution ID đang chạy, không phải JobInstance ID hoặc StepExecution ID. Nếu execution đã kết thúc hoặc không tồn tại, JobOperator có thể ném exception tương ứng. Cần xử lý tình huống Job vừa hoàn tất đúng lúc người vận hành gửi stop request.

## 4. Stop là yêu cầu dừng có kiểm soát, không phải kill thread

Khi gọi `JobOperator.stop()`, Spring Batch yêu cầu Job dừng tại một điểm an toàn. Cơ chế cụ thể phụ thuộc loại Step và thời điểm nhận tín hiệu.

Với chunk-oriented Step, một chunk đang xử lý thường được phép đi đến ranh giới phù hợp trước khi Step dừng. Điều này giúp tránh ngắt một thao tác ghi ở giữa transaction. Chunk đã commit vẫn được giữ; nếu chunk hiện tại rollback do lỗi hoặc interruption, dữ liệu trong transaction đó được hoàn tác.

Với Tasklet Step, việc dừng phụ thuộc vào thời gian và cách Tasklet thực hiện công việc. Nếu Tasklet đang thực hiện một lời gọi mạng hoặc vòng lặp dài không kiểm tra trạng thái, yêu cầu stop có thể không được phản ánh cho đến khi lời gọi hoặc lần thực thi đó kết thúc. Tasklet nên chia công việc dài thành các đơn vị có giới hạn, kiểm tra tín hiệu dừng phù hợp hoặc lưu tiến độ để có thể tiếp tục.

Không nên dùng `Thread.stop()` hoặc tự ngắt thread của Spring Batch. Ngắt cưỡng bức có thể bỏ qua cleanup, để lại transaction hoặc tài nguyên ở trạng thái không an toàn và làm metadata không phản ánh đúng kết quả nghiệp vụ.

## 5. Theo dõi trạng thái sau khi gửi stop request

Sau khi yêu cầu dừng, ứng dụng nên tra cứu JobExecution để biết Job đã thực sự kết thúc hay chưa. Có thể dùng `JobExplorer`:

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class JobStatusService {

    private final JobExplorer jobExplorer;

    public JobStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public BatchStatus getStatus(long executionId) {
        JobExecution execution = jobExplorer.getJobExecution(executionId);
        if (execution == null) {
            throw new IllegalArgumentException(
                    "JobExecution not found: " + executionId);
        }
        return execution.getStatus();
    }
}
```

Một endpoint quản trị có thể trả về trạng thái `STOPPING` ngay sau khi nhận yêu cầu, sau đó client polling cho đến khi Job chuyển sang trạng thái kết thúc. Trong môi trường nhiều instance, JobExplorer phải đọc metadata từ cùng repository bền vững mà Job đang sử dụng.

Không nên chỉ dựa vào boolean trả về từ `stop()` để hiển thị Job đã dừng. Hãy đọc trạng thái thực tế từ JobRepository/JobExplorer.

## 6. Stop ở ranh giới chunk và ảnh hưởng đến checkpoint

Với chunk Step, Spring Batch quản lý transaction theo từng chunk. Khi yêu cầu dừng đến trong lúc chunk đang chạy, Step thường cần hoàn tất hoặc rollback đơn vị transaction hiện tại trước khi dừng.

```text
Chunk 1: READ / PROCESS / WRITE -> COMMIT
Chunk 2: READ / PROCESS / WRITE -> COMMIT
             |
             +--> Nhận stop request
             |
             v
       Dừng tại điểm an toàn
             |
             v
          STOPPED

Restart cùng JobInstance
             |
             v
       Tiếp tục từ checkpoint đã commit
```

Checkpoint được lưu ở các ranh giới commit phù hợp. Các chunk đã commit trước khi dừng được giữ lại. Khi restart cùng JobInstance, Reader hỗ trợ state có thể tiếp tục từ checkpoint gần nhất.

Không nên giả định stop luôn xảy ra đúng giữa hai chunk. Nếu yêu cầu đến khi Writer đang thực thi, kết quả phụ thuộc thời điểm Step kiểm tra tín hiệu và transaction kết thúc như thế nào. Hãy thiết kế Writer idempotent để dữ liệu an toàn nếu một chunk cần được thử lại.

## 7. Dừng một Job bằng flow transition

Ngoài yêu cầu stop từ bên ngoài, Job flow cũng có thể chủ động kết thúc ở trạng thái `STOPPED`. Đây là cách hữu ích khi nghiệp vụ cần tạm dừng ở một điểm cụ thể và chỉ định Step bắt đầu lại khi restart.

Spring Batch cung cấp transition `stopAndRestart(step)` trong flow builder. Ví dụ, sau khi kiểm tra dữ liệu, Job có thể dừng có chủ đích nếu cần chờ phê duyệt; khi restart, flow tiếp tục từ Step xử lý đã chỉ định.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;

@Bean
public Job approvalJob(
        JobRepository jobRepository,
        Step validateRequestStep,
        Step processApprovedRequestStep) {

    return new JobBuilder("approvalJob", jobRepository)
            .start(validateRequestStep)
            .on("WAIT_FOR_APPROVAL")
            .stopAndRestart(processApprovedRequestStep)
            .from(validateRequestStep)
            .on("COMPLETED")
            .to(processApprovedRequestStep)
            .end()
            .build();
}
```

Ví dụ giả định `validateRequestStep` có thể trả `ExitStatus("WAIT_FOR_APPROVAL")` khi cần chờ người phê duyệt. Transition `stopAndRestart(processApprovedRequestStep)` kết thúc Job với trạng thái dừng và xác định điểm tiếp tục khi JobInstance được restart.

Flow transition được chọn dựa trên ExitStatus của Step. Do đó, Step cần đặt ExitStatus đúng mã mà flow đang kiểm tra. Có thể đặt mã tùy chỉnh trong Tasklet hoặc Step listener:

```java
contribution.setExitStatus(new ExitStatus("WAIT_FOR_APPROVAL"));
return RepeatStatus.FINISHED;
```

Đây là dừng theo quy tắc nghiệp vụ đã được khai báo trong flow, khác với stop request gửi đến một Job đang chạy từ JobOperator.

## 8. Phân biệt stop, end, fail và abandon trong flow

Spring Batch flow builder có các transition kết thúc với ý nghĩa khác nhau:

| Transition | Kết quả | Restart cùng JobInstance |
|---|---|---|
| `.end()` | Kết thúc flow bình thường, Job thường `COMPLETED`. | Không restart JobInstance đã hoàn tất. |
| `.fail()` | Kết thúc flow với trạng thái lỗi, Job `FAILED`. | Có thể restart nếu Job cho phép. |
| `.stop()` | Kết thúc flow với trạng thái `STOPPED`. | Có thể restart theo trạng thái và cấu hình. |
| `.stopAndRestart(step)` | Dừng flow và chỉ định Step bắt đầu lại khi restart. | Có thể restart từ Step đã chỉ định. |

`abandon` là thao tác quản trị trên JobExecution thông qua JobOperator, không phải transition thay thế cho `.stop()`. Khi abandon, execution được đánh dấu `ABANDONED` và không thể tiếp tục theo quy trình restart thông thường.

Hãy chọn `STOPPED` khi muốn tạm dừng và giữ khả năng tiếp tục; chọn `FAILED` khi có lỗi cần sửa; chọn `COMPLETED` khi đơn vị công việc đã hoàn tất; chỉ abandon khi đã quyết định bỏ hẳn execution đó.

## 9. STOPPED và ExitStatus

`BatchStatus` và `ExitStatus` là hai thông tin khác nhau:

- `BatchStatus` biểu diễn trạng thái vòng đời của JobExecution/StepExecution.
- `ExitStatus` biểu diễn mã kết quả thoát và có thể chứa mã tùy chỉnh phục vụ flow hoặc báo cáo.

Khi Job được dừng, `BatchStatus` cuối thường là `STOPPED`; `ExitStatus` mặc định thường phản ánh mã `STOPPED`, nhưng có thể được tùy chỉnh bởi listener hoặc flow. Vì vậy, khi kiểm tra kết quả, nên đọc cả hai giá trị.

Ví dụ đọc trạng thái:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    BatchStatus batchStatus = execution.getStatus();
    String exitCode = execution.getExitStatus().getExitCode();

    log.info("JobExecution {} status={}, exitCode={}",
            executionId, batchStatus, exitCode);
}
```

Không nên chỉ so sánh ExitStatus với chuỗi `STOPPED` rồi kết luận Job chắc chắn đã dừng. Cần xem BatchStatus và liệu execution còn đang `STOPPING` hay không.

## 10. Restart một Job đã STOPPED

Một Job kết thúc `STOPPED` thường có thể được restart nếu Job không bị cấu hình `preventRestart()` và Step liên quan có thể tiếp tục. Khi restart, cần dùng cùng identifying JobParameters để tiếp tục cùng JobInstance.

Có thể restart bằng `JobOperator`:

```java
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.stereotype.Service;

@Service
public class RestartService {

    private final JobOperator jobOperator;

    public RestartService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public Long restart(long stoppedExecutionId) throws Exception {
        return jobOperator.restart(stoppedExecutionId);
    }
}
```

`stoppedExecutionId` là ID của JobExecution đã dừng, không phải JobInstance ID. JobOperator tạo một JobExecution mới cho cùng JobInstance nếu trạng thái và chính sách cho phép.

Một cách khác là gọi `JobLauncher.run()` với cùng Job và cùng identifying parameters. Spring Batch tra cứu JobInstance tương ứng và áp dụng restart semantics. Không thêm UUID hoặc timestamp identifying mới nếu mục tiêu là restart; làm vậy sẽ tạo JobInstance mới.

### Step nào chạy lại sau restart?

- Step đã `COMPLETED` thường được bỏ qua.
- Step bị dừng hoặc chưa hoàn tất có thể được tiếp tục theo checkpoint và flow.
- Step có `allowStartIfComplete(true)` có thể chạy lại dù đã hoàn tất.
- Step đã chạm `startLimit` không được bắt đầu thêm.
- Nếu flow dùng `stopAndRestart(step)`, điểm restart được xác định theo Step đã cấu hình.

Restart không nhất thiết chạy lại toàn bộ Job từ Step đầu tiên. Nó dựa vào metadata và cấu hình flow.

## 11. Dừng có chủ đích khác với abandon

`JobOperator.stop(executionId)` yêu cầu Job đang chạy dừng có kiểm soát. Sau khi dừng, JobExecution có thể restart.

`JobOperator.abandon(executionId)` đánh dấu execution là `ABANDONED`. Thao tác này dành cho trường hợp người vận hành quyết định không tiếp tục execution đó theo cách restart thông thường. Không dùng abandon chỉ vì muốn tạm dừng Job.

| Tác vụ vận hành | API/transition phù hợp |
|---|---|
| Tạm dừng Job đang chạy để bảo trì rồi tiếp tục sau | `JobOperator.stop(executionId)` |
| Dừng flow theo điều kiện nghiệp vụ và chỉ định điểm tiếp tục | `.stopAndRestart(step)` |
| Kết thúc flow thành công | `.end()` |
| Kết thúc flow vì lỗi | `.fail()` |
| Bỏ hẳn một execution, không tiếp tục restart thông thường | `JobOperator.abandon(executionId)` |

Abandon là thao tác quản trị có ảnh hưởng đến khả năng phục hồi. Trước khi abandon, cần xác nhận dữ liệu nghiệp vụ đã ở trạng thái an toàn và có phương án xử lý phần công việc còn lại.

## 12. Stop request khi Job đang chạy bất đồng bộ

Với asynchronous JobLauncher, lời gọi launch có thể trả về ngay khi Job mới được gửi tới executor. Job tiếp tục chạy ở thread khác. Khi cần dừng, ứng dụng cần dùng JobExecution ID đã được tạo và gọi `JobOperator.stop()`.

Luồng quản lý điển hình:

```text
API / Scheduler
    |
    v
JobLauncher (async)
    |
    v
JobExecution ID được lưu/trả về
    |
    +------------------------+
    |                        |
    v                        v
Theo dõi status          Yêu cầu dừng
    |                        |
    |                   JobOperator.stop(id)
    |                        |
    +----------+-------------+
               |
               v
          JobExecution
               |
               v
       STOPPING -> STOPPED
```

Không nên giữ transaction của request API mở trong suốt thời gian Job chạy hoặc chờ Job dừng. Hãy lưu ID execution, trả kết quả điều khiển phù hợp và cung cấp endpoint/status view để theo dõi.

Nếu ứng dụng chạy nhiều instance, JobOperator và JobExplorer cần truy cập metadata repository dùng chung. Việc stop phải gửi đến execution đúng và worker phải có khả năng quan sát tín hiệu dừng theo cơ chế Spring Batch.

## 13. Xử lý Tasklet dài và điểm dừng hợp tác

Một Tasklet thực hiện một lần gọi dịch vụ kéo dài hoặc vòng lặp lớn có thể không phản hồi stop request nhanh nếu không có điểm kiểm tra. Không nên viết một Tasklet thực hiện hàng giờ công việc trong một lần `execute()` mà không có checkpoint hoặc cách chia nhỏ.

Các hướng thiết kế:

1. Chia công việc thành các đơn vị nhỏ, mỗi đơn vị có thể hoàn tất và lưu trạng thái.
2. Dùng chunk-oriented Step nếu công việc là đọc/xử lý/ghi nhiều item.
3. Với Tasklet lặp, lưu tiến độ vào ExecutionContext hoặc database để có thể tiếp tục.
4. Đặt timeout cho HTTP/database call để stop không phải chờ vô hạn một dependency bị treo.
5. Đảm bảo cleanup tài nguyên trong `finally` hoặc callback lifecycle phù hợp.

Nếu nghiệp vụ cần kiểm tra stop signal trong vòng lặp, hãy dùng cơ chế phối hợp an toàn với StepExecution/JobExecution và kiểm tra ở ranh giới đơn vị công việc. Không tự sửa BatchStatus trong database hoặc ngắt thread để ép trạng thái thành `STOPPED`.

## 14. Listener và audit khi Job bị dừng

`JobExecutionListener.afterJob()` được gọi khi Job kết thúc, kể cả khi trạng thái cuối là `STOPPED` hoặc `FAILED`. Listener có thể đọc BatchStatus và ExitStatus để lưu audit hoặc phát thông báo.

```java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;

public class JobAuditListener implements JobExecutionListener {

    @Override
    public void beforeJob(JobExecution jobExecution) {
        // Ghi nhận bắt đầu.
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (jobExecution.getStatus() == BatchStatus.STOPPED) {
            // Ghi nhận Job đã dừng có chủ đích hoặc flow đã dừng.
        }
    }
}
```

Trong hệ thống thật, nên lưu execution ID, JobInstance ID, thời điểm dừng, Step đang thực hiện và người/nguồn gửi yêu cầu stop nếu ứng dụng có thông tin đó. Không nên dùng một field mutable trong singleton listener để giữ người yêu cầu hoặc thời điểm bắt đầu; hãy gắn dữ liệu với JobExecution hoặc audit record riêng.

Nếu gửi email hoặc message khi Job dừng, cần chống gửi trùng khi listener hoặc quy trình điều phối được gọi lại. Có thể ghi sự kiện vào outbox theo execution ID rồi gửi sau commit.

## 15. Kiểm thử Job dừng có chủ đích

Nên có integration test dùng `JobRepository` và `JobLauncherTestUtils` hoặc `JobOperator` để xác nhận trạng thái thực tế, thay vì chỉ gọi một phương thức Java giả lập.

Các kịch bản nên kiểm tra:

1. **Stop một Job đang chạy:** launch Job có Step chạy đủ lâu hoặc có latch điều khiển; gọi `JobOperator.stop(executionId)`; xác nhận Job chuyển từ `STOPPING` sang `STOPPED`.
2. **Restart Job đã STOPPED:** dùng cùng identifying JobParameters; xác nhận JobExecution mới thuộc cùng JobInstance và Step tiếp tục theo checkpoint.
3. **Stop request quá muộn:** để Job hoàn tất trước khi gọi stop; xác nhận ứng dụng xử lý trường hợp execution không còn running.
4. **Flow stopAndRestart:** cấu hình Step trả ExitStatus phù hợp; xác nhận Job dừng và restart từ Step đã chỉ định.
5. **Abandon:** xác nhận execution được đánh dấu `ABANDONED` và không được xem như một Job có thể restart bình thường.
6. **Listener:** xác nhận `afterJob()` nhận đúng `STOPPED` và audit không bị ghi trùng.

Với Job chạy bất đồng bộ, test phải chờ trạng thái terminal bằng cơ chế đồng bộ có timeout. Không nên dùng `Thread.sleep()` dài và giả định Job đã dừng; hãy poll `JobExplorer` hoặc dùng latch/test hook để điều khiển thời điểm.

Khi kiểm tra restart, giữ nguyên identifying JobParameters. Nếu thêm tham số định danh mới, Spring Batch tạo JobInstance mới và test sẽ không còn kiểm tra restart của execution đã dừng.

## 16. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Xem `STOPPING` là đã dừng hoàn toàn | Job có thể vẫn đang hoàn tất chunk hoặc cleanup. | Theo dõi đến trạng thái terminal như `STOPPED`. |
| Dùng kill thread để dừng Job | Có thể bỏ qua cleanup hoặc làm transaction/tài nguyên không an toàn. | Dùng `JobOperator.stop()` và điểm dừng hợp tác. |
| Nhầm STOPPED với FAILED | Báo cáo và quy trình restart không phản ánh đúng nguyên nhân. | Dùng stop cho yêu cầu dừng có chủ đích, fail cho lỗi. |
| Nhầm stop với abandon | Execution có thể bị đánh dấu không restart được. | Chỉ abandon khi quyết định bỏ hẳn execution. |
| Tin rằng stop request hoàn tất ngay khi API trả về | Boolean chỉ phản ánh yêu cầu được chấp nhận, không phải Job đã dừng. | Poll JobExecution qua JobExplorer. |
| Gửi stop cho JobExecution ID sai | Không dừng được execution mong muốn. | Tra cứu và xác thực ID trước khi gọi JobOperator. |
| Tasklet dài không có điểm kiểm tra | Job phản hồi stop chậm hoặc phải đợi thao tác kéo dài kết thúc. | Chia nhỏ công việc, đặt timeout và lưu tiến độ. |
| Restart với identifying parameters mới | Tạo JobInstance mới thay vì tiếp tục Job đã dừng. | Dùng lại identifying parameters của instance cũ. |
| Gửi thông báo dừng trực tiếp không chống trùng | Audit/notification có thể bị lặp khi retry hoặc restart. | Gắn idempotency key với execution ID hoặc dùng outbox. |

## Kết luận

Khi Job được dừng có chủ đích, Spring Batch thường chuyển trạng thái từ `STARTED` sang `STOPPING` rồi `STOPPED` sau khi đạt điểm dừng an toàn. Dùng `JobOperator.stop(executionId)` để yêu cầu dừng và theo dõi JobExecution đến khi thực sự kết thúc; không ngắt thread cưỡng bức. `STOPPED` khác với `FAILED`, `COMPLETED` và `ABANDONED`: Job đã dừng thường có thể restart cùng JobInstance nếu chính sách cho phép. Với chunk Step, checkpoint và transaction giúp tiếp tục từ phần đã commit; với Tasklet dài, cần chia nhỏ công việc và lưu tiến độ. Kiểm thử cả stop, restart, flow transition và audit sẽ giúp quy trình dừng có chủ đích an toàn và dễ vận hành.
