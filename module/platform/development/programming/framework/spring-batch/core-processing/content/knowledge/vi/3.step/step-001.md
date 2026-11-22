# Step là đơn vị xử lý trong Job

Trong Spring Batch, **Job** mô tả một quy trình xử lý theo lô, còn **Step** chia quy trình đó thành những giai đoạn có trách nhiệm rõ ràng. Một Job thường gồm nhiều Step nối tiếp hoặc rẽ nhánh theo kết quả. Mỗi Step thực hiện một phần công việc, có vòng đời, trạng thái, thông tin thống kê và cơ chế giao dịch riêng.

Ví dụ, quy trình nhập dữ liệu khách hàng có thể được chia thành các Step:

1. Kiểm tra file đầu vào và tham số của lô.
2. Đọc, chuẩn hóa và ghi khách hàng vào cơ sở dữ liệu.
3. Đối soát số lượng bản ghi.
4. Lưu báo cáo kết quả hoặc gửi thông báo hoàn tất.

Việc chia Job thành Step giúp dễ theo dõi tiến độ, xử lý lỗi, khởi động lại từ giai đoạn phù hợp và kiểm thử từng phần.

## 1. Job và Step trong kiến trúc Spring Batch

Job là đơn vị công việc ở cấp cao nhất. Job xác định các Step cần chạy và quy tắc chuyển từ Step này sang Step khác. Step là một giai đoạn thực thi cụ thể bên trong Job.

~~~mermaid
flowchart TD
    A["Job: importCustomersJob"] --> B["Step 1: validateInput"]
    B --> C["Step 2: importCustomers"]
    C --> D["Step 3: reconcile"]
    D --> E["Step 4: publishReport"]
~~~

Trong ví dụ này:

- Job đại diện cho toàn bộ quy trình nhập khách hàng.
- Mỗi Step đảm nhiệm một giai đoạn độc lập.
- Kết quả của một Step có thể quyết định Step tiếp theo.
- Spring Batch ghi lại kết quả thực thi của từng Step để theo dõi và restart.

Không nên gom mọi thao tác vào một Step duy nhất nếu các thao tác có vòng đời, cách xử lý lỗi hoặc yêu cầu restart khác nhau. Ngược lại, cũng không cần tạo Step mới cho mọi dòng lệnh nhỏ. Một Step nên đại diện cho một giai đoạn có ý nghĩa trong quy trình nghiệp vụ hoặc vận hành.

### Phân biệt các khái niệm

| Khái niệm | Vai trò |
|---|---|
| Job | Định nghĩa quy trình batch gồm một hoặc nhiều Step và luồng điều khiển |
| JobInstance | Một lần xử lý logic được xác định bởi Job và các identifying JobParameters |
| JobExecution | Một lần thực thi cụ thể của JobInstance |
| Step | Định nghĩa một giai đoạn xử lý trong Job |
| StepExecution | Bản ghi về một lần thực thi Step trong một JobExecution |
| JobRepository | Lưu metadata của Job, Step, trạng thái và ExecutionContext |
| JobLauncher | Khởi chạy Job với các JobParameters |

Cần phân biệt **Step** và **StepExecution**. Step là cấu hình có thể được tham chiếu trong Job. StepExecution là bản ghi runtime được tạo khi Step thực sự bắt đầu chạy. Khi một JobInstance được khởi động lại, Spring Batch tạo JobExecution mới và tạo StepExecution mới cho những Step được thực thi trong lần đó.

## 2. Step đảm nhiệm những việc gì?

Một Step tạo ra ranh giới rõ ràng cho một giai đoạn xử lý. Tùy loại Step, framework và cấu hình của ứng dụng sẽ quản lý các trách nhiệm sau:

- **Thực thi công việc:** gọi logic Tasklet hoặc điều phối luồng đọc, xử lý và ghi theo chunk.
- **Giao dịch:** xác định phạm vi transaction cho từng lần thực thi Tasklet hoặc từng chunk.
- **Theo dõi trạng thái:** ghi nhận Step đang chạy, hoàn tất, thất bại hay bị dừng.
- **Thống kê:** lưu số item đã đọc, ghi, lọc, skip, số lần commit và rollback.
- **Lưu trạng thái:** giữ checkpoint trong ExecutionContext để có thể tiếp tục khi Job được restart.
- **Vòng đời mở rộng:** gọi listener trước, sau Step hoặc quanh từng chunk.
- **Điều khiển luồng:** cung cấp ExitStatus để Job quyết định bước tiếp theo.

