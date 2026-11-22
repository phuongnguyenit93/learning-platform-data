# Stream-Specific Filters, JVM Configuration, and JDK Version Dependencies in Java Serialization

When calling `ObjectInputStream.readObject()`, an application feeds a byte stream into **Java deserialization**. A malicious stream can request reconstructing unwanted class types or huge, deeply nested object graphs that exhaust resources. **`ObjectInputFilter`** (serialization filter) lets the application inspect class names and certain graph metrics during reading, returning **`ALLOWED`**, **`REJECTED`**, or **`UNDECIDED`**.

There are three configuration layers that are easily confused:

1. **Stream-specific filter:** set on **one** `ObjectInputStream`, for example `input.setObjectInputFilter(filter)`.
2. **JVM-wide/static filter:** configured via `-Djdk.serialFilter=...` or `ObjectInputFilter.Config.setSerialFilter(...)`, applied at JVM level per the filter selection mechanism.
3. **JVM-wide filter factory (since JDK 17):** selects or combines filters for **each stream** when `ObjectInputStream` is created and when a stream-specific filter is requested; configured via `jdk.serialFilterFactory` or `setSerialFilterFactory`.

Do not assume that enabling just any filter makes deserializing untrusted data safe. A filter is an **additional defense layer**. The safer choice remains avoiding Java native deserialization for untrusted data, using instead a data format with schema validation, authentication, and resource limits.

## 1. Core APIs and Risks to Bound

Related classes belong to package `java.io`:

| API | Role |
| --- | --- |
| `ObjectInputStream` | Reads objects from a Java serialization stream |
| `ObjectInputFilter` | Interface evaluating objects/classes and graph metrics during deserialization |
| `ObjectInputFilter.FilterInfo` | Current context: `serialClass()`, `arrayLength()`, `depth()`, `references()`, `streamBytes()` |
| `ObjectInputFilter.Status` | Three decisions: `ALLOWED`, `REJECTED`, `UNDECIDED` |
| `ObjectInputFilter.Config` | Builds filters from pattern strings, reads/sets the JVM-wide static filter and filter factory |
| `ObjectInputStream.setObjectInputFilter(...)` | Requests applying a specific filter to a stream |
| `ObjectInputStream.getObjectInputFilter()` | Inspects the effective filter applied to the stream per actual configuration |

A filter can control **which class types are constructed and resource metrics**. It is not a business-value validator; nor does it verify sender identity, guarantee a constructed object has valid state, or turn serialization data into a safe sandbox.

A payload can be dangerous because an allowed class has custom `readObject()`/`readResolve()`, because the graph is too deep, because reference chains are excessive, or because field data is invalid. Hence you need **use-case class allowlists**, **graph limits**, **byte/CPU limits**, and **post-read data validation**.

## 2. Lifecycle of a Filtered Stream

Typical flow:

```text
Trusted or controlled byte source
          |
          v
new ObjectInputStream(inputBytes)
          |  (JVM-wide filter factory selects initial filter)
          v
setObjectInputFilter(streamPolicy)
          |  (filter factory decides effective filter)
          v
readObject()
          |  filter checks class / array / depth / refs / streamBytes
          +--- REJECTED  --> read operation fails
          +--- ALLOWED   --> continue deserialization process
          +--- UNDECIDED --> not confirmed allowed; handled per composition policy
          v
Verify type, business validity, close stream
```

In JDK 17, `ObjectInputStream` is created with an initial filter via the factory. When calling `setObjectInputFilter()`, **the factory again determines the final filter** based on the current filter and the newly requested filter. Therefore calling this method should not be assumed to mean "definitely only the newly passed filter remains" or "definitely merged with global" in every application: **behavior depends on the active factory**.

Important boundary points:

- A filter may be invoked **zero or more times**, depending on stream content and processing steps. Some specially encoded values, such as `String` and primitives in certain forms, **do not necessarily trigger a class-check callback for every value**.
- `FilterInfo.serialClass()` may be `null` when a check only evaluates graph/resource limits, so do not dereference it blindly.
- When encountering an array, the filter can be called with the array class and can read `arrayLength()`. Pattern filters match the **element type** for arrays rather than simply matching names like `[Ljava.lang.String;`.
- `arrayLength()` can be `-1` when not checking an array; do not compare it against the real size of arbitrary collections.
- Filters evaluate **before or during graph construction**; they do not guarantee rejecting an object before any side effect of another deserialization step occurs. Do not use them in place of verifying the data source.

