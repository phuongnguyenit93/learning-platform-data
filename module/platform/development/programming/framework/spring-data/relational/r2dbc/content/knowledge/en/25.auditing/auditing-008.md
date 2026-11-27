# Auditing Limitations When Updating Directly with SQL

Spring Data R2DBC supports auditing to record the creator, creation timestamp, modifier, and modification timestamp of an entity. This mechanism works through auditing metadata and entity callbacks within Spring Data's entity save pipeline.

When an application updates data directly with SQL—such as a repository method with @Modifying @Query, DatabaseClient, or R2dbcEntityTemplate.update(Query, Update)—the operation typically does not go through the same full-entity save pipeline. Consequently, @LastModifiedDate and @LastModifiedBy annotations are not automatically applied simply because a SQL statement modified rows.

If the SQL statement does not update the audit columns and the database has no trigger handling them, business data can change while last_modified_at and last_modified_by retain stale values. To keep auditing consistent, explicitly update audit columns in the SQL statement, use a database trigger with clear conventions, or route the operation through an entity save path when appropriate.

## 1. How does auditing work in Spring Data R2DBC?

Auditing records entity lifecycle metadata. Commonly used annotations:

| Annotation | Meaning |
| --- | --- |
| @CreatedDate | Timestamp when the entity was created |
| @CreatedBy | Person or actor that created the entity |
| @LastModifiedDate | Timestamp when the entity was most recently modified |
| @LastModifiedBy | Person or actor that most recently modified the entity |

Entity example:

~~~java
@Table("customers")
public class Customer {

    @Id
    private Long id;

    private String name;
    private String status;

    @CreatedDate
    @Column("created_at")
    private Instant createdAt;

    @CreatedBy
    @Column("created_by")
    private String createdBy;

    @LastModifiedDate
    @Column("last_modified_at")
    private Instant lastModifiedAt;

    @LastModifiedBy
    @Column("last_modified_by")
    private String lastModifiedBy;

    // Constructors, getters, and setters omitted.
}
~~~

When an entity is saved through Spring Data R2DBC's entity processing path, auditing callbacks can populate the corresponding fields:

- When creating a new entity, createdAt and createdBy are set; lastModifiedAt and lastModifiedBy are also typically set on the initial write.
- When updating an existing entity, last-modified fields are updated.
- Created fields represent the initial creation time and actor, so they remain unchanged during normal edits.

Exact values depend on auditing configuration, entity type, callbacks, and the Spring Data version in use.

### 1.1. Enabling R2DBC auditing

Declare the configuration:

~~~java
@Configuration
@EnableR2dbcAuditing(
        auditorAwareRef = "auditorAware",
        dateTimeProviderRef = "dateTimeProvider"
)
public class R2dbcAuditingConfiguration {

    @Bean
    ReactiveAuditorAware<String> auditorAware() {
        return () -> ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .filter(Authentication::isAuthenticated)
                .map(Authentication::getName);
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    DateTimeProvider dateTimeProvider(Clock clock) {
        return () -> Optional.of(Instant.now(clock));
    }
}
~~~

ReactiveAuditorAware<T> allows retrieving the current actor via a reactive publisher. In this example, the actor is retrieved from the reactive security context. If the application does not use Spring Security, the provider can be implemented from a request context, message context, or another actor source.

DateTimeProvider supplies the time for auditing. Injecting Clock helps standardize the application's time source and simplifies testing.

Key imports:

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.Optional;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.auditing.DateTimeProvider;
import org.springframework.data.domain.ReactiveAuditorAware;
import org.springframework.data.r2dbc.config.EnableR2dbcAuditing;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
~~~

In production code, explicitly handle cases where no authentication is present. You can return Mono.empty() if the actor is unknown, use a system actor for background jobs, or reject the operation if business rules require an actor. Do not take createdBy/lastModifiedBy directly from client-submitted request bodies without authentication.

### 1.2. Auditing is invoked via entity callbacks

Spring Data Relational integrates auditing using entity callbacks. Auditing callbacks typically run before the entity is converted into storage data, reading annotation metadata and populating the corresponding properties.

The key point is that callbacks require an entity passing through a callback-aware save workflow. Class annotations only describe metadata; they are not database triggers and do not automatically monitor every SQL statement executed against the table.

Therefore, distinguish between:

- Saving an entity via a repository or an entity-oriented template operation: Spring Data has an entity to run mapping and callbacks on.
- Updating a set of columns via SQL or a query/update builder: the application only supplies a statement and parameters, with no full entity for auditing callbacks to update.

## 2. Why do direct SQL updates not automatically run auditing?

Consider a modifying query:

~~~java
@Modifying
@Query("UPDATE customers SET status = :status WHERE id = :id")
Mono<Integer> updateStatus(
        @Param("id") Long id,
        @Param("status") String status);
~~~

This method sends a SQL update statement to the database and returns the affected row count. Spring Data does not need to instantiate a full Customer to execute the statement. Therefore, no corresponding entity passes through auditing callbacks to populate @LastModifiedDate or @LastModifiedBy.

If the table has these columns:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by VARCHAR(120),
    last_modified_at TIMESTAMP,
    last_modified_by VARCHAR(120)
);
~~~

