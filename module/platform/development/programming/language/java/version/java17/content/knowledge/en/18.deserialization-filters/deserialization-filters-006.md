# JVM-Wide Filters and Per-ObjectInputStream Filters in Java 17

## 1. Why Filter During Deserialization?

Java serialization converts object state into a byte stream. When a program reads the stream using `ObjectInputStream`, the JVM reconstructs the object graph from the received data. This process can execute custom logic in deserialized classes, such as `readObject()`, `readResolve()`, or behavior triggered when objects are instantiated.

If data comes from an untrusted source, an attacker can control:

- Which classes are requested to be instantiated.
- Field values and reference relationships between objects.
- Depth and size of the object graph.
- Quantities of objects, arrays, and data that deserialization must process.

Some libraries contain *gadget* classes with side effects during deserialization. When such classes are loaded and instantiated from attacker-controlled data, an application can suffer unintended code execution or denial of service.

Java provides **serialization filtering** to inspect classes and limit resources during deserialization. In Java 17, the central APIs are:

- `ObjectInputFilter`: describes the policy to accept, reject, or remain undecided for data being read.
- `ObjectInputFilter.Config`: creates pattern-based filters, configures the JVM-wide filter, and configures the filter factory.
- `ObjectInputStream.setObjectInputFilter()`: sets a filter for a specific stream.
- `ObjectInputFilter.Config.setSerialFilterFactory()`: customizes how filters are selected or combined per stream.

There are two main scopes:

| Scope | Target | Common Configuration Method |
|---|---|---|
| **JVM-wide filter** | Deserialization operations across the entire JVM, via `ObjectInputStream` instances configured per the active factory. | The `jdk.serialFilter` property or `ObjectInputFilter.Config.setSerialFilter()`. |
| **Stream-specific filter** | A specific `ObjectInputStream` instance. | `ObjectInputStream.setObjectInputFilter()`. |

Filters reduce the attack surface, yet **do not make deserializing untrusted data completely safe**. Avoid receiving Java serialized data from untrusted sources whenever possible; prefer data formats with schemas and parsers suited to the protocol. If Java serialization must be used, identify the exact data types needed, apply an allowlist, and enforce resource limits.

## 2. The ObjectInputFilter Model

`ObjectInputFilter` is a functional interface. A filter receives `FilterInfo` and returns one of three statuses:

~~~java
ObjectInputFilter.Status checkInput(
        ObjectInputFilter.FilterInfo info)
~~~

Three statuses:

| Status | Meaning |
|---|---|
| `ALLOWED` | The filter accepts the class or information under inspection. |
| `REJECTED` | The filter rejects; object reading will fail. |
| `UNDECIDED` | The filter reaches no conclusion for this case. Another filter may continue evaluating. |

If no filter rejects, `UNDECIDED` is not synonymous with rejection. On a stream with no other filter, data resulting in `UNDECIDED` can still be deserialized. Therefore, a strict allowlist must have a way to reject unmatched classes, such as a pattern ending in `!*` or a custom filter returning `REJECTED` for unlisted classes.

### 2.1. What Information Does FilterInfo Provide?

`ObjectInputFilter.FilterInfo` provides metadata about the read operation:

| Method | Information |
|---|---|
| `serialClass()` | Class being checked; may be `null` when the call carries only metric/reference info. |
| `arrayLength()` | Length of the array being checked; negative when not an array case. |
| `depth()` | Current depth of the object graph, based on nested read calls. |
| `references()` | Number of objects/references read so far in the stream. |
| `streamBytes()` | Number of stream bytes consumed per implementation at the time of inspection. |

With this, a filter checks not only *which classes* are created, but also *how large* the object graph is.

### 2.2. When Is the Filter Called?

During `readObject()` or `readUnshared()`:

- The filter is called when encountering a new class in the stream, before an instance of that class is created and deserialized.
- Classes in stream type descriptions may be checked separately, including superclasses and interfaces explicitly referenced in the stream.
- Arrays are checked along with the array type and length.
- References to already-read objects can also trigger filter calls to check depth, references, and stream bytes.
- The filter is not called for primitives and `String` values encoded directly in the stream's specific manner.

