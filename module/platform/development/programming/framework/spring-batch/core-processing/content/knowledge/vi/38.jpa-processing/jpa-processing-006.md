# JpaItemWriter

`JpaItemWriter<T>` là writer của Spring Batch dùng Java Persistence API (JPA) để ghi một chunk entity vào database thông qua `EntityManager`. Nó nhận các entity từ processor hoặc reader, thực hiện thao tác persist/merge trong transaction của step và flush thay đổi xuống persistence provider.

`JpaItemWriter` phù hợp khi ứng dụng đã dùng JPA/Hibernate và muốn batch step ghi entity theo cùng mô hình mapping với phần còn lại của ứng dụng. Để dùng an toàn, cần hiểu entity đang ở trạng thái transient, managed hay detached; chọn `persist` hay `merge`; cấu hình đúng `EntityManagerFactory` và transaction manager; đồng thời thiết kế cascade, flush, rollback và restart theo ranh giới chunk.

## 1. JpaItemWriter nằm ở đâu trong chunk processing?

Trong chunk-oriented step, reader lấy input, processor chuyển input thành entity và writer ghi nhóm entity. `JpaItemWriter` nhận một `Chunk` và thực hiện thao tác JPA cho từng item.

```text
Input source
    |
    v
ItemReader<OrderInput>
    |
    v
ItemProcessor<OrderInput, OrderEntity>
    |
    v
Chunk<OrderEntity>
    |
    v
JpaItemWriter<OrderEntity>
    |
    +--> EntityManager.persist(...) hoặc merge(...)
    |
    +--> flush persistence context
    |
    v
JPA provider / JDBC
    |
    v
Database
    |
    v
Chunk transaction commit
```

Writer không tự quyết định toàn bộ transaction boundary của step. Spring Batch mở transaction cho chunk; `JpaItemWriter` thực hiện thao tác JPA trong transaction đó. Khi chunk commit, database commit các thay đổi; nếu transaction rollback, các thay đổi chưa commit của chunk được hoàn tác.

## 2. Cấu hình JpaItemWriter trong Spring Batch 5

`JpaItemWriterBuilder<T>` giúp cấu hình writer với `EntityManagerFactory` và các tùy chọn persist/merge.

```java
@Bean
JpaItemWriter<OrderEntity> orderJpaWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<OrderEntity>()
        .entityManagerFactory(entityManagerFactory)
        .build();
}
```

Ví dụ trên dùng hành vi mặc định của writer là merge entity. `EntityManagerFactory` phải là factory tương ứng với persistence unit và database mà step cần ghi.

Khi dùng Spring Boot với Spring Data JPA, `EntityManagerFactory` thường đã được cấu hình tự động. Không cần tự tạo `EntityManager` cho từng item hoặc inject một `EntityManager` mutable vào writer; hãy để writer sử dụng factory và transaction hiện tại.

## 3. Cấu hình JpaTransactionManager cho step

JPA cần transaction manager phù hợp với `EntityManagerFactory`. Trong ứng dụng Spring thuần, có thể khai báo `JpaTransactionManager` như sau:

```java
@Bean
PlatformTransactionManager jpaTransactionManager(
        EntityManagerFactory entityManagerFactory) {
    return new JpaTransactionManager(entityManagerFactory);
}
```

