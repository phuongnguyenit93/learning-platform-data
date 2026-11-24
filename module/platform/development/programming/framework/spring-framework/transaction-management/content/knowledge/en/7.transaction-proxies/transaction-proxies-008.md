# Objects Created with `new` and Calls Outside the Spring Container

## 1. The Problem: `@Transactional` Is Present Yet Rollback Still Does Not Happen

In Spring Framework, a Java class may contain a `@Transactional` method and the application may already have a configured transaction manager, yet when that method is called, **no transaction is created by Spring**. A very common reason is creating the object with `new` and calling it directly instead of using a **Spring bean reference wrapped by a transaction proxy**.

Example:

```java
@Service
public class PaymentService {
    @Transactional
    public void pay() {
        // Debit funds and save order.
    }
}

// Elsewhere:
PaymentService payment = new PaymentService();
payment.pay();
```

The snippet above only **illustrates the principle** and is not a standalone compilable program. If `PaymentService` has constructor dependencies, the `new` call would need to supply them. More importantly, `payment` here is a plain object: Spring did not instantiate it, inject dependencies, apply lifecycle callbacks, or **create a transaction AOP proxy** for the newly constructed reference. The annotation on the class does not run the transaction interceptor by itself.

However, one case must be distinguished: **having a caller outside the Spring container does not necessarily prevent transactions**. A plain class created via `new` can still successfully call into a `@Transactional` bean, provided it holds the **actual proxy reference supplied by Spring**:

```java
PaymentService bean = context.getBean(PaymentService.class);
ExternalJob job = new ExternalJob(bean); // Caller is created with new.
job.execute();                           // Caller invokes through the bean proxy.
```

This snippet is **illustrative**; it needs `context` and a suitable `ExternalJob` class. Because `job` holds a reference to `bean` managed and proxied by Spring, the method call can still be intercepted. Where the caller is created and where the **target service** is created are two separate questions.

**Lesson goal:** accurately identify which object/reference is managed by Spring, check whether the call passes through a proxy, and practice with a demo showing the data difference between direct `new` calls and bean proxy calls.

## 2. How Does Spring Manage Beans and Proxies?

`@Transactional` is **metadata** describing a transaction policy. In the default `AdviceMode.PROXY` mode, a transaction activates when:

1. The class or method has matching `@Transactional` metadata.
2. The bean is registered/instantiated in a Spring `ApplicationContext` with annotation-driven transaction management infrastructure (such as `@EnableTransactionManagement` or appropriate auto-configuration).
3. A `TransactionManager` suitable for the managed resource exists.
4. The caller actually invokes an advisable method through the **proxy reference** created by Spring.
5. Data operations use the right resource participating in the transaction governed by the manager.

Spring typically uses a **Spring AOP proxy**: a JDK dynamic proxy when proxying interfaces, or a class-based proxy for classes without a suitable interface. The transaction interceptor runs **before** the method body to open/join the transaction and **after** the method body to commit/roll back.

```text
                      SPRING APPLICATION CONTEXT
                     +---------------------------+
                     |  Bean definition          |
                     |  @EnableTransactionManagement
                     |  TransactionManager       |
                     |       |                   |
                     |       v                   |
Caller ------------->|  Transaction proxy        |
                     |       |                   |
                     |       v                   |
                     |  PaymentService target    |
                     +---------------------------+
                              |
                              v
                       JDBC/JPA operations

Caller -> new PaymentService() -> target method
         (bypasses Spring's transaction proxy)
```

If you directly invoke `new PaymentService(...)`, the interceptor never gets a chance to run. This **does not mean** every JDBC statement inside will fail: SQL statements can still execute normally and commit individually. Bugs typically surface only when a group of operations needs to roll back.

### 2.1. Distinguishing three concepts

| Concept | Question to answer |
| --- | --- |
| Who created the object? | Ad-hoc `new` in application code, or admitted into Spring's bean lifecycle? |
| What is the current reference? | Plain target or a **proxy** returned by BeanFactory? |
| Where is the caller? | Inside a Spring bean, in `main()`, a listener, job, servlet, or external library? |

**The reference** is the decisive factor at call time. A caller in any Java class can use a proxy returned by `ApplicationContext.getBean(...)` or injected via constructor. Conversely, a Spring-managed bean can instantiate a target with `new` and call it directly, leaving the new target's methods unhandled by Spring AOP.

