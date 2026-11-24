# Schema Registry in Operations

In a Kafka system, brokers store **bytes** for keys, values, and headers without understanding business fields like `orderId`, `amount`, or `createdAt`. When data is exchanged using Avro, Protobuf, or JSON Schema, producers and consumers must agree on how messages are encoded, decoded, and evolved structurally. **Schema Registry** is a service that manages schemas, versions, and compatibility rules, allowing applications to evolve independently while reducing the risk of a deployment preventing consumers from deserializing data.

From the **Spring Kafka Reliability Operations** perspective, Schema Registry is not just a place to store schema files. It is also a **runtime dependency at startup or when encountering an uncached schema**, a control boundary for data changes, and a component that must be monitored when troubleshooting consumer incidents. If you only check whether a pod is `Ready` without observing deserialization errors, schema registrations, and consumer lag, an incompatible schema change can still stall processing or push large volumes of records into the DLT.

This lesson uses **Confluent Schema Registry and compatible serializers/deserializers** as examples. Other registry products may support different APIs, subject identifiers, or wire formats; do not assume every Schema Registry uses identical mechanics.

## 1. Components in the data flow

A typical architecture:

```text
                    +-------------------------+
                    |     Schema Registry     |
                    | subject / version / id  |
                    | compatibility policy    |
                    +------------+------------+
                                 ^
                         lookup / register
                                 |
     +------------------+        |        +---------------------+
     | Producer         |--------+        | Spring Kafka        |
     | KafkaAvro        |                 | KafkaAvro           |
     | Serializer       |                 | Deserializer        |
     +--------+---------+                 +----------+----------+
              |                                      ^
              | bytes + schema ID                    | bytes
              v                                      |
        +-----+--------------------------------------+-----+
        |            Kafka topic: orders                  |
        | partition 0 | partition 1 | partition 2         |
        +------------------------------------------------+
```

The producer uses a schema to serialize records and may register or look up the schema ID in the Registry. Kafka brokers store the encoded records. The consumer receives bytes, reads the schema ID metadata per the serializer's wire format, looks up the matching schema when needed, and deserializes into the object or structure handled by the listener.

**Key takeaway:** Kafka brokers can usually still store and deliver records when the Registry has an outage. However, producers or consumers can fail if they need to register/look up a schema while unable to reach the Registry. That is why a Schema Registry outage can surface as application errors or consumer lag even when Kafka brokers remain healthy.

## 2. Schema, subject, version, and schema ID

Four concepts to distinguish:

| Concept | Operational meaning |
|---|---|
| **Schema** | Data structure definition: field names, types, encoding rules, and metadata. |
| **Subject** | Namespace for managing versions and compatibility rules of a schema lineage. |
| **Version** | Sequential version number within **a single subject**, e.g., 1, 2, 3. |
| **Schema ID** | Schema identifier issued by the Registry; serializers can embed the ID in messages so consumers fetch the schema. |

Example:

```text
Subject: orders-value
  version 1 -> schema ID 101
  version 2 -> schema ID 117
  version 3 -> schema ID 125

Topic: orders
  partition 0:
    record A -> schema ID 101
    record B -> schema ID 117
    record C -> schema ID 125
```

The IDs in the example are illustrative. **Version is not schema ID**: version belongs to a subject's history, while ID identifies schema content under the Registry's scheme. One schema can be referenced across multiple subjects or versions, so never deduce `schema ID = version`.

With the traditional wire format of the **Confluent Avro serializer**, the payload typically starts with a magic byte and a four-byte schema ID, followed by the encoded data. The consumer uses the ID to look up the writer schema. **This is Confluent's wire-format convention**, not a universal rule for all Kafka messages, not plain JSON, and not inserted by the broker. For Protobuf and other formats, accompanying metadata headers have additional specifics.

## 3. Subject naming strategies affect operability

Under the common default configuration of Confluent serializers, the value schema for topic `orders` is managed under subject `orders-value`, and the key schema under `orders-key`.

Common strategies:

| Strategy | Idea | Notes |
|---|---|---|
| `TopicNameStrategy` | Subject scoped by topic and key/value, e.g., `orders-value`. | Record types sharing a subject must satisfy that subject's compatibility rules. |
| `RecordNameStrategy` | Subject based on the record's full name. | Allows record-centric schema modeling, yet requires producers and consumers to align on strategy. |
| `TopicRecordNameStrategy` | Subject combines topic and record name. | Separates compatibility per record within a topic's scope. |

Subject names do not automatically reveal the physical topic if the system changed strategies. When troubleshooting `subject not found` errors or schemas registered in the wrong place, check **topic, key/value side, and subject naming strategy**, not just one guessed subject name.

Changing the strategy across application versions is a data-protocol change, not a simple rename. It can cause producers to register schemas under a new subject and invalidate CI/CD pipelines, Registry permissions, or contract checks.

## 4. Compatibility is a deployment contract between versions

The Registry can validate a new schema against a subject's schema history upon registration. Common modes:

| Mode | Core meaning |
|---|---|
| `BACKWARD` | Readers using the **new** schema can read data written with the **previous** schema. |
| `FORWARD` | Readers using the **previous** schema can read data written with the **new** schema. |
| `FULL` | Combines backward and forward. |
| `NONE` | No compatibility checking required. |
| `BACKWARD_TRANSITIVE`, `FORWARD_TRANSITIVE`, `FULL_TRANSITIVE` | Checks against **all prior versions**, not just the latest one. |

For example with Avro, first version:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "amount", "type": "long" }
  ]
}
```

A new version wants to add an optional note:

```json
{
  "type": "record",
  "name": "OrderCreated",
  "namespace": "com.example.events",
  "fields": [
    { "name": "orderId", "type": "string" },
    { "name": "amount", "type": "long" },
    {
      "name": "note",
      "type": ["null", "string"],
      "default": null
    }
  ]
}
```

Field `note` with default `null` lets new readers process old records lacking that field. This is a common way to evolve schemas in a backward-compatible manner. Conversely, deleting a required field or making an incompatible type change may be rejected by the Registry depending on policy.

**Deployment order also matters.** With backward compatibility, teams can usually deploy new consumers first to read old data, then deploy producers emitting new data. If multiple application versions run in parallel, verify requirements for old readers reading new writers as well; checking one direction alone may not suffice. Exact compatibility rules differ across Avro, Protobuf, and JSON Schema; never mechanically apply Avro examples to every format.

## 5. Compatibility policies do not replace contract tests

Schema-level compatibility checks read/write capability against schema definitions; it **does not understand full business semantics**. For instance, field `status` remains `string`, yet the producer starts sending `REFUNDED` before old consumers support it; the schema may still pass compatibility while listeners throw exceptions.

Defense layers to combine:

1. **Schema compatibility checks:** validate syntax and compatibility before registration.
2. **Contract tests:** verify consumers handle key values and business conventions.
3. **Integration tests:** use real serializers/deserializers and a test Registry.
4. **Controlled rollouts:** deploy in an agreed order while watching deserialization errors and consumer lag.
5. **DLT/recovery:** retain evidence of unprocessable records without silently losing data.

The Registry can block incompatible schemas from being registered **through checked registration APIs**. However, if a producer crafts malformed bytes directly or embeds a wrong schema ID, the broker does not validate payload correctness on its own.

## 6. Configuring Spring Boot with Confluent Avro

Example service both publishing and consuming Avro events whose generated class is `OrderCreated`:

```yaml
spring:
  kafka:
    bootstrap-servers: kafka:9092
    properties:
      "[schema.registry.url]": "http://schema-registry:8081"
    producer:
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: io.confluent.kafka.serializers.KafkaAvroSerializer
      properties:
        "[auto.register.schemas]": false
    consumer:
      group-id: order-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: io.confluent.kafka.serializers.KafkaAvroDeserializer
      properties:
        "[specific.avro.reader]": true
