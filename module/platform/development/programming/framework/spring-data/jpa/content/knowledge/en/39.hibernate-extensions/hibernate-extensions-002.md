# Unwrapping EntityManager to Session for Specific Needs

## 1. Purpose of unwrap

Spring Data JPA encourages applications to work through repositories and Jakarta Persistence's `EntityManager`. These APIs keep code less coupled to Hibernate and make switching persistence providers easier.

However, there are needs where JPA has no equivalent API or Hibernate provides a useful specialized feature, such as:

- Running JDBC work on the exact connection currently managed by Hibernate.
- Enabling Hibernate filters or fetch profiles per Session.
- Setting entities or queries to read-only using Hibernate's mechanism.
- Using certain HQL, loading, batching, or session-specific options.
- Accessing Hibernate features without creating a second persistence context.

When such needs arise, you can obtain the Hibernate `Session` from `EntityManager`:

```java
Session session = entityManager.unwrap(Session.class);
```

This is the standard Jakarta Persistence mechanism for retrieving the provider's native API. When Hibernate is the JPA provider, the unwrapped object is the Session backing that EntityManager.

Only unwrap once you have identified a concrete Hibernate-specific feature you need. If `EntityManager`, a Spring Data repository, or `JdbcTemplate` can fulfill the requirement, stay on that API to minimize provider coupling.

## 2. How Do EntityManager and Session Relate?

### 2.1. EntityManager is the JPA API

`jakarta.persistence.EntityManager` is the standard API to:
- Persist, merge, remove, and find entities.
- Create JPQL, Criteria, and native queries.
- Flush, clear, and refresh the persistence context.
- Manage the entity lifecycle.
- Participate in transactions managed by JPA or Spring.

Example:

```java
Customer customer = entityManager.find(Customer.class, customerId);
customer.setName("New name");
entityManager.flush();
```

This code does not need to know whether the provider is Hibernate or another JPA implementation.

### 2.2. Session is Hibernate's native API

`org.hibernate.Session` is Hibernate's central API. It represents the persistence context and exposes Hibernate-specific operations.

When Hibernate is the provider, Session and EntityManager represent the same persistence context. Unwrapping does not copy entities, does not create a new persistence context, and does not reload all data.

```text
Spring @Transactional
       |
       v
Transaction-bound EntityManager
       |
       | entityManager.unwrap(Session.class)
       v
Hibernate Session
       |
       +---- Persistence Context / First-level Cache
       |
       +---- Hibernate-specific APIs
       |
       +---- Managed JDBC Connection
```

An entity loaded through EntityManager remains a managed entity when operated on via the unwrapped Session. Dirty checking, the identity map, lazy proxies, and flush still belong to the same persistence context.

### 2.3. unwrap is a JPA API

The `EntityManager.unwrap(Class<T>)` method is provided by Jakarta Persistence to access the provider's native API:

```java
Session session = entityManager.unwrap(Session.class);
```

If the provider does not support the requested type, the call can throw `PersistenceException`. Do not catch the exception and silently assume another provider behaves like Hibernate.

If an application supports multiple JPA providers, isolate Hibernate code in a dedicated adapter/service and invoke that adapter only in flows known to use Hibernate.

## 3. Unwrapping Session Inside a Spring-Managed Transaction

### 3.1. Injecting EntityManager

In Spring applications, EntityManager is typically injected via `@PersistenceContext`:

```java
@Service
public class CustomerMaintenanceService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void renameCustomer(Long customerId, String newName) {
        Session session = entityManager.unwrap(Session.class);

        Customer customer =
            session.find(Customer.class, customerId);

        if (customer == null) {
            throw new CustomerNotFoundException(customerId);
        }

        customer.setName(newName);
    }
}
```

Spring typically injects a shared EntityManager proxy. When a method runs inside a Spring-managed transaction, the proxy delegates to the EntityManager bound to the current transaction. Unwrapping within that scope retrieves the Session corresponding to the current persistence context.

The example uses `session.find()` to illustrate the native API. If no Hibernate-specific behavior is needed, use `entityManager.find()` directly in the method.

### 3.2. Do not open a second Session for the same unit of work

