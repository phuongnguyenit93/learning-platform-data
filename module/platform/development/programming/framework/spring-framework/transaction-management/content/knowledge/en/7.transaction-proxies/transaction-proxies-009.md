# Bean Initialization Timing and Limitations of `@PostConstruct` with Spring Transactional Proxies

## Goal

This lesson explains why `@Transactional` is not guaranteed to open a transaction while a Spring bean is being initialized, especially inside `@PostConstruct`. After studying it, you will be able to identify callback order and when proxies take effect, distinguish lifecycle bugs from self-invocation, observe transactions with Java 17 + Spring JDBC, and choose the right time to run transactional logic after the application context is ready.

**Main idea:** in the default **Spring AOP proxy** mode, only eligible method calls **entering from outside through a ready proxy** are intercepted by the transaction interceptor. `@PostConstruct` is invoked by the container during target bean initialization, when you cannot rely on that bean's own transactional proxy.

## 1. `@Transactional` Depends on Going Through a Proxy

With `@EnableTransactionManagement` (or corresponding Boot auto-configuration), Spring applies AOP proxies to eligible beans. When another bean calls a `@Transactional` public method through a proxy reference, Spring runs `TransactionInterceptor`, selects a `PlatformTransactionManager` for JDBC/JPA, begins/joins a transaction, invokes the target, and commits or rolls back depending on the outcome. The scope of this lesson is **imperative** transactions, though proxy-creation timing principles also matter when applying reactive transactions.

```text
Caller
  |
  v
Spring AOP proxy -- TransactionInterceptor
  |                        |
  |                        +--> TransactionManager:
  |                             begin/join, commit/rollback
  v
TargetBean.transactionalMethod()
```

`@Transactional` is metadata; it does not automatically turn an ordinary Java call into a transaction. For advice to run, at minimum you need: transaction management enabled, a suitable transaction manager, an eligible method interceptable by the proxy, and a caller actually going through the proxy.

Two distinct bugs are easily confused:

1. **Wrong timing:** the callback runs while the target is still initializing, before the proxy is published/finalized.
2. **Wrong call path:** `this.otherMethod()` calls internally on the target; even after the bean finishes initializing, it still bypasses the proxy.

Fixing the first bug does not automatically fix the second.

## 2. Bean Lifecycle: `@PostConstruct` Runs Before Normal Proxy Creation

For a typical singleton, a reasonable diagram is:

```text
1. Constructor: create target bean
       |
2. Dependency injection: populate fields/constructor/properties
       |
3. BeanPostProcessor.postProcessBeforeInitialization
       |  CommonAnnotationBeanPostProcessor invokes @PostConstruct
       |
4. InitializingBean.afterPropertiesSet() (if implemented)
       |
5. Custom init-method (if configured)
       |
6. BeanPostProcessor.postProcessAfterInitialization
       |  AOP auto-proxy creator typically creates/returns proxy
       |
7. Bean is published under its complete reference
       |
8. Another bean calls method through proxy
       |  TransactionInterceptor can apply @Transactional
```

This is the general order for standard cases; not every edge case with bean scopes, custom bean post-processors, or circular dependencies is identical. Nevertheless, Spring explicitly documents that initialization callbacks execute on the **raw bean reference** before AOP interceptors are applied; the proxy needs to be complete for transactions to behave as expected.

`CommonAnnotationBeanPostProcessor` recognizes `jakarta.annotation.PostConstruct`; Spring Framework 6+ uses the `jakarta.annotation` namespace rather than the `javax.annotation` package common in older Spring 5 code. `@PostConstruct` is usually a no-arg method returning `void`, invoked once by the container per bean creation lifecycle (beans may be recreated depending on scope/context).

During singleton initialization, Spring uses internal locking/coordination mechanisms. Spring documentation recommends using `@PostConstruct` to validate configuration and prepare local state; calling other beans, slow DB tasks, asynchronous preparation, or external system interactions can cause slow startup or deadlocks.

| Execution point | Calling on target or proxy? | Can `@Transactional` on the callback itself be trusted? |
|---|---|---|
| Constructor | Target under construction | No |
| `@PostConstruct` | Lifecycle processor invokes target | **No** |
| `InitializingBean.afterPropertiesSet()` | Initialization callback on target | **No** |
| Custom `init-method` | Initialization callback on target | **No** |
| Call from another bean after context refresh | Spring proxy reference | Yes, if manager and method are valid |
| `this.save()` inside the same bean | Direct target call | No, in proxy mode |
| Runner/event listener calling **another** proxied service | Service called through proxy | Yes, if properly configured |

