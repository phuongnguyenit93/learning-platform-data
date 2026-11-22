# Late binding từ ExecutionContext trong Spring Batch

Trong Spring Batch, nhiều giá trị chỉ được biết khi Job hoặc Step bắt đầu chạy. Ví dụ, đường dẫn file đến từ JobParameters, khoảng ID do Partitioner giao cho worker, hoặc tên file trung gian do Step trước tạo ra. Nếu một bean đọc các giá trị này ngay lúc Spring khởi tạo application context, dữ liệu runtime chưa tồn tại và việc inject có thể thất bại.

**Late binding** trì hoãn việc tạo bean thực tế đến khi scope tương ứng hoạt động. Spring Batch cung cấp StepScope và JobScope, kết hợp với SpEL để lấy dữ liệu từ JobParameters, JobExecutionContext và StepExecutionContext. Nhờ vậy, reader, processor, writer hoặc Step có thể nhận đúng dữ liệu ở thời điểm chạy.

Bài học này giải thích cách late-bind giá trị từ ExecutionContext, phân biệt context của Job và Step, đăng ký bean có scope phù hợp, truyền dữ liệu giữa các Step, cấp context riêng cho partition và bảo đảm trạng thái có thể lưu cũng như khôi phục khi restart.

## 1. Late binding là gì?

Late binding là cách bind giá trị vào bean ở thời điểm bean thực sự được sử dụng trong Job hoặc Step, thay vì bind ngay lúc application context khởi tạo.

Ví dụ, một Job nhận tham số:

~~~text
input.file = /data/in/customer-20261115.csv
~~~

Reader cần đường dẫn này để mở file. Nếu reader là singleton thông thường, Spring có thể tạo reader khi ứng dụng khởi động, lúc chưa có JobExecution và JobParameters. Biểu thức SpEL đọc JobParameters khi đó chưa có execution context phù hợp.

Khi khai báo reader với @StepScope, Spring tạo scoped proxy lúc khởi động và chỉ tạo target reader khi StepExecution bắt đầu. Lúc đó, JobParameters và StepExecutionContext đã sẵn sàng.

~~~mermaid
flowchart TD
    A["Ứng dụng khởi động"] --> B["Spring tạo scoped proxy"]
    B --> C["Job được launch"]
    C --> D["JobExecution và StepExecution được tạo"]
    D --> E["StepScope hoạt động"]
    E --> F["Tạo target bean"]
    F --> G["Đánh giá SpEL từ ExecutionContext"]
    G --> H["Reader hoặc Writer dùng giá trị runtime"]
~~~

Late binding hữu ích khi cùng một cấu hình Step cần xử lý nhiều file, nhiều ngày nghiệp vụ hoặc nhiều partition với dữ liệu đầu vào khác nhau.

## 2. ExecutionContext lưu dữ liệu ở đâu?

Spring Batch có các phạm vi lưu trữ khác nhau. Cần chọn đúng nơi lưu để các Step và worker nhìn thấy đúng giá trị.

| Nơi lưu | Phạm vi | Ai thường đọc? | Ví dụ |
|---|---|---|---|
| JobParameters | Đầu vào của JobInstance hoặc JobExecution theo identifying flag | Job và mọi Step | businessDate, input.file, batchId |
| JobExecutionContext | Dùng chung giữa các Step trong một JobExecution | Các Step sau và JobScope | file trung gian, watermark |
| StepExecutionContext | Riêng cho một StepExecution | StepScope của Step đó | checkpoint, minId, maxId, partition key |

ExecutionContext là vùng key-value mà Spring Batch quản lý và lưu trong JobRepository. Giá trị có thể được khôi phục khi restart nếu được cập nhật và lưu đúng thời điểm.

### JobParameters không phải ExecutionContext

JobParameters là dữ liệu đầu vào do caller cung cấp khi launch Job. Nó phù hợp với giá trị xác định một lần xử lý, ví dụ ngày nghiệp vụ hoặc batch ID.

ExecutionContext lưu trạng thái phát sinh trong lúc thực thi. Ví dụ, Step đầu tạo file đã chuẩn hóa rồi lưu đường dẫn để Step sau đọc.

### JobExecutionContext và StepExecutionContext khác nhau

- JobExecutionContext thuộc một JobExecution và có thể chia sẻ dữ liệu giữa các Step trong lần chạy đó.
- StepExecutionContext thuộc một StepExecution, vì vậy mỗi Step và mỗi worker partition có context riêng.
- Khi Job restart, một JobExecution mới được tạo cho cùng JobInstance; trạng thái context được khôi phục theo cơ chế restart của Spring Batch.

Không đưa dữ liệu riêng của từng partition vào một JobExecutionContext chung. Mỗi worker cần context riêng để không ghi đè giá trị của worker khác.

## 3. SpEL truy cập dữ liệu runtime

