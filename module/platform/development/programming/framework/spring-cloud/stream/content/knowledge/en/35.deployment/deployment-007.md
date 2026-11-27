# Contract Compatibility When Deploying Producers and Consumers Out of Sync

In an event-driven system, producers and consumers are often deployed at different times. A new consumer version may already be running while the producer still emits the old schema; later, the new producer starts emitting the new schema while some old consumer instances are still active. If payload changes are not designed for this overlap period, messages can fail deserialization, land in retry/DLQ queues, or corrupt business processing.

Contract compatibility is the ability of different producer and consumer versions to continue exchanging messages accurately across deployment, rollback, and replay lifecycles. What must be verified are the actual writer/reader schema pair, serializers/deserializers, content types, headers, and the business semantics of each field. Having a schema accepted by a registry is not enough to prove the application processes it properly.

This lesson explains how to choose compatibility modes, apply expand-contract, deploy consumers and producers in the right order, use Schema Registry in Spring Cloud Stream, test version pairs, and handle breaking changes through topic migration.

## Learning Objectives

After this lesson, you can:

- Explain why producers and consumers can run multiple versions simultaneously.
- Distinguish wire contracts, Java DTOs, content types, and schema registries.
- Understand backward, forward, full, and transitive compatibility.
- Choose consumer/producer deployment ordering according to compatibility mode.
- Apply expand-contract when adding, changing, and removing fields.
- Design evolvable Avro, JSON, and Protobuf schemas.
- Use the Spring Cloud Stream Schema Registry and Avro message converter.
- Distinguish a schema registry from broker-native schemas.
- Test producers/consumers using a version matrix and historical data.
- Plan rolling deployments, rollbacks, replays, and migrations for breaking changes.

## 1. Why Do Producers and Consumers Diverge in Version?

Spring Cloud Stream standardizes the programming model around `Supplier`, `Function`, `Consumer`, and bindings. The binder moves messages between the application and the broker. However, the binder does not automatically make payloads compatible across every application version.

Suppose an `orders` producer emits `OrderCreated` events and a `billing` consumer reads them. During an upgrade, the following may coexist:

- Producer v1 and producer v2.
- Consumer v1 and consumer v2.
- Messages written at different times with different schema versions.
- Old messages still sitting in retention, backlogs, or DLQs.
- New consumers replaying historical data after deployment.
- Consumers rolled back to an older version while the producer has already emitted new data.

~~~mermaid
flowchart TD
    P1["Producer v1"] -->|Schema v1| B["Broker topic / queue"]
    P2["Producer v2"] -->|Schema v2| B
    B --> G["Consumer group<br/>one message to one member"]
    G --> C1["Instance v1"]
    G --> C2["Instance v2"]
    C1 --> D["Database / downstream"]
    C2 --> D
    B --> R["Replay / DLQ recovery"]
    R --> C1
    R --> C2
~~~

Within the same consumer group, v1 and v2 instances normally share incoming messages. The broker does not route messages based on schema version. During a rolling update, a message can land on any active member in the group. Therefore, every live instance must be able to read messages emitted by current producers.

If two consumer groups differ, each group receives an independent copy of every message. In that case, both groups need their own compatibility contracts and risk duplicate side effects if both write to the same target system.

## 2. What Makes Up a Message Contract?

Do not treat a contract as merely a Java class. A message contract has multiple layers:

| Component | Contents | Example |
|---|---|---|
| Event identity | Event name and meaning | `OrderCreated` |
| Payload schema | Fields, types, optional/default | `orderId`, `totalMinor`, `currency` |
| Serialization | How objects turn into bytes | JSON, Avro, Protobuf |
| Content type | Hint for which `MessageConverter` to use | `application/json` |
| Schema reference | Subject, version, or schema ID | `orders-value v4` |
| Headers | Transport metadata | `eventId`, `correlationId`, `traceparent` |
| Key | Routing, ordering, or partitioning | `orderId` |
| Semantics | Business meaning of fields | `totalMinor` is always amount in minor currency units |

A change can be structurally compatible yet break semantics. For instance, `total` remains a `long`, yet the producer switches units from dollars to cents. A schema registry may consider the data type unchanged while the consumer calculates amounts off by 100x.

