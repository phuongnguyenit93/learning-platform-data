# Testing Rejections, Excessive Resources, and Context-Specific Policies in Java 17 Deserialization

**Topic:** Java 17  
**Chapter:** Deserialization Filters  
**Lesson:** Testing Rejections, Excessive Resources, and Context-Specific Policies

Java serialization can reconstruct an object graph from a byte stream. When data crosses from outside a trust boundary, calling `ObjectInputStream.readObject()` without limits can cause the application to instantiate unwanted classes or consume excessive memory, CPU, and other resources.

Java provides **serialization filters** via `java.io.ObjectInputFilter` to control deserialization. A filter can inspect the class being read along with object graph metrics such as depth, reference count, array size, and bytes read. It can accept, reject, or defer the decision to another filter.

Java 17 also features context-specific filter factories, standardized via JEP 415. A factory lets you select or combine policies suited to each deserialization stream—for example, by application function, module, class loader, or request context.

This lesson focuses on three tasks needed in a real system:

- **Testing rejections:** proving data containing disallowed classes is rejected before the application uses the object.
- **Resource limits:** setting thresholds on depth, references, array length, and stream bytes to reduce excessive resource consumption risk.
- **Context-specific policies:** applying distinct allowlists and limits for each data type while preserving the application's baseline policy.

Filters are an important defense layer, yet do not turn Java native serialization into a safe format for untrusted data. Whenever possible, prefer data formats with schemas and parsers designed for external input.

## 1. What Do Serialization Filters Control?

A serialized object can hold references to many other objects. When calling `readObject()`, `ObjectInputStream` reconstructs the *object graph* from the data stream.

Example of a simple message:

```java
import java.io.Serializable;

public final class Message implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String text;

    public Message(String text) {
        this.text = text;
    }

    public String text() {
        return text;
    }
}
```

A `Message` object can reference `String`; another object might contain lists, maps, arrays, or nested objects. If the application does not restrict class types and graph sizes, input data can demand processing structures beyond business needs.

`ObjectInputFilter` is invoked during deserialization to make decisions based on information about the item currently being processed.

### 1.1. The Three Filter Statuses

`ObjectInputFilter.Status` has three values:

| Status | Meaning |
|---|---|
| `ALLOWED` | This filter permits the current object/condition |
| `REJECTED` | This filter rejects; reading is aborted |
| `UNDECIDED` | This filter has not made a decision |

`UNDECIDED` does not mean confirmed safe. It merely states the current filter made no decision. Another filter, composite filter, or stream default behavior may still decide.

Therefore, a strict allowlist needs explicit handling for unlisted classes. In Java 17, `ObjectInputFilter.rejectUndecidedClass(filter)` can convert `UNDECIDED` results for classes into `REJECTED`.

### 1.2. Information the Filter Receives

`ObjectInputFilter.FilterInfo` provides key details:

| Method | Information | Special Value |
|---|---|---|
| `serialClass()` | Class being deserialized | May be `null` when there is no new class to consider |
| `arrayLength()` | Current array length | `-1` if the current object is not an array |
| `depth()` | Current depth of the object graph | Larger numbers indicate deeper nesting |
| `references()` | Number of object references processed | Increases as the stream is read |
| `streamBytes()` | Number of bytes read from the stream | Total bytes consumed at the time of inspection |

These metrics help filters limit both **data types** and **data scale**. Never assume `serialClass()` is always non-null; filters must handle cases where there is no class to decide on.

## 2. Setting Resource Limits

A filter can reject an object graph when any of these thresholds is exceeded:

- Maximum depth: avoids overly deep nested structures.
- Maximum references: bounds the number of object references the stream requests to process.
- Maximum array size: prevents arrays whose element counts exceed business capacity.
- Maximum bytes: bounds the amount of serialization data consumed.

Example of a resource-limiting policy:

```java
import java.io.ObjectInputFilter;

final class SerializationLimits {
    static final long MAX_DEPTH = 20;
    static final long MAX_REFERENCES = 10_000;
    static final long MAX_ARRAY_LENGTH = 100_000;
    static final long MAX_STREAM_BYTES = 1_048_576; // 1 MiB

    static final ObjectInputFilter FILTER = info -> {
        if (info.depth() > MAX_DEPTH
                || info.references() > MAX_REFERENCES
                || info.arrayLength() > MAX_ARRAY_LENGTH
                || info.streamBytes() > MAX_STREAM_BYTES) {
            return ObjectInputFilter.Status.REJECTED;
        }

        return ObjectInputFilter.Status.UNDECIDED;
    };
}
```

