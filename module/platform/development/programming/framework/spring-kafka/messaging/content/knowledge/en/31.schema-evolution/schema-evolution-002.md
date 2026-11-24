# JSON Schema and Versioning

JSON is very flexible, but if producers and consumers freely alter payload structure, the contract between services easily breaks. A producer might change `amount` from a number to a string, remove a field, or add a required field that older consumers do not know about. The message remains syntactically valid JSON, yet it is no longer valid for the application reading it.

JSON Schema describes the structure and constraints of a JSON document. When combined with Schema Registry, each subject maintains a history of schema versions and a compatibility policy to validate changes before producers or consumers deploy. In Spring Kafka, you can use Jackson `JsonSerializer`/`JsonDeserializer` for plain JSON transport, or Confluent `KafkaJsonSchemaSerializer`/`KafkaJsonSchemaDeserializer` to integrate JSON Schema with Schema Registry. These two approaches serve different goals and should not be confused.

## 1. JSON document, JSON Schema, and Schema Registry

Three concepts to distinguish:

| Component | Role | Example |
|---|---|---|
| JSON document | Actual data sent in a Kafka record | `{"orderId":"O-42","amount":120000}` |
| JSON Schema | Describes data types, required fields, and constraints | `orderId` is a string, `amount` is a number |
| Schema Registry | Stores schemas by subject/version, assigns schema IDs, and checks compatibility | Subject `orders-value`, version 2 |

A JSON Schema is not a sample JSON message. It is a contract used to validate messages. Schema Registry also does not replace the Kafka broker; the Registry manages schemas and metadata, while Kafka stores records. Serializers/deserializers connect the two via the schema ID.

If you only use `org.springframework.kafka.support.serializer.JsonSerializer`, Spring Kafka uses Jackson to convert objects into JSON bytes. That serializer does not automatically register JSON Schemas, assign schema IDs, or perform compatibility checks in Schema Registry. To get those capabilities, you need Registry-compatible serializers/deserializers, such as Confluent JSON Schema SerDes.

## 2. How does JSON Schema describe data?

JSON Schema uses keywords to define data types and rules. Common keywords:

| Keyword | Meaning |
|---|---|
| `$schema` | URI identifying the JSON Schema dialect/draft |
| `$id` | URI identifying the schema and serving as the base URI for resolving references |
| `type` | Data type such as `object`, `array`, `string`, `integer`, `number`, `boolean`, `null` |
| `properties` | Schema for each property inside an object |
| `required` | List of properties that must be present |
| `additionalProperties` | Specifies whether undeclared properties are allowed |
| `items` | Schema for elements inside an array |
| `enum` | Allowed set of values |
| `minimum`, `maximum` | Numeric bounds |
| `minLength`, `maxLength` | String length bounds |
| `pattern` | Regular expression for strings |
| `oneOf`, `anyOf`, `allOf` | Combine multiple schemas under different rules |
| `$ref` | Reference another schema or part of the current schema |

