# StepExecution và trạng thái thực thi

Trong Spring Batch, `StepExecution` là đối tượng ghi nhận một lần thực thi cụ thể của một `Step`. Nó cho biết Step nào đã chạy, thuộc lần chạy Job nào, bắt đầu và kết thúc lúc nào, đang ở trạng thái nào, đã đọc hoặc ghi bao nhiêu item, có bao nhiêu lần commit hoặc rollback, và những dữ liệu trạng thái nào cần được giữ lại khi chạy tiếp.

`StepExecution` là một phần quan trọng của cơ chế quản lý và khôi phục công việc trong Spring Batch. Khi cần giải thích vì sao một Step thành công hay thất bại, theo dõi tiến độ xử lý, quyết định nhánh tiếp theo của Job hoặc tiếp tục một Job bị gián đoạn, bạn thường phải xem xét `StepExecution` cùng với `BatchStatus`, `ExitStatus`, `ExecutionContext` và `JobRepository`.

## 1. StepExecution nằm ở đâu trong mô hình thực thi?

Một Job được cấu thành từ một hoặc nhiều Step. Mỗi lần một Step được thực thi, Spring Batch tạo một đối tượng `StepExecution` để đại diện cho lần chạy đó. `StepExecution` thuộc về một `JobExecution`, còn `JobExecution` đại diện cho một lần chạy của một Job instance.

Các khái niệm có quan hệ với nhau như sau:

```text
Job
 |
 +-- JobInstance
       |
       +-- JobExecution lần chạy thứ nhất
       |      |
       |      +-- StepExecution: validateInput
       |      +-- StepExecution: importOrders
       |      +-- StepExecution: archiveFile
       |
       +-- JobExecution lần chạy lại
              |
              +-- StepExecution: importOrders
              +-- StepExecution: archiveFile
```

`JobInstance` xác định một lần nghiệp vụ của Job dựa trên tên Job và các identifying JobParameters. `JobExecution` là một lần thử chạy JobInstance đó. Nếu một Job thất bại và được khởi động lại với cùng identifying parameters, Spring Batch tạo một `JobExecution` mới cho cùng `JobInstance`. Các Step được thực thi trong lần chạy đó có `StepExecution` tương ứng.

Một `StepExecution` vì vậy không phải là bản thân định nghĩa Step. Định nghĩa Step mô tả cách công việc được thực hiện; `StepExecution` lưu thông tin của một lần thực hiện cụ thể. Cùng một Step có thể có nhiều StepExecution qua các lần chạy hoặc restart khác nhau.

Ví dụ, `importOrdersStep` có thể chạy lần đầu và thất bại sau khi xử lý một số chunk. Khi Job được restart, Spring Batch tạo một lần thực thi mới cho Step đó. Trạng thái checkpoint đã lưu có thể được dùng để tiếp tục công việc. Bản ghi StepExecution cũ vẫn là lịch sử của lần chạy trước.

## 2. StepExecution chứa những thông tin nào?

`StepExecution` cung cấp thông tin nhận diện, trạng thái, thời gian, số liệu xử lý và execution context của một lần chạy Step.

### Thông tin nhận diện và liên kết

Một số thuộc tính thường dùng:

| Thuộc tính hoặc phương thức | Ý nghĩa |
|---|---|
| `getId()` | ID của bản ghi StepExecution đã được lưu trong JobRepository. |
| `getStepName()` | Tên Step mà lần thực thi này đại diện. |
| `getJobExecution()` | JobExecution cha chứa StepExecution này. |
| `getJobExecutionId()` | ID của JobExecution cha. |
| `getVersion()` | Phiên bản metadata được dùng cho cơ chế optimistic locking. |
| `getStartTime()` | Thời điểm Step bắt đầu thực thi. |
| `getEndTime()` | Thời điểm Step kết thúc, nếu đã kết thúc. |
| `getLastUpdated()` | Thời điểm metadata StepExecution được cập nhật gần nhất. |

