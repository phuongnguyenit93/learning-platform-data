# Scope trong multi-thread execution

Trong Spring Batch, scope xác định vòng đời và phạm vi tồn tại của một Spring bean. Khi một job chạy nhiều thread, việc chọn scope ảnh hưởng trực tiếp đến cách các thread nhìn thấy và sử dụng cùng một instance. Một bean singleton có thể được nhiều worker gọi đồng thời; một bean step-scoped được tạo theo StepExecution; một bean job-scoped thuộc phạm vi JobExecution. Những scope này quản lý vòng đời bean, nhưng bản thân scope không tự làm cho object trở nên thread-safe.

Đây là điểm quan trọng khi cấu hình multi-threaded step, partitioning hoặc parallel flow. Nếu reader giữ cursor mutable mà nhiều thread cùng gọi, dữ liệu có thể bị đọc trùng hoặc bỏ sót. Nếu một singleton service lưu batch ID hiện tại trong field, thread này có thể ghi đè dữ liệu thread kia. Nếu nhiều flow cập nhật cùng một Job ExecutionContext key, kết quả cuối có thể phụ thuộc thứ tự thực thi.

Thiết kế đúng cần tách ba vấn đề: bean tồn tại trong phạm vi nào, thread nào có thể truy cập bean đó, và state nào được phép chia sẻ. Scope trả lời câu hỏi đầu tiên; thread safety và transaction/concurrency design phải được giải quyết riêng.

## 1. Scope là gì?

Spring bean scope xác định khi nào bean được tạo, instance được chia sẻ ở phạm vi nào và khi nào instance bị hủy. Một số scope thường gặp:

| Scope | Vòng đời cơ bản | Cách dùng thường gặp |
|---|---|---|
| Singleton | Một instance trong Spring ApplicationContext | Service stateless, repository, template, cấu hình dùng chung |
| Prototype | Tạo instance mới mỗi lần container được yêu cầu bean | Object cần instance mới, với lifecycle do ứng dụng quản lý thêm |
| Step | Một instance trong phạm vi StepExecution | Reader, writer hoặc processor cần late binding theo step |
| Job | Một instance trong phạm vi JobExecution | Dữ liệu/cấu hình dùng chung trong một job execution |

Spring mặc định tạo bean singleton. Điều đó chỉ có nghĩa container quản lý một instance; nó không có nghĩa các lời gọi phương thức được đồng bộ hoặc mỗi thread có bản sao riêng.

Tương tự, prototype không tự động tạo instance mới cho mỗi lần gọi phương thức. Nếu một prototype bean được inject trực tiếp vào singleton, instance thường được tạo khi singleton được khởi tạo và tiếp tục được singleton giữ lại. Muốn lấy prototype mới theo từng lần sử dụng, cần dùng ObjectProvider, Provider hoặc cơ chế lookup phù hợp.

Spring Batch bổ sung StepScope và JobScope để bean có thể truy cập dữ liệu runtime của execution, chẳng hạn JobParameters hoặc ExecutionContext. Chúng hữu ích cho late binding, nhưng cần hiểu rõ phạm vi khi nhiều thread chạy đồng thời.

## 2. Scope không đồng nghĩa với thread safety

Scope quản lý vòng đời object. Thread safety là khả năng một object được nhiều thread sử dụng đồng thời mà không làm sai dữ liệu hoặc vi phạm invariant.

Ví dụ một singleton service không giữ state theo request:

~~~java
@Service
public class CustomerLookupService {

    private final CustomerRepository repository;

    public CustomerLookupService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Customer findRequired(String customerId) {
        return repository.findById(customerId)
                .orElseThrow(() ->
                        new CustomerNotFoundException(customerId));
    }
}
~~~

Service chỉ dùng dependency và biến cục bộ trong phương thức. Nhiều flow có thể gọi đồng thời mà không ghi đè một field trạng thái dùng chung, với điều kiện repository và các dependency cũng hỗ trợ concurrent use.

Ngược lại, singleton có mutable state theo lần chạy rất dễ gây race condition:

~~~java
@Component
public class UnsafeBatchState {

    private String currentBatchId;

    public void setBatchId(String batchId) {
        this.currentBatchId = batchId;
    }

    public void process(Order order) {
        // Một thread khác có thể đã thay currentBatchId.
        saveOrder(order, currentBatchId);
    }
}
~~~

Nếu flow A đặt batch ID là A, rồi flow B đặt batch ID là B trước khi flow A gọi process, đơn hàng của A có thể bị ghi dưới batch B. Chuyển bean sang một scope khác không tự sửa được thiết kế state nếu phạm vi mới vẫn được nhiều thread chia sẻ.

