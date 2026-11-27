# Limits of Auditing, Logs, and Events for Business Traceability Requirements

In a **Spring Data Relational JDBC** system, business traceability cannot rely solely on created_at/updated_at columns or SQL logs. Each mechanism answers a different question:

- **Auditing metadata** tells who created or modified an entity and when.
- **Persistence callbacks and lifecycle events** show that a save/delete/load operation is passing through the persistence infrastructure.
- **Application logs and distributed tracing** help operations locate requests, errors, latencies, and flows across services.
- **Business audit history and domain events** record meaningful business actions, such as who approved an order, changed a credit limit, or cancelled a contract.
- **Transactional outbox** persists events destined for external publishing in the same transaction as the data change.

These mechanisms do not replace one another. Auditing annotations do not create a complete history of every change; lifecycle callbacks do not observe every SQL statement; logs can be lost or rotated; in-memory events are not durable queues. When business traceability has audit compliance requirements, you must explicitly design data sources, transaction boundaries, access controls, retention, and how write paths outside Spring Data JDBC are handled.

## 1. Distinguishing Five Types of Traceability Information

| Mechanism | Question answered | Examples | Main limitation |
|---|---|---|---|
| Spring Data JDBC auditing | Who created/modified an entity and when? | createdBy, createdDate, lastModifiedBy, lastModifiedDate | Runs only on persistence paths with auditing callbacks |
| Entity callbacks/lifecycle events | Which stage is the persistence operation in? | BeforeSave, AfterSave, BeforeDelete | Not durable business history; direct SQL can bypass it |
| Application logs/tracing | Which request ran, where did it fail, how long did it take? | traceId, correlationId, operation, duration | Logs can be lost, rotated, or tampered with; not an audit ledger |
| Business audit record/domain event | What business action occurred? | ORDER_APPROVED, CREDIT_LIMIT_CHANGED | Requires explicit schema, actor, payload, retention, and transaction design |
| Transactional outbox | Which events must be published externally reliably? | OrderApprovedEvent awaiting publish | Requires relay, retries, deduplication, and monitoring |

Example: an employee approves an order.

- created/lastModified metadata shows who most recently created or updated the aggregate.
- Business audit records capture exactly who approved which order, from which state to which state, and for what reason.
- Logs record the request/trace, outcome, duration, and any errors.
- The outbox stores the OrderApproved event for a worker to publish to a message broker after the transaction commits.

With only two auditing columns, the system cannot fully answer who approved it, under what authority, why, what the prior state was, or whether the event was delivered to downstream systems.

## 2. What Does Spring Data JDBC Auditing Record?

Spring Data Relational provides standard auditing annotations:

- **@CreatedBy:** the actor that created the entity.
- **@CreatedDate:** creation timestamp.
- **@LastModifiedBy:** the actor that most recently modified it.
- **@LastModifiedDate:** most recent modification timestamp.

Auditing is enabled with **@EnableJdbcAuditing**. The framework uses auditing infrastructure and entity callbacks to populate metadata when entities pass through matching persistence paths.

Example:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private String status;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @LastModifiedBy
    @Column("last_modified_by")
    private String lastModifiedBy;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;
}
~~~

Corresponding SQL columns might look like:

~~~sql
ALTER TABLE purchase_order
    ADD COLUMN created_by VARCHAR(120),
    ADD COLUMN created_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN last_modified_by VARCHAR(120),
    ADD COLUMN last_modified_at TIMESTAMP WITH TIME ZONE;
~~~

This DDL illustrates PostgreSQL. For other databases, choose appropriate timestamp types. If a table already has audit columns, map existing column names with **@Column**; do not add duplicate columns merely because Java field names differ.

Auditing metadata generally represents the entity's current state. After multiple updates, lastModifiedBy and lastModifiedDate retain only the latest update; they do not preserve the full history of prior changes.

## 3. Configuring AuditorAware and Time

CreatedBy and LastModifiedBy need an actor provider. Spring Data uses **AuditorAware<T>** to obtain the current user. In web applications, the actor normally comes from Spring Security; in batch jobs or schedulers, it may be a service account.

