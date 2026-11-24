# `@PostAuthorize`, Rollback, and Effects Outside the Transaction

## 1. Objective: Does Denying a Return Value Mean Undoing Side Effects?

Suppose a Spring service method creates a record, sends a notification, and returns an object containing `owner`. The application annotates it with:

```java
@Transactional
@PostAuthorize("returnObject.owner == authentication.name")
public RecordResult createFor(String owner) {
    // Write database, send notification, return RecordResult.
}
```

This is only a **method signature sample**, not a standalone Java program. If the caller is `bob` while the returned object belongs to `alice`, `@PostAuthorize` will reject the result (typically with an exception in the `AccessDeniedException` family). However, the more important question is: **is the record rolled back and is the sent notification retracted?**

You cannot conclude this from the annotations alone. At least three boundaries must be examined:

1. **Authorization boundary**: `@PostAuthorize` evaluates its condition **after the target method has executed and returned a value**.
2. **Transaction boundary**: commit/rollback depends on whether the transaction interceptor still wraps the point where the exception is thrown or whether the transaction has already finished.
3. **System boundary**: emails, HTTP requests, direct Kafka publishes, files, and Redis do not participate in the same database transaction and do not undo themselves when SQL rolls back.

**The most important rule:** `@PostAuthorize` is useful for protecting **the return of read data**; it should not be used as the sole permission check for write/delete/transfer operations or irreversible side effects. The official Spring Security documentation explicitly warns against using `@Transactional` together with `@PostAuthorize` on database-writing methods.

## 2. When Does `@PostAuthorize` Evaluate?

With Method Security enabled:

```java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
}
```

Spring Security uses an AOP interceptor to evaluate the annotation. Common pattern:

```java
@PostAuthorize("returnObject.owner == authentication.name")
public Document findOne(long id) {
    return repository.findById(id).orElseThrow();
}
```

In this snippet, `repository` and `Document` are application components. Meaning:

- `returnObject` is **the full object returned by the method**; the expression reads its `owner`.
- `authentication.name` is the current identity per `Authentication#getName()`.
- The target method runs first, and only afterward does Spring Security evaluate the expression.
- If the condition holds, the caller receives the object; if false, it throws `AccessDeniedException` or a corresponding subclass by default. In a properly configured HTTP servlet request, this behavior normally translates to HTTP 403.
- If the call does not pass through a Spring AOP proxy (e.g., manually `new`-ing the service or calling `this.findOne(...)` inside the same bean), the interceptor may not run.
- If the method already produced side effects before returning, the annotation **cannot turn back time**.

Timeline example:

```text
T0   caller invokes Spring-managed service through proxy
T1   "before" interceptors (e.g. @PreAuthorize) may check
T2   target method begins executing
T3   target INSERT / UPDATE / API call / publish message
T4   target returns RecordResult(owner="alice")
T5   @PostAuthorize reads returnObject.owner and bob's Authentication
T6   condition false → AuthorizationDeniedException / AccessDeniedException
T7   caller receives error; whether transaction rolls back depends on transaction advice position
```

**Distinction from `@PreAuthorize`:** pre-checking can block the call **before the target runs**, provided the expression has enough information from `Authentication` and method arguments. For actions with side effects, this is usually the more appropriate safeguard.

## 3. AOP Ordering Determines Whether the Transaction Sees the Exception

Both `@Transactional` and `@PostAuthorize` can be applied via Spring AOP. The two interceptors wrap the method according to **advisor order**; an interceptor with a smaller order usually sits **outside** an interceptor with a larger order. In Spring Security 6.x:

- `@PreAuthorize` has order 200.
- `@PostAuthorize` has order 500.
- `@EnableTransactionManagement`'s transaction advisor defaults to `Ordered.LOWEST_PRECEDENCE` (very large) if not reconfigured.

