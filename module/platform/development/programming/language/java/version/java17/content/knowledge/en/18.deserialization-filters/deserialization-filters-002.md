# ObjectInputFilter and Its Role in Limiting Object Graphs

Java serialization can restore an object along with the objects it references from a byte stream. Because this process constructs an entire **object graph**, input data can contain many classes, large arrays, deeply nested references, or resource-intensive structures. If an application deserializes untrusted data without limits, it can instantiate unexpected objects, consume excessive memory or CPU, or trigger dangerous behavior through chains of classes in libraries.

Since Java 9, the **`ObjectInputFilter`** API allows controlling which classes are deserialized and limiting graph characteristics. Java 17 continues to support this mechanism and adds **context-specific filter factories** under JEP 415, enabling applications to apply policies tailored to each stream or component.

This lesson focuses on the APIs applicable in Java 17: understanding object graphs, limiting depth/reference count/size/array length, building allowlists, installing JVM-wide or per-stream filters, and the role of filter factories. `ObjectInputFilter` is an important protection layer for Java native serialization; it does not replace business validation and does not turn serialization into a safe format for accepting arbitrary data.

## 1. Why Filter During Deserialization?

Java serialization does not only read a standalone object. When an object holds references to other objects, `ObjectInputStream` can continue restoring dependent objects to reconstruct the original structure.

For example:

~~~java
class Order implements Serializable {
    Customer customer;
    List<Item> items;
}
~~~

When deserializing an `Order`, the stream may restore `Customer`, the `items` list, each `Item`, strings, arrays, and further referenced objects.

This can be visualized as:

~~~text
Order
 ├── Customer
 │    └── Address
 └── List<Item>
      ├── Item
      │    └── Product
      └── Item
           └── Product
~~~

This structure is a **graph**, because multiple fields can point to the same object and reference cycles may exist. Filtering only the root class `Order` is not enough to control classes created deeper inside.

A crafted byte stream can contain:

- A class outside the data model the application expects.
- A graph with excessive depth.
- A huge number of objects/references.
- Arrays with excessive length.
- Large data volume making reading and object creation memory-intensive.
- A chain of library classes with undesirable behavior when restored.

`ObjectInputFilter` allows rejecting deserialization as soon as classes or graph limits fail to meet policy.

## 2. What Is ObjectInputFilter?

`ObjectInputFilter` is a functional interface in the `java.io` package:

~~~java
@FunctionalInterface
public interface ObjectInputFilter {
    Status checkInput(FilterInfo filterInfo);
}
~~~

A filter receives a `FilterInfo` describing the object or state being checked, and returns one of three statuses:

| Status | Meaning |
| --- | --- |
| `ALLOWED` | This filter accepts the information being checked |
| `REJECTED` | Reject; deserialization is aborted |
| `UNDECIDED` | This filter has not made a decision yet |

When a filter returns `REJECTED`, `ObjectInputStream` rejects the data and typically throws `InvalidClassException` with information that the filter rejected it.

`UNDECIDED` is not synonymous with rejection. It allows another policy in a filter combination mechanism to make a decision; if no filter rejects, deserialization may proceed. Therefore, an allowlist needs an explicit rejection branch for unaccepted classes instead of returning `UNDECIDED` for every unknown class.

## 3. What Does FilterInfo Describe?

`ObjectInputFilter.FilterInfo` provides five key pieces of information:

| Method | Meaning |
| --- | --- |
| `serialClass()` | The class being checked; may be `null` in certain checks not tied to a new class |
| `arrayLength()` | Array length; negative if the check does not involve an array |
| `depth()` | Current depth of the deserialization graph |
| `references()` | Number of references processed so far in the stream |
| `streamBytes()` | Number of bytes consumed from the serialization stream |

These fields help the filter check both **data types** and **structural scale**.

### 3.1. Graph Depth — depth

`depth()` reports the current depth of graph restoration. An overly deep nested graph can increase processing overhead, cause memory pressure, or create issues in application logic.

