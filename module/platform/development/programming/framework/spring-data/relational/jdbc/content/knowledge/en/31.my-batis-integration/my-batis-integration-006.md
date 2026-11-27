# Sharing a DataSource, Transactions, and Consistency Testing

When an application uses both **MyBatis** and **Spring Data Relational JDBC** simultaneously, both frameworks can read and write to the same database. For a multi-operation use case to be atomic, MyBatis mappers, Spring Data JDBC repositories, and JDBC templates must participate in **the same Spring transaction**.

There are three main conditions:

1. MyBatis and Spring Data JDBC are configured with the same **DataSource**.
2. Both use the same **PlatformTransactionManager** managing that DataSource.
3. MyBatis uses Spring integration (**SqlSessionTemplate** and **SpringManagedTransactionFactory**), while services open transactions via **@Transactional**.

When configured properly, a service method can save an aggregate with Spring Data JDBC, update another table with MyBatis, and write an audit row with **JdbcTemplate**. The changes commit or roll back together according to the transaction boundary.

However, sharing a transaction only guarantees database-level consistency. Both frameworks still maintain separate mappings, converters, caches, and lifecycles. Updating a table directly with MyBatis does not automatically execute Spring Data JDBC aggregate callbacks, auditing, or optimistic locking; MyBatis caches also do not automatically notice when a repository modifies data.

## 1. Integration Architecture

Suppose an order-placement use case needs to:

- Save the **PurchaseOrder** aggregate using Spring Data JDBC.
- Deduct inventory using a MyBatis mapper.
- Write an audit row using MyBatis or `JdbcTemplate`.

~~~mermaid
flowchart TD
    A["PlaceOrderService<br/>@Transactional"] --> B["PurchaseOrderRepository<br/>Spring Data JDBC"]
    A --> C["InventoryMapper<br/>MyBatis-Spring"]
    A --> D["OrderAuditMapper<br/>MyBatis-Spring"]
    B --> E["DataSource"]
    C --> E
    D --> E
    E --> F["Transaction-bound connection"]
    F --> G["JdbcTransactionManager"]
    G --> H["COMMIT or ROLLBACK"]
~~~

Both frameworks are clients of the same database and the same DataSource. The transaction manager does not need to know whether SQL came from Spring Data JDBC or MyBatis; it manages JDBC connections and transaction resources.

**Having the same JDBC URL is not enough to prove the same transaction.** Two separate connection pools, even if pointing to the same URL/database, are still two distinct DataSources/resources. Use the exact same DataSource bean for repository infrastructure, MyBatis `SqlSessionFactory`, and the transaction manager.

## 2. Configuring a Shared DataSource

With Spring Boot, you usually only need to declare one DataSource:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/sales
    username: app
    password: secret-from-environment
    driver-class-name: org.postgresql.Driver
~~~

Common dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jdbc</artifactId>
</dependency>

<dependency>
    <groupId>org.mybatis.spring.boot</groupId>
    <artifactId>mybatis-spring-boot-starter</artifactId>
</dependency>

<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Use a MyBatis Spring Boot Starter version compatible with your application's Spring Boot version; let Spring Boot dependency management manage Spring Framework/Spring Data versions instead of upgrading individual libraries arbitrarily.

When using the starter, MyBatis can auto-configure **SqlSessionFactory**, **SqlSessionTemplate**, and mapper scanning from the Spring Boot DataSource. Do not redeclare those beans if auto-configuration already creates the right configuration.

### Explicit Java Configuration Without Auto-Configuration

Example configuring a single DataSource, transaction manager, and MyBatis factory:

~~~java
@Configuration
@EnableTransactionManagement
@MapperScan("com.example.persistence.mybatis")
public class PersistenceConfiguration {

    @Bean
    public DataSource dataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:postgresql://localhost:5432/sales")
                .username("app")
                .password(System.getenv("DB_PASSWORD"))
                .driverClassName("org.postgresql.Driver")
                .build();
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    public SqlSessionFactory sqlSessionFactory(DataSource dataSource)
            throws Exception {
        SqlSessionFactoryBean factory = new SqlSessionFactoryBean();
        factory.setDataSource(dataSource);
        factory.setTransactionFactory(new SpringManagedTransactionFactory());
        return factory.getObject();
    }
}
~~~

Important MyBatis/Spring imports:

~~~java
import org.mybatis.spring.SqlSessionFactoryBean;
import org.mybatis.spring.annotation.MapperScan;
import org.mybatis.spring.transaction.SpringManagedTransactionFactory;
import org.apache.ibatis.session.SqlSessionFactory;

import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
~~~

This example uses **JdbcTransactionManager**. You can use **DataSourceTransactionManager** instead if appropriate. `JdbcTransactionManager` was introduced in Spring Framework 5.3 and extends `DataSourceTransactionManager`; it adds `SQLException` translation at the commit/rollback step. `DataSourceTransactionManager` can still coordinate with MyBatis-Spring when using the right DataSource and transaction factory.

**SqlSessionFactoryBean** uses **SpringManagedTransactionFactory** by default; declaring it explicitly in the example highlights the integration requirement. Do not replace it with a standalone JDBC transaction factory if you want sessions to participate in Spring transactions.

With Spring Boot, manual configuration is only needed when you want custom factory/mapper scan control or have disabled auto-configuration. Avoid accidentally creating two `SqlSessionFactory` beans, two DataSources, or two transaction managers managing the same group of mappers.

## 3. How Does MyBatis-Spring Participate in Spring Transactions?

MyBatis-Spring provides two key components:

- **SqlSessionTemplate** is a thread-safe `SqlSession` implementation when used with Spring. It manages session lifecycles and coordinates with transaction synchronization.
- **SpringManagedTransactionFactory** creates a transaction adapter that uses the Spring-managed transaction instead of committing independently.

When a **@Transactional** method starts:

1. The transaction manager acquires a connection from the DataSource and binds it to the current transaction.
2. Spring Data JDBC repositories obtain that same connection when executing SQL.
3. MyBatis mappers are invoked through `SqlSessionTemplate`; MyBatis-Spring locates the session bound to the current transaction.
4. The MyBatis session uses the DataSource connection currently managed by the Spring transaction.
5. When the service finishes, the transaction manager commits or rolls back.
6. MyBatis-Spring synchronizes session state and releases resources per the transaction lifecycle.

You do not need to manually pass a `Connection` from a repository to a mapper. Sharing happens through Spring's transaction infrastructure and DataSource identity.

### Using Mapper Proxies Instead of Opening SqlSession Manually

Mapper interface:

~~~java
@Mapper
public interface InventoryMapper {

    @Update("""
        UPDATE inventory
        SET available = available - #{quantity}
        WHERE product_id = #{productId}
          AND available >= #{quantity}
        """)
    int reserve(
            @Param("productId") Long productId,
            @Param("quantity") int quantity
    );
}
~~~

Spring creates a mapper proxy and invokes MyBatis through the session template. Do not manually call **SqlSessionFactory.openSession()** in a service to run mappers if you want Spring transaction integration. A manually opened session can sit outside the Spring-synchronized session/transaction.

Do not manually call **commit()**, **rollback()**, or **close()** on sessions managed by `SqlSessionTemplate`. Let the transaction manager control the transaction.

## 4. Placing Transaction Boundaries at the Application Service

The transaction boundary should span the entire use case requiring atomicity, rather than letting individual repositories/mappers commit separately.

Example aggregate root:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;

    private String status;

    // constructor, getters, domain methods...
}
~~~

Spring Data JDBC repository:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

MyBatis mapper:

~~~java
@Mapper
public interface InventoryMapper {

    @Update("""
        UPDATE inventory
        SET available = available - #{quantity}
        WHERE product_id = #{productId}
          AND available >= #{quantity}
        """)
    int reserve(
            @Param("productId") Long productId,
            @Param("quantity") int quantity
    );
}
~~~

Audit mapper:

~~~java
@Mapper
public interface OrderAuditMapper {

    @Insert("""
        INSERT INTO order_audit(order_id, event_type)
        VALUES (#{orderId}, #{eventType})
        """)
    int insert(
            @Param("orderId") Long orderId,
            @Param("eventType") String eventType
    );
}
~~~

Coordinating service:

~~~java
@Service
public class PlaceOrderService {

    private final PurchaseOrderRepository orderRepository;
    private final InventoryMapper inventoryMapper;
    private final OrderAuditMapper auditMapper;

    public PlaceOrderService(
            PurchaseOrderRepository orderRepository,
            InventoryMapper inventoryMapper,
            OrderAuditMapper auditMapper) {
        this.orderRepository = orderRepository;
        this.inventoryMapper = inventoryMapper;
        this.auditMapper = auditMapper;
    }

