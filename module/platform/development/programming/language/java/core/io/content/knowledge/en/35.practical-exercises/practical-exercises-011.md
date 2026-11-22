# Java I/O Practice: Serialization and `ObjectInputFilter` Configuration

## Objectives

After this exercise, you will be able to: (1) serialize Java objects into a byte stream and restore them; (2) understand the roles of `Serializable`, `serialVersionUID`, and `transient`; (3) configure `ObjectInputFilter` to restrict allowed object types and object-graph scale during deserialization; (4) distinguish valid streams, filter-rejected streams, and corrupted streams; and (5) recognize the security limitations of Java serialization.

**Context:** This is a practice exercise in Java Core I/O. It uses JDK 17 or newer, requiring no frameworks or libraries outside the JDK.

## 1. Mechanics to Understand Before Running

**Serialization** converts an object's eligible state into a byte representation using `ObjectOutputStream`. **Deserialization** uses `ObjectInputStream` to read that byte stream and reconstruct the object graph. A single stream can contain multiple objects; shared references and certain cyclic graphs are managed by the serialization protocol.

Processing flow in the example:

~~~text
Account("Lan", token="SECRET")
  -> ObjectOutputStream.writeObject(...)
  -> byte[] containing Java serialization stream
  -> ByteArrayInputStream
  -> ObjectInputStream + ObjectInputFilter
  -> readObject()
      -> ALLOWED  : Account is read, transient token becomes null
      -> REJECTED : classes not on allowlist trigger InvalidClassException
~~~

Key points to remember:

- A custom class must implement `Serializable` to be written via the default mechanism; it is a marker interface with no methods to override. Objects referenced by non-transient fields must also be serializable if traversed; otherwise `NotSerializableException` can occur.
- `ObjectOutputStream` writes a Java-specific binary format. `ObjectInputStream` reads this format back; it must not be treated as JSON, UTF-8 text, or a cross-language data exchange format.
- `serialVersionUID` identifies the class version for compatibility checks on read. Explicitly declaring a stable value helps manage class evolution, yet **does not** guarantee every schema change is compatible.
- Instance fields marked `transient` are skipped by default serialization; upon deserialization they take their type's default value (e.g., `null` for `String`). `static` fields are likewise excluded from serialized instance state.
- `ObjectInputFilter` is invoked **during deserialization** to evaluate the class, array length, graph depth, reference count, and bytes read. It is not applied during `writeObject` alone and is not an encryption or data-authentication tool.

## 2. Complete Program: Allowing the Right Class, Rejecting Others

Create a single file named **SerializationFilterDemo.java** with the contents below. Both data classes are nested inside the main class so the entire exercise runs from one file.

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

            // Configure the filter before the first readObject() call.
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

1. `serialize(...)` creates a `ByteArrayOutputStream`, wraps it with `ObjectOutputStream`, and calls `writeObject(value)`. The returned `byte[]` is real serialized binary data, undecoded and not a character string.
2. `deserializeWithFilter(...)` constructs `ObjectInputStream` and installs the filter via `setObjectInputFilter(...)` **before** calling `readObject()`.
3. `Account` is allowlisted and therefore reconstructed. `owner` is `"Lan"`; `sessionToken` is `transient`, so it becomes `null` even though it held `"SECRET"` before writing.
4. `Unexpected` still serializes cleanly because `Unexpected` implements `Serializable`; during deserialization, the filter encounters `Unexpected`, the trailing `!*` rule rejects it, and `ObjectInputStream` throws `InvalidClassException`.
5. The code catches `InvalidClassException` specifically for filter rejection. In real applications, `IOException`, `ClassNotFoundException`, and other data errors must be handled separately per context; never attribute every `readObject` failure to filtering.

**Note on nested classes:** `Account`'s binary name is `SerializationFilterDemo$Account`, not `SerializationFilterDemo.Account`. Thus the pattern string must use `$`. If moving `Account` to package `com.example.io` as a top-level class, the pattern must use its exact full name `com.example.io.Account`.

