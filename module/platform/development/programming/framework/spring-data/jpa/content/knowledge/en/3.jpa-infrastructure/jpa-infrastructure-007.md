# Configuring TransactionManager and Linking to a Persistence Unit

Spring Data JPA participates properly in transactions only when Spring knows **which transaction manager controls which EntityManagerFactory**. With a single persistence unit, Spring Boot usually auto-configures this entire chain. When an application has multiple datasources or multiple persistence units, you must explicitly declare each triplet of repositories, EntityManagerFactory, and transaction manager so queries and transactions go to the right place.

This article focuses on that linkage in Spring Boot 3.x, Spring Framework 6, and Jakarta Persistence.

## 1. Distinguishing Four Components

| Component | Role | Example Name |
|---|---|---|
| DataSource | Provides connections to the database | ordersDataSource |
| Persistence unit | Group of entities, mappings, and JPA settings managed together | orders |
| EntityManagerFactory | Creates EntityManager instances for a persistence unit | ordersEntityManagerFactory |
| PlatformTransactionManager | Begins, commits, and rolls back transactions for that persistence unit | ordersTransactionManager |

**DataSource** is the database connectivity layer. It holds the details needed to acquire JDBC connections, typically configured with URL, username, password, and a connection pool.

**Persistence unit** is a JPA concept. It defines a set of entities and persistence configuration managed as one unit. A persistence unit usually corresponds to one database/schema and a group of business-related entities. In Spring, persistence units can be configured with Java configuration; a persistence.xml file is not mandatory.

**EntityManagerFactory (EMF)** is the object that creates EntityManager instances. Each EMF is bound to a specific persistence unit. EntityManager executes persist, find, merge, remove, and query operations and manages the persistence context.

**PlatformTransactionManager** is Spring's transaction abstraction. For JPA, the common implementation is JpaTransactionManager. It connects Spring transactions to the corresponding EntityManagerFactory.

The fundamental linkage:

```text
DataSource
    |
    v
LocalContainerEntityManagerFactoryBean
    |  persistence unit: orders
    v
EntityManagerFactory
    |
    v
JpaTransactionManager
    |
    v
@Transactional service
    |
    v
Spring Data JPA repositories
```

The diagram above describes configuration relationships, not the exact order of every runtime call. When a service starts a transaction, the transaction manager uses its EMF to obtain or create an EntityManager and binds that EntityManager to the current transaction. Repositories and EntityManager instances injected within the persistence unit's scope participate in that transaction.

## 2. How Does JpaTransactionManager Link to EntityManagerFactory?

JpaTransactionManager is a PlatformTransactionManager implementation dedicated to a single EntityManagerFactory. When creating the bean, pass the right EMF to its constructor:

```java
@Bean
PlatformTransactionManager ordersTransactionManager(
        EntityManagerFactory ordersEntityManagerFactory) {
    return new JpaTransactionManager(ordersEntityManagerFactory);
}
```

The key lies in the EntityManagerFactory parameter. JpaTransactionManager does not auto-discover repositories or choose a database based on method names. It manages transactions for the EMF passed into it.

Within a transaction, Spring binds the EntityManager corresponding to the EMF to the current execution thread. Components such as Spring Data JPA repositories or an EntityManager injected via @PersistenceContext can join the same persistence context and transaction. On commit, changes are flushed to the database and the transaction commits; on rollback, the transaction manager instructs the database to roll back according to transaction rules.

JpaTransactionManager is designed for **a single EntityManagerFactory**. If there are two persistence units, you normally need two EMFs and two separate JpaTransactionManager beans. Do not create one JpaTransactionManager expecting it to control every EMF in the application.

When using direct JDBC alongside JPA, JpaTransactionManager can coordinate JDBC access on the same DataSource within the transaction if JDBC code uses Spring mechanisms such as JdbcTemplate or DataSourceUtils and targets the exact DataSource managed by the EMF. Obtaining connections directly from a separate pool can cause JDBC operations to execute outside the JPA transaction.

## 3. Standard Case: One DataSource, One Persistence Unit