    @Transactional
    public Long place(PurchaseOrder order, Long productId, int quantity) {
        PurchaseOrder saved = orderRepository.save(order);

        int reserved = inventoryMapper.reserve(productId, quantity);
        if (reserved != 1) {
            throw new InsufficientStockException(productId);
        }

        auditMapper.insert(saved.getId(), "ORDER_CREATED");

        return saved.getId();
    }
}
~~~

If `reserve()` returns `0`, a runtime exception escapes the transactional method. The transaction rolls back both saving `PurchaseOrder` and any prior MyBatis operations. The audit insert only executes when reservation succeeds.

**@Transactional** rolls back on `RuntimeException` and `Error` by default. If a service throws a checked exception that must also trigger rollback, declare `rollbackFor`:

~~~java
@Transactional(rollbackFor = OrderProcessingException.class)
public Long place(...) throws OrderProcessingException {
    // ...
}
~~~

Do not catch and swallow exceptions inside the service if business rules require rollback. If wrapping or translating exceptions, ensure an exception exits the transaction boundary or mark the transaction rollback-only appropriately.

## 5. Reading Data Just Written by the Other Framework

When both frameworks participate in the same transaction and share the same connection, the transaction can read changes it has just performed (read-your-writes).

For example, MyBatis updates status, then Spring Data JDBC reads the aggregate:

~~~java
@Transactional
public PurchaseOrder changeStatusAndRead(Long orderId) {
    int updated = orderMapper.changeStatus(orderId, "READY");

    if (updated != 1) {
        throw new OrderNotFoundException(orderId);
    }

    return orderRepository.findById(orderId).orElseThrow();
}
~~~

Conversely, Spring Data JDBC can save a root and then a MyBatis mapper reads it back in the same transaction:

~~~java
@Transactional
public OrderRow createAndRead(PurchaseOrder order) {
    PurchaseOrder saved = orderRepository.save(order);
    return orderMapper.findRow(saved.getId());
}
~~~

SQL statements execute immediately within the JDBC transaction; Spring Data JDBC does not hold a JPA-style persistence context waiting to flush at transaction end. Therefore, mappers can read changes previously written by repositories on the same transaction connection.

This does not mean other transactions see uncommitted data. Other transactions still obey the database's isolation level. Under `READ_COMMITTED`, other transactions normally see changes only after commit; under `REPEATABLE_READ` or `SERIALIZABLE`, snapshot/locking semantics depend on the database.

## 6. Testing Rollback Between Spring Data JDBC and MyBatis

The most critical test confirms both frameworks roll back together when a step fails.

A test-only service or use case can deliberately throw an exception after writing through both frameworks:

~~~java
@Service
public class ConsistencyTestService {

    private final PurchaseOrderRepository orderRepository;
    private final OrderAuditMapper auditMapper;

    public ConsistencyTestService(
            PurchaseOrderRepository orderRepository,
            OrderAuditMapper auditMapper) {
        this.orderRepository = orderRepository;
        this.auditMapper = auditMapper;
    }

    @Transactional
    public void createThenFail(PurchaseOrder order) {
        PurchaseOrder saved = orderRepository.save(order);
        auditMapper.insert(saved.getId(), "CREATED");
        throw new IllegalStateException("Simulated failure");
    }
}
~~~

Integration test:

~~~java
@SpringBootTest
class SharedTransactionIntegrationTest {

    @Autowired ConsistencyTestService service;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void repositoryAndMyBatisWritesRollbackTogether() {
        assertThatThrownBy(() -> service.createThenFail(
                new PurchaseOrder(42L, "DRAFT")
        )).isInstanceOf(IllegalStateException.class);

        Integer orderCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM purchase_order WHERE customer_id = ?",
                Integer.class,
                42L
        );

        Integer auditCount = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM order_audit WHERE event_type = ?",
                Integer.class,
                "CREATED"
        );

        assertThat(orderCount).isZero();
        assertThat(auditCount).isZero();
    }
}
~~~

This test should run against a real production-compatible database, such as PostgreSQL via Testcontainers. Do not annotate the test method itself with **@Transactional** when the goal is to verify that the service transaction rolled back before assertions run; an outer test transaction can obscure which transaction is being tested.