## 3. Step-by-Step Analysis of `ObjectInputFilter`

`ObjectInputFilter` is a JDK-provided interface that participates in decisions when `ObjectInputStream` creates/reads objects from a stream. It inspects metadata about the incoming object via `FilterInfo`:

| `FilterInfo` Property | Meaning | How to Use |
| --- | --- | --- |
| `serialClass()` | The class being checked; sometimes `null` on checks not tied to a new class | Make class-based decisions only when non-null |
| `arrayLength()` | Array length if checking an array; typically `-1` if not an array | Block oversized arrays |
| `depth()` | Current depth of the object graph | Limit overly deep nested graphs |
| `references()` | Number of references processed by the stream so far | Cap total object/reference count |
| `streamBytes()` | Number of bytes consumed so far at check time | Cap bytes read |

The filter returns one of three values:

- **ALLOWED**: permits the inspected object/class to proceed.
- **REJECTED**: rejects it; deserialization fails (typically as `InvalidClassException`).
- **UNDECIDED**: the filter has not decided. This value **does not implicitly mean reject**; if other filters or active policies do not reject it, reading may still proceed.

Pattern used in the program:

~~~text
maxdepth=5;maxrefs=20;maxbytes=4096;maxarray=100;SerializationFilterDemo$Account;!*
~~~

Four limits are evaluated alongside the class rules:

| Component | Role |
| --- | --- |
| `maxdepth=5` | Reject when depth exceeds 5 |
| `maxrefs=20` | Reject when reference count exceeds 20 |
| `maxbytes=4096` | Reject when bytes read exceed 4,096 |
| `maxarray=100` | Reject when an array's length exceeds 100 |
| `SerializationFilterDemo$Account` | Allow the program's `Account` class |
| `!*` | Reject all remaining classes matching wildcard `*` |

**Class rule order matters.** For a given class, the first matching pattern decides. Putting `!*` first would reject `Account` as well. The `maxdepth/maxrefs/maxbytes/maxarray` limits are checked regardless of class-rule ordering. Whitespace in patterns is significant; do not arbitrarily insert spaces around semicolons or class names.

In the example, a narrow allowlist suffices because `Account`'s graph contains only a `String` field and simple values. Filter callbacks are not invoked for primitives or `String`s encoded directly by the serialization protocol; therefore **do not infer that a class allowlist alone controls all data of every type**. When models include `List`, `Map`, arrays, or nested classes, verify every class that actually appears in the stream, internal representations, and allocatable resources.

## 4. Controlled Experiments

### 4.1. Observing the Effect of `transient`

In the program, change the values when creating the object:

~~~java
serialize(new Account("Minh", "TOKEN-123"))
~~~

Re-running shows `owner=Minh` and `sessionToken=null` in the `Account` output. `transient` prevents **that field** from being written by default serialization; it does not erase data elsewhere, and custom `writeObject` methods can alter what gets written. Never rely on `transient` as your sole protection for secrets.

### 4.2. Blocking `Account` Too via Class Policy

Change the pattern to:

~~~java
String pattern = "maxdepth=5;maxrefs=20;maxbytes=4096;"
        + "maxarray=100;!*";
~~~

Now even `Account` is rejected. In the current program, the first `deserializeWithFilter(acceptedBytes)` call throws `InvalidClassException` before reaching the `catch` meant for `Unexpected`. To observe a friendly message, catch the exception on the first branch or restore the pattern after experimenting.

### 4.3. Testing the Array Size Limit

Standalone example of a 101-element array:

~~~java
byte[] arrayBytes = serialize(new int[101]);
~~~

To test this array with `deserializeWithFilter(...)`, you can pass `arrayBytes`; `maxarray=100` blocks the oversized array. However, that method currently ends with `!*`, so the array could also be blocked by class rules even when within bounds. To test `maxarray` **in isolation**, use an illustrative filter like:

