# Multiple DataSources: Separating Repositories, Templates, and Transaction Managers

An application using **Spring Data Relational JDBC** can work with multiple databases or multiple data sources. For example, orders reside in the orders database, inventory resides in the inventory database, and reporting data is read from a dedicated source. In such setups, each repository group must use its corresponding `DataSource`, JDBC operations, and transaction manager.

The key point is that **a repository does not automatically pick a database based solely on aggregate type**. Repository configuration must be bound to the appropriate persistence bean group. When the application injects `JdbcAggregateTemplate` directly, the template must also be constructed from the right data source's infrastructure. When multiple transaction managers exist, services must explicitly specify which manager their transactions use.

This lesson covers separating repository packages, configuring multiple `DataSource`s, `NamedParameterJdbcOperations`, transaction managers, and aggregate templates, selecting the manager in `@Transactional`, and the limitations when a single use case writes to multiple databases.

## 1. When does an application need multiple DataSources?

An application may connect to multiple data sources for reasons such as:

- Bounded contexts use separate databases, such as orders and inventory.
- One database serves transactions while another serves reporting.
- The application reads from a legacy system while writing new data into a new database.
- Tenants are partitioned into separate databases.
- Certain tables are managed by a dedicated database or schema.

Architectural example:

~~~text
OrderApplicationService
    |
    +--> PurchaseOrderRepository
    |       |
    |       +--> ordersDataSource
    |               |
    |               +--> ordersTransactionManager
    |
    +--> InventoryRepository
            |
            +--> inventoryDataSource
                    |
                    +--> inventoryTransactionManager
~~~

Each repository is configured to use the right JDBC operations and transaction manager. If configuration is ambiguous, Spring may not know which bean to inject or a repository may access the wrong database.

### 1.1. Distinguishing multiple DataSources from multiple schemas

Two schemas in the same database do not necessarily require two `DataSource`s. If both repository groups can share the same connection pool, transaction manager, and schema routing mechanism, a single DataSource may suffice.

Conversely, two separate `DataSource`s normally represent two separate connection resources. Even if both beans point to the same database server URL, two distinct connection pools still create two distinct transactional resources.

Start from actual transaction boundaries and operational requirements to decide whether to split DataSources or only split schemas.

## 2. Components that must be bound to each DataSource

In Spring Data JDBC, a data source configuration typically includes these components:

| Component | Role |
|---|---|
| `DataSource` | Supplies JDBC connections to the database |
| `NamedParameterJdbcOperations` | Executes SQL with named parameters |
| `PlatformTransactionManager` | Manages transactions on the corresponding resource |
| `JdbcMappingContext` | Holds relational mapping metadata |
| `JdbcConverter` | Converts values between domain and JDBC |
| `DataAccessStrategy` | Executes aggregate read/write operations |
| `JdbcAggregateTemplate` | Direct aggregate persistence API |
| Repository | Aggregate-root persistence API |

The first three beans must be clearly distinguished when multiple data sources exist. Mapping and aggregate operation components must also match the DataSource, dialect, and mapping configuration they use.

If two databases use the exact same schema, dialect, and domain mapping, some metadata may be shared depending on configuration. If dialects, naming strategies, custom conversions, or mappings differ, the corresponding infrastructure must be separated. Never use a `DataAccessStrategy` built for database A to operate on database B.

## 3. Separating repository packages by data source

A straightforward organization puts each database's repositories in a dedicated package:

~~~text
com.example
├── orders
│   ├── domain
│   └── repository
│       └── PurchaseOrderRepository.java
├── inventory
│   ├── domain
│   └── repository
│       └── InventoryRepository.java
└── config
    ├── OrdersJdbcConfiguration.java
    └── InventoryJdbcConfiguration.java
~~~

Separate packages let each `@EnableJdbcRepositories` configuration scan its intended repository group. Never let two configurations scan the same repository package, as a repository interface could be registered twice against different infrastructures.

Example repositories:

~~~java
package com.example.orders.repository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

~~~java
package com.example.inventory.repository;

public interface InventoryRepository
        extends CrudRepository<InventoryItem, Long> {
}
~~~