~~~java
@Configuration
@EnableJdbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "auditDateTimeProvider"
)
public class JdbcAuditingConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> {
            Authentication authentication =
                    SecurityContextHolder.getContext().getAuthentication();

            if (authentication == null
                    || !authentication.isAuthenticated()
                    || authentication instanceof AnonymousAuthenticationToken) {
                return Optional.empty();
            }

            return Optional.of(authentication.getName());
        };
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock clock) {
        return () -> Optional.of(clock.instant());
    }

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }
}
~~~

This snippet illustrates using Spring Security and Java's Clock. Corresponding Security dependencies and configuration are required. If the application does not use Spring Security, implement AuditorAware from your own authentication context.

### Why Use Clock?

Injecting Clock helps you:

- Use UTC consistently.
- Test timestamps with a fixed clock.
- Avoid scattering Instant.now() across domains/services.
- Control clock sources across environments.

For example, tests can provide Clock.fixed(...) for deterministic timestamps. If the database also generates timestamps via defaults or triggers, decide explicitly which timestamp is the source of truth. Mixing app clocks and DB clocks without rules can introduce drift.

### Actors May Be Absent

AuditorAware returns Optional.empty() when no actor exists. This commonly happens with:

- Scheduled jobs.
- Batch imports.
- Message consumers.
- System-to-system requests.
- Tests without a configured security context.
- Async tasks running on different threads.

If audit columns are NOT NULL, define a clear system actor convention such as system:billing-reconciliation or pass actor context into the use case. Never assign a fake username everywhere, as that obscures real provenance.

Never assume SecurityContext automatically propagates across every executor or thread. For async or message processing, pass actor/correlation metadata inside messages or use configured context propagation.

## 4. Which Persistence Paths Trigger Auditing Callbacks?

Spring Data JDBC uses entity callbacks to apply auditing metadata before writing. The auditing infrastructure registers the callback and updates the entity according to its mapping.

Operations going through Spring Data JDBC repositories or JdbcAggregateTemplate can trigger lifecycle/callback infrastructure:

- Inserting aggregates.
- Updating aggregates.
- Loading aggregates.
- Deleting aggregates, depending on the operation and corresponding callback.

However, write paths must be clearly distinguished:

| Write path | Spring Data JDBC auditing callback |
|---|---|
| repository.save(aggregate) | Yes, per auditing configuration and entity mapping |
| JdbcAggregateTemplate.insert/update | Goes through Spring Data JDBC aggregate infrastructure |
| JdbcTemplate.update(...) | Does not automatically trigger entity auditing callbacks |
| NamedParameterJdbcTemplate.update(...) | Does not automatically trigger entity auditing callbacks |
| MyBatis mapper DML | Does not automatically trigger Spring Data JDBC callbacks |
| SQL executed by another service | Does not trigger this application's callbacks |
| Stored procedures/direct ETL | Does not trigger Spring Data JDBC callbacks |

This is the most critical limitation when multiple writers exist. If a table is updated by repositories, MyBatis, batch jobs, and hand-written SQL, the four auditing columns populated by Spring Data JDBC are not guaranteed to reflect every change.

If auditing must cover every writer, choose one of these designs:

1. Standardize all writes through application services/repositories with auditing.
2. Use database triggers to record audits at the database layer, passing actor/session context securely.
3. Use a central audit service/API and require all writers to integrate with it.
4. Combine database-level auditing for data mutations with business audit events for business actions.

Never enable @EnableJdbcAuditing and claim every database change is audited.

## 5. Auditing Aggregate Roots and Owned Entities

Spring Data JDBC persists aggregates as a unit, yet audit requirements can differ between roots and child entities.

~~~text
PurchaseOrder
  id
  status
  last_modified_by
  last_modified_at
  lines
    ├── OrderLine
    │     id
    │     quantity
    │     last_modified_by
    │     last_modified_at
    └── OrderLine
~~~

When metadata is required on both root and child entities, verify:

- Do child entities have their own entity metadata and audit columns?
- Are callbacks invoked on every object needing auditing along that specific persistence path?
- Does saving the root rewrite/delete-insert child rows under the current mapping strategy?
- Is a child's createdAt preserved when the child is saved again?
- Does direct SQL updating children follow the same rules?

