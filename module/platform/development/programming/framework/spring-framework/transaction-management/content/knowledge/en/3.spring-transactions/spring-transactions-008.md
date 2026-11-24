# Choosing a Transaction Manager by Resource Type, Not by `@Transactional` Name

> **Spring Framework — Transaction Management → Spring Model.** This lesson answers the questions: when an application uses JDBC, JPA, R2DBC, MongoDB, Kafka, or multiple data sources, which `TransactionManager` must be chosen, and why does the `@Transactional` annotation name not reveal which resource actually commits or rolls back?

## 1. Core Principle

**Choose a transaction manager based on the resource that needs to participate in the transaction and the mechanism used to access that resource.** The `@Transactional` annotation only supplies metadata about the transaction boundary; it does not automatically turn every data access inside a method into a unified transaction.

Three layers to distinguish:

1. **Annotation and transaction attributes:** `@Transactional` describes propagation, isolation, read-only, timeout, rollback rules, and optionally specifies the manager name/qualifier.
2. **Transaction infrastructure:** Spring AOP `TransactionInterceptor` reads the metadata, resolves the matching manager, and asks the manager to start/join, commit, or roll back the transaction.
3. **Resource binding:** the manager manages the actual resource — a JDBC `Connection` from a `DataSource`, a JPA `EntityManager` from an `EntityManagerFactory`, an R2DBC `Connection` from a `ConnectionFactory`, a MongoDB `ClientSession`, or a global transaction coordinated by a JTA coordinator.

General flow:

```text
Call goes through Spring proxy
          |
          v
@Transactional (metadata: propagation/rollback/transactionManager)
          |
          v
TransactionInterceptor
          |
          +--> select configured/qualified TransactionManager bean
                     |
                     +--> manage the appropriate resource
                     |      JDBC DataSource + Connection
                     |      JPA EntityManagerFactory + EntityManager
                     |      R2DBC ConnectionFactory + Connection
                     |      MongoDatabaseFactory + ClientSession
                     |      JTA coordinator + enlisted resources
                     |
                     +--> invoke business logic
                     |
                     +--> commit or rollback
```

**With the same `@Transactional`, how the transaction is managed changes with the manager.** For instance, `@Transactional` on a JPA service and on a JDBC service may look identical; if the JPA service uses a JDBC manager that does not integrate its `EntityManager`, you cannot expect JPA persist/flush/rollback to behave properly.

Conversely, renaming a bean from `ordersTxManager` to `jpaTxManager` **does not** turn a `JdbcTransactionManager` into a `JpaTransactionManager`. The name is merely an identifier to reference the bean; behavior is determined by **the manager implementation type + the resource object passed to that bean during configuration**.

## 2. Distinguishing Abstractions in Spring

- `org.springframework.transaction.TransactionManager`: common marker interface.
- `PlatformTransactionManager`: manager for **imperative transactions**; provides `getTransaction(...)`, `commit(...)`, and `rollback(...)`. Typically binds transaction state/resources to a thread.
- `ReactiveTransactionManager`: manager for **reactive transactions**; uses reactive flows and Reactor `Context`, not JDBC's thread-bound model.
- `@Transactional`: annotation describing transaction attributes; **not** a manager.
- `TransactionTemplate`: programmatic way to use a specific `PlatformTransactionManager`.
- `TransactionalOperator`: programmatic way to use a specific `ReactiveTransactionManager`.

Managers can share the same declarative `@Transactional` API without necessarily supporting every attribute identically. `NESTED`/savepoints, isolation, timeout, and `readOnly` capabilities depend on the manager, driver, and datastore. `readOnly=true` is usually a hint/optimization, **not a default security mechanism** blocking all writes across every database system.

## 3. Manager Selection Table by Resource and Access Mechanism

