# Never Directly Deserialize Untrusted Object Data in Java

## 1. Nature of the Problem: Unknown Bytes Are Not Safe Objects

Java Object Serialization allows writing an object graph using `ObjectOutputStream.writeObject(...)` and reading it back using `ObjectInputStream.readObject()`. Yet **reading an object stream is not merely decoding data**: the JVM must resolve classes from stream descriptors, construct an object graph, restore fields, maintain reference handles, and potentially invoke special class mechanisms.

A very dangerous anti-pattern is:

```java
// DO NOT DO THIS with bytes from an untrusted source.
try (ObjectInputStream in = new ObjectInputStream(networkInput)) {
    Object value = in.readObject();
    if (value instanceof ExpectedMessage) {
        process((ExpectedMessage) value);
    }
}
```

This is **unsafe illustrative code**, not a standalone program; `networkInput`, `ExpectedMessage`, and `process` are assumed to exist. The `instanceof` check executes **after `readObject()` has already performed deserialization**, so it does not prevent unwanted classes from being processed during reading.

**Core principle of this lesson:** *Never directly deserialize Java objects from untrusted data.* Prefer a clearly structured/schema-defined data format with a reader bounding size, types, and resources; convert to DTOs or domain objects **after** validating input. If forced to maintain compatibility with trusted legacy serialized data, apply class/depth/size filters, source authentication, resource caps, and contextual validation — and never call that "absolute safety."

### 1.1. What Sources Count as "Untrusted"?

Not only HTTP requests arriving from the Internet:

- Bytes read from sockets, message queues, or services whose sender could be compromised.
- Uploaded files, URL downloads, email attachments, or user-selected content.
- Caches/object blobs stored in buckets, databases, queues, or filesystems where writers are not strictly inside the reading process's trust boundary.
- Legacy data written by another program version without integrity protection, signatures, source control, or a clear compatibility plan.
- Content in multi-tenant environments where one tenant can influence another tenant's files/caches.
- Any byte stream that an adversary could substitute, truncate, partially modify, or replay.

A file with a `.ser` extension or starting with `AC ED 00 05` only tells you it **looks like a Java serialization stream**. It does not prove the writer is trusted, the object graph is valid, or the classes loaded will be safe.

## 2. Why Does `readObject()` Have Such a Large Attack Surface?

When `readObject()` processes a stream, it can:

1. Read class names and **class descriptors** embedded in the stream.
2. Ask the JVM to locate/load matching classes on the classpath/module path.
3. Instantiate objects and reference structures according to Java serialization mechanics.
4. Restore non-transient fields, including nested objects across the graph.
5. Execute special serialization logic, such as private `readObject`, `readResolve`, or corresponding validation callbacks.
6. Allocate arrays, object graphs, and structures far larger than the caller expects.
7. Encounter type mismatches, missing classes, exceeded limits, or invalid stream states **while** restoration is already underway.

A **gadget chain** is a sequence of behaviors across classes already present in the application/libraries that deserialized data can trigger in ways the developer never intended. The risk does not require compiling new attacker classes at runtime; classes sitting on the classpath can carry dangerous side effects when driven through serialization.

This lesson **does not present exploit payloads or how to weaponize gadget chains**. What you must grasp is: checking an object's type after `readObject` cannot block behavior that happens *before the method returns*.

### 2.1. Three Impact Categories to Defend Against

| Category | Example Risk | Defense Direction |
|---|---|---|
| Unintended logic execution | Hooks/class graphs with side effects or unforeseen behavior | Avoid native deserialization; restrict allowed classes; minimize classpath |
| Resource exhaustion | Deep graphs, excessive references, huge arrays, drawn-out payloads | Cap bytes at transport layer; bound depth/references/arrays; CPU/time/memory quotas |
| Business invariant corruption | Null/out-of-range fields, objects in states uncreatable via constructors, unexpected references | Parse by schema; validate every field; enforce invariants in constructors/factories; distrust post-deserialization fields |

