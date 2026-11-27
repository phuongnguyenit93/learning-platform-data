# Combining Policies with ObjectInputFilter.merge in Java 17

**Topic:** Java 17 → Deserialization Filters  
**Focus:** Combining multiple deserialization filtering policies with `ObjectInputFilter.merge`; understanding the precedence of `REJECTED`, `ALLOWED`, and `UNDECIDED`, how to handle null filters, and how to combine an allowlist with resource limits to protect `ObjectInputStream`.

Java 17 provides `ObjectInputFilter.merge` to combine two filters into a composite filter. This API was added in Java 17 alongside the `allowFilter`, `rejectFilter`, and `rejectUndecidedClass` utilities. It is useful when each component is responsible for one part of the policy: the first filter checks class types, the second bounds object graph depth or size, while another filter may apply rules specific to a processing context.

The most important rule to remember is `merge`'s combination rule:

- If **either filter returns `REJECTED`**, the result is `REJECTED`.
- If neither filter rejects and **at least one filter returns `ALLOWED`**, the result is `ALLOWED`.
- If both return `UNDECIDED`, the result is `UNDECIDED`.

Therefore, `merge` is not an AND operation requiring both filters to return `ALLOWED`. It uses the principle that **rejection has veto power; one allow decision suffices to yield an allow result if no filter rejects**. How each filter's statuses are designed determines the final policy.

## 1. At What Stage Is ObjectInputFilter Used?

Java Serialization can reconstruct an object graph from a byte stream. If data comes from an untrusted source, deserialized classes and object graph structures can introduce risks: instantiating unexpected objects, consuming memory, creating overly deep graphs, or containing oversized arrays.

`ObjectInputFilter` enables inspecting object graph information while `ObjectInputStream` reads data. The filter can evaluate:

- The class of the object about to be deserialized.
- Array length.
- Current depth of the object graph.
- Number of object references read so far.
- Number of bytes consumed from the stream.

The filter is invoked as the stream deserializes the object graph. It can return one of three statuses:

| Status | Meaning |
| --- | --- |
| `ALLOWED` | The filter accepts the information being checked. |
| `REJECTED` | The filter rejects; `ObjectInputStream` aborts deserialization of that object and typically throws `InvalidClassException`. |
| `UNDECIDED` | The filter makes no decision for this information. |

**`UNDECIDED` is not synonymous with rejection.** If the active filter returns `UNDECIDED`, deserialization can proceed as if that filter made no decision. For a strict allowlist, ensure unlisted classes are not left in `UNDECIDED` unintentionally.

Filters are not invoked for primitive values and `java.lang.String` instances encoded directly in the serialization stream. For arrays, the filter receives the array class along with its length; for previously read object references, `serialClass()` can be `null` and the filter can still inspect metrics.

## 2. Syntax and Contract of ObjectInputFilter.merge

Syntax:

~~~java
ObjectInputFilter combined =
    ObjectInputFilter.merge(filter, anotherFilter);
~~~

Method available since Java 17:

~~~java
static ObjectInputFilter merge(
    ObjectInputFilter filter,
    ObjectInputFilter anotherFilter
)
~~~

Contract:

1. `filter` (first argument) must be non-null.
2. If `anotherFilter` (second argument) is `null`, the method returns `filter`.
3. If both filters are non-null, the method returns a composite filter that invokes the filters in order and combines their statuses.
4. The first filter is called first. If it returns `REJECTED`, the second filter does not need to be called.
5. If the first filter does not reject, the second filter is called. Either filter returning `REJECTED` causes the final result to be `REJECTED`.

Null cases:

| Call | Result |
| --- | --- |
| `ObjectInputFilter.merge(filterA, filterB)` | Creates a combined filter. |
| `ObjectInputFilter.merge(filterA, null)` | Returns `filterA`. |
| `ObjectInputFilter.merge(null, filterB)` | Throws `NullPointerException`. |
| `ObjectInputFilter.merge(null, null)` | Throws `NullPointerException`. |

Because the first argument must be non-null, if an application has two optional filters it must handle a null first filter before calling `merge`.

## 3. Three-Status Truth Table

Here is the truth table when both filters are present:

| First Filter | Second Filter | Merge Result |
| --- | --- | --- |
| `REJECTED` | `REJECTED` | `REJECTED` |
| `REJECTED` | `ALLOWED` | `REJECTED` |
| `REJECTED` | `UNDECIDED` | `REJECTED` |
| `ALLOWED` | `REJECTED` | `REJECTED` |
| `ALLOWED` | `ALLOWED` | `ALLOWED` |
| `ALLOWED` | `UNDECIDED` | `ALLOWED` |
| `UNDECIDED` | `REJECTED` | `REJECTED` |
| `UNDECIDED` | `ALLOWED` | `ALLOWED` |
| `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |

This can be remembered by precedence:

~~~text
               Is any filter REJECTED?
                    /        \
                  Yes         No
                  |            |
               REJECTED   Is any filter ALLOWED?
                              /       \
                            Yes        No
                            |           |
                         ALLOWED    UNDECIDED
~~~

### 3.1. Why Is It Not an AND Operation?

Suppose:

- Filter A allows the `Invoice` class.
- Filter B checks resource limits and returns `UNDECIDED` if limits are not exceeded.

When checking `Invoice`, A returns `ALLOWED` and B returns `UNDECIDED`; the `merge` result is `ALLOWED`. This is the desired outcome: the class is accepted by the allowlist and resource limits found no violation.

If a limit is exceeded, B returns `REJECTED`; even though A returned `ALLOWED`, the result is still `REJECTED`. Thus the limit filter has veto power.

If both filters must return `ALLOWED` for acceptance, default `merge` does not express that AND policy. Write a custom composite filter and handle `UNDECIDED` accordingly, or design each filter so its statuses express the intended policy.

## 4. Designing Focused Single-Responsibility Filters

A maintainable way to organize policies is splitting them into small filters:

| Filter | Responsibility | When There Is No Issue |
| --- | --- | --- |
| Allowlist | Allow only identified classes. | Return `ALLOWED` for allowed classes; return `REJECTED` for unlisted classes. |
| Blocklist | Reject dangerous or disallowed classes. | Return `UNDECIDED` for classes not matching rejection rules. |
| Resource limits | Limit depth, references, bytes, and array length. | Return `UNDECIDED` when all limits are within thresholds. |
| Context policy | Specify which classes are permitted in a particular business flow or module. | Return statuses within the context's responsibility scope. |

A filter should decide only within the scope it understands. For example, a resource-limit filter does not need to return `ALLOWED` for every class of valid size; it only needs to return `REJECTED` when exceeding thresholds and `UNDECIDED` when there is no violation. When merged with an allowlist, this avoids having the limit filter accidentally grant permission to unlisted classes.

## 5. Combining an Allowlist with Resource Limits

This is a common pattern: accept only data types the application expects, while bounding object graph size.

### 5.1. Creating an Allowlist with allowFilter

Java 17 provides:

~~~java
ObjectInputFilter.allowFilter(
    Predicate<Class<?>> predicate,
    ObjectInputFilter.Status otherStatus
)
~~~

The filter returns:

- `UNDECIDED` if `FilterInfo.serialClass()` is `null`.
- `ALLOWED` if the predicate returns `true`.
- `otherStatus` if the predicate returns `false`.

To build a strict allowlist, pass `Status.REJECTED` as `otherStatus`:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter allowedClasses = ObjectInputFilter.allowFilter(
    type -> type == Message.class || type == Notice.class,
    ObjectInputFilter.Status.REJECTED
);
~~~

Thus, listed classes return `ALLOWED`; all other classes with a non-null `serialClass` return `REJECTED`. Metrics-only filter checks with `serialClass == null` still return `UNDECIDED`.

### 5.2. Creating a Resource-Limit Filter

`FilterInfo` provides metrics to detect oversized object graphs:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter resourceLimits = info -> {
    if (info.depth() > 20
            || info.references() > 10_000
            || info.streamBytes() > 1_000_000
            || (info.arrayLength() >= 0 && info.arrayLength() > 100_000)) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

Meaning:

- `depth()`: current depth of the object graph.
- `references()`: number of object references read so far.
- `streamBytes()`: number of bytes read from the stream.
- `arrayLength()`: length of the array being checked; a negative value indicates the current check is not an array.

The numbers in the example are only illustrative. Applications must choose limits based on valid data sizes, object graph structure, and available resources. Do not copy sample thresholds into production without evaluation.

### 5.3. Using merge to Combine Both Filters

~~~java
ObjectInputFilter combined =
    ObjectInputFilter.merge(allowedClasses, resourceLimits);
~~~

Outcomes:

- Class in allowlist, resources within limits: `ALLOWED + UNDECIDED` → `ALLOWED`.
- Class outside allowlist: `REJECTED` → `REJECTED`.
- Allowed class, but object graph exceeds limits: `ALLOWED + REJECTED` → `REJECTED`.
- Metrics-only check within thresholds: `UNDECIDED + UNDECIDED` → `UNDECIDED`.

This is how complementary policies combine: the allowlist decides which classes are allowed, while the resource filter has authority to reject oversized object graphs.

## 6. Complete Example: Deserializing with a Merged Filter

Create the file **`FilterMergeDemo.java`**:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class FilterMergeDemo {
    static final class Message implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String text;
        private final int priority;

        Message(String text, int priority) {
            this.text = text;
            this.priority = priority;
        }

        @Override
        public String toString() {
            return "Message[text=" + text + ", priority=" + priority + "]";
        }
    }

    static final class UnexpectedPayload implements Serializable {
        private static final long serialVersionUID = 1L;
    }

    private static byte[] serialize(Object value) throws IOException {
        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(value);
        }
        return bytes.toByteArray();
    }

    private static Object deserialize(
            byte[] bytes,
            ObjectInputFilter filter
    ) throws IOException, ClassNotFoundException {
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes))) {
            // Must set the filter before the first object read.
            in.setObjectInputFilter(filter);
            return in.readObject();
        }
    }

    private static ObjectInputFilter createFilter() {
        ObjectInputFilter allowlist = ObjectInputFilter.allowFilter(
            type -> type == Message.class,
            ObjectInputFilter.Status.REJECTED
        );

        ObjectInputFilter limits = info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 100_000
                    || (info.arrayLength() >= 0
                        && info.arrayLength() > 10_000)) {
                return ObjectInputFilter.Status.REJECTED;
            }
            return ObjectInputFilter.Status.UNDECIDED;
        };

        return ObjectInputFilter.merge(allowlist, limits);
    }

    public static void main(String[] args) throws Exception {
        ObjectInputFilter filter = createFilter();

        byte[] acceptedBytes = serialize(new Message("Hello", 1));
        Object accepted = deserialize(acceptedBytes, filter);
        System.out.println(accepted);

        byte[] rejectedBytes = serialize(new UnexpectedPayload());
        try {
            deserialize(rejectedBytes, filter);
        } catch (InvalidClassException e) {
            System.out.println("Rejected: " + e.getMessage());
        }
    }
}
~~~

Compile and run with JDK 17:

~~~shell
javac --release 17 FilterMergeDemo.java
java FilterMergeDemo
~~~

Key output:

~~~text
Message[text=Hello, priority=1]
Rejected: filter status: REJECTED
~~~

The error message may include class names or details depending on the JDK. The observable outcome is that `Message` is accepted while `UnexpectedPayload` is rejected by the allowlist. If `Message`'s object graph exceeds limits, the resource filter can reject it too.

In real applications, permitted data classes may require other component types. List the exact permitted types per the actual object graph; do not widen the allowlist to entire packages or all classes just to avoid errors.

## 7. Combining a Blocklist with a Resource Filter

Not every policy uses an allowlist. A system might need to explicitly reject certain dangerous class categories, leaving other classes to be handled by another filter.

Java 17 provides `rejectFilter`:

~~~java
ObjectInputFilter.rejectFilter(
    Predicate<Class<?>> predicate,
    ObjectInputFilter.Status otherStatus
)
~~~

Example:

~~~java
ObjectInputFilter blockLegacyTypes = ObjectInputFilter.rejectFilter(
    type -> type.getName().startsWith("com.example.legacy."),
    ObjectInputFilter.Status.UNDECIDED
);
~~~

This filter returns:

- `REJECTED` if the class name belongs to the blocked package.
- `UNDECIDED` if the class does not match.
- `UNDECIDED` if `serialClass()` is `null`.

Merging with resource limits:

~~~java
ObjectInputFilter policy =
    ObjectInputFilter.merge(blockLegacyTypes, resourceLimits);
~~~

Classes in the blocked package are rejected. Other classes are left undecided by the blocklist; the resource filter also rejects only when detecting exceeded thresholds. If both return `UNDECIDED`, the result remains `UNDECIDED`.

**Warning:** this is a blocklist, not an allowlist. Classes not matching the blocked package are not automatically proven safe. If data comes from an untrusted source, a context-specific allowlist is usually needed rather than merely blocking a few packages.

## 8. rejectUndecidedClass: Turning Undecided Decisions into Rejections

Java 17 provides:

~~~java
ObjectInputFilter.rejectUndecidedClass(filter)
~~~

This wrapper invokes the inner filter and converts `UNDECIDED` results into `REJECTED` for classes, with special handling for arrays and primitive arrays per the API contract. If `serialClass()` is `null`, the status remains `UNDECIDED` because that call carries only object graph metrics.

Example:

~~~java
ObjectInputFilter strictPolicy =
    ObjectInputFilter.rejectUndecidedClass(
        ObjectInputFilter.merge(allowlist, resourceLimits)
    );
~~~

With the design in the earlier example:

- Classes accepted by the allowlist and within limits: `ALLOWED`, preserved.
- Classes rejected by the allowlist: `REJECTED`, preserved.
- Classes undecided by any filter: `UNDECIDED` converted to `REJECTED`.
- Metrics-only checks: can remain `UNDECIDED`.

This creates a fail-closed policy for classes: any class not explicitly allowed is rejected.

### 8.1. Do Not Wrap with rejectUndecidedClass Mechanically

If you only have a blocklist and a resource filter, both may return `UNDECIDED` for an unblocked valid class. Wrapping `rejectUndecidedClass` around that composite will reject that class too.

Therefore:

- Use `rejectUndecidedClass` when the policy has an explicit allow source.
- Do not use it as a default decoration step for every filter.
- Verify supporting classes, array components, and classes in the object graph before applying it.

## 9. Combining Filters Created from Pattern Strings

`ObjectInputFilter.Config.createFilter` constructs a filter from a pattern string. Patterns can describe resource limits and allowed or rejected class/package names.

Example:

~~~java
ObjectInputFilter patternFilter =
    ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=10000;maxbytes=1000000;"
        + "com.example.dto.*;!*"
    );
~~~

In the example:

- `maxdepth=20`: limits object graph depth.
- `maxrefs=10000`: limits reference count.
- `maxbytes=1000000`: limits bytes read from stream.
- `com.example.dto.*`: allows classes in the specified package per pattern syntax.
- `!*`: rejects classes not matching preceding patterns.

You can combine a pattern filter with a context-specific filter:

~~~java
ObjectInputFilter contextFilter = ObjectInputFilter.allowFilter(
    type -> type == ImportRequest.class,
    ObjectInputFilter.Status.UNDECIDED
);

ObjectInputFilter combined =
    ObjectInputFilter.merge(patternFilter, contextFilter);
~~~

Both filters have authority to reject. Therefore, a class must not be rejected by either filter; a single filter returning `ALLOWED` is insufficient if the other filter returns `REJECTED`.

In this example, `contextFilter` makes a decision only for `ImportRequest` and returns `UNDECIDED` for other classes. Using `REJECTED` as the fallback status would cause the context filter to reject all other DTOs that the pattern filter might allow.

Pattern strings are useful when policies can be configured via system properties or config files. Lambdas are useful when conditions depend on Java logic, class loaders, modules, or application metadata.

## 10. Using Merged Filters with ObjectInputStream

After creating the composite filter, set it on the stream before reading objects:

~~~java
try (ObjectInputStream in =
        new ObjectInputStream(inputStream)) {
    in.setObjectInputFilter(combinedFilter);
    Object value = in.readObject();
}
~~~

Points to keep in mind:

- Set the filter before the first object read.
- `setObjectInputFilter` may be called only once per stream.
- The filter applies while the stream deserializes the object graph.
- If the filter returns `REJECTED`, object reading aborts and throws `InvalidClassException`.
- A stream-specific filter protects only the stream to which it is attached.
- If the application creates multiple `ObjectInputStream`s, ensure each stream has an appropriate policy.

Do not call `setObjectInputFilter` after the stream has begun reading objects expecting it to apply retroactively to objects already processed.

## 11. Combining Policies via Filter Factories in Java 17

In an application with multiple libraries or multiple deserialization contexts, a single fixed JVM-wide filter may not suffice. Java 17 adds a **deserialization filter factory** mechanism under JEP 415.

A factory is a `BinaryOperator<ObjectInputFilter>`. It is invoked when:

1. An `ObjectInputStream` is constructed, with current filter `null` and requested filter as the static JVM-wide filter (if present).
2. The application calls `ObjectInputStream.setObjectInputFilter`, with the current filter and the newly requested filter.

The factory can use execution context to choose or combine policies. Minimal example:

~~~java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

BinaryOperator<ObjectInputFilter> factory = (current, requested) -> {
    if (current == null) {
        return requested;
    }
    if (requested == null) {
        return current;
    }
    return ObjectInputFilter.merge(requested, current);
};

ObjectInputFilter.Config.setSerialFilterFactory(factory);
~~~

This illustrates how to combine the current filter and requested filter. `setSerialFilterFactory` can be configured only once and must be called before any `ObjectInputStream` is created. In real systems, the factory may need to retrieve extra filters by thread, module, calling library, or data type being read. Design `UNDECIDED` handling explicitly; if the requirement is to allow only named classes, wrap the composite with `rejectUndecidedClass` after ensuring allowlist filters return `ALLOWED` for valid classes.

### 11.1. Why Are Factories Useful?

Suppose an application has:

- A JVM-wide filter bounding maximum depth, references, and bytes.
- An import library filter allowing only import DTOs.
- A cache library filter allowing only cache data types.

The factory can combine the JVM-wide filter with each `ObjectInputStream`'s specific filter. That way, the global filter still retains authority to reject object graphs exceeding limits, while each context restricts permitted classes.

Do not let a library arbitrarily replace the application's entire protection policy. The factory is the central point to decide whether new filters are merged, preserved, or replaced per system contract.

## 12. Filter Invocation Order and Side Effects

In terms of statuses, combination is symmetric in result: `merge(A, B)` and `merge(B, A)` obey the same status precedence rules. Yet execution **is not completely symmetric**:

- The first filter is called first.
- If the first filter returns `REJECTED`, the second filter is not called.
- If the first filter does not reject, only then is the second filter called.

Therefore, filters should be pure check functions that do not depend on whether another filter was invoked. Avoid writing business data, incrementing counters used for core logic, or mutating application state inside `checkInput`.

If logging is needed, logging should be purely observational and never alter policy outcomes. Never assume every filter is always invoked for every object.

## 13. Mistakes When Merging Filters

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `merge` returns `ALLOWED` only when both filters allow | Misunderstands contract; a single `ALLOWED` suffices if the other does not reject. | Use the truth table to design each filter. |
| Allowlist returns `UNDECIDED` for unlisted classes | Another filter returning `ALLOWED` can cause that class to be accepted. | Use `allowFilter(predicate, REJECTED)` for strict allowlists. |
| Resource filter returns `ALLOWED` for all objects under thresholds | Can turn a class undecided by the allowlist into `ALLOWED` after merge. | Return `UNDECIDED` when limits are not exceeded. |
| Using only a blocklist for untrusted data | New or unknown classes can still be accepted. | Prefer per-use-case allowlists. |
| Assuming `UNDECIDED` means reject | Deserialization can proceed if no other filter rejects. | Use `rejectUndecidedClass` when fail-closed class handling is needed. |
| Calling `merge(null, filter)` | First argument must be non-null; throws `NullPointerException`. | Handle null before calling or put the mandatory filter first. |
| Using `rejectUndecidedClass` with a resource-limits-only filter | Classes not explicitly allowed by any filter may all be rejected. | Combine with an explicit allowlist before converting undecided to reject. |
| Thinking `ALLOWED` can override `REJECTED` | False; `REJECTED` always wins. | Keep all rejection rules in the composite filter. |
| Attaching a filter to one stream while the app creates other streams | Remaining streams may lack the desired protection policy. | Apply filters on every stream or configure a JVM-wide factory. |
| Treating filters as full data validators | Filters check classes and metrics, not all business invariants. | Validate data after deserialization and avoid Java serialization for untrusted data when possible. |

## 14. Choosing a Combination Approach by Goal

| Goal | Suitable Design |
| --- | --- |
| Allow only a specific group of DTOs | `allowFilter(predicate, REJECTED)`. |
| Reject a known group of classes, letting other filters decide the rest | `rejectFilter(predicate, UNDECIDED)`. |
| Bound depth, references, bytes, and array length | Metrics filter returning `REJECTED` when exceeding thresholds, otherwise `UNDECIDED`. |
| Allowlist plus resource limits | `merge(allowlist, limits)`. |
| Multiple independent allowlists must all accept a class | Use strict allowlists; `REJECTED` from either filter vetoes. |
| All undecided classes must be rejected | Wrap composite with `rejectUndecidedClass` after ensuring valid classes yield `ALLOWED`. |
| Different policies per library or thread | Use a filter factory and merge filters by context. |
| Policy configured via pattern string | `Config.createFilter(...)`, optionally merged with programmatic filters. |

Before merging, write down what each filter is responsible for and what status it returns when there is no issue. This step matters more than merely calling `merge`.

## 15. Example: Tracing Each Filter Result by Hand

Suppose there are two filters:

~~~java
ObjectInputFilter classFilter = info -> {
    Class<?> type = info.serialClass();
    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }
    if (type == Message.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }
    return ObjectInputFilter.Status.REJECTED;
};

ObjectInputFilter sizeFilter = info -> {
    if (info.streamBytes() > 500_000) {
        return ObjectInputFilter.Status.REJECTED;
    }
    return ObjectInputFilter.Status.UNDECIDED;
};

ObjectInputFilter combined =
    ObjectInputFilter.merge(classFilter, sizeFilter);
~~~

Analysis:

| Check | classFilter | sizeFilter | combined |
| --- | --- | --- | --- |
| `Message`, 100 KB | `ALLOWED` | `UNDECIDED` | `ALLOWED` |
| `Message`, 600 KB | `ALLOWED` | `REJECTED` | `REJECTED` |
| `Unexpected`, 100 KB | `REJECTED` | Not called if classFilter runs first and rejects | `REJECTED` |
| No class, 100 KB | `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |
| No class, 600 KB | `UNDECIDED` | `REJECTED` | `REJECTED` |

