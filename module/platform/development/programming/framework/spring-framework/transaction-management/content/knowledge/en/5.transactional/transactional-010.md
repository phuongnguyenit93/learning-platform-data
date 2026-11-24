# Scope of `@Transactional` Detection in `ApplicationContext`

## 1. Lesson Objectives

A method annotated with `@Transactional` can still run **without a transaction** even when the application declares `@EnableTransactionManagement`. Sometimes the root cause is not the annotation, transaction manager, or JDBC, but **which `ApplicationContext` owns the bean and which `ApplicationContext` enables annotation processing**.

After this lesson, you can:

- Distinguish `@Transactional` (metadata on a method/class) from `@EnableTransactionManagement` (enabling the infrastructure that processes the metadata).
- Explain the **same `ApplicationContext`** rule: the transaction advisor/proxy applies to beans managed by that corresponding context and does not automatically propagate down or up across every context in a hierarchy.
- Identify a classic pitfall in traditional Spring MVC setups with a **root `WebApplicationContext`** and a **`DispatcherServlet` child `WebApplicationContext`**.
- Build a parent–child context pair to observe the difference between "bean is visible" and "bean was wrapped in a transaction proxy".
- Verify using three pieces of evidence: bean ownership location, `AopUtils.isAopProxy(...)`, and database state after an exception.
- Fix the issue by placing transaction configuration in the context that owns the service or registering beans needing protection in the context where transaction advice is enabled.

**Main point:** `@EnableTransactionManagement` and XML `<tx:annotation-driven/>` in standard proxy mode only process `@Transactional` on **beans belonging to the same `ApplicationContext`**. If you enable them in the `DispatcherServlet` child context while services live in the parent context, annotations on parent services will not automatically be processed by the child context.

## 2. What Does "Detecting the Annotation" Actually Mean?

Consider the method:

```java
@Transactional
public void placeOrder() {
    debitInventory();
    saveOrder();
}
```

This is **illustrative code**, without defining `debitInventory()` and `saveOrder()`. `@Transactional` states that a method needs transaction semantics; by itself it **does not open a transaction** merely because the JVM sees the annotation.

In Spring's default **proxy mode**, the process works as follows:

1. `@EnableTransactionManagement` on a `@Configuration` class imports transaction management infrastructure beans into **the `ApplicationContext` containing that configuration**. XML `<tx:annotation-driven/>` plays the same role.
2. The infrastructure registers an advisor/interceptor alongside an auto-proxy mechanism. When the context creates and initializes its Spring beans, beans with eligible `@Transactional` metadata may be returned as an **AOP proxy**.
3. The caller must invoke through the proxy. The transaction interceptor resolves the transaction manager and applies begin/join and commit/rollback around the call.
4. Calling the target object directly, or calling an internal method via `this.`, can bypass the interceptor in proxy mode.

Diagram:

```text
Bean definition in Context A
    |
    v
Context A creates bean
    |
    +-- Has Context A enabled transaction annotation advice?
    |       |
    |       +-- Yes, method is eligible -> create transaction-aware proxy
    |       |
    |       +-- No -> returned bean has no transaction proxy from this mechanism
    |
    v
Caller invokes object created by Context A
    |
    +-- Through proxy -> can open/join transaction
    +-- Through target directly -> no interception by that proxy
```

**Do not confuse with component scanning:** `@ComponentScan` discovers classes to register bean definitions. `@EnableTransactionManagement` activates applying transaction advice to beans inside that context. Having a package scanned, an annotation present in bytecode, or a child context able to see a parent bean **does not mean** a transaction proxy was created for that bean.

Nor should "same context" be confused with same **Java package**, same source module, or same config directory. Two classes in different packages registered by the same context can share transaction advice. Conversely, two different contexts scanning the same package remain two distinct bean lifecycle scopes.

## 3. Bean Ownership Rules in Parent–Child Contexts

`ApplicationContext` instances can form a **hierarchy**: a child context can look up beans in its parent context when no matching bean exists in its local scope. Visibility normally flows **child → parent**, whereas a parent does not automatically see beans declared only in a child.

