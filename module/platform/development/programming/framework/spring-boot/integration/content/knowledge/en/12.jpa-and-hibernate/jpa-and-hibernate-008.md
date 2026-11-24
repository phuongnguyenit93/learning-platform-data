# Multiple Persistence Units Bound to Different DataSources

## 1. Why Are Multiple Persistence Units Needed?

In a **Spring Boot Integration** application, the integration layer may need to read and write across multiple sources: an operational database storing orders, an analytics database, or a legacy system managed by another team. Each source has its own entity model, connection credentials, schema migrations, transaction policies, and performance limits. When using **JPA/Hibernate** across multiple sources within one application, you can configure **multiple persistence units**, each bound to its own `DataSource` and `EntityManagerFactory`.

Example in this lesson:

- **Orders** uses the PostgreSQL database `orders_db`, containing `OrderEntity` and `OrderRepository`; this is the system of record for order status.
- **Analytics** uses the PostgreSQL database `analytics_db`, containing `OrderMetricEntity` and `OrderMetricRepository`; this holds analytics records or derived data.

The goal goes beyond "connecting to two databases." More importantly, you must guarantee **repositories bind to the right `EntityManagerFactory`**, **transactions use the right transaction manager**, **schemas are managed independently**, and **a failure in one source is not mistaken for an atomic rollback across all sources**.

## 2. Distinguishing the Four Components

| Component | Role | Scope in This Example |
| --- | --- | --- |
| `DataSource` | Supplies JDBC connections to a database, typically backed by a connection pool like HikariCP. | `ordersDataSource` and `analyticsDataSource` |
| Persistence unit | Group of managed entities sharing JPA configuration and a logical unit name. | `ordersPU` and `analyticsPU` |
| `EntityManagerFactory` | Creates `EntityManager` instances and manages mapping metadata, persistence contexts, and Hibernate settings for one unit. | `ordersEntityManagerFactory` and `analyticsEntityManagerFactory` |
| `PlatformTransactionManager` | Starts, commits, and rolls back transactions for a resource; JPA typically uses `JpaTransactionManager`. | `ordersTransactionManager` and `analyticsTransactionManager` |

In a single-source JPA application, Spring Boot auto-configures most of these beans. With **two JPA sources**, explicitly declare each bean group and map repositories so behavior never relies on default beans.

~~~mermaid
flowchart TB
    subgraph A["Orders persistence unit"]
        OR["OrderRepository"] --> OEM["ordersEntityManagerFactory"]
        OEM --> ODS["ordersDataSource"]
        OTM["ordersTransactionManager"] --> OEM
        ODS --> ODB[("orders_db")]
    end
    subgraph B["Analytics persistence unit"]
        AR["OrderMetricRepository"] --> AEM["analyticsEntityManagerFactory"]
        AEM --> ADS["analyticsDataSource"]
        ATM["analyticsTransactionManager"] --> AEM
        ADS --> ADB[("analytics_db")]
    end
~~~

**Do not confuse different topologies:**

1. **Two independent databases and two distinct entity sets:** two `DataSource`s, two `EntityManagerFactory` beans, and two transaction managers are usually the cleanest structure.
2. **Two schemas in the same database:** you can often keep a single persistence unit using `@Table(schema = "...")` if they share the connection source and transactions; two units are not automatically required.
3. **Reading from a replica, writing to primary with the same entity model:** a routing `DataSource` or dedicated read/write separation pattern fits better. Using two persistence units does not solve replica lag.
4. **Multi-tenancy with identical schemas or models across tenants:** look into Hibernate multi-tenancy or tenant-routing datasources; do not manually define one persistence unit per tenant when tenant counts are large or dynamic.

## 3. Preparing Packages, Dependencies, and Configuration

Examples use **Spring Boot 3.x, Java 17+, Spring Data JPA, and PostgreSQL**; JPA imports come from `jakarta.persistence`. The project needs two entity/repository groups and two configuration classes:

~~~text
com.example.integration
├── IntegrationApplication.java
├── orders
│   ├── entity/OrderEntity.java
│   ├── repository/OrderRepository.java
│   └── config/OrdersJpaConfiguration.java
└── analytics
    ├── entity/OrderMetricEntity.java
    ├── repository/OrderMetricRepository.java
    └── config/AnalyticsJpaConfiguration.java
