# Bean scoped theo step

Trong Spring Batch, `@StepScope` cho phép khai báo một bean có vòng đời gắn với một lần thực thi Step (`StepExecution`). Bean chỉ được tạo khi Step context đã sẵn sàng và có thể nhận các giá trị runtime như `JobParameters`, `StepExecutionContext` hoặc `JobExecutionContext` thông qua late binding.

Điều này đặc biệt hữu ích với các thành phần như `ItemReader`, `ItemProcessor` và `ItemWriter` cần biết file đầu vào, ngày nghiệp vụ, khoảng ID của partition hoặc một giá trị chỉ được xác định khi Job bắt đầu chạy. `@StepScope` cũng giúp mỗi StepExecution có instance riêng của component có state, thay vì dùng chung một object singleton cho toàn bộ application context.

## 1. Bean scope là gì?

Trong Spring Framework, bean scope xác định Spring tạo và quản lý instance bean trong phạm vi nào. Ví dụ, bean `singleton` mặc định thường có một instance trong application context; bean `prototype` tạo instance mới theo yêu cầu lấy bean.

Spring Batch bổ sung các scope gắn với vòng đời batch:

- **Step scope:** một target bean instance cho mỗi `StepExecution` đang chạy.
- **Job scope:** một target bean instance cho mỗi `JobExecution`.

`@StepScope` là annotation thuận tiện để khai báo bean thuộc step scope. Nó tương đương việc khai báo scope `step` với scoped proxy.

Ví dụ:

```java
@Bean
@StepScope
public ItemReader<Order> orderReader() {
    return new CustomOrderReader();
}
```

Bean trên không được tạo thành target instance ngay khi Spring khởi động application context. Spring tạo một proxy để các bean khác có thể tham chiếu đến nó; target thực tế được tạo khi một StepExecution phù hợp đang hoạt động và bean được sử dụng.

## 2. Vì sao cần @StepScope?

Các bean singleton được tạo trước khi Job chạy, trong khi nhiều thông tin đầu vào chỉ có khi Job được khởi chạy. Ví dụ, cùng một Job có thể chạy cho nhiều ngày nghiệp vụ hoặc nhiều file khác nhau:

```text
Lần chạy A: businessDate=2026-11-14, inputFile=orders-14.csv
Lần chạy B: businessDate=2026-11-15, inputFile=orders-15.csv
```

Nếu reader singleton giữ đường dẫn file trong field, hai lần chạy có thể vô tình dùng chung hoặc ghi đè state. `@StepScope` cho phép reader nhận tham số của StepExecution hiện tại và có instance riêng cho từng lần thực thi Step.

Các lợi ích chính:

- **Late binding:** đọc JobParameters hoặc ExecutionContext tại thời điểm Step chạy.
- **State riêng theo StepExecution:** reader/writer có state không cần chia sẻ target instance giữa các StepExecution khác nhau.
- **Cấu hình linh hoạt:** cùng một Step definition có thể chạy với file, ngày hoặc phạm vi dữ liệu khác nhau.
- **Hỗ trợ partitioning:** mỗi partition có StepExecution và có thể nhận context riêng.
- **Tách cấu hình khỏi code khởi tạo:** giá trị runtime được inject thay vì đọc thủ công từ static field hoặc singleton mutable state.

Không cần đặt mọi bean trong application thành step-scoped. Các service stateless, mapper bất biến hoặc repository thường vẫn phù hợp với singleton. Dùng `@StepScope` khi bean thực sự cần dữ liệu runtime hoặc state gắn với StepExecution.

## 3. Cách @StepScope hoạt động

`@StepScope` tạo scoped proxy. Proxy có thể được inject vào cấu hình Step từ lúc application context khởi tạo, nhưng chỉ khi Step đang chạy mới có context để tạo hoặc truy cập target bean tương ứng.

```text
Application context khởi động
        |
        +--> Tạo scoped proxy cho orderReader
        |
        +--> Inject proxy vào Step definition

Job bắt đầu importOrdersStep
        |
        +--> Tạo / kích hoạt StepExecution
        |
        +--> Step scope có context hiện tại
        |
        +--> Proxy tạo hoặc truy cập target orderReader
        |
        +--> Reader nhận JobParameters / StepExecutionContext
        |
        +--> Step xử lý và kết thúc
        |
        +--> Step scope hủy target instance
```

