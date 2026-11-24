# Interface-Based Proxies vs. Class-Based Proxies in Spring Transaction Management

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **JDK dynamic proxies** (interface-based proxies) and **CGLIB proxies** (class-based proxies) in Spring AOP.
2. Explain how Spring chooses a proxy type, what object the caller actually receives, and how this relates to `@Transactional`.
3. Understand the impact of proxy type on **allowed injection/cast types**, callable methods, and methods eligible to receive transaction advice.
4. Identify limitations around `final`, `private`, methods not declared on an interface, and **self-invocation**.
5. Deliberately choose `proxyTargetClass` when justified, while distinguishing Spring Framework defaults from common Spring Boot configuration.
6. Run a **Java 17+** example comparing a JDK proxy and a CGLIB proxy on the same service, verifying begin/commit/rollback and proxy invocation conditions.

This lesson focuses on **Spring's proxy mechanisms and their consequences for transaction management**. The two proxy creation approaches are not two different ACID levels; they are two techniques for wrapping method invocations with interceptors.

## 1. Where Does the Proxy Stand in a Transaction?

Suppose a bean has a method:

```java
@Transactional
public void transfer(long fromId, long toId, long amount) {
    // Debit source account and credit destination account.
}
```

Simply adding the annotation does not inject `BEGIN` and `COMMIT` statements into the method's bytecode. In Spring transaction **proxy mode**, the caller interacts with a **proxy** object provided by the container. When the caller invokes through the proxy, Spring AOP places `TransactionInterceptor` in the call path, reads `@Transactional` metadata, chooses the appropriate `PlatformTransactionManager` or `ReactiveTransactionManager`, and manages the transaction lifecycle according to the model in use.

```text
Controller / Another Service / ApplicationRunner
                   |
                   v
            Spring AOP proxy
                   |
            TransactionInterceptor
                   |
       TransactionManager (begin/join)
                   |
        Service executes business logic
                   |
       success -> commit (if owner)
       error   -> rollback per policy
                   |
                Caller
```

For synchronous JDBC work, the interceptor typically coordinates `PlatformTransactionManager`. For reactive publishers, a different transaction mechanism uses `ReactiveTransactionManager` and the subscriber context, yet the JDK/CGLIB distinction still matters for **which calls go through the proxy**.

There are two main proxy forms:

- **JDK dynamic proxy:** the JVM generates an object **implementing the service's interface(s)**; it forwards interface calls to Spring AOP's invocation handler mechanism.
- **CGLIB proxy:** Spring generates a **dynamic subclass at runtime** of the concrete target class; it can override eligible methods to apply interceptors.

The proxy types differ in object representation and method coverage; when transaction advice actually runs with the same policy, both can deliver identical commit/rollback behavior.

## 2. JDK Dynamic Proxy: Interface-Based

Suppose we have a contract:

```java
public interface PaymentService {
    void pay(long invoiceId);
}
```

and an implementation:

```java
public class PaymentServiceImpl implements PaymentService {
    @Override
    @Transactional
    public void pay(long invoiceId) {
        // Data operations participating in the transaction.
    }

    public void recalculateInternalIndex() {
        // This method is not on PaymentService.
    }
}
```

These two snippets illustrate structure and are not a standalone application. In interface-based proxy mode, the runtime object Spring hands to callers looks conceptually like:

```text
                implements
JDK Proxy ------------------------> PaymentService
   |
   | InvocationHandler / advice chain
   v
PaymentServiceImpl (actual target)
```

The proxy **implements** `PaymentService`, but **does not extend** `PaymentServiceImpl`. Therefore:

```java
PaymentService service = context.getBean(PaymentService.class);
service.pay(10L); // Can be handled by the transaction interceptor.
```

is valid usage, whereas the following is not guaranteed:

```java
PaymentServiceImpl concrete = (PaymentServiceImpl) service;
// When the bean is a JDK proxy: typically ClassCastException.
```

`recalculateInternalIndex()` is not on the interface, so it cannot be called via a `PaymentService` reference and is not exposed as a method of that JDK proxy. Even if the implementation method has `@Transactional`, if it is **not a callable method on the proxy's interface**, callers cannot invoke it through this proxy.