Example of a nested structure:

~~~text
Node
 └── Node
      └── Node
           └── Node
                ...
~~~

Limiting depth prevents input data from creating nesting deeper than the application allows.

### 3.2. Reference Count — references

`references()` reflects the number of object references processed. A graph can be shallow yet contain vast numbers of elements or linked objects. Limiting depth alone is not enough to control this case.

For example, a list with hundreds of thousands of elements may only have a few levels of nesting while still creating a large number of references.

### 3.3. Bytes Read — streamBytes

`streamBytes()` reports the number of bytes consumed from the stream. This is a useful limit to control the total amount of serialization data the application processes.

It does not replace request size limits at the HTTP layer or file size limits at the storage layer. You should control both input size before creating `ObjectInputStream` and bytes observed by the filter during deserialization.

### 3.4. Array Length — arrayLength

`arrayLength()` enables limiting large arrays. An array can hold huge numbers of elements in a single object, so counting references or depth alone is insufficient.

For example:

~~~java
byte[] payload = new byte[100_000_000];
~~~

A very large byte array can cause heap pressure even if the graph has only one level. Filters should enforce an array length limit matching valid application data sizes.

### 3.5. Class Being Deserialized — serialClass

`serialClass()` allows inspecting the actual class being restored. A filter can allow a defined set of classes, reject classes outside that set, or apply only structural limits without deciding on classes.

A `null` value does not mean the data is guaranteed safe. You still must check `depth`, `references`, `streamBytes`, and other limits before handling that case.

## 4. Limiting the Graph with Defense in Depth

A good policy typically combines multiple limits:

- **Class allowlist:** allow only classes the data contract genuinely requires.
- **Maximum depth:** limit nested structure.
- **Maximum references:** limit object/reference count.
- **Maximum bytes:** limit data read.
- **Maximum array length:** limit large arrays.

For example, a service accepting only a small DTO might set a policy:

| Limit | Illustrative Value | Purpose |
| --- | ---: | --- |
| `maxdepth` | 10 | Prevent overly deep graph nesting |
| `maxrefs` | 1,000 | Restrict reference count |
| `maxbytes` | 1,048,576 | Limit serialization data to roughly 1 MiB |
| `maxarray` | 100,000 | Limit array length |

The numbers above are only examples. Actual limits must derive from the application's valid payload sizes and structures. An image-processing service, an app receiving small DTOs, and a large data import tool will have different needs.

Do not set overly broad limits just so current data is always accepted. Conversely, overly low limits can reject valid payloads. Define the data contract and measure real sizes before deploying.

## 5. Writing a Filter by Class and Limits

The example below allows only a `User` class along with `String`, while limiting graph scale:

~~~java
import java.io.ObjectInputFilter;

public final class UserFilter {
    private static final long MAX_DEPTH = 10;
    private static final long MAX_REFERENCES = 1_000;
    private static final long MAX_BYTES = 1_048_576;
    private static final long MAX_ARRAY_LENGTH = 100_000;

    private UserFilter() {
    }