Điểm quan trọng là bean được inject vào Step configuration thường là proxy, không phải target object đã được khởi tạo với tham số runtime. Khi Step gọi reader, proxy chuyển lời gọi đến target instance thuộc StepExecution hiện tại.

Nếu gọi một method của scoped proxy khi không có Step context đang hoạt động, Spring không thể xác định target instance và có thể ném lỗi scope/context, thường với thông báo rằng không có context holder cho step scope. Vì vậy, không nên gọi trực tiếp method của bean step-scoped từ code khởi động application hoặc từ một singleton trước khi Step chạy.

## 4. Late binding từ JobParameters

Một trường hợp phổ biến là reader cần đường dẫn file được truyền khi khởi chạy Job. Có thể dùng `@Value` cùng SpEL để lấy JobParameter:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Job có thể được khởi chạy với tham số:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "data/orders-2026-11-15.csv")
        .addString("businessDate", "2026-11-15")
        .toJobParameters();
```

Khi `orderReader` được sử dụng trong Step, Spring Batch cung cấp JobParameters của JobExecution hiện tại. Reader sẽ dùng đúng file được chỉ định cho lần chạy đó.

Trong ví dụ, `.saveState(true)` bật việc lưu checkpoint của reader để hỗ trợ restart. `@StepScope` không tự lưu vị trí đọc; hai chức năng này có vai trò khác nhau: scope quản lý vòng đời bean, còn save state/ExecutionContext quản lý tiến độ xử lý.

Nên kiểm tra tham số bắt buộc trước khi tạo resource. Nếu `inputFile` thiếu hoặc rỗng, hãy báo lỗi cấu hình rõ ràng thay vì để reader thất bại với một lỗi khó hiểu khi mở file.

## 5. Late binding từ StepExecutionContext

Với partitioned Step, mỗi worker partition có một StepExecution và ExecutionContext riêng. Partitioner có thể đặt giới hạn dữ liệu vào context; reader step-scoped nhận các giá trị đó khi target instance được tạo.

Ví dụ partitioner tạo context:

```java
ExecutionContext context = new ExecutionContext();
context.putLong("minId", 1L);
context.putLong("maxId", 1000L);
```

Reader đọc giới hạn từ StepExecutionContext:

```java
@Bean
@StepScope
public JdbcPagingItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        PagingQueryProvider queryProvider,
        RowMapper<Order> rowMapper,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("partitionOrderReader")
            .dataSource(dataSource)
            .queryProvider(queryProvider)
            .parameterValues(Map.of("minId", minId, "maxId", maxId))
            .rowMapper(rowMapper)
            .pageSize(100)
            .saveState(true)
            .build();
}
```

Mỗi partition có thể nhận một cặp `minId`/`maxId` khác nhau. Vì bean reader thuộc step scope, target instance của từng StepExecution được tạo với context tương ứng.

Query của `PagingQueryProvider` cần dùng các tham số này để lọc đúng phạm vi và có thứ tự ổn định, ví dụ `ORDER BY order_id` với `order_id` là khóa xác định duy nhất từng bản ghi.

## 6. Late binding từ JobExecutionContext

JobExecutionContext chứa dữ liệu ở phạm vi JobExecution, có thể được chia sẻ giữa các Step trong cùng lần thực thi Job. Bean step-scoped có thể đọc dữ liệu đó:

```java
@Bean
@StepScope
public ItemProcessor<Order, EnrichedOrder> enrichOrderProcessor(
        @Value("#{jobExecutionContext['referenceVersion']}") String referenceVersion) {

    return order -> enrichUsingReferenceVersion(order, referenceVersion);
}
```

Ví dụ, một Step trước đó xác định version của bảng tham chiếu và lưu vào JobExecutionContext. Step sau dùng processor step-scoped để nhận version tương ứng.

Nên phân biệt các nguồn binding:

| Biểu thức | Nguồn dữ liệu | Phạm vi |
|---|---|---|
| `#{jobParameters['inputFile']}` | JobParameters | Tham số của JobExecution |
| `#{stepExecutionContext['minId']}` | Step ExecutionContext | Riêng StepExecution hiện tại |
| `#{jobExecutionContext['referenceVersion']}` | Job ExecutionContext | Dùng chung giữa các Step của JobExecution |

