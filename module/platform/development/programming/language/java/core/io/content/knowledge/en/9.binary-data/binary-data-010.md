# Distinguishing Custom Binary Formats from Java Serialization

When saving data as bytes or transmitting it over a network, Java offers at least two very different approaches:

1. **Designing a custom binary format**: the application defines exactly which bytes are written, their order, sizes, data types, versions, and decoding rules. You can use `DataOutputStream`/`DataInputStream`, `ByteBuffer`, or byte streams.
2. **Java Object Serialization**: uses `ObjectOutputStream` and `ObjectInputStream` to encode/restore a **Java object graph** via the platform's serialization mechanism, typically with classes implementing `Serializable`.

Both produce a sequence of bytes, yet their **purpose and data contracts** are quite different. A custom format is a *protocol/schema you own*; Java serialization carries extensive semantics tied to classes, objects, references, and Java compatibility.

This article focuses on choosing between them, implementation, compatibility, and handling untrusted data. All examples run on Java 17+.

## 1. Learning Objectives

After this article, you will be able to:

- Distinguish **serializing an object graph** from **encoding a binary schema**.
- Explain `Serializable`, `serialVersionUID`, `transient`, `ObjectOutputStream.writeObject`, and `ObjectInputStream.readObject`.
- Design a binary format containing magic, version, record count, integers, and length-prefixed UTF-8 strings.
- Use `DataOutputStream`/`DataInputStream` with matching write–read order, understand endianness, and handle `EOFException`.
- Distinguish standard UTF-8 from `writeUTF/readUTF`'s **modified UTF-8**.
- Enforce bounds on record counts, string lengths, and payload sizes, validating **before allocating**.
- Choose the appropriate storage mechanism when format stability, cross-language exchange, versioning, or external input handling is needed.
- Recognize the risks of Java deserialization on untrusted data and the bounded role of `ObjectInputFilter`.

## 2. High-Level Comparison

| Criterion | Custom Binary Format | Java Serialization |
| --- | --- | --- |
| Logical input | Values/fields per a defined schema | Java objects and object graphs |
| Typical tools | `DataOutputStream`, `DataInputStream`, `ByteBuffer` | `ObjectOutputStream`, `ObjectInputStream` |
| Byte layout | Defined and tested by you | Per the Java Object Serialization protocol |
| Java class names in format | Not required | Usually contains class descriptors/type info in stream |
| Shared references / cycles | Must design IDs/references yourself if needed | Object handles mechanism supports shared refs and cyclic graphs |
| Schema evolution | Self-defined versions, optional fields, migrations | Depends on serialization compatibility rules and class design |
| Readable by other languages | Possible, if specification is clear enough | Not a general cross-language exchange format |
| Size control | Tight, if format is minimal | Includes metadata/overhead; byte count hard to predict |
| Untrusted data | Can bound and validate per field; still guard against parser bugs | **Do not deserialize untrusted sources**; risk via classes/callbacks/gadgets |
| Suggested use cases | File/network protocols, firmware, schema-bound caches, long-term storage | Exchanging or storing Java object graphs in a **trusted** environment with controlled classes/versions |

**Do not equate** "Java serialization" with every act of turning Java data into bytes. A custom format, JSON, Protocol Buffers, or CBOR are all forms of serialization in the broad sense; in this article, **Java serialization** is used in the narrow sense of `ObjectOutputStream`/`ObjectInputStream` and the `Serializable` mechanism.

## 3. What Is a Custom Binary Format?

A binary format is a **byte contract** between writer and reader. For example, let us define a file holding a list of people:

~~~text
Header:
+------------------+------------------+------------------+
| magic: 4 bytes   | version: 2 bytes | count: 4 bytes   |
+------------------+------------------+------------------+

Each record:
+------------------+------------------+--------------------------+
| id: int32, 4 B   | nameLength: 4 B  | name: UTF-8, N bytes     |
+------------------+------------------+--------------------------+
~~~

You must specify **every detail**, rather than merely saying "write an integer and a string":

