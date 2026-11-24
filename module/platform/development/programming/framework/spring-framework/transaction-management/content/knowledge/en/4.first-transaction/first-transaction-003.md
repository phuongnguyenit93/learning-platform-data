# Enabling Transaction Management with `@EnableTransactionManagement` in Spring Framework

## 1. Lesson Objectives

When writing a plain Spring application (without relying on Spring Boot's transaction auto-configuration), you need to **enable `@Transactional` processing** and provide a suitable **transaction manager**. `@EnableTransactionManagement` is the configuration annotation that helps Spring detect, intercept method calls, and apply declarative transaction boundaries.

After this lesson, you can:

- Explain why placing `@Transactional` on a service alone is not enough.
- Place `@EnableTransactionManagement` in the right spot in Java configuration.
- Declare `DataSource`, `PlatformTransactionManager`, and services as Spring beans.
- Run one successful transaction and one rolled-back transaction with Java 17+, Spring Framework, and H2.
- Identify common mistakes: calling an object directly, self-invocation within the same class, missing manager, confusing `proxyTargetClass`, and confusing Spring Boot with plain Spring.

**Primary scope:** imperative (synchronous) transactions via Spring AOP proxy and JDBC. Reactive applications have a different transaction management mechanism; the final section briefly notes this to avoid misapplication.

## 2. Why Is `@Transactional` Alone Not Enough?

For example, we write:

```java
public class PaymentService {
    @Transactional
    public void pay() {
        // Write data to the database
    }
}
```

`@Transactional` is only **metadata** describing the desire for transaction management. It does not automatically turn arbitrary Java objects into Spring-managed objects, nor does it create a transaction manager.

In plain Spring configuration using JavaConfig, all pieces must be present:

| Component | Responsibility |
| --- | --- |
| `@Configuration` + `@EnableTransactionManagement` | Activates transaction annotation processing infrastructure in the Spring ApplicationContext. |
| `@Transactional` | Marks methods/classes needing transaction boundaries and configures propagation, rollback, isolation, read-only, etc. |
| `PlatformTransactionManager` | Begins, commits, and rolls back physical transactions for the corresponding data technology. For example: `JdbcTransactionManager`, `DataSourceTransactionManager`, or `JpaTransactionManager`. |
| `DataSource` / data resource | Provides actual connections to the database. |
| Spring-managed bean and proxy call | Gives the transaction interceptor a chance to intercept the method call. |

`@EnableTransactionManagement` **does not create a `DataSource` or transaction manager by itself**. If a transaction manager is missing, an error may appear when invoking the `@Transactional` method rather than at annotation scanning time.

### Execution Flow

```text
ApplicationContext initializes
  |
  +-- Reads @Configuration and @EnableTransactionManagement
  +-- Registers transaction advisor + TransactionInterceptor + AOP auto-proxy
  +-- Creates beans, including DataSource and transactionManager
  '-- Creates proxies for beans with matching @Transactional methods

External code calls Spring bean (proxy)
  |
  +-- TransactionInterceptor selects the transaction manager
  +-- Starts a new transaction or joins an existing transaction
  +-- Calls the business method
  +-- Normal return: commits when the proxy owns the transaction to complete
  '-- Throws exception: checks rollback/commit rules then propagates exception to caller
```

**Key point:** the interceptor wraps calls through a **proxy**. With the default `AdviceMode.PROXY`, a `this.someMethod()` call inside the same object does not go through the proxy to apply a new `@Transactional` configuration.

## 3. Minimal Enablement with JavaConfig

In plain Spring Framework, the configuration looks like:

```java
@Configuration
@EnableTransactionManagement
public class TransactionConfig {

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

This is an **illustrative configuration snippet**, not yet enough to run standalone: `DataSource` must be created in the same ApplicationContext or imported from another configuration; the service must also be a Spring bean. The complete example below supplies both.

Meaning of each line:

1. `@Configuration`: tells Spring that the class contains bean definitions/configuration.
2. `@EnableTransactionManagement`: enables transaction advice based on `@Transactional`. You do not need to add `@EnableAspectJAutoProxy` just to enable transaction annotations in basic examples.
3. `@Bean transactionManager(...)`: supplies the manager so Spring can actually open/close transactions.
4. `JdbcTransactionManager`: manages JDBC transactions for the exact `DataSource` injected. `JdbcTemplate` used in the service must also access that same resource to participate in the transaction.

You can use `DataSourceTransactionManager` instead of `JdbcTransactionManager` for JDBC; both manage local transactions on a single `DataSource`. When using JPA, you normally use `JpaTransactionManager` configured for the persistence unit rather than copying JDBC configuration verbatim to JPA.

## 4. Complete Demo: Enabling Management and Proving Rollback

The demonstration project uses **Java 17+, Spring Framework 6.2.19, Maven, and in-memory H2**. No Spring Boot, Docker, or separate database server is required.

Two-file structure:

```text
enable-transaction-demo/
├── pom.xml
└── src/main/java/com/example/tx/EnableTxDemo.java
```

### 4.1. Creating `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>enable-transaction-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.4.240</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the container/JavaConfig, `spring-jdbc` provides `JdbcTemplate` and the JDBC transaction manager, `spring-tx` contains transaction annotations/APIs, and H2 is the test database. Versions are pinned so re-running the example does not depend on the latest releases at the time of study.

### 4.2. Creating `EnableTxDemo.java`

```java
package com.example.tx;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class EnableTxDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(TxConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE demo_accounts (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO demo_accounts (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO demo_accounts (id, balance) VALUES (?, ?)", 2, 100);

            MoneyService service = context.getBean(MoneyService.class);
            printBalances("INIT", jdbc);

            service.transfer(1, 2, 30, false);
            printBalances("AFTER_COMMIT", jdbc);

            try {
                service.transfer(1, 2, 20, true);
            } catch (IllegalStateException ex) {
                System.out.println("EXPECTED_ERROR=" + ex.getMessage());
            }
            printBalances("AFTER_ROLLBACK", jdbc);
        }
    }

    private static void printBalances(String prefix, JdbcTemplate jdbc) {
        int a = jdbc.queryForObject(
                "SELECT balance FROM demo_accounts WHERE id = ?", Integer.class, 1);
        int b = jdbc.queryForObject(
                "SELECT balance FROM demo_accounts WHERE id = ?", Integer.class, 2);

        System.out.printf("%s: A=%d, B=%d%n", prefix, a, b);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class TxConfig {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:transaction_lesson;DB_CLOSE_DELAY=-1");
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
        public MoneyService moneyService(JdbcTemplate jdbcTemplate) {
            return new MoneyService(jdbcTemplate);
        }
    }

    public static class MoneyService {
        private final JdbcTemplate jdbc;

        public MoneyService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transfer(int from, int to, int amount, boolean failAfterDebit) {
            System.out.println("IN_TRANSACTION="
                    + TransactionSynchronizationManager.isActualTransactionActive());

            if (amount <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            int debited = jdbc.update(
                    "UPDATE demo_accounts SET balance = balance - ? "
                    + "WHERE id = ? AND balance >= ?",
                    amount, from, amount);
            if (debited != 1) {
                throw new IllegalArgumentException("source missing or insufficient funds");
            }

            // Simulate an error occurring after the debit SQL statement has already been sent.
            if (failAfterDebit) {
                throw new IllegalStateException("simulated failure");
            }

            int credited = jdbc.update(
                    "UPDATE demo_accounts SET balance = balance + ? WHERE id = ?",
                    amount, to);
            if (credited != 1) {
                throw new IllegalArgumentException("destination account missing");
            }
        }
    }
}
```

The example packs configuration, service, and `main` into **one Java file** using nested `static` classes. `MoneyService` is registered via `@Bean`, then retrieved via `context.getBean(...)`; this is the condition for calls to pass through the Spring proxy. In real applications, you can separate `@Configuration` and `@Service` into separate files, using `@ComponentScan` or Spring Boot configuration.

**Note:** `DriverManagerDataSource` is suitable for short demos; production applications should use a properly configured connection pool. The H2 accounts and balances here are dummy data for observing transaction boundaries.

### 4.3. Running the Example and Checking Output

In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.tx.EnableTxDemo
```

The main lines printed by the program (excluding tool/startup logs):

```text
INIT: A=100, B=100
IN_TRANSACTION=true
AFTER_COMMIT: A=70, B=130
IN_TRANSACTION=true
EXPECTED_ERROR=simulated failure
AFTER_ROLLBACK: A=70, B=130
```

**Explanation of each milestone:**

1. `AnnotationConfigApplicationContext(TxConfig.class)` loads `@EnableTransactionManagement`, the beans, and transaction infrastructure.
2. Calling `service.transfer(..., false)` goes through the proxy. Spring opens a transaction before entering the method body, so `IN_TRANSACTION=true`. Both `UPDATE` statements succeed; the interceptor commits when the method ends normally. A decreases by 30, B increases by 30.
3. Calling `service.transfer(..., true)` also runs inside a transaction. The `UPDATE` deducting 20 has been executed inside the transaction, and then `IllegalStateException` is thrown. Since this is a `RuntimeException`, the interceptor rolls back under default rules; both balances remain **unchanged**.
4. `printBalances(...)` is called from `main` after the proxied call finishes; the final read confirms the effect of commit/rollback.

`TransactionSynchronizationManager.isActualTransactionActive()` is a way to observe an active transaction on the current thread; **a single `true` line alone does not prove a commit succeeded**. You must inspect data state after the transaction boundary, as in this example.

### 4.4. Control Experiment: What Happens If Not Enabled?

Only in a test project, temporarily remove `@EnableTransactionManagement` from `TxConfig` and re-run. With no other component activating transaction advice, `@Transactional` does not create a transaction proxy:

- `IN_TRANSACTION` will be `false`.
- Individual `JdbcTemplate.update(...)` statements run with H2's JDBC auto-commit.
- The failed transfer after the debit statement will leave state **A=50, B=130**: A was deducted an extra 20 while B never received the money.

This before–after experiment demonstrates the actual function of `@EnableTransactionManagement`. **Do not perform this kind of test on real data.** After the experiment, add the annotation back to restore transaction management.

## 5. Reading Configuration Correctly: Three Conditions Must All Hold

### 5.1. The Annotation Is Processed in the Right `ApplicationContext`

Place `@EnableTransactionManagement` on a configuration class that is **actually loaded by Spring**. A class with the annotation that is not scanned/imported/registered into the container has no effect.

Transaction annotation infrastructure processes beans within **the same ApplicationContext**. In classic web applications with a root context and a child `DispatcherServlet` context, configuration placed in the controller's context may not apply to service beans belonging only to the root context. Place the configuration in the context that owns the service or structure contexts appropriately.

### 5.2. A Compatible Transaction Manager Exists

The demo registers:

```java
@Bean
public PlatformTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

The name `transactionManager` keeps configuration easy to understand, especially when starting out. If there are **multiple transaction managers**, explicitly specify which manager a method uses, for example:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void createOrder() {
    // Transaction on resources managed by ordersTransactionManager.
}
```

This is only an **illustration of selecting a manager**, not a standalone runnable method. You can also select a default manager via `TransactionManagementConfigurer` when configuration requires it. Do not assume `@EnableTransactionManagement` guesses the right manager among multiple DataSources or automatically creates a distributed transaction across multiple databases.

### 5.3. Calls Must Go Through the Spring Proxy

Two usages look similar yet have different semantics:

```java
MoneyService managed = context.getBean(MoneyService.class);
managed.transfer(1, 2, 10, false); // Goes through Spring bean/proxy

MoneyService unmanaged = new MoneyService(jdbc);
unmanaged.transfer(1, 2, 10, false); // Manually created object, no transaction proxy
```

This is **illustrative code**, not part of the flow in section 4; do not execute both lines on the same data and treat the result as the demo. A call through `new` does not get transaction advice applied by the container. Similarly, in proxy mode, calling `this.inner()` within the same object will not go through the proxy: `inner()`'s own transaction annotation is not processed for that call. If the outer method is already in a transaction, `inner()`'s operations can still **participate in the outer transaction**; what is bypassed is `inner()`'s own boundary/advice.

## 6. What Options Does `@EnableTransactionManagement` Have?

| Option | Default | Meaning |
| --- | --- | --- |
| `mode` | `AdviceMode.PROXY` | Uses AOP proxies; only intercepts calls passing through the proxy. |
| `proxyTargetClass` | `false` | Prefers interface-based proxies when suitable interfaces exist; if there are no interfaces, class-based proxies may still be used. |
| `order` | `Ordered.LOWEST_PRECEDENCE` | Precedence of transaction advice relative to other advice. |

Example requesting class-based proxies:

```java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
class TxConfig {
    // @Bean DataSource, PlatformTransactionManager, service...
}
```

This is an **option illustration snippet**, not a replacement for the entire `TxConfig` in the demo. `proxyTargetClass=true` is useful when class-based proxies are needed, yet it **does not cure self-invocation**; `final` methods/classes also cannot be overridden by a proxy class to apply advice. For common designs, place `@Transactional` on public methods of concrete service classes.

`AdviceMode.ASPECTJ` is an advanced option using weaving and the `spring-aspects` module, requiring actual compile-time/load-time weaving configuration; changing `mode` alone without weaving **is not enough**. In a first-transaction lesson, the default proxy mode is the right choice.

## 7. Does Spring Boot Need You to Add `@EnableTransactionManagement` Manually?

**Distinguish two ways of setting up a project:**

- **Plain Spring Framework:** when using transaction annotations, you typically declare `@EnableTransactionManagement` and a `PlatformTransactionManager` bean explicitly as in this demo.
- **Spring Boot:** with JDBC/JPA starters and matching auto-configuration conditions, Boot normally auto-configures a transaction manager and activates transaction annotation processing. Therefore, most Boot projects **do not need to add `@EnableTransactionManagement`** just to use `@Transactional`.

If a Boot application already has transaction management configured, mechanically adding the annotation will not fix a missing `DataSource`, wrong manager selection, or proxy-bypass calls. When there are multiple datasources, managers, or custom transaction advice, inspect the actual configuration instead of inferring from the annotation's presence.

## 8. Common Mistakes and How to Handle Them

| Symptom | Cause to Check | How to Fix |
| --- | --- | --- |
| `@Transactional` is present, yet an error between two SQL statements leaves data half-updated | Transaction advice is not enabled or object was created via `new`/bypassed proxy. | Verify JavaConfig is loaded, retrieve service from container, and test rollback. |
| Transaction manager not found at runtime | No matching manager bean registered; multiple managers exist without explicit selection. | Create `PlatformTransactionManager`; select the right one via qualifier/`transactionManager` if needed. |
| Service in one context, `@EnableTransactionManagement` in another | Infrastructure only scans transaction annotations on beans in the context containing the configuration. | Place configuration in the ApplicationContext that owns the service. |
| Annotation on `private`/`final` method or calling `this.inner()` | Proxy cannot intercept the call/method as desired. | Place transaction boundary on public service methods, call via another bean/proxy; do not rely on self-invocation. |
| `@Transactional` placed on an interface and proxy type changed | Annotation detection depends on proxy/weaving mode and configuration. | Prefer annotating methods on the concrete class. |
| Using `JdbcTransactionManager` with a different `DataSource` than `JdbcTemplate` | SQL operation's connection may not participate in the transaction controlled by the manager. | Ensure the same `DataSource` resource, and use Spring JDBC/DataSourceUtils properly. |
| Expecting every exception to roll back | Default rules roll back on `RuntimeException` and `Error`; checked exceptions do not auto-rollback. | Use `@Transactional(rollbackFor = SomeCheckedException.class)` when business rules require it. |
| Initializing bean with `@PostConstruct` and calling a transactional method | Proxy may not yet be ready to apply advice during initialization. | Run business logic after container initialization, via service bean/proxy. |
| Seeing `IN_TRANSACTION=true` yet other data remains uncommitted | Transaction is still open or method merely joined an outer transaction; displayed output does not reflect final commit yet. | Identify the outer transaction boundary and observe data after it finishes. |

### Two Notes to Avoid Wrong Conclusions

**One:** Spring defaults to `Propagation.REQUIRED`. If an outer transaction already exists, an inner `@Transactional` call normally joins that transaction; the inner method returning **does not mean** the physical transaction has committed.

**Two:** Regular JDBC transactions are bound to the executing thread. Do not assume that spawning a new thread, using `@Async`, or switching to reactive processing carries the transaction context along automatically. For reactive transactions, Spring uses `ReactiveTransactionManager` and the Reactor context, not the thread-bound JDBC model from this demo.

## 9. Checklist Before Considering Transactions Successfully Enabled

1. The `@Configuration` class with `@EnableTransactionManagement` is registered in the ApplicationContext containing the service.
2. A `PlatformTransactionManager` matching the technology and datasource exists; when multiple managers exist, selection is explicit.
3. The service is a Spring bean called externally via proxy; the transactional method is an appropriate business entry point.
4. Both a commit case and a case throwing `RuntimeException` **after at least one SQL statement** have been tested, observing the final DB state for rollback.
5. Do not treat `save()` return values, logs before `return`, or `isActualTransactionActive()` as sole proof of **successful commit**.
6. With Spring Boot, verify whether auto-configuration already enables it or custom configuration is needed before adding the annotation.

## 10. Self-Check Questions

**Question 1.** Using `@Transactional` only on a class instantiated with `new`, with no Spring context. Is there a Spring-managed transaction?

**Answer:** No. The annotation is only metadata; the object is not a Spring-managed bean/proxy.

**Question 2.** Adding `@EnableTransactionManagement` without creating any transaction manager. Can JDBC `@Transactional` work properly right away?

**Answer:** No. A matching manager is required to open/commit/roll back transactions. An error may only appear when the `@Transactional` call is executed.

**Question 3.** The demo calls `transfer(...)` through a bean and throws `IllegalStateException` after the debit statement. Why isn't A deducted by 20?

**Answer:** `IllegalStateException` is an unchecked exception; Spring's transaction interceptor rolls back the same JDBC transaction that contained the `UPDATE` statement.

**Question 4.** Why does a Spring Boot project use `@Transactional` even though `@EnableTransactionManagement` does not appear in source code?

**Answer:** Boot may have already enabled and configured transaction infrastructure via auto-configuration for the corresponding starter/resources. Check the actual setup.

## Key Takeaway

**`@EnableTransactionManagement` enables transaction annotation processing; `@Transactional` describes business boundaries; `PlatformTransactionManager` executes the transaction; the Spring proxy is the path through which the interceptor applies the transaction.** Verify with a real rollback test, not merely by checking that code compiles or carries an annotation.

## Official References

- Spring Framework 6.2 — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- Spring Framework — [Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- Spring Framework — [Spring AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- Spring Framework — [`@EnableTransactionManagement` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.5/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html)