```text
Root ApplicationContext
  ├─ accountService         [@Transactional]
  ├─ accountRepository
  ├─ dataSource
  └─ transactionManager
           ^
           | Child can look up/inject parent beans
           |
Child ApplicationContext
  ├─ webController
  └─ @EnableTransactionManagement
```

If `@EnableTransactionManagement` is **only in Child**:

- `child.getBean("accountService")` can return the bean created by **Root**; this reachability is **bean visibility**.
- **Child's** proxy infrastructure only post-processes beans managed by **Child** when they are initialized; it **does not go back and replace beans already created by Root**.
- Consequently, `accountService` in Root may remain an object unprotected by a transaction proxy, even though Child has the configuration and can see that bean.
- `child.containsBean("accountService")` can return `true`, while `child.containsLocalBean("accountService")` returns `false`. Those two methods answer **two different questions**.

### 3.1. Three Configurations to Distinguish

| Where `@Transactional` service lives | Where `@EnableTransactionManagement` lives | Outcome in standard proxy mode |
| --- | --- | --- |
| Root | Root | Service in Root is considered for transaction proxying. |
| Root | Only Child | Service in Root is **not** automatically proxied by Child. |
| Child | Child | Service in Child is considered for transaction proxying. |
| Both Root and Child have their own services | Only Root | Only Root beans are processed by Root's infrastructure; Child-only beans are not automatically processed by Root. |
| Both Root and Child have their own services | Both | Each context's own infrastructure processes beans **belonging to itself**. |

The table describes default processing scope; it **does not guarantee** every call gets a transaction, because proxy visibility, call path, transaction manager, rollback policy, and resource participation still apply.

### 3.2. Do Not Confuse Bean Inheritance with Proxy Inheritance

If Root **already created a proxy** for `accountService`, Child looking up that bean receives **that exact proxy from Root**. Thus it still runs transactionally when called through the proxy. That is **completely different** from Child re-scanning annotations on a parent bean.

If Root **did not create a proxy**, Child's lookup normally receives the unproxied parent bean; enabling infrastructure in Child does not retroactively patch that object. In other words, a context hierarchy passes **bean references**, not post-initialization bean processing across contexts.

## 4. Real-World Scenario: Spring MVC Root and `DispatcherServlet` Child

In some traditional Spring MVC applications (especially when organizing multiple `WebApplicationContext`s manually), the layout looks like:

```text
Root WebApplicationContext
  ├─ Services: OrderService, PaymentService
  ├─ Repositories, DataSource
  └─ PlatformTransactionManager

DispatcherServlet WebApplicationContext (child)
  ├─ Controllers: OrderController
  ├─ HandlerMapping / ViewResolver
  └─ MVC configuration
```

**Easy-to-make mistake:** placing `@EnableTransactionManagement` only on the web/MVC configuration so it gets loaded **only into the `DispatcherServlet` child**, while `OrderService` is actually created by the root context. Annotations on root services **are not applied merely by child configuration**. The controller can still inject the service because child lookup sees the parent, so the app boots normally; only when an exception hits does it reveal data failing to roll back as expected.

**Correct configuration by ownership:** register transaction infrastructure in the **root context that owns the services**:

```java
@Configuration
@EnableTransactionManagement
public class RootTransactionConfig {
    // Place this class in the ROOT context together with services needing @Transactional.
    // TransactionManager can be provided by another root configuration.
}
```

The snippet above is an **illustrative configuration**, not a complete app. Make sure it is **actually registered/imported by the root context**, rather than merely sitting in a package scanned by the child. For systems with services managed by a child context, that child can also enable transaction management for its own beans.

Typical Spring Boot MVC apps use one main application context, and Boot auto-configuration can enable transaction infrastructure when conditions match. Still, whenever an app adds child contexts, multiple `DispatcherServlet`s, modular parent/child contexts, or manual web config imports, you must check **which context creates which bean**. Never assume scope issues cannot happen just because you use Boot.

## 5. Runnable Practice: A Bean in Root, Transactions Enabled in Child vs. Root

