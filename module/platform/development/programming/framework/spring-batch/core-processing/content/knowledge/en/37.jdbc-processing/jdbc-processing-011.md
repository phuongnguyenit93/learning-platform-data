# Skipping Duplicate Keys

In Spring Batch, a duplicate key commonly occurs when the writer inserts a record whose primary key or unique key already exists in the database. In some import flows, encountering the same business key again is an expected scenario: data was already imported in a previous run, the upstream source re-sent a message, or the same record appeared multiple times in an input file.

You can configure a fault-tolerant Step to skip items that trigger `DuplicateKeyException`. However, skipping duplicates is only valid when business rules confirm that a duplicate record can be treated as already processed or quarantined by policy. A unique constraint failure can also signal conflicting data, wrong keys, or mapping bugs. Therefore, keep unique constraints in the database, distinguish valid replays from data conflicts, cap the number of skipped items, and persist sufficient audit records for traceability.

## 1. Where Do Duplicate Keys Occur?

Databases use primary keys and unique constraints to guarantee a value or combination of values does not appear multiple times. For example, an `orders` table has primary key `order_id` and a unique constraint on `external_reference`.

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    external_reference VARCHAR(80) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL
);
~~~

If the writer tries to insert a record whose `order_id` or `external_reference` already exists, the database rejects the statement and the driver returns an error. With Spring JDBC, that error may be translated into `DuplicateKeyException`.

Common scenarios:

- The input file contains the same `order_id` multiple times.
- A Job is relaunched with previously imported data.
- Two concurrent Jobs process the same business key.
- An upstream system re-emits the same event.
- The Job persisted data successfully, but the process stopped before completing subsequent steps.
- Another unique key, such as `external_reference`, collides even when primary keys differ.

A duplicate key is the outcome of a database data constraint. It is not purely a Spring Batch concern and should not be checked solely via Java logic inside a reader or processor.

## 2. Unique Constraints Are the Source of Truth

An unsafe approach is querying first to check if the key exists and then inserting:

~~~text
SELECT to check if order_id already exists?
          |
          +--> Not yet present
                    |
                    v
                  INSERT
~~~

This approach has a race condition. Two transactions can check simultaneously and both see that the key is absent. Both then attempt to insert; only one succeeds, while the other hits a duplicate key error.

Therefore, pre-checks cannot replace unique constraints. They may reduce exception counts in some workloads, yet the database must still enforce uniqueness.

Reliable model:

1. Normalize the business key.
2. The database enforces primary keys or unique constraints.
3. The writer performs the insert.
4. The application handles duplicate errors according to defined policy.
5. Auditing records skipped items or conflicts needing investigation.

If two transactions race on the same key, the unique constraint is the final arbiter. Skip configuration only decides what Spring Batch does after the database rejects the insert.

## 3. Spring's DuplicateKeyException

Spring DAO exception translation provides `DuplicateKeyException` in package `org.springframework.dao`. It is a subclass of `DataIntegrityViolationException`, indicating a write operation violated a uniqueness or key constraint.

With `JdbcTemplate`, `NamedParameterJdbcTemplate`, and Spring JDBC writers, `SQLException`s are usually translated into Spring's exception hierarchy using database metadata and an exception translator.

Example import:

~~~java
import org.springframework.dao.DuplicateKeyException;
~~~

When the writer throws `DuplicateKeyException`, a fault-tolerant Step can be configured to skip that exception.

Not every JDBC driver produces the same exception shape. A custom writer using `Connection` and `PreparedStatement` directly might receive a raw `SQLException` or `BatchUpdateException` not yet translated into `DuplicateKeyException`. In that case, configuring skip on `DuplicateKeyException` will not match. Use Spring JDBC or an appropriate exception translator, and test against the real database and driver.

## 4. Configuring Skip for DuplicateKeyException

In Spring Batch 5, a Step can be configured via the Java DSL as follows:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> orderReader,
        ItemWriter<Order> orderWriter,
        SkipListener<Order, Order> duplicateSkipListener) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(200, transactionManager)
            .reader(orderReader)
            .writer(orderWriter)
            .faultTolerant()
            .skip(DuplicateKeyException.class)
            .skipLimit(100)
            .listener(duplicateSkipListener)
            .build();
}
~~~

