# JobScope và StepScope

Trong Spring Batch, **JobScope** và **StepScope** là hai scope giúp tạo bean theo vòng đời thực thi của Job hoặc Step. Chúng đặc biệt hữu ích khi một bean cần nhận dữ liệu chỉ có khi Job bắt đầu, chẳng hạn JobParameters, Job ExecutionContext hoặc Step ExecutionContext.

Hai scope này giải quyết một vấn đề phổ biến: bean được khai báo trong Spring ApplicationContext thường là singleton và được tạo trước khi Job chạy, trong khi dữ liệu của một lần thực thi chỉ có sau khi Spring Batch tạo JobExecution hoặc StepExecution.

- **JobScope** tạo một target bean cho mỗi JobExecution. Các Step trong cùng lần chạy Job có thể sử dụng cùng instance đó.
- **StepScope** tạo một target bean cho mỗi StepExecution. Mỗi lần thực thi Step có state và instance riêng.

Một quy tắc thực tế: dùng JobScope cho dữ liệu hoặc object dùng chung ở cấp một lần chạy Job; dùng StepScope cho reader, processor, writer hoặc component cần tham số và trạng thái riêng của Step. Với reader cần late binding, StepScope thường là lựa chọn phù hợp.

## 1. Vì sao cần JobScope và StepScope?

Spring tạo singleton bean khi khởi tạo ApplicationContext. Thời điểm đó Job có thể chưa được chạy, nên chưa có JobParameters, JobExecution hoặc StepExecution để inject.

Ví dụ cấu hình reader cần đường dẫn file từ JobParameters:

~~~java
@Bean
public FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {
    // ...
}
~~~

Nếu bean là singleton thông thường, Spring có thể cố resolve biểu thức jobParameters khi ApplicationContext khởi tạo, lúc chưa có JobExecution. Bean không thể lấy đúng dữ liệu runtime.

Khi dùng StepScope:

~~~java
@Bean
@StepScope
public FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {
    // ...
}
~~~

Spring tạo scoped proxy lúc cấu hình ứng dụng, sau đó tạo target reader khi StepExecution thực sự hoạt động. Tại thời điểm đó JobParameters đã sẵn sàng và biểu thức có thể được resolve.

Đây là cơ chế **late binding**: giá trị được gắn vào bean khi scope tương ứng đang hoạt động, thay vì lúc ApplicationContext khởi động.

## 2. JobScope là gì?

JobScope giới hạn vòng đời target bean theo một JobExecution.

Một JobInstance có thể có nhiều JobExecution nếu Job bị restart. Mỗi JobExecution là một lần thực thi cụ thể và có Job ExecutionContext riêng. Job-scoped bean được tạo riêng cho JobExecution đang chạy đó.

~~~text
ApplicationContext
      |
      +--> JobExecution A
      |       |
      |       +--> Job-scoped bean A
      |       |
      |       +--> Step 1
      |       +--> Step 2
      |       +--> Step 3
      |
      +--> JobExecution B (restart)
              |
              +--> Job-scoped bean B
              |
              +--> Step 1
              +--> Step 2
              +--> Step 3
~~~

Các Step trong cùng JobExecution có thể truy cập cùng target bean JobScope. Khi một JobExecution khác bắt đầu, Spring Batch tạo target bean theo scope của lần chạy mới.

JobScope hữu ích khi:

- Nhiều Step cần cùng một cấu hình runtime.
- Một object cần giữ trạng thái dùng chung trong phạm vi JobExecution.
- Bean cần đọc JobParameters hoặc Job ExecutionContext.
- Muốn tránh dùng singleton mutable để lưu state riêng của một lần chạy Job.

JobScope không phải một vùng lưu trạng thái bền vững thay cho JobRepository. Nếu cần restart sau khi process dừng, dữ liệu cần khôi phục phải được lưu trong ExecutionContext hoặc kho lưu trữ bền vững. Một field trong Job-scoped bean chỉ tồn tại trong bộ nhớ của lần thực thi hiện tại.

## 3. Khai báo bean với @JobScope

Spring Batch cung cấp annotation @JobScope để khai báo bean theo scope job.

Ví dụ một object giữ cấu hình nhập dữ liệu dùng chung giữa các Step:

~~~java
public record ImportSettings(
        String businessDate,
        String tenantId,
        String mode) {
}
~~~