- **Magic**: four bytes `50 45 50 4C` (ASCII "PEPL") to identify payload type.
- **Version**: **unsigned** 16-bit integer, **big-endian** byte order; initial version is `1`.
- **Count**: signed 32-bit integer, big-endian, accepting only `0..1000`.
- **ID**: signed 32-bit integer, big-endian; meaning/value range must be specified by the application.
- **Name length**: signed 32-bit integer, big-endian, accepting only `0..4096` bytes.
- **Name**: exact `nameLength` bytes in standard UTF-8, **with no trailing NUL byte**.
- **Order**: write header first, then each record in sequence; no automatic separators or padding.
- **Termination**: for a standalone packed payload, no trailing data is permitted after `count` records; for streams carrying multiple consecutive frames, separate framing is required.

A custom format must explicitly define **endianness**, optional fields, nullability, data bounds, handling of unknown versions, missing-byte errors, and trailing data. A pair of encoder/decoder routines running on the same machine is **not enough** to make a reliable protocol if the byte specification remains ambiguous.

## 4. `DataOutputStream` and `DataInputStream`: Tools for Custom Formats

`DataOutputStream` has methods such as `writeByte`, `writeShort`, `writeInt`, `writeLong`, `writeBoolean`, `write(byte[])`; `DataInputStream` has matching read methods.

For multi-byte integers:

- `writeShort` writes two bytes; `writeInt` writes four bytes; `writeLong` writes eight bytes.
- These methods place the **most significant byte first** (*big-endian*), without varying by CPU.
- `readUnsignedShort` reads 2 bytes as an `int` in `0..65535`; suitable for unsigned versions.
- `readFully(byte[])` attempts to read **all** requested bytes or throws `EOFException` if the source ends early.
- A single `InputStream.read(byte[])` **does not guarantee** filling the array, so when exact N bytes are needed, `readFully` or an accumulating loop is vital.
- I/O methods can throw `IOException` on source/sink failures; `EOFException` indicates insufficient data when full bytes are required.

Decisive point: `DataOutputStream` **does not create a schema automatically**. If you write `writeInt(id)` then `writeInt(nameLength)` and name bytes, the decoder must read in the **exact same order**. Swapping positions causes data to be misinterpreted, even when both sides use the exact same Java classes.

### Do Not Assume `writeUTF()` Is Standard UTF-8

`DataOutputStream.writeUTF(String)` writes **two length bytes** followed by characters encoded in **modified UTF-8**, a variant of UTF-8. It has a maximum limit of **65,535 encoded bytes**, throwing `UTFDataFormatException` if exceeded. `DataInputStream.readUTF()` is its matching reader.

If a format must interoperate with non-Java software or specify standard UTF-8 strictly, a cleaner approach to specify is:

~~~java
byte[] bytes = text.getBytes(java.nio.charset.StandardCharsets.UTF_8);
out.writeInt(bytes.length);
out.write(bytes);
~~~

The reader must validate length before allocating, use `readFully`, and then decode UTF-8. The snippet above is a **code fragment** assuming `text` is a `String` and `out` is a declared `DataOutputStream`. `String.length()` measures **UTF-16 code units**, not UTF-8 bytes; never write `text.length()` as the byte length.

## 5. Java 17+ Example: Binary Format with Header, Version, and UTF-8

