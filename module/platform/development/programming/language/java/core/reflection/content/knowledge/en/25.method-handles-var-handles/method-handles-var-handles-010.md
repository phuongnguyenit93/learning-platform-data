# When to Choose `Method`, `MethodHandle`, or `VarHandle` in Java Reflection

## 1. The Problem: One Java Member, Three Different Ways of Working

When a program already knows the type and method to call at compile time, the simplest approach is usually a **direct call** through a Java type or interface. However, frameworks, data mappers, expression evaluators, serialization libraries, or plugin systems sometimes know only the class name, method name, or field name at runtime. In those cases, Java provides different tools:

- `java.lang.reflect.Method`: an object **describing a method** for inspecting metadata (name, parameters, annotations, modifiers...) and optionally invoking via `invoke`.
- `java.lang.invoke.MethodHandle`: an **invocable reference** to a method, constructor, or other operation whose call signature is explicitly represented by `MethodType`. Suits cases where the target is already resolved and you need typed dynamic invocations, signature transformations, or reuse.
- `java.lang.invoke.VarHandle`: a typed reference to a **storage location** such as a field or array element, offering read/write modes and several **atomic/memory-synchronization** operations. Suits cases where the task is truly variable access, especially in concurrent code.

The three tools are not three directly interchangeable versions of one thing. If you need to *discover metadata*, `Method` is the natural starting point. If you need to *invoke a chosen behavior*, `MethodHandle` provides flexible invocation and composition. If you need to *read/write or atomically update a variable*, `VarHandle` expresses that problem directly.

> First rule: if application code already knows the exact API and can call it directly and safely, prefer an ordinary Java call. Reflection is only useful when the program must select or operate dynamically at runtime.

## 2. Quick Decision Table

| Key Question | `Method` | `MethodHandle` | `VarHandle` |
| --- | --- | --- | --- |
| What does this object describe? | **Method** metadata | An **invocable** target with a `MethodType` | A **variable location** and access modes |
| How is it obtained? | `Class.getMethod` / `getDeclaredMethod` | `MethodHandles.Lookup.findVirtual`, `findStatic`, `unreflect`... | `Lookup.findVarHandle`, `findStaticVarHandle`, `arrayElementVarHandle`... |
| Primary operation | `invoke(receiver, Object...)` | `invokeExact(...)` / `invoke(...)` | `get`, `set`, `getVolatile`, `compareAndSet`, `getAndAdd`... |
| Can it query annotations, name, and modifiers? | **Yes**, via the Reflection API | **No**, not like a `Method`; holds call-signature info | Not used to discover field annotations |
| Parameter / return types | Passes through `Object`, boxing/unboxing as needed | Explicit call types in `MethodType` and call site | Coordinate types and variable value type per access mode |
| Exception handling from target method | `Method.invoke` wraps target exceptions in `InvocationTargetException` | Target exception propagates directly along the execution flow | Errors depend on access mode, types, and operation |
| Useful for memory synchronization / CAS? | Not the purpose of `Method` | Can invoke existing synchronized code; does not provide field CAS itself | **Yes**, access modes support memory semantics and atomic updates |
| Typical scenario | Framework scanning annotations then calling methods infrequently | Reusable dynamic invoker, adapters for already-resolved methods | Counters, state, field/array access needing explicit concurrency rules |

**Do not choose merely by the slogan "the newer API is always faster."** Cost depends on the call pattern, reuse of lookup results, JVM optimizations, call frequency, and thread contention. If performance is an actual requirement, measure under the corresponding conditions.

## 3. `Method`: Needing Method Info and Simple Dynamic Invocation

### 3.1. What `Method` Does Well

`Class.getMethod(name, parameterTypes...)` looks up a matching `public` method (including inherited `public` methods per API rules). `Class.getDeclaredMethod(...)` looks up a method declared **directly** in the class, regardless of modifier, without searching superclasses. The result is a `Method`, which can be used to:

- Read `getName()`, `getParameterTypes()`, `getReturnType()`, `getModifiers()`, `getDeclaringClass()`.
- Inspect annotations with `getAnnotations()` or `getAnnotation(...)`, and inspect generic metadata when needed.
- Select the right method in a framework based on conventions or annotations.
- Invoke the method via `invoke(target, args...)` if access is permitted.

