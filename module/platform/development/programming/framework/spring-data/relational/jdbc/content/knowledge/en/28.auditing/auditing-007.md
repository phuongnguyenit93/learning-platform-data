# Distinguishing Default Auditing from Full Change History

In Spring Data JDBC, default auditing records **who created an aggregate and who modified it most recently, and at what time**. Fields such as `createdBy`, `createdDate`, `lastModifiedBy`, and `lastModifiedDate` are updated alongside the entity through Spring Data's auditing infrastructure.

That information is useful for admin screens, basic accountability tracing, and operational support. However, it is not a full change history. When an entity is modified multiple times, `lastModifiedBy` and `lastModifiedDate` only describe the latest modification; previous values are replaced. Spring Data JDBC does not automatically create a record per modification, does not store before/after values of individual fields, and does not capture the reason for the change.

If business requirements need to answer questions such as "who changed the status from PENDING to APPROVED?", "what was the previous value?", "what changes occurred this month?", or "who deleted the record?", the application must design a separate history mechanism, such as an append-only audit table, database triggers, change data capture, or event sourcing.

This lesson distinguishes these two goals, shows how to enable auditing in Spring Data JDBC, and demonstrates how to persist full change history in the same transaction as business data.

## 1. What Does Default Auditing Record?

Spring Data provides annotations to store metadata about entity creation and modification times:

| Annotation | Information Recorded |
| --- | --- |
| `@CreatedBy` | User or principal who created the entity. |
| `@CreatedDate` | Timestamp when the entity was created. |
| `@LastModifiedBy` | User or principal who last modified the entity. |
| `@LastModifiedDate` | Timestamp when the entity was last modified. |

Annotations can be used selectively. If only creation and modification dates are needed, the application does not need to supply an `AuditorAware`. If recording the creator or modifier is required, the auditing infrastructure must know the current principal via `AuditorAware<T>`.

Example row after a few updates:

~~~text
id   name       created_by   created_at           last_modified_by   last_modified_at
---  ---------  -----------  -------------------  -----------------  -------------------
42   Keyboard   user-101     2026-10-01T08:00Z     user-205           2026-11-13T09:30Z
~~~

We know the record was created by `user-101` and last modified by `user-205`. From these columns alone, however, we do not know:

- Who modified the record on the 3rd, 8th, and 10th.
- What the product name was before each edit.
- When the status transitioned from ACTIVE to DISCONTINUED.
- Which values changed in each update.
- Why the user made the change.
- Whether a record was deleted, if deletions are not recorded separately.

That is the core limitation: **default auditing keeps current metadata, not a sequence of data versions**.

## 2. Enabling Auditing in Spring Data JDBC

To activate auditing, add `@EnableJdbcAuditing` to Spring configuration.

Example:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing
public class DataJdbcConfiguration {
}
~~~

If entities have `@CreatedDate` and `@LastModifiedDate` fields, this configuration is enough to enable assigning timestamps via the default date-time provider.

If recording creator/modifier is needed, register an `AuditorAware` bean:

~~~java
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(auditorAwareRef = "auditorAware")
public class DataJdbcConfiguration {

    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system");
    }
}
~~~

The example above uses a fixed `system` principal to illustrate configuration. In real applications, the auditor must reflect the user or service account performing the operation. Do not use a single fixed value for all requests if accountability tracing is required.

### 2.1. Retrieving the Principal from Spring Security

If the application uses Spring Security, the principal name can be read from `SecurityContextHolder`:

~~~java
import java.util.Optional;

import org.springframework.data.domain.AuditorAware;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class SpringSecurityAuditorAware
        implements AuditorAware<String> {

    @Override
    public Optional<String> getCurrentAuditor() {
        return Optional.ofNullable(
                    SecurityContextHolder.getContext().getAuthentication()
                )
                .filter(Authentication::isAuthenticated)
                .filter(authentication ->
                        !(authentication instanceof AnonymousAuthenticationToken))
                .map(Authentication::getName);
    }
}
~~~

When there is only one `AuditorAware` bean in the application context, the auditing infrastructure can auto-detect that bean. If there are multiple beans, use `auditorAwareRef` on `@EnableJdbcAuditing` to specify which bean to use.

`AuditorAware<T>` must return a type compatible with the properties annotated with `@CreatedBy` and `@LastModifiedBy`. If those fields are `String`, use `AuditorAware<String>`; if storing a domain user type, use the corresponding type.

### 2.2. Requests Without an Interactive User

Not every operation comes from a logged-in user. Examples:

- Scheduled jobs updating data.
- Workers processing messages.
- Import processes.
- Maintenance tasks.
- Cross-service data synchronization systems.

