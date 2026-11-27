# Selecting Transactions by TransactionManager Name

When a Spring Data JPA application connects to multiple databases, each entity/repository group can belong to its own persistence unit and its own transaction manager. Spring needs to know which transaction manager governs a service method; otherwise, the application may use the wrong default transaction manager or fail with an error when multiple beans of the same type exist.

There are two places that must be configured explicitly:

- **@Transactional(transactionManager = "...")** selects the transaction manager for the transaction boundary of a service method or class.
- **@EnableJpaRepositories(transactionManagerRef = "...", entityManagerFactoryRef = "...")** binds a group of repositories to the right transaction manager and EntityManagerFactory.

Both configurations must point to the same persistence unit when a service operates on the corresponding repositories.

## 1. What is a TransactionManager?

In Spring, **TransactionManager** is the abstraction that manages transaction boundaries. For imperative JPA applications, the commonly used type is **PlatformTransactionManager**. The **JpaTransactionManager** class implements this abstraction for a single **EntityManagerFactory**.

A JPA persistence unit typically has the following component chain:

~~~text
DataSource
    |
    v
EntityManagerFactory
    |
    v
JpaTransactionManager
    |
    v
Repositories and services using that persistence unit
~~~

If an application has a single database, Spring Boot usually preconfigures a default DataSource, EntityManagerFactory, and transaction manager. With multiple databases, the application typically needs to configure each set of components separately:

| Persistence unit | DataSource | EntityManagerFactory | TransactionManager |
|---|---|---|---|
| Orders | ordersDataSource | ordersEntityManagerFactory | ordersTransactionManager |
| Billing | billingDataSource | billingEntityManagerFactory | billingTransactionManager |
| Audit | auditDataSource | auditEntityManagerFactory | auditTransactionManager |

A **JpaTransactionManager** manages transactions for one EntityManagerFactory. It does not automatically coordinate transactions across all EntityManagerFactories in the application context.

Do not create an extra EntityManagerFactory solely to rename a transaction. Each persistence unit should correspond to a distinct scope of entities, datasource, and JPA configuration that genuinely needs separate management.

## 2. Selecting a transaction manager with @Transactional

Spring provides two equivalent attributes on the **@Transactional** annotation:

- **value**: qualifier or bean name of the transaction manager.
- **transactionManager**: alias for value, often more readable in explicit configurations.

Example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    @Transactional(transactionManager = "ordersTransactionManager")
    public void createOrder() {
        // Operations belonging to the Orders database transaction
    }
}
~~~

It can be written in shorthand form:

~~~java
@Transactional("ordersTransactionManager")
public void createOrder() {
    // ...
}
~~~

Spring resolves the transaction manager by the corresponding bean name or qualifier. The passed name must match a bean registered in the application context.

Example with two different business operations:

~~~java
@Service
public class OrderService {

    @Transactional("ordersTransactionManager")
    public void createOrder() {
        // Read and write entities of the Orders database
    }
}

@Service
public class BillingService {

    @Transactional("billingTransactionManager")
    public void recordInvoice() {
        // Read and write entities of the Billing database
    }
}
~~~

When invoked through a Spring proxy, each method uses the specified transaction manager. Methods without a qualifier use the default transaction manager selected by Spring's infrastructure.

### 2.1. Bean names and qualifiers

Example bean declaration:

~~~java
@Bean(name = "ordersTransactionManager")
PlatformTransactionManager ordersTransactionManager(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {

    return new JpaTransactionManager(entityManagerFactory);
}
~~~

The bean name here is **ordersTransactionManager**. Service annotations can reference this name directly.

If a qualifier is used instead of a bean name, the qualifier value can also be used to resolve the transaction manager. When a system has multiple managers, consistent naming makes code readable and prevents choosing the wrong database.

### 2.2. Enabling transaction annotations

In a manually configured Spring Framework application, annotation-driven transaction management must be enabled with **@EnableTransactionManagement** on a configuration class:

~~~java
@Configuration
@EnableTransactionManagement
public class TransactionConfiguration {
}
~~~

Spring Boot normally auto-configures transaction management when the required infrastructure is present, so typical Boot applications do not need to add this annotation again. If using plain Spring Framework, enable it in the application context containing the services that need to be proxied.

## 3. Linking repositories to the right EntityManagerFactory and TransactionManager

Selecting the transaction manager on the service alone is not enough. Spring Data JPA also needs to know which persistence unit a repository interface belongs to.

Use **@EnableJpaRepositories** with three key attributes:

- **basePackages**: package containing the repository interfaces to register.
- **entityManagerFactoryRef**: name of the EntityManagerFactory used to create the repositories.
- **transactionManagerRef**: name of the default transaction manager for those repositories.

Example configuration for Orders:

~~~java
import javax.sql.DataSource;
import jakarta.persistence.EntityManagerFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;
import org.springframework.orm.jpa.JpaTransactionManager;
import org.springframework.orm.jpa.LocalContainerEntityManagerFactoryBean;
import org.springframework.transaction.PlatformTransactionManager;

// Import EntityManagerFactoryBuilder from the package matching
// your project's Spring Boot major version.
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfiguration {

    @Bean(name = "ordersEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("ordersDataSource") DataSource dataSource) {

        return builder
            .dataSource(dataSource)
            .packages("com.example.orders.entity")
            .persistenceUnit("orders")
            .build();
    }

    @Bean(name = "ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {

        return new JpaTransactionManager(entityManagerFactory);
    }
}
~~~

The configuration for Billing uses its own package, datasource, persistence unit, and bean names:

~~~java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.billing.repository",
    entityManagerFactoryRef = "billingEntityManagerFactory",
    transactionManagerRef = "billingTransactionManager"
)
public class BillingJpaConfiguration {