## 3. Stream-Specific Filters: Separating Policies per Stream

A service may have multiple inputs. For example, one stream should accept only `InvoiceDTO`, while another accepts `CacheSnapshot`. Using one class list for everything easily grants broader deserialization privileges than needed.

With JDK 9+ and JDK 17, you can build a pattern filter and request attaching it to `ObjectInputStream`:

```java
// Illustrative inside a read method, before readObject().
ObjectInputFilter policy = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=200;maxbytes=1048576;maxarray=10000;" +
        "com.example.dto.**;java.base/java.util.*;!*");

try (ObjectInputStream in = new ObjectInputStream(source)) {
    in.setObjectInputFilter(policy);
    Object value = in.readObject();
    // Check concrete type and validate data structure.
}
```

This is an **illustrative snippet**, leaving `source` and `com.example.dto` classes undefined; it is not a standalone compilable program. If the application uses `List`, `Map`, arrays, or other internal classes, test the policy against the **entire valid object graph** rather than assuming the pattern above always fits.

**Setting the filter before the first read** is an essential habit. With the standard API, never wait until after reading part of an object to decide to install a filter. If `ObjectInputStream` is owned by a framework/library, calling `setObjectInputFilter()` might be disallowed or too late; coordinate configuration right where the stream is created.

### When to Use a Custom Filter Instead of Patterns?

When logic beyond class names is required, write a lambda against `ObjectInputFilter.FilterInfo`:

```java
// Illustrative inside a program that imported java.io.ObjectInputFilter.
ObjectInputFilter policy = info -> {
    if (info.depth() > 12
            || info.references() > 1000
            || info.streamBytes() > 1_048_576
            || info.arrayLength() > 10_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }
    if (type == ExampleDTO.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }
    return ObjectInputFilter.Status.REJECTED;
};
```

This is **illustrative**; `ExampleDTO` is a hypothetical application class, not a standalone file. This filter permits only `ExampleDTO` on callbacks with a concrete class: if `ExampleDTO` has fields of other classes/arrays requiring deserialization, the filter will reject them. In real systems, account for every valid type and do not overlook primitive arrays, collections, proxies, nested classes, or dependent objects.

## 4. Three Outcomes: ALLOWED, REJECTED, UNDECIDED

| Outcome | Meaning |
| --- | --- |
| `ALLOWED` | Current check passes this filter policy; deserialization continues |
| `REJECTED` | Denied; deserialization will fail, typically surfaced via `InvalidClassException` |
| `UNDECIDED` | Filter makes no decision for this check; **not ALLOWED in the allowlist sense** |

With `ObjectInputFilter.Config.createFilter(pattern)`, the system evaluates **resource limits first**, then evaluates class patterns **from left to right**. The first matching pattern decides ALLOWED/REJECTED; if none matches and no threshold is exceeded, the outcome is UNDECIDED.

If the effective filter returns UNDECIDED for a class and nothing else rejects it, reading can proceed. Thus **listing allowed classes without adding a reject rule for everything else does not necessarily yield a "deny by default" allowlist**.

A common pattern ends with `!*`:

```text
com.example.api.**;java.base/java.util.*;!*
```

This accepts classes matching the first two patterns, then rejects remaining classes when checked. Still, do not open entire large packages if the application only needs a few specific DTOs; every class in an allowed package/module must belong to your trust model.

JDK 17 provides utilities `ObjectInputFilter.merge(...)` to combine filters and `ObjectInputFilter.rejectUndecidedClass(...)` to handle undecided outcomes on class checks. Their usage must be evaluated per system; do not assume "merge" always equals pattern concatenation or always behaves like the intersection of two allowlists.

## 5. JVM-Wide Configuration via jdk.serialFilter

If an application or library creates `ObjectInputStream` in many hard-to-modify places, you can configure a static filter **at JVM startup**:

```bash
java '-Djdk.serialFilter=maxdepth=12;maxrefs=5000;maxbytes=10485760;maxarray=100000;com.example.dto.**;!*' com.example.Main
```

