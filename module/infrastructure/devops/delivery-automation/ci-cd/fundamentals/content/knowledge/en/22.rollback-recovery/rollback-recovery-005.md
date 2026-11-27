# Verifying Data Compatibility When Running an Old Application Version

## 1. Why Can Rolling Back an Application Corrupt Data?

When a new release causes errors, operations teams often want to revert the application to the previous stable version. This action restores source code and binaries, yet databases, message queues, caches, and external data usually retain the changes created by the new version.

Here lies the critical risk: **the old application version may not understand data written by the new version**.

Examples:

- The new version writes an order status of REFUNDED, whereas the old version only recognizes PENDING, PAID, and CANCELLED.
- The new version stores JSON with a different structure; the old version fails to read a new required field or data type.
- A migration changed monetary units from smaller units to larger currency units, while the old version still treats the value as the smaller unit.
- The new version writes a record to a new table and stops updating the old table; the reverted old version reads only the old table and sees missing or stale data.
- Messages emitted by the new version have a schema that old consumers cannot decode.
- Sessions or caches hold new data that causes the old version to crash during deserialization.

Therefore, application rollback does not equal database rollback. To run an old version safely, you must verify that it can still read, write, and process currently existing data.

Within **DEVOPS_CI_CD_FUNDAMENTALS**, data compatibility verification is part of the rollback and recovery strategy. Rollback decisions must be based on the relationship between application version, current schema, generated data, artifacts, messages, and dependent systems.

## 2. What Does Data Compatibility Cover?

It is not only new table structures that affect the ability to run an old version. Multiple layers must be examined:

| Layer | Questions to check | Risk example |
|---|---|---|
| Database schema | Do old columns, tables, indexes, and constraints still exist? | Old version queries a column that was DROPped |
| Data values | Does the old version understand new values? | New enum causes a parse failure |
| Semantics | Do values still carry the meaning assumed by the old version? | Currency unit changed while old code calculates using the old unit |
| Data relationships | Are foreign keys, uniqueness, and record relationships still valid? | Old table is no longer updated |
| Serialization | Are JSON, binary, or documents still readable? | New required field or altered data type |
| Events and messages | Can old consumers decode new messages? | New event version adds an enum or changes a field |
| Cache and session | Can temporary data be read by old code? | New session object cannot be deserialized |
| External side effects | Have external systems received irreversible changes? | Payments, emails, or webhooks already sent |
| Permissions and config | Does the old version still have required permissions or config? | Old secret, role, or endpoint was revoked |

A rollback is only safe when all relevant layers are evaluated. Checking the database schema alone is insufficient.

## 3. Distinguishing Backward Compatibility and Forward Compatibility

Two concepts are commonly used when designing changes:

- **Backward compatibility:** an older version continues to work with schemas or new data created in a controlled manner.
- **Forward compatibility:** a newer version can read or process data created by an older version.

When preparing for rollback, backward compatibility is what matters: current data must not cause the old application to fail or misinterpret values.

For example, if the new version adds an optional JSON field and the old version ignores unknown fields, the change may be compatible. However, if the new version begins writing an enum value that the old code does not recognize, rollback can fail even if the database schema did not change.

Do not infer that a forward-compatible change is also backward-compatible. Each direction must be tested separately.

## 4. Application Version and Data State Model

Suppose the current version is N and the new release is N+1. Once N+1 has run, the system may contain data produced by both versions.

| State | Version N | Version N+1 | Rollback capability |
|---|---|---|---|
| Before migration | Reads/writes old schema | Not yet deployed | Normal |
| Schema expanded | Works if new structures are ignored | Can use new structures | Usually still safe |
| N+1 writes both old and new formats | Reads properly if old data is maintained accurately | Reads/writes both | Potentially safe after validation |
| N+1 writes only new format | May miss new data or misread it | Works | Requires adapter or conversion before rollback |
| New values have appeared | May error or misprocess | Works | Must check mapping and semantics |
| Old schema has been removed | Does not work | Works | Cannot roll back binary alone |

This matrix must be established before release. Without records of which version wrote which type of data, during an incident the team will have to investigate while the system is actively impacted.

## 5. Changes That Commonly Break Older Application Versions

### 5.1. Dropping or Renaming Columns

The old version may still contain queries referencing the old column. If a migration dropped or renamed the column, the application will fail immediately upon running that query.

