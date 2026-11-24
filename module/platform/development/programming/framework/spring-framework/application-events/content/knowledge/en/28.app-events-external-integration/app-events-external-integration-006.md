# Schema Registry and Versioning When Integrating Spring Application Events Externally

## 1. Why do events need a schema registry?

In a Spring application, `ApplicationEventPublisher.publishEvent(...)` usually passes a Java object between components within the same process. Producer and listener can be built and deployed together, so the compiler helps catch many type-change errors at compile time.

When an event must reach independent services over Kafka, RabbitMQ, or other messaging infrastructure, the boundary changes:

- Producer and consumer may run **different application versions** during a rolling deployment.
- A consumer may read a message stored months earlier using newer code.
- An event may be read by Java, Go, Python, or an analytics system.
- There is no longer a guarantee that all sides share a Java class, enum, or package name.
- The broker stores/routes messages, but does not inherently understand the meaning of all business fields.

A **Schema** is a description of the data types/structure on the wire: fields, data types, default values, and certain interpretation rules. A **Schema Registry** is a service that stores, versions, and looks up schemas, typically paired with compatibility-checking policies before accepting a new version.

For example, an older version of a service emits `order.placed` with only an order ID and amount. A newer version wants to add currency:

```json
{
  "orderId": "ORD-101",
  "amountMinorUnits": 12500,
  "currency": "USD"
}
```

If an older consumer does not understand the new field, or a newer consumer reads historical data lacking `currency`, deployment can cause errors or—worse—misinterpret data. A schema registry checks **part of the data contract**, but **does not replace contract tests for business semantics**.

**Scope:** This lesson presents Schema Registry using Avro and Kafka/Confluent as concrete examples; the versioning principles also apply to Protobuf, JSON Schema, and other brokers, though compatibility rules and wire formats differ across technologies.

## 2. Distinguishing four layers of an event system

```text
[Domain/Application Layer]
      OrderPlaced (Java record/POJO)
           |
           | ApplicationEventPublisher.publishEvent(...)
           v
      @EventListener (bridge/adapter)
           |
           | map to integration event
           v
[Integration Contract Layer]
      eventType=order.placed
      Avro schema v1 / v2 ...
           |
           | serializer looks up/registers schema
           v
[Transport Layer]
      Kafka topic / message broker
      bytes + headers + key
           |
           | consumer fetches payload's schema
           v
[Consumer Layer]
      deserializer -> decoded data
      validation -> business handler -> ACK/offset
```

Be clear about **what the schema registry manages**:

- Manages a set of **schemas per subject**.
- Records the **version** of each schema within a subject.
- Issues or looks up a **schema ID** so deserializers know which definition to use.
- Can **reject registering a new schema** if it violates the compatibility policy.
- Provides a REST API/client for producers, consumers, and CI to verify contracts.

And what it **does not manage**:

- Whether Spring registered an `@EventListener` bean.
- When the database commits or rolls back.
- Whether the broker actually persisted and delivered the message.
- Whether the consumer successfully called an external API.
- Idempotency, retries, DLQ, or exactly-once business effects.
- Business meaning of a value like whether `amountMinorUnits` is cents or dollars.

**A Schema Registry is not a message broker.** Producers still need Kafka/RabbitMQ and dedicated mechanisms for sending, receiving, retrying, and monitoring.

## 3. Schema, subject, version, and schema ID are four different concepts

With Confluent Schema Registry, distinguish:

| Concept | Meaning | Example |
| --- | --- | --- |
| Schema | Definition of structure/types on the wire | Avro record `OrderPlaced` |
| Subject | Namespace/version group where compatibility is checked | `order.placed-value` |
| Subject version | Registration sequence number within **one subject** | v1, v2 |
| Schema ID | Identifier issued by the registry for clients to look up a schema | An integer returned by the server |
| Event type | Name of the business fact | `order.placed` |
| Payload/event version | Business contract version if the organization also uses custom metadata | `schemaVersion=2` |
| Aggregate version | State transition sequence of an aggregate | `aggregateVersion=17` |
| Application release | Service build/deploy version | `orders-service 4.2.0` |

**A Schema ID is not a subject version.** One schema can be registered under multiple subjects; IDs can be reused across the registry while each subject’s version evolves independently. Never write code assuming `schema ID=2` is always `version 2`.

### Subject naming in Kafka

With the common topic-based subject naming strategy (`TopicNameStrategy`):

- Topic `order.placed` has value subject `order.placed-value`.
- If the key also has its own schema, the key subject may be `order.placed-key`.
- Typically a sequence of value schema versions within a subject is compatibility-checked per configuration.

There are also strategies like `RecordNameStrategy` and `TopicRecordNameStrategy`. They group schemas by record name or topic+record combination, suitable when multiple record types share a topic. Choose a strategy before producers run widely; **changing subject naming does not migrate schema history automatically** and can cause consumers to look up the wrong schema.

### Why do you need versions even when the class name stays the same?

Two services can share the class name `OrderPlaced` while the newer classpath adds a field. Conversely, internal classes can be refactored without changing the Avro contract. **Schema version belongs to the data contract**; it should not be bumped on every release, nor depend on internal entity package names.

## 4. How Avro encodes and looks up schemas

Avro is a schema-based format. Binary data can only be decoded properly when the deserializer knows the **writer schema**; when projecting onto a newer contract, it can also use a **reader schema** and perform schema resolution.

In the **default/legacy Confluent Avro wire format**, the message value usually has:

```text
+-----------+--------------------+-----------------------+
| magic byte| schema ID (4 bytes)| Avro binary payload   |
+-----------+--------------------+-----------------------+
|     0     |       ID           | serialized values     |
+-----------+--------------------+-----------------------+
```