We will build a **Java 17+, Spring Framework 6.2.8, Spring JDBC, in-memory H2** project using **one Java file and one Maven file**. No Spring Boot or servlet container is needed. Both scenarios use the same service located in Root:

1. **CHILD_ONLY:** Child enables transaction annotation processing, Root does not. The service has `@Transactional` but is not proxied by Root; both `UPDATE` statements auto-commit before the exception is thrown.
2. **ROOT_AND_CHILD:** Root also enables transaction annotation processing. The Root service is proxied; the same exception causes **both writes to roll back**.

We trigger a simulated error **after running both write statements**. Afterward we read back the data to see whether they actually rolled back. Checking the annotation on the class alone is not enough.

### 5.1. Project Structure

```text
context-transaction-scope/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── example/
                └── ScopeDemo.java
```

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>context-transaction-scope</artifactId>
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
                    <mainClass>example.ScopeDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides `ApplicationContext`s and `@Bean` configuration; `spring-jdbc` provides `JdbcTemplate`/`DataSourceTransactionManager`; `spring-tx` contains `@Transactional`; H2 provides the in-memory database. The example directly uses `org.h2.jdbcx.JdbcDataSource`, so the H2 dependency must be present at **compile time**, not only runtime.

### 5.3. `ScopeDemo.java`

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

public class ScopeDemo {

    public static void main(String[] args) {
        runCase(false);
        runCase(true);
    }