## 3. Real-World Cases to Distinguish

### 3.1. Creating an annotated service with `new` right inside a method

```java
public class CheckoutCoordinator {
    public void checkout() {
        PaymentService service = new PaymentService();
        service.pay();
    }
}
```

This is a **condensed illustration**, assuming `PaymentService` has a no-arg constructor. With a freshly `new`-ed `service`, the annotation does not turn the method call into a proxied call. If `pay()` runs two write statements on an auto-committing JDBC connection, they can commit independently; a failure on the second step will not automatically undo the first step.

**Fix:** register `PaymentService` as a Spring bean and inject/reference the **managed bean**. Use constructor injection when `CheckoutCoordinator` also belongs to Spring:

```java
@Service
public class CheckoutCoordinator {
    private final PaymentService paymentService;

    public CheckoutCoordinator(PaymentService paymentService) {
        this.paymentService = paymentService;
    }

    public void checkout() {
        paymentService.pay(); // Reference injected by Spring.
    }
}
```

This is an **illustrative class**; `PaymentService` is a bean registered in the context, transaction infrastructure must be enabled, and calling `pay()` must satisfy interception conditions. Prefer constructor injection so dependencies are explicit.

### 3.2. A Spring bean creating another object with `new`

```java
@Service
public class CheckoutCoordinator {
    public void checkout() {
        PaymentService local = new PaymentService();
        local.pay();
    }
}
```

Even though `CheckoutCoordinator` is managed by the container, `local` is still a plain object. **A parent bean does not automatically confer container management** onto objects created inside its code via `new`. If you need multiple managed instances, use an appropriate scope, factory bean, or `ObjectProvider<PaymentService>`. `provider.getObject()` obtains the object through Spring and allows relevant `BeanPostProcessor`s/proxies to participate.

### 3.3. A `@Bean` method returning an object created with `new`

Do not infer that **every occurrence of the `new` keyword is wrong**:

```java
@Configuration
@EnableTransactionManagement
public class AppConfig {

    @Bean
    PaymentService paymentService() {
        return new PaymentService(); // Spring registers this object as a bean.
    }
}
```

This is an **illustrative configuration**, needing a `PaymentService()` constructor and a properly configured transaction manager. Here, **Spring invokes the `@Bean` factory method and manages the result**. When the bean is created, a `BeanPostProcessor` can still apply a transaction proxy before the bean is supplied to callers via `getBean`/injection. An object `new`-ed **inside a `@Bean` method** is different from one `new`-ed inside an arbitrary method and kept as a local reference.

However, if you **manually call** `new AppConfig().paymentService()` outside Spring, that result is not automatically registered in the container. Never call configuration factory methods directly as a way to obtain beans. Always retrieve dependencies through Spring.

### 3.4. Caller created outside Spring yet invoking the right proxy

A console program, batch runner, Java listener, legacy servlet, or third-party library object might not be created by Spring. It can still call into a transactional service if it receives the **proxy reference**:

```java
public final class ExternalRunner {
    private final PaymentService service;

    public ExternalRunner(PaymentService service) {
        this.service = service;
    }

    public void run() {
        service.pay();
    }
}

// Example after the ApplicationContext has been initialized:
PaymentService proxy = context.getBean(PaymentService.class);
new ExternalRunner(proxy).run();
```

The statements after the class are an **illustrative usage snippet**, not a standalone Java file; an actual `context` and matching bean are required. Even though `ExternalRunner` is created with `new`, `service.pay()` passes through the proxy reference, so transaction advice can run. Spring AOP **does not require the caller itself to be a Spring bean**; it requires the call to the target needing interception to go through the proxy.

Another broken variant:

```java
PaymentService raw = new PaymentService();
new ExternalRunner(raw).run(); // External caller holds a raw target.
```

This time `ExternalRunner` cannot compensate for the missing proxy on `raw`. So inspect **the object passed in**, instead of merely asking whether the caller has `@Component`.

### 3.5. `@Autowired` on an object created with `new`

Field injection does not run automatically on manually constructed objects:

```java
@Service
public class EmailProcessor {
    @Autowired
    private PaymentService paymentService;

    public void process() {
        paymentService.pay();
    }
}

// Wrong if constructing manually and expecting Spring to inject the field:
EmailProcessor processor = new EmailProcessor();
processor.process(); // paymentService may be null.
```

