# Lỗi bean ngoài scope

Trong Spring Batch, một số bean chỉ có thể được tạo hoặc sử dụng khi JobExecution hoặc StepExecution tương ứng đang hoạt động. Ví dụ, reader cần lấy tên file từ JobParameters hoặc lấy khoảng ID từ StepExecutionContext. Nếu bean được khai báo như singleton thông thường nhưng lại truy cập dữ liệu chỉ tồn tại trong Job/Step scope, ứng dụng có thể gặp lỗi khi khởi tạo bean, khi gọi phương thức hoặc khi chạy Job.

Nhóm lỗi này thường xuất hiện khi dùng late binding nhưng bean chưa được đặt đúng scope. Spring Batch cung cấp **@StepScope** và **@JobScope** để trì hoãn việc tạo target bean đến đúng thời điểm thực thi và gắn vòng đời bean với StepExecution hoặc JobExecution.

Hiểu rõ scope giúp tránh lỗi kiểu **Scope 'step' is not active for the current thread**, tránh dùng nhầm tham số giữa các lần chạy và tránh chia sẻ state của reader/writer giữa các StepExecution.

## 1. Vì sao bean có thể nằm ngoài scope?

Spring quản lý bean theo scope. Scope quyết định thời điểm tạo bean, thời gian tồn tại và phạm vi instance được chia sẻ.

Các scope thường gặp:

| Scope | Vòng đời |
| --- | --- |
| singleton | Một instance cho mỗi bean definition trong Spring ApplicationContext |
| prototype | Tạo instance mới mỗi khi container được yêu cầu lấy bean |
| request/session | Gắn với HTTP request hoặc session trong ứng dụng web |
| step | Một target bean cho một StepExecution đang hoạt động |
| job | Một target bean cho một JobExecution đang hoạt động |

Trong ứng dụng Spring thông thường, singleton được tạo khi ApplicationContext khởi tạo hoặc khi bean được yêu cầu lần đầu. Lúc đó JobExecution và StepExecution có thể chưa tồn tại.

Ví dụ, một reader cần đọc giá trị inputFile từ JobParameters:

~~~java
@Bean
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(OrderInput.class)
            .build();
}
~~~

Bean trên mặc định là singleton. Spring có thể phải giải quyết biểu thức jobParameters khi chưa có JobExecution đang hoạt động. Kết quả là không tìm thấy ngữ cảnh Job hoặc Step tương ứng.

Ngay cả khi bean khởi tạo được, singleton giữ một giá trị đã bind tại thời điểm tạo. Nếu cùng bean được dùng cho nhiều JobExecution với input khác nhau, giá trị cũ có thể được dùng lại hoặc state của lần chạy này ảnh hưởng lần chạy khác.

## 2. Dấu hiệu thường gặp của lỗi ngoài scope

Một số thông báo lỗi phổ biến:

~~~text
Scope 'step' is not active for the current thread
~~~

~~~text
Scope 'job' is not active for the current thread
~~~

~~~text
No context holder available for step scope
~~~

Thông báo chính xác có thể khác theo phiên bản Spring, Spring Batch và cách bean được truy cập. Ý nghĩa chung là bean hoặc scoped proxy cần một StepExecution/JobExecution nhưng thread hiện tại không có context tương ứng.

Các dấu hiệu khác:

- Job chạy trong test nhưng lỗi khi gọi reader trực tiếp từ test method.
- Bean khởi tạo thất bại lúc ApplicationContext startup vì biểu thức jobParameters hoặc stepExecutionContext chưa có giá trị.
- Hai lần chạy dùng input khác nhau nhưng reader lại dùng chung file, tenant hoặc khoảng dữ liệu.
- Worker partition đọc nhầm phạm vi của partition khác.
- @Value trả về null hoặc không resolve được key do dùng sai tên context hoặc bean được tạo ngoài scope.
- @StepScope đã khai báo nhưng lỗi vẫn xuất hiện vì target bị gọi trước khi Step bắt đầu hoặc ở một thread không có Batch context.

Không nên chỉ xử lý bằng cách bắt exception hoặc gán giá trị mặc định cho mọi tham số. Trước tiên hãy xác định bean nào cần Job/Step context, ai tạo bean và tại thời điểm nào target được gọi.