The exact wire format depends on the serializer and configuration; this is the typical Confluent serializer layout rather than **an Avro specification requirement that every application must follow**.

Typical decode flow:

1. Consumer receives bytes from the broker.
2. Deserializer reads the schema ID from the framing.
3. Client looks up the corresponding schema via the registry; client may cache the result.
4. Uses the writer schema to interpret the binary data.
5. If the application uses a newer reader schema, applies appropriate resolution/default rules.
6. Maps the data into the business processing model.

The registry helps decode older data, but **does not automatically turn a v1 event into a semantically valid v2 domain object**. Mapping, defaults, or upcasting require an explicit contract.

## 5. Compatibility modes: reading in the right direction

When registering a new schema, the registry can evaluate it against earlier schemas. Common terms:

| Mode | What must be guaranteed |
| --- | --- |
| `BACKWARD` | Readers with the **new** schema can read data written with the **immediately preceding** schema |
| `BACKWARD_TRANSITIVE` | New readers can read data written with **all prior schemas** |
| `FORWARD` | Old schema readers can read data written by the new schema, against the immediately preceding version |
| `FORWARD_TRANSITIVE` | Readers of all prior versions can read data written by the new schema |
| `FULL` | Both backward and forward against the immediately preceding version |
| `FULL_TRANSITIVE` | Both directions against all prior versions |
| `NONE` | Disables registry compatibility checks |

**Confluent Schema Registry defaults to `BACKWARD`, not `BACKWARD_TRANSITIVE`.** This matters when a system must read/replay very old data. With non-transitive `BACKWARD`, a chain v1→v2 and v2→v3 may be accepted even if v3 cannot read all data from v1.

### Producer/consumer upgrade direction

- For **backward compatibility**, normally upgrade consumers to read old/new data **before** producers start writing the new schema. That way, the last-upgraded consumer is not surprised by new data.
- For **forward compatibility**, evaluate older consumers’ ability to understand new data and the deployment order per the specific contract; do not infer a single rule for every schema format.
- For **full compatibility**, upgrade order is more flexible, yet contract tests are still needed for business logic, enums, nulls, and older versions.
- With **NONE**, any syntactically valid schema can be registered; the organization must manually control breaking-change risks.

Choose policies **per subject** when needs differ. Never set `NONE` globally across the registry just to “unblock a deploy” without a migration plan or a new subject/topic.

## 6. Schema evolution example: v1, v2, and a breaking version

An explicit business assumption is recorded: **all orders during the v1 era used USD**. Therefore, when upgrading to v2, `currency="USD"` is a valid default for historical data.

### v1 — two initial fields

```json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.contract",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinorUnits", "type": "long"}
  ]
}
```

### v2 — adding currency with a default

```json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.contract",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinorUnits", "type": "long"},
    {"name": "currency", "type": "string", "default": "USD"}
  ]
}
```

With Avro, schema v2 can read data written by v1: when `currency` is missing from writer schema v1, the Avro v2 reader can apply the **reader schema’s** `default` of USD.

**Easy-to-miss point:** Avro defaults serve **schema resolution when reading data missing a field**, not a promise that serializers will auto-fill defaults into every v2 producer record. When writing with schema v2, the application usually still needs to provide a valid field for that record.

In this example, schema v1 reading data written by v2 can also ignore the new `currency` field. For this specific change, both directions may be structurally compatible, yet v1 logic might **not support non-USD transactions**. This is a prime example of *schema compatibility not guaranteeing semantic compatibility*.

### v3-bad — adding a required field with no default

```json
{
  "type": "record",
  "name": "OrderPlaced",
  "namespace": "example.contract",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "amountMinorUnits", "type": "long"},
    {"name": "currency", "type": "string", "default": "USD"},
    {"name": "salesChannel", "type": "string"}
  ]
}
```

When reading a v2 event with reader schema v3-bad, Avro does not know the value of `salesChannel` because old writers did not include it and the new reader defines no default. Hence v3-bad is **not backward compatible** with v2.

A sensible v3 could declare `salesChannel` as nullable with default `null` if business allows “unspecified”:

```json
{"name": "salesChannel", "type": ["null", "string"], "default": null}
```

In Avro, the order of union branches and the default’s type must match; `["null","string"]` with `default:null` is the standard idiom.

**Never pick defaults arbitrarily.** If v1 actually contained multi-currency orders without recording `currency`, defaulting to USD produces corrupted data. When facts are missing, you need an audited migration/upcaster strategy, an explicit unknown value, or to prevent old data from being interpreted as a known value.

## 7. Changes requiring caution beyond adding fields

| Change | Risk | How to handle |
| --- | --- | --- |
| Add field with valid default | Usually backward compatible in Avro | Write reader/writer tests |
| Add required field without default | New reader cannot read old data | Default, nullable union, or separate version |
| Remove required field | Old reader may fail on new writer | Evaluate bidirectional compatibility |
| Change `long` to `string` | Usually breaks contract | Create new field/schema/topic or adapter |
| Rename `orderId` to `id` | Needs Avro aliases/proper migration | Evaluate schema resolution, contract tests |
| Change meaning of `amountMinorUnits` | Risk of silent corruption | New event type/version, business review |
| Add enum symbol | Old reader may fail on unknown symbol | Fallback/unknown, check per format |
| Change nullability | Affects writers/readers differently | Check union/default and all consumers |
| Change nested record/union | Can affect multiple types | Test historical fixtures and policy |
| Delete schema too early | Old data becomes undecodable | Controlled retention/migration/replay |

