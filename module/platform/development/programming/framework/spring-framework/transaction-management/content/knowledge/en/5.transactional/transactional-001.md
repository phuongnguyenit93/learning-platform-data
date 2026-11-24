# Annotations Are Just Metadata Requiring Infrastructure to Process: Understanding Spring's @Transactional

## 1. Objectives

When seeing `@Transactional` on a method, many people imagine that the JVM automatically opens a transaction before that method, commits when it finishes, and rolls back if an error occurs. **That is not how Java annotations work.** An annotation is descriptive information; transactional behavior only appears when infrastructure reads that information and actually intercepts the method call.

After this lesson, you can:

- Accurately explain that `@Transactional` is **metadata declaring transactional intent**, not self-executing Java code.
- Describe the roles of the Spring container, transaction management configuration, AOP proxy, `TransactionInterceptor`, `TransactionAttributeSource`, and `PlatformTransactionManager`.
- Recognize cases where an annotation is present but transaction advice does not execute: objects created with `new`, self-invocation, methods that cannot be intercepted by a proxy, or calls targeting the wrong application context.
- Distinguish between "annotation is detected", "call passes through the interceptor", and "data operations participate in the right transaction".
- Run a Java 17+ example observing three cases: calling through a Spring proxy rolls back; self-invocation within the same bean and calling on a manually instantiated object do not roll back.

This lesson is set in the context of **Spring Framework — transaction management**, the `@Transactional` group. The content focuses on the annotation activation mechanism and does not treat every transaction configuration or persistence model as identical.

## 2. Annotations in Java: Descriptions, Not Executable Statements

An annotation is metadata attached to a class, method, or program element. The Java compiler/JVM may retain, inspect, or expose metadata depending on the annotation and its retention policy. **An annotation itself does not insert `begin`, `commit`, or `rollback` instructions into a method body.**

Example:

```java
import org.springframework.transaction.annotation.Transactional;

public class PaymentService {
    @Transactional
    public void charge() {
        System.out.println("Charging...");
    }
}
```

The snippet above is a **syntax illustration**, requires the `spring-tx` library to compile, and is not a standalone application. If you only run:

```java
new PaymentService().charge();
```

Java executes `charge()` as a normal method call. No Spring bean, proxy, or transaction manager is created just because of the annotation. Spring can read the annotation at runtime to obtain transaction rules, but being able to read it does not mean the call has been intercepted.

An annotation can have `@Retention(RetentionPolicy.RUNTIME)` so it can be accessed via reflection. Even in that case, **a metadata consumer** is required: a framework, annotation processor, bytecode weaver, or code you write. Spring's `@Transactional` is a classic example of an annotation interpreted by Spring infrastructure.

Do not equate it with every other annotation: `@Override` helps the compiler check override contracts; `@Deprecated` carries warning information; `@Transactional` describes business rules that Spring must enforce at runtime. Each annotation takes effect according to its corresponding processing tool, not simply because its name starts with `@`.

## 3. What Does @Transactional Declare?

`org.springframework.transaction.annotation.Transactional` represents transaction rules for an applied method or type. Common attributes include:

| Attribute | Meaning in metadata | Example |
| --- | --- | --- |
| `propagation` | How to join or create a transaction when one already exists or does not exist | `REQUIRED` (default), `REQUIRES_NEW` |
| `isolation` | Isolation level requested from the transaction manager/resource | `Isolation.READ_COMMITTED` |
| `readOnly` | Optimization hint or read-only semantics for supporting managers/drivers | `readOnly = true` |
| `timeout` | Transaction timeout in seconds when applicable | `timeout = 5` |
| `rollbackFor` | Additional exception types that must trigger rollback | `rollbackFor = IOException.class` |
| `noRollbackFor` | Exceptions that do not require rollback according to declared rules | `noRollbackFor = BusinessException.class` |
| `transactionManager` | Select a manager by name/qualifier when multiple managers exist | `transactionManager = "ordersTxManager"` |

