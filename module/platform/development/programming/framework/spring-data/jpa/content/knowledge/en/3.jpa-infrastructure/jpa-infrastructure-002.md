# Persistence Unit, PersistenceContext, and Resource Lifecycle in Spring Data JPA

This document explains how JPA organizes persistence configuration, creates and manages `EntityManagerFactory`, allocates `EntityManager`, binds a persistence context to a transaction, and releases resources. This is the infrastructure layer that determines the scope in which entities are managed, which database configuration queries use, and when connections are returned to the connection pool.

The examples use the `jakarta.persistence` namespace of Jakarta Persistence and Spring Framework 6 / Spring Boot 3 or later. Older Spring Boot 2 projects commonly use `javax.persistence`; do not mix the two namespaces in the same application.

## 1. Overall Picture

Related concepts that are not synonymous:

- **Persistence unit** is a logical configuration unit of JPA: the set of managed entities, provider, connection source, transaction type, and mapping/cache/validation settings.
- **EntityManagerFactory (EMF)** is a factory created from a persistence unit. It holds provider metadata and infrastructure, and creates EntityManager instances.
- **EntityManager (EM)** is the API for working with entities within a persistence context. It performs persist, find, merge, remove, query, and flush.
- **Persistence context** is the management scope of entity instances. Within that scope, JPA tracks entity state, identity, and changes that need to be synchronized to the database.
- **Transaction** is the commit/rollback boundary of database operations. Persistence context and transaction are typically coupled in common Spring usage.
- **Connection** is a physical or logical connection to the database provided by a DataSource/connection pool. An EntityManager does not equate to a connection kept open throughout its entire lifecycle.

Typical flow in a Spring application:

`Application service → EntityManager proxy → Transaction-bound EntityManager → JPA provider → JDBC connection → Database`

Here Spring manages the transaction and the lifecycle of the real EntityManager. Business code usually only sees an injected EntityManager reference.

## 2. What Is a Persistence Unit?

A persistence unit is a named configuration for a set of persistence classes and related settings. It answers questions such as:

- Which entities fall under this unit's management scope?
- Which JPA provider implements Jakarta Persistence?
- Does the unit use DataSource/JDBC connections or JTA?
- How are mapping files, converters, listeners, caching, and validation configured?
- How are schema generation and provider-specific properties set?

A persistence unit usually corresponds to one database domain or one group of entities that must be managed under the same configuration. It is **not** a transaction, a session, a schema, or a database name.

An application can have one persistence unit or multiple units. For a single database and a standard set of entities, Spring Boot normally configures one unit automatically. Applications connecting to multiple databases, separating data domains, or needing two independent groups of entities/providers may require multiple persistence units and multiple EntityManagerFactory beans.

### 2.1. Configuring with persistence.xml

Per Jakarta Persistence, standard configuration can be placed in `META-INF/persistence.xml` on the classpath or inside a persistence archive. Minimal example for Java SE:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<persistence xmlns="https://jakarta.ee/xml/ns/persistence"
             version="3.1">
    <persistence-unit name="catalog"
                     transaction-type="RESOURCE_LOCAL">
        <provider>org.hibernate.jpa.HibernatePersistenceProvider</provider>
        <class>com.example.catalog.Product</class>
        <properties>
            <property name="jakarta.persistence.jdbc.url"
                      value="jdbc:postgresql://localhost:5432/catalog"/>
            <property name="jakarta.persistence.jdbc.user"
                      value="app"/>
            <property name="jakarta.persistence.jdbc.password"
                      value="change-me"/>
            <property name="jakarta.persistence.jdbc.driver"
                      value="org.postgresql.Driver"/>
        </properties>
    </persistence-unit>
