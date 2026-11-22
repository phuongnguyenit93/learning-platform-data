# Scope khi test job

Trong Spring Batch, nhiều bean chỉ có thể được tạo hoặc sử dụng đúng khi một job hoặc step đang chạy. Hai scope quan trọng là `@JobScope` và `@StepScope`. Chúng cho phép bean nhận giá trị runtime từ `JobParameters`, `JobExecutionContext` hoặc `StepExecutionContext` bằng late binding.

Khi viết test, cần tạo đúng ngữ cảnh thực thi để các bean scoped hoạt động như trong job thật. Nếu không có `JobExecution` hoặc `StepExecution` đang hoạt động, ứng dụng có thể gặp lỗi không tìm thấy scope, không resolve được SpEL hoặc tạo bean với dữ liệu runtime không đúng. Spring Batch Test cung cấp listener và utility để thiết lập các scope này trong unit test và integration test.

## 1. Vì sao scope quan trọng khi test?

Một bean thông thường có thể được tạo ngay khi Spring ApplicationContext khởi động. Nhưng bean có `@StepScope` hoặc `@JobScope` phụ thuộc vào execution context của Spring Batch. Giá trị như tên file đầu vào, ngày nghiệp vụ, partition range hoặc checkpoint chỉ có khi job/step bắt đầu.

Ví dụ reader nhận đường dẫn từ JobParameters:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fieldSet -> new OrderInput(
                    fieldSet.readString("orderId"),
                    fieldSet.readBigDecimal("amount")))
            .build();
}
```

Bean reader này cần `inputFile` ở thời điểm step execution hoạt động. Trong test, chỉ tạo ApplicationContext rồi gọi trực tiếp `orderReader()` là chưa đủ. Test cần kích hoạt step scope và cung cấp một `StepExecution` có JobParameters phù hợp.

## 2. Phân biệt singleton, JobScope và StepScope

| Scope | Vòng đời | Dùng phù hợp cho |
|---|---|---|
| Singleton (mặc định) | Một instance trong ApplicationContext | Service/stateless component dùng chung, không phụ thuộc execution cụ thể. |
| `@JobScope` | Một instance trong phạm vi một `JobExecution` | Bean cần JobParameters hoặc Job ExecutionContext và được chia sẻ giữa các step của cùng job execution. |
| `@StepScope` | Một instance trong phạm vi một `StepExecution` | Reader, writer, processor hoặc tasklet cần tham số riêng của step/partition. |

Khi restart, một `JobExecution` mới được tạo cho cùng `JobInstance`; job-scoped bean có vòng đời gắn với execution mới. Mỗi worker/partition có `StepExecution` riêng nên step-scoped bean có thể nhận dữ liệu riêng cho partition đó.

Không nên dùng `@JobScope` hoặc `@StepScope` chỉ để tránh phải truyền tham số giữa các class. Hãy dùng scope khi bean thực sự phụ thuộc dữ liệu của job/step execution. Các service nghiệp vụ không phụ thuộc execution thường nên giữ stateless và dùng singleton.

## 3. Late binding và proxy trong scoped bean

Spring Batch tạo scoped bean thông qua proxy. Bean proxy có thể được inject vào cấu hình hoặc thành phần singleton trước khi scope thực sự hoạt động. Đối tượng đích được tạo khi execution tương ứng bắt đầu và giá trị late-bound được resolve.

Ví dụ các biểu thức thường dùng:

| SpEL | Giá trị được lấy từ |
|---|---|
| `#{jobParameters['inputFile']}` | JobParameters của job execution hiện tại. |
| `#{jobExecutionContext['batchReference']}` | Job ExecutionContext. |
| `#{stepExecutionContext['minId']}` | Step ExecutionContext của step hiện tại. |
| `#{stepExecution.stepName}` | Tên step hiện tại. |
| `#{jobExecution.jobInstance.jobName}` | Tên job của execution hiện tại. |

