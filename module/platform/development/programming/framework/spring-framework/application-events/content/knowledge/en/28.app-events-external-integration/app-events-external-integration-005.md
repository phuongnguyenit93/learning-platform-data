# Event Contracts for External Systems in Spring Framework Application Events

## 1. Why is an internal domain event not yet an integration contract?

In a Spring application, `ApplicationEventPublisher.publishEvent(...)` and `@EventListener` help modules exchange **facts that happened** within an application context. However, an external system—such as Billing, Fulfillment, CRM, Analytics, or an external partner—cannot inherently receive and understand the Java object Spring just published.

For example, Ordering receives a successful payment confirmation and publishes:

```java
publisher.publishEvent(new PaymentCaptured(
        paymentId, orderId, amountMinor, currency));
```

This is an **illustrative snippet**, not a standalone program. The `PaymentCaptured` type may contain domain objects, internal enums, or constraints specific to Ordering. Sending this object directly over JSON/Kafka/RabbitMQ/HTTP webhooks and forcing every consumer to depend on the corresponding Java class allows internal refactors to accidentally break external systems.

An **event contract for external systems** is a **versioned promise** about an event’s meaning, structure, source of truth, delivery semantics, and processing rules. It lives at the integration boundary, independent of the producer’s code/domain model version.

A sufficiently good contract answers:

1. **What happened?** The event name and the condition under which the fact becomes true.
2. **Who is the authoritative source?** The producer/service or bounded context that owns the fact.
3. **How is an occurrence identified?** Event ID and uniqueness scope.
4. **What data is always present?** Required/optional fields, types, and units.
5. **Time, ordering, replays?** `occurredAt`, aggregate identity/version, ordering scope.
6. **How does the schema evolve?** Versioning, compatibility, deprecation.
7. **How should errors be handled?** Delivery, retries, duplicates, replays, acknowledgments, idempotency.
8. **Who is permitted to view it?** Access permissions, tenant boundaries, PII/secrets, retention.
9. **How is compatibility verified?** Schema validation, fixtures, contract tests.

> **Core principle:** a domain event expresses a fact in the internal model; an integration event expresses **the portion of that fact permitted to be published** under a stable contract for other systems. A change on one side should not automatically force the other side to deploy simultaneously.

## 2. Comparing domain events and integration events

| Aspect | Domain event in Spring | External integration event |
| --- | --- | --- |
| Goal | Notify facts across application/domain parts | Publish facts for independent consumers |
| Context | Bounded context and internal Java code | Contract understood by multiple teams/systems |
| Representation | Record/class/`ApplicationEvent`/POJO | JSON, Avro, Protobuf, CloudEvents, or agreed format |
| Mutability/Evolution | Can be refactored alongside the codebase | Requires compatibility and versioning policies |
| Delivery | Inside the application context by default | Over broker, outbox relay, webhook, event bus, etc. |
| Reliability | Not inherently durable using Spring core | Must explicitly define ack, retry, redelivery, replay |
| Security | In-process permissions and internal boundaries | Producer authentication, transport ACLs, tenant isolation |
| Payload | May reference domain types | Should use minimal, serializable, schema-backed data |
| Owner | Module/domain emitting the fact | Producer/contract owner and channel owner |

You do not necessarily need a one-to-one integration event for every domain event. Some domain events remain strictly internal, one domain event may be mapped into messages for multiple audiences, or a single integration milestone may be emitted only after multiple conditions complete.

### Example of translating language across bounded contexts

```text
Billing domain:
    PaymentCapturedDomain(paymentEntity, policyDetails)
                  |
                  | anti-corruption/translation layer
                  v
Public integration contract:
    payment.captured, schemaVersion=1
    data(paymentId, orderId, amountMinor, currency)
                  |
                  +--> Fulfillment consumer
                  +--> Finance projection
                  +--> Analytics
```

The translation layer publishes only meaningful and authorized data; it never serializes `paymentEntity` or repository objects directly. Billing can refactor its aggregate classes while keeping the `payment.captured/v1` contract intact.

## 3. A “fact that happened” must have a clear truth condition

An integration event is **not a disguised command**.

- `CapturePayment`: a request to *capture funds*; the operation may fail or be declined.
- `PaymentAuthorized`: the provider granted an authorization/hold per the agreement.
- `PaymentCaptured`: the funds have been captured successfully according to the authoritative verification source.
- `PaymentSettled`: funds have settled per accounting or provider rules; this may be a separate milestone from capture.
- `PaymentDeclined`: the provider declined the transaction; emit only if this is a recognized domain fact.

**Never** emit `PaymentCaptured` immediately upon sending a capture request. External consumers cannot tell that “captured” actually meant “capture is pending” if the producer does not state semantics clearly.

A contract table should include:

| Item | Example for `payment.captured` |
| --- | --- |
| Business definition | Payment provider confirmed capture succeeded |
| Trigger | Producer receives and verifies capture result; business state is durably persisted |
| Not triggered by | Request sent, authorization succeeded, timeout with unknown outcome |
| Source of truth | Billing/Payments, not Ordering inferring on its own |
| Multiplicity | Each valid capture transaction is one occurrence |
| Downstream meaning | Safe to update read models and trigger post-capture allowed workflows |
| Non-guarantees | Does not imply settlement, successful fulfillment, or that refunds cannot occur |

Only when domain experts and consumers agree on the **truth condition** does schema compatibility become meaningful. Two identical JSON structures whose meanings are “capture request accepted” vs. “funds captured” are not the same contract.

## 4. Designing the envelope and business data

An example **custom integration envelope**:

```json
{
  "eventId": "6f9b27d3-160b-4ff2-a0a8-b58c3ff0ec31",
  "eventType": "payment.captured",
  "schemaVersion": 1,
  "source": "/services/billing",
  "tenantId": "tenant-blue",
  "aggregateId": "O-100",
  "correlationId": "checkout-913",
  "occurredAt": "2026-11-11T02:00:00Z",
  "data": {
    "paymentId": "P-900",
    "orderId": "O-100",
    "amountMinor": 125000,
    "currency": "VND"
  }
}
```

