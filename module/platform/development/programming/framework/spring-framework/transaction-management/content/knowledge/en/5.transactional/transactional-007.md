# `@Transactional.label` and Transaction-Manager-Dependent Meaning

## 1. Central Question

Spring allows writing:

```java
@Transactional(label = {"operation:checkout", "audit"})
public void checkout() {
    // Perform transactional operations.
}
```

Do those two strings `"operation:checkout"` and `"audit"` force Spring to write an audit log, enable a special commit mode, or choose a different transaction manager?

**There is no such guarantee.** `label` is **transaction-descriptive metadata** that a label-aware transaction manager or extension component may use to apply custom behavior. The exact policy depends on the **implementation**. If the manager does not evaluate those labels, they **do not automatically change** commit, rollback, isolation, timeout, read-only, or propagation.

That is the core point of *"label and manager-dependent meaning"*. A label can:

- Simply describe the transaction's purpose, such as `"operation:checkout"`.
- Represent an option **documented by a specific transaction manager**, such as a policy dedicated to that manager's resource.
- Be read by extension code written by the development team to log, emit metrics, or apply an explicit policy.
- Have no operational effect when the manager ignores or merely accepts the metadata.

Learning goal: read the API accurately, trace the path of a label, distinguish **metadata** from **enforced behavior**, use labels safely, and write tests yourself to verify what the manager actually does.

> Scope of illustration: `org.springframework.transaction.annotation.Transactional` in Spring Framework 6.x (the `label` attribute has existed since Spring 5.3), imperative model with `PlatformTransactionManager` and JDBC. Transaction managers for JPA, JTA, or reactive stacks may process metadata differently. Label names in examples are **illustrative conventions**, not standard options prescribed by Spring.

## 2. What Exactly Does `label` Declare?

In Spring, the attribute has the signature:

```java
String[] label() default {};
```

It is a **`String` array**, empty by default. Writing one element or multiple elements are both valid:

```java
@Transactional(label = "operation:checkout")
public void singleLabel() {
    // ...
}

@Transactional(label = {"operation:checkout", "audit"})
public void multipleLabels() {
    // ...
}
```

The two methods above only illustrate syntax; their bodies are omitted so they are **not standalone programs**. Labels can be placed on a method, class, or meta-annotation containing `@Transactional`. Spring reads the annotation when building transaction information for an intercepted call.

The `@Transactional.label` API documentation explicitly notes two possibilities: labels can be **purely descriptive** or used by a specific manager as **manager-specific options**. There is no global Spring Framework label dictionary guaranteeing that `"retryable"`, `"audit"`, `"read-consistent"`, or `"causal-consistency"` carry the same built-in meaning across all systems.

### 2.1. Distinguishing from Easily Confused Attributes

| Attribute | Purpose | Does Spring/framework have standard semantics? |
| --- | --- | --- |
| `label = {"audit", "checkout"}` | Adds description/options for supporting managers | **No universal semantics** for arbitrary strings |
| `value = "ordersTxManager"` | Selects transaction manager by name/qualifier | Yes: `value` is an alias of `transactionManager` |
| `transactionManager = "ordersTxManager"` | Selects the manager executing the transaction | Yes |
| `propagation = Propagation.REQUIRES_NEW` | Requests an independent transaction per propagation rules | Yes, subject to manager capabilities |
| `isolation = Isolation.SERIALIZABLE` | Requests isolation when creating a new transaction | Yes, depends on database/manager support |
| `timeout = 5` | Requests a 5-second timeout on eligible transactions | Yes, depends on support and check timing |
| `readOnly = true` | Provides a read-only hint/optimization opportunity | Has conventional meaning, but does not guarantee blocking all writes |
| `rollbackFor = IOException.class` | Specifies exceptions triggering rollback | Yes, used by the transaction interceptor |

For instance, the **right** way to select a manager named `ordersTxManager`:

```java
@Transactional(
    transactionManager = "ordersTxManager",
    label = {"operation:checkout", "audit"}
)
public void checkout() {
    // ...
}
```

This annotation selects the manager via `transactionManager`; the two labels are passed only as metadata. If you replace `transactionManager` with `label = "ordersTxManager"`, Spring **does not automatically look up a bean with that name**. Similarly, `label = "timeout:5"` is not equivalent to `timeout = 5`; `label = "rollback-on-checked"` does not replace `rollbackFor`.