In those cases, define a meaningful actor such as `batch-import`, `inventory-sync`, or a specific service account. An application-managed context can supply the actor to `AuditorAware`.

Do not assign every operation lacking an `Authentication` to a dummy user without distinguishing the source. If auditing needs to explain the change origin, record `source` or `actorType` in audit events as well.

### 2.3. Customizing Time with DateTimeProvider

`@EnableJdbcAuditing` lets you specify `dateTimeProviderRef` to change the time source. This is useful when standardizing on UTC or injecting a `Clock` for testing.

Example:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.jdbc.repository.config.EnableJdbcAuditing;

@Configuration
@EnableJdbcAuditing(dateTimeProviderRef = "auditDateTimeProvider")
public class DataJdbcConfiguration {

    @Bean
    Clock auditClock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider auditDateTimeProvider(Clock auditClock) {
        return () -> Optional.of(Instant.now(auditClock));
    }
}
~~~

If `AuditorAware` is also needed, declare both `auditorAwareRef` and `dateTimeProviderRef` in the same auditing configuration.

In `@EnableJdbcAuditing` of Spring Data Relational 4.1.2:

- `setDates` defaults to `true`, meaning creation and modification dates are set.
- `modifyOnCreate` defaults to `true`, meaning an entity can be marked modified right at creation.
- `auditorAwareRef` selects the bean providing the principal.
- `dateTimeProviderRef` selects the bean providing the time.

These attributes configure current metadata on the entity; they do not turn auditing into a version history mechanism.

## 3. Declaring Auditing Metadata on an Aggregate

Example `Customer` aggregate:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.CreatedBy;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;

    @CreatedBy
    private String createdBy;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedBy
    private String lastModifiedBy;

    @LastModifiedDate
    private Instant lastModifiedAt;

    @Version
    private Long version;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public void rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer name is required"
            );
        }
        this.name = newName;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCreatedBy() {
        return createdBy;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public String getLastModifiedBy() {
        return lastModifiedBy;
    }

    public Instant getLastModifiedAt() {
        return lastModifiedAt;
    }

    public Long getVersion() {
        return version;
    }
}
~~~

The schema could be:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    created_by VARCHAR(150),
    created_at TIMESTAMP WITH TIME ZONE,
    last_modified_by VARCHAR(150),
    last_modified_at TIMESTAMP WITH TIME ZONE,
    version BIGINT NOT NULL
);
~~~

When creating and updating a customer through Spring Data JDBC, the auditing infrastructure populates the corresponding metadata. For example:

| Point in Time | createdBy | createdAt | lastModifiedBy | lastModifiedAt |
| --- | --- | --- | --- | --- |
| After insert | user-101 | 08:00 | user-101 | 08:00 |
| After edit 1 | user-101 | 08:00 | user-205 | 09:00 |
| After edit 2 | user-101 | 08:00 | user-310 | 10:30 |

`createdBy` and `createdAt` retain the initial information. `lastModifiedBy` and `lastModifiedAt` reflect the most recent modification. `user-205` and the 09:00 timestamp are no longer stored in the current columns after the second edit.

### 3.1. @Version Is Not Audit History

The example above also includes `@Version`. The two groups of fields serve different purposes:

| Field | Purpose |
| --- | --- |
| `@CreatedBy`, `@CreatedDate` | Entity creation metadata. |
| `@LastModifiedBy`, `@LastModifiedDate` | Last modification metadata. |
| `@Version` | Detecting concurrent updates via optimistic locking. |

The version may increment on each update, but there is only one current version number on the aggregate. It does not automatically create records for prior versions and does not save snapshots of earlier data.

If the database simply shows `version = 7`, we know the aggregate went through updates under the versioning mechanism, but we cannot reconstruct the contents of versions 1 through 6 unless they are stored elsewhere.

### 3.2. Auditing Does Not Automatically Generate Diffs

Default auditing does not compare individual fields to generate a record like:

~~~text
name:   "Keyboard" -> "Mechanical Keyboard"
price:  100.00     -> 120.00
status: "DRAFT"    -> "ACTIVE"
~~~

It only updates the declared auditing fields. If diffs are needed, the application must capture before/after state itself, use a database-level history mechanism, or store domain events representing the changes.

## 4. Comparing Default Auditing and Full Change History

