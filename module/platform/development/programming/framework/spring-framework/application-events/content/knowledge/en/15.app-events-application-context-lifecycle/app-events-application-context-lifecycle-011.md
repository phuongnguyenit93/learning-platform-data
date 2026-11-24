# Data Initialization Listeners in the ApplicationContext Lifecycle

## 1. Problem and scope

When a Spring application starts running, certain data needs to be present before primary features are used: order status catalogs, default role groups, reference configuration codes, or a stable lookup table. You can write a **data initialization listener** to perform this task when `ApplicationContext` completes its initialization phase.

For example: an authorization system must always have two roles `ADMIN` and `VIEWER`. The preparation task must ensure:

- When the application runs for the first time, both records are created with defined business keys.
- When the application restarts, data is not duplicated.
- If part of the data write operation fails, no half-finished state is left behind.
- If parent–child contexts exist or the event is observed multiple times, the listener does not accidentally seed the wrong context.
- When seeding is a mandatory precondition for serving requests, failures must be detected before the application is considered ready.

This lesson is about **data initialization listeners in the ApplicationContext lifecycle event group**. Do not confuse it with business events like `OrderCreated` or with updating database schemas via migrations.

### Mental flow

~~~text
ApplicationContext.refresh()
        |
        +-- register bean definitions, create required singletons
        +-- finish refreshing context
        |
        +-- ContextRefreshedEvent
                 |
                 +-- @EventListener
                          |
                          +-- check source context
                          +-- run seed in transaction
                          +-- write/reconcile data by stable key
                          +-- complete or report error
~~~

`ContextRefreshedEvent` is the point Spring Framework provides to know a context has finished refreshing. Regular listeners run synchronously by default, so if a listener performs heavy work, it prolongs startup time. Choosing it must be based on the application's real startup contract.

## 2. Why choose ContextRefreshedEvent?

Spring Framework has four representative lifecycle events extending `ApplicationContextEvent`:

| Event | When published | Suitable for seeding data? |
| --- | --- | --- |
| `ContextRefreshedEvent` | Context finishes refreshing | Can be suitable for small seeds needing initialized beans |
| `ContextStartedEvent` | Explicit `context.start()` call | Usually not suitable: not present on every startup |
| `ContextStoppedEvent` | `context.stop()` call | No: used for observing stops |
| `ContextClosedEvent` | During `context.close()` | No: this is shutdown time, dependencies are terminating |

A simple listener:

~~~java
@Component
public class ReferenceDataListener {
    private final ReferenceDataService referenceDataService;

    public ReferenceDataListener(ReferenceDataService referenceDataService) {
        this.referenceDataService = referenceDataService;
    }

    @EventListener
    public void onContextRefreshed(ContextRefreshedEvent event) {
        referenceDataService.ensureDefaults();
    }
}
~~~

This is **illustrative code in an existing project** with `ReferenceDataService` and component scanning configured; you need to import `Component`, `EventListener`, and `ContextRefreshedEvent`. Spring infers the event from the parameter type. `ReferenceDataService.ensureDefaults()` should have a safe re-runnable contract.

According to Spring Framework documentation, listeners on `ContextRefreshedEvent` or `SmartInitializingSingleton` are useful options for work that needs to run **after the singleton initialization phase**, avoiding putting too many complex operations into `@PostConstruct` while beans are still being constructed. Even so, `ContextRefreshedEvent` only indicates **the container has refreshed**; it does not mean all external services are ready or that Spring Boot has published `ApplicationReadyEvent`.

**Warning about once-only execution:** some contexts may support re-refreshing; a parent context may receive events published by a child context. Therefore, do not treat `ContextRefreshedEvent` as an "execute strictly once across the whole cluster" mechanism.

## 3. Distinguishing data seeding from schema migration and bean initialization

Three needs are often mixed together:

1. **Table structure changes:** creating tables, columns, indexes, foreign keys, schema versions. Use dedicated migration tools like Flyway or Liquibase in real operations.
2. **Creating stable reference data:** inserting or synchronizing records with defined business keys, e.g., `ADMIN` and `VIEWER`. This can live in versioned migrations, deployment scripts, or an idempotent seed service.
3. **Initializing in-memory state of a bean:** building internal caches, validating configuration, preparing data structures. Consider constructors, `@PostConstruct`, init methods, or `SmartInitializingSingleton` depending on dependencies and timing.

For reference data that is **mandatory and versioned** (such as a standard lookup code set accompanying the schema), migrations containing data may be easier to control than a repeatedly running listener. A listener fits when seeding is a runtime step with clear rules, safe to execute multiple times, and not dependent on running a script strictly once.

A seed listener should not assume required tables are always created merely because `ContextRefreshedEvent` arrived. In Spring Boot, the initialization ordering of databases, Flyway/Liquibase, SQL initializers, JPA, and dependent beans must be configured/verified specifically. If seeding must happen after migrations, express real dependencies or place seeding in an explicitly orchestrated initialization step.

## 4. Designing the listener right: idempotency, transactions, business keys

### 4.1. What does idempotent mean?

A seed operation `S` is **idempotent with respect to target state** when applying it multiple times produces no unintended additional data effects:

~~~text
S(database) = database_with_complete_standard_data
S(S(database)) = S(database)
~~~

Example data to guarantee:

| code | label |
| --- | --- |
| `ADMIN` | Administrator |
| `VIEWER` | Read-only |

If an unconditional `INSERT` runs on every refresh, subsequent runs can fail with duplicate keys or increase record counts. To seed safely:

- Identify a stable **natural key or business key**, such as `code`; create a `UNIQUE`/`PRIMARY KEY` in the database.
- Use **upsert** in the database dialect (e.g., `MERGE` in H2 or `ON CONFLICT` in PostgreSQL) when the policy is "ensure data exists/has the right values".
- If data can be edited by users, clearly define which columns are system-owned; never accidentally overwrite user values on every restart.
- Use transactions so records needing consistency commit/rollback together.
- Test first run, re-run, missing-row recovery, and multiple instances starting simultaneously.

State idempotency **does not automatically guarantee every side effect runs strictly once**. If seeding also sends emails, each listener execution may send a new email even when the database did not change.

### 4.2. Why is a transaction necessary?

Suppose seeding must create two roles at once. If inserting the first role succeeds but inserting the second fails, we want a clear policy: roll back both or allow filling in later. For mandatory seeds needing atomicity, a shared transaction is usually created.

You can use `@Transactional` on a **service invoked by Spring via proxy**, or use `TransactionTemplate`. Placing the transaction on the service containing seed business logic is easier to test than depending on proxy details of the listener.

~~~java
@Service
public class BootstrapService {
    @Transactional
    public void ensureDefaults() {
        roleRepository.upsert("ADMIN", "Administrator");
        roleRepository.upsert("VIEWER", "Read-only");
    }
}
~~~

This snippet is **illustrative** because `roleRepository.upsert(...)` is an application-defined API, not a default Spring Data method. For transactions to actually apply, a transaction manager must exist, the method must be called through a suitable proxy, and the data resource must participate in the same transaction. By default, Spring rolls back on `RuntimeException` or `Error`; checked exceptions need explicit rollback rules if desired.

## 5. Runnable Java 17+ example: seeding safely on ContextRefreshedEvent

This example uses Spring Framework 6.2.8, Spring JDBC, and in-memory H2, **without requiring Spring Boot**. It illustrates:

- Registering the listener bean before context refresh.
- Using `@EventListener` to receive `ContextRefreshedEvent`.
- Checking the exact event-publishing context.
- Seeding two roles inside one JDBC transaction.
- Using `MERGE` in **H2** syntax so re-running preserves exactly two records.
- Publishing a **simulated** event to test idempotency; simulating an event **does not** refresh the context a second time.

### 5.1. Directory structure

~~~text
context-seed-demo/
├── pom.xml
└── src/main/java/ContextSeedDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-seed-demo</artifactId>
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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>ContextSeedDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. Complete source code

File `src/main/java/ContextSeedDemo.java`:

~~~java
import javax.sql.DataSource;

import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class ContextSeedDemo {

    // Prepare schema dedicated to the demo program.
    // Real applications should manage schemas with Flyway or Liquibase.
    public static class DemoSchema {
        public DemoSchema(JdbcTemplate jdbc) {
            jdbc.execute(
                "CREATE TABLE role_catalog ("
                + "code VARCHAR(20) PRIMARY KEY, "
                + "label VARCHAR(100) NOT NULL)"
            );
        }
    }

    public static class SeedOnRefresh {
        private final ApplicationContext owner;
        private final JdbcTemplate jdbc;
        private final TransactionTemplate transaction;

        public SeedOnRefresh(
                ApplicationContext owner,
                JdbcTemplate jdbc,
                TransactionTemplate transaction
        ) {
            this.owner = owner;
            this.jdbc = jdbc;
            this.transaction = transaction;
        }

        @EventListener
        public void onContextRefreshed(ContextRefreshedEvent event) {
            if (event.getApplicationContext() != owner) {
                return; // Ignore events from another context.
            }

            transaction.executeWithoutResult(status -> {
                seedRole("ADMIN", "Administrator");
                seedRole("VIEWER", "Read-only");
            });

            int count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM role_catalog", Integer.class
            );
            System.out.println("SEED count=" + count);
        }

        private void seedRole(String code, String label) {
            // MERGE ... KEY is H2 syntax for this example.
            // Other databases need upsert statements in their dialect.
            jdbc.update(
                "MERGE INTO role_catalog (code, label) "
                + "KEY (code) VALUES (?, ?)",
                code, label
            );
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:seed_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbc(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        TransactionTemplate transactionTemplate(
                PlatformTransactionManager manager
        ) {
            return new TransactionTemplate(manager);
        }

        @Bean
        DemoSchema demoSchema(JdbcTemplate jdbc) {
            return new DemoSchema(jdbc);
        }

        @Bean
        @DependsOn("demoSchema")
        SeedOnRefresh seedOnRefresh(
                ApplicationContext context,
                JdbcTemplate jdbc,
                TransactionTemplate transaction
        ) {
            return new SeedOnRefresh(context, jdbc, transaction);
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM role_catalog", Integer.class
        );
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

            context.setId("seed-demo");
            context.register(Config.class);
            context.refresh();

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            System.out.println(
                "AFTER_REFRESH count=" + count(jdbc)
            );

            // Only simulates redelivering the event to test idempotency.
            // This statement does NOT execute context.refresh() a second time.
            context.publishEvent(new ContextRefreshedEvent(context));

            System.out.println(
                "AFTER_REPLAY count=" + count(jdbc)
            );
        }
    }
}
~~~

In the `context-seed-demo/` directory, using JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the program itself in order (excluding environment-dependent Maven messages):

~~~text
SEED count=2
AFTER_REFRESH count=2
SEED count=2
AFTER_REPLAY count=2
~~~

### 5.3. Milestone-by-milestone explanation

**Context initialization:** `context.register(Config.class)` registers configuration, while `context.refresh()` instantiates singletons. The `demoSchema` bean creates the table; `@DependsOn("demoSchema")` explicitly states the listener depends on the table preparation step. Then Spring publishes `ContextRefreshedEvent` and the registered listener receives the event.

**First seed:** the listener compares `event.getApplicationContext()` against the bean context it belongs to. If it is the right context, `TransactionTemplate` opens a transaction, executes two `MERGE` statements, and commits. `SEED count=2` shows both roles are present. `AFTER_REFRESH count=2` proves the data is already there when `refresh()` returns.

**Replaying the event in test:** `context.publishEvent(new ContextRefreshedEvent(context))` is a simulated operation **written intentionally for testing**. It makes the listener receive the same event type again, without running the refresh pipeline, reinitializing beans, or refreshing the context. Both `MERGE` statements continue maintaining the same two role codes without creating a third record. `AFTER_REPLAY count=2` is proof of the final data state.

