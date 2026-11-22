# Never Directly Deserialize Untrusted Object Data in Java

## 1. Nature of the Problem: Foreign Bytes Are Not Safe Objects

Java Object Serialization lets you write an object graph via `ObjectOutputStream.writeObject(...)` and read it back via `ObjectInputStream.readObject()`. Yet **reading back an object stream is not merely decoding data**: the JVM must resolve classes from stream descriptors, construct an object graph, restore fields, maintain reference handles, and potentially invoke special class hooks.

A very dangerous antipattern is:

```java
// DO NOT DO THIS with bytes from untrusted sources.
try (ObjectInputStream in = new ObjectInputStream(networkInput)) {
    Object value = in.readObject();
    if (value instanceof ExpectedMessage) {
        process((ExpectedMessage) value);
    }
}
```

This is **unsafe illustrative code**, not a standalone program; `networkInput`, `ExpectedMessage`, and `process` are assumed to exist. The `instanceof` check happens **after `readObject()` has already performed deserialization**, so it cannot stop unexpected classes from being processed during reading.

**Core principle of this lesson:** *Never directly reconstruct Java objects from untrusted data.* Prefer a data format with an explicit structure/schema and a reader bounding size, types, and resources; convert into DTOs or domain objects **after** validating the input. If compatibility with trusted legacy serialized data is unavoidable, apply class/depth/size filters, source authentication, resource bounds, and context-aware validation—yet never label that "completely safe."

### 1.1. What Counts as "Untrusted" Sources?

Not only HTTP requests arriving from the Internet:

- Bytes read from sockets, message queues, or services whose sender could be compromised.
- Uploaded files, files downloaded from URLs, email attachments, or user-selected content.
- Caches or object blobs stored in buckets, databases, queues, or filesystems where writers are not strictly inside the reader process's trust boundary.
- Legacy data written by another program version lacking integrity protection, signatures, source verification, or a clear compatibility plan.
- Content in multi-tenant environments where one tenant can influence another tenant's files or caches.
- Any byte stream that an adversary could substitute, truncate, partially tamper with, or replay.

A file ending in `.ser` or starting with `AC ED 00 05` only tells you it **looks like a Java serialization stream**. It does not prove the writer is trusted, the object graph is valid, or the classes to be loaded are safe.

## 2. Why Does `readObject()` Have Such a Large Attack Surface?

When `readObject()` processes a stream, it can:

1. Read class names and **class descriptors** embedded in the stream.
2. Ask the JVM to locate/restore the corresponding classes on the classpath/module path.
3. Instantiate objects and reference structures per Java serialization mechanics.
4. Restore non-transient fields, including deeply nested objects in the graph.
5. Run special serialization logic such as private `readObject`, `readResolve`, or corresponding validation callbacks.
6. Allocate arrays, object graphs, and structures far larger than the caller anticipated.
7. Trigger type mismatches, missing classes, exceeded limits, or malformed stream errors **while** restoration is already underway.

A **gadget chain** is a sequence of behaviors across classes already present in the application/libraries that deserialized data can trigger in ways unintended by developers. The risk does not require compiling new attack classes at runtime; ordinary classes already sitting on the classpath can carry dangerous side effects when driven through serialization.

This lesson **does not present exploit payloads or gadget-chain exploitation steps**. The key takeaway is: checking an object's type after `readObject` cannot block behavior that already occurred *before the method returned*.

### 2.1. Three Impact Categories to Defend Against

| Category | Example Risk | Defense Approach |
|---|---|---|
| Unintended code execution | Hooks/class graphs with side effects or unforeseen behavior | Avoid native deserialization; restrict allowed classes; minimize classpath |
| Resource exhaustion | Deep graphs, excessive references, huge arrays, drawn-out payloads | Cap bytes at transport layer; depth/references/arrays; CPU/time/memory quotas |
| Domain invariant violations | Null/out-of-range fields, objects in states impossible via constructors, unexpected references | Parse against a schema; validate every field; enforce invariants in constructors/factories; never trust raw post-deserialization fields |

Schema-based formats like JSON, CBOR, or Protocol Buffers **avoid automatically instantiating arbitrary Java graphs from stream class names** when implemented properly, yet they **are not automatically immune** to deep payloads, oversized inputs, misconfigured polymorphic typing, or parser library bugs. Switching formats is part of the solution, not an excuse to skip validation.

## 3. Distinguishing Deserialize, Parse, and Validate

A well-defended data pipeline separates these stages:

```text
[Untrusted input]
        │
        ▼
Cap size/timeout/format at ingress layer
        │
        ▼
Parse with fixed schema/format; do not instantiate arbitrary classes
        │
        ▼
Validate version, field types, length, range, UTF-8, invariants
        │
        ▼
Validated pure-data DTO
        │
        ▼
Domain object constructor/factory (least privilege)
        │
        ▼
Business logic
```