then the update statement above changes only status. The last_modified_at and last_modified_by columns do not change automatically merely because the entity class carries those annotations.

### 2.1. Write paths that normally do not trigger entity auditing

| Write method | Does a full entity go through auditing callbacks? | Audit behavior |
| --- | --- | --- |
| Repository save(entity) | Yes, via the entity save workflow | Auditing can populate configured fields |
| Entity-oriented insert/save via template | Has an entity and goes through mapping/callbacks | Auditing can be applied |
| Repository @Modifying @Query | No | Must update audit columns explicitly or use a trigger |
| DatabaseClient.sql(...).fetch() | No | Must update audit columns explicitly or use a trigger |
| R2dbcEntityTemplate.update(Query, Update) | No entity to audit in partial update | Must add audit fields to Update or use a trigger |
| SQL executed directly outside the application | Bypasses Spring Data callbacks | Only database-side auditing can apply uniformly |

This table illustrates the difference between entity saves and direct DML statements. Check the exact API in your project's Spring Data R2DBC version if using a special overload that accepts an entity.

### 2.2. @Modifying does not mean automatic auditing

@Modifying marks a repository query as a data-modifying statement such as UPDATE or DELETE. This annotation does not tell Spring Data to load the entity, does not automatically call ReactiveAuditorAware, and does not automatically inject last_modified_at into the SQL.

Example:

~~~java
@Modifying
@Query("""
       UPDATE customers
       SET status = :status
       WHERE id = :id
       """)
Mono<Integer> updateStatus(
        @Param("id") Long id,
        @Param("status") String status);
~~~

To record audit metadata, expand the statement:

~~~java
@Modifying
@Query("""
       UPDATE customers
       SET status = :status,
           last_modified_at = :modifiedAt,
           last_modified_by = :modifiedBy
       WHERE id = :id
       """)
Mono<Integer> updateStatusAndAudit(
        @Param("id") Long id,
        @Param("status") String status,
        @Param("modifiedAt") Instant modifiedAt,
        @Param("modifiedBy") String modifiedBy);
~~~

### 2.3. DatabaseClient does not automatically know the current actor either

DatabaseClient executes direct SQL:

~~~java
databaseClient.sql("""
        UPDATE customers
        SET status = :status
        WHERE id = :id
        """)
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
~~~

This API has no entity from which to read @LastModifiedBy or @LastModifiedDate. When using DatabaseClient, the application must pass audit values into the SQL statement or rely on a database trigger.

## 3. Approach 1: update audit columns directly in SQL

This is the most direct and visible approach. Every update query needing auditing includes the audit columns in the SET clause.

~~~sql
UPDATE customers
SET status = :status,
    last_modified_at = :modifiedAt,
    last_modified_by = :modifiedBy
WHERE id = :id;
~~~

Advantages:

- The SQL statement clearly shows both the business data and audit columns being changed.
- Does not depend on entity callbacks.
- Easy to verify in code reviews and integration tests.
- Can apply a single timestamp/actor across an entire batch update.

Disadvantages:

- Every write query must remember to update the audit columns.
- Different services or repositories might forget a field.
- Requires shared conventions for actor, timezone, and timestamp source.
- If multiple applications write to the same table, each application must follow the same contract or use a database-side mechanism.

### 3.1. Retrieving the actor from the reactive security context

In a WebFlux application, do not use thread-local SecurityContextHolder.getContext() to obtain the principal inside a reactive pipeline. Use ReactiveSecurityContextHolder or an equivalent reactive context source.