**Fragment** example, assuming a public `Service` class with `public String greet(String name)`:

~~~java
Method method = Service.class.getMethod("greet", String.class);
Object result = method.invoke(service, "Minh");
String message = (String) result;
~~~

Requires `import java.lang.reflect.Method;`, a `service` variable of a compatible type, and handling `ReflectiveOperationException` along with access-related exceptions. For instance methods, the first argument to `invoke` is the **receiver**; for static methods, `null` may be passed. Primitive results are **boxed** into their wrapper types; `void` methods return `null`.

### 3.2. Costs and Pitfalls to Understand

- Each `Method.invoke` receives arguments in an `Object[]` array (varargs); boxing/unboxing and type conversions may occur. The API validates receiver/arguments and can throw `IllegalArgumentException` on mismatch.
- If the target method throws an exception, `Method.invoke` throws `InvocationTargetException`; the **original exception** is in `getCause()`.
- `getDeclaredMethod` finding a private method **does not mean** you are permitted to invoke it. Java checks access permissions; `setAccessible(true)` can be denied by module boundaries. When possible, design public APIs or configure `opens` properly rather than trying to break access controls.
- Avoid calling `getMethod`/`getDeclaredMethod` repeatedly in a hot loop if the method is already known; you can retain the resolved `Method`.

**When to choose:** code needing metadata or invoking a handful of methods based on configuration/annotations, where frequency is not high and simplicity matters more than optimizing a dynamic dispatcher.

## 4. Checking Types and Permissions Before Choosing a Mechanism
Once the target is chosen, a `MethodHandle` is obtained via `MethodHandles.Lookup` and has signature `handle.type()`. With `findVirtual`, the type used for lookup describes the method without a receiver, whereas the resulting handle takes the receiver as its first argument; `invokeExact` requires matching both parameters **and return type** at the call site. `Method` allows discovering annotations; when repeated invocation is needed, metadata can be converted into a handle via `Lookup.unreflect(method)` after checking permissions.

`VarHandle` needs `varType()` along with `coordinateTypes()` (receiver for instance fields; no coordinates for static fields; array and index for array elements). `getAndAdd` returns the old value before adding; `compareAndSet` returns a boolean. Plain `get`/`set` operations do not synchronize between threads by themselves, and two separate calls do not compose into an atomic increment.

All three mechanisms perform access checks. For private members across named modules, `privateLookupIn` requires a suitably privileged source lookup and the target package opened to the right module, so choose public APIs whenever possible.

## 5. Standalone Java 17+ Example: One Program, Three Roles

