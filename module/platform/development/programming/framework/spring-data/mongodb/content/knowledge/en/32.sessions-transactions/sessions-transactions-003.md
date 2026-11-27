# Registering MongoTransactionManager and Enabling Transaction Management

## 1. Why Register a Transaction Manager?

In the **Sessions and Transactions** chapter of **Spring Data MongoDB**, applications can interact with MongoDB using `MongoTemplate` or repositories. MongoDB guarantees that a write operation on **a single document** is atomic; however, business requirements sometimes mandate that multiple documents **commit or roll back together**.

For example, consider a system transferring an amount from account A to account B, where the two accounts are stored in two separate documents:

~~~text
Before transfer:
  Account A = 100,000 VND
  Account B =  20,000 VND

Operations:
  1. Deduct 30,000 VND from A
  2. Add 30,000 VND to B

After transfer:
  Account A =  70,000 VND
  Account B =  50,000 VND
  Total still = 120,000 VND
~~~

If you invoke two separate `updateFirst` calls, the process could crash after deducting A but before crediting B. **Each update being individually atomic does not mean both updates are atomic together.** To instruct both documents to participate in a single MongoDB transaction, a Spring application needs:

1. **A MongoDB topology that supports transactions**.
2. A `MongoDatabaseFactory` connected to the right MongoDB/database.
3. A `MongoTransactionManager` bean bound to that database factory.
4. Spring transaction interception infrastructure, such as `@EnableTransactionManagement` and `@Transactional` calls routed through a Spring proxy.
5. MongoDB operations that actually use the session/transaction managed by the manager.
6. Appropriate handling for commit, rollback, transient errors, and idempotency.

The focus of this lesson is **registering `MongoTransactionManager` and enabling transaction management for synchronous (imperative) flows**, then proving the transaction works via integration testing. The final sections contrast reactive access, multiple transaction managers, and common deployment mistakes.

> Examples use Java 17+, Spring Boot 3.x, Spring Data MongoDB 4.x, and a MongoDB server supporting multi-document transactions. Check your project's actual versions and configuration: some APIs/conventions differ across Spring Boot/Spring Data lines. Transactions do not automatically make operations outside MongoDB (email, HTTP, Kafka) atomic.

## 2. Distinguishing Session, Transaction, and Transaction Manager

Three concepts are frequently confused:

| Concept | Role | Automatically Creates a Transaction? |
|---|---|---|
| MongoDB Driver **ClientSession** | Holds context for a session, causal consistency, or a transaction when opened | No, unless `startTransaction` is called |
| **MongoDB transaction** | Multiple read/write operations in one transaction committed/aborted per server rules | Must be started and lifecycle-managed |
| **MongoTransactionManager** | Bridge between Spring transaction abstraction and MongoDB client session/transaction | Creates and manages when entering a Spring transaction boundary |
| **@Transactional** | Declares a transaction boundary on a service method | Only works when a manager/interceptor exists and the call passes through the proxy |
| **@EnableTransactionManagement** | Activates Spring annotation-driven transaction handling per configuration | Does not create a `MongoTransactionManager` bean or change server topology |
| **MongoTemplate** | Sends queries/writes to MongoDB using Spring Data mapping | Participates in the transaction when properly managed |

Standard flow:

~~~mermaid
flowchart TD
    A["HTTP / Worker calls Spring service proxy"] --> B["@Transactional interceptor"]
    B --> C["MongoTransactionManager"]
    C --> D["MongoDatabaseFactory"]
    D --> E["MongoDB ClientSession + start transaction"]
    E --> F["MongoTemplate / repositories use session"]
    F --> G["Update account A"]
    G --> H["Update account B"]
    H --> I{"Method finishes?"}
    I -->|"Normally"| J["Commit"]
    I -->|"Rollback rule or error"| K["Abort"]
~~~

**Without a `MongoTransactionManager` bean**, `@Transactional` does not automatically know it should use MongoDB transactions. If another transaction manager exists, Spring might even pick the **wrong** manager for JDBC/JPA. Configure explicitly.

### 2.1. A Plain Session Differs from a Transaction

A `ClientSession` can be used for operations within the same session **without opening a transaction**. Having a session does not prove commands commit together.

In Spring, `MongoTemplate` operations can participate in the session bound to the current thread while `MongoTransactionManager` manages a transaction. Do not create a separate driver session inside the method and assume it automatically joins the running Spring transaction.

### 2.2. Single-Document Atomicity Remains Useful

When an invariant resides inside **a single document**, you can write one command:

~~~javascript
db.inventory_products.updateOne(
  {
    _id: "p-101",
    tenantId: "tenant-a",
    stock_qty: { $gte: 3 }
  },
  { $inc: { stock_qty: -3 } }
);
~~~

Both filter and update are evaluated and applied atomically on that document. **There is no need to open a transaction** just to protect a single-document case like this. Multi-document transactions carry higher overhead and should be reserved for wider consistency boundaries.

## 3. MongoDB Server and Topology Requirements

Multi-document transactions require a MongoDB server and deployment environment that support them. In practice, the topology is usually a **replica set** or **sharded cluster** supporting transactions; a plain **standalone** MongoDB instance does not meet this requirement.

To avoid confusion:

- A single MongoDB container running plain `mongod` **does not automatically become a replica set**.
- A **single-node replica set** can be used in development/testing when configured properly.
- Production typically uses a replica set with enough nodes to meet availability/durability needs.
- Sharded clusters support transactions per server version/rules, with their own costs, limits, and operational steps.
- Driver URI, authentication, replica set discovery, and session support must all work; adding `@Transactional` in Java alone is not enough.

### 3.1. Checking Topology with mongosh

In an environment where access is permitted:

~~~javascript
db.hello();
~~~

For a replica set, the response may contain metadata such as `setName` and primary/member details. You can also inspect:

~~~javascript
rs.status();
~~~

`rs.status()` is appropriate in a `mongosh` session connected to a replica set with sufficient privileges; on standalone or under-privileged users, the command may fail. **Do not use the success/failure of a single command as your sole check**: also inspect the URI/connection options and run a real transaction test.

### 3.2. Spring Boot URI

Example for a **local/test environment with a replica set named `rs0`**:

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://localhost:27017/shopdb?replicaSet=rs0"
~~~

`localhost` is only appropriate when the application actually reaches MongoDB at that address. In Docker/Kubernetes, host/port, replica set member DNS, and network topology must be configured correctly; never copy a local URI to production.

In systems with accounts/passwords, secrets should come from a secret management mechanism; never hardcode credentials in lessons, Git repositories, or logs.

### 3.3. Preparing Collections/Indexes Before Transactions

For the transfer example, create the necessary collections and indexes **before** starting business transactions. Certain DDL operations and collection/index creation inside transactions have restrictions depending on server version/topology. Never perform implicit index migrations inside `@Transactional` services.

