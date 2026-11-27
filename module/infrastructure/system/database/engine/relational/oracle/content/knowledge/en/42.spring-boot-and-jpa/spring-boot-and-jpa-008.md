# Sequence Generators, allocationSize, and Coordinating with Oracle Sequences

In a Spring Boot application using Spring Data JPA/Hibernate with Oracle Database, primary keys can be generated using an Oracle sequence. JPA describes this mechanism via the `SequenceGenerator` and `GeneratedValue` annotations; Hibernate decides how to fetch sequence values and allocate IDs to entities.

The key point of coordination is `allocationSize` in the Java mapping and `INCREMENT BY` on the Oracle sequence. When Hibernate uses a pooled optimizer to claim a range of IDs, the database sequence must advance in increments matching the block size Hibernate expects. Mismatched settings can cause application startup to fail when Hibernate detects the mismatch, or in older/unvalidated configurations can lead to overlapping ID ranges.

Furthermore, `allocationSize` is not the same as Oracle's `CACHE`:

- `allocationSize` lets Hibernate fetch one sequence value and dispense multiple IDs in application memory.
- `CACHE` lets Oracle pre-allocate multiple sequence values in the database instance to reduce sequence generation overhead.

Both mechanisms operate at different layers and can be used simultaneously. Getting the design right requires aligning JPA mappings, Hibernate optimizers, Oracle DDL, all other writers sharing the sequence, and change procedures while the application is running.

## 1. Oracle Sequences and JPA Sequence Generators

### 1.1. What Is an Oracle Sequence?

A sequence is a database object that generates a series of numbers according to its definition. Multiple sessions and application instances can call the same sequence to obtain distinct values without locking a shared counter table.

Example sequence creation:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

Fetching a value:

```sql
SELECT APP.ORDERS_SEQ.NEXTVAL
FROM DUAL;
```

Within a session, after calling `NEXTVAL`, you can read `CURRVAL`:

```sql
SELECT APP.ORDERS_SEQ.CURRVAL
FROM DUAL;
```

`CURRVAL` is undefined in a session until that session has called `NEXTVAL` at least once. A `NEXTVAL` value issued by the sequence is not returned if the transaction rolls back.

### 1.2. JPA Generator Name and Database Sequence Name Are Different

In `SequenceGenerator`:

- `name` is the logical name of the generator within the persistence unit.
- `sequenceName` is the actual sequence object name in the database.
- `schema` identifies the schema containing the sequence when declared.
- `allocationSize` specifies how many IDs the provider can allocate per sequence fetch.
- `initialValue` specifies the starting value the provider uses when generating schemas from metadata; it does not reset an existing sequence.

Do not confuse `name` with `sequenceName`. The generator `name` must be unique within the persistence unit per JPA rules; the database `sequenceName` must match the Oracle object.

### 1.3. Entity Using a Sequence

Entity example:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.SequenceGenerator;
import jakarta.persistence.Table;

