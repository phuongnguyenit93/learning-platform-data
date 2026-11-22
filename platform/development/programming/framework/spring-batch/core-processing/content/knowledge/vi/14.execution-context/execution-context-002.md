# JobExecutionContext và StepExecutionContext

Trong Spring Batch, `ExecutionContext` là một vùng lưu trữ key-value mà framework dùng để giữ trạng thái thực thi giữa các bước xử lý và hỗ trợ restart. Có hai phạm vi context chính: **JobExecutionContext** gắn với một lần thực thi Job và **StepExecutionContext** gắn với một lần thực thi Step.

Hai context đều có thể chứa dữ liệu cần lưu lại, nhưng phạm vi sử dụng và thời điểm cập nhật khác nhau. Job context phù hợp với thông tin cần chia sẻ giữa nhiều Step trong cùng một JobExecution. Step context phù hợp với trạng thái riêng của một Step, đặc biệt là checkpoint của reader hoặc tiến độ xử lý cần khôi phục khi Step được restart.

## 1. ExecutionContext là gì?

`ExecutionContext` là một cấu trúc key-value được Spring Batch quản lý và lưu trong `JobRepository`. Các thành phần trong Job có thể ghi trạng thái vào context và đọc lại trạng thái đó trong quá trình thực thi.

Ví dụ, một Job import dữ liệu có thể cần lưu:

- Phiên bản file đầu vào đã được xác thực.
- Số lượng bản ghi hợp lệ sau Step kiểm tra.
- Mã snapshot dữ liệu được dùng trong lần chạy.
- Vị trí đọc hiện tại của file hoặc database reader.
- Khóa cuối cùng đã xử lý khi đọc theo trang.

`ExecutionContext` cung cấp các thao tác như `putString`, `putLong`, `putInt`, `put` và các phương thức lấy giá trị tương ứng. Ví dụ:

```java
ExecutionContext context = new ExecutionContext();
context.putString("sourceVersion", "v3");
context.putLong("validRecordCount", 12_500L);

String version = context.getString("sourceVersion");
long count = context.getLong("validRecordCount");
```

Đoạn code trên chỉ minh họa API của context. Trong ứng dụng Spring Batch, context thường được lấy từ `JobExecution` hoặc `StepExecution` do framework tạo và quản lý, thay vì tự tạo một context mới rồi mong framework tự lưu nó.

## 2. Hai phạm vi context

Mỗi `JobExecution` có một JobExecutionContext. Mỗi `StepExecution` có một StepExecutionContext riêng. Một JobExecution có thể thực thi nhiều Step; các Step có thể chia sẻ dữ liệu thông qua JobExecutionContext, trong khi StepExecutionContext thuộc về Step tương ứng.

```text
JobInstance
    |
    v
JobExecution
    |
    +---- JobExecutionContext
    |       (dữ liệu dùng chung trong lần chạy Job)
    |
    +---- StepExecution A
    |        |
    |        +---- StepExecutionContext A
    |
    +---- StepExecution B
    |        |
    |        +---- StepExecutionContext B
    |
    +---- StepExecution C
             |
             +---- StepExecutionContext C
```

| Tiêu chí | JobExecutionContext | StepExecutionContext |
|---|---|---|
| Phạm vi | Một JobExecution | Một StepExecution |
| Ai có thể sử dụng? | Các Step trong cùng JobExecution | Step đang thực thi và các thành phần thuộc Step đó |
| Dữ liệu phù hợp | Kết quả hoặc tham số trung gian cần Step sau sử dụng | Checkpoint reader, trạng thái nội bộ và tiến độ riêng của Step |
| Lưu metadata | Gắn với JobExecution | Gắn với StepExecution |
| Restart | Được khôi phục cho lần chạy tiếp theo của cùng JobInstance theo metadata đã lưu | Được dùng để khôi phục trạng thái Step khi Step được restart |

JobExecutionContext không phải vùng nhớ dùng chung cho mọi Job trong ứng dụng. Nó thuộc về một JobExecution cụ thể. StepExecutionContext cũng không tự động chia sẻ giữa các Step khác nhau.

## 3. JobExecutionContext dùng để làm gì?

JobExecutionContext phù hợp khi một Step tạo ra thông tin mà Step tiếp theo cần sử dụng. Ví dụ:

1. Step đầu kiểm tra file đầu vào và xác định version.
2. Step tiếp theo import dữ liệu theo version đã kiểm tra.
3. Step cuối tạo báo cáo sử dụng số lượng bản ghi đã import.

Các giá trị như `sourceVersion`, `validRecordCount` hoặc `batchReference` có thể được lưu trong JobExecutionContext để các Step tiếp theo truy cập.

### Ghi vào JobExecutionContext

Trong Tasklet, có thể truy cập JobExecution thông qua StepExecution:

```java
@Component
public class RecordBatchMetadataTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = contribution
                .getStepExecution()
                .getJobExecution();

        ExecutionContext jobContext = jobExecution.getExecutionContext();
        jobContext.putString("sourceVersion", "v3");
        jobContext.putLong("validRecordCount", 12_500L);

        return RepeatStatus.FINISHED;
    }
}
```

JobExecutionContext có thể được các Step sau đọc thông qua JobExecution của chúng. Spring Batch quản lý việc lưu metadata context tại các mốc vòng đời của Job/Step. Khi một Step hoàn tất, JobExecutionContext được cập nhật trong repository để các Step tiếp theo và quy trình restart có thể sử dụng trạng thái đã lưu.

### Đọc JobExecutionContext trong Step tiếp theo

Với bean có `@StepScope`, có thể late-bind giá trị bằng SpEL:

```java
@Bean
@StepScope
Tasklet createSummaryTasklet(
        @Value("#{jobExecutionContext['validRecordCount']}") Long validRecordCount,
        @Value("#{jobExecutionContext['sourceVersion']}") String sourceVersion,
        SummaryService summaryService) {

    return (contribution, chunkContext) -> {
        summaryService.createSummary(validRecordCount, sourceVersion);
        return RepeatStatus.FINISHED;
    };
}
```

`jobExecutionContext` là ngữ cảnh SpEL được Spring Batch cung cấp trong scope phù hợp. `@StepScope` giúp giá trị được lấy khi StepExecution hiện tại đã tồn tại. Cần xử lý trường hợp key không có giá trị nếu Step trước không chạy, bị bỏ qua hoặc không ghi key đó.

## 4. StepExecutionContext dùng để làm gì?

StepExecutionContext dành cho trạng thái nội bộ của một Step. Ví dụ:

- Vị trí byte hoặc số dòng đã đọc từ file.
- Trang hoặc khóa cuối cùng đã đọc từ database.
- Số lượng item đã xử lý trong một tác vụ nhiều lượt.
- Mã tạm thời hoặc trạng thái trung gian chỉ Step hiện tại cần.

Trong Tasklet, có thể lấy StepExecutionContext từ `StepContribution`:

```java
@Component
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext stepContext = contribution
                .getStepExecution()
                .getExecutionContext();

        stepContext.putString("validatedFile", "customers-20261115.csv");
        stepContext.putInt("validationWarnings", 4);

        return RepeatStatus.FINISHED;
    }
}
```

Các giá trị này thuộc Step hiện tại. Step khác không tự động nhìn thấy chúng qua StepExecutionContext của mình. Nếu Step sau cần dùng `validatedFile`, cần chuyển giá trị đó sang JobExecutionContext, chẳng hạn bằng `ExecutionContextPromotionListener`.

## 5. Promotion: chuyển dữ liệu từ Step context lên Job context

Một mẫu phổ biến là Step ghi kết quả vào StepExecutionContext, sau đó promote một số key được chọn lên JobExecutionContext khi Step hoàn tất. Spring Batch cung cấp `ExecutionContextPromotionListener` cho mục đích này.

### Khai báo listener

```java
@Bean
ExecutionContextPromotionListener promoteValidationResults() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {
            "validatedFile",
            "validationWarnings"
    });

    return listener;
}
```

### Gắn listener vào Step

```java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ValidateInputTasklet tasklet,
        ExecutionContextPromotionListener promoteValidationResults) {

    return new StepBuilder("validateInputStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .listener(promoteValidationResults)
            .build();
}
```