Spring Batch hỗ trợ SpEL để đọc giá trị từ scope hiện hành.

| Biểu thức | Giá trị |
|---|---|
| `#{jobParameters['input.file']}` | JobParameter có tên input.file |
| `#{jobParameters['businessDate']}` | JobParameter ngày nghiệp vụ |
| `#{jobExecutionContext['validatedFile']}` | Key trong JobExecutionContext |
| `#{stepExecutionContext['minId']}` | Key trong StepExecutionContext |
| `#{stepExecution.stepName}` | Tên Step hiện tại |
| `#{stepExecution.id}` | ID của StepExecution |
| `#{jobExecution.id}` | ID của JobExecution |

Ví dụ inject key từ StepExecutionContext:

~~~java
@Value("#{stepExecutionContext['minId']}")
Long minId
~~~

Ví dụ inject key từ JobExecutionContext:

~~~java
@Value("#{jobExecutionContext['validatedFile']}")
String validatedFile
~~~

Các biểu thức này cần được đánh giá khi bean được tạo trong scope có execution context tương ứng. Vì vậy, late binding phải đi cùng @StepScope hoặc @JobScope thích hợp.

### Key phải tồn tại và đúng kiểu

Nếu worker mong đợi key minId nhưng Partitioner không ghi key đó, bean có thể nhận null hoặc lỗi chuyển đổi tùy kiểu tham số và cấu hình. Với dữ liệu bắt buộc, hãy kiểm tra giá trị trước khi tạo reader hoặc thực hiện truy vấn.

Ưu tiên dùng kiểu wrapper như Long khi cần phát hiện null. Sau đó kiểm tra điều kiện hợp lệ và ném lỗi cấu hình rõ ràng nếu thiếu key.

## 4. Vì sao cần @StepScope?

@StepScope tạo bean có vòng đời gắn với StepExecution hiện tại. Bean được tạo khi Step scope hoạt động và các giá trị từ StepExecutionContext, JobExecutionContext hoặc JobParameters đã có thể truy cập.

Ví dụ reader nhận đường dẫn file từ JobParameters:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException(
            "Thiếu JobParameter input.file"
        );
    }

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(StandardCharsets.UTF_8.name())
        .delimited()
        .names("customerId", "fullName", "email")
        .fieldSetMapper(fields -> new CustomerInput(
            fields.readString("customerId"),
            fields.readString("fullName"),
            fields.readString("email")
        ))
        .saveState(true)
        .build();
}
~~~

Khi Job được launch với input.file, reader target được tạo trong Step scope và nhận đường dẫn runtime. Một Job khác có thể truyền đường dẫn khác và nhận target reader riêng cho StepExecution của nó.

### @StepScope là meta-annotation

@StepScope là annotation tiện ích khai báo scope step với proxy mode phù hợp. Không cần thêm một @Scope("step") khác cho cùng bean.

Dùng trực tiếp trên phương thức @Bean là cách rõ ràng trong Java configuration:

~~~java
@Bean
@StepScope
ItemReader<CustomerInput> customerReader(...) {
    // Tạo reader dựa trên dữ liệu runtime.
}
~~~

## 5. Late binding từ StepExecutionContext

StepExecutionContext phù hợp với dữ liệu riêng của Step hoặc worker partition. Ví dụ, Partitioner chia bảng thành các khoảng ID và ghi minId, maxId vào context của từng partition.

Worker reader có thể lấy hai giá trị đó:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Customer> partitionCustomerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId,
        @Value("#{jobParameters['batchId']}") String batchId) {

    if (minId == null || maxId == null || minId > maxId) {
        throw new IllegalArgumentException(
            "Partition range không hợp lệ"
        );
    }

    return new JdbcCursorItemReaderBuilder<Customer>()
        .name("partitionCustomerReader")
        .dataSource(dataSource)
        .sql("""
            SELECT customer_id, full_name
            FROM customer_source
            WHERE batch_id = ?
              AND customer_id >= ?
              AND customer_id <= ?
            ORDER BY customer_id
            """)
        .preparedStatementSetter(ps -> {
            ps.setString(1, batchId);
            ps.setLong(2, minId);
            ps.setLong(3, maxId);
        })
        .rowMapper((rs, rowNum) -> new Customer(
            rs.getLong("customer_id"),
            rs.getString("full_name")
        ))
        .saveState(true)
        .build();
}
~~~

Trong ví dụ:

- minId và maxId đến từ StepExecutionContext riêng của worker.
- batchId đến từ JobParameters chung.
- @StepScope bảo đảm giá trị được đọc khi worker StepExecution đã tồn tại.
- Reader chỉ truy vấn dữ liệu trong batch và range được giao.

Cùng một worker Step definition có thể được sử dụng cho nhiều partition. Mỗi partition có StepExecution riêng, vì vậy scoped reader nhận range riêng.

