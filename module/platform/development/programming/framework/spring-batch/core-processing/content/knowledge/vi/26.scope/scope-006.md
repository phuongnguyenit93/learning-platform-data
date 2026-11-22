# Proxy của scoped bean

Trong Spring Batch, `@StepScope` và `@JobScope` cho phép tạo bean có vòng đời gắn với một lần thực thi step hoặc job. Nhưng các bean này thường được khai báo trong application context từ lúc ứng dụng khởi động, trong khi `StepExecution` và `JobExecution` chỉ tồn tại khi job được launch.

Spring giải quyết khoảng cách thời gian đó bằng scoped proxy. Các thành phần cấu hình có thể nhận proxy ngay khi application context được tạo; proxy chỉ tìm hoặc tạo object đích (scoped target) khi một phương thức được gọi trong scope tương ứng đang hoạt động.

Vì vậy, cần phân biệt proxy với target: proxy là đối tượng đại diện được inject vào nơi sử dụng; target là bean thực tế được tạo theo `StepExecution` hoặc `JobExecution` hiện tại. Hiểu cơ chế này giúp dùng late binding cho `JobParameters` và `ExecutionContext`, tránh lỗi truy cập scope quá sớm và thiết kế đúng khi chạy song song.

## 1. Vì sao cần scoped proxy?

Application context Spring thường tạo các singleton bean khi ứng dụng khởi động. Một bean cấu hình step có thể cần tham chiếu tới reader, writer hoặc service mà dữ liệu cấu hình chỉ có khi job chạy.

Ví dụ, tên file đầu vào được truyền qua `JobParameters`. Khi Spring tạo bean `FlatFileItemReader` ở thời điểm startup, chưa có JobExecution nào để cung cấp parameter đó. Nếu reader là singleton thông thường, nó không có cách tự nhiên để nhận giá trị riêng cho từng lần chạy.

`@StepScope` giải quyết vấn đề bằng cách trì hoãn việc tạo target cho đến khi step bắt đầu và context của step đã sẵn sàng.

```text
Application startup
  Spring tạo application context
       |
       +--> tạo singleton Step bean
       |
       +--> inject scoped proxy cho reader

Job launch
  JobExecution / StepExecution được tạo
       |
       v
  Step bắt đầu, StepScope được kích hoạt
       |
       v
  Step gọi reader proxy
       |
       v
  Proxy tìm/tạo reader target cho StepExecution hiện tại
       |
       v
  Reader target dùng JobParameters / ExecutionContext
```

Proxy cho phép dependency được nối dây sớm, trong khi object đích được khởi tạo muộn theo ngữ cảnh thực thi.

## 2. Proxy và target là hai đối tượng khác nhau

Khi một bean được khai báo với `@StepScope`, Spring đăng ký một scoped proxy làm đối tượng được inject vào các bean khác. Khi proxy nhận lời gọi phương thức, nó tra cứu target trong scope đang hoạt động rồi chuyển lời gọi tới target đó.

| Đối tượng | Vai trò | Vòng đời |
|---|---|---|
| Scoped proxy | Đại diện được inject vào bean khác | Thường tồn tại trong application context |
| Scoped target | Reader, writer hoặc service thực tế | Gắn với scope hiện tại, chẳng hạn một StepExecution |

Proxy không phải một reader mới cho mỗi lần gọi `read()`. Trong cùng một `StepExecution`, proxy thường tiếp tục trỏ tới cùng target của step đó. Khi một execution khác chạy, scope cung cấp target tương ứng với execution mới.

Đây là lý do có thể inject một scoped bean vào singleton bean mà không làm target bị tạo sớm. Singleton giữ proxy; proxy tra cứu target theo scope lúc được sử dụng.

## 3. @StepScope tạo proxy theo StepExecution

`@StepScope` là annotation chuyên dụng của Spring Batch cho bean có scope `step`. Nó tương đương khai báo scope `step` với proxy mode theo lớp đích (`TARGET_CLASS`).