Actual ordering can differ when you set `order`, change `@EnableMethodSecurity(offset=...)`, register custom advisors, use an outer transaction, different propagation, or invoke across different proxies. Therefore, **observe the advisor chain and write integration tests** to draw conclusions, rather than inferring unconditionally from annotation source order.

### 3.1. Transaction Inside Post-Check: Committed Before Being Denied

In the common default setup with no outer transaction and the transaction advisor at lowest precedence:

```text
Caller
  → PostAuthorize advice (outer)
      → Transaction advice (inner)
          BEGIN
          → Target method: database write
          COMMIT
      ← Target result (transaction already ended)
      → PostAuthorize checks returnObject
          DENY → AccessDeniedException
Caller receives 403 / exception
```

Here **SQL has already committed before the post-check exception occurs**. Transaction advice is no longer active and cannot observe the exception to roll back. Even adding:

```java
@Transactional(rollbackFor = AccessDeniedException.class)
```

**does not help** if the exception arises **after the transaction has already committed**. `rollbackFor` only governs the transaction interceptor's decision while exceptions pass through the scope managed by that interceptor.

An HTTP 403, therefore, **does not prove the database remained unchanged**. Verify results with DB queries in tests or by inspecting transaction logs.

### 3.2. Transaction Wrapping Post-Check: Can Roll Back DB Changes

If transaction advice sits **outside** `@PostAuthorize` (order smaller than 500), it is still open when the post-check denies:

```text
Caller
  → Transaction advice (outer)
      BEGIN
      → PostAuthorize advice (inner)
          → Target method: database write
          ← Target result
          → check returnObject: DENY
          → throw AccessDeniedException
      ← exception propagates through transaction advice
      ROLLBACK (default for runtime exception)
Caller receives 403 / exception
```

Illustrative ordering configuration for Spring Security 6.x:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity
@EnableTransactionManagement(order = 300)
public class SecurityAndTransactionConfig {
}
```

With `@PreAuthorize` order 200, transaction order 300, and `@PostAuthorize` order 500:

```text
@PreAuthorize (200) → @Transactional (300) → @PostAuthorize (500)
    → target method → post-check → commit or rollback