For example, a schema for the `OrderCreated` event:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.com/orders/order-created.json",
  "title": "OrderCreated",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "eventId": { "type": "string", "minLength": 1 },
    "orderId": { "type": "string", "minLength": 1 },
    "occurredAt": { "type": "string", "format": "date-time" },
    "amount": { "type": "number", "minimum": 0 },
    "currency": { "type": "string", "enum": ["VND", "USD"] }
  },
  "required": ["eventId", "orderId", "occurredAt", "amount", "currency"]
}
```

This schema requires the payload to be an object with all five properties. `amount` must be a non-negative number; `currency` can only be `VND` or `USD`; undeclared properties are rejected due to `additionalProperties: false`.

The example uses Draft 2020-12. Confluent Platform before 7.6.0 fully supports Draft 04, 06, and 07; version 7.6.0 and later additionally support Draft 2020-12. If your project's Registry is older, change `$schema` to a supported draft (typically Draft 07) and verify the keywords used.

`format: date-time` describes a date-time string format, but whether `format` validation is enforced or treated merely as an annotation depends on the draft and validator. If the format is a hard requirement, verify whether your validator has format assertion enabled and add tests for invalid data.

## 3. Distinguishing `$schema`, `$id`, and version

These three pieces of metadata solve three different problems:

- `$schema` identifies the JSON Schema specification version, such as Draft 07 or Draft 2020-12. It is not the event version.
- `$id` identifies the schema and helps resolve `$ref`. It does not auto-increment when a new schema is registered.
- Schema Registry subject version indicates the registration order of a schema within a subject, such as version 1, 2, 3.

In addition, Schema Registry assigns a schema ID for the serializer to write into the wire format. Schema ID and subject version are not the same concept. A schema ID identifies a schema across the Registry; a version identifies a schema's position in a subject's history. Do not use the schema ID as a business event version.

If an event needs a version for business logic, include a dedicated field such as `eventVersion` or `eventTypeVersion` in the payload. That field describes the business contract version, whereas the Registry version serves schema management. The two numbers may coincide by chance, but they are not required to match.

## 4. Absent field vs. field with a null value

In JSON Schema, `required` specifies that a property must be present. It does not mean the property must be non-null. The property's type determines whether null is valid.

For example, the `note` property is allowed to be absent, but if present it must be a string:

```json
{
  "type": "object",
  "properties": {
    "note": { "type": "string" }
  }
}
```

The following payloads have different meanings:

```json
{}
```

```json
{"note": "Deliver during business hours"}
```

```json
{"note": null}
```

The first payload is valid because `note` is not required. The second payload is valid because the value is a string. The third payload is invalid because the schema does not allow null.

If a property is allowed to accept both string and null, declare a union type according to the draft in use:

```json
{
  "type": "object",
  "properties": {
    "note": {
      "type": ["string", "null"]
    }
  }
}
```

`nullable: true` is common in OpenAPI 3.0, not a standard JSON Schema keyword. When authoring pure JSON Schema, use a type union or `oneOf` appropriate to your draft.

## 5. Open, closed, and partially open content models

`additionalProperties` has a major impact on schema evolution:

| Content model | Configuration | Meaning |
|---|---|---|
| Open | Omit `additionalProperties` or set to `true` | Allows undeclared properties |
| Closed | Set `additionalProperties: false` | Rejects undeclared properties |
| Partially open | Set `additionalProperties` to a schema | Allows extra properties, but they must satisfy a type/constraint |

Open model:

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" }
  }
}
```

The schema above still accepts `{"orderId":"O-42","source":"mobile"}` because `additionalProperties` defaults to true.

Closed model:

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" }
  },
  "additionalProperties": false
}
```

This schema rejects the `source` property if it is not declared in `properties`.

Partially open model:

```json
{
  "type": "object",
  "properties": {
    "orderId": { "type": "string" }
  },
  "additionalProperties": { "type": "string" }
}
```

This schema allows extension properties, but the value of any extra property must be a string. This preserves extensibility while still controlling data types.

An open model is flexible for new fields but can hide typos or mistyped fields. A closed model catches undeclared properties early, but makes field changes more sensitive for old consumers. Choose a content model based on your actual contract and compatibility policy, not personal preference.

## 6. Schema versioning in Schema Registry

Schema Registry manages schemas by subject. With the default `TopicNameStrategy`, the value subject is typically named `<topic>-value`, and the key subject is typically `<topic>-key`.

Example for topic `orders`:

```text
orders-key
  version 1: key schema

orders-value
  version 1: OrderCreated schema v1
  version 2: OrderCreated schema v2
  version 3: OrderCreated schema v3
