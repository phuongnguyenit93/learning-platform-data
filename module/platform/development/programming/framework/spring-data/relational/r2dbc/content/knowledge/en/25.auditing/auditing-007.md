# Distinguishing Auditing Fields from Business Change Logs

In a Spring Data R2DBC application, entities often have fields such as `createdAt`, `createdBy`, `lastModifiedAt`, and `lastModifiedBy`. These fields show when a record was created, by whom, and when the most recent update occurred. Spring Data Auditing can automatically populate this metadata during the entity save lifecycle.

However, auditing fields on an entity are not a full change history log. When a record is updated multiple times, `lastModifiedAt` and `lastModifiedBy` only retain information from the most recent update. Old values are overwritten; they do not show what each change was, why the change happened, or the before-and-after state of each update.

If business logic needs to answer questions such as "Who changed the credit limit?", "What were the before and after values?", "Which request prompted the change?", or "Which steps did the order status go through?", the application needs a separate business change log. This log is typically stored as append-only records, queryable by subject, actor, timestamp, or request identifier.

## 1. What are auditing fields on an entity?

Spring Data Auditing provides annotations to store creation and update metadata of an entity:

| Annotation | Meaning | Common values |
|---|---|---|
| `@CreatedDate` | Timestamp when the entity was created | `Instant`, `LocalDateTime`, or supported temporal types |
| `@CreatedBy` | User or principal that created the entity | User ID, service account, or actor name |
| `@LastModifiedDate` | Timestamp when the entity was most recently modified | Temporal type |
| `@LastModifiedBy` | User or principal that most recently modified the entity | User ID or service account |

Entity example:

```java
@Table("customer_account")
public class CustomerAccount {

    @Id
    private UUID id;

    private String displayName;

    private BigDecimal creditLimit;

    @CreatedDate
    private Instant createdAt;

    @CreatedBy
    private String createdBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @LastModifiedBy
    private String lastModifiedBy;
}
```

These fields are metadata attached to the current state of the `customer_account` row. After initial creation, `createdAt` and `createdBy` describe the record's origin. On each subsequent update, `lastModifiedAt` and `lastModifiedBy` are updated to reflect the latest modification.

Example after three updates:

| Timestamp | Actor | Action |
|---|---|---|
| 09:00 | `user-17` | Created account, limit 10 million |
| 10:15 | `user-42` | Changed limit to 15 million |
| 14:30 | `admin-3` | Changed limit to 20 million |

The final entity state can only retain information such as `createdBy = user-17`, `createdAt = 09:00`, `lastModifiedBy = admin-3`, `lastModifiedAt = 14:30`. The two edits at 10:15 and 14:30 along with their before/after changes are no longer represented by these four metadata fields.

## 2. Enabling auditing for Spring Data R2DBC

In Java configuration, enable auditing with `@EnableR2dbcAuditing`:

```java
@Configuration
@EnableR2dbcAuditing(auditorAwareRef = "auditorAware")
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName);
    }
}
```

`ReactiveAuditorAware<T>` supplies the current actor as a publisher. The example above retrieves the principal name from the reactive security context. In real applications, you can return a stable user ID instead of a display username, depending on your system's identity model.

If the application does not use Spring Security, `ReactiveAuditorAware` can be implemented from the application's actor-management context. For background tasks, imports, or schedulers, the actor can be a service account such as `batch-import` rather than an interactive user.

Some configuration notes:

- Dependencies and the Spring Data R2DBC version must support the corresponding auditing features.
- The bean referenced in `auditorAwareRef` must match the configured bean name.
- In reactive applications, retrieve the actor from the Reactor/Security Context; do not rely on regular `ThreadLocal` since steps may run on different threads.
- Never trust a `createdBy` or `modifiedBy` field sent by a client. The actor must be determined server-side from an authenticated identity or service identity.
- If there is no actor, clearly decide whether to allow null values or use a system principal; do not assign a fake user just to avoid null.

With Spring Boot, auditing configuration still needs to be explicitly enabled if your application's auto-configuration does not enable it automatically. Do not assume adding annotations to entities alone is enough.

