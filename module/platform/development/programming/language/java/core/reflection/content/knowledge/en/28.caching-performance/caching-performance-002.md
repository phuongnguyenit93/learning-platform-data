# Caching `Field`, `Method`, and `Constructor` in the Appropriate Context

## 1. Why and When Should You Cache Reflection Metadata?

In Java Reflection, a program can look up class metadata using APIs such as `Class.getDeclaredField(...)`, `getDeclaredMethod(...)`, and `getDeclaredConstructor(...)`, then use the resulting `Field`, `Method`, or `Constructor` objects to read/write fields, invoke methods, or instantiate objects.

If a framework repeatedly **looks up the exact same member** while processing thousands of objects, resolving metadata over and over can create unnecessary overhead. Caching lets you separate two tasks:

1. **Discovering the member once** within a specific context: class name, member name, parameter types, access rights.
2. **Using the discovered metadata** for appropriate receivers or arguments in subsequent operations.

For example, a serializer writing the `name` field for many `Person` objects can look up that `Field` once and then call `field.get(person)` on each instance. A dependency injector can cache the selected constructor per component type; a router can cache the method corresponding to a fixed endpoint.

However, **caching does not automatically make reflective calls as fast as direct Java calls**. It primarily avoids repeated metadata lookup costs. `Method.invoke(...)` still carries indirection overhead, type checking, boxing/unboxing, or corresponding exception handling. Reflection execution mechanisms and JIT behavior can also vary across JDK versions. Optimize based on profiling/benchmarks when performance is a real requirement.

### Three-Layer Model

```text
Access specification
  └── Class + member kind + name + signature + access policy
        ↓
Look up/check once
  └── Field / Method / Constructor
        ↓
Cache in the appropriate scope
  └── Selected metadata
        ↓
Use per object/invocation
  └── Field.get/set | Method.invoke | Constructor.newInstance
```

The most important thing is not “putting everything into a static Map,” but choosing **the right unit of reuse, cache key, and cache lifecycle**.

## 2. What to Store for `Field`, `Method`, and `Constructor`

All three metadata types belong to Reflection, yet they have different lookup and usage rules:

| Kind | Typical Lookup | Required Identifying Key | Usage After Caching |
| --- | --- | --- | --- |
| `Field` | `getDeclaredField("name")` / `getField("name")` | Declaring/lookup class context, field name, declared/public lookup policy | `field.get(receiver)`, `field.set(receiver, value)` |
| `Method` | `getDeclaredMethod("save", String.class)` / `getMethod(...)` | Class/lookup context, **name and ordered parameter type list**, lookup policy | `method.invoke(receiver, args...)` |
| `Constructor` | `getDeclaredConstructor(String.class)` / `getConstructor(...)` | Target class and **parameter type list**, lookup policy | `constructor.newInstance(args...)` |

- **The receiver instance is not part of the metadata key** if the same `Field`/`Method` can be used across many instances of a compatible type. Do not cache per business object just to avoid looking up the same field.
- **`Field`** is looked up by name. The field's type can be checked via `field.getType()` when needed, but the name together with the lookup policy/class forms the identifying basis in the APIs above.
- **`Method`** can be overloaded. For instance, `parse(String)` and `parse(int)` are two distinct methods; caching by `"parse"` alone is wrong. When using `getDeclaredMethod` or `getMethod`, the parameter list determines the overload. These Java Reflection lookup APIs do not accept a return type as a parameter; if a system requires checking the return type, also compare `method.getReturnType()` according to your system's contract.
- **`Constructor`** has no distinct name to pass to the lookup API. The key requires the class and parameter types; `getDeclaredConstructor()` does not mean “pick any constructor.”
- `getDeclaredXxx` looks up members **declared directly** on the queried class, including non-public ones, without automatically walking the entire superclass chain for every member kind. Public `getXxx` finds public members according to inheritance rules. These two lookup strategies must not share a cache key when their semantics differ.

You must also distinguish **caching descriptor objects** from **caching read data values**. Caching a `Field` may be valid; caching `field.get(person)` holds a value from one point in time, which may become stale if the field changes.

