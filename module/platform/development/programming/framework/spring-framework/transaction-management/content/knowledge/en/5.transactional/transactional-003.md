# Precedence Order of Specific vs. Default @Transactional Configuration

## 1. The Problem: When Multiple Places Declare a Transaction, Whom Does Spring Listen To?

In Spring Framework, `@Transactional` describes how to manage transactions for a method call: propagation, isolation, read-only, timeout, rollback rules, and transaction manager. When a single service has configuration on the **class**, on the **method**, and sometimes on an **interface/superclass**, readers easily mistake that Spring merges individual attributes, or takes a "default" value from the class and only replaces the attributes explicitly written on the method.

The rule to grasp: **the transaction declaration at the most specific effective location for the invoked method takes precedence**. In the common case, `@Transactional` placed **directly on the implementation class's method** wins over `@Transactional` placed at the **class level**. If the method has no declaration, the class-level configuration acts as the fallback policy for methods within the scope recognized by Spring.

Second important point: **a method-level annotation is not merged attribute-by-attribute with a class-level annotation**. For example, if the class declares `readOnly = true` and a method only writes `@Transactional`, the method takes **the annotation's own defaults**: `readOnly = false`, `propagation = REQUIRED`, etc.; it does not implicitly inherit `readOnly = true` or `rollbackFor` from the class.

Third important point: **selecting metadata configuration differs from creating the actual physical transaction**. A method with its own configuration that joins an already-open transaction via `PROPAGATION_REQUIRED` cannot overwrite certain properties of the outer transaction.

This lesson distinguishes three independent questions:

1. **Where does Spring select the annotation from?** A specific method, the class, an inherited location, or no annotation.
2. **How are the annotation's attributes interpreted?** Explicitly written values vs. `@Transactional` defaults, rollback rules, and manager defaults.
3. **Which attributes does the actual transaction receive?** Creating a new transaction vs. joining an existing physical transaction; whether a proxy/transaction advice is active or not.

## 2. Default Values When Using @Transactional

If a method has `@Transactional` without specifying additional attributes, Spring essentially uses the following values (when no global default configuration has been altered):

| Attribute | `@Transactional` default | Meaning |
| --- | --- | --- |
| `propagation` | `Propagation.REQUIRED` | Creates a transaction if no suitable one exists; joins if one already exists |
| `isolation` | `Isolation.DEFAULT` | Does not force a specific isolation; uses the default isolation of the transaction system/DB |
| `readOnly` | `false` | Read-write transaction; `true` is a hint, not an access-control enforcement mechanism |
| `timeout` | `TransactionDefinition.TIMEOUT_DEFAULT` (-1) | Uses the transaction manager/underlying system's default timeout, or unlimited when unsupported |
| `rollbackFor`, `noRollbackFor` | Empty array | By default rolls back on `RuntimeException` or `Error`; usually does not roll back on checked `Exception` |
| `transactionManager`/`value` | Empty string | Does not specify a dedicated manager on the annotation; uses Spring's manager resolution mechanism |
| `label` | Empty array | Does not attach optional transaction labels |

**Two kinds of "defaults" that should not be conflated:**

- `@Transactional` at the **class level** is a **positional default** for methods without a more specific annotation.
- The values in the table are **annotation attribute defaults** when you write `@Transactional` with no arguments or only a subset of attributes.

For example, `@Transactional(readOnly = true)` still uses `REQUIRED` and default rollback rules. Conversely, when a method annotation only contains `propagation = REQUIRES_NEW`, the other attributes of the **method annotation** take their own default values; they do not pull missing values from the class annotation.

`Isolation.DEFAULT` does not mean "`READ_COMMITTED` in every DB". The default timeout is not a fixed number of seconds; and `readOnly = true` may only be an optimization hint for the driver/ORM. These details depend on the manager and resource in use.

## 3. Method-Level Configuration Takes Precedence Over Class-Level Configuration

Consider a Spring service:

~~~java
@Service
@Transactional(readOnly = true)
public class CatalogService {
    public Product findById(long id) {
        // No separate @Transactional:
        // class-level readOnly=true metadata is applied.
        return repository.findById(id).orElseThrow();
    }

    @Transactional(readOnly = false, propagation = Propagation.REQUIRES_NEW)
    public void changePrice(long id, long newPrice) {
        // Method metadata takes precedence:
        // readOnly=false and REQUIRES_NEW.
        repository.updatePrice(id, newPrice);
    }

