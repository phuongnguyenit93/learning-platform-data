# Limiting Classes, Depth, References, Bytes, and Array Sizes in Deserialization Filtering

Java serialization can reconstruct an object graph from binary data. While reading a stream, `ObjectInputStream` can create many objects, link them together, process arrays, and restore repeated references or reference cycles. If data comes from an untrusted source, an overly large graph or unexpected classes can consume excessive memory or CPU, or trigger unwanted behavior during deserialization.

Since Java 9, Java provides **serialization filtering** via `java.io.ObjectInputFilter` (JEP 290). Java 17 continues supporting this API. Filters allow limiting:

- **Classes allowed to be deserialized** (*class filtering*).
- **Object graph depth** (*maximum depth*).
- **Number of references** (*maximum references*).
- **Bytes read from the stream** (*maximum stream bytes*).
- **Array size** (*maximum array length*).

These limits are usually combined. For example, a request might only be allowed to read DTOs in an approved package, with a graph depth no deeper than 20 levels, no more than 1,000 references, consuming no more than 1 MiB of data, and creating no array longer than 10,000 elements.

`ObjectInputFilter` is a mechanism for controlling data **being deserialized**. It does not replace business validation, network-layer size checks, or choosing a safer data format when Java native serialization is unnecessary.

## 1. Why Filter During Deserialization?

With Java serialization, data is not just a simple sequence of fields. One object can reference another; objects can share references or form cycles:

```text
Request
  ├── User
  │    ├── Profile
  │    └── Preferences
  ├── Orders[]
  │    ├── Order
  │    └── Order
  └── Metadata
```

When restoring this graph, the JVM must read class descriptors, allocate objects and arrays, and wire references. If input is unconstrained, a stream can:

- Request restoring a class the application does not intend to accept.
- Create a very deeply nested graph.
- Contain a massive number of references.
- Consume stream data beyond budget.
- Request an array of huge size.

Filters allow the application to reject the graph during reading, before continuing to restore blocked objects.

### 1.1. Filters Are Not Automatically Enabled for Every Application

Do not assume Java 17 automatically applies an allowlist or suitable thresholds to every `ObjectInputStream`. Applications must actively configure filters matching the data and classes actually permitted.

If a system still uses Java serialization, configure the filter before reading the first object. For untrusted data, combine a class allowlist with resource limits; setting only a size threshold without restricting classes can still allow unwanted object types.

## 2. ObjectInputFilter and FilterInfo

Core API:

```java
import java.io.ObjectInputFilter;
```

`ObjectInputFilter` is a functional interface. The filter receives `ObjectInputFilter.FilterInfo` describing the state being deserialized and returns one of three statuses:

| Status | Meaning |
| --- | --- |
| `ALLOWED` | The filter permits the object or state under consideration. |
| `REJECTED` | Reject; deserialization is aborted and typically throws `InvalidClassException`. |
| `UNDECIDED` | The filter has not decided; the outcome depends on other filters or default handling. |

`FilterInfo` provides key information:

| Method | Information |
| --- | --- |
| `serialClass()` | The class under consideration; may be `null` when the information is not tied to a specific new class. |
| `arrayLength()` | Length of the array being deserialized; negative if not an array. |
| `depth()` | Current depth of the object graph. |
| `references()` | Number of references processed so far in the stream. |
| `streamBytes()` | Number of bytes read from the stream at the time the filter is invoked. |

A filter can rely on these values to decide whether to accept or reject the data.

### 2.1. Two Groups of Conditions

Typically, conditions should be split into two groups:

1. **Resource limits:** `depth`, `references`, `streamBytes`, `arrayLength`.
2. **Type restrictions:** `serialClass`.

If any resource threshold is exceeded, reject immediately. If not exceeded, check whether the class belongs to the allowed set.

## 3. Four Resource Limits

Java serialization filters support four independent thresholds. They control different dimensions of the graph and stream.

### 3.1. maxdepth: Limiting Graph Depth