The `Unexpected` case demonstrates short-circuiting: the first filter already rejected, so the second filter need not run. The metrics-only case shows that a filter can still decide based on stream size even when there is no specific class in that check.

## 16. Frequently Asked Questions

**Which Java version introduced `ObjectInputFilter.merge`?**  
This method was added in Java 17.

**Is `merge` an AND operation?**  
No. `REJECTED` from either filter wins; if there is no rejection, a single filter returning `ALLOWED` yields `ALLOWED`; if both are `UNDECIDED`, the result is `UNDECIDED`.

**Is the second filter called if the first filter returns `REJECTED`?**  
No. `merge` returns `REJECTED` immediately after the first filter's result.

**Can null be passed for both filters?**  
No. The first argument must be non-null. The second argument can be null, in which case the method returns the first filter.

**Does `UNDECIDED` block a class?**  
No. This status means the filter made no decision. Deserialization can continue if no other filter rejects. Use `rejectUndecidedClass` when explicitly unallowed classes must be rejected.

**Why should a resource filter return `UNDECIDED` when limits are not exceeded?**  
Because that filter is responsible only for resource limits. If it returned `ALLOWED` for every class of valid size, merge results could allow a class not accepted by the allowlist.

**Is `allowFilter` available in Java 17?**  
Yes. `ObjectInputFilter.allowFilter` was added in Java 17; pass `Status.REJECTED` as the status when the predicate is false to create a strict allowlist.

