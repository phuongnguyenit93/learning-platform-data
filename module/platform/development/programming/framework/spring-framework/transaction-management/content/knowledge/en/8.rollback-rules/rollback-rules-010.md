# ALL_EXCEPTIONS and Global Default Changes Since Spring Framework 6.2

## 1. What Actually Changed in Spring Framework 6.2

Starting in **Spring Framework 6.2**, an application can configure **rollback by default for all exceptions**, including checked exceptions, at the annotation-driven transaction management infrastructure level:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.RollbackOn;

@Configuration
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
public class TransactionConfiguration {
}
```

The point to emphasize: this is an **opt-in configuration option to change the global default for transaction annotations**, **not** an automatic behavior change applied to every application upon upgrading to Spring 6.2. If `rollbackOn` (or an equivalent configuration) is not specified, the default **remains `RollbackOn.RUNTIME_EXCEPTIONS`**: roll back when `RuntimeException` or `Error` exits through the transaction interceptor, while checked `Exception`s generally lead to commit unless there is a specific rollback rule or another rollback-only state.

This topic belongs to **Rollback Rules**. What you need to learn is not just the `ALL_EXCEPTIONS` syntax, but also:

1. How the legacy mechanism and the new mechanism differ when a method throws a checked exception.
2. Where and within what scope `@EnableTransactionManagement(rollbackOn = ...)` changes the **default rule**.
3. Whether a method's `rollbackFor` and `noRollbackFor` rules take precedence over the global default.
4. What does **not** change: propagation, commit failures, already rollback-only transactions, exceptions caught inside the method, and programmatic transaction APIs.
5. How to verify outcomes with real data after the proxy call completes.
6. How to assess the impact when migrating an application that uses checked exceptions as business signals.

The hands-on example below uses **Java 17+, Spring Framework 6.2.6, Spring JDBC, H2, JUnit 5, and Gradle**. Version 6.2.6 is pinned so the code and APIs can be verified consistently; it is an illustrative version, not a statement about the latest Spring release.

## 2. Recap: Checked and Unchecked Exceptions

Java classifies errors relevant to rollback rules as follows:

```text
java.lang.Throwable
  |
  +-- Error                         -> not an Exception
  |
  +-- Exception
        |
        +-- RuntimeException        -> unchecked
        |     +-- IllegalArgumentException
        |     +-- IllegalStateException
        |     +-- ...
        |
        +-- IOException             -> checked
        +-- SQLException            -> checked
        +-- BusinessNotice          -> custom checked
```

**Checked exceptions** are typically classes extending `Exception` without extending `RuntimeException`; Java forces methods to declare `throws` or catch them. **Unchecked exceptions** include `RuntimeException` and `Error`; no `throws` declaration is required. Kotlin does not enforce checked-exception declarations the way Java does, so a uniform rollback rule for both groups can be especially useful in Kotlin applications.

### 2.1. Spring's Traditional Mechanism

Example:

```java
@Transactional
public void saveThenThrow() throws IOException {
    jdbc.update("INSERT INTO audit_event(code) VALUES (?)", "T1");
    throw new IOException("I/O failed");
}
```

This is an illustrative snippet in a service with `JdbcTemplate jdbc`; running it requires a Spring-managed bean, a transaction manager, and a real table schema. In the default **`RUNTIME_EXCEPTIONS`** mode, `IOException` does not match an automatic rollback rule: Spring may **commit the INSERT and still propagate IOException to the caller**. The caller seeing an exception **does not mean** data changes were rolled back.

If replaced with an `IllegalStateException` escaping through the transaction interceptor, Spring requests rollback by default. If an `IOException` is caught **inside the method itself** and the method returns normally, the interceptor never sees that exception, so switching globally to `ALL_EXCEPTIONS` will not automatically roll back the transaction either (unless another component marks rollback-only).

### 2.2. Decision Table Before and After Enabling ALL_EXCEPTIONS

Assuming a **new transaction**, no prior rollback-only flag, uncommitted writes, and a manager able to complete normally:

| Scenario | `RUNTIME_EXCEPTIONS` (default) | `ALL_EXCEPTIONS` (explicitly enabled) |
| --- | --- | --- |
| Method returns normally | Commit | Commit |
| `IllegalStateException` escapes proxy | Rollback | Rollback |
| `IOException` escapes proxy, no custom rule | **Commit** | **Rollback** |
| `SQLException` escapes proxy, no custom rule | **Commit** | **Rollback** |
| `Error` escapes proxy | Rollback | Rollback |
| `@Transactional(rollbackFor = IOException.class)` throws `IOException` | Rollback | Rollback |
| `@Transactional(noRollbackFor = IOException.class)` throws `IOException` | Commit | Commit — method rule beats default |
| `@Transactional(noRollbackFor = BusinessNotice.class)` throws `IOException` | Commit (legacy default) | **Rollback** (new default still applies to unmatched errors) |
| Checked exception caught inside and method returns | Usually commits | Usually commits |
| Inner `REQUIRED` set rollback-only, outer catches and returns | Rolls back per status | Rolls back per status |

The “commit” column is the **rollback-rule decision**, not a guarantee that the database commit always succeeds: `commit()` can still fail, or the transaction may already be marked rollback-only for another reason.

## 3. New API: `RollbackOn` and `@EnableTransactionManagement.rollbackOn`

Spring Framework 6.2 introduces the enum:

```java
package org.springframework.transaction.annotation;

