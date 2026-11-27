# Event Schema Evolution and Interpreting Historical Data

## 1. The Problem: Application Code Changes While Historical Events Remain

Imagine an equipment rental system that stored a `DepositCaptured` event last year. Back then, the payload contained only the amount, currency, and transaction ID. Later, the development team wants to add the payment channel, rename the provider field, and separate refund details. A new application version must read **the entire history** to reconstruct contract state or rebuild reports.

If the new code only understands the new JSON, replay may fail. If it silently interprets old data as new data, the system may **parse cleanly yet compute wrong results**, a bug far worse than a parse failure. Conversely, keeping old code around forever also makes data harder to evolve.

In event-based data modeling, good design must answer:

1. **What structure do old events have?** Which fields are present, and what are their types and units?
2. **What did old events mean at write time?** Did “paid” mean capture was requested, accepted by the bank, or settled?
3. **How does the new application read old data?** Multi-version readers, upcasters, migrations, or separate projections?
4. **What can change without breaking consumers?** Separate internal contracts from externally published messages.
5. **How is it verified?** Replay must yield expected outputs, produce no side effects, and never silently mutate history.

This is a core capability of **data modeling**: turning business requirements into data contracts with explicit names, types, constraints, keys, and lifecycles—never treating JSON as schema-less blobs exempt from governance.

## 2. Separating Four Frequently Confused Kinds of Versions

In event-sourced or event-log systems, several values are all called “version” while carrying distinct responsibilities:

| Concept | What is it used for? | Example |
| --- | --- | --- |
| **Stream version** | Numbers accepted events sequentially within **one aggregate stream**. | The 37th event of contract `RENT-204`. |
| **Event schema version** | Specifies how to decode and interpret the **structure of one event type**. | `DepositCaptured` payload version 1 or 2. |
| **Reducer/state-model version** | Specifies rules transforming an event sequence into state. | Balance calculation logic `rental-state-v3`. |
| **Projection/contract version** | Specifies read-data definitions or published consumer contracts. | `daily_cashflow_v2` or `DepositCapturedPublic.v2`. |

They **do not increment together**. An aggregate at stream version 100 can hold schema v1, v2, and v3 events; a projection v2 can be built from those exact events using newly approved calculation logic. Changing one event's schema does not necessarily bump every read model's version, nor may you assume zero impact by default.

Example event envelope at position 37:

~~~json
{
  "event_id": "7e6066df-9a60-43f1-87de-4f7e2eb803cc",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 37,
  "event_type": "DepositCaptured",
  "event_schema_version": 1,
  "occurred_at": "2026-02-18T03:05:00Z",
  "recorded_at": "2026-02-18T03:05:03Z",
  "payload": {
    "amount_minor": 200000,
    "currency": "VND",
    "provider_tx_id": "GW-811"
  }
}
~~~

`stream_version = 37` is the position in the `Rental` stream; `event_schema_version = 1` indicates applying the v1 definition of `DepositCaptured`. `occurred_at` is the business timestamp from a confirmed source, whereas `recorded_at` is when the system persisted the event. Both are timestamps, **not versions**.

## 3. Structural Evolution Differs From Semantic Business Changes

**Schema** changes usually involve field names, data types, required/optional flags, enums, object nesting, or units. **Semantic** changes alter what an event or field **actually asserts**.

| Proposed change | Classification | Risk level |
| --- | --- | --- |
| Add optional `payment_channel` to `DepositCaptured`. | Additive structural change. | Usually manageable if old readers tolerate unknown fields. |
| Rename `provider_tx_id` to `provider_reference` with **identical meaning**. | Structural rename. | Requires mapping/alias or new version. |
| Change `amount_minor` from integer to formatted string with separators. | Type change. | Can break readers, indexes, and arithmetic. |
| Change money from **minor units** to **major units** while keeping field name. | Semantic/unit change. | Very dangerous; identical values mean different money. |
| Rename `PaymentRequested` to `PaymentCaptured` without provider confirmation. | Event-meaning change. | Invalid if treating a request as captured funds. |
| Add an enum value `PARTIALLY_REFUNDED`. | Expanding valid value set. | Exhaustive consumer switches may fail or silently skip. |
| Split `RentalClosed` into `EquipmentReturned` and `FinanciallySettled`. | Business-fact boundary change. | Requires migration/old-interpretation rules, not just field edits. |