With **Protobuf**, field numbers are part of the wire contract; avoid reusing deleted field numbers and mark them `reserved` per rules. With **JSON Schema**, compatibility behavior also depends on whether the model allows extra fields (open/closed content model), `required` rules, and registry policies. Do not copy Avro rules verbatim to those two formats.

## 8. Runnable Java 17+ example: Spring events + Avro evolution

The hands-on exercise below **does not need Kafka, a Schema Registry server, or a database**. It demonstrates two foundational pieces:

1. Java/Avro determining whether a new schema can read data written with an older schema.
2. A Spring `@EventListener` converting an internal Java event into a record matching an **integration schema**.

Then, in section 9, we use REST with a **real Schema Registry** to store subjects/versions and run server-side compatibility checks. The two exercises serve distinct purposes: checking Avro in the JVM does not substitute for registering schemas or sending messages to a broker.

### 8.1. Directory structure

```text
spring-avro-schema-demo/
├── pom.xml
├── compose.yaml
└── src/
    ├── main/java/example/events/SchemaEvolutionDemo.java
    └── test/java/example/events/SchemaEvolutionDemoTest.java
```

### 8.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>spring-avro-schema-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.13</version>
        </dependency>
        <dependency>
            <groupId>org.apache.avro</groupId>
            <artifactId>avro</artifactId>
            <version>1.12.0</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.3. SchemaEvolutionDemo.java

```java
package example.events;

import java.io.ByteArrayOutputStream;
import java.io.IOException;

import org.apache.avro.Schema;
import org.apache.avro.SchemaCompatibility;
import org.apache.avro.generic.GenericData;
import org.apache.avro.generic.GenericDatumReader;
import org.apache.avro.generic.GenericDatumWriter;
import org.apache.avro.generic.GenericRecord;
import org.apache.avro.io.BinaryDecoder;
import org.apache.avro.io.BinaryEncoder;
import org.apache.avro.io.DecoderFactory;
import org.apache.avro.io.EncoderFactory;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SchemaEvolutionDemo {

    private static final String V1_JSON = """
            {
              "type": "record",
              "name": "OrderPlaced",
              "namespace": "example.contract",
              "fields": [
                {"name":"orderId","type":"string"},
                {"name":"amountMinorUnits","type":"long"}
              ]
            }
            """;

    private static final String V2_JSON = """
            {
              "type": "record",
              "name": "OrderPlaced",
              "namespace": "example.contract",
              "fields": [
                {"name":"orderId","type":"string"},
                {"name":"amountMinorUnits","type":"long"},
                {"name":"currency","type":"string","default":"USD"}
              ]
            }
            """;

    private static final String V3_BAD_JSON = """
            {
              "type": "record",
              "name": "OrderPlaced",
              "namespace": "example.contract",
              "fields": [
                {"name":"orderId","type":"string"},
                {"name":"amountMinorUnits","type":"long"},
                {"name":"currency","type":"string","default":"USD"},
                {"name":"salesChannel","type":"string"}
              ]
            }
            """;

    private static final Schema V1 =
            new Schema.Parser().parse(V1_JSON);
    private static final Schema V2 =
            new Schema.Parser().parse(V2_JSON);
    private static final Schema V3_BAD =
            new Schema.Parser().parse(V3_BAD_JSON);

    // Internal event: not yet an Avro/Kafka message.
    public record OrderPlaced(
            String eventId,
            String orderId,
            long amountMinorUnits,
            String currency) {
    }

    public static Schema schemaV1() {
        return V1;
    }

    public static Schema schemaV2() {
        return V2;
    }

    public static Schema schemaV3Bad() {
        return V3_BAD;
    }

    // Compatibility direction: newReader reads oldWriter.
    public static boolean canRead(Schema reader, Schema writer) {
        return SchemaCompatibility.checkReaderWriterCompatibility(
                reader, writer).getType()
                == SchemaCompatibility.SchemaCompatibilityType.COMPATIBLE;
    }

    // Demo: build a record according to schema V1 or V2.
    public static byte[] write(
            Schema writerSchema,
            String orderId,
            long amountMinorUnits,
            String currency) throws IOException {

        GenericRecord record = new GenericData.Record(writerSchema);
        record.put("orderId", orderId);
        record.put("amountMinorUnits", amountMinorUnits);

        if (writerSchema.getField("currency") != null) {
            record.put("currency", currency);
        }

        try (ByteArrayOutputStream output =
                     new ByteArrayOutputStream()) {
            GenericDatumWriter<GenericRecord> writer =
                    new GenericDatumWriter<>(writerSchema);

            BinaryEncoder encoder =
                    EncoderFactory.get().binaryEncoder(output, null);

            writer.write(record, encoder);
            encoder.flush();
            return output.toByteArray();
        }
    }

    // Avro schema resolution with explicit writer and reader schemas.
    public static GenericRecord read(
            byte[] bytes,
            Schema writerSchema,
            Schema readerSchema) throws IOException {

        GenericDatumReader<GenericRecord> reader =
                new GenericDatumReader<>(writerSchema, readerSchema);

        BinaryDecoder decoder =
                DecoderFactory.get().binaryDecoder(bytes, null);

        return reader.read(null, decoder);
    }

    public static class Bridge {
        private GenericRecord lastRead;

        @EventListener
        public void on(OrderPlaced domainEvent) {
            try {
                byte[] payload = write(
                        V2,
                        domainEvent.orderId(),
                        domainEvent.amountMinorUnits(),
                        domainEvent.currency());

                // Simulated wire round-trip;
                // not yet sent to a message broker.
                lastRead = read(payload, V2, V2);

                System.out.printf(
                        "BRIDGE id=%s order=%s currency=%s%n",
                        domainEvent.eventId(),
                        lastRead.get("orderId"),
                        lastRead.get("currency"));
            } catch (IOException ex) {
                throw new IllegalStateException(
                        "Cannot encode integration event", ex);
            }
        }

        public GenericRecord lastRead() {
            return lastRead;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DemoConfig {
        @Bean
        Bridge bridge() {
            return new Bridge();
        }
    }

    public static void main(String[] args) throws IOException {
        System.out.println("BACKWARD v2<-v1="
                + canRead(V2, V1));
        System.out.println("BACKWARD v3<-v2="
                + canRead(V3_BAD, V2));

        byte[] oldBytes =
                write(V1, "ORD-101", 12500L, null);
        GenericRecord upgraded = read(oldBytes, V1, V2);

        System.out.printf(
                "REPLAY order=%s currency=%s%n",
                upgraded.get("orderId"),
                upgraded.get("currency"));

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             DemoConfig.class)) {

            context.publishEvent(
                    new OrderPlaced(
                            "evt-102", "ORD-102", 2500L, "VND"));
        }
    }
}
```