The safe approach is to add the new column first, deploy compatible application code, migrate data, and keep the old column throughout the observation window. Contract only after confirming no old consumers remain.

### 5.2. Adding New Enum Values

A VARCHAR column may accept a new value without the database raising an error, yet old code may use a closed enum. Java example:

~~~java
enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}

OrderStatus status = OrderStatus.valueOf(databaseValue);
~~~

If the new version writes REFUNDED, the old version's parse call will throw an exception. Evaluate how old code handles unknown values before allowing new values to be written.

Options include:

- Deploying a version of old code capable of handling unknown values before releasing the new value.
- Keeping stored values within the set understood by both versions during the transition period.
- Using a mapping or compatibility adapter.
- Deferring enabling the feature that produces new values until the rollback window closes.

Do not automatically map every unknown status to a default status if doing so can corrupt business logic.

### 5.3. Changing Data Semantics

A column can keep the exact same name and type while its meaning changes. Examples:

- Monetary values changing from minor units to major units.
- Timestamps changing from local time to UTC.
- Status changing from "sent" to "confirmed by supplier."
- An old boolean replaced by three states.
- Quantity stored in packaging units instead of base units.

The old version can read the data type yet miscalculate. This is a dangerous bug because it does not necessarily raise exceptions or fail health checks.

### 5.4. Changing JSON or Document Structures

If the application stores JSON in a database or object store, the new version might rename fields, change types, or add required fields. Check the old version's serializer/deserializer configuration, including how it handles unknown fields, missing fields, nulls, and defaults.

### 5.5. Changing Relationships or Uniqueness

The new version may move a relationship from one table to another, alter keys, or change uniqueness rules. If the old version still assumes the old relationships, it may return incomplete results, create duplicate records, or update the wrong entity.

## 6. Using Expand-Contract to Keep the Rollback Window Open

Expand-contract allows a new schema to coexist without breaking the ability of the old version to operate.

~~~mermaid
flowchart TD
    A["Application N and old schema"] --> B["EXPAND: add new columns/tables"]
    B --> C["Deploy N+1 compatible with both"]
    C --> D["Controlled dual-write or synchronization"]
    D --> E["Backfill and reconcile data"]
    E --> F["Switch to new structure"]
    F --> G["Maintain compatibility window"]
    G --> H{"Still need rollback to N?"}
    H -- "Yes" --> I["Keep old structures and data compatible"]
    H -- "No" --> J["CONTRACT: remove old structures"]
~~~

Principles:

1. Add new structures without deleting old structures.
2. Deploy code capable of handling both pre- and post-migration states.
3. Maintain data required by the old version throughout the rollback window.
4. Verify data and consumers before switching over completely.
5. Remove old structures in a separate release only after compatibility is no longer needed.

If rolling back to N is necessary during this phase, the team can bring back the old binary while the old schema still exists. However, values written by N+1 must still be checked.

## 7. Maintaining Compatible Data While N+1 Writes Data

There are several ways to keep new data readable by the old version. No single method fits every system; the choice depends on whether the data lives in the same database or across multiple systems.

### 7.1. Dual-Write Within the Same Transaction

If old and new data reside in the same database, the application can update both representations in the same transaction:

~~~sql
UPDATE orders
SET legacy_status = :legacy_value,
    normalized_status = :normalized_value
WHERE id = :order_id;
~~~

This allows the old version to continue reading the old column while the new version uses the new column. However, every write path must be updated, including APIs, workers, batch jobs, admin tools, and integrations.

If one write path updates only the new column or only the old column, the two representations will diverge. Metrics, reconciliation, and tests are needed for all writers.

### 7.2. Compatibility Adapter

A translation layer can convert new data into the old format when the old version needs to consume it. The adapter can sit in the application, API, or data access layer.

The adapter must have explicit rules for every value. If a new state has no equivalent meaning in the old model, do not force-map it to an approximate value merely to avoid technical errors. Make a business decision: keep the feature disabled, block rollback, or roll forward.

### 7.3. Read Fallback

During the transition period, the application can prefer reading the new structure and fall back to the old structure when new data does not yet exist. Avoid letting fallback mask corrupted data: NULL due to pending backfill differs from NULL due to a write failure.

Record which data source was used and fallback counts so you know when the compatibility path can be removed.

### 7.4. Avoid Blind Dual-Writes Across Two Systems

