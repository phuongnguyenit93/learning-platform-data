# Applicability of @Transactional to public, protected, and package-visible Methods by Spring Version

> **Topic:** Spring Framework — transaction management, **Proxy mechanism** section. This lesson focuses on **method visibility scope** of `org.springframework.transaction.annotation.Transactional` in **proxy mode**: Spring 5.3 and earlier vs. Spring 6.0 and later, JDK interface proxies vs. class-based proxies (CGLIB), and cases where the annotation is present yet transaction advice does not run.

## 1. The Key Answer to Remember

**According to the Spring Framework 6.2 reference documentation:**

- In **Spring Framework 5.3 and earlier**, the default transaction proxy configuration only considers `public` methods. Annotating `protected` or **package-visible/package-private** methods with `@Transactional` normally does not make those methods transaction boundaries through a proxy.
- **Starting with Spring Framework 6.0**, **class-based proxies** can process `@Transactional` on **`protected` and package-visible methods by default**, in addition to `public`, provided the call genuinely enters from outside through the proxy and the method can be overridden/intercepted by the proxy.
- **JDK interface-based proxies** still only intercept **`public` methods declared on the interface exposed by the proxy**. A `public` method residing only on the implementation class and absent from the proxied interface will not be a callable entry point through that interface proxy.
- **`private` methods are not intercepted by Spring AOP proxies**. `final` methods or `final` classes likewise restrict or prevent the subclass proxy mechanism from working accordingly.
- **Self-invocation** — one method of the target calling another via `this.method()` or an implicit call on the same target — **bypasses the proxy**. The Spring 6.0 change **does not remove this rule**.
- If you need to keep the `public`-only policy on Spring 6.x, you can configure `AnnotationTransactionAttributeSource(true)`, corresponding to `publicMethodsOnly = true`.

Do not turn "Spring 6 supports `protected`" into "any `protected` call gets a transaction". **Version + proxy type + overridability + call path + transaction manager** determine the outcome.

## 2. Access Levels in Java

In Java, methods have four common access levels:

```java
public class LedgerService {
    public void publicOperation() {
        // Callable from anywhere if the class and method are accessible.
    }

    protected void protectedOperation() {
        // Callable from the same package; outside the package follows inheritance rules.
    }

    void packageOperation() {
        // No modifier written: accessible only within the same package.
    }

    private void privateOperation() {
        // Accessible only inside the declaring class.
    }
}
```

**Package-visible**, **package-private**, and **default access** in this context refer to the same access level: **no `public`/`protected`/`private` keyword** before the method. There is no Java modifier named `package`.

Distinguish two concepts:

1. **Does Java allow calling the method?** This is a language rule about access modifiers and packages.
2. **Can Spring intercept that call to wrap a transaction?** This is a capability of the proxy and transaction interceptor.

A method can be **valid in Java** yet **not processed by transaction advice**, for example a `private` method annotated with `@Transactional` and called only from inside the bean.

## 3. Matrix by Version and Proxy Type

The table below assumes: Spring manages the bean, the annotation is Spring's own, transaction infrastructure is active, the caller invokes **through the proxy**, the method is not `final`, and a class-based proxy can see/override the method.

| Method | Spring 5.3 and earlier — default class-based proxy | Spring 6.0+ — default class-based proxy | JDK interface proxy across both generations |
| --- | --- | --- | --- |
| `public`, present on interface if using JDK proxy | Yes | Yes | Yes, if declared on the proxied interface |
| `public`, only on implementation | Yes | Yes | No corresponding entry point on the interface proxy |
| `protected` | No, under the old default | **Yes, possible** | No |
| Package-visible / package-private | No, under the old default | **Yes, possible** | No |
| `private` | No | No | No |
| `final` method (class proxy) | Cannot override/intercept | Cannot override/intercept | JDK proxy works differently, but only methods on the interface are called via proxy |

**Table scope:** covers only Spring **transaction proxy mode**. `AspectJ` weaving does not follow this exact proxy matrix because it can weave bytecode instead of creating a proxy class. Different Spring 6.x versions may have implementation/documentation nuances across specific patch releases; when upgrading a running application, verify against the **exact packaged framework version** using integration tests and its corresponding docs. Spring 6.2 reference docs state the default change began in Spring 6.0.

