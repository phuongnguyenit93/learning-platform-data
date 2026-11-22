# Differences from Java-Independent Schema-Based Interchange Formats

## 1. Serializing a Java Object Differs from Designing an Interchange Protocol

**Serialization** converts data state into bytes or text for storage or transmission; **deserialization** reads that representation back into data or objects. Java provides `ObjectOutputStream`, `ObjectInputStream`, and the `Serializable` interface. Together they implement the **Java Object Serialization Stream Protocol**, primarily aimed at reconstructing Java objects and object graphs.

By contrast, a **Java-independent schema-based interchange format** (such as JSON + data contract, Protocol Buffers, Avro, or a fully specified binary format) defines messages that Java, Go, Python, or JavaScript can produce and understand without needing the sender's Java classes.

Distinguish two goals:

1. **Internal Java object persistence/transport:** restores state and reference graphs according to Java rules; the reading class must be compatible with the writing class's serial form.
2. **Interoperability and data contracts:** two applications—potentially in different languages and on different release cycles—exchange business fields through agreed field identifiers, types, optional/default semantics, and wire encoding.

**Key point:** having Java write a `byte[]` does not automatically make the format Java-independent. Conversely, a codec written in Java can still conform to a Java-independent schema if the byte layout is specified and tested outside that language.

## 2. How Java Object Serialization Works

Example class:

~~~java
import java.io.Serial;
import java.io.Serializable;

final class Profile implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final int id;
    private final String name;

    Profile(int id, String name) {
        this.id = id;
        this.name = name;
    }
}
~~~

This is an illustrative class, not a standalone runnable program. `Serializable` is a marker interface; Java Object Serialization stores data according to the class's serial form. By default, eligible instance fields are serialized; `static` fields are not instance state, and `transient` fields are omitted from the default serial form. Special classes and hooks follow dedicated rules.

To write/read an object:

~~~java
try (ObjectOutputStream out = new ObjectOutputStream(destination)) {
    out.writeObject(profile);
}

try (ObjectInputStream in = new ObjectInputStream(source)) {
    Profile restored = (Profile) in.readObject();
}
~~~

This is **illustrative code**: `destination` and `source` are streams backed by the same bytes, `profile` is declared, with imports and handling for `IOException`/`ClassNotFoundException`. `try-with-resources` closes the wrapped stream: appropriate when the code owns the stream, though you should verify ownership contracts if the stream is borrowed from a caller.

When writing, the Java protocol may contain:

- Stream header and protocol control tags.
- Class descriptors containing identities/serial forms of involved classes.
- Field data, object references, and handles preserving graph/alias topology.
- Custom data from `writeObject`, or substitution/externalization data if supported by the class.

When reading, `ObjectInputStream` resolves classes in the Java runtime, checks serial-form compatibility, and constructs objects. Hooks such as `readObject` and `readResolve` can execute class-defined logic; this cannot be treated as merely "parsing JSON into a map."

A standard Java stream starts with header `AC ED 00 05` (hex). The header does not solve cross-language support: a non-Java consumer would still have to implement full Java serialization semantics and class/graph rules to read such payloads.

### Data That Does Not Restore Meaningfully on Its Own

Serialization does not turn a JVM resource into a live resource in another process. For example, a connected socket, running thread, file descriptor, or native lock is not meaningfully "cloned" merely because a class implements `Serializable`. `transient` fields must be re-established when needed. When an object graph references non-serializable types, `NotSerializableException` can occur.

## 3. `serialVersionUID` Is Not an API Schema Version

`serialVersionUID` belongs to a **Java serializable class** and is used to check compatibility between stream data and the local class during decoding. If omitted, Java computes a default UID from class details; hence declaring it explicitly is sensible for classes intentionally using Java Serialization.

However:

- Keeping the same UID **does not guarantee all class changes are compatible**. Altering field types, class hierarchies, or custom serialization logic can still break reading or semantics.
- Renaming a package or class can break class resolution even when business fields look identical.
- The UID does not describe field numbers, data types, or defaults in a schema independently implementable in Python or Go.
- Never "fix" every `InvalidClassException` by changing the UID to match while ignoring the underlying cause.