Illustrative example:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = false,
    rollbackFor = IOException.class
)
public void publishInvoice() throws IOException {
    // Data operations belonging to a use case.
}
```

This snippet only describes the **desired configuration**. If the call is not intercepted by transaction advice, the attributes remain in metadata and do not create a transaction on their own. Nor does `readOnly` mean the JVM automatically forbids write statements; its effect depends on the infrastructure/resource.

In Spring Framework 6.1's default mechanism, `@Transactional` uses propagation `REQUIRED`, isolation `DEFAULT`, a read-write transaction, and rolls back on `RuntimeException` or `Error`; checked exceptions do not trigger rollback unless configured otherwise. Specific rules may be customized by version or configuration. **Those are rules used by the infrastructure**, not the Java annotation catching exceptions by itself.

## 4. Which Infrastructure Turns Metadata into Behavior?

An imperative Spring application using declarative transactions typically has the following components:

1. **Spring ApplicationContext** managing business beans. This is the foundation for Spring to create and wrap appropriate beans.
2. **A transaction annotation processing enabler**, such as `@EnableTransactionManagement`, XML `<tx:annotation-driven/>`, or appropriate auto-configuration in Spring Boot.
3. **`TransactionAttributeSource`**, usually `AnnotationTransactionAttributeSource`, which reads `@Transactional` metadata and converts it into transaction attributes.
4. **Advisor and Spring AOP proxy** applying transactional advice to calls within the proxy's scope.
5. **`TransactionInterceptor`** executing transaction coordination around the invocation.
6. **`PlatformTransactionManager`** suited to the imperative model and data resource: `JdbcTransactionManager`/`DataSourceTransactionManager` for JDBC, `JpaTransactionManager` for JPA, or another implementation.
7. **Data access libraries participating in the transaction**, such as `JdbcTemplate` using the right `DataSource`, or repositories/JPA using the same manager. If an operation uses a separate resource not managed by that manager, the annotation does not automatically cover it.

Diagram:

```text
Caller (another bean, controller, listener)
             |
             v
Spring AOP proxy of Service
             |
             v
TransactionInterceptor
  +-- TransactionAttributeSource reads @Transactional
  +-- PlatformTransactionManager gets/starts transaction
             |
             v
Service executes business logic (target method)
             |
       JDBC/JPA/repositories
       same transaction resource
             |
             v
Interceptor commits or rolls back based on outcome
             |
             v
Caller receives return/exception
```

**Key mechanism**: the proxy is the representative object that the caller actually invokes; the proxy gets the chance to run before/after/exception logic around the call to the target. If the caller holds a direct reference to the target object bypassing the proxy, the transaction interceptor is not executed.

### 4.1. Why Is a Transaction Manager Needed?

The proxy knows *when* to manage a transaction, but does not itself know *how* to open and commit a transaction on the real resource. The transaction manager performs that job. For example, `DataSourceTransactionManager` coordinates JDBC connections from a `DataSource`; `JpaTransactionManager` coordinates the EntityManager and its underlying resource transaction.

Having `@Transactional` and a proxy without a missing or matching manager causes the call to fail due to configuration, rather than silently turning into a valid transaction. Conversely, merely creating a transaction manager bean **does not automatically turn** every Java method call into a proxied call.

### 4.2. What Does @EnableTransactionManagement Mean?

In plain Spring Framework, you typically use:

```java
@Configuration
@EnableTransactionManagement
class TransactionConfig {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }
}
```

This is an **illustrative configuration snippet**, requiring a configured `DataSource` and corresponding imports. `@EnableTransactionManagement` registers the infrastructure for processing `@Transactional` in the application context. When combined with appropriate beans and a manager, transaction advice can be applied.

**Note on Spring Boot:** auto-configuration can provide both the manager and declarative transaction processing when conditions are met; not every Boot application is required to write `@EnableTransactionManagement` manually. Conversely, removing this annotation from a Boot application **is not a reliable test to disable transactions** because Boot may still enable it automatically. You must check the actual configuration/context.

### 4.3. A Proxy Is Not @Transactional Itself

A bean may be proxied because of transaction advice or other advice; `AopUtils.isAopProxy(bean)` checks for a proxy, **not whether a specific method will run inside a transaction**. To prove that, check whether a transaction is active inside the exact method, the commit/rollback state after the call, and the real resource.

In proxy mode, Spring can use a JDK interface proxy or a class-based proxy (CGLIB). The choice depends on configuration, bean type, and environment; you should not guess solely from the presence of `@Transactional`. In the example below, the service declares no interface, so Spring uses a class-based proxy.

## 5. When Is an Annotation "Present" Yet Has No Effect?

### 5.1. Objects Created with `new` Outside the Bean Lifecycle

```java
PaymentService service = new PaymentService();
service.charge();
```

If no Spring proxy/interceptor wraps the object, `charge` is just a plain Java method. Metadata can still be read via reflection, but no transaction is started automatically. Similarly, creating instances manually in code instead of injecting beans bypasses Spring infrastructure.

### 5.2. Self-Invocation: `this.method()` Goes Directly to the Target

```java
@Service
class OrderService {
    public void handle() {
        this.save();
    }

