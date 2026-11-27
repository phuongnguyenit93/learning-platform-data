# Behavioral Regression Testing and Stored Data Compatibility

An upgrade can compile cleanly, pass unit tests, and still corrupt data written by a previous version. For example: a new model renames an enum, a serializer changes how timestamps are represented, a migration adds a required column without backfilling, or a new consumer fails to read messages still sitting in the queue from last week. Failures only surface when the application encounters real existing data.

Therefore, regression testing when upgrading Spring Boot and Spring Cloud libraries must verify both **application behavior** and **the ability to read, write, and migrate data across versions**. You must retain representative data samples from earlier versions, run migrations on populated databases, verify stored payloads, and test real cloud flows. A test that only spins up an empty database or publishes a new message and consumes it immediately does not prove old data remains compatible.

This lesson belongs to the **Integration Upgrades** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module practices integrating Spring Boot with AWS, Azure, and Google Cloud managed services through the corresponding Spring Cloud libraries. This lesson focuses on regression testing for databases, object storage, message brokers, serialization, and provider SDK changes.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish behavioral regression tests, integration tests, contract tests, and data migration tests.
- Identify which application versions must stay compatible during rolling deployments and data replays.
- Build a set of golden fixtures representing payloads, records, and objects written by older versions.
- Test schema evolution for JSON, Avro, Protocol Buffers, and message envelopes.
- Run database migrations on snapshots containing data and verify post-migration invariants.
- Verify object storage metadata, checksums, versioning, and conditional writes.
- Test message ordering, duplicates, redelivery, ack, dead-letter handling, and idempotency.
- Use Testcontainers, emulators, and cloud sandboxes within their proper scope.
- Detect differences between emulators and real managed services.
- Design canaries, backfills, reconciliation, and rollbacks that account for already-written data.

## 2. Why Do Upgrades Require Testing Old Data?

Cloud applications typically store data in multiple places. Each location has its own lifecycle and compatibility rules:

| Data store | Data to protect | Common post-upgrade failures |
| --- | --- | --- |
| Relational database | Rows, schemas, indexes, constraints, sequences | Migration loses data, changes column types, sets wrong defaults, breaks old queries |
| NoSQL | Partition keys, sort keys, document attributes, indexes | Key encoding changes, attribute types change, old items fail to deserialize |
| Object storage | Bytes, metadata, tags, content types, version IDs, checksums | ETag mistaken for checksum, lost metadata, old URLs/versions unreadable |
| Message broker | Payloads, headers, schema versions, message IDs, ordering keys | New consumer cannot read old messages, duplicates, or wrong ack behavior |
| Cache | Serialized values, key formats, TTLs | Old cache entries fail to deserialize or key namespaces change |
| Secret/config store | Key names, versions, formats, encoding | Application reads wrong version or fails to parse secret |
| Search/index | Document mappings, analyzers, query fields | Old index is incompatible with new queries |

A regression test that only checks HTTP responses or method return values is insufficient. You must verify persisted effects as well: rows in the database, objects in the bucket, events in the queue, and side effects executed the exact expected number of times.

### 2.1. Distinguishing compatibility directions

When multiple versions coexist, express compatibility in terms of writers and readers instead of vaguely writing “backward compatible”.

| Check | Question |
| --- | --- |
| New reader reads old data | Can version N read records/messages written by N-1? |
| Old reader reads new data | During a rolling deployment, can consumer N-1 read payloads written by producer N? |
| New reader reads migrated data | After migration, does new code understand both old records and backfilled records? |
| Replay old data | Can messages/objects replayed after days or months still be read? |
| Code rollback | Can code N-1 run safely on a schema expanded by N? |

In schema registry documentation, forward/backward compatibility terms may be defined by specific writer/reader directions. Therefore, test plans should specify the exact version pair and read direction, such as `writer=N-1, reader=N`, rather than just saying “test backward compatibility”.

### 2.2. Building a version matrix

Example of an application deployed via rolling updates:

| Writer / Reader | N-1 reader | N reader |
| --- | --- | --- |
| N-1 writer | Current flow | Must verify old data |
| N writer | Verify if rollback/old consumers still run | New flow |

If a queue retains messages for a long time, the compatibility window must cover both retention and replay periods. If the database holds records from years ago, fixtures must cover every schema version still present in production, not only the version immediately preceding the deployment.