`maxdepth` limits the nesting levels of the object graph being deserialized.

Example:

```text
maxdepth=20
```

If a graph has the structure:

```text
Order
  └── Customer
       └── Address
            └── Country
```

then each level of object nesting increments depth during reading. A graph with an overly deep chain of nested references can increase processing cost or put pressure on the stack.

`maxdepth` is suitable for limiting abnormal nesting. It does **not** limit the total number of objects in the graph: one node can reference thousands of child nodes at the same level. Therefore it must be combined with `maxrefs`.

### 3.2. maxrefs: Limiting Reference Count

`maxrefs` limits the number of references recorded in the stream. This is useful when a graph has many objects or links:

```text
maxrefs=1000
```

A graph can be shallow yet very wide:

```text
Catalog
  ├── Item 1
  ├── Item 2
  ├── Item 3
  ├── ...
  └── Item 50000
```

In this example, depth may be small while the reference count is huge. `maxdepth` alone does not control this case; `maxrefs` adds a count-based limit.

Repeated references and back-references are also part of the serialization mechanism. Do not try to infer business object counts directly from `references()`; treat it as a resource counter per the filter contract.

### 3.3. maxbytes: Limiting Bytes Read from the Stream

`maxbytes` limits the number of bytes consumed from the input stream:

```text
maxbytes=1048576
```

The value above corresponds to 1 MiB. This is an overall budget for serialized data read, useful when a payload can contain many objects or fields.

`maxbytes` differs from file size at the storage layer:

- The filter observes bytes read from the serialization stream.
- HTTP, message broker, or file upload layers may need separate limits prior to creating `ObjectInputStream`.
- A stream may have framing or surrounding data outside the serialization portion; transport-layer budgets still must be enforced independently.

Do not rely solely on `maxbytes` to protect the entire data-ingestion pipeline. Limit payloads at the input boundary and use the filter as an additional defense layer inside deserialization.

### 3.4. maxarray: Limiting Array Length

`maxarray` limits the number of elements in a restored array:

```text
maxarray=10000
```

For example, data might contain:

```java
byte[] payload;
String[] labels;
Order[] orders;
```

If the stream requests an array exceeding the threshold, the filter can reject it before the array is allocated per that request.

`maxarray` is an element count, not a byte count. For example:

- `byte[10000]` has 10,000 byte elements.
- `int[10000]` also has 10,000 elements, though the element data occupies more space.
- `String[10000]` has 10,000 reference slots; the strings inside are separate objects.

Array limits do not replace `maxbytes` or `maxrefs`. Moderate-sized arrays can still contain many objects; a stream without large arrays can still consume many bytes.

## 4. Combining the Four Thresholds

A configuration often needs to bound all four dimensions simultaneously:

```text
maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000
```

Meaning:

| Limit | Example Value | Goal |
| --- | ---: | --- |
| `maxdepth` | 20 | Prevent graph nesting deeper than allowed. |
| `maxrefs` | 1,000 | Restrict total references processed. |
| `maxbytes` | 1,048,576 | Restrict bytes read from stream to 1 MiB. |
| `maxarray` | 10,000 | Restrict the length of each array. |

These are only **illustrative values**, not thresholds suitable for every application. Measure actual valid payloads, determine business maximums, and leave a reasonable margin. Too-low thresholds break valid requests; too-high thresholds reduce protection.

### 4.1. Why Not Set Only maxbytes?

Suppose a small payload describes many tiny objects. Total bytes might not be large yet, while reference counts are high. Conversely, an object with a huge array can consume vast memory even when depth and node count are low.

The thresholds complement one another:

- `maxdepth`: limits nested structure.
- `maxrefs`: limits breadth/number of links processed.
- `maxbytes`: limits serialized data read.
- `maxarray`: limits size of each array.

## 5. Limiting Classes: Allowlists and Denylists

Resource limits do not answer the question of **which classes are allowed to appear**. `serialClass()` lets the filter check the object type being restored.

An easily controlled strategy is an **allowlist**:

- Allow specific DTOs or a defined DTO package.
- Allow core platform types genuinely needed for the data structure.
- Reject remaining classes.

For example, suppose an application only accepts types in package `com.example.dto`:

```text
com.example.dto.**
```

A pattern-based filter can combine limits and class patterns:

```java
String pattern =
        "maxdepth=20;" +
        "maxrefs=1000;" +
        "maxbytes=1048576;" +
        "maxarray=10000;" +
        "com.example.dto.**;" +
        "java.lang.String;" +
        "!*";

ObjectInputFilter filter =
        ObjectInputFilter.Config.createFilter(pattern);
```

In the pattern:

- `com.example.dto.**` matches classes in that package and subpackages.
- `java.lang.String` allows the string type if it appears in the filtered graph.
- `!*` rejects any class not matching preceding allow patterns.

Patterns are separated by semicolons and evaluated in order. `max...` limits are checked as resource thresholds; if exceeded, the filter rejects. For class patterns, ordering allows placing specific rules before a catch-all rejection rule at the end.

### 5.1. *, package.*, and package.**

Common class patterns:

| Pattern | Meaning |
| --- | --- |
| `com.example.dto.Customer` | A specific class. |
| `com.example.dto.*` | Classes directly in package `com.example.dto`. |
| `com.example.dto.**` | Classes in that package and its subpackages. |
| `!*` | Rejects any class not accepted by an earlier pattern. |
| `*` | Matches all classes. |

`package.*` and `package.**` are not the same. If DTOs are organized into subpackages like `com.example.dto.order`, `com.example.dto.*` does not cover the same scope as `com.example.dto.**`.

### 5.2. Why Place !* at the End of an Allowlist?

A pattern containing only allowed classes can return `UNDECIDED` for non-matching classes. `UNDECIDED` does not mean reject. When a true allowlist is needed, a final rejection rule is required so unlisted classes are excluded.

Example:

```text
com.example.dto.**;java.lang.String;!*
```

Do not omit `!*` and assume all unmatched classes are automatically blocked.

### 5.3. Allowlists Must Reflect the Entire Valid Graph

A DTO may contain collections, enums, date/time types, or other supporting classes. If only the root DTO is allowlisted, the filter may reject a required child class when the stream restores the graph.

For example, if a DTO has an `ArrayList<String>` field, the application needs to evaluate and allow the needed collection type along with related element types. Do not arbitrarily add the entire `java.util.**` package just to make requests succeed; that widens the type set considerably.

Identify the classes actually serialized in the data contract, then add individual classes or narrow packages. Test with valid payloads representing all supported data branches.

## 6. Configuring Filters with Pattern Strings

`ObjectInputFilter.Config.createFilter(String)` builds a filter from a pattern string. This is a concise way to configure thresholds and class patterns.

Example:

```java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;" +
        "maxrefs=1000;" +
        "maxbytes=1048576;" +
        "maxarray=10000;" +
        "com.example.dto.**;" +
        "java.lang.String;" +
        "!*"
);
```

This pattern:

1. Rejects streams exceeding any resource limit.
2. Allows DTO classes in the specified package.
3. Allows `String`.
4. Rejects other non-matching classes.

This is a sample configuration. If the graph includes `ArrayList`, enums, or other supporting types, add them according to the data contract. Do not replace `!*` with `*` just to eliminate rejection errors; doing so defeats the allowlist.

### 6.1. Limit Values

Values of limit properties are non-negative numbers:

- `maxdepth=n`
- `maxrefs=n`
- `maxbytes=n`
- `maxarray=n`

Document units and meaning in deployment configuration. For example, `maxbytes=1048576` is bytes, not KB or object count.

### 6.2. Patterns Do Not Replace Business Checks

A class `com.example.dto.PaymentRequest` can be allowlisted yet still contain:

- Negative amounts or amounts exceeding business limits.
- Invalid customer IDs.
- Disallowed statuses.
- Strings longer than business limits.