Do not open an independent Session with `SessionFactory.openSession()` while the current EntityManager is managed by Spring:

```java
// Do not use this approach for the same Spring-managed persistence context.
Session anotherSession = sessionFactory.openSession();
```

A new Session has its own persistence context and transaction/resource lifecycle. An entity loaded in the new Session does not automatically become a managed entity of the original EntityManager. This can cause:
- Two Java object instances for the same database row.
- Lazy proxies belonging to a different persistence context.
- Queries running on a different connection or outside the same transaction.
- Divergent data between memory and the database.
- Manual responsibility for commit, rollback, and close.

If the goal is to use Hibernate APIs within the current transaction, unwrapping Session from the injected EntityManager is the right approach.

### 3.3. Do not manually commit, rollback, or close an unwrapped Session

A Session obtained from a Spring-managed EntityManager has its lifecycle governed by Spring/JPA transaction integration. Do not invoke the following operations on a Spring-managed Session:

```java
session.beginTransaction();
session.getTransaction().commit();
session.close();
```

The Spring transaction manager is responsible for starting, committing/rolling back, and releasing resources according to configuration. Closing the Session yourself can invalidate the persistence context currently in use by the transaction.

If writing a plain Hibernate program without Spring managing the EntityManager, the lifecycle differs: the application can open a Session from SessionFactory, begin a transaction, commit/rollback, and close the Session. Do not mix the two management models in the same flow.

## 4. Using doWork and doReturningWork

### 4.1. When is JDBC work via Session needed?

Hibernate provides `doWork()` and `doReturningWork()` to run JDBC on the connection managed by the Session.

Use them when:
- You need to call a JDBC API for which Hibernate has no suitable abstraction.
- You need vendor-specific operations or stored procedures via JDBC.
- You need to use the Session's exact connection and transaction.
- You need to invoke a lower-level JDBC library within the current persistence context.

If you only need routine JDBC queries in a Spring application, `JdbcTemplate` is usually simpler. If you directly need the connection managed by the Session or tight coordination with Hibernate's persistence context, `doWork` is a better fit.

### 4.2. doWork: executing JDBC without returning a result

Example updating a database-managed column:

```java
@Transactional
public void markCustomerForReindex(Long customerId) {
    Session session = entityManager.unwrap(Session.class);

    entityManager.flush();

    session.doWork(connection -> {
        try (PreparedStatement statement =
                 connection.prepareStatement(
                     "update customer set reindex_required = ? where id = ?"
                 )) {

            statement.setBoolean(1, true);
            statement.setLong(2, customerId);
            statement.executeUpdate();
        }
    });

    entityManager.clear();
}
```

Explanation:
- `entityManager.flush()` pushes pending JPA changes to the database before direct JDBC reads or writes.
- `doWork` receives the connection managed by the Session.
- `PreparedStatement` is closed via try-with-resources.
- Do not close the connection, commit manually, or roll back manually inside the callback.
- A JDBC update does not automatically update the state of managed entities, so the example calls `clear()` to evict managed entities from the persistence context.

`clear()` affects all managed entities in the EntityManager, not just the updated Customer. If only one entity is affected and you need to continue using other entities in the transaction, you can call `refresh(customer)` on that entity after the JDBC update instead of clearing the entire context.

### 4.3. doReturningWork: executing JDBC and returning a result

Example counting orders:

```java
@Transactional(readOnly = true)
public long countOrders(Long customerId) {
    Session session = entityManager.unwrap(Session.class);

    return session.doReturningWork(connection -> {
        try (PreparedStatement statement =
                 connection.prepareStatement(
                     "select count(*) from purchase_order where customer_id = ?"
                 )) {

            statement.setLong(1, customerId);

            try (ResultSet resultSet = statement.executeQuery()) {
                resultSet.next();
                return resultSet.getLong(1);
            }
        }
    });
}
```

`doReturningWork` returns the callback result to the caller. The Statement and ResultSet are closed, while the connection remains managed by Hibernate.

### 4.4. Are connection and transaction shared?

When the Session is participating in a Spring-managed transaction, JDBC work executes on the Session's connection and coordinates with that transaction/resource integration. Do not open a new connection via `DriverManager.getConnection()` if you want to stay in the same transaction.

