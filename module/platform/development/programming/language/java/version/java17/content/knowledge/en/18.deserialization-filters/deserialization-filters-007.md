# Context-Specific Filter Factories Since Java 17

Java Serialization can restore an object graph from a byte stream using `ObjectInputStream`. If data comes from an untrusted source, deserialization can trigger logic inside restored classes and consume significant resources. Therefore, applications need to restrict which classes can be read and bound object graph size.

Java has had `ObjectInputFilter` since Java 9 to inspect classes and limit resources during deserialization. However, a large application may contain many libraries or processing flows, each needing a different set of classes. An overly broad JVM-wide filter cannot satisfy every context well; a per-stream filter can accidentally replace the global policy.

Java 17 adds **context-specific filter factories** via JEP 415. The factory decides which filter attaches to each `ObjectInputStream`, based on the current filter, the requested filter, and context information such as thread, call stack, module, library, or class loader. As a result, applications can combine shared policies with policies specific to each processing flow.

## 1. Why Are Filter Factories Needed?

A filter controls two groups of conditions:

- **Data types:** which classes are allowed or rejected when reading objects.
- **Resources:** graph depth, reference count, array size, and bytes read.

A system may have multiple deserialization contexts:

| Context | Expected Data Types |
| --- | --- |
| Reading internal messages | Messaging module DTOs and known supporting types |
| Reading cache | Application-controlled cache types |
| Reading partner-compatible data | A narrow set of classes per the partner protocol |
| Reading job state | Job status and metadata types |

If everything shares one large allow-list, each stream can read more types than necessary. If each component calls `setObjectInputFilter` independently, a component can replace the JVM-wide filter under Java's default behavior.

A filter factory solves **selecting or combining filters per stream**. The factory does not inspect individual objects itself; it supplies the `ObjectInputFilter` that `ObjectInputStream` calls while reading.

## 2. ObjectInputFilter and the Three Result Statuses

`java.io.ObjectInputFilter` is a functional interface. A filter receives `FilterInfo` and returns one of three statuses:

| Status | Meaning |
| --- | --- |
| `ALLOWED` | The filter confirms the object/condition is allowed |
| `REJECTED` | The filter rejects; deserialization is aborted |
| `UNDECIDED` | The filter makes no decision for that information |

`UNDECIDED` does not equal rejection. If the final filter returns `UNDECIDED`, `ObjectInputStream` can still proceed with deserialization. Therefore, when building an allow-list, ensure unlisted classes are rejected rather than left undecided.

### 2.1. What Information Does a Filter Inspect?

`ObjectInputFilter.FilterInfo` provides:

- `serialClass()`: class being checked; may be `null` when the check pertains only to graph metrics.
- `arrayLength()`: array length if the object is an array, or negative if not.
- `depth()`: current depth of the object graph.
- `references()`: number of object references read so far in the stream.
- `streamBytes()`: number of bytes consumed from the stream per implementation.

A filter can check one or more pieces of information. Example:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter resourceFilter = info -> {
    if (info.depth() > 12
            || info.references() > 500
            || info.streamBytes() > 1_000_000
            || info.arrayLength() > 20_000) {
        return ObjectInputFilter.Status.REJECTED;
    }

    return ObjectInputFilter.Status.UNDECIDED;
};
~~~

This example limits only resources; it does not allow a specific class. Without another filter deciding classes, returning `UNDECIDED` does not form an allow-list. In real applications, combine resource limits with an explicit class policy.

### 2.2. Pattern Filters

Java provides `ObjectInputFilter.Config.createFilter(String)` to construct a filter from a pattern string:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter filter = ObjectInputFilter.Config.createFilter(
        "maxdepth=12;maxrefs=200;maxbytes=500000;maxarray=10000;"
        + "com.example.dto.Message;!*");
~~~

Common limits:

| Pattern | Meaning |
| --- | --- |
| `maxdepth=12` | Maximum graph depth |
| `maxrefs=200` | Maximum reference count |
| `maxbytes=500000` | Maximum bytes read |
| `maxarray=10000` | Maximum array length |