Do not assume the filter is called exactly once per object. New classes and object graph metrics can produce multiple calls. Also do not assume the filter is called for each primitive field or each string.

### 2.3. How Does Rejection Happen?

If the active filter returns `REJECTED`, `readObject()` or `readUnshared()` throws `InvalidClassException` and deserialization is aborted. This is a filter policy error; it differs from errors reading a corrupted byte stream or class-not-found errors.

Filters should be stateless whenever possible, relying on information in `FilterInfo`. State can be maintained across calls, but must be managed carefully because filters can be invoked many times and object graph reading is nested.

## 3. JVM-Wide Filter

A JVM-wide filter is a static policy shared across the Java process. It is suitable when an application has a common set of rules, such as:

- Rejecting certain classes or packages not permitted to appear in serialized data.
- Allowing only a set of classes the application needs to deserialize.
- Limiting object graph depth, reference count, array size, and total stream bytes.

Java 17 supports configuring a JVM-wide filter in two common ways: startup properties and API configuration.

### 3.1. Configuring via System Property at Launch

Use the `jdk.serialFilter` property:

~~~text
java "-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.dto.**;!*" com.example.Main
~~~

The example above:

- Limits maximum graph depth to 20.
- Limits maximum references to 1,000.
- Limits maximum stream bytes to 1,048,576.
- Limits maximum array length to 10,000.
- Allows classes in package `com.example.dto` and subpackages.
- Rejects all classes not matching the given patterns.

This is a syntax example; the actual class list must match the application's object graphs. Do not copy a broad allowlist without inspecting needed dependent classes.

The system property is read when the `ObjectInputFilter.Config` class is initialized. If using launch-time configuration, pass `-Djdk.serialFilter` directly on the `java` command.

### 3.2. Configuring via JDK Security Property

`jdk.serialFilter` can be set in:

~~~text
$JAVA_HOME/conf/security/java.security
~~~

Example:

~~~properties
jdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.dto.**;!*
~~~

The Security property applies to applications running on the configured runtime. If the `jdk.serialFilter` system property is also set, the system property takes precedence.

This option targets runtime-level configuration; manage edits to the JDK security file via deployment procedures and verify impacts on all applications sharing that runtime.

### 3.3. Configuring via Java API

If the application needs to create the filter in code, use `ObjectInputFilter.Config.createFilter()` and install it with `setSerialFilter()`:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter globalFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=1000;maxbytes=1048576;"
                        + "maxarray=10000;com.example.dto.**;!*");

ObjectInputFilter.Config.setSerialFilter(globalFilter);
~~~

Perform this configuration at application startup, before creating `ObjectInputStream`s needing protection. `setSerialFilter()` sets the static JVM-wide filter only if it has not been configured or set previously. If a filter is already set, the method can throw `IllegalStateException`.

You can read the current filter using:

~~~java
ObjectInputFilter current =
        ObjectInputFilter.Config.getSerialFilter();

System.out.println(current);
~~~

If no filter has been configured, `getSerialFilter()` returns `null`.

### 3.4. Do Not Use System.setProperty Too Late

The following is not a reliable way to configure a filter:

~~~java
System.setProperty(
        "jdk.serialFilter",
        "maxdepth=20;maxrefs=1000;!*");
~~~

`jdk.serialFilter` is read when `ObjectInputFilter.Config` initializes. Calling `System.setProperty()` after that class has initialized **does not reconfigure the filter**. Use `-Djdk.serialFilter` at launch, a Security property, or `Config.setSerialFilter()`.

## 4. Filter Pattern Syntax

`ObjectInputFilter.Config.createFilter(String)` constructs a filter from a pattern string. Patterns are separated by semicolons `;`. Whitespace is part of the pattern, so do not add spaces arbitrarily.

There are two groups of patterns:

1. Resource limit patterns.
2. Class/package/module name patterns to accept or reject classes.