By contrast, a message's **schema version** is part of an interchange contract understandable across languages. A `Profile v2` DTO schema can add a `points` field without requiring internal Java classes to preserve package names, superclasses, or business methods.

Even a schema version **does not create compatibility by itself**; you must define behavior when new data carries unknown fields, old data lacks fields, or a field changes meaning.

## 4. What Is a Java-Independent Schema?

A schema describes **data shape and interpretation rules** without needing to know the producer's runtime class. Example:

~~~text
Message: Profile
id      : signed 32-bit integer, required by business
name    : UTF-8 text, non-empty, max 1024 encoded bytes
points  : signed 64-bit integer, default 0 if omitted by agreed schema
Version : 1
Unknown-field handling, null/absence and invalid-input behavior are explicit
~~~

This is a conceptual specification, not the syntax of a specific schema framework. Wire specifications must additionally define: encoding, byte order if binary, length framing, numeric overflow, nullability, unknown fields, version, timestamp/units, and validation rules.

Unlike a serialized Java object, **the consumer does not need a `com.example.Profile` class**. A Python consumer can read `id`/`points`/`name` into its own struct or dictionary, provided both sides implement the exact same schema/wire contract.

Not every format inherently includes a full schema:

- JSON provides syntax and basic types without enforcing a schema; it is typically paired with OpenAPI, JSON Schema, and application validation.
- Protobuf defines messages and field numbers in `.proto` with multi-language codecs.
- Avro uses writer/reader schemas during schema resolution; a standalone binary datum may require transferring schema info separately, whereas object container files include a header carrying the schema.
- A custom binary format can be Java-independent if its **specification** is published and verified across implementations. `DataOutputStream` by itself is not a schema language.

## 5. Core Comparison Table

| Criterion | Java Object Serialization | Java-independent schema |
| --- | --- | --- |
| Primary focus | Java object/graph state | Message/DTO contract |
| Tied to producer's Java classes | Yes, via serial form/class resolution | Not required |
| Wire format | Java Object Serialization protocol | JSON/Protobuf/Avro/custom specification |
| Go/Python/JS support | Not natively | Designed for it when suitable codec/schema is used |
| Versioning | `serialVersionUID`, Java compatibility rules | Schema/wire version, field numbers/names, rules |
| Object identity/cycles | Protocol can preserve aliases/object graphs | Usually modeled explicitly if needed |
| Long-term storage | Coupled to Java code/serial forms | Schema/migration can be managed more stably |
| Input security | `readObject` risks object/gadget hooks | Still needs parse limits/validation, yet avoids arbitrary Java class instantiation |
| Debugging | Binary and tied to Java protocol | JSON is human-readable; binary schema codecs have tooling |
| Performance/size | Depends on object graph/protocol | Depends on codec and data; must benchmark |
| Schema evolution | Depends on class/serial-form edits | Explicit, governed evolution rules |
| Coupling | Data format couples easily to internal Java models | External DTO can be decoupled from domain model |

No format is automatically "100% safe, fast, and compatible." The advantage of an independent schema is a **data contract that can be reviewed and tested across languages and evolved independently of Java class details**.

## 6. Schema-Backed JSON: Easy to Use Yet Requires Type Control

A JSON message:

~~~json
{
  "schemaVersion": 1,
  "id": 7,
  "name": "Lan",
  "points": 120
}
~~~

Java can produce it using a JSON library/codec without `ObjectOutputStream`. The contract should specify:

- Whether `id` is required and what range is valid.
- Whether `points` is a signed 64-bit integer or another type. JavaScript `Number` cannot accurately represent all integers above `2^53 - 1`; cross-language schemas need an explicit strategy for longs/decimals.
- Whether `name` can be null or empty, what Unicode normalization applies, and byte/char limits.
- Whether unknown fields are rejected or ignored, and how missing fields default.
- Consistent rules for timestamps/timezones, monetary units, identifiers, and enum values.
- Parsers must enforce payload size/nesting limits and validate before mapping to domain types.

