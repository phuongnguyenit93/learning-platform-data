# Cache Keys Must Consider `Class` and ClassLoader Identity in Java Reflection

## 1. The Problem: “Same Class Name” Does Not Guarantee Same Type

In applications using **Reflection**, frameworks, plugins, multi-classloader setups, or hot-reload mechanisms, we often cache expensive lookup results such as `Class<?>`, `Method`, `Constructor<?>`, `Field`, annotation metadata, or data converters. A subtle bug occurs when the cache key is only a string name:

~~~java
// Easy-to-break approach with multiple classloaders
Map<String, Method> methodCache = new HashMap<>();
methodCache.put("com.example.Plugin#execute", aMethod);
~~~

The name `com.example.Plugin` is only a **binary name**. It is insufficient to identify a Java class at runtime: **two different classloaders can define two different classes carrying the same binary name**. If you take a `Method` from the first class and invoke it on an instance of the second class, Java Reflection can throw `IllegalArgumentException` because the receiver is not an instance of the matching declaring class.

This lesson explains how to choose the right key, demonstrates the bug with runnable Java 17+ code, recommends `ClassValue` for retaining metadata per `Class<?>`, and analyzes how caches keep classloaders in memory.

**Expected outcome:** distinguish class name, initiating loader, and defining loader; build caches with accurate identity; handle overloads/thread safety; avoid retaining old classes/plugins after unloading.

## 2. Class Identity in the JVM: Binary Name **Plus** Defining Loader

The JVM identifies a runtime class/interface by **its binary name and the classloader that defined it**. Therefore, you can have:

~~~text
Loader-A --define--> demo.Plugin   (Class object A)
Loader-B --define--> demo.Plugin   (Class object B)
~~~

Even though `Class.getName()` returns the same `"demo.Plugin"`:

- `classA == classB` is `false`; they represent **two different runtime types**.
- `classA.getClassLoader() != classB.getClassLoader()` if they were defined by two different loaders.
- An object created by `classA` is not automatically an instance of `classB`: `classB.isInstance(objectFromA)` returns `false`.
- A `Method`/`Constructor` or `Field` looked up on class A cannot arbitrarily be applied to class B, even if the bytecode looks identical.
- Static fields and class initialization also belong to each runtime class; loading the same name in another loader does not make the two classes share static state.

**Distinguish defining and initiating loaders:** when calling `requestedLoader.loadClass("demo.Plugin")`, that loader may **delegate to its parent**. The resulting `Class<?>` is then defined by the **parent**, so `type.getClassLoader()` may differ from `requestedLoader`. Keying by the resolved `Class<?>` is the simplest and most accurate approach when caching metadata that depends on the *actual type*.

For the bootstrap loader, calls like `String.class.getClassLoader()` may return `null`; `null` here is a valid case, not an error.

## 3. Choosing Cache Keys Based on What Is Cached

There is no single key structure that fits every problem. First determine whether you want to cache **the result of resolving a name** or **metadata of an already-resolved class**:

| Cached Data | Suggested Key | Why? |
| --- | --- | --- |
| Metadata/annotations of a class | `Class<?>` or `ClassValue<T>` | `Class` itself carries runtime identity including loader |
| List of `Method`s of a class | `Class<?>` then secondary key for signature | Prevents mixing methods across two classes with the same name |
| A specific `Method` | `Class<?>` + name + parameter types + declared/public policy | Overloads do not share the same metadata |
| A `Constructor` | `Class<?>` + parameter types | Constructors overload by parameters |
| A `Field` | `Class<?>` + field name + lookup scope | Fields are bound to a specific declaring class |
| Resolving `"demo.Plugin"` to `Class<?>` | **Name + initiating loader / resolution context** | The same name can resolve differently by loader |
| Lookups across JPMS layers/modules | Include `Module`/`ModuleLayer` when resolution depends on them | A loader alone does not always fully describe module lookup policy |