</persistence>
```

Explanation:

- `name="catalog"` is the persistence unit name. This name can be used in `@PersistenceContext(unitName = "catalog")` or `@PersistenceUnit(unitName = "catalog")`.
- `transaction-type="RESOURCE_LOCAL"` indicates that transactions are controlled through the EntityManager's local transaction API. In a Jakarta EE environment with JTA, the unit can use `JTA`.
- `provider` specifies the implementation, such as Hibernate. When using only a default provider, some configurations may omit this element.
- `class` lists the managed entities. Additional mapping files, jars, converter classes, or listeners can be declared depending on the configuration.
- `properties` contains standard Jakarta Persistence properties or provider-specific properties. The connection properties in the example are for illustration; real applications should retrieve secrets from a secret manager or environment variables.

In Jakarta EE, the container can provide a DataSource and transaction manager via JNDI/JTA. In that case, connection and transaction configuration differs from the Java SE example above.

### 2.2. Spring Boot Usually Does Not Need persistence.xml

In Spring Boot with Spring Data JPA, auto-configuration normally creates the DataSource, EntityManagerFactory, and transaction manager based on dependencies, datasource configuration, and scanned entities. Hibernate is typically the default provider when using the JPA starter without replacing the provider.

Configuration example:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=app
spring.datasource.password=${DB_PASSWORD}

spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
spring.jpa.properties.hibernate.format_sql=true
```

Common settings:

- `spring.datasource.*` configures the DataSource and database connection.
- `spring.jpa.hibernate.ddl-auto` controls Hibernate's schema behavior, such as `validate`, `update`, `create`, or `create-drop`. For production, choose an explicit migration policy; do not default to `update`.
- `spring.jpa.properties.*` forwards properties to the provider.
- `spring.jpa.open-in-view` controls Open EntityManager in View in web applications. Disabling it usually clarifies data access boundaries and forces services to load required data inside transactions.

Spring Boot also automatically discovers entities in appropriate packages starting from the package of the main configuration class. `@EntityScan` can be used when entities reside in other packages. Thus, in typical Boot applications, there is no need to manually create `persistence.xml` just to declare entities.

## 3. EntityManagerFactory: The Factory That Allocates EntityManager

### 3.1. Role and Characteristics

An EntityManagerFactory is created for a persistence unit. During initialization, the provider processes entity metadata, mappings, appropriate query plans/caches, and connection settings. The EMF then creates EntityManager instances on demand.

Key points:

- **Heavyweight and expensive to initialize:** do not create a new EMF per request or per transaction.
- **Thread-safe for concurrent use:** EntityManagerFactory is designed to be shared across threads in an application.
- **Typically one EMF per unit:** if there are multiple persistence units, there is usually one corresponding EMF for each unit.
- **Application-level lifecycle:** the Spring container usually creates the EMF on context startup and closes it on context shutdown.
- **Not a connection pool:** EMF creates EntityManager instances; DataSource/connection pool manages allocating connections to the database.

In Spring Boot, do not manually call `close()` on a container-managed EMF. Let Spring execute lifecycle callbacks when the application shuts down.

### 3.2. Obtaining EntityManagerFactory

An EMF can be injected using `@PersistenceUnit`:

```java
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.PersistenceUnit;
import org.springframework.stereotype.Component;

@Component
public class JpaInfrastructureInfo {
    @PersistenceUnit
    private EntityManagerFactory entityManagerFactory;

    public boolean isOpen() {
        return entityManagerFactory.isOpen();
    }
}
```

`@PersistenceUnit` is for EntityManagerFactory. This is the choice when you need to manually create an EntityManager, inspect metadata via the factory, or call factory APIs.

If the application manages an EntityManager manually via `createEntityManager()`, the application must also manage transactions and close the EntityManager itself. In ordinary Spring services, prefer letting Spring manage it rather than creating it manually.

### 3.3. When Are Multiple EntityManagerFactory Beans Needed?

For example, a system has an independent orders database and a reporting database. Each entity group needs its own DataSource, package scan, and transaction manager. A representative configuration:

```java
@Configuration
@EnableJpaRepositories(
    basePackages = "com.example.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager"
)
public class OrdersJpaConfig {

    @Bean
    public LocalContainerEntityManagerFactoryBean ordersEntityManagerFactory(
            @Qualifier("ordersDataSource") DataSource dataSource,
            JpaVendorAdapter vendorAdapter) {

        var factory = new LocalContainerEntityManagerFactoryBean();
        factory.setDataSource(dataSource);
        factory.setPackagesToScan("com.example.orders.domain");
        factory.setPersistenceUnitName("orders");
        factory.setJpaVendorAdapter(vendorAdapter);
        factory.setJpaPropertyMap(Map.of(
            "hibernate.hbm2ddl.auto", "validate"
        ));
        return factory;
    }

    @Bean
    public PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersEntityManagerFactory")
            EntityManagerFactory entityManagerFactory) {
        return new JpaTransactionManager(entityManagerFactory);
    }
}
```

