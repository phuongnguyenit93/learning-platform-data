# When Multiple DataSources Are Needed in One Application

## 1. What is a DataSource and when do you need more than one?

A `DataSource` is a JDBC connection source to a database. In a typical Spring Data JPA application, one `DataSource` supplies connections to one `EntityManagerFactory`; this factory manages the persistence unit, Entity mappings, and corresponding repositories.

An application may need multiple DataSources when it must work with independent databases, for example:

- A primary transactional business database and a reporting/analytics database.
- An orders database and an accounting database owned by two separate systems.
- A legacy database that needs to be accessed during a migration/transition phase.
- Databases separated by bounded context or security requirements.
- A primary write database and a read replica, if the architecture has an explicit read/write routing policy.

Do not add a DataSource just because there are many tables or schemas. If the tables reside in the same database, share the same transaction boundary, and use common mappings, a single DataSource with one persistence unit is usually simpler. Multiple DataSources entail multiple connection pools, EntityManagerFactories, transaction managers, migrations, and operational rules.

## 2. Distinguishing multiple schemas, multiple databases, and multiple persistence units

These three concepts are related but not synonymous:

| Concept | Meaning | Typical Implementation |
| --- | --- | --- |
| Multiple schemas in one database | Groups of tables reside in different schemas but within the same database/connection | One DataSource; map schemas or use appropriate table/schema names |
| Multiple databases | Databases with separate endpoints, credentials, or transactions | Usually requires one DataSource per database |
| Multiple persistence units | Groups of Entities with separate configurations/providers/lifecycles | Each persistence unit has its own EntityManagerFactory; may use separate or shared DataSources depending on architecture |

If you only need to access `sales.customer` and `sales.order` within the same database, you do not necessarily have to create two DataSources. You can map the schema in `@Table(schema = "sales")` or configure a default schema depending on the provider.

If two groups of Entities require independent transactions, different Hibernate configurations, or different databases, separating persistence units makes the boundaries clearer.

## 3. Each JPA DataSource typically comes with a dedicated set of components

With two independent databases, a common structure is:

```text
Orders database
   |
ordersDataSource
   |
ordersEntityManagerFactory
   |
ordersTransactionManager
   |
Order repositories + Order entities

Analytics database
   |
analyticsDataSource
   |
analyticsEntityManagerFactory
   |
analyticsTransactionManager
   |
Analytics repositories + Analytics entities
```

Each `EntityManagerFactory` manages a separate persistence unit and set of Entities. Each repository group must be bound to the right factory and transaction manager. This separation prevents repositories of database A from accidentally using connections or transactions of database B.

With a fixed two-DataSource configuration, do not let the two repository packages scan each other. Use `@EnableJpaRepositories` to explicitly specify the package, `entityManagerFactoryRef`, and `transactionManagerRef`.

## 4. Configuring properties for two DataSources

