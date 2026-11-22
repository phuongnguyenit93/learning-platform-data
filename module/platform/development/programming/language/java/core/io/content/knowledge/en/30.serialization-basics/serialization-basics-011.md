# Differences from Java-Independent Schema Exchange Formats

## 1. Serializing a Java Object Differs from Designing an Exchange Protocol

**Serialization** converts data state into bytes/text for storage or transmission; **deserialization** reads that representation back into data or objects. Java includes `ObjectOutputStream`, `ObjectInputStream`, and the `Serializable` interface. They implement the **Java Object Serialization Stream Protocol**, primarily aimed at restoring Java objects and object graphs.

By contrast, a **Java-independent schema exchange format** (such as JSON + data contract, Protocol Buffers, Avro, or a fully specified binary format) defines messages that Java, Go, Python, or JavaScript can produce and understand without needing the sender's Java classes themselves.

Distinguish two goals:

1. **Java-internal object persistence/transport:** restoring state and reference graphs under Java rules; the reading class must be compatible with the writing class's serial form.
2. **Interoperability and data contracts:** two applications, possibly in different languages and release cycles, exchanging business fields via agreed field identifiers, types, optional/default semantics, and wire encoding.

**Key point:** Java writing a `byte[]` does not automatically make the format Java-independent. Conversely, a codec written in Java can still conform to a Java-independent schema if the byte format is specified and tested outside the language.

## 2. The Java Object Serialization Mechanism

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

This is an illustrative class, not a standalone runnable program. `Serializable` is a marker interface; Java Object Serialization stores data according to the class's serial form. By default, eligible instance fields are serialized; `static` fields are not instance state, and `transient` fields are excluded from the default serial form. Special classes and hooks follow their own rules.

To write/read objects:

~~~java
try (ObjectOutputStream out = new ObjectOutputStream(destination)) {
    out.writeObject(profile);
}

try (ObjectInputStream in = new ObjectInputStream(source)) {
    Profile restored = (Profile) in.readObject();
}
~~~

This is **illustrative code**: `destination` and `source` are two streams backed by the same bytes, `profile` is declared, imports are present, and `IOException`/`ClassNotFoundException` are handled. `try-with-resources` closes the wrapped stream: appropriate when the code owns the stream, though verify the contract if the stream is borrowed from a caller.

When writing, the Java protocol can contain:

- Stream header and protocol control markers.
- Class descriptors carrying identities/serial forms of participating classes.
- Field data, object references, and handles preserving graph/alias structure.
- Custom data from `writeObject` or substitution/externalization mechanisms if supported by the class.

When reading, `ObjectInputStream` resolves classes in the Java runtime, checks serial form compatibility, and constructs objects. Hooks like `readObject` and `readResolve` can execute class-defined logic; this cannot be treated as merely "parsing JSON into a map."

A standard Java stream starts with header `AC ED 00 05` (hex). The header does not solve cross-language support: a non-Java consumer would still have to implement full Java serialization semantics and class/graph rules to read this kind of data.

### Data That Is Not Meaningfully Restored Automatically

Serialization does not turn a JVM resource into a live resource in another process. For instance, an open socket, running thread, file descriptor, or native lock is not meaningfully "cloned" just because a class implements `Serializable`. `transient` fields must be re-established as needed. With an object graph referencing non-serializable types, `NotSerializableException` can occur.

## 3. `serialVersionUID` Is Not an API Schema Version

`serialVersionUID` belongs to a **Java serializable class** and is used to verify compatibility between stream data and the local class during decoding. When omitted, Java can compute a default UID from class details; hence declaring it explicitly usually makes sense for classes intentionally using Java Serialization.

However:

- Keeping the UID unchanged **does not guarantee every class change is compatible**. Changing field types, class hierarchy, or custom serialization logic can break reading or semantics.
- Changing package/class names can break class resolution even if the business data looks identical.
- UID does not describe field numbers, data types, and defaults in a schema independently implementable in Python or Go.
- Never "fix" every `InvalidClassException` by making UIDs match and ignoring the underlying cause.