The filter returns `REJECTED` when any threshold is exceeded. If none is exceeded, it returns `UNDECIDED` so another policy can inspect classes.

The numbers above are examples only. Actual quotas must be based on valid payload sizes, object graph structures, available memory, and business requirements. No single set of thresholds fits every application.

### 2.1. Why Are Multiple Limits Needed Simultaneously?

Limiting stream bytes alone is insufficient:

- A modest-sized payload can still contain a very deeply nested graph.
- An array can declare a huge element count and create memory pressure.
- Many tiny objects can cause reference counts to rise rapidly.
- A deeply nested structure can increase processing cost or trigger stack overflow in application code.

Combining multiple metrics helps the policy cover different forms of resource consumption.

### 2.2. Meaning of Threshold Comparisons

Conditions commonly use `> MAX`, meaning values equal to the threshold are permitted while exceeding the threshold is rejected.

For example, with `MAX_DEPTH = 20`:

- `depth() == 20`: does not exceed the limit.
- `depth() == 21`: is rejected.

Document clearly in configuration docs that thresholds are inclusive upper bounds. If business requirements call for rejecting as soon as the threshold is reached, the condition differs.

### 2.3. Limits Do Not Replace Protocol-Layer Bounds

`streamBytes()` measures bytes consumed by `ObjectInputStream` when the filter is called. Applications should still limit request or file sizes before starting deserialization—for example, upload limits on HTTP servers or checking file size.

Apply defense in depth across multiple layers:

1. Limit input size before creating the stream.
2. Bound depth, references, arrays, and stream bytes with a serialization filter.
3. Allow only required classes.
4. Validate business data after deserialization.
5. Enforce timeouts and resource limits at the request/worker layer if work can be time-consuming.

Filters are not general CPU limiters and cannot replace process-level timeouts, quotas, or memory limits.


## 3. Controlling Classes with an Allowlist

Resource limits are insufficient if all classes are allowed. Policies should accept only classes the data protocol genuinely requires.

For example, an endpoint receives only `Message` with a `String` field. You can write a filter allowing those two classes and rejecting others.

```java
import java.io.ObjectInputFilter;
import java.util.Set;

final class MessagePolicy {
    private static final Set<Class<?>> ALLOWED =
            Set.of(Message.class, String.class);

    static final ObjectInputFilter FILTER = info -> {
        Class<?> type = info.serialClass();

        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (ALLOWED.contains(type)) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
```

Exact allowlists are usually easier to control than denylists. Denylists eliminate only classes already known to be dangerous; a new class or a class nested inside the object graph can still slip through.

### 3.1. Handling Arrays in Allowlists

If the protocol permits arrays, explicitly decide which element types are accepted. Do not allow all arrays merely because their class is an array.

Example accepting primitive arrays and String arrays:

```java
static boolean isAllowedArray(Class<?> type) {
    if (!type.isArray()) {
        return false;
    }

    Class<?> component = type;
    while (component.isArray()) {
        component = component.getComponentType();
    }

    return component.isPrimitive() || component == String.class;
}
```

Combined with class checks:

```java
static ObjectInputFilter classFilter() {
    return info -> {
        Class<?> type = info.serialClass();

        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (ALLOWED.contains(type) || isAllowedArray(type)) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
```

Arrays must still obey `arrayLength()` limits. Accepting the `byte[]` type does not mean allowing byte arrays of arbitrary size.

### 3.2. Allowlists Must Reflect the Entire Object Graph

When an allowed class has fields referencing other classes, those classes must be accounted for too. For instance, `Message` may reference `String`; another DTO may contain `List`, list elements, enums, or arrays.

Do not broadly add entire standard-library packages just to get a deserialization example running. Identify the exact required structure and test with real valid object graphs.

## 4. Combining Filters via Java 17 APIs

Java 17 provides two useful static methods on `ObjectInputFilter`:

- `merge(filterA, filterB)`: combines two filters.
- `rejectUndecidedClass(filter)`: rejects a class if the inner filter returns `UNDECIDED`.

Combination rules for `merge`:

- If either filter returns `REJECTED`, the result is `REJECTED`.
- If neither rejects and at least one returns `ALLOWED`, the result is `ALLOWED`.
- If both are `UNDECIDED`, the result is `UNDECIDED`.

This lets you split policies into two readable parts: a resource-limit filter and a class-checking filter.

```java
ObjectInputFilter limits = SerializationLimits.FILTER;
ObjectInputFilter classes = MessagePolicy.classFilter();

ObjectInputFilter combined =
        ObjectInputFilter.merge(limits, classes);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(combined);
```

