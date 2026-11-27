# Pattern-Based Filters and Programmatic Filters in Java 17

Java Serialization can reconstruct an object graph from binary data using ObjectInputStream. If data comes from an untrusted source, merely calling readObject() can cause the program to instantiate unexpected object types or process a graph that is too large or too deep. Serialization filtering allows restricting the classes permitted to be deserialized and limiting the resources the object graph can consume.

Java 17 supports two primary ways of building filters:

- **Pattern-based filters**: describe allowed/rejected classes and limits via a configuration string.
- **Programmatic filters**: implement ObjectInputFilter to inspect each object, array, and graph metric as data is read.

Both approaches can be used at the ObjectInputStream level or within a JVM-wide policy. Java 17 also provides a filter factory mechanism to select filters by context. This lesson focuses on pattern syntax, writing filters in code, and attaching them to the deserialization process.

## 1. Why Are Serialization Filters Needed?

When reading Java Serialization data, the program is not merely reading a simple sequence of bytes. A stream can describe:

- each object's class;
- object fields and values;
- arrays and array lengths;
- references between objects;
- nested relationships forming an object graph.

If an application reads an untrusted stream without a filtering policy, the data can request instantiating unwanted objects, allocating huge arrays, or constructing graphs whose depth and reference counts exceed what the application can handle.

A serialization filter allows the application to inspect information about an object **during deserialization**, before accepting that object. A filter can:

1. allow a specific class or group of classes;
2. reject classes outside the policy;
3. limit graph depth;
4. limit reference count, bytes read, and array length.

The standard API is java.io.ObjectInputFilter, introduced in Java 9 via JEP 290 and still supported in Java 17.

**Filters are a defense layer for Java Serialization.** If a protocol does not require Java native serialization, consider an explicit-schema data format such as JSON, Protocol Buffers, or another suitable format. If serialized objects must still be read, apply a filter and validate business data after reading.

## 2. How Does ObjectInputFilter Work?

ObjectInputFilter is invoked while ObjectInputStream reads the components of an object graph. The filter receives a FilterInfo containing details about the element being processed and returns one of three statuses:

| Status | Meaning |
| --- | --- |
| ALLOWED | This filter permits the current element. |
| REJECTED | The filter rejects the element; reading will fail. |
| UNDECIDED | The filter makes no decision for the current element. |

Key information provided by FilterInfo:

| Method | Information |
| --- | --- |
| serialClass() | The class of the object or array being deserialized; may be null on some calls such as back-references to already-read objects. |
| arrayLength() | The array length if the element under inspection is an array; returns a negative value if not an array. |
| depth() | The current depth of the object graph. |
| references() | The number of references processed so far in the stream. |
| streamBytes() | The number of bytes read from the stream at the time of the check. |

A filter can check only classes, only resource limits, or both.

### 2.1. The Three Statuses Do Not Have the Same Meaning

Do not confuse UNDECIDED with REJECTED:

- ALLOWED means this filter makes an acceptance decision.
- REJECTED means this filter makes a rejection decision.
- UNDECIDED means this filter has no rule applying to that case.

If a pattern-based filter has no matching pattern, it returns UNDECIDED. That **does not automatically turn into a rejection**. When no other filter makes a rejection decision, ObjectInputStream can continue reading the object.

Therefore, if you want to build an allowlist (allowing only a specific group of classes), you must include a default-deny rule for the remaining classes. With patterns, !** is typically used at the end. With programmatic filters, return REJECTED for classes not in the allowlist.

## 3. Pattern-Based Filter Syntax

Java provides ObjectInputFilter.Config.createFilter(String pattern) to construct a filter from a configuration string.

A pattern can include:

- exact class names;
- package names with wildcards;
- module names combined with class or package names;
- rejection rules starting with !;
- limits maxdepth, maxrefs, maxbytes, and maxarray.

Items are separated by semicolons. Patterns are evaluated left to right; the first matching class pattern decides ALLOWED or REJECTED. Resource limits are checked independently of class rules and if any limit is exceeded, the filter rejects.

### 3.1. Matching a Specific Class

Class names are written as fully qualified class names:

~~~text
com.acme.model.Order
~~~

This pattern matches the class com.acme.model.Order. It does not automatically match other classes in the same package.

### 3.2. Matching Packages

Two commonly used package wildcards:

| Pattern | Scope |
| --- | --- |
| com.acme.model.* | Classes directly in the com.acme.model package. |
| com.acme.model.** | Classes in com.acme.model and its subpackages. |