If two data stores are independent, a dual-write can succeed in one store and fail in the other. Consider transactional outbox, CDC, idempotent retries, and reconciliation. Know clearly which store is the source of truth in each phase.

## 8. Checking Enums, Statuses, and New Values

Enum values are one of the most common reasons an old version fails to read new data.

Build a mapping table:

| Value written by N+1 | Understood by N? | Handling during rollback |
|---|---|---|
| PENDING | Yes | Keep as-is |
| PAID | Yes | Keep as-is |
| CANCELLED | Yes | Keep as-is |
| REFUNDED | No | Stop generating, use adapter, or roll forward |
| DISPUTED | No | Clarify semantics; do not map arbitrarily |

Check both database constraints and code. A database may accept a value that old code does not recognize. Conversely, new code may recognize a value that an old constraint forbids writing.

If the old version uses strict switch expressions or enum deserialization, an unknown value can throw an exception. If the code has a default branch, verify whether that branch preserves business logic or silently masks errors.

## 9. Checking JSON, Serialized Objects, and Documents

Data may be stored as JSON in databases, object storage files, caches, or messages.

When changing a JSON schema, check:

- Are old fields still present?
- Are new fields required?
- Have data types changed?
- Do null and missing fields carry different meanings?
- Will the old serializer reject unknown fields?
- Do enums and timestamps use a new format?
- Is the document version stored?

A compatible JSON sample can retain old fields during the transition window:

~~~json
{
  "schemaVersion": 2,
  "status": "PAID",
  "legacyStatus": "settled"
}
~~~

This example illustrates preserving old information so old code or an adapter can use it. Before contracting, confirm no consumers still depend on legacyStatus.

For Java serialization or serialized objects tied to class names/`serialVersionUID`, changing a class can prevent the old version from deserializing it. Do not use native Java serialization as a long-term storage format when multi-version compatibility is required. For schema-based formats like Avro or Protobuf, verify compatibility rules and schema registry settings in the proper read/write direction.

## 10. Checking Data Types, Precision, and Semantics

Data type changes must be tested with realistic values, not merely by seeing that the migration runs without error.

| Change | Risk to old version | Required check |
|---|---|---|
| Integer to decimal | Overflow or loss of fractional part | Boundary values and rounding rules |
| Minor currency unit to another currency unit | Wrong scaling factor in calculations | Unit conversion and totals |
| Local time to UTC | Date/time offset | Timezone, daylight saving, and boundaries |
| String to enum | Unknown value | Mapping and default handling branch |
| Nullable to NOT NULL | Inserts/updates from old code fail | All writers and defaults |
| ID format change | Parsing or comparison failure | Format, sorting, and relationships |
| Boolean to multi-state | Information loss when collapsing back to true/false | Intentional mapping rules |

If a conversion loses information—for instance, multiple new states collapsed into a single old state—rollback may be unable to restore original semantics. Recognize this as a design boundary and consider retaining original data or choosing roll-forward.

## 11. Checking Messages, Events, and Consumers

Rolling back an application can cause old consumers to receive messages published by the new version. This is a compatibility issue independent of the database.

Verify:

- Did the new producer add or alter fields?
- Do old consumers ignore unknown fields?
- Will new enums cause deserialization failures?
- Did partition keys or ordering change?
- How long do old messages remain in the queue?
- Does the dead-letter queue contain new-schema messages?
- Can consumers read messages already published after rollback?

If new messages are incompatible with old consumers, you may need to keep the producer on the old schema during the compatibility window, use versioned events, or deploy consumers supporting both schemas before emitting new events.

Do not assume rolling back the producer deletes already-published messages. Queues can hold new messages for hours or days. Inspect the backlog and handle queued messages before bringing old consumers back.

## 12. Cache, Sessions, and Ephemeral Data

Caches and sessions are often overlooked during rollback planning, yet they can hold object structures or values created by the new version.

Examples:

- A new session contains a required field unknown to the old version.
- A cache value changed from a plain string to JSON.
- A cache key changed while the old version still reads the old key.
- Objects in a distributed cache are serialized under a new class definition.
- Feature flags or config snapshots are stored in the cache.

Risk mitigation measures:

- Version cache keys or payloads.
- Keep serializers compatible during the transition period.
- Allow cache misses and regenerate from the source of truth.
- Selectively clear caches that cannot be safely read prior to rollback.
- Avoid clearing active sessions if doing so unexpectedly logs users out.
- Test the old version against cache values created by the new version.