Create file **`CustomBinaryDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.EOFException;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.List;

public class CustomBinaryDemo {
    private static final int MAGIC = 0x5045504C; // "PEPL"
    private static final int VERSION = 1;
    private static final int MAX_RECORDS = 1000;
    private static final int MAX_NAME_BYTES = 4096;

    record Person(int id, String name) {}

    static byte[] encode(List<Person> people) throws IOException {
        if (people.size() > MAX_RECORDS) {
            throw new IOException("Too many records");
        }

        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (DataOutputStream out = new DataOutputStream(sink)) {
            out.writeInt(MAGIC);
            out.writeShort(VERSION);
            out.writeInt(people.size());

            for (Person person : people) {
                byte[] nameBytes =
                        person.name().getBytes(StandardCharsets.UTF_8);

                if (nameBytes.length > MAX_NAME_BYTES) {
                    throw new IOException("Name is too long");
                }

                out.writeInt(person.id());
                out.writeInt(nameBytes.length);
                out.write(nameBytes);
            }
            out.flush();
        }

        return sink.toByteArray();
    }

    static List<Person> decode(byte[] payload) throws IOException {
        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(payload))) {

            if (in.readInt() != MAGIC) {
                throw new IOException("Bad magic");
            }

            int version = in.readUnsignedShort();
            if (version != VERSION) {
                throw new IOException("Unsupported version: " + version);
            }

            int count = in.readInt();
            if (count < 0 || count > MAX_RECORDS) {
                throw new IOException("Invalid record count");
            }

            List<Person> result = new ArrayList<>(count);

            for (int i = 0; i < count; i++) {
                int id = in.readInt();
                int nameLength = in.readInt();

                if (nameLength < 0 || nameLength > MAX_NAME_BYTES) {
                    throw new IOException("Invalid name length");
                }

                byte[] nameBytes = new byte[nameLength];
                in.readFully(nameBytes);

                String name = StandardCharsets.UTF_8.newDecoder()
                        .onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT)
                        .decode(ByteBuffer.wrap(nameBytes))
                        .toString();

                result.add(new Person(id, name));
            }

            // Check EOF only because this payload is passed as an
            // independent byte[] message, not multiple combined frames.
            if (in.read() != -1) {
                throw new IOException("Unexpected trailing bytes");
            }

            return result;
        }
    }

    public static void main(String[] args) throws IOException {
        List<Person> people = List.of(
                new Person(7, "An"),
                new Person(9, "Bình")
        );

        byte[] encoded = encode(people);

        System.out.println("size=" + encoded.length);
        System.out.println(
                "magic=" + HexFormat.of().formatHex(encoded, 0, 4));
        System.out.println("decoded=" + decode(encoded));

        byte[] truncated = Arrays.copyOf(
                encoded, encoded.length - 1);
        try {
            decode(truncated);
            System.out.println("unexpected success");
        } catch (EOFException exception) {
            System.out.println("truncated=EOFException");
        }
    }
}
~~~

Compile (specifying source file encoding to preserve "Bình" across Java 17 environments) and run:

~~~bash
javac -encoding UTF-8 CustomBinaryDemo.java
java CustomBinaryDemo
~~~

**Stdout matching the program's Unicode content:**

~~~text
size=33
magic=5045504c
decoded=[Person[id=7, name=An], Person[id=9, name=Bình]]
truncated=EOFException
~~~

### Why Exactly 33 Bytes?

- Header: `4 + 2 + 4 = 10` bytes.
- First person: `4` bytes ID + `4` bytes length + `2` UTF-8 bytes of `An` = `10` bytes.
- Second person: `4 + 4 + 5 = 13` bytes because `Bình` needs 5 UTF-8 bytes: `B` (1), `ì` (2), `n` (1), `h` (1).
- Total: `10 + 10 + 13 = 33` bytes.

`HexFormat` has been included since Java 17; it only formats bytes for display and is not part of the protocol. `ByteArrayOutputStream` keeps results in memory, suitable for small demos. For large files, write via streaming and apply total-size/processing-time limits.

### Why Is This Decoder Safer Than Arbitrary Reading?

1. Checks magic to identify the format.
2. Rejects unsupported versions instead of guessing structure.
3. Validates count **before** allocating a list or looping.
4. Validates name length **before** allocating a byte array.
5. `readFully` enforces exact byte counts per name; early EOF becomes an error.
6. `CharsetDecoder` with `CodingErrorAction.REPORT` flags malformed UTF-8 instead of silently substituting invalid characters.
7. The trailing-bytes check applies to a **standalone payload**. If a protocol sends consecutive messages over a socket, reading an extra byte to "check EOF" will accidentally consume the next message or block; instead, decode the exact declared frame length.

This remains a teaching format: before production use, define valid ID ranges, empty/`null` names, **total** payload caps, checksums or authentication if needed, and behavior on corrupted data or new fields.

## 6. How Does Java Object Serialization Work Differently?

Java Object Serialization is designed to write and read **Java objects** and relationships between objects:

~~~java
ObjectOutputStream out = new ObjectOutputStream(outputStream);
out.writeObject(object);

ObjectInputStream in = new ObjectInputStream(inputStream);
Object restored = in.readObject();
~~~

This is a **code fragment** with existing byte source/sink and `object`; exceptions must be declared and resources closed according to ownership.

Key points:

- Classes intended for default serialization typically implement **`java.io.Serializable`**, a *marker interface* declaring no mandatory public methods.
- `ObjectOutputStream` writes data according to the **Java serialization stream protocol**, including class metadata and object data; it does not just write fields in the order you picture.
- An object graph can contain multiple objects, shared references, and cycles. A **handles** mechanism preserves proper reference relationships when writing/reading within the same stream.
- `ObjectInputStream.readObject()` reconstructs objects and may require corresponding Java class definitions; it can throw `ClassNotFoundException`, `InvalidClassException`, `StreamCorruptedException`, `IOException`, and other errors.
- Not every object is serializable. If a serialized field holds an instance of a non-serializable class, writing can throw **`NotSerializableException`**.
- **`static`** fields belong to the class, not per-object state for default serialization. **`transient`** fields are excluded from default serialization; post-read values must be restored or initialized by application logic if important.
- Extension hooks exist, such as `writeObject/readObject`, `readResolve/writeReplace`, and `Externalizable`. They add flexibility yet complicate serialization logic and increase risks when reading uncontrolled data.

You **do not control per-field byte offsets** simply by declaring `implements Serializable`. Another program not implementing the Java serialization protocol cannot simply read those bytes as an `int32 + UTF-8` sequence.

## 7. Java 17+ Example: Serializing Objects and Preserving Shared References

Create file **`JavaSerializationDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class JavaSerializationDemo {
    static final class Snapshot implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final int id;
        private final String name;

        Snapshot(int id, String name) {
            this.id = id;
            this.name = name;
        }

        @Override
        public String toString() {
            return "Snapshot[id=" + id + ", name=" + name + "]";
        }
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {

        Snapshot person = new Snapshot(7, "An");
        ByteArrayOutputStream sink = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(sink)) {
            out.writeObject(person);
            out.writeObject(person); // Same instance a second time.
        }

        // Only read data produced by THIS program itself.
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(sink.toByteArray()))) {

            Snapshot first = (Snapshot) in.readObject();
            Snapshot second = (Snapshot) in.readObject();

            System.out.println("first=" + first);
            System.out.println("sameReference=" + (first == second));
        }
    }
}
~~~