Example:

~~~text
com.acme.model.*
~~~

matches com.acme.model.Order but does not match com.acme.model.internal.OrderRecord.

Meanwhile:

~~~text
com.acme.model.**
~~~

matches both classes in the base package and subpackages.

Choose the narrowest wildcard that meets your needs. Allowing entire large packages can accidentally allow internal or unnecessary classes.

### 3.3. Matching by Module

Patterns can specify a module by placing the module name before a slash:

~~~text
java.base/java.lang.String
java.base/java.util.ArrayList
~~~

The first pattern specifies the String class belonging to module java.base. The second pattern specifies ArrayList in the same module.

Modules can be combined with package wildcards:

~~~text
java.base/java.util.*
~~~

This pattern matches classes directly in the java.util package of the java.base module.

If no module is specified, the class/package pattern applies by class/package name without restricting to a specific module.

### 3.4. Global Wildcards and the Negation Sign

Two special wildcards:

| Pattern | Meaning |
| --- | --- |
| * | All classes in the unnamed module. |
| ** | All classes in all modules. |

Prepend ! to reject:

~~~text
!com.acme.model.internal.**
!**
~~~

The first pattern rejects the internal package and its subpackages. The second pattern rejects all classes across all modules.

For example, an allowlist can permit certain classes first, then reject the rest:

~~~text
com.acme.model.**;java.base/java.lang.String;!**
~~~

In the example, classes in the model package and String are allowed; other classes are rejected by the last rule. When writing an allowlist, order is critical: placing !** before allow patterns leaves subsequent patterns no opportunity to decide for already-matched classes.

## 4. Resource Limits in Patterns

Patterns support four limits:

| Limit | Meaning |
| --- | --- |
| maxdepth | Maximum depth of the object graph. |
| maxrefs | Maximum number of references processed. |
| maxbytes | Maximum number of bytes read from the stream. |
| maxarray | Maximum length of an array. |

Example:

~~~text
maxdepth=20;maxrefs=10000;maxbytes=5000000;maxarray=100000
~~~

These are illustrative thresholds. Appropriate values must be based on the application's valid data sizes rather than copied mechanically.

### 4.1. maxdepth

Limits object graph depth. If one object references another, which in turn references another, depth can keep increasing.

~~~text
Order
 └── Customer
      └── Address
           └── ...
~~~

Limiting depth helps prevent overly deep nested graphs that can cause heavy resource consumption or increase stack/resource exhaustion risk.

### 4.2. maxrefs

Limits the number of references processed. This is not simply the count of distinct classes. A graph with many objects and links can cause the reference count to grow rapidly.

### 4.3. maxbytes

Limits the number of bytes read from ObjectInputStream. It helps bound the input data size accepted by deserialization.

maxbytes does not replace network-layer request size limits or file size limits before opening. Applications should still limit input where data is received.

### 4.4. maxarray

Limits array length. A single array can request a huge memory allocation even when the stream does not contain many other objects.

If valid data includes large arrays, choose a threshold large enough for valid use yet clearly bounded. Programmatic filters can also check arrayLength() directly.

## 5. Example Creating a Pattern-Based Filter

Suppose an application only needs to read DTOs in package com.acme.model and String, while bounding graph size:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;" +
        "maxrefs=10000;" +
        "maxbytes=5000000;" +
        "maxarray=100000;" +
        "com.acme.model.**;" +
        "java.base/java.lang.String;" +
        "!**"
);
~~~

Meaning:

1. Do not allow graph depth to exceed 20.
2. Do not allow reference count to exceed 10,000.
3. Do not allow the stream to read more than 5,000,000 bytes.
4. Do not allow arrays longer than 100,000 elements.
5. Allow classes in the model package and its subpackages.
6. Allow String in the java.base module.
7. Reject remaining classes.

Attach the filter to ObjectInputStream before calling readObject():

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

static Object readFiltered(InputStream source)
        throws IOException, ClassNotFoundException {
    ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
            "maxdepth=20;maxrefs=10000;maxbytes=5000000;" +
            "maxarray=100000;com.acme.model.**;" +
            "java.base/java.lang.String;!**"
    );

    try (ObjectInputStream input = new ObjectInputStream(source)) {
        input.setObjectInputFilter(filter);
        return input.readObject();
    }
}
~~~

Set the filter before the first object read. If the filter rejects a class or a limit is exceeded, deserialization fails; the application must handle IOException/InvalidClassException appropriately.