## 4. Dependencies: Spring Data MongoDB and Spring Transaction Abstraction

For Spring Boot 3.x, a common Gradle setup:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Data MongoDB and the Spring transaction abstraction are managed by the Spring Boot BOM when proper dependency management is used. Avoid forcing an incompatible standalone `spring-data-mongodb` or MongoDB Driver version just because you saw transaction APIs in docs for another version.

If the project already includes Spring Boot Starter, do not add duplicate dependencies. For non-Boot projects, configure the MongoDB client/database factory/template and transaction infrastructure manually.

### 4.1. Connection Configuration and Manager Registration Are Separate Steps

Spring Boot can automatically create `MongoClient`, `MongoDatabaseFactory`, and `MongoTemplate` based on starters/properties. However, **this does not automatically mean the application has a `MongoTransactionManager` bean registered as intended**. We will declare this bean explicitly.

Inspecting in the application context:

~~~java
Map<String, MongoTransactionManager> managers =
        applicationContext.getBeansOfType(
                MongoTransactionManager.class);
~~~

This snippet illustrates diagnostic logic inside a bean with an injected `applicationContext`; it is not a standalone Java class. Do not rely solely on seeing `@Transactional` in source code.

## 5. Registering MongoTransactionManager via @Configuration

This is the core configuration of the lesson.

**MongoTransactionConfig.java**

~~~java
package com.example.finance;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.MongoDatabaseFactory;
import org.springframework.data.mongodb.MongoTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class MongoTransactionConfig {

    @Bean("mongoTransactionManager")
    public MongoTransactionManager mongoTransactionManager(
            MongoDatabaseFactory mongoDatabaseFactory) {
        return new MongoTransactionManager(mongoDatabaseFactory);
    }
}
~~~

In this configuration:

1. `@Configuration` tells Spring this class registers beans.
2. `@Bean("mongoTransactionManager")` registers a manager with an explicit name.
3. The Spring-managed `MongoDatabaseFactory` provides the MongoDB connection/database scope.
4. `new MongoTransactionManager(factory)` creates Spring's `PlatformTransactionManager` for imperative MongoDB operations.
5. `@EnableTransactionManagement` enables processing of `@Transactional` annotations using Spring's default proxy mechanism.

**Key takeaway:** registering the manager alone does not make every query start a transaction. A transaction only starts when execution enters a Spring-recognized transaction boundary, such as a `@Transactional` method or `TransactionTemplate`.

### 5.1. Is @EnableTransactionManagement Always Required?

In many Spring Boot applications, transaction infrastructure may already be auto-configured when a transaction manager and required conditions are detected. This lesson uses **explicit `@EnableTransactionManagement`** to explain the mechanism and avoid guessing about configuration.

If your project already enables transaction management via auto-configuration or another config class, avoid duplicating configuration without checking. The goal is not "more annotations equals safer," but **one working transaction infrastructure with a clear manager and scope**.

### 5.2. Do Not Create a Separate MongoClient Just for the Manager

Design flaw:

~~~java
// Do not use a different MongoClient/database factory
// inside the transaction manager while the service's
// MongoTemplate connects to another factory.
~~~

If `MongoTemplate` and `MongoTransactionManager` are wired to **two different factories/clients**, the manager opening a transaction does not guarantee template operations enlist in that transaction. Prefer injecting the **same `MongoDatabaseFactory`** managed by the application context.

### 5.3. This Manager Serves Imperative Flows, Not Reactive

`MongoTransactionManager` is for **synchronous/thread-bound** (imperative) flows. Reactive Spring Data MongoDB uses `ReactiveMongoTransactionManager` and the Reactor context; do not attach an imperative manager to a reactive repository and expect transactions to work.

## 6. @Transactional Works Through a Spring Proxy

After registering the manager, create a Spring bean with a transactional method:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ExampleService {
    @Transactional(transactionManager = "mongoTransactionManager")
    public void performBusinessOperation() {
        // Call MongoTemplate / MongoRepository here.
    }
}
~~~

With default proxy configuration, when another bean invokes `performBusinessOperation()` **through the Spring proxy**, the interceptor uses the chosen manager to start a transaction, executes the body, and commits or rolls back based on the outcome.

### 6.1. @Transactional Is Not a Java Keyword

There is no Java compiler magic turning every MongoDB statement inside an annotated method into an atomic unit. The transaction only exists because Spring's **runtime infrastructure** and the driver's session are active.

### 6.2. Self-Invocation Bypasses the Default Proxy

~~~java
@Service
public class UnsafeExample {
    public void outer() {
        // Internal call on "this" does not go through the Spring proxy.
        inner();
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void inner() {
        // Not guaranteed to start a transaction
        // when called from outer() as shown above.
    }
}
~~~

Fix this by moving the transactional method into another bean and calling it via the injected Spring bean, or designing a **public transactional entrypoint** invoked by callers through the proxy. Do not treat self-injection/circular dependencies as a default trick without architectural review.

### 6.3. Thread-Bound Scope

Imperative Spring transactions rely on context bound to the executing thread. `@Async`, manually spawned threads, `CompletableFuture.supplyAsync(...)`, or another Reactor scheduler do not automatically inherit the thread-bound transaction:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void riskyMethod() {
    // If you offload work to another thread,
    // it does not automatically share the same transaction context.
}
~~~

If business logic truly needs operations in the same transaction, keep them within the transaction-bound flow, or design a separate boundary per worker. Never stretch a transaction over the network or let it run for long durations just to cover background work.

## 7. Sample Entity: Two Account Documents

We use the `money_accounts` collection. The two accounts live in **two separate documents**, so transfers cannot rely on single-document atomicity.

**MoneyAccount.java**

~~~java
package com.example.finance;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "money_accounts")
public class MoneyAccount {

    @MongoId(FieldType.STRING)
    private String id;

    private String tenantId;

    @Field("balance_vnd")
    private long balanceVnd;

    protected MoneyAccount() {
        // Spring Data object mapping.
    }

    public MoneyAccount(
            String id, String tenantId, long balanceVnd) {
        this.id = id;
        this.tenantId = tenantId;
        this.balanceVnd = balanceVnd;
    }

    public String getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public long getBalanceVnd() {
        return balanceVnd;
    }
}
~~~

**MoneyAccountRepository.java**

~~~java
package com.example.finance;

import org.springframework.data.mongodb.repository.MongoRepository;

public interface MoneyAccountRepository
        extends MongoRepository<MoneyAccount, String> {
}
~~~

Metadata to remember:

- Java `id` is stored as BSON `_id` of type String.
- Java `balanceVnd` maps to BSON `balance_vnd` via `@Field`.
- `tenantId` must come from a trusted authentication context when updating; MongoDB does not automatically inject tenant filters for us.
- The currency unit is whole VND represented as `long`; multi-currency or fractional systems need a more precise model. Addition/subtraction must also check overflow and business invariants.

