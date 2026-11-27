# When Should You Combine Spring Data JDBC with MyBatis?

Spring Data JDBC and MyBatis both help Java applications work with relational databases, but they solve problems at two different levels. Spring Data JDBC focuses on **aggregate** persistence: mapping domain objects, saving aggregate roots along with their owned components, and supporting rules such as optimistic locking and lifecycle callbacks. MyBatis focuses on **developer-controlled SQL**: mapper methods, XML queries, dynamic SQL, stored procedures, and mapping results into DTOs.

An application can use both if each tool handles the appropriate part of the work. A common pattern is having Spring Data JDBC manage writes and the aggregate lifecycle, while MyBatis serves reporting queries, complex joins, or integration with legacy SQL. Both tools can also participate in the same transaction if configured to share Spring's DataSource and transaction manager.

The important thing is to clearly define who owns each read/write path. If both frameworks update the same aggregate without agreeing on invariants, versioning, auditing, and caching, the application can produce inconsistent data even though every individual SQL statement executes successfully.

## 1. The Role of Each Tool

### 1.1. Spring Data JDBC Manages Aggregates

Spring Data JDBC organizes persistence around the aggregate root. Repositories provide CRUD operations, query derivation, and custom SQL via `@Query`. When saving an aggregate with `repository.save(root)`, the framework understands the aggregate mapping and synchronizes owned parts according to the Spring Data JDBC model.

Example:

```java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    private String orderNumber;
    private OrderStatus status;

    @Version
    private Long version;

    public void confirm() {
        if (status != OrderStatus.PENDING) {
            throw new IllegalStateException(
                "Only PENDING orders can be confirmed"
            );
        }
        status = OrderStatus.CONFIRMED;
    }

    // Constructor and accessors matching the mapping.
}
```

Repository:

```java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

A service can load the aggregate, invoke domain behavior, and then save it:

```java
@Transactional
public void confirm(Long orderId) {
    PurchaseOrder order = orders.findById(orderId)
        .orElseThrow();

    order.confirm();
    orders.save(order);
}
```

This persistence path is appropriate when you need to protect aggregate invariants and let Spring Data JDBC manage the corresponding mapping, version, and lifecycle.

### 1.2. MyBatis Controls SQL and Result Mapping

MyBatis lets you write SQL directly in annotations or XML mappers. It fits well when queries have complex structures, require multi-table joins, window functions, CTEs, stored procedures, or mapping results into a separate read model.

For example, a report needing customer name, order count, and total amount:

```sql
SELECT
    c.id AS customer_id,
    c.name AS customer_name,
    COUNT(o.id) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS total_amount
FROM customers c
LEFT JOIN purchase_orders o
    ON o.customer_id = c.id
GROUP BY c.id, c.name
ORDER BY total_amount DESC;
```

This is a reporting query that can be written with a MyBatis mapper and return a DTO. There is no need to instantiate the entire customer aggregate along with all orders just to display a single summary row.

### 1.3. Role Allocation Table

| Need | Spring Data JDBC | MyBatis |
| --- | --- | --- |
| Aggregate root CRUD | Well suited, with repository abstraction | Possible via mappers, but requires managing many details manually |
| Synchronizing collections belonging to an aggregate | Has aggregate mapping/persistence semantics | Requires writing SQL manually for each operation |
| Simple derived queries | Well suited | Possible to write, but usually requires more configuration |
| Complex SQL joins/reports | Usable with custom SQL, though aggregate mapping is not always ideal | Well suited for mappers/DTOs |
| Multi-branch dynamic SQL | May require custom repositories | Supports dynamic SQL in XML/annotations |
| Stored procedures and legacy SQL | Can be called via JDBC/custom code | Convenient mapper support |
| Aggregate lifecycle callbacks/auditing | Available on supported aggregate save/delete paths | Does not automatically run Spring Data JDBC lifecycle callbacks |
| Fine-grained control over every SQL statement | Available via queries/custom repositories | Core focus of MyBatis |

There is no rule requiring every application to use both. If Spring Data JDBC already satisfies the application's query and persistence needs, adding MyBatis increases dependencies, configuration, and the number of data-access styles to maintain.

## 2. Situations Where Combining Makes Sense

### 2.1. Aggregate Writes, Reporting Reads

This is a common combination pattern:

- Spring Data JDBC writes and manages aggregates according to the domain model.
- MyBatis reads data via joins, aggregate functions, and DTO projections.
- Both sides use the same schema and can share transaction infrastructure when needed.

Example sales application:

```text
                    Application Service
                            |
               +------------+------------+
               |                         |
       Spring Data JDBC                MyBatis
       Aggregate write              Reporting read
               |                         |
               +------------+------------+
                            |
                       DataSource
                            |
                         Database