~~~

Separating repository packages cleanly is essential because each `@EnableJpaRepositories` binds **one specific set of repositories** to its persistence unit. Passing entities via the builder's `packages(...)` is a separate concern and does not replace repository scan configuration.

Maven dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Example `application.yml` using two custom prefixes without embedding passwords in source control:

~~~yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders_db
      username: ${ORDERS_DB_USER}
      password: ${ORDERS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 10
        connection-timeout: 3000
    analytics:
      url: jdbc:postgresql://localhost:5432/analytics_db
      username: ${ANALYTICS_DB_USER}
      password: ${ANALYTICS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 5
        connection-timeout: 3000

spring:
  jpa:
    open-in-view: false
~~~

`DataSourceProperties` binds connection settings (`url`, `username`, `password`), while settings under `configuration` bind onto the underlying `HikariDataSource`. Because this uses the custom `app.datasource.*` prefix, ensure the Java config classes reference the exact same prefixes; standard `spring.datasource.*` will not automatically spin up both sources.

Pool sizes are **illustrative values**. Calculate total open connections by summing pools across **every DataSource on every application replica**, then compare against each database's connection limit. Size timeouts around SLAs, network latency, and query durations.

## 4. Creating Two Separate Entity and Repository Groups

Minimal definitions for the Orders domain (place each type in its corresponding `.java` file):

~~~java
// orders/entity/OrderEntity.java
package com.example.integration.orders.entity;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "orders")
public class OrderEntity {
    @Id
    private UUID id;

    @Column(nullable = false)
    private String status;

    protected OrderEntity() {} // JPA

    public OrderEntity(UUID id, String status) {
        this.id = id;
        this.status = status;
    }

    public UUID getId() { return id; }
    public String getStatus() { return status; }
    public void confirm() { this.status = "CONFIRMED"; }
}
~~~

~~~java
// orders/repository/OrderRepository.java
package com.example.integration.orders.repository;

import com.example.integration.orders.entity.OrderEntity;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<OrderEntity, UUID> {}
~~~

The Analytics domain defines its own entities and repositories:

~~~java
// analytics/entity/OrderMetricEntity.java
package com.example.integration.analytics.entity;

import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

@Entity
@Table(name = "order_metrics")
public class OrderMetricEntity {
    @Id
    private UUID id;
    private long orderCount;

    protected OrderMetricEntity() {}
    public OrderMetricEntity(UUID id, long orderCount) {
        this.id = id;
        this.orderCount = orderCount;
    }
}
~~~

~~~java
// analytics/repository/OrderMetricRepository.java
package com.example.integration.analytics.repository;

import com.example.integration.analytics.entity.OrderMetricEntity;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderMetricRepository
        extends JpaRepository<OrderMetricEntity, UUID> {}
~~~

Include `OrderEntity` only in the Orders persistence unit and `OrderMetricEntity` only in Analytics. A `@ManyToOne`/`@OneToMany` association cannot issue JPA joins across two separate persistence units. When cross-referencing is needed, store the foreign ID as a plain value and combine results in the application layer or through an integration flow.

## 5. Configuring Orders: DataSource, EntityManagerFactory, Transaction Manager

Example `OrdersJpaConfiguration`:

~~~java
package com.example.integration.orders.config;

import com.example.integration.orders.entity.OrderEntity;
import com.example.integration.orders.repository.OrderRepository;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.orm.jpa.EntityManagerFactoryBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.transaction.PlatformTransactionManager;
import javax.sql.DataSource;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
        basePackageClasses = OrderRepository.class,
        entityManagerFactoryRef = "ordersEntityManagerFactory",
        transactionManagerRef = "ordersTransactionManager")
public class OrdersJpaConfiguration {

