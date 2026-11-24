# Distinguishing `org.springframework.transaction.annotation.Transactional` from `jakarta.transaction.Transactional`

## 1. Two Annotations with the Same Name, Two Different APIs

When working with Spring Framework, you may encounter two ways to import `@Transactional`:

```java
import org.springframework.transaction.annotation.Transactional;
```

```java
import jakarta.transaction.Transactional;
```

**Both can declare the transaction boundary of a Spring bean.** Spring Framework supports the standard `jakarta.transaction.Transactional` annotation as an alternative to its own annotation. However, **sharing the same name does not mean sharing the same attributes**: Spring provides its own options for isolation, timeout, read-only, selecting a transaction manager, and `NESTED`; Jakarta uses `TxType`, `rollbackOn`, and `dontRollbackOn`.

- **Spring `@Transactional`** belongs to the Spring API and suits applications deeply using Spring Transaction Management.
- **Jakarta `@Transactional`** belongs to the Jakarta Transactions (JTA) standard, designed for Jakarta EE/CDI managed components. When processed inside a Spring application, it still goes through Spring's transaction infrastructure.
- **The annotation does not determine the transaction manager type.** Using Jakarta's annotation in Spring with `JdbcTransactionManager` still runs a local JDBC transaction; it does not automatically create XA/2-phase commit.

In this lesson, we compare the semantics of both annotations **in Spring Framework 6.x** and point out behaviors rooted in the Jakarta EE specification.

## 2. Quick Comparison Table

| Criterion | `org.springframework.transaction.annotation.Transactional` | `jakarta.transaction.Transactional` |
| --- | --- | --- |
| Origin | Spring Framework | Jakarta Transactions |
| Default propagation | `Propagation.REQUIRED` | `TxType.REQUIRED` |
| Propagation attribute | `propagation = Propagation.REQUIRES_NEW` | `value = TxType.REQUIRES_NEW` |
| Propagation types | `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `MANDATORY`, `NOT_SUPPORTED`, `NEVER`, `NESTED` | The first six values; **no `NESTED`** |
| Isolation level | Has `isolation`, e.g., `Isolation.READ_COMMITTED` | No corresponding attribute |
| Timeout | Has `timeout` and `timeoutString` | No corresponding attribute |
| Read-only | Has `readOnly` | No corresponding attribute |
| Per-method manager selection | Has `transactionManager` or `value` (String) | No attribute to specify a Spring transaction manager |
| Rollback on exception | `rollbackFor` | `rollbackOn` |
| No rollback on exception | `noRollbackFor` | `dontRollbackOn` |
| Exception name rules | Has `rollbackForClassName` and `noRollbackForClassName` | None |
| Transaction labels | Has `label` | None |
| Spring composed annotations | Supports custom meta-annotations | Does not offer the same Spring-specific API |
| Applied on Spring beans | Spring AOP proxy or configured AspectJ mechanism | Spring reads Jakarta annotation metadata and uses matching transaction infrastructure |
| In Jakarta EE/CDI | Not the standard Jakarta Transactions interceptor binding | Standard interceptor binding for CDI/managed beans |

**Most common mistake:** the `value` attribute means completely different things.

```java
// Spring: value (or transactionManager) is a String selecting the manager.
@org.springframework.transaction.annotation.Transactional("ordersTx")
public void springWork() {
    System.out.println("Spring transaction manager: ordersTx");
}

// Jakarta: value is the TxType enum, not a manager name.
@jakarta.transaction.Transactional(
        jakarta.transaction.Transactional.TxType.REQUIRES_NEW)