This is an **illustrative command**: `com.example.Main` and the DTO package must exist in your application. On specific shells, argument quoting may differ; ensure the **entire pattern string containing `;` is passed as a single JVM option**, because semicolons in shells can act as command separators.

Basic thresholds:

| Pattern | Meaning |
| --- | --- |
| `maxdepth=12` | Caps graph depth during deserialization |
| `maxrefs=5000` | Caps tracked references |
| `maxbytes=10485760` | Caps tracked serialization stream bytes |
| `maxarray=100000` | Caps single array length, **not the size of arbitrary collections** |
| `com.example.dto.**` | Allows classes in matching package and subpackages |
| `java.base/java.util.*` | Allows classes directly in package `java.util` of module `java.base` |
| `!*` | Rejects remaining classes when checked by the filter |

The static filter is configured via the **system property `jdk.serialFilter`**; when absent, the JVM can fall back to the **security property of the same name** from security configuration. The system property takes precedence over the security property during `ObjectInputFilter.Config` initialization.

It can be set via API **if the static filter has not yet been set/configured**:

```java
// Illustrative for application bootstrap on Java 17.
ObjectInputFilter global = ObjectInputFilter.Config.createFilter(
        "maxdepth=12;maxrefs=5000;maxbytes=10485760;maxarray=100000");
ObjectInputFilter.Config.setSerialFilter(global);
```

`setSerialFilter()` is a **one-time JVM-level** setting, not a call to toggle per request. If a filter has already been set, you may get `IllegalStateException`; if a running Security Manager/permission check blocks the operation, you may get a security exception.

**Important:** Calling `System.setProperty("jdk.serialFilter", "...")` after `ObjectInputFilter.Config` has initialized **does not guarantee the static filter update takes effect**. Use JVM startup options or the bootstrap API at the proper time.

### JVM-Wide Configuration Does Not Mean "Guaranteed to Apply Alongside Per-Stream"

In JDK 17, a **filter factory** is invoked to choose the filter for each stream. The built-in factory uses the global filter when the stream is created, yet when code calls `setObjectInputFilter(streamPolicy)`, the built-in factory can **replace the global filter with the stream-specific filter** rather than automatically intersecting both policies. If a JVM-wide baseline protection must always remain active, do not merely infer from having set `jdk.serialFilter`; control/combine filters inside an appropriate factory.

## 6. JDK 17: Context-Specific Filter Factories (JEP 415)

Since JDK 17, `ObjectInputFilter.Config` provides a JVM-level filter factory to select **the effective filter for each `ObjectInputStream`**. It can consider the JVM-wide filter, the filter requested by stream code, and the call context (module, ThreadLocal, call stack, service owner…).

Set via API:

```java
// Sketch illustrating only how to combine two filters.
// Must be set at bootstrap, before any ObjectInputStream is created.
ObjectInputFilter.Config.setSerialFilterFactory((current, requested) -> {
    if (current == null) return requested;
    if (requested == null) return current;
    return ObjectInputFilter.merge(current, requested);
});
```

This is an **illustrative JVM-wide configuration snippet**, not a complete production policy. `current` is the stream's current filter (or `null` at initialization), and `requested` is the filter requested by the constructor or `setObjectInputFilter`. If `current` is already non-`null`, the factory must not return `null` to disable an existing filter.

In practice, assign clear ownership of JVM-wide config, test merge/UNDECIDED/REJECTED behavior, measure performance, and ensure per-stream policies do not accidentally **widen** or **reject** types needed by legitimate frameworks.

A factory class can be configured via a startup property:

```bash
java -Djdk.serialFilterFactory=com.example.security.MyFilterFactory com.example.Main
```

This factory class must be application-supplied, **`public`**, have a public no-arg constructor, implement `BinaryOperator<ObjectInputFilter>`, and be loadable by the appropriate class loader. The `jdk.serialFilterFactory` property is a **factory class name**, not a pattern string. It differs from `jdk.serialFilter`.

Under Java 17, the factory configuration can be set **only once** and before any `ObjectInputStream` is created. Configuration via system/security properties takes precedence and cannot be arbitrarily overridden afterward via API. Calling `System.setProperty("jdk.serialFilterFactory", "...")` after Config initializes **does not activate a new factory**.