This illustrates the JPA configuration for one unit; the application must declare the corresponding DataSource and JpaVendorAdapter beans, along with configuration for the other unit. With multiple repository packages, each `@EnableJpaRepositories` must point to the correct `entityManagerFactoryRef` and `transactionManagerRef`.

Having multiple EMFs does not mean a single `@Transactional` automatically spans all databases. Select the transaction manager using a qualifier or clear default configuration. If business logic must update multiple databases in an atomic transaction, you must design JTA/XA or an appropriate distributed consistency strategy; two separate local transaction managers do not automatically form a distributed transaction.

## 4. PersistenceContext and EntityManager

### 4.1. Persistence Context

The persistence context is the area where JPA tracks entity instances. It maintains an identity map: within the same persistence context, one entity type and primary key typically correspond to one managed instance.

An entity can be in the following states:

- **New / transient:** a newly created Java object not yet managed by any persistence context.
- **Managed:** currently managed by a persistence context; changes can be detected and written to the database upon flush.
- **Detached:** previously managed, but no longer associated with a persistence context.
- **Removed:** marked for deletion; a DELETE statement is synchronized upon flush.

Key operations:

| API | Meaning |
|---|---|
| `persist(entity)` | Transitions a new entity to the managed state; INSERT is usually executed on flush or according to ID strategy/provider |
| `find(Type.class, id)` | Looks up an entity by primary key; may retrieve from the persistence context before querying the database |
| `merge(entity)` | Copies state from the passed object into a managed instance and returns that managed instance |
| `remove(entity)` | Marks a managed entity for deletion |
| `detach(entity)` | Detaches a single entity from the persistence context |
| `clear()` | Detaches all entities from the persistence context |
| `refresh(entity)` | Reloads state from the database, overwriting unflushed changes on the entity |
| `flush()` | Synchronizes persistence context changes to the database within the current transaction |

Special note about `merge`: the passed-in object does not itself become managed. The returned value is the managed instance. If you keep modifying the original object, subsequent changes are not automatically dirty-checked.

### 4.2. EntityManager

EntityManager is the API for working with a persistence context. It holds state and is not thread-safe. Do not share the same real EntityManager across multiple concurrent threads.

EntityManager typically provides:

- CRUD and lifecycle operations for entities.
- JPQL, Criteria API, native queries, and named queries.
- Checking managed/detached state.
- Flushing and clearing the persistence context.
- Access to the transaction API in RESOURCE_LOCAL mode.
- Access to the metamodel and persistence utilities.

EntityManager should not be treated as a stateless DAO or a shared singleton. In Spring applications, the injected reference is typically a shared proxy; the proxy looks up the EntityManager bound to the current transaction. The real EntityManager behind the proxy still has its own lifecycle and must not be used carelessly across multiple threads.

## 5. How Do @PersistenceContext and @PersistenceUnit Differ?

These two annotations serve two different purposes:

| Annotation | Injected object | Purpose |
|---|---|---|
| `@PersistenceContext` | EntityManager reference | Perform entity operations within a persistence context |
| `@PersistenceUnit` | EntityManagerFactory | Create EntityManager instances or use factory APIs |

Example:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRepositorySupport {

    @PersistenceContext
    private EntityManager entityManager;

    public Product findProduct(Long id) {
        return entityManager.find(Product.class, id);
    }
}
```

`@PersistenceContext` is the standard way to request an EntityManager reference from the container. In Spring, the framework supports this annotation and normally injects a shared EntityManager proxy. The proxy uses the EntityManager bound to the current transaction if one exists.

You can specify the unit when the application has multiple persistence units:

```java
@PersistenceContext(unitName = "orders")
private EntityManager ordersEntityManager;