public void jakartaWork() {
    System.out.println("Jakarta TxType: REQUIRES_NEW");
}
```

These are **two syntax illustration methods**, not a standalone program. `ordersTx` must exist in the Spring context. If you use the Jakarta annotation and try writing `value = "ordersTx"`, the code will not compile.

## 3. Comparing `Propagation` with `TxType`

| Spring `Propagation` | Jakarta `TxType` | Intended behavior |
| --- | --- | --- |
| `REQUIRED` | `REQUIRED` | Join if a transaction exists; start a new transaction otherwise. |
| `REQUIRES_NEW` | `REQUIRES_NEW` | Suspend the current transaction and start an independent transaction if supported. |
| `SUPPORTS` | `SUPPORTS` | Join if a transaction exists; continue running without a transaction otherwise. |
| `MANDATORY` | `MANDATORY` | A transaction must already exist; otherwise throw an error. |
| `NOT_SUPPORTED` | `NOT_SUPPORTED` | Run without a transaction, suspending the current transaction if present. |
| `NEVER` | `NEVER` | Must be called without a transaction; throw an error if one is active. |
| `NESTED` | **None** | Spring can use a savepoint inside the same physical transaction, depending on manager/driver/DB. |

For example, when you need to **create a new independent transaction**, the two ways to write it are:

```java
@org.springframework.transaction.annotation.Transactional(
        propagation = org.springframework.transaction.annotation.Propagation.REQUIRES_NEW)
public void auditWithSpring() {
    System.out.println("audit in separate transaction");
}

@jakarta.transaction.Transactional(
        value = jakarta.transaction.Transactional.TxType.REQUIRES_NEW)
public void auditWithJakarta() {
    System.out.println("audit in separate transaction");
}
```

These methods are **illustrative snippets to place inside a Spring-managed service**. Actually creating a new transaction still depends on the bean proxy and transaction manager capabilities.

**Do not mechanically replace `Propagation.NESTED` with Jakarta `TxType.REQUIRES_NEW`.** `NESTED` is typically a savepoint inside the current physical transaction rather than committing independently; `REQUIRES_NEW` is a separate transaction boundary. If the outer transaction rolls back, the final effect of the two choices can differ.

## 4. Comparing Rollback Rules

### 4.1. Defaults

In standard imperative Spring Transaction Management, the interceptor rolls back by default when a `RuntimeException` or `Error` escapes the method boundary, but **does not automatically roll back checked exceptions**. Under the Jakarta Transactions specification, `RuntimeException` marks rollback by default while checked exceptions do not. When Jakarta annotations are processed by Spring, you must account for Spring's actual transaction interceptor rules.

Example with checked exception `IOException`: to trigger rollback, you must specify it explicitly.

```java
@org.springframework.transaction.annotation.Transactional(
        rollbackFor = java.io.IOException.class)
public void importWithSpring() throws java.io.IOException {
    throw new java.io.IOException("import failed");
}

@jakarta.transaction.Transactional(
        rollbackOn = java.io.IOException.class)
public void importWithJakarta() throws java.io.IOException {
    throw new java.io.IOException("import failed");
}
```

The two methods are **attribute examples**; when called through a transaction proxy, the escaping exception leads to rollback handling. If you simply `new` the object and call it directly, the annotation does not make Spring start a transaction.

### 4.2. Excluding an Exception from Rollback Rules

```java
@org.springframework.transaction.annotation.Transactional(
        noRollbackFor = IllegalArgumentException.class)
public void springIgnore() {
    throw new IllegalArgumentException("validation outcome");
}

@jakarta.transaction.Transactional(
        dontRollbackOn = IllegalArgumentException.class)
public void jakartaIgnore() {
    throw new IllegalArgumentException("validation outcome");
}
```

Between the two styles, **the attribute names differ**: `noRollbackFor` in Spring, `dontRollbackOn` in Jakarta. Not rolling back according to **interceptor rules** does not mean a commit can be forced if the transaction is already `rollback-only` or the DB hits an error requiring rollback.

### 4.3. When Rules Overlap

- Spring picks the **most specific** matching rollback rule by exception type; there are also class-name pattern variants. Prefer `rollbackFor = MyException.class` over pattern strings to avoid accidentally matching `MyExceptionV2` or similar nested exceptions.
- The Jakarta Transactions specification defines `dontRollbackOn` as taking precedence over `rollbackOn` when the same exception matches both. When running under a specific runtime—especially with multiple rules or advice layers—write integration tests instead of relying on assumptions.
- Newer Spring versions allow changing the **application-wide default rollback rule**, such as `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`. Hence "checked exceptions always commit" holds only while the corresponding default configuration remains unchanged.

**Important:** if you catch an exception **inside** the `@Transactional` method and do not rethrow it, the transaction interceptor normally never sees that exception. Exception-based rollback rules do not trigger automatically just because a `catch` ran, and the transaction may commit unless marked rollback-only or encountering another error.

## 5. Complete Hands-On Example in Spring Framework (Java 17+)

We will run **both annotations in the same Spring `ApplicationContext`** and the same `JdbcTransactionManager`, then inspect database state after each transaction boundary.

Environment: **Java 17+, Spring Framework 6.2.5, Jakarta Transactions API 2.0.1, H2 2.2.224, Maven**. These versions are pinned explicitly so you can easily reproduce the demo. No Spring Boot, Jakarta EE server, or separate database installation is needed.

Structure:

```text
transactional-comparison/
  pom.xml
  src/main/java/demo/TransactionalComparison.java
