# Transaction manager cho JPA

Khi một Spring Batch Step dùng JPA để ghi dữ liệu, transaction manager của chunk cần quản lý đúng `EntityManagerFactory` mà Writer sử dụng. Thành phần thường dùng là `JpaTransactionManager`. Nó mở và quản lý transaction JPA cho một `EntityManagerFactory`, gắn `EntityManager` với thread đang chạy Step và phối hợp commit/rollback khi chunk kết thúc.

Trong Spring Batch 5, transaction manager được truyền rõ ràng vào `chunk(...)` của `StepBuilder`. Vì vậy, cần phân biệt transaction manager dành cho chunk nghiệp vụ với transaction manager mà `JobRepository` dùng để lưu metadata. Nếu hai phần dùng datasource hoặc persistence unit khác nhau, chúng không tự động trở thành một transaction nguyên tử.

## 1. Transaction manager có vai trò gì trong JPA Step?

Một chunk-oriented Step đọc, xử lý và ghi một nhóm item trong transaction. Với JPA, transaction xác định khi nào thay đổi trong persistence context được đồng bộ xuống database và khi nào chúng được commit.

Ví dụ một Step import đơn hàng:

```text
JobRepository
    |
    v
Step: importOrdersStep
    |
    v
JpaTransactionManager.begin()
    |
    +--> ItemReader
    +--> ItemProcessor
    +--> JpaItemWriter
    |       EntityManager.persist / merge
    |       EntityManager.flush
    |
    v
Transaction commit
    |
    v
Checkpoint / Step execution metadata
```

Khi chunk thành công, transaction manager commit các thay đổi của JPA. Nếu có exception làm chunk rollback, các thay đổi chưa commit trong transaction đó được hoàn tác.

Transaction manager phải gắn với đúng persistence unit. Nếu Writer dùng `EntityManagerFactory` A nhưng Step lại chạy bằng transaction manager của persistence unit B, JPA operation có thể không tham gia transaction chunk như dự kiến.

## 2. JpaTransactionManager là gì?

`JpaTransactionManager` là implementation của `PlatformTransactionManager` dành cho JPA. Nó quản lý transaction cho một `EntityManagerFactory`.

Trong transaction, Spring bind `EntityManager` phù hợp với thread hiện tại. Các thành phần Spring như `JpaItemWriter` hoặc repository JPA có thể lấy `EntityManager` đang tham gia transaction thay vì tự tạo một transaction độc lập.

Khai báo bean cơ bản:

```java
import jakarta.persistence.EntityManagerFactory;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class JpaTransactionConfig {

    @Bean("jpaTransactionManager")
    public PlatformTransactionManager jpaTransactionManager(
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Ví dụ dùng Jakarta Persistence như các ứng dụng Spring Boot 3/Spring Batch 5. Với ứng dụng cũ dùng Spring Batch 4 và Java EE namespace, import có thể là `javax.persistence.EntityManagerFactory`; hãy dùng namespace đúng với phiên bản dependency của dự án.

`JpaTransactionManager` thường được dùng cùng `JpaItemWriter`, Spring Data JPA repository và service sử dụng `@Transactional` trên cùng persistence unit.

## 3. Gắn đúng transaction manager vào chunk()

Trong Spring Batch 5, `StepBuilder` nhận `JobRepository`; transaction manager của chunk được truyền vào `chunk(commitInterval, transactionManager)`:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager jpaTransactionManager,
        ItemReader<Order> orderReader,
        ItemProcessor<Order, Order> orderProcessor,
        ItemWriter<Order> orderWriter) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(200, jpaTransactionManager)
            .reader(orderReader)
            .processor(orderProcessor)
            .writer(orderWriter)
            .build();
}
```