**Note on real-world allowlists:** a DTO may contain collections, arrays, or other helper classes. The filter must allow the exact types actually present in valid graphs. Do not broaden wildcards to all of java.util or all of java.base just to get an example running; identify concrete serialization dependencies.

## 6. Configuring Pattern Filters at the JVM Level

A shared filter can be configured at JVM launch via the jdk.serialFilter system property:

~~~bash
java -Djdk.serialFilter="maxdepth=20;maxrefs=10000;maxbytes=5000000;maxarray=100000;com.acme.model.**;java.base/java.lang.String;!**" -jar app.jar
~~~

A JVM-level policy can protect multiple ObjectInputStream instances in the process. This is useful for deployment environments wanting a shared baseline, even when some components do not configure filters themselves.

Points to keep in mind:

- JVM-wide filter configuration affects multiple deserialization flows in the process; verify compatibility with libraries and valid data.
- A narrow allowlist pattern may prevent other libraries from reading classes they need.
- Do not leave the global configuration overly broad just to avoid compatibility issues.
- Configure at launch time and manage alongside the application's security configuration.

The JDK also supports configuration via a security property per runtime rules. Deployment should be managed centrally rather than letting each component set conflicting policies.

## 7. Programmatic Filters with ObjectInputFilter

When patterns are not flexible enough, filters can be written as lambdas or dedicated classes. This approach fits when you need to:

- inspect classes using Class<?> and Java logic;
- handle array component types specifically;
- combine multiple limits based on context;
- read FilterInfo details to apply custom rules;
- build an explicit allowlist using a set of classes.

A filter is declared as:

~~~java
ObjectInputFilter filter = info -> {
    // Inspect info and return a Status.
};
~~~

### 7.1. Checking Limits Before Evaluating Classes

Example filter accepting only OrderSnapshot and String:

~~~java
import java.io.ObjectInputFilter;

final class OrderSnapshot implements java.io.Serializable {
    private static final long serialVersionUID = 1L;

    private final String orderId;
    private final String status;
    private final long createdAtEpochMillis;

    OrderSnapshot(String orderId, String status, long createdAtEpochMillis) {
        this.orderId = orderId;
        this.status = status;
        this.createdAtEpochMillis = createdAtEpochMillis;
    }
}

