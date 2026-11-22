# JobInstance, JobExecution và StepExecution

Spring Batch phân biệt định nghĩa quy trình batch với từng đơn vị công việc và từng lần thực thi. Ba đối tượng `JobInstance`, `JobExecution` và `StepExecution` mô tả ba cấp độ khác nhau của quá trình đó. Hiểu đúng mối quan hệ giữa chúng giúp thiết kế tham số khởi chạy, theo dõi lịch sử, xử lý lỗi và restart một Job an toàn.

- `JobInstance` đại diện cho một đơn vị công việc logic của một Job, được xác định bằng tên Job và các JobParameter có tính định danh.
- `JobExecution` đại diện cho một lần thử thực thi cụ thể của JobInstance.
- `StepExecution` đại diện cho một lần thực thi cụ thể của một Step trong một JobExecution.

Một Job có thể xử lý nhiều đơn vị công việc, mỗi đơn vị có thể cần nhiều lần thử chạy, và mỗi lần thử có thể thực thi nhiều Step. Spring Batch lưu metadata của các đối tượng này trong `JobRepository` để có thể theo dõi lịch sử và hỗ trợ khôi phục.

## 1. Nhìn tổng thể mối quan hệ

Giả sử ứng dụng có Job `dailySalesJob` để tổng hợp doanh thu theo ngày. Mỗi ngày nghiệp vụ là một đơn vị công việc riêng. Quy trình gồm ba Step: kiểm tra dữ liệu đầu vào, tổng hợp giao dịch và xuất báo cáo.

```text
Job definition: dailySalesJob
        |
        +---------------------------------------+
        |                                       |
        v                                       v
JobInstance A                             JobInstance B
businessDate=2026-11-15                   businessDate=2026-11-16
        |                                       |
        v                                       v
JobExecution #101                         JobExecution #102
        |                                       |
        +--> StepExecution: validate             +--> StepExecution: validate
        +--> StepExecution: aggregate            +--> StepExecution: aggregate
        +--> StepExecution: publish             +--> StepExecution: publish
```

Nếu lần chạy ngày 15 thất bại ở Step tổng hợp và sau đó được restart, cấu trúc sẽ có thêm một JobExecution cho chính JobInstance ngày 15:

```text
dailySalesJob
  |
  +--> JobInstance A: businessDate=2026-11-15
         |
         +--> JobExecution #101: FAILED
         |       validateInputStep       COMPLETED
         |       aggregateSalesStep      FAILED
         |
         +--> JobExecution #103: COMPLETED
                 aggregateSalesStep      COMPLETED
                 publishReportStep       COMPLETED
```

JobInstance vẫn là cùng một đơn vị công việc logic. Lần restart tạo JobExecution mới, còn lịch sử của lần chạy trước được giữ lại. Spring Batch đánh giá trạng thái Step và chính sách restart để quyết định Step nào cần thực hiện trong lần chạy mới.

## 2. JobInstance: một đơn vị công việc logic

`JobInstance` là sự kết hợp giữa tên của Job và các tham số định danh (`identifying JobParameters`). Nó trả lời câu hỏi: **đây là công việc logic nào cần được xử lý?**

Ví dụ, `dailySalesJob` xử lý doanh thu theo ngày. Nếu `businessDate` là tham số định danh, hai ngày khác nhau tạo ra hai JobInstance:

```text
Job name: dailySalesJob

businessDate=2026-11-15  --> JobInstance A
businessDate=2026-11-16  --> JobInstance B
```

Hai JobInstance sử dụng cùng một định nghĩa Job, nhưng đại diện cho hai đơn vị dữ liệu khác nhau. Mỗi instance có định danh riêng trong metadata của Spring Batch.

### JobParameters quyết định danh tính như thế nào?

Khi khởi chạy Job, ứng dụng truyền vào `JobParameters`. Mỗi tham số có thể được đánh dấu là định danh hoặc không định danh:

- Tham số định danh tham gia xác định JobInstance.
- Tham số không định danh vẫn có thể được dùng làm dữ liệu đầu vào, nhưng không làm thay đổi danh tính JobInstance.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Trong ví dụ trên, `businessDate` là tham số định danh, còn `requestedBy` không tham gia định danh. Nếu khởi chạy cùng Job với cùng `businessDate` nhưng thay đổi `requestedBy`, Spring Batch vẫn nhận diện cùng một JobInstance.

Việc chọn tham số định danh cần phản ánh đơn vị nghiệp vụ mà Job xử lý. Một số ví dụ thường gặp:

| Loại Job | Tham số định danh có thể dùng |
|---|---|
| Tổng hợp giao dịch theo ngày | `businessDate` |
| Nhập một tệp cụ thể | `fileId` hoặc mã lô nhập |
| Đối soát theo kỳ | `settlementPeriod` |
| Tạo báo cáo theo khách hàng và kỳ | `customerId` kết hợp `reportPeriod` |

Nếu chọn thiếu tham số định danh, hai công việc nghiệp vụ khác nhau có thể bị xem là cùng một JobInstance. Nếu thêm tham số định danh thay đổi ở mỗi lần chạy một cách tùy tiện, cùng một đơn vị dữ liệu có thể bị xem là công việc mới và bị xử lý lặp lại.

### Điều gì xảy ra khi khởi chạy cùng JobParameters?

Spring Batch kiểm tra JobInstance tương ứng trong `JobRepository` trước khi tạo lần thực thi mới. Kết quả phụ thuộc vào lịch sử của instance:

| Tình trạng của JobInstance | Hành vi thường gặp |
|---|---|
| Chưa từng được chạy | Tạo JobInstance và JobExecution mới. |
| Đang có JobExecution chạy | Từ chối lần khởi chạy trùng, thường bằng `JobExecutionAlreadyRunningException`. |
| JobExecution trước đã `COMPLETED` | Không cho chạy lại cùng instance như một công việc mới, thường bằng `JobInstanceAlreadyCompleteException`. |
| Lần chạy trước `FAILED` hoặc `STOPPED` | Có thể tạo JobExecution mới để restart nếu Job và các Step cho phép. |

Các quy tắc này giúp ngăn một đơn vị công việc bị khởi chạy trùng ngoài ý muốn. Nếu nghiệp vụ thực sự cần xử lý một đơn vị mới, hãy cung cấp bộ tham số định danh tương ứng với đơn vị mới.

## 3. JobExecution: một lần thử thực thi JobInstance

`JobExecution` ghi nhận một lần cụ thể mà Spring Batch cố gắng thực hiện JobInstance. Nó trả lời câu hỏi: **lần chạy này đã diễn ra như thế nào và kết thúc với trạng thái gì?**

Một JobInstance có thể có nhiều JobExecution khi lần chạy trước thất bại hoặc bị dừng và sau đó được restart:

```text
JobInstance: dailySalesJob / businessDate=2026-11-15
       |
       +--> JobExecution #101: FAILED
       |
       +--> JobExecution #103: COMPLETED
```

Mỗi JobExecution có ID riêng và lưu thông tin của lần thực thi đó, chẳng hạn:

- Thời điểm tạo, thời điểm bắt đầu và thời điểm kết thúc.
- Trạng thái `BatchStatus` như `STARTING`, `STARTED`, `COMPLETED`, `FAILED` hoặc `STOPPED`.
- `ExitStatus` mô tả mã kết quả thoát.
- Các lỗi thực thi được ghi nhận.
- Các `StepExecution` phát sinh trong lần chạy.
- `ExecutionContext` ở cấp Job, dùng lưu trạng thái cần thiết cho quá trình thực thi và restart.

`JobExecution` thuộc về một JobInstance. Khi restart, Spring Batch tạo JobExecution mới thay vì ghi đè lịch sử của lần chạy thất bại. Nhờ đó, người vận hành có thể so sánh các lần thử, xem lỗi cũ và xác định lần nào đã hoàn tất.

### Vòng đời JobExecution

