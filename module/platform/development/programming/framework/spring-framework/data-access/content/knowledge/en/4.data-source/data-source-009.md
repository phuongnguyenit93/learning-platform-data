# Closing a Connection Pool Following the Container Lifecycle in Spring Framework

> **Topic:** DataSource. This lesson explains when and how to **close a connection pool** along the Spring IoC container's lifecycle, how to distinguish closing an individual `Connection` from closing the entire `DataSource`, and who is responsible for cleaning up resources when the application stops. Examples primarily use HikariCP, Spring Framework, and Spring Boot; lifecycle ownership principles also apply to other pools if they support an equivalent shutdown method.

## 1. Why Does a Pool Need to Be Closed?

A Java application using JDBC constantly obtains connections to the database. Creating a physical connection can cost time and resources, so a **connection pool** keeps a set of connections for multiple operations to borrow and return. Spring typically provides the pool to Repositories/DAOs via a `DataSource` bean.

Throughout the application's active lifetime, the pool manages:

- Physical connections to the DBMS, including sockets and sessions that can occupy server quota.
- Currently borrowed (active) connections, idle connections, and pending requests waiting for a connection.
- Background tasks and internal pool management structures, such as connection lifecycle checks and counters.
- Timeout settings, connection count limits, and connection validation mechanisms.

When the application actually **stops**, the pool no longer serves any requests; the resources it owns must be released. Skipping this step—especially in tests creating multiple Spring contexts, repeated runs within one JVM, or hot redeploys—can leave resources alive longer than expected. In an OS process whose JVM has completely terminated, sockets are eventually reclaimed by the OS; however, you should not rely on forced termination to replace a controlled shutdown procedure.

**Core principle:** **The component owning the pool is responsible for closing the pool when its lifecycle ends.** If the pool bean is created and managed by the Spring container, register a bean destruction callback for Spring to invoke when the context closes. If the DataSource is managed by an application server/JNDI, that external owner is responsible for closing it.

## 2. Distinguishing Three Commonly Confused Actions

| Action | Example | What It Actually Does | When? |
| --- | --- | --- | --- |
| Returning a borrowed connection to the pool | `connection.close()` on a HikariCP-issued connection | Usually closes the **logical handle**, returning the connection to the pool for reuse; does not shut down the entire pool | After each unit of work; via `try-with-resources` or Spring JDBC |
| Closing the entire pool | `hikariDataSource.close()` | Pool stops serving and cleans up internal connections/resources; subsequent Connection acquisitions from the closed pool fail | When the pool's **owner** ends its lifecycle |
| Closing the Spring container | `context.close()` | Spring runs context shutdown, stops lifecycle beans, and destroys managed singleton beans; invokes the pool's registered destroy callback | When the application, test context, or subsystem must terminate |

Example:

~~~java
// Illustrates a running snippet; the dataSource variable is Spring-managed.
// Closing Connection after a JDBC operation is normal.
try (java.sql.Connection connection = dataSource.getConnection()) {
    // Execute JDBC using connection.
}
// HikariDataSource remains active after the logical connection is returned.

// Only the pool owner calls this once the ENTIRE application is done with the pool:
// hikariDataSource.close();
~~~

**Do not put `dataSource.close()` inside a DAO, Repository, Service, or each HTTP request's `finally` block.** If one request shuts down the shared pool, other requests can no longer obtain connections. With `JdbcTemplate` or JPA, the framework typically manages borrowing/returning connections per data-access/transaction context; developers still need to configure pool lifecycle properly, without manually calling `Connection.close()` around every `JdbcTemplate.update()`.

Note: `javax.sql.DataSource` is a **connection-acquisition interface** with no generic `close()` method. Closing a pool depends on the concrete implementation type—such as `HikariDataSource.close()`—or a destroy callback registered by Spring configuration. Do not cast every `DataSource` to HikariCP.

## 3. How Does a Pool Live Alongside ApplicationContext?

Typical lifecycle of a Spring-owned pool bean:

~~~mermaid
flowchart TD
    A["Create ApplicationContext"] --> B["Create/configure DataSource bean"]
    B --> C["Initialize pool on demand or at DataSource creation"]
    C --> D["Service/DAO uses JDBC, borrows and returns Connection"]
    D --> E{"ApplicationContext closed?"}
    E -- "Not yet" --> D
    E -- "Yes" --> F["Emit close signal, stop Lifecycle/SmartLifecycle beans"]
    F --> G["Destroy managed singleton beans"]
    G --> H["Invoke pool close/shutdown callback"]
    H --> I["Pool closed; pool-owned resources released"]
~~~

This is a **responsibility diagram**, not a guarantee that every application type follows the exact same micro-order for every callback. Spring has separate stop and destroy phases; beans also have dependency relationships and phases. The key point is that **the pool must stay available while database-dependent work is still finishing**, and must be closed when the context actually destroys the resources it owns.

### Distinguishing `stop()` and `close()` on Context

- `ConfigurableApplicationContext.close()` closes the context and triggers destruction of managed singleton beans.
- `ConfigurableApplicationContext.stop()` sends a stop signal to eligible Lifecycle components; **it is not equivalent** to destroying all singleton beans or closing the pool via its destroy method.
- `refresh()` is not a shutdown command; destroying and recreating beans in some scenarios is governed by the context implementation and scope management rules.
- Spring Boot normally registers a **JVM shutdown hook** to close ApplicationContext on normal JVM exit. Calling `context.close()` directly remains useful in console/test programs to pinpoint the exact closing moment.

If the container never gets a chance to run shutdown callbacks (e.g., process receives `SIGKILL`, crash/halt, power loss), Java's `close()` cannot be guaranteed to run. Thus, applications still need fault tolerance for abrupt connection drops at the database and operations layers.

## 4. Who Owns DataSource? Three Cases Determining How to Close

| Case | Who Creates and Owns the Pool? | Proper Handling |
| --- | --- | --- |
| Spring Boot auto-configures HikariCP from `spring.datasource.*` | The application's ApplicationContext | Let Spring manage lifecycle; when context closes, the DataSource bean is destroyed and the pool closes |
| Manually declaring `@Bean HikariDataSource` in Spring config | ApplicationContext if that bean owns the pool | Register `destroyMethod = "close"` or use Spring-recognized destroy inference; never call from individual requests |
| Obtaining DataSource via JNDI from an application server or external provider | External container, e.g., application server | **Do not let Spring close an external pool**; disable automatic destroy inference when creating an appropriate `@Bean` proxy/lookup |

Two additional easily forgotten cases:

- If a library or code manually calls `new HikariDataSource(...)` **outside Spring** and does not transfer lifecycle ownership to Spring, Spring does not automatically know about that object to call `close()`. The code that created it must handle its closing procedure.
- If multiple `ApplicationContext`s or multiple pools for multiple databases/tenants are created, each pool must have a **single designated owner**. Do not let one bean's destroy callback accidentally close a pool still serving another context/unit.

Sometimes the same object is exposed under multiple bean names or referenced from multiple contexts. Decide on **one explicit lifecycle owner**; avoid situations where two independent contexts both believe they have the right to close a shared resource.

## 5. How Does Spring Trigger Bean Destroy Callbacks?

Spring offers several ways to declare resource destruction callbacks. The goal is the same: register cleanup with the **container** so it does not have to be invoked manually in the business layer.

### 5.1. Explicit Declaration with `@Bean(destroyMethod = "close")`

~~~java
// Configuration illustration: this class lives in an app with Spring and HikariCP.
@Configuration(proxyBeanMethods = false)
class DataSourceConfig {
    @Bean(destroyMethod = "close")
    HikariDataSource dataSource() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl("jdbc:h2:mem:demo");
        config.setUsername("sa");
        config.setMaximumPoolSize(5);
        return new HikariDataSource(config);
    }
}
~~~

