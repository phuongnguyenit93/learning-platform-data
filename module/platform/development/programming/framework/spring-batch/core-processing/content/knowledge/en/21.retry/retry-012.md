# Distinguishing retry from skip

In Spring Batch, **retry** and **skip** are both error-handling mechanisms in chunk-oriented steps, yet they solve two different problems. Retry asks to re-attempt an operation because the error may only be temporary. Skip accepts bypassing an unprocessable item and continuing with other items under a defined policy.

Properly distinguishing the two mechanisms prevents two common pitfalls: skipping infrastructure failures and producing an incomplete batch, or endlessly retrying a permanent data error so the job cannot advance. In practice, a step may use both retry and skip: retry transient failures first, and skip only if business rules allow discarding the item once retries are exhausted.

## 1. What is retry?

Retry means re-attempting an operation after encountering an exception identified as potentially recoverable. For example, a writer updating a database hits a deadlock. The database rolls back one transaction to resolve contention; if the application retries after a pause, the operation may succeed.

Errors commonly considered for retry:

- Transient deadlocks or lock acquisition failures.
- Brief interruptions in database connectivity.
- Timeouts when calling external services, provided duplicate requests can be prevented or identified.
- Certain transient errors from object storage, message brokers, or networks.

Retry does not remove an item from the processing flow. Its goal is to complete the operation for the failing item or chunk itself.

```text
Item processed
      |
      v
Operation raises transient exception
      |
      v
Retry per policy
      |
      +---- success -------> continue / commit
      |
      +---- still failing -> retry within limit
```

If the operation succeeds on a later attempt, the item proceeds normally. Having been retried does not mean the item was skipped.

## 2. What is skip?

Skip means allowing a specific item or read/write error to be bypassed when the exception belongs to a category permitted by policy. The step continues processing remaining items instead of halting immediately on that item.

For instance, an order import file has one line with an invalid date format. If business rules permit isolating the faulty line and recording it for later correction, the application can configure skip for that line-parsing exception.

```text
Read item A ----> processed and written successfully
Read item B ----> data error, skipped
Read item C ----> processed and written successfully
Read item D ----> processed and written successfully
```

Skip does not try to make a faulty item succeed. It accepts that the item does not continue through the pipeline in the current run. Therefore, skip must tie to a business decision: can that record be set aside, who will reprocess it, and what audit trail must be stored?

## 3. Quick comparison of retry and skip

| Criterion | Retry | Skip |
|---|---|---|
| Goal | Re-attempt the operation to process the same item/chunk successfully. | Bypass an allowed faulty item/error to move on to other items. |
| When appropriate | Transient errors likely to resolve after a pause. | Item-specific errors that business rules permit discarding or deferring. |
| Result if next attempt succeeds | Item is processed normally. | Not applicable; skip is not a retry mechanism. |
| Result if still failing | Continue retrying within limits; then apply next handling branch. | Item counts as skipped if exception is allowed and within limit. |
| Limit | Retry limit / retry policy. | Skip limit / skip policy. |
| Observability | Needs retry-attempt logs/metrics or appropriate listeners. | Has skip counters in `StepExecution` and `SkipListener` callbacks. |
| Risk when misconfigured | Retrying permanent errors, causing slowdowns or duplicate requests. | Bypassing systemic outages, leaving missing data while the job finishes. |

A helpful rule of thumb: **retry asks "should we try again?", while skip asks "if it cannot be processed, may we bypass it?"**

## 4. Retry policy and skip policy are two independent decisions

Spring Batch lets you configure both retry and skip on the same step. The two policies classify exceptions for separate purposes. An exception may be retryable, skippable, both, or neither.

| Retry policy | Skip policy | Typical behavior |
|---|---|---|
| Retry | Do not skip | Retries within limit; if still failing, the step fails. |
| Do not retry | Skip | Discards the item if skip limit still allows. |
| Retry | Skip | Retries first; if error persists after retries, item may be skipped if policy permits. |
| Do not retry | Do not skip | Exception fails the step immediately per step error mechanics. |