Một JobExecution thường đi qua các trạng thái trong quá trình khởi chạy và thực hiện:

```text
STARTING --> STARTED
                |
                +--> COMPLETED
                |
                +--> FAILED
                |
                +--> STOPPING --> STOPPED
```

Các trạng thái cuối phổ biến gồm:

| BatchStatus | Ý nghĩa |
|---|---|
| `COMPLETED` | Job kết thúc bình thường theo luồng đã cấu hình. |
| `FAILED` | Job thất bại do lỗi được phản ánh lên lần thực thi. |
| `STOPPED` | Job được dừng có kiểm soát. Có thể restart nếu cấu hình cho phép. |
| `ABANDONED` | Execution được đánh dấu không tiếp tục theo cách restart thông thường. |
| `UNKNOWN` | Không xác định chắc chắn trạng thái; cần kiểm tra metadata và tình trạng thực tế. |

`BatchStatus` khác `ExitStatus`. `BatchStatus` biểu diễn trạng thái vòng đời mà Spring Batch quản lý; `ExitStatus` là mã kết quả thoát có thể được dùng trong điều khiển luồng. Hai giá trị thường tương ứng trong trường hợp mặc định, nhưng không phải cùng một thuộc tính.

## 4. StepExecution: một lần thực thi Step

`StepExecution` ghi nhận một lần thực thi cụ thể của một Step trong một JobExecution. Nó trả lời câu hỏi: **Step này đã xử lý bao nhiêu dữ liệu, kết thúc ra sao và có lỗi gì?**

Ví dụ, Job tổng hợp doanh thu có ba Step:

```text
JobExecution #101
       |
       +--> StepExecution: validateInputStep
       |
       +--> StepExecution: aggregateSalesStep
       |
       +--> StepExecution: publishReportStep
```

Mỗi StepExecution lưu thông tin riêng về lần chạy của Step đó. Các trường thường được dùng khi theo dõi gồm:

| Thông tin | Ý nghĩa |
|---|---|
| Step name | Tên Step được thực thi. |
| `BatchStatus` | Trạng thái thực thi của Step. |
| `ExitStatus` | Mã kết quả thoát của Step; có thể tham gia chọn nhánh tiếp theo. |
| Start time / end time | Thời điểm bắt đầu và kết thúc. |
| `readCount` | Số bản ghi đã đọc. |
| `writeCount` | Số bản ghi đã ghi. |
| `filterCount` | Số bản ghi bị lọc trong quá trình xử lý. |
| `readSkipCount`, `processSkipCount`, `writeSkipCount` | Số bản ghi bị bỏ qua ở từng giai đoạn. |
| `commitCount`, `rollbackCount` | Số lần commit và rollback được ghi nhận. |
| `ExecutionContext` | Trạng thái của Step được lưu để hỗ trợ khôi phục khi restart. |

Những số liệu này giúp tìm vị trí xảy ra lỗi. Chẳng hạn, `readCount` tăng nhưng `writeCount` không tăng có thể gợi ý vấn đề ở Processor, Writer hoặc transaction; cần đọc thêm log và exception để kết luận chính xác.

### StepExecution gắn với JobExecution nào?

Một StepExecution thuộc về JobExecution đã thực hiện Step đó. Khi JobInstance được restart, JobExecution mới sẽ có các StepExecution tương ứng với những Step được thực thi trong lần chạy mới. Các StepExecution cũ vẫn gắn với JobExecution cũ, giúp giữ lại lịch sử.

Với Step đã hoàn thành ở lần chạy trước, Spring Batch thường bỏ qua Step đó khi restart nếu `allowStartIfComplete` không được bật. Step không được chạy lại sẽ không tạo một lần thực thi mới trong JobExecution hiện tại. Nếu Step cần chạy lại mỗi lần restart, có thể cấu hình `allowStartIfComplete(true)` khi phù hợp với nghiệp vụ.

## 5. Phân biệt ba đối tượng