By contrast, a message's **schema version** is part of an exchange contract understandable across languages. A `Profile v2` DTO schema can add a `points` field without requiring internal Java classes to preserve packages, superclasses, or business methods.

Even a schema version **does not create compatibility by itself**; you must define behavior when new data carries unknown fields, old data omits fields, or a field changes meaning.

## 4. What Is a Java-Independent Schema?

A schema describes **data shape and interpretation rules** without needing to know the producer's runtime class. For example:

~~~text
Message: Profile
id      : signed 32-bit integer, required by business
name    : UTF-8 text, non-empty, max 1024 encoded bytes
points  : signed 64-bit integer, default 0 if omitted by agreed schema
Version : 1
Unknown-field handling, null/absence and invalid-input behavior are explicit
~~~

This is a conceptual specification, not the syntax of a specific schema framework. Wire data must further specify: encoding, byte order if binary, length framing, numeric overflow, nullability, unknown fields, versioning, timestamps/units, and validation conditions.

Unlike a Java serialized object, **the consumer does not need a `com.example.Profile` class**. A Python consumer can read `id`/`points`/`name` into its own struct or dictionary, as long as both sides enforce the agreed schema/wire contract.

Not every format inherently includes a full schema on its own:

- JSON provides syntax and basic data types without enforcing a schema; it is commonly paired with OpenAPI, JSON Schema, and application checks.
- Protobuf defines messages/field numbers in `.proto`, with multi-language codecs.
- Avro uses writer/reader schemas in schema resolution; a standalone binary datum may require transmitting the schema separately, whereas an object container file has a header format embedding the schema.
- A custom binary format can be Java-independent if **its specification** is published and verified across multiple implementations. `DataOutputStream` by itself is not a schema language.

## 5. Core Comparison Table

| Criterion | Java Object Serialization | Java-Independent Schema |
| --- | --- | --- |
| Primary focus | Java object/graph state | Message/DTO contract |
| Coupled to producer's Java classes | Yes, via serial form/class resolution | Not required |
| Wire format | Java Object Serialization protocol | JSON/Protobuf/Avro/custom specification |
| Go/Python/JS support | Not natively | Designed for support with matching codecs/schemas |
| Versioning | `serialVersionUID`, Java compatibility rules | Schema/wire version, field numbers/names, rules |
| Object identity/cycles | Protocol can preserve aliases/object graphs | Usually requires explicit graph modeling if needed |
| Long-term storage | Coupled to Java code/serial form | Can manage schema/migrations more stably |
| Input security | `readObject` carries object/gadget hook risks | Still needs parse limits/validation, yet usually does not instantiate arbitrary Java classes |
| Debugging | Binary and coupled to Java protocol | JSON is human-readable; binary schema codecs have tooling |
| Performance/size | Depends on object graph/protocol | Depends on codec and data; must benchmark |
| Schema evolution | Depends on class/serial-form changes | Has explicitly managed evolution rules |
| Coupling | Data format easily leaks internal Java models | Keeps external DTOs decoupled from domain models |

No format is automatically "safe/fast/universally compatible." The advantage of an independent schema is a **data contract reviewable and testable across languages, evolving separately from Java class internals**.

## 6. JSON with a Schema: Easy to Use Yet Requires Type Control

A JSON message:

~~~json
{
  "schemaVersion": 1,
  "id": 7,
  "name": "Lan",
  "points": 120
}
~~~

Java can produce it using a JSON library/codec; `ObjectOutputStream` is unnecessary. The contract must specify:

- Whether `id` is required and what its valid range is.
- Whether `points` is a signed 64-bit integer or another type. JavaScript `Number` cannot accurately represent integers above `2^53-1`; cross-language schemas need an appropriate strategy for longs/decimals.
- Whether `name` can be null or empty, what Unicode normalization applies, and byte/character limits.
- Whether unknown fields are rejected or ignored; how missing fields receive defaults.
- Timestamps/timezones, monetary units, identifiers, and enum values all require consistent rules.
- The parser must cap payload size/nesting and validate before mapping to domain types.