Examples:

- `DeadlockLoserDataAccessException`: can be retried because deadlocks are usually transient. If retries run out and errors persist, the application can let the step fail; skip only if business rules genuinely allow dropping that operation.
- `InvalidOrderException`: normally pointless to retry because input data does not fix itself. Can be skipped if faulty orders are independent and recorded for later remediation.
- `FileNotFoundException`: usually should neither be retried nor skipped in a job requiring that file; fail the job so the input is fixed.

Do not share one exception list across both retry and skip merely because both relate to errors. Decide based on root cause and business impact.

## 5. Retry limit and skip limit

Retry limit bounds how many times operations are retried under the retry policy. Skip limit bounds the total number of errors skipped in the step.

Example configuration:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skip(FlatFileParseException.class)
        .skipLimit(50)
        .build();
```

In this example:

- Deadlocks are retried under the retry policy.
- Invalid orders or unparseable file lines can be skipped.
- Total skips across read, process, and write phases must not exceed 50.
- If a deadlock persists after retries and is not in the skip policy, the step fails.

`retryLimit` and `skipLimit` do not replace each other. A retry attempt is not automatically counted as a skip. A skipped item does not imply the framework retried it beforehand.

When you need exact total invocation counts, check the semantics of `retryLimit` in your Spring Batch/Spring Retry version and add attempt logs/metrics. Never infer attempt counts from `skipCount`.

## 6. What happens when retries run out?

When an exception is accepted by the retry policy yet the operation still fails after the limit, retrying stops. Spring Batch evaluates remaining fault-tolerance rules.

Normally there are two possibilities:

1. The exception is also allowed by the skip policy and the skip limit is not exceeded: the item can be skipped, listeners are invoked to record it, and the step continues.
2. The exception is not skippable or the skip limit is exceeded: the exception propagates out, the current transaction rolls back per the transaction manager, and the step fails.

Diagram:

```text
Exception occurs
       |
       v
In retry policy?
   |             |
  No            Yes
   |             |
   |       Retry attempts left?
   |          |       |
   |         Yes      No
   |          |       |
   |        Retry    +----------------+
   |                                 |
   +---------------+-----------------+
                   v
            Is it skippable?
               |          |
              Yes         No
               |          |
         Skip limit left? |
           |       |      |
          Yes     No      |
           |       |      |
          Skip   Step FAILED
