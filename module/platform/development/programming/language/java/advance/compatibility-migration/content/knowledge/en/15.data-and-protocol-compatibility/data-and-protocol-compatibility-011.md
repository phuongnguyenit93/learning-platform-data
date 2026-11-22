# Rollback conditions when data has already been written by the new version

A Java/JDK upgrade or application version deployment plan often includes the statement “if an issue occurs, roll back to the old version”. That statement is only true when **the old version still understands and safely handles all data, messages, and state created by the new version**. If the new version has written an unprecedented enum state, used a new serialization format, changed the meaning of a column, or emitted events that the old consumer does not recognize, bringing back the old JAR or container image can make the incident more severe.

**Code rollback does not equal data rollback.** Swapping an application artifact usually only replaces the running program. The database, event log, object storage, cache, pending messages, checkpoints, and side effects in external systems still retain the state created by the new version. Safe rollback requires controlling these states as well.

This lesson presents the conditions for version N-1 to run again after version N has written data, how to identify changes that cannot be rolled back, cross-version testing procedures, phased rollout strategies, and runbooks for handling situations where rollback is no longer safe.

## 1. Clarifying what “rollback” means

A Java system typically has multiple layers with independent lifecycles:

~~~text
Application image / JAR         May switch N -> N-1
         |
         v
Database schema                 May have already been migrated
         |
         v
Database records                May already contain new-format data
         |
         v
Event stream / message queue    May have already emitted new event format
         |
         v
Cache / object storage          May have already stored new serialization
         |
         v
External systems                May have already received transactions / side effects
~~~

When asking “can we roll back?”, you must specify **which artifact or layer is being rolled back**:

- **Application rollback:** re-running the N-1 binary/config; does not automatically alter data.
- **Schema rollback:** reversing one or more database schema changes, if the migration is actually reversible.
- **Data rollback:** returning records to a state compatible with N-1 via conversion, backup restore, or compensating operations.
- **Protocol rollback:** reverting producers/consumers to a message format that older versions understand.
- **Business process rollback:** compensating for or reversing external side effects that have already occurred, such as sending emails, processing payments, or updating other systems.

These types of rollback cannot be collapsed into a single deployment command. For example, a database that already has new rows from version N might not require a schema rollback, yet N-1 still cannot read the newly written status value. Conversely, N-1 might read the new data but write the record back using old logic and erase the new information.

### 1.1. Four forms of compatibility to distinguish

| Type | Question | Error examples |
|---|---|---|
| Binary compatibility | Can the N-1 binary run on the deployed JDK/dependencies? | `UnsupportedClassVersionError`, `NoSuchMethodError`. |
| Schema compatibility | Can N-1 connect to and operate against the current schema? | Column renamed, new constraint rejects old queries. |
| Data/behavioral compatibility | Does N-1 understand the values and meaning of records written by N? | New enum unrecognized, currency unit changed. |
| Protocol compatibility | Can N-1 read/write messages, events, and cache formats produced by N? | Incompatible JSON/Protobuf/Java serialization. |

Upgrading the JDK can also change behavior for time handling, charset, locale, Unicode, serialization, or security libraries. Those changes must be factored into rollback even when the application schema has not changed on paper.

## 2. Core condition: N-1 must safely handle data created by N

Assume the two application versions are:

- **N-1:** the incumbent version, which may be redeployed if an incident occurs.
- **N:** the version being tested or recently released.

Let `D_N` be the set of data states that N can write during the rollout window. To perform a **code-only rollback** from N to N-1 without modifying data, at least the following guarantees are required:

1. **Readable:** N-1 can read and parse every state in `D_N` without failing.
2. **Understood accurately:** N-1 interprets the data with compatible business meaning, not merely skipping failing fields.
3. **Processable:** N-1 can still execute required business flows with that data.
4. **Safely writable:** if N-1 updates a record created by N, it does not silently delete, misconvert, or corrupt data added by N.
5. **No broken invariants:** constraints on monetary amounts, states, uniqueness, references, and authorization remain upheld.
6. **Side effects manageable:** events, queues, checkpoints, caches, and interactions with other services continue operating with the old binary.
7. **Runnable environment:** N-1 remains compatible with the JDK, configuration, libraries, database driver, and infrastructure still present after rollout.

These are the conditions **requiring evaluation** for a code-only rollback. They do not guarantee that every feature automatically works flawlessly; the team must test the business paths and states that can occur.

### 2.1. “Readable” does not mean “safe”

Suppose N adds a `fraudReviewReason` field to an order's JSON. N-1 is configured to ignore unknown fields, so it does not throw an exception. From the outside, N-1 is “able to read it”.