## 3. Designing a Regression Dataset
+
A regression dataset must represent existing data, including common cases and boundary data. Do not generate all fixtures from the new model, because a new serializer might silently normalize or strip the exact legacy edge cases you need to test.

### 3.1. Versioned golden fixtures

Store fixtures by writer or schema version:

```text
src/test/resources/compatibility/
  invoice/
    v1/
      invoice-paid.json
      invoice-null-customer.json
      invoice-large-amount.json
    v2/
      invoice-issued.json
      invoice-with-currency.json
  events/
    v1/
      invoice-created.json
    v2/
      invoice-created.json
      invoice-cancelled.json
  objects/
    v1/
      metadata.json
      expected-sha256.txt
    v2/
      metadata.json
      expected-sha256.txt
```

Each fixture should document:

- The application or schema version that produced the data.
- Format/encoding, content type, and compression if any.
- Timestamps and timezone.
- Business assumptions regarding defaults or missing fields.
- Expected read outcome.
- Checksums if the fixture contains bytes or objects.

Do not edit old fixtures to fit a new model. When a contract changes intentionally, add a new fixture version and keep the old fixture to continue testing newer readers.

### 3.2. Edge cases to include

An invoice fixture suite might include:

- Completely missing fields and fields set to `null`.
- Enums containing values that were removed or unknown to new code.
- Decimals with many fractional digits, negative numbers, and boundary values.
- Timestamps with non-UTC timezones, day rollovers, and nano/millisecond precision.
- Unicode strings, combining characters, long names, and accented text.
- Empty arrays, large arrays, nested objects, and fields undefined in the current model.
- Legacy IDs, prefixed IDs, UUIDs, and case-sensitive keys.
- Empty payloads, large payloads, compressed data, and binary payloads.
- Duplicate events or out-of-order events.

If old data may contain unknown fields, verify that new consumers ignore, preserve, or reject them according to the contract. Do not silently drop unrecognized data if business rules require preserving it.

### 3.3. Do not put sensitive data into fixtures

Generate fixtures from anonymized or synthetic production data. Never store access tokens, connection strings, secrets, personally identifiable information, or encryption keys in the repository. If a fixture needs to test encryption, use dedicated test keys and synthetic data.

## 4. Testing Database Migrations on Populated Data

Testing migrations on an empty database only proves the new schema can be created. Production typically has millions of rows, historical nulls, data written by multiple versions, and large indexes.

### 4.1. Testing from multiple baselines

For each baseline still existing in production, create a database from that schema/version, load fixtures, and run migrations up to the target version.

| Baseline | Test coverage |
| --- | --- |
| Fresh database | Full migration runs from scratch |
| Schema N-2 | Migration crosses intermediate versions |
| Schema N-1 | Direct upgrade from the most recent release |
| Representative data snapshot | Legacy rows, nulls, duplicates, boundary values, and large values |
| Production-scale snapshot | Migration duration, locks, index builds, transactions, and storage |

If the project uses Flyway, versioned migrations form an ordered change history. Do not modify a migration already applied to shared environments; create a new migration instead. `flyway validate` checks applied migrations against available migrations, including name, type, and checksum. This validates migration history and does not replace verifying data after running migrations.

### 4.2. Checking invariants before and after migration

Before running migrations, record the invariants to preserve:

- Total row counts per table and per status.
- Null/empty counts in critical fields.
- Total monetary amounts or quantities by business group.
- Count of orphaned foreign keys.
- Uniqueness of business keys.
- Min/max timestamps and historical date ranges.
- Total objects/events referencing records.
- Checksums or digests of critical data fields.

After migration, re-run reconciliation queries. Comparing row counts alone is not enough: a migration can preserve row counts while corrupting values, timezones, or precision.

### 4.3. Example schema-expansion migration

Suppose the old schema stores `amount` without `currency`. If the new application requires currency, you should not add a `NOT NULL` column without handling existing rows.

Expansion migration:

```sql
-- V2__add_currency_to_invoice.sql
ALTER TABLE invoice
    ADD COLUMN currency CHAR(3);

UPDATE invoice
SET currency = 'VND'
WHERE currency IS NULL;

ALTER TABLE invoice
    ALTER COLUMN currency SET NOT NULL;
```

This example is only valid if all existing rows truly represent VND. If legacy currencies depended on tenant or transaction time, backfill using authoritative source data. Never use the system's current currency to guess the currency of historical transactions.