Step không nhất thiết là một giao dịch duy nhất kéo dài từ đầu đến cuối. Một chunk-oriented Step có thể gồm hàng nghìn giao dịch nhỏ, mỗi giao dịch tương ứng với một chunk. Điều này giúp Job xử lý dữ liệu lớn mà không phải giữ toàn bộ công việc trong một transaction dài.

## 3. Các cách triển khai một Step

Spring Batch hỗ trợ nhiều kiểu Step. Hai cách phổ biến nhất là Tasklet và chunk-oriented processing.

### Tasklet Step

Tasklet phù hợp với một thao tác có phạm vi tương đối rõ ràng, chẳng hạn:

- Xóa file tạm hoặc chuẩn bị thư mục làm việc.
- Kiểm tra điều kiện trước khi nhập dữ liệu.
- Gọi stored procedure.
- Sao chép hoặc đổi tên file.
- Cập nhật một nhóm trạng thái trong cơ sở dữ liệu.
- Tạo báo cáo hoặc đánh dấu lô đã hoàn tất.

Tasklet có hợp đồng đơn giản:

~~~java
public interface Tasklet {
    RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext
    ) throws Exception;
}
~~~

Mỗi lần gọi `execute`, Tasklet trả về một trong các kết quả:

- `RepeatStatus.FINISHED`: công việc của Tasklet đã hoàn tất.
- `RepeatStatus.CONTINUABLE`: framework có thể gọi Tasklet tiếp tục.

Spring Batch thực thi mỗi lần gọi Tasklet trong phạm vi transaction do Step sử dụng. Nếu Tasklet trả về `CONTINUABLE`, framework lặp lại việc gọi theo cơ chế repeat; nếu trả về `FINISHED`, Step kết thúc bình thường.

Ví dụ một Tasklet kiểm tra và tạo thư mục đầu ra:

~~~java
@Bean
Tasklet prepareOutputDirectory() {
    return (contribution, chunkContext) -> {
        Path output = Path.of("work", "output");

        Files.createDirectories(output);

        return RepeatStatus.FINISHED;
    };
}
~~~

Khai báo Step sử dụng Tasklet:

~~~java
@Bean
Step prepareOutputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet prepareOutputDirectory) {

    return new StepBuilder("prepareOutputStep", jobRepository)
        .tasklet(prepareOutputDirectory, transactionManager)
        .build();
}
~~~

Tasklet trả về `FINISHED` sau khi tạo thư mục. Nếu thao tác tạo thư mục thất bại và exception được ném ra, Step sẽ thất bại theo chính sách xử lý lỗi đang áp dụng.

### Chunk-oriented Step

Chunk-oriented processing phù hợp với công việc xử lý nhiều item. Step đọc từng item, có thể xử lý item, gom kết quả thành chunk rồi ghi theo nhóm.

~~~mermaid
flowchart LR
    A["ItemReader"] --> B["ItemProcessor"]
    B --> C["Chunk"]
    C --> D["ItemWriter"]
    D --> E["Commit"]
~~~

Cấu hình một chunk-oriented Step thường khai báo commit interval:

~~~java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
        .<CustomerInput, Customer>chunk(200, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

Với commit interval là `200`, framework đọc và xử lý tối đa 200 item đầu vào cho một chunk trước khi ghi kết quả và hoàn tất transaction của chunk đó. Chunk cuối có thể ít item hơn nếu nguồn đã hết. Nếu processor lọc item bằng cách trả về `null`, số item writer nhận có thể nhỏ hơn số item reader đã đọc.

Tasklet và chunk-oriented là hai cách cấu hình cách Step thực hiện công việc. Chunk-oriented Step cũng được triển khai thông qua cơ chế Tasklet ở bên trong framework, nhưng người dùng cấu hình nó bằng `chunk(...)` cùng reader, processor và writer. Khi thiết kế Job, hãy chọn cách phù hợp với bản chất của giai đoạn xử lý.

### So sánh Tasklet và chunk-oriented

| Tiêu chí | Tasklet | Chunk-oriented |
|---|---|---|
| Đơn vị công việc | Một thao tác hoặc một lượt lặp của Tasklet | Một nhóm item |
| Cấu hình chính | `tasklet(...)` | `chunk(...)` |
| Thành phần thường dùng | Tasklet | ItemReader, ItemProcessor, ItemWriter |
| Giao dịch | Mỗi lần gọi Tasklet | Mỗi chunk |
| Trường hợp phù hợp | Chuẩn bị, dọn dẹp, gọi thủ tục, thao tác điều khiển | Nhập, chuyển đổi, xuất tập dữ liệu |
| Theo dõi dữ liệu | Tự cập nhật contribution nếu cần | Framework thống kê các item trong chunk |

## 4. Khai báo Step và gắn Step vào Job

Trong Spring Batch 5, có thể tạo Step bằng `StepBuilder` và truyền `JobRepository` vào constructor. Transaction manager được khai báo rõ khi cấu hình Tasklet hoặc chunk.

Ví dụ Job chạy ba Step theo thứ tự:

~~~java
@Bean
Job customerImportJob(
        JobRepository jobRepository,
        Step prepareOutputStep,
        Step importCustomersStep,
        Step reconcileStep) {

    return new JobBuilder("customerImportJob", jobRepository)
        .start(prepareOutputStep)
        .next(importCustomersStep)
        .next(reconcileStep)
        .build();
}
~~~

Job thực hiện:

1. `prepareOutputStep` chuẩn bị môi trường đầu ra.
2. `importCustomersStep` nhập và ghi dữ liệu khách hàng.
3. `reconcileStep` đối soát kết quả.

`start(...)` chỉ định Step đầu tiên. `next(...)` nối thêm Step tiếp theo. Khi một Step hoàn tất theo luồng bình thường, Job chuyển sang Step kế tiếp.

Các bean Step thường được khai báo riêng để có thể tái sử dụng trong nhiều Job nếu cùng ngữ nghĩa và cấu hình. Tuy nhiên, cần cân nhắc kỹ khi chia sẻ một Step giữa nhiều Job vì tên Step, trạng thái restart, tham số và tài nguyên đầu vào có thể khác nhau.

## 5. Vòng đời thực thi của Step

Khi Job chạy đến một Step, Spring Batch tạo và quản lý StepExecution tương ứng. Vòng đời khái quát như sau:

~~~mermaid
sequenceDiagram
    participant J as Job
    participant R as JobRepository
    participant S as Step
    participant L as StepListener
    participant W as Công việc

    J->>R: Tạo StepExecution
    J->>S: Thực thi Step
    S->>L: beforeStep
    S->>W: Thực hiện Tasklet hoặc các chunk
    W-->>S: Kết quả và thống kê
    S->>L: afterStep
    S->>R: Lưu trạng thái và kết quả
    S-->>J: ExitStatus
    J->>J: Chọn nhánh tiếp theo
~~~

Có thể diễn giải thành các giai đoạn:

1. Job flow chọn Step cần chạy.
2. Spring Batch tạo StepExecution gắn với JobExecution hiện tại.
3. Step chuyển sang trạng thái bắt đầu và gọi listener trước Step nếu được cấu hình.
4. Step thực hiện Tasklet hoặc xử lý các chunk.
5. Framework cập nhật thống kê, trạng thái và ExecutionContext.
6. Khi Step kết thúc, listener sau Step được gọi.
7. Kết quả được lưu trong JobRepository.
8. Job sử dụng ExitStatus để xác định đường đi tiếp theo.

Nếu Step phát sinh exception không được xử lý, Step thường kết thúc với trạng thái thất bại. Job sẽ đánh giá kết quả theo flow và các transition đã cấu hình.

## 6. StepExecution và thông tin thống kê

`StepExecution` đại diện cho một lần chạy cụ thể của Step. Đối tượng này liên kết với JobExecution và lưu các thông tin như:

- Tên Step và thời điểm bắt đầu, kết thúc.
- BatchStatus và ExitStatus.
- Số item đọc và ghi.
- Số item bị lọc hoặc skip.
- Số lần commit và rollback.
- ExecutionContext của Step.

Một số bộ đếm thường gặp:

| Thuộc tính | Ý nghĩa |
|---|---|
| `readCount` | Số item đã đọc |
| `writeCount` | Số item đã ghi thành công |
| `filterCount` | Số item bị lọc trong processor |
| `readSkipCount` | Số lỗi đọc được skip |
| `processSkipCount` | Số lỗi xử lý được skip |
| `writeSkipCount` | Số lỗi ghi được skip |
| `commitCount` | Số lần commit |
| `rollbackCount` | Số lần rollback |
| `status` | BatchStatus của StepExecution |
| `exitStatus` | Kết quả thoát của Step |

Các bộ đếm giúp xác định Step đã xử lý bao nhiêu dữ liệu và lỗi phát sinh ở giai đoạn nào. Ví dụ, nếu `readCount` lớn nhưng `writeCount` thấp, có thể có nhiều item bị lọc hoặc một phần xử lý bị skip. Cần xem thêm `filterCount` và các skip count để hiểu nguyên nhân.

Có thể truy cập StepExecution từ listener hoặc các thành phần nhận `StepContribution`. Với Tasklet, `StepContribution` cho phép cập nhật thông tin đóng góp của lần thực thi hiện tại. Trong chunk-oriented Step, framework tự quản lý nhiều thống kê chuẩn.

## 7. Phân biệt BatchStatus và ExitStatus

Spring Batch lưu cả trạng thái thực thi và kết quả thoát của Step. Hai giá trị này liên quan nhưng có mục đích khác nhau.

**BatchStatus** biểu thị trạng thái vòng đời của StepExecution. Một số trạng thái thường gặp:

| BatchStatus | Ý nghĩa |
|---|---|
| `STARTING` | Đang chuẩn bị bắt đầu |
| `STARTED` | Đang thực thi |
| `STOPPING` | Đang trong quá trình dừng |
| `STOPPED` | Đã dừng theo yêu cầu hoặc cơ chế stop |
| `COMPLETED` | Thực thi hoàn tất |
| `FAILED` | Thực thi thất bại |
| `ABANDONED` | Execution được đánh dấu không tiếp tục |
| `UNKNOWN` | Không xác định được trạng thái đáng tin cậy |

**ExitStatus** mô tả kết quả mà Step trả về cho Job flow. Các giá trị phổ biến gồm `COMPLETED`, `FAILED`, `STOPPED` và `NOOP`. Ứng dụng cũng có thể tạo ExitStatus tùy chỉnh như `NO_DATA` hoặc `VALIDATION_WARNING` để điều khiển nhánh tiếp theo.

Sự khác biệt quan trọng là **Job flow dùng ExitStatus để so khớp transition**. BatchStatus chủ yếu phản ánh trạng thái thực thi. Không nên giả định hai giá trị luôn giống nhau hoặc luôn có cùng ý nghĩa.

Ví dụ, một Step có thể hoàn tất kỹ thuật nhưng phát hiện không có dữ liệu để nhập. Listener có thể trả về ExitStatus tùy chỉnh `NO_DATA`; Job sau đó chuyển đến nhánh xử lý dữ liệu rỗng.

## 8. Điều khiển luồng Job bằng kết quả của Step

Job có thể chạy tuần tự hoặc rẽ nhánh dựa trên ExitStatus. Cấu hình tuần tự dùng `next(...)`. Khi cần rẽ nhánh, có thể dùng transition với `on(...)` và `to(...)`.

Ví dụ, sau Step kiểm tra đầu vào:

~~~java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importStep,
        Step rejectInputStep) {

    return new JobBuilder("importJob", jobRepository)
        .start(validateInputStep)
            .on("FAILED").to(rejectInputStep)
        .from(validateInputStep)
            .on("*").to(importStep)
        .end()
        .build();
}
~~~