    private static void runCase(boolean enableTransactionsInRoot) {
        // 1. ROOT owns DataSource, TransactionManager, and TransferService.
        try (var root = new AnnotationConfigApplicationContext()) {
            root.register(RootBeans.class);

            if (enableTransactionsInRoot) {
                root.register(RootTransactionConfig.class);
            }
            root.refresh();

            // 2. CHILD has the same parent in both cases.
            //    Enabling transactions only in CHILD does not re-proxy ROOT beans.
            try (var child = new AnnotationConfigApplicationContext()) {
                child.setParent(root);
                child.register(ChildTransactionConfig.class);
                child.refresh();

                JdbcTemplate jdbc = root.getBean(JdbcTemplate.class);
                initializeDatabase(jdbc);

                TransferService fromRoot =
                    root.getBean("transferService", TransferService.class);
                TransferService fromChild =
                    child.getBean("transferService", TransferService.class);

                System.out.println(
                    enableTransactionsInRoot ? "ROOT_AND_CHILD" : "CHILD_ONLY"
                );
                System.out.println(
                    "Child sees bean: " + child.containsBean("transferService")
                );
                System.out.println(
                    "Child owns bean: " + child.containsLocalBean("transferService")
                );
                System.out.println(
                    "Same bean: " + (fromRoot == fromChild)
                );
                System.out.println(
                    "Root service proxied: " + AopUtils.isAopProxy(fromRoot)
                );

                try {
                    fromChild.transferThenFail();
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
        }
    }

    private static void initializeDatabase(JdbcTemplate jdbc) {
        // Reuse the same H2 database across both runCases; reset data before each case.
        jdbc.execute("DROP TABLE IF EXISTS wallets");
        jdbc.execute(
            "CREATE TABLE wallets (id INT PRIMARY KEY, balance INT NOT NULL)"
        );
        jdbc.update("INSERT INTO wallets (id, balance) VALUES (1, 100)");
        jdbc.update("INSERT INTO wallets (id, balance) VALUES (2, 50)");
    }

    // Beans created and post-processed by ROOT context.
    @Configuration(proxyBeanMethods = false)
    public static class RootBeans {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:tx_scope;DB_CLOSE_DELAY=-1");
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
        public TransferService transferService(JdbcTemplate jdbcTemplate) {
            return new TransferService(jdbcTemplate);
        }
    }

    // Registered in ROOT in the second case.
    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class RootTransactionConfig {
    }

    // Registered in CHILD in BOTH cases.
    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class ChildTransactionConfig {
    }

    public static class TransferService {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void transferThenFail() {
            System.out.println(
                "Transaction active: " +
                TransactionSynchronizationManager.isActualTransactionActive()
            );

            int debited = jdbc.update(
                "UPDATE wallets SET balance = balance - 20 WHERE id = 1"
            );
            int credited = jdbc.update(
                "UPDATE wallets SET balance = balance + 20 WHERE id = 2"
            );

            if (debited != 1 || credited != 1) {
                throw new IllegalStateException("invalid wallet");
            }
            throw new IllegalStateException("forced failure");
        }
    }
}
```

**Why does this demo test context scope properly?**

- `RootBeans` is always registered **before Root refreshes**. Hence `TransferService` belongs to Root in both scenarios.
- `ChildTransactionConfig` is always registered in Child. The only variable is whether Root receives `RootTransactionConfig`.
- `child.containsBean(...)` vs. `child.containsLocalBean(...)` distinguishes **lookup via parent** from **ownership inside child**.
- `AopUtils.isAopProxy(fromRoot)` checks whether Root actually returned a proxy or a plain target.
- `TransactionSynchronizationManager.isActualTransactionActive()` is called **right inside the method**; in this demo it reflects the JDBC transaction applied by the interceptor at execution time.
- `transferThenFail()` executes **two SQL UPDATEs**, then intentionally throws an unchecked exception. The balance difference after the error proves whether a transaction was active.
- The H2 setting `DB_CLOSE_DELAY=-1` keeps the in-memory database alive for the JVM's lifetime; `initializeDatabase` recreates the table and data before each case so results are independent.

`TransferService` does not need `@Service` because it is declared via `@Bean` in `RootBeans`. What decides is not the stereotype annotation, but **which Spring context instantiates the bean**.

### 5.4. Running and Reading the Output Correctly

From the `context-transaction-scope` directory, using **JDK 17+** and **Maven 3.9+**:

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Lines printed by **the program** in exact order (excluding Maven/Spring logs if any):

```text
CHILD_ONLY
Child sees bean: true
Child owns bean: false
Same bean: true
Root service proxied: false
Transaction active: false
Caught: forced failure
Balances: A=80, B=70
ROOT_AND_CHILD
Child sees bean: true
Child owns bean: false
Same bean: true
Root service proxied: true
Transaction active: true
Caught: forced failure
Balances: A=100, B=50
```

In **CHILD_ONLY**, both `UPDATE`s succeed and the connection is not wrapped by the transaction manager during the service call, so with `JdbcDataSource`/default JDBC they auto-commit. The exception thrown **after both writes** cannot undo them; data ends up `A=80, B=70`.

In **ROOT_AND_CHILD**, Root applies the transaction advisor to `TransferService` when creating the bean. The caller retrieves the bean via Child yet receives **the proxy from Root**. The interceptor starts a transaction before the method; the `IllegalStateException` escapes the method so it rolls back by default, leaving `A=100, B=50`. All inputs are identical; the only difference is **which context enabled annotation-driven transaction processing**.

Note: this demo demonstrates the behavior of a service intentionally throwing an error. In real business code, two writes should check updated row counts, valid amounts, concurrency handling, and required atomicity; do not use simulated exceptions in production.

## 6. Fixing Context Scope Bugs in Real Projects

When you discover a method has `@Transactional` yet fails to roll back, check in this order:

### Step 1. Identify Where the Bean Is Created

Inspect which `@Configuration`/`@Bean`, `@ComponentScan`, `@Import`, or XML bean definitions are **registered into which context**. In traditional MVC setups, find the root configuration and the configuration loaded by `DispatcherServlet`. **A config file sitting next to controllers does not mean it is loaded into root.**

If you have references to root/child in diagnostic code, you can check:

```java
System.out.println(root.containsLocalBean("transferService"));
System.out.println(child.containsLocalBean("transferService"));
System.out.println(child.containsBean("transferService"));
```

This is an **illustrative diagnostic snippet**, assuming `root` and `child` variables exist. `containsBean` can see parent beans; `containsLocalBean` checks only local beans.

### Step 2. Identify Which Context Holds the Transaction Infrastructure

Find where this is registered:

```java
@Configuration
@EnableTransactionManagement
class TransactionConfig {
}
```

or the XML element:

```xml
<tx:annotation-driven transaction-manager="transactionManager"/>
```

Both snippets are **illustrative configurations**; XML also requires full namespaces/schemas/manager beans. They must be loaded in **the context owning the beans to protect**. If there are multiple contexts, enable separately for each context containing corresponding transactional beans. Do not enable indiscriminately in every context as a band-aid for unclear ownership.

### Step 3. Check Whether the Injected Spring Bean Is a Proxy

```java
Object service = context.getBean("transferService");
System.out.println(AopUtils.isAopProxy(service));
```

The snippet above assumes `context` exists and `org.springframework.aop.support.AopUtils` is imported. `false` in a configuration **expected to produce a proxy** is a signal to investigate (e.g., wrong context, unregistered advice, ineligible method). `true` only indicates the object is an AOP proxy; it **does not prove transaction advice itself ran**, because a proxy could serve another advice. Combine this with checking active transactions and rollback results.

### Step 4. Verify the Call Passes Through the Proxy

A properly proxied bean can still bypass interception if it calls `this.inner()` within the same target instance:

```java
public void outer() {
    inner(); // Self-invocation: does not go through proxy.
}

@Transactional
public void inner() {
    // Write data requiring a transaction.
}
```

This is **illustrative code**, not a complete class. Typical fixes are placing the annotation on the public entry method called through the proxy by external callers, or moving `inner` into another bean and injecting/calling that bean. **Self-invocation** and **context scope** are two independent bugs; fixing context scope will not fix self-invocation.

### Step 5. Verify Transaction Manager, Data Source, and Rollback Rules

A proxy may be active while data access code uses an out-of-transaction connection or a different manager. Check `JdbcTemplate`/JPA repositories, the shared datasource, the selected manager bean (especially with multiple managers), propagation, and participating transactions. For methods throwing checked exceptions, default Spring transaction declarations may **commit** unless `rollbackFor` or a matching policy is configured. When a method catches an exception and returns normally, the interceptor may not know the operation failed.

Do not jump to blaming context for every rollback bug: if `AopUtils.isAopProxy(...)` is true and transaction active state is true, move on to inspecting **resource participation, propagation, timeout, and rollback semantics**.

## 7. Easy-to-Confuse Scope Scenarios

### 7.1. Is `@ComponentScan` Enough?

No. `@ComponentScan` only decides **which beans are registered into the scanning context**. If you scan services in the child instead of root, you change **ownership** and may create duplicate beans. Moving component scans must be evaluated alongside dependency injection, bean scopes, and same-named beans. The usual fix is enabling transaction advice **in the exact context that already owns the services**, causing less architectural churn.

### 7.2. What If Child Sees Root's Transaction Manager?

Child can resolve the manager bean from Root when **Child's** transaction advice needs to use it. Yet merely seeing the manager **does not** mean Root's services are proxied. Distinguish three layers:

1. **Bean lookup:** does Child see `transactionManager` and `service` in parent?
2. **Bean post-processing:** which context creates the proxy for `service`?
3. **Runtime:** does the specific call pass through the proxy and use the right transaction manager/resource?

Without step 2, having the manager still will not make annotations on Root beans take effect.

### 7.3. Do You Need `@EnableTransactionManagement` Next to Every `@Transactional`?

No. It is infrastructure configuration for **one `ApplicationContext`**, not a marker annotation attached to every service. It can live on one `@Configuration` class imported into the same context as the services. A context normally needs transaction management configured once, not repeated on every class.

### 7.4. What If the Bean Is in Child and Configuration Is Only in Root?

Root's auto-proxy infrastructure does not reach down to post-process beans created only by Child. Even though Child can see Root's manager/repository beans, it still needs transaction annotation processing inside **Child** if it wants to create transactional proxies for Child services (or a separately configured weaving/proxy mechanism).

### 7.5. Roles of `proxyTargetClass`, `AdviceMode.ASPECTJ`, and Non-Public Methods?

`@EnableTransactionManagement` defaults to `AdviceMode.PROXY`. `proxyTargetClass=true` changes proxy creation to class-based instead of interface-based where applicable, **without changing context scope**. Spring also supports `AdviceMode.ASPECTJ` with separate weaving/dependencies and setup, which has different semantics from proxy mode; this lesson describes **default proxy mode**, so do not apply every proxy conclusion verbatim to AspectJ weaving.

`private` methods cannot be intercepted by proxies in normal calls. Support for package-private/protected methods varies by version and proxy type, so prefer public service methods called from outside the bean. Do not confuse method/proxy limitations with infrastructure placed in the wrong context.

### 7.6. What If a Spring Boot App Does Not Declare `@EnableTransactionManagement`?

Spring Boot includes transaction auto-configuration based on dependency and transaction manager conditions. In typical apps it can automatically enable annotation-driven transaction management. That **does not mean** every custom `ApplicationContext` or `DispatcherServlet` child is configured identically. When debugging, inspect **which infrastructure actually exists in each context**, rather than inferring solely from dependencies in `pom.xml`.

### 7.7. When There Are Multiple `DispatcherServlet`s or Multiple Module Contexts?

Each child `WebApplicationContext` may have its own controllers/beans. If transaction configuration lives only in one servlet's child, separate beans in other children are not automatically processed. You can keep shared services in Root with Root's transaction infrastructure and let child controllers inject Root proxies, or configure advice independently in children that genuinely own transactional beans. Keeping ownership easy to inspect reduces seemingly random failures across endpoints.

## 8. Self-Check Table and Exercises

| Symptom | First cause to verify | Helpful observation |
| --- | --- | --- |
| Root service has `@Transactional` yet rollback does not run | Advice is enabled only in Child | Check parent/child registration and `AopUtils.isAopProxy` |
| Child `getBean(...)` returns the service, yet it is unproxied | Bean belongs to Root; Child only resolves reference | `containsBean` true but `containsLocalBean` false |
| Service is properly proxied, yet internal call opens no transaction | `this.method()` bypasses interceptor | Place boundary on caller or call through another bean |
| Bean is proxied, yet errors still commit | Caught exception, checked exception, wrong resource/manager | Check rollback rules, active transaction, datasource |
| Controller in Child has working annotations while Root service does not | The two beans belong to two different contexts | Compare bean ownership and where infrastructure is enabled |
| Enabled `proxyTargetClass=true` yet service still has no transaction | Context owning the bean lacks transaction advice | Configure in the same context before changing proxy type |

**Hands-on exercises on a copy of the demo:**

1. Remove `child.register(ChildTransactionConfig.class)` in both cases and re-run. In the case where Root has transactions, predict whether `TransferService` stays proxied; explain based on **owner context**.
2. Move `TransferService` from Root to a `@Bean` in Child and enable transactions only in Child. Predict `AopUtils.isAopProxy(...)` and rollback results. When editing, ensure you do not leave duplicate bean names across root/child.
3. Change the unchecked error to a checked exception with `@Transactional(rollbackFor = IOException.class)` in an appropriate method; explain why the rollback policy had to change.
4. Write a service method calling `this.transferThenFail()` and see why internal calls can bypass the proxy. Extract to another bean or move the boundary to the entry point, then re-test.
5. Diagram the context layout of a real project: who creates services, where transaction configuration lives, which context callers retrieve beans from, and where the transaction manager sits. Only when all four questions are answered should you conclude an annotation will be intercepted.

**Takeaway to remember:** in proxy mode, **`@EnableTransactionManagement` infrastructure operates per `ApplicationContext` where it is configured**. A child context can **see parent beans**, yet that does not mean it will **create proxies for parent beans**. When placing `@Transactional` on a service, check where the bean is instantiated, where transaction annotation processing is enabled, and the actual call path through the proxy.

## 9. Official References

- [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html) — explicitly explains the same-`ApplicationContext` scope and `DispatcherServlet` child example.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — `@EnableTransactionManagement` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/EnableTransactionManagement.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
- [Spring Framework — BeanFactory/ApplicationContext Hierarchies](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