However, if N-1 deserializes the JSON into an old DTO and then serializes the entire object back when updating the shipping address, the `fraudReviewReason` field may be lost. The rollback may succeed at startup yet cause **silent data loss** when users edit orders.

Therefore, you must verify the **read–modify–write round trip**, not just one-way parsing.

### 2.2. “Not throwing an exception” is also insufficient

Suppose N adds a status:

~~~text
PENDING_FRAUD_REVIEW
~~~

N-1 does not have this status, but has a default branch treating “any unknown status as APPROVED”. It does not crash, yet it may allow an unreviewed transaction to proceed.

This is a more severe business/security bug than an explicit parse error. **Fail closed** on unrecognized states is usually safer than interpreting them as an allowed state.

### 2.3. Two questions that must be answered before rollout

- *Does version N produce any new state that N-1 has never seen?*
- *If N-1 sees and subsequently writes back that state, what will happen?*

If these two questions have not been answered with tests and evidence, you cannot declare a “safe rollback”.

## 3. Data changes that commonly block rollback

### 3.1. New enum values

Old version:

~~~java
enum OrderStatus {
    CREATED, PAID, SHIPPED, CANCELLED
}
~~~

New version:

~~~java
enum OrderStatus {
    CREATED, PAID, PENDING_FRAUD_REVIEW,
    SHIPPED, CANCELLED
}
~~~

If the database stores the status as a string and N writes `PENDING_FRAUD_REVIEW`, the old code may fail:

~~~java
OrderStatus status =
    OrderStatus.valueOf(dbValue);
~~~

When `dbValue` is the new name, `valueOf` throws `IllegalArgumentException`. If JSON maps directly into an enum, the deserialization library can also throw an error upon encountering an unknown value.

The solution must be prepared **before N is permitted to write the new state**: deploy N-1+, a version compatible with unknown values that handles them safely, or lock creation of the new state behind a feature flag until the rollback window closes. You cannot fix an already-released N-1 simply by changing N's configuration.

### 3.2. Adding a new field with mandatory meaning

For example, N adds `currency` and enables payments in multiple currencies. Previously, N-1 implicitly treated every amount as VND. If N writes:

~~~json
{
  "orderId": "O-100",
  "amount": 125,
  "currency": "USD"
}
~~~

N-1 can parse `amount=125` without knowing the USD unit and process it as 125 VND. This is **semantic incompatibility**, even though the JSON parses cleanly.

To allow rollback, you cannot simply add a default field back. You must ensure the old version never receives records with a currency it does not understand, or has already been upgraded to handle multi-currency before N writes them.

### 3.3. Changing units or encoding

Changing from `amountCents` to `amountDecimal` may require data conversion; changing from Unix timestamps in milliseconds to microseconds can cause old code to miscalculate times even though the data type remains `long`.

Such “same type, different meaning” changes are especially dangerous because there is not always a compile or parse error to warn you.

### 3.4. Renaming/deleting columns or fields

If N drops the `customer_name` column after moving data to `given_name` and `family_name`, N-1 may fail because its SQL still accesses `customer_name`.

Even if the schema keeps the old column while N stops updating it, N-1 may read missing or stale data. Keeping the column name is **not enough**; you must also preserve its meaning and consistency.

### 3.5. New database constraints

N may apply `NOT NULL`, foreign keys, unique indexes, enum types, or new CHECK constraints. When rolling back to N-1, a previously valid INSERT/UPDATE statement may be rejected.

An example:

~~~sql
-- Old schema allows writing orders without review_state yet.
ALTER TABLE orders
  ADD COLUMN review_state VARCHAR(30);

-- If NOT NULL is later enforced while N-1 does not write this column:
ALTER TABLE orders
  ALTER COLUMN review_state SET NOT NULL;
~~~

On database engines supporting this syntax (such as PostgreSQL), the last statement can cause N-1's INSERT to fail if it does not supply `review_state` and the column lacks a suitable default.

The *contract* step should not be executed before all binaries eligible for rollback support the new schema.

### 3.6. Serialization format and version

Java native serialization, JSON, Avro, Protobuf, CBOR, Kryo, binary caches, or custom structures each have different compatibility rules. A version N writing new data that N-1 cannot deserialize can turn a cache, queue, or database blob into a “time bomb” after rollback.

With Java serialization, `serialVersionUID` and class structure changes can affect compatibility; keeping `serialVersionUID` does not automatically guarantee all changes are safe. With Protobuf, adding new fields can work cleanly if field numbers, wire types, and unknown fields are managed properly, whereas changing a field's meaning or reusing an old field number is a major risk. If routed through intermediate JSON or conversion libraries, unknown fields can be dropped upon write-back.