### 4.4. Expand-contract for rolling-deployment migrations

For major schema changes, roll out in multiple steps:

1. **Expand:** add new columns/tables in a compatible state; keep old columns.
2. **Deploy compatible code:** code reads both old and new formats, dual-writing when needed.
3. **Backfill:** migrate old data in batches with checkpointing and re-runnability.
4. **Reconcile:** compare row counts, values, and invariants between both representations.
5. **Switch reads:** point readers to the new column/format.
6. **Observe:** maintain an observation window and confirm no consumer still needs the old format.
7. **Contract:** drop old columns/constraints in a separate migration after the rollback window closes.

Do not perform expand and contract in the same release if older application versions may still run during a rolling deployment or if rollback may be needed.

### 4.5. Testing migrations with Testcontainers and Flyway

Spring Boot supports Testcontainers; for recognized containers, `@ServiceConnection` creates connection details for auto-configuration to consume. Add `spring-boot-testcontainers` in test scope. These connection details take precedence over connection-related properties, which is useful when tests must use a database container instead of endpoints in configuration files.

Example:

```java
@Testcontainers
class InvoiceMigrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void migratesExistingInvoiceWithoutChangingItsMeaning() throws Exception {
        var dataSource = new org.postgresql.ds.PGSimpleDataSource();
        dataSource.setURL(postgres.getJdbcUrl());
        dataSource.setUser(postgres.getUsername());
        dataSource.setPassword(postgres.getPassword());

        Flyway oldVersion = Flyway.configure()
            .dataSource(dataSource)
            .locations("classpath:db/migration")
            .target(MigrationVersion.fromVersion("1"))
            .load();

        oldVersion.migrate();

        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(
                 "INSERT INTO invoice(id, amount, status, created_at) " +
                 "VALUES (?, ?, ?, ?)")) {
            statement.setObject(1, UUID.fromString(
                "8e52a9c8-3d11-4d7e-a932-3d6bcb54f1a0"));
            statement.setBigDecimal(2, new BigDecimal("125.50"));
            statement.setString(3, "PAID");
            statement.setObject(4, OffsetDateTime.parse(
                "2025-10-12T09:30:00+07:00"));
            statement.executeUpdate();
        }

        Flyway latest = Flyway.configure()
            .dataSource(dataSource)
            .locations("classpath:db/migration")
            .load();

        latest.migrate();

        try (var connection = dataSource.getConnection();
             var statement = connection.prepareStatement(
                 "SELECT amount, status, currency FROM invoice WHERE id = ?")) {
            statement.setObject(1, UUID.fromString(
                "8e52a9c8-3d11-4d7e-a932-3d6bcb54f1a0"));

            try (var result = statement.executeQuery()) {
                assertTrue(result.next());
                assertEquals(new BigDecimal("125.50"), result.getBigDecimal("amount"));
                assertEquals("PAID", result.getString("status"));
                assertEquals("VND", result.getString("currency"));
            }
        }
    }
}
```

In a real project, replace `VND` with a business-verified backfill rule. Add fixtures for null rows, negative/boundary amounts, timestamps, and foreign keys. You can use `@SpringBootTest` with `@ServiceConnection` to test repository auto-configuration after migration finishes.

## 5. Testing JSON, Serializer, and Message Schema Compatibility
+
Messages sitting in SQS, Pub/Sub, or Service Bus may be read by consumers after producers have upgraded. Therefore, checking that the new serializer produces valid JSON is not enough; you must prove the new consumer can read previously written payloads.

### 5.1. Keeping message envelopes stable

An event should include enough metadata for consumers to identify versions and handle duplicates:

```json
{
  "eventId": "evt-2025-000184",
  "eventType": "InvoiceIssued",
  "schemaVersion": 1,
  "occurredAt": "2025-10-12T09:30:00+07:00",
  "aggregateId": "invoice-100184",
  "payload": {
    "amount": 125.50,
    "status": "PAID"
  }
}
```

When adding currency, you can introduce a new schema version:

```json
{
  "eventId": "evt-2025-000184",
  "eventType": "InvoiceIssued",
  "schemaVersion": 2,
  "occurredAt": "2025-10-12T09:30:00+07:00",
  "aggregateId": "invoice-100184",
  "payload": {
    "amount": 125.50,
    "currency": "VND",
    "status": "PAID"
  }
}
```