### Small example

```java
@Service
class BillingService {
    @Transactional
    public void pay() {
    }

    @Transactional
    protected void reserve() {
    }

    @Transactional
    void register() {
    }

    @Transactional
    private void auditInternally() {
    }
}
```

This is an **illustrative snippet**, assuming `@Service`, `@Transactional` imports, a Spring context, and a suitable transaction manager. In Spring 6.2 with class-based proxies:

- `pay()` is an interceptable point if called through the proxy.
- `reserve()` and `register()` **can** be intercepted when an external caller can see and invoke the method **on the proxy itself**.
- `auditInternally()` does not become an interception point just from the annotation, because CGLIB cannot override `private`.
- If `pay()` calls `reserve()` directly on `this`, that **internal** call still does not pass through `reserve()`'s own interceptor. If `pay()` already opened a transaction, code inside `reserve()` can see the **existing transaction**; that **does not prove `reserve()`'s annotation was processed**.

## 4. Why Do JDK Proxies and Class-Based Proxies Differ?

### 4.1. JDK dynamic proxy

A JDK proxy creates an object implementing the interface(s) exposed by the bean:

```text
Caller
  |
  | calls InvoicePort.create()
  v
JDK proxy implements InvoicePort
  |
  | TransactionInterceptor, if method has a transaction attribute
  v
InvoiceService implements InvoicePort
  |
  v
Database
```

A JDK proxy does not extend `InvoiceService`; it exposes **interface methods**, which are `public`. Therefore:

```java
public interface InvoicePort {
    void create();
}

@Service
public class InvoiceService implements InvoicePort {
    @Override
    @Transactional
    public void create() {
        // Public method exposed via InvoicePort.
    }

    @Transactional
    public void reindex() {
        // Extra public method on implementation, not in InvoicePort.
    }

    @Transactional
    protected void internalProcess() {
        // Not part of the interface proxy.
    }
}
```

This is an **illustrative snippet**, not three top-level types in a single file. When forcing **JDK interface proxies**, the caller injects `InvoicePort` and calls `create()` through the proxy: this can serve as a transaction boundary. The caller does not have `reindex()` or `internalProcess()` on the `InvoicePort` type. Trying to inject concrete `InvoiceService` when the proxy only implements the interface can cause an incompatible bean injection error; do not work around it by grabbing the raw target and calling it directly, as that bypasses the proxy again.

Crucially, **being `public` alone is not enough for a JDK proxy**: the method must belong to an interface actually proxied, and the call must go through that proxy object.

### 4.2. Class-based proxy (CGLIB)

A class-based proxy is a subclass generated at runtime:

```text
Caller
  |
  | calls proxy.protectedOperation() from where Java permits access
  v
BillingService$$SpringCGLIB... extends BillingService
  |
  | overrides/intercepts visible methods
  v
TransactionInterceptor
  |
  v
BillingService (target)
```

Because a subclass can override methods beyond `public`, Spring 6.0+ extended default transaction processing to `protected` and package-visible methods in class-based proxies.

Nevertheless, subclass capabilities remain bounded by Java:

- `private` cannot be overridden, so it cannot be intercepted via subclassing.
- `final` methods cannot be overridden.
- `final` classes cannot be subclassed to create a class proxy.
- A package-private method declared in a superclass from **another package** may not be visible to the proxy subclass, effectively acting like private for that class.
- Java Module System restrictions or proxy-generation constraints can also affect proxy creation.

A class-based proxy **does not automatically make every method transactional**. Only eligible methods with transaction metadata that are called **through the proxy** are handled by the transaction interceptor.

### 4.3. Selecting proxies via configuration

In plain Spring Framework:

```java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class TransactionConfiguration {
}
```

Requires importing `org.springframework.context.annotation.Configuration` and `org.springframework.transaction.annotation.EnableTransactionManagement`. `proxyTargetClass = true` requests **class-based proxies** for transaction proxy mode. Leaving it `false` means Spring AOP usually uses JDK proxies when the target has interfaces, or class-based proxies when no suitable interface exists.

