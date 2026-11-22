# Per-Stream Filters, JVM Configuration, and JDK Version Dependencies in Java Serialization

When calling `ObjectInputStream.readObject()`, an application feeds a byte stream into **Java deserialization**. A malicious stream can trigger instantiation of unexpected classes or deeply nested, massive object graphs that exhaust resources. **`ObjectInputFilter`** (the serialization filter) lets the application inspect class names and graph metrics during reading, returning **`ALLOWED`**, **`REJECTED`**, or **`UNDECIDED`**.

There are three configuration layers that are easily confused:

1. **Stream-specific filter:** configured on **one** `ObjectInputStream`, e.g. `input.setObjectInputFilter(filter)`.
2. **JVM-wide/static filter:** configured via `-Djdk.serialFilter=...` or `ObjectInputFilter.Config.setSerialFilter(...)`, applied at the JVM level per the filter selection mechanism.
3. **JVM-wide filter factory (since JDK 17):** selects or combines filters for **each stream** when `ObjectInputStream` is constructed and when a per-stream filter is requested; configured via `jdk.serialFilterFactory` or `setSerialFilterFactory`.

Never assume simply enabling any filter makes deserializing untrusted data safe. Filters are an **additional defense layer**. The safer choice remains avoiding native Java deserialization on untrusted data altogether, preferring schema-validated, authenticated, resource-bounded formats instead.

## 1. Core APIs and Risks to Bound

Relevant types belong to `java.io`:

| API | Role |
| --- | --- |
| `ObjectInputStream` | Reads objects from a Java serialization stream |
| `ObjectInputFilter` | Interface evaluating objects/classes and graph metrics during deserialization |
| `ObjectInputFilter.FilterInfo` | Current context: `serialClass()`, `arrayLength()`, `depth()`, `references()`, `streamBytes()` |
| `ObjectInputFilter.Status` | Three decisions: `ALLOWED`, `REJECTED`, `UNDECIDED` |
| `ObjectInputFilter.Config` | Creates filters from pattern strings; gets/sets JVM-wide static filters and filter factories |
| `ObjectInputStream.setObjectInputFilter(...)` | Requests applying a specific filter to a stream |
| `ObjectInputStream.getObjectInputFilter()` | Inspects the effective filter active on the stream per actual configuration |

A filter controls **which class types can be constructed and resource metrics**. It is not a business-value validator; nor does it authenticate sender identity, guarantee a constructed object holds valid state, or turn serialization data into a safe sandbox.

A payload can still be dangerous because an allowed class has custom `readObject()`/`readResolve()` hooks, an overly deep graph, excessive reference chains, or invalid domain data. Therefore, combine **use-case class allowlists**, **graph limits**, **byte/CPU limits**, and **post-read data validation**.

## 2. Lifecycle of a Stream with a Filter

Typical flow:

```text
Trusted or controlled byte source
          |
          v
new ObjectInputStream(inputBytes)
          |  (JVM-wide filter factory selects initial filter)
          v
setObjectInputFilter(streamPolicy)
          |  (filter factory determines effective filter)
          v
readObject()
          |  filter checks class / array / depth / refs / streamBytes
          +--- REJECTED  --> read operation fails
          +--- ALLOWED   --> continue deserialization flow
          +--- UNDECIDED --> permission not confirmed; handle per composition policy
          v
Verify types, business validity, close stream
```

In JDK 17, `ObjectInputStream` is constructed with an initial filter supplied by the factory. When `setObjectInputFilter()` is called, **the factory again determines the final filter** from the current filter and the newly requested filter. Thus, calling this method must not be assumed to mean "only the passed filter remains active" or "automatically merged with global" in every application: **actual behavior depends on the active factory**.

Important caveats:

- The filter may be invoked **zero or many times**, depending on stream contents and processing steps. Certain specially encoded values, such as `String` and primitives in particular forms, **do not necessarily trigger class-check callbacks per value**.
- `FilterInfo.serialClass()` may be `null` when a check only inspects graph/resource limits, so never dereference it blindly.
- When encountering an array, the filter may be invoked with the array class and receive `arrayLength()`. Pattern filters match an array's **element type**, rather than simply matching `[Ljava.lang.String;`.
- `arrayLength()` can be `-1` when not checking an array; do not compare it against sizes of arbitrary collections.
- Filters evaluate **before or during graph construction**; they do not guarantee rejecting an object before any side effects of other deserialization steps happen. Never use them as a substitute for source verification.

## 3. Per-Stream Filters: Isolating Policy Per Stream

