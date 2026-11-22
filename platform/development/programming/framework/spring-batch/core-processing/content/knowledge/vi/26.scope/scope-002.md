# Late binding từ JobParameters

Trong Spring Batch, `JobParameters` là các giá trị đầu vào được truyền khi khởi chạy một Job, chẳng hạn đường dẫn file, ngày nghiệp vụ, mã lô hoặc chế độ xử lý. Nhiều bean của batch cần những giá trị này để biết phải đọc nguồn nào, lọc dữ liệu theo phạm vi nào hoặc tạo kết quả ở đâu.

Vấn đề là các bean Spring thông thường thường được tạo khi application context khởi động, trong khi `JobParameters` chỉ có sẵn khi một JobExecution và StepExecution cụ thể bắt đầu. **Late binding** giải quyết khoảng cách này: Spring trì hoãn việc tạo hoặc lấy giá trị cấu hình cho đến khi scope của Job hoặc Step đang hoạt động, rồi inject giá trị từ `JobParameters` bằng SpEL.

Trong Spring Batch, cách dùng phổ biến nhất là khai báo bean với `@StepScope` và lấy tham số qua biểu thức như `@Value("#{jobParameters['input.file']}")`. Điều này đặc biệt hữu ích cho `ItemReader`, `ItemWriter`, `Tasklet` và các dependency có cấu hình thay đổi theo từng lần chạy.

## 1. JobParameters là gì?

`JobParameters` là tập hợp các tham số được cung cấp khi launch Job. Chúng mô tả công việc cần thực hiện, ví dụ:

- `input.file`: đường dẫn file đầu vào.
- `businessDate`: ngày nghiệp vụ cần xử lý.
- `batchId`: mã lô dữ liệu.
- `sourceSystem`: hệ thống nguồn.
- `output.directory`: thư mục tạo kết quả.
- `mode`: chế độ chạy như FULL hoặc DELTA.

