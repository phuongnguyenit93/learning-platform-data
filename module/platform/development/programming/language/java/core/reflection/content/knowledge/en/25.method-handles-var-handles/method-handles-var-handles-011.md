# Do Not Assume One Mechanism Is Always Faster Than Another: Reflection, MethodHandle, and VarHandle

## 1. The Conclusion to Understand Accurately

In Java, `MethodHandle` and `VarHandle` provide access to members/variables with signatures handled directly by the JVM, yet **there is no universal rule** that they are always faster than `Method.invoke` or `Field.get/set` from Core Reflection. Nor can you say `MethodHandle` is always faster than `VarHandle`: they **do not solve the exact same problem**.

Actual speed depends simultaneously on:
- **Operation**: invoking a method, reading a field, writing a field, `volatile` access, or `compareAndSet`.
- **Stability of types and call sites**: whether the `MethodHandle`, `VarHandle`, `Method`, or `Field` object is cached, stable across calls, and recognizable/optimizable by the JIT.
- **Inlining potential and runtime profile**: whether a call site is monomorphic or polymorphic, and how much the receiver and target classes vary.
- **Conversion overhead**: boxing/unboxing, `Object[]` arrays for arguments, type conversions in `invoke` vs. `invokeExact`, and adapters like `asType`, `bindTo`, and `filterArguments`.
- **Memory constraints**: plain/opaque/acquire/release/volatile have different semantics and costs; comparing different semantics misses the target.
- **JDK/JVM version, CPU architecture, compilation tiers, GC, configuration, and actual workload**.

A good benchmark must define **"faster at doing what, on which runtime, with what semantics?"** before making a decision. Prioritize correctness, access control, and maintainability; use performance data measured on critical paths to weigh changing mechanisms.

## 2. What Do They Do and How Are They Non-Interchangeable?

| Mechanism | Suitable Task | Typical Invocation | What to Note When Comparing Performance |
| --- | --- | --- | --- |
| Ordinary Java call | Type/method already known at compile time | `obj.work(arg)` | Useful baseline; JIT can inline and eliminate unobservable work. |
| `java.lang.reflect.Method` | Flexibly find/invoke methods from runtime metadata | `method.invoke(obj, args...)` | Returns `Object`; may incur boxing/unboxing, argument handling, and access checks. |
| `MethodHandle` | Typed reference to a method/constructor/field, composed into dynamic pipelines | `mh.invokeExact(...)`, `mh.invoke(...)` | Cost and optimization potential depend on signature, adapters, call site, and whether the handle is stable. |
| `java.lang.reflect.Field` | Read/write fields via Reflection metadata | `field.getInt(obj)`, `field.setInt(obj, v)` | Primitive APIs like `getInt` avoid the boxing caused by `get` returning `Object`. |
| `VarHandle` | Access variables/fields/arrays with explicit access modes and memory ordering | `vh.get(obj)`, `vh.set(obj,v)`, `vh.compareAndSet(obj,a,b)` | Must pick equivalent modes when comparing; `getVolatile` is not equivalent to `get`. |

`MethodHandle` can represent field **getters/setters**, while `VarHandle` can convert an access mode into a `MethodHandle` via `toMethodHandle(...)`. Thus there is overlap, yet `VarHandle` is designed to express **multiple variable access modes** and atomic operations, not as a mechanism for calling arbitrary methods.

Do not compare the timing of `MethodHandle.invokeExact` calling an addition method with `VarHandle.compareAndSet` updating a variable: the two operations produce different results and guarantees. If you want to compare field reads, compare `obj.field`, `Field.getInt`, a `MethodHandle` getter, and `VarHandle.get` on the same field under equivalent conditions.

## 3. What Determines Performance at the Call Site?

### 3.1. Lookup vs. Invocation

`Class.getMethod`, `MethodHandles.Lookup.findVirtual`, `findGetter`, and `findVarHandle` are used to **look up and verify access permissions**. Lookup cost is not the cost of repeatedly invoking a method or reading a field.

- If an application performs only a few accesses, the setup/configuration cost of a handle can outweigh invocation time.
- If running millions of times, caching `Method`/`Field`/`MethodHandle`/`VarHandle` outside the loop typically reflects the true hot path.
- Do not place lookup *inside* one benchmark variant while another variant uses a pre-cached handle. If you want to compare total setup + usage cost, measure **the same lifecycle** for all.

### 3.2. JIT Optimization and Constant-Folding Handles

When the JIT can see a stable target/handle (for instance, a `static final` field or a sufficiently clear dataflow path), the JIT has an **opportunity** to inline, specialize, or fold away intermediate steps. When targets change constantly, are fetched from array elements, or a call site sees many target types, optimizations can differ.