## 6. Partitioner tạo dữ liệu cho late binding

Partitioner trả về map tên partition và ExecutionContext tương ứng:

~~~java
public class CustomerRangePartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions =
            new LinkedHashMap<>();

        long[][] ranges = {
            {1L, 250L},
            {251L, 500L},
            {501L, 750L},
            {751L, 1000L}
        };

        for (int i = 0; i < Math.min(gridSize, ranges.length); i++) {
            ExecutionContext context = new ExecutionContext();
            context.putLong("minId", ranges[i][0]);
            context.putLong("maxId", ranges[i][1]);
            context.putString("partitionName", "partition" + i);

            partitions.put("partition" + i, context);
        }

        return partitions;
    }
}
~~~

Mỗi context là một object mới. Không dùng chung một ExecutionContext cho nhiều partition vì giá trị của worker có thể bị ghi đè.

Cấu hình manager Step:

~~~java
@Bean
Step customerManagerStep(
        JobRepository jobRepository,
        Step customerWorkerStep,
        Partitioner customerPartitioner,
        TaskExecutor partitionTaskExecutor) {

    return new StepBuilder("customerManagerStep", jobRepository)
        .partitioner("customerWorkerStep", customerPartitioner)
        .step(customerWorkerStep)
        .gridSize(4)
        .taskExecutor(partitionTaskExecutor)
        .build();
}
~~~

Khi manager tạo worker StepExecution, Spring Batch gắn ExecutionContext của partition vào execution đó. Scoped reader sau đó đọc minId và maxId.

### Tên partition và key context là hai khái niệm khác nhau

Tên map key như partition0 giúp Spring Batch định danh partition. Key trong ExecutionContext như partitionName, minId hoặc maxId là dữ liệu worker cần.

Có thể lưu partitionName trong context nếu worker cần dùng, nhưng không bắt buộc nếu có thể lấy tên từ StepExecution theo cách phù hợp.

## 7. @JobScope và late binding từ JobExecutionContext

@JobScope tạo bean có vòng đời gắn với JobExecution. Nó hữu ích khi một bean cần truy cập JobParameters hoặc JobExecutionContext và được dùng trong phạm vi Job.

Ví dụ một Step được tạo theo tham số ngày nghiệp vụ:

~~~java
@Bean
@JobScope
Step archiveStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        Tasklet archiveTasklet) {

    return new StepBuilder("archiveStep", jobRepository)
        .tasklet(archiveTasklet, transactionManager)
        .build();
}
~~~

Giá trị businessDate được bind khi JobExecution hoạt động. Cách này hữu ích khi cấu hình Step phụ thuộc JobParameters.

Tuy nhiên, không phải bean nào cũng cần JobScope. Nếu chỉ reader hoặc writer cần dữ liệu runtime ở cấp Step, @StepScope thường phù hợp hơn.

### Đọc dữ liệu từ JobExecutionContext

Ví dụ một bean job-scoped nhận đường dẫn do Step trước lưu trong JobExecutionContext:

~~~java
@Bean
@JobScope
ArchivePlan archivePlan(
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {

    if (validatedFile == null || validatedFile.isBlank()) {
        throw new IllegalStateException(
            "Không tìm thấy validatedFile trong JobExecutionContext"
        );
    }

    return new ArchivePlan(validatedFile);
}
~~~

Một Step-scoped bean cũng có thể đọc JobExecutionContext:

~~~java
@Bean
@StepScope
ItemReader<CustomerInput> validatedFileReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {
    // Tạo reader dùng file đã được Step trước xác nhận.
}
~~~

Chọn scope theo vòng đời bean cần có. Dữ liệu trong JobExecutionContext có phạm vi JobExecution, nhưng bean đọc dữ liệu đó vẫn có thể là StepScope nếu chỉ dùng trong một Step.

## 8. Truyền dữ liệu từ Step trước sang Step sau

Một tình huống thường gặp:

1. Step validate kiểm tra file đầu vào.
2. Step validate tạo file đã chuẩn hóa.
3. Step validate lưu đường dẫn vào StepExecutionContext.
4. Sau khi Step hoàn tất, key được promote lên JobExecutionContext.
5. Step import dùng late binding để lấy đường dẫn đó.

Có thể ghi dữ liệu vào StepExecutionContext trong Tasklet:

~~~java
@Bean
Step validateInputStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        InputValidationTasklet tasklet,
        ExecutionContextPromotionListener promotionListener) {

    return new StepBuilder("validateInputStep", jobRepository)
        .tasklet(tasklet, transactionManager)
        .listener(promotionListener)
        .build();
}
~~~

Trong Tasklet:

~~~java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) throws Exception {

    String validatedPath = validateAndPrepareInput();

    contribution.getStepExecution()
        .getExecutionContext()
        .putString("validatedFile", validatedPath);

    return RepeatStatus.FINISHED;
}
~~~

