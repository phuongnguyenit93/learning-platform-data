# Imperative vs. Reactive Models in Spring Transaction Management

## Learning objectives

After this lesson, you will be able to: (1) distinguish imperative and reactive execution flows; (2) explain how Spring attaches transaction state to an execution flow; (3) choose between `PlatformTransactionManager` and `ReactiveTransactionManager`; (4) apply `@Transactional` or programmatic APIs in the right place; and (5) recognize common bugs when mixing JDBC/JPA with R2DBC/Reactor.

## 1. What problem do both models solve?

Transactions group data operations into a single unit of work: either all valid changes commit, or uncommitted changes roll back upon failure. For example, transferring 20 units from account A to B must pair two commands: debiting A and crediting B. If crediting B fails, debiting A must be undone. Actual guarantees (atomicity, isolation, durability, etc.) also depend on the database, driver, isolation level, and configuration.

The difference between *imperative* and *reactive* lies primarily in **how work is expressed, when it executes, and how transaction context is propagated**. Both can use Spring's `@Transactional`, yet they do not share the same resource management mechanism.

- **Imperative:** statements are written sequentially; method calls normally execute work immediately and return a result or throw an exception. With JDBC/JPA, database interaction is typically blocking.
- **Reactive:** builds a `Publisher` chain (usually Reactor `Mono<T>` or `Flux<T>`). The chain normally executes only when subscribed to; completion, errors, and cancellation are conveyed as signals. With R2DBC, database I/O can be non-blocking.

"Reactive" does not automatically mean "faster" or "the database always supports transactions." It is advantageous when the entire I/O stack and libraries support non-blocking processing, particularly under high concurrency.

## 2. Direct comparison

| Aspect | Imperative | Reactive |
|---|---|---|
| Typical service return types | `void`, `T`, `List<T>` | `Mono<T>`, `Mono<Void>`, `Flux<T>` |
| When DB work runs | When reaching DB statements during the method call | When the DB publisher is subscribed to (for typical cold publishers) |
| Transaction manager | `PlatformTransactionManager` | `ReactiveTransactionManager` |
| How transaction state is held | Primarily `ThreadLocal` on the executing thread | Reactor `Context` attached to the subscription |
| Common data technologies | JDBC, JdbcTemplate, JPA/Hibernate | R2DBC, Spring `DatabaseClient`, supported reactive drivers |
| Convenient programmatic API | `TransactionTemplate` | `TransactionalOperator` |
| Success/failure signals | Return / throw exception | `onComplete` / `onError` (and `cancel`) |
| Context propagation | Stays on the transaction-bound thread; switching to a new thread does not carry it automatically | Stays in the same reactive pipeline and Reactor Context, even when valid operators switch threads |
| Key boundary | Call through Spring proxy and method body | Call through proxy, returned publisher, and pipeline subscription |

**Key point:** choose the transaction manager based on **data access technology and execution model**, not merely because a controller uses Spring MVC or WebFlux. A WebFlux endpoint calling a JDBC service is still using blocking technology; changing the return signature to `Mono` does not turn JDBC into R2DBC.

## 3. Imperative transaction lifecycle

When a Spring bean invokes a proxied method supporting `@Transactional`:

```text
Caller
  → Spring transactional proxy
  → PlatformTransactionManager acquires/creates transaction
  → runs service body; JDBC/JPA operations join the transaction
  → normal return: commit
  → rollback-triggering exception thrown: roll back
  → caller receives result or exception
```

In typical JDBC configurations, Spring binds the connection and transaction state to the current thread. `JdbcTemplate` or Spring-managed repositories obtain the matching connection to participate together. `@Transactional` defaults to `REQUIRED` propagation: it joins a compatible existing transaction, or creates a new one if none exists.

### Java 17+ example: balance transfer with JdbcTemplate

Assume a SQL table (`DECIMAL` type and table creation syntax must match the target DB):

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(19, 2) NOT NULL
);