Do not infer "`static final` guarantees inlining" or "non-`final` is guaranteed to be slow": these outcomes depend on runtime profiles and JIT implementation. `final` is a helpful signal to the JVM that a reference is stable, not a performance-ranking promise.

### 3.3. `invokeExact`, `invoke`, and Adapters

- `MethodHandle.invokeExact` requires the **call-site signature to match `MethodHandle.type()` exactly**, including parameter types **and return type**. Mismatches can throw `WrongMethodTypeException`.
- `MethodHandle.invoke` permits certain type conversions like `asType`. The JVM may optimize conversions when enough information is available, yet adaptation can also add work.
- `invokeWithArguments` is convenient for dynamic `Object[]`/`List<?>` arguments and does not represent the same optimized call pattern as fixed-signature `invokeExact`.
- `VarHandle` has signature-polymorphic access modes; `withInvokeExactBehavior()` requires exact signature matching, whereas the default behavior may allow adaptations equivalent to `invoke` per API rules.

When benchmarking, record the exact variant used and the call-site types. Switching `invokeExact` to `invokeWithArguments` and blaming `MethodHandle` as a whole is an invalid conclusion.

### 3.4. Core Reflection Evolves Across Java Releases

Starting in **JDK 18**, [JEP 416](https://openjdk.org/jeps/416) reimplemented the core of Core Reflection (`Method`, `Constructor`, `Field`) on top of method handles. This does **not** mean `Method.invoke` and `MethodHandle.invokeExact` are the same public API or have identical overhead. However, it shows that runtime internals evolve: comparisons based on older Reflection implementations do not automatically apply to newer JDKs.

JEP 416 also cites benchmarks showing that performance varies **by reference-holding pattern** (constant, variable, array access...) and by operation kind. Numbers in a JDK enhancement proposal describe only that environment and workload; they are not a fixed speedup ratio for another application. **Do not extrapolate one version's benchmark numbers to every JDK.**

## 4. Runnable Java 17+ Example: Same Results, Without Claiming Which Is Faster

Save the entire program below as **`AccessChoicesDemo.java`**. It uses the same `add(int)` method and the same `value` field to verify equivalent results before discussing performance.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.VarHandle;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class AccessChoicesDemo {
    public static final class Counter {
        public int value = 2;

        public int add(int delta) {
            return value + delta;
        }
    }

    public static void main(String[] args) throws Throwable {
        Counter counter = new Counter();
        Method reflectedAdd = Counter.class.getMethod("add", int.class);
        Field reflectedValue = Counter.class.getField("value");

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle addHandle = lookup.findVirtual(
                Counter.class, "add", MethodType.methodType(int.class, int.class));
        MethodHandle getterHandle = lookup.findGetter(
                Counter.class, "value", int.class);
        VarHandle valueHandle = lookup.findVarHandle(
                Counter.class, "value", int.class);

        System.out.println("Direct call: " + counter.add(3));
        System.out.println("Method.invoke: " + reflectedAdd.invoke(counter, 3));
        System.out.println("MethodHandle.invokeExact: "
                + (int) addHandle.invokeExact(counter, 3));

        System.out.println("Direct field read: " + counter.value);
        System.out.println("Field.getInt: " + reflectedValue.getInt(counter));
        System.out.println("MethodHandle field getter: "
                + (int) getterHandle.invokeExact(counter));
        System.out.println("VarHandle.get: " + (int) valueHandle.get(counter));

        System.out.println("VarHandle.compareAndSet: "
                + valueHandle.compareAndSet(counter, 2, 9));
        System.out.println("Field after CAS: " + reflectedValue.getInt(counter));
    }
}
```

Compile and run:

```bash
javac --release 17 AccessChoicesDemo.java
java AccessChoicesDemo
```

Verified actual output on JDK 24 with Java 17 bytecode target:

```text
Direct call: 5
Method.invoke: 5
MethodHandle.invokeExact: 5
Direct field read: 2
Field.getInt: 2
MethodHandle field getter: 2
VarHandle.get: 2
VarHandle.compareAndSet: true
Field after CAS: 9
```

Analysis:

1. All three ways of calling `add(3)` return `5`. `Method.invoke` returns `Object`, so string concatenation prints the value from a boxed `Integer`; `invokeExact` here returns primitive `int` matching `MethodType`.
2. All four field reads observe the same value `2`. `Field.getInt` and a `MethodHandle` getter are direct choices for comparing **plain reads** with `VarHandle.get`. `MethodHandle getter` has a signature equivalent to `(Counter)int`.
3. `compareAndSet` performs an **atomic** operation checking `2` and swapping to `9`; this is a different feature from a plain field read and must not be lumped into a "read cost" measurement.
4. All lookups are performed before the calls; **this program verifies correctness, not speed**. Wrapping each line in `System.nanoTime()` will not yield a meaningful ranking.

The example uses `public` members so `setAccessible(true)` is unnecessary. For private members, `MethodHandles.Lookup` and Reflection permissions must be configured per the corresponding module/package; do not compare a version failing due to missing permissions against one with opened access.

## 5. Memory Semantics: Compare the Same Work Before Comparing Time

`VarHandle` offers clearly separated operation modes:
- `get` / `set`: **plain** access (ordinary read/write semantics, adding no `volatile` synchronization guarantees).
- `getOpaque` / `setOpaque`: opaque access; provides weaker ordering constraints than acquire/release/volatile.
- `getAcquire` / `setRelease`: acquire/release ordering, fitting certain publication/consumption protocols.
- `getVolatile` / `setVolatile`: semantics equivalent to reading/writing `volatile`.
- `compareAndSet`, `compareAndExchange`, `getAndAdd`...: atomic or read-modify-write primitives when supported by the access mode and variable type.

`Field.getInt` on an ordinary field and `VarHandle.get` on the same field form a sensible pair to start comparing **plain reads**. On a `volatile`-declared field, re-analyze semantics before selecting an API/mode; do not compare a plain read against a volatile read and assume the faster one still satisfies synchronization requirements. `VarHandle` also does not automatically make an algorithm with a data race safe: you must choose appropriate memory ordering/atomicity and design the protocol correctly.

Not every access mode exists for every variable kind (for example, write/atomic operations on `final` fields are restricted). Check `isAccessModeSupported` and the `VarHandle` contract when specialized operations are needed.

## 6. Measuring Properly: JMH, Warm-Up, Forks, and Bias Control

### 6.1. Why a Loop with `nanoTime` Is Not Enough

If you write:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    handle.invokeExact(counter, 3); // note the return type!
}
long elapsed = System.nanoTime() - start;
```

this illustrative snippet **is not a valid benchmark program**: calling `invokeExact` as a statement gives the call site a `void` return type while the example handle returns `int`, so it can throw `WrongMethodTypeException`. Even when casting/consuming the result properly, the measurement still suffers from issues like cold JIT, dead-code elimination, OS/GC noise, or comparing algorithms doing unequal work.

The minimal signature fix is:

```java
int result = (int) addHandle.invokeExact(counter, 3);
```

yet a single `nanoTime` loop still **cannot** replace a rigorously designed benchmark.

### 6.2. How to Structure Benchmarks with JMH

[JMH (Java Microbenchmark Harness)](https://github.com/openjdk/jmh) is OpenJDK's dedicated toolkit for JVM microbenchmarks. When you need to make optimization decisions on a hot path:

1. **Define identical semantics** and comparison pairs: (a) direct method call / `Method.invoke` / `MethodHandle.invokeExact`; (b) direct field read / `Field.getInt` / getter `MethodHandle` / `VarHandle.get`. Measure CAS/volatile operations separately.
2. **Move lookups into the setup phase** when measuring steady-state invocation, and build a **separate** benchmark if the use case must measure setup + single use together.
3. **Configure warm-up, multiple measurement iterations, and multiple forks**. Record JDK vendor/version, JVM flags, CPU/OS, load environment, GC, and JMH version.
4. **Consume results** (return from `@Benchmark` or use `Blackhole`), supply varying inputs as appropriate, and avoid dead-code elimination or constant folding erasing the workload. Do not print to the console inside benchmark methods.
5. **Ensure equal polymorphism**: a single fixed target cannot be directly compared against a target chosen randomly on each iteration.
6. **Inspect result distributions and uncertainty**, fork-to-fork stability, and profiling. If differences are smaller than noise or do not shift the application's bottleneck, there is no basis to switch APIs.

*Structural sketch* template—must be placed inside a benchmark class with `MethodHandle addHandle`, `Method reflectedAdd`, `Counter counter` fields and JMH dependencies; **not a standalone Java file**:

```java
@Benchmark
public int direct() {
    return counter.add(3);
}

@Benchmark
public int viaReflection() throws ReflectiveOperationException {
    return (Integer) reflectedAdd.invoke(counter, 3);
}

@Benchmark
public int viaHandle() throws Throwable {
    return (int) addHandle.invokeExact(counter, 3);
}
```

Before running this template, declare `@State`, set up the handle/method/receiver, import `org.openjdk.jmh.annotations.Benchmark`, and configure JMH and its annotation processor in your build tool. Make `Counter` a workload with appropriate state/input so the real computation is not proven constant by the JIT. **Do not invent "expected ns/op" numbers**: figures must come from an actual measurement accompanied by system details.

### 6.3. Measurement Checklist

| Question | What Happens If Ignored? |
| --- | --- |
| Are lookup and caching identical? | Measuring setup on one side without measuring it on the other. |
| Are signatures and conversions equivalent? | Measuring different boxing/adapter overhead without stating so. |
| Do field operations use the same memory ordering? | Comparing two different semantics. |
| Are inputs, targets, and receiver type counts identical? | JIT profiles are not comparable. |
| Are warm-up, forks, and system state sound? | Random numbers, noise, or mostly measuring JIT startup. |
| Is the return value consumed and is there a real side effect? | The JIT may eliminate the work entirely. |
| Running on production-equivalent JDK/CPU? | Experimental results do not represent deployment. |
| Does end-to-end performance improve? | Microbenchmark optimization may yield no real-world benefit. |

## 7. Choosing an API Based on Real Requirements

**Discovery / plugin / serialization frameworks:** If you must discover classes/methods by name at runtime and call counts are low, Core Reflection is usually simpler and clearer to express. When a member is called very frequently with a stable signature, you can try caching a `MethodHandle` and **measuring** the benefit; outcomes still depend on the JDK and call site.

**Dynamic invocation with signature transformations:** `MethodHandle` has an API built for composition (`asType`, `bindTo`, `filterArguments`...), though each adapter can influence optimization. If an adapter can be built once and reused repeatedly, measure that pattern rather than rebuilding the adapter chain on every invocation.

**Field access with a concurrency protocol:** Choose `VarHandle` when you need `getAcquire`/`setRelease`/`compareAndSet` or explicit memory access modes, because **correct semantics** are mandatory. Then optimize among implementations with the same guarantees. Do not replace an atomic CAS with a plain write just to shrink benchmark time.

**Ordinary code with compile-time known types:** Direct calls or standard Java constructs are usually easy to understand and serve as the baseline. There is no default reason to convert every getter into `MethodHandle`/`VarHandle` hoping for speedups.

**After upgrading the JDK:** Re-measure if this is a critical hot spot. The JIT, Reflection implementation, memory barriers, and optimizations change across runtime versions. "Last year framework A beat B" is not a performance contract.

## 8. Common Wrong Conclusions

| Wrong Claim | Accurate Interpretation |
| --- | --- |
| "`MethodHandle` is always faster than Reflection." | JIT optimization potential and overhead depend on operation type, handle shape, call site, and JDK version. |
| "`VarHandle` is always faster than `MethodHandle`." | They serve different roles; compare only when performing the exact same field operation with the exact same semantics. |
| "`invokeExact` is always faster than `invoke`." | `invokeExact` avoids adaptation semantically, yet the runtime may optimize `invoke` in suitable cases; measure the specific workload. |
| "Measuring `Field.get` vs. `VarHandle.get` is completely fair." | `Field.get` can box primitives; consider `Field.getInt` if the goal is a plain int read. |
| "One `nanoTime` loop is enough to conclude." | You need warm-up, forks, noise control, and dead-code prevention. |
| "JDK 18 implements Reflection using MethodHandles, so both APIs have identical speed." | Sharing parts of internal implementation does not erase differences in API, caller shape, and overhead. |
| "CAS is slower than plain set, so use plain set for synchronization." | CAS guarantees atomicity that a plain store does not; synchronization requirements must be preserved. |
| "A great benchmark result means the application is definitely faster." | Bottlenecks may lie in I/O, allocation, locks, GC, or algorithms; measure end-to-end. |

## 9. Self-Check Questions

1. When comparing `Method.invoke` and `MethodHandle.invokeExact` on the same method, why should looking up `Method`/`MethodHandle` be moved outside the benchmark or measured separately?
2. When reading an `int field`, why is `Field.getInt` a more useful baseline than `Field.get` against `VarHandle.get`?
3. `MethodHandle.invokeExact` returns `int`. What issue can arise from calling it as a statement `mh.invokeExact(...)` without casting the return type?
4. If a variable can only be safely updated with `compareAndSet`, is it valid to use `VarHandle.set` as a direct speed baseline?
5. Why can a `static final MethodHandle` help the JIT yet still not guarantee it beats a cached `Method`?
6. After upgrading from JDK 17 to a newer JDK, why must old microbenchmark figures be re-evaluated?

**Rule of practice:** Pick the API by operation and semantics; start with a correct implementation; cache sensibly; use reproducible benchmarks on the real runtime; and check end-to-end impact. Without trustworthy data, **never claim any mechanism always wins**.

## 10. Official References

- [Java SE 17 — `MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `invokeExact`, `invoke`, adaptation, and type-checking rules.
- [Java SE 17 — `VarHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VarHandle.html): access modes, memory ordering, and invocation types.
- [Java SE 17 — `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `invoke` and the Core Reflection contract.
- [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): changes since JDK 18 along with per-pattern benchmark results.
- [OpenJDK JMH](https://github.com/openjdk/jmh): JVM microbenchmark harness, benchmark authoring, and runner tools.