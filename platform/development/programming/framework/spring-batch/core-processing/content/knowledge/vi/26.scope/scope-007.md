# Reader hoặc writer cần step scope

Trong Spring Batch, reader và writer thường là các component có trạng thái gắn với một lần thực thi Step. Reader có thể giữ vị trí đọc hiện tại, writer có thể giữ trạng thái mở file hoặc checkpoint, và cả hai thường cần nhận các giá trị chỉ có khi Job/Step bắt đầu, chẳng hạn tên file, ngày xử lý hoặc phạm vi dữ liệu của partition. Nếu khai báo những component này như singleton thông thường, nhiều lần chạy Step có thể dùng chung một instance và vô tình chia sẻ state.

@StepScope cho phép Spring tạo target bean trong phạm vi một StepExecution. Cơ chế này cũng hỗ trợ late binding: bean chỉ được khởi tạo khi Step đang chạy, lúc đó các giá trị từ JobParameters, Job ExecutionContext và Step ExecutionContext mới có thể được đưa vào factory method. Vì vậy, reader hoặc writer cần dữ liệu runtime riêng cho từng StepExecution thường nên được khai báo step-scoped.

## 1. Spring bean mặc định là singleton

Nếu không khai báo scope khác, bean Spring thường có singleton scope. Spring tạo một instance trong ApplicationContext và dùng lại instance đó ở các nơi inject bean.

Ví dụ reader singleton:

~~~java
@Bean
FlatFileItemReader<Order> orderReader() {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource("/data/orders.csv"))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .build();
}
~~~

Cấu hình trên phù hợp khi resource và cấu hình thực sự cố định, đồng thời component có thể được dùng lại an toàn. Nhưng reader thường giữ state như vị trí hiện tại trong file, số item đã đọc, trạng thái mở resource và các checkpoint. Nếu cùng một instance được dùng cho nhiều StepExecution, state có thể bị chia sẻ ngoài ý muốn.

Writer cũng có thể giữ file output đang mở, buffer hoặc trạng thái ghi. Nếu hai JobExecution dùng chung writer instance, chúng có thể ghi vào cùng resource hoặc ảnh hưởng lifecycle open/close của nhau.

Vấn đề không chỉ nằm ở field mutable do ứng dụng khai báo. Reader/writer có thể giữ state bên trong thư viện, delegate hoặc resource mà ứng dụng không nhìn thấy trực tiếp. Vì vậy, cần xem xét lifecycle thực tế của component.

## 2. Step scope là gì?

Step scope là một scope của Spring được Spring Batch cung cấp. Bean trong scope này có target instance gắn với StepExecution hiện tại. Khi một StepExecution khác chạy, Spring tạo target instance khác cho cùng định nghĩa bean.

~~~text
ApplicationContext
      |
      +--> Bean definition: orderReader
                 |
                 v
          Scoped proxy được inject
                 |
       +---------+---------+
       |                   |
       v                   v
 StepExecution A      StepExecution B
       |                   |
       v                   v
 Target reader A      Target reader B
       |                   |
       v                   v
 State/checkpoint A   State/checkpoint B
~~~

Scoped proxy cho phép các bean singleton như Job và Step definition tham chiếu tới reader/writer step-scoped ngay từ lúc ApplicationContext được tạo. Proxy sẽ tìm target instance phù hợp khi được gọi trong một StepExecution đang hoạt động.

Annotation @StepScope là cách khai báo tiện dụng cho scope step. Nó thường được dùng trên phương thức @Bean khai báo reader hoặc writer:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader() {
    // Target reader được tạo khi Step scope đang hoạt động.
}
~~~

Scope này không có nghĩa bean tồn tại mãi theo Job hoặc toàn ứng dụng. Target được quản lý theo vòng đời StepExecution và được hủy khi scope tương ứng kết thúc.

## 3. Vì sao reader thường cần step scope?

Reader thường là component có state. Ví dụ:

- FlatFileItemReader giữ vị trí dòng hiện tại và trạng thái resource.
- JdbcPagingItemReader giữ thông tin trang hoặc vị trí đọc cần thiết.
- JpaPagingItemReader quản lý page và trạng thái đọc.
- Custom ItemReader có thể giữ last ID, offset, cursor hoặc token phân trang.
- Reader nhận phạm vi partition cần biết start/end của partition hiện tại.

Nếu reader được dùng cho nhiều lần thực thi, một instance singleton có thể giữ checkpoint hoặc resource của lần chạy trước. Điều đó gây ra các lỗi như đọc tiếp từ vị trí cũ, dùng nhầm file hoặc chia sẻ state giữa các partition.