Create test data:

~~~javascript
db.money_accounts.insertMany([
  {
    _id: "A",
    tenantId: "tenant-a",
    balance_vnd: NumberLong(100000)
  },
  {
    _id: "B",
    tenantId: "tenant-a",
    balance_vnd: NumberLong(20000)
  }
]);
~~~

Never run repeated seed scripts against a production collection. In integration tests, seed only inside an isolated database.

## 8. Transfer Service Using MongoTemplate and @Transactional

**MoneyTransferService.java**

~~~java
package com.example.finance;

import com.mongodb.client.result.UpdateResult;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MoneyTransferService {

    private final MongoTemplate mongo;

    public MoneyTransferService(MongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(transactionManager = "mongoTransactionManager")
    public void transfer(
            String authenticatedTenantId,
            String fromAccountId,
            String toAccountId,
            long amountVnd) {

        if (authenticatedTenantId == null
                || authenticatedTenantId.isBlank()
                || fromAccountId == null || fromAccountId.isBlank()
                || toAccountId == null || toAccountId.isBlank()
                || fromAccountId.equals(toAccountId)
                || amountVnd <= 0) {
            throw new IllegalArgumentException("Invalid transfer details");
        }

        Query debitFilter = Query.query(
                Criteria.where("id").is(fromAccountId)
                        .and("tenantId").is(authenticatedTenantId)
                        .and("balanceVnd").gte(amountVnd));

        UpdateResult debit = mongo.updateFirst(
                debitFilter,
                new Update().inc("balanceVnd", -amountVnd),
                MoneyAccount.class);

        if (debit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Invalid source account or insufficient balance");
        }

        Query creditFilter = Query.query(
                Criteria.where("id").is(toAccountId)
                        .and("tenantId").is(authenticatedTenantId));

        UpdateResult credit = mongo.updateFirst(
                creditFilter,
                new Update().inc("balanceVnd", amountVnd),
                MoneyAccount.class);

        if (credit.getMatchedCount() != 1) {
            throw new IllegalStateException(
                    "Destination account does not exist or does not belong to tenant");
        }

        // When the method returns normally, the interceptor commits.
    }
}
~~~

In this code:

1. `@Transactional(transactionManager = "mongoTransactionManager")` explicitly selects the MongoDB manager.
2. `MongoTemplate` injected by Spring uses the session bound by the transaction manager properly.
3. Debit includes a **sufficient-balance condition** so the balance never goes negative.
4. Credit restricts to the same `tenantId` so it cannot write to another tenant's account.
5. If debit/credit fails to match, the method throws an unchecked exception. Under default rollback rules, the transaction aborts.
6. **Do not use two read–modify–save cycles** for balances: `$inc` in the database avoids stale overwrites on a field.

### 8.1. Why Check matchedCount Instead of Trusting the Absence of Exceptions?

`updateFirst` can be valid and throw no error while returning `matchedCount = 0` when the predicate does not match. For transfers, that is a business failure: if debit does not match, credit must not run; if credit does not match, debit must roll back.

Do not assume `matchedCount = 0` always means "account does not exist"; it can also mean wrong tenant, insufficient balance, or an unmet extra filter. HTTP status mapping rules must be defined separately.

### 8.2. Why Is a Single Update on One Account Not Enough?

Deducting from A and adding to B are each **atomic single-document updates**. However, the invariant "the sum of both accounts remains constant" requires both documents to commit together, which is why the transaction matters.

### 8.3. Why Not Send Email or Call HTTP Inside the Transaction?

A call to an external payment system or sending an email **does not participate in the MongoDB transaction**. If the MongoDB server aborts after the email has been sent, the email cannot be unsent. An outbox pattern and idempotent consumer are usually more suitable.

### 8.4. Data Conditions That Must Be Checked Before Production

This is a *data-transaction* example, **not yet a production money-transfer system**. You still need an immutable ledger, idempotency by transfer ID, currency checks, overflow checks, limits/permissions, auditing, double-spend protection on other write paths, handling of transient errors, and unknown commit outcome handling.

## 9. Actual Commit and Rollback Timeline

Both `updateFirst` calls inside the `@Transactional` service execute within the transaction session. Afterward, the outcome depends on whether the method completes normally or throws an error.

### 9.1. Success Case

~~~text
Caller -> Spring proxy
  -> MongoTransactionManager: open session + startTransaction
     -> debit(A, 30000), matched=1
     -> credit(B, 30000), matched=1
     -> service returns normally
  -> transaction manager: commit
Caller receives result

After commit:
A = 70000
B = 50000
~~~

### 9.2. Invalid Debit Case

~~~text
Caller -> Spring proxy
  -> transaction begin
     -> debit(A, 30000), matched=0
     -> throw IllegalStateException
     -> DO NOT run credit(B)
  -> abort transaction
Caller receives exception
~~~

### 9.3. Credit Failure After Debit

~~~text
Caller -> Spring proxy
  -> transaction begin
     -> debit(A, 30000), matched=1
     -> credit(B, 30000), matched=0
     -> throw IllegalStateException
  -> abort transaction
Caller receives exception

After abort:
A still = 100000
B still = 20000 (if B exists but failed to match)
~~~

**What must be proven by an integration test** is that A was modified inside the transaction, yet **the change was not committed** after the method threw an error. Do not merely assert an exception was thrown; a non-transactional service could also throw an exception after debit while leaving A permanently deducted.

### 9.4. Errors Can Still Happen at Commit After Service Return

The method body finishing cleanly **does not guarantee the client receives a successful commit**. The transaction manager must still send the commit command; commit can encounter timeouts, transient errors, or an unknown outcome. Distinguish:

- Error occurring **inside the body** -> framework handles rollback per rules.
- Error **during commit** -> transaction state must be classified/reconciled per MongoDB semantics.
- Client loses response **after successful commit** -> retrying the whole transfer can double the effect without idempotency.

Displaying "success" in a web UI solely because the method body finished without considering commit outcomes is a brittle design.

## 10. Rollback Rules: Unchecked, Checked, and Caught Exceptions

Spring's transaction proxy applies rollback rules. Under common Spring Framework defaults:

- `RuntimeException` and `Error` trigger rollback.
- Checked exceptions normally **do not trigger rollback by default**, unless configured via a rollback rule.
- Newer Spring versions may support customizing default rollback rules; verify your project's configuration.

Example:

~~~java
@Transactional(
        transactionManager = "mongoTransactionManager",
        rollbackFor = java.io.IOException.class)
public void processWithCheckedFailure() throws java.io.IOException {
    // MongoDB writes ...
    throw new java.io.IOException("Process error");
}
~~~

When business logic has checked exceptions that must roll back, **specify `rollbackFor` explicitly**. Never assume every exception rolls back automatically.

### 10.1. Swallowing Exceptions Can Cause the Transaction to Commit

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void unsafe() {
    try {
        debit();
        credit();
    } catch (RuntimeException ex) {
        logger.warn("Transfer failed", ex);
        // Method still returns normally.
        // Transaction interceptor may treat it as success.
    }
}
~~~

`logger` and the two methods above are illustrative within a service that declares them. **If an exception is caught and not rethrown**, the transaction interceptor normally receives no rollback signal from the invocation. Certain driver/transaction-state errors may mark the transaction doomed internally, but **never rely on that**.

A better approach:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void transferOrFail() {
    debit();
    credit(); // If a business error requires rollback, throw an exception.
}
~~~

If there is a reason to catch and still roll back, you can mark rollback-only via the Spring transaction API inside the active transaction; however, prefer throwing a clear exception and handling it outside the transaction layer.

### 10.2. Where to Handle Errors

~~~text
Controller / Job boundary
    try:
        call @Transactional service via Spring proxy
    catch:
        translate error into response / retry policy

@Transactional Service
    validate
    MongoDB writes
    throw when an invariant fails
~~~

With this structure, the exception passes **through the transaction interceptor** before the controller catches and handles it, giving the framework a chance to abort the transaction according to its rules.

## 11. Propagation and Transaction Scope

`@Transactional` supports propagation. Its exact effect must be understood within the transaction manager in use.

| Propagation | General Meaning | Notes for MongoDB |
|---|---|---|
`REQUIRED` | Join current transaction or create a new one | Usually the appropriate default for a service boundary |
`SUPPORTS` | Join if present; otherwise run non-transactionally | Easy to accidentally write outside a transaction if caller lacks one |
`MANDATORY` | Must already have an active transaction | Useful for helpers that may only run inside a transaction |
`REQUIRES_NEW` | Request a new independent transaction, suspending the old scope if supported | Must account for resources/sessions and avoid holding multiple long transactions |
`NOT_SUPPORTED` | Run outside a transaction, suspending current scope if supported | Do not use for mandatory all-or-nothing steps |
`NEVER` | Throw an error if currently inside a transaction | Suitable for operations disallowed inside transactions |
`NESTED` | Relies on savepoints/nested transactions if manager supports them | **Do not assume `MongoTransactionManager` has JDBC-like savepoints/nested transactions** |

Example of a helper that must only be called inside an existing transaction:

~~~java
import org.springframework.transaction.annotation.Propagation;

@Transactional(
        transactionManager = "mongoTransactionManager",
        propagation = Propagation.MANDATORY)
public void writeLedgerEntry(...) {
    // Requires caller's transaction.
}
~~~

The fragment above belongs inside a Spring bean with a concrete implementation. `Propagation.MANDATORY` catches some cases of calling the helper outside a transaction, though you must still ensure the transaction **is actually a MongoDB transaction** and `MongoTemplate` uses the same factory.

### 11.1. Do Not Put @Transactional on Every Method and Guess the Effect

If an outer method opens a transaction and calls a `REQUIRED` helper via a Spring proxy, they can share the same transaction. However, self-invocation, the wrong manager, a new thread, or a different propagation attribute can break the intended boundary.

Define **one main transaction entrypoint**, keep its scope short, state invariants, and test actual rollbacks.

### 11.2. Do Not Use NESTED as a MongoDB Savepoint

MongoDB multi-document transactions do not support nested transactions/savepoints in the JDBC sense by default. Do not design "roll back part B while keeping part A in the same transaction" by adding `Propagation.NESTED` without verifying manager and server capabilities.

If one branch can fail without aborting the entire business process, consider changing the transaction model or storing explicit state/compensation.

## 12. Programmatic Transaction Management with TransactionTemplate

Not every application wants annotations on every flow. Spring provides `TransactionTemplate` to define explicit transaction boundaries:

**MongoTransactionTemplateConfig.java**

~~~java
package com.example.finance;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class MongoTransactionTemplateConfig {

    @Bean("mongoTransactionTemplate")
    public TransactionTemplate mongoTransactionTemplate(
            @Qualifier("mongoTransactionManager")
            PlatformTransactionManager manager) {
        return new TransactionTemplate(manager);
    }
}
~~~

Usage from a Spring service:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ProgrammaticTransferService {
    private final TransactionTemplate transactions;
    private final MongoTemplate mongo;

    public ProgrammaticTransferService(
            @Qualifier("mongoTransactionTemplate")
            TransactionTemplate transactions,
            MongoTemplate mongo) {
        this.transactions = transactions;
        this.mongo = mongo;
    }

    public void doWork() {
        transactions.execute(status -> {
            // MongoTemplate operations inside this callback.
            // Throw RuntimeException if business logic fails.
            return null;
        });
    }
}
~~~

This is a **programmatic transaction scope** example, not a full transfer implementation. It makes the "begin -> callback -> commit/rollback" boundary explicit without relying on a `@Transactional` method being called through a proxy.

### 12.1. When to Use TransactionTemplate?

- A small block of code needs an explicit transaction inside a complex service.
- Tight control over callback boundaries and return values is required.
- You want to avoid `@Transactional` self-invocation pitfalls when the design fits a template.
- Multiple managers exist and you want to inject an explicit MongoDB template.

Do not use `TransactionTemplate` to turn a minutes-long workflow into a long-running transaction. It still uses `MongoTransactionManager` and remains subject to MongoDB session/transaction limits.

### 12.2. Do Not Nest Templates and Annotations Arbitrarily

A `TransactionTemplate` callback inside a `@Transactional` method may join the existing transaction or create another scope depending on propagation. Do not assume two annotation/template layers yield "double atomicity." Always determine the transaction boundary from the manager/server perspective.

## 13. How Is the Session Bound to MongoTemplate?

Inside an imperative transaction managed by `MongoTransactionManager`, Spring Data binds the `ClientSession` to a thread-bound resource used by `MongoTemplate` and repositories sharing the same factory.

~~~text
Request-handling thread
  Spring transaction context
      -> MongoTransactionManager
          -> ClientSession + transaction
              -> MongoTemplate.updateFirst(A)
              -> Repository.save(B)
              -> MongoTemplate.findOne(C)
  commit/rollback
~~~

Requirement: templates/repositories must use a **compatible `MongoDatabaseFactory`** and Spring transaction infrastructure must be active.

### 13.1. Do Not Arbitrarily Grab Native Collections and Bypass the Session

~~~java
// Inside a @Transactional method.
mongo.updateFirst(query, update, MoneyAccount.class);

// Direct driver operations via MongoCollection may need
// an explicit ClientSession passed to join the transaction.
mongo.getCollection("money_accounts")
        .updateOne(rawFilter, rawUpdate);
~~~

This snippet illustrates the **risk** of mixing Spring Data and Java Driver paths; `rawFilter`/`rawUpdate` are BSON documents built in another scope. Never assume a direct driver command on a collection automatically uses the thread-bound Spring transaction like the template does. If forced to use the native driver, verify the session API and how to enlist it in that specific transaction.

### 13.2. Another MongoTemplate May Use the Wrong Factory

If an application configures multiple MongoDB databases:

~~~text
mongoTemplateA -> databaseFactoryA
mongoTemplateB -> databaseFactoryB
mongoTransactionManager -> databaseFactoryA
~~~

then the transaction manager for A does not automatically manage writes on B. To cover the whole business operation in a transaction, ensure the same MongoDB deployment/session is used and operations enlist properly; **there is no "transaction across two MongoDB servers" merely because both templates use Spring**.

### 13.3. Session Synchronization When Using Other Managers

Spring Data MongoDB provides `SessionSynchronization` settings for session/transaction integration scenarios. However, do not modify `mongoTemplate.setSessionSynchronization(...)` based on an isolated snippet when the system already uses `MongoTransactionManager` properly. Understand which manager owns the transaction, which scope binds the session, and test BSON commands/rollbacks after any change.

## 14. Multiple Transaction Managers

An application may simultaneously have:

- `MongoTransactionManager` for MongoDB.
- `DataSourceTransactionManager` or `JpaTransactionManager` for a relational database.
- A transaction manager for a different MongoDB database/deployment.

In this case, `@Transactional` without specifying a manager easily causes confusion:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void updateMongoData() {
    // MongoTemplate operations
}
~~~

Naming `@Bean("mongoTransactionManager")` as in section 5 keeps the manager name clear. If one manager should be default, you can configure `@Primary` or `TransactionManagementConfigurer` as needed, but evaluate the entire application before changing the default.

### 14.1. Choosing the Wrong Manager Creates No MongoDB Transaction

For instance, a method modifies MongoDB while wrapped by `JpaTransactionManager`. A JDBC/JPA transaction may run, yet **MongoDB writes are not automatically enlisted in the JDBC transaction**. Specify the right manager in the annotation and test MongoDB rollback to avoid false assumptions.

### 14.2. Two Transaction Managers Do Not Create a Distributed Transaction

~~~text
@Transactional("mongoTransactionManager")
  update MongoDB
  update PostgreSQL
~~~

This does not mean MongoDB and PostgreSQL commit/roll back together. A single transaction manager cannot coordinate ACID across two independent systems. Neither `ChainedTransactionManager` nor nested transaction managers automatically provide XA-style distributed atomicity.

If a business workflow spans multiple systems, consider **outbox, saga, compensation, idempotency, and reconciliation**, or a dedicated orchestration solution with well-analyzed limits.

## 15. Transaction Options: Read/Write Concern, Read Preference, and Timeout

When using MongoDB transactions, understand the configuration and semantics of:

- **Read concern**: consistency level of data read inside the transaction.
- **Write concern**: server commit/write acknowledgment level.
- **Read preference**: how replicas are chosen for reads; transactions have specific restrictions regarding primary and read operations.
- **`maxCommitTime`**, lifetime/timeouts, and other server/driver limits.

Example building `TransactionOptions` with the MongoDB Java Driver:

~~~java
import com.mongodb.ReadConcern;
import com.mongodb.WriteConcern;
import com.mongodb.TransactionOptions;

TransactionOptions options = TransactionOptions.builder()
        .readConcern(ReadConcern.SNAPSHOT)
        .writeConcern(WriteConcern.MAJORITY)
        .build();
~~~

When configuring the manager on Spring Data versions whose constructor accepts options, you can pass these options into `MongoTransactionManager`. **Do not attach options arbitrarily to every transaction**; define the consistency/durability contract first. Benchmark the latency cost of `snapshot`/`majority` read concern and `majority` write concern.

### 15.1. @Transactional(readOnly = true) Does Not Mean "No Transaction"

`readOnly = true` in Spring is usually a **hint/semantic indicator** to transaction infrastructure, not a security mechanism preventing MongoDB writes. With `MongoTransactionManager`, a read-only scope may still start a session/transaction to serve reads depending on version/config.

Do not rely on `readOnly` to protect an endpoint from writing data; database privileges, code reviews, and policies must still be enforced.

### 15.2. Spring's IsolationLevel Does Not Automatically Equal Arbitrary MongoDB Isolation

MongoDB transactions have their own read concern/snapshot semantics and limits. Do not expect `@Transactional(isolation = Isolation.SERIALIZABLE)` to suddenly make MongoDB support RDBMS-style isolation levels if the manager/server does not provide them. Read the version documentation and test specific invariants.

### 15.3. Keep Transactions Short

Opening a transaction and waiting for user confirmation, calling slow network services, uploading files, or sleeping is poor practice. Long-running transactions increase contention, memory/working-set pressure, and the risk of transient errors.

Design short services: validate input -> perform database writes that must commit together -> return. Heavy external work belongs outside the transaction or behind an outbox/worker.

## 16. Imperative and Reactive Transaction Managers Are Not Interchangeable

**`MongoTransactionManager`** is for `MongoTemplate`/imperative MongoDB repositories. If your project uses **`ReactiveMongoTemplate`** and reactive repositories, it needs a dedicated manager:

~~~java
package com.example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

@Configuration
public class ReactiveMongoTxConfig {

    @Bean("reactiveMongoTransactionManager")
    public ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }
}
~~~

