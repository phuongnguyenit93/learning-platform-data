# `ObjectInputFilter.Config.setSerialFilterFactory` and Configuration Timing in Java 17

`ObjectInputFilter.Config.setSerialFilterFactory(...)` configures the **JVM-wide deserialization filter factory**. This factory decides which filter is attached to each `ObjectInputStream`, allowing you to combine the global filter, stream-specific filters, and runtime context policies.

The most critical aspect of the API is **call timing**: the factory can be configured only once and must be set **before any `ObjectInputStream` is created**. If a library or framework has already created a stream beforehand, calling the configuration method in application code can fail with `IllegalStateException`, even if `readObject()` has not yet been called.

This lesson focuses on the official Java 17 API, how the factory is invoked, initialization order, how to combine filters, and how to pick a safe configuration point.

## 1. Why Does Java Need a Filter Factory?

Java Serialization can reconstruct an object graph from a byte stream using `ObjectInputStream`. During that process, data determines which classes are instantiated, field values, and reference relationships between objects. Some classes contain logic in `readObject`, constructors, or deserialization callbacks; therefore reading untrusted data can pose security risks and cause excessive resource consumption.

`ObjectInputFilter` enables controlling:

- Which classes are allowed or rejected.
- Object graph depth.
- Total number of references.
- Array sizes.
- Bytes read from the stream.

A filter returns one of three statuses:

| Status | Meaning |
|---|---|
| `ALLOWED` | The filter accepts the data under inspection |
| `REJECTED` | The filter rejects; reading is aborted |
| `UNDECIDED` | The filter has not decided; another filter may continue evaluating |

If the final filter does not reject, deserialization can proceed. Thus, `UNDECIDED` is not equivalent to "reject".

### 1.1. Three Components to Distinguish

| Component | Role | Scope |
|---|---|---|
| **JVM-wide filter** | Shared filtering policy for the application/process | Entire JVM |
| **Stream-specific filter** | Additional or dedicated policy for a single `ObjectInputStream` | Single stream |
| **Filter factory** | Selects, combines, or produces the effective filter for each stream | Entire JVM |

Visualize it as:

```text
                         JVM
                          |
             setSerialFilterFactory(...)
                          |
                   Filter factory
                          |
              +-----------+-----------+
              |                       |
       ObjectInputStream A      ObjectInputStream B
              |                       |
       Effective filter A       Effective filter B
              |                       |
       reads object graph A     reads object graph B
              |                       |
       checkInput(...)          checkInput(...)
```

The factory is a **filter coordinator**. It does not automatically define which classes are safe. Allow/reject policies still must be expressed in the `ObjectInputFilter`s that the factory selects or combines.

## 2. Signature and Scope of setSerialFilterFactory

Java 17 API:

```java
public static void setSerialFilterFactory(
        BinaryOperator<ObjectInputFilter> filterFactory
)
```

Parts:

- `setSerialFilterFactory` is a static method on `ObjectInputFilter.Config`.
- `BinaryOperator<ObjectInputFilter>` receives two filters and returns one filter.
- The first argument is the stream's current filter.
- The second argument is the filter requested at the current call.
- The return value is the filter that will be used for the stream.

Minimal example:

```java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

BinaryOperator<ObjectInputFilter> factory = (current, requested) -> {
    if (current == null) {
        return requested;
    }
    if (requested == null) {
        return current;
    }
    return ObjectInputFilter.merge(current, requested);
};

ObjectInputFilter.Config.setSerialFilterFactory(factory);
```

This factory preserves the current filter when there is no new filter, uses the requested filter when there is no current filter, and merges both filters when both exist.

This is only an example of implementing `BinaryOperator`. In real applications, the factory may need to identify context, apply allow-lists, or combine additional filters by thread, module, library, or class loader.

### 2.1. The Factory Is a JVM-Wide Setting

`setSerialFilterFactory` does not accept a specific `ObjectInputStream` and does not configure a single class. It establishes one shared factory across the Java process.

Therefore:

- A JVM has only one active filter factory.
- `ObjectInputStream`s created in the JVM use that factory.
- You cannot call the method arbitrarily to swap factories per request.
- To get different filters for different streams, the factory itself must choose a filter based on context or the requested filter.

This is why JEP 415 introduced filter factories: an application can contain multiple libraries or execution contexts, each needing a different set of classes allowed for deserialization.