@Entity
@Table(name = "ORDERS", schema = "APP")
@SequenceGenerator(
    name = "orders_id_generator",
    sequenceName = "ORDERS_SEQ",
    schema = "APP",
    allocationSize = 1
)
public class Order {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "orders_id_generator"
    )
    @Column(name = "ORDER_ID")
    private Long id;

    // Other business fields.
}
```

In Spring Boot 2 using the legacy Java EE/JPA namespace, imports are typically `javax.persistence.*`; Spring Boot 3 and later use `jakarta.persistence.*`. Pick the namespace matching your actual Spring Boot/JPA version.

### 1.4. Oracle Configuration Matching allocationSize = 1

For the example above:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

This is the simplest configuration: Hibernate fetches one sequence value per ID. `CACHE 100` can still be used to cut sequence-generation cost in Oracle; it does not make Hibernate allocate 100 IDs inside the JVM.

### 1.5. Using allocationSize Greater Than 1

When you need fewer round trips to the database, you can configure:

```java
@SequenceGenerator(
    name = "orders_id_generator",
    sequenceName = "ORDERS_SEQ",
    schema = "APP",
    initialValue = 1,
    allocationSize = 50
)
```

With Hibernate using `pooled` or `pooled-lo` optimizers, the Oracle sequence typically needs to be defined as:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Once the provider retrieves a sequence value, Hibernate uses the optimizer to manage the ID block according to that optimizer's rules. Exact block start/end values depend on `pooled` vs. `pooled-lo` and generator initialization; the critical rule is that the database sequence increment must match the allocation protocol used by the provider.

Never change the annotation to 50 while leaving the sequence increment at 1 without verifying the optimizer and mismatch strategy. This is one of the most common mistakes when migrating Hibernate applications from older configurations to newer mappings.

## 2. GenerationType.SEQUENCE and SequenceGenerator

### 2.1. GenerationType.SEQUENCE

`GenerationType.SEQUENCE` tells the persistence provider to use a database sequence to generate identifiers. Oracle supports sequences natively, making this a natural choice for entities requiring numeric IDs.

Unlike `GenerationType.IDENTITY`, the sequence can be called before the `INSERT` statement. The provider knows the ID before inserting the entity, allowing Hibernate to coordinate more smoothly with the persistence context and JDBC batching.

### 2.2. GenerationType.IDENTITY

Oracle supports identity columns starting in releases with that feature. When using an identity column, the mapping typically uses:

```java
@Id
@GeneratedValue(strategy = GenerationType.IDENTITY)
private Long id;
```

Do not declare `SequenceGenerator` for an identity column in the same way as the sequence example. Identity columns are managed internally by the database's identity mechanism. Choosing `IDENTITY` vs. `SEQUENCE` depends on schema design, Oracle release, Hibernate dialect, and batching requirements.

### 2.3. Why Declare Generators Explicitly?

Do not rely on default sequence names inferred by Hibernate. Explicitly declaring a generator lets you:

- Use Oracle sequence names managed by migration scripts.
- Keep naming consistent between Java and the database.
- Control `allocationSize`.
- Avoid accidentally creating extra unwanted sequences.
- Simplify code reviews when multiple services access the schema.

### 2.4. Generators Can Be Placed at Entity or Package Level

`SequenceGenerator` can be placed on an entity or package per JPA mapping rules. When multiple entities share a generator, ensure they genuinely belong on the same sequence and share the same allocation protocol. Never share a sequence across entities with differing `allocationSize` values without an explicitly tested design.

### 2.5. Using schema in the Annotation

If the sequence lives in schema `APP` while the app connects as `APP_RUNTIME`, declare `schema` and grant the required privilege. Even if the app connects directly as owner `APP`, declaring `schema` makes the mapping explicit.

## 3. What Is allocationSize?

### 3.1. Meaning

`allocationSize` is the allocation block size used by the JPA provider when generating identifiers. When set greater than 1 and Hibernate uses a compatible optimizer, the provider can fetch one marker from Oracle and generate multiple IDs in memory before querying the sequence again.

Example with `allocationSize` 50:

1. Hibernate needs an ID for a new entity.
2. Hibernate fetches a value from the Oracle sequence.
3. The optimizer derives the corresponding ID block.
4. Hibernate dispenses IDs from that block to subsequent entities.
5. Once the block is exhausted, Hibernate fetches the next sequence value.

As a result, `NEXTVAL` calls drop significantly compared to calling once per `INSERT`.

### 3.2. allocationSize = 1

This is the easiest configuration to coordinate:

- Every ID requires one sequence call.
- The Oracle sequence normally uses `INCREMENT BY 1`.
- No large unused ID blocks sit in application memory.
- Easy interoperability with external programs calling `NEXTVAL` directly.
- Adds database round trips when inserting many entities.

Use this when insert volume is moderate, when simplifying coordination with multiple writers, or during migrations from legacy systems that cannot synchronize on a block allocation protocol yet.

### 3.3. allocationSize Greater Than 1

Benefits:

- Fewer database sequence calls.
- Fewer network round trips between application and Oracle.
- Supports higher insert throughput.
- Reduces sequence contention in multi-node workloads.

Trade-offs:

- Unused IDs in memory are wasted on JVM restarts or process crashes.
- Sequence increment must match the optimizer.
- Every application instance must use a compatible allocation protocol.
- Changing `allocationSize` requires coordinating deployment with database DDL.
- In-memory allocated IDs may not match exact commit order.

### 3.4. Default Value

In JPA, `SequenceGenerator.allocationSize` defaults to 50. Never omit this attribute in systems with multiple services or existing sequences; declare the value explicitly and align the DDL.

### 3.5. allocationSize Is Not Batch Size

These are two distinct settings:

- `allocationSize`: number of identifiers dispensed from one sequence allocation.
- Hibernate JDBC batch size: number of DML statements grouped in one JDBC batch.

For example, `allocationSize` 50 and JDBC batch size 25 can be used together: Hibernate reserves IDs in blocks of 50 while sending `INSERT` statements in batches of 25. Raising one does not automatically raise the other.

## 4. Hibernate Sequence Optimizers

### 4.1. Why Are Optimizers Needed?

JPA defines `allocationSize` at the specification level. Hibernate implements ID allocation via optimizers. The optimizer defines what a `NEXTVAL` value means and how to turn it into one or more entity IDs.

Common optimizers:

| Optimizer | Idea | Relationship to database sequence |
|---|---|---|
| none | Fetches one value per ID | Typically uses increment 1 |
| hilo | Uses a high value from the sequence to generate a range of low values | Legacy mechanism often paired with increment-by-1 sequences |
| pooled | Sequence value marks block boundaries per pooled rules | Sequence increment must match block size |
| pooled-lo | Sequence value marks the start of a block per pooled-lo rules | Sequence increment must match block size |

Exact initialization, block boundaries, and default optimizer depend on Hibernate version, generator mapping, and configuration. Do not guess the optimizer from annotations alone; check your Hibernate version and startup logs.

### 4.2. none

The `none` optimizer queries the sequence for every identifier. With an increment-1 sequence, each `NEXTVAL` yields one ID. This is straightforward and plays nicely with native SQL or external applications.

### 4.3. hilo

Hi/lo is an identifier allocation algorithm that treats a sequence value as the high component and generates multiple low values in memory. Legacy mappings could use a sequence with increment 1 even when the allocation block exceeded 1.

This is why you cannot claim every large `allocationSize` forces `INCREMENT BY` to equal `allocationSize` without knowing the optimizer. In modern Hibernate, `pooled`/`pooled-lo` are the standard approaches; legacy `hilo` has different semantics.

### 4.4. pooled

The `pooled` optimizer uses sequence values as block boundaries. The database sequence increment must match the allocation size expected by the optimizer so blocks from consecutive fetches do not overlap.

### 4.5. pooled-lo

`pooled-lo` treats the fetched sequence value as the lower bound of the block. With an allocation size of 50, one fetch yields a range of 50 IDs starting at that value. The next fetch claims the next sequence marker, spaced 50 apart when the Oracle sequence is configured accordingly.

### 4.6. Do Not Force Optimizers Without Understanding the Mapping

Hibernate exposes properties to pick pooled optimizers or tune generator behavior. Legacy settings and Hibernate 5/6 properties can differ. If switching optimizers, test in staging across multiple application instances and verify ID uniqueness before deploying.

### 4.7. Sequence Increment Mismatch Checks

Hibernate can detect at startup when the mapping's increment size differs from the database sequence's increment. Depending on version and config, mismatches can be handled via strategies such as `EXCEPTION`, `FIX`, `LOG`, or `NONE`.

Never disable checks just to hide DDL errors. Verify the sequence increment, mapping, and optimizer. If Hibernate reports a mismatch, halt rollout and align them.

## 5. Coordinating allocationSize with Oracle INCREMENT BY

### 5.1. Practical Rule for Pooled Optimizers

If Hibernate uses `pooled` or `pooled-lo` with `allocationSize` 50, the Oracle sequence is typically:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

If `allocationSize` is 1 with optimizer `none`, the simple setup is:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 1
    CACHE 100
    NOCYCLE;
```