~~~java
public Mono<Void> changeStatus(Long customerId, String status) {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                    new IllegalStateException("No authenticated auditor")))
            .flatMap(actor -> {
                Instant now = clock.instant();
                return customerRepository.updateStatusAndAudit(
                        customerId, status, now, actor);
            })
            .flatMap(rows -> {
                if (rows == 0) {
                    return Mono.error(new CustomerNotFoundException(customerId));
                }
                if (rows != 1) {
                    return Mono.error(new IllegalStateException(
                            "Expected one customer to be updated"));
                }
                return Mono.empty();
            });
}
~~~

This example assumes id is a unique key and clock is an injected Clock. Instant is bound to a column type compatible with the driver/database. If the schema uses TIMESTAMP WITHOUT TIME ZONE, TIMESTAMP WITH TIME ZONE, or another temporal type, pick an appropriate Java type and converter.

### 3.2. Reusing ReactiveAuditorAware

If the application already has a ReactiveAuditorAware<String> bean for entity auditing, you can inject that same provider into services to retrieve the actor for direct SQL:

~~~java
public Mono<Void> changeStatus(Long customerId, String status) {
    return auditorAware.getCurrentAuditor()
            .switchIfEmpty(Mono.error(
                    new IllegalStateException("Auditor is required")))
            .flatMap(actor -> customerRepository.updateStatusAndAudit(
                    customerId,
                    status,
                    clock.instant(),
                    actor))
            .flatMap(this::requireOneUpdatedRow);
}
~~~

Reusing the provider keeps repository saves and direct SQL on the same actor source. However, ReactiveAuditorAware does not run automatically inside modifying queries; the service actively invokes it and passes the result into SQL.

### 3.3. Using system actors for background jobs

A scheduled job or message consumer may not have an HTTP authentication context. Define actors based on the processing source:

- system:reconciliation for reconciliation jobs.
- system:expiry-worker for expiration jobs.
- Authenticated service identity for message consumers.

Avoid using one generic value if you need to trace the specific job type. System actors should come from trusted configuration/identity, not unvalidated payloads.

### 3.4. Generating the timestamp once per operation

If one request updates multiple rows, it is usually best to generate a single timestamp before executing the query and reuse it across all rows:

~~~java
Instant modifiedAt = clock.instant();

return repository.updateManyStatuses(
        ids, status, modifiedAt, actor);
~~~

This ensures rows modified in the same operation share the same audit timestamp. If business rules require distinct timestamps per row, define that rule clearly and let the database or statement produce the corresponding values.

## 4. Approach 2: updating audit fields with R2dbcEntityTemplate

R2dbcEntityTemplate.update(Query, Update) lets you update selected properties without loading the full entity. Since no entity is saved through auditing callbacks, add the audit properties to Update.

~~~java
public Mono<Long> updateCustomerStatus(
        Long customerId,
        String status,
        String actor) {

    Update changes = Update.update("status", status)
            .set("lastModifiedAt", clock.instant())
            .set("lastModifiedBy", actor);

    Query condition = query(where("id").is(customerId));

    return template.update(Customer.class)
            .matching(condition)
            .apply(changes);
}
~~~

Here status, lastModifiedAt, and lastModifiedBy are entity property names. Mapping metadata translates them to the corresponding database column names.

If the entity declares:

~~~java
@LastModifiedDate
@Column("last_modified_at")
private Instant lastModifiedAt;
~~~

then Update uses lastModifiedAt, without hardcoding the physical column name last_modified_at.

### 4.1. Keeping update conditions strict

Auditing does not replace permission checks or business preconditions. In multi-tenant applications, include the tenant in the predicate:

~~~java
Query condition = query(
        where("id").is(customerId)
                .and("tenantId").is(tenantId)
);
~~~

tenantId must come from an authenticated security context. Never trust a tenant ID sent by a client in the request body.

### 4.2. Checking the updated row count

apply() returns Mono<Long> containing the number of rows the database reported as updated:

~~~java
return template.update(Customer.class)
        .matching(query(where("id").is(customerId)))
        .apply(changes)
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(new CustomerNotFoundException(customerId));
            }
            if (rows != 1) {
                return Mono.error(new IllegalStateException(
                        "Unexpected number of updated rows: " + rows));
            }
            return Mono.just(rows);
        });
~~~