A contract should explicitly document:
- Event name and business purpose.
- Field meanings, units, timezones, and value domains.
- Required, optional, nullable, and default fields.
- Enum rules and unknown value handling.
- Key, ordering, and partitioning semantics.
- How unknown fields or newer schema versions are handled.
- Deprecation policy and support window for older versions.

### Java DTOs Are Not Wire Contracts

Two services can use Java classes with different packages, names, and internal structures and still interoperate if the wire bytes and schemas are compatible. Conversely, two services declaring identically named `OrderCreated` classes yet serializing different formats or field meanings remain incompatible.

Do not share a DTO library and assume it solves versioning automatically. Shared libraries can force services to deploy in lockstep or accidentally pull inconsistent dependency versions. Wire contracts must be managed and tested independently of how each service structures its code.

## 3. Content Types and Schema Registries in Spring Cloud Stream

Spring Cloud Stream represents data as Spring `Message` objects. The framework uses `MessageConverter` to convert payloads between application types and wire formats. `contentType` can come from message headers, binding properties, or the default `application/json`.

Example of a JSON binding:

~~~yaml
spring:
  cloud:
    function:
      definition: acceptOrder
    stream:
      bindings:
        acceptOrder-in-0:
          destination: orders
          group: billing
          content-type: application/json
~~~

`content-type` helps the framework choose a converter. It does not automatically validate whether every message conforms to a business JSON Schema. If a consumer DTO uses strict Jackson settings and receives an unexpected field, deserialization can fail even on valid JSON.

Distinguish:
- Content type: Selects how messages are converted.
- Schema: Describes data structure.
- Schema registry: Stores and resolves schema versions, optionally performing compatibility checks.
- Broker-native schema: A schema mechanism provided directly by the broker with its own semantics.

### Native Encoding/Decoding

When `useNativeEncoding` or `useNativeDecoding` is enabled, serialization/deserialization is delegated to the binder's client library. The framework then skips standard `content-type` payload marshalling. Producer serializers and consumer deserializers must be configured compatibly. With native encoding/decoding, `headerMode=embeddedHeaders` is also ignored.

Do not switch between framework conversion and native serialization during a rolling deployment without checking wire bytes and header behavior. Two applications can use the exact same Java DTO yet emit incompatible payloads.

## 4. Backward, Forward, and Full Compatibility

Compatibility modes describe the relationship between the producer's writer schema and the consumer's reader schema.

| Mode | Relationship | When Appropriate |
|---|---|---|
| BACKWARD | New reader schema reads data written with old schema | Prioritizes new consumers reading historical data |
| FORWARD | Old reader schema reads data written with new schema | Need new producers running alongside old consumers |
| FULL | Bidirectional compatibility between adjacent schemas | Producers and consumers can upgrade independently |
| BACKWARD_TRANSITIVE | New schema reads data from all prior schemas | Consumers can replay full history |
| FORWARD_TRANSITIVE | Old consumers read data from all newer schemas | Need old readers compatible across multiple writer generations |
| FULL_TRANSITIVE | Bidirectional compatibility across entire schema history | Systems requiring rollbacks/replays across multiple generations |
| NONE | No compatibility check | Only for tightly controlled migration workflows |

**Backward compatibility:** consumers using the new schema can read old messages. It does not guarantee old consumers can read new messages.

**Forward compatibility:** consumers using the old schema can read new messages. It does not guarantee new consumers can read old messages.

**Full compatibility:** both directions hold between the checked schemas. Regular `FULL` only compares against the immediate predecessor; `FULL_TRANSITIVE` checks against the entire schema history.

Confluent Schema Registry defaults to non-transitive `BACKWARD`. Therefore, when a system needs to replay from the start of a topic, evaluate `BACKWARD_TRANSITIVE` rather than assuming compatibility with the immediate previous schema implies full historical compatibility.

### Deployment Ordering by Compatibility Mode

| Compatibility | Safe Deployment Order | Reason |
|---|---|---|
| BACKWARD | New consumers first, new producers second | Old consumers are not guaranteed to read the new schema |
| FORWARD | New producers first; wait for old data to drain/expire; new consumers second | New consumers are not guaranteed to read the old schema |
| FULL | Producers and consumers can upgrade independently within tested version pairs | Both old and new readers handle old and new writers within policy scope |
| NONE | Requires coordinated migration/maintenance window | No guarantees enforced by registry |