For a Spring Boot application using a single database, configuration typically requires only the datasource and JPA properties:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/shop
    username: shop_app
    password: change-me
    driver-class-name: org.postgresql.Driver

  jpa:
    hibernate:
      ddl-auto: validate
    open-in-view: false
    properties:
      hibernate:
        format_sql: true
```

When the appropriate starter and driver are on the classpath, Spring Boot auto-configures DataSource, EntityManagerFactory, the default persistence unit, JpaTransactionManager, and repository infrastructure. With a single-persistence-unit application, you typically do not need to manually declare LocalContainerEntityManagerFactoryBean or JpaTransactionManager.

Services can use @Transactional:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository orderRepository;

    public OrderService(PurchaseOrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public Long createOrder(PurchaseOrder order) {
        PurchaseOrder saved = orderRepository.save(order);
        return saved.getId();
    }

    @Transactional(readOnly = true)
    public Optional<PurchaseOrder> findOrder(Long id) {
        return orderRepository.findById(id);
    }
}
```

Since the application has only one eligible transaction manager, @Transactional does not need to specify a manager name. Spring uses the default transaction manager configured in the application context.

In the example, ddl-auto=validate asks Hibernate to verify whether the existing schema is compatible with mappings. In deployed environments, schema changes should be managed using versioned migrations such as Flyway or Liquibase; do not use ddl-auto=update as a production migration mechanism.

## 4. Manually Configuring a Persistence Unit

When you need explicit control over entity packages, persistence unit names, the JPA provider, or Hibernate properties, you can declare LocalContainerEntityManagerFactoryBean and JpaTransactionManager.

```java
@Configuration
@EnableTransactionManagement
@EnableJpaRepositories(
    basePackages = "com.example.orders.persistence.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfiguration {

    @Bean(name = "ordersEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            @Qualifier("ordersDataSource") DataSource dataSource) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();

        factory.setDataSource(dataSource);
        factory.setPackagesToScan(
                "com.example.orders.persistence.entity"
        );
        factory.setPersistenceUnitName("orders");
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());
        factory.setJpaPropertyMap(Map.of(
                "hibernate.hbm2ddl.auto", "validate",
                "hibernate.format_sql", "true"
        ));

        return factory;
    }

    @Bean(name = "ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {

        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

The example assumes a DataSource bean named ordersDataSource is configured elsewhere. Key imports belong to the following packages:

- org.springframework.context.annotation for @Configuration, @Bean.
- org.springframework.data.jpa.repository.config for @EnableJpaRepositories.
- org.springframework.orm.jpa for LocalContainerEntityManagerFactoryBean and JpaTransactionManager.
- org.springframework.orm.jpa.vendor for HibernateJpaVendorAdapter.
- jakarta.persistence for EntityManagerFactory and JPA annotations.
- javax.sql for DataSource.
- org.springframework.beans.factory.annotation for @Qualifier.

Four settings need to be understood:

1. **setDataSource** specifies the database connection source used by the persistence unit.
2. **setPackagesToScan** determines which entity packages are included in this persistence unit. Do not scan into entities of another persistence unit.
3. **setPersistenceUnitName("orders")** names the persistence unit so JPA injection points can reference it.
4. **new JpaTransactionManager(entityManagerFactory)** links the transaction manager to the exact EMF just declared.

@EnableJpaRepositories also has two important references. entityManagerFactoryRef is the Spring bean name providing EntityManagerFactory; transactionManagerRef is the Spring bean name managing transactions for those repositories. Repositories in the specified package will use that exact pair.

When configuring with Spring Boot, consider letting Boot create beans when there are no special requirements. When declaring EMF or the transaction manager manually, certain corresponding auto-configurations will back off based on bean conditions. Avoid configuring manually while inadvertently keeping unwanted default beans.

## 5. Persistence Unit Name, Bean Name, and Transaction Manager Name

These three names are often named similarly for readability, but they have different meanings:

| Name | Belongs To | Referenced By |
|---|---|---|
| orders | JPA persistence unit | @PersistenceContext(unitName = "orders"), @PersistenceUnit(unitName = "orders") |
| ordersEntityManagerFactory | Spring bean | @Qualifier and entityManagerFactoryRef |
| ordersTransactionManager | Spring bean | transactionManagerRef and @Transactional(transactionManager = "ordersTransactionManager") |

**The persistence unit name is not the EntityManagerFactory bean name.** In the example, the two names are similar so readers can relate them easily, but they are two distinct identifiers. Renaming the bean does not rename the persistence unit, and vice versa.

Similarly, transactionManagerRef takes the Spring bean name of the transaction manager. It does not take the persistence unit name.

The references can be visualized as:

```text
@PersistenceContext(unitName = "orders")
                |
                v
       persistence unit "orders"
                |
                v