**Important rule:** bumping `event_schema_version` lets readers parse a new representation, yet **never legitimizes changing meaning**. If “successful payment” shifted from “request submitted” to “provider confirmed capture”, historical records must not automatically be treated as real captures.

### Define Every Event in One Complete Sentence

Example event contract:

> `DepositCaptured`: an authoritative payment provider confirmed the deposit was successfully captured with a unique transaction ID, amount, and currency recorded at confirmation time.

This definition must accompany the **confirmation milestone**, authoritative source, deduplication rules, and field schema. If historically an old event emitted as soon as a capture request went out, both share a topic yet carry different meanings. Classify or interpret those records per known truth rather than turning them into successes via a rename.

## 4. Backward Compatibility, Forward Compatibility, and Contract Scope

Common compatibility checks include:

- **Backward compatibility (reader-oriented definition):** a **new** reader can read data written by an **old** writer.
- **Forward compatibility:** an **old** reader can read data written by a **new** writer.
- **Full compatibility:** both directions satisfy the chosen rules.

Naming and validation rules vary across schema registries and serialization frameworks; always consult your tool's exact conventions. Here we use the reader/writer definitions above to clarify the design problem.

Suppose v1 has `amount_minor` and `currency`. v2 adds `payment_channel`:

~~~json
{
  "amount_minor": 200000,
  "currency": "VND",
  "payment_channel": "BANK_TRANSFER"
}
~~~

For a v2 reader to understand old events, define how **absent fields** are handled. Here `payment_channel = null` or `UNKNOWN` may fit if the business allows an “unknown” state. **Never default to `BANK_TRANSFER`** if historical events lack evidence.

For a v1 reader to understand new events, it must **accept and ignore** extra fields, or the system must serve a dedicated v1 representation. A v1 reader configured to reject unknown fields is not forward compatible even when a change is “additive only”.

| Schema change type | New reader reads old event | Old reader reads new event | Caveats to watch |
| --- | --- | --- | --- |
| Add optional field | Usually works. | Only if unknown fields are ignored/allowed. | Missing values must carry valid semantics. |
| Add required field without valid default | Usually fails. | Depends on reader checks. | Never invent defaults to force-fit data. |
| Remove field | New reader must not need it or must use an adapter. | Old reader may lack required data. | Audit consumers and read models. |
| Rename field | Needs alias/mapping or new version. | Needs reverse mapping if old readers remain live. | Preserve exact meaning and units. |
| Change type/unit | Needs provable conversion. | May fail parsing/interpretation. | Also watch arithmetic/precision. |
| Add enum value | New reader usually supports it. | Old reader may encounter unknown values. | Must define unknown-enum policy. |
| Change event meaning | Cannot be handled merely as a schema rename. | Cannot be handled merely as a schema rename. | Requires business contract and migration plan. |

**There is no absolute “adding any field is always safe” rule.** Behavior depends on serialization format (JSON, Avro, Protobuf...), required/default policies, validation modes, consumer parsing behavior, and contract guarantees.

## 5. Running Example: Evolving `DepositCaptured` From v1 to v2

Suppose contract v1 has been ratified:

~~~json
{
  "event_type": "DepositCaptured",
  "event_schema_version": 1,
  "payload": {
    "amount_minor": 200000,
    "currency": "VND",
    "provider_tx_id": "GW-811"
  }
}
~~~

New business requirements want:

- Clearer naming: `provider_reference` instead of `provider_tx_id`.
- Recording `payment_channel`, while **historical events may lack this information**.
- Preserving the definition “funds successfully captured”, integer minor units, and valid ISO currency codes.
- Preserving event IDs and order within the stream.

v2 representation:

~~~json
{
  "event_type": "DepositCaptured",
  "event_schema_version": 2,
  "payload": {
    "amount_minor": 200000,
    "currency": "VND",
    "provider_reference": "GW-811",
    "payment_channel": "BANK_TRANSFER"
  }
}
~~~

Interpretation policy must state explicitly that v1 `provider_tx_id` and v2 `provider_reference` **are simply two names for the same identifier**. If v1 was actually a “request ID” while v2 is a “settled transaction ID”, they **cannot** be treated as a simple rename.