    @Transactional
    public void save() {
        // Write data
    }
}
```

This is illustrative code (omitting the repository). In the **default proxy mode**, even if an external caller invokes `orderService.handle()` through the proxy, the call `this.save()` happens inside the target and does not pass through the proxy again. If `handle()` is not already in a transaction, `save()` will not start a transaction on its own because of its annotation.

**Subtle point:** if `handle()` has already opened a transaction, `this.save()` can execute **inside the existing transaction** because the thread is already participating in it, but `save()`'s own attributes (such as `REQUIRES_NEW`) are not applied via self-invocation. Therefore, "self-invocation never has a transaction" is too strong a conclusion; the accurate conclusion is that **internal calls do not receive separate interception**.

Common fixes: move the operation needing an independent boundary to another bean and inject/call that bean, or redesign where the transaction boundary sits. You should not rely on `AopContext.currentProxy()` as a default way to rescue the design.

### 5.3. Some Methods Cannot Be Intercepted

Spring AOP proxies have Java proxy limitations: `private` methods cannot be overridden/intercepted by a class-based proxy; `final` methods cannot be overridden by a subclass, so class-proxy transaction advice cannot intercept those calls. With a JDK proxy, methods on the interface can be delegated through the interface proxy; methods that exist only on the target class are not exposed on the JDK proxy as interface methods.

In Spring Framework 6.x, class-based proxies may support certain `protected` or package-private methods depending on configuration, but **public, non-final methods on a concrete Spring bean** are the most predictable and testable choice. Do not assume all non-public methods behave the same across all versions.

A method in `@PostConstruct` or during bean initialization is also not a safe place to expect a complete proxy to intercept calls. Move startup logic to calls through a fully initialized bean.

### 5.4. Annotation and Context Mismatch

Transaction infrastructure is registered in a specific `ApplicationContext`. If a service bean lives in a parent context while annotation processing is enabled only in a child servlet context, Spring may only scan beans in the child context. Similarly, missing `@ComponentScan`, excluded auto-configuration, or a missing transaction manager with the expected name can lead to missed interception or configuration errors.

### 5.5. Annotation Placed on an Interface

Spring can pick up `@Transactional` metadata on an interface in certain proxy situations. However, Java annotations are not inherited from interfaces in the sense of `@Inherited`, and AspectJ weaving does not pick up interface annotations the same way. To avoid depending on mechanism differences, Spring recommends annotating **methods on the concrete class**.

### 5.6. Switching Threads or Using Reactive

`PlatformTransactionManager` normally binds imperative transactions to the current thread. Calling `@Async` or spawning a new thread does not automatically transfer an existing transaction to that thread. For reactive pipelines, Spring uses a different mechanism (`ReactiveTransactionManager` and Reactor context), and calls must be properly composed within the reactive pipeline. Having the same annotation **does not mean having the same runtime context**.

## 6. Runnable Example: Same @Transactional, Three Different Outcomes

This Java 17+ example uses Spring Boot 3.3.13, Spring JDBC, H2 in-memory, and a simple table. The Spring Boot version is pinned to reproduce the lesson; for production applications, choose a still-supported version.

All three write attempts intentionally throw `IllegalStateException` **after the INSERT statement**:

- Calling `service.writeThenFail(...)` externally through the Spring proxy: transaction is active, INSERT is rolled back.
- Calling `service.selfCall()` which then calls `this.writeThenFail(...)`: the annotation on the internal call is not intercepted, INSERT is auto-committed.
- Creating `new PlainWriter(jdbc)` and calling the `@Transactional` method: not a Spring bean/proxy, INSERT is auto-committed.

### 6.1. Project Structure

```text
transaction-metadata-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/metadata/
    │   ├── MetadataApplication.java
    │   └── EventService.java
    └── resources/
        └── schema.sql