Khai báo bean:

~~~java
@Bean
@JobScope
public ImportSettings importSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") String tenantId,
        @Value("#{jobParameters['mode']}") String mode) {

    return new ImportSettings(
            businessDate,
            tenantId,
            mode);
}
~~~

Các Step có thể inject ImportSettings:

~~~java
@Bean
public Step validateStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // Dùng cấu hình của JobExecution hiện tại.
    // ...
}
~~~

~~~java
@Bean
public Step importStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // Dùng cùng cấu hình Job-scoped.
    // ...
}
~~~

Mỗi JobExecution nhận một ImportSettings được resolve từ JobParameters của lần chạy đó. Các Step trong cùng JobExecution có thể dùng cùng target instance.

Nếu chỉ cần đọc JobParameters ở một Step duy nhất, không nhất thiết phải tạo bean JobScope. StepScope thường đơn giản và giới hạn vòng đời rõ hơn.

## 4. StepScope là gì?

StepScope giới hạn target bean theo một StepExecution.

Một Step có thể được chạy trong nhiều JobExecution khác nhau. Mỗi lần thực thi tạo StepExecution riêng, có ExecutionContext, trạng thái và counter riêng. Step-scoped bean được tạo riêng theo StepExecution đó.

~~~text
JobExecution
    |
    +--> StepExecution A
    |       |
    |       +--> Step-scoped reader A
    |       +--> Step-scoped processor A
    |
    +--> StepExecution B
            |
            +--> Step-scoped reader B
            +--> Step-scoped processor B
~~~

StepScope phù hợp với:

- ItemReader có resource hoặc query phụ thuộc tham số runtime.
- ItemProcessor cần tham số riêng của Step hoặc partition.
- ItemWriter cần đường dẫn output hoặc chế độ ghi riêng.
- Custom component giữ state chỉ có ý nghĩa trong một StepExecution.
- Bean cần đọc Step ExecutionContext hoặc Job ExecutionContext tại thời điểm Step chạy.

Ví dụ một Step đọc file riêng:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {
    // Tạo reader cho file của lần chạy hiện tại.
    // ...
}
~~~

Khi Step chạy, reader nhận Resource từ JobParameters. Khi StepExecution kết thúc, target bean thuộc StepScope được hủy theo lifecycle của scope.

## 5. Khai báo bean với @StepScope

Ví dụ reader nhận đường dẫn file và một cờ cấu hình:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile,
        @Value("#{jobParameters['skipHeader']}") Boolean skipHeader) {

    FlatFileItemReaderBuilder<CustomerInput> builder =
            new FlatFileItemReaderBuilder<CustomerInput>()
                    .name("customerReader")
                    .resource(inputFile)
                    .delimited()
                    .names("id", "name", "email")
                    .targetType(CustomerInput.class)
                    .saveState(true);

    if (Boolean.TRUE.equals(skipHeader)) {
        builder.linesToSkip(1);
    }

    return builder.build();
}
~~~

Ở đây:

- @StepScope trì hoãn việc tạo target reader tới lúc Step hoạt động.
- jobParameters cung cấp đầu vào của JobExecution.
- saveState(true) cho phép reader lưu checkpoint để hỗ trợ restart.
- Tên reader ổn định giúp phân biệt state trong ExecutionContext.

Một bean StepScope vẫn có thể đọc JobParameters. Điểm khác biệt là vòng đời target bean được gắn với StepExecution, không phải JobExecution.

## 6. So sánh JobScope và StepScope

| Tiêu chí | JobScope | StepScope |
|---|---|---|
| Vòng đời target bean | Một JobExecution | Một StepExecution |
| Chia sẻ giữa các Step | Có, trong cùng JobExecution | Không, mỗi StepExecution có target riêng |
| Đọc JobParameters | Có | Có |
| Đọc Job ExecutionContext | Có | Có |
| Đọc Step ExecutionContext | Không có một Step cụ thể để tham chiếu | Có |
| Dùng cho reader riêng của Step | Thường không phải lựa chọn đầu tiên | Phù hợp |
| Dùng cho cấu hình chung của Job | Phù hợp | Mỗi Step sẽ có instance riêng |
| Restart JobExecution mới | Target bean mới | Target bean mới cho StepExecution được chạy |
| State trong field | Chia sẻ trong phạm vi JobExecution | Chia sẻ trong phạm vi StepExecution |

