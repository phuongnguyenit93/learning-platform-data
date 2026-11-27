# Wrong Bean, Wrong Repository Group, or Wrong Transaction Manager

When a Spring Data R2DBC application has multiple persistence configurations, the bug often does not lie in the SQL query itself, but in how Spring wires the components together. A repository may be backed by the `R2dbcEntityTemplate` of another database; a repository package may be scanned by the wrong configuration; a Service may inject the wrong `ConnectionFactory`; or `@Transactional` may select a transaction manager that does not manage the connection the repository uses.

These errors sometimes do not fail at application startup. A simple query may still run, yet data appears from another database, transactions do not roll back, or part of a write operation commits unexpectedly. Therefore, when diagnosing R2DBC, trace the entire wiring chain: repository package → `R2dbcEntityOperations`/`R2dbcEntityTemplate` → `ConnectionFactory` → `ReactiveTransactionManager`.

This article covers how to identify bean errors, repository group errors, and transaction manager errors; how to configure single- and multi-database setups clearly; how to verify that repositories and transactions share the right connection factory; and how to write tests that catch configuration mistakes before production.

## 1. Map of Components That Must Be Linked

In a Spring Data R2DBC application, the main components have distinct roles:

| Component | Role | Error When Miswired |
|---|---|---|
| `ConnectionFactory` | Creates connections to a specific database/pool | Connects to wrong database, wrong credentials, or wrong pool |
| `DatabaseClient` | Executes reactive SQL via `ConnectionFactory` | Query runs against an unexpected data source |
| `R2dbcEntityTemplate` | Entity mapping and persistence operations over R2DBC | Wrong mapping/dialect or wrong connection |
| `R2dbcEntityOperations` | Abstraction used by the repository infrastructure | Repository bound to the wrong template |
| `@EnableR2dbcRepositories` | Selects repository packages to scan and operations/manager beans | Repository created in the wrong persistence group |
| `ReactiveTransactionManager` | Manages reactive transactions | Transaction does not cover repository calls |
| `@Transactional` | Marks transaction boundaries | Selects wrong manager or uses wrong transaction model |

A repository group should be treated as a unified configuration:

```text
Repository package: orders.repository
          |
          v
R2dbcEntityOperations: ordersEntityTemplate
          |
          v
ConnectionFactory: ordersConnectionFactory
          |
          +------------------------------+
                                         |
                                         v
ReactiveTransactionManager: ordersTransactionManager
          |
          v
Same ConnectionFactory: ordersConnectionFactory
```

The critical requirement is that the repository/template and the transaction manager must use the same corresponding `ConnectionFactory` when they need to participate in the same transaction. Having the same database URL is not enough to guarantee they share the same resource instance and transaction context.

## 2. Identifying Bean Errors at Application Startup

Bean errors usually surface early as exceptions during `ApplicationContext` creation. Read the deepest `Caused by` and the bean currently being created, not just the first line of the stack trace.

### 2.1. NoSuchBeanDefinitionException

Example message:

```text
NoSuchBeanDefinitionException:
No qualifying bean of type 'io.r2dbc.spi.ConnectionFactory' available
```

Common causes:

- R2DBC driver is not on the runtime classpath.
- `spring.r2dbc.url` or `ConnectionFactory` configuration is missing.
- The bean belongs to an inactive profile.
- The configuration class is not component-scanned.
- Auto-configuration backed off because its conditions no longer hold.
- `@Qualifier` references the wrong bean name.
- Repository configuration references an `R2dbcEntityOperations` or transaction manager bean that is not registered.

How to fix:

1. Verify the driver dependency is on the runtime classpath.
2. Verify the URL starts with the appropriate R2DBC scheme, e.g., `r2dbc:postgresql:`.
3. Check the active profiles and actual property sources.
4. Check that the package containing `@Configuration` is scanned/imported.
5. Check bean names in `@Qualifier`, `entityOperationsRef`, and `transactionManagerRef`.
6. If using multiple databases, declare each bean explicitly instead of waiting for auto-configuration to guess.

### 2.2. NoUniqueBeanDefinitionException

Example:

```text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2:
ordersConnectionFactory, billingConnectionFactory
```

This error occurs when an injection point expects a single bean, but multiple candidates of the same type exist.

Ambiguous example:

```java
@Service
class OrderLookupService {

    private final DatabaseClient databaseClient;

    OrderLookupService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }
}
```

If there are two `DatabaseClient` beans, Spring does not know which bean to pick. Specify `@Qualifier`:

```java
@Service
class OrderLookupService {

    private final DatabaseClient databaseClient;

    OrderLookupService(
            @Qualifier("ordersDatabaseClient") DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }
}
```

`@Primary` can designate a default candidate for unqualified injections. However, with multi-database configurations, qualifiers usually express intent more clearly. `@Primary` does not automatically pick the right repository group and does not replace `entityOperationsRef`/`transactionManagerRef`.

### 2.3. Bean Created, but Using the Wrong Configuration

This is more dangerous than a startup failure. If a default bean is marked `@Primary`, unqualified injections can receive the primary database even when a Service needs a secondary database.

The application still runs and queries still return data, but the data may come from the wrong database. Check bean names and `ConnectionFactoryMetadata`, and use distinguishing fixture data in integration tests to verify the real source.

## 3. Distinguishing Three Error Categories: Bean, Repository Group, and Transaction Manager

The three error groups show different symptoms:

| Symptom | First Suspect | Where to Check |
|---|---|---|
| `ApplicationContext` fails to start, missing bean | Bean not registered or wrong qualifier | Configuration, profiles, component scan, dependencies |
| `ApplicationContext` reports multiple beans of same type | Unqualified injection | `@Qualifier`, `@Primary`, constructor injection |
| Repository query runs on another database | Miswired repository group/template | `basePackages`, `entityOperationsRef`, template bean |
| Some repositories use right DB, others use wrong DB | Overlapping package scans or unclear configuration groups | Multiple `@EnableR2dbcRepositories` and package boundaries |
| `@Transactional` does not roll back R2DBC operations | Non-reactive manager or different `ConnectionFactory` | `ReactiveTransactionManager`, manager qualifier |
| Repository A rolls back, but repository B still commits | Two repositories use two connection factories/transaction managers | Resource boundary and database grouping |
| Transaction does not cover query inside `flatMap` | Publisher subscribed separately or context detached | `subscribe()`, `block()`, pipeline composition |
| Error only happens in a test slice | Test context does not load full configuration | `@DataR2dbcTest`, `@Import`, dynamic properties |

Do not change multiple configuration layers at the same time before identifying where the error lies. Verify each link in order, from repository down to connection factory and then to transaction manager.

## 4. Single Database: Minimal Configuration and Verification

With a single database, Spring Boot can usually auto-configure `ConnectionFactory`, `DatabaseClient`, `R2dbcEntityTemplate`, and the reactive transaction manager when appropriate dependencies and properties are present.

Example configuration:

```yaml
spring:
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/store
    username: store_app
    password: ${DB_PASSWORD}
```

Repository:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<CustomerEntity, Long> {
}
```

In a simple setup, there is no need to declare `@EnableR2dbcRepositories` if Spring Boot already scans repositories in the application's default package. If you declare the annotation manually, make sure the base package and bean references match.

### 4.1. When Should Beans Be Declared Explicitly?

Explicit declaration helps when:

- There are multiple `ConnectionFactory` beans.
- Repositories live outside the default scan package.
- Custom conversions/dialects are needed.
- Multiple independent repository groups are needed.
- You want to explicitly specify which transaction manager each group uses.

Do not recreate a new `ConnectionFactory` inside every bean just to pass the same URL. Inject the same bean instance via qualifier so the template and transaction manager share the exact resource.

## 5. Configuring Multiple Databases and Multiple Repository Groups

Suppose an application has two databases:

- `orders`: stores customers and orders.
- `billing`: stores invoices and payments.

Separate repository packages:

```text
com.example.app.orders.repository
  OrderRepository.java
  CustomerRepository.java

com.example.app.billing.repository
  InvoiceRepository.java
  PaymentRepository.java
```

Each group needs its own set of beans:

```text
ordersRepository package
  -> ordersEntityTemplate
  -> ordersConnectionFactory
  -> ordersTransactionManager

billingRepository package
  -> billingEntityTemplate
  -> billingConnectionFactory
  -> billingTransactionManager
