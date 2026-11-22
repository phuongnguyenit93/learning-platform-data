# Hoàn thiện bộ kiểm chứng số SQL, dữ liệu lưu, khóa và khả năng phục hồi

Một bài kiểm thử persistence chỉ assert rằng service trả về thành công là chưa đủ để chứng minh Hibernate đã làm đúng. Entity có thể mới chỉ nằm trong persistence context; một query có thể âm thầm tạo thêm hàng chục SELECT; hai requests đồng thời có thể ghi đè dữ liệu của nhau; một constraint violation có thể làm transaction thất bại nhưng code vẫn tiếp tục dùng Session; và một retry có thể tạo duplicate nếu lần commit trước có kết quả không rõ.

Một bộ kiểm chứng thực tế cần trả lời được bốn câu hỏi bằng evidence có thể lặp lại:

1. **SQL nào đã chạy, bao nhiêu lần và có vượt ngân sách không?**
2. **Database thực sự lưu dữ liệu gì sau flush và commit?**
3. **Khóa và transaction có bảo vệ invariants khi nhiều requests chạy đồng thời không?**
4. **Khi có lỗi, rollback, retry và phục hồi có giữ dữ liệu đúng không?**

Bài học này kết hợp SQL observation, Hibernate Statistics, JDBC assertions, database constraints, optimistic/pessimistic locking, concurrency tests và failure recovery thành một bộ kiểm chứng thống nhất. Ví dụ dùng Jakarta Persistence, Hibernate ORM, JUnit 5, Spring và PostgreSQL/Testcontainers ở mức minh họa. API cụ thể cần điều chỉnh theo framework, Hibernate version và DBMS của dự án.

## 1. Bộ kiểm chứng phải xác nhận behavior ở nhiều tầng

Một thao tác lưu entity đi qua nhiều tầng:

```text
Application service
      |
      v
EntityManager / Hibernate Session
      |
      +--> Persistence context (L1)
      |
      +--> Hibernate action queue / flush
      |
      v
JDBC driver
      |
      v
Database transaction
      |
      +--> constraints
      +--> locks / isolation
      +--> indexes
      +--> triggers
      |
      v
Committed rows
```

Mỗi tầng cần loại evidence riêng:

| Tầng | Câu hỏi | Evidence phù hợp |
|---|---|---|
| Application | Use case trả kết quả nào? | Service/API result, domain assertions |
| Hibernate | Entity/association được load và flush ra sao? | Hibernate Statistics, SQL logs, persistence-context behavior |
| JDBC | Bao nhiêu statements/batches thực sự được gửi? | DataSource proxy, JDBC instrumentation |
| Database | Rows/columns/FK/constraints cuối cùng là gì? | JDBC queries, DB catalog, committed transaction |
| Concurrency | Hai transactions tương tác thế nào? | Hai connections/EntityManagers, barriers, lock outcomes |
| Recovery | Rollback/retry có an toàn không? | Transaction outcome, fresh-session reads, idempotency records |

Không một metric đơn lẻ chứng minh toàn bộ correctness. Ví dụ, Hibernate Statistics có thể cho biết số prepared statements nhưng không tự chứng minh dữ liệu đã commit đúng; query trả đúng entity trong cùng Session cũng không chứng minh database row đã được ghi.

## 2. Xác định invariant trước khi đếm SQL

Trước khi viết test, mô tả invariant nghiệp vụ cần được giữ.

Ví dụ hệ thống quản lý tồn kho:

```text
InventoryItem
  id
  sku (unique)
  available
  version

Reservation
  id
  inventory_item_id (FK)
  quantity
  request_key (unique)
```

Một request đặt trước hàng có thể yêu cầu:

- Số lượng reservation phải lớn hơn 0.
- SKU phải tồn tại.
- Không được đặt nhiều hơn available.
- Một request key chỉ được ghi nhận một lần.
- Available không được âm.
- Mỗi reservation phải tham chiếu đúng InventoryItem.
- Hai requests cạnh tranh không được cùng tiêu thụ một đơn vị hàng cuối cùng.
- Nếu transaction thất bại, không được có reservation nửa chừng.
- Nếu retry sau timeout, không được tạo reservation trùng.

Viết invariant trước giúp xác định test cần kiểm tra SQL, database state, locking hay recovery. Nếu chưa biết điều gì phải luôn đúng, việc đếm query chỉ tạo ra con số thiếu ý nghĩa.

## 3. Tách unit test và database integration test

Unit test phù hợp với business rules thuần Java:

- Quantity âm bị từ chối.
- Không cho phép chuyển trạng thái Order không hợp lệ.
- Tính tổng tiền đúng.
- Một command tạo ra các domain events cần thiết.

Database integration test cần thiết cho:

- SQL shape và số statement.
- Flush/auto-flush.
- Mapping và FK.
- Unique/check/not-null constraints.
- Optimistic/pessimistic locks.
- Isolation và concurrent transactions.
- Rollback, deadlock và retry.
- Hibernate cache, Envers hoặc database-specific features.

Không mock EntityManager/Session rồi dùng kết quả đó để kết luận Hibernate SQL hoặc database locking đúng. Mock có thể kiểm tra service orchestration, nhưng không mô phỏng database engine.

## 4. Chọn database tương thích production

Hành vi transaction, lock, constraint, SQL dialect và query plan phụ thuộc DBMS.

H2 có thể hữu ích cho test nhanh, nhưng không thay thế integration test trên PostgreSQL, MySQL, Oracle hoặc SQL Server đang chạy production. Ví dụ:

- PostgreSQL đánh dấu transaction aborted sau nhiều statement errors.
- Lock timeout và deadlock reporting khác nhau giữa DBMS.
- Partial/filtered unique indexes có syntax và semantics riêng.
- FOR UPDATE, skip locked và isolation behavior có khác biệt.
- Generated keys, sequence và batch update counts phụ thuộc driver.

Dùng Testcontainers để chạy DBMS cùng loại và version gần production. Nếu production dùng extension, collation, timezone hoặc isolation configuration đặc biệt, đưa chúng vào test setup.

## 5. Khởi tạo schema bằng migrations

Một test đáng tin cậy nên chạy Flyway/Liquibase hoặc migration tool thật của dự án.

Quy trình:

1. Khởi động database trống.
2. Chạy migrations theo thứ tự production.
3. Khởi tạo Hibernate với schema validation phù hợp.
4. Chạy integration tests.
5. Kiểm tra constraints và indexes được tạo thật.
6. Dọn dữ liệu/test container khi hoàn tất.

Không để Hibernate tự tạo schema trong test rồi kết luận migration production đúng. Cấu hình create-drop có thể che giấu migration bị thiếu hoặc khác biệt giữa mapping và DDL.

## 6. Cấu trúc Testcontainers minh họa

Ví dụ PostgreSQL container với JUnit 5:

```java
@Testcontainers
@SpringBootTest
class InventoryPersistenceIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16");

    @DynamicPropertySource
    static void databaseProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "spring.datasource.url",
            postgres::getJdbcUrl
        );
        registry.add(
            "spring.datasource.username",
            postgres::getUsername
        );
        registry.add(
            "spring.datasource.password",
            postgres::getPassword
        );
    }
}
```

Đây là skeleton; dependencies, container lifecycle và property names cần theo Spring Boot/Testcontainers versions của dự án.

Nếu test suite chạy song song, tránh dùng một schema chung mà tests truncate hoặc reset lẫn nhau. Có thể dùng database/schema riêng, transaction isolation phù hợp hoặc test execution serialization cho nhóm tests cần shared state.

## 7. Tạo dữ liệu test có thể lặp lại

Fixture phải rõ ràng và độc lập:

```java
InventoryItem createInventory(String sku, int available) {
    InventoryItem item = new InventoryItem(sku, available);
    entityManager.persist(item);
    entityManager.flush();
    return item;
}
```

Với test cần commit thật, factory nên chạy trong transaction setup riêng và trả về ID thay vì trả managed entity:

```java
Long createInventoryAndCommit(String sku, int available) {
    return transactionTemplate.execute(status -> {
        InventoryItem item =
            new InventoryItem(sku, available);
        entityManager.persist(item);
        entityManager.flush();
        return item.getId();
    });
}
```

Mỗi test cần biết:

- Fixture được tạo trong transaction nào?
- Fixture đã commit chưa?
- ID được tạo bằng identity hay sequence?
- L2/query cache có đang bật không?
- Test có chạy song song với test khác không?
- Cleanup có tạo audit events hoặc trigger side effects không?

Đừng dùng IDs cố định hoặc shared mutable fixtures trong concurrent tests.

## 8. Đếm SQL: cần phân biệt các loại số đếm

“SQL count” có thể mang nhiều nghĩa:

| Metric | Ý nghĩa | Giới hạn |
|---|---|---|
| SQL strings observed | Số SQL được instrumentation nhìn thấy | Có thể ghi nhận trước khi execute |
| Prepared statements | Số JDBC statements được prepare | Không luôn bằng số round trips |
| Execute calls | Số lần gọi execute/executeUpdate | Batch có semantics riêng |
| Batch executions | Số lần gửi JDBC batch | Một batch chứa nhiều rows/statements |
| Database statements | Số statements DBMS ghi nhận | Cần DB telemetry/logging |
| Queries per request | Tổng query count gắn với request | Cần correlation/context instrumentation |