| Resource and access mechanism | Typically suitable manager | Resource coordinated by manager | Conditions to remember |
| --- | --- | --- | --- |
| JDBC, `JdbcTemplate`, or SQL via `DataSource` | `JdbcTransactionManager` or `DataSourceTransactionManager` | JDBC `Connection` of **the exact `DataSource`** | DAO must use transaction-aware connections; `JdbcTemplate`/`DataSourceUtils` do this |
| JPA, `EntityManager`, Spring Data JPA repository | `JpaTransactionManager` | JPA `EntityManager` of **the exact `EntityManagerFactory`** | Repository/`EntityManager` must belong to the factory coordinated by the manager |
| JDBC **on the same underlying datasource as JPA** | Can use `JpaTransactionManager` for both JPA and JDBC | `EntityManager`; can share JDBC connection | Requires same `DataSource` and support from `JpaDialect`; do not infer from matching database URLs |
| Multiple resources requiring global atomic commit | `JtaTransactionManager` + transaction coordinator | XA resources participating in JTA transaction | Driver, pool, provider, and coordinator must be configured for XA/JTA; does not happen from an annotation alone |
| R2DBC via `DatabaseClient` / reactive repository | `R2dbcTransactionManager` | R2DBC `Connection` of **the exact `ConnectionFactory`** in Reactor `Context` | Uses reactive pipeline; cannot replace a JDBC manager |
| Imperative MongoDB (`MongoTemplate`) | `MongoTransactionManager` (Spring Data MongoDB) | MongoDB `ClientSession` on the right `MongoDatabaseFactory` | Mongo deployment must support transactions; manager must be configured |
| Reactive MongoDB (`ReactiveMongoTemplate`) | `ReactiveMongoTransactionManager` (Spring Data MongoDB) | MongoDB `ClientSession` in reactive context | Do not use the imperative version for reactive operations |
| Transactional Kafka producer | `KafkaTransactionManager` (Spring Kafka) | Kafka producer transaction | Does not guarantee atomic commit with another database like a local JDBC transaction |

This table is a **selection map by resource**, not a rigid law of "only one manager per technology." For example, JTA can coordinate JPA/JDBC when resources are properly integrated with JTA; `JpaTransactionManager` can also serve JDBC access on its underlying datasource. Every capability depends on actual configuration.

### JDBC: `JdbcTransactionManager` and `DataSourceTransactionManager`

Both serve local transactions on **a single JDBC `DataSource`**:

- `DataSourceTransactionManager` manages JDBC connections, commit, rollback, isolation, timeout, and savepoints when supported.
- `JdbcTransactionManager` is a subclass of `DataSourceTransactionManager` that adds translation of commit/rollback errors into `DataAccessException` subclasses better aligned with `JdbcTemplate`.
- For standard pure JDBC cases, `JdbcTransactionManager` is a convenient choice; `DataSourceTransactionManager` remains valid when the application expects its contract/exceptions.

Whichever variant you choose, the manager must receive **the exact `DataSource` bean** used by `JdbcTemplate`/DAOs. If there are two datasources A and B, a manager bound to A does not automatically create transactions for connections obtained from B.

### JPA: Why Choose `JpaTransactionManager`?

`JpaTransactionManager` manages `EntityManager` instances tied to a specific `EntityManagerFactory`, giving the persistence context, flushing, and database transaction a unified boundary. Spring Data JPA repositories and `@PersistenceContext` must use the matching factory/manager.

If a service performs both JPA and `JdbcTemplate` operations **on the same database and same underlying datasource**, `JpaTransactionManager` can let JDBC participate in **the same transaction** when `JpaDialect`/connection access is compatibly configured. This is an important exception to the mechanical rule of thumb "always pick a JDBC manager whenever you see JDBC."

Do not also instantiate a separate `JdbcTransactionManager` for the same datasource and arbitrarily switch managers between methods if the goal is **one** shared transaction for JPA and JDBC. Two independent managers do not synchronize JPA's persistence context with a JDBC transaction opened by the other manager.

### R2DBC: Seeing "SQL" Is Not Enough to Pick a Manager

JDBC is a blocking API using `javax.sql.DataSource`; R2DBC is a reactive API using `io.r2dbc.spi.ConnectionFactory`. They have different connection types and transaction-binding mechanisms.

- `JdbcTransactionManager` is a `PlatformTransactionManager`, typically binding connections per thread.
- `R2dbcTransactionManager` is a `ReactiveTransactionManager`, binding connections in the subscriber `Context`.
- `@Transactional` on a method with a reactive return type (`Mono`/`Flux`/`Publisher`) is handled along the reactive path; methods returning `void` or normal Java objects must pair with an appropriate imperative manager.

**You cannot wrap JDBC in a `Mono` and expect an R2DBC transaction automatically**; nor can you take an R2DBC connection and coordinate it with a JDBC manager.

### JTA: Choose When the Real Requirement Is Resource Coordination

`JtaTransactionManager` acts as an adapter to a JTA coordinator. For database A and database B to commit/rollback atomically under the XA protocol, XA-capable resources, a coordinator, and compatible enlistment configuration are required. Simply adding `@Transactional` or naming a bean `globalTransactionManager` **does not create a distributed transaction**.

When multiple systems do not support a shared coordinator (for example, a database and an HTTP API), evaluate transactional outbox, saga, and compensation/idempotency mechanisms; do not assume one annotation guarantees cross-system atomicity.