These templates fit Hibernate `pooled`/`pooled-lo` and `none` respectively; confirm the active optimizer and Hibernate version before applying.

### 5.2. allocationSize 50 Example

Suppose the mapping is:

```java
@SequenceGenerator(
    name = "invoice_seq_gen",
    sequenceName = "INVOICE_SEQ",
    schema = "APP",
    allocationSize = 50
)
```

DDL for a pooled optimizer:

```sql
CREATE SEQUENCE APP.INVOICE_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Hibernate fetches sequence markers and issues IDs from the block per the optimizer. The application does not call `NEXTVAL` for every invoice; it only fetches a marker when the current block runs out.

### 5.3. allocationSize 100 Example

Java:

```java
@SequenceGenerator(
    name = "payment_seq_gen",
    sequenceName = "PAYMENT_SEQ",
    schema = "APP",
    allocationSize = 100
)
```

Oracle:

```sql
CREATE SEQUENCE APP.PAYMENT_SEQ
    START WITH 1
    INCREMENT BY 100
    CACHE 50
    NOCYCLE;
```

Here `CACHE 50` means 50 sequence values in Oracle's cache, not 50 Hibernate entity IDs. Because the sequence increments by 100, each cached sequence value is spaced 100 apart.

### 5.4. Mismatch: allocationSize 50 with INCREMENT BY 1

Suppose:

- Java mapping: `allocationSize` 50.
- Hibernate uses `pooled-lo`.
- Oracle sequence: `INCREMENT BY 1`.

The sequence returns consecutive markers 1, 2, 3... while Hibernate treats each marker as the start of a 50-ID block. Blocks overlap. Modern Hibernate typically detects the mismatch and refuses to start under the default strategy; if validation is disabled or legacy behavior differs, the risk of duplicate IDs is severe.

### 5.5. Mismatch: allocationSize 1 with INCREMENT BY 50

The mapping and physical sequence follow incompatible protocols. Depending on optimizer/version, Hibernate may throw an increment mismatch error, create large gaps, or consume the sequence unexpectedly. Never accept a mismatch merely because a quick smoke test with a few inserts didn't hit duplicates.

### 5.6. All Writers Must Understand the Same Sequence

If the same sequence is used by:

- Spring Boot service A.
- Spring Boot service B.
- A batch process.
- Stored procedures.
- Native SQL inserts.

you must define how every writer obtains IDs. Never let one service use pooled allocation while another assumes increment-by-1 without a compatible design. When coordinating multiple writers is hard, consider `allocationSize` 1 or separate sequences per owning domain.

## 6. How Oracle CACHE and allocationSize Differ

### 6.1. allocationSize in the Application

Hibernate fetches a sequence marker and dispenses a block of IDs in JVM heap. That block belongs to the application process, and any unused IDs are discarded when the process stops.

### 6.2. CACHE in Oracle

Oracle sequence `CACHE` pre-allocates sequence values in database instance memory to reduce sequence generation overhead. When a database instance crashes or shuts down abnormally, unused cached values can be lost.

Example:

```sql
CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Oracle caches 100 sequence values, each incrementing by 50. Hibernate separately uses `allocationSize` 50 to manage entity IDs. These are two independent allocation layers.

### 6.3. Comparison

| Attribute | JPA allocationSize | Oracle CACHE |
|---|---|---|
| Where managed | Application/Hibernate | Oracle Database instance |
| What is allocated | Entity IDs in a block | Sequence values |
| What cost it reduces | Reduces app-to-DB round trips for sequences | Reduces sequence value generation overhead |
| On JVM restart | Unused block is discarded | Does not directly affect Oracle's cache |
| On DB instance restart | JVM-held blocks may remain, though connections/txns need handling | Cached sequence values may be lost |
| Must match allocationSize? | Yes, with pooled optimizers per protocol | CACHE does not need to equal allocationSize |

### 6.4. How Large Should CACHE Be?

Choose `CACHE` based on sequence call frequency, instance count, performance targets, and gap tolerance. Larger `CACHE` generally reduces sequence generation cost; it does not guarantee contiguous IDs.

### 6.5. NOCACHE Does Not Produce a Gapless Sequence

`NOCACHE` removes one source of gaps (lost cache on instance crash), but `NEXTVAL` remains non-transactional. Rollbacks, process failures, block allocations, and other events still create gaps. Never use `NOCACHE` to promise sequential invoice numbers.

## 7. ID Gaps, Ordering, and Uniqueness

### 7.1. Gaps Are Normal

Sequences guarantee unique values per their configuration, not gap-free numbers. Gaps occur when:

- A transaction calls `NEXTVAL` and rolls back.
- An application claims a block of 50 IDs and uses only part of it before restarting.
- Oracle's sequence cache is lost during an instance failure.
- A batch claims IDs without inserting every row.
- A sequence is advanced past previously imported IDs.

Do not treat ID gaps as evidence of lost data or failed migrations without corroborating evidence.

### 7.2. Sequences Do Not Guarantee Commit Order

IDs are allocated before transactions commit. Transaction A may obtain a lower ID yet commit after Transaction B. With pooled allocation, separate application instances hold different blocks and insert at independent rates.

Never use sequence IDs to infer exact business ordering or event timestamps.

### 7.3. CACHE and ORDER

- `CACHE` controls how many sequence values Oracle pre-allocates.
- `ORDER` requests sequence values be issued in request order within Oracle's guarantees.
- `NOORDER` is generally appropriate for primary keys when only uniqueness is required.

`ORDER` does not eliminate gaps and does not guarantee commit order. In RAC, `ORDER` adds synchronization overhead; enable it only if business logic genuinely requires ordered issuance and performance has been measured.

### 7.4. NOCYCLE for Primary Keys

Sequences backing primary keys must normally be `NOCYCLE`. With `CYCLE`, a sequence can wrap back around after hitting `MAXVALUE`/`MINVALUE`, causing duplicate key errors.

### 7.5. Sequences Are Not Business Document Numbers

If business rules require gapless document numbers, you likely need a dedicated numbering workflow with transaction serialization, locking, and auditing. Database sequences cannot guarantee gapless numbering simply by setting `NOCACHE`/`ORDER`.

## 8. Spring Boot and Hibernate Configuration

### 8.1. Entity Mapping

Example configuring `allocationSize` 50:

```java
@Entity
@Table(name = "INVOICE", schema = "APP")
@SequenceGenerator(
    name = "invoice_seq_gen",
    sequenceName = "INVOICE_SEQ",
    schema = "APP",
    initialValue = 1,
    allocationSize = 50
)
public class Invoice {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "invoice_seq_gen"
    )
    @Column(name = "INVOICE_ID")
    private Long id;

    // Business fields.
}
```

Ensure `INVOICE_SEQ` is created by migration scripts with an increment matching Hibernate's optimizer.

### 8.2. Spring Boot Application Properties

Production-oriented configuration example:

```yaml
spring:
  datasource:
    url: jdbc:oracle:thin:@//dbhost:1521/APP_SERVICE
    username: APP_RUNTIME
  jpa:
    hibernate:
      ddl-auto: validate
    properties:
      hibernate:
        format_sql: true
```

Inject the password using your environment's secret management; never commit credentials to source control.

### 8.3. Managing Sequences with Flyway or Liquibase

In production, create and alter sequences using versioned migrations:

```sql
CREATE SEQUENCE APP.INVOICE_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

Do not rely on `spring.jpa.hibernate.ddl-auto=update` to synchronize sequence increments. Schema migration tools provide DDL review, rollout ordering, and rollback plans.

### 8.4. ddl-auto

- `create`/`create-drop`: suitable for certain test environments; can drop/recreate schemas.
- `update`: Hibernate attempts to alter schemas; should not be used for controlled production migrations.
- `validate`: checks certain mapping/schema compatibility, but does not replace full verification of sequence optimizers, privileges, and runtime behavior.
- `none`: does not manage schema automatically.

Choose strategy by environment; production usually delegates DDL to Flyway/Liquibase and lets Hibernate validate mappings.

### 8.5. Hibernate Version

Spring Boot manages Hibernate versions via release dependency management. When upgrading Spring Boot, Hibernate may change generator behavior, optimizer defaults, or schema validation. Record the actual resolved version:

```text
mvn dependency:tree
```

Or use Gradle `dependencyInsight` to see the resolved Hibernate ORM version. Do not just check the version written in a build file if dependencies can be overridden.

### 8.6. Sequence Increment Mismatch Strategy

Hibernate provides a property controlling sequence increment mismatch handling in supported versions. Common strategies include:

- `EXCEPTION`: fails when the sequence increment does not match the mapping.
- `FIX`: adjusts how Hibernate interprets the increment per supported strategy.
- `LOG`: logs a warning.
- `NONE`: skips mismatch checks.

Property names, values, and defaults depend on Hibernate version. Never set `NONE` to mask mismatches. Prefer aligning DDL and mappings; only pick another strategy when you thoroughly understand the optimizer and have proved zero overlap.

## 9. Oracle Sequence Privileges

### 9.1. Same Schema

If the application database user owns the sequence, it can access its own sequence by ownership.

### 9.2. Cross-Schema

If the sequence is in `APP` and the application connects as `APP_RUNTIME`, grant privilege:

```sql
GRANT SELECT ON APP.ORDERS_SEQ TO APP_RUNTIME;
```

In Oracle, `SELECT` privilege on a sequence grants permission to call `NEXTVAL`/`CURRVAL`. You can create a synonym for shorter mapping, though synonyms do not grant privileges:

```sql
CREATE SYNONYM APP_RUNTIME.ORDERS_SEQ
FOR APP.ORDERS_SEQ;
```

### 9.3. Checking Privileges

```sql
SELECT owner,
       table_name,
       grantee,
       privilege
FROM all_tab_privs
WHERE owner = 'APP'
  AND table_name = 'ORDERS_SEQ';