### 8.4. Run command and expected output

Requires JDK 17+ and Maven, from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.events.SchemaEvolutionDemo
```

Lines printed by the **demo code** (excluding library logs):

```text
BACKWARD v2<-v1=true
BACKWARD v3<-v2=false
REPLAY order=ORD-101 currency=USD
BRIDGE id=evt-102 order=ORD-102 currency=VND
```

Explanation:

1. `canRead(V2,V1)` returns `true` because reader schema v2 has a default for the new `currency` field.
2. `canRead(V3_BAD,V2)` returns `false` because v3 adds `salesChannel` with no default.
3. Avro bytes were written using **v1**, then read using **v2**. The Avro reader applies the default `USD`, so `REPLAY` prints `currency=USD`.
4. Spring dispatches the Java record `OrderPlaced` to the `@EventListener` method. The bridge maps to a **v2** record, encodes/decodes, and prints `VND`.
5. The example needs no network, database, registry, or Kafka. It illustrates **old-schema readability and the internal → integration event boundary**, not proof that a broker received a message.

Do not alter `canRead` to swap the two arguments: `checkReaderWriterCompatibility(reader, writer)` defines **reader first, writer second**. Swapping them turns a `BACKWARD` check into a different check.

### 8.5. JUnit 5 unit/integration tests

File `src/test/java/example/events/SchemaEvolutionDemoTest.java`:

```java
package example.events;

import org.apache.avro.generic.GenericRecord;
import org.junit.jupiter.api.Test;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SchemaEvolutionDemoTest {

    @Test
    void newReaderCanReadOldAvroData() throws Exception {
        byte[] writtenByV1 =
                SchemaEvolutionDemo.write(
                        SchemaEvolutionDemo.schemaV1(),
                        "ORD-1", 100L, null);

        GenericRecord readByV2 =
                SchemaEvolutionDemo.read(
                        writtenByV1,
                        SchemaEvolutionDemo.schemaV1(),
                        SchemaEvolutionDemo.schemaV2());

        assertEquals("ORD-1",
                readByV2.get("orderId").toString());
        assertEquals(100L,
                readByV2.get("amountMinorUnits"));
        assertEquals("USD",
                readByV2.get("currency").toString());
    }

    @Test
    void requiredNewFieldBreaksBackwardCompatibility() {
        assertTrue(SchemaEvolutionDemo.canRead(
                SchemaEvolutionDemo.schemaV2(),
                SchemaEvolutionDemo.schemaV1()));

        assertFalse(SchemaEvolutionDemo.canRead(
                SchemaEvolutionDemo.schemaV3Bad(),
                SchemaEvolutionDemo.schemaV2()));
    }

    @Test
    void springDispatchesInternalEventToSchemaBridge() {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             SchemaEvolutionDemo.DemoConfig.class)) {

            context.publishEvent(
                    new SchemaEvolutionDemo.OrderPlaced(
                            "evt-1", "ORD-2", 200L, "EUR"));

            var bridge = context.getBean(
                    SchemaEvolutionDemo.Bridge.class);

            assertNotNull(bridge.lastRead());
            assertEquals("ORD-2",
                    bridge.lastRead().get("orderId").toString());
            assertEquals("EUR",
                    bridge.lastRead().get("currency").toString());
        }
    }
}
```

Run:

```bash
mvn test
```

The project defines **3 test methods**. When all assertions pass, Surefire reports success; duration and logs depend on the machine. These tests do not connect to a registry/broker—that is the **intentional scope** of unit and Spring context tests.

## 9. Hands-on with a real Schema Registry via REST API

Schema Registry is a separate service that typically uses Kafka to store internal metadata. To run locally, you can use Docker Compose with Kafka and Schema Registry. This section demonstrates the real API used to manage **subjects, versions, and compatibility**.

### 9.1. compose.yaml (local lab)

```yaml
services:
  kafka:
    image: confluentinc/cp-kafka:7.8.2
    hostname: kafka
    ports:
      - "9092:9092"
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_PROCESS_ROLES: "broker,controller"
      KAFKA_CONTROLLER_QUORUM_VOTERS: "1@kafka:29093"
      KAFKA_LISTENERS: "PLAINTEXT://kafka:29092,CONTROLLER://kafka:29093,PLAINTEXT_HOST://0.0.0.0:9092"
      KAFKA_ADVERTISED_LISTENERS: "PLAINTEXT://kafka:29092,PLAINTEXT_HOST://localhost:9092"
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: "PLAINTEXT:PLAINTEXT,PLAINTEXT_HOST:PLAINTEXT,CONTROLLER:PLAINTEXT"
      KAFKA_INTER_BROKER_LISTENER_NAME: "PLAINTEXT"
      KAFKA_CONTROLLER_LISTENER_NAMES: "CONTROLLER"
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS: 0
      CLUSTER_ID: "MkU3OEVBNTcwNTJENDM2Qk"

  registry:
    image: confluentinc/cp-schema-registry:7.8.2
    hostname: registry
    depends_on:
      - kafka
    ports:
      - "8081:8081"
    environment:
      SCHEMA_REGISTRY_HOST_NAME: "registry"
      SCHEMA_REGISTRY_LISTENERS: "http://0.0.0.0:8081"
      SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS: "PLAINTEXT://kafka:29092"