Ví dụ tạo JobParameters bằng Java:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("input.file", "/data/in/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("batchId", "BATCH-20261115-01", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Tham số được thêm vào builder có tên, giá trị và cờ identifying. Cờ này quyết định tham số có tham gia định danh `JobInstance` hay không. Nó không quyết định tham số có được inject vào bean hay không: cả identifying và non-identifying JobParameters đều có thể được đọc qua late binding.

JobParameters là dữ liệu đầu vào của một JobExecution và được xem là bất biến trong quá trình thực thi. Nếu cần lưu tiến độ hoặc kết quả phát sinh khi Job chạy, hãy dùng `ExecutionContext` hoặc kho dữ liệu nghiệp vụ phù hợp thay vì cố thay đổi JobParameters.

## 2. Late binding giải quyết vấn đề gì?

Giả sử một ứng dụng có Job import khách hàng từ file. Mỗi lần chạy có thể nhận file khác nhau:

```text
Lần chạy A: input.file = /data/customers-2026-11-14.csv
Lần chạy B: input.file = /data/customers-2026-11-15.csv
```

Nếu reader được tạo như một singleton thông thường và nhận đường dẫn file ngay khi application context khởi động, reader không biết JobParameters của từng lần chạy. Bean có thể giữ đường dẫn cố định hoặc không có giá trị cần thiết.

Late binding cho phép reader được cấu hình khi Step bắt đầu. Spring Batch lúc đó đã có `StepExecution`, `JobExecution` và `JobParameters`, nên biểu thức SpEL có thể lấy đúng giá trị của lần chạy hiện tại.

```text
Application context khởi động
          |
          v
Đăng ký scoped proxy của reader
          |
          v
Launch Job với JobParameters
          |
          v
Step bắt đầu, StepScope được kích hoạt
          |
          v
Tạo target reader cho StepExecution hiện tại
          |
          v
Inject input.file từ JobParameters
          |
          v
Reader mở đúng file của lần chạy
```

Nhờ đó, cùng một cấu hình Job có thể xử lý nhiều file hoặc ngày nghiệp vụ khác nhau mà không cần tạo một bean reader riêng cho từng giá trị.

## 3. Vì sao cần `@StepScope`?

`@StepScope` đánh dấu bean thuộc phạm vi một `StepExecution`. Spring tạo scoped proxy khi application context khởi động; target bean thực sự được tạo khi StepExecution tương ứng hoạt động. Lúc đó, các giá trị như `jobParameters`, `stepExecutionContext` và `jobExecutionContext` mới có thể được phân giải.

Ví dụ:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .build();
}
```

Điểm quan trọng là `@StepScope` nằm trên phương thức `@Bean` tạo reader. Spring đăng ký proxy cho bean; khi Step cần sử dụng reader, proxy chuyển lời gọi tới target được tạo trong scope của StepExecution hiện tại.

Nếu bỏ `@StepScope`, Spring có thể cố tạo reader khi khởi tạo application context. Khi đó không có JobParameters của một lần chạy cụ thể để phân giải biểu thức. Lỗi có thể xuất hiện ngay lúc khởi động hoặc khi bean được khởi tạo, tùy cách cấu hình.

## 4. Đọc JobParameters bằng SpEL

Spring Batch cung cấp các biến ngữ cảnh cho SpEL. Để đọc JobParameters, dùng `jobParameters` và truy cập theo key:

```java
@Value("#{jobParameters['input.file']}") String inputFile
```

Với key có dấu chấm hoặc ký tự đặc biệt, cú pháp truy cập bằng dấu ngoặc vuông là cách rõ ràng và an toàn hơn dot notation.

Một số ví dụ:

```java
@Value("#{jobParameters['businessDate']}") String businessDate
@Value("#{jobParameters['batchId']}") String batchId
@Value("#{jobParameters['sourceSystem']}") String sourceSystem
@Value("#{jobParameters['output.directory']}") String outputDirectory
```

Giá trị được chuyển đổi sang kiểu tham số của method theo cơ chế conversion của Spring và kiểu JobParameter được lưu. Nếu dùng kiểu ngày hoặc số, hãy bảo đảm kiểu JobParameter và kiểu nhận tương thích; khi format đầu vào phức tạp, có thể nhận `String` rồi parse tường minh để thông báo lỗi rõ ràng.

Ví dụ parse ngày:

```java
@Bean
@StepScope
Tasklet reconcileTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        ReconciliationService service) {

    LocalDate date = LocalDate.parse(businessDate);

    return (contribution, chunkContext) -> {
        service.reconcile(date);
        return RepeatStatus.FINISHED;
    };
}
```

Trong ví dụ, ngày được parse khi bean được tạo trong scope Step. Nếu chuỗi không đúng định dạng ISO `yyyy-MM-dd`, `LocalDate.parse()` ném exception và Step không thể khởi tạo bean thành công. Có thể thực hiện validation rõ ràng hơn trước khi gọi service.

## 5. Late binding cho ItemReader

`ItemReader` thường cần biết resource, query hoặc phạm vi dữ liệu trước khi bắt đầu đọc. Đây là một trong những trường hợp sử dụng `@StepScope` phổ biến nhất.

Ví dụ reader đọc file được truyền từ JobParameters:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("Job parameter input.file is required");
    }

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

Step sử dụng reader như dependency bình thường:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> customerReader,
        ItemProcessor<CustomerInput, Customer> customerProcessor,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(customerReader)
            .processor(customerProcessor)
            .writer(customerWriter)
            .build();
}
```

`customerReader` được inject dưới dạng scoped proxy. Khi Step chạy, proxy phân giải target reader với đường dẫn file của JobExecution hiện tại.

Với reader dùng `saveState(true)`, Spring Batch có thể lưu checkpoint trong StepExecutionContext để hỗ trợ restart. Late binding xác định resource đầu vào; checkpoint xác định vị trí đọc đã lưu. Hai cơ chế có liên quan nhưng giải quyết hai việc khác nhau.

## 6. Late binding cho Tasklet

Tasklet cũng có thể nhận JobParameters khi tạo bean. Ví dụ một Tasklet tạo báo cáo cho ngày nghiệp vụ:

```java
@Bean
@StepScope
Tasklet generateDailyReportTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['output.directory']}") String outputDirectory,
        ReportService reportService) {

    LocalDate date = LocalDate.parse(businessDate);
    Path output = Path.of(outputDirectory);

    return (contribution, chunkContext) -> {
        reportService.generate(date, output);
        return RepeatStatus.FINISHED;
    };
}
```

Khai báo Step:

```java
@Bean
Step generateDailyReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet generateDailyReportTasklet) {

    return new StepBuilder("generateDailyReportStep", jobRepository)
            .tasklet(generateDailyReportTasklet, transactionManager)
            .build();
}
```

Tasklet được tạo khi StepScope hoạt động nên có thể dùng đúng ngày và thư mục của lần chạy hiện tại. Nếu Tasklet được khai báo là singleton, không nên đọc JobParameters trực tiếp trong constructor hoặc field khởi tạo vì lúc đó chưa có execution context.

## 7. Late binding cho ItemProcessor và ItemWriter

Processor có thể cần một tham số để chọn quy tắc chuyển đổi, còn writer có thể cần tên bảng, thư mục hoặc chế độ ghi theo lần chạy.

Ví dụ processor nhận chế độ xử lý:

```java
@Bean
@StepScope
ItemProcessor<CustomerInput, Customer> customerProcessor(
        @Value("#{jobParameters['mode']}") String mode,
        CustomerMappingService mappingService) {

    return input -> mappingService.map(input, mode);
}
```

Ví dụ writer nhận batch ID:

```java
@Bean
@StepScope
JdbcBatchItemWriter<Customer> customerWriter(
        DataSource dataSource,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO imported_customer
                        (batch_id, customer_id, full_name)
                    VALUES
                        (:batchId, :customerId, :fullName)
                    """)
            .itemSqlParameterSourceProvider(item -> {
                MapSqlParameterSource params =
                        new MapSqlParameterSource();
                params.addValue("batchId", batchId);
                params.addValue("customerId", item.customerId());
                params.addValue("fullName", item.fullName());
                return params;
            })
            .build();
}
```

Các ví dụ trên minh họa ý tưởng late binding; kiểu writer và mapping cần phù hợp với model thực tế của ứng dụng. Không nên dùng JobParameters để thay đổi tên bảng hoặc ghép SQL động từ input không được kiểm soát. Nếu tham số ảnh hưởng đến cấu trúc SQL, hãy dùng allowlist và parameter binding cho giá trị dữ liệu.

## 8. Phân biệt `@StepScope` và `@JobScope`

Spring Batch có hai scope thường được dùng cho late binding:

- `@StepScope`: bean có vòng đời theo một StepExecution.
- `@JobScope`: bean có vòng đời theo một JobExecution.

Cả hai đều có thể đọc `jobParameters`, nhưng phạm vi tạo bean khác nhau.

| Tiêu chí | `@StepScope` | `@JobScope` |
|---|---|---|
| Phạm vi | Một StepExecution | Một JobExecution |
| Thường dùng cho | Reader, processor, writer, Tasklet và dependency riêng Step | Dependency cần tồn tại trong phạm vi Job và được nhiều Step sử dụng |
| Có thể đọc JobParameters | Có | Có |
| Có thể đọc StepExecutionContext | Có | Không phải scope phù hợp để gắn với một StepExecution cụ thể |
| Có thể đọc JobExecutionContext | Có | Có |

Ví dụ bean JobScope:

```java
@Bean
@JobScope
BatchRunDescriptor batchRunDescriptor(
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new BatchRunDescriptor(batchId, businessDate);
}
```

Một Step có thể nhận `BatchRunDescriptor` như dependency. Bean được tạo trong phạm vi JobExecution hiện tại, nên các Step trong cùng JobExecution có thể dùng cùng descriptor theo scope.

Trong đa số trường hợp reader cần một resource riêng cho Step, hãy dùng `@StepScope`. Dùng `@JobScope` khi thật sự cần trạng thái hoặc cấu hình chung ở phạm vi JobExecution. Job scope có những giới hạn trong một số mô hình chạy song song/partitioning vì context của JobExecution có thể được truy cập đồng thời; cần kiểm tra hỗ trợ của phiên bản và thiết kế thread safety phù hợp.