| Capability | Default Auditing | Full Change History |
| --- | --- | --- |
| Who created the record | Yes, via `@CreatedBy` | Can be recorded in events |
| When it was created | Yes, via `@CreatedDate` | Can be recorded in events |
| Who last modified it | Yes, via `@LastModifiedBy` | Yes |
| When it was last modified | Yes, via `@LastModifiedDate` | Yes |
| Previous modifications | No | Yes |
| Before/after values | No | Yes if designed to store them |
| Which fields changed | Not recorded automatically | Can store diffs |
| Reason for change | Not recorded automatically | Can be stored |
| Correlation/request ID | Not recorded automatically | Can be stored |
| Deletion history | Not created automatically | Can record delete events/tombstones |
| Restoring previous state | No | Possible if snapshots or sufficient event data are stored |

A system can use both at the same time:

- Auditing metadata to quickly query who created and last modified a record.
- An audit event table to look up the complete change history.

You do not have to choose only one if the application has both current-metadata display needs and detailed auditing requirements.

## 5. Designing Audit History with an Append-Only Table

A common way to store full history is creating a separate audit table. On each business change, the application inserts a new row instead of overwriting previous history rows.

Example:

~~~text
customers
---------
id = 42
name = "Mechanical Keyboard"
status = "ACTIVE"

customer_audit_events
---------------------
event 1: CUSTOMER_CREATED
event 2: CUSTOMER_NAME_CHANGED
event 3: CUSTOMER_STATUS_CHANGED
event 4: CUSTOMER_PRICE_CHANGED
~~~

An audit event can contain:

- Aggregate type and ID.
- Action or event type.
- Performing actor.
- Timestamp when it occurred.
- Version after the change.
- Old and new values or a diff payload.
- Reason for change.
- Correlation ID / request ID.
- Source performing the change.
- Payload schema version.

### 5.1. Audit Table Schema

Example using a `TEXT` column to store a JSON payload relatively simply without depending directly on a specific database's native JSON type:

~~~sql
CREATE TABLE customer_audit_events (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(80) NOT NULL,
    actor_id VARCHAR(150) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    aggregate_version BIGINT,
    reason VARCHAR(1000),
    correlation_id VARCHAR(150),
    changes_json TEXT NOT NULL,
    schema_version INTEGER NOT NULL
);

CREATE INDEX idx_customer_audit_aggregate_time
    ON customer_audit_events(
        aggregate_type,
        aggregate_id,
        occurred_at,
        id
    );

CREATE INDEX idx_customer_audit_correlation
    ON customer_audit_events(correlation_id);
~~~

You do not necessarily need a separate table per aggregate type. You can use a shared table with `aggregate_type` and `aggregate_id`, or split tables by domain when query patterns, retention, and access permissions differ.

If considering a foreign key from audit rows back to the aggregate, keep in mind that history often needs to outlive deletion of the aggregate. A cascading-delete foreign key would wipe out history and defeat the audit's purpose. Many systems keep `aggregate_id` as a logical reference without cascading on the aggregate's lifecycle.

### 5.2. Audit Events Are Immutable Records

An audit table should be designed as append-only:

- Each change creates a new event.
- Do not edit old events to reflect new state.
- Do not delete history merely because the aggregate was deleted.
- Restrict UPDATE/DELETE privileges on the audit table.
- Have retention, backup, and access-control policies.
- Optionally add checksums or tamper-evident mechanisms if compliance requires proving integrity.

`CrudRepository` exposes both update and delete operations, so naming a table `audit_events` does not by itself enforce append-only behavior. You can restrict the repository interface to expose only insert/read methods while also using database permissions to prevent the application account from modifying or deleting history.

## 6. Saving Audit Events in the Same Transaction as Business Changes

If audit history is a mandatory part of business data, updating the aggregate and inserting the audit event should execute within the same database transaction.

Example event model:

~~~java
import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer_audit_events")
public record CustomerAuditEvent(
        @Id Long id,
        String aggregateType,
        Long aggregateId,
        String eventType,
        String actorId,
        Instant occurredAt,
        Long aggregateVersion,
        String reason,
        String correlationId,
        String changesJson,
        Integer schemaVersion
) {
}
~~~

Repository exposing only the required operations:

~~~java
import java.util.List;

import org.springframework.data.repository.Repository;

public interface CustomerAuditEventRepository
        extends Repository<CustomerAuditEvent, Long> {

    <S extends CustomerAuditEvent> S save(S event);

    List<CustomerAuditEvent>
    findByAggregateTypeAndAggregateIdOrderByOccurredAtAscIdAsc(
            String aggregateType,
            Long aggregateId
    );
}
~~~