```

This is a **local lab**, not a production configuration: single broker, no TLS/auth, no persistent volumes, no replication/HA. Some image versions may change configuration requirements; keep the same version family and check logs if containers fail to start. `depends_on` only orders container startup; **it does not guarantee Kafka is ready** before the registry tries to connect.

Start:

```bash
docker compose up -d
docker compose ps
```

Wait for the REST API to be ready by testing:

```bash
curl -fsS http://localhost:8081/subjects
```

When the new registry has no subjects yet, it usually returns `[]`. On connection errors, inspect `docker compose logs registry kafka` and retry **after the services finish starting**, rather than ignoring errors. The `curl` commands below use POSIX shell quoting; PowerShell has its own quoting rules.

### 9.2. Setting compatibility for a subject

Use the subject bound to topic `order.placed` under `TopicNameStrategy`:

```bash
curl -fsS -X PUT \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"compatibility":"BACKWARD_TRANSITIVE"}' \
  http://localhost:8081/config/order.placed-value
```

A successful response contains a `compatibility` field with value `BACKWARD_TRANSITIVE`. Setting policy at the **subject** level avoids unintended impact on other subjects.

Verify:

```bash
curl -fsS http://localhost:8081/config/order.placed-value
```

### 9.3. Registering schema v1

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"schemaType":"AVRO","schema":"{\"type\":\"record\",\"name\":\"OrderPlaced\",\"namespace\":\"example.contract\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amountMinorUnits\",\"type\":\"long\"}]}"}' \
  http://localhost:8081/subjects/order.placed-value/versions
```

The response contains the server-assigned schema ID, in a form such as:

```json
{"id": 123}
```

The number `123` is an **illustrative example only**, not a prediction of the actual ID. Check versions after registering:

```bash
curl -fsS http://localhost:8081/subjects/order.placed-value/versions
```

For a new subject, the result may be `[1]`.

### 9.4. Checking v2 before registering

Use `/compatibility/subjects/{subject}/versions` to validate against the subject’s policy, including transitive modes. This is the right step for CI to check schema changes:

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"schemaType":"AVRO","schema":"{\"type\":\"record\",\"name\":\"OrderPlaced\",\"namespace\":\"example.contract\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amountMinorUnits\",\"type\":\"long\"},{\"name\":\"currency\",\"type\":\"string\",\"default\":\"USD\"}]}"}' \
  http://localhost:8081/compatibility/subjects/order.placed-value/versions
```

With the `BACKWARD_TRANSITIVE` policy and v1 above, the expected result is:

```json
{"is_compatible": true}
```

This is only a **check**; it has not created a new version yet. The registry validates Avro structure and policy, not whether defaulting to USD is business-accurate.

### 9.5. Registering v2 and reading metadata

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"schemaType":"AVRO","schema":"{\"type\":\"record\",\"name\":\"OrderPlaced\",\"namespace\":\"example.contract\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amountMinorUnits\",\"type\":\"long\"},{\"name\":\"currency\",\"type\":\"string\",\"default\":\"USD\"}]}"}' \
  http://localhost:8081/subjects/order.placed-value/versions

curl -fsS \
  http://localhost:8081/subjects/order.placed-value/versions/latest
```

The `latest` response provides subject/version/schema ID/schema string and may include additional metadata depending on server/client. For a new subject with two distinct schemas registered sequentially, latest is typically **version 2**. The schema ID is a separate server-assigned value and **does not have to equal 2**.

### 9.6. Testing a breaking version without registering

Propose adding a required `salesChannel` with no default:

```bash
curl -fsS -X POST \
  -H 'Content-Type: application/vnd.schemaregistry.v1+json' \
  --data '{"schemaType":"AVRO","schema":"{\"type\":\"record\",\"name\":\"OrderPlaced\",\"namespace\":\"example.contract\",\"fields\":[{\"name\":\"orderId\",\"type\":\"string\"},{\"name\":\"amountMinorUnits\",\"type\":\"long\"},{\"name\":\"currency\",\"type\":\"string\",\"default\":\"USD\"},{\"name\":\"salesChannel\",\"type\":\"string\"}]}"}' \
  'http://localhost:8081/compatibility/subjects/order.placed-value/versions?verbose=true'
```

With v1/v2 and the `BACKWARD_TRANSITIVE` policy above, `is_compatible` must be `false`. When `verbose=true` is enabled, the response may include explanatory messages. Do not hardcode exact registry error message strings in tests, as server versions may alter wording.

If you attempt to **register** a breaking version via `POST /subjects/.../versions`, the registry will reject it per the compatibility policy (typically HTTP 409). Do not put contract-breaking registration calls into a real deploy pipeline just to “see if it errors”; use the compatibility check endpoint first.

### 9.7. Tearing down the lab

```bash
docker compose down
```

If you want to wipe all data in managed volumes, do so intentionally on the lab; never run volume-deletion commands in an environment holding real Kafka/SR data.