Test phải thiết lập đúng context trước khi gọi method trên proxy. Nếu gọi scoped bean ngoài scope, thường gặp lỗi dạng `ScopeNotActiveException` hoặc thông báo scope chưa được đăng ký/kích hoạt, tùy phiên bản Spring và cách cấu hình.

## 4. Dependency cần có cho Spring Batch Test

Để kiểm thử scope và job/step execution, thêm module `spring-batch-test` cùng phiên bản tương thích với Spring Batch đang sử dụng.

Ví dụ Gradle:

```groovy
dependencies {
    testImplementation("org.springframework.batch:spring-batch-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Nếu dự án dùng Spring Boot dependency management hoặc Spring Batch BOM, nên để dependency version được quản lý tập trung để tránh lệch phiên bản giữa `spring-batch-core` và `spring-batch-test`.

Một số thành phần hữu ích:

- `@SpringBatchTest`: hỗ trợ cấu hình test Spring Batch và các tiện ích kiểm thử.
- `StepScopeTestExecutionListener`: kích hoạt step scope trong phạm vi test method.
- `JobScopeTestExecutionListener`: kích hoạt job scope trong phạm vi test method.
- `StepScopeTestUtils`: chạy một đoạn code trong step scope với `StepExecution` được cung cấp.
- `JobScopeTestUtils`: chạy một đoạn code trong job scope với `JobExecution` được cung cấp.
- `MetaDataInstanceFactory`: tạo các đối tượng metadata như `JobExecution` và `StepExecution` cho test.
- `JobLauncherTestUtils`: khởi chạy job/step trong integration test.
- `JobRepositoryTestUtils`: hỗ trợ dọn metadata test khi cần.

Tên package và overload cụ thể có thể khác theo phiên bản Spring Batch. Hãy dùng các API được cung cấp bởi đúng phiên bản `spring-batch-test` trong dự án.

## 5. Dùng @SpringBatchTest trong integration test

`@SpringBatchTest` là cách thuận tiện khi test job hoặc step được cấu hình trong Spring context. Annotation này đăng ký các tiện ích test như `JobLauncherTestUtils`, `JobRepositoryTestUtils` và hỗ trợ các listener cần thiết để làm việc với job/step scope.

Ví dụ cấu trúc test:

```java
@SpringBootTest
@SpringBatchTest
class OrderImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void importsOrdersUsingTestParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .addString("businessDate", "2026-11-15")
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
    }
}
```

Ví dụ giả định job được cấu hình trong application context và test có database/schema phù hợp. `JobLauncherTestUtils` cần biết job cần chạy; nếu context có nhiều job, có thể cần cấu hình tên job cho test utility theo API của phiên bản đang dùng.

`@SpringBatchTest` không tự cung cấp file test hoặc database đã được chuẩn bị. Test vẫn phải tạo input, cấu hình datasource, schema metadata và dữ liệu nghiệp vụ cần thiết.

## 6. Test một StepScope bean bằng StepScopeTestUtils

Nếu chỉ muốn test reader, processor hoặc writer mà không chạy toàn job, có thể dùng `StepScopeTestUtils.doInStepScope`.

Ví dụ test reader nhận `inputFile` từ JobParameters:

```java
@SpringJUnitConfig(OrderBatchConfiguration.class)
class OrderReaderScopeTest {

    @Autowired
    private FlatFileItemReader<OrderInput> orderReader;

    @Test
    void readsFileFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .toJobParameters();

        StepExecution stepExecution = MetaDataInstanceFactory
                .createStepExecution(parameters);