```

Properties under `spring.kafka.properties` apply globally as Spring Boot constructs client properties; producer/consumer properties can override by scope. Brackets `"[... ]"` in the YAML example preserve dots in configuration map keys; do not pass brackets literally to the Kafka client. In your application, use the Spring Boot syntax matching your running version.

`KafkaAvroSerializer` and `KafkaAvroDeserializer` come from Confluent libraries, requiring appropriate dependencies in the build. Spring Kafka does not automatically pull these serializers merely because a Registry URL is declared. If you want listeners to receive generated Avro classes (`SpecificRecord`), `specific.avro.reader=true` selects the specific reader; otherwise it typically returns `GenericRecord`.

When setting `auto.register.schemas=false` on producers, schemas must already be pre-registered matching the subject naming strategy and serializer configuration. This mode fits setups where CI/CD is the sole authority allowed to register production schemas. If the corresponding schema is absent, the producer can fail during serialize/send; never enable this mode without establishing a pre-deployment schema registration step.

## 7. Adding ErrorHandlingDeserializer for consumers

Deserialization errors happen during `poll()`, **before the listener is invoked**. Therefore, `try/catch` inside `@KafkaListener` cannot catch errors like nonexistent schema IDs, malformed payloads, or deserializer incompatibility.

Spring Kafka provides `ErrorHandlingDeserializer` to turn deserialization failures into metadata that the listener container/error handler can handle. Wrap the Confluent deserializer like this:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-service
      enable-auto-commit: false
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.springframework.kafka.support.serializer.ErrorHandlingDeserializer
      properties:
        "[spring.deserializer.value.delegate.class]": io.confluent.kafka.serializers.KafkaAvroDeserializer
        "[schema.registry.url]": "http://schema-registry:8081"
        "[specific.avro.reader]": true
```

If keys are also Avro-encoded or use a format prone to deserialization failures, wrap the key deserializer similarly. `ErrorHandlingDeserializer` attaches error details in headers following Spring Kafka's protocol and lets the container pass failed records to the error handler instead of letting `poll()` failures stall consumer progress unpredictably.

Example registering `DefaultErrorHandler` with a DLT recoverer:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    return new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 2L)
    );
}
```

Deserialization exceptions generally belong to the category that **should not be retried continuously with the same bytes**; many `DefaultErrorHandler` versions classify related exceptions as fatal/non-retryable by default. Verify your actual classifier. A schema ID lookup failure caused by a temporarily down Registry warrants a different strategy than permanently corrupted payloads; avoid pushing every record to the DLT prematurely if the root cause is a system-wide dependency outage.

**Especially for deserialization-error DLTs:** the value may need to be republished as raw bytes rather than `OrderCreated`. The DLT producer must have serializers supporting the data types received; you can use `DelegatingByTypeSerializer`, multiple `KafkaTemplate`s, or appropriate recovery configuration. If the DLT serializer accepts only Avro objects while the recoverer emits `byte[]`, DLT publishing itself can fail. Verify this pipeline with integration tests.

## 8. Operating when the Registry is unavailable

Schema Registry is a stateful API dependency. When the Registry is slow, returns 5xx errors, times out, or fails authentication, these scenarios can arise:

| Component | Possible behavior |
|---|---|
| Producer using a schema not yet in local cache | Cannot look up/register ID, so serialize/send fails. |
| Consumer encountering an uncached schema ID | Cannot fetch writer schema, so deserialization fails. |
| Consumer using already-cached IDs | May keep deserializing for a while without calling the Registry for that ID. |
| New pod starting during outage | Cache is usually empty, so it may fail immediately even while older pods still run. |

Caching behavior depends on client libraries, configuration, and schema specifics. Do not treat "old pods are still reading" as proof that the Registry is non-critical. A restart or receiving a record from a new schema version can trigger immediate failures.

When investigating an outage, test connectivity **from the application to the Registry**, not just the Registry health endpoint from an operator's laptop. DNS, TLS certificates, Service/Ingress, network policies, auth, and quotas can also block clients.

A safe workflow during a Registry incident:

1. Determine whether the error lies in the Registry, network, TLS/auth, or a specific schema ID/subject.
2. Pause producer rollouts emitting new schemas and new consumer rollouts if they are amplifying errors.
3. Check Registry latency, 4xx/5xx rates, timeouts, and affected instance counts.
4. Avoid mass-restarting consumers that are still functioning via caches.
5. Monitor producer send failures, deserialization errors, lag, and DLT ingress.
6. Restore the Registry and confirm clients can look up schemas again before resuming rollouts.

Do not "band-aid" by disabling compatibility or pointing `schema.registry.url` at a different Registry lacking the same data/IDs. Schema IDs are not inherently equivalent across two independent Registries.

## 9. Inspecting the Registry via API

Confluent Schema Registry provides an HTTP API to inspect subjects, versions, schema IDs, and compatibility policies. From an environment with access to the Registry:

```bash
# List existing subjects
curl -fsS http://schema-registry:8081/subjects