    @Transactional
    public void refreshCounters() {
        // Entire method @Transactional metadata is selected.
        // readOnly=false, propagation=REQUIRED by annotation defaults.
        repository.refreshCounters();
    }
}
~~~

This is an **illustrative snippet**, not a standalone runnable program: `Product`, `repository`, and data methods are undefined. Assuming all three methods are called externally through the Spring proxy with no outer transaction, we deduce:

| Method | Selected annotation | Effective propagation | Requested read-only |
| --- | --- | --- | --- |
| `findById` | Class `@Transactional(readOnly=true)` | `REQUIRED` | `true` |
| `changePrice` | Method `@Transactional(readOnly=false, propagation=REQUIRES_NEW)` | `REQUIRES_NEW` | `false` |
| `refreshCounters` | Method `@Transactional` | `REQUIRED` | `false` |

What is often missed lies in `refreshCounters`: even though `readOnly=false` is not written, the method **does not stay read-only from the class**. Simply placing a new `@Transactional` on the method causes Spring to select that method metadata.

A sharper example of attributes not being partially merged:

~~~java
@Transactional(
    readOnly = true,
    propagation = Propagation.SUPPORTS,
    rollbackFor = IOException.class,
    transactionManager = "catalogTx"
)
public class CatalogService {
    @Transactional(timeout = 10)
    public void updateItem() {
        // Method annotation is selected in full.
    }
}
~~~

Assuming `CatalogService` is Spring-managed and advice applies, the configuration of `updateItem()` is:

- `timeout = 10` seconds (written on the method).
- `propagation = REQUIRED` (default of the method annotation), **not** `SUPPORTS` from the class.
- `readOnly = false` (default of the method annotation), **not** `true` from the class.
- No `rollbackFor = IOException.class` from the class; default rollback rules apply to the method unless a global default has also been configured.
- `transactionManager` on the method is an empty string; it **does not implicitly inherit** `"catalogTx"` from the class. Spring will resolve the manager according to its default/qualifier mechanism.

If a method must keep the class-level manager and rollback rule while changing only the timeout, **redeclare those required attributes on the method annotation**, or use a composed annotation with a consistent policy. Do not assume Spring "inherits the missing parts" of the class annotation.

## 4. Decision Graph: Select Metadata First, Then Decide the Transaction

~~~mermaid
flowchart TD
    A["Caller invokes method through Spring proxy"] --> B{"Is transaction advice effective?"}
    B -->|"No"| X["@Transactional semantics do not apply at this call site"]
    B -->|"Yes"| C{"Is @Transactional metadata present<br/>on the most specific method?"}
    C -->|"Yes"| D["Select method metadata"]
    C -->|"No"| E{"Is class / hierarchy metadata<br/>recognized by Spring?"}
    E -->|"Yes"| F["Select matching class/hierarchy metadata"]
    E -->|"No"| G["No transaction attribute for method"]
    D --> H["Resolve all attributes<br/>and default fallbacks"]
    F --> H
    H --> I["Select TransactionManager"]
    I --> J{"Propagation and current transaction?"}
    J -->|"Create new transaction"| K["Apply supported attributes on begin"]
    J -->|"Join existing transaction"| L["Use outer physical transaction;<br/>check/mark rollback per scope"]
    K --> M["Execute, commit/rollback"]
    L --> M
~~~

This diagram is a **configuration-resolution workflow**. It does not depict a fixed linear order for every inheritance, bridge method, and proxy scenario. The formal rule is that the appropriate **most derived** location takes precedence; when interfaces and superclasses are involved, selection also depends on the exact method Spring is resolving.

**With no annotation on the method or class**, the framework does not automatically spin up a transaction just because the method calls a DAO. However, the method might call a repository that declares its own transaction or run inside a transaction created by the caller; that is a different boundary.

## 5. When Interfaces, Superclasses, and Implementation Classes Are Involved

In real projects, a method may appear on an interface, a superclass, and an implementation. The safe approach is to place important semantics **on the public method of the concrete service class**, so both readers and proxies see the configuration to apply.

### 5.1. Concrete Implementation Class Configuration

~~~java
public interface PaymentOperations {
    void submit();
}

@Transactional(readOnly = true)
public class PaymentService implements PaymentOperations {
    @Override
    @Transactional(readOnly = false, rollbackFor = IOException.class)
    public void submit() {
        // Metadata directly on PaymentService.submit takes precedence.
    }
}
~~~