**JSON does not equal JSON Schema.** JSON Schema/OpenAPI and contract tests specify/verify requirements beyond JSON syntax. A decoder reading valid JSON that violates business rules must still reject it.

## 7. Protocol Buffers: Field Numbers Instead of Java Class Identity

A `profile.proto` file can declare:

~~~proto
syntax = "proto3";
package example.profile.v1;

message Profile {
  int32 id = 1;
  string name = 2;
  int64 points = 3;
}
~~~

The Protobuf compiler/runtime generates APIs for many languages. Field numbers are essential: `1` identifies the `id` field on the wire, `2` is `name`, `3` is `points`. Go/Java/Python consumers can interpret the same wire format using compatible schemas.

To evolve schemas safely:

1. Avoid changing field numbers for already-deployed fields.
2. When retiring a field, use `reserved` for the appropriate numbers/names to avoid reusing them with a different meaning.
3. For new fields, confirm how older consumers behave when ignoring unknown fields and whether business logic accepts that.
4. Be careful when changing field types, enums, `oneof`, or field presence.
5. In proto3, distinguish default scalar values from explicit presence; use `optional` or appropriate types when needed.
6. Maintain golden test vectors and backward/forward compatibility tests with real consumers.

Protobuf does not automatically provide authorization, input trust, transactions, or a schema registry. Those problems require application-level solutions.

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

Avro defines rules reconciling the **writer schema** (used when writing) and **reader schema** (expected by the consumer), permitting certain compatible changes without requiring identical Java classes.

Understand the limitations:

- A standalone Avro **binary datum** typically does not embed the full writer schema. Storing messages on a broker may require a schema registry/schema ID or passing metadata in the protocol.
- An Avro object container file has its own structure and header/schema metadata; do not assume every form of Avro data looks like a container file.
- Adding fields with defaults, renames/aliases, unions, and type promotions must follow specific rules. Incompatible changes can cause schema resolution to fail.
- Every consumer must still understand field **meaning**; successful decoding does not guarantee business semantics.

JSON, Protobuf, and Avro are all viable options in Java systems; the choice depends on ecosystem, observability, size, versioning, and performance benchmarks.

## 9. Complete Java 17+ Example: Two Ways to Write the Same Profile

The program below writes the same data in two formats:

1. **Java Object Serialization**: `ObjectOutputStream` writes an object with UID/class descriptor; `ObjectInputStream` reads it back in Java. The example includes a filter limiting classes and read resources.
2. **Binary wire format specified outside Java classes**: `DataOutputStream`/`DataInputStream` uses a magic header, version, big-endian fixed-width integers, and length-prefixed UTF-8. A decoder in another language can be implemented from the schema table in the next section.

**The second format is an illustrative protocol invented for this lesson**, not a commercial standard or Protobuf. Java-independence comes from the byte specification/validation rather than from using `DataOutputStream`.

Create **`SchemaExchangeDemo.java`**:

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

**Exact stdout**, compiled and verified on the JDK:

~~~text
Java header: ACED0005
Java roundtrip: 7|Lan|120
Wire magic: PRF1
Wire version: 1
Wire length: 27
Wire roundtrip: 7|Lan|120
~~~

Explanation:

- `ACED0005` is the Java Serialization Stream Protocol header; it does not describe a Java-independent exchange schema.
- `serialVersionUID=1L` is tied to the serial form of `SchemaExchangeDemo.Profile`; it is not a cross-language API version.
- `ObjectInputFilter` in the example permits a specific class and caps depth/references/bytes. Even so, **never treat this as proof that `ObjectInputStream` is safe for untrusted data**. In practice, avoid Java native deserialization across trust boundaries.
- The wire branch writes `PRF1` and version `1`; a consumer in any language can interpret them by following the published byte layout.
- `writeInt`/`writeLong` write numbers in **big-endian** order; the name is UTF-8 encoded, with length counted in **bytes**, not Java `String.length()`.
- Total size is **4 + 4 + 4 + 8 + 4 + 3 = 27 bytes** for the 3-byte UTF-8 name `Lan`.
- The illustrative decoder checks magic, version, max length 1024, missing bytes, and trailing bytes. `readFully` throws an error if the stream ends before the requested byte count.
- The example decoder uses `new String(bytes, UTF_8)`. That can replace malformed UTF-8 with replacement characters; systems needing to reject invalid UTF-8 must use `CharsetDecoder` with `CodingErrorAction.REPORT`.
- The example does not yet enforce business validation (`id` positive, `name` non-empty, `points` valid) and does not demonstrate live interop with Python/Go. Those are tests to add in real implementations.