### 4.1. Resource Limits

| Pattern | Limit |
|---|---|
| `maxdepth=n` | Maximum object graph depth. |
| `maxrefs=n` | Maximum reference count. |
| `maxbytes=n` | Maximum bytes read from stream. |
| `maxarray=n` | Maximum array length. |

Example:

~~~java
ObjectInputFilter limits = ObjectInputFilter.Config.createFilter(
        "maxdepth=15;maxrefs=500;maxbytes=2000000;maxarray=50000");
~~~

Limits are checked before evaluating class name patterns. If a limit is exceeded, the filter returns `REJECTED`.

Limits should be chosen from actual valid data sizes plus an appropriate margin. Setting them too low can reject valid data; setting them too high may fail to meaningfully curb resource consumption.

### 4.2. Exact Class Name Patterns

Patterns can match a class's fully qualified name:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "com.example.dto.OrderSnapshot;!*");
~~~

In the example, `OrderSnapshot` is allowed and other unmatched classes are rejected. This is a class-name allowlist.

### 4.3. Package Wildcards

Common forms:

| Pattern | Meaning |
|---|---|
| `com.example.dto.*` | Classes directly in package `com.example.dto`. |
| `com.example.dto.**` | Classes in that package and all subpackages. |
| `com.example.dto.Order*` | Class names starting with `com.example.dto.Order`. |
| `*` | All class names. |

`.*` does not include subpackages. If subpackages must be covered, use `.**`.

### 4.4. Rejection Patterns with !

Prepend `!` to reject matching classes:

~~~text
!com.example.internal.UnsafeType;com.example.dto.**;!*
~~~

Example:

- Reject `com.example.internal.UnsafeType`.
- Allow classes in `com.example.dto` and subpackages.
- Reject all remaining classes.

Patterns are evaluated left to right; the first matching class pattern determines `ALLOWED` or `REJECTED`. If no class pattern matches, the result is `UNDECIDED`. Therefore, if you want a true allowlist, add `!*` at the end to reject remaining classes.

### 4.5. Patterns with Module Names

A module name can be added before a slash:

~~~text
java.base/java.util.*;com.example.app/com.example.dto.**
~~~

The part before `/` is the module name; the part after is the class name pattern. Without a module prefix, matching is based solely on class name.

### 4.6. Patterns Do Not Check Inheritance Relationships

Patterns match class, package, or module names. They cannot say "allow all classes implementing interface X" or "allow all subclasses of superclass Y". Patterns also do not check interfaces implemented by a class, unless an interface is explicitly referenced in the stream.

If a policy must depend on parent types/interfaces, write a custom filter using `Class.isAssignableFrom()`. Patterns suit simple name-based cases.

### 4.7. Classes Not Matching a Pattern Are Not Necessarily Rejected

Example:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter("com.example.dto.*");
~~~

Classes in the matching package are `ALLOWED`. Unmatched classes return `UNDECIDED`, not automatic rejection. If no other filter rejects, deserialization can still continue.

To allow only that package:

~~~java
ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(
                "com.example.dto.*;!*");
~~~

## 5. Per-ObjectInputStream Filters

A JVM-wide filter fits a shared policy. However, many applications have distinct data flows:

- One stream receives only order DTOs.
- One stream receives only report metadata.
- Another stream receives internal data with its own set of types.

In this case, a filter can be set directly on each `ObjectInputStream` using `setObjectInputFilter()`.

### 5.1. When to Set the Filter

The filter must be set **after creating ObjectInputStream and before reading any object**:

~~~java
try (ObjectInputStream input =
        new ObjectInputStream(source)) {

    input.setObjectInputFilter(myFilter);

    Object value = input.readObject();
}
~~~

`setObjectInputFilter()` may be called only once per stream and must be called before the first `readObject()` or `readUnshared()`. Calling it too late or a second time can throw `IllegalStateException`.

You can inspect the active filter on a stream with `getObjectInputFilter()`:

~~~java
ObjectInputFilter active = input.getObjectInputFilter();
~~~