The new consumer must read version 1 according to published business rules. Do not assume all legacy invoices use the current configuration's currency unless source data proves it.

### 5.2. Writer/reader tests by version

Write dedicated tests:

- Read v1 fixtures with the current model/consumer.
- Read v2 fixtures with the current consumer.
- Write new payloads and verify fields, types, content type, and headers.
- If rolling deployment requires it, test old consumers reading new payloads.
- Test unknown enums, extra fields, missing fields, `null`s, and unexpected field types.
- Replay the same event twice to verify idempotency.
- Test messages written several versions ago that are still within the retention period.

Do not compare JSON solely by field order. JSON objects do not enforce property ordering; compare structure and values per the contract. For binary Avro/Protobuf, check schema and wire compatibility instead of byte-for-byte equality unless serialization guarantees deterministic bytes.

### 5.3. Avro and Protocol Buffers

With Avro, distinguish the message's writer schema from the consumer's reader schema. Spring Cloud Stream Schema Registry uses content types carrying version/schema references to locate the writer schema, then performs schema resolution against the reader schema. Tests should retain fixtures written by every schema version still in use.

With Protocol Buffers:

- Never reuse field numbers that were ever published.
- When removing fields, reserve field numbers/names per protobuf rules.
- Preserve wire types and field semantics.
- Test legacy binary payloads with newly generated classes.
- Verify new/unknown enum values and scalar field defaults.

Google Pub/Sub supports Avro and Protocol Buffers schemas. Pub/Sub validates published messages against the topic's attached schema; schema revisions must be forward and backward compatible with each other. Even so, the application must still test conversion logic and defaults in its own reader.

### 5.4. Spring Cloud Contract and contract tests

Spring Cloud Contract supports producer-driven and consumer-driven contract testing. Use contracts to verify HTTP APIs and message boundaries between services:

- Producer tests verify payloads, headers, and statuses emitted by the service.
- Consumer tests verify the consumer accepts the producer's contract.
- Stub tests let services run independently in CI.
- Integration tests with real brokers/emulators verify bindings, serialization, ack, and retries.

Contract tests do not replace full business tests or migration tests on stored data. A contract may pass while a consumer still mishandles historical values.

## 6. Testing Object Storage and Binary Data

Object storage stores both bytes and metadata. An SDK upgrade or upload mechanism change can alter content type, metadata, checksums, versioning, encryption, or conditional writes.

### 6.1. Do not use ETag as a general-purpose checksum

| Provider | What to check |
| --- | --- |
| Amazon S3 | ETag is not always the MD5 of the entire object, especially with multipart uploads or SSE-KMS/SSE-C; use explicit checksums |
| Google Cloud Storage | CRC32C is the recommended checksum; MD5 is unavailable for composite objects or certain multipart uploads |
| Azure Blob Storage | Check Content-MD5/CRC64 when used; ETag is for conditional requests and optimistic concurrency |

For S3, modern SDKs may calculate checksums automatically; default behavior varies across SDK versions. Inspect the actual stored checksum and compare it against a checksum computed from bytes. Never write tests assuming ETag always equals MD5.

### 6.2. Object storage test suite

For each object fixture, verify:

- Downloaded bytes match expected checksums.
- Content type, content encoding, content disposition, and metadata.
- Object keys, prefixes, Unicode, and special characters.
- Encryption mode/KMS key and read permissions.
- Multipart uploads and large objects.
- Range downloads and resume.
- Conditional writes using ETag/version.
- Versioning, delete markers, and restore if versioning is enabled on the bucket/account.
- Retention, lifecycle, and object lock if the application relies on them.

With S3 Versioning, `PUT` creates a new version and `DELETE` without a version ID creates a delete marker. Tests must verify restore or reading specific versions if business logic relies on versioning. With Azure Blob, ETag changes after writes; `If-Match` detects concurrent updates. With GCS, use CRC32C to verify whole-object integrity during downloads/uploads.

### 6.3. Testing metadata as part of the contract

Metadata can hold business IDs, tenants, content classifications, or schema versions. If new code renames metadata keys or changes casing, objects still upload yet downstream jobs may fail to classify them properly.

Define expected metadata per contract and compare keys/values after upload. If metadata must change, write explicit migrations or backfills; do not assume updating code automatically updates already-stored objects.

## 7. Testing Message Brokers and Consumer Behavior