### Wire Format v1 Byte Schema Table

| Position (byte offset) | Size | Type | Content |
| --- | ---: | --- | --- |
| 0–3 | 4 | ASCII | Magic `PRF1` |
| 4–7 | 4 | signed int32 big-endian | Version = 1 |
| 8–11 | 4 | signed int32 big-endian | `id` |
| 12–19 | 8 | signed int64 big-endian | `points` |
| 20–23 | 4 | signed int32 big-endian | UTF-8 byte length `0..1024` |
| 24 to end of length | Variable | UTF-8 | Bytes of `name`, without NUL terminator |

This format is **independent of Java implementation** when all producers/consumers follow the table. It **lacks field tagging, an unknown-field policy, or a schema registry**. If the v1 layout changes, old decoders will reject trailing bytes; you must bump the version and migrate code or move to a field-tagged format.

**Why not use `DataOutputStream.writeUTF`?** It uses **modified UTF-8** and a Java-specific length prefix, rather than standard UTF-8 encoding typically specified by cross-language schemas. A cross-language contract must explicitly document byte encoding and length prefixes as in the example.

## 10. Backward Compatibility and Forward Compatibility

When formats/schemas evolve, both questions must be answered:

- **Backward compatibility:** can a new reader read data produced by an old writer?
- **Forward compatibility:** can an old reader read data produced by a new writer?

Given schema v1:

~~~text
Profile v1: id, name
Profile v2: id, name, points
~~~

Decision table:

| Reader / Writer | Risk | Mitigation |
| --- | --- | --- |
| Reader v2 ← Writer v1 | Missing `points` | Defaults/optional handling per codec and business meaning |
| Reader v1 ← Writer v2 | Unknown `points` field | Unknown-field skip policy or compatible versioning |
| New reader ← Very old message | Multiple migration steps | Transitive compatibility/migration fixtures |
| Old reader ← Changed field type | Wrong decoder or business logic | Do not arbitrarily change field numbers/meanings; use a new version |

**Being able to read bytes does not mean business semantics are correct.** If a numeric field holds cents and a new version interprets it as dollars, both sides still parse numbers yet produce wrong results. Distinguish *wire compatibility* from *semantic compatibility*.

With Protobuf, field numbers/tagged fields allow skipping some unknown fields, though not every change is safe. With Avro, writer–reader schema resolution supports compatible changes. With JSON, unknown/default field behavior depends on the JSON decoder and contract. With the custom binary format in the demo, the v1 reader rejects trailing bytes, so simply appending a field at the end is **not forward compatible**.

A safe upgrade plan needs golden messages, upgrade/downgrade tests, and tracking of consumers still running older versions before shipping breaking changes.

## 11. Security: Why Shouldn't ObjectInputStream Receive Arbitrary Payloads?

Native Java deserialization does not merely parse primitive fields. `ObjectInputStream.readObject()` can instantiate objects, traverse object graphs, invoke hooks with side effects, and trigger class/library code. This creates gadget-chain, DoS, or unintended execution risks if the byte stream is attacker-controlled.

Principles:

1. **Do not use Java native serialized objects as the default input format for untrusted public HTTP/socket/message queues.**
2. Replace with DTOs/schemas and type-restricted codecs, then run business validation before use.
3. If legacy Java Serialization data must be supported, apply `ObjectInputFilter`/JDK filter factories, class allowlists, and caps on depth, refs, bytes, and array lengths; audit the entire classpath.
4. Filters are not sandboxes and do not eliminate all risk; isolate or eliminate Java object deserialization paths for untrusted inputs.
5. JSON/Protobuf/Avro also require payload size, nesting, and time limits along with parser hardening; codecs do not provide authentication or authorization.
6. Never deserialize old data of unknown origin just to "see if it reads"; migration environments must be isolated and protected.