Ví dụ reader đọc file được chọn bởi JobParameters:

```java
@Bean
@StepScope
public FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Customer>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .delimited()
        .names("customerId", "name")
        .targetType(Customer.class)
        .build();
}
```

Spring có thể tạo proxy cho `customerReader` trong lúc cấu hình application context. Giá trị `inputFile` được resolve khi target được tạo trong StepScope, lúc JobParameters của execution đã có sẵn.

Với mỗi `StepExecution`, Spring Batch có một scope context riêng. Nếu cùng job chạy cho hai file khác nhau thành hai execution, mỗi execution có thể nhận một reader target với resource tương ứng.

## 4. Inject scoped proxy vào Step singleton

Step thường được khai báo như một bean cấu hình thông thường. Có thể inject reader scoped vào phương thức tạo step:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Customer> customerReader,
        ItemWriter<Customer> customerWriter) {

    return new StepBuilder("importCustomers", jobRepository)
        .<Customer, Customer>chunk(100, transactionManager)
        .reader(customerReader)
        .writer(customerWriter)
        .build();
}
```

Ở thời điểm Spring tạo `importCustomersStep`, dependency `customerReader` có thể là proxy. Step giữ tham chiếu tới proxy; khi step thực sự gọi reader trong một StepExecution, proxy mới lấy target phù hợp.

Không cần tự gọi factory để tạo reader trong mỗi lần chạy. Cũng không nên lưu một reader target được tạo thủ công vào static field hoặc singleton mutable vì những lần chạy khác nhau có thể dùng chung state.

## 5. Late binding với JobParameters

Late binding là việc resolve giá trị cấu hình vào thời điểm scoped target được tạo, thay vì lúc application context khởi động.

Ví dụ reader nhận file và encoding từ JobParameters:

```java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile,
        @Value("#{jobParameters['encoding']}") String encoding) {

    return new FlatFileItemReaderBuilder<Customer>()
        .name("customerReader")
        .resource(new FileSystemResource(inputFile))
        .encoding(encoding)
        .delimited()
        .names("customerId", "name")
        .targetType(Customer.class)
        .build();
}
```

Khi launch job, caller truyền parameters:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("input.file", "data/customers.csv", true)
    .addString("encoding", "UTF-8", false)
    .toJobParameters();

jobLauncher.run(importCustomersJob, parameters);
```

`input.file` được đánh dấu identifying trong ví dụ vì nó xác định nguồn dữ liệu của instance. `encoding` không identifying vì ví dụ giả định nó chỉ là tùy chọn kỹ thuật; nếu thay encoding làm thay đổi ý nghĩa dữ liệu được xử lý, cần cân nhắc đưa nó vào identity.

## 6. Late binding với ExecutionContext

Ngoài JobParameters, scoped bean có thể lấy dữ liệu từ `ExecutionContext`. Đây là cách truyền phạm vi hoặc checkpoint cho reader/writer của step.

Ví dụ reader trong partition nhận khoảng ID từ step execution context:

```java
@Bean
@StepScope
JdbcCursorItemReader<Order> partitionOrderReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Order>()
        .name("partitionOrderReader")
        .dataSource(dataSource)
        .sql("""
            SELECT ORDER_ID, CUSTOMER_ID, TOTAL
            FROM ORDERS
            WHERE ORDER_ID >= ? AND ORDER_ID <= ?
            ORDER BY ORDER_ID
            """)
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxId);
        })
        .rowMapper(new OrderRowMapper())
        .saveState(true)
        .build();
}
```

`minId` và `maxId` được lấy từ context của worker StepExecution. Vì mỗi partition có StepExecution và context riêng, mỗi scoped target có thể nhận phạm vi riêng mà không cần tạo một class reader khác nhau.

Các expression thường dùng:

| Expression | Giá trị được resolve từ |
|---|---|
| `#{jobParameters['input.file']}` | JobParameters của JobExecution hiện tại |
| `#{stepExecutionContext['minId']}` | Step ExecutionContext hiện tại |
| `#{jobExecutionContext['watermark']}` | Job ExecutionContext hiện tại |
| `#{stepExecution.stepName}` | Tên step execution hiện tại |