## 3. Designing Safe Cache Keys

If a cache serves a fixed class with a fixed list of members, you can create a metadata bundle attached to that class. If a cache serves multiple classes, overloads, and lookup strategies, a complete descriptive key is required.

A dynamic method key can be defined like this:

```java
record MethodKey(
        Class<?> owner,
        String name,
        java.util.List<Class<?>> parameterTypes,
        boolean declaredOnly) {}
```

This snippet only illustrates key declaration, not a standalone program. When constructing the key, use an **immutable copy of the parameter types**, for example:

```java
MethodKey key = new MethodKey(
        Person.class,
        "greet",
        java.util.List.of(String.class),
        true
);
```

Points to consider when implementing a real cache:

1. **`Class<?>` is determined by identity, including its classloader**. Two classes with the same fully qualified name loaded by two different classloaders are two distinct `Class` objects; using `getName()` as the entire key can mix up metadata.
2. **Overloads must include the full signature**. For a parameter list supplied by callers, copy it into an immutable list before putting it into the key; do not keep a mutable array as the source of hash/equality.
3. **Member lookup scope** must be fixed: declared-only, public/inherited, or a custom traversal algorithm over the class hierarchy. The same name and signature with different lookup policies can yield different results.
4. **Permissions and caller context** cannot be inferred from the class name alone. If a framework produces metadata on which `setAccessible(true)` was called or creates handles with a privileged lookup, do not expose those objects through a global cache readable by less-trusted code.
5. **Constructor selection policy** must be stable: if a framework selects by annotation, visibility, or configuration, those factors are part of the cache contract. Changing selection rules must invalidate the relevant entries.

Incorrect example:

```java
// Wrong: the two overloads save(String) and save(int) are collapsed into the same key.
java.util.Map<String, java.lang.reflect.Method> methodsByName;
```

Better structural example when each class has its own cache:

```java
record Signature(String name, java.util.List<Class<?>> params) {}

java.util.concurrent.ConcurrentMap<Signature, java.lang.reflect.Method> methods;
```

The two declarations above are design fragments, without variable initialization or exception handling. The owning class can serve as the outer key; when caching per class, the inner key only needs to describe methods **within** that exact class/context.

## 4. Choosing Cache Scope Based on System Lifecycle

There are several valid scopes. Choose based on class stability, access permissions, and lifetime:

| Scope | When Appropriate | Notes |
| --- | --- | --- |
| Local variable in a processing batch | Repeatedly used only within one request/batch | Easy to control, does not retain classes/objects beyond the batch |
| A service or component | Service works with a few fixed DTO/domain types | Cache lives with the service lifecycle, easy to invalidate |
| Per `Class<?>` with `ClassValue<T>` | Library processing many classes that wants data tied to the class and its lifecycle | Better suited than a strong static map in environments with changing classloaders |
| Shared cache by full key | Many dynamic entries where work genuinely reuses metadata | Needs control over permissions, concurrency, size, and classloaders |

### Risk of a Static Map Retaining Classloaders

An application-level cache like:

```java
static final java.util.Map<Class<?>, Object> CACHE = new java.util.concurrent.ConcurrentHashMap<>();
```

holds **strong references** to `Class<?>` and values. If the cache outlives a plugin, deployment, or classloader containing the class, it can prevent those classes/classloaders from being garbage collected. This is a real issue in application servers with hot deploy, plugin systems, IDEs, and frameworks that generate classes.

Switching the key to `WeakHashMap<Class<?>, Field>` **does not automatically solve every leak**: the `Field`/`Method` value can hold a reference back to its declaring class, creating a strong reference path from the map to the key itself via the value. Using `ClassValue` or a cache managed by component/classloader lifecycle is usually clearer. If a long-lived map is still used, ensure proper lifecycle cleanup, appropriate entry bounds, and retained-reference checks.

### `ClassValue<T>`

`ClassValue<T>` provides a value mapping **per `Class<?>`**, useful when you want to keep metadata belonging to a class without building a strong static map keyed by class. When `ClassValue.get(type)` does not yet have a value for that class, `computeValue(type)` is called to compute it.