This is a **custom format defined by the example**, not a JSON structure auto-generated or mandated by Spring Framework or CloudEvents. When choosing a format, the organization must document its fields, owners, stability guarantees, and serialization/deserialization mechanisms.

### 4.1. Metadata and data have distinct roles

| Field | Meaning | Rules |
| --- | --- | --- |
| `eventId` | ID of a single occurrence | **Preserved** across retries/redeliveries; never mint a new ID for the same fact |
| `eventType` | Type of published fact | Stable name; do not turn it into a command like `doPayment` |
| `schemaVersion` | Defined payload/envelope contract version | Not synonymous with app version or CloudEvents `specversion` |
| `source` | Source emitting the fact | Should be stable and clearly identified |
| `tenantId` | Tenant owning the data if tenant-scoped | Not proof that producer/consumer is authorized |
| `aggregateId` | Aggregate ID for correlation/ordering/partitioning | Not every event shares the same aggregate type |
| `correlationId` | Links a workflow/request | Multiple events may share the same correlation ID |
| `occurredAt` | Moment the domain confirmed the fact per contract | Distinct from `publishedAt` and `processedAt` |
| `data.paymentId` | Captured payment transaction/attempt | Must be stable within the domain |
| `data.amountMinor` | Value in smallest currency unit by convention | Do not use unchecked `double`s |
| `data.currency` | Currency code, e.g., ISO 4217 | Must define scale handling and rounding rules |

If an event is a **system-wide** fact belonging to no tenant, do not populate a dummy tenant just to pass a validator. Choose a different schema or explicit scope metadata.

### 4.2. Event ID vs. business ID

One order can emit multiple events: `OrderPlaced`, `PaymentCaptured`, `OrderCancelled`. Therefore `orderId` is **not** an event ID. One payment may also have separate captures and refunds; do not deduplicate all messages by `paymentId` when semantics differ.

If a consumer only guards against **redelivery**, the key is typically `(source,eventId)` or `(subscriberId,source,eventId)` per contract. If it must prevent **double charges/double fulfillment**, add a separate business-effect key per invariant.

### 4.3. Time and timezones

Use `Instant`/ISO-8601 UTC or an agreed timestamp format, such as `2026-11-11T02:00:00Z`. Do not conflate:

- `occurredAt`: when the business fact occurred.
- `committedAt`: when the DB transaction committed, if tracked.
- `publishedAt`: when the relay sent the message to transport.
- `receivedAt`: when the consumer received it.
- `processedAt`: when the consumer finished.

If the producer generates `occurredAt` before commit, document those semantics clearly; **do not** claim it is the commit timestamp.

## 5. Designing payloads that can evolve independently

A good contract does not depend on internal Java types. For example:

```java
// Internal domain model — free to change during refactoring.
record PaymentCapturedDomain(
        UUID eventId,
        String tenantId,
        String paymentId,
        String orderId,
        long amountMinor,
        String currency,
        Instant occurredAt,
        String correlationId) {}

// Public integration data — keep schema stable.
record PaymentCapturedV1(
        String paymentId,
        String orderId,
        long amountMinor,
        String currency) {}
```

These are **illustrative declarations**, requiring `UUID` and `Instant` imports. The full runnable example in section 11 includes all imports.

Notes:

1. **Only necessary data:** does the consumer need email, full name, shipping address, or raw payment gateway responses to know a capture succeeded? If not, omit them.
2. **Stable identifiers:** opaque IDs generally couple less to domain models than usernames, emails, or internal DB object graphs.
3. **No secrets:** access tokens, refresh tokens, credentials, webhook signing secrets, private keys, and session state must never enter events.
4. **Currency:** use integer minor units or decimal strings per explicit convention; never silently change `amountMinor` from dollars to cents.
5. **Null/optional:** do a missing field and `null` mean the same thing? Do not leave consumers guessing.
6. **Collections:** does element order matter? Can it be empty? What is the size limit?
7. **Enums:** what should consumers do when a producer adds an unknown value?
8. **Timestamps:** precision and timezone must be consistent.
9. **ID privacy:** `customerId`/`tenantId` may identify individuals/organizations; do not assume they are “anonymous”.

Define message size limits and schema validation before messages reach consumers. An event accidentally carrying a base64 file or a full entity graph can break brokers/consumers and create data exposure risks.

## 6. Contract schema: JSON Schema example