Đăng ký promotion listener:

~~~java
@Bean
ExecutionContextPromotionListener promotionListener() {
    ExecutionContextPromotionListener listener =
        new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {"validatedFile"});
    listener.setStatuses(new String[] {"COMPLETED"});

    return listener;
}
~~~

Sau khi validateInputStep hoàn tất với status phù hợp, listener promote key validatedFile từ StepExecutionContext lên JobExecutionContext.

Step import có thể dùng:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> importReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
        .name("importReader")
        .resource(new FileSystemResource(validatedFile))
        .delimited()
        .names("customerId", "fullName")
        .fieldSetMapper(fields -> new CustomerInput(
            fields.readString("customerId"),
            fields.readString("fullName")
        ))
        .saveState(true)
        .build();
}
~~~

Không nên giả định key được ghi vào StepExecutionContext tự động xuất hiện trong JobExecutionContext. Muốn Step sau đọc được key, cần promote hoặc ghi vào JobExecutionContext bằng cơ chế phù hợp.

### Chỉ promote dữ liệu thực sự cần chia sẻ

StepExecutionContext nên giữ trạng thái riêng của Step. Chỉ đưa key cần cho Step sau lên JobExecutionContext. Điều này tránh làm context chung phình to và tránh chia sẻ trạng thái nội bộ không cần thiết.

## 9. Late binding từ JobParameters

JobParameters là nguồn dữ liệu phổ biến cho late binding. Ví dụ caller launch Job với:

~~~java
JobParameters parameters = new JobParametersBuilder()
    .addString("input.file", "/data/in/customer.csv")
    .addString("businessDate", "2026-11-15")
    .addString("batchId", "BATCH-20261115")
    .toJobParameters();

jobLauncher.run(importJob, parameters);
~~~

Reader có thể nhận trực tiếp input.file:

~~~java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {
    // Tạo reader theo đường dẫn runtime.
}
~~~

Processor hoặc writer cũng có thể nhận businessDate hoặc batchId qua @StepScope.

JobParameters phù hợp với dữ liệu đầu vào ổn định của lần chạy. Nếu một Step tạo ra giá trị mới trong lúc chạy, hãy lưu giá trị đó vào ExecutionContext thay vì cố thay đổi JobParameters.

### Identifying và non-identifying parameters

Một JobParameter có cờ identifying quyết định JobInstance identity. Non-identifying parameter vẫn có thể được đọc qua SpEL nhưng không làm thay đổi identity.

Late binding không thay đổi quy tắc này. Ví dụ requestedBy là non-identifying vẫn có thể được inject, nhưng thay requestedBy không tạo JobInstance mới.

## 10. Kết hợp nhiều nguồn dữ liệu trong một bean

Một bean có thể cần dữ liệu từ nhiều scope. Ví dụ reader dùng batchId từ JobParameters, minId và maxId từ partition context:

~~~java
@Bean
@StepScope
ItemReader<Customer> customerReader(
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new CustomerRangeReader(batchId, minId, maxId);
}
~~~

Điều này hợp lý vì:

- batchId mô tả lô dữ liệu chung.
- minId và maxId mô tả phần dữ liệu riêng của worker.
- StepScope cung cấp cả JobParameters và StepExecutionContext trong lúc Step chạy.

Không sao chép batchId vào mọi partition context nếu JobParameters đã là nguồn chuẩn và worker có thể đọc trực tiếp. Tránh lưu cùng một giá trị ở nhiều nơi với nguy cơ không đồng nhất.

## 11. Default value và kiểm tra key bắt buộc

Một số key là tùy chọn. SpEL có thể dùng toán tử Elvis để cung cấp giá trị mặc định:

~~~java
@Value("#{jobParameters['output.mode'] ?: 'STANDARD'}")
String outputMode
~~~

Default chỉ nên dùng khi có ý nghĩa nghiệp vụ rõ ràng. Với input.file, minId hoặc batchId bắt buộc, không nên âm thầm dùng giá trị mặc định có thể làm worker đọc nhầm dữ liệu.

Có thể kiểm tra trong factory method:

~~~java
@Bean
@StepScope
CustomerRangeReader customerRangeReader(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    if (minId == null || maxId == null) {
        throw new IllegalStateException(
            "Partition context phải có minId và maxId"
        );
    }

    if (minId > maxId) {
        throw new IllegalArgumentException(
            "minId phải nhỏ hơn hoặc bằng maxId"
        );
    }

    return new CustomerRangeReader(minId, maxId);
}
~~~

Thông báo lỗi cụ thể giúp phân biệt lỗi thiếu context với lỗi truy vấn database hoặc lỗi dữ liệu.

### Dùng kiểu dữ liệu phù hợp