**Parsing** only turns bytes into a statically typed representation. **Validation** ensures that representation satisfies business rules. **Java object stream deserialization** goes further by building arbitrary object graphs and triggering custom object logic; that is why it is not a general-purpose input parser for adversarial sources.

A safer contract can look like:

```java
record IncomingMessage(String text, int sequence) {}

static IncomingMessage validate(String text, int sequence) {
    if (text == null || text.isBlank() || text.length() > 100) {
        throw new IllegalArgumentException("Invalid text");
    }
    if (sequence < 0) {
        throw new IllegalArgumentException("Negative sequence");
    }
    return new IncomingMessage(text, sequence);
}
```

This is an **illustrative snippet** placed inside a Java 17+ class; it does not read bytes on its own and has no `main`. Even after a parser extracts `String` and `int`, you must still verify ranges, required fields, and invariants.

## 4. Preferred Solution: Compact Data Format, Explicit Limits, No `readObject`

When the application controls the protocol, prefer transferring a fixed data record instead of a Java object graph. Example frame:

```text
Offset   Size         Content
0        4 bytes      magic = 0x4D534731 ("MSG1")
4        1 byte       protocolVersion = 1
5        4 bytes      sequence (signed int, big-endian)
9        2 bytes      textByteLength (unsigned short, big-endian)
11       N bytes      UTF-8 text, N <= 256
```

Benefits:

- Fixed types: only `sequence` and `text`, with no input-chosen class names.
- Both maximum string bytes and maximum frame size are bounded.
- UTF-8 decoder can be configured to reject malformed byte sequences.
- Protocol versioning is managed by the application, independent of `serialVersionUID`/Object Serialization Stream Protocol.
- Validators inspect raw fields before constructing domain objects.

**Critical caveat:** if input arrives over a network stream, **cap/truncate bytes as they arrive**, before allocating large arrays. Checking `byte[].length` only after accidentally buffering a 20 GB stream into RAM is already too late against memory exhaustion.

## 5. Runnable Java 17+ Example: Parsing a Well-Structured Frame

This example does not use `ObjectInputStream`. It writes and reads a frame with bounded length, magic header, version, and strict UTF-8 decoding. Invalid-length inputs are rejected **before allocating the payload array**.

**File:** `SafeFrameDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;

public class SafeFrameDemo {

    public record Message(String text, int sequence) {}

    public static byte[] encode(Message message) throws IOException {
        byte[] body = message.text()
                .getBytes(StandardCharsets.UTF_8);

        if (body.length > 256) {
            throw new IOException("text too long");
        }

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (DataOutputStream out = new DataOutputStream(bytes)) {
            out.writeInt(0x4D534731);   // "MSG1"
            out.writeByte(1);           // protocol version
            out.writeInt(message.sequence());
            out.writeShort(body.length);
            out.write(body);
        }
        return bytes.toByteArray();
    }

    public static Message decode(byte[] frame) throws Exception {
        // Cap total bytes before parsing.
        if (frame.length < 11 || frame.length > 512) {
            throw new IOException("invalid frame size");
        }

        try (DataInputStream in = new DataInputStream(
                new ByteArrayInputStream(frame))) {

            if (in.readInt() != 0x4D534731) {
                throw new IOException("invalid magic");
            }
            if (in.readUnsignedByte() != 1) {
                throw new IOException("unknown version");
            }

            int sequence = in.readInt();
            int length = in.readUnsignedShort();

            if (length > 256) {
                throw new IOException("invalid length");
            }

            byte[] body = new byte[length];
            in.readFully(body); // Fail if frame is missing bytes.

            // available() is only used to detect trailing bytes here
            // because the source is a ByteArrayInputStream holding the full frame.
            if (in.available() != 0) {
                throw new IOException("trailing bytes");
            }

            String text = StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(body))
                    .toString();

            if (text.isBlank() || text.length() > 100
                    || sequence < 0) {
                throw new IOException("invalid message fields");
            }

            return new Message(text, sequence);
        }
    }

    public static void main(String[] args) throws Exception {
        Message message = decode(
                encode(new Message("HELLO", 7)));

        System.out.println("message: " + message.text()
                + ", seq=" + message.sequence());

        byte[] invalid = encode(new Message("A", 7));

        // Two length bytes at offsets 9..10 become 0x03E7 = 999.
        invalid[9] = 3;
        invalid[10] = (byte) 0xE7;

        try {
            decode(invalid);
        } catch (IOException ex) {
            System.out.println("invalid length: rejected");
        }
    }
}
```

