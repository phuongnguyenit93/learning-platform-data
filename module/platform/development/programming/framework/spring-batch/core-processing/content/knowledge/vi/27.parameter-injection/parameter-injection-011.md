# Kiểm thử parameter binding

Trong Spring Batch, nhiều bean chỉ nhận được dữ liệu đầu vào khi job hoặc step bắt đầu chạy. Các giá trị này thường được inject bằng SpEL từ `JobParameters`, `JobExecutionContext` hoặc `StepExecutionContext`, thông qua `@JobScope` và `@StepScope`. Cơ chế đó được gọi là late binding.

Khi kiểm thử, chỉ tạo Spring ApplicationContext là chưa đủ để xác nhận parameter binding hoạt động. Test phải cung cấp đúng execution context, kích hoạt scope tương ứng và truy cập bean thông qua scoped proxy. Với kiểm thử tích hợp, cần khởi chạy job hoặc step bằng `JobParameters` thực tế để xác nhận toàn bộ đường đi từ launcher đến bean.

## 1. Parameter binding trong Spring Batch

Spring Batch có ba nguồn dữ liệu thường được dùng trong biểu thức SpEL:

| Nguồn | Ví dụ SpEL | Phạm vi |
|---|---|---|
| `JobParameters` | `#{jobParameters['inputFile']}` | Tham số được cung cấp khi khởi chạy job. |
| Job `ExecutionContext` | `#{jobExecutionContext['batchReference']}` | Metadata runtime thuộc một `JobExecution`. |
| Step `ExecutionContext` | `#{stepExecutionContext['minId']}` | Metadata runtime thuộc một `StepExecution`. |

Ví dụ một reader nhận file và ngày nghiệp vụ từ JobParameters, đồng thời nhận khoảng ID từ Step ExecutionContext:

```java
@Bean
@StepScope
JdbcPagingItemReader<OrderInput> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .dataSource(dataSource)
            .selectClause("select order_id, amount")
            .fromClause("from orders")
            .whereClause("where business_date = :businessDate " +
                    "and order_id between :minId and :maxId")
            .parameterValues(Map.of(
                    "businessDate", businessDate,
                    "minId", minId,
                    "maxId", maxId))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getString("order_id"), rs.getBigDecimal("amount")))
            .pageSize(200)
            .saveState(true)
            .build();
}
```

`@StepScope` cho phép Spring tạo target bean khi có `StepExecution` đang hoạt động. Khi đó các biểu thức SpEL mới được resolve với dữ liệu của execution hiện tại.

## 2. Phân biệt JobParameters với ExecutionContext khi test

Một lỗi thường gặp là đặt giá trị vào sai nguồn. `JobParameters` là input của lần khởi chạy job; `ExecutionContext` lưu trạng thái phát sinh trong quá trình chạy.

| Dữ liệu | Nơi thiết lập trong test |
|---|---|
| Đường dẫn file được scheduler truyền vào | `JobParameters` |
| Ngày nghiệp vụ của lần chạy | `JobParameters` |
| Mã batch được step trước ghi để step sau dùng | `JobExecution.getExecutionContext()` |
| Min/max ID của một partition | `StepExecution.getExecutionContext()` |
| Checkpoint reader | Step ExecutionContext theo vòng đời `ItemStream` |

Ví dụ tạo metadata test với cả ba nguồn:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "src/test/resources/orders.csv", true)
        .toJobParameters();

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(parameters);

stepExecution.getExecutionContext().putLong("minId", 100L);
stepExecution.getExecutionContext().putLong("maxId", 199L);

stepExecution.getJobExecution().getExecutionContext()
        .putString("batchReference", "TEST-BATCH-01");
```

Sau đó:

- `#{jobParameters['businessDate']}` đọc từ JobParameters của JobExecution liên kết với StepExecution.
- `#{stepExecutionContext['minId']}` đọc từ Step ExecutionContext.
- `#{jobExecutionContext['batchReference']}` đọc từ Job ExecutionContext.

Test phải đặt giá trị vào đúng context trước khi target scoped bean được tạo.

## 3. Vì sao cần @StepScope hoặc @JobScope?

Bean singleton mặc định được tạo khi ApplicationContext khởi động. Ở thời điểm đó, Spring Batch chưa có `JobExecution` hoặc `StepExecution` cụ thể để resolve các tham số runtime.