ordersEntityManagerFactory (Spring bean)
                |
                v
ordersTransactionManager (Spring bean)
                |
                v
@Transactional(transactionManager = "ordersTransactionManager")
```

In code, you can inject the EntityManager for a specific persistence unit:

```java
@Repository
public class OrderLookup {

    @PersistenceContext(unitName = "orders")
    private EntityManager entityManager;

    public PurchaseOrder find(Long id) {
        return entityManager.find(PurchaseOrder.class, id);
    }
}
```

@PersistenceContext asks Spring for an EntityManager proxy matching the specified persistence unit. This proxy participates in the EntityManager bound to the active transaction when an appropriate transaction exists. Do not create EntityManager manually via createEntityManager() for routine business operations, as doing so detaches the persistence context lifecycle from Spring's transaction management.

If injecting EntityManagerFactory directly, you can use @PersistenceUnit(unitName = "orders") or inject the bean via @Qualifier("ordersEntityManagerFactory"). The second approach references the bean name; the first references the persistence unit name.

## 6. Multiple DataSources or Multiple Persistence Units

Suppose an application has two independent data areas:

- Orders stores customers, orders, and order line items.
- Billing stores invoices and payment details.

Each area has its own datasource, entity package, persistence unit, EntityManagerFactory, transaction manager, and repository package.

```text
ordersDataSource
    |
ordersEntityManagerFactory (unit: orders)
    |
ordersTransactionManager
    |
com.example.orders.persistence.repository

billingDataSource
    |
billingEntityManagerFactory (unit: billing)
    |
billingTransactionManager
    |
com.example.billing.persistence.repository
```

Repository configuration for Orders:

```java
@Configuration
@EnableTransactionManagement
@EnableJpaRepositories(
    basePackages = "com.example.orders.persistence.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfiguration {

    @Bean(name = "ordersEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            @Qualifier("ordersDataSource") DataSource dataSource) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan(
                "com.example.orders.persistence.entity"
        );
        factory.setPersistenceUnitName("orders");
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());
        factory.setJpaPropertyMap(Map.of(
                "hibernate.hbm2ddl.auto", "validate"
        ));
        return factory;
    }

    @Bean(name = "ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Billing has a similar configuration but references its own beans and packages:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.billing.persistence.repository",
    entityManagerFactoryRef = "billingEntityManagerFactory",
    transactionManagerRef = "billingTransactionManager"
)
public class BillingJpaConfiguration {

    @Bean(name = "billingEntityManagerFactory")
    LocalContainerEntityManagerFactoryBean billingEntityManagerFactory(
            @Qualifier("billingDataSource") DataSource dataSource) {

        LocalContainerEntityManagerFactoryBean factory =
                new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan(
                "com.example.billing.persistence.entity"
        );
        factory.setPersistenceUnitName("billing");
        factory.setJpaVendorAdapter(new HibernateJpaVendorAdapter());
        factory.setJpaPropertyMap(Map.of(
                "hibernate.hbm2ddl.auto", "validate"
        ));
        return factory;
    }