Ví dụ Job chạy mỗi ngày với một file khác nhau. Tên file là JobParameter:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

Mỗi JobExecution có thể truyền một inputFile khác. Reader được tạo trong Step scope nên nhận đúng giá trị của execution đang chạy.

Nếu bỏ @StepScope, Spring sẽ cố tạo bean singleton khi khởi tạo ApplicationContext. Tại thời điểm đó chưa có StepExecution cụ thể để phân giải jobParameters['inputFile']; late binding không thể hoạt động đúng.

## 4. Vì sao writer thường cần step scope?

Writer cũng có thể giữ state và resource:

- FlatFileItemWriter giữ file output, writer buffer và trạng thái ghi.
- Writer phân trang hoặc ghi theo batch có thể giữ counter/checkpoint.
- Custom writer có thể nhận tên file, bảng đích, tenant hoặc partition ID.
- Writer có thể cần tạo resource riêng cho từng JobExecution.

Ví dụ mỗi JobExecution ghi ra một file được truyền qua JobParameter:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .saveState(true)
            .build();
}
~~~

Trong ứng dụng thật, chính sách xử lý file đã tồn tại cần được quyết định rõ. Ví dụ trên chỉ minh họa việc truyền resource theo JobExecution; không nên vô tình ghi đè file của một lần chạy khác.

Một writer singleton có thể giữ resource đang mở hoặc trạng thái của lần chạy trước. Step scope tạo target riêng cho StepExecution và giúp lifecycle của writer gắn với lần chạy tương ứng.

## 5. Late binding từ JobParameters

JobParameters được cung cấp khi launch Job. Step-scoped bean có thể nhận giá trị đó bằng SpEL:

~~~java
@Value("#{jobParameters['inputFile']}")
String inputFile
~~~

Ví dụ reader:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

Các giá trị chỉ được phân giải khi target bean được tạo trong Step scope. Điều này cho phép cùng một Job definition chạy với nhiều bộ tham số khác nhau mà không cần tạo bean definition mới cho từng lần chạy.

JobParameters mô tả đầu vào của Job. Nếu parameter được đánh dấu identifying, nó tham gia xác định JobInstance. Nếu là non-identifying, nó không làm thay đổi danh tính JobInstance nhưng vẫn có thể được lưu trong metadata. Không đưa password hoặc token vào JobParameters chỉ vì có thể inject chúng qua SpEL.

## 6. Late binding từ Job ExecutionContext

Một Step có thể tạo metadata để Step sau dùng. Giá trị được lưu trong Job ExecutionContext có thể được inject vào reader/writer step-scoped.

Ví dụ Step chuẩn bị file đã kiểm tra:

~~~java
public class ValidateInputTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        String validatedFile =
                "/data/batch/validated-orders.csv";

        contribution.getStepExecution()
                .getJobExecution()
                .getExecutionContext()
                .putString("validatedFile", validatedFile);

        return RepeatStatus.FINISHED;
    }
}
~~~

Reader của Step tiếp theo nhận đường dẫn:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> validatedOrderReader(
        @Value("#{jobExecutionContext['validatedFile']}")
        String validatedFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("validatedOrderReader")
            .resource(new FileSystemResource(validatedFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

Job ExecutionContext được chia sẻ giữa các Step trong cùng JobExecution. Nó phù hợp với metadata nhỏ cần truyền giữa các Step, chẳng hạn đường dẫn file, business date đã xác định hoặc mã staging batch.

Nếu Step trước chỉ ghi dữ liệu vào Step ExecutionContext, Step sau không tự động đọc được key đó qua jobExecutionContext. Khi cần promotion, dùng ExecutionContextPromotionListener hoặc thiết kế Step trước ghi giá trị vào đúng phạm vi Job context.

## 7. Late binding từ Step ExecutionContext

Step ExecutionContext giữ state riêng của một StepExecution. Với partitioning, mỗi worker StepExecution có context riêng, thường chứa phạm vi dữ liệu mà worker cần xử lý.

Ví dụ Partitioner tạo hai giới hạn:

~~~java
ExecutionContext context = new ExecutionContext();
context.putLong("minId", 1001L);
context.putLong("maxIdExclusive", 2001L);
~~~

Reader nhận các giá trị đó:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}")
        Long maxIdExclusive) {

    // Cấu hình truy vấn chỉ đọc ID trong khoảng của partition.
}
~~~

Mỗi partition có một StepExecution và một target reader riêng. Vì vậy, worker có thể dùng cùng bean definition nhưng nhận các giới hạn khác nhau.

Không dùng một biến static hoặc một singleton mutable để thay min/max trước mỗi worker. Khi partition chạy đồng thời, các worker có thể ghi đè tham số của nhau.

## 8. Khai báo Step-scoped reader trong Java configuration

Một cấu hình điển hình gồm reader step-scoped và Step singleton:

~~~java
@Configuration
public class OrderBatchConfiguration {

    @Bean
    @StepScope
    FlatFileItemReader<Order> orderReader(
            @Value("#{jobParameters['inputFile']}")
            String inputFile) {

        return new FlatFileItemReaderBuilder<Order>()
                .name("orderReader")
                .resource(new FileSystemResource(inputFile))
                .delimited()
                .names("id", "customerId", "amount")
                .targetType(Order.class)
                .saveState(true)
                .build();
    }

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<Order> orderReader,
            ItemWriter<Order> orderWriter) {

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, Order>chunk(100, transactionManager)
                .reader(orderReader)
                .writer(orderWriter)
                .build();
    }
}
~~~