public enum RollbackOn {
    RUNTIME_EXCEPTIONS,
    ALL_EXCEPTIONS
}
```

This snippet **only illustrates the shape of the enum for learning**; do not create this enum file in your application. In real code, import the enum from Spring.

| Value | Role |
| --- | --- |
| `RollbackOn.RUNTIME_EXCEPTIONS` | Traditional default: runtime exceptions and `Error`s trigger rollback |
| `RollbackOn.ALL_EXCEPTIONS` | Opt-in mode: checked `Exception`s also trigger rollback under the default rule |

Syntax to enable:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.RollbackOn;

@Configuration
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
class GlobalRollbackConfiguration {
}
```

Syntax to keep the legacy mode explicitly:

```java
@EnableTransactionManagement(
    rollbackOn = RollbackOn.RUNTIME_EXCEPTIONS
)
class TraditionalRollbackConfiguration {
}
```

These two snippets are **separate configuration examples**; do not register both in the same application context expecting each annotation to govern a subset of services. The default mode is a choice of the **annotation-driven transaction management infrastructure in the context**, not a per-call value selected by an annotation on a single service.

### 3.1. Does Upgrading Versions Automatically Enable ALL_EXCEPTIONS?

**No.** Distinguish two separate events:

- **Upgrading from Spring Framework 6.1 to 6.2:** your application gains the `RollbackOn` API, `@EnableTransactionManagement.rollbackOn`, and `AnnotationTransactionAttributeSource.addDefaultRollbackRule(...)`.
- **Enabling `rollbackOn = RollbackOn.ALL_EXCEPTIONS`:** you actively change the fallback rollback rule for transaction annotations. Only this action changes how checked exceptions without explicit rules are handled.

If you have not changed the configuration, a checked `IOException` in `@Transactional` can still result in commit as before. Write regression tests to detect configuration-driven changes rather than concluding “Spring 6.2 rolls back all checked exceptions.”

### 3.2. Spring Boot Versions to Check

Spring Boot **3.3.x** builds on Spring Framework **6.1.x**, so the `RollbackOn` code above will not compile against a 3.3.x dependency set. Spring Boot **3.4.x** builds on Spring Framework **6.2.x** (for example, Boot 3.4.5 manages Spring 6.2.6). When working in a Boot project, inspect the **actual** dependency tree rather than relying solely on the Java version or plugin name.

A concise configuration in a Boot project can look like:

```java
@SpringBootApplication
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

This snippet illustrates configuration placement; it requires imports for `SpringBootApplication`, `SpringApplication`, and transaction annotations, plus an appropriate transaction manager and data-access setup. The complete lab later uses **Spring Framework directly** to compare the two modes separately without auto-configuration obscuring the mechanism being studied.

## 4. Where Does Spring Apply the New Default Rule?

Typical declarative transaction flow:

```text
External caller
  -> Spring AOP proxy
       -> TransactionInterceptor
          -> AnnotationTransactionAttributeSource
             - reads Spring @Transactional / JTA @Transactional
             - creates RuleBasedTransactionAttribute
             - adds default rollback rule if configured
          -> PlatformTransactionManager.getTransaction(...)
          -> invokes target method
          -> if an exception escapes:
               TransactionAttribute.rollbackOn(exception)
               -> selects commit / rollback for the scope
          -> manager.commit(status) or rollback(status)
  -> caller receives result/exception
```

At the API level, `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)` supplies a default rule for **rule-based transaction attributes** created by Spring's annotation infrastructure. In Spring Framework 6.2, `AnnotationTransactionAttributeSource` supports:

```java
AnnotationTransactionAttributeSource source =
        new AnnotationTransactionAttributeSource();

source.addDefaultRollbackRule(
        RollbackRuleAttribute.ROLLBACK_ON_ALL_EXCEPTIONS);