When this bean is a Spring-managed singleton and the context closes, Spring invokes `close()` as the bean's destroy method. This is a clear, easy-to-review way to express that the context owns the pool. With `@Bean`, Spring also **automatically infers destroy methods** named public no-arg `close` or `shutdown` when using the default `(inferred)` mode. Thus, for a `HikariDataSource` properly created as a `@Bean`, writing `destroyMethod = "close"` is usually an explicit clarification rather than strictly required for inference to work.

### 5.2. Other Mechanisms

- `@PreDestroy` (in modern Spring, `jakarta.annotation.PreDestroy`) on a bean's cleanup method.
- The `org.springframework.beans.factory.DisposableBean` interface with `destroy()`.
- The `@Bean(destroyMethod = "...")` attribute to call an appropriate no-arg method.
- XML bean definitions using `destroy-method`, if the application is configured via XML.

If multiple **distinct-method** destroy mechanisms are declared on the same bean, Spring's typical order is `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method. Do not intentionally close the same pool multiple times from different callbacks; keep **one clear pool-management path**. Using a Service's `@PreDestroy` to call `dataSource.close()` directly is usually wrong ownership, since that service is not necessarily the last consumer needing the database.

### 5.3. Bean Lifecycle Depends on Scope

Automatic destroy callbacks are most reliable for **singleton beans managed by the Spring container**. Prototype beans are created by Spring, yet normally do not receive the full automatic destruction cycle like singletons; the caller using a prototype must handle any needed cleanup. Therefore, a typical connection pool should be defined as a **singleton with a clear owner**, rather than creating a new pool per request/prototype bean.

## 6. Spring Boot Auto-Configured DataSource: Most Apps Need No Pool-Closing Code

With Spring Boot, adding `spring-boot-starter-jdbc` or `spring-boot-starter-data-jpa` typically brings HikariCP in as a dependency. When no custom DataSource bean exists and configuration matches, Spring Boot usually selects HikariCP as the pool.

Example in `application.properties`:

~~~properties
spring.datasource.url=jdbc:postgresql://localhost:5432/lesson
spring.datasource.username=lesson_user
spring.datasource.password=replace-with-secret-from-environment
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=30000
~~~

This is only a property example; in practice, obtain the password from environment variables/a secret manager instead of storing secrets in the repo. When Boot owns the pool, **do not add a `@PreDestroy` inside a Controller/Service to call `HikariDataSource.close()`**. The Spring container already destroys the bean when the context closes.

### How a Boot Application Shuts Down

In a standard Boot application launched via `SpringApplication.run(...)`, Boot registers a JVM shutdown hook to close the context on normal JVM exit. In a job/CLI or test that must stop at an exact time, you can close the context explicitly:

~~~java
// Illustration inside an application that defines App.class as @SpringBootApplication.
try (org.springframework.context.ConfigurableApplicationContext context =
         org.springframework.boot.SpringApplication.run(App.class, args)) {
    // Work while the context is open.
} // context.close() runs upon exiting try.
~~~

This snippet only illustrates context management; `App` and the Boot build are not defined here. A complete **standalone runnable** Spring Framework example is shown in Section 8.

### Shutting Down a Web App with In-Flight Requests

When using Spring Boot 3.3 with a supported embedded web server, you can configure graceful shutdown:

~~~properties
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
~~~

During shutdown, the server stops accepting or rejects new requests in a manner fitting its implementation and gives active requests time to finish. Once the stop phase completes, Spring proceeds to destroy singleton beans, including the managed pool. **Graceful shutdown does not guarantee every request finishes with unlimited time**: timeouts, hanging JDBC operations, and how the platform delivers the stop signal still determine actual results. Design sensible timeouts for JDBC, transactions, and incoming requests.

## 7. Stopping Background Work First, Closing the Pool Afterward

A common tough question: what if scheduled jobs, message listeners, or worker threads are currently using the database?

A safe architectural pattern:

1. Receive the stop-serving signal, prevent new work from starting, or adjust readiness/routing.
2. Ask active workers/listeners to finish or cancel in a controlled manner within a clear deadline.
3. Wait for active transactions/Connections to complete per an appropriate policy.
4. Let Spring execute the pool bean's destroy callback, closing pool connections and resources.
5. Exit the process or complete subsystem shutdown.

