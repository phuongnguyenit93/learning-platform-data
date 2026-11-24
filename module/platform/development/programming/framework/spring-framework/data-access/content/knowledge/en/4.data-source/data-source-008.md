# Injecting the Right DataSource When an Application Has Multiple Sources

## Objectives and Scenario

A Spring application may work with two databases: **orders** holding customer orders and **audit** holding business audit logs. Both sources are represented by the `javax.sql.DataSource` interface. When a Spring container holds multiple beans of type `DataSource`, dependency injection (DI) must specify **which bean serves which data access path**.

After this lesson, you can:

1. Recognize ambiguous data source injection errors and why picking the wrong source is more dangerous than a startup failure.
2. Distinguish bean names, `@Qualifier`, and `@Primary` when injecting `DataSource`, `JdbcTemplate`, or repositories.
3. Configure and run a Java 17+ example with two independent H2 databases, verifying data goes to the right place.
4. Choose the right transaction manager for each source and recognize transaction boundaries when one business operation touches two databases.
5. Apply the same principles to Spring Data JPA and Spring Boot without confusing auto-configuration with DI.

The focus of this lesson is **accurate data source selection at injection points**. Pool tuning, JPA mapping details, distributed transactions, and multi-tenant routing are mentioned only when needed to avoid practical mistakes.

## 1. Why Does Having Multiple DataSources Easily Lead to Wrong Injection?

`DataSource` is a JDBC interface providing `Connection`. It does not carry business names like "orders" or "audit" in Java's type system. Two beans like these share the exact same type:

```java
DataSource ordersDataSource;
DataSource auditDataSource;
```

If another bean requests by type without an identifier:

```java
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
```

Spring finds multiple `DataSource` candidates. Without a mechanism to select a unique one, the application typically fails startup—for example with `NoUniqueBeanDefinitionException` or an unsatisfied dependency error. Yet if `@Primary` or another resolution mechanism is present, Spring may pick a candidate that is **valid for DI but wrong for business logic**.

Commonly encountered situations:

- `OrderRepository` writes order data into the audit database because it received the wrong `DataSource`.
- Both databases have a `users` table, so the SQL runs without error even though it reads the wrong user set.
- `JdbcTemplate` uses the orders source, while `@Transactional` manages transactions on the audit source. An error occurs, yet orders operations do not roll back as the author expected.
- Local has only one database, whereas staging/production has two sources and different bean configurations.

**Principle:** establish source identity end-to-end from `DataSource → JdbcTemplate/EntityManagerFactory → Repository → TransactionManager`; verify this chain with tests and real connections.

## 2. Bean Names, @Qualifier, and @Primary

### 2.1. Bean Name Is the Identity of a Source

Declare `@Bean("ordersDataSource")` for the orders connection bean and `@Bean("auditDataSource")` for audit. Names should reflect the source's stable role; avoid `dataSource1` and `dataSource2`.

The bean-naming example below only illustrates syntax, **not standalone runnable code**, because the connection-source creation methods are omitted:

```java
@Bean("ordersDataSource")
DataSource ordersDataSource() {
    return createOrdersDataSource();
}

@Bean("auditDataSource")
DataSource auditDataSource() {
    return createAuditDataSource();
}
```

Bean names tell readers which database is used at each configuration site; they also aid finding the exact bean in `ApplicationContext` and in tests.

### 2.2. @Qualifier Selects a Bean Right at the Injection Point

`@Qualifier` narrows candidates by the specified qualifier/bean name. Example:

```java
@Bean("auditJdbc")
JdbcTemplate auditJdbc(
        @Qualifier("auditDataSource") DataSource source) {
    return new JdbcTemplate(source);
}
```

When the application has two `DataSource` beans, this `auditJdbc` method still receives `auditDataSource`. The same qualifier can be used in constructors:

```java
public AuditRepository(
        @Qualifier("auditJdbc") JdbcTemplate jdbc) {
    this.jdbc = jdbc;
}
```

The constructor snippet assumes the class has a `jdbc` field; see the runnable example in Section 4. If a class has a single constructor and is managed by Spring, adding `@Autowired` is normally unnecessary.

**Qualify the intermediate layer too.** Naming two `DataSource`s and building two `JdbcTemplate`s of the same type is not enough: repositories must still receive the right template. `@Qualifier` is placed at the **injection point**, not only where beans are defined.

`@Qualifier` does not switch connections on every SQL execution. It routes **the dependency to the selected bean at initialization time**; a `JdbcTemplate` uses the `DataSource` configured for it, unless that source actively implements a routing mechanism.