Service updating the customer and writing the event:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Map;
import java.util.Objects;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.domain.AuditorAware;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerCommandService {

    private final CustomerRepository customerRepository;
    private final CustomerAuditEventRepository auditRepository;
    private final AuditorAware<String> auditorAware;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    public CustomerCommandService(
            CustomerRepository customerRepository,
            CustomerAuditEventRepository auditRepository,
            AuditorAware<String> auditorAware,
            ObjectMapper objectMapper,
            Clock clock
    ) {
        this.customerRepository = customerRepository;
        this.auditRepository = auditRepository;
        this.auditorAware = auditorAware;
        this.objectMapper = objectMapper;
        this.clock = clock;
    }

    @Transactional
    public Customer rename(
            Long customerId,
            String newName,
            String reason,
            String correlationId
    ) {
        Customer customer = customerRepository.findById(customerId)
                .orElseThrow();

        String oldName = customer.getName();

        customer.rename(newName);

        Customer saved = customerRepository.save(customer);

        if (!Objects.equals(oldName, saved.getName())) {
            String actor = auditorAware.getCurrentAuditor()
                    .orElseThrow(() ->
                            new IllegalStateException(
                                    "An audit actor is required"
                            )
                    );

            String changes = toJson(Map.of(
                    "name", Map.of(
                            "old", oldName,
                            "new", saved.getName()
                    )
            ));

            auditRepository.save(new CustomerAuditEvent(
                    null,
                    "Customer",
                    saved.getId(),
                    "CUSTOMER_NAME_CHANGED",
                    actor,
                    Instant.now(clock),
                    saved.getVersion(),
                    reason,
                    correlationId,
                    changes,
                    1
            ));
        }

        return saved;
    }

    private String toJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException exception) {
            throw new IllegalStateException(
                    "Cannot serialize audit changes",
                    exception
            );
        }
    }
}
~~~

In this example:

1. The service loads the customer state prior to modification.
2. Captures the old `name` value.
3. Executes domain behavior and saves the aggregate.
4. Compares before/after values.
5. Creates an audit event if an actual change occurred.
6. Writes the event to the audit table within the same transaction.

Both repositories must share the same DataSource and transaction manager to participate in the same transaction. If inserting the audit event fails, the transaction rolls back the customer update as well. This is appropriate when business changes must never occur without a corresponding audit record.

In a real application, the actor should come from a trusted server-side context. Never use an arbitrary client-supplied `actorId` as the audit identity. `reason` and `correlationId` may come from the request after validation, while the actor identity must be authenticated.

### 6.1. Why Is a Shared Transaction Needed?

If the customer update commits first and the audit event is written in a separate transaction, an audit write failure can leave:

~~~text
customers:
  name = "New name"       COMMITTED

customer_audit_events:
  no corresponding event
~~~

Business data changed while history is missing.

When both operations run inside one transaction:

~~~text
BEGIN
  UPDATE customers
  INSERT customer_audit_events
COMMIT
~~~

If either operation fails, the database rolls back both. This preserves consistency between current state and mandatory history.

### 6.2. Audit Events and Transactional Outbox Differ

An audit event records what happened in the business domain for querying and auditing. An outbox records messages that must be delivered reliably to other systems after commit.

Both kinds of data can be created within the same transaction, yet they are not synonymous:

- Audit history serves historical querying and explaining changes.
- An outbox serves event delivery to a message broker or external systems.
- An audit event is not automatically published reliably to a message broker.
- An outbox message does not necessarily contain full audit data required for long-term retention.

If both are needed, you can insert an audit row and an outbox row in the same transaction as the aggregate update, then have a worker publish the outbox.

## 7. Storing Diffs or Storing Snapshots?

There are two common strategies for history payloads.

### 7.1. Field-Level Diff

Store only changed fields:

~~~json
{
  "name": {
    "old": "Keyboard",
    "new": "Mechanical Keyboard"
  },
  "status": {
    "old": "DRAFT",
    "new": "ACTIVE"
  }
}
~~~

Advantages:

- Easy to read and display changes.
- Per-event payloads are typically small.
- Can search changes by field if the structure is standardized.

Limitations:

- Must detect and serialize changed fields manually.
- Harder to reconstruct full state if an event is missing.
- Must handle field renames, schema evolution, and payload migrations.
- For complex objects, diffs can be hard to interpret.

### 7.2. Before/After Snapshots

Store the full before and after state:

~~~json
{
  "before": {
    "name": "Keyboard",
    "status": "DRAFT",
    "price": 100.00
  },
  "after": {
    "name": "Mechanical Keyboard",
    "status": "ACTIVE",
    "price": 120.00
  }
}
~~~

Advantages:

- Easy to inspect state at a point in time.
- Can reconstruct a specific version from a snapshot.
- No need to replay multiple diffs to understand the entire entity.

Limitations:

- Uses more storage.
- May store unnecessary sensitive data.
- Snapshot schema versioning is required.
- Retention and masking policies are needed.