Chỉ tham chiếu key đã được tạo trước thời điểm target cần giá trị đó. Nếu key không tồn tại hoặc kiểu không phù hợp, việc resolve có thể thất bại khi bean target được tạo.

## 7. @JobScope tạo proxy theo JobExecution

`@JobScope` tạo bean có vòng đời gắn với một `JobExecution`. Bean này có thể dùng JobParameters hoặc Job ExecutionContext và được chia sẻ trong phạm vi execution đó.

Ví dụ service tạo tên báo cáo từ ngày nghiệp vụ:

```java
@Bean
@JobScope
ReportNamingPolicy reportNamingPolicy(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new ReportNamingPolicy("orders-" + businessDate + ".csv");
}
```

Các step trong cùng JobExecution có thể sử dụng proxy của `reportNamingPolicy`; target được tạo trong job scope và giữ trong vòng đời JobExecution.

Phân biệt:

- `@StepScope`: target riêng theo StepExecution, thích hợp cho reader/writer hoặc component phụ thuộc context của một step.
- `@JobScope`: target theo JobExecution, thích hợp cho dữ liệu hoặc policy dùng chung trong phạm vi job.

Không dùng JobScope để chứa mutable state được nhiều step song song cập nhật nếu không có cơ chế đồng bộ. Với state thuộc riêng một worker hoặc partition, StepScope thường phù hợp hơn.

## 8. Scope target được tạo khi nào và hủy khi nào?

Scoped target không được tạo chỉ vì application context được khởi động. Nó thường được tạo lần đầu khi proxy được gọi trong scope đang hoạt động. Sau đó target được giữ trong scope tương ứng cho đến khi scope kết thúc.

Với StepScope, vòng đời khái quát là:

1. Job được launch và Spring Batch tạo JobExecution/StepExecution.
2. Step bắt đầu và StepScope context được thiết lập cho StepExecution.
3. Lời gọi đầu tiên qua proxy làm target được tạo và các dependency/SpEL được resolve.
4. Step sử dụng target trong quá trình đọc, xử lý hoặc ghi.
5. Khi step kết thúc, các callback lifecycle phù hợp được gọi và scope được đóng.
6. Target được hủy theo callback destruction đã đăng ký nếu bean hỗ trợ lifecycle đó.

Với JobScope, target gắn với JobExecution và tồn tại trong phạm vi job execution. Vòng đời cụ thể của resource còn phụ thuộc interface/lifecycle mà bean triển khai và cách step đăng ký stream.

## 9. Scoped proxy và ItemStream lifecycle

Nhiều reader và writer của Spring Batch triển khai `ItemStream`, với các callback `open`, `update` và `close`. Step cần nhận diện được các callback này để mở tài nguyên, lưu checkpoint và giải phóng tài nguyên.

Khi khai báo scoped bean là `ItemStream` component, kiểu trả về của phương thức `@Bean` cần thể hiện interface phù hợp. Tốt nhất trả về kiểu cụ thể như `FlatFileItemReader<Customer>` hoặc một kiểu `ItemStreamReader<Customer>` thay vì chỉ khai báo `ItemReader<Customer>` nếu target cần được quản lý như `ItemStream`.

```java
@Bean
@StepScope
FlatFileItemReader<Customer> customerReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {
    // Khởi tạo reader có hỗ trợ ItemStream
    return buildCustomerReader(inputFile);
}
```

Khai báo kiểu trả về quá tổng quát có thể khiến Spring không nhận diện đầy đủ interface cần thiết tại thời điểm tạo proxy hoặc cấu hình step. Hãy bảo đảm proxy có thể được dùng như `ItemStream` nếu step cần gọi lifecycle của interface này.

Không tự gọi `open()` hoặc `close()` trên target từ bean cấu hình. Hãy để Spring Batch quản lý lifecycle reader/writer đã đăng ký trong step.

