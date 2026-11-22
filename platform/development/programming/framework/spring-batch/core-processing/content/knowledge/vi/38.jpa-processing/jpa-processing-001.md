# JpaPagingItemReader

Trong Spring Batch, `JpaPagingItemReader<T>` đọc dữ liệu từ database thông qua JPA và chia kết quả truy vấn thành từng page. Reader thực thi một JPQL query, dùng `setFirstResult` và `setMaxResults` để lấy từng trang, sau đó ánh xạ các kết quả thành item cho chunk step.

Reader này phù hợp khi ứng dụng đã dùng JPA entity model, muốn đọc dữ liệu bằng JPQL hoặc cần trả về DTO từ constructor expression. Nó giúp xử lý tập dữ liệu lớn theo từng phần thay vì nạp toàn bộ kết quả vào một `List`.

Khi dùng `JpaPagingItemReader`, cần phân biệt ba đơn vị thường bị nhầm:

- **Page size:** số kết quả reader yêu cầu trong một lần truy vấn.
- **Chunk size:** số item Spring Batch xử lý trong một transaction chunk trước khi commit.
- **Fetch size của JDBC:** gợi ý cho JDBC driver về số row lấy mỗi đợt từ database; đây không phải page size của JPA reader.

Page query và chunk transaction có lifecycle riêng. Reader cũng quản lý một `EntityManager` và persistence context của nó; các entity có thể bị detach sau khi page được đọc. Vì vậy, việc chọn page size, thứ tự query, transaction strategy và cách xử lý lazy association ảnh hưởng trực tiếp tới hiệu năng, tính nhất quán và khả năng restart.

## JpaPagingItemReader là gì?

`JpaPagingItemReader<T>` thuộc package `org.springframework.batch.item.database`. Nó triển khai reader theo cơ chế paging và dùng `EntityManagerFactory` để tạo `EntityManager` phục vụ query.

Với mỗi page, reader thực hiện quy trình khái quát:

1. Tính vị trí bắt đầu của page hiện tại.
2. Tạo JPQL query.
3. Gán parameter và query hint nếu có.
4. Gọi `setFirstResult(...)` và `setMaxResults(...)`.
5. Thực thi query để lấy page kết quả.
6. Đưa các kết quả vào buffer nội bộ để `read()` trả từng item.
7. Làm sạch persistence context theo lifecycle của reader để tránh giữ quá nhiều entity được quản lý.

```text
Job / Step
    |
    v
JpaPagingItemReader.read()
    |
    +--> Page 0: JPQL + firstResult=0, maxResults=pageSize
    |       |
    |       +--> item 1, item 2, ... item N
    |
    +--> Page 1: JPQL + firstResult=N, maxResults=pageSize
    |       |
    |       +--> item N+1, ... item 2N
    |
    +--> Page 2: ...
    |
    v
Chunk processor / writer
```

Đây là reader theo page, không phải cursor giữ một `ResultSet` duy nhất. Khi chuyển page, reader thực hiện query mới với offset tương ứng.

## Khi nào nên dùng JpaPagingItemReader?

Reader này phù hợp khi:

- Ứng dụng dùng JPA và muốn đọc theo JPQL.
- Dữ liệu được biểu diễn bằng entity hoặc DTO projection.
- Muốn xử lý lần lượt từng page để giới hạn lượng dữ liệu trong memory.
- Cần query có parameter theo `JobParameters` hoặc `ExecutionContext`.
- Dataset có thứ tự ổn định và có thể tiếp tục bằng page/offset khi restart.

Nên cân nhắc reader khác khi:

- Cần một JDBC cursor mở liên tục và database/driver hỗ trợ tốt: xem `JdbcCursorItemReader`.
- Cần paging theo SQL, sort key hoặc database-specific query provider: xem `JdbcPagingItemReader`.
- Dataset thay đổi liên tục và offset pagination không bảo đảm tiếp tục đúng: cân nhắc keyset pagination hoặc snapshot/staging.
- Cần đọc một tập object đã được tải sẵn trong memory: dùng reader phù hợp với collection, nhưng lưu ý giới hạn bộ nhớ.

Không có một reader tối ưu cho mọi database. Hãy chọn theo query plan, provider JPA, JDBC driver, kích thước page và yêu cầu consistency.

## Cấu hình cơ bản