```

Each time a new schema is registered for the same subject, the Registry checks compatibility against the configured policy. If valid, the schema is appended to the subject's history. If invalid, registration is rejected unless an administrator intentionally changes the policy or uses an appropriate force mechanism.

The subject is the boundary for compatibility checks. If you change the subject naming strategy, the same payload may be managed under a different subject and will no longer be compared against the prior history as before. Therefore, changing a subject strategy is an architectural change that requires review.

## 7. Compatibility modes

Compatibility describes whether old and new schemas can be used together during a rollout window.

| Mode | Meaning | Question to answer |
|---|---|---|
| `BACKWARD` | Consumers using the new schema can read data written with the immediately preceding schema | Can the new consumer read old records? |
| `BACKWARD_TRANSITIVE` | New consumers can read data from all previous schema versions | Can the new consumer replay the entire history? |
| `FORWARD` | Consumers using the old schema can read data written with the latest schema | Can the old consumer read new records? |
| `FORWARD_TRANSITIVE` | Every old schema can read data written with the new schema | Can the oldest running consumer read new records? |
| `FULL` | Backward and forward compatible with the immediately preceding schema | Can both sides cross-read adjacent versions? |
| `FULL_TRANSITIVE` | Backward and forward compatible with all previous versions | Can all existing clients read one another's data? |
| `NONE` | No compatibility checking | Organization accepts the risk of breaking changes |

Confluent Schema Registry defaults to `BACKWARD` and checks only against the latest version, not the entire history. If consumers need to replay from the beginning of a topic or old data persists for a long time, consider `BACKWARD_TRANSITIVE` to validate new schemas against every prior version.

No compatibility mode replaces business testing. Two schemas can pass compatibility checks while altering field semantics, currency units, or timestamp interpretation and causing consumers to process data incorrectly.

## 8. JSON Schema compatibility depends on the content model

JSON Schema has more complex compatibility rules than simply adding or removing properties. With Confluent Schema Registry under the `STRICT` compatibility policy, the outcome also depends on whether the schema is open or closed. The tables below summarize common changes; always verify against the exact Registry version and policy you run.

### Open content model (`additionalProperties` true or omitted)

| Change | Backward | Forward | Full |
|---|---|---|---|
| Add optional property |  | Yes |  |
| Remove optional property | Yes |  |  |
| Add required property |  | Yes |  |
| Remove required property | Yes |  |  |
| Add variant to `oneOf`/union | Yes |  |  |
| Remove variant from `oneOf`/union |  | Yes |  |
| Widen scalar type (e.g. `integer` -> `number`) | Yes |  |  |
| Narrow scalar type |  | Yes |  |

### Closed content model (`additionalProperties: false`)

| Change | Backward | Forward | Full |
|---|---|---|---|
| Add optional property | Yes |  |  |
| Remove optional property |  | Yes |  |
| Add required property |  |  |  |
| Remove required property |  |  |  |
| Add variant to `oneOf`/union | Yes |  |  |
| Remove variant from `oneOf`/union |  | Yes |  |
| Widen scalar type (e.g. `integer` -> `number`) | Yes |  |  |
| Narrow scalar type |  | Yes |  |

These tables describe Confluent Registry rules under strict policy, not a claim that every JSON Schema validator implements compatibility identically. The `LENIENT` policy may apply different rules. Complex changes such as `patternProperties`, `dependencies`, `$ref`, `oneOf`, `enum`, `minimum`, or `format` must be verified via the Registry API rather than inferred solely from the change description.

An important point: if the old writer schema was open, it could have emitted undeclared properties of any type. When a new reader schema declares that property with a specific type, old data might not satisfy the new type. This is why adding a field is sometimes not backward compatible with an open model.

## 9. How to safely add an optional field?

Suppose `OrderCreated` schema v1 has `eventId`, `orderId`, and `amount`. The application wants to add `source` to know whether the order came from web or mobile.

Schema v1:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.com/orders/order-created.json",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "eventId": { "type": "string" },
    "orderId": { "type": "string" },
    "amount": { "type": "number" }
  },
  "required": ["eventId", "orderId", "amount"]
}
```