A service may expose multiple inputs. For example, one stream should accept only `InvoiceDTO`, while another accepts `CacheSnapshot`. Using a single shared class list easily grants broader deserialization privileges than necessary.

On JDK 9+ and JDK 17, you can build a filter from a pattern and attach it to `ObjectInputStream`:

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

This is an **illustrative snippet** without defining `source` or `com.example.dto` classes; not a standalone compilable program. If your application uses `List`, `Map`, arrays, or internal classes, test the policy against **the entire valid object graph** instead of assuming the pattern above automatically fits.

**Setting the filter before the first read** is essential practice. With standard APIs, never read part of an object before deciding to install a filter. If a framework or library owns the `ObjectInputStream`, calling `setObjectInputFilter()` may be disallowed or too late; coordinate configuration at stream creation time.

### When Should You Use a Custom Filter Instead of a Pattern?

When you need logic beyond class names, write a lambda against `ObjectInputFilter.FilterInfo`:

```java
// Illustrative in a program importing java.io.ObjectInputFilter.
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

This is **illustrative**: `ExampleDTO` is a hypothetical application class, not a standalone file. This filter permits only `ExampleDTO` on callbacks with a concrete class: if `ExampleDTO` contains fields of other classes/arrays needing deserialization, the filter rejects them. In real systems, account for every valid type without overlooking primitive arrays, collections, proxies, nested classes, or helper objects.

## 4. Three Outcomes: ALLOWED, REJECTED, UNDECIDED

| Result | Meaning |
| --- | --- |
| `ALLOWED` | Current check passes this filter policy; continue deserialization |
| `REJECTED` | Rejected; deserialization fails, typically throwing `InvalidClassException` |
| `UNDECIDED` | Filter makes no decision for this check; **not equivalent to ALLOWED under an allowlist** |

With `ObjectInputFilter.Config.createFilter(pattern)`, the runtime checks **resource limits first**, then evaluates class patterns **left to right**. The first matching pattern determines `ALLOWED`/`REJECTED`; if none match and no threshold is exceeded, the result is `UNDECIDED`.

If the effective filter returns `UNDECIDED` for a class and nothing else rejects it, reading can proceed. Thus, **listing allowed class names without adding a reject-rest rule does not necessarily create a "deny by default" allowlist**.

A common pattern ends with `!*`:

```text
com.example.api.**;java.base/java.util.*;!*
```

This accepts classes matching the first two patterns, then rejects remaining classes during class checks. Still, avoid opening large packages when the app needs only a few concrete DTOs; every class in an allowed package/module enters your trust boundary.

JDK 17 provides `ObjectInputFilter.merge(...)` to combine filters and `ObjectInputFilter.rejectUndecidedClass(...)` to reject undecided outcomes on class checks. Usage must be evaluated per system; never assume "merge" always equals concatenating patterns or intersecting two allowlists.

## 5. JVM-Wide Configuration via jdk.serialFilter

If an application or library constructs `ObjectInputStream` across many hard-to-edit call sites, you can configure a static filter **at JVM startup**:

```bash
java '-Djdk.serialFilter=maxdepth=12;maxrefs=5000;maxbytes=10485760;maxarray=100000;com.example.dto.**;!*' com.example.Main
```

This is an **illustrative command**: `com.example.Main` and the DTO package must exist in the app. On specific shells, argument quoting differs; ensure **the entire pattern string containing `;` is passed as a single JVM option**, since `;` can act as a command separator in shells.

Baseline thresholds:

| Pattern | Meaning |
| --- | --- |
| `maxdepth=12` | Caps graph depth during deserialization |
| `maxrefs=5000` | Caps tracked reference count |
| `maxbytes=10485760` | Caps tracked bytes in the serialization stream |
| `maxarray=100000` | Caps single array length, **not sizes of all collections** |
| `com.example.dto.**` | Allows classes in the package and matching subpackages |
| `java.base/java.util.*` | Allows classes directly in package `java.util` of module `java.base` |
| `!*` | Rejects remaining classes when checked by the filter |

The static filter is configured via the **system property `jdk.serialFilter`**; when absent, the JVM falls back to the **security property of the same name** in security configuration. The system property takes precedence over the security property according to `ObjectInputFilter.Config` initialization order.

It can also be set via API **if the static filter has not yet been set/configured**:

```java
// Illustrative for application bootstrap on Java 17.
ObjectInputFilter global = ObjectInputFilter.Config.createFilter(
        "maxdepth=12;maxrefs=5000;maxbytes=10485760;maxarray=100000");