In Spring, `Lifecycle`/`SmartLifecycle` lets a component participate in context start/stop phases. With `SmartLifecycle`, `getPhase()` and the `stop(Runnable callback)` callback coordinate ordered stop completion as defined. **Higher phases stop before lower phases** within the coordinated lifecycle group; explicit dependencies also affect order. The normal stop phase happens **before** singleton bean destroy callbacks. There is no need to turn every Repository into a `SmartLifecycle`; this mechanism is mainly useful for beans managing background work themselves.

~~~java
// Illustrative fragment, NOT a standalone runnable program.
@Override
public void stop(Runnable callback) {
    consumer.pauseAcceptingNewWork();
    consumer.finishOrCancelCurrentWork();
    callback.run(); // Signal stop completion to LifecycleProcessor.
}
~~~

Do not invoke `callback.run()` prematurely while the worker is still actively using the database; nor block indefinitely during shutdown. Terminating asynchronous tasks requires real coordination, timeouts, and error handling. If using only standard Spring MVC without spawning custom background threads, you can rely on the built-in lifecycle of the server and pool.

### Things to Avoid with Shutdown Callbacks

- `ContextClosedEvent` signals the context is beginning to close; listeners must not assume they can run long transactions or always run in a fixed order relative to every other bean.
- Do not perform complex JDBC transactions inside `@PreDestroy` if they still depend on many beans already/currently being destroyed; prefer completing work in an ordered stop phase.
- Do not treat `HikariDataSource.close()` as a mechanism that "waits for all requests to finish" instead of coordinating shutdown; pool shutdown does not replace stopping requests/workers in proper order.
- Do not rely on shutdown callbacks to repair data after a `SIGKILL`; callbacks may never run in that scenario.

## 8. Runnable Example: Closing HikariCP When Closing the Spring Container

The example runs with **Java 21**, **Gradle**, **Spring Framework 6.1.14**, **HikariCP 5.1.0**, and **H2 2.3.232**. This is a plain Spring Framework console application so you can see the exact pool owner; no web server or Spring Boot is needed.

Project structure:

~~~text
pool-lifecycle-demo/
├── build.gradle
└── src/main/java/demo/PoolLifecycleLesson.java
~~~

### 8.1. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'application'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'demo.PoolLifecycleLesson'
}

dependencies {
    implementation platform('org.springframework:spring-framework-bom:6.1.14')
    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-jdbc'
    implementation 'com.zaxxer:HikariCP:5.1.0'
    runtimeOnly 'com.h2database:h2:2.3.232'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.16'
}
~~~

### 8.2. `src/main/java/demo/PoolLifecycleLesson.java`

~~~java
package demo;

import java.sql.Connection;
import javax.sql.DataSource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

public final class PoolLifecycleLesson {

    public static void main(String[] args) throws Exception {
        HikariDataSource pool;

        // Context is the owner of the pool bean within this scope.
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(PoolConfiguration.class)) {

            pool = context.getBean(HikariDataSource.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("CREATE TABLE lesson_item (id INTEGER PRIMARY KEY)");
            jdbc.update("INSERT INTO lesson_item (id) VALUES (?)", 7);

            Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM lesson_item", Integer.class
            );
            System.out.println("Rows = " + count);

            // Borrow a logical Connection and return it to the pool.
            try (Connection connection = pool.getConnection()) {
                System.out.println(
                    "Borrowed connection open = " + !connection.isClosed()
                );
            }

            // Connection.close() above does not shut down the entire pool.
            System.out.println(
                "Pool open after Connection.close = " + !pool.isClosed()
            );

        } // AnnotationConfigApplicationContext.close() is called here.