INSERT INTO accounts(id, balance)
VALUES (1, 100.00), (2, 50.00);
```

File `JdbcTransferService.java` (a Spring bean; requires an application context, JDBC driver, `DataSource`, and transaction manager, **not a standalone runnable Java program**):

```java
import java.math.BigDecimal;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class JdbcTransferService {
    private final JdbcTemplate jdbc;

    public JdbcTransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional("jdbcTx")
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Sender missing or insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalStateException("Recipient missing");
        }
    }
}
```

**Explanation:** calling `transfer(1, 2, new BigDecimal("20.00"))` on the Spring proxy executes both UPDATE statements inside the same transaction. On success, balances become 80.00 and 70.00; if the recipient does not exist or the second statement errors, the unchecked exception causes the transaction to roll back the prior debit statement as well. These results assume a properly configured transaction manager sharing the same `DataSource` and no concurrent modifications. Checking affected row counts catches business failures before commit.

## 4. Reactive transaction lifecycle

With `ReactiveTransactionManager`, Spring cannot use `ThreadLocal` as the "identity" for the whole unit of work because signals can cross multiple threads. Instead, transaction state and connection are attached to the **subscription's Reactor Context**. Conceptual steps:

```text
Caller → Spring transactional proxy → receives wrapped Mono/Flux
                                        (SQL not yet executed)
Subscriber subscribes
  → ReactiveTransactionManager opens/joins transaction
  → places state/connection into Reactor Context
  → DB publishers execute sequentially per operators
  → onComplete: commit
  → onError: roll back (per rollback rules)
  → cancel: roll back for reactive transactions
```

The context travels along the **reactive chain**. Using standard Reactor operators, even switching schedulers, does not drop transaction context; however, creating a detached subscription or calling a context-unaware API can run operations outside the intended transaction.

### Java 17+ example: same business operation with R2DBC

File `R2dbcTransferService.java` (Spring bean; requires Reactor, `spring-r2dbc`, R2DBC driver/`ConnectionFactory`, and the corresponding `ReactiveTransactionManager`; **not a standalone runnable Java program**):

```java
import java.math.BigDecimal;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import reactor.core.publisher.Mono;

@Service
public class R2dbcTransferService {
    private final DatabaseClient db;

    public R2dbcTransferService(DatabaseClient db) {
        this.db = db;
    }

    @Transactional("r2dbcTx")
    public Mono<Void> transfer(long fromId, long toId, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            return Mono.error(new IllegalArgumentException("Invalid transfer"));
        }

        Mono<Long> debit = db.sql(
                "UPDATE accounts SET balance = balance - :amount " +
                "WHERE id = :id AND balance >= :amount")
            .bind("amount", amount)
            .bind("id", fromId)
            .fetch()
            .rowsUpdated();

        Mono<Long> credit = db.sql(
                "UPDATE accounts SET balance = balance + :amount WHERE id = :id")
            .bind("amount", amount)
            .bind("id", toId)
            .fetch()
            .rowsUpdated();

        return debit.flatMap(changed -> {
            if (changed != 1L) {
                return Mono.<Void>error(
                    new IllegalStateException("Sender missing or insufficient funds"));
            }
            return credit.flatMap(updated -> {
                if (updated != 1L) {
                    return Mono.<Void>error(
                        new IllegalStateException("Recipient missing"));
                }
                return Mono.<Void>empty();
            });
        });
    }
}
```

- `db.sql(...).fetch().rowsUpdated()` creates a publisher representing the SQL operation; the two UPDATEs do not run merely because the service returned `Mono<Void>`.
- `flatMap` ensures the credit runs only after the debit confirms exactly one updated row. Returning `Mono.error(...)` propagates the error inside the same pipeline so Spring rolls back; returning `Mono.empty()` upon success lets the pipeline complete and commit.
- If nothing subscribes, no work occurs. In a WebFlux application, the framework typically subscribes when writing the response; **never call `subscribe()` manually inside the service**.
- Expected balances match the JDBC example given the same inputs and no concurrent changes. This example shows no stdout because it runs within Spring/database rather than having a `main` method.

### Configuring the right transaction managers

In an application with both JDBC and R2DBC, both managers can be clearly distinguished (file `TxConfig.java`; requires `DataSource`, `ConnectionFactory` beans, and corresponding dependencies):

```java
import javax.sql.DataSource;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;

