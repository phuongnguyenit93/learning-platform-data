# ObjectInputFilter in Java 17: Limiting Classes, Depth, References, and Array Lengths

## 1. The Problem: Why Filter Data During Deserialization?

`ObjectInputStream.readObject()` turns a byte sequence formatted in **Java Object Serialization** into instances, arrays, and an **object graph**. If the stream arrives from a file, message broker, socket, or any source not completely controlled by the application, reading it is never merely "parsing data."

A stream may contain:

- Classes unexpected by the application, including classes with special logic triggered during deserialization.
- A deeply nested object graph, increasing the risk of stack or resource exhaustion.
- Vast numbers of objects/references, consuming heap and processing overhead.
- Extremely large arrays, causing the application to attempt huge memory allocations.
- Complexly encoded data designed to make the program spend excessive processing time.

`java.io.ObjectInputFilter` acts as a **control barrier while deserialization is underway**: it can decide to accept or reject classes and cap resource metrics of the object graph. Introduced in Java 9, it is available for use on Java 17+.

However, **filters alone do not make native Java serialization completely safe**. They do not replace input authentication, authorization, post-deserialization data validation, protocol-level request size caps, or application resource management.

### Core Limits

| Limit | Meaning | Type of Issue Mitigated |
|---|---|---|
| **Class allowlist** | Permits only approved data types | Deserialization of unexpected classes |
| **`maxdepth`** | Caps traversal depth of the graph | Overly deep graphs increasing stack/cost |
| **`maxrefs`** | Caps the number of references observed during deserialization | Graphs with excessive references |
| **`maxarray`** | Caps the number of elements in an array | An array requesting excessive allocation |
| **`maxbytes`** | Caps stream bytes consumed at check checkpoints | Large / resource-heavy inputs |

This lesson highlights the four axes: class, depth, references, and array length. `maxbytes` is a highly recommended supplementary limit, **not** a replacement for payload size caps at the layer before creating `ObjectInputStream`.

## 2. How ObjectInputFilter Is Invoked

The interface defines the method:

```java
ObjectInputFilter.Status checkInput(ObjectInputFilter.FilterInfo info);
```

While `ObjectInputStream` processes data under Java serialization mechanics, it consults the filter at specific checkpoints to inspect the **class** and **object graph metrics**. The `FilterInfo` object provides current state:

| `FilterInfo` | Returned Data | Caveats |
|---|---|---|
| `serialClass()` | Class currently under inspection; **may be null** | Null does not mean the request is necessarily valid |
| `arrayLength()` | Array length; typically `-1` when not an array | Compare directly against the `maxarray` threshold |
| `depth()` | Current depth of the graph | Not the class inheritance depth |
| `references()` | Running reference count during reading | Not distinct object count or business IDs |
| `streamBytes()` | Stream bytes read so far at checkpoint | Not total file length; enforcement occurs at checkpoints |

Conceptual view:

```text
ObjectInputStream.readObject()
        |
        v
   Read token / class / array / reference
        |
        v
   filter.checkInput(FilterInfo)
        |
        +--> ALLOWED   : this check accepts
        +--> REJECTED  : reject, abort with deserialization error
        +--> UNDECIDED : filter makes no decision at this step
        |
        v
   If not rejected, continue processing graph
```

### Is the Filter Called for Every Byte and Every String?

**No.** Per the serialization filtering contract, the filter is not a parser invoked on *every byte* or every kind of value. Strings encoded directly in the stream and primitive values have exceptions in filter invocation mechanics; references to objects already assigned handles may be checked differently. Documentation describes checks when encountering new instances, arrays, and certain references, yet **this must not be viewed as inspecting the full semantics of all data**.

Consequences:

- Do not use `ObjectInputFilter` to validate String **contents**, individual raw bytes, or business field values.
- Use class filters and resource limits, then **validate the object after reading**.
- Cap payload bytes at ingress (HTTP request body, file length, framed socket messages) to reject oversized inputs early rather than relying solely on `streamBytes()`.

## 3. Three Outcomes: `ALLOWED`, `REJECTED`, `UNDECIDED`

`checkInput(...)` must return one of these statuses:

```java
ObjectInputFilter.Status.ALLOWED
ObjectInputFilter.Status.REJECTED
ObjectInputFilter.Status.UNDECIDED
```