For **metadata where `Class<?>` is already obtained**, keying by `Class<?>` is **sufficient to distinguish loaders**. You do not need to add `type.getClassLoader()` to the key, because two distinct `Class` objects are already unequal. A `(Class<?>, ClassLoader)` key sometimes works, but it is usually redundant and can accidentally hold an extra strong reference.

If an API accepts a **string class name** and selects a loader at lookup time, use a key containing both the name **and the resolution request context itself**. Use the **loader object**, not just `loader.getClass().getName()`, `toString()`, or `hashCode()`: two loader instances of the same class can still define different classes. If the system has layers, plugin versions, lookup variants, or custom rules, reflect every factor that changes the outcome in the key.

**The equivalence relation must be sound:** two requests should share a cached result only if the program truly guarantees they resolve to the same runtime object and the same access policy.

## 4. Runnable Example: Same Name, Two Different Classloaders

The example below reads the bytecode of the nested class `Widget` and creates two custom `ClassLoader` instances to **redefine the exact same class name**. The custom loader bypasses parent delegation only for `Widget`; all other classes still delegate normally.

Create the file `ClassCacheKeyDemo.java`:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

public class ClassCacheKeyDemo {
    public static class Widget {
        public Widget() {}
        public String ping() { return "pong"; }
    }

    static class ShadowLoader extends ClassLoader {
        private final byte[] bytes;

        ShadowLoader(byte[] bytes) {
            super(ClassCacheKeyDemo.class.getClassLoader());
            this.bytes = bytes;
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!name.equals(Widget.class.getName())) {
                return super.loadClass(name, resolve);
            }
            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);
                if (found == null) {
                    found = defineClass(name, bytes, 0, bytes.length);
                }
                if (resolve) resolveClass(found);
                return found;
            }
        }
    }

    static byte[] widgetBytes() throws IOException {
        try (InputStream in = ClassCacheKeyDemo.class.getResourceAsStream(
                "ClassCacheKeyDemo$Widget.class")) {
            if (in == null) throw new IOException("Class bytes not found");
            return in.readAllBytes();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes = widgetBytes();
        Class<?> appClass = Widget.class;
        Class<?> pluginClass =
                new ShadowLoader(bytes).loadClass(Widget.class.getName());
        Class<?> otherPluginClass =
                new ShadowLoader(bytes).loadClass(Widget.class.getName());

        System.out.println("Same name: "
                + appClass.getName().equals(pluginClass.getName()));
        System.out.println("Same Class: " + (appClass == pluginClass));
        System.out.println("Different plugin classes: "
                + (pluginClass != otherPluginClass));
        System.out.println("Different defining loaders: "
                + (pluginClass.getClassLoader()
                        != otherPluginClass.getClassLoader()));

        Map<String, Method> wrongCache = new HashMap<>();
        wrongCache.put(appClass.getName() + "#ping",
                appClass.getMethod("ping"));
        Object pluginObject = pluginClass.getConstructor().newInstance();
        try {
            wrongCache.get(pluginClass.getName() + "#ping")
                    .invoke(pluginObject);
        } catch (IllegalArgumentException expected) {
            System.out.println("Wrong cached Method: IllegalArgumentException");
        }

        Map<Class<?>, Method> correctCache = new HashMap<>();
        correctCache.put(appClass, appClass.getMethod("ping"));
        correctCache.put(pluginClass, pluginClass.getMethod("ping"));
        System.out.println("Correct reflection call: "
                + correctCache.get(pluginClass).invoke(pluginObject));
    }
}
~~~

Compile and run in the file's directory using **Java 17+**:

~~~bash
javac --release 17 ClassCacheKeyDemo.java
java ClassCacheKeyDemo
~~~

Actual output verified on JDK 21 with `--release 17`:

~~~text
Same name: true
Same Class: false
Different plugin classes: true
Different defining loaders: true
Wrong cached Method: IllegalArgumentException
Correct reflection call: pong
~~~

**Analysis:**

