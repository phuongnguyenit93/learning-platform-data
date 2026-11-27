# Choosing JSON, Avro, or Protobuf Based on Interoperability Requirements

In event-driven systems, producers and consumers may be developed in different languages, deployed at different times, and managed by different teams. Therefore, payloads need a clear contract: both sides must share the same understanding of field semantics, data type representations, and versioning rules. JSON, Avro, and Protobuf can all be used to exchange events, but they address different priorities.

JSON is often convenient when direct human readability and broad integration are needed. Avro fits systems with managed schemas that need compact binary payloads and cross-version compatibility mechanisms. Protobuf fits when you want strongly typed contracts, code generation, and efficient binary payloads across multiple languages. There is no single best format for all situations; the choice should be based on interoperability requirements, rate of schema change, operational capabilities, and the technology ecosystem.

## 1. What Does a Message Contract Include?

The serialization format is only part of a contract. Before choosing JSON, Avro, or Protobuf, define:

- **Event name and meaning:** `OrderCreated` means an order has been created successfully, not a request to create an order.
- **Payload and data types:** which fields are required, which may be absent, measurement units, null rules, and value constraints.
- **Identifiers and timestamps:** `eventId`, `orderId`, `occurredAt`, and `correlationId` help with deduplication, business ordering, and tracing.
- **Schema version:** how older consumers will react when the producer adds fields or changes structure.
- **Compatibility rules:** whether older consumers are allowed to read new data, whether new producers' consumers can read old data, and who is responsible for approving changes.
- **Serialization mechanism:** media type, serializer, deserializer, or message converter used by both sides.

A broker only transports bytes and metadata. The broker does not inherently know that a `total` field is currency, `orderId` is an identifier, or what `eventType` means. Producers and consumers must agree on the contract beyond simply connecting to the same destination.

## 2. Comparing JSON, Avro, and Protobuf

| Criterion | JSON | Avro | Protobuf |
|---|---|---|---|
| Data form | Structured text | Binary, schema defined in JSON | Binary, schema defined in `.proto` files |
| Direct readability | High | Low when inspecting binary payloads | Low when inspecting binary payloads |
| Data typing | Flexible; requires schema or validation to constrain | Data types described in schema | Strongly typed, with code generated from schema |
| Size and speed | Usually larger due to field names and text characters | Usually compact, efficient for high-volume streams | Usually compact, efficient for binary exchange |
| Schema evolution | Requires conventions and validation | Has writer schema / reader schema rules | Based on field numbers and compatibility rules |
| Tooling | Very ubiquitous across web and APIs | Popular in data and streaming ecosystems | Popular in polyglot systems and RPC |
| Best suited when | Easy integration, observability, moderate load | Schema registry and data version management needed | Strong typed contracts, generated code, and compact payloads needed |

Observations about size and speed are general trends, not absolute guarantees. Actual results depend on data structure, serializer, compression, batch size, language, and implementation. Measure with real payloads before making decisions based on generic benchmarks.

## 3. JSON: Easy Integration and Observability

JSON represents objects using field name and value pairs. Humans can read payloads directly in logs, command-line tools, or broker management UIs:

~~~json
{
  "eventId": "evt-7f31",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-1001",
  "customerId": "CUS-204",
  "totalMinorUnits": 12550,
  "currency": "VND",
  "occurredAt": "2026-11-24T09:30:00Z"
}
~~~

Advantages of JSON:

- Nearly every language and platform has libraries to read and write JSON.
- Easy to inspect during development and integrate with REST APIs and observability tools.
- Fields can be added while many parsers continue reading if consumers ignore unknown fields.
- Does not require every consumer to generate code from a schema before reading payloads.

JSON does not provide contract checking on its own. A payload can be syntactically valid yet business-invalid, such as `totalMinorUnits` being a string instead of a number or `currency` being missing. Use JSON Schema, application-level validation, or contract tests to verify types, required fields, and value constraints.

Example JSON configuration for a Spring Cloud Stream binding:

~~~yaml
spring:
  cloud:
    function:
      definition: publishOrder
    stream:
      bindings:
        publishOrder-out-0:
          destination: orders.created
          content-type: application/json
~~~

With content type `application/json`, Spring Cloud Stream can use an appropriate message converter to convert Java objects to JSON on publish and JSON to Java types on receipt. Consumers still need to validate payloads and apply compatibility rules. Do not assume that setting `content-type` alone provides schema validation.

JSON fits when services need fast integration, payloads are not overly large, observability is important, and teams can maintain field conventions alongside contract tests. When streams carry very high throughput or schemas evolve in complex ways, evaluate the added cost of payload size, parsing, and contract management.

## 4. Avro: Explicit Schemas and Binary Data

Avro is a schema-based serialization format. A schema describes record names, fields, and data types. Data is binary-encoded so it does not repeat field names like JSON. In streaming systems, producers and consumers typically use a schema registry or a schema distribution mechanism to look up the right schema for a message.

Example Avro schema for an `OrderCreated` event:

~~~json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.orders",
  "fields": [
    { "name": "eventId", "type": "string" },
    { "name": "orderId", "type": "string" },
    { "name": "customerId", "type": "string" },
    { "name": "totalMinorUnits", "type": "long" },
    { "name": "currency", "type": "string", "default": "VND" }
  ]
}
~~~

Avro has two core concepts:

- **Writer schema:** the schema the producer uses to encode the record.
- **Reader schema:** the schema the consumer uses to read the record.

When the writer schema and reader schema differ, Avro can resolve differences according to schema resolution rules. For example, the reader can supply a default value for a new field that an older writer did not send. Compatible reading depends on the specific change and how schemas are distributed.

### Schema Evolution with Avro

Suppose the initial version only has `eventId`, `orderId`, and `totalMinorUnits`. The next version adds `currency` with a default of `VND`. New consumers can read old records and use the default value if the schema is designed properly. In Avro, the `default` in the reader schema is used when a record created by an older writer lacks that field; it does not automatically force producers to write the default value into every record. Adding a field without a default may prevent a new reader from reading old data because old records lack that field.

When renaming fields, consider `aliases` so the reader schema recognizes the old name. When changing data types, check Avro's type promotion rules and test reading both old and new data. Do not treat adding a `default` as a universal fix for every incompatible change; determine the exact writer schema, reader schema, and deployment order.

### Schema Registry

A schema registry stores schemas and their versions and can enforce compatibility policies such as backward, forward, or full. Serializers typically register or look up a schema, then write schema identification metadata into the payload according to the ecosystem's conventions. Consumers use that information to retrieve the matching schema before decoding.

A registry is not a broker and does not replace destinations. The broker stores and transports messages; the registry manages schema contracts. How a schema ID is attached to a message depends on the chosen serializer and registry, not a single universal format mandated across all brokers.

Avro fits when multiple teams produce/consume events, controlled version management is required, payloads are large or size optimization matters, and teams have the operational capability to run a registry.

## 5. Protobuf: Strongly Typed Contracts and Code Generation

Protocol Buffers (Protobuf) defines messages in `.proto` files. The `protoc` tool generates classes and serialization code for target languages. Each field has a name, a type, and a field number; binary payloads encode using field numbers rather than repeating field names.

Example:

~~~protobuf
syntax = "proto3";

package orders.v1;

message OrderCreated {
  string event_id = 1;
  string order_id = 2;
  string customer_id = 3;
  int64 total_minor_units = 4;
  string currency = 5;
  int64 occurred_at_epoch_millis = 6;
}
~~~

In this example, `total_minor_units` stores the monetary amount in the smallest unit of the currency, avoiding binary floating-point numbers for money calculations. For VND, the smallest unit may be dong; for currencies with fractional parts, clearly specify the scale in the contract. `occurred_at_epoch_millis` represents the timestamp in epoch milliseconds; both sides must agree on time zone and units.