The result is the filter returned by the JVM-wide factory for the stream; it can be the JVM-wide filter, the per-stream filter, or a combined filter depending on the factory.

### 5.2. Custom Filter via Lambda

Example filter allowing only one DTO type and bounding the object graph:

~~~java
ObjectInputFilter orderFilter = info -> {
    if (info.depth() > 16
            || info.references() > 1000
            || info.streamBytes() > 1_000_000
            || (info.arrayLength() >= 0
                    && info.arrayLength() > 10_000)) {
        return ObjectInputFilter.Status.REJECTED;
    }

    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == OrderSnapshot.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
~~~

The policy above:

- Rejects graphs deeper than 16.
- Rejects when there are more than 1,000 references.
- Rejects streams larger than 1 MB.
- Rejects arrays with more than 10,000 elements.
- Allows only `OrderSnapshot`; other classes are rejected.
- When `serialClass()` is `null`, the filter makes no class decision yet has already checked metrics.

This is a very narrow allowlist. If the actual object graph needs additional types, such as a nested DTO or serialized collection type, include those types in the policy after reviewing the data contract. Do not broaden to an entire package or entire module just to make errors go away.

### 5.3. Creating a Pattern Filter for a Single Stream

There is no need to write a lambda if rules consist only of class names and limits:

~~~java
ObjectInputFilter orderFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=16;maxrefs=1000;maxbytes=1000000;"
                        + "maxarray=10000;"
                        + "com.example.dto.OrderSnapshot;!*");

try (ObjectInputStream input =
        new ObjectInputStream(source)) {
    input.setObjectInputFilter(orderFilter);
    Object value = input.readObject();
}
~~~

Pattern filters suit simple allowlists and limits. Use custom filters when checking types by inheritance, module, class loader, or more complex logic.

## 6. Complete Example: Stream-Specific Filter Reading OrderSnapshot

The following example creates a small serializable DTO, writes it to a byte array, and reads it back using an `ObjectInputStream` configured with a filter. In practice, the byte stream may come from a file, socket, or storage; the example uses a byte array to focus on the filter mechanism.

