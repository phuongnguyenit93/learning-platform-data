# ALLOWED, REJECTED, and UNDECIDED Statuses in Java 17 Serialization Filtering

Java Object Serialization can reconstruct an object graph from a byte stream. When an application reads serialized data, classes in the object graph can be instantiated and some class logic may participate in restoring data. If data comes from an untrusted source, allowing any class to be deserialized can create security risks and unexpected resource consumption.

Java provides **Serialization Filtering** via `java.io.ObjectInputFilter`. The filter is invoked during deserialization to inspect classes, object graph depth, reference counts, stream size, and array length. Each check can return one of three statuses:

- **`ALLOWED`**: the filter accepts the object or condition being checked.
- **`REJECTED`**: the filter rejects; `ObjectInputStream` stops reading with an appropriate error.
- **`UNDECIDED`**: the filter does not make a decision for this check.

The most important point: **`UNDECIDED` does not mean reject**. When a filter returns `UNDECIDED`, Java can continue deserialization if no other filter rejects. Therefore, you must understand all three statuses, how filters combine, and how to build an explicit allow-list policy.

The APIs in this lesson are present in Java 17. Utilities such as `allowFilter`, `rejectFilter`, `merge`, and `rejectUndecidedClass` were added in Java 17.

## 1. What Problem Does Serialization Filtering Solve?

Java Serialization allows writing objects to a byte stream and reading them back into objects. For example:

```java
import java.io.*;

record UserSnapshot(String username, int level)
        implements Serializable {
}

public class SerializationDemo {
    public static void main(String[] args) throws Exception {
        UserSnapshot original = new UserSnapshot("lan", 3);

        byte[] bytes;
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(buffer)) {
            output.writeObject(original);
            bytes = buffer.toByteArray();
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            Object restored = input.readObject();
            System.out.println(restored);
        }
    }
}
```

Output:

```text
UserSnapshot[username=lan, level=3]
```

When reading a stream, the application is not merely receiving a passive byte array. Java must determine the class of objects written in the stream, instantiate them, and restore their state per serialization rules.

If an application reads data supplied by a user, client, external service, or untrusted file, the stream can contain classes the application did not intend to process. An overly deep object graph, excessive references, or huge arrays can also consume excessive resources.

Serialization Filtering enables the application to make decisions while reading the object graph:

- Which classes are accepted.
- Which classes are rejected.
- Whether the object graph exceeds a depth limit.
- Whether the reference count exceeds a limit.
- Whether total bytes read exceed a limit.
- Whether an array being created is too large.

Filters do not replace business data validation. They are a control layer specifically for the Java Object Deserialization process.

## 2. The Three Statuses of `ObjectInputFilter.Status`

The `ObjectInputFilter.Status` enum is in `java.io` and has exactly three constants:

| Status | Meaning | Role in Policy |
| --- | --- | --- |
| `ALLOWED` | Accepted. | This filter agrees to allow the check. |
| `REJECTED` | Rejected. | This filter vetoes the check; reading is blocked. |
| `UNDECIDED` | Undecided, neither allowing nor rejecting. | This filter has no opinion; another filter may make a decision. |

### 2.1. `ALLOWED`

Return `ALLOWED` when the filter determines the class or condition under inspection is within the accepted policy.

For example, a filter accepting only a specific DTO record:

```java
import java.io.ObjectInputFilter;

record UserSnapshot(String username, int level)
        implements java.io.Serializable {
}

ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == UserSnapshot.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Here the filter makes an acceptance decision when the class being checked is `UserSnapshot`. For other classes, it has no opinion and returns `UNDECIDED`.

`ALLOWED` applies to the result of the filter in question. When multiple filters are combined, another filter can still return `REJECTED` and cause the overall outcome to be rejected.

### 2.2. `REJECTED`

Return `REJECTED` when an object or resource limit violates the policy.

Example rejecting any class not in the allowed list:

```java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == UserSnapshot.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

If a filter rejects a class during reading, `ObjectInputStream` aborts deserialization and throws an error, typically `InvalidClassException` indicating the filter rejected it.

Do not return `REJECTED` merely because the current filter does not recognize a condition outside its scope if another filter is responsible for evaluating that condition. In such cases, `UNDECIDED` may be the right choice.