## 3. When does Spring Data Auditing execute?

Spring Data uses entity callbacks to populate metadata into entities during the persistence process. Creation/update fields are processed before data is written to the database. Thus, they reflect the metadata of the save operation currently executing.

For example, when calling:

```java
accountRepository.save(account);
```

Spring Data can populate `createdAt`/`createdBy` for new entities or `lastModifiedAt`/`lastModifiedBy` for existing entities, depending on state and auditing configuration. These values are included in the mapping to be written alongside the entity row.

Auditing operates in Spring Data entity persistence paths such as repositories or `R2dbcEntityTemplate` when properly configured. If the application executes direct SQL via `DatabaseClient` or R2DBC SPI, do not assume entity auditing callbacks will run automatically. For explicit SQL statements, the application must update metadata columns directly in the statement or route the operation through an appropriate entity abstraction.

Example of direct SQL that must set metadata explicitly:

```java
databaseClient.sql("""
        UPDATE customer_account
        SET credit_limit = :limit,
            last_modified_at = :modifiedAt,
            last_modified_by = :modifiedBy
        WHERE id = :id
        """)
    .bind("limit", newLimit)
    .bind("modifiedAt", clock.instant())
    .bind("modifiedBy", actorId)
    .bind("id", accountId)
    .fetch()
    .rowsUpdated();
```

Here the code supplies the timestamp and actor itself because it executes direct SQL. Inject a `Clock` so time can be controlled in tests, instead of scattering `Instant.now()` calls throughout the code.

## 4. Limitations of the four auditing fields

The `created*` and `lastModified*` fields are useful for display and operations, but do not provide a complete change history.

| Question to answer | Are auditing fields enough? |
|---|---|
| Who created the record? | Yes, if `@CreatedBy` is configured and data is saved properly. |
| When was the record created? | Yes, if `@CreatedDate` is configured. |
| Who modified the record most recently? | Yes, via `@LastModifiedBy`. |
| When did the most recent modification occur? | Yes, via `@LastModifiedDate`. |
| When did earlier modifications occur? | No. |
| Which fields changed in each modification? | No. |
| What were the values before and after each modification? | No. |
| Why did the user make the change? | No, unless the application stores reasons separately. |
| Which request, ticket, or workflow did the change belong to? | No, unless the application stores correlation/reference separately. |
| Can state at a previous point in time be restored? | Impossible using these metadata fields alone. |

Therefore, do not treat `lastModifiedBy` as sole proof of all operations that ever occurred. This field only indicates the actor of the most recent modification recorded on the entity.

## 5. What is a business change log?

A business change log (or business audit trail) records actions that carry meaning for the business. Each modification is written as a separate record rather than overwriting previous information.

A log entry typically contains:

- **Target:** aggregate/entity type and identifier of the modified object.
- **Action:** for example `CREDIT_LIMIT_CHANGED`, `ORDER_APPROVED`, `ACCOUNT_SUSPENDED`.
- **Actor:** user, service, or system performing the action.
- **Timestamp:** business timestamp recorded for the action.
- **Before and after:** old/new values or snapshots needed to explain the change.
- **Reason:** business reason, approval note, or request code.
- **Correlation/reference:** request ID, ticket ID, workflow ID, or command ID to link steps together.

Not every SQL operation needs a business audit entry. The log should describe business-meaningful actions—for example "credit limit increased from 10 million to 15 million per approved request"—rather than merely logging "UPDATE row 123".

## 6. Comparing auditing fields, business logs, and technical logs

Three types of data frequently coexist in a system, each serving a different purpose:

| Criterion | Spring Data Auditing fields | Business change log | Technical/application log |
|---|---|---|---|
| Goal | Creation and last-modified metadata of an entity | History of business actions | System diagnostics, monitoring, and troubleshooting |
| Storage form | Columns on the entity row | Separate records, typically append-only | Log files or centralized logging system |
| Record count | One current metadata set per entity | Potentially many records per entity | Many lines per request, component, or process |
| Content | Who created/modified and when | Who did what, which target, before/after, reason | Log level, message, stack trace, latency, correlation ID |
| When entity updates | Overwrites last-modified metadata | Appends a new entry for tracked actions | Logs technical events if configured |
| Used for restoring history | No | Can support it, if sufficient data and clear replay rules are stored | Should not be used as a source for business recovery |
| Access permissions | Follows entity read permissions | Often requires separate audit permissions, restricting edit/delete | Follows operational and log security policies |

Technical logs do not replace a business audit trail. A log line such as `Updated customer 123` may lack a trusted actor, before/after values, reason, and durable storage guarantees. Conversely, never put stack traces, sensitive SQL, or arbitrary debug details into a business change log.

## 7. Designing a change log table

A simple table can store changes across multiple aggregate types:

```sql
CREATE TABLE business_change_log (
    id UUID PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    action VARCHAR(120) NOT NULL,
    actor_id VARCHAR(160) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    reason TEXT,
    correlation_id VARCHAR(160),
    before_state TEXT,
    after_state TEXT
);

CREATE INDEX ix_change_log_aggregate_time
    ON business_change_log (aggregate_type, aggregate_id, occurred_at);

CREATE INDEX ix_change_log_actor_time
    ON business_change_log (actor_id, occurred_at);
```

The example uses `TEXT` for `before_state` and `after_state` to illustrate serialized payloads. If your database supports JSON/JSONB and the application needs to query individual properties, choose the matching JSON type with appropriate codecs/converters. Timestamp, UUID, and index types should be adjusted for your actual database.

Design decisions to clarify:

- `aggregate_type` should be a stable business type name, not necessarily a Java class name that could change during refactoring.
- `aggregate_id` can be a string to support multiple key types, though its format must be consistent.
- `action` should be a stable action code, using an enum/domain code rather than free-text descriptions as a classification key.
- `actor_id` should be a stable identifier; if a display name is needed, you can also store a name snapshot at the time of the action.
- `occurred_at` should have a clear timezone convention, typically storing UTC instants.
- `reason` should have length limits and rules filtering sensitive data.
- `correlation_id` helps link business logs with requests and technical traces, though it does not replace audit content.
- Before/after snapshots should only contain necessary fields; avoid copying the entire entity if it holds secrets or unnecessary personal data.

## 8. Example logging a credit limit change

Suppose business logic allows authorized staff to change a credit limit. The current entity holds `creditLimit`, while the log must capture before and after values, actor, and reason.

A log model can look like this:

```java
@Table("business_change_log")
public class BusinessChangeLog {

    @Id
    private UUID id;

    private String aggregateType;
    private String aggregateId;
    private String action;
    private String actorId;
    private Instant occurredAt;
    private String reason;
    private String correlationId;
    private String beforeState;
    private String afterState;

    public static BusinessChangeLog creditLimitChanged(
            UUID accountId,
            String actorId,
            Instant occurredAt,
            String reason,
            String correlationId,
            BigDecimal oldLimit,
            BigDecimal newLimit) {

        return new BusinessChangeLog(
            UUID.randomUUID(),
            "CustomerAccount",
            accountId.toString(),
            "CREDIT_LIMIT_CHANGED",
            actorId,
            occurredAt,
            reason,
            correlationId,
            oldLimit.toPlainString(),
            newLimit.toPlainString()
        );
    }
}
```

Constructors and getters/setters are omitted to focus on data structure. In a project, you can use a record/immutable object or builder.

A service writing both the entity and the change log in the same R2DBC transaction:

```java
@Service
public class CreditLimitService {

    private final CustomerAccountRepository accountRepository;
    private final BusinessChangeLogRepository changeLogRepository;
    private final Clock clock;

    @Transactional
    public Mono<CustomerAccount> changeLimit(
            UUID accountId,
            BigDecimal newLimit,
            String reason,
            String actorId,
            String correlationId) {

        return accountRepository.findById(accountId)
            .switchIfEmpty(Mono.error(
                new AccountNotFoundException(accountId)))
            .flatMap(current -> {
                BigDecimal oldLimit = current.getCreditLimit();
                current.setCreditLimit(newLimit);

                return accountRepository.save(current)
                    .flatMap(saved -> {
                        BusinessChangeLog entry =
                            BusinessChangeLog.creditLimitChanged(
                                accountId,
                                actorId,
                                clock.instant(),
                                reason,
                                correlationId,
                                oldLimit,
                                saved.getCreditLimit()
                            );

                        return changeLogRepository.save(entry)
                            .thenReturn(saved);
                    });
            });
    }
}
```

The example assumes both repositories share the same `ConnectionFactory` and transaction manager. Then the credit limit change and history record can commit or roll back together. If saving the entity succeeds but writing the change log fails, the error in the reactive chain rolls back the transaction; never let the entity change without its corresponding log entry.

`actorId` and `correlationId` in the example are passed into the service to highlight the required data. In a real application, the actor must come from the security context or a trusted server-side context, not directly from the request body. The change reason must also be validated against business rules.

## 9. Logging changes by business action, not only by column

There are two common ways to describe changes:

**Field-level diff:** stores field names alongside old and new values, for example:

```json
{
  "changes": [
    {
      "field": "creditLimit",
      "before": "10000000.00",
      "after": "15000000.00"
    }
  ]
}
```

**Business event:** stores a meaningful action, such as `CREDIT_LIMIT_CHANGED`, with a payload describing before/after limits and the approval reason.

Field-level diff fits cases where you need to display detailed edit history across many properties. Business events fit cases where the system needs to categorize actions in ubiquitous business language and reuse them in reports or workflows.

Not every technical change needs a business event. For example, updating `lastAccessedAt`, syncing a cache, or editing internal metadata might not be an action worth showing in business history. Clearly defining the list of tracked actions prevents excessive logging that obscures important changes.

## 10. Business change logs are not Event Sourcing

A business audit trail and Event Sourcing share the trait of storing events over time, but their roles differ.

| Aspect | Business audit trail | Event Sourcing |
|---|---|---|
| Primary purpose | Explain who performed what action and how data changed | Store events as the source of truth to derive aggregate state |
| Source of current state | Usually still the current entity/state table | Computed by applying a sequence of events |
| Event content | Can be diffs, actor, reason, before/after | Domain events sufficient to reconstruct state per domain rules |
| Schema/event evolution | Serves historical lookup | Requires versioning/upcasting and long-term replay compatibility |
| Reading current data | Direct read from state table | Derived from events or served via projections/snapshots |

A system can store an audit log alongside a CRUD model without adopting Event Sourcing. If you want events to be the source of truth, you must design full aggregates, event schemas, replay, snapshots, projections, and event versioning. Simply adding a `business_change_log` table does not turn a system into Event Sourcing.

## 11. Ensuring consistency between entities and logs

If the requirement is "every successful business change must have a corresponding audit record", both write operations must reside within the same local database transaction:

1. Read the current state and verify the change is valid.
2. Update the entity.
3. Construct the change log with actor, action, timestamp, reason, and before/after data.
4. Save the change log.
5. Commit the transaction once both operations succeed.

If the change log resides in a different database, the entity database's `R2dbcTransactionManager` does not automatically guarantee both databases commit together. In that case, an outbox, compatible distributed transaction, or dedicated synchronization/compensation workflow is required.

If logs are used to publish messages to a broker, you can write the business change log or outbox event inside the database transaction, then have a publisher dispatch after commit. Never send messages directly inside an `AfterSaveCallback` assuming the callback only runs after commit.

## 12. Append-only properties and protecting logs

Change logs generally require stricter protection than regular entity tables. Key principles:

- Insert new records only; business applications should not update or delete already-written history entries.
- Use a dedicated database role with appropriate `INSERT` and `SELECT` privileges; restrict `UPDATE`/`DELETE` on audit tables.
- Database triggers or controls can be used to prevent accidental modifications or deletions.
- Store actors and timestamps from a trusted server-side source.
- Index by aggregate ID and timestamp for efficient history lookups.
- Design partitioning/archival as data grows, with an explicit retention policy.
- Restrict read access to logs because before/after snapshots may contain sensitive data.
- Log access or exports of audit logs if access-control auditing is required.