Another bean already created might have a proxy even while the current bean is still initializing, yet you should not turn bean dependency creation order into an implicit transaction mechanism for callbacks. Transaction boundaries should be designed explicitly.

## 3. Why Are These Two `@PostConstruct` Patterns Wrong?

### 3.1. Putting `@Transactional` directly on `@PostConstruct`

```java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class UnsafeStartup {
    @PostConstruct
    @Transactional
    public void initialize() {
        // Never assume this code runs inside a Spring transaction.
    }
}
```

This snippet **illustrates a bug** and is not a standalone Java program. The lifecycle processor calls `initialize()` while initializing the raw target. Even though the annotation is present, Spring does not guarantee interception at this point. With JDBC, if the connection is auto-committing, write operations can commit individually; an exception halfway through will not undo earlier writes merely because the method has `@Transactional`.

### 3.2. Calling one's own transactional method from `@PostConstruct`

```java
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AlsoUnsafe {
    @PostConstruct
    public void init() {
        this.seedData();
    }

    @Transactional
    public void seedData() {
        // Calling this.seedData() does not go through the Spring AOP proxy.
    }
}
```

This is **self-invocation**. `this.seedData()` is a call on the same target instance, bypassing the transaction interceptor. The bug persists even after startup completes—for instance, if a `process()` method on the same bean calls `this.seedData()`. Do not view this solely as a "`@PostConstruct` runs too early" bug.

## 4. Java 17 Experiment: Same Method, Different Outcomes Between Proxy and Self-Invocation

The complete example below uses Spring Framework 6.2, in-memory H2, and Spring JDBC. It intentionally puts an INSERT into a method that always throws `IllegalStateException` to contrast rollbacks:

- External call through the proxy has a transaction: the INSERT rolls back, row count is 0.
- Internal call via `this` has no transaction: H2/JDBC auto-commits the INSERT, row count is 1.
- Inside `@PostConstruct`, even though the method has `@Transactional`, actual transaction status is still `false`.

### 4.1. Project structure

```text
spring-tx-initialization/
├── pom.xml
└── src/main/java/com/example/txinit/Main.java
```

### 4.2. File `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-tx-initialization</artifactId>
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
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides the application context and related AOP infrastructure; `spring-jdbc` provides `JdbcTemplate` and `JdbcTransactionManager`. H2 serves as the sample database, and `jakarta.annotation-api` supplies `@PostConstruct` on JDK 17. Dependency versions are pinned to reproduce the example; real projects should use a BOM/version-update process.

### 4.3. File `src/main/java/com/example/txinit/Main.java`

```java
package com.example.txinit;

import jakarta.annotation.PostConstruct;
import javax.sql.DataSource;

import org.springframework.aop.support.AopUtils;
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

public class Main {

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:txinit;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public LedgerService ledgerService(JdbcTemplate jdbc) {
            return new LedgerService(jdbc);
        }
    }

    public static class LedgerService {
        private final JdbcTemplate jdbc;

        public LedgerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @PostConstruct
        @Transactional
        public void initialize() {
            System.out.println("init transaction=" + txActive());
            this.printTx("init self-call");
        }

        @Transactional
        public void printTx(String source) {
            System.out.println(source + " transaction=" + txActive());
        }

        @Transactional
        public void insertThenFail(String label) {
            System.out.println(label + " insert transaction=" + txActive());
            jdbc.update("INSERT INTO tx_log(label) VALUES (?)", label);
            throw new IllegalStateException("planned failure");
        }

        public void selfInvoke() {
            try {
                this.insertThenFail("self");
            } catch (IllegalStateException ex) {
                System.out.println("self error=" + ex.getMessage());
            }
        }

        private static boolean txActive() {
            return TransactionSynchronizationManager.isActualTransactionActive();
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE tx_log (" +
                "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
                "label VARCHAR(40) NOT NULL)"
            );

            LedgerService service = context.getBean(LedgerService.class);
            System.out.println("proxy=" + AopUtils.isAopProxy(service));

            service.printTx("external");

            try {
                service.insertThenFail("external");
            } catch (IllegalStateException ex) {
                System.out.println("external error=" + ex.getMessage());
            }

            System.out.println("rows after external=" +
                jdbc.queryForObject("SELECT COUNT(*) FROM tx_log", Integer.class));

            service.selfInvoke();

            System.out.println("rows after self=" +
                jdbc.queryForObject("SELECT COUNT(*) FROM tx_log", Integer.class));
        }
    }
}
```