## 3. Most Important Rule: Configure Before Creating ObjectInputStream

`setSerialFilterFactory` must be called before **any `ObjectInputStream` instance is created**.

Correct ordering example:

```java
public class Application {
    public static void main(String[] args) {
        ObjectInputFilter.Config.setSerialFilterFactory(
                (current, requested) -> {
                    if (current == null) {
                        return requested;
                    }
                    if (requested == null) {
                        return current;
                    }
                    return ObjectInputFilter.merge(current, requested);
                }
        );

        startApplication();
    }

    private static void startApplication() {
        // Initialize frameworks, services, and other components
        // after the factory has been configured.
    }
}
```

The configuration call happens at the beginning of startup, before other components have a chance to create `ObjectInputStream`.

### 3.1. Do Not Wait Until readObject to Configure

Incorrect ordering example:

```java
ObjectInputStream input = new ObjectInputStream(source);

// Too late: the constructor above already created an ObjectInputStream.
ObjectInputFilter.Config.setSerialFilterFactory(factory);

Object value = input.readObject();
```

Failure does not depend on whether `readObject` has been called yet. Merely having created one `ObjectInputStream` means the precondition for configuring via this method is no longer met.

This also applies when streams are created by third-party libraries. Your application might not call `new ObjectInputStream(...)` directly, yet a framework, cache library, RPC layer, or another component may have created a stream earlier.

### 3.2. Can Only Be Configured Exactly Once

The factory can be configured using exactly one of these methods:

1. Calling `ObjectInputFilter.Config.setSerialFilterFactory` in code.
2. Setting the `jdk.serialFilterFactory` system property when launching the JVM.
3. Setting the `jdk.serialFilterFactory` Security property in the JDK's security configuration file.

Once a factory is configured, it cannot be replaced with another factory. If already configured via system property or Security property, the application cannot override it with `setSerialFilterFactory` either.

```java
ObjectInputFilter.Config.setSerialFilterFactory(factoryA);

// State error: cannot replace with factoryB.
ObjectInputFilter.Config.setSerialFilterFactory(factoryB);
```

The second call can throw `IllegalStateException`.

### 3.3. Error When Configuring Too Late

If the built-in factory has already been replaced or an `ObjectInputStream` has already been created, calling:

```java
ObjectInputFilter.Config.setSerialFilterFactory(factory);
```

throws `IllegalStateException`.

There is no public API to "unlock", swap the factory, or restore pre-stream-creation state. The proper fix is to configure at the next startup, before any component creates a stream.

### 3.4. Config Initialization Timing Also Matters

`ObjectInputFilter.Config` reads relevant properties when the class is initialized:

- `jdk.serialFilter` configures the JVM-wide filter.
- `jdk.serialFilterFactory` specifies the JVM-wide factory class.

Setting properties with `System.setProperty` after `ObjectInputFilter.Config` has been initialized **does not reconfigure** the filter or factory.

Example that does not behave as expected:

```java
// Config may have already initialized before this line.
System.setProperty(
        "jdk.serialFilterFactory",
        "com.example.security.MyFilterFactory"
);
```

If configuring via properties, set them at JVM launch time:

```bash
java -Djdk.serialFilterFactory=com.example.security.MyFilterFactory \
     -m com.example.app/com.example.app.Main
```

This lets the JVM know the factory from initialization, before application code starts creating streams.

## 4. What Happens When the Factory Is Called?

The factory is not called per object. It is called at two points related to configuring an `ObjectInputStream`:

1. When the `ObjectInputStream` constructor is invoked.
2. When the application calls `ObjectInputStream.setObjectInputFilter` to request a stream-specific filter.

Once the effective filter is chosen, `ObjectInputFilter.checkInput(...)` is invoked while reading the object graph.

### 4.1. First Call: ObjectInputStream Constructor

When a stream is created, the factory receives:

| Parameter | Value |
|---|---|
| `current` | `null` |
| `requested` | Configured JVM-wide filter, or `null` if none |

Example:

```java
ObjectInputFilter.Config.setSerialFilter(globalFilter);

// Factory is called inside the constructor.
ObjectInputStream input = new ObjectInputStream(source);
```

On this call, the factory can pick the global filter, add a context-based filter, or combine multiple filters to create the stream's initial filter.

### 4.2. Second Call: setObjectInputFilter

After creating the stream, the application can request a specific filter:

```java
try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(streamFilter);

    Object value = input.readObject();
}
```