Nếu context lưu Long bằng putLong, inject vào Long. Nếu lưu chuỗi ngày, có thể inject String rồi parse rõ ràng bằng LocalDate.parse. Tránh ép kiểu ngầm phức tạp hoặc dùng primitive khi giá trị có thể thiếu.

## 12. Thời điểm tạo bean và scoped proxy

Khi application context khởi động, Spring tạo scoped proxy cho bean @StepScope hoặc @JobScope. Proxy đại diện cho bean thực tế nhưng chưa cần tạo target ngay.

Khi StepExecution hoặc JobExecution phù hợp hoạt động, proxy lấy target bean trong scope tương ứng. Các biểu thức @Value được đánh giá lúc target được tạo.

Điều này cho phép một bean definition được dùng trong nhiều lần chạy mà mỗi execution có dữ liệu runtime riêng.

~~~mermaid
sequenceDiagram
    participant App as ApplicationContext
    participant Proxy as Scoped Proxy
    participant Job as JobExecution
    participant Step as StepExecution
    participant Target as Target Bean

    App->>Proxy: Tạo proxy lúc startup
    Job->>Step: Bắt đầu Step
    Step->>Proxy: Gọi reader
    Proxy->>Target: Tạo target trong StepScope
    Target->>Target: Đọc SpEL từ ExecutionContext
    Target-->>Proxy: Trả target đã cấu hình
    Proxy-->>Step: Thực hiện thao tác
~~~

### Không gọi scope quá sớm

Nếu singleton bean gọi trực tiếp phương thức của scoped target trong lúc application context khởi động, chưa có StepExecution thì Spring không thể tìm context hiện tại.

Lỗi thường gặp có dạng:

~~~text
Scope 'step' is not active for the current thread
~~~

Nguyên nhân thường là bean scoped bị truy cập trước khi Step bắt đầu hoặc một thread không có execution context phù hợp.

Hãy để framework gọi scoped bean trong vòng đời Step. Tránh gọi method của reader hoặc writer trong constructor, @PostConstruct hay lúc cấu hình Job nếu method đó buộc target được tạo quá sớm.

## 13. Scope của reader, processor và writer

Late binding không chỉ dành cho reader. Bất kỳ thành phần nào cần dữ liệu runtime đều có thể dùng scope phù hợp.

### Reader

Reader có thể nhận input file hoặc range partition. Đây là trường hợp phổ biến nhất vì nguồn đọc thay đổi theo JobParameters hoặc partition.

### Processor

Processor có thể nhận businessDate, tenant hoặc mã cấu hình để áp dụng quy tắc biến đổi:

~~~java
@Bean
@StepScope
ItemProcessor<OrderInput, Order> orderProcessor(
        @Value("#{jobParameters['businessDate']}")
        String businessDate) {

    LocalDate effectiveDate = LocalDate.parse(businessDate);

    return input -> mapOrder(input, effectiveDate);
}
~~~

### Writer

Writer có thể nhận partition name hoặc output path riêng:

~~~java
@Bean
@StepScope
ItemWriter<Customer> customerWriter(
        @Value("#{stepExecutionContext['partitionName']}")
        String partitionName,
        CustomerRepository repository) {

    return chunk -> {
        for (Customer customer : chunk.getItems()) {
            repository.saveProcessed(customer, partitionName);
        }
    };
}
~~~

Chỉ scope những bean thực sự cần dữ liệu runtime. Một service stateless không phụ thuộc execution context thường nên là singleton để tái sử dụng và dễ kiểm thử.

## 14. @StepScope trong partitioning

Partitioning là tình huống late binding từ StepExecutionContext phát huy tác dụng rõ rệt.

Mỗi partition có một ExecutionContext riêng:

~~~text
partition0:
  minId = 1
  maxId = 250

partition1:
  minId = 251
  maxId = 500

partition2:
  minId = 501
  maxId = 750
~~~

Worker Step definition giống nhau nhưng mỗi worker StepExecution có context khác nhau. Một bean @StepScope được tạo trong scope của từng StepExecution, nên reader nhận range phù hợp.

Các yêu cầu:

- Partitioner tạo context mới cho mỗi partition.
- Key trong context thống nhất với biểu thức SpEL.
- Tên partition ổn định nếu cần restart.
- Worker dùng @StepScope cho bean late-bind partition values.
- Query sử dụng đúng range và điều kiện batch chung.
- Partition plan xác định và không chồng lấn.

### JobScope trong partitioning cần thận trọng

JobScope có phạm vi JobExecution, tức một target bean có thể được chia sẻ trong phạm vi Job. Trong partitioning hoặc xử lý đa luồng, Spring Batch không luôn kiểm soát các thread do cơ chế thực thi tạo ra để gắn job scope context đúng cách.

