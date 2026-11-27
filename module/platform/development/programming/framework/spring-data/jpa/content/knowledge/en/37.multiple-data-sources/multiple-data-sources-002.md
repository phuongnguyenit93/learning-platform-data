# Separating EntityManagerFactory, Persistence Unit, and TransactionManager in Spring Data JPA

When an application needs to work with multiple data sources, simply declaring an extra `DataSource` is not enough. Each repository group must be bound to the right `EntityManagerFactory`, persistence unit, and `PlatformTransactionManager`. If misconfigured, a repository may hit the wrong database, an entity may not be managed by the intended persistence unit, or a transaction may fail to cover the intended operations.

This article uses Java 17+, Spring Boot 3.x, Spring Data JPA, Hibernate 6, and PostgreSQL in its examples. We assume the application has two independent databases: `orders` for storing orders and `billing` for storing invoices.

## 1. Distinguishing the four components

| Component | Responsibility | Example |
|---|---|---|
| `DataSource` | Provides JDBC connections to a data source | URL, username, password, connection pool of the orders database |
| Persistence unit | JPA configuration group consisting of entities, mappings, provider, and logical name | `orders` containing order entities |
| `EntityManagerFactory` | Creates `EntityManager` instances for a persistence unit | `ordersEntityManagerFactory` |
| `PlatformTransactionManager` | Manages transactions for a resource or persistence unit | `ordersTransactionManager` |

A persistence unit is typically backed by one `EntityManagerFactory`. The EntityManager created by the factory manages its persistence context. Two separate factories can use two different DataSources, or even the same database with separate entity scans and configurations.

`@EnableJpaRepositories` links a repository package with the corresponding JPA beans via two attributes:

- `entityManagerFactoryRef`: the factory bean that the repositories will use.
- `transactionManagerRef`: the transaction manager that the repositories use for their transactions.

Bean names and persistence unit names are two distinct concepts. `entityManagerFactoryRef` points to the Spring bean name; `@PersistenceContext(unitName = "...")` points to the persistence unit name declared when building the factory.

## 2. Organizing packages to separate repositories and entities

An easy-to-manage structure:

```text
com.example
├── orders
│   ├── domain
│   │   └── Order.java
│   ├── repository
│   │   └── OrderRepository.java
│   └── config
│       └── OrdersJpaConfig.java
├── billing
│   ├── domain
│   │   └── Invoice.java
│   ├── repository
│   │   └── InvoiceRepository.java
│   └── config
│       └── BillingJpaConfig.java
└── service
    ├── OrderService.java
    └── BillingService.java
```

Separating packages ensures each configuration only scans repositories and entities belonging to its own data source. Avoid letting two `@EnableJpaRepositories` configurations scan the same repository package, as a repository could be registered against an unintended factory.

Example entities:

**Order.java**

```java
package com.example.orders.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "orders")
public class Order {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String orderNumber;

    protected Order() {
    }

    public Order(String orderNumber) {
        this.orderNumber = orderNumber;
    }

    public Long getId() {
        return id;
    }

    public String getOrderNumber() {
        return orderNumber;
    }
}
```

**Invoice.java**

```java
package com.example.billing.domain;

import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "invoices")
public class Invoice {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String invoiceNumber;

    protected Invoice() {
    }

    public Invoice(String invoiceNumber) {
        this.invoiceNumber = invoiceNumber;
    }

    public Long getId() {
        return id;
    }

    public String getInvoiceNumber() {
        return invoiceNumber;
    }
}
```

Repositories:

**OrderRepository.java**

```java
package com.example.orders.repository;

import com.example.orders.domain.Order;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository extends JpaRepository<Order, Long> {
    Optional<Order> findByOrderNumber(String orderNumber);
}
```

**InvoiceRepository.java**

```java
package com.example.billing.repository;

import com.example.billing.domain.Invoice;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InvoiceRepository extends JpaRepository<Invoice, Long> {
    Optional<Invoice> findByInvoiceNumber(String invoiceNumber);
}
```

## 3. Declaring configuration for the orders database

Use `DataSourceProperties` to bind URL, username, password, and driver. `initializeDataSourceBuilder()` handles the difference between the `url` property in configuration and HikariCP's `jdbcUrl`.