## 9. Đọc JobParameters và ExecutionContext cùng lúc

Late binding không chỉ áp dụng cho JobParameters. Một bean `@StepScope` có thể nhận dữ liệu từ nhiều context:

```java
@Bean
@StepScope
Tasklet exportPartitionTasklet(
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId,
        @Value("#{jobExecutionContext['sourceVersion']}") String sourceVersion,
        ExportService exportService) {

    return (contribution, chunkContext) -> {
        exportService.export(batchId, minId, maxId, sourceVersion);
        return RepeatStatus.FINISHED;
    };
}
```

Trong ví dụ:

- `jobParameters['batchId']` là đầu vào do caller cung cấp khi launch Job.
- `stepExecutionContext['minId']` và `maxId` là phạm vi được gán cho Step hiện tại, chẳng hạn bởi `Partitioner`.
- `jobExecutionContext['sourceVersion']` là trạng thái hoặc metadata dùng chung trong JobExecution, thường được Step trước ghi hoặc promote.

Việc lấy giá trị từ context yêu cầu key đã tồn tại tại thời điểm bean được tạo. Nếu key chưa được ghi hoặc Step trước không chạy, giá trị có thể là `null`; cần kiểm tra và báo lỗi rõ ràng thay vì để lỗi xuất hiện muộn ở service.

## 10. JobParameters identifying và non-identifying

Mỗi JobParameter có cờ identifying. Các tham số identifying tham gia tạo định danh `JobInstance`; các tham số non-identifying vẫn có thể được đọc nhưng không ảnh hưởng định danh instance.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("input.file", "/data/customers-2026-11-15.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

Ở đây, file và ngày nghiệp vụ xác định công việc cần chạy; người yêu cầu chỉ là metadata bổ sung.

Một tham số vẫn có thể được late-bind dù là non-identifying:

```java
@Value("#{jobParameters['requestedBy']}") String requestedBy
```

Hãy đánh dấu identifying cho các giá trị làm thay đổi đơn vị công việc nghiệp vụ, chẳng hạn file đầu vào, ngày xử lý hoặc batch ID. Nếu một giá trị ảnh hưởng đến dữ liệu cần xử lý nhưng bị đánh dấu non-identifying, một lần launch có thể bị xem là cùng JobInstance với execution trước. Điều này làm restart và đối soát khó hiểu nếu giá trị thay đổi.

Khi restart, hãy giữ identifying parameters ổn định. Không thêm timestamp hoặc UUID mới chỉ để tránh lỗi `JobInstanceAlreadyCompleteException`; việc đó tạo JobInstance mới thay vì restart công việc cũ.

## 11. Kiểu dữ liệu và chuyển đổi tham số

JobParameters hỗ trợ các kiểu dữ liệu được Spring Batch quản lý. Khi inject vào bean, Spring cần chuyển giá trị sang kiểu tham số của phương thức hoặc field.

Ví dụ dùng chuỗi:

```java
@Bean
@StepScope
Tasklet closeBusinessDayTasklet(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        ClosingService closingService) {

    LocalDate date = LocalDate.parse(businessDate);
    return (contribution, chunkContext) -> {
        closingService.close(date);
        return RepeatStatus.FINISHED;
    };
}
```

Nếu ứng dụng tạo tham số có kiểu `LocalDate` và phiên bản Spring Batch/ConversionService đang dùng hỗ trợ chuyển đổi tương ứng, có thể inject trực tiếp kiểu ngày. Tuy nhiên, với dữ liệu định dạng đặc thù hoặc tương thích nhiều phiên bản, nhận `String` rồi parse tường minh thường giúp kiểm soát format và thông báo lỗi.

Với số:

```java
@Value("#{jobParameters['pageSize']}") Integer pageSize
```

Hãy kiểm tra giá trị nằm trong phạm vi hợp lệ trước khi dùng. Một `pageSize` bằng 0 hoặc âm có thể làm reader lỗi hoặc tạo tải không mong muốn.

## 12. Tham số bắt buộc và giá trị mặc định

Nếu tham số bắt buộc bị thiếu, nên dừng sớm với thông báo dễ hiểu. Có thể kiểm tra null/blank ngay khi tạo bean StepScope:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> reader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
                "Required JobParameter 'input.file' is missing");
    }

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName")
            .targetType(CustomerInput.class)
            .build();
}
```

Với tham số tùy chọn, có thể dùng giá trị mặc định trong SpEL:

```java
@Value("#{jobParameters['mode'] ?: 'FULL'}") String mode
```

Nếu `mode` không có giá trị, bean nhận `FULL`. Sau đó nên validate giá trị nằm trong tập được hỗ trợ, ví dụ `FULL` hoặc `DELTA`. Không nên dùng default cho tham số bắt buộc như đường dẫn file nếu điều đó có thể khiến Job vô tình đọc nhầm một resource mặc định.

## 13. Late binding và vòng đời scoped proxy

Một bean `@StepScope` không được tạo target ngay khi application context khởi động. Spring đăng ký proxy để các bean khác có thể inject dependency từ sớm. Khi StepExecution hoạt động, proxy tìm scope context hiện tại và tạo hoặc lấy target bean tương ứng.

Điều này giải thích vì sao có thể inject một reader `@StepScope` vào phương thức `@Bean` định nghĩa Step dù JobParameters chưa có ở thời điểm cấu hình:

```java
@Bean
Step importStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader) {

    return new StepBuilder("importStep", jobRepository)
            .<CustomerInput, Customer>chunk(100, transactionManager)
            .reader(reader)
            .build();
}
```

`reader` ở đây là proxy. Việc truyền proxy vào Step không buộc target reader phải được tạo ngay lúc khai báo Step.

Không nên gọi trực tiếp method `@Bean` để lấy target rồi đọc field phụ thuộc JobParameters ngoài một Step đang hoạt động. Bean scoped chỉ có thể phân giải context khi scope tương ứng đã được mở.

## 14. Vì sao không nên inject JobParameters vào singleton bean?

Singleton bean thường được tạo một lần cho application context và có thể được dùng bởi nhiều JobExecution. Nếu giữ JobParameters trong field singleton, giá trị có thể không tồn tại lúc khởi tạo hoặc bị chia sẻ giữa các lần chạy.

Ví dụ thiết kế không phù hợp:

```java
@Component
public class CustomerReaderFactory {