    @Bean("ordersDataSourceProperties")
    @Primary
    @ConfigurationProperties("app.datasource.orders")
    DataSourceProperties ordersDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean("ordersDataSource")
    @Primary
    @ConfigurationProperties("app.datasource.orders.configuration")
    HikariDataSource ordersDataSource(
            @Qualifier("ordersDataSourceProperties") DataSourceProperties props) {
        return props.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean("ordersEntityManagerFactory")
    @Primary
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("ordersDataSource") DataSource ds) {
        return builder
                .dataSource(ds)
                .packages(OrderEntity.class)
                .persistenceUnit("ordersPU")
                .properties(Map.of("hibernate.hbm2ddl.auto", "validate"))
                .build();
    }

    @Bean("ordersTransactionManager")
    @Primary
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory emf) {
        return new JpaTransactionManager(emf);
    }
}
~~~

Clarifying common points of confusion:

1. `@ConfigurationProperties("app.datasource.orders")` binds connection details onto `DataSourceProperties`; `initializeDataSourceBuilder()` maps JDBC `url` appropriately when building Hikari.
2. `@ConfigurationProperties("app.datasource.orders.configuration")` applies pool settings onto `HikariDataSource`. Never mix pool configurations between Orders and Analytics.
3. `builder.dataSource(ds).packages(OrderEntity.class).persistenceUnit("ordersPU")` creates the Orders persistence unit; `packages` scans entities in the package of the supplied class.
4. `entityManagerFactoryRef` and `transactionManagerRef` bind every repository scanned in the Orders package to the declared bean names.
5. `@Primary` designates Orders as the default candidate when multiple beans share a type. It also helps auto-configuration expecting a single `DataSource` pick the primary candidate. **`@Primary` does not automatically route databases by entity or business logic.**
6. `hibernate.hbm2ddl.auto=validate` validates mappings against the existing schema on startup; this example intentionally prevents Hibernate from creating or altering tables in an integration environment.

In Spring Boot 3.x, `EntityManagerFactoryBuilder` is typically supplied by Boot's JPA configuration when a matching `DataSource` exists. Depending on version and how much auto-configuration is overridden, a project may need to define the builder and `JpaVendorAdapter`/vendor properties manually; never copy configuration across Spring Boot generations without verifying API signatures and active auto-configuration.

## 6. Configuring Analytics with a Matching Bean Set

`AnalyticsJpaConfiguration` defines an independent group:

~~~java
package com.example.integration.analytics.config;

import com.example.integration.analytics.entity.OrderMetricEntity;
import com.example.integration.analytics.repository.OrderMetricRepository;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.orm.jpa.EntityManagerFactoryBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.transaction.PlatformTransactionManager;
import javax.sql.DataSource;

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
        basePackageClasses = OrderMetricRepository.class,
        entityManagerFactoryRef = "analyticsEntityManagerFactory",
        transactionManagerRef = "analyticsTransactionManager")
public class AnalyticsJpaConfiguration {

    @Bean("analyticsDataSourceProperties")
    @ConfigurationProperties("app.datasource.analytics")
    DataSourceProperties analyticsDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean("analyticsDataSource")
    @ConfigurationProperties("app.datasource.analytics.configuration")
    HikariDataSource analyticsDataSource(
            @Qualifier("analyticsDataSourceProperties") DataSourceProperties props) {
        return props.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean("analyticsEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean analyticsEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("analyticsDataSource") DataSource ds) {
        return builder
                .dataSource(ds)
                .packages(OrderMetricEntity.class)
                .persistenceUnit("analyticsPU")
                .properties(Map.of("hibernate.hbm2ddl.auto", "validate"))
                .build();
    }

    @Bean("analyticsTransactionManager")
    PlatformTransactionManager analyticsTransactionManager(
            @Qualifier("analyticsEntityManagerFactory")
            EntityManagerFactory emf) {
        return new JpaTransactionManager(emf);
    }
}
~~~

**Critical rule:** The two `@EnableJpaRepositories` annotations must scan **non-overlapping** repository packages; otherwise you risk duplicate bean registration errors or repositories getting bound to the wrong `EntityManagerFactory`. Packages must also lie under the application's component-scan root or be explicitly `@Import`ed.

Choose clear bean names distinct from default `entityManagerFactory` and `transactionManager`. Some libraries or add-ons assume those default names; supply explicit refs/qualifiers rather than relying on implicit defaults.

## 7. Selecting the Right Transaction Manager for Each Data Source

In the service layer, declare the transaction manager for each operation:

~~~java
import com.example.integration.orders.entity.OrderEntity;
import com.example.integration.orders.repository.OrderRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final OrderRepository orders;