Chọn scope theo phạm vi dữ liệu cần truy cập và vòng đời của object. Không nên chọn JobScope chỉ vì bean cần đọc JobParameters; StepScope cũng đọc được JobParameters và thường phù hợp hơn cho các thành phần chunk.

## 7. Các biểu thức SpEL thường dùng

Spring Batch cung cấp các ngữ cảnh để late-bind dữ liệu vào bean.

| Biểu thức | Giá trị |
|---|---|
| jobParameters['inputFile'] | Tham số đầu vào của Job |
| jobExecutionContext['key'] | Key trong Job ExecutionContext |
| stepExecutionContext['key'] | Key trong Step ExecutionContext |
| jobExecution | JobExecution hiện tại |
| stepExecution | StepExecution hiện tại |
| stepExecution.stepName | Tên Step hiện tại |
| stepExecution.jobExecutionId | ID JobExecution của Step |

Ví dụ đọc tham số file:

~~~java
@Value("#{jobParameters['inputFile']}")
Resource inputFile
~~~

Đọc trạng thái chung của Job:

~~~java
@Value("#{jobExecutionContext['reportId']}")
Long reportId
~~~

Đọc trạng thái riêng của Step:

~~~java
@Value("#{stepExecutionContext['fromId']}")
Long fromId
~~~

Các biểu thức này cần được resolve trong scope đang hoạt động. StepScope có ngữ cảnh của cả JobExecution và StepExecution, nên có thể đọc cả jobParameters, jobExecutionContext và stepExecutionContext.

JobScope không có StepExecution cụ thể. Không dùng job-scoped bean để đọc stepExecutionContext.

## 8. Truyền dữ liệu từ JobParameters vào StepScope

JobParameters được tạo trước khi Job chạy:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/customers.csv", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("mode", "FULL", false)
        .toJobParameters();

JobExecution execution =
        jobLauncher.run(customerImportJob, parameters);
~~~

Reader StepScope có thể nhận các giá trị đó:

~~~java
@Bean
@StepScope
public FlatFileItemReader<CustomerInput> customerReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new FlatFileItemReaderBuilder<CustomerInput>()
            .name("customerReader")
            .resource(inputFile)
            .delimited()
            .names("id", "name", "email")
            .targetType(CustomerInput.class)
            .saveState(true)
            .build();
}
~~~

Nếu một giá trị xác định đơn vị công việc độc lập, hãy cân nhắc đánh dấu identifying trong JobParameters. JobParameters xác định JobInstance; scope chỉ quyết định khi nào bean nhận giá trị đó.

Không dùng field trong JobScope hoặc StepScope để thay thế identifying parameters. Một biến trong bean không tham gia xác định JobInstance.

## 9. Dùng StepScope để đọc Step ExecutionContext

Partitioner hoặc Step trước có thể ghi các giá trị vào Step ExecutionContext. Worker Step dùng StepScope để nhận đúng giá trị cho StepExecution của nó.

Ví dụ reader đọc một khoảng ID:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['fromId']}") Long fromId,
        @Value("#{stepExecutionContext['toId']}") Long toId) {

    return buildOrderReader(dataSource, fromId, toId);
}
~~~

Mỗi partition có StepExecution context riêng. Khi worker partition 0 chạy, reader nhận cận của partition 0; khi worker partition 1 chạy, reader nhận cận của partition 1.

Đây là một lý do quan trọng để reader của partition dùng StepScope. Nếu dùng singleton stateful reader, các worker có thể chia sẻ cùng field và ghi đè phạm vi hoặc vị trí đọc của nhau.

## 10. Dùng JobScope cho dữ liệu dùng chung giữa nhiều Step

Giả sử Job có ba Step:

1. validateFileStep xác định cấu hình nhập.
2. importCustomersStep nhập dữ liệu.
3. createSummaryStep tạo báo cáo.

Một object cấu hình bất biến theo JobParameters có thể được dùng chung:

~~~java
@Bean
@JobScope
public ImportSettings importSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['tenantId']}") String tenantId) {

    return new ImportSettings(businessDate, tenantId, "FULL");
}
~~~

Các Step inject bean này:

~~~java
@Bean
public Step validateFileStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // ...
}
~~~