### 3.7. Event versions and consumption state

If N emits new events to Kafka or a message broker that N-1 does not understand, rolling back the producer/consumer does not automatically erase events already published.

N-1 may:
- Fail continuously when reading a new event.
- Send messages to a dead-letter queue.
- Ignore critical data, causing downstream state drift.
- Record incorrect offsets/checkpoints.
- Reprocess events, causing duplicate transactions if the consumer is not idempotent.

Therefore, event compatibility is a rollback condition independent of the primary database schema.

## 4. End-to-end example: an order with a risk-review step

Suppose an order system has a Java service, an `orders` database, an event queue, and a payment-processing worker.

### 4.1. In version N-1

~~~text
CREATED --> PAID --> SHIPPED
    |
    +--> CANCELLED
~~~

Illustrative schema:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    status VARCHAR(40) NOT NULL,
    amount_minor BIGINT NOT NULL
);
~~~

Application N-1 only understands four statuses. The payment worker processes payment upon receiving the `OrderPaid` event.

### 4.2. Version N adds a pending-review status

N wants to introduce a new status:

~~~text
CREATED --> PENDING_FRAUD_REVIEW --> PAID
                                 |
                                 +--> CANCELLED
~~~

N may write:

~~~sql
UPDATE orders
SET status = 'PENDING_FRAUD_REVIEW'
WHERE id = 1234;
~~~

N also emits an event:

~~~json
{
  "eventType": "OrderReviewRequired",
  "version": 2,
  "orderId": 1234,
  "reviewReason": "RISK_SCORE_HIGH"
}
~~~

Now suppose N hits a regression related to the new JDK, and the operator immediately redeploys N-1. N-1 may:

- Fail to parse the new `status`.
- Fall into an inappropriate `default` branch.
- Fail to process the `OrderReviewRequired` event already sitting in the queue.
- Write back the order and accidentally erase the review data.
- Allow payment processing when the order ought to be awaiting review.

**Rolling back to N-1 cannot be considered safe** merely because the old JAR still starts on the current JDK.

### 4.3. Three viable approaches

**Approach A – block writing new states during the rollback window.** Deploy N's code but keep the feature flag that creates `PENDING_FRAUD_REVIEW` turned off. If rollback is needed, all data remains within the status set N-1 understands. Every write path must be tested, including APIs, batch jobs, schedulers, and consumers.

**Approach B – prepare N-1 as a rollback-compatible version beforehand.** A transitional version N-1+ is released that safely understands and handles the review status, even though the new feature is not yet enabled. Rolling back from N to N-1+ is then safer than rolling back to the original N-1.

**Approach C – build a data remediation step before rollback.** If the new status has already been written, determine whether each record can be converted back to an old status without losing meaning or violating workflow rules. If no safe mapping exists, keep the new application or a hotfix capable of reading the new data, rather than forcing data into a fake status.

For example, changing `PENDING_FRAUD_REVIEW` to `PAID` just to “stop the errors” is insecure. Changing it to `CREATED` is not automatically correct either if side effects, payments, or idempotency tasks tied to the new status have already occurred.

## 5. The expand–migrate–contract strategy for databases

A common way to preserve rollback capability is to split schema and data changes across multiple phases rather than doing everything in a single release.

### 5.1. Expand: add structures in a compatible direction

Instead of renaming a column immediately:

~~~sql
-- PostgreSQL, demonstrating new column still allowing NULL
ALTER TABLE orders
  ADD COLUMN review_state VARCHAR(30) NULL;
~~~

The old version can continue reading/writing data via the `status` column. The new version can start writing `review_state` when deployment mechanisms and timing allow.

During this phase, avoid enforcing constraints that block N-1 from writing, or stopping updates to old fields that N-1 needs.

### 5.2. Migrate: support both representations and migrate data

The new version can read both old and new representations:

~~~text
Record with only old status
        |
        v
Reader N understands and uses old data

Record with new review_state added
        |
        v
Reader N understands review_state under new business logic
~~~

If data needs to stay synchronized during the transition period, controlled dual-write, migration jobs, triggers, or an outbox can be used depending on architecture. You must designate **which field is the source of truth**, ensuring the two representations do not diverge under retries, transaction rollbacks, or concurrent writes from multiple versions.

Dual-write does not mean simply writing two fields ensures compatibility. If the new state has no equivalent in the old model, no faithful mapping can be created merely by copying data.

### 5.3. Contract: clean up old structures after the rollback window closes

Only once all consumers have migrated and rolling back to the old version is no longer required:

~~~sql
-- Illustrative only: compatibility-breaking operation,
-- do not run during the rollback window to N-1.
ALTER TABLE orders DROP COLUMN legacy_status;
~~~

The contract step may include dropping columns, changing enum types, adding mandatory constraints, removing compatibility layers, or changing event shapes. This is typically the stage **too late/hard for a code-only rollback**.

### 5.4. Phase-by-phase diagram

~~~text
T0: N-1
  Old schema, old data
        |
        v
T1: EXPAND
  Schema keeps old column + adds new nullable column
  N-1 can still read/write
        |
        v
T2: ROLLBACK-COMPATIBLE RELEASE
  Readers/consumers understand the new representation if needed
  Writing values N-1 does not understand is not enabled yet
        |
        v
T3: ROLLOUT N
  Enable feature gradually, canary
  Monitor new records/events
        |
        v
T4: CLOSE ROLLBACK WINDOW
  Announce no further code-only rollback to N-1
        |
        v
T5: CONTRACT
  Remove old structures, enable new invariants, clean up flags
~~~

The decision point at T4 must be announced explicitly: from then on, the incident plan shifts from **old-version rollback** to **roll-forward/hotfix or controlled data remediation**.

## 6. Protocol and event versions must be managed separately

Database changes are only one side of the problem; Java applications also commonly exchange data over HTTP, gRPC, message queues, object storage, and caches.

### 6.1. Old readers must tolerate data produced by new writers

For a JSON API, adding a new field can be compatible with consumers that ignore unknown fields. However, do not assume compatibility if the consumer performs strict schema validation or serializes the whole object back.

Example event v1:

~~~json
{
  "eventType": "OrderPaid",
  "orderId": 42,
  "amountMinor": 120000
}
~~~

Event v2:

~~~json
{
  "eventType": "OrderPaid",
  "orderId": 42,
  "amountMinor": 120000,
  "currency": "VND",
  "riskReview": "PASSED"
}
~~~

An old consumer may ignore `currency`, but if N later writes `currency=USD`, the old consumer may misinterpret `amountMinor`. Syntactically valid schema evolution does not guarantee semantic compatibility.

### 6.2. New events require defining how old consumers handle them

There are three main scenarios:

1. **Old event type, new compatible field:** old readers can ignore the field only if it does not break the old meaning.
2. **New event type:** old readers need a defined policy: safely ignore, halt processing, route to DLQ, or never be delivered that event.
3. **Old event with changed semantics:** the most dangerous case, because old readers can silently process it incorrectly.

For long-retention streams, an event generated during a few minutes of canary traffic may be replayed months later. The rollback plan must account for already-published data, not just events arriving after the old image is brought back up.

### 6.3. Producer/consumer compatibility matrix

| Producer | Consumer | Required test |
|---|---|---|
| N-1 | N-1 | Legacy flows continue working |
| N-1 | N | N understands historical events/data |
| N | N | New flows work properly |
| **N** | **N-1** | **Mandatory condition if rolling back to N-1 while N's events still exist** |

The last row is the case most easily overlooked in CI pipelines because many teams only test N against N or N against old data.

### 6.4. Formats with a schema registry

With Avro, Protobuf, or formats backed by a schema registry, the team must determine the actual compatibility policy:

- Forward compatibility: old readers can read data from new writers under a specific contract.
- Backward compatibility: new readers can read data from old writers.
- Full compatibility: both directions must be satisfied according to the enforced rules.

Even if the registry accepts the schema, you must still test how the application handles new **values**, unknown enums, nulls, defaults, event-ordering consistency, and side effects.

With Protobuf, do not reuse removed field numbers, properly reserve field numbers/names, and check how libraries or conversion steps preserve unknown fields. With Java enums or string mappings, verify whether the logic handling unknown values is truly safe.

## 7. Read–modify–write: a test often more important than read-only

Version N-1 may be able to read a v2 record yet corrupt data when writing it back.

Example in JSON:

~~~json
{
  "id": 42,
  "name": "Minh",
  "riskReview": {
    "decision": "REVIEW",
    "explanation": "Requires manual approval"
  }
}
~~~

Old model:

~~~java
public class CustomerRecordV1 {
    public long id;
    public String name;
}
~~~

If the old serializer ignores unknown fields and the old code reads and then overwrites the entire record:

~~~text
JSON v2 -> DTO v1 -> update name -> JSON v1
~~~

then `riskReview` will disappear if the entire storage payload is replaced. If the system uses database columns and SQL updating only `name`, data in the new column may survive, but you must not assume every ORM or API behaves that way.

### 7.1. Behaviors to determine for the old reader

