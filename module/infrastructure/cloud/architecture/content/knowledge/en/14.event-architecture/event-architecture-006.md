# Event Contracts, Schemas, and Evolution Compatibility

## 1. Why Do Events Need a Clear Contract?

In an event-driven architecture, services exchange information through events such as BookingConfirmed, PaymentCaptured, or InventoryChanged. Producers can be deployed and released independently of consumers; a single event can also be consumed by multiple consumers for notifications, search, analytics, or partner integrations. That independence stays sustainable only when all parties **understand the same meaning and the same data structure**.

If a producer renames a field, changes a currency unit, or alters the meaning of a status without warning, older consumers may misread data, drop events, or halt processing. The fallout goes beyond parse errors: the system may send wrong notifications, corrupt inventory counts, or miscalculate revenue.

An **event contract** specifies what the producer commits to emitting and what consumers are permitted to rely on: event semantics, envelope/payload structure, data types and constraints, timing rules, identity, ordering, versioning, access permissions, and compatibility policies. A **schema** describes the structure and part of the validation rules of a contract; a syntactically valid schema does not guarantee sound business semantics.

In the **CLOUD_ARCHITECTURE** module, designing event contracts directly ties into choices around networking, compute, storage, brokers, and deployment models. You must balance **reliability, security, scalability, cost, and operability** using Well-Architected thinking.

Running example: a booking platform emits booking confirmation events to a notification service, a search indexer, analytics, and a partner system. The producer and consumers follow independent release schedules; messages may be stored and replayed days later, and new consumers may roll out while older consumers are still running.

## 2. Distinguishing Events, Commands, Notifications, and Schemas

| Concept | Question answered | Example |
| --- | --- | --- |
| **Event** | What happened? | BookingConfirmed |
| **Command** | What is a component asked to do? | ConfirmBooking |
| **Notification** | Who needs to know an event happened? | Send an email when a booking is confirmed |
| **Event contract** | What meaning and data does the producer commit to? | BookingConfirmed v1, emission conditions, and field definitions |
| **Schema** | What structure, types, and constraints does the message have? | bookingId is a non-empty string, occurredAt is a timestamp |
| **Schema registry** | Which schemas are registered, and which versions are valid and compatible? | Registry storing schema IDs, versions, and compatibility policies |

Event names should describe a business fact that has occurred, typically using past tense or a completed state. BookingConfirmed is not synonymous with a request to confirm. Producers should emit an event only after business conditions are satisfied according to the agreed contract.

### 2.1. Events Are Historical Records, Not Arbitrary Database Dumps

Events should describe occurrences meaningful to consumers. Avoid automatically serializing entire entities or database rows into messages. Internal structures change rapidly and often contain unnecessary sensitive data.

For example, a BookingConfirmed event might provide bookingId, customerRef, propertyId, confirmation timestamp, currency, and confirmed total amount. It does not need to include passwords, tokens, full billing addresses, or the customer's entire action history.

A good contract tells consumers **what they are allowed to rely on**, while also stating what consumers must not assume. For instance, consumers must not assume events always arrive in strict chronological order merely because the producer created them in order.

## 3. Contract Structure: Envelope and Payload

A message is typically divided into:

- **Envelope/metadata:** information for routing, tracing, version governance, and interpreting the message.
- **Payload/data:** the business content the event conveys.

Illustrative example:

~~~json
{
  "specVersion": "1.0",
  "id": "evt-7f21a9",
  "type": "com.example.booking.confirmed",
  "source": "booking-service",
  "subject": "bookings/booking-42",
  "time": "2026-12-18T08:30:00Z",
  "schemaVersion": 1,
  "correlationId": "req-51bc",
  "dataContentType": "application/json",
  "data": {
    "bookingId": "booking-42",
    "customerRef": "customer-18",
    "propertyId": "property-91",
    "confirmedAt": "2026-12-18T08:29:58Z",
    "currency": "VND",
    "totalAmountMinor": 125000000
  }
}
~~~

These field names are an illustrative design, not a mandatory standard schema. Some systems use CloudEvents or a custom envelope format. When adopting a standard envelope, follow the standard's semantics and add extensions in a controlled way to avoid creating two conflicting sources of metadata.

