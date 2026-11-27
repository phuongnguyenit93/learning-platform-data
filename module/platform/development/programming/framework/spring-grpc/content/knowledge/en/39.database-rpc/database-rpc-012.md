# Testing Rollback and Retries

## 1. What should be tested in database RPCs?

In **SPRING_GRPC**, a unary RPC may write to multiple tables within one business operation: creating an order, updating inventory, saving an idempotency record, and writing an outbox event. If one step fails, the transaction must roll back all changes belonging to that unit of work. When a recoverable error such as a deadlock or serialization conflict occurs, the system may retry the business operation in a new transaction.

Two properties must be proven independently:

- **Rollback:** a failed attempt leaves no partial database changes behind.
- **Retry:** the subsequent attempt reads fresh state and re-runs the entire use case in a separate transaction.

Testing only that the RPC returns an error is insufficient. The server might return an error even though some rows committed; or a retry might run inside the same transaction already marked rollback-only. You need to observe the database after each scenario and verify execution counts, transaction boundaries, side effects, and gRPC statuses.

This lesson focuses on:

- Inducing controlled failures after data has been written.
- Verifying rollback using an independent transaction/connection.
- Testing through gRPC to verify statuses and observer lifecycle.
- Ensuring each retry opens a new transaction.
- Classifying transient vs. permanent errors.
- Testing idempotency when a response is lost after commit.
- Using Testcontainers, concurrency controls, and fault injection to minimize flaky tests.

## 2. Identify transaction boundaries before writing tests

A Spring use case is typically placed in a @Transactional application service. The gRPC adapter calls the service through a Spring bean proxy; the proxy begins a transaction before running the method and commits/rolls back before returning the result to the adapter.

Success flow:

1. Adapter receives and validates the request.
2. Application service begins the transaction.
3. Service writes business data and outbox/idempotency records if needed.
4. Method returns the result.
5. Spring transaction interceptor commits.
6. Adapter receives the post-commit result and emits onNext/onCompleted.

Failure flow:

1. Service has executed one or more write statements.
2. A runtime or database error occurs.
3. Transaction rolls back.
4. Exception escapes the proxy back to the adapter.
5. Adapter maps the exception to a gRPC status and emits onError.

For errors that only surface at flush/commit, the target method may already have reached return, yet the proxy still throws an exception while finishing the transaction. Therefore, the adapter must only send a success response after the transactional proxy call returns normally.

## 3. Do not use a test-level transaction to simulate the gRPC server's transaction

A common mistake is annotating a test method with @Transactional and then calling the RPC over a channel. The server usually handles the request on another thread and opens its own transaction. The test's transaction does not wrap the server's transaction.

This causes misleading behavior:

- Fixtures created inside an uncommitted test transaction may not be visible to the server thread.
- The test transaction may hold snapshots or locks that alter concurrency behavior.
- The test framework rolls back the test transaction at the end, while the server transaction may have committed independently.
- Assertion reads inside the same test transaction may not see new data due to isolation/snapshots.

To test server transactions:

- Create fixtures in a committed transaction before invoking the RPC.
- Do not wrap the test method in an outer transaction when the goal is to verify server commit/rollback.
- After the RPC finishes, read the database using an independent transaction or connection.
- Use unique IDs per test and clean up intentionally.
- For tests requiring multiple concurrent transactions, coordinate them with barriers/latches rather than relying on timing.

You can use @Transactional for pure application-service unit tests if you understand proxies and test transactions, but integration tests over gRPC must prove the server's real transaction behavior.

## 4. Inducing controlled failures after writing data

Rollback tests need to trigger a failure at a deterministic point. One way is injecting a test-only collaborator that throws an exception after the first write step:

```java
@Service
@RequiredArgsConstructor
public class PlaceOrderService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;
    private final FailureProbe failureProbe;

    @Transactional
    public OrderResult place(PlaceOrderCommand command) {
        Order order = orders.save(Order.create(command));

        failureProbe.afterOrderSaved();

        outbox.save(OutboxRecord.orderCreated(order));
        return OrderResult.from(order);
    }
}
```

In production, FailureProbe has a no-op implementation; tests substitute an implementation that throws exceptions according to the scenario. You can use a test profile or bean override, depending on the Spring version.