**Common pitfall:** A JDK proxy does not require `@Transactional` to be placed **on the interface**. In modern Spring Framework, Spring can locate annotations on the concrete implementation method when a call arrives via the proxy. Prefer placing transaction metadata on the **concrete class/method** for maintainability and compatibility across advice mechanisms.

### Advantages and limitations

- Fits **program to an interface** design and contract-based dependency injection.
- Does not require subclassing the implementation, avoiding subclassing restrictions like `final class` under interface-based proxying, provided calls go through a matching interface.
- Exposes only methods of interfaces implemented by the proxy; injecting or casting to the concrete class no longer works.
- Transactional methods used with interface-based proxies must be **`public` and declared on the proxied interface**.
- An interface proxy is not an actual subclass of the target; do not rely on the runtime class name to identify business types.

## 3. CGLIB Proxy: Concrete-Class-Based

When using class-based proxies, Spring creates a dynamic subclass of the service:

```text
PaymentServiceImpl
        ^
        | extends
PaymentServiceImpl$$SpringCGLIB$$... (proxy)
        |
        v
Caller invokes eligible method
        |
   AOP advice chain
        |
   target implementation
```

The proxy object **is assignable to the concrete class**, in addition to any interfaces the class implements:

```java
PaymentServiceImpl concrete =
    context.getBean(PaymentServiceImpl.class);

concrete.pay(10L);
concrete.recalculateInternalIndex();
```

If `recalculateInternalIndex` is eligible for Spring advice and has matching metadata, it can also be intercepted even though it is absent from the interface.

However, because the proxy must extend the concrete class and override methods, CGLIB has important limitations:

- **`final` classes cannot be subclassed** to create a class-based proxy.
- **`final` methods cannot be overridden**, so Spring AOP advice cannot be applied via overriding for that method.
- **`private` methods cannot be overridden**, so they cannot be proxy-intercepted under this model.
- Methods not visible to the subclass—for example, package-private methods inherited across packages and thus inaccessible—cannot be advised either.
- Specific Java Platform Module System constraints or inability to open packages can impede subclass/proxy generation.

In Spring Framework **6.0 and later**, `@Transactional` on `protected` or package-visible methods can be processed **by default with class-based proxies** when the method is eligible. This differs from older versions where people assumed every transactional method had to be public. Even so, using `public` service methods remains the most predictable practice; interface-based proxies still only support public methods declared on the interface.

### CGLIB does not mean "every call is intercepted"

A CGLIB proxy does not rewrite the target's own source code. It only intercepts calls **entering the proxy object**, and only for methods that can be overridden/advised. If logic inside the target directly calls `this.otherMethod()`, that call usually goes straight to the implementation without passing through the external interceptor. This self-invocation issue applies equally to both JDK and CGLIB proxies.

## 4. Systematic Comparison

| Criterion | JDK dynamic proxy | CGLIB proxy |
| --- | --- | --- |
| How it is created | JVM object implementing one or more interfaces | Runtime-generated subclass of the concrete class |
| Basic requirement | Target has suitable interface(s) | Class can be subclassed |
| Runtime type | Assignable to interface(s) | Assignable to concrete class and interface(s) |
| Recommended injection | Inject by interface | Can inject by class or interface |
| Method only in implementation | Not exposed through JDK proxy | Callable/advisable if eligible |
| `final class` | Can be proxied via interface | Cannot subclass a `final` class |
| `final method` on target | Interface call can be advised because target override is unnecessary | Cannot override/advise a final method |
| `private method` | Not a public interface method | Cannot override/advise |
| `protected`/package-visible transactional method (Spring 6+) | Cannot be called as a public interface method | Can be advised when eligible and metadata exists |
| Self-invocation `this.method()` | Bypasses advice of the called method | Also bypasses advice of the called method |
| Isolation/rollback behavior | Follows transaction metadata/manager | Follows the same transaction metadata/manager |
| `@Transactional` required? | Not every proxy is a transaction proxy | Same; can be used for other AOP advice |