~~~java
ObjectInputFilter arrayFilter =
        ObjectInputFilter.Config.createFilter("maxarray=100;*");
~~~

Install `arrayFilter` on a new `ObjectInputStream` **before `readObject()`**, then read `int[100]` and `int[101]` streams. On default JDK 17, the 100-element array is accepted and the 101-element array is rejected. The `*` pattern permits all classes, so **use it only for array-limit experiments**, never as a protection policy for untrusted data.

### 4.4. Varying Byte and Depth Thresholds

Lowering `maxbytes` from 4096 to a small value like 16 typically causes the example's `Account` stream to be rejected before reconstruction succeeds. However, the byte count reported at each callback depends on read timing; do not treat that threshold as the exact serialized byte-array length. Similarly, on deeply nested graphs, lowering `maxdepth` blocks deep reads. Never hardcode a single demo threshold for every data model.

### 4.5. Distinguishing Failure Causes

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `InvalidClassException` with filter status message | Filter rejected a class or limit | Inspect allowlist, limits, rule order |
| `InvalidClassException` due to `serialVersionUID` | Incompatible class versions between writer and reader | Check `serialVersionUID` and schema changes |
| `NotSerializableException` on write | An object in the graph is not serializable | Inspect relevant fields and types |
| `StreamCorruptedException` / `EOFException` on read | Malformed, missing, or truncated stream | Confirm input is valid Java serialized bytes |
| `ClassNotFoundException` on read | Reader lacks a class named in the stream | Check classpath/modules and deployment |

An error can be wrapped by a caller-layer exception. Never classify failures solely by exception class name without inspecting the message, cause, and program state.

## 5. Two Ways to Configure `ObjectInputFilter`

### 5.1. Per `ObjectInputStream`: Fits This Exercise

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=100;maxbytes=65536;maxarray=1000;"
                + "com.example.io.SafeMessage;!*");
try (ObjectInputStream in = new ObjectInputStream(inputStream)) {
    in.setObjectInputFilter(filter);
    Object value = in.readObject();
}
~~~

This snippet illustrates only the read side inside an application that already has `inputStream` and an existing `com.example.io.SafeMessage` class. It is **not a standalone program**. Specific patterns must be tailored to the actual object graph. Set the filter before `readObject`, close streams with `try-with-resources`, and check the returned type after reading.

### 5.2. JVM-Wide Filter and Filter Factory

The JDK supports a JVM-wide filter via the `jdk.serialFilter` system property or corresponding security property; for instance, launching an app with a global cap:

~~~bash
java -Djdk.serialFilter=maxdepth=20;maxrefs=200;maxbytes=1048576 SerializationFilterDemo
~~~

**Shell note:** `;` is often a special shell metacharacter (especially in PowerShell/Bash). Quote the entire JVM argument to pass the full value intact:

~~~bash
java "-Djdk.serialFilter=maxdepth=20;maxrefs=200;maxbytes=1048576" SerializationFilterDemo
~~~

These global settings apply broadly, so evaluate their impact across every object-reading stream in the application. Since JDK 17, a filter factory can combine the JVM-wide filter with per-stream filters; the exact combination depends on factory configuration. Never assume `setObjectInputFilter` always completely overrides an installed JVM-wide policy. To verify behavior, consult the documentation for your exact JDK and runtime configuration.

**Principle:** application policies must define an allowlist and resource caps tailored to each data stream; a JVM-wide policy is a supporting layer, not a substitute for defining the expected data model at each input boundary.

## 6. When a Filter Must Be Written in Java Instead of a Pattern

Patterns are handy for class-name rules and basic bounds. When contextual logic is required, implement `ObjectInputFilter` directly. Below is an **illustrative snippet** targeting `SafeMessage` in package `com.example.io`:

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