This is **illustrative code** and should not be run verbatim as a standalone app. `@Autowired` requires Spring to perform injection. On a plain `new` object, the field is never populated. Constructor injection forces the caller to supply dependencies; if the dependency is a Spring proxy, calls through it can be intercepted even when the caller itself is unmanaged.

Some advanced APIs like `AutowireCapableBeanFactory` can process dependencies/lifecycle of an existing object, yet **merely autowiring an object does not guarantee you end up using the created transaction proxy**. If you do use advanced bean initialization APIs, you must distinguish the **original target** from the **reference returned after post-processing**. In normal cases, the clearest path is registering the bean with Spring and obtaining it from the container.

## 4. Runnable Demo: Same `@Transactional`, Different Rollback Outcomes

The example uses **Java 17+, Maven, Spring Framework 6.2.8, Spring JDBC, and H2 2.3.232**. It is a standalone project requiring neither Spring Boot nor an HTTP server. We keep the same `@Transactional` method and test four call paths:

1. **Raw target:** service created manually via `new` → no proxy → both UPDATEs auto-commit.
2. **Spring bean:** service obtained via `context.getBean(...)` → calls proxy → exception triggers rollback.
3. **External caller:** caller created manually via `new` but passed the Spring bean proxy → rollback still works.
4. **Raw target + `TransactionTemplate`:** service remains a plain object, yet a transaction is **opened programmatically outside** → rollback works even though the annotation on the raw target is not processed by Spring AOP.

The lab intentionally throws an unchecked exception **after running two write operations**. Re-read the database after the error to see whether the two operations rolled back.

### 4.1. Project structure

```text
manual-new-transaction/
  pom.xml
  src/main/java/example/ProxyBoundaryDemo.java
```

### 4.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>manual-new-transaction</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
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
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.ProxyBoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` supplies `ApplicationContext`/bean configuration; `spring-jdbc` contains `JdbcTemplate` and `DataSourceTransactionManager`; `spring-tx` contains annotations and the transaction abstraction; H2 is an in-memory JDBC database. H2 is on the compile classpath because the code imports `org.h2.jdbcx.JdbcDataSource`.

### 4.3. `src/main/java/example/ProxyBoundaryDemo.java`

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class ProxyBoundaryDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            // Manually constructed object: same class, same JdbcTemplate, but no proxy.
            WalletService raw = new WalletService(jdbc);

            // @Bean in Config returns new WalletService(...);
            // Spring manages the result and can create a proxy.
            WalletService bean = context.getBean(WalletService.class);

            System.out.println(
                "Manual service proxy: " + AopUtils.isAopProxy(raw)
            );
            System.out.println(
                "Spring service proxy: " + AopUtils.isAopProxy(bean)
            );

            runCase(
                "manual new service",
                jdbc,
                () -> raw.transferAndFail(20)
            );

            runCase(
                "Spring-managed service",
                jdbc,
                () -> bean.transferAndFail(20)
            );

            ExternalCaller caller = new ExternalCaller(bean);
            runCase(
                "new caller with Spring proxy",
                jdbc,
                caller::execute
            );

            TransactionTemplate template = new TransactionTemplate(
                context.getBean(PlatformTransactionManager.class)
            );
            runCase(
                "manual service inside TransactionTemplate",
                jdbc,
                () -> template.executeWithoutResult(
                    status -> raw.transferAndFail(20)
                )
            );
        }
    }

    private static void runCase(
        String name,
        JdbcTemplate jdbc,
        Runnable action
    ) {
        reset(jdbc);
        System.out.println("CASE: " + name);

        try {
            action.run();
        } catch (IllegalStateException expected) {
            System.out.println("Caught: " + expected.getMessage());
        }

        Integer a = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = 1",
            Integer.class
        );
        Integer b = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = 2",
            Integer.class
        );
        System.out.println("Balances: A=" + a + ", B=" + b);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.execute("DROP TABLE IF EXISTS wallets");
        jdbc.execute(
            "CREATE TABLE wallets (" +
            "id INT PRIMARY KEY, balance INT NOT NULL)"
        );
        jdbc.update("INSERT INTO wallets(id, balance) VALUES (1, 100)");
        jdbc.update("INSERT INTO wallets(id, balance) VALUES (2, 50)");
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:manual_new_tx;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
            DataSource dataSource
        ) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public WalletService walletService(JdbcTemplate jdbcTemplate) {
            return new WalletService(jdbcTemplate);
        }
    }

    // Class can be proxied by Spring because it is public, non-final,
    // and its transactional method is public, non-final.
    public static class WalletService {
        private final JdbcTemplate jdbc;

        public WalletService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transferAndFail(int amount) {
            System.out.println(
                "Transaction active: " +
                TransactionSynchronizationManager.isActualTransactionActive()
            );

            if (amount <= 0) {
                throw new IllegalArgumentException("invalid amount");
            }

            int debitCount = jdbc.update(
                "UPDATE wallets " +
                "SET balance = balance - ? " +
                "WHERE id = 1 AND balance >= ?",
                amount, amount
            );
            int creditCount = jdbc.update(
                "UPDATE wallets " +
                "SET balance = balance + ? WHERE id = 2",
                amount
            );
            if (debitCount != 1 || creditCount != 1) {
                throw new IllegalStateException("update count invalid");
            }

            throw new IllegalStateException("simulated failure");
        }
    }

    // Caller is not a bean, yet holds a valid Spring proxy reference.
    public static class ExternalCaller {
        private final WalletService service;

        public ExternalCaller(WalletService service) {
            this.service = service;
        }

        public void execute() {
            service.transferAndFail(20);
        }
    }
}
```