Class patterns can specify class, package, or module names. A leading `!` rejects matching classes. `*` and `**` have different meanings: `package.*` matches classes directly in the package, while `package.**` includes subpackages. Trailing `!*` rejects all classes not matching earlier allow patterns.

For an allow-list, the `!*` part is critical. Omitting it can cause unmatched classes to return `UNDECIDED`, which does not automatically mean blocked.

## 3. JVM-Wide Filters and Per-Stream Filters

Java has two filter scopes:

**Static JVM-wide filter** applies across the entire JVM. It can be configured with the `jdk.serialFilter` system property at launch or via `ObjectInputFilter.Config.setSerialFilter(...)`.

**Stream-specific filter** attaches to a single `ObjectInputStream` via `setObjectInputFilter(...)`.

Example configuring a JVM-wide filter via command line:

~~~bash
java -Djdk.serialFilter="maxdepth=20;maxrefs=1000;maxbytes=2000000;!com.example.legacy.UnsafeType" \
     -jar application.jar
~~~

Or configuring in code before a filter is set:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter globalFilter = ObjectInputFilter.Config.createFilter(
        "maxdepth=20;maxrefs=1000;maxbytes=2000000;"
        + "!com.example.legacy.UnsafeType");

ObjectInputFilter.Config.setSerialFilter(globalFilter);
~~~

`setSerialFilter` sets the JVM-wide filter only if no filter has been configured or set earlier. If a filter was already set via system property, Security property, or another API call, setting it again may throw `IllegalStateException`.

### 3.1. Default Factory Behavior

If the application does not register a custom factory, `ObjectInputFilter.Config.getSerialFilterFactory()` returns the built-in factory. This factory preserves compatibility with pre-Java 17 filter configuration:

1. When creating `ObjectInputStream`, the JVM-wide filter is used as the stream's initial filter.
2. When calling `setObjectInputFilter(...)`, the requested stream filter replaces the initial filter under default behavior.

The second point is crucial: **per-stream filters are not combined with the JVM-wide filter by default**. If the application wants both policies enforced, a custom factory is needed to combine them.

## 4. When Is the Filter Factory Called?

The factory has type `BinaryOperator<ObjectInputFilter>` and is invoked at two times:

1. When creating an `ObjectInputStream`.
2. When calling `ObjectInputStream.setObjectInputFilter(...)` to set a stream-specific filter.

The factory takes two parameters:

~~~java
ObjectInputFilter apply(
        ObjectInputFilter current,
        ObjectInputFilter requested)
~~~

Meaning of the two parameters:

| Parameter | At Stream Creation | When Calling setObjectInputFilter |
| --- | --- | --- |
| `current` | `null` | Filter currently attached to the stream |
| `requested` | Static JVM-wide filter | Filter passed to `setObjectInputFilter` |

The factory returns the final filter to be attached to the stream.

Diagram:

~~~text
new ObjectInputStream(...)
        |
        v
Factory.apply(null, globalFilter)
        |
        v
Select initial filter for stream
        |
        v
setObjectInputFilter(streamFilter)
        |
        v
Factory.apply(currentFilter, streamFilter)
        |
        v
Select final filter
        |
        v
readObject() / readUnshared()
        |
        v
ObjectInputFilter.checkInput(...)
        |
        +---- ALLOWED / proceed
        +---- UNDECIDED / another filter or default rule decides
        +---- REJECTED / abort deserialization
~~~

The factory can also use information beyond the two parameters, such as `ThreadLocal`, call stack, module, or class loader. This is the basis for context-based filter selection.

### 4.1. A Factory Is Not a Filter

The two components have distinct roles:

- **Factory** selects or combines filters when a stream is created/configured.
- **Filter** inspects classes and resource metrics while a stream is being read.

Do not put per-object inspection logic inside the factory. That logic belongs in `ObjectInputFilter.checkInput(FilterInfo)`.

## 5. Configuring a Factory in Java 17

Java 17 provides:

~~~java
ObjectInputFilter.Config.getSerialFilterFactory();
ObjectInputFilter.Config.setSerialFilterFactory(factory);
~~~