### Verifying Successful Commit

Add a test for the non-exception path:

- The repository saves the aggregate.
- The MyBatis mapper writes the audit record or updates inventory.
- The service completes normally.
- An independent query after the service returns confirms both changes committed.

### Verifying Bidirectional Read-Your-Writes

Include cases for:

1. Spring Data JDBC insert/update followed by MyBatis SELECT in the same transaction.
2. MyBatis UPDATE followed by Spring Data JDBC SELECT in the same transaction.
3. Both performing updates within one service transaction.
4. One operation violating a constraint after the other framework has written; verifying the entire transaction rolls back.

**@MybatisTest** usually loads only the MyBatis slice and does not automatically represent full Spring Data JDBC repositories. To test the real composition, use **@SpringBootTest** or an integration test configuration that includes both infrastructures.

## 7. Using Testcontainers to Test on the Same Database Engine

H2 can be helpful for fast tests, but if production runs PostgreSQL/MySQL/SQL Server, run integration tests with the exact database engine and driver. Testcontainers lets you spin up ephemeral databases for testing.

PostgreSQL example:

~~~java
@Testcontainers
@SpringBootTest
class SharedDatabaseIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("sales")
                    .withUsername("app")
                    .withPassword("secret");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
        registry.add("spring.datasource.driver-class-name",
                postgres::getDriverClassName);
    }
}
~~~

Add Flyway/Liquibase migrations or SQL schema scripts to create `purchase_order`, `inventory`, and `order_audit`. When testing, verify MyBatis and Spring Data JDBC receive the exact same DataSource bean configured by Spring Boot.

Do not just assert that two beans share the same JDBC URL. Stronger functional proof is testing rollback: write through the first framework, write through the second framework, throw an exception, and confirm no changes remain after the transaction ends.

## 8. MyBatis Caches Can Cause Stale Reads

Sharing a DataSource and transaction does not automatically synchronize caches between the two frameworks.

MyBatis has:
- **SqlSession-level local cache** (first-level cache), which defaults to `SESSION` scope.
- **Second-level cache** per mapper namespace if enabled and configured.

Spring Data JDBC does not know which mapper namespaces/caches hold results. Thus, if MyBatis SELECTs a row and then Spring Data JDBC UPDATEs that row, a subsequent MyBatis SELECT in the same `SqlSession` can return stale local cache data instead of running fresh SQL.

Similarly, if a MyBatis second-level cache holds data from a table modified by Spring Data JDBC, Spring Data JDBC does not automatically invalidate that MyBatis cache.

Mitigations:

- For tables written by both frameworks, consider disabling MyBatis second-level cache for those mappers/tables.
- Consider **localCacheScope=STATEMENT** if use cases require MyBatis queries to re-read the database across statements.
- Use **flushCache** on queries that must bypass caching as supported by MyBatis.
- Actively clear/evict caches when the other framework's write path modifies data, if caching is still needed.
- Avoid long-lived caches for mutable data updated by multiple persistence mechanisms unless there is an explicit invalidation protocol.

Example MyBatis configuration:

~~~yaml
mybatis:
  configuration:
    local-cache-scope: STATEMENT
~~~

`STATEMENT` reduces local cache reuse across statements; it does not automatically disable all second-level caches. If a mapper enables namespace caching, manage that cache separately.

### Transaction Consistency and Cache Consistency Are Two Separate Problems

| Layer | Guaranteed by a shared transaction? |
|---|---|
| SQL updates via MyBatis | Yes, if using the same transaction resource |
| SQL updates via Spring Data JDBC | Yes, if using the same transaction resource |
| Commit/rollback across both frameworks | Yes, with the same manager/DataSource |
| Previously loaded Java objects | Not automatically synchronized |
| MyBatis local cache | Not automatically invalidated by Spring Data JDBC |
| MyBatis second-level cache | Not automatically invalidated by Spring Data JDBC |
| External caches such as Redis | Do not automatically participate in JDBC transactions |

After one framework writes data, reload objects/caches when fresh state is needed. A transaction does not merge two object graphs or two caches into one shared memory space.

## 9. Aggregate Lifecycle and @Version Are Not Shared Automatically

Spring Data JDBC saves aggregates according to its mapping and lifecycle. When calling **repository.save(root)**, the framework can handle:

- The aggregate root and owned entities.
- Entity callbacks and lifecycle events.
- Auditing fields if configured.
- Optimistic locking via **@Version**.