- Does it fail explicitly on unknown fields/enums or silently ignore them?
- Does it write back the entire object or only changed fields?
- Does it use ORM entity merge/full replacement?
- Does it re-serialize objects back into a queue or cache?
- Does it preserve unknown fields or extension data?
- Does it compute derived values from portions of data it does not understand?
- Does it use optimistic locking/a version column to detect concurrent overwrites?

### 7.2. A meaningful test case

~~~text
1. N creates a valid record containing new fields/values
2. N-1 reads that record
3. N-1 modifies a field it understands
4. N-1 writes the record back
5. N reads the final record
6. Verify the data added by N remains intact and invariants hold
~~~

If step 2 succeeds but step 6 fails, **code-only rollback is unsafe for that write path**.

## 8. Rollback with multiple instances and concurrent writes

Systems using rolling deployments typically run N and N-1 concurrently. This is the point when data gets mixed between the two versions even before a rollback incident happens.

~~~text
Load balancer
     |
     +--> Instance N-1 --\
     |                   +--> Shared DB / Queue
     +--> Instance N ----/
~~~

Issues to check:

- Does N write new values as soon as it starts serving requests?
- Does N-1 read records just written by N?
- Does N-1 update those records and drop new fields?
- Do background jobs on N-1 process queue items emitted by N?
- Is there a lagging instance or a batch job running an older version?
- Are there race conditions from two versions maintaining two interpretations of state?

A service that is unsafe when running two versions against a shared data store may require a different rollout strategy: **deploy compatible readers first**, and only then enable writers producing the new format. Sending only a small percentage of canary traffic does not guarantee safety if the canary can write into a shared table read by all old instances.

### 8.1. Feature flags and when to enable the new writer

Separate **deploying N** from **activating new writes**:

~~~text
Deploy N with code supporting the new format
           |
           v
New-write flag = OFF
           |
           v
Verify reading/writing old data on N
           |
           v
Update N-1 fallback if needed
           |
           v
Enable new-write flag by cohort
           |
           v
Monitor new records/events and rollback gate
~~~

The flag must control **all write paths**: APIs, schedulers, consumers, batch jobs, administrative tools, and migration scripts. If you only disable a UI feature while a background consumer keeps emitting new events, rollback capability can still be lost.

### 8.2. Controlling rollback by data state

For automated deploy controllers, distinguish between:

- **rollbackAllowed:** can revert to N-1 code-only.
- **newWritesEnabled:** permitted to create new states.
- **rollbackGateClosed:** incompatible state has been written; automatic rollback to N-1 is no longer allowed.
- **dataRemediationRequired:** requires a data remediation process or roll-forward.

These values must rely on trustworthy data sources and determination logic; they should not depend solely on a Boolean flag self-reported by one instance, because distributed systems also involve latency, caches, and asynchronous batches. The gate must evaluate evidence of records/events actually created and write paths that have not yet stopped.

## 9. Data may be irreversible despite a “down migration” script

Having both `up` and `down` migration files does not prove data rolls back safely.

### 9.1. Lossy type changes

For instance, N rounds monetary amounts from the smallest unit or changes precision. If data has been rounded or truncated, no inverse conversion completely restores the original value.

### 9.2. Merging multiple states into one

N maps several legacy statuses into a single new status; afterward, it is unknown which status each record belonged to previously. Reversing the schema does not recover the lost distinction.

### 9.3. Deleting or re-encrypting data

If N deletes a field holding critical information, rotates encryption keys, or migrates data without retaining the original, running a down migration may fail to restore the lost values.

### 9.4. External side effects

If N has already dispatched payment requests or emails, rolling back the database does not automatically recall them. A **compensating action** may be required, but compensation is not the same as rewinding time: a refund transaction is still different from a payment that never occurred.

### 9.5. Backup restore is not zero-loss rollback

Restoring a pre-rollout snapshot can bring the database back to a state N-1 understands, while simultaneously **losing valid writes** created after the snapshot timestamp unless appropriate recovery/forward-replay and reconciliation mechanisms exist.

Before treating this as an option, determine:

- **RPO (Recovery Point Objective):** acceptable level of data loss.
- **RTO (Recovery Time Objective):** acceptable downtime duration.
- Are backups/snapshots consistent between the database and event logs?
- Can valid transactions be replayed idempotently?
- Have side effects in other services been reconciled?
- Who holds authority to approve data loss or business compensation?

`restore backup` should not be treated as a “self-evidently safe” step inside a deployment script.

## 10. Strategies when N has already written incompatible data

Once code-only rollback no longer meets its preconditions, several handling paths exist. The option must be chosen based on real impact, not a desire to return to the old version at all costs.