Here `arrayLength() > 1_000` does not reject `-1` (non-array). `serialClass() == null` can happen in callbacks that only update limit counters; returning `UNDECIDED` after checking bounds is appropriate in that branch. When `type` is non-null and disallowed, return `REJECTED` to leave no allowlist gaps.

This illustrates filtering logic and requires `com.example.io.SafeMessage` to be declared in the project. If valid types include auxiliary elements (e.g., certain collections, enums, arrays, or nested classes), build a complete allowlist based on real streams and resource caps; otherwise valid data itself will be rejected.

## 7. Common Misconceptions and Mistakes

1. **Checking `instanceof` only after `readObject()`.** Too late for several risks: Java has already deserialized the graph before the return-type check executes. Install `ObjectInputFilter` before `readObject` to reject earlier within filter capabilities.
2. **Assuming `implements Serializable` implies safety.** This interface only states an object can participate in serialization; it says nothing about trusted byte origin or valid content.
3. **Using a filter with only `maxdepth` and no class restrictions.** A solid policy checks types, array sizes, references, and bytes; where needed, also cap inputs at the transport layer before creating `ObjectInputStream`.
4. **Assuming `UNDECIDED` means `REJECTED`.** In a pattern lacking a final catch-all rejection rule, unmatched classes may still be read.
5. **Misspelling class names.** Nested classes use `$` in their binary names; package and module names (if specified in patterns) must be exact.
6. **Putting `!*` before the allowlist.** Filters evaluate patterns in order, so a leading catch-all rejection rule shadows all allow rules after it.
7. **Believing a filter guarantees absolute security.** Filters shrink the attack surface yet do not verify signatures, block every side effect in custom `readObject`/`readResolve`, or patch library bugs. Untrusted data remains risky even with a filter.
8. **Using serialization for long-term stable data storage.** Changing class names, `serialVersionUID`, fields, or classpath can break compatibility. For long-lived data exchange, prefer explicit schemas like JSON or Protocol Buffers with validation, size limits, and authentication.
9. **Logging or exposing secrets inside objects.** Even when `transient` fields are not serialized by default, calling `toString()` in an app can still expose live values. Print only non-sensitive demo values.

## 8. Self-Check Checklist and Discussion Questions

Re-run the program yourself, then confirm:

- The file is named `SerializationFilterDemo.java`, and `javac` compiles cleanly on JDK 17+.
- `ObjectOutputStream` successfully writes both `Account` and `Unexpected`.
- `Account` is restored when allowed by policy; `owner` remains `Lan` and `sessionToken` becomes `null`.
- `Unexpected` is rejected during `readObject()` under the policy containing the `Account` allowlist and `!*`.
- Moving `!*` to the front causes `Account` to be blocked as well.
- You can explain `maxdepth`, `maxrefs`, `maxbytes`, `maxarray`, and the difference between `ALLOWED` / `REJECTED` / `UNDECIDED`.
- Any object deserialization from untrusted sources in your apps has an explicit policy, transport-layer input bounds, and dedicated error handling.

**Reflection questions:** (1) Why can't casting to `Account` after `readObject` replace `ObjectInputFilter`? (2) Why does a `transient` field become `null`, and when is custom serialization needed? (3) Which legitimate classes might a class-name filter miss if `Account` holds a `List` or array? (4) Why do `maxbytes` and `maxrefs` mitigate resource exhaustion without proving the stream is trustworthy?

## Official References

- Oracle JDK 17 API — `Serializable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Oracle JDK 17 API — `ObjectInputStream`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html
- Oracle JDK 17 API — `ObjectInputFilter`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html
- Oracle JDK 17 API — `ObjectInputFilter.Config` and pattern syntax: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html
- OpenJDK JEP 290 — Filter Incoming Serialization Data: https://openjdk.org/jeps/290
- OpenJDK JEP 415 — Context-Specific Deserialization Filters: https://openjdk.org/jeps/415