ID thường chỉ có giá trị sau khi JobRepository lưu đối tượng. Trong ứng dụng, nên để Spring Batch tạo và quản lý StepExecution thay vì tự tạo hoặc sửa metadata trực tiếp.

### Trạng thái và kết quả

Hai thông tin thường được đọc cùng nhau là:

- `getStatus()` trả về `BatchStatus`, mô tả trạng thái thực thi của Step.
- `getExitStatus()` trả về `ExitStatus`, mô tả kết quả kết thúc mà Spring Batch dùng trong luồng điều khiển và báo cáo.

Hai giá trị này liên quan nhưng không đồng nghĩa. `BatchStatus` cho biết Step đang chạy, đã hoàn tất, thất bại hay dừng. `ExitStatus` cho biết mã kết quả và phần mô tả của lần chạy; ứng dụng có thể tạo exit code tùy chỉnh để điều khiển nhánh Job.

### Các bộ đếm xử lý

Với Step xử lý dữ liệu, các bộ đếm giúp quan sát tiến độ và phát hiện vấn đề:

| Bộ đếm | Ý nghĩa |
|---|---|
| `getReadCount()` | Số item đã đọc thành công. |
| `getWriteCount()` | Số item đã được writer ghi. |
| `getFilterCount()` | Số item bị processor lọc, thường do processor trả về `null`. |
| `getCommitCount()` | Số lần transaction của Step đã commit. |
| `getRollbackCount()` | Số lần transaction của Step đã rollback. |
| `getReadSkipCount()` | Số item bị skip do lỗi trong lúc đọc. |
| `getProcessSkipCount()` | Số item bị skip do lỗi trong lúc xử lý. |
| `getWriteSkipCount()` | Số item bị skip do lỗi trong lúc ghi. |
| `getSkipCount()` | Tổng số item bị skip qua các giai đoạn. |

Các bộ đếm này hữu ích để theo dõi và chẩn đoán. Chúng không thay thế số liệu nghiệp vụ được lưu trong hệ thống đích. Ví dụ, `writeCount` cho biết số item writer đã ghi theo thống kê của Step, nhưng không tự chứng minh rằng mọi hệ thống bên ngoài đã nhận và xử lý dữ liệu đúng như mong muốn.

### ExecutionContext

Mỗi StepExecution có một `ExecutionContext` riêng. Đây là vùng lưu trạng thái cần tồn tại qua các lần cập nhật và có thể được dùng khi restart Step. Ví dụ, reader có thể lưu vị trí hiện tại trong tệp hoặc chỉ số trang đang đọc.

`StepExecution` còn liên kết với `JobExecution`, do đó ứng dụng có thể truy cập context cấp Job thông qua JobExecution. Cần phân biệt hai phạm vi này:

- Step `ExecutionContext` lưu trạng thái riêng của một Step, thường là checkpoint phục vụ restart Step đó.
- Job `ExecutionContext` lưu dữ liệu cần chia sẻ giữa các Step trong cùng JobExecution.

Không nên dùng hai context thay thế tùy tiện cho nhau. Chọn phạm vi theo vòng đời và nơi cần sử dụng dữ liệu.

## 3. BatchStatus: trạng thái thực thi của Step

`BatchStatus` là enum biểu diễn trạng thái vòng đời của một JobExecution hoặc StepExecution. Các giá trị thường gặp gồm:

| BatchStatus | Ý nghĩa |
|---|---|
| `STARTING` | Execution đang được khởi tạo trước khi bước vào trạng thái chạy. |
| `STARTED` | Execution đang chạy. |
| `STOPPING` | Đã nhận yêu cầu dừng và đang chờ dừng an toàn. |
| `STOPPED` | Execution đã dừng theo yêu cầu. |
| `COMPLETED` | Execution hoàn tất thành công theo trạng thái BatchStatus. |
| `FAILED` | Execution thất bại do lỗi. |
| `ABANDONED` | Execution được đánh dấu bỏ qua, thường không được restart như một Step thất bại thông thường. |
| `UNKNOWN` | Không thể xác định chắc chắn trạng thái thực thi hoặc tính an toàn của việc tiếp tục. |

