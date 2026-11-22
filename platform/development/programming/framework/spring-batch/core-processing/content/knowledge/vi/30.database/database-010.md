# DataSourceTransactionManager

`DataSourceTransactionManager` là implementation của Spring Framework cho `PlatformTransactionManager`, dùng để quản lý transaction JDBC trên một `DataSource`. Nó mở hoặc lấy một JDBC `Connection`, gắn connection đó với thread đang thực thi, rồi commit hoặc rollback khi transaction kết thúc.

Trong Spring Batch, transaction manager này thường được truyền vào chunk-oriented step. Nhờ đó các thao tác JDBC được thực hiện trong cùng transaction của chunk nếu chúng dùng cùng `DataSource` thông qua các API tích hợp với Spring như `JdbcTemplate` hoặc `DataSourceUtils`.

Điều quan trọng là transaction manager chỉ quản lý một tài nguyên JDBC `DataSource` theo cơ chế local transaction. Nó không tự tạo transaction phân tán cho nhiều database, file system hoặc HTTP service. Khi thiết kế batch job, cần xác định chính xác resource nào tham gia transaction và resource nào cần idempotency, outbox hoặc compensation.

## 1. Vai trò của DataSourceTransactionManager

`DataSourceTransactionManager` triển khai hợp đồng `PlatformTransactionManager`. Nó quản lý transaction JDBC bằng cách làm việc trực tiếp với connection lấy từ `DataSource`.

Các trách nhiệm chính:

- Lấy JDBC connection khi transaction bắt đầu.
- Thiết lập các thuộc tính transaction như isolation level, read-only và timeout nếu được cấu hình và driver hỗ trợ.
- Gắn connection với thread hiện tại để các thao tác JDBC tiếp theo có thể dùng lại connection đó.
- Commit khi transaction hoàn tất bình thường.
- Rollback khi transaction kết thúc với điều kiện yêu cầu rollback.
- Trả connection về pool hoặc đóng connection theo cách `DataSource` quản lý.

`DataSourceTransactionManager` phù hợp với ứng dụng sử dụng một database JDBC và cần local transaction cho các thao tác đọc/ghi. Nếu ứng dụng dùng JDBC và muốn exception translation bổ sung cho lỗi commit/rollback, Spring cũng cung cấp `JdbcTransactionManager`, một lớp mở rộng của `DataSourceTransactionManager`.

## 2. Connection được gắn với thread hiện tại

Khi transaction bắt đầu, `DataSourceTransactionManager` lấy một connection từ `DataSource` và bind connection đó vào thread qua cơ chế đồng bộ transaction của Spring. Các API như `JdbcTemplate` gọi `DataSourceUtils` để tìm connection đang được bind và dùng lại nó.

```text
Thread đang chạy chunk
       |
       v
DataSourceTransactionManager
       |
       +--> lấy Connection từ DataSource
       |
       +--> bind Connection vào thread
       |
       v
JdbcTemplate / DataSourceUtils
       |
       +--> tìm connection đã bind
       +--> thực thi SQL trên cùng connection
       |
       v
Commit hoặc rollback
       |
       +--> unbind và release Connection
```

Nhờ vậy, nhiều DAO hoặc repository cùng dùng một transaction manager và một `DataSource` có thể tham gia cùng transaction mà không phải truyền connection qua từng method.

Transaction context gắn với thread. Nếu code tự tạo thread mới hoặc gửi công việc sang executor khác, thread mới không tự động nhận transaction connection của thread cha. Mỗi worker thread cần transaction riêng hoặc cơ chế điều phối transaction được thiết kế rõ ràng.

## 3. Vì sao nên dùng JdbcTemplate hoặc DataSourceUtils?

Để tham gia transaction do `DataSourceTransactionManager` quản lý, các thao tác JDBC cần lấy connection thông qua cơ chế Spring transaction-aware.

`JdbcTemplate` tự sử dụng `DataSourceUtils`, nên thường là lựa chọn đơn giản:

```java
@Repository
public class OrderRepository {

    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void insert(Order order) {
        jdbcTemplate.update(
            "INSERT INTO ORDERS (ORDER_ID, CUSTOMER_ID, TOTAL) VALUES (?, ?, ?)",
            order.getOrderId(),
            order.getCustomerId(),
            order.getTotalAmount()
        );
    }
}
```

