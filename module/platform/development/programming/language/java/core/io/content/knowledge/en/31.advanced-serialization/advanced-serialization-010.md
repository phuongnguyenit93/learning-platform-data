# ObjectInputFilter in Java 17: Limiting Classes, Depth, References, and Array Length

## 1. The Problem: Why Filter Data During Deserialization?

`ObjectInputStream.readObject()` turns a byte sequence formatted in **Java Object Serialization** into instances, arrays, and an **object graph**. If the stream comes from a file, message broker, socket, or source not wholly controlled by the application, reading is not merely "parsing data."

A stream may contain:

- Classes unwanted by the application, including classes with special deserialization logic.
- A very deeply nested object graph, increasing the risk of stack or resource exhaustion.
- Huge numbers of objects/references, consuming heap and processing effort.
- Extremely large arrays, causing the application to attempt massive memory allocations.
- Complexly encoded data or structures that can stall processing.

`java.io.ObjectInputFilter` is a **control gate while deserialization is underway**: it can decide to allow/reject classes and cap object graph resource metrics. It was introduced in Java 9 and is available on Java 17+.

However, **filters alone do not make Java native serialization completely safe**. They do not replace input authentication, authorization, post-deserialization data validation, protocol-level request size limits, or application resource management.

### Four Core Limits

| Limit | Meaning | Problem Category Mitigated |
|---|---|---|
| **Class allowlist** | Accepts only permitted types | Deserialization of unexpected classes |
| **`maxdepth`** | Caps traversal depth of the graph | Overly deep graphs, stack/cost spikes |
| **`maxrefs`** | Caps the number of references observed during deserialization | Graphs with excessive references |
| **`maxarray`** | Caps the number of elements in an array | Single arrays demanding huge allocations |
| **`maxbytes`** | Caps stream bytes consumed at check checkpoints | Large/resource-intensive inputs |

The topic emphasizes the four axes of class, depth, references, and array length. `maxbytes` is a highly recommended supplementary limit, **not** a replacement for capping payload sizes before creating ObjectInputStream.

## 2. How ObjectInputFilter Is Invoked

The interface defines the method:

~~~java
ObjectInputFilter.Status checkInput(ObjectInputFilter.FilterInfo info);
~~~

While `ObjectInputStream` processes data under Java serialization mechanics, it consults the filter at various points to inspect the **class** and **object graph metrics**. The `FilterInfo` object provides current state:

| `FilterInfo` | Returned Data | Note |
|---|---|---|
| `serialClass()` | Class under consideration; **may be null** | Null does not mean the request is definitely valid |
| `arrayLength()` | Array length; typically `-1` when not an array | Compare directly against maxarray threshold |
| `depth()` | Current graph depth | Not the class inheritance depth |
| `references()` | Reference index of the read process | Not distinct object count or business ID |
| `streamBytes()` | Stream bytes read at the checkpoint | Not total file length; limit triggers at checkpoints |

Conceptual flow:

~~~text
ObjectInputStream.readObject()
        |
        v
   Read token / class / array / reference
        |
        v
   filter.checkInput(FilterInfo)
        |
        +--> ALLOWED   : this check step accepts
        +--> REJECTED  : reject, abort with deserialization error
        +--> UNDECIDED : filter makes no decision at this step
        |
        v
   If not rejected, continue processing graph
~~~

### Is the Filter Called for Every Byte and Every String?

**No.** Under the serialization filtering contract, the filter is not a parser called after *every byte* or for every kind of value. Strings encoded directly in the stream and primitive values have exceptions in filter invocation; references to existing object handles may be checked differently. Documentation describes checks upon encountering new instances, arrays, and certain references, so **never treat this as a full semantic inspection of the data**.

Consequences:

- Do not use ObjectInputFilter to validate **String content**, individual byte contents, or business field values.
- Use class filters and resource limits, then **validate objects after reading**.
- Cap payload bytes at ingress (HTTP request body, file length, framed socket message) to block oversized inputs upfront rather than relying wholly on `streamBytes()`.

## 3. Three Outcomes: `ALLOWED`, `REJECTED`, `UNDECIDED`

`checkInput(...)` must return one of these statuses:

~~~java
ObjectInputFilter.Status.ALLOWED
ObjectInputFilter.Status.REJECTED
ObjectInputFilter.Status.UNDECIDED
~~~

- **`ALLOWED`:** the filter permits the information checked in this call. **Not** a guarantee that the complete object is semantically valid or safe.
- **`REJECTED`:** denied; `ObjectInputStream` will fail deserialization, normally with `InvalidClassException`.
- **`UNDECIDED`:** the filter makes no decision in this call. **Do not infer "denied by default."**

A common security bug is a filter that blocks a few known dangerous classes and returns `UNDECIDED` for all others. Without another filter layer rejecting them, unlisted classes outside the denylist can still be deserialized.

**Safer allowlist policy:** check resource limits first; return `ALLOWED` for truly permitted classes; return `REJECTED` for all remaining classes. When `serialClass()==null` because no class info exists in that callback, still enforce limits and return `UNDECIDED` for that check alone.

Decision examples:

~~~text
Class Message allowed, length 4, depth 2      -> ALLOWED
Class Gadget not in allowlist                -> REJECTED
Class Message allowed, but depth 100         -> REJECTED
No class in callback, metrics valid          -> UNDECIDED
No class in callback, maxrefs exceeded       -> REJECTED
~~~

**Never let allowlist conditions override limit conditions.** An allowed class containing a gigantic array must still be blocked.

## 4. Limiting Classes: Allowlist Instead of Blacklist Alone

When an application expects a DTO like `com.example.dto.Order`, it should not deserialize arbitrary classes found on the classpath. Two ways to implement:

1. **Pattern filter** using `ObjectInputFilter.Config.createFilter(...)`.
2. **Programmatic filter** using a lambda/class implementing `ObjectInputFilter`.

### Pattern Filter

Illustrative configuration example:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=10;maxrefs=1000;maxarray=10000;"
              + "maxbytes=1048576;"
              + "com.example.dto.*;java.base/java.util.ArrayList;!*");
~~~

Explanation:

- Parts are separated by semicolons `;`.
- Limits like `maxdepth=10`, `maxrefs=1000`, `maxarray=10000`, `maxbytes=1048576` apply independently of class pattern order.
- `com.example.dto.*` is a pattern for classes in the stated package per JDK pattern rules.
- `java.base/java.util.ArrayList` is a module-prefixed pattern targeting a specific class in the Java module.
- `!*` rejects **classes not matched by earlier allow patterns**.

**Important warning:** A pattern filter checks **object types**, not the full DTO schema rules across fields. A DTO may contain collection implementations, nested classes, or arrays that must be reviewed individually. Do not copy the allowlist above to production without testing the actual structure and classes queried by the filter during reads.

### Which Pattern Matches Which Class?

Per Java serialization filter patterns:

| Form | Common Meaning |
|---|---|
| `com.acme.dto.Order` | Exact fully qualified class |
| `com.acme.dto.*` | Classes directly in the specified package |
| `com.acme.dto.**` | Includes the package and all subpackages |
| `!com.acme.Bad` | Rejects the matched class |
| `!*` | Rejects remaining classes not allowed |
| `java.base/java.util.ArrayList` | Class with module name |
| `maxdepth=20` | Depth limit, **not** a class pattern |

For array classes, matching uses the **element type** per specification. Class patterns do not exhaustively enumerate every array dimension/shape; array length is still checked via `maxarray`.

**Do not confuse `"package.*"` with a wildcard for arbitrary packages, and do not mistake class patterns for field-value checks.** Read the Java 17 pattern matching rules, especially regarding module prefixes, nested classes, and arrays.

### Do Not Broadly Allowlist Huge Packages

For example, `java.base/*` or `java.**` (depending on pattern syntax) can be far too broad if the application only needs a few DTOs. The wider the set of deserializable classes, the larger the attack surface.

Normally, design **dedicated minimal DTOs** with fixed field types, carrying no runtime services, threads, class loaders, or callback objects in the stream. Avoid direct library serialization on complex domain objects.

## 5. `maxdepth`: Depth of the Object Graph

`depth()` is the current depth while decoding references, not:

- Class inheritance `extends` depth.
- Package name length.
- JSON depth under another parser.
- Count of unique objects in the entire stream.

Example:

~~~text
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
~~~

If a graph is chained too deeply, deserialization can exhaust stack and CPU. The `maxdepth` limit rejects graphs exceeding the threshold at callbacks.

Example:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=100;maxarray=1000;maxbytes=65536");
~~~

This snippet configures only resource limits, **with no class allowlist**, so it is not a complete safety filter for untrusted inputs.

**How to choose maxdepth:** measure and understand valid graphs. If a DTO has at most three levels (Envelope → Payload → Item), there is no reason to allow 10,000 levels. Yet do not guess too low and reject valid graphs due to collections, wrappers, or nested references.

### Reference Cycles and Depth

Java Object Serialization uses object handles and back-references to preserve cyclic graphs. A cycle A → B → A does not mean the serializer recurses infinitely: when encountering A again, it uses a handle rather than creating a new A. Still, many nested levels before hitting a back-reference can make a graph deep. `maxdepth` acts as a dedicated guardrail.

## 6. `maxrefs`: Limiting Processed References

The `references()` metric reflects **references observed during deserialization** per the FilterInfo contract. It is **not**:

- Distinct instances remaining after reading finishes.
- Number of fields defined on a class.
- Stream byte count.
- Object ID or `System.identityHashCode()` value.

For instance, an ArrayList with 100,000 entries pointing to the same object can generate huge reference counts in the stream despite few distinct objects. Therefore `maxrefs` must be capped independently of class checks.

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=12;maxrefs=5000;maxarray=10000;"
              + "maxbytes=2097152");
~~~

If `references()` exceeds `5000` at a check, the filter rejects. Because metrics are checked at callbacks, do not treat it as an exact guarantee of total memory footprint.

### Maxrefs and Shared References

Java serialization preserves multiple fields pointing to the same object via stream handles. Still, maxrefs matters even when references share one object. **Do not mitigate risk solely by limiting class count**: a single valid DTO class can still construct an enormous reference graph.

## 7. `maxarray`: Blocking Oversized Array Allocations

A payload containing `byte[]`, `int[]`, or `Order[]` can request huge memory before the program can inspect its contents. When deserializing an array, `FilterInfo.arrayLength()` supplies the length if known, letting the filter reject before the array is allocated.

Example:

~~~java
ObjectInputFilter f =
        ObjectInputFilter.Config.createFilter(
                "maxarray=10000;maxdepth=10;maxrefs=1000;"
              + "maxbytes=1048576");
~~~

`maxarray=10000` is **element count**, not byte count:

- `byte[10000]` has 10,000 byte elements.
- `long[10000]` has 10,000 long elements, taking much more memory.
- `Object[10000]` has 10,000 references, plus the objects they point to consume separate resources.

Do not equate `maxarray=1000000` with "1 MiB max" across all array types. Pair with `maxbytes`, `maxrefs`, and realistic input size caps.

### When Not an Array: `arrayLength() == -1`

In a custom filter, a negative value normally means **no array length information applies to this callback**. Hence:

~~~java
long length = info.arrayLength();
if (length >= 0 && length > MAX_ARRAY_LENGTH) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

Do not require every class check to have `arrayLength() >= 0`: otherwise even valid DTOs without arrays will be rejected.

## 8. `maxbytes`: Capping Read Bytes, Not Replacing Ingress Caps

`maxbytes` relies on `FilterInfo.streamBytes()`. If exceeded, the filter rejects at the checkpoint. However, the filter **is not called for every byte**; streams carrying specialized payloads or reads outside ObjectInputStream can demand separate controls.

Layered protection:

~~~text
HTTP/Socket/File input
   -> max 1 MiB payload before deserialization
   -> ObjectInputStream with allowlist + graph limits
   -> DTO is deserialized
   -> validate field values, business invariants
   -> only then process business logic
~~~

Over a network, if input is a continuous byte stream, use a **bounded length-prefix** or disciplined framing instead of reading unboundedly until EOF. Over HTTP, enforce max request body size. For files, checking `Files.size` helps, though files can change between check and read, so bounded streams/protocols are needed.

