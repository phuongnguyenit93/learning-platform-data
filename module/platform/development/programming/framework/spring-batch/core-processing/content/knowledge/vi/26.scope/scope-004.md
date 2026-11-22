# Bean scoped theo job

Trong Spring Batch, một bean đôi khi cần tồn tại xuyên suốt nhiều step của cùng một lần chạy job. Ví dụ, nhiều step cùng cần dùng cấu hình xuất báo cáo lấy từ `JobParameters`, một client được cấu hình theo tenant, hoặc một đối tượng cung cấp các đường dẫn và tùy chọn dành riêng cho lần chạy hiện tại.

Nếu dùng singleton thông thường, bean có thể được chia sẻ giữa nhiều job execution cùng lúc. Nếu dùng `@StepScope`, mỗi step execution lại có một instance riêng, dù một số cấu hình cần được dùng chung qua nhiều step. **`@JobScope`** giải quyết trường hợp này bằng cách tạo một instance bean cho mỗi `JobExecution` và giữ instance đó trong suốt vòng đời execution tương ứng.

Job scope cũng hỗ trợ late binding: giá trị từ `JobParameters` và `JobExecutionContext` được đưa vào bean khi bean thực sự được tạo trong lúc job đang chạy. Tuy nhiên, job-scoped bean chỉ quản lý vòng đời dependency. Nó không thay thế `ExecutionContext`, không tự lưu state qua restart và không làm cho các field mutable trở nên an toàn khi nhiều flow truy cập đồng thời.

## 1. Ba phạm vi bean thường gặp

Spring Batch cung cấp các scope quan trọng để tạo bean theo vòng đời thực thi:

| Scope | Vòng đời instance | Trường hợp phù hợp |
|---|---|---|
| Singleton | Một instance trong application context | Service stateless, repository, mapper dùng chung |
| `@StepScope` | Một instance cho mỗi `StepExecution` | Reader/writer giữ cursor, checkpoint hoặc state riêng của step |
| `@JobScope` | Một instance cho mỗi `JobExecution` | Cấu hình hoặc collaborator cần dùng chung qua nhiều step trong cùng job execution |

Ví dụ, một job có ba step:

```text
dailyExportJob
  JobExecution 101
    prepareStep
    exportCustomersStep
    exportOrdersStep
```

Một bean `@JobScope` được tạo tối đa một lần cho `JobExecution 101` và có thể được dùng bởi các step trong execution đó. Nếu cùng job chạy đồng thời cho một ngày nghiệp vụ khác, execution thứ hai có instance job-scoped riêng.

Mỗi step execution vẫn có thể có các bean `@StepScope` riêng. Hai scope phục vụ các vòng đời khác nhau và có thể được dùng cùng nhau trong một job.

## 2. Job scope được tạo theo JobExecution

`JobInstance` và `JobExecution` không phải cùng một khái niệm:

- `JobInstance` đại diện cho một công việc nghiệp vụ, được xác định bởi job name và identifying `JobParameters`.
- `JobExecution` đại diện cho một lần thực thi cụ thể của instance đó.

Job scope gắn với một lần chạy đang hoạt động, tức là `JobExecution`. Nếu một execution thất bại và được restart, Spring Batch tạo `JobExecution` mới cho cùng `JobInstance`. Bean `@JobScope` được tạo lại cho execution mới.

```text
JobInstance: dailyExportJob / businessDate=2026-11-15

  JobExecution 101 (FAILED)
    Job-scoped bean instance A
    prepareStep
    exportStep

  JobExecution 108 (restart, COMPLETED)
    Job-scoped bean instance B
    tiếp tục theo metadata/checkpoint đã lưu
```

Instance B không phải object A được giữ lại trong bộ nhớ. Nếu cần khôi phục trạng thái sau restart, hãy lưu trạng thái cần thiết vào `ExecutionContext` hoặc một kho dữ liệu bền vững. Không dựa vào field của job-scoped bean để nhớ tiến độ qua các execution.

## 3. Khi nào nên dùng `@JobScope`?

Job scope phù hợp khi một bean cần có cấu hình riêng cho từng job execution và được nhiều step trong execution đó sử dụng.

Các ví dụ thường gặp:

- Một `JobRunSettings` chứa ngày nghiệp vụ, tenant và thư mục output được lấy từ job parameters.
- Một collaborator được cấu hình theo input file hoặc output version của lần chạy hiện tại.
- Một service wrapper giữ thông tin cấu hình bất biến cần chia sẻ giữa nhiều step.
- Một bean đọc giá trị trong job execution context sau khi step trước đã chuẩn bị và lưu giá trị đó.
- Một đối tượng tạo tên output key hoặc resource path nhất quán trong cùng execution.

Không nên dùng job scope chỉ vì bean được gọi từ một job. Service stateless như mapper, validator thuần hoặc repository thường có thể là singleton. Reader có cursor, writer có vị trí ghi hoặc component cần state riêng cho từng step thường phù hợp với `@StepScope` hơn.

## 4. Khai báo bean bằng `@JobScope`

Có thể đặt `@JobScope` trên phương thức `@Bean` để bean được tạo theo job execution.

Ví dụ một class giữ cấu hình export:

```java
public class JobRunSettings {

    private final String businessDate;
    private final Long tenantId;
    private final String outputDirectory;

    public JobRunSettings(
            String businessDate,
            Long tenantId,
            String outputDirectory) {
        this.businessDate = businessDate;
        this.tenantId = tenantId;
        this.outputDirectory = outputDirectory;
    }

    public String getBusinessDate() {
        return businessDate;
    }

    public Long getTenantId() {
        return tenantId;
    }

    public String getOutputDirectory() {
        return outputDirectory;
    }
}
```

Khai báo bean:

```java
@Bean
@JobScope
public JobRunSettings jobRunSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") Long tenantId,
        @Value("#{jobParameters['outputDirectory']}") String outputDirectory) {

    return new JobRunSettings(businessDate, tenantId, outputDirectory);
}
```

Khi job execution đang hoạt động và bean được sử dụng lần đầu, Spring tạo target instance với các giá trị của execution hiện tại. Một execution khác có thể nhận một target instance khác với bộ tham số riêng.

Trong ứng dụng thực tế, nên xác thực các tham số bắt buộc trước khi sử dụng. Nếu `tenantId` hoặc đường dẫn output bị thiếu, hãy trả lỗi cấu hình rõ ràng thay vì để lỗi xuất hiện muộn trong writer.

## 5. Late binding với JobParameters

Late binding nghĩa là giá trị được resolve khi scoped bean được tạo trong execution, thay vì lúc application context khởi động.

Ví dụ:

```java
@Bean
@JobScope
public JobRunSettings jobRunSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") Long tenantId,
        @Value("#{jobParameters['outputDirectory']}") String outputDirectory) {
    return new JobRunSettings(businessDate, tenantId, outputDirectory);
}
```

Các expression đọc tham số của job execution đang chạy:

| Expression | Giá trị |
|---|---|
| `#{jobParameters['businessDate']}` | Job parameter có tên `businessDate` |
| `#{jobParameters['tenantId']}` | Job parameter có tên `tenantId` |
| `#{jobExecution}` | `JobExecution` hiện tại |
| `#{jobExecutionContext['preparedInputFile']}` | Giá trị trong job execution context |

`JobParameters` mô tả đầu vào của lần chạy và identifying parameters góp phần xác định `JobInstance`. Job parameters không phải nơi để cập nhật tiến độ xử lý. Nếu cần lưu giá trị phát sinh trong lúc job chạy, hãy dùng job execution context hoặc step execution context phù hợp.

## 6. Inject job-scoped bean vào singleton

Các bean `@Bean` mặc định thường là singleton. Một singleton có thể phụ thuộc vào một job-scoped bean, nhưng Spring cần sử dụng scoped proxy để trì hoãn việc lấy target cho tới khi có job context hoạt động.

Ví dụ một tasklet singleton dùng `JobRunSettings`:

```java
@Bean
public Tasklet prepareExportTasklet(JobRunSettings settings) {
    return (contribution, chunkContext) -> {
        Path outputDirectory = Path.of(settings.getOutputDirectory());
        Files.createDirectories(outputDirectory);
        return RepeatStatus.FINISHED;
    };
}
```

Khi Spring tạo tasklet singleton, dependency được inject là proxy của job-scoped bean. Khi tasklet thực sự gọi `settings.getOutputDirectory()` trong một job execution đang chạy, proxy tìm target instance tương ứng với execution đó.

Không được gọi method của proxy trong lúc application context đang khởi tạo nếu chưa có job execution. Khi đó không có job context để resolve target và ứng dụng có thể nhận lỗi kiểu `ScopeNotActiveException` hoặc lỗi tương đương.