A simple schema using **JSON Schema Draft 2020-12** for the contract in section 4:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://example.invalid/schemas/payment-captured-v1.json",
  "title": "PaymentCapturedV1",
  "type": "object",
  "required": [
    "eventId",
    "eventType",
    "schemaVersion",
    "source",
    "tenantId",
    "aggregateId",
    "correlationId",
    "occurredAt",
    "data"
  ],
  "properties": {
    "eventId": { "type": "string", "format": "uuid" },
    "eventType": { "const": "payment.captured" },
    "schemaVersion": { "const": 1 },
    "source": { "type": "string", "minLength": 1 },
    "tenantId": { "type": "string", "minLength": 1 },
    "aggregateId": { "type": "string", "minLength": 1 },
    "correlationId": { "type": "string", "minLength": 1 },
    "occurredAt": { "type": "string", "format": "date-time" },
    "data": {
      "type": "object",
      "required": [
        "paymentId",
        "orderId",
        "amountMinor",
        "currency"
      ],
      "properties": {
        "paymentId": { "type": "string", "minLength": 1 },
        "orderId": { "type": "string", "minLength": 1 },
        "amountMinor": { "type": "integer", "minimum": 1 },
        "currency": { "type": "string", "pattern": "^[A-Z]{3}$" }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
```

The `example.invalid` address is a placeholder illustrating schema registry organization, **not an active schema URL**. In real deployments, replace it with an actively governed schema ID/URI.

**Notes on JSON Schema:**

- `format` keywords like `uuid` and `date-time` may only be annotations depending on validator/vocabulary settings; verify whether your validator enables format assertion. Do not assume every validator rejects malformed UUIDs.
- `additionalProperties:false` helps the producer enforce the exact V1 field set, **however** a consumer enforcing this schema too rigidly may reject a future optional field. If your policy allows additive evolution, consumers should apply tolerant-reader/compatibility validation or use explicit schema versions.
- JSON numbers do not inherently guarantee `long` precision across all languages. JavaScript `Number` cannot accurately represent all 64-bit integers; define value bounds or use decimal strings when needed.
- A `currency` field matching a regex may still not be a valid currency code; validate against an authoritative currency catalog/semantics.
- Schemas only check **shape**; they do not prove funds were actually captured, the actor is authorized, or the tenant is valid.

### Contract documentation needs more than a schema

A valid JSON Schema still does not tell you:

- Does `PaymentCaptured` mean provider capture succeeded or only provider accepted the request?
- Can a payment be captured multiple times / partially captured?
- What should the consumer do after a chargeback/refund?
- Is ordering guaranteed per `paymentId`/`orderId`?
- Does the producer emit only on commit success or upon receiving a response?
- Is the consumer allowed to call APIs back on Billing directly inside the listener?

Every event type needs a **semantic specification** alongside its technical schema.

## 7. CloudEvents: standardizing the envelope, not replacing the business contract

**CloudEvents 1.0** is a standard option for the event envelope. **Required** attributes are:

- `specversion`, e.g., `"1.0"`.
- `id`.
- `source`.
- `type`.

Attributes like `time`, `subject`, and `datacontenttype` are optional per specification; `data` holds the business payload when present.

Example **structured JSON CloudEvent**:

```json
{
  "specversion": "1.0",
  "id": "6f9b27d3-160b-4ff2-a0a8-b58c3ff0ec31",
  "source": "/services/billing",
  "type": "com.example.billing.payment.captured.v1",
  "subject": "payments/P-900",
  "time": "2026-11-11T02:00:00Z",
  "datacontenttype": "application/json",
  "tenantid": "tenant-blue",
  "correlationid": "checkout-913",
  "data": {
    "paymentId": "P-900",
    "orderId": "O-100",
    "amountMinor": 125000,
    "currency": "VND"
  }
}
```

This example uses application-chosen naming for the CloudEvents extension attributes `tenantid` and `correlationid`. CloudEvents **does not automatically define** the business meaning of these two extensions.

**Clearly distinguish two types of versions:**

- `specversion="1.0"`: version of the **CloudEvents specification**.
- `type="...captured.v1"` or a team-managed schema ID/version: version of the **business event contract**.

Do not set `specversion="2"` just because the team created `PaymentCapturedV2`. CloudEvents standardizes the envelope/transport layer; it does not automatically guarantee compatible payloads, ordering, retries, or authorization.

An application can use the custom envelope from section 4 **or** CloudEvents. Do not stitch half of a custom envelope with half of CloudEvents and claim specification compliance.

### When using Kafka, RabbitMQ, HTTP, or CloudEvents

| Choice | Contract items to define |
| --- | --- |
| Kafka/Pulsar | Topic name, key/partitioning, schema registry, consumer group, retry/DLQ, retention |
| RabbitMQ/AMQP | Exchange/routing key, queue bindings, publisher confirms, acknowledgments, dead-lettering |
| HTTP webhook | URL, authentication/signature, retry response codes, timeouts, replay protection, event ID |
| CloudEvents | `specversion/id/source/type` and appropriate transport binding |
| Custom JSON event bus | Corresponding envelope/schema/version/validation |
| Batch export | Watermarks, snapshot/replay semantics, event ordering, and idempotency |

No transport automatically turns an event into a durable contract. **A contract is a promise of semantics and handling**, while the transport is how the message is moved.

## 8. Version management and compatibility

A schema change must be evaluated against active consumers, not merely whether the new JSON “validates”.

| Change | Risk | How to handle |
| --- | --- | --- |
| Add optional field with default/consumer ignores unknown | Usually low if readers are tolerant | Test backward/forward compatibility |
| Add required field | Consumers/old messages may lack it | New contract or clear migration/default |
| Rename `paymentId` | Old consumers fail to read field | Temporary dual-read/dual-write or new version |
| Change `amountMinor` from number to string | Parse error or type mismatch | New version and migration |
| Change unit from minor to major | Wrong monetary amount even though schema stays `number` | **Dangerous semantic change**; separate contract/version |
| Change fact from “captured” to “authorized” | Consumers may fulfill prematurely | New event name/contract; do not reuse old name |
| Add enum value | Consumers with exhaustive switches may fail | Unknown fallback or new version |
| Remove field used by consumers | Downstream breaks | Deprecation and migration |
| Change how `eventId` is generated on retry | Deduplication breaks | Keep identity semantics stable |
| Change meaning of `tenantId` | Risk of data leaks/misrouting | Explicit migration, security review |

### Backward and forward compatibility

- **Backward compatible:** newer consumers/versions can read older messages under deployment rules.
- **Forward compatible:** older consumers can still read newer messages, e.g., ignoring new fields where permitted.
- **Full compatible:** satisfies both within the supported version/schema range.

Schema registries may further define modes for these terms. You must state **who reads whom** and maintain a testing matrix, rather than just slapping on a “compatible” label.

**Schema compatibility differs from semantic compatibility.** Changing the meaning of `isPaid` from “capture succeeded” to “authorization approved” might not alter the data type, yet it breaks consumers worse than renaming a field.

### Practical contract change workflow

1. Write an RFC/ADR covering semantics and the set of consumers.
2. Inventory actively produced/consumed versions and log usage.
3. Prefer truly compatible additive changes; add optional fields where appropriate.
4. Write producer schema tests and consumer contract tests for both old and new data.
5. Deploy consumers capable of reading both old and new formats before switching the producer.
6. For breaking changes, emit contract V2 alongside V1 during a migration window if architecture allows.
7. Monitor consumer acknowledgments and production usage; do not shut off V1 merely because producer code changed.
8. Retire V1 on an agreed timeline and conditions; document replay/backfill.
9. Retain historical schemas/decoders for messages that may be replayed.
10. Perform a security/PII review whenever a new schema adds fields.

Do not hardcode consumers to read “the first field” or specific producer package/class names. Rely on stable schemas and semantic contracts.

## 9. Contract ownership, discoverability, and integration documentation

Every public event type should carry governance metadata:

```text
Event:          payment.captured
Owner:          Payments/Billing team
Version:        v1
Source:         /services/billing
Audience:       Fulfillment, Finance, Analytics
Truth condition: provider confirmed capture
Transport:      billing.events topic (illustrative)
Key:            paymentId (illustrative)
Retention:      per agreed policy
PII class:      internal, no raw card credentials
Duplicate:      possible; dedupe by source+eventId
Ordering:       only per configured partition/key, if guaranteed
Support:        on-call team and escalation policy
Deprecation:    documented migration window
Schema:         registry URI/version
```

The values above are an **illustrative contract template**, not the topic name, retention, or SLA of a specific system.

Documentation should include:

- At least one **valid** example message.
- Examples of optional fields and absent values.
- At least one **negative example** (e.g., a pending payment does **not** emit captured).
- Links to schema, owner, changelog, topic/queue, and ACL/credentials workflow.
- Event identity, timestamps, key ordering, TTL/replay, and retry/DLQ.
- Error classifications and which side effects consumers are/aren’t allowed to perform.
- Data sensitivity rules and dev/staging/prod operational guidance.
- Expected frequency/volume, payload size limits, and SLA/latency if applicable.

An API portal, AsyncAPI document, or schema registry aids discoverability, but **must be enforced by code review and CI** to avoid drift between specs and producers.

## 10. Reliability: local publish does not equal remote delivery

Spring core’s `ApplicationEventPublisher` is not a broker. By default, listeners run synchronously inside the context and publications are not durably stored. If calling a webhook directly inside a transaction:

```java
@Transactional
public void markPaymentCaptured(...) {
    repository.markPaid(...);
    publisher.publishEvent(new PaymentCapturedDomain(...));
}
```

Suppose the internal listener executes `httpClient.post(...)` to another system. Failure windows exist:

- The request reaches the other system **before commit**, and then the local transaction rolls back → the outside system acted on a fact that never durably existed.
- DB commit succeeds, but the process crashes **before sending** → the external system never receives it.
- Remote finishes processing, but the response times out → producer does not know it succeeded and retries can cause duplicates.
- Listener throws an exception → transaction outcome depends on sync/async, exception handling, and transaction manager.
- Target API is temporarily down → application requests block for a long time if coupled synchronously.

Therefore, for events requiring reliable emission, teams typically choose a **transactional outbox** or a framework/registry with verified equivalent guarantees.

### 10.1. Transactional outbox: same transaction as the state change

```text
Billing service
   |
   +-- BEGIN DB transaction
   |     |
   |     +-- UPDATE payment_orders SET state='PAID'
   |     |
   |     +-- INSERT outbox(eventId, contract JSON, PENDING)
   |
   +-- COMMIT
         |
         v
   Outbox relay (polling or transaction log tailing)
         |
         +-- publish to broker/webhook
         +-- observe appropriate ACK
         +-- mark outbox SENT
         |
         v
   Consumer receives integration event
         |
         +-- validate source/schema/authorization
         +-- dedupe event
         +-- apply side effect safely
```

In this model, the **DB update and outbox insert** must succeed or roll back together. The relay runs after commit and can retry unacknowledged messages.

An outbox **does not guarantee each message is emitted only once**. The relay can publish successfully and crash before marking `SENT`, causing a resend upon restart. Thus consumer idempotency remains mandatory for critical side effects.

### 10.2. Why is AFTER_COMMIT insufficient for atomic outbox inserts?

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` enables callbacks to execute after a successful commit. However, if the application **only begins INSERTing into the outbox inside the post-commit callback**, the outbox insert is no longer in the same transaction that updated business state. A crash between commit and callback can lose the event.

**In the section 11 example, the outbox adapter uses a synchronous `@EventListener`** to insert into the outbox **inside the currently open transaction**. This is an intentional design choice and does not imply that all side effects should happen before commit.

If using Spring Modulith’s Event Publication Registry or externalization, understand the exact **version and transaction/retry semantics** of those modules rather than assuming `@TransactionalEventListener` equals an outbox.

## 11. Runnable example: domain event → integration contract V1 → transactional outbox

This project uses:

- Java **17+** and Maven.
- Spring Framework **6.2.12** (`spring-context`, `spring-jdbc`).
- In-memory H2 **2.3.232**.
- Jackson Databind **2.17.2** to serialize records into JSON.

**Illustrative goal:** a payment capture verified by an authoritative source updates state in the local database; in the same transaction, an event adapter converts the domain event into **contract V1** and writes JSON into the outbox. A repeat confirmation for the same order is blocked by the demo’s simple invariant.

**Explicit limitations:** the demo does not integrate with a real payment provider, does not publish to Kafka/RabbitMQ, has no relay, and has no HTTP authentication or schema registry. It demonstrates only the **atomic write portion of the outbox** and how to decouple domain types from public contracts.

### 11.1. Directory structure

```text
integration-event-contract/
├── pom.xml
└── src/main/java/demo/IntegrationContractDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>integration-event-contract</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <version>2.17.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.IntegrationContractDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/IntegrationContractDemo.java`:

```java
package demo;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

import javax.sql.DataSource;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public final class IntegrationContractDemo {

    // Internal event belonging to the Payments domain.
    public record PaymentCapturedDomain(
            UUID eventId,
            String tenantId,
            String orderId,
            String paymentId,
            long amountMinor,
            String currency,
            Instant occurredAt,
            String correlationId) {
    }

    // Data portion belonging to public contract V1.
    public record PaymentCapturedV1(
            String paymentId,
            String orderId,
            long amountMinor,
            String currency) {
    }

    // Custom envelope (NOT CloudEvents).
    public record IntegrationEventV1(
            String eventId,
            String eventType,
            int schemaVersion,
            String source,
            String tenantId,
            String aggregateId,
            String correlationId,
            String occurredAt,
            PaymentCapturedV1 data) {
    }

    // Not final: @Transactional requires method proxying.
    public static class PaymentService {
        private final JdbcTemplate jdbc;
        private final ApplicationEventPublisher publisher;

        public PaymentService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            this.jdbc = jdbc;
            this.publisher = publisher;
        }

        @Transactional
        public void recordCapturedPayment(
                String tenantId,
                String orderId,
                String paymentId,
                long amountMinor,
                String currency,
                String correlationId) {

            Objects.requireNonNull(tenantId, "tenantId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(paymentId, "paymentId");
            Objects.requireNonNull(currency, "currency");
            Objects.requireNonNull(correlationId, "correlationId");

            if (amountMinor <= 0) {
                throw new IllegalArgumentException("amount must be positive");
            }

            int changed = jdbc.update(
                    "UPDATE payment_orders SET state = 'PAID' "
                    + "WHERE order_id = ? AND tenant_id = ? "
                    + "AND state = 'UNPAID'",
                    orderId, tenantId);

            if (changed != 1) {
                throw new IllegalStateException(
                        "not eligible for capture confirmation");
            }

            // In the demo, only call after provider verification.
            publisher.publishEvent(new PaymentCapturedDomain(
                    UUID.randomUUID(),
                    tenantId,
                    orderId,
                    paymentId,
                    amountMinor,
                    currency,
                    Instant.now(),
                    correlationId));
        }
    }

    public static class OutboxAdapter {
        private final JdbcTemplate jdbc;
        private final ObjectMapper mapper;

        public OutboxAdapter(JdbcTemplate jdbc, ObjectMapper mapper) {
            this.jdbc = jdbc;
            this.mapper = mapper;
        }

        @EventListener
        public void on(PaymentCapturedDomain domain) {
            PaymentCapturedV1 data = new PaymentCapturedV1(
                    domain.paymentId(),
                    domain.orderId(),
                    domain.amountMinor(),
                    domain.currency());

            IntegrationEventV1 contract = new IntegrationEventV1(
                    domain.eventId().toString(),
                    "payment.captured",
                    1,
                    "/services/billing",
                    domain.tenantId(),
                    domain.orderId(),
                    domain.correlationId(),
                    domain.occurredAt().toString(),
                    data);

            final String json;
            try {
                json = mapper.writeValueAsString(contract);
            } catch (JsonProcessingException ex) {
                throw new IllegalStateException(
                        "Unable to serialize contract", ex);
            }

            // Synchronous @EventListener, inside the source transaction.
            jdbc.update(
                    "INSERT INTO outbox "
                    + "(event_id, event_type, schema_version, "
                    + "tenant_id, payload_json, dispatch_state) "
                    + "VALUES (?, ?, ?, ?, ?, ?)",
                    contract.eventId(),
                    contract.eventType(),
                    contract.schemaVersion(),
                    contract.tenantId(),
                    json,
                    "PENDING");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:integration_contract;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new DataSourceTransactionManager(ds);
        }

        @Bean
        ObjectMapper objectMapper() {
            return new ObjectMapper();
        }

        @Bean
        PaymentService paymentService(
                JdbcTemplate jdbc,
                ApplicationEventPublisher publisher) {
            return new PaymentService(jdbc, publisher);
        }

        @Bean
        OutboxAdapter outboxAdapter(
                JdbcTemplate jdbc,
                ObjectMapper mapper) {
            return new OutboxAdapter(jdbc, mapper);
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            ObjectMapper mapper = context.getBean(ObjectMapper.class);

            jdbc.execute(
                    "CREATE TABLE payment_orders ("
                    + "order_id VARCHAR(40) PRIMARY KEY, "
                    + "tenant_id VARCHAR(40) NOT NULL, "
                    + "state VARCHAR(20) NOT NULL)");

            jdbc.execute(
                    "CREATE TABLE outbox ("
                    + "event_id VARCHAR(36) PRIMARY KEY, "
                    + "event_type VARCHAR(80) NOT NULL, "
                    + "schema_version INT NOT NULL, "
                    + "tenant_id VARCHAR(40) NOT NULL, "
                    + "payload_json CLOB NOT NULL, "
                    + "dispatch_state VARCHAR(20) NOT NULL)");

            jdbc.update(
                    "INSERT INTO payment_orders "
                    + "(order_id, tenant_id, state) VALUES (?, ?, ?)",
                    "O-100", "tenant-blue", "UNPAID");

            PaymentService service =
                    context.getBean(PaymentService.class);

            service.recordCapturedPayment(
                    "tenant-blue", "O-100", "P-900",
                    125000L, "VND", "checkout-913");

            // A repeat confirmation for the same order creates no new event.
            boolean secondAttemptBlocked = false;
            try {
                service.recordCapturedPayment(
                        "tenant-blue", "O-100", "P-900",
                        125000L, "VND", "checkout-913");
            } catch (IllegalStateException expected) {
                secondAttemptBlocked = true;
            }

            String state = jdbc.queryForObject(
                    "SELECT state FROM payment_orders "
                    + "WHERE order_id = ?",
                    String.class, "O-100");

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM outbox",
                    Integer.class);

            String json = jdbc.queryForObject(
                    "SELECT payload_json FROM outbox",
                    String.class);

            JsonNode contract = mapper.readTree(json);

            System.out.println("ORDER_STATE=" + state);
            System.out.println("OUTBOX_ROWS=" + count);
            System.out.println(
                    "EVENT_TYPE=" + contract.path("eventType").asText());
            System.out.println(
                    "SCHEMA_VERSION="
                    + contract.path("schemaVersion").asInt());
            System.out.println(
                    "TENANT=" + contract.path("tenantId").asText());
            System.out.println(
                    "PAYMENT="
                    + contract.path("data").path("paymentId").asText());
            System.out.println(
                    "AMOUNT_MINOR="
                    + contract.path("data").path("amountMinor").asLong());
            System.out.println(
                    "SECOND_ATTEMPT_BLOCKED=" + secondAttemptBlocked);
        }
    }
}
```

Run from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

Lines printed by the program (excluding environment-dependent startup logs):

```text
ORDER_STATE=PAID
OUTBOX_ROWS=1
EVENT_TYPE=payment.captured
SCHEMA_VERSION=1
TENANT=tenant-blue
PAYMENT=P-900
AMOUNT_MINOR=125000
SECOND_ATTEMPT_BLOCKED=true
```

### 11.2. Why is the outbox record consistent with business state?

1. `AnnotationConfigApplicationContext` creates the beans; `@EnableTransactionManagement` activates the transaction proxy for `PaymentService`.
2. `recordCapturedPayment(...)` is invoked **through the Spring bean**, not via self-invocation. The transaction manager opens a local JDBC transaction on the `DataSource`.
3. `UPDATE payment_orders` only transitions state from `UNPAID` to `PAID` when tenant/order match. If no matching row exists, the method throws an exception and publishes no event.
4. When the update succeeds, the service constructs `PaymentCapturedDomain` and calls Spring `publishEvent(...)`. `SimpleApplicationEventMulticaster` by default invokes `@EventListener` synchronously on the same thread.
5. `OutboxAdapter.on(...)` maps the domain payload to `IntegrationEventV1` and INSERTs JSON into the outbox table **inside the service’s currently open transaction**.
6. If the INSERT fails or the serializer throws a runtime exception, the service transaction rolls back the update as well. If the transaction commits, business state and outbox row appear together.
7. A repeat call for an already-`PAID` order fails to match the update condition and therefore emits no additional fact. This is a **demo rule**: one order confirms only one capture. Domains with partial/multiple captures need different invariants/keys.
8. The test reads back from H2 and prints fields of the JSON contract. Runtime UUIDs and timestamps are omitted so stdout stays deterministic.

**What the demo does not include:** sending messages to a broker, ACK confirmation, retries, DLQ, consumer-side duplicate handling, CI schema validation, and security authentication. These pieces must be added in real systems as described in the following sections.

### 11.3. Why not use @TransactionalEventListener(AFTER_COMMIT) here?

The goal is an **atomic outbox insert** within the transaction that mutated `payment_orders`. Changing `@EventListener` to a listener that runs only `AFTER_COMMIT` and then inserts into the outbox means you can no longer claim both the `UPDATE` and `INSERT` occurred in **the same transaction**.

If you want an adapter to write to the outbox on another thread, you must also re-evaluate transaction context: a JDBC transaction’s `ThreadLocal` does not automatically cross an executor boundary. An async listener is **unsuitable** when same-transaction outbox writing is required in this pattern.

## 12. Relaying to a broker and idempotent consumers

Once the outbox has `PENDING` rows, a separate worker/relay needs to read, send, confirm, and mark complete. Pseudocode:

```text
repeat:
  rows = claimPendingOutboxRows(limit, lease)
  for row in rows:
      try:
          broker.publish(
              topic="billing.events",
              key=row.aggregateIdOrPaymentId,
              payload=row.payloadJson,
              eventId=row.eventId
          )
          waitForBrokerAcknowledgement()
          markOutboxSent(row.eventId)
      catch retryableError:
          recordAttemptAndBackoff(row.eventId)
      catch terminalError:
          quarantineOrDeadLetter(row.eventId)
```

This is an **illustrative algorithm**, not an API built into Spring core. Production requires handling contention across multiple relay workers, leases/locking, retry policies, timeouts, and shutdown recovery.

**Critical duplicate window:**

```text
Outbox row E-1 committed
  |
  v
Relay publishes E-1 -> broker ACK
  |
  +-- PROCESS CRASH before marking SENT
         |
         v
Relay restarts -> republishes E-1
         |
         v
Consumer may receive E-1 a second time
```

Therefore, the consumer must be idempotent. Example SQL table:

```sql
CREATE TABLE processed_messages (
    subscriber_id VARCHAR(80) NOT NULL,
    source VARCHAR(100) NOT NULL,
    event_id VARCHAR(80) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (subscriber_id, source, event_id)
);
```

Inside the consumer’s transaction:

1. Verify source, tenant, and schema.
2. Insert the processed marker using the unique constraint.
3. On a duplicate key matching the constraint, skip the already-committed side effect.
4. If the insert succeeds, perform the consumer DB updates **within the same transaction**.
5. Commit marker and effect; then ACK per transport semantics.
6. On rollback, the marker must also roll back so retries get a chance to process.

Do not rely solely on an in-memory `Set<UUID>` for durable idempotency across multiple replicas. For side effects on external payment/email/shipping APIs, a local DB transaction is not atomic with the external service; use stable idempotency keys at the target, reconciliation, or appropriate orchestration.

### Event-level dedupe vs. business-level dedupe

Two deliveries with the same `eventId` are one occurrence delivered twice. Two different event IDs can still cause a duplicate business effect (for example, the same order creating two invalid fulfillments). You may therefore need **two keys**:

- `(subscriberId,source,eventId)`: guards against redelivery of a single event.
- `fulfillment:orderId` or a business key per specific invariant: guards against creating two unintended effects.

Do not use `correlationId` as an event dedupe key: one checkout flow typically emits multiple events with the same correlation.

## 13. Ordering and replay: no default global order

Consumers must not assume every event across every service arrives in wall-clock order. Factors affecting order include:

- Multiple producers, threads, or instances.
- Broker partitioning and keys.
- Retries/dead-lettering/redrives.
- Outbox relays running concurrently.
- Consumer group concurrency.
- Network and clock skew.

If a state projection requires ordering for **one aggregate**, you can add `aggregateVersion`/sequence and route events for the same aggregate to the same partition/key when transport supports it. Example:

```text
Order O-100:
  PaymentAuthorized  aggregateVersion=3
  PaymentCaptured    aggregateVersion=4
  PaymentRefunded    aggregateVersion=5
```

The version must be generated by the authoritative store under the same transaction rules; do not use an arbitrary timestamp as a sequence. Consumers can reject stale versions or wait on gaps per policy. Do not infer from `aggregateVersion` that a broker always preserves order if keys or consumer concurrency are misconfigured.

### Replay contracts must be explicit

Replaying historical events may be used to rebuild projections, bootstrap new consumers, or investigate incidents. When replaying:

- Preserve the identity/provenance of the original occurrence.
- Ensure consumers know they are replaying or enforce idempotent policies.
- Avoid re-invoking disallowed external payment APIs, sending emails, or triggering shipment side effects.
- Retain old schemas/decoders throughout the retention/replay window.
- Distinguish `occurredAt` from replay time.
- Do not mint a new `eventId` just because you are re-forwarding the same fact.

## 14. Security when emitting events to external systems

An event contract is a data boundary. External systems may have different permissions, lifecycles, and storage than the producer. Key controls:

**Producer authentication and transport security.** Brokers use ACLs/service identities, TLS connections, and topic access controls. HTTP webhooks must verify endpoints, signatures/MACs, or appropriate authentication mechanisms. Never trust a `source` field inside JSON as proof of the genuine producer.

**Tenant isolation.** `tenantId` must be derived from an authorized business source. The receiving side must never let an event pick a tenant datasource/index solely from an unverified string. Define which consumers are permitted to receive which tenants.

**PII minimization.** Do not send raw customer profiles, tokens, cookies, card PANs, passwords, or internal security contexts unless explicitly approved in the contract and specifically protected. Event payloads and outboxes are **data storage locations**, not merely transient pipes.

**Retention and erasure.** Brokers, outboxes, DLQs, replay storage, logs, and backups have different retention windows. Apply legal/contractual policies per data classification; do not retain PII indefinitely just for replay convenience.

**Logging/tracing.** Use safe `eventId`, `eventType`, outcome, and correlation IDs; do not dump raw JSON. Even an opaque actor/tenant ID can link back to a person/organization. Do not put event IDs or customer IDs into high-cardinality metric labels.

**Webhook security.** Verify signatures over raw request bytes per protocol, bound replay windows using timestamps/nonces if specified, and deduplicate events. Each retry of the same occurrence must preserve identity per contract. Never put signing secret keys inside the payload.

**Validation and resource limits.** Check schema, size, UTF-8 validity, nesting depth, required fields, message authentication, and rate limits. A schema-valid payload may still contain an invalid amount or an unauthorized tenant.

### Do not “borrow” a historical actor’s permissions

An event recording `actor=user-42` only describes who performed the fact at the producer. A consumer running later may not be authorized to act on behalf of `user-42`, especially if permissions were revoked. Consumers need their own authorization/trust policies; event metadata is not an access token.

## 15. Contract testing between producer and consumer

**Producer contract tests** verify that what the producer actually emits matches the published schema/semantics.

**Consumer contract tests** verify that the consumer parses and reacts properly to supported examples/contracts, including optional fields and failure paths.

A practical matrix:

| Scenario | What to assert |
| --- | --- |
| Valid capture | Event type, version, source, ID, tenant, and capture data match |
| Capture request still pending | `payment.captured` is **not** emitted |
| Transaction rollback | No committed outbox row exists |
| Outbox serialization error | Business state rolls back along with the outbox write |
| Optional field added | Older consumer still reads per compatibility policy |
| Missing required field | Producer validator/test fails; consumer rejects/quarantines |
| Unknown enum value | Consumer applies fallback or rejects cleanly |
| Amount unit changed | Semantic test fails, not only schema type check |
| Duplicate `eventId` (redelivery) | Consumer effect executes only once |
| Two events sharing correlation | Not falsely deduplicated |
| Unauthorized tenant | Consumer does not access another tenant’s data |
| Spoofed source message | Rejected before tenant routing |
| Out-of-order aggregate version | Newer state is not overwritten by stale event |
| Poison event/invalid JSON | Retry/DLQ policy applies, no infinite retry |
| Relay crashes right after publish | Message resent with the same `eventId` |
| Schema V1 replayed after V2 deploy | Decoder/consumer still understands per support matrix |
| Provider capture succeeds but webhook times out | Producer reconciles/preserves idempotency and emits fact once |
| Audit/logging | No tokens/PII leaked in errors or traces |

### 15.1. Unit testing the mapper independently

When the mapping adapter is a pure function, verifying fields without a broker is straightforward:

```java
// Illustrative JUnit snippet, not part of the section 11 Maven project.
PaymentCapturedV1 data =
        new PaymentCapturedV1("P-900", "O-100", 125000L, "VND");

assertEquals("P-900", data.paymentId());
assertEquals(125000L, data.amountMinor());
assertEquals("VND", data.currency());
```

This snippet requires JUnit Jupiter assertions and the declared record types. Better yet, test that the mapper **does not** copy unpublished sensitive fields from the domain event.

### 15.2. Contract fixtures and golden JSON

Store V1 JSON samples in test resources in real projects (recommended here as a practice), then:

- Parse using the exact consumer deserializer.
- Validate against the exact schema version.
- Assert field semantics.
- Test backward/forward compatibility across supported versions.
- Check canonical encoding when signatures are used.
- Ensure unknown properties are handled per policy.
- Do not compare raw JSON strings if field order is not part of the contract.

When signing webhook JSON, signatures typically depend on **raw bytes** per protocol rules; do not deserialize and re-serialize and expect the signature to remain valid.

### 15.3. Integration testing DB transactions and the outbox

For the section 11 example, worthwhile assertions include:

```java
// JUnit pseudocode with context/jdbc/service set up.
service.recordCapturedPayment(...);
assertEquals("PAID", stateFromDatabase);
assertEquals(1L, countOutboxRows);
assertEquals("payment.captured", parsedEventType);
assertEquals(1, parsedSchemaVersion);
```

This is **pseudocode**, not standalone runnable Java; variables must be defined in the test. Another critical test intentionally triggers an outbox insert error (such as a unique violation) and asserts state rolls back to `UNPAID` after the transaction. Test with the exact transaction manager/DB driver used in production if you want conclusions about concurrency, locking, or isolation behavior.

### 15.4. Consumer-driven contract testing

When a producer serves multiple consumers, consumer-driven contract tests can collect valid consumer expectations. However, consumers do not unilaterally dictate the producer’s truth conditions. The contract owner must maintain semantics and migration phases; JSON shape-checking tools do not replace business agreements.

## 16. Monitoring and operating the contract

Metrics to have:

- Outbox pending rows and oldest record age.
- Relay publish, retry, failure, and DLQ counts.
- Producer events by `eventType`/version.
- Consumer accepted/processed/duplicate/rejected counts by `eventType`/version.
- Schema validation errors and unknown contract versions.
- Consumer lag, processing latency, and backlog.
- Share of consumers still on V1 vs. V2 before deprecation.

Do not use each `eventId` or `customerId` as a metric tag. IDs have very high cardinality; use standardized labels and store details in controlled logs/traces.

A safe log example:

```text
component=billing-outbox
eventType=payment.captured
schemaVersion=1
outcome=RETRY_SCHEDULED
errorCode=BROKER_UNAVAILABLE
```

Fields can be extended with opaque `eventId`/correlation IDs if policy permits. Do not dump entire payment payloads when the broker is temporarily unavailable.

### Recovery runbook when a consumer cannot read V2

1. Confirm event type/schema ID/version and a sanitized sample.
2. Identify which consumer is failing, from which deployment, which message, and which schema registry mode.
3. Classify: parse/type mismatch, missing field, semantic change, or authentication/tenant rejection.
4. Temporarily quarantine/apply bounded retries; avoid infinite loops or silent drops.
5. For breaking changes, restore V1 or enable dual-publish/adapter per an approved plan.
6. Check which side effects already occurred to avoid duplicates during replay.
7. Write a regression contract test before rolling out again.
8. Update owner/changelog/support matrix and deprecation milestones.

## 17. Anti-patterns to avoid

1. **Sending raw JPA entities over a broker.** Couples consumers to lazy fields, internal models, and excess data.
2. **Reusing producer Java classes as the mandatory public contract.** Couples deployments across service packages.
3. **Giving events technical names like `EntityUpdated` and expecting consumers to infer business facts.** Unstable semantics.
4. **Emitting `PaymentCaptured` as soon as the capture command is sent.** States an untrue fact.
5. **Putting access tokens/credentials inside payloads for consumers to reuse.** Leaks secrets and violates trust boundaries.
6. **Lacking a stable `eventId` or generating a new UUID on every retry.** Deduplication fails.
7. **Changing field meanings without changing the contract.** Causes business bugs even when JSON still parses.
8. **Validating only JSON Schema while ignoring truth conditions.** Producers emitting false facts still pass validation.
9. **Using CloudEvents `specversion` as the business schema version.** Mixes two unrelated standards.
10. **Forcing all consumers to upgrade simultaneously.** Destroys independent deployment.
11. **Adding a required field to V1 and calling it additive.** Older consumers and historical messages can break.
12. **Using a strict unknown-field parser while promising forward compatibility.** Promise and implementation contradict each other.
13. **No schema owner, changelog, or fixtures.** Consumers guess fields from log samples.
14. **Assuming `@EventListener` sends to Kafka/HTTP on its own.** Spring core only dispatches internally.
15. **Calling webhooks directly inside a DB transaction.** Opens a window for external side effects before commit.
16. **Placing the outbox `INSERT` only in an `AFTER_COMMIT` callback and believing it is atomic with business state.** Wrong transaction boundary.
17. **Believing a transactional outbox gives end-to-end exactly-once.** The relay can still resend.
18. **Using `correlationId` as a deduplication key.** One workflow typically emits multiple facts.
19. **Assuming global broker ordering.** Depends on keys/partitions/retries/concurrency.
20. **Not securing DLQ/replay storage.** Sensitive payloads get retained across extra places outside policy.
21. **Replaying old events and calling payment APIs again.** Side effects need idempotency/business policies.
22. **Logging raw event JSON on deserialization failure.** Leaks data right on the error path.
23. **Skipping event validation at the consumer.** A JSON payload containing a tenant ID does not prove trustworthiness.
24. **No limits on size/depth/retention.** One oversized message can stall the system.
25. **Not supporting old schemas during replay.** Upgrading versions breaks newer consumers reading historical data.
26. **Switching public formats with no migration window.** Running consumers break abruptly.

## 18. Design checklist before publishing an event

### Semantics

- [ ] Does the event express a **fact that happened**, rather than an unexecuted command?
- [ ] Are truth conditions, owner, and confirmation timing documented?
- [ ] Is captured clearly distinguished from authorized/settled/refunded?
- [ ] Are multiplicity and business identity clear?

### Contract

- [ ] Does the public envelope include necessary event ID, source, type, and version?
- [ ] Do the schema/payload define required/optional fields, units, and constraints?
- [ ] Are domain entities/runtime objects/secrets excluded?
- [ ] Is `eventId` stable when resending an occurrence?
- [ ] Do correlation, tenant, aggregate ID, and `occurredAt` have consistent semantics?
- [ ] If using CloudEvents, does `specversion` track the specification while schema version is separate?

### Reliability

- [ ] Are state and outbox written atomically, or backed by a verified alternative guarantee?
- [ ] Does the relay handle ACKs, retries/backoff, concurrency control, and failure monitoring?
- [ ] Is the consumer idempotent on redelivery and equipped with business-effect keys where needed?
- [ ] Are ordering scope and out-of-order handling defined?
- [ ] Do replay/retention/DLQ paths avoid re-triggering dangerous side effects?

### Governance and security

- [ ] Is there an owner, schema registry/AsyncAPI, or CI-maintained documentation?
- [ ] Are compatibility policies, changelogs, migrations, and deprecation windows clear?
- [ ] Are producer identity, broker/webhook auth, and tenant isolation verified?
- [ ] Do PII/retention/encryption/access logging meet applicable policies?
- [ ] Are there contract tests on producer, consumer, transaction/outbox, and backward compatibility?

**Conclusion:** When a Spring domain event needs to reach external systems, do not export raw Java objects or merely “add a topic”. Build an **independent integration event contract** that accurately describes a fact that occurred, with a versioned schema, meaningful metadata, and minimal payload. Write business state and the outbox in the same transaction when reliable publication is required, while consumers verify sources, handle duplicates/replays, and maintain schema compatibility per agreement. Good contracts let each system evolve independently while still understanding **the exact same business fact**.

## References

- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Modulith — Working with Application Events](https://docs.spring.io/spring-modulith/reference/events.html)
- [CloudEvents Specification 1.0](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
- [JSON Schema — Draft 2020-12](https://json-schema.org/draft/2020-12)
- [AsyncAPI — Specification](https://www.asyncapi.com/docs/reference/specification/latest)
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
- [Idempotent Consumer Pattern](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