**Spring Boot note:** Boot has its own AOP defaults and properties, typically favoring class-based proxies in common setups. Do not infer proxy type solely from seeing that a bean has an interface. The complete example below **explicitly forces class-based proxies** so results do not depend on environment defaults.

## 5. The Interceptor Mechanism and External Calls

`@Transactional` provides **metadata**; actual runtime effect requires Spring to configure transaction advice/transaction manager and the bean to be called through its proxy.

Valid call diagram:

```text
CheckoutController or CommandLineRunner
    |
    | reference injected by Spring
    v
Spring proxy of BillingService
    |
    +-- check method metadata and transaction manager
    +-- open/join transaction if appropriate
    +-- invoke target method
    +-- commit or roll back per outcome
```

Self-invocation:

```java
@Service
class StockService {

    public void start() {
        reserve(); // Equivalent to this.reserve(): bypasses proxy.
    }

    @Transactional
    protected void reserve() {
        // Annotation is not intercepted separately in the call above.
    }
}
```

This is a **snippet**, not runnable standalone. Even though Spring 6.2 supports `protected` on class-based proxies, `start()` calls `reserve()` **on the target**, not through the proxy to run `reserve()`'s transaction advice.

If `start()` had no prior transaction, `reserve()` can run **without a transaction**. If `start()` already had a transaction, `reserve()` executes **inside the existing transaction**, yet `reserve()`'s own annotation is still not activated separately (for instance, its own `REQUIRES_NEW` or `timeout` does not apply through self-invocation).

A simple, testable design:

```java
@Service
class StockReserveService {
    @Transactional
    public void reserve() {
        // Clear transaction boundary on a public method.
    }
}

@Service
class StockWorkflowService {
    private final StockReserveService reservation;

    StockWorkflowService(StockReserveService reservation) {
        this.reservation = reservation;
    }

    public void start() {
        reservation.reserve(); // Called through another Spring bean proxy.
    }
}
```

These are illustrative classes in the same application package. Extracting a bean makes the transaction boundary explicit and avoids relying unnecessarily on non-public methods.

## 6. Complete Example: Proving with Real Rollbacks on H2

This demo uses **Spring Boot 3.5.7**, Spring Framework 6.2, **Java 17**, Maven, Spring JDBC, and H2. We intentionally throw `IllegalStateException` after writing to the database to verify whether transaction advice ran:

- When a call **is intercepted by the proxy** and creates a transaction, the insert **rolls back** → no row remains.
- When a call **is not intercepted**, `JdbcTemplate` executes the insert using a connection in auto-commit mode under the demo config → the row **remains** even though the Java method subsequently throws an exception.

The comparison covers `public`, `protected`, package-private, `private`, and **self-invocation**. The runner and service reside in **the same Java package** so Java allows the runner to invoke `protected`/package-private methods on the bean proxy.

### 6.1. Project structure

```text
method-visibility-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── vn/example/visibility/
        │       ├── VisibilityApplication.java
        │       └── VisibilityService.java
        └── resources/
            └── application.properties
```

### 6.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>method-visibility-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-jdbc` provides JDBC/transaction infrastructure and a connection pool. The H2 dependency provides an in-memory database to observe rollbacks without installing an external database.