### Protobuf Evolution Rules

Field numbers are part of the wire format. When removing a field, never reuse old field numbers or names. Use `reserved` to mark them:

~~~protobuf
message OrderCreated {
  reserved 7;
  reserved "legacy_note";

  string event_id = 1;
  string order_id = 2;
  string customer_id = 3;
  int64 total_minor_units = 4;
  string currency = 5;
  int64 occurred_at_epoch_millis = 6;
}
~~~

Key principles:

- Add new fields with previously unused field numbers.
- Do not change the field numbers of already published fields.
- Do not reuse numbers or names of removed fields; mark them `reserved`.
- Avoid changing field types if the wire type or semantics may change.
- Check field presence when distinguishing an unset field from a field holding its default value.
- Maintain compatibility rules across generated code versions.

Protobuf supports unknown fields during decoding in many runtimes, enabling older consumers to skip new fields. However, wire compatibility does not equal business compatibility: an older consumer can read the message yet fail to understand the semantics of a new field. Check the behavior of the `protoc` version and runtime you use.

Protobuf fits when contracts require strong typing, multiple languages, generated code, compact payloads, and teams have a workflow for managing `.proto` files. Inspecting payloads requires decoding tools and the corresponding schemas; raw binary logs are not as convenient as JSON.

## 6. Choosing a Format Based on Interoperability Requirements

You can use the following questions to make a decision:

| Question | JSON | Avro | Protobuf |
|---|---|---|---|
| Do consumers need to read payloads directly? | Very suitable | Requires decoding tools | Requires decoding tools |
| Are there multiple teams needing centralized schema management? | Possible, with JSON Schema and a suitable registry | Very suitable | Possible, with a schema repo and `.proto` workflow |
| Is strongly typed code generation required? | Depends on tooling | Code generation tools available | Core strength |
| Do you need to exchange with web APIs and common tools? | Very convenient | Requires an integration layer | Requires an integration layer |
| High throughput, wanting compact binary payloads? | May need compression/benchmarking | Suitable | Suitable |
| What ecosystem do teams already have? | JSON tooling | Avro/registry | Protobuf/protoc |

Some typical scenarios:

- **Business services and dashboards needing easy payload inspection:** start with JSON, adding JSON Schema or contract tests for validation.
- **Kafka event platforms with many producers/consumers and a registry:** consider Avro if teams already operate a schema registry and need schema resolution.
- **Polyglot systems, strict API contracts, or services already using Protobuf for RPC:** use Protobuf for message streaming if the binder and serializer are well integrated and tested.
- **Integrating with external partners:** choose a format the partner reliably supports, then define schema versioning and change processes before release.

Do not pick a format solely because its payload is smaller in a single benchmark. Account for schema management, code generation, debugging, integration, concurrent deployments, and supporting older consumers.

## 7. Integrating Serializers and Converters in Spring Cloud Stream

Spring Cloud Stream allows business functions to work with Java objects or `Message<T>`. Converting objects to bytes and vice versa can be performed by Spring Cloud Stream's message converter or by the binder's serializer/deserializer.

### Using JSON via Message Converter

With JSON, you can usually declare the content type and let the message converter handle conversion:

~~~yaml
spring:
  cloud:
    function:
      definition: validateOrder
    stream:
      bindings:
        validateOrder-in-0:
          destination: orders.created
          group: order-validator
          content-type: application/json
        validateOrder-out-0:
          destination: orders.validated
          content-type: application/json
~~~

The function can receive `OrderCreated` and return `OrderValidated`. The Java types and converter determine how JSON is mapped. Verify required fields, numeric types, date/time formats, and unknown field handling using contract tests.

### Using Avro or Protobuf

With Avro and Protobuf, the application needs a serializer/deserializer or message converter that understands the corresponding format. There are two common integration approaches:

1. Use Spring's message converter to convert between objects and payloads according to the configured content type.
2. Use the binder/client's native serialization, where the Kafka client or broker library is responsible for encoding and decoding payloads.