Schema v2 adds `source` without placing it in `required`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.com/orders/order-created.json",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "eventId": { "type": "string" },
    "orderId": { "type": "string" },
    "amount": { "type": "number" },
    "source": { "type": "string", "enum": ["web", "mobile", "store"] }
  },
  "required": ["eventId", "orderId", "amount"]
}
```

Consumer v2 can read old records because `source` is not required. However, consumer v1 using a closed schema will reject new records containing `source`. With a backward-compatible rollout strategy, deploy consumers supporting v2 first, then deploy producers to start emitting `source`.

With an open model, consumer v1 can accept unknown new properties, but the Registry compatibility check still needs to be run according to the specific policy. Do not assume compatibility just because `additionalProperties` defaults to true.

## 10. Why should you not add a required field immediately?

Suppose v2 puts `source` into `required`. New consumers expect this field when reading data, but old records do not have `source`. Consumer v2 may fail to read existing history. With an open model, old producers may still send payloads missing the new field; with a closed model, adding a required field can also be rejected by the Registry under strict policy.

A safe workflow is typically:

1. Add the property as optional.
2. Deploy consumers that can read both old records missing the property and new records containing it.
3. Deploy producers to start writing the property.
4. Monitor historical data and determine when all records/consumers have transitioned.
5. Only when there is an explicit major version plan should you consider making the property required or moving to a new topic/version contract.

If business logic requires the new property to always have a value, you can apply a default at the application layer. The JSON Schema `default` keyword is an annotation describing a default value; standard validators do not automatically inject that value into the payload. Either the producer or the consumer must actively apply the default.

## 11. Changing types and constraints

Changing types can be a breaking change:

```json
{"amount": 120000}
```

```json
{"amount": "120000"}
```

JSON number and string are not equivalent. A consumer parsing `amount` into `BigDecimal` may fail when the producer switches to a string. Do not use a type change to fix formatting in a single deployment.

Constraints also affect compatibility:

- Increasing `minimum` can invalidate previously valid data.
- Decreasing `maximum` can make old records invalid.
- Increasing `minLength` or decreasing `maxLength` can reject old payloads.
- Narrowing `enum` can render existing values invalid.
- Changing from `integer` to `number` widens the type under certain JSON Schema rules; the reverse narrows it.

If you need to change units, such as `amount` from VND to USD, keeping the same name and type is insufficient. Add an explicit field/currency, define semantics, or create a new event contract. Technical compatibility checks cannot detect all semantic changes.

## 12. Versioning via expand-migrate-contract

For large changes, apply three phases:

```text
EXPAND
  Add new field or new schema in a way that can coexist
       |
       v
MIGRATE
  Deploy consumers supporting both formats, then migrate producers/data
       |
       v
CONTRACT
  Retire old field when no producer/consumer depends on it
```

For example, to replace `customerName` with a `customer` object:

1. Expand: add optional `customer`, keep `customerName`.
2. Migrate: consumers read `customer` if present and fall back to `customerName`; producers write both during the transition if needed.
3. Contract: after confirming every consumer uses `customer`, stop writing and remove `customerName` in a compatibility-checked schema version.

Do not delete the old field in the very first deployment. If the field exists within Kafka's retention window, consumer replays or batch jobs may still need to read old records for days or months.

## 13. Subject naming strategy and compatibility boundaries

The subject name strategy determines under which subject a schema is registered. The default `TopicNameStrategy` uses the topic name, such as `orders-value` and `orders-key`.

Common strategies:

| Strategy | Subject boundary | When appropriate |
|---|---|---|
| `TopicNameStrategy` | One key/value subject per topic | Topic has one primary contract and compatibility is checked per topic |
| `RecordNameStrategy` | Subject by record/type name | Multiple topics share one event type and need a shared schema history |
| `TopicRecordNameStrategy` | Combines topic and record/type | One topic holds multiple event types needing independent compatibility per type in that topic |

With JSON Schema, subject naming must align across producers, consumers, and schema registration pipelines. Changing the strategy can cause the Registry to create a new subject, meaning the old compatibility history is no longer checked under the previous boundary. Treat this as a migration, not a harmless configuration tweak.

## 14. Schema ID and wire format

The Confluent JSON Schema serializer does not embed the entire schema in every Kafka record by default. The typical wire format consists of:

```text
+----------------+----------------------+----------------------+
| Magic byte     | Schema ID            | JSON payload         |
| 1 byte         | 4 bytes              | JSON bytes           |
+----------------+----------------------+----------------------+
```

The deserializer reads the schema ID, looks up the corresponding schema in Schema Registry, and then deserializes the payload. Therefore:

- Producers and consumers must be able to reach Schema Registry.
- The schema ID written in the record must remain resolvable.
- Do not delete schemas/versions still referenced by records within retention.
- When archiving/migrating records to another system, note that records depend on the Registry to be decoded.

This specific wire format belongs to the Confluent serializer; the Kafka broker only stores bytes and does not validate JSON Schema itself.

## 15. Using JSON Schema SerDes with Spring Kafka

If your application uses Confluent Schema Registry, add the JSON Schema serializer dependency compatible with your running Confluent Platform/Schema Registry. Maven example:

```xml
<dependency>
    <groupId>io.confluent</groupId>
    <artifactId>kafka-json-schema-serializer</artifactId>
    <version>${confluent.version}</version>