```

Checking synonyms:

```sql
SELECT owner, synonym_name, table_owner, table_name, db_link
FROM all_synonyms
WHERE synonym_name = 'ORDERS_SEQ';
```

### 9.4. Privilege Errors

Common errors:

- `ORA-02289`: sequence does not exist; may be caused by wrong name/schema or missing privilege.
- `ORA-01031`: insufficient privileges.
- `ORA-00942` when querying related objects may be caused by name or privilege issues.

Verify the actual runtime user, current schema, and object resolution; never test solely with a DBA account because DBA privileges mask missing application-user grants.

## 10. Multiple Application Instances and Multiple Writers

### 10.1. Spring Boot Running Multiple Replicas

In Kubernetes or an application cluster, multiple JVMs can share one Oracle sequence. The Oracle sequence issues distinct values across sessions; each JVM's Hibernate holds its own ID block.

Conceptual illustration:

```text
JVM A reserves block A
JVM B reserves block B
JVM C reserves block C

Each JVM allocates IDs locally until its block is exhausted.
```

Block size and sequence increment must agree. Do not rely on giving each pod a different generator name to avoid collisions; uniqueness comes from the database sequence and the allocation protocol.

### 10.2. Scale-Out and Restarts

When a pod restarts, unused IDs in its block are wasted. That is normal behavior. As pod counts rise, block fetches increase, though they remain far fewer than total inserts when workloads consume full blocks.

### 10.3. Rolling Deployments

Never run a rolling deployment of two application versions with differing `allocationSize`/optimizer settings against the same sequence without a compatible transition design. Old instances may still hold in-memory blocks while new instances start fetching under new rules.

When changing the allocation protocol, use a coordinated rollout:

1. Stop or drain all writers.
2. Wait for in-flight transactions to finish.
3. Confirm no JVM still holds old blocks.
4. Execute sequence DDL.
5. Deploy the updated mapping uniformly.
6. Restart all writers.
7. Run concurrent insert tests and verify unique constraints.

### 10.4. Native SQL and Stored Procedures

If a stored procedure also calls `NEXTVAL`, verify it uses the same sequence and does not assume increment 1 while Hibernate uses pooled allocation. Even if the procedure calls `NEXTVAL` once per row, the sequence allocation protocol must remain compatible with the pooled optimizer.

### 10.5. Bulk Loads

Data imports can bring existing IDs without automatically advancing the sequence past `MAX(primary key)`. After a bulk load, the sequence may sit below imported IDs. Reconcile the sequence before opening write traffic.

### 10.6. Separating Sequences by Service

If services have independent lifecycles and release schedules, separating sequences by domain/service reduces coupling. However, if services insert into the same table or require globally unique IDs, establish a unified key-space design.

## 11. Oracle RAC and Sequence Behavior

### 11.1. Sequences in RAC

Oracle RAC allows multiple instances to access the database concurrently. Sequences manage issuing distinct values across instances. `CACHE` reduces cross-instance synchronization, whereas `ORDER` enforces stricter allocation ordering.

### 11.2. NOORDER

`NOORDER` is the common choice when only uniqueness is required. Values issued across RAC instances may not increase chronologically from the application's viewpoint. That does not affect sequence uniqueness.

### 11.3. ORDER

`ORDER` requests sequence issuance in request order within Oracle's guarantees. It does not guarantee commit order, eliminate gaps, or come free of overhead. Enable it only when business rules strictly require ordered sequence issuance and performance has been benchmarked.

### 11.4. Application Allocation Has Its Own Ordering

Even when the Oracle sequence uses `ORDER`, Hibernate dispenses IDs from reserved blocks inside each JVM. Inserted/committed IDs are not necessarily globally ordered. If chronological ordering is needed, store an explicit timestamp or dedicated business sequence.

## 12. Inspecting Oracle Sequence Metadata

### 12.1. ALL_SEQUENCES

```sql
SELECT sequence_owner,
       sequence_name,
       min_value,
       max_value,
       increment_by,
       cycle_flag,
       order_flag,
       cache_size,
       last_number
FROM all_sequences
WHERE sequence_owner = 'APP'
ORDER BY sequence_name;
```

`DBA_SEQUENCES` offers broader visibility if you have DBA privileges. `ALL_SEQUENCES` shows sequences visible to the current user.

### 12.2. LAST_NUMBER

`LAST_NUMBER` reflects the cached/next boundary persisted in the dictionary, not necessarily the exact next `NEXTVAL` when sequence caching is active. Never use `LAST_NUMBER` as the exact last issued ID.

### 12.3. Auditing an Entity's Sequence

Cross-check:

- `sequenceName` in the annotation.
- Declared schema.
- Actual Oracle object.
- `INCREMENT_BY`.
- `CACHE_SIZE`.
- `CYCLE_FLAG`.
- Active Hibernate optimizer and `allocationSize`.
- Whether the runtime user has `SELECT` privilege.

### 12.4. Testing NEXTVAL

You can test `NEXTVAL` in test environments or controlled verification steps. In production, remember `NEXTVAL` consumes a value that does not roll back. Log any test invocation and never treat `NEXTVAL` as a read-only check.

## 13. Sequences After Migration or Data Import

### 13.1. Common Issue

Data Pump can import tables and primary-key data without synchronizing sequences past `MAX(primary key)` as expected. When the application resumes inserting, the sequence emits already-used values and triggers `ORA-00001`.

### 13.2. Checking MAX(id)

```sql
SELECT MAX(order_id) AS max_order_id
FROM app.orders;
```

Retrieve sequence metadata:

```sql
SELECT increment_by,
       cache_size,
       cycle_flag,
       order_flag,
       last_number