Create the file `StreamFilterDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class StreamFilterDemo {
    private StreamFilterDemo() {
    }

    static final class OrderSnapshot implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String orderId;
        private final long quantity;

        OrderSnapshot(String orderId, long quantity) {
            this.orderId = orderId;
            this.quantity = quantity;
        }

        @Override
        public String toString() {
            return "OrderSnapshot[orderId=" + orderId
                    + ", quantity=" + quantity + "]";
        }
    }

    private static ObjectInputFilter.Status orderFilter(
            ObjectInputFilter.FilterInfo info) {

        if (info.depth() > 16
                || info.references() > 1000
                || info.streamBytes() > 1_000_000
                || (info.arrayLength() >= 0
                        && info.arrayLength() > 10_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        return type == OrderSnapshot.class
                ? ObjectInputFilter.Status.ALLOWED
                : ObjectInputFilter.Status.REJECTED;
    }

    private static byte[] serialize(OrderSnapshot snapshot)
            throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream output =
                new ObjectOutputStream(bytes)) {
            output.writeObject(snapshot);
        }
        return bytes.toByteArray();
    }

    private static OrderSnapshot deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {

            input.setObjectInputFilter(StreamFilterDemo::orderFilter);

            Object value = input.readObject();
            if (!(value instanceof OrderSnapshot snapshot)) {
                throw new IOException("Unexpected object type");
            }
            return snapshot;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = serialize(new OrderSnapshot("ORD-42", 3));

        OrderSnapshot snapshot = deserialize(bytes);
        System.out.println(snapshot);
    }
}
~~~

Compile and run with JDK 17:

~~~text
javac --release 17 -encoding UTF-8 StreamFilterDemo.java
java StreamFilterDemo
~~~

Output:

~~~text
OrderSnapshot[orderId=ORD-42, quantity=3]
~~~

This example demonstrates a filter for a single stream. `String` is handled specially in serialization and does not invoke the filter like an ordinary class; the filter still checks the DTO class and object graph metrics.

If the stream contains another class outside the allowlist, `orderFilter` returns `REJECTED` and `readObject()` fails with `InvalidClassException`. In a real application, keep the list of allowed types as specific as possible.

## 7. Relationship Between JVM-Wide Filters and Per-Stream Filters

This is the part requiring the greatest attention when an application uses both scopes.

### 7.1. Java 17's Default Factory

If no custom filter factory is installed, Java uses the built-in filter factory. Behavior of the default factory:

- When creating `ObjectInputStream`, the static JVM-wide filter is used as the initial filter for the stream.
- When calling `setObjectInputFilter()`, the requested stream-specific filter **replaces the static JVM-wide filter** on that stream, per built-in factory behavior.

Therefore, do not assume calling `setObjectInputFilter(localFilter)` automatically merges `localFilter` with the JVM-wide filter. With the default factory, a stream filter can replace the JVM-wide filter on that stream.

Example:

~~~java
// JVM-wide filter has been configured.
ObjectInputFilter global =
        ObjectInputFilter.Config.getSerialFilter();

try (ObjectInputStream input =
        new ObjectInputStream(source)) {

    // With the default built-in factory, localFilter replaces the current filter
    // on this stream rather than automatically merging with global.
    input.setObjectInputFilter(localFilter);
    Object value = input.readObject();
}
~~~

This does not mean a JVM-wide filter is useless. It acts as the default policy for streams that do not set their own filter. However, if you want every stream to obey both common limits and stream-specific allowlists, design a factory that combines the filters.

### 7.2. What Is a Filter Factory?

A filter factory is a function of type:

~~~java
BinaryOperator<ObjectInputFilter>
~~~

The factory is invoked:

1. When an `ObjectInputStream` is constructed.
2. When `setObjectInputFilter()` is called on the stream.

It receives two arguments:

- `current`: the filter currently used for the stream; on the first call, typically `null`.
- `requested`: the JVM-wide filter when creating the stream, or the stream filter passed to `setObjectInputFilter()`.

The factory returns the filter actually attached to the stream. It can choose a filter based on context, such as thread-local, call stack, module, library, or class loader.

### 7.3. Configuring a Factory in Java 17

Java 17 adds `ObjectInputFilter.Config.setSerialFilterFactory()`. You can configure a simple factory to combine the current filter and the new filter:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory(
        (current, requested) -> {
            if (current == null) {
                return requested;
            }
            if (requested == null) {
                return current;
            }
            return ObjectInputFilter.merge(current, requested);
        });
~~~

The factory must be configured **before any `ObjectInputStream` is created**. It can only be set once. If a factory was already configured via the `jdk.serialFilterFactory` system property or Security property at startup, it cannot be replaced via `setSerialFilterFactory()`.

A factory can be configured at launch time:

~~~text
java -Djdk.serialFilterFactory=com.example.SecurityFilterFactory com.example.Main
~~~

The factory class must be public, have a public no-arg constructor, implement `BinaryOperator<ObjectInputFilter>`, and be accessible to the application class loader.

### 7.4. Understanding merge Precisely

`ObjectInputFilter.merge(first, second)` combines the results of two filters according to the rules:

| Filter A Result | Filter B Result | Merge Result |
|---|---|---|
| At least one `REJECTED` | Any | `REJECTED` |
| No `REJECTED` and at least one `ALLOWED` | `ALLOWED` or `UNDECIDED` | `ALLOWED` |
| Both `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |

Thus, `merge` is **not an intersection of two allowlists**. If one filter allows a class and the other filter is undecided, the result is still `ALLOWED`. If you want a filter to reject unknown classes, have that filter return `REJECTED` for classes outside its allowlist.

For example, a suitable setup is:

- The global filter enforces only resource limits; if exceeded it returns `REJECTED`, and for unevaluated classes it returns `UNDECIDED`.
- The per-stream filter is a strict allowlist, allowing required types and returning `REJECTED` for all other classes.
- The factory merges the two filters. The result still rejects when JVM-wide limits are exceeded or when a class is outside the stream's allowlist.

Do not merge two filters with complex class policies without clearly understanding `ALLOWED`, `REJECTED`, and `UNDECIDED`. A misconfiguration can unintentionally broaden the allowed class set.

## 8. Helper Methods for Creating Filters in Java 17

Besides `createFilter()`, `ObjectInputFilter` provides static methods for creating and combining filters.

### 8.1. `allowFilter()`

Creates a filter accepting classes matching a predicate:

~~~java
ObjectInputFilter numbers = ObjectInputFilter.allowFilter(
        type -> Number.class.isAssignableFrom(type),
        ObjectInputFilter.Status.UNDECIDED);
~~~

Classes that are subtypes of `Number` return `ALLOWED`; other classes return `UNDECIDED`. If you want to reject other classes, use `REJECTED` as the fallback status or combine with `rejectUndecidedClass()` per your policy.

### 8.2. `rejectFilter()`

Creates a filter rejecting classes matching a predicate:

~~~java
ObjectInputFilter rejectInternal = ObjectInputFilter.rejectFilter(
        type -> type.getName().startsWith("com.example.internal."),
        ObjectInputFilter.Status.UNDECIDED);
~~~

Classes in the internal package are rejected; other classes are left unevaluated by this filter.

### 8.3. `rejectUndecidedClass()`

This method wraps a filter and turns `UNDECIDED` results into `REJECTED` for applicable classes. It is useful when building an allowlist: only classes confirmed `ALLOWED` by the filter proceed.

~~~java
ObjectInputFilter allowNumbers = ObjectInputFilter.allowFilter(
        type -> Number.class.isAssignableFrom(type),
        ObjectInputFilter.Status.UNDECIDED);

ObjectInputFilter strictNumbers =
        ObjectInputFilter.rejectUndecidedClass(allowNumbers);
~~~

Metric-only callbacks with `serialClass() == null` can still return `UNDECIDED`; the conversion focuses on class decisions. For arrays, the API also checks component types under specific rules. Read the Javadoc when designing allowlists for arrays.

### 8.4. `merge()`

`merge()` combines two filters per the table in the previous section. It is an essential tool when implementing a factory, yet remember that `ALLOWED` from one filter beats `UNDECIDED` from the other; only `REJECTED` always vetoes.

## 9. Limitations of Serialization Filters

Serialization filters are a useful defense layer, but they do not replace other safeguards.

### 9.1. Filters Do Not Check Individual Field Values

Filters check classes, array lengths, and graph metrics. They do not verify that:

- `quantity` must be greater than 0.
- `amount` is non-negative.
- `customerId` has a valid format.
- A string does not exceed business limits.
- Object state fits the business workflow.

Validate data after deserialization or within object-reading logic per the data contract. Class invariants also need protection.

### 9.2. Filters Do Not Make Allowed Classes Safe

If a class is in the allowlist yet has a dangerous `readObject()` or can invoke undesirable side effects, the filter can still permit that class. Allowlists must be built from types the application truly needs and whose behavior has been reviewed.

### 9.3. Filters Do Not Check Primitives and Strings Like Ordinary Classes

Directly encoded primitive values and `String`s do not trigger class checks the way ordinary objects do. Therefore, if string length limits or content rules are needed, validate after reading; do not assume `maxarray` limits strings.

### 9.4. Filters Do Not Replace Protocol Limits

`maxbytes` limits are helpful, yet the application should still bound data size at the transport layer before creating `ObjectInputStream`. For sockets or uploads, enforce timeouts, request body limits, source authentication, and overall resource limits.

### 9.5. Filters Apply Only to Java Serialization Filtering

`ObjectInputFilter` does not automatically filter JSON parsers, XML parsers, YAML parsers, or other object conversion libraries. Each format needs its own parser, schema, and limits.

### 9.6. Serialization Filtering Is Not Enabled by Default