    @Value("#{jobParameters['input.file']}")
    private String inputFile;

    // Singleton không có một StepExecution cụ thể để phân giải tham số.
}
```

Thay vào đó, đặt late-bound value trên bean được tạo theo StepScope:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {
    // Tạo reader từ tham số của StepExecution hiện tại.
}
```

Nếu một singleton service cần dùng giá trị thay đổi theo lần chạy, hãy truyền giá trị đó qua method argument từ component StepScope, thay vì lưu JobParameters vào mutable field của singleton.

## 15. Late binding trong partitioning và chạy song song

Trong partitioning, mỗi worker StepExecution có `StepExecutionContext` riêng. Một reader `@StepScope` có thể nhận cả JobParameters chung của Job và phạm vi riêng của partition:

```java
@Bean
@StepScope
JdbcPagingItemReader<Customer> partitionReader(
        DataSource dataSource,
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return createReader(dataSource, batchId, minId, maxId);
}
```

JobParameters xác định lô chung; StepExecutionContext xác định phạm vi dữ liệu mà partition hiện tại được xử lý. Vì mỗi worker có StepExecution riêng, `@StepScope` giúp mỗi worker nhận đúng min/max của nó.

Với multi-threaded Step hoặc code tự tạo thread, scope context có thể không được truyền tự động sang thread do ứng dụng tạo. Cần dùng mô hình concurrency được Spring Batch hỗ trợ và tránh truy cập scoped proxy từ thread không có context. `@JobScope` cũng cần thận trọng trong partitioning hoặc flow chạy song song vì nhiều worker có thể truy cập cùng JobExecution-scoped bean.

## 16. Kiểm thử late binding từ JobParameters

Test nên chứng minh cùng một Job có thể nhận các tham số khác nhau ở các lần chạy khác nhau và bean StepScope nhận đúng giá trị tương ứng.