1. Both custom loaders define the bytecode of `ClassCacheKeyDemo$Widget`, producing `Class<?>` objects distinct from the `Widget` class defined by the application loader.
2. The broken cache uses `getName() + "#ping"`, so it returns the application class's `Method`, even though the target instance belongs to the class defined by the plugin loader.
3. `Method.invoke(pluginObject)` throws `IllegalArgumentException` because the receiver does not belong to the method's declaring type.
4. The cache using `Map<Class<?>, Method>` distinguishes the two runtime classes; invoking the plugin class's method on the plugin instance returns the correct result.

This is a **deliberate demo** using child-first loading for one class to reproduce the difference. Do not turn an entire loader into child-first in production without understanding dependency, package, resource, and security boundaries.

## 5. Method Caches Must Also Include Signature and Reflection Rules

Even when the outer key is `Class<?>`, a class can overload methods:

~~~java
String substring(int beginIndex)
String substring(int beginIndex, int endIndex)
~~~

Therefore, you should not cache solely by the name `"substring"`. When using `Class.getMethod(name, parameterTypes)` (which finds only public methods, including inherited ones), the secondary key should contain the name and the **list of parameter `Class<?>` types in exact order**. With `getDeclaredMethod(...)`, make the policy for directly declared methods explicit; do not mix caches of `getMethod` and `getDeclaredMethod`.

Details that are easy to miss:

- `int.class` differs from `Integer.class`; `String[].class` differs from `String.class`.
- Overloads `call(String)` and `call(Object)` differ; both parameter count and order matter.
- Varargs methods still have an array parameter type in Reflection, e.g., `String...` becomes `String[].class`.
- `Method.getDeclaringClass()` can be a **superclass or interface** rather than the owner class used for the lookup. Cache by the requested class and identify the method/declaring class according to your needs.
- Generics after **type erasure** do not make `List<String>` and `List<Integer>` two different runtime parameter types.
- Bytecode may contain bridge or synthetic methods. If working with raw metadata or JVM descriptors, also check `getReturnType()`, `isBridge()`, and `isSynthetic()` where appropriate. The standard `getMethod` API does not select methods by return type.
- Member access rights can depend on **caller lookup, module, and `exports`/`opens`**. Obtaining or caching a `Method` does not mean every caller has permission to invoke it or access private members.

For an application with only one parameterless public `status()` API, the secondary key can be very simple. For a general-purpose Reflection library, represent the full signature, member kind, lookup mode, and access policy.

## 6. `ClassValue<T>`: Caching Values Attached Directly to Each `Class<?>`

The JDK provides `java.lang.ClassValue<T>` (Java 7+) to **attach computed data per runtime class**. Because `Class<?>` already distinguishes loaders, `ClassValue` also distinguishes two same-named classes defined by different loaders.

~~~java
private static final ClassValue<Metadata> CACHE = new ClassValue<>() {
    @Override
    protected Metadata computeValue(Class<?> type) {
        return inspect(type);
    }
};
~~~

This is an **illustrative fragment**; `Metadata` and `inspect` are application-defined type/function names. `CACHE.get(type)` computes the value when absent and stores it under `type`; `CACHE.remove(type)` discards the value for that class so it can be recomputed next time.

Main benefit: avoids manually managing a global `Map<Class<?>, ...>` just to map classes to metadata; `ClassValue` is purpose-built for this association and supports concurrent access. However:

- `computeValue` **may run multiple times when threads contend**, though only one result is installed and returned. Do not place unsafe side effects or strictly once-only transactions inside `computeValue`.
- `remove(type)` only removes the association for **that exact `Class<?>`** from **that exact `ClassValue` instance**. It does not “clear all caches” across the application.
- `ClassValue` does not automatically prevent all memory leaks: if other code still holds a `Class<?>`, loader, instance, or handle from an old plugin, the class can still stay alive.
- Only add `ClassValue` when metadata is truly reused many times; caching adds complexity and memory overhead if lookups are cheap or infrequent.