### 3.1. Metadata Fields to Consider

| Field | Purpose | Rules to agree upon |
| --- | --- | --- |
| id/eventId | Uniquely identifies an event emission | Uniqueness scope, stability across retries, retention window for deduplication |
| type/eventType | Event type name | Naming conventions/namespace, stability, never reuse a name with a new meaning |
| source/producer | Emitting system | Verifiable producer identity, not just a self-declared string |
| subject/aggregateId | Related business entity | Identification and partitioning rules |
| time/occurredAt | Time the event occurred | Timezone, precision, time source |
| schemaVersion | Payload contract version | Version scope: per event type or schema ID |
| correlationId | Links multiple steps in a journey | Propagated across requests, events, consumers, and workflows |
| causationId | Identifies the message or action that caused this event | Useful for tracing causal chains |
| trace context | Links to distributed tracing | Propagation rules through brokers without leaking sensitive data |
| tenantId | Customer routing and isolation in multi-tenant systems | Source verification, access control, and partitioning capability |

Not every event needs every field. Each field requires clear definitions for type, optionality, semantics, generation, verification, and protection policies. If both an envelope time and a payload timestamp exist, document how they differ—such as when the event was emitted versus when the transaction was confirmed.

### 3.2. Designing Payloads Around Business Semantics

Fields must be documented clearly enough that consumers do not have to guess:

- Is an amount in minor units or decimal? Which currency standard applies? Are fees and taxes included in the total?
- Is a timestamp the occurrence time, database write time, or publisher emit time?
- Is status the status at the moment of the event or a current status that may change afterward?
- Is an ID an internal identifier, public ID, or an identifier cleared for partner sharing?
- Can an optional field be absent, null, or an empty string? Do those three cases mean the same thing?

For example, the name totalAmount does not indicate the unit or currency. A clear contract might specify totalAmountMinor as an integer in the currency's minor unit paired with an agreed currency code. Ensure that representation works for every currency/precision the product supports; do not assume all currencies have two decimal places.

## 4. Schema Definitions and Validation

A schema describes message structure in a machine-checkable form. Depending on the stack, teams may use JSON Schema, Avro, Protocol Buffers, or other formats. Systems can also use a schema registry to manage versions and prevent producers from publishing non-compliant data.

### 4.1. JSON Schema

Simple schema example for the BookingConfirmed payload:

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.invalid/booking-confirmed-v1.json",
  "title": "BookingConfirmed",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "bookingId",
    "confirmedAt",
    "currency",
    "totalAmountMinor"
  ],
  "properties": {
    "bookingId": {
      "type": "string",
      "minLength": 1
    },
    "confirmedAt": {
      "type": "string",
      "format": "date-time"
    },
    "currency": {
      "type": "string",
      "pattern": "^[A-Z]{3}$"
    },
    "totalAmountMinor": {
      "type": "integer",
      "minimum": 0
    },
    "customerRef": {
      "type": "string"
    }
  }
}
~~~

This illustrative schema checks data types, required fields, and basic constraints. In production, choose a JSON Schema draft supported by your validator, and define how format, additionalProperties, nullability, and cross-version compatibility behave. A three-letter regex pattern does not prove a currency code is supported by the business; domain validation is still required.

### 4.2. Avro

Avro expresses schemas in JSON and is widely used in event and streaming systems. Readers and writers can use schema IDs or schema resolution to interpret data according to Avro's rules. When adding fields with defaults, old and new readers resolve records differently depending on writer schema and reader schema.

Simple record example:

~~~json
{
  "type": "record",
  "name": "BookingConfirmed",
  "namespace": "com.example.booking",
  "fields": [
    {"name": "bookingId", "type": "string"},
    {"name": "confirmedAt", "type": "string"},
    {"name": "currency", "type": "string"},
    {"name": "totalAmountMinor", "type": "long"}
  ]
}
~~~

In Avro, numeric types impact representable range and schema resolution; do not swap int/long or union types merely for producer coding convenience without verifying older consumers.

### 4.3. Protocol Buffers

Protocol Buffers use message definitions and stable field numbers. Example:

~~~protobuf
syntax = "proto3";