    @Bean(name = "billingEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean billingEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("billingDataSource") DataSource dataSource) {

        return builder
            .dataSource(dataSource)
            .packages("com.example.billing.entity")
            .persistenceUnit("billing")
            .build();
    }

    @Bean(name = "billingTransactionManager")
    PlatformTransactionManager billingTransactionManager(
            @Qualifier("billingEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {

        return new JpaTransactionManager(entityManagerFactory);
    }
}
~~~

The **ordersDataSource** and **billingDataSource** beans must be declared and configured separately. Each DataSource points to the intended database/schema. The example above focuses on JPA wiring; it assumes the application already provides both DataSources and Spring Boot provides EntityManagerFactoryBuilder.

In Spring Boot 3, EntityManagerFactoryBuilder typically lives in the **org.springframework.boot.orm.jpa** package. In newer major versions, check the API package for the version in use. Using the Boot-provided builder preserves the JPA/vendor customizations configured by Boot. If creating an EntityManagerFactory completely manually, you must supply provider properties, dialect, naming strategy, packages, and all necessary settings yourself.

### 3.1. Why configure both refs?

The two attributes solve two distinct responsibilities:

| Attribute | Question Answered |
|---|---|
| entityManagerFactoryRef | Which persistence context and entity mappings does the repository use? |
| transactionManagerRef | Which transaction manager does the repository use when starting its own transaction? |

If **entityManagerFactoryRef** is omitted, Spring Data JPA typically looks for a bean named **entityManagerFactory**. If **transactionManagerRef** is omitted, the repository infrastructure typically uses the default manager named **transactionManager** or a single matching manager in the application context.

These defaults are convenient for single-database applications. In multi-persistence-unit configurations, declare both refs explicitly to prevent repositories from inadvertently attaching to the default component set.

### 3.2. Separating repository and entity packages

An easy-to-manage package structure:

~~~text
com.example
  orders
    entity
    repository
    service
  billing
    entity
    repository
    service
  config
    OrdersJpaConfiguration
    BillingJpaConfiguration
~~~

Each **@EnableJpaRepositories** should scan only its own repository package. Do not let two configurations scan the same repository interface, because a repository may be registered twice or bound to the wrong EntityManagerFactory.

Similarly, each EntityManagerFactory should scan only the entities belonging to its corresponding persistence unit. Do not include Orders database entities in the Billing persistence unit just because both entity groups share a broad parent package.

## 4. Using the right manager at the service boundary

Once repositories are linked, services must also select the matching transaction manager:

~~~java
@Service
public class OrderApplicationService {

    private final OrderRepository orders;

    public OrderApplicationService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Long placeOrder(Order order) {
        Order saved = orders.save(order);
        return saved.getId();
    }
}
~~~

Here:

1. The Spring proxy intercepts the placeOrder call.
2. The transaction interceptor selects ordersTransactionManager.
3. JpaTransactionManager opens or joins a transaction on ordersEntityManagerFactory.
4. OrderRepository uses the EntityManagerFactory wired in OrdersJpaConfiguration.
5. When the method finishes, the transaction manager commits if no rollback error occurs.

If a service uses **billingTransactionManager** while the repository is configured with **ordersTransactionManager**, the two components are referring to two different transaction contexts. The repository may open its own transaction under its configured manager; the service's transaction does not automatically cover that operation.

Therefore, keep the three names aligned: repository package, EntityManagerFactory, and transaction manager.

## 5. Default transactions when multiple managers exist

When no manager is specified on **@Transactional**, Spring needs to select a default manager.

In simple setups, a bean named **transactionManager** is typically the default name searched. You can explicitly configure the default manager via **TransactionManagementConfigurer** if the application has multiple managers and you want to designate one manager for unqualified annotations.

**@Primary** is useful when Spring needs to pick a preferred bean at injection points by type. However, @Primary does not replace binding repository packages to the right EntityManagerFactory and transaction manager via the ref attributes.

Example of an injection point requiring a specific manager:

~~~java
@Service
public class OrderMaintenanceService {