### 2.2. Label Is Not the Transaction Name

Spring has a transaction name used in tracking/logging mechanisms, typically derived from the fully qualified class name plus the transactional method name (e.g., `com.example.CheckoutService.checkout` in declarative transactions). `label` is separate metadata, can hold multiple elements, and does not automatically rename this transaction.

You should not assume that:

- Spring automatically prints every label to logs.
- `TransactionSynchronizationManager.getCurrentTransactionName()` returns the label.
- Every label appears in tracing/metrics without additional configuration.

An observability system may actively consume labels, but that is the result of **explicit integration code**, not a default promise of the annotation.

## 3. Metadata Flow: Who Gets the Chance to Read Labels?

A typical call:

```text
Caller
  |
  v
Spring AOP proxy
  |
  v
AnnotationTransactionAttributeSource
  |  Reads @Transactional and creates TransactionAttribute
  |  - propagation, isolation, timeout, readOnly
  |  - rollback rules
  |  - qualifier/transactionManager
  |  - getLabels()
  v
TransactionInterceptor
  |  Selects transaction manager by qualifier (if present)
  |  Calls PlatformTransactionManager.getTransaction(definition)
  v
Specific transaction manager
  |  May inspect label metadata if implementation supports it
  |  Executes begin/join/commit/rollback per manager contract
  v
Database / transaction resource
```

Related APIs:

- `@Transactional.label()` declares the strings.
- `AnnotationTransactionAttributeSource` reads the annotation and supplies a `TransactionAttribute` for the method/class.
- `TransactionAttribute.getLabels()` returns a `Collection<String>` of parsed metadata.
- `DefaultTransactionAttribute.getLabels()` and `setLabels(...)` provide access/mutation for labels on the attribute representation class.
- `PlatformTransactionManager.getTransaction(TransactionDefinition)` receives the transaction definition to decide whether to start or join a transaction. On Spring's declarative path, this parameter can be a `TransactionAttribute`, which extends `TransactionDefinition` and exposes `getLabels()`.

**Subtle point:** `TransactionDefinition` itself does not declare a `getLabels()` method. Manager code wanting to inspect labels on the declarative path needs to read from the appropriate metadata, such as checking `definition instanceof TransactionAttribute`. The same `PlatformTransactionManager` interface can also be called with a plain `DefaultTransactionDefinition`, where no labels exist; the manager must handle that case gracefully.

Example **illustrating only the metadata check**, not a runnable service:

```java
if (definition instanceof TransactionAttribute attribute) {
    Collection<String> labels = attribute.getLabels();
    // Execute documented policy, or merely record labels.
}
```

The word `label` **is not a contract requiring every manager** to act on the passed strings. Some managers ignore labels, some extended managers recognize specific values, and wrapper code around managers can add logic. Therefore never guess meaning from a label's name; read the documentation of **the manager in use** or test it directly.

## 4. Why Does Meaning Depend on the Transaction Manager?

Spring provides a shared abstraction across diverse transaction systems: local JDBC transactions, JPA, JTA, reactive transactions, and custom integrations. These systems have heterogeneous resources, capabilities, begin/end lifecycles, and context models.

Several examples distinguishing **intent** from **guarantees**:

| Self-chosen label | Possible intent | What **must not be assumed by default** |
| --- | --- | --- |
| `"audit"` | Tag transactions needing monitoring | Spring automatically saves an audit record or logs it |
| `"operation:checkout"` | Categorize the business operation | The transaction will be named `checkout` or use a dedicated manager |
| `"retryable"` | Declare intent for an extension | Spring automatically retries on deadlock |
| `"consistency:strong"` | Hint a consistency policy for a custom manager | JDBC/JPA automatically raises isolation |
| `"readonly-report"` | Categorize read workload | Database automatically blocks every `INSERT` |
| `"training:reject"` | Experimental rule we build in Section 7 | Vanilla Spring rejects the transaction upon seeing this string |

The strings in the table are **author-invented examples** for learning the API; do not treat them as built-in options on `DataSourceTransactionManager`, `JdbcTransactionManager`, `JpaTransactionManager`, or another manager.

