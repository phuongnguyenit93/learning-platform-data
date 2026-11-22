# BatchStatus của JobExecution

Trong Spring Batch, `JobExecution` đại diện cho một lần thực thi cụ thể của một job. Thuộc tính `BatchStatus` cho biết lần thực thi đó đang ở giai đoạn nào hoặc đã kết thúc theo trạng thái nào: đang khởi động, đang chạy, đang dừng, hoàn thành, thất bại hoặc được đánh dấu không thể tiếp tục.

Khi theo dõi batch job, `BatchStatus` là thông tin đầu tiên để biết job còn chạy hay đã kết thúc. Tuy nhiên, trạng thái này không mô tả đầy đủ kết quả nghiệp vụ. Một job có thể có `BatchStatus.COMPLETED` dù một số item đã bị skip theo chính sách; một job có thể có step thất bại nhưng flow được cấu hình kết thúc theo nhánh hoàn thành. Vì vậy, cần đọc `JobExecution.getStatus()` cùng `ExitStatus`, trạng thái từng step và dữ liệu nghiệp vụ.

## 1. JobExecution và BatchStatus

Một `JobInstance` biểu diễn một lần xử lý nghiệp vụ được xác định bởi tên job và các identifying `JobParameters`. Mỗi lần job được khởi chạy hoặc restart, Spring Batch tạo một `JobExecution` riêng cho instance đó.

Ví dụ, job nhập file cho ngày nghiệp vụ 2026-11-14 có thể có:

| Đối tượng | Ý nghĩa |
|---|---|
| `JobInstance` | Job `importOrdersJob` với `businessDate=2026-11-14` |
| `JobExecution` 101 | Lần chạy đầu, thất bại ở step ghi dữ liệu |
| `JobExecution` 102 | Lần restart, hoàn thành thành công |

Hai `JobExecution` thuộc cùng một `JobInstance`, nhưng có ID và trạng thái riêng. `BatchStatus` gắn với từng execution, không phải một trạng thái chung tồn tại vĩnh viễn trên `JobInstance`.

Trong code, có thể đọc trạng thái của một execution:

~~~java
JobExecution execution = jobLauncher.run(job, jobParameters);

BatchStatus status = execution.getStatus();
log.info("Job execution {} status={}", execution.getId(), status);
~~~

Nếu job chạy đồng bộ, lời gọi `run()` thường trả về sau khi execution kết thúc. Nếu dùng launcher bất đồng bộ, object trả về có thể vẫn ở trạng thái đang chạy; cần tra cứu lại trạng thái mới nhất từ `JobExplorer`.

## 2. Các giá trị BatchStatus

`BatchStatus` là enum do Spring Batch định nghĩa. Các trạng thái thường gặp:

| BatchStatus | Ý nghĩa |
|---|---|
| `STARTING` | Execution đã được tạo và đang trong giai đoạn khởi động |
| `STARTED` | Job hoặc step đang thực thi |
| `STOPPING` | Đã có yêu cầu dừng và framework đang xử lý yêu cầu đó |
| `STOPPED` | Execution đã dừng |
| `COMPLETED` | Execution hoàn tất theo flow và cơ chế thực thi của framework |
| `FAILED` | Execution kết thúc do lỗi không được xử lý thành công |
| `ABANDONED` | Execution được đánh dấu bỏ, không tiếp tục theo cách restart thông thường |
| `UNKNOWN` | Không thể xác định trạng thái thực thi một cách đáng tin cậy |

Các trạng thái này mô tả vòng đời framework. Chúng không phải mã tùy chỉnh cho từng kết quả nghiệp vụ. Nếu cần phân biệt `COMPLETED_WITH_WARNINGS`, `COMPLETED_WITH_SKIPS` hoặc `NO_DATA`, hãy dùng `ExitStatus` hoặc trạng thái nghiệp vụ riêng.

## 3. Vòng đời trạng thái của JobExecution

Một lần thực thi thông thường đi qua các giai đoạn khởi động, chạy và kết thúc:

~~~mermaid
stateDiagram-v2
    [*] --> STARTING
    STARTING --> STARTED
    STARTED --> COMPLETED
    STARTED --> FAILED
    STARTED --> STOPPING
    STOPPING --> STOPPED
    STOPPED --> [*]
    COMPLETED --> [*]
    FAILED --> [*]
    ABANDONED --> [*]
    UNKNOWN --> [*]
