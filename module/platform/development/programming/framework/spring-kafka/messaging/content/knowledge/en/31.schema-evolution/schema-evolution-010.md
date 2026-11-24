# Schema Compatibility Testing

In Kafka, producers and consumers are frequently deployed at different times. A new producer may emit events while some consumer instances are still running an older version. In addition, events already written to a topic may be re-read hours or days later when a consumer restarts, joins a new consumer group, or reprocesses data.

Therefore, changing a DTO or JSON structure is not merely an internal application change. It is a change to the data contract between services. Schema compatibility testing determines which producer and consumer versions can exchange data safely before changes are rolled out.

In Spring Kafka, `KafkaTemplate` converts objects into bytes via a serializer; `@KafkaListener` receives bytes and converts them into objects via a deserializer. The Kafka broker stores and forwards records, but the broker itself does not understand the meaning of fields inside payloads. Compatibility must be guaranteed by serializers, deserializers, schemas or Schema Registry if used, and application tests.

## 1. The schema is the event's contract

Suppose a service emits an `OrderCreated` event with the payload:

```json
{
  "orderId": "DH-001",
  "amount": 125000
}
```

The producer can represent this event with a Java class:

```java
import java.math.BigDecimal;

public record OrderCreated(
    String orderId,
    BigDecimal amount
) {}
```

The consumer can also have its own DTO to read the same event. The two services do not need to share a Java library, yet they must agree on field names, data types, semantics, and rules for handling absent fields or `null` values.

A useful schema should answer these questions:

- Which fields are required? Which fields may be absent?
- If a new field is not present in old events, where does the new consumer get a default value?
- How do old consumers behave when encountering a new field?
- Can a field change type, name, or meaning?
- Which schema versions' events must consumers be able to re-read?

The last point is especially important for Kafka. A producer change does not affect only records sent from deployment onward. New consumers may also read old records still sitting within the topic's retention window.

## 2. Three compatibility directions to distinguish

When discussing schema compatibility, distinguish the **write schema** from the **read schema**. The write schema describes the payload produced by the producer; the read schema describes the structure the consumer uses to decode that payload.

| Compatibility type | Question to verify | Deployment scenario |
|---|---|---|
| Backward compatibility | Can consumers using the new schema read data written with the old schema? | Deploy new consumers first while old producers are still sending events. |
| Forward compatibility | Can consumers using the old schema read data written with the new schema? | New producers begin sending events while old consumers are still running. |
| Full compatibility | Do both new consumers reading old data and old consumers reading new data work? | Producers and consumers are upgraded at different times. |

For example, version 1 has `orderId` and `amount`; version 2 adds `currency`. If new consumers supply a default value when `currency` is absent, they can read old events. If old consumers ignore unrecognized fields, they can read new events. Once both conditions are verified, the change can satisfy full compatibility across those two versions.

Systems using Schema Registry typically configure compatibility levels such as `BACKWARD`, `FORWARD`, or `FULL`. Some registries also offer transitive modes, such as `BACKWARD_TRANSITIVE`, to compare the new schema against all prior versions rather than only the latest one. Read the exact conventions of your registry because mode names and check scopes depend on the product and configuration.

## 3. Assessing the impact of schema changes

Do not conclude a change is safe merely because code compiles or JSON remains valid. Evaluate the readability of old consumers and new consumers separately.

| Change | Compatibility risk | What to test |
|---|---|---|
| Add optional field with default value | Usually safer since new consumers know how to handle old events; old consumers can still fail if they reject unknown fields. | New consumer reads old payload; old consumer reads new payload. |
| Add required field without default | New consumers may fail to read old events because the field does not exist yet. | Decode old events with new consumer and verify validation. |
| Remove field | Old consumers may fail to read new events if they still require that field. New consumers also need to handle the field appearing in old data. | Read payloads of both versions in both directions. |
| Rename field | Usually equivalent to removing the old field and adding a new one; old data may not map to the new name. | Verify aliases, mappings, or data-migration steps. |
| Change data type | May cause serializer or deserializer failures, or corrupt values during conversion. | Test boundary values, large numbers, and historical data. |
| Add enum value | Old consumers may not know how to handle the new value. | Send the new enum value to every supported consumer version. |
| Change field meaning while keeping same type | Structural schema checks may succeed even though business logic misreads the data. | Verify business rules and value semantics. |