Application-layer append-only enforcement does not guarantee absolute tamper resistance. Database administrators can still alter data unless additional controls exist. For high-assurance evidentiary requirements, you may need immutable storage, hash chaining, signatures, or audit copies in a separately administered system. Such measures must be designed and operated properly; adding a hash column alone does not make data tamper-proof.

## 13. Sensitive data and retention policies

Do not copy entire entities into `before_state` and `after_state` by default. Snapshots may contain passwords, tokens, payment details, personal data, or fields unnecessary for auditing.

Recommended practices:

- Allowlist the business fields whose history should be stored.
- Mask or strip secrets, credentials, tokens, and authentication data.
- Never store payment card values or secrets improperly.
- Enforce length limits and accepted content rules on `reason`.
- Define retention periods, archival workflows, and deletion policies per legal/internal rules.
- Authorize history queries by tenant, role, and usage purpose.
- Avoid leaking sensitive snapshots into application logs or traces.

Logs meant for investigation do not mean keeping all data forever. Retention policies must balance audit requirements, privacy, storage costs, and data-erasure obligations.

## 14. Handling updates via direct SQL

`DatabaseClient` or custom SQL operations can bypass entity callbacks and auditing infrastructure. If a use case uses direct SQL to update an entity table, it must explicitly update `last_modified_*` columns and create a business audit entry.

Example:

```java
@Transactional
public Mono<Void> updateStatus(
        UUID orderId,
        OrderStatus newStatus,
        String actorId,
        String reason) {

    Instant now = clock.instant();

    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(oldOrder -> {
            OrderStatus oldStatus = oldOrder.getStatus();

            return databaseClient.sql("""
                    UPDATE purchase_order
                    SET status = :status,
                        last_modified_at = :modifiedAt,
                        last_modified_by = :modifiedBy
                    WHERE id = :id
                    """)
                .bind("status", newStatus.name())
                .bind("modifiedAt", now)
                .bind("modifiedBy", actorId)
                .bind("id", orderId)
                .fetch()
                .rowsUpdated()
                .flatMap(count -> {
                    if (count != 1) {
                        return Mono.error(
                            new UnexpectedUpdateCountException(count));
                    }

                    return changeLogRepository.save(
                        OrderStatusChange.of(
                            orderId, oldStatus, newStatus,
                            actorId, now, reason))
                        .then();
                });
        });
}
```

This example reads the old state and then updates with SQL to illustrate explicit audit writing. When concurrent updates can occur, add an optimistic version predicate or appropriate locking so `oldStatus` accurately reflects the transitioned state. Otherwise, two transactions could read the same old state and write two history records out of line with intended business ordering.

For conditional updates, check `rowsUpdated()` and write audit entries only when the database actually modified a row. If the update count is 0, the row may not exist, the version may have mismatched, or the predicate may no longer hold; interpret it according to the use-case contract.

## 15. Avoiding duplicate or missing logs

Several situations can produce inaccurate logs:

- Writing the change log before the update, then the update fails while the log commits in another transaction.
- Writing the entity first and then writing the log in a separate transaction; if log writing fails, the state changed without history.
- Retrying a command after a timeout when the first attempt actually committed, creating two change logs for one action.
- Both a post-save callback and the service writing an audit entry for one change, creating duplicate records.
- Logging an update whose `rowsUpdated = 0`, even though no data changed.

Controls:

1. Write the entity and audit entry in the same transaction when using the same database.
2. Generate a stable `commandId` or `idempotencyKey` for retryable actions.
3. Place a unique constraint on event/command ID if each command may be recorded only once.
4. Create change logs only after validating the change and verifying the expected affected row count.
5. Designate a single layer responsible for writing business audits; never log the same action in both callbacks and services without deduplication rules.
6. For broker side effects, use an outbox and consumer idempotency.