Nếu application có nhiều `PlatformTransactionManager`, hãy inject bằng `@Qualifier` thay vì dựa vào tên tham số hoặc bean `@Primary` một cách ngầm định:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("jpaTransactionManager")
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(reader)
            .writer(writer)
            .build();
}
```

`chunk(200, transactionManager)` có nghĩa mỗi chunk gồm tối đa 200 item được xử lý trong transaction do manager đó quản lý. Commit interval không phải số lần commit của từng Writer; tất cả JPA changes tham gia cùng transaction đó sẽ được commit theo ranh giới chunk.

## 4. Kết hợp JpaItemWriter với JpaTransactionManager

`JpaItemWriter<T>` ghi các item vào database qua `EntityManager`. Nó cần `EntityManagerFactory` tương ứng với `JpaTransactionManager` của Step.

Ví dụ dùng builder:

```java
import jakarta.persistence.EntityManagerFactory;

import org.springframework.batch.item.database.JpaItemWriter;
import org.springframework.batch.item.database.builder.JpaItemWriterBuilder;
import org.springframework.context.annotation.Bean;

@Bean
public JpaItemWriter<Order> orderJpaWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .usePersist(false)
            .build();
}
```

Theo cấu hình trên, Writer dùng `merge` theo mặc định (`usePersist(false)`). `merge` phù hợp khi item có thể là entity detached cần đồng bộ vào persistence context. Nếu tất cả item đều là entity mới và chưa có identity trong persistence context, có thể chọn `usePersist(true)` để gọi `persist`.

Không chọn `persist` chỉ vì muốn ghi nhanh hơn. Nếu entity đã tồn tại hoặc đã có identity trong database, `persist` có thể dẫn đến lỗi entity đã tồn tại hoặc vi phạm khóa. Cần xác định rõ item là entity mới hay entity cần cập nhật.

`JpaItemWriter` flush persistence context theo cấu hình của nó trước khi kết thúc thao tác ghi. Flush đồng bộ câu lệnh SQL xuống database connection, nhưng transaction vẫn chưa commit cho đến khi transaction manager commit chunk. Nếu exception xảy ra sau flush nhưng trước commit, database vẫn có thể rollback các thay đổi trong transaction.

## 5. persist và merge khác nhau thế nào?

Hai thao tác này có semantics khác nhau:

| Thao tác | Dùng cho | Hành vi |
|---|---|---|
| `EntityManager.persist(entity)` | Entity mới, transient | Đưa chính instance đó vào persistence context để insert khi flush/commit. |
| `EntityManager.merge(entity)` | Entity detached hoặc dữ liệu cần đồng bộ | Copy state vào một instance managed; giá trị trả về là instance managed. |

Một điểm dễ nhầm là `merge()` không làm cho object truyền vào trở thành managed. Nó trả về một object managed khác hoặc instance managed tương ứng. Nếu code tiếp tục thay đổi object gốc sau `merge`, những thay đổi đó không nhất thiết được đồng bộ như mong đợi.

Với dữ liệu import, nếu mỗi record đại diện một entity mới, có thể dùng `persist`. Nếu record có thể cập nhật entity đã tồn tại, có thể dùng `merge` hoặc tốt hơn là tìm entity theo business key rồi cập nhật các field được phép.

`merge` không tự bảo đảm idempotency nghiệp vụ. Nếu mỗi lần retry tạo entity mới với ID mới, database vẫn có thể chứa duplicate. Dùng unique constraint theo business key và xác định chính sách insert/update.

## 6. Cấu hình JpaPagingItemReader và JPA transaction manager

Spring Batch cung cấp `JpaPagingItemReader` để đọc dữ liệu qua JPA theo trang. Ví dụ:

```java
import jakarta.persistence.EntityManagerFactory;

import org.springframework.batch.item.database.JpaPagingItemReader;
import org.springframework.batch.item.database.builder.JpaPagingItemReaderBuilder;
import org.springframework.context.annotation.Bean;