Quy tắc thực hành:

- Ưu tiên service stateless và dữ liệu cấu hình immutable.
- Truyền dữ liệu theo lần gọi qua method argument thay vì lưu trong field singleton.
- Để state riêng của worker thuộc StepExecution hoặc object riêng cho worker.
- Nếu thực sự phải cập nhật state dùng chung, dùng cơ chế đồng bộ hoặc kho dữ liệu có atomic operation.

## 3. StepScope trong Spring Batch

StepScope là scope dành cho bean gắn với một StepExecution. Khi step bắt đầu, Spring Batch tạo hoặc lấy instance scoped bean tương ứng; bean có thể đọc dữ liệu runtime từ step context, job context và job parameters.

Một bean step-scoped thường được khai báo bằng @StepScope:

~~~java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

Reader được tạo khi step execution có sẵn JobParameters. Nhờ đó, cùng một cấu hình job có thể xử lý các file khác nhau ở những lần chạy khác nhau.

StepScope thường được triển khai thông qua scoped proxy. Bean được inject vào cấu hình step là proxy; khi step đang thực thi, proxy tìm target instance gắn với StepExecution hiện tại. Vì vậy, không nên gọi method của scoped bean trong lúc khởi tạo application context nếu chưa có StepExecution đang hoạt động.

## 4. Late binding từ execution context

Step-scoped bean có thể lấy giá trị từ nhiều nguồn:

| SpEL | Nguồn dữ liệu |
|---|---|
| `#{jobParameters['batchId']}` | JobParameters của job hiện tại |
| `#{jobExecutionContext['referenceFile']}` | Job ExecutionContext |
| `#{stepExecutionContext['partitionId']}` | Step ExecutionContext của step hiện tại |

Ví dụ worker reader nhận một khoảng ID do Partitioner tạo:

~~~java
@Bean
@StepScope
JdbcPagingItemReader<Order> partitionReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxIdExclusive) {

    // Tạo reader theo range của StepExecution hiện tại.
    return createOrderReader(dataSource, minId, maxIdExclusive);
}
~~~

Late binding giúp tái sử dụng một định nghĩa bean cho nhiều step execution với các giá trị khác nhau. Nhưng giá trị được inject không tự trở thành dữ liệu thread-local. Nếu cùng target bean được nhiều thread gọi, các field trong target vẫn có thể bị truy cập đồng thời.

Hãy dùng late binding cho cấu hình của execution như input file, range, tenant hoặc batch ID. Không dùng một field mutable của scoped bean làm nơi lưu “item hiện tại” nếu nhiều thread có thể gọi bean đó cùng lúc.

## 5. JobScope trong Spring Batch

JobScope tạo một instance bean trong phạm vi một JobExecution. Nó phù hợp với dữ liệu/cấu hình cần dùng chung giữa nhiều step của cùng lần chạy job, ví dụ một tham chiếu artifact hoặc một giá trị đã được chuẩn bị ở đầu job.

Ví dụ:

~~~java
@Bean
@JobScope
BatchRunSettings batchRunSettings(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return new BatchRunSettings(
            LocalDate.parse(businessDate),
            batchId);
}
~~~

Job-scoped bean được chia sẻ trong phạm vi JobExecution. Nếu các step hoặc flow song song cùng truy cập bean đó, chúng có thể gọi cùng một instance. Vì vậy, job-scoped bean nên chứa cấu hình bất biến hoặc state được bảo vệ rõ ràng; không nên dùng nó như một mutable scratchpad cho nhiều worker.

JobScope có một giới hạn quan trọng trong multi-thread execution: Spring Batch không kiểm soát mọi thread do một multi-threaded step tự tạo. Context của scope không phải lúc nào cũng được thiết lập đúng trong các thread đó. Vì vậy, tài liệu Spring Batch khuyến cáo không dùng JobScope trong multi-threaded hoặc partitioned steps khi bean cần được truy cập từ worker thread. Hãy kiểm tra hướng dẫn của đúng phiên bản và cách executor được cấu hình; thiết kế an toàn thường là truyền dữ liệu cần thiết vào worker context và dùng StepScope cho từng StepExecution.

Ngay cả trong parallel flow, nơi mỗi nhánh có StepExecution riêng nhưng thuộc cùng JobExecution, JobScope vẫn đại diện cho một phạm vi job chung. Nếu nhiều nhánh cùng ghi mutable state vào job-scoped bean, cần cơ chế đồng bộ hoặc thay đổi thiết kế để mỗi nhánh ghi kết quả riêng.

## 6. Multi-threaded step: một StepExecution, nhiều thread xử lý