The factory is invoked again with:

| Parameter | Value |
|---|---|
| `current` | Filter currently attached to the stream after construction |
| `requested` | Filter passed into `setObjectInputFilter` |

The factory determines the new effective filter. If you want to retain the global policy and add a stream-specific policy, the factory must combine them properly.

### 4.3. Factory Does Not Run on Every checkInput

Overall workflow:

```text
Application startup
       |
       v
setSerialFilterFactory(factory)
       |
       v
new ObjectInputStream(...)
       |
       | factory.apply(null, globalFilter)
       v
Stream's initial filter
       |
       +---- setObjectInputFilter(streamFilter)
       |          |
       |          | factory.apply(current, streamFilter)
       |          v
       |     New effective filter
       |
       v
readObject() / readUnshared()
       |
       v
ObjectInputFilter.checkInput(FilterInfo)
       |
       v
ALLOWED / REJECTED / UNDECIDED
```

Distinguish clearly:

- The factory's `apply(current, requested)` selects a filter for the stream.
- The filter's `checkInput(filterInfo)` inspects classes and resource limits during deserialization.

## 5. Roles of JVM-Wide Filters and Stream-Specific Filters

`setSerialFilterFactory` is commonly used alongside two other filter types.

### 5.1. JVM-Wide Filter

A JVM-wide filter applies at the process level. It can be configured via:

- System property `jdk.serialFilter` at launch.
- Security property `jdk.serialFilter`.
- `ObjectInputFilter.Config.setSerialFilter(filter)`.

Example configuring resource limits:

```java
ObjectInputFilter limits = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=10000;maxbytes=5000000"
);

ObjectInputFilter.Config.setSerialFilter(limits);
```

This filter bounds graph depth, reference count, and byte count. It is **not yet a class allow-list**; unconstrained classes may still yield `UNDECIDED`. Add a class policy suited to real data.

### 5.2. Stream-Specific Filter

A stream-specific filter is set via:

```java
input.setObjectInputFilter(streamFilter);
```

It fits when each data source or business workflow has a different set of permitted classes.

For example:

- Customer file import reads only customer DTOs.
- Configuration import reads only defined configuration types.
- A messaging library reads only message types belonging to its contract.

The stream filter must be set **before reading the first object**. Per the API, `setObjectInputFilter` can be called only once per stream.

### 5.3. What Does the Default Built-In Factory Do?

If an application does not configure a custom factory, Java uses the built-in filter factory compatible with legacy behavior:

- When creating `ObjectInputStream`, the JVM-wide filter is attached as the initial filter.
- When calling `setObjectInputFilter`, the requested filter replaces the JVM-wide filter under default behavior, unless a filter was already set per API rules.

This means the built-in factory **does not automatically combine** the global filter and the stream-specific filter.

If a combined policy is needed—for example, a global filter bounding resources and a stream filter restricting classes—provide a custom factory to decide how they merge.

## 6. Rules for current and requested

The factory receives two parameters of type `ObjectInputFilter`:

```java
ObjectInputFilter apply(
        ObjectInputFilter current,
        ObjectInputFilter requested
);
```

The following cases can occur:

| `current` | `requested` | Meaning |
|---|---|---|
| `null` | Global filter | Call from stream constructor |
| `null` | `null` | No global filter and no current filter yet |
| Filter A | Filter B | Requesting to add/change stream-specific filter |
| Filter A | `null` | No new filter; must retain current filter |

The factory must handle `null` in both parameters. Do not write code assuming both are always non-null.

### 6.1. Do Not Drop the Current Filter by Returning null

If `current` is non-null, the factory must return a non-null filter. This rule prevents accidentally disabling an attached filter.

Incorrect example:

```java
BinaryOperator<ObjectInputFilter> unsafeFactory =
        (current, requested) -> requested;
```

If `current` has a filter while `requested` is `null`, the factory returns `null`. That violates the rule and can cause `IllegalStateException`.

How to preserve the current filter:

```java
BinaryOperator<ObjectInputFilter> safeFactory = (current, requested) -> {
    if (current != null && requested == null) {
        return current;
    }

    if (current == null) {
        return requested;
    }

    return ObjectInputFilter.merge(current, requested);
};
```

This example demonstrates the principle of preserving filters. A real factory may also need context handling and class policies.

## 7. Combining Filters with ObjectInputFilter.merge

