# Injecting EntityManager with @PersistenceContext

`EntityManager` is the central Jakarta Persistence API for working with the persistence context: finding entities, creating queries, saving new entities, deleting entities, synchronizing changes, and managing managed/detached states. In a Spring Data JPA custom repository or DAO, you can inject `EntityManager` using the standard `@PersistenceContext` annotation.

In Spring applications, the key point is that the injected object is usually a **shared EntityManager proxy**. This proxy delegates calls to the `EntityManager` bound to the current transaction. As a result, a singleton DAO can hold a reference to the proxy without sharing the same real `EntityManager` across concurrent requests.

This lesson uses Spring Boot 3.x, Spring Framework 6.x, Spring Data JPA 3.x, Jakarta Persistence, and Java 17+. With Spring Boot 2.x, annotation imports belong to the `javax.persistence` namespace; starting with Spring Boot 3.x, they move to `jakarta.persistence`. Do not mix the two namespaces in the same application.

## 1. EntityManager and the Persistence Context

`EntityManager` provides the API to interact with the persistence context. The persistence context tracks managed entities and their state changes.

An entity is typically in one of the following states:

| State | Meaning |
|---|---|
| New / transient | A new object, not yet managed by a persistence context and with no corresponding database record |
| Managed / persistent | Entity is managed by a persistence context; changes can be written to the database by dirty checking |
| Detached | Entity has an identity but no longer belongs to the current persistence context |
| Removed | Entity is marked for deletion; the DELETE statement is synchronized on flush/commit |

Within a single persistence context, each entity type and primary key has only one corresponding managed instance. Consequently, calling `find()` twice with the same ID inside the same persistence context normally returns the same managed instance.

`EntityManager` is not a simple stateless DAO. It holds persistence context state and must not be shared directly across concurrent threads. Jakarta Persistence requires each application-managed `EntityManager` to serve only one unit of work at a time.

## 2. What Is @PersistenceContext?

`@PersistenceContext` is a Jakarta Persistence annotation used to declare an injection point for an `EntityManager` and its corresponding persistence context:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;

@Repository
public class PersonDao {

    @PersistenceContext
    private EntityManager entityManager;
}
```

Key points to remember:

- Import the annotation from `jakarta.persistence` in Spring Boot 3.x.
- Place the annotation on a field or setter method.
- Do not place `@PersistenceContext` directly on a constructor; it is not a constructor-injection annotation.
- If the application has only one persistence unit, `unitName` can usually be omitted.
- By default, the persistence context type is `TRANSACTION`.

In a Spring Boot application with the JPA starter and standard JPA configuration, Spring handles this annotation automatically. In plain Spring configurations, `PersistenceAnnotationBeanPostProcessor` is required to process `@PersistenceContext` and `@PersistenceUnit` injection points.

## 3. Shared EntityManager Proxy in Spring

An important detail of Spring ORM is that an `EntityManager` injected via `@PersistenceContext` is normally a shared proxy, not a single real `EntityManager` created once and shared across all requests.

The Spring proxy routes calls to the `EntityManager` bound to the current transaction. When a service starts a transaction with `@Transactional`, `JpaTransactionManager` binds the appropriate `EntityManager` to that transaction/thread. A DAO using the proxy participates in the same persistence context.

```java
@Repository
public class PersonDao {

    @PersistenceContext
    private EntityManager entityManager;

    public Person findById(Long id) {
        return entityManager.find(Person.class, id);
    }
}
```

When multiple requests call the same `PersonDao` bean, each request can participate in its own transaction and persistence context. The proxy reference is the shared object; the underlying real `EntityManager` is selected by Spring according to the active transaction.

Never infer that a real `EntityManager` can be shared across threads simply because the field is injected into a singleton. Thread safety comes from the proxy and Spring's transaction-bound mechanism.

### 3.1. When There Is No Active Transaction

With Spring's shared `EntityManager` proxy, if no `EntityManager` is bound to the current transaction, the proxy may create a temporary `EntityManager` per operation and close it afterward. Entities returned in that case can quickly become detached.

Operations requiring a transaction—such as `persist()`, `remove()`, or `flush()`—cannot be executed arbitrarily outside a transaction and may throw `TransactionRequiredException`.

Therefore, for multi-step read/write business operations, place the transaction at the service or appropriate custom repository method rather than relying on standalone operations outside a transaction.

## 4. Integrating with a Custom Repository Fragment

A common scenario is when Spring Data query methods are not flexible enough, such as requiring the Criteria API, dynamic queries, or specialized handling. You can create a custom repository fragment and inject `EntityManager` into its implementation.

Fragment interface:

```java
public interface PersonSearchRepository {