If you want to test real database errors, trigger a unique constraint violation or a controlled flush failure. Calling repository.flush() in the test path can force the ORM to send SQL early, though commit can still raise other errors. Tests should clearly state whether they are testing flush-time or commit-time exceptions.

Never use Thread.sleep to "hope" a failure happens at the right moment. Fault injection must be deterministic and repeatable.

## 5. Verifying rollback via database state

Suppose the application service writes the order and then fails before writing the outbox. After calling the RPC and receiving the error status, check via an independent connection:

```java
@Test
void rollsBackOrderWhenOutboxStepFails() {
    String orderId = uniqueOrderId();

    StatusRuntimeException error = assertThrows(
        StatusRuntimeException.class,
        () -> blockingStub.placeOrder(requestFor(orderId))
    );

    assertEquals(
        Status.Code.INTERNAL,
        Status.fromThrowable(error).getCode()
    );

    Integer orderCount = jdbcTemplate.queryForObject(
        "select count(*) from orders where id = ?",
        Integer.class,
        orderId
    );

    Integer outboxCount = jdbcTemplate.queryForObject(
        "select count(*) from outbox_event where aggregate_id = ?",
        Integer.class,
        orderId
    );

    assertEquals(0, orderCount);
    assertEquals(0, outboxCount);
}
```

This test confirms that neither the business row nor the outbox row is left partially persisted. If the failure occurs after both have been inserted but before commit, both must likewise roll back.

If the exception occurs after commit, rollback is no longer possible. Keep "error before commit" tests strictly separate from "response lost after commit" tests; the two cases have different expected states.

## 6. Testing rollback-only and checked exceptions

Spring rolls back by default on unchecked exceptions (RuntimeException) and Error. Checked exceptions do not roll back automatically under the default configuration unless declared in rollbackFor or the transaction is marked rollback-only.

Tests should cover the actual configured policy:

```java
@Transactional(rollbackFor = ImportRejectedException.class)
public void importRecord(ImportCommand command)
        throws ImportRejectedException {
    repository.save(toEntity(command));
    validateExternalRule(command);
}
```

Verify these scenarios:

- RuntimeException after write: transaction rolls back.
- Checked exception listed in rollbackFor: transaction rolls back.
- Checked exception not in rollback rules: behaves per configured policy, may commit.
- Exception caught and swallowed inside the transactional method: transaction may commit if not marked rollback-only.
- Transaction marked rollback-only: completing the call may throw UnexpectedRollbackException at commit.

Do not assert only the exception type. Always inspect row state after the transaction ends. An exception caught at the adapter layer does not determine whether the transaction rolled back; the transaction interceptor acts before the exception leaves the proxy.

## 7. Testing gRPC statuses and observer lifecycle

Integration tests should invoke the server over a gRPC channel to verify both application behavior and transport mapping.

For unary RPCs:

- Success: exactly one response message, followed by onCompleted.
- Failure: no success response emitted; client receives the appropriate status.
- Never call onNext/onCompleted after onError.
- Proxy commit failures are caught by the adapter and mapped properly.
- Status descriptions contain no SQL, stack traces, or secrets.

Common mappings:

| Cause | Commonly Used Status |
| --- | --- |
| Malformed request | INVALID_ARGUMENT |
| Missing resource | NOT_FOUND |
| Business precondition unsatisfied | FAILED_PRECONDITION |
| Optimistic lock conflict | ABORTED |
| Database temporarily unavailable after retries | UNAVAILABLE |
| RPC deadline expired | DEADLINE_EXCEEDED |
| Unexpected internal error | INTERNAL |

Do not use INTERNAL for every failure when the contract classifies errors more specifically. Tests must verify the status code on the client, not just check the internal exception thrown inside the application service.

## 8. Retries must run in a new transaction

When a transaction rolls back due to a deadlock, serialization failure, or optimistic lock conflict, the persistence context and previously read data may no longer be valid. A retry must re-read state and re-run the entire use case in a new transaction.

A clean structure separates the retry coordinator from the transactional attempt bean:

```java
@Service
@RequiredArgsConstructor
public class TransferAttemptService {
    private final AccountRepository accounts;

    @Transactional
    public TransferResult execute(TransferCommand command) {
        Account account = accounts.findById(command.accountId())
            .orElseThrow(AccountNotFoundException::new);

        account.debit(command.amount());
        return TransferResult.from(account);
    }
}
```