This ordering follows schema compatibility rules. During rolling deployments, you must still account for live old instances, consumer group membership, backlogs, and messages in DLQs.

### Non-Transitive vs. Transitive

Suppose schemas v1, v2, and v3 exist:

- `BACKWARD` only checks v3 against v2.
- `BACKWARD_TRANSITIVE` checks v3 against both v2 and v1.
- A sequence of edits can be stepwise compatible while v3 still cannot read v1 data.

Transitivity is critical when topics retain data for long periods, consumers reset offsets, or DLQs are replayed months later.

## 5. The Expand-Contract Pattern

Expand-contract is a technique for evolving contracts across multiple deployments to maintain compatibility while services roll out out of sync.

The workflow has two phases:

- **Expand:** Widen schemas and code to accept both old and new data.
- **Contract:** Remove legacy structures only after all producers/consumers have migrated and old data no longer needs processing.

Example: adding `currency` to the `OrderCreated` event.

### Phase 1: Schema v1

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "totalMinor": 125500
}
~~~

Consumer v1 only knows `eventId`, `orderId`, and `totalMinor`.

### Phase 2: Expand the Consumer

Deploy consumer v2 capable of handling messages without `currency`. During this stage, the producer still emits schema v1. Consumer v1 and v2 can share the group; both can read old messages.

Example new Java DTO:

~~~java
public record OrderCreated(
    String eventId,
    String orderId,
    long totalMinor,
    String currency
) {
    String resolvedCurrency() {
        return currency == null ? "VND" : currency;
    }
}
~~~

Default values must reflect the real business contract. Never use an arbitrary default to hide missing data or mismatched units. Never assume all currencies share the same decimal precision; minor-unit conversion rules belong to an explicit business contract.

### Phase 3: Upgrade the Producer

Once all old consumers have left the group and consumer v2 is ready, producer v2 begins emitting `currency`:

~~~json
{
  "eventId": "evt-1002",
  "orderId": "ORD-1002",
  "totalMinor": 125500,
  "currency": "VND"
}
~~~

Consumer v2 reads both old messages without `currency` and new messages with `currency`. If v1 consumers remain, new messages may reach them and fail if they are strict about unknown fields. Thus, do not enable producer v2 while v1 consumers are active unless you have verified v1 consumers ignore unknown fields.

### Phase 4: Contract the Schema

Only after:
- All producers emit the new field.
- All consumers read the new field.
- Backlogs and old DLQs have been processed or have a replay strategy.
- The retention window requiring old-schema support has elapsed.
- No remaining service reads the old field.

Only then consider dropping the legacy field or changing the schema in a separate migration step. If a field's meaning or data type must change, add a new field, migrate producers/consumers gradually, and then remove the old field.

~~~mermaid
sequenceDiagram
    participant C1 as Consumer v1
    participant C2 as Consumer v2
    participant P1 as Producer v1
    participant P2 as Producer v2
    participant B as Broker
    P1->>B: Event schema v1
    alt Broker assigns message to old instance
        B->>C1: Consumer v1 reads v1
    else Broker assigns message to new instance
        B->>C2: Consumer v2 reads v1
    end
    Note over C1,C2: Deploy consumer v2; producer stays v1
    P1->>B: Event schema v1
    B->>C2: New consumer reads v1 after rebalance
    Note over C1,C2: Wait until all v1 consumers leave the group
    P2->>B: Event schema v2 with optional field
    B->>C2: Consumer v2 reads v2
    Note over P2,C2: Remove old contract only after backlog and replay window
~~~

## 6. Rolling Deployments and Consumer Groups

In Kubernetes or other orchestrators, rolling updates usually start new instances before stopping old ones. With consumer groups, both old and new consumer versions can run simultaneously.

For example, a billing group has four instances:
- Two v1 instances.
- Two v2 instances.

The broker distributes messages across instances according to group/partition/queue mechanics. The broker does not know that v1 instances only support schema v1. If the producer emits schema v2, v1 instances can still receive those messages.