For v1 events lacking payment channel, the canonical in-memory representation can be:

~~~json
{
  "amount_minor": 200000,
  "currency": "VND",
  "provider_reference": "GW-811",
  "payment_channel": null
}
~~~

Here `null` means **absent in the historical source**, not that payment used no channel. A channel breakdown dashboard must include an “unknown” bucket rather than silently assigning all legacy data to one channel and skewing statistics.

### When Must You Not Upcast Automatically?

Suppose the system previously had `PaymentRecorded.v1` with payload:

~~~json
{
  "amount": 200000,
  "status": "SUCCESS"
}
~~~

No documentation states whether `amount` is major or minor units, or whether `SUCCESS` meant bank confirmation or merely request acceptance. Converting it directly into `DepositCaptured.v2` is **guessing semantics**. Better handling:

1. Recover the v1 contract, code/records, and authoritative reconciliation data within permitted scope.
2. If meaning can be verified, write a transformation rule **with documentation and test cases**.
3. If unverifiable, retain an explicit legacy/unknown state; sensitive metrics must separate those buckets or require manual reconciliation.
4. If business adjustments are needed once new evidence arrives, append an appropriate **correction/confirmation event** instead of silently editing source history.

**Never fabricate timestamps, units, actors, transactions, or confirming sources** merely to make an old payload fit a new schema.

## 6. Upcasting: Transforming Old Representations Into Canonical Read Form

An **upcaster** is a function transforming an older-version event into a newer in-memory representation. It typically sits at the event-store read boundary before events reach reducers/projectors.

~~~mermaid
flowchart LR
    ES[("Event store: immutable raw events")] --> D["Decode by event_type + schema_version"]
    D --> U["Upcaster v1 → v2 (if needed)"]
    U --> V["Validate canonical contract"]
    V --> R["Reducer / projector"]
    R --> S[("State / read model")]
~~~

Crucially, **an upcaster does not update stored raw data**. The original event keeps `event_schema_version = 1`, preserving history and allowing verification of interpretation logic. Conversion happens only on read.

### Example Upcaster Logic

~~~text
upcast_DepositCaptured(event):
    require event.type == "DepositCaptured"

    if event.schema_version == 1:
        require event.payload.amount_minor is a valid integer >= 0
        require event.payload.currency is a supported currency code
        require event.payload.provider_tx_id is non-empty

        return CanonicalDepositCaptured(
            amount_minor = event.payload.amount_minor,
            currency = event.payload.currency,
            provider_reference = event.payload.provider_tx_id,
            payment_channel = UNKNOWN
        )

    if event.schema_version == 2:
        validate v2 fields, types and business constraints
        return CanonicalDepositCaptured(
            amount_minor = event.payload.amount_minor,
            currency = event.payload.currency,
            provider_reference = event.payload.provider_reference,
            payment_channel = event.payload.payment_channel or UNKNOWN
        )

    fail with UnsupportedEventVersion
~~~

This pseudocode uses `UNKNOWN` as **an explicit missing-information value** in the canonical model; in implementation, specify clearly how `UNKNOWN`, `null`, and empty strings differ.

### Properties to Preserve

- **Deterministic:** the same v1 event and upcaster version always yield the same canonical representation.
- **No side effects:** never capture/refund funds, send emails, or append new events during replay.
- **No mutable external dependencies:** never consult today's fee schedule or current channel names to rewrite last year's facts.
- **No lost identity:** preserve `event_id`, `aggregate_id`, `stream_version`, and `occurred_at`; if adding derived interpretation metadata, distinguish it from original metadata.
- **Never skip unknown versions:** fail explicitly and observably; silently skipping a balance-altering event corrupts state.
- **Chainable:** across v1 → v2 → v3, transformations can be chained or mapped directly to a canonical model, provided the full chain and lifecycle bounds are tested.

An upcaster should operate only on **proven structure/meaning**. If v2 adds a fact required for financial decisions that v1 lacks, an upcaster cannot conjure new facts. Adjust read models, collect verified supplemental evidence, or accept that some historical queries lack sufficient source data.

## 7. Multi-Version Direct Readers or Upcasters?