## 7. Cấu hình một job dùng bean scoped theo job

Ví dụ hoàn chỉnh hơn với một tasklet sử dụng cấu hình theo execution:

```java
@Configuration
public class DailyExportConfiguration {

    @Bean
    @JobScope
    public JobRunSettings jobRunSettings(
            @Value("#{jobParameters['businessDate']}") String businessDate,
            @Value("#{jobParameters['tenantId']}") Long tenantId,
            @Value("#{jobParameters['outputDirectory']}") String outputDirectory) {
        return new JobRunSettings(businessDate, tenantId, outputDirectory);
    }

    @Bean
    public Tasklet prepareExportTasklet(JobRunSettings settings) {
        return (contribution, chunkContext) -> {
            Path directory = Path.of(settings.getOutputDirectory());
            Files.createDirectories(directory);
            return RepeatStatus.FINISHED;
        };
    }

    @Bean
    public Step prepareExportStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            Tasklet prepareExportTasklet) {
        return new StepBuilder("prepareExportStep", jobRepository)
                .tasklet(prepareExportTasklet, transactionManager)
                .build();
    }

    @Bean
    public Job dailyExportJob(
            JobRepository jobRepository,
            Step prepareExportStep) {
        return new JobBuilder("dailyExportJob", jobRepository)
                .start(prepareExportStep)
                .build();
    }
}
```

Ví dụ dùng API builder của Spring Batch 5. Các import và phần cấu hình hạ tầng như `@EnableBatchProcessing`, datasource, transaction manager và `JobRepository` được lược bớt để tập trung vào job scope.

Trong ứng dụng, cần bảo đảm các tham số được truyền khi launch job và bean chỉ được sử dụng trong lúc execution đang hoạt động.

## 8. Đọc dữ liệu từ JobExecutionContext

Ngoài job parameters, job-scoped bean có thể nhận giá trị từ `JobExecutionContext`. Điều này hữu ích khi step trước tạo ra một giá trị để các step sau dùng chung.

Ví dụ, step chuẩn bị file input lưu đường dẫn vào job context:

```java
public class PrepareInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = chunkContext
                .getStepContext()
                .getStepExecution()
                .getJobExecution();

        jobExecution.getExecutionContext()
                .putString("preparedInputFile", "staging/orders-input.csv");

        return RepeatStatus.FINISHED;
    }
}
```

Một job-scoped bean được sử dụng trong step tiếp theo có thể late-bind giá trị này:

```java
@Bean
@JobScope
public PreparedInputSettings preparedInputSettings(
        @Value("#{jobExecutionContext['preparedInputFile']}") String inputFile) {
    return new PreparedInputSettings(inputFile);
}
```

Điểm cần chú ý là job-scoped target được tạo khi được truy cập lần đầu và sau đó được giữ cho execution. Vì vậy, nếu bean được khởi tạo trước khi key `preparedInputFile` được ghi, field đã inject không tự cập nhật khi context thay đổi. Hãy bảo đảm bean chỉ được sử dụng lần đầu sau khi step chuẩn bị đã lưu key, hoặc đọc giá trị động từ `JobExecution` tại thời điểm cần dùng.

Với dữ liệu cần tồn tại qua restart, hãy bảo đảm job execution context được cập nhật và lưu qua `JobRepository` theo lifecycle của step. Việc thay đổi field của job-scoped bean không tự động cập nhật execution context.

## 9. Job scope không phải ExecutionContext

Hai cơ chế này có mục đích khác nhau:

| Tiêu chí | `@JobScope` | `ExecutionContext` |
|---|---|---|
| Bản chất | Vòng đời và phạm vi của bean | Kho key/value lưu trạng thái thực thi |
| Dữ liệu tồn tại trong bao lâu? | Trong JobExecution đang hoạt động | Được lưu bền vững trong metadata repository |
| Dùng qua nhiều step? | Có, target bean dùng chung trong execution | Job context dùng được qua các step |
| Tồn tại qua restart? | Không, target bean được tạo lại | Có, nếu context đã được lưu |
| Ví dụ | Cấu hình export theo tenant | `lastProcessedId`, output path đã tạo |

Không nên dùng một field như `settings.lastProcessedId` để thay thế checkpoint. Khi process dừng, object trong heap mất đi. Hãy lưu checkpoint trong step execution context hoặc cơ chế bền vững khác.

## 10. Phân biệt JobScope và StepScope