**OrdersJpaConfig.java**

```java
package com.example.orders.config;

import com.example.orders.domain.Order;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import javax.sql.DataSource;
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

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackages = "com.example.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfig {

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
            @Qualifier("ordersDataSourceProperties")
            DataSourceProperties properties) {
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
            .build();
    }

    @Bean
    @Primary
    public PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Key points to note:

- `@EnableJpaRepositories` only scans the orders repository package.
- `packages(Order.class)` tells the factory to scan the package containing the `Order` entity.
- `persistenceUnit("orders")` names the persistence unit so it can be referenced via `@PersistenceContext(unitName = "orders")`.
- `ordersTransactionManager` is created from the exact `ordersEntityManagerFactory`.
- `@Primary` helps Spring Boot choose a default data source when certain auto-configurations require a primary candidate. It does not replace the two explicit references in `@EnableJpaRepositories`.

In this configuration, `EntityManagerFactoryBuilder` is the builder provided by Spring Boot JPA auto-configuration. Marking the orders DataSource as `@Primary` gives auto-configuration a primary DataSource when the application has multiple DataSources. If the project configures JPA entirely manually or does not use the auto-configured builder, you can instantiate `LocalContainerEntityManagerFactoryBean` directly with the DataSource, package scan, persistence unit name, and `JpaVendorAdapter`.

## 4. Declaring configuration for the billing database

The second configuration is similar, but uses separate entity/repository packages and bean names. The billing beans are not marked as `@Primary` in this example because orders is chosen as the default.

**BillingJpaConfig.java**

```java
package com.example.billing.config;

import com.example.billing.domain.Invoice;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.persistence.EntityManagerFactory;
import javax.sql.DataSource;
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

@Configuration(proxyBeanMethods = false)
@EnableJpaRepositories(
    basePackages = "com.example.billing.repository",
    entityManagerFactoryRef = "billingEntityManagerFactory",
    transactionManagerRef = "billingTransactionManager"
)
public class BillingJpaConfig {

    @Bean
    @ConfigurationProperties("app.datasource.billing")
    public DataSourceProperties billingDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.billing.configuration")
    public HikariDataSource billingDataSource(
            @Qualifier("billingDataSourceProperties")
            DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
    }

    @Bean
    public LocalContainerEntityManagerFactoryBean billingEntityManagerFactory(
            EntityManagerFactoryBuilder builder,
            @Qualifier("billingDataSource") DataSource dataSource) {
        return builder
            .dataSource(dataSource)
            .packages(Invoice.class)
            .persistenceUnit("billing")
            .build();
    }