        // Keep reference only to inspect state; do not use pool for queries anymore.
        System.out.println(
            "Pool closed after context.close = " + pool.isClosed()
        );
    }

    @Configuration(proxyBeanMethods = false)
    public static class PoolConfiguration {

        @Bean(destroyMethod = "close")
        public HikariDataSource dataSource() {
            HikariConfig config = new HikariConfig();
            config.setJdbcUrl("jdbc:h2:mem:pool_lifecycle;DB_CLOSE_DELAY=-1");
            config.setUsername("sa");
            config.setPassword("");
            config.setPoolName("lesson-pool");
            config.setMaximumPoolSize(2);
            return new HikariDataSource(config);
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }
}
~~~

Explaining the relationships:

1. `AnnotationConfigApplicationContext` creates the `HikariDataSource` bean per `PoolConfiguration`, owning this singleton's lifecycle.
2. `JdbcTemplate` receives `DataSource` via dependency injection. Executing SQL with `jdbc.execute` and `jdbc.update` does not require the caller to manage pool lifecycle manually.
3. `try (Connection connection = pool.getConnection())` simulates a low-level JDBC task: exiting the block returns the connection to the pool; the pool's `isClosed()` remains `false`.
4. Exiting the outer `try` calls `context.close()`, triggering Spring's bean destruction callback, which invokes `HikariDataSource.close()`.
5. After the context closes, `pool.isClosed()` must be `true`. We do not use the closed object to run SQL or borrow new connections.

If the directory has a Gradle wrapper, run `./gradlew run` on Linux/macOS or `.\gradlew.bat run` on Windows PowerShell. Without a wrapper but with a compatible Gradle installed: `gradle run`. Java toolchain 21 must be available or configured for Gradle to provision.

The lines **printed by the demo code itself**, omitting informational/startup/shutdown logs from Spring, HikariCP, and Gradle, are:

~~~text
Rows = 1
Borrowed connection open = true
Pool open after Connection.close = true
Pool closed after context.close = true
~~~

This is a **self-contained two-file example**; it does not use Spring Boot autoconfiguration. If you remove `destroyMethod = "close"` and leave just `@Bean`, Spring can still automatically detect `HikariDataSource`'s public `close()` via destroy-method inference rules. If you replace it with `@Bean(destroyMethod = "")`, you disable callback inference; do not do that for a pool genuinely owned by the context.

