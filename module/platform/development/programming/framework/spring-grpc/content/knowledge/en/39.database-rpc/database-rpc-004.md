# Optimistic Locking and ABORTED

## 1. Why does optimistic locking need to be tied to gRPC status?

In **SPRING_GRPC**, multiple unary RPCs can read and update the same record concurrently. For example, two requests both read an account balance, both calculate a new balance, and both write it back. Without a mechanism to detect that the data changed between read and write, the later write can overwrite the earlier request's result (lost update).

**Optimistic locking** detects this situation using a version number or token. On each successful update, the version is incremented. When writing, the database accepts the update only if the current version still equals the version the transaction read. If another transaction has already updated the row first, the update statement no longer matches and the persistence layer reports a conflict.

In gRPC, concurrency control conflicts are typically represented with the **ABORTED** status. This status indicates that the operation was aborted due to a conflict in a read-modify-write sequence; the caller may need to re-read the latest state and retry the entire operation.

This lesson focuses on the version check mechanism, JPA `@Version` in Spring, when conflicts surface at flush/commit, mapping exceptions to gRPC `ABORTED`, distinguishing statuses, safe retries in a new transaction, idempotency, and concurrency testing.

## 2. How optimistic locking works

Suppose the account table has the following columns:

| id | balance | version |
| --- | ---: | ---: |
| acct-17 | 1000 | 4 |

Two transactions T1 and T2 both read this row and both receive `version = 4`.

- T1 calculates a balance of 900 and updates with the condition `version = 4`.
- T1 succeeds, writes `balance = 900`, and increments version to 5.
- T2 still holds version 4; when it updates, the condition `version = 4` no longer matches.
- The database updates 0 rows; the ORM detects stale state and raises an optimistic locking conflict.

Conceptual SQL that an ORM might emit:

```sql
UPDATE account
SET balance = ?, version = version + 1
WHERE id = ? AND version = ?
```

If the update count is 0, the record was modified or no longer exists matching the update condition. The ORM typically translates a stale version case into an optimistic locking exception.

The key point is that the database performs the version comparison directly inside the UPDATE statement. This avoids the race condition between a separate SELECT checking the version and a subsequent UPDATE.

## 3. Declaring a version with JPA @Version

With Spring Data JPA, declare a version field on the entity:

```java
@Entity
@Table(name = "account")
public class Account {
    @Id
    private String id;

    private long balance;

    @Version
    private long version;

    public void debit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (balance < amount) {
            throw new InsufficientFundsException();
        }
        balance -= amount;
    }

    public long getBalance() {
        return balance;
    }

    public long getVersion() {
        return version;
    }
}
```

The JPA provider manages reading and incrementing the version when the entity is updated. The application should not manually set the version to force an update past a conflict.

Integer types or other version types supported by the provider can be used. Avoid reusing the version field for separate business logic. Version is a persistence-layer concurrency token, not an order sequence number or user-visible timestamp.

If using JDBC or manual SQL, include the version in the UPDATE condition yourself and check the number of affected rows. `@Version` does not automatically protect SQL statements that bypass the entity lifecycle.

## 4. Transaction boundaries and when conflicts appear

Optimistic locking only makes sense within a transaction that reads state, computes changes, and writes that state back. The use case should live in a Spring application service:

```java
@Service
@RequiredArgsConstructor
public class AccountApplicationService {
    private final AccountRepository accounts;

    @Transactional
    public AccountResult debit(String accountId, long amount) {
        Account account = accounts.findById(accountId)
            .orElseThrow(AccountNotFoundException::new);

        account.debit(amount);

        return new AccountResult(
            account.getId(),
            account.getBalance(),
            account.getVersion()
        );
    }
}
```

When the transactional method returns a result through the Spring proxy, the transaction interceptor commits before returning control to the gRPC adapter. If the version conflict is only detected during flush/commit, the exception may appear when the proxy completes the transaction, even though code inside the method already reached the return statement.

Therefore:

- The adapter only sends `onNext()` after the proxy call to the application service returns successfully.
- If the commit throws an optimistic lock exception, the adapter receives the exception and sends an error status.
- Never send a success response before commit and only discover the conflict afterward.
- Never catch the exception inside the transactional method and return a normal result when rollback is required.

You can call `flush()` inside the transaction to detect conflicts earlier, but the transaction must still commit successfully before the adapter reports success to the client. Flush does not equal commit.

## 5. Mapping optimistic locking conflicts to ABORTED

JPA/Spring can surface conflicts via exceptions such as:

- `jakarta.persistence.OptimisticLockException`.
- `org.springframework.orm.ObjectOptimisticLockingFailureException`.
- `org.springframework.dao.OptimisticLockingFailureException`.