Không gọi tất cả những số này là “database round trips” nếu công cụ đang đo ở một tầng khác.

Một test có thể đo SQL count ở tầng JDBC và đối chiếu với Hibernate Statistics. Hai con số có thể khác vì prepare, batch, retries hoặc instrumentation boundaries.

## 9. Dùng Hibernate Statistics để quan sát ORM

Bật statistics trong test profile:

```properties
hibernate.generate_statistics=true
```

Trong Spring Boot:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Lấy Statistics:

```java
SessionFactory sessionFactory =
    entityManagerFactory.unwrap(SessionFactory.class);

Statistics statistics =
    sessionFactory.getStatistics();

statistics.setStatisticsEnabled(true);
```

Một số counters hữu ích:

```java
long prepared =
    statistics.getPrepareStatementCount();

long entityLoads =
    statistics.getEntityLoadCount();

long entityFetches =
    statistics.getEntityFetchCount();

long queryExecutions =
    statistics.getQueryExecutionCount();
```

Tên và availability của API phụ thuộc Hibernate version. Statistics thường là counters tổng hợp ở phạm vi SessionFactory; nhiều tests/requests chạy đồng thời có thể làm lẫn số liệu.

Trong test cô lập, snapshot counters trước và sau một operation để lấy delta. Tránh gọi clear() trên Statistics trong production traffic vì nó reset counters dùng chung.

## 10. Snapshot và delta counters

Ví dụ:

```java
record OrmSnapshot(
    long preparedStatements,
    long entityLoads,
    long entityFetches,
    long queryExecutions
) {}

static OrmSnapshot snapshot(Statistics s) {
    return new OrmSnapshot(
        s.getPrepareStatementCount(),
        s.getEntityLoadCount(),
        s.getEntityFetchCount(),
        s.getQueryExecutionCount()
    );
}
```

Sử dụng:

```java
OrmSnapshot before = snapshot(statistics);

runOneUseCase();

OrmSnapshot after = snapshot(statistics);

long statementDelta =
    after.preparedStatements()
        - before.preparedStatements();

long entityLoadDelta =
    after.entityLoads() - before.entityLoads();
```

Delta chỉ đại diện chính xác use case nếu không có hoạt động ORM khác chen vào counters trong cửa sổ đo. Chạy test tuần tự/cô lập hoặc dùng JDBC instrumentation gắn với execution context cụ thể.

## 11. Dùng StatementInspector để ghi SQL Hibernate tạo

Hibernate cung cấp StatementInspector cho phép quan sát SQL string trước khi Hibernate gửi statement qua JDBC.

Ví dụ:

```java
public final class RecordingStatementInspector
        implements StatementInspector {

    private final List<String> statements =
        new CopyOnWriteArrayList<>();

    @Override
    public String inspect(String sql) {
        statements.add(sql);
        return sql;
    }

    public List<String> snapshot() {
        return List.copyOf(statements);
    }

    public void clear() {
        statements.clear();
    }
}
```

Cấu hình inspector trong test bootstrap theo API/version tương ứng.

Ưu điểm:

- Quan sát SQL Hibernate tạo.
- Có thể phân loại SELECT/INSERT/UPDATE/DELETE.
- Hữu ích để phát hiện N+1 và query shape.
- Không cần sửa business code.

Giới hạn:

- Không nhất thiết cho biết statement đã execute thành công.
- Không ghi bind parameter values.
- Không phản ánh chính xác số batch executions.
- Có thể ghi SQL từ bootstrap hoặc hoạt động ngoài test nếu inspector dùng chung.
- Một inspector singleton cần xử lý concurrency/thread safety.

Dùng nó để quan sát SQL do Hibernate phát ra, không thay thế JDBC/database-level execution metrics.

## 12. Đếm execute calls ở JDBC layer

Nếu mục tiêu là số lần JDBC thực sự gọi execute/executeUpdate/executeBatch, dùng DataSource proxy hoặc JDBC instrumentation.

Ví dụ khái niệm với datasource-proxy:

```java
ProxyDataSource proxy =
    ProxyDataSourceBuilder
        .create(realDataSource)
        .name("integration-test")
        .listener(queryExecutionListener)
        .build();
```

Listener có thể ghi nhận:

- SQL.
- Method execution.
- Elapsed time.
- Batch size/update counts.
- Success/failure.
- Connection identity.
- Correlation/test context.

Cấu hình chính xác phụ thuộc thư viện và version. Nếu dự án dùng P6Spy hoặc datasource-proxy, dùng một công cụ thống nhất thay vì chồng nhiều proxy khiến số đếm khó diễn giải.

Không log raw bind parameters nhạy cảm trong production. Trong integration tests với synthetic data, parameter capture có thể hữu ích để chẩn đoán.

## 13. Gắn SQL count với một test hoặc request

Không nên reset global SQL counter giữa hai requests chạy đồng thời. Có thể dùng:

- Một DataSource/test context riêng cho mỗi test.
- ThreadLocal execution context nếu tất cả DB calls đồng bộ trên cùng thread.
- Explicit correlation ID được instrumentation truyền qua context.
- Một request-scoped metrics collector.
- Test execution tuần tự cho counter global.

ThreadLocal không tự theo được asynchronous tasks, executor threads hoặc reactive context. Nếu request chuyển thread, cần context propagation phù hợp.

Với integration test đơn giản, cách ít rủi ro là chỉ chạy một operation trong cửa sổ đo và không chạy tests song song trên cùng SessionFactory/counter.

## 14. Viết SQL budget thay vì chỉ log số

Một assertion có thể đặt ngân sách:

```java
assertThat(statementCount)
    .isLessThanOrEqualTo(5);
```

Ngân sách phải gắn với use case và fixture cụ thể. Ví dụ:

- Load một Order với customer: tối đa 2 SELECT.
- Load một page 20 orders và các associations cần thiết: tối đa 3 SELECT.
- Persist một aggregate nhỏ: số INSERT dự kiến theo mapping.
- Lookup cùng entity trong Session: không phát SELECT thứ hai nhờ L1.
- Lookup trong Session mới với L2 enabled: kỳ vọng cache behavior phù hợp.

Không đặt ngưỡng “mọi request dưới 3 queries” cho toàn ứng dụng. Một report hợp lệ có thể cần nhiều queries; điều quan trọng là query count phù hợp với use case và không tăng theo số rows ngoài dự kiến.

## 15. Kiểm thử N+1 bằng fixture tăng kích thước

Một cách phát hiện N+1:

1. Tạo 1 Order có nhiều Lines và mỗi Line tham chiếu Product.
2. Clear persistence context.
3. Bắt đầu SQL capture.
4. Load danh sách Orders theo query thực tế.
5. Duyệt dữ liệu đúng như service/serializer sử dụng.
6. Dừng capture.
7. Assert SELECT count không tăng tuyến tính theo số Orders/Lines ngoài dự kiến.

Ví dụ:

```java
List<PurchaseOrder> orders =
    repository.findRecentOrders(pageable);

List<String> productNames = orders.stream()
    .flatMap(order -> order.getLines().stream())
    .map(line -> line.getProduct().getName())
    .toList();
```

Nếu mỗi Order hoặc Line gây thêm SELECT riêng, SQL count tăng theo dataset. Test với 1, 10 và 50 parents giúp nhìn thấy xu hướng.

Đừng chỉ test một parent; N+1 có thể không xuất hiện rõ với fixture nhỏ.

## 16. Phân biệt L1 hit, L2 hit và database SELECT

Trong cùng Session:

```java
InventoryItem first =
    session.find(InventoryItem.class, id);

InventoryItem second =
    session.find(InventoryItem.class, id);

assertSame(first, second);
```

Lần đọc thứ hai có thể là L1 hit. Nó không chứng minh L2 hoạt động.

Để kiểm tra L2:

1. Session A load entity và kết thúc.
2. Session B mới load cùng ID.
3. Quan sát L2 statistics/provider metrics.
4. Kiểm tra JDBC SELECT count.
5. Chạy lại với L2 tắt để có baseline.

Để đo SQL query độc lập, kiểm soát query cache và cache regions. Không gộp L1/L2/query cache hits thành một số cache hit chung.

## 17. Kiểm soát cache trong SQL-count tests

Cache có thể làm test query count pass vì database không được gọi, dù test đang muốn đo fetch plan/SQL.

Tùy mục tiêu:

- Tắt L2/query cache trong test query-shape baseline.
- Evict region/entity trước mỗi test cô lập.
- Dùng Session mới để loại L1.
- Tách test cache behavior thành suite riêng.
- Không clear shared production cache để đo.

Ghi rõ cache mode trong test report. Một test “3 SELECT” không có ý nghĩa nếu không biết cache state.

## 18. SQL count khi dùng JDBC batching

Nếu bật Hibernate JDBC batching, một số INSERT/UPDATE có thể được gom vào executeBatch().