**JSON does not equal JSON Schema.** JSON Schema/OpenAPI and contract tests specify and verify constraints beyond JSON syntax. A decoder reading syntactically valid JSON that violates business rules must still reject it.

## 7. Protocol Buffers: Field Numbers Instead of Java Class Identity

A `profile.proto` file may declare:

~~~proto
syntax = "proto3";
package example.profile.v1;

message Profile {
  int32 id = 1;
  string name = 2;
  int64 points = 3;
}
~~~

The Protobuf compiler/runtime generates APIs for many languages. Field numbers are essential: `1` identifies `id` on the wire, `2` is `name`, `3` is `points`. Go/Java/Python consumers interpret the exact same wire format using compatible schemas.

To evolve schemas safely:

1. Avoid changing field numbers for deployed fields.
2. When retiring a field, use `reserved` for its number/name to prevent reuse with a different meaning.
3. For new fields, verify how older consumers ignore unknown fields and whether business logic accepts it.
4. Be cautious when changing field types, enums, `oneof`, or field presence.
5. In `proto3`, distinguish default scalar values from explicit presence; use `optional` or appropriate types when needed.
6. Maintain golden test vectors and backward/forward compatibility tests with real consumers.

Protobuf does not automatically provide authorization, input trust, transactions, or a schema registry. Those require application-level solutions.

## 8. Apache Avro: Writer Schema and Reader Schema

A simple Avro schema:

~~~json
{
  "type": "record",
  "name": "Profile",
  "namespace": "example.profile",
  "fields": [
    {"name": "id", "type": "int"},
    {"name": "name", "type": "string"},
    {"name": "points", "type": "long", "default": 0}
  ]
}
~~~

Avro defines rules reconciling the **writer schema** (used when writing) and the **reader schema** (expected by the consumer), permitting certain compatible changes without requiring identical Java classes.

Limits to understand:

- A single Avro **binary datum** normally does not embed the full writer schema. When sending messages over a broker, you often need a schema registry/schema ID or out-of-band protocol metadata.
- Avro object container files have their own structure and schema header metadata; do not assume all Avro payloads look like container files.
- Adding fields with defaults, renames/aliases, unions, and type promotions must follow strict rules. Incompatible edits cause schema resolution to fail.
- Consumers must still understand field **meaning**; decodability does not guarantee business semantics.

JSON, Protobuf, and Avro are all viable options in Java systems; selection depends on ecosystem, observability, payload size, versioning, and performance benchmarks.

## 9. Complete Java 17+ Example: Two Ways to Write the Same Profile

The program below writes the same data in two formats:

1. **Java Object Serialization**: `ObjectOutputStream` writes an object with UID/class descriptor; `ObjectInputStream` reads it back in Java. The example includes a filter limiting classes and read resources.
2. **Binary wire format specified independently of Java classes**: `DataOutputStream`/`DataInputStream` writes magic header, version, big-endian fixed-width integers, and length-prefixed UTF-8. A decoder in another language can be implemented directly from the schema table in the next section.

**The second format is an illustrative protocol invented for this lesson**, not an industry standard or Protobuf. Java independence comes from specifying the bytes and validation explicitly, not merely from using `DataOutputStream`.