Compile and run on JDK 17+:

```bash
javac SafeFrameDemo.java
java SafeFrameDemo
```

**Expected stdout:**

```text
message: HELLO, seq=7
invalid length: rejected
```

### 5.1. Why Does This Design Reduce Risk?

1. The parser expects strictly magic, version, sequence, length, and UTF-8 bytes; there is no mechanism for input to tell the JVM to instantiate arbitrary Java classes.
2. `readUnsignedShort` explicitly treats length as an unsigned 16-bit integer, yet **still checks `<= 256`** before allocating `byte[]` instead of trusting the data-supplied length.
3. `readFully` rejects truncated frames rather than silently accepting partial text.
4. `ByteArrayInputStream` already holds the complete frame, so checking `available() != 0` works in **this specific case** to catch trailing bytes. Never use `available()` as an exact total-length check on a network stream.
5. `CharsetDecoder` with `CodingErrorAction.REPORT` rejects invalid UTF-8 instead of silently substituting replacement character `�`.
6. After decoding, baseline business rules (`text` non-blank, character count bound, non-negative `sequence`) are verified **before** constructing the record.
7. Malformed inputs raise clean `IOException`/decode errors without driving arbitrary class loading through Object Serialization.

**Scope of the example:** the method receives an already-buffered `byte[]`; real sockets need a framing layer plus **total incoming byte caps**, timeouts, and connection handling before calling `decode`. The example includes no authentication, replay protection, or integrity checksums; those must be built separately according to your threat model.

### 5.2. UTF-8 Byte Limits Differ from String Length Limits

`body.length` counts **bytes** after UTF-8 encoding. `text.length()` counts UTF-16 code units; the two numbers can differ significantly, especially for Vietnamese text and emojis. A protocol specification should clearly define whether limits apply in bytes or code points and check the corresponding unit.

When text carries security-sensitive values or must be digitally signed, specify canonicalization/normalization and encoding explicitly instead of expecting parsers to normalize Unicode automatically.

### 5.3. Even When Choosing JSON, You Must Still Constrain the Schema

Another option is sending JSON such as:

```json
{"version":1,"sequence":7,"text":"HELLO"}
```

The JSON parser should deserialize strictly into known data structures while bounding depth, bytes, string lengths, and numeric ranges, and **never enabling default polymorphic class resolution** on user-supplied data. After parsing, use DTO-validating constructors or factories. If a library offers payload-embedded class-name features to instantiate subclasses dynamically, enabling them carelessly recreates the exact same "input-chosen type" vulnerability in a different format.

## 6. When Is Using ObjectInputStream Still Considered?

For example, when an application must read legacy files written via `ObjectOutputStream` by **the controlled system itself** and maintain compatibility during a transition period. Before deciding to proceed, answer:

- Does the path from writer to reader protect **integrity and source authenticity**?
- Could any less-trusted actor swap files or blobs on the filesystem, database, queue, or backups?
- Which exact classes truly need to be constructed when reading a record?
- Do any of those classes have `readObject`/`readResolve`/`readExternal` hooks or side effects?
- Are upper bounds enforced on bytes, graph depth, reference counts, array sizes, and processing time?
- Do you actually need to read an arbitrary graph, or just extract 2–5 fields into a DTO?
- If a filter rejects a valid legacy file, is there a clear error-reporting and migration workflow?

Even for internal data, file exposure or loose write permissions can turn a "trusted local file" into an attack surface. Trust is a property of **the entire data pipeline**, not a filename.

## 7. `ObjectInputFilter`: Limiting Classes and Resources, Not Making Foreign Data Safe

In JDK 17/21, `ObjectInputFilter` helps constrain Java object reconstruction. It can evaluate:

- The class requested for instantiation when the filter is invoked.
- Graph depth.
- Number of references processed so far.
- Array length.
- Stream bytes consumed per filter metrics.

Three return statuses:

| `ObjectInputFilter.Status` | Meaning |
|---|---|
| `ALLOWED` | Condition allowed by this filter; does not replace validation |
| `REJECTED` | Rejected; active `readObject`/`readUnshared` typically aborts with `InvalidClassException` |
| `UNDECIDED` | Filter makes no decision; **does not mean REJECTED** |

A major pitfall is writing a filter that rejects dangerous classes and returns `UNDECIDED` for others thinking it denied them. When an allowlist is required, establish an **explicit reject policy** for unlisted classes, while accounting for all classes, references, arrays, and strings actually present in valid streams.

### 7.1. `setObjectInputFilter` Must Be Set Before Reading Objects

```java
try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
```