If you open an independent connection, that SQL may run outside the current transaction and will not see uncommitted changes. With JTA, connection handling and enlistment depend on transaction manager and data source configuration; verify the actual integration.

### 4.5. Notes when JDBC modifies data

Hibernate does not know which rows JDBC updated. After a direct JDBC write:
- Managed entities may hold stale values.
- Loaded collections may not reflect the new data.
- Second-level cache/query cache may need handling if affected entities/queries are cached.
- Bulk SQL does not trigger JPA entity lifecycle callbacks or cascades like entity operations do.

Flush before a JDBC write if consistent ordering is needed. Afterward, refresh affected entities, clear the persistence context where appropriate, and handle cache regions according to your application's policy.

## 5. Session-Scoped Hibernate Filters

### 5.1. What problem do filters solve?

A Hibernate filter enables a parameterized SQL condition for the duration of a Session. For example, a multi-tenant application can filter Customer rows by the current tenant.

Filters differ from JPQL conditions written explicitly in each repository method: a filter is enabled on the Session and can affect entities/collections loaded within that scope depending on mapping and Hibernate version.

### 5.2. Declaring a filter on an entity

Hibernate annotation example:

```java
@Entity
@Table(name = "customer")
@FilterDef(
    name = "tenantFilter",
    parameters = @ParamDef(name = "tenantId", type = Long.class)
)
@Filter(
    name = "tenantFilter",
    condition = "tenant_id = :tenantId"
)
public class Customer {

    @Id
    private Long id;

    @Column(name = "tenant_id")
    private Long tenantId;

    private String name;
}
```

`@FilterDef`, `@ParamDef`, and `@Filter` belong to Hibernate, not Jakarta Persistence. The condition uses the mapped SQL column name, not the Java field name.

### 5.3. Enabling and setting filter parameters

In a service:

```java
@Transactional(readOnly = true)
public List<Customer> findCustomersForTenant(Long tenantId) {
    Session session = entityManager.unwrap(Session.class);

    Filter filter = session.enableFilter("tenantFilter");
    filter.setParameter("tenantId", tenantId);

    try {
        return entityManager.createQuery(
            "select c from Customer c order by c.name",
            Customer.class
        ).getResultList();
    } finally {
        session.disableFilter("tenantFilter");
    }
}
```

The filter is enabled on the current Session. Set parameters before running queries. The `finally` block disables the filter when the method finishes, preventing subsequent code in the same Session from accidentally inheriting the previous condition.

In a typical Spring transaction, the Session ends with the persistence context/transaction. Still, explicitly disabling the filter makes its effective scope clearer, especially when a method invokes multiple components participating in one transaction.

### 5.4. Filters do not replace access control

Do not use Hibernate filters as the sole security boundary for multi-tenancy.

Verify:
- Is the filter enabled on every data access path?
- Does any code use native JDBC or stored procedures that bypass the filter?
- Are there paths loading entities directly by ID?
- Do background jobs, async tasks, and batch jobs open their own Sessions?
- Can caches return entities without going through filtered queries?
- Can database row-level security or repository-level tenant predicates add defense in depth?

Depending on the Hibernate version, standard filters do not necessarily apply to direct identifier loads. Newer versions offer the `applyToLoadByKey` option on `@FilterDef`; if relying on that behavior, verify your Hibernate version and test `find`/`get` by ID as well. Never assume a filter protects every API just because a JPQL query returns the expected results.

## 6. Fetch Profiles and Read-Only Mode

### 6.1. Enabling Fetch Profiles per use case

A Hibernate Fetch Profile lets you define a fetch plan and enable it on a Session when needed. Example mapping:

```java
@FetchProfile(
    name = "customer-with-orders",
    fetchOverrides = {
        @FetchProfile.FetchOverride(
            entity = Customer.class,
            association = "orders",
            mode = FetchMode.JOIN
        )
    }
)
@Entity
public class Customer {
    // entity mapping
}
```

When the profile is needed:

```java
@Transactional(readOnly = true)
public Customer loadCustomerWithOrders(Long customerId) {
    Session session = entityManager.unwrap(Session.class);
    session.enableFetchProfile("customer-with-orders");

    return entityManager.find(Customer.class, customerId);
}
```