```

This snippet **only illustrates configuring a metadata source instance** and requires importing `AnnotationTransactionAttributeSource` and `RollbackRuleAttribute`. Creating a standalone `source` variable in application code **does not automatically replace** the source used by the proxy transaction infrastructure. To alter runtime behavior, configure the actual infrastructure bean, or simply use `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`.

### 4.1. Why Does `addDefaultRollbackRule` Exist?

This API lets you add a **fallback rule** for exceptions where a method lacks a specific rule. It is especially helpful when an application wants a default rollback convention across Spring-parsed attributes while still honoring explicitly declared business exceptions.

You no longer need to repeat `rollbackFor = Exception.class` on every service. Nevertheless, **a global fallback does not erase local rules**. An explicit `noRollbackFor` on a method can still permit commit for a specified exception type.

### 4.2. Scope of the Change Is Not “JVM-Wide”

The word **global** here must be understood precisely: the scope of the **configured annotation-driven transaction management infrastructure** (typically one Spring `ApplicationContext`). Do not infer that:

- Every other application in the same JVM or other microservices change their defaults.
- Every manual `PlatformTransactionManager` API call enforces this default.
- `TransactionTemplate` gets its rollback rules reconfigured by this annotation.
- Transactions created by a database/JTA container outside Spring change behavior.
- Transactions on another thread/`@Async` automatically join the open transaction.
- Commit/rollback behavior of non-managed resources (email, HTTP, message brokers) is automatically adjusted.

This mode affects `org.springframework.transaction.annotation.Transactional` and, when parsed by Spring's transaction infrastructure, `jakarta.transaction.Transactional` as well. That does **not** mean it reconfigures a standalone EJB/JTA transaction container outside Spring. `TransactionAttribute`s not based on rollback rules are not automatically mutated as if “inserting a default rule into every object.”

## 5. Precedence: Local Rules Are Stronger Than the Fallback

On Spring's `@Transactional`, the relevant attributes are:

- `rollbackFor`: which exception classes require rollback.
- `rollbackForClassName`: exception name patterns requiring rollback.
- `noRollbackFor`: which exception classes request **no** rollback.
- `noRollbackForClassName`: exception name patterns requesting **no** rollback.

Example:

```java
@Transactional(noRollbackFor = IOException.class)
public void saveEvenIfIoFails() throws IOException {
    // ...
}
```

With `ALL_EXCEPTIONS`, an `IOException` exiting this method matches `noRollbackFor = IOException.class`, which is **more specific** than the fallback specifying rollback for `Exception`, so Spring chooses **commit** if the transaction is not rollback-only and the manager's commit succeeds.

Meanwhile:

```java
@Transactional(noRollbackFor = BusinessNotice.class)
public void saveThenThrowDifferentChecked() throws IOException {
    // ...
}
```

If the method throws `IOException`, the rule `noRollbackFor = BusinessNotice.class` **does not match** this exception. Hence the `ALL_EXCEPTIONS` fallback still runs → **rollback**.

### 5.1. “Strongest Matching Rule Wins”

Spring matches rules against the exception class and its superclasses. A rule matching a specific type directly is generally stronger than a rule matching via a more distant superclass. Example:

```java
@Transactional(
    noRollbackFor = IOException.class,
    rollbackFor = java.io.FileNotFoundException.class
)
public void openFile() throws IOException {
    // ...
}
```

- If `FileNotFoundException` occurs: the rollback rule for this exact class beats the no-rollback rule for `IOException` → **rollback**.
- If `EOFException` occurs: the no-rollback rule for `IOException` matches via superclass → **commit** per rule, barring rollback-only or other failures.
- If `SQLException` occurs: no local rule matches, so the default applies: **rollback** under `ALL_EXCEPTIONS`; **commit** under `RUNTIME_EXCEPTIONS`.

This snippet only illustrates rule behavior; it is not a standalone runnable method. Do not put two **contradictory rules of equal specificity** for one exception and expect a readable policy; declare an unambiguous rule and test it.

### 5.2. Why Prefer Types Over Patterns?

`rollbackForClassName` and `noRollbackForClassName` use **substring matching** on exception names, not full glob/regex syntax. A short pattern like `"Exception"` easily matches unintended types; even class names sharing a prefix can be affected. Use `rollbackFor = MyException.class` / `noRollbackFor = MyException.class` whenever possible so rules stay type-safe without accidentally widening scope.

### 5.3. Global ALL_EXCEPTIONS Does Not Override Rollback-Only State

If an inner transactional scope joins a physical transaction under `REQUIRED` and marks rollback-only, the outer method might catch the exception and return normally. When outer tries to commit, the manager still cannot commit the physical transaction. `noRollbackFor` at one boundary is not a “clear rollback-only” command for a flag set by another boundary. This situation can lead to `UnexpectedRollbackException` on outer commit.

## 6. Why Did Spring Introduce ALL_EXCEPTIONS Mode?

In many modern applications, checked exceptions are no longer used consistently as a signal for “business exception where commit is acceptable.” A repository might throw a checked I/O exception; a service might sometimes declare `throws Exception`; Kotlin does not enforce checked exceptions. If a developer forgets `rollbackFor`, an operation that already wrote data can **commit even though the caller received an error**.

`ALL_EXCEPTIONS` lets you establish a uniform baseline: **any exception thrown out of a transactional method requests rollback, unless the method declares otherwise**. Accordingly, Spring 6.2 recommends considering this mode if your application does not rely on EJB-style business exceptions carrying commit semantics.

Still, enabling it globally is a **business contract change**, not mere code cleanup. Suppose a service accepts a request, saves a record, and throws checked `DocumentPendingReviewException` so the caller knows approval is still needed. Previously it could commit the record; under `ALL_EXCEPTIONS`, the exact same code will roll back unless adjusted. You must verify whether that was an intended design to preserve or a bug to fix.

### 6.1. Three Method Groups to Audit During Migration

| Group | State before the change | Action when enabling ALL_EXCEPTIONS |
| --- | --- | --- |
| Checked exception signals **failure, data must be discarded** | Easy to commit accidentally if `rollbackFor` was omitted | New default improves consistency; add rollback tests |
| Checked exception signals **business outcome that intentionally keeps data** | May intentionally commit and then throw exception | Consider changing the outcome to a return value or declaring explicit `noRollbackFor`; add commit tests |
| Method already has detailed `rollbackFor`/`noRollbackFor` | Explicit rules already govern specific exception types | Keep rules; audit **exception types not covered by those rules**, as they now hit the new fallback |

Inspect actual proxy call paths, where exceptions are caught, propagation, and transaction managers. Methods without transaction advice, or calling each other via `this` in proxy mode, will not be magically fixed by the new default.

## 7. Hands-On Side-by-Side Comparison of Both Modes on Spring Framework 6.2

Instead of two separate Spring Boot apps, we use **two independent Spring test application contexts** sharing the exact same service:

- The first context uses default `@EnableTransactionManagement` (i.e., `RUNTIME_EXCEPTIONS`).
- The second context enables `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`.

Each context has its own uniquely named H2 database to prevent interference. We observe row counts after the service is called through a Spring proxy and the exception reaches the test. This is **integration testing** with real H2 database transactions; no web server or Spring Boot is needed.

### 7.1. File Structure

```text
rollback-defaults/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/com/example/rollback/
    │   │   ├── BusinessNotice.java
    │   │   ├── RollbackScenarios.java
    │   │   ├── DatabaseBeans.java
    │   │   ├── TraditionalMode.java
    │   │   └── AllExceptionsMode.java
    │   └── resources/
    │       └── schema.sql
    └── test/
        └── java/com/example/rollback/
            ├── TraditionalModeTest.java
            └── AllExceptionsModeTest.java