```

**`settings.gradle`**

```groovy
rootProject.name = 'transaction-metadata-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

The application uses only the JDBC starter, without declaring `spring-boot-starter-web`, so no web server is needed. The starter provides Spring transaction support and `JdbcTemplate`, H2 provides an in-memory database, and Boot initializes the schema from `schema.sql`.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE lesson_event (
    id INT PRIMARY KEY,
    source VARCHAR(32) NOT NULL
);
```

**`src/main/java/demo/metadata/EventService.java`**

```java
package demo.metadata;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class EventService {
    private final JdbcTemplate jdbc;

    public EventService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void writeThenFail(int id, String label) {
        boolean active =
            TransactionSynchronizationManager.isActualTransactionActive();
        System.out.println(label + " txActive=" + active);

        jdbc.update(
            "INSERT INTO lesson_event(id, source) VALUES (?, ?)",
            id, label
        );

        throw new IllegalStateException("demo-error");
    }

    public void selfCall() {
        // This call does not go through the Spring proxy a second time.
        this.writeThenFail(2, "self");
    }
}
```

The `writeThenFail` method is public and non-final, and is called through the proxy in the first case. In the `selfCall` internal call, a separate transaction is not activated. `TransactionSynchronizationManager.isActualTransactionActive()` is a convenient observation helper in the imperative model, **not a substitute for checking commit/rollback in the DB**.

**`src/main/java/demo/metadata/MetadataApplication.java`**

```java
package demo.metadata;

import javax.sql.DataSource;

import org.springframework.aop.support.AopUtils;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@SpringBootApplication
@EnableTransactionManagement
public class MetadataApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetadataApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(EventService service, JdbcTemplate jdbc) {
        return args -> {
            boolean annotated = EventService.class
                .getMethod("writeThenFail", int.class, String.class)
                .isAnnotationPresent(Transactional.class);
            System.out.println("annotationPresent=" + annotated);
            System.out.println("serviceProxied=" + AopUtils.isAopProxy(service));

            try {
                service.writeThenFail(1, "external");
            } catch (IllegalStateException ex) {
                System.out.println("external exception=" + ex.getMessage());
            }
            System.out.println("rows#1=" + count(jdbc, 1));

            try {
                service.selfCall();
            } catch (IllegalStateException ex) {
                System.out.println("self exception=" + ex.getMessage());
            }
            System.out.println("rows#2=" + count(jdbc, 2));

            try {
                new PlainWriter(jdbc).writeThenFail();
            } catch (IllegalStateException ex) {
                System.out.println("new exception=" + ex.getMessage());
            }
            System.out.println("rows#3=" + count(jdbc, 3));
        };
    }

    private static int count(JdbcTemplate jdbc, int id) {
        Integer value = jdbc.queryForObject(
            "SELECT COUNT(*) FROM lesson_event WHERE id = ?",
            Integer.class, id
        );
        return value;
    }

    static class PlainWriter {
        private final JdbcTemplate jdbc;

        PlainWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void writeThenFail() {
            boolean active =
                TransactionSynchronizationManager.isActualTransactionActive();
            System.out.println("new txActive=" + active);

            jdbc.update(
                "INSERT INTO lesson_event(id, source) VALUES (?, ?)",
                3, "new"
            );

            throw new IllegalStateException("demo-error");
        }
    }
}
```

**Details to observe**:

- `EventService` is a Spring bean. `@EnableTransactionManagement` enables transaction infrastructure, and the `PlatformTransactionManager` bean manages the `DataSource` used by `JdbcTemplate`. To keep the demo self-contained, we declare the manager explicitly, even though Boot can auto-configure a manager in many setups.
- `demo(EventService service, ...)` receives the post-processed/proxied Spring bean rather than doing `new EventService(...)`.
- `AopUtils.isAopProxy(service)` confirms the service is proxied; `isAnnotationPresent` only confirms **metadata exists** on the class method. These two checks are not equivalent.
- The three cases use separate IDs 1, 2, and 3; all exceptions are caught by the caller **after** the method finishes; `count` runs outside the service's transaction so it sees the DB state after commit/rollback.
- `PlainWriter` is a nested class not registered as a bean. Even though its method has `@Transactional`, calling it via `new` has no advice.

### 6.2. Running and Comparing Stdout

Requires JDK 17+ and Gradle 8.x. From the `transaction-metadata-demo` directory:

```bash
gradle bootRun
```

If the project already includes a Gradle Wrapper, run `./gradlew bootRun` on Linux/macOS or `gradlew.bat bootRun` on Windows. Do not use `javac` directly for the project above because the code depends on external Spring/H2 libraries outside the JDK; Gradle handles downloading the classpath, compiling, and launching.

Ignoring Spring Boot/Gradle startup logs, the `System.out.println` lines from the program, in exact order, are:

```text
annotationPresent=true
serviceProxied=true
external txActive=true
external exception=demo-error
rows#1=0
self txActive=false
self exception=demo-error
rows#2=1
new txActive=false
new exception=demo-error
rows#3=1
```

**Result explanation**:

1. `annotationPresent=true`: reflection finds `@Transactional` on `EventService.writeThenFail`. This alone does **not** prove the transaction works.
2. `serviceProxied=true`: Spring created an AOP proxy for the service.
3. `external txActive=true`: the external call through the proxy enters `writeThenFail`, and the interceptor starts a transaction. The escaping runtime exception causes the transaction manager to roll back. `rows#1=0` proves no row with id 1 remains.
4. `self txActive=false`: `selfCall` is not annotated with `@Transactional` and `this.writeThenFail` bypasses the proxy. Because the connection has no Spring-opened transaction for this call, JDBC/H2 auto-commits the INSERT successfully; the subsequent Java exception does not roll it back automatically. `rows#2=1`.
5. `new txActive=false`: `PlainWriter` is not a bean/proxy. The annotation is still in the class file, but there is no interceptor. INSERT auto-commits; `rows#3=1`.