message BookingConfirmed {
  string booking_id = 1;
  string confirmed_at = 2;
  string currency = 3;
  int64 total_amount_minor = 4;
}
~~~

Field numbers are part of the wire contract. **Never reuse a deleted field number** for a different field; reserve old numbers and names where supported by the schema format. Changing types or wire representations can break compatibility even when field names stay unchanged.

### 4.4. Comparing the Options

| Format | Strengths | Considerations |
| --- | --- | --- |
| JSON / JSON Schema | Human-readable, easy HTTP and polyglot integration; clear validation | Payloads are usually larger than binary; null/unknown field handling and validator drafts must align |
| Avro | Schema resolution suited to data pipelines/events; supports reader/writer schemas | Must manage schema IDs, defaults, and compatibility per exact Avro semantics |
| Protocol Buffers | Compact, efficient binary; field numbers support disciplined evolution | Must manage field numbers, reserved fields, and generated code; not as directly human-readable as JSON |
| XML/XSD | Useful in certain enterprise integrations and legacy systems | Verbose, complex namespaces and tooling; requires explicit schema/version management |

No format is optimal for every system. Choose based on brokers, languages, throughput, testability, partner integrations, storage needs, and team capability. More important than the format are **contract rules and consistently enforced evolution workflows**.

## 5. Schema Compatibility: Backward, Forward, and Full

Compatibility describes the ability of different producer/consumer versions to exchange data safely. Terms may be defined by a registry along specific writer/reader directions; always read the exact semantics of your registry and format.

### 5.1. Backward Compatibility

A new schema is backward compatible when newer consumers/readers can read data written under older schemas within supported rules. For instance, adding an optional field with an appropriate default can be backward compatible under certain formats and registries.

### 5.2. Forward Compatibility

A new schema is forward compatible when older consumers/readers can read data written under the new schema. This usually requires older readers to ignore new fields or the format to support equivalent handling. If older readers reject any unknown field, adding a new field can break forward compatibility.

### 5.3. Full Compatibility

Full compatibility combines both backward and forward compatibility under the registry's validation model: newer and older versions can read across each other in the specified directions. Full compatibility does not mean every business change is safe; a field remaining a string while changing meaning from "pre-tax amount" to "post-tax amount" will still cause consumers to miscalculate.

### 5.4. Compatibility Against Adjacent Versions vs. Full History

Some registries check compatibility against **the most recent previous version** (backward/forward/full), or against **all prior versions** (transitive modes). Transitive checking is stricter in streams with long-retained messages where consumers may replay years of history.

| Conceptual mode | Checked against | When to consider |
| --- | --- | --- |
| Backward | New reader against old writer data | New consumers will read existing messages |
| Backward transitive | New reader against all prior schemas in scope | Long-term replays or multiple active producer generations |
| Forward | Old reader against new writer data | New producers deploy ahead of consumers |
| Forward transitive | Old reader against all newer schemas per policy | Legacy consumers must keep reading messages from multiple producer versions |
| Full | Bidirectional between latest old and new schemas | Producers and consumers roll out independently |
| Full transitive | Bidirectional across entire schema history per policy | Compatibility needed across many retained versions |

These are conceptual descriptions. Mode names and enforcement vary across registries; some systems have additional policies or format-specific compatibility rules. Never pick a mode by name alone without examining **who writes, who reads, how long old messages are retained, and whether replays occur**.

## 6. Which Changes Are Usually Safe vs. Risky?

| Schema/contract change | Risk | Handling approach |
| --- | --- | --- |
| Add optional field with clear default | Usually safe if older consumers ignore unknown fields and format supports it | Verify compatibility in registry and test legacy consumers |
| Add required field without default | Legacy consumers/readers may fail or older writers will omit it | Add as optional first, roll out in phases, require only after consumers catch up |
| Remove an active field | Current consumers or historical replays may break | Deprecate, measure usage, migrate consumers, then stop emitting |
| Rename a field | Legacy readers cannot find the field | Add new field alongside, dual-write/dual-read temporarily, then deprecate old field |
| Change data type | Parse failures or precision loss | Introduce a new field with explicit conversion; avoid implicit casting |
| Change unit or semantics while keeping name/type | Schema-valid payload that causes business bugs | Treat as breaking change; new version/type or new field with distinct definition |
| Narrow an enum | Consumers encounter disallowed values | Consumers need unknown-value strategies; adjust values per compatibility policy |
| Add enum values | Consumers using exhaustive switches may fail | Test legacy consumers; provide an unknown/other branch |
| Change meaning of null/default | Old and new records are interpreted differently | Clearly define absent/null/default and bump version when semantics shift |
| Change partition key | Can alter ordering and load distribution | Re-evaluate ordering, hot partitions, and migration strategy |