```

This is an **example intentionally ordering advisors for illustration**, not a recommendation to change order in every application. Altering advisor order affects all `@Transactional` methods, changes when transactions open/close, and alters interactions with other advice. In real projects, prefer checking permissions **before writing** and opening the transaction afterward; if post-check rollback is truly needed, verify the chain with tests on the exact deployed version and configuration.

According to Spring Security, another coordination approach in some setups is ensuring `@EnableTransactionManagement` is processed before `@EnableMethodSecurity`; however, **declaration order or annotation names alone are insufficient to prove safety** when other advisor configurations exist. Using `order=300` here makes the outer/inner relationship explicit and testable.

### 3.3. Matrix of Critical Scenarios

| Scenario | When post-check denies | Data in DB transaction | Non-transactional effects |
|---|---|---|---|
| `@PostAuthorize` wraps an already-committed transaction | After commit | **Cannot roll back** committed changes | Not undone |
| Transaction wraps `@PostAuthorize`; exception escapes | Before commit | Typically **rolls back** on `AccessDeniedException` | Not undone |
| Caller has open transaction, method joins with `REQUIRED` | Before outer caller commit if exception propagates | Can roll back outer transaction per rollback rules | Not undone |
| Method uses `REQUIRES_NEW` and commits independently before post-check | After independent transaction commit | Independent transaction is not undone | Not undone |
| Unauthorized caller caught in `@PreAuthorize` before target runs | Before target side effects | No target changes to undo | No target effects |
| Exception caught/swallowed before transaction boundary or `noRollbackFor` set | May not roll back transaction | Depends on rollback-only and transaction rules | Not undone |

In these rows, "roll back" applies strictly to resources actually enlisted in **the same transaction** and managed by the transaction manager. It is not a mechanism to reverse arbitrary operations inside a JVM.

## 4. Why Doesn't `@Transactional` Automatically Guarantee Rollback?

### 4.1. Rollback Rules and Exception Timing

By default in Spring Framework 6.x, when the transaction interceptor **sees** an exception:
- `RuntimeException` or `Error` → marks rollback.
- Checked exception → normally **does not** roll back, unless declared in `rollbackFor` or matching rules are configured.
- `AccessDeniedException` is a runtime exception and therefore normally triggers rollback **if** the exception exits through transaction advice.
- `@Transactional(noRollbackFor = AccessDeniedException.class)` can allow the transaction to commit upon receiving that exception, absent other rollback-only conditions.
- Catching the exception and returning normally inside the transaction can prevent advice from seeing the error; handle rollback status explicitly if business logic requires it.

Example:

```java
@Transactional(rollbackFor = Exception.class)
public void performBusinessOperation() throws Exception {
    // Marks rollback even for unhandled checked Exceptions
    // if the exception propagates through the transaction interceptor.
}
```

The example above is an illustrative signature; it does not directly help `@PostAuthorize` if post-checking occurs outside the transaction.

### 4.2. Rollback Applies Only to Enlisted Transaction Resources

If `DataSourceTransactionManager` manages the JDBC connection, SQL statements on that same connection/transaction can roll back before commit. If a method writes to a second datasource not participating in the same transaction manager, Spring does not automatically roll back that second datasource.

Distinguish these states as well:
- **SQL executed / JPA flushed**: data may have been sent to the database yet remains uncommitted; rollback still works.
- **SQL committed**: another transaction cannot "undo" that commit via a later exception.
- **Data already received by a third party**: even if the database rolls back, external systems may have already sent emails, stored events, or changed state.

With `PROPAGATION_REQUIRES_NEW`, an inner transaction can commit independently of an outer transaction. Rolling back the outer transaction does not undo the inner transaction's commit. With multiple transaction managers or async flows, each boundary must be analyzed individually.

### 4.3. Transactions Are Advice, Not Annotation Magic

In default proxy mode for `@Transactional` and `@EnableMethodSecurity`, self-invocation normally goes straight to the target without passing through AOP advice:

```java
@Service
class ExampleService {
    public void outer() {
        inner(); // Call within the same object; may bypass proxy
    }

    @Transactional
    @PostAuthorize("returnObject.owner == authentication.name")
    public Document inner() {
        // ...
    }
}
```

This is a **warning pattern** and is not runnable because `Document` and imports are omitted. When a caller invokes `outer()` through the proxy, the call to `inner()` via `this` may skip both transaction management and post-authorization. Split into another service bean or route entry points through Spring-managed proxies; write integration tests instead of relying on annotations merely appearing in code.

## 5. Runnable Example: Database Rolls Back Yet "Simulated Email" Still Exists

The following example uses Java 17+, Spring Boot **3.5.6**, Spring Security 6.5.x managed by Boot, Maven, an H2 in-memory database, and `JdbcTemplate`. It intentionally shows three distinct outcomes:

1. **Transaction wraps post-check**: authorization denied → INSERT rolls back, yet the out-of-transaction effect still happens.
2. **Transaction commits inside the method**: authorization denied afterward → the committed INSERT remains.
3. **`@PreAuthorize` blocks upfront**: method never runs, producing neither INSERT nor external call.

No real email service is used. An in-memory component holding a list of notifications represents **an action not participating in the JDBC transaction**; that list is unaffected by SQL rollback.

### 5.1. Project Structure

```text
postauthorize-transaction-demo/
├── pom.xml
├── src/main/java/com/example/authztx/
│   ├── PostAuthorizeTransactionApplication.java
│   ├── SecurityAndTransactionConfig.java
│   ├── RecordResult.java
│   ├── FakeExternalGateway.java
│   └── WriteService.java
├── src/main/resources/schema.sql
└── src/test/java/com/example/authztx/WriteServiceTest.java
```

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>postauthorize-transaction-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
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
```

### 5.3. Application and Advisor Ordering

