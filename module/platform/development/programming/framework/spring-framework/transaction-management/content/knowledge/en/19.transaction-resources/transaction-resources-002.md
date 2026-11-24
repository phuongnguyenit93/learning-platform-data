# DataSourceUtils, EntityManagerUtils, and Transaction-Aware Access Helpers

> **Spring Framework – Transaction Management → Transaction-Bound Resources.** A Spring-managed transaction does not automatically make every JDBC `Connection` or JPA `EntityManager` in the application share the same resource. For data to commit/rollback together, data access code must acquire **the exact resource bound to the transaction**. This article explains `DataSourceUtils`, its JPA utility counterpart, `TransactionSynchronizationManager`, and abstractions such as `JdbcTemplate`, `@PersistenceContext`, and `SharedEntityManagerCreator`. At the end, there is a Java 17+ example with Spring JDBC and H2.

## 1. Objectives

After finishing this article, you should be able to:

1. Describe logical transaction scope, physical transaction, connection/entity manager, and resource binding.
2. Explain why `DataSourceUtils.getConnection(ds)` participates in the transaction, whereas `ds.getConnection()` on an ordinary pool may acquire a different connection.
3. Use the `getConnection`/`releaseConnection` pair properly and avoid accidentally closing a connection held by the manager.
4. Understand how `JdbcTemplate` uses transaction-aware mechanisms behind the scenes.
5. Distinguish the informal name "EntityManagerUtils" from Spring's actual API, `EntityManagerFactoryUtils`, along with `@PersistenceContext` and `SharedEntityManagerCreator`.
6. Diagnose `TransactionSynchronizationManager` without manually binding/unbinding resources in business code.
7. Avoid mismatched transaction managers, datasources, threads, proxies, and lifecycles when mixing JDBC and JPA.
8. Run a demo capable of verifying commit, rollback from an exception, explicit rollback-only, as well as the same JDBC path called outside a transaction.

## 2. Note on the Class Name EntityManagerUtils

In **Spring Framework 6.2**, the official JPA utility class in `org.springframework.orm.jpa` is named **`EntityManagerFactoryUtils`**, not `org.springframework.orm.jpa.EntityManagerUtils`. The phrase "EntityManagerUtils" may be used as a general expression for utilities operating on `EntityManager`, but it is **not a valid Spring 6.2 import name**.

```java
// DO NOT USE: the following intentionally illustrates an invalid import.
import org.springframework.orm.jpa.EntityManagerUtils;

// ACTUAL SPRING APIS:
import org.springframework.orm.jpa.EntityManagerFactoryUtils;
import org.springframework.orm.jpa.SharedEntityManagerCreator;
import org.springframework.jdbc.datasource.DataSourceUtils;
```

This is an example **illustrating an import error**, not a compilable source file. When writing normal JPA application code, Spring generally recommends using `@PersistenceContext` or Spring Data JPA repositories instead of calling utility classes manually.

Table of exact names and purposes:

| Technology | API | Purpose |
| --- | --- | --- |
| JDBC | `DataSourceUtils.getConnection(DataSource)` | Acquire a connection aware of the thread-bound transaction resource |
| JDBC | `DataSourceUtils.releaseConnection(Connection,DataSource)` | Return/close the connection **only when appropriate** with respect to transaction binding |
| JDBC | `JdbcTemplate` | High-level JDBC access path that manages connection/statement lifecycle automatically |
| Legacy JDBC | `TransactionAwareDataSourceProxy` | Make plain `DataSource.getConnection()` calls in legacy code aware of Spring transactions |
| JPA | `EntityManagerFactoryUtils.getTransactionalEntityManager(emf)` | Obtain the EntityManager under Spring transaction synchronization; may return `null` |
| JPA | `SharedEntityManagerCreator` | Create a shared EntityManager proxy pointing to the EntityManager appropriate for the current transaction |
| Typical JPA | `@PersistenceContext` | Inject a shared transaction-scoped EntityManager reference |
| Spring infrastructure | `TransactionSynchronizationManager` | Store the resource map and synchronization metadata for the imperative transaction context |

## 3. What Problem Does Resource Binding Solve?

Suppose a use case needs to write to two tables and roll back if an error occurs:

```java
@Transactional
public void submitOrder() {
    jdbcTemplate.update("INSERT INTO orders ...");
    customAuditDao.insert(...);
    // May throw an error after the two INSERT statements.
}
```

This is a **business fragment**: SQL and parameters are abbreviated. If `JdbcTemplate` uses connection C1 inside transaction T1 while `customAuditDao` opens connection C2 with autocommit, rolling back T1 only reverts the data on C1. The audit row on C2 may already be committed. **An annotation does not automatically combine two independent connections into a single physical transaction.**

The proper mechanism:

```text
                  Spring-managed service
                            |
                  @Transactional / txTemplate
                            |
                            v
                 PlatformTransactionManager
                            |
                       begin T1
                            |
                  ConnectionHolder(C1)
                            |
     TransactionSynchronizationManager.bindResource(ds, holder)
                            |
             +--------------+--------------+
             |                             |
       JdbcTemplate                      Custom DAO
             |                             |
       DataSourceUtils             DataSourceUtils.getConnection(ds)
             |                             |
             +------------- C1 ------------+
                            |
                       commit/rollback
                            |
              cleanup binding + release C1
```

Here, `TransactionSynchronizationManager` provides a resource map bound to the execution context of **imperative Spring transaction management**. The transaction manager uses it to bind/unbind resources and synchronize lifecycles. A DAO **should not** call `bindResource` itself or hold a `ConnectionHolder` in a shared field.

### 3.1. Logical Scope Differs from Physical Transaction

If an outer `@Transactional(REQUIRED)` calls an inner `@Transactional(REQUIRED)` through a proxy, Spring can create two logical scopes **participating in the same T1**, hence sharing the same connection/resource. With `REQUIRES_NEW`, the inner call creates an independent T2: the manager can suspend T1's binding, bind connection C2 for T2, and then restore C1 when the inner call ends.

```text
outer REQUIRED: T1, bound C1
    |
    +-- inner REQUIRES_NEW:
    |       suspend T1
    |       bound C2 for T2
    |       DataSourceUtils.getConnection(ds) -> C2
    |       commit/rollback T2
    |       resume T1
    |
    +-- DataSourceUtils.getConnection(ds) -> C1
    +-- commit/rollback T1
```

**Resource-aware** means acquiring the right resource **for the current scope**, not "always the same connection across every method on the same thread forever."

## 4. DataSourceUtils.getConnection / doGetConnection

Imports:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import org.springframework.jdbc.datasource.DataSourceUtils;
```

Call:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
```

This is a fragment with a `dataSource` variable injected or configured from Spring. Key logic:

1. The helper checks the resource holder corresponding to the **datasource key** bound to the transaction context.
2. If the holder has an appropriate JDBC connection, it returns this bound connection so subsequent SQL statements participate in the transaction.
3. If none is bound yet, the helper acquires a connection from the datasource. If synchronization is active, Spring can register a holder/callback for reuse and proper cleanup when the scope ends.
4. When there is no Spring transaction/synchronization, the helper can still acquire a normal connection for a JDBC operation.

Two variants:

- `getConnection(ds)`: translates connection acquisition failures into Spring's unchecked `CannotGetJdbcConnectionException`.
- `doGetConnection(ds)`: preserves the JDBC `SQLException` for the caller to handle.

Do not equate `DataSourceUtils.getConnection(ds)` with `DriverManager.getConnection(url)`. A `DriverManager` call does not consult the resource map managed by the Spring manager and typically creates an independent connection/transaction.

### 4.1. Is the Connection Currently Bound by Spring?

```java
boolean transactional =
    DataSourceUtils.isConnectionTransactional(connection, dataSource);
```

Fragment. A `true` status reflects that the connection is associated with a holder bound for the datasource; it does **not** prove that commit succeeded or that no database error occurred. For full diagnosis, cross-check `TransactionSynchronizationManager.isActualTransactionActive()` and query the data after the transaction boundary.

### 4.2. Why Does DataSource Identity Matter?

The Spring transaction manager typically binds resources under the corresponding `DataSource` key. Two pools with the same JDBC URL **do not** imply the same holder. Two inconsistently configured wrappers/proxies can also cause code to fail to find the bound resource.

With multiple datasources, you must verify: which bean `JdbcTemplate` uses, which bean `JdbcTransactionManager` was constructed with, and which bean the custom DAO receives. Sharing the same database name alone is not enough.

## 5. DataSourceUtils.releaseConnection Is the Proper Way to Return It

A hand-written JDBC DAO:

```java
Connection con = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement statement =
        con.prepareStatement("INSERT INTO audit_events(id, text) VALUES (?, ?)")) {

    statement.setLong(1, 10L);
    statement.setString(2, "created");
    DataSourceUtils.applyTransactionTimeout(statement, dataSource);
    statement.executeUpdate();

} catch (SQLException ex) {
    throw new IllegalStateException("Insert failed", ex);
} finally {
    DataSourceUtils.releaseConnection(con, dataSource);
}
```

This is a **fragment**, assuming imports, datasource, and table exist. If the connection is being held by Spring for a transaction, `releaseConnection` does not close the physical connection prematurely; the manager releases it at the appropriate phase. If there is no transaction-bound connection, the helper can close/return the connection to the pool.

**Do not use:**

```java
// Anti-pattern with a connection returned by DataSourceUtils:
try (Connection con = DataSourceUtils.getConnection(dataSource)) {
    // ...
}
```

This is a fragment illustrating incorrect usage. Try-with-resources will call `Connection.close()` directly, which can close a connection that the transaction manager is still using. With `DataSourceUtils.getConnection`, use `DataSourceUtils.releaseConnection` in `finally`; statements and result sets should still use try-with-resources.