## 10. Integrating Schema Registry into Spring Kafka

The section 8 exercise tests Avro in the JVM; section 9 registers schemas via REST. For **Kafka messages to actually use Schema Registry**, producers/consumers need appropriate serializers/deserializers.

Sample configuration in a **Spring Boot application with Spring Kafka and Confluent Avro SerDes** (not in the `spring-context`-only demo project):

```properties
spring.kafka.bootstrap-servers=localhost:9092

spring.kafka.producer.key-serializer=org.apache.kafka.common.serialization.StringSerializer
spring.kafka.producer.value-serializer=io.confluent.kafka.serializers.KafkaAvroSerializer

spring.kafka.consumer.key-deserializer=org.apache.kafka.common.serialization.StringDeserializer
spring.kafka.consumer.value-deserializer=io.confluent.kafka.serializers.KafkaAvroDeserializer

spring.kafka.properties.schema.registry.url=http://localhost:8081
spring.kafka.consumer.properties.specific.avro.reader=false
```

`KafkaAvroSerializer` / `KafkaAvroDeserializer` come from the **`io.confluent:kafka-avro-serializer`** dependency at a version compatible with your Kafka/Confluent stack; Maven may require the Confluent repository. `spring-kafka` is Spring’s Kafka framework dependency, whereas `spring-context` does **not** bring these serializers onto the classpath automatically.

With `specific.avro.reader=false`, consumers typically receive `GenericRecord`. If you want `SpecificRecord` classes generated from Avro schemas, configure appropriate code generation/readers and manage versions of those generated classes.

Example send with Spring Kafka, **illustrative snippet only**:

```java
GenericRecord record = new GenericData.Record(orderPlacedSchemaV2);
record.put("orderId", "ORD-101");
record.put("amountMinorUnits", 12500L);
record.put("currency", "USD");

kafkaTemplate.send("order.placed", "ORD-101", record)
        .whenComplete((result, error) -> {
            if (error != null) {
                // Record error and route to retry/outbox per contract.
            } else {
                // Kafka producer send succeeded per ACK config.
                // Does not yet mean consumer completed business processing.
            }
        });
```

This snippet assumes `KafkaTemplate<String, GenericRecord> kafkaTemplate`, schema V2, imports, and a configured producer/serializer bean exist. It is **not a standalone compilable program**. Spring Kafka uses `CompletableFuture` for `KafkaTemplate.send(...)` in modern framework releases; handle completions/errors rather than ignoring the result.

**Do not auto-register new schemas from arbitrary events at runtime.** Some serializers allow `auto.register.schemas=true`, but production usually requires controlled registration in CI/CD or a governance pipeline using approved schemas. When disabling auto-registration, ensure the schema/subject already exists, and configure lookup/schema ID settings appropriate to the serializer in use.

### Can Schema Registry be used with RabbitMQ?

You can use the registry as an **independent contract service** and serialize Avro/Protobuf before sending to RabbitMQ, but RabbitMQ does not natively understand Confluent Schema Registry framing/subjects. Applications must agree on how to transmit schema IDs/headers, serializers/deserializers, lookups, compatibility, and caching. Do not copy `spring.kafka.*` properties onto `RabbitTemplate` expecting them to work.

## 11. Versioning does not live solely in the schema registry

Beyond the schema, an integration event also needs fields such as:

```json
{
  "eventId": "d1e173a5-486a-4c78-b90e-abc25004f604",
  "eventType": "order.placed",
  "occurredAt": "2026-11-11T06:15:00Z",
  "aggregateId": "ORD-101",
  "aggregateVersion": 7,
  "payload": {
    "orderId": "ORD-101",
    "amountMinorUnits": 12500,
    "currency": "USD"
  }
}
```

This is an **illustrative envelope**; Confluent Avro messages do not have to use this exact JSON envelope. Some metadata can live in Kafka headers or be defined inside the Avro record.

Distinguish:

- `eventId` identifies a single occurrence, typically serving as the deduplication key.
- `aggregateVersion` tracks state-change order for an aggregate, if the app maintains a sequence.
- `occurredAt` helps look up/audit when the event occurred.
- `schemaVersion` is a contract version if the system also publishes this field; it **does not replace** the registry-assigned schema ID.
- `eventType` is the business fact, not necessarily identical to the subject name or Java class name.

A schema registry generally **does not validate the meaning** of event types, aggregate sequences, or idempotency. Systems still need business contracts, unique constraints, versioning policies, and tests.

## 12. Rolling deployments and handling historical data

In a system with multiple producers/consumers, schema changes need a rollout plan:

1. **Confirm the v1 contract:** document every field, unit, nullability, default, enum, and real data examples.
2. **Propose v2:** add fields or alter types with clear impact analysis.
3. **Run compatibility checks:** in CI against the active subject/schema policy.
4. **Run consumer contract tests:** read v1 and v2 fixtures using the implementation slated for deployment.
5. **Upgrade consumers that need to read the new version before producers emit it** under a backward-compatibility plan.
6. **Register v2 in a controlled step:** pipeline records subject/version/ID.
7. **Deploy producer:** monitor serializer/registry lookup errors and consumer decoding.
8. **Observe both versions:** emit metrics by event type/schema family; do not drop v1 support while retention, DLQs, or replays still exist.
9. **Conditionally complete migration:** remove v1 readers/upcasters only when retention and consumer contracts allow.

If a new producer emits a schema-valid v2 payload whose `currency` holds a value unsupported by older consumers, you need a **business-level compatibility plan**. The registry cannot know whether `"JPY"` will break a consumer’s financial report.