- **`ALLOWED`:** the filter accepts the details inspected in this check. **Not** a guarantee that the resulting object is semantically valid or safe.
- **`REJECTED`:** rejected; `ObjectInputStream` aborts deserialization, typically via `InvalidClassException`.
- **`UNDECIDED`:** the filter makes no decision on this step. **Do not assume this means "denied by default."**

A common security pitfall is a filter that blocks only a few known dangerous classes and returns `UNDECIDED` for everything else. Without another filter layer rejecting them, unlisted classes can still be deserialized.

**Safer allowlist policy:** check resource limits first; return `ALLOWED` strictly for permitted classes; return `REJECTED` for all other classes. When `serialClass() == null` because no class applies to that callback, still enforce limits and return `UNDECIDED` only for that specific check.

Decision examples:

```text
Class Message allowed, length 4, depth 2   -> ALLOWED
Class Gadget not in allowlist              -> REJECTED
Class Message allowed, but depth 100       -> REJECTED
No class at callback, valid metrics        -> UNDECIDED
No class at callback, maxrefs exceeded     -> REJECTED
```

**Never let allowlist checks override limit checks.** An allowed class containing a massive array must still be blocked.

## 4. Limiting Classes: Allowlist Instead of Blacklist-Only

When an application expects a DTO like `com.example.dto.Order`, it should never deserialize arbitrary classes on the classpath. There are two implementation approaches:

1. **Pattern filter** using `ObjectInputFilter.Config.createFilter(...)`.
2. **Programmatic filter** using a lambda/class implementing `ObjectInputFilter`.

### Pattern Filter

Illustrative configuration example:

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=10;maxrefs=1000;maxarray=10000;"
              + "maxbytes=1048576;"
              + "com.example.dto.*;java.base/java.util.ArrayList;!*");