Compile and run:

~~~bash
javac JavaSerializationDemo.java
java JavaSerializationDemo
~~~

Stdout:

~~~text
first=Snapshot[id=7, name=An]
sameReference=true
~~~

Why is `sameReference=true`?

- `ObjectOutputStream` recognizes an object already written to the **same stream** and writes a reference to it instead of always emitting independent object contents.
- When `ObjectInputStream` reads that reference, it restores both locations pointing to the exact same object in the deserialized graph.
- This differs from two separate records in a custom format: identical `id/name` data **does not automatically** mean the same object identity after decoding.

In a custom format, if you need shared references or cycles, you usually must assign object IDs, represent relationships, and resolve references across multiple passes. When storing independent records, you typically **do not need** these semantics.

**Usage warning:** this demo serializes and deserializes the exact payload the program itself just created. Never replace the source in this example with bytes from the Internet, uploaded files, or untrusted content and call `readObject()` directly.

## 8. What Does `serialVersionUID` Help With—and Not Help With?

For normal serializable classes, `serialVersionUID` is a version identifier tied to class compatibility mechanisms:

~~~java
@java.io.Serial
private static final long serialVersionUID = 1L;
~~~

Declaring it explicitly avoids relying on a computed UID for the class; computed UIDs can shift from unintended declaration edits. However, **keeping the same UID does not automatically make every change compatible**.

For example:

- Adding or removing certain fields in compatible changes may be handled by default serialization per Java rules; new fields can receive default values.
- Changing class nature, field types, or inheritance hierarchies can break readability or semantics even if the UID is preserved.
- When stream and class UIDs mismatch, `InvalidClassException` may occur.
- `serialVersionUID` is **not a byte-format version number you specify**, nor is it a checksum, signature, or source-authentication measure.
- Application classes still must handle invariants, legacy data, and migrations when fields evolve.