## 16. Querying change history

When storing each change as a separate row, you can fetch history by aggregate:

```java
public interface BusinessChangeLogRepository
        extends ReactiveCrudRepository<BusinessChangeLog, UUID> {

    Flux<BusinessChangeLog>
    findByAggregateTypeAndAggregateIdOrderByOccurredAtDesc(
        String aggregateType, String aggregateId);
}
```

For large histories, paginate or bound by time instead of loading everything. Include a stable tie-breaker like `id` if multiple events share the same timestamp:

```sql
SELECT *
FROM business_change_log
WHERE aggregate_type = :type
  AND aggregate_id = :aggregateId
ORDER BY occurred_at DESC, id DESC
LIMIT :pageSize;
```

You can also query by actor, action, or correlation ID for investigation. Indexes should match actual query patterns; avoid creating excessive indexes since every audit insert must update them too.

## 17. Auditing fields and business change logs can be used together

These two mechanisms are not mutually exclusive. An entity can store current metadata for fast reads while a history table explains each individual change.

Example:

| Need | Data source |
|---|---|
| Display "Created by An at 09:00" on the detail page | `createdBy`, `createdAt` |
| Display "Last updated by Binh at 14:30" | `lastModifiedBy`, `lastModifiedAt` |
| View all credit limit changes over 6 months | `business_change_log` |
| View before/after values and approval reason | Business change log with before/after and reason |
| Trace the request that caused a change | `correlation_id` in the audit entry paired with technical traces/logs |
| Diagnose why a SQL query timed out | Technical logs, metrics, and traces |

Auditing fields make querying current state fast and simple. Business change logs add the historical dimension, while technical logs serve operations. Designing these three purposes clearly avoids stuffing entire histories into entity tables and avoids treating technical logs as business evidence.

## 18. Design checklist for a use case requiring history

Before implementing, determine:

1. Which actions truly require business-level audit tracking?
2. Which security context/service identity provides the actor, and is it stable?
3. Do we need field-level before/after diffs or selective snapshots?
4. Which reason, ticket ID, command ID, and correlation ID must be recorded?
5. Can the entity and audit log be written within the same `ConnectionFactory`/transaction?
6. Does direct SQL explicitly update `lastModified*` columns and write audit logs?
7. Could retries create duplicate audits; is an idempotency key/unique constraint needed?
8. Who is permitted to read history, and which sensitive data must be masked or omitted?
9. What are the retention, archival, and append-only protection policies?
10. Are there integration tests verifying the entity and change log commit/roll back together?

## 19. Testing audit consistency

Both success and failure cases should be tested:

| Scenario | Expected outcome to verify |
|---|---|
| Create entity via repository | `createdAt` and `createdBy` are populated per configuration. |
| Update entity via repository | `lastModifiedAt` and `lastModifiedBy` reflect the new modification. |
| Update entity multiple times | Entity metadata keeps only the latest edit; change log captures every required entry. |
| Entity save succeeds, audit write fails in same transaction | Both entity and audit entry roll back. |
| Transaction rolls back after creating audit entry | Neither uncommitted entity changes nor audit entries remain. |
| Retry the same command | No duplicate change logs if command is designed to be idempotent. |
| Direct SQL | Metadata columns and business audits are explicitly updated. |
| Cross-tenant history access | Cannot read audit entries outside authorized scope. |

Unit tests can verify event creation logic and before/after content. Integration tests on a real database must confirm transactions, constraints, mappings, and access permissions. For high tamper-resistance requirements, test database privileges and archive/retention procedures as well.

Spring Data R2DBC auditing fields describe who created an entity and who most recently modified it. A business change log records each meaningful action, along with actor, timestamp, reason, and before/after data when needed. The two mechanisms complement each other: entity metadata serves current state; a business audit trail serves history and accountability; and technical logs serve system diagnostics. When changes and history must stay consistent, write them in the same database transaction, design idempotency for retries, and protect logs according to your organization's access, sensitive-data, and retention policies.