`@StepScope` và `@JobScope` tạo proxy để trì hoãn việc tạo target bean đến khi scope tương ứng hoạt động.

| Scope | Gắn với | Có thể bind dữ liệu thường dùng |
|---|---|---|
| Singleton | ApplicationContext | Cấu hình tĩnh, dependency không phụ thuộc execution. |
| `@JobScope` | Một `JobExecution` | JobParameters, Job ExecutionContext. |
| `@StepScope` | Một `StepExecution` | JobParameters, Job ExecutionContext, Step ExecutionContext. |

Một bean `@JobScope` không có một step cụ thể để đọc Step ExecutionContext. Nếu giá trị thay đổi theo từng step hoặc partition, hãy dùng `@StepScope`.

Khi test, cần truy cập bean qua proxy bên trong scope. Không gọi trực tiếp method factory `@Bean` để lấy target object ngoài scope rồi cho rằng late binding đã được kiểm tra.

## 4. Chuẩn bị dependency kiểm thử

Thêm `spring-batch-test` với phiên bản tương thích với Spring Batch đang dùng:

```groovy
dependencies {
    testImplementation("org.springframework.batch:spring-batch-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Nếu dự án dùng Spring Boot dependency management hoặc Spring Batch BOM, nên để version được quản lý tập trung để tránh lệch giữa `spring-batch-core` và `spring-batch-test`.

Các tiện ích thường dùng:

- `MetaDataInstanceFactory`: tạo `JobExecution` và `StepExecution` cho test.
- `StepScopeTestUtils`: chạy một callback trong StepScope với StepExecution đã cho.
- `JobScopeTestUtils`: chạy một callback trong JobScope với JobExecution đã cho.
- `StepScopeTestExecutionListener`: kích hoạt StepScope cho test method.
- `JobScopeTestExecutionListener`: kích hoạt JobScope cho test method.
- `@SpringBatchTest`: đăng ký các tiện ích test Spring Batch, gồm listener cho scope và các utility launcher/repository.
- `JobLauncherTestUtils`: chạy job hoặc step trong integration test.

Tên package, overload và cách cấu hình cụ thể phụ thuộc phiên bản. Dùng API từ đúng phiên bản `spring-batch-test` được khai báo trong dự án.

Ngoài dependency test, ApplicationContext cần cấu hình Spring Batch để đăng ký các scope. Điều này thường được cung cấp bởi `@EnableBatchProcessing`, `DefaultBatchConfiguration` hoặc auto-configuration của Spring Boot. `@SpringBatchTest` hỗ trợ test; nó không thay thế cấu hình batch infrastructure và datasource của ứng dụng.

## 5. Test StepScope bean bằng StepScopeTestUtils

`StepScopeTestUtils.doInStepScope` phù hợp khi chỉ muốn kiểm tra một reader, processor, writer hoặc component scoped mà không cần chạy toàn bộ job.

Giả sử có một bean options nhận tham số:

```java
public class OrderImportOptions {

    private final String inputFile;
    private final String businessDate;

    public OrderImportOptions(String inputFile, String businessDate) {
        this.inputFile = inputFile;
        this.businessDate = businessDate;
    }

    public String inputFile() {
        return inputFile;
    }

    public String businessDate() {
        return businessDate;
    }
}
```

Khai báo scoped bean:

```java
@Configuration
public class OrderOptionsConfiguration {

    @Bean
    @StepScope
    OrderImportOptions orderImportOptions(
            @Value("#{jobParameters['inputFile']}") String inputFile,
            @Value("#{jobParameters['businessDate']}") String businessDate) {

        return new OrderImportOptions(inputFile, businessDate);
    }
}
```

Test:

```java
@SpringJUnitConfig({BatchInfrastructureConfiguration.class,
        OrderOptionsConfiguration.class})
class OrderImportOptionsTest {

    @Autowired
    private OrderImportOptions orderImportOptions;

    @Test
    void bindsValuesFromJobParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv", true)
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        StepExecution stepExecution = MetaDataInstanceFactory
                .createStepExecution(parameters);

