# `@Value` từ `jobExecutionContext`

Trong Spring Batch, `JobExecution` có một `ExecutionContext` ở phạm vi job. Context này lưu các giá trị nhỏ cần được chia sẻ giữa nhiều step trong cùng một lần chạy job. Một step có thể tạo ra đường dẫn file, ID của lô staging, ngày nghiệp vụ đã chuẩn hóa hoặc số lượng bản ghi; step tiếp theo có thể đọc các giá trị đó để cấu hình reader, processor, writer hoặc tasklet.

Spring Batch hỗ trợ **late binding** bằng Spring Expression Language (SpEL). Với một bean được tạo trong scope của step, có thể inject giá trị từ job execution context bằng biểu thức:

```java
@Value("#{jobExecutionContext['generatedFile']}")
String generatedFile
```

`jobExecutionContext` là biến context do Spring Batch cung cấp trong lúc một step đang chạy. Biểu thức được resolve khi target bean scoped được tạo cho execution, không phải lúc application context khởi động. Vì vậy, bean `@StepScope` có thể nhận giá trị mà step trước đã lưu và promote vào job context.

Đây là cơ chế chia sẻ dữ liệu nhỏ giữa các step. Nó không phải cách truyền một object tùy ý giữa các thread hoặc thay thế database nghiệp vụ. Hãy lưu ID, URI, version, count hoặc giá trị cấu hình nhỏ trong context; dữ liệu lớn nên nằm trong database, staging table hoặc object storage.

## JobExecutionContext là gì?

Mỗi lần chạy job có một `JobExecution`. `JobExecution` giữ một `ExecutionContext` riêng ở phạm vi job. Giá trị trong context này có thể được dùng bởi các step thuộc cùng execution.

```text
JobInstance
    |
    +-- JobExecution #101
           |
           +-- JobExecutionContext
           |      generatedFile = "staging/orders.csv"
           |      importedCount = 12500
           |
           +-- StepExecution: prepareStep
           |      StepExecutionContext
           |        tempFileId = "tmp-42"
           |
           +-- StepExecution: importStep
           |      StepExecutionContext
           |        lastReadLine = 800
           |
           +-- StepExecution: summaryStep
                  StepExecutionContext
                    reportPage = 1
```

Job context phù hợp với giá trị cần chia sẻ giữa các step, ví dụ `generatedFile` hoặc `importedCount`. Step context dành cho checkpoint và state riêng của một step, ví dụ vị trí reader hoặc trạng thái writer.

| Nguồn biểu thức | Phạm vi | Ví dụ |
| --- | --- | --- |
| `jobExecutionContext` | Toàn bộ `JobExecution` hiện tại | `#{jobExecutionContext['generatedFile']}` |
| `stepExecutionContext` | `StepExecution` hiện tại | `#{stepExecutionContext['lastReadLine']}` |
| `jobParameters` | Parameters dùng để định danh/cấu hình job execution | `#{jobParameters['businessDate']}` |

Ba nguồn này có mục đích khác nhau. Nếu một giá trị chỉ dùng để cấu hình lần chạy và có sẵn từ lúc launch, thường nên truyền bằng `JobParameters`. Nếu một step tạo ra giá trị để step sau sử dụng, job context là nơi phù hợp. Nếu giá trị chỉ là checkpoint nội bộ của một step, giữ nó trong step context.

## `@Value` và SpEL late binding

`@Value` là annotation của Spring để inject giá trị. Khi dùng với Spring Batch scope, biểu thức SpEL có thể đọc các biến context do framework cung cấp.

```java
@Bean
@StepScope
ItemReader<OrderInput> orderReader(
        @Value("#{jobExecutionContext['generatedFile']}") String inputFile) {

    return buildOrderReader(inputFile);
}
```

Các phần quan trọng:

- `@Bean` đăng ký reader trong Spring application context.
- `@StepScope` tạo target bean theo từng `StepExecution`.
- `@Value(...)` yêu cầu Spring resolve biểu thức SpEL.
- `jobExecutionContext` là context của `JobExecution` đang chứa step hiện tại.
- `['generatedFile']` truy cập key trong map context.