MyBatis mappers execute SQL according to their own mappings. A MyBatis UPDATE on an aggregate table does not automatically invoke Spring Data JDBC callbacks, does not automatically update **@LastModifiedDate**, and does not automatically increment **@Version**.

Example entity:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
~~~

If MyBatis updates this table directly:

~~~java
@Update("""
    UPDATE purchase_order
    SET status = #{status}
    WHERE id = #{id}
    """)
int changeStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

the version does not increment. A previously loaded aggregate may still hold the old version and later be saved by Spring Data JDBC without detecting the MyBatis write. This can overwrite newer data.

If you must update the root with MyBatis, enforce optimistic locking manually:

~~~java
@Update("""
    UPDATE purchase_order
    SET status = #{status},
        version = version + 1
    WHERE id = #{id}
      AND version = #{expectedVersion}
    """)
int changeStatus(
        @Param("id") Long id,
        @Param("status") String status,
        @Param("expectedVersion") Long expectedVersion
);
~~~

If the update count is `0`, the version no longer matches or the ID does not exist. The application service must handle the conflict. After the mapper updates, any previously loaded Spring Data JDBC object must be reloaded or have its version state updated in a controlled manner.

### Choosing Write-Path Ownership

A practical convention:

- Spring Data JDBC is the primary write path for aggregate roots and owned entities.
- MyBatis is used for complex queries, projections/DTOs, reporting, and auxiliary tables outside the aggregate lifecycle.
- If MyBatis must write to aggregate tables, define explicit rules for versions, auditing, invariants, and cache invalidation.
- Do not let both frameworks arbitrarily update the same aggregate without a write protocol.

Sharing a transaction does not replace aggregate boundaries and domain rules.

## 10. MyBatis TypeHandlers and Spring Data Converters Are Two Separate Systems

Spring Data JDBC uses Spring Data's conversion infrastructure, such as **@ReadingConverter** and **@WritingConverter**. MyBatis uses **TypeHandler** to convert Java types into JDBC parameters and read JDBC results.

The two frameworks do not share converters automatically:

| Need | Spring Data JDBC | MyBatis |
|---|---|---|
| Java value object ↔ SQL scalar | Converter, `JdbcCustomConversions` | `TypeHandler<T>` |
| Column renaming | `@Column` or naming strategy | SQL aliases, `resultMap`, `@Results` |
| Relationship mapping | Aggregate mapping, `@MappedCollection`, `AggregateReference` | SQL JOINs and mapper-declared result mappings |
| Optimistic version | `@Version` in aggregate lifecycle | SQL mapper must check/increment version manually |
| Caching | No JPA-style persistence context cache by default | Local/second-level cache per MyBatis configuration |

If the domain uses **EmailAddress**, Spring Data JDBC might use an `EmailAddress` ↔ `String` converter; a MyBatis mapper still needs **TypeHandler<EmailAddress>** if it accepts or returns that type directly. If the mapper uses `String`, conversion can happen at the application layer.

Do not assume **@Column("email_address")** affects MyBatis SQL or result mappings. MyBatis SQL and `resultMap` definitions must declare column names matching the schema.

## 11. Generated IDs and Shared Data

Both frameworks can operate on the same identity/sequence tables, but generated-key retrieval is configured separately.

Spring Data JDBC uses its mapping/dialect and ID generation infrastructure. MyBatis typically uses **useGeneratedKeys/keyProperty** or database-appropriate sequence SQL.

Example MyBatis insert:

~~~java
@Insert("""
    INSERT INTO order_audit(order_id, event_type)
    VALUES (#{orderId}, #{eventType})
    """)
@Options(useGeneratedKeys = true, keyProperty = "id")
int insertAudit(AuditRecord record);
~~~

When MyBatis inserts a row with a generated ID, the key is written into the configured property of the parameter object per the JDBC driver and MyBatis. When Spring Data JDBC inserts an aggregate, the ID is assigned according to Spring Data JDBC's mapping.

Points to check:

- Both target the right table/sequence/identity in the same database.
- Do not manually assign IDs that collide with the database-generated ID range.
- With PostgreSQL sequences, if the application assigns IDs manually, the sequence must be synchronized per your migration/maintenance strategy.
- Test generated keys on the production driver; H2 may behave differently.