Conclusions in the table depend on format and configuration. For instance, JSON does not automatically dictate that consumers ignore unknown fields; Jackson can be configured to reject unknown properties. With Avro, adding a field usually requires a default so new reader schemas can read old data. With Protobuf, used field numbers must never be reused after removal.

A practical principle is designing consumers resilient to controlled evolution: handle absent fields, `null` fields, unknown fields, and unknown enum values explicitly. However, merely ignoring unknown fields does not replace business verification. If a new field changes how totals or order states are calculated, old consumers may decode successfully yet process business logic incorrectly.

## 4. Building a producer and consumer test matrix

Before writing tests, list all schema versions that can still appear in data and all consumer versions that can run concurrently. A basic matrix includes:

| Data produced by | Consumer under test | Goal |
|---|---|---|
| Old producer | New consumer | Verify backward compatibility. |
| New producer | Old consumer | Verify forward compatibility. |
| New producer | New consumer | Verify the current version's contract. |
| Stored historical payloads | New consumer | Verify Kafka data replay capability. |

If a topic has existed across multiple upgrades, keep representative payloads of old versions as fixtures in `src/test/resources`. Fixtures should be the actual bytes or event contents released previously—do not regenerate everything from new DTOs, as doing so can accidentally erase old schema differences.

The matrix should reflect real deployment topology. During rolling deployments, old and new consumer instances can coexist inside one consumer group. Each partition is assigned to one instance at a time, so new events can reach old instances while an upgrade is in progress. During replays, new consumers can encounter events from multiple producer versions. Test these cases instead of only testing the newest DTO pair.

## 5. Example JSON compatibility test with Jackson

The following example simulates two event versions. Consumer version 1 ignores unknown fields. Consumer version 2 supplies a default value for `currency` when reading old payloads.

```java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.json.JsonMapper;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;

record OrderCreatedV1(String orderId, BigDecimal amount) {}

record OrderCreatedV2(
    String orderId,
    BigDecimal amount,
    String currency
) {
    OrderCreatedV2 {
        if (currency == null || currency.isBlank()) {
            currency = "VND";
        }
    }
}

class OrderSchemaCompatibilityTest {

    // Illustrative config: consumer accepts unknown JSON fields.
    // In a real application, tests must use the same ObjectMapper config as production.
    private final ObjectMapper mapper = JsonMapper.builder()
        .disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES)
        .build();

    @Test
    void oldConsumerCanReadPayloadFromNewProducer() throws Exception {
        OrderCreatedV2 event = new OrderCreatedV2(
            "DH-001",
            new BigDecimal("125000"),
            "VND"
        );

        byte[] payload = mapper.writeValueAsBytes(event);
        OrderCreatedV1 decoded = mapper.readValue(payload, OrderCreatedV1.class);

        assertEquals("DH-001", decoded.orderId());
        assertEquals(new BigDecimal("125000"), decoded.amount());
    }

    @Test
    void newConsumerCanReadPayloadFromOldProducer() throws Exception {
        String oldPayload = """
            {
              "orderId": "DH-001",
              "amount": 125000
            }
            """;

        OrderCreatedV2 decoded = mapper.readValue(oldPayload, OrderCreatedV2.class);

        assertEquals("DH-001", decoded.orderId());
        assertEquals("VND", decoded.currency());
    }
}
```

The first test proves the old consumer can read a payload with the added `currency` field when Jackson is configured to ignore unknown fields. If the production application enables `FAIL_ON_UNKNOWN_PROPERTIES`, the test must mirror that setting; the test will then catch the incompatible change instead of silently assuming unknown fields are ignored.

The second test verifies that the new consumer reads a payload lacking `currency`. The record's compact constructor applies the default when Jackson passes `null` for the missing field. If business logic distinguishes an absent field from a field explicitly set to `null`, add tests for both payloads and handle them per documented rules.

This is a Jackson-level payload contract test. It does not prove the entire Spring Kafka configuration works properly. In real applications, use the actual `ObjectMapper` bean and serializer/deserializer configuration running in production. If `JsonSerializer` or `JsonDeserializer` uses type headers, trusted packages, or type mappings, test those settings too.

## 6. Testing with real schema formats and tooling

The test strategy must match the event format the application actually sends.