Nên dùng cú pháp truy cập bằng dấu ngoặc vuông cho key, đặc biệt khi tên key có dấu chấm, dấu gạch hoặc ký tự không phù hợp với property navigation. Ví dụ `#{jobExecutionContext['input.file.name']}`.

### Khác nhau giữa `#{...}` và `${...}`

Trong `@Value`, hai cú pháp thường gặp có ý nghĩa khác nhau:

| Cú pháp | Nguồn giá trị | Ví dụ |
| --- | --- | --- |
| `#{...}` | SpEL expression, có thể truy cập context của Spring Batch | `#{jobExecutionContext['generatedFile']}` |
| `${...}` | Property placeholder từ cấu hình Spring | `${batch.input.directory}` |

Ví dụ, `${batch.input.directory}` thường lấy giá trị từ `application.yml`, environment hoặc property source. `#{jobExecutionContext['generatedFile']}` lấy giá trị được lưu trong context của một job execution cụ thể.

Không viết `@Value("${jobExecutionContext['generatedFile']}")` để truy cập batch context; đó là property placeholder và không có ý nghĩa late binding như mong muốn.

## Vì sao cần `@StepScope`?

Spring tạo các singleton bean thông thường khi application context được khởi tạo. Lúc đó chưa có `JobExecution` hoặc `StepExecution` cụ thể, nên các biến như `jobExecutionContext` chưa có dữ liệu của một lần chạy.

`@StepScope` trì hoãn việc tạo target bean cho tới khi step thực sự chạy. Khi target được tạo, Spring Batch đã gắn `StepExecution` hiện tại vào scope và có thể resolve các biểu thức như `jobExecutionContext`.

```java
@Bean
@StepScope
Tasklet publishTasklet(
        @Value("#{jobExecutionContext['generatedFile']}") String fileKey) {

    return (contribution, chunkContext) -> {
        publishFile(fileKey);
        return RepeatStatus.FINISHED;
    };
}
```

Nếu bỏ `@StepScope`, Spring có thể cố resolve biểu thức khi khởi tạo singleton, trước khi job chạy. Khi đó không có context execution phù hợp để inject. Đây là một trong những lỗi thường gặp khi dùng `@Value` với job/step context.

`@StepScope` tạo một scoped proxy để các bean khác có thể inject reader/tasklet từ application context. Target thật được tạo khi step scope hoạt động. Vì thế, method `@Bean` có thể được gọi trong lúc cấu hình step mà giá trị context vẫn được resolve muộn hơn, khi step chạy.

## Ví dụ: step đầu tạo file, step sau đọc từ jobExecutionContext

Giả sử job có hai step:

1. `prepareFileStep` tạo file staging và lưu key file vào step context.
2. `importFileStep` đọc key đó từ job execution context để cấu hình reader.

Giá trị được ghi vào step context của step đầu, sau đó `ExecutionContextPromotionListener` promote key lên job context khi step hoàn tất.

### Step đầu ghi giá trị vào StepExecutionContext

```java
public class PrepareFileTasklet implements Tasklet {

    private final StagingService stagingService;

    public PrepareFileTasklet(StagingService stagingService) {
        this.stagingService = stagingService;
    }

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        StagingResult result = stagingService.prepareOrdersFile();

        ExecutionContext stepContext =
                contribution.getStepExecution().getExecutionContext();
        stepContext.putString("generatedFile", result.objectKey());
        stepContext.putLong("importedCount", result.recordCount());

        return RepeatStatus.FINISHED;
    }
}
```

`StagingResult` là kiểu dữ liệu do ứng dụng định nghĩa. File thực tế được lưu trong staging storage; context chỉ giữ key và số lượng bản ghi nhỏ.

### Promote key lên job context

```java
@Bean
ExecutionContextPromotionListener prepareFilePromotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {
            "generatedFile",
            "importedCount"
    });
    listener.setStrict(true);
    return listener;
}
```

Listener được gắn vào step tạo dữ liệu. Với cấu hình status mặc định phổ biến, listener promote khi step hoàn tất với exit status `COMPLETED`. `strict=true` làm thiếu key bắt buộc trở thành lỗi rõ ràng thay vì âm thầm bỏ qua.