`getSerialFilterFactory()` always returns the active factory; if no custom factory is registered, it returns the built-in factory.

`setSerialFilterFactory(...)` has important lifecycle rules:

- The factory can be configured only once.
- It must be configured before any `ObjectInputStream` is created.
- If a factory was already configured via system property or Security property, it cannot be changed via this API call.
- If an `ObjectInputStream` was already created earlier, calling this method can throw `IllegalStateException`.
- The factory argument must not be `null`.
- If `current` is non-null, the factory must return a non-null filter so as not to accidentally disable an already-enabled filter.

Therefore, register the factory during application bootstrap, before frameworks or libraries create `ObjectInputStream`s.

### 5.1. Registering Directly via API

~~~java
import java.io.ObjectInputFilter;

ContextFilterFactory factory = new ContextFilterFactory();
ObjectInputFilter.Config.setSerialFilterFactory(factory);
~~~

Do not call this multiple times in the same JVM. If independent factories must be tested, run JVM-wide configuration tests in separate JVM processes or design tests around a single registered factory.

### 5.2. Configuring via System Property

The factory can be configured from the command line:

~~~bash
java -Djdk.serialFilterFactory=com.example.security.ContextFilterFactory \
     -jar application.jar
~~~

The value is the fully qualified name of the factory class. The class must:

- Be `public`.
- Have a `public` no-arg constructor.
- Implement `BinaryOperator<ObjectInputFilter>`.
- Be loadable by the application class loader.

The same configuration can be set in the JDK's `jdk.serialFilterFactory` Security property.

System properties take precedence over Security properties of the same name. If the factory is configured via property when `ObjectInputFilter.Config` initializes, the application cannot change it with `setSerialFilterFactory`.

Do not call `System.setProperty("jdk.serialFilterFactory", "...")` after the application has initialized `ObjectInputFilter.Config` and expect the factory to change. Configure the property on the command line or in the Security file before the JVM launches the application.

## 6. Combining Filters with ObjectInputFilter.merge

Java 17 provides helpful methods for creating composite filters:

- `ObjectInputFilter.merge(filter, anotherFilter)`
- `ObjectInputFilter.rejectUndecidedClass(filter)`
- `ObjectInputFilter.allowFilter(predicate, otherStatus)`
- `ObjectInputFilter.rejectFilter(predicate, otherStatus)`

`merge` combines the results of two filters per the rules:

1. If either filter returns `REJECTED`, the result is `REJECTED`.
2. If neither rejects and at least one returns `ALLOWED`, the result is `ALLOWED`.
3. If both are `UNDECIDED`, the result is `UNDECIDED`.

This means `merge` lets an `ALLOWED` decision beat `UNDECIDED`, while `REJECTED` always retains veto power.

### 6.1. Merge Does Not Automatically Turn Any Filters into an Allow-List Intersection

Suppose:

- Filter A returns `ALLOWED` for `com.example.dto.Message`.
- Filter B returns `UNDECIDED` for that class.

The merge result is `ALLOWED`. Therefore, if you want a strict allow-list, each filter must explicitly reject unlisted classes—for instance, via patterns ending in `!*`.

`rejectUndecidedClass` can turn `UNDECIDED` into `REJECTED` for undecided classes, yet it cannot reverse an `ALLOWED` result already produced by `merge`. Thus, design each filter's semantics carefully.

### 6.2. Allow-List Filter Example

~~~java
ObjectInputFilter messageFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=12;maxrefs=200;maxbytes=500000;"
                + "maxarray=10000;com.example.dto.Message;!*");
~~~

This filter allows only `com.example.dto.Message` alongside the set resource limits. When the object graph includes additional types, list those types according to the protocol's requirements.

For applications with many DTOs, list the set of classes genuinely required. Avoid overly broad wildcards like an entire application package if that package also contains unrelated types.

## 7. Selecting Filters via ThreadLocal Context

One Java-supported implementation pattern stores context-specific filters in a `ThreadLocal`. Before creating `ObjectInputStream`, code sets the corresponding filter on the current thread. The factory reads that value and combines it with the JVM-wide filter.