Data in a broker can outlive a single application version. When upgrading SDKs or Spring Cloud integrations, test legacy messages, headers, settlement, and duplicates.

### 7.1. Testing message properties

For SQS/SNS, Pub/Sub, and Service Bus, test:

- Body bytes and content types.
- Message IDs, correlation IDs, and application properties/attributes.
- Schema versions and event types.
- Ordering keys/sessions/partition keys if used.
- Visibility timeouts or lock durations.
- Ack/complete/abandon/nack behavior.
- Retry counts, dead-letter reasons, and redelivery.
- Message TTL, retention, and scheduled delivery.
- Duplicate detection and idempotency keys.

Azure Service Bus can redeliver messages if locks expire, consumers restart, or operations succeed while acknowledgements are lost. Duplicate detection relies on MessageId within a configured window; it does not replace idempotent consumer processing. Test both send-side retries and receive-side redelivery.

### 7.2. Testing idempotency with real data

A consumer can receive the same event multiple times. Tests must verify:

1. The first processing attempt creates the exact expected side effect.
2. A second delivery with the same event ID creates no extra invoice, payment, or ledger entry.
3. If the first attempt fails midway, retries can resume safely.
4. Messages are acked/completed only after business state is committed.
5. Duplicate events do not inflate amounts or corrupt state transitions.

If using outbox/inbox tables, test transaction boundaries and unique constraints on event IDs. Publishing a message before committing the database, or committing before publishing without an outbox, can drop events or produce duplicates upon process crashes.

## 8. Using Testcontainers and Emulators Within Proper Scope
+
Local integration tests reduce cost and speed up feedback, but emulators do not simulate every aspect of managed services. Split tests into three tiers:

| Tier | Goal | Environment |
| --- | --- | --- |
| Unit/contract | Serializers, mappers, domain rules, schema compatibility | JUnit, fixtures, Spring Cloud Contract |
| Local integration | Repositories, SDK calls, message flows, basic object metadata | Testcontainers, emulators |
| Cloud sandbox | IAM/RBAC, encryption, versioning, retention, quotas, managed identity, and service-specific behavior | Dedicated test account/project |

### 8.1. Spring Boot Testcontainers

Spring Boot supports `@ServiceConnection` to automatically generate connection details for recognized containers. Add `spring-boot-testcontainers` in test scope. Generated connection details take precedence over connection-related configuration properties, which helps when tests need a database container instead of configured endpoints.

PostgreSQL example:

```java
@Testcontainers
@SpringBootTest
class InvoiceRepositoryIntegrationTest {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    InvoiceRepository repository;

    @Test
    void readsInvoiceAfterSchemaMigration() {
        Invoice invoice = repository.findById("invoice-100184")
            .orElseThrow();

        assertEquals(new BigDecimal("125.50"), invoice.amount());
        assertEquals("VND", invoice.currency());
    }
}
```

The test above requires fixtures loaded into the database after migration. For migration regression, initialize the schema from the old baseline, insert fixtures, and then apply the new migration as shown in the database section.

### 8.2. AWS

You can use DynamoDB Local for repository tests and a sandbox environment for service behavior. DynamoDB Local does not fully emulate the managed service: client account/region scoping is unsupported, provisioned throughput is ignored, and parallel scans are unsupported. Therefore, do not use it to draw conclusions about quotas, throughput, or region-specific production behavior.

For S3, verify checksums, metadata, versioning, encryption, and IAM on a sandbox bucket. If using third-party emulators, document which APIs/features are emulated and verify critical behaviors against real AWS.

### 8.3. Google Cloud

The Pub/Sub emulator supports publish/receive, ordering, replay, dead-letter forwarding, retry policies, filtering, and Avro schemas. However, it does not support IAM operations, configurable message retention, or subscription expiration; Protocol Buffers schemas are also listed under documented limitations.

Therefore:

- Use the emulator to test serialization, publish/consume, ordering, and basic retries.
- Use a sandbox project to test IAM, real schema revisions, retention, and permissions.
- Use older schema revision fixtures to test new consumers.
- Use CRC32C checksums when verifying Cloud Storage objects.

### 8.4. Azure

Azurite supports Blob, Queue, and Table Storage. It does not support Azure Files or Azure Data Lake Storage Gen2; local endpoints also differ from cloud endpoints. Use Azurite for CRUD, metadata, and basic storage behavior, then test unemulated features against a sandbox account.