| Format | Points to verify |
|---|---|
| JSON | Required fields, optional fields, `null` values, unknown fields, data types, and Jackson deserialization configuration. If using JSON Schema, validate payloads against each version's schema. |
| Avro | Writer schema and reader schema, defaults for new fields, unions with `null`, aliases when renaming fields, and ability to read old schema versions. |
| Protobuf | Field numbers, wire types, default values, new enum handling; no reuse of deleted field numbers or names. |

If the system uses Schema Registry, add a compatibility check step to CI before registering or releasing a new schema. That step catches structural changes rejected by the registry early. Select the right compatibility mode for your rollout strategy and consider transitive modes when new consumers must read all retained data from prior versions.

Registry checks alone are not sufficient. They cannot verify every business rule, each consumer's Jackson configuration, or whether code processes new values properly. Therefore, combine three layers:

1. **Schema checks:** validate the new schema and registry compatibility rules.
2. **Contract tests:** use payload fixtures from old and new producers to test each consumer.
3. **Spring Kafka integration tests:** use an embedded broker or test environment to send records via `KafkaTemplate`, then verify `@KafkaListener` receives and processes payloads with real serializers/deserializers.

Integration tests should verify keys, values, and headers if the application relies on them. For asynchronous consumers, await event receipt using test synchronization utilities rather than short fixed sleep durations. If tests involve retries or dead-letter topics, verify incompatible events route to the configured error flow.

## 7. Integrating testing into the event change workflow

A suitable workflow for each schema change can follow these steps:

1. **Describe the change:** record added, removed, renamed, retyped, or re-semanticized fields; define default values and `null`-handling rules.
2. **Select compatibility direction:** determine whether backward, forward, or full compatibility is needed based on producer/consumer upgrade order.
3. **Check schema:** run validators or Schema Registry compatibility checks if used.
4. **Run payload matrix:** read old fixtures with the new consumer, read new payloads with the old consumer, and verify current-version payloads.
5. **Run integration tests:** verify real Kafka configuration, including serializers, deserializers, type headers, and listeners.
6. **Define rollout:** for backward-compatible changes, consumers can usually upgrade before producers. For forward-compatible changes, new producers can deploy first if old consumers are verified to read new payloads. For full compatibility, both sides have greater flexibility, yet historical readability must still be preserved.

Do not delete old fixtures simply because current producers stopped emitting that schema. If records may still exist within retention, in external archives, or be replayed from another system, new consumers must still process them or have an explicit data-conversion pipeline.

## 8. Common pitfalls in testing

**Testing only that the producer serializes successfully.** Producing JSON or Avro bytes does not prove old consumers can read that payload. Test the read path of every supported consumer version.

**Using new DTOs to generate fixtures for old data.** Such fixtures no longer represent historical payloads. Store real sample payloads by version or pull them from controlled test datasets.

**Using a separate `ObjectMapper` in tests.** If tests configure ignoring unknown fields while production rejects them, test results misrepresent real behavior. Use the actual configured bean in integration tests or keep test config aligned with production.

**Testing only whether fields exist.** Also test `null`, absent fields, empty strings, new enum values, out-of-range numbers, and semantic changes.

**Testing only against the immediately preceding version.** New consumers may need to re-read events produced several releases earlier. Maintain fixtures for all versions still within retention or still supported.

**Treating registry acceptance as an absolute guarantee.** The registry checks the schema rules it supports. Application tests must still verify serializers/deserializers, DTO mappings, and business behavior.

## 9. Checklist before releasing a new schema

- [ ] Identified write schemas and read schemas of all relevant versions.
- [ ] Explicitly chosen backward, forward, or full compatibility.
- [ ] New fields have rules for absent values and `null` values.
- [ ] Old and new consumers are tested against each other's payloads.
- [ ] Historical payloads eligible for replay have test fixtures.
- [ ] Serializer/deserializer configuration in tests matches Spring Kafka production settings.
- [ ] Schema Registry or validators accept the new schema if the system uses them.
- [ ] Business meaning changes are verified beyond structural schema comparisons.
- [ ] Rollout order and rollback capability are defined.

Schema compatibility testing is part of the event contract in a Kafka system. By testing new data, old data, live consumers, and replay flows, teams can evolve events incrementally while keeping Spring Kafka services exchanging data accurately throughout upgrades.