Truyền transaction manager vào chunk builder:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager jpaTransactionManager,
        ItemReader<OrderInput> orderReader,
        ItemProcessor<OrderInput, OrderEntity> orderProcessor,
        JpaItemWriter<OrderEntity> orderJpaWriter) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderInput, OrderEntity>chunk(100, jpaTransactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderJpaWriter)
        .build();
}
```

Trong Spring Boot, ứng dụng có thể đã có một `JpaTransactionManager` được auto-configure. Nếu có nhiều persistence unit hoặc nhiều transaction manager, hãy inject đúng bean bằng `@Qualifier`.

Không nên chọn `DataSourceTransactionManager` một cách tùy tiện cho step ghi JPA. `JpaTransactionManager` quản lý transaction gắn với `EntityManagerFactory` và đồng bộ persistence context với transaction. Nếu một step dùng cả JPA và JDBC, cần cấu hình chúng cùng datasource và theo cơ chế Spring hỗ trợ để JDBC access tham gia transaction phù hợp.

## 4. Entity cần được ánh xạ JPA

`JpaItemWriter` ghi entity được JPA provider quản lý. Entity cần có mapping hợp lệ, thường gồm `@Entity`, `@Id` và các mapping field/relationship.

```java
@Entity
@Table(name = "ORDERS")
public class OrderEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "SOURCE_ORDER_ID", nullable = false, unique = true)
    private String sourceOrderId;

    @Column(name = "CUSTOMER_ID", nullable = false)
    private String customerId;

    @Column(name = "TOTAL_AMOUNT", nullable = false, precision = 19, scale = 2)
    private BigDecimal totalAmount;

    protected OrderEntity() {
    }

    public OrderEntity(
            String sourceOrderId,
            String customerId,
            BigDecimal totalAmount) {
        this.sourceOrderId = sourceOrderId;
        this.customerId = customerId;
        this.totalAmount = totalAmount;
    }

    public Long getId() { return id; }
    public String getSourceOrderId() { return sourceOrderId; }
    public String getCustomerId() { return customerId; }
    public BigDecimal getTotalAmount() { return totalAmount; }
}
```

Ví dụ dùng `sourceOrderId` làm khóa nghiệp vụ duy nhất để tránh nhập trùng cùng một đơn nguồn. Khóa chính JPA và khóa nghiệp vụ có vai trò khác nhau: ID database xác định entity, còn source ID giúp nhận diện cùng một bản ghi đầu vào qua retry/restart hoặc lần import lặp.

## 5. Processor chuyển DTO thành entity

Reader có thể đọc DTO từ CSV, XML, JSON hoặc JDBC. Processor chuyển DTO thành entity trước khi writer ghi:

```java
@Bean
ItemProcessor<OrderInput, OrderEntity> orderProcessor() {
    return input -> {
        if (input.orderId() == null || input.orderId().isBlank()) {
            throw new InvalidOrderException("orderId is required");
        }

        if (input.totalAmount() == null || input.totalAmount().signum() < 0) {
            throw new InvalidOrderException("totalAmount must be non-negative");
        }

        return new OrderEntity(
            input.orderId(),
            input.customerId(),
            input.totalAmount()
        );
    };
}
```

Validation dữ liệu của item thường nên nằm trong processor hoặc một validator riêng. Writer tập trung vào persistence. Nếu processor tra cứu entity hiện có hoặc tạo quan hệ JPA, cần cân nhắc số query, trạng thái entity và transaction mà processor đang tham gia.

## 6. Persist và merge khác nhau thế nào?

`JpaItemWriter` mặc định dùng `EntityManager.merge(item)`. Có thể cấu hình `usePersist(true)` để dùng `EntityManager.persist(item)`.

| Thao tác | Mục đích | Đối tượng đầu vào |
|---|---|---|
| `persist` | Đưa entity mới/transient vào persistence context để insert | Entity mới chưa được persist |
| `merge` | Sao chép state của entity đầu vào vào một instance managed | Thường dùng với entity detached hoặc entity cần đồng bộ state |

`persist` không phải thao tác upsert. Nếu một entity có định danh đã tồn tại hoặc vi phạm identity/constraint, thao tác có thể thất bại tại lúc persist hoặc flush.

`merge` cũng không đơn giản là “update nếu tồn tại, insert nếu không” theo nghĩa một câu SQL upsert. JPA provider quyết định cách tìm/tạo managed instance dựa trên identity và mapping. Nếu không tìm thấy entity tương ứng, merge có thể tạo một bản sao mới để insert.

## 7. Dùng persist cho entity mới

Khi mọi item là entity mới và ID được sinh theo cách phù hợp, có thể cấu hình writer dùng persist:

```java
@Bean
JpaItemWriter<OrderEntity> newOrderWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<OrderEntity>()
        .entityManagerFactory(entityManagerFactory)
        .usePersist(true)
        .build();
}
```

`persist` thường phù hợp với pipeline import tạo entity mới. Cần bảo đảm mỗi entity chưa tồn tại theo identity và khóa nghiệp vụ. Nếu cùng item được phát lại do retry/restart hoặc job được launch lại, unique constraint có thể làm lần ghi tiếp theo thất bại.

Để import có thể chạy lại an toàn, cần chính sách riêng như kiểm tra tồn tại theo source ID, upsert có kiểm soát, staging table hoặc xử lý duplicate theo nghiệp vụ. Không bật `persist` rồi kỳ vọng writer tự loại bỏ bản ghi trùng.

## 8. Dùng merge cho entity detached hoặc state cần đồng bộ

`merge` hữu ích khi item là entity detached hoặc được tạo bên ngoài persistence context hiện tại. Có thể dùng hành vi mặc định:

```java
@Bean
JpaItemWriter<CustomerEntity> customerWriter(
        EntityManagerFactory entityManagerFactory) {

    return new JpaItemWriterBuilder<CustomerEntity>()
        .entityManagerFactory(entityManagerFactory)
        .usePersist(false)
        .build();
}
```

`merge` trả về một managed instance. Đối tượng truyền vào không tự trở thành managed; nó vẫn có thể là detached. `JpaItemWriter` thực hiện merge nhưng không thay item trong chunk bằng object trả về từ `merge`, vì vậy không dựa vào việc field được cập nhật trên object đầu vào sau khi writer chạy.

Merge có thể phát sinh truy vấn để tìm entity hiện có, nên với hàng triệu item cần đo query count và throughput. Nếu mục tiêu chỉ là cập nhật một số cột, có thể cân nhắc bulk update bằng JDBC/JPA query hoặc một writer chuyên biệt thay vì merge toàn bộ entity graph.

## 9. Khi nào nên chọn persist hoặc merge?

Quyết định phụ thuộc trạng thái entity và yêu cầu nghiệp vụ:

| Tình huống | Hướng lựa chọn thường gặp |
|---|---|
| Tạo mới entity, bảo đảm chưa tồn tại | `persist` |
| Nhận entity detached cần đồng bộ state | `merge` |
| Cập nhật entity đang managed trong cùng persistence context | Thường không cần gọi persist/merge lại; thay đổi dirty checking sẽ được flush |
| Import có thể gặp ID đã tồn tại | Xác định rõ update/skip/reject; không dựa vào mặc định để đoán |
| Cần upsert theo khóa nghiệp vụ | Dùng quy tắc upsert rõ ràng hoặc database-specific strategy |

Đừng chọn merge chỉ vì nó “linh hoạt hơn”. Merge có thể làm tăng SELECT và sao chép cả trạng thái field, kể cả giá trị null nếu object đầu vào không được tạo đầy đủ. Đừng chọn persist cho detached entity chỉ vì muốn tránh SELECT; persist không có semantics cập nhật entity hiện có.

## 10. JpaItemWriter flush persistence context

JPA không nhất thiết gửi SQL xuống database ngay khi gọi `persist` hoặc `merge`. Thay đổi được theo dõi trong persistence context và có thể được flush trước commit.

`JpaItemWriter` flush persistence context sau khi ghi chunk để các lỗi constraint hoặc persistence có thể được phát hiện trong phạm vi writer call/transaction. Flush gửi SQL đến database nhưng chưa đồng nghĩa transaction đã commit.

```text
Chunk transaction bắt đầu
    |
    v