Một Step thường đi từ `STARTING` sang `STARTED`, sau đó kết thúc bằng một trạng thái cuối như `COMPLETED`, `FAILED` hoặc `STOPPED`. `STOPPING` là trạng thái chuyển tiếp trong quá trình dừng. Đây là cách hiểu vòng đời phổ biến; không nên giả định mọi trạng thái đều phải xuất hiện hoặc mọi lần chạy đều đi qua một chuỗi giống hệt nhau.

### COMPLETED

`COMPLETED` biểu thị Step đã hoàn tất thành công theo trạng thái BatchStatus. Khi restart JobInstance, một Step đã hoàn tất thường được Spring Batch bỏ qua để tránh thực hiện lại công việc đã xong. Nếu nghiệp vụ cần chạy lại Step đã hoàn tất trong một lần restart, có thể cấu hình `allowStartIfComplete(true)` cho Step, nhưng phải bảo đảm tác vụ chạy lại an toàn.

### FAILED

`FAILED` biểu thị Step không hoàn tất bình thường do lỗi. Nếu cấu hình và điều kiện restart cho phép, JobInstance có thể được chạy lại. Spring Batch tạo execution mới cho lần chạy lại; trạng thái và context đã lưu của lần trước có thể được dùng để khôi phục.

Không nên hiểu rằng mọi Step `FAILED` đều tự động được chạy lại ngay. Việc restart phụ thuộc vào JobInstance, trạng thái JobExecution, cấu hình Step, start limit và cách ứng dụng khởi chạy Job.

### STOPPED và STOPPING

`STOPPING` cho biết yêu cầu dừng đã được ghi nhận và framework đang cố gắng kết thúc ở ranh giới an toàn. `STOPPED` là trạng thái sau khi execution đã dừng. Trong chunk processing, việc dừng thường cần chờ phần xử lý hiện tại đạt tới điểm thích hợp để trạng thái và transaction được xử lý nhất quán.

Một Job hoặc Step dừng không đồng nghĩa với thất bại nghiệp vụ. Có thể restart theo chính sách của ứng dụng nếu metadata và checkpoint cho phép.

### ABANDONED và UNKNOWN

`ABANDONED` thường dùng khi một execution được quyết định bỏ qua trong quy trình vận hành hoặc restart. Step ở trạng thái này không được xem như một Step thất bại thông thường có thể tự động chạy tiếp.

`UNKNOWN` cần được xem xét thận trọng. Nó có thể biểu thị trạng thái không chắc chắn, ví dụ hệ thống không thể xác định an toàn công việc đã hoàn tất đến đâu. Không nên tùy tiện sửa metadata từ `UNKNOWN` thành `FAILED` hoặc `COMPLETED` chỉ để làm Job chạy tiếp. Trước tiên cần đối chiếu dữ liệu nghiệp vụ và trạng thái tài nguyên liên quan.

## 4. ExitStatus: mã kết quả của Step

`ExitStatus` là đối tượng mang exit code và exit description. Spring Batch sử dụng exit status trong luồng điều khiển của Job, đặc biệt khi cấu hình các nhánh chuyển tiếp dựa trên kết quả Step.

Một số exit code thường gặp là `COMPLETED`, `FAILED`, `EXECUTING`, `NOOP`, `STOPPED` và `UNKNOWN`. Ứng dụng cũng có thể tạo exit code riêng, chẳng hạn `COMPLETED_WITH_NO_DATA` hoặc `COMPLETED_WITH_WARNINGS`.

Ví dụ, một Step có thể có:

```java
ExitStatus exitStatus = stepExecution.getExitStatus();

String code = exitStatus.getExitCode();
String description = exitStatus.getExitDescription();
```

### Phân biệt BatchStatus và ExitStatus

| Tình huống | BatchStatus | ExitStatus |
|---|---|---|
| Step chạy thành công bình thường | `COMPLETED` | Thường là `COMPLETED` |
| Step chạy thành công nhưng không có dữ liệu | Có thể là `COMPLETED` | Có thể là `COMPLETED_WITH_NO_DATA` |
| Step gặp lỗi không xử lý được | `FAILED` | Thường là `FAILED` |
| Step dừng theo yêu cầu | Thường là `STOPPED` sau khi dừng xong | Thường là `STOPPED` |