static ObjectInputFilter orderFilter() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 1000
                || info.streamBytes() > 1_000_000
                || info.arrayLength() > 10_000) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (type == OrderSnapshot.class || type == String.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
~~~

This filter performs two steps:

1. Reject immediately if any resource limit is exceeded.
2. Allow only the two listed classes; reject all other classes.

serialClass() can be null, such as when the filter is invoked for a reference to an already-read object. In that case there is no new class to check; returning UNDECIDED keeps the filter from wrongly assuming a class.

The example deliberately uses a simple DTO with String and primitive types. If a DTO has other object fields, add those exact classes to the allowlist.

### 7.2. Checking Arrays by Component Type

When a DTO contains arrays, checking arrayLength() alone is insufficient. You must identify the array's element type:

~~~java
static ObjectInputFilter arrayAwareFilter() {
    return info -> {
        if (info.depth() > 20
                || info.references() > 5000
                || info.streamBytes() > 2_000_000) {
            return ObjectInputFilter.Status.REJECTED;
        }

        Class<?> type = info.serialClass();
        if (type == null) {
            return ObjectInputFilter.Status.UNDECIDED;
        }

        if (type.isArray()) {
            if (info.arrayLength() > 50_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> component = type.getComponentType();
            if (component.isPrimitive() || component == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        }

        if (type == OrderSnapshot.class || type == String.class) {
            return ObjectInputFilter.Status.ALLOWED;
        }

        return ObjectInputFilter.Status.REJECTED;
    };
}
~~~

Here:

- Arrays longer than 50,000 are rejected.
- Primitive arrays are allowed.
- String arrays are allowed.
- Object arrays with other component types are rejected.
- Classes not in the allowlist are rejected.

If the application needs LineItem[] arrays, add LineItem.class to the component type condition. Do not allow Object[] broadly without justification, as it can hold many kinds of objects; element objects are still filtered individually, yet narrower allowlists remain easier to control.

## 8. Attaching a Filter to ObjectInputStream

A filter can be attached via setObjectInputFilter():

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;

static Object deserialize(InputStream source)
        throws IOException, ClassNotFoundException {
    try (ObjectInputStream input = new ObjectInputStream(source)) {
        input.setObjectInputFilter(orderFilter());
        return input.readObject();
    }
}
~~~

Attach the filter before reading objects. In a typical design, a stream's filter is set once during initialization and not altered arbitrarily after reading has begun.

If the filter returns REJECTED, ObjectInputStream throws a deserialization error, typically represented by InvalidClassException. Applications should catch errors at the ingestion boundary and log enough to diagnose without logging sensitive payloads.

### 8.1. Checking the Result Type After Reading

Filters control classes and resources, yet type validation at the API boundary is still needed:

~~~java
Object value = deserialize(source);
if (!(value instanceof OrderSnapshot order)) {
    throw new IOException("Data is not an OrderSnapshot");
}
~~~

Afterward, check business rules such as whether orderId is valid, status is in the allowed set of states, and timestamps fall within reasonable bounds.

Do not treat the filter allowing a class as proof that the object contains valid business data.

## 9. Pattern vs. Programmatic Filters: Which to Choose?

| Criterion | Pattern-Based Filter | Programmatic Filter |
| --- | --- | --- |
| Declaration | Configuration string. | Lambda or class implementing ObjectInputFilter. |
| Class allowlist | Class/package/module names. | Comparing Class<?> or class sets. |
| Resource limits | maxdepth, maxrefs, maxbytes, maxarray. | Reading FilterInfo and checking manually. |
| Complex logic | Limited. | More flexible. |
| Deployment configurability | Good, can use jdk.serialFilter. | Requires code or filter factory. |
| Array component control | Limited with patterns. | Can use Class.isArray() and getComponentType(). |
| Best suited for | Standard allow/deny policies and limits. | Context-specific rules or complex class checks. |

You do not need to pick only one approach everywhere. Patterns fit simple, easy-to-manage baselines. Programmatic filters fit when the application needs type-based allowlists or dynamic conditions.

## 10. Combining Filters and Filter Factories in Java 17

An application may have multiple policy sources:

- a JVM-wide filter configured by administrators;
- a per-stream filter for a single ObjectInputStream;
- a filter based on data type or request context.

If policies are combined inconsistently, a less strict filter might accidentally weaken another policy. Java 17 adds **context-specific deserialization filters** under JEP 415 via filter factories.

A filter factory is a BinaryOperator<ObjectInputFilter> used to select a filter for ObjectInputStream. The factory is invoked when a stream is created and when the application sets a per-stream filter. The factory receives the current filter and the requested filter, returning the final filter to use.

The configuration API resides in ObjectInputFilter.Config:

~~~java
ObjectInputFilter.Config.setSerialFilterFactory((current, requested) -> {
    // Select or combine policies based on context.
    return requested;
});
~~~

This snippet only illustrates the factory integration point, not a complete production-ready policy: returning requested directly may drop the current policy. In real implementations, the factory must define how JVM-wide filters, stream filters, and context policies combine; rules must ensure stricter rejections are not bypassed.

The factory can be configured via the jdk.serialFilterFactory system property per Java 17 mechanisms. Because the factory is a process-level extension point, configure it early and manage it uniformly; do not let individual libraries replace the global factory.

### 10.1. When Is a Filter Factory Needed?

A filter factory is useful when the same JVM deserializes multiple distinct data types:

- request type A may only contain DTO A;
- cache data type B has a different allowlist;
- administrative components have their own policy;
- the application must ensure every stream still abides by a global baseline.

For small applications with a single data type, a per-stream filter on each ObjectInputStream is usually clear and sufficient. Do not add a factory unless multi-context policy management is needed.

## 11. Common Mistakes When Writing Filters

### 11.1. Setting Limits Without Creating an Allowlist

Pattern:

~~~text
maxdepth=20;maxrefs=10000;maxbytes=5000000
~~~

only sets resource limits. Unconstrained classes can return UNDECIDED and still be read if no other filter rejects them.

If an allowlist is needed, add allowed classes and a default-deny rule:

~~~text
maxdepth=20;com.acme.model.**;!**
~~~

### 11.2. Putting !** First

Pattern:

~~~text
!**;com.acme.model.**
~~~

already rejects all classes before reaching the allow rule. Put the allowlist first, deny-all last:

~~~text
com.acme.model.**;!**
~~~

### 11.3. Confusing * with **

- * matches only classes in the unnamed module.
- ** matches classes in all modules.

If the goal is to reject all unlisted classes, !** is usually more appropriate than !*.

### 11.4. Using Overly Broad Package Wildcards

Pattern:

~~~text
com.acme.**
~~~

can allow more classes than expected, including internal packages, framework helper classes, or classes outside public DTOs. Use specific subpackages and deny sensitive areas if needed.

### 11.5. Returning UNDECIDED for Unknown Classes

In programmatic filters, if the goal is an allowlist, the default branch should return REJECTED:

~~~java
if (isAllowed(type)) {
    return ObjectInputFilter.Status.ALLOWED;
}
return ObjectInputFilter.Status.REJECTED;
~~~

Returning UNDECIDED for all unknown classes prevents the filter from actually blocking them.

### 11.6. Ignoring Arrays

An allowed class might contain a huge array or an array with an unwanted element type. Check arrayLength() and component types when valid data uses arrays.

### 11.7. Filtering Classes Only While Forgetting Resource Limits

A class allowlist does not automatically bound object count, graph depth, or array sizes. Set appropriate resource thresholds alongside class rules.

### 11.8. Assuming Filters Replace Data Validation

Filters only decide classes and resource metrics during reading. They do not verify whether the sender is authorized to send that data, whether the data has a valid signature, or whether business state is valid. Those checks are still needed at the application layer.

## 12. Complete Example: Reading OrderSnapshot with an Allowlist

The following example uses a programmatic filter and a simple DTO:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InvalidClassException;
import java.io.ObjectInputFilter;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;

public class FilteredDeserializationDemo {
    static final class OrderSnapshot implements Serializable {
        private static final long serialVersionUID = 1L;

        private final String orderId;
        private final String status;

        OrderSnapshot(String orderId, String status) {
            this.orderId = orderId;
            this.status = status;
        }

        @Override
        public String toString() {
            return "OrderSnapshot[orderId=" + orderId
                    + ", status=" + status + "]";
        }
    }

    static ObjectInputFilter filter() {
        return info -> {
            if (info.depth() > 10
                    || info.references() > 100
                    || info.streamBytes() > 100_000
                    || info.arrayLength() > 1_000) {
                return ObjectInputFilter.Status.REJECTED;
            }

            Class<?> type = info.serialClass();
            if (type == null) {
                return ObjectInputFilter.Status.UNDECIDED;
            }

            if (type == OrderSnapshot.class || type == String.class) {
                return ObjectInputFilter.Status.ALLOWED;
            }

            return ObjectInputFilter.Status.REJECTED;
        };
    }

    public static void main(String[] args)
            throws IOException, ClassNotFoundException {
        OrderSnapshot original =
                new OrderSnapshot("ORD-1001", "CONFIRMED");

        byte[] serialized;
        try (ByteArrayOutputStream bytes = new ByteArrayOutputStream();
             ObjectOutputStream output = new ObjectOutputStream(bytes)) {
            output.writeObject(original);
            output.flush();
            serialized = bytes.toByteArray();
        }

        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(serialized))) {
            input.setObjectInputFilter(filter());

            Object value = input.readObject();
            if (!(value instanceof OrderSnapshot order)) {
                throw new InvalidClassException(
                        "Unexpected root object type");
            }

            System.out.println(order);
        }
    }
}
~~~

Compile and run with JDK 17:

~~~bash
javac FilteredDeserializationDemo.java
java FilteredDeserializationDemo
~~~

The example uses self-generated data to demonstrate the API. In a real application, byte sources may come from files, networks, or caches; do not treat self-generated demo data as a sufficient safety model for external inputs.

## 13. Workflow for Designing an Application Filter

When building a filtering policy, follow this sequence:

1. List the classes actually required in valid object graphs.
2. Identify the packages/modules containing those classes.
3. Choose narrow patterns or programmatic allowlists.
4. Set maxdepth, maxrefs, maxbytes, and maxarray based on the largest valid data plus a safety margin.
5. Attach the filter before the first readObject call.
6. Test both valid payloads and payloads that must be rejected.
7. Verify exception handling and logging when the filter rejects.
8. If there are multiple deserialization contexts in the same JVM, consider a filter factory and policy combination rules.
9. After reading, check the root object type and validate business fields.

Do not set limits so low that valid data is rejected, nor set huge thresholds just to avoid errors. Measure actual object graph sizes and document the rationale for each threshold.

## 14. Common Errors and How to Handle Them

| Symptom | Cause | How to Handle |
| --- | --- | --- |
| Unknown objects are still read | Pattern did not match, so filter returned UNDECIDED. | Add deny-all such as !** or return REJECTED for classes outside the allowlist. |
| Valid classes are rejected | Allowlist missing dependent classes in the graph. | Inspect the actual classes needed and add those exact classes. |
| Pattern allows too many classes | Package wildcard is too broad. | Narrow the package or specify exact classes/modules. |
| Filter fails to block overly large graphs | Only classes checked, no resource limits set. | Add maxdepth, maxrefs, maxbytes, and maxarray or check FilterInfo in code. |
| Large arrays are still created | Array length limit not checked. | Set maxarray and check arrayLength() in filter code. |
| Classes in subpackages do not match | Used package.* instead of package.**. | Choose the wildcard matching the intended package scope. |
| Classes in named modules are not rejected by !* | !* applies only to classes in the unnamed module. | Use !** when needing to reject classes across all modules. |
| Stream throws InvalidClassException | Filter returned REJECTED or class incompatible. | Check filter status and rejected class; do not remove the filter just to read data. |
| JVM-wide filter breaks older libraries | Global policy too narrow or ignores valid library graphs. | Identify serialization dependencies and design an explicit policy; do not widen blindly. |
| Filter factory drops existing policy | Factory replaces old filter with new filter without combining. | Design combination rules preserving strict REJECTED decisions. |
| Object allowed by filter yet data is wrong | Filter does not check business rules. | Validate objects after reading and enforce authorization at the application layer. |

## 15. Practice Exercises

### Exercise 1 — Reading a Pattern

Explain the meaning of the pattern:

~~~text
maxdepth=15;maxrefs=5000;com.acme.dto.**;java.base/java.lang.String;!**
~~~

State whether classes in package com.acme.dto.internal are allowed and what decision classes outside the stated packages receive.

### Exercise 2 — Fixing Pattern Order

What is wrong with the following pattern?

~~~text
!**;com.acme.dto.**
~~~

Reorder it to allow the DTO package first and reject remaining classes afterward.

### Exercise 3 — Writing a Programmatic Allowlist

Write an ObjectInputFilter allowing only CustomerSnapshot and String. Reject all other classes. Add limits of depth max 12, references max 500, and streamBytes max 200,000.

### Exercise 4 — Checking Arrays

Write a filter allowing byte[] arrays up to 1 MB and String[] arrays up to 100 elements. Reject all other array types. Hint: check type.isArray(), type.getComponentType(), and info.arrayLength().

### Exercise 5 — Distinguishing UNDECIDED and REJECTED

A filter returns UNDECIDED when encountering a class not in the allowlist. Explain why this is not yet default-deny and fix the default branch to reject unknown classes.

### Exercise 6 — Choosing Configuration Scope

An application has three components reading different types of serialized objects. Propose how to combine a JVM-wide filter, per-stream filters, and a filter factory in Java 17. Explain how to ensure a rejection policy cannot be overridden by a less strict filter.

## 16. Key Points to Remember When Using Serialization Filters

- ObjectInputFilter controls classes and resource limits while ObjectInputStream deserializes.
- Patterns are built with ObjectInputFilter.Config.createFilter with items separated by semicolons.
- Class names match exact classes; package.* matches only direct classes; package.** includes subpackages.
- module/class patterns can restrict classes by module; * matches classes in the unnamed module, ** matches classes in all modules.
- ! is used to reject; class pattern order matters, so put allowlists before deny-all.
- maxdepth, maxrefs, maxbytes, and maxarray bound graph depth, reference count, bytes read, and array length.
- UNDECIDED does not equal REJECTED; default-deny requires rejecting classes outside the allowlist.
- Programmatic filters can use FilterInfo to inspect classes, array length, depth, references, and stream bytes.
- Attach filters to ObjectInputStream before reading objects; handle errors when a filter rejects.
- Java 17 adds filter factories under JEP 415 to choose filters by context; combine policies consistently.
- Filters do not replace sender authentication, authorization, or post-read business data validation.
- Continue using Java native serialization only when clearly justified; for untrusted data, filters are an important defense layer, not the sole measure.

### References

- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html) — FilterInfo, Status, filter patterns, and limits.
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html) — creating filters from patterns, configuring filters and filter factories.
- [Java SE 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html) — attaching filters to deserialization streams.
- [JEP 290: Filter Incoming Serialization Data](https://openjdk.org/jeps/290) — serialization filtering and graph limits.
- [JEP 415: Context-Specific Deserialization Filters](https://openjdk.org/jeps/415) — filter factories and context-specific policies in Java 17.