Example `application.yml` with two Hikari pools:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders_db
      username: orders_app
      password: ${ORDERS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 12
        minimum-idle: 2
    analytics:
      url: jdbc:postgresql://localhost:5432/analytics_db
      username: analytics_app
      password: ${ANALYTICS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 6
        minimum-idle: 1
```

Put credentials in environment variables or a secret manager instead of committing real passwords to source control. URLs and database names in the example are illustrative only.

`DataSourceProperties` helps bind URL, username, password, and driver. Then `initializeDataSourceBuilder()` creates the specific pool; `@ConfigurationProperties` on the Hikari bean binds the pool options under `configuration`.

## 5. Creating DataSource and EntityManagerFactory for the orders database

The example uses Spring Boot 3+, Jakarta Persistence, and HikariCP. Place the configuration in the application's configuration package; standard imports are omitted to focus on wiring:

```java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = OrderRepository.class,
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders")
    public DataSourceProperties ordersDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders.configuration")
    public HikariDataSource ordersDataSource(
            @Qualifier("ordersDataSourceProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }

    @Bean
    @Primary
    public LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return builder
            .dataSource(dataSource)
            .packages(Order.class)
            .persistenceUnit("orders")
            .properties(Map.of("hibernate.hbm2ddl.auto", "validate"))
            .build();
    }

    @Bean
    @Primary
    public PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory") EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

`basePackageClasses = OrderRepository.class` tells Spring to scan the package containing this repository marker. `.packages(Order.class)` limits Entity scanning for the orders persistence unit. If there are multiple Entity packages, list the corresponding marker classes.

`@Primary` marks the orders set as the default choice when a dependency requires a bean of the same type without a qualifier. This is only a default selection for injection/transaction resolution; it does not combine transactions across the two databases.

`EntityManagerFactoryBuilder` is typically provided by Spring Boot when using JPA auto-configuration. When creating multiple factories manually, check your project's Boot version configuration and avoid unintentionally creating an extra default EntityManagerFactory.

## 6. Creating the configuration set for the analytics database

The second database has its own configuration and is not marked with `@Primary`:

```java
@Configuration
@EnableJpaRepositories(
    basePackageClasses = AnalyticsRepository.class,
    entityManagerFactoryRef = "analyticsEntityManagerFactory",
    transactionManagerRef = "analyticsTransactionManager"
)
public class AnalyticsJpaConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource.analytics")
    public DataSourceProperties analyticsDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.analytics.configuration")
    public HikariDataSource analyticsDataSource(
            @Qualifier("analyticsDataSourceProperties") DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean analyticsEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("analyticsDataSource") DataSource dataSource) {
        return builder
            .dataSource(dataSource)
            .packages(AnalyticsRecord.class)
            .persistenceUnit("analytics")
            .properties(Map.of("hibernate.hbm2ddl.auto", "validate"))
            .build();
    }

    @Bean
    public PlatformTransactionManager analyticsTransactionManager(
            @Qualifier("analyticsEntityManagerFactory") EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Ensure `OrderRepository` and `AnalyticsRepository` reside in separate scan packages. If the same repository is scanned by both configurations, the application may fail to start or the repository may be bound to the wrong persistence unit.

In real-world applications, DataSource creation can be extracted into a shared helper/configuration to reduce duplication, while still keeping bean names, qualifiers, package scans, and persistence units explicit.

## 7. Entities and repositories must belong to the right persistence unit

Example of two repositories:

```java
public interface OrderRepository extends JpaRepository<Order, Long> {
}

public interface AnalyticsRepository extends JpaRepository<AnalyticsRecord, Long> {
}
```

The `Order` Entity is scanned via `.packages(Order.class)` in the orders factory; `AnalyticsRecord` is scanned by the analytics factory. Do not put the same mutable Entity into two EntityManagerFactories unless there is a special reason and you clearly understand the two independent persistence contexts.

An Entity managed by the orders EntityManagerFactory cannot be used directly as a managed association in the analytics persistence unit. If both databases reference the same business object, store the ID or business key in the other database and exchange data via service/event/API.

JPA associations such as `@ManyToOne` and `@OneToMany` do not create joins across two independent persistence units/databases. If you need to aggregate data from both databases, read them separately and combine in the service layer, use a read model, or build an appropriate synchronization pipeline.

## 8. Choosing the right transaction manager

Each `JpaTransactionManager` manages transactions for a single `EntityManagerFactory`. When there are multiple managers, relying solely on `@Transactional` without a qualifier may pick the `@Primary` manager or encounter ambiguity if there is no primary.

Explicitly specify the transaction manager in the service:

```java
@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Order create(Order order) {
        return orders.save(order);
    }
}
```

For analytics:

```java
@Service
public class AnalyticsService {
    private final AnalyticsRepository analytics;

    public AnalyticsService(AnalyticsRepository analytics) {
        this.analytics = analytics;
    }

    @Transactional(transactionManager = "analyticsTransactionManager")
    public AnalyticsRecord record(AnalyticsRecord record) {
        return analytics.save(record);
    }
}
```

The transaction annotation needs to be placed on a method invoked through a Spring proxy, typically a public service method. Self-invocation within the same object bypasses the proxy and may not trigger the transaction as expected.

## 9. Is a method calling two databases automatically atomic?

No. Two local `JpaTransactionManager` instances manage two separate transactions. `@Transactional("ordersTransactionManager")` does not automatically open an atomic transaction spanning the analytics database.

For example, if a service writes to orders and then calls the analytics repository, the analytics operation may run in a separate transaction under the analytics repository's manager. Analytics could commit successfully while the orders transaction rolls back, or vice versa. The result is out-of-sync data between the two databases.

Do not assume:

```java
@Transactional("ordersTransactionManager")
public void placeOrder(...) {
    orders.save(...);
    analytics.save(...); // Does not automatically join the orders transaction.
}
```

This is an example of a non-atomic design. If you must write to both databases as an indivisible unit, you must choose a distributed transaction solution or redesign the workflow.

## 10. When is JTA/XA needed?

JTA with XA-capable resources and an appropriate transaction manager can coordinate transactions across multiple resources using two-phase commit (2PC). This is an option when atomic commit across databases is mandatory and the databases/drivers/cache resources support XA.

In return, the system requires:

- XA DataSources/drivers and a JTA-compliant transaction manager.
- Configuration to enlist resources and persistence units into JTA.
- Transaction logs/recovery and procedures to handle resources failing mid-2PC.
- Monitoring for in-doubt transactions, timeouts, locks, and connection usage.
- Failure/recovery testing in a production-like environment.

JTA/XA carries operational overhead and can hold resource locks longer during transactions. Do not enable XA just because a request touches two repositories. First determine whether simultaneous atomicity is truly required or if eventual consistency can be used.

## 11. When to use Outbox or Saga?

If one database is the primary source of truth and the other is a read model/analytics store, you can often use a local transaction combined with Outbox:

1. Within the orders database transaction, write the Order and an Outbox event into the same database.
2. After commit, a worker reads the Outbox and publishes the event.
3. The consumer updates the analytics database in its own transaction.
4. The consumer processes idempotently so receiving the same event multiple times does not corrupt data.
5. Retry and dead-letter handling aid recovery when the analytics database is temporarily unavailable.

Outbox guarantees that the business change and the event are recorded in the same local transaction. Forwarding the event to the other database happens asynchronously, so this model provides eventual consistency rather than atomic 2PC.

For multi-step workflows that need compensation when a step fails, use Saga: each step commits a local transaction and has an appropriate compensating action. Compensation is a business action, not a physical rollback of an already committed transaction.

## 12. Fixed multiple DataSources vs. Routing DataSource

Fixed multiple DataSources means repository A always uses database A, and repository B always uses database B. This is appropriate when data groups have clear ownership.

`AbstractRoutingDataSource` solves the scenario where a target DataSource must be selected dynamically by a lookup key, such as tenant or read/write routing:

```java
public class TenantRoutingDataSource extends AbstractRoutingDataSource {
    @Override
    protected Object determineCurrentLookupKey() {
        return TenantContext.getCurrentTenant();
    }
}
```

A Routing DataSource is typically configured with a map of target DataSources and a default target. With JPA, it usually sits beneath a shared DataSource/EntityManagerFactory; the route is chosen when a connection is acquired.

Set the tenant/route context before the transaction begins and ensure it is always cleared in `finally`. Never switch routes in the middle of a transaction that has already acquired a connection. Thread-local context must be properly propagated across async/reactive boundaries; do not assume it transfers automatically to other threads.

For complex multi-tenancy or tenant-per-database setups, consider Hibernate multi-tenancy support or a dedicated tenant-aware DataSource architecture. A Routing DataSource does not solve authorization on its own: the server must authenticate the tenant and enforce the tenant context.

## 13. Read replicas and read/write routing

Some systems use a primary database for writes and replicas for reads. A routing DataSource can be used, but you must handle its limitations:

- Replicas may have replication lag, so reading immediately after a write might not reflect the new data yet.
- Read-your-writes may require routing subsequent reads back to the primary.
- A read-only transaction hint does not automatically guarantee the router picks a replica; an explicit routing policy is needed.
- A transaction that has already acquired a connection from the primary cannot safely switch to a replica mid-flight.
- Health checks and failover must avoid routing writes to a replica.

If an API requires the latest data after a write operation, do not send that query to an asynchronous replica unless an appropriate consistency mechanism is in place.

## 14. Migration and schema management per database

Each database has its own schema version and access permissions. When using Flyway or Liquibase, you must ensure migrations run against the right DataSource:

- Create separate migration locations, e.g., `db/migration/orders` and `db/migration/analytics`.
- Configure migration beans with the right DataSource when the application has multiple sources.
- Do not let orders migrations accidentally run on the analytics database.
- Use a database user with the minimum required privileges.
- Test migrations against each deployed database engine/version.

Do not rely on `hibernate.hbm2ddl.auto=update` to synchronize schemas across multiple databases in production. Typically, use `validate` or disable DDL generation, and manage schema changes with versioned migrations.

## 15. Connection pools and resource limits

Each Hikari DataSource typically creates its own connection pool. If orders has a maximum pool of 12 and analytics has a maximum pool of 6, a single application instance can open up to around 18 connections across both pools, excluding administrative, migration, or other component connections.

When running multiple application instances, total potential connections scale with the number of instances. Calculate the system-wide connection budget against database limits.

Size pools according to concurrency and database capacity rather than setting them large just to avoid waiting for connections. Monitor active/idle/pending connections, acquisition timeouts, query latency, and connection leaks. Use distinct metric/health indicator names for each pool to identify which database is bottlenecked.

## 16. Per-persistence-unit Hibernate/JPA configuration

Each EntityManagerFactory can have its own configuration:

- Hibernate dialect/provider properties if needed.
- DDL mode such as `validate`.
- Naming strategy.
- Batch size and JDBC fetch size.
- Second-level cache/region.
- Mapping packages and persistence unit name.

Do not assume every default Boot `spring.jpa.*` property applies identically to all manually created EntityManagerFactories. With multiple factories, bind separate configurations by prefix or pass explicit vendor properties to each builder.

Keep timezone, naming strategy, schema, and cache policies consistent with the corresponding database. An Entity may work in one persistence unit but fail in another if dialects, converters, or schemas differ.

## 17. Testing multiple DataSources

With multiple persistence units, `@DataJpaTest` may be insufficient because the default slice test usually focuses on a single JPA configuration. You can use `@SpringBootTest` with separate test databases/containers for each DataSource, or explicitly import the persistence unit configurations you want to test.

Important tests:

1. Start the context and verify both DataSources/EntityManagerFactories are created.
2. Save an Order via OrderRepository and verify the row exists in the orders database.
3. Save an AnalyticsRecord via AnalyticsRepository and verify the row exists in the analytics database.
4. Verify repository packages are bound to the right EntityManagerFactory.
5. Verify `@Transactional("ordersTransactionManager")` rolls back the orders transaction as expected.
6. Verify analytics transactions are independent and prove that rolling back one database does not automatically roll back the other.
7. Verify Entities are not accidentally managed by the wrong persistence unit.
8. Verify migrations run against the right database.
9. Verify pool shutdown, health checks, and connection leaks.
10. If using XA, test commit, rollback, timeout, and recovery when a resource fails.

Testcontainers with a production-compatible database engine is generally more reliable than relying solely on H2, especially when using native SQL, dialects, schemas, or database-specific migrations.

## 18. Common mistakes and troubleshooting

**Repository uses the wrong database.** Check `basePackageClasses`, `entityManagerFactoryRef`, and `transactionManagerRef` on each `@EnableJpaRepositories`.

**Spring reports multiple DataSources/TransactionManagers and cannot choose a bean.** Mark one default set with `@Primary` where appropriate, and use `@Qualifier` and explicit transaction manager names where clarity is needed.

**Entity not found or `Not a managed type`.** Check `.packages(...)` on the right EntityManagerFactory and the Entity's package.

**Overlapping repository scans.** Separate repository packages or restrict scanning with marker classes; do not let one interface be registered in two configurations.

**`@Transactional` only rolls back one database.** `JpaTransactionManager` manages only a single persistence unit. Use JTA/XA if atomicity is required, or Outbox/Saga if eventual consistency is acceptable.

**JPA association fails to join an Entity in another database.** Associations cannot span persistence units. Exchange IDs/business keys and assemble data in the service or read model.

**Reading from a replica returns stale data.** Check replication lag and route read-your-writes back to the primary.

**Migration runs against the wrong database.** Bind Flyway/Liquibase to the specific DataSource and use separate locations/schemas.

**Database runs out of connections even though each pool looks small.** Sum the pools across all instances and background components; reduce maximum pool sizes or limit concurrency.

## 19. Decision checklist for multiple DataSources

- Do the tables truly reside in independent databases/endpoints, or just different schemas?
- Are separate credentials, network boundaries, pools, or availability guarantees needed?
- Do the Entities require separate persistence units and Hibernate configurations?
- Are repository packages clearly separated and bound to the right EntityManagerFactory?
- Does each persistence unit have a clearly named transaction manager?
- Are atomic transactions required across databases? If so, has JTA/XA been evaluated?
- If eventual consistency is acceptable, have Outbox/Saga and idempotency been designed?
- Are any associations or joins assuming two Entities share the same persistence unit?
- Are migrations, schema validation, health checks, and pool metrics separated per database?
- Have routing, rollback, failure, and connection capacity been tested in a production-like environment?

## 20. Conclusion

Multiple DataSources are appropriate when an application genuinely needs to access multiple independent databases or requires separate connection/persistence boundaries. With JPA, each database usually has an explicitly configured DataSource, EntityManagerFactory, transaction manager, and repository group. `@Primary` only selects a default bean; it does not unify transactions.

Before implementing, define your data and transaction boundaries. If atomic commits across databases are required, evaluate JTA/XA; if asynchronous updates are acceptable, Outbox or Saga is usually a better fit. Clear configuration of repository scanning, migrations, connection pools, and per-database testing keeps multi-datasource systems easy to operate and less prone to misrouting errors.