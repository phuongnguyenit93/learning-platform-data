# Không dùng scoped bean cho state toàn cục trong Spring Batch

Spring Batch cung cấp các scope như `@StepScope` và `@JobScope` để tạo bean đúng thời điểm và gắn vòng đời bean với một lần thực thi step hoặc job. Những scope này rất hữu ích khi bean cần đọc `JobParameters`, `ExecutionContext` hoặc giữ trạng thái chỉ thuộc về một execution cụ thể.

Tuy nhiên, scoped bean không phải nơi lưu state toàn cục của ứng dụng. Một bean step-scoped chỉ sống trong phạm vi `StepExecution`; một bean job-scoped chỉ sống trong phạm vi `JobExecution`. Nếu đặt bộ đếm dùng chung cho toàn ứng dụng, cache dùng chung giữa các job hoặc trạng thái cần tồn tại qua nhiều lần chạy vào những bean này, dữ liệu có thể bị tách theo execution, biến mất khi execution kết thúc hoặc bị truy cập đồng thời ngoài dự kiến.

Để chọn scope đúng, cần xác định state thuộc về ai và tồn tại trong bao lâu: một lần xử lý item, một step execution, một job execution, toàn bộ ApplicationContext hay nhiều process/nhiều node.

## 1. Bean scope quyết định vòng đời của object

Trong Spring, scope xác định khi nào container tạo bean, khi nào các nơi inject nhận cùng một instance và khi nào instance đó được hủy. Spring singleton là scope mặc định: một instance cho mỗi bean definition trong một Spring ApplicationContext. `@StepScope` và `@JobScope` bổ sung các vòng đời gắn với execution của Spring Batch.

| Scope | Phạm vi instance | Thời điểm thường được tạo | Phù hợp với |
| --- | --- | --- | --- |
| Singleton | Một instance cho bean definition trong một ApplicationContext | Khi context khởi tạo hoặc khi bean được yêu cầu lần đầu | Service stateless, cấu hình, repository, thành phần dùng chung an toàn với concurrency |
| Job scope | Một instance cho mỗi `JobExecution` | Khi job-scoped bean được truy cập trong job execution | Giá trị hoặc helper chỉ thuộc về một lần chạy job |
| Step scope | Một instance cho mỗi `StepExecution` | Khi step-scoped bean được truy cập trong step execution | Reader, writer, processor hoặc helper cần tham số/context riêng của step |
| Prototype | Một instance mới mỗi lần container yêu cầu bean | Mỗi lần gọi lấy bean | Object ngắn hạn được tạo tường minh; container không quản lý đầy đủ lifecycle sau khi inject |

Điểm cần nhớ là scope mô tả vòng đời object, không tự quyết định dữ liệu có được lưu bền vững hay không. Field trong `@StepScope` vẫn là field trong bộ nhớ. Khi step kết thúc hoặc process dừng, field đó không tự được ghi vào `JobRepository`.

## 2. @StepScope thuộc về một StepExecution

`@StepScope` là scope dành cho bean cần được khởi tạo trong ngữ cảnh của một `StepExecution`. Mỗi lần thực thi step có thể nhận một target bean riêng. Đây là lý do step-scoped reader thường được dùng để lấy tham số từ `JobParameters` hoặc step `ExecutionContext`.

Ví dụ:

```java
@Bean
@StepScope
JdbcPagingItemReader<Order> orderReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") LocalDate businessDate,
        @Value("#{stepExecutionContext['tenantId']}") String tenantId) {

    return new JdbcPagingItemReaderBuilder<Order>()
        .name("orderReader")
        .dataSource(dataSource)
        .selectClause("select id, tenant_id, total")
        .fromClause("from orders")
        .whereClause("where tenant_id = :tenantId and business_date = :businessDate")
        .parameterValues(Map.of(
            "tenantId", tenantId,
            "businessDate", businessDate
        ))
        .rowMapper(new OrderRowMapper())
        .pageSize(200)
        .saveState(true)
        .build();
}
```

`businessDate` được lấy từ job parameters; `tenantId` được lấy từ step execution context. Những giá trị này chỉ có nghĩa khi Spring Batch đã thiết lập execution context tương ứng.