### When Do You Need a Factory Instead of a Static Filter?

A multi-module application may receive varied payloads: payments use only `PaymentDTO`, caching uses `CacheSnapshot`, internal tools use `MigrationRecord`. A single JVM-wide allowlist broad enough for all of them widens the attack surface. A context-specific factory can combine **mandatory baseline limits** with an **allowlist tailored to each input**. Still, the context itself must be trusted—never take arbitrary class names from the sender's payload or request as a self-allowing policy.

## 7. Complete Java 17 Example: Per-Stream Allowlist Accepting One Class and Rejecting Another

This program constructs two serialization streams in memory. It reads no network data, making it safe to demonstrate filter checks. One class is allowed (`AllowedMessage`) and the other is `BlockedMessage`. Each read creates **a separate ObjectInputStream** and installs the same filter **before `readObject()`**.

Create the file **`SerialFilterDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class SerialFilterDemo {
    private SerialFilterDemo() {}

    private static final class AllowedMessage implements Serializable {
        private static final long serialVersionUID = 1L;
        private final int code;

        AllowedMessage(int code) {
            this.code = code;
        }

        int code() {
            return code;
        }
    }

    private static final class BlockedMessage implements Serializable {
        private static final long serialVersionUID = 1L;
        private final int code;

        BlockedMessage(int code) {
            this.code = code;
        }
    }

    private static byte[] encode(Serializable object) throws Exception {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(object);
        }
        return bytes.toByteArray();
    }

    private static Object decode(byte[] bytes) throws Exception {
        ObjectInputFilter policy = ObjectInputFilter.Config.createFilter(
                "maxdepth=8;maxrefs=100;maxbytes=8192;maxarray=128;" +
                "SerialFilterDemo$AllowedMessage;!*");

        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            in.setObjectInputFilter(policy);
            return in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] valid = encode(new AllowedMessage(42));
        AllowedMessage accepted = (AllowedMessage) decode(valid);
        System.out.println("allowed=" + accepted.code());

        byte[] invalid = encode(new BlockedMessage(99));
        try {
            decode(invalid);
            System.out.println("unexpected acceptance");
        } catch (InvalidClassException expected) {
            System.out.println("rejected=InvalidClassException");
        }
    }
}
```

Compile and run with **JDK 17**, under standard JVM configuration without a custom factory:

```bash
javac SerialFilterDemo.java
java SerialFilterDemo
```

Expected output:

```text
allowed=42
rejected=InvalidClassException
```

**Why does it produce this output?**

1. `encode` uses `ObjectOutputStream` to convert a valid instance into an in-memory byte array; it does not read objects back yet.
2. `decode` creates `ObjectInputStream` and installs the filter via `setObjectInputFilter` before reading. The pattern caps depth/references/bytes/array length and allows only the binary class name `SerialFilterDemo$AllowedMessage`.
3. The trailing `!*` rejects remaining classes when checked. `AllowedMessage` is in the allowed set, so `readObject()` returns the object with `code=42`.
4. `BlockedMessage` does not match the allowlist, so deserialization yields `REJECTED`, typically via `InvalidClassException`. The program catches that exception type and prints only the exception name, avoiding dependence on messages/stack traces that can vary across JVMs.
5. Because the class stores only a primitive `int` field, the example needs no extra allowlist entries for nested classes like `ArrayList` or other DTO types. If you add serializable reference fields, update the filter and re-test the object graph.

This is an illustrative filter example, **not a production-ready filter template for real data**. In environments where an application or framework configures a JVM-wide filter/factory, the effective filter may differ and must be tested before assuming identical demo behavior.

## 8. Pattern Syntax and Configuration Traps

The filter pattern syntax of `ObjectInputFilter.Config.createFilter` is a set of **semicolon-separated** components. For class patterns:

| Pattern | Meaning |
| --- | --- |
| `com.example.Foo` | Exact fully qualified class name |
| `com.example.*` | Classes directly in package `com.example` |
| `com.example.**` | Classes in package `com.example` and all subpackages |
| `com.example.Foo*` | Classes whose names start with the given prefix |
| `java.base/java.util.*` | Classes in module `java.base` and directly in package `java.util` |
| `!com.example.Dangerous` | Rejects this class |
| `!*` | Rejects all remaining matchable classes when placed at the end of the list |

