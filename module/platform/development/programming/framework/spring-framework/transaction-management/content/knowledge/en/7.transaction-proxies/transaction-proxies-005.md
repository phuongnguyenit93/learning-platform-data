# Self-Invocation Bypasses Interception in Spring Transaction Proxy Mode

## 1. The Phenomenon: `@Transactional` Is Present Yet the Method Runs Outside a Transaction

In Spring Framework, a method annotated with `@Transactional` **does not automatically become a transactional block just because Java invokes it**. In the default transaction mode (`mode = PROXY`), the annotation is metadata used by the **Spring AOP proxy** and `TransactionInterceptor` when a call passes **through the bean's proxy**.

**Self-invocation** is a call from one method of an object to another method **on the same object**, via `this.otherMethod()` or the shorthand `otherMethod()`. Once execution has entered the **target object**, a self-invocation calls the target directly: it **does not route back through the proxy**, so the transaction advice attached to the inner method **is not executed again**. This is a fundamental rule of Spring AOP proxies, applying equally to JDK interface-based proxies and subclass-based (CGLIB) proxies.

Conceptual example:

~~~java
@Service
public class OrderService {
    public void placeOrder() {
        this.persistOrder(); // Call within the same instance: bypasses persistOrder's advice.
    }

    @Transactional
    public void persistOrder() {
        // This self-call does not open a new transaction by itself.
    }
}
~~~

This is an illustrative snippet, without database operations or a standalone runnable program. If `placeOrder()` **is not inside another transaction**, calling `persistOrder()` this way does not make `@Transactional` on `persistOrder()` take effect. Conversely, if the caller invokes `orderService.persistOrder()` **through the Spring proxy** and transaction conditions are properly configured, advice has the chance to create or join a transaction.

**Remember accurately:** self-invocation bypasses the **interception point of the called method**, not that internal calls can never run inside a transaction. If the outer method already had a transaction opened by the proxy, inner code can still use that transaction. This lesson proves both scenarios.

## 2. Proxy and Target Have Distinct Roles

A Spring-managed bean can be presented to callers via a **proxy**. The proxy is responsible for running relevant interceptors before delegating to the method on the target. For transaction advice, the typical sequence is:

1. Caller holds a bean reference provided by Spring (`@Autowired`, constructor injection, or `ApplicationContext.getBean`).
2. Caller invokes a method **through the proxy**.
3. `TransactionInterceptor` reads `@Transactional` metadata on the matching method, selects a transaction manager, and begins/joins a transaction per propagation.
4. Proxy delegates the method call to the **target**.
5. When the target returns or throws an exception, the interceptor decides commit/rollback based on transaction status and rollback rules.

When the target itself calls `this.inner()`, steps 2–3 **do not happen a second time** for `inner()`. A plain Java call does not automatically "see" annotations and apply AOP.

### 2.1. Diagram of the two call paths

~~~mermaid
flowchart TD
    A["Caller from another bean"] --> B["Spring AOP proxy"]
    B --> C["TransactionInterceptor<br/>checks @Transactional"]
    C --> D["Target.outer()"]
    D -->|"this.inner()"| E["Target.inner()"]
    E --> F["Data access code"]
    D -.->|"Internal call bypasses"| G["Proxy advice for inner()"]
    H["Caller from another bean"] -->|"proxy.inner()"| I["Spring AOP proxy"]
    I --> J["TransactionInterceptor<br/>for inner()"]
    J --> K["Target.inner()"]
~~~

Top branch: `outer()` was called through the proxy, but `inner()` is called directly inside the target. Bottom branch: another bean calls `inner()` through the proxy, allowing Spring to process `inner()`'s own transaction metadata.

Do not interpret this diagram as "a new proxy is created for every call". Normally the bean proxy already exists; the difference lies in **the call path**.

### 2.2. CGLIB does not fix self-invocation automatically

There are two common proxy forms:

| Proxy | When common | Self-invocation |
| --- | --- | --- |
| JDK dynamic proxy | Bean is proxied via a suitable interface | `this.inner()` from target still bypasses advice |
| Class-based proxy (typically CGLIB) | Bean is proxied via subclass, e.g. service without interface | `this.inner()` from target still bypasses advice |