Phân biệt:

- Số SQL statements Hibernate tạo.
- Số PreparedStatements.
- Số lần gọi executeBatch.
- Số rows DBMS cập nhật.
- Số network round trips thực tế.

Ví dụ 100 inserts có thể tạo 100 logical INSERTs nhưng chỉ một số batch executions tùy hibernate.jdbc.batch_size, ordering và driver capabilities.

Không assert một số round trips chỉ từ StatementInspector. Nếu batching là mục tiêu, dùng JDBC proxy/driver metrics và xác nhận database rows cuối cùng.

## 19. SQL shape quan trọng hơn whitespace

SQL có thể khác alias, quoting, whitespace và parameter markers giữa Hibernate versions/Dialects.

Thay vì so sánh nguyên văn, hãy assert properties ổn định hơn:

- Statement category SELECT/INSERT/UPDATE/DELETE.
- Table được truy cập.
- Có/không có join cần thiết.
- Số statements.
- Có pagination predicate/limit.
- Có điều kiện tenant/soft-delete.
- Có optimistic version predicate.
- Có FOR UPDATE nếu yêu cầu lock.
- Database state cuối.

Nếu SQL shape chính là contract performance, normalize SQL hoặc dùng DB plan tests cho DBMS cụ thể; vẫn tránh hardcode alias không có ý nghĩa.

## 20. Kiểm tra persisted state: flush chưa phải commit

Một entity sau persist có thể chỉ đang managed trong persistence context.

```java
entityManager.persist(order);

assertNotNull(order.getId());
```

Generated ID không chứng minh transaction đã commit. Một số ID strategies cấp ID sớm và transaction có thể rollback sau đó.

Mẫu test:

```java
entityManager.persist(order);
entityManager.flush();
entityManager.clear();

PurchaseOrder reloaded =
    entityManager.find(PurchaseOrder.class, orderId);

assertNotNull(reloaded);
```

- flush gửi pending SQL xuống database trong transaction.
- clear loại managed state khỏi L1.
- find sau đó dùng context mới trong cùng EntityManager sau clear, nhưng transaction vẫn có thể chưa commit.
- Để chứng minh committed state, kết thúc transaction thành công rồi đọc trong transaction mới.

## 21. Flush, clear, commit và fresh transaction khác nhau

| Bước | Điều chứng minh | Điều chưa chứng minh |
|---|---|---|
| Persist | Entity được đưa vào persistence context | SQL đã chạy |
| Flush | Pending SQL đã được gửi trong transaction | Transaction đã commit |
| Clear | L1 managed state bị detach | L2/query cache đã bị xóa |
| Commit | Transaction đã commit thành công | External side effects đã hoàn tất |
| Fresh transaction read | Transaction mới quan sát committed state theo isolation | Mọi replica/cache khác đã đồng bộ nếu hệ thống phân tán |

Test cần chọn đúng mức assertion. Đừng dùng flush làm bằng chứng cho durability.

## 22. Đọc trực tiếp database để kiểm tra rows

Ví dụ dùng JdbcTemplate:

```java
Integer count = jdbcTemplate.queryForObject(
    "select count(*) from inventory_items where sku = ?",
    Integer.class,
    "SKU-100"
);

assertEquals(1, count);
```

Kiểm tra field values:

```java
Integer available = jdbcTemplate.queryForObject(
    "select available from inventory_items where id = ?",
    Integer.class,
    itemId
);

assertEquals(7, available);
```

JDBC assertion kiểm tra physical database state, không chỉ ORM-filtered view. Đối với post-commit assertion, thực hiện trong transaction/connection mới. Nếu đọc trong transaction hiện tại, hiểu rõ isolation và visibility.

## 23. Persistence context và L2 cache có thể che giấu database state

Sau clear, L1 đã bị xóa nhưng L2 có thể vẫn giữ entity. Vì vậy, một lần find sau clear không chắc phát SELECT.

Khi cần kiểm tra database row:

- Dùng JDBC query độc lập.
- Hoặc evict L2 trong test cô lập.
- Hoặc tắt L2/query cache cho suite đó.
- Mở transaction mới sau commit.
- Ghi lại cache mode.

Đối với test cache, ngược lại, phải bật cache và kiểm tra invalidation riêng. Không để một test vừa cố đo SQL vừa phụ thuộc cache state không kiểm soát.

## 24. Kiểm tra foreign keys bằng database

Một mapping hai chiều có thể đúng trong memory nhưng FK sai. Dùng JDBC:

```java
Long storedItemId = jdbcTemplate.queryForObject(
    "select inventory_item_id from reservations where id = ?",
    Long.class,
    reservationId
);

assertEquals(expectedItemId, storedItemId);
```

Kiểm tra thêm:

- FK thực sự tồn tại trong schema.
- FK không nullable nếu domain yêu cầu.
- Delete behavior RESTRICT/CASCADE/SET NULL đúng policy.
- Tenant key có nằm trong composite FK nếu schema cần.
- Migration đã tạo constraint, không chỉ mapping annotation.

Không chỉ assert collection size hoặc reservation.getItem(). Kiểm tra row/constraint thực tế.

## 25. Kiểm tra unique constraints bằng hai transactions

Một check trước khi insert không bảo vệ được race condition:

```java
if (!repository.existsBySku(sku)) {
    repository.save(new Product(sku));
}
```

Hai requests có thể cùng thấy SKU chưa tồn tại rồi cùng insert. Unique constraint ở database là lớp bảo vệ cuối.

Test:

1. Mở hai transactions độc lập.
2. Cả hai kiểm tra cùng SKU chưa tồn tại.
3. Dùng barrier để đồng bộ.
4. Cả hai cố insert.
5. Một transaction commit; transaction còn lại nhận unique violation.
6. Rollback transaction thất bại.
7. Query mới xác nhận chỉ có một row.

Kết quả chính xác transaction nào thắng không quan trọng. Invariant là chỉ một row tồn tại.

## 26. Kiểm tra NOT NULL và CHECK constraints

Mapping có nullable=false hoặc Bean Validation không thay thế database constraints.

Ví dụ DDL:

```sql
create table inventory_items (
    id bigint primary key,
    sku varchar(80) not null unique,
    available integer not null check (available >= 0),
    version bigint not null
);
```

Test negative nên cố ghi dữ liệu vi phạm qua đường JDBC/native SQL nếu mục tiêu là chứng minh DB constraint. Nếu chỉ gọi service validation, test đó chứng minh application validation chứ không chứng minh DB constraint.

Có thể có cả validation và database constraints; chúng bảo vệ ở các tầng khác nhau.

## 27. Optimistic locking với @Version

Mapping:

```java
@Entity
public class InventoryItem {

    @Id
    private Long id;

    @Version
    private long version;

    private int available;
}
```

Hibernate thường phát UPDATE có điều kiện version, khái niệm:

```sql
update inventory_items
set available = ?, version = ?
where id = ? and version = ?
```

Nếu một transaction đã update row và tăng version, transaction khác dùng version cũ sẽ không update được đúng số rows mong đợi. Hibernate báo optimistic locking failure theo exception hierarchy/version.

Test phải dùng hai persistence contexts và transactions độc lập. Hai object trong cùng Session không tạo ra cạnh tranh optimistic locking thật.

## 28. Test optimistic locking với hai EntityManagers

Mẫu test có thể tổ chức bằng hai transactions:

```text
Transaction A                  Transaction B
-------------                  -------------
Load item version 4            Load item version 4
Change available               Change available
Flush/commit
                               Flush/commit
                               -> version conflict
Rollback/close B
New transaction reads version 5
```

Assertions:

- A commit thành công.
- B thất bại do stale version.
- B rollback và Session bị discard.
- Database giữ state từ A.
- Version tăng đúng theo mapping.
- Retry của B (nếu business cho phép) phải reload state mới trong transaction mới.

Không assert chính xác exception wrapper ở mọi tầng nếu Spring translation/Hibernate version khác nhau; assert root cause và database outcome.

## 29. Ví dụ concurrent optimistic-lock test

Đây là skeleton cần điều chỉnh transaction manager và test executor của dự án:

```java
CountDownLatch bothLoaded = new CountDownLatch(2);
CountDownLatch allowUpdates = new CountDownLatch(1);

Callable<Void> worker = () ->
    transactionTemplate.execute(status -> {
        InventoryItem item =
            entityManager.find(InventoryItem.class, itemId);

        bothLoaded.countDown();
        await(allowUpdates);

        item.decreaseAvailable(1);
        entityManager.flush();
        return null;
    });

Future<Void> first = executor.submit(worker);
Future<Void> second = executor.submit(worker);

bothLoaded.await();
allowUpdates.countDown();
```

Trong code thật, hai workers phải có transaction-scoped EntityManagers riêng. Không chia sẻ một injected EntityManager proxy theo cách khiến cả hai thread dùng chung persistence context. Helper await phải xử lý interrupt/timeout; executor cần được shutdown trong finally.

Kiểm tra một attempt thành công và một attempt conflict, không dựa vào thứ tự winner cố định.

## 30. Pessimistic locking với PESSIMISTIC_WRITE