@PersistenceUnit(unitName = "orders")
private EntityManagerFactory ordersEntityManagerFactory;
```

If there is only one EntityManagerFactory, `unitName` can usually be omitted. When there are multiple factories, declaring an explicit unit name or qualifier avoids injecting the wrong persistence context.

### 5.1. Shared EntityManager in Spring

In imperative Spring applications, the shared EntityManager proxy typically works as follows:

1. The service is invoked through a Spring proxy and a transaction is opened by `@Transactional`.
2. `JpaTransactionManager` obtains an EntityManager from the EntityManagerFactory.
3. Spring binds the EntityManager to the current transaction in the thread-bound transaction context.
4. When a repository or service invokes the EntityManager proxy, the proxy looks up and delegates to the EntityManager bound to the transaction.
5. When the transaction commits or rolls back, Spring ends the persistence context bound to the transaction and releases related resources.
6. The next call in another transaction will use a different EntityManager.

If there is no active transaction, the shared proxy may create a temporary EntityManager for the operation and close it afterward. This is one reason accessing lazy relations after a service returns typically fails when Open EntityManager in View is disabled.

Do not call `close()` on an EntityManager injected with `@PersistenceContext`. It is a container/Spring-managed reference; the application does not own its lifecycle.

## 6. Transaction-Scoped and Extended Persistence Context

A persistence context can have different lifetimes. Distinguish the lifetime of the persistence context from the lifetime of the EntityManager proxy or the connection.

### 6.1. Transaction-Scoped Persistence Context

This is the common model in Spring Data JPA applications:

- The persistence context is bound to the active transaction.
- Entities loaded during the transaction are managed within that context's scope.
- When the transaction commits or rolls back, the context ends and entities held in the context become detached.
- The next transaction typically uses a new persistence context/EntityManager.

Example:

```java
@Service
public class ProductService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void rename(Long id, String newName) {
        Product product = entityManager.find(Product.class, id);
        if (product == null) {
            throw new IllegalArgumentException("Product not found");
        }

        product.setName(newName);
        // Dirty checking will write changes on flush/commit.
    }
}
```

In this transaction, `product` is managed. You do not need to call `save` just to update attributes on a managed entity; dirty checking detects the changes. However, if the entity is detached or newly created, an appropriate operation such as merge/persist or repository save is needed.

### 6.2. Extended Persistence Context

An extended persistence context can span multiple transactions and keep entities managed between transactions. This model is typically associated with stateful lifecycle components in Jakarta EE.

It can be useful for a multi-step business workflow that needs to keep a group of entities managed longer than a single transaction. However:

- A long-lived persistence context can retain many entities in memory.
- Entity state may become stale relative to data updated by other transactions.
- You must clearly determine when to flush, synchronize, and end the context.
- You should not place an extended EntityManager inside a singleton service invoked concurrently by multiple requests.
- In Spring, support for extended contexts and lifecycles depends on configuration, bean scope, and the provider; you must design an owner with an explicit lifecycle rather than defaulting to it for stateless services.

For most Spring REST APIs and services, a transaction-scoped persistence context is the simpler and easier-to-control choice.

## 7. Resource Lifecycle by Model

### 7.1. Spring-Managed EntityManager

When using `@PersistenceContext`:

- Spring creates and manages EntityManagerFactory.
- Spring supplies an EntityManager proxy to the bean.
- The real EntityManager is obtained and bound to the transaction when needed.
- The transaction manager performs commit/rollback.
- Spring closes or releases the real EntityManager when the persistence context ends.
- Business code does not call `close()` on the EntityManager proxy.

This is the recommended approach for standard Spring services and repositories.

### 7.2. Application-Managed EntityManager

When calling `entityManagerFactory.createEntityManager()`, the application owns the created EntityManager and must close it. With RESOURCE_LOCAL, the application must also begin, commit, or roll back the transaction:

```java
EntityManager entityManager =
        entityManagerFactory.createEntityManager();
EntityTransaction transaction = entityManager.getTransaction();