Note that `rows#2` and `rows#3` rely on the default auto-commit behavior of the H2 connection provided by the pool in this example. An outer transaction opened by the caller, or a custom `DataSource`/connection, could change the outcome. Therefore do not interpret this as "self-invocation **always** auto-commits"; the durable conclusion is that **the infrastructure of the internally called method is not activated**.

### 6.3. What Happens If We Move the Annotation?

If you put `@Transactional` directly on `selfCall` (ensuring `service.selfCall()` is called from another bean through the proxy), a transaction is opened **before** code inside `selfCall` runs; `this.writeThenFail` then participates in that existing transaction. Thus the row with id 2 will roll back even though the internal call is not separately intercepted. This is the key distinction between:

- **"The specific call is intercepted"**: determines whether advice applies to that method itself.
- **"A transaction is currently active"**: may have been created beforehand by an outer call.
- **"Does data roll back"**: also depends on the manager/resource/exception/commit scope.

Do not apply this change when comparing against the original stdout, as it alters the purpose of the test case.

## 7. Three Verification Layers in Real Applications

### Layer A — Does the Metadata Exist and Is It in the Right Place?

Check:

- Is the annotation `org.springframework.transaction.annotation.Transactional` or a variant with a different processing mechanism?
- Is it placed on the concrete method/class that Spring actually sees? Are there annotations on interfaces, inherited methods, or overridden metadata?
- Are `propagation`, `readOnly`, and `rollbackFor` attributes declared as intended?
- When using a composed annotation, does the infrastructure read the meta-annotation and aliases properly?

Reflection `isAnnotationPresent` is only suitable for a simple check; Spring has its own annotation/meta-annotation lookup mechanism. Positive reflection **does not yet** prove that a transaction is running.

### Layer B — Does the Call Actually Pass Through Spring Transaction Advice?

Check:

- Is the instance a Spring-managed bean provided by injection/context?
- Does the bean have an AOP proxy or corresponding AspectJ weaving mechanism?
- Does the caller come from another bean through the proxy, or is it `this.method()`/`new`/constructor/`@PostConstruct`?
- Can the method be intercepted by the proxy? Is it `final`/`private`, or is a JDK proxy not exposing the method?
- Is transaction management enabled in the right `ApplicationContext`?
- Are there multiple beans with the same or similar names causing code to accidentally use an instance outside the container?