If the update uses a status or tenant predicate, a row count of 0 may indicate the record does not exist, does not belong to the tenant, or no longer satisfies the condition. Translate it into an appropriate business error rather than always reporting not found if callers need to distinguish these cases.

## 5. Approach 3: using a database trigger

If multiple applications or tools write to the same table, relying on each client to manually update audit columns may not be dependable enough. A database trigger can automatically update last_modified_at whenever a row is updated, regardless of whether the statement came from Spring Data, a SQL script, or another application.

Conceptual example:

~~~sql
-- Pseudocode: trigger syntax depends on the database engine.
BEFORE UPDATE ON customers
FOR EACH ROW
BEGIN
    NEW.last_modified_at = CURRENT_TIMESTAMP;
END;
~~~

A trigger can guarantee that the modification timestamp is recorded in the database. However, who made the modification still needs to be passed to the database through a reliable mechanism.

### 5.1. Database-managed timestamps

Triggers can use CURRENT_TIMESTAMP or an equivalent time function to standardize the time source across all writers. Clarify the time function's semantics: transaction start time, statement time, or wall-clock time at invocation can differ across databases.

### 5.2. Actors must be passed explicitly

Databases normally do not know the HTTP principal or application user. You can pass the actor via:

- A last_modified_by column in the SQL statement.
- A database session variable or transaction-local setting.
- A database role/service identity if you only need to know which application wrote the row.
- A trigger looking up the actor from an authenticated context.

Do not infer end users from a shared connection pool database login if every request uses the same service account.

### 5.3. PostgreSQL example with a transaction-local setting

PostgreSQL supports set_config with is_local = true to set a value valid only for the current transaction. You can set the actor before the update statement:

~~~sql
SELECT set_config('app.actor_id', :actor, true);

UPDATE customers
SET status = :status
WHERE id = :id;
~~~

The PostgreSQL trigger can read the context:

~~~sql
NEW.last_modified_by := current_setting('app.actor_id', true);
NEW.last_modified_at := CURRENT_TIMESTAMP;
~~~

This is a PostgreSQL-specific example, not portable SQL. Both set_config and the update statement must run inside the same transaction/connection for the transaction-local setting to remain effective. The reactive transaction manager must ensure operations use the same connection bound to the transaction.

With connection pools, avoid long-lived session settings without resetting them; an actor value from a previous request could leak to the next request if scoped improperly. Transaction-local settings reduce that risk, though you should still test with your actual pool and transaction manager.

### 5.4. Triggers and application-side audit updates should not compete

If a trigger always sets last_modified_at, a timestamp bound by the application may be overwritten by the trigger. If both the application and trigger update last_modified_by, the final result depends on trigger and SQL execution order.

Choose one authoritative source for each field:

- Database trigger manages timestamps, application passes the actor.
- Application manages both timestamps and actors.
- Database manages both timestamps and actors from a transaction context.

Document the contract clearly in the schema and operational docs so every writer follows the same rule.

## 6. Bulk updates and entity auditing limits

A bulk update can modify hundreds or thousands of records with a single statement:

~~~sql
UPDATE customers
SET status = 'INACTIVE'
WHERE last_login_at < :cutoff;
~~~

No individual entity is loaded and saved for each row. Consequently, entity auditing callbacks do not automatically run once per record.

If auditing is needed:

~~~sql
UPDATE customers
SET status = 'INACTIVE',
    last_modified_at = :modifiedAt,
    last_modified_by = :actor
WHERE last_login_at < :cutoff;
~~~

One timestamp and actor can represent the entire batch. If detailed per-row history is needed, design a separate audit/event table or history-logging trigger.

### 6.1. Do not load thousands of entities just to run auditing callbacks

One workaround is fetching all entities, modifying each one, and calling save on every item. This can produce many round trips, increase memory pressure, and slow down batches.

If business logic simply changes a uniform status based on a predicate, a bulk update with explicit audit columns is usually better suited. If each entity requires custom domain logic, process in bounded batches and watch transaction size.

### 6.2. Bulk updates can bypass entity optimistic locking

A direct SQL update does not automatically apply @Version like an entity save. If optimistic locking is needed for direct updates, include version or an appropriate predicate in the statement, or design a conditional update and inspect the affected row count.

Example:

~~~sql
UPDATE customers
SET status = :newStatus,
    version = version + 1,
    last_modified_at = :modifiedAt,
    last_modified_by = :actor