Fetch profiles are a Hibernate-specific feature. They fit well when multiple use cases need different fetch plans and you want the default mapping to avoid loading too many associations.

If the requirement applies to a single repository query, a JPA EntityGraph or JPQL fetch join can be clearer and more portable.

### 6.2. Read-only entities

Hibernate allows marking already-loaded entities as read-only or setting read-only as the default for subsequently loaded entities:

```java
Session session = entityManager.unwrap(Session.class);
session.setDefaultReadOnly(true);

Customer customer =
    session.find(Customer.class, customerId);
```

Read-only here refers to Hibernate's dirty-checking behavior, not database permissions, and it does not replace `@Transactional(readOnly = true)`. Entities loaded before changing the default may need to be marked individually with the corresponding API such as `session.setReadOnly(entity, true)`.

Use this only when the use case is genuinely read-only and you understand the impact on flush and dirty checking. Do not set default read-only on a Session shared across both read and write flows without controlling its scope.

## 7. Other Hibernate APIs You May Need

### 7.1. Flush, clear, and detach

`Session` provides persistence-context APIs corresponding to JPA:

```java
Session session = entityManager.unwrap(Session.class);

session.flush();
session.clear();
```

If code only needs flush or clear, `EntityManager` already provides standard methods. There is no need to unwrap just to call these two operations.

Hibernate has `session.evict(entity)` to remove a specific entity from the first-level cache:

```java
session.evict(customer);
```

The equivalent JPA API is `entityManager.detach(customer)`. Unless you have another Hibernate requirement, use `detach` to preserve portability.

### 7.2. HQL and query APIs

Hibernate has its own query APIs and some HQL capabilities extending beyond JPQL. If a query uses only standard JPQL syntax, continue using `EntityManager.createQuery()` or Spring Data `@Query`.

When using Hibernate-specific syntax, document the dependency/provider requirement and test queries on the exact Hibernate version. HQL can change across major versions; avoid copying examples from 5.x documentation into 6.x/7.x projects without checking the migration guide.

### 7.3. Do not confuse Session with StatelessSession

`StatelessSession` is a separate Hibernate API for bulk data processing with different semantics from a regular Session:
- No persistence context or first-level cache in the manner of a normal Session.
- No dirty checking like managed entities.
- Different cascade/lifecycle semantics.
- Requires managing transactions and resources according to its own API.

You cannot substitute `StatelessSession` for `Session` simply by casting or unwrapping. It is a distinct architectural choice whose semantics must be verified before use.

## 8. When to Unwrap and When Not To

| Need | Preferred API | Reason |
|---|---|---|
| CRUD, find, persist, merge, remove | EntityManager/Repository | Standard JPA API |
| JPQL/Criteria queries | EntityManager | Portable across JPA providers |
| Pagination/sorting | Spring Data Pageable/Sort | Clear repository contract |
| Routine JDBC queries | JdbcTemplate | Spring manages connections and exception translation |
| JDBC on the Session's connection | Session.doWork/doReturningWork | Uses the connection managed by Hibernate |
| Hibernate filters | Session.enableFilter | No equivalent JPA API |
| Hibernate fetch profiles | Session.enableFetchProfile | Hibernate-specific feature |
| Hibernate read-only mode | Session.setDefaultReadOnly/setReadOnly | Customizes dirty checking |
| Basic flush/clear/detach | EntityManager | No unwrap required |

Practical rule: start with repositories/JPA. Unwrap only at a small boundary where a Hibernate feature is needed; do not pass Session across the entire application layer when only one adapter requires it.

## 9. Transactions, Exceptions, and Lifecycle

### 9.1. A Session lives only within its persistence context

A Hibernate Session is a short-lived object holding mutable state of the persistence context. With a Spring-managed EntityManager, a Session obtained via unwrap is valid only within the lifecycle managed by the provider/Spring.

Do not store a Session in:
- Static fields.
- Singleton caches.
- Objects retained after the transaction ends.
- Messages sent to another thread.
- Async tasks running after the transactional method finishes.