**Demo design notes:**

- Both `raw` and `bean` have the underlying class `WalletService` and use the **same `JdbcTemplate` bean**. The difference does not lie in SQL statements, dependencies, or annotations.
- `WalletService` is a `public static` (non-`final`) class, and `transferAndFail()` is `public`. It implements no interface, so Spring can wrap the bean with a **class-based proxy** in the demo.
- `Config.walletService()` contains `new WalletService(jdbcTemplate)`. Because Spring calls the `@Bean` method to **register and finalize** the bean, Spring can create a proxy. Meanwhile `new WalletService(jdbc)` in `main()` creates a raw object outside the container.
- `@EnableTransactionManagement` enables transaction advice; `transactionManager` manages the same H2 datasource. `JdbcTemplate` uses the thread-bound transactional connection via Spring JDBC.
- `reset()` recreates the table and balances **before each case**, so all four cases start with A=100, B=50.
- The method intentionally debits 20 from A, credits 20 to B, checks row counts, and throws `IllegalStateException`. The exception is caught **on the caller side after crossing the boundary**, allowing the demo to proceed to the next case.

### 4.4. How to run

Place both files according to the directory tree. From `manual-new-transaction`, using JDK 17 or higher, Maven 3.9+, and repository connectivity to download dependencies on the first run:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Lines **printed by the program** (excluding Maven/Spring logs) in order:

```text
Manual service proxy: false
Spring service proxy: true
CASE: manual new service
Transaction active: false
Caught: simulated failure
Balances: A=80, B=70
CASE: Spring-managed service
Transaction active: true
Caught: simulated failure
Balances: A=100, B=50
CASE: new caller with Spring proxy
Transaction active: true
Caught: simulated failure
Balances: A=100, B=50
CASE: manual service inside TransactionTemplate
Transaction active: true
Caught: simulated failure
Balances: A=100, B=50
```

### 4.5. Explanation of each outcome

**Case 1 — `manual new service`:**

`raw` is a Java object created with `new` in `main()`, bypassing any transaction proxy. `TransactionSynchronizationManager.isActualTransactionActive()` returns `false` because the caller has opened no transaction. The two `UPDATE` statements are executed by `JdbcTemplate` on JDBC connections outside any Spring transaction; under the demo's H2 `JdbcDataSource` config, they auto-commit. The thrown exception **does not roll back already-committed statements**, leaving A=80, B=70. The demo happens not to lose the sum of balances because it intentionally fails after **both** writes; in real business logic, an error **between** two writes can leave far more dangerous half-finished data.

**Case 2 — `Spring-managed service`:**

`bean` is returned by `ApplicationContext` as a proxy. The interceptor opens a transaction before `transferAndFail` runs, so it prints `Transaction active: true`. Both `UPDATE`s join the same transaction. `IllegalStateException` is a `RuntimeException`, so `@Transactional` requests rollback by default; A=100, B=50 after the method throws. The bean gets a transaction not because `@Bean` avoided `new`, but because **Spring processes the object returned by `@Bean`**.