### 7.3. Combining Periodic Snapshots and Diffs

For very long histories, you can store periodic snapshots along with events/diffs between snapshots. When reconstructing state at a point in time, the system fetches the nearest snapshot and applies subsequent changes.

This reduces the number of events to replay, at the cost of increased complexity. Only use it when historical query or state reconstruction demands it.

## 8. Recording Delete Operations

`@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy` do not automatically create a complete deletion history. When an aggregate is deleted, the row holding that metadata may also be deleted.

If deletion history is required, record the action explicitly before or together with the delete operation.

Service example:

~~~java
@Transactional
public void deleteCustomer(
        Long customerId,
        String reason,
        String correlationId
) {
    Customer customer = customerRepository.findById(customerId)
            .orElseThrow();

    String actor = auditorAware.getCurrentAuditor()
            .orElseThrow();

    auditRepository.save(new CustomerAuditEvent(
            null,
            "Customer",
            customer.getId(),
            "CUSTOMER_DELETED",
            actor,
            Instant.now(clock),
            customer.getVersion(),
            reason,
            correlationId,
            toJson(Map.of(
                    "name", customer.getName()
            )),
            1
    ));

    customerRepository.delete(customer);
}
~~~

The audit event and the delete operation must share the same transaction. If deleting fails, the delete audit event also rolls back; if the event fails to save, the deletion does not commit.

If the application needs to keep current data after a user "deletes" it, soft delete can be used with `deletedAt`, `deletedBy`, and a status field. Still, soft delete only holds current state metadata; if a history of multiple delete/restore cycles is needed, audit events are still required.

## 9. Other Approaches to Storing History

An audit table in an application service is not the only option. The choice depends on the scope of data to track and which writers must be covered.

### 9.1. Application-Level Audit Table

A service or domain handler creates an audit event while executing a use case.

Suitable when:

- Actor, reason, command ID, or correlation ID are required.
- You want to record business semantics such as `ORDER_APPROVED`, not just SQL UPDATEs.
- Shared transactions with aggregates are required.
- All write paths can be controlled through the application.

Limitation: if another program writes directly to the database bypassing the service, it may fail to create an audit event.

### 9.2. Database Triggers

Triggers fire when the database receives an INSERT, UPDATE, or DELETE on a tracked table.

Suitable when:

- Changes from multiple applications or writers must be captured.
- You want the database to automatically record old/new rows.
- Audit history must be protected even against direct SQL operations.

Limitations:

- Syntax and behavior vary across databases.
- Triggers can be difficult to test and deploy via migrations.
- The database knows the session/database user, not the application's business principal unless the application passes context down.
- Triggers recording row-level changes may not understand domain intent or change reasons.

### 9.3. Change Data Capture (CDC)

CDC reads the database's transaction log or change stream to detect committed changes.

Suitable when:

- Tracking changes across multiple writers is needed.
- Propagating data changes to a data warehouse, search index, or downstream systems.
- Asynchronous processing is desired without adding audit logic to each service.

Limitations:

- CDC typically captures table/row-level data changes without understanding business commands.
- Actor, reason, and correlation ID do not appear automatically unless stored alongside the data or context.
- Requires operating connectors, offsets, retries, schema evolution, and transaction log retention.
- CDC is an asynchronous stream; it does not replace a use case's transaction boundary.

### 9.4. Event Sourcing

In event sourcing, events are the primary source of truth defining aggregate state. Current state is derived by applying a sequence of events.

Example:

~~~text
CustomerRegistered
CustomerNameChanged
CustomerEmailChanged
CustomerDeactivated
~~~

Suitable when:

- Change history is a core part of the domain.
- Reconstructing state at past points in time is required.
- Understanding how current state emerged is essential.
- The domain has a clear event model.

Event sourcing is a major architectural choice, not merely adding an audit table to Spring Data JDBC. The application must handle event versioning, replay, snapshots, idempotency, eventual consistency, and event migration workflows.

### 9.5. Do Not Confuse Spring Data JDBC Auditing with Hibernate Envers

Hibernate Envers is an auditing solution built for Hibernate/JPA. Spring Data JDBC does not use a Hibernate persistence context and does not provide Envers as a default auditing feature.

If a project uses Spring Data JDBC, design an audit table, triggers, CDC, or event model suited to its JDBC infrastructure. Do not copy JPA Envers configuration expecting it to work with Spring Data JDBC.

## 10. When Is Default Auditing Enough?

Default auditing is usually sufficient if requirements are limited to:

- Displaying creation date and last updated date.
- Knowing who created and last modified a record.
- Supporting basic operational investigation.
- Sorting data by most recent modification.
- Tracking metadata on standard business tables.