```

### 5.1. Create `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transactional-comparison</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>jakarta.transaction</groupId>
            <artifactId>jakarta.transaction-api</artifactId>
            <version>2.0.1</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
            <scope>runtime</scope>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the container and JavaConfig; `spring-jdbc` provides `JdbcTemplate`; `spring-tx` provides the transaction API/manager; `jakarta.transaction-api` provides the Jakarta annotation; H2 is the in-memory database.

### 5.2. Create `src/main/java/demo/TransactionalComparison.java`

```java
package demo;

import java.io.IOException;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionalComparison {
    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE tx_record (
                        id INT PRIMARY KEY,
                        note VARCHAR(40) NOT NULL
                    )
                    """);

            SpringWriter spring = ctx.getBean(SpringWriter.class);
            JakartaWriter jakarta = ctx.getBean(JakartaWriter.class);

            spring.insert(1, false);
            jakarta.insert(2, false);
            System.out.println("after_success=" + count(jdbc));

            try {
                spring.insert(3, true);
            } catch (IllegalStateException ex) {
                System.out.println("spring_failure=" + ex.getMessage());
            }

            try {
                jakarta.insert(4, true);
            } catch (IllegalStateException ex) {
                System.out.println("jakarta_failure=" + ex.getMessage());
            }
            System.out.println("after_runtime_errors=" + count(jdbc));

            try {
                spring.insertThenThrowChecked(5);
            } catch (IOException ex) {
                System.out.println("spring_checked_failure=" + ex.getMessage());
            }

            try {
                jakarta.insertThenThrowChecked(6);
            } catch (IOException ex) {
                System.out.println("jakarta_checked_failure=" + ex.getMessage());
            }
            System.out.println("after_checked_errors=" + count(jdbc));
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject("SELECT COUNT(*) FROM tx_record", Integer.class);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        public DataSource dataSource() {
            var ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_compare;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        public SpringWriter springWriter(JdbcTemplate jdbcTemplate) {
            return new SpringWriter(jdbcTemplate);
        }

        @Bean
        public JakartaWriter jakartaWriter(JdbcTemplate jdbcTemplate) {
            return new JakartaWriter(jdbcTemplate);
        }
    }

    public static class SpringWriter {
        private final JdbcTemplate jdbc;

        public SpringWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @org.springframework.transaction.annotation.Transactional
        public void insert(int id, boolean failAfterInsert) {
            jdbc.update("INSERT INTO tx_record (id, note) VALUES (?, ?)", id, "spring");
            System.out.println("spring_active="
                    + TransactionSynchronizationManager.isActualTransactionActive());
            if (failAfterInsert) {
                throw new IllegalStateException("boom");
            }
        }

        @org.springframework.transaction.annotation.Transactional(
                rollbackFor = IOException.class)
        public void insertThenThrowChecked(int id) throws IOException {
            jdbc.update("INSERT INTO tx_record (id, note) VALUES (?, ?)", id, "spring");
            throw new IOException("checked");
        }
    }

    public static class JakartaWriter {
        private final JdbcTemplate jdbc;

        public JakartaWriter(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @jakarta.transaction.Transactional
        public void insert(int id, boolean failAfterInsert) {
            jdbc.update("INSERT INTO tx_record (id, note) VALUES (?, ?)", id, "jakarta");
            System.out.println("jakarta_active="
                    + TransactionSynchronizationManager.isActualTransactionActive());
            if (failAfterInsert) {
                throw new IllegalStateException("boom");
            }
        }

        @jakarta.transaction.Transactional(rollbackOn = IOException.class)
        public void insertThenThrowChecked(int id) throws IOException {
            jdbc.update("INSERT INTO tx_record (id, note) VALUES (?, ?)", id, "jakarta");
            throw new IOException("checked");
        }
    }
}
```