**Case 3 — `new caller with Spring proxy`:**

`ExternalCaller` is constructed manually with `new`, yet holds the **bean proxy**. Calling `service.transferAndFail(20)` from it still goes through the proxy, so a transaction is opened and rolled back. Result: A=100, B=50. This proves **a call originating from a class outside the container can still be intercepted**.

**Case 4 — `manual service inside TransactionTemplate`:**

`raw` is still not a Spring proxy, yet a transaction was opened by `TransactionTemplate` **before the raw method ran**. Because `raw` uses the exact `JdbcTemplate`/datasource managed by the transaction manager, both SQL statements join that transaction. The exception from the callback causes `TransactionTemplate` to roll back; A=100, B=50. This case reminds us that **a raw object cannot initiate a transaction via its annotation**, yet SQL it executes **can still participate in an active transaction** if the right infrastructure and resources are used.

All four cases do not depend on a Spring web server. `main()` is ordinary Java code, yet it pulls a bean proxy from the Spring context and passes the reference to callers. That clearly demonstrates "outside the container" must be understood in terms of **target/reference**, not merely which file or method contains the call site.

## 5. Checklist to Diagnose Why `@Transactional` Is Not Running

When a method has the annotation yet rollback does not behave as expected, check in order.

### 5.1. First: where did the service object come from?

```java
WalletService fromContainer = context.getBean(WalletService.class);
WalletService fromNew = new WalletService(jdbc);
```

This is an **illustrative snippet**, requiring an existing `context` and `jdbc`. The two references differ in lifecycle. The bean retrieved from the context has the opportunity to be processed and proxied by Spring; the manually `new`-ed object does not. Never decide based on class name or the presence of `@Service`. An instance is still a raw object if you `new` it yourself.

### 5.2. Right bean, but is it actually a proxy?

In diagnostic code, when `spring-aop` is on the classpath:

```java
Object candidate = context.getBean("walletService");
System.out.println(AopUtils.isAopProxy(candidate));
```

This snippet is **illustrative**; import `org.springframework.aop.support.AopUtils`. If you expect a transaction proxy and get `false`, check bean registration, `@EnableTransactionManagement`, the owning context, non-proxiable class/method modifiers, and supporting conditions. Still, `true` only proves there is **an AOP proxy**, not necessarily that the specific transaction interceptor is active. Combine this with observing active transactions and rollback data.

### 5.3. Did dependency injection happen?

- A manually `new`-ed object with `@Autowired` fields usually was never injected: fields may be `null`.
- With constructor injection, the caller must supply dependencies. Passing a container-created `JdbcTemplate` or repository into a raw service **does not automatically turn the raw service into a Spring proxy**.
- Register the object via `@Bean`, `@Component` + proper component scanning, or obtain it via `ObjectProvider.getObject()` when scoping/prototype instances are needed. Objects validly created through Spring's lifecycle can be wrapped in proxies.
- Avoid keeping a manually created raw instance alongside a Spring bean proxy of the same class; it easily leads to business paths running with different transaction semantics.

### 5.4. Does the call go through the proxy?

Even when the service is a Spring bean, internal calls via `this` bypass the proxy in standard Spring AOP mode:

```java
@Service
public class BillingService {
    public void process() {
        save(); // Self-call on 'this', bypassing save()'s proxy.
    }

    @Transactional
    public void save() {
        // Persist data.
    }
}
```

This is an **illustrative class**. The clean fix is usually placing `@Transactional` on the public entry method `process()` if the whole operation needs a transaction, or moving `save()` to another bean and calling it through an injected proxy. Calling `this.save()` and manually `new`-ing objects are two distinct mistakes sharing one rule: **neither passes through Spring's transaction advice**.

### 5.5. Is transaction management configured in the right context?

`@EnableTransactionManagement` and `<tx:annotation-driven/>` in standard proxy mode apply to beans within the **corresponding `ApplicationContext`**. If services live in the root context while transaction configuration is only in a `DispatcherServlet` child context, root services are not automatically proxied by the child. Conversely, if a service lives in a child context while advice is enabled only in the root, the root does not automatically post-process child beans.