```

Requirements: **Java 17+**, compatible Gradle 8.x, and Maven Central access for first-run dependencies. All Java files share package `com.example.rollback`. Do not add extra `@EnableTransactionManagement` annotations across the two test contexts.

`settings.gradle`:

```groovy
rootProject.name = 'rollback-defaults'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.6'
    implementation 'org.springframework:spring-jdbc:6.2.6'
    implementation 'org.springframework:spring-tx:6.2.6'

    runtimeOnly 'com.h2database:h2:2.3.232'
    testImplementation 'org.springframework:spring-test:6.2.6'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-context`, `spring-jdbc`, `spring-tx`, and `spring-test` are all pinned to **6.2.6** so the `RollbackOn` API is consistent. H2 is a runtime dependency because `EmbeddedDatabaseBuilder` loads the H2 driver at context initialization. `spring-context`/`spring-tx` provide AOP/annotation transaction infrastructure, and `spring-test` provides `@SpringJUnitConfig`.

### 7.2. H2 Schema

`src/main/resources/schema.sql`:

```sql
CREATE TABLE tx_receipts (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    business_key VARCHAR(80) NOT NULL UNIQUE
);
```

The `UNIQUE` constraint enforces a distinct business key per test. H2 only serves as a testbed for Spring rules; production database isolation/locking/DDL behavior may still need testing against the real engine.

### 7.3. A Business Checked Exception

`src/main/java/com/example/rollback/BusinessNotice.java`:

```java
package com.example.rollback;

public class BusinessNotice extends Exception {
    public BusinessNotice(String message) {
        super(message);
    }
}
```

This class extends `Exception`, **not `RuntimeException`**, making it a checked exception. Any method throwing it must declare `throws BusinessNotice` or catch it. In real systems, design this kind of exception only when throwing it truly fits the API contract.

### 7.4. Service with Verification Branches

`src/main/java/com/example/rollback/RollbackScenarios.java`:

```java
package com.example.rollback;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;

public class RollbackScenarios {
    private final JdbcTemplate jdbc;