In a custom format, version is written as **a header field** and your decoder dictates exactly how each version is read. In Java serialization, compatibility also hinges on class structure and Java's runtime mechanics; do not treat a UID alone as a guarantee of durable format stability.

## 9. Designing for Compatibility and Schema Upgrades

### Custom Binary Formats

You control the evolution strategy. For example:

- **V1**: `id:int32`, `name:utf8`.
- **V2**: add `age`, or switch to TLV (*type–length–value*) records so parsers can skip unrecognized fields.
- The decoder checks the header version, branches to the matching schema reader, and supplies deliberate defaults when reading old data.
- If old decoders must read new files, the format must design **forward compatibility** upfront, such as length-prefixed frames/fields and rules for skipping unknown parts.

Do not casually tack an `age` field onto the end of each V1 record in a stream lacking explicit record sizes: a V1 decoder will interpret the bytes of `age` as the start of the next record. Changing field counts without bumping version or having a skip mechanism easily corrupts files.

A practical schema should specify: supported versions, defaults for missing fields, required vs. nullable fields, ordered vs. unordered lists, maximum lengths, encodings, unknown-field policies, and migration procedures.

### Java Serialization

You retain some object-graph semantics, yet modifying class structure impacts reading old data. Beyond `serialVersionUID`, watch out for class/package names, field types, serializable fields, inheritance, and hook logic.

If data must be stored for 5–10 years, shared across service versions, or exchanged with Go/Python/Rust, prefer an **explicitly versioned protocol/schema** with independent docs and compatibility tests. Use a custom format when simple enough, or consider standardized format/schema tools when cross-language and complex evolution needs arise.

## 10. Security: Why Not Deserialize Java Objects from Untrusted Data?

**`ObjectInputStream.readObject()` does not merely read harmless fields.** Java deserialization can load/instantiate object types and trigger class mechanisms during graph reconstruction (e.g., relevant callbacks/hooks). When an application allows uncontrolled input to dictate which objects/classes get reconstructed, classes available on the classpath and associated behavior chains can create severe security risks.

This is why Oracle's documentation warns that **deserialization of untrusted data is inherently dangerous and should be avoided**. Core rules:

1. **Never use Java native deserialization on payloads supplied by untrusted parties**, even if you "inspected the first few bytes" or expect only one object type.
2. If a legacy system **must** deserialize, use `ObjectInputFilter`/serialization filtering suited to your Java version and context; restrict allowed classes, graph depth, reference count, array lengths, and bytes read.
3. Combine total payload limits, authentication/integrity, isolation, and classpath/callback audits; filters are one defense layer, **not a substitute** for secure protocol design.
4. Never treat `serialVersionUID`, `transient`, or casting to an expected class after `readObject` as protection against malicious payloads. Side effects can execute **before** the cast completes.
5. For endpoints receiving external data, prefer parsers for formats with strictly defined fields and constraints; validate all input lengths and received data before allocating or running business logic.

`ObjectInputFilter` has existed since Java 9 and supports filtering classes, arrays, and graphs, yet filter configuration must cover the **entire** graph and application security policy. Never deploy an overly permissive filter and assume absolute safety.

### Is a Custom Binary Format Automatically Safe?

**No.** A hand-written parser can still fail on negative lengths, huge counts, integer overflow in size arithmetic, truncated frames, malformed UTF-8, or payloads causing excessive memory allocation.

Minimum checks for external data:

- Cap total frame/payload sizes at the receiving layer before copying entire payloads into RAM.
- Validate magic, version, and all counts/lengths **before allocating** or looping.
- Use `readFully`/accumulating loops for fixed-length data; handle early EOF properly.
- Verify lengths fit within remaining bytes when decoding a self-contained payload.
- Reject malformed UTF-8 if required by the contract; define policies for invalid/unknown values.
- Specify checksums to catch accidental corruption when needed; **checksums generally do not prove a trusted sender**. Authenticating and resisting intentional tampering require appropriate cryptography.
- Bound CPU, nesting, cycles, and memory—not just a single string field.
- Treat the parser as an input boundary: errors must fail cleanly without triggering business side effects or unintended file overwrites.