Schema-based formats like JSON/CBOR/Protocol Buffers **avoid automatically instantiating arbitrary Java graphs from stream class names** when configured properly, yet **are not immune** to deeply nested payloads, oversized inputs, misconfigured polymorphic typing, or parser library bugs. Switching formats is part of the solution, not an excuse to skip validation.

## 3. Distinguishing Deserialize, Parse, and Validate

A well-defended data pipeline separates these stages:

```text
[Untrusted Input]
        │
        ▼
Limit size/timeout/format at receiving layer
        │
        ▼
Parse with fixed schema/format; do not instantiate arbitrary classes
        │
        ▼
Validate version, field types, length, range, UTF-8, invariants
        │
        ▼
Validated pure data DTO
        │
        ▼
Domain object constructor/factory (least privilege)
        │
        ▼
Business operation
```

**Parsing** only converts bytes into a representation of predetermined types. **Validation** ensures that representation satisfies business rules. **Java object stream deserialization** additionally builds arbitrary object graphs and triggers custom object logic; that is why it is not a general-purpose input parser for adversarial sources.

A safer contract looks like:

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

This is an **illustrative snippet** placed inside a Java 17+ class; it does not read bytes itself and has no `main`. Even after a parser extracts `String` and `int`, you must still check ranges, required fields, and invariants.

## 4. Preferred Solution: Compact Data Format, Explicit Bounds, No `readObject`

When your application controls the protocol, it is usually better to transmit a fixed data record rather than a Java object graph. Example frame:

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
- Maximum byte sizes for strings and frames are explicitly bounded.
- UTF-8 decoders can be configured to reject malformed byte sequences.
- Protocol versioning is managed by the application, independent of `serialVersionUID`/Object Serialization Stream Protocol.
- Validators can check data before constructing domain objects.

**Important limitation:** when input arrives from a network stream, **cap/bound bytes as they are received**, before creating large arrays. Checking `byte[].length` only after accidentally reading an entire 20 GB file into RAM is far too late against memory exhaustion.

## 5. Runnable Java 17+ Example: Parsing an Explicitly Structured Frame

This example does not use `ObjectInputStream`. It encodes and decodes a frame with length bounds, magic header, version, and strict UTF-8. Inputs with invalid lengths are rejected **before allocating the payload array**.

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
        // Limit total bytes before parsing.
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
            in.readFully(body); // Fails if frame is missing bytes.

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

        // The two length bytes at offsets 9..10 become 0x03E7 = 999.
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

Compile/run on JDK 17+:

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

1. The parser knows upfront a frame contains only magic, version, sequence, length, and UTF-8 bytes; there is no way for input to ask the JVM to instantiate arbitrary Java classes.
2. `readUnsignedShort` makes clear that length is an unsigned 16-bit integer, yet **still checks ≤256** before allocating `byte[]`, never trusting data-supplied lengths.
3. `readFully` rejects truncated frames rather than silently consuming partial text.
4. `ByteArrayInputStream` already holds the complete frame, so checking `available()!=0` works in **this specific case** to catch trailing bytes. Never use `available()` as an exact measure of total network stream length.
5. `CharsetDecoder` with `CodingErrorAction.REPORT` rejects invalid UTF-8 instead of silently replacing it with `�`.
6. After decoding, minimal business rules (non-blank `text`, character count cap, non-negative `sequence`) are validated **before** constructing the record.
7. Malformed data produces only a clean `IOException`/decode failure, rather than driving arbitrary class loading via Object Serialization.

**Scope of the example:** the method's input is an existing `byte[]`; with real sockets you need a framing layer and **caps on total received bytes**, timeouts, and connection handling before calling `decode`. The example includes no authentication, replay protection, or integrity checksums; those requirements must be built separately per threat model.

### 5.2. UTF-8 Byte Limits Differ from String Length Limits

`body.length` is the number of **bytes** after UTF-8 encoding. `text.length()` is the number of UTF-16 code units; the two counts can differ, especially with Vietnamese and emoji. A protocol specification should state clearly whether limits apply to bytes or code points and enforce the matching unit.