Clearing caches can be an appropriate recovery step when cached data is derived. Never delete unique data or business state stored in a cache without understanding the impact.

## 13. Compatibility with Side Effects and External Systems

Certain actions taken by the new version cannot simply be reversed by re-running the old binary:

- Payments already submitted to a payment provider.
- Emails or SMS already sent.
- Webhooks already delivered to partners.
- Messages that already triggered downstream workflows.
- Files already exported to object storage.
- Transactions already recorded in accounting systems.

Distinguish code rollback from business compensation. For example, a captured payment transaction may require a refund via the provider's API; redeploying the old version does not automatically reverse that charge.

Before release, determine which side effects can be compensated, which operations are idempotent, and how to reconcile when it is uncertain whether a request was processed. For distributed workflows, maintain correlation IDs and transaction states to avoid duplicate sends during recovery.

## 14. Feature Flags and Limiting New Data During the Rollback Window

Feature flags can control when the new version begins creating data that the old version does not understand.

A possible strategy:

1. Deploy the new code while keeping the feature that writes new values disabled.
2. Verify code and schema compatibility.
3. Enable the feature for a small cohort.
4. Monitor new data and verify rollback compatibility.
5. Expand only once you accept that the old version may no longer be a rollback option.
6. After the compatibility window closes, remove adapters and old structures as planned.

A feature flag does not make data compatible by itself. It only controls when new data begins being generated. Ensure every write path honors the flag, including workers and background jobs.

## 15. Determining Whether Rollback Is Safe or Roll-Forward Is Required

Application rollback is not always the best option. Evaluate the generated data and the old version's ability to read it.

| Scenario | Typically appropriate approach |
|---|---|
| Bug is only in code; schema and data remain compatible | Roll back binary/artifact |
| Schema is expanded; old structures not yet removed | Usually safe to roll back after compatibility check |
| N+1 wrote a new enum that N does not understand | Stop generating new values, perform controlled conversion, or roll forward |
| Data semantics changed or information was lost | Usually prefer roll-forward or compensation |
| Old schema was DROPped | Must restore/recreate compatible schema or roll forward; do not roll back binary alone |
| External side effects occurred | Use compensation and reconciliation procedures |
| Insufficient data to prove compatibility | Hold rollout / evaluate further; do not declare rollback safe |

The decision must weigh user impact, data recoverability, recovery time, and the risk of worsening the situation. Roll-forward can be safer when new data cannot be interpreted correctly by the old version.

## 16. Pre-Rollback Verification Procedure

Before bringing the old version back, gather information:

1. **Identify the old artifact:** retrieve the exact digest or package that previously ran stably.
2. **Identify database state:** which migrations have run, current schema, and which constraints changed.
3. **Identify new data:** values, formats, or relationships written by the new version.
4. **Identify writers:** which APIs, workers, batch jobs, and consumers produced that data.
5. **Verify reads:** can the old version read the new data without errors or misinterpretation?
6. **Verify writes:** can the old version continue writing without losing or corrupting new data?
7. **Verify side effects:** are already-triggered messages, payments, webhooks, and files handled properly?
8. **Verify infrastructure compatibility:** are runtimes, secrets, permissions, endpoints, and configs still compatible?
9. **Choose action:** direct rollback, data conversion, disabling the new feature, or roll-forward.
10. **Record decision:** save evidence, approver, artifact digest, and verification plan.

Do not test-run the old version directly against production data without isolation measures. Use a sanitized copy of data or an equivalent rehearsal environment to verify beforehand.

## 17. Executing a Controlled Rollback

Once compatibility is confirmed:

1. Stop or throttle write paths generating more incompatible new data.
2. Pause relevant workers or consumers if necessary.
3. Record the release ID, artifact digest, migration version, and timestamp.
4. Deploy the verified old artifact.
5. Keep the expanded schema if the old version can safely ignore new structures.
6. Verify database connections, critical queries, and health checks.
7. Run smoke tests across core business flows.
8. Inspect message backlogs, caches, sessions, and side effects.
9. Monitor error rates, latency, data discrepancies, and retries.
10. Reopen traffic or workers only when criteria are met.

Do not automatically run down-migrations alongside an application rollback. A destructive migration or column drop can make the old version perform worse. The schema can stay in its expanded state until the team determines the next step.