The exact exception type depends on the JPA provider, Spring version, and where the failure occurs (flush/commit). In the adapter layer or a centralized exception mapper, recognize the optimistic locking exception family and map it to `Status.ABORTED`.

Illustrative example:

```java
try {
    AccountResult result =
        accountApplicationService.debit(
            request.getAccountId(),
            request.getAmount()
        );

    DebitReply reply = DebitReply.newBuilder()
        .setAccountId(request.getAccountId())
        .setBalance(result.balance())
        .setVersion(result.version())
        .build();

    observer.onNext(reply);
    observer.onCompleted();

} catch (OptimisticLockingFailureException ex) {
    observer.onError(
        Status.ABORTED
            .withDescription("Concurrent update; reload and retry")
            .asRuntimeException()
    );
}
```

The example catches the standardized Spring exception. If your code also catches JPA exceptions directly, check the class hierarchy to avoid multi-catch conflicts between an exception and its subclass on the active classpath.

Do not expose entity names, SQL, internal versions, or stack traces in the status description. Server logs should preserve the original exception and correlation ID for investigation.

## 6. Distinguishing ABORTED, FAILED_PRECONDITION, and UNAVAILABLE

gRPC statuses express different root causes and suggest different caller actions:

| Status | Typical Meaning | Caller Action |
| --- | --- | --- |
| `ABORTED` | Concurrency conflict in an operation sequence, e.g., optimistic lock | Re-read state and retry the entire read-modify-write |
| `FAILED_PRECONDITION` | Current system/business state does not satisfy preconditions to execute | Wait for state change or fix state before retrying |
| `UNAVAILABLE` | Service temporarily unavailable or connection failure | Can retry the call according to policy and backoff |
| `NOT_FOUND` | Resource does not exist | Do not retry as a conflict |
| `INVALID_ARGUMENT` | Invalid request | Fix the request before resending |

Examples:

- Two requests concurrently update entity version 4: the losing request receives `ABORTED`.
- An order is CANCELLED and therefore cannot be shipped: typically `FAILED_PRECONDITION`.
- The server temporarily refuses connections: can be `UNAVAILABLE`.

Do not use `ABORTED` for every database error. Proper classification enables clients to pick the right recovery strategy.

## 7. Retries must re-run the entire use case

After an optimistic locking conflict, the data the transaction read is stale. Retrying only the UPDATE statement with the previously computed values does not resolve the conflict; it can write based on old state and violate invariants.

Proper retry flow at the application/client level:

1. Catch `ABORTED`.
2. Start a new transaction or re-invoke the RPC so the server opens a new transaction.
3. Re-read the entity and its current version.
4. Recompute the business decision from the fresh data.
5. Execute the update with the new version.
6. If conflicts persist, retry up to a limit and then return an error to the caller.

For example, two requests both debit 80 from a balance of 100. The first request commits a balance of 20. The second request receives `ABORTED`; when it re-reads, it sees a balance of 20 and must return an insufficient funds business error, never repeating the update based on the old balance of 100.

Retries must include:

- A maximum number of attempts.
- Backoff with jitter to prevent conflicting requests from colliding repeatedly at the same instant.
- A time budget that stays within the RPC deadline.
- Exception classification; only retry recoverable conflicts.
- Load limits so retries do not amplify database overload.

Do not retry unboundedly on both client and server. If multiple layers retry simultaneously, database attempt counts can multiply.

## 8. Idempotency and side effects on retry

A request may commit successfully, yet the response is lost. The client observes a timeout or dropped connection and does not know whether the operation took effect. This differs from an optimistic locking conflict, though it often appears in the same retry infrastructure.

For commands with side effects such as creating an order, capturing payment, or transferring funds, use an idempotency key:

- The client sends a stable key for a single business intent.
- The database saves the key and result in the same transaction as the business change.
- A unique constraint protects when two requests with the same key arrive concurrently.
- Retrying with the same key and same payload returns the stored result.
- Same key with a different payload is rejected.

Optimistic locking protects against updating an entity from an old version; idempotency protects against executing the same intent repeatedly. The two mechanisms solve different problems and may need to be used together.

If the transaction needs to emit an event, write an outbox record in the same transaction. Do not send an event or call an external service before commit expecting an optimistic lock failure to roll back that external side effect.

## 9. Optimistic locking with a client-supplied version

Some APIs include a version in the request so the client indicates the operation is only valid on the version it read:

```proto
message UpdateProfileRequest {
  string profile_id = 1;
  string display_name = 2;
  int64 expected_version = 3;
}

message UpdateProfileReply {
  string profile_id = 1;
  int64 version = 2;
}
```