**H2 and portability:** `MERGE INTO ... KEY (code)` is H2 syntax; PostgreSQL has `INSERT ... ON CONFLICT ... DO UPDATE`, and other databases use different upsert strategies. The JDBC transaction structure of the example is general, yet the seed SQL must be adapted to the actual database.

**Why use @DependsOn?** It confirms bean creation order in the example. In real applications, do not use `@DependsOn` as a substitute for migration tools in multi-instance environments. Here `DemoSchema` only serves the standalone example, not a migration architecture for production use.

## 6. When must a seed listener cause startup to fail?

If initialization data is **mandatory** for the application to function properly, the safe choice is usually an observable failure rather than ignoring errors and still reporting ready. With the default `SimpleApplicationEventMulticaster` (without an async executor or error-swallowing `ErrorHandler`), `@EventListener` methods run synchronously; an unhandled exception can propagate out from publishing `ContextRefreshedEvent`, causing `refresh()` to fail.

Example in a service (illustrative code):

~~~java
public void ensureDefaults() {
    if (!catalogStorage.isAvailable()) {
        throw new IllegalStateException(
            "Cannot initialize required catalog"
        );
    }
    catalogStorage.upsertRequiredEntries();
}
~~~

If the application needs this data **before receiving traffic**, connect initialization failure to actual startup/readiness status. Do not just log the error and continue. With Spring Boot, you can choose `ApplicationRunner` or `CommandLineRunner` running before the application is considered ready in the Boot lifecycle sequence, suitable for late-startup tasks.

Conversely, if seeding a recoverable auxiliary cache or an optional projection, failing the entire startup is not strictly necessary. However, report degraded status, include retries/monitoring, and avoid returning a false "ready" when endpoints actually require that cache.

### Synchronous listeners are not the solution for every kind of initialization

By default `@EventListener` handles synchronously; a large seed can prolong `refresh()`, causing timeouts or increasing rolling deployment durations. Avoid loading millions of rows or making many network API calls inside a listener merely because it is an easy place to hook code. Extract batch jobs/migrations or post-startup tasks appropriately when execution time and reliability demand it.

`@Async` can let the listener return fast, yet it also allows the application to receive requests before seeding completes; exceptions from async tasks do not automatically propagate back to the publisher like synchronous listeners. If seeding is a mandatory precondition, a specifically designed readiness/blocking mechanism is required before allowing traffic.

## 7. Parent–child contexts and multiple instances

### 7.1. Context hierarchy: events can propagate up to parent context

In Spring, events published from a child context can propagate up to the parent context. A listener placed in the parent context can thus receive `ContextRefreshedEvent` published by a child context. Without source filtering, the same seed logic could re-run at an unintended moment.

An explicit approach is injecting the listener's owning context and checking:

~~~java
@EventListener
public void seed(ContextRefreshedEvent event) {
    if (event.getApplicationContext() != owningContext) {
        return;
    }
    seedService.ensureDefaults();
}
~~~

`owningContext` is the `ApplicationContext` bean injected into the listener; `seedService` is an application service. This snippet is illustrative and runs only when placed inside a listener bean. Comparing the **context object** avoids confusion if IDs are configured identically. In the full example, this comparison appeared directly inside `SeedOnRefresh`.

Do not solve duplicate events solely with an `AtomicBoolean seeded` in one JVM. An in-memory flag can skip redundant tasks within one instance, but does not protect the database when there are **two instances, two processes, rolling deployments, or tests creating multiple contexts**.

### 7.2. Multiple instances: unique constraints and concurrency

When two pods start simultaneously, both can receive the refresh event and run seeding against the same database. The pattern "`SELECT COUNT(*)`; if 0 then `INSERT`" suffers from a **race condition**:

~~~text
Instance A: SELECT, ADMIN does not exist yet
Instance B: SELECT, ADMIN does not exist yet
Instance A: INSERT ADMIN
Instance B: INSERT ADMIN  -> duplicate key or duplicated data
~~~

A reliable solution must reside at the data and coordination layer:

- Mandatory `UNIQUE`/`PRIMARY KEY` constraints on business keys.
- Database-native atomic upserts and proper conflict handling.
- Appropriate transactions to seed multiple records consistently.
- When a strictly cluster-wide single execution step is required (e.g., non-idempotent data transformation), use a migration coordinator, database lock/distributed lock, or dedicated deployment job; a flag in a singleton alone is not enough.

`@Order` among listeners only affects processing order within one event/context per the corresponding Spring mechanism; it **does not coordinate multiple JVMs**, nor replace transactions or unique constraints.

## 8. Choosing the right initialization option

| Need | Starting point | Points to note |
| --- | --- | --- |
| Preparing internal fields of a bean | Constructor or `@PostConstruct` | Do not place heavy work depending on many other beans inside creation lock |
| Running a step after regular singletons are created | `SmartInitializingSingleton` | Tied to singleton instantiation phase; not a business event |
| Small seed needing Spring beans and context refresh milestone | `@EventListener(ContextRefreshedEvent.class)` | Idempotent, transactional, check source context |
| Work after Spring Boot startup but before app is considered ready | `ApplicationRunner`/`CommandLineRunner` | Belongs to Spring Boot; different milestone from `ContextRefreshedEvent` |
| Need to react after Spring Boot finishes runners | `ApplicationReadyEvent` | Later timing; if task is a readiness precondition, consider lifecycle |
| Schema or versioned reference data | Flyway/Liquibase/migrations | Tracks versions, rollbacks, and deployment ordering |
| Starting/stopping a consumer by phase | `SmartLifecycle` | Provides start/stop and shutdown coordination |
| Loading large datasets or complex transformations | Dedicated batch job/migration | Provides checkpoints, resume, load limits, progress tracking |
| Populating recoverable cache after startup | Monitored background worker | Readiness and behavior before cache is warm must be clear |

### Avoid confusing Spring Boot milestones

Spring Boot publishes `ApplicationStartedEvent` after context refresh yet **before** `ApplicationRunner`/`CommandLineRunner`, whereas `ApplicationReadyEvent` appears after runners complete. `ContextRefreshedEvent` belongs to Spring Framework and occurs earlier than Boot readiness. Thus the shared word "startup" can lead to choosing the wrong time for when data must be ready.

Someone writing `@EventListener(ContextStartedEvent.class)` instead of `ContextRefreshedEvent` may never see the listener run on default startup because `ContextStartedEvent` is tied to an explicit `context.start()` call, not first-time context initialization.

## 9. Testing data initialization listeners

For seeds with stability requirements, test both **the data outcome after the lifecycle milestone** and error behavior.

| Test case | What to prove |
| --- | --- |
| Creating a new context with empty DB | Mandatory data appears when refresh finishes |
| Replaying event on same context | Does not increase record count, produces no unwanted side effects |
| Database already has full data | Re-running does not corrupt valid data |
| Database is missing only one record | Only inserts/updates the proper record per policy |
| One seed statement throws an exception | Transaction rolls back changes belonging to the same transaction |
| Parent–child contexts | Listener handles only the intended context |
| Two instances starting together | No duplicates thanks to unique/upsert or coordination mechanism |
| Listener bean unregistered or lazy | Test catches that listener fails to receive required event |
| Wrong migration/schema order | Startup reports error clearly; does not mark app ready with missing schema |
| Async executor/exception handler configured | Re-verify blocking and error contracts; do not assume synchronous equivalence |

Do not merely check the `SEED count=2` log and conclude a real transaction committed. For integration tests, query data **after the startup/transaction step has finished**, and avoid wrapping the entire test in a test transaction that makes visible data differ from actual deployment.

For failures, test a `MERGE` statement intentionally violating a constraint to confirm the transaction itself rolls back; do not check only exception text. When testing a context with `AnnotationConfigApplicationContext`, **do not call `refresh()` a second time** because this context type does not support repeated hot refreshes like some other contexts. In the example, a `ContextRefreshedEvent` is published manually solely to test idempotency, not to perform a second refresh.

### Observability in production