Two common patterns exist for reading legacy events:

**Approach A — version-specific readers:** each event version has its own decoder and handler; reducers handle v1 and v2 via conditional branches.

**Approach B — canonical representation/upcasting:** decoders read events in their original schema, then convert older versions into one canonical event type before reducers process them.

| Criterion | Per-version reader | Upcaster to canonical form |
| --- | --- | --- |
| Where differences live | Inside individual handlers. | At the event-read boundary. |
| Reducer complexity | Can grow with version count. | Usually simpler once normalized. |
| Historical fidelity | Good if every handler is maintained. | Good if conversion preserves meaning without fabricating facts. |
| Risk | Calculation logic scattered and inconsistent across projections. | A buggy normalization misleads all consumers at once. |
| Best suited when | Few versions; intentional semantic differences. | Many structural changes with valid mappings. |

You can **combine both**: upcast purely technical differences while handling **distinct semantics** via separate event types or handlers. Never force every old event into one canonical event if doing so erases real business distinctions.

### Java Example: Safe Canonical Type

A Java design can use a dedicated type for normalized events:

~~~java
record DepositCapturedCanonical(
    long amountMinor,
    String currency,
    String providerReference,
    String paymentChannel // null means unknown in this contract
) {}

final class DepositCapturedUpcaster {
    static DepositCapturedCanonical fromV1(
            long amountMinor,
            String currency,
            String providerTxId
    ) {
        if (amountMinor < 0
                || currency == null || currency.isBlank()
                || providerTxId == null || providerTxId.isBlank()) {
            throw new IllegalArgumentException("Invalid historical event");
        }
        return new DepositCapturedCanonical(
                amountMinor, currency, providerTxId, null);
    }

    static DepositCapturedCanonical fromV2(
            long amountMinor,
            String currency,
            String providerReference,
            String paymentChannel
    ) {
        if (amountMinor < 0
                || currency == null || currency.isBlank()
                || providerReference == null || providerReference.isBlank()) {
            throw new IllegalArgumentException("Invalid event");
        }
        return new DepositCapturedCanonical(
                amountMinor, currency, providerReference, paymentChannel);
    }
}
~~~

This illustrates **post-deserialization conversion**, not a full serializer, validator, or event store. Production applications must also validate supported currencies, monetary bounds, permissions, and business invariants. `null` for legacy payment channel is valid only if the canonical contract explicitly defines `null` as “unknown”.

## 8. Do Not Alter Historical Meaning When Replaying With New Code

In event sourcing, state is computed by applying events in stream order. After upgrading code, **the same raw events** pass through the new reducer. Separate two goals:

- **Recovering state matching historical decisions/calculations:** requires the rules and facts originally used, or equivalent compatible logic.
- **Creating a new view under updated definitions:** may build a new projection from historical events, provided you announce that **calculation rules and metric meanings changed**.

For example, last year a dashboard computed `gross_captured` as total capture events. Now finance wants `net_cashflow = captured - refunded`. Do not keep calling the field `revenue` on the old dashboard and let users assume both numbers share the same meaning. Version or create a new projection, and define policies for partial refunds, business dates, and currencies.

### Changing Event Meaning May Require a New Event Type

Suppose `RentalReturned` previously emitted when a customer **clicked the return request button**, whereas the workflow now recognizes “returned” only after **warehouse inspection acceptance**. These are two different confirmation points:

- Historical `RentalReturned` was actually **ReturnRequested** under the old definition.
- New occurrences should emit **EquipmentReturnAccepted** after inspection proof.

Never upcast every `RentalReturned.v1` into `EquipmentReturnAccepted.v2`, because inspection proof never existed. Keep a legacy handler, map to `ReturnRequestedLegacy` in analytical models, or append new confirmation events after reconciliation if business rules require. That is **domain model evolution**, not a routine JSON rename.

### Late-Arriving Data and Retroactive Timestamps

`stream_version` defines accepted order within a stream; `occurred_at` reflects when the occurrence happened per confirming source, and `recorded_at` is storage time. An event for yesterday's occurrence can be appended today at a new version. During aggregate replay, never reorder stream sequence by timestamp. If you need both “what the system knew at time X” and “what was actually effective at time X given current evidence”, define separate temporal dimensions—potentially requiring a bitemporal model.

