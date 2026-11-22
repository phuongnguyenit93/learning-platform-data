# Reflection Cost, Caching, and Class Loader Management in Java Annotations

In Java, annotations with `RUNTIME` retention are metadata that can be read via reflection. Frameworks often rely on annotations to build routes, validate objects, map entities, handle authorization, or register handlers. The performance issue does not lie in the `@Something` symbol written in source code by itself, but usually in **repeated scanning and interpretation of annotations**, the number of reflected elements, caching strategies, and the lifecycle of classes loaded by multiple class loaders.

A sound design needs to address three questions simultaneously:

1. **What work is reflection doing, and is it on the hot path?**
2. **Can metadata be normalized into immutable structures and stored per class or in a registry?**
3. **Does the cache strongly retain the plugin's Class/Method/ClassLoader after the plugin has been closed?**

This lesson uses Java 17+ to create a `ClassValue`-based cache, observe one-time scanning in a sequential scenario, remove and recompute the cache, and then demonstrate that two classes **with the same name but different class loaders** are two different types. Do not infer benchmarks or class unloading capability from a functional test.

## 1. Sources of Annotation Reflection Cost

Consider:

~~~java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Route {
    String value();
}

class Service {
    @Route("/check")
    public void check() {}
}
~~~

An application can retrieve the path with:

~~~java
var method = Service.class.getDeclaredMethod("check");
var route = method.getDeclaredAnnotation(Route.class);
String path = route.value();
~~~

This is an **illustrative snippet placed inside a method that handles NoSuchMethodException**; the full example is in section 7.

Different steps have different costs:

| Task | Common API | Considerations |
| --- | --- | --- |
| Resolve a method | `Class.getMethod`, `getDeclaredMethod` | Name/signature lookup; results depend on declared/inherited semantics |
| Scan all methods | `getMethods`, `getDeclaredMethods` | Member count, result array, bridge/synthetic methods |
| Read an annotation | `getAnnotation`, `getDeclaredAnnotation` | Retention, location, annotation present or absent |
| Retrieve multiple annotations of the same type | `getAnnotationsByType` | Repeatable container and returned elements |
| Read type annotations | `getAnnotatedType` and `AnnotatedType` | Traversing type uses, generic arguments, nested types |
| Interpret into configuration | Parse route/validation/policy | Framework business-logic cost, duplicate/conflict checks |
| Invoke a method reflectively | `Method.invoke` | A different operation from **reading annotations**, involves access checks |

It is **incorrect** to claim that every `getAnnotation` call re-reads the `.class` file from disk; the JVM/JDK may cache and optimize reflection internals. However, an application can still waste CPU and allocations if it repeatedly calls `getDeclaredMethods()`, iterates through hundreds of methods, and rebuilds the same route table on every HTTP request.

Conversely, if a framework scans metadata only once at bootstrap, a second-tier cache may offer almost no benefit. Measure where CPU, allocations, and GC are actually being spent.

### Annotations Do Not Execute Automatically on Every Method Call

`@Route("/check")` is metadata. It **does not automatically inject dispatch code** into the `check()` method or cause the JVM to call `getAnnotation` every time `check()` runs. Only the framework or application **actively reading and processing** the annotation generates reflection work.

Similarly, compiler annotation processing and runtime reflection occur at two different points in time. An annotation with `SOURCE` retention can be used by a processor at compile time, but is no longer available for runtime reflection to read.

## 2. Choosing What Data to Cache

For `Service.check()`, there are at least three strategies.

**Caching the Method:**

~~~java
Map<MethodKey, java.lang.reflect.Method> handlers;
~~~

This can avoid repeated method lookups, but `Method` objects still carry references to the declaring `Class`, parameter types, and potentially the class loader. If the cache is static in a long-lived location, retaining a plugin's `Method` can extend the class loader's lifetime.

**Caching the annotation object:**

~~~java
Map<MethodKey, Route> routes;
~~~

This can avoid reading the annotation again, but the annotation object and its annotation type also belong to the runtime class-loading context. Moreover, a method/annotation proxy is not always the lightest business metadata.

**Caching normalized metadata:**

~~~java
Map<MethodKey, String> routePaths;
~~~