If text carries sensitive values or must be digitally signed, specify canonicalization/normalization and encoding explicitly instead of expecting parsers to normalize Unicode automatically.

### 5.3. If Choosing JSON, Still Bind the Schema Strictly

Another route is sending JSON such as:

```json
{"version":1,"sequence":7,"text":"HELLO"}
```

A JSON parser should read only into known data structures, cap depth/bytes/string lengths/number ranges, and **never enable default polymorphic class resolution** for user-supplied data. After parsing, use constructors/factories to validate DTOs. If a library lets payloads embed class names to auto-instantiate subclasses, carelessly enabling such features recreates the "input-chosen type" vulnerability in a different format.

## 6. When Is Using ObjectInputStream Still Considered?

For example, an application must read legacy files written via `ObjectOutputStream` by **the same controlled system** and needs compatibility during a transition period. Before deciding to proceed, answer:

- Does the path from writer to reader protect **integrity and source authentication**?
- Could any less-trusted actor replace files/blobs on the filesystem, database, queue, or backups?
- Which exact classes genuinely need to be instantiated when reading a record?
- Do any of those classes have `readObject`/`readResolve`/`readExternal` hooks or side effects?
- Are upper bounds enforced on bytes, graph depth, reference counts, array sizes, and processing time?
- Do you really need an arbitrary graph, or only 2–5 fields convertible to a DTO?
- If the filter rejects a valid legacy file, is there a clear error reporting/migration path?

Even for internal data, exposed files or altered write permissions can turn a "trusted local file" into an attack surface. Trust is a property of **the entire data pipeline**, not a filename.

## 7. `ObjectInputFilter`: Bounding Classes and Resources, Not Making Unknown Data Safe

In JDK 17/21, `ObjectInputFilter` helps control Java object restoration. It can evaluate:

- The class requested for instantiation when the filter is invoked.
- Graph depth.
- Number of references processed.
- Array length.
- Bytes consumed per filter info.

Three return statuses:

| `ObjectInputFilter.Status` | Meaning |
|---|---|
| `ALLOWED` | Condition is permitted by this filter; does not replace validation |
| `REJECTED` | Denied; active `readObject`/`readUnshared` typically ends with `InvalidClassException` |
| `UNDECIDED` | This filter does not decide; **not equivalent to REJECTED** |

A major risk is writing a filter that returns `UNDECIDED` for dangerous classes and assuming they are denied. If an allowlist is required, there must be an **explicit reject policy** for unlisted classes. Simultaneously account for all classes/references/arrays/strings the stream legitimately contains.

### 7.1. `setObjectInputFilter` Must Be Set Before Reading Objects

```java
try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
```

This is an illustrative snippet; `source` is an `InputStream`, `filter` is already created, with imports and `IOException`/`ClassNotFoundException` handling. The filter must be installed **before reading objects**, not after `readObject`. In Java 17/21, `setObjectInputFilter` follows a once-before-reading rule, and the final effective filter is also governed by the JVM's **filter factory** mechanism.

**Very important note:** filters are not called for every primitive value and are not a mechanism to validate **String/field contents**. `ObjectInputStream` documentation notes that Strings are handled specially like primitives and do not trigger class filtering in the same way regular objects do. Thus even when allowlisting only DTO classes, you must validate text field lengths and contents **after restoration** and **before use**.

### 7.2. Pattern-Based Filters

`ObjectInputFilter.Config.createFilter(...)` supports string-based policies:

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
            "maxdepth=5;maxrefs=32;maxarray=256;maxbytes=8192;"
          + "com.example.legacy.dto.*;!*");