Include logs and metrics for: seed duration, rows inserted/updated, retry counts, SQL/constraint errors, startup status, and seed version. Avoid logging passwords, tokens, or sensitive data. When multiple nodes exist, attach instance ID and context ID to distinguish runs.

If seeding uses feature flags or profiles, inspect `Environment` before executing. However, do not turn mandatory data into "silently skipped" logic simply because a property is missing. Policy when a flag is off must be explicitly specified.

## 10. Common mistakes

1. **Unconditional INSERT after every refresh:** duplicates data or causes duplicate keys. Use business keys and idempotent upserts.
2. **Using ContextStartedEvent to wait for first-time application initialization:** this event requires an explicit `start()` operation; usually consider `ContextRefreshedEvent`.
3. **Treating ContextRefreshedEvent as synonymous with Spring Boot ready:** Boot still has runners/readiness steps after refresh.
4. **Cramming heavy seeding into @PostConstruct:** can execute under singleton creation locks while other dependencies are incomplete.
5. **Seeding before tables/schema are ready:** declare migration order and dependencies explicitly; do not rely on luck.
6. **Not using transactions for multiple records that must succeed together:** leaves half-initialized data behind.
7. **Relying on a boolean variable in a singleton to stop two pods from seeding:** does not solve cross-process concurrency.
8. **Only checking COUNT before INSERT:** still has race conditions; use appropriate unique constraints/upserts/locks.
9. **Not filtering parent–child contexts:** a parent listener can process events published by a child.
10. **Swallowing mandatory seed errors:** application still reports ready despite missing critical data.
11. **Making mandatory seeds async:** requests can arrive before data is ready, and async errors do not automatically fail startup.
12. **Putting schema migrations into every refresh event:** DDL changes without a safe migration/versioning contract.
13. **Overwriting user data on every restart:** an ownership policy and mechanism preserving valid edits are needed.
14. **Creating admin accounts with default passwords in seeds:** poses severe security risks; use secret provisioning and secure password rotation workflows.
15. **Manually publishing ContextRefreshedEvent to "restart" the application:** publishing an event object does not re-run the refresh pipeline or recreate beans.

## 11. Self-check exercises

1. Why should a role-initialization listener accept `ContextRefreshedEvent` instead of `ContextStartedEvent`?
2. Why isn't `@PostConstruct` always appropriate for calling multiple services/DBs during bootstrap?
3. In the H2 example, does firing the event twice leave four roles in the table? Why?
4. If two pods run seeding concurrently, is an `AtomicBoolean` in a bean enough to prevent duplicate data?
5. If one of the two `MERGE` statements fails, what does `TransactionTemplate` help ensure for that same transaction?
6. If hundreds of reference records need to be versioned per release, should they necessarily live inside a listener?
7. Why does `getApplicationContext() != owner` prevent mis-handling events in a context hierarchy?
8. If seeding is mandatory yet moved to `@Async`, in what way can readiness go wrong?
9. Does manually publishing `new ContextRefreshedEvent(context)` re-invoke the `refresh()` lifecycle?
10. When data is user-editable, why can an "upsert all columns" seed corrupt data?

**Answer guide:** (1) refresh is the container initialization milestone, start is an explicit operation; (2) bean is still mid-initialization with dependency/creation-lock risks; (3) no, `MERGE` by key `code` keeps two records; (4) no, each pod has its own memory; (5) rolls back changes within the transaction on appropriate exceptions; (6) consider versioned migrations; (7) filters for the exact context object; (8) app accepts requests before seeding finishes; (9) no, only dispatches an event object; (10) overwrites user-owned state.

## References

- Spring Framework Reference — *Application Events / Standard and Custom Events*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — *Lifecycle Callbacks and Initialization*: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework Reference — *Declarative Transaction Management*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2.8 Javadoc — *ContextRefreshedEvent*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/ContextRefreshedEvent.html
- Spring Framework 6.2.8 Javadoc — *TransactionTemplate*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring Boot Reference — *Application Events and ApplicationRunner*: https://docs.spring.io/spring-boot/reference/features/spring-application.html