```java
ClassValue<SomeMetadata> cache = new ClassValue<>() {
    @Override
    protected SomeMetadata computeValue(Class<?> type) {
        // Discover and build metadata for this specific type.
        return buildMetadata(type);
    }
};
```

This is **contractual Java pseudocode**: `SomeMetadata` and `buildMetadata` must be defined in the application; a complete example is in section 6.

`ClassValue` supports concurrent access, but **`computeValue` may be called multiple times for the same class under contention**; only one matching value is published to successful `get` calls. Therefore, the compute function should be pure or have safe side effects, and must not trigger one-time non-repeatable actions. `ClassValue.remove(type)` removes the value for a class, but when other threads may be computing or reading concurrently, invalidation procedures must be designed carefully.

## 5. Access Permissions: Caching Metadata Is Not a License to Bypass Private/Module Rules

Each `Field`, `Method`, and `Constructor` is a reflective descriptor. Being able to look up a member **does not mean** every caller is allowed to operate on that member.

- For public members in public classes/valid exported packages, you can usually use `getField`, `getMethod`, and `getConstructor` without relaxing access checks.
- For private/package-private members, reflective operations may be blocked by access control. `setAccessible(true)` only succeeds when Java language/module rules permit opening access; in named modules, `opens` and module relationships can determine the outcome.
- If access cannot be opened, `setAccessible(true)` may throw `InaccessibleObjectException`, an unchecked exception. Depending on requirements, you can use `trySetAccessible()` to receive `false` when it cannot be enabled and respond appropriately.
- **The accessible flag on an `AccessibleObject` is mutable state**. If one component enables access and then shares the same `Method`/`Field` with untrusted code, that can become a security issue. Metadata caches should stay within the trusted service that uses them.
- Reflection does not remove module encapsulation guarantees, nor does it make ordinary `final` fields arbitrarily updatable in every circumstance.

**Recommended workflow:** cache once you have clearly identified the target member and required permissions; centralize access logic in the responsible component. Do not blindly call `setAccessible(true)` on every field of every class, as this easily violates module policies and widens the access surface.

## 6. Standalone Java 17+ Example: Caching All Three Member Kinds with `ClassValue`

The example below defines a `Person` class with a private constructor, field, and method. The cache holds all three pieces of metadata, and each `CACHE.get(Person.class)` call returns the member set for `Person`. Enabling access succeeds in this example because `Person` is a nested class in the same **nest** as the accessing class, so Java permits this context to access private members; do not assume the same when switching to a class in another module.

Save the file as **`ReflectionCacheDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionCacheDemo {
    private static class Person {
        private String name;

        private Person(String name) {
            this.name = name;
        }

        private String greet(String greeting) {
            return greeting + " " + name;
        }
    }

    private record Accessors(
            Constructor<?> constructor,
            Field field,
            Method method) {
    }

    private static final ClassValue<Accessors> CACHE = new ClassValue<>() {
        @Override
        protected Accessors computeValue(Class<?> type) {
            if (type != Person.class) {
                throw new IllegalArgumentException("Class not supported");
            }
            try {
                Constructor<?> constructor =
                        type.getDeclaredConstructor(String.class);
                Field field = type.getDeclaredField("name");
                Method method = type.getDeclaredMethod("greet", String.class);

                constructor.setAccessible(true);
                field.setAccessible(true);
                method.setAccessible(true);

                return new Accessors(constructor, field, method);
            } catch (ReflectiveOperationException ex) {
                throw new IllegalStateException("Cannot resolve members", ex);
            }
        }
    };

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Accessors a = CACHE.get(Person.class);
        Person person = (Person) a.constructor().newInstance("Lan");

        System.out.println(a.field().get(person));
        System.out.println(a.method().invoke(person, "Hello,"));

        a.field().set(person, "Minh");
        System.out.println(a.method().invoke(person, "Hi,"));

        System.out.println(a == CACHE.get(Person.class));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ReflectionCacheDemo.java
java ReflectionCacheDemo
```

Output:

```text
Lan
Hello, Lan
Hi, Minh
true
```

Explanation:

1. On the first `CACHE.get(Person.class)`, `Accessors` must be created via `computeValue`: looking up constructor `Person(String)`, field `name`, and method `greet(String)`.
2. The metadata bundle is used to create a `Person("Lan")` object, read the field, and invoke the method. There is no need to re-lookup on every `get`/`invoke`.
3. After changing the field on the instance to `"Minh"`, calling the cached method sees the instance's **current value**; metadata caching does not freeze business data.
4. In this sequential run, the second `CACHE.get(Person.class)` returns the same `Accessors` reference, so comparing with `==` prints `true`.

Because `setAccessible(true)` may be invalid in other contexts, this example does **not** encourage granting private access to arbitrary classes. For public members, prefer normal public lookup/access. In real implementations, catching `ReflectiveOperationException` inside `computeValue` does not catch `InaccessibleObjectException` (unchecked) if module configuration forbids access; configuration errors should be reported clearly rather than hidden.

## 7. Caching Multiple Members of the Same Class

In a serializer or framework, each class may have dozens of fields and methods. In that case, a `ClassValue` can hold a **separate metadata table per class**:

```text
ClassValue<PerClassCache>
   |
   +-- Person.class → PerClassCache
   |       +-- Field "name"
   |       +-- Method ("greet", [String])
   |       +-- Constructor ([String])
   |
   +-- Order.class → PerClassCache
           +-- Field "status"
           +-- Method ("update", [int])
           +-- Constructor ([long])
```

Design a `PerClassCache` containing multiple `ConcurrentHashMap` instances, each using an appropriate key type. This approach:

- Avoids holding `Class<?>` directly in a global static map.
- Centralizes member lookup and access policy within each class.
- Enables lazy lookup by name/signature instead of discovering all members upfront when not yet needed.
- Makes it easy to attach cache hit/miss metrics if optimization is genuinely needed.

### `ConcurrentHashMap` and Checked Exceptions

`computeIfAbsent` is convenient, but its mapping function cannot be declared to throw a checked `NoSuchMethodException`. A condensed example illustrates wrapping the error:

```java
Method result = methods.computeIfAbsent(key, k -> {
    try {
        return owner.getDeclaredMethod(
                k.name(),
                k.parameterTypes().toArray(Class<?>[]::new)
        );
    } catch (NoSuchMethodException ex) {
        throw new IllegalArgumentException("Method not found: " + k, ex);
    }
});
```

This is an **illustrative snippet inside a `PerClassCache` implementation**, not a standalone runnable Java file. It assumes `methods: ConcurrentHashMap<Signature,Method>`, `key: Signature`, `owner: Class<?>`, and `Signature` providing `name()`/`parameterTypes()`. A real system must decide upfront how to handle failures: `computeIfAbsent` does not cache `null` results or exceptions; queries that always fail can keep costing time if called repeatedly.

Under high concurrency, the mapping function can cause lock contention. Do not put I/O, network queries, recursive calls back into the same map, or heavy side effects inside compute. Build immutable keys and cache valid members; when metadata expires according to lifecycle, discard the entire related cache.

## 8. Cases Requiring Caution

### a) Overloaded Methods and Inherited Methods

For `UserService.save(User)` and `UserService.save(String)`, the key `(name="save")` is insufficient. When calling `getDeclaredMethod` on a subclass, inherited members are not necessarily present in the declared list. Fix your lookup algorithm and signature; if switching to `getMethod` or manually walking superclasses, use keys/configuration that accurately distinguish the behavior.

### b) Proxies and Multiple Classloaders

Frameworks that generate proxy classes may produce multiple `Class<?>` instances even when the classes have similar structure. A `Method` looked up for class A does not automatically fit every proxy or a class with the same name loaded by another loader. With `Method.invoke`, the actual receiver must be compatible with that method's **declaring class**. Caching across classloaders using only a string like `"com.example.User"` is unsafe.

### c) Concurrent Access and Shared Metadata Objects

`Field`, `Method`, and `Constructor` can be reused when multiple threads invoke through Reflection concurrently; that does not mean **the business object being accessed is automatically thread-safe**. For example, calling `field.set(...)` on the same field of an object does not provide desired atomicity or happens-before guarantees. If your problem requires memory-ordering control or CAS, look at `VarHandle` or appropriate synchronization primitives, not just caching `Field`.