~~~java
@Bean
public Step importCustomersStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // ...
}
~~~

~~~java
@Bean
public Step createSummaryStep(
        JobRepository jobRepository,
        ImportSettings importSettings) {
    // ...
}
~~~

Cùng một JobExecution sử dụng cùng cấu hình. Nếu Job restart tạo JobExecution mới, bean JobScope mới được tạo theo tham số của lần chạy đó.

Nên ưu tiên object cấu hình bất biến. Nếu nhiều Step cùng sửa một Job-scoped mutable object, thứ tự thực thi và concurrency có thể ảnh hưởng kết quả.

## 11. Truyền dữ liệu giữa Step qua Job ExecutionContext

JobScope không tự động chuyển mọi biến local của Step trước sang Step sau. Cách chuẩn để truyền trạng thái bền vững giữa các Step là Job ExecutionContext.

Ví dụ Step tạo báo cáo ghi reportId vào Step ExecutionContext:

~~~java
public class CreateReportTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        StepExecution stepExecution = chunkContext
                .getStepContext()
                .getStepExecution();

        stepExecution.getExecutionContext()
                .putLong("reportId", 12345L);

        return RepeatStatus.FINISHED;
    }
}
~~~

Dùng ExecutionContextPromotionListener để promote key lên Job ExecutionContext:

~~~java
@Bean
public ExecutionContextPromotionListener reportPromotionListener() {
    ExecutionContextPromotionListener listener =
            new ExecutionContextPromotionListener();

    listener.setKeys(new String[] {"reportId"});
    return listener;
}
~~~

Đăng ký listener trên Step tạo báo cáo:

~~~java
@Bean
public Step createReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ExecutionContextPromotionListener reportPromotionListener) {

    return new StepBuilder("createReportStep", jobRepository)
            .tasklet(new CreateReportTasklet(), transactionManager)
            .listener(reportPromotionListener)
            .build();
}
~~~

Step sau có thể đọc Job ExecutionContext bằng StepScope:

~~~java
@Bean
@StepScope
public ItemWriter<ReportRow> reportWriter(
        @Value("#{jobExecutionContext['reportId']}") Long reportId) {
    return new ReportWriter(reportId);
}
~~~

Ở đây StepScope được dùng vì writer thuộc một Step cụ thể; biểu thức lấy reportId từ Job ExecutionContext. Dữ liệu được promotion có thể tồn tại qua restart nhờ JobRepository.

Không đọc stepExecutionContext của Step trước từ một Step khác. Mỗi StepExecution có context riêng; muốn chia sẻ trạng thái cần promotion hoặc cập nhật Job ExecutionContext có chủ đích.

## 12. JobScope và StepScope không phải nơi lưu checkpoint

Scope quản lý vòng đời object trong bộ nhớ. ExecutionContext quản lý trạng thái có thể lưu vào JobRepository.

Ví dụ một bean StepScope có field:

~~~java
@Bean
@StepScope
public ItemProcessor<OrderInput, Order> processor() {
    return new ItemProcessor<>() {
        private long processed;

        @Override
        public Order process(OrderInput input) {
            processed++;
            return convert(input);
        }
    };
}
~~~

Field processed tồn tại trong target bean của StepExecution hiện tại. Khi process kết thúc hoặc ứng dụng dừng, field không tự động được lưu để restart.

Nếu cần khôi phục counter, hãy lưu vào Step ExecutionContext hoặc metadata phù hợp. Nếu chỉ cần thống kê trong lần chạy hiện tại, có thể dùng field hoặc Micrometer counter nhưng phải hiểu vòng đời và concurrency.

Tương tự, field trong JobScope không phải dữ liệu bền vững. Không dùng chúng làm checkpoint thay cho ExecutionContext.

## 13. Proxy và late binding hoạt động thế nào?

Khi Spring gặp bean có @JobScope hoặc @StepScope, nó tạo một scoped proxy để các bean khác có thể inject trước khi Job/Step chạy.

~~~text
ApplicationContext khởi động
        |
        v
Tạo scoped proxy
        |
        v
Step/Job được cấu hình
        |
        v
JobExecution / StepExecution bắt đầu
        |
        v
Scope được kích hoạt
        |
        v
Proxy tìm hoặc tạo target bean
        |
        v
Resolve JobParameters / ExecutionContext
        |
        v