The `strict` filter rejects classes not accepted by the allowlist, while still rejecting immediately when the resource-limit filter reports exceeded thresholds.

### 4.1. Why Is rejectUndecidedClass Useful?

A filter might return `UNDECIDED` for an unlisted class because it has no responsibility for deciding that class. Without another filter rejecting, reading of the class can proceed.

When a policy is designed as an allowlist, an undecided result for a class should normally be treated as disallowed. `rejectUndecidedClass` turns that rule into an explicit wrapper.

Note: this wrapper converts `UNDECIDED` to `REJECTED` only when there is a class to examine. When `serialClass()` is null, it can preserve `UNDECIDED` so other filters can evaluate resource metrics.

## 5. Using Pattern Filters from Configuration

Besides writing lambdas, Java provides `ObjectInputFilter.Config.createFilter(String pattern)` to construct filters from pattern strings. This is useful when configuring policies without writing separate Java classes.

Example:

```java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;"
      + "maxrefs=10000;"
      + "maxbytes=1048576;"
      + "maxarray=100000;"
      + "!com.example.dto.LegacyPayload;"
      + "com.example.dto.**;"
      + "java.lang.String;"
      + "!*"
);
```

Some pattern components:

| Pattern | Meaning |
|---|---|
| `maxdepth=20` | Reject when depth exceeds 20 |
| `maxrefs=10000` | Reject when references exceed 10,000 |
| `maxbytes=1048576` | Reject when stream bytes exceed 1 MiB |
| `maxarray=100000` | Reject arrays with length exceeding 100,000 |
| `com.example.dto.*` | Match classes directly in that package |
| `com.example.dto.**` | Match classes in that package and subpackages |
| `!com.example.dto.LegacyPayload` | Reject the specified class |
| `!*` | Reject classes not matching earlier allow patterns |

Class patterns are evaluated in order; the first matching pattern decides the status for the class. Therefore, if a class inside an allowed package must be rejected, place the specific rejection pattern before the broader package pattern.

### 5.1. Pattern Filters Do Not Replace Business Structure Checks

Pattern filters can control classes and general limits, yet complex business policies often require custom filters. For example, the same DTO class might be valid in one request type yet invalid in another.

Furthermore, broad package patterns can accidentally allow new classes added to that package in the future. For untrusted data, exact-class allowlists are usually easier to audit.

### 5.2. Pattern Configuration Errors

`createFilter` parses the pattern string and can throw `IllegalArgumentException` if misconfigured. Build filters at application startup to catch configuration errors early, rather than waiting until the first request arrives.

Never silently replace a broken filter with an allow-all policy. If security configuration is invalid, the application should fail configuration startup and refuse to start the affected deserialization flow.

## 6. Attaching Filters to ObjectInputStream

Per-stream filters are set via `ObjectInputStream.setObjectInputFilter(filter)`. Set the filter before the first `readObject()` call.

```java
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

static Object readMessage(byte[] serialized) throws IOException, ClassNotFoundException {
    try (ObjectInputStream input =
                 new ObjectInputStream(new ByteArrayInputStream(serialized))) {

        input.setObjectInputFilter(MessagePolicy.strictFilter());

        return input.readObject();
    }
}
```

The filter applies while reading the object graph. If the filter rejects, deserialization aborts and typically throws `InvalidClassException` containing filter status details.

Do not wait until deserialization finishes to set the filter. Once the object graph has been constructed, setting the filter late cannot protect reads that already occurred.

### 6.1. Checking the Attached Filter

You can read the stream's current filter using `getObjectInputFilter()`:

```java
ObjectInputFilter current = input.getObjectInputFilter();
System.out.println(current);
```

This helps when diagnosing configuration. Do not log sensitive contents of the object graph just to confirm a filter was installed.

### 6.2. JVM-Wide Filter

A global filter can be configured via `ObjectInputFilter.Config.setSerialFilter(filter)` or the `jdk.serialFilter` JVM property at startup.

A global filter establishes a baseline protection layer for `ObjectInputStream`s in the process. It should be configured early, typically during application bootstrap, because the global API has a one-time setup rule.

An overly strict global filter can break valid serialization flows of other libraries. Inventory all use cases before deploying and combine with per-stream policies when needed.

## 7. Testing Rejection of Disallowed Classes

A policy is only valuable when tests prove it rejects data outside the allowlist.

Example of a disallowed class:

```java
import java.io.Serializable;

final class UnexpectedPayload implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String value = "unexpected";
}
```

Serialization helper for testing:

```java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.ObjectOutputStream;

static byte[] serialize(Object value) throws IOException {
    try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
         ObjectOutputStream output = new ObjectOutputStream(bytes)) {
        output.writeObject(value);
        output.flush();
        return bytes.toByteArray();
    }
}
```

Testing rejection:

```java
import java.io.ByteArrayInputStream;
import java.io.InvalidClassException;
import java.io.ObjectInputStream;

byte[] data = serialize(new UnexpectedPayload());

try (ObjectInputStream input =
             new ObjectInputStream(new ByteArrayInputStream(data))) {

    input.setObjectInputFilter(MessagePolicy.strictFilter());

    try {
        input.readObject();
        throw new AssertionError("Classes outside allowlist must be rejected");
    } catch (InvalidClassException expected) {
        System.out.println("Rejected as expected: " + expected.getMessage());
    }
}
```

When a class is not accepted by the allowlist, the filter returns `REJECTED` and `readObject()` does not return that object. This is a *negative test*: confirming invalid data is blocked.

Do not test only by calling the filter lambda directly. Test through a real `ObjectInputStream` to verify the filter is attached at the right time and the expected exception is thrown.


## 8. Testing Excessive Resource Limits

Alongside unknown classes, test object graphs that exceed limits. Tests should cover each metric individually rather than relying on one combined case.

| Scenario | Test Data | Expectation |
|---|---|---|
| Depth too large | Deeply nested objects | `REJECTED` when exceeding `MAX_DEPTH` |
| References too high | Graph with many objects | `REJECTED` when exceeding `MAX_REFERENCES` |
| Array too large | Array longer than threshold | `REJECTED` when exceeding `MAX_ARRAY_LENGTH` |
| Stream too large | Serialization payload exceeding byte budget | `REJECTED` when exceeding `MAX_STREAM_BYTES` |
| Class outside allowlist | Object of a disallowed class | `REJECTED` |
| Valid payload within limits | Allowed DTO of valid size | Deserialized successfully |

### 8.1. Testing Array Exceeding Limits

Suppose a filter permits primitive arrays but caps length at 256:

```java
static ObjectInputFilter arrayLimit(long maxLength) {
    return info -> {
        if (info.arrayLength() > maxLength) {
            return ObjectInputFilter.Status.REJECTED;
        }

        return ObjectInputFilter.Status.UNDECIDED;
    };
}
```

Test data:

```java
byte[] serialized = serialize(new byte[1024]);

try (ObjectInputStream input =
             new ObjectInputStream(new ByteArrayInputStream(serialized))) {

    input.setObjectInputFilter(arrayLimit(256));

    try {
        input.readObject();
        throw new AssertionError("Oversized array must be rejected");
    } catch (InvalidClassException expected) {
        System.out.println("Array limit enforced");
    }
}
```

The filter is invoked when the array is read and can reject based on `arrayLength()` before the application uses that array.

### 8.2. Testing Depth and References

You can create test classes with nested links or many referenced nodes to construct object graphs exceeding thresholds. Example node structure:

```java
final class Node implements Serializable {
    private static final long serialVersionUID = 1L;

    Node next;
    String value;
}
```

Build a node chain longer than the depth limit and serialize it as a test fixture. For references, build an object graph containing many distinct nodes or referenced elements.

There is no need to hard-code a dangerous payload in tests. Just use deterministic, finite fixtures proving the filter rejects right at the threshold.

### 8.3. Testing Byte Budget

`streamBytes()` grows as `ObjectInputStream` consumes data. A payload larger than the budget must be rejected when the filter is called and bytes read exceed the threshold.

Test all of these cases:

- Valid payload smaller than the threshold.
- Payload right at the threshold (if the policy allows equality).
- Payload slightly exceeding the threshold.
- Payload containing many small objects whose total bytes are large.

Byte limits do not replace array or depth limits; tests must verify each dimension separately.

## 9. Positive and Negative Tests in the Same Test Suite

A good test suite must verify both permitted data and rejected data. Testing only rejections can leave a policy so strict that valid payloads fail. Testing only acceptances can allow unallowlisted classes to slip through.

Recommended test matrix:

| Test Group | Data | Expected Outcome |
|---|---|---|
| Positive: valid DTO | `Message` with `String` | Deserializes successfully |
| Negative: unknown class | `UnexpectedPayload` | `InvalidClassException` |
| Negative: large array | `byte[]` exceeding threshold | `InvalidClassException` |
| Negative: high depth | Overly deep `Node` chain | `InvalidClassException` |
| Negative: many references | Graph with many objects | `InvalidClassException` |
| Negative: large stream | Byte stream exceeding budget | `InvalidClassException` |
| Boundary: at threshold | Data exactly at limit | Per chosen `>` or `>=` rule |
| Regression | Existing valid payloads | Continues to deserialize |