Step definition có thể là singleton. Khi cấu hình Step, biến orderReader được inject thực tế là scoped proxy. Khi Step chạy, proxy phân giải target reader của StepExecution hiện tại.

Không tự gọi new FlatFileItemReader ở nơi khác để thay thế bean đã khai báo step-scoped. Việc khởi tạo thủ công bỏ qua container scope, late binding và lifecycle quản lý resource của Spring.

## 9. Khai báo Step-scoped writer trong Java configuration

Writer có thể nhận output path hoặc thông tin đích từ JobParameters:

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderWriter")
            .resource(new FileSystemResource(outputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .saveState(true)
            .build();
}
~~~

Step sử dụng proxy như với reader:

~~~java
@Bean
Step exportOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        FlatFileItemWriter<Order> orderWriter) {

    return new StepBuilder("exportOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .build();
}
~~~

Ví dụ cho thấy output resource được xác định tại thời điểm Step chạy. Trong ứng dụng có restart, cần quyết định writer mở lại file theo chế độ nào và checkpoint được lưu ra sao. Không thay đổi output path giữa lần chạy đầu và restart của cùng JobInstance nếu writer dựa vào file cũ để tiếp tục.

## 10. Return type của @Bean và ItemStream

Một lưu ý quan trọng khi khai báo reader/writer có state là kiểu trả về của phương thức @Bean.

Nếu component triển khai ItemStream, hãy khai báo kiểu trả về đủ cụ thể để Spring Batch nhận biết lifecycle đó. Tốt nhất dùng concrete class như FlatFileItemReader<Order> hoặc interface ItemStreamReader<Order>/ItemStreamWriter<Order> phù hợp.

Ví dụ:

~~~java
@Bean
@StepScope
ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

Nếu chỉ khai báo return type là ItemReader<Order> trong khi implementation còn triển khai ItemStream, thông tin kiểu có thể không được nhìn thấy khi cấu hình Step. Điều đó có thể khiến lifecycle open, update và close không được đăng ký như mong đợi.

Đối với custom reader/writer có state, hãy triển khai ItemStreamReader hoặc ItemStreamWriter và để kiểu khai báo thể hiện interface stream-aware.

## 11. Step scope và ItemStream lifecycle

@StepScope và ItemStream giải quyết hai vấn đề liên quan nhưng khác nhau:

- Step scope quản lý vòng đời target bean theo StepExecution và cho phép late binding.
- ItemStream cung cấp lifecycle để mở resource, khôi phục state, lưu checkpoint và đóng resource.

Một reader step-scoped không tự động lưu mọi field của nó vào JobRepository. Muốn restart, component phải lưu state vào ExecutionContext qua ItemStream lifecycle hoặc dùng cơ chế checkpoint phù hợp.

Các callback ItemStream:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

Trong chunk-oriented Step, Spring Batch gọi open khi Step bắt đầu, update tại các checkpoint và close khi Step kết thúc theo lifecycle. Reader/writer có thể khôi phục state từ ExecutionContext trong open và cập nhật checkpoint trong update.

Ví dụ reader tự viết:

~~~java
public class CustomerReader implements ItemStreamReader<Customer> {

    private static final String LAST_ID = "customerReader.lastId";
    private long lastId;

    @Override
    public void open(ExecutionContext context) {
        lastId = context.containsKey(LAST_ID)
                ? context.getLong(LAST_ID)
                : 0L;
    }

    @Override
    public Customer read() {
        Customer customer = loadNextAfter(lastId);
        if (customer != null) {
            lastId = customer.getId();
        }
        return customer;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong(LAST_ID, lastId);
    }

    @Override
    public void close() {
        // Đóng resource nếu có.
    }
}
~~~

Nếu bean này được tạo theo Step scope, mỗi StepExecution có target reader riêng. ItemStream vẫn là cơ chế lưu checkpoint; scope không thay thế nó.

## 12. Delegate và composite reader/writer

Một reader hoặc writer có thể bọc delegate khác. Ví dụ composite writer điều phối nhiều writer con hoặc custom reader dùng delegate để đọc file.

Khi delegate triển khai ItemStream, cần bảo đảm delegate được đăng ký vào Step để framework gọi open, update và close. Chỉ bọc delegate trong một bean step-scoped không bảo đảm mọi stream con đều tự động được nhận diện trong mọi cấu trúc.

Các điểm cần kiểm tra:

- Composite có triển khai ItemStream hay không.
- Delegate stream có được đăng ký đúng lifecycle hay không.
- Delegate có state riêng cần lưu vào ExecutionContext hay không.
- Tên component trong context có ổn định và không trùng nhau hay không.
- Resource được đóng khi Step hoàn tất hoặc thất bại hay không.

Nếu custom wrapper che mất interface ItemStream của delegate, hãy triển khai/ủy quyền lifecycle phù hợp hoặc đăng ký stream bằng cơ chế của Step. Nếu không, Job có thể chạy bình thường lần đầu nhưng không khôi phục đúng state khi restart.

## 13. Step scope khác Job scope

Spring Batch có cả @StepScope và @JobScope.

| Scope | Vòng đời target | Dùng khi |
|---|---|---|
| Singleton | Một instance trong ApplicationContext | Bean stateless, cấu hình cố định và an toàn khi dùng chung |
| Job scope | Gắn với một JobExecution | Bean cần dữ liệu hoặc state chia sẻ trong phạm vi JobExecution |
| Step scope | Gắn với một StepExecution | Reader/writer hoặc component cần state và tham số riêng của Step |

@JobScope có ích cho component cần tồn tại trong phạm vi một JobExecution, ví dụ một bean điều phối dùng metadata chung giữa các Step. @StepScope phù hợp hơn cho reader/writer cần checkpoint hoặc partition parameter của một StepExecution.

JobParameters có thể được inject vào cả Job-scoped và Step-scoped bean. Tuy nhiên, nếu component là reader/writer thuộc Step, step scope thường diễn đạt đúng lifecycle của nó hơn.

Không dùng Job scope để lưu checkpoint reader riêng cho từng Step. Nếu Job có nhiều Step hoặc nhiều partition, state của reader cần thuộc StepExecution tương ứng.

## 14. Khi nào reader/writer không cần step scope?

Không phải mọi reader hoặc writer đều bắt buộc phải step-scoped. Một component stateless, thread-safe, dùng cấu hình cố định và không giữ resource hoặc checkpoint riêng có thể được dùng như singleton nếu lifecycle của nó cho phép.

Ví dụ một writer chỉ chuyển dữ liệu sang một service thread-safe và không giữ state có thể không cần scope riêng. Tuy nhiên, cần xác minh:

- Không có field mutable theo execution.
- Không mở resource kéo dài qua nhiều lần chạy.
- Không cần late binding từ JobParameters hoặc ExecutionContext.
- Có thể được nhiều StepExecution gọi đồng thời.
- Không giữ checkpoint hoặc dữ liệu tạm thuộc một Step.

Nếu không chắc component có state ẩn hay không, kiểm tra implementation và hợp đồng ItemStream của nó. Đừng thêm @StepScope cho mọi bean một cách máy móc; hãy chọn scope theo lifecycle và dữ liệu mà component thực sự cần.

## 15. Step scope trong partitioning

Trong partitioned Step, manager tạo nhiều worker StepExecution. Mỗi worker có Step ExecutionContext riêng, vì vậy reader/writer cần nhận đúng tham số của partition tương ứng.

Ví dụ:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Customer> partitionCustomerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}")
        Long maxIdExclusive) {

    // Tạo reader giới hạn trong phạm vi ID của worker.
}
~~~