WHERE id = :id
  AND version = :expectedVersion;
~~~

If the updated row count is 0, the record may not exist or the version changed. Incrementing version inside the same statement keeps checking and writing atomic.

## 7. Auditing is not synonymous with full change history

The createdBy, createdAt, lastModifiedBy, and lastModifiedAt fields show who created and who most recently modified a record. They do not retain every old value, new value, or intermediate edit.

Example:

| Timestamp | Actor | Change |
| --- | --- | --- |
| 09:00 | user-10 | Created customer, status = NEW |
| 09:15 | user-22 | Changed status to ACTIVE |
| 10:30 | system:sync | Changed email |

After the last edit, the last-modified columns show only system:sync and timestamp 10:30. You cannot tell from those columns alone that user-22 previously changed status to ACTIVE.

If full history is needed, use an audit table, event log, CDC, or appropriate versioning mechanism. Direct SQL updates must be designed to record history in the same transaction if no events may be lost.

### 7.1. Audit table

Schema example:

~~~sql
CREATE TABLE customer_audit (
    audit_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    action VARCHAR(30) NOT NULL,
    changed_at TIMESTAMP NOT NULL,
    changed_by VARCHAR(120),
    old_status VARCHAR(30),
    new_status VARCHAR(30)
);
~~~

A service can update the customer and insert an audit row in the same transaction. If either step fails, both roll back:

~~~java
@Transactional
public Mono<Void> changeStatus(
        Long customerId,
        String newStatus,
        String actor) {

    Instant now = clock.instant();

    return customerRepository.updateStatusAndAudit(
                    customerId, newStatus, now, actor)
            .flatMap(rows -> {
                if (rows != 1) {
                    return Mono.error(new CustomerNotFoundException(customerId));
                }

                return customerAuditRepository.insertStatusChange(
                        customerId, now, actor, newStatus);
            })
            .then();
}
~~~

This condensed example omits reading the old status. If auditing needs accurate old values, design the statement or trigger to capture old/new within the same update operation, avoiding reading first and writing audit later under insufficient transaction isolation.

## 8. Choosing the right auditing approach

| Scenario | Approach to consider |
| --- | --- |
| Regular entity CRUD via repository save | Spring Data auditing callbacks |
| A modifying query updating selected columns | Add last_modified_at and last_modified_by to SQL |
| Partial update via R2dbcEntityTemplate | Add audit properties to Update |
| Multiple applications/SQL tools writing to one table | Database triggers or shared database conventions |
| Bulk update by predicate | Update audit columns in the statement or use a trigger |
| Full old/new history needed for all changes | Audit table, history trigger, event log, or CDC |
| Background job without HTTP principal | Explicit system actor |
| Optimistic locking needed in direct SQL | Add version predicate and increment version atomically |

There is no single choice for every system. If only one Spring Data application writes data, updating audit columns in services/repositories may be clear enough. If multiple independent writers exist, database triggers reduce the risk of a writer forgetting to update audit fields.

## 9. Common mistakes

| Symptom | Cause | How to fix |
| --- | --- | --- |
| lastModifiedAt unchanged after @Modifying @Query | Modifying queries bypass auditing entity callbacks | Add audit columns to SQL or use a trigger |
| lastModifiedBy always null | Direct SQL does not invoke auditor provider | Retrieve reactive actor and bind to query |
| createdAt modified during update | SQL or trigger accidentally updates created fields | Only update last-modified fields on update |
| Entity saves have audits but bulk updates do not | The two write paths use different mechanisms | Establish audit conventions for both paths |
| Actor recorded as anonymous | Auditor provider accepts anonymous authentication | Filter principals and define actor fallback rules |
| Background job has no actor | No HTTP SecurityContext exists | Use a clearly named system actor |
| Timestamp timezone mismatch | Java/database use inconsistent temporal types or timezones | Choose Instant/UTC and matching mapping/schema |
| Some writers skip auditing | Auditing is updated manually in individual services | Use shared helpers, triggers, or database checks |
| Trigger overwrites application timestamp | Two sources manage the same column | Designate one authoritative source |
| Audit table out of sync with main data | Update and history insert not in the same transaction | Combine in one transaction or use a trigger |
| Bulk update bypasses version | Direct SQL does not automatically apply @Version | Add explicit version predicate/increment |

## 10. Testing auditing limits on direct updates