This code illustrates metadata; `IOException` is a rule example, as this method does not actually throw `IOException`. If the method had no separate `@Transactional`, the class-level `readOnly=true` would serve as the fallback for class methods within Spring's applicable scope.

### 5.2. Do Not Deduce a Rigid Order for Every Inheritance Scenario

- If the **implementation method** directly declares `@Transactional`, it is the specific location that takes precedence in common scenarios.
- Annotations on the **concrete class** usually serve as the shared policy for methods declared/applied in the class.
- Spring can look up annotations on methods/types of **interfaces or superclasses** in proxy mode; you should not treat a hand-written priority order on paper as a guarantee for every overload, bridge method, proxy, or composed metadata variant.
- Spring documentation notes: annotations **at the subclass level** do not automatically apply upward to methods **declared only in an ancestor class**; when a subclass policy must cover an inherited method, **redeclare/override** the method in the subclass and verify.
- For interface annotations, Spring can support them in proxy mode (including class-based proxies since Spring 5.0), but **AspectJ weaving does not inherit annotations from interfaces under Java rules**. Therefore Spring recommends annotating concrete classes/methods, avoiding reliance on interface-only metadata if switching AOP mechanisms.

Methods with the same name but different parameters are **different overloads**; placing `@Transactional` on `save(String)` does not automatically apply it to `save(long)`, unless there is class-level configuration or separate metadata on the second method.

### 5.3. Composed Annotations as a Reusable Metadata Source

For example, if most write methods need the same manager and rollback rule:

~~~java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Transactional(transactionManager = "catalogTx", rollbackFor = IOException.class)
public @interface CatalogWriteTx {
}
~~~

Then place `@CatalogWriteTx` on methods needing this rule. It is a **meta-annotation** carrying transactional semantics, not merely a decorative label. A matching transaction manager bean and valid Spring AOP configuration are required. If you also add a separate `@Transactional` on the same method or combine competing transaction annotations, do not guess how they merge; keep one clear policy and avoid ambiguous configurations.

## 6. Rollback Rules: Precedence **Inside One Annotation** Differs from Annotation Precedence

Two easily confused concepts:

- **Declaration-site precedence:** a method-level annotation is selected before a class-level annotation. Rules on the class are not automatically merged into the method annotation.
- **Precedence among rollback rules within the selected configuration:** when an exception matches multiple rules, the **most specific (strongest match)** rule wins.

Example:

~~~java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = DuplicateOrderException.class
)
public void persistOrder() {
    // ...
}
~~~

Suppose `DuplicateOrderException extends RuntimeException`; this exception matches both `Exception.class` and `DuplicateOrderException.class`; because the `noRollbackFor` rule is more specific, the policy requires **not rolling back for that exception type**. For another subclass of `Exception` that does not match the narrow exclusion rule, `rollbackFor=Exception.class` still applies.

Example of **declaration-site precedence**:

~~~java
@Transactional(rollbackFor = IOException.class)
public class ImportService {
    @Transactional
    public void importData() throws IOException {
        // If IOException escapes the proxy, the method annotation
        // does not retain the class's rollbackFor=IOException.class.
    }
}
~~~

Under the default configuration of Spring Framework 6.1/6.2, `importData` will **not trigger rollback merely for a checked `IOException`**; the transaction may commit before the exception is propagated. To roll back:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importData() throws IOException {
    // ...
}
~~~

Place the rule **directly on the method**. If the class also uses `readOnly`, `transactionManager`, or a specific propagation, repeat the essential attributes on the method when needed, because Spring does not merge them automatically.

**Prefer `Class`-based rules**, such as `rollbackFor = IOException.class` or `noRollbackFor = BusinessException.class`. `rollbackForClassName`/`noRollbackForClassName` rules match substrings of exception names and can accidentally match `CustomExceptionV2` or inner classes, so do not treat name-pattern matching as an "exact match".

Aside from checked exceptions, by default Spring rolls back when a `RuntimeException`/`Error` **escapes the boundary managed by advice**. If a method swallows the exception and returns normally, the proxy cannot observe it; no annotation precedence rule can fix that.

## 7. Global Defaults, Managers, and Spring Versions

There are several kinds of "global defaults". Place each at the right layer:

### 7.1. @EnableTransactionManagement Activates the Mechanism, Does Not Override Methods