## 18. Post-Rollback Verification

A technically successful rollback deployment is only the first step. Verify that the old version handles existing data properly.

Checks should include:

- Running artifact digest matches the selected version.
- Application startup and readiness are stable.
- No spike in deserialization or enum parse errors.
- Old queries do not reference dropped columns.
- No new records are missed because they were written only to new structures.
- Business invariants still hold.
- Workers and consumers clear the backlog.
- No side effects are sent repeatedly.
- Caches/sessions work or have been safely handled.
- SLIs/SLOs return to acceptable levels.

Compare metrics before and after rollback. If the error rate drops while failed transactions or mismatches rise, the system has not truly recovered.

## 19. Testing Rollback in CI/CD

Rollback compatibility must be tested before release, not left solely to a paper runbook.

A test matrix may include:

| Test case | Input | Expected result |
|---|---|---|
| Old app + expanded schema | Schema with new columns/tables added | Old version continues running |
| Old app + data from new app | Fixture with new values and JSON | Reads properly or rejects in a controlled manner per policy |
| Old app + new enum | Record containing new value | Does not crash or executes clear fallback behavior |
| Old writer + expanded schema | Writes from old version | Does not corrupt new data |
| Old consumer + new event | New message schema | Consumer reads or routing handles it |
| Rollback after partial backfill | Data partially migrated | Old app keeps working or has a recovery procedure |
| Retry and replay | Messages or batches reprocessed | Creates no duplicates or invalid states |

Useful techniques:

- Integration tests against real database migrations.
- Contract tests between producers and consumers.
- Deserialization tests using the old version's binary.
- Fixtures representing pre- and post-migration data.
- Snapshot restores in an isolated environment.
- Rollback rehearsals in staging.
- Mid-execution failure tests during backfill or cutover.

Testing only the new version against the new schema is not enough. You must run the old binary against data that the new version can produce.

## 20. Example: New Version Adds REFUNDED Status

Suppose version N understands only PENDING, PAID, and CANCELLED. Version N+1 adds REFUNDED and begins writing this value after successful refunds.

If N+1 fails and the team redeploys N:

- Database queries still run because the status column remains VARCHAR.
- Yet N's code invokes an enum parser and throws on REFUNDED.
- Some APIs return 500 when reading refunded orders.
- Old workers may retry messages endlessly.
- Dashboards may only surface errors once traffic hitting this data subset increases.

Options:

**Before enabling the feature:** if keeping the ability to revert to line N is required, prepare a compatibility patch on that release line or an adapter to handle unknown statuses. If the old binary cannot be changed and no safe adapter exists, do not enable the feature producing new values during the rollback window.

**Once REFUNDED data already exists:** determine whether it can be mapped back to an old status while preserving business meaning. If not, never arbitrarily map it to CANCELLED or PAID. You may keep N+1, release a compatible patch, or roll forward.

**If immediate recovery is needed:** turn off the path generating the new status, preserve refund data intact, and run a version capable of reading it. Serve required requests and reports via an adapter or compatible version. Never delete refund data just so an old enum parser can succeed.

## 21. Automating Compatibility Checks in the Pipeline

A pipeline can enforce a compatibility gate before permitting a release:

~~~mermaid
flowchart TD
    A["Pull request and migration"] --> B["Schema compatibility tests"]
    A --> C["Data mapping tests"]
    A --> D["Event/API contract tests"]
    B --> E["Build artifact N+1"]
    C --> E
    D --> E
    E --> F["Generate data fixtures written by N+1"]
    F --> G["Run binary N against new schema and fixtures"]
    G --> H{"Rollback compatibility passes?"}
    H -- "No" --> I["Block release or require roll-forward plan"]
    H -- "Yes" --> J["Publish artifact and compatibility evidence"]
    J --> K["Deploy per strategy"]
~~~

The gate can record attributes:

- Tested old application version.
- Tested schema version.
- Applied migrations.
- Fixture set and data format version.
- Read/write results from the old version.
- Related consumers and event schemas.
- Known compatibility boundaries.
- Rollback or roll-forward decision.

Pseudo-code policy example:

~~~yaml
rollback_compatibility:
  old_application: "release-N"
  candidate_application: "release-N-plus-1"
  database_schema: "schema-after-expand"

  checks:
    - old_binary_reads_new_records
    - old_binary_writes_without_data_loss
    - old_enum_parser_handles_unknown_values
    - old_consumer_reads_new_events
    - cache_and_session_compatibility
    - business_invariants_pass

  on_failure:
    release_action: BLOCK_OR_REQUIRE_FORWARD_RECOVERY_PLAN
~~~

This is an illustrative structure, not a standard schema of any CI platform. In real systems, run against the actual old binary and target database engine/version, not merely unit-test mocks.

## 22. Storing Evidence and Managing the Rollback Window

Every release should record:

- Artifact digests of the current and previous versions.
- Migration ID/version and execution state.
- Schema version or schema fingerprint.
- Related data formats/versions.
- Feature flags and activation timestamps.
- Event schema versions.
- Rollback compatibility test results.
- Values or operations that are not backward-compatible.
- Approver and rollback window expiration.

The rollback window is the duration during which the team commits to being able to revert to the previous version via a verified procedure. Beyond this window, contract changes or new data may make direct rollback unsafe.

Do not set the rollback window purely by calendar. Base it on observation duration, business cycles, message lifetimes, batch jobs, and infrequently run consumers. For example, a weekly report may still depend on an old column long after the API system switched over.

## 23. Common Anti-Patterns

| Anti-pattern | Consequence | Improvement |
|---|---|---|
| Assuming rolling back the binary reverses the database | Schema and data remain in the new state | Check schema and data compatibility separately |
| Dropping old columns in the same cutover release | Old version cannot query | Use expand-contract and a compatibility window |
| Writing new enums before old app understands them | Parse errors or misprocessing | Test unknown values and gate with features |
| Testing only schema, not data | Old code still misreads semantics | Use fixtures generated by the new version |
| Checking only web services | Old workers or consumers may fail | Check every writer and reader |
| Arbitrarily falling back new values to defaults | Loss of business meaning | Controlled mapping or roll-forward |
| Running down-migrations automatically on rollback | May delete new data | Keep expanded schema and evaluate separately |
| Ignoring queues and caches | Consumer/session failures after rollback | Inspect message backlogs, caches, and sessions |
| Not retaining old artifacts | Must rebuild during an incident | Retain immutable artifacts by digest |
| Not rehearsing rollback | Runbook does not reflect reality | Rehearse with old binaries and new data |

## 24. Checklist Before Allowing Old Application Rollback

**Schema and data**

- [ ] Old schema required by the old version still exists.
- [ ] No columns, tables, or constraints were altered beyond compatibility.
- [ ] Old version understands new enums and values.
- [ ] Data types, units, timezones, and semantics are not misinterpreted.
- [ ] JSON/documents and serialized payloads have been tested.
- [ ] Relationships, unique constraints, and invariants remain valid.

**Writers, readers, and messages**

- [ ] All APIs, workers, batches, and admin tools have been reviewed.
- [ ] New data is written to old structures when rollback is needed.
- [ ] New messages are compatible with old consumers or a handling plan exists.
- [ ] Queue backlogs and dead-letter queues have been evaluated.
- [ ] Caches and sessions can be safely read or refreshed.
- [ ] External side effects have compensation/reconciliation procedures.

**Execution and verification**

- [ ] Old artifact is retained and identified by digest.
- [ ] Old binary has been tested against the new schema and data fixtures.
- [ ] Clear decision exists between rollback and roll-forward.
- [ ] Destructive down-migrations are not run automatically.
- [ ] Runbook covers stopping writers/workers and shifting traffic.
- [ ] Post-rollback smoke tests, invariants, and SLIs/SLOs are verified.
- [ ] Evidence and accountability are recorded for the decision.

## 25. Conclusion

Running an older application version is safe only when current data remains within the bounds that version can read, write, and interpret accurately. Risks can stem from altered schemas, new enums, new JSON, changed semantics, event backlogs, caches/sessions, or external side effects.

Expand-contract, compatibility adapters, writing data in compatible formats, and testing the old binary on fixtures generated by the new version help preserve the rollback path. Before rolling back, identify executed migrations, newly generated data, and all relevant consumers. When data has changed irreversibly in ways required by business correctness, roll-forward or compensation is usually better than forcing an old version to process a state it does not understand.

A recoverable release requires retaining old artifacts, versioning schemas and data, storing compatibility test evidence, and verifying after switching versions. That way, rollback decisions rest on actual compatibility rather than assuming swapping binaries is enough.