    @Bean
    public PlatformTransactionManager billingTransactionManager(
            @Qualifier("billingEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

Each configuration has three key beans: DataSource, EntityManagerFactory, and TransactionManager. Never reuse the orders transaction manager for billing repositories, because that manager is bound to the orders factory.

## 5. Configuring connections in application.yml

Example using two PostgreSQL databases:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders
      username: ${ORDERS_DB_USER}
      password: ${ORDERS_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 10
        minimum-idle: 2

    billing:
      url: jdbc:postgresql://localhost:5432/billing
      username: ${BILLING_DB_USER}
      password: ${BILLING_DB_PASSWORD}
      driver-class-name: org.postgresql.Driver
      configuration:
        maximum-pool-size: 5
        minimum-idle: 1
```

Environment variables hold the credentials. Never commit real passwords to the repository. Even if both databases share the same server with different database names/schemas, URLs and access permissions should still be configured separately.

Different JPA properties can be configured per persistence unit when needed, such as naming strategy, schema, or Hibernate batch size. Place properties on the appropriate factory; a global Hibernate setting may not apply as expected to both manually created factories.

## 6. Binding services to the right transaction manager

The order service uses the orders transaction manager:

**OrderService.java**

```java
package com.example.service;

import com.example.orders.domain.Order;
import com.example.orders.repository.OrderRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "ordersTransactionManager")
    public Long create(String orderNumber) {
        return repository.save(new Order(orderNumber)).getId();
    }
}
```

The invoice service uses the billing transaction manager:

**BillingService.java**

```java
package com.example.service;

import com.example.billing.domain.Invoice;
import com.example.billing.repository.InvoiceRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BillingService {

    private final InvoiceRepository repository;

    public BillingService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "billingTransactionManager")
    public Long create(String invoiceNumber) {
        return repository.save(new Invoice(invoiceNumber)).getId();
    }
}
```

When specifying `transactionManager`, the name must match the declared TransactionManager bean. If you omit the qualifier, Spring picks the default manager according to bean resolution rules, typically the `@Primary` bean; that can cause a service to use the wrong transaction manager.

You can write the shorthand `@Transactional("ordersTransactionManager")`, as the `value` attribute is an alias for the transaction manager name. Using the named attribute makes the intent clearer.

## 7. Injecting EntityManager from the right persistence unit

In repositories, Spring Data already uses the factory configured via `entityManagerFactoryRef`. For custom DAOs that need an `EntityManager` directly, declare the unit name:

```java
package com.example.orders.repository;

import com.example.orders.domain.Order;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import java.util.List;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class OrderSearchDao {

    @PersistenceContext(unitName = "orders")
    private EntityManager entityManager;

    @Transactional(transactionManager = "ordersTransactionManager", readOnly = true)
    public List<Order> findRecent() {
        return entityManager.createQuery(
            "select o from Order o order by o.id desc",
            Order.class
        ).setMaxResults(20).getResultList();
    }
}
```

A billing DAO can use `@PersistenceContext(unitName = "billing")`. The unit name must match `persistenceUnit("billing")`, not the bean name `billingEntityManagerFactory`.

Do not manually create an `EntityManager` by calling `entityManagerFactory.createEntityManager()` in a regular service and forget to close it. `@PersistenceContext` provides a proxy bound to the current persistence context/transaction whose lifecycle is managed by the container.

If you need to inject the factory directly, use a qualifier:

```java
@Autowired
public OrderMaintenance(
        @Qualifier("ordersEntityManagerFactory")
        EntityManagerFactory entityManagerFactory) {
    this.entityManagerFactory = entityManagerFactory;
}
```

## 8. Transactions across two databases are not automatically atomic

Two `JpaTransactionManager` instances manage two separate resources. A service method annotated with `@Transactional("ordersTransactionManager")` only creates a transaction for the orders persistence unit. If that method calls a billing service that has its own transaction manager, billing can open and commit an independent transaction.

Example scenario:

1. Save the order in the orders transaction.
2. Call the billing service to create an invoice; the billing transaction commits.
3. The orders transaction encounters an error and rolls back.

The outcome can be an existing invoice while the order was rolled back. Placing two `@Transactional` annotations with different managers does not create an atomic distributed transaction.

If the business requires both databases to commit or roll back together, a genuine distributed transaction solution is needed, typically JTA/XA with XA-capable DataSources and a `JtaTransactionManager`. This approach requires coordinator configuration, recovery logs, and more complex operations.

For many systems, transactional outbox and saga are often a better fit:

- Commit the business data alongside an outbox record in the source database.
- A worker publishes messages or calls a service targeting the destination database.
- Track state, retry, and process idempotently.
- If a downstream step fails, execute compensating actions or let the workflow continue retrying according to policy.

Choose the solution based on consistency requirements. Do not assume two local transaction managers provide an atomic commit.

## 9. Testing multi-persistence-unit wiring

When there are multiple DataSources, `@DataJpaTest` is by default designed around a single JPA slice and may not load both factories and their distinct configurations. To test the full wiring, use `@SpringBootTest` with two explicitly configured test databases. If you need to verify PostgreSQL-specific behavior, use Testcontainers PostgreSQL instead of relying on H2.

Example integration test verifying repositories are bound to two different transaction managers:

**MultiDatabaseWiringTest.java**

```java
package com.example;

import static org.assertj.core.api.Assertions.assertThat;

import com.example.billing.domain.Invoice;
import com.example.billing.repository.InvoiceRepository;
import com.example.orders.domain.Order;
import com.example.orders.repository.OrderRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootTest
class MultiDatabaseWiringTest {

    @Autowired
    private OrderRepository orderRepository;

    @Autowired
    private InvoiceRepository invoiceRepository;