### 9.1. Ensuring Tests Prove the Filter Actually Ran

A negative test can fail due to a corrupted payload, a missing class on the classpath, or a `serialVersionUID` mismatch. Those failures do not prove the filter rejected it.

To make tests meaningful:

1. Generate valid payloads using the same test fixture classes.
2. Confirm the payload deserializes when using a permissive filter.
3. Read that exact same payload with the restrictive policy.
4. Verify the operation fails due to filter rejection.
5. Keep a positive test ensuring the policy allows the required classes.

### 9.2. Do Not Use Sensitive Production Data as Fixtures

Filter tests should use synthetic, reproducible classes and data. Never put session tokens, personal information, or real customer payloads into test fixtures or error logs.

## 10. Context-Specific Policies with JEP 415

A large application can have many deserialization flows with different purposes:

- Reading messages from an internal protocol.
- Loading saved caches.
- Restoring task state.
- Reading legacy compatibility config files.
- Receiving payloads from a plugin component.

A single global filter can be too broad for some flows and too strict for others. Java 17 adds **serialization filter factories** via JEP 415 to choose or combine filters per `ObjectInputStream`.

The factory is configured JVM-wide via `ObjectInputFilter.Config.setSerialFilterFactory(...)`. It receives the current filter and requested filter, returning the filter to be used.

### 10.1. The Factory Receives Two Filters

The factory signature uses `BinaryOperator<ObjectInputFilter>`:

```java
ObjectInputFilter.Config.setSerialFilterFactory(
        (currentFilter, requestedFilter) -> {
            // Select or combine filters per application policy.
            return requestedFilter;
        }
);
```

General meaning:

- `currentFilter` is the filter currently applied to the stream; when creating a new stream, this value may be null.
- `requestedFilter` is the filter requested at the factory call site, coming from global configuration or a stream filter assignment.
- The return value is the filter applied after the factory runs.

The factory is called when `ObjectInputStream` is created and when the stream requests changing its filter via `setObjectInputFilter`. Because the factory decides whether to combine or replace filters, it is the central point for policy enforcement.

### 10.2. Combining Filters Without Losing the Baseline Policy

If the application needs to keep both the current filter and the requested filter, use `ObjectInputFilter.merge`:

```java
ObjectInputFilter.Config.setSerialFilterFactory(
        (currentFilter, requestedFilter) -> {
            if (currentFilter == null) {
                return requestedFilter;
            }

            if (requestedFilter == null) {
                return currentFilter;
            }

            return ObjectInputFilter.merge(
                    currentFilter,
                    requestedFilter
            );
        }
);
```

When merging, any filter returning `REJECTED` causes the outcome to be rejected. One filter cannot override the other filter's rejection decision by returning `ALLOWED`.

This is a critical property when combining an application-wide baseline policy with stream-specific policies.

### 10.3. Selecting Filters by Application Context

JEP 415 enables the factory to pick policies based on application-supplied context. Context can be:

- Type of operation being performed.
- Module or class loader initiating the stream.
- Application component or endpoint.
- Policy attached to the request or thread before creating the stream.
- Stream-specific filter requested by the caller.

Illustrative example using `ThreadLocal` to pass the current operation's policy to the factory. The factory must be installed once during application startup:

```java
import java.io.ObjectInputFilter;

final class ContextFilters {
    private static final ThreadLocal<ObjectInputFilter> CONTEXT =
            new ThreadLocal<>();

    static ObjectInputFilter merge(
            ObjectInputFilter first,
            ObjectInputFilter second) {

        if (first == null) {
            return second;
        }

        if (second == null) {
            return first;
        }

        return ObjectInputFilter.merge(first, second);
    }

    static void installFactory() {
        ObjectInputFilter.Config.setSerialFilterFactory(
                (current, requested) -> {
                    ObjectInputFilter context = CONTEXT.get();

                    ObjectInputFilter combined =
                            merge(current, requested);

                    return merge(combined, context);
                }
        );
    }

    static ObjectInputFilter currentContext() {
        return CONTEXT.get();
    }

    static void setContext(ObjectInputFilter filter) {
        CONTEXT.set(filter);
    }

    static void clearContext() {
        CONTEXT.remove();
    }
}
```

When handling a request, the application sets the policy before creating `ObjectInputStream`:

```java
ObjectInputFilter previous = ContextFilters.currentContext();
ContextFilters.setContext(policyForMessageEndpoint());

try (ObjectInputStream input =
             new ObjectInputStream(sourceStream)) {

    return input.readObject();
} finally {
    if (previous == null) {
        ContextFilters.clearContext();
    } else {
        ContextFilters.setContext(previous);
    }
}
```

The factory retrieves the policy when the stream is created and attaches the corresponding filter to that stream. Restore or clear context in `finally` to prevent a previous request's policy from leaking to the next request on the same thread.

This example illustrates the context-passing mechanism. In asynchronous applications where streams may be created on other threads, pass the policy explicitly via task context rather than assuming thread-locals follow tasks automatically.

### 10.4. The Factory Is a Process-Level Setting

`setSerialFilterFactory` is a JVM-wide setting and can only be set once. Therefore:

- Install it at application bootstrap before streams are created.
- Do not let individual libraries independently swap the factory.
- If multiple components need policies, a central factory must coordinate them.
- Do not unintentionally overwrite an already-configured baseline filter.
- Test the factory in a startup environment matching production.

If a factory was already set by a container or another component, calling it again can fail. That is an application configuration issue and should not be solved by silently dropping the filter.


## 11. Global Filter, Stream Filter, and Filter Factory

The three mechanisms serve distinct roles:

| Mechanism | Scope | Purpose |
|---|---|---|
| Global serial filter | Entire JVM | Baseline policy for streams |
| Stream-specific filter | One `ObjectInputStream` | Specific restrictions for one data flow |
| Filter factory | Entire JVM, called per stream | Select/combine filters by context |

A global filter can be configured via the `jdk.serialFilter` JVM property or the `Config.setSerialFilter` API. Stream-specific filters are set via `setObjectInputFilter`. The factory decides the final filter based on the current filter, requested filter, and application context.

### 11.1. Do Not Let Stream Policies Weaken the Global Policy

If the global filter rejects a class, a stream-specific filter should not be permitted to turn that decision into acceptance. When combining, use `ObjectInputFilter.merge` to ensure any `REJECTED` decision is preserved.

A per-stream policy can add tighter limits for an endpoint. It should not expand permissions in a way that accidentally bypasses process-wide baseline limits.

### 11.2. Choosing Policies by Data Purpose

Examples:

| Context | Suggested Policy |
|---|---|
| Small messages from internal endpoints | Specific DTO allowlist, low depth and bytes |
| Cached objects with known structure | Cache class allowlist, reference and byte limits matched to cache size |
| Large state files | Dedicated allowlist, byte/array limits suited to file format |
| Data from plugins | Per-trusted-plugin policy, tight limits and class loader checks |
| Untrusted data from the Internet | Avoid native Java serialization if possible; if mandatory, very narrow allowlist and multiple limits |

Do not take one endpoint's policy and reuse it across all data types merely because all flows call `readObject()`.

## 12. Analyzing Errors When Filters Reject

When a filter returns `REJECTED`, `ObjectInputStream` typically throws `InvalidClassException`. This exception can appear when a class is rejected or a filter limit is exceeded.

Handling example:

```java
try (ObjectInputStream input =
             new ObjectInputStream(sourceStream)) {

    input.setObjectInputFilter(policy);

    Object value = input.readObject();
    handle(value);

} catch (InvalidClassException rejected) {
    logger.warn("Serialized input rejected by filter", rejected);
}
```

In operational logs, record:

- Endpoint or task type.
- Policy/version used.
- Cause category if determinable: class, depth, references, array, or bytes.
- Non-sensitive request correlation ID.
- Never log full payloads or secret data.

If rejection reasons need to be distinguished, a custom filter can record metrics or events when detecting an invalid threshold/class. Avoid logging a line on every filter invocation since a filter can be invoked very frequently within a single object graph.

### 12.1. Do Not Treat Every InvalidClassException as a Filter Rejection

`InvalidClassException` can also occur due to other serialization issues, such as incompatible classes or mismatched serial versions. When investigating, inspect the message, cause, and origin rather than attributing every error to the filter.

### 12.2. Do Not Continue Processing Objects After Rejection

When `readObject()` fails due to a filter, there is no valid object to pass to the business layer. End the operation, close the stream, and return an appropriate error to the caller.

Do not catch `InvalidClassException` and return a default object without recording the reason; doing so can mask malicious or corrupted input.

## 13. Limitations and Security Principles

Serialization filters reduce risk, yet are not the sole security solution.

### 13.1. Prefer Allowlists Over Denylists

Denylists require knowing every unsafe class in advance. Allowlists permit only classes required by the protocol, making them easier to review and less surprising when dependencies introduce new classes.