Ý nghĩa:

- Nếu `validateInputStep` có ExitStatus khớp `FAILED`, Job chuyển đến `rejectInputStep`.
- Nếu kết quả khớp mẫu `*`, Job chuyển đến `importStep`.
- `end()` kết thúc định nghĩa flow trước khi build Job.

Mẫu `*` là wildcard, khớp các ExitStatus khác. Khi khai báo nhiều transition, cần sắp xếp và thiết kế pattern sao cho nhánh cụ thể được xử lý đúng như mong muốn.

Việc chuyển đến một Step xử lý lỗi không tự động quyết định Job cuối cùng phải là COMPLETED hay FAILED. Kết quả cuối phụ thuộc vào flow và transition kết thúc được cấu hình. Nếu cần Job báo thất bại dù đã chạy một Step ghi log hoặc thu thập lỗi, hãy thiết kế kết quả cuối của flow một cách rõ ràng.

### JobExecutionDecider

Khi điều kiện rẽ nhánh phụ thuộc vào dữ liệu hoặc logic nghiệp vụ phức tạp, có thể dùng `JobExecutionDecider`. Decider trả về `FlowExecutionStatus` để Job chọn nhánh.

Ví dụ về những quyết định phù hợp:

- Lô có dữ liệu hay không.
- Có cần chạy bước đối soát bổ sung hay không.
- Dữ liệu thuộc loại nhập mới hay cập nhật.
- Một điều kiện nghiệp vụ có cho phép đi tiếp hay cần chuyển sang luồng xử lý ngoại lệ.

Decider phù hợp với quyết định điều khiển luồng. Phần xử lý dữ liệu lớn vẫn nên đặt trong Step chuyên trách, để flow không trở thành nơi chứa logic đọc và ghi dữ liệu.