Changing `proxyTargetClass = true` **does not turn an internal call into a call through the proxy**. Class-based proxies also have limitations on non-overridable methods such as `final` or `private`; that is a separate issue, not the root cause of self-invocation.

## 3. What Does `@Transactional` Actually Do When Going Through a Proxy?

`@Transactional` normally defaults to `REQUIRED` propagation: if no matching transaction exists, the manager opens a new one; if one already exists, the method joins the current transaction. When the method finishes, the interceptor decides commit or rollback based on transaction state and rollback rules. Under common Spring Framework defaults, `RuntimeException` and `Error` trigger rollback, whereas checked exceptions do not trigger rollback unless configured otherwise.

Those behaviors are triggered **at an advised transaction boundary**. That does not mean annotations are re-evaluated on every method call inside the target. Thus a self-call can nullify the specific declarations of:

- `propagation = REQUIRES_NEW`: does not open an independent physical transaction for inner.
- `propagation = MANDATORY`: does not enforce the mandatory "must have a transaction" check at the inner boundary.
- `propagation = NEVER`: does not enforce the "must not have a transaction" check for inner.
- `rollbackFor` / `noRollbackFor`: does not evaluate inner's rollback rules at the self-call site.
- `readOnly`, `isolation`, `timeout`, `transactionManager`: does not apply **inner's own** transaction attributes merely because inner carries the annotation.
- `NESTED`: does not automatically establish a nested scope/savepoint per inner's annotation.

If the caller already opened a transaction, SQL statements inside inner **can still participate in the existing transaction**, provided they use the right resource/transaction manager. That does not prove inner's `@Transactional` was executed.

## 4. Three Easily Confused Cases: No Transaction, Existing Outer Transaction, and Independent New Transaction

### 4.1. Outer has no transaction; only inner has `@Transactional`

~~~java
@Service
class RegistrationService {
    public void register() {
        saveRegistration();
    }

    @Transactional
    public void saveRegistration() {
        // Write to database
    }
}
~~~

If an external caller invokes `register()` via the Spring bean, `register()` has no transaction metadata of its own, and `saveRegistration()` is called **directly on the target**. A common outcome with JDBC auto-commit is that write statements may commit per statement, rather than being grouped into the transaction the author expected on `saveRegistration()`.

The conclusion here is conditional: **assuming no outer transaction from another source**. A test transaction, caller-opened transaction, or `TransactionTemplate` callback can change the picture. Do not claim "self-invocation always makes transactionActive=false".

### 4.2. Outer already has a transaction; inner uses `@Transactional(REQUIRED)`