    private final TransactionTemplate ordersTransaction;
    private final TransactionTemplate billingTransaction;

    @Autowired
    MultiDatabaseWiringTest(
            @Qualifier("ordersTransactionManager")
            PlatformTransactionManager ordersManager,
            @Qualifier("billingTransactionManager")
            PlatformTransactionManager billingManager) {
        this.ordersTransaction = new TransactionTemplate(ordersManager);
        this.billingTransaction = new TransactionTemplate(billingManager);
    }

    @Test
    void repositoriesUseTheirOwnPersistenceUnits() {
        Long orderId = ordersTransaction.execute(status ->
            orderRepository.save(new Order("ORD-TEST-001")).getId()
        );

        Long invoiceId = billingTransaction.execute(status ->
            invoiceRepository.save(new Invoice("INV-TEST-001")).getId()
        );

        boolean orderExists = ordersTransaction.execute(status ->
            orderRepository.findById(orderId).isPresent()
        );

        boolean invoiceExists = billingTransaction.execute(status ->
            invoiceRepository.findById(invoiceId).isPresent()
        );

        assertThat(orderId).isNotNull();
        assertThat(invoiceId).isNotNull();
        assertThat(orderExists).isTrue();
        assertThat(invoiceExists).isTrue();
    }
}
```

This test requires two test databases with initialized schemas configured in the test profile. In real projects, use unique identifiers or clean up data after tests to avoid execution-order dependencies. If a repository is bound to the wrong factory or transaction manager, the test will typically fail when persisting/querying an entity not belonging to that persistence unit, or data will appear in an unintended source.

Additional checks you can make:

- `ordersEntityManagerFactory` and `billingEntityManagerFactory` are two distinct factories.
- Each factory manages only its expected entity package.
- Each repository package is scanned exactly once.
- `@Transactional` in services picks the right manager.
- Rolling back orders is not mistaken for automatically rolling back the billing transaction.
- Migrations/schemas are applied separately per database.

## 10. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `NoUniqueBeanDefinitionException` for DataSource or EntityManagerFactory | Multiple beans of the same type without qualifier/primary | Use `@Qualifier` at injection points and pick `@Primary` for default if needed |
| Repository uses wrong database | Misconfigured `entityManagerFactoryRef` or package scan | Set explicit refs and separate repository packages |
| `Not a managed type` | Entity is not in the factory's scanned packages | Use `.packages(EntityClass.class)` or declare the exact package |
| Persistence unit not found | `@PersistenceContext(unitName)` does not match factory name | Cross-check with `.persistenceUnit("...")` |
| Transaction does not roll back data as expected | Service uses wrong transaction manager or operates on another resource | Set `@Transactional(transactionManager = "...")` to the right resource |
| Boot cannot create default JPA builder | Multiple DataSources without a primary candidate or auto-configuration excluded | Choose a primary DataSource or configure builder/factory manually |
| Two repository configs register the same repository | Overlapping package scans | Restrict `basePackages` for each `@EnableJpaRepositories` |
| Tests pass on H2 but fail in production | Different dialects, schemas, sequences, types, or SQL | Test against the real database family with Testcontainers |

## 11. Implementation checklist

1. Identify which DataSource, persistence unit, EntityManagerFactory, and TransactionManager belong to each data source.
2. Separate entity and repository packages by data source.
3. Configure `@EnableJpaRepositories` with explicit `entityManagerFactoryRef` and `transactionManagerRef`.
4. Set persistence unit names and match them in `@PersistenceContext(unitName)`.
5. Use qualifiers when injecting beans of the same type; only use `@Primary` for an intentional default.
6. Bind service `@Transactional` annotations to the right transaction manager.
7. Manage schemas/migrations and connection pools separately per database.
8. Test repository wiring against the respective databases.
9. If a business operation touches multiple databases, explicitly design the consistency model: JTA/XA, outbox, or saga.

A DataSource provides connections; a persistence unit defines a JPA mapping group; an EntityManagerFactory creates EntityManagers; a TransactionManager controls transactions for the corresponding resource. When these links are explicitly declared, Spring Data JPA can operate multiple data sources with clear, testable repository and transaction boundaries.