Filters decide types and structural/stream limits; after reading the object, the application must still check business values and relationships.

## 7. Attaching a Filter Per ObjectInputStream

If only one data-receiving flow needs a dedicated filter, `ObjectInputStream.setObjectInputFilter(...)` can be used.

Example:

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

public class FilteredReader {
    static Object read(InputStream source)
            throws IOException, ClassNotFoundException {

        ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
                "maxdepth=20;" +
                "maxrefs=1000;" +
                "maxbytes=1048576;" +
                "maxarray=10000;" +
                "com.example.dto.**;" +
                "java.lang.String;" +
                "!*"
        );

        try (ObjectInputStream input = new ObjectInputStream(source)) {
            input.setObjectInputFilter(filter);
            return input.readObject();
        }
    }
}
```

The filter must be set **before reading objects**. Once the stream has begun deserializing, do not wait until part of the data has been read to set the filter.

The method above returns `Object` to illustrate the API. At the application layer, check the result type:

```java
import java.io.InvalidObjectException;

Object value = FilteredReader.read(source);
if (!(value instanceof CustomerDto customer)) {
    throw new InvalidObjectException("Unsupported data type");
}
```

Checking the result type does not replace the filter; it is a contract verification step after the object has been read.

### 7.1. Scope of a Per-Stream Filter

A per-stream filter fits when:

- An endpoint receives a specific message type.
- An import flow has its own limits.
- Different data sources have different allowlists and budgets.

The advantage is each flow can have a policy closely tailored to its data. The drawback is every place creating `ObjectInputStream` must be configured properly; missing a single read site creates an unprotected entry point.

## 8. Writing Filters with Lambdas for Fine-Grained Control

Pattern strings are convenient for configuration, while custom filters allow writing clearer logic, especially when handling array classes or type-based conditions.

Resource limit example:

```java
import java.io.ObjectInputFilter;

static ObjectInputFilter resourceFilter() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 1_000
                || info.streamBytes() > 1_048_576
                || (info.arrayLength() >= 0
                    && info.arrayLength() > 10_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }

        return ObjectInputFilter.Status.UNDECIDED;
    };
}
```

This filter only sets resource limits; it does not allowlist classes itself. Used alone, `UNDECIDED` is not a rule rejecting all unknown classes. Combine with a class filter if type restrictions are needed.

### 8.1. Combining Limits with a Class Allowlist

Example with a DTO class:

```java
import java.io.Serializable;

public final class CustomerDto implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String name;
    private final int age;

    public CustomerDto(String name, int age) {
        this.name = name;
        this.age = age;
    }
}
```

The filter can check both thresholds and types:

```java
import java.io.ObjectInputFilter;