    List<Person> searchByNamePrefix(String prefix);
}
```

Implementation following the `Impl` suffix convention:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;
import java.util.List;
import java.util.Locale;

public class PersonSearchRepositoryImpl
        implements PersonSearchRepository {

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    public List<Person> searchByNamePrefix(String prefix) {
        if (prefix == null || prefix.isBlank()) {
            return List.of();
        }

        String normalized = prefix.trim().toLowerCase(Locale.ROOT);

        TypedQuery<Person> query = entityManager.createQuery(
            """
            select p
            from Person p
            where lower(p.name) like :prefix
            order by p.name asc, p.id asc
            """,
            Person.class
        );

        return query
            .setParameter("prefix", normalized + "%")
            .getResultList();
    }
}
```

Main repository composing the fragment:

```java
public interface PersonRepository
        extends JpaRepository<Person, Long>, PersonSearchRepository {
}
```

Spring Data composes the fragment implementation into the repository based on the interface name and implementation naming convention. For the `PersonSearchRepository` interface, the default class is `PersonSearchRepositoryImpl`. If the project changes the postfix or uses another fragment configuration, follow the project's repository configuration.

JPQL examples should reference Java entity names and properties (`Person`, `name`, `id`), not physical table/column names. The `prefix` value is bound using a named parameter; do not concatenate input strings directly into JPQL.

If a custom DAO is a standalone Spring bean rather than a repository fragment, you can annotate the class with `@Repository` to register the bean and opt into Spring's exception translation mechanism.

## 5. Transactions for Custom Repositories

Transactions should be placed at the service layer wrapping a use case:

```java
@Service
public class PersonSearchService {

    private final PersonRepository repository;

    public PersonSearchService(PersonRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public List<Person> search(String prefix) {
        return repository.searchByNamePrefix(prefix);
    }
}
```

In this flow:

1. The caller invokes the service through the Spring proxy.
2. The transaction interceptor opens or joins a transaction.
3. `JpaTransactionManager` binds an `EntityManager` to the current transaction.
4. The custom repository uses the shared `EntityManager` proxy.
5. The query call is forwarded to the `EntityManager` bound to the transaction.
6. The transaction ends when the service method completes or throws an error requiring rollback.

You can place `@Transactional` on the custom repository's implementation method if that is the appropriate boundary. However, service-level transactions usually express multi-repository use cases more clearly.

### 5.1. Self-Invocation and Transaction Proxies

In Spring's default proxy mode, an internal call from one method to another within the same object bypasses the proxy. For example, if method A calls method B directly in the same class, `@Transactional` on B may not take effect as expected.

For transactions to work as designed, call transactional methods through a Spring-managed bean/proxy, or reorganize service boundaries. Do not instantiate a DAO manually with `new`, because that object is not managed by Spring and injection/transaction annotations may not be processed.

## 6. Common EntityManager Operations

### 6.1. `find()`: Look Up by Primary Key

```java
Person person = entityManager.find(Person.class, 10L);
```

`find()` returns the entity if found or `null` if absent. The returned entity is managed in the current persistence context.

### 6.2. `getReference()`: Obtain a Reference by ID

```java
Person reference = entityManager.getReference(Person.class, 10L);
```

`getReference()` may return a proxy/reference without immediately loading all data. If the entity does not exist, an error may only surface when the proxy is accessed or when the provider needs to verify existence. Use it when you need an entity reference by ID—for instance, setting a relationship—and do not need to read the entity's fields immediately.