    public RollbackScenarios(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void success(String businessKey) {
        insert(businessKey);
    }

    @Transactional
    public void checkedIOException(String businessKey) throws IOException {
        insert(businessKey);
        throw new IOException("simulated checked failure");
    }

    @Transactional
    public void runtimeFailure(String businessKey) {
        insert(businessKey);
        throw new IllegalStateException("simulated runtime failure");
    }

    @Transactional(rollbackFor = IOException.class)
    public void checkedWithExplicitRollback(String businessKey) throws IOException {
        insert(businessKey);
        throw new IOException("explicit rollback rule");
    }

    @Transactional(noRollbackFor = IOException.class)
    public void checkedWithExplicitNoRollback(String businessKey) throws IOException {
        insert(businessKey);
        throw new IOException("explicit no-rollback rule");
    }

    @Transactional(noRollbackFor = BusinessNotice.class)
    public void acceptedBusinessNotice(String businessKey) throws BusinessNotice {
        insert(businessKey);
        throw new BusinessNotice("saved, but needs review");
    }

    @Transactional(noRollbackFor = BusinessNotice.class)
    public void unrelatedCheckedIOException(String businessKey) throws IOException {
        insert(businessKey);
        throw new IOException("unrelated to BusinessNotice");
    }

    @Transactional
    public void caughtCheckedInside(String businessKey) {
        insert(businessKey);
        try {
            throw new IOException("handled internally");
        } catch (IOException ignored) {
            // To illustrate the mechanism: the interceptor will see a normal return.
            // Production code should not swallow an important business error like this.
        }
    }

    private void insert(String businessKey) {
        jdbc.update(
                "INSERT INTO tx_receipts(business_key) VALUES (?)",
                businessKey);
    }
}
```

Public methods are invoked through a **Spring-managed proxy** in tests. `insert` is a private helper; it needs no separate `@Transactional` because every public method has already started or joined a transaction before calling the helper.

These eight branches intentionally keep SQL logic identical. They differ only in **escaping exception**, **local rollback rule**, and **global default**, making Spring's decisions easy to observe.

### 7.5. Shared Database and Transaction Manager Configuration

`src/main/java/com/example/rollback/DatabaseBeans.java`:

```java
package com.example.rollback;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class DatabaseBeans {
    @Bean
    public DataSource dataSource() {
        return new EmbeddedDatabaseBuilder()
                .generateUniqueName(true)
                .setType(EmbeddedDatabaseType.H2)
                .addScript("schema.sql")
                .build();
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public RollbackScenarios rollbackScenarios(JdbcTemplate jdbcTemplate) {
        return new RollbackScenarios(jdbcTemplate);
    }
}
```

`generateUniqueName(true)` is crucial: each `ApplicationContext` creates its own in-memory database. `DataSourceTransactionManager` owns JDBC transactions on that datasource. `RollbackScenarios` is a Spring bean, so `@EnableTransactionManagement` can proxy it. We do not call `commit()` or `rollback()` manually in the service.

### 7.6. Two Independent Configurations

`src/main/java/com/example/rollback/TraditionalMode.java`:

```java
package com.example.rollback;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@Import(DatabaseBeans.class)
@EnableTransactionManagement // defaults to RUNTIME_EXCEPTIONS
public class TraditionalMode {
}
```

`src/main/java/com/example/rollback/AllExceptionsMode.java`:

```java
package com.example.rollback;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.RollbackOn;

@Configuration(proxyBeanMethods = false)
@Import(DatabaseBeans.class)
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
public class AllExceptionsMode {
}
```

**Note:** we do not include both configs in the same context. Each test class below picks **one** config via `@SpringJUnitConfig(classes = ...)`. This isolates the global setting for comparison; production apps do not need multiple contexts.

### 7.7. Testing Legacy Mode: Checked Exceptions Can Still Commit

`src/test/java/com/example/rollback/TraditionalModeTest.java`:

```java
package com.example.rollback;

import java.io.IOException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(classes = TraditionalMode.class)
class TraditionalModeTest {
    @Autowired
    private RollbackScenarios service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_receipts");
    }

    private long rows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_receipts", Long.class);
    }

    @Test
    void checkedIOExceptionCommitsWithLegacyDefault() {
        assertThrows(IOException.class,
                () -> service.checkedIOException("legacy-checked"));
        assertEquals(1L, rows());
    }

    @Test
    void runtimeExceptionRollsBackWithLegacyDefault() {
        assertThrows(IllegalStateException.class,
                () -> service.runtimeFailure("legacy-runtime"));
        assertEquals(0L, rows());
    }