### 6.1. Example: Adding Customer Tier

The older version only has bookingId and confirmedAt. The new version adds customerTier so analytics consumers can segment reports:

~~~json
{
  "bookingId": "booking-42",
  "confirmedAt": "2026-12-18T08:29:58Z",
  "customerTier": "gold"
}
~~~

If legacy consumers ignore unknown fields and the format/schema policy permits it, this can be non-breaking for old consumers. Still, clarify whether customerTier may be absent, whether the enum can expand, whether tier data counts as PII, and how new consumers handle historical events lacking this field.

### 6.2. Never Assume Unknown Enum Values Will Never Appear

A consumer can receive a new status from a producer deployed earlier. Design consumer logic by these principles:

- Know the exact set of statuses the consumer handles.
- Never silently treat an unfamiliar value as a success state.
- Emit safe metrics/logs when encountering an unknown value.
- Have a quarantine or business-policy handling path so messages are not silently dropped.

## 7. Versioning: Controlled Contract Changes

Several versioning strategies exist; pick one and apply it consistently across the ecosystem:

### 7.1. Version in the Event Name

Examples: BookingConfirmed.v1 and BookingConfirmed.v2. This makes clear they are distinct contracts and makes parallel coexistence straightforward during incompatible changes. The trade-off is managing more types across routing, topics, dashboards, consumers, and governance.

### 7.2. Version in Metadata / Schema Registry

The event name stays stable while a schema ID or schemaVersion determines how to parse the payload. This works well when the format/registry supports schema resolution and consumers handle multiple versions. However, metadata versions cannot automatically fix semantic changes.

### 7.3. Version in the Payload

A version field inside the payload lets consumers branch on structure, though strict rules are needed to avoid unbounded branching logic. Avoid mixing event-name versioning, schema IDs, and payload version fields without declaring which one is authoritative.

### 7.4. Do Not Bump Major Versions Just for Adding One Field

If a change is genuinely compatible under your contract and system policy, emitting a new event type may be unnecessary. Conversely, changing semantics, units, sources of truth, or state models can break consumers even if syntax stays unchanged. Versioning decisions should rest on **semantics and readability**, not simply field count.

## 8. Schema Registry and Governance

A **schema registry** stores schemas, assigns version identifiers, enforces compatibility policies, and often supplies schema IDs/metadata for producers and consumers. It catches many unsafe changes before messages reach production.

A governance workflow should include:

1. Identifying the event type and domain owner.
2. Defining the contract, schema, sample payloads, and purpose of each field.
3. Checking naming conventions, data classification, compatibility, and permissions.
4. Reviewing changes with the producer owner and representative consumer teams.
5. Registering the schema and running CI/CD checks.
6. Deploying compatible consumers first or following the designed rollout sequence.
7. Monitoring usage, validation errors, unknown fields/values, and deprecation timelines.
8. Deprecating and retiring schemas once verified that no producers or consumers still depend on them.

### 8.1. CI/CD for Contracts

A pipeline can verify:

~~~text
Pull request
  -> Validate schema syntax
  -> Lint naming / required metadata
  -> Check compatibility against registry history
  -> Validate sample payloads
  -> Consumer contract tests
  -> Security and data-classification checks
  -> Publish schema artifact
  -> Deploy producer/consumer according to rollout plan
~~~

A registry does not replace business reviews and integration tests. A schema can pass backward-compatibility checks yet still produce wrong events if the producer emits BookingConfirmed before its database transaction actually commits.

### 8.2. Access Governance

- Producers may register/write schemas only within their assigned domain or namespace.
- Producers may publish only approved event types to their corresponding topics/streams.
- Consumers may consume only required subscriptions.
- Modifying compatibility policies, deleting schemas, or running historical replays must be audited and restricted.
- Secrets, tokens, and sensitive payloads must never appear in schema descriptions, public examples, or CI logs.