Nếu một job được chạy hai lần với hai `JobExecution` khác nhau, mỗi lần chạy có các `StepExecution` riêng. Bean step-scoped được tạo cho step execution tương ứng, nên state nằm trong field của bean không phải state toàn cục dùng chung cho cả hai job.

## 3. @JobScope thuộc về một JobExecution

`@JobScope` tạo bean trong phạm vi một `JobExecution`. Bean đó có thể được dùng ở nhiều step thuộc cùng lần chạy job, nhưng execution khác sẽ có instance khác.

Ví dụ:

```java
@Bean
@JobScope
BatchRunDescriptor batchRunDescriptor(
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['region']}") String region) {

    return new BatchRunDescriptor(businessDate, region);
}
```

Một step có thể inject `BatchRunDescriptor` để dùng thông tin chung của lần chạy job:

```java
@Bean
Step validateStep(JobRepository jobRepository,
                  PlatformTransactionManager transactionManager,
                  BatchRunDescriptor batchRunDescriptor) {
    return new StepBuilder("validateStep", jobRepository)
        .tasklet((contribution, chunkContext) -> {
            log.info(
                "Validating date={} region={}",
                batchRunDescriptor.businessDate(),
                batchRunDescriptor.region()
            );
            return RepeatStatus.FINISHED;
        }, transactionManager)
        .build();
}
```

Bean job-scoped có thể chia sẻ thông tin giữa các step của cùng một `JobExecution`. Nhưng nó không phải singleton toàn ứng dụng, cũng không phải kho dữ liệu bền vững giữa các lần chạy job.

Nếu job chạy hai lần đồng thời, mỗi `JobExecution` có một target `BatchRunDescriptor` riêng. Không dùng một field trong bean job-scoped để tổng hợp số liệu của tất cả job execution.

## 4. Vì sao scoped bean không phải state toàn cục?

Giả sử ứng dụng cần một bộ đếm số order đã import trong toàn bộ tiến trình. Nếu đặt bộ đếm trong step-scoped bean, mỗi step execution có thể nhận một bộ đếm riêng:

```text
ApplicationContext
    |
    +-- JobExecution A
    |      |
    |      +-- StepExecution A1 -> StepScopedCounter = 0
    |      +-- StepExecution A2 -> StepScopedCounter = 0
    |
    +-- JobExecution B
           |
           +-- StepExecution B1 -> StepScopedCounter = 0
```

Các instance không tự chia sẻ cùng một giá trị. Nếu đặt bộ đếm trong job-scoped bean, các step trong cùng job execution có thể thấy chung target, nhưng job execution khác vẫn có instance riêng:

```text
ApplicationContext
    |
    +-- JobExecution A -> JobScopedCounter = 0
    |
    +-- JobExecution B -> JobScopedCounter = 0
```

Do đó, chọn `@StepScope` hay `@JobScope` chỉ vì muốn field tồn tại trong lúc xử lý sẽ dẫn đến sai phạm vi nếu state thực tế thuộc về toàn ứng dụng hoặc nhiều job.

Một scoped bean cũng không phải nơi lưu state lâu dài. Khi scope kết thúc, target bean được hủy theo lifecycle; dữ liệu trong field không tự được serialize vào metadata repository.

## 5. Phân biệt state theo từng phạm vi

Trước khi chọn scope, hãy phân loại state theo chủ sở hữu:

| State cần lưu | Phạm vi đúng thường gặp | Cách triển khai |
| --- | --- | --- |
| Vị trí reader đã commit | Step execution | `ItemStream.update(ExecutionContext)` |
| Giá trị riêng của một partition | Step execution của partition | Step context và `@StepScope` |
| Tham số chung của một lần chạy job | Job execution | `JobParameters`, `JobExecutionContext`, `@JobScope` |
| Bộ đếm tạm của một lần gọi method | Method invocation | Biến local |
| Cấu hình dùng chung, service stateless | ApplicationContext | Singleton bean |
| Cache dùng chung trong một process | ApplicationContext/process | Singleton cache có concurrency control và eviction |
| Trạng thái cần chia sẻ giữa nhiều node | Hệ thống phân tán | Database, distributed cache hoặc coordination service |
| Lịch sử cần tồn tại qua restart | Kho dữ liệu bền vững | Bảng nghiệp vụ/audit hoặc metadata phù hợp |