`@EnableTransactionManagement` (or `<tx:annotation-driven/>` in XML) enables transaction annotation processing infrastructure for eligible beans in the application context. It has settings such as `mode` (proxy/AspectJ), proxy type, and advice `order`.

**The `order` of transaction advice is not the precedence between method-level and class-level `@Transactional`.** It controls AOP advice ordering relative to other advice (logging, retry, etc.), and does not make class-level metadata beat method-level metadata.

If no transaction advice is actually applied, debating method-level vs. class-level will produce no rollback in practice. In proxy mode, calling `this.anotherTransactionalMethod()` bypasses the proxy, so the called method's annotation **does not create a new transaction boundary**.

### 7.2. Default Transaction Manager

When an annotation does not specify `transactionManager`, Spring uses its default transaction manager lookup mechanism: a configured/named matching manager, `TransactionManagementConfigurer`, or bean/class qualifiers in supported scenarios. With multiple managers, specify explicitly to avoid targeting the wrong data source.

~~~java
@Transactional(transactionManager = "ordersTx", readOnly = true)
class OrdersService {
    @Transactional(readOnly = false)
    public void saveOrder() {
        // This method does NOT automatically inherit "ordersTx" from the class annotation.
        // Verify the default manager or redeclare ordersTx on the method.
    }
}
~~~

Explicit approach:

~~~java
@Transactional(transactionManager = "ordersTx", readOnly = false)
public void saveOrder() {
    // ...
}
~~~

These two snippets illustrate annotations only; without an `ordersTx` bean and method implementation they cannot run standalone. **Default manager selection** and **annotation attribute defaults** are two separate concerns.

### 7.3. Global Default Rollback Since Spring Framework 6.2

In Spring Framework **6.2+**, you can change the default rollback policy for all checked exceptions:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.RollbackOn;

@Configuration
@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)
class TransactionConfig {
}
~~~

This is a **snippet for Spring Framework 6.2+**, not for verbatim use in the Spring Boot 3.3.5 example below (Boot 3.3.x uses Spring Framework 6.1.x). When `ALL_EXCEPTIONS` is enabled, checked exceptions also roll back under the new default, even when a method only has `@Transactional`. **A transaction's own rollback rules** take precedence for exceptions they match, while the global policy serves as the fallback for exceptions without a specific rule.

This configuration does not merge class-level `rollbackFor` into method-level `@Transactional`; it affects the **default rollback decision** after the specific metadata has been resolved.

### 7.4. Default Timeout and Isolation

`@Transactional(timeout = 5)` is an explicit method value used when the manager must open a new transaction; if a method only has `@Transactional`, timeout typically uses the manager/system default. `Isolation.DEFAULT` relies on the data source to provide its default isolation; it does not assign one fixed level across all DBs.

If the default transaction manager has a 30-second timeout while the method requests 5 seconds and actually opens a new transaction, the method normally requests 5 seconds. However, if the method **joins an existing transaction**, the outer physical transaction's timeout remains decisive; joining does not reopen the deadline.

## 8. A Selected Method Configuration Still May Not Alter an Existing Transaction

Consider two distinct Spring beans:

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(readOnly = true)
    public void outer() {
        inner.inner();
    }
}

@Service
class InnerService {
    @Transactional(readOnly = false, propagation = Propagation.REQUIRED)
    public void inner() {
        // Method metadata: readOnly=false, REQUIRED.
        // However, the method is joining outer's readOnly=true physical transaction.
    }
}
~~~

This is **illustrative code missing imports and bootstrap**, not a standalone program. Assuming both services pass through proxies and share the same manager and resource:

- Spring selects `inner()`'s metadata with `readOnly=false` because that method annotation is direct.
- Because of `REQUIRED` and outer already having a transaction, inner **joins outer's physical transaction**, creating no new physical transaction.
- Under the default mode, the participating scope's isolation/timeout/readOnly declarations may be **ignored**, so the physical transaction retains outer's attributes. Managers with `validateExistingTransaction` enabled can reject incompatible combinations, such as a read-write inner joining a read-only outer.
- `readOnly` is primarily a hint; do not treat a single successful or failing `UPDATE` as the sole test of the policy.

If inner uses `REQUIRES_NEW` instead of `REQUIRED`, Spring creates an independent physical transaction and can apply inner's own attributes within what the manager/DB supports. Consider connection pool usage because outer typically still holds its resource while inner executes.

Summary table:

| Scenario | Which metadata does Spring select? | Which attributes does the physical transaction receive? |
| --- | --- | --- |
| Method has `@Transactional`, no outer transaction | Method | Method attributes when manager opens a new transaction |
| Method unannotated, class has `@Transactional`, no outer transaction | Class | Class attributes when manager opens a new transaction |
| `REQUIRED` method called inside outer with active transaction | Method in inner scope | Typically uses outer's physical transaction attributes; may validate mismatch |
| `REQUIRES_NEW` method called via proxy while outer is running | Method in inner scope | Independent new transaction using supported method attributes |
| Annotated method called directly via `this` in same bean | Annotation exists in code | No separate advice on self-invocation; do not assume a new transaction |
| Method has no annotation from any recognized source | No metadata for method | Transaction advice does not open a separate transaction for that call |

Thus "method beats class" is a **metadata selection rule**, not a promise that the manager will alter the isolation/read-only state of an already-running physical transaction.

## 9. Runnable Example with Java 17 and Spring JDBC: Verifying Both readOnly and rollbackFor

This example creates a small Spring Boot CLI app with JDBC/H2. It proves two points:

1. An unannotated method uses `readOnly=true` from the **class**.
2. A method with its own `@Transactional` uses default `readOnly=false` and **does not retain `rollbackFor=IOException.class`** from the class. When the method writes data and throws checked `IOException`, the transaction commits under Spring Framework 6.1's default rollback policy.
3. A method explicitly declaring `rollbackFor=IOException.class` rolls back on that same exception type.

Uses Spring Boot **3.3.5**, corresponding to Spring Framework **6.1.x**, to pin the default checked-exception behavior. Assumes JDK 17+, Maven, and dependency download access. There are **exactly three files**:

~~~text
tx-precedence-demo/
├── pom.xml
└── src/main/java/example/precedence/
    ├── TxPrecedenceApplication.java
    └── LedgerService.java
~~~

### 9.1. File pom.xml

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
    <artifactId>tx-precedence-demo</artifactId>
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

### 9.2. File src/main/java/example/precedence/TxPrecedenceApplication.java

~~~java
package example.precedence;

import java.io.IOException;
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
public class TxPrecedenceApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxPrecedenceApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, LedgerService service) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE ledger (id INT PRIMARY KEY, amount INT NOT NULL)"
            );
            jdbc.update("INSERT INTO ledger (id, amount) VALUES (?, ?)", 1, 100);

            // Method uses only class annotation.
            service.showClassPolicy();

            // Method has its own @Transactional: checked IOException
            // does not trigger rollback under 6.1 default policy.
            try {
                service.addWithDefault(10);
            } catch (IOException ex) {
                System.out.println("CAUGHT " + ex.getMessage());
            }
            System.out.println("AFTER_DEFAULT=" + amount(jdbc));

            // Method explicitly requests rollback for IOException.
            try {
                service.addWithRollbackRule(30);
            } catch (IOException ex) {
                System.out.println("CAUGHT " + ex.getMessage());
            }
            System.out.println("AFTER_EXPLICIT_ROLLBACK=" + amount(jdbc));
        };
    }

    private static Integer amount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT amount FROM ledger WHERE id = ?", Integer.class, 1
        );
    }
}
~~~

### 9.3. File src/main/java/example/precedence/LedgerService.java

~~~java
package example.precedence;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

// Shared policy applied when a method has no separate annotation.
@Service
@Transactional(readOnly = true, rollbackFor = IOException.class)
public class LedgerService {
    private final JdbcTemplate jdbc;

    public LedgerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void showClassPolicy() {
        printPolicy("CLASS");
        // Does not write data; readOnly=true is only a hint.
        jdbc.queryForObject(
            "SELECT amount FROM ledger WHERE id = ?", Integer.class, 1
        );
    }

    // Method annotation is selected in full: readOnly=false,
    // default rollback on RuntimeException/Error, not IOException.
    @Transactional
    public void addWithDefault(int delta) throws IOException {
        printPolicy("METHOD_DEFAULT");
        jdbc.update(
            "UPDATE ledger SET amount = amount + ? WHERE id = ?", delta, 1
        );
        throw new IOException("checked-default");
    }

    // Method explicitly declares the required rollback rule.
    @Transactional(readOnly = false, rollbackFor = IOException.class)
    public void addWithRollbackRule(int delta) throws IOException {
        printPolicy("METHOD_ROLLBACK");
        jdbc.update(
            "UPDATE ledger SET amount = amount + ? WHERE id = ?", delta, 1
        );
        throw new IOException("checked-rollback");
    }