JobParameters thường là đầu vào cố định của lần chạy. ExecutionContext chứa trạng thái được tạo trong lúc Job/Step thực thi. Chọn đúng scope để tránh lưu checkpoint của reader vào nơi không phù hợp.

## 7. Dùng @StepScope cho ItemReader

`ItemReader` thường là component cần step scope nhất vì nó có thể phụ thuộc file, query parameter hoặc state vị trí đọc. Reader tích hợp sẵn như `FlatFileItemReader`, `JdbcPagingItemReader` và `JdbcCursorItemReader` có thể lưu trạng thái thông qua `ItemStream`.

Ví dụ reader nhận ngày nghiệp vụ:

```java
@Bean
@StepScope
public FlatFileItemReader<Order> dailyOrderReader(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    Resource resource = new FileSystemResource(
            "data/orders-" + businessDate + ".csv"
    );

    return new FlatFileItemReaderBuilder<Order>()
            .name("dailyOrderReader")
            .resource(resource)
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

Reader được tạo theo StepExecution với file phù hợp. Tên reader phải ổn định giữa các lần restart; nếu đổi tên, key nội bộ dùng lưu state có thể thay đổi và reader có thể không tìm thấy checkpoint cũ.

Nếu file có thể bị thay thế giữa lần chạy đầu và restart, checkpoint theo dòng không còn đảm bảo trỏ đến cùng dữ liệu. Cần giữ file đầu vào ổn định, dùng version/checksum hoặc có quy trình snapshot phù hợp.

## 8. Dùng @StepScope cho ItemProcessor và ItemWriter

Processor hoặc writer cũng có thể cần tham số runtime hoặc state riêng theo StepExecution.

Ví dụ processor nhận ngưỡng nghiệp vụ:

```java
@Bean
@StepScope
public ItemProcessor<Order, Order> minimumAmountProcessor(
        @Value("#{jobParameters['minimumAmount']}") BigDecimal minimumAmount) {

    return order -> order.getAmount().compareTo(minimumAmount) >= 0
            ? order
            : null;
}
```

Processor filter đơn hàng có amount thấp hơn ngưỡng bằng cách trả `null`. Mỗi StepExecution có thể dùng một ngưỡng khác nhau.

Ví dụ writer tạo tên file theo ngày nghiệp vụ:

```java
@Bean
@StepScope
public FlatFileItemWriter<Order> orderWriter(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("dailyOrderWriter")
            .resource(new FileSystemResource(
                    "output/orders-" + businessDate + ".csv"
            ))
            .delimited()
            .names("orderId", "amount")
            .shouldDeleteIfExists(false)
            .saveState(true)
            .build();
}
```

Writer có thể cần thêm cấu hình append/overwrite theo chiến lược restart thực tế. Không nên chọn `shouldDeleteIfExists` hoặc append một cách tùy tiện; thao tác đó phải phù hợp với checkpoint và quy trình tạo file.

Không phải processor hoặc writer nào cũng cần step scope. Nếu chúng stateless và không cần late binding, singleton thường đơn giản hơn.

## 9. Đăng ký scoped bean vào Step

Một bean step-scoped có thể được inject vào cấu hình Step thông qua proxy:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> dailyOrderReader,
        ItemProcessor<Order, Order> minimumAmountProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(dailyOrderReader)
            .processor(minimumAmountProcessor)
            .writer(orderWriter)
            .build();
}
```

Các tham số method của `importOrdersStep()` được Spring inject khi xây dựng Step definition. Với bean step-scoped, đối tượng được inject là scoped proxy. Target reader/processor/writer chỉ được tạo khi StepExecution tương ứng đang hoạt động và Step thực sự gọi đến bean.

Đây là lý do có thể khai báo một Step singleton nhưng vẫn sử dụng các collaborator step-scoped. Step definition mô tả cấu trúc xử lý; các target bean nhận giá trị runtime theo từng StepExecution.

Không gọi `new` để tự tạo component cần scope, vì object tạo thủ công nằm ngoài lifecycle và dependency injection của Spring. Hãy để Spring quản lý bean thông qua `@Bean` hoặc component scanning phù hợp.