## 9. Non-Breaking Schema Rollout Workflow

Even compatible changes require a planned rollout. A standard model is **expand → migrate → contract**:

1. **Expand:** add fields/schemas in a way that coexists with the old version, typically using optional fields/appropriate defaults.
2. **Migrate consumers:** deploy updated consumers capable of reading both old and new data, handling missing fields cleanly.
3. **Migrate producers:** begin emitting the new field once required consumers are ready or policy permits.
4. **Observe:** watch validation rates, consumer errors, field adoption, and unknown values.
5. **Contract:** only after all relevant consumers have migrated, consider retiring the old field or tightening constraints.

### 9.1. Field Rename Example

Suppose an existing field totalAmount needs to migrate to totalAmountMinor plus currency:

| Phase | Producer | Consumer |
| --- | --- | --- |
| 0 — current | Emits totalAmount per legacy contract | Reads totalAmount |
| 1 — expand | Emits both totalAmount and new fields with reconciliation rules | Accepts both, preferring the new fields when valid |
| 2 — migrate consumers | Continues emitting both | All required consumers read new fields; track any still using old field |
| 3 — stop old field | Stops emitting totalAmount per deprecation notice | No remaining consumers depend on old field |
| 4 — contract | Only new fields remain, or new event type if semantics broke | Consumers rely strictly on the new contract |

If legacy totalAmount was a decimal while totalAmountMinor is an integer, the producer must define rounding/conversion rules, currency exponents, and handling for older records lacking currency. **Never convert by multiplying by 100 by default** across all currencies.

## 10. Consumer Contract Testing and Compatibility Verification

Schema validation verifies structural correctness; **consumer contract tests** verify that producers emit what consumers actually rely on and consumers handle payloads according to contract.

Testing layers:

| Test type | Objective |
| --- | --- |
| Schema validation | Message matches structure, types, required fields, and constraints |
| Compatibility check | New schema satisfies policy against prior schemas |
| Producer contract test | Producer emits semantically accurate events matching the contract |
| Consumer contract test | Consumer handles valid payloads, missing fields, and unknown values per rules |
| Integration test | Broker, serialization, schema IDs, authentication, and routing work end-to-end |
| Replay test | New consumers can read historical messages stored under older versions |
| Semantic test | Units, state transitions, timestamps, and monetary amounts are interpreted accurately |

A test suite should cover:

- Minimal valid messages and messages with optional fields populated.
- New unknown fields arriving at an older consumer.
- Enums carrying new values.
- Old fields being absent/null under different default combinations.
- Timestamps in differing timezones/precisions allowed by the contract.
- Duplicate events, out-of-order events, or versions older than current consumer state.
- Missing schema IDs, schema validation failures, or producers sending the wrong content type.
- Unusually large payloads or disallowed sensitive data.

## 11. Replay, Retention, and New Consumers

A major advantage of event logs is replaying messages to rebuild projections or recover from consumer bugs. However, replay highlights compatibility challenges:

- New consumers may need to read events emitted years ago under legacy schemas.
- Fields may be missing, enums may contain retired values, and timestamps may follow older conventions.
- Historical events should not be mutated just to resemble a new schema, as that breaks historical immutability.
- Consumers need multi-version reading logic or a controlled upcasting/normalization step.

### 11.1. Upcasting and Normalization

An **upcaster** transforms older messages into the newer internal model before consumer processing. For instance, v1 has totalAmount and currency, while v2's internal model uses amountMinor and currency. The upcaster must encode exact conversion rules, be tested across all edge cases, and never alter the original event in the event store.

If safe conversion is impossible due to missing data, the consumer should route the message to quarantine or a reconciliation flow. Never invent a misleading business default just to dodge a parse error.

### 11.2. Retention Is Part of the Contract

Message retention and schema lifecycles must align:

| Question | Impact |
| --- | --- |
| How long are messages retained? | Consumers/replays must support legacy schemas for at least that span |
| Is there long-term archiving? | Must preserve schema IDs/contracts and access to older registry versions |
| Will replays span multiple consumer versions? | Must test upcasting/normalization and idempotency |
| Who is authorized to replay? | Replays can repeat side effects and require approval/auditing |
| Must personal data be deleted on request? | Immutable events and retention must align with privacy requirements; avoid storing excess data |