## 9. Complete Java 17+ Program: One Allowed Payload and One Rejected Payload

Example using a **custom ObjectInputFilter** to make checks clear:

- Allows only the `Message` DTO and the `byte[]` array used by that DTO.
- Caps `depth <= 8`, `references <= 64`, `arrayLength <= 8`, `streamBytes <= 65536`.
- Reads a 4-byte payload successfully.
- Rejects a payload containing a 12-byte array **before accepting the complete object**.
- Uses no network sources or real files, since exercises require deterministic output.

Save as **`InputFilterDemo.java`**:

~~~java
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
            // Always check resource limits before the class allowlist.
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
~~~

Compile and run commands:

~~~bash
javac InputFilterDemo.java
java InputFilterDemo
~~~

**Expected stdout on Java 17 under default serialization:**

~~~text
allowed: id=7, length=4
too-large: REJECTED
~~~

Step-by-step explanation:

1. `Message` implements `Serializable`, containing an `int` and a `byte[]`.
2. `encode(...)` produces bytes via native Java serialization; writing does not apply an input filter because filtering is a **read** mechanism.
3. `decode(...)` constructs `ObjectInputStream`, **installing the filter before the first `readObject()` call**.
4. For `Message(7, byte[4])`, `Message` and `byte[]` are allowed; depth/references/streamBytes are within bounds, so the object is built and printed.
5. For `Message(8, byte[12])`, when the filter is queried for an array of length 12, `arrayLength() > 8` returns `REJECTED`. Deserialization throws `InvalidClassException`, and the program prints `too-large: REJECTED`.
6. Exception messages are not printed because exact wording can vary across implementations/JDK builds.

Note: the example wraps `readObject()` in `try/catch InvalidClassException` to demonstrate filtering. In production, distinguish corrupted streams, I/O errors, schema mismatches, and filter rejections separately—**do not assume every InvalidClassException comes from a filter**. Moreover, this custom filter only describes expected types in a tiny DTO; complex DTOs need allowlists and tests for nested types/arrays.

### Examining the Meaning of `UNDECIDED` in the Example

When `serialClass() == null`, the custom filter returns `UNDECIDED` **after** checking resource limits. That is proper when deliberately designing a policy for observed classes; however, in complex applications, combining a filter with a global filter factory can change how `UNDECIDED` is resolved. Never assume `UNDECIDED` automatically rejects.

## 10. Writing Pattern-Based Filters for Typical Systems

When the class schema is known, patterns are convenient and require less code:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=64;maxarray=8;maxbytes=65536;"
              + "com.example.messages.Message;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object o = in.readObject();
}
~~~

This is **illustrative code**; `source` is an application-created `InputStream` and `com.example.messages.Message` is a hypothetical DTO class. With arrays, nested classes, and filter factories, test against real valid/invalid inputs before deployment. If any valid nested type gets blocked by `!*`, **explicitly add it** to the allowlist instead of deleting deny-by-default.

**Common pitfall:** `createFilter(...)` with only `maxdepth/maxrefs` does not build a class allowlist. Appending `!*` closes the policy against unmatched classes; conversely, without a catch-all reject rule, unmatched classes can yield `UNDECIDED`.

### Properly Combining Pattern Limits

Suggested workflow for authoring patterns:

1. List permitted root DTOs based on the real schema.
2. Build sample valid streams including nested collections, arrays, and nullable fields.
3. Turn on a tight allowlist; observe which classes the filter is queried for in tests.
4. Permit **only** the exact classes needed; avoid overly broad wildcards.
5. Set `maxdepth` and `maxrefs` from valid graph statistics plus a small safety margin.
6. Set `maxarray` to the largest array size accepted by business rules.
7. Set `maxbytes` and full request byte caps at ingress.
8. Add negative tests: unknown classes, deep nesting, massive arrays, excessive references.

## 11. Per-Stream Filter, Global Filter, and Filter Factory

### 11.1. Per-Stream: Configured on Individual ObjectInputStreams

~~~java
try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(filter);
    Object result = in.readObject();
}
~~~

Suitable when different payload types or trust levels need distinct allowlists. Set the filter **immediately after creating the stream and before deserializing the first object**.