FROM all_sequences
WHERE sequence_owner = 'APP'
  AND sequence_name = 'ORDERS_SEQ';
```

Do not merely compare `MAX(id)` with `LAST_NUMBER`, because pooled optimizers may require a specific block boundary and Oracle caching prevents `LAST_NUMBER` from reflecting the live `NEXTVAL`.

### 13.3. Safe Reconciliation Procedure

1. Identify all tables/entities using the sequence.
2. Identify the active optimizer and `allocationSize`.
3. Stop all writers and drain transactions.
4. Confirm no JVM still holds an ID block.
5. Compute the next optimizer-aligned boundary strictly above all imported IDs.
6. Adjust the sequence using a method supported by your Oracle release.
7. Restore `INCREMENT BY` to match the allocation protocol.
8. Clear stale caches per procedure/DDL if required.
9. Start all application instances uniformly.
10. Test inserts and confirm zero unique constraint violations.

### 13.4. ALTER SEQUENCE RESTART

Some Oracle releases support sequence restart syntax; availability and syntax depend on release. If using it, consult official docs for your exact version and ensure the restart value aligns with the optimizer.

On releases without direct restart support, a controlled increment-adjustment procedure may be needed to advance the sequence before restoring the target increment. Never run generic scripts blindly in production, as `pooled` and `pooled-lo` interpret boundaries differently.

### 13.5. Why Stop All Application Instances?

A JVM may still hold unused IDs from a block fetched before the sequence was reset. Resetting the sequence into that range or changing the increment lets old and new blocks overlap. Stopping writers and restarting all instances clears in-memory allocation state.

### 13.6. Never Reset a Sequence Below Existing Data

Never set `START WITH 1` or restart to a low value when a table already holds rows. Never drop and recreate a sequence while the application is running. Sequence resets are migration operations requiring a maintenance window and rollback plan.

## 14. Changing allocationSize in a Running System

### 14.1. Changing from 1 to 50

This change requires synchronizing:

- Annotation `allocationSize`.
- Oracle `INCREMENT BY`.
- Hibernate optimizer behavior.
- All running application instances.
- Stored procedures or external writers using the sequence.

### 14.2. Changing from 50 to 1

Decreasing `allocationSize` is also a protocol change. Old JVMs may still hold cached blocks. Never just edit the annotation and rolling-restart pods one by one while the sequence increment has changed.

### 14.3. Two-Phase Deployment

A safe rollout typically requires:

1. Preparing the DDL and new mapping release.
2. Scheduling a simultaneous writer stop/drain.
3. Applying the sequence DDL change.
4. Deploying all application instances with the updated mapping.
5. Starting up and verifying.

If stopping all writers is impossible, design a dedicated compatibility protocol or introduce a new sequence for the new version; never assume two allocation sizes are safe to run side by side.

### 14.4. Version Control

Keep the sequence DDL in Flyway/Liquibase migrations and the Java mapping in the same pull request/release. Review both changes as one unit. Document migration execution order and application restart timing.

## 15. Performance and Choosing allocationSize

### 15.1. When to Choose 1?

Choose `allocationSize` 1 when:

- Insert traffic is moderate.
- Multiple heterogeneous writers need to call the sequence directly.
- Operational simplicity is prioritized.
- Avoiding optimizer changes during migrations.
- No benchmark shows large allocation blocks provide a meaningful gain.

### 15.2. When to Choose 20, 50, or 100?

Larger blocks reduce sequence round trips. Choose based on:

- Insert throughput.
- Number of application instances.
- Network latency between app and database.
- Entities created per process before restart.
- Autoscaling churn rate.
- Tolerance for ID gaps.
- Number of writers sharing the sequence.

No single `allocationSize` is optimal for every app. The JPA default of 50 is a specification default, not a universal performance rule.

### 15.3. Benchmarking

Measure at least:

- Insert throughput (rows/second).
- P50/P95/P99 insert transaction latency.
- `SELECT NEXTVAL` call counts.
- Database round trips.
- CPU/network utilization.
- JDBC batch effectiveness.
- Unique constraint violations.
- Behavior across application restarts.

Keep dataset, schema, indexes, transaction sizes, and concurrency constant when comparing.

### 15.4. Sequence Cache Tuning

Benchmark `allocationSize` and Oracle `CACHE` separately. Change one parameter at a time to see whether gains come from application block allocation or database sequence caching. Do not set `CACHE` huge solely because `allocationSize` is large.

### 15.5. Multi-Node Performance

Pooled allocation reduces `NEXTVAL` calls per node. However, higher node counts also waste more unused blocks during autoscaling events. Balance block size against pod lifetimes and actual insert rates.

## 16. Common Errors and Troubleshooting

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| `ORA-02289` sequence does not exist | Wrong schema/name or missing privilege | `ALL_SEQUENCES`, grants, synonyms |
| `ORA-01031` insufficient privileges | Runtime user lacks `SELECT` on sequence | Test using exact application user |
| `ORA-00001` unique constraint violated | Sequence below `MAX(id)`, block mismatch, or bad writer protocol | `MAX(id)`, increment, optimizer, and all writers |
| Hibernate reports sequence increment mismatch | `allocationSize` differs from `INCREMENT BY` | Compare mapping, Hibernate version, `ALL_SEQUENCES` |
| Large ID jumps | Allocation blocks, rollbacks, restarts, or Oracle `CACHE` | Review optimizer and lifecycle |
| Pod restarts create gaps | Unused ID blocks discarded | Normal behavior for pooled allocation |
| Sequence hits `MAXVALUE` | Low `MAXVALUE` or unsuitable `CYCLE`/limits | `ALL_SEQUENCES`, sequence design |
| Native SQL inserts cause conflicts | Native writer ignores pooled protocol | Audit shared sequence usage |
| Works on one node, fails across multiple nodes | Mismatched mapping/optimizer or schema across nodes | Compare config/runtime versions across all pods |
| Duplicate IDs appear after import | Sequence not advanced past imported data | Check `MAX(PK)`, perform controlled sequence reset |
| Schema validation misses runtime error | `validate` does not check all sequence behaviors/permissions | Test `NEXTVAL` as runtime user and integration test |

### 16.1. ORA-00001 After Cutover

Do not blindly bump the sequence immediately. First:

1. Identify the failing constraint and table.
2. Inspect the duplicate ID value.
3. Check `MAX(primary key)`.
4. Identify the sequence generator and optimizer.
5. Check sequence increment and cache.
6. Check whether any JVMs still hold old blocks.
7. Identify native writers or other services.
8. Stop writers and reconcile the sequence following the proper protocol.

### 16.2. Hibernate Mismatch at Startup

Record:

- Hibernate ORM version.
- Annotation `allocationSize`.
- Physical sequence `INCREMENT_BY`.
- Active optimizer.
- Increment mismatch strategy.

Fix the DDL or mapping via migration. Never disable validation before finding the root cause.

## 17. Integration and Concurrency Testing

### 17.1. Single-Instance Testing

Create multiple entities, flush/commit, and verify:

- IDs are non-NULL.
- Primary keys are unique.
- The sequence object resides in the right schema.
- Zero privilege errors.
- ID generation still works after transaction rollbacks.

### 17.2. Multi-Instance Testing

Run at least two Spring Boot instances connected to the Oracle test schema. Insert entities concurrently across multiple transactions and confirm zero duplicate IDs.

### 17.3. Restart Testing

1. Have instance A reserve a block.
2. Create a subset of entities.
3. Stop instance A before exhausting the block.
4. Restart A and continue inserting.
5. Confirm zero duplicates; gaps are expected.

### 17.4. Rollback Testing

Create an entity, obtain its ID, and roll back the transaction. The next insert receives a different ID rather than reusing the rolled-back ID. Tests must treat this as normal behavior.

### 17.5. Native Writer Testing

If native SQL or stored procedures also call the sequence, run them concurrently with Hibernate writers. Confirm the shared sequence protocol prevents overlaps, including across application restarts and partial blocks.

### 17.6. Migration Testing

Import a dataset with IDs higher than the current sequence value, then run sequence reconciliation before cutover. Test inserts using the exact application runtime user across multiple nodes.

## 18. Complete Example: Spring Boot + Oracle

### 18.1. DDL

Choosing `allocationSize` 50 with a matching pooled optimizer:

```sql
CREATE TABLE APP.ORDERS (
    ORDER_ID NUMBER(19) NOT NULL,
    CUSTOMER_ID NUMBER(19) NOT NULL,
    ORDER_STATUS VARCHAR2(30 CHAR) NOT NULL,
    TOTAL_AMOUNT NUMBER(18, 2) NOT NULL,
    CONSTRAINT PK_ORDERS PRIMARY KEY (ORDER_ID)
);