## 12. Security and Privacy in Event Contracts

Messages may be stored long-term and replicated across brokers, archives, DLQs, and multiple consumers. Consequently, adding a field to an event widens data exposure far more than returning it in a direct user-facing API response.

Design principles:

- **Data minimization:** emit only fields consumers require; prefer references over full copies.
- **Classification:** tag data sensitivity (public/internal/confidential or organizational taxonomy) in the contract/catalog.
- **Access control:** scope publish/consume permissions by domain, topic, subscription, and tenant where applicable.
- **Encryption:** protect data in transit and at rest, managing keys per compliance needs.
- **Auditing:** log who modifies schemas, publishes, reads/replays, or alters compatibility policies.
- **Retention/deletion:** define retention windows and mechanisms for fulfilling personal-data obligations.
- **Schema examples:** use synthetic data; never put real customer records into documentation or repositories.

### 12.1. Immutable Events and Data Deletion Requests

Event logs are commonly designed as immutable for history and auditability. When payloads contain personal data, erasure or processing-restriction requests create tension. Solutions must reflect legal obligations and concrete data architecture:

- Avoid embedding personal data directly in events when a reference suffices.
- Use revocable tokens/references or store sensitive data separately behind access controls.
- Establish retention and deletion/anonymization policies across event stores, archives, backups, and consumer projections.
- Document how obligations are handled once data has propagated to downstream systems.

Do not assume encryption alone satisfies all erasure or access-restriction requirements; evaluate replicas, keys, logs, and backups.

## 13. Catalog Management, Ownership, and Event Lifecycle

Beyond a schema registry, organizations should maintain an **event catalog** so developers can discover which events exist, who owns them, and how they may be used.

Minimal catalog record:

| Field | Purpose |
| --- | --- |
| Event type/name | Stable identifier |
| Domain/business meaning | Business semantics and emission trigger |
| Producer/owner | Accountable team |
| Consumer/subscribers | Consuming teams and use cases |
| Schema ID/version | Link to schema versions |
| Compatibility policy | Permitted change rules |
| Data classification | Sensitivity tier and permissions |
| Delivery/ordering semantics | At-least-once, partition keys, ordering scope if applicable |
| Retention/replay policy | Retention duration, archive, and replay rules |
| Lifecycle status | Draft, active, deprecated, retired |

### 13.1. Deprecation and Retirement

Retiring an event means more than deleting a schema. You must notify producers/consumers, set a retirement date, monitor live traffic, inspect backlogs and archives, provide a migration path, and designate who approves removing the topic/schema. Past events may still be replayed, so producer retirement does not immediately end historical compatibility obligations.

## 14. Example of a Complete Event Contract Design

**Event:** BookingConfirmed — emitted when a booking transitions to confirmed under Booking Service transaction rules.

### Business Specification

- Authoritative producer: Booking Service.
- Timing: after the booking confirmation transaction commits.
- One event represents one transition of a booking to confirmed.
- The event does not imply payment settlement if the payment contract only confirms authorization.
- Booking ID is stable; event ID is unique per emission; retries do not create new business events.
- Consumers may receive duplicate deliveries; they must deduplicate using event ID or business key.
- The event carries confirmed amount/currency, but never card details or payment secrets.

### Reference Payload

~~~json
{
  "eventId": "evt-7f21a9",
  "eventType": "com.example.booking.confirmed",
  "schemaVersion": 1,
  "occurredAt": "2026-12-18T08:29:58Z",
  "producer": "booking-service",
  "correlationId": "req-51bc",
  "aggregateId": "booking-42",
  "data": {
    "bookingId": "booking-42",
    "customerRef": "customer-18",
    "propertyId": "property-91",
    "currency": "VND",
    "totalAmountMinor": 125000000
  }
}
~~~

### Consumers and Permissions