JpaItemWriter.write(chunk)
    |
    +--> persist/merge từng entity
    |
    +--> EntityManager.flush()
    |
    v
Database thực thi SQL trong transaction
    |
    +--> writer/step thành công -> COMMIT ở cuối chunk
    |
    +--> exception -> ROLLBACK theo policy
```

Nếu flush phát sinh `ConstraintViolationException`, `PersistenceException` hoặc exception được Spring dịch, exception truyền ra step và transaction có thể rollback. Không bắt rồi bỏ qua lỗi flush nếu dữ liệu chưa được ghi đúng.

## 11. Persistence context và clear sau khi ghi

Persistence context theo dõi các entity managed. Nếu giữ quá nhiều entity trong một context lâu dài, bộ nhớ tăng và dirty checking trở nên tốn kém.

`JpaItemWriter` cung cấp tùy chọn `clearPersistenceContext` trong các phiên bản Spring Batch hỗ trợ. Khi được bật, writer flush rồi clear persistence context để giải phóng các entity đang được quản lý sau lần ghi chunk. Builder có thể cấu hình tùy chọn này bằng `clearPersistenceContext(...)`.

Khi context bị clear, các entity trước đó trở thành detached. Không giữ tham chiếu rồi kỳ vọng thay đổi field sau đó sẽ tự được dirty checking ghi xuống database. Nếu cần cập nhật tiếp, hãy load/merge entity trong transaction phù hợp.

Clear giúp hạn chế persistence context tích lũy qua nhiều chunk. Tuy nhiên, nếu processor hoặc listener dựa vào entity vẫn managed sau writer, cần kiểm tra thứ tự callback và cấu hình; không giả định object luôn được quản lý sau khi writer hoàn tất.

## 12. Transaction boundary của JpaItemWriter

`JpaItemWriter` cần một transaction đang hoạt động để ghi dữ liệu một cách nhất quán. Trong Spring Batch, transaction của chunk step thường là ranh giới phù hợp.

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderInput, OrderEntity>chunk(100, jpaTransactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderJpaWriter)
    .build();
```