Similarly, **do not arbitrarily call `con.commit()`, `con.rollback()`, or `con.setAutoCommit(true)`** on a connection bound by the manager, as you can break the transaction boundary coordinated by Spring.

## 6. DataSourceUtils.applyTransactionTimeout

Custom JDBC code that does not use `JdbcTemplate` should account for transaction timeout when creating `Statement`/`PreparedStatement`:

```java
Connection c = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement ps =
        c.prepareStatement("SELECT id FROM jobs WHERE status = ?")) {

    DataSourceUtils.applyTransactionTimeout(ps, dataSource);
    ps.setString(1, "READY");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Read rows.
        }
    }
} finally {
    DataSourceUtils.releaseConnection(c, dataSource);
}
```

**Fragment:** requires catch/`throws SQLException`, imports, and schema. The helper can apply the remaining transaction timeout to the statement when managed by a resource holder. `applyTimeout(statement,ds,timeout)` can apply a different timeout, with the transaction timeout applied according to Spring's semantics when appropriate.

Do not confuse Spring transaction timeout with database lock timeout, network socket timeout, or HTTP timeout: each has a different scope. No utility guarantees interrupting every slow operation inside a callback.

## 7. JdbcTemplate Already Has Transaction Awareness

`JdbcTemplate` accesses JDBC connections through a Spring-aware path using `DataSourceUtils`. For example:

```java
@Transactional
public void process() {
    jdbcTemplate.update(
            "INSERT INTO orders(id, label) VALUES (?, ?)",
            1, "new");
    jdbcTemplate.update(
            "INSERT INTO audit_events(id, text) VALUES (?, ?)",
            1, "order-created");
}
```

Fragment requiring real beans, schema, and a Spring AOP proxy. Both statements typically use the same physical transaction if the manager and `JdbcTemplate` use the exact same datasource. The DAO does not need to wrap every `jdbcTemplate.update(...)` with additional `DataSourceUtils` calls.

### 7.1. When Raw JDBC Is Needed, Prefer ConnectionCallback

`JdbcTemplate.execute(ConnectionCallback<T>)` hands the appropriate connection to your code and manages acquisition/release:

```java
Integer count = jdbcTemplate.execute(connection -> {
    try (PreparedStatement ps =
            connection.prepareStatement("SELECT COUNT(*) FROM orders");
         ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getInt(1);
    }
});
```

Fragment requiring imports and the `orders` table. If you only need a count query, `queryForObject` is even simpler. However, the callback is useful when you need specialized JDBC APIs while still letting Spring manage the resource lifecycle.

### 7.2. NamedParameterJdbcTemplate

`NamedParameterJdbcTemplate` delegates to `JdbcTemplate` underneath, so it shares the same transaction awareness when configured with the right datasource/manager:

```java
namedJdbc.update(
    "UPDATE inventory SET available=available-:n WHERE id=:id",
    Map.of("n", 2, "id", 101));
```

This is a fragment requiring a `namedJdbc` variable, imports, and schema. `:n` and `:id` are Spring named parameters converted into JDBC bind parameters.

## 8. Is Raw dataSource.getConnection() Always Wrong?

With an ordinary/pooled `DataSource`, calling directly:

```java
try (Connection raw = dataSource.getConnection()) {
    // Plain JDBC call.
}
```

does not automatically consult the Spring-bound `ConnectionHolder`. Inside outer transaction T1, a raw call may borrow a different connection C2 in autocommit mode; its data **does not roll back** with T1.

However, `dataSource` could be a **`TransactionAwareDataSourceProxy`**; in that case, the proxy's `getConnection()` has Spring-transaction-aware behavior. Therefore, the proper recommendations are:

- New code: use `JdbcTemplate`, `NamedParameterJdbcTemplate`, `ConnectionCallback`, or `DataSourceUtils`.
- Legacy library forced to call `DataSource.getConnection` and `Connection.close` directly: consider passing a `TransactionAwareDataSourceProxy` wrapping the target datasource.
- Manager: must coordinate the **appropriate target/underlying datasource** rather than creating an arbitrary proxy chain and expecting resource keys to match by themselves.

## 9. TransactionAwareDataSourceProxy vs. LazyConnectionDataSourceProxy

| Proxy | Role | What It Does Not Do |
| --- | --- | --- |
| `TransactionAwareDataSourceProxy` | Allows plain JDBC legacy code to participate in a Spring-managed transaction when calling `getConnection`/`close` | Does not create a transaction if the caller does not have one; does not replace `PlatformTransactionManager` |
| `LazyConnectionDataSourceProxy` | Delays borrowing a physical JDBC connection until a statement/metadata operation is actually needed | Does not turn a raw JDBC operation into a proper transaction boundary when the manager is misconfigured |
| Target `DataSource`/pool | Supplies physical JDBC connections | Does not automatically know Spring's transaction map without bridges/utilities |

Instantiation fragment:

```java
DataSource legacyAware = new TransactionAwareDataSourceProxy(targetDataSource);
DataSource lazy = new LazyConnectionDataSourceProxy(targetDataSource);
```