### 2.3. @Primary Designates One Default Choice

`@Primary` marks a bean to be preferred when multiple candidates of the same type exist and the injection point has no more specific selector. For instance:

```java
@Bean("ordersDataSource")
@Primary
DataSource ordersDataSource() {
    return createOrdersDataSource();
}
```

This is also just an illustrative snippet, because `createOrdersDataSource()` is not defined here.

Marking orders as primary can be appropriate when it is the agreed default source for most of the application. However:

- An injection point with `@Qualifier("auditDataSource")` still selects audit, even when orders is primary.
- `@Primary` on `DataSource` **does not automatically make** `ordersJdbc` primary among `JdbcTemplate` beans.
- Similarly, `@Primary` on a connection source **does not automatically select** the corresponding transaction manager for every `@Transactional`.
- Using `@Primary` merely to make an error disappear can hide a miswired data access path.

When two sources have equal standing, explicit qualifiers at each point needing a source are usually easier to audit than enforcing a default.

### 2.4. Do Not Rely on Variable or Parameter Names

Spring can consider parameter/bean names when resolving autowiring under certain rules, but that depends on compilation metadata and how beans are registered. Renaming a parameter or tweaking compiler settings can produce unexpected results.

For important sources, specify `@Qualifier("ordersDataSource")` or `@Qualifier("auditDataSource")` directly at the injection point. This expresses business intent without relying on variable name coincidence.

## 3. Designing the Bean Flow Before Coding

Two fixed data sources can be organized as follows:

```text
                         Spring ApplicationContext
                                     |
                +--------------------+--------------------+
                |                                         |
                v                                         v
        ordersDataSource                           auditDataSource
                |                                         |
                | @Qualifier("ordersDataSource")          | @Qualifier("auditDataSource")
                v                                         v
            ordersJdbc                                auditJdbc
                |                                         |
                | @Qualifier("ordersJdbc")                | @Qualifier("auditJdbc")
                v                                         v
         OrdersRepository                          AuditRepository
                |                                         |
                +--------------------+--------------------+
                                     |
                                Business Service
                         (decides the right use case)
```

Four responsibilities to keep clear:

1. **Connection source:** each `DataSource` represents a JDBC configuration source (URL, credentials, driver, pool). A `DataSource` bean can also be a router if intentionally designed that way; this example uses no router.
2. **Query tool:** `JdbcTemplate` receives a source via constructor. With two independent sources, creating a separate template for each makes identification clear.
3. **Repository:** each repository encapsulates the SQL/mapping of one data domain and receives the matching template. Services call repositories per business need rather than picking beans arbitrarily by name.
4. **Transactions:** a transaction manager must match the datasource of the operations it manages; this is a **separate** link from repository wiring.

If configuration is complex, draw a mapping table of connection source → bean → template → repository → manager and cross-check against actual database URLs/schemas.

## 4. Runnable Example: Two H2 Databases with Spring Framework

The example uses **Java 17+**, Spring Framework **6.2.x**, Gradle, and in-memory H2. It simultaneously demonstrates two `DataSource`s, two `JdbcTemplate`s, and two repositories. No Spring Boot, HTTP server, or external database installation is required.

Structure:

```text
multi-data-source-demo/
├── build.gradle
└── src/main/java/example/MultiDataSourceDemo.java
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.MultiDataSourceDemo'
}
```

Contents of `src/main/java/example/MultiDataSourceDemo.java`:

```java
package example;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration
public class MultiDataSourceDemo {

    // Same DataSource type but two different database addresses.
    @Bean("ordersDataSource")
    DataSource ordersDataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:orders_db;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean("auditDataSource")
    DataSource auditDataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:audit_db;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    // Select target via qualifier, not relying on a default bean.
    @Bean("ordersJdbc")
    JdbcTemplate ordersJdbc(
            @Qualifier("ordersDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean("auditJdbc")
    JdbcTemplate auditJdbc(
            @Qualifier("auditDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    // Both JdbcTemplates also share the same type: must pick the right template.
    @Bean
    OrdersRepository ordersRepository(
            @Qualifier("ordersJdbc") JdbcTemplate jdbc) {
        return new OrdersRepository(jdbc);
    }

    @Bean
    AuditRepository auditRepository(
            @Qualifier("auditJdbc") JdbcTemplate jdbc) {
        return new AuditRepository(jdbc);
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                MultiDataSourceDemo.class)) {

            OrdersRepository orders =
                    context.getBean(OrdersRepository.class);
            AuditRepository audit =
                    context.getBean(AuditRepository.class);

            orders.createTable();
            audit.createTable();

            orders.save(10L, "PAID");
            audit.append(10L, "order-created");

            System.out.println("orders/10=" + orders.findStatus(10L));
            System.out.println("audit/10=" + audit.findEvent(10L));
        }
    }

    static final class OrdersRepository {
        private final JdbcTemplate jdbc;

        OrdersRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        void createTable() {
            jdbc.execute("""
                    CREATE TABLE orders (
                        id BIGINT PRIMARY KEY,
                        status VARCHAR(30) NOT NULL
                    )
                    """);
        }

        void save(long id, String status) {
            jdbc.update(
                    "INSERT INTO orders (id, status) VALUES (?, ?)",
                    id, status);
        }

        String findStatus(long id) {
            return jdbc.queryForObject(
                    "SELECT status FROM orders WHERE id = ?",
                    String.class, id);
        }
    }

    static final class AuditRepository {
        private final JdbcTemplate jdbc;

        AuditRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        void createTable() {
            jdbc.execute("""
                    CREATE TABLE audit_events (
                        id BIGINT PRIMARY KEY,
                        event_name VARCHAR(100) NOT NULL
                    )
                    """);
        }

        void append(long id, String eventName) {
            jdbc.update(
                    "INSERT INTO audit_events (id, event_name) VALUES (?, ?)",
                    id, eventName);
        }

        String findEvent(long id) {
            return jdbc.queryForObject(
                    "SELECT event_name FROM audit_events WHERE id = ?",
                    String.class, id);
        }
    }
}
```

Run in the project directory:

```bash
gradle run
```

If Gradle Wrapper is present, you can run `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows. Gradle prints its own logs; **stdout printed by the Java program** is two lines:

```text
orders/10=PAID
audit/10=order-created
```

Why the example hits the right sources:

- `ordersDataSource` connects to `jdbc:h2:mem:orders_db;DB_CLOSE_DELAY=-1`, and `auditDataSource` to `jdbc:h2:mem:audit_db;DB_CLOSE_DELAY=-1`. These are two separate H2 databases in the same JVM.
- `ordersJdbc` is injected with the orders source; `auditJdbc` is injected with the audit source. `OrdersRepository` receives only `ordersJdbc`, and `AuditRepository` receives only `auditJdbc`.
- Repositories are created via `@Bean`. Neither `@Repository` nor component scanning is needed in this program.
- There is no `@Primary`: if a new component requests an unqualified `DataSource`, the missing-unique-candidate error catches that it failed to select a source.
- `DriverManagerDataSource` opens connections on demand, fine for small examples but **not a pool for production**.
- With the H2 URL `DB_CLOSE_DELAY=-1`, the in-memory database survives across connection closes within the same JVM; data disappears when the JVM exits.

### 4.1. Checking the Actual URL Used by a Template

Bean names can be misnamed. To verify the actual underlying source, you can use JDBC metadata via `JdbcTemplate`:

```java
import org.springframework.jdbc.core.ConnectionCallback;

// Example is a snippet where ordersJdbc and auditJdbc variables already exist.
String ordersUrl = ordersJdbc.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getURL());

String auditUrl = auditJdbc.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getURL());
```

This is an **illustrative snippet**, not a standalone Java file. Both URLs must point to their intended sources; also check the active catalog/schema and seed data if multiple databases share identical table names. Never print connection URLs with embedded secrets or sensitive data in production logs.

## 5. Constructor Injection and the Role of Repositories

When a repository accepts dependencies via constructor, the source is forced to be resolved when Spring creates the bean. This supports `final` fields, unit testing, and easier dependency tracing than field injection.

**Snippet** example for a project using component scanning:

```java
@Repository
public class AuditRepository {
    private final JdbcTemplate jdbc;

