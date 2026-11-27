# Filter Limitations: Not a Replacement for Data Content Validation in Java 17

## 1. What Do Deserialization Filters Protect Against?

Java Serialization can reconstruct an object graph from a byte stream. When data arrives from a file, network, or external source, reading the stream can cause the JVM to instantiate many objects, large arrays, or a very deep reference graph. Some classes also execute custom logic during deserialization.

Since Java 9, Java provides `ObjectInputFilter` for applications to set limits on data read through `ObjectInputStream`. Filters can make decisions based on metadata such as:

- The class currently being deserialized.
- Depth of the object graph.
- Number of references encountered.
- Stream bytes consumed so far.
- Length of the array currently being read.

These limits help reduce risks from object graphs that are too large, too deep, or contain disallowed classes. However, **filters are not a validator for an object's business content**. They do not replace validating field values, relationships between fields, schemas, access permissions, or business rules after data is restored.

For example, a filter can allow the `UserProfile` class and bound input bytes. Yet it cannot verify that `age` must be between 0 and 130, that `email` is properly formatted, or that the sender has permission to edit that profile. Those are content and business checks at a different layer.

After this lesson, learners should be able to:

1. Understand the scope of `ObjectInputFilter` and the metadata it observes.
2. Distinguish object graph structural limits from field content checks.
3. Know that filters do not validate invariants, schemas, authorization, or business semantics.
4. Combine filters with post-read validation and invariants in `Serializable` classes.
5. Recognize risks of custom serialization code and gadget chains.
6. Avoid treating filters as a sandbox or proof that Java native serialization is safe for untrusted data.

## 2. ObjectInputFilter in Java 17

### 2.1. Role of the Filter

`ObjectInputFilter` is an interface in `java.io`. The filter is invoked during deserialization to inspect information about the class and stream state at that moment. It returns one of three decisions:

| Status | Meaning |
|---|---|
| `ALLOWED` | This filter allows proceeding with the inspected information |
| `REJECTED` | Reject the inspected data; reading is blocked |
| `UNDECIDED` | The filter makes no decision; subsequent handling depends on the filter factory/configuration and stream defaults |

A filter is a control mechanism **during deserialization**, not a function receiving an already-constructed object and inspecting its properties.

### 2.2. What Does FilterInfo Provide?

`ObjectInputFilter.FilterInfo` provides the following details:

| Method | Information |
|---|---|
| `serialClass()` | Class under consideration; may be `null` in certain cases such as references or when no class corresponds to the call point |
| `arrayLength()` | Array length; negative if this information does not apply |
| `depth()` | Current depth of the object graph |
| `references()` | Number of object references processed in the stream |
| `streamBytes()` | Number of bytes consumed from the stream at the time the filter is called |

This metadata is useful for limiting resources and classes. The interface does not expose a general API like `getFieldValue("age")` for filters to read fields of the object being constructed.

### 2.3. Filters Are Not Called as Validators for Each Primitive

Primitive values encoded directly in the serialization stream are not object classes for a filter to inspect as separate classes. Strings encoded specifically in the stream also have their own handling rules; never design business logic assuming the filter will be called for every string or every primitive field.

For instance, an `int age` field can carry a negative or abnormally large value. A `maxbytes` limit can bound total data, yet cannot express the rule `age >= 0`. To check that, the class or business layer must validate values after reading.

## 3. What Can Filters Limit?

### 3.1. Restricting Class Types

A filter can reject classes not belonging to the set of types accepted by the application. This is a key mechanism for reducing Java Serialization's attack surface.

For example, a protocol expecting only DTO `UserProfile` can reject other classes appearing in the object graph:

~~~java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }
    if (type == UserProfile.class || type == String.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }
    return ObjectInputFilter.Status.REJECTED;
};
~~~

This is merely an illustration of a narrow allowlist. Real applications must list all valid classes required by the object graph format, including containers or element types if present. Do not broaden allowlists into wide packages just to make tests pass.

