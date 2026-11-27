# Binding Each Repository Group to the Right R2dbcEntityOperations

When a Spring Data Relational R2DBC application connects to multiple databases, each repository group must be bound to the data-access infrastructure of the database it manages. The decisive configuration point is the **entityOperationsRef** attribute of `@EnableR2dbcRepositories`.

`R2dbcEntityOperations` is the abstraction that the repository infrastructure uses to perform entity operations. `R2dbcEntityTemplate` is the common implementation of this abstraction. Each template must be created from the right `ConnectionFactory`; then each repository group references its corresponding template bean.

For example, repositories managing orders must use `ordersR2dbcEntityOperations`, while repositories managing billing must use `billingR2dbcEntityOperations`. Simply declaring multiple `ConnectionFactory` beans or marking one bean `@Primary` does not automatically route each repository to the right database.

## 1. Role of R2dbcEntityOperations

In Spring Data R2DBC, the main components relate as follows:

| Component | Role |
|---|---|
| `ConnectionFactory` | Provides R2DBC Connections to a database |
| `DatabaseClient` | Executes SQL and binds parameters on a ConnectionFactory |
| `R2dbcEntityOperations` | Abstraction for entity operations such as select, insert, update, delete |
| `R2dbcEntityTemplate` | Implementation of R2dbcEntityOperations, using Spring Data's mapping infrastructure |
| Repository factory | Creates implementations for repository interfaces |
| `@EnableR2dbcRepositories` | Specifies the repository group to scan and the entity operations bean that group uses |

When Spring creates a repository, the repository factory needs to know how to read and write entities. The `R2dbcEntityOperations` bean provides that path.

Single-database model:

~~~text
OrdersRepository
       |
       v
ordersR2dbcEntityOperations
       |
       v
R2dbcEntityTemplate
       |
       v
ordersConnectionFactory
       |
       v
Orders database
~~~

Multi-database model:

~~~text
OrdersRepository                  BillingRepository
       |                                  |
       v                                  v
ordersR2dbcEntityOperations     billingR2dbcEntityOperations
       |                                  |
       v                                  v
R2dbcEntityTemplate              R2dbcEntityTemplate
       |                                  |
       v                                  v
ordersConnectionFactory          billingConnectionFactory
       |                                  |
       v                                  v
Orders database                  Billing database
~~~

Each branch has its own `ConnectionFactory` and entity operations. Binding the right branch is done in the repository scanning configuration.

## 2. Why Separate Each Repository Group?

Suppose the application has two databases:

- `orders_db` stores orders, order lines, and delivery status.
- `billing_db` stores invoices, payments, and transactions.

There may be two repositories:

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

~~~java
public interface InvoiceRepository
        extends ReactiveCrudRepository<Invoice, Long> {
}
~~~

If both groups are scanned by the same default `@EnableR2dbcRepositories`, they will be created based on the same entity operations bean. This can cause repositories to access the wrong database or use unsuitable mapping/transaction infrastructure.

The solution is to separate repository packages by database and declare each group in its own configuration, with `entityOperationsRef` pointing to the corresponding bean.

## 3. Organizing Repository Packages

An easy-to-manage structure:

~~~text
com.example.application
|
+-- orders
|   +-- entity
|   |   +-- Order.java
|   |   +-- OrderLine.java
|   +-- repository
|   |   +-- OrderRepository.java
|   |   +-- OrderLineRepository.java
|   +-- config
|       +-- OrdersR2dbcConfiguration.java
|
+-- billing
|   +-- entity
|   |   +-- Invoice.java
|   |   +-- Payment.java
|   +-- repository
|   |   +-- InvoiceRepository.java
|   |   +-- PaymentRepository.java
|   +-- config
|       +-- BillingR2dbcConfiguration.java
|
+-- shared
    +-- config
~~~

Each configuration only scans the repository package belonging to its database. You can use `basePackages` with string package names or `basePackageClasses` with a marker class.

Marker example:

~~~java
package com.example.application.orders.repository;

public interface OrdersRepositoryMarker {
}
~~~

`basePackageClasses` helps avoid package typos and continues to work when refactoring packages in an IDE.

## 4. Declaring Repository Scanning with entityOperationsRef

The `@EnableR2dbcRepositories` annotation has an `entityOperationsRef` attribute. This attribute takes the **bean name** that provides `R2dbcEntityOperations` for the scanned repositories.

For example:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackageClasses = OrdersRepositoryMarker.class,
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
public class OrdersRepositoryConfiguration {
}
~~~

Here:

- `basePackageClasses` specifies the package to scan.
- `entityOperationsRef` points to the bean named `ordersR2dbcEntityOperations`.
- All repositories discovered in this scan scope are created with the specified entity operations.

The value of `entityOperationsRef` must match the bean name exactly. It is a reference by name, not a class name and not a `ConnectionFactory` name.

If this attribute is omitted, Spring Data R2DBC uses the default entity operations name per standard configuration, usually `r2dbcEntityTemplate`. With multiple databases, declare it explicitly so repositories do not accidentally use the default template.

## 5. Configuring ConnectionFactory and R2dbcEntityOperations for the First Database

Example configuration for the orders database:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackageClasses = OrdersRepositoryMarker.class,
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
public class OrdersR2dbcConfiguration {

    @Bean("ordersConnectionFactory")
    public ConnectionFactory ordersConnectionFactory(
            OrdersDatabaseProperties properties) {
        return properties.connectionFactory();
    }

    @Bean("ordersR2dbcEntityOperations")
    public R2dbcEntityOperations ordersR2dbcEntityOperations(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

`OrdersDatabaseProperties` in the example represents the application's connection configuration. The `ConnectionFactory` can be created from URLs and credentials loaded from the environment, a secret store, or external configuration. Do not hard-code passwords in source code.

Key points:

1. The ConnectionFactory bean has a distinct name.
2. The injected parameter uses `@Qualifier` to select the right ConnectionFactory.
3. The template is created from the selected ConnectionFactory.
4. The template bean has a name matching `entityOperationsRef`.

`R2dbcEntityTemplate` implements `R2dbcEntityOperations`, so the bean return type can be declared as the interface or the implementation. Using the interface clearly expresses the contract the repository infrastructure requires.

## 6. Configuring the Second Database

Billing has a similar configuration but uses a different package, connection factory, and entity operations:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackageClasses = BillingRepositoryMarker.class,
    entityOperationsRef = "billingR2dbcEntityOperations"
)
public class BillingR2dbcConfiguration {

    @Bean("billingConnectionFactory")
    public ConnectionFactory billingConnectionFactory(
            BillingDatabaseProperties properties) {
        return properties.connectionFactory();
    }