The Azure Service Bus emulator supports AMQP TCP and sequential testing, but has published limitations: no Microsoft Entra ID support, no partitioned entities, no AMQP WebSockets, and no large messages; data/entities do not persist across container restarts. Never use the emulator to prove managed identity, partition behavior, disaster recovery, or production retention.

### 8.5. Environment selection table

| Behavior | Unit/fixture | Emulator | Cloud sandbox |
| --- | --- | --- | --- |
| Decode legacy JSON/Avro payloads | Yes | Possible | Optional |
| Database migrations | Insufficient | Testcontainers DB | Staging snapshot if scale needed |
| S3 checksums/versioning/KMS | Checksum fixtures | Optional emulator | Required for AWS-specific behavior |
| Pub/Sub publish/ordering | Can mock | Yes | Required for IAM/retention |
| Azure Blob metadata | Fixtures | Azurite | Required for features unsupported by Azurite |
| Service Bus Entra ID/partitions | No | No | Required |
| IAM/RBAC/managed identity | No | Usually no | Required |
| Quotas/performance/latency | Synthetic benchmarks | Insufficient | Required |

## 9. Building a Change-Driven Regression Suite

Do not run every test on every commit if cost is prohibitive. Map each type of change to a minimum required test set and run the full compatibility suite before release.

| Type of change | Required tests |
| --- | --- |
| Spring Boot/Jackson upgrade | Golden JSON fixtures, unknown fields/enums, timestamps, decimals, nulls |
| Provider SDK upgrade | Client config, checksums, metadata, retries, timeouts, resource closing |
| Database schema change | Migration from older baselines, data invariants, old/new code compatibility |
| Message converter change | Old writer/new reader, new writer/old reader, replay, headers |
| Queue/subscription change | Ordering, ack, redelivery, duplicates, DLQ |
| Object storage API change | Bytes/checksums, metadata, versioning, conditional writes |
| Identity change | Real principals, permissions, denied cases, key/secret access |
| Endpoint/region change | Resource mapping, encoding, TLS, and data residency |

A regression suite should name tests after the version pair, such as `readsInvoiceV1FixtureWithCurrentModel`, `migratesSchemaV3ToV5WithHistoricalRows`, `consumerV2ProcessesEventV1`, and `s3MultipartUploadPreservesFullObjectChecksum`.

## 10. Verifying Data After Migration and Deployment

After migration or deployment, run repeatable reconciliation checks:

1. Count records/objects/messages by business group.
2. Check null/default/enum distributions.
3. Compute checksums for selected datasets or objects.
4. Compare business aggregates: total amounts, invoice counts, payment counts, and statuses.
5. Inspect dead-letter queues and retry backlogs.
6. Check consumer lag and message age.
7. Verify object metadata, content types, and encryption.
8. Check logs for deserialization failures and unknown schema versions.
9. Verify database migration history and migration checksums.
10. Save reconciliation results per release for future comparison.

Reconciliation must distinguish expected differences from erroneous ones. For instance, a migration normalizing timestamps to UTC may change formatted display strings while the underlying instant must stay identical. Write tests comparing instants rather than strings if the contract permits timezone normalization.

## 11. Data-Aware Canary Rollouts and Rollbacks

Older code may not be able to read data written by newer code. Consequently, rolling back a container image is not always sufficient.

Before deploying:

- Lock the schema compatibility window.
- Identify still-running consumer versions and message retention periods.
- Keep readers capable of reading old formats throughout replay/rollback windows.
- Ensure database snapshots/backups follow policy.
- Enable object versioning/retention if business rules require recovery.
- Record schema versions and migration state.
- Prepare feature flags to switch read/write paths.

During canary:

- Route a portion of traffic or a subset of tenants.
- Compare read outputs between old and new code on the same data (shadow reads where appropriate).
- Monitor deserialization errors, query latency, duplicates, DLQs, and checksum mismatches.
- Track backfilled record counts and records remaining in legacy formats.

During rollback:

- Verify old code can read the expanded schema.
- Do not run destructive contract migrations before the rollback window closes.
- Do not delete object versions or messages needed for replay.
- If new code already wrote new payloads, keep compatible adapters/readers or run a verified reverse migration.
- Reconcile side effects and idempotency before replaying messages.