When changing managers, re-evaluate all three levels:

1. **Syntax:** `@Transactional(label = "...")` remains valid on Spring versions supporting `label`.
2. **Propagation path:** Spring reads and can place labels into `TransactionAttribute`.
3. **Behavior:** Does the chosen manager **actually evaluate** that label, and if so, at begin, join, commit, or which callback?

Levels 1 and 2 do not prove level 3. If a team promises a label enables auditing, that configuration must exist, be documented, and have tests proving it. Any compliance or safety-control rule also needs an actual enforcement point rather than relying solely on an annotation string.

## 5. Usage Patterns in Real Applications

### 5.1. Naming So Readers Understand Intent

Example internal convention:

```java
@Transactional(label = {"operation:invoice", "critical"})
public void issueInvoice() { /* ... */ }
```

At a basic level, labels help readers identify a transaction's purpose. For labels to take effect in observability, a component must read the metadata and emit it into metrics/tracing/logs. Avoid embedding secrets, tokens, customer accounts, or personal data inside static label strings in source code.

A maintainable convention should have an allowed-values list, owner, purpose, applicability conditions, and tests. Do not rename a label consumed by a manager extension without checking dependents.

### 5.2. Using a Composed Annotation for Repeated Conventions

Spring supports meta-annotations:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Transactional(label = {"operation:payment", "audit"})
public @interface PaymentTransaction {
}
```

And usage:

```java
@PaymentTransaction
public void pay() {
    // ...
}
```

This is an **illustrative API pattern**, not a complete project. It standardizes declared metadata; it still does not make a manager implement auditing automatically. If a composed annotation also needs to specify a transaction manager or rollback rules, declare them explicitly, test the actual attributes Spring reads, and avoid assuming labels are automatically "merged" across annotation levels.

### 5.3. Labels on Class and Method

A `@Transactional` on a class provides defaults for eligible methods. Method-level metadata can take precedence over class-level metadata. Example:

```java
@Transactional(label = "module:billing")
public class BillingService {
    public void create() { /* ... */ }

    @Transactional(label = "operation:refund")
    public void refund() { /* ... */ }
}
```

Verify the resolved attribute on `refund` rather than **assuming** the two label sets are combined automatically. In default proxy mode, internal calls like `this.refund()` are not handled by the AOP interceptor as a proxied call; therefore tests should invoke the method from another Spring bean.

## 6. Exercise 1 — Reading the Exact Labels Parsed by Spring

Goal: demonstrate how Spring turns a Java annotation into a `TransactionAttribute`, without needing a database connection.

Suppose we have the class:

```java
package com.example.txlabels;

import org.springframework.transaction.annotation.Transactional;

public class LabelledOperations {
    @Transactional(
        transactionManager = "transactionManager",
        label = {"operation:checkout", "audit"}
    )
    public void checkout() {
    }

    @Transactional
    public void ordinary() {
    }
}
```

We read the metadata with `AnnotationTransactionAttributeSource`. This is a unit test using JUnit 5 and the `spring-tx` dependency (in the full Gradle example in Section 7, the dependency is brought in by the starter):

```java
package com.example.txlabels;