**Most important takeaway:** the difference lies in the **object interface and which methods can be intercepted**, not in JDK proxies having "weaker" transactions than CGLIB. The same service, same DB, same `@Transactional`, and same transaction manager produce identical transaction outcomes.

## 5. How Does Spring Choose the Proxy Type?

### 5.1. Spring Framework AOP default

In Spring Framework's standard proxy-based model:

1. If the target implements one or more interfaces and no configuration forces class proxies, the framework usually picks a **JDK dynamic proxy**.
2. If the target has no interface to proxy, the framework must use a **class-based proxy** (if the target is eligible).
3. When `proxyTargetClass = true` is set, Spring requests a **class-based proxy** even if the target has interfaces.

Java configuration examples for transaction management:

```java
@Configuration
@EnableTransactionManagement(proxyTargetClass = false)
public class JdkFriendlyConfiguration {
}
```

and:

```java
@Configuration
@EnableTransactionManagement(proxyTargetClass = true)
public class ClassProxyConfiguration {
}
```

These are **two mutually exclusive configuration alternatives**; do not put both in the same ApplicationContext. `proxyTargetClass = false` means allowing JDK proxies when interfaces exist, **not forcing JDK proxies for classes without interfaces**.

A practical note: Spring can merge settings from multiple AOP proxy-creation mechanisms in the same context. Even a single other configuration setting `proxyTargetClass = true` can cause related proxies to use CGLIB. Thus when runtime proxies differ from expectations, inspect the **AOP/transaction configuration across the entire context**, not just one annotation.

### 5.2. Spring Boot often has a different default

Spring Boot AOP auto-configuration normally favors **CGLIB class-based proxies**. When you need to switch to JDK interface proxies, you can configure:

```yaml
spring:
  aop:
    proxy-target-class: false
```

Set `true` to favor class-based proxies. However, if other proxy configurations force class-based proxies, a single property does not necessarily override everything. Observe the runtime proxy or write a test instead of guessing from config files.

The runnable example in the next section uses **plain Spring Framework** without Spring Boot auto-configuration, so you can observe the direct effect of `@EnableTransactionManagement(proxyTargetClass = ...)` without Boot defaults interfering.

### 5.3. When do you actually need to change the proxy type?

Choose **JDK proxies** when the API is cleanly designed around interfaces, callers never need to inject implementation classes, and all transactional methods are exposed on interfaces.

Choose **CGLIB proxies** when there is no interface, callers must inject concrete classes, or you need to advise an eligible public method not on an interface. Ensure the target class is not final and methods needing advice can be overridden.

Do not switch an entire application to CGLIB just to hide a self-invocation bug; changing proxy type **does not fix** that root cause.

## 6. Runnable Java 17+ Example: Same Transaction Service, Two Proxy Types

The example below creates **two separate Spring ApplicationContexts**. The first allows JDK interface proxies; the second requests CGLIB class proxies. Both use the exact same service implementation, `JdbcTemplate`, H2, and `DataSourceTransactionManager`, differing only in `proxyTargetClass`.

We use a single Java file with `static` nested classes so you can copy it verbatim and run it. At the time of testing, Spring Framework 6.1.x is compatible with Java 17+; a specific 6.1 version is pinned so dependencies are deterministic.

### 6.1. Directory structure

```text
tx-proxy-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── example/
                └── txproxy/
                    └── ProxyTransactionsDemo.java
```

### 6.2. `settings.gradle`

```groovy
rootProject.name = 'tx-proxy-demo'
```

### 6.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'application'
}

group = 'example'
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
    implementation platform('org.springframework:spring-framework-bom:6.1.14')
    implementation 'org.springframework:spring-context'
    implementation 'org.springframework:spring-aop'
    implementation 'org.springframework:spring-jdbc'
    implementation 'org.springframework:spring-tx'

    runtimeOnly 'com.h2database:h2:2.2.224'
}