Nếu có bốn partition, Spring tạo target reader theo từng StepExecution. Các worker có thể dùng cùng bean definition nhưng mỗi target nhận min/max riêng.

Đây là một lý do quan trọng để dùng Step scope trong partitioning. Không dùng singleton reader có tham số được thay đổi theo partition; khi worker chạy song song, chúng có thể đọc trùng hoặc bỏ sót dữ liệu.

## 16. Step scope và chạy đa luồng trong một Step

Cần phân biệt partitioning với multi-threaded Step.

Trong partitioning, mỗi worker có StepExecution riêng, nên mỗi StepExecution có scope target riêng. Trong một multi-threaded Step, nhiều thread có thể cùng làm việc trong một StepExecution. Step-scoped bean không tự động có nghĩa là một instance riêng cho từng thread hoặc từng item.

Nếu reader/writer step-scoped giữ state mutable nhưng Step xử lý nhiều thread đồng thời, thread safety vẫn phụ thuộc implementation. Một reader không thread-safe có thể cần đồng bộ, phân chia reader hoặc dùng thiết kế khác phù hợp với mô hình concurrency.

Không dùng @StepScope như giải pháp tự động cho mọi vấn đề race condition. Hãy xác định:

- Có bao nhiêu StepExecution?
- Có bao nhiêu thread cùng xử lý một StepExecution?
- Reader/writer có hỗ trợ concurrent calls không?
- Checkpoint có thể được cập nhật đồng thời không?
- Transaction boundary và thứ tự commit có được đảm bảo không?