Do not create a stream, start calling `readObject()`, and only later install a filter expecting previously read objects to be retroactively checked.

### 11.2. Global Filter: JVM-Wide Policy

Java supports a JVM-wide filter via **system property** or API, for example:

~~~text
-Djdk.serialFilter=maxdepth=20;maxrefs=10000;maxarray=100000;maxbytes=10485760
~~~

This is an illustrative setting; semicolon escaping depends on your shell/launch command. A runtime-wide policy can be set at application startup. `ObjectInputFilter.Config.setSerialFilter(...)` also exists to set the static JVM-wide filter, though rules govern when/whether it can be reset and required permissions; do not call it repeatedly across the application lifecycle.

**A global filter is defense-in-depth**, not an excuse for individual streams reading untrusted inputs to skip dedicated class allowlists.

### 11.3. Java 17: Filter Factory and Composition

Java 17 supports **context-specific deserialization filters** via a filter factory (JEP 415). API:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory(
        (current, requested) -> {
            // Decide how to combine or choose policy.
            // Conceptual example only; understand the full contract
            // and JVM-wide configuration ownership.
            return requested != null ? requested : current;
        });
~~~

This is an **illustrative configuration snippet**, not a safe policy to copy into applications: it can replace the current policy with the requested one, dropping prior restrictions. **Do not use the factory above to ensure both global and per-stream filters remain active.**

Key points to understand:

- The factory receives the current filter and requested filter, returning the effective filter for the stream in that context.
- A misconfigured factory can accidentally drop global limits when a per-stream filter is set.
- The specification allows early factory configuration; this is a JVM-wide policy requiring centralized design/testing, not ad-hoc configuration after server startup.
- When combining allowlists and limits, clearly define the **union or intersection** of policies, ensuring any `REJECTED` from mandatory limits is always respected.

**Recommendation:** for small apps, use a dedicated filter installed before `readObject` containing **both class rules and resource limits**. For multi-module/multi-library systems, design a shared factory with integration tests proving no path bypasses minimum policy.

## 12. What Happens When a Filter Returns `REJECTED`?

When an input is rejected by the filter, `ObjectInputStream` throws an error; in practice typically `InvalidClassException` carrying a filter-status message. Do not rely on exact message strings as a stable API.

Handling template:

~~~java
try {
    Object result = in.readObject();
    validateBusinessFields(result);
} catch (InvalidClassException e) {
    // May be due to filter rejection or class incompatibility.
    // Log safely and terminate the request in an error state.
} catch (StreamCorruptedException e) {
    // Binary stream is malformed.
} catch (ClassNotFoundException e) {
    // Class requested by stream cannot be found.
} catch (IOException e) {
    // I/O or serialization protocol error.
}
~~~

The snippet above is illustrative; `in` and `validateBusinessFields` are defined externally. Never continue deserializing the remainder of the same untrusted input after a serious failure as if stream alignment remained valid; close the stream/request and report an error.

**Avoid logging raw untrusted payloads or object graphs.** Doing so can leak sensitive data or trigger complex `toString()` calls after reading objects.

## 13. Limits ObjectInputFilter Does Not Solve

Filters are essential when Java Object Serialization is still used, but should not be "over-trusted":

### Does Not Validate Business Fields

An allowed object can still contain `amount=-999999`, invalid dates, invalid enum states, or duplicates. Filters govern **types and graph dimensions**, not business rules. After `readObject`, validate against schema and domain constraints.

### Does Not Automatically Prevent Every Gadget Chain

Allowing certain classes does not mean those classes are always harmless, and `readObject`, `readResolve`, `readExternal`, or custom callbacks on those classes can execute during deserialization. A class allowlist shrinks the attack surface, yet permitting classes with side effects remains risky. Only deserialize audited data classes.

### Not a Byte-Level Parser or Checksum

Filters do not verify digital signatures, check CRCs, protect against protocol-valid tampering, decrypt, or authenticate the sender. TLS/authentication, message integrity, and authorization are still required.

### Does Not Replace Timeouts or Total CPU/Memory Caps