## 12. Common Regression Failures
+
| Symptom | Cause | How to detect |
| --- | --- | --- |
| Old records fail to deserialize | Missing fields, new enums, changed data types | Golden fixtures by writer version |
| Monetary totals shift after migration | Decimal scale/rounding or wrong currency default | Aggregate invariants and precision tests |
| Timestamps shifted by hours | Local timezone, parse format, or precision mismatch | Fixtures with offsets and Instant comparison |
| Object uploads fine yet downstream fails to read | Content type/encoding/metadata changed | Object metadata contract tests |
| False checksum mismatch | Using ETag as MD5 for multipart/encrypted objects | Compare explicit algorithm checksums |
| Consumer processes twice | At-least-once delivery or ack after side effect | Replay same MessageId and idempotency tests |
| Old messages enter DLQ after deploy | New consumer cannot read old schemas/headers | Replay fixtures on test broker |
| Emulator passes yet production fails | Emulator does not simulate IAM/managed features | Cloud sandbox tests |
| Rollback fails to run | Old code cannot read new formats/schemas | N-1/N compatibility matrix |
| Migration times out/locks heavily | Production data much larger than fixtures | Representative-scale snapshots and migration timing |
| Double backfill corrupts data | Non-idempotent job or missing checkpoints | Re-run job and reconcile outcomes |
| Versioned objects fail recovery | Misunderstood delete markers or version IDs | Versioning/restore tests on cloud sandbox |

## 13. Hands-On Exercise: Regression Testing invoice-service Across Two Versions

**Context:** invoice-service version N-1 stores invoices in PostgreSQL, PDFs in S3, and publishes InvoiceCreated to SQS. Version N adds currency, changes the message envelope, and upgrades the AWS SDK. Production still contains records and messages written by N-1.

### Step 1 — Collect sample data

Create fixtures from N-1:

- Paid invoices, cancelled invoices, and invoices missing customer references.
- Small PDFs and large PDFs uploaded via single-part and multipart.
- v1 messages with eventId, eventType, occurredAt, and old payload.
- S3 metadata with known content types and checksums.

Anonymize data while preserving types, nulls, precision, and key structures.

### Step 2 — Run database migrations

- Start a PostgreSQL container.
- Run Flyway up to schema N-1.
- Insert N-1 fixtures.
- Run migrations up to schema N.
- Verify amount, status, created_at, currency, and foreign keys.
- Re-check invariants and migration history.

### Step 3 — Verify serializers and readers

- Consumer N reads all v1 messages.
- Producer N writes v2 messages.
- If rolling deployment still has N-1 consumers, verify N-1 consumers can read v2 or keep a feature flag so producers continue writing v1 during the rollout window.
- Republish the same event ID and verify no duplicate invoice is created.
- Test unknown enums and missing fields.

### Step 4 — Verify S3

- Download v1 PDFs using version N code.
- Compare bytes via SHA-256 or stored checksums.
- Verify Content-Type, metadata, encryption, and version IDs.
- Upload new PDFs via multipart and verify whole-object checksums.
- Do not assume ETag equals MD5 for every object.

### Step 5 — Run provider sandbox tests

- Use a test IAM role scoped to read/write the intended bucket and queue.
- Verify SQS redelivery, visibility timeouts, and DLQs.
- Verify KMS permissions if the bucket uses SSE-KMS.
- Reconcile object metadata and message attributes written by the new SDK.

### Step 6 — Test rollback

- Start N-1 code against the expanded schema.
- Read invoices updated by N.
- Read v2 events if older consumers remain within the compatibility window.
- If N-1 code cannot read v2, confirm producers can revert to v1 before enabling rollback, or keep an adapter reading v2.

### Step 7 — Canary and reconcile

Deploy a subset of N instances and compare invoice totals, monetary sums, event counts, DLQ message counts, object checksums, and deserialization errors. Expand rollout only when invariants pass and no legacy data is dropped from processing.

## 14. Review Checklist Before Merging