Với multi-threaded Step, hãy tham khảo khả năng thread-safe của component cụ thể và kiểm thử tải song song. Với partitioning, ưu tiên state riêng cho mỗi worker StepExecution.

## 17. Step scope được kích hoạt như thế nào?

Step scope cần hạ tầng Spring Batch được cấu hình. Các cách cấu hình thông dụng như @EnableBatchProcessing hoặc DefaultBatchConfiguration đăng ký scope cần thiết. Spring Boot với cấu hình Batch phù hợp cũng thiết lập hạ tầng này.

Ví dụ:

~~~java
@Configuration
@EnableBatchProcessing
public class BatchConfiguration {
    // Khai báo Job, Step và các scoped component.
}
~~~

Trong ứng dụng dùng cấu hình Batch tự động của Spring Boot, không thêm cấu hình hạ tầng trùng lặp chỉ để bật Step scope. Hãy dùng một mô hình cấu hình repository/Batch nhất quán với phiên bản framework.

@StepScope tạo scoped proxy cho bean. Khi proxy được gọi ngoài một StepExecution đang hoạt động, Spring không thể tìm target trong scope và có thể ném lỗi ScopeNotActiveException hoặc lỗi liên quan đến context chưa được đăng ký.

Điều này thường xảy ra khi:
- Gọi trực tiếp reader trong lúc ApplicationContext khởi động.
- Dùng một scoped bean trong @PostConstruct của singleton.
- Tự tạo Step component ngoài Job/Step lifecycle.
- Test bean mà không thiết lập StepExecution context.

Không gọi method của reader/writer step-scoped trong quá trình khởi tạo cấu hình. Hãy để Step framework gọi component khi Step đang chạy.

## 18. Proxy và kiểu bean

Vì @StepScope dùng scoped proxy, bean được inject vào Job/Step definition thường là proxy, còn target thực tế chỉ được tạo khi scope hoạt động.

Một số lưu ý:

- Tránh khai báo target class final khi dùng class-based scoped proxy.
- Không gọi method phụ thuộc runtime context trước khi Step bắt đầu.
- Giữ kiểu trả về @Bean đủ cụ thể, đặc biệt với ItemStream.
- Không tự tạo instance bằng new để thay thế scoped proxy.
- Không giữ tham chiếu đến target bean sau khi Step scope kết thúc.
- Dùng constructor injection cho dependency ổn định; dùng @Value cho giá trị runtime.

Trong ví dụ Java configuration, phương thức @Bean có thể nhận JobParameters hoặc context values qua tham số @Value. Spring chỉ tạo target khi scope có thể phân giải các giá trị đó.

## 19. Lỗi thường gặp khi dùng @StepScope

**Quên khai báo Step scope.** SpEL tham chiếu JobParameters hoặc ExecutionContext được phân giải quá sớm khi tạo singleton.

**Dùng reader/writer stateful như singleton.** Nhiều execution có thể chia sẻ checkpoint hoặc resource.

**Gọi scoped bean ngoài Step.** Không có StepExecution hiện hành để tạo target.