Trong multi-threaded step, một step dùng TaskExecutor để xử lý các chunk hoặc phần việc trên nhiều thread. Khác với partitioning, mô hình này không nhất thiết tạo một StepExecution riêng cho mỗi worker. Các worker có thể cùng làm việc trong một step execution và dùng chung một số component.

Điều đó có ý nghĩa với scope:

- Step-scoped bean thuộc StepExecution của step đó; không nên mặc định rằng mỗi worker thread có một target instance riêng.
- Nếu reader, processor hoặc writer target được gọi đồng thời, component cần thread-safe hoặc phải được bọc/thiết kế để tránh truy cập đồng thời không an toàn.
- Step ExecutionContext thuộc step execution; không dùng nó làm nơi nhiều thread cập nhật cùng một key mà không có quy tắc đồng bộ.
- Transaction thường được tạo và quản lý trong thread thực hiện chunk; transaction của thread này không tự lan sang thread khác.

Ví dụ một multi-threaded chunk step:

~~~java
@Bean
Step multiThreadedImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, ImportedOrder> processor,
        ItemWriter<ImportedOrder> writer,
        TaskExecutor chunkTaskExecutor) {

    return new StepBuilder("multiThreadedImportStep", jobRepository)
            .<Order, ImportedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .taskExecutor(chunkTaskExecutor)
            .build();
}
~~~

Trong cấu hình này, không nên giả định reader hoặc writer được gọi tuần tự. Một FlatFileItemReader thông thường có cursor và state mutable; nếu nhiều thread cùng gọi read(), cần một chiến lược an toàn. Có thể serialize thao tác đọc bằng synchronized wrapper như SynchronizedItemStreamReader trong trường hợp phù hợp, hoặc chọn partitioning để mỗi worker có reader riêng. Việc đồng bộ read không làm toàn bộ pipeline tuần tự và cũng không tự bảo đảm thứ tự item ở writer.

Với multi-threaded step, @StepScope vẫn hữu ích cho late binding và lifecycle theo step, nhưng nó không phải giải pháp tự động tạo một instance riêng cho mỗi chunk thread. Hãy xác định rõ component nào được gọi đồng thời và kiểm tra thread safety của target object.

## 7. Partitioning: mỗi worker có StepExecution riêng

Partitioning chia dữ liệu thành nhiều partition và tạo một StepExecution cho mỗi worker partition. Mỗi execution có Step ExecutionContext riêng, vì vậy đây thường là mô hình phù hợp khi cần state reader/writer độc lập theo worker.

Ví dụ:

| Worker | StepExecution context | Reader |
|---|---|---|
| partition0 | minId=1, maxId=1001 | Reader cho range 1–1000 |
| partition1 | minId=1001, maxId=2001 | Reader cho range 1001–2000 |
| partition2 | minId=2001, maxId=3001 | Reader cho range 2001–3000 |

Worker reader có thể là step-scoped:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<Order> workerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxIdExclusive) {

    return new JdbcCursorItemReaderBuilder<Order>()
            .name("workerReader")
            .dataSource(dataSource)
            .sql("""
                    select id, customer_id, amount
                    from orders
                    where id >= ? and id < ?
                    order by id
                    """)
            .preparedStatementSetter(ps -> {
                ps.setLong(1, minId);
                ps.setLong(2, maxIdExclusive);
            })
            .rowMapper(orderRowMapper())
            .saveState(true)
            .build();
}
~~~

Mỗi worker StepExecution nhận context riêng, vì vậy Spring Batch có thể tạo target reader riêng cho từng partition. Cursor, checkpoint và resource của một worker không bị chia sẻ với worker khác, miễn là bean thực sự được tạo trong StepScope và worker không giữ một resource singleton bên ngoài.

Partitioning không tự giải quyết tranh chấp dữ liệu ở database. Nếu hai partition có range giao nhau hoặc cùng cập nhật một business key, vẫn có thể có duplicate, lock contention hoặc lost update. Partitioner cần tạo phạm vi ổn định và không giao nhau.

## 8. Parallel flow: nhiều StepExecution trong một JobExecution

Parallel flow chạy nhiều nhánh độc lập của job đồng thời, thường qua split(TaskExecutor). Mỗi nhánh có các StepExecution riêng nhưng cùng thuộc một JobExecution.

Điều này tạo ra hai phạm vi state:

- StepScope tách target bean theo StepExecution của từng step/nhánh.
- JobScope có phạm vi chung của JobExecution và có thể được nhiều nhánh truy cập.

Ví dụ cấu trúc:

~~~java
@Bean
Job parallelJob(
        JobRepository jobRepository,
        Flow customerFlow,
        Flow productFlow,
        TaskExecutor flowExecutor) {

    return new JobBuilder("parallelJob", jobRepository)
            .start(customerFlow)
            .split(flowExecutor)
            .add(productFlow)
            .end()
            .build();
}
~~~

Nếu mỗi flow dùng một reader step-scoped, mỗi step execution có reader riêng. Nếu hai flow cùng dùng một singleton service stateless, service có thể được chia sẻ. Nếu hai flow cùng dùng một job-scoped bean có field mutable, chúng có thể tranh chấp cùng state.

Không giả định flow A luôn chạy trước flow B theo thứ tự khai báo. Nếu flow B cần dữ liệu do flow A tạo, hãy đặt một step chuẩn bị trước split, lưu dữ liệu trong kho chung có semantics rõ ràng, hoặc chuyển bước phụ thuộc xuống sau khi split hoàn tất.

## 9. So sánh các mô hình thực thi và phạm vi bean

| Mô hình | Execution được tạo | Component có thể được gọi đồng thời | Cách tổ chức state |
|---|---|---|---|
| Step tuần tự | Một StepExecution tại một thời điểm | Thường không có nhiều chunk thread trong cùng step | StepScope phù hợp cho state của step |
| Multi-threaded step | Một StepExecution, nhiều worker thread xử lý | Reader/processor/writer có thể được gọi đồng thời | Component phải thread-safe; không coi StepScope là per-thread |
| Partitioning | Một StepExecution cho mỗi partition worker | Các worker step chạy đồng thời | StepScope và Step ExecutionContext riêng cho từng partition |
| Parallel flow | Nhiều StepExecution trong cùng JobExecution | Các step/flow có thể chạy đồng thời | StepScope tách theo step; JobScope là phạm vi job chung |
| Remote partitioning | Worker StepExecution chạy ở process/node khác | Worker phân tán có thể chạy đồng thời | Truyền partition context qua cơ chế partition; tránh phụ thuộc state trong bộ nhớ manager |

Mô hình phù hợp phụ thuộc loại nguồn dữ liệu và cách chia công việc. Nếu reader không thread-safe và cần checkpoint độc lập, partitioning thường dễ kiểm soát hơn multi-threaded step. Nếu các flow độc lập về dữ liệu và logic, parallel flow có thể phù hợp.

## 10. Prototype không phải giải pháp tự động cho multi-thread

Một số người chuyển bean từ singleton sang prototype với hy vọng mỗi thread sẽ có instance riêng. Điều này không tự xảy ra khi bean prototype được inject vào một singleton:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public class MutableProcessorState {
    private int currentCount;
}

@Component
public class ImportService {

    private final MutableProcessorState state;

    public ImportService(MutableProcessorState state) {
        this.state = state;
    }
}
~~~

Trong ví dụ này, Spring tạo một MutableProcessorState khi tạo ImportService và singleton giữ instance đó. Các thread gọi ImportService vẫn có thể dùng chung state.

Nếu thật sự cần một prototype instance mới cho mỗi lần sử dụng, có thể inject ObjectProvider:

~~~java
@Component
public class ImportService {

    private final ObjectProvider<MutableProcessorState> stateProvider;

    public ImportService(
            ObjectProvider<MutableProcessorState> stateProvider) {
        this.stateProvider = stateProvider;
    }

    public void processBatch() {
        MutableProcessorState state = stateProvider.getObject();
        // Instance mới cho lần lấy này.
    }
}
~~~

Tuy nhiên, prototype instance không tự được Spring quản lý đầy đủ lifecycle sau khi trả về cho client. Ứng dụng cần giải phóng resource nếu object giữ file handle, cursor hoặc tài nguyên khác. Trong Spring Batch, StepScope thường là lựa chọn tự nhiên hơn khi state thuộc một StepExecution.

## 11. Thiết kế reader an toàn khi nhiều thread đọc

Reader thường là component dễ gặp vấn đề nhất vì giữ cursor, page, offset hoặc trạng thái stream.

Các lựa chọn:

**Reader thread-safe:** dùng reader được thiết kế để hỗ trợ concurrent reads theo hợp đồng của nó. Cần đọc tài liệu cụ thể; không suy ra thread safety chỉ từ việc bean là singleton hoặc step-scoped.

**SynchronizedItemStreamReader:** bọc reader để đồng bộ lời gọi read(). Cách này serialize phần đọc, nhưng processor và writer vẫn có thể chạy đồng thời. Thứ tự xử lý/ghi có thể khác thứ tự đọc; cần đánh giá restart và reprocessing semantics.