```

This is a policy configuration example, **not a standalone program**. `com.example.legacy.dto.*` is merely an illustrative namespace; real deployments must inventory the exact classes needed for the serialized graph, arrays, and library/framework types. The `!*` pattern denies classes not matched by the allowlist. Never broadly pick `java.base/*` or `java.*` just because "it is the Java standard library" unless truly required; an allowlist means permitting only types genuinely needed.

An overly strict policy can reject valid data; an overly broad policy can leave a gadget surface open. Test against real serialized fixtures rather than trusting that a filter string "looks safe."

### 7.3. Class-Specific Programmatic Filters

You can write an `ObjectInputFilter` targeting exact classes and bounds instead of broad patterns:

```java
ObjectInputFilter filter = info -> {
    if (info.depth() > 5
            || info.references() > 20
            || info.streamBytes() > 4096
            || info.arrayLength() > 128) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();

    // Callbacks related to references/metrics have a null type.
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == TrustedRecord.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

This is a snippet with a serializable `TrustedRecord` managed by a trusted system. If the full graph includes other classes, design a matching allowlist; do not copy this verbatim expecting it to read arbitrary `List`, `Map`, arrays, and nested DTOs. Filter-supplied metrics also do not replace input size caps at the receiving layer.

## 8. Runnable Java 17+ Example: Reading Trusted Legacy Data with a Filter

This example **does not accept adversary-controlled data**. It generates two payloads in memory: a valid `Allowed` and an unlisted `Unexpected`. The reader bounds byte length before constructing `ObjectInputStream`, installs the filter **before `readObject()`**, permits strictly the `Allowed` class, enforces graph metrics, and validates fields after reading.

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

        // This is a demo guard; production must also limit at the reading layer.
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

### 8.1. What the Example Actually Tests

- `Allowed` and `Unexpected` are **two test classes defined by the example itself**; there are no exploit payloads or external inputs.
- `readTrusted` checks total byte array length **before** constructing ObjectInputStream.
- The filter enforces resource limits and **rejects any class other than Allowed**.
- `in.setObjectInputFilter(filter)` happens **before** `in.readObject()`.
- After reading, the code verifies the **exact** class and bounds on `name`.
- The `String name` field still requires validation because filters do not validate individual string values.
- `Unexpected` is rejected by the filter, producing `InvalidClassException` which is caught intentionally.

### 8.2. What the Example Does Not Prove

**Do not** use this example as proof that any Java object stream from the Internet is safe if fitted with the same filter. Filters have narrow scope; allowed classes must still be audited for hooks/side effects, complex graphs may need different policies, and input sources/authentication/timeouts are outside this example.

Future edits to `Allowed` could add new fields or a custom `readObject`. Keeping the same allowlisted class name **is not** proof that the code is safe against adversary-crafted data. Thorough code review and testing are required for all allowlisted classes.

### 8.3. Why Is the Self-Test Output Deterministic?

Both payloads are generated by `ObjectOutputStream` in the same process, so class descriptors match local classes; there is no file or network dependency. The output reflects only the class policy for two tiny objects. If the JVM already configures a stricter system-wide filter factory, additional rejections under that policy may occur; test that in the target deployment environment.

## 9. Filters Do Not "Sanitize" Arbitrary Streams

Several boundaries must be understood accurately:

| False Claim | Reality |
|---|---|
| "Filters inspect all field values." | Filters see class/graph metrics at callbacks; they are not schema/content validators |
| "Just check `instanceof` after `readObject`." | Restoration has already executed beforehand |
| "Classes in the allowlist are always safe." | Those classes or related actions can still have side effects and bugs |
| "Returning `UNDECIDED` rejects the class." | UNDECIDED means undecided; you must configure a reject policy |
| "Setting `maxbytes` guarantees requests cannot consume RAM outside the filter." | Filters run during deserialization; early byte caps and system quotas are still required |
| "One global filter suffices for every use case." | Each endpoint/context has distinct classes/graphs and needs tailored policies |
| "Strings always pass through the filter for length checking." | Strings/primitives are handled differently; explicit payload validation is needed |
| "JSON/CBOR can never cause DoS." | Other parsers also need resource bounds and schema checks |

### 9.1. Global Filters and Context-Specific Filter Factories

Java supports JVM-wide serialization filters via system/security properties like `jdk.serialFilter`, or configuration APIs. On Java 17+, filter factories allow building policies tailored to each `ObjectInputStream`'s context.

**Illustrative** process configuration example:

```bash
java -Djdk.serialFilter="maxdepth=10;maxrefs=100;maxarray=1000;maxbytes=65536;com.example.dto.*;!*" MyApp
```

`MyApp` and `com.example.dto.*` are deployment placeholders, **not a command to run verbatim**. A JVM-wide filter can affect libraries using serialization internally; inventory use cases and test thoroughly before setting a policy. Never enable `java.base/*` globally just to avoid allowlist failures if doing so widens scope unnecessarily.

### 9.2. Filter Selection Order Matters

`ObjectInputStream` can receive an initial filter from the **filter factory** when its constructor runs; calling `setObjectInputFilter` can invoke the factory again to choose/combine filters. If an application replaces the filter factory carelessly or produces a weaker policy, it risks stripping protections another library relies on.

Therefore:

- Designate clear ownership for managing the filter factory at the application level.
- Never let modules arbitrarily mutate the global filter factory at runtime.
- For each data stream, apply a **context**-appropriate filter and audit the effective policy.
- Test both global filters and per-stream filters together.
- Log rejected streams without logging sensitive data.

### 9.3. Filters Can Have Policy Design Flaws

For example, checking only the root class:

```java
Object root = in.readObject();
if (root.getClass() != Allowed.class) {
    throw new SecurityException("wrong root");
}
```

This snippet is **unsafe on its own**, because nested graphs may have already been processed before checking the root. A proper filter must restrict **all classes allowed anywhere in the graph** and bound resources, not merely the top-level type. And right afterward, validate invariants of both the root and nested data.

## 10. Source Authentication and Integrity: Necessary but Insufficient

A system may protect data with mTLS, HMAC, digital signatures, or storage ACLs. These mechanisms verify bytes came from a legitimate source or were not tampered with undetected. Yet:

- Even an authenticated source can be compromised or have bugs writing invalid data.
- A valid blob can contain too many objects/bytes exceeding the reader's quota.
- An older signed file can still be incompatible with current classes.
- Integrity does not make a class's custom `readObject` safe.
- Authentication policies must also account for replay, key rotation, expiration, and version identification if business rules require.

Hence authentication/integrity is only **one layer**. It does not replace input validation, allowlists, resource bounds, and minimal data design.

## 11. Serialization Hooks and Constructor Bypass

When a Serializable class is restored, it does not run the constructor of **the serializable class itself** as in a normal `new` call. Field restoration can happen before business validation. Mechanisms such as:

- private `readObject(ObjectInputStream)`;
- `readResolve()`;
- `readObjectNoData()`;
- `ObjectInputValidation` callbacks;
- `Externalizable.readExternal(...)`;

can participate in object construction logic per their respective contracts.

### 11.1. Invariants Must Be Checked on Restoration

Example of a class allowing only non-negative quantities:

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

This is a **standalone compilable class** `Quantity.java`, without `main`. This validation hook is valuable for data **already permitted** to deserialize, yet **does not** make deserializing untrusted streams safe. Nor does it replace controlling side effects across the whole object graph.

### 11.2. Immutability Is Not Automatically Protected by Serialization

`final` fields, private constructors, and factory methods are object design tools, yet Java serialization has special restoration rules; never infer that merely lacking public setters guarantees every deserialized object satisfies invariants. For sensitive classes, reduce or eliminate direct deserializability and build objects only via factories taking validated DTOs.

## 12. Handling Network Inputs

**Never** wrap a socket directly in `ObjectInputStream` simply because the sender claims "this is a valid object":

```java
// ANTI-PATTERN: do not use with a socket receiving untrusted data.
ObjectInputStream in = new ObjectInputStream(socket.getInputStream());
Object request = in.readObject();
```

Beyond the attack surface, `ObjectInputStream`'s constructor can **block waiting for a stream header**, and `readObject` can block waiting for incomplete data. A remote peer can trickle data slowly, never terminate a frame, or blow through quotas.

Replace with a protocol that enforces:

1. Read timeouts, connection caps, and maximum total bytes.
2. Frame headers (magic/version/length) parsed safely upfront.
3. Valid length checks **before allocation**.
4. Fixed types/schemas; never resolve classes by input-supplied names.
5. Charset decoding with explicit error handling, verifying required fields and ranges.
6. Authentication/authorization where needed, plus per-sender message rate limits.
7. Backpressure, error telemetry, and closing connections on protocol violations.

### 12.1. Bound InputStreams Before calling readAllBytes

`InputStream.readAllBytes()` is convenient, but if the source is untrusted and unbounded, it can keep allocating until out of memory. The same applies to `ByteArrayOutputStream` when copying blindly until EOF.

In length-prefixed protocols, allocate at most the valid maximum size. When the length prefix itself is untrusted, validate it first. When reading unframed streams, use a counted/limited wrapper with a hard cap and fail closed; do not wait until RAM is exhausted to check size.

### 12.2. Compression and Nested Content

Even if an uploaded compressed file is only 10 KB, decompressing it can expand into hundreds of MB or GB. You must cap **post-decompression size**, recursion/nesting, entry counts, and processing time. Never limit only compressed byte size and conclude the deserializer/parser cannot face gigantic inputs.

## 13. Error Handling: Fail Closed Instead of "Trying Another Way"

Exceptions associated with Java deserialization:

| Exception | Possible Meaning |
|---|---|
| `StreamCorruptedException` | Invalid header or control data |
| `InvalidClassException` | Incompatible class, or rejected by filter |
| `NotSerializableException` | Graph being written contains a non-serializable object |
| `ClassNotFoundException` | Class named in stream is absent in reading environment |
| `OptionalDataException` | Mismatched object/primitive read or special data |
| `EOFException` | Stream ran out of bytes/hit end during read |
| `InvalidObjectException` | Invariant/validation hook explicitly rejected |
| `IOException` | I/O error or data reading error |
| `ClassCastException` | Root object read differs from expected application type |

These errors must not be swallowed into an "empty valid payload." For `ObjectInputStream.readObject()`, documentation states exceptions leave the stream in an **indeterminate** state; close the stream and reject the message instead of skipping bytes and continuing as if nothing happened.

**Never implement automatic fallbacks** such as "if deserialization fails, disable the filter and retry." When a filter rejects a payload, that is a security/policy signal. Log non-sensitive diagnostics and investigate per process—never weaken validation just to "keep the program running."

## 14. Migrations: Moving Safely Away from Java Serialization

A legacy system may hold many `.ser` files. Migrating formats is more than finding `readObject` and replacing it with `parseJson`; you need a roadmap:

### 14.1. Inventory Read Points and Classify Sources

Locate every place accepting serialized objects:

- `ObjectInputStream.readObject` and `readUnshared`.
- Libraries/frameworks doing hidden deserialization internally, caches, RPC, or messaging.
- State files, sessions, job data, serialized blobs in databases.
- Backups and data lacking retention/deletion policies.
- Consumers running different versions within the same system.

For each point, record source, write permissions, expected class graph, volume, lifetime, and trust level. Never rely on file extensions or database table names.

### 14.2. Design the Replacement Format

Choose JSON/CBOR/Protocol Buffers/explicit binary framing as appropriate; agree on:

- Message/schema versioning.
- Fixed field lists and types.
- Maximum size of messages and individual fields.
- Rules for optional/default/unknown fields.
- Charset, timezone, date/time, numeric ranges, and Unicode normalization.
- Integrity/authentication per threat model.
- Backward/forward compatibility rules and sunset plans for old versions.

### 14.3. Conversion Tool in a Controlled Environment

If legacy files must still be opened:

1. Run only on copies from authenticated, integrity-checked sources, never directly on untrusted uploads.
2. Use an audited JDK and classpath, applying strict class/graph/resource filters.
3. Run the tool with least OS privileges, restricted network, filesystem, CPU/memory/time limits, and proper logging; isolation reduces blast radius without guaranteeing absolute safety.
4. Validate data after deserialization, then write to the new format.
5. Test valid/corrupted samples and support rollback if conversion goes wrong.
6. After cutover, remove obsolete `ObjectInputStream` entry points rather than leaving legacy endpoints open forever.

If legacy input cannot be proven trusted and adequate controls cannot be applied, **refusing automated conversion** is safer than bringing it into critical production processes.

## 15. Common Design Mistakes

1. **Reading untrusted object streams just because the class implements `Serializable`.** This is not a safety guarantee.
2. **Checking `instanceof` after `readObject` thinking it blocks exploits.** Deserialization has already run beforehand.
3. **Trusting `.ser` file extensions or the `AC ED 00 05` magic header.** Those indicate format, not authenticity.
4. **Filtering only the root class.** Nested graphs can contain other classes already processed.
5. **Returning `UNDECIDED` for unlisted classes assuming it denies.** An explicit reject policy is needed.
6. **Allowing entire packages/Java modules needlessly.** Enlarges the class surface beyond actual needs.
7. **Omitting bounds on arrays, depth, references, or bytes.** Exposes resource exhaustion.
8. **Checking byte limits only after `readAllBytes`.** Unbounded allocation already happened before the check.
9. **Assuming filters validate String contents.** Field lengths and values still need validation.
10. **Assuming allowlisted classes never have side effects.** Audit hooks and class changes.
11. **Authenticating the source without bounding format/resources.** A compromised source can still send malformed inputs.
12. **Switching to JSON while enabling generic polymorphic deserialization for input-chosen classes.** Schema/type allowlisting is still needed.
13. **Not checking for malformed UTF-8.** Data can silently get replacement characters.
14. **Trusting input length prefixes and allocating arrays immediately.** Attacker-controlled lengths must be bounded.
15. **Not checking for trailing bytes or missing data.** Invalid frames could be partially accepted.
16. **Letting parsers/converters read indefinitely on slow sockets.** Timeouts and quotas are essential.
17. **Silently converting class versions without invariant checks.** Legacy data does not automatically fit new models.
18. **Catching filter errors and automatically disabling filters/retrying.** Downgrades security policy.
19. **Using `readObject` as a tool to probe unknown files.** Never deserialize just to "peek at what a file contains."
20. **Logging entire serialized bytes or secrets on failure.** Leaks data; log sanitized error details.
21. **Assuming a sandbox/process alone is enough protection.** Least privilege, patching, runtime observability, and defense-in-depth are required.
22. **Failing to check filter policies of libraries using `ObjectInputStream` under the hood.** Entry points may sit outside endpoint source code.
23. **Sharing one overly broad filter across all use cases.** Different contexts need distinct classes/limits.
24. **Not testing truncated files, deep graphs, and invalid fields.** Happy-path testing alone misses robustness bugs.
25. **Assuming parsing into a Java record is enough.** Records enforce field types, yet business validation is still required.
26. **Treating any read `IOException` as recoverable and continuing on a broken stream.** ObjectInputStream can be in an indeterminate state.
27. **Confusing integrity checks with confidentiality.** Authenticated data can still be read without encryption/access controls.
28. **Assuming data stored "internally" is immutable.** Audit who has write access across apps, backups, file shares, and queues.
29. **Failing to cap output size during decoding/decompression.** Small inputs can expand enormously.
30. **Having no plan to retire legacy endpoints.** Systems keep dangerous deserialization endpoints long after migrating most traffic.

## 16. Self-Check Knowledge Questions

**Question 1.** Why is `(Expected) in.readObject()` dangerous when bytes are untrusted?  
**Answer:** Before the cast, the JVM can already build graphs, run deserialization logic, and allocate resources per the stream.

**Question 2.** Does checking the file header `AC ED 00 05` prove the stream is safe?  
**No.** It is the protocol magic/version, not proof of source authenticity or safe class graphs.

**Question 3.** What approach should be prioritized for user-generated API requests?  
**Answer:** A data protocol with fixed schema/types, a parser bounding bytes/depth, and per-field validation.

**Question 4.** What can `ObjectInputFilter` limit?  
**Answer:** Classes, array lengths, graph depth, reference counts, and consumed bytes per contract.

**Question 5.** Does a filter returning `UNDECIDED` mean the class was blocked?  
**Not yet.** It is an undecided status; explicit denial requires returning `REJECTED` per policy.

**Question 6.** Is placing `setObjectInputFilter` after `readObject` valid?  
**No.** The filter must be set before reading objects, per API usage rules.

**Question 7.** If only one DTO class is allowlisted, do you still need to validate `String name`?  
**Yes.** Filters do not inspect all primitive/String values; content, bounds, and invariants must still be validated.

**Question 8.** Do `Future`/async transports automatically limit object stream length?  
**No.** Transport APIs and input framing need explicit quotas before deserialization.

**Question 9.** If `InvalidClassException` reports a filter rejection, should you keep reading the same stream?  
**No.** Treat the stream as corrupted/untrusted, close it, and report an error; never auto-downgrade filters.

**Question 10.** Does `SafeFrameDemo`'s use of `available()` work to measure total bytes of a network stream?  
**No.** There the source is a `ByteArrayInputStream` holding the entire frame; network streams require length prefixes and bounded reads.

**Question 11.** Are digital signatures enough to replace filters/schemas?  
**No.** Signatures verify integrity and origin per threat model; graph/byte limits and validation are still required.

**Question 12.** When forced to convert legacy serialized files, where should conversion run?  
**Answer:** A controlled environment with authenticated data, restricted classpath, tight filters, and bounded permissions/resources; write to the new format and retire the old reader.

**Question 13.** Is `InputStream.readAllBytes()` safe for unbounded file uploads?  
**No.** It can allocate up to the entire input size; a hard cap is needed at the receiving layer.

**Question 14.** Does a strict class filter guarantee avoiding all side effects of allowed classes?  
**No.** Code inside allowed classes/hooks still needs auditing; filters do not validate behavior.

**Question 15.** What is the right purpose of Java Object Serialization when it must still be used?  
**Answer:** Compatibility with system-controlled Java data/object graphs alongside proper boundaries and controls—**not** a default input format from untrusted parties.

## 17. Conclusion and Official References

**Key takeaway:** "Do not deserialize in order to check whether an object is the right type; deserialize only when trust foundations, class/graph policies, and resource boundaries are in place — and whenever you have a choice, use a data format with a schema-driven parser."

Decision flow:

```text
Could the source be controlled by an adversary?
    ├── Yes, or source trust is unproven
    │       └── DO NOT use ObjectInputStream.readObject directly
    │               └── Bounded framing → schema parser → validation → DTO
    └── Trusted legacy data, compatibility required
            └── Inventory classes + verify source
                    └── Quota/input bounds + ObjectInputFilter
                            └── Validate output and audit allowed hooks
                                    └── Migrate to a stable data format
```

Official sources (Java SE 21; presented APIs apply to Java 17+):

- `ObjectInputStream` — untrusted deserialization warnings, `readObject` contract, and `setObjectInputFilter`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputStream.html
- `ObjectInputFilter` — class/resource filtering, policy composition, and filter factories: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.html
- `ObjectInputFilter.Config` — pattern filters and JVM-wide filters: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/ObjectInputFilter.Config.html
- `Serializable` — default serialization and class hooks: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/Serializable.html
- `DataInputStream` — bounded primitive/data reading per application-designed formats: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/io/DataInputStream.html
- `CharsetDecoder` — UTF-8 error policies: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/charset/CharsetDecoder.html
- Oracle Secure Coding Guidelines for Java SE, Serialization/Deserialization section: https://www.oracle.com/java/technologies/javase/seccodeguide.html