Do not assume annotations on the root automatically populate audit columns on every child row or every row in the aggregate. Verify behavior in your Spring Data JDBC version using integration tests and SQL logs.

If auditing per child operation is an important requirement, an append-only business audit table is often better suited than trying to keep complete history on individual entity rows.

## 6. Lifecycle Callbacks and Lifecycle Events Differ from Business Events

Spring Data Relational provides callbacks and events tied to the persistence lifecycle. Common names include:

- BeforeConvertCallback
- BeforeSaveCallback
- AfterSaveCallback
- AfterLoadCallback
- BeforeDeleteCallback
- AfterDeleteCallback

Lifecycle events can be emitted around stages such as before convert/save, after save, after load, or after delete.

Callbacks and events extend persistence infrastructure—for example, normalizing metadata, generating technical values, or observing persistence operations. They do not express business meaning on their own.

For example:

- AfterSaveCallback means the aggregate was just saved via the persistence path.
- ORDER_APPROVED means a business action was accepted under domain rules.
- These are not equivalent: an aggregate might be saved to change an address, edit a note, or apply a technical update without any approval action.

### What Are Callbacks Good For?

- Populating/normalizing metadata before conversion.
- Validating or adjusting persistence data per technical rules.
- Assigning required technical values before saving.
- Running entity-lifecycle logic requiring deterministic ordering.

### What Are Events Good For?

- Notifying listeners inside the application context that a persistence lifecycle event occurred.
- Observing, recording metrics, or triggering internal reactions.
- Wiring processing coupled to lifecycle phases.

### Never Use Callbacks/Events to Replace Domain Rules

Do not place order approval decisions, credit checks, authorization, or payment confirmations into a callback simply because it runs before save. Domain rules belong in aggregates, domain services, or application services so they can be invoked, tested, and understood per use case.

Callbacks are not the right place to send emails, make HTTP calls, or publish external messages before transaction commit. If an external side effect succeeds and the transaction later rolls back, external systems hold inconsistent information.

## 7. EntityCallback vs. ApplicationEvent: Choosing the Right Mechanism

EntityCallbacks are invoked directly by the persistence infrastructure and return the potentially modified entity. Callbacks can be synchronous or reactive depending on the API; Spring Data JDBC is imperative JDBC, so use callbacks suited to imperative flows.

Example callback before conversion:

~~~java
@Component
public class OrderNormalizationCallback
        implements BeforeConvertCallback<PurchaseOrder> {

    @Override
    public PurchaseOrder onBeforeConvert(
            PurchaseOrder aggregate) {

        aggregate.normalizeStatus();
        return aggregate;
    }
}
~~~

This example is illustrative; with immutable aggregates, callbacks must return a new instance rather than mutating the object.

Lifecycle events are usually published via Spring's ApplicationEvent infrastructure, and listeners can use @EventListener. When a listener must run after transaction commit, use @TransactionalEventListener with the proper phase rather than assuming AfterSaveEvent means data has committed.

Do not rely on ordering among multiple callbacks or event listeners unless order is explicitly configured. If logic requires strict sequencing, place it in an application service or an explicitly ordered callback chain.

## 8. Business Audit History Must Be Stored Separately

When requirements must answer:

- Who performed the action?
- What action occurred?
- Which aggregate was affected?
- What were the before and after values?
- What was the business reason?
- Which request/approval led to the change?
- When did the action happen?
- Did it succeed and commit?

you need a dedicated business audit table or event store rather than relying only on created/modified columns.

Append-only schema example:

~~~sql
CREATE TABLE business_audit (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    action VARCHAR(120) NOT NULL,
    actor_id VARCHAR(160) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    correlation_id VARCHAR(160),
    causation_id VARCHAR(160),
    reason VARCHAR(1000),
    payload JSONB,
    schema_version INTEGER NOT NULL
);

CREATE INDEX idx_business_audit_aggregate_time
    ON business_audit(aggregate_type, aggregate_id, occurred_at DESC);

CREATE INDEX idx_business_audit_actor_time
    ON business_audit(actor_id, occurred_at DESC);
~~~

This DDL uses PostgreSQL UUID/JSONB. For other databases, choose equivalent types and review indexing strategies.