    public OrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional("ordersTransactionManager")
    public void confirm(UUID orderId) {
        OrderEntity order = orders.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException("Order not found"));
        order.confirm();
        // Dirty checking flushes changes on flush/commit.
    }
}
~~~

~~~java
import com.example.integration.analytics.entity.OrderMetricEntity;
import com.example.integration.analytics.repository.OrderMetricRepository;
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AnalyticsService {
    private final OrderMetricRepository metrics;

    public AnalyticsService(OrderMetricRepository metrics) {
        this.metrics = metrics;
    }

    @Transactional(transactionManager = "analyticsTransactionManager")
    public void record(UUID eventId) {
        metrics.save(new OrderMetricEntity(eventId, 1));
    }
}
~~~

Above, `@Transactional("ordersTransactionManager")` wraps the Orders operation, and `@Transactional(transactionManager = "analyticsTransactionManager")` wraps Analytics. Spring Data repositories also use the manager configured in `@EnableJpaRepositories` when starting transactions for individual repository calls, yet **use-case transactions** belong on services with the explicit manager.

Key caveats:

- `@Transactional` without specifying a manager selects the default/`@Primary` manager, easily creating the illusion that all repositories share one transaction.
- `@Transactional(readOnly = true)` is an optimization hint and read-only intent; it is not a security guard or a guarantee every database rejects writes.
- Proxy-based transactions do not apply when calling a `@Transactional` method from another method **on the same object** (self-invocation).
- A persistence context manages only entities belonging to its unit. Passing an entity loaded from Orders into Analytics' `EntityManager` does not make it managed in the second unit.
- When injecting `EntityManager` directly, use `@PersistenceContext(unitName = "ordersPU")` or `@PersistenceContext(unitName = "analyticsPU")` to specify the unit; never inject an unqualified `EntityManager` expecting Spring to route it automatically.

## 8. Two `@Transactional` Annotations Do Not Create a Global ACID Transaction

This is the single biggest pitfall in multi-persistence-unit designs:

~~~mermaid
sequenceDiagram
    participant App as Application service
    participant O as Orders DB
    participant A as Analytics DB
    App->>O: Begin Orders transaction
    App->>A: Write metric in Analytics transaction
    A-->>App: Analytics commits cleanly
    App->>O: Commit Orders
    O-->>App: Commit fails
    Note over O,A: Analytics recorded metric yet Orders did not confirm
~~~

`JpaTransactionManager` manages **one** `EntityManagerFactory`/`DataSource`. When a service sequentially invokes two services using two different transaction managers, each commits independently. Even if an outer method carries `@Transactional("ordersTransactionManager")` and calls an Analytics repository, the Analytics call typically runs under its own transaction manager. Rolling back Orders **does not** automatically roll back Analytics.

### 8.1. Choosing Coordination Based on Business Constraints

| Requirement | Typical Sound Approach | Trade-Offs |
| --- | --- | --- |
| All changes must be atomic and share an owner | Keep data guarding the invariant inside **one local transaction boundary** when architecture allows. | May require adjusting service ownership or schemas. |
| Orders is source of truth; Analytics can lag | Commit Orders with a **transactional outbox**, emit event; Analytics consumer processes idempotently. | Eventual consistency, outbox relay, retries, lag, and reconciliation. |
| Multiple business steps across independent systems | Saga/orchestration, intermediate states, timeouts, and compensating actions. | Compensation is not instant rollback. |
| Mandatory atomicity across XA-capable resources | Evaluate JTA/XA with a properly configured transaction coordinator, checking DB/driver support. | Locking/coordination overhead, operational complexity, tricky recovery. |

For Orders and Analytics, a standard pattern writes `OrderConfirmed` into **Orders' outbox within the same transaction setting status to `CONFIRMED`**. After commit, a relay publishes the event via a broker like RabbitMQ/Kafka; Analytics handles the event and writes metrics in its own local Analytics transaction. Consumers receiving redeliveries must avoid double-counting metrics via a unique `eventId` key, such as an inbox table with a unique constraint or an equivalent idempotent upsert.