</dependency>
```

Ensure Maven declares the Confluent repository and select a version compatible with your project's Kafka client and Spring Boot. Do not arbitrarily pick the latest version if it pulls in an incompatible Kafka client version against existing dependency management.

Producer/consumer configuration in Spring Boot:

```yaml
spring:
  kafka:
    bootstrap-servers: localhost:9092
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaSerializer
      properties:
        "[schema.registry.url]": http://localhost:8081
        "[auto.register.schemas]": false
        "[json.fail.invalid.schema]": true
    consumer:
      group-id: order-projection
      auto-offset-reset: earliest
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.json.KafkaJsonSchemaDeserializer
      properties:
        "[schema.registry.url]": http://localhost:8081
        "[json.value.type]": com.example.orders.OrderCreated
        "[json.fail.invalid.schema]": true
```

`json.value.type` tells the deserializer the target Java type. Without a specific type configured, the deserializer may return a `LinkedHashMap` for JSON objects or a `JsonNode` if configured accordingly. For multiple event types in the same topic, design type resolution/`oneOf`/schema references instead of forcing all records into a single class.

`json.fail.invalid.schema=true` instructs the serializer/deserializer to fail when a payload violates the schema; Confluent documentation notes the default for this property is `false`. Enable it explicitly if client-side validation is needed and test the error path as well. Schema Registry compatibility checking at registration time and payload validation at serialization time are two distinct steps.

## 16. Distinguishing Jackson JsonSerializer from KafkaJsonSchemaSerializer

| Criterion | Spring Kafka `JsonSerializer` | Confluent `KafkaJsonSchemaSerializer` |
|---|---|---|
| Converts Java objects to JSON | Yes | Yes |
| Uses Jackson | Yes | Can use Jackson for object mapping |
| Registers/looks up schemas in Schema Registry | Not automatically | Yes |
| Schema ID in wire format | No | Yes |
| Compatibility check on schema registration | No | Can use Schema Registry |
| JSON Schema validation | Requires a separate validator if needed | Can be enabled via JSON Schema SerDes config |
| Depends on Schema Registry | No | Yes |

If the project only needs JSON payloads and contracts are managed via code/tests separately, the Jackson serializer may suffice. If you need the Registry to manage schema versions, schema IDs, and compatibility across multiple services, use Registry-aware serializers/deserializers.

Do not configure `KafkaJsonSchemaSerializer` and assume every payload is automatically strictly validated. Verify `json.fail.invalid.schema`, auto registration, subject strategy, and the actual schema the serializer is using.

## 17. Auto registration and schema release workflow

`auto.register.schemas` determines whether the serializer automatically registers a schema when encountering one not yet present in the subject.

| Configuration | Behavior |
|---|---|
| `auto.register.schemas=true` | Serializer can register a schema inferred from the object; convenient for local/dev, but runtime producers may create versions outside the release process |
| `auto.register.schemas=false` | Schema must be pre-registered or the serializer must be configured to use an existing schema version |
| `use.latest.version=true` | When auto registration is off, the serializer can use the subject's latest schema version; ensure the object conforms to that schema |
| `latest.compatibility.strict=true` | When using latest version, checks compatibility between the latest schema and the schema inferred from the object before serializing |

In production, it is usually best to register schemas in CI/CD before rolling out producers, then disable auto registration so individual instances do not create versions. However, using `use.latest.version` must be designed carefully: the serializer may use the latest schema instead of the schema derived from the object, so the Java model and Schema Registry must stay in sync.

Do not set `latest.compatibility.strict=false` merely to suppress errors. Only use it when schema references or intentional differences are well understood and tests prove the payload is valid.

## 18. Compatibility checks in CI/CD

Before merging or releasing a new schema, invoke Schema Registry's compatibility API. Example checking a candidate schema against the latest version of subject `orders-value`:

```bash
curl -X POST \
  http://localhost:8081/compatibility/subjects/orders-value/versions/latest \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  -d '{
    "schemaType": "JSON",
    "schema": "{\"type\":\"object\",\"additionalProperties\":false,\"properties\":{\"orderId\":{\"type\":\"string\"},\"amount\":{\"type\":\"number\"},\"source\":{\"type\":\"string\"}},\"required\":[\"orderId\",\"amount\"]}"
  }'