### Audit Record Contents

| Field | Meaning |
|---|---|
| event_id | Unique ID for deduplication |
| aggregate_type | Aggregate type |
| aggregate_id | ID of the affected aggregate |
| action | Business action |
| actor_id | Performing user or service account |
| occurred_at | Business occurrence timestamp |
| correlation_id | Groups operations belonging to a single request/workflow |
| causation_id | Event/command that caused the current change |
| reason | Permitted reason or note |
| payload | Business values needed for traceability |
| schema_version | Payload structure version |

Do not dump entire entity graphs or full request bodies by default. Store only the fields required for audit purposes, and define rules for personal data, trade secrets, and sensitive data.

### Audit Records Must Not Be Arbitrarily Updated

Business audit history generally requires append-only semantics. Database permissions should restrict the runtime account to necessary INSERT/SELECT privileges; UPDATE/DELETE should be granted only to controlled retention/administration workflows.

Still, application-level append-only rules alone do not create tamper-proof storage. Users with high database privileges could still edit or delete rows. If strong tamper resistance is required, add separation of duties, database-level auditing, immutable/WORM storage, signing/hash chains, or dedicated audit storage and test access procedures.

## 9. Writing Business Audits in the Same Transaction as Aggregate Changes

If an audit record serves as proof that a change committed, insert the audit row in the same transaction as the aggregate:

~~~java
@Service
public class ApproveOrderService {

    private final PurchaseOrderRepository orders;
    private final BusinessAuditRepository audit;

    public ApproveOrderService(
            PurchaseOrderRepository orders,
            BusinessAuditRepository audit) {
        this.orders = orders;
        this.audit = audit;
    }

    @Transactional
    public void approve(
            Long orderId,
            String actorId,
            String reason,
            String correlationId) {

        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow();

        String previousStatus = order.getStatus();
        order.approve();

        PurchaseOrder saved = orders.save(order);

        audit.insert(new BusinessAuditEntry(
                UUID.randomUUID(),
                "PurchaseOrder",
                saved.getId().toString(),
                "ORDER_APPROVED",
                actorId,
                Instant.now(),
                correlationId,
                null,
                reason,
                previousStatus,
                saved.getStatus()
        ));
    }
}
~~~

This is an illustrative example; BusinessAuditRepository can be a Spring Data JDBC repository or a custom JDBC repository. Inject a Clock rather than calling Instant.now() directly in production code if deterministic time testing is needed.

If the audit insert fails and the exception escapes the transaction, the aggregate change rolls back as well. If the aggregate update fails, the audit row is not committed. This provides atomicity between business state and audit history within the same database.

Never insert an audit record in an independent REQUIRES_NEW transaction if the record represents a "committed action." If the outer transaction rolls back while the audit transaction committed, history would record an action that never happened. If you need to log attempts or failures separately, use distinct naming and semantics such as ORDER_APPROVAL_ATTEMPTED or ORDER_APPROVAL_FAILED.

## 10. Domain Events and Business Events

A domain event represents something meaningful within the domain, such as:

- OrderApproved.
- PaymentCaptured.
- CreditLimitChanged.
- CustomerAddressChanged.
- InventoryReserved.

Events should be raised by aggregate/domain logic when invariants are satisfied, or by an application service orchestrating a use case. They should not be inferred solely from a row update.

An aggregate can hold unpublished domain events:

~~~java
public class PurchaseOrder {

    private final List<Object> domainEvents = new ArrayList<>();

    public void approve(String actorId) {
        if (!canApprove()) {
            throw new IllegalStateException("Order cannot be approved");
        }

        String previousStatus = status;
        status = "APPROVED";

        domainEvents.add(new OrderApproved(id, actorId, previousStatus));
    }

    @DomainEvents
    public Collection<Object> domainEvents() {
        return List.copyOf(domainEvents);
    }

    @AfterDomainEventPublication
    public void clearDomainEvents() {
        domainEvents.clear();
    }
}
~~~

Spring Data repository infrastructure supports publishing domain events from aggregate roots via annotations such as @DomainEvents and @AfterDomainEventPublication when corresponding repository methods are called. Check the exact methods and lifecycle behavior of your Spring Data version.