        StepScopeTestUtils.doInStepScope(stepExecution, () -> {
            orderReader.open(stepExecution.getExecutionContext());
            try {
                OrderInput first = orderReader.read();
                assertThat(first.orderId()).isEqualTo("O-001");
            } finally {
                orderReader.close();
            }
            return null;
        });
    }
}
```

Điểm quan trọng là `StepScopeTestUtils` thiết lập context cho lời gọi bên trong lambda. Khi thoát khỏi block, step scope được đóng lại. Các thao tác đọc scoped bean phải diễn ra bên trong block đó.

Nếu reader được cấu hình với `@StepScope`, hãy inject proxy vào test. Không gọi trực tiếp phương thức factory `@Bean` để lấy target object ngoài scope.

## 7. Tạo StepExecution có JobParameters và ExecutionContext

`MetaDataInstanceFactory` giúp tạo metadata test mà không cần khởi chạy job thật.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "src/test/resources/orders.csv")
        .addString("businessDate", "2026-11-15")
        .toJobParameters();

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(parameters);

stepExecution.getExecutionContext().putLong("minId", 100L);
stepExecution.getExecutionContext().putLong("maxId", 200L);

stepExecution.getJobExecution().getExecutionContext()
        .putString("batchReference", "TEST-BATCH-01");
```

Trong test scoped bean:

- `jobParameters` lấy từ `stepExecution.getJobParameters()` thông qua JobExecution liên kết.
- `stepExecutionContext` lấy từ `stepExecution.getExecutionContext()`.
- `jobExecutionContext` lấy từ `stepExecution.getJobExecution().getExecutionContext()`.

Điều này cho phép test các biểu thức SpEL mà không phải chạy toàn bộ job flow. Cần đặt đúng key và kiểu dữ liệu mà bean mong đợi.

## 8. Dùng StepScopeTestExecutionListener

Khi muốn nhiều test method trong một class tự động có step scope, có thể dùng `StepScopeTestExecutionListener`. Listener thiết lập `StepExecution` cho test method và đóng scope sau khi test kết thúc.

Ví dụ:

```java
@SpringJUnitConfig(OrderBatchConfiguration.class)
@TestExecutionListeners(
        listeners = StepScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class OrderReaderStepScopeTest {

    @Autowired
    private FlatFileItemReader<OrderInput> orderReader;

    public StepExecution getStepExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv")
                .toJobParameters();

        StepExecution execution = MetaDataInstanceFactory
                .createStepExecution(parameters);
        execution.getExecutionContext().putString("region", "NORTH");
        return execution;
    }

    @Test
    void readsWithActiveStepScope() throws Exception {
        orderReader.open(new ExecutionContext());
        try {
            assertThat(orderReader.read()).isNotNull();
        } finally {
            orderReader.close();
        }
    }
}
```

Listener có thể tìm phương thức factory `getStepExecution` trên test class để lấy execution tùy chỉnh; nếu không có, listener dùng metadata mặc định. Cần tham khảo tài liệu API đúng phiên bản để biết quy ước factory method và cách listener được đăng ký.

Khi dùng `@SpringBatchTest`, các listener scope đã được đăng ký cho test context; tránh đăng ký lặp theo cách gây xung đột. Nếu tự khai báo `@TestExecutionListeners`, dùng `MERGE_WITH_DEFAULTS` khi cần giữ các listener mặc định khác của Spring Test.

## 9. Test một JobScope bean bằng JobScopeTestUtils

`@JobScope` gắn vòng đời bean với một `JobExecution`. Bean có thể đọc JobParameters hoặc Job ExecutionContext và được chia sẻ giữa các step thuộc cùng job execution.

Ví dụ bean job-scoped:

```java
@Bean
@JobScope
BatchRunDescriptor batchRunDescriptor(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobExecutionContext['batchReference']}") String batchReference) {

    return new BatchRunDescriptor(businessDate, batchReference);
}
```

Test có thể tạo `JobExecution` rồi chạy code trong job scope:

```java
@SpringJUnitConfig(BatchConfiguration.class)
class BatchRunDescriptorTest {

    @Autowired
    private BatchRunDescriptor batchRunDescriptor;

    @Test
    void resolvesJobScopedValues() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15")
                .toJobParameters();

        JobExecution jobExecution = MetaDataInstanceFactory
                .createJobExecution(parameters);
        jobExecution.getExecutionContext()
                .putString("batchReference", "BATCH-TEST-01");

        JobScopeTestUtils.doInJobScope(jobExecution, () -> {
            assertThat(batchRunDescriptor.businessDate())
                    .isEqualTo("2026-11-15");
            assertThat(batchRunDescriptor.batchReference())
                    .isEqualTo("BATCH-TEST-01");
            return null;
        });
    }
}
```