## 10. ItemStream và kiểu trả về của @Bean

Một lưu ý quan trọng khi khai báo reader step-scoped là kiểu trả về của phương thức `@Bean`. Spring Batch cần nhận diện reader có triển khai `ItemStream` để gọi `open()`, `update()` và `close()` trong vòng đời Step.

Ví dụ nên khai báo kiểu trả về thể hiện `ItemStreamReader` hoặc class reader cụ thể:

```java
@Bean
@StepScope
public ItemStreamReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
```

`ItemStreamReader<T>` kết hợp `ItemReader<T>` và `ItemStream`. Nếu chỉ khai báo kiểu trả về chung là `ItemReader<T>`, Spring Batch có thể không nhận diện được contract `ItemStream` ở thời điểm cấu hình Step, tùy cách bean/proxy được khai báo. Khi đó callback lưu/khôi phục state có thể không được đăng ký như mong muốn.

Với reader tự viết, hãy đảm bảo kiểu trả về và registration thể hiện rõ `ItemStream`. Nếu reader được bọc trong delegate/wrapper, có thể cần đăng ký stream delegate tường minh bằng `.stream(delegate)` trong cấu hình Step.

## 11. @StepScope và restart

`@StepScope` không tự làm một bean restartable. Scope chỉ quản lý vòng đời target instance theo StepExecution và cho phép late binding. Restartability phụ thuộc component có lưu state cần thiết và nguồn dữ liệu có thể khôi phục đúng vị trí hay không.

Ví dụ, khi Job bị lỗi sau khi reader đã commit đến dòng 500:

1. StepExecution cũ lưu checkpoint reader trong ExecutionContext.
2. Job được restart với cùng identifying JobParameters để tiếp tục cùng JobInstance.
3. Spring Batch tạo StepExecution mới cho lần chạy lại Step.
4. Step scope tạo target reader instance cho StepExecution mới.
5. Reader mở lại và đọc checkpoint đã lưu trong ExecutionContext.

Target bean mới không cần giữ field Java từ process trước. Nó khôi phục trạng thái từ ExecutionContext hoặc nguồn dữ liệu bền vững.

Với reader tích hợp sẵn, bật `.saveState(true)` nếu cần checkpoint và đặt `.name(...)` ổn định. Với custom reader, triển khai `ItemStream`, đọc state trong `open()` và ghi state trong `update()`.

## 12. @StepScope trong partitioning

Partitioning tạo nhiều StepExecution cho worker Step. Mỗi partition có StepExecutionContext riêng và do đó có thể có target bean step-scoped riêng.

```text
Manager Step
   |
   +--> Worker StepExecution partition-0
   |       +--> Step-scoped reader target #0
   |       +--> stepExecutionContext: minId=1, maxId=1000
   |
   +--> Worker StepExecution partition-1
   |       +--> Step-scoped reader target #1
   |       +--> stepExecutionContext: minId=1001, maxId=2000
   |
   +--> Worker StepExecution partition-2
           +--> Step-scoped reader target #2
           +--> stepExecutionContext: minId=2001, maxId=3000
```

Nhờ step scope, mỗi worker có thể dùng cùng một bean definition nhưng target instance nhận giới hạn dữ liệu riêng. Điều này giúp tránh chia sẻ reader state giữa các partition.

Tên partition, tên reader và key trong ExecutionContext cần ổn định để restart. Nếu partitioner tạo tên hoặc phạm vi khác giữa lần chạy đầu và restart, target bean có thể nhận context không còn tương thích với checkpoint cũ.

## 13. @StepScope không đồng nghĩa thread-safe

Một hiểu lầm phổ biến là vì bean có step scope nên nó luôn an toàn khi chạy đa luồng. Điều đó không đúng.

Trong multi-threaded Step, nhiều thread có thể cùng thực thi trong một StepExecution. Bean step-scoped gắn với StepExecution đó có thể được chia sẻ giữa các thread trong cùng Step. Nếu target bean có mutable field hoặc reader không hỗ trợ concurrent access, race condition vẫn có thể xảy ra.

Ví dụ không an toàn:

```java
@Bean
@StepScope
public ItemProcessor<Order, Order> sequenceProcessor() {
    return new ItemProcessor<>() {

        private long sequence;

        @Override
        public Order process(Order order) {
            sequence++;
            return order.withSequence(sequence);
        }
    };
}
```

Nếu nhiều thread cùng gọi processor, việc tăng `sequence` không bảo đảm thứ tự nghiệp vụ hoặc tính đúng đắn. `@StepScope` không tự đồng bộ field và cũng không biến một reader không thread-safe thành thread-safe.

Các hướng thiết kế:

- Ưu tiên processor stateless và dependency bất biến.
- Chỉ dùng mutable state khi component hỗ trợ concurrent access hoặc có đồng bộ phù hợp.
- Với partitioning, dùng StepExecution riêng cho mỗi partition để mỗi partition có target instance riêng.
- Không giả định multi-threaded Step và partitioning có cùng mô hình scope; hãy xem StepExecution nào đang sở hữu bean.
- Kiểm tra thread safety của reader/writer theo tài liệu implementation cụ thể.

## 14. So sánh @StepScope với @JobScope

Hai scope này khác nhau ở phạm vi instance và nguồn dữ liệu runtime.

| Tiêu chí | `@StepScope` | `@JobScope` |
|---|---|---|
| Phạm vi target instance | Một StepExecution | Một JobExecution |
| Có thể truy cập | JobParameters, StepExecutionContext, JobExecutionContext | JobParameters và JobExecutionContext |
| Phù hợp với | Reader/processor/writer phụ thuộc Step hoặc partition | Component dùng chung dữ liệu ở cấp Job giữa nhiều Step |
| Số instance trong một Job | Có thể có nhiều, mỗi StepExecution một instance | Một target cho JobExecution |
| Restart | Target mới cho StepExecution mới; state cần khôi phục từ metadata | Target mới cho JobExecution mới; dữ liệu cần giữ qua restart phải được lưu bền vững |

Ví dụ `@JobScope`:

```java
@Bean
@JobScope
public SomeJobCoordinator jobCoordinator(
        @Value("#{jobParameters['businessDate']}") String businessDate) {
    return new SomeJobCoordinator(businessDate);
}
```

Nếu một reader cần giới hạn `minId` riêng của từng partition, `@StepScope` là lựa chọn phù hợp vì mỗi partition có StepExecutionContext riêng. Nếu một component cần dữ liệu chung cho toàn JobExecution và được nhiều Step sử dụng, `@JobScope` có thể phù hợp hơn.

Không nên dùng `@JobScope` cho một reader có state vị trí đọc riêng của từng partition, vì target instance theo JobExecution có thể bị chia sẻ giữa nhiều worker StepExecution.

## 15. Những lỗi thường gặp khi dùng @StepScope

### Truy cập bean ngoài Step context

Scoped proxy được inject lúc application khởi động, nhưng target chỉ có thể được lấy khi Step context hoạt động. Gọi method quá sớm từ một singleton hoặc trong `@PostConstruct` có thể gây lỗi không có active Step scope.

### Quên annotation @StepScope

Nếu bean cần `jobParameters` hoặc `stepExecutionContext` nhưng lại là singleton, biểu thức late binding có thể không được đánh giá đúng thời điểm hoặc không có context. Gắn scope cho đúng bean cần runtime binding.

### Dùng sai tên key trong SpEL

`#{jobParameters['inputFile']}` và `#{stepExecutionContext['inputFile']}` lấy dữ liệu từ hai nguồn khác nhau. Hãy kiểm tra key được tạo ở JobParameters hoặc Partitioner có đúng tên và đúng scope hay không.

### Trả về kiểu ItemReader quá chung khi reader cần ItemStream

Nếu kiểu trả về không thể hiện `ItemStream`, framework có thể không đăng ký lifecycle callback cho reader như mong muốn. Dùng `ItemStreamReader<T>` hoặc class cụ thể.

### Tắt saveState nhưng kỳ vọng restart

Scope không lưu checkpoint. Reader cần `saveState(true)` hoặc implementation `ItemStream` phù hợp.

### Dùng step scope để giải quyết mọi vấn đề thread safety

Bean có thể vẫn được chia sẻ trong cùng StepExecution giữa nhiều thread. Cần thiết kế concurrent access riêng.

### Dùng mutable singleton để giữ tham số của Step