## 3. Dùng @StepScope cho bean phụ thuộc StepExecution

@StepScope gắn vòng đời target bean với một StepExecution. Đây là lựa chọn phổ biến cho reader, processor hoặc writer cần:

- stepExecutionContext.
- stepExecution.
- jobParameters được sử dụng trong phạm vi Step.
- State riêng của một lần thực thi Step.

Sửa ví dụ reader bằng cách thêm @StepScope:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

Với cấu hình này, Spring tạo scoped proxy khi ApplicationContext khởi tạo. Target FlatFileItemReader được tạo khi StepExecution thích hợp đang hoạt động và các giá trị JobParameters có thể được resolve.

@StepScope là annotation tiện ích cho scope step cùng scoped proxy. Vì vậy, bean có thể được inject vào cấu hình Step trước khi Step chạy; proxy sẽ chuyển lời gọi đến target gắn với StepExecution hiện tại.

### Late binding từ StepExecutionContext

Trong partitioned Step, mỗi worker cần nhận một phạm vi dữ liệu riêng:

~~~java
@Bean
@StepScope
public ItemReader<Order> orderRangeReader(
        OrderRepository repository,
        @Value("#{stepExecutionContext['minOrderId']}") Long minId,
        @Value("#{stepExecutionContext['maxOrderId']}") Long maxId) {

    return new OrderRangeReader(repository, minId, maxId);
}
~~~

Master Step tạo các ExecutionContext khác nhau cho từng partition. Khi worker của partition 0 chạy, target reader nhận minOrderId và maxOrderId của partition 0. Worker của partition 1 có target reader và context tương ứng với partition 1.

Nếu bỏ @StepScope, reader có thể được tạo quá sớm hoặc trở thành singleton dùng chung, khiến các partition đọc sai phạm vi.

## 4. Dùng @JobScope cho dữ liệu gắn với JobExecution

@JobScope gắn target bean với một JobExecution. Nó phù hợp khi bean cần dữ liệu chung cho toàn Job, chẳng hạn:

- Tham số Job.
- Giá trị trong JobExecutionContext.
- State được chia sẻ ở phạm vi Job và không phụ thuộc riêng vào một Step.

Ví dụ:

~~~java
@Bean
@JobScope
public ImportSettings importSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobExecutionContext['sourceSystem']}") String sourceSystem) {

    return new ImportSettings(businessDate, sourceSystem);
}
~~~

Bean ImportSettings được tạo cho JobExecution hiện tại. Các Step thuộc Job có thể dùng proxy để truy cập cùng target trong phạm vi JobExecution đó.

Không dùng @JobScope để đọc stepExecutionContext, vì dữ liệu này thuộc về một StepExecution cụ thể. Nếu giá trị thay đổi theo worker hoặc partition, hãy dùng @StepScope.

### Chọn Step scope hay Job scope?

| Nhu cầu | Scope phù hợp |
| --- | --- |
| Reader cần tên file từ JobParameters | @StepScope thường phù hợp |
| Reader cần min/max ID của partition | @StepScope |
| Processor cần giá trị riêng của StepExecution | @StepScope |
| Bean chứa cấu hình dùng chung cho toàn JobExecution | @JobScope |
| Bean cần đọc jobExecutionContext | @JobScope hoặc @StepScope nếu truy cập trong Step |
| Bean cần đọc stepExecutionContext | @StepScope |
| Service stateless, không phụ thuộc execution context | singleton thông thường |

Chọn scope theo dữ liệu mà bean cần và vòng đời mong muốn, không chỉ theo loại class. Không phải mọi reader, processor hoặc writer đều cần scope đặc biệt.

## 5. Scoped proxy giải quyết vấn đề tạo bean quá sớm

Khi một singleton Step configuration inject một bean @StepScope, target Step-scoped chưa được tạo ngay. Spring inject một proxy đại diện:

~~~text
ApplicationContext khởi tạo
        |
        v
Tạo scoped proxy cho orderReader
        |
        v
Proxy được inject vào Step definition
        |
        v
Job bắt đầu
        |
        v
StepExecution được tạo và context được kích hoạt
        |
        v