```

If an exception is outside the retry policy yet inside the skip policy, the framework can skip without retrying first. Retry exhaustion is not a prerequisite for skipping.

## 7. Example choosing retry for transient errors

Suppose a writer inserts orders into a database and occasionally hits deadlocks because concurrent transactions update related rows. This error may vanish once the other transaction completes.

```java
return new StepBuilder("writeOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
```

Here, no skip is configured for deadlocks. If retry succeeds, the chunk commits. If retries run out and deadlocks persist, the step fails so operators investigate lock contention, update ordering, or indexes.

This is typically the safe choice when errors indicate database issues and dropping some orders would corrupt batch output.

## 8. Example choosing skip for data errors

Suppose a file contains many independent orders. A few lines have non-existent customer IDs. Business rules allow bypassing those lines and storing details for later reconciliation.

```java
return new StepBuilder("validateOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(UnknownCustomerException.class)
        .skipLimit(100)
        .listener(orderSkipListener)
        .build();
```

No retry is configured for `UnknownCustomerException` because repeating the same validation against the same data normally produces the same result. The listener records the order ID and reason so the business team can add customer data or reprocess later.

If a missing-customer error was actually caused by a lookup service being temporarily unavailable, the exception should represent a separate infrastructure failure and may be retried. Do not reuse the same exception for "customer not found" and "service unresponsive."

## 9. Using both retry and skip for the same exception

Sometimes business rules allow skipping an item if a transient error persists after several attempts. For instance, independent items are sent to a partner system; if the partner times out repeatedly, the application can record the item in a deferred queue rather than stopping the entire batch.

```java
return new StepBuilder("publishOrdersStep", jobRepository)
        .<Order, PartnerRequest>chunk(50, transactionManager)
        .reader(orderReader)
        .processor(requestProcessor)
        .writer(partnerWriter)
        .faultTolerant()
        .retry(ResourceAccessException.class)
        .retryLimit(3)
        .skip(ResourceAccessException.class)
        .skipLimit(25)
        .listener(partnerSkipListener)
        .build();
```

In this configuration, timeout exceptions are retried first. If still failing, the skip policy can allow bypassing the item within bounds. This approach is appropriate only when:

- Each request is independent, without relying on ordering or outcomes of other requests.
- A mechanism exists to persist unsent requests for later reprocessing.
- A stable idempotency key is used because timeouts do not tell whether the partner already processed the request.
- Continuing the batch when some requests remain unpublished is an accepted business requirement.

If the partner API is a mandatory part of the transaction, or the database/partner is experiencing a widespread outage, let the step fail rather than mass-skipping items.

## 10. Distinguishing skip from filter

Skip is often confused with filter because both keep an item from reaching the writer. However, they carry different meanings.

| Mechanism | How it works | Related counters |
|---|---|---|
| Filter | `ItemProcessor` returns `null` | `filterCount` |
| Skip | Exception allowed by the skip policy | `readSkipCount`, `processSkipCount`, `writeSkipCount`, `skipCount` |

Filter example:

```java
@Bean
ItemProcessor<OrderInput, Order> processor() {
    return input -> {
        if (input.status() == OrderStatus.CANCELLED) {
            return null;
        }
        return mapToOrder(input);
    };
}
```

Cancelled orders are excluded under normal business rules, not via an exception. Therefore, they count as filtered.

Skip example:

```java
@Bean
ItemProcessor<OrderInput, Order> processor() {
    return input -> {
        if (input.customerId() == null) {
            throw new InvalidOrderException("customerId is required");
        }
        return mapToOrder(input);
    };
}
```

If `InvalidOrderException` is configured as skippable, the item is recorded as skipped. This is invalid data raising an exception.

Do not return `null` to hide data errors or exceptions. Filters should represent deliberate business exclusions; skips should represent errors permitted by policy to be bypassed.

## 11. Retry and skip across read, process, and write

Exceptions can happen in any phase of chunk processing. Retry/skip design must account for the specific phase.

| Phase | Error examples | Retry may fit when | Skip may fit when |
|---|---|---|---|
| Read | Database connection error while reading | Connection glitch is transient and reader can safely re-read. | One record/file line has bad formatting and can be isolated. |
| Process | Error calling an enrichment service | Service timeout is transient and reads can repeat. | Item violates deterministic data rules, no point retrying. |
| Write | Deadlock or database timeout | Transaction can roll back and rewrite safely. | One item fails uniquely, can be quarantined and skipped per business rules. |

With writers in particular, one call usually receives an entire chunk. If one item breaks the writer, the framework must isolate the failing item to apply skip. Exact behavior depends on the writer, exception, and how Spring Batch handles chunks. Do not assume every write exception can isolate and skip a single item cleanly.

## 12. Transactions and rollback on retry or skip

In a chunk-oriented step, each chunk typically runs inside a transaction. If an operation fails, the current transaction may roll back before the framework retries or applies the skip policy.

Example:

```text
BEGIN chunk transaction
  read A, B, C
  process A, B, C
  writer writes A, B, C
  writer fails on B
ROLLBACK chunk

Framework applies retry/skip policy
  -> retries as configured
  -> or identifies skippable item
  -> rewrites remaining items and commits when valid
```

Database rollback only undoes changes belonging to that transaction. Sent emails, HTTP requests processed by partners, or messages published to brokers are not automatically recalled. Therefore, retrying a non-database operation can produce duplicate side effects.

When retrying external calls, consider idempotency keys, outboxes, status lookups before resending, or compensating actions. For database writers, unique constraints and upserts help make rewrites safe.

## 13. Retry and skip do not guarantee exactly-once

Retries can cause operations to run multiple times. Skips can cause an item to go unprocessed in the current batch. Neither mechanism by itself guarantees end-to-end exactly-once semantics for the job.

For example, a partner API accepted a payment request, yet the client timed out before receiving the response. Retrying with a new request can create two payments. Skipping immediately after a timeout can bypass a payment whose actual outcome remains unknown.

Typical protective measures needed:

- Stable idempotency keys tied to batch ID and item ID.
- Unique constraints on business keys in the database.
- Rejected-item tables or outboxes to record unprocessed requests.
- Status reconciliation workflows against external systems.
- Checkpoints and immutable data sources so restarts are reproducible.

Retry/skip are control-flow decisions; idempotency and reconciliation are what control duplicate side effects.

## 14. Monitoring retry and skip

`StepExecution` provides skip counters:

```java
long readSkip = stepExecution.getReadSkipCount();
long processSkip = stepExecution.getProcessSkipCount();
long writeSkip = stepExecution.getWriteSkipCount();
long totalSkip = stepExecution.getSkipCount();
```

These counters report how many items/errors were skipped in each phase. They are not retry attempt counters. To monitor retry attempts, use listeners, logs, or metrics from the retry infrastructure matching your version.

`SkipListener` captures bypassed items:

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        // Reader failed before producing an item.
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        // Record item key and reason.
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        // Record output item that failed to write.
    }
}
```

When analyzing incidents, inspect retry attempts, final exceptions, skip counters, filter counts, rollback counts, and step status together. Looking solely at total skips does not show how many retries occurred beforehand.

## 15. `noRetry` and `noSkip`

In a fault-tolerant step, you can exclude specific exceptions from retry or skip policies using the corresponding settings.

Example:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .noRetry(InvalidOrderException.class)
        .skip(Exception.class)
        .noSkip(FileNotFoundException.class)
        .skipLimit(20)
        .build();
```

This snippet merely illustrates exclusion syntax. In practice, `.skip(Exception.class)` is overly broad and normally should be avoided because it can swallow infrastructure outages or programming bugs. It is better to list specific skippable exceptions and use `noSkip` only to carve out explicit exceptions from a broader rule.

Similarly, `.noRetry(...)` is helpful when a failure type cannot recover via retries even though a parent exception class is configured for retry.

## 16. Choosing a strategy by error type

A practical decision table helps teams standardize error handling:

| Situation | Retry | Skip | Typically appropriate action |
|---|---:|---:|---|
| Short-lived deadlock on update | Yes | Usually no | Bounded retry with backoff; if retries run out, fail the step to investigate. |
| Malformed CSV line | No | Possibly | Skip, persist bad line and line number for reconciliation. |
| Missing required input file | No | No | Fail the job and request the input file. |
| Lookup API transient timeout | Yes | Business-dependent | Retry; if retries run out, store as pending or fail the step. |
| Non-existent customer | Usually no | Possibly | Skip or quarantine item if business rules permit. |
| Widespread database disconnect | Bounded | Usually no | Brief retry with backoff; then stop to avoid mass skipping. |
| Duplicate key from repeated request | Not necessarily | Not by default | Check idempotency/unique keys and verify existing record matches content. |
| Data violating deterministic business rules | No | Possibly | Skip or rejected store, depending on business obligations. |

No single decision table fits every application. The same exception can mean different things depending on source and context. Separate item-level errors from systemic errors.

## 17. Testing retry and skip

Tests should clearly prove the two mechanisms behave differently:

1. **Retry succeeds:** first call throws a transient exception, next succeeds; item is written and skip count stays unchanged.
2. **Retries exhausted, no skip:** all attempts fail; chunk rolls back and step ends `FAILED`.
3. **No retry, skip enabled:** skippable exception occurs; item is bypassed and the corresponding skip counter increments.
4. **Retries exhausted then skip:** exception configured for both retry and skip; once retries run out, item is skipped if budget remains.
5. **Skip limit exceeded:** skips cross threshold; step fails.
6. **Filter:** processor returns `null`; filter count increments while skip count does not.
7. **Repeated side effects:** writer/API is re-invoked; idempotency keys prevent duplicate business outcomes.

For unit tests, mocks can simulate exceptions per call and verify call counts. For integration tests, use a real JobRepository and transaction manager in a test environment to verify statuses, rollbacks, counters, and restarts.

## 18. Common configuration mistakes

| Problem | Cause | Remedy |
|---|---|---|
| Retrying bad data repeatedly | Configuring retry on unrecoverable exceptions. | Remove retry for data errors; use skip or fail per business rules. |
| Database down yet job ends COMPLETED | Overly broad skip policy swallowing infrastructure errors. | Narrow skippable exceptions; systemic outages should fail the step. |
| Items lost after retry exhaustion | No skip/rejected path and operators do not monitor failures. | Let step fail or store rejected items in a proper transaction. |
| Skip count is 0 even though items never reached writer | Processor returned `null`, filtering the items. | Check `filterCount` and processor conditions. |
| Duplicate writes on retry | Non-idempotent side effects or missing unique keys. | Use idempotency keys, upserts, outboxes, or reconciliation. |
| Retry storm | Many workers retrying immediately while downstream is overloaded. | Use backoff/jitter, concurrency caps, and timeouts. |
| Unknown which items were skipped | Checking only `skipCount` without listeners or error tables. | Use `SkipListener` and persist business keys/exceptions. |
| Confusing behavior when both retry and skip apply | Unclassified exceptions or untested policy combinations. | Build an error matrix and test every branch. |

## 19. Process for designing retry/skip for a step

When building a fault-tolerant step, clarify these questions in order:

1. **Classify exceptions:** which errors are transient, which are data errors, and which are configuration/infrastructure failures?
2. **Choose retry policy:** retry only recoverable errors; set sensible limits and backoff.
3. **Choose skip policy:** skip only item errors that business rules permit discarding; set a total skip limit.
4. **Decide post-exhaustion behavior:** skip, quarantine item, or fail the step?
5. **Record failures:** capture item key, read/process/write phase, exception, and execution ID.
6. **Control side effects:** ensure retries/restarts do not generate duplicate transactions, messages, or emails.
7. **Check transactions:** determine which chunks roll back, which commit, and which external resources might have mutated.
8. **Test all branches:** retry success, retry exhaustion, skip, exceeding limits, and unskippable errors.
9. **Design operations:** define who handles rejected items and how to restart after fixing root causes.

Never start by raising `retryLimit` or `skipLimit` until a job passes. Limits must reflect acceptable recovery windows and permissible business data error tolerances.

## 20. Key takeaways

- Retry re-attempts an operation to succeed on the same item/chunk; skip accepts bypassing a faulty item and continuing.
- Retry fits transient errors; skip fits item errors that business rules allow discarding or deferring.
- Retry policy and skip policy are independent; an exception can be retryable, skippable, both, or neither.
- When retries run out, an item is skipped only if the exception is allowed by the skip policy and skip limit is not exceeded; otherwise, the step fails.
- An exception that is skippable but not retryable can be skipped without retrying first.
- `retryLimit` bounds attempts under the retry policy; `skipLimit` bounds total skips across read, process, and write.
- Filtering by returning `null` from the processor differs from exception-driven skip; they have separate counters.
- Retry/skip do not guarantee exactly-once on their own; writers and external integrations require idempotency, unique keys, or outboxes.
- `SkipListener` records skipped items; retry attempts should be tracked via appropriate listeners/logs/metrics.
- Widespread systemic outages such as database unavailable should normally fail the step after bounded retries rather than mass-skipping.
- Test each retry/skip combination, especially retry-exhausted-then-skip and retry-exhausted-then-fail.

When designing Spring Batch jobs, treat retry as a chance to recover an operation and skip as a deliberate decision to bypass an item. Choose both policies based on exception type, business meaning, and potential side effects. With clear bounds, failure recording, and idempotent writers, jobs gain resilience against transient glitches while remaining transparent when data cannot be processed.
