# Choosing the Right Transaction Manager for Each Data Source

In a Spring application with multiple data sources, each source typically has its own ConnectionFactory or DataSource. The transaction manager must manage the exact resource that an operation is using. With Spring Data R2DBC, the transaction manager is usually **R2dbcTransactionManager**, which implements **ReactiveTransactionManager** and is bound to a specific ConnectionFactory.

If an application has multiple R2DBC databases, each database must clearly configure its corresponding ConnectionFactory, template/repositories, and transaction manager. When using @Transactional, specify the right transaction manager bean for the method. One R2dbcTransactionManager only manages transactions on the ConnectionFactory it is configured with; it does not automatically cover other databases or an HTTP service.

## 1. What Is the Role of a Transaction Manager?

A transaction manager starts, commits, or rolls back a transaction. It provides a boundary so that multiple data operations execute as a single unit of work.

Spring has two primary abstractions:

- **PlatformTransactionManager**: manages transactions in the imperative model, commonly used with JDBC, JPA, or synchronous resources.
- **ReactiveTransactionManager**: manages transactions in the reactive model, integrating with Reactor Context and Publishers such as Mono/Flux.

In Spring Data R2DBC, the commonly used implementation is R2dbcTransactionManager. It manages an R2DBC ConnectionFactory and binds the transaction-participating connection into the reactive context so corresponding R2DBC operations use the same transaction.

| Data Source | Commonly Used Transaction Manager | Abstraction |
|---|---|---|
| R2DBC | R2dbcTransactionManager | ReactiveTransactionManager |
| JDBC | DataSourceTransactionManager | PlatformTransactionManager |
| JPA | JpaTransactionManager | PlatformTransactionManager |
| Multiple supported XA resources | JTA transaction manager | JTA integration |

Do not use DataSourceTransactionManager to manage R2DBC operations just because both access the same database. JDBC Connection and R2DBC Connection belong to two different APIs and resource lifecycles. Likewise, R2dbcTransactionManager does not automatically manage a DataSource's JDBC Connection.

### 1.1. A Transaction Manager Is Bound to a Specific Resource

R2dbcTransactionManager is created from a ConnectionFactory. That ConnectionFactory determines the pool, driver, and database that the transaction manager manages.

~~~java
@Bean("ordersTransactionManager")
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {

    return new R2dbcTransactionManager(connectionFactory);
}
~~~

If a transaction manager is created from ordersConnectionFactory, it manages operations participating in transactions on that factory. It does not automatically manage another billingConnectionFactory.

## 2. Single R2DBC Data Source

With one database, Spring Boot usually auto-configures the ConnectionFactory from spring.r2dbc.* and creates the required Spring Data components. The transaction manager can be declared explicitly:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Configuration
public class OrdersTransactionConfiguration {

    @Bean
    ReactiveTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

When there is only one matching transaction manager, Spring can use that bean for @Transactional methods. Giving the bean a meaningful name is still useful for scaling to multiple data sources later.

Reactive service:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final AuditRepository auditRepository;

    public OrderService(
            OrderRepository orderRepository,
            AuditRepository auditRepository) {
        this.orderRepository = orderRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Order> create(Order order) {
        return orderRepository.save(order)
            .flatMap(saved ->
                auditRepository.recordCreated(saved.id())
                    .thenReturn(saved)
            );
    }
}
~~~

If both repositories use the same ConnectionFactory and transaction manager, operations in the reactive chain can participate in the same transaction. If auditRepository uses a different data source, the annotation does not automatically turn the transaction into a multi-database transaction.

## 3. When the Application Has Multiple R2DBC Databases

Suppose the application has two independent data sources:

- Orders database stores orders.
- Billing database stores invoices.

Each source needs its own ConnectionFactory, template/repositories, and transaction manager:

~~~text
OrdersRepository
    -> Orders R2dbcEntityTemplate
    -> ordersConnectionFactory
    -> ordersTransactionManager

BillingRepository
    -> Billing R2dbcEntityTemplate
    -> billingConnectionFactory
    -> billingTransactionManager
~~~

### 3.1. Clear Bean Naming

Example configuring two ConnectionFactory beans:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import io.r2dbc.spi.ConnectionFactories;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MultiDatabaseConfiguration {

    @Bean("ordersConnectionFactory")
    ConnectionFactory ordersConnectionFactory() {
        return ConnectionFactories.get(
            "r2dbc:postgresql://localhost:5432/orders"
        );
    }

    @Bean("billingConnectionFactory")
    ConnectionFactory billingConnectionFactory() {
        return ConnectionFactories.get(
            "r2dbc:postgresql://localhost:5432/billing"
        );
    }
}
~~~

This is an illustrative example. In real environments, credentials should come from environment variables or a secret manager; do not hard-code passwords in source code. You can use ConnectionFactoryOptions or a dedicated builder if TLS, pooling, and driver-specific options are needed.

When multiple beans of type ConnectionFactory exist, inject using @Qualifier:

~~~java
public BillingAdapter(
        @Qualifier("billingConnectionFactory")
        ConnectionFactory connectionFactory) {
    this.connectionFactory = connectionFactory;
}
~~~

If injected by type alone without @Qualifier or a @Primary bean, Spring may fail to resolve a unique bean and throw NoUniqueBeanDefinitionException.

### 3.2. Creating a Transaction Manager for Each ConnectionFactory

~~~java
@Configuration
public class MultiTransactionConfiguration {

