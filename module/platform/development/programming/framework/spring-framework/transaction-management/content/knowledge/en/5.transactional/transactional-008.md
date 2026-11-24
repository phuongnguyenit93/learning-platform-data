# Creating Composed Annotations for Shared `@Transactional` Policies in Spring

## Objectives

After completing this lesson, you can:

1. Explain what a **composed annotation** is and why it is used to establish a consistent transaction policy.
2. Declare a Java annotation with **`@Transactional` as a meta-annotation**, along with `@Target`, `@Retention(RUNTIME)`, and `@Documented`.
3. Create shared annotations for **write** and **read** operations, including propagation, isolation, rollback rules, timeout, and transaction manager when actually needed.
4. Distinguish a **fixed policy** from an attribute exposed in a controlled way via `@AliasFor`.
5. Use composed annotations on Spring services, inspect the metadata Spring resolves, and prove rollback with a Java 17+ example.
6. Avoid common mistakes: wrong `@Transactional` import, methods bypassing the proxy, self-invocation, swallowing exceptions, misunderstanding `readOnly`, or thinking annotations provide ACID by themselves.

The scope of this lesson is **creating composed annotations for shared transaction policies**. Database/ACID mechanisms, propagation, and isolation are mentioned where needed to understand the policy.

## 1. The Problem: The Same Transaction Policy Repeated Everywhere

Suppose multiple services must follow the same data-writing rules: join an existing transaction or open a new one (`REQUIRED`), use `READ_COMMITTED` isolation, roll back even on checked exceptions, and cap the timeout of a new transaction.

Without a shared convention, code easily repeats itself:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    rollbackFor = Exception.class,
    timeout = 15
)
public void transfer(...) { ... }
```

Imagine that configuration appearing across 30 methods. A newcomer might forget `rollbackFor`, mistype `REQUIRES_NEW`, or change timeout without knowing the policy. Even with IDE copy-paste, declarations tend to drift over time.

**Composed annotations** put the policy in one place:

```java
@WriteTx
public void transfer(...) { ... }
```

Then `@WriteTx` becomes part of the **business vocabulary**: readers know the write method follows the defined policy. You only edit one definition when the shared policy changes, and you can test that policy at both the metadata and real-transaction levels.

It **does not** create a new transaction manager, does not replace database constraints, and does not guarantee non-DB side effects roll back. It is a way to reuse **transaction metadata**, read by Spring transaction infrastructure when a bean is invoked through an eligible mechanism.

## 2. Mechanism: An Annotation Placed on Another Annotation

In Java, an annotation can be placed on the declaration of another annotation. The annotation placed above is called a **meta-annotation**.

```text
@Transactional(...)
       |
       v
public @interface WriteTx { ... }
       |
       v
@WriteTx
public void transfer(...) { ... }
       |
       v
Spring looks up merged transaction metadata
       |
       v
TransactionInterceptor + TransactionManager
```

There are two layers of responsibility:

- **Java:** retains the annotation per its retention policy, restricts where it may be placed, and checks syntax/types.
- **Spring:** locates `@Transactional` directly or through one/multiple meta-annotations, synthesizes attributes, and applies transactional advice.

Having `@WriteTx` on a method does not make the method's bytecode generate `begin`/`commit` instructions. In standard proxy mode, Spring creates an **AOP proxy** for the bean, and only calls passing through the proxy are wrapped by `TransactionInterceptor` with begin/commit/rollback. The real transaction manager (e.g., JDBC/JPA/R2DBC) coordinates participating resources.

### Required Java Annotations

| Annotation | Purpose | Decision in this lesson |
| --- | --- | --- |
| `@Target` | Where the annotation may be placed | `METHOD`, `TYPE` for service methods or classes |
| `@Retention` | Lifetime of the metadata | `RUNTIME` so Spring can find it at runtime |
| `@Documented` | Appears in Javadoc | Recommended to publicize the policy |
| `@Transactional` | Defines Spring transaction semantics | The **most important meta-annotation** |
| `@AliasFor` | Lets an attribute of the new annotation override a meta-annotation attribute | Use only when you genuinely want to allow tuning |

`@Inherited` is optional if you want the annotation to apply across **class inheritance** per Java/Spring rules; it does not make method annotations automatically "inherit" onto overridden methods. Prefer placing policies clearly on concrete service classes/methods.

**Correct import:** `org.springframework.transaction.annotation.Transactional`. `jakarta.transaction.Transactional` is a different annotation with different semantics/attributes; do not use it while copying Spring examples using `propagation`, `isolation`, and `rollbackFor`.

## 3. Creating a Fixed Policy for Read Methods: `@ReadOnlyTx`

A read policy can be designed concisely, clearly, and without customizable parameters.

**File `src/main/java/example/txpolicy/ReadOnlyTx.java`:**

```java
package example.txpolicy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Transactional(
    propagation = Propagation.REQUIRED,
    readOnly = true
)
public @interface ReadOnlyTx {
}
```

Explanation:

- `@Transactional(...)` is placed **on the `@interface` declaration**. This is what makes `ReadOnlyTx` a Spring transaction composed annotation.
- `REQUIRED` is Spring's default: start a transaction when none exists; join an existing matching transaction when one is active.
- `readOnly = true` is a **hint/information for the manager and database**, sometimes optimized or enforced depending on driver/DB. Never treat it as a security barrier that always forbids writes.
- When a `REQUIRED` method joins an existing transaction, `readOnly` on the inner method does not automatically alter the nature of the already-started outer transaction.
- With no attributes on `@ReadOnlyTx`, every usage follows the exact same metadata. If read cases have diverging needs, consider whether multiple clearly named policies are warranted.

Example:

```java
@Service
public class CustomerQueryService {