Java 17 provides:

```java
ObjectInputFilter.merge(filterA, filterB)
```

This method returns a filter combining the results of two filters.

Combination rules:

1. If either filter returns `REJECTED`, the result is `REJECTED`.
2. If neither rejects and at least one returns `ALLOWED`, the result is `ALLOWED`.
3. If both are undecided, the result is `UNDECIDED`.

Table:

| Filter A | Filter B | Merge Result |
|---|---|---|
| `REJECTED` | `ALLOWED` | `REJECTED` |
| `REJECTED` | `UNDECIDED` | `REJECTED` |
| `ALLOWED` | `UNDECIDED` | `ALLOWED` |
| `ALLOWED` | `ALLOWED` | `ALLOWED` |
| `UNDECIDED` | `UNDECIDED` | `UNDECIDED` |

### 7.1. Merge Is Not the Intersection of Two Allow-Lists

This is a very common point of confusion.

If filter A yields `ALLOWED` and filter B yields `UNDECIDED`, the result is `ALLOWED`. Thus `merge` does not require both filters to agree before allowing a class.

However, `REJECTED` always wins. One filter can reject a class regardless of whether the other filter accepts it.

If a design requires a class to be accepted by every allow-list, write combination logic matching that policy; do not assume `merge` means "both A and B allow".

### 7.2. UNDECIDED Can Lead to Acceptance

In the serialization filter mechanism, if a filter does not return `REJECTED`, reading can proceed. Therefore, a filter that only rejects a few classes and returns `UNDECIDED` for all remaining classes is not a strict allow-list.

`ObjectInputFilter.rejectUndecidedClass(filter)` can be used when the policy is to accept only explicitly allowed classes:

```java
ObjectInputFilter strictAllowList =
        ObjectInputFilter.rejectUndecidedClass(classFilter);
```

This method converts `UNDECIDED` results into `REJECTED` for classes per API rules, with special handling for primitives and arrays. Use it only when the input filter is genuinely designed around an allow-list model.

## 8. Minimal Factory Example: Combining Current and New Filters

A simple factory can be written as follows:

```java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

public final class MergingFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    public MergingFilterFactory() {
    }

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested
    ) {
        if (current == null) {
            return requested;
        }

        if (requested == null) {
            return current;
        }

        return ObjectInputFilter.merge(current, requested);
    }
}
```

Register at program startup:

```java
public class Main {
    public static void main(String[] args) {
        ObjectInputFilter.Config.setSerialFilterFactory(
                new MergingFilterFactory()
        );

        runApplication();
    }

    private static void runApplication() {
        // Start the rest of the application.
    }
}
```

Characteristics:

- The factory handles null arguments safely.
- The current filter is preserved when no new filter is supplied.
- When two filters exist, they are combined using `ObjectInputFilter.merge` rules.
- If the current filter is non-null, the result is never turned into null.

This is an illustrative factory for basic combination. It does not yet pick separate filters by user, thread, or data type.

## 9. ThreadLocal Context Factory Example

JEP 415 allows a factory to use information beyond the two parameters, such as thread-local context, call stack, module, or class loader.

A realistic scenario: one JVM handles multiple import workflows. Each workflow needs its own allow-list. The application can set a per-thread filter before creating `ObjectInputStream`; the factory reads that filter and combines it with the global filter.

Example:

```java
import java.io.ObjectInputFilter;
import java.util.concurrent.Callable;
import java.util.function.BinaryOperator;

public final class ContextFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    private static final ThreadLocal<ObjectInputFilter> CONTEXT_FILTER =
            new ThreadLocal<>();

    public ContextFilterFactory() {
    }

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested
    ) {
        if (current == null) {
            return merge(requested, CONTEXT_FILTER.get());
        }

        return merge(current, requested);
    }

    private static ObjectInputFilter merge(
            ObjectInputFilter first,
            ObjectInputFilter second
    ) {
        if (first == null) {
            return second;
        }

        if (second == null) {
            return first;
        }

        return ObjectInputFilter.merge(first, second);
    }

    public static <T> T withFilter(
            ObjectInputFilter filter,
            Callable<T> action
    ) throws Exception {
        ObjectInputFilter previous = CONTEXT_FILTER.get();

        try {
            if (filter == null) {
                CONTEXT_FILTER.remove();
            } else {
                CONTEXT_FILTER.set(filter);
            }

            return action.call();
        } finally {
            if (previous == null) {
                CONTEXT_FILTER.remove();
            } else {
                CONTEXT_FILTER.set(previous);
            }
        }
    }
}
```