**Partitioning:** tạo một reader instance riêng cho mỗi worker StepExecution và chia input thành các phạm vi không giao nhau. Đây thường là lựa chọn rõ ràng khi nguồn dữ liệu có thể phân vùng.

**Reader stateless theo page/range:** thiết kế reader sao cho mỗi lần đọc dùng khóa hoặc page token rõ ràng, tránh một cursor mutable dùng chung.

Ví dụ wrapper đồng bộ:

~~~java
@Bean
@StepScope
SynchronizedItemStreamReader<Order> synchronizedReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    FlatFileItemReader<Order> delegate = createReader(inputFile);

    return new SynchronizedItemStreamReaderBuilder<Order>()
            .delegate(delegate)
            .build();
}
~~~

Wrapper chỉ đồng bộ read operation. Nó không làm writer, processor, ExecutionContext hoặc external side effects trở nên thread-safe. Nếu cần thứ tự output chính xác, hãy lưu sequence key và sắp xếp/tổng hợp ở bước sau.

## 12. Processor và writer trong multi-thread execution

Processor thường dễ làm thread-safe nếu chỉ chuyển đổi input thành output bằng biến cục bộ. Tránh lưu item hiện tại hoặc trạng thái tạm trong field:

~~~java
@Component
public class OrderProcessor implements ItemProcessor<OrderInput, Order> {

    @Override
    public Order process(OrderInput input) {
        BigDecimal normalizedAmount =
                input.amount().setScale(2, RoundingMode.HALF_UP);
        return new Order(input.orderId(), input.customerId(), normalizedAmount);
    }
}
~~~

Writer cần được xem xét kỹ hơn. Writer có thể giữ buffer, file handle, batch statement hoặc trạng thái retry. Nếu nhiều thread gọi cùng writer:

- Kiểm tra implementation có hỗ trợ concurrent writes không.
- Nếu ghi database, dùng transaction/connection theo thread và tránh shared mutable statement.
- Nếu ghi file, thường dùng output riêng theo worker hoặc serialize toàn bộ thao tác ghi bằng cơ chế phù hợp.
- Nếu gửi API/message, dùng idempotency key và giới hạn concurrency theo dịch vụ ngoài.
- Không dùng một mutable collection singleton làm buffer chung nếu không có đồng bộ.

Một processor/writer stateless vẫn có thể gọi một dependency không thread-safe. Cần xem toàn bộ dependency graph, không chỉ class được đánh dấu @Component.

## 13. ExecutionContext không phải thread-local storage

Step ExecutionContext và Job ExecutionContext là state được Spring Batch quản lý và lưu vào JobRepository theo lifecycle/transaction tương ứng. Chúng không phải một map đồng bộ để các thread tùy ý trao đổi dữ liệu tức thời.

Trong multi-threaded step, nhiều chunk có thể cùng thuộc một StepExecution. Nếu các thread cùng ghi một key như currentOffset, lastId hoặc count vào cùng execution context, giá trị có thể bị ghi đè hoặc cập nhật sai thứ tự. Không nên dùng context để đếm số item xử lý đồng thời nếu không có cơ chế đồng bộ và semantics checkpoint rõ ràng.

Trong parallel flow, các step có StepExecutionContext riêng nhưng có thể truy cập cùng Job ExecutionContext. Hai flow ghi cùng key có thể tạo race condition hoặc kết quả phụ thuộc thứ tự hoàn tất.

Các lựa chọn an toàn:

- Dùng Step ExecutionContext cho checkpoint do một worker sở hữu.
- Dùng key riêng cho từng partition/flow khi cần lưu metadata nhỏ.
- Để một step tổng hợp sau split đọc kết quả đã được ghi vào database.
- Dùng bảng coordination có unique key/atomic update nếu cần trạng thái chung bền vững.
- Dùng concurrent data structure cho metric tạm thời trong một JVM, nhưng không xem nó là checkpoint bền vững.

## 14. ThreadLocal và scope context

Một số cơ chế Spring gắn execution context với thread hiện tại thông qua ThreadLocal. Đây là cách framework xác định step/job đang hoạt động khi một scoped proxy cần lấy target bean.

Không nên tự tạo ThreadLocal để lưu JobParameters hoặc StepExecution rồi giả định nó tự truyền sang thread do TaskExecutor tạo. ThreadLocal không tự kế thừa sang thread pool worker, và thread pool tái sử dụng thread giữa nhiều task. Nếu tự quản lý ThreadLocal, phải đăng ký và dọn dẹp đúng cách trong finally; nếu không, dữ liệu execution trước có thể rò sang task sau.