    private final PlatformTransactionManager transactionManager;

    public OrderMaintenanceService(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager transactionManager) {
        this.transactionManager = transactionManager;
    }
}
~~~

Do not confuse **@Qualifier** in constructor injection with **transactionManager** in @Transactional:

- @Qualifier selects which bean is injected into a field or constructor parameter.
- @Transactional(transactionManager = "...") selects which manager controls the method's transaction.

They can use the same name, but they apply to two different mechanisms.

## 6. Propagation with multiple transaction managers

By default, **@Transactional** uses **Propagation.REQUIRED**. If a transaction already exists for the selected manager, the method joins that transaction; if none exists, the manager opens a new transaction.

When two methods use two different transaction managers, they do not automatically share a single transaction just because they are called within the same call stack.

Example:

~~~java
@Service
public class CheckoutService {

    private final OrderRepository orders;
    private final BillingService billing;

    public CheckoutService(
            OrderRepository orders,
            BillingService billing) {
        this.orders = orders;
        this.billing = billing;
    }

    @Transactional("ordersTransactionManager")
    public void checkout(Order order) {
        orders.save(order);
        billing.createInvoice(order);
    }
}

@Service
public class BillingService {

    private final InvoiceRepository invoices;

    public BillingService(InvoiceRepository invoices) {
        this.invoices = invoices;
    }

    @Transactional("billingTransactionManager")
    public void createInvoice(Order order) {
        invoices.save(Invoice.from(order));
    }
}
~~~

In this flow:

1. checkout opens an Orders transaction.
2. createInvoice is invoked through the BillingService proxy.
3. BillingService selects the Billing transaction manager and opens a separate Billing transaction if none exists yet for that manager.
4. The Billing transaction may commit when createInvoice finishes.
5. Afterward, the Orders transaction continues and commits when checkout completes.

If a subsequent step causes the Orders transaction to roll back, the invoice already committed in Billing does not automatically roll back with it. These are two independent transactions.

### 6.1. REQUIRED and REQUIRES_NEW do not create distributed transactions

**REQUIRED** only joins a transaction managed by the corresponding manager. When a different manager is selected, it does not automatically turn two local transactions into one atomic transaction.

**REQUIRES_NEW** instructs the selected manager to open a new transaction and suspend any existing transaction managed by that same manager. It does not turn two databases into a single commit/rollback unit.

If you need to guarantee that two databases commit together or roll back together, an appropriate coordination mechanism is required:

- **JTA/XA** can coordinate distributed transactions when resources, drivers, and the transaction manager support XA. An appropriate transaction coordinator must be configured and operated.
- **Saga** splits the business process into local transaction steps, with compensating actions if a subsequent step fails.
- **Transactional outbox** writes events into the same database/transaction as the business data, and a background process then emits events for other systems to handle.

Do not assume two @Transactional annotations referencing two managers will provide cross-database atomic commits.

## 7. Using TransactionTemplate when choosing a manager programmatically

In addition to annotations, Spring allows creating a **TransactionTemplate** with an explicitly injected manager. This approach is helpful when transaction boundaries depend on execution branches or when explicit programmatic orchestration is needed.

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class OrderImportService {

    private final TransactionTemplate ordersTransaction;

    public OrderImportService(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager transactionManager) {
        this.ordersTransaction = new TransactionTemplate(transactionManager);
    }

    public void importOrder(Order order) {
        ordersTransaction.executeWithoutResult(status -> {
            // Operations against the Orders database within this transaction
        });
    }
}
~~~

You can create another TransactionTemplate from **billingTransactionManager** if you need to run a separate Billing transaction. Remember that each template only controls transactions for the manager passed into it.

For typical business logic, **@Transactional** at the service boundary is usually easier to read and test. Use TransactionTemplate when programmatic transaction control is required or when multiple sequential transactions are needed inside the same method.

## 8. Testing that the right transaction manager is selected

Multi-database tests must verify that repositories and services actually use the right manager.

### 8.1. Testing per persistence unit

You can annotate a test with:

~~~java
@SpringBootTest
@Transactional("ordersTransactionManager")
class OrderRepositoryIntegrationTest {

    @Autowired
    private OrderRepository orders;