# View the latest version of subject orders-value
curl -fsS \
  http://schema-registry:8081/subjects/orders-value/versions/latest

# Look up schema by ID seen in logs
curl -fsS http://schema-registry:8081/schemas/ids/117

# View subject compatibility policy
curl -fsS http://schema-registry:8081/config/orders-value
```

Example response from `/subjects/orders-value/versions/latest`:

```json
{
  "subject": "orders-value",
  "version": 3,
  "id": 125,
  "schema": "{...}"
}
```

The output above is abbreviated for readability; fetch actual IDs, versions, and schema contents from the Registry. If the API returns `404`, distinguish between a missing subject and a missing schema ID. On `401/403`, check authentication/authorization. On `429` or `5xx`, check quotas, resources, and Registry availability.

In environments enforcing HTTPS and auth, supply your organization's URL/CA and auth mechanisms. Never embed real tokens or passwords in scripts committed to Git or shell history. When inspecting from Kubernetes, run from an appropriately authorized utility pod instead of exposing the Registry to the public Internet just to debug.

## 10. Checking compatibility before registering

A release pipeline should run compatibility checks before publishing new schemas. For Confluent Registry, the endpoint takes the form:

```text
POST /compatibility/subjects/{subject}/versions/latest
```

The body follows the API format; for Avro, the `schema` field holds **the JSON schema escaped as a string**. Example `compatibility-request.json` file:

```json
{
  "schemaType": "AVRO",
  "schema": "{\"type\":\"record\",\"name\":\"OrderCreated\",\"namespace\":\"com.example.events\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amount\",\"type\":\"long\"},{\"name\":\"note\",\"type\":[\"null\",\"string\"],\"default\":null}]}"
}
```

Sending the check request:

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data-binary @compatibility-request.json \
  http://schema-registry:8081/compatibility/subjects/orders-value/versions/latest
```

The response typically includes `is_compatible`. A `true` result does not replace business checks. To validate against all prior versions, configure a transitive policy or an equivalent check workflow; never look solely at `latest` and assume every historical schema is compatible.

**Do not auto-register schemas in production merely because a compatibility test passed.** Separate validation, review, and registration according to pipeline permissions. Registering a schema modifies shared metadata used across multiple services.

## 11. Controlled producer/consumer rollouts

When changing an event contract, account for the overlap window where old producers, new producers, old consumers, and new consumers coexist.

Backward-compatible rollout example:

```text
T0: Producer v1 -> Avro schema v1 -> Consumer v1

T1: Register schema v2 and run compatibility check

T2: Deploy Consumer v2
    Consumer v2 can read data written by Producer v1

T3: Deploy Producer v2
    Producer v2 starts writing records with schema v2

T4: Monitor deserialization errors, lag, business metrics
```

Consumer-first ordering usually fits `BACKWARD` evolution, yet **is only safe when any remaining old consumers can handle new records or are replaced in time**. During rolling updates of a group, both old and new consumers can hold partitions simultaneously; never assume every member is running new code just because one new pod reached Ready.

A rollout plan must clearly define:

- Which subject and compatibility policy apply in the Registry.
- What fields the new schema adds/removes/changes and what defaults apply.
- Whether old consumers can read new records during the overlap window.
- Whether new producers risk caching old schemas or auto-registering unexpectedly.
- Whether consumer group lag or DLT spikes after each step.
- If rolling back the app, whether records already written with the new schema will break the older consumer version.

**Rolling back code does not revert already-written records.** If producer v2 emitted messages incompatible with consumer v1, reverting consumers to v1 can make them fail at those written offsets. Therefore, define a data/schema rollback strategy, not just container-image rollback.