```java
@Service
@RequiredArgsConstructor
public class TransferRetryService {
    private final TransferAttemptService attemptService;
    private final RetryPolicy retryPolicy;

    public TransferResult execute(TransferCommand command) {
        for (int attempt = 1; ; attempt++) {
            try {
                return attemptService.execute(command);
            } catch (TransientDataAccessException ex) {
                if (!retryPolicy.mayRetry(attempt, ex)) {
                    throw ex;
                }
                retryPolicy.pauseBeforeNextAttempt(attempt);
            }
        }
    }
}
```

The two classes are separate Spring beans. Each time the coordinator calls attemptService.execute() through the proxy, a new transaction opens; if an exception escapes the transactional method, that attempt's transaction rolls back before the coordinator decides to retry.

Avoid self-invocation where a retry method calls another @Transactional method on the same object in standard proxy mode. Internal calls can bypass the transaction proxy.

## 9. Choosing which errors may be retried

Retries are appropriate only for recoverable errors with a clear policy:

| Error | Auto-Retry? | Notes |
| --- | --- | --- |
| Deadlock victim | Usually yes | Re-run the entire transaction |
| Serialization failure | Usually yes | Re-read snapshot in a new transaction |
| Optimistic lock conflict | Depends on contract | Re-read and recompute; may return ABORTED to client |
| Connection failure before transaction begins | Possible | Resolve outcome before executing command |
| Validation failure | No | Fix the request |
| NOT_FOUND | Usually no | Resource must be created or ID fixed |
| FAILED_PRECONDITION | Do not blind-retry | Business state must change |
| Permission denied | No | Permissions must be granted |
| Database schema/programming error | No | Fix operational/code bug |

Classify by SQLState/vendor code and the active driver/database exception translation. Do not retry every DataAccessException or RuntimeException; constraint, syntax, and mapping errors will repeat endlessly without recovering.

Optimistic locking has two valid policies: the server retries the entire use case automatically if the business logic can recompute; or it returns ABORTED so the client re-reads and decides. Never auto-retry when a request carries expected_version and the contract requires rejecting updates against an outdated version.

## 10. Bounding retries by attempts, backoff, and deadline

Retries must never run indefinitely or cause a retry storm. Policies should define:

- Explicit maximum attempts.
- Exponential backoff with jitter.
- Overall deadline for the entire RPC/use case.
- Query/transaction timeout smaller than the remaining deadline.
- Retry only classified exceptions.
- Metrics for attempt count, success-after-retry, and exhausted retries.

Backoff pseudocode example:

```text
delay = min(max_delay, base_delay × 2^(attempt - 1))
wait  = delay + random_jitter
```

Before each attempt, check the remaining deadline. If insufficient time remains for another attempt, stop and return an appropriate status. Never grant a full fresh timeout on each retry iteration.

Never sleep on a gRPC event-loop thread. For synchronous retries, execute on an appropriate worker/executor with bounded concurrency; for async systems, use scheduler/reactive retries with cancellation support.

## 11. Testing retries with deterministic fault injection

Use a probe that counts attempts and throws a transient error on the initial tries:

```java
@Component
public class RetryFaultProbe {
    private final AtomicInteger failuresRemaining =
        new AtomicInteger(0);

    public void failNext(int count) {
        failuresRemaining.set(count);
    }

    public void beforeCommit() {
        if (failuresRemaining.getAndUpdate(
                value -> Math.max(0, value - 1)) > 0) {
            throw new TransientDataAccessResourceException(
                "Injected transient failure"
            );
        }
    }
}
```

Place the probe after writes have run inside the transactional attempt. If the first attempt throws, the transaction must roll back; the next attempt invokes the service via the proxy and starts a new transaction.

Tests can configure the probe to fail once, invoke the retry coordinator, and assert:

- Attempt count equals 2.
- The first transaction rolled back.
- The second transaction committed.
- Only one final business outcome exists.
- No leftover rows from the failed attempt.
- Each attempt had an active transaction with distinct transaction identity if the test harness can observe it.

Reset the probe between tests. Never share static mutable state across tests running in parallel.

## 12. Testing commit success with a lost response

This is a key scenario for verifying retries do not duplicate side effects:

1. Server processes the command and commits to the database.
2. A test fault hook cuts off the response before the client receives it.
3. Client retries with the same idempotency key.
4. Server finds the committed idempotency record.
5. Server replays the stored result.
6. The database contains only one business record and one outbox event.