~~~

Sơ đồ thể hiện các nhánh phổ biến, không phải mọi chuyển trạng thái nội bộ có thể xảy ra trong mọi phiên bản hoặc mọi tình huống phục hồi. Ví dụ, `ABANDONED` thường là kết quả của thao tác quản trị, còn `UNKNOWN` thường liên quan đến tình huống không thể xác định chắc chắn execution đã kết thúc ở đâu.

Ý nghĩa thực tế:

- `STARTING` và `STARTED` cho biết job chưa có kết quả cuối cùng.
- `STOPPING` cho biết yêu cầu dừng đang được xử lý; chưa nên coi job đã dừng.
- `STOPPED`, `FAILED` và `COMPLETED` là các trạng thái kết thúc thường được quan sát trong vận hành.
- `ABANDONED` và `UNKNOWN` cần được xử lý thận trọng vì chúng ảnh hưởng tới khả năng restart.

Không nên dựa vào một lần đọc trạng thái duy nhất để kết luận job đã kết thúc nếu execution đang ở `STARTING`, `STARTED` hoặc `STOPPING`.

## 4. STARTING và STARTED

`STARTING` xuất hiện khi Spring Batch đã tạo execution và đang chuẩn bị khởi chạy job. Framework cần khởi tạo các thành phần liên quan, kiểm tra trạng thái và bắt đầu flow.

`STARTED` cho biết job đang thực thi. Các step có thể đang chạy hoặc chờ theo cấu trúc flow. Trong job có parallel flow, nhiều step có thể chạy đồng thời trong khi JobExecution vẫn có một trạng thái chung.

Khi API vận hành nhận thấy execution ở `STARTING` hoặc `STARTED`, có thể trả về trạng thái đang chạy và cung cấp execution ID để client tra cứu sau. Không khởi chạy một execution mới chỉ vì chưa thấy kết quả cuối cùng; hãy kiểm tra xem cùng `JobInstance` đã có execution đang chạy hay chưa.

Ví dụ:

~~~java
if (execution.getStatus() == BatchStatus.STARTING
        || execution.getStatus() == BatchStatus.STARTED) {
    log.info("Job {} is still running", execution.getId());
}
~~~

Trong hệ thống có nhiều node, `JobRepository` là nguồn metadata chung để điều phối và ngăn những lần chạy xung đột theo cùng định danh. Không dùng biến trong bộ nhớ của một node làm nguồn chân lý duy nhất cho trạng thái job.

## 5. STOPPING và STOPPED

`STOPPING` có nghĩa đã có yêu cầu dừng execution nhưng việc dừng chưa hoàn tất. `STOPPED` là trạng thái sau khi framework xử lý xong yêu cầu dừng.

Có thể yêu cầu dừng một execution đang chạy qua `JobOperator`:

~~~java
@Service
public class BatchControlService {

    private final JobOperator jobOperator;