Không có một scope duy nhất phù hợp cho mọi loại state. Hãy chọn theo thời gian tồn tại, phạm vi chia sẻ, khả năng phục hồi và mức độ đồng thời.

## 6. Dùng singleton cho service dùng chung, không giữ state theo execution

Singleton là lựa chọn phù hợp cho service không giữ state riêng của một job/step, ví dụ service validation, repository hoặc client có cấu hình cố định:

```java
@Service
public class OrderValidationService {

    public ValidationResult validate(Order order) {
        // Tính toán từ input, không lưu item hiện tại vào field.
        if (order.getCustomerId() == null) {
            return ValidationResult.invalid("Missing customer id");
        }
        return ValidationResult.valid();
    }
}
```

Service singleton có thể được nhiều job/step sử dụng. Vì thế, không lưu dữ liệu tạm của item hiện tại trong field mutable:

```java
// Không nên: field này bị các execution ghi đè lẫn nhau.
private Order currentOrder;
```

Thay vào đó, truyền dữ liệu qua tham số và biến local:

```java
public ValidationResult validate(Order order) {
    String customerId = order.getCustomerId();
    return validateCustomer(customerId);
}
```

Singleton không đồng nghĩa với thread-safe. Nếu bean có cache hoặc bộ đếm dùng chung, cần chọn cấu trúc dữ liệu đồng thời, atomic operation hoặc cơ chế đồng bộ phù hợp. Nếu state phải tồn tại sau khi JVM restart hoặc được chia sẻ giữa nhiều instance ứng dụng, singleton trong một process không đáp ứng được yêu cầu đó.

## 7. Không dùng @StepScope để giữ state toàn ứng dụng

Một lỗi thiết kế thường gặp là đặt cache hoặc counter toàn cục vào step-scoped bean:

```java
@Component
@StepScope
public class GlobalImportStatistics {

    private long totalImported;

    public void increment() {
        totalImported++;
    }

    public long getTotalImported() {
        return totalImported;
    }
}
```

Tên bean nói rằng đây là statistics toàn cục, nhưng scope lại tạo instance theo `StepExecution`. Khi một step khác hoặc job execution khác sử dụng bean, nó có thể nhận instance riêng và counter không phản ánh tổng toàn ứng dụng.

Nếu thống kê chỉ thuộc một step, hãy đặt tên và scope đúng với mục đích:

```java
@Component
@StepScope
public class StepImportStatistics {

    private long importedInThisStep;

    public void increment() {
        importedInThisStep++;
    }
}
```

Nếu cần tổng hợp trên nhiều step trong cùng một job, cân nhắc job execution context, listener tổng hợp từ `StepExecution` hoặc một service job-scoped có kiểm soát concurrency. Nếu cần tổng hợp qua nhiều job, dùng một nơi lưu chung có định danh và transaction phù hợp.

## 8. Không dùng @JobScope cho state toàn ứng dụng

Job scope rộng hơn step scope nhưng vẫn chỉ thuộc một `JobExecution`. Ví dụ, một bộ đếm trong job-scoped bean có thể tổng hợp dữ liệu trong cùng lần chạy job nếu các step truy cập cùng target:

```java
@Component
@JobScope
public class JobRunStatistics {

    private final AtomicLong processed = new AtomicLong();

    public void addProcessed(long count) {
        processed.addAndGet(count);
    }

    public long getProcessed() {
        return processed.get();
    }
}
```

Bean này không tổng hợp tự động mọi job. Job execution tiếp theo có một target khác; process khác cũng không chia sẻ field này. Nếu yêu cầu là thống kê toàn ứng dụng, job scope sai phạm vi.

Ngay cả khi state chỉ thuộc một job, hãy xem xét cách nhiều step hoặc thread có thể cập nhật cùng lúc. `AtomicLong` giúp phép cộng nguyên tử trong một process, nhưng không biến bean thành store phân tán và không bảo đảm dữ liệu sống sót qua restart.