## 4. How to Choose a Manager: From Actual Work to Bean

Answer in order:

1. **Which data must roll back together?** One table, multiple tables in the same database, two independent databases, or a database + message broker?
2. **Which access API does the code use?** `JdbcTemplate`, JPA repository/`EntityManager`, R2DBC `DatabaseClient`, Mongo template, Kafka template?
3. **From which factory does that API acquire resources?** `DataSource`, `EntityManagerFactory`, `ConnectionFactory`, `MongoDatabaseFactory`, Kafka `ProducerFactory`?
4. **Which manager actually coordinates that factory?** Inspect constructor/setter/bean configuration; do not guess from names.
5. **Do all operations needing rollback participate in the chosen manager?** With a local manager, resources outside its scope do not join automatically.
6. **Is this an imperative or reactive flow?** Check the return type and whether resources bind to a thread or Reactor `Context`.
7. **Is there more than one manager in the ApplicationContext?** Specify the default or qualifier explicitly so Spring picks the right one; avoid relying on accidental selection.

Condensed decision tree:

```text
Need a unit of transaction
          |
          +-- R2DBC/reactive SQL? ----------> R2dbcTransactionManager
          |
          +-- Mongo imperative/reactive? --> MongoTransactionManager /
          |                                 ReactiveMongoTransactionManager
          |
          +-- JPA/EntityManager? ----------> JpaTransactionManager
          |                                   (can coordinate JDBC on same datasource)
          |
          +-- JDBC-only? ------------------> JdbcTransactionManager
          |                                   or DataSourceTransactionManager
          |
          +-- Multiple XA resources needing
          |   global atomic commit? -------> JtaTransactionManager + XA/JTA
          |
          +-- Kafka producer transaction? -> KafkaTransactionManager
                                            (Kafka transaction scope)
```

**If a service touches multiple technologies, the most important question is not "which name sounds reasonable", but whether they can participate in the same transaction mechanism.**

## 5. How `@Transactional` Selects a Manager

`@Transactional` does not inspect the method body to see "this method calls `JpaRepository`, so find `JpaTransactionManager`." It works from metadata and configured beans.

In a single-manager application, explicit specification is usually unnecessary:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void createOrder() {
    // Spring uses the configured default transaction manager.
}
```

This snippet only illustrates syntax inside a Spring bean; it is not a standalone runnable program.

When multiple managers exist, specify the corresponding identifier explicitly:

```java
@Transactional(transactionManager = "ordersTxManager")
public void createOrder() {
    // Operations must participate in the right resources of ordersTxManager.
}

@Transactional("billingTxManager") // Alias for transactionManager = "billingTxManager"
public void createInvoice() {
    // Operations must participate in resources of billingTxManager.
}
```

Both forms above **use the exact same `org.springframework.transaction.annotation.Transactional` annotation**. The string value is a bean name or qualifier, **not a transaction technology name**. The name `ordersTxManager` could point to a `JdbcTransactionManager`, a `JpaTransactionManager`, or something else; you must inspect the actual bean.

A wiring example:

```java
// Illustrative configuration snippet, assuming datasources already exist.
@Bean("ordersTxManager")
PlatformTransactionManager ordersTxManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

In an application with multiple `TransactionManager` beans, `@Transactional` without specifying a manager can cause an ambiguous-default error or pick an unintended default depending on configuration. Using explicit names/qualifiers is the easiest approach to verify. You can configure `@Primary` or `TransactionManagementConfigurer` to set a sensible default; that **does not replace** selecting a separate manager for other resources.

Additionally, in Spring Framework 6.2+, a class-level `@Qualifier` can influence manager selection for `@Transactional` declarations that omit a qualifier; this is an extra configuration option, and proper resource binding must still be ensured.

**`jakarta.transaction.Transactional` is the standard Jakarta Transactions annotation.** Spring supports this annotation as a declarative metadata source in appropriate configurations, but importing the Jakarta annotation **does not force Spring to use JTA**. The transaction management mechanism is still determined by the configured manager. When you need Spring-specific attributes like `transactionManager`, `propagation`, and `rollbackFor`, use `org.springframework.transaction.annotation.Transactional`.

## 6. Runnable Java 17+ Example: Two Databases, Two Managers, Two Different Commit Outcomes

This example proves three things:

- Both methods use the exact same `@Transactional` annotation type.
- The order-processing method selects `ordersTxManager` bound to `ordersDb`; the audit-recording method selects `auditTxManager` bound to `auditDb`.
- When the order method fails, the order rolls back; the audit already committed in **an independent local transaction**, so it remains persisted. This is not a Spring bug: it is the configured transaction scope.