Common Java Serialization exceptions:

| Exception | Common scenario |
| --- | --- |
| `NotSerializableException` | Writing an object ineligible for serialization |
| `InvalidClassException` | Incompatible serial form or class rejected |
| `ClassNotFoundException` | Java class to resolve is missing on the reader |
| `StreamCorruptedException` | Invalid stream header/protocol data |
| `ClassCastException` | Restored object differs from expected type |
| `EOFException`/`OptionalDataException` | Missing data or mismatched read order |
| `IOException` | Read/write failures and other I/O errors |

Never tweak UIDs blindly to mask `InvalidClassException`, disable filters because a sample fails, or swallow exceptions and treat a payload as processed.

## 12. Long-Term Storage and Model Evolution

A Java serialized object file saved a year ago can become unreadable after renaming packages/classes, changing field types, altering hierarchies, or changing custom serialization code. Even when readable at runtime, field semantics may have drifted.

When long retention or multiple consumers are required:

- Separate the **external message schema** from internal Java classes.
- Attach a schema version/schema ID in an appropriate envelope or container.
- Govern field add/remove/rename rules according to the chosen codec.
- Retain fixtures from older versions for regression tests.
- Run migrations reading old trusted data in a controlled environment, mapping to new DTOs, and validating.
- Define a rollback policy if a new producer writes data an older consumer does not yet understand.
- Separate integrity/authentication/durability/atomic publishing from the serialization contract.

A database schema is also a data contract; choosing an exchange schema format does not replace database migration management.

## 13. DTO Boundaries Instead of Exposing Java Domain Models

Do not automatically turn JPA entities or complex domain objects into network messages. A service can maintain an internal model:

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

- Changing internal implementations does not automatically break the external contract.
- Prevents leaking private/sensitive fields as domain classes grow.
- Provides a clear place to validate values, business invariants, and size limits.
- Decouples tests for mapping, codecs, and cross-language integration.
- Allows serving multiple API schema versions concurrently during migrations.

In return, you maintain extra DTOs, mappings, and schema governance. For multi-service or polyglot systems, that cost is usually far easier to manage than coupling the wire format directly to Java classes.

## 14. Migration Process Away from Java Serialization

A system storing `.ser` files, sessions, caches, or queues using Java Object Serialization cannot simply swap its reader to JSON/Protobuf and expect to read legacy bytes directly.

Steps:

1. Identify all places calling `writeObject/readObject` and the associated classes/serial UIDs.
2. Audit trust boundaries, data sources, retention periods, and deployed versions.
3. Design a new schema/DTO containing only necessary business fields; do not mirror every Java field.
4. Define IDs, defaults, versioning, unknown-field behavior, encoding, constraints, and error handling.
5. Build a dedicated migration adapter to read trusted legacy data under filters/resource limits; map to DTOs and validate.
6. Test/verify compatibility with message fixtures, contract tests, and at least one non-Java consumer if interop is a goal.
7. Deploy support for reading required versions; orchestrate dual-write/backfill/on-read migration with idempotency and rollback controls.
8. Monitor decode errors, unknown fields, message sizes, schema versions, and backlog data.
9. Remove native deserialization once no legacy data or consumers require it.

If formats must be distinguished during a transition period, use an explicit **format discriminator** (magic/version/schema ID). Do not repeatedly try every decoder on untrusted input by catching exceptions.

## 15. Common Misconceptions