Conceptual example using Kafka binder native encoding:

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        orders-out-0:
          destination: orders.created
        orders-in-0:
          destination: orders.created
          group: order-consumer
      kafka:
        bindings:
          orders-out-0:
            producer:
              use-native-encoding: true
          orders-in-0:
            consumer:
              use-native-decoding: true
~~~

When enabling native encoding/decoding, configure the corresponding serializer and deserializer for the Kafka client, along with the registry or schema source if the format requires one. Serializer class names, registry properties, and configuration namespaces depend on the chosen library. For example, Avro can use a serializer integrated with a schema registry; Protobuf can use a serializer/deserializer matching the message classes generated by `protoc`.

Setting `content-type` does not automatically turn a Java payload into Avro or Protobuf. Content type describes the format; the serializer or converter performs the actual encoding. Likewise, do not enable native decoding while expecting another converter to decode the same payload without understanding the binder's processing order.

For RabbitMQ or Pulsar, configuring serializers and message properties can differ from Kafka. Consult the exact version's binder documentation, verify how content type/schema metadata are propagated, and confirm consumers receive the expected data types. Do not copy Kafka configuration verbatim to other binders.

## 8. Organizing Schema Versions and Deploying Producers/Consumers

Compatibility rules must align with real-world deployment schedules. Producers and consumers are not upgraded simultaneously in many distributed systems. A safe workflow typically includes:

1. Propose the schema change and classify it: field addition, removal, rename, type change, or semantic change.
2. Check the chosen compatibility rules and run tests against schemas of currently deployed versions.
3. Deploy consumers capable of reading both old and new data if phased migration is needed.
4. Deploy the new producer after relevant consumers are ready.
5. Monitor decoding errors, validation failures, and message rates going to retry/DLQ.
6. Only remove old fields or schemas after confirming no consumers still rely on them and old retained data has expired.

For incompatible changes, consider a new destination or a new event type/version, such as `orders.created.v2`. Do not change the meaning of an existing field within the same schema version merely to avoid creating a new version. A `total` field changing from dong to thousands of dong is a semantic change even though the data type remains numeric.

## 9. Contract Testing

Unit testing a single function is not enough to confirm two services understand the same schema. Combine:

- **Schema validation:** verify payloads or schemas are syntactically and type-wise valid.
- **Compatibility tests:** check the new schema against the producer/consumer versions that must be supported.
- **Serialization round-trip:** encode then decode payloads and compare critical data.
- **Cross-language tests:** when multiple languages are involved, produce a message in one runtime and decode it in another.
- **Spring Cloud Stream test binder:** test bindings, payloads, and headers at the application level.
- **Broker integration tests:** verify serializers, deserializers, registry, native encoding/decoding, and actual binder behavior.

For Avro, test writer schemas and reader schemas against registry policies. For Protobuf, verify field numbers, `reserved` directives, and code generated from `.proto` versions. For JSON, verify JSON Schema or validation logic and confirm whether consumers ignore or handle new fields as specified by the contract.

## 10. Checklist Before Finalizing a Format

Before launching a new event stream, development teams should agree on:

- Which producer and consumers own the contract?
- Which formats are supported by the participating languages and platforms?
- Is a schema registry, schema repository, or automated code generation needed?
- Which backward, forward, or full compatibility rules apply?
- How are missing fields, null fields, unknown fields, and default values handled?
- Which serializers, deserializers, or converters are used in each binder?
- How are content type and schema metadata propagated?
- How are old data, new data, and skewed-version deployments tested?
- Who monitors decoding errors and handles failed messages?

JSON enables a fast start and easy observability. Avro provides schemas with writer/reader resolution helpful for data platforms. Protobuf provides strongly typed contracts and multi-language code generation. When selecting a format, prioritize interoperability requirements and long-term operability across all producers and consumers; then configure serializers or converters properly for the binder in Spring Cloud Stream and test contracts across versions.