## 9. Scoped proxy cho phép inject bean vào singleton

Một bean singleton có thể inject dependency step-scoped hoặc job-scoped thông qua scoped proxy. Proxy được tạo sớm, còn target thật được resolve khi scope tương ứng đang hoạt động.

Ví dụ:

```java
@Bean
@StepScope
OrderReader orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new OrderReader(inputFile);
}

@Bean
Step importStep(JobRepository jobRepository,
                PlatformTransactionManager transactionManager,
                OrderReader orderReader) {
    return new StepBuilder("importStep", jobRepository)
        .<Order, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .build();
}
```

`Step` bean thường là singleton được xây dựng khi ApplicationContext khởi tạo. Nếu Spring inject trực tiếp target step-scoped trước khi có `StepExecution`, bean sẽ không thể resolve `jobParameters`. Scoped proxy giải quyết vấn đề này bằng cách trì hoãn việc truy cập target đến khi step scope hoạt động.

`@StepScope` annotation của Spring Batch cấu hình scoped proxy theo cơ chế phù hợp. Khi tự khai báo `@Scope`, cần hiểu proxy mode và cách inject để không giữ target của execution cũ trong một singleton.

Không nên lấy target scoped bean rồi lưu tham chiếu lâu dài vào static field hoặc singleton cache. Làm vậy có thể giữ nhầm instance sau khi scope kết thúc hoặc dùng target ngoài execution hợp lệ.

## 10. @StepScope không có nghĩa một instance cho mỗi thread

Đây là điểm quan trọng khi chạy multi-threaded step. Step scope gắn với `StepExecution`, không phải tự động tạo một target riêng cho mỗi thread xử lý item.

Trong một step chạy nhiều thread, nhiều thread có thể cùng truy cập một step-scoped target. Nếu bean có field mutable, các thread có thể ghi đè hoặc đọc state của nhau.

Ví dụ nguy hiểm:

```java
@Component
@StepScope
public class CurrentItemHolder {

    private Order current;

    public void setCurrent(Order order) {
        current = order;
    }

    public Order getCurrent() {
        return current;
    }
}
```

Nếu nhiều thread gọi `setCurrent()` và `getCurrent()`, một thread có thể đọc order do thread khác ghi. Step scope không cung cấp thread isolation cho từng item.

Ưu tiên processor/reader/writer stateless theo từng invocation. Dùng biến local hoặc truyền item trực tiếp qua method. Nếu thực sự cần state chia sẻ trong step đa luồng, thiết kế đồng bộ và xác định rõ tính đúng đắn khi nhiều item xử lý song song.

## 11. Partitioning tạo StepExecution riêng cho từng partition

Trong partitioning, mỗi worker partition có một `StepExecution` riêng. Vì vậy, step-scoped bean của worker có thể nhận `ExecutionContext` riêng của partition:

```text
Manager Step
    |
    +-- Partition 0 / StepExecution 0
    |       @StepScope target 0
    |       step context: minId=1, maxId=1000
    |
    +-- Partition 1 / StepExecution 1
    |       @StepScope target 1
    |       step context: minId=1001, maxId=2000
    |
    +-- Partition 2 / StepExecution 2
            @StepScope target 2
            step context: minId=2001, maxId=3000
```

Đây là use case phù hợp cho `@StepScope`: mỗi worker có reader hoặc helper riêng với phạm vi dữ liệu riêng. Không cần đặt một biến global `currentPartition` trong singleton rồi thay đổi trước khi worker chạy; các worker có thể chạy đồng thời và ghi đè biến đó.

Ví dụ reader:

```java
@Bean
@StepScope
JdbcCursorItemReader<Customer> customerReader(
        DataSource dataSource,
        @Value("#{stepExecutionContext['minId']}") Long minId,
        @Value("#{stepExecutionContext['maxId']}") Long maxId) {

    return new JdbcCursorItemReaderBuilder<Customer>()
        .name("customerReader")
        .dataSource(dataSource)
        .sql("select id, name from customer where id between ? and ? order by id")
        .preparedStatementSetter(ps -> {
            ps.setLong(1, minId);
            ps.setLong(2, maxId);
        })
        .rowMapper(new BeanPropertyRowMapper<>(Customer.class))
        .saveState(true)
        .build();
}
```