This is an illustrative snippet; `source` is an `InputStream`, `filter` is pre-built, and imports plus `IOException`/`ClassNotFoundException` handling are required. The filter must be configured **before the first object read**, not after `readObject`. In Java 17/21, `setObjectInputFilter` follows a one-time pre-read setting rule, and the final effective filter also depends on the JVM's **filter factory**.

**Crucial note:** the filter is not invoked for all primitive values and does not inspect String or field **contents**. `ObjectInputStream` documentation notes that Strings are handled specially and do not trigger class filtering like regular objects. Therefore, even when allowlisting only a DTO class, still check string lengths and contents **after restoration** and **before use**.

### 7.2. Pattern-Based Filters

`ObjectInputFilter.Config.createFilter(...)` supports string-based policies:

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
            "maxdepth=5;maxrefs=32;maxarray=256;maxbytes=8192;"
          + "com.example.legacy.dto.*;!*");
```

This is a policy configuration example, **not a standalone program**. `com.example.legacy.dto.*` is purely an illustrative namespace; real deployments must inventory the exact classes needed by the serialized graph, arrays, and library/framework types. The `!*` pattern denies classes not matched by the allowlist. Never broadly allow `java.base/*` or `java.*` just because "it's the Java standard library" if unneeded; an allowlist means permitting strictly required types only.

An overly strict policy rejects valid legacy data; an overly permissive policy leaves gadget surfaces exposed. Test against real serialized fixtures rather than assuming a filter string looks "safe enough."

### 7.3. Class-Specific Programmatic Filters

You can write an `ObjectInputFilter` targeting exact classes and limits instead of broad patterns:

```java
ObjectInputFilter filter = info -> {
    if (info.depth() > 5
            || info.references() > 20
            || info.streamBytes() > 4096
            || info.arrayLength() > 128) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();

    // Callbacks related to references/metrics have null type.
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == TrustedRecord.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

This snippet assumes a serializable `TrustedRecord` managed by a trusted system. If the full graph includes other classes, adjust the allowlist appropriately; never copy the snippet verbatim expecting arbitrary `List`, `Map`, array, and nested DTOs to work. Filter metrics also do not replace input size limits at the receive layer.

## 8. Runnable Java 17+ Example: Reading Trusted Legacy Data with a Filter

This example **accepts no adversary-controlled data**. It self-generates two in-memory payloads: a valid `Allowed` and an unlisted `Unexpected`. The reader caps total bytes before constructing `ObjectInputStream`, sets the filter **before `readObject()`**, permits strictly `Allowed.class`, bounds graph metrics, and validates fields after reading.

**File:** `FilteredLegacyDemo.java`

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class FilteredLegacyDemo {

    static final class Allowed implements Serializable {
        private static final long serialVersionUID = 1L;
        final String name;

        Allowed(String name) {
            this.name = name;
        }
    }

    static final class Unexpected implements Serializable {
        private static final long serialVersionUID = 1L;
    }

    static byte[] serialize(Object obj) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(obj);
        }

        return bytes.toByteArray();
    }

    static Allowed readTrusted(byte[] wire)
            throws IOException, ClassNotFoundException {

        // Demo guard; production must also enforce limits at the read layer.
        if (wire.length > 4096) {
            throw new IOException("frame too large");
        }

        ObjectInputFilter filter = info -> {
            if (info.depth() > 5
                    || info.references() > 20
                    || info.streamBytes() > 4096
                    || info.arrayLength() > 128) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            return type == Allowed.class
                    ? ObjectInputFilter.Status.ALLOWED
                    : ObjectInputFilter.Status.REJECTED;
        };

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(wire))) {

            in.setObjectInputFilter(filter);
            Object obj = in.readObject();

            if (obj.getClass() != Allowed.class) {
                throw new InvalidObjectException("unexpected type");
            }

            Allowed value = (Allowed) obj;

            if (value.name == null || value.name.length() > 40) {
                throw new InvalidObjectException("invalid name");
            }

            return value;
        }
    }

    public static void main(String[] args) throws Exception {
        Allowed record = readTrusted(
                serialize(new Allowed("trusted")));

        System.out.println("name: " + record.name);

        try {
            readTrusted(serialize(new Unexpected()));
        } catch (InvalidClassException ex) {
            System.out.println("unexpected class: rejected");
        }
    }
}
```

Compile/run:

```bash
javac FilteredLegacyDemo.java
java FilteredLegacyDemo
```

**Stdout:**

```text
name: trusted
unexpected class: rejected
```

### 8.1. What This Example Actually Verifies

- `Allowed` and `Unexpected` are **two test classes defined by the example itself**; there are no exploit payloads or external inputs.
- `readTrusted` checks the total length of the byte array **before** constructing `ObjectInputStream`.
- The filter enforces resource limits and **rejects any class other than `Allowed`**.
- `in.setObjectInputFilter(filter)` runs **before** `in.readObject()`.
- After reading, the code verifies the **exact** class and bounds `name`.
- The `String name` field still needs explicit validation because the filter does not validate individual string contents.
- `Unexpected` is rejected by the filter, raising `InvalidClassException` which is caught intentionally.

### 8.2. What This Example Does Not Prove

**Never** cite this example as proof that arbitrary Java object streams from the Internet become safe simply by attaching the same filter. Filters have limited scope: allowed classes still require auditing for hooks and side effects, complex graphs require different policies, and input origins, authentication, and timeouts lie outside this example.

A future change to `Allowed` might introduce new fields or a custom `readObject`. Matching the allowlist class name **does not** prove that class's code is safe against adversarial data. Thoroughly code-review and test every class on your allowlist.

### 8.3. Why Is This Self-Test Result Deterministic?

Both payloads are generated by `ObjectOutputStream` in the same process, so class descriptors match local classes without file or network dependencies. The output demonstrates only the class policy for two tiny objects. If the JVM configures a stricter global filter factory, additional rejections may occur per that policy—something you must test in your deployment environment.

## 9. Filters Do Not "Sanitize" Every Stream

Several limitations must be clearly understood:

| False Claim | Reality |
|---|---|
| "Filters inspect all field values." | Filters see class/graph metrics at callback points; not a schema/content validator |
| "Just check `instanceof` after `readObject`." | Object restoration already executed beforehand |
| "Any class in the allowlist is automatically safe." | That class or related operations may still contain side effects and bugs |
| "Returning `UNDECIDED` rejects the class." | `UNDECIDED` means no decision yet; configure an explicit reject policy |
| "`maxbytes` ensures requests cannot consume RAM outside the filter." | Filters run during deserialization; cap bytes early and enforce system quotas |
| "One global filter fits all use cases." | Each endpoint/context has distinct class/graph shapes requiring tailored policies |
| "Strings always pass through the filter for length checks." | Strings/primitives are handled differently; validate payloads explicitly |
| "JSON/CBOR can never cause DoS." | Other parsers also need resource limits and schema validation |

### 9.1. Global Filters and Context-Specific Filter Factories

Java supports JVM-wide serialization filters via system/security properties like `jdk.serialFilter` or configuration APIs. On Java 17+, the filter factory mechanism lets you tailor policies to each `ObjectInputStream`'s usage context.

**Illustrative** process configuration example:

```bash
java -Djdk.serialFilter="maxdepth=10;maxrefs=100;maxarray=1000;maxbytes=65536;com.example.dto.*;!*" MyApp
```

`MyApp` and `com.example.dto.*` are deployment placeholders, **not a command to run as-is**. A JVM-wide filter can affect libraries using serialization internally; inventory use cases and test thoroughly before enforcing a global policy. Never allow `java.base/*` globally just to avoid allowlist errors if doing so opens unnecessary surface area.

### 9.2. Filter Selection Order Matters

`ObjectInputStream` receives an initial filter from the **filter factory** during construction; calling `setObjectInputFilter` invokes the factory again to select or merge filters. If an application overrides the filter factory carelessly or produces a weaker policy, it risks stripping protections expected by other libraries.

Therefore:

- Assign clear application-level ownership for managing the filter factory.
- Do not let individual modules mutate the global filter factory at runtime.
- For each data stream, apply a filter matching its **context** and audit the effective policy.
- Test scenarios with both global filters and per-stream filters active.
- Log stream rejections without dumping sensitive payload contents.

### 9.3. Policy Design Flaws Inside Filters

For example, checking only the root class:

```java
Object root = in.readObject();
if (root.getClass() != Allowed.class) {
    throw new SecurityException("wrong root");
}
```

This snippet is **unsafe in isolation** because nested graphs have already been processed before inspecting the root. A proper filter must constrain **all classes allowed anywhere in the graph** along with resource limits, not just the top-level type. Even afterward, still validate invariants on both root and nested data.

## 10. Source Authentication and Integrity: Necessary, Not Sufficient

A system may protect data using mTLS, HMACs, digital signatures, or storage ACLs. These confirm bytes came from a valid source and were not silently altered in transit. Still:

- An authenticated source can be compromised or suffer bugs emitting malformed data.
- A legitimately signed blob can still exceed the reader's object/byte quotas.
- An older signed file may be incompatible with current class definitions.
- Integrity checks do not make a class's custom `readObject` safe.
- Authentication policies must also consider replay, key rotation, expiration, and version identifiers where domain rules require.

Thus, authentication/integrity is only **one layer**. It does not replace input validation, allowlists, resource bounds, or lean data design.

## 11. Serialization Hooks and Constructor Bypass

When a regular `Serializable` class is restored, **the serializable class's own constructor** does not run as in normal `new` calls. Field restoration occurs prior to business validation. Mechanisms such as:

- private `readObject(ObjectInputStream)`;
- `readResolve()`;
- `readObjectNoData()`;
- `ObjectInputValidation` callbacks;
- `Externalizable.readExternal(...)`;

may participate in object construction under their respective contracts.

### 11.1. Invariants Must Be Checked During Restoration

Example class allowing only non-negative quantities:

```java
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputStream;
import java.io.Serializable;

public final class Quantity implements Serializable {
    private static final long serialVersionUID = 1L;
    private int amount;

    public Quantity(int amount) {
        if (amount < 0) {
            throw new IllegalArgumentException("negative");
        }
        this.amount = amount;
    }

    private void readObject(ObjectInputStream in)
            throws IOException, ClassNotFoundException {
        in.defaultReadObject();

        if (amount < 0) {
            throw new InvalidObjectException("negative amount");
        }
    }
}
```

This is a **standalone compilable class** `Quantity.java` without a `main`. This validation hook is meaningful for data **already authorized** for deserialization, yet it **does not** make deserializing untrusted streams safe. Nor does it replace controlling side effects across the rest of the object graph.

### 11.2. Immutability Is Not Automatically Protected Across Serialization

`final` fields, private constructors, and factory methods are object-design tools, yet Java serialization follows specialized restoration rules; never assume that lacking public setters guarantees every deserialized object obeys invariants. For sensitive classes, minimize or eliminate direct deserialization and construct instances solely through factories consuming validated DTOs.

## 12. Handling Inputs from the Network

**Never** wrap a raw socket in `ObjectInputStream` merely because the sender claims "it's a valid object":

```java
// ANTI-PATTERN: do not use on sockets receiving untrusted data.
ObjectInputStream in = new ObjectInputStream(socket.getInputStream());
Object request = in.readObject();
```

Beyond the attack surface, `ObjectInputStream`'s constructor **blocks waiting for the stream header**, and `readObject` can hang indefinitely on incomplete data. A remote peer can trickle bytes slowly, never complete a frame, or exceed quotas.

Replace with a protocol providing:

1. Read timeouts, connection limits, and total maximum bytes.
2. Frame headers (magic/version/length) parsed safely first.
3. Length validation **before allocating**.
4. Fixed types/schemas; never resolve classes by input-supplied names.
5. Charset decoding with explicit error handling, verifying required fields and ranges.
6. Authentication/authorization where needed, plus per-sender message rate limits.
7. Backpressure, error telemetry, and closing connections on protocol violations.

### 12.1. Bounding InputStream Before readAllBytes

`InputStream.readAllBytes()` is convenient, yet on an untrusted, unbounded source it keeps reallocating until memory is exhausted. The same applies to `ByteArrayOutputStream` copying until EOF.

In length-prefixed protocols, allocate at most the allowed maximum size—and validate the prefix before trusting it. When reading unframed streams, wrap them in a counting/bounding wrapper enforcing hard caps with fail-closed semantics rather than checking RAM after exhaustion.

### 12.2. Compression and Nested Content

Even a 10 KB compressed payload can decompress into hundreds of MB or GB. Cap **decompressed size**, recursion/nesting depth, entry counts, and processing time. Never cap only compressed bytes and assume downstream parsers/deserializers cannot receive massive inputs.

## 13. Error Handling: Fail Closed Instead of "Trying Another Way"

Exceptions associated with Java deserialization:

| Exception | Possible Cause |
|---|---|
| `StreamCorruptedException` | Invalid stream header or control data |
| `InvalidClassException` | Incompatible class, or rejected by filter |
| `NotSerializableException` | Written graph includes a non-serializable object |
| `ClassNotFoundException` | Stream references a class absent from the reader environment |
| `OptionalDataException` | Mismatched object/primitive read or unexpected optional data |
| `EOFException` | Stream lacked sufficient bytes / ended prematurely during read |
| `InvalidObjectException` | Invariant or validation hook actively rejected the object |
| `IOException` | I/O failure or data reading error |
| `ClassCastException` | Root object differs from the type expected by the application |

Never turn these errors into "an empty valid payload." For `ObjectInputStream.readObject()`, documentation notes that exceptions leave the stream in an **indeterminate state**; close the stream and reject the message rather than skipping a few bytes and continuing as if nothing happened.

**Never automatically fall back** to "if deserialization fails, disable the filter and retry." A filter rejection is a security/policy signal. Log non-sensitive diagnostic metadata and investigate per incident procedures—never weaken validation just "to keep the program running."

## 14. Migrations: Safely Moving Off Java Serialization

A legacy system may already store many `.ser` files. Migrating formats is more than finding `readObject` and swapping in `parseJson`; it requires a structured plan:

### 14.1. Inventory Read Sites and Classify Sources

Locate every place receiving serialized objects:

- `ObjectInputStream.readObject` and `readUnshared`.
- Libraries/frameworks doing implicit deserialization, caching, RPC, or messaging.
- State files, sessions, job payloads, and serialized blobs in databases.
- Backups and historical data lacking retention/deletion policies.
- Consumers running different versions concurrently within the same system.

For each site, document origin, write permissions, expected class graphs, sizes, lifetimes, and trust levels. Never rely solely on file extensions or database table names.

### 14.2. Design the Replacement Format

Choose JSON, CBOR, Protocol Buffers, or a clearly specified binary format as appropriate; standardize:

- Message/schema versioning.
- Fixed field lists and types.
- Maximum sizes for the message and individual fields.
- Rules for optional, default, and unknown fields.
- Charsets, timezones, date/time formats, numeric bounds, and Unicode normalization.
- Integrity/authentication per your threat model.
- Backward/forward compatibility rules and deprecation plans for legacy versions.

### 14.3. Conversion Tooling in Controlled Environments

When legacy files still must be opened:

1. Run only on copies from authenticated, integrity-verified sources—never directly on untrusted uploads.
2. Use an audited JDK and minimal classpath with strict class/graph/resource filters.
3. Run the converter with least OS privileges, restricting network, filesystem, CPU/memory/time, and ensuring safe logging; isolation reduces blast radius without guaranteeing absolute safety.
4. Validate data after deserialization before writing the new format.
5. Test both valid and corrupted samples and support rollback if conversion fails.
6. After cutover, decommission obsolete `ObjectInputStream` entry points instead of leaving legacy endpoints open indefinitely.

If legacy inputs cannot be proven trustworthy and proper controls cannot be enforced, **refusing automated conversion** is safer than feeding them into critical production processes.

## 15. Common Design Mistakes

1. **Reading untrusted object streams merely because the class implements `Serializable`.** That is not a safety certification.
2. **Checking `instanceof` after `readObject` assuming exploitation was blocked.** Deserialization already ran beforehand.
3. **Trusting `.ser` file extensions or the `AC ED 00 05` magic header.** They identify format, not authenticity.
4. **Filtering only the root class.** Nested graphs can contain other classes already processed.
5. **Returning `UNDECIDED` for unlisted classes thinking it denies them.** An explicit reject policy is required.
6. **Allowing entire packages or Java modules unnecessarily.** Expands the class attack surface beyond actual needs.
7. **Omitting caps on arrays, depth, references, or bytes.** Exposes the system to resource exhaustion.
8. **Bounding bytes only after `readAllBytes`.** Unbounded allocation already happened before the check.
9. **Assuming filters validate String contents.** Field lengths and values still need explicit validation.
10. **Assuming allowlisted classes never have side effects.** Audit hooks and future class modifications.
11. **Authenticating the source without bounding format/resources.** Even an authenticated source can be compromised or buggy.
12. **Switching to JSON while enabling generic polymorphic deserialization for input-chosen classes.** Schema/type allowlists are still mandatory.
13. **Skipping malformed UTF-8 checks.** Corrupted bytes may silently turn into replacement characters.
14. **Trusting an input length prefix and allocating arrays immediately.** Attacker-controlled lengths must be bounded first.
15. **Ignoring trailing bytes or truncated data.** Invalid frames can be partially accepted.
16. **Letting parsers/converters block indefinitely on slow sockets.** Enforce timeouts and quotas.
17. **Silently evolving class versions without invariant checks.** Legacy data does not automatically fit new models.
18. **Catching filter errors and automatically disabling the filter/retrying.** Downgrades protective controls.
19. **Using `readObject` as a tool to probe unknown files.** Never deserialize just "to see what's inside."
20. **Logging raw serialized bytes or secrets on failure.** Leaks sensitive data; log sanitized error details only.
21. **Assuming a sandbox/process boundary alone suffices.** Combine least privilege, patching, runtime observability, and defense in depth.
22. **Ignoring filter policies of libraries using `ObjectInputStream` implicitly.** Entry points may hide outside endpoint code.
23. **Reusing one overly broad filter across all use cases.** Distinct contexts need distinct class sets and limits.
24. **Skipping tests for truncated files, deep graphs, and invalid fields.** Happy-path tests do not measure robustness.
25. **Assuming parsing into a Java record is sufficient.** Records enforce field types, yet business validation is still required.
26. **Treating every `IOException` while reading as recoverable on a broken stream.** `ObjectInputStream` may be in an indeterminate state.
27. **Confusing integrity checks with confidentiality.** Authenticated data can still be read unless encrypted and access-controlled.
28. **Trusting "internally stored" data as immutable.** Audit who can write to apps, backups, file shares, and queues.
29. **Failing to cap output size when decoding/decompressing.** Tiny inputs can expand massively.
30. **Having no plan to remove legacy endpoints.** Leaves dangerous deserialization paths exposed long after migrating most traffic.

## 16. Self-Check Questions

**Question 1.** Why is `(Expected) in.readObject()` dangerous on untrusted bytes?  
**Answer:** Before the cast executes, the JVM may already construct graphs, run deserialization logic, and allocate resources driven by the stream.

**Question 2.** Does verifying the file header `AC ED 00 05` prove a stream is safe?  
**No.** That is the protocol magic/version header, verifying neither source trust nor class graph safety.

**Question 3.** What approach should be prioritized for user-supplied API requests?  
**Answer:** A data protocol with fixed schemas/types, parsers bounding bytes and depth, and per-field validation.

**Question 4.** What can `ObjectInputFilter` constrain?  
**Answer:** Classes, array lengths, graph depth, reference counts, and consumed stream bytes per contract.

**Question 5.** If a filter returns `UNDECIDED`, is the class blocked yet?  
**Not yet.** That means undecided; to deny explicitly, return `REJECTED` per policy.

**Question 6.** Is calling `setObjectInputFilter` after `readObject` valid?  
**No.** The filter must be configured before reading objects per API rules.

**Question 7.** If only one DTO class is allowlisted, do you still need to validate `String name`?  
**Yes.** Filters do not check all primitive/String values; content, bounds, and invariants still require validation.

**Question 8.** Do `Future`/async transports automatically bound object stream length?  
**No.** Transport APIs and input framing need explicit quotas prior to deserialization.

**Question 9.** If `InvalidClassException` signals a filter rejection, should you keep reading from the same stream?  
**No.** Treat the stream as corrupted/untrusted, close it, and report an error; never auto-downgrade filters.

**Question 10.** Can the `available()` check in `SafeFrameDemo` measure total bytes on a network stream?  
**No.** There the source is a `ByteArrayInputStream` already holding the full frame; network streams require length-prefixing and bounded reads.

**Question 11.** Can digital signatures alone replace filters or schemas?  
**No.** Signatures establish integrity and origin per your threat model; graph/byte limits and validation are still needed.

**Question 12.** Where should mandatory conversion of legacy serialized files run?  
**Answer:** In a controlled environment on authenticated data, with a minimal classpath, strict filters, and bounded privileges/resources; write the new format and retire old read paths.

**Question 13.** Is `InputStream.readAllBytes()` safe for unbounded file uploads?  
**No.** It can allocate memory for the entire input; enforce hard caps at the ingress layer.

**Question 14.** Does a strict class filter guarantee allowed classes have no side effects?  
**No.** Code in allowed classes and hooks still requires auditing; filters do not validate behavioral safety.

**Question 15.** What is the legitimate role of Java Object Serialization when it must still be used?  
**Answer:** Compatibility with Java data/object graphs controlled by your own system, paired with strict boundaries and controls—**never** as the default input format from untrusted parties.

## 17. Conclusion and Official Documentation

**Takeaway:** "Do not deserialize just to check whether an object has the right type; deserialize only with an established trust basis, class/graph policy, and appropriate resource boundaries—and whenever you have a choice, use a data format with a schema-driven parser."

Decision flow:

```text
Can the source be controlled by an adversary?
    ├── Yes, or source trustworthiness is unproven
    │       └── DO NOT use ObjectInputStream.readObject directly
    │               └── Bounded framing → schema parser → validation → DTO
    └── Trusted legacy data requiring compatibility
            └── Inventory classes + authenticate source
                    └── Quota/input bounds + ObjectInputFilter
                            └── Validate output and audit allowed hooks
                                    └── Migrate to a stable data format
```

Official sources (Java SE 21, with the presented APIs applicable to Java 17+):

- `ObjectInputStream` — warnings on untrusted deserialization, `readObject` contract, and `setObjectInputFilter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html
- `ObjectInputFilter` — class/resource filtering, policy composition, and filter factories: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html
- `ObjectInputFilter.Config` — pattern filters and JVM-wide filters: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.Config.html
- `Serializable` — default serialization and class hooks: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html
- `DataInputStream` — bounded primitive/data reading for application-designed formats: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html
- `CharsetDecoder` — UTF-8 error handling policies: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
- Oracle Secure Coding Guidelines for Java SE, Serialization and Deserialization section: https://www.oracle.com/java/technologies/javase/seccodeguide.html