~~~mermaid
flowchart LR
    O["OrderService"] -->|"Single transaction"| DB[("Orders + Outbox")]
    DB --> R["Outbox relay"]
    R --> B[("Broker")]
    B --> C["Analytics consumer"]
    C -->|"Single transaction"| A[("Analytics + Inbox")]
~~~

**Outbox does not make the broker deliver only once:** if the relay crashes after broker accept and before marking the row published, the same event can be sent again. Build idempotency on the Analytics side. If data moves between the two sources without a broker, you still need checkpoints, reconciliation, and retries for partial-failure recovery.

## 9. Coordinating Schema Migrations and Hibernate Configuration

Each persistence unit normally has its own schema lifecycle. When using Flyway or Liquibase, explicitly configure **which DataSource each migration targets**, script locations, history tables, and startup ordering. Never assume Spring Boot's default migration auto-configuration handles both sources automatically.

Example directory layout:

~~~text
src/main/resources/db/migration/
├── orders/
│   ├── V1__create_orders.sql
│   └── V2__create_outbox.sql
└── analytics/
    ├── V1__create_order_metrics.sql
    └── V2__create_consumer_inbox.sql
~~~

Configure separate migration runners per `DataSource` (or run migrations outside the app), pointing to the right locations and ensuring migrations finish before `EntityManagerFactory` beans validate schemas. Depending on Flyway/Liquibase, wire startup dependencies explicitly. In Sections 5–6, `hibernate.hbm2ddl.auto=validate` only **validates** schemas; it neither creates nor updates tables.

Users often expect `spring.jpa.*` properties to apply to every persistence unit, yet when constructing `EntityManagerFactory` beans manually, verify which properties are actually passed to each unit's builder. Settings such as naming strategies, dialects, SQL formatting, batch sizes, timezones, second-level cache, or multi-tenancy may have to be configured explicitly per unit. Differences across databases or Hibernate versions make per-unit configuration even more important than copy-pasting.

If the two sources run on different RDBMS engines, give each `EntityManagerFactory` the proper Hibernate dialect, driver, and type mappings. Letting Hibernate infer the dialect from JDBC metadata works when connections are available at startup; in restricted-metadata environments or specialized setups, configure dialects explicitly per version.

## 10. Common Errors and Diagnostic Signals

| Symptom | Common Cause | Check and Fix |
| --- | --- | --- |
| `Not a managed type: ...OrderEntity` | Entity is outside packages scanned by `ordersEntityManagerFactory` or imported into the wrong unit. | Check `packages(OrderEntity.class)`, entity package, and `@Entity`. |
| Repository hits the wrong table/database | Overlapping `@EnableJpaRepositories` scopes, wrong bean refs, or unexpected default package scan. | Set distinct `basePackageClasses`; verify `entityManagerFactoryRef` and `transactionManagerRef`. |
| `NoUniqueBeanDefinitionException` | Multiple `DataSource`, `EntityManagerFactory`, or `PlatformTransactionManager` beans with ambiguous injection. | Add `@Qualifier`/bean names, and `@Primary` for the default if needed. |
| `No bean named 'entityManagerFactory'` | A library or config expects the default bean name while custom names were used. | Point dependent configs to the right bean name, or add an alias when appropriate. |
| `No EntityManager with actual transaction available` | Write/flush ran outside an active JPA transaction. | Place `@Transactional` on the service, pick the right manager, check proxies and callers. |
| `Connection is closed`, pool timeouts | Pool too small, leaks, slow queries, or DB connection limits exceeded. | Monitor active/idle/pending connections, timeouts, query latencies, and total pool budget across replicas. |
| Orders rolled back while Analytics committed | Two local transaction managers do not coordinate atomicity. | Use outbox/saga/reconciliation; only use XA if mandatory and supported. |
| Migrations ran on the wrong database | Auto-config picked only the default `DataSource` or locations were misconfigured. | Bind migrations explicitly per DS and verify real history tables/schemas. |
| `LazyInitializationException` | Accessing a lazy association after the `EntityManager`/session closed. | Fetch needed data inside the right transaction; use DTOs/projections/fetch plans. |
| Analytics reads lag behind Orders | Analytics is an asynchronous projection or reads from a lagging replica. | Define freshness SLAs, show status clearly, and query the owner when fresh state is mandatory. |