Proxy yêu cầu target
        |
        v
Tạo FlatFileItemReader với JobParameters hiện tại
~~~

Proxy giúp bean có thể được tham chiếu từ cấu hình singleton mà không cần tạo target quá sớm. Khi lời gọi đi qua proxy trong scope hợp lệ, Spring tìm hoặc tạo target gắn với execution hiện tại.

### Không tự gọi target khi scope chưa hoạt động

Tránh truy cập method của bean scoped trong:

- Constructor của một singleton bean.
- @PostConstruct của một singleton bean.
- Logic cấu hình được thực thi lúc ApplicationContext khởi tạo.
- Một test gọi reader trước khi tạo StepExecution context.
- Một thread tự tạo không có Batch context.

Ví dụ không nên làm:

~~~java
@Component
public class StartupInspector {

    public StartupInspector(ItemReader<OrderInput> orderReader) {
        // Không gọi orderReader.read() ở đây.
        // Step scope chưa chắc đã hoạt động.
    }
}
~~~

Inject proxy là hợp lệ; gọi target trước khi Job/Step context được thiết lập mới là vấn đề.

## 6. Phân biệt scope với prototype

Một cách sửa dễ nhầm là đổi singleton thành prototype:

~~~java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public ItemReader<OrderInput> orderReader(...) {
    // ...
}
~~~

Prototype chỉ yêu cầu Spring tạo instance mới mỗi lần container được gọi để lấy bean. Nó không tự liên kết instance với StepExecution, không tự resolve late-bound value đúng thời điểm và không tự quản lý vòng đời open, update, close theo Step.

Nếu một singleton nhận prototype qua dependency injection, instance prototype thường được tạo tại thời điểm singleton được tạo và sau đó singleton giữ nguyên instance đó. Vì vậy, prototype không thay thế @StepScope.

Khi cần một instance cho mỗi StepExecution cùng khả năng truy cập context và lifecycle do Spring Batch quản lý, hãy dùng @StepScope.

## 7. Scope infrastructure phải được đăng ký

@StepScope và @JobScope cần scope infrastructure của Spring Batch. Trong ứng dụng dùng cấu hình Batch chuẩn, infrastructure thường được đăng ký qua cấu hình Spring Batch, chẳng hạn @EnableBatchProcessing, hoặc được Spring Boot auto-configuration cung cấp tùy cách ứng dụng cấu hình Batch.

Ví dụ cấu hình Batch:

~~~java
@Configuration
@EnableBatchProcessing
public class BatchInfrastructureConfiguration {
}
~~~

Nếu ứng dụng tự cấu hình infrastructure, hãy xác nhận StepScope và JobScope đã được đăng ký. Khi Spring không nhận diện scope, lỗi thường có dạng:

~~~text
No Scope registered for scope name 'step'
~~~

Lỗi này khác với Scope 'step' is not active: trường hợp đầu là scope chưa được đăng ký trong container; trường hợp sau là scope có tồn tại nhưng chưa có StepExecution context hoạt động tại thời điểm truy cập.

Không đăng ký lặp nhiều scope bean nếu infrastructure đã cung cấp chúng. Việc trộn nhiều cấu hình Batch hoặc bật/tắt auto-configuration không nhất quán có thể tạo bean infrastructure trùng hoặc thiếu.

## 8. Lỗi sai key hoặc sai loại context

Ngay cả khi bean đã có @StepScope, SpEL vẫn phải dùng đúng tên context:

| Biểu thức | Dữ liệu |
| --- | --- |
| #{jobParameters['inputFile']} | Job parameter |
| #{jobExecutionContext['sourceSystem']} | JobExecutionContext |
| #{stepExecutionContext['minOrderId']} | StepExecutionContext |
| #{jobExecution.jobId} | Thông tin JobExecution |
| #{stepExecution.stepName} | Thông tin StepExecution |

Ví dụ, nếu Partitioner ghi:

~~~java
context.putLong("minOrderId", 1000L);
~~~

thì reader phải đọc đúng key:

~~~java
@Value("#{stepExecutionContext['minOrderId']}") Long minOrderId
~~~

Các lỗi thường gặp:

- Ghi key minOrderId nhưng đọc minId.
- Ghi giá trị vào JobExecutionContext nhưng lại đọc từ StepExecutionContext.
- Dùng tên key khác chữ hoa/chữ thường.
- Giá trị chưa được thêm vào context trước khi worker bắt đầu.
- Ép kiểu không phù hợp, ví dụ giá trị số được lưu dưới dạng String nhưng bean nhận Long.

Khi một key có thể không tồn tại, cần xác định rõ đó là trường hợp hợp lệ hay lỗi cấu hình. Có thể dùng giá trị mặc định trong SpEL cho trường hợp optional, nhưng không nên đặt mặc định cho một partition boundary bắt buộc vì có thể khiến worker đọc sai phạm vi.

## 9. Không giữ state của execution trong singleton

Một singleton bean được chia sẻ trong ApplicationContext. Nếu lưu JobParameters, StepExecution, file path hoặc counter của một lần chạy trong field mutable, các lần chạy có thể ghi đè dữ liệu của nhau.

Ví dụ không an toàn:

~~~java
@Component
public class CurrentImportState {

    private String inputFile;

    public void setInputFile(String inputFile) {
        this.inputFile = inputFile;
    }

    public String getInputFile() {
        return inputFile;
    }
}
~~~

Nếu hai JobExecution chạy đồng thời và cùng ghi inputFile, một Job có thể đọc file của Job còn lại.

Hãy chọn một trong các cách:

- Đưa giá trị vào JobParameters nếu đó là input cố định của JobInstance.
- Đưa giá trị vào JobExecutionContext nếu đó là state dùng chung trong phạm vi JobExecution.
- Đưa giá trị vào StepExecutionContext nếu nó riêng cho Step hoặc partition.
- Dùng bean @StepScope/@JobScope để bind dữ liệu theo đúng execution.
- Giữ service singleton stateless và truyền tham số qua method.

Không nên biến service nghiệp vụ thành scoped bean chỉ để giữ một giá trị tạm nếu có thể truyền tham số tường minh.

## 10. Scope trong multi-threaded Step và partitioning

Scope không tự giải quyết mọi vấn đề concurrency.

### Partitioned Step

Mỗi partition có StepExecution riêng. Một bean @StepScope được khởi tạo theo StepExecution của partition tương ứng, vì vậy có thể bind minOrderId, maxOrderId hoặc file riêng cho từng worker.

~~~text
Master Step
    |
    +--> partition0 / StepExecution 0
    |       +--> step-scoped reader 0
    |
    +--> partition1 / StepExecution 1
    |       +--> step-scoped reader 1
    |
    +--> partition2 / StepExecution 2
            +--> step-scoped reader 2
~~~

Đây là trường hợp điển hình nên dùng Step scope cho reader phụ thuộc partition context.

### Multi-threaded Step

Trong multi-threaded Step, nhiều thread có thể cùng xử lý một StepExecution. @StepScope gắn target với StepExecution, không có nghĩa tự động tạo một target riêng cho từng thread. Nếu reader, writer hoặc processor giữ mutable state, cần kiểm tra thread safety và cách framework truyền Batch context sang worker thread.

Không nên cho rằng thêm @StepScope sẽ làm một reader có cursor an toàn khi nhiều thread cùng gọi. Hãy dùng component hỗ trợ concurrency, đồng bộ truy cập hoặc chọn mô hình partitioning khi cần một reader riêng cho từng đơn vị công việc.

### Job scope trong xử lý đồng thời

@JobScope là một target cho JobExecution. Vì vậy, nhiều Step hoặc worker trong cùng Job có thể cùng truy cập target đó. Tránh lưu mutable state không thread-safe trong job-scoped bean nếu Job có các nhánh hoặc worker chạy đồng thời.

Với dữ liệu riêng của partition, ưu tiên Step scope thay vì Job scope. Job scope cũng có những giới hạn khi dùng trong multi-threaded hoặc partitioned execution vì việc quản lý Job context qua các thread worker không phải lúc nào cũng được framework bảo đảm theo cách ứng dụng mong đợi.

## 11. Bean scope và lifecycle của ItemStream

Reader hoặc writer triển khai ItemStream cần được Spring Batch quản lý lifecycle:

- open(ExecutionContext) khi Step bắt đầu hoặc restart.
- update(ExecutionContext) tại ranh giới chunk để lưu checkpoint.
- close() khi Step kết thúc.

Nếu bean scoped được bọc bởi proxy hoặc decorator, cần bảo đảm ItemStream delegate được đăng ký đúng với Step. Các builder chuẩn thường nhận diện reader/writer được truyền trực tiếp, nhưng một wrapper tự viết có thể không chuyển tiếp ItemStream lifecycle.

Ví dụ một delegate reader:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> delegateReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("delegateReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

Nếu bọc reader này bằng custom decorator, decorator nên triển khai và chuyển tiếp ItemStream để checkpoint không bị mất. Một bean đúng scope nhưng lifecycle stream không được gọi vẫn có thể restart sai.

## 12. Kiểm thử bean có Step scope

Một lỗi thường gặp trong test là gọi method của scoped bean mà không thiết lập StepExecution context. Test cần kích hoạt scope với execution giả lập hoặc chạy qua test support của Spring Batch.

Có thể dùng StepScopeTestUtils:

~~~java
@SpringBatchTest
@SpringJUnitConfig(BatchConfiguration.class)
class OrderReaderTest {

    @Autowired
    private ItemReader<OrderInput> orderReader;

    @Test
    void readsFromInputDefinedByJobParameters() throws Exception {
        StepExecution stepExecution = MetaDataInstanceFactory
                .createStepExecution(
                        new JobParametersBuilder()
                                .addString("inputFile", "orders.csv")
                                .toJobParameters());

        OrderInput first = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> orderReader.read());

        assertNotNull(first);
    }
}
~~~

Ví dụ minh họa cách kích hoạt Step scope cho lời gọi trong test. Cần cung cấp resource thực tế, reader bean và fixture phù hợp với cấu hình của dự án.

Một cách khác là dùng StepScopeTestExecutionListener và một factory method cung cấp StepExecution:

~~~java
@SpringBatchTest
class ScopedReaderIntegrationTest {

    @Autowired
    private ItemReader<OrderInput> orderReader;

    public StepExecution getStepExecution() {
        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", "orders-test.csv")
                .toJobParameters();

        return MetaDataInstanceFactory.createStepExecution(parameters);
    }

    @Test
    void readerIsCreatedInsideStepScope() throws Exception {
        assertNotNull(orderReader.read());
    }
}
~~~

Tên listener và cách bật test support cần phù hợp với phiên bản Spring Batch Test đang dùng. Nếu chỉ kiểm thử một bean method trực tiếp mà không qua container, @StepScope không thể tự tạo StepExecution context cho test.

## 13. Cách chẩn đoán lỗi ngoài scope

Khi gặp lỗi scope, hãy kiểm tra theo thứ tự:

1. **Bean nào cần context?** Tìm @Value có jobParameters, jobExecutionContext hoặc stepExecutionContext, hoặc code gọi StepSynchronizationManager.
2. **Bean đang có scope gì?** Nếu cần dữ liệu theo execution mà vẫn là singleton, thêm @StepScope hoặc @JobScope đúng trường hợp.
3. **Target được gọi lúc nào?** Tránh gọi trong constructor, @PostConstruct, startup callback hoặc trước khi Job/Step bắt đầu.
4. **Scope infrastructure đã đăng ký chưa?** Phân biệt lỗi scope chưa đăng ký với scope chưa active.
5. **Thread hiện tại có Batch context không?** Kiểm tra executor, thread tự tạo và mô hình concurrency.
6. **Key context có đúng không?** So sánh key ghi vào ExecutionContext với key SpEL đang đọc.
7. **Có nhiều JobExecution chạy đồng thời không?** Tìm mutable state đang đặt trong singleton.
8. **Có wrapper/decorator không?** Xác nhận scoped proxy và ItemStream lifecycle được chuyển tiếp.
9. **Test đã kích hoạt scope chưa?** Dùng test utilities thay vì gọi target ngoài context.

Không khắc phục bằng cách gọi StepSynchronizationManager.register(...) thủ công trong code nghiệp vụ nếu không thực sự quản lý đầy đủ lifecycle và cleanup. Việc đăng ký context thủ công có thể làm rò rỉ state giữa các lần chạy hoặc thread.