```java
@Bean
Step prepareFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PrepareFileTasklet tasklet,
        ExecutionContextPromotionListener prepareFilePromotionListener) {

    return new StepBuilder("prepareFileStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .listener(prepareFilePromotionListener)
            .build();
}
```

Sau khi step hoàn tất, `generatedFile` và `importedCount` có trong `JobExecution` context. Step sau có thể inject các key này bằng `@Value`.

### Step sau inject từ jobExecutionContext

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> stagingOrderReader(
        @Value("#{jobExecutionContext['generatedFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("stagingOrderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

Target reader được tạo khi `importFileStep` bắt đầu. Tại thời điểm đó, `prepareFileStep` đã hoàn tất và promotion listener đã đưa key lên job context. Reader nhận đúng resource của lần chạy hiện tại.

### Inject nhiều giá trị cùng lúc

Có thể inject nhiều key bằng các tham số `@Value` riêng:

```java
@Bean
@StepScope
Tasklet importSummaryTasklet(
        @Value("#{jobExecutionContext['generatedFile']}") String fileKey,
        @Value("#{jobExecutionContext['importedCount']}") Long importedCount) {

    return (contribution, chunkContext) -> {
        importSummaryService.record(fileKey, importedCount);
        return RepeatStatus.FINISHED;
    };
}
```

Nên dùng kiểu wrapper như `Long` nếu giá trị có thể thiếu hoặc có default. Nếu dùng primitive `long`, null không thể được biểu diễn và quá trình inject có thể thất bại khi key chưa tồn tại.

## Ghi trực tiếp vào JobExecutionContext

Ngoài promotion listener, code trong step có thể truy cập `JobExecution` và đặt trực tiếp giá trị vào job context:

```java
JobExecution jobExecution =
        contribution.getStepExecution().getJobExecution();

jobExecution.getExecutionContext()
        .putString("generatedFile", result.objectKey());
```

Sau đó step tiếp theo có thể dùng:

```java
@Value("#{jobExecutionContext['generatedFile']}") String inputFile
```

Tuy nhiên, cần hiểu lifecycle lưu job context của `JobRepository` và transaction boundary. Khi dữ liệu được tạo trong một step và cần công bố sau khi step thành công, `ExecutionContextPromotionListener` thường thể hiện ý định rõ ràng hơn: step ghi state vào context riêng, listener promote một allowlist key khi step đạt exit status mong muốn.

Không nên vừa ghi trực tiếp vào job context vừa promote cùng key nếu không có quy tắc ghi rõ ràng; hai nguồn có thể ghi đè nhau hoặc khiến kết quả phụ thuộc thứ tự thực thi.

## Đọc stepExecutionContext hay jobExecutionContext?

Chọn đúng context theo nơi lưu giá trị:

```java
@Bean
@StepScope
Tasklet tasklet(
        @Value("#{stepExecutionContext['currentPage']}") Integer currentPage,
        @Value("#{jobExecutionContext['generatedFile']}") String generatedFile) {

    return (contribution, chunkContext) -> {
        // currentPage là state của step hiện tại.
        // generatedFile là giá trị được chia sẻ ở phạm vi job.
        return RepeatStatus.FINISHED;
    };
}
```

Nếu `generatedFile` chỉ được lưu trong step context của step trước mà chưa promote, biểu thức `jobExecutionContext['generatedFile']` sẽ không tìm thấy key đó. Cần promote key hoặc lưu trực tiếp vào job context theo một cơ chế có kiểm soát.

Không nên đọc step context của một step khác bằng `stepExecutionContext`; biến đó luôn đại diện cho step hiện tại. Để chia sẻ giữa step, dùng job context hoặc một store nghiệp vụ.

## JobScope và StepScope

Spring Batch cung cấp cả `@StepScope` và `@JobScope` để tạo bean theo execution context.

| Scope | Vòng đời target bean | Thường dùng cho |
| --- | --- | --- |
| `@StepScope` | Một target cho mỗi `StepExecution` | Reader, processor, writer, tasklet phụ thuộc context của step đang chạy |
| `@JobScope` | Một target cho mỗi `JobExecution` | Component cần giữ state/cấu hình chung ở phạm vi job |

Ví dụ một bean job-scoped đọc giá trị có sẵn trong job context:

```java
@Bean
@JobScope
JobRunDescriptor jobRunDescriptor(
        @Value("#{jobExecutionContext['businessDate']}") String businessDate) {

    return new JobRunDescriptor(businessDate);
}
```

`JobRunDescriptor` là kiểu dữ liệu do ứng dụng định nghĩa. `@JobScope` phù hợp khi bean được tạo tại thời điểm key đã có và cần dùng chung trong phạm vi job execution.

Nếu giá trị chỉ được tạo ở một step chạy sau khi job bắt đầu, hãy cân nhắc thời điểm bean job-scoped được truy cập lần đầu. Job-scoped target chỉ được tạo một lần cho execution; nếu nó được khởi tạo trước khi key được ghi vào job context, giá trị inject có thể không phản ánh dữ liệu mới. Với reader/tasklet của step tiêu thụ, `@StepScope` thường an toàn và dễ dự đoán hơn vì target được tạo khi step đó bắt đầu, sau step sản xuất dữ liệu.

Không dùng singleton bean thông thường để inject trực tiếp một giá trị phụ thuộc `JobExecution` cụ thể. Singleton tồn tại qua nhiều execution và không có một context job duy nhất để gắn vào.

## Giá trị mặc định khi key không tồn tại

SpEL hỗ trợ toán tử Elvis `?:` để cung cấp giá trị mặc định khi biểu thức bên trái là null.

```java
@Bean
@StepScope
Tasklet publishTasklet(
        @Value("#{jobExecutionContext['format'] ?: 'CSV'}") String format) {

    return (contribution, chunkContext) -> {
        publishUsingFormat(format);
        return RepeatStatus.FINISHED;
    };
}
```

Nếu key `format` không tồn tại hoặc có giá trị null, bean nhận `CSV`. Cách này phù hợp với giá trị tùy chọn có default hợp lệ.

Không nên dùng default để che một key bắt buộc. Ví dụ, nếu step sau phải đọc đúng file do step trước tạo, default một đường dẫn khác có thể làm job xử lý nhầm dữ liệu. Với key bắt buộc, hãy dùng promotion strict mode và kiểm tra key trước khi step tiêu thụ chạy.

### Kiểm tra key bắt buộc

Nếu muốn lỗi có thông điệp rõ ràng khi key không tồn tại, có thể kiểm tra trong tasklet/service bằng API context:

```java
ExecutionContext context =
        contribution.getStepExecution().getJobExecution().getExecutionContext();

if (!context.containsKey("generatedFile")) {
    throw new IllegalStateException(
            "Required job context key 'generatedFile' is missing");
}

String generatedFile = context.getString("generatedFile");
```

Đây là lựa chọn khi muốn kiểm soát lỗi ở runtime. Với constructor injection bằng `@Value`, có thể dùng strict promotion ở step trước để phát hiện thiếu key sớm hơn.

## Type conversion và kiểu dữ liệu

`ExecutionContext` lưu giá trị theo key. Khi inject bằng `@Value`, Spring thực hiện type conversion nếu có converter phù hợp. Dù vậy, nên lưu đúng kiểu ngay từ đầu và dùng kiểu nhận tương ứng.

```java
// Step trước
stepContext.putLong("importedCount", 12500L);
stepContext.putInt("retryWindow", 3);
stepContext.putString("businessDate", "2026-11-15");

// Step sau
@Value("#{jobExecutionContext['importedCount']}") Long importedCount
@Value("#{jobExecutionContext['retryWindow']}") Integer retryWindow
@Value("#{jobExecutionContext['businessDate']}") String businessDate
```

Các nguyên tắc:

- Dùng `putString`, `putLong`, `putInt`, `putBoolean` tương ứng với kiểu dữ liệu.
- Dùng wrapper type (`Long`, `Integer`, `Boolean`) nếu key có thể thiếu.
- Dùng format ổn định cho ngày giờ nếu cần tương thích giữa phiên bản.
- Tránh lưu entity JPA, proxy, stream hoặc object graph lớn.
- Đảm bảo serializer của `JobRepository` có thể lưu và khôi phục kiểu dữ liệu đã chọn.
- Giữ kiểu và ý nghĩa key tương thích khi execution cũ còn cần restart.

Không nên dựa vào conversion ngầm cho dữ liệu phức tạp. Nếu cần truyền object tùy chỉnh, hãy cân nhắc lưu ID/URI rồi truy vấn lại từ kho dữ liệu nghiệp vụ.

## Key name và SpEL syntax

Key là chuỗi trong `ExecutionContext`. Đặt tên rõ ràng, ổn định và tránh trùng giữa các thành phần.

Ví dụ:

```java
context.putString("report.objectKey", objectKey);
context.putLong("report.recordCount", recordCount);
context.putString("validation.resultCode", resultCode);
```

Truy cập bằng dấu ngoặc vuông:

```java
@Value("#{jobExecutionContext['report.objectKey']}") String objectKey
@Value("#{jobExecutionContext['report.recordCount']}") Long recordCount
@Value("#{jobExecutionContext['validation.resultCode']}") String resultCode
```

Dấu chấm trong key là một phần của tên key; nó không tự tạo nested map. Vì vậy, cú pháp `['report.objectKey']` giúp truy cập chính xác chuỗi key.

Không dùng các tên quá chung như `data`, `result` hoặc `value` trong job context có nhiều step. Namespace theo nghiệp vụ hoặc step tạo giá trị giúp giảm xung đột và dễ truy vết.

## `@Value` từ jobExecutionContext trong reader

Reader thường là trường hợp sử dụng late binding rõ nhất. Step trước xác định file hoặc resource; reader của step sau được cấu hình theo giá trị đó.

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobExecutionContext['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

Reader target được tạo trong step scope, vì vậy `inputFile` được resolve theo `JobExecution` hiện tại. `saveState(true)` lưu checkpoint reader để hỗ trợ restart; nó không thay thế việc bảo đảm `inputFile` trỏ tới cùng nguồn dữ liệu khi restart.

Nếu `inputFile` được tạo trong step trước, hãy promote key lên job context sau khi step đó hoàn thành. Nếu file được truyền từ lúc launch, dùng `jobParameters` có thể phù hợp hơn:

```java
@Value("#{jobParameters['inputFile']}") String inputFile
```

## `@Value` từ jobExecutionContext trong processor hoặc writer

Processor và writer cũng có thể là step-scoped bean nếu cần giá trị do step trước tạo.

```java
@Bean
@StepScope
ItemProcessor<OrderInput, Order> orderProcessor(
        @Value("#{jobExecutionContext['businessDate']}") String businessDate,
        OrderMapper mapper) {

    return input -> mapper.toOrder(input, businessDate);
}
```

```java
@Bean
@StepScope
ItemWriter<Order> orderWriter(
        @Value("#{jobExecutionContext['targetTable']}") String targetTable,
        OrderWriteService writeService) {

    return chunk -> writeService.write(targetTable, chunk.getItems());
}
```

Các ví dụ minh họa injection theo scope. Nếu `targetTable` được dùng để tạo SQL động, không nối chuỗi trực tiếp từ dữ liệu không tin cậy; tên bảng cần được kiểm soát bằng allowlist hoặc mapping cố định. Giá trị context không tự động trở thành dữ liệu đáng tin cậy chỉ vì nó được lưu trong repository.

## Dùng `@Value` trong Tasklet

Tasklet có thể nhận giá trị job context trực tiếp qua constructor bean method:

```java
@Bean
@StepScope
Tasklet sendReportTasklet(
        @Value("#{jobExecutionContext['reportObjectKey']}") String reportObjectKey,
        ReportPublisher publisher) {

    return (contribution, chunkContext) -> {
        publisher.publish(reportObjectKey);
        return RepeatStatus.FINISHED;
    };
}
```

Nếu tasklet là class được tạo bằng `new` bên trong một bean singleton, `@Value` trên constructor hoặc field của class đó không tự được Spring xử lý. Hãy để Spring tạo tasklet bean có scope phù hợp hoặc dùng API `StepExecution`/`JobExecution` trong `execute`.

Ví dụ truy cập context trực tiếp trong tasklet:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    ExecutionContext jobContext =
            contribution.getStepExecution()
                    .getJobExecution()
                    .getExecutionContext();

    String reportObjectKey = jobContext.getString("reportObjectKey");
    publish(reportObjectKey);

    return RepeatStatus.FINISHED;
}
```

Chọn constructor injection khi muốn dependency hiển thị rõ trong cấu hình bean. Truy cập qua `StepExecution` hữu ích khi key là tùy chọn hoặc cần kiểm tra/đọc nhiều giá trị động.

## Giá trị context được tạo ở step trước

Để step sau inject đúng giá trị, cần bảo đảm thứ tự lifecycle:

1. Step tạo dữ liệu và đặt key vào step context hoặc job context.
2. Nếu key nằm trong step context, promotion listener promote key sau khi step hoàn tất với status được cho phép.
3. `JobRepository` lưu job context theo lifecycle step/job.
4. Step tiếp theo bắt đầu.
5. Target bean `@StepScope` được tạo và SpEL đọc job context.

Nếu bean step sau bị khởi tạo quá sớm ở scope không phù hợp, hoặc key chưa được promote, biểu thức có thể trả null/không tìm thấy giá trị.

### Promotion listener và statuses

`ExecutionContextPromotionListener` cho phép khai báo danh sách key và exit status cho phép promotion:

```java
listener.setKeys(new String[] { "inputFile", "businessDate" });
listener.setStatuses(new String[] { "COMPLETED" });
listener.setStrict(true);
```

`statuses` xét `ExitStatus` của step. Nếu ứng dụng dùng custom exit code, cần khai báo đúng code muốn cho phép promotion. Không promote kết quả chưa hoàn tất chỉ để step sau có dữ liệu; xác định rõ trạng thái nào bảo đảm key hợp lệ.

## JobParameters, jobExecutionContext và stepExecutionContext

Không nên dùng job context cho mọi loại parameter. Chọn nguồn dựa trên vòng đời dữ liệu:

| Nhu cầu | Nguồn nên dùng | Biểu thức |
| --- | --- | --- |
| Ngày nghiệp vụ do caller truyền khi launch | Job parameters | `#{jobParameters['businessDate']}` |
| File do step chuẩn bị tạo ra | Job execution context sau promotion | `#{jobExecutionContext['generatedFile']}` |
| Page/offset reader của step hiện tại | Step execution context | `#{stepExecutionContext['nextPage']}` |
| Cấu hình cố định từ application.yml | Property placeholder | `${batch.reader.page-size}` |
| Dữ liệu nghiệp vụ lớn | Database/staging/object storage | Context chỉ lưu ID/URI |

Job parameters xác định danh tính `JobInstance` dựa trên identifying flags. Job context là state của một `JobExecution`; nó không thay thế identifying parameters. Nếu cần restart cùng instance, giữ nguyên identifying parameters và bảo đảm giá trị context được lưu tương thích.

## Restart và giá trị được inject

Khi job restart, Spring Batch tạo `JobExecution` mới cho cùng `JobInstance` nếu trạng thái cho phép. Job context được khôi phục từ metadata theo restart semantics. Bean `@StepScope` của step được restart được tạo cho `StepExecution` mới và có thể đọc giá trị job context đã lưu.

Ví dụ, `prepareFileStep` đã hoàn thành và promote `generatedFile`, nhưng `importFileStep` thất bại. Khi restart:

- Step prepare đã hoàn thành có thể được bỏ qua theo restart semantics.
- Job context của execution trước được khôi phục theo cơ chế repository.
- Step import được restart và target reader mới được tạo.
- `@Value("#{jobExecutionContext['generatedFile']}")` nhận lại key đã lưu.
- Reader cần dùng đúng file/version mà lần chạy trước đã tạo.

Resource được tham chiếu phải còn tồn tại trong thời gian job có thể restart. Nếu file bị xóa hoặc thay thế, biểu thức vẫn có thể resolve được đường dẫn nhưng reader không thể đọc đúng dữ liệu ban đầu.

Không tạo identifying parameter mới ở lần restart chỉ để làm mới file path. Nếu cần chạy một lần nghiệp vụ mới, hãy tạo logical instance mới có chủ đích và định nghĩa rõ output resource mới.

## Threading và phạm vi context

`jobExecutionContext` thuộc một `JobExecution`; `stepExecutionContext` thuộc một `StepExecution`. Các bean scoped dùng proxy để truy cập context gắn với execution hiện tại.

Trong step chạy đa luồng hoặc partitioned step, cần thận trọng với bean scope và dữ liệu mutable. Một giá trị job context dùng chung không nên bị nhiều worker ghi đồng thời mà không có quy tắc đồng bộ. Nếu mỗi partition có state riêng, lưu state trong step/partition execution context tương ứng.

`@Value` inject một giá trị khi target bean được tạo; nó không phải một subscription tự động cập nhật field mỗi khi context thay đổi. Nếu một key được sửa sau khi bean target đã được tạo, field đã inject có thể vẫn giữ giá trị cũ. Vì vậy, hãy chỉ inject giá trị đã sẵn sàng trước khi step-scoped bean được tạo. Với dữ liệu cần đọc động sau đó, truy cập context qua execution API tại thời điểm sử dụng hoặc thiết kế một service đọc state có kiểm soát.

## Bảo mật và kích thước dữ liệu

Job execution context được lưu trong batch metadata database và có thể xuất hiện trong backup hoặc công cụ vận hành. Không lưu password, access token, private key hoặc payload cá nhân/nhạy cảm không cần thiết.

Nếu step sau cần credential để truy cập resource, lưu một secret reference rồi lấy secret từ secret manager khi chạy. Nếu cần truyền file lớn, lưu file trong object storage và inject object key/version thay vì byte array.

Context nên nhỏ và có kiểu ổn định. Các key có thể tồn tại qua nhiều lần deploy nếu job chưa hoàn tất; thay đổi kiểu dữ liệu hoặc tên key có thể làm restart cũ không tương thích.

## Lỗi thường gặp khi dùng `@Value` từ jobExecutionContext

### Quên `@StepScope`

Bean singleton được tạo trước khi có job execution cụ thể. SpEL không có context đúng để resolve. Dùng `@StepScope` cho reader/processor/writer/tasklet phụ thuộc execution.

### Đọc nhầm step context

`stepExecutionContext` là context của step hiện tại, không phải step trước. Nếu step sau cần key từ step trước, promote key lên job context hoặc lưu trực tiếp vào job context theo lifecycle rõ ràng.

### Quên promotion

Step trước ghi key vào step context nhưng step sau đọc `jobExecutionContext`. Key không tự xuất hiện ở job context. Đăng ký `ExecutionContextPromotionListener` với đúng key và status.

### Dùng JobScope cho giá trị chỉ có sau một step

Job-scoped bean chỉ được tạo một lần cho job execution. Nếu target được khởi tạo trước khi key được tạo, field inject có thể không có giá trị mong muốn. Với bean tiêu thụ ở step sau, dùng StepScope để late-bind tại thời điểm step đó bắt đầu.

### Dùng `${...}` thay vì `#{...}`

`${...}` là property placeholder; `#{...}` là SpEL expression dùng để truy cập batch context.

### Key không tồn tại hoặc sai chính tả

Map lookup có thể trả null. Dùng strict promotion cho key bắt buộc, kiểm tra key và chọn wrapper type nếu có thể null.

### Dùng primitive cho giá trị tùy chọn

Primitive như `long` không biểu diễn null. Dùng `Long` hoặc cung cấp default SpEL có ý nghĩa.

### Inject object lớn vào bean

Context không phải data store. Lưu ID/URI/version và đọc dữ liệu từ staging/database/object storage.

### Thay key hoặc kiểu dữ liệu khi job cũ còn restart

Execution context đã lưu có thể không tương thích. Giữ contract key/type ổn định hoặc có kế hoạch migration.

### Mong field `@Value` tự cập nhật khi context thay đổi

Giá trị được resolve khi target bean scoped được tạo. Nếu cần dữ liệu động, truy cập execution context tại thời điểm sử dụng.

## Kiểm thử `@Value` từ jobExecutionContext

Unit test biểu thức SpEL riêng lẻ không đủ để chứng minh late binding hoạt động trong job lifecycle. Nên có integration test chạy ít nhất hai step với `JobRepository` và scope thực tế.

### Kiểm thử promotion và injection end-to-end

Một test có thể:

1. Chạy `prepareFileStep`, ghi `generatedFile` vào step context.
2. Cho promotion listener promote key sau khi step hoàn thành.
3. Chạy `importFileStep` với reader/tasklet `@StepScope` inject key từ job context.
4. Dùng service test double hoặc writer để ghi nhận giá trị nhận được.
5. Xác nhận step sau nhận đúng giá trị và xử lý đúng resource.

Ví dụ tasklet tiêu thụ:

```java
@Bean
@StepScope
Tasklet consumeGeneratedFileTasklet(
        @Value("#{jobExecutionContext['generatedFile']}") String generatedFile,
        FileImportService importService) {

    return (contribution, chunkContext) -> {
        importService.importFile(generatedFile);
        return RepeatStatus.FINISHED;
    };
}
```

Trong test, mock hoặc fake `FileImportService` và xác nhận `importFile` nhận đúng key do step trước tạo. Không hard-code giá trị khác với dữ liệu được promote.

### Kiểm thử key thiếu

Tạo fixture không ghi key hoặc cấu hình listener strict. Xác nhận step tạo thất bại hoặc step tiêu thụ dừng với lỗi rõ ràng theo contract. Không để job âm thầm dùng một file default không liên quan.

### Kiểm thử default value

Với key tùy chọn, xác nhận biểu thức Elvis cung cấp default khi key không có và dùng giá trị context khi key có mặt.

### Kiểm thử type conversion

Ghi `Long`, `Integer` hoặc `String` vào context rồi xác nhận bean nhận đúng kiểu/giá trị. Với custom type, kiểm tra serializer và khả năng đọc lại metadata.

### Kiểm thử restart

Cho step tạo hoàn tất và step tiêu thụ thất bại. Restart cùng identifying parameters; xác nhận bean `@StepScope` được tạo lại và inject giá trị đã lưu trong job context. Kiểm tra resource được tham chiếu vẫn tồn tại và đúng version.

### Kiểm thử scope timing

Đảm bảo bean không được khởi tạo trước khi key được tạo. Có thể ghi nhận giá trị nhận trong fake service ở step tiêu thụ. Nếu chuyển bean từ `@StepScope` sang `@JobScope`, kiểm tra thời điểm target được tạo và tránh khởi tạo trước khi dữ liệu sẵn sàng.

## Nguyên tắc thiết kế

Khi dùng `@Value` từ job execution context, hãy xác định:

1. Key được tạo ở step nào và trong context nào?
2. Nếu key nằm ở step context, promotion listener đã promote nó chưa?
3. Step nào tiêu thụ giá trị và bean có `@StepScope` phù hợp không?
4. Target bean được tạo sau khi key đã sẵn sàng chưa?
5. Key có bắt buộc hay tùy chọn; có cần strict promotion hoặc default không?
6. Kiểu dữ liệu được ghi và inject có tương thích không?
7. Giá trị có nhỏ, ổn định và serializer-compatible không?
8. Resource được tham chiếu có tồn tại khi restart không?
9. Identifying parameters có ổn định qua restart không?
10. Integration test đã xác nhận promotion, injection, missing key và restart chưa?

Với phần lớn trường hợp, cách rõ ràng là step sản xuất ghi key vào step context, `ExecutionContextPromotionListener` promote key sau khi step thành công, và bean của step tiêu thụ dùng `@StepScope` cùng `@Value("#{jobExecutionContext['key']}")`. Cách này làm rõ nguồn dữ liệu, thời điểm inject và phạm vi chia sẻ.

## Ghi nhớ

`@Value("#{jobExecutionContext['key']}")` dùng SpEL để inject một giá trị từ `JobExecution` context. Bean phụ thuộc execution phải dùng scope phù hợp, thường là `@StepScope`, để target được tạo khi step chạy thay vì lúc application khởi động. Nếu step trước ghi key vào step context, cần promote key lên job context bằng `ExecutionContextPromotionListener` trước khi step sau bắt đầu. Dùng `stepExecutionContext` cho state của step hiện tại, `jobParameters` cho dữ liệu đầu vào lúc launch và `${...}` cho property cấu hình. Chọn wrapper type/default cho key tùy chọn, strict promotion cho key bắt buộc, lưu giá trị nhỏ và ổn định, đồng thời giữ resource/identifying parameters phù hợp cho restart. Kiểm thử end-to-end để xác nhận target bean nhận đúng giá trị sau promotion và có thể khôi phục khi restart.