Java serialization filtering is not automatically active unless the application configures a filter via system property, Security property, or API. Check runtime configuration and confirm a filter is actually attached to a stream using `getObjectInputFilter()` when diagnosing.

## 10. Logging to Observe Filter Decisions

Java provides the `java.io.serialization` logger to record filtering actions. This is a useful diagnostic tool for identifying which classes are read, which are rejected, or why a limit was exceeded.

In the JDK logging configuration file:

~~~properties
java.io.serialization.level = FINE
~~~

The `FINE` level logs rejection results. To view all results:

~~~properties
java.io.serialization.level = FINEST
~~~

Do not enable verbose logging indefinitely in production under high traffic. Logs can reveal class names, data structures, or internal details; restrict access permissions and retention.

## 11. How to Choose Filter Scope

| Scenario | Implementation Approach |
|---|---|
| Application has one shared deserialization policy | Set a JVM-wide filter via `jdk.serialFilter` or `Config.setSerialFilter()`. |
| Each stream receives a different set of DTOs | Set a stream-specific filter via `setObjectInputFilter()` before reading. |
| Want JVM-wide resource limits and per-stream allowlists | Configure a filter factory to combine JVM-wide and stream filters. |
| Only need to block a few identified classes | Use a reject-list, while still considering allowlists and resource limits. |
| Allow only a small set of known classes | Use an allowlist ending in `!*` or a custom filter returning `REJECTED` for invalid classes. |
| Need decisions by inheritance or context | Use custom filters or a filter factory, not just name patterns. |

A policy can combine two layers:

~~~text
JVM-wide:
  - Limit depth, references, bytes, array length.
  - Common rejection rules for the whole process.

Per ObjectInputStream:
  - Allowlist of types this stream is permitted to read.
  - Additional limits for the specific data format.

Filter factory:
  - Select or combine filters.
  - Preserve JVM-wide rules when a stream has its own filter.
~~~

Not every application needs a filter factory. With one shared policy and no per-stream filters, a JVM-wide filter is enough. A factory is only needed when customizing how filters are selected/combined per stream or context.

## 12. Common Mistakes

| Symptom | Cause | How to Fix |
|---|---|---|
| Thinking filters are enabled by default in Java 17 | Filtering is not configured by default. | Set `jdk.serialFilter` or configure via `ObjectInputFilter.Config`. |
| Calling `System.setProperty("jdk.serialFilter", ...)` does not change the filter | `Config` already initialized; property is read at class initialization time. | Set the system property at startup or use `setSerialFilter()` before a filter is configured. |
| `setSerialFilter()` throws `IllegalStateException` | JVM-wide filter was already configured or set earlier. | Choose a single configuration point, preferably at startup. |
| `setObjectInputFilter()` throws `IllegalStateException` | Objects already read or filter already set for the stream. | Set filter right after the `ObjectInputStream` constructor and call only once. |
| Stream filter drops JVM-wide limits | Default built-in filter factory replaces static global filter with stream filter. | Use a filter factory to combine both policies if both are needed. |
| Classes outside allowlist are still read | Filter returns `UNDECIDED` instead of `REJECTED` for unmatched classes. | Add `!*` to pattern or return `REJECTED` for unlisted classes. |
| Package pattern fails to match subpackages | Used `.*` instead of `.**`. | Use the wildcard matching the intended package scope. |
| Assuming `merge` is the intersection of two allowlists | `ALLOWED` from one filter beats `UNDECIDED` from the other; only `REJECTED` always vetoes. | Design statuses and factory according to an explicit policy. |
| Checking only class names while ignoring large graphs | Filter does not limit depth, references, array length, or bytes. | Combine allowlist with resource limits. |
| Using filters to validate business data | Filters do not check individual field values. | Validate objects after reading against domain rules. |
| Thinking filters protect all parsers | `ObjectInputFilter` applies only to Java serialization. | Use separate limiting and validation mechanisms for JSON/XML/other formats. |

## 13. Practice Exercises