Unwrap again inside the transaction of each unit of work.

### 9.2. Session is not thread-safe

Do not use the same Session concurrently from multiple threads. EntityManager is also not thread-safe under the JPA contract.

Unsafe example:

```java
Session session = entityManager.unwrap(Session.class);

executor.submit(() -> session.find(Customer.class, 1L));
executor.submit(() -> session.find(Customer.class, 2L));
```

Both tasks may concurrently access the persistence context and connection state. Each thread/transaction must have its own persistence context created by Spring for that thread; never pass a Session from the calling thread.

### 9.3. Exception handling

If a Session throws an exception during database access, do not continue using the persistence context as if no error occurred. Hibernate recommends rolling back the transaction and discarding the Session after an exception because internal state may no longer be consistent with the database.

In Spring:
- Let appropriate exceptions propagate out of the transactional boundary.
- Configure rollback for checked exceptions if required by business logic.
- Do not catch an exception and continue writing with the same Session.
- Do not manually commit or roll back a Spring-managed Session.

### 9.4. Lazy loading and closed Sessions

Unwrapping does not extend the lifecycle of the persistence context. Once the transaction finishes and the Session closes, uninitialized lazy proxies can still throw `LazyInitializationException`.

Load required data within the transaction using an appropriate fetch plan or DTO. Do not keep a Session open longer solely so a serializer or view layer can access associations afterward.

## 10. Testing Code That Unwraps Session

### 10.1. Testing with the real provider

Tests using Hibernate must run against the actual Hibernate dependency, not just a mocked EntityManager:

```java
@DataJpaTest
class HibernateSessionIntegrationTest {

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void unwrapsTheHibernateSession() {
        Session session = entityManager.unwrap(Session.class);

        assertThat(session).isNotNull();
        assertThat(session.isOpen()).isTrue();
    }
}
```

The example requires Hibernate and AssertJ dependencies from the project's test stack. If a test slice uses a different provider or mocks EntityManager, unwrap may not behave as in production.

### 10.2. Testing JDBC work in the same transaction

An integration test should verify:
- Persisted and flushed entities are visible to JDBC work.
- JDBC writes roll back when the test transaction rolls back.
- Managed entities are refreshed or cleared after direct JDBC updates.
- The connection is not closed by the callback.
- Exceptions from JDBC work trigger proper transaction handling.

For database-specific SQL, use Testcontainers running the exact PostgreSQL/MySQL engine used in production. H2 is insufficient to confirm every dialect or stored procedure behavior.

### 10.3. Testing filters and fetch profiles

For filters:
- Create data for at least two tenants.
- Enable the filter for tenant A and verify only tenant A's data appears.
- Disable the filter and verify default behavior.
- Test lookup by ID/direct load according to the exact Hibernate version.
- Verify that native JDBC paths do not automatically receive the filter.

For fetch profiles:
- Confirm associations are loaded according to the profile.
- Use SQL capture or Hibernate statistics to inspect queries.
- Verify the returned data is identical whether the profile is enabled or disabled.
- Check that the profile does not remain active outside the intended use case.

## 11. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| `unwrap(Session.class)` throws PersistenceException | Current provider is not Hibernate or does not expose the requested type | Check JPA provider and isolate Hibernate code |
| Session is already closed when calling a method | Using Session outside transaction/persistence context | Unwrap inside a transactional method |
| Entity loaded twice or two objects for same ID | Opening a second Session via `SessionFactory.openSession()` | Use the Session unwrapped from the current EntityManager |
| Connection closes unexpectedly | Code closes the connection passed to doWork | Close only Statement/ResultSet; let Hibernate manage the connection |
| JDBC does not see recent JPA changes | Persistence context has not flushed | Call flush before JDBC work |
| In-memory entity holds stale data after JDBC update | Hibernate does not know direct JDBC modified the row | Refresh the entity or clear the persistence context |
| Transactions are out of sync | JDBC opens its own connection | Use doWork or JdbcTemplate sharing the DataSource transaction |
| Filter does not apply to ID lookup | Filter behavior for direct load differs from regular queries | Check `applyToLoadByKey` and Hibernate version |
| Tenant data leaks through native SQL | Hibernate filters do not automatically filter arbitrary JDBC SQL | Add tenant predicates or DB row-level security |
| LazyInitializationException | Session ended before loading association | Fetch data within the transaction |
| Intermittent session errors under concurrency | Sharing a Session across multiple threads | Each thread/transaction must have its own persistence context |
| Inconsistent Session after exception | Continuing to use Session after a database error | Roll back and discard the persistence context |

