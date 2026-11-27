# Declaring Multiple ConnectionFactory Beans and Naming Beans Clearly

## 1. Why Does an Application Need Multiple ConnectionFactory Beans?

A Spring Data Relational R2DBC application usually starts with a single database and a single ConnectionFactory. When the application accesses only one data source, Spring Boot can auto-configure the R2DBC components based on one set of connection properties.

In larger systems, an application may need to access multiple databases or multiple database clusters. For example:

- An orders database storing orders and order line items.
- A customers database storing customer profiles.
- An audit database storing business event logs.
- A reporting database serving reporting queries.
- One PostgreSQL database and another database using a different driver.
- Two databases of the same type belonging to different environments or bounded contexts.

With R2DBC, each data source needs a corresponding ConnectionFactory. The ConnectionFactory is responsible for creating connections to a database according to its driver and configuration.

When there are multiple ConnectionFactory beans, the application must clearly specify:

1. Which repository uses which database.
2. Which R2dbcEntityTemplate is bound to which ConnectionFactory.
3. Which DatabaseClient sends SQL to which data source.
4. Which transaction manager manages operations on each database.
5. How beans injected into services must be explicitly selected.

If you simply declare multiple beans of type ConnectionFactory without clear naming and qualifiers, Spring may not know which bean to inject. Even worse, the code might run without startup errors but operate on the wrong database if a default bean is chosen unintentionally.

This lesson focuses on how to declare multiple ConnectionFactory beans, name beans consistently, and wire each data source to its corresponding repository, template, DatabaseClient, and transaction manager.

## 2. Required Components for Each Data Source

An R2DBC data source typically has the following components:

| Component | Role |
|---|---|
| ConnectionFactory | Creates and manages connection acquisition for a database |
| DatabaseClient | Executes reactive SQL on the ConnectionFactory bound to it |
| R2dbcEntityTemplate | Performs entity operations based on mapping metadata and ConnectionFactory |
| Repository configuration | Specifies which R2dbcEntityTemplate a repository package uses |
| R2dbcTransactionManager | Manages reactive transactions on the corresponding ConnectionFactory |
| TransactionalOperator | Wraps a publisher in the selected transaction |

An application with two databases can be organized as follows:

~~~text
Orders database
  ordersConnectionFactory
       |
       +-- ordersDatabaseClient
       |
       +-- ordersEntityTemplate
       |       |
       |       +-- com.example.orders.repository
       |
       +-- ordersTransactionManager
       |
       +-- ordersTransactionalOperator


Audit database
  auditConnectionFactory
       |
       +-- auditDatabaseClient
       |
       +-- auditEntityTemplate
       |       |
       |       +-- com.example.audit.repository
       |
       +-- auditTransactionManager
       |
       +-- auditTransactionalOperator
~~~

Each group has its own name to reflect the data source it represents. When injecting beans in code, use the corresponding qualifier instead of relying on declaration order or parameter names.

## 3. How Do Bean Names and Qualifiers Differ?

### 3.1. Bean Name

In Spring, the default name of a bean created by a @Bean method is the method name itself.

For example:

~~~java
@Bean
ConnectionFactory ordersConnectionFactory() {
    // ...
}
~~~

The bean above is named ordersConnectionFactory.

You can specify the name explicitly:

~~~java
@Bean("ordersConnectionFactory")
ConnectionFactory ordersConnectionFactory() {
    // ...
}
~~~

When an application has multiple beans of the same type, bean names help identify each instance.

You should follow a consistent naming convention per data source, for example:

- ordersConnectionFactory
- ordersDatabaseClient
- ordersEntityTemplate
- ordersTransactionManager
- auditConnectionFactory
- auditDatabaseClient
- auditEntityTemplate
- auditTransactionManager

Consistent naming lets anyone reading the configuration or constructor immediately see which database a bean connects to.

### 3.2. @Qualifier

@Qualifier specifies a particular bean when multiple candidates of the same type exist.

For example:

~~~java
@Service
public class AuditWriter {

    private final DatabaseClient databaseClient;

    public AuditWriter(
            @Qualifier("auditDatabaseClient")
            DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }
}
~~~

If there are two DatabaseClient beans, Spring cannot automatically choose based on type alone. The qualifier explicitly states that auditDatabaseClient must be injected.

Similarly with ConnectionFactory:

~~~java
public OrdersService(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {
    this.connectionFactory = connectionFactory;
}
~~~

Use qualifiers at injection points where multiple beans of the same type exist. Do not rely on Java variable names such as ordersConnectionFactory as a substitute for @Qualifier in every case.

### 3.3. @Primary

@Primary marks a bean as the default candidate when Spring has to choose among multiple beans of the same type and the injection point does not specify a qualifier.

For example:

~~~java
@Bean("ordersConnectionFactory")
@Primary
ConnectionFactory ordersConnectionFactory() {
    // ...
}
~~~

@Primary is useful when an application has one primary database used by most legacy components, while other sources are used only in specific modules.

However, @Primary does not replace clear naming and qualifiers:

- It only determines the default candidate for certain injection points.
- It does not automatically route repositories to the desired database.
- It does not automatically select the transaction manager for every business operation.
- A service that needs the audit database still must use the corresponding audit qualifier.

In a multi-database system, prefer explicit injection. Only use @Primary when there truly is a sensible default data source for the application.

## 4. Configuring Properties for Multiple Databases

You should not hard-code URLs, usernames, and passwords directly in configuration code. Place them in externalized configuration and retrieve secrets from environment variables or a secret manager.

Example application.yml:

~~~yaml
app:
  r2dbc:
    orders:
      url: r2dbc:postgresql://orders-host:5432/orders
    audit:
      url: r2dbc:postgresql://audit-host:5432/audit
~~~

The URLs above only illustrate the connection shape. In real environments, supply values from deployment configuration or secret management; do not commit credentials to source control.

Environment variables can hold driver-compatible R2DBC URLs. Exact syntax and connection options depend on the R2DBC driver.

You can inject each URL using @Value:

~~~java
@Value("${app.r2dbc.orders.url}")
private String ordersUrl;
~~~

In larger projects, use @ConfigurationProperties to group each database's properties into a structured configuration type. This makes validation, testing, and adding pool settings easier than scattering many @Value annotations.

### 4.1. A Single Set of spring.r2dbc Properties Does Not Create Multiple Data Sources

Spring Boot's standard spring.r2dbc.* properties typically describe the configuration of a single auto-configured ConnectionFactory.

If the application needs multiple data sources, declare separate property groups such as app.r2dbc.orders and app.r2dbc.audit, then create each ConnectionFactory bean accordingly.

Do not assume that simply adding app.r2dbc.audit.url will make Spring Boot automatically create a second ConnectionFactory. Custom property names have no automatic meaning to Boot unless you write configuration to read them.

### 4.2. Creating ConnectionFactory Manually from a URL

The R2DBC SPI provides ConnectionFactories to create a ConnectionFactory from a URL:

~~~java
import io.r2dbc.spi.ConnectionFactories;
import io.r2dbc.spi.ConnectionFactory;

@Bean("ordersConnectionFactory")
ConnectionFactory ordersConnectionFactory(
        @Value("${app.r2dbc.orders.url}") String url) {

    return ConnectionFactories.get(url);
}
~~~

Second bean:

~~~java
@Bean("auditConnectionFactory")
ConnectionFactory auditConnectionFactory(
        @Value("${app.r2dbc.audit.url}") String url) {

    return ConnectionFactories.get(url);
}
~~~

The two beans are created independently. Each URL must specify the appropriate driver, host, port, database, and authentication options.

If a URL contains sensitive information, ensure the value comes from secret/configuration management and is not written to logs or committed to source control.

### 4.3. Creating ConnectionFactory from ConnectionFactoryOptions

When you need to configure individual options separately, you can use ConnectionFactoryOptions:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactoryOptions;
import io.r2dbc.spi.ConnectionFactories;

import static io.r2dbc.spi.ConnectionFactoryOptions.DATABASE;
import static io.r2dbc.spi.ConnectionFactoryOptions.DRIVER;
import static io.r2dbc.spi.ConnectionFactoryOptions.HOST;
import static io.r2dbc.spi.ConnectionFactoryOptions.PASSWORD;
import static io.r2dbc.spi.ConnectionFactoryOptions.PORT;
import static io.r2dbc.spi.ConnectionFactoryOptions.USER;

@Bean("ordersConnectionFactory")
ConnectionFactory ordersConnectionFactory(
        @Value("${app.r2dbc.orders.host}") String host,
        @Value("${app.r2dbc.orders.port}") int port,
        @Value("${app.r2dbc.orders.database}") String database,
        @Value("${app.r2dbc.orders.username}") String username,
        @Value("${app.r2dbc.orders.password}") String password) {

    ConnectionFactoryOptions options =
        ConnectionFactoryOptions.builder()
            .option(DRIVER, "postgresql")
            .option(HOST, host)
            .option(PORT, port)
            .option(DATABASE, database)
            .option(USER, username)
            .option(PASSWORD, password)
            .build();

    return ConnectionFactories.get(options);
}
~~~

This approach works well when you want to validate or transform individual properties before creating the factory. Driver names and supported options depend on the driver.

Do not mix options from two databases in the same builder. Each ConnectionFactory must be created from its own set of options.

## 5. Declaring Two ConnectionFactory Beans with Clear Bean Names

Complete configuration example for two databases both using PostgreSQL:

~~~java
@Configuration
public class R2dbcConnectionFactoryConfiguration {

    @Bean("ordersConnectionFactory")
    @Primary
    ConnectionFactory ordersConnectionFactory(
            @Value("${app.r2dbc.orders.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean("auditConnectionFactory")
    ConnectionFactory auditConnectionFactory(
            @Value("${app.r2dbc.audit.url}") String url) {
        return ConnectionFactories.get(url);
    }
}
~~~

In this example:

- ordersConnectionFactory is the primary data source by application convention.
- auditConnectionFactory is the secondary data source.
- @Primary causes ordersConnectionFactory to be selected at injection points without a qualifier when a default ConnectionFactory is needed.
- Downstream configurations still must use qualifiers to bind the right data source.

If the application has no default database, you can omit @Primary and require qualifiers at every injection point with multiple candidates.

### 5.1. Do Not Inject ConnectionFactory Ambiguously

Do not write:

~~~java
public DatabaseHealthService(ConnectionFactory connectionFactory) {
    this.connectionFactory = connectionFactory;
}
~~~

If there are multiple ConnectionFactory beans and no single default candidate, Spring may throw NoUniqueBeanDefinitionException.

Instead, write:

~~~java
public DatabaseHealthService(
        @Qualifier("auditConnectionFactory")
        ConnectionFactory connectionFactory) {
    this.connectionFactory = connectionFactory;
}
~~~

When reading code, the qualifier also clearly identifies which database an operation targets.

## 6. Creating a Dedicated DatabaseClient for Each ConnectionFactory

A DatabaseClient is bound to one ConnectionFactory. If you create two ConnectionFactory beans, you should create two correspondingly named DatabaseClient beans.

~~~java
@Configuration
public class R2dbcClientConfiguration {

    @Bean("ordersDatabaseClient")
    DatabaseClient ordersDatabaseClient(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {

        return DatabaseClient.create(connectionFactory);
    }

    @Bean("auditDatabaseClient")
    DatabaseClient auditDatabaseClient(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {

        return DatabaseClient.create(connectionFactory);
    }
}
~~~

When used in a service:

~~~java
@Repository
public class AuditSqlRepository {

    private final DatabaseClient databaseClient;

    public AuditSqlRepository(
            @Qualifier("auditDatabaseClient")
            DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Mono<Integer> record(Long orderId, String action) {
        return databaseClient.sql("""
                INSERT INTO audit_events(order_id, action)
                VALUES (:orderId, :action)
                """)
            .bind("orderId", orderId)
            .bind("action", action)
            .fetch()
            .rowsUpdated();
    }
}
~~~

This INSERT statement executes through auditDatabaseClient, so the connection is obtained from auditConnectionFactory.

If ordersDatabaseClient is injected by mistake, the SQL statement will be sent to the orders database. Clear bean names and qualifiers help prevent routing bugs like this.

### 6.1. DatabaseClient Does Not Automatically Know the Business Database

DatabaseClient only knows the ConnectionFactory it was created with. It does not inspect service package names or table names to select a database automatically.

A DatabaseClient cannot automatically switch to auditConnectionFactory just because the SQL accesses the audit_events table. Routing must be configured in beans or explicitly chosen in code.

### 6.2. Using DatabaseClient in a Multi-Database Configuration

For direct SQL, inject the right DatabaseClient using a qualifier. Avoid creating new DatabaseClient instances scattered throughout services using a ConnectionFactory obtained from a default bean, because that breaks consistency in dialect configuration, mapping, logging, and observability.

If the application has different bind marker rules or SQL configurations across drivers, create the corresponding DatabaseClient for each data source and keep configuration in one place.

## 7. Creating a Dedicated R2dbcEntityTemplate for Each Database

R2dbcEntityTemplate is the entity mapping abstraction. Each template must be bound to the ConnectionFactory of the database it manages.

For example:

~~~java
@Configuration
public class R2dbcTemplateConfiguration {

    @Bean("ordersEntityTemplate")
    R2dbcEntityTemplate ordersEntityTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean("auditEntityTemplate")
    R2dbcEntityTemplate auditEntityTemplate(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

Each template has a mapping context and dialect configured according to its corresponding setup. If a database uses custom converters, a naming strategy, or its own mapping context, configure them for the corresponding template instead of assuming all templates share a single set of converters.

### 7.1. Injecting the Right Template in Services

~~~java
@Service
public class AuditQueryService {

    private final R2dbcEntityTemplate auditTemplate;

    public AuditQueryService(
            @Qualifier("auditEntityTemplate")
            R2dbcEntityTemplate auditTemplate) {
        this.auditTemplate = auditTemplate;
    }
}
~~~

When using a template, entity operations go through the mapping metadata of the injected template. If the wrong template is used, SQL may be sent to another database even though the entity class is the same.

### 7.2. Template and DatabaseClient Have Different Roles

| Component | Focuses On |
|---|---|
| R2dbcEntityTemplate | Entity mapping, Criteria, Query, metadata-driven Insert/Update |
| DatabaseClient | Direct SQL, parameter binding, and result mapping |
| ConnectionFactory | Creating connections for a data source |

An application can use both a template and a DatabaseClient for the same database. When using multiple databases, name both groups of beans according to the same convention to avoid confusion.

## 8. Routing Repositories with entityOperationsRef

Declaring a repository interface that extends ReactiveCrudRepository is not enough for Spring to know which template it must use when the application has multiple data sources.

Spring Data R2DBC provides @EnableR2dbcRepositories with the entityOperationsRef attribute. This attribute specifies the R2dbcEntityOperations bean that repositories scanned in the corresponding package will use.

Example orders repository configuration:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.orders.repository",
    entityOperationsRef = "ordersEntityTemplate"
)
public class OrdersRepositoryConfiguration {
}
~~~

Audit repository configuration:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.audit.repository",
    entityOperationsRef = "auditEntityTemplate"
)
public class AuditRepositoryConfiguration {
}
~~~

Thus:

- Repositories in com.example.orders.repository use ordersEntityTemplate.
- Repositories in com.example.audit.repository use auditEntityTemplate.

The name in entityOperationsRef must match a declared bean name. If there is a typo or the bean does not exist, the repository infrastructure cannot initialize properly.

### 8.1. Separating Repository Packages

Organize packages cleanly:

~~~text
com.example
  orders
    domain
    repository
    service
  audit
    domain
    repository
    service
  config
    OrdersRepositoryConfiguration
    AuditRepositoryConfiguration
    R2dbcConnectionFactoryConfiguration
    R2dbcTemplateConfiguration
~~~

The two repository packages should not overlap. If the same repository interface is scanned by two @EnableR2dbcRepositories configurations, bean registration may conflict or the repository may be bound to an unexpected template.

Each repository interface should belong to a single package routed to one specific entityOperationsRef.

### 8.2. Do Not Use entityOperationsRef to Choose a Transaction Manager

entityOperationsRef selects R2dbcEntityOperations for repositories. It is not the attribute for choosing a transaction manager.

The transaction manager is chosen at the transaction boundary, for example via @Transactional(transactionManager = "...") or a TransactionalOperator created from the corresponding manager.

These two concerns are related but independent:

- Repository routing determines the database/template used for entity access.
- Transaction routing determines the transaction manager managing the publisher.

Configure both explicitly.

## 9. Declaring a Dedicated R2dbcTransactionManager for Each Database

Each ConnectionFactory needs a reactive transaction manager if the application wants to manage transactions independently on that database.

For example:

~~~java
@Configuration
public class R2dbcTransactionConfiguration {

    @Bean("ordersTransactionManager")
    ReactiveTransactionManager ordersTransactionManager(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("auditTransactionManager")
    ReactiveTransactionManager auditTransactionManager(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

R2dbcTransactionManager manages reactive transactions on the ConnectionFactory passed to its constructor.

Bean names must be clear so services select the right transaction manager.

### 9.1. Selecting the Transaction Manager with @Transactional

Example of a business operation that only updates the orders database:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Mono<Order> confirm(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                order.setStatus("CONFIRMED");
                return orderRepository.save(order);
            });
    }
}
~~~

transactionManager specifies the manager bean that Spring uses for the reactive method's transaction.

If you omit the manager name in an application with multiple transaction managers, Spring may fail to find a single unique manager or pick a default manager based on configuration. With multiple databases, explicitly specify the manager at the business boundary.

### 9.2. Selecting TransactionalOperator with a Qualifier

You can create separate TransactionalOperator beans:

~~~java
@Configuration
public class TransactionalOperatorConfiguration {

    @Bean("ordersTransactionalOperator")
    TransactionalOperator ordersTransactionalOperator(
            @Qualifier("ordersTransactionManager")
            ReactiveTransactionManager transactionManager) {

        return TransactionalOperator.create(transactionManager);
    }

    @Bean("auditTransactionalOperator")
    TransactionalOperator auditTransactionalOperator(
            @Qualifier("auditTransactionManager")
            ReactiveTransactionManager transactionManager) {

        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Inject the appropriate operator:

~~~java
public AuditService(
        @Qualifier("auditTransactionalOperator")
        TransactionalOperator transactionalOperator) {
    this.transactionalOperator = transactionalOperator;
}
~~~

Then:

~~~java
public Mono<Void> recordAudit(Long orderId) {
    return transactionalOperator.transactional(
        auditRepository.save(new AuditEvent(orderId, "ORDER_CONFIRMED"))
            .then()
    );
}
~~~

TransactionalOperator makes it explicit which publisher a transaction wraps. Ensure that the repositories inside the publisher use the corresponding ConnectionFactory.

## 10. Complete Per-Database Configuration

An easy-to-follow way to organize configuration is to split it into separate classes for each data source.

### 10.1. Orders Database

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.orders.repository",
    entityOperationsRef = "ordersEntityTemplate"
)
public class OrdersR2dbcConfiguration {

    @Bean("ordersConnectionFactory")
    @Primary
    ConnectionFactory ordersConnectionFactory(
            @Value("${app.r2dbc.orders.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean("ordersDatabaseClient")
    DatabaseClient ordersDatabaseClient(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }

    @Bean("ordersEntityTemplate")
    R2dbcEntityTemplate ordersEntityTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean("ordersTransactionManager")
    ReactiveTransactionManager ordersTransactionManager(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("ordersTransactionalOperator")
    TransactionalOperator ordersTransactionalOperator(
            @Qualifier("ordersTransactionManager")
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

### 10.2. Audit Database

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.audit.repository",
    entityOperationsRef = "auditEntityTemplate"
)
public class AuditR2dbcConfiguration {

    @Bean("auditConnectionFactory")
    ConnectionFactory auditConnectionFactory(
            @Value("${app.r2dbc.audit.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean("auditDatabaseClient")
    DatabaseClient auditDatabaseClient(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }

    @Bean("auditEntityTemplate")
    R2dbcEntityTemplate auditEntityTemplate(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean("auditTransactionManager")
    ReactiveTransactionManager auditTransactionManager(
            @Qualifier("auditConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("auditTransactionalOperator")
    TransactionalOperator auditTransactionalOperator(
            @Qualifier("auditTransactionManager")
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

The example above assumes both sources use drivers compatible with the configured URLs and use default mapping. If the two databases have different drivers, dialects, converters, or pool configurations, adjust each bean accordingly.

If both configuration classes are placed in a package covered by component scanning, Spring will detect both. If the application configures scanning manually, make sure these configuration classes are imported or within the scan scope.

## 11. Spring Boot Configuration When Multiple ConnectionFactory Beans Exist

Spring Boot can auto-configure several R2DBC components when an application has a single suitable ConnectionFactory and no custom beans alter the auto-configuration conditions.

When an application manually declares multiple ConnectionFactory beans, do not rely on single-data-source auto-configuration to infer all templates and repositories. Explicitly declare the required beans for each source:

- ConnectionFactory.
- DatabaseClient if direct SQL is needed.
- R2dbcEntityTemplate for repository/entity operations.
- Separate repository scanning.
- Reactive transaction manager.
- TransactionalOperator if using programmatic transactions.

Auto-configuration conditions and default beans can vary by Spring Boot version. Check the bean conditions for your application's version, especially when adding custom ConnectionFactory beans.

### 11.1. Do Not Create Two Default Beans with the Same Name

If auto-configuration already creates default beans such as connectionFactory or r2dbcEntityTemplate, do not declare another bean with the same name intending to override it implicitly.

Choose one consistent strategy:

- Use auto-configuration for the primary data source and declare secondary sources with distinct names, if your Boot version and auto-configuration conditions allow it.
- Or manually configure all data sources with distinct names and explicit repository routing.

Do not depend on whether bean overriding is enabled. Bean overriding may be disabled, and implicit overrides make configuration hard to understand.

### 11.2. Check Auto-Configured DatabaseClient

When there are multiple ConnectionFactory beans, injecting a default DatabaseClient may become ambiguous or no longer match auto-configuration conditions.

Create a separate DatabaseClient for each ConnectionFactory and inject it with a qualifier. This makes it clear which database direct SQL will use.

### 11.3. Configuring Schema Initialization and Migration

Having multiple databases means multiple schemas must be created or updated. A migration tool may need a separate connection configuration for each database.

Do not assume migrations run for the primary database will also run for secondary databases. Declare migration locations, datasources/connections, and deployment order explicitly according to your project's tool.

The application should only start repositories after the corresponding schema is ready. If a secondary database is unavailable, explicitly decide whether the application can run in degraded mode or must fail fast.

## 12. Connection Pool for Each ConnectionFactory

In production environments, applications typically use a connection pool instead of creating a new physical connection for each operation.

R2DBC Pool provides ConnectionPool wrapping a ConnectionFactory:

~~~java
ConnectionPoolConfiguration poolConfiguration =
    ConnectionPoolConfiguration.builder(connectionFactory)
        .initialSize(2)
        .maxSize(10)
        .build();

ConnectionPool pool = new ConnectionPool(poolConfiguration);
~~~

The example only illustrates the structure for creating a pool. You need the R2DBC Pool dependency and must configure timeout, validation, idle time, and max life appropriate for the library version.

With multiple databases, each pool has its own limits:

- The orders pool has its own max size.
- The audit pool has its own max size.
- The total connections that can be opened across all databases is the sum of the pool limits.
- Increasing the pool size on one database does not resolve connection exhaustion on another database.

If you declare pools as beans, manage pool shutdown lifecycle on application stop according to your R2DBC Pool version's API. Do not create a new pool per request or per service call.

### 12.1. Calculating Total Connections

Suppose:

| Database | Max pool size |
|---|---:|
| Orders | 20 |
| Audit | 8 |
| Reporting | 12 |
| Total | 40 |

A single application instance can open up to about 40 connections across the three pools when all reach capacity. If running 4 instances, the potential total connections to the databases can be much higher.

Calculate limits based on the number of instances, each database's connection limit, other applications, and real workload.

### 12.2. Do Not Share One Pool Across Two Different Databases

ConnectionPool wraps a specific ConnectionFactory. If two databases have different URLs or credentials, you need two separate factories and two separate pools.

Do not take one pool and switch databases per request. Database/session state on a connection can leak between requests and cause wrong data or security issues.

## 13. Choosing the Right Repository and Database in Services

After routing repositories, services can inject repositories from the corresponding packages/modules.

Orders repository:

~~~java
package com.example.orders.repository;

public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

Audit repository:

~~~java
package com.example.audit.repository;

public interface AuditRepository
        extends ReactiveCrudRepository<AuditEvent, Long> {
}
~~~

Orders business service:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Mono<Order> confirm(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                order.setStatus("CONFIRMED");
                return orderRepository.save(order);
            });
    }
}
~~~

Audit service:

~~~java
@Service
public class AuditService {

    private final AuditRepository auditRepository;

    public AuditService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(transactionManager = "auditTransactionManager")
    public Mono<AuditEvent> record(Long orderId, String action) {
        return auditRepository.save(
            new AuditEvent(orderId, action)
        );
    }
}
~~~

Each service selects the transaction manager corresponding to the database used by its repository.

## 14. Can a Service Using Multiple Databases Create a Single Shared Transaction?

This is an especially important point.

Suppose a use case needs to:

1. Update an order in the orders database.
2. Record an audit event in the audit database.

The two databases have two separate ConnectionFactory beans and two separate R2dbcTransactionManager beans. A single @Transactional only selects one transaction manager at a time. It does not automatically create a distributed transaction spanning both data sources.

The following example does not guarantee atomicity across both databases:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> confirmAndAudit(Long orderId) {
    return orderRepository.findById(orderId)
        .flatMap(order -> {
            order.setStatus("CONFIRMED");

            return orderRepository.save(order)
                .flatMap(saved ->
                    auditRepository.save(
                        new AuditEvent(saved.getId(), "CONFIRMED")
                    ).thenReturn(saved)
                );
        });
}
~~~

The selected transaction manager is ordersTransactionManager. AuditRepository is routed to the audit database, but that does not automatically make the audit operation join the orders transaction. The audit operation may run outside the selected transaction or under a different transaction mechanism depending on configuration.

You can create two separate transactions in one pipeline, but they remain two independent transactions. If the orders transaction commits and then the audit transaction fails, orders data will not automatically roll back because of audit.

### 14.1. Do Not Confuse Multiple Transaction Managers with a Distributed Transaction

Declaring multiple R2dbcTransactionManager beans only enables independent transaction management on each ConnectionFactory.

It does not automatically provide:

- An atomic commit across multiple databases.
- Rolling back all databases if one database fails.
- Coordinating two connections under a distributed commit protocol.
- Automatically undoing a side effect already committed in another database.

Do not put two managers in the same annotation and expect Spring to coordinate them into a single global transaction.

### 14.2. Transactional Outbox

If updating an order and recording the need to emit an audit/message must be atomic, you can save an outbox record within the same orders transaction:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            order.setStatus("CONFIRMED");

            return orderRepository.save(order)
                .flatMap(saved ->
                    outboxRepository.save(
                        OutboxEvent.orderConfirmed(saved.getId())
                    ).thenReturn(saved)
                );
        });
}
~~~

After the orders transaction commits, a worker reads the outbox and writes to the audit database or sends a message. The worker must handle retries, idempotency, and delivery status.

Outbox ensures that the order change and the follow-up processing request are written in the same database transaction. It does not create a distributed transaction; it provides a durable mechanism to continue processing after commit.

### 14.3. Saga and Compensating Actions

For multi-step business workflows across multiple databases, you can use a saga:

1. Record the initial state in the orders database.
2. Send a command or event for audit/reporting processing.
3. Receive confirmation from the next step.
4. Advance to the final state.
5. If a later step fails, run the appropriate compensating action.

Compensating actions are business logic, not ACID rollbacks. You need to design states, retries, idempotency, and handling for late-arriving events.

## 15. When You Need to Query Data from Two Databases

A normal SQL JOIN only runs within the database that the connection is connected to. A DatabaseClient bound to ordersConnectionFactory cannot automatically JOIN tables in an audit database on another server.

If you need to combine data from two databases, there are several options:

- Read each source using its own DatabaseClient/repository and combine them in the reactive pipeline.
- Synchronize the query data into a reporting database.
- Use database federation or a foreign data wrapper if the DBMS supports it and it is properly governed.
- Build an aggregated read model updated asynchronously.

Example combining two sources in a reactive pipeline:

~~~java
public Mono<OrderAuditView> loadOrderAndAudit(Long orderId) {
    Mono<Order> order =
        orderRepository.findById(orderId);

    Mono<List<AuditEvent>> events =
        auditRepository.findByOrderId(orderId)
            .collectList();

    return Mono.zip(order, events)
        .map(tuple -> new OrderAuditView(
            tuple.getT1(),
            tuple.getT2()
        ));
}
~~~

The two publishers can be subscribed concurrently by Mono.zip. Each repository uses its own routed template/ConnectionFactory.

If data consistency at the exact same point in time across both databases is required, concurrent reads do not automatically provide a distributed snapshot. Determine the level of business consistency required and either accept or resolve data skew.

### 15.1. Do Not Assume One Repository Can Use Two Templates Per Method

A repository interface is registered with a single entityOperationsRef. If methods need to access two databases, split the repository by data source or use two separate data-access components.

Do not try to route a method based on a database name parameter inside a repository if the infrastructure is not designed for it. Splitting repositories gives each interface a well-defined data source.

## 16. Mapping Context, Converters, and Auditing with Multiple Templates

Each R2dbcEntityTemplate has associated mapping and conversion configuration. When two databases use different schemas or data types, separate configuration may be needed:

- Naming strategy.
- Custom converters.
- Mapping context.
- Dialect.
- Auditing configuration.
- Entity types and corresponding schemas.

For example, the orders database stores status as a string code while the audit database stores numeric codes. Do not assume converters from one template automatically apply to another template.

Place converters per data source and register them in the corresponding R2dbcCustomConversions. When using automatic configuration, verify which conversion service each template uses.

### 16.1. Auditing Per Data Source

If both databases need auditing, determine how callbacks/auditing are registered for each mapping context and entity type. Do not just enable one configuration and assume all custom templates use the same auditor and mapping context if you created them manually.

The auditor can use a shared reactive security context, but auditing fields and schemas still need to be compatible in each database.

### 16.2. Naming Strategy and Table Mapping

The same Java class can be used across two databases with different tables/columns. However, sharing an entity across differing schemas can make mapping hard to follow.

If structures differ, consider separating entities or configuring separate mappings instead of relying on a single set of @Table/@Column annotations for both schemas.

## 17. Testing Multi-Database Configurations

A multi-ConnectionFactory configuration should be verified with integration tests against real databases or corresponding containers.

### 17.1. Checking Bean Wiring

You can verify that the ApplicationContext contains the right beans with the expected names:

~~~java
assertThat(context.getBean("ordersConnectionFactory"))
    .isInstanceOf(ConnectionFactory.class);

assertThat(context.getBean("auditConnectionFactory"))
    .isInstanceOf(ConnectionFactory.class);
~~~

This only checks wiring. It does not prove the two beans connect to two different databases.

### 17.2. Checking Repository Routing

Create distinguishable data in each database:

- The orders database has a specific Order ID.
- The audit database has a distinct AuditEvent ID.

Call each repository and verify it only sees data from its configured source. This catches mis-scanned repository packages or wrong entityOperationsRef values.

### 17.3. Checking DatabaseClient Routing

Use each DatabaseClient to execute a query verifying the database/schema name or reading a table that exists only in the corresponding source.

Do not just check that the bean is injected. Confirm SQL is actually sent to the intended database.

### 17.4. Checking Transaction Managers

Perform a write operation followed by an error in the same publisher. Verify that the corresponding transaction manager rolls back the data on the right database.

Also verify that an orders transaction is not mistakenly treated as an audit transaction. Both data sources need separate tests.

### 17.5. Checking Migrations and Startup

In the test environment, verify:

- The orders schema has been created.
- The audit schema has been created.
- The corresponding repositories initialize.
- Both ConnectionFactory beans can connect.
- An unavailable database is handled according to the chosen startup policy.
- There is no ambiguous bean injection.

## 18. Common Mistakes

| Mistake or Confusion | Cause | How to Fix |
|---|---|---|
| NoUniqueBeanDefinitionException for ConnectionFactory | Multiple beans of the same type with injection lacking qualifier/primary | Use @Qualifier or one intentional @Primary |
| Repository queries the wrong database | Repository package bound to wrong entityOperationsRef | Check @EnableR2dbcRepositories and template name |
| Bean in entityOperationsRef not found | Bean name mismatch or template not created | Align bean name and configuration |
| Two configurations scan the same package | Duplicate repository registration or unclear routing | Separate non-overlapping repository packages |
| DatabaseClient uses wrong source | Default bean injected or client created from wrong factory | Create separate clients and use qualifiers |
| @Transactional uses wrong manager | Transaction manager not specified when multiple exist | Specify manager name explicitly |
| Thinking entityOperationsRef selects transaction manager | Confusing repository routing with transaction routing | Configure both independently |
| Thinking two managers create a distributed transaction | Each manager manages one ConnectionFactory | Use outbox/saga or a dedicated distributed solution |
| Assuming Boot creates all ConnectionFactory beans from app.r2dbc.* | Custom properties not bound/configured | Write configuration creating each bean |
| Auto-configured and manual beans share the same name | Relying on implicit override | Choose explicit auto-config or custom strategy |
| Using one pool for multiple databases | ConnectionFactory does not match data source | Create a separate pool per factory |
| Migration only runs on primary database | Only one migration source configured | Configure migrations separately per database |
| One repository needs to access two databases | Repository only binds one entityOperationsRef | Split repositories or query components by source |
| Direct JOIN across two databases on different servers | One connection only runs SQL within its database/dialect | Combine reactive results or build a read model/federation |
| One database's converter accidentally applied to another | Mapping/conversion configuration not cleanly separated | Configure converters per template |

## 19. Workflow for Declaring Multiple ConnectionFactory Beans

When adding a second or third database, follow this sequence:

1. Identify the purpose and data ownership of each database.
2. Set separate configuration prefixes for each source, such as app.r2dbc.orders and app.r2dbc.audit.
3. Create one ConnectionFactory bean per database.
4. Name beans after the data source and use qualifiers at every ambiguous injection point.
5. Only use @Primary if there truly is a single default source.
6. Create a separate DatabaseClient if that source needs direct SQL.
7. Create a separate R2dbcEntityTemplate for repository/entity mapping.
8. Separate repository packages by data source.
9. Use @EnableR2dbcRepositories with matching basePackages and entityOperationsRef for each package.
10. Create a separate R2dbcTransactionManager for each ConnectionFactory.
11. Select the transaction manager explicitly with @Transactional or the corresponding TransactionalOperator.
12. Configure pool, timeout, converters, dialect, and auditing separately as needed.
13. Configure migrations for each schema.
14. Test repositories, clients, transactions, and routing against real databases.
15. If a use case writes to multiple databases, design outbox/saga instead of assuming an atomic transaction.

## 20. Self-Check Exercises

### Exercise 1: Naming Beans

An application has orders and audit databases. Name two ConnectionFactory beans and two R2dbcEntityTemplate beans.

Hint:

~~~text
ordersConnectionFactory
ordersEntityTemplate
auditConnectionFactory
auditEntityTemplate
~~~

### Exercise 2: Resolving Ambiguous Injection

A constructor needs the audit ConnectionFactory, but the application has two beans of the same type. What must be added?

Hint:

~~~java
public AuditService(
    @Qualifier("auditConnectionFactory")
    ConnectionFactory connectionFactory
) {
    this.connectionFactory = connectionFactory;
}
~~~

### Exercise 3: Routing Repositories

Repositories in package com.example.audit.repository need to use auditEntityTemplate. Declare the annotation.

Hint:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.audit.repository",
    entityOperationsRef = "auditEntityTemplate"
)
~~~

### Exercise 4: Selecting the Transaction Manager

A method only updates the orders database. Specify the transaction manager.

Hint:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> updateOrder(Long id) {
    // ...
}
~~~

### Exercise 5: Two Databases and One Transaction

A service updates orders and then writes an audit record using two repositories. Does @Transactional with ordersTransactionManager guarantee both databases roll back together?

Hint: No. That manager manages transactions on the orders ConnectionFactory. The audit database has an independent transaction or does not participate in that transaction. Use outbox/saga if reliable coordination is needed.

### Exercise 6: DatabaseClient

An SQL INSERT into audit_events needs to run on the audit database. Which bean should the service inject?

Hint: auditDatabaseClient with @Qualifier("auditDatabaseClient").

### Exercise 7: Primary

If ordersConnectionFactory is marked @Primary, can you omit all @Qualifier annotations in the application?

Hint: No. @Primary only picks the default candidate at injection points without a qualifier. Audit operations still need to explicitly select the audit bean.

### Exercise 8: Migration

The application adds an audit database, but migrations only run for the orders database. What needs to be done?

Hint: Configure separate migrations for the audit database and ensure the audit schema is ready before repositories operate.

## 21. Key Takeaways

- Each R2DBC database needs its own ConnectionFactory.
- Name beans after the data source, such as ordersConnectionFactory and auditConnectionFactory.
- Use @Qualifier to inject the right bean when multiple candidates of the same type exist.
- @Primary only supplies a default candidate; it does not replace repository and transaction routing.
- Create a separate DatabaseClient for each ConnectionFactory if direct SQL is needed.
- Create a separate R2dbcEntityTemplate for each data source.
- Use @EnableR2dbcRepositories with basePackages and entityOperationsRef to bind a repository package to the right template.
- entityOperationsRef does not select the transaction manager.
- Create a separate R2dbcTransactionManager for each ConnectionFactory.
- Specify the transaction manager via @Transactional(transactionManager = "...") or the corresponding TransactionalOperator.
- Configure converters, dialect, auditing, pool, and migrations per database as needed.
- One transaction manager does not automatically manage multiple databases; multiple managers do not automatically form a distributed transaction.
- For use cases that need to coordinate multiple databases, consider outbox, saga, and idempotency.
- One DatabaseClient only queries the data source its ConnectionFactory connects to; joining two independent databases requires another solution.
- Test bean wiring, repository routing, SQL routing, and rollback on each database.

When declaring multiple ConnectionFactory beans, name them clearly and connect each data source with its corresponding DatabaseClient, R2dbcEntityTemplate, repository package, and transaction manager. Qualifiers pick the right bean, entityOperationsRef routes repositories, and the transaction manager defines the commit/rollback scope. These three decisions must be configured separately and tested together to avoid operating on the wrong database or misunderstanding atomicity across multiple data sources.