`@JobScope` và `@StepScope` thường được dùng cùng nhau nhưng không thay thế nhau.

Ví dụ một job nhập dữ liệu có hai step:

```text
importJob
  validateStep
  importStep
```

Một `JobRunSettings` chứa `businessDate` và `tenantId` có thể được dùng chung bởi cả hai step, nên phù hợp với job scope. Một `FlatFileItemReader` giữ line count và file pointer chỉ thuộc `importStep`, nên phù hợp với step scope.

Ví dụ:

```java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    FlatFileItemReader<OrderInput> reader = new FlatFileItemReader<>();
    reader.setName("orderReader");
    reader.setResource(new FileSystemResource(inputFile));
    reader.setSaveState(true);
    reader.setLineMapper(orderLineMapper());
    return reader;
}
```

Reader này có state riêng cho `StepExecution` và hỗ trợ checkpoint. Không cần chuyển reader thành job-scoped chỉ vì đường dẫn input đến từ job parameter; `@StepScope` vẫn có thể late-bind `jobParameters`.

Quy tắc thực tế:

- Dùng `@JobScope` cho cấu hình hoặc collaborator có vòng đời toàn job execution.
- Dùng `@StepScope` cho state gắn với một step execution, nhất là reader/writer.
- Dùng singleton cho component stateless và thread-safe.
- Dùng `ExecutionContext` để lưu state cần khôi phục sau restart.

## 11. Job-scoped bean không tự thread-safe

Một job execution có thể chứa parallel flow hoặc các step sử dụng nhiều thread. Vì job-scoped bean được chia sẻ trong phạm vi execution, nhiều nhánh có thể truy cập cùng target instance.

Nếu bean chỉ chứa cấu hình bất biến như business date, tenant ID và output directory, việc chia sẻ thường đơn giản. Nhưng nếu bean có field mutable như counter, list, buffer hoặc current item, các thread có thể cập nhật đồng thời và tạo race condition.

Ví dụ không an toàn:

```java
@JobScope
public class JobRunState {
    private final List<String> processedIds = new ArrayList<>();

    public void add(String id) {
        processedIds.add(id);
    }
}
```

Nếu nhiều flow gọi `add()` cùng lúc, `ArrayList` không an toàn luồng. Đổi sang collection concurrent cũng không giải quyết vấn đề checkpoint, thứ tự nghiệp vụ hoặc tính bền vững qua restart.

Nên giữ job-scoped bean gần như immutable. State riêng của mỗi step đặt trong step execution context hoặc một store có transaction; dữ liệu tổng hợp được ghi theo khóa riêng và tổng hợp sau khi các flow hoàn tất.

## 12. Giới hạn khi dùng job scope trong parallel hoặc partitioned step

Spring Batch có những giới hạn thực tế khi sử dụng job scope trong multi-threaded step hoặc partitioned step. Các cơ chế này có thể tạo thread hoặc execution worker mà framework không thiết lập job context theo cách mà một job-scoped proxy cần ở mọi thread. Vì vậy, không nên mặc định rằng một job-scoped bean có thể được truy cập an toàn từ mọi thread do ứng dụng tự tạo.

Đặc biệt cần thận trọng với:

- Step chạy nhiều thread.
- Partition worker được chạy qua `TaskExecutor`.
- Remote worker hoặc tiến trình khác.
- Parallel flow dùng executor bất đồng bộ.
- Thread do ứng dụng tự tạo bên trong processor/writer.

Khi cần cấu hình cho worker, hãy cân nhắc truyền dữ liệu qua `StepExecution`/`ExecutionContext`, tạo bean `@StepScope` riêng cho từng worker step hoặc dùng immutable configuration được tạo và truyền rõ ràng. Kiểm tra khả năng hỗ trợ của phiên bản Spring Batch và mô hình executor cụ thể trước khi dùng job scope trong đường chạy song song.

Không dùng job-scoped bean như một vùng chia sẻ để đồng bộ các worker. Nếu cần chia sẻ dữ liệu, hãy dùng database, message broker hoặc cấu trúc concurrency có thiết kế rõ ràng.

## 13. Job scope không phải transaction scope

Một bean job-scoped có thể tồn tại qua nhiều transaction và nhiều step trong cùng job execution. Việc bean còn tồn tại không có nghĩa một transaction database cũng còn mở trong suốt thời gian đó.