@Configuration
public class TxConfig {
    @Bean("jdbcTx")
    PlatformTransactionManager jdbcTx(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean("r2dbcTx")
    ReactiveTransactionManager r2dbcTx(ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
```

The names `jdbcTx` and `r2dbcTx` match `@Transactional("...")` on the two services. If an application has only one compatible manager, `@Transactional` can usually omit the name. Never assume the two managers automatically share a connection or belong to a single transaction: JDBC and R2DBC are two independent management infrastructures.

## 5. Declarative and programmatic: same goal, different APIs

**Declarative**: `@Transactional` describes the transaction boundary on a Spring bean method. Spring AOP/proxies handle begin/commit/rollback; ideal when the entire business operation fits neatly in one service method.

**Programmatic**: used when specifying exactly which pipeline/code block belongs inside a transaction, or setting transaction attributes dynamically. Recommended Spring APIs:

| Flow | API | Form |
|---|---|---|
| Imperative | `TransactionTemplate` with `PlatformTransactionManager` | `template.execute(status -> { ... })` |
| Reactive | `TransactionalOperator` with `ReactiveTransactionManager` | `pipeline.as(operator::transactional)` or `operator.transactional(pipeline)` |

Reactive example, assuming `debit(...)` and `credit(...)` are methods returning `Mono<Void>` and using the appropriate R2DBC client:

```java
// Snippet inside a Spring component that already has reactiveTx,
// debit(...), and credit(...); not a standalone file.
TransactionalOperator operator = TransactionalOperator.create(reactiveTx);

Mono<Void> work = debit(fromId, amount)
    .then(credit(toId, amount));

return operator.transactional(work);
```

Only operations **chained within `work`** belong to this transaction. If another publisher executes via a separate `subscribe()`, that publisher gets its own subscription/context. You cannot assume it acts as a third step inside the same transaction.

**Operator order matters.** For example, `work.onErrorResume(ex -> Mono.empty())` placed *before* `operator.transactional(...)` turns an error signal into normal completion, so updates before the error may commit. To roll back, let errors propagate past the transaction boundary, or explicitly mark rollback-only via the appropriate API.

## 6. Shared transaction rule principles

- By default `@Transactional` uses `Propagation.REQUIRED`, the data system's default isolation, and rolls back on `RuntimeException`/`Error`; checked exceptions do not roll back by default (configurable via `rollbackFor` or application-wide default policy).
- `readOnly = true` is a hint to the infrastructure, not an absolute protection preventing all writes; level of support varies by driver and database.
- Propagation, isolation, timeout, and savepoints **do not have identical support** across all managers/drivers. In particular, do not assume `NESTED` is always available with R2DBC just because JDBC supports savepoints.
- A database transaction does not automatically encompass emails, HTTP calls, or external brokers. When synchronizing side effects, consider outbox or eventual consistency designs rather than assuming multiple resources form a single atomic transaction.

## 7. Pitfalls to watch out for

### 7.1. Annotating a method with `@Transactional` and calling it internally in the same class

In default proxy mode, `this.innerMethod()` bypasses the proxy, so `@Transactional` on `innerMethod` is not applied by the interceptor for that call. Invoke from another bean through the Spring proxy, or place the transaction boundary on the externally invoked method.

### 7.2. Wrapping JDBC/JPA in `Mono.just(...)` and assuming it is reactive

```java
// Wrong regarding lazy execution: jdbc.update(...) already executed before creating the Mono.
Mono<Integer> changed = Mono.just(jdbc.update("DELETE FROM temp_rows"));
```

`Mono.defer(...)` can defer executing the code, but it does not turn blocking JDBC into non-blocking I/O nor make JDBC join an R2DBC transaction. Use the matching manager and driver; if JDBC is unavoidable, dedicate threads/schedulers for blocking workloads and treat the JDBC transaction as its own separate boundary.

### 7.3. Calling `subscribe()` or `block()` manually inside a reactive service

Manual `subscribe()` creates an execution flow detached from the returned publisher, risking side effects running after commit/rollback or outside the intended Reactor Context. Calling `block()` on an event-loop thread can also error out and stall the thread serving concurrent requests. In reactive services, **return** the composed `Mono/Flux` chain; leave subscribing to the outermost layer.

### 7.4. Swallowing errors before the transaction boundary

If `onErrorResume` converts an error into a successful outcome *inside* the transactional pipeline, the manager sees `onComplete` and commits. In imperative code, catching an exception without rethrowing carries the same risk. Distinguish "business error handled" from "DB changes must roll back."

### 7.5. Ignoring reactive stream cancellation

A subscriber can `cancel` (for instance in certain `take`, `next`, or `timeout` scenarios). Since Spring Framework 5.3, cancellation of a reactive transaction triggers a **rollback**. When a transaction must commit all processing of a `Flux`, design the pipeline so the publisher is consumed through terminal completion, avoiding operators that cancel early unintentionally.

### 7.6. Mixing resources, contexts, or transaction managers

In a reactive transaction, data operations must use a driver/API that participates in the same Reactor Context, such as Spring `DatabaseClient` with `R2dbcTransactionManager`. Opening a raw R2DBC connection manually does not guarantee using the transaction-bound connection. Conversely, `PlatformTransactionManager` transactions rely on thread-bound state and do not automatically follow new threads. Neither manager type coordinates with the other into a distributed transaction merely by placing `@Transactional` on both.

## 8. Integration verification and model selection

With initial data `(id=1, balance=100.00)` and `(id=2, balance=50.00)`, verify at minimum:

1. **Success:** transfer 20.00, wait for the service to finish, and verify with a fresh query that both accounts hold 80.00 and 70.00 respectively.
2. **Failure/rollback:** reset data; transfer to a non-existent `toId`. Assert an exception (imperative) or `onError` (reactive), then re-query balances to confirm they remain 100.00 and 50.00.
3. **Lazy execution:** in reactive code, merely creating the `Mono` without subscribing produces no DB change. When testing reactive flows, you can use `StepVerifier.create(service.transfer(...)).verifyComplete()` or `verifyError(...)` with the `reactor-test` dependency.
4. **Boundary/context:** when multiple managers or services are involved, test a failure after the first operation to confirm both operations truly belong to the **same** transaction.

| Situation | Recommended direction |
|---|---|
| Application uses JPA/Hibernate or JDBC with synchronous business logic | Imperative + `PlatformTransactionManager` |
| Full chain request → service → database uses non-blocking R2DBC for high concurrency | Reactive + `ReactiveTransactionManager` |
| Hybrid JDBC and R2DBC application | Separate boundaries, name managers explicitly, test rollback on each side; never expect one local transaction to span both |
| Need fine-grained control over a small section of a flow | `TransactionTemplate` (imperative) or `TransactionalOperator` (reactive) |

**Self-check:** (a) why is `ThreadLocal` insufficient for reactive pipelines? (b) what happens if a `Mono` is returned without a subscriber? (c) why can two `UPDATE` statements inside separate `subscribe()` calls fail to share a transaction? (d) does calling `this.save()` with `@Transactional` on `save` get intercepted by a Spring proxy?

## References

- Spring Framework — Declarative transaction implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Programmatic transaction management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — Data access with R2DBC: https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html
- Spring Blog — Reactive Transactions with Spring: https://spring.io/blog/2019/05/16/reactive-transactions-with-spring/