    @Test
    void savesOrderInOrdersDatabase() {
        // Save and read back Order in the Orders persistence unit
    }
}
~~~

When the test finishes, the Orders transaction is rolled back according to the test transaction semantics unless a commit is requested. This test does not automatically roll back transactions on the Billing manager.

### 8.2. Using TransactionTemplate to verify isolated rollback

A test can invoke TransactionTemplate with a specific manager and throw an exception to verify that data in that database is rolled back:

~~~java
TransactionTemplate tx = new TransactionTemplate(ordersTransactionManager);

assertThrows(RuntimeException.class, () ->
    tx.executeWithoutResult(status -> {
        orders.save(order);
        throw new RuntimeException("force rollback");
    })
);
~~~

Then read back in a new transaction to confirm the record was not committed. Avoid reading back using the old persistence context because the first-level cache may hold the entity state in memory.

### 8.3. Testing multiple databases

Have separate tests for each persistence unit:

- Verify Orders repositories write to the Orders database.
- Verify Billing repositories write to the Billing database.
- Verify each service selects the right manager.
- Verify rolling back one manager is not mistaken for rolling back another manager.
- Verify migrations/schemas and entity scanning separately for each database.
- Verify the scenario where one business operation invokes both managers and explicitly confirm behavior when one step fails.

Testcontainers can be used to run production-compatible databases. Test data should use distinct business keys and proper cleanup for each database.

## 9. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| No qualifying bean of type PlatformTransactionManager | Multiple managers exist or no suitable default manager exists | Specify the name via @Transactional or configure a default manager |
| Transaction manager not found by name | Name in annotation does not match bean name/qualifier | Check bean names and qualifiers |
| Repository uses wrong database | Missing or incorrect entityManagerFactoryRef | Bind repository package to the right EntityManagerFactory |
| Repository opens a different transaction than the service | transactionManagerRef differs from the manager chosen by the service | Align both refs and qualifiers |
| Entity not found | EntityManagerFactory scans the wrong package | Fix packages(...) or packagesToScan |
| Repository registered twice | Two @EnableJpaRepositories scan overlapping packages | Separate basePackages clearly |
| Rolling back one database leaves data in the other | Two independent local transactions | Use JTA/XA or design an outbox/saga |
| @Transactional has no effect | Self-invocation or non-proxied object call | Place boundary on a Spring bean and call through proxy |
| @Primary does not solve repository mapping | @Primary only helps resolve preferred bean by type | Configure entityManagerFactoryRef and transactionManagerRef |
| Test rollback does not clean up the other database | Test only runs a transaction on one manager | Explicitly specify managers per test and perform cleanup |
| Spring Boot loses JPA config after manual EMF creation | Custom EMF omits auto-configured properties | Use EntityManagerFactoryBuilder and bind appropriate JPA properties |

## 10. Checklist for configuring multiple TransactionManagers

- [ ] Each persistence unit has an appropriate DataSource.
- [ ] Each entity group has the right EntityManagerFactory.
- [ ] Each EntityManagerFactory has a corresponding JpaTransactionManager.
- [ ] Transaction manager bean names are clear and consistent.
- [ ] Each repository group has separate basePackages.
- [ ] entityManagerFactoryRef points to the right EntityManagerFactory.
- [ ] transactionManagerRef points to the right transaction manager.
- [ ] Services use @Transactional with the right manager name.
- [ ] Default transaction manager is clearly defined for unqualified annotations.
- [ ] @Qualifier in dependency injection is not confused with the @Transactional attribute.
- [ ] Independent transaction behavior is understood when one method calls multiple managers.
- [ ] If cross-database atomic commit is required, JTA/XA or an appropriate saga/outbox design is chosen.
- [ ] Integration tests verify the right database, transaction, and rollback behavior.

## 11. Key takeaways

Use **@Transactional(transactionManager = "ordersTransactionManager")** to choose the transaction manager for a service method. Use **@EnableJpaRepositories(entityManagerFactoryRef = "...", transactionManagerRef = "...")** to bind a repository group to the right persistence unit.

A JPA transaction manager typically manages a single EntityManagerFactory. When a business operation uses multiple managers, local transactions are independent and do not automatically roll back or commit atomically together. Define clear transaction boundaries, use consistent bean naming, and test rollback behavior on each database.

## References

- [Spring Framework — Using @Transactional and multiple transaction managers](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Data JPA — Repository configuration and transaction-manager-ref](https://docs.spring.io/spring-data/jpa/reference/repositories/create-instances.html)
- [Spring Data JPA — EnableJpaRepositories API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/config/EnableJpaRepositories.html)
- [Spring Boot — Using multiple EntityManagerFactories](https://docs.spring.io/spring-boot/how-to/data-access.html)