    @Bean("billingR2dbcEntityOperations")
    public R2dbcEntityOperations billingR2dbcEntityOperations(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {

        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

Repositories in the billing package are bound to the billing template:

~~~java
public interface InvoiceRepository
        extends ReactiveCrudRepository<Invoice, Long> {
}
~~~

There is no need to add `@Qualifier` on each repository interface. Binding is determined by the scan scope of `@EnableR2dbcRepositories` and `entityOperationsRef`.

## 7. Configuring Two Groups in One Class or Two Classes?

Multiple repository groups can be declared in separate configuration classes. This approach is usually easier to read and maintain:

- Each class represents one database boundary.
- ConnectionFactory and template have clear names.
- Package scanning is scoped separately.
- The corresponding transaction manager can be declared in the same configuration.

Beans can also be placed in a shared configuration class, provided each `@EnableR2dbcRepositories` still specifies the right package and `entityOperationsRef`. What matters is that the two scan scopes do not overlap or accidentally share the same operations bean.

Do not place multiple identical scan annotations on the same package just "to be sure." A single repository interface must not be registered by two different repository configurations.

## 8. Using basePackages and basePackageClasses Properly

Two common ways to declare:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application.orders.repository",
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
~~~

Or:

~~~java
@EnableR2dbcRepositories(
    basePackageClasses = OrdersRepositoryMarker.class,
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
~~~

`basePackages` is convenient when packages are configured as strings. `basePackageClasses` is safer during refactoring because the compiler can verify the referenced class.

If both attributes are omitted, Spring scans the package of the configuration class and its subpackages according to the annotation's component/repository scanning rules. In a multi-database application, do not rely on the default scope if it might include repositories from another database.

Example of bad configuration:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.application",
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
public class OrdersR2dbcConfiguration {
}
~~~

If package `com.example.application` contains both orders and billing repositories, both groups may be registered with orders' operations. Narrow the scan to the orders package.

## 9. Why Does @Primary Not Replace entityOperationsRef?

When Spring sees multiple beans of the same type, `@Primary` helps pick a default bean for injections without a qualifier.

For example:

~~~java
@Bean
@Primary
ConnectionFactory ordersConnectionFactory() {
    // ...
}
~~~

This is useful when some auto-configuration or component needs a default ConnectionFactory. However, `@Primary` cannot express that:

- OrderRepository uses the orders database.
- InvoiceRepository uses the billing database.

That must be configured in the repository infrastructure using `entityOperationsRef`.

Similarly, if you declare multiple `R2dbcEntityOperations` beans without specifying `entityOperationsRef`, default bean selection may depend on configuration and create unclear bindings. With multiple databases, always reference explicitly.

Practical rules:

- Use `@Primary` only to resolve a genuinely needed default dependency.
- Use `@Qualifier` to inject a specific ConnectionFactory or DatabaseClient.
- Use `entityOperationsRef` to bind a repository group to a specific template.

## 10. Configuring a Dedicated DatabaseClient for Each Database

If custom SQL is needed in addition to repositories, create a DatabaseClient for each ConnectionFactory:

~~~java
@Bean("ordersDatabaseClient")
public DatabaseClient ordersDatabaseClient(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {

    return DatabaseClient.create(connectionFactory);
}

@Bean("billingDatabaseClient")
public DatabaseClient billingDatabaseClient(
        @Qualifier("billingConnectionFactory")
        ConnectionFactory connectionFactory) {

    return DatabaseClient.create(connectionFactory);
}
~~~

Inject with a qualifier:

~~~java
public OrdersReadService(
        @Qualifier("ordersDatabaseClient")
        DatabaseClient databaseClient) {
    this.databaseClient = databaseClient;
}
~~~

Do not inject a `DatabaseClient` without a qualifier when multiple beans of the same type exist. Spring may throw `NoUniqueBeanDefinitionException` or select the primary bean unintentionally.

A `DatabaseClient` created directly from a ConnectionFactory does not automatically become repository entity operations. It is an SQL execution abstraction. If you want repositories to use a database, you still must configure `R2dbcEntityOperations` and `entityOperationsRef`.

## 11. Binding the Transaction Manager to the Right Database

Each ConnectionFactory usually needs its own `R2dbcTransactionManager`:

~~~java
@Bean("ordersTransactionManager")
public ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {

    return new R2dbcTransactionManager(connectionFactory);
}

@Bean("billingTransactionManager")
public ReactiveTransactionManager billingTransactionManager(
        @Qualifier("billingConnectionFactory")
        ConnectionFactory connectionFactory) {

    return new R2dbcTransactionManager(connectionFactory);
}
~~~

When a service operates on orders:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order);
}
~~~

When a service operates on billing:

~~~java
@Transactional(transactionManager = "billingTransactionManager")
public Mono<Invoice> createInvoice(Invoice invoice) {
    return invoiceRepository.save(invoice);
}
~~~

The transaction manager must manage the same ConnectionFactory that the repository uses. If the wrong manager is used, the repository may not participate in the transaction the service expects.

If there is only one transaction manager or you want to pick a default manager, `@Primary` can be used on the default manager bean. However, when a service needs a specific database, explicitly specify `transactionManager` in `@Transactional`.

## 12. Using TransactionalOperator Per Database

For programmatic transactions, create one operator per manager:

~~~java
@Bean("ordersTransactionalOperator")
public TransactionalOperator ordersTransactionalOperator(
        @Qualifier("ordersTransactionManager")
        ReactiveTransactionManager transactionManager) {

    return TransactionalOperator.create(transactionManager);
}

@Bean("billingTransactionalOperator")
public TransactionalOperator billingTransactionalOperator(
        @Qualifier("billingTransactionManager")
        ReactiveTransactionManager transactionManager) {

    return TransactionalOperator.create(transactionManager);
}
~~~

Inject the right operator:

~~~java
public OrdersService(
        OrderRepository orderRepository,
        @Qualifier("ordersTransactionalOperator")
        TransactionalOperator transactionalOperator) {
    this.orderRepository = orderRepository;
    this.transactionalOperator = transactionalOperator;
}
~~~

Then:

~~~java
return transactionalOperator.transactional(
    orderRepository.save(order)
);
~~~

Do not use a TransactionalOperator created from the billing manager to wrap an orders operation and expect it to automatically pick the right ConnectionFactory. An operator is bound to a specific transaction manager.

## 13. Multiple Databases Do Not Default to a Distributed Transaction

A method can call both the orders repository and the billing repository, but two independent transaction managers do not automatically form an atomic transaction across two databases.

For example:

~~~java
public Mono<Void> createOrderAndInvoice(
        Order order,
        Invoice invoice) {

    return orderRepository.save(order)
        .flatMap(savedOrder ->
            invoiceRepository.save(invoice)
                .thenReturn(savedOrder)
        )
        .then();
}
~~~

If this method only uses a single `@Transactional` with the orders manager:

- The orders operation can participate in the orders transaction.
- The billing operation uses a different ConnectionFactory so it does not automatically join the orders transaction.
- If billing succeeds and orders rolls back, or vice versa depending on execution order, the two databases can become out of sync.

If cross-database coordination is truly required, choose an appropriate architecture:

- Saga with steps and compensating actions.
- Outbox/inbox for reliable event propagation.
- Retry and reconciliation workflows.
- A distributed transaction coordinator if the entire technology stack and drivers support that solution.

Do not assume a single R2dbcTransactionManager provides atomic commit across multiple ConnectionFactory beans.

## 14. Entity Mapping and Converters Per Database

Each `R2dbcEntityTemplate` has mapping infrastructure and a dialect corresponding to the database that its ConnectionFactory represents. This matters when databases differ in:

- Data types.
- Identifier and quoting rules.
- ID generation strategies.
- SQL dialects.
- Timestamp and UUID types.
- Custom conversions.

If two databases use the same entity class but have different schemas or column types, determine which mapping applies to each template. Do not assume all converters or naming rules are automatically identical.

When separate custom conversions are needed, configure mapping/conversions explicitly for each template according to the API of the Spring Data version in use. Avoid sharing a converter with database-specific assumptions across all databases.

### Shared Entities or Separate Entities?

If two databases store the same model with the same column semantics, you can share the entity class. If schemas, lifecycles, or semantics differ, separate entities usually prevent confusion:

~~~text
orders_db.OrderRecord
billing_db.InvoiceRecord
~~~

Do not use the same repository interface to access two different databases. Create separate repositories and bind each group to its corresponding operations bean.

## 15. Multi-Database Configuration in Spring Boot

Spring Boot can usually auto-configure R2DBC infrastructure when there is one default connection configuration. When an application has multiple ConnectionFactory beans, declare separate beans and avoid ambiguous injection.

External configuration can be separated by namespace:

~~~yaml
app:
  r2dbc:
    orders:
      url: r2dbc:postgresql://orders-host:5432/orders_db
      username: orders_user
      password: ${ORDERS_DB_PASSWORD}
    billing:
      url: r2dbc:postgresql://billing-host:5432/billing_db
      username: billing_user
      password: ${BILLING_DB_PASSWORD}
~~~

This is an example property structure; the application must create the corresponding `ConnectionFactory` from these properties using a builder or `ConnectionFactoryOptions`. Property names are not automatically recognized by Spring Boot as two databases simply because they sit under `app.r2dbc`.

If you keep `spring.r2dbc.*` for the default database and create the second database under a custom namespace, make it explicit which beans are default and which beans are used by each repository configuration.

Do not put real credentials in committed configuration files. Use environment variables, a secret manager, or the deployment environment's secret management mechanism.

## 16. Separate Connection Pools and Resources Per Database

Each ConnectionFactory can use its own pool. This helps limit the number of connections to each database:

~~~text
Orders pool                    Billing pool
  max 20                         max 10
    |                              |
    v                              v
ordersConnectionFactory       billingConnectionFactory
    |                              |
    v                              v
ordersR2dbcEntityOperations   billingR2dbcEntityOperations
~~~

Pool limits should be based on each database's connection limit, number of application instances, load level, and connection hold time. Do not set the total maximum connections across all instances higher than the database limit.

A slow database does not necessarily exhaust the pool of the other database if they use separate pools. However, application requests may still depend on both databases and must handle timeouts/failures appropriately.

## 17. Avoiding Overlapping Repository Scans

Suppose you have:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application",
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
class OrdersConfiguration {
}
~~~

and:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application.billing.repository",
    entityOperationsRef = "billingR2dbcEntityOperations"
)
class BillingConfiguration {
}
~~~

Orders' scan package encompasses billing. A billing repository may be detected by both configurations or registered unexpectedly. Restrict the packages:

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application.orders.repository",
    entityOperationsRef = "ordersR2dbcEntityOperations"
)
~~~

~~~java
@EnableR2dbcRepositories(
    basePackages = "com.example.application.billing.repository",
    entityOperationsRef = "billingR2dbcEntityOperations"
)
~~~

Each repository interface should belong to exactly one scan region.

## 18. Common Configuration Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Omitting `entityOperationsRef` when multiple templates exist | Repository may use default template or wrong bean | Reference explicitly by bean name |
| Typo in bean name in `entityOperationsRef` | Entity operations bean not found | Match the exact bean name |
| Template created from wrong ConnectionFactory | Repository accesses wrong database | Use `@Qualifier` when creating template |
| Two configurations scan the same package | Duplicate repository registration or wrong binding | Separate scan packages |
| Scanning the entire root package | Repositories of another database get pulled in | Use basePackageClasses or specific packages |
| Using only `@Primary` to route repositories | Does not bind each group to its own database | Use `entityOperationsRef` |
| Injecting DatabaseClient without qualifier | `NoUniqueBeanDefinitionException` or wrong primary bean selected | Use `@Qualifier` |
| Repository uses right template but wrong transaction manager | Operations do not join intended transaction | Choose manager using the same ConnectionFactory |
| Using one TransactionalOperator for all databases | Transactions opened on wrong manager | Create separate operators per manager |
| Thinking two transaction managers create a distributed transaction | Partial commit possible | Saga/outbox or suitable coordinator |
| Same entity with different schemas without checking mapping | Wrong column or wrong conversion | Separate mapping/converters or separate entities |
| Hard-coding credentials in source | Connection info leaked | Use secrets outside source |
| Pool sizes set too large for all databases | Database connection exhaustion | Sum pools across instances and DB limits |

## 19. Testing That Repositories Are Bound to the Right Database

You should have integration tests for each repository group and verify the actual target database.

One way to test:

1. Initialize two distinguishable databases or schemas.
2. Create a customer table or record with the same name but different data in each database.
3. Call a repository in the orders package.
4. Verify data is read/written in the orders database.
5. Call a repository in the billing package.
6. Verify data is read/written in the billing database.
7. Check that repositories do not accidentally write to the other database.
8. Check that the corresponding transaction manager rolls back the right database.
9. Check that DatabaseClient with a qualifier also accesses the right ConnectionFactory.

You can use Testcontainers to spin up real databases for the corresponding drivers. Tests that only mock repositories do not prove `entityOperationsRef` is bound to the right ConnectionFactory.

### Checks at Application Startup

When the context starts, you can verify the beans:

- `ordersConnectionFactory`.
- `billingConnectionFactory`.
- `ordersR2dbcEntityOperations`.
- `billingR2dbcEntityOperations`.
- `ordersTransactionManager`.
- `billingTransactionManager`.

If there are duplicate bean names or wrong references, the application usually fails on startup or when repository factories are created. Keep bean names consistent and avoid depending on unclear default beans.

## 20. Step-by-Step Setup for Each Repository Group

When adding a new database, follow this sequence:

1. Create separate packages for the database's entities and repositories.
2. Create a uniquely named `ConnectionFactory`.
3. Create `R2dbcEntityOperations`/`R2dbcEntityTemplate` from that ConnectionFactory.
4. Create an `@EnableR2dbcRepositories` configuration with its own package scan.
5. Set `entityOperationsRef` to the exact template bean name.
6. Create a transaction manager using the same ConnectionFactory.
7. If needed, create a dedicated `TransactionalOperator` for that transaction manager.
8. Create a dedicated DatabaseClient if custom SQL is needed and inject it with a qualifier.
9. Determine mapping/converters/dialect appropriate for the database.
10. Configure pool, credentials, and migrations separately.
11. Verify package scans do not overlap.
12. Write integration tests proving repositories access the right database.

Each repository group needs a clear configuration path from package scan to entity operations, and then to ConnectionFactory. When this path is transparent, adding a new database does not silently change where existing repositories store data.

## 21. Key Takeaways

- `R2dbcEntityOperations` is the abstraction for entity operations; `R2dbcEntityTemplate` is the commonly used implementation.
- Each template must be created from the right ConnectionFactory.
- `@EnableR2dbcRepositories(entityOperationsRef = "...")` binds a repository group to an entity operations bean by name.
- Separate repository packages by database and ensure scan scopes do not overlap.
- Use `basePackageClasses` or `basePackages` to clearly define repository groups.
- `@Primary` only resolves default bean selection when injection is ambiguous; it does not replace entityOperationsRef.
- Use `@Qualifier` when injecting specific ConnectionFactory, DatabaseClient, and transaction manager beans.
- Each database usually needs its own transaction manager and TransactionalOperator using the same ConnectionFactory as its repositories.
- One R2DBC transaction manager does not automatically create an atomic transaction across multiple ConnectionFactory beans.
- Mapping, dialect, converters, schema, and connection pool must match each database.
- Do not hard-code credentials and do not let one repository be scanned by multiple configurations.
- Test with real databases/drivers to prove each repository group reads and writes the right database.