    @ReadOnlyTx
    public Customer findCustomer(long id) {
        // Access database via appropriate repository/JdbcTemplate.
        // This snippet illustrates annotation placement, not a standalone class.
        return customerRepository.findById(id).orElseThrow();
    }
}
```

This snippet only illustrates usage; the complete runnable example in Section 5 uses `JdbcTemplate` with H2.

## 4. Creating a Write Policy with Checked-Exception Rollback: `@WriteTx`

Many systems use checked exceptions to represent business errors. If business rules require **committing no partial writes when a checked exception escapes**, you can define a policy:

**File `src/main/java/example/txpolicy/WriteTx.java`:**

```java
package example.txpolicy;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import org.springframework.core.annotation.AliasFor;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    rollbackFor = Exception.class
)
public @interface WriteTx {

    @AliasFor(annotation = Transactional.class, attribute = "timeout")
    int timeout() default 15;
}
```

Why combine two styles of configuration in one annotation?

- **Fixed:** `REQUIRED`, `READ_COMMITTED`, and `rollbackFor = Exception.class` are always the default policy for every method with `@WriteTx`.
- **Controlled customization:** only `timeout` is exposed. `@WriteTx` defaults to a 15-second timeout, while `@WriteTx(timeout = 12)` lets a method use 12 seconds.
- `@AliasFor(annotation = Transactional.class, attribute = "timeout")` declares that `@WriteTx`'s attribute **overrides** the `timeout` attribute of the `@Transactional` meta-annotation when Spring synthesizes metadata. Both attributes have type `int`.
- If overriding timeout is unnecessary, it is simpler to put `timeout = 15` directly inside `@Transactional(...)` and leave the annotation body empty.

Alias rules do not come from plain Java reflection. Spring uses its **merged annotations** mechanism to locate meta-annotations and compute overridden values. Calling `method.getAnnotation(Transactional.class)` can return `null` when a method only has `@WriteTx`; that does not mean Spring fails to see transaction metadata.

**Do not treat `@AliasFor` as "automatically forwarding every attribute with the same name."** For each attribute to override, explicitly declare the target meta-annotation and `attribute`, ensure matching types, and verify with Spring's merged annotation API.

## 5. Runnable Example: Spring Boot + JDBC/H2

We build a small app transferring points between two wallets. The workflow tests one key aspect of the policy: a **checked exception** thrown after debiting causes the debit change to **roll back**, thanks to `rollbackFor = Exception.class` in `@WriteTx`.

The example uses **Java 17+, Spring Boot 3.3.5, and Gradle**. If your project toolchain uses Java 21, change `JavaLanguageVersion.of(17)` to `of(21)` or keep 17 if your runtime supports it.

### 5.1. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Create a Gradle Spring Boot project with wrapper using Spring Initializr or an installed Gradle, then place the files in the `example.txpolicy` package. No web server is needed because the example uses `ApplicationRunner`.

### 5.2. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:policy_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

Spring Boot auto-configures `DataSource`, `JdbcTemplate`, and the JDBC transaction manager when matching dependencies are present. `mode: always` runs `schema.sql` at startup. In-memory H2 is an illustrative environment; in production systems, consider schema migrations, connection management, durable storage, and testing on your actual production DBMS.

### 5.3. `src/main/resources/schema.sql`

```sql
CREATE TABLE wallets (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO wallets (id, balance) VALUES (1, 1000);
INSERT INTO wallets (id, balance) VALUES (2, 500);
```

The two wallets hold a total of 1,500 points. After transferring 200, balances must be 800 and 700. When an error occurs during the credit step, balances must remain unchanged from before that transaction.

### 5.4. `src/main/java/example/txpolicy/MissingWalletException.java`

```java
package example.txpolicy;

public class MissingWalletException extends Exception {
    public MissingWalletException(String message) {
        super(message);
    }
}
```

This is a **checked exception** because the class directly extends `Exception` rather than `RuntimeException`. Under Spring Framework 6.1's common default, checked exceptions do not automatically trigger rollback; `@WriteTx` provides an explicit rule. Default behavior can be configured differently in newer Spring versions, yet an explicit write rule documents the business policy clearly.

### 5.5. `src/main/java/example/txpolicy/WalletService.java`

```java
package example.txpolicy;

import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

@Service
public class WalletService {
    private final JdbcTemplate jdbc;

    public WalletService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @WriteTx(timeout = 12)
    public void transfer(long sourceId, long targetId, long amount)
            throws MissingWalletException {
        if (amount <= 0 || sourceId == targetId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE wallets SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, sourceId, amount
        );

        if (debited != 1) {
            throw new MissingWalletException(
                "Source missing or insufficient funds"
            );
        }

        int credited = jdbc.update(
            "UPDATE wallets SET balance = balance + ? WHERE id = ?",
            amount, targetId
        );

        if (credited != 1) {
            throw new MissingWalletException("Destination missing");
        }
    }

    @ReadOnlyTx
    public String balances() {
        List<String> pairs = jdbc.query(
            "SELECT id, balance FROM wallets ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + "=" + rs.getLong("balance")
        );
        return String.join(", ", pairs);
    }
}
```

Transaction analysis:

1. Caller invokes `transfer()` **through the Spring bean proxy**. Spring resolves merged metadata from `@WriteTx(timeout=12)`.
2. The interceptor uses the JDBC manager to start a new transaction when the caller has none; the policy includes `REQUIRED`, `READ_COMMITTED`, 12-second timeout, and rollback on `Exception`.
3. Source `UPDATE` debits points and includes `balance >= ?` in the same statement. If balance is insufficient, affected rows = 0 and the service throws a checked exception.
4. Destination `UPDATE` runs only after the source debit succeeds. If the destination ID does not exist, affected rows = 0; the checked exception escapes the method and **Spring rolls back** the source debit too.
5. If both updates succeed, the method finishes and the interceptor commits.
6. `balances()` uses the dedicated read policy. `readOnly=true` itself is just a hint; read SQL must still fit isolation and business rules.

Placing the transaction on the whole `transfer()` method is crucial: putting it only on separate update helpers could create two independent transactions and break transfer atomicity.

### 5.6. `src/main/java/example/txpolicy/TxPolicyApplication.java`

```java
package example.txpolicy;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class TxPolicyApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxPolicyApplication.class, args);
    }

    @Bean
    ApplicationRunner example(WalletService wallets) {
        return args -> {
            wallets.transfer(1L, 2L, 200L);
            System.out.println("After commit: " + wallets.balances());

            try {
                wallets.transfer(1L, 999L, 50L);
            } catch (MissingWalletException ex) {
                System.out.println("Expected error: " + ex.getMessage());
            }

            System.out.println("After rollback: " + wallets.balances());
        };
    }
}
```

`@EnableTransactionManagement` makes declarative transaction configuration explicit; many Spring Boot apps with qualifying auto-configuration also enable transaction management automatically. Methods are called from `ApplicationRunner` through the injected Spring bean, avoiding self-invocation bugs.

Run:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

The lines printed by the application, ignoring startup logs, have the expected content:

```text
After commit: 1=800, 2=700
Expected error: Destination missing
After rollback: 1=800, 2=700
```

Explanation of the final line: after the first transaction, wallet 1 has 800 and wallet 2 has 700. The second transaction tentatively debits another 50 from wallet 1, but because wallet 999 does not exist it throws a **checked exception**. The `rollbackFor=Exception.class` policy causes the DB to roll back the tentative debit; balances remain 800 and 700.

The runnable example's Java files are `ReadOnlyTx.java`, `WriteTx.java`, `MissingWalletException.java`, `WalletService.java`, plus `TxPolicyApplication.java`. All classes must be in package `example.txpolicy`; each Java code block corresponds to one file rather than combining everything into one file.

## 6. Verifying Spring Actually Recognizes the Composed Annotation

Verify at **two layers**:

- **Metadata test:** Spring synthesizes `@Transactional` with the right propagation, isolation, rollback rules, and timeout.
- **Behavior test:** the method is handled by the proxy, and a real transaction rolls back when a checked exception is thrown after a successful SQL statement.

### 6.1. Metadata: Reading with the Merged Annotation API

Plain Java reflection does not turn `@WriteTx` into a direct `@Transactional`. Spring provides `AnnotatedElementUtils.findMergedAnnotation(...)` to obtain the merged view.

Place the following inside a JUnit 5 test class:

```java
import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.junit.jupiter.api.Test;
import org.springframework.core.annotation.AnnotatedElementUtils;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