application {
    mainClass = 'example.txproxy.ProxyTransactionsDemo'
}
```

Dependency breakdown: `spring-context` instantiates beans and configuration; `spring-aop` builds proxies/advice; `spring-tx` provides transaction annotations/interceptor; `spring-jdbc` supplies `JdbcTemplate` and `DataSourceTransactionManager`; H2 is the in-memory database. Sharing the Spring BOM avoids version mismatches.

### 6.4. `src/main/java/example/txproxy/ProxyTransactionsDemo.java`

```java
package example.txproxy;

import javax.sql.DataSource;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class ProxyTransactionsDemo {

    public interface TransferOperations {
        void transfer(long from, long to, long amount);
        boolean transactionActive();
        boolean callInternally();
    }

    public static class TransferService implements TransferOperations {
        private final JdbcTemplate jdbc;

        public TransferService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Override
        @Transactional
        public void transfer(long from, long to, long amount) {
            if (amount <= 0 || from == to) {
                throw new IllegalArgumentException("Invalid transfer");
            }

            int debited = jdbc.update(
                "UPDATE wallets SET balance = balance - ? " +
                "WHERE id = ? AND balance >= ?",
                amount, from, amount
            );
            if (debited != 1) {
                throw new IllegalStateException(
                    "Source missing or insufficient funds"
                );
            }

            int credited = jdbc.update(
                "UPDATE wallets SET balance = balance + ? WHERE id = ?",
                amount, to
            );
            if (credited != 1) {
                throw new IllegalStateException("Destination missing");
            }
        }

        @Override
        @Transactional(readOnly = true)
        public boolean transactionActive() {
            return TransactionSynchronizationManager
                .isActualTransactionActive();
        }

        @Override
        public boolean callInternally() {
            return this.transactionActive();
        }

        @Transactional(readOnly = true)
        public boolean classOnlyTransactional() {
            return TransactionSynchronizationManager
                .isActualTransactionActive();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Infrastructure {

        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_proxy_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public TransferService transferService(JdbcTemplate jdbc) {
            return new TransferService(jdbc);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = false)
    @Import(Infrastructure.class)
    public static class JdkMode {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    @Import(Infrastructure.class)
    public static class CglibMode {
    }

    private static String balances(JdbcTemplate jdbc) {
        return String.join(", ", jdbc.query(
            "SELECT id, balance FROM wallets ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + "=" + rs.getLong("balance")
        ));
    }

    private static void demonstrate(Class<?> configuration) {
        try (AnnotationConfigApplicationContext ctx =
                new AnnotationConfigApplicationContext(configuration)) {

            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            jdbc.execute("DROP TABLE IF EXISTS wallets");
            jdbc.execute(
                "CREATE TABLE wallets (" +
                "id BIGINT PRIMARY KEY, " +
                "balance BIGINT NOT NULL CHECK (balance >= 0))"
            );
            jdbc.update(
                "INSERT INTO wallets (id, balance) VALUES (?, ?)",
                1L, 1000L
            );
            jdbc.update(
                "INSERT INTO wallets (id, balance) VALUES (?, ?)",
                2L, 500L
            );

            Object bean = ctx.getBean("transferService");
            TransferOperations service = (TransferOperations) bean;

            String proxyType = AopUtils.isJdkDynamicProxy(bean) ? "JDK"
                : AopUtils.isCglibProxy(bean) ? "CGLIB" : "NONE";

            System.out.println("Proxy=" + proxyType);
            System.out.println(
                "Assignable to TransferService=" +
                (bean instanceof TransferService)
            );
            System.out.println(
                "External transaction=" + service.transactionActive()
            );
            System.out.println(
                "Self-invocation transaction=" + service.callInternally()
            );

            if (bean instanceof TransferService concrete) {
                System.out.println(
                    "Class-only method transaction=" +
                    concrete.classOnlyTransactional()
                );
            } else {
                System.out.println(
                    "Class-only method transaction=not exposed"
                );
            }

            service.transfer(1L, 2L, 200L);
            System.out.println("After commit=" + balances(jdbc));

            try {
                service.transfer(1L, 999L, 50L);
            } catch (IllegalStateException expected) {
                System.out.println(
                    "Expected error=" + expected.getMessage()
                );
            }
            System.out.println("After rollback=" + balances(jdbc));
        }
    }

    public static void main(String[] args) {
        demonstrate(JdkMode.class);
        demonstrate(CglibMode.class);
    }
}
```

### 6.5. How to run

Use the Gradle wrapper in your initialized project, or an installed Gradle with a compatible JDK/toolchain:

```bash
./gradlew run
```

On Windows PowerShell:

```powershell
.\gradlew.bat run
```

If you created the project manually and do not have a wrapper yet, you can use `gradle run` with Gradle installed, or generate the wrapper first. This command executes `application.mainClass` above; **do not run `javac`/`java` directly without Spring and H2 on the classpath**.

The meaningful stdout of the program, ignoring Spring/Gradle logs, is expected to be:

```text
Proxy=JDK
Assignable to TransferService=false
External transaction=true
Self-invocation transaction=false
Class-only method transaction=not exposed
After commit=1=800, 2=700
Expected error=Destination missing
After rollback=1=800, 2=700
Proxy=CGLIB
Assignable to TransferService=true
External transaction=true
Self-invocation transaction=false
Class-only method transaction=true
After commit=1=800, 2=700
Expected error=Destination missing
After rollback=1=800, 2=700
```

### 6.6. Line-by-line explanation of the output

**`Proxy=JDK` then `Proxy=CGLIB`:** In each context, `AopUtils` identifies the corresponding runtime proxy. Do not rely on internal class name strings like `$Proxy42` or `$$SpringCGLIB$$0`; auto-generated names can vary.

**`Assignable to TransferService`:** The JDK proxy only implements `TransferOperations`, so `instanceof TransferService` is false. The CGLIB proxy is a subclass, so it is assignable to `TransferService`. Both can be cast to `TransferOperations`.

**`External transaction=true`:** `service.transactionActive()` is invoked from the caller through the proxy; the interceptor opens a read-only transaction and `TransactionSynchronizationManager.isActualTransactionActive()` sees an active transaction. Read-only here is a hint, not a guarantee that the DB cannot perform writes.

**`Self-invocation transaction=false`:** `service.callInternally()` goes through the proxy, yet this method **has no `@Transactional`**; it calls `this.transactionActive()` inside the target. The direct call does not pass back through the proxy, so `transactionActive()`'s annotation is not processed by the interceptor. Since there is no outer transaction in the demo, the result is false in both modes.

**`Class-only method transaction`:** `classOnlyTransactional()` has `@Transactional` but **is not declared on the interface**. The JDK proxy does not expose this method. The CGLIB proxy is a subclass and the method is public non-final, so it can be called via the concrete type; the interceptor opens a transaction and returns true.

**`After commit`:** Debits 200 from wallet 1 and credits 200 to wallet 2 in **one transaction**; since both SQL statements succeed, the transaction commits and balances are 800 and 700.

**`Expected error` then `After rollback`:** Transferring to wallet 999 throws `IllegalStateException` after temporarily debiting 50 from the source wallet. By default Spring rolls back when an unchecked exception escapes through the transactional interceptor; balances after rollback remain 800 and 700. This holds in both proxy modes.

**Why reinitialize the table twice?** `demonstrate(...)` runs with two separate `ApplicationContext`s to demonstrate each proxy mode, and each pass `DROP`/`CREATE`s the table and inserts initial data. In-memory H2 is kept alive within the process via `DB_CLOSE_DELAY=-1`, so resetting the fixture ensures accurate stdout comparison across both passes.

### 6.7. Four technical details that make the demo genuinely meaningful

1. **`@Transactional` is on the implementation method** so Spring's transaction metadata source can locate it under both proxy types.
2. **Caller fetches the bean by name and casts to the interface**, because trying to look up `TransferService.class` in JDK mode would not match the bean's runtime type.
3. **Two contexts configure different proxy types** via `@EnableTransactionManagement`, avoiding multiple auto-proxy configurations forcing a single global setting.
4. **A real JDBC transaction manager and DB checks are used**, so commit/rollback results reflect actual transactional behavior, not merely `instanceof` checks on an object.

## 7. Why Does `this.method()` Bypass Transactions on Both Proxies?

Suppose a service looks like:

```java
@Service
public class BillingService {

    public void invoiceAndCharge() {
        charge(); // Internal call via 'this', bypassing the proxy.
    }

    @Transactional
    public void charge() {
        // SQL statements requiring a transaction.
    }
}
```

This illustrative snippet highlights a design bug, not a standalone runnable program. If an external caller invokes `invoiceAndCharge()` through the proxy and the outer method is **non-transactional**, and the target internally calls `charge()` directly, `@Transactional` on `charge()` does not automatically start a transaction. CGLIB cannot fix this either, because the called method's advice is not triggered by self-invocation.

There are three architectural options:

- **Place `@Transactional` on the appropriate entry point:** if the entire `invoiceAndCharge()` must be one atomic unit, place the annotation there.
- **Extract to another Spring bean:** `InvoiceService` calls `ChargeService.charge()` via an injected bean; the call to `ChargeService` goes through its own proxy.
- **Use `TransactionTemplate` when a transaction boundary is needed inside the same class:** invoke an explicit transactional callback rather than expecting self-invocation to be intercepted by a proxy.

Calling `((BillingService) AopContext.currentProxy()).charge()` is discouraged as a default solution. It tightly couples business logic to the AOP framework, requires enabling `exposeProxy`, and becomes awkward if the runtime proxy is interface-based.

### What if an outer transaction already exists?

If `invoiceAndCharge()` **already** opened a transaction, `this.charge()` can still execute SQL inside the **existing** transaction because Spring binds the JDBC connection to the thread. However, `charge()`'s own metadata (such as `REQUIRES_NEW`, isolation, rollback rules) **is not evaluated on the internal call**. Thus the accurate conclusion is "self-invocation does not trigger the called method's advice", not "every self-invocation runs outside any transaction".

## 8. `final`, `private`, and Method Visibility: Limits by Proxy Type

Java example:

```java
public final class FinalPaymentService {
    @Transactional
    public void pay() {
        // ...
    }
}
```

CGLIB cannot subclass `FinalPaymentService` because the class is `final`. A JDK proxy can still implement an **interface** that a final class implements; that does not require subclassing the final class. But if the class lacks a suitable interface, a JDK proxy cannot help.

A `final` method:

```java
public class PaymentService {
    @Transactional
    public final void pay() {
        // ...
    }
}
```

CGLIB cannot override `pay()`, so it cannot apply the interceptor that way. If `pay()` is a public method of an interface proxied by JDK, calls through the interface can be advised because the JDK proxy intercepts **on the interface proxy object**, without overriding the `final` method on the target.

A `private` method:

```java
public class PaymentService {
    @Transactional
    private void persist() {
        // ...
    }
}
```

Neither a JDK interface proxy nor a CGLIB class proxy can intercept direct calls to `private persist()` under the Spring AOP proxy model. Do not try to rescue the transaction simply by switching `proxyTargetClass=true`. Place the transactional boundary on a method callable from outside through the proxy.

**Version note:** Spring Framework 6+ allows handling certain `protected`/package-visible transactional methods with class-based proxies, whereas JDK interface proxies remain restricted to public methods declared on interfaces. If you want a consistent "public-only" rule across both forms, Spring provides `AnnotationTransactionAttributeSource(true)` to configure `publicMethodsOnly`. Avoid relying on non-public methods when code must switch flexibly between proxy types.

## 9. Placing Annotations on Interface vs. Implementation?

You can annotate an interface method with `@Transactional`:

```java
public interface LedgerOperations {
    @Transactional
    void settle(long ledgerId);
}
```

Modern Spring Framework can recognize transaction metadata from interfaces in appropriate proxy configurations. However, in Java, interface annotations **are not inherited via `@Inherited` the way class annotations are**, and switching to AspectJ weaving can introduce differences in metadata detection.

Therefore, Spring documentation recommends preferring `@Transactional` on the **concrete implementation class/method**:

```java
public interface LedgerOperations {
    void settle(long ledgerId);
}

@Service
public class LedgerService implements LedgerOperations {

    @Override
    @Transactional
    public void settle(long ledgerId) {
        // ...
    }
}
```

This is a separate illustrative example. Placing `@Transactional` on the implementation method does not prevent a JDK proxy from working: when an invocation originates from the interface method, Spring transaction attribute resolution can still locate metadata on the **specific target method**.

When refactoring from interface proxies to class proxies changes behavior, check annotation placement, method visibility, `final` modifiers, AOP policy, and rollback tests together. Do not jump to concluding that interface annotations "only ever work with JDK proxies"; exact behavior depends on version/mechanism, especially compared to AspectJ weaving.

## 10. Injection, Casting, Reflection, and Runtime Proxy Inspection

With interface-dependent code:

```java
@Service
public class CheckoutController {
    private final PaymentService service;

    public CheckoutController(PaymentService service) {
        this.service = service;
    }
}
```

This pattern supports both JDK proxies and CGLIB proxies, provided Spring has a matching bean.

Conversely, if another component requires the concrete implementation:

```java
@Service
public class CheckoutController {
    private final PaymentServiceImpl service;

    public CheckoutController(PaymentServiceImpl service) {
        this.service = service;
    }
}
```

In JDK proxy mode, the proxy bean may not be assignable to `PaymentServiceImpl`. Depending on the lookup path and context, you may encounter a missing-bean-by-type error or a runtime type mismatch. The first fix is to **inject the interface** the component actually needs. Only switch to CGLIB if depending on the concrete class is deliberate.

### Inspecting with Spring APIs

```java
Object bean = applicationContext.getBean("transferService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(AopUtils.isJdkDynamicProxy(bean));
System.out.println(AopUtils.isCglibProxy(bean));
```

This snippet belongs in an application that already has an `ApplicationContext`; import `org.springframework.aop.support.AopUtils`. `isAopProxy` returns true when the object is a Spring AOP proxy; the other two methods distinguish JDK vs. CGLIB. **Having a proxy does not prove transactions work**: you must observe actual calls, transaction context, and DB commit/rollback.

You can also inspect:
- `bean instanceof PaymentService` and `bean instanceof PaymentServiceImpl`;
- `org.springframework.transaction` logs at DEBUG/TRACE when investigating begin/commit/rollback;
- bean definitions and the selected transaction manager;
- active transactions inside the method via `TransactionSynchronizationManager.isActualTransactionActive()` for JDBC.

In tests, avoid asserting specific runtime class names since generated suffixes can change. Prefer `AopUtils` and behavioral transaction assertions.

## 11. Avoiding Confusion Between Spring AOP Proxies and AspectJ Weaving

With the same `@Transactional` annotation, Spring can operate in two major modes:

| Mode | Mechanism | Consequence |
| --- | --- | --- |
| `mode = AdviceMode.PROXY` | Spring AOP proxy, using JDK or CGLIB | Only method calls going through the proxy receive transactional advice |
| `mode = AdviceMode.ASPECTJ` | Compile-time/load-time weaving with AspectJ | Target bytecode is woven, allowing advice even on internal calls with proper setup |

For the question "JDK proxy or CGLIB proxy", we are on the **PROXY** branch. `proxyTargetClass` is not a switch to enable AspectJ weaving. If you truly need to intercept self-invocation without changing service architecture, AspectJ is a separate technical path requiring `spring-aspects` and weaving setup; it cannot be substituted merely with `proxyTargetClass=true`.

In most standard CRUD/transaction services, clear business boundaries via public methods on Spring beans and testability are sufficient. Moving an entire system to weaving should have a dedicated architectural rationale and test suite.

## 12. Common Pitfalls and Fixes

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `@Autowired MyServiceImpl` fails under JDK proxy | Proxy bean implements the interface but does not extend the implementation | Inject the `MyService` interface or intentionally choose class proxies |
| Implementation-only method cannot be called | JDK proxy does not expose methods outside the proxied interface | Add the method to the interface if it is API, or use a class proxy |
| `proxyTargetClass=false` set yet CGLIB appears | Target lacks interfaces or another AOP config forces class proxies | Check all proxy creator settings and runtime `AopUtils` |
| `final` class fails to get CGLIB proxy | Cannot subclass target | Remove `final` if appropriate, or use an interface proxy |
| `@Transactional` on a `final` method has no effect under CGLIB | Cannot override method | Remove `final` on advised method or move the boundary |
| `@Transactional` on a `private` method does not work | Private methods cannot be intercepted via proxy | Put transaction on a public service entry point |
| Calling transactional method via `this` starts no new begin | Self-invocation bypasses advice | Extract a bean, annotate the entry point, or use a template |
| JDBC update ran then failed without rollback | Transaction interceptor did not run; statements auto-committed | Check proxy, manager, invocation path, and rollback tests |
| Proxy exists yet DB result is unexpected | Business logic, SQL/constraint, or rollback rule issue unrelated to proxy type | Check transaction metadata, exceptions, and actual DB |
| Choosing `CGLIB` because it is "safer" | Proxy type does not replace transaction logic | Choose based on API contract and method visibility |
| Checking only `getClass().getName()` | Dynamically generated names are not a stable API | Use `AopUtils`, `instanceof`, and behavioral tests |

## 13. Self-Check Questions

1. A service has an interface and `@EnableTransactionManagement(proxyTargetClass=false)`; what does Spring usually create? **A JDK dynamic proxy** if no other proxy config forces CGLIB.
2. What happens to an implementation without an interface when `proxyTargetClass=false`? **Spring can still use a class-based proxy**, if the class is eligible.
3. `PaymentServiceImpl` has a `rebuild()` method not on `PaymentService`. Can a caller holding a `PaymentService` JDK proxy call `rebuild()`? **Not through that interface proxy**.
4. Why can concrete-class injection fail with a JDK proxy? **A JDK proxy does not extend the implementation class**.
5. Can CGLIB intercept a `final` method? **No**, because it cannot override it.
6. Does switching from JDK to CGLIB make `this.method()` go through the proxy automatically? **No**.
7. Does `@Transactional` placed on an implementation method work when Spring uses a JDK proxy? **Yes**, for public methods declared on the interface when transaction infrastructure is enabled.
8. Why doesn't `@Transactional` guarantee full ACID just because a proxy exists? **The proxy only wraps the call with transaction advice; the DB, transaction manager, participating resources, isolation, rollback rules, and invariants determine data behavior**.
9. Does `AopUtils.isCglibProxy(bean) == true` prove commit/rollback works properly? **No**. DB tests are required.
10. Which proxy type does Spring Boot usually select in AOP auto-configuration? **CGLIB**, unless configuration or another AOP mechanism changes it.

## 14. Checklist for Choosing a Proxy for Transaction Services

1. Identify which public business methods form the service's true API; can the contract be declared via an interface?
2. Check whether callers inject interfaces or concrete implementations; avoid accidental coupling to a proxy type.
3. Confirm `@Transactional` is placed on an eligible concrete class/method, transaction management is enabled, and the right manager is chosen.
4. For JDK proxies, ensure advised methods are **public and declared on the proxied interface**.
5. For CGLIB, check `final` classes/methods, `private`, package visibility, and Java Module System constraints.
6. Audit for self-invocation, `new`-instantiated calls, `@PostConstruct`, and tasks bypassing the bean proxy.
7. Review all `@EnableTransactionManagement`, `@EnableAspectJAutoProxy`, related AOP configs, and Boot's `spring.aop.proxy-target-class`.
8. Verify the actual proxy type with `AopUtils`, then verify active transactions inside methods and commit/rollback against the DB.
9. Keep transaction boundaries short and domain-aligned; use DB constraints/conditional SQL to protect consistency rather than relying on proxy type.

## Official References

- Spring Framework 6.2 — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- Spring Framework 6.2 — Understanding AOP Proxies: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html#proxying-introduction-understanding-aop-proxies
- Spring Framework 6.2 — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework 6.2 — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html
- Spring Boot — Aspect-Oriented Programming: https://docs.spring.io/spring-boot/reference/features/aop.html