        StepScopeTestUtils.doInStepScope(stepExecution, () -> {
            assertThat(orderImportOptions.inputFile())
                    .isEqualTo("src/test/resources/orders.csv");
            assertThat(orderImportOptions.businessDate())
                    .isEqualTo("2026-11-15");
            return null;
        });
    }
}
```

`BatchInfrastructureConfiguration` trong ví dụ đại diện cho cấu hình batch thực tế của ứng dụng, có đăng ký StepScope. Có thể thay bằng cấu hình `@EnableBatchProcessing` hoặc cấu hình Spring Boot đang sử dụng.

Điểm quan trọng là callback được chạy bên trong StepScope. Khi callback kết thúc, scope được đóng. Không nên gọi `orderImportOptions.inputFile()` trước hoặc sau callback.

## 6. Tạo StepExecution với JobParameters

`MetaDataInstanceFactory` có thể tạo một StepExecution gắn với JobExecution và JobParameters. Đây là cách đơn giản để kiểm tra late binding mà không cần khởi chạy JobLauncher.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "orders.csv", true)
        .addLong("tenantId", 42L, true)
        .toJobParameters();

StepExecution stepExecution = MetaDataInstanceFactory
        .createStepExecution(parameters);
```

Trong một bean có binding kiểu số:

```java
@Bean
@StepScope
TenantOptions tenantOptions(
        @Value("#{jobParameters['tenantId']}") Long tenantId) {
    return new TenantOptions(tenantId);
}
```

Test có thể xác nhận giá trị được chuyển thành kiểu Java mong đợi. Nếu tham số được lưu dưới kiểu không tương thích, hoặc key bị thiếu, việc resolve/conversion có thể thất bại khi scoped target được tạo.

Với tham số ngày tháng, mã định danh phức tạp hoặc giá trị có format riêng, có thể bind dưới dạng String rồi parse/validate trong factory method hoặc một component chuyên trách. Cách này giúp lỗi định dạng được báo rõ ràng và dễ test.

## 7. Test Step ExecutionContext binding

Một bean step-scoped thường nhận dữ liệu do partitioner hoặc step trước chuẩn bị. Test cần ghi key vào `stepExecution.getExecutionContext()`.

Ví dụ bean:

```java
@Bean
@StepScope
CustomerRangeOptions customerRangeOptions(
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new CustomerRangeOptions(minId, maxId);
}
```

Test:

```java
@Test
void bindsPartitionRangeFromStepExecutionContext() throws Exception {
    StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution();
    stepExecution.getExecutionContext().putLong("minId", 100L);
    stepExecution.getExecutionContext().putLong("maxId", 199L);

    StepScopeTestUtils.doInStepScope(stepExecution, () -> {
        assertThat(customerRangeOptions.minId()).isEqualTo(100L);
        assertThat(customerRangeOptions.maxId()).isEqualTo(199L);
        return null;
    });
}
```

Không đặt `minId` và `maxId` vào JobParameters nếu bean đang đọc `stepExecutionContext`. Cùng một key name nhưng hai nguồn dữ liệu là hai vùng khác nhau.

## 8. Test Job ExecutionContext binding

Job ExecutionContext thường chứa metadata được step trước ghi và promote để step sau sử dụng. Bean có thể đọc giá trị này qua `@JobScope` hoặc `@StepScope`.

Ví dụ:

```java
@Bean
@JobScope
BatchRunOptions batchRunOptions(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobExecutionContext['batchReference']}") String batchReference) {

    return new BatchRunOptions(businessDate, batchReference);
}
```

Test:

```java
@Test
void bindsJobExecutionContextValue() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    JobExecution jobExecution = MetaDataInstanceFactory
            .createJobExecution(parameters);
    jobExecution.getExecutionContext()
            .putString("batchReference", "BATCH-TEST-01");

    JobScopeTestUtils.doInJobScope(jobExecution, () -> {
        assertThat(batchRunOptions.businessDate())
                .isEqualTo("2026-11-15");
        assertThat(batchRunOptions.batchReference())
                .isEqualTo("BATCH-TEST-01");
        return null;
    });
}
```

Test cần đặt `batchReference` vào Job ExecutionContext trước khi truy cập bean. Nếu giá trị được tạo bởi step trước, có thể test riêng listener promotion hoặc chạy integration test để xác nhận giá trị thực sự được chuyển từ Step ExecutionContext sang Job ExecutionContext.

## 9. Test scope bằng TestExecutionListener

Nếu nhiều test method trong một class cần scope hoạt động, có thể dùng `StepScopeTestExecutionListener` hoặc `JobScopeTestExecutionListener`. Listener thiết lập execution context cho từng test method và đóng scope sau khi test kết thúc.

Ví dụ StepScope:

```java
@SpringJUnitConfig({BatchInfrastructureConfiguration.class,
        OrderOptionsConfiguration.class})
@TestExecutionListeners(
        listeners = StepScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class OrderOptionsListenerTest {

    @Autowired
    private OrderImportOptions orderImportOptions;

    public StepExecution getStepExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv", true)
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();
        return MetaDataInstanceFactory.createStepExecution(parameters);
    }

    @Test
    void resolvesParametersInsideStepScope() {
        assertThat(orderImportOptions.inputFile())
                .isEqualTo("src/test/resources/orders.csv");
    }
}
```

Listener có thể lấy StepExecution từ phương thức factory `getStepExecution()` trên test class. Nếu không cung cấp factory method, listener sử dụng metadata mặc định. Quy ước method và cách đăng ký cần đối chiếu với phiên bản Spring Batch Test đang dùng.

Tương tự, `JobScopeTestExecutionListener` có thể dùng với phương thức `getJobExecution()` để cung cấp JobExecution có JobParameters và Job ExecutionContext tùy chỉnh.

Khi dùng `@SpringBatchTest`, các listener hỗ trợ scope thường đã được đăng ký. Tránh đăng ký trùng listener nếu không cần thiết; nếu tự khai báo `@TestExecutionListeners`, cân nhắc `MERGE_WITH_DEFAULTS` để giữ các listener mặc định khác của Spring Test.

## 10. Test bằng @SpringBatchTest và JobLauncherTestUtils

Kiểm thử scoped bean riêng chỉ xác nhận late binding trong một scope giả lập. Để xác nhận job thực sự nhận tham số từ launcher, tạo scope, chạy step và lưu metadata đúng, hãy chạy integration test.

```java
@SpringBootTest
@SpringBatchTest
class OrderImportJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void launchesJobWithRuntimeParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "src/test/resources/orders.csv", true)
                .addString("businessDate", "2026-11-15", true)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        assertThat(execution.getJobParameters().getString("businessDate"))
                .isEqualTo("2026-11-15");
    }
}
```

Test này giả định ApplicationContext có một job được cấu hình cho `JobLauncherTestUtils`, datasource và schema Spring Batch đã sẵn sàng, cùng file input ở vị trí chỉ định. Nếu context có nhiều job, cần cấu hình rõ job được test theo API của phiên bản `JobLauncherTestUtils` đang sử dụng.

`@SpringBatchTest` cung cấp tiện ích kiểm thử, nhưng không tự tạo dữ liệu nghiệp vụ hoặc database schema. Test phải chuẩn bị các dependency đó.

## 11. Test riêng một step với JobLauncherTestUtils

Khi không cần chạy toàn bộ job, có thể khởi chạy một step bằng `launchStep`:

```java
@Test
void launchesImportStepWithParameters() throws Exception {
    JobParameters parameters = new JobParametersBuilder()
            .addString("inputFile", "src/test/resources/orders.csv", true)
            .addString("businessDate", "2026-11-15", true)
            .toJobParameters();

    JobExecution execution = jobLauncherTestUtils.launchStep(
            "importOrdersStep", parameters);

    StepExecution stepExecution = execution.getStepExecutions()
            .stream()
            .filter(step -> step.getStepName().equals("importOrdersStep"))
            .findFirst()
            .orElseThrow();

    assertThat(stepExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
}
```

`launchStep` hữu ích để tập trung vào reader/processor/writer và parameter binding của một step. Tuy nhiên, nó không kiểm tra flow của toàn job, dữ liệu được step trước tạo ra hoặc listener promotion giữa các step. Với những trường hợp đó, hãy chạy job đầy đủ.

## 12. Test dữ liệu được promote từ Step ExecutionContext

Giả sử step chuẩn bị ghi `validatedInputFile` vào Step ExecutionContext và `ExecutionContextPromotionListener` đưa key này sang Job ExecutionContext.

Test riêng listener có thể tạo StepExecution, đặt key và gọi listener theo lifecycle step. Tuy nhiên, cách chắc chắn hơn để xác nhận toàn bộ wiring là integration test có hai step:

```text
prepareFileStep
   |
   +-- Step ExecutionContext:
   |      validatedInputFile = /test/orders.csv
   |
   v
ExecutionContextPromotionListener
   |
   v
Job ExecutionContext:
   validatedInputFile = /test/orders.csv
   |
   v
importFileStep đọc #{jobExecutionContext['validatedInputFile']}
```