This is a fragment requiring imports. When wrapping in multiple layers, the Spring documentation recommends placing `TransactionAwareDataSourceProxy` **outermost** for legacy code. Wrapper usage must be verified with integration tests: the manager, application JDBC code, and pool must agree on resource identity.

## 10. What Does TransactionSynchronizationManager Store?

This is Spring infrastructure for the imperative transaction context. Inspection APIs:

```java
boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();

boolean sync =
        TransactionSynchronizationManager.isSynchronizationActive();

boolean bound =
        TransactionSynchronizationManager.hasResource(dataSource);

Object holder =
        TransactionSynchronizationManager.getResource(dataSource);
```

**Fragment:** requires imports and a datasource bean. A `ConnectionHolder` can be bound under the datasource key; an `EntityManagerHolder` can be bound under the `EntityManagerFactory` key.

**The two flags are not identical:**

- `isActualTransactionActive()`: Spring is marking an actual transaction in the execution context.
- `isSynchronizationActive()`: resource synchronization callbacks are active. A `SUPPORTS` scope under certain configurations can have synchronization even without an actual physical transaction.

Do not see `isSynchronizationActive()==true` and conclude that all SQL in the method will roll back together.

Characteristics that can be read:

```java
String name =
        TransactionSynchronizationManager.getCurrentTransactionName();

Integer isolation =
        TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();

boolean readOnly =
        TransactionSynchronizationManager
                .isCurrentTransactionReadOnly();
```

These methods are used for introspection. `isolation == null` usually means no explicit Spring isolation override is present, not that JDBC has no isolation. `readOnly` is a transaction hint/configuration, not a security policy guaranteeing that all writes are forbidden.

### 10.1. Do Not Call bindResource Manually in a DAO

`TransactionSynchronizationManager.bindResource(key,value)` and `unbindResource(key)` are infrastructure APIs. A normal DAO **should not** manually bind a physical connection or EntityManager to "force a transaction", as doing so can corrupt the holder lifecycle, cause leaks, or overwrite a bound resource. Let the manager and Spring templates handle it.

### 10.2. Thread Context and @Async

Imperative transaction binding is typically **thread-bound**. Running `@Async`, `CompletableFuture`, or another executor thread does not automatically carry over the outer transaction's JDBC Connection or JPA EntityManager. Do not cache a `Connection`/physical `EntityManager` in a singleton and share it across threads.

Reactive/R2DBC uses a reactive transaction context and abstractions such as `ConnectionFactoryUtils` and `TransactionalOperator`; do not use `DataSourceUtils` (JDBC) to manage R2DBC transactions.

## 11. EntityManagerFactoryUtils in Spring JPA

Exact import names:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.springframework.orm.jpa.EntityManagerFactoryUtils;
```

Utility method:

```java
EntityManager em =
        EntityManagerFactoryUtils.getTransactionalEntityManager(emf);
```

This is a **fragment** requiring `emf` configured with an appropriate `JpaTransactionManager`/persistence unit. `getTransactionalEntityManager(...)` can return **null** when no appropriate thread-bound EntityManager/synchronization exists. Therefore, do not dereference it unconditionally:

```java
EntityManager em =
        EntityManagerFactoryUtils.getTransactionalEntityManager(emf);

if (em == null) {
    throw new IllegalStateException(
            "No transaction-synchronized EntityManager available");
}
em.persist(entity);
```

This is a fragment: `entity` must be managed by the right persistence unit, and JPA writes require an appropriate actual transaction.

In particular, **do not call `em.close()`** if `em` is bound by the Spring transaction manager. Resource cleanup in this case belongs to the manager/synchronization infrastructure.

### 11.1. Notable Methods

| `EntityManagerFactoryUtils` method | Meaning |
| --- | --- |
| `getTransactionalEntityManager(emf)` | Obtain a transaction-aware EntityManager; nullable |
| `doGetTransactionalEntityManager(...)` | Low-level variant that can preserve `PersistenceException` |
| `applyTransactionTimeout(query,emf)` | Apply the appropriate timeout onto a JPA `Query` |
| `closeEntityManager(em)` | Helper to close an application-managed EntityManager when the caller truly owns it |
| `convertJpaAccessExceptionIfPossible(ex)` | Translate certain JPA exceptions into Spring `DataAccessException`; may return null |
| `findEntityManagerFactory(beanFactory,unitName)` | Look up a persistence unit/EMF from the bean factory |

The Javadoc describes `EntityManagerFactoryUtils` as primarily intended for framework internals/integrations. For everyday application code, `@PersistenceContext` and Spring Data JPA repositories are simpler and less error-prone.

## 12. @PersistenceContext and SharedEntityManagerCreator

In Spring JPA, an injected field:

```java
@Repository
public class CustomerDao {
    @PersistenceContext
    private EntityManager em;