## 9. StepExecutionListener và các listener khác

Listener cho phép chạy logic tại những thời điểm xác định trong vòng đời Step mà không cần trộn logic đó vào reader, processor hoặc writer.

`StepExecutionListener` cung cấp hai điểm mở rộng chính:

- `beforeStep(StepExecution)` được gọi trước khi Step thực thi.
- `afterStep(StepExecution)` được gọi sau khi Step kết thúc; phương thức có thể trả về ExitStatus để bổ sung hoặc thay đổi kết quả thoát.

Ví dụ listener đánh dấu Step không có dữ liệu:

~~~java
@Bean
StepExecutionListener emptyResultListener() {
    return new StepExecutionListener() {
        @Override
        public void beforeStep(StepExecution stepExecution) {
            // Có thể ghi nhận thời điểm hoặc thông tin bắt đầu.
        }

        @Override
        public ExitStatus afterStep(StepExecution stepExecution) {
            if (stepExecution.getReadCount() == 0) {
                return new ExitStatus("NO_DATA");
            }
            return null;
        }
    };
}
~~~

Gắn listener vào Step:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .listener(emptyResultListener())
    .build();
~~~

Trong ví dụ, nếu reader không đọc được item nào, listener trả về ExitStatus `NO_DATA`. Nếu không có kết quả tùy chỉnh, listener trả về `null` để giữ nguyên kết quả hiện có.

Ngoài StepExecutionListener, Spring Batch còn có các listener ở phạm vi chunk, read, process và write. Ví dụ, `ChunkListener` có thể chạy trước hoặc sau chunk; `ItemReadListener` có thể phản ứng khi đọc thành công hoặc gặp lỗi. Chọn listener theo đúng phạm vi sự kiện cần quan sát.

Listener nên dùng cho logging, metrics, ghi nhận audit hoặc điều chỉnh kết quả thực thi. Tránh đặt toàn bộ nghiệp vụ chính trong listener vì điều đó làm khó xác định luồng xử lý và ranh giới giao dịch.

## 10. ExecutionContext và dữ liệu giữa các Step

Step thường cần lưu trạng thái để restart hoặc chia sẻ một lượng thông tin nhỏ giữa các giai đoạn. Spring Batch cung cấp `ExecutionContext` ở hai phạm vi:

- **StepExecutionContext:** gắn với một StepExecution, thường lưu checkpoint và trạng thái riêng của Step.
- **JobExecutionContext:** gắn với JobExecution, dùng để chia sẻ thông tin giữa các Step trong cùng một lần chạy Job.

Ví dụ, Step kiểm tra file có thể lưu số dòng hợp lệ hoặc mã lô vào JobExecutionContext để Step nhập dữ liệu tiếp theo sử dụng. Reader có thể lưu vị trí đọc vào StepExecutionContext để khôi phục khi restart.

~~~java
// Ví dụ minh họa trong một thành phần đang chạy bên trong Step.
stepExecution.getExecutionContext()
    .putLong("lastProcessedId", lastProcessedId);

jobExecution.getExecutionContext()
    .putString("batchReference", batchReference);
~~~

Cần chọn đúng phạm vi lưu trữ:

| Loại dữ liệu | Phạm vi phù hợp |
|---|---|
| Vị trí đọc file hoặc checkpoint của reader | StepExecutionContext |
| Trạng thái nội bộ chỉ dùng trong một Step | StepExecutionContext |
| Mã lô được nhiều Step dùng chung | JobExecutionContext |
| Thông tin kết quả cần truyền giữa các Step | JobExecutionContext |

ExecutionContext là vùng lưu trạng thái có thể được persist qua JobRepository. Chỉ lưu dữ liệu nhỏ, có ý nghĩa để tiếp tục hoặc phối hợp công việc. Không nên dùng nó làm kho chứa tập dữ liệu lớn; dữ liệu nghiệp vụ nên nằm ở file, database hoặc hệ thống lưu trữ phù hợp.

StepExecutionContext thường được cập nhật tại các checkpoint của Step. JobExecutionContext được lưu để các Step tiếp theo có thể sử dụng, thường tại ranh giới hoàn tất Step. Với thành phần tự viết, cần triển khai cơ chế lưu và khôi phục trạng thái đúng vòng đời.

## 11. Restart và hành vi chạy lại Step

Một lợi ích quan trọng của Step là Spring Batch có thể theo dõi giai đoạn nào đã hoàn tất và giai đoạn nào cần tiếp tục.

Giả sử Job gồm ba Step:

~~~mermaid
flowchart TD
    A["Step 1: Prepare"] --> B["Step 2: Import"]
    B --> C["Step 3: Reconcile"]
    B -. "Lỗi giữa chừng" .-> D["Job dừng"]
    D -. "Restart cùng JobInstance" .-> B
~~~

Nếu Step 1 đã hoàn tất, Step 2 thất bại và Job được restart đúng JobInstance, Spring Batch thường bỏ qua Step 1 đã hoàn tất và tiếp tục từ Step có thể restart. Với chunk-oriented Step có checkpoint, framework có thể khôi phục trạng thái và tiếp tục từ phần chưa commit.

Một số quy tắc cần hiểu:

- Step đã COMPLETED thường được bỏ qua khi restart JobInstance.
- Step thất bại hoặc dừng có thể được thực thi lại nếu Job và Step cho phép restart.
- Mỗi lần Step thực sự chạy tạo một StepExecution mới.
- Dữ liệu checkpoint được dùng để khôi phục trạng thái của các thành phần hỗ trợ restart.
- Nếu thay đổi identifying JobParameters, ứng dụng có thể tạo JobInstance mới thay vì tiếp tục JobInstance cũ.

### allowStartIfComplete

Mặc định, Step đã hoàn tất sẽ không chạy lại khi restart cùng JobInstance. Có thể cho phép Step chạy lại bằng `allowStartIfComplete(true)`:

~~~java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet refreshReferenceDataTasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
        .tasklet(refreshReferenceDataTasklet, transactionManager)
        .allowStartIfComplete(true)
        .build();
}
~~~

Tùy chọn này hữu ích khi một Step cần chạy lại mỗi lần JobInstance được restart, ví dụ làm mới một vùng dữ liệu trung gian trước khi tiếp tục. Chỉ bật khi công việc có thể chạy lại an toàn hoặc đã có cơ chế kiểm soát side effect.

### startLimit

`startLimit(...)` giới hạn số lần một Step được phép bắt đầu thực thi:

~~~java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .startLimit(3)
    .build();
~~~

Ví dụ trên giới hạn số lần bắt đầu Step theo cấu hình là 3. Khi vượt giới hạn, Spring Batch không tiếp tục khởi chạy Step đó trong JobInstance. Giới hạn này hữu ích để tránh một Step liên tục thất bại và được khởi động lại vô hạn.

### Restart an toàn và idempotency

Spring Batch lưu metadata và checkpoint, nhưng không tự làm cho mọi thao tác bên ngoài trở nên idempotent. Nếu Step gửi request đến API, gửi email hoặc ghi file mà không có cơ chế kiểm soát, thao tác có thể bị lặp khi Job restart.

Một số cách giảm rủi ro:

- Dùng khóa nghiệp vụ hoặc mã lô để nhận diện thao tác đã xử lý.
- Thiết kế thao tác ghi theo hướng idempotent nếu nghiệp vụ cho phép.
- Ghi trạng thái xử lý và dữ liệu trong cùng transaction khi cả hai cùng thuộc một cơ sở dữ liệu.
- Dùng outbox hoặc cơ chế xác nhận từ hệ thống đích cho tác động bên ngoài.
- Đảm bảo Tasklet có thể được gọi lại mà không tạo dữ liệu sai hoặc side effect trùng lặp.

Restart chỉ an toàn khi trạng thái đã lưu và tác động của Step được thiết kế nhất quán với nhau.

## 12. Step Scope và Job Parameters

Một Step có thể cần nhận tham số lúc Job được khởi chạy, chẳng hạn đường dẫn file, mã lô hoặc ngày xử lý. Không phải lúc khai báo bean Step các giá trị này đã có sẵn. `@StepScope` cho phép tạo bean theo phạm vi StepExecution và dùng late binding để lấy tham số runtime.

Ví dụ:

~~~java
@Bean
@StepScope
Tasklet validateInputFile(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return (contribution, chunkContext) -> {
        Path path = Path.of(inputFile);
        if (!Files.isRegularFile(path)) {
            throw new FileNotFoundException("Input file not found: " + inputFile);
        }
        return RepeatStatus.FINISHED;
    };
}
~~~

Khi Step bắt đầu, Spring Batch tạo bean theo scope và inject giá trị `inputFile` từ JobParameters. Tasklet dùng đường dẫn đó để kiểm tra file đầu vào, nhờ vậy cùng một cấu hình có thể chạy với nhiều file khác nhau mà không phải hard-code đường dẫn.

Có thể lấy dữ liệu từ các context thông qua biểu thức tương tự:

- `#{jobParameters['batchDate']}`: tham số của Job.
- `#{jobExecutionContext['batchReference']}`: dữ liệu chia sẻ ở phạm vi JobExecution.
- `#{stepExecutionContext['partitionFile']}`: dữ liệu ở phạm vi StepExecution.

Chỉ dùng Step scope khi bean cần dữ liệu runtime hoặc trạng thái gắn với một StepExecution. Các bean stateless và không phụ thuộc tham số runtime thường không cần scope này.

## 13. Dừng Step và xử lý lỗi

Step có thể kết thúc theo nhiều cách:

- Hoàn tất bình thường.
- Thất bại do exception hoặc điều kiện lỗi.
- Dừng theo yêu cầu của ứng dụng hoặc cơ chế vận hành.
- Bị bỏ qua theo quy tắc flow hoặc restart.

Trong thực tế, cần phân biệt lỗi nghiệp vụ, lỗi dữ liệu và lỗi hạ tầng. Ví dụ, file sai định dạng có thể được xử lý bằng Step kiểm tra và báo lỗi rõ ràng; lỗi kết nối database tạm thời có thể cần retry; lỗi logic lập trình thường cần làm Job thất bại để điều tra.

Với chunk-oriented Step, có thể cấu hình skip và retry cho loại exception phù hợp. Với Tasklet, cần chủ động xử lý hoặc ném exception để framework ghi nhận trạng thái. Không nên bắt mọi exception rồi trả về `FINISHED` vì như vậy Job có thể báo hoàn tất dù công việc chưa thành công.

Khi cần dừng có kiểm soát, ứng dụng có thể yêu cầu Job hoặc Step dừng. Step sẽ đi đến trạng thái dừng tại điểm framework có thể xử lý an toàn. Với chunk processing, điều này thường gắn với ranh giới chunk và transaction, giúp dữ liệu đã commit được giữ nguyên.

## 14. Tổ chức Step để dễ vận hành

Một Job lớn nên được chia thành các Step có mục tiêu và đầu vào, đầu ra rõ ràng. Khi đặt tên Step, nên dùng tên thể hiện nghiệp vụ hoặc giai đoạn, chẳng hạn:

- `validateInputStep`
- `loadReferenceDataStep`
- `importCustomerStep`
- `reconcileResultStep`
- `publishReportStep`

Tên Step được lưu trong metadata, vì vậy cần giữ ổn định qua các phiên bản triển khai nếu muốn restart và truy vấn lịch sử hoạt động nhất quán.

Một Step nên có một trách nhiệm chính. Nếu Step vừa tải file, vừa kiểm tra nghiệp vụ, vừa gửi thông báo, vừa cập nhật nhiều hệ thống, sẽ khó xác định lỗi thuộc giai đoạn nào và có thể restart an toàn ra sao. Có thể tách thành các Step riêng khi mỗi giai đoạn có quy tắc giao dịch, retry, audit hoặc vận hành khác nhau.

Tuy nhiên, chia quá nhỏ cũng làm Job phức tạp: nhiều metadata, nhiều lần chuyển Step và nhiều điểm phải quản lý trạng thái. Hãy chia theo ranh giới có ý nghĩa với nghiệp vụ hoặc vận hành.

### Chạy Step song song và partitioning

Với khối lượng dữ liệu lớn, Spring Batch có các cách mở rộng thực thi:

- Chạy các flow độc lập song song khi không phụ thuộc kết quả của nhau.
- Partitioning chia dữ liệu thành nhiều phần và chạy worker Step cho từng phần.
- Một số cấu hình chunk có thể dùng TaskExecutor để xử lý đồng thời, tùy mô hình và phiên bản.

Các cách này làm tăng yêu cầu về tính thread-safe của reader, processor, writer và tài nguyên dùng chung. Cần bảo đảm mỗi partition có phạm vi dữ liệu riêng, không ghi đè checkpoint của partition khác và không tạo xung đột khi ghi đích. Chỉ nên thêm song song sau khi đã xác định nút thắt hiệu năng và kiểm tra được tính đúng đắn của dữ liệu.

## 15. Theo dõi và kiểm thử Step

Một Step cần được kiểm thử như một đơn vị độc lập trước khi kiểm thử toàn bộ Job. Các khía cạnh quan trọng gồm:

- **Luồng thành công:** Step thực hiện đúng công việc và kết thúc với trạng thái mong đợi.
- **Luồng lỗi:** exception được truyền hoặc xử lý theo đúng chính sách.
- **Thống kê:** read, write, filter, skip, commit và rollback count phản ánh đúng kết quả.
- **Transaction:** lỗi giữa chừng không để lại dữ liệu dở dang trong tài nguyên tham gia transaction.
- **Restart:** Step có thể khôi phục checkpoint và không tạo tác động trùng lặp ngoài dự kiến.
- **Flow:** ExitStatus đưa Job đến đúng Step tiếp theo.
- **Listener:** listener được gọi đúng thời điểm và không làm thay đổi kết quả ngoài ý muốn.
- **Tham số runtime:** Step scope nhận đúng JobParameters và ExecutionContext.

Khi kiểm thử Job, cần kiểm tra thêm trường hợp một Step hoàn tất nhưng Step kế tiếp thất bại. Khi restart, Step đã hoàn tất có được bỏ qua đúng không, Step thất bại có khôi phục đúng trạng thái không, và Job có kết thúc với trạng thái phù hợp với flow hay không.

Có thể dùng các tiện ích kiểm thử của Spring Batch như `JobLauncherTestUtils` và `JobRepositoryTestUtils` trong bài kiểm thử tích hợp. Kiểm thử nên dùng JobRepository và transaction configuration tương tự môi trường ứng dụng để kết quả phản ánh đúng hành vi metadata và restart.

## 16. Ví dụ tổng hợp: Job nhập khách hàng

Một Job nhập khách hàng có thể được tổ chức thành ba Step:

~~~mermaid
flowchart TD
    A["validateInputStep"] --> B["importCustomersStep"]
    B --> C["reconcileStep"]
    A -. "FAILED" .-> D["rejectInputStep"]
~~~

- `validateInputStep` là Tasklet Step kiểm tra file và tham số.
- `importCustomersStep` là chunk-oriented Step đọc, chuẩn hóa và ghi dữ liệu.
- `reconcileStep` là Tasklet Step đối chiếu số bản ghi đã nhận và đã ghi.
- `rejectInputStep` là nhánh xử lý khi đầu vào không hợp lệ.

Cấu hình tuần tự cơ bản:

~~~java
@Bean
Job customerImportJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importCustomersStep,
        Step reconcileStep) {

    return new JobBuilder("customerImportJob", jobRepository)
        .start(validateInputStep)
        .next(importCustomersStep)
        .next(reconcileStep)
        .build();
}
~~~

Nếu cần nhánh xử lý đầu vào không hợp lệ, thay flow tuần tự bằng transition dựa trên ExitStatus như ví dụ ở phần điều khiển luồng. Khi đó, listener hoặc Tasklet của Step kiểm tra có thể trả về một ExitStatus tùy chỉnh để phân biệt dữ liệu rỗng, dữ liệu hợp lệ và dữ liệu không hợp lệ.

Khi Job chạy, JobRepository lưu JobExecution và các StepExecution. Nếu Step nhập dữ liệu thất bại sau một số chunk đã commit, có thể restart JobInstance để tiếp tục theo checkpoint. Step kiểm tra đầu vào đã hoàn tất thường được bỏ qua, còn Step nhập dữ liệu khôi phục trạng thái nếu reader và writer hỗ trợ restart.

## 17. Những điểm cần nhớ khi thiết kế Step

- Job mô tả toàn bộ quy trình; Step đại diện cho từng giai đoạn xử lý có ý nghĩa.
- Step là định nghĩa, còn StepExecution là bản ghi của một lần chạy Step.
- Tasklet phù hợp với thao tác đơn lẻ hoặc công việc điều khiển; chunk-oriented phù hợp với tập dữ liệu gồm nhiều item.
- Step có ranh giới giao dịch và trạng thái riêng; chunk-oriented Step thường commit theo từng chunk.
- BatchStatus phản ánh trạng thái thực thi, ExitStatus dùng để điều khiển Job flow.
- ExecutionContext lưu checkpoint và thông tin cần thiết giữa các giai đoạn.
- Listener cung cấp điểm mở rộng trong vòng đời Step.
- Restart an toàn đòi hỏi reader, writer và các side effect có khả năng khôi phục hoặc xử lý lặp phù hợp.
- Tên Step nên ổn định và trách nhiệm của Step nên đủ rõ để dễ theo dõi, kiểm thử và vận hành.

Khi chia Job thành các Step theo đúng ranh giới công việc, ứng dụng Spring Batch có thể kiểm soát tiến trình tốt hơn, định vị lỗi nhanh hơn và khởi động lại từ giai đoạn phù hợp mà không phải thực hiện lại toàn bộ quy trình.