When the framework only needs a URL path, an immutable string is sufficient. This approach does not require retaining the annotation proxy; however, if the consumer needs to invoke the method, the handler registry still has to manage the appropriate method/instance.

In the snippets above, `MethodKey` is an **illustrative application-defined** type, such as a record holding a name and parameter types. They are not standalone programs yet.

### Do Not Use Method Name as the Key When Overloads Exist

`run()` and `run(String)` are two different methods and may carry different annotations. If the key is only `"run"`, one entry can overwrite the other. For a real framework, you need to key by the resolved signature or a domain identifier with clear meaning.

### Also Cache Results When Annotations Are Absent

If the `ping()` method is not annotated with `@Route`, you still want to avoid re-scanning it on every request. One approach is an immutable map containing only real entries; `!routes.containsKey("ping")` indicates that the method has no route in the current scan. For general data, you can use `Optional` or a dedicated sentinel.

`Map.copyOf(...)` **does not accept null keys or values**. Do not store `null` to represent a negative result in this kind of map.

## 3. Why Static Caches Can Retain Class Loaders

Risky example:

~~~java
static final java.util.concurrent.ConcurrentHashMap<
        Class<?>, java.util.List<java.lang.reflect.Method>> CACHE =
        new java.util.concurrent.ConcurrentHashMap<>();
~~~

This is an **illustrative anti-pattern snippet for a long-lived global cache in a plugin-reloading system**, not an initialization statement that is always wrong. `ConcurrentHashMap` holds keys and values via **strong references**. If the key contains the plugin's `Class<?>` and the value contains the plugin's `Method`, a reference chain exists:

~~~text
Static cache belonging to a long-lived class loader
    |
    +--> strong key: plugin's Class<?>
    |       |
    |       +--> defining ClassLoader
    |
    +--> strong value: plugin's Method
            |
            +--> declaring Class and related types
~~~

When a plugin is redeployed, having no remaining business objects is not enough to guarantee that the old loader will be unloaded if the static cache still retains it. The result can be old class loaders accumulating and metaspace growing.

**Note:** Class unloading depends on reachability and GC; calling `System.gc()` or `URLClassLoader.close()` does not obligate the JVM to unload immediately. What needs to be investigated is the entire reference graph and lifetime of the application.

### WeakHashMap Does Not Automatically Fix All Reference Cycles

A common mistaken fix:

~~~java
java.util.WeakHashMap<Class<?>, java.util.List<java.lang.reflect.Method>> cache;
~~~

`WeakHashMap` holds **weak keys**, but values are still strongly referenced. If the value contains a `Method` that has a reference path to its declaring class, we can end up with:

~~~text
Map --> value (Method) --> declaring Class (which is also the key)
~~~

Because the key remains strongly reachable through the value, merely changing a strong map key to a weak key **does not guarantee** that the loader will be released. `WeakHashMap` is also not inherently thread-safe; concurrency remains a separate concern. Do not infer behavior from the data structure's name while ignoring the object reference graph.

Other reference roots besides caches—such as thread-locals, callbacks, event listeners, executor tasks, MBeans, or static registries—can also retain old plugins.

## 4. ClassValue: Associating Metadata with Each Class

`java.lang.ClassValue<T>` (available since Java 7) lets you lazily associate computed metadata with a `Class<?>` without needing a global static map with strong Class keys.

~~~java
private static final ClassValue<Metadata> META = new ClassValue<>() {
    @Override
    protected Metadata computeValue(Class<?> type) {
        return scan(type);
    }
};
~~~

This is an **illustrative snippet**, assuming `Metadata` and `scan(type)` have already been defined. Section 7 uses a runnable program with `ClassValue<Map<String,String>>`.

Key mechanisms:

- `get(type)` returns the metadata attached to the class if present; otherwise it invokes `computeValue(type)`.
- Associating the value with the class is synchronized per the API contract, but when multiple threads query for the first time concurrently, **`computeValue` may run more than once**. Do not write code assuming a side effect always happens exactly once.
- `remove(type)` removes the association so that the next `get(type)` call can recompute it.
- `ClassValue` is generally well-suited for caching per-class metadata in environments where class loaders are unloaded, because the framework does not need a strong static map listing every `Class<?>` ever encountered.
- The value should be immutable or have a clear thread-safety contract. `Map.copyOf(...)` helps create an immutable map (though it does not automatically freeze nested objects inside).