`JobScopeTestUtils` thiết lập job scope trong thời gian thực thi callback. Nếu phiên bản đang dùng không cung cấp utility này hoặc test cần kiểm tra toàn bộ job lifecycle, có thể dùng `JobScopeTestExecutionListener` hoặc khởi chạy job qua `JobLauncherTestUtils`.

## 10. Dùng JobScopeTestExecutionListener

Tương tự step scope, job scope có listener để kích hoạt context trong test method.

```java
@SpringJUnitConfig(BatchConfiguration.class)
@TestExecutionListeners(
        listeners = JobScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class BatchRunDescriptorScopeTest {

    @Autowired
    private BatchRunDescriptor batchRunDescriptor;

    public JobExecution getJobExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15")
                .toJobParameters();

        JobExecution execution = MetaDataInstanceFactory
                .createJobExecution(parameters);
        execution.getExecutionContext()
                .putString("batchReference", "BATCH-TEST-01");
        return execution;
    }

    @Test
    void readsValuesFromActiveJobScope() {
        assertThat(batchRunDescriptor.businessDate())
                .isEqualTo("2026-11-15");
    }
}
```

Listener thiết lập `JobExecution` cho test method theo cơ chế factory method của Spring Batch Test. Nếu dùng `@SpringBatchTest`, hãy kiểm tra listener đã được đăng ký tự động để không cấu hình trùng.

## 11. Khi nào dùng utility, listener hay chạy cả job?

Ba cách kiểm thử phục vụ các mức khác nhau:

| Cách | Phạm vi | Khi phù hợp |
|---|---|---|
| `StepScopeTestUtils` | Một đoạn code trong StepScope | Test reader/processor/writer scoped độc lập với Job flow. |
| `JobScopeTestUtils` | Một đoạn code trong JobScope | Test bean phụ thuộc JobParameters/JobExecutionContext. |
| Scope test execution listener | Scope được kích hoạt cho test method | Nhiều test method cần cùng kiểu metadata setup. |
| `JobLauncherTestUtils` | Khởi chạy job/step thật trong test context | Kiểm tra wiring, flow, transaction và tương tác giữa các thành phần. |

Nên test riêng scoped bean khi cần xác định lỗi ở late binding hoặc logic của bean. Dùng integration test khi cần xác nhận Spring Batch thực sự tạo scope, khởi chạy step và lưu metadata như mong đợi.

## 12. Test StepScope reader với dữ liệu trong Step ExecutionContext

Một partitioned reader thường lấy khoảng dữ liệu từ Step ExecutionContext. Test phải thêm các key tương ứng trước khi kích hoạt step scope.

Ví dụ:

```java
@Bean
@StepScope
JdbcPagingItemReader<CustomerInput> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .dataSource(dataSource)
            .selectClause("select id, name")
            .fromClause("from customer")
            .whereClause("where id between :minId and :maxId")
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .sortKeys(Map.of("id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new CustomerInput(
                    rs.getLong("id"), rs.getString("name")))
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Test:

```java
StepExecution execution = MetaDataInstanceFactory.createStepExecution();
execution.getExecutionContext().putLong("minId", 100L);
execution.getExecutionContext().putLong("maxId", 199L);

StepScopeTestUtils.doInStepScope(execution, () -> {
    customerReader.open(execution.getExecutionContext());
    try {
        CustomerInput item = customerReader.read();
        assertThat(item).isNotNull();
        assertThat(item.id()).isBetween(100L, 199L);
    } finally {
        customerReader.close();
    }
    return null;
});
```

Test cần database test có schema và dữ liệu phù hợp. Nếu chỉ muốn kiểm tra SpEL hoặc việc nhận tham số, có thể dùng mock dependency thay vì tạo database thật; nhưng để xác nhận paging query và mapping, integration test với database là cần thiết.

## 13. Scope và test theo partition

Mỗi partition có `StepExecution` riêng, vì vậy step-scoped bean nên nhận context của đúng partition. Khi test một worker step, tạo StepExecution có `ExecutionContext` tương ứng với partition đang mô phỏng.

Ví dụ hai partition:

```java
StepExecution north = MetaDataInstanceFactory.createStepExecution();
north.getExecutionContext().putString("region", "NORTH");