class TxMetadataTest {

    @Test
    void mergedWritePolicyHasExpectedValues() throws Exception {
        Method method = WalletService.class.getMethod(
            "transfer", long.class, long.class, long.class
        );

        Transactional tx = AnnotatedElementUtils.findMergedAnnotation(
            method, Transactional.class
        );

        assertNotNull(tx);
        assertEquals(Propagation.REQUIRED, tx.propagation());
        assertEquals(Isolation.READ_COMMITTED, tx.isolation());
        assertEquals(12, tx.timeout());
        assertTrue(Arrays.asList(tx.rollbackFor()).contains(Exception.class));
    }
}
```

Running pure metadata tests needs no DB. `@WriteTx` defines a default timeout of 15, while `transfer` specifies `@WriteTx(timeout=12)`, so merged `@Transactional.timeout()` must be 12. This catches alias bugs, wrong retention, or wrong meta-annotations early.

The test snippet above belongs in `src/test/java/example/txpolicy/TxMetadataTest.java`: add `package example.txpolicy;` on the first line before imports to run in the right package. It uses JUnit 5 and `spring-core` already included in the starter.

### 6.2. Behavior: Checked Exceptions Must Roll Back Updated Data

**File `src/test/java/example/txpolicy/WalletServiceTest.java`:**

```java
package example.txpolicy;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class WalletServiceTest {
    @Autowired WalletService wallets;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("UPDATE wallets SET balance = 1000 WHERE id = 1");
        jdbc.update("UPDATE wallets SET balance = 500 WHERE id = 2");
    }

    @Test
    void checkedExceptionRollsBackDebit() {
        assertThrows(MissingWalletException.class,
            () -> wallets.transfer(1L, 999L, 200L));

        Long actual = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = 1",
            Long.class
        );
        assertEquals(1000L, actual.longValue());
    }

    @Test
    void successCommitsBothChanges() throws Exception {
        wallets.transfer(1L, 2L, 200L);

        assertEquals("1=800, 2=700", wallets.balances());
    }
}
```

Run:

```bash
./gradlew test
```

Assertions after the method finishes inspect the real DB state. `@BeforeEach` resets the fixture to initial balances because `ApplicationRunner` also runs on startup and performs a transfer. Test methods are not annotated with `@Transactional`, avoiding having the test framework auto-roll back the test and distort verification of the service's real commits.

**Do not verify solely by checking that `@WriteTx` exists on the method.** Metadata tests do not prove a proxy wrapped the call, whereas behavior tests catch wiring errors or missing transaction managers.

## 7. Exposing Attributes with `@AliasFor`: When and When Not

There are two design directions.

### Fixed Policy

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    rollbackFor = Exception.class
)
public @interface IndependentAuditTx {
}
```