Khi cần serialize access trên row, JPA cung cấp lock modes như PESSIMISTIC_READ và PESSIMISTIC_WRITE.

Ví dụ:

```java
InventoryItem item = entityManager.find(
    InventoryItem.class,
    itemId,
    LockModeType.PESSIMISTIC_WRITE
);
```

Hibernate có thể tạo SQL lock phù hợp dialect, chẳng hạn SELECT ... FOR UPDATE trên PostgreSQL. SQL cụ thể tùy DBMS.

Test cần xác nhận:

- Transaction A lấy lock.
- Transaction B yêu cầu lock cùng row.
- B chờ hoặc timeout theo cấu hình.
- A commit/rollback và giải phóng lock.
- B tiếp tục hoặc nhận lock timeout.
- Dữ liệu cuối giữ invariant.

Không chỉ assert annotation hoặc lock mode được truyền; xác nhận concurrency behavior trên database thật.

## 31. Test pessimistic lock với hai connections

Một test deterministic hơn dùng barriers:

```text
Connection / Tx A                 Connection / Tx B
-----------------                 -----------------
BEGIN                             BEGIN
SELECT ... FOR UPDATE
                                  SELECT ... FOR UPDATE
                                  waits or times out
UPDATE row
COMMIT
                                  lock becomes available
                                  continue or timeout
COMMIT / ROLLBACK
```

Không dùng cùng JDBC connection cho hai transactions. Không dùng cùng EntityManager. Dùng latches để biết A đã giữ lock trước khi B yêu cầu lock.

Để test timeout, cấu hình timeout nhỏ và có giới hạn tổng thời gian test. Lock timeout hint/setting có thể được diễn giải khác nhau theo Hibernate dialect và DBMS; xác nhận SQL/driver behavior thực tế.

## 32. Không kiểm tra lock bằng sleep tùy tiện

Test concurrency dùng Thread.sleep(500) để “chờ lock được giữ” dễ flaky. Máy CI chậm hoặc nhanh có thể làm kết quả thay đổi.

Ưu tiên:

- CountDownLatch.
- CyclicBarrier.
- Phases có timeout.
- Transaction callbacks.
- Explicit signals sau khi statement đầu tiên hoàn tất.
- DBMS lock introspection nếu cần chẩn đoán.

Dùng timeout như giới hạn an toàn, không làm cơ chế đồng bộ chính. Mỗi test phải giải phóng locks/executors trong finally để tránh ảnh hưởng tests tiếp theo.

## 33. Lock timeout và query timeout không phải một khái niệm

- **Lock timeout:** giới hạn thời gian chờ lấy lock.
- **Query timeout:** giới hạn thời gian statement/query chạy.
- **Transaction timeout:** giới hạn thời gian transaction theo transaction manager/provider.
- **Connection acquisition timeout:** giới hạn thời gian chờ connection từ pool.

Chúng có thể phát ra exception khác nhau và tác động tới transaction khác nhau. Test cần xác nhận đúng failure mode.

Không đặt một timeout duy nhất rồi gọi mọi lỗi là lock timeout. Log SQLState/vendor code và exception chain.

## 34. Deadlock cần được kiểm thử như một outcome có thể xảy ra

Hai transactions lock nhiều rows theo thứ tự khác nhau có thể tạo deadlock:

```text
T1: lock row A
T2: lock row B
T1: request lock row B
T2: request lock row A
       |
       v
Database detects deadlock
       |
       v
One transaction becomes victim
```

Test trên DBMS thật có thể tạo deadlock có kiểm soát bằng hai transactions và barriers. DBMS chọn victim có thể không cố định.

Assertions nên kiểm tra:

- Có một transaction bị abort/victim.
- Transaction còn lại có thể hoàn tất.
- Transaction thất bại được rollback/discard.
- Database cuối cùng giữ invariant.
- Retry (nếu có) dùng transaction mới.
- Không có duplicate/partial writes.

Không assert T1 luôn là victim hoặc T2 luôn là victim.

## 35. Giữ thứ tự lock nhất quán

Một cách giảm deadlock là lấy locks theo thứ tự ổn định, ví dụ sort IDs tăng dần trước khi lock nhiều InventoryItems.

```java
List<Long> ids = requestedIds.stream()
    .sorted()
    .toList();

for (Long id : ids) {
    entityManager.find(
        InventoryItem.class,
        id,
        LockModeType.PESSIMISTIC_WRITE
    );
}
```

Điều này không loại bỏ mọi deadlock, vì database còn lock indexes/foreign keys và các code paths khác. Nhưng nó giảm một nguồn cycle phổ biến.

Test hai requests cùng lock một tập IDs theo thứ tự khác nhau ở input, xác nhận service normalize thứ tự lock và giữ invariants.

## 36. Isolation level và anomalies

Transaction isolation ảnh hưởng các reads/writes đồng thời:

| Isolation | Hiện tượng cần chú ý |
|---|---|
| READ COMMITTED | Mỗi statement có thể thấy committed state mới hơn |
| REPEATABLE READ | Snapshot/locking semantics phụ thuộc DBMS |
| SERIALIZABLE | Có thể abort transaction do serialization conflict |
| READ UNCOMMITTED | Một số DBMS không hỗ trợ đầy đủ hoặc ánh xạ khác |

Không suy luận isolation behavior chỉ từ tên level; PostgreSQL và MySQL/InnoDB có semantics khác nhau ở một số trường hợp.

Test cần gắn với business invariant, ví dụ:

- Không oversell inventory.
- Không tạo hai active reservations cùng request key.
- Tổng phân bổ không vượt capacity.
- Không đọc trạng thái nửa chừng.
- Khi serialization failure, retry toàn transaction.

## 37. Kiểm tra lost update và write skew

Optimistic locking @Version có thể bảo vệ update trên cùng entity row. Nhưng một invariant trải qua nhiều rows có thể cần lock/query strategy khác.

Ví dụ hai doctors cùng trực ca, rule là ít nhất một người phải ở trạng thái ON_CALL. Hai transactions cùng đọc hai rows và mỗi người tự chuyển mình OFF_CALL có thể tạo write skew nếu không có constraint/locking phù hợp.

Test phải mô phỏng hai transactions đọc cùng snapshot rồi update các rows khác nhau. Nếu invariant không được bảo vệ bởi @Version trên từng row, cân nhắc:

- Lock một aggregate/root row.
- Pessimistic locks.
- Serializable isolation và retry.
- Database constraint/trigger.
- Thiết kế schema để invariant trở thành constraint.

Đừng giả định có @Version trên mọi entity là mọi multi-row invariant đã an toàn.

## 38. Constraint vẫn là lớp bảo vệ cuối

Application-level check như:

```java
if (item.getAvailable() >= requested) {
    item.decreaseAvailable(requested);
}
```

có thể bị race khi hai requests cùng đọc giá trị. Có thể cần atomic update:

```sql
update inventory_items
set available = available - :quantity,
    version = version + 1
where id = :id
  and available >= :quantity;
```

Sau đó kiểm tra affected row count. Nhưng native/bulk update có thể bypass persistence context, callbacks, Envers và cache invalidation; cần clear/refresh/evict phù hợp và kiểm tra transaction semantics.

Một unique/check/FK constraint phù hợp có thể bảo vệ invariants ngay cả khi code path khác bỏ qua service validation.

## 39. Kiểm tra atomic update và affected row count

Ví dụ repository native update:

```java
@Modifying
@Query(value = """
    update inventory_items
       set available = available - :quantity
     where id = :id
       and available >= :quantity
    """, nativeQuery = true)
int reserve(@Param("id") Long id,
            @Param("quantity") int quantity);
```

Service:

```java
int updated = repository.reserve(itemId, quantity);

if (updated != 1) {
    throw new InsufficientInventoryException();
}
```

Nếu updated = 0, có thể row không tồn tại hoặc quantity không đủ; domain phải phân biệt nếu cần bằng một read trong transaction mới hoặc query phù hợp.

Sau native update, không dùng managed entity cũ như state mới nhất. Clear/refresh context theo transaction design và xử lý L2/query cache invalidation. Nếu statement lỗi, rollback và discard context.

## 40. Kiểm tra transaction rollback sau SQL failure

Một test nên tạo constraint violation có chủ đích:

```java
@Test
void failedInsertDoesNotLeavePartialRows() {
    assertThrows(
        DataIntegrityViolationException.class,
        () -> writer.insertDuplicateSku()
    );

    Integer count = jdbcTemplate.queryForObject(
        "select count(*) from products where sku = ?",
        Integer.class,
        "SKU-DUP"
    );

    assertEquals(0, count);
}
```

Điều kiện:

- Method writer chạy qua Spring transaction proxy.
- Exception thoát khỏi transactional boundary để rollback.
- Query kiểm tra chạy trong transaction mới.
- Test không bị outer test transaction che giấu commit/rollback.
- Database thật có unique constraint.

Không chỉ assert exception; kiểm tra rows cuối cùng.

## 41. Sau persistence exception phải discard Session

Khi Hibernate Session ném exception trong persistence operation, rollback transaction và đóng/discard Session. Không tiếp tục dùng Session đó.