Do not equate a child context **seeing a bean** in the parent with the child **creating a transaction proxy** for that bean. Single-context Boot apps are simpler here, yet multi-context setups still require verifying specific ownership.

### 5.6. Are the class and method proxiable?

In class-based proxies, `final` classes and `final` methods cannot be subclassed/overridden by CGLIB for advice; `private` methods cannot be intercepted this way either. With JDK interface proxies, callers must invoke through the interface proxy and the method must belong to the interface. A `public` method on a non-final service bean, called by another caller via proxy, is the least surprising choice.

`proxyTargetClass=true` can select class-based proxies where applicable, yet **never turns a `new`-created raw object into a bean**. `AdviceMode.ASPECTJ` has different semantics because it uses weaving and requires its own setup; this lesson covers **default proxy mode**, so do not extrapolate to weaving cases.

### 5.7. Are rollback rules and resources actually aligned?

Even when the interceptor runs, `@Transactional` rolls back by default on uncaught `RuntimeException` and `Error`, whereas checked exceptions such as `IOException` usually need `rollbackFor` or a global default rollback config supported by your Spring version. If a method **catches an exception and returns normally**, the interceptor may commit earlier changes unless the transaction was already marked rollback-only.

A JDBC transaction manager only controls connections from its participating datasource. Raw code using a **different** JDBC connection or calling external systems (email, HTTP, an independent message broker) will not automatically roll back with the transaction. When using JDBC directly, ensure connections are obtained through transaction-aware infrastructure (like `JdbcTemplate`/`DataSourceUtils`), rather than arbitrarily calling `dataSource.getConnection()` and managing it manually while expecting Spring transaction control.

## 6. How Should Each Scenario Be Handled?

| Scenario | Appropriate Fix |
| --- | --- |
| Service has `@Transactional` yet is instantiated ad hoc via `new` | Register as a Spring bean; inject or obtain the bean proxy via `ApplicationContext` / `ObjectProvider`. |
| A job/caller outside the container needs to call the service | Pass in the **proxy** obtained from Spring; the caller need not be a Spring bean. |
| Service is created by a `@Bean` method returning `new` | This is valid because Spring manages the **resulting bean**; obtain the reference from the context instead of calling the factory method ad hoc. |
| Need a transaction for a callback in non-bean code | Use `TransactionTemplate` with the appropriate manager and participating resources. |
| Transactional method is called via `this.method()` | Place the boundary on the entry point or call through another injected bean. |
| Service bean is in parent context, advice only in child context | Enable transaction infrastructure in the context that owns the service. |
| Bean is proxied yet fails to roll back | Check exception rules, whether the exception escapes the boundary, manager, connection, and propagation. |
| `new`-ing an object containing `@Autowired` fields | Use constructor injection / bean lifecycle; do not assume injection ran. |

**Key point:** "fixing" this by sprinkling `@Transactional` onto every method rarely helps if calls still hit a raw object. Fix **reference flow** and **lifecycle ownership** first.

## 7. Common Misconceptions and Boundaries to Remember

**Misconception 1 — "If a class has `@Service`, `new` is managed too."** No. `@Service` is a stereotype allowing Spring to discover the class during component scanning; it does not turn every instance of the class into a bean.

**Misconception 2 — "`@Bean` uses `new`, so transaction annotations on the bean break."** No. If Spring invokes the factory method to create the bean and transaction bean post-processors are active, the resulting bean can be wrapped in a proxy normally. The demo directly confirms this.

**Misconception 3 — "Callers outside the container cannot use transactions."** No. Ordinary callers can invoke a proxy from Spring; calls entering the proxy are handled by the interceptor. Many real-world callers such as command-line runners, test harnesses, schedulers, and application plugins can use a properly supplied proxy reference.

**Misconception 4 — "Just grabbing dependencies from Spring and `new`-ing the service is enough."** No. A raw service can use a manually injected `JdbcTemplate`, yet the raw service's own `@Transactional` methods remain unproxied. The demo deliberately reproduced this to isolate the cause.

**Misconception 5 — "Without a proxy, no SQL runs."** No. JDBC still executes; under certain connection configs statements auto-commit one by one, leading to **partial commits** on failure. Adding annotations without a real transaction boundary creates a false sense of safety.