## 14. Những lỗi thường gặp

### Dùng singleton cho bean cần JobParameters

Singleton được tạo trước khi JobExecution tồn tại hoặc giữ giá trị của lần chạy đầu. Dùng Step scope hoặc Job scope cho late binding.

### Dùng @StepScope nhưng gọi bean trước khi Step chạy

Proxy có thể được inject từ sớm, nhưng target chỉ có thể được tạo khi Step scope active. Không gọi method trong startup callback hoặc constructor.

### Dùng @JobScope để đọc stepExecutionContext

Job scope không đại diện cho một StepExecution cụ thể. Dùng @StepScope cho giá trị riêng của Step/partition.

### Dùng prototype thay cho Step scope

Prototype không gắn bean với StepExecution và không tự cung cấp context hoặc lifecycle. Dùng @StepScope khi cần late binding theo Step.

### Scope chưa được đăng ký

Lỗi No Scope registered for scope name 'step' thường cho thấy Batch infrastructure chưa đăng ký scope hoặc cấu hình bị thiếu/trùng. Kiểm tra @EnableBatchProcessing hoặc auto-configuration đang dùng.

### Scope không active trên worker thread

Lỗi Scope 'step' is not active for the current thread có thể xảy ra khi target bị gọi ngoài Step lifecycle hoặc Batch context không được truyền sang thread đó. Kiểm tra executor và cách khởi chạy worker.

### Dùng scoped bean như thể mỗi thread có một instance

Step scope gắn với StepExecution, không phải thread. Trong multi-threaded Step, target có thể được nhiều thread cùng dùng. Kiểm tra thread safety.

### Singleton giữ dữ liệu của lần chạy trước

Không lưu input file, tenant, execution ID hoặc counter riêng của Job trong field mutable của singleton.

### Bọc reader nhưng làm mất ItemStream

Decorator cần chuyển tiếp open/update/close. Nếu không, checkpoint có thể không được lưu hoặc khôi phục.

### Test không tạo StepExecution context

Kích hoạt scope bằng StepScopeTestUtils hoặc Spring Batch test listener trước khi gọi scoped bean.

## 15. Quy trình chọn scope cho bean

Khi khai báo một bean trong Batch configuration, hãy xác định:

1. Bean có phụ thuộc vào dữ liệu chỉ tồn tại trong JobExecution hoặc StepExecution không?
2. Dữ liệu đó thuộc phạm vi toàn Job hay chỉ một Step/partition?
3. Bean có cần một target riêng cho mỗi execution không?
4. Có thể truyền giá trị qua method parameter thay vì giữ state không?
5. Bean có mutable state và được nhiều thread dùng đồng thời không?
6. Scoped proxy có được inject và chỉ được gọi khi scope active không?
7. Scope infrastructure có được Spring Batch đăng ký không?
8. Nếu là reader/writer, ItemStream lifecycle có được chuyển tiếp không?
9. Test có thiết lập Job/Step context phù hợp không?
10. Job restart hoặc chạy song song có thể làm bean nhận nhầm dữ liệu không?

Thông thường, service nghiệp vụ stateless nên là singleton. Bean cần late binding theo StepExecution nên dùng @StepScope. Bean cấu hình hoặc state dùng chung cho một JobExecution có thể dùng @JobScope, với lưu ý về concurrency.

## Kết luận

Lỗi bean ngoài scope xuất hiện khi một bean cần Job/Step context nhưng được tạo hoặc gọi ngoài vòng đời execution tương ứng. Bean singleton có thể được khởi tạo quá sớm và không thể resolve jobParameters hoặc stepExecutionContext, hoặc có thể giữ state dùng chung giữa các lần chạy. Dùng @StepScope cho dữ liệu theo StepExecution/partition và @JobScope cho dữ liệu theo JobExecution; scoped proxy cho phép inject bean vào cấu hình singleton nhưng target chỉ được tạo khi scope active. Cần đăng ký Batch scope infrastructure, gọi bean đúng lifecycle, kiểm tra thread safety, giữ ItemStream lifecycle và thiết lập context trong test.