@Bean
public JpaPagingItemReader<SourceOrder> sourceOrderReader(
        EntityManagerFactory entityManagerFactory) {

    return new JpaPagingItemReaderBuilder<SourceOrder>()
            .name("sourceOrderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("select o from SourceOrder o order by o.id")
            .pageSize(200)
            .saveState(true)
            .build();
}
```

Query cần có thứ tự ổn định và duy nhất, thường là `ORDER BY` theo primary key. Nếu query không có thứ tự xác định, dữ liệu có thể dịch chuyển giữa các trang; restart hoặc paging có thể dẫn đến bỏ sót hay đọc lặp item.

`JpaPagingItemReader` quản lý cách đọc theo page và persistence context của Reader. Cần đọc tài liệu đúng phiên bản về tùy chọn `transacted` và trạng thái detached của entity sau khi đọc. Nếu Processor cần thay đổi entity hoặc truy cập lazy association, hãy xác định rõ entity còn managed hay đã detached; không dựa vào Open Session in View trong batch.

Reader và Writer có thể dùng cùng `EntityManagerFactory` nếu đọc và ghi cùng persistence unit. Nếu đọc từ source persistence unit và ghi sang target persistence unit khác, xem phần nhiều persistence unit bên dưới.

## 7. EntityManagerFactory và transaction manager phải cùng persistence unit

Mối quan hệ cần nhất quán:

```text
EntityManagerFactory (ordersEntityManagerFactory)
             |
             v
JpaTransactionManager (ordersTransactionManager)
             |
             v
Step.chunk(..., ordersTransactionManager)
             |
             v
JpaItemWriter dùng ordersEntityManagerFactory
```

Nếu có nhiều `EntityManagerFactory`, không inject bean mặc định một cách mơ hồ. Hãy đặt tên và qualifier:

```java
@Bean("ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
```

Writer cũng phải dùng đúng factory:

```java
@Bean
JpaItemWriter<Order> orderWriter(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {
    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .build();
}
```

Khi một Writer dùng factory khác với transaction manager của Step, JPA operation có thể mở persistence context/transaction khác hoặc không tham gia chunk transaction. Điều này khiến rollback không bao gồm các thay đổi mà ứng dụng tưởng rằng đang được bảo vệ.

## 8. Nhiều transaction manager: phân biệt JobRepository và chunk

Spring Batch có hai nhóm transaction cần phân biệt:

- Transaction của `JobRepository` để lưu JobExecution, StepExecution và ExecutionContext.
- Transaction của chunk để quản lý thao tác đọc/xử lý/ghi nghiệp vụ.

Nếu metadata dùng JDBC datasource riêng còn dữ liệu nghiệp vụ dùng JPA, có thể có hai transaction manager:

```text
Batch metadata database
  batchDataSource
       |
       v
  batchTransactionManager
       |
       v
  JobRepository

Business JPA database
  businessEntityManagerFactory
       |
       v
  jpaTransactionManager
       |
       v
  Step.chunk(..., jpaTransactionManager)
```

Ví dụ cấu hình hạ tầng Batch trong Spring Batch 5:

```java
@Configuration
@EnableBatchProcessing(
        dataSourceRef = "batchDataSource",
        transactionManagerRef = "batchTransactionManager")
public class BatchInfrastructureConfig {
}
```

Trong khi đó, Step nghiệp vụ nhận `jpaTransactionManager` trong `chunk(...)`. `transactionManagerRef` ở `@EnableBatchProcessing` chỉ định transaction manager cho Batch infrastructure/JobRepository; nó không tự thay thế transaction manager được truyền vào từng chunk Step.

Nếu metadata và business data nằm ở hai database, local transaction của chúng không tự động commit/rollback nguyên tử cùng nhau. Có thể xảy ra tình huống dữ liệu nghiệp vụ đã commit nhưng checkpoint metadata chưa được lưu, hoặc ngược lại. Writer cần idempotent và hệ thống cần có chiến lược reconciliation; nếu bắt buộc atomicity xuyên database, cần giải pháp distributed transaction như JTA/XA.

## 9. Dùng Spring Data JPA repository trong Processor hoặc service

Một Processor hoặc service được gọi trong chunk có thể sử dụng Spring Data JPA repository. Nếu repository và Step cùng dùng `JpaTransactionManager` cho cùng persistence unit, các thao tác repository với propagation mặc định `REQUIRED` sẽ tham gia transaction đang có.

Ví dụ:

```java
@Service
public class OrderImportService {

    private final ImportedOrderRepository repository;

    public OrderImportService(ImportedOrderRepository repository) {
        this.repository = repository;
    }

    public void save(Order order) {
        repository.save(order);
    }
}
```

Nếu service được gọi từ Writer/Processor trong chunk, hãy bảo đảm repository dùng cùng `EntityManagerFactory` và transaction manager. Không cần mở transaction độc lập cho mỗi item nếu thao tác cần commit cùng chunk.

Nếu service có `@Transactional`, hãy chỉ rõ manager khi có nhiều manager:

```java
@Transactional(transactionManager = "jpaTransactionManager")
public void updateOrder(Order order) {
    repository.save(order);
}
```

Propagation `REQUIRED` thường tham gia transaction chunk đang tồn tại. `REQUIRES_NEW` tạo transaction độc lập; nếu dùng không chủ ý, dữ liệu có thể commit dù chunk bên ngoài rollback. Điều này phá vỡ kỳ vọng atomicity theo chunk.

## 10. Flush không đồng nghĩa với commit

JPA sử dụng persistence context để theo dõi thay đổi. Khi `flush()` được gọi, Hibernate/JPA đồng bộ các thay đổi thành câu lệnh SQL tới database. Nhưng transaction vẫn có thể chưa commit.

```text
EntityManager.persist(order)
        |
        v
Entity ở persistence context
        |
        v
EntityManager.flush()
        |
        v
SQL INSERT được gửi tới database
        |
        v
Transaction commit
        |
        v
Thay đổi được commit
```

Nếu một constraint violation xảy ra khi flush, exception có thể được phát hiện trước khi commit. Nếu flush thành công nhưng sau đó một item khác gây lỗi, transaction vẫn có thể rollback.

Không nên gọi `EntityManager.getTransaction().commit()` bên trong Writer khi Spring đang quản lý transaction. Làm vậy tạo xung đột với transaction manager và có thể gây `TransactionRequiredException`, trạng thái transaction không nhất quán hoặc dữ liệu commit ngoài chunk.

## 11. Persistence context và kích thước chunk

Persistence context theo dõi entity đã load hoặc thay đổi. Với chunk lớn, số entity managed có thể tăng và chiếm nhiều memory. `JpaItemWriter` có tùy chọn clear persistence context sau khi ghi; cần cân nhắc khi batch xử lý nhiều item.

Ví dụ:

```java
@Bean
JpaItemWriter<Order> orderWriter(EntityManagerFactory entityManagerFactory) {
    return new JpaItemWriterBuilder<Order>()
            .entityManagerFactory(entityManagerFactory)
            .usePersist(false)
            .build();
}
```

Nếu cần kiểm soát persistence context, có thể cấu hình writer theo API của phiên bản Spring Batch đang dùng hoặc dùng một Writer tùy chỉnh quản lý `flush()`/`clear()` trong transaction. Không clear persistence context khi các entity còn cần được truy cập như managed object trong cùng chunk.

Chunk size cần cân bằng giữa throughput, memory, thời gian giữ lock và phạm vi rollback. Chunk quá lớn có thể tạo persistence context lớn và transaction kéo dài. Chunk quá nhỏ làm tăng số lần commit và overhead metadata.

## 12. Kết hợp JPA và JdbcTemplate trên cùng database

Một Step có thể dùng JPA cho một phần và JDBC cho phần khác. Nếu cả hai truy cập cùng database, có thể phối hợp trong một transaction khi `JpaTransactionManager` được cấu hình với datasource phù hợp và JDBC code lấy connection qua cơ chế Spring như `JdbcTemplate`/`DataSourceUtils`.

Ví dụ:

```java
@Bean
JdbcTemplate businessJdbcTemplate(
        @Qualifier("businessDataSource") DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}

@Bean
PlatformTransactionManager jpaTransactionManager(
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
```

`EntityManagerFactory` cần gắn với cùng `businessDataSource`. `JpaTransactionManager` có thể cung cấp JDBC connection đồng bộ với transaction JPA khi datasource được nhận diện/cấu hình và `JpaDialect` hỗ trợ. Nếu datasource không được tự phát hiện, cần cấu hình datasource tương ứng cho transaction manager theo API phù hợp.

Không dùng `DriverManager.getConnection()` hoặc tự mở connection độc lập trong Writer nếu muốn JDBC statement tham gia transaction JPA hiện tại. Kết nối tự mở thường không được `JpaTransactionManager` quản lý và có thể commit độc lập.

Nếu JPA và JDBC dùng hai datasource khác nhau, chúng không cùng transaction chỉ vì cùng nằm trong một Step. Cần tách Step hoặc dùng distributed transaction/consistency pattern.

## 13. Nhiều EntityManagerFactory hoặc nhiều database

`JpaTransactionManager` quản lý một `EntityManagerFactory`. Nếu ứng dụng có source persistence unit và target persistence unit, thường khai báo hai factory và hai transaction manager:

```text
sourceEntityManagerFactory
       |
       v
sourceJpaTransactionManager

targetEntityManagerFactory
       |
       v
targetJpaTransactionManager
```

Một Step đọc từ source và ghi vào target có thể chọn transaction manager của target cho chunk, trong khi Reader dùng source factory để đọc. Tuy nhiên, transaction của target không tự quản lý transaction đọc riêng của source. Nếu yêu cầu snapshot nhất quán giữa hai database, cần cơ chế snapshot/watermark hoặc distributed transaction phù hợp.

Không thể truyền hai `JpaTransactionManager` độc lập vào một `chunk(...)` để tự động commit cả hai. Nếu cả hai database phải cùng commit/rollback nguyên tử, cần JTA/XA với resource hỗ trợ XA và transaction coordinator được cấu hình đúng. Nếu chấp nhận eventual consistency, dùng outbox, idempotency key, retry và reconciliation.

## 14. Rollback và retry khi dùng JPA Writer

Khi JPA Writer ném exception trong chunk, transaction manager rollback transaction của chunk. Các thay đổi JPA chưa commit được hoàn tác. Nếu Step được cấu hình retry, item/chunk có thể được xử lý lại theo policy.

Ví dụ cấu hình retry lỗi database tạm thời:

```java
return new StepBuilder("saveOrdersStep", jobRepository)
        .<Order, Order>chunk(100, jpaTransactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderJpaWriter)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .build();
```

Chỉ retry exception có khả năng tạm thời. Constraint violation do dữ liệu không hợp lệ thường không tự hết khi thử lại. Nếu muốn skip lỗi nghiệp vụ, hãy phân loại exception cụ thể và giới hạn số skip.

Khi chunk được retry hoặc Job restart, cùng business item có thể tới Writer lần nữa. Dùng unique constraint, upsert hoặc lookup theo business key để ngăn duplicate. Không dựa vào một entity ID mới được sinh trong mỗi lần thử để nhận diện cùng nghiệp vụ.

## 15. Restart và JobRepository khi dùng JPA

Restart cần metadata bền vững từ JobRepository và checkpoint được lưu tại ranh giới commit của Step. Với JPA Reader/Writer, cần:

1. JobRepository dùng database bền vững.
2. Reader triển khai `ItemStream` và bật `saveState(true)` nếu cần checkpoint.
3. Tên Reader/Writer ổn định giữa các lần chạy.
4. Cùng identifying JobParameters khi restart cùng JobInstance.
5. Nguồn dữ liệu có thứ tự/snapshot ổn định.
6. Writer idempotent để xử lý lại item thuộc chunk chưa commit hoặc tình huống metadata/business transaction lệch nhau.

Nếu metadata database và business database khác nhau, commit của chúng có thể không atomic. Đây là lý do idempotency vẫn cần thiết ngay cả khi Reader đã lưu checkpoint đúng.

Không sửa trực tiếp bảng `BATCH_*` để đặt lại checkpoint hoặc trạng thái transaction. Dùng API Spring Batch như `JobOperator`, `JobExplorer` và quy trình vận hành có kiểm soát.

## 16. Kiểm thử transaction manager cho JPA Step

Nên có integration test với database thật hoặc Testcontainers phù hợp để xác nhận transaction manager thực sự quản lý JPA changes.

Các kịch bản hữu ích:

1. **Commit chunk:** Writer lưu các entity; sau khi chunk thành công, xác nhận dữ liệu có trong database.
2. **Rollback chunk:** làm Writer ném exception sau khi persist một số entity; xác nhận không có thay đổi của chunk thất bại được commit.
3. **Retry:** mô phỏng lỗi tạm thời ở lần đầu và thành công ở lần sau; xác nhận kết quả cuối không trùng.
4. **Restart:** làm Job thất bại sau một số chunk đã commit, restart cùng JobInstance và xác nhận Reader tiếp tục đúng checkpoint.
5. **Qualifier:** khi có nhiều transaction manager, xác nhận Step sử dụng manager của đúng EntityManagerFactory.
6. **JPA và JDBC cùng transaction:** xác nhận JDBC update rollback cùng JPA update nếu dùng cùng datasource và manager được cấu hình phù hợp.
7. **REQUIRES_NEW:** nếu có service dùng propagation này, kiểm tra rõ dữ liệu nào vẫn commit khi chunk ngoài rollback.
8. **Nhiều database:** kiểm thử lỗi một resource và xác nhận XA hoặc reconciliation theo thiết kế.

Ví dụ test rollback khái quát:

```java
assertEquals(BatchStatus.FAILED, jobExecution.getStatus());
assertEquals(0, orderRepository.countByBatchId(failedBatchId));
```

Test cần bảo đảm lỗi xảy ra trong cùng chunk và query xác nhận được chạy sau khi transaction kết thúc. Nếu có chunk trước đã commit, chỉ xác nhận dữ liệu của chunk thất bại được rollback; không kỳ vọng toàn bộ Job tự xóa dữ liệu của các chunk thành công trước đó.

## 17. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng `DataSourceTransactionManager` cho JPA Writer mà không phối hợp JPA | EntityManager có thể không tham gia transaction chunk như mong đợi. | Dùng `JpaTransactionManager` cho đúng EntityManagerFactory. |
| Step dùng transaction manager của persistence unit khác | JPA Writer có thể commit ngoài transaction Step. | Dùng `@Qualifier` và ghép đúng factory/manager. |
| Nhầm `transactionManagerRef` của Batch infrastructure với TM của chunk | Step có thể dùng sai transaction manager. | Truyền manager nghiệp vụ vào `chunk(...)` một cách tường minh. |
| Gọi `EntityManager.getTransaction().commit()` thủ công | Xung đột với transaction do Spring quản lý. | Để Step transaction manager commit/rollback. |
| Dùng `REQUIRES_NEW` không chủ ý | Một phần dữ liệu commit dù chunk ngoài rollback. | Dùng propagation `REQUIRED` khi cần cùng chunk transaction. |
| Nhầm flush với commit | SQL đã gửi nhưng transaction vẫn có thể rollback. | Hiểu flush và commit là hai bước khác nhau. |
| Dùng `persist` cho entity đã tồn tại | Có thể lỗi entity/duplicate key. | Chọn persist cho entity mới, merge/update cho entity detached/tồn tại. |
| Persistence context quá lớn | Tốn memory và làm transaction kéo dài. | Điều chỉnh chunk size và chiến lược flush/clear. |
| Hai EntityManagerFactory nhưng một JpaTransactionManager | Manager chỉ điều phối một persistence unit. | Khai báo manager riêng hoặc dùng JTA/XA nếu cần atomicity. |
| Không có business key chống duplicate | Retry/restart có thể tạo bản ghi trùng. | Unique constraint, upsert và idempotency. |

## Kết luận

`JpaTransactionManager` quản lý transaction JPA cho một `EntityManagerFactory`. Trong Spring Batch 5, hãy truyền đúng manager vào `StepBuilder.chunk(...)` và bảo đảm `JpaItemWriter` dùng cùng factory. `flush()` chỉ đồng bộ SQL, còn commit/rollback vẫn do transaction manager điều khiển ở ranh giới chunk. Khi có nhiều transaction manager, cần tách rõ manager của JobRepository và manager của dữ liệu nghiệp vụ; local transaction của nhiều database không tự động atomic. Kết hợp checkpoint, business key, unique constraint và Writer idempotent để restart an toàn, đồng thời kiểm thử commit, rollback, retry và restart trên đúng loại database mà ứng dụng sử dụng.