Key parts:

- `faultTolerant()` enables fault-tolerance configuration on the Step.
- `skip(DuplicateKeyException.class)` marks this exception class as skippable.
- `skipLimit(100)` caps the total number of allowed skips.
- `listener(...)` registers a listener to record skipped items.

In this example, when `DuplicateKeyException` is classified as skippable and skips remain within the limit, the Step continues processing remaining items. If the skip limit is exceeded, the Step fails.

Set an explicit skip limit based on business rules. Never treat an arbitrary number as safe for every Job; the appropriate threshold depends on volume, source quality, and expected duplicate rates.

## 5. How Skip Differs from Filter and Retry

These three mechanisms handle different cases:

| Mechanism | Meaning | Example |
|---|---|---|
| Filter | Processor returns null because the item needs no write | Dropping canceled orders per business rules |
| Skip | Item triggers an error classified as skippable | Insert hits an acceptable duplicate key |
| Retry | Error is potentially transient and operation can be retried | Deadlock or transient connection failure |

If an item is invalid by business rules and known before writing, the processor can filter it or route it to a reject writer. If an item causes the database to throw a duplicate key error, skip policy can handle that failure.

Do not retry a deterministic duplicate indefinitely. If the key already exists and the operation remains an `INSERT`, retrying usually hits the exact same error. Retry only makes sense when there is a specific transient cause or when retry re-reads state and makes a different decision.

## 6. Is a Duplicate Key Always a Valid Duplicate?

No. `DuplicateKeyException` only indicates a unique constraint was violated; it does not prove two records share the same business contents.

Examples:
- Source record has `order_id = 100` and the database already holds order 100 with identical amount and customer. This may be a harmless replay.
- Source record has `order_id = 100` but a different amount than stored data. This may be a conflict needing investigation.
- `order_id` differs yet `external_reference` collides. This may indicate wrong mapping or upstream reference reuse.
- Duplicate keys caused by a misconfigured generator or sequence. This is a system bug, not a skippable duplicate.

Skip only when business rules confirm that category of duplicate is allowed. If every duplicate is skipped blindly, the Job can finish `COMPLETED` even while source data conflicts with target data.

For systems requiring idempotency, compare the business key and a checksum/version of the existing payload. Same key and same content can be treated as a replay; same key with different content must follow conflict policy.

## 7. Configuring JdbcBatchItemWriter

A simple JDBC writer can insert `Order` items:

~~~java
@Bean
JdbcBatchItemWriter<Order> orderInsertWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    insert into orders
                        (order_id, external_reference, customer_id, amount)
                    values
                        (:id, :externalReference, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
~~~

`JdbcBatchItemWriter` uses Spring JDBC to execute batch updates. When the database rejects an insert due to a unique constraint, exception translation can produce `DuplicateKeyException` for the Step to classify.

Notes:

- Parameter names in SQL must match item properties or the provided parameter mapping.
- The writer's `DataSource` must participate in the Step's transaction if database writes must roll back with the chunk.
- Unique constraints must exist in the database.
- Test batch update behavior with the deployed driver.
- Do not use a non-thread-safe writer instance across multiple threads without appropriate design.

`JdbcBatchItemWriter`'s `assertUpdates` option checks affected row counts in update scenarios that return 0. It is not a switch to suppress duplicate keys and does not replace unique constraint handling.

## 8. Exception Translation and JDBC Driver Errors

When a writer uses `JdbcTemplate` or `NamedParameterJdbcTemplate`, Spring can translate `SQLException` into specific `DataAccessException` subclasses. However, with JDBC batching, drivers may wrap errors inside `BatchUpdateException` or multi-level cause chains.

Some database engines use distinct error codes for duplicates:

| Database | Common error code | Description |
|---|---|---|
| PostgreSQL | `SQLState 23505` | Unique violation |
| MySQL | Vendor error code `1062` | Duplicate entry |
| Oracle | Vendor error code `1` / `ORA-00001` | Unique constraint violated |
| SQL Server | `2601` or `2627` | Duplicate key / unique constraint |

These are illustrative database examples; verify the exact driver version and exception translator in your application. Never rely solely on message text because messages can change across locales or driver versions.

If an exception is not translated into `DuplicateKeyException`, you can:
- Use Spring JDBC to leverage built-in exception translation.
- Configure an appropriate `SQLExceptionTranslator`.
- Wrap recognized duplicate errors into a meaningful custom domain exception.
- Use a custom `SkipPolicy` inspecting the cause chain, `SQLState`, or vendor error code.

Never classify every `SQLException` or `DataIntegrityViolationException` as a duplicate. Foreign key, not-null, check constraints, and other data errors may need to fail the Step.

## 9. Broad vs. Narrow Skip Policies

You can configure skip on a specific exception class:

~~~java
.skip(DuplicateKeyException.class)
~~~

This is straightforward when the writer consistently throws `DuplicateKeyException` for skippable duplicates.

Be cautious with broader classes:

~~~java
.skip(DataIntegrityViolationException.class)
~~~

`DataIntegrityViolationException` encompasses many distinct data violations, such as foreign key, not-null, check, and unique constraints. Skipping the entire hierarchy can mask errors that ought to stop the Job.

Also avoid configuring:

~~~java
.skip(Exception.class)
~~~

without a very explicit policy. That can cause the Job to skip programming bugs, configuration errors, I/O failures, or connection drops.

If `DuplicateKeyException` can originate in multiple phases yet you only want to skip errors from the writer, throw a writer-specific exception or write a policy with enough context to distinguish them. Basic exception-class skip classification applies Step-wide, not just to one SQL statement.

## 10. Skip Limits and Data Quality Thresholds

`skipLimit` caps the allowed number of skips. The count accumulates across skips in the read, process, and write phases of the Step, not only writer duplicates.

Example:
- `skipLimit = 10`.
- The Step encounters 6 duplicates during writes and 3 malformed records during reads.
- Total skips is 9, still within the limit.
- If another skip occurs and pushes the total past the limit, the Step fails.

Set limits from data contracts:
- Small batches may tolerate only a handful of duplicates.
- Large batches may allow a defined ratio or count.
- If duplicates reflect normal upstream replays, measure actual rates.
- If duplicates should be rare, a tight threshold catches bugs early.

`skipLimit` is an absolute count, not a percentage. If the requirement is "at most 0.1% of inputs," compute and check the ratio against read/write counts or use a custom policy/monitoring check. Never set `skipLimit` and assume it represents a percentage.

## 11. Recording Skipped Items with SkipListener

`SkipListener` lets the application observe skipped items and their causes. For duplicates occurring during writes, use `onSkipInWrite`.

Example:

~~~java
@Bean
SkipListener<Order, Order> duplicateSkipListener(
        DuplicateAuditService auditService) {

    return new SkipListener<>() {
        @Override
        public void onSkipInRead(Throwable throwable) {
            // Read skips are not handled in this example.
        }

        @Override
        public void onSkipInProcess(
                Order item, Throwable throwable) {
            // Process skips are not handled in this example.
        }

        @Override
        public void onSkipInWrite(
                Order item, Throwable throwable) {
            auditService.recordDuplicate(
                    item.getId(),
                    item.getExternalReference(),
                    throwable.getClass().getSimpleName());
        }
    };
}
~~~

Audits should capture enough context for traceability:
- `JobInstance` ID and `JobExecution` ID.
- Step name.
- Item's business key.
- Relevant constraint or route if identifiable.
- Exception class and `SQLState`/vendor code when safe.
- Timestamp and rule version.
- Whether the duplicate was accepted or needs investigation.

Do not log full payloads if they contain personal or sensitive data. Use business keys and necessary metadata.

## 12. Auditing Must Align with Transactions

`SkipListener` is a Spring Batch callback invoked during skip processing. If the audit writes to the same database in the same transaction, understand it can roll back if the chunk transaction fails.

If audits write to files, HTTP endpoints, or message brokers, those side effects do not roll back with a JDBC transaction. If the callback is invoked again during a recovery path or process restart, the audit mechanism must be idempotent.

Options include:
- Writing audit rows inside the same transaction when they must commit alongside chunk state.
- Writing outbox records in the transaction for a separate publisher to dispatch externally.
- Using an idempotency key combining `JobInstance` ID, item business key, and skip phase.
- Routing items to a reject/quarantine table with a unique key.
- Accepting independent auditing paired with reconciliation.

Never swallow audit failures silently. If a mandatory audit write fails, decide explicitly whether the Step must fail or use a fallback.

## 13. Behavior When an Error Occurs in the Writer

Writer errors typically happen after the reader and processor have assembled a chunk. When one item in the chunk causes a duplicate key, the batch operation may fail.

In a fault-tolerant Step, Spring Batch must roll back the chunk transaction before processing the skippable item. Depending on the writer, driver, and configuration, the framework may need to pinpoint the failing item in the chunk; this can cause the writer to be re-invoked with smaller sub-groups or individual items.

Consequences:
- The writer must be safe to re-invoke after a rollback.
- Never perform out-of-transaction side effects inside `write` without idempotency.
- A chunk containing many duplicates can incur extra round trips as the framework isolates failing items.
- JDBC drivers report batch failures differently.
- Test against the actual production database and driver.

Never assume a batch insert exception always pinpoints the exact duplicate item by itself. Verify the actual behavior of your writer and driver.

## 14. Duplicates Within the Same Chunk

Suppose a chunk contains three items:

~~~text
Chunk:
  Order 101
  Order 102
  Order 102
~~~

If the database does not yet have Order 102, the first insert can succeed while the second insert violates the unique constraint. When the batch statement fails, the chunk transaction can roll back all inserts in that transaction. Spring Batch then applies skip/recovery to locate the offending item.

If inputs frequently contain internal duplicates, you can eliminate them before the writer:
- Deduplicate by business key in the processor or a staging step.
- Use a staging table with a unique constraint.
- Pick a winning record by timestamp/version.
- Write internal duplicates to a reject output.

Clearly define which record wins if two items share a key yet have different payloads. Using simple object `distinct` may be wrong if `equals`/`hashCode` are not based on the business key.

## 15. Duplicates Already Present from a Previous Run

A common goal is making imports idempotent. A Job may be re-run, or the source may re-send records imported earlier.

Example:
- Initial run imports Order 100 successfully.
- The Job stops before sending an acknowledgment or updating source status.
- The source re-sends Order 100.
- The database unique constraint rejects the second insert.
- The Step skips `DuplicateKeyException` and continues.

This works if a duplicate means "this record was already imported." Still, verify the existing record actually matches the incoming record.

If existing data differs from the source payload, skipping can hide a needed update or a serious conflict. In that case, compare versions/checksums or use an upsert per business rules.

## 16. Upsert or Insert-If-Absent May Fit Better Than Skip

When duplicates are normal, SQL can handle conflicts directly instead of raising an exception for every item.

PostgreSQL example:

~~~sql
INSERT INTO orders (order_id, customer_id, amount)
VALUES (:id, :customerId, :amount)
ON CONFLICT (order_id) DO NOTHING;
~~~

This ignores conflicts only on the specified `order_id`. Another unique constraint can still raise an error.

Other databases have their own syntax:
- MySQL has `INSERT ... ON DUPLICATE KEY UPDATE`.
- Oracle has `MERGE`.
- SQL Server can use conditional `INSERT` or an upsert strategy tuned for isolation and locking.

Check the semantics of each syntax. For instance, "do nothing" and "update existing" are two different business policies.

Advantages of upsert:
- Avoids using exceptions as control flow for routine duplicates.
- Handles conflicts directly in the database.
- Reduces rollback/recovery overhead when duplicates are frequent.
- Explicitly specifies which columns get updated.

Skipping exceptions remains useful when duplicates are rare, per-item auditing is required, or the writer cannot use conflict-aware SQL. Do not use `INSERT IGNORE` broadly if it silently downgrades other data errors into warnings or drops invalid rows unintentionally.

## 17. Existence Pre-Checks Do Not Solve Race Conditions

You can check beforehand:

~~~sql
SELECT 1
FROM orders
WHERE order_id = :id;
~~~

If no row exists, the application inserts. This can sometimes reduce duplicate errors when sources contain many existing records, but it does not guarantee the insert will succeed because another transaction can insert the same key right after the check.

If using pre-checks:
- Still enforce unique constraints.
- Still handle `DuplicateKeyException` at the insert step.
- Avoid issuing one query per item at high volumes.
- Consider preloading keys per page or using staging where appropriate.
- Measure performance before and after.

Never treat pre-checks as a synchronization mechanism across concurrent Jobs.

## 18. Distinguishing Duplicates from Other Data Errors

`DataIntegrityViolationException` covers many distinct violations. Examples:

| Error | Example | Should it be skipped as a duplicate? |
|---|---|---|
| Unique constraint | `order_id` already exists | Only when business rules allow |
| Primary key | Duplicate ID | Could be a replay or an ID generator bug |
| Foreign key | `customer_id` does not exist | Usually needs dedicated handling |
| Not-null | Null `customer_id` | Usually a data error |
| Check constraint | Negative amount when disallowed | Usually a business error |
| Length/type violation | String too long or invalid type | Must reject or fail per policy |

If you skip all `DataIntegrityViolationException`s, the Job can swallow corrupt records without distinguishing valid duplicates from unpersistable data.

Use a narrow exception class or a custom exception raised only for confirmed unique conflicts. If the driver surfaces only a generic `SQLException`, the policy must deliberately inspect `SQLState`/vendor codes and the cause chain.

## 19. Custom SkipPolicy When Identifying Specific Constraints

Some systems have multiple unique constraints where only certain constraints are skippable. For example, an `external_reference` duplicate is a valid replay, whereas an `order_id` collision with a different payload is a conflict.

In that case, use a custom `SkipPolicy` instead of simple class-based skipping. The policy should:
- Walk the cause chain for `SQLException` or `DataAccessException`.
- Match exact `SQLState` or vendor error codes.
- Identify the constraint if the driver exposes that metadata.
- Return skippable only for business-permitted conflicts.
- Respect the skip limit or a dedicated threshold.
- Re-throw/reject all other violation types.

Constraint names inside exception messages are not a stable API across all databases. If you must identify by constraint name, use a verified driver/database mechanism or translate the error in the writer into a custom domain exception.

Never write a policy matching purely on message substrings like `"duplicate"` or `"unique"`. Messages vary by locale and driver.

## 20. Handling Same-Key Different-Data Conflicts

A record with a duplicate key may carry a different payload than the existing row. This situation demands an explicit rule.

Example:

~~~text
Database:
  order_id = 100
  amount = 120.00
  version = 1

Incoming:
  order_id = 100
  amount = 150.00
  version = 2
~~~

Options include:
- **Identical replay:** compare checksums or business fields; record as already existing and skip.
- **Valid newer update:** use upsert or versioned update with optimistic locking.
- **Conflict:** route to quarantine for human or secondary workflow resolution.
- **Bad source data:** fail the Step or reject the record per contract.

`DuplicateKeyException` does not carry enough information to pick among these policies. You may need to query the existing row after the transaction rolls back, or use conflict-aware SQL returning inserted/existing status.

Never automatically overwrite all columns on duplicate. That can overwrite newer data with stale replayed messages.

## 21. Retry, Deadlocks, and Duplicate Keys

Duplicate keys are usually deterministic errors for the same `INSERT` and an already-existing key. Retrying the exact same operation normally does not make it succeed.

Deadlocks or serialization failures can be transient errors handled by retry if the transaction can re-execute safely.

General classification example:

| Exception/scenario | Typical handling |
|---|---|
| `DuplicateKeyException` confirmed as valid replay | Skip or insert-if-absent |
| Duplicate key with conflicting payload | Fail or quarantine |
| `DeadlockLoserDataAccessException` | Bounded retry |
| Transient connection error | Retry per policy and timeout |
| Not-null/foreign key violation | Reject or fail per business rules |
| SQL syntax/mapping error | Fail and fix config/code |

Do not configure overlapping retry and skip carelessly for the same exception. Clearly define which exceptions retry, which skip, and which must fail. When an operation has out-of-transaction side effects, retries require idempotency.

## 22. Skipping Exceptions Does Not Replace Idempotency

Unique constraints stop the database from storing two rows with the same key, yet idempotency is broader. A Job might:
- Write the database successfully but fail to send a message.
- Write a file successfully before Job metadata commits.
- Update the database and then stop before sending an acknowledgment.
- Retry a request to an external service that already processed the previous call.

Skipping duplicate keys solves only one kind of database conflict. It does not make other side effects idempotent.

Techniques include:
- Stable idempotency keys derived from source event IDs.
- Unique constraints on idempotency keys.
- Outbox tables for message publishing.
- Inbox/deduplication tables for consumers.
- Upserts with version checks.
- Reconciliation jobs to detect missing or mismatched records.

Idempotency identifiers must stay stable across launches and restarts; never generate a fresh UUID on every retry.

## 23. SkipListener and Monitoring Skipped Data

When skipping duplicates, record enough information to explain why items were not inserted. Without auditing, a Job can complete without anyone knowing how many records were dropped.

An operational summary might report:

~~~text
Job: importOrders
JobInstance: 52
Step: importOrdersStep

Read count:       10,000
Write count:       9,920
Write skip count:     80
Status: COMPLETED
~~~

Numbers are meaningful only when reconciled by skip category. If the Step also skips during reads/processes, total skip counts will exceed duplicate write skips. Use listeners or custom metrics to separate reasons and phases.

You can track:
- Total accepted duplicates.
- Duplicates with matching payloads.
- Keys with conflicting payloads.
- Unrecognized unique constraint errors.
- Items routed to quarantine.

If duplicate rates spike suddenly, it can signal upstream replays, duplicate Job launches, or buggy business key generation.

## 24. Restarts and Duplicate Keys

A restart can encounter items already written successfully before the process failed in another step. Depending on transactions and checkpoints, items may be re-read or re-written.

Unique constraints and idempotent writes are valuable safeguards, yet distinguish carefully:
- Items committed in earlier chunks: checkpoints usually already passed those items.
- Items in rolled-back chunks: the database transaction rolled back inserts in that chunk.
- Out-of-transaction side effects: may still persist despite chunk rollback.
- Process crashes across systems: state may need reconciliation.

If the writer inserts a duplicate and the Step skips it, verify the existing item represents the same logical event. Do not treat all post-restart duplicates as harmless; output files, messages, and audits might still be written twice.

Reader/writer names, queries, identifying `JobParameters`, and input ordering must also remain stable across restarts. If a new `JobInstance` is launched for the same business data, unique keys can still block double inserts, provided skip/upsert policies are explicitly defined.

## 25. Duplicates Across Concurrent Jobs

Two `JobInstance`s can process the same source or overlapping business keys concurrently. Pre-checks before inserting will not stop the race. Unique constraints pick one winning transaction while the other receives a duplicate error.

Consider:
- Are two Jobs allowed to process the same tenant/batch concurrently?
- Is there an input claim or locking mechanism?
- Is the unique key global or scoped per tenant?
- Should the losing Job skip, re-read and retry, or fail?
- Can audits identify which Job created the record first?
- Are non-database outputs generated twice?

If concurrent Jobs running on the same scope are unintended, use appropriate identifying `JobParameters`, locks/claims, or orchestration to prevent duplicate launches. Skipping duplicates is a last line of defense, not a substitute for Job coordination.

## 26. Testing Duplicate Keys with a Real Database

Mock-based tests can verify the Step wiring invokes listeners, but they do not prove the JDBC driver's exception translator returns the expected exception class. Write integration tests against a production-like database and driver.

Scenarios to verify:

| Scenario | What to verify |
|---|---|
| Insert new key | Record is inserted |
| Insert existing primary key | Duplicate is classified properly |
| Collide on another unique business key | Policy distinguishes constraints if required |
| Duplicate within same chunk | Only the skippable item is skipped |
| Duplicate from a prior Job | Job proceeds per idempotency policy |
| Same key, different payload | Conflict is detected, not silently dropped |
| Exceed skip limit | Step status is `FAILED` |
| Foreign key/not-null error | Not mistaken for a valid duplicate |
| Writer using JDBC batch | Driver exception is translated and failing item isolated |
| `SkipListener` | Audits the exact item and phase |
| Audit failure | Transaction/Step behavior follows policy |
| Two transactions racing on same key | Unique constraint protects data |
| Restart after chunk commit | No double writes or skipped items |
| Deadlock retry | Only transient errors are retried |

A basic integration test:
1. Create a table with a primary key and unique constraint.
2. Pre-insert one record representing an existing duplicate.
3. Launch the Job with input containing a new key, an existing key, and another new key.
4. Verify new keys are written, the duplicate is skipped, and subsequent items still process.
5. Verify `SkipListener` receives the right business key.
6. Check `StepExecution` skip count and write count.
7. Test exceeding `skipLimit` and confirm the Step fails.
8. Test another integrity violation and confirm it is not accidentally skipped.

## 27. Common Pitfalls

**Skipping all DataIntegrityViolationExceptions.** Foreign key, not-null, or check constraint errors can get hidden alongside duplicates.

**Using pre-checks instead of unique constraints.** Two concurrent Jobs can still insert the same key.

**Retrying duplicates unconditionally.** The same `INSERT` keeps failing while the key exists.

**Assuming same key means same payload.** Existing records can conflict with incoming source data.

**Omitting an explicit skipLimit.** A batch may drop far too many items without hitting a business threshold.

**Forgetting skip counts span multiple phases.** `skipLimit` does not count only writer errors if the Step also skips during reads/processes.

**Skipping exception translation verification.** Drivers may throw `SQLException` or `BatchUpdateException` instead of `DuplicateKeyException`.

**Matching message text to detect duplicates.** Messages depend on driver, locale, and version.

**Not auditing skipped items.** Makes duplicate rates and dropped records hard to investigate.

**Auditing with non-idempotent side effects.** Retries/recovery can produce duplicate audit entries.

**Using skip to mask ID generator bugs.** Duplicates may signal severe configuration errors.

**Assuming filesystems and messages roll back with the database.** External side effects can persist after rollback.

**Not testing against real JDBC batching.** Mocks cannot accurately simulate driver behavior when one item in a batch violates a constraint.

## 28. Process for Implementing Duplicate Key Skipping

When you need to skip duplicate keys in Spring Batch, follow this sequence:

1. Identify which primary keys and unique constraints can collide.
2. Distinguish valid replays from same-key conflicts with differing payloads.
3. Keep unique constraints in the database as the final safeguard.
4. Use Spring JDBC or an exception translator to reliably surface `DuplicateKeyException`.
5. Configure `faultTolerant()`, `skip(DuplicateKeyException.class)`, and an explicit `skipLimit`.
6. Use narrow exception classes; avoid skipping all `DataIntegrityViolationException`s.
7. If specific constraints must be distinguished, use a custom exception or `SkipPolicy` based on verified `SQLState`/vendor codes.
8. Register a `SkipListener` to audit skipped items.
9. Define transaction semantics for audits and external side effects.
10. Choose skip for rare duplicates, or upsert/insert-if-absent when duplicates are routine.
11. Use retry for transient errors like deadlocks; never blindly retry deterministic duplicates.
12. Keep idempotency keys and routing rules stable across retries and restarts.
13. Test in-chunk duplicates, prior-run duplicates, concurrent inserts, and skip limits on a real database.
14. Monitor skip counts, duplicate rates, payload conflicts, and other integrity errors in production.

Skipping duplicate keys lets Spring Batch continue when an item violates a unique constraint deemed safe to ignore. The database remains the guarantor of uniqueness; the skip policy decides which errors are tolerated; `SkipListener` provides traceability for dropped items. By separating valid replays from data conflicts, setting explicit limits, and testing against the real driver and transactions, Jobs can handle re-delivered data while still catching genuine failures.