**`src/main/java/com/example/authztx/PostAuthorizeTransactionApplication.java`**

```java
package com.example.authztx;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PostAuthorizeTransactionApplication {
    public static void main(String[] args) {
        SpringApplication.run(PostAuthorizeTransactionApplication.class, args);
    }
}
```

**`src/main/java/com/example/authztx/SecurityAndTransactionConfig.java`**

```java
package com.example.authztx;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableMethodSecurity
@EnableTransactionManagement(order = 300)
public class SecurityAndTransactionConfig {
}
```

In this fixed example, transaction order 300 sits between `@PreAuthorize` (200) and `@PostAuthorize` (500). Consequently, the post-check exception passes through the transaction interceptor and can trigger rollback. In real applications, verify the advisor chain on your specific version before applying global ordering changes.

### 5.4. `schema.sql` and Result Class

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS audit_write (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    owner VARCHAR(100) NOT NULL
);
```

H2 is an embedded database in the example; Spring Boot can initialize `schema.sql` when the application uses an H2 datasource. For testing real systems, configure an appropriate datasource and schema migration strategy.

**`src/main/java/com/example/authztx/RecordResult.java`**

```java
package com.example.authztx;

public record RecordResult(String owner) {
    public String getOwner() {
        return owner;
    }
}
```

The `getOwner()` getter allows SpEL `returnObject.owner` to access the property cleanly.

### 5.5. Out-of-Transaction Effect Gateway

**`src/main/java/com/example/authztx/FakeExternalGateway.java`**

```java
package com.example.authztx;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import org.springframework.stereotype.Component;

@Component
public class FakeExternalGateway {
    private final List<String> sentEvents = new CopyOnWriteArrayList<>();

    public void send(String event) {
        sentEvents.add(event);
    }

    public List<String> events() {
        return List.copyOf(sentEvents);
    }