The server can compare `expected_version` with the current version and return `ABORTED` if they do not match. However, checking via a SELECT followed by a separate UPDATE still has a race condition: another transaction could update after the check step.

Therefore, an atomic version check at the database is still needed, such as JPA `@Version`, a version-conditional UPDATE statement, or appropriate locking. The `expected_version` field in the API is a client-supplied precondition; the persistence version is the atomic protection mechanism at the database. They can be mapped to each other, but one does not replace the other.

Do not let the client choose the new version or overwrite the internal version. The server returns the current version after a successful commit for the client to use on its next update.

## 10. Cases optimistic locking does not protect automatically

`@Version` typically protects entity updates through the ORM when the provider includes the version in the UPDATE statement. However, watch out for:

- Bulk JPQL updates and native SQL may bypass the version check or fail to increment the version unless written explicitly.
- Multi-table or multi-aggregate cross-row invariants may require additional locks or constraints.
- Unmanaged entities or improperly merged detached entities can cause subtle issues.
- An operation that reads from the DB and writes to an external system is not protected by the database version.
- A transaction reading multiple entities requiring broader consistency may need appropriate isolation/locking.

If using a manual update statement:

```sql
UPDATE account
SET balance = :newBalance,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
```

Check the update count. If it is 0, distinguish between a missing resource and a version conflict if the API needs to differentiate them; an extra query in a new transaction may be needed. Do not assume native updates automatically throw the same exception type as JPA dirty checking.

## 11. Controlled concurrency testing

A unit test calling the method twice sequentially does not prove optimistic locking works. You need two transactions genuinely competing on the same version.

Scenario:

1. Create an account with balance 100 and version 1.
2. T1 reads the entity at version 1.
3. T2 reads the same entity at version 1.
4. T1 updates and commits; version becomes 2.
5. T2 attempts to commit the entity read at version 1.
6. Verify T2 receives an optimistic lock exception.
7. Over gRPC, verify T2's caller receives `ABORTED`.
8. Retry the entire use case; verify the application reads the new balance/version and applies business rules correctly.

Use two independent transactions/threads and a barrier/latch to control read/write timing. Testcontainers or a database matching production helps verify real locking and exception translation; H2 may not reproduce every difference.

Key assertions:

- Only one update based on the same old version commits successfully.
- Version increments properly after commit.
- The losing request does not cause a lost update for the winning request.
- The adapter does not emit a success response when a commit conflict occurs.
- Status is mapped to `ABORTED`.
- Retry opens a new transaction and re-reads state.
- Idempotency prevents duplicate side effects when a commit result is lost to the client.

## 12. Observing conflicts and protecting the system

Monitor optimistic locking conflicts by use case/RPC:

- Conflict count and conflict rate over total updates.
- Entity/aggregate types causing conflicts.
- Average retry count and retry success rate.
- Requests hitting deadlines during retries.
- Lock waits, transaction duration, and database load.
- `ABORTED` rate by method.

Do not put entity IDs, user IDs, or arbitrary request values into metric labels because cardinality can grow unboundedly. Use bounded labels such as RPC method, operation type, and outcome; use correlation IDs in logs to investigate specific requests.

A high `ABORTED` rate can indicate heavy contention, overly long transactions, overly wide aggregates, or many requests updating the same row. Improvements include shortening transactions, splitting aggregates appropriately, using atomic updates, partitioning workloads, or considering pessimistic locking for hotspots. Do not increase retry counts to mask contention, as doing so can worsen database load.

## 13. Review checklist

- Entities requiring concurrency control have a version field managed by the persistence layer.
- All relevant write paths perform version checks; bulk/native SQL has been audited.
- Read-modify-write use cases live inside short transactions.
- Flush/commit conflicts propagate to the adapter or exception mapper.
- Responses are emitted only after the transaction commits successfully.
- Optimistic locking conflicts are mapped to `ABORTED`.
- `FAILED_PRECONDITION` and `UNAVAILABLE` are used for other causes.
- Retries re-read data and re-execute the entire use case in a new transaction.
- Retries are bounded, use backoff/jitter, and respect deadlines.
- Commands with side effects use idempotency keys when needed.
- External events are published via outbox after commit.
- Concurrency integration tests exist with two independent transactions.
- Metrics track conflicts/retries without creating high-cardinality labels.

In **SPRING_GRPC**, optimistic locking uses a version to prevent a transaction from overwriting data already updated by another request. When the version no longer matches, the server should roll back and return `ABORTED`, signaling the caller to re-read and retry the entire operation. Place transactions in the application service, emit responses only after commit, and combine bounded retries with idempotency to maintain business correctness under concurrent load.