```

Reporting DTO:

```java
public class OrderSummary {

    private Long orderId;
    private String orderNumber;
    private String customerName;
    private BigDecimal totalAmount;

    public OrderSummary() {
    }

    public Long getOrderId() {
        return orderId;
    }

    public void setOrderId(Long orderId) {
        this.orderId = orderId;
    }

    public String getOrderNumber() {
        return orderNumber;
    }

    public void setOrderNumber(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public String getCustomerName() {
        return customerName;
    }

    public void setCustomerName(String customerName) {
        this.customerName = customerName;
    }

    public BigDecimal getTotalAmount() {
        return totalAmount;
    }

    public void setTotalAmount(BigDecimal totalAmount) {
        this.totalAmount = totalAmount;
    }
}
```

MyBatis mapper:

```java
@Mapper
public interface OrderReportMapper {

    @Select("""
        SELECT
            o.id AS order_id,
            o.order_number,
            c.name AS customer_name,
            o.total_amount
        FROM purchase_orders o
        JOIN customers c ON c.id = o.customer_id
        WHERE o.status = #{status}
        ORDER BY o.created_at DESC, o.id DESC
        """)
    List<OrderSummary> findSummaries(
        @Param("status") String status
    );
}
```

Service calling the mapper to fetch the read model:

```java
@Service
public class OrderReportService {

    private final OrderReportMapper reports;

    public OrderReportService(OrderReportMapper reports) {
        this.reports = reports;
    }