Không gán JobParameters của execution hiện tại vào field của singleton service. Nhiều Job chạy đồng thời có thể ghi đè giá trị. Dùng late binding, method argument hoặc context theo đúng scope.

## 16. Kiểm thử bean step-scoped

Test một bean step-scoped cần có Step context đang hoạt động để proxy tạo target instance. Spring Batch Test cung cấp công cụ hỗ trợ tạo `StepExecution` và chạy code trong step scope.

Ví dụ dùng `StepScopeTestUtils`:

```java
@SpringBatchTest
@SpringBootTest
class OrderReaderStepScopeTest {

    @Autowired
    private ItemStreamReader<Order> orderReader;

    @Test
    void readerUsesInputFileFromStepContext() throws Exception {
        StepExecution stepExecution = MetaDataInstanceFactory.createStepExecution(
                new JobParametersBuilder()
                        .addString("inputFile", "data/test-orders.csv")
                        .toJobParameters()
        );

        Order firstOrder = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> orderReader.read()
        );

        assertNotNull(firstOrder);
    }
}
```

Đây là ví dụ minh họa; test thực tế cần chuẩn bị file fixture và lifecycle `open()`/`close()` cho reader nếu trực tiếp gọi `read()`. Có thể dùng `StepScopeTestExecutionListener` hoặc test support được đăng ký qua `@SpringBatchTest` để thiết lập scope trong test method.

Các trường hợp nên kiểm tra:

- Bean nhận đúng JobParameters của StepExecution hiện tại.
- Hai StepExecution khác nhau nhận giá trị runtime khác nhau.
- StepExecutionContext của mỗi partition được binding đúng.
- Truy cập target ngoài Step context không xảy ra trong code ứng dụng thông thường.
- Reader mở, cập nhật và đóng state đúng.
- Restart tạo target instance mới nhưng khôi phục checkpoint từ ExecutionContext.
- Multi-threaded Step không làm mutable state bị race.

## 17. Những nhầm lẫn thường gặp

**Cho rằng `@StepScope` tạo một bean mới cho mỗi item hoặc mỗi chunk.** Target instance gắn với StepExecution, không phải từng lần gọi `read()` hay `process()`.

**Cho rằng bean step-scoped được tạo ngay khi application khởi động.** Spring tạo proxy trước; target instance được tạo khi có Step context hoạt động và bean được truy cập.

**Cho rằng `@StepScope` tự lưu state qua restart.** Scope quản lý vòng đời bean; `ExecutionContext`/`ItemStream` mới lưu checkpoint bền vững.

**Cho rằng `@StepScope` tự làm bean thread-safe.** Nhiều thread trong cùng StepExecution có thể dùng chung target. Mutable state vẫn cần được quản lý.

**Cho rằng mọi component đều nên step-scoped.** Dùng scope khi cần late binding hoặc state riêng theo StepExecution; service stateless có thể vẫn là singleton.

**Dùng Job scope cho state riêng từng partition.** Partition có StepExecutionContext riêng, nên reader phụ thuộc partition thường cần StepScope.

## 18. Cách chọn và cấu hình StepScope

Hãy xác định bean nào cần dữ liệu chỉ có lúc Job/Step chạy. Nếu giá trị thuộc về một Step hoặc partition, dùng `@StepScope` và late binding từ JobParameters hoặc StepExecutionContext. Nếu dữ liệu thuộc phạm vi toàn JobExecution và được nhiều Step chia sẻ, cân nhắc `@JobScope`. Giữ các service stateless ở singleton để cấu hình đơn giản.

Với reader có state, bảo đảm kiểu trả về thể hiện `ItemStreamReader` hoặc implementation cụ thể, đặt tên reader ổn định và bật `saveState` khi cần restart. Đừng xem scope là checkpoint hoặc cơ chế thread safety. Khi chạy partitioning, mỗi StepExecution có target instance riêng; với multi-threaded Step, nhiều thread vẫn có thể cùng dùng một target trong StepExecution.

Thiết kế đúng `@StepScope` giúp một định nghĩa Step có thể chạy với nhiều tham số runtime và giữ state riêng theo từng lần thực thi, đồng thời tích hợp late binding với cơ chế checkpoint/restart của Spring Batch.