In a reactive pipeline, the transaction context propagates via the **Reactor Context**, not the thread-local context of imperative flows. A `Mono` or `Flux` that is created but **not subscribed** executes no database operations; the transaction boundary must wrap the reactive chain that actually executes.

### 16.1. TransactionalOperator for Reactive Flows

~~~java
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;

TransactionalOperator operator =
        TransactionalOperator.create(reactiveMongoTransactionManager);

Mono<Void> work = debitReactive()
        .then(creditReactive())
        .as(operator::transactional);
~~~

This fragment belongs in a bean where `reactiveMongoTransactionManager`, `debitReactive()`, and `creditReactive()` are declared. Reactor's `Mono` must be imported; this illustrates transaction wrapping, not a complete production service.

Never call `block()` inside a reactive chain and assume imperative writes automatically enlist in the same reactive MongoDB session. If a workflow must combine imperative and reactive logic, analyze the transaction boundaries explicitly rather than mixing managers.

### 16.2. Pair @Transactional with the Matching Return Type

In Spring, reactive transaction interception works with reactive return types and a reactive transaction manager. A method returning `Mono` configured with an imperative manager, or a `void` method expected to join a reactive manager, leads to errors or unexpected behavior.

When a codebase has both types, assign **distinct bean names** and pick the manager explicitly:

~~~java
@Transactional(transactionManager = "mongoTransactionManager")
public void imperativeOperation() {
    // MongoTemplate operations
}

@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> reactiveOperation() {
    // ReactiveMongoTemplate operations
    return Mono.empty();
}
~~~

The snippet above only illustrates annotations and signatures and performs no database writes. It only applies when methods live on Spring-managed beans and the respective imperative/reactive infrastructure and dependencies are configured.

## 17. Transaction Retries and Unknown Commit Outcomes

MongoDB transactions can encounter **write conflicts** or transient errors when concurrent requests modify hot documents. The driver/server attach error labels such as `TransientTransactionError` or `UnknownTransactionCommitResult` on applicable failures.

Never handle all exceptions with:

~~~java
while (true) {
    transferService.transfer(...);
}
~~~

This is an anti-pattern: unbounded retries can amplify load, and if the transaction **already committed but the response was lost**, re-running the business operation as a new transfer can move money **twice**.

### 17.1. Distinguishing Three Cases

| Case | Handling Strategy |
|---|---|
Transaction definitely aborted with an identified transient error | Retry the **entire transaction** with backoff/bounds and idempotent logic |
Outcome of `commitTransaction` is unknown | Per driver/server rules, retry commit or **reconcile state**; do not assume abort |
Business exception from insufficient funds/wrong tenant | **Do not** retry blindly; return business error |