Một Step có thể có `BatchStatus.COMPLETED` và exit code tùy chỉnh. Điều này hữu ích khi công việc kỹ thuật đã hoàn tất nhưng Job cần rẽ nhánh theo kết quả nghiệp vụ. Không nên đổi BatchStatus thành `FAILED` chỉ để điều khiển một nhánh nghiệp vụ nếu Step thực tế đã hoàn tất bình thường; hãy dùng ExitStatus cho mục đích đó.

### Tạo exit status tùy chỉnh bằng listener

`StepExecutionListener.afterStep` có thể trả về một `ExitStatus` để bổ sung hoặc thay đổi exit status của Step. Trả về `null` nếu listener không cần thay đổi kết quả.

```java
@Bean
StepExecutionListener noDataExitStatusListener() {
    return new StepExecutionListener() {
        @Override
        public void beforeStep(StepExecution stepExecution) {
            // Có thể ghi nhận thông tin lúc Step bắt đầu.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getStatus() == BatchStatus.COMPLETED
                    && stepExecution.getReadCount() == 0) {
                return new ExitStatus("COMPLETED_WITH_NO_DATA");
            }
            return null;
        }
    };
}
```

Đăng ký listener vào Step:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet importTasklet,
        StepExecutionListener noDataExitStatusListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .tasklet(importTasklet, transactionManager)
            .listener(noDataExitStatusListener)
            .build();
}
```

Trong ứng dụng thực tế, điều kiện nhận biết “không có dữ liệu” phải phù hợp với cách Step đọc dữ liệu. Ví dụ trên minh họa cách sử dụng listener và exit code; không phải mọi Step đều có ý nghĩa nghiệp vụ khi chỉ dựa vào `readCount`.

### Dùng ExitStatus để điều khiển flow

Một Job có thể rẽ nhánh theo exit code:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        Step notifyNoDataStep,
        Step archiveStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importOrdersStep)
                .on("COMPLETED_WITH_NO_DATA").to(notifyNoDataStep)
            .from(importOrdersStep)
                .on("COMPLETED").to(archiveStep)
            .from(importOrdersStep)
                .on("*").fail()
            .end()
            .build();
}
```

Đây là ví dụ về ý tưởng định tuyến theo exit code. Trong một Job có nhiều nhánh, cần định nghĩa đầy đủ các chuyển tiếp và kiểm tra thứ tự pattern để không tạo nhánh không mong muốn. Exit code tùy chỉnh cần được thống nhất giữa listener và cấu hình flow.

## 5. StepExecution được tạo và cập nhật như thế nào?

Trong quá trình chạy, Spring Batch phối hợp Step, JobRepository và các thành phần liên quan để lưu trạng thái execution.

Ở mức khái quát:

1. Job bắt đầu và Spring Batch tạo JobExecution cho lần chạy đó.
2. Khi một Step bắt đầu, framework tạo StepExecution gắn với JobExecution.
3. JobRepository lưu metadata ban đầu và trạng thái execution.
4. Step chạy logic Tasklet hoặc chunk, cập nhật các bộ đếm, context và trạng thái cần thiết.
5. Khi các transaction hoặc điểm cập nhật phù hợp hoàn tất, metadata được ghi lại qua JobRepository.
6. Khi Step kết thúc, thời gian kết thúc, BatchStatus và ExitStatus được cập nhật.