### 3.2. Limiting Depth

`depth()` reports the depth of the object graph at the point the filter is called. Setting a limit helps reject overly deep nested graphs:

~~~java
if (info.depth() > 20) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

This limit is useful for tree structures or nested object graphs. It does not check the semantics of parent/child relationships, nor does it ensure element counts in each node are valid.

### 3.3. Limiting Reference Count

`references()` helps bound the number of object references processed:

~~~java
if (info.references() > 10_000) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

This limit can prevent a stream from creating a graph with too many objects/references. However, it is not an exact limit on business records. A collection can have varying serialization representations; reference count is not generally equivalent to valid business record count.

### 3.4. Limiting Stream Bytes

`streamBytes()` allows bounding the amount of data read:

~~~java
if (info.streamBytes() > 1_000_000L) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

Byte limits reduce the likelihood of reading an oversized stream. However, a byte limit does not confirm the payload matches the schema, does not ensure each string has a valid business length, and does not directly cap all processing costs stemming from a small object.

### 3.5. Limiting Array Length

`arrayLength()` can be used to reject arrays exceeding a size threshold:

~~~java
long length = info.arrayLength();
if (length >= 0 && length > 100_000) {
    return ObjectInputFilter.Status.REJECTED;
}
~~~

This limit applies to arrays. It does not automatically equate to an element-count limit for all collections. An `ArrayList` or custom collection type may store data in its own way; combine byte, reference, and class limits with post-read element-count validation.

## 4. Example Configuring a Filter with Resource Limits

A filter can combine multiple limits in the same decision:

~~~java
import java.io.ObjectInputFilter;

static ObjectInputFilter resourceLimits() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 10_000
                || info.streamBytes() > 1_000_000L
                || (info.arrayLength() >= 0
                    && info.arrayLength() > 100_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }
        return ObjectInputFilter.Status.UNDECIDED;
    };
}
~~~

This filter enforces only structural/resource limits. It does not yet provide a class allowlist. In real applications, combine it with an appropriate class policy rather than relying solely on size limits.

One way to combine:

~~~java
static ObjectInputFilter profileFilter() {
    return info -> {
        if (info.depth() > 10
                || info.references() > 100
                || info.streamBytes() > 64 * 1024
                || (info.arrayLength() >= 0
                    && info.arrayLength() > 1_000)) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (type == UserProfile.class || type == String.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
~~~

The numbers are examples only. Actual limits must derive from payload sizes, valid data structures, and application load. If a valid DTO adds date/time types, collections, or enums, the allowlist must accurately reflect that schema.

## 5. Attaching Filters to ObjectInputStream

### 5.1. Per-Stream Filter

A filter can be attached to an `ObjectInputStream` using `setObjectInputFilter`:

~~~java
try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(profileFilter());
    Object value = input.readObject();
}
~~~

Set the filter **before the first object read**. A stream that has already begun reading cannot arbitrarily swap filters; the API restricts configuration timing and count.

### 5.2. Global Filter

Java 17 also supports configuring a JVM-wide filter via the `jdk.serialFilter` property or the `ObjectInputFilter.Config.setSerialFilter` API. A global filter is useful for setting a baseline across serialization flows in the process.

However, an application may have many data types and schemas. An overly narrow global allowlist can break valid flows; an overly broad global allowlist reduces protection effectiveness. Design filter factories and per-boundary policies if the application has multiple serialization sources.

### 5.3. Filter Factories and Multi-Layer Policies

Java 17 has a filter factory mechanism to combine or select filters per stream and context. When an application uses a global filter together with per-stream filters, understand the combination rules in the Javadoc; never assume a new filter always overrides or always appends in the desired way.

Design points to preserve:

- Broadly applied resource-limit baseline.
- Class allowlists tailored by payload type.
- Content and business rules in application validators.

## 6. Pattern-Based Filters Also Inspect Only Metadata

Java provides a filter pattern syntax to configure limits and classes:

~~~java
ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=10;maxrefs=1000;maxbytes=1048576;"
      + "maxarray=10000;com.example.dto.*;!*");
~~~

Parts of the pattern:

- `maxdepth=10`: limits depth.
- `maxrefs=1000`: limits reference count.
- `maxbytes=1048576`: limits bytes read.
- `maxarray=10000`: limits array length.
- `com.example.dto.*`: allows classes in the stated package per pattern rules.
- `!*`: rejects classes not matching earlier allow patterns.

Pattern filters are useful for concise policy declarations. Still, they cannot read field values like `age` or validate an email string. A class allowlist is not an object-value allowlist.

When using patterns, verify package syntax, wildcards, and pattern order against the Java 17 Javadoc. Do not copy a broad pattern from examples without tuning it to your actual object graph.

## 7. What Filters Cannot Replace

### 7.1. Do Not Check Field Values

Suppose an object has the structure:

~~~java
final class UserProfile implements Serializable {
    private String username;
    private int age;
    private String role;
}
~~~

The filter can decide that `UserProfile` is permitted to appear. It cannot verify:

- `username` is non-empty and has an appropriate length.
- `age` falls within a valid range.
- `role` takes only permitted business values.

That is data validation after the object is restored.

### 7.2. Do Not Check Relationships Between Fields

An object may contain:

~~~text
startDate = 2026-12-20
endDate   = 2026-11-01
~~~

Both values individually parse cleanly, yet the relationship `startDate <= endDate` is violated. The filter lacks field information to check such invariants.

Similarly, it does not verify that:

- Line-item totals equal the invoice total.
- Currency matches the account.
- Order status allows transitioning to the new status.
- Referenced IDs point to an existing record the caller is authorized to access.

### 7.3. Do Not Validate Business Schemas

Filters do not replace checking payload version, required fields, enum values, schema migrations, or compatibility between producer and consumer. A class may be allowed while the payload still lacks required data or holds stale-version values.

For long-lived data exchange, maintain an explicit schema and intentional versioning. Native Java serialization has its own versioning mechanism like `serialVersionUID`, yet that does not automatically validate business content.

### 7.4. Do Not Check Authorization

An object having field `role = "ADMIN"` does not mean the sender is authorized to become an admin. The filter knows nothing of the sender's identity, current session, resource permissions, or access policy.

Authorization must be enforced at the business/server layer after data has been validated and bound to a trusted identity. Never use a payload field as proof of authority.

### 7.5. Do Not Guarantee Object Validity Just Because a Class Is Allowed

An allowed class can still receive invalid field data. It may also have custom serialization logic. The filter does not prove every instance of that class is safe or satisfies invariants.

## 8. Validation After Deserialization

After reading an object, verify the expected type and internal data before passing it into business logic.

~~~java
Object value = input.readObject();

if (!(value instanceof UserProfile profile)) {
    throw new InvalidObjectException("Expected UserProfile");
}

validateProfile(profile);
~~~

Validator example:

~~~java
static void validateProfile(UserProfile profile)
        throws InvalidObjectException {
    if (profile.username() == null
            || profile.username().isBlank()
            || profile.username().length() > 80) {
        throw new InvalidObjectException("Invalid username");
    }

    if (profile.age() < 0 || profile.age() > 130) {
        throw new InvalidObjectException("Invalid age");
    }

    if (!Set.of("USER", "EDITOR", "ADMIN").contains(profile.role())) {
        throw new InvalidObjectException("Invalid role");
    }
}
~~~

The rules above are illustrative examples; applications must apply their own actual policies. Checking that `role` is syntactically valid is still insufficient to grant ADMIN privileges; authorization needs a separate check.

### 8.1. Checking Before Objects Enter Domain Logic

A proper workflow:

~~~text
Byte stream
   |
   v
ObjectInputStream + ObjectInputFilter
   |  - class allowlist
   |  - depth / references / bytes / array length
   v
Object graph restored
   |
   v
Check type and invariants
   |  - required fields
   |  - value ranges
   |  - cross-field relationships
   v
Check business rules and authorization
   |
   v
Pass valid data into processing
~~~

The filter is a defense layer at the reading stage. Validation and authorization remain required before trusting or using the data.

## 9. Protecting Invariants Directly Inside Serializable Classes

If a class manages its own invariants, it can validate inside a custom `readObject` after `defaultReadObject`:

~~~java
private void readObject(ObjectInputStream input)
        throws IOException, ClassNotFoundException {
    input.defaultReadObject();

    if (username == null || username.isBlank()) {
        throw new InvalidObjectException("username is required");
    }
    if (age < 0 || age > 130) {
        throw new InvalidObjectException("age is out of range");
    }
}
~~~

When an invariant is violated, throw `InvalidObjectException` to reject the object. This protects class state during deserialization; it is still distinct from a filter.

### 9.1. Validation in readObject Is Not a Sandbox

`readObject` is class-defined code executed during deserialization. If an untrusted class is permitted, its custom serialization methods can run before the caller ever receives the object to validate it.

Therefore:

- Allow only classes the application genuinely trusts and requires.
- Do not arbitrarily allow plugin classes or unknown classes.
- Do not treat post-`readObject` validation as a way to stop side effects from custom code that already executed.
- Avoid native serialization for untrusted data if a safer data format exists.

### 9.2. ObjectInputValidation for Graph Invariants

Java Serialization also provides `ObjectInputValidation` to register a validation callback after the object graph is restored per serialization rules. This mechanism can be useful when invariants span multiple objects in the graph.

It remains validation of the object graph, not a class/resource filter. Do not use it as a replacement for depth, byte, array limits, or class allowlists.

## 10. Gadget Risks and Custom Serialization

A major risk of native deserialization is **gadget chains**: a chain of classes present on the classpath that can combine behavior in methods like `readObject`, `readResolve`, `readExternal`, or logic invoked during restoration to cause unintended side effects.

Filters help reject classes outside the allowlist, thereby shrinking the gadget surface. However, if the allowlist is too broad or permits classes with dangerous behavior, the filter does not guarantee safety.

Points to keep in mind:

- `Serializable` does not mean a class is safe to deserialize from any source.
- `Externalizable` lets a class define its own data-reading logic; that logic requires special review.
- `readObject` can execute code during restoration.
- `readResolve` can replace the returned object with a different object.
- An object graph can contain many interdependent classes, not just the root class.

Do not accept arbitrary Java serialization byte streams from the Internet or users and hope a filter will make everything safe. For untrusted data, prefer formats with schemas and parsers designed for untrusted input, such as JSON/CBOR/Protocol Buffers with explicit validation, or another format suited to your system.

## 11. Combined Example: Filter and Validation Are Two Distinct Steps

The following example uses a small DTO to show clearly that the filter only allows classes and bounds resources, whereas the validator checks content.

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidObjectException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class Main {
    static final class UserProfile implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String username;
        private final int age;
        private final String role;

        UserProfile(String username, int age, String role) {
            this.username = username;
            this.age = age;
            this.role = role;
        }

        String username() { return username; }
        int age() { return age; }
        String role() { return role; }
    }

    static ObjectInputFilter filter() {
        return info -> {
            if (info.depth() > 5
                    || info.references() > 50
                    || info.streamBytes() > 16_384
                    || (info.arrayLength() >= 0
                        && info.arrayLength() > 100)) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }
            if (type == UserProfile.class || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }
            return ObjectInputFilter.Status.REJECTED;
        };
    }

    static void validate(UserProfile profile)
            throws InvalidObjectException {
        if (profile.username() == null
                || profile.username().isBlank()
                || profile.username().length() > 40) {
            throw new InvalidObjectException("Invalid username");
        }
        if (profile.age() < 0 || profile.age() > 130) {
            throw new InvalidObjectException("Invalid age");
        }
        if (!"USER".equals(profile.role())
                && !"EDITOR".equals(profile.role())) {
            throw new InvalidObjectException("Invalid role");
        }
    }

    static byte[] serialize(UserProfile profile) throws IOException {
        try (var bytes = new ByteArrayOutputStream();
             var output = new ObjectOutputStream(bytes)) {
            output.writeObject(profile);
            output.flush();
            return bytes.toByteArray();
        }
    }

    static UserProfile deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {
        try (var input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            input.setObjectInputFilter(filter());

            Object value = input.readObject();
            if (!(value instanceof UserProfile profile)) {
                throw new InvalidObjectException("Unexpected root type");
            }

            // This is content validation; the filter does not perform this step.
            validate(profile);
            return profile;
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] valid = serialize(
                new UserProfile("linh", 28, "USER"));
        UserProfile profile = deserialize(valid);
        System.out.println(profile.username()); // linh

        byte[] invalidContent = serialize(
                new UserProfile("linh", -5, "USER"));
        try {
            deserialize(invalidContent);
        } catch (InvalidObjectException ex) {
            System.out.println(ex.getMessage()); // Invalid age
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 Main.java
java Main
~~~

Output:

~~~text
linh
Invalid age
~~~

Things to observe:

1. Both payloads contain the allowlisted `UserProfile` class and fall below resource limits.
2. The filter does not know whether `age` is negative or positive; it does not inspect field values for business evaluation.
3. The object with a negative age is still restored, and then rejected by the validator.
4. If the class graph contained a disallowed class, the filter could reject it right during reading.

The example uses only a trusted DTO and illustrates the boundary between the two kinds of checks. It does not prove native serialization is safe for arbitrary data.

## 12. Boundaries of Each Check Type

| Requirement | ObjectInputFilter | Validator/Domain Layer |
|---|---|---|
| Reject classes not in allowlist | Yes | Can check root type, yet too late for some side effects during deserialization |
| Limit object graph depth | Yes | Can check structure after construction, yet cannot prevent already-incurred cost |
| Limit reference/byte counts | Yes | Does not replace stream-reading limits |
| Limit array length | Yes | Can check collection/array size after reading |
| Check non-empty strings | No | Yes |
| Check age within range | No | Yes |
| Check relationship between two fields | No | Yes |
| Check business schema/version | No | Yes |
| Check sender authorization | No | Authorization layer |
| Prevent all side effects from custom serialization code | No | Post-read validation cannot undo side effects that already occurred |

No single check layer replaces all other layers. Safe design requires input byte limits, class/resource filtering, content validation, and proper authorization.

## 13. Common Mistakes

### 13.1. Thinking a Class Allowlist Means the Payload Is Valid

An object of an allowed class can still have invalid fields. For instance, `age = -5` is still an instance of `UserProfile`.

**How to handle:** validate fields and invariants after reading or inside an appropriate custom `readObject`.

### 13.2. Using maxbytes to Replace All Other Limits

A small payload can still contain invalid business values or trigger unwanted logic in an allowed class. Conversely, a valid payload may exceed a byte limit if configured too low.

**How to handle:** set each limit according to its target: bytes, depth, references, array length, and classes.

### 13.3. Thinking maxarray Bounds Element Count of All Collections

`arrayLength` only provides the length of the array being inspected. Not every collection is represented directly as a serialized array.

**How to handle:** check collection size after reading and limit overall resources in the filter.

### 13.4. Letting the Filter Return UNDECIDED for All Classes

`UNDECIDED` is not rejection. If no other filter rejects, the stream may proceed depending on overall policy.

**How to handle:** use an explicit allowlist and return `REJECTED` for unaccepted classes.

### 13.5. Allowing Broad Packages Unnecessarily

Patterns such as `com.example.**` can allow more classes than the object graph actually requires.

**How to handle:** list minimal packages/classes and update when schemas change.

### 13.6. Thinking Validation After readObject Stops Custom Code Execution

Custom serialization methods may have already run before the caller receives the object. Validators cannot undo side effects.

**How to handle:** do not allow untrusted classes; prefer data formats that do not trigger native object deserialization for untrusted input.

### 13.7. Treating Filters as a Sandbox

Filters do not isolate file, network, thread, reflection, or native code permissions of allowed classes.

**How to handle:** deserialize only trusted classes and use proper isolation mechanisms if untrusted code must be executed.

## 14. Practice Exercises

### Exercise 1 — Distinguishing Metadata and Content

A payload contains `UserProfile(username=" ", age=-2, role="ROOT")`. The filter allows `UserProfile` and bounds depth/bytes. List which checks the filter can perform and which checks must belong to the validator.

**Hint:** class and resource metadata belong to the filter; username, age, role, and permission to use a role belong to subsequent layers.

### Exercise 2 — Adding Resource Limits

Write a filter that rejects when:

- Depth exceeds 8.
- References exceed 500.
- Stream bytes exceed 256 KiB.
- Array length exceeds 4096.

Then add an allowlist permitting only two specific DTO classes.

### Exercise 3 — Distinguishing Collection Size and Array Length

An `ArrayList` has 50,000 elements. Explain why `maxarray=1000` is not a general contract saying every List can have at most 1000 elements. Propose checking size after deserialization and bounding references/bytes during reading.

### Exercise 4 — Checking Invariants

Write a `Booking` class with `startDate` and `endDate`. The filter allows that class. Add validation to reject when the end date precedes the start date.

### Exercise 5 — Custom readObject

Add `readObject` to a DTO to check required fields after `defaultReadObject` and throw `InvalidObjectException` if invalid. Explain why this mechanism protects class invariants yet is not a sandbox for other classes in the graph.

### Exercise 6 — Designing Data Boundaries

A service receives serialization byte streams from external customers. Propose an alternative design using explicit DTOs/schemas and parsers for untrusted data. State the remaining role of ObjectInputFilter if the system still must read an internal Java serialization stream.

## 15. Completion Criteria

A learner masters this lesson when able to:

1. Describe how ObjectInputFilter inspects classes and structural/resource metadata during deserialization.
2. Explain the meaning of `serialClass`, `arrayLength`, `depth`, `references`, and `streamBytes`.
3. Write a filter with an allowlist and suitable limits.
4. Distinguish `ALLOWED`, `REJECTED`, and `UNDECIDED`.
5. Clearly explain that filters do not read or validate field values, cross-field relationships, schemas, business rules, or access permissions.
6. Write post-read validators and/or invariant checks in `readObject` appropriately.
7. Explain why custom serialization code and gadget chains remain risks.
8. Avoid treating filters as a sandbox or guaranteeing that native serialization is safe for untrusted input.
9. Choose formats with schemas and parsers suited to untrusted data exchange.

## 16. Official Documentation

- [Java SE 17 API — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): Filter, FilterInfo, Status, and provided metadata.
- [Java SE 17 API — `ObjectInputFilter.Config`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): configuring filters, patterns, and filter factories.
- [Java SE 17 API — `ObjectInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): reading objects and attaching per-stream filters.
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): goals and scope of serialization filtering.
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter factories and context-specific filter policies.
- [Java SE 17 API — `ObjectInputValidation`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputValidation.html): callback for validating an object graph after restoration.
- [Java SE 17 API — `InvalidObjectException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InvalidObjectException.html): rejecting an object with invalid state.

**Key takeaway:** ObjectInputFilter is a guardrail for classes and object graph resources during deserialization. It does not stand in for validators checking fields, invariants, schemas, business relationships, or access permissions. Combine allowlists and resource limits with content validation and authorization, and avoid native Java deserialization for untrusted data when safer format choices exist.