    public AuditRepository(
            @Qualifier("auditJdbc") JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Audit data operations all use this same jdbc.
}
```

Requires importing `Repository`, `Qualifier`, and `JdbcTemplate`. `@Repository` lets Spring detect the component during package scanning; it **does not automatically know which database is right**, and does not replace `@Qualifier`. In Section 4, repositories were already registered with `@Bean`, so do not combine component scanning for those same repositories.

If multiple query layers are used, select the source where adapters/repositories are built and then inject **business-meaningful repositories** into services. Do not let controllers or individual SQL calls call `ApplicationContext.getBean("...")`, as that hides dependencies and hurts testability.

## 6. Comparison Table When Multiple Sources Exist

| Orders | Audit | Role |
| --- | --- | --- |
| `ordersDataSource` | `auditDataSource` | JDBC source, URL/credentials/driver/pool |
| `ordersJdbc` | `auditJdbc` | `JdbcTemplate` using each source |
| `OrdersRepository` | `AuditRepository` | Queries/writes data for the corresponding domain |
| `ordersTransactionManager` | `auditTransactionManager` | Transaction manager bound to the source |
| `app.datasource.orders.*` | `app.datasource.audit.*` | Example property prefix for externalized config |

To catch miswiring, compare **the entire chain**, not just the `@Bean` declarations of the two DataSources.

### 6.1. Externalized Configuration and Connection Pools

In real systems, URL, username, password, and pool sizes should come from configuration/environment variables or a secret manager. The YAML example below only illustrates two property prefixes; **Spring Framework does not automatically create two DataSources just because YAML exists**:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://orders-db:5432/orders
      username: orders_app
      password: ${ORDERS_DB_PASSWORD}
    audit:
      url: jdbc:postgresql://audit-db:5432/audit
      username: audit_app
      password: ${AUDIT_DB_PASSWORD}
```

With Spring Boot, you need corresponding bean/configuration binding—for example `@ConfigurationProperties` combined with `DataSourceProperties` or building the pool from properties. When using HikariCP directly, it has the `jdbcUrl`/`jdbc-url` property rather than a plain `url` JavaBean property; `DataSourceProperties` handles this mapping in the right configuration style. Read the documentation for your exact Spring Boot version.

Production should use an appropriate connection pool (such as HikariCP) **for each source**, setting separate pool sizes, timeouts, health checks, metrics, and access privileges. Do not mechanically copy pool settings from a large database to a small one.

## 7. Choosing the Right Transaction Manager per Source

This is an often overlooked bug: **injecting the right `JdbcTemplate` does not automatically ensure `@Transactional` coordinates the right database**.

A Spring JDBC configuration can declare separate managers for orders and audit. The snippet below is **supplementary configuration** in a project that already has `ordersDataSource` and `auditDataSource`, not a standalone compilable file:

```java
@Configuration
@EnableTransactionManagement
public class TransactionConfiguration {

    @Bean("ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean("auditTransactionManager")
    PlatformTransactionManager auditTransactionManager(
            @Qualifier("auditDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }
}
```

Imports for the snippet above:

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
```

`JdbcTransactionManager` is a JDBC transaction manager for a single `DataSource`. `DataSourceTransactionManager` is also a common choice; `JdbcTransactionManager` adds the ability to translate certain commit/rollback exceptions in the Spring JDBC model.

A service method chooses a manager via `@Transactional`:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void markOrderPaid(long orderId) {
    ordersRepository.updateStatus(orderId, "PAID");
}
```

The method above is **illustrative** only, assuming `ordersRepository` is valid and the code sits in a Spring-managed service. The default transaction mechanism is proxy-based, so external calls through the Spring bean proxy are intercepted to apply transactions; self-invocation (`this.markOrderPaid(...)`) normally bypasses advice.

Points to grasp:

1. The orders manager must use **the exact DataSource** that `ordersJdbc` uses; the audit manager must match `auditJdbc`.
2. A local JDBC manager only manages transactions on its corresponding source; it does not automatically span other connections.
3. With multiple transaction managers, specify `@Transactional(transactionManager = "...")` in business methods that must explicitly select a source instead of guessing a default.
4. `@Transactional(readOnly = true)` does not automatically pick a replica or switch a template from orders to audit. It is a transaction attribute; read/write routing requires dedicated routing configuration and replica lag checks.
5. Use `JdbcTemplate`/`DataSourceUtils` properly to participate in Spring-managed transactions. Acquiring a connection directly with `dataSource.getConnection()` outside Spring synchronization may fail to join the expected transaction.

### 7.1. Writing to Both Databases Is Not One Shared Transaction

Suppose a service writes order status to the orders database and then appends an event to the audit database. Orders may commit while audit fails if the two sources use independent local transactions. Creating two `PlatformTransactionManager` beans, adding `@Transactional`, or marking a primary source **does not automatically create an atomic commit across two databases**.

If the business requires cross-source consistency, you must choose another strategy based on requirements: transactional outbox with idempotent/retried event processing, saga/compensation, asynchronous reconciliation, or XA/JTA distributed transactions when infrastructure and trade-offs fit. This is a transaction and reliability design problem, not just a bean selection bug.

### 7.2. Do Not Confuse JDBC and JPA Transaction Managers

In the JDBC example, `JdbcTransactionManager` manages a `DataSource`. With **JPA**, each `EntityManagerFactory` typically needs a matching `JpaTransactionManager`. Using a JDBC manager and expecting it to cover every JPA persistence context, or using one JPA manager for two entity manager factories, is an invalid assumption.

```text
Spring JDBC:  DataSource -> JdbcTemplate -> Repository
                   ^
                   |
             JDBC TransactionManager

Spring JPA:   DataSource -> EntityManagerFactory -> JPA Repository
                               ^
                               |
                          JpaTransactionManager
```

The transaction manager is a component that must be wired accurately in the diagram, not just an annotation placed on a service.

## 8. With Spring Data JPA, a Qualifier on DataSource Is Not Enough

A system with two groups of JPA repositories needs separate configuration:

- `DataSource` for each group.
- `EntityManagerFactory` bound to the corresponding source, with proper entity packages and persistence configuration.
- `JpaTransactionManager` for each factory.
- `@EnableJpaRepositories` with matching `basePackages`, `entityManagerFactoryRef`, and `transactionManagerRef`.

**Illustrative annotation snippet** for the orders slice, not a complete class:

```java
@EnableJpaRepositories(
    basePackages = "example.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager")
```

A matching configuration must apply to audit, pointing to `auditEntityManagerFactory` and `auditTransactionManager`. Do not let both scan configurations overlap the same repository package or default to the wrong persistence unit. Putting `@Primary` on `DataSource` does not guarantee JPA repositories wire themselves properly.

Schema migrations (Flyway/Liquibase or equivalent workflows) must also target the right database; avoid misconfigurations that run orders migrations on audit.

## 9. Spring Boot Auto-Configuration Must Be Verified

Spring Boot provides auto-configuration for `DataSource`, pools, `JdbcTemplate`, and JPA, but **does not automatically understand arbitrary custom property prefixes** like `app.datasource.orders.*` and `app.datasource.audit.*`. When adding a second source, answer three questions:

1. **Which beans does Boot create?** Once the application declares a `DataSource` itself, auto-configuration conditions can change depending on the version. Read the exact version's docs rather than assuming Boot still creates any missing default source.
2. **Which is the default?** Some auto-configurations require a default source, typically distinguished by `@Primary`. In newer Boot versions, bean `defaultCandidate` mechanics can also affect interactions with auto-configuration. The direct Spring Framework code in Section 4 does not depend on that Boot behavior.
3. **Who creates the upper-layer beans?** Having two `DataSource`s does not guarantee Boot auto-creates two `JdbcTemplate`s, two transaction managers, and two `EntityManagerFactory`s. Inspect configuration at every layer.

Inspect the active bean list from `ApplicationContext` or Boot observability tools if enabled, alongside property bindings, connection URLs, and integration tests exercising each repository. Do not draw conclusions merely because `application.yml` lists two endpoints.

## 10. Testing to Catch Misrouted Sources

### 10.1. Integration Tests with Distinguishable Data

Create two independent test databases or schemas; seed distinct data:

- Orders holds `order id=10`, `status=PAID`.
- Audit holds event `id=10`, `event_name=order-created`.
- Read through the corresponding repository and verify results.
- When both databases have identically named tables, deliberately seed **different** data so accidental cross-reads are still caught.
- For write operations, verify the record appears in the target source and does not appear in the wrong source.

Section 4 shows two separate H2 databases. For systems running on PostgreSQL/MySQL, write integration tests against the matching DBMS or database containers to catch schema, driver, and transaction differences.

### 10.2. Verifying Beans Are Wired Accurately

In applications using `JdbcTemplate` directly as in the example, you can use `JdbcTemplate#getDataSource()` to compare against the expected bean. **Test snippet** pattern, not a complete JUnit class:

```java
assertSame(
    context.getBean("ordersDataSource", DataSource.class),
    context.getBean("ordersJdbc", JdbcTemplate.class).getDataSource()
);

assertSame(
    context.getBean("auditDataSource", DataSource.class),
    context.getBean("auditJdbc", JdbcTemplate.class).getDataSource()
);
```

`assertSame` comes from `org.junit.jupiter.api.Assertions`; the snippet assumes the `context` variable and Section 4 beans exist. With proxies/wrappers or routing datasources, identity comparison is not always sufficient; also verify the connection URL, schema/catalog, and actual data.

### 10.3. Testing Failure Cases

- Temporarily remove a qualifier in a test when two candidates exist and no default is set: verify the container fails clearly rather than picking arbitrarily.
- Swap qualifiers of `ordersJdbc`/`auditJdbc` in a test environment: integration tests must catch it via missing tables or wrong contents.
- Trigger rollback on an orders transaction and verify only orders data inside that transaction scope is reverted.
- Simulate the audit source losing connectivity and verify business logic executes retry/outbox or handles inconsistency as designed.
- Use separate least-privilege DB accounts so a misrouted connection is less able to write to the wrong tables.
- Verify each profile (local/test/staging/production) binds the right URL/secret, without trusting plausible-looking bean names.

Do not log passwords, URLs containing secrets, or sensitive data for "quick debugging".

## 11. Common Errors

| Symptom | Possible Cause | How to Check/Fix |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` for `DataSource` | Two beans of the same type without selection at the injection point. | Add a qualifier or designate a primary with clear business meaning. |
| No DI error yet queries hit the wrong database | Wrong qualifier, primary, or bean name at one layer. | Audit the full chain DataSource → template/factory → repository and actual URL/schema. |
| `NoUniqueBeanDefinitionException` for `JdbcTemplate` | Datasources were split, yet the two templates were not distinguished when injected. | Qualify `ordersJdbc` and `auditJdbc` at repositories. |
| `@Repository` still uses the wrong source | Stereotype annotations do not choose a DataSource. | Qualify template/EntityManagerFactory; check repository scanning. |
| `@Transactional` does not roll back as expected | Wrong transaction manager or call bypassing proxy. | Check the manager bound to the same source and calls going through Spring beans. |
| Orders commits while audit fails | Two local transactions do not form a shared atomic commit. | Pick a cross-source consistency model and test failures/retries. |
| Used `@Primary` and now all queries go to orders | Default masks audit's need to pick its own source. | Put explicit qualifiers on audit consumers; avoid arbitrary defaults. |
| Works locally, fails in production | Different profiles, property prefixes, secrets, pools, or schemas. | Inspect actual beans/properties in each environment. |
| Spring Data JPA queries wrong persistence unit | Wrong repository scan or EntityManagerFactory/manager ref. | Separate packages and configure `entityManagerFactoryRef`/`transactionManagerRef`. |
| `readOnly=true` does not use replica automatically | Confusing read-only transactions with routing mechanics. | Design dedicated routing/replica selection and measure replication lag. |

## 12. Checklist When Adding a New Source

1. Name and document each `DataSource`'s responsibility; record URL, schema, driver, credentials, privileges, and pool.
2. Configure the actual source to fit the project's Spring Framework or Spring Boot version.
3. Define the corresponding template or EntityManagerFactory; use `@Qualifier` at every multi-candidate injection point.
4. Keep repositories tied to clear sources; inject only the necessary repositories into services.
5. Configure matching transaction managers; never treat two local managers as one distributed transaction.
6. Test every read/write path and rollback with distinct data between the two sources.
7. Monitor health, pool metrics, query timeouts, migrations, and separate privileges; include misrouting checks before deployment.

## 13. Self-Check Questions

1. Why can Spring not infer on its own that `OrderRepository` needs `ordersDataSource` solely from the `DataSource` interface?
2. How does `@Qualifier("auditJdbc")` on a constructor differ from `@Primary` on `ordersDataSource`?
3. If two `DataSource`s are already created clearly, why is it still necessary to distinguish the two `JdbcTemplate`s?
4. In the H2 program, which bean determines that `orders.save(...)` goes into `orders_db`?
5. Why does `ordersTransactionManager` not automatically roll back a statement executed by `auditJdbc`?
6. With two-source JPA, what additional components must be configured?
7. What test catches a misrouted source error when both databases contain tables with the same name?

**Remember:** `@Qualifier` clarifies **which DataSource or template is injected** at each dependency; `@Primary` is only a default when a single main source genuinely exists. After selecting the right JDBC/JPA repository, you must choose the matching **transaction manager** and verify with integration tests across two independent sources.

### Official References

- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Framework — Using @Qualifier](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html).
- [Spring Framework — Fine-tuning with @Primary](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html).
- [Spring Framework — Using @Transactional and Multiple Transaction Managers](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- [Spring Boot — Data Access / Configure Two DataSources](https://docs.spring.io/spring-boot/how-to/data-access.html); select the exact Boot version your project uses.