Both repositories extend `CrudRepository`, yet they are bound to different data source configurations.

## 4. Declaring two DataSources

Example using Spring Boot and `DataSourceBuilder` to create two distinct beans:

~~~java
import javax.sql.DataSource;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DataSourceConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource.orders")
    DataSource ordersDataSource() {
        return DataSourceBuilder.create().build();
    }

    @Bean
    @ConfigurationProperties("app.datasource.inventory")
    DataSource inventoryDataSource() {
        return DataSourceBuilder.create().build();
    }
}
~~~

Example properties configuration:

~~~yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders_db
      username: orders_app
      password: ORDERS_DB_PASSWORD_FROM_SECRET_STORE
      driver-class-name: org.postgresql.Driver
    inventory:
      url: jdbc:postgresql://localhost:5432/inventory_db
      username: inventory_app
      password: INVENTORY_DB_PASSWORD_FROM_SECRET_STORE
      driver-class-name: org.postgresql.Driver
~~~

Property prefixes and binding details depend on application configuration. If using HikariCP or another specific pool, you can declare beans of that pool type to configure pool sizes, timeouts, and connection properties.

Never put real credentials directly in committed configuration files. Use environment variables or your deployment environment's secret management.

## 5. Creating separate JDBC operations and transaction managers

Each DataSource needs a `NamedParameterJdbcOperations` and a transaction manager bound to that exact DataSource:

~~~java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcOperations;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class JdbcResourceConfiguration {

    @Bean
    NamedParameterJdbcOperations ordersJdbcOperations(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    NamedParameterJdbcOperations inventoryJdbcOperations(
            @Qualifier("inventoryDataSource") DataSource dataSource) {
        return new NamedParameterJdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager inventoryTransactionManager(
            @Qualifier("inventoryDataSource") DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
~~~

`JdbcTransactionManager` is available in Spring Framework releases supporting that class; in older versions, `DataSourceTransactionManager` can be used. Both are JDBC transaction managers, so use the API present in your project's dependencies.

Critically, each pair of beans must point to the same DataSource:

- `ordersJdbcOperations` uses `ordersDataSource`.
- `ordersTransactionManager` uses `ordersDataSource`.
- `inventoryJdbcOperations` uses `inventoryDataSource`.
- `inventoryTransactionManager` uses `inventoryDataSource`.

Never pair the orders transaction manager with inventory JDBC operations. Otherwise, the transaction may fail to govern the SQL statements the application assumes it manages.

## 6. Binding repositories to the right JDBC operations and transaction manager

`@EnableJdbcRepositories` lets you specify the repository package, JDBC operations bean, and transaction manager bean:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;

@Configuration
@EnableJdbcRepositories(
    basePackages = "com.example.orders.repository",
    jdbcOperationsRef = "ordersJdbcOperations",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersRepositoryConfiguration {
}
~~~

~~~java
@Configuration
@EnableJdbcRepositories(
    basePackages = "com.example.inventory.repository",
    jdbcOperationsRef = "inventoryJdbcOperations",
    transactionManagerRef = "inventoryTransactionManager"
)
public class InventoryRepositoryConfiguration {
}
~~~

The two configurations separate repository scanning and explicitly specify the two required beans. Attribute names and additional infrastructure options should be verified against your project's Spring Data JDBC version; the pattern above illustrates binding a repository group to its matching JDBC operations and transaction manager.

If the application uses `AbstractJdbcConfiguration`, ensure mapping context, converters, dialect, and data access strategy are created consistently for each data source. Do not create multiple base configurations with identical default bean names without controlling bean naming and dependency injection.

## 7. Injecting repositories and transaction managers in services

Once repositories are registered by package, services can inject them as normal dependencies:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Long createOrder(CreateOrderCommand command) {
        PurchaseOrder saved = orders.save(
            PurchaseOrder.create(command)
        );
        return saved.getId();
    }
}
~~~

The inventory service selects its own transaction manager:

~~~java
@Service
public class InventoryService {

    private final InventoryRepository inventory;

    public InventoryService(InventoryRepository inventory) {
        this.inventory = inventory;
    }

    @Transactional(transactionManager = "inventoryTransactionManager")
    public void reserve(Long productId, int quantity) {
        InventoryItem item = inventory.findById(productId)
            .orElseThrow();

        item.reserve(quantity);
        inventory.save(item);
    }
}
~~~

When multiple transaction managers exist, explicitly specify `transactionManager` in `@Transactional`. Omitting this attribute forces Spring to choose a default manager, typically based on a primary bean or default name. Relying on implicit selection can cause a service to run its transaction on the wrong DataSource.

### 7.1. Can @Primary be used?

You can mark one DataSource or transaction manager as `@Primary` to serve as the default when multiple beans of the same type exist. This helps if most of the application targets one primary database.

However, `@Primary` does not remove the need to specify the manager on services targeting the other data sources. Important use cases should explicitly state which resource the transaction manages.

## 8. Using JdbcAggregateTemplate per DataSource

`JdbcAggregateTemplate` is the aggregate-level persistence API. When an application has multiple databases and needs to inject the template directly, each template must be tied to its corresponding database's infrastructure.

For example, a service can receive two clearly named templates:

~~~java
@Service
public class AggregateMaintenanceService {

    private final JdbcAggregateOperations ordersOperations;
    private final JdbcAggregateOperations inventoryOperations;

    public AggregateMaintenanceService(
            @Qualifier("ordersJdbcAggregateTemplate")
            JdbcAggregateOperations ordersOperations,
            @Qualifier("inventoryJdbcAggregateTemplate")
            JdbcAggregateOperations inventoryOperations) {
        this.ordersOperations = ordersOperations;
        this.inventoryOperations = inventoryOperations;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public PurchaseOrder insertOrder(PurchaseOrder order) {
        return ordersOperations.insert(order);
    }

    @Transactional(transactionManager = "inventoryTransactionManager")
    public InventoryItem insertInventoryItem(InventoryItem item) {
        return inventoryOperations.insert(item);
    }
}
~~~

In this example, `JdbcAggregateOperations` is the aggregate-operations abstraction; the bean implementation can be `JdbcAggregateTemplate`. The bean names in `@Qualifier` match the names registered by the application configuration.

### 8.1. Each template must use the right DataAccessStrategy

Merely giving two template beans different names is not enough. Each template must be built from the persistence components of the matching database:

~~~text
ordersJdbcAggregateTemplate
    ├── orders mapping/conversion configuration
    ├── orders DataAccessStrategy
    └── orders JDBC operations

inventoryJdbcAggregateTemplate
    ├── inventory mapping/conversion configuration
    ├── inventory DataAccessStrategy
    └── inventory JDBC operations
~~~

If the orders template is constructed with the inventory `DataAccessStrategy`, the template may read or write the wrong database even if the service specified `ordersTransactionManager`.

Constructor signatures and how `JdbcAggregateTemplate` is created depend on your Spring Data JDBC version and infrastructure setup. When declaring templates explicitly, use the `JdbcMappingContext`, `JdbcConverter`, and `DataAccessStrategy` beans configured for that exact DataSource; never take a default template and pair it with another transaction manager.

A bean factory method can clearly wire the dependencies for the orders database:

~~~java
@Bean("ordersJdbcAggregateTemplate")
JdbcAggregateOperations ordersJdbcAggregateTemplate(
        ApplicationContext applicationContext,
        @Qualifier("ordersJdbcMappingContext")
        JdbcMappingContext mappingContext,
        @Qualifier("ordersJdbcConverter")
        JdbcConverter converter,
        @Qualifier("ordersDataAccessStrategy")
        DataAccessStrategy dataAccessStrategy) {

    return new JdbcAggregateTemplate(
        applicationContext,
        mappingContext,
        converter,
        dataAccessStrategy
    );
}
~~~

The inventory database needs a similar factory taking `inventoryJdbcMappingContext`, `inventoryJdbcConverter`, and `inventoryDataAccessStrategy`. Those mapping context, converter, and strategy beans must be configured separately or intentionally shared when metadata is genuinely compatible. Creating `DataAccessStrategy` depends on the dialect and API of your Spring Data JDBC version; the snippet above demonstrates assembling the template with the right pre-configured beans rather than replacing the framework's entire underlying setup.

### 8.2. When to use repositories instead of injecting a template?

If a use case only needs standard CRUD, a per-database configured repository is sufficient:

~~~java
orders.save(order);
inventory.save(item);
~~~

Only inject `JdbcAggregateTemplate` when direct aggregate operations such as `insert`, `update`, or `findById` by domain type are needed, or when building a generic infrastructure adapter. The template does not handle transaction manager selection itself; services must still pick the right manager.

## 9. Mapping context, converters, and dialects

When multiple databases exist, evaluate whether they share the same relational model.

| Component | Can be shared when | Should be separated when |
|---|---|---|
| `JdbcMappingContext` | Domain mappings, naming strategies, and metadata match | Mappings or naming strategies differ |
| `JdbcConverter` | Conversion rules and JDBC mappings are compatible | Custom conversions or mappings differ |
| `JdbcCustomConversions` | Both sources need the exact same set of converters | Storage types or conversion rules differ |
| `JdbcDialect` | Databases use the same dialect | Databases use different DBMSs or dialects |
| `DataAccessStrategy` | Same resource and same mapping infrastructure | Each DataSource needs separate operations |
| `JdbcAggregateTemplate` | Same data access strategy and resource | Each database has its own strategy |

For instance, orders uses PostgreSQL while inventory uses another DBMS. The two databases may differ in ID generation, identifier quoting, array support, or SQL syntax. In that case, do not assume a single dialect works properly for both.

If both sources are PostgreSQL using identical domain mappings, some metadata configuration can be shared. Even then, each `DataAccessStrategy` must still be bound to its corresponding DataSource's JDBC operations.

## 10. Transactions when one use case writes to two DataSources

This is the most critical limitation of multi-database setups.

Suppose a use case needs to:

1. Create an order in the orders database.
2. Decrement stock in the inventory database.

Code:

~~~java
@Service
public class CheckoutService {

    private final OrderService orders;
    private final InventoryService inventory;

    public CheckoutService(
            OrderService orders,
            InventoryService inventory) {
        this.orders = orders;
        this.inventory = inventory;
    }

    public Long checkout(CreateOrderCommand command) {
        Long orderId = orders.createOrder(command);
        inventory.reserve(
            command.productId(),
            command.quantity()
        );
        return orderId;
    }
}
~~~

`orders.createOrder()` uses `ordersTransactionManager`; `inventory.reserve()` uses `inventoryTransactionManager`. Two transaction managers govern two separate transactions.

If order creation commits successfully but inventory reservation fails, the orders database does not automatically roll back with the inventory transaction. Calling two services sequentially does not merge two transactions into one atomic transaction.

### 10.1. @Transactional on the caller does not merge two transaction managers

You cannot achieve atomicity across two DataSources simply by adding:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void checkout(...) {
    orders.createOrder(...);
    inventory.reserve(...);
}
~~~

The annotation on the caller manages only the `ordersTransactionManager` transaction. The inventory transaction must still be managed separately if the inventory service opens a transaction with another manager.

Likewise, `REQUIRED` only joins an existing transaction managed by the same transaction manager/resource. `REQUIRED` on a different transaction manager does not join the first database's JDBC transaction.

### 10.2. Options when consistency across two databases is required

**Accept separate transactions with compensation:** each database commits independently. If the second step fails, the application executes a compensating action, such as canceling the created order or releasing the reservation.

**Saga or workflow:** model the multi-step flow with explicit states. Each step commits locally and defines compensating actions on downstream failures. This fits long-running flows and multi-service processes.

**Outbox and messaging:** persist aggregate changes alongside an outbox event within the aggregate-owning database's transaction. A worker publishes the event and another service updates the other database. Requires designing retries, idempotency, and processing states.

**Distributed transaction/XA:** if the system and databases support XA/JTA, a transaction coordinator can manage multiple resources within one global transaction. This increases operational complexity, requires compatible drivers/resources, and can affect performance/availability. Not all DataSources support XA.

Never treat an ordinary JDBC transaction manager as if it automatically coordinates multiple DataSources. Choose a consistency mechanism based on business requirements and operational capabilities.

## 11. Transaction managers, propagation, and cross-service calls

Within the same database, services using the same transaction manager and `REQUIRED` propagation can participate in one physical transaction:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public void createOrder(...) {
    orderRepository.save(...);
    orderLineService.addLines(...);
}
~~~

If `orderLineService` also uses `ordersTransactionManager` with `REQUIRED`, it joins the active transaction.

If the called service uses `inventoryTransactionManager`, it operates on a different transactional resource. `REQUIRED` on that service does not turn it into a sub-transaction of orders.

For a service needing an independent transaction on the same database, `REQUIRES_NEW` can be used with the matching transaction manager. However, consider connection pool usage, locking, and consistency as covered in the propagation lesson.

## 12. Reading from another database

Many applications use a transactional database for writes and a read replica or reporting database for reads. Repositories can be organized into two packages:

~~~text
orders.repository.write
orders.repository.read
~~~

or separated more clearly into modules by responsibility. Read repositories must bind to the corresponding read DataSource. If the read replica has replication lag, newly written data may not appear immediately when read from the replica.

Do not assume a transaction commit on primary makes data instantly visible on a read replica. If a use case requires read-your-writes, read from primary for a window or use an appropriate routing mechanism.

For reporting databases with aggregated schemas, DTOs/projections and `NamedParameterJdbcTemplate` may fit better than loading transactional aggregates.

## 13. Dynamic routing DataSource for tenants

If multiple tenants share the same schema and mapping structure while each tenant has its own database, consider `AbstractRoutingDataSource` rather than declaring a separate repository group per tenant.

Model:

~~~text
Repository
    |
    v
Routing DataSource
    |
    +--> tenant A DataSource
    +--> tenant B DataSource
    +--> tenant C DataSource
~~~

The routing DataSource picks the target DataSource based on context, typically a tenant ID established prior to acquiring a connection.

Key considerations:

- Tenant context must be set before the transaction acquires a connection.
- Never switch tenants mid-transaction.
- Clear context after the request/task to prevent tenant leakage into subsequent threads or requests.
- Every tenant must have a schema compatible with the active mappings.
- Control connection pools and total DataSource count when tenant count grows large.

If tenants have differing schemas, dialects, or lifecycles, a single routing DataSource may not suffice; separate persistence configurations or another architecture may be required.

## 14. Migrations and operating multiple databases

With multiple DataSources, schema migrations must also target the right database.

For example:

| Database | Responsible migrations |
|---|---|
| orders | Tables purchase_orders, order_lines, order_audit |
| inventory | Tables inventory_items, stock_reservations |
| reporting | Reporting views or aggregated tables |

Each migration tool must be configured with the right DataSource and schema. Do not let orders migrations accidentally run against inventory due to picking up a default bean.

Operations must also monitor each source separately:

- Connection pool per DataSource.
- Transaction timeouts and lock timeouts.
- Health checks and connection state.
- Credentials and access permissions per database.
- Backups/restores and retention.
- Migration version of each database.
- Error metrics and query latency per source.

One database failing does not necessarily bring down the other, but the application must define how to handle partial use-case failures.

## 15. Common pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Cannot inject DataSource | Multiple beans of same type without qualifier/primary | Use `@Qualifier` or `@Primary` deliberately |
| Repository connects to wrong database | Misconfigured package scan or `jdbcOperationsRef` | Separate packages and specify JDBC operations explicitly |
| Transaction fails to roll back SQL | Transaction manager uses a different DataSource than JDBC operations | Pair matching DataSource and manager |
| `@Transactional` picks wrong manager | Relying on default when multiple managers exist | Specify `transactionManager` explicitly |
| Repository registered twice | Two configurations scan the same package | Partition `basePackages` without overlap |
| Template operates on wrong database | Using `DataAccessStrategy`/JDBC operations of another source | Build template from matching infrastructure |
| Duplicate mapping context bean name | Multiple base configurations register identical default bean names | Control bean naming and mapping configuration |
| Custom converter works on only one database | Converter registered only in one infrastructure | Register converter in the right `JdbcCustomConversions` |
| Dialect generates unsuitable SQL | Sharing dialect across different DBMSs | Configure dialect per data source |
| Single transaction fails to roll back both databases | Two independent JDBC transaction managers | Use Saga/outbox or XA/JTA if truly needed |
| Replica reads miss newly written data | Replication lag | Read primary for read-your-writes or accept eventual consistency |
| Tenant routed incorrectly | Tenant context changed after connection acquisition or not cleared | Set and clear context properly across lifecycle |
| Migration runs on wrong database | Migration tool uses default DataSource | Configure separate migration per source |

## 16. Workflow for configuring multiple DataSources

When splitting persistence across multiple databases, follow this sequence:

1. **Define data boundaries:** which aggregate groups belong to which database.
2. **Separate repository packages:** each configuration scans a distinct package.
3. **Declare DataSources:** assign clear bean names and property prefixes.
4. **Create JDBC operations:** each bean uses the right DataSource.
5. **Create transaction managers:** each manager governs the right DataSource.
6. **Configure repositories:** specify `basePackages`, `jdbcOperationsRef`, and `transactionManagerRef`.
7. **Configure mappings:** verify converters, mapping context, dialect, and data access strategy.
8. **Configure templates:** if used directly, build templates from the matching source's infrastructure.
9. **Select transaction managers:** specify the manager in `@Transactional`.
10. **Define atomicity:** decide how multi-database write use cases are handled.
11. **Verify migrations and operations:** ensure schemas, pools, and health checks are separated per source.
12. **Integration tests:** confirm each repository writes to the right database and rolls back under the right transaction manager.

## 17. Hands-on exercises

### Exercise 1 — Two DataSources and two repository groups

1. Create two databases `orders_db` and `inventory_db`.
2. Create two DataSource beans with distinct names.
3. Create `ordersJdbcOperations` and `inventoryJdbcOperations`.
4. Create two corresponding transaction managers.
5. Separate repository packages.
6. Use two `@EnableJdbcRepositories` configurations to bind repositories to the right sources.
7. Persist data and inspect each database.

### Exercise 2 — Selecting the transaction manager

1. Create `OrderService` using `ordersTransactionManager`.
2. Create `InventoryService` using `inventoryTransactionManager`.
3. Trigger an error after a write operation.
4. Verify transaction rollback occurs on the right database.
5. Try omitting the manager qualifier and observe Spring's default selection.

### Exercise 3 — Two JdbcAggregateTemplates

1. Create separate infrastructures for two databases.
2. Register two templates with different bean names.
3. Inject via `@Qualifier`.
4. Call `insert` on each template.
5. Verify each aggregate is persisted in the right database.

### Exercise 4 — One use case writing two databases

1. Create an order in orders.
2. Update stock in inventory.
3. Cause the inventory operation to fail after orders has committed.
4. Observe why the orders transaction does not automatically roll back.
5. Design a compensating action or outbox/Saga for the flow.

### Exercise 5 — Dedicated read source

1. Configure a read-only or reporting DataSource.
2. Create a reporting read repository/DAO.
3. Perform a write to primary.
4. Observe lag if reading through a replica.
5. Design read-your-writes for a use case needing immediate fresh data.

## 18. Conclusion

With multiple DataSources, separate repositories by package and bind each group to its corresponding `NamedParameterJdbcOperations` and transaction manager. When using `JdbcAggregateTemplate` directly, the template must be constructed from the `DataAccessStrategy`, converters, mapping context, and JDBC operations suited to that database. In services, specify `transactionManager` explicitly so Spring opens transactions on the right resource.

An ordinary JDBC transaction manager governs a single DataSource. Two services using two different managers do not automatically form one atomic transaction, even when called within the same method. If a use case must coordinate multiple databases, design local transactions with compensation, Sagas, or outbox; use XA/JTA only when infrastructure genuinely supports it and requirements demand distributed transactions.

Cleanly separating resources, repository scans, templates, and transaction managers prevents applications from hitting the wrong database, rolling back the wrong scope, or making false assumptions about atomicity. Verify with integration tests against each real database and manage migrations, connection pools, and health checks separately per source.