| Tiêu chí | `JobInstance` | `JobExecution` | `StepExecution` |
|---|---|---|---|
| Đại diện cho | Một đơn vị công việc logic | Một lần thử chạy Job | Một lần thử chạy Step |
| Được xác định/gắn với | Tên Job + identifying JobParameters | Một JobInstance và ID lần chạy | Một Step và JobExecution chứa nó |
| Số lượng | Một Job có thể có nhiều instance | Một instance có thể có nhiều execution | Một JobExecution có các execution của Step được thực hiện |
| Dữ liệu nổi bật | Job name, JobKey, identifying parameters | Thời gian chạy, BatchStatus, ExitStatus, lỗi, Job ExecutionContext | Trạng thái Step, bộ đếm đọc/ghi/skip, Step ExecutionContext |
| Vai trò khi restart | Giữ nguyên nếu restart cùng đơn vị công việc | Tạo execution mới cho lần thử mới | Ghi nhận các Step được thực thi trong lần thử mới |

Cách nhớ ngắn gọn:

- `JobInstance`: *cần xử lý công việc nào?*
- `JobExecution`: *đã thử chạy công việc đó lần thứ mấy và kết quả ra sao?*
- `StepExecution`: *mỗi Step trong lần thử đó đã thực hiện như thế nào?*

## 6. JobRepository lưu các đối tượng này như thế nào?

`JobRepository` là thành phần quản lý metadata của Spring Batch. Khi Job được khởi chạy và các Step thực hiện, Spring Batch sử dụng repository để tạo mới hoặc cập nhật thông tin về JobInstance, JobExecution, StepExecution và ExecutionContext.

Với cấu hình repository dựa trên cơ sở dữ liệu, schema metadata mặc định có các bảng quen thuộc:

| Bảng | Nội dung chính |
|---|---|
| `BATCH_JOB_INSTANCE` | Thông tin định danh của JobInstance, gồm tên Job và JobKey. |
| `BATCH_JOB_EXECUTION` | Các lần thực thi của JobInstance và trạng thái từng lần. |
| `BATCH_JOB_EXECUTION_PARAMS` | Các JobParameters của lần thực thi, bao gồm thông tin tham số định danh. |
| `BATCH_STEP_EXECUTION` | Metadata và bộ đếm của từng StepExecution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | ExecutionContext ở cấp JobExecution. |
| `BATCH_STEP_EXECUTION_CONTEXT` | ExecutionContext ở cấp StepExecution. |

Các bảng này tạo nên lịch sử có thể truy vấn sau khi ứng dụng khởi động lại. Chúng lưu **metadata thực thi**, không phải dữ liệu nghiệp vụ chính. Ví dụ, các bản ghi giao dịch bán hàng được lưu trong bảng nghiệp vụ của ứng dụng; repository lưu trạng thái cho biết Job tổng hợp giao dịch nào đã chạy, Step nào đã hoàn thành và checkpoint ở đâu.

Trong môi trường production, nên sử dụng repository có lưu trữ bền vững để hỗ trợ theo dõi và restart. Repository dạng in-memory thường không giữ được lịch sử qua lần dừng ứng dụng.

## 7. ExecutionContext ở cấp Job và cấp Step

`ExecutionContext` là vùng lưu trữ key-value mà Spring Batch quản lý cùng metadata thực thi. Nó thường được dùng để giữ trạng thái cần thiết khi một Job hoặc Step được khởi động lại.

Spring Batch có hai phạm vi chính:

- **Job ExecutionContext:** gắn với JobExecution, phù hợp cho dữ liệu trạng thái cần chia sẻ giữa các Step trong cùng một lần chạy Job.
- **Step ExecutionContext:** gắn với StepExecution, phù hợp cho trạng thái riêng của Step, ví dụ vị trí hiện tại của một reader.

Với xử lý theo chunk, reader có thể lưu thông tin vị trí đọc sau mỗi lần commit. Nếu lần chạy thất bại, lần restart có thể dùng thông tin đã lưu để tiếp tục từ checkpoint thích hợp. Mức độ khôi phục phụ thuộc vào việc thành phần xử lý có hỗ trợ lưu trạng thái và được cấu hình đúng hay không.