This direction fits when **every usage of the annotation must share the exact same semantics**. Note that `REQUIRES_NEW` splits off an independent transaction: audit can commit even if the outer business transaction rolls back, so you must accept the data consequences. Do not choose `REQUIRES_NEW` just to "be safer."

### Policy with Controlled Overridable Parameters

```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
@Transactional(rollbackFor = Exception.class)
public @interface ManagedWriteTx {

    @AliasFor(annotation = Transactional.class, attribute = "timeout")
    int timeout() default 10;
}
```

Usage:

```java
@ManagedWriteTx
public void saveFast() { ... }

@ManagedWriteTx(timeout = 30)
public void processLargeBatch() { ... }
```

`@AliasFor` expresses intent: all methods share the rollback rule, while timeout is allowed to vary. This is **design illustration code**, not part of Section 5's full demo. To make classes runnable, place each annotation and service in valid files/classes and replace `...` with real method bodies.

Design rule: expose only attributes that are **intentional points of variation**. If every method can arbitrarily change `propagation`, `readOnly`, `isolation`, `rollbackFor`, and `timeout`, a composed annotation becomes merely another name for `@Transactional` and stops enforcing a shared policy.

## 8. Specifying Transaction Manager Names in Composed Annotations

In an application with only one local JDBC transaction manager, you normally do not need to specify a manager in the meta-annotation. However, if there are **multiple** transaction managers, the policy can bind explicitly to one manager:

```java
@Target({ElementType.METHOD, ElementType.TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Transactional(
    transactionManager = "ordersTransactionManager",
    rollbackFor = Exception.class
)
public @interface OrdersWriteTx {
}
```

`ordersTransactionManager` here is an **illustrative bean name**. The annotation only works if the real application defines a matching transaction manager bean/qualifier. Do not copy this name into Section 5's H2 demo without creating that manager.

Spring documentation also demonstrates custom composed annotations for distinct managers such as `order` and `account`. This prevents choosing the wrong datasource/transaction manager, **not** a way to automatically create distributed transactions across two databases.

If a service uses two separate managers, `@OrdersWriteTx` normally only wraps the transaction coordinated by the orders manager. Achieving atomicity across multiple resources requires designing an appropriate coordination mechanism or using outbox/saga depending on system requirements.

## 9. Scope of Application, Metadata Precedence, and AOP Proxies

### 9.1. On Classes and Methods

You can place a composed annotation on a class when **all business methods** in the service share the same policy:

```java
@ReadOnlyTx
@Service
public class ProductQueryService {
    public Product findOne(long id) { ... }
    public List<Product> findAll() { ... }
}
```

When one method needs a different policy, place the specific policy explicitly on that method or split it into a separate service. Method-level transaction attributes can override class-level defaults. Example:

```java
@ReadOnlyTx
@Service
public class ProductService {

    public Product findOne(long id) { ... }

    @WriteTx
    public void updatePrice(long id, long amount) { ... }
}
```

The two snippets above are service sketches, not complete Java classes with imports/repositories. Avoid placing **two conflicting policies on the same method** (`@ReadOnlyTx` and `@WriteTx`) expecting Spring to "combine" them as you intend; give each method one clear policy source.

### 9.2. Proxies and Self-Invocation

`@WriteTx` behaves like `@Transactional` regarding AOP: in proxy mode, **only calls through the Spring proxy** are handled by the interceptor.

```java
@Service
public class WrongService {

    public void outer() {
        inner(); // self-invocation, typically bypasses transaction advice
    }

    @WriteTx
    public void inner() {
        // ...
    }
}
```

If `outer()` calls `inner()` directly on the same instance, it does not pass through the proxy; if no outer transaction exists yet, `@WriteTx` on `inner()` will not start a transaction on its own. Extract `inner()` into a dedicated Spring bean and call that bean, or design the transaction boundary at the public method invoked by external callers.

`@Target(METHOD)` on a private method, `@Target(TYPE)` on a class manually instantiated with `new`, or using the annotation on a class outside the Spring context will not create an AOP transaction either. For interface annotations, proxy/weaving mechanisms and method visibility differ; prefer placing policies on **concrete service classes/methods** that can be observed and tested.

### 9.3. Propagation: Policy Applies Only Within the Real Boundary

When `@WriteTx` uses `REQUIRED` and a transaction already exists, the method **joins** that transaction. Isolation and timeout declared for a new transaction do not automatically upgrade the isolation or change the timeout of an already-open transaction.

If a caller is running a read-only transaction and invokes a `REQUIRED` `@WriteTx` method, the method may still join the existing transaction. Do not think `@WriteTx` creates an independent "write zone" with all new attributes; check policies at the entry point and consider existing-transaction validation when needed.

## 10. Common Mistakes