Spring Batch thiết lập scope context trong các đường thực thi mà framework quản lý. Với thread do ứng dụng tự tạo hoặc executor tùy chỉnh, không giả định context đã được truyền. Hãy dùng cơ chế partition/step execution được Spring Batch hỗ trợ, truyền dữ liệu tường minh qua task context hoặc thiết kế worker độc lập.

Đặc biệt, không gọi một step-scoped hoặc job-scoped proxy từ thread tùy ý ngoài vòng đời step/job nếu không có scope context tương ứng. Có thể gặp lỗi không tìm thấy context đang hoạt động hoặc lấy nhầm state.

## 15. Transaction và scope là hai khái niệm độc lập

Scope không quyết định transaction. Một step-scoped bean có thể được gọi trong nhiều transaction chunk; một singleton repository có thể tham gia transaction khác nhau trên các thread khác nhau.

Trong multi-threaded step:

- Mỗi chunk thường chạy trong transaction riêng trên thread xử lý chunk.
- Transaction của thread A không tự lan sang thread B.
- Không chia sẻ JDBC Connection, EntityManager hoặc TransactionStatus giữa worker thread.
- Một chunk rollback không tự rollback chunk đã commit của thread khác.

Trong partitioning, mỗi worker StepExecution xử lý chunk trong transaction riêng. Trong parallel flow, các step ở các nhánh cũng có transaction riêng. Nếu toàn bộ job cần công bố kết quả như một đơn vị nghiệp vụ, có thể ghi vào staging theo batch ID rồi chạy bước đối soát/publish sau khi mọi nhánh thành công.

Không dùng @JobScope hoặc @StepScope như một cách để chia sẻ transaction hoặc khóa dữ liệu. Nếu cần transaction coordination, phải thiết kế qua transaction manager, database constraint, locking hoặc cơ chế phối hợp phù hợp.

## 16. JobScope trong worker thread: giới hạn và cách thay thế

JobScope rất hữu ích khi một bean cần lấy tham số job và được dùng trong các step tuần tự. Nhưng trong multi-threaded hoặc partitioned step, worker thread có thể không có job scope context được thiết lập như thread điều phối. Tài liệu Spring Batch khuyến cáo tránh job-scoped bean trong những worker path này.

Thay vì để worker thread tự truy cập một mutable job-scoped bean:

1. Đọc JobParameters hoặc Job ExecutionContext ở nơi scope context được hỗ trợ.
2. Đưa các giá trị cần thiết vào partition Step ExecutionContext hoặc cấu hình worker.
3. Dùng StepScope để tạo bean cho từng worker StepExecution.
4. Giữ dữ liệu cấu hình chung immutable.
5. Nếu cần kết quả chung, ghi từng worker result riêng rồi tổng hợp.

Ví dụ Partitioner đưa batch ID và range vào context:

~~~java
Map<String, ExecutionContext> partitions = new LinkedHashMap<>();

ExecutionContext context = new ExecutionContext();
context.putString("batchId", batchId);
context.putLong("minId", startId);
context.putLong("maxIdExclusive", endId);

partitions.put("partition0", context);
~~~

Worker bean đọc giá trị từ step context:

~~~java
@Bean
@StepScope
OrderReader workerReader(
        @Value("#{stepExecutionContext['batchId']}") String batchId,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxIdExclusive']}") Long maxId) {

    return new OrderReader(batchId, minId, maxId);
}
~~~

Mỗi partition nhận giá trị riêng qua StepExecutionContext. Đây là mô hình phù hợp hơn cho state thuộc worker, thay vì để worker truy cập một bean job-scoped mutable dùng chung.

## 17. Các chiến lược bảo vệ shared state

Khi state thực sự phải được chia sẻ, chọn cơ chế theo yêu cầu:

| Chiến lược | Phù hợp khi | Giới hạn |
|---|---|---|
| Immutable object | Dữ liệu cấu hình chỉ đọc | Không dùng cho kết quả cần cập nhật |
| Method arguments/local variables | State thuộc một lần gọi | Cần truyền tham số qua các tầng |
| StepScope/partition context | State thuộc một StepExecution/partition | Không tự tạo một instance cho mỗi chunk thread |
| synchronized/Lock | Cần tuần tự hóa một vùng critical section trong JVM | Có thể giảm throughput; không bảo vệ giữa nhiều process |
| Atomic/concurrent collection | Counter/cache tạm thời trong một JVM | Không bền vững qua restart; semantics nghiệp vụ vẫn cần xác định |
| Database unique constraint/atomic update | State chung cần bền vững và nhiều node cùng cập nhật | Có thể tạo contention; cần thiết kế khóa/index |
| Message/coordination service | Worker cần phối hợp qua process/node | Thêm vận hành và xử lý giao nhận/lỗi |