Với Spring Batch Test:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchTestConfiguration.class)
class LateBindingJobParametersTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void readsInputFileFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("input.file", "/test-data/customers.csv", true)
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

Test trên cần có file fixture tại đường dẫn tương ứng và output/assertion phù hợp. Nên thêm test chạy với file khác để chứng minh reader không giữ giá trị cũ giữa các JobExecution.

Các tình huống nên kiểm tra:

- Tham số bắt buộc có mặt và bean nhận đúng giá trị.
- Tham số bắt buộc bị thiếu hoặc blank: Job/Step thất bại với thông báo rõ.
- Tham số tùy chọn không có: default được áp dụng đúng.
- Tham số sai kiểu hoặc sai format: validation thất bại sớm.
- Hai JobExecution dùng hai giá trị khác nhau: mỗi StepScope bean dùng đúng giá trị của execution.
- Restart cùng JobInstance: identifying parameters và resource đầu vào giữ ổn định.
- Partition: mỗi worker nhận đúng JobParameters chung và StepExecutionContext riêng.

Không nên lấy bean StepScope và gọi method phụ thuộc context trực tiếp trong unit test khi chưa mở StepScope. Hãy chạy Step/Job bằng Spring Batch Test hoặc dùng scope test utility phù hợp với phiên bản framework.

## 17. Các lỗi thường gặp

**Quên `@StepScope`:** SpEL cần JobParameters khi bean được tạo, nhưng singleton thường được khởi tạo trước khi Job chạy. Đặt `@StepScope` cho bean cần giá trị theo StepExecution.

**Dùng sai key:** tên trong `jobParameters['...']` phải khớp chính xác với key được thêm vào `JobParametersBuilder`.

**Nhầm JobParameters với ExecutionContext:** JobParameters là đầu vào launch; ExecutionContext lưu trạng thái phát sinh trong quá trình thực thi.

**Cho rằng chỉ identifying parameters mới được inject:** identifying flag ảnh hưởng JobInstance identity, không quyết định khả năng late binding.

**Đánh dấu input là non-identifying:** nếu file hoặc ngày nghiệp vụ thay đổi nhưng không tham gia identity, lần launch có thể bị xem là cùng JobInstance. Hãy chọn identifying flag theo ý nghĩa nghiệp vụ.

**Không kiểm tra null hoặc default:** tham số thiếu có thể làm bean khởi tạo lỗi khó hiểu hoặc truyền null xuống reader/service.

**Inject giá trị động vào singleton field:** nhiều JobExecution có thể dùng chung bean và gây giữ nhầm giá trị. Dùng scope phù hợp hoặc truyền tham số qua method.

**Dùng `@JobScope` thay cho `@StepScope` mọi nơi:** bean gắn với reader/processor/writer của một Step thường nên là StepScope để nhận đúng StepExecution context.

**Giả định scope tự truyền sang thread bất kỳ:** thread do ứng dụng tạo có thể không có StepContext. Dùng concurrency mechanism phù hợp và kiểm thử.

**Thay identifying JobParameters khi restart:** việc này tạo JobInstance mới thay vì tiếp tục instance cũ.

**Dùng JobParameters để lưu tiến độ:** JobParameters không phải nơi cập nhật checkpoint. Dùng StepExecutionContext, JobExecutionContext hoặc kho dữ liệu nghiệp vụ.

## Kết luận

Late binding cho phép bean nhận JobParameters tại thời điểm Job hoặc Step thực sự chạy, thay vì lúc application context khởi động. Trong Spring Batch, `@StepScope` là lựa chọn phổ biến cho reader, processor, writer và Tasklet cần tham số theo StepExecution; `@JobScope` phù hợp với dependency ở phạm vi JobExecution. Dùng SpEL như `#{jobParameters['input.file']}` để lấy giá trị, kiểm tra tham số bắt buộc và kiểu dữ liệu, đồng thời chọn identifying flag theo đơn vị công việc nghiệp vụ. Hãy giữ JobParameters ổn định khi restart, dùng ExecutionContext cho checkpoint và kiểm thử nhiều JobExecution để bảo đảm scoped bean luôn nhận đúng đầu vào của lần chạy hiện tại.