The advantage of a simple format is that you **can strictly constrain which data types are created** (e.g., ints/strings/records) without letting the JVM instantiate arbitrary classes; safety still depends on parser implementation.

## 11. Common Mistakes When Reading/Writing Binary Data

### Mistake 1: Writing and Reading in Different Orders

~~~java
// Writer:
out.writeInt(12);
out.writeLong(999L);

// WRONG Reader:
long x = in.readLong();
int y = in.readInt();
~~~

Both sides must agree on field order. This is a **code fragment** with suitable `out` and `in`; reversing as above misinterprets data with zero compile errors.

### Mistake 2: Confusing Byte Length with Character Count

~~~java
String name = "Bình";
int wrongLength = name.length(); // 4 UTF-16 chars, yet 5 UTF-8 bytes
byte[] utf8 = name.getBytes(java.nio.charset.StandardCharsets.UTF_8);
int correctLength = utf8.length;  // 5
~~~

If the header records 4 while the payload is 5 bytes, every subsequent field shifts out of alignment.

### Mistake 3: Calling `read(byte[])` Only Once

A single `read` can return fewer bytes than requested. When the schema specifies name length `N`, loop until all `N` bytes arrive or use `DataInputStream.readFully`. Mid-way EOF must be a truncated-frame error, not padded with null characters.

### Mistake 4: Allocating Before Checking Length

~~~java
int length = in.readInt();
// WRONG if length comes from untrusted data:
byte[] bytes = new byte[length];
~~~

`length` may be negative or huge. Validate domain bounds, total payload, and allowed memory before allocating.

### Mistake 5: Using `writeUTF` as General-Purpose UTF-8

`writeUTF` uses modified UTF-8 with a 2-byte length and 65,535-byte cap; do not write it and feed it to a non-Java standard UTF-8 decoder. If you choose modified UTF-8, state so in the specification and pair with `readUTF`.

### Mistake 6: Thinking `Serializable` Means "Permanently Stable"

Class changes, graph changes, and compatible-serialization rules can alter readability. `serialVersionUID` does not handle migrations or preserve business semantics automatically.

### Mistake 7: Assuming Java Serialization Emits Identical Bytes for Equal Values

A stream can contain class descriptors, references, and state dependent on write sequence. Do not write tests guessing byte sizes or doing raw byte comparisons like a hand-crafted canonical format. To test Java serialization, verify object round-trips and preserved reference/invariant relationships.

### Mistake 8: Feeding Untrusted Bytes to `readObject`

Never use `ObjectInputStream` as a general decoder for external input. Use bounded schema/parsers and security policies; serialization filtering is only for unavoidable legacy cases and is **one part** of defense.

### Mistake 9: Forgetting to Distinguish Format from Transport

TCP is a **byte stream** with no built-in message boundaries. One `write` on the sender does not necessarily correspond to one `read` on the receiver. Frame lengths/terminators and partial-read/timeout handling are required. Two programs both using `DataInputStream` do not automatically establish message framing.

### Mistake 10: Thinking Magic/Version/Length Policies Guarantee Integrity

Magic identifies the format, version guides compatible decoding, length marks boundaries; they are **not** proof that data was unaltered. Formats guarding against accidental errors can use checksums; authenticating peers and contents requires an appropriate authentication protocol/MAC.

## 12. When to Choose Which Approach?

**Choose a binary format with a self-defined schema** when you need:

- Readability from both Java and other languages, or data existing independently of a specific class.
- Compact formats with clear byte order, easily tested via hex vectors/golden files.
- Exact control over versions, fields, bounds, framing, and backward/forward compatibility.
- External file/network data requiring a parser with a finite set of data types.
- Embedded devices, optimized binary payloads, or protocols with an existing specification.

**Consider Java serialization** when:

- You must preserve object graphs and shared references between Java objects.
- Both ends are **trusted** Java environments controlling the classpath, serializable classes, and versions.
- Data lifetimes are short, or clear compatibility/migration strategies exist.
- Overhead and coupling to the Java class model are acceptable, and deserialization risks have been evaluated.