Nếu phải dùng JDBC API trực tiếp, hãy lấy và release connection qua `DataSourceUtils`:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement statement = connection.prepareStatement(
        "UPDATE ORDERS SET STATUS = ? WHERE ORDER_ID = ?")) {
    statement.setString(1, "PROCESSED");
    statement.setLong(2, orderId);
    statement.executeUpdate();
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
```

`releaseConnection` không đóng connection đang được transaction quản lý; nó chỉ release theo quy tắc của Spring. Không gọi `connection.close()` trực tiếp với connection lấy từ `DataSourceUtils` trong transaction, vì có thể đóng connection đang được transaction sử dụng.

Nếu code gọi trực tiếp `dataSource.getConnection()` trên một pool thông thường, có thể nhận connection khác với connection đã bind vào transaction. Khi đó câu lệnh SQL có thể chạy ngoài transaction của chunk và không rollback cùng các thao tác khác. Chỉ dùng direct connection khi bạn chủ động quản lý transaction/resource riêng và hiểu rõ hệ quả.

## 4. Khai báo DataSourceTransactionManager

Trong cấu hình Java, có thể khai báo transaction manager như một bean:

```java
@Configuration
public class BatchDatabaseConfiguration {

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

Bean nhận `DataSource` do ứng dụng cấu hình, thường là connection pool được Spring Boot hoặc cấu hình datasource của dự án tạo ra. Hãy bảo đảm repository, `JdbcTemplate` và transaction manager cùng trỏ đến đúng `DataSource` khi cần tham gia một transaction.

Nếu dùng nhiều transaction manager, đặt tên bean và inject bằng `@Qualifier` để tránh chọn nhầm:

```java
@Bean("ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
```

Trong Spring Batch 5, transaction manager được truyền rõ vào builder của chunk hoặc tasklet step. Điều này làm ranh giới transaction của step dễ nhìn thấy trong cấu hình.

## 5. Truyền transaction manager vào chunk step

Ví dụ chunk step đọc và ghi đơn hàng bằng JDBC:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        @Qualifier("ordersTransactionManager") PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

Với `chunk(100, transactionManager)`, Spring Batch xử lý tối đa 100 item trong một chunk transaction theo cấu hình step. Khi chunk hoàn tất, transaction manager commit; nếu có exception yêu cầu rollback, transaction hiện tại được rollback.

Tasklet step cũng cần transaction manager:

```java
@Bean
Step archiveStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet archiveTasklet) {

    return new StepBuilder("archive", jobRepository)
        .tasklet(archiveTasklet, transactionManager)
        .build();
}
```

Không nhầm transaction manager của step với `JobRepository`. `JobRepository` lưu metadata của job/step; transaction manager được step dùng để bao transaction xử lý chunk hoặc tasklet. Cấu hình hạ tầng batch cũng cần transaction manager phù hợp để quản lý metadata theo datasource của repository.

## 6. Transaction boundary trong chunk processing

Với chunk-oriented step, một transaction thường bao quanh việc xử lý một chunk. Reader lấy các item, processor biến đổi item, writer ghi chunk và Spring Batch cập nhật state của `ItemStream` theo lifecycle. Khi công việc của chunk hoàn tất, transaction commit.

```text
Chunk 1
  BEGIN
    read/process/write item 1..100
    update stream state
  COMMIT

Chunk 2
  BEGIN
    read/process/write item 101..200
    update stream state
  ROLLBACK nếu có lỗi cần rollback

Chunk 3
  chỉ chạy nếu step recovery/policy cho phép tiếp tục
```

Chunk size là một phần của thiết kế transaction. Chunk lớn giảm số lần commit nhưng giữ connection và transaction lâu hơn, tăng lượng công việc phải rollback khi lỗi. Chunk nhỏ commit thường xuyên hơn nhưng có thể tăng overhead database.

Không nên giả định mỗi item có một transaction riêng khi dùng chunk processing. Nếu cần transaction boundary khác, phải thiết kế step hoặc service transaction rõ ràng.

## 7. Transaction tham gia qua @Transactional

Service được gọi từ processor/writer có thể tham gia transaction chunk nếu nó dùng cùng transaction manager và propagation mặc định `REQUIRED`.

```java
@Service
public class OrderUpdateService {

    private final JdbcTemplate jdbcTemplate;

    public OrderUpdateService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional
    public void markProcessed(long orderId) {
        jdbcTemplate.update(
            "UPDATE ORDERS SET STATUS = 'PROCESSED' WHERE ORDER_ID = ?",
            orderId
        );
    }
}
```

Nếu `markProcessed` được gọi bên trong chunk transaction và sử dụng cùng transaction manager, `REQUIRED` thường tham gia transaction hiện tại. Khi chunk rollback, thay đổi này cũng rollback.

Chú ý cơ chế proxy của Spring: lời gọi `@Transactional` phải đi qua proxy để advice được áp dụng. Self-invocation bên trong cùng object không đi qua proxy theo cơ chế proxy-based thông thường. Cũng cần bảo đảm bean dùng đúng transaction manager khi ứng dụng có nhiều datasource.

## 8. Propagation và REQUIRES_NEW

Propagation xác định một method transactional tham gia transaction hiện tại hay tạo transaction khác.

| Propagation | Hành vi khái quát | Tác động trong chunk |
|---|---|---|
| `REQUIRED` | Tham gia transaction hiện tại; nếu chưa có thì tạo mới | Thường phù hợp cho service ghi cùng database với chunk |
| `REQUIRES_NEW` | Tạm treo transaction hiện tại và tạo transaction mới | Có thể commit độc lập dù chunk bên ngoài rollback |
| `SUPPORTS` | Tham gia nếu có transaction, nếu không thì chạy không transaction | Cần hiểu rõ caller context |
| `MANDATORY` | Yêu cầu phải có transaction hiện tại | Hữu ích khi service không được gọi độc lập |
| `NOT_SUPPORTED` | Chạy không có transaction, tạm treo transaction hiện tại | Không phù hợp cho thao tác cần rollback cùng chunk |
| `NESTED` | Dùng nested transaction/savepoint nếu manager và driver hỗ trợ | Có thể rollback một phần trong transaction ngoài |

`REQUIRES_NEW` cần được dùng có chủ đích. Ví dụ, nếu service ghi audit trong transaction mới rồi chunk bên ngoài rollback, audit record vẫn tồn tại. Điều đó có thể đúng cho audit về lần thử, nhưng sai nếu record được hiểu là nghiệp vụ đã commit.

`NESTED` phụ thuộc hỗ trợ savepoint của JDBC driver và transaction manager. Không nên giả định mọi database hoặc mọi cấu hình đều hỗ trợ nested transaction.

## 9. Rollback rules và checked exception

Với transaction declarative của Spring, mặc định `RuntimeException` và `Error` làm transaction rollback; checked exception không tự động làm rollback theo quy tắc mặc định, trừ khi cấu hình rollback rule phù hợp.

Ví dụ yêu cầu rollback với một checked exception:

```java
@Transactional(rollbackFor = PartnerFileException.class)
public void importPartnerFile() throws PartnerFileException {
    // Các thao tác JDBC cần cùng transaction
}
```

Trong Spring Batch, fault-tolerant step còn có retry/skip và rollback classification. Vì vậy, cần phân biệt rollback rule của transaction manager với skip/retry policy của step. Một exception có thể được phép skip nhưng vẫn làm rollback chunk trước khi framework recovery; cấu hình `noRollback` có semantics riêng và chỉ nên dùng sau khi hiểu các thay đổi đã thực hiện.

Không bắt exception rồi nuốt trong writer hoặc service nếu muốn Spring Batch nhận biết lỗi để rollback/retry/skip. Hãy để exception truyền ra ngoài hoặc chuyển thành exception có ý nghĩa phù hợp.

## 10. Isolation level

Isolation level kiểm soát mức độ một transaction nhìn thấy thay đổi của transaction khác. `DataSourceTransactionManager` có thể áp dụng isolation level thông qua JDBC connection khi transaction bắt đầu, nếu driver/database hỗ trợ.

Các mức JDBC thường gặp:

| Isolation | Đặc điểm khái quát |
|---|---|
| `READ_UNCOMMITTED` | Có thể đọc dữ liệu chưa commit của transaction khác nếu database hỗ trợ |
| `READ_COMMITTED` | Chỉ đọc dữ liệu đã commit tại thời điểm đọc |
| `REPEATABLE_READ` | Giảm khả năng cùng một row trả về giá trị khác trong cùng transaction; phantom behavior tùy database |
| `SERIALIZABLE` | Mức cô lập cao, có thể giảm concurrency và tăng contention |

Không có một isolation level tối ưu cho mọi batch job. Chọn theo tính đúng đắn nghiệp vụ, database engine, query pattern và khả năng chịu tải. `SERIALIZABLE` có thể tăng deadlock hoặc thời gian chờ; `READ_COMMITTED` thường đủ cho nhiều job nhưng không bảo đảm một snapshot toàn bộ dữ liệu xuyên suốt nhiều chunk.

Nếu job cần đọc một snapshot nhất quán cho toàn bộ lần chạy, cần xem xét snapshot isolation, watermark hoặc snapshot staging. Một transaction riêng cho mỗi chunk không tự tạo snapshot duy nhất xuyên suốt job.

## 11. Timeout và read-only

Transaction definition có thể đặt timeout và read-only hint. `DataSourceTransactionManager` áp dụng các thuộc tính này lên connection theo khả năng của driver và database.

- Timeout giúp giới hạn thời gian transaction; JDBC operations cần dùng API tích hợp Spring để statement timeout có thể được áp dụng phù hợp.
- Read-only là hint cho database/driver và có thể hỗ trợ tối ưu đọc; không nên coi nó là cơ chế bảo vệ dữ liệu tuyệt đối.
- Transaction timeout của chunk nên phối hợp với timeout của query, HTTP client và SLA tổng thể.

Với writer step, không đánh dấu transaction read-only. Với reader-only tasklet hoặc step chỉ truy vấn, read-only có thể hữu ích nếu database hỗ trợ và cấu hình transaction được áp dụng đúng.

## 12. DataSourceTransactionManager và JobRepository

`JobRepository` lưu metadata như JobInstance, JobExecution, StepExecution, execution context và trạng thái. Trong cấu hình JDBC, repository có một `DataSource` dùng để lưu các bảng metadata.

Transaction manager của chunk step quản lý transaction xử lý dữ liệu nghiệp vụ. Transaction manager mà hạ tầng `JobRepository` sử dụng quản lý các thao tác metadata theo cấu hình repository. Hai vai trò có thể dùng cùng một `DataSourceTransactionManager` nếu metadata và dữ liệu nghiệp vụ cùng datasource, hoặc dùng transaction manager riêng nếu datasource tách biệt.

Ví dụ cấu hình hạ tầng Spring Batch 5 có thể chỉ rõ các bean datasource và transaction manager:

```java
@Configuration
@EnableBatchProcessing(
    dataSourceRef = "batchDataSource",
    transactionManagerRef = "batchTransactionManager"
)
public class BatchInfrastructureConfiguration {
    // JobRepository và các thành phần hạ tầng được cấu hình bởi Spring Batch
}
```

Các thuộc tính annotation và cách cấu hình repository cần khớp phiên bản Spring Batch đang dùng. Nếu ứng dụng tự cấu hình `JobRepository`, hãy chỉ định transaction manager phù hợp cho datasource metadata.

Nếu metadata repository và dữ liệu nghiệp vụ nằm ở hai datasource khác nhau, không giả định một local `DataSourceTransactionManager` có thể commit/rollback cả hai như một transaction nguyên tử. Cần thiết kế consistency, restart và đối soát cho trường hợp một bên commit còn bên kia thất bại.

## 13. Một DataSource hay nhiều DataSource?

`DataSourceTransactionManager` quản lý một `DataSource` tại một thời điểm. Khi một chunk cập nhật hai database độc lập, hai local transaction manager không tự động phối hợp thành một transaction chung.

| Kiến trúc | Cách quản lý |
|---|---|
| Một database cho metadata và nghiệp vụ | Có thể dùng cùng DataSource/transaction manager theo cấu hình phù hợp |
| Hai datasource, một datasource cho mỗi step | Chọn transaction manager của datasource mà step cần quản lý |
| Một chunk ghi hai datasource độc lập | Hai local manager không bảo đảm atomic commit toàn cục |
| Nhiều XA-capable resource cần atomicity | Cân nhắc JTA/XA transaction manager và hạ tầng tương ứng |
| Tích hợp database với file/API/message broker | Thường dùng outbox, staging, idempotency hoặc compensation |

Không nên tạo hai `DataSourceTransactionManager` rồi giả định cả hai cùng rollback khi một writer ném exception. Chỉ transaction manager đang bao step mới trực tiếp quản lý transaction của resource tương ứng; manager khác cần được tham gia theo cơ chế riêng.

## 14. Kết hợp database với file writer

Một batch step có thể vừa ghi database vừa tạo file. Tuy nhiên, transaction JDBC không tự rollback file system. Nếu database rollback sau khi file đã được ghi trực tiếp, file có thể còn nội dung không tương ứng với database.

Cách thiết kế thường an toàn hơn:

1. Ghi file vào tên tạm gắn với JobExecution hoặc batch ID.
2. Hoàn thành các chunk và kiểm tra dữ liệu đầu ra.
3. Sau khi step/job đạt điều kiện thành công, dùng bước publish để đổi tên hoặc di chuyển file vào vị trí chính thức.
4. Nếu job thất bại, giữ file tạm để điều tra hoặc dọn theo chính sách.

`FlatFileItemWriter` có transaction-aware buffering cho chunk trong một số cấu hình, nhưng không biến filesystem và database thành một XA transaction. Hãy kiểm thử hành vi thực tế với transaction manager và filesystem đang dùng.

## 15. DataSourceTransactionManager trong partitioning

Trong partitioned step, mỗi worker `StepExecution` thường chạy trên thread riêng khi local partitioning dùng `TaskExecutor`. Vì transaction context được bind theo thread, mỗi worker có transaction JDBC riêng và connection riêng từ pool.

```text
Manager step
    |
    +--> Worker partition 0 / Thread 1 / JDBC Connection 1
    |
    +--> Worker partition 1 / Thread 2 / JDBC Connection 2
    |
    +--> Worker partition 2 / Thread 3 / JDBC Connection 3
```

Transaction của partition 0 commit độc lập với partition 1 và 2. Nếu partition 2 thất bại, dữ liệu đã commit ở các partition khác không tự rollback.

Connection pool phải đủ cho số worker đồng thời cộng với nhu cầu của JobRepository, web requests và các thành phần khác. Tăng `gridSize` hoặc thread pool mà không kiểm tra pool capacity có thể gây cạn connection, timeout và giảm throughput.

## 16. Multi-threaded step và transaction context

Trong multi-threaded step, việc xử lý item có thể diễn ra trên nhiều thread tùy cấu hình. Transaction resources được quản lý theo thread, không tự chia sẻ một JDBC connection giữa các thread.

Không truyền `Connection` hoặc transaction-bound resource từ thread này sang thread khác. Mỗi thread cần tham gia transaction theo cơ chế được Spring Batch và transaction manager hỗ trợ. Reader/writer cũng phải an toàn khi được truy cập đồng thời.

Nếu nghiệp vụ cần một transaction cho từng nhóm dữ liệu độc lập, partitioning thường giúp mô hình hóa rõ hơn vì mỗi partition có StepExecution và transaction riêng. Dù dùng mô hình nào, cần kiểm tra connection pool, isolation, lock contention và khả năng retry deadlock.

## 17. Cấu hình nhiều transaction manager

Khi ứng dụng có nhiều datasource, nên đặt tên rõ ràng cho từng transaction manager và inject đúng manager vào step/service.

```java
@Bean("ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}

@Bean("auditTransactionManager")
PlatformTransactionManager auditTransactionManager(
        @Qualifier("auditDataSource") DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}
```

Service có thể chỉ định manager:

```java
@Transactional(
    transactionManager = "auditTransactionManager",
    propagation = Propagation.REQUIRES_NEW
)
public void recordAttempt(AuditRecord record) {
    // Ghi audit bằng auditDataSource
}
```

Đây là transaction riêng. Nếu audit commit nhưng transaction nghiệp vụ rollback, audit vẫn tồn tại. Đó có thể là yêu cầu đúng khi muốn lưu lịch sử attempt; nhưng nếu audit biểu thị nghiệp vụ đã hoàn tất, cần thiết kế trạng thái rõ ràng.

Không dùng nhiều transaction manager để tạo atomicity giữa datasource. Nếu cần transaction đa tài nguyên thật sự, cần JTA/XA hoặc một mẫu consistency phù hợp.

## 18. Nested transaction và savepoint

`DataSourceTransactionManager` có thể hỗ trợ nested transaction dựa trên JDBC savepoint khi driver và database hỗ trợ. Nested transaction không phải transaction độc lập có thể commit bền vững trước transaction ngoài.

```text
Outer transaction
   |
   +--> SQL A
   |
   +--> SAVEPOINT
   |       |
   |       +--> SQL B
   |       +--> lỗi -> rollback to savepoint
   |
   +--> SQL C
   |
   +--> COMMIT outer transaction
```

Nếu outer transaction rollback, SQL A và SQL C vẫn rollback dù phần nested đã hoàn tất. Nested/savepoint phù hợp khi muốn hoàn tác một phần thao tác trong transaction lớn, không thay thế `REQUIRES_NEW`.

Khả năng nested phụ thuộc cấu hình `nestedTransactionAllowed`, JDBC driver và database. Hãy kiểm thử với nền tảng thực tế trước khi dựa vào savepoint trong batch job.

## 19. Deadlock, lock timeout và retry

Batch job có thể cạnh tranh lock với ứng dụng online hoặc worker khác. Database có thể phát sinh deadlock hoặc lock timeout; transaction hiện tại thường phải rollback trước khi thử lại.

Có thể cấu hình retry ở fault-tolerant step cho exception tạm thời:

```java
return new StepBuilder("updateOrders", jobRepository)
    .<OrderRow, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(DeadlockLoserDataAccessException.class)
    .retryLimit(3)
    .build();
```

Ví dụ exception cụ thể phụ thuộc lớp exception được driver và Spring dịch ra. Trong ứng dụng hiện đại, có thể gặp các lớp con của `TransientDataAccessException`. Hãy phân loại theo exception thực tế, đặt retry limit và backoff phù hợp, và bảo đảm writer idempotent.

Không retry mọi `DataAccessException`. Lỗi schema, permission, SQL syntax hoặc dữ liệu vi phạm constraint cố định thường không tự hết khi thử lại.

## 20. Transaction timeout và thời gian chunk

Transaction dài giữ connection và lock lâu hơn. Với chunk size lớn hoặc writer gọi dịch vụ chậm trong lúc transaction mở, database có thể chịu contention và pool nhanh cạn.

Thiết kế cần phối hợp:

- Chunk size với số lượng SQL và thời gian xử lý mỗi item.
- Transaction timeout với query timeout và thời gian response của dependency.
- Retry/backoff với tổng deadline của job.
- Connection pool size với số worker đồng thời.
- Lock order giữa các writer để giảm deadlock.

Tránh gọi HTTP hoặc thực hiện tác vụ chậm trong transaction JDBC nếu có thể tách thành giai đoạn chuẩn bị và phát side effect sau commit. Một transaction manager JDBC không quản lý timeout của HTTP client.

## 21. Kiểm thử rollback với DataSourceTransactionManager

Integration test nên xác nhận dữ liệu thực sự rollback trên database, không chỉ xác nhận exception được ném.

Ví dụ kiểm thử service:

```java
@Test
void rollsBackDatabaseChangesWhenRuntimeExceptionOccurs() {
    assertThatThrownBy(() -> transactionTemplate.execute(status -> {
        jdbcTemplate.update(
            "INSERT INTO ORDERS (ORDER_ID, STATUS) VALUES (?, ?)",
            9001L, "NEW");
        throw new IllegalStateException("forced failure");
    })).isInstanceOf(IllegalStateException.class);

    Integer count = jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM ORDERS WHERE ORDER_ID = ?",
        Integer.class, 9001L);

    assertThat(count).isZero();
}
```

Test này giả định `TransactionTemplate` dùng cùng `DataSourceTransactionManager` với `JdbcTemplate`. Kiểm tra database sau khi transaction kết thúc để xác nhận row chưa được commit.

Với Spring Batch step, nên có integration test:

1. Writer ghi một số row rồi ném exception trong cùng chunk.
2. Xác nhận các row của chunk bị rollback.
3. Xác nhận chunk trước đã commit vẫn tồn tại.
4. Kết hợp retry/skip và xác nhận dữ liệu cuối cùng đúng policy.
5. Kiểm tra `ExecutionContext` checkpoint và restart.
6. Kiểm tra hai worker partition có transaction và connection riêng.
7. Kiểm tra `REQUIRES_NEW` có commit độc lập như thiết kế.
8. Kiểm tra datasource thứ hai không bị hiểu nhầm là tự rollback cùng datasource thứ nhất.

## 22. Quan sát transaction trong production

Để điều tra transaction issue, nên theo dõi:

- JobExecution ID và StepExecution ID.
- Job/step name và worker/partition nếu có.
- Database connection pool active/idle/pending count.
- Transaction duration và timeout.
- Deadlock, lock wait và rollback count.
- Retry count theo exception category.
- Chunk read/write/skip count.
- Query duration và lỗi connection.

Không ghi credentials, connection string có password hoặc dữ liệu nhạy cảm vào log. Bật log transaction ở mức debug chỉ trong thời gian điều tra vì có thể tạo lượng log lớn và ảnh hưởng hiệu năng.

## 23. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng `dataSource.getConnection()` trực tiếp trong transaction | Có thể nhận connection ngoài transaction-bound connection | Dùng `JdbcTemplate` hoặc `DataSourceUtils` |
| Truyền nhầm DataSource vào transaction manager | SQL không tham gia transaction mong đợi | Dùng cùng DataSource và qualifier rõ ràng |
| Dùng transaction manager cho một datasource để kỳ vọng rollback datasource khác | Resource thứ hai có thể đã commit độc lập | Dùng JTA/XA hoặc outbox/compensation |
| Tăng chunk size quá lớn | Transaction dài, lock lâu và rollback tốn kém | Chọn chunk size theo workload và database |
| Dùng `REQUIRES_NEW` mà không hiểu hệ quả | Thay đổi con có thể commit dù chunk rollback | Chỉ dùng khi cần transaction độc lập |
| Nhầm skip với noRollback | Item có thể skip nhưng chunk vẫn rollback trong recovery | Phân biệt skip policy và rollback classification |
| Chia sẻ JDBC Connection qua thread | Connection/transaction không an toàn | Mỗi worker dùng transaction riêng theo thread |
| Không tính connection pool cho partitioning | Worker chờ connection hoặc timeout | Giới hạn concurrency và tăng pool hợp lý |
| Retry mọi lỗi database | Lỗi cấu hình/schema bị lặp lại vô ích | Chỉ retry lỗi transient đã phân loại |
| Giả định DB và file commit nguyên tử | File có thể tồn tại khi database rollback | Dùng staging và bước publish |

## 24. Quy trình chọn DataSourceTransactionManager cho batch job

Khi cấu hình job, hãy xác định theo thứ tự:

1. Step đọc/ghi datasource nào?
2. Reader, writer và service có dùng cùng một DataSource không?
3. Mỗi chunk cần một transaction local hay cần phối hợp nhiều resource?
4. JobRepository lưu metadata ở datasource nào và dùng transaction manager nào?
5. JDBC access có đi qua `JdbcTemplate`/`DataSourceUtils` để tham gia transaction không?
6. Isolation, timeout, read-only và rollback rule có phù hợp không?
7. Retry/skip có được cấu hình cho exception transient và data error riêng biệt không?
8. Với partitioning, connection pool có đủ cho concurrency không?
9. Side effect ngoài database có outbox/idempotency/compensation không?
10. Integration test có xác nhận commit, rollback, restart và metadata không?

## Kết luận

`DataSourceTransactionManager` quản lý local JDBC transaction cho một `DataSource`. Nó lấy connection, bind connection với thread hiện tại và điều khiển commit/rollback. `JdbcTemplate` và `DataSourceUtils` dùng lại connection đã bind, nhờ đó các thao tác JDBC trong reader, processor, writer hoặc service có thể tham gia transaction của chunk.

Trong Spring Batch 5, truyền transaction manager vào `.chunk(size, transactionManager)` hoặc `.tasklet(tasklet, transactionManager)` để xác định transaction boundary của step. Chọn đúng datasource, propagation, isolation và timeout; tránh truyền connection qua thread hoặc giả định nhiều datasource/file/API tự rollback cùng nhau. Với partitioning, mỗi worker có transaction riêng và cần connection pool phù hợp. Hãy kiểm thử commit/rollback trên database thật, thiết kế retry cho lỗi transient và dùng outbox/idempotency hoặc compensation cho side effect ngoài transaction.