    public static ObjectInputFilter create() {
        return info -> {
            if (info.depth() > MAX_DEPTH
                    || info.references() > MAX_REFERENCES
                    || info.streamBytes() > MAX_BYTES
                    || info.arrayLength() > MAX_ARRAY_LENGTH) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == User.class || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }
}
~~~

Key points:

1. Check structural limits before deciding by class.
2. Allow only the exact classes needed.
3. Reject other classes with `REJECTED`.
4. Do not use `UNDECIDED` as the default branch for all unknown classes.

In the example, `User` may contain a `String` field; if the actual model includes additional classes or arrays, you must add them intentionally and limit sizes accordingly.

Filters should be fast, predictable, and free of side effects. Do not perform network queries, database reads, or business operations inside `checkInput`, because the filter can be called many times during deserialization.

## 6. Installing a Per-Stream Filter on ObjectInputStream

When a component deserializes only a single payload type, a per-stream filter enforces policy close to where data is read.

~~~java
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.nio.file.Files;
import java.nio.file.Path;

try (ObjectInputStream input =
             new ObjectInputStream(Files.newInputStream(path))) {

    input.setObjectInputFilter(UserFilter.create());

    Object value = input.readObject();

    if (!(value instanceof User user)) {
        throw new InvalidObjectException("Payload is not a User");
    }

    System.out.println(user.name());
}
~~~

`setObjectInputFilter(...)` must be called before reading objects from the stream begins. A stream's filter is configured once per the API contract; do not design code to change it arbitrarily once deserialization has begun.

The `User` class in the example must implement `Serializable`. The `InvalidObjectException` in the type check is an example of post-deserialization validation; filtering and validation serve two distinct roles.

### 6.1. Complete Runnable Example

Create the file `UserFilterDemo.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public final class UserFilterDemo {

    private UserFilterDemo() {
    }

    private static final class User implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String name;
        private final int age;

        User(String name, int age) {
            this.name = name;
            this.age = age;
        }

        String name() {
            return name;
        }

        int age() {
            return age;
        }
    }

    private static ObjectInputFilter userFilter() {
        return info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 100_000
                    || info.arrayLength() > 10_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();

            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == User.class || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }

    private static byte[] serialize(Object value) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        try (ObjectOutputStream output =
                     new ObjectOutputStream(bytes)) {
            output.writeObject(value);
        }

        return bytes.toByteArray();
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {

        byte[] data = serialize(new User("An", 28));

        try (ObjectInputStream input =
                     new ObjectInputStream(
                             new ByteArrayInputStream(data))) {

            input.setObjectInputFilter(userFilter());

            Object value = input.readObject();

            if (!(value instanceof User user)) {
                throw new InvalidObjectException(
                        "Expected a User object");
            }

            System.out.println(user.name());
            System.out.println(user.age());
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 -encoding UTF-8 UserFilterDemo.java
java UserFilterDemo
~~~

Output:

~~~text
An
28
~~~

This example illustrates a small allowlist. In a real application, set the allowed classes according to the actual data contract; do not widen the allowlist with broad wildcards just to make the program run.

## 7. Pattern Filters with Config.createFilter

If the policy can be expressed with class names and numeric limits, `ObjectInputFilter.Config.createFilter(String)` creates a filter from a pattern string.

Common limit components:

| Pattern | Limit |
| --- | --- |
| `maxdepth=n` | Maximum depth |
| `maxrefs=n` | Maximum reference count |
| `maxbytes=n` | Maximum bytes read |
| `maxarray=n` | Maximum array length |

Class patterns can allow or reject specific classes, packages, or class groups using filter syntax. Some common forms:

| Pattern | Meaning |
| --- | --- |
| `com.example.dto.User` | Specific class |
| `com.example.dto.*` | Classes directly in that package |
| `com.example.dto.**` | Classes in that package and subpackages |
| `!com.example.internal.BadType` | Reject the specified class |
| `!*` | Reject classes not allowed by an earlier pattern |

A module name can be prepended to the class name using `module/classname` syntax when restricting by module.

Example of creating an allowlist:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;"
        + "maxrefs=1000;"
        + "maxbytes=1048576;"
        + "maxarray=100000;"
        + "com.example.dto.**;"
        + "java.base/java.lang.String;"
        + "!*");
~~~

Patterns are evaluated in order; the first matching class pattern decides `ALLOWED` or `REJECTED`. Numeric limits are still enforced. If no class pattern matches, the filter may return `UNDECIDED`.

A trailing `!*` creates a default-deny policy for unlisted classes. This is a more readable fail-closed approach than leaving unknown classes undecided.

### 7.1. Using a Pattern Filter Per Stream

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=1000;maxbytes=1048576;"
        + "maxarray=100000;com.example.dto.**;!*");

try (ObjectInputStream input =
             new ObjectInputStream(Files.newInputStream(path))) {
    input.setObjectInputFilter(filter);
    Object value = input.readObject();
}
~~~

If the data contains `ArrayList`, `HashMap`, arrays, or other supporting types, examine the actual classes serialization uses and add them to the allowlist as needed. Do not allow all of `java.util.**` if only a few specific types are needed.

## 8. Installing a JVM-Wide Filter

If an application has many deserialization points, a JVM-wide filter can establish a baseline policy.

### 8.1. Configuring via System Property

Patterns can be configured via the `jdk.serialFilter` property at JVM launch:

~~~bash
java "-Djdk.serialFilter=maxdepth=20;maxrefs=10000;maxbytes=5000000;maxarray=100000;com.example.dto.**;java.base/java.lang.String;!*" -jar application.jar
~~~

This is an example policy. Allowlists and limits must be tuned to actual payloads. Setting the property at JVM startup ensures the policy takes effect early, before components begin deserializing.

### 8.2. Configuring via API

A JVM-wide filter can be set using `ObjectInputFilter.Config.setSerialFilter(...)`:

~~~java
ObjectInputFilter.Config.setSerialFilter(
        ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=10000;maxbytes=5000000;"
                + "maxarray=100000;com.example.dto.**;!*"));
~~~

The JVM-wide filter can only be set once per the API contract. If already configured via system property or set by another component, calling it again can fail. Therefore, place configuration ownership in the application bootstrap and avoid letting multiple libraries compete to set the global filter.

### 8.3. Global Filter vs. Per-Stream Filter

| Filter Type | Scope | When Appropriate |
| --- | --- | --- |
| JVM-wide filter | Baseline policy for `ObjectInputStream`s in the JVM | The application needs a consistent baseline |
| Per-stream filter | A specific stream | An endpoint or component has its own payload and allowlist |
| Filter factory | Decides how filters are created/combined by context | Multi-component applications needing context-specific policies |

Do not treat per-stream filters as a reason to skip a global policy. A JVM-wide policy provides a baseline defense layer; stream filters can add stream-specific restrictions.

## 9. Context-Specific Filter Factories in Java 17

Java 17 adds **JEP 415 – Context-Specific Deserialization Filters**. Prior to this change, a JVM-wide filter and a per-stream filter could make it difficult to express different policies for independent contexts within the same process.

A filter factory lets the application decide which filter is attached to an `ObjectInputStream`, based on the current filter and the requested filter. The factory can use application-managed context information, such as endpoint type, calling component, or per-tenant policy.

Configuration API:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory(
        (currentFilter, requestedFilter) -> {
            // Select or combine policies according to application context.
            // Return the final filter used for ObjectInputStream.
            return combineAccordingToPolicy(
                    currentFilter,
                    requestedFilter);
        });
~~~

`combineAccordingToPolicy(...)` here is an application-designed helper, not a built-in API. The key idea is that the factory receives two filters and returns the final filter. The factory is invoked when a stream is constructed and when a per-stream filter is set.

### 9.1. Why Are Filter Factories Needed?

Suppose the same JVM runs two components:

- Component A only deserializes `UserProfile`.
- Component B only deserializes `Invoice`.
- Both must abide by JVM-wide resource limits.

A factory can choose different allowlists by context while preserving baseline limits. This avoids expanding a global allowlist too broadly just to serve unrelated payload types.

### 9.2. Configuring the Factory

The factory can be set via `ObjectInputFilter.Config.setSerialFilterFactory(...)` or by configuring a factory class via the runtime's `jdk.serialFilterFactory` property mechanism.

The factory is an application-level policy. When writing a custom factory, you need to:

- Clearly define the baseline filter and context-specific filters.
- Ensure `REJECTED` decisions are never turned into acceptance.
- Never bypass baseline filter resource limits.
- Never rely on context information that can be forged from the payload.
- Write tests for each context as well as the missing-context case.

The JDK's default factory defines how JVM-wide and per-stream filters interact. When replacing it with a custom factory, the application is responsible for preserving the policies it needs.

## 10. Allowlists Are Better Than Broad Denylists

A denylist only enumerates known dangerous classes. This approach easily misses new classes or gadget chains arising from other dependencies.

Example of a policy that rejects only one class:

~~~java
if (type == SomeKnownDangerousType.class) {
    return ObjectInputFilter.Status.REJECTED;
}
return ObjectInputFilter.Status.ALLOWED;
~~~

This approach allows every remaining class, including classes the application never intended to deserialize.

For payloads with an explicit schema, prefer an allowlist:

~~~java
if (type == User.class
        || type == String.class
        || type == Address.class) {
    return ObjectInputFilter.Status.ALLOWED;
}
return ObjectInputFilter.Status.REJECTED;
~~~

An allowlist allows only the necessary classes. When adding a new data type, developers must explicitly update the contract and filter.

There is no universal allowlist right for every application. If a model contains collections, maps, enums, or arrays, identify the exact implementations and element types written by serialization; avoid enabling broad wildcards to fix missing-class errors.

## 11. Filters Do Not Replace Data Validation

`ObjectInputFilter` controls classes and structural traits during deserialization. It does not automatically verify that field values are valid under business rules.

For example, an object may belong to an allowlisted `User` class yet still contain:

- An empty or overly long name.
- A negative age.
- A non-existent ID.
- An invalid state.
- Inconsistent relationships between fields.

After deserialization, the application still needs validation:

~~~java
if (user.name() == null || user.name().isBlank()) {
    throw new InvalidObjectException("Invalid name");
}

if (user.age() < 0 || user.age() > 130) {
    throw new InvalidObjectException("Age out of allowed range");
}
~~~

Filters also do not verify signatures, origin, or data integrity. If the application must verify the sender, appropriate authentication and integrity protection mechanisms must be used at the protocol layer.

## 12. ObjectInputFilter Is Not a Complete Sandbox

Filters are an important defense layer, but Java native deserialization should not be treated as a safe way to accept arbitrary data from the Internet.

Limitations to understand:

- Filters apply to Java object deserialization, not as a general filter for JSON, XML, or all parsers.
- Filters do not replace request/file size limits prior to creating `ObjectInputStream`.
- Filters do not validate the full business semantics of fields.
- Filters do not guarantee data is authenticated or unmodified.
- An overly broad allowlist can still permit a class with dangerous behavior or an unwanted object chain.
- Resource limits must suit the system; a very large threshold can still cause significant pressure.

For new protocols or untrusted data, prefer data formats with explicit schemas and parsers designed for untrusted input. If Java serialization must be maintained for compatibility contracts, use strict filters, small allowlists, and post-deserialization validation.

## 13. Applying Filters at the Right Time and Place

Important implementation principles:

1. **Set the global filter early:** configure before other libraries or modules create deserialization streams.
2. **Set per-stream filters before `readObject()`:** do not wait until the first object has already been restored.
3. **Do not let multiple components set the global filter:** the global API has a one-time setup limit.
4. **Use a filter factory when multiple contexts are needed:** manage policy centrally with clear ownership.
5. **Limit input before deserialization:** control request size, file size, and data source.
6. **Check classes and graph limits:** do not check only the root class.
7. **Validate objects after deserialization:** check field values, permissions, and business rules.

If a library creates `ObjectInputStream` internally, the application needs to be aware of that point to ensure the global filter or filter factory applies. You cannot assume only streams created directly by your own code need protection.

## 14. Handling Filter Rejections

When a filter returns `REJECTED`, object reading is aborted. Example:

~~~java
try (ObjectInputStream input =
             new ObjectInputStream(Files.newInputStream(path))) {

    input.setObjectInputFilter(UserFilter.create());

    Object value = input.readObject();

} catch (InvalidClassException ex) {
    System.err.println("Object graph rejected by filter: "
            + ex.getMessage());
}
~~~

In a real system, distinguish between:

- Payload containing a class not in the allowlist.
- Graph exceeding depth/reference/byte/array limits.
- Corrupted or incompatible serialization data.
- I/O errors while reading the source.

Do not catch `InvalidClassException` and ignore it as if the data were valid. Log at an appropriate level without logging full payloads or sensitive data.

## 15. Common Mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Filtering only the root class still creates unexpected objects inside | The graph contains multiple referenced classes | Filter every class encountered during deserialization |
| Shallow graph still consumes large heap | Reference count or array length is too large | Combine `maxrefs`, `maxarray`, and `maxbytes` |
| Deeply nested graph consumes heavy resources | Depth is not limited | Set an appropriate `maxdepth` |
| Unknown classes are still deserialized | Filter returns `UNDECIDED` instead of default-deny | Use an allowlist and return `REJECTED` for disallowed classes |
| Valid payloads are rejected | Allowlist misses supporting types or limits are too low | Determine the exact valid graph and update policy in a controlled way |
| `setObjectInputFilter` throws a state error | Filter set too late or attempted multiple times | Set once before reading any object |
| Global filter is not set | Another component configured earlier or filter already set | Assign configuration ownership at bootstrap |
| Per-stream filter misses global policy | Only stream filter set, bypassing baseline | Use global policy and factory to combine intentionally |
| Using a denylist misses new classes | Only blocking a few known classes | Use a small allowlist per data contract |
| Data has valid classes but wrong fields | Filter does not check business semantics | Validate objects after deserialization |
| Believing the filter protects JSON/XML | Filter applies only to Java serialization | Use validation/schema and limits specific to the corresponding parser |

## 16. Practice Exercises

### Exercise 1 — Observing FilterInfo

Create a `Serializable` class with a `String` field and a byte array. Install a filter that prints `serialClass()`, `depth()`, `references()`, `streamBytes()`, and `arrayLength()`. Observe how the information changes while reading.

### Exercise 2 — Depth Limit

Create a multi-level nested object structure. Set a low `maxdepth` to observe filter rejection. Increase the limit to just enough for the valid model.

### Exercise 3 — Array and Byte Limits

Serialize a small byte array and a large array. Set different `maxarray` and `maxbytes` values to see how each limit controls a distinct aspect.

### Exercise 4 — Allowlist

Create a payload containing an allowed class and a class not in the allowlist. Verify the first payload can be read and the second is rejected.

### Exercise 5 — Pattern Filter

Use `ObjectInputFilter.Config.createFilter(...)` to configure limits and a DTO package. Try trailing `!*` to reject unallowed classes. Explain how pattern order affects decisions.

### Exercise 6 — Global and Per-Stream

Set a JVM-wide filter as a baseline, then set a per-stream filter on a stream. Check the combined policy and verify the stream filter does not accidentally bypass baseline limits.

### Exercise 7 — Filter Factory

Design two hypothetical contexts: one reading `UserProfile`, the other reading `Invoice`. Describe how a factory selects the corresponding allowlist while preserving shared resource limits.

## 17. Principles to Remember

- Java object deserialization restores an **object graph**, not just a single root object.
- `ObjectInputFilter` checks classes and structural limits during deserialization.
- Use `depth`, `references`, `streamBytes`, and `arrayLength` to control multiple forms of resource consumption.
- Prefer allowlists of required classes and reject classes outside the contract.
- `UNDECIDED` is not a rejection status; fail-closed requires an explicit `REJECTED` decision.
- Filters can be set JVM-wide or per `ObjectInputStream`; set them before reading objects.
- Java 17 provides context-specific filter factories under JEP 415 to select/combine policies per stream.
- Filters do not replace input size limits, data source authentication, or business validation.
- For untrusted data and new protocols, prefer explicit-schema formats; if Java serialization must be used, apply strict filters and test policies.

Properly limiting object graphs reduces the risk of instantiating unexpected classes and controls resources during deserialization. In Java 17, combining allowlists, structural limits, JVM-wide filters, and context-specific filter factories creates a clearer policy for components still using Java serialization.