**Misconception 6 — "`TransactionSynchronizationManager.isActualTransactionActive()` is sufficient proof for the entire operation."** Not sufficient. It reports whether Spring currently considers a transaction active on the thread; you must still verify **that data access resources participate**, rollback rules, and database state after the transaction finishes. Async code on another thread or reactive pipelines have separate context models.

**Misconception 7 — "Every method invocation on a proxied bean is intercepted."** No. Method visibility, final/private methods, interface proxies, and self-invocation impose limits. A proxy's existence also does not force a method lacking transaction metadata to open a transaction.

**Misconception 8 — "Raw objects never run inside a transaction."** No. Raw objects cannot start transactions via their annotations, yet their JDBC operations can still join a transaction already created by a caller/template on the same thread and datasource. The `TransactionTemplate` demo showed this.

**Misconception 9 — "Spawning a new thread keeps the caller's transaction."** For Spring imperative transactions, resources are usually bound to the current thread; `new Thread`, `@Async`, or `CompletableFuture` do not automatically carry transactions across threads. For R2DBC/reactive, use `ReactiveTransactionManager` and Reactor Context; do not conflate the two models.

**Misconception 10 — "A `@Transactional` test passing means the service opens a transaction itself."** Spring Test can open a transaction for the **test method** and roll everything back afterward. Raw code running inside a test transaction can trick authors into thinking annotations on a raw service took effect. Tests should invoke the service without an outer transaction (or explicitly control test boundaries) and inspect data after the service commits/rolls back.

## 8. Self-Check and Exercises

Before running the lab, predict the outcome and then run the demo:

| Case | `WalletService` Target | Caller | Where is the transaction actively opened? | Expected after failure |
| --- | --- | --- | --- | --- |
| 1 | `new WalletService(jdbc)` | `main()` | Nowhere | A=80, B=70 |
| 2 | Bean proxy from `context.getBean` | `main()` | Transaction interceptor | A=100, B=50 |
| 3 | Bean proxy from `context.getBean` | `new ExternalCaller(bean)` | Transaction interceptor | A=100, B=50 |
| 4 | Raw `new WalletService(jdbc)` | `TransactionTemplate` | Outer template | A=100, B=50 |

Additional experiments:

1. **Swap the reference:** change `new ExternalCaller(bean)` to `new ExternalCaller(raw)` and rerun. Predict `Transaction active` and balances; explain why the caller's construction site is identical yet the result changes.
2. **Remove transaction infrastructure:** remove `@EnableTransactionManagement` from `Config`, retrieve `WalletService` from the context again, and predict `AopUtils.isAopProxy(bean)`. Distinguish `@Transactional` metadata from the runtime advisor.
3. **Change how the service is registered:** remove `@Bean walletService(...)` and register `WalletService` via `@Component` + properly scoped `@ComponentScan` with constructor injection. The goal is seeing that Spring still owns the bean and creates the proxy regardless of discovery style.
4. **Catch the error inside the service:** modify `transferAndFail` to catch and swallow `IllegalStateException` before returning through the proxy; predict whether Spring rolls back by default. Distinguish rollback policy from whether the exception actually crosses the boundary.
5. **Move the transaction boundary:** keep the raw service but wrap its call in `TransactionTemplate` as in case 4. Explain why a real transaction exists even though `@Transactional` on the raw service is still unproxied.
6. **Think about real data:** modify the demo to throw an error **between** debiting and crediting. With the raw service, A's balance changes while B never increases; with the proxy service, both A and B revert to their original values. This is a far more important check than just reading logs.

Self-assessment questions:

- Does `@Transactional` do anything by itself when the JVM calls a method on an object just created with `new`?
- When is a `@Bean` method allowed to return `new SomeService(...)` and still be processed by Spring AOP?
- Does `new ExternalCaller(proxy)` lose transactions merely because the caller is not a bean?
- Why can a raw method print `transaction active = true` when called from `TransactionTemplate`?
- When logs show an AOP proxy yet rollback behaves wrongly, what should you check next?

## 9. Official References

- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): annotations as metadata; runtime transactions via infrastructure/proxy; self-invocation and transaction boundaries.
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): `TransactionInterceptor`, `TransactionManager`, and AOP proxies.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): difference between calling target and calling proxy, JDK/CGLIB, self-invocation.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` opening transactions programmatically.
- [Spring Framework — `@Bean` Methods](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): objects created via factory methods managed by the container.