```

### 5.1. Configuring the Orders Database

```java
@Configuration
@EnableR2dbcRepositories(
        basePackages = "com.example.app.orders.repository",
        entityOperationsRef = "ordersEntityTemplate",
        transactionManagerRef = "ordersTransactionManager")
public class OrdersR2dbcConfiguration {

    @Bean
    @Primary
    ConnectionFactory ordersConnectionFactory(
            @Value("${app.r2dbc.orders.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean
    R2dbcEntityOperations ordersEntityTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean
    ReactiveTransactionManager ordersTransactionManager(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
```

`entityOperationsRef` is the `R2dbcEntityOperations` bean name used by the repository group. `R2dbcEntityTemplate` implements this abstraction. `transactionManagerRef` is the reactive transaction manager bean name configured for the repository group.

### 5.2. Configuring the Billing Database

```java
@Configuration
@EnableR2dbcRepositories(
        basePackages = "com.example.app.billing.repository",
        entityOperationsRef = "billingEntityTemplate",
        transactionManagerRef = "billingTransactionManager")
public class BillingR2dbcConfiguration {

    @Bean
    ConnectionFactory billingConnectionFactory(
            @Value("${app.r2dbc.billing.url}") String url) {
        return ConnectionFactories.get(url);
    }

    @Bean
    R2dbcEntityOperations billingEntityTemplate(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean
    ReactiveTransactionManager billingTransactionManager(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
```

The configurations use separate packages, separate templates, separate connection factories, and separate transaction managers. Marking `ordersConnectionFactory` as `@Primary` only provides a default choice for unqualified single-value injections; the billing configuration code still explicitly specifies `billingConnectionFactory`.

In real applications, prefer `@ConfigurationProperties` binding instead of many `@Value` annotations when configurations have many properties such as username, password, pool size, SSL, and timeouts. The code above focuses on bean wiring.

### 5.3. Do Not Let Package Scans Overlap

If both `@EnableR2dbcRepositories` scan `com.example.app`, a repository can be discovered by multiple configurations or registered with the wrong operations. Restrict packages using specific packages or marker classes:

```java
@EnableR2dbcRepositories(
        basePackageClasses = OrdersRepositoryMarker.class,
        entityOperationsRef = "ordersEntityTemplate",
        transactionManagerRef = "ordersTransactionManager")
```

Create a marker class in the corresponding repository package. This avoids relying on package string literals that might break during refactoring.

### 5.4. Do Not Confuse `entityOperationsRef` with `transactionManagerRef`

- `entityOperationsRef` selects the template/operations used to create repositories and perform mapping/queries.
- `transactionManagerRef` selects the reactive transaction manager for the repository infrastructure.

The two references have distinct responsibilities. Configuring the right template with the wrong transaction manager can still allow repository queries to hit the right database while transactions fail to cover them as expected.

## 6. Wrong Repository Group Due to Package Scanning

`@EnableR2dbcRepositories` decides which repository interfaces are registered by a configuration. If the package scan is too broad, a repository group can be bound to the wrong template.

### 6.1. Example of an Overly Broad Configuration

```java
@EnableR2dbcRepositories(
        basePackages = "com.example.app",
        entityOperationsRef = "ordersEntityTemplate")
class OrdersR2dbcConfiguration {
}
```

If `com.example.app` contains both `orders.repository` and `billing.repository`, both groups may be processed by the orders configuration. When a billing repository is called, it still runs, but goes through `ordersEntityTemplate`.

### 6.2. Separating Packages by Bounded Context

```text
com.example.app
  orders
    domain
    service
    repository
  billing
    domain
    service
    repository
```

Each configuration scans only its own repository package. Do not place repository interfaces in a shared parent package if the two databases have different mappings.

### 6.3. Repository Interfaces Extending a Shared Base Repository

A base repository interface can be reused via generics, but pay attention to where Spring scans that interface. If the base interface is not a standalone repository, mark it with `@NoRepositoryBean` so Spring Data does not try to instantiate a repository for the base interface itself.

```java
@NoRepositoryBean
public interface BaseReadRepository<T, ID>
        extends ReactiveCrudRepository<T, ID> {
}
```

Concrete repositories extend the base interface and reside in the proper scan package. Do not let a base interface be scanned as a concrete repository without a specific domain type.

### 6.4. Checking Where a Repository Bean Was Registered

When suspecting a repository belongs to the wrong group, check:

- Bean name and bean definition of the repository.
- Which `@EnableR2dbcRepositories` configuration scans that package.
- Which `entityOperationsRef` is assigned to the repository factory.
- Which `ConnectionFactory` that template injects.
- Whether any packages are scanned multiple times.

Do not look only at the repository bean name. The interface name does not tell you which database it actually uses.

## 7. Mismatched ConnectionFactory Between Template and TransactionManager

This is a common reason transactions fail to work even when `@Transactional` is declared.

Misconfigured example:

```java
@Bean
R2dbcEntityOperations ordersEntityTemplate() {
    ConnectionFactory factory = ConnectionFactories.get(ordersUrl);
    return new R2dbcEntityTemplate(factory);
}

@Bean
ReactiveTransactionManager ordersTransactionManager() {
    ConnectionFactory factory = ConnectionFactories.get(ordersUrl);
    return new R2dbcTransactionManager(factory);
}
```

The two beans create two separate `ConnectionFactory` instances. Even with the same URL, they can be two distinct pools/connection resources. The transaction manager binds connections based on the resource it manages; repository operations via a different template may not participate in the same transaction.

The correct configuration is to create one bean and inject it into both:

```java
@Bean
ConnectionFactory ordersConnectionFactory() {
    return ConnectionFactories.get(ordersUrl);
}

@Bean
R2dbcEntityOperations ordersEntityTemplate(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcEntityTemplate(factory);
}

@Bean
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}
```

Both the template and the transaction manager use the same `ordersConnectionFactory` bean. If pooling is used, ensure both reference the exact configured pooled `ConnectionFactory`, rather than one side using the raw factory and the other using a different pool wrapper.

## 8. Choosing the Right Transaction Manager

Spring has several types of transaction managers. Not every manager can manage R2DBC connections.

| Transaction Manager | Primary Resource | Suitable For |
|---|---|---|
| `R2dbcTransactionManager` | R2DBC `ConnectionFactory` | Reactive R2DBC operations |
| `DataSourceTransactionManager` | JDBC `DataSource` | Imperative JDBC transactions |
| `JpaTransactionManager` | JPA `EntityManagerFactory` | JPA transactions |
| `ReactiveMongoTransactionManager` | Reactive MongoDB database factory | Reactive MongoDB transactions |
| `ReactiveTransactionManager` | Reactive interface | Abstraction for reactive transaction managers |

If a repository uses R2DBC while `@Transactional` selects `DataSourceTransactionManager`, that JDBC transaction will not automatically manage the R2DBC connection. The two resources may point to the same database server yet remain two separate connections/transactions.

### 8.1. Configuring R2dbcTransactionManager

```java
@Bean
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcTransactionManager(factory);
}
```

This manager must use the same `ConnectionFactory` as the `R2dbcEntityTemplate`/repositories in the orders group.

### 8.2. Specifying the Manager on `@Transactional`

When multiple transaction managers exist, specify the bean name:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<OrderEntity> createOrder(OrderCommand command) {
    return inventoryRepository.reserve(command.items())
            .then(orderRepository.save(toOrder(command)));
}
```

If omitted, Spring resolves a default manager based on bean configuration/`@Primary` and how transaction infrastructure is registered. In applications with multiple managers, do not rely on default resolution if the business operation requires a specific database.

### 8.3. Selecting a Manager by Qualifier in the Annotation

`@Transactional` supports the `transactionManager` attribute (and its `value` alias in corresponding Spring versions) to pick a manager by bean name/qualifier. Use the exact bean name registered in the `ApplicationContext`. A class name or database URL cannot substitute for the bean name.

## 9. Distinguishing Reactive Transactions from Imperative Transactions

R2DBC is reactive. Transactions are managed across the reactive pipeline and Reactor Context, rather than relying on a single thread holding a connection for the entire method.

### 9.1. Methods Returning `Mono`/`Flux`

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return orderRepository.save(order);
}
```

With a reactive return type and a reactive transaction manager, the transaction is attached to the publisher subscription. Execution occurs when the publisher is subscribed.

### 9.2. Using `TransactionalOperator` for Explicit Transactions

```java
@Bean
TransactionalOperator ordersTransactionalOperator(
        @Qualifier("ordersTransactionManager")
        ReactiveTransactionManager transactionManager) {
    return TransactionalOperator.create(transactionManager);
}
```

Usage:

```java
public Mono<OrderEntity> createOrder(OrderEntity order) {
    return orderRepository.save(order)
            .as(ordersTransactionalOperator::transactional);
}
```

`TransactionalOperator` is well suited when you want to define transaction boundaries directly in the pipeline, such as around a specific publisher segment. You must choose the operator tied to the manager of the database being modified.

### 9.3. Do Not Use Imperative `TransactionTemplate` for R2DBC

`TransactionTemplate` belongs to the imperative `PlatformTransactionManager` model. For R2DBC, use `@Transactional` with a reactive manager or `TransactionalOperator`. Do not use `block()` to force a reactive repository to run inside a JDBC transaction.

### 9.4. The Publisher Must Remain Inside the Transaction Boundary

Avoid creating detached subscriptions:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Void> createOrder(OrderEntity order) {
    orderRepository.save(order).subscribe(); // Wrong: detached subscription
    return Mono.empty();
}
```

Replace with composition:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Void> createOrder(OrderEntity order) {
    return orderRepository.save(order).then();
}
```

When calling `subscribe()` manually, the transaction interceptor may complete the returned publisher before the detached write finishes. The new subscription also does not necessarily share the same transaction context.

## 10. A Single Transaction Manager Only Manages Its Own Resource

If an application has orders and billing on two `ConnectionFactory` beans, a single `R2dbcTransactionManager` does not automatically create an atomic transaction spanning both databases.

Example:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Void> createOrderAndInvoice(OrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order -> invoiceRepository.save(toInvoice(order)))
            .then();
}
```

If `orderRepository` belongs to the orders database and `invoiceRepository` belongs to the billing database, the orders transaction manager only manages the orders connection. The invoice operation may run on another connection and commit independently. If the invoice step fails, the order operation does not necessarily roll back with it.

### 10.1. Choosing a Design for Cross-Database Workflows

Common options:

- **Separate workflows:** independent transactions per database if business rules allow.
- **Saga/compensation:** each step commits separately, and later failures trigger compensating actions.
- **Transactional outbox:** write an event in the same transaction as the primary data, then a consumer updates the other database/service.
- **Distributed transactions:** only when the platform and drivers/databases fully support an appropriate mechanism; do not assume R2DBC provides universal two-phase XA.

Do not place a single `@Transactional` around two repositories and assume it guarantees cross-database atomicity. Write an integration test that deliberately fails the second database and verify the actual resulting state.

## 11. Combining JDBC and R2DBC in the Same Application

An application may use JDBC for migrations or a legacy module and R2DBC for the reactive runtime. This creates two resource types:

```text
JDBC DataSource -> DataSourceTransactionManager

R2DBC ConnectionFactory -> R2dbcTransactionManager
```

A single transaction manager does not automatically manage both. If a method uses both a JDBC repository and an R2DBC repository within `@Transactional`, you must know which manager is chosen and which resources participate.

### 11.1. JDBC Migrations Do Not Mean Runtime Transactions Use JDBC

Flyway/Liquibase may use JDBC to apply DDL while application repositories run over R2DBC. These are two distinct phases; successful migration via JDBC does not make R2DBC repositories participate in JDBC transactions.

### 11.2. Do Not Use `@Primary` to Mask Transaction Design

If both `PlatformTransactionManager` and `ReactiveTransactionManager` exist, marking one bean `@Primary` may satisfy some default injections, but it does not make the two transaction manager types interchangeable. Specify the right manager at each business boundary and check the method return type.

## 12. Wiring Dependent Beans Clearly

With multiple databases, bean names should reflect both role and data group. A useful naming convention:

| Role | Orders | Billing |
|---|---|---|
| `ConnectionFactory` | `ordersConnectionFactory` | `billingConnectionFactory` |
| `DatabaseClient` | `ordersDatabaseClient` | `billingDatabaseClient` |
| `R2dbcEntityOperations` | `ordersEntityTemplate` | `billingEntityTemplate` |
| Transaction manager | `ordersTransactionManager` | `billingTransactionManager` |
| Repository package | `orders.repository` | `billing.repository` |

Example `DatabaseClient` bean:

```java
@Bean
DatabaseClient ordersDatabaseClient(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return DatabaseClient.create(factory);
}
```

If `R2dbcEntityTemplate` is created directly from `ConnectionFactory`, there is no need to declare a separate `DatabaseClient` bean if nothing injects it. Avoid creating unnecessary duplicate beans.

### 12.1. Using `@ConfigurationProperties` for Multi-Database Configuration

Instead of hardcoding URLs and credentials:

```yaml
app:
  r2dbc:
    orders:
      url: ${ORDERS_R2DBC_URL}
    billing:
      url: ${BILLING_R2DBC_URL}
```

In real systems, configuration may also include username, password, pool options, SSL, and timeouts. Group them into a configuration properties class per database to enable validation and reduce typos in property names.

Do not write passwords in source code or log configuration values. Use secret stores/environment injection per the deployment platform.

### 12.2. Avoid Calling Other `@Bean` Methods Directly When Proxy Semantics Are Unclear

In full `@Configuration` classes, Spring can intercept inter-`@Bean` method calls to return the singleton bean. In lite configuration or when methods are invoked as plain Java calls, new instances can accidentally be created. The clearest approach is injecting dependencies via method parameters:

```java
@Bean
R2dbcEntityOperations ordersEntityTemplate(
        @Qualifier("ordersConnectionFactory") ConnectionFactory factory) {
    return new R2dbcEntityTemplate(factory);
}
```

Do not call `ordersConnectionFactory()` directly to obtain the instance when you can inject the bean via a parameter.

## 13. Diagnosing from Specific Symptoms

### 13.1. Repository Is Not Created

Check:

1. Does the interface extend `ReactiveCrudRepository` or an appropriate repository abstraction?
2. Is the package within `basePackages`/`basePackageClasses`?
3. Was `@NoRepositoryBean` mistakenly placed on a concrete repository?
4. Does `entityOperationsRef` point to an existing bean of the right type?
5. Does another repository configuration scan the same package?
6. Did the `ApplicationContext` exclude repository auto-configuration?

### 13.2. Repository Works, but Queries the Wrong Database

Check step by step:

1. Which package does the repository belong to?
2. Which `@EnableR2dbcRepositories` configuration scans that package?
3. Which template is `entityOperationsRef` selecting?
4. Which `ConnectionFactory` bean does that template inject?
5. Which database does that factory's URL/metadata point to?
6. Is `@Primary` causing another service to inject the wrong factory?

Create one fixture that exists only in database A and another fixture that exists only in database B. Query through each repository to confirm the actual data source.

### 13.3. `@Transactional` Does Not Roll Back

Check:

1. Does the method return `Mono`/`Flux` or execute imperatively?
2. Is the selected manager a `ReactiveTransactionManager`?
3. Does the manager use the same `ConnectionFactory` as the repository?
4. Does `@Transactional` specify the manager when multiple managers exist?
5. Is there a `subscribe()`/`block()` or callback detached from the pipeline?
6. Does `onErrorResume` swallow errors before the transaction boundary?
7. Do the operations actually target the same database/resource?
8. Does the test read the final state from an independent transaction/connection?

### 13.4. Transaction Only Works for One Repository

If two repositories belong to two database groups, they may use two transaction managers. One manager does not manage the other group's connections. Clarify whether the business requirement needs a single-database transaction or a cross-database workflow with compensation/outbox.

### 13.5. Error Only Occurs in Tests

Test slices like `@DataR2dbcTest` may build only a partial `ApplicationContext` or override datasource properties by profile. Check:

- `@Import` of the required persistence configurations.
- Whether `@DynamicPropertySource` supplies the right URL for each factory.
- Whether the test loads the right repository group.
- Whether migrations/schemas are applied to the right database.
- Whether the test transaction manager shares the factory with the repository.

Do not alter production configuration just to make a test slice pass if the test context simply has not imported the right configuration.

## 14. Tools for Inspecting Beans and Auto-Configuration

When unsure which beans Spring created, inspect the `ApplicationContext` instead of guessing.

### 14.1. Listing Beans by Type

You can use a temporary diagnostic component or breakpoint:

```java
@Component
class PersistenceBeanDiagnostics implements ApplicationRunner {

    private final ApplicationContext context;

    PersistenceBeanDiagnostics(ApplicationContext context) {
        this.context = context;
    }

    @Override
    public void run(ApplicationArguments args) {
        context.getBeansOfType(ConnectionFactory.class)
                .forEach((name, bean) ->
                        log.info("ConnectionFactory bean: {} -> {}",
                                name, bean.getMetadata().getName()));

        context.getBeansOfType(R2dbcEntityOperations.class)
                .forEach((name, bean) ->
                        log.info("R2dbcEntityOperations bean: {} -> {}",
                                name, bean.getClass().getName()));

        context.getBeansOfType(ReactiveTransactionManager.class)
                .forEach((name, bean) ->
                        log.info("ReactiveTransactionManager bean: {} -> {}",
                                name, bean.getClass().getName()));
    }
}
```

This is a diagnostic example; import types and logger as appropriate for the project. Avoid logging connection URLs with passwords or object `toString()` outputs containing credentials. You can remove the component after investigation or restrict it to a debug profile.

### 14.2. Spring Boot Condition Evaluation Report

Start with `--debug` to see which auto-configuration conditions matched or backed off. This is useful when a default bean was not created because the application declared a bean of the same type or missed a dependency/property.

If Actuator is enabled, the `beans` and `conditions` endpoints can help inspect the `ApplicationContext`/auto-configuration. Protect these endpoints with security and expose them only in appropriate environments; do not expose internal bean details to the public Internet.

### 14.3. Checking the Dependency Tree

If an error appears after upgrading versions, inspect the dependency tree to spot multiple versions of R2DBC SPI, drivers, Spring Data, or pools. Use the Spring Boot BOM or consistent dependency management. Do not override a core library just to fix a compile error without verifying runtime compatibility.

## 15. Testing Multi-Repository-Group Configurations

Each repository group should have integration tests proving it hits the right database and uses the right transaction manager.

### 15.1. Testing Each Group's Data Source

Create a marker row in each database:

- Orders DB has order code `ORD-ONLY-ORDERS`.
- Billing DB has invoice number `INV-ONLY-BILLING`.

Call the corresponding repository and verify only the right database can return the row. Do not use the same fixture value in both databases, as that hides miswired templates.

### 15.2. Testing Transaction Rollback for Each Group

For orders:

1. Start a transaction using `ordersTransactionManager`.
2. Perform a valid write.
3. Emit an error in the next step.
4. Read back via an independent subscription/transaction.
5. Verify both changes rolled back according to contract.

Repeat similarly for billing with its own manager. This test confirms each manager is bound to the right factory.

### 15.3. Testing Against Accidental Cross-Database Mixing

Invoke a service that operates on orders and billing, and deliberately fail the second step. Confirm the actual state matches the design: without distributed transactions, do not assume both databases roll back together. If using outbox/saga, check the corresponding event or compensation.

### 15.4. Testing the Selected Transaction Manager

You can inject the manager by qualifier into a `TransactionalOperator` for tests and verify operations are managed by the right resource. Do not just check that the annotation has the right name; verify final data and rollback behavior.

## 16. Interaction with Spring Data R2DBC Auditing and Custom Conversions

When there are multiple `R2dbcEntityTemplate` beans, each template may need its own mapping/conversion configuration if the databases use different schemas or data types.

### 16.1. Auditing Provider

`@EnableR2dbcAuditing` must be configured in the appropriate application context. If multiple repository groups share an auditor, they can share a `ReactiveAuditorAware` when actor semantics are identical. If each group has different policies, define providers/callbacks and configuration scopes clearly; avoid two competing auditing configurations or ambiguous bean references.

### 16.2. Custom Conversions

An `R2dbcCustomConversions` or mapping context attached to a template can determine how enums, JSON, or value objects are mapped. When multiple databases have different native types, do not assume one converter works across all drivers. Test mapping through each group's repository.

### 16.3. Dialect

`R2dbcEntityTemplate` needs a dialect matching its `ConnectionFactory`. When configuring multiple databases, do not share one fixed dialect across all of them if the database systems differ. Verify that generated SQL matches the respective driver/database group.

## 17. Common Mistakes

### Adding Only `@Primary` and Assuming Repositories Use the Right Database

`@Primary` resolves default injection, not repository package selection or `entityOperationsRef`. Configure each group explicitly.

### Two Configurations Scanning the Same Package

Repositories can be registered multiple times or bound to the wrong operations. Keep `basePackages`/`basePackageClasses` non-overlapping.

### Template and Transaction Manager Creating Separate ConnectionFactories

Even with the same URL, two separate instances/pools may not share transaction resources. Inject the same factory bean into both.

### Using `JpaTransactionManager` or `DataSourceTransactionManager` for R2DBC Repositories

Imperative managers do not manage R2DBC connections. Use `R2dbcTransactionManager` or an appropriate reactive manager.

### Omitting `transactionManager` When Multiple Managers Exist

Spring may pick an unintended default manager. Use `@Transactional(transactionManager = "...")` or a `TransactionalOperator` created from the specific manager.

### Assuming One Transaction Spans Multiple `ConnectionFactory` Beans

One R2DBC manager manages its own resource. Two databases require a distributed workflow design such as outbox/saga if coordination is needed.

### Using `@Transactional` but Calling `subscribe` Inside

A detached subscription can run outside the transaction context. Return and compose publishers with `flatMap`, `then`, or an appropriate operator.

### Using `TransactionTemplate` with Reactive Repositories

This is an imperative abstraction. Use `TransactionalOperator` or reactive annotations.

### Checking Only Bean Existence Without Checking the Data Source

A bean may have the right type while pointing to the wrong database. Verify metadata, safe URLs, and database-specific fixtures.

### Test Slice Configuration Differing from Production

Tests may load only one template/manager or use wrong properties. Import the configuration and provide dynamic properties for each group.

## 18. Systematic Diagnostic Procedure

When you discover a repository or transaction behaving incorrectly, proceed in this order:

1. Read the full exception and determine whether it occurs during context creation, repository creation, or query execution.
2. List all `ConnectionFactory`, `R2dbcEntityOperations`, and `ReactiveTransactionManager` beans by name.
3. Identify the failing repository's package and which `@EnableR2dbcRepositories` configuration scans it.
4. Verify `entityOperationsRef` points to the right template.
5. Verify the template injects the right `ConnectionFactory` bean.
6. Verify the repository group is not covered by another package scan.
7. Identify the manager selected by `@Transactional` or `TransactionalOperator`.
8. Confirm the manager uses the same `ConnectionFactory` as the template/repository.
9. Check that the publisher is not detached via `subscribe()`/`block()` and errors are not swallowed before the transaction boundary.
10. Run an integration test with a fixture that exists only in the target database.
11. Deliberately cause an error mid-transaction and verify the final state from an independent connection.
12. If multiple databases exist, clarify whether business rules require cross-database atomicity.

## 19. Configuration and Operations Checklist

- [ ] Every `ConnectionFactory` has a clear bean name.
- [ ] Any injection with multiple candidates uses `@Qualifier` or an intentionally chosen `@Primary`.
- [ ] Every repository group has a dedicated, non-overlapping scan package.
- [ ] `entityOperationsRef` points to the right `R2dbcEntityTemplate`/`R2dbcEntityOperations`.
- [ ] The template uses the database group's right `ConnectionFactory`.
- [ ] The transaction manager uses the same `ConnectionFactory` bean as the template.
- [ ] `transactionManagerRef` is declared explicitly for each repository group when needed.
- [ ] `@Transactional` specifies the right manager when multiple managers exist.
- [ ] R2DBC repositories use a reactive transaction manager, not a JDBC/JPA manager.
- [ ] Transactional publishers are not detached by nested `subscribe()` or `block()`.
- [ ] `TransactionalOperator` is created from the manager for the right database.
- [ ] Cross-database workflows have outbox/saga/compensation or an appropriate design.
- [ ] Tests prove each repository group accesses the right database.
- [ ] Rollback tests verify final state on a real database.
- [ ] Context tests load the right configuration, profiles, properties, and migrations.
- [ ] Diagnostic logs do not expose passwords or credentials.

When diagnosing R2DBC, do not stop once a bean exists or a query succeeds. Confirm that the repository is scanned into the right group, that group uses the right `R2dbcEntityTemplate`, the template and transaction manager reference the same `ConnectionFactory`, and the transaction is attached to the right reactive pipeline. With multiple databases, each group needs explicit configuration, while cross-database workflows need a dedicated coordination design. Integration tests verifying data sources and rollbacks provide the most reliable evidence to catch misconfigurations before release.