Register the factory once during bootstrap:

```java
ObjectInputFilter.Config.setSerialFilterFactory(
        new ContextFilterFactory()
);
```

Then, when reading a data type:

```java
ObjectInputFilter importFilter = info -> {
    Class<?> type = info.serialClass();

    if (type == null) {
        return ObjectInputFilter.Status.UNDECIDED;
    }

    if (type == ImportRecord.class || type == String.class) {
        return ObjectInputFilter.Status.ALLOWED;
    }

    return ObjectInputFilter.Status.REJECTED;
};

Object value = ContextFilterFactory.withFilter(
        importFilter,
        () -> {
            try (ObjectInputStream input =
                         new ObjectInputStream(source)) {
                return input.readObject();
            }
        }
);
```

In this example:

1. `withFilter` places the import policy into ThreadLocal.
2. `new ObjectInputStream` invokes the factory.
3. The factory receives the JVM-wide filter via `requested` and retrieves the thread-local filter.
4. The factory combines both filters into the stream's filter.
5. After the constructor completes, the filter is already attached to the stream; cleaning up ThreadLocal in `finally` does not remove the attached filter.
6. When `readObject` reads data, the effective filter checks classes and resource limits.

The illustrative filter allows only two specific classes. Real applications must list all valid data types, including types in the object graph such as collections or needed helper types. Do not use this example as a complete allow-list for every application.

### 9.1. Why Restore ThreadLocal in finally?

Server applications commonly use thread pools. Calling `ThreadLocal.set` without restoring or removing the value lets the next request run on the same thread and accidentally receive the previous request's filter.

The `try/finally` pattern in the example preserves the prior value and restores it after the task finishes. This is an essential principle when using thread-scoped context.

For asynchronous processing or thread handoffs, `ThreadLocal` does not automatically propagate context to other threads. Use a context-propagation mechanism suited to your application's architecture.

## 10. Configuring the Factory via System Property

If you want to configure at JVM startup instead of calling the API in code, use:

```bash
java -Djdk.serialFilterFactory=com.example.security.MyFilterFactory \
     -jar application.jar
```

The property value is the **fully qualified name of the factory class**, not a method name or lambda expression.

The factory class is loaded by the JVM during configuration initialization and must:

- Be a `public` class.
- Have a `public` no-arg constructor.
- Implement `BinaryOperator<ObjectInputFilter>`.
- Be accessible via the application class loader.
- Provide an implementation of `apply`.

Class skeleton example:

```java
package com.example.security;

import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

public final class MyFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    public MyFilterFactory() {
    }

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested
    ) {
        if (current == null) {
            return requested;
        }
        if (requested == null) {
            return current;
        }
        return ObjectInputFilter.merge(current, requested);
    }
}
```

When a factory is specified by property, the application must not call `setSerialFilterFactory` to swap the factory. Configuration from the property cannot be overridden by that call.

### 10.1. Security Property

`jdk.serialFilterFactory` can be set in the JDK's Security file. This suits applying a factory via runtime configuration across applications using that JDK.

System properties take higher priority than Security properties of the same name. If both are set, the system property is used.

### 10.2. System.setProperty Does Not Replace Startup Configuration

Do not do:

```java
System.setProperty(
        "jdk.serialFilterFactory",
        "com.example.security.MyFilterFactory"
);
```

and expect the JVM to load the factory right afterward. This property is read when `ObjectInputFilter.Config` initializes; changing it later neither installs nor replaces the factory.

If dynamic configuration in application code is needed, call `setSerialFilterFactory` exactly once in bootstrap, before any `ObjectInputStream`.

## 11. Distinguishing setSerialFilter and setSerialFilterFactory

These two APIs have similar names but different responsibilities:

| API | Accepts | Function |
|---|---|---|
| `Config.setSerialFilter(filter)` | An `ObjectInputFilter` | Sets the JVM-wide filter |
| `Config.setSerialFilterFactory(factory)` | A `BinaryOperator<ObjectInputFilter>` | Sets the factory selecting/combining filters per stream |
| `ObjectInputStream.setObjectInputFilter(filter)` | An `ObjectInputFilter` | Requests a stream-specific filter for a stream |

Example when only a simple global policy is needed:

```java
ObjectInputFilter globalFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=20;maxrefs=10000;maxbytes=5000000"
        );

ObjectInputFilter.Config.setSerialFilter(globalFilter);
```

In this case a custom factory is usually unnecessary. The default built-in factory attaches the global filter to new streams.

Only consider `setSerialFilterFactory` when streams need different filters and must combine them with the global policy.

### 11.1. What Does getSerialFilterFactory Return?

```java
BinaryOperator<ObjectInputFilter> factory =
        ObjectInputFilter.Config.getSerialFilterFactory();
```

This method returns the active factory. If the application has not configured a custom factory, the result is still the JDK's built-in factory.

Therefore, `getSerialFilterFactory()` returning an object does not mean the application has installed a custom factory.

Similarly:

```java
ObjectInputFilter filter =
        ObjectInputFilter.Config.getSerialFilter();
```

can return `null` if no JVM-wide filter is set yet.

## 12. When Is the Factory Called vs. When Is the Filter Called?

Distinguish the lifecycle of the factory from the lifecycle of the filter.

| Operation | Component Called | Purpose |
|---|---|---|
| `setSerialFilterFactory` | Does not call `apply` immediately per stream | Registers the JVM-wide factory |
| `new ObjectInputStream(...)` | `factory.apply(null, globalFilter)` | Selects initial filter |
| `setObjectInputFilter(filter)` | `factory.apply(current, requested)` | Selects new effective filter |
| `readObject()` / `readUnshared()` | `filter.checkInput(info)` | Inspects data being deserialized |

The filter can be invoked many times while reading an object graph. The factory does not run per class or per reference.

### 12.1. What Information Does FilterInfo Provide?

In `checkInput`, `ObjectInputFilter.FilterInfo` provides:

- `serialClass()`: class being checked, may be `null` for metric-only checks.
- `arrayLength()`: array length if the element under inspection is an array.
- `depth()`: object graph depth.
- `references()`: number of references read.
- `streamBytes()`: number of bytes read from the stream per implementation.

Example resource-limiting filter:

```java
ObjectInputFilter limits = info -> {
    if (info.depth() > 20) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.references() > 10_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.streamBytes() > 5_000_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    if (info.arrayLength() > 100_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
```

This filter rejects graphs exceeding limits and returns `UNDECIDED` when within limits. It does not build a class allow-list itself; combine it with a class policy to restrict object types.

Data such as primitives and Strings encoded directly in the stream have their own filter-invocation rules; never assume the filter will validate every field value or every string content. Applications still must validate data after reading per business contracts.

## 13. Configuration Timing in the Application Lifecycle

A proper startup sequence:

1. JVM receives system/security properties.
2. Application starts running.
3. Application configures the JVM-wide filter if needed.
4. Application configures a custom filter factory if needed.
5. Frameworks and services are initialized.
6. Components create `ObjectInputStream`s.
7. The factory selects a filter for each stream.
8. While reading data, the filter inspects the object graph.

Diagram:

```text
JVM launch
   |
   +-- read -Djdk.serialFilter
   |
   +-- read -Djdk.serialFilterFactory
   |
   v
Application bootstrap
   |
   +-- setSerialFilter(...)        (if configured in code)
   |
   +-- setSerialFilterFactory(...) (if configured in code)
   |
   v
Initialize frameworks / services
   |
   v
Create ObjectInputStream
   |
   v
Factory selects filter
   |
   v
Read objects and check filter
```

### 13.1. Why Configure Before Initializing Frameworks?

Frameworks may create `ObjectInputStream` during:

- Initializing caches or session stores.
- Loading serialized configuration or state.
- Creating RPC channels or object exchange mechanisms.
- Initializing integrated libraries that use Java Serialization.

If the application waits until handling the first request to configure, it may already be too late.

Placing the factory in central bootstrap gives clear ordering control. If you cannot control when `ObjectInputFilter.Config` initializes or when the first stream is created, configuring via JVM property at launch is the more reliable option.

## 14. Common Mistakes