Không dùng `@JobScope` để thay thế state riêng cho từng partition. Job-scoped target thuộc job execution; nhiều worker trong cùng job có thể cùng nhìn thấy một target. Với partition-specific state, dùng step execution context và step scope.

## 12. Cẩn trọng với @JobScope trong multi-threading và partitioning

Job-scoped bean được gắn với `JobExecution`, nên nhiều step thuộc cùng job có thể cùng truy cập target. Trong các mô hình chạy đồng thời, cần hiểu rõ thread nào có batch context và cách scope được truyền tới worker.

Spring Batch lưu ý job scope không phù hợp với một số trường hợp multi-threaded/partitioned step, vì framework không luôn kiểm soát hoặc truyền job context đến mọi thread do executor hay remote worker tạo ra. Không nên dựa vào việc job-scoped target sẽ hoạt động như thread-local state trong mọi mô hình concurrency.

Với worker partition, ưu tiên:

- Truyền dữ liệu riêng qua partition `ExecutionContext`.
- Dùng `@StepScope` cho reader/processor/writer cần dữ liệu partition.
- Dùng singleton stateless service cho logic dùng chung.
- Dùng database/cache ngoài nếu cần chia sẻ dữ liệu thật sự giữa worker.

Nếu cần một giá trị chung của job, có thể lưu nó trong `JobExecutionContext` và đọc theo cơ chế được Spring Batch hỗ trợ. Đừng dùng field mutable trong job-scoped bean làm kênh phối hợp giữa các worker.

## 13. Dùng ExecutionContext cho state cần restart

Nếu state cần được khôi phục sau rollback hoặc process restart, field của scoped bean không đủ. Spring Batch cung cấp `ExecutionContext` gắn với `StepExecution` và `JobExecution`, được quản lý bởi `JobRepository`.

Ví dụ reader lưu checkpoint:

```java
public class OrderReader implements ItemStreamReader<Order> {

    private static final String LAST_ID = "orderReader.lastId";
    private long lastId;

    @Override
    public void open(ExecutionContext context) {
        lastId = context.containsKey(LAST_ID)
            ? context.getLong(LAST_ID)
            : 0L;
    }

    @Override
    public Order read() {
        // Đọc item tiếp theo có ID lớn hơn lastId.
        // Cập nhật lastId theo item được đọc.
        return findNextOrder();
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
```

Trong ví dụ, field `lastId` là state runtime của reader; `ExecutionContext` là bản checkpoint được lưu tại lifecycle update. Khi step restart, `open()` khôi phục field từ context đã lưu.

Không nên nhầm việc reader là step-scoped với việc checkpoint tự động tồn tại. Reader cần triển khai `ItemStream` hoặc được bọc bởi thành phần hỗ trợ `ItemStream`, đồng thời lưu state đúng cách. Bean scope quản lý object; `ExecutionContext` quản lý trạng thái phục hồi.

## 14. Dùng JobParameters cho input bất biến của một lần chạy

Nếu một giá trị là input của job, ví dụ business date, input file hoặc tenant, nên truyền bằng `JobParameters` thay vì đặt nó trong một field global:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("inputFile", "orders-2026-11-15.csv", false)
    .toJobParameters();
```

Các parameter identifying tham gia xác định `JobInstance`; non-identifying parameter cung cấp thông tin bổ sung nhưng không thay đổi danh tính instance. Chọn identifying theo đơn vị công việc logic của job.

Bean step-scoped có thể inject job parameter:

```java
@Bean
@StepScope
OrderFileReader orderFileReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new OrderFileReader(Path.of(inputFile));
}
```

`JobParameters` nên được xem là input của lần chạy, không phải vùng ghi state mutable. Nếu cần cập nhật tiến độ, dùng execution context hoặc kho dữ liệu phù hợp.

## 15. State toàn cục trong một ApplicationContext

Nếu ứng dụng thực sự cần một cache hoặc service dùng chung trong một JVM, singleton bean có thể phù hợp. Ví dụ cache metadata ít thay đổi:

```java
@Component
public class ProductMetadataCache {