    @Bean(name = "billingTransactionManager")
    PlatformTransactionManager billingTransactionManager(
            @Qualifier("billingEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

The ordersDataSource and billingDataSource beans must be declared separately, typically using @ConfigurationProperties with two different prefixes. DataSourceProperties can be used to initialize each pool. When injecting a DataSource into a factory, always use @Qualifier to prevent Spring from selecting the wrong datasource.

Property example:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders
      username: orders_app
      password: change-me
      driver-class-name: org.postgresql.Driver
    billing:
      url: jdbc:postgresql://localhost:5432/billing
      username: billing_app
      password: change-me
      driver-class-name: org.postgresql.Driver
```

The property names above are just application-custom prefixes; configuration beans are needed to bind them into actual DataSources. You cannot simply add two property groups and expect Spring Boot to automatically infer two persistence units. With multiple datasources, the application must declare how to create the DataSources, EMFs, transaction managers, and corresponding repositories.

When having multiple @EnableJpaRepositories annotations, each configuration must have a distinct repository package. If two configurations scan the same package, repositories may be registered twice or wired to the wrong EMF. Entity packages should also be clearly separated to avoid an entity accidentally belonging to both persistence units unless intentional.

## 7. Selecting the Transaction Manager for Services

With multiple transaction managers, a @Transactional annotation without a specified manager may no longer have enough information to select the right transaction. Specify the bean name:

```java
@Service
public class OrderService {

    @Transactional(transactionManager = "ordersTransactionManager")
    public void confirmOrder(Long orderId) {
        // Read and update entities belonging to the Orders persistence unit.
    }
}
```

For Billing operations:

```java
@Service
public class BillingService {

    @Transactional(transactionManager = "billingTransactionManager")
    public void issueInvoice(Long orderId) {
        // Invoke repositories belonging to the Billing persistence unit.
    }
}
```

The transactionManager attribute of @Transactional accepts the qualifier/bean name of the transaction manager; the value attribute is its alias. If the application has only one transaction manager, this attribute can be omitted. When there are multiple managers, you can mark one manager as @Primary to act as the default for injections needing a single choice, though for business services belonging to a specific persistence unit, stating the manager explicitly makes the relationship easier to verify.

Do not confuse the following two things:

- @EnableJpaRepositories(transactionManagerRef = "...") binds a repository package to that repository's default transaction manager.
- @Transactional(transactionManager = "...") selects the transaction manager for the running service method.

Repository configuration does not replace choosing the manager for the service. Keep the two references consistent.

## 8. Can One Transaction Span Multiple Persistence Units?

Two separate JpaTransactionManager instances do not automatically form a single atomic transaction. If a service calls an Orders repository and then a Billing repository, each repository may participate in a transaction controlled by its own manager. One operation succeeding while the other fails can leave data in two divergent states.

For example: confirming an order in Orders and issuing an invoice in Billing. If both operations must commit or roll back together across multiple resources, you need an appropriate distributed transaction design, typically JTA with supporting transaction manager and resources. Atomicity cannot be achieved simply by placing two differently named @Transactional annotations or invoking two JpaTransactionManager instances sequentially.

If the business domain allows eventual consistency, you can design a multi-step workflow, outbox pattern, retries, and compensating actions. The choice depends on business requirements, database capabilities, and transaction infrastructure. Do not add JTA merely because an application has two databases if business operations do not require distributed transactions.

If two EMFs share the same DataSource, each EMF still has its own persistence context and transaction manager. Sharing one database connection source does not automatically merge two persistence units into one persistence context or one JPA transaction.

## 9. Execution Flow When Calling @Transactional

For a service method called from another bean through a Spring proxy, the high-level flow is:

1. The proxy reads metadata from @Transactional, including propagation, isolation, readOnly, and the selected transaction manager.
2. The transaction manager begins a new transaction or joins an existing one per the propagation setting.
3. JpaTransactionManager obtains or creates an EntityManager for the EMF it manages, then binds it to the current transaction.
4. The service invokes repositories or EntityManager. Persistence operations join the appropriate persistence context.
5. When the method finishes normally, the transaction manager flushes necessary changes and commits.
6. If an exception matching the rollback policy occurs, the transaction manager rolls back. By default, Spring rolls back on RuntimeException and Error; checked exceptions do not trigger automatic rollback unless rollbackFor is configured accordingly.

Example declaring rollback for a checked exception:

```java
@Transactional(
    transactionManager = "ordersTransactionManager",
    rollbackFor = OrderRejectedException.class
)
public void confirmOrder(Long orderId) throws OrderRejectedException {
    // Validate conditions and update order status.
}
```

@Transactional works via proxies. Calling another transactional method within the same object via this.method() normally bypasses the proxy, and thus does not create a new transaction boundary as many expect. Place transaction boundaries on service methods called from another bean or use an appropriate Spring mechanism.

Propagation modes such as REQUIRED, REQUIRES_NEW, and MANDATORY determine how a method joins an existing transaction. Isolation is passed down to the transaction/database when supported. readOnly is a hint to the transaction manager/provider that may help optimize reads; do not treat it as an authorization mechanism strictly forbidding writes.

## 10. Testing the Configuration

When verifying a persistence unit configuration, confirm that:

- The application context starts and creates the right DataSource, EntityManagerFactory, and transaction manager.
- Entities are registered into the right persistence unit.
- Repository packages use the right entityManagerFactoryRef and transactionManagerRef.
- Service methods select the right transaction manager.
- EntityManager is injected with the right unitName when multiple persistence units exist.
- Rollback actually reverts data when business logic throws an exception.
- Direct JDBC access, if any, uses the same DataSource and Spring's transaction-aware mechanism.

For single-persistence-unit applications, @DataJpaTest is usually suitable for testing mappings and repositories. With multiple persistence units, import the relevant configurations and confirm each repository accesses the right database. When using PostgreSQL or another database in production, include integration tests against the same database type, e.g., via Testcontainers; H2 can differ in dialect, constraints, locking, and native SQL.

You can verify runtime configuration by inspecting bean names and bean types in ApplicationContext. For deep diagnostics, enable Spring transaction logs and Hibernate SQL logs in development environments. Do not indiscriminately enable sensitive SQL/parameter logging in production.

## 11. Common Errors and Troubleshooting

| Symptom | Possible Cause | How to Check |
|---|---|---|
| No qualifying bean of type PlatformTransactionManager | No manager declared or auto-configuration backed off | Check transaction manager beans and JPA configuration conditions |
| NoUniqueBeanDefinitionException | Multiple transaction managers or EntityManagerFactories without unambiguous injection | Use @Qualifier, specify transactionManager, or configure @Primary intentionally |
| Repository accesses wrong database | Incorrect entityManagerFactoryRef or DataSource qualifier | Check package scans and the bean chain repository → EMF → DataSource |
| Transaction does not cover JPA operations | Service selects manager of another persistence unit | Cross-check transactionManagerRef, @Transactional, and EMF |
| No EntityManager with actual transaction available | Calling an operation requiring a transaction without an eligible transaction | Check transaction annotations, proxy calls, and selected manager |
| Entity not found or missing mapping | Entity package is not in EMF's packagesToScan | Check package scan and persistence unit |
| @PersistenceContext injects wrong unit | unitName does not match configured persistence unit | Cross-check setPersistenceUnitName with unitName |
| Orders data committed while Billing failed | Two independent local transaction managers | Design JTA or an eventual consistency workflow as required |

When troubleshooting, trace the reference chain from the repository down to the DataSource. Most multi-persistence-unit configuration errors stem from one of three points: wrong package scan, wrong bean reference, or a service choosing the wrong transaction manager.

## 12. Design Checklist Before Adding a Persistence Unit

Before creating a second persistence unit, answer these questions:

1. Is separating entities and persistence contexts genuinely necessary, or do you only need to add repositories in the existing persistence unit?
2. What are the entity packages and repository packages for each unit?
3. Which DataSource and bean name does each unit use?
4. What are the persistence unit name, EntityManagerFactory bean name, and transaction manager bean name?
5. Are repositories wired to the correct entityManagerFactoryRef and transactionManagerRef?
6. Which services must specify transactionManager?
7. Does any business workflow require a single atomic transaction across multiple databases?
8. Have integration tests verified the right databases, rollback, and mappings?

Adding another persistence unit increases the number of configurations and transaction boundaries to manage. Only split when there is a clear data, schema, database, or governance boundary.

**Rule to remember:** a persistence unit defines a group of entities and JPA settings; EntityManagerFactory represents the persistence unit at runtime; JpaTransactionManager manages transactions for that exact EntityManagerFactory; repositories are wired to the EMF/transaction manager pair via @EnableJpaRepositories; services select the transaction manager via @Transactional when the application has multiple managers. When these five links align, EntityManager and repositories participate in the right persistence context and transaction.