    public void clear() {
        sentEvents.clear();
    }
}
```

This in-memory store merely simulates an **external effect not participating in the JDBC transaction**. It is not an email server or event broker and does not model network delivery guarantees, yet it suffices to prove that a DB rollback does not call `clear()` on external resources.

### 5.6. Service: Three Execution Paths to Compare

**`src/main/java/com/example/authztx/WriteService.java`**

```java
package com.example.authztx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class WriteService {
    private final JdbcTemplate jdbc;
    private final FakeExternalGateway external;
    private final TransactionTemplate transactionTemplate;

    public WriteService(
            JdbcTemplate jdbc,
            FakeExternalGateway external,
            PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.external = external;
        this.transactionTemplate = new TransactionTemplate(transactionManager);
    }

    @Transactional
    @PostAuthorize("returnObject.owner == authentication.name")
    public RecordResult writeAndCallExternal(String owner) {
        jdbc.update("INSERT INTO audit_write(owner) VALUES (?)", owner);
        external.send("sent:" + owner);
        return new RecordResult(owner);
    }

    @PostAuthorize("returnObject.owner == authentication.name")
    public RecordResult writeWithEarlyCommit(String owner) {
        transactionTemplate.executeWithoutResult(status ->
            jdbc.update("INSERT INTO audit_write(owner) VALUES (?)", owner)
        );
        return new RecordResult(owner);
    }

    @Transactional
    @PreAuthorize("#owner == authentication.name")
    public RecordResult writeWithPreCheck(@P("owner") String owner) {
        jdbc.update("INSERT INTO audit_write(owner) VALUES (?)", owner);
        return new RecordResult(owner);
    }
}
```

In `writeAndCallExternal`, the transaction interceptor **wraps outside the post-check** due to the order 300 setting. If the user does not match `owner`, the post-check throws a runtime exception while the transaction is still open: the INSERT rolls back, yet `external.send(...)` already mutated the out-of-DB list.

In `writeWithEarlyCommit`, `TransactionTemplate` explicitly opens and completes the transaction **inside the method body**, before `@PostAuthorize` evaluates. Consequently, post-check denial cannot undo the committed INSERT. This is a **deterministic** simulation of an early commit boundary independent of `@Transactional`'s advisor order.

In `writeWithPreCheck`, the owner condition is checked before the target executes. An invalid user performs no INSERT. This is usually the right approach when permission information is available from method parameters.

### 5.7. Integration Tests for Commit/Rollback States

**`src/test/java/com/example/authztx/WriteServiceTest.java`**

```java
package com.example.authztx;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class WriteServiceTest {
    @Autowired
    private WriteService service;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private FakeExternalGateway external;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM audit_write");
        external.clear();
    }

    private int rows() {
        Integer count = jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_write", Integer.class
        );
        return count.intValue();
    }

    @Test
    @WithMockUser(username = "bob")
    void deniedPostCheckRollsBackJdbcButNotExternalEffect() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.writeAndCallExternal("alice")
        );
        assertEquals(0, rows());
        assertEquals(List.of("sent:alice"), external.events());
    }

    @Test
    @WithMockUser(username = "bob")
    void deniedPostCheckCannotUndoAlreadyCommittedTransaction() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.writeWithEarlyCommit("alice")
        );
        assertEquals(1, rows());
        assertTrue(external.events().isEmpty());
    }

    @Test
    @WithMockUser(username = "bob")
    void preAuthorizeBlocksBeforeAnyWrite() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.writeWithPreCheck("alice")
        );
        assertEquals(0, rows());
        assertTrue(external.events().isEmpty());
    }

    @Test
    @WithMockUser(username = "alice")
    void allowedPostCheckCommitsAndKeepsExternalEffect() {
        assertEquals(
            new RecordResult("alice"),
            service.writeAndCallExternal("alice")
        );
        assertEquals(1, rows());
        assertEquals(List.of("sent:alice"), external.events());
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn test
```

**Expected outcome:** Four tests pass (`Tests run: 4, Failures: 0, Errors: 0, Skipped: 0`). Maven/Spring logs may vary by environment; this is the **expected outcome by design**, not a claim that Maven was executed inside this lesson.

| Test | Valid permission? | Rows after call | External events | What it proves |
|---|---|---:|---|---|
| `deniedPostCheckRollsBackJdbcButNotExternalEffect` | No | 0 | `["sent:alice"]` | SQL rollback does not roll back external side effects |
| `deniedPostCheckCannotUndoAlreadyCommittedTransaction` | No | 1 | `[]` | Post-check does not undo an earlier commit |
| `preAuthorizeBlocksBeforeAnyWrite` | No | 0 | `[]` | Pre-check blocks before the method executes |
| `allowedPostCheckCommitsAndKeepsExternalEffect` | Yes | 1 | `["sent:alice"]` | Valid post-check allows commit |

**Testing note:** The tests **do not** annotate the test class with `@Transactional`. If the test itself opens an outer transaction and rolls back at the end of the test, observed results can differ because commit timing and ordering change. `@BeforeEach` clears data for each test on the embedded DB, and all methods are called through the Spring-injected bean so AOP interceptors execute.

## 6. Design for Production Business Logic: Authorize First, Then Write

### 6.1. Verify Permission on ID or Owner Before the Write Transaction

When input data already identifies the target resource, write:

```java
@PreAuthorize("@documentPermission.canEdit(authentication, #documentId)")
@Transactional
public void updateDocument(@P("documentId") long documentId,
                           String newTitle) {
    repository.updateTitle(documentId, newTitle);
}
```

This is an **integration pattern**, not runnable standalone because it requires entity/repository classes and the `documentPermission` bean. The method executes only if the `canEdit` policy passes. Never check permission using a client-supplied owner alone: the policy bean must verify that the caller has permission on the **real record** (and real tenant) from trusted data.

Actions vulnerable to **TOCTOU** (*time of check/time of use*): if permissions/ownership can change between check and write, you may need appropriate locking, re-checking inside the transaction, or an `UPDATE ... WHERE owner_id = ? AND id = ?` statement verifying the affected row count. `@PreAuthorize` does not solve race conditions by itself.

### 6.2. When Permissions Can Only Be Checked Against `returnObject`

A useful pattern is **read first, write second** across two service beans:

```java
@Service
public class DocumentReader {
    @PostAuthorize("returnObject.owner == authentication.name")
    public Document findAuthorized(long id) {
        return repository.findById(id).orElseThrow();
    }
}
```

```java
@Service
public class DocumentEditor {
    private final DocumentReader reader;

    public DocumentEditor(DocumentReader reader) {
        this.reader = reader;
    }

    @Transactional
    public void edit(long id, String title) {
        Document document = reader.findAuthorized(id);
        repository.updateTitle(document.getId(), title);
    }
}
```

This is a **structural pattern** requiring imports, repository, and `Document` class to compile. The crux is calling `DocumentReader` through a **Spring-injected bean**, rather than self-invocation. `findAuthorized` is read-only, so a denied caller causes no write side effects from `edit`. For complex workflows, `@PostAuthorize` on the read step can be replaced with a policy bean supplying conditions enforceable inside the write transaction. For data subject to concurrent updates, ensure permission state cannot change between read and write, or re-check at write time.

### 6.3. Enforce Invariants at the Data Layer

For resource-management operations, a permission-guarded SQL statement can act in one step:

```sql
UPDATE document
SET title = :new_title
WHERE id = :document_id
  AND owner_username = :authenticated_username
  AND tenant_id = :current_tenant_id;
```

Then check the affected row count. With 0 rows, return an appropriate error (not found or insufficient permission per anti-enumeration policy). Parameters must come from `Authentication` and a trusted tenant context, **never from a tenant self-declared by the request**. This ties the authorization decision and data mutation into one database operation, reducing races compared to separate read-check-write steps.

## 7. Effects Outside the Transaction: HTTP, Email, Messages, Cache, Files

### 7.1. Common Categories of Side Effects

| Side effect inside method | Does JDBC/JPA `@Transactional` auto-roll it back? | How to handle |
|---|---|---|
| `INSERT`/`UPDATE` on datasource enlisted in transaction | Possible, **if not yet committed** | Ensure tx boundary and rollback rules |
| Committed `REQUIRES_NEW` | Not rolled back by outer rollback | Avoid independent commits before authorization |
| Direct email/SMS send | No | Send after commit and after authorization; outbox if delivery guarantee needed |
| HTTP POST to another service | No | Design idempotency, saga/compensation when needed |
| Direct message publish to broker | Not by default | Outbox or separately verified coordinated transaction |
| File write, object storage upload | No | Defer, clean up files, or controlled compensation |
| Separate Redis/cache update | Not by default | Invalidate/update after commit with consistency rules |
| Writing audit logs to external system | No | Distinguish attempt vs. success logs; avoid announcing false outcomes |

For instance, sending an email inside a method and then having `@PostAuthorize` deny after return can give the user HTTP 403 while the third party **already received the email**. Even if the SQL transaction rolls back cleanly, an email cannot be "unsent."

One important nuance for log content: security logs recording **denied attempts** may intentionally persist outside the transaction; that is a separate audit concern. However, "payment succeeded" or "order created" events must not be emitted before the operation is authorized and committed.

### 7.2. Transaction-Bound Events: Sending After Commit

Spring Framework supports:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onDocumentCommitted(DocumentChanged event) {
    notificationGateway.notify(event);
}
```

This is a **listener pattern**, requiring beans, imports, and `DocumentChanged`/`notificationGateway` classes. The listener is invoked after the transaction **commits** successfully, rather than immediately when the event is published inside the transaction. With the default `fallbackExecution = false`, publishing an event **without an active matching transaction** means the listener will not run. `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION` phases exist for other purposes.

**Yet security ordering still matters:** if `@PostAuthorize` evaluates **after the transaction has committed**, an `AFTER_COMMIT` listener may also have already fired even though the caller is later denied. Thus `AFTER_COMMIT` only avoids sending when the transaction itself rolls back; it **does not fix** authorization checked too late. Before publishing business events, ensure permissions are already verified.

Moreover, publishing events solely in memory has a reliability gap: the process can crash right after commit before the listener finishes. If notification delivery is a strict requirement, use the outbox pattern.

### 7.3. Transactional Outbox for Critical Notifications

Inside **one** database transaction, after authorization has succeeded:

1. Write the business record and insert an `outbox_event` row describing the event to dispatch.
2. Commit both changes together; if rolled back, both vanish together.
3. A dedicated worker reads **committed** outbox rows and dispatches them to the broker/email/API.
4. On successful delivery, mark as sent; on failure, retry with backoff; receivers should be **idempotent** because duplicates can occur.

```text
Valid authorization
        ↓
SQL Transaction
   ├── UPDATE document
   └── INSERT outbox_event
        ↓
      COMMIT
        ↓
Worker reads outbox → dispatches event → marks sent
```

This is a **design pattern**, not a distributed transaction across an email server. Outbox prevents database-committed-but-event-lost crashes; in exchange, it requires a worker, retries, deduplication, monitoring, and failed-event handling. It still cannot cancel an email once sent.

Multi-system workflows may require **sagas and compensating actions**. Compensation creates a reverse business operation (such as a refund), not an atomic rollback of the original SQL transaction.

## 8. Advanced Pitfalls to Distinguish

### 8.1. Caller's Outer Transaction

Service A calls service B annotated with `@PostAuthorize`. If A already has a `REQUIRED` transaction and B joins it via `REQUIRED`, A's transaction may still be open after B returns. When B's post-check exception propagates upward without being swallowed, A may roll back all operations in its transaction. However, this outcome depends on advisor order, propagation, rollback rules, exception catching, and the transaction owner. **Never treat rollback observed in an integration test with an outer transaction as proof that all call paths are safe.**

### 8.2. Catching the Exception and Continuing to Commit

```java
try {
    protectedService.execute();
} catch (AccessDeniedException ex) {
    logger.warn("Access denied", ex);
}
// An outer transaction may continue if not marked rollback-only.
```

This is an **illustrative snippet**, not runnable without `protectedService` and logger. In Spring, an inner transaction interceptor may have already marked the transaction rollback-only when the exception passed through it; then the outer commit throws `UnexpectedRollbackException`. Conversely, if the exception occurred outside transaction advice, rollback-only is not set automatically. Never infer DB state from "it was caught"; inspect transaction status and test directly.

### 8.3. Launching Background/Async Work Before Return

An `@Async` call, new thread, internal queue, or `CompletableFuture` can run in a different transaction context—or with no transaction at all. `@PostAuthorize` on the original call does not retract work already handed off to a background worker. Also consider how `SecurityContext` propagates across threads, as it may not inherit automatically. When post-commit tasks are needed, use a pipeline with clear causality where events are emitted only after authorization is verified.

### 8.4. Read-Only Transactions Are Not Write Prevention

`@Transactional(readOnly = true)` is primarily an optimization hint for the transaction/ORM depending on the driver; it does not unconditionally forbid all SQL writes. `@PostAuthorize` on a read-only method fits better in **intent** because post-checking governs read results. Yet if the code still sends emails or updates a cache/broker, `readOnly` does not prevent external effects.

### 8.5. Security Is Not Identical to HTTP Status

In servlet web apps, `AccessDeniedException` is typically translated to HTTP 403 for authenticated users, or per configured entry point/exception handling. In batch jobs, CLIs, schedulers, and service tests there is no HTTP response; the exception remains a Java exception. If the application uses a custom denied handler (e.g., masking results), examine that behavior separately. HTTP 403 status and final database row counts are **two independent observations**.

### 8.6. Idempotency and Retry Ordering

When an external service was called yet the DB transaction rolled back, the caller may retry and trigger a second notification. For payment APIs, webhooks, messages, or emails, use idempotency keys, deduplication, and durable business state. An SQL transaction does not provide exactly-once network delivery; even an outbox typically offers at-least-once delivery, requiring idempotent consumers.

## 9. Review Checklist for a `@PostAuthorize` Method

1. **Reason for post-check:** do you truly need `returnObject` data to know permissions? If permissions are knowable from method args or record ID, switch to `@PreAuthorize`/policy bean before executing.
2. **Side effects:** inspect every execution path inside the target, including DB writes, emails, event publishing, HTTP calls, business logs, caches, files, and async tasks.
3. **Proxy:** verify callers go through the Spring-managed proxy, avoiding self-invocation or `private`/`final` methods where advice does not apply.
4. **Advisor chain:** record orders for `@PreAuthorize`, transactions, `@PostAuthorize`, and custom advisors. Avoid drawing conclusions from annotation order in source code.
5. **Transaction boundary:** identify who opens the transaction, when it commits, propagation, transaction manager, `REQUIRES_NEW`, and outer callers.
6. **Rollback rules:** confirm `AccessDeniedException` truly passes through the transaction interceptor, is not caught/`noRollbackFor`, and DB resources participate in the transaction.
7. **External side effects:** choose outbox or deferred actions when business requirements tie events to commit; provide retries/idempotency/compensation.
8. **Security tests:** test allowed and unauthorized users, and assert **DB state and external state** after the exception completes.
9. **Concurrency:** if permissions/ownership can change between check and update, protect invariants via query conditions, locks, or revalidation inside the same transaction.
10. **Other access paths:** other APIs, scheduled jobs, message consumers, and direct repository calls must also obey policy; post-checking on one service does not cover all entry points.

## 10. Self-Check Quiz

**Scenario A.** A `@Transactional @PostAuthorize` method updated 10 rows; the transaction advisor sits inside the post-authorization advisor; the method returns another user's object. Does the database roll back?

**Explanation:** If the transaction already committed before the post-check threw `AccessDeniedException`, no. The caller may receive 403 while all 10 rows remain committed.

**Scenario B.** The transaction advisor wraps outside `@PostAuthorize`, the JDBC transaction has not committed yet, `AccessDeniedException` propagates through the transaction interceptor, and there is no exception to rollback rules. Does JDBC roll back?

**Explanation:** Normally yes. It is an unchecked exception passing through the transaction interceptor; uncommitted DB changes roll back if participating in that transaction.

**Scenario C.** In Scenario B, the method called an SMS-sending API before returning. Is the SMS cancelled when the DB rolls back?

**Explanation:** No. HTTP/SMS sits outside the JDBC transaction; you must design send timing, outbox, idempotency, and compensating actions properly.

**Scenario D.** Before editing an order, the app uses `@PreAuthorize("@policy.canEdit(authentication, #id)")`. If denied, does the target method run?

**Explanation:** No, when the AOP proxy is properly applied. This is why pre-checking should be preferred before write operations.

## 11. References

- [Spring Security — Method Security / Authorization Method Results with @PostAuthorize](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html) — post-check sequencing, exceptions, and warning against using post-checking on DB-writing methods.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html) — propagation, transaction advisors, and defaults.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html) — rollback on unchecked exceptions, custom rules.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html) — `@TransactionalEventListener` and `AFTER_COMMIT`/`AFTER_ROLLBACK` phases.
- [Spring Security — AuthorizationInterceptorsOrder](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/authorization/method/AuthorizationInterceptorsOrder.html) — method security advisor ordering.

**Key takeaway:** `@PostAuthorize` controls **returning a result after the method has executed**. Rollback applies strictly to **resources still within an uncommitted transaction** when the exception reaches the right transaction interceptor per rollback rules. Emails, HTTP calls, messages, and independent commits do not undo themselves. To protect an operation with side effects, place permission checks **before execution**, verify transaction boundaries, and design event emission after an authorized commit.