Không nên thêm synchronized quanh toàn bộ processor/writer chỉ để tránh race condition nếu có thể chia state theo partition. Đồng bộ toàn bộ pipeline có thể làm mất lợi ích song song. Chỉ khóa vùng critical section nhỏ và đo ảnh hưởng hiệu năng.

## 18. Scope, resource cleanup và restart

Reader/writer có thể mở file, cursor hoặc connection trong lifecycle của step. StepScope giúp gắn resource với StepExecution để Spring Batch gọi lifecycle tương ứng qua ItemStream hoặc cơ chế bean destruction.

Khi dùng multi-thread execution:

- Không chia sẻ cùng file handle/cursor giữa các worker nếu implementation không hỗ trợ.
- Mỗi partition nên có resource riêng hoặc phạm vi đọc/ghi độc lập.
- Đảm bảo close được gọi khi step kết thúc hoặc thất bại.
- Không lưu resource runtime như Connection, InputStream hoặc EntityManager vào ExecutionContext.
- Lưu checkpoint nhỏ, có thể serialize, để worker khôi phục sau restart.

Scope không thay thế ItemStream. Một reader step-scoped vẫn cần triển khai ItemStream hoặc dùng builder hỗ trợ state để Spring Batch mở, cập nhật và đóng reader đúng thời điểm.

Với restart, giữ partition name/range ổn định và dùng identifying JobParameters giống lần chạy ban đầu. Nếu mỗi lần restart tạo range mới hoặc dùng singleton state lưu vị trí, worker có thể đọc trùng hoặc bỏ sót dữ liệu.

## 19. Cấu hình executor và concurrency

Scope an toàn không đồng nghĩa số thread có thể tăng vô hạn. TaskExecutor cần giới hạn concurrency theo CPU, connection pool, bộ nhớ và giới hạn của hệ thống ngoài.

Ví dụ executor có giới hạn:

~~~java
@Bean
ThreadPoolTaskExecutor batchTaskExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(4);
    executor.setMaxPoolSize(4);
    executor.setQueueCapacity(8);
    executor.setThreadNamePrefix("batch-worker-");
    executor.setWaitForTasksToCompleteOnShutdown(true);
    executor.setAwaitTerminationSeconds(60);
    return executor;
}
~~~

Nếu có bốn worker cùng ghi database, connection pool cần đủ capacity cho worker và các thành phần khác. Nếu worker gọi API ngoài, concurrency phải nằm trong rate limit. Tăng thread count trong khi downstream đã bão hòa có thể làm throughput giảm và tăng timeout.

Theo dõi active thread, queue depth, connection acquisition time, database lock wait, API latency và thời gian từng step. Đặt tên thread giúp liên kết log với flow/worker khi điều tra.

## 20. Kiểm thử scope trong multi-thread execution

Kiểm thử cần xác nhận bean instance và state hoạt động đúng trong đúng mô hình concurrency. Một test chạy tuần tự không thể chứng minh singleton hoặc scoped bean an toàn khi nhiều thread cùng truy cập.

Các tình huống nên kiểm tra:

1. Singleton stateless: nhiều thread gọi cùng service với dữ liệu khác nhau; xác nhận không có cross-talk.
2. Singleton mutable: nếu có state, chạy đồng thời để xác nhận cơ chế đồng bộ hoặc phát hiện race.
3. StepScope late binding: mỗi StepExecution nhận đúng JobParameters/Step ExecutionContext.
4. Multi-threaded step: xác nhận reader, processor và writer an toàn khi được gọi đồng thời; không giả định StepScope tạo target per-thread.
5. Partitioning: mỗi worker có target reader riêng và range/context đúng.
6. Parallel flow: các step có StepScope riêng; không ghi đè Job ExecutionContext key dùng chung.
7. JobScope: không dựa vào job-scoped mutable bean trong worker thread; kiểm tra giới hạn scope context theo cách executor thực tế.
8. Prototype injection: xác nhận prototype được lấy mới qua ObjectProvider khi đó là yêu cầu.
9. Resource lifecycle: xác nhận reader/writer được close và không giữ resource sau step.
10. Restart: worker khôi phục checkpoint đúng sau khi một partition hoặc step thất bại.
11. Transaction isolation: rollback ở một worker không làm mất chunk đã commit của worker khác.
12. Shutdown: dừng job khi worker đang hoạt động và xác nhận resource được giải phóng theo thiết kế.