## 12. Schema changes must account for retention and replay

Kafka topics can retain records for days or weeks. When a consumer restarts from an old offset, or a new group uses `auto.offset.reset=earliest`, it can encounter many historical schema IDs.

Example:

```text
orders-0:
  offset 0..999     -> writer schema v1
  offset 1000..1999 -> writer schema v2
  offset 2000..     -> writer schema v3

New consumer replaying from offset 0
  must handle writer schemas v1, v2, v3
```

When planning Registry retention, cleanup, and disaster recovery, factor in how long records remain in Kafka, snapshots, DLTs, and other event storage copies. **Do not delete schemas/subjects still required for historical data.** Soft delete and hard delete carry different implications in Schema Registry; hard deletion can severely break decoding of old records if metadata is lost.

A solid replay setup must test reading a mix of multiple writer schemas, not just one newly published record in staging.

## 13. Controlling auth, TLS, and secrets

For production Registries, application connections usually require HTTPS, certificate validation, and an appropriate authentication mechanism. Config settings may include `schema.registry.url`, `basic.auth.credentials.source`, `basic.auth.user.info`, truststores/keystores, or tokens depending on vendor.

Example configuration using environment variables supplied by a secrets system:

```yaml
spring:
  kafka:
    properties:
      "[schema.registry.url]": "${SCHEMA_REGISTRY_URL}"
      "[basic.auth.credentials.source]": USER_INFO
      "[basic.auth.user.info]": "${SCHEMA_REGISTRY_CREDENTIALS}"
```

This is an illustrative example for the Confluent client's Basic Auth mechanism, not a mandatory recommendation to use Basic Auth. Add TLS and proper credential issuance/rotation policies; never commit real secret values into YAML stored in repositories.

If the Registry returns `403` on some operations but not others, the client may have read access to schemas without permission to register new schemas. That can be intentional policy: production producers only read schemas approved by pipelines.

## 14. Monitoring Schema Registry and Kafka impact

When monitoring a Kafka cluster using Schema Registry, correlate signals from the Registry, producers, and consumers:

| Component | Signal to watch | Interpretation |
|---|---|---|
| Registry | Availability, request latency, HTTP `4xx/5xx`, timeouts | Registry is not serving lookups/registrations reliably. |
| Registry | Schema registration count, subject/version changes | Detects unusual schema rollouts or unintended auto-registration. |
| Producer | Serialization failures, send failures, publish rate | Producer may be unable to encode records or find schemas. |
| Consumer | Deserialization failures, listener failures | Separates pre-listener errors from business logic errors. |
| Consumer group | Lag by partition, rebalances, committed offsets | Identifies unconsumed records or stalled progress. |
| DLT | Ingress rate, size, replay backlog | Detects unprocessable records routed off the main topic. |

Do not alert only on "Registry down". A healthy Registry whose subject was deleted, compatibility policy changed, or credentials expired will still break applications. Conversely, a brief Registry glitch may affect only new clients or uncached IDs.

When designing alerts, prioritize cause-and-effect correlations: **rising Registry latency + rising deserialization failures + rising consumer lag** is a far stronger investigative signal than three isolated metrics without context.

## 15. Common failure scenarios

| Symptom | Possible cause | Investigation path |
|---|---|---|
| `Unknown schema id` or schema ID lookup failed | ID does not exist in configured Registry, Registry data out of sync, or record wrote wrong ID. | Check `/schemas/ids/{id}`, Registry URL, environment/cluster, and wire format. |
| Producer reports schema registration failure | Incompatible schema, missing write permission, Registry timeout, or `auto.register.schemas=false`. | Check subject, compatibility policy, credentials, and registration pipeline. |
| Consumer fails after deploying new schema | Old consumer cannot read new data, wrong deserializer, or changed subject strategy. | Inspect schema IDs per record, members still on old version, and deployment order. |
| New pods fail while old pods keep running | Old pods have schema caches; new pods must fetch IDs from failing Registry. | Check Registry connectivity from new pods, DNS, TLS, and auth. |
| `ClassCastException` in listener | Consumer received `GenericRecord` while listener expects generated class, or wrong reader config. | Check `specific.avro.reader`, generated classes, and listener signature. |
| Deserialization failure never reaches DLT | `ErrorHandlingDeserializer` not used or DLT producer cannot serialize failing bytes. | Check deserializer delegate, error handler, DLT template, and serializers. |
| Lag rises while listener logs no exceptions | Error occurs before listener in deserializer, poll, or metadata lookup. | Check container logs, `ErrorHandlingDeserializer`, and Kafka client logs. |
| Schema compatibility passes yet business logic fails | Schema is format-valid but semantics changed. | Add contract tests with real payloads and running consumer versions. |
| Replaying old records fails | Old schema was deleted, new reader incompatible, or Registry has different IDs. | Check retention, historical schemas, subjects, and DR strategy. |