try {
    transaction.begin();

    Product product = entityManager.find(Product.class, 1L);
    if (product != null) {
        product.setName("Updated name");
    }

    transaction.commit();
} catch (RuntimeException exception) {
    if (transaction.isActive()) {
        transaction.rollback();
    }
    throw exception;
} finally {
    entityManager.close();
}
```

This is a Java SE example with RESOURCE_LOCAL, not a pattern to use inside a Spring service that already has `@Transactional`. In JTA or container-managed transaction environments, the transaction API differs and `EntityTransaction` should not be invoked this way.

Important rule: every manually created EntityManager must be closed in `finally` or an equivalent try/finally mechanism, even if a query, flush, or commit throws an exception.

### 7.3. Application-Managed EntityManagerFactory

In Java SE, if an application creates its own EMF via `Persistence.createEntityManagerFactory("catalog")`, the application must call `close()` when finished using it. In Spring, if the EMF is declared as a bean or auto-configured by Boot, let the container close it when the ApplicationContext stops.

Do not create an EMF inside each request. EMF is an application-level resource; EntityManager is a unit-of-work resource.

### 7.4. Connections and Connection Pools

An EntityManager does not necessarily hold a JDBC connection from the moment it is created until it is closed. The provider may acquire a connection when needed and return it to the pool depending on the transaction, provider, and connection handling configuration.

Within a transaction, the connection is usually held until the transaction ends to ensure consistency. When the transaction ends, the connection is returned to the pool rather than closing the physical socket in every case.

Therefore, all three separate lifecycles must be tracked:

1. ApplicationContext / EntityManagerFactory.
2. EntityManager / persistence context.
3. JDBC connection / connection pool.

Closing EntityManager at the right time allows the provider to release the persistence context and associated connections. Closing the EMF at the right time releases provider infrastructure. The connection pool has its own configuration for size, timeouts, idle lifetime, and leak detection.

## 8. Flush, Commit, and When Data Is Written

Flush and commit are not the same operation:

- **Flush** synchronizes changes managed by the persistence context into SQL INSERT/UPDATE/DELETE statements sent to the database.
- **Commit** confirms the transaction and makes changes durable according to the database's transaction semantics.
- **Rollback** aborts uncommitted database changes; it cannot turn an already-committed transaction into an uncommitted one.

JPA has two common flush modes:

- `FlushModeType.AUTO`: the provider must ensure queries see relevant pending changes; the provider may flush before a query.
- `FlushModeType.COMMIT`: the provider may defer flushing until commit, though applications should not rely on every query seeing unflushed changes in the same way.

You can call `entityManager.flush()` to request early synchronization, for example to detect constraint violations before leaving a block of logic. Flush does not commit the transaction; constraint errors may surface at flush or at commit.

Example:

```java
@Transactional
public Long createProduct(String name) {
    Product product = new Product(name);
    entityManager.persist(product);
    entityManager.flush();

    // After flush, the database-assigned ID is usually available.
    // The transaction has not committed at this line yet.
    return product.getId();
}
```

There is no need to call flush after every change. Calling it too often can increase round trips. Let transaction commit flush automatically unless there is a specific reason to synchronize early.

## 9. Spring Transactions and EntityManager

### 9.1. JpaTransactionManager

In a Spring application using one EntityManagerFactory for one DataSource, `JpaTransactionManager` is the common transaction manager. It:

- Starts a transaction for the EntityManager.
- Binds the EntityManager to the current transaction.
- Coordinates with JDBC operations on the same DataSource when configured appropriately.
- Executes commit or rollback.
- Closes/releases the EntityManager when the transaction ends.

`@Transactional` is typically placed at service boundaries so multiple repository operations participate in the same transaction:

```java
@Service
public class CheckoutService {

    private final OrderRepository orderRepository;
    private final InventoryRepository inventoryRepository;