Certain driver/API paths provide helpers implementing MongoDB's transaction retry spec. When using Spring `@Transactional`, understand which retries are handled by the driver/framework and which the application must handle. Never slap a generic `@Retryable` over all exceptions and assume it is correct.

### 17.2. Idempotency of the Entire Transfer

So users can retry a transfer after a timeout without transferring money twice, record a stable **transfer ID** durably alongside account changes inside the transaction:

~~~text
Transaction:
  validate transferId has not been processed
  debit A
  credit B
  insert transfer record with unique(tenantId, transferId)
Commit
~~~

The unique constraint and duplicate-key handling must be designed carefully for contention. After a timeout, a request with the same `transferId` should receive **already processed/in progress/unknown** status per contract, rather than simply performing a second transfer.

### 17.3. Transactional Outbox When Publishing Events

If a successful transfer must also publish an event:

~~~text
MongoDB transaction:
  update A
  update B
  insert outbox event (unique eventId)

Outbox worker (outside transaction):
  read unpublished events
  publish
  mark progress
~~~

The worker may publish and crash before marking completed, so consumers must handle duplicate messages. Outbox prevents committing account changes while **having no event data to publish**, rather than magically providing "exactly once" over the network.

## 18. Configuring Real MongoDB for Integration Tests

A unit test mocking `MongoTemplate` cannot prove rollback. Integration tests must run against a **transaction-capable MongoDB topology**, with the manager genuinely registered and operations actually enlisted in the same transaction.

Two common options:

1. **Testcontainers MongoDB** compatible with your Spring Boot/Testcontainers version, configured in a supported **single-node replica set** mode.
2. A **dedicated test MongoDB replica set**, with a connection URI specifying `replicaSet` and test credentials/ports.

In Spring Boot 3.x, `@DataMongoTest` sets up the Spring Data MongoDB test slice, but **does not start a server automatically**. When using Testcontainers, container configuration/`@DynamicPropertySource` or `@ServiceConnection` must follow your library version and provide a connection string with valid sessions/replica set.

### 18.1. Sample Test Properties with a Running Replica Set

~~~yaml
spring:
  data:
    mongodb:
      uri: "mongodb://localhost:27017/transaction_test?replicaSet=rs0"
~~~

Use this address only if a test MongoDB replica set `rs0` is actually running there. **Never point integration tests that delete/seed data at shared or production databases.**

### 18.2. Test Connection Preflight

Before treating transaction tests as meaningful:

- The replica set has elected a primary and the driver has discovered the topology.
- The `money_accounts` collection exists or is prepared in setup **outside the transaction**.
- The test user has required read/write permissions.
- `MongoTransactionConfig` is imported/scanned into the application context.
- No other transaction manager is picked instead of the MongoDB manager.
- The test method is not accidentally wrapped in a large test-framework transaction that makes "rollback" assertions misleading.

In the test below, the test method has **no `@Transactional`**; the transaction boundary sits on `MoneyTransferService.transfer` and is entered via the service proxy.

## 19. Integration Test: Proving Commit and Rollback

**MoneyTransferIntegrationTest.java**

~~~java
package com.example.finance;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;

@DataMongoTest
@Import({
        MongoTransactionConfig.class,
        MoneyTransferService.class
})
class MoneyTransferIntegrationTest {

    @Autowired
    MongoTemplate mongo;

    @Autowired
    MoneyTransferService transfers;

    @BeforeEach
    void seed() {
        // Isolated test database data only.
        // Never run against production/shared databases.
        mongo.remove(new Query(), MoneyAccount.class);
        mongo.insert(
                new MoneyAccount("A", "tenant-a", 100000L));
        mongo.insert(
                new MoneyAccount("B", "tenant-a", 20000L));
    }

    private long balance(String id) {
        MoneyAccount account =
                mongo.findById(id, MoneyAccount.class);
        assertThat(account).isNotNull();
        return account.getBalanceVnd();
    }

    @Test
    void transferCommitsBothDocuments() {
        transfers.transfer("tenant-a", "A", "B", 30000L);

        assertThat(balance("A")).isEqualTo(70000L);
        assertThat(balance("B")).isEqualTo(50000L);
        assertThat(balance("A") + balance("B"))
                .isEqualTo(120000L);
    }

    @Test
    void missingDestinationRollsBackSourceDebit() {
        assertThatThrownBy(() ->
                transfers.transfer(
                        "tenant-a", "A", "MISSING", 30000L))
                .isInstanceOf(IllegalStateException.class);

        // Debit executed inside the transaction,
        // but must roll back when credit fails to match.
        assertThat(balance("A")).isEqualTo(100000L);
        assertThat(balance("B")).isEqualTo(20000L);
    }

    @Test
    void insufficientBalanceDoesNotCreditDestination() {
        assertThatThrownBy(() ->
                transfers.transfer("tenant-a", "A", "B", 200000L))
                .isInstanceOf(IllegalStateException.class);

        assertThat(balance("A")).isEqualTo(100000L);
        assertThat(balance("B")).isEqualTo(20000L);
    }

    @Test
    void crossTenantDestinationIsNotCredited() {
        mongo.insert(
                new MoneyAccount("C", "tenant-b", 50000L));

        assertThatThrownBy(() ->
                transfers.transfer("tenant-a", "A", "C", 30000L))
                .isInstanceOf(IllegalStateException.class);

        assertThat(balance("A")).isEqualTo(100000L);
        assertThat(balance("C")).isEqualTo(50000L);
    }