## 9. Physical Event Store and Attaching Schema Contracts

In PostgreSQL, you can store a strongly typed envelope alongside a `JSONB` payload. This is flexible yet **does not automatically validate the structure of every event version**.

~~~sql
CREATE TABLE event_stream (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0),
    PRIMARY KEY (tenant_id, aggregate_type, aggregate_id)
);

CREATE TABLE domain_event (
    event_id             UUID PRIMARY KEY,
    tenant_id            UUID NOT NULL,
    aggregate_type       VARCHAR(80) NOT NULL,
    aggregate_id         VARCHAR(100) NOT NULL,
    stream_version       BIGINT NOT NULL CHECK (stream_version > 0),
    event_type           VARCHAR(120) NOT NULL,
    event_schema_version SMALLINT NOT NULL
                         CHECK (event_schema_version > 0),
    occurred_at          TIMESTAMPTZ NOT NULL,
    recorded_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload              JSONB NOT NULL
                         CHECK (jsonb_typeof(payload) = 'object'),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream
            (tenant_id, aggregate_type, aggregate_id),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, stream_version)
);

CREATE INDEX ix_domain_event_type_version
    ON domain_event (event_type, event_schema_version);
~~~

**Explanation:**

- `(tenant_id, aggregate_type, aggregate_id)` identifies the stream in multi-tenant setups.
- `UNIQUE(tenant_id, aggregate_type, aggregate_id, stream_version)` enforces a unique slot per stream; the application must use expected-version/transaction control on append to keep contiguous history and reject decisions built on stale state.
- `(event_type, event_schema_version)` identifies the decoder and contract to apply. Never infer schema solely from stream position.
- `CHECK(jsonb_typeof(payload) = 'object')` does not prove `amount_minor` is present, an integer, in valid units, or that `provider_reference` is non-empty. Enforce contract/version validation before appending and upon reading.
- Indexing by type/version helps inventory events still at older versions; weigh write overhead, data size, and real query needs before deploying.

### Should You Add a Schema Management Table?

Use a **schema registry** or versioned contract catalog (in code/artifacts, metadata store, or dedicated schema system). Governed information should include:

| Contract field | Example |
| --- | --- |
| Identity | `event_type = DepositCaptured`, `schema_version = 2`. |
| Format | JSON Schema, Avro schema, Protobuf schema, or published codec. |
| Required fields | `amount_minor`, `currency`, `provider_reference`. |
| Data rules | Amounts, currencies, IDs, enums, units, and cross-field relationships. |
| Semantics | Emission conditions, authoritative source, valid usage timestamps. |
| Compatibility policy | Which readers/writers remain supported; what counts as a breaking change. |
| Retention/privacy | Which fields are sensitive, retention window, and redaction policy. |

A schema registry manages **shape and partial compatibility**; it does not inherently know whether `PaymentCaptured` in your business means funds hit the account. Therefore, document event definitions and invariants alongside schemas.

### What Happens When Changing Storage Engines?

A relational event store can feed document, graph, or analytical read models. Changing table layouts or pipelines must never silently alter historical event payloads. For JSON documents, apply similar structural versioning and validation; for analytical warehouses, align on business dates, deduplication keys, and missing-data rules. Choose technology by query needs, consistency, and operational cost—never use “schema-on-read” as an excuse to skip data contracts.

## 10. Domain Event Evolution Differs From Integration Event Evolution

A **domain event** is a fact defined inside the source domain boundary; its contract serves internal decisions and replay. An **integration event** is a message published to other systems; it has external consumers and its own compatibility lifecycle.

A domain event `DepositCaptured.v2` may produce an integration event `RentalDepositReceived.v1` for the CRM system. Both can carry different names, payloads, and versions:

~~~mermaid
flowchart LR
    C["Successful command"] --> D["Domain event DepositCaptured.v2"]
    D --> E[("Source event store")]
    D --> O["Outbox / public contract mapper"]
    O --> I["Integration event RentalDepositReceived.v1"]
    I --> N["Consumer: CRM"]
    I --> A["Consumer: Analytics"]
~~~

Separating the two contracts offers clear benefits:

- Allows changing internal domain storage without forcing CRM to update immediately.
- Strips internal fields or sensitive data from published payloads.
- Publishes messages at **sufficiently confirmed business milestones** instead of leaking intermediate states.
- Allows consumer-specific versioning and compatibility policies.

A domain event change does not automatically require changing integration events; conversely, you may create an integration event v2 because consumers need another field even when domain events stay unchanged. When serving old and new consumers simultaneously, use **contracted dual publishing** (two clearly versioned message types) during migration. Make sure consumers know both represent **the same occurrence** so no consumer double-counts.

When publishing via broker/outbox, enforce idempotency, retries, late-arrival tolerance, and clear separation between domain event ID and message ID. Bumping a version never automatically guarantees end-to-end exactly-once delivery.

## 11. Safe Rollout Strategy for Schema Changes

A controlled plan begins by **inventorying existing data and consumers** before modifying writers.

### Phase A — Audit and Contract Design

1. List actual event types and versions in the event store; count records per version and their date ranges.
2. Identify consumers: command state loaders, projectors, reports, integration mappers, rebuild jobs, operational tools.
3. Collect **real historical v1 samples**, including missing fields, anomalous values, and previously corrected cases.
4. Propose v2 with **schema and semantic definitions**; classify breaking vs. additive changes and identify facts that cannot be inferred from v1.
5. Implement mappings/upcasters or dedicated v1 handlers; define invariant checks and reconciliation rules.

### Phase B — Deploy Readers Before Writers (Where Applicable)

1. Deploy readers able to understand **both v1 and v2** or safely normalize v1 to canonical form.
2. Dry-run replay on sample historical data; verify final state, currencies, amounts, timestamps, and milestones.
3. Ensure critical projectors/consumers are compatible. For external consumers, agree on migration schedules and v1 support windows if needed.
4. Only then enable writers to emit v2 events; monitor decode error rates, unsupported version alerts, and projection lag.

“Readers before writers” lowers risk in decoupled deployments, yet it is not sufficient for every change. Some systems need **dual writes/dual publishes**, feature flags, or consumer isolation; maintaining two contracts requires explicit deduplication and sunset dates.

### Phase C — Rebuild Read Models When Needed

If a schema change merely adds fields unused by old logic, read models may not need a rebuild. If state-calculation or KPI logic changes:

1. Create a new read model with an explicit name/version instead of overwriting the live table in place.
2. Replay history using readers supporting historical events.
3. Catch up on live events via a cursor/checkpoint safe under **commit order**; never assume pre-commit IDs guarantee zero gaps.
4. Reconcile independently against invariants and source data.
5. Cut over read traffic to the new projection under controlled routing, keeping rollback capability ready.

If aggregate snapshots hold state computed by the old reducer, they may be **incompatible** with new logic. Either migrate snapshots with proven equivalence or discard old snapshots, replay from source events, and generate fresh snapshots.

### Phase D — Retire Old Support Only When Truly Safe

Never delete the v1 decoder merely because writers stopped emitting v1. As long as v1 events remain in storage, a rebuild or loading a dormant aggregate may still encounter them. Retire support only when:

- A durable, verified migration completed, or v1 data lies outside active reading scope by policy.
- Every affected consumer, snapshot, and projection has been addressed.
- Backup/rollback plans exist and historical interpretability guarantees remain intact.

## 12. Testing Against Historical Data, Not Just New JSON

Test suites should cover both **historical data** and **business behavior**.

| Test | Goal | Failure signal |
| --- | --- | --- |
| **v1/v2 contracts** | Every event parses per its recorded schema. | New reader rejects valid v1 events. |
| **Missing fields** | New fields absent in old events are represented accurately. | Fabricating a payment channel with zero proof. |
| **Renames/units** | Mappings preserve values and meaning. | 200,000 VND multiplied/divided by 100 arbitrarily. |
| **Unknown version/enum** | Errors clearly and observably. | Silently skipping balance-altering events. |
| **Replay equivalence** | New reducer over semantically unchanged data yields expected state. | Balances or statuses shift due to buggy upcaster. |
| **Legacy semantics** | Events with older meanings are recognized distinctly. | `PaymentRequested` treated as `PaymentCaptured`. |
| **Corrections/reversals** | References, adjustment amounts, and ordering stay valid. | Reversing the same obligation twice or dropping corrections. |
| **Snapshot compatibility** | Snapshot + tail loads cleanly with compatible reducer. | State diverges from full replay at the same version. |
| **Cross-service contracts** | Old/new consumers receive accurate published events. | Dual publish doubles revenue figures. |
| **Privacy/retention** | Sensitive fields do not leak into integration payloads. | Events publish raw internal objects. |