**There is no guarantee that `ClassValue` eliminates all loader leaks**: if the cached value is copied to another static map, a thread-local retains a handler, or a plugin registers a callback without unregistering it, the loader can still be strongly retained.

### When Should You Use ClassValue?

- You need to scan annotations per `Class<?>` for a mapper/validator/route generator.
- Metadata from the same class is reused many times.
- The application has multiple class loaders or plugin-created classes and wants to avoid a static cache pinning class keys.
- The metadata is tied primarily to the **class definition** and does not change per request.

If annotations are processed **once at bootstrap** and then managed by a registry within the same application lifecycle, adding `ClassValue` may not be necessary. A simpler design is sometimes better.

## 5. Cache Semantics and Invalidation

### Cache Keys Must Match the Question

A `Class<?>` is a reasonable key for static metadata specific to a single class. However, if the result also depends on tenant, locale, runtime policy, environment configuration, or plugin version, **a class-only key may not be sufficient**.

Separating into two tiers is one solution:

1. **Per-class structural metadata:** list of methods, annotations, element values, and fixed signatures — cached with `ClassValue` or a scoped registry.
2. **Runtime policy/config:** route enablement, user permissions, tenant-specific flags — cached by version/tenant/config or resolved on the request path according to a separate rule.

Do not store a security policy result computed for user A in a cache keyed solely by `Class<?>` and then reuse it for user B.

### Differences Between Declared, Inherited, and Repeatable Annotations

`getDeclaredAnnotation` does not search for class annotations on superclasses. `Class.getAnnotation` can look up class annotations marked with `@Inherited` according to its rules. `getAnnotationsByType` unpacks repeatable containers. Annotations on a method **are not automatically inherited by an overriding method** via `@Inherited`.

A cache storing `getDeclaredMethods` results differs semantically from a cache storing `getMethods` results. When caching metadata, state the scanning rules clearly and ensure the cache-building code uses the appropriate API.

### When Metadata Needs to Be Refreshed

- The framework has dynamic policy/config combined with annotation metadata.
- Classes are redefined/retransformed via instrumentation (depending on scope, rules, and purpose).
- The registry is rebuilt after plugin deploy/reload.
- The application wants to proactively change the interpreted metadata structure.

`ClassValue.remove(type)` is an explicit invalidation tool. In the example, it demonstrates re-running the scan. Do not call remove on every request, or you will negate the benefit of reuse.

### Access Checks and Module Boundaries

Reading metadata via reflection is **different** from invoking a private method. You can obtain a `Method` object and still lack permission to `invoke` it if Java access checks/JPMS disallow it. Caching a `Method` cannot bypass `setAccessible` rules or module encapsulation.

You should not automatically open every module with `--add-opens` just because of access errors. A framework should document which packages require `opens` and minimize required privileges. `MethodHandles.Lookup` can be an option in certain designs, though it still must obey access control.

## 6. Class Loader Identity: Same Name Does Not Mean Same Class

Java runtime type identity involves both the **binary name and the defining class loader**. Two `Class<?>` objects with the same `getName()` defined by two different loaders can be **two distinct types**.

Example:

~~~java
Class<?> a = PluginType.class;
Class<?> b = Class.forName("PluginType", false, isolatedLoader);
System.out.println(a == b);
~~~

This is an **illustrative snippet**; `isolatedLoader` is assumed to be appropriately created. It can print `false` even though both classes are named `PluginType`. Therefore, a global cache like:

~~~java
Map<String, Metadata> byClassName;
~~~

can suffer **collisions between plugins** if it only uses `class.getName()`. If the cache is completely scoped under a single loader/version, a name key may suffice within that scope, whereas a shared cache across multiple loaders must account for proper identity.

Conversely, merely changing a `String` key to a `Class<?>` key in a static `ConcurrentHashMap` increases the risk of retaining old loaders. Both **identity and lifetime** must be addressed.

### URLClassLoader Is Not a Tool to Prove Unloading

In the program below, we create a separate `URLClassLoader` and call `Class.forName(..., false, isolated)`. This is a test of **type identity**, not a test that the class loader has been garbage collected. `URLClassLoader.close()` closes the resources managed by the loader, but does not guarantee that all objects/classes are unloaded immediately.