| Consumer | Need | Data permissions |
| --- | --- | --- |
| Notification service | Send confirmation email/SMS | Read booking ID and minimal notification fields |
| Search indexer | Update displayed room status/availability | Receive only necessary fields; no customer contact details |
| Analytics | Compute booking/revenue metrics | Use references or classified fields; avoid unnecessary PII |
| Partner integration | Sync agreed booking states | Dedicated subscription, versioned contract, and partner-scoped permissions |

### Evolution Policy

1. Register, validate, and publish schema v1.
2. When adding promotionCode, introduce it as an optional field; verify backward/forward compatibility per consumer and registry policy.
3. Consumers needing the new field upgrade to handle missing values gracefully.
4. Producers emit promotionCode only after validating data rules and verifying target consumers are ready.
5. If total-amount semantics later change, do not reuse totalAmountMinor with a new meaning; create a new field/type/version and a migration plan.

## 15. Practice Lab: Evolving an Event Contract Without Disrupting Consumers

**Context:** Booking Service emits BookingConfirmed v1. Notification, Search Indexer, and Analytics rely on the current schema. The team wants to add promotionCode and replace totalAmount with an amount + currency structure, while preserving the ability to replay older events.

### Tasks

1. Write the event contract covering business meaning, emission conditions, owner, envelope, payload, data classification, ordering, and retention.
2. Choose JSON Schema, Avro, or Protocol Buffers; justify the choice based on languages, throughput, tooling, and consumer capabilities.
3. Register v1 and determine the compatibility mode needed for independent producer/consumer rollouts.
4. Classify each change as backward, forward, full, or breaking under the exact semantics of your chosen format and registry.
5. Design an expand–migrate–contract plan for promotionCode and amount/currency without silently changing old field semantics.
6. Write tests covering legacy consumers reading new fields, new consumers reading v1 messages, unknown enums, null/absent fields, and replayed messages.
7. Describe how to upcast historical records and handle events that cannot be safely converted.
8. Define producer/consumer permissions, log masking for sensitive data, replay procedures, and schema approvers.
9. Write a concise ADR documenting trade-offs in compatibility, registry cost, payload size, operations, and scalability.

### Completion Criteria

- Contract states clear business semantics, not just a list of field names.
- Envelope and payload cleanly separate metadata from business data.
- Schema validates cleanly and includes valid/invalid sample payloads.
- Compatibility policy is explained in terms of writer/reader direction and actual schema history.
- Breaking changes have versioning/migration plans; semantics are never altered silently.
- Legacy consumers, new consumers, replays, and unknown values all have tests.
- Permissions, sensitive data, retention, and ownership are documented.

## 16. Well-Architected Pre-Publication Checklist for Event Contracts

- [ ] Event describes a business fact that has occurred; producer and emission timing are defined.
- [ ] Contract has an owner, producer, consumers, purpose, examples, and lifecycle status.
- [ ] Envelope/payload, IDs, timestamps, correlation/causation, and schema version have clear semantics.
- [ ] Fields specify types, units, optionality/null/default rules, enums, and compatibility rules.
- [ ] Format/registry fits team capabilities and exact tool semantics have been verified.
- [ ] Compatibility is verified against legacy consumers and replayable historical messages.
- [ ] Semantic or unit changes are treated as breaking; types are never kept while silently changing meaning.
- [ ] Producers/consumers roll out in compatible order with observability and rollback plans.
- [ ] Tests cover schema validation, producer contracts, consumer contracts, integration, and replay.
- [ ] Events have business-appropriate idempotency/deduplication, ordering/partitioning, and delivery semantics.
- [ ] Sensitive data is minimized, classified, access-controlled, and retention-managed.
- [ ] Publish/consume/schema-change/replay permissions follow least privilege and are audited.
- [ ] Schemas, registries, catalogs, DLQs, and archives have owners, backup/DR, and error handling procedures.
- [ ] Costs of serialization, brokers, storage, data transfer, registry, and operations are evaluated.
- [ ] ADR documents trade-offs across reliability, security, performance, cost, and operations.

**Core takeaway:** a valid schema only tells you a message is structurally well-formed; an event contract also ensures all parties agree on **business meaning and how data evolves**. Only when producers, consumers, registries, rollouts, replays, and governance follow a verified compatibility workflow can an event-driven architecture scale independently without turning every field change into an outage or data-corruption risk.