Không dùng những thao tác sau như cơ chế phục hồi:

- Gọi clear() rồi tiếp tục.
- Chạy query chẩn đoán trên cùng Session.
- Gọi flush lần nữa.
- Bắt exception rồi persist row kế tiếp.
- Dùng noRollbackFor để ép commit.
- Retry SQL cuối trên cùng connection.

Persistence context có thể chứa state không còn nhất quán với database, và database transaction có thể đã bị abort/rollback-only.

## 42. Retry phải tạo transaction và persistence context mới

Mẫu cấu trúc:

```java
public ReservationResult reserveWithRetry(Command command) {
    for (int attempt = 1; attempt <= 3; attempt++) {
        try {
            return reservationWriter.reserveInNewTransaction(
                command
            );
        } catch (TransientDataAccessException ex) {
            if (attempt == 3) {
                throw ex;
            }
            backoff(attempt);
        }
    }

    throw new IllegalStateException("Unreachable");
}
```

```java
@Service
public class ReservationWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public ReservationResult reserveInNewTransaction(
            Command command) {
        // Mỗi lần gọi là một unit of work mới.
        return performReservation(command);
    }
}
```

Bean writer riêng giúp lời gọi đi qua Spring proxy. Có thể dùng TransactionTemplate thay thế. Không retry mọi exception; unique/FK/validation errors thường không tự hết.

## 43. Không retry trong cùng @Transactional method

Một loop bên trong cùng transaction:

```java
@Transactional
public void saveWithRetry(Product product) {
    for (int attempt = 0; attempt < 3; attempt++) {
        try {
            entityManager.persist(product);
            entityManager.flush();
            return;
        } catch (PersistenceException ex) {
            // Sai: transaction/session cũ có thể đã lỗi.
        }
    }
}
```

Không tạo attempt độc lập. Transaction có thể rollback-only và Session đã không còn an toàn.

Đặt retry orchestration ngoài transactional method. Mỗi attempt đọc lại dữ liệu mới nhất, tính lại business rules và thực hiện toàn bộ unit of work từ đầu.

## 44. Phân loại transient và permanent failures

| Failure | Retry? | Cách xử lý |
|---|---|---|
| Deadlock victim | Có thể | Rollback, backoff, transaction mới |
| Serialization failure | Có thể | Chạy lại toàn transaction với snapshot mới |
| Temporary connection error | Có điều kiện | Connection mới, giới hạn retries |
| Lock timeout | Có điều kiện | Backoff và kiểm soát contention |
| Optimistic conflict | Có điều kiện | Reload, giải quyết business conflict |
| Unique constraint | Thường không | Trả conflict hoặc xử lý idempotency |
| FK/NOT NULL/CHECK | Không tự động | Sửa dữ liệu/operation |
| Mapping/SQL syntax | Không | Sửa code/configuration |
| Authentication/permission | Không tự động | Sửa credentials/permissions |

Dùng SQLState/vendor error code và exception translation để phân loại. Không retry mọi RuntimeException hoặc PersistenceException.

## 45. Idempotency và uncertain commit outcome

Network failure quanh commit có thể khiến client không biết transaction đã commit hay chưa. Nếu retry một lệnh tạo mới không có idempotency key, có thể tạo duplicate.

Ví dụ bảng request ledger:

```sql
create table request_deduplication (
    request_key varchar(100) primary key,
    result_id bigint,
    created_at timestamp not null
);
```

Trong cùng transaction:

1. Insert request key.
2. Thực hiện operation.
3. Ghi result ID vào ledger.
4. Commit.

Khi retry cùng key, ứng dụng đọc ledger trong transaction mới và trả kết quả đã commit thay vì tạo operation lần nữa.

Test nên mô phỏng retry cùng key và xác nhận chỉ một reservation/order tồn tại. Unique key ở database là bảo vệ cuối khi hai requests đến đồng thời.

## 46. Side effects phải gắn với transaction outcome

Không gửi message/email/HTTP request trước khi database commit nếu side effect phải phản ánh dữ liệu đã commit.

Một flow nguy hiểm:

```text
Persist order
    |
Publish message
    |
Flush fails
    |
Database transaction rolls back
    |
Consumer already received message
```

Dùng transactional outbox hoặc after-commit event handling phù hợp. Outbox row được ghi trong cùng DB transaction với domain change; publisher đọc và gửi sau commit.

Test:

- Transaction rollback không để outbox row.
- Commit tạo đúng một outbox row.
- Publisher retry không gửi duplicate theo idempotency policy.
- Consumer xử lý idempotent.
- Không phát event cho transaction chưa commit.

## 47. Test recovery với batch import

Nếu cần partial success, xác định transaction boundary theo record hoặc chunk.

Ví dụ một record một transaction:

```java
for (ProductInput input : inputs) {
    try {
        transactionTemplate.executeWithoutResult(status -> {
            repository.save(map(input));
            repository.flush();
        });
        results.add(ImportResult.success(input.sku()));
    } catch (DataIntegrityViolationException ex) {
        results.add(ImportResult.failure(input.sku()));
    }
}
```

Exception được catch bên ngoài callback, sau khi TransactionTemplate đã rollback transaction lỗi. Lần tiếp theo dùng transaction mới.

Với chunk lớn, nếu một record làm chunk thất bại, có thể retry chunk mới hoặc chia nhỏ để cô lập row lỗi. Không tiếp tục dùng Session của chunk đã ném persistence exception.

## 48. JDBC batch và partial failure

Hibernate có thể gom statements thành JDBC batches. Khi batch execute lỗi, driver có thể báo update counts một phần, SUCCESS_NO_INFO hoặc EXECUTE_FAILED tùy driver.

Không suy ra mọi row trong batch đều rollback chỉ từ exception message. Transaction rollback mới xác định outcome của transaction, theo DBMS semantics.

Test với JDBC driver production-equivalent:

- Batch insert thành công.
- Một row vi phạm unique.
- Batch flush ném exception.
- Transaction rollback.
- Fresh connection xác nhận không có rows của transaction thất bại.
- Retry bằng transaction mới với input đã sửa.
- Xác nhận không duplicate.

## 49. Test lock recovery sau timeout/deadlock

Một test recovery cần kiểm tra cả trạng thái sau lỗi:

1. Transaction A giữ lock.
2. Transaction B yêu cầu lock và timeout.
3. B rollback/close.
4. A commit hoặc rollback và giải phóng lock.
5. Transaction C mới đọc row.
6. C có thể lấy lock và cập nhật bình thường.
7. Database invariant vẫn đúng.

Nếu Session B được giữ mở sau lock timeout, test phải chứng minh application không dùng lại nó. Mở EntityManager/Session mới cho attempt kế tiếp.

## 50. Test deadlock retry với giới hạn

Deadlock victim có thể được retry nếu operation idempotent và logic được tính lại.

Một policy ví dụ:

- Tối đa 3 attempts.
- Exponential backoff ngắn có jitter.
- Chỉ retry SQLState/vendor code được phân loại deadlock/serialization.
- Mỗi attempt transaction mới.
- Ghi attempt number và correlation ID.
- Không giữ connection trong lúc backoff.
- Sau lần cuối, trả lỗi có thể quan sát và alert.

Test nên inject/induce deadlock trong DBMS test container, xác nhận một transaction bị rollback, attempt mới có thể hoàn tất và không có duplicate rows. Không phụ thuộc DBMS luôn chọn cùng một transaction làm victim.

## 51. Test isolation với hai transactions thay vì một transaction test

Nhiều test framework tự bọc mỗi test trong một transaction rồi rollback cuối test. Cách này tiện cho cleanup nhưng không tự chứng minh hai transactions độc lập đã commit.

Để test locking/concurrency:

- Dùng hai EntityManagers/Connections.
- Mỗi worker có transaction riêng.
- Không để outer test transaction giữ lock hoặc fixture uncommitted.
- Commit fixture trước khi workers đọc.
- Đồng bộ bằng latches/barriers.
- Sau workers, đọc state trong transaction mới.
- Cleanup bằng transaction riêng hoặc container teardown.

Không chia sẻ injected EntityManager giữa threads.

## 52. Test transaction commit thật

Spring TransactionTemplate có thể điều khiển transaction:

```java
Long id = transactionTemplate.execute(status -> {
    InventoryItem item = new InventoryItem("SKU-1", 10);
    entityManager.persist(item);
    entityManager.flush();
    return item.getId();
});

// Callback kết thúc bình thường, transaction commit.
```

Sau đó đọc trong transaction mới:

```java
transactionTemplate.executeWithoutResult(status -> {
    entityManager.clear();

    InventoryItem reloaded =
        entityManager.find(InventoryItem.class, id);

    assertEquals(10, reloaded.getAvailable());
});
```

Nếu transaction template được gọi từ code không có outer transaction, callback tạo boundary độc lập theo cấu hình. Nếu có outer transaction, propagation của template quyết định tham gia hay tạo mới; xác nhận propagation trong test.

## 53. Test không dùng L1 để chứng minh persisted state

Một test:

```java
entityManager.persist(item);
entityManager.flush();

assertEquals(10, item.getAvailable());
```