```

The response `{"is_compatible":true}` indicates that the candidate schema is compatible with the checked version under the current policy. If `false`, the pipeline should halt and require review. With standard `BACKWARD`, the API compares against the latest version; if full history checks are needed, configure transitive compatibility or run checks against individual versions.

After passing, the pipeline can register the schema via the corresponding subject versions endpoint. Producers should be released only after the schema exists and consumers have been deployed in the chosen rollout order.

## 19. Schema references and multiple event types in one topic

If a topic carries multiple event types, you can use `oneOf` to describe the accepted set of schemas and `$ref` to reuse registered schemas:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderEvents",
  "oneOf": [
    { "$ref": "OrderCreated.schema.json" },
    { "$ref": "OrderCancelled.schema.json" }
  ]
}
```

With Confluent Schema Registry, schema references must be registered and declared in the schema registration request. `$ref` pointing to a Registry reference must match the registered reference name; do not assume every external HTTP URL is automatically resolved by the Registry.

In a multi-event-type model, the serializer may need `auto.register.schemas` disabled and `use.latest.version` enabled so it uses the registered `oneOf` union schema rather than registering each class's individual schema and overwriting the subject's latest version. Follow the documentation for your exact Registry version and test each event type.

If a topic contains only one event type, a dedicated schema/subject for that event is usually simpler. Do not add `oneOf` unless there is a real need.

## 20. Rolling out producers and consumers by compatibility

For backward-compatible changes, the typical rollout order is consumers first, producers second:

```text
1. Register schema v2
2. Deploy consumer able to read v1 and v2
3. Confirm new consumer runs stably
4. Deploy producer writing payload according to v2
5. Monitor validation, deserialization, and business metrics
6. Stop supporting old field after migration period ends
```

For forward-compatible changes, producers may need to go first or old consumers must be guaranteed able to read new payloads. Clearly verify the Registry's backward/forward definitions and your actual deployment topology; do not apply one rollout order across every mode.

If producers and consumers are deployed independently, maintaining a coexistence phase is mandatory. For breaking changes, consider a new topic such as `orders.v2` or a new event type/version instead of modifying the contract in place and hoping every consumer upgrades simultaneously.

## 21. Testing schema evolution

Tests should cover schemas, payloads, and application versions:

| Scenario | Check |
|---|---|
| Payload conforms to current schema | Serializes/deserializes successfully |
| Missing required property | Validation fails clearly |
| Property has wrong type | Validation fails without silent coercion |
| Extra property with closed model | Payload is rejected if the field is undeclared |
| Extra property with open model | Payload is accepted according to schema and policy |
| New optional field absent | New consumer still reads old records |
| New optional field present | Old consumer behaves according to chosen content model/compatibility |
| Enum/type/constraint changes | Registry compatibility check returns expected outcome |
| New schema against all historical schemas | Transitive check passes when full history replay is required |
| Missing schema ID | Deserializer reports clear Registry error |
| Registry unavailable | Producer/consumer handles dependency outage per policy |
| Old records after rollout | New consumer reads records within retention |

Consider running a test Schema Registry via Testcontainers or a dedicated CI environment to verify both the compatibility API and serializers/deserializers. Unit tests with a standalone validator do not replace Registry compatibility checks because the Registry has its own policies and compatibility algorithms.

## 22. Common errors and troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| Message is valid JSON but deserialization fails | JSON does not satisfy schema or Java type mismatches | Check schema ID, schema version, required/type, and `json.value.type` |
| Registry rejects schema registration | Change violates subject compatibility policy | Run compatibility check, review open/closed model, choose suitable migration |
| Consumer cannot find schema ID | Schema was deleted or Registry lacks the corresponding schema | Restore schema, check retention/cleanup and Registry endpoint |
| Serializer creates multiple schema versions | `auto.register.schemas=true` across runtimes | Register schemas via release pipeline and consider disabling auto registration |
| Consumer receives `LinkedHashMap` instead of POJO | JSON value type not configured | Set `json.value.type` or intentionally accept `JsonNode`/Map |
| New field rejected by old consumer | Consumer uses a closed schema | Deploy compatible consumers before producers emit the new field |
| Missing new field causes errors | Field added to `required` or code lacks fallback | Keep optional during migration and handle defaults in application code |
| `format` does not catch malformed date-times | Validator does not enable format assertion | Configure validator or validate format at application layer |
| Changing subject strategy creates separate version history | Subject name changed | Review subject migration and register schemas for the new subject intentionally |
| Schema Registry unreachable | Wrong URL, TLS, credentials, or network issue | Check `schema.registry.url`, security properties, and connectivity |

