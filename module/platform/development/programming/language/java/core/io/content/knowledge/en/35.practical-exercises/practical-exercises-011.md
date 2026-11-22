# Java I/O Practical Exercise: Serialization and Configuring `ObjectInputFilter`

## Objectives

After this exercise, you will be able to: (1) serialize Java objects into a byte stream and restore them; (2) understand the roles of `Serializable`, `serialVersionUID`, and `transient`; (3) configure `ObjectInputFilter` to restrict allowed object types and object-graph size during deserialization; (4) distinguish valid streams, filter-rejected streams, and corrupted streams; (5) recognize the security limits of Java serialization.

**Context:** This is a practical exercise in Java Core I/O. It uses JDK 17 or later, requiring no frameworks or libraries outside the JDK.

## 1. Mechanics to Understand Before Running

**Serialization** converts the eligible state of an object into a byte representation using `ObjectOutputStream`. **Deserialization** uses `ObjectInputStream` to read that byte stream and reconstruct the object graph. A single stream can contain multiple objects; shared references and certain cyclic graphs are managed by the serialization protocol.

Processing flow in the example:

~~~text
Account("Lan", token="SECRET")
  -> ObjectOutputStream.writeObject(...)
  -> byte[] containing Java serialization stream
  -> ByteArrayInputStream
  -> ObjectInputStream + ObjectInputFilter
  -> readObject()
      -> ALLOWED  : Account is read, transient token becomes null
      -> REJECTED : class not in allowlist throws InvalidClassException
~~~

Key points to remember:

- A custom class must implement `Serializable` to be written by the default mechanism; this is a marker interface with no methods to override. Objects held in non-transient fields must also be serializable if reached during traversal; otherwise `NotSerializableException` may be thrown.
- `ObjectOutputStream` writes a Java-specific binary format. `ObjectInputStream` reads that format back; it must not be treated as JSON, UTF-8 text, or a cross-language data-exchange format.
- `serialVersionUID` identifies the class version for compatibility checks on read. Declaring a stable value explicitly helps govern class evolution, yet **does not** guarantee every schema change is compatible.
- Instance fields marked `transient` are not serialized by the default mechanism; when read back, they receive the type's default value (such as `null` for `String`). `static` fields likewise do not belong to serialized instance state.
- `ObjectInputFilter` is invoked **during deserialization** to inspect the class, array length, graph depth, reference count, and bytes read. It is not applied during `writeObject` alone and is neither encryption nor data authentication.

## 2. Complete Program: Accepting the Right Class, Rejecting Others

Create a single file named **SerializationFilterDemo.java** with the contents below. Both data classes are declared nested inside the main class so the whole exercise runs from one file.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public class SerializationFilterDemo {

    private static final class Account implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String owner;
        private final transient String sessionToken;

        Account(String owner, String sessionToken) {
            this.owner = owner;
            this.sessionToken = sessionToken;
        }

        @Override
        public String toString() {
            return "Account[owner=" + owner
                    + ", sessionToken=" + sessionToken + "]";
        }
    }

    private static final class Unexpected implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String label;

        Unexpected(String label) {
            this.label = label;
        }
    }

    private static byte[] serialize(Serializable value) throws IOException {
        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(value);
        }
        return buffer.toByteArray();
    }

    private static Object deserializeWithFilter(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {

            String pattern = "maxdepth=5;maxrefs=20;maxbytes=4096;"
                    + "maxarray=100;SerializationFilterDemo$Account;!*";
            ObjectInputFilter filter =
                    ObjectInputFilter.Config.createFilter(pattern);

            // Set the filter before the first readObject() call.
            in.setObjectInputFilter(filter);
            return in.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] acceptedBytes =
                serialize(new Account("Lan", "SECRET"));
        Object accepted = deserializeWithFilter(acceptedBytes);
        System.out.println("Accepted: " + accepted);

        byte[] rejectedBytes =
                serialize(new Unexpected("not allowed"));
        try {
            deserializeWithFilter(rejectedBytes);
            System.out.println("Unexpected object accepted");
        } catch (InvalidClassException rejected) {
            System.out.println("Rejected by ObjectInputFilter");
        }
    }
}
~~~

Compile and run from the directory containing the file:

~~~bash
javac SerializationFilterDemo.java
java SerializationFilterDemo
~~~

Expected output on default JDK 17+:

~~~text
Accepted: Account[owner=Lan, sessionToken=null]
Rejected by ObjectInputFilter
~~~