Vì vậy, không nên dựa vào JobScope trong worker partition hoặc Step đa luồng nếu chưa xác nhận cách thực thi và scope context của phiên bản đang dùng. Với dữ liệu riêng của partition, dùng StepExecutionContext và @StepScope. Với dữ liệu chung, có thể dùng JobParameters hoặc truyền an toàn qua context/bean stateless.

## 15. StepScope và multi-threaded Step

Cần phân biệt partitioning với một Step đa luồng.

Trong partitioning, mỗi worker có StepExecution riêng. Vì vậy, StepScope của từng worker có thể nhận context riêng.

Trong multi-threaded Step, nhiều thread có thể cùng xử lý trong một StepExecution. Step-scoped bean gắn với StepExecution đó, không tự động tạo target khác cho từng item hoặc từng thread. Nếu bean chứa state mutable, các thread có thể truy cập đồng thời.

Các nguyên tắc:

- Không lưu item hiện tại trong field của step-scoped processor dùng chung giữa thread.
- Reader và writer phải hỗ trợ concurrency theo cấu hình.
- Không giả định StepScope tương đương thread scope.
- Dùng object stateless hoặc state thread-safe.
- Kiểm thử hành vi đồng thời với đúng TaskExecutor.

Late binding giải quyết vòng đời và dữ liệu cấu hình của bean. Nó không tự làm cho bean thread-safe.

## 16. ExecutionContext được lưu và khôi phục khi restart

ExecutionContext là một phần của metadata restart. Reader hoặc writer hỗ trợ ItemStream có thể lưu checkpoint trong StepExecutionContext.

Vòng đời ItemStream gồm:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

- open(...) khôi phục trạng thái đã lưu hoặc khởi tạo trạng thái mới.
- update(...) ghi trạng thái hiện tại vào ExecutionContext tại checkpoint.
- close() đóng tài nguyên khi Step kết thúc.

Reader chuẩn như FlatFileItemReader có thể lưu vị trí đọc khi saveState được bật. Khi restart, Spring Batch khôi phục context và reader tiếp tục theo checkpoint.

### Late binding không tự lưu checkpoint

@StepScope chỉ giúp bean nhận giá trị runtime. Nó không tự làm reader restartable hoặc tự lưu vị trí đọc.

Cần:

- Reader triển khai ItemStream hoặc được bọc bởi thành phần quản lý state.
- Có tên reader ổn định.
- Bật saveState khi cần restart.
- Dùng ExecutionContext để lưu trạng thái phù hợp.
- Không ghi đè key checkpoint nội bộ của reader.
- Giữ nguồn dữ liệu và partition plan ổn định giữa lần chạy và restart.

### Không nhầm dữ liệu cấu hình với checkpoint

minId và maxId là dữ liệu mô tả phạm vi partition. Current item count hoặc current row là checkpoint của reader. Cả hai có thể cùng nằm trong StepExecutionContext nhưng phục vụ mục đích khác nhau.

Không tự sửa key nội bộ của reader nếu không hiểu cách reader khôi phục trạng thái. Dùng key riêng có tiền tố rõ ràng cho dữ liệu ứng dụng.

## 17. ExecutionContext phải chứa dữ liệu có thể serialize

JobRepository lưu ExecutionContext xuống metadata store. Vì vậy, các giá trị phải tương thích với serializer và cấu hình lưu trữ.

Nên lưu:

- String, Long, Integer, Double, Boolean.
- Ngày giờ hoặc kiểu được serializer hỗ trợ.
- ID, đường dẫn, range và mã phân vùng.
- Cấu trúc nhỏ có thể serialize ổn định.

Không nên lưu:

- JDBC Connection hoặc ResultSet.
- InputStream, Reader hoặc file handle đang mở.
- Thread, Executor hoặc Spring bean.
- Entity graph lớn hoặc object có tham chiếu vòng.
- Đối tượng phụ thuộc resource runtime không thể khôi phục.

Thay vì lưu FileInputStream, lưu đường dẫn file và mở stream trong reader khi Step bắt đầu. Thay vì lưu repository, lưu batch ID để bean scoped nhận repository qua dependency injection và truy vấn khi cần.

## 18. Đặt tên key trong ExecutionContext

Key trong context là hợp đồng giữa nơi ghi và nơi đọc. Đặt tên rõ nghĩa, ổn định và tránh trùng với key nội bộ của framework.

Ví dụ:

~~~java
context.putString("input.validatedFile", path);
context.putString("batch.sourceId", batchId);
context.putLong("partition.minId", minId);
context.putLong("partition.maxId", maxId);
context.putString("partition.name", partitionName);
~~~

SpEL tương ứng:

~~~java
@Value("#{jobExecutionContext['input.validatedFile']}")
String validatedFile
~~~

~~~java
@Value("#{stepExecutionContext['partition.minId']}")
Long minId
~~~

Dùng namespace hoặc tiền tố giúp phân biệt key của ứng dụng với key checkpoint do reader/writer tạo.