### 2.3. `UNDECIDED`

`UNDECIDED` means the filter neither confirms acceptance nor requests rejection. It is useful when a filter checks only one part of a policy.

For example, a filter concerned only with proxy classes:

```java
import java.lang.reflect.Proxy;
import java.io.ObjectInputFilter;

ObjectInputFilter noProxyFilter = info -> {
    Class<?> type = info.serialClass();

    if (type != null && Proxy.isProxyClass(type)) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

This filter rejects only proxy classes. For all other classes, it returns `UNDECIDED` because it has no goal of evaluating them.

**Important warning:** if only `noProxyFilter` is attached to a stream, other classes are not rejected by this filter. `UNDECIDED` does not automatically turn into `REJECTED`. If the application wants to allow only a specific set of classes, an allow-list policy or appropriate use of `rejectUndecidedClass` is required.

## 3. What Happens When a Filter Returns Each Status?

During deserialization:

- `REJECTED` causes the check to fail and reading cannot proceed normally.
- `ALLOWED` indicates the filter accepts the check.
- `UNDECIDED` does not block the object; if no filter rejects, Java can continue deserializing.

Remember it as:

```text
                 ObjectInputFilter.checkInput(info)
                              |
               +--------------+--------------+
               |              |              |
               v              v              v
            ALLOWED        REJECTED       UNDECIDED
               |              |              |
               v              v              v
       Filter agrees      Rejects reading   Filter has no opinion
       to allow           object graph      |
                              |             v
                              v         Another filter may
                       InvalidClassException  make a decision
                                            |
                                            v
                                   If not rejected,
                                   deserialization continues
```

Because `UNDECIDED` can allow objects to still be read, a filter returning `UNDECIDED` for all classes provides no effective protection. A filter must actually return `REJECTED` for cases that should be blocked, or be combined with a filter responsible for deciding the rest.

## 4. What Information Does `FilterInfo` Provide?

The primary filter method is:

```java
ObjectInputFilter.Status checkInput(
        ObjectInputFilter.FilterInfo filterInfo
);
```

`FilterInfo` provides information about the object being processed and the stream state:

| Method | Meaning |
| --- | --- |
| `serialClass()` | Class being checked; may be `null` if the check pertains only to resource metrics. |
| `arrayLength()` | Array length if checking an array; negative if not an array. |
| `depth()` | Current depth of the object graph. |
| `references()` | Number of object references processed so far in the stream. |
| `streamBytes()` | Number of bytes read from the stream at the time of the check. |

A filter can evaluate one or more of these pieces of information.

### 4.1. `serialClass()` Can Be Null

Never assume `serialClass()` always returns a class:

```java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == UserSnapshot.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

When `serialClass()` is `null`, the filter can still inspect `depth()`, `references()`, and `streamBytes()`. Therefore, evaluate resource limits before returning `UNDECIDED` when no class is present.

Do not return `null` from `checkInput()`. The API contract requires one of the three enum values; returning `null` can lead to a `NullPointerException` or unpredictable behavior.

### 4.2. Object Graph Depth

`depth()` reports the depth of the object structure being read. An overly deep graph can increase stack or resource consumption.

Example:

```java
private static final long MAX_DEPTH = 20;

ObjectInputFilter depthFilter = info -> {
    if (info.depth() > MAX_DEPTH) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

This filter checks only depth. It does not decide which classes are allowed; it can be combined with another filter to check class types.

### 4.3. Reference Count

`references()` reports how many object references have been processed. A stream containing an excessive number of objects can consume memory and processing time.

```java
private static final long MAX_REFERENCES = 10_000;