Do not broadly allow packages like all of `java.util.*` just to support collections if payloads do not actually need them. Every class added to an allowlist needs a justification.

### 13.2. Do Not Deserialize Untrusted Data If Better Options Exist

Native Java serialization has a long history of security issues involving gadget chains and side effects during object restoration. Filters are a mitigation, not a way to make an arbitrary class ecosystem safe.

For external communication, consider JSON with schemas/validation, Protocol Buffers, or data formats whose parsers are designed around explicit contracts. Choose formats matching compatibility, performance, and security needs.

### 13.3. Filters Do Not Replace Business Validation

Even an object graph containing only allowed classes can still carry invalid values:

- Negative amounts or values exceeding limits.
- Strings too long under business rules.
- Invalid states.
- Non-existent logical references.
- Field combinations violating invariants.

After deserialization, validate data against schemas and business rules before using it.

### 13.4. Do Not Mistake Filters for a Sandbox

`ObjectInputFilter` decides object/class acceptance and serialization metrics. It does not sandbox code, restrict behaviors of methods called after deserialization, or replace OS authorization or process isolation.

## 14. Workflow for Building and Testing Policies

A practical workflow may include:

1. **Inventory valid payloads:** identify classes, arrays, and object graph structures the feature genuinely needs.
2. **Build the allowlist:** allow specific classes, avoiding broad package wildcards unless needed.
3. **Set resource budgets:** choose depth, references, array length, and stream bytes from real data.
4. **Combine policies:** use `merge` for resource limits and class checks; use `rejectUndecidedClass` for strict allowlists.
5. **Attach filter before readObject:** ensure no object is read before the policy takes effect.
6. **Positive testing:** valid payloads still read cleanly.
7. **Negative testing:** unknown classes and each exceeded limit are rejected.
8. **Boundary testing:** values just below, equal to, and exceeding thresholds.
9. **Select policy by context:** use a filter factory if different stream types need different permissions.
10. **Operational monitoring:** count rejections by policy and cause without logging sensitive payloads.

## 15. Combined Example: Strict Policy for Message

The following example combines an allowlist, resource limits, and rejection of undecided classes:

```java
import java.io.ObjectInputFilter;
import java.util.Set;

final class MessagePolicy {

    private static final long MAX_DEPTH = 10;
    private static final long MAX_REFERENCES = 100;
    private static final long MAX_ARRAY_LENGTH = 256;
    private static final long MAX_STREAM_BYTES = 64 * 1024;

    private static final Set<Class<?>> ALLOWED =
            Set.of(Message.class, String.class);

    private static ObjectInputFilter limits() {
        return info -> {
            if (info.depth() > MAX_DEPTH
                    || info.references() > MAX_REFERENCES
                    || info.arrayLength() > MAX_ARRAY_LENGTH
                    || info.streamBytes() > MAX_STREAM_BYTES) {
                return ObjectInputFilter.Status.REJECTED;
            }

            return ObjectInputFilter.Status.UNDECIDED;
        };
    }

    private static ObjectInputFilter classes() {
        return info -> {
            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (ALLOWED.contains(type)) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.UNDECIDED;
        };
    }

    static ObjectInputFilter strictFilter() {
        ObjectInputFilter combined =
                ObjectInputFilter.merge(limits(), classes());

        return ObjectInputFilter.rejectUndecidedClass(combined);
    }
}
```

Usage:

```java
try (ObjectInputStream input =
             new ObjectInputStream(sourceStream)) {

    input.setObjectInputFilter(MessagePolicy.strictFilter());

    Object value = input.readObject();

    if (!(value instanceof Message message)) {
        throw new InvalidObjectException("Expected Message");
    }

    handleMessage(message);
}
```

The filter checks classes and resources while constructing the object graph. Checking the result type after `readObject()` is an extra verification layer for the endpoint contract. In a real system, separate class policy, resource budget, and error handling into independently configurable/testable components.

## 16. Common Mistakes

### Mistake 1. Checking Only Classes Without Resource Limits

Allowlists block unlisted classes, yet do not automatically bound depth, references, arrays, or bytes. Add appropriate thresholds.

### Mistake 2. Limiting Only Bytes

Small payloads can still contain deep object graphs or many references. Use multiple metrics together.

### Mistake 3. Allowing Everything When a Filter Returns UNDECIDED

`UNDECIDED` is not a safety confirmation. With a strict allowlist, use `rejectUndecidedClass` or explicitly return `REJECTED` for unlisted classes.

### Mistake 4. Testing Only Valid Payloads

Test unknown classes, large arrays, depth, references, and stream bytes exceeding thresholds. Otherwise, you do not prove the filter rejects properly.