    private final ConcurrentMap<String, ProductMetadata> cache =
        new ConcurrentHashMap<>();

    public ProductMetadata get(String productId) {
        return cache.computeIfAbsent(productId, this::loadMetadata);
    }

    private ProductMetadata loadMetadata(String productId) {
        // Đọc metadata từ nguồn chính thức.
        return metadataRepository.findById(productId)
            .orElseThrow();
    }
}
```

Singleton cache này chia sẻ giữa các job/step trong cùng ApplicationContext. Nhưng cần cân nhắc:

- Cache có thể mất khi ứng dụng restart.
- Mỗi replica ứng dụng có cache riêng.
- Nhiều job/thread có thể truy cập đồng thời.
- Cần eviction hoặc invalidation khi dữ liệu nguồn thay đổi.
- Không lưu state nghiệp vụ quan trọng chỉ trong heap.

Nếu cần tổng hợp toàn bộ job execution trên nhiều node, cache singleton không đủ. Dùng database hoặc distributed cache với khóa và cập nhật nguyên tử phù hợp.

## 16. State toàn cục trong môi trường nhiều node

Trong môi trường triển khai nhiều instance ứng dụng, mỗi JVM có ApplicationContext và singleton bean riêng. `@JobScope` và `@StepScope` cũng chỉ tồn tại trong process thực thi bean đó.

```text
Cluster
  |
  +-- Node A / ApplicationContext A
  |       Singleton cache A
  |       JobScope A
  |       StepScope A
  |
  +-- Node B / ApplicationContext B
          Singleton cache B
          JobScope B
          StepScope B