The pattern below illustrates an allow-list-based factory:

~~~java
import java.io.ObjectInputFilter;
import java.util.Objects;
import java.util.function.BinaryOperator;
import java.util.function.Supplier;

public final class ContextFilterFactory
        implements BinaryOperator<ObjectInputFilter> {

    private final ThreadLocal<ObjectInputFilter> contextFilter =
            new ThreadLocal<>();

    @Override
    public ObjectInputFilter apply(
            ObjectInputFilter current,
            ObjectInputFilter requested) {

        if (current == null) {
            // Called from the ObjectInputStream constructor.
            ObjectInputFilter context = contextFilter.get();
            ObjectInputFilter selected =
                    merge(requested, context);
            return context == null ? selected : strictAllowList(selected);
        }

        // Called when the stream requests a specific filter.
        if (requested == null) {
            return current;
        }

        return merge(requested, current);
    }

    private static ObjectInputFilter merge(
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

    private static ObjectInputFilter strictAllowList(
            ObjectInputFilter filter) {
        if (filter == null) {
            return null;
        }
        return ObjectInputFilter.rejectUndecidedClass(filter);
    }

    public <T> T withContextFilter(
            ObjectInputFilter filter,
            Supplier<T> action) {
        Objects.requireNonNull(action, "action");

        ObjectInputFilter previous = contextFilter.get();
        try {
            if (filter == null) {
                contextFilter.remove();
            } else {
                contextFilter.set(filter);
            }
            return action.get();
        } finally {
            if (previous == null) {
                contextFilter.remove();
            } else {
                contextFilter.set(previous);
            }
        }
    }
}
~~~

This factory:

1. When `current == null`, takes the requested filter (usually the static JVM-wide filter) and the current thread's filter.
2. Merges both filters if both exist.
3. When the stream requests a stream filter, merges it with the stream's current filter.
4. Keeps the current filter if the new call does not request another filter.
5. Never returns `null` when `current` already has a filter.
6. Restores the previous `ThreadLocal` value in `finally`, preventing context leaks into subsequent requests on a thread pool.

Usage example:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ObjectInputStream;
import java.io.ObjectInputFilter;

ContextFilterFactory factory = new ContextFilterFactory();
ObjectInputFilter messageFilter =
        ObjectInputFilter.Config.createFilter(
                "maxdepth=12;maxrefs=200;maxbytes=500000;"
                + "maxarray=10000;com.example.dto.Message;!*");

ObjectInputFilter.Config.setSerialFilterFactory(factory);

Object result = factory.withContextFilter(messageFilter, () -> {
    try (ObjectInputStream input = new ObjectInputStream(
            new ByteArrayInputStream(serializedBytes))) {
        return input.readObject();
    } catch (Exception e) {
        throw new IllegalStateException("Cannot read message", e);
    }
});
~~~

In the example, the context filter is set before creating the stream. The constructor invokes the factory and the factory attaches the combined filter to the stream. The `try-with-resources` block closes `ObjectInputStream` after reading.

The example illustrates the structure; in real applications, define concrete exception policies and return types instead of converting all errors to `IllegalStateException`.

### 7.1. Why Restore ThreadLocal in finally?

Server applications commonly reuse threads via executors or thread pools. If a filter is placed in `ThreadLocal` without clearing/restoring it afterward, the next request can inherit the previous request's policy.

Pattern:

~~~java
ObjectInputFilter previous = context.get();
try {
    context.set(requestFilter);
    deserialize();
} finally {
    if (previous == null) {
        context.remove();
    } else {
        context.set(previous);
    }
}
~~~

Restoring the previous value also supports nested contexts: a task can temporarily swap filters and then restore the parent task's filter.

### 7.2. ThreadLocal Does Not Propagate Across Executors Automatically

`ThreadLocal` is bound to the current thread. If a request sets a filter on thread A and delegates deserialization to thread B, thread B does not automatically inherit that value.

Therefore:

- Set context on the same thread that creates `ObjectInputStream`.
- For asynchronous processing, pass context explicitly to tasks running on target threads.
- Do not assume thread pools or `CompletableFuture` automatically propagate `ThreadLocal`.
- Do not use a shared mutable variable across requests when requests have different policies.

## 8. Selecting Context by Call Stack, Module, or Class Loader

ThreadLocal is one option, not the only way. A factory can choose filters based on:

- **Call stack:** identifying which component invoked deserialization code.
- **Module:** choosing policy based on the library's or caller's module.
- **Class loader:** distinguishing different plugins or class-loading environments.
- **Library/context:** distinguishing components with different data contracts.
- **Thread context:** using application-attached info on the current thread.

Conceptual example:

~~~java
Class<?> caller = StackWalker.getInstance(
        StackWalker.Option.RETAIN_CLASS_REFERENCE)
        .getCallerClass();

Module callerModule = caller.getModule();
String moduleName = callerModule.getName();
~~~

The factory can then map `moduleName` or caller info to a defined filter. This is a conceptual example; when implementing, determine the exact caller visible to the factory on the call stack, as intermediate framework classes may appear on the stack.

Do not use call stacks or class loaders as proof of user identity authentication. They are strictly technical context signals for choosing deserialization policies.

## 9. Factories and JVM-Wide Filters: Policies Must Combine Intentionally

A custom factory can combine three sources:

1. Static JVM-wide filter: process-wide rules.
2. Context filter: allow-list and limits for the current component.
3. Stream-specific filter: extra conditions requested by the stream's caller.

Diagram:

~~~text
                  Static JVM-wide filter
                            |
                            v
Context filter ----> Filter factory <---- Stream-specific filter
                            |
                            v
                 Composite ObjectInputFilter
                            |
                            v
                     ObjectInputStream
                            |
                            v
                   readObject / readUnshared
~~~

When combining:

- `REJECTED` from any filter must be preserved to block data.
- If a strict allow-list is needed, any disallowed class must receive `REJECTED`.
- `UNDECIDED` should not be mistaken for explicit permission.
- Do not let a per-stream filter accidentally discard the JVM-wide policy.

### 9.1. Default Factory vs. Custom Factory

| Behavior | Default Factory | Custom Factory |
| --- | --- | --- |
| Stream creation | Attaches static JVM-wide filter if present | Can select filter by context and combine global filter |
| Setting stream filter | Requested filter replaces initial filter per default behavior | Can combine requested filter with current filter |
| Policy by thread/module/caller | Does not automatically pick separate filters by such contexts | Implemented by the application |
| Controlling merge behavior | Follows built-in compatibility behavior | Decided by the factory |

Only a static JVM-wide filter is needed for simple applications with one shared policy. Use a custom factory when you genuinely have multiple deserialization contexts needing different filters or need to ensure stream filters do not override the baseline filter.

## 10. Configuring Stream-Specific Filters

After creating `ObjectInputStream`, a per-stream filter can be set:

~~~java
try (ObjectInputStream input =
        new ObjectInputStream(source)) {

    input.setObjectInputFilter(streamFilter);
    Object value = input.readObject();
}
~~~

In Java 17, `setObjectInputFilter`:

- Can be called only once per stream.
- Must be called before reading objects via `readObject()` or `readUnshared()`.
- Goes through the JVM-wide filter factory to select the final filter.
- Must not replace a non-null filter with a `null` result filter.

If the factory needs to combine the stream filter with the initial filter, do so inside `apply(current, requested)`. Do not call `setObjectInputFilter` multiple times trying to update policy after reading data.

## 11. Configuring the Factory via Properties

If you want to install the factory before the application starts running, use:

~~~bash
java -Djdk.serialFilterFactory=com.example.security.ContextFilterFactory \
     -Djdk.serialFilter="maxdepth=20;maxrefs=1000;maxbytes=2000000" \
     -jar application.jar
~~~

The two properties serve different roles:

| Property | Function |
| --- | --- |
| `jdk.serialFilter` | Configures the static JVM-wide filter |
| `jdk.serialFilterFactory` | Specifies the JVM-wide factory implementation class |

System properties take precedence over Security properties of the same name. If the factory is configured via property during `ObjectInputFilter.Config` initialization, the application cannot replace it with `setSerialFilterFactory`.

Do not call `System.setProperty("jdk.serialFilterFactory", "...")` after the application has initialized `ObjectInputFilter.Config` and expect the factory to change. Configure the property on the command line or in the Security file before the JVM launches the application.

## 12. Inspecting and Observing Active Filters

You can retrieve the JVM-wide factory and filter:

~~~java
import java.io.ObjectInputFilter;

ObjectInputFilter globalFilter =
        ObjectInputFilter.Config.getSerialFilter();

var factory =
        ObjectInputFilter.Config.getSerialFilterFactory();

System.out.println("Global filter: " + globalFilter);
System.out.println("Factory: " + factory);
~~~

`getSerialFilter()` returns `null` if no static filter has been configured. `getSerialFilterFactory()` returns the active factory; if no custom factory is set, it returns the built-in factory.

After creating a stream, you can inspect the filter selected by the factory:

~~~java
ObjectInputFilter active = input.getObjectInputFilter();
System.out.println("Stream filter: " + active);
~~~

This is useful for verifying configuration in runtime environments. Do not log sensitive object data merely to diagnose filters.

### 12.1. Logging Filter Actions

The JDK supports logging for serialization filters to observe decisions. Enabling logging helps detect:

- Which classes are checked.
- Which classes are rejected.
- Which depth, reference, or byte limit is exceeded.
- Whether a component is sending object types outside the contract.

Enable logging as needed for investigation and manage log volume. Do not log full sensitive data by default or leave overly verbose logging enabled long-term in production.

## 13. Common Mistakes When Implementing Filter Factories

| Error | Cause | How to Fix |
| --- | --- | --- |
| `setSerialFilterFactory` throws `IllegalStateException` | `ObjectInputStream` already created or factory already configured | Register factory early in bootstrap and register only once |
| Stream filter loses JVM-wide filter | Default factory replaces initial filter with stream filter | Use a custom factory to combine both policies if needed |
| Classes outside allow-list are still read | Filter returns `UNDECIDED` for unmatched classes | Use `!*`, explicit rejection filter, or appropriate `rejectUndecidedClass` |
| One filter allows a class that another filter has not decided on | `merge` returns `ALLOWED` if one allows and the other is undecided | Design each filter with clear semantics; strict allow-lists must reject unlisted classes |
| Factory returns `null` when `current` is already non-null | Accidentally drops existing filter | Always preserve current filter or return a non-null composite |
| Subsequent requests inherit previous filter | `ThreadLocal` not cleared/restored | Restore in `finally` |
| Async tasks use the wrong context | `ThreadLocal` does not propagate across threads | Pass context explicitly and set on the thread creating the stream |
| Individual tests pass but test suite fails | Factory is JVM-wide configuration, set only once | Share one factory or run config tests in separate JVMs |
| Filter has class limits yet still reads oversized objects | Graph depth, references, bytes, or arrays not limited | Set resource limits alongside allow-list |
| Thinking factories protect all parsers | Factories apply only to Java Serialization `ObjectInputStream` | Use separate checks for JSON, XML, YAML, or other formats |

## 14. Limitations and Security Principles

Filter factories are an important defense layer, yet do not turn Java Serialization into a safe format for arbitrary input.

- Avoid deserializing untrusted data when a simpler data format can be used.
- Build allow-lists per use case; do not allow entire packages or modules merely for convenience.
- Set `maxdepth`, `maxrefs`, `maxbytes`, and `maxarray` limits matching valid data characteristics.
- Account for all classes in the object graph, arrays, references, and supporting types.
- Do not treat filters as replacements for post-read data validation.
- Do not use `UNDECIDED` as implicit permission when building allow-lists.
- Keep the factory safe when multiple threads invoke it concurrently.
- Do not store request state in shared mutable instance fields; use context with clear scope and lifecycle.
- Expand deserialization permissions only with an explicit data contract and concrete justification.

Filters apply while reading objects; they do not replace connection authentication, sender authentication, integrity verification, or business rule validation of data.

## 15. When Should a Filter Factory Be Used?

| Scenario | Approach |
| --- | --- |
| Small application, all streams share one policy | A static JVM-wide filter may suffice |
| Each stream has its own allow-list, no need to combine global filter | Set stream-specific filters and understand default factory behavior |
| Multiple libraries or modules require different class sets | Use a custom filter factory to select by context |
| Need to keep JVM-wide filter while applying stream filters | Custom factory combining current filter and requested filter |
| Deserialization runs across multiple requests on thread pools | Can use ThreadLocal context; must restore in `finally` |
| Need policy selection by module or caller | Factory can inspect module/call stack, with clear context checks |

Do not introduce a custom factory just because Java 17 has this API. Use it when context-specific policies deliver clear value and can be thoroughly tested.

## 16. Self-Check Questions

**1. In which Java version were context-specific filter factories added?**  
Java 17, under JEP 415.

**2. What functional type does a filter factory have?**  
`BinaryOperator<ObjectInputFilter>`, receiving the current filter and requested filter and returning the final filter for the stream.

**3. At what times is the factory invoked?**  
When creating an `ObjectInputStream` and when calling `setObjectInputFilter` on the stream.

**4. When the `ObjectInputStream` constructor invokes the factory, what are the two arguments?**  
`current` is `null`; `requested` is the static JVM-wide filter.

**5. When calling `setObjectInputFilter`, what are the two arguments?**  
`current` is the filter currently attached to the stream; `requested` is the filter passed to the method.

**6. How does the default factory handle per-stream filters?**  
The requested stream filter replaces the initial filter under built-in behavior, rather than automatically merging with the JVM-wide filter.

**7. Why must a custom factory preserve the current filter if it is non-null?**  
To avoid accidentally disabling already-enabled filtering; the factory must return a non-null filter in this case.

**8. How does `ObjectInputFilter.merge` handle statuses?**  
`REJECTED` wins; if there is no rejection, `ALLOWED` from either filter wins; if both are `UNDECIDED`, the result is `UNDECIDED`.

**9. Why should an allow-list end with `!*`?**  
So classes not matching patterns are explicitly rejected instead of receiving `UNDECIDED`.

**10. How does `ThreadLocal` help a factory?**  
It stores the context filter of the thread creating the stream so the factory can select the appropriate policy.

**11. Why restore or remove ThreadLocal in `finally`?**  
So a thread pool does not carry a previous request's filter over to the next request.

**12. Can `setSerialFilterFactory` be called after creating an `ObjectInputStream`?**  
No. The factory must be configured before any `ObjectInputStream` is created and can be configured only once.

**13. Is `System.setProperty("jdk.serialFilterFactory", ...)` after the JVM starts sufficient?**  
No. Configure the property at startup/via Security property or call the API at the right time.

**14. Does a filter factory inspect each object directly?**  
No. The factory selects a filter; the filter attached to the stream inspects classes, arrays, and graph metrics during reading.

**15. Do filter factories protect all JSON or XML decoders?**  
No. They apply to Java Serialization via `ObjectInputStream`.

## Official References

- [JEP 415 — Context-Specific Deserialization Filters](https://openjdk.org/jeps/415): goals and context-based filter selection mechanism in Java 17.
- [Java SE 17 API — ObjectInputFilter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.html): `FilterInfo`, `Status`, `merge`, `rejectUndecidedClass`, and the factory model.
- [Java SE 17 API — ObjectInputFilter.Config](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputFilter.Config.html): `getSerialFilterFactory`, `setSerialFilterFactory`, `getSerialFilter`, `setSerialFilter`, and `createFilter`.
- [Java SE 17 API — ObjectInputStream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): when the factory is called and `setObjectInputFilter` rules.
- [Java SE 17 — Serialization Filtering Guide](https://docs.oracle.com/en/java/javase/17/core/serialization-filtering1.html): JVM-wide filters, per-stream filters, allow-lists, reject-lists, and filter factories.