Test against a real R2DBC database or Testcontainers. Unit tests that merely mock repositories cannot confirm whether auditing callbacks run or whether SQL actually updates audit columns.

### 10.1. Testing repository save with auditing

For an entity with @CreatedDate, @CreatedBy, @LastModifiedDate, and @LastModifiedBy, create the entity via repository:

~~~java
StepVerifier.create(customerRepository.save(new Customer("Lan", "NEW")))
        .assertNext(saved -> {
            assertThat(saved.getCreatedAt()).isNotNull();
            assertThat(saved.getCreatedBy()).isEqualTo("test-user");
            assertThat(saved.getLastModifiedAt()).isNotNull();
            assertThat(saved.getLastModifiedBy()).isEqualTo("test-user");
        })
        .verifyComplete();
~~~

Tests need a deterministic test auditor, such as ReactiveAuditorAware returning Mono.just("test-user"), and a fixed clock for stable time assertions.

### 10.2. Testing that a modifying query does not auto-audit

Create a row with known last_modified_at and last_modified_by values, then invoke a modifying query that updates only status:

~~~java
StepVerifier.create(customerRepository.updateStatus(id, "ACTIVE"))
        .expectNext(1)
        .verifyComplete();
~~~

Read the row back and verify the last-modified columns remain unchanged. This test clarifies the limitation: auditing annotations do not automatically inject columns into SQL statements.

### 10.3. Testing a modifying query with explicit auditing

Call the update method accepting modifiedAt and modifiedBy. Read the row back and verify:

- status holds the new value.
- last_modified_at equals the passed timestamp.
- last_modified_by equals the passed actor.
- created_at and created_by preserve their initial values.

### 10.4. Testing database triggers

If using triggers, test repository save, repository @Modifying @Query, DatabaseClient, bulk updates, SQL executed outside the application in the test environment, and verify actor context does not leak across connections reused from the pool.

### 10.5. Testing reactive auditor context

Verify that the actor is retrieved properly from the reactive security context in a WebFlux pipeline. Do not test only with thread-local setups or calls from a plain test thread, as that can hide lost-context bugs when switching schedulers.

## 11. Workflow for implementing consistent auditing

1. Identify tables and audit columns to manage.
2. Distinguish entity metadata from actual rules enforced in the database.
3. Enable @EnableR2dbcAuditing and configure ReactiveAuditorAware for entity save paths.
4. Inventory all write paths: repository saves, modifying queries, template updates, DatabaseClient, batch jobs, and external SQL.
5. For direct SQL, add audit columns or establish database triggers.
6. Choose the authoritative source for actors and timestamps.
7. Never alter created_at/created_by during normal updates.
8. If full history is needed, write audit events/tables in the same transaction or use an appropriate CDC mechanism.
9. If direct SQL requires optimistic locking, include version in the predicate and increment version in the same statement.
10. Write integration tests for each write path and verify the actual audit columns.

## 12. Flow for choosing an auditing mechanism

~~~mermaid
flowchart TD
    A[Application needs to write data] --> B{Saving an entity via Spring Data?}
    B -->|Yes| C[Auditing entity callback]
    B -->|No, direct SQL or partial update| D{Can modify the SQL statement?}
    D -->|Yes| E[Bind last_modified_at and last_modified_by]
    D -->|No or multiple writers| F[Database trigger]
    C --> G{Need old/new history?}
    E --> G
    F --> G
    G -->|Yes| H[Audit table, event log, or CDC]
    G -->|No| I[Keep created and last-modified metadata]
~~~

## 13. Conclusion

Spring Data R2DBC auditing relies on entity metadata and callbacks in the entity save workflow. The @CreatedDate, @CreatedBy, @LastModifiedDate, and @LastModifiedBy annotations do not automatically monitor every SQL statement executed against the database.

When using @Modifying @Query, DatabaseClient, or R2dbcEntityTemplate.update(Query, Update), explicitly update audit columns or use a database trigger. Obtain actors from the reactive context or a trusted system identity, use a consistent time source, preserve created fields on updates, and verify the affected row count. If full old/new history is required, design a dedicated audit table or event log because last-modified fields only store the most recent modification state.

Test each write path separately. A successful audited entity save does not prove that bulk updates or native SQL also audit automatically. Clear conventions across Spring Data callbacks, direct SQL, and database triggers keep audit data consistent even when an application updates the same table in multiple ways.