    public BatchControlService(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public boolean requestStop(long executionId) throws Exception {
        return jobOperator.stop(executionId);
    }
}
~~~

Yêu cầu stop thường là yêu cầu dừng có phối hợp, không phải lệnh cưỡng bức giết thread ngay lập tức. Step có thể cần đi tới điểm an toàn để kết thúc transaction hoặc kiểm tra cờ dừng. Thời gian phản hồi phụ thuộc loại tasklet, reader/writer, thao tác đang chờ và cách thành phần xử lý stop.

Với chunk step, framework thường có cơ hội kiểm tra yêu cầu dừng ở ranh giới xử lý chunk. Với một tasklet chạy vòng lặp dài hoặc gọi dịch vụ ngoài lâu, code cần được thiết kế để kiểm tra trạng thái dừng hoặc có timeout phù hợp. Không nên giả định `JobOperator.stop()` sẽ ngắt ngay một HTTP call hoặc rollback một side effect bên ngoài.

Sau khi yêu cầu stop được chấp nhận, trạng thái có thể tạm thời là `STOPPING`. Chỉ khi execution thực sự kết thúc mới nên xem nó là `STOPPED`.

## 6. COMPLETED

`COMPLETED` biểu thị job execution đã kết thúc theo flow như một lần chạy hoàn thành. Đây là trạng thái thường được xem là thành công ở cấp framework.

Tuy nhiên, `COMPLETED` không tự chứng minh:

- Mọi record nguồn đều đã được ghi.
- Không có item nào bị filter hoặc skip.
- Tổng tiền, số lượng hoặc checksum đối soát đã đúng.
- Tất cả side effect ở API, file hoặc message broker đã được xác nhận.
- Kết quả đáp ứng mọi điều kiện nghiệp vụ.

Ví dụ, một step cho phép skip tối đa 20 dòng lỗi. Nếu chỉ có 3 dòng bị skip, step có thể hoàn thành bình thường và job có thể đạt `COMPLETED`. Nếu nghiệp vụ yêu cầu mọi dòng phải được nhập, đây vẫn là kết quả cần điều tra hoặc giữ lại để review.

Để xác định mức độ hoàn tất, hãy kết hợp:

- `JobExecution.getStatus()`.
- `JobExecution.getExitStatus()`.
- `StepExecution` và các bộ đếm read/write/filter/skip.
- Kết quả reconciliation và dữ liệu nghiệp vụ thực tế.

Khi một `JobInstance` đã hoàn thành, việc chạy lại cùng identifying `JobParameters` theo cách thông thường không tạo thêm một execution để xử lý lại cùng instance; Spring Batch thường từ chối bằng lỗi instance đã hoàn thành. Nếu muốn xử lý một batch nghiệp vụ mới, phải dùng identifying parameters mới phù hợp với batch mới.

## 7. FAILED

`FAILED` biểu thị job execution kết thúc do lỗi không được xử lý thành công theo flow và chính sách step. Nguyên nhân có thể là exception ở reader, processor, writer, tasklet, lỗi khởi tạo hoặc lỗi điều phối.

Khi job thất bại:

- Một hoặc nhiều step có thể có trạng thái `FAILED`.
- Các step trước đó đã `COMPLETED` có thể giữ nguyên dữ liệu đã commit.
- Chunk đang lỗi thường rollback theo transaction policy.
- Các step phía sau có thể chưa được chạy.
- Metadata và execution context đã lưu được dùng để hỗ trợ điều tra và restart.

Không được suy luận rằng `FAILED` nghĩa là toàn bộ dữ liệu của job đã rollback. Mỗi chunk/step có ranh giới transaction riêng; dữ liệu đã commit trước lỗi thường vẫn tồn tại.

Có thể đọc lỗi từ execution:

~~~java
JobExecution execution = jobExplorer.getJobExecution(executionId);
if (execution != null) {
    log.error("Job status={}, exit={}",
            execution.getStatus(),
            execution.getExitStatus());

    for (Throwable failure : execution.getAllFailureExceptions()) {
        log.error("Job failure", failure);
    }
}
~~~

Một execution `FAILED` thường có thể được restart nếu job được cấu hình restartable, trạng thái metadata hợp lệ và các điều kiện restart của step được thỏa mãn. Nếu job được khai báo không restart hoặc step có chính sách không cho chạy lại, cần theo quy trình phục hồi riêng.

## 8. ABANDONED

`ABANDONED` biểu thị execution đã được đánh dấu bỏ và không nên tiếp tục restart theo quy trình thông thường. Đây thường là quyết định vận hành, ví dụ một execution thất bại đã được xác định không thể hoặc không nên tiếp tục.

`ABANDONED` khác với `FAILED`:

- `FAILED` ghi nhận lần thực thi thất bại; có thể restart nếu cấu hình và trạng thái cho phép.
- `ABANDONED` thể hiện execution được chủ động loại khỏi quy trình tiếp tục thông thường.

Không đánh dấu execution là abandoned chỉ để xóa một trạng thái lỗi khỏi dashboard. Trước khi abandon, cần hiểu dữ liệu nào đã commit, side effect nào đã xảy ra và batch nghiệp vụ sẽ được xử lý lại bằng cách nào.

Một số tình huống vận hành có thể cần bỏ execution cũ rồi tạo một quy trình xử lý mới với identifying parameters hoặc batch reference khác. Đây là quyết định nghiệp vụ cần audit, không phải cách mặc định để vượt qua lỗi restart.

## 9. UNKNOWN

`UNKNOWN` biểu thị framework hoặc repository không thể xác định trạng thái execution một cách đáng tin cậy. Đây là trạng thái cần thận trọng vì ứng dụng không biết chắc job đã hoàn tất, thất bại hay bị gián đoạn ở một điểm nào đó.

Nguyên nhân có thể liên quan đến:

- JVM hoặc máy chủ dừng đột ngột trong lúc cập nhật metadata.
- Mất kết nối database đúng thời điểm commit trạng thái.
- Metadata không nhất quán hoặc bị can thiệp ngoài cơ chế Spring Batch.
- Lỗi hạ tầng khiến framework không thể xác nhận kết quả cuối.

Không nên tự động restart một execution `UNKNOWN` mà chưa điều tra. Nếu một side effect đã xảy ra nhưng metadata không được lưu, chạy lại có thể tạo dữ liệu trùng. Nếu dữ liệu chưa được ghi, bỏ qua execution có thể làm thiếu dữ liệu.

Quy trình xử lý nên gồm:

1. Kiểm tra log ứng dụng và log database quanh thời điểm lỗi.
2. Đọc `JobExecution`, `StepExecution` và execution context từ `JobExplorer`.
3. Đối chiếu dữ liệu nghiệp vụ, outbox/message và file output.
4. Xác định chunk/step cuối cùng đã commit chắc chắn.
5. Thực hiện recovery theo runbook có audit; không sửa trực tiếp bảng metadata để ép trạng thái.

## 10. BatchStatus của JobExecution khác BatchStatus của StepExecution

Một job có thể gồm nhiều step. Mỗi `StepExecution` có BatchStatus riêng; `JobExecution` có BatchStatus ở cấp job. Hai cấp có quan hệ nhưng không phải lúc nào cũng giống nhau.

Ví dụ:

| Step | BatchStatus | Ghi chú |
|---|---|---|
| `validateInputStep` | `COMPLETED` | Đã kiểm tra đầu vào |
| `importOrdersStep` | `FAILED` | Writer gặp lỗi không được xử lý |
| `reconcileStep` | Không có execution | Chưa được chạy |
| JobExecution | `FAILED` | Flow kết thúc do lỗi |

Trong flow có nhánh điều kiện, job status cuối còn phụ thuộc transition và cách flow kết thúc. Một step có exit code đặc biệt có thể dẫn tới nhánh `.end()`, `.fail()` hoặc `.stop()`. Vì vậy, không nên tính BatchStatus của job bằng cách lấy status của step cuối cùng hoặc tự tổng hợp enum từ các step.

Khi điều tra job, hãy đọc tất cả `StepExecution`:

~~~java
for (StepExecution step : execution.getStepExecutions()) {
    log.info("Step {}: status={}, exitCode={}, reads={}, writes={}, skips={}",
            step.getStepName(),
            step.getStatus(),
            step.getExitStatus().getExitCode(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getSkipCount());
}
~~~

Điều này giúp xác định step nào thực sự thất bại, step nào hoàn tất và step nào chưa được chạy.

## 11. BatchStatus khác ExitStatus

`BatchStatus` là enum mô tả vòng đời execution. `ExitStatus` là value object chứa exit code và exit description. Exit code có thể là giá trị chuẩn hoặc mã tùy chỉnh do ứng dụng đặt.

| Tiêu chí | BatchStatus | ExitStatus |
|---|---|---|
| Kiểu | Enum | Value object |
| Mục đích | Trạng thái thực thi framework | Mã kết thúc và mô tả kết quả |
| Giá trị | STARTED, COMPLETED, FAILED, STOPPED... | COMPLETED, FAILED, COMPLETED_WITH_SKIPS... |
| Truy cập | `getStatus()` | `getExitStatus()` |
| Dùng trong flow | Không phải chuỗi được `on(...)` so khớp trực tiếp | Exit code được dùng cho transition |

Ví dụ, listener có thể đặt exit code `COMPLETED_WITH_SKIPS` khi step có skip:

~~~java
@Override
public ExitStatus afterStep(StepExecution stepExecution) {
    if (stepExecution.getSkipCount() > 0
            && stepExecution.getStatus() == BatchStatus.COMPLETED) {
        return new ExitStatus("COMPLETED_WITH_SKIPS");
    }
    return null;
}
~~~

Trong trường hợp này, BatchStatus của step vẫn có thể là `COMPLETED`; mã exit chỉ bổ sung thông tin để flow chọn nhánh phù hợp. `on("COMPLETED_WITH_SKIPS")` so khớp exit code, không phải một BatchStatus mới.

## 12. Ảnh hưởng của flow transition tới trạng thái job cuối

Flow quyết định cách job kết thúc sau khi một step trả về exit status. Các transition phổ biến:

- `.to(nextStep)`: tiếp tục sang step/flow khác.
- `.end()`: kết thúc flow theo nhánh hoàn thành.
- `.fail()`: kết thúc flow với kết quả thất bại.
- `.stop()`: kết thúc flow ở trạng thái dừng.

Ví dụ, một step có exit code `VALIDATION_REJECTED` có thể được xử lý theo quy tắc nghiệp vụ:

~~~java
return new JobBuilder("validateAndImportJob", jobRepository)
        .start(validateStep)
            .on("VALIDATION_REJECTED").end()
        .from(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("*").fail()
        .end()
        .build();
~~~

Trong nhánh `.end()`, flow có thể kết thúc với trạng thái job hoàn thành theo cấu hình transition, dù step trước đó có một exit code thể hiện dữ liệu bị từ chối. Đây là hành vi có chủ đích nếu nghiệp vụ xem từ chối đầu vào là một kết quả được xử lý bình thường. Nếu muốn job được đánh dấu thất bại và có thể restart theo chính sách, hãy dùng nhánh `.fail()` thích hợp.

Tương tự, `.stop()` dùng khi cần kết thúc job ở trạng thái dừng và có thể restart từ điểm được cấu hình. Hãy kiểm thử trạng thái cuối của `JobExecution`, không chỉ dựa vào tên method hoặc status của step.

## 13. Dừng job và restart

`STOPPED` thường có ý nghĩa khác với `FAILED`: job đã được yêu cầu dừng và kết thúc theo cơ chế stop, thay vì kết thúc do một lỗi không xử lý được. Một execution `STOPPED` thường có thể được restart nếu job và step hỗ trợ restart.

Quy trình thường gặp:

1. Job đang ở `STARTED`.
2. Người vận hành gọi `JobOperator.stop(executionId)`.
3. Job chuyển sang `STOPPING` trong khi framework xử lý yêu cầu.
4. Các step kết thúc tại điểm an toàn phù hợp.
5. JobExecution chuyển sang `STOPPED`.
6. Người vận hành restart cùng JobInstance bằng identifying parameters ban đầu.

Restart không nhất thiết chạy lại mọi step từ đầu. Spring Batch sử dụng metadata và checkpoint để xác định step đã hoàn thành và step cần tiếp tục. Step đã hoàn thành thường được bỏ qua trong restart thông thường, trừ khi cấu hình như `allowStartIfComplete` yêu cầu chạy lại.

Không dùng `STOPPED` như cách thay thế cho `FAILED` khi có lỗi nghiệp vụ. Dừng có chủ đích và thất bại là hai kết quả khác nhau; dashboard và quy trình vận hành cần phân biệt chúng.

## 14. Kiểm tra trạng thái sau khi chạy đồng bộ

Với launcher đồng bộ, có thể kiểm tra trạng thái ngay sau `run()`:

~~~java
JobExecution execution = jobLauncher.run(job, parameters);

switch (execution.getStatus()) {
    case COMPLETED ->
            log.info("Job completed: {}", execution.getId());
    case FAILED ->
            log.error("Job failed: {}", execution.getId());
    case STOPPED ->
            log.warn("Job stopped: {}", execution.getId());
    default ->
            log.info("Job status is {}", execution.getStatus());
}
~~~

Không nên chỉ dùng status để quyết định dữ liệu đã sẵn sàng cho downstream. Với `COMPLETED`, hãy kiểm tra thêm ExitStatus, skip count, reconciliation và trạng thái batch nghiệp vụ nếu output có thể partial.

Nếu job launcher được cấu hình bất đồng bộ, code trên có thể chạy khi execution vẫn đang `STARTING` hoặc `STARTED`. Trong trường hợp đó, cần trả execution ID và cho client tra cứu trạng thái sau.

## 15. Tra cứu trạng thái mới nhất bằng JobExplorer

`JobExplorer` là API chỉ đọc để tra cứu metadata đã lưu trong `JobRepository`. Nó hữu ích cho dashboard, API trạng thái và các tác vụ vận hành không nằm trong thread khởi chạy job.

~~~java
@Service
public class JobStatusService {

    private final JobExplorer jobExplorer;

    public JobStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public BatchStatus getStatus(long executionId) {
        JobExecution execution =
                jobExplorer.getJobExecution(executionId);

        if (execution == null) {
            throw new NoSuchElementException(
                    "JobExecution not found: " + executionId);
        }

        return execution.getStatus();
    }
}
~~~

Khi launcher chạy bất đồng bộ, hãy tải lại execution bằng ID để đọc trạng thái mới nhất thay vì giữ object cũ trong request. `JobExplorer` đọc metadata; không sửa status trên object được tải rồi mong thay đổi được ghi ngược vào repository.

Một API trạng thái có thể trả DTO gồm:

- `executionId`, `jobName`, `jobInstanceId`.
- `batchStatus` và `exitCode`.
- `startTime`, `endTime`, `lastUpdated`.
- Tên và trạng thái từng step.
- Các bộ đếm tiến độ đã được chọn.

Không trả toàn bộ ExecutionContext hoặc exception payload cho người dùng nếu chưa kiểm soát quyền truy cập và dữ liệu nhạy cảm.

## 16. Kiểm tra job đang chạy và tránh khởi chạy trùng

Trong ứng dụng điều phối, có thể cần biết một JobInstance đã có execution đang chạy hay chưa. `JobExplorer` cung cấp các API truy vấn instance/execution; `JobOperator` cung cấp thao tác vận hành như start, stop, restart và abandon tùy cấu hình.

Không nên chỉ kiểm tra trạng thái trong một biến local rồi mới gọi launcher. Hai node có thể đồng thời đọc rằng chưa có job chạy và cùng gửi yêu cầu khởi chạy. `JobRepository` và cơ chế tạo execution của Spring Batch là nơi quản lý định danh và đồng thời; ứng dụng cần xử lý các exception như instance đang chạy hoặc instance đã hoàn thành.

Ví dụ kiểm tra trạng thái từ repository trước khi hiển thị:

~~~java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    boolean running =
            execution.getStatus() == BatchStatus.STARTING
            || execution.getStatus() == BatchStatus.STARTED
            || execution.getStatus() == BatchStatus.STOPPING;

    if (running) {
        log.info("Execution {} has not reached a terminal state", executionId);
    }
}
~~~

Kiểm tra này phục vụ hiển thị/troubleshooting. Nó không thay thế cơ chế concurrency control của `JobRepository` khi khởi chạy.

## 17. Status và restartability

BatchStatus là một yếu tố quan trọng khi quyết định restart, nhưng không phải yếu tố duy nhất.

| Trạng thái execution | Hướng xử lý thường gặp |
|---|---|
| `COMPLETED` | JobInstance đã hoàn thành; không restart lại cùng instance theo cách thông thường |
| `FAILED` | Có thể restart nếu job restartable, metadata hợp lệ và step cho phép |
| `STOPPED` | Thường có thể restart từ trạng thái đã lưu nếu cấu hình hỗ trợ |
| `ABANDONED` | Không tiếp tục restart execution này theo quy trình thông thường |
| `UNKNOWN` | Cần điều tra và phục hồi có kiểm soát trước khi quyết định |
| `STARTING` / `STARTED` | Đang chạy; không coi là execution đã kết thúc để restart |
| `STOPPING` | Yêu cầu dừng đang được xử lý; chờ trạng thái cuối trước khi restart |

Các điều kiện khác gồm:

- Job có bị cấu hình `preventRestart()` hay không.
- Step đã hoàn thành có được phép chạy lại qua `allowStartIfComplete` hay không.
- Reader/writer có lưu và khôi phục state phù hợp không.
- Identifying JobParameters có giống lần chạy trước không.
- Side effect của writer có idempotent khi phần chưa commit được xử lý lại không.

Một job `FAILED` không tự động bảo đảm restart an toàn. Trước khi restart, cần kiểm tra dữ liệu đã commit, output ngoài transaction và trạng thái dependency.

## 18. JobExecution status trong parallel flow

Khi job có parallel flow qua `split(TaskExecutor)`, nhiều step có thể chạy đồng thời nhưng vẫn thuộc một `JobExecution`. `JobExecution` giữ trạng thái cấp job; mỗi `StepExecution` giữ trạng thái riêng của nhánh/step.

Ví dụ:

| Flow | Step | BatchStatus |
|---|---|---|
| Customer flow | `importCustomersStep` | `COMPLETED` |
| Product flow | `importProductsStep` | `FAILED` |
| Job | `parallelImportJob` | Thường `FAILED` nếu flow kết thúc do nhánh lỗi |

Không suy ra job status từ một nhánh duy nhất. Khi điều tra, xem tất cả step executions, exit status và flow transition. Nếu job được thiết kế có nhánh recovery cho một flow lỗi, trạng thái cuối còn phụ thuộc nhánh recovery và cách flow kết thúc.

Các transaction của từng step/flow là độc lập. Một flow thất bại không rollback các chunk đã commit của flow khác. Vì vậy, JobExecution `FAILED` không đồng nghĩa mọi output của parallel flow đều bị hủy.

## 19. Thời gian và metadata liên quan tới status

Ngoài BatchStatus, `JobExecution` có các mốc thời gian hữu ích:

- `startTime`: thời điểm execution bắt đầu.
- `endTime`: thời điểm execution kết thúc, nếu đã kết thúc.
- `lastUpdated`: thời điểm metadata execution được cập nhật gần nhất.

Có thể dùng các trường này để tính thời lượng và phát hiện execution có dấu hiệu bị treo. Tuy nhiên, `lastUpdated` không phải heartbeat bảo đảm rằng job đang xử lý item; một step dài có thể không cập nhật metadata thường xuyên tùy cấu hình và điểm checkpoint.

Ví dụ:

~~~java
Duration duration = null;
if (execution.getStartTime() != null
        && execution.getEndTime() != null) {
    duration = Duration.between(
            execution.getStartTime(),
            execution.getEndTime());
}
~~~

Để phát hiện job bị treo, cần kết hợp status, lastUpdated, log, metric của step, thread dump và trạng thái dependency. Không tự đánh dấu `FAILED` chỉ vì execution không cập nhật trong một khoảng thời gian nếu chưa xác minh tiến trình thực tế.

## 20. Kiểm thử BatchStatus của JobExecution

Kiểm thử nên xác nhận trạng thái cấp job, trạng thái từng step và kết quả nghiệp vụ.

Các trường hợp nên có:

1. Job thành công: xác nhận `JobExecution` kết thúc `COMPLETED`.
2. Exception không xử lý: xác nhận job/step có `FAILED` theo flow mặc định.
3. Stop: yêu cầu stop một job đang chạy và xác nhận cuối cùng là `STOPPED` khi framework xử lý xong.
4. Restart sau FAILED: cùng identifying JobParameters tạo execution mới cho cùng JobInstance và job tiếp tục theo checkpoint.
5. Restart sau STOPPED: xác nhận step tiếp tục theo trạng thái đã lưu.
6. Flow end/fail/stop: xác nhận transition quyết định đúng trạng thái cuối của JobExecution.
7. Custom ExitStatus: xác nhận exit code tùy chỉnh không bị nhầm thành BatchStatus mới.
8. Parallel flow: xác nhận trạng thái từng nhánh và trạng thái job tổng thể.
9. Async launcher: xác nhận object ban đầu có thể chưa phải trạng thái cuối và JobExplorer trả trạng thái mới.
10. Completed instance: xác nhận không khởi chạy lại cùng JobInstance như một batch mới ngoài ý muốn.

Ví dụ test thành công:

~~~java
JobExecution execution =
        jobLauncherTestUtils.launchJob(jobParameters);

assertEquals(BatchStatus.COMPLETED, execution.getStatus());
assertNotNull(execution.getEndTime());

StepExecution step = execution.getStepExecutions()
        .stream()
        .filter(item -> item.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, step.getStatus());
assertEquals(100, step.getWriteCount());
~~~

Ví dụ này giả định job chạy đồng bộ, step được thực thi và writer ghi đúng 100 item. Nếu processor filter hoặc step có skip, write count cần được điều chỉnh theo dữ liệu test.

Với test stop hoặc async, cần đồng bộ test bằng latch/barrier hoặc polling có timeout thay vì dùng sleep tùy tiện. Test restart cần giữ JobRepository metadata giữa lần chạy đầu và lần restart.

## 21. Những lỗi thường gặp

**Coi STARTED là job đã chạy thành công.** STARTED chỉ biểu thị đang thực thi. Chỉ đọc kết quả cuối sau khi execution đạt trạng thái kết thúc.

**Coi STOPPING là đã dừng.** STOPPING là yêu cầu đang được xử lý; chờ STOPPED trước khi restart hoặc giải phóng tài nguyên.

**Cho rằng FAILED nghĩa là mọi dữ liệu rollback.** Các chunk/step đã commit vẫn tồn tại. Đối chiếu dữ liệu và checkpoint.

**Cho rằng COMPLETED đồng nghĩa dữ liệu đầy đủ.** Job có thể skip/filter item hoặc flow có nhánh kết thúc có chủ đích. Kiểm tra ExitStatus, counters và reconciliation.

**Nhầm BatchStatus với ExitStatus.** BatchStatus là enum vòng đời; ExitStatus là mã kết thúc dùng cho transition. Đọc cả hai.

**Đọc trạng thái từ object cũ khi launcher async.** Tải lại bằng JobExplorer theo execution ID.

**Restart job đang STARTED hoặc STOPPING.** Trước hết xác minh execution cũ đã kết thúc và repository phản ánh trạng thái cuối.

**Tạo identifying JobParameters mới khi restart.** Có thể tạo JobInstance mới và xử lý lại từ đầu. Giữ identifying parameters của batch gốc.

**Tự sửa BatchStatus trong database.** Bảng metadata do Spring Batch quản lý. Dùng JobOperator và quy trình recovery có kiểm soát.

**Chỉ nhìn JobExecution mà không xem StepExecution.** Trạng thái cấp job không chỉ ra đầy đủ step nào thất bại hoặc nhánh nào chưa chạy.

## 22. Quy trình đọc và xử lý BatchStatus

Khi nhận một execution ID từ API hoặc dashboard, có thể làm theo trình tự:

1. Dùng `JobExplorer` tải `JobExecution` mới nhất.
2. Đọc `BatchStatus` để xác định execution đang chạy hay đã kết thúc.
3. Đọc `ExitStatus` để hiểu mã kết thúc và nhánh flow.
4. Duyệt `StepExecution` để tìm step đang chạy, thất bại, dừng hoặc hoàn thành.
5. Đọc bộ đếm, exception và checkpoint để điều tra.
6. Đối chiếu dữ liệu nghiệp vụ và side effect đã commit.
7. Nếu đang chạy, tiếp tục theo dõi; nếu STOPPING, chờ stop hoàn tất.
8. Nếu FAILED hoặc STOPPED, xác định restartability và dùng cùng identifying parameters khi restart.
9. Nếu ABANDONED hoặc UNKNOWN, theo runbook phục hồi và audit trước khi thực hiện hành động tiếp theo.
10. Nếu COMPLETED, chỉ công bố output sau khi điều kiện completeness nghiệp vụ đã đạt.

## Kết luận

`BatchStatus` của `JobExecution` mô tả vòng đời của một lần chạy job: `STARTING`, `STARTED`, `STOPPING`, `STOPPED`, `COMPLETED`, `FAILED`, `ABANDONED` hoặc `UNKNOWN`. Trạng thái giúp hệ thống biết execution đang chạy, đã hoàn tất, thất bại hay cần can thiệp vận hành. Nó thuộc về `JobExecution`, vì cùng một `JobInstance` có thể có nhiều execution do restart.

Hãy phân biệt `BatchStatus` với `ExitStatus`, đọc trạng thái từng `StepExecution` và kiểm tra dữ liệu nghiệp vụ trước khi kết luận batch thành công. `STOPPED` và `FAILED` có thể restart nếu cấu hình và metadata cho phép; `ABANDONED` không tiếp tục theo cách thông thường; `UNKNOWN` cần điều tra trước khi hành động. Với launcher bất đồng bộ, dùng `JobExplorer` để đọc trạng thái mới nhất. Trạng thái framework là cơ sở điều phối, còn tính đầy đủ và chính xác của output phải được xác nhận bằng kiểm tra nghiệp vụ riêng.