    public CheckoutService(
            OrderRepository orderRepository,
            InventoryRepository inventoryRepository) {
        this.orderRepository = orderRepository;
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void checkout(Order order) {
        orderRepository.save(order);
        inventoryRepository.reserve(order.getItems());
    }
}
```

If `reserve` throws a runtime exception and the exception propagates past the transaction boundary, the transaction rolls back by default according to Spring's rollback rules. Rollback rules can be further configured for checked exceptions using `rollbackFor`.

### 9.2. Transaction Propagation

When one transactional method calls another transactional method, propagation determines which transaction they use:

- `REQUIRED` (default): joins the current transaction; creates a new one if none exists.
- `REQUIRES_NEW`: suspends the current transaction and creates a new transaction.
- `SUPPORTS`: joins if one exists; otherwise runs without a transaction.
- `MANDATORY`: requires an existing active transaction.
- `NOT_SUPPORTED`: runs without a transaction and suspends any current transaction.
- `NEVER`: requires that no transaction exists.
- `NESTED`: uses a nested transaction/savepoint if supported by the transaction manager.

Propagation affects when a persistence context is bound and ended. In particular, `REQUIRES_NEW` can create a new EntityManager/transaction while the outer context is suspended. Do not use propagation merely to patch a lazy loading error without understanding data boundaries.

### 9.3. Thread-Bound Behavior and Async

In common imperative usage, Spring binds the transaction and EntityManager to the current thread. Do not pass an EntityManager or managed entity proxy to another thread, `@Async`, an executor, or a callback running after the transaction has ended and expect them to continue working.

For asynchronous tasks, pass IDs or required data, then open a new transaction in the worker thread. If multiple transactions are needed, place clear transaction boundaries at each step.

JPA/JDBC is blocking. JPA `@Transactional` does not automatically become a reactive transaction, and EntityManager should not be used inside a reactive event loop as a non-blocking API.

## 10. Open EntityManager in View (OSIV)

Open EntityManager in View is a mechanism that keeps the EntityManager open throughout the lifecycle of an HTTP request, typically via a filter/interceptor. Its historical purpose was to allow views or serialization to access lazy relations after the service transaction has ended.

The advantage is reducing lazy loading errors surfacing in the web layer. Disadvantages:

- SQL can be issued during response serialization, outside the service transaction.
- N+1 queries can be hidden and harder to observe.
- The presentation layer inadvertently depends on the persistence layer.
- Requests hold the EntityManager longer than the business transaction.
- Data loading is no longer centralized at the service boundary.

A more controllable design is to disable OSIV and load required data inside the service transaction using projections, DTOs, fetch joins, or entity graphs. Once the service returns, return a complete DTO rather than serializing an entity graph with lazy relations.

OSIV is not synonymous with an extended persistence context. OSIV typically keeps an EntityManager for the HTTP request lifecycle; an extended persistence context is a type of persistence context with a scope longer than a transaction under JPA semantics.

## 11. Multiple Persistence Units and Choosing the Right Context

In an application with multiple databases or multiple entity groups, three mappings must be controlled:

1. Which repository package uses which EntityManagerFactory.
2. Which entity packages are managed by which factory.
3. Which transactional service uses which transaction manager.

A repository scanned under the wrong factory configuration can cause unmanaged entity errors, queries hitting the wrong database, or transactions failing to cover the intended operations.

Example using unit name:

```java
@PersistenceContext(unitName = "orders")
private EntityManager ordersEntityManager;
```

And a specific transaction manager:

```java
@Transactional("ordersTransactionManager")
public void updateOrder(...) {
    // Operations using the orders persistence unit.
}
```

The qualifier name must match the actual transaction manager bean. When using multiple transaction managers, do not rely on Spring guessing the right database from the repository name.

A local transaction on database A and a local transaction on database B are two independent transactions. If the second step fails after the first step has committed, data can become inconsistent. Options include JTA/XA when appropriate, saga/outbox, or business compensation workflows.

## 12. Memory and Performance Control

The persistence context retains managed entities and snapshots needed for dirty checking. Therefore:

- Overly long transactions can keep many entities in memory and hold connections too long.
- Loading tens of thousands of entities and keeping them all managed increases dirty checking overhead.
- Batch inserts/updates should consider periodic flush and clear.
- `clear()` detaches all entities; old references become detached afterward. Do not continue modifying them expecting dirty checking to write the data.
- Do not call `clear()` arbitrarily in the middle of logic that relies on keeping entities managed.
- EntityManagerFactory should be reused; recreating EMF repeatedly wastes metadata, caches, and provider resources.
- The connection pool should be tuned to actual workload; increasing connection counts does not automatically speed up the database.

Example of batch processing in chunks:

```java
@Transactional
public void importProducts(List<ProductInput> inputs) {
    int batchSize = 50;

    for (int i = 0; i < inputs.size(); i++) {
        entityManager.persist(new Product(inputs.get(i).name()));

        if ((i + 1) % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }
}
```

After `clear()`, the newly persisted entities are no longer managed in the persistence context, but the flushed SQL statements remain within the transaction and are not committed until the transaction completes. Optimal batch size depends on the database, JDBC driver, provider, and batching configuration.

## 13. Common Errors and Troubleshooting

| Symptom | Possible Cause | Inspection Approach |
|---|---|---|
| `No EntityManager with actual transaction available` | Code requires a transaction but runs outside one or uses the wrong transaction manager | Check `@Transactional`, proxy boundaries, propagation, and transaction manager |
| `LazyInitializationException` | Accessing a lazy relation when the persistence context is closed | Load relations inside the service transaction, use DTOs/projections, or an appropriate fetch plan |
| `Not an entity` / `Unknown entity` | Entity is outside package scan or in the wrong persistence unit | Check `@Entity`, `@EntityScan`, `packagesToScan`, unit name, and mapping |
| Entity modified but database not updated | Entity is detached, outside persistence context, or transaction rolled back | Check entity state, merge/save usage, and transaction outcome |
| `EntityManager is closed` | Using a closed reference or manually closing a container-managed EntityManager | Do not call close on injected EntityManager; check manually managed lifecycle |
| Wrong EntityManagerFactory injected | Multiple persistence units without `unitName` or wrong repository ref | Check EMF configuration, `@EnableJpaRepositories`, and qualifiers |
| Connection pool exhausted | Long transactions, leaks, slow queries, or pool too small for load | Check transaction duration, slow queries, pool metrics, and leak detection |
| Memory growth during data import | Persistence context accumulates too many managed entities | Split into batches, flush/clear appropriately, and avoid oversized transactions |
| SQL executes after service returns | OSIV or lazy loading in the web layer | Disable OSIV and complete response data at the service boundary |

Some errors may occur at flush or commit rather than on the line calling `persist`. Read the root cause in the exception chain and check SQL/transaction logs to pinpoint the actual timing.

## 14. Procedure for Debugging a Lifecycle Issue

When suspecting an EntityManager or connection is held too long, check in order:

1. Identify the persistence unit and EntityManagerFactory used by the repository/service.
2. Identify the transaction manager applied to the method.
3. Verify whether the method actually runs through a Spring proxy or is bypassed by self-invocation.
4. Check where the transaction starts/ends, which propagation is used, and whether an exception causes a rollback.
5. Determine whether the EntityManager is an injected shared proxy or created via `createEntityManager()`.
6. Search for calls to `close()`, `clear()`, `flush()`, and async tasks using entities after the transaction.
7. Check OSIV, lazy loading, and queries triggered in controllers/serializers.
8. Observe the connection pool, connection hold time, slow queries, and transaction duration.

Do not conclude there is a connection leak solely because the EntityManager proxy still exists in a singleton service field. The proxy lives with the bean, whereas the real EntityManager is resolved per transaction and released according to its lifecycle.

## 15. Design Checklist

- [ ] Each persistence unit has an explicitly defined name, entity group, DataSource, and provider.
- [ ] EntityManagerFactory is created once per unit and managed by the Spring container.
- [ ] Business code uses `@PersistenceContext` to obtain an EntityManager reference.
- [ ] `@PersistenceUnit` is used only when EntityManagerFactory is needed or manual EntityManager creation is required.
- [ ] Manually created EntityManager instances are always closed; injected EntityManager instances are never closed manually.
- [ ] Transaction boundaries reside at the service layer and select the right transaction manager.
- [ ] Real EntityManager instances or managed entities are never shared across threads.
- [ ] Persistence contexts default to transaction-scoped; extended contexts are used only when a lifecycle owner is explicitly designed.
- [ ] Flush is used intentionally; flush is not confused with commit.
- [ ] OSIV is deliberately evaluated; response data is loaded inside transactions whenever possible.
- [ ] Multiple persistence units have accurate repository scan, EMF, and transaction manager mappings.
- [ ] Connection pool, transaction duration, query count, and persistence context size are monitored.

## 16. Conclusion

A persistence unit defines the JPA configuration scope. EntityManagerFactory is created from a unit and serves as an application-level shared factory. EntityManager works with a persistence context, typically transaction-scoped in Spring applications. `@PersistenceContext` provides a Spring-managed EntityManager reference; `@PersistenceUnit` provides the EntityManagerFactory.

In standard Spring Data JPA applications, let Spring manage the EMF, EntityManager, and transactions via `@Transactional`. Manually create and close an EntityManager only when intentionally choosing the application-managed model. Understanding the distinct lifecycles of the persistence unit, factory, persistence context, transaction, and connection helps prevent lazy loading errors, resource leaks, inconsistent transactions, and unexpected queries.