StepExecution south = MetaDataInstanceFactory.createStepExecution();
south.getExecutionContext().putString("region", "SOUTH");
```

Có thể chạy cùng một proxy trong hai scope riêng biệt để xác nhận giá trị được resolve theo từng execution:

```java
String northRegion = StepScopeTestUtils.doInStepScope(north,
        () -> regionScopedReader.region());

String southRegion = StepScopeTestUtils.doInStepScope(south,
        () -> regionScopedReader.region());

assertThat(northRegion).isEqualTo("NORTH");
assertThat(southRegion).isEqualTo("SOUTH");
```

Ví dụ giả định bean `regionScopedReader` có method `region()` chỉ để minh họa giá trị late binding. Trong ứng dụng thật, nên test hành vi đọc/ghi của worker thay vì thêm accessor chỉ phục vụ test nếu nó không có ý nghĩa trong API production.

Không nên chạy đồng thời nhiều test scope trên cùng một thread hoặc chia sẻ cùng scoped target instance. Scope context gắn với execution/thread và được thiết lập bởi Spring Batch Test; khi test concurrency thật, cần dùng integration test riêng để xác nhận thread safety.

## 14. Test ExecutionContext và JobParameters khác nhau

Một lỗi phổ biến là đặt dữ liệu vào sai context. JobParameters là input của lần chạy; Step ExecutionContext và Job ExecutionContext là trạng thái runtime.

| Dữ liệu cần test | Nơi thiết lập |
|---|---|
| Đường dẫn file truyền khi launch job | `JobParameters` |
| Ngày nghiệp vụ được scheduler cung cấp | `JobParameters` |
| Min/max ID của partition | `StepExecution.getExecutionContext()` |
| File đã được step trước xác nhận và promote | `JobExecution.getExecutionContext()` |
| Checkpoint reader | Step ExecutionContext theo reader/stream lifecycle |

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15")
        .toJobParameters();

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(parameters);

stepExecution.getExecutionContext().putString("partition", "P-01");
stepExecution.getJobExecution().getExecutionContext()
        .putString("batchReference", "B-20261115-01");
```

Bean dùng `#{jobParameters['businessDate']}` cần giá trị trong JobParameters. Bean dùng `#{stepExecutionContext['partition']}` cần giá trị trong Step ExecutionContext. Bean dùng `#{jobExecutionContext['batchReference']}` cần giá trị trong Job ExecutionContext.

## 15. Test step-scoped Tasklet

Tasklet có thể được khai báo `@StepScope` để nhận tham số runtime. Có thể test tasklet trực tiếp trong step scope thay vì chạy toàn job.

```java
@Bean
@StepScope
Tasklet archiveFileTasklet(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return (contribution, chunkContext) -> {
        archiveService.archive(inputFile);
        return RepeatStatus.FINISHED;
    };
}
```

Trong test, tạo StepExecution có JobParameters và gọi tasklet trong `StepScopeTestUtils`. Nếu test chỉ muốn xác nhận tham số được truyền đúng, có thể mock `archiveService` và xác minh lời gọi. Nếu muốn kiểm tra transaction, metadata hoặc restart, hãy chạy step qua `JobLauncherTestUtils` với repository test.

Không nên gọi method factory `archiveFileTasklet(...)` trực tiếp trong test để truyền giá trị giả rồi kết luận scope hoạt động. Cách đó kiểm tra Java method thông thường, không kiểm tra late binding/proxy của Spring Batch.

## 16. Test job-scoped bean được chia sẻ giữa các step

`@JobScope` hữu ích khi nhiều step trong cùng JobExecution cần dùng một bean chứa metadata chung, ví dụ descriptor của batch. Để kiểm tra, cần đảm bảo các lần truy cập nằm trong cùng JobScope và cùng `JobExecution`.