Tất cả thao tác JPA của writer trong chunk tham gia transaction được quản lý bởi transaction manager tương ứng với `EntityManagerFactory`. Nếu chunk có 100 item và writer ghi thất bại ở item cuối, các thay đổi chưa commit của chunk được rollback.

Các chunk trước đó đã commit vẫn tồn tại. Job thất bại không tự rollback toàn bộ dữ liệu từ đầu job. Đây là lý do restart cần checkpoint reader và writer cần an toàn khi item chưa commit được đọc lại.

## 13. Dùng cùng EntityManagerFactory và transaction manager

Writer và transaction manager cần cùng persistence unit. Nếu transaction manager quản lý một `EntityManagerFactory` khác với factory mà writer sử dụng, writer có thể không tham gia transaction dự kiến.

Với nhiều persistence unit, cấu hình rõ ràng:

```java
@Bean("ordersJpaTransactionManager")
PlatformTransactionManager ordersJpaTransactionManager(
        @Qualifier("ordersEntityManagerFactory") EntityManagerFactory emf) {
    return new JpaTransactionManager(emf);
}

@Bean
JpaItemWriter<OrderEntity> ordersWriter(
        @Qualifier("ordersEntityManagerFactory") EntityManagerFactory emf) {
    return new JpaItemWriterBuilder<OrderEntity>()
        .entityManagerFactory(emf)
        .build();
}
```

Khi build step, inject `ordersJpaTransactionManager`. Dùng `@Qualifier` để tránh Spring chọn nhầm transaction manager hoặc EntityManagerFactory khi có nhiều datasource.

## 14. Quan hệ giữa JPA transaction và JDBC access

Một ứng dụng có thể dùng JPA cho entity và JDBC cho một số thao tác bulk. Nếu cả hai dùng cùng datasource và được truy cập qua các API Spring transaction-aware, `JpaTransactionManager` có thể phối hợp JDBC access trên datasource đó theo cấu hình phù hợp.

Ví dụ repository JDBC dùng `JdbcTemplate`:

```java
@Repository
public class ImportAuditRepository {

    private final JdbcTemplate jdbcTemplate;

    public ImportAuditRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void recordChunk(long count) {
        jdbcTemplate.update(
            "INSERT INTO IMPORT_AUDIT (RECORD_COUNT) VALUES (?)",
            count
        );
    }
}
```

Để JDBC operation tham gia transaction JPA, cần dùng đúng datasource được quản lý bởi `JpaTransactionManager` và `JdbcTemplate`/`DataSourceUtils`. Một connection lấy trực tiếp từ pool hoặc một datasource khác có thể chạy ngoài transaction của chunk.

Không giả định JPA và JDBC trên hai datasource độc lập sẽ commit nguyên tử. Khi cần nhiều tài nguyên cùng atomic commit, cần cơ chế phân tán phù hợp; nếu không, thiết kế outbox, staging, idempotency hoặc compensation.

## 15. Cascade với quan hệ entity

Khi entity có quan hệ tới entity khác, `persist` và `merge` có thể lan truyền theo cấu hình cascade.

Ví dụ order có các order lines:

```java
@Entity
@Table(name = "ORDERS")
public class OrderEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToMany(mappedBy = "order", cascade = CascadeType.PERSIST)
    private List<OrderLineEntity> lines = new ArrayList<>();

    public void addLine(OrderLineEntity line) {
        lines.add(line);
        line.setOrder(this);
    }
}
```