**Explaining the output:**

1. `serialize(...)` creates a `ByteArrayOutputStream`, wraps it with `ObjectOutputStream`, and calls `writeObject(value)`. The resulting `byte[]` is real serialized binary data, not decoded and not a character string.
2. `deserializeWithFilter(...)` creates an `ObjectInputStream` and attaches the filter via `setObjectInputFilter(...)` **before** calling `readObject()`.
3. The `Account` class is on the allowlist, so it is reconstructed. `owner` has the value `"Lan"`; `sessionToken` is `transient`, so it receives `null` even though it held `"SECRET"` before writing.
4. The `Unexpected` stream still serializes successfully because `Unexpected` implements `Serializable`; during deserialization, the filter sees `Unexpected`, the trailing `!*` rule rejects it, and `ObjectInputStream` throws `InvalidClassException`.
5. The code catches `InvalidClassException` specifically for filter rejection. In real applications, `IOException`, `ClassNotFoundException`, and other data errors must be handled separately by context; never treat every `readObject` failure as a filter rejection.

**Note on nested classes:** the binary name of `Account` is `SerializationFilterDemo$Account`, not `SerializationFilterDemo.Account`. Therefore the pattern string must use `$`. If `Account` is moved to package `com.example.io` as a top-level class, the pattern must use the exact full name `com.example.io.Account`.

## 3. Step-by-Step Analysis of `ObjectInputFilter`

`ObjectInputFilter` is an interface provided by the JDK to participate in decisions when `ObjectInputStream` creates/reads objects from a stream. It inspects details of the object being read via `FilterInfo`:

| `FilterInfo` Property | Meaning | How to Use |
| --- | --- | --- |
| `serialClass()` | Class being checked; sometimes `null` on checks not tied to a new class | Apply class rules only when non-null |
| `arrayLength()` | Array length if checking an array; typically `-1` when not an array | Block oversized arrays |
| `depth()` | Current depth of the object graph | Limit overly deep nesting |
| `references()` | Number of references processed by the stream so far | Limit object/reference counts |
| `streamBytes()` | Bytes consumed at the moment of the check | Limit volume read |

The filter returns one of three statuses:

- **ALLOWED**: permits the inspected object/class to proceed.
- **REJECTED**: denies it; deserialization fails (typically with `InvalidClassException`).
- **UNDECIDED**: filter has not decided. This value **does not automatically mean forbidden**; if other filters or the effective policy do not reject it, reading can still continue.

Pattern configuration in the program:

~~~text
maxdepth=5;maxrefs=20;maxbytes=4096;maxarray=100;SerializationFilterDemo$Account;!*
~~~

Four resource bounds are checked alongside the class rules:

| Component | Role |
| --- | --- |
| `maxdepth=5` | Rejects when depth exceeds 5 |
| `maxrefs=20` | Rejects when reference count exceeds 20 |
| `maxbytes=4096` | Rejects when bytes read exceed 4,096 |
| `maxarray=100` | Rejects when an array's length exceeds 100 |
| `SerializationFilterDemo$Account` | Allows the `Account` class in the program |
| `!*` | Rejects all remaining classes matching wildcard `*` |

**Class rule order matters.** For a given class, the first matching pattern decides. If `!*` is placed first, `Account` is rejected too. The `maxdepth`/`maxrefs`/`maxbytes`/`maxarray` limits are checked independently of class-rule order. Whitespace in patterns is significant; do not arbitrarily insert spaces around semicolons or class names.

In this example, a narrow allowlist fits because the `Account` graph contains only a `String` field and simple values. Filter callbacks are not invoked for primitives or `String` values encoded directly by the serialization protocol; therefore **do not assume a class allowlist alone governs all data of every type**. When models include `List`, `Map`, arrays, or nested classes, verify every class that actually appears in the stream, including internal types and allocatable resources.

## 4. Controlled Experiments

### 4.1. Observing the Effect of `transient`

In the program, change the values when constructing the object:

~~~java
serialize(new Account("Minh", "TOKEN-123"))
~~~

When re-run, the `Account` portion of stdout shows `owner=Minh` and `sessionToken=null`. `transient` omits **that field** from the stream under default serialization; it does not erase data residing elsewhere, and custom `writeObject` methods can alter what gets written. Never rely on `transient` as your sole protection for secrets.

### 4.2. Blocking `Account` Too via Class Policy

Change the pattern to:

~~~java
String pattern = "maxdepth=5;maxrefs=20;maxbytes=4096;"
        + "maxarray=100;!*";
~~~

Now even `Account` is rejected. In the current program, the first `deserializeWithFilter(acceptedBytes)` call throws `InvalidClassException` before reaching the `catch` block meant for `Unexpected`. To observe a friendly message, catch the exception for the first branch or restore the pattern after experimenting.

### 4.3. Testing Array Size Limits

Standalone example with a 101-element array:

~~~java
byte[] arrayBytes = serialize(new int[101]);
~~~

To test this array with the same `deserializeWithFilter(...)`, you could pass `arrayBytes`; `maxarray=100` blocks oversized arrays. However, because that method includes `!*`, arrays can also be blocked by class rules even below the limit. To test `maxarray` **on its own**, use an illustrative filter such as:

~~~java
ObjectInputFilter arrayFilter =
        ObjectInputFilter.Config.createFilter("maxarray=100;*");
~~~

Install `arrayFilter` on a new `ObjectInputStream` **before `readObject()`**, then read `int[100]` and `int[101]` streams. On default JDK 17, the 100-element array is accepted and the 101-element array is rejected. The `*` pattern permits every class, so **use it only in array-limit experiments**, never as a defense policy for untrusted input.

### 4.4. Changing Byte and Depth Thresholds

Lowering `maxbytes` from 4096 to a small value like 16 typically causes the `Account` stream in the example to be rejected before restoration finishes. However, the byte count at each callback depends on read timing; do not treat that threshold number as the exact length of the serialized byte array. Likewise, for a deeply nested graph, lowering `maxdepth` blocks deep reads. Never hardcode one demo threshold for all data models.

### 4.5. Distinguishing Failure Causes

| Symptom | Common Cause | How to Investigate |
| --- | --- | --- |
| `InvalidClassException` with filter status message | Filter rejected a class or limit | Check allowlist, limits, and rule order |
| `InvalidClassException` due to `serialVersionUID` | Writer and reader class versions incompatible | Check `serialVersionUID` and schema changes |
| `NotSerializableException` on write | An object in the graph is not serializable | Inspect relevant fields and types |
| `StreamCorruptedException` / `EOFException` on read | Malformed, missing, or truncated stream | Verify input is valid Java serialized bytes |
| `ClassNotFoundException` on read | Reader lacks a class named in the stream | Check classpath/modules and deployment |

An error can be wrapped by an exception at a caller layer. Do not classify failures by exception class name alone without checking the message, cause, and program state.

## 5. Two Ways to Configure `ObjectInputFilter`

### 5.1. Per `ObjectInputStream`: Best Fit for This Exercise

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=100;maxbytes=65536;maxarray=1000;"
                + "com.example.io.SafeMessage;!*");
try (ObjectInputStream in = new ObjectInputStream(inputStream)) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
~~~

The snippet above only illustrates the read path inside an application that already has `inputStream` and an actual `com.example.io.SafeMessage` class. It is **not a standalone program**. Specific patterns must be tailored to real object graphs. Set the filter before `readObject`, close the stream with `try-with-resources`, and verify the object's type after reading.

### 5.2. JVM-Wide Filter and Filter Factory

The JDK supports a JVM-wide filter via the `jdk.serialFilter` system property or corresponding security property; for instance, launching an app with broad limits:

~~~bash
java -Djdk.serialFilter=maxdepth=20;maxrefs=200;maxbytes=1048576 SerializationFilterDemo
~~~

**Shell warning:** `;` is often a special shell character (especially in PowerShell/Bash). Quote the entire JVM argument so the full value is passed intact:

~~~bash
java "-Djdk.serialFilter=maxdepth=20;maxrefs=200;maxbytes=1048576" SerializationFilterDemo
~~~

These configurations apply broadly, so evaluate their impact on every object stream in the application. Since JDK 17, a filter factory can combine the JVM-wide filter with per-stream filters; actual combination behavior depends on factory configuration. Do not assume `setObjectInputFilter` always completely overrides an installed JVM-wide policy. To analyze behavior, check documentation for your exact JDK and runtime configuration.

**Principle:** application policies must define allowlists and resource limits tailored to each data stream; JVM-wide policies are a supporting layer, not a replacement for specifying the expected data model at each input boundary.

## 6. When You Need a Java-Written Filter Instead of a Pattern