Bean ở step sau:

```java
@Bean
@StepScope
ValidatedFileOptions validatedFileOptions(
        @Value("#{jobExecutionContext['validatedInputFile']}") String inputFile) {
    return new ValidatedFileOptions(inputFile);
}
```

Trong integration test, khởi chạy job với dữ liệu test và xác nhận step sau nhận đúng file path. Nếu test chỉ đặt trực tiếp giá trị vào Job ExecutionContext, test đó chỉ xác nhận binding, không xác nhận promotion listener hoạt động.

## 13. Test tham số bị thiếu hoặc sai định dạng

Không phải lúc nào tham số cũng được truyền đầy đủ. Test nên xác nhận ứng dụng phản ứng rõ ràng khi thiếu key hoặc giá trị không hợp lệ.

Ví dụ validate trong factory method:

```java
@Bean
@StepScope
OrderImportOptions orderImportOptions(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    if (inputFile == null || inputFile.isBlank()) {
        throw new IllegalArgumentException("inputFile is required");
    }

    LocalDate parsedDate;
    try {
        parsedDate = LocalDate.parse(businessDate);
    } catch (DateTimeParseException exception) {
        throw new IllegalArgumentException(
                "businessDate must use ISO-8601 date format", exception);
    }

    return new OrderImportOptions(inputFile, parsedDate.toString());
}
```

Các trường hợp nên kiểm thử:

- Không truyền `inputFile`.
- `inputFile` là chuỗi rỗng hoặc chỉ có khoảng trắng.
- Không truyền `businessDate`.
- Ngày sai format.
- `tenantId` không thể chuyển đổi sang kiểu được inject.
- Key trong ExecutionContext bị thiếu hoặc sai tên.

Với giá trị bắt buộc, nên báo lỗi rõ ràng khi scoped target được tạo hoặc tại bước validate input. Không nên âm thầm dùng giá trị mặc định nếu điều đó có thể làm job xử lý nhầm dữ liệu.

## 14. Test giá trị mặc định và tùy chọn

Một số parameter có thể là tùy chọn. Khi đó cần định nghĩa hành vi mặc định rõ ràng và kiểm thử cả hai trường hợp có/không có parameter.

Ví dụ dùng SpEL Elvis operator:

```java
@Bean
@StepScope
ImportOptions importOptions(
        @Value("#{jobParameters['delimiter'] ?: ','}") String delimiter) {
    return new ImportOptions(delimiter);
}
```

Test nên kiểm tra:

- Có `delimiter` thì bean nhận đúng giá trị được truyền.
- Không có `delimiter` thì bean dùng dấu phẩy mặc định.
- Giá trị không được hỗ trợ bị từ chối nếu định dạng đầu vào không cho phép.

Chỉ dùng default cho parameter thực sự tùy chọn. Với file path, business date hoặc tenant ID bắt buộc, default có thể khiến job chạy nhầm dữ liệu.

## 15. Test kiểu dữ liệu của JobParameters

JobParameters có thể chứa các kiểu dữ liệu được Spring Batch hỗ trợ, chẳng hạn String, Long, Double, Date và các kiểu thời gian ở những phiên bản hỗ trợ. Bean có thể bind trực tiếp vào kiểu tương thích hoặc nhận String rồi chuyển đổi.

Ví dụ:

```java
@Bean
@StepScope
TenantOptions tenantOptions(
        @Value("#{jobParameters['tenantId']}") Long tenantId,
        @Value("#{jobParameters['dryRun']}") Boolean dryRun) {

    return new TenantOptions(tenantId, dryRun);
}
```

Test:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLong("tenantId", 42L, true)
        .addString("dryRun", "true", false)
        .toJobParameters();
```

Trong ví dụ này, `dryRun` được lưu là String; việc bind sang Boolean phụ thuộc conversion service và cấu hình thực tế. Nếu muốn tránh mơ hồ, hãy lưu parameter bằng kiểu được hỗ trợ tương ứng và test conversion theo đúng phiên bản đang dùng.

Không nên giả định hai parameter có cùng cách viết chuỗi sẽ có cùng kiểu. Test nên xác nhận cả giá trị lẫn kiểu sau khi binding.

## 16. Identifying và non-identifying parameters

`JobParameters` có thể chứa identifying và non-identifying values. Identifying parameters tham gia xác định JobInstance; non-identifying parameters không thay đổi identity.

Ví dụ:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "orders.csv", true)
        .addString("requestedBy", "integration-test", false)
        .toJobParameters();
```