`JobRepository` là thành phần chịu trách nhiệm lưu trữ metadata của JobExecution và StepExecution. Trong cấu hình dùng JDBC JobRepository, metadata thường được lưu trong các bảng như `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, `BATCH_JOB_EXECUTION_CONTEXT` và `BATCH_STEP_EXECUTION_CONTEXT`. Tên bảng và schema có thể được tùy chỉnh theo cấu hình.

Không nên cập nhật trực tiếp các bảng metadata bằng SQL thông thường trong khi Job đang chạy. Spring Batch dùng các cơ chế cập nhật và version để giữ tính nhất quán, bao gồm optimistic locking trong các thao tác phù hợp. Sửa trực tiếp có thể làm sai lệch trạng thái, checkpoint hoặc quan hệ giữa các execution.

### Vai trò của version

StepExecution có thông tin version được dùng trong cơ chế optimistic locking của JobRepository. Khi nhiều thao tác cùng cố cập nhật một bản ghi execution, version giúp phát hiện cập nhật dựa trên dữ liệu cũ. Điều này bảo vệ metadata trước một số tình huống cập nhật đồng thời không nhất quán.

Ứng dụng không nên tự tăng version hoặc tự ghi đè các trường metadata để xử lý xung đột. Hãy tìm nguyên nhân vận hành thực tế, chẳng hạn nhiều launcher khởi chạy cùng một JobInstance hoặc nhiều tiến trình cố cập nhật cùng execution.

## 6. Đọc StepExecution trong code

### Truy cập từ Tasklet

Tasklet nhận `StepContribution` và `ChunkContext`. Có thể lấy StepExecution từ contribution để đọc trạng thái và cập nhật ExecutionContext:

```java
@Bean
Step prepareStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    return new StepBuilder("prepareStep", jobRepository)
            .tasklet((contribution, chunkContext) -> {
                StepExecution stepExecution = contribution.getStepExecution();

                String stepName = stepExecution.getStepName();
                long currentReadCount = stepExecution.getReadCount();

                stepExecution.getExecutionContext()
                        .putString("preparation", "done");

                return RepeatStatus.FINISHED;
            }, transactionManager)
            .build();
}
```

Đây là cách lấy execution context trong lúc Step đang chạy. Các bộ đếm có thể chưa phản ánh toàn bộ kết quả cuối cùng cho đến khi chunk hoặc Step hoàn tất. Không nên dùng một giá trị đọc giữa chừng như số liệu tổng kết cuối cùng.

### Truy cập từ StepExecutionListener

Listener phù hợp khi cần xử lý trước và sau một Step, ví dụ ghi log, kiểm tra bộ đếm hoặc thiết lập exit status:

```java
public class StepAuditListener implements StepExecutionListener {