### Upcasting when reading historical events

Two distinct approaches exist:

- **Schema resolution:** Avro uses reader/writer schemas to decode, fill in defaults, and drop unneeded fields according to rules.
- **Upcasting/domain migration:** the application transforms older events into the current model and intentionally handles semantic shifts.

Do not assume schema resolution performs business upcasting on its own. For instance, if v1 did not record taxes and v2 requires tax calculation, you need rules or historical data rather than an arbitrary default.

During replays, consumers may encounter multiple schema IDs in the same topic. Keep historical schemas available or maintain a verified migration/archival strategy; deleting subjects/schemas just to “clean up the registry” can break data still sitting in brokers/outboxes.

## 13. Contract testing in CI/CD

A good pipeline does more than compile the new producer. It tests producer, schema registry, and consumer.

### 13.1. Tests to include

| Test | Verifies |
| --- | --- |
| Parse schema | Avro/Protobuf/JSON Schema is syntactically valid |
| Reader/writer compatibility | New reader can read old data per policy |
| Registry compatibility endpoint | Schema is accepted by subject policy |
| Historical fixture decode | Consumer reads real binary/JSON from v1/v2 |
| Serialization round-trip | Encoded/decoded data preserves values/semantics |
| Semantic contract test | Currency units, enums, defaults, timestamps, nulls match business rules |
| Producer integration | Serializer looks up/registers schema under the right subject |
| Consumer integration | Deserializer looks up schema ID and processes properly |
| Negative compatibility test | Breaking changes are blocked before deploy |
| Replay test | New consumer processes older data still within retention |
| Cross-service contract | Consumers in other languages/codebases share the same contract |
| Security test | Registry ACLs/auth prevent unauthorized schema mutations |

The section 8 unit tests demonstrate part of parsing/compatibility/reader-writer checks; the section 9 **REST integration** demonstrates server policy. In CI, never use a shared production registry as a sandbox for broken schemas; use a test registry or a read-only compatibility endpoint with appropriate permissions.

### 13.2. Golden fixtures

Store sanitized messages from released versions in test resources:

```text
src/test/resources/contracts/order-placed-v1.avsc
src/test/resources/contracts/order-placed-v2.avsc
src/test/resources/events/order-placed-v1.bin
src/test/resources/events/order-placed-v2.bin
```

This is a **suggested test layout**, not mandatory files for the section 8 demo. Generating fixtures for every version using only the latest serializer can miss real quirks from older producers. Include verified historical payloads in tests to catch mapping regressions.

### 13.3. When schema evolution requires a breaking change

When field/type/meaning changes cannot evolve compatibly, options include:

- Publish a **new event type** if the business fact truly differs.
- Create a **new topic/subject** with a clear migration plan; never write contract-breaking payloads where older consumers cannot handle them.
- Maintain both representations during a transition period, while avoiding double-processing the same business event via correlation IDs/deduplication.
- Use an adapter/upcaster at the boundary for un-upgraded consumers.
- Define deprecation dates and end-of-read dates for old versions based on retention/replay needs.

**Do not set `compatibility=NONE` and treat registry acceptance as a sign of a successful migration.**

## 14. Failure modes: when the registry cannot save you

### 14.1. Registry temporarily unreachable

When a producer serializer needs to look up/register an uncached schema ID, publishing can fail if the registry is unreachable. Consumers reading an uncached schema ID can also fail to decode if lookup fails. Continuity depends on caching, serializers, client retries, and configuration.

Mitigation: monitor registry latency/errors, bounded retries/backoff, caching, and schema pre-registration. For critical events, producers use an outbox to preserve send intent during temporary registry/broker outages.

### 14.2. Producer sends an unregistered schema

If auto-registration is disabled and a schema has not been registered under the right subject, the serializer may throw lookup errors. Check subject naming strategy, URL, auth, canonical schema form, compatibility policy, and version. Never swap the serializer to `StringSerializer` just to bypass the contract.

### 14.3. Consumer cannot understand the new schema

Causes may include schema incompatibility, outdated reader classes, unknown enum symbols, new field semantics, or an un-deployed service. Registry acceptance under a policy does not mean **every consumer** has a deployed build ready for v2. Distinguish deserialization failures from business-mapping failures.

### 14.4. Schema ID missing or deleted

A message still in a topic may reference a schema ID that can no longer be looked up. Never delete historical schemas arbitrarily while replayable data remains or while consumers may receive delayed messages from a DLQ.

### 14.5. Compatible schema, different event meaning

Changing `amountMinorUnits` from cents to major units while keeping `long` passes schema checks yet produces 100x wrong results. This is a **breaking semantic contract** requiring a separate event type or version and business review.

### 14.6. Expecting exactly-once from a schema registry

The registry provides metadata and schema validation only. It does not create atomic transactions between DB and Kafka, confirm consumer side effects, or prevent duplicates. Critical events require **transactional outbox + at-least-once publication + idempotent consumers**, paired with proper broker ACK/offset management.

## 15. Security and schema governance

A registry serving multiple teams requires governance:

- **Schema registration permissions:** restrict writers by subject and environment; do not let every app mutate contracts freely.
- **Auth/TLS:** encrypt transport and protect schema metadata, credentials, and API endpoints.
- **Naming conventions:** standardize topics, subject strategies, namespaces, event types, and ownership.
- **Compatibility policies:** configure deliberately per subject; changing a policy is a risky operation.
- **Schema reviews:** event owners and key consumers jointly review breaking changes.
- **Deprecation/retention:** know which old versions are still read from brokers/outboxes/DLQs or services.
- **CI enforcement:** run schema checks and semantic fixture tests before merge/release.
- **Monitoring:** schema registration error rates, serializer failures, cache misses, deserialization errors.
- **Data classification:** do not put passwords, tokens, or PII into events simply because the schema permits it.
- **Audit:** record who changed a schema/compatibility policy, when, and why.