### 6.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:visibility_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver
```

`DB_CLOSE_DELAY=-1` keeps the in-memory database alive for the JVM's lifetime even after connections return to the pool. This is solely for demo configuration.

### 6.4. `src/main/java/vn/example/visibility/VisibilityService.java`

```java
package vn.example.visibility;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class VisibilityService {
    private final JdbcTemplate jdbc;

    public VisibilityService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void publicFail() {
        insertAndFail(1, "public");
    }

    @Transactional
    protected void protectedFail() {
        insertAndFail(2, "protected");
    }

    @Transactional
    void packageFail() {
        insertAndFail(3, "package");
    }

    @Transactional
    private void privateFail() {
        insertAndFail(4, "private");
    }

    public void callPrivate() {
        privateFail();
    }

    @Transactional
    void selfTargetFail() {
        insertAndFail(5, "self");
    }

    public void callSelf() {
        selfTargetFail();
    }

    private void insertAndFail(int id, String label) {
        boolean active =
            TransactionSynchronizationManager.isActualTransactionActive();

        System.out.printf("%s active=%s%n", label, active);
        jdbc.update(
            "INSERT INTO audit_items(id, label) VALUES (?, ?)",
            id, label
        );
        throw new IllegalStateException("Demo failure: " + label);
    }
}
```

Explanation of each method group:

1. `publicFail()` has `@Transactional` and is called from outside the bean through the proxy. Transaction starts → insert then exception → rollback.
2. `protectedFail()` is also called from **another bean in the same package** through the class-based proxy. With Spring 6.2 defaults, the transaction interceptor handles it → rollback.
3. `packageFail()` has no access modifier, also called from another bean **in the same package** through the class-based proxy → rollback under Spring 6.2 defaults.
4. `privateFail()` has the annotation yet **cannot be overridden in CGLIB**. `callPrivate()` has no transaction and calls the private method directly → not wrapped separately by the transaction interceptor.
5. `selfTargetFail()` is package-private and annotated, yet `callSelf()` invokes it from **the same target object** → no proxy call for the inner method.
6. `insertAndFail()` is a private helper with no annotation, called along all five paths. Whether the helper sees a transaction depends on the **caller's transaction boundary**, not the helper's own visibility.

All `@Transactional` methods can appear validly in source code. The mere fact that Java compiles and runs does not confirm the annotation took effect.

### 6.5. `src/main/java/vn/example/visibility/VisibilityApplication.java`

```java
package vn.example.visibility;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class VisibilityApplication {

    public static void main(String[] args) {
        SpringApplication.run(VisibilityApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(VisibilityService service, JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE audit_items (" +
                "id INT PRIMARY KEY, label VARCHAR(20) NOT NULL)"
            );

            runCase("public", service::publicFail, jdbc);
            runCase("protected", service::protectedFail, jdbc);
            runCase("package", service::packageFail, jdbc);
            runCase("private", service::callPrivate, jdbc);
            runCase("self", service::callSelf, jdbc);
        };
    }

    private static void runCase(String label,
                                Runnable operation,
                                JdbcTemplate jdbc) {
        try {
            operation.run();
        } catch (IllegalStateException expected) {
            // Only catch the intentional exception for the example.
        }

        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_items WHERE label = ?",
            Integer.class,
            label
        );
        System.out.printf("%s rows=%d%n", label, count);
    }
}
```

Because `VisibilityApplication` and `VisibilityService` share the `vn.example.visibility` package, the method references `service::protectedFail` and `service::packageFail` **are permitted by Java compilation**. If you move the runner to another package, `packageFail` becomes inaccessible, and `protectedFail` is also subject to Java's `protected` access rules.

`@EnableTransactionManagement(proxyTargetClass = true)` makes explicit that the `VisibilityService` bean needs a class-based proxy. Neither the class nor the interceptable methods are `final`.

### 6.6. Run

From the `method-visibility-demo` directory:

```bash
java -version
mvn -version
mvn -q package
java -jar target/method-visibility-demo-1.0.0.jar
```

With Spring Boot 3.5.7 / Spring Framework 6.2 and the configuration above, the lines **printed by the demo code itself** are:

```text
public active=true
public rows=0
protected active=true
protected rows=0
package active=true
package rows=0
private active=false
private rows=1
self active=false
self rows=1
```

Spring Boot may also print startup logs; the block above is only the **intentional stdout of the demo**, in the exact order invoked by the runner. No HTTP console is expected because the app only has a `CommandLineRunner` and no Spring Web starter.

### 6.7. Why `rows=0` or `rows=1`?

| Call | Transaction at execution point? | After `IllegalStateException` | Surviving row count |
| --- | --- | --- | --- |
| `publicFail()` | Yes, via proxy | Rollback | 0 |
| `protectedFail()` | Yes, Spring 6.2 + class proxy + external call | Rollback | 0 |
| `packageFail()` | Yes, Spring 6.2 + class proxy + external call | Rollback | 0 |
| `callPrivate()` → `privateFail()` | No, because private is not proxy-intercepted | JDBC auto-commit per demo config | 1 |
| `callSelf()` → `selfTargetFail()` | No, because of self-invocation | JDBC auto-commit per demo config | 1 |

`TransactionSynchronizationManager.isActualTransactionActive()` proves an **actual transaction** is bound to the thread when the code runs. To verify even more rigorously, the demo also checks the **rollback outcome in the database** after the exception escapes the method. Checking only `active=true` inside a context that already has an outer transaction can mislead you into thinking an inner method's annotation was intercepted.

**Important:** the `rows=1` lines only describe this **single-threaded demo with no outer transaction**, `JdbcTemplate`/H2 auto-commit, and an exception after INSERT. In a real application, an unintercepted method may still be executing inside a transaction opened elsewhere. In that case the final row count depends on the actual transaction; never assume private/self-invocation **always** causes data to commit.

## 7. Configuring `publicMethodsOnly`: Keeping a Public-Only Policy

Spring 6.2 allows registering a custom `TransactionAttributeSource` to **ignore non-public methods** in transaction metadata, even when a class-based proxy could intercept the method at the Java level.

Standalone configuration:

```java
package vn.example.visibility;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionAttributeSource;