Points to keep in mind:

- Domain events carry business semantics; lifecycle events carry persistence semantics.
- Publishing an event in-process does not mean a broker received it.
- @AfterDomainEventPublication is not proof an external system processed the event successfully.
- Do not treat an in-object event list as a durable event store.
- When you must guarantee events are published after commit without loss on process crash, use an outbox.

## 11. Transactional Event Listeners and Post-Commit Limits

Spring provides @TransactionalEventListener to bind listeners to transaction phases, for example:

~~~java
@Component
public class OrderNotificationListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderApproved(OrderApproved event) {
        // Send notification or trigger post-commit work.
    }
}
~~~

Common phases include BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, and AFTER_COMPLETION. Listeners bind to transactions by default; without an active transaction, events may not be handled unless fallbackExecution is enabled.

AFTER_COMMIT prevents sending notifications for rolled-back changes. However, it does not guarantee durable delivery:

1. The database commits successfully.
2. The process crashes before the listener runs or before the message finishes sending.
3. The event has no persistent record for retrying.

Listeners also run in the application process; exceptions after commit cannot roll back already-committed data. If a listener needs to write to the database after commit, design a clear new transaction rather than assuming the prior transaction is still active.

Use AFTER_COMMIT for best-effort side effects or internal signals where occasional loss or manual retry is acceptable. For critical financial, order, or cross-system synchronization messages, use a transactional outbox.

## 12. Transactional Outbox for Reliable Delivery

An outbox stores business events in the same database transaction as the aggregate. A worker/relay reads unpublished rows and forwards them to a message broker or target system.

~~~mermaid
flowchart TD
    A["Application service"] --> B["Single transaction"]
    B --> C["Update aggregate"]
    B --> D["Insert outbox event"]
    C --> E["COMMIT"]
    D --> E
    E --> F["Outbox relay"]
    F --> G["Message broker / downstream"]
    G --> H["Consumer deduplicates by event_id"]
~~~

Table example:

~~~sql
CREATE TABLE outbox_event (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(120) NOT NULL,
    aggregate_id VARCHAR(160) NOT NULL,
    event_type VARCHAR(160) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(20) NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE,
    published_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_outbox_pending
    ON outbox_event(status, next_attempt_at, occurred_at);
~~~

Service writing aggregate and outbox:

~~~java
@Transactional
public void approve(Long orderId, String actorId) {
    PurchaseOrder order = repository.findById(orderId).orElseThrow();
    order.approve(actorId);

    PurchaseOrder saved = repository.save(order);

    outboxRepository.insert(
            OutboxEvent.orderApproved(saved, actorId, clock.instant())
    );
}
~~~

If either operation fails, the transaction rolls back both. The relay sees events only after commit.

### At-Least-Once Delivery and Idempotency

Outbox relays typically provide at-least-once delivery. One possible failure sequence:

1. The relay publishes the message successfully.
2. The process crashes before marking the outbox row published.
3. Another worker republishes the same event.

Consumers must therefore deduplicate using event_id or an idempotency key. Never assume end-to-end exactly-once semantics just because an outbox is used.

The relay needs:

- Retry/backoff and attempt limits.
- Lease/claim or locking mechanisms so multiple workers do not process the same row.
- Dead-letter/manual replay paths.
- Metrics for pending count and oldest event age.
- Persistence of published_at/status.
- Procedures for handling permanently failed events.
- Controlled retention/cleanup.

Avoid holding database row locks during slow broker network calls. Claim batches using a lease or status/locked_until, commit the claim, publish outside the transaction, then update status. SQL locking options like SKIP LOCKED depend on the database vendor.

## 13. Structured Logs for Request Traceability

Operational logs should be structured for searching and correlation. Useful fields include:

| Field | Meaning |
|---|---|
| timestamp | Log timestamp |
| level | INFO/WARN/ERROR |
| service/environment | Service and environment |
| trace_id/span_id | Links distributed traces |
| correlation_id | Groups operations in a workflow |
| actor_id | Authenticated principal, if needed |
| operation | Use-case name |
| aggregate_type/id | Related business entity |
| outcome | success/failure/rejected |
| duration_ms | Processing duration |
| error_code | Stable error code |
| retry_count | Retry attempt count |

Structured log example:

~~~java
log.info(
        "order approval completed: orderId={}, actorId={}, correlationId={}, outcome={}",
        orderId,
        actorId,
        correlationId,
        "SUCCESS"
);
~~~

With JSON logging, fields are written as key/value pairs so log backends can filter and aggregate. Avoid writing only long free-form sentences without stable fields.

### Correlation ID and Trace ID

A correlation ID links steps across a business workflow; trace ID/span ID link spans in distributed tracing. Both can be used together since they answer different questions.

- The HTTP gateway can generate or accept a validated/controlled correlation ID.
- Services propagate correlation metadata across HTTP/message headers.
- Consumers restore context when processing messages.
- Async executors need proper context propagation; the current thread's MDC does not automatically copy to every thread.
- Always clear MDC/context after a request or task to avoid leaking data across requests in thread pools.

Never trust a client-supplied correlation ID as an identity or access credential. It is only a correlation key, not an authentication token.

## 14. SQL Logs Are Not Business Audits

SQL logs are valuable for investigating:

- Which queries ran?
- How long did they take?
- Is there an N+1 problem?
- Which bind types/parameters caused an error?
- Where did a transaction roll back?

Yet SQL logs are not business history because:

- They can be disabled, sampled, or rotated.
- They may lack actor or business reason.
- An UPDATE statement does not explain what business action occurred.
- Parameters may be masked or omitted.
- Logs can contain sensitive data.
- They provide no long-term retention or tamper resistance guarantees.
- A rolled-back transaction still emits SQL logs as if statements executed.

Seeing UPDATE status='APPROVED' in a log does not prove the transaction committed. Only audit records/outbox entries written in the same transaction represent a committed business change. To record failed attempts as well, use a separate event type distinguishing attempted from committed actions.

## 15. Write Paths That Bypass Auditing and Event Callbacks

A system may have multiple persistence paths:

~~~text
Spring Data JDBC repository
  └── Entity callbacks + auditing + repository events

JdbcTemplate / NamedParameterJdbcTemplate
  └── Direct SQL

MyBatis mapper
  └── SQL via MyBatis-Spring

Batch/ETL/Stored procedures
  └── Database-side writes

External applications
  └── Other writers
~~~

Direct SQL paths do not automatically go through Spring Data JDBC entity callbacks. Consequently:

- last_modified_by may remain unchanged.
- last_modified_at may retain an old value.
- EntityCallbacks/lifecycle events are not fired.
- Domain events are not created automatically.
- Application caches may become stale.
- Version columns may not increment unless SQL handles them explicitly.
- Business audit rows may not be inserted.

### Designing Controlled Write Paths

Choose a clear rule per aggregate/table:

1. Route all writes through an application service enforcing permissions, invariants, and audits.
2. Restrict direct SQL to designated tables/read models with their own audit/version mechanisms.
3. If external writers are unavoidable, use database triggers/auditing mechanisms or integration contracts so every writer records metadata.
4. Add tests verifying every write path updates audit fields and history properly.
5. Monitor for rows missing expected actor/timestamp values.

Database triggers can cover more writers than application callbacks, yet triggers do not know the business actor unless the application passes session context securely. Never record the connection pool's shared database user as the end-user actor.

## 16. Protecting Logs and Audit Data

Audit records and logs can contain sensitive data. Design data minimization and access controls from the start.

### Never Write Sensitive Data to Logs

Avoid logging:

- Passwords, access tokens, refresh tokens, API keys.
- Session cookies, authorization headers.
- Payment card numbers or security codes.
- Full request/response bodies containing PII.
- Health data or unnecessary personal identifiers.
- SQL bind values containing confidential data.

To trace a record, prefer aggregate IDs or opaque correlation IDs rather than logging entire entities.

### Permissions and Retention

- Give the runtime app only necessary INSERT/SELECT audit permissions; restrict UPDATE/DELETE.
- Admin audit storage should have a dedicated role whose access is audited.
- Separate operational logs from business audit history.
- Define retention aligned with legal/policy requirements and processing purposes.
- Establish procedures to archive/delete/anonymize expired data.
- Protect backups, exports, and log sinks with the same rigor as primary data.
- Synchronize system clocks and use UTC timestamps.
- If tamper evidence is required, design immutable storage/hashing/signatures and key management procedures.

Never retain audit payloads indefinitely by default. Storing excessive personal data can create greater risk than traceability value.

## 17. Testing Auditing and Actor Context

Auditing must be tested with deterministic time and actors. Do not let tests depend on the system clock or leftover SecurityContext from other tests.

Example test configuration with a fixed Clock:

~~~java
@TestConfiguration
@EnableJdbcAuditing(
        auditorAwareRef = "testAuditorAware",
        dateTimeProviderRef = "testDateTimeProvider"
)
class TestAuditingConfiguration {

    @Bean
    AuditorAware<String> testAuditorAware() {
        return () -> Optional.of("test-user");
    }

    @Bean
    DateTimeProvider testDateTimeProvider() {
        Instant fixed = Instant.parse("2026-01-10T09:00:00Z");
        return () -> Optional.of(fixed);
    }
}
~~~

Repository test:

~~~java
@DataJdbcTest
@Import(TestAuditingConfiguration.class)
class PurchaseOrderAuditingTest {

    @Autowired PurchaseOrderRepository repository;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void fillsCreatedAndModifiedMetadataOnInsert() {
        PurchaseOrder saved = repository.save(new PurchaseOrder("DRAFT"));

        Map<String, Object> row = jdbcTemplate.queryForMap("""
                SELECT created_by, created_at,
                       last_modified_by, last_modified_at
                FROM purchase_order
                WHERE id = ?
                """, saved.getId());

        assertThat(row.get("created_by")).isEqualTo("test-user");
        assertThat(row.get("last_modified_by")).isEqualTo("test-user");
    }
}
~~~

Adapt constructors, repositories, and schemas as needed. For insert/update tests, check both creation and subsequent updates, confirming created fields stay untouched while modified fields update according to rules.

### Testing Missing-Actor Cases

- Missing Authentication.
- Anonymous authentication.
- System/batch actors.
- Message consumers.
- Async threads lacking SecurityContext.
- AuditorAware returning Optional.empty.

If columns are NOT NULL, tests must verify either a system actor fallback or an intentional validation error. Never let production silently write nulls without alerting.

## 18. Testing Lifecycle, Direct SQL, and Rollback

A test suite should distinguish:

| Scenario | Expectation |
|---|---|
| Repository insert/update | Auditing metadata is populated |
| Repository save with callback | Callback executes at the right stage |
| JdbcTemplate UPDATE | Spring Data JDBC callbacks do not run automatically |
| MyBatis UPDATE | Spring Data JDBC callbacks do not run automatically |
| Transaction rollback | Aggregate and business audit/outbox roll back together |
| AFTER_COMMIT listener | Runs only when the transaction commits |
| Transaction rollback | AFTER_COMMIT listener does not run |
| Outbox relay publishes twice | Consumer deduplicates by event ID |
| Aggregate child update | Child auditing behavior verified explicitly |
| External writer | Database-level audit or integration contract records actor/source |

You can use @RecordApplicationEvents in Spring tests to observe application events when needed. For callbacks, test the callback directly or inspect entity/database side effects. For transaction phases, test commit and rollback through Spring proxies rather than calling listener methods directly.

## 19. Common Design Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| createdBy/lastModifiedBy always null | AuditorAware not configured or missing actor context | Check @EnableJdbcAuditing and actor source |
| Unexpected timestamps | App clock/timezone differs from DB clock | Standardize on Clock/UTC and check column types |
| Audit columns unchanged after MyBatis update | Direct SQL bypasses entity callbacks | Update metadata in mapper/service or use DB audits |
| Audit keeps only final state | Only LastModified fields used | Add an append-only business audit table |
| AfterSave listener sends message before rollback | Listener ran before commit | Use AFTER_COMMIT or a transactional outbox |
| Events lost after DB commit | Process crashed before publishing | Persist outbox rows in the same transaction |
| Events published twice | Relay crashed after publishing before marking published | Consumer idempotency/deduplication |
| Callbacks skipped on custom DML | DML bypassed aggregate persistence | Design explicit auditing for direct SQL |
| Audit actor is generic service user | End-user actor context not propagated | Propagate authenticated actor metadata |
| Logs contain tokens/PII | Request/SQL bind logging too detailed | Redact, allowlist fields, and enforce retention |
| Cannot trace requests across services | Missing correlation/trace context propagation | Propagate trace/correlation headers |
| Audit history modified | Broad UPDATE/DELETE privileges on table | Append-only permissions, separation of duties, tamper evidence |
| Callbacks contain domain rules | Persistence lifecycle used as business workflow | Move rules into aggregates/application services |

## 20. Business Traceability Design Workflow

1. **Define audit questions to answer:** actor, action, aggregate, before/after, reason, time, and correlation.
2. **Choose data mechanisms:** auditing columns, business audit tables, domain events, logs, or outbox.
3. **Identify all writers:** repositories, JdbcTemplate, MyBatis, batch jobs, triggers, and external services.
4. **Configure actor/time:** AuditorAware, Clock/DateTimeProvider, system actors, and UTC.
5. **Enable auditing:** @EnableJdbcAuditing and audit annotations on tracked entities.
6. **Define lifecycle hooks:** use callbacks/events for fitting technical logic, never replacing domain rules.
7. **Write business history:** insert append-only audit records in the same transaction as aggregates.
8. **Publish events reliably:** write outbox entries in the same transaction; keep relays and consumers idempotent.
9. **Structured logging/tracing:** correlationId, traceId, actor, aggregate ID, outcome, and duration.
10. **Protect data:** mask secrets/PII, enforce access controls, retention, backups, and tamper controls.
11. **Test every write path:** repositories, direct SQL, MyBatis, batch jobs, and external writers.
12. **Monitor operations:** missing actors, audit failures, outbox lag, duplicate deliveries, and log ingestion.

### Quick Decision Table

| Requirement | Appropriate mechanism |
|---|---|
| Know who last created/modified an entity | @CreatedBy/@CreatedDate/@LastModifiedBy/@LastModifiedDate |
| Normalize objects before persistence | EntityCallback |
| Observe persistence lifecycle within the app | Lifecycle events/ApplicationEvent |
| Record business actions and reasons | Append-only business audit |
| Link requests across services | Correlation ID and distributed traces |
| Investigate SQL/errors/latency | Structured application logs and SQL instrumentation |
| Send messages post-commit, best-effort acceptable | @TransactionalEventListener(AFTER_COMMIT) |
| Avoid losing critical post-commit events | Transactional outbox |
| Cover mutations from multiple writers | Database audit/triggers or shared write contract |
| Prevent tampering with audits | Append-only privileges, separation of duties, immutable storage/tamper evidence |

**Core point:** auditing columns capture who last created/modified an entity; callbacks and lifecycle events reflect persistence paths; logs/tracing support operations; business audit history records meaningful domain actions; outboxes ensure events are saved atomically in the transaction for reliable retries. Choose the right mechanism for each question, cover every write path, and test commits, rollbacks, actor context, direct SQL, and duplicate delivery.

## Official References

- [Spring Data Relational — Auditing](https://docs.spring.io/spring-data/relational/reference/jdbc/auditing.html): @EnableJdbcAuditing, AuditorAware, and audit metadata.
- [Spring Data Relational — Entity Callbacks](https://docs.spring.io/spring-data/relational/reference/jdbc/events.html): callbacks and lifecycle events in Spring Data Relational.
- [Spring Data Commons — Publishing Events from Aggregate Roots](https://docs.spring.io/spring-data/commons/reference/repositories/core-domain-events.html): @DomainEvents and @AfterDomainEventPublication.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): @TransactionalEventListener and transaction phases.
- [Spring Framework — Application Events and Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): ApplicationEventPublisher and listener infrastructure.
- [Spring Boot — Logging](https://docs.spring.io/spring-boot/reference/features/logging.html): configuring loggers, levels, and the logging system.
- [Spring Security — SecurityContext](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): Authentication and SecurityContextHolder.
- [OpenTelemetry — Context Propagation](https://opentelemetry.io/docs/concepts/context-propagation/): trace context across process and service boundaries.
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html): saving messages inside the same database transaction and relaying with retries.