Example customer list screen:

~~~text
Customer            Created             Last modified by   Last modified
------------------  ------------------  -----------------  ------------------
Nguyen An           2026-10-01 08:00    user-205           2026-11-13 09:30
Tran Binh           2026-10-04 10:15    user-101           2026-11-12 16:20
Le Chi              2026-10-08 14:00    system             2026-11-10 02:00
~~~

This screen only needs current state and metadata of the most recent modification. No table storing every revision is needed.

Do not add full history merely because a system has `createdAt` or `updatedAt` fields. Identify the business questions to answer and the level of traceability required.

## 11. When Is Full Change History Needed?

Design full history when one or more of these requirements apply:

- Every change to a record must be known.
- Before and after field values must be viewable.
- Actor, timestamp, reason, and change source must be identified.
- Proving who approved or canceled a transaction is required.
- Investigating anomalous changes is necessary.
- Restoring old states or reconstructing data is needed.
- Regulatory, governance, or compliance requirements apply.
- Changes must be synchronized to downstream systems with traceability.

Example order status history:

| Timestamp | Actor | Old Status | New Status | Reason |
| --- | --- | --- | --- | --- |
| 08:00 | customer-12 | — | DRAFT | Order created |
| 08:05 | user-45 | DRAFT | CONFIRMED | Order confirmed |
| 08:20 | warehouse-2 | CONFIRMED | PICKING | Picking started |
| 09:10 | user-45 | PICKING | CANCELLED | Customer requested cancellation |

`lastModifiedBy` and `lastModifiedAt` on the order only reflect the last row. A history table answers the entire state-transition sequence.

## 12. Design Concerns for Audit History

An audit table containing only `id`, `actor`, and `timestamp` is often insufficient when investigating changes.

Decide on the following fields:

| Field | Question Answered |
| --- | --- |
| `aggregateType` | What type of object changed? |
| `aggregateId` | Which specific object? |
| `eventType` | What action occurred? |
| `actorId` | Which person or service performed it? |
| `occurredAt` | When did it happen? |
| `aggregateVersion` | Which version does the change belong to? |
| `changesJson` | Which fields changed, and from what value to what value? |
| `reason` | Why was the change made? |
| `correlationId` | Which request or workflow caused the change? |
| `source` | UI, API, batch, worker, or integration system? |
| `schemaVersion` | Under which schema was the payload serialized? |

### 12.1. Time and Event Ordering

Timestamps can collide, especially when multiple events are generated within a short interval. Therefore, include an auto-incrementing ID or sequence to establish deterministic ordering within the same aggregate.

`occurredAt` is when the application recorded the event. If exact commit ordering across multiple nodes or database-confirmed timestamps are required, design additional metadata accordingly; do not treat distributed application clocks as an absolute ordering source.

### 12.2. Sensitive Data and Access Control

Audit history can contain before/after values of personal data or secrets. Do not mechanically serialize entire entities.

You should:

- Store only fields needed for auditing purposes.
- Exclude passwords, tokens, secrets, and authentication credentials.
- Mask or hash data where appropriate.
- Restrict who can read audit history.
- Define retention and deletion schedules per legal policy.
- Protect the audit table from updates/deletes outside governed administrative workflows.
- Do not dump sensitive data into application logs as a substitute for an audit table.

Audit completeness does not mean storing every byte of data. Record only what is needed for the defined purpose.

## 13. Impact of Different Write Paths

Spring Data JDBC's default auditing operates within Spring Data's persistence flow. If the application writes data via another path, do not assume auditing callbacks are still invoked.

| Write Method | Default Auditing Metadata |
| --- | --- |
| `repository.save(aggregate)` | Applied according to auditing configuration. |
| `JdbcAggregateTemplate` via Spring Data JDBC | Passes through Spring Data JDBC infrastructure. |
| Direct `JdbcTemplate.update(...)` | Do not assume auditing callbacks are called. |
| SQL executed from external scripts | Does not invoke Spring auditing callbacks. |
| Another service writing directly to DB | Does not automatically update auditing metadata without its own mechanism. |
| Database trigger | Can record history at the database level if configured. |

If multiple applications or batch jobs write to the same table, relying solely on `@LastModifiedBy` in one service may be insufficient. Consider triggers or CDC to capture all database changes, or require all writers to go through a unified write API.

## 14. Testing Default Auditing

An integration test can confirm metadata is populated after insert and update.

Example test scaffold with a fixed test `AuditorAware`:

~~~java
@TestConfiguration
@EnableJdbcAuditing(auditorAwareRef = "testAuditor")
class TestAuditingConfiguration {