@Configuration
class PublicOnlyTransactionConfiguration {

    @Bean
    TransactionAttributeSource transactionAttributeSource() {
        return new AnnotationTransactionAttributeSource(true);
    }
}
```

`true` corresponds to `publicMethodsOnly = true`. It restores visibility matching to the public-only policy used by default prior to Spring 6.0.

This is a **configuration variant**, not a required file for the section 6 demo. If added to the demo project, Spring 6.2's class-based proxy may still exist, yet transaction metadata for `protectedFail()` and `packageFail()` is filtered out by the public-only policy. When rerun with no outer transaction, you will see those methods no longer roll back inserts as they did under section 6's default configuration.

You can restore non-public method inspection in supporting configurations with:

```java
@Bean
TransactionAttributeSource transactionAttributeSource() {
    return new AnnotationTransactionAttributeSource(false);
}
```

The `false` argument allows metadata to consider non-public methods; it **does not turn private/final methods into proxy-interceptable targets**. Likewise, it does not make JDK proxies expose methods absent from interfaces, nor does it fix self-invocation.

When using Spring Boot/JPA/multi-manager setups, understand the transaction infrastructure created by the framework. Do not add custom beans merely because "the docs show an example": replacing `TransactionAttributeSource` affects transaction annotations across the corresponding application context.

## 8. When Upgrading from Spring 5.3 to Spring 6.x

A change in default visibility can introduce **new behavior** that legacy code never exhibited before.

Suppose legacy code has:

```java
@Service
class LegacyReportService {