Khi test parameter binding, nên xác nhận:

- Bean nhận đúng identifying values.
- Bean nhận đúng non-identifying values nếu nó sử dụng chúng.
- Hai lần chạy với cùng identifying parameters thuộc cùng JobInstance theo semantics của repository.
- Thay identifying parameter tạo JobInstance khác.
- Khi restart, identifying values giữ nguyên.

Không thêm timestamp hoặc UUID mới làm identifying parameter trong test restart nếu mục tiêu là tiếp tục cùng JobInstance. Tuy nhiên, non-identifying parameter cũng không nên thay đổi tùy tiện nếu nó ảnh hưởng đến logic nghiệp vụ của bean.

## 17. Test nhiều execution với cùng scoped proxy

Một scoped proxy có thể được inject vào test class. Khi mỗi scope được kích hoạt với execution khác nhau, target bean phải được tạo/resolve theo context tương ứng.

Ví dụ:

```java
@Test
void sameProxyResolvesDifferentStepParameters() throws Exception {
    StepExecution first = MetaDataInstanceFactory.createStepExecution(
            new JobParametersBuilder()
                    .addString("businessDate", "2026-11-15", true)
                    .toJobParameters());

    StepExecution second = MetaDataInstanceFactory.createStepExecution(
            new JobParametersBuilder()
                    .addString("businessDate", "2026-11-16", true)
                    .toJobParameters());

    String firstDate = StepScopeTestUtils.doInStepScope(first,
            () -> orderImportOptions.businessDate());

    String secondDate = StepScopeTestUtils.doInStepScope(second,
            () -> orderImportOptions.businessDate());

    assertThat(firstDate).isEqualTo("2026-11-15");
    assertThat(secondDate).isEqualTo("2026-11-16");
}
```

Test này giúp phát hiện bean giữ giá trị cũ ngoài scope hoặc vô tình dùng state từ execution trước. Không giữ reference tới target object của scope đã đóng; hãy truy cập qua proxy trong callback của từng execution.

## 18. Test parameter binding trong partitioning

Trong partitioning, mỗi worker có `StepExecution` và Step ExecutionContext riêng. Cùng một bean definition `@StepScope` có thể nhận `minId`, `maxId` khác nhau ở mỗi partition.

Ví dụ test hai phạm vi:

```java
StepExecution north = MetaDataInstanceFactory.createStepExecution();
north.getExecutionContext().putString("region", "NORTH");
north.getExecutionContext().putLong("minId", 1L);
north.getExecutionContext().putLong("maxId", 100L);

StepExecution south = MetaDataInstanceFactory.createStepExecution();
south.getExecutionContext().putString("region", "SOUTH");
south.getExecutionContext().putLong("minId", 101L);
south.getExecutionContext().putLong("maxId", 200L);
```

Chạy bean trong mỗi scope và xác nhận region/range tương ứng. Test này kiểm tra parameter binding của worker. Để kiểm tra partitioner tạo đúng các context, cần test partitioner riêng; để kiểm tra manager điều phối worker, cần integration test cho partitioned step.

`@StepScope` tạo target theo StepExecution, nhưng không tự làm các dependency singleton bên trong thread-safe. Test binding tuần tự không thay thế test concurrency.

## 19. Test restart và parameter binding

Restart tạo `JobExecution` mới cho cùng `JobInstance`. Các scoped bean được tạo trong context của execution mới, vì vậy cần kiểm tra chúng nhận đúng parameters và ExecutionContext đã được khôi phục.

Một integration test restart thường có các bước:

1. Khởi chạy job với identifying parameters cố định.
2. Làm cho một step thất bại có kiểm soát sau khi checkpoint được lưu.
3. Xác nhận JobExecution đầu tiên là `FAILED`.
4. Khắc phục nguyên nhân lỗi trong test.
5. Restart cùng JobInstance bằng identifying parameters cũ hoặc `JobOperator`.
6. Xác nhận JobExecution mới được tạo.
7. Xác nhận scoped bean nhận đúng JobParameters và context cần thiết.
8. Xác nhận reader/writer khôi phục checkpoint và kết quả không bị ghi trùng.

