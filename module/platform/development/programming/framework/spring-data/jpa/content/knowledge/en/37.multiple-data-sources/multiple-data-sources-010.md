# Testing Routing, Transactions, and Data Isolation

## 1. Objectives

When a Spring Data JPA application uses multiple data sources, you must verify that every operation targets the right database, transactions encompass the right work, and data is never misread or miswritten across sources. A configuration that merely boots is insufficient: wrong routing can make queries hit the primary, commands write to a replica, or a transaction acquire a connection before routing metadata is ready.

This lesson uses a primary/replica model to test that:
- Queries with `@Transactional(readOnly = true)` are routed to the read replica.
- Commands with write transactions are routed to the primary.
- Transaction rollbacks leave no partially written data behind.
- Data existing only in one source does not appear when querying the other source.
- You can distinguish datasource routing, data isolation across databases, and transaction isolation levels.
- You recognize the limits when a single business operation needs to write to multiple databases.

After this lesson, you will be able to write integration tests with two independent databases, verify routing using distinct marker data, and confirm commits/rollbacks by reading directly from each source.

## 2. Concepts to distinguish

Three concepts are frequently confused:

| Concept | Question Answered | Example |
| --- | --- | --- |
| Data source routing | Which database does this operation's connection come from? | Queries read from replica; commands write to primary. |
| Data isolation | Can data from one source/tenant leak into another source/tenant? | A record existing only in tenant A's database does not appear in tenant B. |
| Transaction isolation | To what degree does one transaction see another transaction's changes? | `READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`. |

Routing decides where connections come from. Data isolation defines data boundaries and access permissions. Transaction isolation is enforced by the database across concurrent transactions. Testing one aspect does not automatically prove the other two.

## 3. Primary/replica routing in Spring

A common configuration sends writes to the primary and reads to a replica. Spring provides `AbstractRoutingDataSource` to select a target DataSource based on a lookup key.

Example route key:

```java
package com.example.multidb;

public enum DataSourceRoute {
    PRIMARY,
    REPLICA
}
```

Routing datasource inspecting current transaction state:

```java
package com.example.multidb;

import org.springframework.jdbc.datasource.lookup.AbstractRoutingDataSource;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class ReadWriteRoutingDataSource extends AbstractRoutingDataSource {
    @Override
    protected Object determineCurrentLookupKey() {
        boolean readOnly = TransactionSynchronizationManager.isCurrentTransactionReadOnly();
        return readOnly ? DataSourceRoute.REPLICA : DataSourceRoute.PRIMARY;
    }
}
```

When a transaction is marked read-only, the lookup key is `REPLICA`. All other cases, including calls without transaction metadata, default to `PRIMARY` to prevent accidentally routing write operations to a replica.

`@Transactional(readOnly = true)` by itself does not create a replica nor route connections automatically. `ReadWriteRoutingDataSource` is what makes the selection in this example. Read-only is a transaction hint; true read-only enforcement should be backed by database privileges.

## 4. Why is LazyConnectionDataSourceProxy needed?

The routing datasource reads `TransactionSynchronizationManager.isCurrentTransactionReadOnly()`. This value must be available at the moment the routing datasource chooses a physical connection.

In some JPA setups, the transaction manager may request a connection early when starting a transaction. If the routing datasource picks a target before transaction read-only metadata is bound to the thread, queries intended for the replica may end up routed to the primary.

`LazyConnectionDataSourceProxy` delays physical connection acquisition until a JDBC statement actually needs a connection. As a result, transaction metadata has time to be populated before `AbstractRoutingDataSource` picks a target.

```java
@Bean
@Primary
DataSource dataSource(@Qualifier("routingDataSource") DataSource routingDataSource) {
    return new LazyConnectionDataSourceProxy(routingDataSource);
}
```

This proxy must also be the DataSource used by JPA's `EntityManagerFactory` and transaction manager. Do not wrap only a `JdbcTemplate` while Hibernate continues using a different datasource.

Routing is decided when the physical connection is acquired. Never toggle the read-only flag or tenant route mid-transaction expecting subsequent statements to switch databases. A transaction should use one consistent source from start to finish.

## 5. Configuring two DataSources

The example uses Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate, and H2 for integration tests. Spring Boot manages the JPA provider and JDBC pool versions.

`src/main/java/com/example/multidb/DataSourceRoutingConfiguration.java`:

```java
package com.example.multidb;

import java.util.HashMap;
import java.util.Map;
import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.datasource.LazyConnectionDataSourceProxy;

@Configuration
public class DataSourceRoutingConfiguration {
    @Bean
    @ConfigurationProperties("app.datasource.primary")
    DataSourceProperties primaryDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.replica")
    DataSourceProperties replicaDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean(name = "primaryTargetDataSource")
    DataSource primaryTargetDataSource(
            @Qualifier("primaryDataSourceProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder().build();
    }

    @Bean(name = "replicaTargetDataSource")
    DataSource replicaTargetDataSource(
            @Qualifier("replicaDataSourceProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder().build();
    }

    @Bean(name = "routingDataSource")
    DataSource routingDataSource(
            @Qualifier("primaryTargetDataSource") DataSource primary,
            @Qualifier("replicaTargetDataSource") DataSource replica) {
        Map<Object, Object> targets = new HashMap<>();
        targets.put(DataSourceRoute.PRIMARY, primary);
        targets.put(DataSourceRoute.REPLICA, replica);

        ReadWriteRoutingDataSource routing = new ReadWriteRoutingDataSource();
        routing.setTargetDataSources(targets);
        routing.setDefaultTargetDataSource(primary);
        routing.setLenientFallback(false);
        routing.afterPropertiesSet();
        return routing;
    }

    @Bean
    @Primary
    DataSource dataSource(@Qualifier("routingDataSource") DataSource routingDataSource) {
        return new LazyConnectionDataSourceProxy(routingDataSource);
    }
}
```

`@Primary` ensures Spring Boot JPA auto-configuration selects the routed datasource. Both target datasources can still be injected individually via `@Qualifier` for migrations, health checks, or test fixtures. Do not inject raw targets into Repositories or `EntityManagerFactory` if JPA queries are meant to pass through routing.

Example test configuration in `src/test/resources/application-test.properties`:

```properties
app.datasource.primary.url=jdbc:h2:mem:primarydb;DB_CLOSE_DELAY=-1
app.datasource.primary.username=sa
app.datasource.primary.password=
app.datasource.primary.driver-class-name=org.h2.Driver

app.datasource.replica.url=jdbc:h2:mem:replicadb;DB_CLOSE_DELAY=-1
app.datasource.replica.username=sa
app.datasource.replica.password=
app.datasource.replica.driver-class-name=org.h2.Driver

spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
spring.jpa.hibernate.ddl-auto=none
spring.jpa.open-in-view=false
spring.sql.init.mode=never
```

The two URLs point to two independent H2 databases. In production, replace URLs, credentials, and pool settings with securely managed configuration. Never use the same H2 database name for both targets if the goal of the test is to prove they are separate.

With a real replica, schema and data are normally synced from primary via replication. The H2 example does not replicate automatically; tests seed distinct marker data in each database to confirm routing.

## 6. Entities and Repositories sharing the routing datasource

Example entity:

`src/main/java/com/example/multidb/Product.java`:

```java
package com.example.multidb;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 40)
    private String sku;

    @Column(nullable = false, length = 160)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(String sku, String name, BigDecimal price) {
        if (sku == null || sku.isBlank() || sku.length() > 40) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (name == null || name.isBlank() || name.length() > 160) {
            throw new IllegalArgumentException("Name is required");
        }
        if (price == null || price.signum() < 0) {
            throw new IllegalArgumentException("Price must be zero or greater");
        }
        this.sku = sku.trim();
        this.name = name.trim();
        this.price = price;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public BigDecimal getPrice() { return price; }
}
```

Write-capable Command Repository:

```java
package com.example.multidb;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductCommandRepository extends JpaRepository<Product, Long> {
    Optional<Product> findBySku(String sku);
}
```

Read Repository exposing only read queries and returning projections:

`src/main/java/com/example/multidb/ProductView.java`:

```java
package com.example.multidb;

import java.math.BigDecimal;

public interface ProductView {
    String getSku();
    String getName();
    BigDecimal getPrice();
}
```

```java
package com.example.multidb;

import java.util.Optional;
import org.springframework.data.repository.Repository;

public interface ProductReadRepository extends Repository<Product, Long> {
    Optional<ProductView> findBySku(String sku);
}
```

`ProductReadRepository` extends the marker `Repository` instead of `JpaRepository`, so its public API has no `save()` or `delete()`. This is a helpful code boundary; database write permissions must still be managed separately if strict enforcement is required.

## 7. Placing transactions in Services

Query Service marks transactions read-only so the routing datasource selects the replica:

```java
package com.example.multidb;

import java.util.Optional;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductQueryService {
    private final ProductReadRepository repository;

    public ProductQueryService(ProductReadRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Optional<ProductView> findBySku(String sku) {
        return repository.findBySku(sku);
    }
}
```

Command Service uses write transactions and goes to the primary:

```java
package com.example.multidb;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {
    private final ProductCommandRepository repository;

    public ProductCommandService(ProductCommandRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long create(String sku, String name, BigDecimal price) {
        Product saved = repository.saveAndFlush(new Product(sku, name, price));
        return saved.getId();
    }

    @Transactional
    public void createThenFail(String sku, String name, BigDecimal price) {
        repository.saveAndFlush(new Product(sku, name, price));
        throw new IllegalStateException("Simulated failure after insert");
    }
}
```

The `createThenFail` method flushes the insert to the database before throwing a runtime exception. The transaction interceptor still rolls back the transaction when the exception escapes the method, allowing tests to verify the row was never committed.

Place `@Transactional` on public methods invoked through a Spring proxy. Self-invocation—for instance, one method inside the same class calling another `@Transactional` method—normally bypasses the proxy and may fail to apply the transaction annotation as expected.

## 8. Testing routing using marker data

To prove queries genuinely hit the replica, seed the two databases with distinct SKUs:

- Primary contains only `PRIMARY-ONLY`.
- Replica contains only `REPLICA-ONLY`.

If the Query Service routes properly, it finds `REPLICA-ONLY` and does not find `PRIMARY-ONLY`. If it misroutes to primary, the first assertion fails.

The integration test uses `@SpringBootTest` to initialize the full routing configuration, JPA repositories, and transaction proxies:

`src/test/java/com/example/multidb/DataSourceRoutingIntegrationTest.java`:

```java
package com.example.multidb;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import javax.sql.DataSource;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class DataSourceRoutingIntegrationTest {
    @Autowired
    private ProductQueryService queries;

    @Autowired
    private ProductCommandService commands;

    @Autowired
    @Qualifier("primaryTargetDataSource")
    private DataSource primary;

    @Autowired
    @Qualifier("replicaTargetDataSource")
    private DataSource replica;

    private JdbcTemplate primaryJdbc;
    private JdbcTemplate replicaJdbc;

    @BeforeEach
    void prepareDatabases() {
        primaryJdbc = new JdbcTemplate(primary);
        replicaJdbc = new JdbcTemplate(replica);
        prepare(primaryJdbc, "PRIMARY-ONLY", "Primary row");
        prepare(replicaJdbc, "REPLICA-ONLY", "Replica row");
    }

    private void prepare(JdbcTemplate jdbc, String sku, String name) {
        jdbc.execute("""
                create table if not exists products (
                    id bigint generated by default as identity primary key,
                    sku varchar(40) not null unique,
                    name varchar(160) not null,
                    price decimal(12,2) not null
                )
                """);
        jdbc.update("delete from products");
        jdbc.update(
                "insert into products(sku, name, price) values (?, ?, ?)",
                sku, name, new BigDecimal("10.00"));
    }

    private int count(JdbcTemplate jdbc, String sku) {
        return jdbc.queryForObject(
                "select count(*) from products where sku = ?", Integer.class, sku);
    }

    @Test
    void readOnlyTransactionUsesReplica() {
        assertThat(queries.findBySku("REPLICA-ONLY")).isPresent();
        assertThat(queries.findBySku("PRIMARY-ONLY")).isEmpty();
    }

    @Test
    void writeTransactionUsesPrimaryOnly() {
        commands.create("NEW-001", "Created product", new BigDecimal("25.00"));

        assertThat(count(primaryJdbc, "NEW-001")).isEqualTo(1);
        assertThat(count(replicaJdbc, "NEW-001")).isZero();
    }

    @Test
    void runtimeExceptionRollsBackThePrimaryWrite() {
        assertThatThrownBy(() -> commands.createThenFail(
                "ROLLBACK-001", "Temporary product", new BigDecimal("30.00")))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("Simulated failure after insert");

        assertThat(count(primaryJdbc, "ROLLBACK-001")).isZero();
        assertThat(count(replicaJdbc, "ROLLBACK-001")).isZero();
    }
}
```

The test creates the schema on both databases because they are two independent H2 databases without automatic replication. `JdbcTemplate` in the test fixture connects directly to the qualified target datasources; the JPA Repositories continue using the primary routed datasource.

`readOnlyTransactionUsesReplica` confirms routing via differing data in the two sources. `writeTransactionUsesPrimaryOnly` confirms the insert appears only in primary. The rollback test confirms the flushed insert does not exist after the transaction terminates via exception.