Giả sử ứng dụng có entity:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    private Long id;

    private String fullName;

    private BigDecimal balance;

    private boolean active;

    // Constructor, getter và các mapping khác
}
```

Reader dùng `JpaPagingItemReaderBuilder`:

```java
@Bean
@StepScope
JpaPagingItemReader<Customer> customerReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['activeOnly']}") Boolean activeOnly) {

    return new JpaPagingItemReaderBuilder<Customer>()
            .name("customerReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select c
                    from Customer c
                    where c.active = :active
                    order by c.id
                    """)
            .parameterValues(Map.of("active", activeOnly))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

Các cấu hình quan trọng:

| Cấu hình | Ý nghĩa |
| --- | --- |
| `name` | Tên reader dùng để tạo key state trong `ExecutionContext` |
| `entityManagerFactory` | Factory tạo `EntityManager` |
| `queryString` | JPQL query được thực thi cho từng page |
| `parameterValues` | Map tên parameter tới giá trị cần bind |
| `pageSize` | Số item tối đa reader yêu cầu trong một page |
| `saveState` | Bật/tắt lưu state để hỗ trợ restart |

Ví dụ giả định `activeOnly` luôn có giá trị. Nếu parameter có thể null, `Map.of` không chấp nhận null; hãy tạo map mutable hoặc dùng default rõ ràng. Kiểu dữ liệu parameter phải tương thích với kiểu thuộc tính entity và JPQL provider.

### Khai báo bằng setter thay cho builder

Có thể cấu hình reader theo JavaBean style:

```java
JpaPagingItemReader<Customer> reader = new JpaPagingItemReader<>();
reader.setName("customerReader");
reader.setEntityManagerFactory(entityManagerFactory);
reader.setQueryString("select c from Customer c order by c.id");
reader.setPageSize(500);
reader.setSaveState(true);
reader.afterPropertiesSet();
```

Builder thường dễ đọc hơn và giúp các giá trị cấu hình tập trung tại một nơi. Dù dùng cách nào, reader cần có `EntityManagerFactory`, query hợp lệ, page size phù hợp và tên ổn định nếu cần restart.

## JPQL query và parameter binding

`queryString` của `JpaPagingItemReader` là JPQL, không phải SQL thuần. JPQL làm việc với entity name và thuộc tính entity, không trực tiếp dùng tên bảng/cột như SQL.

Ví dụ SQL:

```sql
SELECT customer_id, full_name
FROM customer
WHERE active = true
ORDER BY customer_id
```

JPQL tương ứng:

```java
select c
from Customer c
where c.active = true
order by c.id
```

`Customer` là entity name; `active` và `id` là thuộc tính Java được mapping. Database provider chuyển JPQL thành SQL phù hợp dialect.

### Named parameter

Nên dùng named parameter để query dễ đọc:

```java
.queryString("""
        select c
        from Customer c
        where c.active = :active
          and c.createdAt < :cutoff
        order by c.id
        """)
.parameterValues(Map.of(
        "active", true,
        "cutoff", cutoff))
```

Tên trong `parameterValues` không cần dấu `:`. Key phải khớp tên parameter trong JPQL.

### Lấy parameter từ JobParameters

Nếu query phụ thuộc ngày nghiệp vụ hoặc trạng thái được truyền khi launch, có thể dùng `@StepScope`:

```java
@Bean
@StepScope
JpaPagingItemReader<Order> orderReader(
        EntityManagerFactory entityManagerFactory,
        @Value("#{jobParameters['businessDate']}") LocalDate businessDate) {

    return new JpaPagingItemReaderBuilder<Order>()
            .name("orderReader")
            .entityManagerFactory(entityManagerFactory)
            .queryString("""
                    select o
                    from Order o
                    where o.businessDate = :businessDate
                    order by o.id
                    """)
            .parameterValues(Map.of("businessDate", businessDate))
            .pageSize(300)
            .build();
}
```

`@StepScope` trì hoãn việc tạo target reader cho tới khi có `StepExecution`, vì vậy có thể resolve job parameter đúng lần chạy. Nếu giá trị là `String`, hãy parse và validate trước khi đưa vào query.

### Parameter không phải là tên cột động

JPA parameter binding dùng cho giá trị, không dùng để thay tên entity, tên thuộc tính hoặc từ khóa `ORDER BY`.

Không viết:

```java
where c.:fieldName = :value
```

Nếu cần chọn sort field động, dùng allowlist trong code để ghép một trong các biểu thức JPQL đã biết. Không nối trực tiếp input không tin cậy vào query string vì có thể tạo query injection hoặc query sai.

## DTO projection thay vì đọc entity

`JpaPagingItemReader<T>` không bắt buộc `T` phải là entity. JPQL có thể dùng constructor expression để trả về DTO:

```java
public record CustomerSummary(
        Long id,
        String fullName,
        BigDecimal balance) {
}
```

Query:

```java
.queryString("""
        select new com.example.batch.CustomerSummary(
            c.id, c.fullName, c.balance)
        from Customer c
        where c.active = true
        order by c.id
        """)
```

Khi dùng DTO projection, reader trả object dữ liệu đã được chọn thay vì entity được quản lý. Điều này hữu ích khi processor chỉ cần một số field, không cần lazy relationship hoặc không có nhu cầu cập nhật entity.

Tên class trong constructor expression thường phải là fully qualified class name. Constructor phải khớp số lượng và kiểu argument theo query/provider.

### Khi nào chọn entity, khi nào chọn DTO?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Processor cần domain entity và relationship đã được fetch có chủ đích | Entity |
| Chỉ cần vài cột để tính toán/ghi sang hệ thống khác | DTO projection |
| Muốn giảm persistence context và tránh lazy loading ngoài scope | DTO projection |
| Cần gọi domain method trên entity | Entity, nhưng quản lý trạng thái detached rõ ràng |
| Chỉ cần báo cáo/summary | DTO projection thường phù hợp |

DTO projection không tự giải quyết query chậm; vẫn cần index, query plan và page size phù hợp.

## Page size và chunk size

Page size và chunk size có mục đích khác nhau. Page size điều khiển lượng kết quả mà JPA reader lấy trong một query; chunk size điều khiển số item xử lý trong một transaction chunk.

Ví dụ:

```java
.pageSize(500)
```

và:

```java
.chunk(100, transactionManager)
```

Reader có thể tải 500 kết quả của page vào buffer, trong khi step xử lý và commit sau mỗi 100 item. Một page có thể phục vụ nhiều chunk; một chunk cũng có thể vượt qua ranh giới giữa hai page.

| Page size | Chunk size | Hệ quả có thể gặp |
| ---: | ---: | --- |
| 100 | 100 | Mỗi page thường tương ứng một chunk nếu không có filter và EOF |
| 500 | 100 | Một page có thể cung cấp cho khoảng 5 chunk |
| 100 | 250 | Một chunk có thể lấy item từ nhiều page |
| 1000 | 50 | Reader có thể giữ buffer lớn hơn so với số item mỗi transaction |

Không bắt buộc page size bằng chunk size. Chọn page size theo chi phí query, memory và hành vi provider; chọn chunk size theo transaction duration, writer và yêu cầu commit/rollback.

### Page size quá nhỏ

Page nhỏ làm reader thực hiện nhiều query hơn. Nếu database có latency cao, chi phí round trip và query setup có thể đáng kể. Tuy nhiên, page nhỏ cũng giới hạn số object được giữ trong buffer và có thể giúp giảm memory.

### Page size quá lớn

Page lớn giảm số query nhưng tăng số object được tải trong một lần. Nó có thể làm tăng heap usage, thời gian tạo page và lượng dữ liệu phải xử lý lại nếu page query gặp lỗi.

### Cách chọn page size

Bắt đầu bằng một giá trị vừa phải, ví dụ 100–500, rồi đo trên dữ liệu thực tế. Theo dõi:

- Thời gian mỗi page query.
- Số query cho toàn bộ job.
- Heap usage và garbage collection.
- Thời gian chunk transaction.
- Throughput của processor/writer.
- Số row thực tế trả về mỗi page.

Không tăng page size để cố làm giảm số transaction. Page size không thay đổi chunk commit boundary.

## Persistence context và EntityManager lifecycle

JPA `EntityManager` quản lý persistence context, nơi các entity được load có thể ở trạng thái managed. Nếu giữ quá nhiều entity trong một persistence context lâu dài, bộ nhớ và dirty checking overhead có thể tăng.

`JpaPagingItemReader` quản lý `EntityManager` trong lifecycle `open`/`close`. Reader làm sạch persistence context theo page để tránh giữ toàn bộ entity đã đọc trong first-level cache. Vì vậy, entity được trả ra có thể trở thành detached sau khi page được đọc/clear.

Điều này có hệ quả quan trọng:

- Không giả định entity từ reader vẫn managed khi processor hoặc writer sử dụng.
- Thay đổi field trên detached entity không tự động được flush xuống database.
- Lazy association chưa được load có thể không truy cập được sau khi entity detach.
- Nếu cần update, dùng writer/service với transaction và merge/update có chủ đích hoặc đọc dữ liệu cần thiết trước khi detach.
- DTO projection tránh được nhiều vấn đề liên quan tới managed/detached entity.

### Entity state

| Trạng thái | Ý nghĩa |
| --- | --- |
| New / transient | Object chưa được persist và chưa có persistence context quản lý |
| Managed | Entity đang được `EntityManager` quản lý; thay đổi có thể được dirty checking |
| Detached | Entity từng được quản lý nhưng hiện không còn gắn với persistence context |
| Removed | Entity được đánh dấu xóa trong persistence context |

Sau khi persistence context bị clear, entity đã load trở thành detached. Nếu processor sửa entity rồi mong JPA tự ghi lại chỉ vì entity từng được đọc bằng JPA reader, điều đó không đúng.

### Cập nhật entity detached

Nếu cần cập nhật entity, một cách là dùng `JpaItemWriter` hoặc service trong transaction để merge entity. Tuy nhiên, merge có semantics copy state từ object detached sang managed instance; cần tránh ghi đè field không được load hoặc field đã thay đổi bởi transaction khác.

Một cách khác là DTO projection chỉ mang ID và dữ liệu cần thiết, rồi writer/service thực hiện câu update rõ ràng. Với batch update lớn, `JdbcBatchItemWriter` hoặc JPQL bulk update có thể phù hợp hơn.

## Lazy loading và relationship

Entity có thể có association `LAZY`, ví dụ:

```java
@ManyToOne(fetch = FetchType.LAZY)
private Department department;
```

Nếu reader clear persistence context sau page, entity được trả có thể detached trong khi association chưa được load. Processor gọi `customer.getDepartment().getName()` có thể gặp `LazyInitializationException` tùy provider/proxy và thời điểm truy cập.

Các cách xử lý:

- Dùng DTO projection lấy các field cần thiết ngay trong query.
- Dùng `JOIN FETCH` cho association to-one hoặc association phù hợp.
- Dùng query hint/entity graph theo JPA provider/API đang dùng.
- Đọc association trong cùng phạm vi persistence context nếu thiết kế reader cho phép, nhưng không dựa vào một persistence context kéo dài ngoài lifecycle reader.
- Tách query lấy relationship cần thiết theo batch để tránh N+1.

Không fetch join collection một cách tùy tiện trong query paging. Join collection làm một entity root xuất hiện nhiều row SQL; kết hợp với pagination có thể khiến provider phải áp dụng pagination trong memory, trả số root không như mong đợi hoặc phát sinh cảnh báo. Với collection lớn, cân nhắc query page ID của root trước rồi load child data bằng query riêng hoặc DTO projection.

### N+1 query

Nếu mỗi item truy cập một lazy relationship, provider có thể chạy thêm một query cho từng item. Với 10.000 customer, một query page cộng hàng nghìn query phụ có thể làm job rất chậm.

Để phát hiện:

- Bật SQL logging ở môi trường test.
- Dùng Hibernate statistics hoặc datasource metrics.
- Đo số query theo page và theo item.
- Kiểm tra execution plan của query chính và query phụ.

Để giảm N+1, dùng DTO projection, fetch join phù hợp, entity graph hoặc batch fetching theo provider. Chọn giải pháp dựa trên cardinality và query plan, không bật fetch join mọi association.

## EntityManager transaction và chunk transaction

`JpaPagingItemReader` có tùy chọn `transacted`. Trong các phiên bản phổ biến, mặc định là `true`: reader thực hiện truy vấn mỗi page trong transaction JPA do reader quản lý, độc lập với transaction do Spring Batch dùng cho chunk. Sau khi lấy page, persistence context được làm sạch theo lifecycle reader.

Điều này có nghĩa page query không tự động nằm trong cùng một transaction với writer của chunk. Ví dụ:

```text
Step
 |
 +--> Reader page transaction
 |       SELECT page 1
 |       COMMIT page read
 |
 +--> Chunk transaction 1
 |       process items 1..100
 |       writer
 |       COMMIT
 |
 +--> Chunk transaction 2
 |       process items 101..200
 |       writer
 |       COMMIT
 |
 +--> Reader page transaction
         SELECT page 2
         COMMIT page read
```

Sơ đồ mô tả ranh giới logic; thứ tự chính xác reader prefetch page so với các chunk phụ thuộc buffer/page size. Điểm cốt lõi là page query transaction và chunk transaction là hai cơ chế khác nhau.

### Tùy chọn transacted

`transacted` kiểm soát việc reader dùng transaction riêng cho thao tác đọc page theo API của `JpaPagingItemReader`. Chỉ thay đổi tùy chọn này khi hiểu rõ persistence provider, transaction manager và cách `EntityManager` được quản lý. Tắt nó không tự động bảo đảm query tham gia transaction chunk; điều đó phụ thuộc cấu hình JPA và cách entity manager được chia sẻ.

Nếu cần consistency giữa query đọc và các cập nhật của chunk, phải thiết kế transaction strategy ở cấp database/JPA và kiểm thử trên provider thực tế. Không suy ra rằng cùng một `EntityManagerFactory` đồng nghĩa cùng một `EntityManager` hoặc cùng một transaction.

### Transaction manager cho step

Chunk step thường dùng `JpaTransactionManager` khi business writer dùng JPA cùng persistence unit, hoặc transaction manager phù hợp với datasource/JPA configuration. Ví dụ:

```java
@Bean
JpaTransactionManager transactionManager(EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
```

Step:

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JpaPagingItemReader<Customer> customerReader,
        ItemProcessor<Customer, CustomerSummary> processor,
        ItemWriter<CustomerSummary> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<Customer, CustomerSummary>chunk(200, transactionManager)
            .reader(customerReader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

Nếu `JobRepository` và business data dùng các datasource/transaction manager khác nhau, cần hiểu transaction metadata và business output có thể không atomic. Một local transaction manager không tự tạo distributed transaction cho nhiều resource.

## Isolation và dữ liệu thay đổi giữa các page

Vì reader thực hiện query theo từng page, page 0 và page 1 có thể được truy vấn tại các thời điểm khác nhau. Nếu transaction của reader kết thúc sau mỗi page, một transaction khác có thể thay đổi dữ liệu giữa hai query.

Ví dụ:

```text
Page 0: SELECT ... ORDER BY id LIMIT/OFFSET -> rows 1..100
Transaction khác INSERT một row có id nằm trước vị trí offset tiếp theo
Page 1: SELECT ... OFFSET 100 -> có thể dịch vị trí so với lần query trước
```

Với offset pagination, insert/delete trước offset có thể làm một row bị đọc lặp hoặc bị bỏ qua. Update một cột dùng trong `WHERE` hoặc `ORDER BY` cũng có thể làm row chuyển vị trí hoặc rời khỏi tập kết quả.

Đây không phải lỗi riêng của Spring Batch; đó là đặc tính của offset-based pagination trên một dataset thay đổi. Nếu job cần một tập input nhất quán, hãy xác định snapshot hoặc watermark rõ ràng.

### Cách giữ tập input ổn định

Một số cách phổ biến:

- Chọn cutoff bất biến khi launch, ví dụ `createdAt < :cutoff`.
- Lọc theo `batchId`/`processingGroupId` đã được gán trước khi job chạy.
- Tạo staging table chứa khóa của tập record cần xử lý.
- Dùng snapshot isolation nếu database hỗ trợ và thời lượng transaction phù hợp.
- Giữ nguồn dữ liệu immutable trong suốt execution/restart.

Cutoff thời gian chỉ hữu ích nếu dữ liệu cũ không bị sửa/xóa theo cách làm thay đổi tập kết quả. Nếu cần snapshot mạnh hơn, dùng staging hoặc cơ chế database snapshot phù hợp.

## ORDER BY và tính xác định của pagination

Query paging phải có `ORDER BY` ổn định. Không dựa vào thứ tự mặc định của database.

Ví dụ chưa đủ ổn định:

```jpql
select o from Order o
where o.status = :status
order by o.createdAt
```

Nếu nhiều order có cùng `createdAt`, database có thể trả chúng theo thứ tự khác nhau giữa các lần query. Thêm tie-breaker duy nhất:

```jpql
select o from Order o
where o.status = :status
order by o.createdAt, o.id
```

`id` làm thứ tự toàn phần nếu nó là khóa duy nhất. Khi restart, cùng offset sẽ trỏ tới cùng vị trí logic chỉ khi dataset và thứ tự kết quả không thay đổi.

`ORDER BY` bảo đảm thứ tự, nhưng không tự đóng băng dataset. Cần kết hợp với cutoff, batch ID hoặc snapshot nếu dữ liệu có thể thay đổi.

## Offset pagination và hiệu năng

JPA paging thường dùng `setFirstResult(offset)` và `setMaxResults(pageSize)`. Ở page sâu, database có thể phải bỏ qua nhiều row trước khi trả page cần thiết. Chi phí có thể tăng khi offset lớn, tùy query plan, index và database.

Ví dụ page size 500:

| Page | First result (offset) | Max results |
| ---: | ---: | ---: |
| 0 | 0 | 500 |
| 1 | 500 | 500 |
| 2 | 1000 | 500 |
| 100 | 50000 | 500 |

Với dataset rất lớn, page 100 có thể tốn hơn page đầu vì database cần xử lý/skip nhiều row. Cần đo query plan thay vì giả định mỗi page có cùng chi phí.

### Keyset pagination

Keyset pagination tiếp tục từ giá trị khóa cuối cùng của page trước thay vì offset:

```jpql
select o from Order o
where o.id > :lastSeenId
order by o.id
```

Đây là ví dụ khái niệm. Với sort key phức hợp như `(createdAt, id)`, điều kiện tiếp tục phải so sánh cả hai phần theo đúng thứ tự. `JpaPagingItemReader` chuẩn dùng page/offset; nếu cần keyset pagination, có thể dùng custom `ItemReader`, query provider hoặc reader chuyên biệt được thiết kế để lưu last-seen key trong `ExecutionContext`.

Keyset có thể hiệu quả hơn cho tập rất lớn và ít bị dịch offset khi có insert trước vị trí hiện tại, nhưng vẫn cần xác định semantics khi row bị update/delete hoặc sort key thay đổi.

## Restart và ExecutionContext

`JpaPagingItemReader` là `ItemStream` và có thể lưu state để hỗ trợ restart. Khi `saveState(true)`, reader ghi tiến độ đọc vào `ExecutionContext` theo tên reader. Khi restart, nó khôi phục vị trí item/page và tiếp tục query từ offset tương ứng.

Để restart đáng tin cậy, cần giữ ổn định:

- `name` của reader.
- JPQL query và parameter values.
- `pageSize` và cách mapping item.
- Thứ tự `ORDER BY`.
- Tập dữ liệu mà query trả về.
- Identifying `JobParameters` dùng cho cùng `JobInstance`.

Nếu thay query, filter, page size hoặc dataset giữa lần chạy đầu và restart, checkpoint cũ có thể không còn trỏ tới item đúng.

### Ví dụ restart

Giả sử page size 500 và step đã commit 1.200 item trước khi thất bại. Khi restart, reader cần khôi phục tiến độ tương ứng với 1.200 item và đọc tiếp từ vị trí kế tiếp theo state đã lưu. Reader có thể phải đọc lại page chứa checkpoint và bỏ qua các item đã xử lý trong page đó theo implementation; không nên tự tính offset hoặc sửa `ExecutionContext` bằng tay.

Nếu có transaction rollback trong chunk cuối, checkpoint chỉ nên phản ánh tiến độ được commit. Spring Batch phối hợp reader state và chunk commit theo `ItemStream` contract. Không ghi checkpoint thủ công từ processor/writer.

### Dataset thay đổi giữa restart

Offset pagination đặc biệt nhạy với insert/delete/update trong tập kết quả. Nếu lần đầu query trả 10.000 row và restart query trả 10.001 row do có record mới trước offset, vị trí tiếp tục có thể lệch. Có thể dẫn tới duplicate hoặc missing item.

Giải pháp là cố định tập input bằng batch ID, cutoff, staging hoặc snapshot; giữ nguyên parameter và query semantics qua restart. Không dùng thời gian hiện tại trực tiếp trong JPQL nếu restart phải xử lý cùng một tập dữ liệu.

### saveState false

Tắt `saveState` khi reader được dùng trong tình huống không cần restart hoặc khi cơ chế chạy song song không hỗ trợ state chia sẻ theo cách mong muốn. Khi tắt, không kỳ vọng reader tự khôi phục vị trí sau failure.

Nếu step chạy nhiều thread hoặc reader được chia sẻ giữa worker, cần xem xét thread-safety và state semantics. Thường nên tạo reader riêng theo partition/step execution thay vì chia sẻ một reader mutable. Chỉ dùng `saveState(false)` khi chấp nhận không restart reader hoặc có cơ chế checkpoint khác.

## EntityGraph, fetch join và N+1

Một query paging có thể load entity root nhưng không load association. Nếu processor truy cập association lazy, provider có thể chạy thêm query cho mỗi item.

Ví dụ query root:

```jpql
select o from Order o
where o.status = :status
order by o.id
```

Processor đọc `o.customer.name` có thể tạo N+1 query nếu customer chưa được fetch. Có thể dùng entity graph hoặc fetch join to-one association nếu phù hợp.

Ví dụ JPQL:

```jpql
select o from Order o
join fetch o.customer
where o.status = :status
order by o.id
```

Fetch join giúp lấy customer cùng query. Tuy nhiên, không nên fetch join collection trong một query paging thông thường vì join làm nhân bản row root và có thể khiến pagination sai hoặc được provider thực hiện trong memory.

Nếu cần collection:

- Page ID của root entity trước.
- Query các child theo danh sách ID của page.
- Gom child vào DTO/map để processor sử dụng.
- Hoặc dùng batch fetching/entity graph có kiểm soát theo provider.

Không dùng `distinct` như một giải pháp tự động cho mọi collection pagination issue; hãy kiểm tra SQL được sinh ra và số root entity thực tế.

## Query hints

JPA query có thể nhận hints qua `hintValues` của reader. Hint phụ thuộc JPA provider hoặc database; một số hint có thể tác động cache, timeout, fetch plan hoặc read-only behavior.

Ví dụ khái niệm:

```java
.hintValues(Map.of(
        "jakarta.persistence.query.timeout", 30000))
```

Tên hint và đơn vị timeout cần khớp JPA version/provider. Các ứng dụng dùng `javax.persistence` API cũ có thể cần tên hint tương ứng của version đó. Không sao chép hint Hibernate/EclipseLink sang provider khác mà không kiểm tra.

Query hint không thay thế index hoặc tối ưu JPQL. Chỉ thêm hint sau khi hiểu tác động và đo được lợi ích.

## Entity lifecycle và ghi dữ liệu

Một entity được reader trả ra có thể đã detached sau khi page được đọc và persistence context được clear. Vì vậy, processor có thể tính toán dựa trên các field đã load nhưng không nên giả định dirty checking tự lưu thay đổi.

Ví dụ processor sửa entity:

```java
@Bean
ItemProcessor<Customer, Customer> markReviewedProcessor() {
    return customer -> {
        customer.setReviewed(true);
        return customer;
    };
}
```

Thay đổi `reviewed` trên detached entity không tự động được ghi chỉ vì object từng đến từ `JpaPagingItemReader`. Writer cần persist/merge/update trong transaction phù hợp.

Nếu dùng `JpaItemWriter`, cấu hình writer để merge entity khi cần cập nhật detached instance theo semantics của writer/provider. Nếu chỉ cần update một vài cột, có thể dùng JDBC writer hoặc query update tường minh để tránh merge toàn bộ graph.

Bulk JPQL update có thể bỏ qua persistence context và không tự đồng bộ các entity đã load. Nếu dùng bulk update, cần hiểu cache/clear semantics và tránh để entity cũ ghi đè dữ liệu mới.

## Transaction khi đọc và ghi cùng dữ liệu

Một pattern phổ biến là đọc entity theo page, xử lý rồi ghi bằng JPA/JDBC. Cần xác định transaction manager nào quản lý writer và transaction nào quản lý page query.

Ví dụ:

```text
JpaPagingItemReader
   |
   +--> page query transaction (reader)
   |
   v
Chunk transaction (Spring Batch)
   |
   +--> processor
   +--> JpaItemWriter / JdbcBatchItemWriter
   +--> commit hoặc rollback
```

Nếu reader query và writer update cùng bảng, một page query có thể được thực hiện trước khi các chunk của page được commit. Các thay đổi từ transaction khác có thể ảnh hưởng page tiếp theo. Nếu writer thay đổi cột filter của reader, dataset có thể dịch chuyển và restart trở nên không an toàn.

Để tránh xử lý cùng một row nhiều lần hoặc bỏ sót row, có thể:

- Claim tập row bằng `batch_id` hoặc trạng thái xử lý trong bước riêng.
- Đọc từ staging table bất biến.
- Dùng cutoff/snapshot phù hợp.
- Không thay đổi sort key/filter key của nguồn trong khi reader đang paging.
- Ghi kết quả sang bảng đích riêng rồi finalize trạng thái sau khi hoàn tất.

Transaction chunk bảo đảm các thay đổi tham gia transaction của nó được commit/rollback cùng nhau. Nó không tự đóng băng tập kết quả của nhiều page query.

## So sánh JpaPagingItemReader, JdbcPagingItemReader và JdbcCursorItemReader

| Tiêu chí | `JpaPagingItemReader` | `JdbcPagingItemReader` | `JdbcCursorItemReader` |
| --- | --- | --- | --- |
| Query | JPQL | SQL qua query provider | SQL với cursor/result set |
| Mapping | JPA entity hoặc DTO projection | `RowMapper` | `RowMapper` |
| Cách đọc | Page bằng first result/max results | Page theo sort key/query provider | Một cursor mở trong lifecycle reader |
| Phụ thuộc | JPA provider và `EntityManagerFactory` | JDBC driver, database dialect/query provider | JDBC driver và cursor semantics |
| Persistence context | Có, được reader quản lý | Không | Không |
| Lazy association | Có thể là concern | Không có JPA lazy proxy | Không có JPA lazy proxy |
| Restart | State page/item và query ổn định | State page/sort key | State vị trí cursor và query ổn định |
| Phù hợp | Ứng dụng domain JPA/JPQL | SQL paging, key sort rõ ràng | Đọc tuần tự qua cursor |

Chọn `JpaPagingItemReader` khi JPA mapping mang lại giá trị thực. Nếu chỉ đọc vài cột và ghi bằng JDBC, `JdbcPagingItemReader` có thể đơn giản và ít overhead hơn. Nếu driver stream cursor tốt và query result ổn định, cursor reader có thể phù hợp. Hãy benchmark với database thật.

## Reader scope và thread safety

Reader giữ page state, `EntityManager` và vị trí hiện tại. Không chia sẻ cùng một instance giữa nhiều step execution hoặc partition chạy đồng thời.

Khi query phụ thuộc `JobParameters` hoặc `ExecutionContext`, khai báo `@StepScope` để reader được tạo theo step execution. Với partitioning, mỗi worker nên có reader instance riêng và parameter/resource riêng.

Nếu dùng multi-threaded step, phải kiểm tra contract thread-safety của reader ở version Spring Batch đang dùng. Việc đặt `saveState(false)` có thể cần thiết trong một số mô hình đa luồng nhưng đồng nghĩa reader không có checkpoint restart chuẩn. Không dùng nó như cách chữa mọi race condition; ưu tiên partitioning với reader độc lập khi có thể.

Không lưu `EntityManager`, query hoặc entity proxy trong static field hay singleton service. Để Spring Batch quản lý reader lifecycle và persistence context.

## Lỗi thường gặp

### Không có ORDER BY

Database không cam kết thứ tự kết quả nếu query không sắp xếp. Page boundary có thể thay đổi giữa lần chạy và restart. Dùng `ORDER BY` trên khóa duy nhất hoặc tổ hợp khóa duy nhất.

### ORDER BY không duy nhất

Nhiều row có cùng sort value có thể đổi thứ tự. Thêm primary key làm tie-breaker.

### Dataset thay đổi giữa các page

Insert/delete/update trước offset có thể gây duplicate hoặc missing item. Dùng batch ID, cutoff, staging hoặc snapshot.

### Nhầm page size với chunk size

Page size điều khiển query; chunk size điều khiển transaction. Chọn độc lập.

### Giữ entity managed quá lâu

Persistence context lớn làm tăng memory/dirty checking. Reader quản lý clear theo page; cân nhắc DTO projection nếu chỉ cần dữ liệu đọc.

### Sửa detached entity và mong dirty checking tự lưu

Entity có thể detached sau page. Dùng writer/merge/update rõ ràng trong transaction.

### Truy cập lazy association sau khi detach

Có thể gây `LazyInitializationException` hoặc query ngoài ý muốn. Fetch dữ liệu cần thiết hoặc dùng DTO projection.

### Fetch join collection với pagination

Join collection có thể nhân bản root row và làm pagination sai/đắt. Page root ID trước rồi tải collection riêng.

### N+1 query

Processor truy cập lazy association từng item làm phát sinh nhiều query. Đo SQL và dùng projection/fetch plan phù hợp.

### Thay query/page size giữa restart

Checkpoint cũ có thể trỏ tới vị trí khác. Giữ query, parameter, page size và reader name ổn định.

### Nghĩ chunk transaction bao trùm page query

Reader có transaction strategy riêng cho page. Không giả định SELECT và writer commit cùng transaction.

### Dùng một reader cho nhiều thread

EntityManager và page state là mutable. Tạo reader riêng theo step/partition và kiểm tra thread-safety.

### Dùng JPQL parameter để thay tên field

Parameter chỉ bind value. Sort field hoặc entity name động cần allowlist và query construction có kiểm soát.

## Kiểm thử JpaPagingItemReader

Nên có unit test cho query/mapping ở mức phù hợp và integration test với JPA provider/database thực tế. H2 có thể hữu ích cho test nhanh nhưng không luôn tái hiện pagination, isolation và SQL dialect của production.

### Kiểm thử đọc theo page

Tạo fixture lớn hơn một page, ví dụ 12 customer với page size 5. Mở reader và xác nhận:

- Reader trả đủ 12 item.
- Item theo thứ tự `ORDER BY`.
- Page cuối có ít hơn page size.
- `read()` trả `null` sau item cuối.
- Không item nào bị lặp hoặc bỏ sót trong lần chạy bình thường.

### Kiểm thử parameter binding

Launch reader với nhiều giá trị `JobParameters` khác nhau và xác nhận query chỉ trả đúng subset. Kiểm tra null/default và kiểu dữ liệu date/time. Không ghép parameter vào query string bằng concatenation.

### Kiểm thử DTO projection

Xác nhận constructor expression tạo đúng DTO, precision của `BigDecimal` được giữ và không phát sinh query lazy không mong muốn.

### Kiểm thử page size và chunk size

Chạy với page size nhỏ hơn, bằng và lớn hơn chunk size. Xác nhận tổng item và số lần commit theo chunk vẫn đúng; page query không bị nhầm thành transaction boundary.

### Kiểm thử persistence context

Sau khi đọc page, xác nhận entity detached theo lifecycle reader/provider. Nếu processor cần association, kiểm tra association đã được fetch trước khi clear hoặc dùng DTO projection.

### Kiểm thử restart

Cho step đọc và commit một số chunk rồi fail. Restart cùng identifying parameters, query, page size và reader name. Xác nhận không missing/duplicate item khi dataset không đổi.

Sau đó thay đổi fixture giữa lần chạy và restart bằng cách insert/delete row trước offset. Test nên chứng minh vì sao dataset phải được cố định hoặc job phải từ chối restart khi manifest/version thay đổi.

### Kiểm thử concurrent modification

Trong transaction khác, thêm/xóa/cập nhật row nằm trước page offset tiếp theo. Quan sát kết quả trên database production-like. Kiểm tra giải pháp cutoff/staging có ngăn được thay đổi làm dịch page hay không.

### Kiểm thử fetch plan và N+1

Bật SQL statistics/log ở môi trường test. Đo số query khi processor truy cập association; xác nhận fetch join/entity graph/projection thực sự giảm query mà không phá pagination.

### Kiểm thử transaction rollback

Làm writer ném exception trong một chunk và xác nhận các thay đổi của chunk rollback theo transaction manager. Kiểm tra reader restart/checkpoint tiếp tục đúng sau khi job restart; không giả định rollback writer làm query page tự chạy lại trong cùng transaction.

## Nguyên tắc thiết kế

Khi dùng `JpaPagingItemReader`, hãy xác định:

1. Dữ liệu nên được đọc dưới dạng entity hay DTO projection?
2. JPQL query có bind parameter bằng named parameter không?
3. Query có `ORDER BY` ổn định trên khóa duy nhất không?
4. Tập dữ liệu có thể thay đổi giữa các page hoặc giữa restart không?
5. Có cần cutoff, batch ID, staging hoặc snapshot để cố định input không?
6. Page size có phù hợp memory, query latency và số round trip không?
7. Chunk size có phù hợp transaction duration và writer không?
8. Entity có bị detach sau page và processor có truy cập lazy association không?
9. Có N+1 query hoặc fetch join collection gây pagination bất thường không?
10. Transaction page query có được hiểu đúng so với chunk transaction không?
11. Reader name, query, parameter và page size có ổn định khi restart không?
12. Reader instance có được cô lập theo step/partition và an toàn với concurrency không?
13. Test đã bao gồm paging, mapping, restart, concurrent update, transaction và query count chưa?

Với một pipeline JPA thông thường, bắt đầu bằng `JpaPagingItemReaderBuilder`, JPQL có named parameter, `ORDER BY` trên khóa duy nhất, page size vừa phải và `saveState(true)`. Dùng DTO projection nếu chỉ cần một phần dữ liệu; nếu dùng entity, hiểu rằng persistence context được clear và entity có thể detached sau page. Xem page query transaction tách biệt với chunk transaction theo cấu hình reader. Cố định dataset bằng cutoff hoặc staging để offset pagination không bị dịch giữa các page/restart, rồi kiểm thử trên đúng JPA provider và database production.

## Ghi nhớ

`JpaPagingItemReader<T>` dùng `EntityManagerFactory` và JPQL để đọc kết quả theo page bằng `setFirstResult`/`setMaxResults`. Page size điều khiển lượng kết quả mỗi query; chunk size điều khiển transaction commit của step. Reader quản lý `EntityManager` và persistence context, làm sạch context theo page nên entity trả về có thể detached; DTO projection giúp tránh lazy loading và dirty-checking không cần thiết. Trong cấu hình phổ biến, page query có transaction reader riêng (`transacted=true`), không mặc nhiên cùng transaction với writer của chunk. Dùng named parameter, `ORDER BY` có khóa duy nhất, giữ query/dataset ổn định qua restart và bật `saveState`. Offset pagination dễ bị duplicate/missing khi dữ liệu thay đổi giữa các page; dùng cutoff, batch ID, staging/snapshot hoặc keyset reader nếu cần. Chọn page size theo memory/query cost, tránh collection fetch join, theo dõi N+1 và kiểm thử restart, isolation, rollback trên JPA provider/database thực tế.