Không nên đưa mọi dữ liệu nghiệp vụ vào ExecutionContext. Context nên chứa trạng thái nhỏ, cần thiết để điều phối hoặc khôi phục. Dữ liệu lớn và dữ liệu nghiệp vụ vẫn nên nằm trong hệ thống lưu trữ phù hợp.

## 8. Ví dụ tạo JobParameters, khởi chạy và xem các execution

Ví dụ dưới đây dùng Spring Batch 5 trở lên. `businessDate` xác định đơn vị công việc; `requestedBy` chỉ ghi nhận nguồn yêu cầu và không tham gia định danh.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.stereotype.Component;

@Component
public class DailySalesJobRunner {

    private final JobLauncher jobLauncher;
    private final Job dailySalesJob;

    public DailySalesJobRunner(
            JobLauncher jobLauncher,
            Job dailySalesJob) {
        this.jobLauncher = jobLauncher;
        this.dailySalesJob = dailySalesJob;
    }

    public void runForDate(String businessDate) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("requestedBy", "scheduler", false)
                .toJobParameters();

        JobExecution jobExecution =
                jobLauncher.run(dailySalesJob, parameters);

        System.out.println("JobInstance ID: "
                + jobExecution.getJobInstance().getInstanceId());
        System.out.println("JobExecution ID: " + jobExecution.getId());
        System.out.println("Job status: " + jobExecution.getStatus());