## 23. Schema version management workflow

1. Define the event contract and JSON Schema in source control.
2. Set `$schema` to a dialect supported by Schema Registry.
3. Choose a stable `$id` and use `$ref` for reusable structures when needed.
4. Select an open, closed, or partially open model based on payload control needs.
5. Define the subject naming strategy and compatibility mode.
6. Create payload fixtures for old and new schemas.
7. Run validators and the Schema Registry compatibility API in CI.
8. Register the new schema through a controlled pipeline.
9. Roll out consumers/producers in the chosen backward or forward order.
10. Monitor serialization, deserialization, schema lookup, and business validation errors.
11. Remove old fields/schemas only when retention, replay jobs, and old consumers no longer depend on them.
12. Record schema history and migration decisions for auditability and reproducibility.

## 24. Common misconceptions

| Misconception | Accurate understanding |
|---|---|
| `$schema` is the event version | `$schema` specifies the JSON Schema dialect |
| `$id` auto-increments on registration | `$id` identifies the schema; the Registry manages subject versions separately |
| Schema ID equals subject version | Schema ID and version are two distinct identifiers |
| Parseable JSON means contract compliance | JSON can be syntactically valid yet violate types, required fields, or constraints |
| Adding a field is always backward compatible | Outcome depends on content model and Registry policy |
| Optional means nullable | Optional means allowed to be absent; null requires an explicit type declaration |
| `default` auto-populates values during validation | `default` is typically an annotation; applications must apply it if needed |
| Jackson `JsonSerializer` uses Schema Registry automatically | Jackson serializer does not register JSON Schemas or write schema IDs |
| `BACKWARD` checks all old schemas | `BACKWARD` defaults to checking only the latest version; transitive checks full history |
| Passing compatibility guarantees correct business behavior | You still need to verify semantics, ordering, units, enums, and actual rollout |

## Checklist before releasing a new JSON Schema

- `$schema` points to a draft supported by both Registry and validator.
- `$id` is stable and not confused with schema version or event version.
- `type`, `properties`, `required`, `enum`, `format`, and numeric/string constraints accurately reflect the contract.
- Decisions on absent properties vs. null values are documented.
- `additionalProperties` is chosen deliberately; implications of open/closed models are understood.
- Subject naming strategy and compatibility mode are agreed upon.
- Compatibility check has been run against a real Registry or equivalent environment.
- Transitive compatibility is verified if consumers must replay the entire history.
- Schema is registered before producers emit payloads under the new version.
- Consumers are rolled out in the proper backward/forward sequence.
- `auto.register.schemas` fits the release process; production does not generate uncontrolled versions.
- Confluent JSON Schema SerDes and Schema Registry URL/type mappings are configured accurately in Spring Kafka.
- Valid payloads, missing fields, nulls, wrong types, extra fields, and old schemas are tested.
- Schema IDs/versions still referenced by records within Kafka retention are not deleted.
- Logs/metrics exist for schema lookup failures, validation failures, and compatibility rejections.

JSON Schema helps define the event contract; Schema Registry helps manage history and verify compatibility when the contract evolves. By properly distinguishing dialects, `$id`, subject versions, and schema IDs, choosing the right content model, checking compatibility in CI, and rolling out consumers and producers in order, Spring Kafka services can read data across multiple versions without requiring simultaneous deployments.

## References

- [JSON Schema – Understanding JSON Schema](https://json-schema.org/understanding-json-schema/)
- [Confluent – JSON Schema Serializer and Deserializer](https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/serdes-json.html)
- [Confluent – Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html)
- [Confluent – Formats, Serializers, and Deserializers](https://docs.confluent.io/platform/current/schema-registry/fundamentals/serdes-develop/index.html)