Khi Step kết thúc với ExitStatus phù hợp (mặc định listener thường chỉ promote khi `COMPLETED`), các key được khai báo sẽ được sao chép từ StepExecutionContext lên JobExecutionContext. Có thể cấu hình các trạng thái được phép promote nếu nghiệp vụ cần hành vi khác; không nên promote dữ liệu chưa hợp lệ hoặc kết quả của Step thất bại.

Sau đó, Step tiếp theo có thể đọc `validatedFile` hoặc `validationWarnings` qua `jobExecutionContext`. Cách làm này thể hiện rõ dữ liệu nào được phép rời khỏi phạm vi Step và được chia sẻ với phần còn lại của Job.

## 6. JobParameters khác ExecutionContext như thế nào?

JobParameters và ExecutionContext đều có thể chứa dữ liệu mà Job sử dụng, nhưng chúng phục vụ hai mục đích khác nhau.

| Tiêu chí | JobParameters | ExecutionContext |
|---|---|---|
| Nguồn tạo | Caller truyền khi launch Job | Job/Step/reader ghi trong quá trình thực thi |
| Vai trò | Đầu vào xác định công việc cần chạy | Trạng thái và checkpoint của quá trình chạy |
| Có thể thay đổi trong Step? | Không; được xem là đầu vào của execution | Có; context được cập nhật trong lifecycle |
| Ảnh hưởng JobInstance | Identifying parameters tham gia định danh JobInstance | Không tham gia định danh JobInstance |
| Ví dụ | Ngày nghiệp vụ, mã file, batch ID | Vị trí đọc, số bản ghi hợp lệ, version đã kiểm tra |

Ví dụ, `businessDate` nên là JobParameter vì caller chọn ngày nghiệp vụ cần xử lý. Trong khi đó, `lastProcessedId` là checkpoint được reader cập nhật trong lúc đọc và phù hợp với StepExecutionContext.

Không nên dùng ExecutionContext để thay thế JobParameters đầu vào hoặc để tạo một JobInstance mới. Nếu một lần chạy logic khác nhau theo ngày hoặc file, hãy thể hiện khác biệt đó bằng identifying JobParameters.

## 7. Context hỗ trợ restart như thế nào?

Spring Batch phân biệt `JobInstance` và `JobExecution`. Một JobInstance đại diện cho một lần chạy logic, được xác định bởi tên Job và identifying JobParameters. Nếu Job thất bại rồi được restart, Spring Batch tạo JobExecution mới cho cùng JobInstance.

Metadata ExecutionContext đã lưu là một phần của thông tin khôi phục. Khi restart, framework sử dụng trạng thái đã lưu từ lần thực thi trước để khôi phục Job context và Step context phù hợp. Nhờ vậy, Step có thể tiếp tục từ checkpoint thay vì mặc định luôn bắt đầu lại từ đầu.

```text
JobInstance (businessDate=2026-11-15)
        |
        +---- JobExecution 1: FAILED
        |          |
        |          +---- JobExecutionContext đã lưu
        |          |
        |          +---- StepExecutionContext có checkpoint
        |
        +---- Restart
                   |
                   v
             JobExecution 2
                   |
                   +---- Khôi phục context đã lưu
                   |
                   +---- Tiếp tục Step theo trạng thái/checkpoint
```

Ví dụ, reader đã đọc và commit đến `customerId=5000`. StepExecutionContext có thể lưu checkpoint tương ứng. Khi restart, reader khôi phục vị trí và tiếp tục từ phần chưa hoàn tất. JobExecutionContext có thể giữ `sourceVersion` đã được Step xác thực để các Step tiếp theo vẫn dùng đúng phiên bản dữ liệu.

Khả năng restart còn phụ thuộc reader có hỗ trợ lưu/khôi phục trạng thái, nguồn input có ổn định và các thao tác ghi có an toàn khi thực hiện lại hay không. Việc có ExecutionContext không tự động làm mọi tác dụng phụ bên ngoài trở nên rollback được.

## 8. Reader tự lưu checkpoint trong StepExecutionContext

