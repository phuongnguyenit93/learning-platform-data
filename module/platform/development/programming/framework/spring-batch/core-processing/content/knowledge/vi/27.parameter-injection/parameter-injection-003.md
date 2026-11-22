# `@Value` từ `stepExecutionContext`

Trong Spring Batch, `StepExecutionContext` là vùng key-value gắn với một lần thực thi Step. Nó thường lưu dữ liệu riêng của Step như phạm vi partition, khóa cuối cùng đã đọc, vị trí file hoặc checkpoint cần khôi phục khi restart. Một bean cần những giá trị này có thể nhận chúng bằng Spring Expression Language (SpEL) thông qua `@Value`.

Biểu thức thường dùng là `@Value("#{stepExecutionContext['key']}")`. Bean cần được khai báo với `@StepScope` để Spring trì hoãn việc tạo target cho đến khi StepExecution hiện tại hoạt động. Khi đó, Spring Batch có thể phân giải `stepExecutionContext` và inject giá trị thuộc đúng StepExecution.

## 1. StepExecutionContext là gì?

Mỗi `StepExecution` có một `ExecutionContext` riêng. Context này là nơi lưu các giá trị cần tồn tại trong phạm vi Step, bao gồm trạng thái của reader, dữ liệu do partitioner cung cấp hoặc thông tin trung gian mà Step cần sử dụng.

Ví dụ một Step có thể lưu:

- `minId`, `maxId`: phạm vi ID được giao cho partition hiện tại.
- `inputFile`: file mà Step đang xử lý.
- `lastProcessedId`: khóa cuối cùng đã xử lý.
- `sourceVersion`: version của snapshot đầu vào.
- `validatedRecordCount`: số bản ghi đã được xác thực.

Có thể truy cập context qua `StepExecution`:

```java
StepExecution stepExecution = contribution.getStepExecution();
ExecutionContext context = stepExecution.getExecutionContext();

context.putLong("minId", 1L);
context.putLong("maxId", 100_000L);
```

Các key và value được lưu theo từng StepExecution. Hai StepExecution khác nhau có thể dùng cùng tên key nhưng giữ giá trị khác nhau. Vì vậy, `stepExecutionContext` phù hợp với dữ liệu riêng của Step hiện tại, không phải vùng chia sẻ chung giữa tất cả Step trong Job.

## 2. Đọc context bằng `@Value`

Spring Batch đưa các map execution context vào SpEL khi scope phù hợp đang hoạt động. Để lấy một key từ StepExecutionContext, dùng tên biến `stepExecutionContext` và cú pháp truy cập map:

```java
@Value("#{stepExecutionContext['minId']}") Long minId
```

Ví dụ đầy đủ với bean reader:

```java
@Bean
@StepScope
JdbcPagingItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return createCustomerReader(dataSource, minId, maxId);
}
```

`minId` và `maxId` được lấy từ context của StepExecution đang chạy. Nếu cùng một worker Step được dùng cho nhiều partition, mỗi worker StepExecution có context riêng nên mỗi instance reader nhận đúng phạm vi được giao.

Với key có dấu chấm, dấu gạch ngang hoặc ký tự không phù hợp với cú pháp thuộc tính, nên dùng dấu ngoặc vuông:

```java
@Value("#{stepExecutionContext['input.file']}") String inputFile
@Value("#{stepExecutionContext['source-version']}") String sourceVersion
```

Tên key trong SpEL phải khớp chính xác với key được ghi vào `ExecutionContext`.

## 3. Vì sao cần `@StepScope`?

Các bean singleton thông thường thường được tạo khi Spring khởi động application context. Nhưng `StepExecutionContext` chỉ có ý nghĩa khi một StepExecution cụ thể bắt đầu. Nếu một singleton cố lấy `stepExecutionContext` lúc khởi tạo, chưa có StepExecution hiện tại để phân giải giá trị.