Having a proxy does not mean every method receives advice; you must check the pointcut/transaction attribute for the actual method.

### Layer C — Does the Transaction Take Effect on the Right Resource and Outcome?

Check:

- Which manager is selected, and does it match the `DataSource` / `EntityManagerFactory` used by the repository?
- Even if a method reports an active transaction, does the data access library open an independent connection or send I/O to another system?
- Does the exception escape to the interceptor according to rollback rules? Does a checked exception need `rollbackFor`?
- Does this scope **create a new** transaction or only **join** an outer transaction (`REQUIRED`)? Which scope owns the final commit?
- Is there an `@Async`/new thread call that drops thread-bound context?
- After the method finishes, did the DB actually commit/roll back as expected?

**The strongest evidence** is a test that performs partial writes and then throws an error, followed by reading back the DB state after the transaction has ended. Checking `TransactionSynchronizationManager.isActualTransactionActive()` helps diagnose issues, but is not enough to conclude that all operations share one transaction.

## 8. Common Misconceptions

| Misconception | Reality | How to verify |
| --- | --- | --- |
| "Having `@Transactional` means it always rolls back on exception." | The annotation is only metadata; infrastructure and an intercepted call are also required. | Run the `new` and self-invocation cases. |
| "Just having `spring-tx` on the classpath is enough." | The library provides APIs/infrastructure, but you must configure a manager and where advice applies. | Inspect bean/configuration and the call path. |
| "`@EnableTransactionManagement` automatically configures every database." | This annotation enables transaction annotation processing; a matching manager/resource must still be provided or auto-configured. | Check the manager bean and `DataSource` in use. |
| "In Spring Boot you must always write `@EnableTransactionManagement`." | Boot can enable transaction management automatically when conditions match. | Check auto-configuration/runtime for your Boot version. |
| "Removing `@EnableTransactionManagement` definitely disables transactions." | Boot may still activate transaction management automatically. | Verify at runtime rather than inferring from one annotation. |
| "A proxied bean means every method is transactional." | A proxy may apply advice selectively by method/metadata. | Check the called method and DB results. |
| "`this.inner()` automatically creates `REQUIRES_NEW` if inner is annotated." | In proxy mode, self-invocation is not separately intercepted by advice. | Split into another bean and call through the proxy if a separate boundary is needed. |
| "The annotation can roll back email/HTTP calls." | Local DB transactions do not control side effects outside the DB. | Identify which resources are managed by the manager. |
| "An annotation out of the box rolls back checked exceptions by default." | Default rules may not roll back checked exceptions, depending on version/configuration. | Use `rollbackFor` and test the DB state. |
| "A method marked `readOnly=true` definitely cannot write." | This is a hint/rule depending on driver/manager/ORM enforcement capabilities. | Check the actual resource and constraints. |

The most dangerous bug in practice is not necessarily an application crash. The application may **keep running** and the `INSERT` succeeds, yet a subsequent error fails to roll back because the call bypassed the proxy. If you only test the happy path, the problem is hard to surface.

## 9. Redesigning for a Clear Annotation Call Path

A sensible structure:

```java
@Service
public class CheckoutService {
    private final InventoryService inventory;

    public CheckoutService(InventoryService inventory) {
        this.inventory = inventory;
    }

    public void placeOrder() {
        inventory.reserveStock(); // Through the injected bean.
    }
}

@Service
public class InventoryService {
    @Transactional
    public void reserveStock() {
        // Write data to the resource managed by the transaction manager.
    }
}
```

This is **illustrative architectural code**, missing repositories and not a standalone runnable program. When both `CheckoutService` and `InventoryService` are Spring-managed beans and transaction infrastructure is enabled, the call `inventory.reserveStock()` can pass through `InventoryService`'s proxy. If the entire order placement must be atomic, you may need **one transaction wrapping the use case in `CheckoutService`** rather than small transactions per step; boundaries must follow business logic and resources.

If an independent transaction is needed, make the purpose and propagation explicit; do not "patch" it by sprinkling annotations on every helper. Do not pass an entity manager or connection outside a transaction and assume it participates in the scope.

### 9.1. When AspectJ Is Needed Instead of Proxies