    @Bean
    AuditorAware<String> testAuditor() {
        return () -> Optional.of("test-user");
    }
}
~~~

Test:

~~~java
@SpringBootTest
class CustomerAuditingTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void recordsCreationAndLastModificationMetadata() {
        Customer created = repository.save(
                new Customer("Nguyen An")
        );

        assertEquals("test-user", created.getCreatedBy());
        assertEquals("test-user", created.getLastModifiedBy());
        assertNotNull(created.getCreatedAt());
        assertNotNull(created.getLastModifiedAt());

        Customer loaded = repository.findById(created.getId())
                .orElseThrow();

        loaded.rename("Nguyen An Updated");

        Customer updated = repository.save(loaded);

        assertEquals("test-user", updated.getCreatedBy());
        assertEquals("test-user", updated.getLastModifiedBy());
        assertNotNull(updated.getLastModifiedAt());
    }
}
~~~

In real tests, you can vary the auditor per step to confirm `createdBy` retains the original actor and `lastModifiedBy` switches to the new actor.

### 14.1. Testing Full History

For an audit event table, also verify:

1. Inserting an aggregate creates the right `CREATED` event.
2. Updating a field creates an `UPDATED` event with old/new values.
3. No actual change either creates or omits an event according to the chosen policy.
4. If inserting the audit event fails, the aggregate update also rolls back.
5. Deleting creates a `DELETED` event and the history remains intact.
6. Multiple consecutive changes preserve proper ordering.
7. Actor, reason, and correlation ID are populated from the proper context.
8. Payloads do not contain sensitive data.

Transaction rollback tests require database integration tests; mocking repositories does not prove that both operations actually commit or roll back together.

## 15. Common Misconceptions

**"@LastModifiedDate stores every modification."** No. It only keeps the most recent modification timestamp on the current row.

**"@CreatedBy and @LastModifiedBy create a history table."** No. They write metadata onto the mapped entity.

**"@Version is version history."** No. Version is for detecting concurrent updates; it does not store snapshots of previous versions.

**"Default auditing records which fields changed."** No. It does not automatically generate per-field diffs or store old/new values.

**"Simply enabling @EnableJdbcAuditing identifies the current user."** No. If `@CreatedBy` or `@LastModifiedBy` is needed, a suitable `AuditorAware` must be provided.

**"Without AuditorAware, auditing cannot be used."** False. If only recording creation/modification dates, date auditing can be used without an auditor provider.

**"Delete also preserves created/modified metadata automatically."** No. When a row is deleted, metadata on that row disappears too; a delete event, soft delete, trigger, or separate history mechanism is needed.

**"JdbcTemplate.update also runs auditing callbacks automatically."** Do not assume that. Direct SQL bypasses Spring Data JDBC's entity auditing pipeline.

**"Writing audit events after commit is always safe."** No, if events are mandatory data. The process may crash after the aggregate commits but before writing the event. Write the audit row in the same transaction, or use an outbox if dispatching events externally.

**"Audit events and outbox are the same thing."** No. Auditing serves history/compliance; an outbox serves reliable message delivery.

**"Saving the entire JSON object into the audit table is always better."** No. It can store excessive sensitive data, bloat payloads, and complicate schema compatibility. Choose diffs or snapshots based on requirements.

**"Storing only actor and timestamp is enough."** Not if you need to know which fields changed, old/new values, reason, and change source.

**"Old audit rows can be edited to reflect new data."** That violates append-only semantics. Each change should create a new event; correcting historical mistakes requires an adjustment event and a governed administrative process.

**"Hibernate Envers works directly with Spring Data JDBC."** No. Envers is tied to Hibernate/JPA; Spring Data JDBC needs a JDBC-compatible auditing mechanism.

## 16. Decision Process

When designing auditing for an aggregate, identify the questions to answer:

1. **Only need who created and who last modified?** Use `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate`.
2. **Need to know who performed the action?** Configure `AuditorAware<T>` and a trusted principal.
3. **Need consistent time?** Use an appropriate `DateTimeProvider` and `Clock`, typically standardized on UTC.
4. **Need a history of every change?** Design an append-only audit event or version table.
5. **Need old/new values?** Store field-level diffs or before/after snapshots.
6. **Need to record deletions?** Create delete events, soft delete, or database-level history.
7. **Are there multiple writers outside Spring Data JDBC?** Consider database triggers or CDC.
8. **Need to sync events to external systems?** Use a transactional outbox or reliable publishing mechanism.
9. **Need to reconstruct state from events?** Evaluate event sourcing as a dedicated architectural decision.
10. **Is auditing mandatory alongside business data?** Write audit rows in the same transaction and same resource.
11. **Is there sensitive data?** Limit payloads, read permissions, and retention.
12. **Have rollback and delete history been tested?** Confirm audits are not missing when a persistence step fails.