Do not use `getReference()` as a way to verify with certainty that an ID exists.

### 6.3. `persist()`: Add a New Entity to the Persistence Context

```java
Person person = new Person();
person.setName("Lan");

entityManager.persist(person);
```

`persist()` is for new entities. The entity becomes managed; the INSERT is synchronized at flush or commit depending on the provider/ID generation strategy. Do not use `persist` to update a detached entity.

### 6.4. `merge()`: Merge Detached State

```java
Person managed = entityManager.merge(detachedPerson);
```

`merge()` copies the state of the passed-in object onto a managed instance with the same identity or creates a corresponding managed instance. The new return value is the managed instance to continue using.

The passed-in object does not automatically become managed just by calling `merge`. Therefore, write:

```java
Person managed = entityManager.merge(detachedPerson);
managed.setName("New name");
```

Do not assume the `detachedPerson` object itself has been re-attached.

### 6.5. `remove()`: Mark an Entity for Deletion

```java
Person managed = entityManager.find(Person.class, id);

if (managed != null) {
    entityManager.remove(managed);
}
```

`remove()` requires a managed entity. If you hold a detached entity, find the managed entity again or merge it according to business logic, then remove the managed instance. The DELETE statement is synchronized on flush/commit.

### 6.6. `refresh()`: Reload State from the Database

```java
entityManager.refresh(person);
```

`refresh()` overwrites the current state of a managed entity with state from the database. Unflushed changes on the object may be lost. Use it only when you genuinely need to re-read fresh state from the database.

### 6.7. `detach()` and `clear()`

```java
entityManager.detach(person); // Detach a single entity
entityManager.clear();        // Detach all entities in the context
```

After `detach`/`clear`, changes to Java objects are no longer synchronized automatically by dirty checking. `clear()` affects every managed entity in the current persistence context, so exercise caution if the service still uses other entities.

## 7. Dirty Checking: There Is No `update()` Method

JPA does not require calling `update()` for a managed entity. When you modify properties of a managed entity, the provider tracks the state and synchronizes changes on flush/commit.

```java
@Transactional
public void renamePerson(Long id, String newName) {
    Person person = entityManager.find(Person.class, id);

    if (person == null) {
        throw new PersonNotFoundException(id);
    }

    person.setName(newName);
    // Dirty checking detects the change and writes an UPDATE on flush/commit.
}
```

Calling `merge(person)` is unnecessary in this example because `person` is already managed. Redundant `merge` calls make code harder to understand and add overhead.

If an entity was loaded in another transaction or received from a request as a detached object, define how updates should happen explicitly. Never merge an entire client-submitted entity directly if doing so could overwrite sensitive fields or state the client is not authorized to change. Usually, load the managed entity and apply only the allowed fields from a DTO.

## 8. `flush()` Is Not `commit()`

`flush()` instructs the persistence provider to synchronize pending changes in the persistence context to the database:

```java
entityManager.persist(person);
entityManager.flush();
```

After a flush, SQL may have been sent and constraints may have been checked, yet the transaction has not committed. A transaction can flush multiple times before committing or rolling back.

Distinctions:

| Action | Meaning |
|---|---|
| Modify a managed entity | Updates state in the persistence context |
| `flush()` | Synchronizes pending changes with the database in the current transaction |
| `commit` | Confirms the transaction via the transaction manager |
| `rollback` | Discards changes belonging to the uncommitted transaction |

Do not call `entityManager.getTransaction().begin()` or `commit()` in a Spring application using `@Transactional` and `JpaTransactionManager`. Let Spring manage transactions. `getTransaction()` is for manual resource-local transaction management with an application-managed `EntityManager` in specialized scenarios.

## 9. Creating JPQL Queries with EntityManager

When pre-declared repository methods are not flexible enough, you can create typed JPQL queries:

```java
TypedQuery<Person> query = entityManager.createQuery(
    """
    select p
    from Person p
    where p.active = :active
      and p.city = :city
    order by p.name asc, p.id asc
    """,
    Person.class
);

List<Person> people = query
    .setParameter("active", true)
    .setParameter("city", "Da Nang")
    .getResultList();
```