    @Transactional
    protected void updateSnapshot() {
        // Write to multiple tables.
    }
}
```

Before the upgrade, with Spring 5.3's default transaction proxy, the annotation on `protected` could be ignored. Upon upgrading to Spring 6.2 with class-based proxies, a valid call **through the proxy** to `updateSnapshot()` can start a real transaction. This is usually beneficial for atomicity, yet it can also change:

- When locks and connections are held.
- How rollback behaves if a `RuntimeException` or `Error` escapes.
- Interaction with existing transactions (default `REQUIRED`), propagation, and `rollbackOnly`.
- Number of transactions started, connection pool demand, and logging observations.
- Existing tests that inadvertently relied on auto-commit or never verified rollback.

**Focused audit steps:**

1. Confirm the **actual runtime** `spring-tx` version, not just the root POM version; dependency management and transitive dependencies can alter it.
2. Confirm the proxy type under runtime configuration: JDK interface or class-based.
3. Search for `@Transactional` on `protected` and package-visible methods, including in superclasses.
4. Determine whether calls reach them **through proxies from other beans** or via self-invocation, private/final, or non-proxied Java access paths.
5. Verify commit/rollback with integration tests against the same database and transaction manager as deployed.
6. If you need to preserve the old public-only policy for a safe migration, consider `AnnotationTransactionAttributeSource(true)` and plan intentional design changes.

Do not mechanically make every method `public`: making APIs public affects encapsulation. For business boundaries invoked across multiple beans, `public` is usually clearer and less dependent on proxy mechanics; `protected`/package-private can make sense for package-internal APIs if tested thoroughly.

## 9. Cases Where the Annotation Is Present Yet Not Intercepted

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `@Transactional` on `protected` has no effect in Spring 5.3 | Default public-only policy | Use a public boundary or check supported versions/configs. |
| Spring 6.x, `protected` still has no transaction | JDK interface proxy, self-invocation, final method, or ineligible method | Check proxy type, call path, and visibility. |
| Package-visible method from superclass in another package is not intercepted | Proxy cannot validly see/override that method | Place boundary at an accessible method or extract a service. |
| `private` annotated yet rollback does not happen | Proxy cannot override/intercept private methods | Put transaction on a public service method or use another suitable mechanism. |
| Bean instantiated via `new` has no transaction | Not managed by Spring container/proxy | Inject the Spring-managed bean. |
| `this.method()` does not trigger its own transaction attributes | Self-invocation bypasses proxy | Call through another bean or restructure boundaries. |
| `public` on implementation yet JDK proxy does not expose it | Method is absent from the proxied interface | Declare the API on the interface or use a class proxy where appropriate. |
| Transaction is active yet inner `REQUIRES_NEW`/`timeout` does not take effect | Inner method annotation not intercepted or inner joins existing transaction | Inspect call graph and propagation. |
| Test rolls back even though service has no transaction | Test method has a transaction opened by Spring TestContext | Run the test outside a test-managed transaction to verify service boundaries. |

### 9.1. Annotations on interfaces vs. implementations

Spring allows placing `@Transactional` on interfaces or implementations in many setups; however, Spring recommends **placing it on the concrete class/method** to avoid relying on metadata lookup mechanics and especially to avoid differences with AspectJ weaving. Java annotations on interfaces are not automatically inherited like class annotations. When switching between proxy mode and AspectJ, or between JDK and class proxies, re-verify transaction attributes instead of relying on assumptions.

### 9.2. Same method called inside an existing transaction

Example:

```java
@Transactional
public void outer() {
    helper(); // helper is called internally.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
protected void helper() {
    // Will not get REQUIRES_NEW if self-invocation bypasses the proxy.
}
```

This is a snippet; `Propagation` import is needed. `helper()` can run **inside `outer()`'s transaction** because `outer()` already opened one, yet it **does not create a new transaction** as the inner annotation asks. Checking only `isActualTransactionActive() == true` can mislead you into thinking the inner annotation worked. Verify physical boundaries and commit/rollback results in a dedicated test.

### 9.3. Methods in `@PostConstruct` or constructors

Proxies must be created and initialized before callers use them. Calling an annotated method inside a constructor or initialization callback like `@PostConstruct` may not pass through the transaction proxy as expected. Data initialization should use a suitable Spring startup mechanism that invokes the bean through its proxy after the context is ready, or use the programmatic transaction API when special needs arise.

### 9.4. `final` methods, `final` classes, and Java modules

CGLIB uses subclassing; hence `final` blocks subclassing/overriding. In Kotlin, classes/methods are final by default unless opened with `open` or an appropriate compiler plugin. In restricted Java modules, proxies can hit class-generation access limits. Verify startup errors and actual runtime proxies rather than assuming raising visibility fixes every case.

## 10. AspectJ Mode: Fundamentally Different from Proxy Mode

You can use Spring transaction management with `AdviceMode.ASPECTJ` instead of `AdviceMode.PROXY`. AspectJ weaves transaction advice into bytecode, avoiding the "must call through a proxy object" restriction. Per Spring docs, the aspect can handle self-invocation and non-public methods when woven properly, depending on annotation placement and build setup.

Illustrative configuration:

```java
@Configuration
@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
class AspectJTransactionConfiguration {
}
```

This is a **configuration snippet**, requiring `org.springframework.context.annotation.AdviceMode` and `@EnableTransactionManagement` imports. Actually using AspectJ requires the `spring-aspects` dependency and proper compile-time or load-time weaving configuration. Simply adding `mode = ASPECTJ` without enabling weaving **is not enough**.

Important scope reminders:

- This lesson analyzes **proxy mode**, the common default.
- **"Private does not work"** is a conclusion about **proxy advice**. With weaving, behavior can differ; inspect the specific annotation and weaving setup.
- Do not switch to AspectJ just for a "quick fix" on one self-invocation: it increases configuration, build, debugging, and runtime complexity. Usually extracting the boundary to another bean solves it cleanly.

## 11. How to Verify at Runtime and in Tests

### 11.1. Confirming you hold a proxy

In tests/diagnostics you can use:

```java
boolean proxy = AopUtils.isAopProxy(service);
boolean jdk = AopUtils.isJdkDynamicProxy(service);
boolean cglib = AopUtils.isCglibProxy(service);

System.out.printf(
    "proxy=%s, jdk=%s, cglib=%s%n",
    proxy, jdk, cglib
);
```

This is a **snippet**, needing `org.springframework.aop.support.AopUtils` and a Spring-injected `service` variable. It reveals the proxy type, yet **does not prove every method has transaction advice**. Verify by calling the method through the proxy in a commit/rollback test and checking the transaction manager.

### 11.2. Measuring active transactions with Spring APIs

Inside the invoked method:

```java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
System.out.println("tx active: " + active);
```

This is a snippet; needs `org.springframework.transaction.support.TransactionSynchronizationManager`. `active=true` indicates a current transaction on the thread, **not** that the method's own annotation was intercepted. An unadvised inner method can still run while a caller already opened a transaction.

### 11.3. Targeted integration tests

A test comparing visibility should:

1. Use the exact framework version, transaction manager, and proxy mode being evaluated.
2. Create a Spring context and invoke the **injected bean**, not `new` service instances.
3. Test `public`, `protected`, and package-visible methods from a **Java-valid caller** outside the target.
4. To observe differences, start the test **with no outer transaction**; if the test already has `@Transactional`, every method may see the pre-existing transaction.
5. Use a real database or H2/Testcontainers as appropriate; intentionally throw a `RuntimeException` after writing and read back from a separate transaction/connection to observe rollback.
6. Add dedicated tests for `this.method()`, `private`, and `final`.
7. Check transaction attributes such as `propagation`, `readOnly`, or `timeout` when needed: an active transaction alone does not prove specific settings applied.

**Beware Spring TestContext:** a test method annotated with `@Transactional` normally has a transaction opened and auto-rolled back by TestContext. This can produce **false positives** when testing service boundaries. To evaluate proxy methods independently, use test methods without `@Transactional` or move setup/verification outside the test-managed transaction.

### 11.4. Logging and observation

In dev/test environments, you can enable transaction interceptor logging:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
```

Check logs for which methods receive transaction advice, combined with database assertions. Do not infer correct transactions from a single log line alone, and avoid verbose logging in production when unnecessary.

## 12. Practical Decision Table

| What do you want? | Maintainable approach |
| --- | --- |
| A public service operation always transactional | `@Transactional` on a `public` method, called via Spring bean proxy, manager configured properly. |
| Use protected/package-private with Spring 6.2 | Class-based proxy, external caller has Java access, method is overridable; test rollback on the database. |
| Force JDK interface proxies | Put transactional operations on `public` methods declared on the interface; place annotations on concrete implementations for clarity. |
| Keep public-only behavior when upgrading Spring 5.3 → 6.x | Custom `AnnotationTransactionAttributeSource(true)` and re-test application-wide scope. |
| Internal helper needing its own transaction | Extract helper into a Spring service/bean with a public transactional operation, invoked via proxy. |
| Actually advise self-invocation without changing call style | Evaluate AspectJ weaving, operate/test thoroughly; do not treat it as a zero-cost drop-in. |
| Active transaction exists yet separate rollback behaves wrong | Trace actual caller, proxy type, propagation, exception rules, and transaction manager. |

## 13. Checklist Before Trusting `@Transactional` to Take Effect

- [ ] Confirm the runtime **Spring Framework version**, especially the **5.3 → 6.0+** boundary.
- [ ] Confirm whether **Spring proxy mode** or **AspectJ weaving** is used.
- [ ] Confirm **JDK interface proxy** vs. **class-based proxy**.
- [ ] For JDK proxies, the method is **public** and declared on the proxied interface.
- [ ] For class proxies, public/protected/package-visible methods match the Spring version's scope and are **overridable/interceptable**.
- [ ] Do not use `private`/`final` as a transaction boundary expecting CGLIB interception.
- [ ] Callers invoke through a **Spring-injected proxy**, not `new` or `this`.
- [ ] Java access rules actually allow external callers to invoke the method.
- [ ] Transaction infrastructure/manager is configured, not just the annotation.
- [ ] If using `AnnotationTransactionAttributeSource(true)`, account for **non-public methods being ignored**.
- [ ] Test via **database commit/rollback**, alongside observing active transactions for diagnostics.
- [ ] Tests are not masked by a pre-opened TestContext transaction.
- [ ] When upgrading, audit non-public methods that might **start receiving advice**.

## 14. Review Questions

**Question 1.** Spring 6.2 uses class-based proxies, `@Transactional` is on `protected void reserve()`, and the caller is another bean in the same package calling `proxy.reserve()`. Can the annotation work?

**Answer:** **Yes**, if the bean/proxy/transaction manager are valid and the method is interceptable. That is a major change since Spring 6.0.

**Question 2.** The same method above is called via `this.reserve()` inside the target with no outer transaction. Is there a separate transaction?

**Answer:** **No**, self-invocation bypasses the proxy. Being `protected` and supported in Spring 6.2 does not change the call path.

**Question 3.** Spring 6.2 uses JDK proxies; the implementation adds `public void reindex()` not on the proxied interface. The caller only injects the interface. Can it call `reindex()` and expect advice to run?

**Answer:** **That method cannot be called through the interface proxy**. You must expose an interface API or design for class proxies when needed; do not unwrap the raw target to bypass the proxy.

**Question 4.** `@Transactional` on `private void save()`, Spring 6.2 class proxy. Is there an independent rollback when calling the private method?

**Answer:** **Not a proxy-created transaction boundary**. Private methods cannot be overridden/intercepted by CGLIB; if the method runs inside another outer transaction, it can still participate in that open transaction.

**Question 5.** After upgrading, you want to default to considering only public methods. What do you use?

**Answer:** A `TransactionAttributeSource` bean configured with `new AnnotationTransactionAttributeSource(true)`, and re-test transaction boundaries.

## Official Documentation

1. Spring Framework 6.2 — [Using `@Transactional`: method visibility in proxy mode](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html). Covers the Spring 6.0 change, JDK vs. class proxies, and `publicMethodsOnly`.
2. Spring Framework 5.3 — [Data Access / Transaction Management](https://docs.spring.io/spring-framework/docs/5.3.31/reference/html/data-access.html): describes the `public` policy in the previous generation.
3. Spring Framework 6.2 — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html): limitations of `private`, `final`, package-private methods from superclasses in other packages, and self-invocation.
4. Spring Framework 6.2 — [`@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html).
5. Spring Framework 6.2 — [`AnnotationTransactionAttributeSource` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/AnnotationTransactionAttributeSource.html): the `publicMethodsOnly` parameter.
6. Spring Framework 6.2 — [TestContext Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): test method transactions vs. service transaction boundaries.

**The single most important message:** **Spring 5.3 defaults to public-only; Spring 6.0+ extends protected/package-visible for class-based proxies; JDK proxies remain public on the interface.** Regardless of version, transaction advice only runs if the call actually passes **through a proxy capable of intercepting it**. `private`, `final`, self-invocation, and Java access rules are separate constraints that must be checked.