Assertion chỉ đọc lại object đang managed. Nó không chứng minh database lưu đúng giá trị.

Làm mới context:

```java
entityManager.clear();

InventoryItem reloaded =
    entityManager.find(InventoryItem.class, item.getId());

assertEquals(10, reloaded.getAvailable());
```

Để chắc chắn database đã commit, thực hiện commit trước và đọc bằng transaction mới. Để chắc chắn không có L2 che giấu SQL, dùng JDBC assertion hoặc kiểm soát cache.

## 54. Kiểm tra số SQL của use case sau commit

SQL capture thường chỉ quan sát statements được gửi trong transaction hiện tại. Một phần SQL có thể phát khi commit/flush sau khi service method return.

Để đo đầy đủ:

- Bắt đầu capture trước khi gọi service.
- Giữ capture qua transaction interceptor commit.
- Kết thúc capture sau khi call đã return/throw.
- Bao gồm statements từ callbacks/listeners nếu chúng nằm trong cùng execution context.
- Tách SQL setup/fixture khỏi cửa sổ đo.
- Ghi rõ transaction boundaries.

Nếu capture chỉ nằm bên trong service method và dừng trước interceptor commit, có thể bỏ sót SQL flush cuối.

## 55. Kiểm tra SQL count cùng dữ liệu kết quả

Một query count thấp nhưng trả sai dữ liệu vẫn là lỗi. Một query count cao nhưng đúng có thể là regression performance.

Mỗi test nên kết hợp:

- SQL count/shape assertion.
- Returned result assertion.
- Persisted database state assertion.
- Constraint/lock outcome assertion nếu có.
- Transaction outcome assertion.

Ví dụ fetch plan:

1. Tạo 20 Orders với Lines.
2. Load page.
3. Duyệt các fields API thực sự cần.
4. Assert số SELECT nằm trong budget.
5. Assert 20 Orders và tổng Lines đúng.
6. Kiểm tra FK/soft-delete/tenant predicates nếu cần.

Không giảm query count bằng cách bỏ mất rows hoặc làm sai filter.

## 56. Kiểm tra query plan khi số SQL đã hợp lý

Một SELECT duy nhất vẫn có thể rất chậm do full table scan hoặc join explosion.

Khi SQL count đạt budget nhưng latency cao, xem:

- EXPLAIN/EXPLAIN ANALYZE phù hợp DBMS.
- Index usage.
- Rows estimated vs actual.
- Join order/cardinality.
- Sort/hash spills.
- Lock waits.
- Buffer/cache reads.
- Parameter selectivity.

Không hardcode cost estimate tuyệt đối trong CI nếu môi trường không ổn định. Có thể test index existence/schema và dùng performance suite riêng cho query plan/latency.

## 57. Test index và uniqueness

Một index có thể phục vụ cả query performance và uniqueness. Test cần xác nhận migration tạo đúng index, không chỉ entity annotation.

Kiểm tra:

- Unique index trên business key.
- Composite index theo tenant + key nếu cần.
- Index phục vụ FK joins.
- Index theo status/time cho pagination.
- Partial index cho active rows nếu DBMS hỗ trợ.
- Index columns/order phù hợp query predicate.

Nếu dùng PostgreSQL partial unique index cho active rows, test reuse key sau soft delete và restore conflict. Nếu dùng composite tenant key, test cùng business key ở hai tenants và uniqueness trong từng tenant.

## 58. Kiểm tra multi-tenant predicates và khóa

Nếu ứng dụng dùng shared tables, mọi query/update cần đúng tenant scope.

Một SQL count test có thể assert câu SELECT/UPDATE chứa tenant predicate, nhưng cần kiểm tra database state:

- Tenant A và B có rows cùng business ID/key theo policy.
- Request A không đọc/update/delete row B.
- Lock của tenant A không khóa nhầm row B nếu key design cho phép tách biệt.
- Unique constraint scope đúng tenant.
- Retry không bỏ mất tenant context.
- Cache keys không trộn tenant state.

Nếu tenant context nằm trong ThreadLocal, concurrency tests cần context propagation/cleanup rõ ràng. Không để thread pool tái sử dụng tenant context cũ.

## 59. Kiểm tra soft delete trong SQL budget

Soft delete có thể thêm predicate vào mọi SELECT:

```sql
select ...
from purchase_orders
where deleted = false
  and tenant_id = ?
```

Test nên xác nhận:

- Current queries lọc deleted rows.
- Admin/history query có quyền đọc deleted rows theo policy.
- Count query và page content query có cùng filter.
- Association loads tuân thủ visibility.
- Unique/index policy phù hợp.
- Soft delete phát UPDATE hoặc behavior provider mong đợi.
- Restore làm entity hiện lại theo contract.

Đừng chỉ kiểm tra service trả về list; query count và SQL predicates có thể cho thấy một repository path bỏ sót filter.

## 60. Kiểm tra cache invalidation sau write

Nếu L2/query cache bật:

1. Session A load entity và warm cache.
2. Transaction B update/delete/soft-delete.
3. B commit.
4. Session C mới load/query.
5. Assert dữ liệu mới và visibility đúng.
6. Kiểm tra L2/query cache metrics và SQL count.
7. Lặp với native SQL/bulk update nếu application có đường này.

Native/bulk paths có thể bypass Hibernate invalidation. Cần explicit eviction/refresh hoặc tránh cache những entities bị external writes.

SQL count test phải ghi cache state để tránh kết luận sai.

## 61. Failure injection cho database integration

Một bộ kiểm chứng recovery nên có các failure scenarios:

| Failure injection | Điều cần xác nhận |
|---|---|
| Unique constraint violation | Transaction rollback, không partial rows |
| FK violation | Không có orphan/inconsistent references |
| Optimistic conflict | Một writer thắng; loser reload/retry đúng |
| Lock timeout | Transaction thất bại kết thúc, lock được giải phóng |
| Deadlock | Victim rollback; retry transaction mới |
| Serialization failure | Retry toàn transaction |
| Connection loss | Session/connection bị discard |
| Query timeout | Không tiếp tục unit of work lỗi |
| Batch failure | Transaction rollback; rows cuối đúng |
| External side effect failure | Outbox/retry không duplicate |

Chỉ inject trong test environment. Không kill database production hoặc làm gián đoạn shared environment để kiểm thử recovery.

## 62. Kiểm tra rollback và không có partial writes

Một use case ghi nhiều bảng:

```text
Create Order
  +-- insert purchase_order
  +-- insert order_lines
  +-- update inventory
  +-- insert outbox_event
```

Nếu update inventory thất bại, transaction cần rollback toàn bộ writes cùng transaction.

Test:

1. Tạo fixture và commit.
2. Gọi use case gây failure sau một số SQL đã chạy.
3. Xác nhận exception propagate/rollback.
4. Mở transaction mới.
5. Kiểm tra không có Order mới.
6. Kiểm tra không có OrderLines mới.
7. Kiểm tra inventory không đổi.
8. Kiểm tra không có outbox row.
9. Xác nhận dữ liệu trước transaction vẫn nguyên vẹn.

Đây là test atomicity quan trọng hơn chỉ assert exception type.

## 63. Kiểm tra transaction state sau lỗi

Sau failure, cần xác nhận:

- Transaction cũ đã rollback hoặc được transaction manager kết thúc.
- Session cũ đã đóng/discard hoặc được framework kết thúc.
- Không có query tiếp theo trên persistence context đã lỗi.
- Lần thử mới có transaction/persistence context mới.
- Không còn connection bị giữ bởi code.
- Lock được giải phóng.
- Connection pool không bị cạn.
- Error response/report phản ánh kết quả thực.

Một test recovery nên đọc database state bằng connection mới và có thể kiểm tra pool metrics nếu lỗi có nguy cơ leak.

## 64. Connection pool và resource recovery

Sau exception hoặc network failure, connection có thể bị invalid. Connection pool/driver cần nhận biết và loại connection lỗi theo cấu hình.

Kiểm tra:

- Connection acquisition timeout.
- Validation/keepalive settings phù hợp.
- Leak detection.
- Active/idle/pending connection metrics.
- Pool behavior khi DB restart/failover.
- Transaction timeout.
- Connection close sau rollback failure.
- Không giữ connection trong backoff/retry.

Đừng tự giữ JDBC connection để retry sau khi Hibernate Session đã lỗi. Mở transaction mới để pool cấp connection hợp lệ.

## 65. Kiểm tra commit outcome không chắc chắn

Nếu client mất kết nối ngay lúc commit, ứng dụng có thể không biết database đã commit hay chưa. Một test không thể giả định mọi network error đều có nghĩa rollback.

Thiết kế:

- Mỗi command có idempotency key.
- Ghi key và business result trong cùng transaction.
- Retry dùng key cũ.
- Nếu key tồn tại, đọc kết quả đã commit.
- Nếu key chưa tồn tại, thực hiện operation mới theo policy.
- Unique constraint bảo vệ khi hai retries chạy đồng thời.

Test failure injection quanh commit cần xác nhận không tạo duplicate và có thể reconcile outcome. Đây là recovery requirement riêng, không chỉ là retry SQL.