### Complete Java 17 Example: `ClassValue` and Overloads

Create the file `ClassValueDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

public class ClassValueDemo {
    record Signature(String name, List<Class<?>> parameters) {
        Signature(String name, Class<?>... parameters) {
            this(name, List.of(parameters));
        }
    }

    private static final ClassValue<ConcurrentHashMap<Signature, Method>> CACHE =
            new ClassValue<>() {
                @Override
                protected ConcurrentHashMap<Signature, Method> computeValue(
                        Class<?> type) {
                    return new ConcurrentHashMap<>();
                }
            };

    static Method publicMethod(Class<?> owner, String name,
                               Class<?>... parameters)
            throws NoSuchMethodException {
        Signature key = new Signature(name, parameters);
        var methods = CACHE.get(owner);
        Method cached = methods.get(key);
        if (cached != null) return cached;

        Method discovered = owner.getMethod(name, parameters);
        Method prior = methods.putIfAbsent(key, discovered);
        return prior == null ? discovered : prior;
    }

    public static void main(String[] args) throws Exception {
        Method one = publicMethod(String.class, "substring", int.class);
        Method again = publicMethod(String.class, "substring", int.class);
        Method two = publicMethod(
                String.class, "substring", int.class, int.class);

        System.out.println("Same cached method: " + (one == again));
        System.out.println("Overloads distinct: " + (one != two));
        System.out.println("First call: " + one.invoke("abcd", 2));
        System.out.println("Second call: " + two.invoke("abcd", 1, 3));
    }
}
~~~

Run:

~~~bash
javac --release 17 ClassValueDemo.java
java ClassValueDemo
~~~

Verified output:

~~~text
Same cached method: true
Overloads distinct: true
First call: cd
Second call: bc
~~~

Because `Signature` is a record, it compares by value; `List.of(parameters)` creates an immutable list containing parameters in exact order rather than directly holding a `Class<?>...` array that the caller might mutate. `ConcurrentHashMap` lets threads safely access the same class metadata at the map-operation level.

The example intentionally caches only **public methods** via `getMethod`. If a method is absent, it throws `NoSuchMethodException` and does not store “not found.” For systems needing to cache *negative lookups*, use a dedicated result type (sentinel/`Optional` or status object) and define an invalidation policy carefully. `ConcurrentHashMap` does not allow `null` keys or values.

Regarding concurrency, the example uses `get` → Reflection lookup → `putIfAbsent`. Under contention, two threads may look up the method concurrently once, but the map retains a single final entry; this is fine because method lookup has no business side effects.

## 7. When You Must Cache by Name Before Obtaining `Class<?>`

A resolver taking:

~~~java
Class<?> resolve(String binaryName, ClassLoader requestedLoader)
        throws ClassNotFoundException {
    return Class.forName(binaryName, false, requestedLoader);
}
~~~

is a **complete method fragment** ready to place in a class. `Class.forName(..., false, requestedLoader)` requests lookup without **eagerly initializing the class**. The loader argument is the loader used to request resolution, not guaranteed to be the resulting class's defining loader.

If you cache the result of `resolve`, the key must include at least **`binaryName` and `requestedLoader` by identity**, or an equivalent namespace/version context. Distinguish carefully:

- `Map<String, Class<?>>` is **wrong** if the same name can be resolved by multiple loaders.
- `Map<Key(String, ClassLoader), Class<?>>` can distinguish requests properly, provided `ClassLoader` is compared by **actual instance identity**. A `record` uses the loader's `equals`; if custom loaders override `equals`, choose an identity wrapper or suitable structure.
- Once `Class<?> resolved` is obtained, cache metadata by **`resolved`** rather than recomputing name + loader keys.
- Do not permanently cache `ClassNotFoundException` for a loader that can discover new classes after adding JARs/plugins; negative lookups need a corresponding refresh policy.

**Avoid using** `requestedLoader.getClass().getName()` as a loader ID; it only tells you the **loader type**, not which instance it is. Also avoid using only `System.identityHashCode(loader)` as a unique identifier in a long-lived cache: hash codes can collide and a hash alone does not hold an exact reference to the loader.

On platforms with multiple `ModuleLayer`s, a resolver may depend on module/layer in addition to loader. Define the key using **the exact inputs of the resolution operation**, rather than assuming every `binaryName` maps to one global class.

## 8. Cache Lifecycle and the Risk of Retaining Classloaders

A metadata key using `Class<?>` may be **correct for identity**, yet a global cache like `static ConcurrentHashMap<Class<?>, Method>` still outlives the plugin. The map strongly holds both the `Class` key and the `Method` pointing back to its declaring class, preventing the old loader from being reclaimed after plugin removal. Switching to `WeakHashMap<Class<?>, Method>` does not automatically break the retention cycle from value back to key.

For per-class computed metadata, `ClassValue` is usually appropriate; for plugins with an explicit lifecycle, a cache scoped inside the plugin or evicted on unload is also a sound choice. Other retention sources such as callbacks, threads, `ThreadLocal`s, or handles must also be cleaned up by lifecycle; **GC and class unloading have no guaranteed deadline**. The lesson “Caches Holding Class Can Retain the Entire ClassLoader” analyzes reference graphs, weak keys, heap dumps, and concrete GC-root checks.

## 9. Reloading, Dynamic Proxies, Hidden Classes, and Redefinition

**Plugin reload:** a new version with the same binary name typically appears under a **new loader**, i.e., a new `Class<?>`. Class-keyed caches automatically separate old/new versions; name-keyed caches can return stale metadata.

**Dynamic proxies:** generated proxy classes depend on loader, interface set, and module context. Using display names or generated proxy class names as durable identifiers is risky. When caching reflection over proxies, use `proxy.getClass()` or a key built from normalized proxy configuration matching the exact loader/interface identity.

**Hidden classes:** classes can be created via `MethodHandles.Lookup.defineHiddenClass`; they are not necessarily identifiable or lookable via `Class.forName(name)` in the usual way. If you need to cache metadata, key directly by the granted `Class<?>`.

**Instrumentation/redefinition:** APIs such as `Instrumentation.redefineClasses` can replace the bytecode of the **same runtime class** within JVM limits. In that case, **the identity of `Class<?>` does not change**, yet metadata/behavior may change per tool action. A cache keyed by `Class<?>` will not automatically know the bytecode version changed: instrumentation/framework mechanisms must provide appropriate **invalidation or generation/versioning** if cached data depends on mutable contents.

**Classloader delegation:** two different loaders may both delegate loading to a parent and receive **the exact same `Class<?>`**. In that case, a metadata cache keyed by the resulting `Class<?>` can safely share entries by identity. Do not assume two types are distinct solely because two `loadClass` calls started from two different loaders.

## 10. Operational Rules for Safe Reflection Caching

### 10.1. Separate Metadata from Access Rights

A `Method` may exist yet be inaccessible from a specific module/caller. `setAccessible(true)` remains bound by `opens`; `MethodHandles.Lookup` carries the permissions of the caller or granted lookup. If caching **privileged handles** or caller-dependent data, keys and sharing boundaries must reflect permission boundaries—never expose privileged handles/lookups to untrusted callers.

### 10.2. Thread Safety Is Not Key Correctness

`ConcurrentHashMap` keeps map operations consistent across threads, **it does not turn `String className` into a safe class identifier**. Fix key design before discussing lock tuning or `computeIfAbsent`.

With `computeIfAbsent`, the mapping function can encounter checked exceptions that you must translate/wrap and handle explicitly; never cache an exception as a success. Consider transient failures, plugin changes, module permissions, and invalidation before introducing negative caching.

### 10.3. Do Not Optimize Without Measuring

Repeated Reflection lookups can be costly, but building a cache also has costs: key lookup, memory, loader retention, synchronization, and invalidation. Use a proper benchmark (such as JMH with warm-up) to decide what to cache. When a hot call path already has a stable, properly authorized `MethodHandle`/`VarHandle`, keeping that handle in a clearly scoped lifecycle is sometimes better than a global `Method` cache.

### 10.4. Review Checklist

- Is the cache storing **name-resolution results** or metadata of a **specific `Class<?>`**?
- If the key is a `String`, across how many loaders/plugins can that class be defined?
- If the key is `Class<?>`, is a global strong map accidentally retaining old loaders?
- Does a method key distinguish overloads, parameter types in order, static/instance, and `getMethod` vs. `getDeclaredMethod`?
- If access permissions vary by caller/module, could the cache accidentally share privileged handles?
- Upon reload/unload or redefinition, which entries must be evicted?
- Have you tested two loaders **loading the same binary name**, or only one default loader?

## 11. Common Errors

| Symptom | Typical Cause | Resolution |
| --- | --- | --- |
| `Method.invoke` throws `IllegalArgumentException` despite “matching class name” | `Method` belongs to a class defined by another loader | Compare `method.getDeclaringClass()` and `receiver.getClass()`, including loaders |
| `ClassCastException` between two classes with the same name | Two defining loaders produced two runtime types | Share common API/interfaces from a shared parent loader; do not cast by name |
| `NoSuchMethodException` after deploying a new version | Stale cache, changed signature, wrong overload | Look up against the new `Class<?>` and exact parameter types |
| `LinkageError` or loader constraint violation | Incompatible loading/linking across classloaders | Review delegation and dependencies between loaders |
| Plugin loader never unloads | Static cache holds `Class`, `Method`, handle, or instance | Use `ClassValue`/lifecycle-scoped caches and clear references |
| Name + loader-class cache still collides | Used **loader class**, not loader instance | Use the resolved class or loader object identity |
| Same class loaded via parent duplicates cache entries | Key used initiating loader when caching class metadata only | Key by the resulting `Class<?>` to merge shared identity |
| Cache unchanged after redefining the same `Class` | Missing version-based invalidation | Tie cache lifetime to generation/redefinition events |
| Thread-safe cache map returns the wrong method | Synchronization is right, identity is wrong | Redesign the key before tuning concurrency |

## 12. Self-Check

1. Two `Class<?>` objects have equal `getName()` values but different defining loaders. Can they share a `Method`? **No**; they are two separate runtime types.
2. Does a `Map<Class<?>, Metadata>` cache already distinguish loaders? **Yes**; `Class<?>` carries runtime identity including the defining loader.
3. If caching `Class.forName(name, false, requestedLoader)` before knowing the result, can you key by `name` alone? **No**, if multiple loaders/contexts can resolve differently.
4. Are `requestedLoader` and `resolvedClass.getClassLoader()` always the same? **No**, because of parent delegation.
5. Why does `WeakHashMap<Class<?>, Method>` not guarantee loader unloading? **The `Method` value can hold the declaring class**, forming a strong reference path from the map value to the key.
6. Is `ClassValue.computeValue` guaranteed to run only once under contention? **No**; multiple threads may compute concurrently, and one value is installed.
7. After redefining a class's bytecode while keeping the same `Class<?>`, is a `Class<?>`-keyed cache automatically invalidated? **No**; generation/invalidation is needed if cached metadata is affected.
8. For `getMethod("substring", int.class)` and `getMethod("substring", int.class, int.class)`, where must the cache keys differ? **The parameter type list**.

## 13. Official References

- [Java Virtual Machine Specification 17 — Creation and Loading, `5.3](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — ClassValue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html)
- [Java SE 17 — Class](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — WeakHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html)

**Takeaway:** For Reflection metadata, **key by `Class<?>` itself** (or use `ClassValue`) so that defining loaders are distinguished as well. Keep name + initiating loader/context only when caching **name resolution before a class is obtained**; once you have the class, do not revert to string-name keys. Consider plugin lifecycles and strong references so a semantically valid cache does not become a memory leak.