`@StepScope` cho phép Spring tạo scoped proxy trước, rồi tạo target bean khi StepScope được kích hoạt cho StepExecution hiện tại. Lúc target được tạo, biểu thức SpEL mới được đánh giá với context tương ứng.

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> inputReader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("inputReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
```

Bean Step có thể nhận reader dưới dạng dependency thông thường:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> inputReader,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(inputReader)
            .writer(customerWriter)
            .build();
}
```

`inputReader` được inject ở đây là scoped proxy. Việc khai báo Step không buộc target reader phải được tạo ngay lúc application context khởi động. Khi Step chạy, proxy lấy target thuộc StepExecution hiện tại.

## 4. Phân biệt `stepExecutionContext` với `jobExecutionContext`

Spring Batch cung cấp nhiều biến SpEL có tên gần nhau. Cần chọn đúng context theo nơi lưu dữ liệu:

| SpEL variable | Nguồn dữ liệu | Phạm vi |
|---|---|---|
| `stepExecutionContext` | `StepExecution.getExecutionContext()` | Một StepExecution |
| `jobExecutionContext` | `JobExecution.getExecutionContext()` | Một JobExecution, có thể dùng giữa các Step |
| `jobParameters` | Tham số khi launch Job | Đầu vào của JobExecution |

Ví dụ bean nhận cả ba loại:

```java
@Bean
@StepScope
Tasklet exportTasklet(
        @Value("#{jobParameters['batchId']}") String batchId,
        @Value("#{jobExecutionContext['sourceVersion']}") String sourceVersion,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId,
        ExportService exportService) {

    return (contribution, chunkContext) -> {
        exportService.export(batchId, sourceVersion, minId, maxId);
        return RepeatStatus.FINISHED;
    };
}
```

Trong ví dụ:

- `batchId` là đầu vào do caller cung cấp khi launch Job.
- `sourceVersion` là metadata được lưu trong JobExecutionContext.
- `minId` và `maxId` là phạm vi riêng của StepExecution hiện tại.

Nếu dữ liệu được tạo ở một Step trước và cần dùng ở Step sau, thông thường nên promote key từ StepExecutionContext lên JobExecutionContext hoặc ghi vào kho dữ liệu nghiệp vụ. Step sau không thể đọc trực tiếp StepExecutionContext của Step trước bằng `stepExecutionContext`.

## 5. Nạp giá trị vào context bằng Partitioner

Một trường hợp sử dụng điển hình của `@Value` từ `stepExecutionContext` là partitioning. `Partitioner` trả về một map gồm partition name và `ExecutionContext` cho từng partition. Spring Batch dùng context đó để khởi tạo StepExecution của worker.

Ví dụ chia bảng khách hàng thành các khoảng ID:

```java
@Component
public class CustomerPartitioner implements Partitioner {

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

        ExecutionContext first = new ExecutionContext();
        first.putLong("minId", 1L);
        first.putLong("maxId", 50_000L);
        partitions.put("partition0", first);

        ExecutionContext second = new ExecutionContext();
        second.putLong("minId", 50_001L);
        second.putLong("maxId", 100_000L);
        partitions.put("partition1", second);

        return partitions;
    }
}
```

Worker reader lấy phạm vi từ StepExecutionContext:

```java
@Bean
@StepScope
JdbcPagingItemReader<Customer> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<Customer>()
            .name("partitionReader")
            .dataSource(dataSource)
            .queryProvider(customerQueryProvider(dataSource))
            .parameterValues(Map.of(
                    "minId", minId,
                    "maxId", maxId))
            .pageSize(500)
            .rowMapper(customerRowMapper())
            .saveState(true)
            .build();
}
```

Query provider cần dùng hai tham số để lọc phạm vi, ví dụ:

```sql
SELECT id, full_name, email
FROM customer
WHERE id BETWEEN :minId AND :maxId
ORDER BY id ASC
```

Mỗi worker có StepExecutionContext riêng. `partition0` nhận `minId=1`, `maxId=50000`; `partition1` nhận `minId=50001`, `maxId=100000`. Cùng một định nghĩa worker Step có thể được dùng cho tất cả partition mà không cần tạo reader singleton với phạm vi cố định.

Trong thực tế, cần bảo đảm các khoảng dữ liệu không chồng lấn và bao phủ đúng tập bản ghi. Sort key của paging reader phải ổn định, tốt nhất có khóa duy nhất, để tránh bỏ sót hoặc đọc trùng khi phân trang.

## 6. Nạp context trước khi bean StepScope được tạo

Giá trị được inject qua `@Value` được phân giải khi target bean scoped được tạo. Vì vậy, key phải có sẵn trong StepExecutionContext tại thời điểm bean được khởi tạo.

Đây là lý do partitioner phù hợp: nó tạo context cho từng partition trước khi worker Step bắt đầu. Khi worker tạo reader, các key `minId` và `maxId` đã tồn tại.

Ngược lại, nếu một listener `beforeStep()` mới ghi key vào StepExecutionContext nhưng một bean StepScope đã được khởi tạo trước đó, giá trị `@Value` trong bean không tự động cập nhật. `@Value` là giá trị được bind khi target bean được tạo, không phải một liên kết động được đánh giá lại mỗi lần đọc field.

Nếu cần giá trị phát sinh sau khi Step đã bắt đầu:

- Dùng `StepExecution` hoặc `ExecutionContext` trực tiếp tại thời điểm cần đọc.
- Đưa dữ liệu vào JobExecutionContext ở Step trước và dùng `jobExecutionContext` ở Step sau.
- Dùng `ExecutionContextPromotionListener` nếu cần promote key khi Step trước hoàn tất.
- Thiết kế một bean scoped chỉ được tạo sau khi key đã sẵn sàng.

Không nên dựa vào thứ tự khởi tạo ngẫu nhiên giữa listener và các scoped bean để truyền dữ liệu.

## 7. Late binding cho ItemReader

Reader thường là thành phần cần dữ liệu StepExecutionContext nhất, vì mỗi Step hoặc partition có thể đọc một file, một tenant hoặc một phạm vi dữ liệu khác nhau.

Ví dụ reader lấy tên file và số dòng bắt đầu từ context:

```java
@Bean
@StepScope
FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile,
        @Value("#{stepExecutionContext['startLine']}") Integer startLine) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("stepExecutionContext.inputFile is required");
    }

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(Math.max(0, startLine - 1))
            .delimited()
            .names("customerId", "fullName", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
```

Ví dụ này giả định `startLine` là số dòng bắt đầu tính từ 1 và header được tính trong quy tắc bỏ dòng của reader. Trong ứng dụng thật, cần xác định rõ header, checkpoint và ý nghĩa offset để không bỏ sót hoặc đọc lặp dòng.

## 8. Late binding cho ItemProcessor và ItemWriter

Processor hoặc writer cũng có thể nhận tham số riêng của StepExecution. Ví dụ processor nhận một mã khu vực do partitioner gán:

```java
@Bean
@StepScope
ItemProcessor<CustomerInput, Customer> customerProcessor(
        @Value("#{stepExecutionContext['regionCode']}") String regionCode,
        CustomerMappingService mappingService) {

    return input -> mappingService.mapForRegion(input, regionCode);
}
```

Writer có thể gắn batch ID hoặc partition name vào dữ liệu đầu ra:

```java
@Bean
@StepScope
JdbcBatchItemWriter<Customer> customerWriter(
        DataSource dataSource,
        @Value("#{stepExecutionContext['partitionName']}") String partitionName) {

    return new JdbcBatchItemWriterBuilder<Customer>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO customer_result
                        (partition_name, customer_id, full_name)
                    VALUES
                        (:partitionName, :customerId, :fullName)
                    """)
            .itemSqlParameterSourceProvider(item ->
                    new BeanPropertyItemSqlParameterSourceProvider<Customer>()
                            .createSqlParameterSource(item))
            .build();
}
```

Đoạn writer trên chỉ minh họa ý tưởng lấy partition name; để bind thêm `partitionName` vào từng parameter source, ứng dụng cần dùng một `ItemSqlParameterSourceProvider` tùy chỉnh hoặc DTO đầu ra đã chứa trường đó. Không nên sao chép nguyên đoạn mapping nếu provider hiện tại chưa cung cấp key SQL tương ứng.

Một cách khác là inject `partitionName` vào writer tùy chỉnh và tạo parameter source chứa cả dữ liệu item lẫn partition name. Dù chọn cách nào, bean cần `@StepScope` để nhận đúng context của từng worker.

## 9. Late binding cho Tasklet

Tasklet cũng có thể đọc giá trị từ StepExecutionContext. Ví dụ một worker Tasklet xử lý một file được giao sẵn:

```java
@Bean
@StepScope
Tasklet processFileTasklet(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile,
        @Value("#{stepExecutionContext['fileType']}") String fileType,
        FileProcessingService fileProcessingService) {

    return (contribution, chunkContext) -> {
        fileProcessingService.process(inputFile, fileType);
        return RepeatStatus.FINISHED;
    };
}
```

Tasklet có thể được dùng trong worker Step của partitioning hoặc trong Step mà dữ liệu đầu vào được thiết lập trước khi Step bắt đầu. Nếu Tasklet cần đọc key được ghi trong chính lần gọi `execute()` hiện tại, hãy truy cập `StepExecution` từ `StepContribution` hoặc `ChunkContext` thay vì mong `@Value` tự cập nhật.

## 10. Kiểu dữ liệu và chuyển đổi giá trị

`ExecutionContext` lưu object theo key. Khi dùng `@Value`, Spring phân giải giá trị và chuyển đổi sang kiểu tham số của bean theo conversion service có sẵn.

Ví dụ context lưu kiểu số:

```java
context.putLong("minId", 100L);
context.putInt("pageSize", 500);
context.putString("regionCode", "NORTH");
```

Bean nhận giá trị tương ứng:

```java
@Bean
@StepScope
Tasklet regionTasklet(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['pageSize']}") Integer pageSize,
        @Value("#{stepExecutionContext['regionCode']}") String regionCode) {

    return (contribution, chunkContext) -> {
        processRegion(minId, pageSize, regionCode);
        return RepeatStatus.FINISHED;
    };
}
```

Nên lưu giá trị bằng đúng kiểu cần sử dụng, chẳng hạn `putLong()` cho khóa ID và `putInt()` cho page size. Điều này giúp giảm lỗi chuyển đổi và làm rõ schema của context.

Với ngày giờ, có thể lưu một biểu diễn ổn định như ISO-8601 rồi parse rõ ràng, hoặc dùng kiểu được serializer của JobRepository hỗ trợ. Không nên giả định mọi object tùy chỉnh đều có thể serialize an toàn.

## 11. Key không tồn tại và giá trị mặc định

Nếu key không tồn tại trong StepExecutionContext, biểu thức có thể trả về `null`. Nếu tham số bean nhận kiểu primitive như `long` hoặc `int`, việc chuyển đổi null có thể gây lỗi. Với key có thể vắng mặt, dùng wrapper type như `Long` hoặc `Integer`, rồi kiểm tra rõ ràng.

Ví dụ:

```java
@Bean
@StepScope
Tasklet optionalRangeTasklet(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    if (minId == null || maxId == null) {
        throw new IllegalStateException(
                "minId and maxId must be provided in StepExecutionContext");
    }

    if (minId > maxId) {
        throw new IllegalArgumentException("Invalid ID range");
    }

    return (contribution, chunkContext) -> {
        processRange(minId, maxId);
        return RepeatStatus.FINISHED;
    };
}
```

Nếu key thực sự tùy chọn, có thể dùng Elvis operator trong SpEL:

```java
@Value("#{stepExecutionContext['pageSize'] ?: 500}") Integer pageSize
```

Giá trị mặc định chỉ nên dùng khi có ý nghĩa nghiệp vụ rõ ràng. Với `minId`, `maxId` hoặc file bắt buộc, tự động thay bằng giá trị mặc định có thể khiến Step xử lý sai phạm vi dữ liệu. Nên fail fast với thông báo chỉ rõ key bị thiếu.

## 12. Lưu dữ liệu vào StepExecutionContext

Có thể ghi dữ liệu vào context từ Tasklet thông qua StepExecution:

```java
@Component
public class PrepareRangeTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        ExecutionContext context = contribution
                .getStepExecution()
                .getExecutionContext();

        context.putLong("minId", 1L);
        context.putLong("maxId", 100_000L);

        return RepeatStatus.FINISHED;
    }
}
```

Giá trị được lưu trong context của StepExecution hiện tại. Một bean `@StepScope` có thể đọc key nếu target bean được tạo sau khi key đã được ghi. Nhưng nếu reader hoặc processor đã được tạo trước khi Tasklet ghi key, giá trị `@Value` đã inject không tự động thay đổi.

Nếu một Step cần tạo context cho Step tiếp theo, có thể ghi vào JobExecutionContext hoặc promote key khi Step hoàn tất. Ví dụ dùng `ExecutionContextPromotionListener`:

```java
@Bean
ExecutionContextPromotionListener promoteRange() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {"minId", "maxId"});
    return listener;
}
```

Step sau đọc các giá trị đã promote bằng `#{jobExecutionContext['minId']}` và `#{jobExecutionContext['maxId']}`. Nó không đọc context của Step trước bằng `stepExecutionContext`.

## 13. Thời điểm persist và restart

StepExecutionContext được quản lý bởi `JobRepository`. Với chunk-oriented Step, trạng thái của reader/ItemStream thường được cập nhật tại ranh giới commit của chunk. Khi Step được restart, framework có thể khôi phục checkpoint đã lưu gần nhất.

Late binding chỉ giúp bean nhận giá trị từ context. Nó không tự bảo đảm rằng key đã được persist hoặc giá trị luôn còn đúng khi restart. Để restart đáng tin cậy:

- Dùng reader/ItemStream có hỗ trợ lưu và khôi phục trạng thái nếu cần checkpoint.
- Giữ tên reader ổn định vì tên thường tham gia tạo key nội bộ trong context.
- Không thay đổi phạm vi partition giữa các lần restart của cùng JobInstance.
- Lưu giá trị cần khôi phục trong context hoặc kho dữ liệu bền vững trước mốc commit phù hợp.
- Bảo đảm nguồn dữ liệu và resource đầu vào ổn định qua restart.

Ví dụ, `minId` và `maxId` do partitioner tạo phải đại diện cùng phạm vi khi cùng JobInstance được restart. Nếu lần đầu `partition0` là ID 1–50.000 nhưng lần restart lại dùng ID 1–60.000, checkpoint cũ có thể không còn tương ứng với phạm vi mới.

## 14. Late binding không phải truy cập context động

Một hiểu nhầm phổ biến là `@Value("#{stepExecutionContext['key']}")` luôn đọc giá trị mới nhất mỗi khi bean dùng field hoặc method. Thực tế, SpEL được phân giải khi target bean scoped được tạo và giá trị được inject vào bean tại thời điểm đó.

Nếu context thay đổi sau khi target đã được tạo, field được inject không tự động cập nhật. Ví dụ:

```java
@Bean
@StepScope
SomeService someService(
        @Value("#{stepExecutionContext['status']}") String status) {
    // status là giá trị được bind khi target bean được tạo.
    return new SomeService(status);
}
```

Nếu một callback trong cùng Step thay đổi `status`, `SomeService` không tự nhận giá trị mới. Khi cần đọc trạng thái mới, truy cập context trực tiếp trong callback hoặc truyền giá trị mới qua method argument.

Điều này cũng là lý do nên tạo các key đầu vào cần thiết trước khi worker Step bắt đầu, thay vì dựa vào việc một bean scoped sẽ tự cập nhật khi context được thay đổi.

## 15. Scope và chạy song song

Trong partitioning, mỗi worker có StepExecution và StepExecutionContext riêng. Bean `@StepScope` được phân giải theo worker execution, nên mỗi worker có thể nhận `minId`, `maxId`, `regionCode` hoặc `inputFile` khác nhau.

Không nên lưu dữ liệu riêng của partition trong field mutable của singleton bean. Nếu một singleton service được dùng đồng thời bởi nhiều worker, nó có thể nhận các lời gọi với tham số khác nhau; service phải thread-safe và không giữ trạng thái theo partition trong field dùng chung.

Với code tự tạo thread, Step scope context có thể không được truyền sang thread mới. Dùng mô hình concurrency mà Spring Batch hỗ trợ và tránh gọi scoped proxy từ thread không có StepContext. Nếu cần truyền dữ liệu sang async task riêng, hãy truyền các giá trị bất biến như tham số method hoặc message payload.

## 16. Bảo mật và kích thước context

ExecutionContext được lưu trong metadata repository, vì vậy chỉ nên chứa dữ liệu nhỏ và có thể serialize bằng cấu hình serializer của ứng dụng.

Nên lưu:

- ID, số lượng, phạm vi, version hoặc mã tham chiếu.
- Đường dẫn resource đã được kiểm soát.
- Các giá trị primitive, String hoặc kiểu nhỏ có serialization rõ ràng.

Tránh lưu:

- Password, access token, private key hoặc secret.
- JDBC Connection, file stream, HTTP client hoặc Spring bean.
- Toàn bộ file hoặc danh sách hàng triệu item.
- Object runtime lớn hoặc không serialize ổn định.

Nếu context cần tham chiếu dữ liệu nhạy cảm, hãy lưu ID của bản ghi được bảo vệ thay vì payload. Với file, có thể lưu đường dẫn và checksum hoặc version để xác minh resource khi restart.

## 17. Kiểm thử `@Value` từ StepExecutionContext

Test nên chứng minh bean `@StepScope` nhận đúng giá trị theo StepExecution, đặc biệt khi cùng một worker Step được chạy cho nhiều partition.

Các tình huống cần kiểm tra:

1. Context có key hợp lệ: bean nhận đúng giá trị.
2. Key bị thiếu: Step thất bại sớm với thông báo rõ.
3. Giá trị sai kiểu: conversion hoặc validation báo lỗi phù hợp.
4. Hai partition có hai phạm vi khác nhau: mỗi reader nhận đúng `minId` và `maxId`.
5. Key được ghi trước khi target bean tạo: giá trị được bind đúng.
6. Key được ghi sau khi target bean tạo: giá trị đã inject không tự cập nhật.
7. Restart: partitioner tái tạo cùng tên và phạm vi; checkpoint được khôi phục đúng.

Ví dụ test Step với `JobLauncherTestUtils`:

```java
@SpringBatchTest
@SpringJUnitConfig(PartitionJobTestConfiguration.class)
class StepExecutionContextBindingTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void bindsPartitionRangeToReader() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", "BATCH-TEST-01", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertEquals(expectedIds, outputRepository.findAllIds());
    }
}
```

Test cần cấu hình partitioner với các range xác định và output repository phù hợp. Có thể kiểm tra dữ liệu đầu ra hoặc một probe service để chứng minh mỗi worker nhận đúng phạm vi. Không nên chỉ kiểm tra Job `COMPLETED`, vì Job vẫn có thể hoàn tất dù reader nhận nhầm key hoặc phạm vi.

## 18. Các lỗi thường gặp

**Quên `@StepScope`:** bean singleton không có StepExecution cụ thể khi khởi tạo. Dùng `@StepScope` cho bean cần late binding theo Step.

**Dùng sai tên biến SpEL:** phải dùng `stepExecutionContext`, không phải `stepContext` hoặc `stepExecution` khi muốn truy cập map context.

**Dùng sai key:** key trong `@Value` phải khớp chính xác với key được ghi vào `ExecutionContext`.

**Nhầm với JobExecutionContext:** dữ liệu dùng chung giữa các Step cần nằm trong JobExecutionContext hoặc kho dữ liệu chung, không phải StepExecutionContext của Step trước.

**Tạo key sau khi bean đã khởi tạo:** giá trị `@Value` không tự cập nhật. Hãy tạo context trước khi target bean được tạo hoặc đọc context trực tiếp lúc cần.

**Dùng primitive cho key có thể thiếu:** null không thể chuyển thành `long` hoặc `int` một cách an toàn. Dùng wrapper type và validate.

**Cho rằng context là cache trong bộ nhớ:** context được quản lý và persist theo lifecycle của JobRepository. Không giả định mọi `put()` lập tức được ghi xuống database.

**Lưu object lớn hoặc secret:** làm metadata phình to hoặc để lộ thông tin nhạy cảm. Chỉ lưu metadata nhỏ và tham chiếu.

**Dùng singleton mutable state cho partition:** nhiều worker có thể ghi đè giá trị của nhau. Dùng StepScope và biến cục bộ.

**Thay đổi phạm vi partition khi restart:** checkpoint cũ có thể không còn khớp dữ liệu mới. Giữ partition name và phạm vi ổn định cho cùng JobInstance.

## Kết luận

`@Value("#{stepExecutionContext['key']}")` cho phép bean lấy giá trị từ ExecutionContext của StepExecution hiện tại. Bean cần `@StepScope` để target được tạo khi StepExecution đã tồn tại và context có thể được phân giải. Cách này đặc biệt hữu ích cho reader, processor, writer và Tasklet trong partitioning, nơi mỗi worker nhận phạm vi hoặc resource riêng. Hãy phân biệt StepExecutionContext với JobExecutionContext và JobParameters, bảo đảm key tồn tại trước khi target bean được tạo, kiểm tra null/kiểu dữ liệu, giữ context nhỏ và có thể serialize, đồng thời duy trì phạm vi ổn định qua restart.