    @Override
    public void beforeStep(StepExecution stepExecution) {
        System.out.println("Starting: " + stepExecution.getStepName());
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        System.out.println("Read: " + stepExecution.getReadCount());
        System.out.println("Written: " + stepExecution.getWriteCount());
        System.out.println("Status: " + stepExecution.getStatus());
        return null;
    }
}
```

`beforeStep` được gọi khi Step bắt đầu. `afterStep` được gọi khi Step kết thúc và có thể trả về exit status bổ sung. Listener là nơi phù hợp để quan sát trạng thái; tránh đặt toàn bộ logic xử lý item vào listener vì như vậy sẽ làm mờ trách nhiệm của reader, processor, writer hoặc Tasklet.

### Truy cập StepExecution trong bean step-scoped

Với một bean `@StepScope`, có thể lấy thuộc tính StepExecution thông qua late binding:

```java
@Bean
@StepScope
ItemReader<OrderInput> orderReader(
        @Value("#{stepExecution}") StepExecution stepExecution) {

    String stepName = stepExecution.getStepName();
    // Khởi tạo reader dựa trên ngữ cảnh của Step nếu cần.
    return createOrderReader(stepName);
}
```

Late binding giúp bean nhận execution đang hoạt động khi StepScope được mở. Không nên truy cập một StepExecution chưa tồn tại trong lúc khởi tạo application context; StepScope giải quyết việc trì hoãn khởi tạo bean đến đúng phạm vi thực thi.

## 7. Dùng StepExecution để theo dõi tiến độ và chẩn đoán

Khi một Step xử lý dữ liệu lớn, StepExecution cung cấp các số liệu quan trọng để hiểu hiệu quả và phát hiện bất thường.

Ví dụ, một Step có số liệu:

| Chỉ số | Giá trị minh họa |
|---|---:|
| Read count | 10.000 |
| Write count | 9.850 |
| Filter count | 100 |
| Read skip count | 20 |
| Process skip count | 25 |
| Write skip count | 5 |
| Commit count | 100 |
| Rollback count | 3 |

Các số liệu này gợi ý rằng có item bị lọc hoặc skip, và Step đã có một số lần rollback. Khi phân tích, cần kết hợp bộ đếm với log lỗi, loại exception, dữ liệu nguồn và kết quả thực tế trong hệ thống đích. Không nên kết luận rằng mọi item không được ghi đều là lỗi: processor có thể chủ động lọc item, còn skip có thể là chính sách đã được cho phép.

Một số dấu hiệu nên điều tra:

- `readCount` tăng nhưng `writeCount` thấp bất thường: xem logic processor, filter, skip và điều kiện ghi.
- `rollbackCount` tăng liên tục: xem lỗi transaction, deadlock, timeout hoặc lỗi writer.
- `readSkipCount`, `processSkipCount` hoặc `writeSkipCount` tăng: kiểm tra dữ liệu lỗi và chính sách skip.
- Step chạy lâu nhưng bộ đếm không tăng: xem reader bị chặn, gọi hệ thống ngoài quá lâu hoặc transaction chưa hoàn tất.
- `COMPLETED` nhưng kết quả nghiệp vụ thiếu: kiểm tra logic lọc/skip, tính idempotent và các tác dụng phụ ngoài transaction.

## 8. Dùng JobExplorer để xem StepExecution đã lưu

Trong vận hành, thường cần tra cứu execution đã kết thúc hoặc đang chạy. `JobExplorer` cung cấp API đọc metadata Job và Step từ kho lưu trữ đã cấu hình.

Ví dụ, lấy một JobExecution theo ID rồi duyệt các StepExecution của nó:

```java
@Service
public class BatchExecutionQueryService {

    private final JobExplorer jobExplorer;