- [ ] Built a writer/reader matrix between N-1 and N.
- [ ] Saved golden fixtures per writer/schema version.
- [ ] Fixtures cover missing/null fields, unknown enums, decimals, timestamps, and Unicode.
- [ ] Verified no secrets or personal data exist inside fixtures.
- [ ] Ran migrations from older populated schemas.
- [ ] Verified row counts and business invariants before/after migration.
- [ ] Checked Flyway migration history and checksums.
- [ ] Verified old code runs against expanded schemas during the rollback window.
- [ ] Tested new consumers reading legacy messages and replays.
- [ ] Tested idempotency, duplicates, ordering, ack, and DLQs.
- [ ] Verified object content types, metadata, checksums, and versioning.
- [ ] Avoided using ETag as a general checksum.
- [ ] Checked emulator limitations and ran cloud sandbox tests for critical features.
- [ ] Tested IAM/RBAC, KMS, and managed identity using test principals.
- [ ] Ran canary and post-deploy data reconciliation.
- [ ] Prepared rollback for code, schemas, objects, and messages.

## 15. Self-Check Questions

1. Why do clean compilation and passing unit tests not prove old data remains compatible?
2. How do regression tests, contract tests, and migration tests differ?
3. Why should golden fixtures be stored per writer version?
4. When must reader N verify data written by writer N-1?
5. Why must reader N-1 be tested against writer N data during a rolling deployment?
6. Why should already-applied Flyway migrations never be edited?
7. How does expand-contract make rollback safer?
8. What invariants besides row counts should be reconciled?
9. Why is an S3 ETag not always an MD5 checksum?
10. What role does CRC32C play when verifying Cloud Storage objects?
11. How do Azure Blob ETags support optimistic concurrency?
12. Why cannot the Pub/Sub emulator prove IAM behavior?
13. Which managed features does the Azure Service Bus emulator lack that must be tested in the cloud?
14. Why does duplicate detection not replace an idempotent consumer?
15. When must you keep readers for an old schema after deploying a new schema?
16. What data besides the database schema must be checked during rollback?

## 16. Key Takeaways

Regression testing for cloud upgrades must start from data already written by prior versions. Keep fixtures by writer/schema version, run migrations on populated databases, and verify business invariants after conversion. For messaging, test both old-writer/new-reader and new-writer/old-reader when rolling deployments or replays require it. For object storage, verify bytes, metadata, checksums, and versioning.

Testcontainers and emulators speed up integration testing, but they do not fully simulate IAM, quotas, retention, managed identities, or every service feature. Combine unit/contract tests, local integration tests, and cloud sandboxes. **An upgrade is ready only when new code accurately reads old data, new data stays within the compatibility window, and rollback preserves recoverability.**

## Official References

- [Spring Boot — Testcontainers and Service Connections](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Flyway — Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations)
- [Flyway — Validate migrations](https://documentation.red-gate.com/flyway/reference/commands/validate)
- [Spring Cloud Contract — Reference Documentation](https://docs.spring.io/spring-cloud-contract/reference/)
- [Spring Cloud Stream — Schema Registry and schema evolution](https://docs.spring.io/spring-cloud-stream/reference/schema-registry/spring-cloud-stream-schema-registry.html)
- [AWS — S3 object integrity and checksums](https://docs.aws.amazon.com/AmazonS3/latest/userguide/checking-object-integrity-upload.html)
- [AWS SDK for Java 2.x — S3 checksums](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/s3-checksums.html)
- [AWS — How S3 Versioning works](https://docs.aws.amazon.com/AmazonS3/latest/userguide/versioning-workflows.html)
- [AWS — DynamoDB Local usage notes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.UsageNotes.html)
- [Google Cloud — Pub/Sub schema overview](https://docs.cloud.google.com/pubsub/docs/schemas)
- [Google Cloud — Pub/Sub emulator and limitations](https://docs.cloud.google.com/pubsub/docs/emulator)
- [Google Cloud — Cloud Storage data validation and checksums](https://docs.cloud.google.com/storage/docs/data-validation)
- [Microsoft — Azurite and Azure Storage differences](https://learn.microsoft.com/en-us/azure/storage/common/storage-use-azurite)
- [Microsoft — Run automated tests using Azurite](https://learn.microsoft.com/en-us/azure/storage/blobs/use-azurite-to-run-automated-tests)
- [Microsoft — Azure Service Bus emulator overview and limitations](https://learn.microsoft.com/en-us/azure/service-bus-messaging/overview-emulator)
- [Microsoft — Service Bus message loss, duplicates and idempotency](https://learn.microsoft.com/en-us/azure/service-bus-messaging/service-bus-message-loss-and-duplicates)
- [Microsoft — Azure Blob conditional headers and ETag](https://learn.microsoft.com/en-us/rest/api/storageservices/specifying-conditional-headers-for-blob-service-operations)