ObjectInputFilter.Config.setSerialFilter(global);
```

`setSerialFilter()` is a **one-time JVM-level configuration**, not a per-request toggle. If a filter is already set, it can throw `IllegalStateException`; if a Security Manager/permissions on older runtimes block it, a security exception can be thrown.

**Crucial point:** Calling `System.setProperty("jdk.serialFilter", "...")` after `ObjectInputFilter.Config` has initialized **does not guarantee the new static filter takes effect**. Use JVM startup options or bootstrap APIs at the proper time.

### JVM-Wide Configuration Does Not Automatically Mean "Always Applied Alongside Per-Stream"

In JDK 17, a **filter factory** selects the filter for each stream. The built-in factory uses the global filter when a stream is created, yet when code calls `setObjectInputFilter(streamPolicy)`, the built-in factory may **replace the global filter with the per-stream filter** instead of intersecting both policies automatically. If JVM-wide protections must always remain active, do not rely merely on having set `jdk.serialFilter`; combine filters explicitly in a suitable factory.

## 6. JDK 17: Context-Specific Filter Factories (JEP 415)

Starting in JDK 17, `ObjectInputFilter.Config` provides a JVM-level filter factory to select **one effective filter per `ObjectInputStream`**. It can consider the JVM-wide filter, any stream-requested filter, and calling context (module, ThreadLocal, call stack, service owner, etc.).

Setting via API:

```java
// Sketch illustrating only how to combine two filters.
// Must be set at bootstrap, before any ObjectInputStream is created.
ObjectInputFilter.Config.setSerialFilterFactory((current, requested) -> {
    if (current == null) return requested;
    if (requested == null) return current;
    return ObjectInputFilter.merge(current, requested);
});
```

This is an **illustrative JVM-wide configuration snippet**, not a complete production policy. `current` is the stream's current filter (or `null` at construction), and `requested` is the filter passed to the constructor or `setObjectInputFilter`. When `current` is already non-null, a factory must not return `null` and silently disable an active filter.

In production, assign clear ownership for JVM-wide config, test `merge`/`UNDECIDED`/`REJECTED` semantics, benchmark overhead, and verify per-stream policies neither accidentally **broaden** permissions nor **reject** types legitimately needed by frameworks.

A factory class can also be configured via startup property:

```bash
java -Djdk.serialFilterFactory=com.example.security.MyFilterFactory com.example.Main
```

This factory class must be application-provided, **`public`**, have a public no-arg constructor, implement `BinaryOperator<ObjectInputFilter>`, and be loadable by the appropriate class loader. The `jdk.serialFilterFactory` property specifies a **factory class name**, not a pattern string—distinct from `jdk.serialFilter`.

Per Java 17, factory configuration can be set **only once** and before any `ObjectInputStream` is created. Configuration via system/security property takes precedence and cannot be overridden later via API. Calling `System.setProperty("jdk.serialFilterFactory", "...")` after Config initializes **does not activate a new factory**.

### When Is a Factory Needed Instead of a Static Filter?

A modular application may receive distinct payload families: billing uses only `PaymentDTO`, caching uses `CacheSnapshot`, and internal tooling uses `MigrationRecord`. A single JVM-wide allowlist broad enough for all of them widens the attack surface. A context-specific factory can combine **mandatory baseline limits** with **input-specific allowlists**. However, the context source must be trustworthy—never take arbitrary class names from the sender's payload or request to self-authorize classes.

## 7. Complete Java 17 Example: Per-Stream Allowlist Accepting One Class and Rejecting Another

This program constructs two serialization streams in memory. It reads no network data, making it safe for demonstrating filter checks. One allowed class is `AllowedMessage`; the other is `BlockedMessage`. Each read opens **a separate `ObjectInputStream`** and installs the same filter **before `readObject()`**.

Create **`SerialFilterDemo.java`**:

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

Compile and run on **JDK 17**, with standard JVM configuration and no custom factory installed:

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

1. `encode` uses `ObjectOutputStream` to serialize a valid instance into an in-memory byte array; it does not read anything back yet.
2. `decode` creates an `ObjectInputStream` and sets the filter via `setObjectInputFilter` before reading. The pattern caps depth/references/bytes/array length and permits only the binary class name `SerialFilterDemo$AllowedMessage`.
3. The trailing `!*` rejects remaining classes when checked. `AllowedMessage` is in the allowed set, so `readObject()` returns an object with `code=42`.
4. `BlockedMessage` fails to match the allowlist, so deserialization returns `REJECTED`, typically surfaced as `InvalidClassException`. The program catches that exact exception type and prints only the exception name, avoiding dependence on messages or stack traces that may vary across JVMs.
5. Because the class stores only a primitive `int` field, the example needs no additional allowlist entries for nested classes like `ArrayList` or other DTO types. If you add serializable reference fields, update the filter and retest the full object graph.

This is a minimal demonstration of filtering mechanics, **not a production-ready template filter for real data**. In environments where an application or framework configures a JVM-wide filter/factory, the effective filter can differ and must be verified before assuming the exact demo outcome.

## 8. Pattern Syntax and Configuration Pitfalls

`ObjectInputFilter.Config.createFilter` pattern syntax is a **semicolon-separated** list of components. For class patterns:

| Pattern | Meaning |
| --- | --- |
| `com.example.Foo` | Exact fully qualified class name |
| `com.example.*` | Classes directly inside package `com.example` |
| `com.example.**` | Classes inside `com.example` and all subpackages |
| `com.example.Foo*` | Classes whose names start with the given prefix |
| `java.base/java.util.*` | Classes in module `java.base` and directly in package `java.util` |
| `!com.example.Dangerous` | Rejects this specific class |
| `!*` | Rejects all remaining matchable classes when placed at the end |

Resource limits accept `maxdepth`, `maxrefs`, `maxbytes`, and `maxarray`. If a limit appears multiple times, the **last** value takes effect. Whitespace is significant in patterns and can prevent names from matching; avoid stray spaces when configuring via properties.

Common pitfalls:

- **Pattern order matters.** Putting `!*` before allowlist entries leaves subsequent classes no chance to be permitted.
- **Binary names of nested classes** use `$` (e.g., `SerialFilterDemo$AllowedMessage`), not the source-level name `SerialFilterDemo.AllowedMessage`.
- **Class patterns differ from content validation.** Allowing `java.util.ArrayList` does not stop a list from carrying invalid domain data or huge element counts when limits do not cover that angle.
- **`streamBytes` limit is not a process-wide budget.** Each `ObjectInputStream` tracks its own counter; many concurrent streams can still consume heavy resources.
- **`UNDECIDED` does not provide deny-by-default protection.** If you intend to block unknown classes, configure an explicit reject rule.
- **Avoid "allow all of `java.base`" patterns out of habit.** That exposes far more classes than actually needed.
- **Never read payload data before setting the filter.** Establish the policy prior to the first operation needing protection.

## 9. JDK Version Dependencies: JEP 290 and JEP 415

| JDK Release | Capabilities and Caveats |
| --- | --- |
| Older Java 6/7/8 before serialization filtering patches | Cannot assume APIs like JDK 9+ exist |
| Certain JDK 6/7/8 updates from the Jan 2017 Critical Patch Update | Backported filtering; legacy API may live under `sun.misc.ObjectInputFilter`, differing from JDK 9+ imports |
| JDK 9 (JEP 290) | Standard `java.io.ObjectInputFilter`, per-stream and JVM-wide filters; class/graph limits |
| JDK 11 | Uses `java.io.ObjectInputFilter`, but do not assume JDK 17 filter factory APIs exist |
| JDK 17 (JEP 415) | Adds **context-specific filter factories**, `Config.setSerialFilterFactory`, and `jdk.serialFilterFactory`; includes helper APIs for policy composition |
| Newer JDKs | Check API docs, release notes, flags, and vendor-specific behavior; do not blindly assume identical behavior to JDK 17 |

Key milestones:

- **JEP 290 – Filter Incoming Serialization Data:** introduced in Java 9; backported to updates like JDK 8u121, 7u131, 6u141. Never assume source importing `java.io.ObjectInputFilter` compiles verbatim on older JDKs: backport packages/APIs differ.
- **JEP 415 – Context-Specific Deserialization Filters:** introduced in JDK 17. Any program requiring `setSerialFilterFactory` should declare and test a minimum JDK level of 17 (unless accounting for explicit vendor backports rather than assuming them).
- Startup flags and filter configuration APIs must be verified on the **target JDK**, not just the developer's build JDK. When deploying across multiple JVMs, test both with no default filter and in environments pre-configuring global filters/factories.

### Checking the Actual Runtime Version

```bash
java -version
javac -version
```

Do not check `java -version` in one terminal and assume your container, service, IDE, or deployment host uses that exact JVM. Track the exact runtime version and vendor running deserialization, and verify how `jdk.serialFilter` / `jdk.serialFilterFactory` are supplied via startup flags, system/security properties, or bootstrap APIs.

## 10. Deploying Filters in Large Applications

A viable policy usually layers additional safeguards:

1. **Eliminate native Java serialization** at untrusted ingress points whenever possible; use schema-validated formats instead.
2. **Inventory deserialization sites:** direct `ObjectInputStream` calls as well as libraries/frameworks using it under the hood.
3. **Define per-payload allowlists:** permit only exact domain classes and necessary dependencies, avoiding broad package wildcards.
4. **Cap resources:** depth, references, array length, stream bytes; add transport caps, processing deadlines, and concurrency limits.
5. **Apply policies early:** global at startup, per-stream before `readObject()`, factory before creating the first `ObjectInputStream`.
6. **Test composition:** verify JVM and stream filters do not accidentally overwrite or relax each other; test valid payloads, unknown classes, large arrays, deep graphs, and EOF/corruption.
7. **Handle errors deliberately:** when `InvalidClassException` or `IOException` occurs, close the stream and reject the input; never retry with a looser filter "for compatibility."
8. **Logging/monitoring:** record blocked classes or limit triggers safely without logging secrets or raw serialization bytes.
9. **Control version drift:** during build/deploy pipelines, check which classes changed, whether dependency updates introduced new legitimate classes, and whether policies remain accurate.
10. **Threat modeling and review:** filters have limits and do not replace authorization, authentication, memory caps, or avoiding gadget-prone classes.

In multi-team applications sharing one JVM, `setSerialFilter` and `setSerialFilterFactory` are **process-wide** resources: individual libraries cannot arbitrarily set them again. Have the bootstrap owner define a unified composition strategy and expose configuration hooks for modules.

## 11. Common Mistakes and How to Fix Them

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Setting a filter on an `ObjectInputStream` after already deserializing | Dangerous classes may already have been processed before protection | Set before the first `readObject()` call |
| Assuming `UNDECIDED` equals rejection | Unmatched classes may still be read | Use an allowlist with an explicit reject-rest rule |
| Configuring `jdk.serialFilter` while a per-stream filter replaces it | Baseline thresholds drop under the default factory | Use a composing factory and test the effective filter |
| Treating `jdk.serialFilterFactory` as a pattern string | Fails to load the factory | Supply the class name implementing `BinaryOperator<ObjectInputFilter>` |
| Calling `setSerialFilterFactory` after an `ObjectInputStream` was created | May throw `IllegalStateException` | Configure during bootstrap |
| Calling `System.setProperty` after `Config` initialized | Appears to change policy at runtime yet has no effect | Use startup properties or timely bootstrap APIs |
| Copying JDK 17 code onto JDK 8 | Import/API errors or missing methods | Check target JDK/vendor and backport differences |
| Allowing only the DTO while forgetting valid arrays/nested/collection types | `InvalidClassException` on legitimate inputs | Test the full graph and edge cases |
| Opening `java.base/*` blindly | Exposes far more classes than needed | Restrict classes/modules per threat model |
| Setting only `maxarray` thinking total RAM is bounded | Multiple objects/streams or non-array structures still exhaust RAM | Combine maxrefs/maxdepth/maxbytes and outer stream caps |
| Catching `InvalidClassException` and retrying without a filter | Drops the protective barrier | Reject payload, alert, and close stream |
| Believing a filter replaces input authentication | Gadgets and invalid domain data can still succeed | Avoid untrusted native deserialization; validate structure and origin |

## 12. Self-Check Questions

**1. When should you choose a stream-specific filter?**  
When you know the exact set of valid classes for a particular input or data type; create `ObjectInputStream`, apply the filter before reading, and verify interaction with JVM-wide policies.

**2. If you want to protect every `ObjectInputStream` creation site in a JVM without editing each call site, what can you use?**  
You can configure `jdk.serialFilter` at startup. Still, verify how it composes with application per-stream filters/factories; never assume a global filter stays mandatory if the factory allows replacing it.

**3. Why is the pattern `com.example.**` not necessarily a strict allowlist?**  
Unmatched classes can evaluate to `UNDECIDED`. When deny-by-default is required, append an explicit reject pattern (such as `!*` at the end) and test it.

**4. Does `maxarray` block every huge collection?**  
No. It caps lengths of arrays checked by the filter, not directly the size of every collection or aggregate memory across concurrent streams.

**5. Can `setSerialFilterFactory` be called on standard JDK 11 just like JDK 17?**  
No: the context-specific factory API was introduced in JDK 17. On older runtimes, use features supported by your target JDK or upgrade when the design requires a factory.

**Takeaway:** Per-stream filters constrain classes and data scale for **one `ObjectInputStream`**; `jdk.serialFilter` sets JVM-wide policy; since JDK 17, `jdk.serialFilterFactory` and `setSerialFilterFactory` govern how they are selected and combined. Mastering `ALLOWED/REJECTED/UNDECIDED`, filter timing, factory mechanics, and JDK version differences is essential whenever Java serialization is used in security-sensitive systems.
