# Metadata Lookup Cost Differs from Invoke Cost in Java Reflection

## Learning Objectives

When an application uses reflection, there are at least two very different tasks:

1. **Finding and interpreting metadata**: identifying a `Class`, looking up a `Method`/`Field`/`Constructor`, or reading generic signatures, annotations, and modifiers.
2. **Executing the method**: once a `Method` is obtained, calling `method.invoke(receiver, arguments...)` to run logic on an object or invoke a static method.

These two tasks have different cost characteristics. Code that is slow because it **looks up a method again on every request** does not mean `Method.invoke` itself bears all of that cost. Conversely, caching a `Method` only eliminates repeated lookups; it **does not turn a reflective call into a direct Java call**.

After this lesson, you will be able to separate the steps when measuring performance, understand when metadata caching helps, distinguish initialization cost from per-call cost, and design reasonably reliable benchmarks.

## 1. Two Stages and Scope of Work

Consider an example class:

~~~java
public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
~~~

This is an **illustrative class declaration snippet**, not a standalone program containing `main`.

The same method can be looked up and then invoked as follows:

~~~java
Method method = Calculator.class.getMethod(
        "add", int.class, int.class);    // Step A: look up metadata
Object result = method.invoke(
        new Calculator(), 2, 5);        // Step B: execute
~~~

This is also a **snippet**; it requires `import java.lang.reflect.Method` and declaring/handling checked exceptions. The value of `result` is an `Integer` representing `7`, because primitive values returned through `Method.invoke` are boxed.

| Stage | API Examples | Type of Work | Result |
| --- | --- | --- | --- |
| Obtain class handle | `Calculator.class`, `obj.getClass()` | Obtain/identify the `Class` object of a type | `Class<?>` |
| Look up member | `getMethod`, `getDeclaredMethod`, `getDeclaredFields` | Look up name/signature/declaration scope, may allocate wrappers and result arrays | `Method`, `Field`, `Constructor`, arrays |
| Read deep metadata | `getGenericReturnType`, `getAnnotations` | May parse `Signature`/annotations and resolve types | `Type`, annotations, metadata |
| Prepare member for use | `canAccess`, `trySetAccessible`, create `MethodHandle` | Check/configure accessibility, bind into a handle | Accessibility status or handle |
| Execute | `Method.invoke(target, args)` | Validate receiver/arguments/access permissions, convert, dispatch, and run the method body | `Object` result or exception |

**Do not equate** obtaining a `Class` from `Calculator.class` with looking up a `Method` by name repeatedly. `Class.forName(...)` can also involve class loading/initialization depending on how it is called, so its cold-start cost is not representative of normal lookup either.

### 1.1. What Does Metadata Lookup Cost?

With `clazz.getMethod("add", int.class, int.class)`, the runtime must find a `public` member matching the name and parameter list, taking inherited members into account according to the API rules. `getDeclaredMethod` only searches methods **declared directly** on the target class and can find non-public members as well. Switching from one method to the other solely for speed can produce the **wrong set of results**, so choose the API based on semantics first.

Factors affecting lookup cost:

- The number and shape of members, overloads, and the inheritance/interface hierarchy to traverse.
- Calling `getMethods()` / `getDeclaredMethods()` to enumerate an array of all members and then filtering, versus looking up a single method with an explicit name and parameter types.
- Allocation for `Method` wrappers and metadata arrays; the JVM/JDK may cache internally, but there is **no fixed performance contract** to rely on.
- Parsing annotations and generic metadata can incur separate additional work, including type resolution; this cost should not be lumped into a single generic metric named “reflection lookup”.
- A lookup performed once at application startup differs from lookups repeated thousands of times inside a request-processing loop.

Once you have the metadata, calls such as `method.getName()` and `method.getReturnType()` read data from the `Method`; they are not equivalent to calling `Class.getMethod(...)` again. However, some metadata APIs may allocate objects/arrays or resolve additional information; do not assume every getter is free.

### 1.2. What Does a Single `Method.invoke` Cost?

Once a `Method` is already available, `invoke` **does not re-run the `getMethod` call that the application used**. It must perform the semantics of a reflective invocation, including:

- Verifying a valid receiver for an instance method and checking access conditions under reflection/JPMS rules (how this is optimized depends on the JDK and member state).
- Checking argument count and types, and performing valid boxing/unboxing or primitive widening; varargs are not automatically flattened from an arbitrary array.
- Resolving the actual method to call, including **dynamic dispatch** for overridden instance methods; static methods use the specified method.
- Executing the **target method body**. SQL, I/O, networking, or data processing inside the method body can completely dominate reflection overhead.
- Boxing a primitive return value or returning `null` for `void`; exceptions thrown by the method body are wrapped in `InvocationTargetException`.

Invocation cost varies with the method, parameter types, JIT warmup, optimization eligibility, and JVM version. There is no universal rule like “invoke is always slower than lookup” or “reflection is always X times slower than a direct call” that holds across all Java/JVM setups.

## 2. Cost Model: Look Up Every Time vs. Cache Method?

Let:

- `L`: cost of **one** `Method` lookup by name/signature.
- `I`: cost of **one reflective invocation**, including invoke overhead and the target's work.
- `n`: number of times the same method needs to be called.

A simplified model, excluding JVM optimizations/caching/allocation and cache creation time:

| Approach | Approximate Total Cost |
| --- | --- |
| Look up then invoke every time | `n × (L + I)` |
| Look up once then reuse | `L + n × I` |
| Lookup savings (model) | `(n - 1) × L` |

For example: with 10,000 requests all calling the same method, the **lookup-per-request** version performs 10,000 lookups; the cached version performs one lookup and 10,000 invocations. Both versions still execute the business method 10,000 times.

This is a model to clarify where costs come from, **not** a claim that `L` or `I` is a constant that can be measured completely independently on a real JVM. If a method is only used once, caching may make no sense; if the target performs lengthy I/O, the lookup savings may be negligible compared to end-to-end latency.

## 3. Runnable Java 17+ Example: Counting Lookups and Invokes

This example intentionally **does not print nanoseconds** because ultra-short timings from a single run easily lead to wrong conclusions. Instead, the code uses deterministic counts to demonstrate that caching `Method` reduces **the number of metadata lookups**, while the number of invocations stays the same.

Save the file as **ReflectionCostDemo.java**:

~~~java
import java.lang.reflect.Method;