**Has `rejectUndecidedClass` existed since Java 17?**  
Yes. It converts `UNDECIDED` results into `REJECTED` for classes, with special handling for arrays and primitive arrays; metrics-only checks can still be `UNDECIDED`.

**Does `merge` automatically attach the filter to every ObjectInputStream?**  
No. It only constructs a composite filter. The application must attach the filter to streams or configure a filter factory to select/share appropriate policies.

**Can merge be used to make untrusted data completely safe?**  
Filters reduce risk by restricting classes and resources, yet do not replace data validation, business invariant checks, or choosing a safer exchange format. Avoid deserializing untrusted data whenever possible.

## 17. Official References

- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): contract for `merge`, `allowFilter`, `rejectFilter`, `rejectUndecidedClass`, filter statuses, and filter factories.
- [Java SE 17 API — ObjectInputFilter.Status](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Status.html): meaning of `ALLOWED`, `REJECTED`, and `UNDECIDED`.
- [Java SE 17 API — ObjectInputStream.setObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html#setObjectInputFilter(java.io.ObjectInputFilter)): attaching a filter to an object input stream.
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): creating filters from patterns, configuring JVM-wide filters and filter factories.
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): filter factory design for applying context-specific policies.
- [Oracle Secure Coding Guidelines — Serialization and Deserialization](https://www.oracle.com/java/technologies/javase/seccodeguide.html): recommendations for securing serialization/deserialization handling.

**Application principle:** Split policies into filters with clear responsibilities, then use `ObjectInputFilter.merge` to combine them. Remember that `REJECTED` always vetoes, one `ALLOWED` suffices for an allow result if there is no rejection, and `UNDECIDED` does not automatically block a class. For untrusted data, combine a strict allowlist, resource limits, and undecided-class rejection tailored to the actual object graph.