Note: schemas themselves can reveal sensitive field names, data descriptions, or internal namespaces. Do not treat the registry REST API as a public service simply because it does not store full payload values.

## 16. Common mistakes

**Mistake 1 — Confusing subject version with schema ID.** Versions increment per subject; schema IDs are server-assigned, may differ, and may be reused for identical schemas.

**Mistake 2 — Using `schemaVersion` to order events.** Schema version describes payload layout; business ordering belongs to aggregate sequences/offsets by design.

**Mistake 3 — Thinking Spring `ApplicationEventPublisher` integrates with a registry automatically.** It only publishes objects to Spring listeners. Adapters, serializers, and broker clients are required across process boundaries.

**Mistake 4 — Treating `BACKWARD` as checking the full history.** The default is non-transitive. Use `BACKWARD_TRANSITIVE` when all historical versions must remain supported.

**Mistake 5 — Picking semantically wrong defaults.** Avro may decode cleanly yet produce incorrect business data. Defaults must be justified by historical contracts.

**Mistake 6 — Substituting generic schema compatibility for consumer contract tests.** The registry checks structure, not consumer validation or billing rules.

**Mistake 7 — Changing field semantics without changing the contract.** Two identical schemas can still be misread if units or event timing change.

**Mistake 8 — Deleting old schemas after deploying v2.** V1 data still in retention, DLQs, or event stores becomes undecodable.

**Mistake 9 — Adding `@Async` to turn an internal event into an integration event.** Async listeners still run in-process, with no schema registry, durable publishing, or automatic replay.

**Mistake 10 — Turning off compatibility in production to pass CI.** This shifts risk onto consumers and causes failures later.

**Mistake 11 — Assuming forward and backward compatibility are identical.** Always ask: “which version is the reader, and which version is the writer?”.

**Mistake 12 — Configuring `KafkaAvroSerializer` while forgetting the subject naming strategy.** Schemas may register under unexpected subjects, breaking lookups/compatibility.

**Mistake 13 — Testing v2 using synthetic data generated by the v2 serializer.** That does not prove v1 bytes can be read. Keep historical golden fixtures.

**Mistake 14 — Treating broker ACK as successful business processing.** Broker ACKs cover only the publish leg; consumer outcomes are a separate step.

**Mistake 15 — Lacking idempotency.** Producer/outbox relay retries and broker redeliveries can deliver the same event multiple times even when schemas are completely valid.

## 17. Schema versioning implementation checklist

1. Does the event type describe **the same business fact** across versions?
2. Are Avro/Protobuf/JSON Schema and the serialization format agreed upon?
3. Is the subject naming strategy explicit and consistent across producers/consumers?
4. Are schema ID, subject version, event type, `schemaVersion`, and `aggregateVersion` clearly separated?
5. Is the compatibility policy aligned with retention and rolling deployments?
6. If all historical versions must be replayed, is the policy genuinely transitive or backed by migration adapters?
7. Does every field define type, unit, nullability, default, and semantics?
8. Are defaults justified by historical business reality rather than guesses?
9. Have v2 readers been tested against v1 writers, and vice versa where full compatibility is required?
10. Have tests run with historical binary fixtures and real consumer code?
11. Does CI check registry compatibility before registration/deployment?
12. Are auto-registration, schema mutation permissions, and auditing controlled?
13. When breaking compatibility, is there a new event/topic/subject or migration plan?
14. Do producers/consumers handle registry outages, serializer failures, and cache behavior?
15. When zero event loss is required, are outbox/relay/retry/broker confirms in place?
16. Are consumers idempotent to tolerate retries/redeliveries and replays?
17. Are metrics/logs/traces capturing schema ID/subject/type while avoiding sensitive payload data?
18. Is there a deprecation schedule for old readers tied to retention and historical requirements?

**Conclusion:** Schema Registry is one piece of **cross-service data contract governance**. It helps producers/consumers look up schemas and blocks many incompatible structural changes. To safely integrate Spring Application Events out to a broker, you still need an internal→integration event adapter, versioned serialization, upgrade strategies, contract tests, transaction/durability handling, and idempotent consumers. **A compatible schema is a necessary condition, not sufficient proof that the system is semantically correct.**

## References

- [Confluent — Schema Evolution and Compatibility](https://docs.confluent.io/platform/current/schema-registry/fundamentals/schema-evolution.html): compatibility modes, transitivity, and rollout order.
- [Confluent — Schema Registry REST API](https://docs.confluent.io/platform/current/schema-registry/develop/api.html): registering schemas, looking up subjects/versions, and checking compatibility.
- [Confluent — Schema Registry REST Usage Examples](https://docs.confluent.io/platform/current/schema-registry/develop/using.html): `curl` examples and compatibility configuration.
- [Apache Avro — Specification](https://avro.apache.org/docs/current/specification/): records, default values, and schema resolution.
- [Apache Avro Java — SchemaCompatibility API](https://avro.apache.org/docs/current/api/java/org/apache/avro/SchemaCompatibility.html): checking reader schemas against writer schemas.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher` and `@EventListener`.
- [Spring Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): `KafkaTemplate` and handling send futures.
- [Spring Kafka — Receiving Messages](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/listener-annotation.html): `@KafkaListener`.
- [Microservices.io — Transactional Outbox](https://microservices.io/patterns/data/transactional-outbox.html): reducing dual-write and duplicate-publication risks.