Khi dùng `persist`, `CascadeType.PERSIST` cho phép persist các line mới theo quan hệ. Nếu dùng merge cho detached graph, cần xem xét `CascadeType.MERGE` hoặc `CascadeType.ALL` theo yêu cầu.

Không thêm cascade rộng một cách máy móc. Ví dụ `CascadeType.REMOVE` có thể xóa entity liên quan ngoài dự kiến; `CascadeType.ALL` bao gồm remove và detach/refresh/persist/merge tùy semantics JPA. Thiết kế ownership và cascade theo vòng đời thực tế của dữ liệu.

## 16. Entity reference và N+1 khi ghi

Processor có thể cần gắn entity mới với customer đã tồn tại. Không nên load cùng một customer nhiều lần theo cách tạo N+1 query nếu có thể tối ưu.

Có thể dùng `EntityManager.getReference` trong một service transactional để lấy proxy tham chiếu theo ID khi phù hợp, hoặc dùng cache/lookup theo chunk. Tuy nhiên, không inject `EntityManager` rồi chia sẻ nó giữa các thread; EntityManager không thread-safe.

Với `JpaItemWriter`, mỗi item thường được persist/merge trong persistence context của transaction. Nếu mỗi item chứa một graph lớn, cascade có thể tạo nhiều câu SQL. Hãy kiểm tra SQL thực tế, fetch strategy và cascade path để tránh ghi lặp hoặc tải không cần thiết.

## 17. Optimistic locking và @Version

Khi nhiều transaction có thể cập nhật cùng entity, optimistic locking giúp phát hiện cập nhật dựa trên state cũ.

```java
@Entity
public class InventoryEntity {

    @Id
    private Long id;

    @Version
    private long version;

    private int availableQuantity;
}
```

JPA provider dùng `version` để phát hiện xung đột. Nếu một transaction cập nhật entity sau khi transaction khác đã thay đổi version, flush/commit có thể phát sinh `OptimisticLockException` hoặc exception được Spring dịch.

Không retry mù quáng optimistic lock bằng cách merge lại cùng một detached snapshot cũ. Lần thử lại có thể vẫn mang version cũ và tiếp tục xung đột. Cần reload state mới và áp dụng lại thay đổi nghiệp vụ nếu thao tác đó có thể được tính lại an toàn.

## 18. Constraint violation và lỗi ghi

Các lỗi thường gặp khi writer flush gồm:

- Unique constraint violation do source ID hoặc business key trùng.
- Foreign key violation do entity tham chiếu chưa tồn tại.
- Not-null/check constraint violation do dữ liệu không hợp lệ.
- Optimistic lock conflict do version đã thay đổi.
- Mapping hoặc SQL error do schema không khớp entity.

Không phải mọi lỗi database đều có thể retry. Lỗi dữ liệu cố định thường cần reject/fail; deadlock hoặc lỗi tạm thời có thể retry có giới hạn; optimistic locking cần chiến lược đọc lại và tính toán lại.

Trong fault-tolerant step, có thể cấu hình skip cho lỗi item cụ thể nếu nghiệp vụ cho phép. Tuy nhiên, writer lỗi ở cấp chunk có thể khiến framework phải recovery để xác định item gây lỗi; writer cần an toàn khi được gọi lại.

## 19. Retry và skip với JpaItemWriter

Ví dụ cấu hình step cho phép skip một loại lỗi dữ liệu đã xác định:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderInput, OrderEntity>chunk(100, jpaTransactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderJpaWriter)
    .faultTolerant()
    .skip(InvalidOrderException.class)
    .skipLimit(50)
    .build();