## 7. Complete Java 17 Example: ClassValue and Two Class Loaders

Save everything into the file **ReflectionCacheDemo.java**:

~~~java
import java.lang.annotation.*;
import java.lang.reflect.Method;
import java.net.URL;
import java.net.URLClassLoader;
import java.util.Map;
import java.util.TreeMap;
import java.util.concurrent.atomic.AtomicInteger;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Route { String value(); }

class Service {
    @Route("/check")
    public void check() {}
    public void ping() {}
}

class PluginType {}

public class ReflectionCacheDemo {
    private static final AtomicInteger SCANS = new AtomicInteger();
    private static final ClassValue<Map<String, String>> ROUTES =
            new ClassValue<>() {
                @Override protected Map<String, String> computeValue(Class<?> type) {
                    SCANS.incrementAndGet();
                    Map<String, String> found = new TreeMap<>();
                    for (Method method : type.getDeclaredMethods()) {
                        Route route = method.getDeclaredAnnotation(Route.class);
                        if (route != null) found.put(method.getName(), route.value());
                    }
                    return Map.copyOf(found);
                }
            };

    public static void main(String[] args) throws Exception {
        Map<String, String> first = ROUTES.get(Service.class);
        Map<String, String> second = ROUTES.get(Service.class);
        System.out.println("routes=" + new TreeMap<>(first));
        System.out.println("sameCache=" + (first == second));
        System.out.println("scans=" + SCANS.get());
        System.out.println("pingPresent=" + first.containsKey("ping"));
        System.out.println("annotationPresent=" +
                Service.class.getDeclaredMethod("check").isAnnotationPresent(Route.class));

        ROUTES.remove(Service.class);
        System.out.println("afterRemove=" + new TreeMap<>(ROUTES.get(Service.class)));
        System.out.println("scansAfterRemove=" + SCANS.get());

        URL location = PluginType.class.getProtectionDomain()
                .getCodeSource().getLocation();
        try (URLClassLoader isolated =
                     new URLClassLoader(new URL[]{location}, null)) {
            Class<?> other = Class.forName("PluginType", false, isolated);
            System.out.println("sameName=" +
                    (other.getName().equals(PluginType.class.getName())));
            System.out.println("sameClass=" + (other == PluginType.class));
            System.out.println("differentLoader=" +
                    (other.getClassLoader() != PluginType.class.getClassLoader()));
        }
    }
}
~~~

In this file, `Service`, `PluginType`, and `Route` are package-private; only `ReflectionCacheDemo` is public. No extra source file is needed for `PluginType` because javac compiles all top-level declarations in the file.

### Compile/Run Commands

From the directory containing the file, using JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 -d out ReflectionCacheDemo.java
java -cp out ReflectionCacheDemo
~~~

**Actual stdout (compiled and run with `--release 17`):**

~~~text
routes={check=/check}
sameCache=true
scans=1
pingPresent=false
annotationPresent=true
afterRemove={check=/check}
scansAfterRemove=2
sameName=true
sameClass=false
differentLoader=true
~~~

### Explaining the First Six Lines: Caching and Scanning

- `routes={check=/check}`: the scan finds `@Route("/check")` and creates an immutable mapping.
- `sameCache=true`: two calls to `ROUTES.get(Service.class)` in the sequential demo, without invalidation, return the **same value object**.
- `scans=1`: `computeValue` runs once in the **sequential** demo; this is not an exactly-once guarantee under a race.
- `pingPresent=false`: the unannotated method has no route; lookups after scanning do not require reflection.
- `annotationPresent=true`: `@Route` is correctly read on `Method check()`.
- `afterRemove={check=/check}` and `scansAfterRemove=2`: after `remove`, the metadata for Service is recreated.

### Explaining the Last Three Lines: Class Loader Identity

- `sameName=true`: both `Class<?>` objects are named `PluginType`.
- `sameClass=false`: they are two different runtime types.
- `differentLoader=true`: one is loaded by the application loader, and the other by a `URLClassLoader` with a `null` parent.
- `PluginType.class.getProtectionDomain().getCodeSource().getLocation()` points to the `out` output in this setup; the new loader can find `PluginType.class` from there.
- `try-with-resources` closes the `URLClassLoader` upon exiting the block; this is **resource cleanup**, not proof that the loader has unloaded.