```

Không có field trong scoped bean nào tự đồng bộ giữa Node A và Node B. Nếu nhiều worker cần chia sẻ trạng thái, dùng một hệ thống chung:

- Database với transaction và unique constraint.
- Distributed cache với atomic operation/TTL.
- Message broker để trao đổi event.
- Coordination service hoặc distributed lock khi thực sự cần điều phối.

Định danh record nên chứa phạm vi như job instance, tenant, partition hoặc business key để tránh các execution khác nhau ghi đè state của nhau.

## 17. Không dùng static field để thay thế scope

Một cách sửa sai phổ biến là chuyển field trong scoped bean thành `static` để mọi execution dùng chung:

```java
public class ImportState {
    public static long processedCount;
}
```

Cách này tạo state dùng chung trong một classloader/process, nhưng có nhiều vấn đề:

- Không có transaction hoặc checkpoint tự động.
- Không phân biệt job execution, tenant hoặc partition.
- Các thread có thể cập nhật đồng thời và làm mất increment.
- Giá trị tồn tại giữa các job trong cùng JVM dù logic muốn reset.
- Không chia sẻ giữa nhiều node và mất khi process restart.
- Test có thể ảnh hưởng lẫn nhau do state static còn sót.

Nếu cần bộ đếm trong một execution, dùng `StepExecution`/`JobExecution` counters hoặc context. Nếu cần counter toàn ứng dụng, dùng một singleton service thread-safe hoặc kho dữ liệu bền vững tùy yêu cầu. Static field không phải cơ chế quản lý state batch.

## 18. Chọn scope cho reader, processor, writer và listener

Không phải mọi thành phần trong step đều cần scoped bean. Hãy chọn theo dữ liệu mà thành phần cần:

| Thành phần | Scope thường dùng | Lý do |
| --- | --- | --- |
| Reader cần job parameter hoặc partition context | `@StepScope` | Mỗi step execution có input/context riêng. |
| Writer tạo file riêng cho step | `@StepScope` | Mỗi step execution có resource và lifecycle riêng. |
| Processor stateless, chỉ biến đổi item | Singleton thường đủ | Không cần target riêng theo execution. |
| Processor phụ thuộc tham số của step/job | `@StepScope` hoặc `@JobScope` tùy phạm vi | Late binding giá trị theo execution. |
| Repository/service dùng chung | Singleton | Service stateless hoặc quản lý concurrency rõ ràng. |
| Listener cần tham số riêng của step | `@StepScope` nếu cần late binding | Target gắn với execution phù hợp. |
| Cache toàn process | Singleton cache có quản lý | Chia sẻ trong một ApplicationContext. |

Không thêm `@StepScope` cho mọi bean chỉ vì chúng được gọi từ một step. Scope bổ sung proxy và lifecycle; dùng nó khi thật sự cần late binding hoặc state/resource riêng cho execution.

## 19. Kiểm thử vòng đời và phạm vi bean

Nên kiểm thử rằng hai execution khác nhau nhận state riêng, còn các nơi trong cùng scope nhận đúng target. Với step-scoped bean, chạy hai `StepExecution` hoặc hai job execution và xác nhận field runtime không bị chia sẻ ngoài ý muốn.

Các tình huống cần kiểm tra:

1. Hai `JobExecution` có tham số khác nhau nhận target job/step scope phù hợp.
2. Hai `StepExecution` có partition context khác nhau nhận reader target với phạm vi riêng.
3. Singleton service không giữ item hoặc context của execution trước.
4. Step-scoped bean không được truy cập trước khi step scope hoạt động.
5. Reader checkpoint được lưu trong `ExecutionContext` và khôi phục sau restart.
6. Bean có mutable state không bị dùng đồng thời ngoài dự kiến trong multi-threaded step.
7. Multi-node state được đọc/ghi qua kho chung thay vì field trong heap.

Có thể dùng `StepScopeTestUtils` hoặc test support của Spring Batch để thiết lập `StepExecution` khi unit test bean step-scoped. Với integration test, khởi chạy job thật qua test launcher để xác nhận proxy và lifecycle hoạt động trong context thực.

Không chỉ kiểm tra bean có được tạo hay không. Hãy kiểm tra chính phạm vi chia sẻ và việc state có tồn tại sau đúng mốc cần thiết hay không.

## 20. Những lỗi thường gặp khi dùng scoped bean cho state

**Dùng step-scoped bean làm cache toàn cục:** mỗi `StepExecution` có target riêng; cache không tự chia sẻ giữa các step/job. Dùng singleton hoặc distributed cache theo phạm vi cần thiết.

**Dùng job-scoped bean cho tất cả job:** mỗi `JobExecution` có target riêng. State không được chia sẻ giữa các lần chạy.

**Nhầm bean scope với persistence:** field trong scoped bean nằm trong bộ nhớ. Dùng `ExecutionContext` hoặc database khi cần restart/durability.

**Cho rằng singleton luôn thread-safe:** singleton có thể được nhiều worker gọi đồng thời. Tránh mutable field không đồng bộ hoặc dùng concurrent primitive phù hợp.

**Cho rằng step scope tạo instance theo thread:** step scope gắn với `StepExecution`; multi-threaded step có thể chia sẻ target. Không lưu current item trong field của step-scoped bean.

**Dùng job scope làm state riêng từng partition:** partition có `StepExecution` riêng. Dùng step context và `@StepScope` cho partition-specific state.

**Dùng static field để chia sẻ state:** static không có checkpoint, transaction hoặc đồng bộ giữa node. Chọn store đúng theo phạm vi và độ bền cần thiết.

**Giữ target scoped bean trong singleton/static field:** tham chiếu có thể sống lâu hơn scope và trỏ đến target không còn hợp lệ. Để Spring quản lý scoped proxy.

**Dùng scoped bean thay cho JobParameters:** input bất biến của job nên là job parameter, không phải mutable field.

**Dùng singleton cache cho dữ liệu cần nhất quán cluster:** mỗi node có cache riêng. Dùng kho chung và invalidation/coordination rõ ràng.

## 21. Quy trình chọn nơi lưu state

Trước khi tạo bean, hãy trả lời bốn câu hỏi:

1. State thuộc về item, step execution, job execution, application process hay toàn cluster?
2. State cần tồn tại trong bao lâu: một method, một step, một job, qua restart hay vĩnh viễn?
3. Có bao nhiêu thread, partition hoặc node có thể đọc/ghi cùng lúc?
4. State có cần transaction, checkpoint, audit hoặc khả năng phục hồi không?

Sau đó chọn cơ chế:

- Dữ liệu tạm trong một lần gọi: biến local.
- Tham số input của job: `JobParameters`.
- State riêng của step: `@StepScope` và `StepExecutionContext`.
- State chung trong một job execution: `@JobScope` hoặc `JobExecutionContext`, có xem xét concurrency.
- Service/config/cache trong một process: singleton thread-safe.
- State cần restart: `ExecutionContext` hoặc database.
- State cần chia sẻ giữa nhiều node: database/distributed store/message broker.

Đừng dùng một scoped bean làm giải pháp cho mọi loại state. Bean scope chỉ giải quyết vòng đời object; transaction, persistence, thread safety và distributed coordination vẫn cần được thiết kế riêng.

## 22. Thiết kế ví dụ: tách state theo đúng phạm vi

Giả sử một job nhập đơn hàng theo tenant và business date. Một thiết kế có thể gồm:

- `JobParameters`: `businessDate`, `inputFile` và định danh batch.
- `@JobScope`: descriptor bất biến của lần chạy, dùng để cấu hình các step.
- `@StepScope`: reader riêng cho từng step execution, lấy tenant/range từ step context.
- Singleton `OrderValidationService`: logic validation stateless dùng chung.
- `StepExecutionContext`: checkpoint reader và trạng thái cần restart.
- Database/outbox: trạng thái nghiệp vụ cần tồn tại sau process restart và side effect cần phát đi.

```text
JobParameters
  businessDate, batchId, inputFile
          |
          v