Before enabling producer v2:
1. Verify all consumer replicas run compatible versions.
2. Verify the consumer group has stabilized after rebalancing.
3. Verify old workers have shut down and left the group.
4. Check other consumers too, not just services owned by your own team.
5. Verify DLQ/replay consumers and batch jobs also understand the new schema.
6. Only then switch the producer to the new schema.

### Readiness and Graceful Shutdown

Readiness should reflect an instance's ability to receive and process messages. When stopping an instance:
- Stop accepting new work using the appropriate binder/client mechanism.
- Finish or safely handle in-flight messages.
- Ack/commit only after business work finishes.
- Close the consumer so the group rebalances.
- Keep `terminationGracePeriodSeconds` large enough for shutdown.
- Monitor lag and duplicates after rollout.

Do not treat an HTTP readiness probe as sole proof of consumer readiness. An instance can return HTTP 200 before the binder joins its group or reaches the schema registry. Check health and binding/broker state according to binder capabilities.

### Rolling Back During a Rolling Update

Rolling back consumer v2 to v1 is only safe if current producers still emit a schema that consumer v1 understands. If the producer has already emitted schema v2:
- Stop or roll back the producer to schema v1 first.
- Verify v1 consumers can read already-written messages.
- If not, use a consumer adapter/bridge or route data to a new topic.
- Do not delete schema v2 from the registry to force a rollback; already-published messages may still reference that schema.

## 7. JSON: New Fields, Unknown Fields, and Null Values

JSON is flexible, yet not automatically safe when adding or removing fields. Compatibility depends on both schema policies and each service's converter settings.

Example v1:

~~~json
{
  "orderId": "ORD-1001",
  "totalMinor": 125500
}
~~~

v2 adds a field:

~~~json
{
  "orderId": "ORD-1001",
  "totalMinor": 125500,
  "currency": "VND"
}
~~~

If consumer v1 ignores unknown fields, the change can be forward-compatible. If Jackson is configured to fail on unknown properties, consumer v1 will error out. Inspect the actual `ObjectMapper` and `MessageConverter` rather than relying on assumptions.

Cases to distinguish:

- Absent field: Producer did not send the property.
- Null field: Producer sent the property with no value.
- Defaulted field: Converter or application filled it in.
- Changed field type: For example, `totalMinor` changed from number to string.
- Changed field meaning: Still a number, yet units changed.

Do not conflate these cases. Business validation may treat missing, null, and default as three distinct scenarios.

### JSON Schema and Strictness

When using a JSON Schema registry, verify `additionalProperties`, `required` properties, and compatibility policies. With a closed schema (`additionalProperties: false`), adding a field may be rejected or render consumers incompatible. With an open schema, unknown fields may pass validation, yet consumer code must still be verified.

Schema compatibility does not guarantee business logic accepts new values. For instance, an enum `status` adds `SUSPENDED`; old consumers might parse the JSON yet lack a branch handling the new value. Provide explicit fallbacks or roll out consumers first.

## 8. Avro: Writer Schema and Reader Schema

Avro supports schema resolution. Producers write data using a writer schema; consumers read using their application version's reader schema. Writer and reader schemas can differ when resolution rules allow.

Example v1:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.acme.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalMinor", "type": "long" }
  ]
}
~~~