JPQL uses Java entities and properties. Use `TypedQuery<T>` to obtain a clear result type and avoid casting from `Query`/`Object`.

If at most one result is expected, you can use `getSingleResult()`, though you must handle `NoResultException` and `NonUniqueResultException`. For search queries that may yield no data, `getResultList()` is often easier to handle because it returns an empty list.

### 9.1. Bind Parameters, Do Not Concatenate Strings

Safe:

```java
query.setParameter("city", city);
```

Unsafe:

```java
String jpql = "select p from Person p where p.city = '"
        + city + "'";
```

Binding parameters prevents input data from being interpreted as query syntax. Entity/property names in JPQL must remain under code control; parameters are only for values.

## 10. Pagination with EntityManager

You can paginate a `TypedQuery` using `setFirstResult()` and `setMaxResults()`:

```java
TypedQuery<Person> query = entityManager.createQuery(
    """
    select p
    from Person p
    where p.active = :active
    order by p.id asc
    """,
    Person.class
);

List<Person> page = query
    .setParameter("active", true)
    .setFirstResult(0)
    .setMaxResults(20)
    .getResultList();
```

`setFirstResult` takes a 0-based offset; `setMaxResults` sets the maximum number of rows. Given a page number and page size, the offset is usually computed as `pageNumber * pageSize`. Enforce limits on page size and offset at the API/service layer, especially for very deep pages.

If you need to return a `Page` with the total record count, you must run a corresponding count query or use Spring Data repository pagination. `EntityManager` does not produce a total count from the content query alone.

## 11. Multi-Persistence-Unit and `unitName`

An application may have multiple persistence units—for example, order data and reporting data residing in two separate databases. In that case, specify the persistence unit explicitly:

```java
@PersistenceContext(unitName = "ordersPU")
private EntityManager ordersEntityManager;

@PersistenceContext(unitName = "reportingPU")
private EntityManager reportingEntityManager;
```

`unitName` is the persistence unit name provided by the configured `EntityManagerFactory`; it is not implicitly the field name, repository name, or Spring bean name. If there is only one persistence unit, this attribute can usually be omitted.

With Spring Boot/Spring Data JPA, each persistence unit typically needs an appropriate `EntityManagerFactory` and transaction manager. Corresponding repositories must be configured to use the right factory/transaction manager, such as via `entityManagerFactoryRef` and `transactionManagerRef` in `@EnableJpaRepositories`.

Do not inject the `EntityManager` of database A by mistake and operate on entities belonging to persistence unit B. Each `EntityManager` manages only the entities belonging to the persistence unit associated with its factory.

## 12. Difference Between @PersistenceContext and @PersistenceUnit

The two annotations serve different purposes:

| Annotation | Injects | When to Use |
|---|---|---|
| `@PersistenceContext` | `EntityManager` | Querying and managing entities in a persistence context |
| `@PersistenceUnit` | `EntityManagerFactory` | When you need to create an application-managed `EntityManager` or access the factory |

Example:

```java
@PersistenceUnit
private EntityManagerFactory entityManagerFactory;
```

In regular Spring applications, prefer `@PersistenceContext` for DAOs/custom repositories so they participate in Spring-managed transactions. Calling `entityManagerFactory.createEntityManager()` creates an application-managed `EntityManager`; the caller must manage transactions and close the `EntityManager` properly.

Manual management example solely to illustrate the lifecycle:

```java
EntityManager em = entityManagerFactory.createEntityManager();

try {
    EntityTransaction transaction = em.getTransaction();
    transaction.begin();

    // Perform work with em.

    transaction.commit();
} catch (RuntimeException exception) {
    if (em.getTransaction().isActive()) {
        em.getTransaction().rollback();
    }
    throw exception;
} finally {
    em.close();
}
```

Do not apply this pattern to the `EntityManager` proxy injected via `@PersistenceContext`. Never call `close()` on the shared `EntityManager` proxy and never manually manage Spring-controlled transactions.