import java.lang.reflect.Method;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.AnnotationTransactionAttributeSource;
import org.springframework.transaction.interceptor.TransactionAttribute;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class LabelsMetadataTest {
    @Test
    void extractsLabelSetAndManagerQualifier() throws Exception {
        Method method = LabelledOperations.class.getMethod("checkout");
        var source = new AnnotationTransactionAttributeSource();
        TransactionAttribute attr = source.getTransactionAttribute(
                method, LabelledOperations.class);

        assertNotNull(attr);
        assertEquals(Set.of("operation:checkout", "audit"),
                Set.copyOf(attr.getLabels()));
        assertEquals("transactionManager", attr.getQualifier());
    }

    @Test
    void absentLabelMeansEmptyCollection() throws Exception {
        Method method = LabelledOperations.class.getMethod("ordinary");
        var source = new AnnotationTransactionAttributeSource();
        TransactionAttribute attr = source.getTransactionAttribute(
                method, LabelledOperations.class);

        assertNotNull(attr);
        assertEquals(Set.of(), Set.copyOf(attr.getLabels()));
    }
}
```

Here `Set.copyOf(...)` compares **the label set** without depending on `Collection` iteration order. These two tests only prove metadata parsing. They **do not** prove the database opened a transaction or that a manager consumed those labels. To observe behavior, combine calls through a proxy with a real transaction manager.

## 7. Exercise 2 — A Manager With and Without a Label Policy

A minimal project using **Spring Boot 3.3.5 + Java 17 + Spring JDBC + H2**. We write a wrapper `LabelAwareTransactionManager` around `JdbcTransactionManager` with two responsibilities **defined by us**:

1. Record the labels Spring passes into `getTransaction`.
2. Reject the label `"training:reject"` **purely as an experiment**.

Those responsibilities **are not default behavior of `JdbcTransactionManager`**. The wrapper delegates all remaining operations to the real JDBC manager.

### 7.1. Project Structure

```text
tx-labels/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/txlabels/
    │   │   ├── TxLabelsApplication.java
    │   │   ├── TransactionConfig.java
    │   │   ├── LabelAwareTransactionManager.java
    │   │   ├── LabelledOperations.java
    │   │   └── CheckoutService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/java/com/example/txlabels/
        ├── LabelsMetadataTest.java
        └── LabelsIntegrationTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'tx-labels'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`src/main/resources/application.properties`:

```properties
spring.datasource.url=jdbc:h2:mem:txlabels;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    code VARCHAR(80) NOT NULL UNIQUE
);
```

This is an in-memory test database. Gradle manages the entire Spring, JDBC, H2, and JUnit classpath; do not run bare `javac` without these dependencies.

### 7.2. Entry Point and Manager Configuration

`src/main/java/com/example/txlabels/TxLabelsApplication.java`:

```java
package com.example.txlabels;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxLabelsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxLabelsApplication.class, args);
    }
}
```

`src/main/java/com/example/txlabels/TransactionConfig.java`:

```java
package com.example.txlabels;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionConfig {
    @Bean("transactionManager")
    public LabelAwareTransactionManager transactionManager(DataSource dataSource) {
        return new LabelAwareTransactionManager(
                new JdbcTransactionManager(dataSource));
    }
}
```

The `transactionManager` bean is the wrapper, while `JdbcTransactionManager` handles the real JDBC begin/commit/rollback. `@EnableTransactionManagement` enables proxy infrastructure so the demo does not depend on whether the reader knows what Spring Boot auto-configures.

### 7.3. Wrapper Intentionally Reading Labels

`src/main/java/com/example/txlabels/LabelAwareTransactionManager.java`:

```java
package com.example.txlabels;

import java.util.List;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.interceptor.TransactionAttribute;

public final class LabelAwareTransactionManager
        implements PlatformTransactionManager {

    private final PlatformTransactionManager delegate;
    private final List<Set<String>> observed = new CopyOnWriteArrayList<>();

    public LabelAwareTransactionManager(PlatformTransactionManager delegate) {
        this.delegate = delegate;
    }

    @Override
    public TransactionStatus getTransaction(TransactionDefinition definition)
            throws TransactionException {
        Set<String> labels =
                definition instanceof TransactionAttribute attribute
                        ? Set.copyOf(attribute.getLabels())
                        : Set.of();

        observed.add(labels);

        // CUSTOM policy to demonstrate manager-dependent behavior.
        // Standard Spring does not understand "training:reject".
        if (labels.contains("training:reject")) {
            throw new IllegalTransactionStateException(
                    "Rejected by the demo label policy");
        }

        return delegate.getTransaction(definition);
    }

    @Override
    public void commit(TransactionStatus status) throws TransactionException {
        delegate.commit(status);
    }

    @Override
    public void rollback(TransactionStatus status) throws TransactionException {
        delegate.rollback(status);
    }

    public List<Set<String>> observedLabels() {
        return List.copyOf(observed);
    }

    public void clearObservedLabels() {
        observed.clear();
    }
}
```

**Analysis:** `getTransaction` receives the definition sent by Spring's interceptor. For calls through `@Transactional`, the definition is a `TransactionAttribute` (or its wrapper) and exposes `getLabels()`. When called via `TransactionTemplate`/manual APIs with a regular `TransactionDefinition`, label metadata may be absent, so the code handles an empty set. Only the `training:reject` condition alters behavior: the wrapper throws an error **before the delegate begins the transaction**.