## 16. Runbook for investigating Registry-related deserialization errors

Suppose after a deployment, consumer group `order-service` sees rising lag and logs schema-related errors.

**Step 1 — Scope the incident.** Confirm Kafka brokers are healthy, partitions still hold records, the group has active members, and when errors began. Capture topic, partition, offset, and client ID of the first failing record.

**Step 2 — Pinpoint where the error occurred.** Is it from producer serialization, Kafka deserializer, business listener, or DLT producer? A stack trace inside `KafkaAvroDeserializer` points to schema lookup/decoding; failures inside the listener after successful deserialization belong to a different category.

**Step 3 — Look up the schema.** For Confluent format, read the schema ID from diagnostic details or appropriate tooling and query Registry API `/schemas/ids/{id}`. Check the actual Registry URL used by the pod, not a staging URL on an operator's machine.

**Step 4 — Inspect subject and compatibility.** Check the active subject, latest version, naming strategy, policy, and recent changes. Correlate schema registration logs with producer/consumer deployment timestamps.

**Step 5 — Check infrastructure.** Verify DNS, TLS, auth, network policies, Registry latency, and connectivity from affected pods. If it is a broad outage, avoid mass-restarting consumers still running off caches.

**Step 6 — Protect data.** If data is genuinely corrupted, use `ErrorHandlingDeserializer` with proper recovery/DLT. If the Registry is temporarily unavailable, consider pausing or delaying processing to avoid pushing a whole stream of valid events into the DLT.

**Step 7 — Recover and verify.** After fixing the root cause, verify decoding succeeds on previously failing records, committed offsets advance, lag drops, and no abnormal DLT/retry errors remain. Record the schema ID, subject, version, changes made, and replay impacts.

Do not manually edit committed offsets just to skip an undeserializable record without a procedure to preserve or process that record; doing so can lose business data.

## 17. Safe operations principles

- Treat the Registry as a serializer/deserializer runtime dependency, not just a schema documentation store.
- Distinguish schema ID, subject, and version; never equate version with ID and never assume IDs match across independent Registries.
- Enforce explicit compatibility policies per subject; test in the right direction across the full version history needing support.
- Place schema validation/registration in controlled CI/CD pipelines; restrict freeform auto-registration in production when contract governance is required.
- Deploy producers and consumers in compatible order; account for multi-version overlap windows and rollback scenarios.
- Verify consumers can read older writer schemas across the retention/replay window.
- Use `ErrorHandlingDeserializer` when pre-listener errors must be managed; ensure the DLT can preserve raw bytes of broken records.
- Monitor Registry availability alongside serialization/deserialization failures, consumer lag, and DLT ingress.
- Retain historical metadata/schemas for all living data; avoid hard-deleting subjects/schemas before assessing replay needs.
- Protect the Registry with TLS/auth, secret rotation, and least-privilege permissions; never put credentials in source code or logs.
- On error, distinguish nonexistent schemas, incompatible schemas, corrupted payloads, and Registry/network outages before choosing retry or DLT.

Schema Registry underpins Spring Kafka stability by governing data contracts across multiple producer and consumer versions. For reliable operations, teams must combine compatibility policies, schema testing, rollout procedures, serializer/deserializer configuration, dependency monitoring, and failed-record recovery. A healthy Registry is necessary, yet **ultimate reliability still depends on how applications handle schema changes, network incidents, and data already written by prior versions**.