    @Test
    void invalidAmountIsRejectedWithoutWrites() {
        assertThatThrownBy(() ->
                transfers.transfer("tenant-a", "A", "B", 0L))
                .isInstanceOf(IllegalArgumentException.class);

        assertThat(balance("A")).isEqualTo(100000L);
        assertThat(balance("B")).isEqualTo(20000L);
    }
}
~~~

### 19.1. The Most Important Test Is Rollback After Debit

The `missingDestinationRollsBackSourceDebit` test ensures:

1. Account A has at least 30,000, so the debit update **matches 1**.
2. Account `MISSING` does not exist, so the credit **matches 0**.
3. The service throws an unchecked exception.
4. When the method exits with an error and the manager aborts the transaction, A returns to 100,000.

If `@Transactional` is removed or the manager has no effect, the same test leaves A at 70,000. This is much stronger proof than merely checking that an exception was thrown.

### 19.2. Tests Must Be Independent

`@BeforeEach` clears account data to re-seed A/B. When tests run in parallel against the same database, clearing can cause other tests to fail. You should:

- Separate databases/collections per test class or suite.
- Disable parallel execution if sharing a collection.
- Never run `dropCollection`/`remove(new Query())` on a database with real data.
- Seed and clean up **outside the transaction** of the code under test so bugs are not masked.

### 19.3. Testing BSON Mapping

In the test class, you can verify that the Java property `balanceVnd` is actually stored under BSON `balance_vnd`:

~~~java
org.bson.Document raw = mongo.getCollection("money_accounts")
        .find(new org.bson.Document("_id", "A"))
        .first();

assertThat(raw).isNotNull();
assertThat(raw.get("balance_vnd")).isInstanceOf(Number.class);
assertThat(raw.containsKey("balanceVnd")).isFalse();
~~~

This snippet belongs in a scope with `mongo` and AssertJ static imports as above. Verifying mapping is important because `MongoTemplate.updateFirst` uses Java property names while the server receives BSON field names.

### 19.4. What This Test Does Not Yet Prove

The test suite above proves **commit/rollback on the test MongoDB topology**. It does not yet prove:

- Resistance to double-transfer retries after an unknown commit result.
- Performance under thousands of concurrent transactions.
- Absence of double-spending through other services.
- Correctness when using multiple MongoDB factories or PostgreSQL alongside MongoDB.
- Behavior under failover, replication lag, or different write concerns.

Those require dedicated tests and design. Never claim one passing test suffices for production financial transfers.

## 20. Diagnosing Manager and Session Behavior in the Application

When `@Transactional` appears not to work, inspect in order from the application context down to the MongoDB server:

### 20.1. Does the Bean Exist?

~~~java
import org.springframework.context.ApplicationContext;
import org.springframework.data.mongodb.MongoTransactionManager;

Map<String, MongoTransactionManager> managers =
        context.getBeansOfType(MongoTransactionManager.class);
~~~

`context` is an injected `ApplicationContext`; `java.util.Map` must be imported. The result should contain the `mongoTransactionManager` bean registered in section 5.

### 20.2. Is the Service Proxied?

If the caller instantiates `new MoneyTransferService(mongoTemplate)` directly or calls `this.transfer(...)` internally, the transaction interceptor will not fire. The service must be an injected Spring bean and the method invoked through the proxy.

You can enable Spring transaction logging at the appropriate level in a **test environment** to observe begin/commit/rollback. Do not enable system-wide DEBUG logging in production without evaluating sensitive data exposure, overhead, and logging policies.

### 20.3. Is a Transaction Actually Started on MongoDB?

A MongoDB Java Driver `CommandListener` in tests can inspect MongoDB commands and details such as `lsid`, `startTransaction`, `autocommit`, or `commitTransaction`/`abortTransaction` according to actual command structure. Verify behavior with rollback integration tests rather than looking only for a single command field across every version.

Never log full commands containing account numbers, tenants, or sensitive financial data. Mask sensitive fields, limit scope, and remove the listener after tests.

### 20.4. Does the Server Actually Support Transactions?

When running against an unsupported standalone server, you may see a server error such as "transaction numbers are only allowed on a replica set member or mongos" or similar depending on version. That is a **topology error**, not a reason to delete the annotation and assume two updates are protected.

### 20.5. What If Multiple Managers Exist?

Inspect the list of `PlatformTransactionManager` beans, their names, and qualifiers. Use `@Transactional(transactionManager = "mongoTransactionManager")`, especially if the app also has a JDBC/JPA transaction manager.

## 21. Common Errors and Remedies

| Symptom / Mistake | Possible Cause | Remedy |
|---|---|---|
Only added `@Transactional` without declaring a manager | Missing MongoDB manager or wrong manager selected | Register `MongoTransactionManager` with the right `MongoDatabaseFactory` |
MongoDB reports transactions are unsupported | Standalone/topology/version requirements unmet | Use a compatible replica set/sharded cluster |
Rollback test fails, debit persists | Transaction not active or write outside session | Check proxy, manager, factory, and API path |
Method calls `@Transactional` method on `this` | Self-invocation bypasses proxy | Call via Spring bean/proxy or use `TransactionTemplate` |
Caught and swallowed RuntimeException | Interceptor sees normal method return | Rethrow or mark rollback-only properly |
Checked exception did not roll back | Default rollback rule does not cover it | Configure `rollbackFor` appropriately |
`MongoTemplate` and manager use different factories | Mongo operations do not enlist properly | Inject the exact same factory/config explicitly |
Native driver update without session | Write may run outside transaction | Use template/session API properly |
Both JPA and Mongo managers exist, annotation omits manager | Wrong manager chosen | Specify by name/qualifier |
Assumed Mongo transaction covers JDBC | No distributed transaction | Use outbox/saga/reconciliation |
Assumed `@EnableTransactionManagement` creates manager | Annotation only enables proxy infrastructure | Register the manager bean |
Assumed `@Bean` manager wraps all queries automatically | No transaction boundary defined | Use `@Transactional` or `TransactionTemplate` |
Put transaction on `@Async` without clear scope | Thread-bound context does not follow new thread | Establish transaction boundary inside the worker |
Mixed reactive and imperative managers | Different session contexts | Use `ReactiveMongoTransactionManager`/operator for reactive |
Expected `Propagation.NESTED` to act like JDBC savepoints | No nested savepoints as assumed | Redesign boundaries |
Implicitly created collection/index inside transaction | Server may restrict DDL | Provision schema/indexes beforehand |
Credit matched 0 yet method returned normally | Transaction may commit the debit | Throw exception and test rollback |
Retried after unknown commit without transfer ID | May transfer money twice | Implement idempotency and reconciliation |
Held transaction open across HTTP/email calls | Locks/contention, external side effects don't roll back | Keep transactions short, use outbox |
Tested on standalone MongoDB | Does not prove transactions | Run replica set tests |
Asserted exception only without checking balances | Misses already-committed debit | Assert actual data rollback |
Secondary read saw stale data after commit | Replication lag/read preference | Define consistency/read concern contract |
Too many long transactions | Increases contention, duration, transient errors | Narrow transaction boundaries |