CREATE SEQUENCE APP.ORDERS_SEQ
    START WITH 1
    INCREMENT BY 50
    CACHE 100
    NOCYCLE;
```

If the runtime user differs from `APP`:

```sql
GRANT SELECT ON APP.ORDERS_SEQ TO APP_RUNTIME;
GRANT SELECT, INSERT, UPDATE, DELETE ON APP.ORDERS TO APP_RUNTIME;
```

### 18.2. Entity

```java
@Entity
@Table(name = "ORDERS", schema = "APP")
@SequenceGenerator(
    name = "orders_seq_gen",
    sequenceName = "ORDERS_SEQ",
    schema = "APP",
    initialValue = 1,
    allocationSize = 50
)
public class Order {

    @Id
    @GeneratedValue(
        strategy = GenerationType.SEQUENCE,
        generator = "orders_seq_gen"
    )
    @Column(name = "ORDER_ID")
    private Long id;

    @Column(name = "CUSTOMER_ID", nullable = false)
    private Long customerId;

    @Column(name = "ORDER_STATUS", nullable = false)
    private String status;

    @Column(name = "TOTAL_AMOUNT", nullable = false)
    private BigDecimal totalAmount;

    protected Order() {
    }
}
```

### 18.3. Repository

```java
public interface OrderRepository extends JpaRepository<Order, Long> {
}
```

### 18.4. Service

```java
@Service
public class OrderService {

    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Long createOrder(
            Long customerId,
            BigDecimal amount
    ) {
        Order order = new Order();
        // Populate business fields via constructor/factory or setters.
        return repository.save(order).getId();
    }
}
```

The service snippet illustrates where the repository is invoked; production entities need appropriate constructors/factories and validation. ID assignment can occur before commit, so allocated IDs are still discarded if the transaction rolls back.

### 18.5. Checking the Sequence

```sql
SELECT sequence_owner,
       sequence_name,
       increment_by,
       cache_size,
       cycle_flag,
       order_flag,
       last_number
FROM all_sequences
WHERE sequence_owner = 'APP'
  AND sequence_name = 'ORDERS_SEQ';
```

Compare `INCREMENT_BY` with `allocationSize` 50 and Hibernate's optimizer.

### 18.6. Checking Data

```sql
SELECT COUNT(*) AS row_count,
       MIN(order_id) AS min_id,
       MAX(order_id) AS max_id