| Mistake | Why it is dangerous | How to fix |
| --- | --- | --- |
| Forgetting `@Transactional` meta-annotation | `@WriteTx` becomes just a plain Java annotation | Attach `org.springframework.transaction.annotation.Transactional` |
| Forgetting `RUNTIME` retention | Spring cannot see the metadata at runtime | Always declare `@Retention(RetentionPolicy.RUNTIME)` |
| Wrong `@Target` | Cannot be placed where intended | Choose `METHOD`, `TYPE` matching actual usage |
| Importing `jakarta.transaction.Transactional` and using Spring attributes | Different API; fails to compile or applies wrong policy | Use the right Spring annotation |
| Same-named attribute without clear override | Hard to verify effective metadata | Use `@AliasFor` and test merged attributes |
| Calling via `this.method()` | Spring proxy does not see internal calls | Place boundary at entry point or extract a bean |
| Catching checked exception and swallowing it | Interceptor sees normal return and may commit | Rethrow, or use rollback-only when appropriate |
| Mistaking `readOnly=true` for an absolute write ban | Some DBs/drivers do not enforce it | Treat only as a hint; still protect via roles/constraints |
| Using one policy for every use case | Long transactions, overly strong isolation, or wrong propagation | Design a small set of policies matching real needs |
| Stacking multiple conflicting policies in one place | Merged metadata selection may surprise you | Only one clear policy per site |
| Testing only with plain Java reflection | Does not verify Spring proxy/manager actually applied it | Test `findMergedAnnotation` **and** DB rollback |
| Referencing a nonexistent manager | Runtime failure resolving `TransactionManager` | Verify bean name/qualifier in context |

**Special note on rollback:** `rollbackFor = Exception.class` covers checked exceptions and most runtime exceptions. However, Spring may have `noRollbackFor`, default rollback rules, or other policies; design and test exact business exceptions rather than assuming every exception rolls back in every context. `rollbackForClassName` uses pattern matching and can match unexpectedly; prefer class literals like `rollbackFor = MyBusinessException.class` when the concrete type is known.

## 11. When Should You Use Composed Annotations?

Composed annotations are useful when:

- **Two or more groups of methods** need a stable, meaningful set of transaction settings.
- The policy has clear domain semantics such as `@ReadOnlyTx`, `@WriteTx`, `@OrdersWriteTx`.
- Multiple teams/services must avoid uncontrolled changes to propagation/rollback/isolation.
- The system has multiple transaction managers and needs a policy name to pick the right manager.
- You need rules that can be tested centrally when upgrading Spring or changing transaction managers.

Do not create dozens of annotations just to save a few characters. If a single method has unique semantics and no shared policy, using `@Transactional(...)` directly can be clearer. A pretty annotation name that hides `REQUIRES_NEW`, an overly short timeout, or an overly broad rollback rule makes consequences hard for readers to predict.

**Naming convention:** express **business/policy intent**, such as `@ReportReadTx` or `@PaymentWriteTx`. In the policy's description/Javadoc, document its scope, selected transaction manager, propagation, rollback conditions, and who owns changes when business requirements evolve.

## 12. Implementation and Testing Checklist

1. Group methods with matching transaction requirements; write down the policy in prose before writing the annotation.
2. Declare `@Target` and `@Retention(RUNTIME)`, attach Spring `@Transactional` as a meta-annotation, and add `@Documented`.
3. Fix important attributes; expose only attributes needing customization, declaring `@AliasFor` with the right target and type.
4. Place the annotation on concrete Spring service classes/methods; verify transaction management is enabled.
5. Ensure callers go through the Spring proxy, avoiding self-invocation or manual `new` service instantiation.
6. If multiple transaction managers exist, verify which bean/qualifier must be selected.
7. Test `AnnotatedElementUtils.findMergedAnnotation(...)` to confirm Spring synthesized the policy correctly.
8. Write DB integration tests: happy-path commit, rollback after mid-step failure, checked exceptions, and critical concurrency/invariants.
9. Re-check behavior when methods join an existing transaction; timeout, isolation, and `readOnly` do not automatically alter an outer transaction's properties.
10. Document the policy and Spring version used to catch semantic changes during framework upgrades.

## References

- Spring Framework — Using `@Transactional`, section **Custom Composed Annotations**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Declarative Transaction Implementation and AOP proxies: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rollback Rules: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — `@AliasFor` Javadoc (6.1.x): https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/core/annotation/AliasFor.html
- Spring Framework — `@Transactional` Javadoc (6.2.x): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html