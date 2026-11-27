# Rejecting Undecided Classes with `rejectUndecidedClass` in Java 17

Java Serialization allows converting an object graph into bytes and restoring the object graph from bytes. When reading serialized data, `ObjectInputFilter` can inspect the class being instantiated and resource metrics of the deserialization process. One of the three filter results is `UNDECIDED` — a status easily mistaken for rejection.

In reality, **`UNDECIDED` means the filter has not made a decision**. If no filter returns `REJECTED`, deserialization can still continue. That can allow an unexpected class outside the intended list to slip through when a filter checks only a few familiar classes and returns `UNDECIDED` for remaining classes.

Java 17 provides `ObjectInputFilter.rejectUndecidedClass(filter)` to wrap an existing filter: classes not explicitly confirmed by the filter are rejected, with dedicated handling rules for arrays and metric-only checks. This lesson explains how to use that API to build explicit allowlists, combine resource limits, and apply filters before calling `readObject`.

> **Version:** `ObjectInputFilter` has existed since Java 9. Factory methods `allowFilter`, `rejectFilter`, `merge`, and `rejectUndecidedClass` were introduced in Java 17. These are standard APIs, not preview features.

## 1. Why Reject UNDECIDED Results?

A deserialization filter returns one of three statuses:

| Status | Meaning | Effect |
|---|---|---|
| `ALLOWED` | Filter confirms data is permitted | Filter does not object to the current class/object |
| `REJECTED` | Filter determines data is not permitted | Deserialization is rejected |
| `UNDECIDED` | Filter makes no decision | Filter neither allows nor rejects |

Key point: **`UNDECIDED` is not synonymous with `REJECTED`**. It signifies the filter has no opinion about the check under consideration. If the final result remains `UNDECIDED`, the deserialization mechanism does not treat that as a rejection command.

Example of a filter allowing only class `com.example.dto.Message`:

~~~java
ObjectInputFilter filter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == Message.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

This filter only confirms `Message`. For all other classes, it returns `UNDECIDED`. If this filter is the only decision applied, other classes are not yet rejected.

This is the core gap `rejectUndecidedClass` addresses: **converting undecided statuses into rejections for classes**, so that the policy accepts only confirmed classes.

## 2. How Does rejectUndecidedClass Work?

Syntax:

~~~java
ObjectInputFilter strictFilter =
        ObjectInputFilter.rejectUndecidedClass(existingFilter);
~~~

The method takes an `ObjectInputFilter` and returns a wrapper filter around it. The new filter invokes the original filter, then processes the result per the API's rules.

For a regular non-array class:

- Original filter returns `ALLOWED` → stays `ALLOWED`.
- Original filter returns `REJECTED` → stays `REJECTED`.
- Original filter returns `UNDECIDED` → converted to `REJECTED`.

Thus, the wrapped filter becomes a **fail-closed policy for unrecognized classes**: without an explicit allow decision, the class is rejected.

Example:

~~~java
ObjectInputFilter allowMessage = info -> {
    Class<?> type = info.serialClass();

    if (type == Message.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter rejectUnknown =
        ObjectInputFilter.rejectUndecidedClass(allowMessage);
~~~

If the class under inspection is `Message`, the result is `ALLOWED`. If it is `UnexpectedData` and the original filter makes no decision, the wrapper converts `UNDECIDED` to `REJECTED`.

### 2.1. Does Not Mutate the Original Filter

`rejectUndecidedClass` creates and returns a new filter. It does not modify the input filter object:

~~~java
ObjectInputFilter base = createAllowlistFilter();
ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(base);
~~~

When attaching to `ObjectInputStream`, use the `strict` variable to get undecided-class rejection behavior. Creating the wrapper while still installing `base` has no effect.

### 2.2. Filter Argument Must Not Be Null

The input filter must be non-null. Passing null causes a `NullPointerException` when creating the wrapper.

~~~java
ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(null); // Invalid
~~~

Initialize the base filter before wrapping it.

## 3. Special Cases: Metric-Only and Arrays

The method name contains `Class` because the wrapper focuses on converting `UNDECIDED` to `REJECTED` for classes. It does not blindly turn every `UNDECIDED` across all calls into `REJECTED`.

Under the Java 17 contract, the wrapper has the following special cases:

| Information from FilterInfo | Result When Original Filter Is UNDECIDED |
|---|---|
| `serialClass() == null` | Remains `UNDECIDED` |
| Regular non-array class | `REJECTED` |
| Array with reference component type | Checks root component type |
| Array with primitive component type | Remains `UNDECIDED` |

### 3.1. Metric-Only Calls Are Not Converted to REJECTED

A filter can be called with `serialClass() == null`. In that case, available information contains only metrics such as:

- `depth()`: current depth of the object graph.
- `references()`: number of object references read so far.
- `streamBytes()`: number of bytes read from the stream.
- `arrayLength()`: array length if the check pertains to an array; returns -1 if not an array.

When there is no class to evaluate, `rejectUndecidedClass` preserves `UNDECIDED`. That prevents the wrapper from mistaking a resource-limit check for an unallowed class.

**Implication:** `rejectUndecidedClass` does not replace a resource-limit filter. If you need to block overly deep object graphs, excessive references, oversized streams, or overly long arrays, add metric checks separately.

### 3.2. Arrays Are Checked Through Their Component Type

Suppose the base filter allows only `Message.class`:

~~~java
ObjectInputFilter allowMessage = ObjectInputFilter.allowFilter(
        type -> type == Message.class,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(allowMessage);
~~~

When inspecting `Message[]`, the wrapper does not look only at the result for the array class. If the initial result is `UNDECIDED`, it determines the root component type and invokes the filter for that type:

- Component type is `ALLOWED` → array is `ALLOWED`.
- Component type is `REJECTED` or remains `UNDECIDED` → array is `REJECTED`.

Therefore, if `Message.class` is allowlisted, one-dimensional or multi-dimensional arrays whose root component type is `Message` can be permitted under this rule.

### 3.3. Primitive Arrays Are a Special Case

For arrays such as `byte[]` or `int[]`, the root component type is a primitive type. If the base filter returns `UNDECIDED` for the array, the wrapper keeps `UNDECIDED` rather than rejecting automatically.

This is explicitly specified behavior; do not assume `rejectUndecidedClass` will reject every array lacking an `ALLOWED` result.

If the application does not accept primitive arrays, add an explicit rule:

~~~java
ObjectInputFilter rejectPrimitiveArrays = info -> {
    Class<?> type = info.serialClass();

    if (type != null
            && type.isArray()
            && type.getComponentType().isPrimitive()) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

The snippet above illustrates only one-dimensional arrays. For multi-dimensional arrays, `getComponentType()` can return another array class; if all arrays with a primitive base component must be forbidden, loop through dimensions to find the final component type.

## 4. Building an Allowlist with allowFilter

Java 17 adds `ObjectInputFilter.allowFilter(predicate, otherStatus)` to construct a filter from a `Class<?>` predicate.

Syntax:

~~~java
ObjectInputFilter allowFilter =
        ObjectInputFilter.allowFilter(
                classPredicate,
                ObjectInputFilter.Status.UNDECIDED
        );
~~~

Rules:

- If `serialClass()` is null, the result is `UNDECIDED`.
- If the predicate returns true for the class, the result is `ALLOWED`.
- If the predicate returns false, the result is `otherStatus`.

To use alongside `rejectUndecidedClass`, choose `UNDECIDED` as `otherStatus`. Thus the base filter confirms only classes in the allowlist; the wrapper turns all unconfirmed regular classes into `REJECTED`.

### 4.1. Exact-Class Allowlist

~~~java
Set<Class<?>> allowedClasses = Set.of(
        Message.class,
        Address.class
);

ObjectInputFilter allowKnownClasses = ObjectInputFilter.allowFilter(
        allowedClasses::contains,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter strictFilter =
        ObjectInputFilter.rejectUndecidedClass(allowKnownClasses);
~~~

This approach fits when the list of classes to read is known precisely. Using exact `Class` objects avoids accidentally allowing another class merely because it resides in the same package or has a similar name.

If the object graph needs other classes such as collection implementations or helper data types, verify whether they genuinely belong to the data contract before adding them to the allowlist. Do not widen the allowlist arbitrarily just to make one specific stream readable.

### 4.2. Allowlist by Package or Hierarchy

Predicates can be used:

~~~java
ObjectInputFilter allowDtos = ObjectInputFilter.allowFilter(
        type -> type.getPackageName().equals("com.example.dto"),
        ObjectInputFilter.Status.UNDECIDED
);
~~~

Or allowing classes implementing a marker interface:

~~~java
ObjectInputFilter allowDomainTypes = ObjectInputFilter.allowFilter(
        DomainMessage.class::isAssignableFrom,
        ObjectInputFilter.Status.UNDECIDED
);
~~~

Exercise caution: allowing an entire package or every class in a broader hierarchy can admit unexpected types. For untrusted data, allowlists of specific classes are usually easier to control.

### 4.3. Do Not Return ALLOWED for All Classes

A filter like this is not a safe allowlist:

~~~java
ObjectInputFilter allowEverything = info ->
        ObjectInputFilter.Status.ALLOWED;
~~~

It confirms every class the filter is called to inspect. Wrapping it with `rejectUndecidedClass` does not tighten the policy either, because the base filter never returns `UNDECIDED`.

The wrapper only converts undecided results; it cannot deduce which classes are safe on its own.

## 5. Combining an Allowlist with Resource Limits

Class filtering and resource limits solve two different problems:

- Allowlists control **data types** that may appear.
- Resource filters control **object graph scale** and the volume of data read.

A class in the allowlist can still appear in an overly deep or oversized object graph. Therefore, practical filters usually need both.

### 5.1. Checking Metrics

Limit example:

~~~java
ObjectInputFilter resourceLimits = info -> {
    if (info.depth() > 20) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.references() > 10_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.streamBytes() > 1_000_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.arrayLength() >= 0 && info.arrayLength() > 100_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

The numbers above are illustrative examples only. Appropriate values must come from the application's valid data size, object graph depth, and memory budget.

This filter returns `UNDECIDED` when limits are not exceeded because it decides only on metrics. It does not assert that the class being read is safe.

### 5.2. Merging Filters with merge

`ObjectInputFilter.merge(filter, anotherFilter)` combines the results of two filters:

1. If either returns `REJECTED`, the result is `REJECTED`.
2. If neither rejects and at least one returns `ALLOWED`, the result is `ALLOWED`.
3. If both are `UNDECIDED`, the result is `UNDECIDED`.

They can be combined as follows:

~~~java
ObjectInputFilter classAllowlist = ObjectInputFilter.allowFilter(
        allowedClasses::contains,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter rejectUnknownClasses =
        ObjectInputFilter.rejectUndecidedClass(classAllowlist);

ObjectInputFilter combined = ObjectInputFilter.merge(
        resourceLimits,
        rejectUnknownClasses
);
~~~

In this configuration:

- Classes in the allowlist are confirmed `ALLOWED` by the class filter.
- Regular classes outside the allowlist are turned into `REJECTED` by the wrapper.
- Metrics exceeding limits are `REJECTED` by the resource filter.
- Valid metrics not tied to a class can remain `UNDECIDED`.

**REJECTED always wins on merge.** Thus, a filter allowing a class cannot override a rejection produced by the resource filter.

### 5.3. Do Not Confuse merge with a Simple OR

`merge` does not mean "if one filter allows, ignore all remaining filters". If filter A returns `ALLOWED` while filter B returns `REJECTED`, the final result is still `REJECTED`.

This is a key property when combining allowlists with resource limits or multi-layer policies.

## 6. Installing a Filter on ObjectInputStream

Creating a filter is not enough. The application must attach the filter to `ObjectInputStream` before reading objects.

~~~java
try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(strictFilter);

    Object value = input.readObject();
}
~~~

Order to preserve:

1. Create the input stream.
2. Create or select a filter matching the context.
3. Call `setObjectInputFilter` before reading objects.
4. Call `readObject`.
5. Handle the result and exceptions.
6. Close the stream using try-with-resources.

If you set the filter after reading data has started, you can no longer protect objects already restored earlier. The simplest design is setting the filter right after creating the stream and before the first `readObject`.

### 6.1. Example Installing an Allowlist on a Stream

~~~java
Set<Class<?>> allowed = Set.of(Message.class, Address.class);

ObjectInputFilter allowKnown = ObjectInputFilter.allowFilter(
        allowed::contains,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(allowKnown);

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(strict);

    Message message = (Message) input.readObject();
    System.out.println(message.text());
}
~~~

If the stream contains an unallowlisted regular class, the wrapper returns `REJECTED` when that class is checked and reading aborts with a deserialization error.

### 6.2. Per-Stream Filtering

`setObjectInputFilter` sets a filter for one specific `ObjectInputStream`. This is useful when data streams have different contracts:

- Config files contain only a fixed set of DTOs.
- Messages from an internal component have their own schema.
- Archived data has its own version and supported type set.

Each stream should use an allowlist tailored to its data format. Do not share an overly broad allowlist across all sources merely to reuse one configuration snippet.

## 7. Complete Example: Allowing Only Message

The following example creates a serialized object in memory, then reads it back with a filter allowing only `Message`. An `Unexpected` class demonstrates the rejected case.

Create the file **`RejectUndecidedDemo.java`**:

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
import java.util.Set;

public class RejectUndecidedDemo {

    static final class Message implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String text;

        Message(String text) {
            this.text = text;
        }

        String text() {
            return text;
        }
    }

    static final class Unexpected implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final int code = 99;
    }

    private static final Set<Class<?>> ALLOWED_CLASSES =
            Set.of(Message.class, String.class);

    static ObjectInputFilter createFilter() {
        ObjectInputFilter allowKnownClasses = ObjectInputFilter.allowFilter(
                ALLOWED_CLASSES::contains,
                ObjectInputFilter.Status.UNDECIDED
        );

        ObjectInputFilter rejectUnknownClasses =
                ObjectInputFilter.rejectUndecidedClass(allowKnownClasses);

        ObjectInputFilter resourceLimits = info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 100_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            if (info.arrayLength() >= 0 && info.arrayLength() > 1_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            return ObjectInputFilter.Status.UNDECIDED;
        };

        return ObjectInputFilter.merge(
                resourceLimits,
                rejectUnknownClasses
        );
    }

    static byte[] serialize(Object value) throws IOException {
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(bytes)) {

            output.writeObject(value);
            output.flush();
            return bytes.toByteArray();
        }
    }

    static Object deserialize(byte[] bytes)
            throws IOException, ClassNotFoundException {

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {

            // Must install the filter before readObject().
            input.setObjectInputFilter(createFilter());

            return input.readObject();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] validBytes = serialize(new Message("Hello Java 17"));

        Message message = (Message) deserialize(validBytes);
        System.out.println(message.text());

        byte[] unexpectedBytes = serialize(new Unexpected());

        try {
            deserialize(unexpectedBytes);
            System.out.println("Did not expect this class to be accepted");
        } catch (InvalidClassException e) {
            System.out.println("Rejected class outside allowlist");
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac --release 17 RejectUndecidedDemo.java
java RejectUndecidedDemo
~~~

Expected output:

~~~text
Hello Java 17
Rejected class outside allowlist
~~~

Key takeaways in the example:

- `allowFilter` confirms `Message.class`.
- For classes not in the set, the base filter returns `UNDECIDED`.
- `rejectUndecidedClass` converts that result to `REJECTED`.
- `resourceLimits` rejects object graphs exceeding set limits.
- `merge` combines both policies while preserving priority for rejection.
- The filter is attached before calling `readObject`.

In a real application, the list of permitted types must reflect the exact data schema. If the object graph includes collections, subtypes, or supporting types, review and incorporate them into the policy intentionally.

## 8. Using rejectUndecidedClass with Pattern Filters

Besides predicates, Java supports building filters from pattern strings:

~~~java
ObjectInputFilter patternFilter =
        ObjectInputFilter.Config.createFilter(
                "com.example.dto.*;!*"
        );
~~~

A pattern filter allows classes matching the stated package and rejects non-matching classes per the pattern. The `!*` token is the pattern that rejects remaining classes.

Because a pattern filter already has an explicit rejection rule for non-matching classes, the `rejectUndecidedClass` wrapper is not always necessary. It is more useful when the underlying filter intentionally returns `UNDECIDED` for classes outside the scope it understands, and an outer policy layer wants to convert that lack of decision into rejection.

Example:

~~~java
ObjectInputFilter packageFilter =
        ObjectInputFilter.Config.createFilter(
                "com.example.dto.*"
        );

ObjectInputFilter strictPackageFilter =
        ObjectInputFilter.rejectUndecidedClass(packageFilter);
~~~

Read pattern syntax carefully and inspect supporting types actually present in the object graph. A broad package pattern can allow more classes than the application needs.

### 8.1. Resource Limits in Pattern Strings

Pattern filters support limits such as:

| Pattern | Meaning |
|---|---|
| `maxdepth=20` | Limits object graph depth |
| `maxrefs=10000` | Limits number of object references |
| `maxbytes=1000000` | Limits stream bytes |
| `maxarray=100000` | Limits array length |

Example:

~~~java
ObjectInputFilter patternFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=10000;"
                + "maxbytes=1000000;maxarray=100000;"
                + "com.example.dto.*;!*"
        );
~~~

These limits are policies tailored to the application's actual data, not default numbers suited to every system. Choose thresholds based on valid object graphs and test cases near the limits as well.

## 9. Distinguishing rejectUndecidedClass from rejectFilter

Java 17 also has `ObjectInputFilter.rejectFilter(predicate, otherStatus)`. The two methods serve different purposes:

| API | Meaning |
|---|---|
| `rejectFilter(predicate, otherStatus)` | Rejects when the predicate is true; otherwise returns the specified status |
| `rejectUndecidedClass(filter)` | Wraps an existing filter and converts `UNDECIDED` to `REJECTED` for classes, following special array rules |

Example of `rejectFilter`:

~~~java
ObjectInputFilter rejectProxyLikeClass = ObjectInputFilter.rejectFilter(
        type -> type.getName().contains("Unexpected"),
        ObjectInputFilter.Status.UNDECIDED
);
~~~

This filter rejects classes whose names satisfy the predicate. Other classes return `UNDECIDED`. If you want a policy accepting only confirmed classes, wrap the filter with `rejectUndecidedClass` or combine it with an appropriate allowlist.

Do not confuse `rejectFilter` with `rejectUndecidedClass`: one decides rejections conditionally, while the other handles undecided results from another filter.

## 10. Statuses When Combining Multiple Filters

When building a multi-layer filter, track the returned statuses carefully:

~~~text
Class-checking filter
    |
    +-- ALLOWED ------> keep ALLOWED
    |
    +-- REJECTED -----> keep REJECTED
    |
    +-- UNDECIDED
            |
            v
    rejectUndecidedClass
            |
            +-- regular class ----> REJECTED
            |
            +-- serialClass null -> UNDECIDED
            |
            +-- primitive array --> UNDECIDED
            |
            +-- reference array --> check base component
                                      |
                                      +-- ALLOWED -> ALLOWED
                                      +-- other   -> REJECTED
~~~

Then, if using `merge` with a resource filter, any rejection from either filter is preserved.

### 10.1. One Filter Returning ALLOWED Does Not Bypass Limits

Example:

- Filter A confirms `Message` and returns `ALLOWED`.
- Filter B sees the stream exceeds `maxbytes` and returns `REJECTED`.
- The composite filter from `merge` returns `REJECTED`.

Do not let allowlist logic override resource limits.

### 10.2. Metric Filters Should Not Return ALLOWED for All Classes

If a resource filter returns `ALLOWED` when metrics are valid without checking the class, it can cause a merged filter to return `ALLOWED` even when the class filter returned `UNDECIDED`. In another configuration, that could weaken the class policy.

The clean approach is for resource filters to return `UNDECIDED` when metrics are valid and return `REJECTED` only when exceeding limits. Class filters remain responsible for deciding whether classes are allowed.

## 11. Limitations and Security Considerations

`rejectUndecidedClass` is a helper for filter policies, not a complete security solution for all cases.

### 11.1. Allow Only Classes Actually Needed

A broad allowlist like an entire package or an entire JDK module can include unneeded types. Start from the expected data schema, then add individual types with clear justification.

### 11.2. Check Resource Limits Separately

The wrapper does not automatically limit:

- Object graph depth.
- Object reference count.
- Stream byte size.
- Array length.

Combine metric filters or pattern limits to reduce the risk of excessive CPU and memory consumption.

### 11.3. Filters Do Not Validate Business Validity

An object belonging to an allowlisted class can still contain invalid data, such as:

- Empty or malformed IDs.
- Negative quantities.
- States unsupported by business logic.
- Strings exceeding application limits.

After deserialization, you must still validate data and domain model invariants.

### 11.4. Do Not Treat Java Serialization as a Safe Default Exchange Format

When designing a new system, consider data formats with explicit schemas and parsers suited to your needs. If Java serialized data must be read, accept data only from trusted sources or apply strict filters alongside application-layer data validation.

Filters reduce the attack surface; they do not make deserializing untrusted data harmless in every scenario.

### 11.5. Do Not Reuse One Allowlist Across All Schema Versions Unchecked

When schemas evolve, the set of valid classes may change. Manage data versioning and filter policies accordingly. Do not add a large package to an allowlist just for temporary compatibility with an old file without reviewing the newly permitted types.

## 12. Common Mistakes

| Symptom | Cause | How to Handle |
|---|---|---|
| Unknown classes are still read | Base filter returns `UNDECIDED` and no wrapper/policy rejects | Wrap with `rejectUndecidedClass` |
| Created wrapper yet unknown classes still pass | Still installed base filter on the stream instead of wrapper filter | Call `setObjectInputFilter(strictFilter)` |
| All classes are rejected | Allowlist missing required classes or predicate does not match | Identify class graph and update allowlist in a controlled way |
| Primitive arrays are still accepted | Wrapper preserves `UNDECIDED` for arrays with primitive base component | Add explicit array rule if rejection is required |
| Object arrays are rejected | Base component type is not allowed by the base filter | Identify component class and add if genuinely valid |
| Overly deep streams are still read | Filtering only classes without checking metrics | Check depth, references, bytes, and array length |
| Creating filter throws NullPointerException | Passed null base filter | Initialize a valid filter before wrapping |
| Calling readObject before setting filter | Filter was attached too late | Set filter immediately after creating ObjectInputStream |
| Merge yields rejected even though one filter allowed | Another filter returned REJECTED; REJECTED takes precedence | Inspect each filter and the rejection reason |
| Allowlisted object still has wrong data | Filter controls only classes/metrics, not business validation | Check fields and domain invariants after reading |

## 13. Practice Exercises

### Exercise 1: Distinguishing the Three Statuses

A filter returns `ALLOWED` for `Message.class`, `REJECTED` for `LegacyPayload.class`, and `UNDECIDED` for other classes.

**Question:** After wrapping with `rejectUndecidedClass`, what result does a regular class other than `Message` and `LegacyPayload` get?

**Answer:** The original filter's `UNDECIDED` is converted to `REJECTED`. Existing `ALLOWED` and `REJECTED` results are preserved.

### Exercise 2: Creating an Allowlist with allowFilter

Write a filter confirming only `Message.class` and `Address.class`; other classes return `UNDECIDED`. Then wrap it with `rejectUndecidedClass`.

**Suggested answer:**

~~~java
Set<Class<?>> allowed = Set.of(Message.class, Address.class);

ObjectInputFilter base = ObjectInputFilter.allowFilter(
        allowed::contains,
        ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter strict =
        ObjectInputFilter.rejectUndecidedClass(base);
~~~

### Exercise 3: Why Is Null serialClass Not Rejected?

**Answer:** This is a filter invocation providing metric information without a specific class. `rejectUndecidedClass` preserves `UNDECIDED` in that case so a metric filter can handle depth, references, stream bytes, or array length separately.

### Exercise 4: Are Primitive Arrays Rejected?

A base filter returns `UNDECIDED` for all classes. After wrapping, what happens to `byte[]`?

**Answer:** The wrapper preserves `UNDECIDED` for arrays whose base component type is primitive. If the application needs to reject `byte[]` or other primitive arrays, an explicit rule must be added.

### Exercise 5: Combining a Resource Filter

Write a filter that rejects when depth exceeds 10 or stream bytes exceed 500,000; otherwise return `UNDECIDED`.

**Answer:**

~~~java
ObjectInputFilter limits = info -> {
    if (info.depth() > 10 || info.streamBytes() > 500_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

### Exercise 6: Why Does Merge Still Reject?

Filter A returns `ALLOWED`, filter B returns `REJECTED`. What is the result of `ObjectInputFilter.merge(A, B)`?

**Answer:** `REJECTED`. In merge, a single filter rejecting causes the combined result to be rejected.

### Exercise 7: Setting the Filter at the Right Time

**Question:** Should `setObjectInputFilter` be called before or after `readObject`?

**Answer:** Before the first object read. Install the filter right after creating `ObjectInputStream` so the object graph is inspected during deserialization.

## 14. Key Points to Remember

When using `rejectUndecidedClass` in Java 17:

1. Understand `UNDECIDED` means no decision yet; it does not automatically mean reject.
2. Create a base filter that explicitly confirms allowed classes.
3. Wrap the filter with `ObjectInputFilter.rejectUndecidedClass(filter)` to reject unconfirmed regular classes.
4. Remember the special handling for metric-only checks, reference arrays, and primitive arrays.
5. Combine a resource filter for depth, references, stream bytes, and array length.
6. Use `ObjectInputFilter.merge` to combine policies; `REJECTED` always takes priority.
7. Install the filter on `ObjectInputStream` before calling `readObject`.
8. Validate business data after reading; a class allowlist does not confirm valid field values.

`rejectUndecidedClass` fits when an existing filter knows only how to confirm a specific set of classes and you want all regular classes outside that set rejected. Use it together with allowlists and resource limits designed for the exact data format your application must read.

## 15. References

- [Oracle Java SE 17 — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): `Status`, `FilterInfo`, `allowFilter`, `rejectFilter`, `merge`, and `rejectUndecidedClass`.
- [Oracle Java SE 17 — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): attaching filters to streams and deserializing objects.
- [Oracle Java SE 17 — Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html): designing class-based filters, pattern filters, resource limits, and applying filters.
- [OpenJDK JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290): filtering incoming Java Serialization data.
- [OpenJDK JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): context-specific filter factories in Java 17.