Limitations to understand:

- `observed` is a list for testing, **not a production logging/metrics mechanism**. In high-traffic applications, design bounded, thread-safe metrics collection and keep sensitive data out of labels.
- The wrapper records when `getTransaction` is called, **which does not prove every call creates a new physical transaction**. With `Propagation.REQUIRED`, a scope can join an existing transaction.
- Throwing an exception as a custom policy is an *experimental* design; a production manager needs a clear policy contract, validation, error handling, and propagation tests.
- The wrapper adds no special JDBC capability. It forwards commit/rollback; DB outcomes still follow the delegate.

### 7.4. Service Using Different Kinds of Labels

`src/main/java/com/example/txlabels/CheckoutService.java`:

```java
package com.example.txlabels;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {
    private final JdbcTemplate jdbc;

    public CheckoutService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        transactionManager = "transactionManager",
        label = {"operation:checkout", "audit"}
    )
    public void checkout(String code) {
        insert(code);
    }

    @Transactional(label = "training:reject")
    public void rejected(String code) {
        insert(code); // Body will not run due to wrapper's policy.
    }

    @Transactional(label = "training:ignored")
    public void failsWithRuntimeException(String code) {
        insert(code);
        throw new IllegalStateException("Simulated failure");
    }

    @Transactional
    public void ordinary(String code) {
        insert(code);
    }

    private void insert(String code) {
        jdbc.update("INSERT INTO tx_events (code) VALUES (?)", code);
    }
}
```

`"operation:checkout"` and `"audit"` are recorded by the wrapper, yet **the wrapper has no special handling branch for them**. `"training:ignored"` is also merely recorded: the method still rolls back when `IllegalStateException` escapes because of `@Transactional`'s standard rollback rules, not because of the label. `"training:reject"` is **only** rejected because of the `if (labels.contains(...))` line in this lesson's wrapper.

### 7.5. Integration Test Comparing Metadata with DB Behavior

`src/test/java/com/example/txlabels/LabelsIntegrationTest.java`:

```java
package com.example.txlabels;

import java.util.List;
import java.util.Set;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.IllegalTransactionStateException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class LabelsIntegrationTest {
    @Autowired
    private CheckoutService checkoutService;

    @Autowired
    private LabelAwareTransactionManager manager;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
        manager.clearObservedLabels();
    }

    private long rows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_events", Long.class);
    }

    @Test
    void multipleLabelsAreVisibleButNormalCommitStillWorks() {
        checkoutService.checkout("checkout-A");

        assertEquals(1L, rows());
        assertEquals(
                List.of(Set.of("operation:checkout", "audit")),
                manager.observedLabels());
    }

    @Test
    void customPolicyRejectsBeforeServiceBody() {
        assertThrows(IllegalTransactionStateException.class,
                () -> checkoutService.rejected("reject-B"));

        assertEquals(0L, rows());
        assertEquals(
                List.of(Set.of("training:reject")),
                manager.observedLabels());
    }

    @Test
    void arbitraryLabelDoesNotChangeRollbackRule() {
        assertThrows(IllegalStateException.class,
                () -> checkoutService.failsWithRuntimeException("fail-C"));

        assertEquals(0L, rows());
        assertEquals(
                List.of(Set.of("training:ignored")),
                manager.observedLabels());
    }

    @Test
    void noLabelIsAValidEmptySet() {
        checkoutService.ordinary("plain-D");

        assertEquals(1L, rows());
        assertEquals(
                List.of(Set.of()),
                manager.observedLabels());
    }
}
```

Do not put `@Transactional` on the test class. If the test opens its own transaction and rolls back afterward, `rows()` might only reflect uncommitted data and fail to prove the service boundary. Here, Spring calls the service bean through its proxy and completes the transaction; the test reads data afterward with `JdbcTemplate`.

### 7.6. Combining the Metadata Tests from Section 6

Save `LabelledOperations.java` and `LabelsMetadataTest.java` from Section 6 at their corresponding paths in the directory tree. Together the project has **6 tests**: 2 annotation-reading tests and 4 integration tests through the service/manager.

Run in the project directory using the Gradle Wrapper (if generated from Spring Initializr) with JDK 17+:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