    public Customer find(long id) {
        return em.find(Customer.class, id);
    }
}
```

This is a JPA fragment, requiring imports and the `Customer` entity. With the default `PersistenceContextType.TRANSACTION`, the injected reference is a **shared transactional EntityManager proxy**; it delegates to the actual EntityManager appropriate for the current transaction.

**Do not confuse the proxy with a physical EntityManager:**

- `EntityManagerFactory` is generally thread-safe for sharing.
- A physical `EntityManager`/persistence context is not thread-safe to share across concurrent requests.
- The shared proxy injected by Spring can be stored as a field in a singleton bean because it selects the actual transactional EntityManager appropriate for each execution.

If you need to define the proxy via Java config:

```java
@Bean("sharedEntityManager")
static EntityManager sharedEntityManager(EntityManagerFactory emf) {
    return SharedEntityManagerCreator.createSharedEntityManager(emf);
}
```

This is a fragment, requiring `import org.springframework.orm.jpa.SharedEntityManagerCreator`. In services, prefer `@PersistenceContext` when using the plain JPA API.

### 12.1. emf.createEntityManager() Is a Different Case

```java
EntityManager manual = emf.createEntityManager();
try {
    // Manual/application-managed EntityManager.
} finally {
    manual.close();
}
```

This is a fragment. `emf.createEntityManager()` creates an EntityManager whose lifecycle is owned by the application itself; it does **not** automatically become the transactional EntityManager bound by `JpaTransactionManager`. When coordination is needed, you must design proper transaction synchronization/JTA/provider integration rather than assuming it from sharing the same EMF.

### 12.2. EXTENDED Persistence Context Has Thread-Safety Risks

`@PersistenceContext(type = PersistenceContextType.EXTENDED)` has a lifecycle spanning beyond a single transaction and is not a choice for "keeping one around longer in any singleton service." A physical extended EntityManager is not thread-safe, so it only makes sense in a stateful component with clear lifecycle/ownership and no uncontrolled concurrent access.

## 13. Can JpaTransactionManager and JDBC Work Together?

With proper configuration, `JpaTransactionManager` can expose the JDBC connection from the transactional EntityManager for `JdbcTemplate`/`DataSourceUtils` to use on **the same datasource**. This depends on the JPA provider/`JpaDialect`, `EntityManagerFactory`, datasource, and transaction manager configuration.

```text
                @Transactional service
                          |
                JpaTransactionManager
                          |
                EntityManagerFactory
                          |
          transaction-bound EntityManager
                          |
                  JPA persistence context
                          |
            JDBC Connection can be exposed
                  /                 \
                 /                   \
      JPA @PersistenceContext       JdbcTemplate
                 \                   /
                  same physical transaction