    public BatchExecutionQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public void printStepExecutions(long jobExecutionId) {
        JobExecution jobExecution = jobExplorer.getJobExecution(jobExecutionId);
        if (jobExecution == null) {
            return;
        }

        for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
            System.out.printf(
                    "step=%s, status=%s, exit=%s, read=%d, write=%d, commits=%d%n",
                    stepExecution.getStepName(),
                    stepExecution.getStatus(),
                    stepExecution.getExitStatus().getExitCode(),
                    stepExecution.getReadCount(),
                    stepExecution.getWriteCount(),
                    stepExecution.getCommitCount());
        }
    }
}
```

Đây là truy vấn metadata đã được lưu. Khi Step vẫn đang chạy, giá trị đọc được phản ánh lần cập nhật metadata gần nhất, vì vậy có thể trễ so với trạng thái trong bộ nhớ của tiến trình đang thực thi. `JobExplorer` dành cho truy vấn; `JobRepository` được dùng bởi framework để lưu và cập nhật execution.

Trong môi trường có nhiều ứng dụng hoặc nhiều launcher, hãy bảo đảm các thành phần cùng sử dụng đúng metadata repository và có quyền truy cập phù hợp. Nếu truy vấn một repository khác với repository mà Job đang dùng, dữ liệu có thể không phản ánh execution mong muốn.

## 9. StepExecution và restart

Restart là một trong những lý do quan trọng khiến Spring Batch lưu StepExecution và ExecutionContext. Khi Job bị gián đoạn, framework cần biết Step nào đã hoàn tất, Step nào thất bại, và Step đang tiếp tục có thể khôi phục tiến độ từ đâu.

### Step đã hoàn tất

Khi restart cùng JobInstance, Step đã có execution hoàn tất thường được bỏ qua. Điều này tránh lặp lại các công việc đã thành công. Nếu Step cần chạy lại trong một lần restart, có thể dùng `allowStartIfComplete(true)`:

```java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet refreshTasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(refreshTasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

Chỉ bật tùy chọn này khi thao tác có thể chạy lại an toàn hoặc đã có cơ chế kiểm soát tác dụng phụ. Nếu Step gửi thanh toán, gửi email hoặc tạo dữ liệu không idempotent, chạy lại có thể gây hậu quả ngoài mong muốn.

### Step thất bại

Khi Step thất bại, Job có thể được restart theo chính sách. Lần chạy lại có StepExecution mới, trong khi execution trước vẫn giữ thông tin lịch sử. Reader hoặc thành phần hỗ trợ restart có thể dùng ExecutionContext đã lưu để tiếp tục tại vị trí phù hợp.

Ví dụ, reader đọc tệp có thể lưu vị trí dòng đã xử lý. Khi restart, reader khôi phục vị trí từ context thay vì đọc lại toàn bộ tệp. Cơ chế này chỉ hoạt động đúng nếu reader hỗ trợ lưu trạng thái và cấu hình stream được đăng ký đúng.

### Checkpoint và ExecutionContext

ExecutionContext của StepExecution là nơi phổ biến để lưu checkpoint. Ví dụ, một Tasklet xử lý theo trang có thể lưu số trang tiếp theo:

```java
ExecutionContext context = stepExecution.getExecutionContext();
long nextPage = context.getLong("nextPage", 0L);

// Sau khi trang hiện tại được xử lý thành công:
context.putLong("nextPage", nextPage + 1L);
```

Đoạn code chỉ minh họa thao tác đọc/ghi context. Trong ứng dụng thực tế, checkpoint phải được cập nhật nhất quán với phần công việc đã hoàn tất và phải được lưu qua JobRepository. Không nên tăng checkpoint trước khi công việc tương ứng thành công nếu điều đó có thể khiến restart bỏ qua dữ liệu chưa xử lý.

Với chunk processing, `ItemStream` cung cấp các callback như `open`, `update` và `close` để thành phần đọc/ghi khôi phục và lưu trạng thái. Spring Batch gọi cơ chế stream theo vòng đời Step; ứng dụng nên dùng reader/writer có hỗ trợ restart thay vì tự quản lý vị trí đọc ngoài metadata khi không cần thiết.

### Start limit

Step có thể cấu hình giới hạn số lần bắt đầu bằng `startLimit`. Nếu vượt giới hạn, Step không được bắt đầu thêm lần nữa. Start limit là chính sách bảo vệ số lần thực thi; nó không thay thế cơ chế restart hoặc kiểm soát idempotency.

## 10. Termination và yêu cầu dừng Step

`StepExecution` có thể được đánh dấu cần kết thúc thông qua cờ terminate-only. Đây là cơ chế nội bộ giúp Step nhận biết cần dừng tại điểm an toàn phù hợp.

Ví dụ về việc kiểm tra cờ trong logic xử lý:

```java
if (stepExecution.isTerminateOnly()) {
    // Dừng xử lý theo cơ chế của Step tại điểm phù hợp.
}
```

Trong ứng dụng thông thường, việc dừng Job nên đi qua cơ chế điều khiển và launcher phù hợp của Spring Batch hoặc qua quy trình vận hành đã thiết kế. Không nên tùy tiện sửa trạng thái trong bộ nhớ hoặc metadata để ép Step dừng, vì có thể làm mất checkpoint hoặc khiến trạng thái lưu trữ không khớp với công việc thực tế.

## 11. Những lỗi thường gặp khi làm việc với StepExecution

### Nhầm BatchStatus với ExitStatus

`BatchStatus` mô tả trạng thái thực thi; `ExitStatus` mô tả kết quả dùng trong điều khiển flow. Khi muốn tạo nhánh “không có dữ liệu” nhưng Step vẫn hoàn tất thành công, hãy dùng exit code tùy chỉnh phù hợp thay vì đánh dấu Step thất bại.

### Đọc bộ đếm trước khi Step kết thúc rồi xem đó là kết quả cuối

Trong lúc chạy, bộ đếm có thể còn thay đổi. Muốn tổng kết một Step, hãy đọc execution sau khi Step hoàn tất hoặc từ metadata đã được lưu ổn định.

### Dùng Job ExecutionContext thay cho Step ExecutionContext

Checkpoint riêng của reader hoặc Tasklet thường thuộc StepExecution. Nếu lưu nhầm vào context cấp Job, các Step có thể chia sẻ trạng thái không phù hợp hoặc làm việc restart khó dự đoán. Hãy chọn context theo phạm vi sử dụng.

### Tự sửa bảng metadata

Việc thay đổi `BATCH_STEP_EXECUTION` hoặc các bảng context bằng SQL trực tiếp có thể làm sai version, status, thời gian và checkpoint. Hãy dùng API Spring Batch để truy vấn hoặc cập nhật thông qua cơ chế framework hỗ trợ.

### Cho rằng một Step chỉ có một StepExecution mãi mãi

Một Step có thể có nhiều StepExecution qua các lần chạy và restart. Khi phân tích log hoặc metadata, cần xác định đúng JobInstance, JobExecution và StepExecution thay vì chỉ lọc theo tên Step.

### Dùng ExecutionContext làm kho dữ liệu nghiệp vụ

ExecutionContext được thiết kế để lưu trạng thái thực thi và checkpoint. Không nên lưu lượng dữ liệu nghiệp vụ lớn hoặc dùng context làm nguồn dữ liệu chính của ứng dụng. Hãy lưu dữ liệu nghiệp vụ ở kho dữ liệu phù hợp và chỉ giữ khóa, vị trí hoặc trạng thái cần thiết trong context.

### Bỏ qua tính an toàn khi restart

Checkpoint không thể tự hoàn tác tác dụng phụ ngoài transaction. Nếu Step đã gửi một yêu cầu HTTP hoặc di chuyển tệp rồi tiến trình dừng trước khi metadata được cập nhật, lần chạy lại có thể thực hiện thao tác đó lần nữa. Cần thiết kế thao tác idempotent, khóa chống trùng hoặc quy trình đối soát.

## 12. Quy trình đọc và phân tích một StepExecution

Khi một Step có kết quả bất thường, có thể phân tích theo trình tự sau:

1. Xác định `JobInstance` và `JobExecution` để biết đây là lần chạy đầu hay lần restart.
2. Tìm đúng `StepExecution` theo tên Step và JobExecution ID.
3. Đọc `BatchStatus`, `ExitStatus`, thời gian bắt đầu/kết thúc và thời điểm cập nhật gần nhất.
4. Xem `readCount`, `writeCount`, `filterCount`, các skip count, `commitCount` và `rollbackCount`.
5. Kiểm tra failure exception và log của Step để xác định lỗi phát sinh ở reader, processor, writer hay transaction.
6. Xem ExecutionContext nếu cần hiểu checkpoint hoặc dữ liệu phục vụ restart.
7. Đối chiếu dữ liệu nghiệp vụ trong hệ thống nguồn và đích trước khi quyết định restart hoặc đánh dấu execution đã hoàn tất.

Không nên chỉ nhìn một trường `status` rồi kết luận toàn bộ kết quả. Ví dụ, `BatchStatus.COMPLETED` cùng `ExitStatus.COMPLETED_WITH_NO_DATA` có thể là kết quả hợp lệ theo nghiệp vụ; ngược lại, `COMPLETED` nhưng dữ liệu đích thiếu có thể cho thấy logic lọc, skip hoặc tác dụng phụ ngoài transaction cần được điều tra.

## Kết luận

`StepExecution` ghi lại một lần thực thi cụ thể của Step, bao gồm trạng thái, exit status, thời gian, bộ đếm xử lý và ExecutionContext. `BatchStatus` cho biết Step đang chạy, đã hoàn tất, thất bại hay dừng; `ExitStatus` mô tả mã kết quả và có thể được tùy chỉnh để điều khiển flow. JobRepository lưu metadata để Spring Batch theo dõi lịch sử và hỗ trợ restart. Khi vận hành hoặc xử lý lỗi, hãy xem StepExecution trong đúng JobExecution, kết hợp các bộ đếm, context và log để hiểu chính xác điều gì đã xảy ra.