**Note on H2:** `DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive until the JVM exits, yet this **does not keep HikariCP open** after the context closes. `pool.isClosed()` proves pool lifecycle, not whether the database engine has terminated or how long H2 data persists.

## 9. Spring Boot Equivalents: Auto-Configured Pool vs. Custom Bean

### 9.1. When Letting Spring Boot Auto-Configure

A Spring Boot project that already has the JDBC starter, PostgreSQL driver, and database properties typically needs no DataSource configuration class. Boot creates an appropriate pool bean and binds it to ApplicationContext. To run DB transactions during requests, Service/Repository continue using JdbcTemplate or JPA as usual. When the application shuts down properly, Spring cleans up the pool bean.

For Boot apps running in a standard JVM, Spring Boot registers a shutdown hook to close the context; in short-lived console/test apps, you can close the context explicitly. **Do not create a second HikariCP** just to control closing when Boot already provides a DataSource bean.

### 9.2. When Declaring `@Bean DataSource` Yourself

You can define a custom DataSource, in which case Boot's default DataSource auto-configuration usually backs off. Make ownership and the destroy method explicit:

~~~java
// Separate config example, illustrative only; Section 8 is the standalone runnable example.
@Bean(destroyMethod = "close")
public HikariDataSource reportsDataSource() {
    HikariDataSource pool = new HikariDataSource();
    pool.setJdbcUrl("jdbc:postgresql://db:5432/reports");
    pool.setUsername("reports_user");
    pool.setPassword("configured-at-runtime");
    pool.setMaximumPoolSize(5);
    return pool;
}
~~~

In practice, supply credentials via a secret/environment system and consider `@ConfigurationProperties` binding instead of hardcoding. When **multiple** DataSources exist, design bean selection (`@Qualifier`/`@Primary`), matching JdbcTemplate/EntityManagerFactory beans, and appropriate transaction managers. Every Spring-owned pool must be destroyed properly.

## 10. DataSource from JNDI or Application-Server-Owned Pool: Do Not Close from Spring

Case of a WAR application or an app inside a Jakarta EE application server: the pool may be administered in Tomcat/JBoss/WebLogic or an external provider, and the application merely **looks up** a `DataSource` via JNDI.

Illustrative example:

~~~java
// Fragment for an app with Spring bean config and matching JNDI.
// Not a standalone program; imports and server JNDI depend on environment.
@Bean(destroyMethod = "")
public javax.sql.DataSource externalDataSource() throws javax.naming.NamingException {
    return (javax.sql.DataSource) new javax.naming.InitialContext()
        .lookup("java:comp/env/jdbc/AppDb");
}
~~~

`destroyMethod = ""` here has a clear purpose: **Spring does not infer and invoke close/shutdown on an object obtained from an external source**, because the true owner is the application server. This is an ownership exception, not a trick to apply by default to every DataSource. Under Spring's mechanics, disabling the inferred destroy method does not necessarily disable callbacks implemented by the bean itself via other lifecycle interfaces; inspect the actual object and the external container's policy.

If deploying Spring Boot onto an application server and configuring `spring.datasource.jndi-name`, also understand that the pool truly belongs to the server. Avoid writing custom application shutdown hooks to close a server-wide pool while other deployments may still be using it.

## 11. Closing Context in Web Apps, CLIs, and Integration Tests

| Environment | Typical Termination Event | Action Needed |
| --- | --- | --- |
| Spring Boot running as a server process | Normal stop signal/JVM exit, Spring shutdown hook | Ensure shutdown is allowed to run; graceful server stop and bean destroy will clean up the pool |
| Spring Framework run via `AnnotationConfigApplicationContext` | End of a context usage unit | Use `try-with-resources` or call `close()`; if long-lived, consider `registerShutdownHook()` |
| CLI tools/batch jobs | Job completion or failure requiring context exit | Close context even on exception branches; do not exit leaving the pool alive in the JVM |
| Spring tests using context caching | Ending a single test does not necessarily close context | TestContext may cache contexts across tests; do not close the pool manually after each test method |
| Tests creating their own context | End of block/test | Close context during cleanup; assert `isClosed()` when needed |
| WAR app on external app server | Redeploy/undeploy or stop deployment | Determine whether pool is app-owned or server-owned before deciding destroy method |

In Spring TestContext, context caching reuses ApplicationContext across tests. Hence **"test method ended" does not always equal "context closed"**. If a test needs to verify destroy lifecycle, create an isolated context like the Section 8 example or design a test permitted to close its context, avoiding breaking a shared cached context and corrupting other tests.

### `registerShutdownHook()` and Manual Closing

In plain Spring Framework, the context can register a hook as needed:

~~~java
// Fragment, not standalone.
AnnotationConfigApplicationContext context =
    new AnnotationConfigApplicationContext(MyConfiguration.class);
context.registerShutdownHook();
// For a program using the context in a clear scope,
// you can still call context.close() explicitly when done.
~~~

The hook handles the normal JVM shutdown path. Do not register a new hook per bean/DAO or per Connection borrow. Spring Boot provides its own shutdown hook mechanism in standard bootstrapping.

## 12. Observing and Verifying Whether the Pool Truly Closed

**Direct check in the lesson:** hold a reference to `HikariDataSource` before the context closes, then call `pool.isClosed()` after `context.close()`. This is clear, quantitative evidence for the pool's lifecycle in the demo. After the pool closes, perform no business operations through the old reference.

In real applications, you can also use:

- **Lifecycle logs** of the pool implementation, such as HikariCP logs on pool shutdown. Do not depend rigidly on exact log strings from a single version.
- **Metrics**: active, idle, total, and pending connections during runtime; observe counts dropping to zero and no remaining borrowers on shutdown (depending on how metrics are registered and torn down).
- **Database session view**: watch sessions from the application drop after the system closes the pool; account for connections from other apps and connections lingering due to server-side timeouts.
- **Integration tests**: create a context with a real DataSource, run a query, close the context, verify pool state; then start a new context and verify old resources are no longer used.

Do not treat `idle=0` as proof that the pool has closed. An open pool can temporarily have zero idle connections; similarly, the DBMS may still hold sessions from other components. If the system has multiple pools, set pool names or connection metadata to correlate the exact object.

### Suggested JUnit Test

~~~java
// JUnit 5 fragment, depending on PoolLifecycleLesson from Section 8.
// Illustrates test logic only; add JUnit dependency when placing in a project.
@Test
void contextCloseShutsDownOwnedPool() {
    HikariDataSource owned;
    try (var context = new AnnotationConfigApplicationContext(
            PoolLifecycleLesson.PoolConfiguration.class)) {
        owned = context.getBean(HikariDataSource.class);
        assertFalse(owned.isClosed());
    }
    assertTrue(owned.isClosed());
}
~~~

Keep the boundary clear: the test proves **the managed Hikari bean closes with the context**; it does not prove requests are gracefully stopped in a real web app. Testing graceful shutdown requires scenarios with in-flight requests and realistic timeouts.

## 13. Common Mistakes and Consequences

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `hikariDataSource.close()` after every query or request | One request kills the pool for all other requests | Return `Connection` after each operation; close the pool once at owner lifecycle end |
| Calling `new HikariDataSource` in a DAO without registering a bean or cleanup | Pool may outlive the Spring context | Use a managed singleton bean or manage ownership explicitly when creating manually |
| Using `@Bean(destroyMethod = "")` on a Spring-owned pool | Loses inferred close callback; risks failing to clean up the pool | Leave default or declare `destroyMethod = "close"` |
| Putting `@PreDestroy` in a Service and calling `dataSource.close()` | Wrong ownership; other dependencies may still need the pool | Register the callback on the pool bean itself; coordinate worker stop first |
| Closing a server JNDI-owned DataSource | Can break other services using the external resource | Set `destroyMethod = ""` on appropriate lookups; let external owner manage |
| Assuming `context.stop()` destroyed the pool | Pool may remain alive because beans were not destroyed | Use `context.close()` when truly ending lifecycle |
| Closing context while workers are still querying | Query errors, timeouts, incomplete jobs | Stop accepting work, let in-flight work finish within deadline, then destroy pool |
| Relying solely on shutdown hooks when processes are force-killed | Callbacks may not run | Design graceful termination, readiness, timeouts, and post-crash recovery |
| Creating a new pool per Spring context in tests without closing contexts | Accumulates pools, increases connection count | Use controlled test context lifecycle/caching; close self-created contexts |
| Seeing zero idle connections and declaring the pool closed | Confuses connection count state with lifecycle state | Check `HikariDataSource.isClosed()`/logs/owner context |

## 14. Advanced Scenarios: Multiple Contexts and Multiple Pools

**Two DataSources owned by the same Spring context:** If an application uses `ordersDataSource` and `analyticsDataSource`, each pool bean must be destroyed properly when the context closes. Do not let custom cleanup close one pool while workers still use it. Bean names and `@Qualifier` decide which pool a DAO call hits; pool names and metrics aid observability.

**Parent/child ApplicationContext:** A DataSource bean owned by a parent context should not be actively closed by a child context when only the child ends. Closing the parent at the end is when the parent-owned pool is destroyed. Do not re-register the same pool object into multiple contexts under beans with independent destroy callbacks unless a single-owner policy exists.

**Pool borrowed from an external framework:** Libraries supporting JNDI, proxy DataSources, or multi-tenant routing may expose a `DataSource` interface that does not own sockets. Identify **which object truly owns the pool** before attaching destroy callbacks. Do not assume having `getConnection()` means that object owns shutdown.

**During redeployment:** If the same JVM/container creates a new Spring context without properly cleaning up the old context, it may retain classloaders, threads, and connections from the old version. Ensure stop/destroy of the old context finishes before shifting resources to the new version, per the deployment environment's lifecycle.

## 15. Self-Check

**Question 1.** A DAO returned its Connection after a query. Should the pool close immediately?  
**Answer:** No. `Connection.close()` on a pooled connection primarily returns the logical Connection to the pool; the pool continues serving other work.

**Question 2.** A `@Bean HikariDataSource` bean has a public `close()` method and does not declare `destroyMethod`. Can Spring invoke close automatically when the context closes?  
**Answer:** Yes. Spring infers `close`/`shutdown` destroy methods on `@Bean`, provided the bean's scope/lifecycle is properly container-managed.

**Question 3.** An application runs on a server with a shared JNDI pool. Who closes the pool?  
**Answer:** The pool owner is the application server; the Spring application merely borrows the DataSource and should not close the external resource itself.

**Question 4.** What is the difference between `context.stop()` and `context.close()` for a pool bean?  
**Answer:** Stop targets the Lifecycle stop phase; close initiates context teardown and destroys singleton beans, including the pool's destroy method.

**Question 5.** Shutting down a web server with a long-running query: does calling `pool.close()` immediately guarantee the query finishes?  
**Answer:** No. Graceful shutdown must coordinate rejecting new requests, in-flight requests/transactions, timeouts, and stop phases before destroying the pool.

**Question 6.** What if `HikariDataSource.isClosed() == false` yet there are currently 0 idle connections?  
**Answer:** The pool is still open; idle count does not determine lifecycle status.

**Question 7.** A test creates a new context for every test case without closing it—what goes wrong?  
**Answer:** Pools/connections and background resources can accumulate. Let TestContext manage caching/cleanup, or explicitly close contexts created individually by tests.

## 16. Practical Deployment Checklist

1. **Verify owner:** Is the DataSource pool created by Spring Boot/Spring config or supplied by an external server?
2. **Right scope:** A pool is normally a long-lived singleton; avoid per-request instantiation.
3. **Right destroy callback:** Spring-owned pools use inferred `close` or explicit `destroyMethod="close"`; external pools must not be destroyed by Spring.
4. **Right JDBC boundaries:** Borrow/return Connection per operation or let Spring JDBC/JPA manage it; never close the pool in the query layer.
5. **Right shutdown order:** Stop accepting work and stop workers before destroying the pool; configure timeouts suitable for web/background jobs.
6. **Right environment handling:** CLIs/tests creating their own context must close it; Boot web apps must allow shutdown hooks/graceful paths to run.
7. **Right evidence:** Verify `isClosed()` in tests, logs/metrics/sessions in real systems, and test stopping with in-flight requests.
8. **Right bug-fix scope:** If the leak comes from unreturned Connections, fix the borrower; if the leak comes from undestroyed contexts/pools, fix the lifecycle owner. Both bugs share the symptom of connection exhaustion yet have different root causes.

## 17. Recommended Official Further Reading

- [Spring Framework — Bean lifecycle and destruction callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `@PreDestroy`, `DisposableBean`, destroy methods, `Lifecycle`, and `SmartLifecycle`.
- [Spring Framework — `@Bean` and close/shutdown inference](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): inference and the JNDI-obtained DataSource case.
- [Spring Boot — SQL Databases / Supported Connection Pools](https://docs.spring.io/spring-boot/reference/data/sql.html): HikariCP selection, DataSource configuration, and JNDI.
- [Spring Boot 3.3 — Graceful Shutdown](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html): phased web server stop and timeouts.
- [Spring Boot — SpringApplication / Application Exit](https://docs.spring.io/spring-boot/reference/features/spring-application.html): shutdown hooks and ApplicationContext lifecycle.

**Final takeaway:** Returning a `Connection` is completely different from closing a **pool**. The Spring container should be responsible for closing pools **it genuinely owns** on `ApplicationContext.close()`. Tasks still using the database must be stopped or finished before the destroy phase; pools provided by an external server must be managed by that server itself. The problem is not merely calling a `close()` method, but **placing the close command on the right owner at the right time**.