```

Do not assume every provider and datasource supports this automatically. When mixing JDBC and JPA:

- JPA modifies an entity without flushing yet: a JDBC query may not see the INSERT/UPDATE because the SQL has not been sent to the database yet.
- Direct JDBC update: the JPA first-level cache may still hold stale managed entities, requiring `flush`/`refresh`/`clear` depending on the use case.
- Bulk/native SQL may not automatically perform optimistic `@Version` updates like normal entity manager operations.
- `em.flush()` is not `commit()`; other physical transactions will not necessarily see the changes yet.
- A JDBC/JPA error can mark the transaction rollback-only; catching the exception does not make the transaction committable.

With **two** independent datasources, a single local manager does not provide distributed atomicity. You need JTA/XA, a saga, or a transactional outbox design according to business requirements.

## 14. Java 17+ Runnable Demo: JdbcTemplate + DataSourceUtils in the Same Transaction

This demo uses Spring Framework **6.2.8**, Java 17+, Maven, and in-memory H2 **2.3.232**, without Spring Boot. This is a **standalone runnable JDBC program**; the JPA examples above are fragments because running JPA requires configuring a separate provider and persistence unit.

Four scenarios:

1. A `@Transactional` service writes one row via `JdbcTemplate` and one row via a DAO using `DataSourceUtils`: both commit.
2. Both DAOs write data, then the service throws `RuntimeException`: both rows roll back.
3. The service calls `setRollbackOnly()` and returns a result normally: both rows roll back.
4. Calling the DAO using `DataSourceUtils` outside a transaction: the helper acquires a connection and returns/closes it with proper lifecycle; with H2's default autocommit, the row is persisted.

### 14.1. Structure

```text
resource-aware-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── ResourceAwareDemo.java
```

### 14.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>resource-aware-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.ResourceAwareDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 14.3. src/main/java/dev/learning/ResourceAwareDemo.java

```java
package dev.learning;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class ResourceAwareDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:resource_aware;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        RawJdbcDao rawJdbcDao(DataSource ds) {
            return new RawJdbcDao(ds);
        }

        @Bean
        BusinessService businessService(
                JdbcTemplate jdbc, RawJdbcDao dao, DataSource ds) {
            return new BusinessService(jdbc, dao, ds);
        }
    }

    // Custom JDBC code: proper get + release pattern.
    public static class RawJdbcDao {
        private final DataSource dataSource;

        public RawJdbcDao(DataSource dataSource) {
            this.dataSource = dataSource;
        }

        public boolean insert(int id, String label) {
            Connection con =
                    DataSourceUtils.getConnection(dataSource);

            try (PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO records(id, label) VALUES(?, ?)")) {
                DataSourceUtils.applyTransactionTimeout(
                        ps, dataSource);

                ps.setInt(1, id);
                ps.setString(2, label);
                ps.executeUpdate();

                return DataSourceUtils.isConnectionTransactional(
                        con, dataSource);
            } catch (SQLException e) {
                throw new IllegalStateException(
                        "Insert failed for id=" + id, e);
            } finally {
                DataSourceUtils.releaseConnection(con, dataSource);
            }
        }
    }

    public static class BusinessService {
        private final JdbcTemplate jdbc;
        private final RawJdbcDao dao;
        private final DataSource dataSource;

        public BusinessService(
                JdbcTemplate jdbc, RawJdbcDao dao, DataSource ds) {
            this.jdbc = jdbc;
            this.dao = dao;
            this.dataSource = ds;
        }

        @Transactional
        public void succeed() {
            System.out.println(
                    "inside.active="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
            System.out.println(
                    "inside.datasourceBound="
                    + TransactionSynchronizationManager
                            .hasResource(dataSource));

            jdbc.update(
                    "INSERT INTO records(id, label) VALUES(?, ?)",
                    1, "jdbc");

            boolean bound = dao.insert(2, "datasource-utils");
            System.out.println(
                    "inside.customConnectionTransactional=" + bound);
        }

        @Transactional
        public void fail() {
            jdbc.update(
                    "INSERT INTO records(id, label) VALUES(?, ?)",
                    3, "will rollback jdbc");
            dao.insert(4, "will rollback custom");
            throw new IllegalStateException("simulated failure");
        }

        @Transactional
        public String reject() {
            jdbc.update(
                    "INSERT INTO records(id, label) VALUES(?, ?)",
                    5, "rollback-only jdbc");
            dao.insert(6, "rollback-only custom");

            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
            return "rejected";
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM records", Integer.class);
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE records (
                        id INT PRIMARY KEY,
                        label VARCHAR(80) NOT NULL
                    )
                    """);

            BusinessService service =
                    context.getBean(BusinessService.class);

            service.succeed();
            System.out.println("afterSuccess.rows=" + count(jdbc));

            try {
                service.fail();
            } catch (IllegalStateException ex) {
                System.out.println(
                        "failure.caught=" + ex.getMessage());
            }
            System.out.println("afterFailure.rows=" + count(jdbc));

            System.out.println(
                    "rollbackOnly.result=" + service.reject());
            System.out.println(
                    "afterRollbackOnly.rows=" + count(jdbc));

            RawJdbcDao dao = context.getBean(RawJdbcDao.class);
            System.out.println(
                    "outside.customConnectionTransactional="
                    + dao.insert(7, "outside"));

            System.out.println("afterOutside.rows=" + count(jdbc));
            System.out.println(
                    "outside.active="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
            System.out.println(
                    "outside.datasourceBound="
                    + TransactionSynchronizationManager
                            .hasResource(context.getBean(DataSource.class)));
        }
    }
}
```

### 14.4. Run Command and Expected stdout

Inside the `resource-aware-demo` directory, JDK 17+, Maven 3.x, and Internet access for downloading Maven dependencies on the first run are required:

```bash
mvn -q clean compile exec:java
```

Lines printed by **the program itself** (Maven/Spring logs may vary depending on the environment):

```text
inside.active=true
inside.datasourceBound=true
inside.customConnectionTransactional=true
afterSuccess.rows=2
failure.caught=simulated failure
afterFailure.rows=2
rollbackOnly.result=rejected
afterRollbackOnly.rows=2
outside.customConnectionTransactional=false
afterOutside.rows=3
outside.active=false
outside.datasourceBound=false
```

### 14.5. Explaining the Results

**Successful commit:** Spring `JdbcTransactionManager` begins a transaction and binds a `ConnectionHolder` for the same `DataSource`. `JdbcTemplate` inserts ID=1, then the `DataSourceUtils` DAO inserts ID=2. The connection in the custom DAO is recognized as transactional; when the service returns, T1 commits, resulting in 2 rows.

**Unchecked exception:** The service writes ID=3 via `JdbcTemplate` and ID=4 via the custom DAO, then throws `IllegalStateException`. The interceptor requests rollback of T2. Both rows are gone; the count remains 2. This verifies that the custom DAO used **the right transaction resource**.

**Explicit rollback-only:** The service writes IDs 5 and 6 and marks rollback-only; the method returns `"rejected"` normally. The transaction manager rolls back because the root scope requested it, so the count remains 2. A normal return must not be interpreted as meaning the data committed.

**Outside a transaction:** The DAO acquires a connection on its own, and the operation runs with H2's default autocommit; the helper releases it after the statement. `isConnectionTransactional` is false and the count increases to 3. This is not "Spring automatically opening a large transaction" for an external caller; it is simply a JDBC operation outside the service's transaction scope.

**Important conditions:** `BusinessService` must be a Spring bean and its methods must be called through a proxy; the `DataSource` injected into the manager, `JdbcTemplate`, and DAO is **the exact same bean**. The example runs sequentially and does not test concurrency. The output is derived from API/DB semantics; run Maven to verify empirically.

## 15. Deliberate Experiments

**Try A — Replace DAO DataSourceUtils with raw ds.getConnection().** Use a new connection with `try-with-resources` (and proper statement cleanup). When the service fails, the custom JDBC insert can commit independently of `JdbcTemplate`'s transaction. This is a test **deliberately simulating a bug**, not for production code.

**Try B — Use TransactionAwareDataSourceProxy for a legacy DAO.** Legacy code that only knows plain `getConnection()/close()` can participate in a Spring transaction if proxy wrapping and the manager target are configured properly. Compare rows after failure.

**Try C — Configure `RawJdbcDao` to use a different datasource.** The Spring manager still coordinates dsA, while the custom insert on dsB may not roll back. If using two different H2 databases, create the schema in each beforehand.

**Try D — Remove `setRollbackOnly()` in `reject()`.** IDs 5 and 6 will commit if no exception or resource failure occurs. The `"rejected"` result can still be returned, yet the data state differs; business semantics must be kept under control.

**Try E — Use REQUIRES_NEW on a separate method.** Observe the manager temporarily suspending the outer connection while the inner call borrows an independent connection and can commit even if the outer rolls back; remember to check pool sizing and lock waits.

**Try F — Print `TransactionSynchronizationManager.isSynchronizationActive()`.** Compare with `isActualTransactionActive()` in different scopes such as `SUPPORTS`; do not equate the two flags.

## 16. Common Implementation Mistakes

| Mistake | Consequence | Proper Fix |
| --- | --- | --- |
| Importing `EntityManagerUtils` from Spring ORM | This class does not exist in Spring 6.2 | Use `EntityManagerFactoryUtils` or `@PersistenceContext` |
| Calling plain `dataSource.getConnection()` from a normal pool inside a transaction | May autocommit outside T1 | Properly configured `JdbcTemplate`/`DataSourceUtils`/transaction-aware proxy |
| Calling `Connection.close()` on a connection from `DataSourceUtils` | Can close a resource held by the manager | `DataSourceUtils.releaseConnection` |
| Failing to release after `getConnection` | Leaks/broken reference count/cleanup | `finally` block releasing once per acquisition |
| Manager on dsA, DAO on dsB | Rollback does not protect dsB statements | Align datasource/manager, use qualifiers |
| Manually binding/unbinding `ConnectionHolder` in business code | Lifecycle/resource map conflicts | Let the manager and Spring framework manage it |
| Treating `isSynchronizationActive` as an active physical transaction | False assumptions about atomicity | Combine `isActualTransactionActive` with DB assertions |
| Holding a physical `EntityManager` in a singleton | Not thread-safe, stale persistence context | Use shared proxy / `@PersistenceContext` |
| Manually closing an injected shared EntityManager | Breaks lifecycle or proxy behavior | Do not close; manager cleans up |
| Using `emf.createEntityManager()` and assuming it joined the transaction | May use a separate context, a different transaction, or no transaction | Shared proxy / proper JPA integration |
| Mixing JPA and JDBC without flush/refresh | JDBC/managed entities may observe different states | Coordinate flush order, cache, and resource manager |
| Passing a JDBC connection across `@Async` | No longer has the thread-bound transaction context | Create a new transaction in the worker |
| Using `REQUIRES_NEW` to fix every rollback | Unintended independent commits, extra connections/locks | Choose propagation based on business invariants |
| Checking only logs instead of data after the transaction | Wrong conclusions about commit/rollback | Integration test with an independent query after the boundary |

## 17. Integration Testing Checklist

- [ ] Writing via `JdbcTemplate` and custom `DataSourceUtils` in the same transaction: both commit.
- [ ] Throwing a `RuntimeException` after both writes: both roll back.
- [ ] Calling `setRollbackOnly()`: the method can return normally while the DB still rolls back.
- [ ] Custom DAO outside a transaction: resource is released without leaking.
- [ ] When using legacy code, `TransactionAwareDataSourceProxy` allows transaction participation if wrappers/target are right.
- [ ] Using a different datasource: test must detect SQL outside the manager's resource.
- [ ] `JpaTransactionManager` and `JdbcTemplate` on the same datasource: verify provider/dialect/flush behavior.
- [ ] `@PersistenceContext` uses a shared proxy; a physical `EntityManager` is not shared across threads.
- [ ] `REQUIRES_NEW` suspends/resumes bindings properly, pool does not exhaust, and inner does not contend on row locks held by outer.
- [ ] Assertions run **after** commit/rollback and outside any test-managed transaction that could roll back further.

**Spring TestContext note:** A test method annotated with `@Transactional` itself may be rolled back by the framework at the end of the test, masking whether the service actually commits. To prove a commit, design transaction boundaries and independent data reads appropriately, or use `TestTransaction` deliberately.

## 18. Self-Check Questions

**1. Does `DataSourceUtils.getConnection(ds)` always open a new physical connection?**  
No. If Spring has a transaction-bound connection for that datasource, the helper can return the bound connection. Otherwise, it requests a connection from the datasource.

**2. Why does `JdbcTemplate` not require custom code to call `DataSourceUtils`?**  
Because `JdbcTemplate` performs transaction-aware acquisition/release behind the scenes; application code should use the abstraction instead of managing the lifecycle manually.

**3. Does `DataSourceUtils.releaseConnection` always close the connection?**  
No. It does not immediately close a connection belonging to a Spring-managed transaction; cleanup is performed by the manager at the right time.

**4. When should `TransactionAwareDataSourceProxy` be used?**  
When legacy code/libraries only accept a standard `DataSource` and call `getConnection()/close()` directly; it serves as a bridge for legacy JDBC.

**5. Does `LazyConnectionDataSourceProxy` serve the same function as the proxy above?**  
No. The lazy proxy defers physical connection acquisition; the transaction-aware proxy lets plain JDBC code participate in transactions.

**6. Is `EntityManagerUtils` a valid Spring ORM class name?**  
Not in Spring 6.2. The corresponding utility class is `EntityManagerFactoryUtils`; applications normally use `@PersistenceContext` or Spring Data JPA.

**7. Does `getTransactionalEntityManager(emf)` always return a non-null EntityManager?**  
No. The method can return null if an appropriate transaction/synchronization context is missing. JPA writes require an appropriate actual transaction.

**8. Why can an injected `@PersistenceContext EntityManager` be used in a singleton even though a physical EntityManager is not thread-safe?**  
Because the injected reference is typically a shared proxy that delegates to the actual EntityManager of the current execution context; it is not a single fixed physical EntityManager shared across all threads.

**9. If the manager opens T1 and an inner call uses `REQUIRES_NEW`, does `DataSourceUtils` return C1 or C2?**  
It uses inner T2's binding (typically C2) while T1 is suspended; when the inner call finishes, T1's resource is resumed.

**10. Does `isConnectionTransactional==true` prove a commit happened?**  
No. It reflects resource binding, not the outcome; DB commit/rollback must be verified after the transaction boundary.

**11. If the JDBC URL is identical but the DAO uses a different pool, does it automatically join the same transaction?**  
You must not assume so. A unified resource key/manager/datasource is required; two different pools can create different connections and different transactions.

**12. Can `DataSourceUtils` be used to manage R2DBC?**  
No. `DataSourceUtils` is a JDBC imperative utility; the reactive stack has `ConnectionFactoryUtils`/`TransactionalOperator` and the reactive context.

## 19. Conclusion

**Correct transactions are not just about having the right annotation**. Code must also **acquire and release the right JDBC/JPA resource**:

- `DataSourceUtils` helps custom JDBC code look up transaction-bound connections and release them safely.
- `JdbcTemplate` already has transaction awareness; prefer it for new code.
- `TransactionAwareDataSourceProxy` is a bridge for plain JDBC legacy code; `LazyConnectionDataSourceProxy` solves a different problem.
- JPA in Spring uses `EntityManagerFactoryUtils` (not a hypothetical `EntityManagerUtils` import), with `@PersistenceContext`/`SharedEntityManagerCreator` as the recommended access paths.
- `TransactionSynchronizationManager` manages the resource map per execution context; application DAOs should not bind/unbind manually.
- The transaction manager and data access code must use the right datasource/persistence unit; `REQUIRES_NEW` can change resource bindings and atomicity.
- Integration tests must verify **the data that actually remains after commit/rollback**, not just flags, annotations, or connection object identity.

## 20. References

1. [Spring Framework 6.2 – JDBC Connections](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/connections.html) — `DataSourceUtils`, `TransactionAwareDataSourceProxy`, `LazyConnectionDataSourceProxy`.
2. [Spring Framework – Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html) — how JDBC resources are bound/reused.
3. [Spring 6.2 – DataSourceUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html) — `getConnection`, `releaseConnection`, `applyTransactionTimeout`.
4. [Spring 6.2 – TransactionSynchronizationManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html) — resource map, synchronization, and transaction characteristics.
5. [Spring Framework 6.2 – JPA integration](https://docs.spring.io/spring-framework/reference/6.2/data-access/orm/jpa.html) — `@PersistenceContext`, shared EntityManager, and transaction lifecycle.
6. [Spring 6.2 – EntityManagerFactoryUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/EntityManagerFactoryUtils.html) — JPA transactional utility and exception translation.
7. [Spring 6.2 – SharedEntityManagerCreator API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/SharedEntityManagerCreator.html) — shared JPA proxy.
8. [Spring 6.2 – JpaTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html) — JPA manager and JDBC exposure.
9. [Spring 6.2 – TransactionAwareDataSourceProxy API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/TransactionAwareDataSourceProxy.html) — legacy JDBC adapter.