static ObjectInputFilter customerFilter() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 1_000
                || info.streamBytes() > 1_048_576
                || (info.arrayLength() >= 0
                    && info.arrayLength() > 10_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        while (type.isArray()) {
            type = type.getComponentType();
        }

        if (type.isPrimitive()
                || type == String.class
                || type == CustomerDto.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
```

This code illustrates how to:

- Reject when any of the four limits is exceeded.
- Handle `serialClass()` possibly being `null`.
- Unwrap array dimensions to inspect the component type.
- Allow only primitive components, `String`, and the chosen DTO.
- Reject other classes.

In a real application, expand the allowlist for the exact types used in the serialized graph. For example, if a DTO has enums, collections, or a custom value class, those types must be reviewed deliberately.

### 8.2. Why Can serialClass() Be Null?

Not every filter invocation is tied to a new class. When `serialClass()` is `null`, the filter has no class name to match. You can still evaluate resource thresholds first; if not exceeded, return `UNDECIDED` rather than assuming a class.

Do not return `ALLOWED` immediately when `serialClass()` is null before checking depth/references/bytes/arrayLength. Resource limits may still need to apply.

## 9. Configuring a JVM-Wide Filter

If an application uses `ObjectInputStream` in many places, a process-wide filter can be configured.

### 9.1. Using the jdk.serialFilter System Property

Can be configured at JVM startup:

```bash
java "-Djdk.serialFilter=maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.dto.**;java.lang.String;!*" -jar app.jar
```

A JVM-wide filter applies a common policy to streams created in the process via the JDK's configuration mechanism. Check how the shell passes semicolons and quotes on the deployment OS; the example above passes the entire pattern as one property value.

### 9.2. Using Config.setSerialFilter

A process-wide filter can be configured via the API:

```java
ObjectInputFilter global = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=1000;maxbytes=1048576;maxarray=10000;com.example.dto.**;java.lang.String;!*"
);

ObjectInputFilter.Config.setSerialFilter(global);
```

This is a process-wide configuration and can only be set per the API's one-time rule; if a global filter is already set, setting it again may fail with `IllegalStateException`. Configure it early during startup before components begin deserialization.

### 9.3. Global Filter and Per-Stream Filter

Global filters work well as a baseline policy; per-stream filters work well when an endpoint needs its own policy. How the JVM selects/combines filters is also influenced by the filter factory. Do not assume two filters are always ANDed or that a local filter always replaces the global filter in every setup.

On Java 17, `ObjectInputFilter.Config.getSerialFilterFactory()` and filter factories let the application control how filters are chosen per stream. If the application needs to combine multiple policies, configure and test the factory explicitly rather than relying on implicit order.

## 10. Filter Factories and Context-Specific Policies

JEP 415 was introduced in Java 17 to support **context-specific deserialization filters**. A large application can have many data types and call sources; a single policy might be too broad for one endpoint yet too strict for another.

Filter factories allow selecting a filter when an `ObjectInputStream` is created, based on the current filter, the requested filter, and application-managed context.

Cases that may need separate policies:

- Internal messages from an authenticated service.
- User-uploaded import files.
- Local caches written by the same application version.
- Data compatible with a legacy integration.

Do not use a single broad allowlist for all sources merely for configuration convenience. Each source has a different data contract and budget; filter factories help make context-appropriate decisions.

JEP 415 does not change the meaning of the four thresholds `maxdepth`, `maxrefs`, `maxbytes`, `maxarray`; it adds a more flexible way to select filters.

## 11. Choosing Thresholds from Real Data

Numbers in examples are not safe defaults. Threshold selection should be based on the message contract:

| Limit | Question to Answer |
| --- | --- |
| `maxdepth` | How many levels deep are valid nested DTOs at most? |
| `maxrefs` | What is the maximum number of objects/references in a valid request? |
| `maxbytes` | What is the largest valid serialized payload in bytes according to business needs? |
| `maxarray` | How many elements are in the largest valid array? |
| Class allowlist | Exactly which classes can appear in the graph? |

Threshold-selection workflow:

1. Collect valid payloads representing small, medium, and large sizes.
2. Measure depth, references, streamBytes, and arrayLength inside the filter callback.
3. Determine maximums from business requirements.
4. Add a controlled safety margin for valid data.
5. Test payloads just below and exceeding each threshold.
6. Monitor rejections in runtime environments to tune based on evidence.

Do not pick an arbitrarily huge number just to avoid errors. Thresholds must relate to the maximum data the system genuinely needs to process.

### 11.1. Each Limit Protects Against a Different Growth Pattern

| Payload Shape | Notable Limit |
| --- | --- |
| Very deeply nested object chain | `maxdepth` |
| List of many small objects | `maxrefs` |
| Large serialized data or large fields | `maxbytes` |
| A very long array | `maxarray` |
| Class outside data contract | Class allowlist |

One payload can exceed multiple limits simultaneously. The filter simply rejects when any mandatory condition is violated.

## 12. Distinguishing Array Limits from String Content Limits

`maxarray` controls Java array lengths, not the character count of every `String`.

If an application needs to limit text field lengths such as names, notes, or descriptions, validate after deserialization:

```java
if (customer.getName() == null
        || customer.getName().length() > 200) {
    throw new IllegalArgumentException("Invalid name");
}
```

If input bytes must be capped, enforce limits at the transport layer or stream wrapper alongside `maxbytes`. If string length must be capped in UTF-8 bytes, measure using the appropriate charset; `String.length()` counts UTF-16 code units, not UTF-8 bytes.

These limit types cannot substitute for one another:

- `maxarray`: element count of an array.
- `maxbytes`: bytes read from the serialization stream.
- `String.length()`: length in UTF-16 code units.
- `getBytes(UTF_8).length`: byte count when encoded in UTF-8.

## 13. Rejecting Data and Handling Exceptions

When a filter returns `REJECTED`, object reading is aborted. The application typically receives `InvalidClassException`, which is an `ObjectStreamException`/`IOException`.

Example:

```java
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputStream;

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
    // Process value after confirming type and data.
} catch (InvalidClassException ex) {
    System.out.println("Data rejected by serialization filter");
} catch (IOException | ClassNotFoundException ex) {
    System.out.println("Unable to read data: " + ex.getMessage());
}
```

Do not return internal details about classes or filter structure to the caller if doing so leaks unnecessary information. Internal logs can record appropriate reasons for investigation, but avoid logging full sensitive payloads.

`REJECTED` should never be caught and ignored to continue using a partially read object. When a stream is rejected, treat the entire message as invalid and terminate processing for that request.

## 14. What Serialization Filters Do Not Do

`ObjectInputFilter` has a specific scope. It does not replace:

- **Business validation:** amounts, statuses, identifiers, and cross-field relationships still need checking.
- **Network/file-layer input limits:** limiting payloads before creating an object stream remains necessary.
- **Sender authentication:** filters do not prove who sent the data.
- **Integrity checks:** if a protocol needs origin/integrity authentication, use appropriate mechanisms like MACs or signatures per system design.
- **Safe API design:** allowlisting a class does not make a class with a dangerous `readObject` safe.
- **Processing time limits:** graph thresholds are not CPU or I/O timeouts.

If native Java serialization can be replaced with an explicit-schema data format and appropriate parser, that is generally an easier-to-control design direction for new communication. If Java serialization must be maintained, use filters with proper allowlists and thresholds.

## 15. Combined Example: Reading a DTO with Limits

The following example illustrates a simple DTO and filter for a specific message type.

```java
import java.io.IOException;
import java.io.InputStream;
import java.io.InvalidClassException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.Serializable;