## 10. Không gọi scoped proxy trước khi scope hoạt động

Proxy chỉ có thể tìm target khi scope tương ứng đang hoạt động. Nếu một singleton gọi phương thức của StepScoped bean trong lúc application context khởi động, trước khi có StepExecution, Spring không có context để resolve target.

Ví dụ không phù hợp:

```java
@Component
public class StartupValidator {

    public StartupValidator(ItemReader<Customer> customerReader) {
        // Không gọi reader.read() tại thời điểm khởi tạo singleton
        // StepScope chưa chắc đã hoạt động
    }
}
```

Việc inject proxy không phải vấn đề; dereference proxy ngoài scope mới là vấn đề. Nếu gọi method khi không có StepExecution hoặc JobExecution context, thường sẽ nhận lỗi như `ScopeNotActiveException` hoặc exception được bọc bởi bean creation/invocation.

Các vị trí cần tránh gọi scoped bean quá sớm:

- Constructor của singleton bean.
- `@PostConstruct` của singleton bean.
- Logic chạy khi application context refresh.
- Job/step configuration method cố đọc giá trị từ target thay vì chỉ inject proxy.
- Background thread không có scope context của Spring Batch.

Chỉ gọi proxy trong execution flow tương ứng, khi Spring Batch đã thiết lập scope.

## 11. Scoped proxy không có nghĩa là tạo target mỗi lần gọi

Một hiểu nhầm khác là mỗi lần gọi phương thức qua proxy thì Spring tạo một object mới. Với StepScope và JobScope, scope giữ target theo execution hiện tại.

Ví dụ trong cùng một StepExecution:

```text
readerProxy.read()  ----+
                       +--> cùng reader target của StepExecution X
readerProxy.update() --+
                       +--> cùng reader target của StepExecution X
readerProxy.close()  --+
```

Khi một StepExecution khác bắt đầu, proxy resolve target theo context mới. Nhờ vậy state của reader như current line hoặc cursor có thể gắn với đúng execution.

Không nên nhầm scoped proxy với prototype scope. Prototype thường tạo instance mới theo từng lần yêu cầu bean từ container; StepScope/JobScope giữ instance trong phạm vi execution đã định nghĩa.

## 12. Proxy mode và giới hạn của class proxy

`@StepScope` và `@JobScope` mặc định dùng proxy theo lớp đích. Spring thường tạo class-based proxy để proxy có thể được inject dưới kiểu bean cụ thể.

Class-based proxy cần tạo lớp con từ target class. Vì vậy, target class không nên là `final`; các phương thức cần được proxy cũng không nên là `final` hoặc `private`. Nếu lớp không thể được proxy theo cơ chế đang dùng, application context có thể thất bại khi tạo proxy.

Ví dụ, tránh khai báo reader tùy chỉnh là `final` khi dùng `@StepScope` mặc định:

```java
// Tránh final class nếu scoped proxy dùng class-based proxy
public class CustomerReader implements ItemStreamReader<Customer> {
    // implementation
}
```

Với các bean tự viết, dùng class có thể mở rộng và phương thức public/protected phù hợp. Nếu cần thiết kế dựa trên interface hoặc thay đổi proxy mode, hãy xác nhận chính xác cấu hình scope và kiểu dependency trong ứng dụng; đừng đổi proxy mode tùy tiện vì step có thể cần interface `ItemStream`.

## 13. StepScope không tự làm bean thread-safe

Scope gắn với một StepExecution, không phải mặc định một object cho từng thread hoặc từng item. Trong một multi-threaded step, nhiều thread có thể làm việc trong cùng StepExecution và cùng truy cập một StepScoped target.

Điều này đặc biệt quan trọng với reader giữ cursor hoặc field mutable. Một reader stateful không tự trở nên thread-safe chỉ vì được đánh dấu `@StepScope`.