**Mechanism in the example:**

1. `@EnableTransactionManagement(proxyTargetClass = true)` chooses class-based proxies so no interface is needed; this attribute **does not make `this` calls transactional**.
2. `JdbcTemplate` and `JdbcTransactionManager` share the same `DataSource`; `transactionManager` is the default bean name Spring recognizes.
3. `@PostConstruct initialize()` is invoked before the normal proxy can intercept calls, so both `initialize()` and `this.printTx(...)` see `false`.
4. After the context finishes initializing, `getBean(LedgerService.class)` returns the proxy; `printTx("external")` and `insertThenFail("external")` get a transaction opened by the interceptor and see `true`.
5. The unchecked exception from `insertThenFail("external")` exits through the interceptor, triggering rollback. Count is 0.
6. `selfInvoke()` is non-transactional; it calls `this.insertThenFail("self")` on the target. With no transaction and JDBC auto-commit, the INSERT persists even though the exception is caught. Count is 1.

### 4.4. Run and compare output

In the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.txinit.Main
```

Lines printed by the program itself in the example (any Maven/driver logs are omitted):

```text
init transaction=false
init self-call transaction=false
proxy=true
external transaction=true
external insert transaction=true
external error=planned failure
rows after external=0
self insert transaction=false
self error=planned failure
rows after self=1
```

This experiment **intentionally writes data outside a transaction** to demonstrate the risk. Do not put `selfInvoke()` into real business code. With JPA, writing without a transaction may fail or have different semantics than JDBC auto-commit; do not extrapolate H2/JDBC results to every provider.

## 5. Correct Ways to Implement Transactional Data Initialization

**Principle:** designate one bean as the *post-startup* trigger and another bean containing the `@Transactional` method. Spring injects the service bean's proxy reference into the trigger bean, so the external call is intercepted properly.

### 5.1. Spring Boot: `ApplicationRunner` or `CommandLineRunner`

```java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class SeedService {
    @Transactional
    public void seed() {
        // JDBC/JPA steps that must commit/roll back together.
    }
}

@Component
class SeedRunner implements ApplicationRunner {
    private final SeedService seedService;

    SeedRunner(SeedService seedService) {
        this.seedService = seedService;
    }

    @Override
    public void run(ApplicationArguments args) {
        seedService.seed();
    }
}
```

These are **two sample classes in a Spring Boot application**, not a standalone Java program. They require Boot, a datasource, a transaction manager, actual business logic, and component scanning registration. `ApplicationRunner` runs after context refresh, before `SpringApplication.run(...)` finishes. `CommandLineRunner` is similar but takes string arguments. Spring Boot recommends running startup tasks via runners rather than `@PostConstruct`.

For critical startup jobs, decide whether a failure should fail startup, how idempotency works across restarts, and execution time limits. If a task runs before readiness, the service should not accept traffic depending on seeded data yet; never assume a job runs "once forever", because redeploys/restarts run it again.

### 5.2. Plain Spring Framework: `ContextRefreshedEvent`

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class StartupService {
    @Transactional
    public void prepareDatabaseState() {
        // Logic requiring a transaction.
    }
}

@Component
class ContextReadyHandler {
    private final StartupService service;

    ContextReadyHandler(StartupService service) {
        this.service = service;
    }

    @EventListener(ContextRefreshedEvent.class)
    public void onRefresh() {
        service.prepareDatabaseState();
    }
}
```

These illustrative classes need a context with component scanning and transaction management. `ContextRefreshedEvent` fires after regular singletons are created, so calling through `StartupService`'s proxy is a clean approach.

Prepare for the event possibly firing multiple times on context refresh, or in setups with parent/child contexts. If true once-only semantics per DB are needed, use unique constraints/migration tables/locks or idempotency checks instead of storing a flag field in a bean.

### 5.3. When to use other options?