Uses Spring Framework **6.2.8**, H2 **2.3.232**, Maven, and Java 17+. The example runs standalone, requiring no Spring Boot or database server.

### 6.1. Project Structure

```text
tx-manager-resource-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── TxManagerResourceDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>tx-manager-resource-demo</artifactId>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.TxManagerResourceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Create `src/main/java/dev/learning/TxManagerResourceDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public class TxManagerResourceDemo {

    @Configuration
    @EnableTransactionManagement
    public static class AppConfig {

        private static DataSource h2(String databaseName) {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:" + databaseName + ";DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean("ordersDataSource")
        public DataSource ordersDataSource() {
            return h2("ordersDb");
        }

        @Bean("auditDataSource")
        public DataSource auditDataSource() {
            return h2("auditDb");
        }

        @Bean("ordersJdbc")
        public JdbcTemplate ordersJdbc(
                @Qualifier("ordersDataSource") DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("auditJdbc")
        public JdbcTemplate auditJdbc(
                @Qualifier("auditDataSource") DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("ordersTxManager")
        public PlatformTransactionManager ordersTxManager(
                @Qualifier("ordersDataSource") DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean("auditTxManager")
        public PlatformTransactionManager auditTxManager(
                @Qualifier("auditDataSource") DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public AuditService auditService(
                @Qualifier("auditJdbc") JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        public OrderService orderService(
                @Qualifier("ordersJdbc") JdbcTemplate jdbc,
                AuditService auditService) {
            return new OrderService(jdbc, auditService);
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(transactionManager = "auditTxManager")
        public void record(long id) {
            jdbc.update(
                    "INSERT INTO audit_events (id, message) VALUES (?, ?)",
                    id, "order attempted");
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final AuditService auditService;

        public OrderService(JdbcTemplate jdbc, AuditService auditService) {
            this.jdbc = jdbc;
            this.auditService = auditService;
        }

        @Transactional(transactionManager = "ordersTxManager")
        public void createThenFail() {
            jdbc.update(
                    "INSERT INTO order_records (id, description) "
                            + "VALUES (?, ?)",
                    1L, "sample order");

            // Call through another Spring bean -> passes through audit proxy.
            // Audit has its own manager and datasource.
            auditService.record(1L);

            throw new IllegalStateException("simulated");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AppConfig.class)) {

            JdbcTemplate orders =
                    context.getBean("ordersJdbc", JdbcTemplate.class);
            JdbcTemplate audit =
                    context.getBean("auditJdbc", JdbcTemplate.class);

            // DDL only initializes the schema, outside the rollback test.
            orders.execute(
                    "CREATE TABLE order_records "
                            + "(id BIGINT PRIMARY KEY, "
                            + "description VARCHAR(80))");
            audit.execute(
                    "CREATE TABLE audit_events "
                            + "(id BIGINT PRIMARY KEY, "
                            + "message VARCHAR(80))");

            try {
                // Obtain the Spring-proxied bean; do not manually instantiate new OrderService.
                context.getBean(OrderService.class).createThenFail();
            } catch (IllegalStateException expected) {
                System.out.println(
                        "Exception: " + expected.getMessage());
            }

            Integer orderCount = orders.queryForObject(
                    "SELECT COUNT(*) FROM order_records", Integer.class);
            Integer auditCount = audit.queryForObject(
                    "SELECT COUNT(*) FROM audit_events", Integer.class);

            System.out.println("order_records=" + orderCount);
            System.out.println("audit_events=" + auditCount);
        }
    }
}
```

### 6.3. Compile and Run

In the `tx-manager-resource-demo` directory, with JDK 17+ and Maven (first run needs Internet to download dependencies):

```bash
mvn -q clean compile exec:java
```

Lines printed by the program (excluding Maven messages or logging library output if enabled):

```text
Exception: simulated
order_records=0
audit_events=1
```

**Explanation:**

1. `AppConfig` creates two different `DataSource`s: `ordersDataSource` points to `jdbc:h2:mem:ordersDb`, `auditDataSource` points to `jdbc:h2:mem:auditDb`.
2. Each `JdbcTransactionManager` is created with **its own corresponding datasource**. Both `JdbcTemplate`s are also configured to match those two datasources.
3. Spring intercepts `OrderService.createThenFail()` and opens the orders transaction. The new order row is not yet committed.
4. `OrderService` calls the `AuditService` proxy bean. Spring selects `auditTxManager` and a separate audit transaction; `record()` completes normally, so the audit commits.
5. `createThenFail()` throws `IllegalStateException`. Spring rolls back the orders transaction because this is an unchecked exception. Outcome: no new order, yet an audit event exists.

**What this proves:** two managers manage two separate databases; there is no single atomic transaction spanning both. There is no sense in which "one `@Transactional` automatically rolls back all data sources." The example intentionally lets the audit commit to clarify boundaries; real business design must decide whether such independent auditing matches requirements.

### 6.4. What If Both Tables Must Roll Back in the Same Database?

If `order_records` and `audit_events` live on **the same datasource**, have both DAOs use the datasource/connections managed by the same manager, and place the transaction boundary on the service calling both operations. When both operations truly join the same JDBC transaction, an exception rolls back both.

If the data lives in **two independent databases**, renaming `@Transactional`, pointing two managers at each other, or adding `@Primary` **does not** provide atomicity. You need a coordination mechanism like JTA/XA when feasible, or an eventual consistency design (outbox/saga) per business requirements.

## 7. Configuring JPA, JDBC, and R2DBC in Common Scenarios

### 7.1. A Single JPA Persistence Unit

When repositories use a single `EntityManagerFactory`, use `JpaTransactionManager` for that persistence unit:

```java
// Inside an @Configuration class of an application that has an EntityManagerFactory bean.
@Bean("ordersJpaTx")
PlatformTransactionManager ordersJpaTx(
        @Qualifier("ordersEntityManagerFactory")
        jakarta.persistence.EntityManagerFactory emf) {
    return new org.springframework.orm.jpa.JpaTransactionManager(emf);
}
```

The code above is a **configuration fragment** requiring a declared `ordersEntityManagerFactory` and Spring ORM/JPA dependencies. Service usage:

```java
@Transactional(transactionManager = "ordersJpaTx")
public void persistOrder() {
    // Call JPA repository / EntityManager belonging to ordersEntityManagerFactory.
}
```

When using Spring Data JPA with multiple `EntityManagerFactory` beans, route repositories to the right factory and manager via `@EnableJpaRepositories`:

```java
@EnableJpaRepositories(
    basePackages = "dev.learning.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersJpaTx"
)
```

This is an annotation fragment, not a standalone Java class. `entityManagerFactoryRef` routes the factory, while `transactionManagerRef` routes the transaction manager; omitting either when multiple persistence units exist can cause repositories to use unintended configuration. Remember that bean names, service default managers, and Spring Data repository transaction managers are separate points to verify.

### 7.2. One Datasource Used by Both JPA and `JdbcTemplate`

When JPA and JDBC must participate **in one transaction**, the typical approach is `JpaTransactionManager` coordinating `EntityManagerFactory` while letting `JdbcTemplate` on the matching datasource join. Conditions are:

- `EntityManagerFactory` is bound to that datasource; `JpaTransactionManager` knows the corresponding datasource.
- `JpaDialect` supports obtaining the underlying JDBC connection for transaction participation.
- JDBC access uses `JdbcTemplate`/`DataSourceUtils` to acquire transaction-aware connections.
- Operation/flush order of JPA is considered when JDBC reads data just modified in the persistence context: when needed, `EntityManager.flush()` may have to run before the JDBC query.

If any of these conditions is not met, do not claim that all code touching the same database URL automatically shares one physical transaction.

### 7.3. A Reactive SQL Pipeline

For R2DBC, the manager should be bound to the `ConnectionFactory` used by `DatabaseClient` or R2DBC repositories:

```java
// Configuration fragment when an R2DBC ConnectionFactory already exists.
@Bean("r2dbcTx")
org.springframework.transaction.ReactiveTransactionManager r2dbcTx(
        io.r2dbc.spi.ConnectionFactory connectionFactory) {
    return new org.springframework.r2dbc.connection
            .R2dbcTransactionManager(connectionFactory);
}
```

The snippet above illustrates the class, package, and constructor; it is not a standalone runnable project. Example service with an injected `DatabaseClient`:

```java
@Transactional(transactionManager = "r2dbcTx")
public reactor.core.publisher.Mono<Void> saveAudit(long id) {
    return databaseClient.sql(
                    "INSERT INTO audit_events (id) VALUES (:id)")
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .then();
}
```

An R2DBC transaction runs with the **reactive subscription/context**, not merely at the moment the method returning `Mono` is called. Return the pipeline, keep all participating steps inside the same reactive chain, and do not split off `subscribe()` or switch to uncoordinated JDBC.

### 7.4. MongoDB and Kafka

For MongoDB, `MongoTransactionManager` and `ReactiveMongoTransactionManager` belong to **Spring Data MongoDB**, not Spring JDBC. The Mongo template must share the same `MongoDatabaseFactory` as the manager; the MongoDB deployment must support transactions. For Kafka, `KafkaTransactionManager` belongs to Spring Kafka and manages Kafka producer transactions—it does not manage a `DataSource` by default.

The same `@Transactional` syntax can appear across both modules. **Identical syntax does not mean identical resources and rollback semantics.**

## 8. Multiple Managers: Define Defaults Clearly, Be Explicit at the Right Boundaries

Suppose an application has `ordersJpaTx` and `reportJdbcTx`. If every service method has an unqualified `@Transactional`, it becomes hard to guarantee the right manager is used. Pick a convention:

- **One manager:** configure a single bean and use `@Transactional` when there is no ambiguity.
- **Multiple managers with a genuinely clear default:** configure the default via bean resolution (`@Primary`) or `TransactionManagementConfigurer` depending on version/setup; services using non-default resources still specify `transactionManager` explicitly.
- **Multiple peer managers:** always declare `@Transactional(transactionManager = "...")` at the service boundary so both readers and the framework pick the right manager.

Example setting a default via `TransactionManagementConfigurer` (illustrative fragment inside an `@Configuration` class with `@EnableTransactionManagement`, manager bean already created):

```java
@Override
public org.springframework.transaction.TransactionManager
annotationDrivenTransactionManager() {
    return ordersJpaTxManager;
}
```

The class containing this method must `implements TransactionManagementConfigurer`. Such a default may make sense when most operations use JPA; however, R2DBC, Mongo, or other JDBC datasource services still need their own managers.

**Do not confuse `@Primary` on a `DataSource` with selecting the right transaction manager for all repositories.** `@Primary` only resolves injection/default candidates at specific points; it does not unify resources or make different transactions participate together.

## 9. Situations Easy to Misconfigure

### 9.1. Choosing by Annotation Name Instead of Resource

```java
@Transactional
public void write() {
    // JPA repository...
}
```

There is no basis to infer the manager is `JpaTransactionManager` from the annotation alone. You must know the bean configuration. If the project has a JDBC manager as default while the method uses another JPA persistence unit, flush/transaction state may not be coordinated as expected; depending on provider and operations, it may fail or fail to roll back properly.

### 9.2. Naming a Bean “jpaTransactionManager” While Instantiating a JDBC Manager

```java
@Bean("jpaTransactionManager")
PlatformTransactionManager wrongName(DataSource ds) {
    return new JdbcTransactionManager(ds);
}
```

The bean name is `jpaTransactionManager`, yet the **actual type** is still `JdbcTransactionManager` and it manages a JDBC datasource. Renaming it does not turn it into a JPA manager.

### 9.3. Manager Bound to Datasource A, Repository Bound to Datasource B

```java
@Bean("ordersTx")
PlatformTransactionManager ordersTx(
        @Qualifier("ordersDataSource") DataSource ds) {
    return new JdbcTransactionManager(ds);
}
```

If `JdbcTemplate` inside the method actually uses `reportsDataSource`, that operation does not automatically join `ordersDataSource`'s local transaction. The two configurations must be cross-checked by **bean dependency wiring**, not merely table names or connection strings.

### 9.4. Mixing JPA and JDBC Using Two Local Managers on the Same DB

The JPA repository is managed by `JpaTransactionManager`, while a helper declares `@Transactional("jdbcTx")` and executes JDBC against the same database. Using two managers can create two transaction boundaries or use different resources. Do not expect manager B's `PROPAGATION_REQUIRED` to automatically "join" manager A's transaction. Design **one transaction owner** and ensure data access APIs actually participate.

### 9.5. Two Independent Datasources, Assuming One Annotation Is a Distributed Transaction

```text
@Transactional("ordersTx")
  ├── write orders DB   [local transaction managed by ordersTx]
  └── write billing DB  [outside that manager's scope if using another datasource]
```

To commit both DBs globally with JTA, both must be configured for an XA/JTA coordinator. Otherwise, choose an outbox/saga model or suitable compensation mechanism. Sequential transaction synchronization (commit DB then Kafka) can reduce ordinary errors, but **does not guarantee atomic commit** if one side succeeds and the other fails.

### 9.6. Choosing an R2DBC Manager for an Imperative Method

```java
@Transactional(transactionManager = "r2dbcTx")
public void saveUsingJdbc() {
    // JdbcTemplate.update(...);
}
```

`r2dbcTx` is a `ReactiveTransactionManager`, and a `void` method is imperative. This is a programming model mismatch; it does not create a proper JDBC transaction. You need an imperative `PlatformTransactionManager` with JDBC, or rewrite the operation as a true R2DBC pipeline.

### 9.7. Internal Self-Invocation of a `@Transactional` Method

```java
public void outer() {
    inner(); // self-invocation: does not go through the Spring proxy.
}

@Transactional(transactionManager = "ordersTx")
public void inner() {
    // ...
}
```

In Spring's default proxy mode, calling `this.inner()` does not apply `inner()`'s advice. A common fix is moving the boundary to another bean and calling via an injected Spring bean, or using `TransactionTemplate` where appropriate.

### 9.8. Confusing Rollback Policy with Wrong Manager

Having the right manager is not enough if exceptions are swallowed. By default Spring rolls back on `RuntimeException` and `Error`; checked `Exception`s do not trigger rollback automatically. You can use:

```java
@Transactional(
    transactionManager = "ordersTx",
    rollbackFor = Exception.class
)
public void importOrders() throws Exception {
    // ...
}
```

The method must actually throw the exception out of the boundary, or mark rollback-only via the appropriate API. Returning normally after catching an error can cause Spring to commit.

## 10. Advanced Aspects to Understand Correctly

### `PROPAGATION_REQUIRED` and `REQUIRES_NEW`

`REQUIRED` is the default. Within **the same manager/resource** and called properly through a proxy, an inner method typically joins the active transaction. `REQUIRES_NEW` requests a new transaction, so work committed in the inner transaction can persist even if the outer transaction rolls back. However, two different local managers already manage two separate resource scopes even when both use `REQUIRED`.

When a new transaction is needed, the connection pool must be able to supply an extra connection; otherwise threads can wait on each other and exhaust connections.

### `NESTED`, Savepoints, and Manager Capabilities

`DataSourceTransactionManager`/`JdbcTransactionManager` supports nested transactions based on JDBC savepoints when the driver permits. `JpaTransactionManager` does not automatically turn all JPA operations in a persistence context into independent savepoints; nested JDBC support, when enabled by configuration, still has limitations. Do not assume `NESTED` behaves identically across JPA, Mongo, R2DBC, or JTA.

### Isolation and `readOnly`

Choosing the right manager does not by itself guarantee isolation requirements. `Isolation.SERIALIZABLE` or `READ_COMMITTED` must be supported by the datastore/driver and applied to the real transaction. `readOnly=true` may be used for optimization or rejecting writes by the manager/provider depending on configuration; do not use it in place of write-permission controls.

### Blocking vs Reactive Context

Imperative transactions of `PlatformTransactionManager` typically rely on `ThreadLocal`. Creating new threads, using `CompletableFuture`, or running database operations on external threads does not automatically inherit the transaction. Reactive transactions of `ReactiveTransactionManager` use Reactor `Context`; splitting the processing flow or calling `subscribe()` outside the chain can cause operations to lose the transaction context.

### Local Managers and State Outside the Database

If a method updates the database and then calls an HTTP API, sends an email, or pushes a message, a local transaction cannot automatically roll back external side effects that already occurred. Consider transactional outbox (storing both business data and an event record in the same DB transaction), retrying publishers, and idempotent consumers when cross-system reliability is required.

## 11. Verifying Which Manager Is Being Selected

When debugging unexpected rollback behavior, inspect from bean wiring down to actual runtime behavior.

**Step 1 — list manager beans in the ApplicationContext.** Fragment running in a Spring application that has `applicationContext`:

```java
applicationContext
        .getBeansOfType(
                org.springframework.transaction.TransactionManager.class)
        .forEach((name, manager) ->
                System.out.println(name + " -> "
                        + manager.getClass().getName()));
```

Bean name, actual type, and the `DataSource`/`EntityManagerFactory`/`ConnectionFactory` passed to the constructor are the three details to cross-check. If proxied, the runtime class name may show a proxy class; inspect bean definitions or original configuration when needed.

**Step 2 — trace the method.** Confirm the service method is invoked through a Spring proxy; check which qualifier/`transactionManager` is on the method or class; check where the default is configured; and confirm `@EnableTransactionManagement`/auto-configuration is actually active.

**Step 3 — trace the repository/client.** For JDBC, verify the exact `JdbcTemplate` and `DataSource`. For JPA, verify `EntityManagerFactory` and repository `transactionManagerRef`. For R2DBC, verify `ConnectionFactory` and the reactive pipeline; for Mongo, verify `MongoDatabaseFactory`.

**Step 4 — transaction logging.** In Spring Boot, you can enable diagnostic logs when needed:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.orm.jpa=DEBUG
```

Exact log lines vary across Spring versions, managers, and backends. This configuration is an example for a Spring Boot application's `application.properties`; the pure Maven example in section 6 does not read this Spring Boot file automatically.

**Step 5 — test rollback intentionally.** Insert into the target resource, throw a `RuntimeException` after the insert, and read back from an independent transaction/connection after the method finishes. With two datasources, inspect results in **each database**, not just one table.

### Required Test Matrix

| Test | Expectation |
| --- | --- |
| JDBC service using right manager, exception after 2 inserts on same datasource | Both inserts roll back |
| JPA service using right `JpaTransactionManager`, error after `save`/`flush` | Changes in the same JPA transaction roll back |
| Two independent datasources, two local managers | The already-committed side's transaction is not rolled back by the other manager |
| Manager bound to A while DAO uses B | Mismatch detected; do not claim B is rolled back by manager A |
| Reactive R2DBC method returning `Mono` and joining right `ConnectionFactory` | Operations in the reactive transaction roll back when the pipeline errors |
| `@Transactional` self-invocation | Verify whether advice activates or is bypassed |
| Checked exception escaping method | Confirm `rollbackFor` configuration reflects business requirements |
| Spring Data JPA multiple persistence units | Repository bound to the right factory and `transactionManagerRef` |

Do not test only the happy path: a transaction is only clearly verified by failing mid-way and observing commit/rollback outcomes on the exact resources.

## 12. Practical Selection Checklist

- [ ] Identified all data that must commit/roll back together.
- [ ] Identified the actual API and factory: JDBC `DataSource`, JPA `EntityManagerFactory`, R2DBC `ConnectionFactory`, MongoDB `MongoDatabaseFactory`, Kafka `ProducerFactory`.
- [ ] Actual manager has the right type and is wired to the right factory.
- [ ] DAOs/templates/repositories participate in the resource managed by that manager.
- [ ] `@Transactional` selects the right bean via a clearly defined default or `transactionManager`/qualifier.
- [ ] Distinguished imperative `PlatformTransactionManager` and reactive `ReactiveTransactionManager`.
- [ ] Clearly understood propagation, rollback rules, proxy/self-invocation, and exception handling.
- [ ] If multi-resource atomic commit is required, designed XA/JTA or an appropriate consistency solution; not relying on annotations.
- [ ] Have integration tests proving rollback when an error occurs mid-way across multiple operations.
- [ ] When JPA + JDBC share a database, verified `JpaTransactionManager`'s JDBC participation conditions.

## 13. Key Takeaway and Self-Check Questions

**One sentence worth memorizing:** *`@Transactional` describes transactional intent; `TransactionManager` executes that intent on a specific kind of resource; only operations participating in the resource actually managed by that manager receive its commit/rollback boundary.*

Self-check:

1. A `@Transactional` method uses `JpaRepository`, yet the actual `transactionManager` bean is `JdbcTransactionManager`. Which configurations should you check before trusting rollback?
2. Two methods both use `@Transactional("orders")`, while the `orders` bean is `R2dbcTransactionManager`. One method returns `Mono<Void>`, the other returns `void`. Which method fits the manager better, and why?
3. A method writes to databases A and B. When A and B use two local transaction managers, can an error after B commits roll back B?
4. A service calls a JPA repository and `JdbcTemplate` on the same datasource. When can `JpaTransactionManager` manage both?
5. Why does renaming `@Transactional("jpa")` to `@Transactional("jdbc")` not solve a resource misconfiguration?

Key answer: inspect **actual manager bean → manager's factory/resource → DAO's factory/resource → imperative/reactive model → boundaries and rollback rules**. An annotation name or bean name alone is never enough to prove what committed or rolled back.

## Official References

- [Spring Framework — Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): distinguishing `PlatformTransactionManager` and `ReactiveTransactionManager`.
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): proxies, `TransactionInterceptor`, imperative vs reactive.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): qualifier/`transactionManager`, multiple managers, propagation, and rollback.
- [Spring Framework — Controlling JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `JdbcTransactionManager`, `DataSourceTransactionManager`, `DataSourceUtils`.
- [Spring Framework — `JpaTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html): EntityManagerFactory, conditions for JDBC participation on the same datasource.
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): `R2dbcTransactionManager` and connections in Reactor Context.
- [Spring Data MongoDB — Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager`.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): `KafkaTransactionManager` and boundaries combining database/Kafka.