~~~mermaid
flowchart TD
    A["Need to track data"] --> B{"Only need creator/last modifier and timestamps?"}
    B -->|Yes| C["Spring Data JDBC Auditing"]
    C --> D["@CreatedBy / @CreatedDate<br/>@LastModifiedBy / @LastModifiedDate"]
    B -->|No, need all changes| E{"Need old/new values and business actor?"}
    E -->|Yes| F["Append-only audit event table"]
    E -->|No, need to capture all SQL writers| G["Database trigger or CDC"]
    F --> H{"Need to publish to external systems?"}
    H -->|Yes| I["Write outbox in same transaction"]
    H -->|No| J["Query audit history"]
    G --> J
    D --> K["Store current metadata"]
    I --> L["Worker publishes after commit"]
~~~

## 17. Practice Exercises

Create a `Customer` aggregate with fields `id`, `name`, `createdBy`, `createdAt`, `lastModifiedBy`, `lastModifiedAt`, and `version`.

### Exercise 1: Enable Default Auditing

1. Add `@EnableJdbcAuditing`.
2. Register `AuditorAware<String>`.
3. Mark the four auditing fields with the corresponding annotations.
4. Save a new customer.
5. Verify creation and modification metadata are populated.

### Exercise 2: Observe Most Recent Modification

1. Create a customer using actor `user-101`.
2. Rename using actor `user-205`.
3. Update status using actor `user-310`.
4. Reload the customer.
5. Verify `createdBy` is still `user-101` and `lastModifiedBy` is `user-310`.
6. Explain why you cannot tell which field `user-205` edited from the auditing columns alone.

### Exercise 3: Create an Audit Event Table

1. Create the `customer_audit_events` table.
2. Create an audit event aggregate with actor, action, timestamp, version, and changes payload.
3. Create a repository exposing only the required insert/read methods.
4. Update the customer and insert an event in the same `@Transactional` method.
5. Query history by aggregate ID.

### Exercise 4: Test Rollback

1. Create a customer update operation.
2. Cause the audit event insert to fail using a reproducible constraint violation.
3. Verify the customer change also rolls back.
4. Try removing the shared transaction and observe the risk of business data changing without an audit event.

### Exercise 5: Record Deletions

1. Create a delete event prior to deleting the aggregate.
2. Delete the customer in the same transaction.
3. Verify the customer row disappears while the audit event remains.
4. Try designing soft delete and compare it against delete events.

### Exercise 6: Compare Approaches

1. Create a database trigger recording old/new values on update.
2. Compare the trigger with service-written audit events.
3. Identify which actors the trigger can know and which actors must be passed via session context.
4. Evaluate CDC when there are multiple writers.
5. Determine when event sourcing would or would not fit the domain.

## 18. Key Takeaways

- Default auditing in Spring Data JDBC records creation and modification metadata on the current entity state.
- `@CreatedBy` and `@CreatedDate` record who created the entity and when.
- `@LastModifiedBy` and `@LastModifiedDate` only record who last modified the entity and when.
- `@EnableJdbcAuditing` activates auditing; `AuditorAware<T>` provides the principal when recording actors is needed.
- `DateTimeProvider` provides control over the time source; standardize time storage, typically using UTC.
- `@Version` serves optimistic locking, not a history table.
- Default auditing does not produce diffs, store old/new values, record reasons, or automatically preserve deletion history.
- Full history requires an append-only audit table, version table, database trigger, CDC, or event sourcing depending on requirements.
- If audit rows must accompany aggregate changes, write both in the same transaction using the same DataSource/transaction manager.
- Audit events and outboxes serve different goals; they can share a transaction but do not replace each other.
- Payload design must balance traceability, storage size, schema evolution, access control, and sensitive-data protection.
- If multiple writers exist, ensure every write path is tracked or use a database-level mechanism.

**Default auditing answers "who created and who last modified it, and when"; full change history answers "what changed each time, by whom, and why".** Choose the mechanism based on the business questions to answer. When both current metadata and an audit trail are needed, combine auditing annotations with an append-only audit event store.

## References

- [Spring Data Relational 4.1.2 — Auditing](https://www.springframework.org/spring-data/relational/reference/jdbc/auditing.html)
- [Spring Data Relational 4.1.2 — EnableJdbcAuditing API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/repository/config/EnableJdbcAuditing.html)
- [Spring Data Commons 4.1.2 — Auditing Infrastructure](https://docs.spring.io/spring-data/commons/reference/auditing.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