FROM app.orders;
```

`MAX_ID` provides a baseline when checking sequences after an import, though calculating the next boundary depends on the optimizer. Never treat `LAST_NUMBER` as the exact live value.

## 19. Runbook for Changing Sequence Allocation

### Before the Change

- Identify every entity and service using the sequence.
- Record `allocationSize` and Hibernate version for each service.
- Identify the active optimizer.
- Record Oracle `INCREMENT BY`, `CACHE`, `ORDER`, and `CYCLE`.
- Locate any stored procedures/native writers.
- Check `MAX(primary key)` for all affected tables.
- Prepare DDL and a rollback/forward-fix plan.

### During the Change

1. Put the application into maintenance/drain mode.
2. Stop all writers and wait for active transactions to finish.
3. Confirm no process holds cached allocation blocks.
4. Execute sequence DDL per Oracle release.
5. Deploy uniform mappings across all instances.
6. Start application instances.
7. Run insert tests and verify constraints.

### After the Change

- Check Hibernate startup logs.
- Verify the runtime user has `SELECT` on the sequence.
- Test concurrent inserts across multiple pods.
- Verify sequence increment and cache settings.
- Monitor for `ORA-00001`, `ORA-02289`, and insert latency.
- Document the updated configuration in the runbook.

## 20. Design Checklist

- [ ] Chosen `GenerationType.SEQUENCE` or `IDENTITY` per schema and Hibernate version.
- [ ] Explicitly declared generator `name` and physical `sequenceName`.
- [ ] Identified the schema owning the sequence.
- [ ] Explicitly configured `allocationSize`.
- [ ] Verified the active Hibernate optimizer.
- [ ] Aligned Oracle `INCREMENT BY` with the allocation protocol.
- [ ] Avoided confusing `allocationSize` with Oracle `CACHE`.
- [ ] Configured `NOCYCLE` for primary-key sequences.
- [ ] Evaluated `ORDER`/`NOORDER` against real requirements.
- [ ] Granted `SELECT` privilege on the sequence to the runtime user.
- [ ] Avoided confusing synonyms with privileges.
- [ ] Ensured all application instances use compatible mappings.
- [ ] Inventoried native SQL/stored procedure writers.
- [ ] Managed sequence DDL with Flyway/Liquibase.
- [ ] Prevented production from relying on Hibernate `ddl-auto` `update` to alter sequences.
- [ ] Planned sequence reconciliation after data imports.
- [ ] Established a coordinated rollout procedure for changing `allocationSize`.
- [ ] Tested concurrently across multiple application instances.
- [ ] Tested rollbacks, restarts, and unused blocks.
- [ ] Confirmed ID gaps are acceptable for surrogate keys.
- [ ] Avoided using sequences for gapless business document numbers.

## 21. Self-Check Questions

1. What problem do Oracle sequences solve when multiple sessions generate keys concurrently?
2. How do `name` and `sequenceName` in `SequenceGenerator` differ?
3. What is the JPA default value for `allocationSize`?
4. Why should `allocationSize` always be declared explicitly?
5. How does `GenerationType.SEQUENCE` differ from `GenerationType.IDENTITY`?
6. How does `allocationSize` differ from JDBC batch size?
7. How do Hibernate optimizers `none`, `hilo`, `pooled`, and `pooled-lo` differ?
8. Why can't you deduce `INCREMENT BY` from `allocationSize` alone without knowing the optimizer?
9. When using `pooled`/`pooled-lo` with `allocationSize` 50, how should the Oracle sequence typically increment?
10. How can an increment mismatch cause startup failures or ID overlaps?
11. Why shouldn't you disable sequence increment mismatch validation to hide errors?
12. At which layers do Oracle `CACHE` and JPA `allocationSize` differ?
13. Why does `NOCACHE` not guarantee a gapless sequence?
14. How does a transaction rollback affect `NEXTVAL`?
15. Why do sequence IDs not guarantee commit order?
16. How do `ORDER` and `NOORDER` differ?
17. Why do primary-key sequences normally use `NOCYCLE`?
18. What must multiple Spring Boot replicas sharing a sequence agree on?
19. Why can rolling-deploying an `allocationSize` change be dangerous?
20. How must native SQL writers coordinate with a Hibernate pooled generator?
21. What privilege does a runtime user need to call a sequence in another schema?
22. Why doesn't a synonym automatically grant sequence privileges?
23. Is `ALL_SEQUENCES.LAST_NUMBER` the exact next `NEXTVAL`?
24. Why must all writers be stopped before resetting a sequence?
25. What inputs are needed to reset a sequence after a Data Pump import?
26. Why are unused sequence allocation blocks lost on JVM restarts?
27. What tests prove ID uniqueness across multiple application instances?
28. Why are sequences unsuitable for mandatory gapless document numbers?
29. How should responsibilities be divided between Flyway/Liquibase and Hibernate `ddl-auto`?
30. When `ORA-00001` happens after cutover, in what order should you investigate?

**Key principle:** `SequenceGenerator.name` is the logical name and `sequenceName` is the Oracle object; `allocationSize` is the ID block managed by the JPA provider, whereas `CACHE` caches sequence values inside Oracle. With Hibernate `pooled`/`pooled-lo`, `INCREMENT BY` must match the allocation protocol and all writers must coordinate. Gaps after rollbacks or restarts are normal; sequences do not guarantee gapless numbering or commit order. When changing `allocationSize` or resetting sequences after migration, stop all writers, drain old JVM blocks, update DDL and mappings synchronously, and test across multiple instances before reopening traffic.