### d) Stale Caches or Runtime Model Changes

Replacing a class with a version loaded from a new classloader creates a **different `Class` object**. Metadata must be looked up from the new class. With plugin reloads, hot redeploys, instrumentation, or changing mapping schemas, clearly define when caches are dropped per loader/component/version. `ClassValue.remove(type)` only removes the entry attached to that `type`; it does not clear external referencing structures.

### e) Memory Cost and Small Gains

If a member is only called once, creating maps, keys, synchronization, and cache entries can cost more than direct lookup. If an application scans many classes but only uses a small subset of members, eagerly caching everything can waste memory. For hot loops, measure **metadata lookup cost** and **member invocation cost** separately, instead of running one combined benchmark and attributing every gain to caching.

### f) Sensitive Data and Trust Boundaries

A shared cache exposing metadata whose private access has been opened can accidentally grant access to other components. Design clear ownership: only authorized code should retrieve or receive privileged members; do not expose an accessible-enabled member map as a multi-tenant service without permission checks.

## 9. Measuring Performance Correctly

If the goal is to reduce latency, test two paths:

- **Without cache:** call `getDeclaredMethod(...)` then `invoke(...)` on every iteration.
- **With cache:** look up once or retrieve `Method` from the cache, then call `invoke(...)`.

However, separate the costs: key creation, cache hit/miss, lookup, invocation, autoboxing, result handling, and the latency of the target method itself. If the method performs several milliseconds of I/O, metadata optimization may be negligible. If the call site is very hot, consider direct interfaces or `MethodHandle` after measuring and when the design allows.

Use JMH or a suitable measurement tool with warmup, multiple iterations, JVM forks, and Dead Code Elimination and GC controls. Avoid drawing conclusions from a single `System.nanoTime()` loop. In particular, **a cache hit does not take zero time**: concurrent map lookups, key construction, and memory footprint all have costs.

Useful metrics can include: number of cached classes/entries, metadata build count, cache hit/miss rates, access/lookup failure counts, per-request-type processing time, total heap retained by the cache, and number of classloaders retained after redeploy. Choose measurements tied to real performance questions rather than adding a cache just because the code “looks faster.”

## 10. Decision Process and Practice

Before caching a Reflection member, answer these questions in order:

1. **Is it repeated often enough?** If looked up only once, caching is not needed yet.
2. **Does the key uniquely identify the member?** For methods/constructors, include parameters in exact order; distinguish declared vs. public lookup.
3. **What are the scope and lifecycle?** Request, component, class, or classloader; are there plugins/redeploys?
4. **Are the cache consumers' permissions uniform?** Avoid putting access-widened members into a cache shared across different trust zones.
5. **How are contention and invalidation handled?** Use appropriate concurrency structures; handle failed lookups clearly without sensitive side effects inside compute.
6. **Have you measured the real bottleneck?** If the cost lies in invocation or business logic, caching lookups may not be enough.

### Self-Check Exercises

- Create two overloaded methods `convert(String)` and `convert(int)`. Explain why a map keyed by the string `"convert"` is wrong and design a key that distinguishes both.
- In the `ReflectionCacheDemo` example, use the same `Accessors` on two different `Person` objects. What metadata does the cache store, and do the `name` values of the two objects affect each other?
- Move `Person` into a different named module that does not `opens` its package to the caller. Explain why `setAccessible(true)` can fail even when member lookup succeeds.
- A plugin is repeatedly loaded and unloaded. Why might a static `ConcurrentHashMap<Class<?>,Method>` retain the old classloader, and how does `ClassValue` solve managing per-class metadata?
- If an application handles 100 requests and only 2 requests use a rare method, is eagerly caching all methods of the class necessarily effective? What would you measure?

**Expected outcome:** know when caching `Field`/`Method`/`Constructor` pays off, build cache keys matching signatures and lookup strategies, maintain proper access-permission scope, avoid classloader leaks, and verify performance with real measurement data.