The example uses the method name as the key only because `Service` has two methods with different names. In real-world code with overloads, you must change the key. For complex plugin JARs, you also need to handle delegation, packages, module layers, resources, and security policies.

## 8. Measure Performance Instead of Guessing

**The functional correctness test in section 7 is not a performance benchmark**. A proper measurement needs to:

1. **Define the workload:** number of classes, number of methods, number of annotations, and number of repeated queries per request.
2. **Establish a clear baseline:** measure the cost of resolving methods, getting annotations, and transforming metadata, isolated from I/O/DB/network.
3. **Warm up the JVM:** JIT and reflection internals can differ significantly between the first execution and repeated executions.
4. **Avoid dead-code elimination:** actually consume benchmark results; JMH with `Blackhole` can be used.
5. **Measure allocations/GC:** a cache might reduce CPU usage while increasing footprint, startup time, or memory retention.
6. **Measure p95/p99 and concurrency:** especially when multiple threads query the cache simultaneously for the first time.
7. **Test class-loader reloads:** if plugin reloading is supported, also measure the number of remaining reachable loaders/metaspace and latency across multiple cycles.
8. **Do not extrapolate a fixed multiplier:** results depend on the JDK, CPU, annotation structure, and framework design.

JDK introspection APIs may already perform internal caching, so the right measurement compares **the entire business metadata path before and after application caching**, not necessarily two isolated API calls inside a JIT-optimized loop.

### Can You Over-Cache?

Yes. If the app has few classes and scans them only once at startup, adding `ClassValue`, a registry, and invalidation may merely increase complexity. If the cache retains large lists of `Method`/`Field` objects while business logic only uses a few String values, memory usage may be higher than necessary.

Choose small, purpose-built metadata rather than storing entire sets of Java reflection objects by default.

## 9. Debugging Class Loader Leaks in Applications Using Annotations

Suggestive signs include an increasing number of old class loaders or growing metaspace across redeployments. These are only **symptoms** and do not by themselves prove that a static reflection cache is the cause.

Procedure:

1. Identify which loader created the plugin's classes and which loader owns the static cache.
2. Traverse the reference graph: caches, thread locals, tasks, listeners, MBeans, callbacks, framework registries.
3. Look for strong references to the plugin's `Class<?>`, `Method`, instances, or `ClassLoader`.
4. Check whether `WeakHashMap` values refer back to the keys.
5. Consider `ClassValue` or a per-plugin scoped registry; clear lifecycle data upon unloading.
6. Unregister callbacks, stop threads/executors, and close resources created by the plugin.
7. Verify using heap dumps/JFR/class-loader statistics across multiple reloads; do not treat a single `System.gc()` call as proof.

**It is necessary to distinguish** among leaks in heap objects, class metadata/metaspace, and a cache holding valid data because the plugin is still active.

## 10. Annotation Registry Design Practices

| Scenario | Suggested Design |
| --- | --- |
| Scanned only once at bootstrap | Build an immutable registry; multiple cache layers are unnecessary |
| Repeatedly querying metadata for the same class | `ClassValue<Metadata>` or a per-class cache with a clear lifecycle |
| Multiple class loaders | Rely on `Class<?>` identity or per-loader scoping, not just class name |
| Plugin hot reload | Tie cache lifetime to the class/plugin; avoid static strong refs |
| Method overloading | Key by signature, do not use name alone |
| Repeatable annotations | Use `getAnnotationsByType` according to policy and cache the normalized result |
| Need to read inherited methods | Explicitly choose `getMethods` and the superclass/interface annotation policy |
| Tenant/config-dependent metadata | Separate structural metadata from runtime policy |
| Need to invoke private methods | Comply with Java access checks and JPMS `opens` |
| Bottleneck unclear | Measure first, optimize later |

A good registry design requires not only a cache structure but also a **contract**:

- **Build:** which annotated elements are scanned? Classes, declared methods, inherited methods, or fields?
- **Key:** `Class<?>`, method signature, class loader scope, tenant/config version?
- **Value:** immutable route info, constraint descriptors, Method/MethodHandle?
- **Concurrency:** compute may race; is an exact-once side effect required?
- **Invalidation:** who calls `remove` or clear, and when?
- **Lifecycle:** who owns the registry, and when is it disposed/unregistered?
- **Observability:** count scans, cache hits/misses, allocations, retained loaders?

## 11. Common Mistakes

**Mistake 1 — Assuming annotations automatically make runtime reflection consume CPU on every method call.** No. Only a consumer that actually reads/processes metadata creates that work.

**Mistake 2 — Assuming caching every Method will always be faster.** You need to measure; a large cache can increase memory usage and retain old loaders.

**Mistake 3 — Using the class name as a shared key across multiple class loaders.** Two classes with the same name but different defining loaders have different identities; the cache risks collisions.

**Mistake 4 — Using a static ConcurrentHashMap<Class<?>, ...> while forgetting about lifecycle.** Strong keys can retain the entire class loader/plugin.

**Mistake 5 — Replacing it with WeakHashMap and assuming the leak is gone.** Strong values can reference back to the weak keys.

**Mistake 6 — Thinking ClassValue guarantees computeValue runs only once.** Under concurrent initialization, multiple computations can occur; `remove` also triggers recomputation.

**Mistake 7 — Having no invalidation for business data that can change.** Class metadata and dynamic configuration require different caching strategies.

**Mistake 8 — Confusing direct annotations with inherited/repeatable annotations.** `getDeclaredAnnotation`, `getAnnotation`, and `getAnnotationsByType` have different semantics. Cache the right API according to the consumer contract.

**Mistake 9 — Treating caching as a way to bypass JPMS access control.** No. `Method.invoke` on a non-public member is still subject to access checks.

**Mistake 10 — Seeing ClassLoader.close() succeed and concluding unloading has occurred.** No. Closing resources is different from GC class unloading; profiling/reference graph inspection is needed.

## 12. Self-Check Questions

**1. When can caching annotations help?** When the application scans/interprets the same metadata repeatedly on a hot path and the results are stable enough to reuse.

**2. Why can caching a `Method` in a static singleton retain a loader?** Because Method references its declaring class; a path of strong references from the static cache can lead to the defining loader.

**3. Is WeakHashMap<Class<?>, List<Method>> guaranteed not to leak?** No; the value strongly holds the Method and can retain the very Class used as the key.

**4. How does ClassValue differ from a static Map?** It associates a lazy value with each Class object without requiring a strong static map storing all Class keys; it fits per-class metadata well.

**5. Is `computeValue` guaranteed to run exactly once when multiple threads race?** No. Computation may execute concurrently, even though only one value is installed in the cache.

**6. Why is `sameName=true` while `sameClass=false`?** Two classes have the same binary name but are defined by two different class loaders.

**7. Is a class-only cache valid for metadata that varies by tenant?** Not sufficient; you need to separate dynamic configuration or add a tenant/config-version dimension.

**8. How can a cache support overloading?** Include the method signature or an unambiguous method identifier in the key, not just the name.

**9. Does calling `System.gc()` prove that a class loader has unloaded?** No.

**10. What does the `ReflectionCacheDemo` example prove and what does it not prove?** It demonstrates concrete annotation-reading/caching/invalidation/type-identity outcomes, **and does not prove a speedup by a fixed ratio or that a class loader has been garbage-collected**.

## 13. Official Documentation

- Java SE 21 — **ClassValue**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassValue.html
- Java SE 21 — **Class and reflection APIs**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21 — **AnnotatedElement and repeatable annotations**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedElement.html
- Java SE 21 — **Method and AccessibleObject**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html and https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AccessibleObject.html
- Java SE 21 — **ClassLoader** and **URLClassLoader**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html and https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 21 — **WeakHashMap**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/WeakHashMap.html
- JVM Specification `5.3 — **Creation of Classes and Interfaces**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html#jvms-5.3

**Remember:** proper annotation caching means **caching the right result of a lookup policy** for an **appropriate lifecycle**. First understand what reflection is scanning, what data can be normalized to immutable form, which class identity serves as the key, and which references could retain old class loaders. `ClassValue` is useful for per-class metadata; running benchmarks and inspecting the class-loader lifecycle are what tell you whether an optimization design actually achieves its goal.