Create file **`SchemaExchangeDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;

public class SchemaExchangeDemo {
    private static final byte[] MAGIC = {'P', 'R', 'F', '1'};
    private static final int VERSION = 1;

    static final class Profile implements Serializable {
        @Serial private static final long serialVersionUID = 1L;
        final int id;
        final long points;
        final String name;

        Profile(int id, long points, String name) {
            this.id = id;
            this.points = points;
            this.name = name;
        }
    }

    static byte[] writeJava(Profile p) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(p);
        }
        return bytes.toByteArray();
    }

    static Profile readJava(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=20;maxbytes=4096;" +
                "SchemaExchangeDemo$Profile;java.base/*;!*"));
            return (Profile) in.readObject();
        }
    }

    static byte[] writeWire(Profile p) throws IOException {
        byte[] name = p.name.getBytes(StandardCharsets.UTF_8);
        if (name.length > 1024) throw new IOException("Name too long");
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.write(MAGIC);
            out.writeInt(VERSION);
            out.writeInt(p.id);
            out.writeLong(p.points);
            out.writeInt(name.length);
            out.write(name);
        }
        return bytes.toByteArray();
    }

    static Profile readWire(byte[] bytes) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(bytes))) {
            byte[] magic = new byte[4];
            in.readFully(magic);
            if (!Arrays.equals(magic, MAGIC)) throw new IOException("Bad magic");
            int version = in.readInt();
            if (version != VERSION) throw new IOException("Unsupported version");
            int id = in.readInt();
            long points = in.readLong();
            int length = in.readInt();
            if (length < 0 || length > 1024) throw new IOException("Bad length");
            byte[] nameBytes = new byte[length];
            in.readFully(nameBytes);
            if (in.read() != -1) throw new IOException("Trailing bytes");
            return new Profile(id, points,
                    new String(nameBytes, StandardCharsets.UTF_8));
        }
    }

    public static void main(String[] args) throws Exception {
        Profile original = new Profile(7, 120, "Lan");
        byte[] javaBytes = writeJava(original);
        byte[] wireBytes = writeWire(original);
        Profile restored = readJava(javaBytes);
        Profile exchanged = readWire(wireBytes);

        System.out.println("Java header: " +
                HexFormat.of().withUpperCase().formatHex(
                        Arrays.copyOf(javaBytes, 4)));
        System.out.println("Java roundtrip: " + restored.id + "|" +
                restored.name + "|" + restored.points);
        System.out.println("Wire magic: " +
                new String(Arrays.copyOf(wireBytes, 4), StandardCharsets.US_ASCII));
        System.out.println("Wire version: 1");
        System.out.println("Wire length: " + wireBytes.length);
        System.out.println("Wire roundtrip: " + exchanged.id + "|" +
                exchanged.name + "|" + exchanged.points);
    }
}
~~~

Compile and run:

~~~bash
javac SchemaExchangeDemo.java
java SchemaExchangeDemo
~~~

**Exact stdout**, compiled and run on a JDK:

~~~text
Java header: ACED0005
Java roundtrip: 7|Lan|120
Wire magic: PRF1
Wire version: 1
Wire length: 27
Wire roundtrip: 7|Lan|120
~~~

Explanation:

- `ACED0005` is the Java Serialization Stream Protocol header, not a Java-independent exchange schema.
- `serialVersionUID=1L` is tied to `SchemaExchangeDemo.Profile`'s serial form; it is not a cross-language API version.
- `ObjectInputFilter` in this example allows specific classes and limits depth/references/bytes. Even so, **never treat this as proof that `ObjectInputStream` is safe for untrusted data**. In practice, avoid Java native deserialization across trust boundaries.
- The wire branch writes `PRF1` and version `1`; any language's consumer can understand it by following the published byte layout.
- `writeInt`/`writeLong` write **big-endian** numbers; the name is UTF-8 encoded, with length measured in **bytes**, not Java `String.length()`.
- Total size is **4 + 4 + 4 + 8 + 4 + 3 = 27 bytes** for the 3-byte UTF-8 name `Lan`.
- The illustrative decoder checks magic, version, max length 1024, missing bytes, and trailing bytes. `readFully` throws if the stream ends before the requested byte count.
- The example decoder uses `new String(bytes, UTF_8)`. That replaces malformed UTF-8 sequences with replacement characters; systems needing strict rejection of invalid UTF-8 must use `CharsetDecoder` with `CodingErrorAction.REPORT`.
- The example does not yet enforce business validation (`id` positive, `name` non-empty, `points` valid) and does not demonstrate live interop with Python/Go. Those are tests to add in real implementations.

### Byte Schema Table for Wire Format v1

| Position (byte offset) | Size | Type | Contents |
| --- | ---: | --- | --- |
| 0–3 | 4 | ASCII | Magic `PRF1` |
| 4–7 | 4 | signed int32 big-endian | Version = 1 |
| 8–11 | 4 | signed int32 big-endian | `id` |
| 12–19 | 8 | signed int64 big-endian | `points` |
| 20–23 | 4 | signed int32 big-endian | UTF-8 byte length `0..1024` |
| 24 through length | Variable | UTF-8 | Bytes of `name`, no NUL terminator |

This format is **independent of Java implementation** as long as every producer and consumer follows the table. It has **no built-in field tagging, unknown-field policy, or schema registry**. If v1 layout changes, old decoders reject trailing bytes; you must bump the version and migrate code, or switch to a field-tagged format.

**Why not `DataOutputStream.writeUTF`?** It uses **modified UTF-8** and a Java-specific length prefix, not the standard UTF-8 encoding typically specified by cross-language schemas. Cross-language contracts must state byte encoding and length prefix explicitly as shown here.

## 10. Backward Compatibility and Forward Compatibility

When a format/schema evolves, answer both questions:

- **Backward compatibility:** can the new reader read data produced by the old writer?
- **Forward compatibility:** can the old reader read data produced by the new writer?

With schema v1:

~~~text
Profile v1: id, name
Profile v2: id, name, points
~~~

Mental matrix:

| Reader / Writer | Risk | Mitigation |
| --- | --- | --- |
| Reader v2 ← Writer v1 | `points` absent | Default/optional semantics per codec and business meaning |
| Reader v1 ← Writer v2 | Unknown `points` present | Unknown-field skipping mechanism or compatible versioning |
| New reader ← Very old message | Multiple migration steps | Transitive compatibility / migration fixtures |
| Old reader ← Changed field type | Decoder or business logic failure | Never repurpose field numbers/meanings arbitrarily; use a new version |

**Being able to parse bytes does not mean business semantics are correct.** If a numeric field held cents and a new version interprets it as dollars, both sides still parse numbers yet produce wrong results. Distinguish *wire compatibility* from *semantic compatibility*.

With Protobuf, field numbers/tagged fields allow skipping certain unknown fields, though they cannot rescue every edit. With Avro, writer–reader schema resolution supports compatible evolution. With JSON, unknown/default field behavior depends on the decoder and contract. With the demo's custom binary format, reader v1 rejects trailing bytes, so simply appending a field at the end is **not forward compatible**.

A safe version-upgrade plan requires golden messages, upgrade/downgrade tests, and tracking consumers still running older versions before shipping breaking changes.

## 11. Security: Why `ObjectInputStream` Should Not Accept Arbitrary Payloads

Native Java deserialization does not merely parse primitive fields. `ObjectInputStream.readObject()` can instantiate arbitrary classes, traverse object graphs, execute hooks with side effects, and trigger library code on the classpath. This creates gadget-chain, DoS, and unintended-execution risks if an attacker controls the byte stream.

Principles:

1. **Do not use Java native serialized objects as the default input format for untrusted public HTTP endpoints, sockets, or message queues.**
2. Replace with schema-backed DTOs and type-bounded codecs, followed by business validation before use.
3. If legacy Java Serialization must be supported, use `ObjectInputFilter`/filter factories per JDK, class allowlists, and bounds on depth, refs, bytes, and array lengths; audit the entire classpath.
4. Filters are not sandboxes and do not eliminate all risks; isolate and eliminate Java object deserialization paths from untrusted inputs where possible.
5. JSON/Protobuf/Avro also require payload size limits, nesting caps, timeouts, and parser hardening; a codec does not provide authentication or authorization.
6. Never deserialize legacy data from unknown sources just to "see if it reads"; migration environments must be secured.

Some Java Serialization errors:

| Exception | Typical scenario |
| --- | --- |
| `NotSerializableException` | Writing an object ineligible for serialization |
| `InvalidClassException` | Incompatible serial form or class rejected |
| `ClassNotFoundException` | Required Java class missing on the reader |
| `StreamCorruptedException` | Invalid stream header or protocol data |
| `ClassCastException` | Restored object differs from expected type |
| `EOFException`/`OptionalDataException` | Missing data or mismatched read order |
| `IOException` | Read/write errors and other I/O failures |

Never fudge UIDs to mask `InvalidClassException`, never disable filters just because a sample payload failed, and never swallow exceptions treating a failed payload as processed.

## 12. Long-Term Storage and Model Evolution

A Java serialized object file saved years ago can become unreadable after renaming packages/classes, changing field types, altering hierarchies, or changing custom serialization code. Even when the runtime decodes it, field semantics may have drifted.

When long-term persistence or multiple consumers are needed:

- Decouple **external message schemas** from internal Java classes.
- Attach schema versions/schema IDs in an appropriate envelope or container.
- Govern field add/remove/rename rules according to the chosen codec.
- Retain fixtures from older versions for regression testing.
- Run migrations reading old data in a controlled environment, transforming to new DTOs and validating.
- Maintain a rollback policy when new producers emit data older consumers do not yet understand.
- Separate integrity, authentication, durability, and atomic publishing from serialization contracts.

A database schema is also a data contract; choosing an exchange schema format does not replace database-layer migration management.

## 13. DTO Boundary Instead of Exposing Java Domain Models

Never automatically use JPA entities or complex domain objects as network messages. A service can maintain an internal model:

~~~text
Java domain: Account(id, balanceCents, riskFlags, persistenceState)
                       |
                       | mapping + validation
                       v
Public DTO: ProfileV1(id, name, points)
                       |
                       | JSON / Protobuf / Avro encoder
                       v
Wire bytes ---------> Consumer in another language
~~~

Benefits:

- Changing internal implementation does not automatically break the external contract.
- Prevents leaking private/sensitive fields as domain classes grow.
- Provides a clear place to validate values, business invariants, and size bounds.
- Separates mapping tests, codec tests, and cross-language integration tests.
- Allows running multiple API schema versions in parallel during migrations.

In return, you maintain extra DTOs, mappings, and schema governance. In multi-service or polyglot systems, this overhead is far easier to manage than coupling the wire format directly to Java classes.

## 14. Migration Workflow from Java Serialization

A system currently storing `.ser` files, sessions, caches, or queues using Java Object Serialization cannot simply switch its reader to JSON/Protobuf and expect to read legacy bytes directly.

Steps:

1. Locate every `writeObject`/`readObject` site and all involved classes/serial UIDs.
2. Audit trust boundaries, data sources, retention periods, and deployed versions.
3. Design a new schema/DTO containing only necessary business fields; do not blindly mirror every Java field.
4. Define IDs, defaults, versioning, unknown-field behavior, encoding, constraints, and error handling.
5. Build a dedicated migration adapter reading trusted legacy data behind filters/resource limits; map to DTOs and validate.
6. Measure/verify compatibility with message fixtures, contract tests, and at least one non-Java consumer if interop is a goal.
7. Deploy support for reading required versions; orchestrate dual-write, backfill, or on-read migration with idempotency and rollback controls.
8. Monitor decode errors, unknown fields, message sizes, schema versions, and migration backlog.
9. Remove native deserialization once no remaining data or consumers require it.

If formats must be distinguished during transition, use an explicit **format discriminator** (magic/version/schema ID). Never repeatedly try every decoder on untrusted input by catching exceptions.

## 15. Common Misconceptions

| Wrong claim | Explanation |
| --- | --- |
| "If it's `Serializable`, Python can read it automatically" | Python lacks Java Serialization protocol/class resolution out of the box |
| "`serialVersionUID` is an API schema version" | The UID belongs to a Java class's serial form |
| "Keeping the UID guarantees any class change stays readable" | Compatibility also depends on fields/types/classes and semantics |
| "JSON automatically has a schema" | JSON is syntax; schema/validation must be defined separately |
| "Protobuf lets you change field numbers freely" | Field numbers identify fields on the wire and must stay stable |
| "An Avro binary datum always embeds its schema" | Often requires an external writer schema or schema ID |
| "`DataOutputStream` is a cross-language standard" | You must publish byte layout, encoding, and version explicitly |
| "`DataOutputStream.writeUTF` uses standard UTF-8" | It uses Java's modified UTF-8 |
| "Decodable bytes mean valid data" | Must check business rules and semantic compatibility |
| "`ObjectInputFilter` protection alone is enough" | Filters are not a sandbox for malicious input |
| "Having a schema eliminates migrations" | Breaking changes still need rollout and compatibility plans |
| "Wire-compatible always means semantically compatible" | Identical bytes can carry different business meanings |
| "Binary is always smaller/faster than JSON" | Must benchmark with actual data and codecs |

## 16. Format Selection Checklist

1. Are consumers non-Java or on independent deployment lifecycles?
2. Must data survive for years across class/package refactorings?
3. Is there a schema governed independently of Java implementations?
4. Are rules defined for numeric types, encodings, timezones, null/absence, and enums?
5. Are length limits, nesting caps, input trust, and access controls in place?
6. Are field identifiers defined with a rule never to reuse retired fields?
7. Are backward/forward compatibility tests and golden fixtures in place?
8. Is semantic validation executed after decoding?
9. Are explicit framing/schema IDs and rejection of unsupported versions defined?
10. Are external DTOs separated from ORM/domain objects?
11. Is there a migration and rollback workflow for schema changes?
12. If using JSON, have 64-bit precision and decimals been accounted for?
13. If using Protobuf, are field presence/defaults and unknown fields understood?
14. If using Avro, is the source of the writer schema defined?
15. If using custom binary, are endianness, lengths, malformed inputs, and interop tests specified?

## 17. Self-Check Questions

1. Does `ObjectOutputStream` output JSON or Protobuf by default? **No**; it uses the Java Object Serialization Stream Protocol.
2. Does `serialVersionUID` allow a Go program to reconstruct Java objects automatically? **No**.
3. Is a Java serialized object tied to a Java class/serial form? **Yes**.
4. Does JSON automatically enforce that `points` is a signed 64-bit integer? **No**; schema/validation must enforce it.
5. How does Protobuf identify fields? **Field numbers**.
6. Does an Avro binary datum always carry the full schema? **No**.
7. Why can Python decode the example's `PRF1` format? Because byte layout, version, big-endian integers, and UTF-8 length prefix are **explicitly specified**.
8. Is `DataOutputStream.writeUTF` standard UTF-8 on the wire? **No**, it is modified UTF-8.
9. Does the v1 wire decoder automatically support appending a field after `name`? **No**, currently it rejects trailing bytes.
10. What is a new reader reading old writer data called? **Backward compatibility** in common terminology.
11. What is an old reader reading new writer data called? **Forward compatibility**.
12. If a message decodes cleanly yet changes units from cents to dollars, is it still valid? **No**, semantics changed.
13. Does `ObjectInputFilter` make accepting arbitrary untrusted byte streams safe? **No**.
14. To migrate old Java serialized data to Protobuf, is swapping codecs enough? **No**, you must read legacy data under controls, map DTOs, and re-encode.
15. Are multi-language consumer tests needed? **Yes**, if cross-language interoperability is a requirement.
16. Does a Java-independent schema mean no contract needs to be shared? **No**; producer and consumer must share the exact schema/wire semantics.

## References

- [Java SE 17 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html), [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): Java Serialization API.
- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): serial form and `serialVersionUID`.
- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): controlling deserialization resources/classes.
- [Java SE 17 — DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html), [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): big-endian primitives and modified UTF-8.
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html): protocol and class evolution.
- [Protobuf proto3 language guide](https://protobuf.dev/programming-guides/proto3/): schemas, field numbers, and wire compatibility.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): binary encoding and schema resolution.
- [JSON Schema](https://json-schema.org/): schema description and validation.