    @Bean("ordersTransactionManager")
    ReactiveTransactionManager ordersTransactionManager(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("billingTransactionManager")
    ReactiveTransactionManager billingTransactionManager(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

Bean names clearly reflect which database each transaction manager manages. When a method needs a transaction on Orders, specify ordersTransactionManager. When a method needs a transaction on Billing, specify billingTransactionManager.

### 3.3. Configuring Templates and Repositories for the Right Source

Each R2dbcEntityTemplate must use the ConnectionFactory of its corresponding database:

~~~java
@Configuration
public class EntityTemplateConfiguration {

    @Bean("ordersR2dbcEntityTemplate")
    R2dbcEntityTemplate ordersTemplate(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }

    @Bean("billingR2dbcEntityTemplate")
    R2dbcEntityTemplate billingTemplate(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return new R2dbcEntityTemplate(connectionFactory);
    }
}
~~~

With multiple repository packages, specify entityOperationsRef so each repository group uses its own template:

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.orders.repository",
    entityOperationsRef = "ordersR2dbcEntityTemplate"
)
class OrdersRepositoriesConfiguration {
}
~~~

~~~java
@Configuration
@EnableR2dbcRepositories(
    basePackages = "com.example.billing.repository",
    entityOperationsRef = "billingR2dbcEntityTemplate"
)
class BillingRepositoriesConfiguration {
}
~~~

Packages and bean names in the example must be adapted to your project structure. Do not let two repository configurations scan the same package if they are intended to bind to two different templates.

Spring Boot auto-configuration for R2DBC typically targets a single default ConnectionFactory. When an application declares multiple factories, explicitly configure the corresponding beans and repositories; exact auto-configuration behavior depends on the Spring Boot version.

## 4. Selecting the Transaction Manager with @Transactional

When multiple transaction managers exist, do not let a method rely on a default choice if it must access a specific database. Use the transactionManager attribute of @Transactional to specify the bean explicitly.

Orders write method:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Mono<Order> create(Order order) {
        return orderRepository.save(order);
    }
}
~~~

Billing write method:

~~~java
@Service
public class BillingService {

    private final InvoiceRepository invoiceRepository;

    public BillingService(InvoiceRepository invoiceRepository) {
        this.invoiceRepository = invoiceRepository;
    }