    @Test
    void explicitRollbackForCheckedStillWorks() {
        assertThrows(IOException.class,
                () -> service.checkedWithExplicitRollback("legacy-explicit"));
        assertEquals(0L, rows());
    }
}
```

Key evidence: the test **has no `@Transactional`**. Each service call goes through the transaction proxy, the service transaction finishes, and then the test reads the data. Therefore `1L` in the checked-exception test is the **committed** result of the example's new transaction, not an uncommitted row still sitting inside a test-managed transaction.

### 7.8. Testing New Mode: ALL_EXCEPTIONS Default and Local Overrides

`src/test/java/com/example/rollback/AllExceptionsModeTest.java`:

```java
package com.example.rollback;

import java.io.IOException;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringJUnitConfig(classes = AllExceptionsMode.class)
class AllExceptionsModeTest {
    @Autowired
    private RollbackScenarios service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_receipts");
    }

    private long rows() {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_receipts", Long.class);
    }

    @Test
    void normalReturnStillCommits() {
        service.success("all-ok");
        assertEquals(1L, rows());
    }

    @Test
    void checkedIOExceptionNowRollsBackByDefault() {
        assertThrows(IOException.class,
                () -> service.checkedIOException("all-checked"));
        assertEquals(0L, rows());
    }

    @Test
    void runtimeExceptionStillRollsBack() {
        assertThrows(IllegalStateException.class,
                () -> service.runtimeFailure("all-runtime"));
        assertEquals(0L, rows());
    }

    @Test
    void explicitRollbackForIsStillHonored() {
        assertThrows(IOException.class,
                () -> service.checkedWithExplicitRollback("all-explicit"));
        assertEquals(0L, rows());
    }

    @Test
    void explicitNoRollbackForOverridesGlobalFallback() {
        assertThrows(IOException.class,
                () -> service.checkedWithExplicitNoRollback("all-excluded"));
        assertEquals(1L, rows());
    }

    @Test
    void specificBusinessNoRollbackForCanStillCommit() {
        assertThrows(BusinessNotice.class,
                () -> service.acceptedBusinessNotice("all-notice"));
        assertEquals(1L, rows());
    }

    @Test
    void unrelatedCheckedExceptionStillUsesAllExceptionsDefault() {
        assertThrows(IOException.class,
                () -> service.unrelatedCheckedIOException("all-unrelated"));
        assertEquals(0L, rows());
    }

    @Test
    void exceptionCaughtInsideIsInvisibleToRollbackRules() {
        service.caughtCheckedInside("all-caught");
        assertEquals(1L, rows());
    }
}
```

### 7.9. Running and Interpreting Results

If the project directory was created with Spring Initializr or already includes a Gradle Wrapper, run:

```bash
./gradlew test
```

On Windows:

```powershell
.\gradlew.bat test
```

If you created the files manually without a wrapper, use a compatible installed Gradle with `gradle test` or generate the wrapper first. Do not use plain `javac` on a Spring project because the classpath contains multiple libraries; Gradle handles compilation and tests.

**Expected result** with proper dependencies and no interfering parallel test environment: **11 tests pass** (3 in `TraditionalModeTest` and 8 in `AllExceptionsModeTest`). JUnit does not guarantee method execution order and the tests **do not print fixed stdout**. View `build/reports/tests/test/index.html` to inspect actual run results.

Primary comparison table:

| Test case | Traditional context | ALL_EXCEPTIONS context |
| --- | ---: | ---: |
| `success` method, no exception | Commit 1 row | Commit 1 row |
| Checked `IOException`, no custom rule | **Commit 1 row** | **Rollback 0 rows** |
| Runtime `IllegalStateException` | Rollback 0 rows | Rollback 0 rows |
| Checked with `rollbackFor=IOException.class` | Rollback 0 rows | Rollback 0 rows |
| Checked with `noRollbackFor=IOException.class` | Commit 1 row | Commit 1 row |
| Checked `BusinessNotice` with specific `noRollbackFor` | Commit 1 row | Commit 1 row |
| Checked `IOException` not matching `noRollbackFor=BusinessNotice.class` | Commit 1 row | Rollback 0 rows |
| Checked exception caught inside method | Commit 1 row | Commit 1 row |

The table gives **predictions based on Spring 6.2 and the sample code**; the actual tests only implement the cases listed in the two test classes. Never infer from a passing `assertThrows` that the transaction rolled back; `rows()` is the proof of data state after the service boundary completes.

## 8. Limitations That Must Not Be Overlooked

### 8.1. “ALL_EXCEPTIONS” Does Not Mean Rollback in Every Situation

This parameter controls the **rollback decision on exceptions exiting through transaction interception** under default rules. It does **not** automatically roll back when:

- The method returns normally and there is no rollback-only flag.
- The exception was caught and swallowed inside the transactional method.
- SQL was committed by **another** transaction or before this transaction began.
- Non-database side effects such as HTTP requests, emails, or message broker publications already happened.
- The error occurs **after physical commit** or on a resource outside the active transaction manager.
- A transaction on another thread lacks proper transaction context propagation.

When commit fails or the connection drops at commit time, the outcome can be uncertain. **Do not treat every exception as proof that rollback succeeded.** For operations with significant business side effects, use idempotency keys and reconciliation mechanisms.

### 8.2. Checked Exceptions and “No Rollback” Can Still Be Rollback-Only

Suppose outer `@Transactional(noRollbackFor = IOException.class)` catches or throws `IOException`, yet an inner `REQUIRED` scope already marked rollback-only beforehand. Even if the outer rule chooses commit, the transaction manager must still obey the rollback-only state and may throw `UnexpectedRollbackException`. **Rule precedence is not a way to erase an already set rollback-only flag.**

### 8.3. Proxies and Self-Invocation

`@Transactional` executes when the call passes through a transactional proxy (in default proxy mode). If an annotated method is called via `this.innerMethod()` inside the same bean, the Spring proxy normally does not intercept that internal call; default rollback rules do not apply as a separate transaction boundary either.

```java
@Service
class ExampleService {
    public void outer() throws IOException {
        this.inner(); // Does not pass through the proxy for the inner() call.
    }