ObjectInputFilter referenceFilter = info -> {
    if (info.references() > MAX_REFERENCES) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Actual limits should be based on the application's valid object graph sizes. Do not pick an excessively large number merely to avoid errors on unusual data.

### 4.4. Stream Size

`streamBytes()` reports the number of bytes read. You can limit the amount of input data:

```java
private static final long MAX_STREAM_BYTES = 1_000_000;

ObjectInputFilter byteLimitFilter = info -> {
    if (info.streamBytes() > MAX_STREAM_BYTES) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Byte limits reduce the risk of reading an oversized stream. They do not replace file or request size limits at the network layer; limit data before creating the stream and continue checking inside the filter.

### 4.5. Array Length

`arrayLength()` is useful when serialized data contains arrays. Large arrays can require significant memory allocation.

```java
private static final long MAX_ARRAY_LENGTH = 100_000;

ObjectInputFilter arrayFilter = info -> {
    long length = info.arrayLength();

    if (length >= 0 && length > MAX_ARRAY_LENGTH) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

Check `length >= 0` so only actual array cases are evaluated. For non-array objects, `arrayLength()` does not represent a valid array length.

## 5. Combining Class Checks and Resource Limits

A practical filter often needs multiple conditions. For example, accepting only a DTO record while limiting depth, reference count, bytes, and arrays:

```java
import java.io.ObjectInputFilter;

record UserSnapshot(String username, int level)
        implements java.io.Serializable {
}

public class UserSnapshotFilter {

    private static final long MAX_DEPTH = 20;
    private static final long MAX_REFERENCES = 2_000;
    private static final long MAX_STREAM_BYTES = 1_000_000;
    private static final long MAX_ARRAY_LENGTH = 100_000;

    static ObjectInputFilter createFilter() {
        return info -> {
            if (info.depth() > MAX_DEPTH
                    || info.references() > MAX_REFERENCES
                    || info.streamBytes() > MAX_STREAM_BYTES
                    || (info.arrayLength() >= 0
                        && info.arrayLength() > MAX_ARRAY_LENGTH)) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == UserSnapshot.class
                    || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }
}
```

In the example:

1. Check resource limits first.
2. If any limit is exceeded, return `REJECTED` immediately.
3. If there is no class to evaluate, return `UNDECIDED`.
4. Accept the explicitly stated classes.
5. Reject other classes.

The class list in the example is only an illustrative policy for a very simple object graph. Real applications must account for every type that can appear in the graph, including collections, element classes, arrays, and supporting types actually used by the serialization format.

Do not replace a specific allow-list with overly broad rules such as allowing every class on the entire classpath or every class in a module without a clear reason.

## 6. Why Can `UNDECIDED` Create a Fail-Open Policy?

Suppose a filter is only tasked with rejecting one dangerous class:

```java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == DangerousPayload.class) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

This filter behaves like a **deny-list**: a specific class is rejected, while other classes fall outside the filter's decision scope.

If the goal is to allow only `UserSnapshot` and reject all other classes, the snippet above is insufficient. Classes other than `DangerousPayload` still receive `UNDECIDED` and can be read.

A strict allow-list should return `REJECTED` for unlisted classes:

```java
ObjectInputFilter allowList = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == UserSnapshot.class || type == String.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};
```

Another option is using `ObjectInputFilter.rejectUndecidedClass()` to turn `UNDECIDED` results into rejections for classes not yet accepted.

### When Should `UNDECIDED` Be Returned?

Return `UNDECIDED` when:

- The filter checks only part of a policy.
- The check has no `serialClass` and the filter has no reason to reject based on class alone.
- The filter is being combined with another filter responsible for remaining classes or limits.
- The filter does not want to impose a decision on cases outside its scope.

### When Should Unknown Classes Not Be Left `UNDECIDED`?

If the goal is a strict allow-list, unlisted classes must be rejected. You can return `REJECTED` directly or use `rejectUndecidedClass` when the filter structure is designed to return `UNDECIDED` for out-of-scope classes.

## 7. Using `ObjectInputFilter.allowFilter()` in Java 17

Java 17 provides the `allowFilter(Predicate<Class<?>>, Status)` helper to create a filter from a class predicate.

Syntax:

```java
ObjectInputFilter allowFilter = ObjectInputFilter.allowFilter(
        classPredicate,
        otherStatus
);
```

Behavior:

- If `serialClass()` is `null`, the filter returns `UNDECIDED`.
- If the predicate returns `true`, the filter returns `ALLOWED`.
- If the predicate returns `false`, the filter returns `otherStatus`.

Allow-list example:

```java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.allowFilter(
        type -> type == UserSnapshot.class
                || type == String.class,
        ObjectInputFilter.Status.REJECTED
);
```

For classes not in the list, `otherStatus` is `REJECTED`. This is the right choice when the filter itself must decide whether classes are accepted or rejected.

If using `UNDECIDED` as `otherStatus`:

```java
ObjectInputFilter partialAllowFilter = ObjectInputFilter.allowFilter(
        type -> type == UserSnapshot.class,
        ObjectInputFilter.Status.UNDECIDED
);
```

the filter accepts only `UserSnapshot` and makes no decision about other classes. If used alone, non-matching classes are not automatically blocked. Consider the overall policy before choosing this status.

## 8. Using `ObjectInputFilter.rejectFilter()` to Create a Deny-List

`rejectFilter(Predicate<Class<?>>, Status)` creates a filter from a predicate identifying classes to reject.

Behavior:

- `serialClass()` is `null`: returns `UNDECIDED`.
- Predicate true: returns `REJECTED`.
- Predicate false: returns `otherStatus`.

Example rejecting dynamic proxies:

```java
import java.io.ObjectInputFilter;
import java.lang.reflect.Proxy;

ObjectInputFilter noProxyFilter = ObjectInputFilter.rejectFilter(
        Proxy::isProxyClass,
        ObjectInputFilter.Status.UNDECIDED
);
```

This filter rejects proxy classes. Remaining classes receive `UNDECIDED` because the filter is only responsible for a specific deny rule.

Another status can be specified when the predicate is false:

```java
ObjectInputFilter proxyFilter = ObjectInputFilter.rejectFilter(
        Proxy::isProxyClass,
        ObjectInputFilter.Status.ALLOWED
);
```

In this case, every non-proxy class is accepted by the filter. Be careful: this is a much broader decision than merely rejecting proxies. If the application needs an allow-list, use a dedicated allow-list filter instead of turning a deny-list into an allow-everything-else policy.

## 9. Combining Filters with `ObjectInputFilter.merge()`

Java 17 provides `ObjectInputFilter.merge(filter1, filter2)` to combine two filters.

Combination rules:

1. Invoke the first filter.
2. If the first filter returns `REJECTED`, the result is `REJECTED`.
3. If not rejected, invoke the second filter.
4. If the second filter returns `REJECTED`, the result is `REJECTED`.
5. If either returns `ALLOWED`, the result is `ALLOWED`.
6. If both return `UNDECIDED`, the result is `UNDECIDED`.

Result table:

| Filter A | Filter B | Merge Result |
| --- | --- | --- |
| `REJECTED` | `ALLOWED` | `REJECTED` |
| `REJECTED` | `UNDECIDED` | `REJECTED` |
| `ALLOWED` | `REJECTED` | `REJECTED` |
| `ALLOWED` | `ALLOWED` | `ALLOWED` |
| `ALLOWED` | `UNDECIDED` | `ALLOWED` |
| `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |

**REJECTED always has veto power.** An allowing filter cannot override a rejection decision from the other filter.

Example combining an allow-list with resource limits:

```java
import java.io.ObjectInputFilter;

ObjectInputFilter classFilter = ObjectInputFilter.allowFilter(
        type -> type == UserSnapshot.class
                || type == String.class,
        ObjectInputFilter.Status.REJECTED
);

ObjectInputFilter resourceFilter = info -> {
    if (info.depth() > 20
            || info.references() > 2_000
            || info.streamBytes() > 1_000_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter combined = ObjectInputFilter.merge(
        classFilter,
        resourceFilter
);
```

Results:

- Class in allow-list and within limits: `ALLOWED`.
- Class not in allow-list: `REJECTED`.
- Any resource limit exceeded: `REJECTED`.
- Check without a class and within limits: `UNDECIDED`.

Separating filters by responsibility makes code easier to understand: one filter manages classes, one manages resources.

## 10. Using `rejectUndecidedClass()` to Close an Allow-List Policy

`ObjectInputFilter.rejectUndecidedClass(filter)` creates a wrapper around the original filter and converts `UNDECIDED` results into `REJECTED` for classes not yet accepted, with special handling for classless checks and arrays.

Example:

```java
ObjectInputFilter partialFilter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == UserSnapshot.class || type == String.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter strictFilter =
        ObjectInputFilter.rejectUndecidedClass(partialFilter);
```

When using `strictFilter`:

- Explicitly accepted classes remain `ALLOWED`.
- Classes not decided by the filter are converted to `REJECTED`.
- Checks without a class can remain `UNDECIDED` so another filter can evaluate resource limits.
- Arrays are checked by their base component type; primitive arrays have special rules.

This is useful when the underlying filter only explicitly marks allowed classes and leaves remaining classes undecided.

### Why Not Simply Convert Every `UNDECIDED` to `REJECTED`?

A filter can be invoked when there is no class to check, yet depth, references, and stream bytes are still present. Turning every `UNDECIDED` into `REJECTED` unconditionally would reject resource-only checks on which a class-based filter has no opinion.

`rejectUndecidedClass` is designed to focus on class decisions and handle arrays/primitives specially, rather than mechanically swapping enum values.

## 11. Combining Allow-List, Deny-List, and Resource Filters

A policy often needs multiple parts:

- An allow-list for permitted application classes.
- A deny-list for certain unacceptable class categories.
- A resource filter for depth, references, stream bytes, and array length.

Example:

```java
import java.io.ObjectInputFilter;
import java.lang.reflect.Proxy;

ObjectInputFilter allowApplicationTypes =
        ObjectInputFilter.allowFilter(
                type -> type == UserSnapshot.class
                        || type == String.class,
                ObjectInputFilter.Status.UNDECIDED
        );

ObjectInputFilter rejectProxyTypes =
        ObjectInputFilter.rejectFilter(
                Proxy::isProxyClass,
                ObjectInputFilter.Status.UNDECIDED
        );

ObjectInputFilter resourceLimits = info -> {
    if (info.depth() > 20
            || info.references() > 2_000
            || info.streamBytes() > 1_000_000
            || (info.arrayLength() >= 0
                && info.arrayLength() > 100_000)) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter combined = ObjectInputFilter.merge(
        allowApplicationTypes,
        rejectProxyTypes
);

combined = ObjectInputFilter.merge(combined, resourceLimits);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(combined);
```

In this example:

- `allowApplicationTypes` confirms allowed application types.
- `rejectProxyTypes` vetoes proxy classes.
- `resourceLimits` rejects object graphs exceeding limits.
- `rejectUndecidedClass` converts classes not explicitly accepted into rejections.

If the allow-list filter is created with `otherStatus = REJECTED`, classes outside the list are already rejected immediately; in that case the `rejectUndecidedClass` wrapper may be unnecessary for ordinary class decisions. Choose a consistent way of expressing policy so readers clearly see where rejection responsibility lies.

## 12. Attaching a Filter to `ObjectInputStream`

You can attach a per-stream filter using `setObjectInputFilter()`. Set the filter before calling `readObject()`:

```java
import java.io.ByteArrayInputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

static Object readFiltered(byte[] bytes)
        throws Exception {

    try (ObjectInputStream input = new ObjectInputStream(
            new ByteArrayInputStream(bytes))) {

        input.setObjectInputFilter(createFilter());

        return input.readObject();
    }
}
```

The filter is applied while the stream reads the object graph. If a class is rejected, reading fails instead of returning that object to the application.

A stream-specific filter is useful when each data stream has a different set of valid classes. For example, a stream importing user profiles needs only certain DTOs, while a stream importing configuration may need other types.

Do not wait until after reading an object to set the filter. The filter must be active during deserialization to prevent disallowed classes or structures from being restored.

## 13. Complete Example: Reading Only an Allowed Record

The following example writes a `UserSnapshot` to a byte array, then reads it back with an allow-list filter.

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class AllowedRecordDemo {

    record UserSnapshot(String username, int level)
            implements Serializable {
    }

    static byte[] serialize(Object value) throws Exception {
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(buffer)) {

            output.writeObject(value);
            return buffer.toByteArray();
        }
    }

    static ObjectInputFilter createFilter() {
        return ObjectInputFilter.allowFilter(
                type -> type == UserSnapshot.class
                        || type == String.class,
                ObjectInputFilter.Status.REJECTED
        );
    }

    static Object deserialize(byte[] bytes) throws Exception {
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {

            input.setObjectInputFilter(createFilter());
            return input.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = serialize(new UserSnapshot("lan", 3));

        Object restored = deserialize(bytes);

        System.out.println(restored);
    }
}
```

Output:

```text
UserSnapshot[username=lan, level=3]
```

The filter accepts the specified record. If the stream contains another class outside the policy, the filter returns `REJECTED` and reading is blocked.

The example illustrates a simple object graph. In a real application, you need to list every type that may be validly read; never assume an allow-list containing only the root record will suffice for all object structures.

## 14. Example Rejecting a Class Outside the Allow-List

Rejection can be demonstrated by serializing a different class and using a filter that allows only `UserSnapshot`.

```java
import java.io.Serializable;

record AdminCommand(String command) implements Serializable {
}
```

Suppose the filter only allows:

```java
ObjectInputFilter filter = ObjectInputFilter.allowFilter(
        type -> type == UserSnapshot.class
                || type == String.class,
        ObjectInputFilter.Status.REJECTED
);
```

If the stream contains `AdminCommand`, the predicate returns `false` for that class. `otherStatus` is `REJECTED`, so the filter rejects it.

Errors can be handled at the reading boundary:

```java
try (ObjectInputStream input = new ObjectInputStream(
        new ByteArrayInputStream(bytes))) {

    input.setObjectInputFilter(filter);

    Object value = input.readObject();
    System.out.println(value);

} catch (java.io.InvalidClassException ex) {
    System.err.println("Object rejected by filter: " + ex.getMessage());
}
```

Do not catch the error, ignore it, and continue processing an unread object. Record the rejection event and return an appropriate error to the calling layer.

## 15. Using Pattern Filters from `ObjectInputFilter.Config.createFilter()`

Besides custom filters via lambdas, Java supports creating filters from a pattern string:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=2000;maxbytes=1000000;"
                + "maxarray=100000;"
                + "com.example.dto.**;!*"
);
```

Components:

| Pattern | Meaning |
| --- | --- |
| `maxdepth=20` | Limits object graph depth. |
| `maxrefs=2000` | Limits number of references. |
| `maxbytes=1000000` | Limits bytes read from stream. |
| `maxarray=100000` | Limits array length. |
| `com.example.dto.**` | Allows classes in that package and its subpackages. |
| `!*` | Rejects remaining classes if not matched by an earlier allow pattern. |

For class patterns, patterns are evaluated left to right; the first matching pattern determines the status for the class. Resource limits are checked and can return `REJECTED` if thresholds are exceeded.

Distinguishing wildcards:

- `com.example.dto.*` matches classes directly in that package.
- `com.example.dto.**` matches classes in that package and subpackages.
- `!com.example.dto.Internal` rejects the specific class.
- `!*` rejects remaining classes if not accepted by an earlier pattern.

A pattern filter returns `UNDECIDED` if no class pattern matches and no limits are exceeded. If a strict allow-list policy is desired, a trailing rejection pattern like `!*` makes the decision explicit for remaining classes.

Package and module names in patterns must match actual classes. Do not add a broad wildcard just to make tests pass without understanding which classes will be accepted.

## 16. Installing a JVM-Wide Filter

For applications needing a common policy, a JVM-wide filter can be configured via a system property:

```bash
java -Djdk.serialFilter="maxdepth=20;maxrefs=2000;maxbytes=1000000;com.example.dto.**;!*" -m com.example.app/com.example.Main
```

Or configured via the API:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=2000;maxbytes=1000000;"
                + "com.example.dto.**;!*"
);