### Exercise 1 — Configuring a JVM-Wide Filter

Create a filter using `Config.createFilter()` with limits:

- Max depth 12.
- Max references 500.
- Max stream bytes 500,000.
- Max array length 5,000.

Set the filter via `Config.setSerialFilter()` before creating `ObjectInputStream`. Call `getSerialFilter()` to display the active configuration.

### Exercise 2 — Writing a Per-Stream Allowlist

Create two serializable classes `CustomerSnapshot` and `InternalCommand`. Write a filter allowing `CustomerSnapshot` and rejecting `InternalCommand` plus all other types. Set the filter before `readObject()` and observe the exception when reading a disallowed object.

### Exercise 3 — Distinguishing UNDECIDED and REJECTED

Create a filter returning `ALLOWED` only for `CustomerSnapshot` and `UNDECIDED` for other types. Try reading an object of another type with no other filter present. Then change the default status to `REJECTED`. Explain why the two runs produce different results.

### Exercise 4 — Preserving Both JVM-Wide Limits and Per-Stream Filters

Set a global filter that checks only resource limits. Install a filter factory with `setSerialFilterFactory()` to combine the current filter and the filter requested for the stream. Set a stream-specific allowlist for `CustomerSnapshot`. Test an object graph exceeding `maxdepth` and a class outside the allowlist.

### Exercise 5 — Checking Patterns

Given patterns `com.example.dto.*`, `com.example.dto.**`, `!com.example.dto.InternalCommand`, and `!*`, determine which classes are allowed/rejected. Create a class in a subpackage to distinguish `.*` from `.**`.

### Exercise 6 — Resource Limits

Create a multi-level nested object graph and a large array. Set low `maxdepth` and `maxarray` values to observe filter rejection. Explain why resource limits must be chosen based on the application's valid data sizes.

### Self-Check Hints

- Exercise 1: Join patterns with `;` and call `setSerialFilter` before creating streams.
- Exercise 2: Compare class tokens `type == CustomerSnapshot.class` and return `REJECTED` for other types.
- Exercise 3: `UNDECIDED` does not reject on its own; without another filter, the object can still be read.
- Exercise 4: The factory is called at stream creation and when setting a stream filter; `merge` must preserve the rule that `REJECTED` vetoes.
- Exercise 5: `.*` matches only the direct package; `.**` includes subpackages.
- Exercise 6: `depth`, `arrayLength`, `references`, and `streamBytes` are distinct metrics that must be checked per application requirements.

## 14. Principles to Remember

- Java serialization filtering uses `ObjectInputFilter` to inspect classes and object graph complexity during reading.
- JVM-wide filters set a shared policy via `jdk.serialFilter` or `Config.setSerialFilter()`.
- Stream-specific filters are set via `ObjectInputStream.setObjectInputFilter()` and must be called before reading the first object.
- With the built-in filter factory, a stream filter can replace the JVM-wide filter on that stream; to combine both, configure an appropriate filter factory.
- `jdk.serialFilterFactory` and `Config.setSerialFilterFactory()` allow customizing filter selection/combination; the factory must be configured before creating any `ObjectInputStream`.
- `ALLOWED` accepts, `REJECTED` rejects, `UNDECIDED` reaches no conclusion. Do not use `UNDECIDED` if the goal is a strict allowlist without another filter.
- Patterns support class, package, and module names along with `maxdepth`, `maxrefs`, `maxbytes`, and `maxarray` limits.
- `.*` matches direct packages; `.**` includes subpackages; `!*` rejects classes not matching preceding patterns.
- `merge` returns `REJECTED` if either filter rejects, `ALLOWED` if neither rejects and at least one allows, and `UNDECIDED` otherwise.
- Filters do not validate field values, do not make allowed classes inherently safe, and do not apply to other serialization formats.
- Combine allowlists, resource limits, post-read data validation, and data source control. Avoid deserializing untrusted data when possible.

### References

- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html).
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html).
- [Java SE 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html).
- [Oracle Java 17 — Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html).
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290).
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415).