Each callback supplies only local metrics. Custom logic during deserialization can consume CPU; file/network requests can stall, drop mid-stream, or carry bytes not yet inspected by the filter. Set external deadlines, bounded inputs, quotas, and monitoring.

### Does Not Make Object Serialization Fit Every System

Java native serialization is tied to Java types, class descriptors, and `serialVersionUID`. In public APIs or cross-language communication, explicit-schema formats (JSON/CBOR/Protocol Buffers, etc.) are often better suited; validation/limits still apply to any parser.

## 14. Differences Between Filters, `transient`, and `serialVersionUID`

- `transient`: controls **which fields** default serialization writes/reads. It **does not** stop unexpected classes from appearing in the stream.
- `serialVersionUID`: aids class version compatibility checks; **not** a class allowlist or authenticity signature.
- Custom `readObject(...)`: can govern deserialization data/logic; if unchecked, an allowed class can still construct unwanted objects or side effects.
- `ObjectInputFilter`: enforces class/resource constraints at read checkpoints.

Combine all four only for their respective roles; never treat one tool as replacing the others.

## 15. Designing a Custom Filter Properly with `FilterInfo`

With a callback:

~~~java
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
~~~

This snippet is illustrative because `MyAllowedDto` is application-defined. Keep in mind:

1. **Limits before allowlist**: allowed classes must still never consume unbounded resources.
2. **Null class** must not cause the filter to skip depth/references/bytes/array checks.
3. **Array length = -1** when no array length applies: comparing `> positiveThreshold` avoids accidentally rejecting.
4. **Do not call complex methods inside the filter**: the filter runs on the deserialization path, so it must be short and deterministic.
5. **Do not access network/databases in checkInput**: easily causes deadlocks, slowdowns, or expanded failure surfaces.
6. **Do not return UNDECIDED for unknown classes** if you want a closed class allowlist.
7. **Do not accidentally block arrays of allowed types** by forgetting `byte[].class` or valid arrays; write real tests.
8. **Do not treat ALLOWED as fully validated**; still validate object invariants after reading.

## 16. Tuning Limit Policies for Real Workloads

No single set of numbers fits every application. Design workflow:

- Measure the depth and reference count of a **largest valid payload**.
- List expected array types and sizes.
- Determine an **ingress request size limit** lower than what would overload heap/CPU.
- Pick thresholds with a modest safety margin rather than infinity.
- Write tests for both valid payloads right near the limit and payloads exceeding the limit.
- Test inputs with reference cycles, many shared handles, and nested arrays.
- Watch out for messages with large Strings: filters do not measure string content like validators; maxbytes/checkpoints and bounded inputs matter.
- Monitor filter rejection rates, without logging untrusted payloads or sensitive data.

Sample policy for a small DTO with an array payload up to 4 KiB:

| Rule | Example Value | Rationale |
|---|---:|---|
| Class allowlist | `OrderMessage`, exact nested types | Reduce unexpected classes |
| `maxdepth` | 12 | Enough for a shallow graph |
| `maxrefs` | 2000 | Cap references |
| `maxarray` | 4096 | Array at most 4096 elements |
| `maxbytes` | 65536 | Stop oversized streams at callbacks |
| Ingress cap | 65536 bytes | Bound payload size before deserialization |

These numbers are **configuration examples only**, not universal safety baselines. If `OrderMessage` holds huge Strings or nested maps creating many classes, adjust both schema and policy.

## 17. Security Testing: Require Both Positive and Negative Cases

| Test | Test Input | Expectation |
|---|---|---|
| Allowed class | DTO in allowlist, normal size | Reads successfully, passes business validation |
| Unknown class | Another Serializable class | `REJECTED` |
| Oversized array | `byte[limit+1]` | `REJECTED` |
| Deep nested graph | Long chain exceeding maxdepth | `REJECTED` |
| Excessive references | Graph with many references | `REJECTED` |
| Too many bytes | Stream exceeding maxbytes triggering checkpoint | `REJECTED` or blocked earlier by ingress cap |
| Corrupted stream | Damaged/truncated bytes | Fails cleanly, does not continue deserializing blindly |
| Compatible update | Expected DTO version | Reads/validates per policy |
| Incompatible class version | Incompatible UID/schema | Handles `InvalidClassException` |
| Null class info | Metrics-only callback | Still enforces limits; does not imply unknown is allowed |
| Global factory | Installing per-stream filter atop global policy | Does not drop JVM-wide limits |