ObjectInputFilter.Config.setSerialFilter(filter);
```

The JVM-wide filter applies at the Java process scope and must be set according to the startup lifecycle. If a global filter has already been configured elsewhere, setting it again may be rejected. Manage configuration in one clear initialization point.

A global filter is useful when you want a baseline policy for the entire application. For flows with different contexts, per-stream filters or a filter factory may be needed.

## 17. Filter Factories and Context in Java 17

Java 17 adds a filter factory mechanism under JEP 415 so applications can select or combine filters based on the context creating an `ObjectInputStream`.

`ObjectInputFilter.Config.setSerialFilterFactory(...)` accepts a `BinaryOperator<ObjectInputFilter>` to decide the new filter from the current filter and the requested filter.

Conceptual configuration example:

```java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

BinaryOperator<ObjectInputFilter> factory =
        (currentFilter, requestedFilter) -> {
            if (currentFilter == null) {
                return requestedFilter;
            }

            return ObjectInputFilter.merge(
                    currentFilter,
                    requestedFilter
            );
        };

ObjectInputFilter.Config.setSerialFilterFactory(factory);
```

This is a conceptual example of combining filters. A real policy needs to handle both filters being `null`, the global filter, thread/context filters, and how the application wants to handle `UNDECIDED`.

The filter factory is invoked when a stream's filter is set or updated per `ObjectInputStream`'s mechanism. It enables the application to bring context-specific policies into deserialization, for example:

- Input streams from service A only allow A types.
- Input streams from configuration files only allow configuration types.
- Streams created by a module/framework may require a separate filter.
- A global filter always enforces resource limits, while per-stream filters decide classes by context.

Do not install a factory arbitrarily inside a shared library because this configuration affects deserialization across the application. Let the application own the policy and configure the factory at a single initialization point.

## 18. Common Mistakes When Using the Three Statuses

| Mistake | Why It Is a Problem | How to Handle |
| --- | --- | --- |
| Returning `UNDECIDED` for all unlisted classes | Unlisted classes may still be read if no other filter rejects. | Return `REJECTED` or use `rejectUndecidedClass`. |
| Thinking `ALLOWED` overrides all other filters | In `merge`, a `REJECTED` result still vetoes. | Review combination policy; `REJECTED` takes rejection precedence. |
| Returning `REJECTED` when `serialClass()` is null without checking resources | Class-based filters may wrongly reject metrics-only checks. | Check depth/references/bytes first; then return `UNDECIDED` if there is no class. |
| Not limiting array length | Large arrays can cause significant memory consumption. | Check `arrayLength()`. |
| Checking only classes, ignoring graph limits | A valid class can still appear in an overly deep or large graph. | Combine allow-list with resource filters. |
| Using a small deny-list as an allow-list | Classes not matching the deny-list can still receive `UNDECIDED`. | Write an explicit allow-list and reject unlisted classes. |
| Returning `null` from `checkInput()` | Violates API contract and can cause unpredictable errors. | Always return one of the three statuses. |
| Setting filter after `readObject()` | The object graph has already been deserialized before the filter takes effect. | Attach the filter before reading objects. |
| Allowing overly broad packages | Many unneeded classes may be read. | Restrict to specific classes/packages and test valid object graphs. |
| Treating filters as business validation | Filters control classes and resources, not whether data makes business sense. | Validate data after reading using application validators. |

## 19. Filters Do Not Replace Validation and Authentication

An object can belong to an allowed class yet contain invalid values:

```java
record UserSnapshot(String username, int level)
        implements java.io.Serializable {
}
```

For example, the stream contains:

```java
new UserSnapshot("", -100)
```

The filter may accept `UserSnapshot` because that class is in the allow-list. However, that does not prove:

- `username` is non-empty.
- `level` is within a valid range.
- The sender has permission to create or update that user.
- The data belongs to the right tenant or user.
- The object contains no forged information.

After reading the object, the application still must validate data and check business permissions:

```java
static void validate(UserSnapshot user) {
    if (user.username() == null || user.username().isBlank()) {
        throw new IllegalArgumentException("invalid username");
    }

    if (user.level() < 0 || user.level() > 10) {
        throw new IllegalArgumentException("level out of range");
    }
}
```

The filter decides **whether Java is allowed to reconstruct this type/object graph**. Validation decides **whether the read data is valid for the application**. Authorization decides **whether the sender is permitted to perform the corresponding action**.

These three control layers have distinct roles and do not replace one another.

## 20. When Should Java Object Deserialization Be Avoided?

Serialization Filtering reduces risk when an application must read Java serialized data, but it does not turn untrusted data into something completely safe.

When designing a new system, consider data-only formats like JSON, Protocol Buffers, or an explicit schema, along with parsers that have size limits and proper validation. Those formats still require input validation, but they do not arbitrarily reconstruct Java object graphs via the native serialization mechanism.

If Java Object Serialization must continue to be used:

- Do not read untrusted serialized data without an appropriate filter.
- Use per-use-case allow-lists.
- Set limits on depth, references, bytes, and array length.
- Reject unexpected classes.
- Validate data after reading.
- Do not treat filters as sender authentication.
- Manage global and per-stream/context filters in one clear place.

`ObjectInputFilter` and filter factory APIs remain the current mechanisms in JDK 17. Avoid relying on legacy workarounds like disabling module checks or altering JVM-wide security mechanisms to allow arbitrary objects to be read.

## 21. Practice Exercises

### Exercise 1 — Distinguish the Three Statuses

Write a filter receiving `FilterInfo`:

- Return `ALLOWED` for `UserSnapshot.class`.
- Return `REJECTED` for `AdminCommand.class`.
- Return `UNDECIDED` for other classes.

Explain what happens if this filter is used alone and the stream contains a third class.

### Exercise 2 — Resource Limits

Write a filter that rejects if:

- `depth()` is greater than 10.
- `references()` is greater than 1,000.
- `streamBytes()` is greater than 500,000.
- `arrayLength()` is greater than 50,000.

If no limit is violated, return `UNDECIDED` so another filter can decide on classes.

### Exercise 3 — Using allowFilter

Create an `allowFilter` accepting only `UserSnapshot.class` and `String.class`, using `REJECTED` as the fallback status. Try deserializing an object of another class and observe the error.

### Exercise 4 — Using rejectFilter

Create a filter rejecting proxy classes using `Proxy.isProxyClass`, returning `UNDECIDED` for other classes. Explain why this filter is not yet an allow-list.

### Exercise 5 — Combining Filters

Create a class filter and a resource filter, then combine them with `ObjectInputFilter.merge()`. Verify the truth table when one filter allows while the other rejects.

### Exercise 6 — Strict Allow-List

Create a filter that returns `ALLOWED` only for a specified class and `UNDECIDED` for other classes. Wrap it with `rejectUndecidedClass()`. Compare its behavior with the unwrapped filter.

### Exercise 7 — Pattern Filter

Create a filter with `Config.createFilter()` setting depth, references, bytes limits, and a package pattern. Add a trailing reject pattern so non-matching classes are blocked. Test a class inside the allowed package and one outside it.

### Exercise 8 — Filter Before Reading

Serialize a record, then create an `ObjectInputStream`, call `setObjectInputFilter()` before `readObject()`, and read it back. Try changing the filter to a policy rejecting the record to observe the behavior.

## 22. Quick Reference

| Need | How to Do It |
| --- | --- |
| Accept the check | Return `ObjectInputFilter.Status.ALLOWED`. |
| Reject the check | Return `ObjectInputFilter.Status.REJECTED`. |
| Filter has no opinion | Return `ObjectInputFilter.Status.UNDECIDED`. |
| Read class being checked | `info.serialClass()`. |
| Limit depth | Check `info.depth()`. |
| Limit reference count | Check `info.references()`. |
| Limit byte count | Check `info.streamBytes()`. |
| Limit array length | Check `info.arrayLength()`. |
| Create predicate allow-list filter | `ObjectInputFilter.allowFilter(...)`. |
| Create predicate deny-list filter | `ObjectInputFilter.rejectFilter(...)`. |
| Combine two filters | `ObjectInputFilter.merge(filter1, filter2)`. |
| Reject remaining undecided classes | `ObjectInputFilter.rejectUndecidedClass(filter)`. |
| Create filter from pattern | `ObjectInputFilter.Config.createFilter(pattern)`. |
| Attach filter to stream | `objectInputStream.setObjectInputFilter(filter)`. |
| Configure JVM-wide filter | `ObjectInputFilter.Config.setSerialFilter(filter)` or system property `jdk.serialFilter`. |
| Select filter by context | Filter factory in Java 17. |

**Core principle:** `ALLOWED` is an acceptance decision, `REJECTED` is a rejection decision, and `UNDECIDED` only means the current filter has not made a decision. When building an allow-list, do not let unknown classes fall into `UNDECIDED` without a subsequent rejection mechanism. Combine class checks with resource limits, attach filters before reading objects, and continue validating data after deserialization.