**Why use fully qualified annotation names?** Both annotations share the simple name `Transactional`; a single Java file cannot import both and use `@Transactional` without ambiguity. Writing full package names helps learners identify the exact API in use.

**Why doesn't the demo need a JTA server?** `Config` enables `@EnableTransactionManagement` and registers a `JdbcTransactionManager` and two Spring beans. Spring AOP proxies intercept public method calls on each bean; Spring reads metadata from both annotations. Transactions here are local JDBC transactions on H2, executed by **the same manager**.

### 5.3. Compile, Run, and Read the Results

Inside the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TransactionalComparison
```

Output from `System.out`, excluding tool startup messages:

```text
spring_active=true
jakarta_active=true
after_success=2
spring_active=true
spring_failure=boom
jakarta_active=true
jakarta_failure=boom
after_runtime_errors=2
spring_checked_failure=checked
jakarta_checked_failure=checked
after_checked_errors=2
```

Result analysis:

1. `spring.insert(1, false)` and `jakarta.insert(2, false)` are called through Spring bean proxies; new transactions start and commit normally, producing two rows.
2. Both `insert(..., true)` methods execute the `INSERT` inside a transaction and then throw unchecked `IllegalStateException`. The interceptor rolls back, so the row count remains `2`.
3. Both `insertThenThrowChecked` methods throw `IOException`. By default checked exceptions do not trigger rollback, yet here we declared **`rollbackFor`** on the Spring annotation and **`rollbackOn`** on the Jakarta annotation; both `INSERT`s roll back, so the row count stays `2`.
4. `TransactionSynchronizationManager.isActualTransactionActive()` prints `true` for both services because Spring is managing a transaction on the thread. That is **not proof of commit**; the `COUNT(*)` query after the proxy calls finish confirms the final data state.

**Additional experiment:** On a copy of the example, remove the `rollbackFor` and `rollbackOn` attributes and re-run against a fresh in-memory database. Under default rules, the two `IOException`s will not automatically mark rollback, so even though the caller catches the checked exceptions, the `INSERT`s can commit. Restore both rollback rules once finished.

## 6. How Does Using the Jakarta Annotation in Spring Differ from Jakarta EE/CDI?

### When Running in Spring

`@EnableTransactionManagement` or equivalent configuration activates transaction advice. Spring can read metadata from both annotations, turn them into transaction attributes, and use the configured transaction manager (JDBC, JPA, or JTA). Having the `jakarta.transaction` package on the annotation **does not automatically require a Jakarta EE container or JTA coordinator**.

If a Spring application has multiple `PlatformTransactionManager`s, the Spring annotation supports per-method selection:

```java
@org.springframework.transaction.annotation.Transactional(
        transactionManager = "auditTransactionManager")
public void auditWithNamedManager() {
    System.out.println("audit");
}
```

This is an illustrative method inside a Spring bean, requiring an actual manager named `auditTransactionManager`. The Jakarta annotation **has no** `transactionManager` attribute to declare this; you may need a default manager/`TransactionManagementConfigurer` per your architecture, or use the Spring annotation where a qualifier is required.

### When Running in Jakarta EE/CDI

`jakarta.transaction.Transactional` is a standard CDI interceptor binding, applied to supported managed beans and backed by the Jakarta EE runtime's transaction infrastructure. `TxType` and rollback rules are handled by the container's interceptor.

Merely adding the `jakarta.transaction-api` dependency to a Java SE project and calling `new Service()` will **not automatically provide a transaction interceptor**. If a single application has both Spring and a Jakarta EE runtime, know which one truly owns the boundary; overlapping interceptor configurations can produce unexpected behavior.

## 7. How to Convert Syntax Safely

If the code only uses corresponding propagation and rollback rules, you can translate the intent:

**Spring:**

```java
@org.springframework.transaction.annotation.Transactional(
        propagation = org.springframework.transaction.annotation.Propagation.REQUIRES_NEW,
        rollbackFor = java.io.IOException.class)