v2 adds `currency` with a nullable union and default `null`:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.acme.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "totalMinor", "type": "long" },
    {
      "name": "currency",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
~~~

Providing a default for the new field allows the new reader schema to read records written under the old schema that lack `currency`. Avro requires the default to match the first branch of the union; hence `null` comes first above.

Renaming a field may require aliases so the reader schema recognizes the old name. Removing fields also requires verifying reader/writer resolution and defaults. Never rename a field simply for prettier Java property names; the wire name is part of the contract.

### Spring Cloud Stream Schema Registry

Spring Cloud Stream provides:
- Standalone Schema Registry Server.
- `SchemaRegistryClient` for applications to register and fetch schemas.
- An Avro message converter integrated with the registry.
- Clients that interact with Spring Cloud Stream Schema Registry or Confluent Schema Registry.

With the Avro converter, output bindings use a content type like `application/*+avro`. The converter infers the schema from the payload type, registers the schema under a subject and version, and sends a content type carrying subject/version info. Consumers read the header reference, fetch the writer schema, and reconcile it with the application's reader schema.

Endpoint configuration example:

~~~yaml
spring:
  cloud:
    stream:
      schemaRegistryClient:
        endpoint: https://schema-registry.example.net
~~~

Register the client in the application:

~~~java
import org.springframework.cloud.stream.schema.registry.EnableSchemaRegistryClient;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
@EnableSchemaRegistryClient
public class BillingApplication {
}
~~~

For output bindings, configure the Avro content type via the binding property supported by your project's Spring Cloud Stream version:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders
          content-type: application/*+avro
~~~

Verify the `spring-cloud-stream-schema-registry-client` artifact, BOM version, and `SchemaRegistryClient` configuration for your project. Spring Cloud Stream supports the Avro schema registry converter out of the box; for JSON Schema or Protobuf, configure appropriate serializers/converters and registry integrations rather than assuming the Avro converter handles them automatically.

Registries check schemas by subject. Subject naming strategies must stay consistent across versions; if a subject changes unintentionally, the new schema enters a separate compatibility lineage and bypasses the old subject's history.

## 9. Protobuf: Field Numbers and Reserved Identifiers

Protobuf uses field numbers on the wire. Never change the field number of an existing field. When deleting a field:
- Never reuse the old field number.
- Add that number to `reserved`.
- Also reserve the field name to avoid JSON/TextFormat conflicts.
- Add new fields with previously unused field numbers.

v1:

~~~protobuf
syntax = "proto3";

message OrderCreated {
  string order_id = 1;
  int64 total_minor = 2;
}
~~~

v2 adds `currency`:

~~~protobuf
syntax = "proto3";

message OrderCreated {
  string order_id = 1;
  int64 total_minor = 2;
  string currency = 3;
}
~~~

After removing `total_minor` in a future change:

~~~protobuf
message OrderCreated {
  string order_id = 1;
  string currency = 3;

  reserved 2;
  reserved "total_minor";
}
~~~

Never change `total_minor` from `int64` to `string` while keeping the same field number. That breaks wire compatibility. Create a new field with a new number, migrate consumers/producers, and then reserve the old field.

Enums must also evolve carefully. Old consumers need a way to handle unknown enum values; avoid assuming producers only send values known to the current code version.

## 10. Schema Registries vs. Broker-Native Schemas

Not all brokers manage schemas the same way:

| System | Common Mechanism | What to Verify |
|---|---|---|
| Kafka | External Schema Registry or convention-based serializers/deserializers | Subject, compatibility mode, schema ID/version, key/value subjects |
| RabbitMQ | Payloads and headers agreed upon by producers/consumers; broker does not enforce a single schema across queues | Contract repository, converters, application-level validation |
| Pulsar | Native schemas and schema versions attached to topics; supports JSON, Avro, Protobuf, or appropriate schema types | Schema compatibility policy, producer/consumer schemas, and topic |
| Spring Cloud Stream | `MessageConverter`, content type, and `SchemaRegistryClient` | Which converters are actually present and whether the binder preserves headers/native metadata |

Spring Cloud Stream's Schema Registry and Pulsar's native schema are two separate mechanisms. An application can use a framework-level schema registry or delegate schemas to the client/broker, but each topic must agree on a single wire contract.

With RabbitMQ, an existing queue does not prove payloads are valid. Use contract tests, validation, and versioned schemas at the application layer or a dedicated registry. With Kafka, registry compatibility does not automatically guarantee running consumers have the right serializers/deserializers. With Pulsar, broker-native schema enforcement must be enabled/configured properly, and consumers still need compatible business logic.

## 11. Testing Contracts Before Deployment

A test that only serializes and deserializes the same version does not test out-of-sync rollouts. Test cross-version producer/consumer pairs.

### Test Matrix

| Producer | Consumer | Question |
|---|---|---|
| P1 | C1 | Does the current baseline still pass? |
| P1 | C2 | Can the new consumer read old data? |
| P2 | C1 | Can the old consumer read new data? |
| P2 | C2 | Do both new versions work together properly? |
| P1/P2 | Replay C2 | Can the new consumer read all required historical data? |
| P2 | DLQ/recovery C1 | Do recovery tools understand the new schema? |

With `BACKWARD`, P1/C2 is critical; P2/C1 is not guaranteed. With `FORWARD`, P2/C1 is critical; P1/C2 is not guaranteed. With `FULL`, both pairs must pass within the version range protected by the policy.

### Testing in CI

A CI pipeline can:

1. Fetch currently registered schemas for the subject.
2. Compare candidate schemas against the compatibility policy.
3. Generate serializers/deserializers or message fixtures.
4. Run `P1 -> C2` and `P2 -> C1` tests per the chosen mode.
5. Test missing/null/default/unknown fields.
6. Test new enums and field type changes.
7. Replay messages from historical fixtures.
8. Verify headers, content types, schema references, and keys.
9. Run integration tests with the actual binder/broker in use.
10. Block merges or releases if required version pairs are incompatible.

Do not test only the schema registry endpoint. The registry may accept a schema while business validation or downstream databases still reject the new values.

### Testing with Spring Cloud Stream

Use the Spring Integration Test Binder for fast binding/function logic tests, yet add integration tests with a real broker or equivalent environment to verify:
- Actual serializers/deserializers.
- Headers and content types.
- Schema registry authentication/availability.
- Consumer group rollouts.
- Retries, DLQs, and replays.
- Native schema behavior of the binder.
- Broker compatibility enforcement.

The test binder does not replace testing wire formats against a real broker.

## 12. Handling Breaking Changes

A change is breaking if new producers emit data that currently running consumers cannot read or interpret accurately.

Examples:
- Changing `totalMinor` from integer to decimal/string.
- Changing currency units or timezones without changing the contract.
- Changing keys in a way that alters ordering/partitioning.
- Removing fields still needed by consumers.
- Changing enums when consumers do not handle new values.
- Changing content types or serialization formats.
- Changing the schema subject so registry policies miss historical schemas.

When compatibility cannot be preserved:
1. Create a new topic or event type for the new contract, such as `orders.v2`.
2. Deploy consumer v2 and test with producer v2.
3. If needed, run a bridge/adapter reading v1 and translating to v2.
4. Dual-publish or mirror during a controlled transition window.
5. Reconcile counts, event IDs, and business outcomes between both streams.
6. Switch consumers/downstream systems to v2.
7. Retire v1 after backlogs, retention, and v1 DLQs are drained.
8. Maintain replay and rollback runbooks throughout the migration.

Never push a breaking schema and switch compatibility mode to `NONE` to pass CI. That merely disables the guardrail; consumers will still fail when receiving the data.

## 13. Rollbacks and Historical Data

Rolling back an application does not delete already-published messages. If producer v2 already wrote schema v2, rolling the producer back to v1 does not leave the topic with only schema v1. Rolled-back consumers must be able to read every schema that can still appear in backlogs/replays.

Before rolling back:
- Identify the newest schema version already published.
- Verify whether rolled-back consumers can read that writer schema.
- Check partially processed messages and idempotency.
- Check DLQs, retry queues, and scheduled replays.
- Keep the schema registry and schema history intact.
- If incompatible, deploy an adapter/consumer bridge before rolling back the service.

With Kafka, resetting offsets or replaying from the beginning can bring very old messages back. With RabbitMQ, messages linger in queues or DLQs per retention/TTL. With Pulsar, backlogs and retained messages may reference older schemas. Compatibility policies should account for how long data can be re-read, not just rolling update duration.

## 14. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Old consumers fail right after producer rollout | Producer emits new fields/types while old instances remain in group | Deploy compatible consumers first or use `FULL` |
| New consumers fail on historical messages | Schema is only backward-compatible with immediate predecessor or lacks defaults | Check transitive compatibility and reader schemas |
| Registry accepts yet function fails | Schema is valid, but business validation/DTO is strict | Test converters, validation, and semantics |
| Adding JSON field breaks old consumers | Strict Jackson fails on unknown properties | Inspect `ObjectMapper` and deploy consumers first |
| Avro reports missing field | New field lacks an appropriate default | Add union/null and default per Avro resolution rules |
| Protobuf misparses after field change | Reused field number or changed wire type | Use a new field number and reserve the old number |
| New consumers misinterpret enums | New enum value lacks fallback | Add `UNKNOWN`/default handling and deploy consumers first |
| Consumer rollback fails | Producer already emitted schemas unreadable by old consumers | Roll back producer, add adapter, or migrate topic |
| Schema checks miss historical breakage | Using non-transitive compatibility | Choose transitive mode when historical replay is needed |
| Two services use different subjects | Inconsistent subject naming strategy | Standardize subjects and ownership |
| Headers/schema IDs disappear | Binder or native encoding altered header behavior | Test header mapping and wire format |
| Dual-publishing causes duplicate side effects | Consumers read the same event from two topics | Use stable `eventId` and deduplication |
| Changing partition key breaks ordering | Key semantics changed while consumers process legacy flow | Plan a separate key/partition migration |

## 15. Practice Exercise: Upgrading OrderCreated v1 to v2

Scenario: the producer currently emits `OrderCreated` v1 with `orderId` and `totalMinor`. You need to add `currency` while `billing` and `reporting` consumers deploy independently.

1. Save schema v1 as a fixture.
2. Create schema v2 adding optional `currency` with a valid default.
3. Register schema v2 and check `BACKWARD` or `FULL` per the planned rollout.
4. Update consumer v2 to read v1 messages missing `currency`.
5. Run `P1/C2` tests and verify business outcomes.
6. Deploy consumer v2 while the producer remains on v1.
7. Confirm all consumer v1 instances left the group and the group is stable.
8. Deploy producer v2 to start sending `currency`.
9. Run `P2/C2` tests and watch deserialization error/DLQ dashboards.
10. Replay v1 messages from fixtures or test environments through consumer v2.
11. Simulate rolling back producer and consumer to verify compatibility.
12. After the legacy support window, retire deprecated fields if any and check transitive schemas.
13. Write runbooks for replay, rollback, and DLQs.

Acceptance checklist:

| Item | Verification Outcome |
|---|---|
| Contract | Includes event name, field semantics, types, null/defaults, and keys |
| Compatibility mode | Selected based on deployment order and replay window |
| Schema registry | Subjects/versions managed consistently |
| Consumer v2 | Reads v1 messages cleanly |
| Producer v2 | Emits new schema only after old consumers leave or mode permits |
| Rolling update | No incompatible instances receive messages simultaneously |
| Replay | Historical data and DLQs are readable |
| Serializer | Content types, schema references, and wire bytes are correct |
| Broker | Kafka/RabbitMQ/Pulsar binders tested against real brokers |
| Rollback | Safe rollback path verified |
| Semantic compatibility | Units, timezones, enums, and keys remain aligned with plan |
| Migration | Breaking changes use controlled topics/adapters and cutover |

## Conclusion

Contract compatibility must be designed for the entire window in which producers and consumers may diverge in version, including rolling updates, rollbacks, backlogs, and replays. Backward compatibility requires new consumers to read old data; forward compatibility requires old consumers to read new data; full compatibility supports both directions across checked schemas. Transitivity is essential whenever historical data may be re-read across multiple versions.

In Spring Cloud Stream, content types, `MessageConverter`, native encoding/decoding, and schema registries all require explicit configuration. Apply expand-contract, deploy compatible consumers before producers emit new schemas, test cross-version producer/consumer pairs, and preserve schema history. When a change genuinely breaks the contract, create a new topic/version and run a controlled migration instead of relying on simultaneous deployment.

## References

- [Spring Cloud Stream 5.0.5 – Schema Registry](https://docs.spring.io/spring-cloud-stream/reference/5.0/schema-registry/spring-cloud-stream-schema-registry.html)
- [Spring Cloud Stream – Content Type Negotiation](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/mechanics.html)
- [Spring Cloud Stream – Binding Properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Confluent – Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Confluent – Schema Compatibility API](https://docs.confluent.io/platform/current/schema-registry/develop/api.html)
- [Apache Avro – Specification](https://avro.apache.org/docs/1.12.0/specification/)
- [Protocol Buffers – Updating a Message Type](https://protobuf.dev/programming-guides/proto3/#updating)
- [Protocol Buffers – Reserved Field Numbers and Names](https://protobuf.dev/programming-guides/editions/#reserved-field-numbers)
- [Spring Boot – Application Availability and Graceful Shutdown](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html)