### 10.1. Roll-forward via hotfix

Keep a version capable of understanding the new data, and release a patch for the regression causing the incident.

Pros: avoids forcing data back into the old representation, often appropriate when N has produced irreversible new state.

Cons: requires a team capable of fixing and releasing quickly; the patch must also be tested against already-written data.

### 10.2. Roll back to a data-compatible N-1+ version

If a fallback version was prepared beforehand that understands new data/events without enabling the regression-causing features, deploy that instead of the original N-1.

Pros: restores stable logic while preserving v2 data.

Cons: requires advance preparation; you cannot assume the old binary automatically reads every new state.

### 10.3. Isolate new data and stop writers

If only a small cohort has v2 data, you can stop writes, split traffic, keep a dedicated service to read v2, or prevent N-1 from accessing those records while handling them.

Pros: limits blast radius.

Cons: increases routing, authorization, and operational complexity; unsuitable if the data has already spread through relationships and events.

### 10.4. Verified data remediation

Use only when a **meaning-preserving or business-approved** conversion exists from the new data back to a form N-1 understands.

A minimal workflow:

1. Stop writers producing the new state.
2. Take snapshots/backups and record checkpoints.
3. Query the exact affected records/events.
4. Build a mapping with invariant checks.
5. Dry-run the conversion on a copy of the data.
6. Reconcile counts, monetary totals, statuses, and relationships.
7. Obtain approval for any loss of meaning (if applicable) from the business owner.
8. Execute the conversion with audit logging, retry/idempotency, and a recovery plan.
9. Only afterward deploy N-1 and verify.

If no safe mapping exists, data remediation is not a valid option.

### 10.5. Snapshot restore with a reconciliation plan

In severe situations, restoring to a point before N wrote incompatible state may be necessary. However, you must have a plan to handle valid data created during the lost interval and reconcile events/transactions in external systems.

This is **disaster recovery**, not a routine code rollback operation. The decision must follow defined RPO/RTO and approval authority.

## 11. Rollback decision workflow during an incident

Do not rely solely on “N's healthcheck is red”. Before putting N-1 back into production, run the data and protocol gates.

~~~text
N hits an incident after rollout
          |
          v
Evidence that N wrote new state?
          |
    +-----+------+
    |            |
   No         Yes / uncertain
    |            |
    v            v
Check          Stop/lock related writers,
rollback       measure scope of new data & events
compatibility        |
    |                v
    |         Can N-1 read, process, and safely
    |         write back that data?
    |                |
    |         +------+------+
    |         |             |
    |        Yes            No
    |         |             |
    v         v             v
Code-only   Monitored    No code-only rollback
rollback    rollback     Choose hotfix, N-1+, isolation,
after gate               or verified remediation
~~~

“Uncertain whether N wrote” **must not automatically be treated as “did not write”**. Especially with queues, batches, and instances outside observability coverage, missing logs are not proof that no changes occurred.

### 11.1. Operational steps before rollback

- Block or throttle traffic generating new writes if consistent with the incident plan.
- Disable feature flags and background writers producing incompatible state.
- Check in-flight requests, open transactions, in-flight messages, and retries.
- Record rollout start time, which N instances received traffic, and the count of new records/events.
- Take a consistency-appropriate snapshot before altering data.
- Verify N-1 remains compatible with the running schema and infrastructure.
- Decide on code-only rollback or an alternative recovery path based on evidence.

Turning off a feature flag in a control plane does not prove all writers have stopped. Actual status must be confirmed on workers, schedulers, and external connections.

### 11.2. After rolling back

Check at minimum:

- N-1 starts up and reads remaining new data.
- Critical requests succeed, not just the health endpoint.
- No spike in parse errors, unknown enums, or DB constraint violations.
- Queue consumers are not stuck on poison messages or growing DLQs.
- No loss of v2 fields when N-1 updates records.
- Business invariants, monetary values, and states remain consistent.
- A plan is in place for v2 data that cannot be processed immediately.

Completing a deployment rollback does not mean the incident is over.

## 12. Mandatory testing matrix for rollback

To prove N-1's ability to handle data written by N, prepare an environment with copies of the schema, representative data, queues, and service dependencies.