public void publishSpring() throws java.io.IOException {
    throw new java.io.IOException("send failed");
}
```

**Jakarta:**

```java
@jakarta.transaction.Transactional(
        value = jakarta.transaction.Transactional.TxType.REQUIRES_NEW,
        rollbackOn = java.io.IOException.class)
public void publishJakarta() throws java.io.IOException {
    throw new java.io.IOException("send failed");
}
```

These are **illustrative service snippets**, not standalone programs. If the method is called through a proxy and a new transaction is actually created, both express equivalent intent for `REQUIRES_NEW` and checked-exception rollback.

Conversely, the following Spring snippet **cannot have its attributes translated directly** to the Jakarta annotation:

```java
@org.springframework.transaction.annotation.Transactional(
        isolation = org.springframework.transaction.annotation.Isolation.READ_COMMITTED,
        timeout = 10,
        readOnly = true,
        transactionManager = "reportingTransactionManager")
public void loadReport() {
    System.out.println("read report");
}
```

`isolation`, `timeout`, `readOnly`, and `transactionManager` do not exist on the Jakarta annotation. Switching the import drops configuration information or causes compilation errors. `readOnly` in Spring is only a **hint**, not a guarantee that the DB strictly rejects writes; `timeout` and `isolation` primarily take effect when creating a new transaction.

### Note on Moving from `javax.transaction` to `jakarta.transaction`

In older Java EE/Spring ecosystems, you may see `javax.transaction.Transactional`. When upgrading to Spring 6 and Jakarta EE 9+, the corresponding API is `jakarta.transaction.Transactional`. `javax.transaction.Transactional` and `jakarta.transaction.Transactional` are **two different Java types**. Do not treat adding both dependencies as an automatic import fix; verify framework versions, configuration, and transaction integration tests.

## 8. Common Mistakes

| Symptom / misconception | Explanation and fix |
| --- | --- |
| Jakarta annotation lacks `readOnly`, `isolation`, `rollbackFor` | These are Spring-specific attributes. Keep the Spring annotation if you need them, or use Jakarta's `rollbackOn`/`TxType` properly. |
| Writing Jakarta `value="txManager"` | Type mismatch: Jakarta `value` expects `TxType`; Spring's `value` is the manager name qualifier. |
| Thinking `TxType.REQUIRES_NEW` replaces `Propagation.NESTED` | Physical transactions and savepoints differ; do not swap mechanically. |
| Thinking the Jakarta annotation creates an XA transaction | The actual transaction manager/resources determine whether a transaction is local or distributed. |
| Annotation present, yet no rollback occurs | Check that annotation transaction management is enabled, the bean is Spring-managed, and calls go through the proxy. |
| Creating a service with `new` or calling `this.innerMethod()` | In proxy mode, Spring advice does not intercept that call as a new boundary. |
| Thinking all checked exceptions roll back | Requires `rollbackFor` or `rollbackOn`, unless global rules were customized. |
| Multiple datasources/transaction managers | Use matching managers explicitly; when per-method manager selection is needed, the Spring annotation offers `transactionManager`. |
| Placing both Spring and Jakarta `@Transactional` on the same method | Makes metadata confusing, especially if rules conflict; choose one annotation per boundary and test. |
| Changing `javax.transaction` import to `jakarta.transaction` without upgrading compatible dependencies | May fail to compile or fail to be recognized at runtime; verify framework and Jakarta API versions. |
| Thinking `@Transactional` handles every self-invocation, new thread, or `@Async` | Spring proxies do not intercept self-invocation; imperative transactions are normally thread-bound and do not automatically propagate to other threads. |

**Note on Spring Boot:** in Boot apps with matching transaction auto-configuration, you often do not need to add `@EnableTransactionManagement` manually. Still, both annotations require active transaction infrastructure and an appropriate manager. That does not change the differences in their attribute sets.

## 9. When Should You Choose Which?

**Prefer Spring `@Transactional` if the application primarily runs on Spring Framework/Spring Boot** and needs any of these features: `isolation`, `timeout`, `readOnly`, `Propagation.NESTED`, per-method transaction manager selection, labels, or class-name rollback rules. This annotation expresses the options of Spring's transaction infrastructure more completely.

**You can choose Jakarta `@Transactional`** if the project targets Jakarta Transactions/CDI contracts or aims to stay consistent with Jakarta-standard code, and only needs the six common `TxType` values and exception-class rollback rules. Before adopting it, verify that Spring/your runtime recognizes the annotation and test critical boundaries.

Once an API is chosen for a codebase area, keep imports consistent. You cannot infer "Jakarta's annotation is faster" or "Spring's annotation is more durable" from the package name alone: performance and reliability depend on the DB, manager, connection handling, and transaction boundaries.

## 10. Comprehension Check Questions

**1.** When using `@jakarta.transaction.Transactional` on a Spring bean accessing JDBC via `JdbcTransactionManager`, is a JTA/XA coordinator strictly required?

**Answer:** No. Spring can interpret the Jakarta annotation and execute a local JDBC transaction using the configured manager.

**2.** How do you declare that a checked `IOException` should trigger rollback?

**Answer:** Spring uses `rollbackFor = IOException.class`; Jakarta uses `rollbackOn = IOException.class`.

**3.** If you need `isolation = READ_COMMITTED`, `timeout = 10`, and `readOnly = true` on the same method, which annotation should you choose?

**Answer:** Spring `@Transactional`, because the Jakarta annotation lacks those corresponding attributes.

**4.** Does Spring `Propagation.NESTED` correspond to Jakarta `TxType.REQUIRES_NEW`?

**Answer:** No. `NESTED` typically relies on a savepoint within the existing transaction, whereas `REQUIRES_NEW` creates a separate physical transaction.

**5.** Why do two files both have `@Transactional`, yet the IDE only allows `value = "paymentsTx"` in one of them?

**Answer:** That file imports the Spring annotation. In Jakarta, `value` is the `TxType` enum rather than a String qualifier.

**6.** If a service uses `@jakarta.transaction.Transactional` yet is instantiated with `new` in a Spring app, does the annotation open a transaction automatically?

**Answer:** No. Manually instantiated objects are not intercepted by Spring proxies; you must use a Spring bean or an appropriate container/interceptor.

## Takeaways

- **Same `@Transactional` name, different APIs.** Spring has more attributes; Jakarta is a concise standard focused on `TxType` and rollback rules.
- **Spring:** `propagation`, `rollbackFor`, `noRollbackFor`, `isolation`, `timeout`, `readOnly`, `transactionManager`, `NESTED`.
- **Jakarta:** `value = TxType.*`, `rollbackOn`, `dontRollbackOn`; no `NESTED` or Spring-specific options.
- **Inside Spring, both can be handled by Spring's transaction interceptor.** The annotation only describes the transaction; the transaction manager and proxy actually govern behavior.
- When switching imports, double-check attribute names, transaction managers, default rollback behavior, and run commit/rollback integration tests.

## Official References

1. Spring Framework 6.2 — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html).
2. Spring Framework — [Spring `@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html).
3. Jakarta EE Platform — [Jakarta `@Transactional` Javadoc](https://jakarta.ee/specifications/platform/11/apidocs/jakarta/transaction/transactional).
4. Jakarta EE — [`Transactional.TxType`](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/transaction/transactional.txtype).
5. Jakarta Transactions — [Specification 2.0](https://jakarta.ee/specifications/transactions/2.0/jakarta-transactions-spec-2.0.html).
6. Maven Central — [`jakarta.transaction-api`](https://central.sonatype.com/artifact/jakarta.transaction/jakarta.transaction-api).