Run the tests:

```bash
mvn test
```

The expected outcome is Maven finishing with `BUILD SUCCESS` and all three tests passing. This is the expected outcome of the example, not a build log executed in a live environment.

## 9. Testing transaction isolation levels

Transaction isolation level is a property of the database transaction, not primary/replica selection. Spring lets you declare isolation on `@Transactional`:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.READ_COMMITTED)
public void updateCatalog() {
    // Read and write within the same transaction.
}
```

Common isolation levels:

| Spring Isolation | General Meaning |
| --- | --- |
| `DEFAULT` | Uses the database/transaction manager's default level. |
| `READ_UNCOMMITTED` | May allow reading uncommitted data if supported by the database. |
| `READ_COMMITTED` | Prevents dirty reads; subsequent reads may observe newer commits. |
| `REPEATABLE_READ` | Preserves repeatable row reads per database semantics; phantom behavior varies by engine. |
| `SERIALIZABLE` | High isolation level; database may lock or abort transactions to guarantee serializability. |

Example using `TransactionTemplate` to choose isolation in tests or orchestration code:

```java
TransactionTemplate transaction = new TransactionTemplate(transactionManager);
transaction.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);

transaction.executeWithoutResult(status -> {
    // Perform JDBC/JPA operations participating in this transaction.
});
```

To genuinely test isolation, you need two independent transactions coordinated by a latch/barrier: transaction A reads, transaction B writes and commits, then A reads again. The result of the second read depends on the isolation level and database engine. Never use a single persistence context to simulate two transactions.

Isolation is set when a new transaction starts. If a method joins an existing transaction, an isolation level declared on the inner method normally does not change the outer transaction's isolation. To detect incompatible configurations, enable `validateExistingTransaction` on the transaction manager or design separate transaction boundaries.

Do not choose `SERIALIZABLE` by default for every query; it can increase contention, lock waits, or serialization failures. Choose based on business needs and benchmark on the real database.

## 10. Isolating data across sources and tenants

In the example, primary and replica are two separate databases. Marker tests prove query routes do not read the wrong target and commands do not write to the replica. This tests physical source isolation.

If a system uses a separate database per tenant, the routing key typically must contain the authenticated tenant. A simple pattern uses thread-bound context:

```java
package com.example.multidb;

public final class TenantContext {
    private static final ThreadLocal<String> CURRENT = new ThreadLocal<>();

    private TenantContext() {
    }