Ví dụ bean:

```java
@Bean
@JobScope
BatchRunDescriptor batchRunDescriptor(
        @Value("#{jobParameters['businessDate']}") String businessDate) {
    return new BatchRunDescriptor(businessDate);
}
```

Trong integration test, có thể khởi chạy job bằng JobParameters test và inject bean proxy vào các thành phần được job sử dụng. Các step của cùng JobExecution sẽ resolve cùng job-scoped target theo scope.

Nếu test hai JobExecution khác nhau, cần thiết lập hai job scope riêng. Không nên giữ reference tới target object của execution trước rồi sử dụng sau khi scope đóng. Hãy truy cập qua proxy trong phạm vi execution tương ứng.

## 17. Test restart với scoped bean

Restart tạo `JobExecution` mới cho cùng `JobInstance`. Vì scope gắn với execution, job-scoped và step-scoped bean được tạo trong context của execution mới. Giá trị late binding sẽ được resolve từ parameters và ExecutionContext tương ứng với lần restart.

Khi test restart, cần kiểm tra:

- Identifying JobParameters giữ nguyên để cùng JobInstance được tiếp tục.
- JobExecution mới được tạo.
- Step đã hoàn tất được bỏ qua theo mặc định, trừ khi `allowStartIfComplete(true)`.
- Step thất bại được chạy lại theo flow và `startLimit`.
- Reader/writer khôi phục checkpoint từ ExecutionContext.
- Scoped bean nhận đúng JobParameters và context của execution mới.
- Bean không giữ dữ liệu mutable từ execution cũ.

Một test scope riêng lẻ không đủ chứng minh restart hoạt động. Cần integration test với JobRepository bền vững hoặc repository test phù hợp, chạy job thất bại rồi restart cùng identifying parameters.

## 18. Scope và concurrency trong test

Local partitioning hoặc multi-threaded step có thể chạy nhiều worker đồng thời. `@StepScope` giúp tạo target riêng theo StepExecution, nhưng không đảm bảo mọi dependency mà target sử dụng đều thread-safe.

Ví dụ reader step-scoped có thể inject một singleton service dùng chung. Nếu service đó giữ state mutable, nhiều worker vẫn có thể gây race condition.

Khi test concurrency:

- Xác nhận mỗi worker có `StepExecution` và `ExecutionContext` riêng.
- Xác nhận late binding nhận đúng partition key/range.
- Không chia sẻ reader/writer có state giữa các worker nếu implementation không thread-safe.
- Kiểm tra dependency singleton được inject vào scoped bean có an toàn khi gọi đồng thời không.
- Dùng database hoặc resource test có thể mô phỏng concurrency thật khi cần kiểm tra lock và transaction.
- Không giả định unit test chạy tuần tự chứng minh được thread safety.

## 19. Những lỗi thường gặp khi test scope

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `ScopeNotActiveException` | Gọi scoped proxy ngoài job/step scope. | Dùng `StepScopeTestUtils`, `JobScopeTestUtils`, listener hoặc launch job. |
| SpEL trả về `null` | Key không có trong JobParameters/ExecutionContext hoặc sai tên key. | Thiết lập đúng context và đúng kiểu dữ liệu trước khi gọi bean. |
| Bean được tạo nhưng dùng giá trị cũ | Test gọi target ngoài scope hoặc giữ reference qua execution. | Inject proxy và truy cập trong scope tương ứng. |
| `@StepScope` không được áp dụng | Bean chưa được khai báo scoped hoặc cấu hình scope chưa được bật. | Kiểm tra annotation/configuration và dependency Spring Batch. |
| Test reader không tìm thấy file | JobParameters trỏ tới đường dẫn sai hoặc resource không có trong test. | Dùng test resource có sẵn và đường dẫn xác định. |
| `JobParameters` đúng nhưng step context thiếu key | Key được đặt nhầm vào Job ExecutionContext. | Đặt key vào `stepExecution.getExecutionContext()`. |
| Job-scoped bean không resolve được | Chưa có JobExecution scope đang hoạt động. | Dùng JobScopeTestUtils/listener hoặc launch job. |
| Test chạy riêng được nhưng job thật lỗi | Unit test chỉ kiểm tra bean, chưa kiểm tra wiring/flow/transaction. | Bổ sung integration test với JobLauncherTestUtils. |
| Test bị ảnh hưởng bởi execution trước | Metadata/database test dùng chung hoặc dữ liệu chưa được dọn. | Dùng dữ liệu test độc lập và dọn JobRepository có kiểm soát. |
| Scoped bean gặp race condition | Dependency singleton bên trong bean không thread-safe. | Kiểm tra toàn bộ dependency graph và chạy test concurrency. |