Gọi method trên target
~~~

Proxy cho phép cấu hình Step có thể inject reader StepScope dù reader thật chưa được tạo. Khi Step thực thi, proxy chuyển lời gọi tới target bean gắn với StepExecution hiện tại.

Điều này cũng giải thích vì sao không nên gọi trực tiếp scoped bean trong lúc ApplicationContext đang khởi tạo hoặc từ một luồng không có Batch execution context. Khi scope chưa hoạt động, Spring không thể resolve target.

Các annotation @JobScope và @StepScope thường dùng class-based proxy. Với class final hoặc method không thể override, cần chú ý giới hạn proxy; có thể inject qua interface phù hợp hoặc thiết kế class không final.

## 14. Khác biệt với singleton và prototype

| Scope | Vòng đời |
|---|---|
| singleton | Một instance trong ApplicationContext |
| prototype | Instance mới mỗi lần container được yêu cầu tạo bean |
| job | Một target instance cho mỗi JobExecution |
| step | Một target instance cho mỗi StepExecution |

Singleton phù hợp với service stateless như validator hoặc mapper không giữ state theo lần chạy.

Prototype không thay thế StepScope. Prototype tạo instance khi bean được yêu cầu, nhưng không tự gắn instance với StepExecution, cũng không tự late-bind JobParameters hay ExecutionContext.

JobScope và StepScope hiểu context do Spring Batch quản lý, nhờ đó target bean được tạo và hủy theo đúng execution lifecycle.

## 15. JobScope có thể dùng cho reader không?

Có thể khai báo reader JobScope nếu reader thực sự được chia sẻ ở cấp JobExecution và không cần StepExecution context. Tuy nhiên, reader thông thường thuộc về một Step và có state riêng theo Step, nên StepScope thường phù hợp hơn.

Ví dụ không nên dùng JobScope cho một reader có checkpoint riêng của từng Step:

~~~java
@Bean
@JobScope
public FlatFileItemReader<Customer> customerReader(...) {
    // Reader state có thể bị chia sẻ giữa các Step
    // trong cùng JobExecution.
}
~~~

Nếu hai Step cùng dùng reader này, chúng có thể truy cập cùng target bean và cùng state. Điều đó dễ gây xung đột vị trí đọc, lifecycle mở/đóng hoặc checkpoint.

Hãy dùng StepScope cho reader của từng Step. Chỉ dùng JobScope nếu object thực sự là tài nguyên dùng chung cấp Job, có lifecycle và concurrency được thiết kế rõ ràng.

## 16. JobScope trong multi-threaded và partitioned Step

JobScope hữu ích trong Job tuần tự, nhưng cần thận trọng trong các mô hình chạy song song. Spring Batch cảnh báo việc sử dụng JobScope trong multi-threaded hoặc partitioned Step vì context có thể không được truyền tới các luồng do executor hoặc cơ chế phân phối quản lý.

Một Job-scoped bean có thể được nhiều worker truy cập cùng lúc. Nếu bean giữ mutable state, các worker có thể ghi đè dữ liệu hoặc gặp race condition.

Với partitioning:

- Mỗi worker có StepExecution và Step ExecutionContext riêng.
- Dùng StepScope để lấy fromId, toId hoặc partition key.
- Không dùng JobScope để giữ state riêng cho từng partition.
- Chỉ chia sẻ object JobScope khi object an toàn cho concurrency và scope context được hỗ trợ trong kiến trúc đang dùng.

Với multi-threaded Step, nhiều thread có thể xử lý cùng một StepExecution. StepScope không tự tạo một bean cho mỗi thread; target bean được gắn với StepExecution và có thể được chia sẻ giữa các thread trong Step đó. Stateful reader hoặc processor cần thread-safe hoặc dùng thiết kế phân vùng phù hợp.

Không giả định scoped proxy tự động làm bean thread-safe. Scope chỉ quản lý vòng đời và truy cập target, không cung cấp đồng bộ hóa cho các field mutable.

## 17. Đặt @StepScope trên bean nào?

Các bean thường phù hợp với StepScope:

| Bean | Khi nào dùng StepScope |
|---|---|
| ItemReader | Resource, query hoặc partition range phụ thuộc runtime; reader có state |
| ItemProcessor | Quy tắc xử lý phụ thuộc tham số riêng của Step |
| ItemWriter | Đường dẫn output, batch ID hoặc cấu hình ghi riêng |
| Tasklet | Logic cần late-bind tham số hoặc state của Step |
| Listener | Cần đọc StepExecution/ExecutionContext khi Step chạy |

Không cần đặt @StepScope cho mọi bean. Service stateless dùng chung có thể giữ singleton để đơn giản và tiết kiệm object.

Ví dụ một processor stateless chỉ gọi service:

~~~java
@Bean
public ItemProcessor<OrderInput, Order> orderProcessor(
        OrderValidationService validationService) {
    return input -> {
        validationService.validate(input);
        return convert(input);
    };
}
~~~

Nếu processor không cần dữ liệu runtime hoặc state riêng, singleton thông thường là đủ.

## 18. Đặt @JobScope trên bean nào?

JobScope phù hợp với object cấu hình hoặc phối hợp dùng chung giữa các Step trong một JobExecution.

Ví dụ:

- ImportSettings chứa business date, tenant và mode.
- ReportContext giữ một mã report dùng chung trong một JobExecution.
- Job-level configuration được resolve từ JobParameters.
- Một object bất biến tổng hợp các tham số đầu vào.

Không dùng JobScope cho:

- Reader có vị trí đọc riêng của một Step.
- State riêng của partition.
- Cache mutable không có kiểm soát concurrency.
- Dữ liệu cần tồn tại qua restart nhưng chỉ được giữ trong field.
- Bean cần truy cập stepExecutionContext.

Nếu dữ liệu cần được chia sẻ giữa các Step và phải tồn tại qua restart, hãy lưu trong Job ExecutionContext hoặc database; JobScope chỉ cung cấp instance trong bộ nhớ.

## 19. Lỗi scope chưa active

Nếu một scoped bean được truy cập khi không có JobExecution hoặc StepExecution hiện tại, Spring có thể báo lỗi tương tự:

~~~text
Scope 'step' is not active for the current thread
Scope 'job' is not active for the current thread
~~~

Các nguyên nhân thường gặp:

- Gọi bean StepScope trong constructor hoặc @PostConstruct của singleton.
- Gọi scoped bean từ application startup listener trước khi Job chạy.
- Tạo thread riêng rồi truy cập scoped bean mà không có Batch context.
- Unit test gọi bean mà không kích hoạt StepScope hoặc JobScope.
- Dùng JobScope trong topology song song không truyền được context.

Cách xử lý:

1. Chỉ truy cập scoped bean trong lifecycle của Job/Step.
2. Inject scoped proxy thay vì tự lấy target trước khi scope hoạt động.
3. Dùng StepScope cho dữ liệu riêng của Step.
4. Với worker thread hoặc partition, kiểm tra cơ chế truyền execution context.
5. Trong test, kích hoạt scope bằng Spring Batch test support hoặc tạo StepExecution/JobExecution phù hợp.

Không tự tạo static holder để giữ JobExecution hoặc StepExecution toàn cục. Cách đó có thể làm lẫn context giữa các lần chạy đồng thời.

## 20. Kiểm thử JobScope và StepScope

Khi kiểm thử scoped bean, cần tạo execution context tương ứng. Spring Batch test support cung cấp các listener để kích hoạt scope trong test.

Với test cấu hình Spring Batch, có thể dùng @SpringBatchTest:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchConfiguration.class)
class CustomerReaderScopeTest {

    @Autowired
    private ItemReader<CustomerInput> customerReader;

    public StepExecution getStepExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "/tmp/customers.csv", true)
                .toJobParameters();

        JobExecution jobExecution =
                new JobExecution(1L, parameters);

        StepExecution stepExecution =
                new StepExecution("importStep", jobExecution);

        stepExecution.getExecutionContext()
                .putString("source", "test");

        return stepExecution;
    }

    @Test
    void readerIsAvailableInsideStepScope() throws Exception {
        assertNotNull(customerReader);
        // Có thể gọi reader sau khi scope đã được kích hoạt.
    }
}
~~~

Spring Batch test support có thể dùng phương thức getStepExecution() để tạo context cho StepScope. Cần cung cấp resource test tồn tại nếu test thực sự mở và đọc file.