    @Transactional(transactionManager = "billingTransactionManager")
    public Mono<Invoice> createInvoice(Invoice invoice) {
        return invoiceRepository.save(invoice);
    }
}
~~~

Common ways to write this:

~~~java
@Transactional("ordersTransactionManager")
public Mono<Order> create(Order order) {
    return orderRepository.save(order);
}
~~~

or:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> create(Order order) {
    return orderRepository.save(order);
}
~~~

The value attribute is an alias for transactionManager on the annotation. Use the configured bean name or qualifier so Spring finds the right manager.

### 4.1. @Primary and Default Transaction Manager

You can mark one transaction manager as @Primary so Spring selects it when no explicit qualifier is given:

~~~java
@Bean("ordersTransactionManager")
@Primary
ReactiveTransactionManager ordersTransactionManager(
        @Qualifier("ordersConnectionFactory")
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
~~~

@Primary is useful when one database is the default source for most of the application. However, it does not replace explicitly specifying the manager on methods that use other databases.

If multiple managers exist and there is no suitable default bean, a @Transactional without an explicit manager can cause a bean resolution error. Do not rely on bean declaration order to select a transaction manager.

## 5. Reactive Transactions vs. Imperative Transactions

A common source of confusion is that @Transactional applies to both imperative and reactive methods, but the transaction management mechanisms differ.

### 5.1. ReactiveTransactionManager for Mono/Flux

With Spring Data R2DBC, methods should return a Publisher such as Mono or Flux:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> placeOrder(Order order) {
    return orderRepository.save(order);
}
~~~

Reactive transactions use Reactor Context to propagate transaction resources across the publisher chain. They do not rely on ThreadLocal like traditional imperative transaction management.

Keep operations within the same reactive chain:

~~~java
return orderRepository.save(order)
    .flatMap(saved ->
        orderLineRepository.saveAll(saved.lines())
            .thenReturn(saved)
    );
~~~

Do not call subscribe() inside a transactional method to launch a detached publisher. Do not call block() to retrieve intermediate results synchronously. Both actions can cause operations to run outside the transaction context or end the transaction before the actual work completes.

### 5.2. PlatformTransactionManager for JDBC/JPA

With JDBC or JPA, methods usually make synchronous calls and transactions are managed via PlatformTransactionManager:

~~~java
@Transactional(transactionManager = "jdbcTransactionManager")
public void updateLegacyRecord(LegacyRecord record) {
    jdbcRepository.save(record);
}
~~~

Do not use ReactiveTransactionManager as a replacement for JDBC's transaction manager just because the service has some methods returning Mono. Each resource needs its matching manager.

### 5.3. Do Not Mix Both Models Expecting a Shared Transaction

The following example does not automatically create a single atomic transaction across both database APIs:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Result> updateBoth(Order order, LegacyRecord record) {
    return orderRepository.save(order)
        .map(saved -> {
            jdbcRepository.save(record);
            return toResult(saved);
        });
}
~~~

The JDBC call is blocking and uses a different resource. It does not automatically join ordersTransactionManager's reactive transaction. Moreover, performing a blocking JDBC call inside a reactive pipeline can block the event-loop thread.

If you must integrate legacy JDBC, clearly separate transaction boundaries, run blocking work on an appropriate scheduler, and design cross-source consistency explicitly. Do not treat a single @Transactional annotation as a distributed transaction solution.

## 6. Using TransactionalOperator for Each Data Source

In addition to @Transactional, Spring provides TransactionalOperator to control reactive transactions programmatically.

Each operator must be created from its corresponding transaction manager:

~~~java
@Configuration
public class TransactionOperatorConfiguration {

    @Bean("ordersTransactionalOperator")
    TransactionalOperator ordersOperator(
            @Qualifier("ordersTransactionManager")
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }

    @Bean("billingTransactionalOperator")
    TransactionalOperator billingOperator(
            @Qualifier("billingTransactionManager")
            ReactiveTransactionManager transactionManager) {
        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Using the operator for Orders:

~~~java
public Mono<Order> create(Order order) {
    Mono<Order> work = orderRepository.save(order);
    return ordersTransactionalOperator.transactional(work);
}
~~~

Using the operator for Billing:

~~~java
public Mono<Invoice> createInvoice(Invoice invoice) {
    Mono<Invoice> work = billingRepository.save(invoice);
    return billingTransactionalOperator.transactional(work);
}
~~~

TransactionalOperator is useful when the transaction boundary needs to wrap a specific publisher or when controlling transactions per processing branch. However, it still only manages resources belonging to the transaction manager passed to it.

## 7. Does One Method Calling Two Databases Create a Shared Transaction?

Suppose a business operation creates an Order in the Orders database and then creates an Invoice in the Billing database:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> placeOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            invoiceRepository.createFor(saved)
                .thenReturn(saved)
        );
}
~~~

If invoiceRepository uses billingConnectionFactory, the Orders transaction manager does not manage the Billing transaction. The Billing statement can execute and commit independently. If Billing succeeds and a subsequent Orders operation rolls back, the two databases can end up out of sync.

An R2DBC transaction manager bound to one ConnectionFactory does not automatically cover another ConnectionFactory. Even if both databases reside on the same server or use the same database engine, two connections/pools do not automatically form one transaction.

### 7.1. When Can the Same Transaction Be Used?

If multiple tables/schemas are accessed through the same ConnectionFactory and the same transaction context, operations can participate in that same database transaction. For example, two schemas within the same database session can be accessed in one transaction if the database supports it and permissions allow.

However, if each schema is configured with a separate ConnectionFactory/pool, they are independent connection resources. Do not assume they share a transaction simply because they are on the same host.

### 7.2. Distributed Transactions Do Not Appear Automatically

For an atomic transaction to span multiple independent resources, a real distributed transaction mechanism is required, such as XA/JTA with compatible resources and drivers. Support depends on the platform and driver; do not assume every R2DBC driver supports XA or can be enlisted into a JTA transaction manager.

In reactive multi-service architectures, local transactions combined with Outbox, Saga, and compensation are much more common than attempting a single transaction across multiple systems.

## 8. Using Outbox When Emitting Events to Another Source

If the Orders database needs to notify Billing or Inventory, you can write an outbox event in the same transaction as the Order:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> create(Order order) {
    return orderRepository.save(order)
        .flatMap(saved -> {
            OutboxMessage event =
                OutboxMessage.orderCreated(saved.id());

            return outboxRepository.save(event)
                .thenReturn(saved);
        });
}
~~~

The Order and outbox row commit or roll back together in the Orders database. A relay reads the outbox after commit and publishes the message. The consumer in Billing processes the message in Billing's local database transaction.

Outbox prevents sending a message before the source data commits. However, the relay may deliver duplicates if it crashes after broker acknowledgment but before marking the event as published. Consumers need idempotency or an inbox to avoid applying business effects multiple times.

## 9. Using Saga and Compensation for Multiple Local Transactions

A distributed workflow may consist of:

1. Orders database creates Order.
2. Inventory database reserves stock.
3. Billing database charges payment.
4. Shipping database creates shipment.

Each step has its own transaction manager and commits independently. If the Billing step fails after Inventory has reserved stock, the application needs a compensating action to release the reservation.

~~~mermaid
flowchart TD
    A["Orders transaction: create Order"]
    B["Inventory transaction: reserve"]
    C["Billing transaction: charge"]
    D["Shipping transaction: create shipment"]
    E["Complete"]
    X["A step fails"]
    R1["Compensation: release inventory"]
    R2["Compensation: refund if charged"]
    F["Update Order status"]

    A --> B --> C --> D --> E
    B --> X
    C --> X
    D --> X
    X --> R1 --> R2 --> F
~~~

A Saga does not roll back transactions already committed in other databases. It executes new business actions to offset prior effects. Each step and compensation must be idempotent, durably persisted with state, and resumable after a service restart.

## 10. Choosing Managers When Using JDBC and R2DBC Together

An application may be migrating gradually from JDBC/JPA to R2DBC. Both types of resources exist concurrently:

~~~text
JDBC repository
    -> DataSource
    -> jdbcTransactionManager (PlatformTransactionManager)

R2DBC repository
    -> ConnectionFactory
    -> r2dbcTransactionManager (ReactiveTransactionManager)
~~~

Configure beans with distinct names:

~~~java
@Bean("jdbcTransactionManager")
PlatformTransactionManager jdbcTransactionManager(
        DataSource dataSource) {
    return new DataSourceTransactionManager(dataSource);
}

@Bean("r2dbcTransactionManager")
ReactiveTransactionManager r2dbcTransactionManager(
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
~~~

JDBC service uses:

~~~java
@Transactional(transactionManager = "jdbcTransactionManager")
public void updateLegacyData() {
    jdbcRepository.updateSomething();
}
~~~

R2DBC service uses:

~~~java
@Transactional(transactionManager = "r2dbcTransactionManager")
public Mono<Void> updateReactiveData() {
    return reactiveRepository.updateSomething();
}
~~~

Do not place both operations in one method and expect them to roll back together simply because there is a @Transactional. If coordination is needed, design separate local transactions and a consistency mechanism at the business layer.

## 11. Default Manager Selection and Avoiding Bean Ambiguity Errors

When multiple beans implement ReactiveTransactionManager, Spring needs to know which bean to use.

Common approaches:

- Specify the manager name in @Transactional.
- Inject using @Qualifier when creating TransactionalOperator.
- Mark one manager @Primary if it truly is the default.
- Use separate transaction configurations per module/repository package.

If you forget a qualifier when multiple managers exist, the application may fail at startup or pick an unintended manager depending on configuration. Do not rely on class names or bean declaration order to guess.

@Primary only resolves default selection when multiple candidates exist. It does not turn the default manager into a manager spanning other sources.

## 12. Transaction Boundaries and Propagation

Transaction managers can support propagation modes such as REQUIRED, REQUIRES_NEW, and other transaction attributes depending on the implementation.

With R2dbcTransactionManager, propagation applies within the scope of the transaction resource managed by that manager. For example, REQUIRES_NEW on ordersTransactionManager creates a new transaction for the Orders resource; it does not automatically create a transaction for the Billing database.

When calling another transactional method, remember:

- Same manager and REQUIRED: usually joins the existing transaction if in the same reactive context.
- Same manager and REQUIRES_NEW: requests a new transaction per manager semantics.
- Different manager: that is a different transaction resource; it does not automatically join the current transaction.
- Self-invocation within the same object may bypass the transaction proxy in typical proxy-based configurations.

If an independent transaction is needed, move the method to another bean or use TransactionalOperator explicitly. Do not use propagation as a substitute for distributed transactions.

## 13. Testing Transaction Managers

With multiple databases, tests must prove that repositories are using the right ConnectionFactory and manager.

Cases to test:

- Orders @Transactional method rolls back when a second operation on Orders fails.
- Billing method uses billingTransactionManager and does not accidentally write to Orders.
- One manager does not inadvertently cover a repository belonging to another ConnectionFactory.
- TransactionalOperator is created from the right manager.
- Reactive chains preserve transaction context across flatMap/then.
- Errors in the publisher trigger rollback when errors cross the transaction boundary.
- Cancellation before commit is handled according to your Spring version's reactive transaction rules.
- JDBC transactions and R2DBC transactions are tested separately if the application uses both.
- Outbox events commit/roll back together with business data in the source database.
- Multi-database workflows execute compensation when a local step fails.

Use integration tests with the database/driver matching production. Embedded databases may not accurately reflect transaction behavior, locking, isolation, or data types of the real DBMS.

## 14. Common Mistakes

**Using the wrong transaction manager.** A method operating on Billing specifies ordersTransactionManager. The Billing repository does not join the selected transaction. Align repository, template, ConnectionFactory, and manager per source; use explicit manager names.

**Missing @Qualifier when multiple ConnectionFactory beans exist.** Spring cannot choose a single bean. Inject with @Qualifier or mark the default source @Primary if appropriate.

**Assuming one @Transactional covers all databases.** An R2DBC transaction manager manages one ConnectionFactory. Two independent databases need two local transactions or genuine distributed transaction infrastructure.

**Mixing blocking JDBC inside a reactive transaction.** JDBC calls do not automatically join reactive transactions and can block the event loop. Separate transaction models, run blocking work on an appropriate scheduler if needed, and design cross-source consistency explicitly.

**Calling subscribe() or block() inside a transactional method.** The publisher may run detached from the transaction context or terminate the transaction before operations finish. Return Mono/Flux and chain publishers with flatMap, then, or appropriate operators.

**Using one TransactionalOperator for every source.** An operator retains the manager passed at creation time. Using Orders' operator for Billing work targets the wrong resource. Create a separate operator per manager and inject with qualifiers.

**Assuming same host means same transaction.** Two ConnectionFactory beans or two pools can open two distinct connections even on the same host. Verify the exact transaction resource.

## 15. Design Principles

- Each ConnectionFactory needs a corresponding transaction manager when the application requires transactions on that source.
- Name beans after the data source: ordersConnectionFactory, ordersTransactionManager, billingConnectionFactory, billingTransactionManager.
- Bind repositories and R2dbcEntityTemplate to the right ConnectionFactory.
- Use @Transactional(transactionManager = "...") on methods targeting a specific data source.
- Use @Qualifier when injecting a specific manager, factory, template, or TransactionalOperator.
- Only mark @Primary on a genuine default manager.
- Use ReactiveTransactionManager for R2DBC Mono/Flux; use PlatformTransactionManager for imperative JDBC/JPA.
- Keep reactive transactions within the same Publisher chain and do not subscribe/block manually.
- Do not assume one manager spans multiple ConnectionFactory beans.
- Use Outbox/Saga/compensation when coordinating multiple local transactions.
- Check Spring Boot auto-configuration when declaring multiple data sources.
- Test rollback, manager selection, and resource boundaries against the target databases.

## 16. Key Takeaways

Choose the transaction manager according to the exact resource type and ConnectionFactory used by the repository. R2dbcTransactionManager manages a single ConnectionFactory reactively; JDBC/JPA typically use a separate PlatformTransactionManager. When there are multiple R2DBC databases, configure each factory, template/repository, and transaction manager as a clearly named group, then specify the manager via @Transactional or create the corresponding TransactionalOperator.

A @Transactional method only creates a transaction for the resource managed by the chosen manager. It does not automatically create an atomic transaction across multiple databases, JDBC, and HTTP. When business logic requires coordinating multiple independent sources, use local transactions per source and Outbox/Saga/compensation to handle state propagation and business recovery after failures.