Create `ChoosingMemberAccessDemo.java`:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class ChoosingMemberAccessDemo {
    public static class Counter {
        private int count;

        public int twice(int x) {
            return x * 2;
        }

        public void fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Throwable {
        Counter counter = new Counter();

        // Method: inspect metadata and invoke the reflected method.
        Method reflected = Counter.class.getMethod("twice", int.class);
        System.out.println("Method name=" + reflected.getName());
        int fromMethod = (Integer) reflected.invoke(counter, 3);
        System.out.println("Method result=" + fromMethod);

        // MethodHandle: invoke the resolved method with an exact signature.
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle twice = lookup.findVirtual(
                Counter.class,
                "twice",
                MethodType.methodType(int.class, int.class));
        int fromHandle = (int) twice.invokeExact(counter, 4);
        System.out.println("MethodHandle result=" + fromHandle);

        // VarHandle: access instance field and perform atomic updates.
        VarHandle count = lookup.findVarHandle(
                Counter.class, "count", int.class);
        System.out.println("VarHandle initial=" + (int) count.get(counter));
        count.set(counter, 10);
        boolean updated = count.compareAndSet(counter, 10, 15);
        int oldValue = (int) count.getAndAdd(counter, 5);
        int current = (int) count.getVolatile(counter);
        System.out.println("CAS success=" + updated);
        System.out.println("getAndAdd previous=" + oldValue);
        System.out.println("VarHandle current=" + current);

        // VarHandle can also access array elements.
        VarHandle elements = MethodHandles.arrayElementVarHandle(int[].class);
        int[] numbers = {1};
        int previousElement = (int) elements.getAndAdd(numbers, 0, 4);
        System.out.println("array previous=" + previousElement
                + ", current=" + numbers[0]);

        // Same target error, two mechanisms throw exceptions differently.
        Method failMethod = Counter.class.getMethod("fail");
        try {
            failMethod.invoke(counter);
        } catch (InvocationTargetException ex) {
            System.out.println("Method exception wrapper="
                    + ex.getClass().getSimpleName());
            System.out.println("Method cause="
                    + ex.getCause().getClass().getSimpleName());
        }

        MethodHandle failHandle = lookup.findVirtual(
                Counter.class, "fail", MethodType.methodType(void.class));
        try {
            failHandle.invokeExact(counter);
        } catch (IllegalStateException ex) {
            System.out.println("MethodHandle exception="
                    + ex.getClass().getSimpleName());
        }
    }
}
~~~

Because `Counter` and the class containing `main` are **nestmates**, `MethodHandles.lookup()` in the outer class can look up the `private count` field of the nested class. This example does not mean that an arbitrary class's `Lookup` has permission to access private fields elsewhere.

Compile and run commands:

~~~bash
javac ChoosingMemberAccessDemo.java
java ChoosingMemberAccessDemo
~~~

Output:

~~~text
Method name=twice
Method result=6
MethodHandle result=8
VarHandle initial=0
CAS success=true
getAndAdd previous=15
VarHandle current=20
array previous=1, current=5
Method exception wrapper=InvocationTargetException
Method cause=IllegalStateException
MethodHandle exception=IllegalStateException
~~~

Points to observe:

1. `Method` provides `getName()` metadata and performs `invoke`. The result returns as `Object`, so here it must be unboxed from wrapper `Integer` to `int`.
2. `MethodHandle` enforces the invocation type (`Counter`, `int`) → `int`. The result `8` comes from `twice(4)` and is unrelated to the `count` field.
3. `VarHandle` points to the `count` field itself. `compareAndSet` changes `10` to `15`; `getAndAdd` returns old value `15` and updates it to `20`.
4. `arrayElementVarHandle` obtains a VarHandle with coordinates (`int[]`, index `int`), enabling atomic operations on an array element.
5. `fail()` throws the same `IllegalStateException`, yet `Method.invoke` wraps the error in `InvocationTargetException` while the handle propagates the target's exception directly.

This is a single-threaded example to verify APIs and stdout. It is **not a benchmark**, nor does it prove correctness of a multi-threaded algorithm from a single run.

## 6. Access Permissions and Modules: Picking the Right API Is Not Enough

All three APIs are subject to Java's access model. The difference lies in **how access is discovered and where permissions are checked**:

- `Method` can find a private method via `getDeclaredMethod`. At `invoke` time, access rights are still checked; `trySetAccessible` returns `false` when access cannot be widened, while `setAccessible(true)` can throw `InaccessibleObjectException`.
- `MethodHandle` is typically obtained via `Lookup.findVirtual` / `findStatic`; access is evaluated against the `Lookup` object at lookup time. `publicLookup()` and `lookup()` are not equivalent.
- `VarHandle` is looked up via `Lookup.findVarHandle` / `findStaticVarHandle`; field access also follows `Lookup` and module boundaries.
- `MethodHandles.privateLookupIn(target, callerLookup)` can create a suitably privileged `Lookup` for a specific target when **the caller holds appropriate permissions and the target module opens the package**. Across another named module, `opens` conditions must be met; read/write access to private members of arbitrary modules is not granted by default.

Example using `privateLookupIn` when the target package is validly opened:

~~~java
MethodHandles.Lookup privateLookup = MethodHandles.privateLookupIn(
        Target.class, MethodHandles.lookup());
MethodHandle handle = privateLookup.findVirtual(
        Target.class, "hidden", MethodType.methodType(void.class));
~~~

*This fragment assumes `Target` exists and has an instance method `private void hidden()`. You must still pass a `Target` instance when invoking the handle, handle `IllegalAccessException` / `NoSuchMethodException` during lookup, and handle `Throwable` during invocation.*

A `VarHandle` referencing a `final` field may allow reading yet **not support write/update operations**. Obtaining the handle does not mean calling `set` or CAS will succeed: an unsupported access throws `UnsupportedOperationException`. With `Method`, field names are irrelevant: if you need field metadata, use `java.lang.reflect.Field`; if you need atomic operations on a field, look at `VarHandle`.

## 7. When Both `Method` and `MethodHandle` Are Involved

Many frameworks must **discover first, invoke later**, so combining the two APIs is natural:

~~~java
Method discovered = SomeApi.class.getMethod("process", String.class);
MethodHandle callable = MethodHandles.lookup().unreflect(discovered);
~~~

This fragment assumes `SomeApi` exists and the method is accessible from the current `Lookup`. `unreflect` converts metadata into a callable handle, but **does not unlock access by itself**. If annotations are needed, retain `discovered` for inspection. If repeated invocation is needed, retain `callable` to avoid repeated lookups.

An instance-method handle still expects a receiver unless **bound** to an object:

~~~java
MethodHandle bound = callable.bindTo(apiInstance);
~~~

`bindTo` fixes the first argument as the receiver (when the handle's type permits). Subsequent calls take only the remaining arguments. Clearly distinguish the handle's `MethodType` **before and after binding**, and do not mix `invokeExact` with call sites using the wrong return type.

### Do Not Mechanically Replace `VarHandle` with `MethodHandle`

`Lookup.findGetter` / `findSetter` can also create `MethodHandle`s to read/write fields when permitted. However, an ordinary getter handle does not provide `compareAndSet` or `getAcquire`, `setRelease`, and `getVolatile` modes. If the requirement involves memory ordering and atomic updates of a storage location, use `VarHandle` or an appropriate concurrency abstraction.

`VarHandle.toMethodHandle(AccessMode)` can also produce a `MethodHandle` for a specific access mode when integration into a dynamic invocation pipeline is needed. The **access semantics** still come from the `VarHandle`'s access mode, not because any `MethodHandle` inherently has that property.

## 8. Choosing by Project Scenario

| Scenario | First Choice | Reason |
| --- | --- | --- |
| Interface/method known in source code and called frequently | Direct Java call | Readable, compiler type-checked, easy to refactor |
| Scanning methods annotated with `@Route` / `@Test` / `@Handler` | `Method` | API for querying declaration metadata |
| Configuration specifies a method by name, called only a few times | `Method` | Simple; no need for an extra adapter layer |
| Framework selects a handler once and invokes it repeatedly across many requests | `MethodHandle` (optionally looked up via `Method` first) | Explicit call signature; supports adapters/combinators with JVM optimization potential |
| Dynamic invocation must adapt/bind/reorder parameters | `MethodHandle` | `asType`, `bindTo`, and combinators |
| Reading field annotations and serialization policies | `Field` for metadata discovery | `VarHandle` does not replace the metadata API |
| Updating an `int` field via CAS or read-and-add | `VarHandle` or `AtomicInteger` | Provides primitive atomic access modes without building read-modify-write manually |
| Accessing array elements in a concurrent algorithm | `arrayElementVarHandle` | Provides access modes on array elements |
| Wanting to mutate the value of a `final` field | Redesign the state | `VarHandle` does not allow writing `final` fields just because a handle was obtained |
| Need locks, queues, or complex concurrent structures | Proven `java.util.concurrent` constructs first | Easier to maintain than hand-rolled CAS/memory-ordering algorithms |

**The same system can use all three:** `Method` discovers annotations; `MethodHandle` executes invocations; `VarHandle` manages the framework's coordination state. The decision depends on each piece of code's responsibility.

## 9. Performance: Understand Correctly Before Optimizing

A choice can affect speed, yet you cannot conclude which is faster from the API name alone:

1. **Lookup and execution are two separate phases.** Comparing "`getMethod` then `invoke` every iteration" against "one cached `MethodHandle`" compares two different strategies; separate lookup cost from invocation cost.
2. **Call-site shape matters.** `MethodHandle.invokeExact` with a stable type has good optimization potential, yet adapter pipelines, polymorphic calls, boxing, visibility, and JVM warm-up change results.
3. **`VarHandle` access modes have different costs and meanings.** `getVolatile` or CAS typically has different synchronization/atomic cost than `get`. Do not use a weaker mode merely for prettier benchmark numbers if the algorithm requires stronger memory ordering.
4. **Measure with JMH when this is a real bottleneck.** Include warm-up, sufficient measurement iterations, prevent the JVM from dead-code eliminating the work, and measure across multiple threads if the application contends on resources. Do not extrapolate a one-off run into a blanket claim that "MethodHandle is always faster than Method."

In particular, if the goal is simply a concurrency-safe counter, using `AtomicInteger` with `incrementAndGet()` is usually clearer and reduces the risk of misusing memory semantics with `VarHandle`.

## 10. Common Mistakes and Misconceptions

**"MethodHandle is just a renamed Method."** False. `Method` stores declaration metadata, whereas `MethodHandle` is a typed callable that can be bound/adapted/combined. You can convert a `Method` into a handle, yet their roles differ.

**"MethodHandle.invokeExact will automatically convert int to long if needed."** False. `invokeExact` demands exact types, including the return type; use `invoke`/`asType` when conversion rules apply.

**"Finding a private Method/VarHandle guarantees you can invoke or write to it."** False. Access permissions, modules, and supported access modes each impose their own limits.

**"VarHandle.get followed by VarHandle.set is an atomic increment."** False. Two separate operations can be interleaved by another thread. Use `getAndAdd`, a valid CAS loop, or an appropriate concurrency abstraction.

**"Just using volatile makes every multi-field state consistent automatically."** False. Volatile/CAS act on the accessed variable and memory-model relationships; invariants spanning multiple variables still must be designed.

**"Catch InvocationTargetException for MethodHandle.invokeExact."** Usually misplaced. That wrapper is specific to `Method.invoke` when the target method throws; a MethodHandle forwards the target's exception directly.

**"Replacing every Method with MethodHandle will make things faster."** There is no such guarantee. Target caching, call-site types, JVM, deployment environment, and call volume determine real-world performance.

## 11. Self-Check

1. You need to find every method annotated on a controller. Which API fits? **`Method`**, because metadata is needed.
2. After picking a handler by annotation, the server will call it many times. How can you structure this cleanly? **Keep `Method` for metadata analysis, then create/cache a `MethodHandle` for invocation; measure performance if needed.**
3. You want to increment `int counter` atomically from multiple threads. Is `MethodHandle.findGetter` enough? **No.** Consider `VarHandle.getAndAdd` or `AtomicInteger`.
4. A `Method` using `invoke` calls a target method that throws `IllegalStateException`. Where should you look for the root cause? **`InvocationTargetException.getCause()`.**
5. With `MethodHandle.invokeExact`, why can assigning the result to a variable of a different type fail? **The return type at the call site is part of the signature that must match.**
6. Does `VarHandle` support `getAndAdd` for every field? **No.** It depends on the variable type and access mode; check the API/support.
7. If processing an ordinary map with no dynamic access or custom atomic requirements, do you need any of these three tools? **Usually no.** Prefer direct Java APIs and high-level concurrency constructs when needed.

## 12. Conclusion and References

Clarify **what the problem actually is** before picking a tool: if you need to know *which method* and what annotations exist, use `Method`; if you need to *invoke a selected behavior* with an explicit, adaptable signature, use `MethodHandle`; if you need to *access/update a variable* with memory modes or CAS, use `VarHandle`. Always verify access permissions, call types, exception handling, and multi-threaded correctness. When static code is already clear, direct Java calls or high-level concurrency APIs remain the first choice to consider.

Official documentation:

- [Java SE 21 — `java.lang.reflect.Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 21 — `java.lang.invoke.MethodHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html)
- [Java SE 21 — `java.lang.invoke.MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html)
- [Java SE 21 — `java.lang.invoke.VarHandle`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/VarHandle.html)
- [Java SE 21 — `java.util.concurrent.atomic`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/atomic/package-summary.html)