| Kiểu thực thi | Phạm vi target StepScoped | Lưu ý |
|---|---|---|
| Step tuần tự | Một target cho StepExecution | Thường phù hợp với reader stateful thông thường |
| Multi-threaded step | Target gắn với StepExecution chung | Có thể bị nhiều thread truy cập; cần kiểm tra thread safety |
| Partitioning | Mỗi worker StepExecution có context riêng | Mỗi partition có thể nhận target riêng |
| Nhiều JobExecution | Mỗi execution có scope tương ứng | Không dùng mutable static state để chia sẻ |

Với partitioning, StepScope rất hữu ích vì mỗi worker execution có thể resolve range riêng từ `stepExecutionContext`. Với multi-threaded step, hãy dùng reader/writer thread-safe hoặc chọn mô hình partitioning nếu cần state reader độc lập theo phần dữ liệu.

## 14. JobScope và xử lý song song

JobScoped target thuộc một JobExecution. Vì vậy, nhiều step trong cùng job có thể nhìn thấy cùng target job-scoped. Nếu nhiều nhánh hoặc worker truy cập cùng object mutable, có thể xảy ra race condition.

Không nên dùng JobScope như một cách chia sẻ biến an toàn giữa các thread. JobScope không thay thế concurrent collection, lock, database coordination hoặc message passing.

Trong multi-threaded và partitioned workloads, cần thận trọng khi dựa vào JobScope từ các thread được tạo bởi executor. Scope context của Spring Batch được quản lý theo execution thread; không giả định một thread tự tạo bằng `@Async` hoặc executor tùy chỉnh sẽ có đầy đủ context cần thiết. Ưu tiên truyền dữ liệu bất biến qua parameters/context phù hợp hoặc dùng cơ chế đồng bộ rõ ràng.

## 15. Scoped proxy và dependency injection

Một singleton bean có thể nhận scoped proxy qua constructor injection:

```java
@Component
public class CustomerStepCoordinator {

    private final ItemReader<Customer> reader;

    public CustomerStepCoordinator(ItemReader<Customer> reader) {
        this.reader = reader;
    }

    public void invokeDuringStep() throws Exception {
        Customer customer = reader.read();
        // Chỉ gọi khi StepScope đang hoạt động
    }
}
```

Constructor nhận proxy, không buộc target phải được tạo ngay. Tuy nhiên, `invokeDuringStep()` chỉ hợp lệ khi được gọi trong StepExecution có scope đang hoạt động.

Trong cấu hình Spring Batch, thường nên inject scoped proxy trực tiếp vào step builder thay vì tự điều phối reader qua một service. Spring Batch có thể quản lý `ItemStream` lifecycle tốt hơn khi reader/writer được khai báo đúng trên step.

## 16. Phân biệt scoped proxy với lazy injection

Scoped proxy và lazy injection đều có thể trì hoãn việc tạo hoặc lấy bean, nhưng chúng giải quyết vấn đề khác nhau.

| Cơ chế | Ý nghĩa |
|---|---|
| Scoped proxy | Mỗi lời gọi được định tuyến tới target thuộc scope hiện tại |
| `@Lazy` | Trì hoãn khởi tạo/resolve bean cho đến khi cần |
| Prototype scope | Container tạo instance mới theo từng lần yêu cầu bean |
| Singleton scope | Một instance dùng chung trong application context |

`@Lazy` không tự biến bean thành StepScoped. Nếu dùng lazy singleton, bean vẫn không có target riêng cho từng StepExecution. Khi cần late binding theo JobParameters hoặc ExecutionContext, dùng `@StepScope`/`@JobScope` và scoped proxy tương ứng.