## 20. Quy trình viết test cho scoped component

Khi kiểm thử một bean có `@JobScope` hoặc `@StepScope`, có thể làm theo trình tự:

1. **Xác định scope:** bean phụ thuộc JobExecution hay StepExecution?
2. **Liệt kê late-bound key:** JobParameters, Job ExecutionContext hoặc Step ExecutionContext nào được sử dụng?
3. **Chọn mức test:** test bean riêng, test scope listener hay chạy toàn job/step?
4. **Tạo metadata:** dùng `MetaDataInstanceFactory` để tạo JobExecution/StepExecution phù hợp.
5. **Đặt dữ liệu context:** thêm key và value đúng kiểu trước khi kích hoạt scope.
6. **Kích hoạt scope:** dùng `StepScopeTestUtils`, `JobScopeTestUtils` hoặc listener tương ứng.
7. **Gọi qua proxy:** không lấy target object bằng cách gọi factory method ngoài scope.
8. **Kiểm tra hành vi:** xác nhận bean nhận đúng tham số và thực hiện đúng logic.
9. **Giải phóng tài nguyên:** đóng reader/writer hoặc resource được mở trong test.
10. **Bổ sung integration test:** kiểm tra flow, transaction, repository và restart khi cần.

Với reader/writer triển khai `ItemStream`, cần kiểm tra cả `open`, `read`/`write`, `update` và `close` theo vòng đời thực tế. Không chỉ gọi một method nghiệp vụ mà bỏ qua quản lý resource.

## 21. Những điểm cần ghi nhớ

- `@JobScope` gắn bean với một `JobExecution`; `@StepScope` gắn bean với một `StepExecution`.
- Scoped bean thường được inject qua proxy và chỉ resolve late-bound value khi scope tương ứng hoạt động.
- Dùng `spring-batch-test` để có listener và utility hỗ trợ kiểm thử scope.
- `@SpringBatchTest` thuận tiện cho integration test job/step và hỗ trợ các test scope listener.
- `StepScopeTestUtils` chạy callback trong StepScope với một `StepExecution` cụ thể.
- `JobScopeTestUtils` chạy callback trong JobScope với một `JobExecution` cụ thể nếu phiên bản thư viện cung cấp API này.
- `MetaDataInstanceFactory` tạo metadata test; cần tự thiết lập JobParameters và ExecutionContext đúng key/kiểu.
- `StepScopeTestExecutionListener` và `JobScopeTestExecutionListener` có thể thiết lập scope cho test method.
- Phân biệt JobParameters, Job ExecutionContext và Step ExecutionContext để đặt dữ liệu test đúng nơi.
- Test scoped bean riêng không thay thế integration test cho flow, transaction, repository và restart.
- `@StepScope` không tự làm mọi dependency bên trong thread-safe; concurrency test cần kiểm tra toàn bộ dependency graph.
- Không giữ target object của scoped bean sau khi execution scope đã đóng.

Khi test job hoặc step có scoped component, hãy tạo đúng execution context trước khi truy cập bean. Dùng utility/listener cho kiểm thử scope riêng và `JobLauncherTestUtils` cho kiểm thử tích hợp. Cách làm này giúp xác nhận late binding, vòng đời bean, tham số runtime và hành vi của Spring Batch trong môi trường test gần với lúc job thực sự chạy.