## 66. Không dùng một transaction test rollback để kiểm tra after-commit behavior

Nhiều Spring test slices tự mở transaction và rollback cuối test. Điều này tiện cleanup nhưng không chứng minh:

- Transaction đã commit thật.
- After-commit listeners đã chạy.
- Outbox publisher nhìn thấy row đã commit.
- Deferred constraints đã được kiểm tra.
- Một transaction mới có thể đọc dữ liệu.

Dùng TransactionTemplate/programmatic transaction để commit thật và đọc trong transaction mới khi cần. Cleanup bằng transaction riêng hoặc container teardown.

## 67. Test Envers/audit khi persistence thất bại

Nếu entity có Envers hoặc audit listener:

- Successful persist/update tạo revisions theo policy.
- Failed transaction không để lại committed audit rows.
- Rollback sau flush loại bỏ audit writes cùng transaction.
- Native/bulk paths được nhận diện là có thể bypass Envers.
- Revision metadata actor/correlation ID đúng.
- Một transaction nhiều entity changes có revision semantics đúng.

Đừng chỉ assert revision count trong cùng transaction chưa commit. Đọc audit history sau commit/rollback bằng context mới.

## 68. Test locking với database constraints và affected rows

Một số use cases dùng atomic SQL update thay vì load-modify-save. Khi đó affected row count là evidence quan trọng:

```java
int changed = jdbcTemplate.update(
    """
    update inventory_items
       set available = available - ?
     where id = ?
       and available >= ?
    """,
    quantity,
    itemId,
    quantity
);

assertEquals(1, changed);
```

Nếu changed = 0, có thể row không tồn tại hoặc quantity không đủ; domain phải phân biệt nếu cần bằng một read trong transaction mới hoặc query phù hợp.

Khi concurrency, hai requests cùng cập nhật, tổng affected rows và database value cuối phải giữ invariant. Dùng constraint/locking strategy được xác định rõ.

## 69. Không để test query count bị phụ thuộc order

SQL count có thể thay đổi do:

- Test chạy song song.
- Shared SessionFactory Statistics.
- Cache warm từ test trước.
- Data fixture khác kích thước.
- Auto-flush.
- Lazy loading từ assertion/toString/JSON.
- Logging hoặc listeners query thêm.
- ORM version/Dialect khác.

Để ổn định:

- Mỗi test tạo fixture riêng.
- Reset/cô lập collector, không reset global production counters tùy tiện.
- Mở Session mới.
- Kiểm soát L2/query cache.
- Bắt đầu capture sau setup.
- Dừng capture sau commit.
- Không chạy tests dùng cùng counter đồng thời.
- Assert budget và SQL behavior cần thiết, tránh exact count quá mong manh.

## 70. Test lazy loading trong khi đo SQL

Một assertion đọc tên Customer qua association có thể trigger lazy SELECT. Logging entity toString() cũng có thể trigger associations nếu toString dereference fields.

Khi test query count:

- Duyệt đúng fields mà endpoint/service cần.
- Không để assertion vô tình tải graph khác với production.
- Không serialize entity toàn bộ nếu API dùng DTO.
- Capture SQL trước khi truy cập associations.
- Assert cả số SELECT và dữ liệu DTO cuối.

Đo use case thực tế, không chỉ repository method cô lập nếu bottleneck xảy ra ở service/serialization layer.

## 71. Kiểm tra pagination và count queries

Một endpoint page thường chạy content SELECT và count SELECT. Nếu fetch join collection với pagination, Hibernate có thể phát cảnh báo, thực hiện pagination in memory hoặc tạo query khác tùy mapping/version.

Test:

- Content rows đúng page/ordering.
- Total count đúng.
- SQL có pagination tại DB nếu đó là yêu cầu.
- Không tải toàn bộ collection không cần thiết.
- Không có N+1 khi map DTO.
- Số SELECT ổn định theo page size.
- Query plan có index phù hợp.

Không chỉ assert response có 20 items; kiểm tra SQL để chắc database thực hiện pagination đúng cách.

## 72. Kiểm tra batch fetch và N+1 tradeoff

Hibernate có thể dùng batch fetching hoặc subselect fetching để giảm N+1. Nhưng một batch size có thể tạo nhiều query hơn khi dataset lớn hoặc cache state khác.

Test với nhiều sizes:

| Parents | Expected behavior |
|---:|---|
| 1 | Baseline |
| 10 | Không tăng tuyến tính một SELECT mỗi parent |
| 50 | Query count vẫn nằm trong budget |
| 200 | Không tạo memory/query regression |

Không ép một exact count duy nhất cho mọi Hibernate version nếu fetch strategy có thể thay đổi. Dùng upper bound có cơ sở và kiểm tra query shape/dữ liệu đầy đủ.

## 73. Kiểm tra SQL count của writes

Một aggregate persist có thể phát:

- INSERT parent.
- INSERT children.
- INSERT join table rows.
- UPDATE foreign keys nếu mapping/action ordering cần.
- Audit table writes.
- Outbox rows.
- Sequence fetches.

Viết expected statement budget theo mapping và generator strategy. Sequence-based IDs có thể phát thêm sequence statements; identity generation có thể buộc INSERT sớm và ảnh hưởng batching.

Khi nâng Hibernate hoặc đổi ID generator, cập nhật expectation dựa trên behavior cần thiết, không chỉ sửa số test để pass mà không hiểu SQL mới.

## 74. Đo batch insert/update và flush boundaries

Với dữ liệu lớn, có thể flush/clear theo chunk để giới hạn persistence context:

```java
for (int i = 0; i < items.size(); i++) {
    entityManager.persist(items.get(i));

    if ((i + 1) % 50 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
```

Đây là optimization cho batch lớn, nhưng nếu một flush ném persistence exception thì transaction hiện tại thất bại. Không catch rồi tiếp tục vòng lặp với cùng transaction/Session.

Nếu partial success là yêu cầu, mỗi chunk cần transaction boundary riêng. Nếu toàn bộ batch atomic, một lỗi phải rollback toàn batch theo policy.

## 75. Kiểm tra khóa khi delete/update

Locking không chỉ áp dụng cho reads:

- Update entity có @Version kiểm tra version.
- Pessimistic lock có thể serialize read-modify-write.
- Delete có thể cần version predicate.
- FK constraints có thể tạo lock interactions.
- Soft delete thường là UPDATE và có thể cần version check.
- Bulk update/delete có thể bypass entity-level version semantics nếu không viết predicate/increment phù hợp.

Test update/delete đồng thời với hai transactions và xác nhận một operation conflict đúng policy. Đừng giả định soft delete là “chỉ đổi boolean” nên không cần locking.

## 76. Kiểm tra lock scope và query behavior

Một query dùng pessimistic lock có thể khóa các rows được chọn và có thể ảnh hưởng joined tables tùy dialect/lock scope.

Test cần xác định:

- Rows nào được lock.
- Có lock associations/joined tables không?
- Pagination có tương thích lock không?
- Query timeout/lock timeout được áp dụng không?
- Lock được giải phóng khi commit/rollback?
- Một transaction đọc không lock có bị block không?
- DBMS có hỗ trợ lock mode/hint đã chọn không?

Đừng suy ra lock scope chỉ từ LockModeType trên source code. Dùng SQL capture và hai-connection integration test.

## 77. Kiểm tra tenant, cache và SQL count cùng nhau

Một query có thể đạt SQL budget nhưng thiếu tenant predicate, trả dữ liệu sai. Một cache hit có thể giảm SQL nhưng trả entity của tenant khác nếu cache key/isolation sai.

Test cùng IDs ở hai tenants:

1. Tenant A tạo row.
2. Tenant B tạo row có ID/business key tương ứng theo schema strategy.
3. Mở Session mới trong từng tenant.
4. Warm cache A rồi đọc B.
5. Update/delete ở A.
6. Xác nhận B không bị ảnh hưởng.
7. Capture SQL và xác nhận tenant scope.
8. Kiểm tra database rows và cache metrics.

Correctness/security phải ưu tiên hơn query count. Không chấp nhận SQL budget tốt nếu predicate hoặc cache isolation sai.

## 78. Bộ báo cáo kiểm chứng cho mỗi use case

Một report có thể dùng mẫu:

```text
Use case:
  reserve inventory

Environment:
  Hibernate:
  JDK:
  Database:
  JDBC driver:
  Cache:
  Isolation:

Fixture:
  inventory available:
  concurrent requests:
  tenant count:

SQL:
  Hibernate prepared statement delta:
  JDBC execute count:
  batch executions:
  SELECT / INSERT / UPDATE / DELETE:
  query shape notes:

Persisted state:
  rows inserted:
  rows updated:
  FK/unique/check constraints:
  committed values:

Locks:
  lock mode:
  version before/after:
  lock wait/timeout:
  conflict outcome:

Recovery:
  failure injected:
  rollback result:
  retry attempts:
  idempotency result:
  outbox/audit rows:

Decision:
  pass/fail:
  regression:
  follow-up:
```