| Misconception | Explanation |
| --- | --- |
| "If it's `Serializable`, Python can read it automatically" | Python lacks native Java Serialization protocol/class resolution |
| "`serialVersionUID` is an API schema version" | UID belongs to a Java class's serial form |
| "Keeping the UID will always read any class change" | Compatibility still depends on fields/types/classes and semantics |
| "JSON automatically has a schema" | JSON is syntax; schema/validation must be defined separately |
| "Protobuf field numbers can be changed freely" | Field numbers identify fields on the wire and must stay stable |
| "An Avro binary datum always embeds its schema" | It may require an external writer schema/schema ID |
| "`DataOutputStream` is a cross-language standard" | Byte layout, encoding, and versioning must be published |
| "`DataOutputStream.writeUTF` uses standard UTF-8" | It uses Java's modified UTF-8 |
| "If bytes decode, the data is valid" | Business rules and semantic compatibility must still be checked |
| "Protecting with `ObjectInputFilter` is enough" | Filters are not sandboxes for malicious input |
| "Having a schema eliminates migrations" | Breaking changes still require rollout and compatibility plans |
| "Wire-compatible always means semantically compatible" | Identical bytes can carry altered business meanings |
| "Binary is always smaller/faster than JSON" | Must benchmark with real data and codecs |

## 16. Format Selection Checklist

1. Are consumers non-Java or on independent deployment lifecycles?
2. Must data live for years and survive class/package refactoring?
3. Is the schema governed independently of Java implementations?
4. Are numeric types, encodings, timezones, null/absence, and enums specified?
5. Are length limits, nesting caps, input trust, and access controls defined?
6. Are field identifiers and rules against reusing retired fields established?
7. Are backward/forward compatibility tests and golden fixtures in place?
8. Is semantic validation performed after decoding?
9. Are explicit framing/schema IDs and rejection of unsupported versions defined?
10. Are external DTOs separated from ORM/domain objects?
11. Are migration and rollback procedures defined when changing schemas?
12. If using JSON, have 64-bit precision and decimals been accounted for?
13. If using Protobuf, are field presence/defaults and unknown fields understood?
14. If using Avro, is the source of the writer schema defined?
15. If using custom binary, are endianness, lengths, malformed inputs, and interop tests specified?

## 17. Self-Check Questions

1. Does `ObjectOutputStream` output JSON or Protobuf by default? **No**; it uses the Java Object Serialization Stream Protocol.
2. Does `serialVersionUID` let a Go program restore a Java object automatically? **No**.
3. Are Java serialized objects coupled to Java classes/serial forms? **Yes**.
4. Does JSON enforce that `points` is a signed 64-bit integer? **No**; schema/validation must specify it.
5. How does Protobuf identify fields? **Field numbers**.
6. Does an Avro binary datum always contain the full schema? **No**.
7. Why can the example's `PRF1` format be decoded by Python? Because byte layout, version, big-endian integers, and UTF-8 length prefix are **explicitly specified**.
8. Is `DataOutputStream.writeUTF` standard UTF-8 on the wire? **No**, it is modified UTF-8.
9. Does the v1 wire decoder automatically support appending a field after `name`? **No**, it currently rejects trailing bytes.
10. What is a new reader reading data from an old writer called? **Backward compatibility** in standard terminology.
11. What is an old reader reading data from a new writer called? **Forward compatibility**.
12. If a message decodes cleanly yet changes units from cents to dollars, is it still correct? **No**, semantics were broken.
13. Does `ObjectInputFilter` allow safely accepting arbitrary untrusted byte streams? **No**.
14. To migrate legacy Java serialized data to Protobuf, is swapping codecs alone enough? **No**, you must read legacy data under controls, map to DTOs, and encode anew.
15. Are multi-language consumer tests needed? **Yes**, when cross-language interoperability is a requirement.
16. Does a Java-independent schema mean no shared contract is needed? **No**; producers and consumers must share exact schema/wire semantics.

## References

- [Java SE 17 — ObjectOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectOutputStream.html), [ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): Java Serialization API.
- [Java SE 17 — Serializable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html): serial form and `serialVersionUID`.
- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): controlling deserialization resources/classes.
- [Java SE 17 — DataOutputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutputStream.html), [DataInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html): big-endian primitives and modified UTF-8.
- [Java Object Serialization Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/index.html): protocol and class evolution.
- [Protobuf proto3 language guide](https://protobuf.dev/programming-guides/proto3/): schemas, field numbers, and wire compatibility.
- [Apache Avro Specification](https://avro.apache.org/docs/current/specification/): binary encoding and schema resolution.
- [JSON Schema](https://json-schema.org/): schema description and validation.