### Mistake 5. Setting the Filter After readObject

The filter must be attached before the first object read. Setting it after data has already been deserialized does not protect what was already read.

### Mistake 6. Overly Broad Package Patterns

Patterns such as `java.util.*` can expand the permitted class surface beyond what is needed. Prefer exact classes or narrow packages.

### Mistake 7. Letting a Stream Filter Override Baseline Rejections

Combine filters with `ObjectInputFilter.merge` to preserve all `REJECTED` decisions.

### Mistake 8. Setting the Global Factory from Multiple Libraries

The filter factory is a JVM-wide configuration set only once. Let the application or container coordinate it centrally.

### Mistake 9. Using ThreadLocal Without Clearing Context

A previous request's policy can leak to the next request unless restored/cleared in `finally`. For async processing, pass context explicitly.

### Mistake 10. Thinking Filters Bound All Process Resources

Filters provide only serialization metrics. They do not replace upload limits, timeouts, quotas, memory limits, or CPU controls.

### Mistake 11. Catching InvalidClassException and Continuing with Default Data

Rejection signals that input violates policy. Terminate the operation and handle the error intentionally.

### Mistake 12. Treating Filters as a Reason to Keep Native Serialization for Arbitrary Data

Filters reduce risk, yet do not eliminate all gadget or side-effect risks. Avoid deserializing untrusted data when better formats exist.

## 17. Practice Exercises

### Exercise 1. Meaning of UNDECIDED

A filter returns `UNDECIDED` for classes not in the allowlist. Can you conclude those classes are allowed?

**Answer:** No. `UNDECIDED` means only that this filter has not decided. For a strict allowlist, use `rejectUndecidedClass` or reject unlisted classes.

### Exercise 2. Choosing Appropriate Limits

A payload has a 200,000-element array while total stream bytes remain under budget.

**Question:** Is using `maxbytes` alone enough?

**Answer:** No. Bound `arrayLength()` with `maxarray` or a custom filter.

### Exercise 3. Rejecting Classes

An endpoint accepts only `Message` and `String`, yet receives `UnexpectedPayload`.

**Answer:** The class filter must return `REJECTED` for classes outside the allowlist; `readObject()` fails, typically with `InvalidClassException`.

### Exercise 4. Boundary Testing

If a policy rejects when `arrayLength() > 256`, what happens to arrays of length 256 and 257?

**Answer:** A 256-element array does not exceed the threshold; a 257-element array is rejected.

### Exercise 5. Role of merge

A resource-limit filter returns `REJECTED` while a class filter returns `ALLOWED`. What is the merge result?

**Answer:** `REJECTED`. One filter rejecting suffices for the composite filter to reject.

### Exercise 6. When Is the Factory Called?

**Answer:** The filter factory is called when creating `ObjectInputStream` and when `setObjectInputFilter` requests applying a filter to the stream. The factory selects or combines filters by context.

### Exercise 7. Why Install the Factory Only Once?

**Answer:** It is a JVM-wide configuration. Multiple libraries installing factories would conflict; the application should coordinate one central factory.

### Exercise 8. Do Filters Replace Business Validation?

**Answer:** No. Filters control classes and certain serialization metrics. After deserialization, business values and invariants still need checking.

### Exercise 9. Why Are Positive Tests Needed?

**Answer:** Negative tests prove bad data is blocked; positive tests prove the policy still allows valid payloads and causes no functional regressions.

### Exercise 10. Can Filters Sandbox Untrusted Code?

**Answer:** No. Filters do not sandbox code and do not replace process isolation or OS privilege controls.

## 18. Official References

- [JDK 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): ALLOWED/REJECTED/UNDECIDED statuses, FilterInfo, merge, and rejectUndecidedClass.
- [JDK 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): creating filters from patterns, global filters, and filter factories.
- [JDK 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): attaching per-stream filters and deserializing objects.
- [JDK 17 API — InvalidClassException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InvalidClassException.html): exception thrown when a class is rejected or incompatible.
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): serialization filters, class filtering, and resource limits.
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): context-specific filter factories added in Java 17.

**Key takeaway:** Use `ObjectInputFilter` to inspect classes and bound depth, references, array length, and stream bytes during deserialization. For strict allowlists, combine `merge` and `rejectUndecidedClass` to preserve rejection decisions and exclude unconfirmed classes. Java 17 adds filter factories under JEP 415 to choose policies per stream. Always test valid payloads, rejected classes, each resource threshold, and boundary values; filters are an additional defense layer, not a sandbox or guarantee of safety for arbitrary untrusted serialization data.