    @Transactional(readOnly = true)
    public List<OrderSummary> findConfirmedOrders() {
        return reports.findSummaries("CONFIRMED");
    }
}
```

The DTO only contains the columns needed for the screen/report. It is not an aggregate and should not be passed back into `PurchaseOrderRepository.save`.

### 2.2. Complex or Database-Specific Queries

Consider MyBatis when queries require:

- Common Table Expressions (CTEs), recursive queries, or window functions.
- Multiple JOINs and aggregations with a projection shape different from the domain model.
- Dynamic WHERE, ORDER BY, or complex optional criteria.
- Stored procedures or database-specific functions.
- Legacy SQL that has already been tuned and needs to be preserved as-is.
- Mapping results into DTOs, records, or reporting structures.

Spring Data JDBC still provides `@Query` and custom repositories, so a single simple SELECT statement is not enough reason to add MyBatis. MyBatis is worth considering when the volume of specialized SQL and mapping control needs becomes a significant part of the persistence layer.

### 2.3. Batch or Controlled SQL Operations

MyBatis can fit batch inserts/updates, imports, or operations on technical tables without loading full aggregates. However, direct SQL on aggregate tables can bypass domain behavior and Spring Data JDBC's lifecycle.

If a batch modifies data belonging to an aggregate, decide clearly how to preserve invariants, versions, auditing, and synchronization of child tables. Do not treat batch mappers as a harmless shortcut for every write operation.

### 2.4. Legacy System Integration

A system may already have XML mappers, stored procedures, or long-standing SQL conventions. You do not necessarily have to rewrite all of that SQL to start using Spring Data JDBC for a new part of the domain.

You can let MyBatis continue managing legacy queries within a well-defined scope while using Spring Data JDBC for new aggregates. When doing so, specify which tables and operations belong to each persistence path to avoid two places writing the same data without a shared contract.

## 3. When You Don't Need to Add MyBatis

Do not add MyBatis just to use another SQL framework. The following cases usually do not need it:

- Repositories only need basic CRUD.
- Queries can be expressed concisely with query derivation.
- A few custom SQL statements can be managed well with `@Query`.
- The application does not have complex read/reporting queries.
- The team has no need to maintain additional XML mappers, type handlers, and configuration.

Example:

```java
List<PurchaseOrder> findByStatus(OrderStatus status);

Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
```

Simple queries like these fit Spring Data JDBC well. Creating a MyBatis mapper for each method only adds more abstractions without commensurate benefit.

## 4. Dividing Data Ownership and Write Paths

This is the most important decision when two tools access the same database.

An easy-to-maintain convention is:

| Data part | Write-owning tool | Tool that may read |
| --- | --- | --- |
| Purchase order aggregate | Spring Data JDBC | MyBatis for reports/read models |
| Customer aggregate | Spring Data JDBC | MyBatis for reports/read models |
| Dedicated reporting/projection tables | MyBatis or dedicated pipeline | MyBatis |
| Outbox/integration table | Clearly designated repository or mapper | Worker/mapper |
| Unmigrated legacy tables | MyBatis per current ownership | MyBatis; Spring Data JDBC only when a migration plan exists |

MyBatis can read aggregate tables managed by Spring Data JDBC. However, if MyBatis updates aggregate tables directly, it does not automatically invoke domain methods, synchronize aggregate children, or trigger Spring Data JDBC lifecycle callbacks.

### 4.1. Why Shouldn't You Have Arbitrary Dual Write Paths?

Suppose an aggregate has the following rules:

- An order can only be confirmed when it is PENDING.
- Confirming must record the confirmation timestamp.
- The version increments to detect concurrent updates.
- Certain child rows must be synchronized along with the aggregate.

If a mapper executes:

```sql
UPDATE purchase_orders
SET status = 'CONFIRMED'
WHERE id = #{id};
```

then the SQL only changes the status column. It does not invoke `order.confirm()`, does not check other invariants, and does not automatically apply the optimistic locking mechanism that Spring Data JDBC uses when saving an aggregate with `@Version`.

If a direct update is truly necessary, all conditions and side effects must be explicitly expressed in the SQL/transaction—for example, checking the previous status, incrementing the version, updating audit fields, and checking the row count. Afterward, any previously loaded aggregate must be reloaded before continuing to use or save it.

### 4.2. A MyBatis Read Model Is Not an Aggregate

A DTO built by MyBatis from a JOIN can contain fields taken from multiple aggregates. It serves a specific read purpose and does not necessarily carry the invariants or identity of a domain aggregate.

Do not take a reporting DTO and convert it into a Spring Data JDBC entity to save. When business state needs to change, load the aggregate root via its repository, invoke domain behavior, and save through the designated write path.

## 5. Configuring MyBatis Alongside Spring Data JDBC

The application needs dependencies compatible with the version of Spring Boot in use:

- Spring Boot starter for Spring Data JDBC.
- MyBatis Spring Boot Starter.
- JDBC driver for the database.
- Flyway or Liquibase if the application uses versioned schema migrations.

Do not pick starter versions independently while ignoring the Spring Boot/MyBatis compatibility matrix. Use dependency management/BOM appropriate for the project's platform.

### 5.1. Package Structure

Example:

```text
com.example.shop
├── ShopApplication.java
├── domain
│   └── PurchaseOrder.java
├── repository
│   └── PurchaseOrderRepository.java
├── persistence
│   └── mybatis
│       ├── OrderReportMapper.java
│       └── OrderReportMapper.xml
└── service
    └── OrderService.java
```

Mappers can be marked with `@Mapper` or discovered via `@MapperScan`:

```java
@SpringBootApplication
@MapperScan("com.example.shop.persistence.mybatis")
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

If `@MapperScan` is used for a package, mappers inside that package do not need to repeat `@Mapper`. Choose one clear approach and avoid unnecessary duplicate scanning.

### 5.2. MyBatis Configuration

Example:

```yaml
mybatis:
  mapper-locations: classpath:/mapper/**/*.xml
  type-aliases-package: com.example.shop.persistence.mybatis.dto
  configuration:
    map-underscore-to-camel-case: true
    local-cache-scope: STATEMENT
```

Meaning:

- `mapper-locations` specifies where XML mappers are located.
- `type-aliases-package` specifies the package containing types used in XML mappers.
- `map-underscore-to-camel-case` maps columns like `customer_name` to properties like `customerName`.
- `local-cache-scope` adjusts the scope of MyBatis SqlSession's local cache.

This is a configuration example; exact properties must match the MyBatis starter version. If mappers use annotations exclusively, no XML location configuration is needed.

### 5.3. One Shared DataSource

In a typical configuration, Spring Boot creates a single DataSource used by both Spring Data JDBC and MyBatis auto-configuration. MyBatis-Spring uses `SqlSessionTemplate` to manage SqlSessions and participate in Spring transactions.

There is no need to open sessions or commit manually in mappers. Let Spring manage session lifecycles and transactions.

If the application declares multiple DataSources, explicitly specify which mapper uses which SqlSessionFactory/DataSource and which JDBC repository uses which DataSource. Two DataSources having the same JDBC URL does not mean they are the same transaction resource.

## 6. Sharing Transactions Between Spring Data JDBC and MyBatis

Both frameworks can participate in the same local transaction if:

1. They use the same DataSource bean.
2. The transaction manager manages that exact DataSource.
3. MyBatis is integrated via MyBatis-Spring, typically using `SqlSessionTemplate`.
4. Repositories and mappers are invoked within the same Spring transaction context.

Example of a service saving an aggregate and then writing an outbox row with MyBatis:

```java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final OutboxMapper outbox;

    public OrderApplicationService(
        PurchaseOrderRepository orders,
        OutboxMapper outbox
    ) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public Long placeOrder(PlaceOrderCommand command) {
        PurchaseOrder order = PurchaseOrder.create(command);
        PurchaseOrder saved = orders.save(order);

        outbox.insert(
            "ORDER_PLACED",
            saved.getId().toString(),
            command.toEventPayload()
        );

        return saved.getId();
    }
}
```

MyBatis mapper:

```java
@Mapper
public interface OutboxMapper {

    @Insert("""
        INSERT INTO outbox_events
            (event_type, aggregate_id, payload, created_at)
        VALUES
            (#{eventType}, #{aggregateId}, #{payload}, CURRENT_TIMESTAMP)
        """)
    int insert(
        @Param("eventType") String eventType,
        @Param("aggregateId") String aggregateId,
        @Param("payload") String payload
    );
}
```

If inserting into the outbox fails and an exception escapes the method, the transaction can roll back both saving the order and inserting the outbox row. This is the benefit of having both tools participate in a single database transaction.

The outbox table is a separate table managed by the MyBatis mapper in this example. A worker reads and publishes events after the transaction commits; do not send messages directly to a broker inside a transaction callback assuming a database rollback can retract the message.

### 6.1. Do Not Call Commit or Rollback Manually

When using MyBatis-Spring, do not call `SqlSession.commit()`, `rollback()`, or close the session manually for ordinary mapper calls. `SqlSessionTemplate` manages the session according to the Spring transaction and synchronizes commit/rollback with the transaction manager.

Manually opening a `SqlSession` via `SqlSessionFactory.openSession()` and committing manually can create an independent transaction, breaking the atomicity the service expects.

### 6.2. What Happens If Two DataSources Are Used?

A standard `PlatformTransactionManager` manages a single local transaction resource. If Spring Data JDBC uses DataSource A and MyBatis uses DataSource B, `@Transactional` bound to A's manager will not automatically commit/roll back B's transaction at the same time.

If both databases must change atomically, use an appropriate distributed transaction solution or redesign the use case with outbox/saga and handle eventual consistency. Do not assume a plain `@Transactional` annotation automatically spans multiple databases.

### 6.3. Read-Only Transactions

You can use `@Transactional(readOnly = true)` when a service only reads through both repositories and mappers:

```java
@Transactional(readOnly = true)
public OrderDetailsView loadOrder(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    List<OrderLineView> lines = reports.findLines(id);

    return OrderDetailsView.from(order, lines);
}
```

The read-only flag is a hint to the transaction manager/driver/database and is not an absolute authorization layer. Do not use read-only transactions for use cases that perform write operations.

## 7. Distinguishing Spring Data JDBC Converters from MyBatis TypeHandlers

Both frameworks have their own type conversion mechanisms:

| Mechanism | Scope |
| --- | --- |
| Spring Data custom converters | Converts between property/domain types and relational/JDBC types when Spring Data JDBC reads/writes. |
| MyBatis TypeHandler | Converts between Java types and JDBC types in MyBatis parameter/result mapping. |

If the same enum is stored by Spring Data JDBC as code `A` while MyBatis reads by enum name `ACTIVE`, the two access paths can interpret the same column differently.

Example MyBatis TypeHandler:

```java
@MappedTypes(CustomerStatus.class)
@MappedJdbcTypes(JdbcType.VARCHAR)
public class CustomerStatusTypeHandler
        extends BaseTypeHandler<CustomerStatus> {

    @Override
    public void setNonNullParameter(
            PreparedStatement ps,
            int index,
            CustomerStatus value,
            JdbcType jdbcType
    ) throws SQLException {
        ps.setString(index, switch (value) {
            case ACTIVE -> "A";
            case INACTIVE -> "I";
        });
    }

    @Override
    public CustomerStatus getNullableResult(
            ResultSet rs,
            String columnName
    ) throws SQLException {
        return parse(rs.getString(columnName));
    }

    @Override
    public CustomerStatus getNullableResult(
            ResultSet rs,
            int columnIndex
    ) throws SQLException {
        return parse(rs.getString(columnIndex));
    }

    @Override
    public CustomerStatus getNullableResult(
            CallableStatement cs,
            int columnIndex
    ) throws SQLException {
        return parse(cs.getString(columnIndex));
    }

    private CustomerStatus parse(String value) {
        if (value == null) {
            return null;
        }

        return switch (value) {
            case "A" -> CustomerStatus.ACTIVE;
            case "I" -> CustomerStatus.INACTIVE;
            default -> throw new IllegalArgumentException(
                "Unknown customer status: " + value
            );
        };
    }
}
```

This is an illustrative TypeHandler example; you need to register the handler in the MyBatis configuration or declare it directly in the mapper. Spring Data JDBC converters are not automatically used by MyBatis, and MyBatis TypeHandlers do not automatically apply to Spring Data JDBC repositories.

Write tests for both mapping paths if they access the same column with a special format.

## 8. Dynamic SQL and Parameter Binding in MyBatis

MyBatis is useful when queries vary based on input filters. XML mappers support `<if>`, `<where>`, `<choose>`, `<foreach>`, and other dynamic SQL constructs.

Example:

```xml
<mapper namespace="com.example.shop.persistence.mybatis.OrderReportMapper">

    <select id="search" resultType="com.example.shop.persistence.mybatis.dto.OrderSummary">
        SELECT
            o.id AS order_id,
            o.order_number,
            c.name AS customer_name,
            o.total_amount
        FROM purchase_orders o
        JOIN customers c ON c.id = o.customer_id

        <where>
            <if test="status != null">
                AND o.status = #{status}
            </if>

            <if test="customerId != null">
                AND c.id = #{customerId}
            </if>

            <if test="minTotal != null">
                AND o.total_amount >= #{minTotal}
            </if>

            <if test="maxTotal != null">
                AND o.total_amount <= #{maxTotal}
            </if>
        </where>

        ORDER BY o.created_at DESC, o.id DESC
    </select>
</mapper>
```

Corresponding mapper interface:

```java
@Mapper
public interface OrderReportMapper {

    List<OrderSummary> search(
        @Param("status") String status,
        @Param("customerId") Long customerId,
        @Param("minTotal") BigDecimal minTotal,
        @Param("maxTotal") BigDecimal maxTotal
    );
}
```

Values using `#{...}` are bound via PreparedStatement. Do not replace this with MyBatis's string substitution mechanism for request data.

String substitution inserts text directly into SQL and can cause SQL injection if given untrusted input. It should only be used for strictly controlled identifiers/fragments, such as choosing a column name from an allowlist in code. Do not allow users to send arbitrary column names or ORDER BY clauses directly.

## 9. Result Mapping: Aggregate or DTO?

Spring Data JDBC repositories typically return aggregates mapped according to domain metadata. MyBatis typically returns DTOs or projections tailored to the query.

Example report that does not need the entire aggregate:

```java
public class CustomerSalesSummary {
    private Long customerId;
    private String customerName;
    private Long completedOrders;
    private BigDecimal revenue;

    // No-args constructor, getters, and setters.
}
```

A MyBatis query can return this DTO directly. It does not need to construct a `Customer` aggregate with a collection of orders just to compute revenue.

Choose the return type based on purpose:

- Aggregate when you need to modify domain state and enforce invariants.
- DTO/projection when you only need to read a data shape for a screen, API, or report.
- A dedicated read model when querying/reporting has a different lifecycle and schema from the domain write model.

## 10. Caching When Both Frameworks Access the Same Data

MyBatis has a per-SqlSession local cache and may have a per-mapper-namespace second-level cache if enabled. Spring Data JDBC does not automatically notify MyBatis caches when an aggregate is updated through a repository.

Therefore, if a mapper enables caching for data that Spring Data JDBC can also modify, cached results can become stale.

A few principles:

- Avoid enabling second-level cache on mappers reading tables frequently written via Spring Data JDBC unless there is an invalidation strategy.
- Consider `localCacheScope=STATEMENT` when you need to limit local caching to the statement level.
- Use `useCache="false"` for queries that should not use the second-level cache when appropriate.
- If caching shared data is mandatory, design explicit invalidation/refresh after write operations.
- Do not assume one framework's cache automatically synchronizes with the persistence context/cache of the other.

If a transaction updates via Spring Data JDBC and then calls the same mapper query again, be aware that MyBatis's local cache can retain previous results within the SqlSession scope. Configure caching appropriately and integration-test the actual read/write sequence.

## 11. Impact on Lifecycle, Auditing, and Optimistic Locking

Spring Data JDBC can apply entity callbacks and auditing along the aggregate save path. MyBatis does not run those callbacks when executing mapper SQL.

Example MyBatis UPDATE:

```java
@Update("""
    UPDATE purchase_orders
    SET status = #{status}
    WHERE id = #{id}
    """)
int updateStatus(
    @Param("id") Long id,
    @Param("status") String status
);
```

This statement does not automatically:

- Invoke domain methods on `PurchaseOrder`.
- Check aggregate invariants.
- Increment the version column according to Spring Data JDBC's optimistic locking rules.
- Update `@LastModifiedDate` or `@LastModifiedBy`.
- Synchronize child rows owned by the aggregate.
- Publish Spring Data JDBC entity callbacks or lifecycle events.

If MyBatis needs to update an aggregate table, the necessary rules must be included in the SQL and application service. For example, optimistic locking requires checking the old version and incrementing the version in the same statement:

```sql
UPDATE purchase_orders
SET status = :newStatus,
    version = version + 1,
    last_modified_at = :modifiedAt
WHERE id = :id
  AND status = :expectedStatus
  AND version = :expectedVersion;
```

Then check the row count to detect conflicts. This is a separate write path that must be documented and tested, and is not automatically equivalent to `repository.save`.

When possible, keep MyBatis on the read path and make Spring Data JDBC the owner of the aggregate write path.

## 12. Migrations and Schema Ownership

Both Spring Data JDBC and MyBatis operate on the relational schema, so there must be a single source of truth for DDL.

Typically:

- Flyway or Liquibase manages versioned schema migrations.
- Spring Data JDBC mapping describes the tables/columns used by aggregates.
- MyBatis mappers reference the corresponding tables/columns in SQL.
- Migrations update the schema alongside mapper/domain code in the same reviewed change.

Do not let Spring SQL initialization, Flyway, Liquibase, and MyBatis mappers create/modify the same table through independent processes. A column rename can leave repository mapping valid while breaking XML mappers, or vice versa.

When changing the schema:

1. Add a compatible migration.
2. Update Spring Data JDBC mappings.
3. Update mapper SQL/MyBatis result mappings.
4. Run tests for both read and write paths.
5. Deploy using an expand-and-contract strategy if multiple application versions run concurrently.

## 13. Testing Applications Sharing Both Persistence Frameworks

Tests should run with the actual application configuration, because errors typically occur at integration points: mapper scanning, SqlSessionTemplate, DataSource, transaction manager, type handlers, or schema.

### 13.1. Testing MyBatis Reads and Spring Data JDBC Writes

Example integration test:

```java
@SpringBootTest
class OrderPersistenceIntegrationTest {

    @Autowired
    PurchaseOrderRepository orders;

    @Autowired
    OrderReportMapper reports;

    @Test
    void springDataWriteIsVisibleToMyBatisRead() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("PO-MIXED-001")
        );

        List<OrderSummary> summaries =
            reports.findByOrderNumber("PO-MIXED-001");

        assertThat(summaries).hasSize(1);
        assertThat(summaries.get(0).getOrderNumber())
            .isEqualTo("PO-MIXED-001");
    }
}
```

The test needs the appropriate schema and mappers. If an outer test transaction wraps the test, understand whether data is read on the same transaction/connection or from another transaction. To test real commits, let the service complete its transaction and then query in a new transaction.

### 13.2. Testing Shared Transaction Rollback

An important test verifies that writes across both frameworks roll back together:

```java
@Service
public class MixedPersistenceService {

    private final PurchaseOrderRepository orders;
    private final OutboxMapper outbox;

    public MixedPersistenceService(
        PurchaseOrderRepository orders,
        OutboxMapper outbox
    ) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public void createThenFail() {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create("PO-ROLLBACK-MIXED")
        );

        outbox.insert(
            "ORDER_CREATED",
            saved.getId().toString(),
            "{}"
        );

        throw new IllegalStateException("Test rollback");
    }
}
```

The test calls the service and verifies after the transaction ends:

- There is no order `PO-ROLLBACK-MIXED`.
- There is no corresponding outbox event.

If only one change rolls back, check whether both frameworks use the same DataSource instance, transaction manager, and MyBatis-Spring integration.

### 13.3. Testing Bidirectional Type Mapping

If enums/dates/JSON/UUIDs have custom conversions, test separately that:

- The Spring Data JDBC converter writes the expected format.
- Spring Data JDBC reads the expected format.
- The MyBatis TypeHandler writes the expected format.
- The MyBatis TypeHandler reads the expected format.
- Legacy data is understood by both read paths if compatibility is required.

Do not assume custom converters registered in Spring Data JDBC are used by MyBatis.

### 13.4. Using the Right Database Engine

H2 can be useful for fast tests, but it does not completely replace production PostgreSQL/MySQL/SQL Server. Dynamic SQL, type handlers, JSON, stored procedures, CTEs, and vendor-specific types should be tested against the corresponding database, typically via Testcontainers.

## 14. Common Mistakes

| Symptom | Cause | Solution |
| --- | --- | --- |
| Mapper is not injected | Missing `@Mapper`/`@MapperScan` or wrong scan package. | Configure mapper scanning explicitly. |
| Mapper and repository do not roll back together | Different DataSource or transaction manager; MyBatis not using a Spring-managed session. | Use MyBatis-Spring/SqlSessionTemplate and a shared transaction resource. |
| Mapper call commits independently | Opening SqlSession manually or calling commit manually. | Let SqlSessionTemplate and Spring transactions manage it. |
| Report returns stale data | MyBatis cache was not invalidated after Spring Data JDBC write. | Adjust local/second-level cache or disable cache for that query. |
| Aggregate missing children after mapper update | MyBatis only executes the written SQL without synchronizing the aggregate. | Keep aggregate writes in Spring Data JDBC or manage all invariants manually. |
| LastModified unchanged after mapper UPDATE | MyBatis does not run Spring Data JDBC auditing callbacks. | Update audit columns in SQL or triggers. |
| Optimistic locking bypassed | Mapper UPDATE does not check and increment version. | Add version predicate, increment, and check row count. |
| Enum read differently between frameworks | Spring converter and MyBatis TypeHandler have separate mappings. | Define/test bidirectional mapping for both. |
| SQL XML resource not found | Wrong `mapper-locations` or XML not packaged into classpath. | Check resource paths in the build artifact. |
| Dynamic sort introduces SQL injection | Using string substitution with untrusted input. | Allowlist identifiers; bind values with `#{...}`. |
| H2 tests pass but production fails | Differences in dialect, types, or stored procedures. | Run integration tests with the production-equivalent database. |
| Both frameworks write the same aggregate | Ownership and invariants are not clearly delineated. | Choose one write path or clearly define a direct SQL contract. |

## 15. Decision Process for Whether to Combine

Before adding MyBatis to a Spring Data JDBC application, answer:

1. Can current queries be expressed concisely with derived queries or `@Query`?
2. Is there a genuine need for complex SQL, dynamic SQL, stored procedures, legacy mappers, or DTO projections?
3. Which parts are the aggregate write model and which are the read/reporting model?
4. Which framework owns writes on each table/aggregate?
5. If both participate in a single use case, do they share the same DataSource and transaction manager?
6. Are there converters/TypeHandlers that need to be synchronized between the two frameworks?
7. Could MyBatis caching return stale data after Spring Data JDBC writes?
8. Does direct SQL need to update versions, auditing, or child rows manually?
9. Do migrations update both mappings and mapper SQL together?
10. Do integration tests run on a database matching production?

If the benefits of SQL control/read models are clear and ownership can be delineated, combining the two frameworks makes sense. If you only need CRUD and a few simple queries, Spring Data JDBC is usually sufficient.

> **Spring Data JDBC is well suited for managing aggregates and the write lifecycle; MyBatis is well suited when you need SQL control, dynamic queries, legacy integration, or complex read models.** Combine them when each tool has a clear role, divide write-path ownership, share a DataSource/transaction manager when atomicity is required, and test both mappings and caching. One database can be accessed by both frameworks, but each aggregate should have consistent write rules.

### References

- [Spring Data Relational — Spring Data JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc.html): aggregate persistence, repositories, and mapping in Spring Data JDBC.
- [Spring Data JDBC — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): query derivation and custom SQL.
- [MyBatis — Java API](https://mybatis.org/mybatis-3/java-api.html): mappers, SqlSession, and using MyBatis.
- [MyBatis — Mapper XML Files](https://mybatis.org/mybatis-3/sqlmap-xml.html): result mapping, dynamic SQL, and XML mappers.
- [MyBatis-Spring — SqlSessionTemplate](https://mybatis.org/spring/sqlsession.html): integrating SqlSession with Spring transactions and managing sessions.
- [MyBatis-Spring — Transactions](https://mybatis.org/spring/transactions.html): participating in Spring-managed transactions.
- [MyBatis Spring Boot Starter](https://mybatis.org/spring-boot-starter/mybatis-spring-boot-autoconfigure/): auto-configuration, mapper scanning, and MyBatis configuration in Spring Boot.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction managers and declarative transactions.