Test scope riêng chỉ chứng minh cách resolve giá trị trong một execution giả lập. Nó không chứng minh JobRepository lưu/khôi phục context đúng hoặc step flow restart đúng. Những điều đó cần integration test.

## 20. Kiểm tra lỗi scope và SpEL

Một số lỗi thường gặp khi parameter binding:

| Triệu chứng | Nguyên nhân có thể gặp | Hướng xử lý |
|---|---|---|
| `ScopeNotActiveException` | Truy cập scoped bean ngoài JobScope/StepScope. | Dùng scope utility/listener hoặc khởi chạy job/step. |
| Không resolve được `jobParameters` | Chưa có JobExecution đang hoạt động hoặc bean không có scope phù hợp. | Dùng `@StepScope`/`@JobScope` và thiết lập execution context. |
| SpEL trả về `null` | Sai key hoặc giá trị chưa được đặt trong context. | Kiểm tra đúng tên key và đúng nguồn context. |
| Giá trị chuyển đổi sai kiểu | Kiểu JobParameter không tương thích với kiểu method argument. | Dùng kiểu rõ ràng hoặc parse/validate String. |
| Bean giữ giá trị cũ giữa hai test | Target scoped bean bị giữ reference hoặc scope không được đóng đúng. | Truy cập qua proxy trong từng scope và để utility quản lý lifecycle. |
| Step context không thấy giá trị job context | Đặt key sai phạm vi hoặc thiếu promotion từ step trước. | Đặt đúng JobExecutionContext hoặc test promotion flow. |
| `@JobScope` không resolve step key | Job scope không có một StepExecution cụ thể. | Dùng `@StepScope` nếu cần Step ExecutionContext. |
| Test chạy riêng được nhưng launch job thất bại | Test utility không kiểm tra toàn bộ wiring, flow hoặc repository. | Bổ sung integration test với `JobLauncherTestUtils`. |
| Test lỗi do metadata cũ | JobRepository dùng chung giữa test hoặc JobInstance đã tồn tại. | Dùng parameter test riêng và dọn metadata có kiểm soát. |

Khi điều tra, hãy xác định lỗi xảy ra lúc tạo ApplicationContext, lúc mở scope hay lúc resolve từng expression. Ba thời điểm này thường dẫn đến nguyên nhân khác nhau.

## 21. Những điểm cần ghi nhớ

- Parameter binding thường dùng SpEL để lấy dữ liệu từ JobParameters, Job ExecutionContext và Step ExecutionContext.
- `@StepScope` phù hợp khi bean cần tham số riêng của step/partition; `@JobScope` phù hợp với dữ liệu chung của một JobExecution.
- Scoped bean được truy cập qua proxy; target và late-bound values chỉ được resolve khi scope tương ứng hoạt động.
- `MetaDataInstanceFactory` tạo JobExecution/StepExecution test; phải đặt tham số và context đúng nguồn trước khi gọi bean.
- `StepScopeTestUtils` và `JobScopeTestUtils` chạy callback trong scope tương ứng.
- `StepScopeTestExecutionListener` và `JobScopeTestExecutionListener` có thể kích hoạt scope cho test method.
- `@SpringBatchTest` và `JobLauncherTestUtils` phù hợp để kiểm tra job/step thực sự được khởi chạy với JobParameters.
- Đặt giá trị vào Step ExecutionContext không làm nó tự xuất hiện trong Job ExecutionContext; cần promotion hoặc cơ chế truyền rõ ràng.
- Test bean riêng không thay thế integration test cho flow, transaction, metadata promotion và restart.
- Kiểm thử cả parameter hợp lệ, thiếu, sai định dạng, sai kiểu và giá trị mặc định.
- Giữ identifying parameters ổn định khi test restart cùng JobInstance.
- Test partition cần tạo StepExecution riêng với context riêng cho từng worker.
- Không giữ target object của scoped bean sau khi scope đóng và không giả định scope tự bảo đảm thread safety cho dependency dùng chung.

Kiểm thử parameter binding cần mô phỏng đúng vòng đời thực thi mà bean phụ thuộc. Hãy dùng scope utility hoặc listener khi test một component, và dùng `JobLauncherTestUtils` khi cần xác nhận cả job flow. Khi JobParameters và ExecutionContext được đặt đúng nơi, test sẽ phát hiện sớm lỗi sai key, sai kiểu, thiếu context và late binding không hoạt động trước khi batch chạy trong môi trường thật.