Beyond unit tests, run integration tests matching the actual JDK/runtime and serializer libraries. If custom `readObject`/`readResolve` exist, test those paths as well.

## 18. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Using only a denylist of known classes | Other dangerous classes can slip through | Use a strict allowlist |
| Omitting `!*` at the end of a pattern intended as deny-by-default | Unmatched classes may be `UNDECIDED` | Add explicit reject rule |
| Allowing overly broad classes | Expands gadget/deserialization surface | Permit exact DTO and nested types |
| Not checking `maxdepth` | Deeply nested graphs | Set depth cap |
| Not checking `maxrefs` | Excessive references | Set reference cap |
| Treating `maxarray` as byte count | Huge `long[]` or `Object[]` | Understand it is element count |
| Setting only `maxbytes` without input limits | Filter is not a byte-level hard cap | Bound stream/request length |
| Returning `ALLOWED` before checking limits | Allowed class can consume excessive resources | Check limits first |
| Returning `UNDECIDED` for unknown classes assuming it rejects | Another filter may not block them | Return `REJECTED` for unknown classes |
| Setting filter after reading objects | Fails to protect already-processed data | Set before first `readObject` |
| Assuming `serialClass()!=null` in every callback | NullPointerException or skipped metrics | Handle null properly |
| Global/per-stream filters inadvertently replacing each other | Security limits lost | Design/test filter factory |
| Assuming filters validate String/content | Invalid business values accepted | Validate at DTO layer |
| Catching `InvalidClassException` and reading further in stream | State can no longer be trusted | Close stream/request, report error |
| Thinking Internet deserialization is safe by default thanks to filters | Large attack surface remains | Prefer safer formats and defense-in-depth |

## 19. Self-Check Questions

1. Is `ObjectInputFilter` used during serialization or deserialization? **During deserialization** via ObjectInputStream.
2. Does `UNDECIDED` mean definitely rejected? **No.** It is the status where the filter makes no decision.
3. Which should be checked first in a custom filter: class allowlist or resource limits? **Check resource limits first.**
4. Can all checks be skipped when `serialClass() == null`? **No; still check depth, references, arrayLength, and streamBytes.**
5. Does `maxdepth` limit class inheritance depth? **No; it limits object graph depth while reading.**
6. Is `maxrefs` the number of unique instances? **No, it is a reference metric during deserialization.**
7. Does `maxarray=500` mean at most 500 bytes for any array? **No, at most 500 array elements.**
8. If `arrayLength() == -1`, what should you do? **Do not treat it as an invalid negative-length array; it signals no length info applies.**
9. Can `maxbytes` replace an ingress size cap? **No.**
10. In patterns, what is `!*` used for? **Rejecting classes not matched by earlier allowlist rules.**
11. When should `setObjectInputFilter` be called? **Before starting `readObject()`.**
12. When a filter rejects a class, what exception typically occurs? **`InvalidClassException`.**
13. Is `InvalidClassException` always caused by a filter? **No; class incompatibility can also cause it.**
14. Do global filters and per-stream filters always stack limits automatically? **Do not guess; understand and test the filter factory.**
15. Does an `ALLOWED` class mean its field values are valid? **No**, post-deserialization validation is required.
16. Does ObjectInputFilter automatically defeat every gadget chain? **No; it shrinks surface, it is not a sandbox.**
17. Should Java native serialization be used for public-facing APIs? **Generally prefer another format/schema**, and if forced, apply defense-in-depth.

## 20. Official Documentation

- [Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): FilterInfo, Status, class/resource limits, and filter composition.
- [Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): `setObjectInputFilter`, `readObject`, input errors.
- [Java SE 17 — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): `createFilter`, global filter, and filter factory.
- [Java SE 17 — Serialization Filtering Guide](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html): pattern-based filters, resource limits, and combining filters.
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): technical foundation, class and graph filtering semantics.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): context-specific filter policies and factories in Java 17.