### Golden Fixtures and Replay Tests

Maintain anonymized/validated **golden fixtures** built from real events, covering:

- Short v1-only streams.
- Streams transitioning from v1 to v2.
- Events missing optional fields, legacy enums, and legacy ID formats.
- Streams with retroactive corrections, partial refunds, and multiple captures/refunds.
- Streams holding snapshots written by older reducers.

For each fixture, specify **business-verified expected outcomes**: statuses, monetary totals, currencies, timestamps, and fields intentionally left “unknown”. Do not merely snapshot JSON output and treat every difference as a bug; when fixing projection logic, verify against source truth and new definitions rather than locking in old bugs.

Example test logic:

~~~text
given event DepositCaptured.v1:
    amount_minor = 200000
    currency = VND
    provider_tx_id = GW-811

when decoded and upcasted by reader v2

then canonical.amount_minor == 200000
and  canonical.currency == VND
and  canonical.provider_reference == GW-811
and  canonical.payment_channel == UNKNOWN
and  event_id / stream_version remain unchanged
and  no network or database writes occur
~~~

**Historical tests must never emit side effects.** Replay runs must make zero payment API calls, send zero emails, and write zero events back to the event store. Inspect diffs between event-reconstructed state and existing read models, keeping in mind the old read model itself may have contained bugs.

## 13. When Should You Migrate Raw Events, and When Should You Not?

Some teams consider rewriting all v1 events into v2 in storage so old code can be removed. This can fit controlled migration projects, yet it **differs from read-time upcasting** and carries major risks:

| Approach | Advantages | Limits/warnings |
| --- | --- | --- |
| **Keep raw events + upcast on read** | Preserves trail, easy reader rollback, avoids rewriting full history. | Maintains conversion code; CPU cost on large replays; needs long-term testing. |
| **Keep raw events + multi-version readers** | Stays faithful to each version's semantics; avoids forced mappings. | Reducer/projector complexity scales with version count. |
| **Materialize canonical copy** | Fast reads; avoids repeated conversion on hot read paths. | Copy needs lineage/source IDs and sync control; does not replace raw events without explicit decision. |
| **Rewrite/migrate event store** | Standardizes physical storage and retires old schemas. | Risks breaking audits, signatures, checksums, ordering, replication, and interpretability; demands strict verification. |

**Never silently rewrite v1 payloads into v2 while keeping identical `event_id`/timestamps** as if nothing changed. If rewriting is required for legal compliance or repairing corrupted data, follow a separate governed workflow: backups, mapping records, blast-radius analysis, data verification, snapshot/projection updates, and provenance tracking. When dealing with **an accepted business fact later discovered wrong**, prefer an appropriate **correction event** over traceless history edits.

**Privacy is an independent constraint:** append-only does not permit retaining personal data indefinitely when unlawful or against policy. Reference IDs, separating sensitive data, authorization, retention, encryption, and controlled erasure/anonymization should be designed upfront; some erasure mechanisms limit replayability and those limits must be stated explicitly.

## 14. Common Mistakes in Event Evolution

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Checking only whether JSON parses | Readers may misapply units or business meaning. | Version schemas alongside semantic definitions and invariants. |
| Using `stream_version` as payload version | Decoders select the wrong schema. | Keep `stream_version` and `event_schema_version` separate. |
| Filling “nice” defaults when v1 lacks facts | Historical metrics silently skew. | Use explicit unknown values or reconcile authoritative sources. |
| Turning `Requested` into `Completed` via rename | Treats intent as confirmed success. | Separate event types and acceptance criteria. |
| Deleting old decoders when writers move to v2 | Replay/recovery of older streams fails. | Retain compatible readers across the data lifecycle. |
| Upcasters calling live APIs to backfill old fields | Replay turns non-deterministic and uses mutated data. | Rely strictly on events and immutable versioned references. |
| Upcasters silently ignoring unknown events | Balances drop or invariants break without alerts. | Fail/route to controlled error handling. |
| Adding new enum values without auditing consumer switches | Old consumers fail on unhandled cases. | Run compatibility tests and enforce unknown-enum rules. |
| Rebuilding from incompatible old snapshots | State combines two conflicting logics. | Version reducers; migrate with proof or replay from scratch. |
| Dual publishing without correlation/dedup | Consumers count the same business event twice. | Version contracts, event/source IDs, and consumer dedup policies. |
| Changing KPI logic without renaming/versioning | Reports across eras become incomparable. | Explicit projection contracts and migration milestones. |
| Testing only newly produced data | Millions of legacy events crash on deploy. | Golden fixtures and replay tests across diverse historical streams. |