If creating the project manually without a Gradle Wrapper, generate one with an installed Gradle or run `gradle test` using a Gradle version compatible with Spring Boot 3.3.5. Gradle will compile Java and run JUnit. **Expected result:** 6 tests pass; there is no fixed Java stdout from the tests. Inspect `build/reports/tests/test/index.html` for actual results.

| Case | Labels received by manager | Data change | Meaning |
| --- | --- | --- | --- |
| Checkout succeeds | `operation:checkout` and `audit` | 1 row committed | Labels are passed but do not automatically cause auditing |
| Reject | `training:reject` | 0 rows | **Custom wrapper** rejects before running service body |
| Runtime exception | `training:ignored` | 0 rows | Rollback due to default exception rule |
| No label | Empty set | 1 row committed | Annotation does not require labels to create a transaction |

The example results are **expected outcomes of the provided code**, not a claim that tests were executed on the reader's machine. Do not assume exact log output, since logs depend on configuration and framework versions.

## 8. Important Notes for Nested Calls or Multiple Transaction Managers

### 8.1. A Label on Nested `REQUIRED` Does Not Mean Opening a New Transaction

Consider two beans:

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(label = "scope:outer")
    public void process() {
        inner.step();
    }
}

@Service
class InnerService {
    @Transactional(label = "scope:inner")
    public void step() {
        // ...
    }
}
```

This is **illustrative code**, requiring `@Service` and `@Transactional` imports in a real project. Default `REQUIRED` can cause `inner` to join **the same physical transaction** created by `outer`. A wrapper like the example may record both label sets when `getTransaction` is called; that **does not mean two independent transactions were started** or that a start-only policy ran again for the physical transaction.

Therefore you must clarify whether a label policy takes effect:

- When receiving a **logical transaction scope**.
- When starting a **new physical transaction**.
- At commit/rollback or in a specific callback.
- Or only when emitting metadata/telemetry.

If that distinction matters, test two beans calling through proxies with `REQUIRED`, `REQUIRES_NEW`, and rollback scenarios. Never infer a label's meaning solely from the scope carrying an annotation.

### 8.2. Labels Are Not Used to Select the Manager

When an application has both `ordersTxManager` and `reportingTxManager`, Spring selects the manager via qualifiers, default configuration, and `transactionManager`/`value`, **not based on labels unless explicit custom infrastructure is written**.

```java
@Transactional(
    transactionManager = "reportingTxManager",
    label = "operation:report"
)
public void generateReport() {
    // ...
}
```

Here the manager is already selected via `transactionManager`; `operation:report` is metadata the selected manager *may* inspect further. Never use labels to implicitly route data to a different database.

### 8.3. Reactive Transactions Have a Different Context

The imperative model typically binds transaction state to a thread; reactive transactions manage state through the Reactor context. A label can be present in metadata passed to `ReactiveTransactionManager`, but that does not make it available as a thread-local label or give it JDBC semantics. When writing label-reading code, be explicit about whether you are integrating with an **imperative** or **reactive** manager and its actual transaction path.

## 9. How to Design Meaningful Labels on an Engineering Team

Use a minimal contract before a team decides that a label triggers behavior:

| Question | Example verifiable answer |
| --- | --- |
| Which label names are accepted? | `"operation:checkout"`; `"policy:strict"`, documented |
| Who reads the label? | A custom `PlatformTransactionManager` or an explicitly registered integration |
| Where does the label take effect? | Before `getTransaction`, on starting a physical transaction, or only when recording metrics |
| What if no label is present? | Keep the transaction manager's defaults |
| What if an unknown label appears? | Ignore or fail fast per published contract |
| If multiple labels exist, how is precedence decided? | A deterministic rule with conflict tests |
| What about nested `REQUIRED`? | Define whether it applies per logical scope or per physical transaction |
| What if switching managers? | Have integration tests proving behavior mapping is preserved |
| How are failures surfaced if a policy is not applied? | Boundary tests + appropriate metrics/alerts |

For security, compliance, anti-fraud, or critical data policies, never treat an **unconsumed** label as a technical guardrail. If a project switches from a custom manager to a standard manager without porting the consumer, the code still compiles while the extended semantics silently vanish.

## 10. Common Reasoning Mistakes

1. **Confusing `label` with `transactionManager`/`value`.** Labels do not select a transaction manager bean by default.
2. **Writing `label = "retryable"` and expecting auto-retry.** Retries need their own mechanism and policy, considering idempotency.
3. **Writing `label = "audit"` and treating it as an audit trail.** Metadata does not replace actual audit records, logs, or emitted events.
4. **Using `label` instead of `rollbackFor`.** Rollback rules are still governed by transaction infrastructure and rollback rule configuration.
5. **Using `label` instead of `isolation`, `readOnly`, or `timeout`.** Those attributes have their own APIs, subject to manager/database support.
6. **Reading `@Transactional` with reflection on a method and assuming the proxy ran.** Metadata presence does not prove runtime interception.
7. **Forgetting self-invocation.** Calls like `this.methodWithLabel()` in standard proxy mode do not trigger the called method's interceptor.
8. **Assuming `getLabels()` has a guaranteed order.** The intent is typically a set of labels; test the set of values rather than depending on an unpromised order.
9. **Assuming method labels automatically merge with class labels.** Verify actual resolution; do not assume automatic merging.
10. **Seeing a wrapper log two labels and assuming two physical transactions.** `REQUIRED` can join an outer transaction.
11. **Relying heavily on a specific manager without tests.** When switching technologies, manager-specific options may stop having any effect.
12. **Testing behavior only with annotation-reading unit tests.** Integration tests calling through proxies and measuring data/manager observations are needed.

## 11. Verification Workflow for a Label in a Real Project

Follow these steps before claiming a label "has an effect":

1. **Identify the exact annotation:** verify `org.springframework.transaction.annotation.Transactional` import, Spring version supporting `label`, and which method/class declares it.
2. **Check metadata:** `AnnotationTransactionAttributeSource.getTransactionAttribute(method, clazz)` then `getLabels()`, verifying the expected label set.
3. **Check calls through the proxy:** service is Spring-managed, caller invokes from another bean, and AOP transaction advice actually runs.
4. **Identify the selected manager:** check `transactionManager`, qualifiers, and default transaction manager; do not infer from labels.
5. **Read the manager's implementation or documentation:** does it evaluate labels, is there an allowlist, and at which stage does behavior apply?
6. **Write control tests:** same business logic with/without the label; measure at least one concrete effect produced by the consumer. For example, this lesson checks `observedLabels` and manager rejection of `training:reject`.
7. **Inspect data after the transaction boundary:** do not let `@Transactional` on the test itself mask real commit/rollback.
8. **Check nested/proxy/propagation behavior:** new scope vs. joining an existing transaction, and whether each scope's labels are observed per contract.
9. **Check when changing managers:** re-run label and extended-semantics tests; update documentation for API users.

### Self-Check Questions

**1.** Is `@Transactional(label = "timeout:10")` guaranteed to time out a transaction after 10 seconds?  
**No.** Use the `timeout = 10` attribute per Spring's contract, and verify manager support. A label string only means something if a manager/integration defines it.

**2.** Which manager does `@Transactional(value = "ordersTxManager", label = "audit")` select?  
Spring uses `value` (alias of `transactionManager`) to locate `ordersTxManager`; the `audit` label is metadata passed to the selected manager.

**3.** Does calling `getLabels()` in a unit test alone prove auditing ran?  
**No.** It proves Spring parsed the annotation. Proving auditing ran requires observing the output of the actual consumer.

**4.** Why is inner `@Transactional(label="inner")` not guaranteed to start a new transaction?  
Because default `PROPAGATION_REQUIRED` can join the outer physical transaction. Labels do not alter propagation.

**5.** If you switch from `JdbcTransactionManager` to another manager and all business tests still pass, can you claim extended label behavior still works?  
**No.** You need dedicated tests for the label consumer and manager-dependent effects; ordinary commit/rollback tests do not prove custom options are still applied.

## Official References

- [Spring Framework — `@Transactional` settings and the `label` attribute](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — `@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework 6.2 — `TransactionAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/TransactionAttribute.html)
- [Spring Framework 6.2 — `AnnotationTransactionAttributeSource` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/AnnotationTransactionAttributeSource.html)
- [Spring Framework — Transaction Propagation (`REQUIRED` and `REQUIRES_NEW`)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