Nhiều reader có sẵn của Spring Batch triển khai `ItemStream` và tự lưu trạng thái vào StepExecutionContext. Ví dụ `FlatFileItemReader` có thể lưu vị trí đọc để hỗ trợ restart:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
```

Với `saveState(true)`, reader có thể ghi thông tin trạng thái vào ExecutionContext trong lifecycle do Spring Batch quản lý. Khi Step restart, reader sử dụng thông tin đó để tiếp tục đọc. Các key nội bộ do reader quản lý; ứng dụng không nên tự sửa các key này nếu không có lý do và hiểu rõ hợp đồng của reader.

Với reader tùy chỉnh, nếu cần restart, có thể triển khai `ItemStream` để mở resource, lưu trạng thái và khôi phục vị trí đọc:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Trong triển khai thực tế, `ItemStreamReader<T>` kết hợp `ItemReader<T>` và `ItemStream`. `open()` nhận context đã lưu để khôi phục; `update()` ghi checkpoint hiện tại; `close()` giải phóng resource. Spring Batch gọi các lifecycle method này tại những mốc phù hợp của Step.

## 9. Thời điểm lưu JobExecutionContext và StepExecutionContext

Hai context đều được lưu trong metadata repository, nhưng thời điểm cập nhật gắn với lifecycle khác nhau:

- **StepExecutionContext:** với chunk-oriented Step, trạng thái reader và checkpoint thường được cập nhật tại ranh giới commit của chunk. Điều này giúp khôi phục từ checkpoint đã commit gần nhất.
- **JobExecutionContext:** được chia sẻ giữa các Step trong cùng JobExecution và được repository cập nhật tại các mốc quản lý Job/Step, đặc biệt khi Step hoàn tất. Các Step sau có thể đọc dữ liệu đã được lưu/promote.

Không nên giả định mọi thay đổi trong context đều được ghi xuống database ngay lập tức tại thời điểm gọi `put()`. Việc lưu phụ thuộc vào lifecycle của Step, transaction và repository. Nếu ứng dụng bị dừng đột ngột trước mốc cập nhật metadata, thay đổi chưa được commit có thể không tồn tại sau restart.

Vì vậy, chỉ lưu trong context những trạng thái có thể khôi phục theo các mốc lưu mà framework cung cấp. Nếu cần ghi nhận từng sự kiện nghiệp vụ ngay lập tức hoặc lưu lịch sử chi tiết, hãy dùng bảng nghiệp vụ/audit riêng với transaction phù hợp, không dựa vào context như một event log.

## 10. Những nguyên tắc thiết kế context

### Dùng key có ý nghĩa và tránh trùng tên

Đặt tên key mô tả rõ phạm vi, ví dụ `customerImport.lastProcessedId`, `validation.validRecordCount` hoặc `report.outputVersion`. Tránh các tên chung như `status`, `count` hoặc `value` khi nhiều thành phần cùng ghi context.

StepExecutionContext riêng cho từng Step giúp giảm xung đột key. JobExecutionContext được chia sẻ giữa các Step nên cần quy ước tên key và xác định rõ Step nào sở hữu việc ghi từng key.

### Lưu giá trị nhỏ, có thể serialize

ExecutionContext được lưu vào repository, vì vậy giá trị phải được serializer đang cấu hình hỗ trợ. Các kiểu đơn giản như String, số, boolean, ngày được biểu diễn ổn định hoặc object nhỏ có serialization rõ ràng thường phù hợp.

Tránh lưu:

- Một danh sách hàng triệu bản ghi.
- File content hoặc payload lớn.
- JDBC Connection, HTTP client, stream hoặc resource đang mở.
- Spring bean, proxy hoặc object chứa trạng thái runtime không thể serialize ổn định.
- Password, access token hoặc secret.

Thay vì lưu dữ liệu lớn, hãy lưu một định danh, đường dẫn, checksum hoặc khóa tham chiếu đến dữ liệu được quản lý ở nơi phù hợp. Không lưu bí mật trong context vì metadata có thể được truy cập bởi công cụ vận hành hoặc người có quyền đọc repository.

### Không dùng context như cache dùng chung

Context phục vụ trạng thái thực thi và restart, không phải cache tổng quát giữa nhiều JobInstance hoặc nhiều node. Nếu cần cache, dùng cache chuyên dụng với TTL, giới hạn dung lượng và chính sách invalidation phù hợp.

### Cẩn thận với Step chạy song song

Các Step chạy tuần tự có thể truyền dữ liệu qua JobExecutionContext theo thứ tự flow. Nếu nhiều Step chạy song song và cùng cập nhật JobExecutionContext, có thể phát sinh ghi đè hoặc xung đột logic. Nên dùng key riêng, tránh nhiều writer cùng sở hữu một key và cân nhắc lưu trạng thái vào repository nghiệp vụ có kiểm soát transaction khi cần cập nhật đồng thời.

## 11. Truy cập context bằng API trong code

Ngoài SpEL trong bean `@StepScope`, có thể lấy context trực tiếp từ đối tượng thực thi.

### Lấy StepExecutionContext

```java
StepExecution stepExecution = contribution.getStepExecution();
ExecutionContext stepContext = stepExecution.getExecutionContext();