This test differs from a rollback test: the data must remain after the first attempt because the commit succeeded. The retry must not execute the side effect a second time.

Without idempotency, you cannot prove a retry after timeout is safe for a non-idempotent command. Use a transport test/fault proxy or an adapter hook after the application service returns; never simulate this by throwing an exception inside the transaction if the goal is to simulate a post-commit failure.

## 13. Concurrency testing and real databases

H2 is useful for fast tests, yet can differ from production databases in locking, isolation, deadlocks, SQLStates, constraint timing, and timeouts. For critical transaction/retry tests, prefer Testcontainers running the same engine/version as production.

Concurrency tests should:

1. Create committed initial data.
2. Open two independent transactions.
3. Use CountDownLatch/CyclicBarrier so both read the same version or contend on the same row.
4. Let one transaction commit first.
5. Force the remaining transaction to hit a conflict/deadlock.
6. Verify the loser rolls back or retries per policy.
7. Read the final state through an independent connection.

Do not rely on Thread.sleep to create races. Barriers/latches and fault probes produce repeatable execution schedules.

Testcontainers also verifies native SQL, lock timeouts, and exception translation against the actual database/driver.

## 14. Testing outbox and external side effects

If a use case updates domain data and creates an outbox event, rollback tests must confirm both roll back together. Retry tests must confirm a single command ultimately produces one business effect and one logical event.

Scenarios to verify:

- Pre-commit error: neither business row nor outbox row exists.
- Successful commit: both business row and outbox row exist.
- Dispatcher publishes then crashes before marking: event may resend with the same event ID.
- Consumer receives duplicate: inbox/unique constraint prevents a second side effect.
- Command retry with the same idempotency key: no new outbox event is created.
- Worker retry after lease expiry: handled idempotently.

Do not test "broker receives exactly one message" as the sole outbox condition. Delivery is normally at-least-once; what must be guaranteed is that consumers do not apply duplicate side effects.

## 15. Minimum test suite for a database RPC command

| Group | Required Test | Key Assertion |
| --- | --- | --- |
| Happy path | Command succeeds | Rows commit, response matches |
| Rollback | Error after first write | No partial rows left |
| Commit failure | Constraint/flush failure | No success response emitted |
| Retry | Transient failure then success | New attempt uses new transaction |
| Retry exhausted | All attempts fail | No side effects; accurate status |
| Permanent failure | Validation/permission error | No retry occurs |
| Lost response | Commit then sever response | Retry with same key replays |
| Duplicate concurrency | Two requests with same key | One logical side effect |
| Optimistic conflict | Two transactions on same version | Loser rolls back or ABORTED per policy |
| Outbox | Domain + outbox | Commit or roll back together |
| Deadline | Budget exhausted during retry | No new attempt starts past deadline |

The test suite should separate unit tests for classifiers/backoff, integration tests for transactions and gRPC, and fault-injection/concurrency tests for failure windows. Avoid writing excessive tests that repeat the same assertion without proving a new boundary.

## 16. Review checklist

- Tests invoke the application service through a Spring proxy or real gRPC server.
- Fixtures are committed before the server reads them.
- Never use a test-level transaction to simulate transactions on server threads.
- Failures are injected after a deterministic write.
- Rollback is verified via an independent transaction/connection.
- Flush/commit failures are tested, not only errors before SQL runs.
- Checked exceptions and rollbackFor are tested per policy.
- Adapter emits responses only after commit.
- Retry coordinator calls a separate transactional bean for each attempt.
- Permanent errors or unclassified exceptions are never retried.
- Each attempt re-reads data in a new transaction.
- Backoff, max attempts, and total deadline are verified.
- Commands with side effects use idempotency keys.
- Lost-response tests prove replay does not duplicate effects.
- Outbox and consumer deduplication are tested when external events exist.
- Concurrency tests use barriers/latches, not arbitrary timing.
- Test databases match production in engine, driver, and isolation.

In **SPRING_GRPC**, rollback testing must prove the database retains no partial changes after failure; retry testing must prove each subsequent attempt runs in a new transaction and re-reads state. Use deterministic fault injection, query through an independent connection, and invoke through a gRPC server to verify real statuses. For commands with side effects, include lost-response tests with idempotency to ensure a successful commit followed by a lost response never executes a second effect.