## 17. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Gọi method của StepScoped bean lúc startup | Không có StepExecution để resolve target | Chỉ dereference proxy trong step đang chạy |
| Nghĩ proxy chính là target | Nhầm vòng đời và state của bean | Phân biệt proxy đại diện với target theo execution |
| Dùng singleton reader có state cho nhiều job | Các lần chạy có thể dùng chung cursor/checkpoint | Dùng `@StepScope` cho reader phụ thuộc execution |
| Cho rằng mỗi lần gọi proxy tạo object mới | Hiểu sai scope và lifecycle | Target được giữ trong scope hiện tại |
| Khai báo `@Bean` trả về kiểu quá tổng quát cho ItemStream | Step có thể không nhận diện interface lifecycle cần thiết | Khai báo kiểu trả về cụ thể hoặc `ItemStreamReader` |
| Dùng final class với class-based scoped proxy | Không thể tạo proxy theo lớp | Dùng class có thể proxy hoặc cấu hình proxy phù hợp |
| Cho rằng StepScope bảo đảm thread safety | Nhiều thread trong cùng StepExecution có thể chia sẻ target | Dùng component thread-safe hoặc partitioning |
| Dùng JobScope mutable để đồng bộ worker | Race condition giữa các nhánh/worker | Dùng state riêng, immutable value hoặc cơ chế đồng bộ |
| Gọi scoped proxy từ thread ngoài execution | Scope context có thể không tồn tại | Truyền dữ liệu rõ ràng hoặc tạo execution context phù hợp |

## 18. Kiểm thử scoped proxy

Có thể kiểm thử scoped bean bằng integration test khởi chạy step/job thật, thay vì chỉ tạo object thủ công. Mục tiêu là xác nhận target được tạo trong đúng scope và nhận đúng dữ liệu execution.

Các trường hợp nên kiểm tra:

1. Application context khởi động thành công dù chưa có JobExecution hoặc StepExecution.
2. Reader target được tạo khi step bắt đầu và nhận đúng JobParameters.
3. Hai JobExecution với file khác nhau nhận target reader phù hợp với từng file.
4. Hai partition nhận `minId`/`maxId` riêng trong StepExecution context.
5. Gọi proxy ngoài scope tạo lỗi phù hợp, thay vì âm thầm dùng target sai.
6. `ItemStream.open`, `update` và `close` được Spring Batch gọi đúng lifecycle.
7. Restart khôi phục checkpoint mà không dùng lại target runtime cũ.
8. Multi-threaded step không truy cập stateful target theo cách gây race condition.

Đừng chỉ kiểm tra object proxy có được inject hay không. Cần kiểm tra target được resolve trong đúng execution context, bởi đó mới là mục đích của scoped proxy.

## 19. Quy trình chọn và dùng scoped bean

Khi khai báo reader, writer hoặc service phụ thuộc execution, hãy xác định:

1. Bean cần state riêng theo StepExecution hay dùng chung trong JobExecution?
2. Có cần late binding từ JobParameters hoặc ExecutionContext không?
3. Bean có được inject vào singleton step/job configuration không? Nếu có, dùng scoped proxy.
4. Phương thức `@Bean` có khai báo kiểu trả về đủ cụ thể để Spring Batch nhận diện `ItemStream` khi cần không?
5. Có nơi nào gọi proxy trước khi scope được kích hoạt không?
6. Bean có state mutable và có thể bị nhiều thread truy cập trong cùng StepExecution không?
7. Target có cần mở/đóng resource hoặc lưu checkpoint không?
8. Integration test có xác nhận target, context và lifecycle trong cả lần chạy mới lẫn restart không?

## Kết luận

Scoped proxy cho phép inject bean `@StepScope` hoặc `@JobScope` vào các singleton bean trước khi job/step thực sự chạy. Proxy được tạo sớm; target chỉ được resolve trong scope đang hoạt động và được giữ theo vòng đời StepExecution hoặc JobExecution. Nhờ vậy, bean có thể nhận JobParameters và ExecutionContext bằng late binding.

Proxy không phải target, không tạo object mới cho mỗi lần gọi và không tự làm bean thread-safe. Hãy dùng `@StepScope` cho state thuộc worker/step, `@JobScope` cho dữ liệu thuộc job, khai báo kiểu trả về phù hợp với `ItemStream`, tránh dereference proxy ngoài scope và kiểm thử concurrency khi chạy song song.