## 13. Field Injection vs. Setter Injection

Field injection is concise:

```java
@PersistenceContext
private EntityManager entityManager;
```

Setter injection:

```java
private EntityManager entityManager;

@PersistenceContext
public void setEntityManager(EntityManager entityManager) {
    this.entityManager = entityManager;
}
```

Setter injection is useful if additional processing is needed when the dependency is assigned, though most DAOs only need field injection. `@PersistenceContext` does not target constructors; if constructor injection is desired, you can register the shared proxy as a Spring bean.

Example creating a proxy bean:

```java
@Configuration
public class JpaSharedEntityManagerConfiguration {

    @Bean
    public EntityManager sharedEntityManager(EntityManagerFactory emf) {
        return SharedEntityManagerCreator.createSharedEntityManager(emf);
    }
}
```

This bean can then be constructor-injected by type/qualifier. With multiple persistence units, create a corresponding proxy for each `EntityManagerFactory` and use `@Qualifier` explicitly. Do this only when the project genuinely requires constructor injection for `EntityManager`; `@PersistenceContext` remains the standard and simpler way for JPA DAOs.

## 14. PersistenceContextType.TRANSACTION vs. EXTENDED

Default:

```java
@PersistenceContext(type = PersistenceContextType.TRANSACTION)
private EntityManager entityManager;
```

A transaction-scoped persistence context is bound to the current transaction. When the transaction ends, entities belonging to that context become detached.

`PersistenceContextType.EXTENDED` has a lifetime longer than a single transaction:

```java
@PersistenceContext(type = PersistenceContextType.EXTENDED)
private EntityManager entityManager;
```

An extended persistence context is not the default choice for Spring singleton services/DAOs. It retains state across multiple transactions and is not thread-safe; use it only in components with strictly controlled lifecycle and concurrency, such as an appropriate stateful conversation. Never place an extended `EntityManager` in a singleton bean accessed concurrently by multiple requests.

For standard stateless web applications, use the default `TRANSACTION` type.

## 15. Synchronization and Properties

Jakarta Persistence also allows configuring:

- `synchronization`: whether the persistence context joins transaction synchronization automatically or requires calling `joinTransaction()` in appropriate cases.
- `properties`: configuration properties for the container/provider.
- `unitName`: selects the persistence unit.
- `type`: selects transaction-scoped or extended.

Declarative example:

```java
@PersistenceContext(
    unitName = "ordersPU",
    type = PersistenceContextType.TRANSACTION
)
private EntityManager entityManager;
```

In typical Spring Boot applications, leaving `synchronization` and `properties` at their defaults is usually sufficient. Only change them when you understand transaction types, JTA/resource-local modes, the provider, and how Spring configures `EntityManagerFactory`. Do not use annotation properties as a substitute for general datasource or transaction manager configuration.

## 16. Common Errors When Injecting EntityManager

| Symptom | Common Cause | Resolution |
|---|---|---|
| `EntityManager` is `null` | Class instantiated with `new` or not managed by Spring container | Let Spring create the bean and handle injection |
| `EntityManagerFactory` not found | Missing JPA or datasource dependencies/config | Check starter, `DataSource`, and JPA auto-configuration |
| `@PersistenceContext` not recognized | Missing persistence annotation post-processor in manual Spring config | Register `PersistenceAnnotationBeanPostProcessor` or use appropriate JPA config |
| `ClassNotFoundException javax.persistence` | Old namespace used in Spring Boot 3 | Switch to `jakarta.persistence` |
| Cannot constructor-inject | `@PersistenceContext` only supports fields/methods | Use field/setter or register a `SharedEntityManagerCreator` bean |
| No qualifying `EntityManagerFactory` with multiple DBs | Ambiguous persistence unit | Specify `unitName` and configure corresponding factory/transaction manager |
| `TransactionRequiredException` on `persist`/`remove`/`flush` | No active transaction | Place `@Transactional` on service/repository and check transaction manager |
| `LazyInitializationException` | Accessing lazy association after persistence context closes | Read data inside transaction or use fetch plan/DTO |
| Returned entity is already detached | Entity loaded outside transaction or transaction already ended | Complete operations in transaction; return DTOs if independent data is needed |
| Stale data after native/bulk DML | Persistence context still holds previously loaded entities | Flush before if needed, then clear/refresh intentionally |
| `ConcurrentModification` or unpredictable state | Real `EntityManager` shared across threads | Use Spring's shared proxy; never share an application-managed EM |
| Closing `EntityManager` breaks subsequent operations | Calling `close()` on injected proxy | Never close an `EntityManager` from `@PersistenceContext` |
| Entity changes are not saved | Entity detached or missing transaction/dirty checking | Load managed entity inside transaction or merge and use the returned instance |