Spring can use `@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)` with appropriate dependencies/weaving to apply transaction advice via bytecode weaving, allowing self-invocation to be intercepted. This is a different mechanism, not the default behavior, and requires separate infrastructure (such as `spring-aspects` and compile-time/load-time weaving). Do not enable AspectJ merely to avoid redesigning a few internal calls if transactional needs do not demand it.

### 9.2. When Using Spring Test

A test method annotated with `@Transactional` in Spring TestContext may have a transaction opened and rolled back after the test by the framework. That can make tests pass even when the service's production transaction configuration is broken. Add tests that call the service bean at a realistic boundary, trigger an error between write steps, finish the scope, and read the DB from an independent transaction; do not rely on default test rollback as proof that the service is properly proxied.

## 10. Quick Debugging Workflow When @Transactional "Doesn't Work"

1. **Reproduce in a controlled way** with a single record: insert, throw `RuntimeException`, inspect the DB after the call.
2. **Verify the instance:** print/log `AopUtils.isAopProxy(service)` and determine whether the object comes from the Spring context or `new`.
3. **Inspect the call graph:** is there `this.method()`, a private/final method, constructor/`@PostConstruct`, or a new thread call?
4. **Check configuration:** is `@EnableTransactionManagement` or Boot auto-config enabled in the right context; which transaction manager bean is available?
5. **Check resources:** do JDBC/JPA/repositories use the right manager and the same transactional connection/entity manager?
6. **Check rules:** does the exception escape rather than being caught and returned, is it checked or unchecked, and are `rollbackFor` or `noRollbackFor` set?
7. **Check propagation:** does the method join an outer transaction or create its own, and who owns the final commit?
8. **Observe outcomes:** an active transaction is a signal; reading back the DB after commit/rollback confirms the business effect.

You can enable `org.springframework.transaction.interceptor` logging at TRACE level along with transaction manager logs during investigation; use logs to verify advice execution while avoiding logging secrets or sensitive payloads. In proxy mode, stack traces or debugging may show interceptor classes around the method; they are indicators of the mechanism running, not a substitute for data tests.

## 11. Self-Check

**Question 1.** Why is putting `@Transactional` on a Java method not enough to open a transaction?  
**Answer:** Because the annotation only stores metadata. Infrastructure such as `TransactionAttributeSource`, a transaction advisor/proxy, `TransactionInterceptor`, and an appropriate transaction manager are needed to actually handle the call.

**Question 2.** `EventService.writeThenFail` has the annotation; why did the call from `selfCall` not roll back in the example?  
**Answer:** Because `this.writeThenFail` bypasses the proxy; `selfCall` does not open an outer transaction, so JDBC writes under auto-commit and the exception after INSERT cannot reverse it.

**Question 3.** If `selfCall` is also `@Transactional` and called by another bean through the proxy, does `writeThenFail` need to be intercepted on its own to roll back together?  
**Answer:** Not necessarily. It can run in the transaction **already opened by the outer call**; however, the separate metadata on the inner method is not applied by self-invocation.

**Question 4.** Why does `AopUtils.isAopProxy(service) == true` still not prove that calling `service.someMethod()` is transactional?  
**Answer:** A proxy can apply advice to a specific set of methods. The method in question may lack a transaction attribute, fall outside the pointcut, or its data access logic may not participate in the right transactional resource.

**Question 5.** Does Spring Boot always require users to add `@EnableTransactionManagement`?  
**Answer:** No. Boot has auto-configuration when conditions and dependencies match; verify the actual runtime infrastructure.

**Question 6.** When rollback is not working, will simply adding `rollbackFor = Exception.class` definitely fix it?  
**Answer:** No. If there is no suitable proxy/interceptor/manager or the method is self-invoked, `rollbackFor` metadata is still not processed. You must fix the activation cause first.

## References

- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative transaction implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Proxying mechanisms: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Boot 3.3 — System requirements: https://docs.spring.io/spring-boot/3.3/system-requirements.html

**Takeaway:** `@Transactional` expresses **what semantics a transaction should have**; the Spring runtime must enforce those semantics with the right infrastructure, on the right call, and on the right resource. "Having the annotation", "having the interceptor", and "data committing/rolling back properly" are three separate things that must be verified independently.