### Tránh thay đổi ý nghĩa key

Nếu JobInstance cũ có thể restart, không thay đổi ý nghĩa key context giữa các phiên bản ứng dụng mà không có kế hoạch tương thích. Ví dụ, nếu minId trước đây là inclusive nhưng phiên bản mới hiểu là exclusive, restart có thể bỏ sót hoặc đọc trùng dữ liệu.

Khi cần thay đổi schema context, cân nhắc version hóa:

~~~java
context.putString("partition.context.version", "v2");
~~~

Worker kiểm tra version trước khi sử dụng và từ chối context không tương thích thay vì suy đoán.

## 19. Late binding và validation JobParameters

Late binding không thay thế validation đầu vào. JobParameters nên được kiểm tra trước khi Step bắt đầu.

Ví dụ validator:

~~~java
@Bean
JobParametersValidator importParametersValidator() {
    return parameters -> {
        String inputFile = parameters.getString("input.file");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                "JobParameter input.file là bắt buộc"
            );
        }
    };
}
~~~

Gắn validator vào Job:

~~~java
return new JobBuilder("importJob", jobRepository)
    .start(importStep)
    .validator(importParametersValidator)
    .build();
~~~

Validator kiểm tra hợp đồng đầu vào của Job. Bean @StepScope vẫn nên kiểm tra key riêng của StepExecutionContext vì chúng có thể được tạo trong quá trình chạy.

Phân chia trách nhiệm:

- JobParametersValidator kiểm tra tham số caller cung cấp.
- Partitioner kiểm tra và tạo phạm vi partition.
- Step-scoped bean kiểm tra giá trị cần thiết khi được tạo.
- Reader/writer kiểm tra resource và trạng thái khi thực thi.

## 20. Lỗi thường gặp khi late binding

### Quên @StepScope

Một reader singleton cố đọc stepExecutionContext trước khi Step chạy có thể không tìm thấy scope hoặc nhận giá trị không đúng. Dùng @StepScope cho bean cần dữ liệu runtime cấp Step.

### Dùng JobScope cho dữ liệu riêng của partition

JobExecutionContext là phạm vi chung của JobExecution. Không đặt minId/maxId riêng của từng partition ở đó. Dùng StepExecutionContext và StepScope.

### Ghi vào StepExecutionContext nhưng đọc từ JobExecutionContext

Hai context khác nhau. Muốn Step sau đọc được key, cần promote hoặc ghi vào JobExecutionContext.

### Ghi sai key

Nếu Partitioner ghi minID nhưng SpEL đọc minId, worker sẽ không nhận được giá trị mong muốn. Dùng hằng số hoặc quy ước key thống nhất.

### Inject vào singleton service

Một singleton bean không có execution scope phù hợp có thể được tạo trước JobExecution. Nếu service cần dữ liệu runtime, truyền giá trị từ scoped bean vào method hoặc dùng scope phù hợp cho bean đó.

### Gọi scoped bean quá sớm

Gọi target trong constructor, @PostConstruct hoặc khi application context khởi tạo có thể gây lỗi scope chưa active. Chỉ truy cập bean trong vòng đời Job/Step.

### Dùng primitive cho key có thể thiếu

Nếu Long minId không có giá trị, dùng kiểu primitive long có thể gây lỗi chuyển đổi. Dùng wrapper và kiểm tra null trước khi sử dụng.

### Lưu object không serialize được

ExecutionContext được lưu trong JobRepository. Connection, stream hoặc bean không phù hợp để lưu. Chỉ lưu dữ liệu nhỏ và có thể khôi phục.

### Dùng một ExecutionContext cho nhiều partition

Các worker có thể chia sẻ cùng object và ghi đè giá trị. Tạo một context mới cho mỗi partition.

### Nhầm StepScope với thread scope

Một StepExecution có thể được xử lý bởi nhiều thread. Scoped bean không tự tạo instance cho mỗi thread. Bảo đảm state thread-safe.

### Cho rằng @StepScope tự bật restart

Scope không thay thế ItemStream, checkpoint hoặc saveState. Reader phải hỗ trợ lưu và khôi phục trạng thái.

## 21. Kiểm thử late binding

Nên kiểm thử cả việc inject giá trị và vòng đời thực tế của scoped bean.

### Kiểm thử reader nhận JobParameters

1. Tạo JobParameters chứa input.file.
2. Chạy Step trong test context Spring Batch.
3. Xác nhận reader mở đúng resource.
4. Xác nhận dữ liệu đọc được tương ứng file được truyền.
5. Chạy JobExecution khác với file khác và xác nhận reader nhận giá trị mới.

Không chỉ tạo application context rồi gọi reader trực tiếp nếu StepScope chưa được kích hoạt.

### Kiểm thử reader nhận StepExecutionContext