| Error or Symptom | Cause | How to Handle |
|---|---|---|
| `IllegalStateException` when calling `setSerialFilterFactory` | Factory already configured or an `ObjectInputStream` already created | Move configuration to bootstrap or use JVM launch property |
| Factory not loaded from `System.setProperty` | Property set after `Config` already initialized | Use `-Djdk.serialFilterFactory` or Security property |
| First factory call has both parameters null | Neither static filter nor current filter exists | Factory must handle null safely; may return null if policy allows |
| Global filter replaced by stream filter | Default built-in factory does not merge two filters automatically | Configure a custom factory if combining is needed |
| Current filter disappears | Factory returned null when current was non-null | Always preserve current or return a non-null combined filter |
| Class not blocked even though filter returns UNDECIDED | No filter returned REJECTED | Use an allow-list or reject undecided results per policy |
| Valid classes are rejected | Allow-list misses supporting classes in the object graph | Add exact needed types, do not broaden to allow-all |
| Subsequent request mistakenly uses previous request's filter | ThreadLocal was not restored | Use try/finally to restore or remove context |
| Factory runs yet data remains unsafe | Factory only selects filters; filter policy is too broad or absent | Design concrete allow-lists and resource limits |

### 14.1. Factory Returning null Does Not Mean Reject All

`null` indicates the stream has no effective filter. It is not the `REJECTED` status.

If the application needs to protect every stream, the factory must ensure an appropriate filter is attached to each stream. In particular, if there is no static filter, no context filter, and the factory returns null, the stream may remain unfiltered.

### 14.2. Do Not Allow All Classes Just to Avoid Errors

A filter like:

```java
info -> ObjectInputFilter.Status.ALLOWED
```

allows every class and defeats the purpose of restricting deserialization. Only allowlist types genuinely needed and set reasonable resource limits.

### 14.3. Do Not Treat the Factory as Data Validation

Filters control classes and certain object graph metrics. They do not replace:

- Sender authentication.
- Data integrity or signature verification.
- Business validation of field values.
- Encrypting data in transit or at rest.
- Avoiding deserializing untrusted data.

Whenever possible, prefer data formats with schemas and safe parsers over Java native serialization for external data.

## 15. Complete Example: Configuring a Factory at Bootstrap

The following example illustrates an application with global limits and per-workflow filters.

### 15.1. Factory

```java
import java.io.ObjectInputFilter;
import java.util.function.BinaryOperator;

public final class ApplicationFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    public ApplicationFilterFactory() {
    }

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested
    ) {
        if (current == null) {
            return requested;
        }

        if (requested == null) {
            return current;
        }

        return ObjectInputFilter.merge(current, requested);
    }
}
```

### 15.2. Bootstrap

```java
import java.io.ObjectInputFilter;

public final class Main {
    public static void main(String[] args) {
        ObjectInputFilter globalLimits =
                ObjectInputFilter.Config.createFilter(
                        "maxdepth=20;maxrefs=10000;maxbytes=5000000;maxarray=100000"
                );

        // Set the JVM-wide limit policy.
        ObjectInputFilter.Config.setSerialFilter(globalLimits);

        // Must be called before any ObjectInputStream is created.
        ObjectInputFilter.Config.setSerialFilterFactory(
                new ApplicationFilterFactory()
        );

        startServices();
    }

    private static void startServices() {
        // Initialize services, frameworks, and other components.
    }
}
```

In this example, the global filter bounds resources. It does not restrict classes because the pattern contains only resource limits. The factory preserves that filter at stream creation and merges a stream filter if requested.

The application still must add a class allow-list policy for untrusted data. Bounding depth/bytes/arrays alone is insufficient to determine which classes are safe.

### 15.3. Attaching a Stream-Specific Filter

```java
ObjectInputFilter streamFilter = ObjectInputFilter.Config.createFilter(
        "com.example.dto.**;java.base/*;!*"
);

try (ObjectInputStream input = new ObjectInputStream(source)) {
    input.setObjectInputFilter(streamFilter);

    Object value = input.readObject();
}
```

With the custom factory above, the stream filter is merged with the current filter. Because `merge` prioritizes `REJECTED`, global limits or rejection rules from the current filter can still block classes.

The illustrative pattern allows the DTO package and classes in the `java.base` module; this remains an example to tailor to your actual object graph. Do not use overly broad package patterns if the data only needs a few specific types.

## 16. When to Use a Custom Factory, and When Not To?