Report phải ghi rõ instrumentation layer. Không so sánh JDBC execute count với Hibernate prepared statement count như thể chúng cùng định nghĩa.

## 79. Một ma trận kiểm thử tích hợp đề xuất

| Nhóm | Kịch bản | Assertion chính |
|---|---|---|
| SQL count | Load page với associations | SELECT nằm trong budget, không N+1 |
| SQL shape | Tenant/soft-delete query | Có predicates đúng |
| Writes | Persist aggregate | INSERT/FK/rows đúng |
| Flush | Constraint violation | Exception xuất hiện ở flush/commit như dự kiến |
| Commit | Fresh transaction read | Dữ liệu đã commit đúng |
| Rollback | Failure giữa aggregate writes | Không partial rows |
| Unique | Hai requests cùng key | Chỉ một row được commit |
| Optimistic lock | Hai writers cùng version | Một writer conflict |
| Pessimistic lock | Hai transactions cùng row | Wait/timeout theo policy |
| Deadlock | Lock order đảo ngược | Victim rollback, invariant giữ |
| Retry | Transient failure | Transaction/session mới, bounded attempts |
| Idempotency | Retry cùng request key | Không duplicate |
| Batch | Một row lỗi | Partial/all-or-nothing đúng policy |
| Cache | Warm rồi update/delete | Không stale reads |
| Envers | Commit/rollback | History chỉ phản ánh committed changes |
| Multi-tenant | Same IDs | Không lẫn dữ liệu |
| Migration | Database trống | Schema/constraints đúng |

Không cần chạy mọi tổ hợp cho mọi entity. Chọn các use cases rủi ro cao và invariants quan trọng nhất.

## 80. Pipeline CI cho bộ kiểm chứng

Một pipeline có thể chia thành các lớp:

```text
Compile + static checks
        |
        v
Unit tests (domain rules)
        |
        v
Database integration tests
  - migrations
  - SQL budgets
  - persisted state
  - constraints
        |
        v
Concurrency/recovery tests
  - optimistic/pessimistic locks
  - deadlock/timeout
  - retry/idempotency
        |
        v
Performance suite
  - query plans
  - latency percentiles
  - batch throughput
        |
        v
Artifact/report
```

SQL-count và persisted-state tests có thể chạy thường xuyên trong CI. Deadlock/network failure tests có thể chạy trong một integration profile riêng nếu cần nhiều tài nguyên hoặc DBMS-specific setup.

Không để performance test timing-sensitive làm flaky unit test suite. Tách correctness assertions khỏi benchmark thresholds.

## 81. Phân biệt correctness gate và performance gate

**Correctness gate** nên có kết quả xác định:

- Không có duplicate business key.
- Available không âm.
- FK hợp lệ.
- Failed transaction không để partial rows.
- Optimistic conflict được phát hiện.
- Retry không tạo duplicate.
- Tenant isolation đúng.
- Audit/outbox semantics đúng.

**Performance gate** thường cần tolerance:

- SQL count không vượt budget.
- N+1 không xuất hiện.
- p95/p99 nằm trong target trên môi trường benchmark ổn định.
- Batch size/throughput hợp lý.
- Lock wait không vượt policy.
- DB connection pool không bị cạn.

Không hạ correctness gate để đổi lấy performance. Một use case nhanh nhưng ghi sai dữ liệu là failure.

## 82. Khi SQL count tăng sau Hibernate upgrade

Điều tra theo thứ tự:

1. So sánh Hibernate core/Dialect/JDBC driver versions.
2. So sánh SQL capture trước và sau.
3. Xác định statement mới là SELECT, sequence, audit hay batch.
4. Kiểm tra fetch plan, eager associations và auto-flush.
5. Kiểm tra L1/L2/query cache state.
6. Kiểm tra enhancement/proxy/lazy loading behavior.
7. Kiểm tra ID generator và batching.
8. Kiểm tra framework listeners/callbacks.
9. Xác nhận fixture và transaction boundary giống nhau.
10. Chỉ điều chỉnh budget sau khi hiểu nguyên nhân.

Không xóa assertion query count chỉ vì upgrade làm test fail. Query budget là tín hiệu giúp phát hiện thay đổi behavior.

## 83. Khi persisted state khác object trong memory

Nếu object trả về đúng nhưng database row sai:

- Kiểm tra transaction có commit không.
- Kiểm tra merge trả managed object khác object đầu vào.
- Kiểm tra owning side và FK.
- Kiểm tra flush/clear/reload.
- Kiểm tra trigger/generated columns.
- Kiểm tra bulk/native updates bypass persistence context.
- Kiểm tra L2 cache stale.
- Kiểm tra transaction isolation và read replica.
- Kiểm tra tenant/schema routing.
- Kiểm tra rollback-only hoặc commit failure.

Đọc row bằng JDBC trong transaction mới để phân biệt ORM view với physical state.

## 84. Khi lock test bị flaky

Nguyên nhân thường gặp:

- Hai workers không thật sự dùng hai transactions/connections.
- Một transaction đã commit trước khi worker kia load.
- Latch đặt sai vị trí.
- Timeout quá ngắn so với CI.
- Connection pool không đủ connections.
- Outer test transaction giữ lock ngoài dự kiến.
- DBMS chọn deadlock victim khác nhau.
- Test dựa vào sleep hoặc scheduling order.

Đặt barriers sau khi cả hai transactions đã load state hoặc sau khi A xác nhận lock đã lấy. Ghi transaction IDs, thread IDs và DB lock diagnostics nếu cần. Luôn có timeout/finally để giải phóng resources.

## 85. Khi retry tạo duplicate hoặc mất dữ liệu

Kiểm tra:

- Retry có chạy cùng Session/transaction không?
- Attempt đầu đã commit nhưng response bị mất?
- Idempotency key có unique constraint không?
- Retry có dùng key mới ngoài ý muốn?
- Entity detached từ attempt cũ có được merge lại không?
- Business state có được reload và tính lại không?
- External side effect có phát trước commit không?
- Outbox consumer có idempotent không?
- Transaction propagation có thực sự REQUIRES_NEW không?
- Self-invocation có bỏ qua Spring proxy không?

Retry chỉ an toàn khi transaction boundary, idempotency và uncertain commit handling được thiết kế cùng nhau.

## 86. Nguyên tắc bảo trì bộ kiểm chứng

- Giữ SQL collector tách khỏi business code.
- Gắn metrics với test/request scope, không reset global counters tùy tiện.
- Ghi rõ instrumentation layer và cache state.
- Dùng DBMS production-equivalent cho constraints/locks.
- Tạo fixture có commit rõ ràng khi test concurrency.
- Không chia sẻ EntityManager/Session giữa threads.
- Flush/clear/reload khi kiểm tra ORM state; fresh transaction khi kiểm tra commit.
- Đọc database rows bằng JDBC cho assertions physical state.
- Assert invariants và SQL budgets có ý nghĩa, tránh exact SQL formatting mong manh.
- Sau persistence exception, rollback và discard Session.
- Retry toàn transaction bằng persistence context mới.
- Dùng idempotency cho uncertain outcomes.
- Kiểm tra side effects bằng outbox/after-commit semantics.
- Giữ correctness gates độc lập với performance gates.
- Ghi environment/version để so sánh kết quả giữa CI và production-like tests.

## 87. Kết luận

Một bộ kiểm chứng persistence hoàn chỉnh phải nối được SQL đã chạy với dữ liệu thực sự commit, concurrency outcomes và khả năng phục hồi khi có lỗi.

1. **Số SQL:** đo ở đúng tầng, dùng Hibernate Statistics cho ORM metrics và JDBC instrumentation cho execute/batch counts; kiểm thử N+1, fetch plans và SQL budgets.
2. **Dữ liệu lưu:** phân biệt persist, flush và commit; clear L1, đọc trong transaction mới và dùng JDBC để xác nhận rows, columns, foreign keys và constraints.
3. **Khóa:** dùng hai transactions/EntityManagers độc lập để kiểm tra optimistic version conflicts, pessimistic locks, timeouts và deadlocks; đồng bộ tests bằng barriers/latches.
4. **Khả năng phục hồi:** inject constraint/lock/connection failures, xác nhận rollback không để partial writes, discard Session sau persistence exception và retry toàn unit of work bằng transaction mới.
5. **Idempotency:** xử lý uncertain commit outcome bằng request key/unique constraint và kiểm tra retry không tạo duplicate.
6. **Tính nhất quán:** test cache invalidation, Envers, outbox, tenant isolation và migrations khi chúng tham gia persistence path.
7. **CI:** tách correctness gates khỏi performance gates, dùng DBMS production-equivalent và lưu lại environment/instrumentation để kết quả có thể tái hiện.

Khi một test chỉ nói “method không ném lỗi”, nó chưa cho biết database đã làm gì. Khi bộ kiểm chứng ghi được SQL, xác nhận committed rows, mô phỏng transactions cạnh tranh và chứng minh rollback/retry giữ invariant, nhóm phát triển mới có evidence đủ mạnh để thay đổi mapping, fetch plan, locking hoặc Hibernate version mà vẫn kiểm soát được dữ liệu.