- `SmartInitializingSingleton.afterSingletonsInstantiated()` runs after **regular singletons** finish initializing, useful when all beans must be observable; it does not guarantee lazy beans have been created, and you should not put `@Transactional` directly on the callback expecting proxy interception.
- `ApplicationReadyEvent` in Boot fires **after runners**. It is a later lifecycle event suited for work that truly needs to wait until the application is ready; avoid using it for migrations that must finish before serving requests.
- For versioned schema migrations and seed data, prefer Flyway/Liquibase or an equivalent migration tool instead of writing extensive DDL in `@PostConstruct`.
- `TransactionTemplate` can open a transaction directly without a proxy, yet overusing it inside `@PostConstruct` still risks bean creation locks, dependency cycles, and infrastructure ordering issues. Use it only when lifecycle is well controlled and programmatic transactions are truly needed.

## 6. Changes Commonly Mistaken for Fixes

| Change | Why it does not solve the problem |
|---|---|
| Putting `@Transactional` on `@PostConstruct` | Callback still runs before normal AOP proxies intercept methods |
| Making the callback `public` | Visibility may be needed for AOP, yet does not change callback timing |
| Enabling `@EnableTransactionManagement(proxyTargetClass = true)` | Only changes proxy type; does not fix lifecycle timing or self-invocation |
| Adding `@DependsOn("transactionManager")` | Only sets dependency creation order; manager existence does not wrap the callback in an interceptor |
| Enabling `@Lazy` | Defers bean creation, yet its `@PostConstruct` still runs during target lifecycle |
| Injecting the bean's own proxy back into itself | Prone to circular dependencies and init-order fragility; extracting a separate bean is safer |
| Using `this.save()` after startup | Proxy bypass still occurs even after the bean is fully initialized |
| Marking a `private`/`final` method transactional | Proxies do not intercept private methods; class-based proxies cannot override final methods |
| Switching straight to `mode=ASPECTJ` | Weaving can handle self-invocation yet needs extra setup/dependencies and different semantics; not the default way to run I/O in init callbacks |

For Spring Framework 6+, class-based proxies can support protected/package-visible transactional methods under default configuration; JDK interface-based proxies require public interface methods. Even so, the best pattern remains public methods on a service called from another bean after startup.

## 7. Debugging, Testing, and Identifying Bugs

**Verify proxy presence:** once the context is ready, check `AopUtils.isAopProxy(bean)`. Getting `true` does not prove internal self-calls inside that bean went through advice.

**Verify an actual transaction:** in the imperative JDBC part of the example, call `TransactionSynchronizationManager.isActualTransactionActive()` inside the method. Do not confuse it with `isSynchronizationActive()`: synchronization can be active when no actual transaction is active. This mechanism is thread-based and cannot be used directly to reason about reactive transactions with their own context.

**Test real rollbacks:** use an integration test that writes a record and throws `RuntimeException`; afterward, query the DB via a separate operation/transaction. Compare proxy calls against self-calls via `this.method()`. When testing a service inside a transaction already opened by the test framework, `isActualTransactionActive() = true` may merely reflect the outer test transaction, so design independent tests to verify the method actually opens/joins a transaction as intended.

**Check configuration:** is `@EnableTransactionManagement` or `<tx:annotation-driven/>` enabled; does the transaction manager govern the same datasource used by the repository; is the method invoked through a Spring-managed bean; do `final`/`private` modifiers block proxying; is an exception caught and swallowed inside the method?

**Logging:** depending on the version, enable DEBUG/TRACE on `org.springframework.transaction.interceptor` and the corresponding transaction manager to observe begin/commit/rollback. Do not treat logs as sole proof; database state after rollback is a more reliable check.

### Self-check questions

1. Is `@Transactional` on `@PostConstruct` enough to roll back SQL statements inside the callback? **No**, because the callback runs on the raw target during initialization.
2. Why doesn't `this.save()` in the same bean open a transaction in proxy mode? **Because it does not go through the proxy**.
3. Can `@DependsOn("transactionManager")` fix this? **No**, it only dictates dependency order.
4. Why is an `ApplicationRunner` bean calling `seedService.seed()` effective? **Because the runner executes after refresh and calls through another service bean's proxy**.
5. What is the clearest way to verify? **Have the method write and throw an error, confirm an actual transaction, and inspect data after rollback using an independent DB operation**.

## Official Documentation

- Spring Framework — Using `@Transactional`, proxies, and `@PostConstruct` limitations: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Customizing the Nature of a Bean, lifecycle callbacks, and bean initialization locks: https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html
- Spring Framework — Using `@PostConstruct` and `@PreDestroy`: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/postconstruct-and-predestroy-annotations.html
- Spring Framework — Understanding Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Boot — SpringApplication lifecycle, runners, and readiness: https://docs.spring.io/spring-boot/reference/features/spring-application.html