Ví dụ, `JobRunSettings` có thể được sử dụng trong `prepareStep`, `importStep` và `summaryStep`. Mỗi step/chunk vẫn có transaction riêng theo cấu hình. Không giữ JDBC connection hoặc transaction-bound resource trong field của job-scoped bean để dùng xuyên qua các step.

Hãy để `JdbcTemplate`, repository hoặc transaction-aware collaborator lấy resource theo transaction hiện hành. Không lưu `Connection`, `ResultSet`, Hibernate session hoặc file handle dài hạn trong job-scoped configuration bean trừ khi vòng đời resource được quản lý rõ ràng và phù hợp.

## 14. Khởi tạo lazy và lỗi khi truy cập ngoài job

Job-scoped target chỉ có thể được tạo khi Spring Batch đã đăng ký một job context đang hoạt động. Vì thế:

- Application context có thể tạo proxy khi khởi động mà chưa tạo target bean.
- Target được tạo khi proxy được gọi trong job execution.
- Gọi proxy từ một `CommandLineRunner`, controller hoặc test không có job context có thể gây lỗi scope chưa hoạt động.
- Gọi proxy trong constructor hoặc `@PostConstruct` của singleton có thể xảy ra quá sớm.

Nếu một component cần đọc cấu hình trước khi job chạy, hãy dùng cấu hình singleton hoặc đọc `JobParameters` ở launcher/service rồi truyền chúng khi khởi chạy. Không cố truy cập job-scoped target ngoài vòng đời job.

## 15. Proxy và kiểu class của bean

Các annotation `@JobScope` thường sử dụng scoped proxy để bean ở scope ngắn hơn có thể được inject vào bean singleton. Với proxy dựa trên class, class đích cần có thể được proxy; các class hoặc method `final` có thể gây vấn đề với CGLIB.

Khuyến nghị:

- Trả về kiểu class cụ thể trong phương thức `@Bean` khi cần proxy class.
- Tránh class `final` hoặc method cần proxy là `final`.
- Không gọi method nội bộ theo cách bỏ qua proxy nếu logic phụ thuộc vào scope.
- Không tự tạo target bằng `new` rồi mong Spring quản lý job scope.
- Dùng bean do Spring quản lý và inject proxy qua dependency injection.

Ví dụ `JobRunSettings` ở trên là class thông thường với getter không `final`, phù hợp cho proxy kiểu class. Nếu ứng dụng chọn interface-based proxy, cần cấu hình và kiểu inject nhất quán.

## 16. Bật job scope trong hạ tầng Spring Batch

Trong cấu hình Spring Batch dựa trên annotation, `@EnableBatchProcessing` đăng ký hạ tầng cần thiết, bao gồm các scope dành cho batch như job scope và step scope. Spring Boot với cấu hình Batch tự động cũng thường thiết lập hạ tầng tương ứng.

Ví dụ:

```java
@Configuration
@EnableBatchProcessing
public class BatchInfrastructureConfiguration {
    // JobRepository, transaction manager và các cấu hình batch liên quan.
}
```

Không đăng ký scope trùng lặp hoặc tự tạo một `JobScope` riêng nếu hạ tầng đã cung cấp. Nếu ứng dụng dùng cấu hình Batch tùy chỉnh, hãy xác nhận `JobScope` đã được đăng ký trong application context.

Khi cấu hình job scope không hoạt động, kiểm tra:

- Hạ tầng Spring Batch có được bật đúng cách không?
- Bean có được Spring quản lý qua `@Bean`/component scan không?
- Annotation `@JobScope` có được đặt trên đúng bean definition không?
- Bean có bị tạo hoặc gọi trước khi job context hoạt động không?
- Job được khởi chạy qua `JobLauncher` và execution context có được đăng ký đúng không?

## 17. Sử dụng JobExecutionContext động

Một job-scoped bean có thể nhận context qua `@Value`, nhưng vì target chỉ được tạo một lần cho execution, giá trị inject là giá trị tại thời điểm target được khởi tạo. Nếu key thay đổi sau đó, field không tự cập nhật.

Với giá trị chỉ có sau một step, có hai cách:

1. Đảm bảo job-scoped bean chỉ được khởi tạo lần đầu trong step sau khi key đã được ghi vào job context.
2. Nếu cần đọc giá trị thay đổi theo thời gian, truy cập `JobExecution`/`ExecutionContext` trong method tại thời điểm sử dụng thay vì snapshot bằng constructor injection.