Limits accept `maxdepth`, `maxrefs`, `maxbytes`, and `maxarray`. If a limit appears multiple times, the **last** value for that limit takes effect. Whitespace is part of the pattern and can cause names to fail to match; avoid stray spaces when configuring via properties.

Several traps:

- **Pattern order matters.** Putting `!*` before the allowlist leaves subsequent classes no chance to be allowed.
- **Binary names of nested classes** use `$` (e.g., `SerialFilterDemo$AllowedMessage`), not source syntax `SerialFilterDemo.AllowedMessage`.
- **Class patterns differ from content validation.** Allowing `java.util.ArrayList` does not stop a list from holding invalid business data or too many elements when a limit does not cover that exact scenario.
- **The `streamBytes` limit is not a process-wide budget.** Each `ObjectInputStream` tracks its own state; many concurrent streams can still consume huge resources.
- **UNDECIDED does not provide deny-by-default protection.** If you want to forbid unknown classes, design an explicit reject policy.
- **Do not use filters like "allow all of `java.base`" out of habit.** That exposes far more classes than actually needed.
- **Never read payload first and install the filter afterward.** Pick the policy before the first operation requiring protection.

## 9. JDK Version Dependencies: JEP 290 and JEP 415

| JDK Line | Capabilities and Notes |
| --- | --- |
| Old Java 6/7/8 before serialization filtering patches | Cannot assume JDK 9+ APIs exist |
| Certain JDK 6/7/8 updates from the Jan 2017 Critical Patch Update | Have backported filtering; legacy API may live in `sun.misc.ObjectInputFilter`, differing from JDK 9+ standard imports |
| JDK 9 (JEP 290) | `java.io.ObjectInputFilter`, per-stream and JVM-wide filters; class/graph limits |
| JDK 11 | Uses `java.io.ObjectInputFilter` but cannot assume JDK 17 filter factory APIs |
| JDK 17 (JEP 415) | Adds **context-specific filter factories**, `Config.setSerialFilterFactory`, and `jdk.serialFilterFactory`; includes policy composition helpers |
| Later JDKs | Check API docs, release notes, config flags, and actual behavior of the specific JDK/vendor; do not assume complete equivalence to JDK 17 |

Key milestones:

- **JEP 290 – Filter Incoming Serialization Data**: introduced in Java 9; JDK 8u121, 7u131, and 6u141 received backports. Do not assume source code importing `java.io.ObjectInputFilter` compiles unchanged on old JDKs: backport packages/APIs differ.
- **JEP 415 – Context-Specific Deserialization Filters**: introduced in JDK 17. A program requiring `setSerialFilterFactory` should declare and test a minimum target of JDK 17 (or account for vendor-specific backports without assuming them).
- Startup flags and filter-installation APIs must be verified against the **target JDK**, not just the development machine's build JDK. When running apps/frameworks across multiple JVMs, test both with no default filter and with operator-supplied preconfigured filters/factories.

### Check the Actual Runtime Version

```bash
java -version
javac -version
```

Do not check `java -version` in one terminal and assume containers, services, IDEs, or deployment servers run the exact same JVM. Track the version and vendor of the runtime actually executing deserialization, and inspect how `jdk.serialFilter` / `jdk.serialFilterFactory` are passed via startup arguments, system/security properties, or startup APIs.

## 10. Deploying Filters in Large Applications

A viable policy typically includes layered safeguards:

1. **Eliminate Java native serialization** at untrusted payload boundaries wherever possible; use schema-validated formats.
2. **Inventory deserialization points:** direct `ObjectInputStream` calls and libraries/frameworks that may use it under the hood.
3. **Define per-payload-type allowlists:** permit only necessary business classes and dependencies, avoiding broad package wildcards.
4. **Bound resources:** depth, references, array length, stream bytes; add transport-layer limits, timeouts, and concurrency caps.
5. **Apply policies early:** global at startup, per-stream before `readObject()`, factory before the first ObjectInputStream is constructed.
6. **Test composition:** verify JVM and stream filters do not accidentally replace or widen each other; test valid payloads, unknown classes, huge arrays, deep graphs, and EOF/corruption.
7. **Handle errors deliberately:** when `InvalidClassException` or `IOException` occurs, close the stream and reject the input; never retry with a broader filter to "force compatibility."
8. **Logging/monitoring:** record blocked classes or limit triggers safely, without logging secrets or entire raw serialization bytes.
9. **Control version drift:** in build/deploy pipelines, track changed classes, whether dependency updates introduce new legitimate classes, and whether policies remain accurate.
10. **Threat modeling and review:** filters have limits and do not replace authorization, authentication, memory caps, or eliminating gadget deserialization.

In multi-team applications sharing one JVM, `setSerialFilter` or `setSerialFilterFactory` are **process-wide** resources: individual libraries cannot arbitrarily set their own values a second time. Preferably, the bootstrap owner selects a unified composition strategy and exposes configuration hooks to modules.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Setting a filter on an ObjectInputStream after already deserializing | Dangerous classes may have already run before protection | Set before the first `readObject()` call |
| Assuming `UNDECIDED` equals reject | Unmatched classes can still be read | Use an allowlist with an explicit reject rule for the rest |
| Configuring `jdk.serialFilter` while a stream-specific filter replaces it | Baseline thresholds stop applying under the default factory | Use a composing factory and test the effective filter |
| Treating `jdk.serialFilterFactory` as a pattern string | Fails to load factory | Supply the class name implementing `BinaryOperator<ObjectInputFilter>` |
| Calling `setSerialFilterFactory` after an ObjectInputStream was created | May throw `IllegalStateException` | Configure during bootstrap |
| Using `System.setProperty` after Config initialization | Appears to update running policy while having no effect | Use startup properties or bootstrap APIs at the right time |
| Copying JDK 17 code onto JDK 8 | Missing import/API errors | Check target JDK/vendor and backport differences |
| Allowing the DTO while forgetting valid arrays/nested/collections | `InvalidClassException` on valid inputs | Test the full graph and edge cases |
| Opening `java.base/*` broadly without review | Exposes more classes than needed | Restrict classes/modules per trust model |
| Setting only `maxarray` thinking total RAM is bounded | Many objects/streams or non-array structures bypass it | Combine maxrefs/maxdepth/maxbytes and external quotas |
| Catching `InvalidClassException` and re-deserializing unfiltered | Destroys protection barrier | Reject payload, alert, and close stream |
| Believing filters replace input authentication | Gadgets and invalid business data can still slip through | Avoid untrusted native deserialization; validate structure and source |

## 12. Self-Check Questions

**1. When should you choose a stream-specific filter?**  
When you know the exact set of valid classes for a specific input or data kind; create `ObjectInputStream`, apply the filter before reading, and verify interaction with JVM-wide policies.

**2. If you want to protect every ObjectInputStream creation point in the JVM without editing each call site, what do you use?**  
You can configure `jdk.serialFilter` at startup. However, verify its interaction with application per-stream filters/factories; never assume a global filter is "unconditionally enforced" if a factory allows replacement.

**3. Why isn't the pattern `com.example.**` necessarily a strict allowlist?**  
Unmatched classes can receive `UNDECIDED`. If deny-by-default is required, append an explicit reject pattern (such as `!*` at the end) and test it.

**4. Does `maxarray` prevent all huge collections?**  
No. It caps checked array lengths, not directly the size of arbitrary collections or total RAM across multiple streams.

**5. Can `setSerialFilterFactory` be called on standard JDK 11 just like JDK 17?**  
No: the context-specific factory API was added in JDK 17. On older runtimes, use capabilities supported by the target JDK or upgrade when the design requires a factory.

**Key takeaway:** Stream-specific filters restrict exact classes and data scale for **one ObjectInputStream**; `jdk.serialFilter` sets JVM-wide policy; since JDK 17, `jdk.serialFilterFactory` and `setSerialFilterFactory` control how they are chosen/combined. Understanding `ALLOWED/REJECTED/UNDECIDED`, when filters are installed, factory mechanics, and JDK version dependencies is mandatory whenever Java serialization is used in security-sensitive systems.