| Scenario | Choice |
|---|---|
| Application only needs shared class and resource limits | JVM-wide filter via `setSerialFilter` or `jdk.serialFilter` property |
| Each stream needs a distinct allow-list, no need to combine global filter | Stream-specific filter; check built-in factory behavior |
| Need to keep global filter and merge per-stream filters | Custom factory via `setSerialFilterFactory` |
| Multiple modules/libraries have different deserialization contexts | Custom factory selecting filters by context |
| Need mandatory configuration before application code runs | System/Security property `jdk.serialFilterFactory` |
| Application already created ObjectInputStream before bootstrap finished | Cannot install custom factory via method afterward; fix startup order or configure on next launch |

Do not use a custom factory merely because the application uses `ObjectInputFilter`. For simple policies, a JVM-wide filter and the default built-in factory are usually sufficient.

## 17. Practice Exercises

### Exercise 1 — When to Call the Factory?

An application creates an `ObjectInputStream` in a library's static initializer, and only later calls `setSerialFilterFactory` in `main`.

**Answer:** Too late. The stream constructor ran first and the default factory was already used. Configure via a JVM property or ensure the factory is installed before the library creates a stream.

### Exercise 2 — How Many Times Is the Factory Called?

A stream is created and then `setObjectInputFilter` is called once. At which points is the factory invoked?

**Answer:** Twice: once in the `ObjectInputStream` constructor and once in `setObjectInputFilter`. It is not called for every object in the stream.

### Exercise 3 — What Do Two Null Parameters Mean?

The first call has `current == null` and `requested == null`.

**Answer:** Neither a current filter nor a JVM-wide filter was passed in. The factory may return null if the application genuinely allows unfiltered streams, or return a default application filter.

### Exercise 4 — Why Must the Factory Not Return Null?

A stream has a non-null `current` filter; the next call has `requested == null`. The factory returns null.

**Answer:** This violates the rule against replacing a non-null current filter with null. The factory must return current or a non-null combined filter.

### Exercise 5 — Is Merge the Intersection of Two Allow-Lists?

Filter A returns `ALLOWED`; filter B returns `UNDECIDED`.

**Answer:** `ObjectInputFilter.merge` returns `ALLOWED`. This is not an intersection of allow-lists. If either filter returns `REJECTED`, the result is always `REJECTED`.

### Exercise 6 — Does setSerialFilterFactory Replace setSerialFilter?

**Answer:** No. `setSerialFilter` sets a JVM-wide filter; `setSerialFilterFactory` sets the function that selects/combines filters for each stream. The factory can receive the static filter as the `requested` argument on the first call.

### Exercise 7 — Can the Factory Be Configured via System.setProperty in main?

**Answer:** You should not rely on it. The property is read when `ObjectInputFilter.Config` initializes. Use `-Djdk.serialFilterFactory` at JVM launch or call `setSerialFilterFactory` early in bootstrap before any stream.

### Exercise 8 — The Factory Ran, So Are Objects Checked Yet?

**Answer:** Not yet. The factory only selects the filter. The filter's `checkInput` is called during `readObject`/`readUnshared` to inspect classes and object graph metrics.

## 18. Key Points to Remember

- `ObjectInputFilter.Config.setSerialFilterFactory` configures a JVM-wide factory, not an individual stream.
- The factory can be configured only once via method, system property, or Security property.
- When using the method, call it before any `ObjectInputStream` is created.
- Factory calls occur in the `ObjectInputStream` constructor and when `setObjectInputFilter` is called.
- The factory does not run per object; `ObjectInputFilter.checkInput` inspects data during deserialization.
- The first call has `current == null`; `requested` is the JVM-wide filter or null.
- If `current` is non-null, the factory must return a non-null filter.
- The default built-in factory attaches the JVM-wide filter on stream creation; stream-specific filters replace that filter under default behavior.
- Use a custom factory when you need to combine global filters, stream filters, and context-specific filters.
- `ObjectInputFilter.merge` prioritizes REJECTED, then ALLOWED, and finally UNDECIDED; it is not an allow-list intersection.
- `System.setProperty` after Config initializes does not reconfigure the factory.
- The factory does not create security policies by itself; the application must supply suitable allow-lists and resource limits.
- Avoid deserializing untrusted data when possible; serialization filters are only one defense layer.

## Official Java 17 References

- [Java SE 17 API — `ObjectInputFilter.Config`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html).
- [Java SE 17 API — `ObjectInputFilter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html).
- [Java SE 17 API — `ObjectInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html).
- [Oracle Java 17 — Serialization Filtering](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html).
- [JEP 290 — Filter Incoming Serialization Data](https://openjdk.org/jeps/290).
- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415).