Ví dụ đọc context động trong tasklet:

```java
public class ReadPreparedInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = chunkContext
                .getStepContext()
                .getStepExecution()
                .getJobExecution();

        String inputFile = jobExecution.getExecutionContext()
                .getString("preparedInputFile");

        // Dùng inputFile cho bước hiện tại.
        return RepeatStatus.FINISHED;
    }
}
```

Nếu giá trị phải được dùng qua nhiều step, hãy cân nhắc `ExecutionContextPromotionListener` khi dữ liệu đang nằm trong step context. Job context là phạm vi phù hợp cho giá trị cần chia sẻ ở cấp job.

## 18. Job-scoped bean và restart

Khi job restart, một `JobExecution` mới được tạo cho cùng `JobInstance`. Bean `@JobScope` của execution cũ đã kết thúc vòng đời và target mới sẽ được tạo cho execution mới.

Các giá trị lấy từ identifying `JobParameters` thường giống nhau nếu restart đúng instance. Tuy nhiên, field mutable mà ứng dụng đã thay đổi trong target cũ không tự được khôi phục.

Ví dụ:

- `businessDate` lấy từ job parameter: có thể resolve lại với cùng giá trị khi restart.
- `lastProcessedId` lưu trong field bean: mất khi execution cũ kết thúc.
- `lastProcessedId` lưu trong `StepExecutionContext`: có thể khôi phục từ checkpoint đã commit.
- `preparedInputFile` lưu trong `JobExecutionContext`: có thể được đọc lại nếu metadata đã được lưu.

Vì vậy, job scope giúp cô lập cấu hình và object theo execution, còn `ExecutionContext` chịu trách nhiệm lưu trạng thái cần restart. Hai cơ chế nên được dùng đúng mục đích.

## 19. Kiểm thử job-scoped bean

Kiểm thử job scope cần có job context hoạt động. Nếu gọi trực tiếp một proxy `@JobScope` trong unit test mà không thiết lập scope, test có thể gặp lỗi không có active job context.

Spring Batch Test cung cấp các tiện ích để tạo job execution context trong test. Có thể dùng `@SpringBatchTest` cùng `JobLauncherTestUtils` để chạy job thật trong test configuration.

Ví dụ kiểm tra một job-scoped settings bean thông qua job:

```java
@SpringBatchTest
@SpringJUnitConfig(DailyExportConfiguration.class)
class JobScopedSettingsTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Test
    void usesParametersForCurrentJobExecution() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-15", true)
                .addLong("tenantId", 42L, true)
                .addString("outputDirectory", "build/test-output", false)
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

Đây là khung minh họa; test configuration cần cung cấp job và hạ tầng test phù hợp. Để kiểm tra giá trị settings thực tế, có thể cho tasklet ghi lại giá trị đã resolve vào một test probe hoặc kiểm tra artifact được tạo theo đúng tham số.

Với test tập trung vào scope mà không chạy toàn job, Spring Batch Test có `JobScopeTestUtils.doInJobScope(...)` trong các phiên bản hỗ trợ. Có thể dùng nó để thực thi callback trong một `JobExecution` test đã tạo. Cần theo chữ ký API của phiên bản thư viện test đang dùng.

## 20. Kiểm thử sự cô lập giữa hai JobExecution

Một mục tiêu quan trọng của job scope là không để cấu hình của job này rò sang job khác.

Có thể kiểm tra:

1. Khởi chạy job với `tenantId=42` và output directory A.
2. Xác nhận bean dùng đúng giá trị của execution thứ nhất.
3. Khởi chạy một execution khác với `tenantId=84` và output directory B.
4. Xác nhận execution thứ hai nhận target bean và giá trị riêng.
5. Xác nhận không có state mutable của execution đầu bị giữ lại trong execution sau.

Nếu hai job chạy đồng thời, kiểm tra cả hai execution để phát hiện singleton state vô tình chứa tham số theo job. Đây là một trong những lý do nên đặt cấu hình theo execution vào job-scoped bean thay vì field của singleton service.

## 21. Các lỗi thường gặp

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| `ScopeNotActiveException` | Proxy được gọi ngoài job execution hoặc quá sớm | Chỉ truy cập target trong lúc job đang chạy |
| Giá trị `@Value` là null | Sai tên job parameter/context key hoặc key chưa tồn tại khi target được tạo | Kiểm tra tên key và thời điểm khởi tạo |
| Bean không được tạo lại khi restart | Hiểu nhầm job scope tồn tại theo JobInstance | Nhớ rằng scope gắn với JobExecution mới |
| Field state mất sau restart | Dùng bean field thay cho ExecutionContext | Lưu checkpoint vào context hoặc store bền vững |
| Hai step có state đè nhau | Dùng job scope cho state thực ra thuộc step | Chuyển sang `@StepScope` hoặc step context riêng |
| Hai flow cập nhật cùng field gây race | Job-scoped bean được chia sẻ nhưng mutable | Giữ bean immutable hoặc dùng store/thread-safe design |
| Worker thread không resolve được job scope | Job context không được thiết lập trong thread/worker đó | Tránh job scope trong đường chạy song song không được hỗ trợ; truyền context rõ ràng |
| Proxy không hoạt động với class final | Class/method không thể được CGLIB proxy | Dùng class có thể proxy hoặc interface proxy phù hợp |
| Singleton giữ target job-scoped quá sớm | Gọi method proxy trong constructor hoặc `@PostConstruct` | Chỉ dereference trong execution lifecycle |
| Giá trị context cũ vẫn được dùng | Bean được tạo trước khi context key thay đổi | Khởi tạo sau khi key có sẵn hoặc đọc context động |

## 22. Quy tắc thiết kế thực tế

Khi quyết định dùng scope nào, hãy xem vòng đời dữ liệu:

1. Giá trị có giống nhau trong toàn application không? Nếu có, singleton thường phù hợp.
2. Giá trị có riêng cho một job execution và cần được dùng qua nhiều step không? Cân nhắc `@JobScope`.
3. Giá trị có riêng cho một step execution như cursor hoặc output position không? Dùng `@StepScope`.
4. Giá trị có cần tồn tại qua restart không? Lưu trong `ExecutionContext` hoặc store bền vững.
5. Bean có bị nhiều thread truy cập đồng thời không? Giữ cấu hình bất biến hoặc thiết kế concurrency rõ ràng.
6. Giá trị có được tạo sau khi job bắt đầu không? Kiểm tra thời điểm target job-scoped được khởi tạo.

Một thiết kế thường dễ vận hành là:

- Singleton cho service stateless và repository.
- Job-scoped bean cho immutable job configuration.
- Step-scoped bean cho reader/writer có state riêng.
- Job/step execution context cho checkpoint và dữ liệu cần khôi phục.
- Database/outbox cho trạng thái nghiệp vụ cần bền vững hoặc chia sẻ giữa worker.

## 23. Những nguyên tắc cần nhớ

- `@JobScope` tạo một target bean cho mỗi `JobExecution` đang chạy.
- Restart tạo `JobExecution` mới, nên job-scoped target được tạo lại dù `JobInstance` vẫn giữ nguyên.
- Job scope phù hợp với cấu hình/collaborator dùng chung qua nhiều step trong cùng execution.
- `@Value` hỗ trợ late binding từ `jobParameters`, `jobExecution` và `jobExecutionContext`.
- Scoped proxy cho phép inject job-scoped bean vào singleton; chỉ gọi target khi job context đang hoạt động.
- `@JobScope` quản lý vòng đời bean, không lưu state bền vững và không thay thế `ExecutionContext`.
- Dùng `@StepScope` cho state riêng của reader/writer hoặc một step execution.
- Field mutable trong job-scoped bean có thể bị nhiều flow/thread truy cập; ưu tiên cấu hình immutable.
- Thận trọng với job scope trong multi-threaded hoặc partitioned step vì job context không được thiết lập tự động trong mọi worker thread.
- Nếu bind `jobExecutionContext` khi target được tạo, giá trị được inject là snapshot tại thời điểm đó; key thay đổi sau không tự cập nhật field.
- Không giữ connection, cursor hoặc transaction trong bean chỉ vì bean sống suốt job.
- Kiểm thử scope trong một job execution thực hoặc dùng tiện ích JobScopeTestUtils phù hợp với phiên bản.

`@JobScope` giúp các step trong cùng một lần chạy chia sẻ cấu hình theo execution mà không làm lẫn tham số giữa những job chạy đồng thời. Khi giữ job-scoped bean cho cấu hình bất biến, dùng step scope cho state cục bộ và lưu checkpoint trong `ExecutionContext`, ứng dụng có thể tận dụng đúng vòng đời của Spring Batch mà vẫn restart và vận hành an toàn.