    public static void set(String tenantId) {
        if (tenantId == null || tenantId.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        CURRENT.set(tenantId);
    }

    public static String getRequired() {
        String tenantId = CURRENT.get();
        if (tenantId == null) {
            throw new IllegalStateException("Tenant context is missing");
        }
        return tenantId;
    }

    public static void clear() {
        CURRENT.remove();
    }
}
```

A tenant routing datasource can use `TenantContext.getRequired()` as its lookup key. Context must be set after authentication and before opening a transaction, then always cleared in `finally` or a request filter. Never trust an arbitrary tenant ID sent by the client without checking access permissions.

For async executors, schedulers, or message listeners, `ThreadLocal` does not propagate automatically to other threads. Pass tenant context explicitly and clear it after processing; without this step, thread pools can retain a previous request's context and leak data across tenants.

Tenant isolation integration tests should seed the same SKU into two tenant databases with different names/prices, set tenant context A and then B, and verify each context sees only its own source's record. Also test that missing tenant context fails closed rather than routing to a default tenant.

Datasource-level tenant isolation does not replace authorization. The application still must authenticate the tenant and restrict user actions within that tenant. If sharing one database and separating via `tenant_id`, every query must apply a tenant predicate or a controlled, tested filtering mechanism.

## 11. Multiple DataSources and transaction managers

Primary/replica routing above uses a single `EntityManagerFactory` and a single transaction manager working with one routing DataSource. Each transaction picks one target connection.

If an application has two independent databases that both need writes in one business operation, a regular `JpaTransactionManager` manages only one `EntityManagerFactory`/DataSource. Two separate local transaction managers do not automatically create an atomic transaction across both databases.

Options:

- If you only need to write to one source and sync the other asynchronously, use transactional outbox and idempotent consumers.
- If distributed commit/rollback across multiple resources is genuinely needed, evaluate JTA/XA and its operational overhead.
- If the business accepts eventual consistency, use saga/compensation and track step-by-step state.

Never call two services using different transaction managers and assume an outer `@Transactional` will roll back both databases. Explicitly specify transaction managers by qualifier when configuring multiple persistence units, e.g., `@Transactional("ordersTransactionManager")`, and design a coordination mechanism when cross-database atomicity is required.

## 12. Common routing and transaction mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Read-only queries still hit primary | Physical connection acquired before read-only metadata is ready. | Wrap the routing datasource with `LazyConnectionDataSourceProxy` and test with two distinct marker sources. |
| Commands write to replica | Method marked read-only or wrong default route key. | Use write `@Transactional`, set primary as default target, and test inserts directly against both sources. |
| `readOnly = true` does not route automatically | No routing datasource inspects transaction metadata. | Implement `AbstractRoutingDataSource`; readOnly is only a hint without routing logic. |
| Connection switches source mid-transaction | Code modifies route context after connection was acquired. | Select route before the transaction and keep it fixed until commit/rollback. |
| Test reads rows from both databases | Two targets accidentally point to the same URL or fixture seeds wrong source. | Use distinct database names, inject qualifiers, and verify URLs/configs in tests. |
| Rollback test still sees the row | Service bypassed transaction proxy, exception was caught, or method is non-transactional. | Call a public Service bean, let the exception escape, and read back on a fresh connection. |
| Replica query returns stale data | Asynchronous replication or replica lag. | Define read-your-writes; temporarily route to primary or return command result. |
| Two databases do not roll back together | Two local transaction managers used without a distributed transaction. | Use JTA/XA when atomicity is required or outbox/saga when eventual consistency is acceptable. |
| Tenant A sees tenant B's data | Missing/stale tenant context or query missing tenant predicate. | Fail closed, authenticate tenant, clear context in `finally`, and test cross-tenant access. |
| Flaky transaction isolation test | Shared EntityManager or reliance on fixed timing sleeps. | Use independent transactions, latches/barriers, and production database engines for critical tests. |

## 13. Reliable testing workflow

1. Use two test databases with distinct URLs/names; never let two targets point to the same source accidentally.
2. Create schemas and seed distinct marker data per source.
3. Call Query Service through a Spring proxy with `@Transactional(readOnly = true)` and confirm only the replica marker is seen.
4. Call Command Service with a write transaction and confirm rows appear only in primary.
5. Force a command to flush and then throw a runtime exception; verify no data remains after rollback.
6. Read back directly from each target via qualifiers so routing logic itself cannot mask bugs.
7. Test replica lag/read-your-writes if production uses asynchronous replication.
8. If using tenant routing, test each tenant, missing tenant context, and context cleanup after requests.
9. If isolation levels matter, coordinate two independent transactions and run tests against the real database engine.
10. If multiple databases must be written in one business operation, test mid-step failures and verify XA/outbox/saga behavior.

## 14. H2 and production databases

H2 is suitable for verifying lookup keys, bean configuration, basic repository queries, and rollbacks in a lightweight setup. However, H2 cannot prove:

- Real replica lag or read-replica behavior.
- Locking, isolation, deadlocks, and timeouts matching PostgreSQL/MySQL/SQL Server.
- Production connection pool limits and failover.
- JDBC driver behavior and SQL dialects of the target deployment database.

Where routing/transactions affect correctness, supplement tests with Testcontainers running the production database. You can spin up independent primary and replica test containers to verify routing; if replication itself must be simulated, configure real replication or use a test environment with matching sync behavior.

## 15. Completion checklist

- [ ] Can explain routing datasources and lookup keys.
- [ ] Used `AbstractRoutingDataSource` to select primary/replica.
- [ ] Understand why `LazyConnectionDataSourceProxy` is required when routing by transaction metadata.
- [ ] Placed `@Transactional(readOnly = true)` on Query Service and write transactions on Command Service.
- [ ] Verified queries read from replica using distinct markers.
- [ ] Verified commands write to primary and not to replica.
- [ ] Tested rollback after a flushed insert.
- [ ] Distinguished data source routing from transaction isolation levels.
- [ ] Tested tenant/data isolation and fail-closed behavior on missing context.
- [ ] Understand `ThreadLocal` does not propagate automatically across async threads.
- [ ] Know that a local transaction manager does not guarantee atomicity across two databases.
- [ ] Selected outbox/saga or JTA/XA according to consistency requirements.
- [ ] Added Testcontainers where database-specific behavior affects business correctness.

Once completed, you can reliably test connection routing, data boundaries, and commit/rollback behavior in Spring Data JPA applications using multiple data sources.