## 15. Exercise: Designing an Evolution Path Without Losing Historical Meaning

**Context:** a delivery management system has operated for years. Event `DeliveryUpdated.v1` has payload:

~~~json
{
  "shipment_id": "SHP-204",
  "status": "DONE",
  "time": "2026-08-20 10:30",
  "operator": "EMP-17"
}
~~~

Now the business wants to distinguish: **driver reported delivery**, **customer confirmed receipt**, **delivery failed**, and **parcel returned to warehouse**. The new system wants events `DeliveryAttempted`, `DeliverySucceeded`, `DeliveryFailed`, and `ReturnToWarehouseConfirmed`; timestamps must include explicit timezones, and events will feed SLA reporting.

### Tasks

1. **Audit old definitions:** list what is unknown in `DeliveryUpdated.v1`. Did `DONE` mean the driver tapped complete or the recipient confirmed? Which timezone does the string represent, and could DST or offline devices be involved? Is `operator` the driver or a data-entry clerk?
2. **Define business boundaries:** when is each new event emitted, who are the actor/subject/aggregate, and what evidence/authoritative source suffices?
3. **Classify migration:** which fields map deterministically from v1; which cannot be inferred and must retain a legacy/unknown state?
4. **Version contracts:** design an envelope with `event_id`, `aggregate_id`, `stream_version`, `event_type`, `event_schema_version`, `occurred_at`, `recorded_at`, and meaningful new payloads.
5. **Choose read strategy:** write upcasters for safe structural mappings; keep dedicated readers or legacy fields for semantically ambiguous events.
6. **Design new projections:** compute delivery success rate per **actual delivery attempt**, SLA from trusted business timestamps, and the proportion of legacy events that cannot be classified. Never lump “unknown” into “delivery succeeded”.
7. **Rollout roadmap:** readers before writers, integration event mappings, compatibility tests, parallel rebuild, reconciliation, and cutover; state when v1 support can safely retire.
8. **Testing:** include at least one v1-only stream, one mixed v1/v2 stream, one failed attempt followed by successful redelivery, one late-arriving event, and one event lacking timezone info.
9. **Limits:** if legacy carriers no longer provide delivery proof, state explicitly which historical portion cannot be “upgraded” into verified outcomes.

### Verification Checklist

| Criterion | Passing model |
| --- | --- |
| **Historical accuracy** | Never turns ambiguous `DONE` into customer-confirmed delivery without proof. |
| **Explicit versioning** | Stream, event schema, and projection versions are independent and contracted. |
| **Compatibility** | New readers handle valid legacy shapes; unknowns are handled deliberately. |
| **No fabricated data** | Missing timestamps, currencies, actors, units, and statuses are explicitly surfaced. |
| **Replay** | Same source and interpretation rules yield identical outputs; zero side effects. |
| **Safe rollout** | Includes historical tests, rebuilds, reconciliation, cutover, and rollback. |
| **Physical model** | Stream/version keys, indexes, and constraints serve real queries and version audits. |

**Conclusion:** evolving event structures is not merely “changing JSON v1 to JSON v2”. It is preserving **the ability to accurately interpret what the system recorded**, controlling the boundary between schema changes and business-meaning changes, and ensuring current and future consumers read history under verifiable contracts. When old data lacks proof, the right choice is to represent that boundary honestly rather than fabricating facts. On that foundation, event stores, projections, documents, graphs, and analytical systems can evolve while remaining trustworthy.