JobExecution
  JobExecutionContext
          |
          +-- ValidateStep / StepExecution
          |      @StepScope reader/worker
          |      StepExecutionContext checkpoint
          |
          +-- ImportStep / StepExecution
          |      @StepScope reader/writer
          |      StepExecutionContext checkpoint
          |
          +-- ReportStep / StepExecution
                 @StepScope output resource

Singleton services: stateless logic shared in one ApplicationContext
Database/outbox: durable state shared across executions and nodes
```

Mỗi loại state có một chủ sở hữu rõ ràng. Khi job restart, Spring Batch dùng parameters và execution context để khôi phục luồng xử lý; singleton service được tạo lại theo ApplicationContext; database/outbox vẫn lưu trạng thái bền vững. Không cần dùng một field global để truyền trạng thái giữa các step hoặc node.

## 23. Cách thiết kế scoped bean trong production

Trước tiên, dùng `@StepScope` cho thành phần cần tham số hoặc context riêng của `StepExecution`, đặc biệt reader/writer theo partition, file hoặc tenant. Dùng `@JobScope` cho object cần thông tin thuộc về một `JobExecution`, nhưng cẩn trọng khi flow có multi-threading hoặc partitioning. Dùng singleton cho service stateless, repository và cấu hình dùng chung.

Tiếp theo, không coi field trong scoped bean là nơi lưu state bền vững. Dùng `ExecutionContext` cho checkpoint và dữ liệu cần khôi phục theo job/step; dùng `JobParameters` cho input của lần chạy; dùng database hoặc distributed store cho state cần chia sẻ qua execution/process/node.

Cuối cùng, kiểm tra concurrency theo scope thực tế. Step-scoped target không tự tạo một instance cho mỗi thread trong cùng step; job-scoped target cũng không phải state riêng từng partition. Tránh mutable field trong singleton/scoped bean nếu không có thiết kế đồng bộ. Test hai job chạy đồng thời, partition chạy song song và restart để xác nhận state không rò rỉ giữa execution.

Không dùng scoped bean cho state toàn cục là nguyên tắc về quyền sở hữu và vòng đời dữ liệu. `@StepScope` dành cho một step execution, `@JobScope` dành cho một job execution, singleton dành cho một ApplicationContext, còn state bền vững hoặc chia sẻ nhiều node cần một kho lưu trữ phù hợp. Khi chọn đúng phạm vi, job có thể chạy đồng thời và restart mà không làm lẫn state giữa các execution.