## 22. Recommended Implementation Workflow

A technical checklist applicable to Spring Data MongoDB applications:

1. **Identify the invariant.** Does the business logic require single-document or multi-document atomicity? If single-document, prefer a conditional update over a transaction.
2. **Verify MongoDB topology.** Server and driver support transactions, and the app connects to the right replica set/sharded cluster.
3. **Set up dependencies/config.** Proper Spring Boot MongoDB starter, URI, and database factory.
4. **Register `MongoTransactionManager`.** Give the bean a clear name and share the exact `MongoDatabaseFactory` used by business templates/repositories.
5. **Enable transaction interception.** Add `@EnableTransactionManagement` when needed or verify auto-configuration is active.
6. **Place the transaction at the service boundary.** A public `@Transactional(transactionManager = "mongoTransactionManager")` method invoked by callers via a Spring proxy.
7. **Keep all co-committed MongoDB operations in scope.** Never mix out-of-transaction raw driver sessions or separate threads.
8. **Check write results.** `matchedCount=0` on debit/credit must be handled as an appropriate business error.
9. **Do not swallow rollback exceptions.** Specify `rollbackFor` for checked exceptions when required.
10. **Keep scope short.** Never hold a transaction open across HTTP calls, emails, user input, or long background work.
11. **Add idempotency.** Use a transfer ID and unique business key to guard against retries/unknown commit outcomes.
12. **Write replica-set integration tests.** Assert both the happy path and rollback on failure after debit but before credit.
13. **Measure contention and latency.** Test with representative data, concurrency, failover, and write concerns.
14. **Deploy and monitor.** Track abort/retry rates, latency, operational errors, and reconciliation outcomes.

~~~mermaid
flowchart TD
    A["Multi-document business operation"] --> B["MongoDB replica set / sharded cluster"]
    B --> C["MongoDatabaseFactory"]
    C --> D["MongoTransactionManager bean"]
    D --> E["@EnableTransactionManagement + @Transactional"]
    E --> F["MongoTemplate / repository inside session"]
    F --> G{"All steps and invariants met?"}
    G -->|"Yes"| H["Commit"]
    G -->|"No"| I["Rollback"]
    H --> J["Outbox/idempotency/observability"]
    I --> J
    J --> K["Integration tests + production metrics"]
~~~

## 23. Hands-on Exercises

**Exercise 1 — Registering the bean.** Create `MongoTransactionConfig` with `@Bean("mongoTransactionManager")` taking `MongoDatabaseFactory`. Verify the application context has the exact expected MongoDB manager.

**Exercise 2 — Enabling transaction management.** Add `@EnableTransactionManagement` and create a `@Transactional` service method. Invoke via an injected bean; contrast with self-invocation to explain the difference.

**Exercise 3 — Topology test.** Compare standalone MongoDB with a single-node replica set for testing. Record the specific error when transactions are unsupported by the server; do not "fix" it by removing the transaction.

**Exercise 4 — Two-document transfer.** Seed A=100000, B=20000. Transfer 30000 with the transactional service; assert new balances and unchanged total.

**Exercise 5 — Rollback after debit.** Call transfer from A to a nonexistent account. Assert A returns to 100000 after the exception. Temporarily remove the annotation in a test environment to see the difference.

**Exercise 6 — Rollback rules.** Write a method throwing a checked exception after an update. Compare without and with `rollbackFor`; explain why unchecked and checked exceptions differ by default.

**Exercise 7 — Exception swallowing.** Catch an exception inside the service and return normally; observe the risk of committing. Fix it so the interceptor receives the rollback signal and re-test.

**Exercise 8 — TransactionTemplate.** Create a `TransactionTemplate` from `mongoTransactionManager`, move a multi-update block into the callback, and verify rollback when throwing an exception.

**Exercise 9 — Two managers.** Configure both MongoDB and JDBC/JPA transaction managers in a demo test. Specify the bean name with `@Transactional(transactionManager=...)`; verify that picking the wrong manager fails to protect MongoDB.

**Exercise 10 — Session propagation.** In one transactional method, update accounts with both `MongoTemplate` and a repository. Verify they commit/roll back together; then evaluate the risk of a native driver call that omits the session.

**Exercise 11 — Imperative vs reactive.** Explain when to use `MongoTransactionManager` vs `ReactiveMongoTransactionManager`. Build a simple reactive flow with `TransactionalOperator` on a test replica set.

**Exercise 12 — Propagation.** Create a `Propagation.MANDATORY` helper to write ledger entries, calling it outside and inside a transaction. Contrast with `REQUIRED`, avoiding assumptions about `NESTED` savepoints.

**Exercise 13 — Idempotency.** Simulate a transaction that committed while the response was lost. Design a transfer ID with a unique index so replays do not transfer funds twice.

**Exercise 14 — Outbox.** Write a state-transition document and an outbox message in the same transaction; let a separate worker publish with retries and deduplication.

**Exercise 15 — Concurrency benchmark.** Send many concurrent transfers targeting the same source account on a test replica set; collect stats on write conflicts, retries, and latency. Check invariants, not just throughput.

**Exercise 16 — Consistency and concerns.** Using a workload with secondary reads, vary read/write concerns per policy, observe lag, and explain why a transaction commit does not immediately mean every secondary reads the new data.

## 24. Key Takeaways

**Registering `MongoTransactionManager`** bridges Spring's transaction abstraction with MongoDB `ClientSession` and server transactions. For imperative Spring Data MongoDB, the foundational setup is **`@Bean("mongoTransactionManager")` receiving the same `MongoDatabaseFactory`** used by `MongoTemplate`/repositories, paired with **`@EnableTransactionManagement`** or verified active Spring transaction interception.

**`@Transactional` must be invoked through the right Spring proxy, select the right transaction manager, and run on a supported MongoDB topology.** A method performing two updates is not automatically all-or-nothing without the manager/session; when a transaction is active, an appropriate exception aborts all MongoDB operations in scope. To prove it, **test rollback after debit matches while credit fails** on a real replica set, rather than merely asserting an exception was thrown.

Finally, **transactions do not replace idempotency, authorization, unique constraints, write concerns, or handling unknown commit outcomes**. Keep transactions short, avoid external side effects in scope, use an outbox when publishing events, and distinguish imperative `MongoTransactionManager` from reactive `ReactiveMongoTransactionManager`. The goal is not to "enable transactions everywhere," but to place the **right consistency boundary around the right business logic and verify it against real MongoDB**.