~~~java
@Service
class OrderService {
    @Transactional
    public void outer() {
        inner();
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void inner() {
        // Code here runs inside the transaction opened by outer,
        // but inner's annotation gets no separate advice execution.
    }
}
~~~

When the caller passes through the proxy on `outer()`, the manager opens/joins a transaction. `inner()` is a self-call, so it **is not intercepted separately**. Its database operations can still use outer's connection; commit/rollback is decided at the outer boundary.

This case is easy to misread because checking `TransactionSynchronizationManager.isActualTransactionActive()` inside inner typically returns `true`. That flag only reports that **the current transaction context is active**; it does not prove interception occurred for inner.

If inner is merely a helper method and you genuinely want it in the same transaction as outer, this can be a completely valid design. There is no need to add `@Transactional` on a helper if no separate boundary is required.

### 4.3. Outer has a transaction; inner requests `REQUIRES_NEW`

~~~java
@Service
class BillingService {
    @Transactional
    public void outer() {
        this.writeAuditIndependently();
        throw new IllegalStateException("outer failed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAuditIndependently() {
        // Author expects audit to commit independently.
    }
}
~~~

Even though inner specifies `REQUIRES_NEW`, self-invocation bypasses inner's advice. Thus the audit-writing code still runs in outer's transaction if using the same resource. When outer throws `RuntimeException` and rolls back, the audit record may roll back with outer; **no independent transaction was created by inner's annotation**.

For genuine `REQUIRES_NEW`, the call must pass through a **valid transactional proxy** (such as another service bean), or use a programmatic transaction mechanism like `TransactionTemplate`.

## 5. Special Trap: Catching Exceptions Inside Outer

Consider another scenario:

~~~java
@Service
class InventoryService {
    @Transactional
    public void outer() {
        try {
            inner();
        } catch (IllegalArgumentException ex) {
            // Decide to continue without rethrowing.
        }
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void inner() {
        throw new IllegalArgumentException("rejected");
    }
}
~~~

If calling `inner()` is a self-call, there is no separate `TransactionInterceptor` for inner. The exception is caught in `outer()`, and outer returns normally; **if there is no other rollback-only cause**, outer's transaction can commit. Do not assume "inner has `@Transactional` and throws a RuntimeException, so outer will definitely roll back".

If you refactor inner into **another bean**, called through the proxy with `REQUIRED` and the same physical transaction, inner's interceptor can mark the shared transaction **rollback-only** when the exception crosses inner's boundary. When outer catches the exception and still tries to commit, it may receive `UnexpectedRollbackException`. Catching the exception in outer does not clear an existing rollback-only marker.

This difference is one reason you must test **DB outcomes after the transaction completes**, rather than only checking whether an exception was caught or whether logs printed "active=true".

## 6. Runnable Java 17+ Example: Comparing Self-Call, Proxy-Call, and `REQUIRES_NEW`

The example below uses Spring Boot 3.3.5, Spring JDBC, in-memory H2, and Java 17+. There are four files; it runs as a command-line application with no web server needed. An `account` table holds one row with initial balance 100. The program demonstrates:

1. Self-call to a `@Transactional` method when outer has no transaction: the first UPDATE may auto-commit; the exception does not roll it back.
2. Calling that same method through the Spring proxy: a transaction is created, and the exception triggers rollback.
3. Self-call to a `REQUIRES_NEW` method from a transactional outer method: inner does not create an independent transaction; outer rollback discards the change.
4. Calling a `REQUIRES_NEW` method on **another bean** from outer: inner commits independently; outer rollback does not undo inner's committed change.

### 6.1. File structure

~~~text
self-invocation-demo/
├── pom.xml
└── src/main/java/example/selfinvoke/
    ├── SelfInvocationApplication.java
    ├── AccountService.java
    └── IndependentWriter.java
~~~

### 6.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>self-invocation-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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
~~~

### 6.3. `SelfInvocationApplication.java`

~~~java
package example.selfinvoke;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class SelfInvocationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelfInvocationApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource source) {
        return new JdbcTransactionManager(source);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, AccountService account) {
        return args -> {
            jdbc.execute("CREATE TABLE account (id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.update("INSERT INTO account (id, amount) VALUES (?, ?)", 1, 100);
            System.out.println("START=" + amount(jdbc));

            account.callSelf();
            System.out.println("AFTER_SELF=" + amount(jdbc));

            try {
                account.incrementThenFail(10); // Caller -> proxy -> target
            } catch (IllegalStateException ex) {
                System.out.println("PROXY_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_PROXY=" + amount(jdbc));

            try {
                account.outerSelfNew();
            } catch (IllegalStateException ex) {
                System.out.println("SELF_NEW_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_SELF_REQUIRES_NEW=" + amount(jdbc));

            try {
                account.outerOtherBean();
            } catch (IllegalStateException ex) {
                System.out.println("BEAN_NEW_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_SEPARATE_REQUIRES_NEW=" + amount(jdbc));
        };
    }

    private static Integer amount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT amount FROM account WHERE id = ?", Integer.class, 1
        );
    }
}
~~~

### 6.4. `AccountService.java`

~~~java
package example.selfinvoke;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class AccountService {

    private final JdbcTemplate jdbc;
    private final IndependentWriter writer;

    public AccountService(JdbcTemplate jdbc, IndependentWriter writer) {
        this.jdbc = jdbc;
        this.writer = writer;
    }

    // This method does not declare a transaction.
    public void callSelf() {
        try {
            this.incrementThenFail(10); // Bypasses inner's TransactionInterceptor.
        } catch (IllegalStateException ex) {
            System.out.println("SELF_CAUGHT=" + ex.getMessage());
        }
    }

    @Transactional
    public void incrementThenFail(int delta) {
        System.out.println(
            "INNER_TX_ACTIVE="
                + TransactionSynchronizationManager.isActualTransactionActive()
        );
        jdbc.update(
            "UPDATE account SET amount = amount + ? WHERE id = ?", delta, 1
        );
        throw new IllegalStateException("boom");
    }

    @Transactional
    public void outerSelfNew() {
        this.incrementRequiresNew(20); // Inner annotation is bypassed.
        throw new IllegalStateException("outer-fail");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void incrementRequiresNew(int delta) {
        System.out.println(
            "SELF_NEW_TX_ACTIVE="
                + TransactionSynchronizationManager.isActualTransactionActive()
        );
        jdbc.update(
            "UPDATE account SET amount = amount + ? WHERE id = ?", delta, 1
        );
    }

    @Transactional
    public void outerOtherBean() {
        writer.incrementIndependently(20); // Goes through the other bean's proxy.
        throw new IllegalStateException("outer-fail");
    }
}
~~~

### 6.5. `IndependentWriter.java`

~~~java
package example.selfinvoke;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentWriter {

    private final JdbcTemplate jdbc;

    public IndependentWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void incrementIndependently(int delta) {
        jdbc.update(
            "UPDATE account SET amount = amount + ? WHERE id = ?", delta, 1
        );
    }
}
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

The application prints these lines in order. Spring Boot/Hikari may emit additional startup logs:

~~~text
START=100
INNER_TX_ACTIVE=false
SELF_CAUGHT=boom
AFTER_SELF=110
INNER_TX_ACTIVE=true
PROXY_CAUGHT=boom
AFTER_PROXY=110
SELF_NEW_TX_ACTIVE=true
SELF_NEW_CAUGHT=outer-fail
AFTER_SELF_REQUIRES_NEW=110
BEAN_NEW_CAUGHT=outer-fail
AFTER_SEPARATE_REQUIRES_NEW=130
~~~

**Explanation of each result:**

- **START=100:** initial data outside any service transaction.
- **INNER_TX_ACTIVE=false:** `callSelf()` has no transaction, and `this.incrementThenFail(...)` bypasses advice. `JdbcTemplate` runs the UPDATE on a normal connection; with H2 and default JDBC settings in the example, the statement auto-commits.
- **AFTER_SELF=110:** even though the annotated method throws `IllegalStateException`, transaction advice did not run for this self-call, so there is no rollback for that method; the +10 update persists.
- **INNER_TX_ACTIVE=true** on the second call: the caller invokes `account.incrementThenFail(...)` through the Spring bean proxy. Spring opens a transaction, the +10 UPDATE runs inside it, and the exception triggers rollback.
- **AFTER_PROXY=110:** rollback preserves the balance from after the self-call.
- **SELF_NEW_TX_ACTIVE=true:** `outerSelfNew()` had a transaction opened by the proxy. The internal self-call creates no other transaction yet still sees the outer transaction, so the active flag is true.
- **AFTER_SELF_REQUIRES_NEW=110:** the inner method annotated `REQUIRES_NEW` ran directly on the target; the +20 update rolls back along with the outer transaction.
- **AFTER_SEPARATE_REQUIRES_NEW=130:** `IndependentWriter` is a separate bean. The call from `AccountService` goes through writer's proxy, `REQUIRES_NEW` opens an independent transaction and commits +20. The later exception in outer rolls back the outer transaction without undoing the committed +20.

With genuine `REQUIRES_NEW`, the transaction manager usually needs **another connection** while outer holds one. The example uses Boot's default Hikari pool, which suffices for a single thread; in high-concurrency systems, size the pool carefully to avoid exhausting connections waiting on each other.

**The decisive observation point** is the balance after the transaction completes. Looking only at `INNER_TX_ACTIVE=true` or `SELF_NEW_TX_ACTIVE=true` is not enough to conclude the inner annotation was intercepted.

## 7. Recommended Fix: Extract the Transaction Boundary into a Separate Bean

When a helper needs a **different** propagation or rollback policy from the caller method, design it as a separate service/bean with a clear boundary:

~~~mermaid
flowchart LR
    A["Client"] --> B["OrderService proxy"]
    B --> C["OrderService.outer()"]
    C --> D["AuditService proxy"]
    D --> E["TransactionInterceptor<br/>REQUIRES_NEW"]
    E --> F["AuditService.writeAudit()"]
    F --> G[("Database")]
~~~

Structurally standalone illustrative example (`Order`/`Audit` types and repositories assumed):

~~~java
@Service
class OrderService {
    private final AuditService audit;

    OrderService(AuditService audit) {
        this.audit = audit;
    }

    @Transactional
    public void submit(Order order) {
        // Save order in outer transaction.
        audit.writeAudit(order.id());
    }
}

@Service
class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(long orderId) {
        // Save audit in an independent physical transaction.
    }
}
~~~

Each service receives dependencies via constructor. Spring manages both beans, and `OrderService` invokes **`AuditService`'s bean proxy** instead of `this.writeAudit()`. Transaction boundaries become clear to read, test, and resource-manage.

However, do not use `REQUIRES_NEW` just to "fix a self-call" if the business domain truly requires atomicity across both the order and the audit. When inner commits independently, an outer rollback **no longer undoes** inner; an audit record could exist while the order never committed. Choose propagation based on business requirements first, then pick the bean-calling architecture.

## 8. How to Fix When No Separate Transaction Is Needed

Not every self-call is a bug. If the requirement is simply that all steps share **the same transaction**, place `@Transactional` on the **public method serving as the entry point from another bean**, and let internal helpers do the work:

~~~java
@Service
class CheckoutService {
    @Transactional
    public void checkout() {
        reserveStock();
        chargeAccount();
        saveInvoice();
    }

    private void reserveStock() { /* Same transaction as checkout */ }
    private void chargeAccount() { /* Same transaction as checkout */ }
    private void saveInvoice() { /* Same transaction as checkout */ }
}
~~~

This is structural pseudo-code (no persistence code), not a standalone application. Condition: `checkout()` is called **through the Spring proxy** and repositories use resources matching the manager. Private helpers **need no separate annotation** when they are merely steps in the same transaction.

Benefit: readers see one clear transaction boundary. If a helper later needs its own `REQUIRES_NEW`, `NESTED`, timeout, or rollback rule, extract that boundary properly instead of merely slapping an annotation onto the existing helper.

## 9. Other Approaches and Limitations

### 9.1. `TransactionTemplate`: explicitly creating a scope inside the same bean

`TransactionTemplate` uses the transaction manager directly via a callback; it does not need a call through a Spring AOP proxy to activate a transaction. Hence it is a good choice if code wants to keep a single bean while needing an explicit boundary around a block of work.

~~~java
// Snippet inside a Spring bean that already has JdbcTemplate jdbc
// and PlatformTransactionManager transactionManager.
TransactionTemplate tx = new TransactionTemplate(transactionManager);
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);

tx.executeWithoutResult(status -> {
    jdbc.update(
        "UPDATE account SET amount = amount + ? WHERE id = ?", 20, 1
    );
});
~~~

Imports for the snippet: `org.springframework.transaction.support.TransactionTemplate` and `org.springframework.transaction.TransactionDefinition`. Inside an outer `@Transactional` method, this callback can create an independent transaction matching `REQUIRES_NEW`; the transaction manager must support suspend/resume. Note only that the template is a **programmatic transaction boundary** and code directly depends on the transaction API; many declarative service apps remain easier to read when extracting a bean.

### 9.2. Self-injection: calling through a proxy reference to the bean itself

Spring AOP can support calling the proxy via a self-injected reference—for example, a lazily resolved injected reference—and then calling `self.inner()`. However, you must ensure `self` is truly the **proxy**, not the raw target, while avoiding circular dependency issues and harder-to-follow design. Spring also considers self-injection a fallback when refactoring is not feasible; it is not the first choice for business architecture.

In environments with multiple transaction managers or interface-based JDK proxies, the reference type can matter: the target method must be exposed on the appropriate proxy type. Do not casually inject your own concrete class if the proxy only exposes an interface.

### 9.3. `AopContext.currentProxy()`: last resort

You can call through `AopContext.currentProxy()` when Spring AOP is configured with **exposeProxy=true**, then cast to the appropriate proxy interface/class. However, this ties business code directly to Spring AOP, can throw an exception if not in the proper invocation context or if `exposeProxy` is not enabled. Spring documentation recommends avoiding this approach whenever refactoring is possible.

Do not equate `AopContext.currentProxy()` with `this`. Only the former has a chance to route through the proxy, and it depends on properly configured infrastructure/proxy context.

### 9.4. AspectJ mode: weaving instead of proxies

`@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)` can use **bytecode weaving** to apply transaction advice without calls having to pass through a Spring AOP proxy; when properly configured, self-invocation does not hit this proxy limitation. However, it requires `spring-aspects` and corresponding compile-time or load-time weaving setup, along with build and operational considerations.

This is a **different mechanism**, not an automatic effect of adding an `@EnableTransactionManagement` annotation. Interface annotations also have limitations in AspectJ mode; `@Transactional` should be placed on concrete classes/methods. Do not turn on AspectJ just for one small helper self-call when extracting a bean or placing the boundary at the entry point already solves the requirement cleanly.

## 10. How to Detect Self-Invocation in a Real Project

Inspect the **call graph** rather than just searching for `@Transactional`:

1. Identify the **entry point**: which controller, scheduler, listener, job, or caller bean invokes the service?
2. Identify the object reference on each edge: a Spring-injected field, a call on another bean, or `this.` / an unqualified call within the same class?
3. Confirm transactions are enabled in the right application context. Spring Boot normally supports transaction auto-configuration when a transaction manager exists, yet an annotation on an object created via `new` will not get advice.
4. Note the propagation required at **each boundary**: one shared transaction or a new transaction?
5. Check which boundaries exceptions cross and where they are caught. Under default rollback rules, a `RuntimeException` must cross an intercepted boundary for that rule to take effect.
6. When in doubt, write an integration test that fails after a write and reads data **after the method completes**, from a caller not wrapped in a test transaction.
7. Only after proving the outcome should you choose to refactor to another bean or remove redundant annotations on helpers.

You can enable experimental logging:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
~~~

Logs can show advice creating or completing transactions at each proxy boundary, though exact messages depend on manager/version. Seeing no log at `inner()` does not mean "everything in inner runs outside a transaction"; cross-check against outer's existing transaction and database state.

### 10.1. Using `TransactionSynchronizationManager` appropriately

In an imperative application with thread-bound transactions:

~~~java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean readOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();
~~~

This is an **illustrative snippet**, not a standalone program. It checks the current transaction context; it **does not** provide a flag saying "this method's own `@Transactional` ran advice". In a self-call from a transactional outer method, `active` remains true even though inner opened no new boundary.

For reactive transactions using `ReactiveTransactionManager`, the transaction context may reside in the **Reactor subscriber Context**, so imperative `ThreadLocal` checks do not apply as-is. Even in reactive mode, if relying on Spring AOP proxies, self-invocation remains a call-path issue; keep publishers inside the right pipeline and proxy boundary.

### 10.2. Testing rollback accurately

In Spring tests, `@Transactional` on a test method can make a `REQUIRED` service join the test transaction and then roll back under TestContext rules, leading to misinterpretation. To test self-invocation:

- Use a test caller **without** `@Transactional` on itself, inject the service from the Spring context, and invoke the public method through the bean.
- Use an isolated database per test or reset data before each case.
- After the service returns/throws, read the balance from a separate call outside the transaction under test.
- Check **both data and exceptions**: a self-call throws an error yet updates may have committed; a proxy call throws an error and updates roll back.
- For `REQUIRES_NEW`, verify inner committed independently by checking the persisted row after outer rolls back.

When multiple resources exist, a DAO using a connection from the wrong manager can produce symptoms resembling self-invocation. Therefore also check the injected transaction manager, `DataSource`, or `ConnectionFactory`. If the app uses a multi-tenant/routing datasource, verify the actual resource key too.

## 11. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| "If `@Transactional` is on inner, it always opens a transaction." | Only if advice is applied to the invocation or another boundary actively creates a transaction. |
| "`this.inner()` is different from `inner()`." | Both are self-invocations on the same target. |
| "Switching to CGLIB will catch self-calls." | Class-based proxies do not alter direct calls on the target. |
| "Inner sees `active=true`, so `REQUIRES_NEW` ran." | The active flag may come from outer; check physical transactions and commit results. |
| "Self-calls never have a transaction." | False when outer/caller already opened an appropriate transaction. |
| "Inner throws RuntimeException, so outer definitely rolls back." | If self-call bypasses inner advice and outer catches the exception and returns, it can commit. |
| "Inner `rollbackFor` still applies even on internal calls." | Inner's annotation is not processed separately at a self-call site. |
| "`@Transactional` on private/final helpers is a fix." | Proxy mode cannot advise many uninterceptable method forms; changing visibility does not fix self-invocation. |
| "Spring beans always have proxies everywhere." | Requires transaction infrastructure and an eligible bean/method; objects created via `new` are not bean proxies. |
| "Calling a transactional method from `@PostConstruct` opens a transaction." | The proxy may not be fully initialized yet; do not rely on proxy transactions in init callbacks. |
| "Using `REQUIRES_NEW` outside is always safe." | It commits independently; it can break atomicity and requires an extra connection. |
| "AspectJ mode is just a flag needing no extra setup." | Requires weaving and matching dependencies; it does not activate without prepared infrastructure. |

## 12. Exercises: Predicting Call Paths and Outcomes

**Scenario A:** Controller calls `service.outer()` through the proxy; `outer()` has no annotation and calls `this.inner()`; `inner()` has `@Transactional(rollbackFor=Exception.class)`, updates the DB, and throws a checked exception. No outer transaction exists, and the JDBC driver defaults to auto-commit. Prediction: inner's annotation is bypassed; the UPDATE may have committed per statement. When the exception escapes, there is no Spring transaction from inner to roll back.

**Scenario B:** `outer()` has `@Transactional`; inner has `@Transactional(REQUIRES_NEW)` and uses the same JDBC template. Outer calls `this.inner()` and then throws RuntimeException. Prediction: inner gets no new transaction; changes belong to outer and roll back provided there are no out-of-transaction side effects.

**Scenario C:** Keep B, but move inner to a public method on a different Spring bean, injected and called through its proxy. Prediction: inner's `REQUIRES_NEW` transaction can commit separately, and outer's subsequent rollback does not undo inner's commit. The business domain must accept that state.

**Scenario D:** Outer `@Transactional` calls `this.inner()`, inner throws `IllegalStateException`, yet outer catches it and returns normally. Prediction: if only this Java exception occurred and no other rollback-only marker exists, outer can commit. If inner lived on another bean with `REQUIRED`, inner's advice could mark rollback-only, causing outer's commit to fail with `UnexpectedRollbackException`.

**Scenario E:** A component calls `this.inner()` inside `@PostConstruct`. Prediction: do not rely on transaction advice because the proxy may not be set up yet; move initialization needing transactions to a lifecycle mechanism after context/proxy completion, or coordinate explicitly via a service/template.

## 13. Design Decision Checklist

When you see `outer() -> inner()` in the same class, answer:

1. Is outer managed by Spring and **invoked through a proxy**?
2. Does inner need the **same transaction** or an **independent boundary** (such as `REQUIRES_NEW`)?
3. If the same transaction, can the annotation live on outer while keeping inner a plain helper?
4. If independent, can inner be extracted into another bean and called through a proxy?
5. Does advice see inner's exception, or does outer catch it before the boundary?
6. Is there an ambient transaction from a caller/test/`TransactionTemplate` skewing observed results?
7. Do the manager and connection match the right resource, and did the transaction truly **commit/roll back** after the scope ended?

**Technical conclusion:** self-invocation is an **AOP proxy call-path issue**. Annotations on internal methods remain in source code, yet in proxy mode they do not trigger additional transaction advice when code calls `this.method()`. Designing boundaries at proper entry points, extracting beans for scopes needing distinct policies, or using explicit transaction APIs keeps commit/rollback behavior aligned with business intent.

## Official References

- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy mode, self-invocation limits, defaults, and AspectJ mode.
- [Spring Framework — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): distinguishing proxy/target, self-calls, and workarounds.
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): role of transaction advice/interceptor.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, and rollback-only when participating in a transaction.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` and `PlatformTransactionManager`.