public class SafeMessageReader {

    public static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String id;
        private final String body;

        public Message(String id, String body) {
            this.id = id;
            this.body = body;
        }

        public String id() {
            return id;
        }

        public String body() {
            return body;
        }
    }

    private static ObjectInputFilter filter() {
        return info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 256 * 1024
                    || (info.arrayLength() >= 0
                        && info.arrayLength() > 2_000)) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            while (type.isArray()) {
                type = type.getComponentType();
            }

            if (type.isPrimitive()
                    || type == String.class
                    || type == Message.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }

    public static Message read(InputStream source)
            throws IOException, ClassNotFoundException {
        try (ObjectInputStream input = new ObjectInputStream(source)) {
            input.setObjectInputFilter(filter());
            Object value = input.readObject();

            if (!(value instanceof Message message)) {
                throw new InvalidObjectException(
                        "Expected SafeMessageReader.Message"
                );
            }

            if (message.id() == null || message.id().length() > 64) {
                throw new InvalidObjectException("Message id is invalid");
            }
            if (message.body() == null || message.body().length() > 10_000) {
                throw new InvalidObjectException("Message body is invalid");
            }

            return message;
        }
    }
}
```

In this example:

- Maximum depth is 10.
- Maximum references is 100.
- Maximum bytes read from serialization stream is 256 KiB.
- Maximum array length is 2,000 elements.
- Only `Message`, `String`, and corresponding primitive/primitive-array types are allowed.
- After reading, the application still checks the root type and business length limits of `id` and `body`.

These small thresholds suit only this message example. When modifying the DTO or adding collections/enums/nested types, update the allowlist and budget according to the new contract.

## 16. Common Errors and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `InvalidClassException` when reading valid objects | Filter rejected a needed class or a threshold was set too low. | Inspect classes and FilterInfo metrics; add only genuinely needed types/thresholds. |
| `maxdepth` is set but payloads with too many objects still pass | Graph is wide rather than deep. | Add `maxrefs`. |
| `maxrefs` is set but payloads still read too many bytes | Object count may be small while serialized data is large. | Add `maxbytes` and limit payloads at the transport layer. |
| `maxbytes` is set but large arrays still need separate bounds | Byte budget and array element count are two distinct quantities. | Add `maxarray`. |
| Allowlist does not match subpackages | Used `package.*` while classes reside in subpackages. | Use `package.**` if all subpackages genuinely belong to the allowed contract. |
| Unmatched classes are not yet rejected | Unmatched patterns return `UNDECIDED`. | Add `!*` at the end of the allowlist or return `REJECTED` in a custom filter. |
| DTO is allowed but collections inside are blocked | Graph also contains collection/enum/value classes. | Identify actual serialized types and allowlist accurately. |
| Filter set only after `readObject()` | Objects were already deserialized before the filter was set. | Set the filter immediately after creating `ObjectInputStream` and before reading objects. |
| `maxarray` does not limit `String` length as expected | String is not a Java array in the sense of this threshold. | Check string length after reading and limit bytes at stream/transport layers. |
| Global filter affects more streams than expected | JVM-wide filter has process-wide scope. | Use appropriate context-specific or per-stream policies; manage filter factory when needed. |
| Thinking filters protect all aspects of deserialization | Filters do not validate business values, sender origin, or processing time. | Combine with validation, source authentication, and limits at other layers. |

## 17. Practice Exercises

### Exercise 1 — Apply the Four Limits

Create a filter pattern:

```text
maxdepth=10;maxrefs=500;maxbytes=524288;maxarray=5000;*
```

Explain each threshold and why the `*` pattern does not create a class allowlist.

### Exercise 2 — Write an Allowlist

Create a filter allowing only classes in `com.example.dto` and `java.lang.String`, rejecting all other classes. Try removing `!*` and explain the difference between `UNDECIDED` and `REJECTED`.

### Exercise 3 — Depth and Reference Count

Create two graphs:

- A deeply nested chain of objects.
- One root object referencing many child objects.

Observe why `maxdepth` and `maxrefs` detect two different forms of growth.

### Exercise 4 — Array Size

Serialize a DTO containing a `byte[]` with lengths below and above the `maxarray` threshold. Observe the filter receiving `arrayLength()` and explain why this limit is not synonymous with total stream byte limits.

### Exercise 5 — Per-Stream and Global Filters

Write a reader using `setObjectInputFilter`, then explore configuring process-wide with `jdk.serialFilter`. State suitable scenarios for each scope.

### Exercise 6 — Post-Deserialization Checks

Create a DTO with `name` and `amount` fields. Use a filter to limit class/graph, then validate `name` is non-null and within length bounds and `amount` is non-negative. Explain why filters do not replace business validation.

## 18. Official Java 17 Documentation

- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): filter interface, FilterInfo, Status, and graph metrics.
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): creating filters from patterns, configuring process-wide filters and filter factories.
- [Java SE 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): setting per-stream filters and reading objects.
- [Java SE 17 Launcher — jdk.serialFilter](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): configuring filters via JVM system property.
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): serialization filter design, resource limits, and class filtering.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter factories and context-specific deserialization policies, introduced in JDK 17.

When filtering deserialization in Java 17, combine a **class allowlist** with four independent thresholds: `maxdepth`, `maxrefs`, `maxbytes`, and `maxarray`. Depth limits nesting; reference count limits graph breadth; byte count limits data read; array size limits individual arrays. Configure filters before reading objects, set thresholds from real valid payloads, and continue validating values after deserialization.