Patterns are convenient for class-name rules and basic limits. When contextual conditions are required, implement `ObjectInputFilter` directly. Here is an **illustrative snippet** for `SafeMessage` in package `com.example.io`:

~~~java
ObjectInputFilter customFilter = info -> {
    if (info.depth() > 10
            || info.references() > 100
            || info.streamBytes() > 65_536
            || info.arrayLength() > 1_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    while (type.isArray()) {
        type = type.getComponentType();
    }

    if (type == com.example.io.SafeMessage.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }
    return ObjectInputFilter.Status.REJECTED;
};
~~~

Here, `arrayLength() > 1_000` does not block `-1` (non-arrays). `serialClass() == null` can occur in callbacks used purely to update resource counters; returning `UNDECIDED` after checking bounds is appropriate in that branch. When `type` is non-null and not permitted, return `REJECTED` to leave no gaps in the allowlist.

This illustrates filtering logic and requires `com.example.io.SafeMessage` in your project. If a valid type holds supporting elements (such as collections, enums, arrays, or nested classes), build the complete allowlist from real stream inspection and resource limits; otherwise, valid data itself will be rejected.

## 7. Common Misconceptions and Mistakes

1. **Checking `instanceof` only after `readObject()`.** Too late for several risks: Java has already executed deserialization before the return-type check runs. Attach `ObjectInputFilter` before `readObject` to reject earlier within filter capabilities.
2. **Assuming `implements Serializable` implies safety.** That interface only marks an object eligible for serialization; it says nothing about trusted byte origin or valid content.
3. **Configuring a filter with `maxdepth` only and no class restrictions.** A sound policy governs types, array sizes, reference counts, and bytes; depending on the case, also enforce transport-level limits before creating `ObjectInputStream`.
4. **Assuming `UNDECIDED` means `REJECTED`.** In a pattern without a trailing deny rule, unmatched classes may still be read.
5. **Using wrong class names.** Nested classes use `$` in binary names; package and module names (when included in patterns) must be exact.
6. **Putting `!*` before the allowlist.** Filters evaluate patterns in order, so an early catch-all deny rule shadows all subsequent allow rules.
7. **Believing a filter guarantees absolute security.** Filters reduce attack surface, yet do not verify signatures, cannot block every side effect inside custom `readObject`/`readResolve`, and do not patch library bugs. Untrusted data remains risky even with a filter.
8. **Using serialization for long-term durable data storage.** Changing class names, `serialVersionUID`, fields, or the classpath can break compatibility. For long-lived data exchange, consider explicit schemas such as JSON or Protocol Buffers with validation, size limits, and proper authentication.
9. **Logging or exposing secrets inside objects.** Even though `transient` fields are not written by default, printing `toString()` in an application can leak live secrets. Print only non-sensitive demo values.

## 8. Self-Check Checklist and Follow-Up Questions

Re-run the program yourself, then confirm:

- The file is named `SerializationFilterDemo.java` and `javac` compiles cleanly on JDK 17+.
- `ObjectOutputStream` writes both `Account` and `Unexpected`.
- `Account` is restored when allowed by policy; `owner` remains `Lan` and `sessionToken` becomes `null`.
- `Unexpected` is rejected during `readObject()` under the policy with `Account` allowlisted and `!*`.
- Moving `!*` first blocks `Account` as well.
- You can explain `maxdepth`, `maxrefs`, `maxbytes`, `maxarray`, and the differences among `ALLOWED` / `REJECTED` / `UNDECIDED`.
- All untrusted-object reads in applications define proper policies, transport-layer input bounds, and dedicated error handling.

**Reflection questions:** (1) Why does casting to `Account` after `readObject` not substitute for `ObjectInputFilter`? (2) Why does a `transient` field become `null`, and when is custom serialization needed? (3) Which legitimate classes might a class-name filter miss if `Account` contains a `List` or arrays? (4) Why do `maxbytes` and `maxrefs` mitigate resource exhaustion yet fail to prove a stream is trustworthy?

## Official References

- Oracle JDK 17 API — `Serializable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Oracle JDK 17 API — `ObjectInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html
- Oracle JDK 17 API — `ObjectInputFilter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html
- Oracle JDK 17 API — `ObjectInputFilter.Config` and pattern syntax: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html
- OpenJDK JEP 290 — Filter Incoming Serialization Data: https://openjdk.org/jeps/290
- OpenJDK JEP 415 — Context-Specific Deserialization Filters: https://openjdk.org/jeps/415