```

Explanation:

- Segments are separated by semicolons `;`.
- Limits like `maxdepth=10`, `maxrefs=1000`, `maxarray=10000`, `maxbytes=1048576` apply regardless of class-pattern order.
- `com.example.dto.*` matches classes in that package per JDK pattern rules.
- `java.base/java.util.ArrayList` includes a module prefix targeting a specific class within a Java module.
- `!*` rejects **any class not matched by the preceding allow patterns**.

**Important warning:** Pattern filters check **object types** rather than automatically constraining all data to match a DTO schema. A DTO may involve collection implementations, nested classes, or arrays that need individual consideration. Never copy the allowlist above to production without testing the actual structure and classes queried during reading.

### Which Pattern Matches Which Class?

Per Java serialization filter patterns:

| Form | Common Meaning |
|---|---|
| `com.acme.dto.Order` | Exact fully qualified class |
| `com.acme.dto.*` | Classes directly in that package |
| `com.acme.dto.**` | Includes the package and all subpackages |
| `!com.acme.Bad` | Rejects the matched class |
| `!*` | Rejects all remaining unallowed classes |
| `java.base/java.util.ArrayList` | Class with module name |
| `maxdepth=20` | Depth limit, **not** a class pattern |

For array classes, matching rules inspect the **element type** per specification. Class patterns do not enumerate every distinct array dimension/type separately; array lengths are still constrained via `maxarray`.

**Do not confuse `package.*` with a wildcard for arbitrary packages, and do not confuse class patterns with field-value checks.** Read Java 17 pattern matching rules carefully, especially for module prefixes, nested classes, and arrays.

### Avoid Overly Broad Wildcards in Allowlists

Patterns like `java.base/*` or `java.**` (depending on pattern syntax) are far too broad when an application only needs a few DTOs. The wider the set of deserializable classes, the larger the attack surface.

Usually you should build **dedicated lean DTOs** with fixed field types, carrying no runtime services, threads, class loaders, or callback objects in the stream. Avoid directly serializing complex domain objects.

## 5. `maxdepth`: Depth of the Object Graph

`depth()` tracks the current traversal depth while decoding references—it is **not**:

- Class inheritance (`extends`) depth.
- Package name segment count.
- JSON nesting depth from another parser.
- Total number of distinct objects in the stream.

Example:

```text
Root
  |
  v
Child
  |
  v
GrandChild
  |
  v
GreatGrandChild
  ...
```

If a graph chains too deeply, deserialization can exhaust stack and CPU. The `maxdepth` limit rejects graphs exceeding the threshold at callbacks.

Example:

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=100;maxarray=1000;maxbytes=65536");
```

This snippet configures only resource limits **without a class allowlist**, so it is not a complete safe filter for untrusted inputs.

**How to choose maxdepth:** measure and understand valid graphs. If your DTO has at most three levels (Envelope → Payload → Item), there is no reason to allow 10,000 levels. Yet avoid guessing too low and rejecting valid graphs due to collections, wrappers, or nested references.

### Reference Cycles and Depth

Java Object Serialization uses object handles and back-references to preserve cyclic graphs. A cycle A → B → A does not make the serializer recurse infinitely: upon encountering A again, it reuses the handle instead of allocating a new A. Even so, many nesting levels before hitting a back-reference can still yield deep graphs. `maxdepth` serves as a dedicated guardrail.

## 6. `maxrefs`: Limiting Processed References

The `references()` metric reflects **references observed during deserialization** per the `FilterInfo` contract. It is **not**:

- Distinct instance count after reading finishes.
- Number of fields defined on a class.
- Stream byte count.
- An object ID or `System.identityHashCode()` value.

For instance, an `ArrayList` with 100,000 elements all pointing to the same object generates massive reference counts in the stream despite few distinct instances. Therefore, capping `maxrefs` independently of class checks is essential.

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=12;maxrefs=5000;maxarray=10000;"
              + "maxbytes=2097152");
```

If `references()` exceeds `5000` at any checkpoint, the filter rejects. Because metrics are sampled at callbacks, do not treat `maxrefs` as an exact promise of total memory footprint.

### Maxrefs and Shared References

Java serialization preserves multiple fields pointing to the same object via stream handles. Yet `maxrefs` remains meaningful even when references alias one object. **Do not assume limiting class types alone removes the risk:** a single allowed DTO class can still construct an enormous reference graph.

## 7. `maxarray`: Blocking Oversized Array Allocations

A payload containing `byte[]`, `int[]`, or `Order[]` can request huge memory before the program ever inspects contents. When deserializing arrays, `FilterInfo.arrayLength()` supplies the length when known, letting the filter reject before allocation.

Example:

```java
ObjectInputFilter f =
        ObjectInputFilter.Config.createFilter(
                "maxarray=10000;maxdepth=10;maxrefs=1000;"
              + "maxbytes=1048576");
```

`maxarray=10000` counts **elements**, not bytes:

- `byte[10000]` has 10,000 byte elements.
- `long[10000]` has 10,000 long elements, consuming significantly more memory.
- `Object[10000]` has 10,000 references, plus whatever memory the referenced objects consume.

Do not equate `maxarray=1000000` with "1 MiB maximum" across all array types. Pair it with `maxbytes`, `maxrefs`, and real input size caps.

### When No Array Is Present: `arrayLength() == -1`

In custom filters, a negative value indicates **no array length applies to that callback**. Therefore:

```java
long length = info.arrayLength();
if (length >= 0 && length > MAX_ARRAY_LENGTH) {
    return ObjectInputFilter.Status.REJECTED;
}
```

Never require every check to have `arrayLength() >= 0`, or even valid non-array DTOs will be rejected.

## 8. `maxbytes`: Capping Bytes Read, Not Replacing Ingress Limits

`maxbytes` relies on `FilterInfo.streamBytes()`. Once exceeded, the filter rejects at the checkpoint. Still, the filter **is not called on every byte**; specially crafted streams or reads outside `ObjectInputStream` may require separate controls.

Layered defense:

```text
HTTP/Socket/File input
   -> max 1 MiB payload before deserialization
   -> ObjectInputStream with allowlist + graph limits
   -> DTO deserialized
   -> validate field values, business invariants
   -> only then run business processing
```

Over networks with continuous byte streams, use **bounded length-prefixing** or structured framing rather than reading unboundedly until EOF. On HTTP, enforce maximum request body sizes. With files, checking `Files.size` helps, yet files can change between check and use—so enforce bounded streams/protocols as well.

## 9. Complete Java 17+ Program: One Valid Payload and One Rejected Payload

The example uses a **custom `ObjectInputFilter`** to show checking clearly:

- Permits only the `Message` DTO and the `byte[]` array used by that DTO.
- Caps `depth <= 8`, `references <= 64`, `arrayLength <= 8`, `streamBytes <= 65536`.
- Reads a 4-byte payload successfully.
- Rejects a payload containing a 12-byte array **before returning a complete object**.
- Uses no network or disk files, since the exercise requires deterministic results.

Save as **`InputFilterDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class InputFilterDemo {

    private static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;

        final int id;
        final byte[] payload;

        Message(int id, byte[] payload) {
            this.id = id;
            this.payload = payload;
        }
    }

    private static ObjectInputFilter policy() {
        return info -> {
            // Always check resource limits before class allowlist.
            if (info.depth() > 8
                    || info.references() > 64
                    || info.streamBytes() > 65536
                    || info.arrayLength() > 8) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                // When only metrics/references exist, limits were still checked.
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == Message.class || type == byte[].class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }

    private static byte[] encode(Message message) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(message);
        }
        return bytes.toByteArray();
    }

    private static void decode(String caseName, byte[] bytes)
            throws Exception {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(policy());

            try {
                Message restored = (Message) in.readObject();
                System.out.println(caseName + ": id=" + restored.id
                        + ", length=" + restored.payload.length);
            } catch (InvalidClassException rejected) {
                System.out.println(caseName + ": REJECTED");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        decode("allowed",
                encode(new Message(7, new byte[] {1, 2, 3, 4})));

        decode("too-large",
                encode(new Message(8, new byte[12])));
    }
}
```

Compile and run commands:

```bash
javac InputFilterDemo.java
java InputFilterDemo
```

**Expected stdout on Java 17 with default serialization:**

```text
allowed: id=7, length=4
too-large: REJECTED
```

Step-by-step explanation:

1. `Message` implements `Serializable`, holding `int` and `byte[]`.
2. `encode(...)` generates bytes using native Java serialization; writing does not use an input filter because filtering is a **read-side** control.
3. `decode(...)` constructs `ObjectInputStream` and **installs the filter before the first `readObject()` call**.
4. For `Message(7, byte[4])`, `Message` and `byte[]` are allowed; depth/references/streamBytes stay within bounds, so the object constructs and prints its result.
5. For `Message(8, byte[12])`, when the filter is consulted for the 12-element array, `arrayLength() > 8` returns `REJECTED`. Deserialization throws `InvalidClassException`, and the program prints `too-large: REJECTED`.
6. We avoid printing exception messages because exact message strings can vary by JDK implementation/build.

Note: the example wraps `readObject()` in `try/catch InvalidClassException` to demonstrate filtering. In production, distinguish corrupted streams, I/O failures, schema mismatches, and filter rejections separately—**never assume every `InvalidClassException` came from the filter**. Furthermore, this custom filter lists only types expected in a tiny DTO; complex DTOs require allowlisting and testing nested types and arrays thoroughly.

### Checking the Meaning of `UNDECIDED` in the Example

When `serialClass() == null`, the custom filter returns `UNDECIDED` **after** verifying resource limits. This works cleanly when you control the class policy; however, in complex applications, combining filters with a global filter factory can change how `UNDECIDED` is resolved. Never assume `UNDECIDED` automatically means reject.

## 10. Writing Pattern Filters for Typical Systems

When class schemas are known, patterns are concise and convenient:

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=64;maxarray=8;maxbytes=65536;"
              + "com.example.messages.Message;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object o = in.readObject();
}
```

This snippet is **illustrative code**, where `source` is an application-supplied `InputStream` and `com.example.messages.Message` is a hypothetical DTO class. With arrays, nested classes, and filter factories, test against real valid and invalid inputs before deploying. If any legitimate nested type is blocked by `!*`, **explicitly add** it to the allowlist rather than removing deny-by-default.

**Common pitfall:** `createFilter(...)` with only `maxdepth/maxrefs` does not build a class allowlist on its own. Appending `!*` closes the policy against unmatched classes; without an explicit reject rule, unmatched classes evaluate to `UNDECIDED`.

### Combining Patterns with Resource Limits

Suggested workflow for building patterns:

1. Enumerate allowed root DTOs based on the real schema.
2. Generate valid sample streams with nested collections, arrays, and nullable fields.
3. Enable a strict allowlist; observe which classes the filter gets queried on during tests.
4. Allow **only the exact** required classes; avoid overly broad wildcards.
5. Set `maxdepth` and `maxrefs` from measured valid-graph stats plus a small safety margin.
6. Set `maxarray` to the largest array size accepted by business rules.
7. Set `maxbytes` and enforce total request byte caps at ingress.
8. Add negative tests: unknown classes, deep nesting, massive arrays, excessive references.

## 11. Per-Stream Filters, Global Filters, and Filter Factories

### 11.1. Per-Stream: Configured on Each ObjectInputStream

```java
try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object result = in.readObject();
}
```

Ideal when different payload types or trust levels need distinct allowlists. Install the filter **right after creating the stream and before deserializing the first object**.

Never create a stream, start calling `readObject()`, and install the filter afterward hoping previously read objects are retroactively checked.

### 11.2. Global Filter: JVM-Wide Policy

Java supports JVM-wide filters via a **system property** or API, for example:

```text
-Djdk.serialFilter=maxdepth=20;maxrefs=10000;maxarray=100000;maxbytes=10485760
```

This is an illustrative setting; semicolon escaping depends on your shell/launch command. You can configure a runtime-wide policy at application startup. `ObjectInputFilter.Config.setSerialFilter(...)` also sets a static JVM-wide filter, subject to one-time initialization and permission rules; never attempt to call it repeatedly mid-lifecycle.

**Global filters are defense in depth**, not an excuse for streams reading from untrusted sources to omit dedicated class allowlists.

### 11.3. Java 17: Filter Factories and Composition

Java 17 supports **context-specific deserialization filters** via a filter factory (JEP 415). API:

```java
ObjectInputFilter.Config.setSerialFilterFactory(
        (current, requested) -> {
            // Decide how to combine or select a policy.
            // This is a conceptual example; understand the full contract
            // and JVM-wide configuration ownership.
            return requested != null ? requested : current;
        });
```

This is an **illustrative configuration snippet**, not a safe policy to copy into an app: it can overwrite the current policy with the requested one, dropping prior restrictions. **Do not use the factory above if you expect both global and per-stream filters to stay active.**

Key points to understand:

- The factory receives the current filter and requested filter, returning the effective filter for that stream context.
- A misconfigured factory can inadvertently drop global limits whenever a per-stream filter is set.
- The specification expects factory setup early at startup; it is a JVM-wide policy requiring centralized design and testing, not ad-hoc updates after a server is running.
- When combining allowlists and limits, define explicit **union or intersection** semantics so any `REJECTED` from mandatory limits is always honored.

**Recommendation:** for small apps, install a per-stream filter before `readObject` with **both class rules and resource limits**. For multi-module systems with libraries, design a centralized factory backed by integration tests proving no code path bypasses baseline policies.

## 12. What Happens When a Filter Returns `REJECTED`?

When the filter rejects an item, `ObjectInputStream` fails; in practice this is commonly an `InvalidClassException` with a filter-status message. Never depend on exact message text as a stable API.

Handling pattern:

```java
try {
    Object result = in.readObject();
    validateBusinessFields(result);
} catch (InvalidClassException e) {
    // Could be filter rejection or class incompatibility.
    // Log safely, terminate request in error state.
} catch (StreamCorruptedException e) {
    // Malformed binary stream.
} catch (ClassNotFoundException e) {
    // Required class from stream not found.
} catch (IOException e) {
    // I/O or serialization protocol error.
}
```

This is illustrative code; `in` and `validateBusinessFields` are defined externally. Do not keep deserializing the rest of an untrusted stream after a fatal error as if alignment were intact; close the stream/request and report failure.

**Avoid logging raw payloads or untrusted object graphs.** Doing so can leak sensitive data or trigger complex `toString()` methods on deserialized objects.

## 13. Limitations ObjectInputFilter Does Not Solve

Filters are essential when still using Java Object Serialization, but do not treat them as a silver bullet:

### Does Not Validate Business Fields

An allowed object can still carry `amount=-999999`, invalid dates, invalid enum states, or duplicate entries. Filters check **types and graph dimensions**, not business rules. After `readObject`, validate schema and domain invariants.

### Does Not Automatically Prevent All Gadget Chains

Allowing a class does not guarantee the class is safe, and `readObject`, `readResolve`, `readExternal`, or custom callbacks on that class can run during deserialization. A class allowlist shrinks the attack surface, yet permitting classes with side effects remains risky. Deserialize only audited data classes.

### Not a Byte-Level Parser or Checksum

Filters do not verify digital signatures, check CRCs, block protocol-valid tampered inputs, decrypt payloads, or identify senders. You need TLS/authentication, message integrity, and authorization.

### Does Not Replace Timeouts and Overall CPU/Memory Caps

Each callback reports only select metrics. Custom logic during deserialization can still burn CPU; file/network reads can stall, drop mid-stream, or carry bytes unchecked by the filter. Enforce deadlines, bounded inputs, quotas, and monitoring at outer layers.

### Does Not Make Object Serialization Right for Every System

Native Java serialization is tightly coupled to Java types, class descriptors, and `serialVersionUID`. For public APIs or cross-language communication, explicit-schema formats (JSON/CBOR/Protocol Buffers, etc.) are often far better suited; validation and resource limits still apply to any parser.

## 14. How Filters Differ from `transient` and `serialVersionUID`

- `transient`: controls **which fields** default serialization writes/reads. It **does not** stop unexpected classes from appearing in the stream.
- `serialVersionUID`: helps verify class version compatibility; **not** a class allowlist or authentication signature.
- Custom `readObject(...)`: controls deserialization data/logic; if unconstrained, even an allowed class can construct objects or trigger unintended side effects.
- `ObjectInputFilter`: enforces class and resource constraints at checkpoints during reading.

Combine all four only for their respective roles; never treat one tool as a substitute for the others.

## 15. Designing Custom Filters Properly with `FilterInfo`

Callback structure:

```java
ObjectInputFilter filter = info -> {
    if (info.depth() > 10
            || info.references() > 1000
            || info.streamBytes() > 1_048_576
            || info.arrayLength() > 10_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == MyAllowedDto.class || type == byte[].class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

This snippet is illustrative since `MyAllowedDto` is application-defined. Remember:

1. **Limits before allowlist:** even allowed classes must not consume unbounded resources.
2. **Null class** must not skip checking depth/references/bytes/array length.
3. **Array length = -1** when no array length applies: comparing `> positiveThreshold` avoids rejecting non-arrays.
4. **Never call complex methods inside the filter:** filters run on the deserialization hot path and must stay fast and deterministic.
5. **Never touch networks or databases inside `checkInput`:** risks deadlocks, latency spikes, and error surfaces.
6. **Never return `UNDECIDED` for unknown classes** when you intend a closed allowlist.
7. **Avoid blocking arrays of allowed types** by forgetting `byte[].class` or legitimate array types; test thoroughly.
8. **Never treat `ALLOWED` as complete validation;** still check object invariants after reading.

## 16. Tuning Limit Policies for Real Workloads

No single set of numbers fits every application. Design process:

- Measure depth and reference count of a **largest valid payload**.
- List expected array types and sizes.
- Determine an **ingress request size limit** well below what overloads heap or CPU.
- Pick thresholds with a modest safety margin rather than unbounded values.
- Write tests for both valid payloads right near the limit and payloads just over it.
- Test inputs with reference cycles, heavy handle sharing, and nested arrays.
- Watch out for messages with large Strings: filters do not validate String contents like domain validators; `maxbytes`/checkpoints and bounded input remain essential.
- Monitor filter rejection rates without logging untrusted payloads or sensitive data.

Sample policy for a small DTO with up to 4 KiB array payload:

| Rule | Sample Value | Rationale |
|---|---|---|
| Class allowlist | `OrderMessage`, exact nested types | Eliminates unexpected classes |
| `maxdepth` | 12 | Sufficient for a shallow graph |
| `maxrefs` | 2000 | Bounds reference count |
| `maxarray` | 4096 | Maximum 4096 array elements |
| `maxbytes` | 65536 | Blocks oversized streams at checkpoints |
| Ingress cap | 65536 bytes | Bounds payload size before deserialization |

These numbers are **sample configuration values**, not universal security defaults. If `OrderMessage` carries huge Strings or nested maps spawning many classes, adjust both schema and policy.

## 17. Security Testing: Include Both Positive and Negative Cases

| Test | Test Input | Expected Outcome |
|---|---|---|
| Allowed class | DTO in allowlist, normal size | Reads cleanly, passes business validation |
| Unknown class | Another Serializable class | `REJECTED` |
| Oversized array | `byte[limit+1]` | `REJECTED` |
| Deeply nested graph | Chain exceeding `maxdepth` | `REJECTED` |
| Excessive references | Graph with too many references | `REJECTED` |
| Too many bytes | Stream exceeding `maxbytes` hitting checkpoint | `REJECTED` or blocked earlier at ingress cap |
| Corrupted stream | Damaged/truncated bytes | Fails cleanly without blind continuation |
| Compatible update | Expected DTO version | Reads and validates per policy |
| Incompatible class version | Mismatched UID/schema | Handles `InvalidClassException` |
| Null class info | Metrics-only callback | Still checks limits; does not infer unknown allowed |
| Global factory | Per-stream filter layered on global policy | Preserves JVM-wide limits |

Beyond unit tests, run integration tests on the target JDK/runtime and real serialization setup. If custom `readObject`/`readResolve` hooks exist, test those paths as well.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Relying solely on a denylist of known bad classes | Other dangerous classes still slip through | Use a strict allowlist |
| Omitting `!*` at end of pattern expecting deny-by-default | Unmatched classes evaluate to `UNDECIDED` | Add explicit reject rule |
| Allowing overly broad wildcards | Expands gadget/deserialization surface | Allow exact DTOs and nested types only |
| Omitting `maxdepth` | Deeply nested graphs | Set a depth cap |
| Omitting `maxrefs` | Excessive references | Set a reference cap |
| Treating `maxarray` as a byte count | Oversized `long[]` or `Object[]` | Remember it counts elements |
| Setting only `maxbytes` without capping ingress | Filter is not a byte-level hard cap | Bound stream/request lengths |
| Returning `ALLOWED` before checking limits | Allowed classes can exhaust resources | Check limits first |
| Returning `UNDECIDED` for unknown classes assuming rejection | Another filter may permit them | Return `REJECTED` for unknown classes |
| Setting filter after already reading objects | Leaves previously processed objects unprotected | Set before the first `readObject` |
| Assuming `serialClass() != null` on every callback | `NullPointerException` or skipped metrics | Handle null properly |
| Global/per-stream filters accidentally overwriting each other | Drops security limits | Design and test the filter factory |
| Assuming filters validate String/field contents | Accepts invalid business values | Validate at the DTO/domain layer |
| Catching `InvalidClassException` and keeping reading stream | Stream state is untrustworthy | Close stream/request and fail cleanly |
| Assuming internet deserialization is safe with a filter | Broad attack surface remains | Prefer safer formats and defense in depth |

## 19. Self-Check Questions

1. Is `ObjectInputFilter` used during serialization or deserialization? **During deserialization** via `ObjectInputStream`.
2. Does `UNDECIDED` guarantee rejection? **No.** It means the filter has not made a decision yet.
3. Which should come first in a custom filter: class allowlist or resource limits? **Check resource limits first**.
4. When `serialClass() == null`, can all checks be skipped? **No; still check depth, references, arrayLength, and streamBytes**.
5. Does `maxdepth` limit class inheritance depth? **No; it caps object graph traversal depth while reading**.
6. Does `maxrefs` count distinct instances? **No, it tracks reference metrics observed during deserialization**.
7. Does `maxarray=500` mean at most 500 bytes for any array? **No, at most 500 array elements**.
8. If `arrayLength() == -1`, what should you do? **Do not treat it as an invalid negative-length array; it means no array length applies**.
9. Can `maxbytes` replace an ingress size cap? **No.**
10. In a pattern string, what does `!*` do? **Rejects any class not matched by earlier allow patterns**.
11. When should `setObjectInputFilter` be called? **Before calling `readObject()`**.
12. When a filter rejects a class, what exception commonly occurs? **`InvalidClassException`**.
13. Is `InvalidClassException` always caused by a filter? **No; class incompatibility can also throw it**.
14. Do global filters and per-stream filters always intersect automatically? **Never assume; understand and test the filter factory**.
15. Does an `ALLOWED` class mean its field values are valid? **No**, post-deserialization validation is still required.
16. Does `ObjectInputFilter` alone defeat every gadget chain? **No; it shrinks the surface, not a sandbox**.
17. Should native Java serialization be used for public-facing APIs? **Prefer another schema/format**; if unavoidable, enforce defense in depth.

## 20. Official Documentation

- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): `FilterInfo`, `Status`, class/resource limits, and filter composition.
- [Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): `setObjectInputFilter`, `readObject`, and input errors.
- [Java SE 17 — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): `createFilter`, global filters, and filter factories.
- [Java SE 17 — Serialization Filtering Guide](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html): pattern-based filters, resource limits, and combining filters.
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): technical foundation, class and graph filtering semantics.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): context-specific filter policies and factories in Java 17.