| Test | Setup | Expected outcome |
|---|---|---|
| Old reader ↔ old data | N-1 reads N-1 data | No baseline regression |
| New reader ↔ old data | N reads N-1 data | Legacy data supported |
| New reader ↔ new data | N creates and reads N data | New features work properly |
| **Old reader ↔ new data** | **N writes, N-1 reads** | **No crashes/misinterpretation** |
| **Old writer ↔ new data** | **N writes, N-1 updates, N reads back** | **No lost fields, no broken invariants** |
| Mixed-version writes | N and N-1 concurrently write to shared store | No races causing state drift |
| Consumer downgrade | N emits event, consumer N-1 reads | Handled or rejected per policy |
| Replay/history | N-1 replays log/snapshot containing N events | No duplicate side effects or stalls |
| Cache downgrade | N writes cache, N-1 reads | No deserialization error or handled via invalidation |
| Schema rollback check | N-1 runs on post-migration schema | All key SQL/read/write paths keep working |
| Failure-injection | N stops mid-migration/dual-write | Recovery and reconciliation remain feasible |

### 12.1. Decisive format tests

A single “serialize and immediately deserialize inside N” test is not enough. Store *golden fixtures* generated by each writer version and run readers from the versions actually still supported.

For example, with JSON:

~~~text
fixtures/
  orders-v1.json
  orders-v2-with-new-field.json
  orders-v2-with-new-enum.json
  orders-v2-null-and-defaults.json
~~~

For Java serialization, store binary fixtures across real versions, and evaluate `serialVersionUID`, class hierarchy, and `readObject`/`writeObject` if used. For Protobuf, test unknown enums/fields as well as intermediate JSON hops if the system converts formats.

### 12.2. Testing on the exact JDK and dependencies

During a Java migration, two dimensions may vary simultaneously:

~~~text
App N-1 runs old JDK
              |
              v
App N runs new JDK
              |
              v
New data is written
              |
              v
Which JDK does N-1 rollback run on?
~~~

If rolling back N-1 requires reverting to the old JDK, verify that infrastructure still supports that JDK and all new data can be handled by the old reader. If N-1 runs on the new JDK, the N-1 binary must be tested against the new JDK/dependencies. Both approaches carry distinct risks.

A test suite that records the JDK vendor/build, application version, driver, database version, and effective config helps distinguish data errors from runtime compatibility errors.

### 12.3. Testing indirect write paths

Do not test only the primary HTTP endpoint. The following paths can also create data that N-1 does not understand:

- Database migration/backfill.
- Scheduled jobs.
- Kafka/RabbitMQ consumers.
- Retry/outbox publishers.
- CDC transformations.
- Cache warming mechanisms.
- Operator scripts.
- Admin features or import/export.
- Plugins or external integration systems.

The rollback gate must account for all of these sources.

## 13. Monitoring and evidence for opening/closing the rollback window

Metrics/alerts can be established to monitor data capable of blocking rollback:

| Metric/signal | Meaning |
|---|---|
| `new_format_records_created_total` | Records in the new format already exist |
| `new_enum_values_written_total` | States N-1 may not understand have appeared |
| `event_schema_v2_published_total` | Messages under the new schema have been published |
| `old_reader_unknown_values_total` | Old reader encountered unknown values |
| `old_reader_roundtrip_failures_total` | Updating with the old writer corrupted data |
| `migration_backfill_completed` | Data transformation step has executed |
| `dual_write_mismatch_total` | The two representations are out of sync |
| `dlq_messages_total` | Consumer failed to process messages |
| `rollback_gate_state` | State permitting/forbidding code-only rollback |

Metric names are merely design suggestions. Ensure metrics reflect system truth, not merely that a line of code was invoked. Cross-check logs, DB queries, event metadata, and checkpoints when deciding on rollback.

### 13.1. Rollback window closure must be explicit

A release can be divided into:

- **Rollback-safe phase:** N has not written state beyond N-1's capabilities.
- **Conditional rollback phase:** N has written new data, but a verified conversion measure or an N-1+ fallback exists.
- **Rollback-gate closed:** N has written state that cannot be safely handled by N-1; only alternative recovery options may be used.

Closing the gate should have a responsible owner, timestamp, rationale, and notification to operations. Any auto-rollback mechanism unaware of written data should be restricted or disabled once the code-only rollback window closes.

## 14. Prepare a runbook instead of only writing “kubectl rollout undo”

A useful runbook tells operators **when rollback is allowed**, **when to stop**, and **which data to inspect**.

### 14.1. Pre-rollback decision template

~~~text
Incident ID:
N deployment timestamp:
N / N-1 versions:
Current JDK and vendor/build:
Database schema revision:
Feature flags creating new format:
Have writers stopped:
Count of N-only or undetermined records:
Count of N-only events in queue/log:
N-1 reads N data successfully:
N-1 read-modify-write preserves invariants:
External side effects reconciled:
Backup/snapshot/checkpoint:
RPO/RTO if restore is needed:
Decision: CODE-ONLY / N-1+ / ROLL-FORWARD / DATA REMEDIATION / DR
Approver:
Post-operation verification conditions:
~~~