1. Tạo StepExecutionContext với minId và maxId.
2. Chạy worker Step.
3. Xác nhận reader nhận đúng hai giá trị.
4. Xác nhận query chỉ đọc range của worker.
5. Tạo worker thứ hai với range khác và xác nhận không dùng nhầm context.

### Kiểm thử truyền dữ liệu giữa Step

1. Step đầu ghi validatedFile vào StepExecutionContext.
2. ExecutionContextPromotionListener promote key khi Step thành công.
3. Step sau đọc key từ jobExecutionContext.
4. Xác nhận reader mở đúng file đã chuẩn hóa.
5. Kiểm tra trường hợp Step đầu thất bại thì key không được promote theo cấu hình status.

### Kiểm thử restart

1. Chạy một phần dữ liệu rồi làm Step thất bại.
2. Xác nhận ExecutionContext được lưu tại checkpoint.
3. Restart cùng JobInstance.
4. Xác nhận scoped bean được tạo với context đã khôi phục.
5. Xác nhận reader tiếp tục từ vị trí đúng và không bỏ sót hoặc đọc trùng.

### Kiểm thử partition

Tạo nhiều partition với context khác nhau và xác nhận mỗi worker có StepExecutionContext riêng. Không chỉ kiểm tra map do Partitioner trả về; cần kiểm tra bean @StepScope thực sự nhận đúng giá trị khi worker chạy.

Có thể dùng JobLauncherTestUtils, JobRepositoryTestUtils và các tiện ích test scope của Spring Batch phù hợp với phiên bản thư viện. Điểm cần xác nhận là bean được tạo trong scope thật và nhận đúng execution context, không phải chỉ kiểm tra biểu thức SpEL như một chuỗi.

## 22. Quy trình triển khai late binding từ ExecutionContext

Khi một bean cần dữ liệu runtime, có thể làm theo trình tự:

1. **Xác định nguồn:** JobParameters, JobExecutionContext hay StepExecutionContext.
2. **Chọn scope:** dùng @StepScope cho dữ liệu của Step/partition; dùng @JobScope cho dữ liệu cấp Job khi phù hợp.
3. **Định nghĩa key:** đặt tên rõ ràng và thống nhất giữa nơi ghi và nơi đọc.
4. **Tạo dữ liệu:** Partitioner, Tasklet hoặc listener ghi giá trị vào đúng context.
5. **Chia sẻ nếu cần:** promote key từ StepExecutionContext lên JobExecutionContext khi Step sau cần dùng.
6. **Bind bằng SpEL:** dùng @Value với key tương ứng.
7. **Kiểm tra giá trị:** xác thực key bắt buộc, kiểu dữ liệu và phạm vi.
8. **Giữ context serialize được:** chỉ lưu dữ liệu nhỏ, có thể khôi phục.
9. **Thiết kế restart:** giữ key và ý nghĩa context ổn định; reader lưu checkpoint phù hợp.
10. **Kiểm thử scope:** chạy Step/Job thật trong test context, bao gồm nhiều execution và partition.

## 23. Những điểm cần nhớ

- Late binding trì hoãn việc bind dữ liệu đến khi JobExecution hoặc StepExecution đã hoạt động.
- @StepScope tạo bean theo StepExecution và phù hợp với reader, processor, writer cần dữ liệu riêng của Step hoặc partition.
- @JobScope tạo bean theo JobExecution và phù hợp với dữ liệu dùng chung trong phạm vi Job khi cơ chế thực thi hỗ trợ scope đó.
- Dùng `#{stepExecutionContext['key']}` để đọc key của StepExecutionContext.
- Dùng `#{jobExecutionContext['key']}` để đọc key của JobExecutionContext.
- Dùng `#{jobParameters['key']}` để đọc JobParameters.
- StepExecutionContext riêng cho từng StepExecution; worker partition không nên dùng chung context.
- Muốn Step sau đọc key do Step trước tạo, hãy promote key hoặc ghi vào JobExecutionContext.
- @StepScope không tự làm bean thread-safe và không tự bật restart.
- ExecutionContext phải chứa dữ liệu có thể serialize; không lưu connection, stream hoặc Spring bean.
- Reader cần ItemStream/checkpoint/saveState phù hợp để khôi phục khi restart.
- Kiểm tra key bắt buộc và kiểu dữ liệu trước khi sử dụng.
- Kiểm thử bean trong scope thật, bao gồm JobParameters, partition context, promotion và restart.

Late binding từ ExecutionContext cho phép một cấu hình Step dùng được với nhiều lần chạy và nhiều partition mà vẫn nhận đúng dữ liệu runtime. Khi chọn đúng scope, lưu key ở đúng cấp và giữ ExecutionContext có thể khôi phục, Spring Batch có thể truyền trạng thái giữa các giai đoạn một cách rõ ràng và đáng tin cậy.