stepContext.putLong("processedCount", 2_000L);
long processedCount = stepContext.getLong("processedCount", 0L);
```

### Lấy JobExecutionContext

```java
JobExecution jobExecution = stepExecution.getJobExecution();
ExecutionContext jobContext = jobExecution.getExecutionContext();

jobContext.putString("reportVersion", "2026-11");
String reportVersion = jobContext.getString("reportVersion");
```

### Lấy context từ ChunkContext

`ChunkContext` cung cấp `StepContext`, từ đó có thể truy cập các map context cho mục đích đọc:

```java
StepContext stepContext = chunkContext.getStepContext();
Map<String, Object> stepValues = stepContext.getStepExecutionContext();
Map<String, Object> jobValues = stepContext.getJobExecutionContext();
```

Các map này hữu ích để đọc giá trị trong Tasklet. Khi cần ghi và quản lý trạng thái, nên lấy `ExecutionContext` từ `StepExecution` hoặc `JobExecution` như các ví dụ trên để sử dụng API cập nhật chính thức.

## 12. Các lỗi thường gặp

**Dùng StepExecutionContext để truyền dữ liệu sang Step khác:** Step sau có StepExecutionContext riêng nên không tự thấy key của Step trước. Hãy promote key cần chia sẻ lên JobExecutionContext.

**Đưa mọi dữ liệu vào JobExecutionContext:** context cấp Job có phạm vi rộng hơn, nhưng không phải nơi chứa mọi trạng thái. Checkpoint nội bộ của reader nên nằm trong StepExecutionContext.

**Nhầm ExecutionContext với JobParameters:** JobParameters là đầu vào launch và tham gia định danh JobInstance nếu được đánh dấu identifying; ExecutionContext là trạng thái được cập nhật trong lúc chạy.

**Cho rằng gọi `put()` là ghi database ngay:** repository lưu context theo lifecycle và transaction. Thay đổi chưa đến mốc lưu có thể không còn sau sự cố.

**Lưu object không serialize được:** Job có thể lỗi khi repository cố lưu context. Chỉ lưu giá trị tương thích với serializer đã cấu hình.

**Lưu payload lớn hoặc secret:** metadata phình to và có thể làm lộ dữ liệu nhạy cảm. Chỉ lưu khóa tham chiếu hoặc thông tin tối thiểu.

**Để nhiều Step song song ghi cùng key:** dữ liệu có thể ghi đè hoặc không phản ánh kết quả mong muốn. Phân quyền sở hữu key hoặc dùng kho dữ liệu phù hợp cho cập nhật đồng thời.

**Dùng context thay cho bảng nghiệp vụ:** context phục vụ điều phối và restart; dữ liệu cần truy vấn lâu dài, audit hoặc báo cáo nghiệp vụ nên được lưu trong schema nghiệp vụ.

## Kết luận

`JobExecutionContext` lưu trạng thái dùng chung giữa các Step trong cùng một JobExecution. `StepExecutionContext` lưu trạng thái riêng của một Step, đặc biệt hữu ích cho checkpoint của reader và restart. Dữ liệu cần chuyển từ Step này sang Step khác có thể được promote bằng `ExecutionContextPromotionListener`. Hãy phân biệt context với JobParameters, lưu các giá trị nhỏ có thể serialize, dùng key rõ ràng và hiểu thời điểm repository cập nhật metadata. Khi thiết kế đúng phạm vi, hai context giúp Job chia sẻ kết quả trung gian và khôi phục tiến độ đáng tin cậy sau lỗi.