### 14.2. Emergency stop rules

If any of the following conditions are encountered, do not automatically restore N-1 simply because it is the old image:

- N has written new enum values that N-1 handles incorrectly or does not understand.
- N has irreversibly transformed/deleted old data.
- Current DB structure rejects required write statements from N-1.
- New events or checkpoints cannot be safely processed by N-1 consumers.
- N-1 can read records, yet writing them back drops mandatory N information.
- The scope of v2 data cannot be determined while business side effects are critical.

In these cases, switch to a controlled incident response plan and preserve evidence. “Stopping rollback” does not mean abandoning the incident; it means choosing an alternative path that does not corrupt data.

## 15. Common mistakes

**“Rollback only requires swapping the image.”** False when data, schemas, events, and side effects have changed.

**“A schema migration has a down file, so it is always reversible.”** No. A down script can alter structure without recovering lost or reinterpreted data.

**“Adding a new JSON field is always backward-compatible.”** Not necessarily. Old readers may validate strictly, drop fields upon write-back, or misunderstand the meaning of the new data.

**“An unknown enum with a default branch is safe.”** Not if the default assigns the wrong business meaning. Risk states require failing closed or pre-designed compatibility mechanisms.

**“If N-1 can read N's record, rollback is safe.”** You must test N-1 updating records and check invariants after writes.

**“Canary only has 1% traffic, so new data will not affect the rest.”** If sharing a DB/queue, a single new record or event can be processed by all old instances.

**“Disabling the feature flag guarantees no new data.”** In-flight requests, background jobs, retries, and outboxes may continue writing/publishing.

**“Backups can return the system to a perfect state.”** Restores can lose valid transactions; RPO, reconciliation, and external side-effect checks are required.

**“Protobuf/Avro schema compatibility means full application compatibility.”** Valid schemas do not automatically guarantee semantic compatibility or preservation of unknown data across conversion steps.

**“If rollback fails, just run the down migration and retry.”** This can worsen data corruption. Snapshots, root-cause identification, and a verified recovery option are needed.

**“Only check data in the primary database.”** Event logs, caches, object storage, search indexes, CDC, checkpoints, and external systems can also hold state from the new version.

## 16. Rollback evaluation checklist when N has already written data

- [ ] Distinguished between code, schema, data, event, and business side-effect rollback.
- [ ] Inventoried new formats/states/enums that N can write.
- [ ] Proved N-1 accurately reads data created by N.
- [ ] Tested N-1 read–modify–write without dropping fields or breaking invariants.
- [ ] Confirmed N-1 does not assign wrong semantics to unknown values.
- [ ] Verified schema migrations do not block N-1 SQL statements.
- [ ] Defined activation timing for new-write flags and background write paths.
- [ ] Tested N and N-1 running concurrently against the shared data store.
- [ ] Checked events/messages, schema registry, and legacy consumers.
- [ ] Checked serialization/caches/object storage and related plugins.
- [ ] Tested on the exact JDKs/runtimes that rollback could target.
- [ ] Established golden fixtures, cross-version tests, and replay tests.
- [ ] Identified irreversible data transformations.
- [ ] Defined RPO/RTO and reconciliation procedures if backup restore is needed.
- [ ] Measured the scope of new data actually written during rollout.
- [ ] Confirmed feature flags and all writers can be halted.
- [ ] Announced the rollback gate and designated approver.
- [ ] Prepared roll-forward/hotfix or N-1+ fallback if N-1 is incompatible.
- [ ] Prepared post-rollback verification tests and a handling plan for remaining v2 data.

## 17. Conclusion

The most critical condition for rolling back after a new version has written data is: **the version rolled back to must continue to read, understand, process, and safely write back the states created by the new version**. Being able to start the old JAR, connect to the database, or possess a `down migration` file is not enough to prove this.

In Java Advance Compatibility Migration, treat rollback as an **end-to-end contract across code–schema–data–protocol–runtime**. Prepare schemas using expand–migrate–contract, decouple deployment from enabling new writers, test the N/N-1 matrix and especially read–modify–write, and explicitly close the rollback window once data becomes incompatible.

If new data has already been written and no meaning-preserving conversion exists, do not perform a blind code-only rollback. Safer options may then be **rolling forward with a hotfix, deploying a fallback that understands the new format, isolating the data, or performing a reconciled restore**, depending on business requirements and RPO/RTO. A good rollback plan does not just state how to revert to the old version—it also knows **when not to revert**.