Có thể dùng CountDownLatch hoặc CyclicBarrier trong test để buộc nhiều thread cùng đi vào một đoạn code, từ đó tạo race condition có thể tái hiện. Tránh dựa vào Thread.sleep() để đoán thời điểm thread chạy. Với test integration, dùng JobRepository và transaction manager thực tế của cấu hình test; kiểm tra cả dữ liệu cuối, không chỉ BatchStatus.

## 21. Những lỗi thường gặp

**Cho rằng singleton bean an toàn vì Spring quản lý.** Singleton chỉ nói về một instance trong ApplicationContext. Nếu có mutable field, nhiều thread có thể ghi đè state.

**Cho rằng StepScope là per-thread.** StepScope gắn với StepExecution, không phải cam kết mỗi chunk thread có một target riêng. Component vẫn phải thread-safe nếu được nhiều thread gọi.

**Dùng JobScope cho state mutable trong worker.** JobScope thuộc JobExecution và có giới hạn context trong multi-thread/partitioned execution. Truyền dữ liệu vào worker context và dùng StepScope phù hợp hơn.

**Dùng prototype nhưng inject trực tiếp vào singleton.** Singleton có thể giữ một prototype instance duy nhất. Dùng ObjectProvider nếu thật sự cần instance mới theo lần lấy.

**Chia sẻ reader có cursor.** Reader không thread-safe có thể đọc trùng/bỏ sót item. Dùng reader an toàn, wrapper đồng bộ phù hợp hoặc partitioning.

**Ghi cùng key trong ExecutionContext từ nhiều thread.** State có thể bị ghi đè hoặc checkpoint sai. Phân chia quyền sở hữu key và tổng hợp sau.

**Dùng ThreadLocal tự tạo mà không truyền/dọn context.** Thread pool tái sử dụng thread; state cũ có thể rò sang task mới. Dùng scope context của framework hoặc truyền dữ liệu tường minh.

**Cho rằng scope chia sẻ transaction.** Transaction gắn với execution thread và transaction manager; bean scope không làm transaction lan sang thread khác.

**Tăng concurrency mà không tính tài nguyên.** Database pool, API quota và CPU có thể trở thành bottleneck. Giới hạn executor và theo dõi tải.

## 22. Quy trình chọn scope cho worker

Khi một bean được dùng trong multi-thread execution, hãy xác định:

1. Bean giữ state hay chỉ chứa logic stateless?
2. State thuộc toàn application, một JobExecution, một StepExecution, một partition hay một lần gọi?
3. Có bao nhiêu thread có thể gọi cùng target instance?
4. Framework có thiết lập scope context trong các thread đó không?
5. Bean hoặc dependency có hỗ trợ concurrent use không?
6. State có cần tồn tại qua restart hay chỉ là dữ liệu tạm?
7. Resource cần close ở thời điểm nào?
8. Có thể chia state theo partition thay vì đồng bộ state chung không?
9. Có cần ghi kết quả vào database/ExecutionContext và ai sở hữu từng key?
10. Đã có concurrency test và restart test chưa?

Hướng dẫn lựa chọn thường dùng:

- Service stateless: singleton.
- Reader/writer cần JobParameters hoặc Step ExecutionContext: StepScope.
- State riêng của partition: StepScope cùng Step ExecutionContext của partition.
- Cấu hình immutable dùng trong một job: có thể cân nhắc JobScope, nhưng tránh để worker thread cập nhật mutable state; lưu ý giới hạn JobScope trong multi-threaded/partitioned steps.
- Object mới theo mỗi lần gọi: ObjectProvider/prototype nếu lifecycle phù hợp.
- State chung cần bền vững: database hoặc coordination store thay vì field singleton.

## Kết luận

Scope trong multi-thread execution quyết định bean được tạo và chia sẻ ở phạm vi nào, nhưng không tự bảo đảm thread safety. Singleton thường được nhiều flow hoặc worker gọi đồng thời; StepScope gắn với StepExecution chứ không phải một instance riêng cho mỗi chunk thread; JobScope có phạm vi JobExecution và không được khuyến nghị cho worker path trong multi-threaded hoặc partitioned steps khi scope context không được bảo đảm.

Hãy giữ service stateless, dùng StepScope cho cấu hình và state thuộc worker execution, tạo reader/writer riêng theo partition khi cần checkpoint độc lập, và tránh dùng ExecutionContext hoặc ThreadLocal như cơ chế đồng bộ tùy tiện. Kiểm tra thread safety của toàn bộ dependency graph, transaction boundary và resource lifecycle. Cuối cùng, chạy concurrency và restart test để xác nhận không có state bị trộn, item bị mất hoặc side effect trùng khi các worker chạy đồng thời.