Another dangerous trap is naming a table `orders` in both databases and treating a successful query as proof the right source was chosen. Tests should inspect **the physical database/schema**, sentinel rows, and actual state in each datasource rather than merely checking that a repository returns a list.

## 11. Testing Two Persistence Units Meaningfully

With multiple data sources, a standard `@DataJpaTest` slice does not automatically bring in custom multi-datasource configurations and both databases. For integration tests, use `@SpringBootTest` with Testcontainers or two isolated databases, mapping each datasource's URL to the corresponding properties.

A high-value test matrix:

1. **Boot and wiring:** the application creates two `DataSource`s, two `EntityManagerFactory` beans, and two `JpaTransactionManager`s; each repository hits its intended database.
2. **Transaction isolation:** writing to Orders does not create rows in Analytics; rolling back Analytics does not undo committed Orders rows.
3. **Entity isolation:** Orders repositories manage only `OrderEntity` and Analytics repositories manage only `OrderMetricEntity`; attempting to persist an entity in the wrong PU fails appropriately.
4. **Migrations:** both databases contain all expected versioned tables without cross-running migrations.
5. **Single-DB outage:** when Analytics is unavailable, Orders processing behaves per business requirements and queues/retries Analytics updates if permitted.
6. **Event deduplication:** delivering the same `OrderConfirmed` event twice to the Analytics consumer does not double-increment metrics.
7. **Pools and observability:** verify connection limits per source; dashboards distinguish Orders from Analytics.
8. **Eventual consistency:** when relays or consumers lag, the system exposes pending state, lag metrics rise, and state converges upon recovery.

If using transactional tests to roll back test fixtures, specify the manager explicitly. `@Transactional("ordersTransactionManager")` on a test **will not** roll back commits made with `analyticsTransactionManager`. To clean both databases, use explicit cleanup, independent transactions, or fresh test environments.

### 11.1. Per-Source Observability

Assign distinct pool names via Hikari `pool-name`, such as `orders-pool` and `analytics-pool`, to track connection usage and timeouts per source. Monitor:

- `active`, `idle`, and `pending` connections; connection acquisition times and timeouts per pool.
- Query latency, slow queries, deadlocks, and transaction durations per database.
- Retry counts, event/outbox lag, consumer lag, DLQs, and reconciliation mismatches.
- Migration failures, schema mismatches, and Hibernate/driver version changes.

Never log passwords, JDBC URLs containing credentials, or sensitive PII. Apply least-privilege DB accounts; the Analytics account should not have write access to Orders tables.

## 12. Design Checklist

Before putting a multi-persistence-unit configuration into operation, verify:

- [ ] Each `DataSource` has dedicated property prefixes, pool sizing, credentials, permissions, and health/metrics.
- [ ] Each entity set belongs exclusively to its intended persistence unit; repository packages do not overlap.
- [ ] Each `@EnableJpaRepositories` specifies the exact `entityManagerFactoryRef` and `transactionManagerRef`.
- [ ] Mutating services declare the right transaction manager explicitly and never assume cross-database rollback.
- [ ] Each schema has independent migrations and deploy/rollback workflows; Hibernate never alters schemas unexpectedly.
- [ ] Cross-database data flows have clear consistency, retry, idempotency, reconciliation, and monitoring policies.
- [ ] Integration tests use **two real databases or equivalent isolated environments**, verifying physical targets and single-side failures.

In **Spring Boot Integration**, multiple persistence units cleanly separate technical boundaries: JPA/Hibernate manages entities and local transactions per source, while HTTP, message broker, cache, or Spring Integration flows coordinate data exchange across those boundaries. Designing around **data ownership, message contracts, and consistency guarantees** upfront keeps multi-DataSource configurations predictable and prevents false assumptions about global transactions.