**Chỉ khai báo return type ItemReader/ItemWriter.** Framework có thể không nhận diện được ItemStream lifecycle của implementation. Dùng kiểu stream-aware hoặc concrete type.

**Nghĩ rằng scope tự lưu checkpoint.** Step scope quản lý instance; ItemStream và ExecutionContext mới lưu state phục hồi.

**Nhầm Job scope với Step scope.** Job scope gắn với JobExecution, còn checkpoint reader/writer thuộc StepExecution.

**Dùng chung một reader cho các partition.** Worker có thể ghi đè tham số và state. Tạo target riêng theo StepExecution.

**Cho rằng step-scoped bean riêng cho mỗi thread.** Một StepExecution có thể có nhiều thread và target bean vẫn có thể được dùng chung tùy cách thực thi.

**Bọc ItemStream delegate mà không đăng ký lifecycle.** Reader/writer con có thể không nhận callback open/update/close.

**Thay đổi tên reader/writer khi restart.** Các key ExecutionContext cũ có thể không còn được khôi phục như mong đợi.

## 20. Kiểm thử step-scoped reader và writer

Có thể kiểm thử scoped bean bằng Spring Batch Test. Test cần tạo StepExecution context để proxy có thể khởi tạo target và phân giải các giá trị late-bound.

Ví dụ dùng StepScopeTestUtils:

~~~java
@Test
void readerUsesInputFileFromJobParameters() throws Exception {
    StepExecution stepExecution =
            MetaDataInstanceFactory.createStepExecution();

    StepScopeTestUtils.doInStepScope(stepExecution, () -> {
        FlatFileItemReader<Order> reader =
                applicationContext.getBean("orderReader",
                        FlatFileItemReader.class);

        reader.open(new ExecutionContext());
        Order first = reader.read();
        reader.close();

        assertNotNull(first);
        return null;
    });
}
~~~

Đây là ví dụ minh họa cách kích hoạt Step scope trong test; cần có bean ApplicationContext đã cấu hình và file fixture tương ứng. Nếu giá trị được inject từ JobParameters, hãy tạo JobExecution có parameters cần thiết trước khi chạy test.

Có thể dùng StepScopeTestExecutionListener hoặc tiện ích tương ứng của phiên bản Spring Batch Test. Kiểm tra đúng package/API trong phiên bản đang dùng.

Các kịch bản nên xác nhận:

- JobParameter được inject đúng vào reader/writer.
- Job ExecutionContext được đọc đúng.
- Step ExecutionContext của partition được đọc đúng.
- Hai StepExecution khác nhau nhận target instance và state riêng.
- ItemStream open/update/close được gọi.
- Checkpoint được lưu và khôi phục khi restart.
- Reader/writer không bị gọi ngoài scope.
- Multi-threaded Step không truy cập state không an toàn.

## 21. Quy trình quyết định reader/writer có cần step scope

Khi khai báo một reader hoặc writer, hãy xem xét theo thứ tự:

1. Component có cần JobParameters, Job ExecutionContext hoặc Step ExecutionContext không? Nếu có, dùng Step scope để late-bind.
2. Component có state mutable theo lần chạy không? Nếu có, dùng target riêng theo StepExecution.
3. Component có giữ file, cursor, connection hoặc resource mở không? Kiểm tra lifecycle và tránh chia sẻ instance.
4. Component có triển khai ItemStream không? Bảo đảm framework nhận diện và gọi open/update/close.
5. Component có chạy trong partitioning không? Mỗi worker cần nhận context riêng.
6. Step có chạy đa luồng không? Kiểm tra thread safety; scope không tự tạo instance theo thread.
7. Bean có bị gọi trước khi Step bắt đầu không? Tránh dereference scoped proxy ngoài lifecycle.
8. State có cần restart không? Lưu checkpoint qua ExecutionContext, giữ tên component và key ổn định.
9. Có delegate/composite không? Đăng ký đầy đủ ItemStream delegate.
10. Test ít nhất hai StepExecution với tham số khác nhau để xác nhận không chia sẻ state.

@StepScope đặc biệt hữu ích cho reader và writer có state hoặc phụ thuộc dữ liệu runtime. Nó giúp mỗi StepExecution có target bean phù hợp và cho phép late binding từ JobParameters, Job ExecutionContext hoặc Step ExecutionContext. Kết hợp Step scope với ItemStream, checkpoint và cấu hình concurrency đúng cách sẽ giúp reader/writer hoạt động độc lập giữa các lần chạy và có thể phục hồi khi Job restart.