public class ReflectionCostDemo {
    public static final class Calculator {
        public int add(int a, int b) {
            return a + b;
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Calculator target = new Calculator();
        final int calls = 4;

        // Approach 1: look up Method again on every call.
        int repeatedSum = 0;
        int repeatedLookups = 0;
        for (int i = 1; i <= calls; i++) {
            Method method = Calculator.class.getMethod(
                    "add", int.class, int.class);
            repeatedLookups++;
            repeatedSum += (Integer) method.invoke(target, i, 10);
        }

        // Approach 2: look up once, then invoke multiple times.
        Method cached = Calculator.class.getMethod(
                "add", int.class, int.class);
        int cachedSum = 0;
        for (int i = 1; i <= calls; i++) {
            cachedSum += (Integer) cached.invoke(target, i, 10);
        }

        // Control: direct Java call without reflection.
        int directSum = 0;
        for (int i = 1; i <= calls; i++) {
            directSum += target.add(i, 10);
        }

        System.out.println("repeated: lookups=" + repeatedLookups
                + ", invokes=" + calls + ", sum=" + repeatedSum);
        System.out.println("cached: lookups=1, invokes=" + calls
                + ", sum=" + cachedSum);
        System.out.println("direct: lookups=0, invokes=0, sum=" + directSum);
        System.out.println("metadata: name=" + cached.getName()
                + ", parameters=" + cached.getParameterCount()
                + ", return=" + cached.getReturnType().getTypeName());
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 ReflectionCostDemo.java
java ReflectionCostDemo
~~~

Stdout:

~~~text
repeated: lookups=4, invokes=4, sum=50
cached: lookups=1, invokes=4, sum=50
direct: lookups=0, invokes=0, sum=50
metadata: name=add, parameters=2, return=int
~~~

Explanation:

1. All three paths execute the addition for `i` from 1 to 4 and `10`, yielding the sum `11 + 12 + 13 + 14 = 50`.
2. The first approach calls `Class.getMethod(...)` **four times**; the second calls it **only once**. Both use `Method.invoke(...)` four times.
3. `cached.getName()`, `getParameterCount()`, and `getReturnType()` show that metadata can be read from the saved `Method` without running `getMethod(...)` again.
4. This is a **work-structure experiment**, not a wall-clock microbenchmark. The lookup/invoke counts and stdout above are deterministic; actual latency varies across machines, JDKs, and individual runs.

## 4. Designing Caches at the Right Scope

### 4.1. Where Should You Cache?

- **A fixed method in a long-lived component:** resolve the `Method` during initialization and store it in a field; reuse it across requests.
- **One class with many methods:** build an index by name + parameter types or annotations once when registering routes/serializers/DI beans. Do not scan `getDeclaredMethods()` and filter on every request.
- **Many dynamic classes:** use a cache structure with keys that properly distinguish `Class<?>` and signature, handling concurrency if multiple threads use it; consider `ClassValue<T>` to tie data to class lifetime.
- **Plugins/hot reload/changing classloaders:** avoid unbounded strong `static Map<Class<?>, Method>` caches. Keys and values holding references to classes/classloaders can prevent unloading; use explicit lifecycles or an appropriate cache mechanism.

A common mistake is caching a `Method` only by the string name `"save"`. Two classes or two overloads can share the same name while differing in parameters and declarations. Cache keys typically need to include **class identity (and classloader context), method name, parameter types, and lookup mode**; do not rely solely on class name as a String.

A `Method` can be reused across threads for normal invocation, provided the target object itself and business data are properly managed for thread safety. Caching does not make `target` thread-safe. In addition, calls to `trySetAccessible()`/`setAccessible(true)` are governed by permissions and module access; caching a lookup result does not bypass JPMS.

### 4.2. Which Lookups Does Caching Eliminate, and What Does It Not?

| Decision | Can Reduce | Does Not Automatically Reduce |
| --- | --- | --- |
| Reuse `Method` | Repeated `getMethod` / `getDeclaredMethod` | Invoke overhead, method body |
| Cache valid annotation/generic scan results | Repeated metadata parsing/filtering | Work that uses those results on each request |
| Prepare `MethodHandle` once | Repeated lookup/handle creation step | Method body cost; JIT gains must be measured |
| Replace reflection with direct Java calls | Can eliminate multiple layers of dynamic overhead | Does not change I/O or business CPU work in the method |
| Cache **business results** as well | Can avoid calling the method if results may be reused | Freshness correctness, invalidation, and concurrency |

Do not confuse **metadata caching** with **business result caching**. Caching a `Method` does not return an old value from a previous invocation, whereas caching method results requires its own key/TTL/invalidation rules.

### 4.3. When Do You Need `MethodHandle` or `VarHandle`?

`java.lang.invoke.MethodHandle` represents a call path prepared through `MethodHandles.Lookup` and can be used with `invokeExact`/`invoke` under specific typing rules. For very hot call paths with a stable handle, the JIT can optimize well, but handle lookup/setup also has a cost and there is no guarantee every benchmark will be faster than reflection.

- For hot-path methods, compare **cached `Method.invoke`** against **cached `MethodHandle`**, rather than comparing a pre-built handle against `getMethod + invoke` inside every iteration and attributing the entire difference to invoke.
- `VarHandle` is a mechanism for accessing variables/fields with explicit memory-order semantics, distinct from methods; use the right API for the job.
- Do not ignore access permissions, module openness, exact type signatures, and method handle adaptation costs.

## 5. Measuring Performance Properly: Separating Lookup, Invoke, and Total Path

`System.nanoTime()` is an interval timer, but taking a few readings in a `main` method is **not enough** to determine the isolated cost of reflection: an un-warmed JIT, class initialization, dead-code elimination, constant folding, GC, CPU scheduling, and the JVM's own caches can all skew the result.

Use **JMH (Java Microbenchmark Harness)** when the real goal is comparing nanoseconds/op or throughput in small scenarios. Create separate benchmarks and run them in the same environment:

| Benchmark | Work Per Operation | Question Answered |
| --- | --- | --- |
| `lookupOnly` | `clazz.getMethod(name, parameterTypes...)`, consume `Method` | What is the lookup cost under warmed-up conditions? |
| `invokeCached` | `cachedMethod.invoke(target, ...)`, consume result | What is the invocation cost when the `Method` is already obtained? |
| `lookupThenInvoke` | Lookup and invoke in the same operation | What is the total cost when real code looks it up every time? |
| `directCall` | `target.add(...)`, consume result | How much does a normal Java call with the same target logic cost? |
| `cachedHandleCall` (optional) | Use a `MethodHandle` created during setup | Are there different optimization opportunities with a prepared handle? |

A meaningful experimental design should:

1. Prepare `target` and `Method` in `@Setup` for the cached branch; **do not include setup in the timing of `invokeCached`**.
2. Include warmup, measurement iterations, and multiple independent forks/JVMs; record JDK version, hardware, JMH version, flags, and compiler state.
3. Use inputs/outputs properly so the compiler cannot eliminate the computation; in JMH, return results or use `Blackhole`. Choose a target method that reflects real work, not just a trivial addition if you want to extrapolate to an application.
4. Measure allocation and GC alongside latency/throughput when needed; distinguish **cold startup** from **steady state**.
5. Distinguish `getMethod` looking up one name from `getMethods` scanning all methods, and distinguish simple signatures from complex generics/annotations.
6. Compare relative results across multiple trials and variance ranges; do not treat a single “reflection is N times slower” number as a fixed property of Java.

**Important:** in a lookup benchmark, the JVM may optimize constant input values; while this still reflects a particular usage pattern, it does not represent lookups with continuously changing class/method names. Measure the workload that fits your application: a fixed signature, many overloads, or many dynamically loaded types.

### Analyzing Measurement Results by Cost Source

Suppose a profiler shows that most request time is spent inside a target method executing database queries; saving a few lookups will barely change end-to-end latency. Conversely, a framework mapping millions of small objects—calling `getDeclaredFields()` and iterating annotations for each object—can incur substantial allocation and CPU cost; caching the schema/metadata once is usually worth testing.

If `lookupOnly` accounts for a significant share, prioritize reusing metadata. If `invokeCached` remains a bottleneck on a hot path, consider static APIs, stable method handles, or code generation, but only after measuring and verifying correctness.

## 6. Correctness Risks and Optimization Traps

### 6.1. Get Lookup Semantics Right Before Optimizing

`getMethod` only retrieves matching `public` methods (including inherited ones); `getDeclaredMethod` only retrieves members declared on the class itself, including non-public ones. They cannot be swapped just because a benchmark shows a difference. If a method is overloaded, you must pass the exact `Class<?>` of each parameter; `Integer.class` cannot arbitrarily substitute for `int.class` when looking up `add(int,int)`.

### 6.2. Reflective Invoke Has Its Own Runtime Contract

- `Method.invoke` can throw `IllegalAccessException`, `IllegalArgumentException`, or `InvocationTargetException`; exceptions thrown by the target method are wrapped in `InvocationTargetException`.
- For instance methods, the receiver must be compatible; static methods do not require an instance receiver.
- Primitive arguments are boxed in the argument array, and primitive results are boxed in `Object`; `void` returns `null`.
- Caching a `Method` under the wrong class/loader or signature easily leads to runtime errors, even if a benchmark of the cache looks fast.
- Non-public access in JPMS may be blocked. Do not automatically use `setAccessible(true)` as a performance trick; it alters accessibility within the JVM's module rules.

### 6.3. Do Not Optimize Before Knowing the Lifecycle

A startup tool that scans annotations once and stores a router/mapper can accept startup cost to reduce request cost. A long-lived plugin library must account for reload and unloading so it does not retain old classloaders. And an application that rarely uses reflection can keep direct lookup code for simplicity if the profiler has not shown an issue.

## 7. Summary and Self-Check Questions

The key takeaway is that **metadata lookup time** and **reflective invocation execution time** belong to two separate stages. Caching a `Method` avoids repeating the `Method` lookup stage; it does not eliminate `Method.invoke` overhead or the business method's work. Deep metadata (generics, annotations) also has its own parsing cost that needs to be measured in the right place. Actual gains always depend on workload/JDK/JIT, so use a profiler and JMH instead of guessed numbers.

Self-check:

1. When the same `Method` is called 1,000 times, why should you consider caching instead of calling `getMethod` 1,000 times? Which costs still remain?
2. How do `getMethods()` and `getMethod("add", int.class, int.class)` differ in semantics and amount of work?
3. Why does the `sum=50` output in the example only prove functional equivalence, not speed?
4. When benchmarking `cachedHandleCall` against `lookupThenInvoke`, why is the conclusion “MethodHandle invoke is faster” unverified?
5. When using a cache in a plugin with its own classloader, how do you avoid confusing type identity and retaining a classloader that is no longer used?

### Official API References

- Java SE 21 — `Class`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html
- Java SE 21 — `Method`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 21 — `ClassValue`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassValue.html
- Java SE 21 — `MethodHandle`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandle.html
- JMH (OpenJDK benchmark harness): https://github.com/openjdk/jmh