```

Ví dụ trên skip lỗi do processor ném ra. Nếu lỗi xảy ra trong JPA flush, hãy xác định exception cụ thể và liệu có thể quy về một item hay không. Không skip mọi `PersistenceException`, vì lỗi connection, schema hoặc database-wide có thể ảnh hưởng cả chunk và không thể xử lý bằng cách bỏ một item.

Retry chỉ phù hợp với lỗi transient đã phân loại. Ví dụ deadlock có thể retry sau rollback; unique constraint cố định thường không tự hết khi retry. Nếu dùng `merge`, thao tác cần có semantics idempotent để lần thử lại không gây side effect nghiệp vụ trùng.

## 20. Restart và JobRepository

`JpaItemWriter` không thay thế checkpoint của reader. Khi chunk commit, dữ liệu JPA được commit; reader và các `ItemStream` khác cập nhật state qua `ExecutionContext`. Khi restart cùng JobInstance, Spring Batch dùng JobRepository để quyết định step nào cần chạy lại và reader tiếp tục từ checkpoint.

Ví dụ:

```text
Execution #1
  chunk 1 -> 100 entities -> COMMIT
  chunk 2 -> 100 entities -> COMMIT
  chunk 3 -> lỗi trước commit -> ROLLBACK

Execution #2 (restart cùng JobInstance)
  reader khôi phục checkpoint sau item 200
  đọc lại item thuộc chunk chưa commit
  writer ghi chunk tiếp theo
```

Các entity thuộc chunk đã commit vẫn tồn tại. Các thay đổi của chunk chưa commit được rollback nếu JPA transaction và database hoạt động đúng. Vì vậy, writer không cần lưu item index riêng trong `ExecutionContext` chỉ để thay thế reader checkpoint.

## 21. Idempotency khi restart hoặc chạy lại job

Restart cùng JobInstance khác với việc tạo một JobInstance mới cho cùng input. Khi restart, Spring Batch dựa vào checkpoint để không chạy lại các chunk đã commit trong điều kiện transaction/metadata được phối hợp đúng.

Nhưng hệ thống vẫn cần bảo vệ trường hợp job được launch lại với identifying parameters mới, input bị phát lại hoặc transaction metadata và dữ liệu nghiệp vụ nằm ở các resource khác nhau.

Các cách thường dùng:

- Unique constraint trên source/business key.
- Upsert có quy tắc cập nhật rõ ràng.
- Staging table theo batch ID rồi merge/publish sau khi kiểm tra.
- Ghi trạng thái import theo source ID.
- Idempotency key cho side effect ngoài database.

Không dựa vào `merge` để tự đảm bảo idempotency. Merge đồng bộ state entity theo identity JPA; nó không thay thế khóa nghiệp vụ hoặc quy tắc xử lý duplicate.

## 22. Performance với chunk lớn

Hiệu năng của `JpaItemWriter` phụ thuộc số item mỗi chunk, số câu SQL, cascade graph, persistence context, chiến lược ID và khả năng batch insert của JPA provider/database.

Các điểm cần xem xét:

- Chunk lớn giảm số transaction commit nhưng tăng bộ nhớ và lượng công việc rollback.
- Merge detached entity có thể phát sinh SELECT trước khi update/insert.
- Cascade graph lớn có thể tạo nhiều SQL hơn dự kiến.
- `flush` theo chunk giúp phát hiện lỗi trước commit nhưng có thể tạo đợt SQL lớn.
- Clear persistence context giúp giới hạn managed entities tích lũy.
- JDBC batching phụ thuộc provider, dialect, driver và cấu hình Hibernate/JPA.

Với Hibernate, cấu hình như `hibernate.jdbc.batch_size` và `hibernate.order_inserts`/`hibernate.order_updates` có thể cải thiện batching trong trường hợp phù hợp. Cần đo SQL và benchmark với database thật; không có một batch size tối ưu cho mọi workload.

## 23. IDENTITY generation và JDBC batching

Chiến lược sinh ID ảnh hưởng khả năng gom INSERT. Một số provider/database khó batch insert khi dùng `GenerationType.IDENTITY` vì cần thực thi INSERT để lấy generated key ngay.

Các chiến lược sequence hoặc table generator có thể cho phép provider lấy ID trước và gom lệnh insert tốt hơn, tùy database và cấu hình.

Không đổi ID strategy chỉ để tăng throughput mà không xem xét schema, tính duy nhất và yêu cầu portability. Hãy đo với provider/database thực tế, đồng thời xác nhận thứ tự insert và cascade.

## 24. Bulk operation khác JpaItemWriter

`JpaItemWriter` xử lý entity qua persistence context và các thao tác persist/merge. Bulk JPQL update/delete hoặc JDBC batch có thể hiệu quả hơn khi cần cập nhật số lượng lớn theo một điều kiện mà không cần hydrate từng entity.

Bulk JPQL update/delete thường bỏ qua một phần semantics của entity lifecycle như dirty checking và callback theo từng entity; persistence context đang mở có thể trở nên stale sau bulk operation.

Chọn cách ghi theo yêu cầu:

| Nhu cầu | Cách phù hợp có thể cân nhắc |
|---|---|
| Ghi entity graph với cascade/lifecycle | `JpaItemWriter` |
| Ghi entity mới theo chunk | `JpaItemWriter` với persist nếu item thực sự mới |
| Đồng bộ detached entity | `JpaItemWriter` với merge |
| Cập nhật một cột cho hàng triệu row theo điều kiện | Bulk JPQL hoặc JDBC batch |
| Cần SQL đặc thù hoặc upsert database-specific | Custom JDBC writer/query |

Không chọn bulk query nếu cần callback, cascade hoặc entity validation ở từng entity. Ngược lại, không merge hàng triệu graph lớn nếu một câu SQL bulk có thể diễn tả đúng nghiệp vụ.

## 25. EntityManager không thread-safe

JPA `EntityManager` và persistence context không được thiết kế để chia sẻ đồng thời giữa nhiều thread. `JpaItemWriter` dùng transaction/persistence context phù hợp với lần ghi; không tự tạo một `EntityManager` singleton rồi dùng chung giữa các worker.

Với partitioning, mỗi worker step có transaction và persistence context theo thread/execution của nó. Cần bảo đảm mỗi worker dùng đúng transaction manager và connection pool đủ capacity.

Không lưu `EntityManager` vào static field, không truyền nó qua executor và không gọi cùng persistence context từ nhiều thread. Nếu custom processor/writer cần JPA, inject service/repository transaction-aware và để Spring quản lý context.

## 26. Writer trong composite pipeline

Có thể đặt `JpaItemWriter` làm một delegate của composite writer khi cùng một chunk cần ghi nhiều đích. Tuy nhiên, các delegate cần có transaction semantics tương thích.

Ví dụ cấu hình khái quát:

```java
CompositeItemWriter<OrderEntity> compositeWriter =
    new CompositeItemWriterBuilder<OrderEntity>()
        .delegates(orderJpaWriter, auditWriter)
        .build();