    @Transactional
    public void inner() throws IOException {
        throw new IOException("checked");
    }
}
```

This is a mechanism illustration requiring imports for `@Service`, `@Transactional`, and `IOException`; it is not a standalone program. To test properly, invoke **another Spring-managed bean** via injection or use a transaction template when programmatic control is needed. Do not blame the global default when advice never ran at all.

### 8.4. Reactive Transactions and Special Return Types

With `ReactiveTransactionManager`, transactions bind to the **Reactor context** and publisher lifecycle rather than an imperative `ThreadLocal`. A default rollback configuration can apply when the reactive infrastructure parses transaction attributes, yet `onError`, `cancel`, and subscription timing require separate analysis. Do not apply “Java method returns normally → commit” to `Mono`/`Flux`.

In Spring 6.1+, a `Future` already completed exceptionally at the moment the method returns can be evaluated by the transaction infrastructure against rollback rules. This does not mean imperative transactions wait for arbitrary background tasks completing later. `@Async` tasks and retry advice must be tested at the real boundary and actual advice order.

### 8.5. Test-Managed Transactions Masking Outcomes

In Spring TestContext, a test annotated with `@Transactional` typically gets its own transaction rolled back after the test. A `REQUIRED` service can join the test's transaction, so seeing a record **during the test** does not prove the service committed. The hands-on test suite omits that annotation on test classes specifically to observe post-boundary state.

### 8.6. Databases Can Throw Different Exceptions Than Expected

`JdbcTemplate` usually translates SQL exceptions into `DataAccessException` (unchecked); those already rolled back under the legacy default. `ALL_EXCEPTIONS` mainly makes a difference when **checked exceptions actually escape** a transactional method. With JPA, SQL may flush at commit time, causing exceptions to appear after the method body. Testing with H2 does not prove every isolation/locking/flushing behavior of a production database.

## 9. Migration Checklist When Enabling Global Rollback

Do not flip one annotation and assume every business flow stays intact. Proceed step by step:

1. **Confirm dependencies** actually use Spring Framework 6.2+; if using Spring Boot, check the Spring version managed by its BOM.
2. **Inventory public transactional methods** that declare checked `throws` or call libraries throwing checked exceptions. For Kotlin, also look for Java checked exceptions that Kotlin does not require declaring.
3. **Classify exceptions by business semantics:** failures that must discard all changes, outcomes that should keep data, errors caught and recovered, and errors spanning other resources.
4. **Write regression tests before switching modes** for methods currently relying on checked-exception commits: observe real row counts/states after the proxy.
5. **Enable `rollbackOn = ALL_EXCEPTIONS`** on the right transaction configuration context; avoid duplicate conflicting configurations.
6. **Declare explicit `noRollbackFor`** for exceptions where business logic intentionally commits; or better, consider returning a result type instead of using exceptions as partial-success signals.
7. **Audit exceptions uncovered** by local `rollbackFor`/`noRollbackFor` rules, especially methods that declare one exception yet can throw others.
8. **Test nested propagation and rollback-only**, such as an inner `REQUIRED` throwing a checked exception caught by outer; the new global default may mark the shared transaction rollback-only.
9. **Read data after the transaction boundary** in tests without `@Transactional` to confirm real commit/rollback.
10. **Verify against a production-compatible database** when logic involves constraints, flushing, savepoints, locking, or specialized transaction managers.
11. **Measure and update contracts** of APIs returning errors/exceptions: callers may still receive the same `IOException`, yet the backing data changed from committed to rolled back.
12. **Monitor deployment**, as this change can increase rollbacks and alter retry counts or business event observability.

A proper migration preserves **business invariants**, not merely green unit tests checking annotation presence. If a workflow “saves an order and signals that extra info is needed” must retain the order, design an appropriate status rather than relying on checked exceptions and legacy commit habits.

## 10. Common Misconceptions

**Misconception 1 — Upgrading to Spring 6.2 automatically rolls back all checked exceptions.**  
False. `RollbackOn.RUNTIME_EXCEPTIONS` remains the default; you must opt in to change it.

**Misconception 2 — `ALL_EXCEPTIONS` is equivalent to editing `@Transactional(rollbackFor=Exception.class)` onto every method.**  
Not quite. It is a **global fallback rule** supplied by the infrastructure with lower precedence than specific rules; it does not rewrite per-method source annotations or out-of-scope transaction APIs.

**Misconception 3 — Having `noRollbackFor` on a method disables the global default for other exceptions.**  
False. Only exceptions matching the rule take precedence; unmatched exceptions still use the fallback.

**Misconception 4 — `noRollbackFor` guarantees commit succeeds.**  
False. The transaction may already be rollback-only, SQL/commit can fail, or another resource can error.

**Misconception 5 — A checked exception caught internally still rolls back because of ALL_EXCEPTIONS.**  
False when the interceptor sees only a normal method return and there is no rollback-only flag.

**Misconception 6 — Putting `@EnableTransactionManagement` in any context affects every bean.**  
False. Transaction annotation processing is tied to the configured Spring application context; verify beans are proxied in the right context.

**Misconception 7 — `ALL_EXCEPTIONS` mode overrides `@Transactional(propagation=...)`.**  
False. It only changes the default rollback rule; propagation still applies independently.

**Misconception 8 — `DataAccessException` now rolls back only thanks to ALL_EXCEPTIONS.**  
False. `DataAccessException` is a runtime exception and already rolled back in typical cases under the legacy default.

**Misconception 9 — If commit throws an exception, the database definitely rolled back.**  
False. Some commit failures leave an ambiguous state; reconciliation, business keys, and idempotency mechanisms are required.

**Misconception 10 — XML transaction advice and `TransactionTemplate` both inherit the global switch automatically.**  
Do not assume that. The option is documented for Spring's rule-based **annotation transaction** infrastructure; XML/programmatic configurations have their own paths and contracts.

## 11. Self-Check Questions

**Question 1.** An application upgrades from Spring 6.1 to 6.2 without changing configuration. A `@Transactional` method throws `IOException`. What changes?  
**Answer:** No default change occurs solely from upgrading versions: it still follows `RUNTIME_EXCEPTIONS`, unless other rollback rules or transaction states exist.

**Question 2.** `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)` is enabled, and a method with `noRollbackFor = IOException.class` throws `IOException`. Under rollback rules, what does Spring choose?  
**Answer:** It chooses commit for that method because the specific local rule beats the default. Actual outcome still depends on transaction state/committability.

**Question 3.** The same method declares only `noRollbackFor = BusinessNotice.class`, yet throws `IOException`. Outcome under `ALL_EXCEPTIONS`?  
**Answer:** `IOException` does not match the local rule; the fallback selects rollback.

**Question 4.** `@Transactional` is called via `this.method()` inside a bean with no outer transaction. Does enabling `ALL_EXCEPTIONS` make advice run?  
**Answer:** No. A proxy call or another transaction mechanism is required; global rules do not fix self-invocation.

**Question 5.** Why is `assertThrows(IOException.class, ...)` insufficient to prove rollback?  
**Answer:** The caller can receive `IOException` **after Spring commits** (under traditional defaults). You must query data after the transaction boundary ends.

**Question 6.** Does enabling `ALL_EXCEPTIONS` automatically alter `TransactionTemplate` or a JTA container not using Spring's interceptor?  
**Answer:** Do not assume so. This configures the default rollback rule for the annotation transaction infrastructure in the context; programmatic/external systems have separate contracts.

**Question 7.** When migrating a service that uses checked `BusinessNotice` to report “saved and awaiting review”, what should you check?  
**Answer:** Confirm the invariant that the record must be kept. Consider returning a normal business status or adding tested `noRollbackFor = BusinessNotice.class`, and measure post-boundary data.

**Question 8.** Why should you test inner `REQUIRED` when changing the global default?  
**Answer:** Checked exceptions that an inner scope previously did not mark rollback-only can now mark the shared physical transaction rollback-only, preventing outer from committing even if it catches the exception.

## 12. Official Documentation

- [Spring Framework 6.2 — Using @Transactional: global rollback defaults](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — EnableTransactionManagement Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html)
- [Spring Framework 6.2 — RollbackOn enum Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/RollbackOn.html)
- [Spring Framework 6.2 — AnnotationTransactionAttributeSource Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/AnnotationTransactionAttributeSource.html)
- [Spring Framework 6.2 — RollbackRuleAttribute Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/RollbackRuleAttribute.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Embedded Database Support](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/embedded-database-support.html)