        for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
            System.out.printf(
                    "Step=%s, status=%s, read=%d, write=%d, skips=%d%n",
                    stepExecution.getStepName(),
                    stepExecution.getStatus(),
                    stepExecution.getReadCount(),
                    stepExecution.getWriteCount(),
                    stepExecution.getSkipCount());
        }
    }
}
```

Đoạn code minh họa cách đọc thông tin execution sau khi gọi launcher. Nếu `JobLauncher` chạy đồng bộ, khi `run` trả về, JobExecution thường đã có trạng thái cuối. Nếu dùng launcher bất đồng bộ, Job có thể vẫn đang chạy; trạng thái đọc ngay sau `run` có thể là `STARTING` hoặc `STARTED`. Khi đó cần theo dõi execution qua cơ chế phù hợp thay vì coi trạng thái ban đầu là kết quả cuối.

`JobExecution` cung cấp truy cập đến JobInstance và tập hợp StepExecution của lần chạy. Trong ứng dụng thực tế, có thể dùng các đối tượng này để ghi log, hiển thị tiến độ hoặc gửi thông tin cho hệ thống giám sát.

## 9. Theo dõi lịch sử bằng JobExplorer

`JobExplorer` cung cấp API chỉ đọc để tra cứu metadata thực thi đã lưu trong `JobRepository`. Đây là công cụ hữu ích cho trang quản trị hoặc tác vụ giám sát cần tìm JobInstance, JobExecution và StepExecution mà không trực tiếp sửa metadata.

Các thao tác tra cứu thường gặp gồm:

- Tìm các JobInstance theo tên Job và tham số.
- Lấy danh sách JobExecution của một JobInstance.
- Lấy một JobExecution theo ID.
- Xem các StepExecution thuộc một JobExecution.
- Đọc ExecutionContext để điều tra trạng thái đã lưu.

Ví dụ truy vấn một JobExecution theo ID:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class BatchExecutionQueryService {

    private final JobExplorer jobExplorer;

    public BatchExecutionQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

Kết quả tra cứu có thể là `null` nếu không có execution tương ứng. `JobExplorer` phục vụ việc quan sát lịch sử; các thao tác điều khiển như khởi chạy, dừng hoặc restart thuộc những API điều phối tương ứng, không nên thực hiện bằng cách sửa trực tiếp các bảng metadata.

## 10. Các lỗi thiết kế thường gặp

| Vấn đề | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng tham số thời gian hiện tại làm identifying parameter cho mọi lần gọi | Mỗi lần gọi có thể tạo JobInstance mới, làm restart không nối lại instance cũ. | Chọn tham số định danh đại diện cho đơn vị nghiệp vụ, như ngày dữ liệu hoặc mã lô. |
| Không đánh dấu đúng identifying parameters | Các công việc khác nhau có thể bị nhận diện là cùng instance. | Xem lại ý nghĩa nghiệp vụ và cờ identifying của từng JobParameter. |
| Nghĩ JobExecution và JobInstance là một | Có thể nhầm lần restart là công việc mới hoặc ghi đè ý nghĩa lịch sử. | Giữ phân biệt đơn vị công việc logic với từng lần thử chạy. |
| Chỉ xem trạng thái JobExecution | Không biết Step nào thất bại hoặc đã xử lý bao nhiêu bản ghi. | Xem các StepExecution, bộ đếm, exception và log liên quan. |
| Cho rằng FAILED sẽ rollback mọi dữ liệu | Các chunk đã commit hoặc Step trước đã hoàn thành có thể vẫn giữ thay đổi. | Thiết kế restart idempotent và kiểm tra dữ liệu đã xử lý. |
| Lưu dữ liệu nghiệp vụ lớn vào ExecutionContext | Metadata khó quản lý và không phù hợp làm nơi lưu trữ nghiệp vụ. | Chỉ lưu checkpoint và trạng thái cần cho điều phối; dữ liệu chính nằm trong kho nghiệp vụ. |
| Chỉnh sửa trực tiếp các bảng BATCH_* để sửa trạng thái | Có thể làm metadata mất nhất quán và gây lỗi restart. | Dùng API Spring Batch và quy trình vận hành phù hợp. |

## 11. Áp dụng khi điều tra một Job thất bại

Khi một Job thất bại, có thể lần theo ba cấp độ theo thứ tự:

1. **Xác định JobInstance.** Kiểm tra tên Job và identifying JobParameters để chắc chắn đang xem đúng ngày dữ liệu, mã lô hoặc kỳ nghiệp vụ.
2. **Xem các JobExecution.** Tìm lần chạy mới nhất, trạng thái cuối, thời gian chạy và exception. Đối chiếu với các lần chạy trước để biết đây có phải lần restart hay không.
3. **Xem các StepExecution.** Xác định Step thất bại, Step đã hoàn thành, số bản ghi đọc/ghi/bỏ qua và trạng thái ExecutionContext.
4. **Đối chiếu dữ liệu nghiệp vụ.** Xác định phần dữ liệu đã commit trước khi lỗi và đánh giá nguy cơ ghi trùng khi chạy lại.
5. **Quyết định restart.** Dùng đúng identifying JobParameters và xác nhận Job, Step hỗ trợ restart. Kiểm tra checkpoint cùng tính idempotent của thao tác ghi.

Ví dụ, `dailySalesJob` cho ngày 15 có JobExecution đầu tiên `FAILED` tại `aggregateSalesStep`. Nếu dữ liệu đầu vào đã được đọc và các chunk đầu tiên đã commit, lần restart cần tiếp tục theo checkpoint hoặc bảo đảm các thao tác được lặp lại không gây trùng. Khi Job hoàn tất, JobInstance vẫn đại diện cho ngày 15, còn JobExecution mới ghi nhận lần chạy thành công.

## Kết luận

`JobInstance`, `JobExecution` và `StepExecution` là ba cấp độ metadata bổ sung cho nhau trong Spring Batch. JobInstance xác định đơn vị công việc logic bằng tên Job và identifying JobParameters. JobExecution ghi lại từng lần thử thực thi đơn vị đó. StepExecution ghi lại kết quả và số liệu của từng Step trong một lần chạy. `JobRepository` lưu các thông tin này cùng ExecutionContext để hỗ trợ theo dõi, điều tra và restart. Khi phân biệt rõ ba cấp độ, ứng dụng có thể quản lý nhiều kỳ dữ liệu, giữ lịch sử lần chạy và khôi phục quy trình batch có kiểm soát.