## 12. Transaction Propagation and Thread Boundaries

**@Transactional** uses `REQUIRED` propagation by default: mapper/repository methods invoked inside a service transaction join the existing transaction when sharing the transaction manager/resource.

| Propagation | Behavior in MyBatis + Spring Data JDBC integration |
|---|---|
| REQUIRED | Shares the current transaction; appropriate for most use cases |
| REQUIRES_NEW | Suspends the outer transaction and opens a new one; may require a second connection |
| SUPPORTS | Joins if a transaction exists; otherwise runs non-transactionally |
| MANDATORY | Requires the caller to already have an open transaction |
| NESTED | Uses savepoints if supported by the transaction manager/database |

Do not use `REQUIRES_NEW` just to "give MyBatis its own transaction" if business logic requires both frameworks to roll back together. The new transaction can commit independently while the outer transaction rolls back.

JDBC transactions are thread-bound. If a service invokes `@Async`, an executor, or spawns a new thread, the current transaction does not automatically propagate to worker threads. Workers need their own transactions.

**@Transactional** is applied via Spring proxies. Self-invocation—one method in a class directly calling another method in the same class—bypasses the proxy and does not apply a new transaction interceptor as expected. Place transactions on use-case methods called from other beans or extract separate services.

## 13. Multiple DataSources Are Not a Single Shared Transaction

If an application has two databases:

~~~text
ordersDataSource
  ├── Spring Data JDBC repositories
  ├── MyBatis orders SqlSessionFactory
  └── ordersTransactionManager

reportingDataSource
  ├── MyBatis reporting SqlSessionFactory
  └── reportingTransactionManager
~~~

You must create a corresponding `SqlSessionFactory`, mapper scan, and transaction manager for each DataSource. **@Transactional("ordersTransactionManager")** only manages resources of the orders database.

Two DataSources with the same JDBC URL that belong to two separate pools also do not automatically share transaction connections. A single local transaction manager cannot atomically commit/roll back two independent resources.

If a use case must write to both databases, options include:

- Distributed transactions/XA/JTA if supported by infrastructure and databases and strict atomicity is genuinely required.
- Transactional outbox combined with a consumer/worker.
- Saga/compensation for multi-service/multi-database workflows.

Do not put two DataSources in the same service and assume a default `@Transactional` coordinates both.

## 14. Common Configuration Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Repository rolls back but MyBatis insert persists | MyBatis uses a different DataSource/transaction factory or manually opened session | Use the same DataSource and MyBatis-Spring `SqlSessionTemplate` |
| MyBatis mapper commits before service ends | Using standalone MyBatis session/JDBC transaction | Use mapper proxies via `SqlSessionTemplate`; do not commit manually |
| JdbcTemplate rolls back but mapper does not | `SqlSessionFactory` uses a different DataSource or not `SpringManagedTransactionFactory` | Check factory and transaction manager |
| Two transaction managers exist and wrong one is chosen | Multiple DataSources or multiple manager beans | Use explicit qualifiers/transaction manager names |
| Same URL but not same transaction | Two independent pools/DataSource objects | Share a single DataSource bean |
| MyBatis SELECT returns stale data after repository UPDATE | MyBatis local/second-level cache not invalidated | Reduce cache scope, disable/flush cache, or manage eviction |
| MyBatis UPDATE breaks optimistic locking | Mapper does not check/increment version | Put expected version in WHERE and increment version in SQL |
| Spring Data JDBC overwrites MyBatis changes | Aggregate object holds stale state/unchanged version | Reload aggregate; establish write protocols and versioning |
| MyBatis fails to map custom value objects | Missing MyBatis `TypeHandler` | Register a dedicated `TypeHandler` or convert via scalar |
| MyBatis test passes but repository not loaded | Using `@MybatisTest` slice without importing Spring Data JDBC | Use `@SpringBootTest` or integration test config covering both |
| Rollback test yields confusing results | Test method also opens an outer transaction | Keep test non-transactional or control commit/rollback explicitly |
| `@Transactional` has no effect | Self-invocation or calling manually instantiated objects | Invoke through a Spring bean proxy |

## 15. Consistency Testing Checklist

An integration test suite should verify the following behaviors:

| Scenario | Expected Outcome |
|---|---|
| Spring Data JDBC save, MyBatis SELECT in same transaction | Mapper reads newly saved data if caching does not mask it |
| MyBatis UPDATE, Spring Data JDBC SELECT in same transaction | Repository reads changes made on the same transaction connection |
| Repository write + MyBatis write + runtime exception | Both changes roll back |
| Repository write + MyBatis write + normal method completion | Both changes commit |
| MyBatis UPDATE on an aggregate with `@Version` | Version is checked/incremented per designed write protocol |
| Spring Data JDBC UPDATE after MyBatis UPDATE | No lost updates due to stale object/unchanged version |
| MyBatis cache enabled and Spring Data JDBC writes | Cache invalidation is controlled; no stale data returned |
| Two separate DataSources | Do not expect one local transaction manager to roll back both |

When testing rollback, verify data with an independent query after the service transaction ends. When testing caching, run the exact sequence: MyBatis SELECT, Spring Data JDBC UPDATE, MyBatis SELECT again within the same transaction/session. Testing only SQL commit/rollback will not detect stale caches.

## 16. Integration Implementation Workflow

1. **Choose a single shared DataSource:** configure Spring Data JDBC, MyBatis, and the transaction manager with the same bean.
2. **Configure MyBatis-Spring:** use `SqlSessionFactoryBean`, `SpringManagedTransactionFactory`, and mapper proxies/`SqlSessionTemplate`.
3. **Choose a transaction manager:** `JdbcTransactionManager` or `DataSourceTransactionManager` managing that exact DataSource.
4. **Place transactions at the service layer:** use `@Transactional` for use cases coordinating repositories and mappers.
5. **Define write ownership:** specify which framework is responsible for writing aggregate roots/children.
6. **Manage versioning/auditing:** MyBatis DML on aggregates must explicitly honor versions and audits where needed.
7. **Check caching:** prevent stale caches when Spring Data JDBC modifies data cached by MyBatis mappers.
8. **Test rollback:** throw an exception after both frameworks have written and confirm no changes commit.
9. **Test read-your-writes:** verify data is readable across frameworks within the same transaction.
10. **Use a production-compatible database:** Testcontainers helps verify drivers, generated keys, transactions, and SQL on the actual engine.

### Quick Decision Table

| Requirement | Implementation Approach |
|---|---|
| MyBatis and Spring Data JDBC commit/roll back together | Same DataSource, same transaction manager, MyBatis-Spring |
| MyBatis mapper uses Spring transactions | `SqlSessionTemplate` and `SpringManagedTransactionFactory` |
| Coordinate multiple operations in one use case | `@Transactional` at application service |
| MyBatis reads data just written by repository | Shared transaction connection; check caching |
| MyBatis writes to aggregate tables | Explicitly manage invariants, callbacks/auditing, and `@Version` |
| Both frameworks use custom Java types | Separate Spring Data `Converter` and MyBatis `TypeHandler` |
| Verify atomicity | Integration test failing between two operations and asserting rollback |
| Two independent databases | Separate transaction managers; XA/outbox/saga if coordination is needed |

**Core takeaway:** MyBatis and Spring Data JDBC can share transactions when they share one DataSource, one transaction manager, and MyBatis-Spring manages sessions. Place transaction boundaries at the application service so multiple operations commit/roll back together. Then handle differences in caching, mapping, aggregate lifecycles, and optimistic locking separately; a database transaction does not automatically synchronize state at the framework/application layer.

## Official References

- [MyBatis-Spring — Transactions](https://mybatis.org/spring/transactions.html): how MyBatis-Spring participates in Spring transactions and the shared DataSource requirement.
- [MyBatis-Spring — SqlSession](https://mybatis.org/spring/sqlsession.html): `SqlSessionTemplate`, session management, and transaction integration.
- [MyBatis-Spring — SqlSessionFactoryBean](https://mybatis.org/spring/factorybean.html): configuring `SqlSessionFactoryBean`, DataSource, and transaction factory.
- [MyBatis — Configuration](https://mybatis.org/mybatis-3/configuration.html): local cache, second-level cache, and `localCacheScope`.
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, connection reuse, and transaction-aware DataSources.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction managers, propagation, and declarative transactions.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction behavior of Spring Data JDBC repositories and the service layer.
- [Spring Data Relational — Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): version properties and concurrent update detection.
- [Testcontainers — PostgreSQL Module](https://java.testcontainers.org/modules/databases/postgres/): integration testing with a PostgreSQL container.