## 17. Testing Custom Repositories Using EntityManager

You can use `@DataJpaTest` to test custom fragments and queries:

```java
@DataJpaTest
class PersonSearchRepositoryTest {

    @Autowired
    PersonRepository repository;

    @Test
    void searchesPeopleByNamePrefix() {
        Person lan = new Person();
        lan.setName("Lan");

        Person linh = new Person();
        linh.setName("Linh");

        Person minh = new Person();
        minh.setName("Minh");

        repository.saveAll(List.of(lan, linh, minh));
        repository.flush();

        List<Person> result =
            repository.searchByNamePrefix("L");

        assertThat(result)
            .extracting(Person::getName)
            .containsExactly("Lan", "Linh");
    }
}
```

This is an illustrative test skeleton; the `Person` entity needs matching constructors/accessors and constraints. The test verifies that Spring Data composes the fragment into the repository and the custom query executes via the injected `EntityManager`.

Consider adding tests for:

- `null` or blank prefix according to API policy.
- Parameters containing special characters to verify parameter binding works.
- Empty result returning an empty list.
- Stable sorting when results may have duplicate names.
- Transaction rollback when a use case fails.
- Multiple persistence units if the application uses multiple databases.
- Real database/Testcontainers when queries use database-specific functions or dialects.

## 18. Implementation Checklist

Before deploying a custom repository to an application:

1. Use the right namespace (`jakarta.persistence` or `javax.persistence`) for your Spring Boot version.
2. Place `@PersistenceContext` on a field or setter of a Spring-managed bean.
3. Ensure persistence units and `EntityManagerFactory` are configured.
4. Use the default transaction-scoped persistence context.
5. Place `@Transactional` at the appropriate use-case boundary.
6. Use JPQL with Java entities/properties, or native SQL when clearly justified.
7. Bind every input value using parameters.
8. Do not call `close`/`begin`/`commit` on the shared `EntityManager` proxy.
9. Do not share a real `EntityManager` across threads.
10. With multiple persistence units, specify `unitName` and transaction managers explicitly.
11. Return DTOs when data must outlive the transaction or when avoiding exposing the entity graph.
12. Test custom fragments and transactions against an appropriate database.

## 19. Official References

- [Spring Framework — JPA](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html): shared `EntityManager`, `@PersistenceContext`, `@PersistenceUnit`, transaction integration, and multiple persistence units.
- [Jakarta Persistence — PersistenceContext API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/persistencecontext): `unitName`, `type`, `synchronization`, `properties`, and annotation scope.
- [Jakarta Persistence — EntityManager API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitymanager): entity management operations, queries, `flush`, `clear`, `detach`, and persistence context lifecycle.
- [Spring Framework — JpaTransactionManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html): transaction manager binding `EntityManager` to threads and supporting the shared `EntityManager` proxy.

**Guiding principle:** use `@PersistenceContext` to inject the shared `EntityManager` proxy into a Spring-managed custom repository/DAO. The proxy participates in the current transaction's persistence context while the underlying real `EntityManager` maintains the rule of never being shared across threads. Let Spring manage transactions, never close the proxy or call `begin`/`commit` manually, and only use `EntityManagerFactory` and application-managed `EntityManager` instances when you have a dedicated, fully managed lifecycle need.