For public APIs, long-term storage, cross-language communication, or external user input, choosing a schema independent of Java's implementation is usually better. When schemas grow complex, you do not always have to hand-roll a parser: specified tools/formats such as Protocol Buffers, Avro, CBOR, etc. can manage the protocol (each with its own limits and compatibility model).

## 13. Process for Designing a Reliable Binary Format

1. **Define the use case**: standalone file, multi-frame stream, network payload, or cache? Are random seeking and compression required?
2. **Write the byte specification**: magic, version, endianness, numeric types (signed/unsigned), charset, lengths, nullability, field order, trailing bytes, and frame boundaries.
3. **Choose a version policy**: when to increment versions, how to read old versions, how to skip unknown fields, whether batch migration is needed?
4. **Set bounds**: max frame, record, field, name byte length, nesting, total allocation, and processing time.
5. **Write schema-driven encoder/decoder independently**: never pass uncontrolled object graphs straight to receivers.
6. **Create golden vectors**: for a small record, lock in expected hex bytes; decoder must read accurately, encoder must emit identically. Test Vietnamese/Unicode, zero lengths, and boundary values.
7. **Test malformed/corrupted inputs**: bad magic, unknown version, negative count, oversized length, missing single byte, trailing data, malformed UTF-8, overflow.
8. **Verify interoperability**: if clients exist in other languages, run cross-implementation round-trips rather than testing only a single implementation against itself.
9. **Define failure semantics**: partially written files, checksums, atomic replacement, timeouts, retries, and connection drops.
10. **Maintain the spec like a public API**: versioned changes, docs, fixtures, and legacy-data support policies.

## 14. Self-Check Questions

**1.** Two services currently use Java. If Python might read the bytes in the future, what should you choose?  
**Answer:** A format with a Java-independent schema and encoding specification (custom-designed or standardized), rather than assuming native Object Serialization suits Python.

**2.** Which endianness does `DataOutputStream.writeInt` use?  
**Answer:** Big-endian (most significant byte first). If a format requires little-endian, design/implement it explicitly, such as using `ByteBuffer.order(ByteOrder.LITTLE_ENDIAN)` appropriately.

**3.** Why is `writeUTF("Bình")` not the same as `write(getBytes(UTF_8))`?  
**Answer:** `writeUTF` prepends a 2-byte length and uses modified UTF-8, whereas `getBytes(UTF_8)` produces standard UTF-8 bytes without adding a length prefix.

**4.** `ObjectOutputStream` writes the same instance twice into the same stream; do the read objects preserve reference equality?  
**Answer:** Normally yes, thanks to handles in Java serialization; the `sameReference=true` demo illustrates this behavior.

**5.** Does specifying `serialVersionUID = 1L` guarantee reading all versions of a class?  
**Answer:** No. You still must follow Java serialization compatibility rules and maintain invariants/migrations for actual changes.

**6.** After reading `nameLength` from an untrusted file, what is the next step?  
**Answer:** Validate the legal range, maximum limit, remaining frame bytes, and memory budget; only then allocate and call `readFully`.

**7.** Should you call `new ObjectInputStream(socket.getInputStream()).readObject()` on uncontrolled client data?  
**Answer:** No. Java deserialization on untrusted data carries high risk; use a controlled schema/parser with appropriate authentication and bounds.

**8.** Does a custom format need a version if today there is only one record type?  
**Answer:** If data may be stored long-term or exchanged across versions, include a version policy from the start so future changes can be detected and handled.

**Takeaway:** `DataInputStream`/`DataOutputStream` are **tools to implement a byte format you control**. `ObjectInputStream`/`ObjectOutputStream` are **Java's mechanism for reading/writing object graphs**. Choose based on data contract, longevity, compatibility, schema ownership, and source trustworthiness—never solely because one API takes fewer lines of code.

## Java 17 API References

- [DataOutput — primitive encodings and modified UTF-8](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataOutput.html)
- [DataInputStream — reading binary data](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/DataInputStream.html)
- [ObjectInputStream — Java serialization and untrusted data warning](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html)
- [ObjectInputFilter — class filtering and graph limits during deserialization](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html)