## 12. Decision Process Before Unwrapping

1. Determine whether the requirement truly needs a Hibernate-specific feature.
2. Check whether EntityManager, Spring Data repositories, or JdbcTemplate can meet it.
3. Ensure the method runs within an appropriate transaction/persistence context.
4. Call `entityManager.unwrap(Session.class)` at the exact boundary where it is needed.
5. Never open, close, or manually commit a Spring-managed Session.
6. For JDBC, use connection callbacks and close statements/result sets.
7. Flush before JDBC needs to read pending changes; refresh/clear after JDBC writes.
8. For filters/fetch profiles, enable them in an explicit Session scope and disable them when done if needed.
9. Never share a Session across threads or retain it past the transaction.
10. Write integration tests against real Hibernate/database and verify transactions, SQL, cache, and filters.

## 13. Code Review Checklist

- [ ] There is a concrete reason to use Hibernate Session instead of the JPA API.
- [ ] Session is obtained via `EntityManager.unwrap(Session.class)`.
- [ ] Unwrapping occurs inside an appropriate Spring-managed transaction/persistence context.
- [ ] No second Session is opened with `SessionFactory.openSession()` for the same use case.
- [ ] No manual calls to beginTransaction/commit/rollback/close on a Spring-managed Session.
- [ ] Session is not stored in fields/statics or passed across threads.
- [ ] JDBC work uses the connection managed by the Session.
- [ ] Statements and ResultSets are closed; the connection is not closed manually.
- [ ] Flush is called before direct JDBC when data synchronization is needed.
- [ ] Refresh/clear/cache handling is performed after direct JDBC writes.
- [ ] Filters are not treated as the sole security boundary.
- [ ] Fetch profiles/filters are enabled within a clear scope.
- [ ] Exceptions lead to rollback and proper termination of the persistence context.
- [ ] Integration tests exist for the exact Hibernate version and target database.
- [ ] Hibernate-specific code is isolated for easier provider/version upgrades.

## 14. Official References

- [Hibernate ORM — Session Javadoc](https://docs.hibernate.org/orm/7.4/javadocs/org/hibernate/Session.html): Session, unwrap, lifecycle, thread-safety, and JDBC work.
- [Hibernate ORM User Guide](https://docs.hibernate.org/stable/orm/userguide/html_single/): persistence context, filters, fetch profiles, read-only state, and Session behavior.
- [Spring Framework — JPA](https://docs.spring.io/spring-framework/reference/data-access/orm/jpa.html): EntityManagerFactory, EntityManager proxies, and transaction integration in Spring.
- [Jakarta Persistence — EntityManager API](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/entitymanager): JPA's `unwrap(Class<T>)` contract.
- [Hibernate ORM — Integrations Guide](https://docs.hibernate.org/stable/orm/integrationguide/html_single/): integrating Hibernate with transaction managers and resource lifecycles.

## 15. Conclusion

`EntityManager.unwrap(Session.class)` is the bridge from the portable JPA API to Hibernate's native API. It is useful when you need specific features such as JDBC work on the Session's managed connection, Hibernate filters, fetch profiles, or read-only behavior. Unwrapping does not create a new persistence context; the resulting Session represents the current EntityManager's persistence context.

In Spring applications, unwrap inside transactional methods and let Spring manage the lifecycle. Never manually open/close/commit the Session, never share a Session across threads, and never retain it after the transaction. When running direct JDBC, flush before reading if needed, refresh/clear after writing, and close JDBC statements/result sets while letting Hibernate manage the connection.

Keep JPA code in standard repositories/services and isolate Hibernate-specific parts only where truly needed. Test with real Hibernate and a real database—especially for filters, fetch profiles, transactions, and direct JDBC—to ensure using Session does not break data or lifecycle semantics.