Đối với JobScope, test có thể cung cấp JobExecution test context thông qua JobScopeTestExecutionListener hoặc chạy Job bằng JobLauncherTestUtils để scope được kích hoạt theo lifecycle thực tế.

### Kiểm thử late binding

Nên xác nhận các giá trị được resolve đúng:

- JobParameters của JobExecution hiện tại.
- Job ExecutionContext đã lưu trước Step.
- Step ExecutionContext của Step hiện tại.
- Hai JobExecution khác nhau nhận target bean khác nhau.
- Hai StepExecution khác nhau nhận Step-scoped target riêng.

### Kiểm thử restart

Nếu bean scope giữ state trong field, test restart cần xác nhận state bền vững được khôi phục từ ExecutionContext hoặc database. Không kỳ vọng field của target bean cũ tồn tại qua JobExecution mới.

## 21. Những lỗi thường gặp

### Inject JobParameters vào singleton

Singleton được tạo trước khi Job chạy nên không có runtime context. Dùng JobScope hoặc StepScope để late-bind.

### Dùng JobScope cho reader riêng của Step

JobScope chia sẻ target trong cùng JobExecution. Reader có thể dùng chung state giữa các Step. Dùng StepScope cho reader của từng Step.

### Dùng StepScope để chia sẻ một object giữa các Step

Mỗi StepExecution có target riêng. Nếu cần dữ liệu dùng chung, dùng JobScope cho object phù hợp hoặc Job ExecutionContext cho trạng thái cần lưu bền vững.

### Nghĩ scope là checkpoint

Field trong target bean không tự động được lưu khi chunk commit. Dùng ItemStream và ExecutionContext cho reader state.

### Nghĩ StepScope tạo một instance cho mỗi thread

StepScope tạo target theo StepExecution. Trong multi-threaded Step, nhiều thread có thể cùng truy cập target. Cần xử lý thread safety.

### Nghĩ JobScope an toàn trong mọi partition topology

Context có thể không được truyền đúng tới worker thread hoặc tiến trình. Dùng StepScope cho partition-specific state và kiểm thử topology.

### Truy cập scoped bean trước khi scope active

Bean không có JobExecution/StepExecution hiện tại để resolve. Chỉ sử dụng trong lifecycle phù hợp.

### Lưu mutable state dùng chung trong JobScope

Nhiều Step hoặc worker có thể cùng thay đổi state. Ưu tiên object bất biến hoặc cơ chế lưu trạng thái có đồng bộ và bền vững.

### Dùng prototype thay cho StepScope

Prototype không cung cấp late binding và lifecycle theo StepExecution. Dùng scope của Spring Batch khi cần execution context.

## 22. Quy trình chọn scope cho một bean

Khi khai báo bean trong Spring Batch, hãy hỏi:

1. Bean có cần JobParameters hoặc ExecutionContext không?
2. Bean thuộc về một JobExecution hay một StepExecution?
3. Nhiều Step trong cùng Job có cần dùng cùng target instance không?
4. Bean có state thay đổi theo lần chạy không?
5. State đó chỉ cần trong bộ nhớ hay phải khôi phục sau restart?
6. Bean có được truy cập từ nhiều thread hoặc partition không?
7. Bean có thể là singleton stateless không?

Có thể dùng quy tắc sau:

| Nhu cầu | Lựa chọn |
|---|---|
| Service stateless, không cần runtime context | singleton |
| Cấu hình dùng chung cho một JobExecution | JobScope |
| Reader/processor/writer riêng của một StepExecution | StepScope |
| Tham số đầu vào đã biết khi launch | JobParameters, inject qua scope nếu cần |
| Checkpoint riêng của reader | Step ExecutionContext và ItemStream |
| Dữ liệu cần Step sau sử dụng | Job ExecutionContext hoặc promotion |
| State riêng của từng partition | StepScope trong worker Step |

JobScope và StepScope giúp bean nhận dữ liệu đúng thời điểm và có vòng đời phù hợp với Spring Batch. JobScope gắn target bean với một JobExecution và có thể chia sẻ giữa các Step của lần chạy đó. StepScope gắn target bean với một StepExecution, phù hợp cho reader và các thành phần cần state hoặc tham số riêng của Step. Hãy dùng ExecutionContext cho checkpoint bền vững, dùng JobParameters cho đầu vào của Job và luôn xem xét concurrency khi scoped bean được truy cập từ nhiều worker.