    private void printPolicy(String label) {
        System.out.println(
            label
            + " active=" + TransactionSynchronizationManager.isActualTransactionActive()
            + ", readOnly=" + TransactionSynchronizationManager.isCurrentTransactionReadOnly()
        );
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

**Lines printed by the application itself** in order (excluding Spring Boot/Hikari logs):

~~~text
CLASS active=true, readOnly=true
METHOD_DEFAULT active=true, readOnly=false
CAUGHT checked-default
AFTER_DEFAULT=110
METHOD_ROLLBACK active=true, readOnly=false
CAUGHT checked-rollback
AFTER_EXPLICIT_ROLLBACK=110
~~~

Interpretation:

1. The runner receives an injected `LedgerService` proxy from Spring and calls `showClassPolicy()` from **outside the bean**. With no method annotation, Spring uses the class policy and opens a transaction with flag `readOnly=true`.
2. `addWithDefault(10)` has a method `@Transactional`. Even though the class declares `rollbackFor=IOException.class`, this method **does not inherit that rule**. It requests a read-write transaction; when checked `IOException` is thrown, the advice applies the default (no rollback) and commits the UPDATE before rethrowing the exception to the caller. The amount goes from 100 to 110.
3. `addWithRollbackRule(30)` writes data and throws `IOException`. Because the method has `rollbackFor=IOException.class`, Spring rolls back the UPDATE; the amount stays 110.
4. `catch` is in `CommandLineRunner`, i.e., **outside the proxy**, so it does not alter the transaction advice's commit/rollback decision.
5. Printing `isCurrentTransactionReadOnly()` checks the **flag in the Spring transaction context**, not whether the database always blocks writes when read-only. The database state after transaction completion is the key verification of commit/rollback.

The example uses one `JdbcTransactionManager` and one H2 `DataSource`; there is no internal `this.*` call so it avoids self-invocation. If switching to Spring Framework 6.2+ and enabling `rollbackOn=ALL_EXCEPTIONS`, re-predict the outcome of `addWithDefault`: the default rollback behavior for checked exceptions will have changed.

## 10. When Custom Configuration Is Needed: Design Explicitly Instead of Relying on "Implicit Inheritance"

Several ways to organize code to avoid mistakes:

### 10.1. Shared Class Policy, Complete Method Policy

~~~java
@Transactional(readOnly = true, transactionManager = "mainTx")
class CustomerService {
    public Customer find(long id) {
        // Class policy.
        return loadCustomer(id);
    }

    @Transactional(
        readOnly = false,
        propagation = Propagation.REQUIRED,
        transactionManager = "mainTx",
        rollbackFor = IOException.class
    )
    public void importCustomer() throws IOException {
        // Explicit method policy.
    }
}
~~~

This is an **excerpt**; `Customer` and `loadCustomer` have no implementation. The key point is that the write method carries all attributes it needs to preserve rather than leaving them to the class annotation.

### 10.2. Separating Read Service and Write Service

If read and write policies differ in manager, timeout, or rollback rules, you can split into two service beans. Class-level policies become shorter, with fewer overrides and easier-to-verify proxy boundaries. Still, splitting classes solely to avoid repeating 1–2 attributes is not always necessary; prioritize clear business boundaries.

### 10.3. Writing Integration Tests at the Right Layer

To verify an assumption about configuration precedence:

- **Call through the Spring proxy** from another bean/test client to ensure advice runs. Do not use `new Service()` or self-invocation to test property selection.
- **Observe flags** inside the transaction when appropriate: `TransactionSynchronizationManager.isActualTransactionActive()`, `isCurrentTransactionReadOnly()`, and logs from `org.springframework.transaction`. Flags report Spring context state, not whether the DB committed.
- **Trigger a failure after a data modification**, then re-check the DB from another transaction/connection. Distinguish checked exceptions from unchecked exceptions, and class policy from method policy.
- **Verify the actual manager** if multiple `PlatformTransactionManager`s exist; picking the wrong bean can make tests fail due to a different connection source rather than annotation precedence.
- If the test framework opens a transaction around the test itself, a `REQUIRED` service method may join the test transaction; avoid misreading commit/rollback results. With `@Transactional` on a test, Spring TestContext rolls back after the test by default; when testing real commits, control the test transaction or separate the test caller.
- Use explicit checks for important attributes when a refactor might alter annotations: manager name, propagation, rollback rules, and whether an outer transaction exists.

## 11. Common Pitfalls When Reading Precedence Order

| Misconception | Reality to remember |
| --- | --- |
| "The method only sets `timeout=5`, so it keeps all class attributes" | A method annotation replaces the entire annotation metadata; other attributes take its defaults |
| "With `@Transactional` on the class, a separate method annotation stays read-only" | A method with its own `@Transactional` defaults to `readOnly=false` unless `true` is specified again |
| "`rollbackFor` on the class still applies when the method has its own annotation" | Class rules do not automatically merge into the method annotation; redeclare or use an appropriate global default |
| "`isolation=SERIALIZABLE` on an inner method always raises DB isolation" | `REQUIRED` joining an existing physical transaction may ignore the inner isolation request |
| "`order` on `@EnableTransactionManagement` makes method annotations beat class annotations" | `order` controls advice ordering, not location-based metadata selection |
| "Just annotating the interface works across all proxy/AspectJ modes" | Interface annotations have specific limitations; prefer annotating the concrete implementation |
| "Private/final methods or `this.method()` self-calls always receive advice" | Proxy mode has visibility/override limits and only intercepts calls through the proxy |
| "`readOnly=true` definitely throws an error on DB writes" | It is a hint, depending on transaction manager/driver/database |
| "Checked exceptions always commit" | That is the common default before changing the global rollback policy; specific rules or Spring 6.2+ `ALL_EXCEPTIONS` can trigger rollback |
| "Class-level metadata automatically applies to all methods declared in the superclass" | Spring notes that subclass annotations do not apply upward to ancestor methods; overriding/redeclaring may be required |
| "Having `@Transactional` everywhere makes managers automatically coordinate" | The specific manager chosen determines the resource; annotations do not turn two independent DataSources into one transaction |

## 12. How to Reason Through a New Scenario Yourself

Suppose you have:

~~~java
@Transactional(readOnly = true, rollbackFor = Exception.class)
public class OrderService {
    public Order get(long id) { /* ... */ return null; }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void save(Order order) { /* ... */ }

    @Transactional(readOnly = false, noRollbackFor = BusinessException.class)
    public void finalizeOrder() { /* ... */ }
}
~~~

This is Java pseudocode illustrating signatures; `Order` and `BusinessException` are hypothetical domain types. Follow this sequence:

1. **`get`:** no separate annotation ⇒ uses class metadata (read-only, `rollbackFor = Exception.class`, default propagation `REQUIRED`).
2. **`save`:** method annotation is selected ⇒ `REQUIRES_NEW`; `readOnly` defaults to **false**, not `true` from the class; `rollbackFor=Exception.class` from the class is not retained either.
3. **`finalizeOrder`:** method annotation is selected ⇒ default `REQUIRED`; `readOnly` is false, `noRollbackFor` for `BusinessException`; does not inherit `rollbackFor=Exception.class` from the class. If `BusinessException` is unchecked, the explicit `noRollbackFor` rule applies.
4. Only then ask whether the method is actually called **through the proxy**, whether there is an **outer transaction**, which manager is responsible, and when the final commit/rollback occurs.

**Check question:** If `save` is changed to `@Transactional(timeout=3)`, does propagation stay `REQUIRES_NEW`? **No** — the new method annotation defaults propagation to `REQUIRED`. If the reader wants both 3 seconds and `REQUIRES_NEW`, they must declare `@Transactional(timeout=3, propagation=Propagation.REQUIRES_NEW)`.

**Check question:** If an outer method has `readOnly=true` and calls `finalizeOrder` from another bean through the proxy, does method-level `readOnly=false` turn the physical transaction into read-write? With `REQUIRED` joining an existing transaction, **not automatically**; the outer configuration still governs the physical transaction and the manager may report a mismatch.

## References

- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): most-derived rule, method/class precedence, attribute defaults, managers, and proxy notes.
- [Spring Framework — Understanding declarative transaction implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): AOP proxies, transaction interceptor, and transaction manager.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): physical/logical transactions, `REQUIRED` and `REQUIRES_NEW`, validating existing transactions.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): rollback rules, strongest match, checked and unchecked exceptions.
- [Spring Framework — Transactional API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): annotation attributes and the meaning of `readOnly`/`rollbackFor`.