```

Nếu `auditWriter` ghi vào cùng datasource và tham gia cùng transaction, cả hai có thể commit/rollback cùng nhau. Nếu audit writer gọi API hoặc ghi file, side effect đó không tự rollback khi JPA transaction thất bại.

Thứ tự delegate cũng quan trọng: nếu delegate đầu đã tạo side effect ngoài transaction rồi delegate sau thất bại, side effect đầu có thể vẫn tồn tại. Dùng outbox, staging hoặc compensation nếu cần consistency giữa nhiều đích.

## 27. Kiểm thử JpaItemWriter

Unit test cho processor có thể kiểm tra entity được tạo đúng. Nhưng transaction, cascade, flush và constraint cần integration test với JPA provider và database phù hợp.

Các trường hợp nên kiểm tra:

1. Entity mới được persist và row xuất hiện sau commit.
2. Entity detached được merge và state được đồng bộ theo mapping.
3. `usePersist(true)` gặp duplicate identity/constraint theo đúng policy.
4. Quan hệ cascade persist/merge hoạt động đúng.
5. Constraint violation tại flush làm chunk rollback.
6. Chunk trước đã commit vẫn tồn tại khi chunk sau thất bại.
7. Optimistic locking conflict được xử lý theo policy.
8. Clear persistence context không làm code downstream dựa nhầm vào managed state.
9. Restart cùng JobInstance không ghi trùng chunk đã commit.
10. Chạy partition song song không chia sẻ EntityManager giữa thread.
11. JDBC và JPA operations cùng datasource tham gia transaction khi được cấu hình như yêu cầu.
12. Side effect ngoài database được bảo vệ bằng idempotency/outbox/compensation.

Ví dụ kiểm thử service bằng transaction có thể xác nhận rollback:

```java
@Test
void rollsBackJpaWritesWhenChunkTransactionFails() {
    assertThatThrownBy(() -> transactionTemplate.execute(status -> {
        entityManager.persist(new OrderEntity(
            "SRC-1001", "C001", new BigDecimal("125.50")));
        entityManager.flush();
        throw new IllegalStateException("forced failure");
    })).isInstanceOf(IllegalStateException.class);

    assertThat(orderRepository.findBySourceOrderId("SRC-1001"))
        .isEmpty();
}
```

Ví dụ giả định `TransactionTemplate`, `EntityManager` và repository dùng cùng `JpaTransactionManager`/persistence unit. Trong test Spring Batch đầy đủ, nên launch job và xác nhận cả JobRepository metadata lẫn dữ liệu database.

## 28. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng sai `EntityManagerFactory` | Writer không tham gia persistence unit/transaction mong đợi | Inject factory đúng bằng qualifier |
| Dùng transaction manager không tương thích | JPA write có thể không cùng transaction chunk | Dùng `JpaTransactionManager` phù hợp |
| Chọn persist cho entity đã tồn tại | Có thể phát sinh duplicate/EntityExists/constraint error | Xác định entity mới hay detached trước khi chọn |
| Cho rằng merge là SQL upsert | Có thể phát sinh SELECT/INSERT/UPDATE ngoài dự kiến | Thiết kế identity và upsert nghiệp vụ rõ ràng |
| Bỏ qua managed instance trả về từ merge | Tiếp tục sửa object đầu vào detached và mong dirty checking | Load/merge lại hoặc dùng instance managed trong transaction |
| Cascade không phù hợp | Thiếu child insert hoặc xóa/cập nhật lan rộng | Cấu hình cascade theo vòng đời entity |
| Không xử lý unique business key | Job chạy lại tạo bản ghi trùng hoặc thất bại | Unique constraint và idempotent import |
| Persistence context tích lũy quá lớn | Tăng bộ nhớ và dirty checking overhead | Dùng clear phù hợp và chunk size hợp lý |
| Retry mọi PersistenceException | Lỗi schema/constraint cố định bị lặp lại | Phân loại lỗi transient và data error |
| Chia sẻ EntityManager giữa thread | Race condition và lỗi persistence context | Dùng transaction-bound EntityManager theo thread |
| Nghĩ flush là commit | Dữ liệu có thể rollback sau flush | Phân biệt flush với transaction commit |
| Cho rằng JPA và file/API atomic cùng nhau | Side effect ngoài DB còn tồn tại sau rollback | Dùng outbox, staging hoặc compensation |

## 29. Quy trình chọn và cấu hình JpaItemWriter

Khi thiết kế step ghi JPA, hãy xác định:

1. Item đầu vào writer là entity JPA hay DTO cần được processor chuyển đổi?
2. Entity mới/transient hay detached cần đồng bộ state?
3. Nên dùng persist hay merge theo semantics dữ liệu?
4. `EntityManagerFactory` và `JpaTransactionManager` có cùng persistence unit không?
5. Step builder đã nhận đúng transaction manager chưa?
6. Quan hệ entity cần cascade persist/merge nào?
7. Có unique business key, optimistic locking hoặc constraint cần xử lý không?
8. Persistence context có cần clear sau chunk để kiểm soát bộ nhớ không?
9. Chunk size, JDBC batching và ID strategy đã được đo với database thật chưa?
10. Restart, duplicate input và side effect ngoài database có idempotency không?
11. Integration test có xác nhận flush, commit, rollback, cascade và restart không?

## Kết luận

`JpaItemWriter<T>` ghi entity theo chunk bằng JPA `EntityManager`. Theo mặc định, writer dùng `merge`; có thể chọn `persist` khi mọi item là entity mới. `persist` và `merge` có semantics khác nhau: merge sao chép state vào managed instance và trả về instance đó, còn persist đưa entity mới vào persistence context. Merge không phải bảo đảm upsert theo khóa nghiệp vụ.

Hãy cấu hình writer với đúng `EntityManagerFactory` và dùng `JpaTransactionManager` tương ứng trong chunk step. Hiểu flush khác commit, cascade theo quan hệ entity, persistence context clear, optimistic locking và giới hạn thread safety. Dùng unique business key/idempotency để bảo vệ restart và import lặp; kiểm thử trên database thực tế để xác nhận commit, rollback, performance và dữ liệu cuối cùng.
