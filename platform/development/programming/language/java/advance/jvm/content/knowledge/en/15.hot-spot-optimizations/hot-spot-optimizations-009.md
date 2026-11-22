# Why can a small source code change cause a large performance difference?

In the **HotSpot JVM**, a change of just a few characters in Java source can create a large, small, or even **reversed** performance difference after the application runs long enough. The reason is not simply "shorter code runs faster": Java source is compiled into **bytecode**, after which HotSpot may **interpret**, **collect profiles**, **JIT compile** with C1/C2, **inline**, **devirtualize**, **eliminate allocations**, **optimize loops**, **vectorize**, or **deoptimize** when runtime assumptions are no longer valid.

A small edit sometimes accidentally pushes the compiler across or below an **optimization decision threshold**. For example, a large method gaining a bit more bytecode may no longer fit the **inlining heuristic**, or changing a field to `volatile` may prevent simplifications that previously existed. Conversely, changing a data structure can greatly reduce cache misses or allocations even with only a few lines changed.

This lesson explains the **cause-and-effect mechanisms**, **when not to blame the JIT**, and **how to design reliable experiments** on Java 17+.

## 1. Performance does not scale linearly with source line count

Typical pipeline diagram:

```text
Java source
   │ javac
   ▼
JVM bytecode
   │ class loading / linking / execution
   ▼
Interpreter + profiling (level 0)
   │ method/loop "hot", compiler queues
   ▼
C1 (levels 1–3) ────► C2 (level 4)
   │                      │
   │       type/branch profiles + speculation
   └──────────────────────┘
               │
               ▼
      native machine code
      in HotSpot code cache
               │
               ▼
  CPU pipeline, caches, memory hierarchy,
  allocation, GC, OS scheduler, contention
```

**A small diff in source** can have an impact at multiple layers:

- Changing bytecode size / control flow structure.
- Changing how hot a method or loop is and when JIT compilation occurs.
- Changing the receiver types observed at a call site.
- Changing **method inlining** opportunities, especially in call chains.
- Changing opportunities for **constant folding**, **dead-code elimination**, or **escape analysis**.
- Changing branch distribution, locality, branch prediction, and cache behavior.
- Changing allocation rate, GC timing, and safepoints.
- Changing lock contention or memory ordering constraints.
- Changing the nature of the experiment: the compiler optimized away what was being "measured".

**There is no rule of "adding 1 line = X nanoseconds slower"**. You must identify the actual code path the CPU executes and all measurement conditions.

## 2. Correctly distinguishing two types of changes

### 2.1. Changing program behavior

For example, replacing an O(n²) algorithm with O(n log n), changing a linked list to a contiguous array, adding a cache, or changing I/O access. Those changes can make speed differ greatly **without needing to invoke the JIT as the explanation**.

```java
// Illustrative snippet inside a method, not a standalone program.
for (int i = 0; i < values.length; i++) {
    result += values[i];
}
```

If `values` is `int[]`, the direct representation differs from `List<Integer>` which has boxing/references and a different access pattern. However, one must not claim arrays are always faster in every task; different APIs, access patterns, nullability, and collections have their own trade-offs.

### 2.2. Same functional result, different optimization path

For example, turning a small method into a chain of delegates, adding an interface/proxy layer, or adding a `volatile` write. The returned result may still be correct as before, but the JIT and CPU see something **completely different**.

The key is knowing **what was changed**: semantic work, compiler opportunity, or measurement environment? Without classifying this, it is easy to attribute every difference to "HotSpot is unpredictable".

## 3. Tiered compilation thresholds: a change makes a method hot earlier or later

HotSpot typically starts executing bytecode with the **interpreter**, and may compile with C1 then C2 when profiles and policy are appropriate:

| Level | Component | General role |
| --- | --- | --- |
| 0 | Interpreter | Initial execution, collecting counters/profiles |
| 1 | C1 without full profiling | Lightweight compiled code, not aimed at collecting much data |
| 2 | C1 limited profiling | Tracking hotness with limited instrumentation |
| 3 | C1 full profiling | Collecting type/branch data for further optimization |
| 4 | C2 | Optimized code, may use profiles and assumptions |

**Not every method goes sequentially through 0 → 1 → 2 → 3 → 4.** The policy selects based on invocation/backedge counters, when compiler threads process the queue, method size, code cache, and other conditions.

### A single line changing the call count can change the entire execution tier

Suppose method `process` was previously called 50 times at startup, and after refactoring is called 50,000 times. The same method body may:

- Initially run in the interpreter.
- Be compiled by C1 when hot enough.
- Receive type/branch profiles.
- Be more deeply optimized by C2 after warm-up.

In a benchmark that is too short, such a change causes us to **compare the interpreter in version A with optimized code in version B**, rather than measuring "the direct impact of a one-line refactor".

### Long loops and OSR

**On-Stack Replacement (OSR)** allows HotSpot to transition a method **currently running in a long loop** to compiled code at an appropriate bytecode index. Therefore, a small change in loop bounds can affect hotness via backedge counters; the first run and subsequent runs can produce different results.

**Do not assume** that exceeding exactly 10,000 iterations forces OSR; compiler policy, flags, and environments differ.

## 4. Inlining cliff: changing a few bytecodes loses the inlining opportunity

**Inlining** replaces a method call with the callee's body inside the compiled caller (when the compiler deems it appropriate). In HotSpot, this is a decision based on **heuristics, profiling, bytecode size, and budgets**, not a rule that "every method under N lines is inlined".

Example:

```java
static int addOne(int x) {
    return x + 1;
}

static int compute(int x) {
    return addOne(x) * 2;
}
```

The two methods above are **snippets placed in the same class**. If the compiler inlines `addOne`, it can see the whole expression `(x + 1) * 2` and optimize further. However, it is not guaranteed that all JDK builds/conditions must inline it.

### A small change can cross the inlining threshold

Suppose you add validation, logging, exception handling, or branches to the callee:

```java
static int addOneWithCheck(int x) {
    if (x < 0) {
        throw new IllegalArgumentException("negative");
    }
    return x + 1;
}
```

On all-positive data, the business result is still adding 1. But the body/call graph/cost changes:

- The callee has more bytecode.
- There is a new branch and an exception path.
- The compiler must preserve exception semantics.
- The inlining decision may change.
- When not inlined, the caller may lose opportunities for constant propagation and cross-method optimizations.

**This is a possibility, not a pre-measured result:** HotSpot may still inline a callee with a check, or hoist/eliminate the check if there is sufficient basis. Do not claim that adding an `if` always makes code slower.

### Inlining heuristics are not an ABI

There are HotSpot flags such as `MaxInlineSize`, `FreqInlineSize`, `MaxTrivialSize`, and other budget limits. However, a single bytecode threshold does not independently decide everything: **hot methods** may have different thresholds from cold methods; call depth, recursive inlining, compiler budgets, type profiles, and code cache also have an effect.

When editing a method right near a threshold, performance can take the form of a **step jump** rather than increasing smoothly with bytecode count. That is why calling this phenomenon an **optimization cliff** is more useful than interpreting it as "the new line costs 3 ns".

## 5. Devirtualization cliff: the receiver profile changes upon refactoring

An interface call is usually compiled to `invokeinterface` in bytecode. However, at a hot call site, HotSpot can use **class hierarchy analysis (CHA)** and **type profiling** to determine the target, then make a direct call or inline it.

Example:

```java
interface Operation {
    int apply(int x);
}

final class AddOne implements Operation {
    public int apply(int x) {
        return x + 1;
    }
}

final class TimesTwo implements Operation {
    public int apply(int x) {
        return x * 2;
    }
}
```

These are illustrative types, without a `main`. A caller:

```java
static int route(Operation operation, int value) {
    return operation.apply(value);
}
```

**Case A:** during warm-up, `route` receives almost only `AddOne`. The type profile can be **monomorphic**, favorable for guarded devirtualization and inlining.

**Case B:** just adding one call path with `TimesTwo`, the call site can become **polymorphic**. The compiler may generate guarded paths for a few targets, or choose generic dispatch, or deopt/recompile if old assumptions no longer fit.

**Do not equate "having 2 implementations in source" with "a bimorphic call site":** the profile follows the **runtime receiver types at the site itself**. An interface with 100 implementations where the site only ever sees one type can still be monomorphic.

### Assumptions can be invalidated

- A new plugin class is loaded.
- A dynamic proxy or subclass appears.
- Traffic shifts to a different concrete type.
- A class hierarchy dependency no longer holds.
- C2 code previously inlined a target based on speculative type data.

HotSpot needs **guards/fallbacks/deoptimization/compiled dependency invalidation** to preserve Java semantics. A site with an unexpected target **must not** mistakenly call the old implementation. However, not **every** encounter with a new type forces a deopt: the compiler may have an appropriate fallback path.

### Why can the difference be large?

If devirtualization enables inlining a small method, and inlining enables constant folding/escape analysis across methods, losing the optimized target can lose **the entire chain of optimizations**. It does not merely add the cost of one virtual dispatch instruction.

## 6. Escape analysis: adding one escaping reference makes scalar replacement disappear

**Escape analysis (EA)** checks whether an object can escape a method/thread. HotSpot C2 can use that information to **scalar-replace** an object: keeping field values as scalars instead of maintaining a physical heap allocation on the optimized path.

Example:

```java
static int localScore(int x) {
    Pair p = new Pair(x, x * 2);
    return p.left + p.right;
}
```

This is a snippet; `Pair` must be defined in the same class. If `p` does not escape and the compiler understands the entire processing path, object creation may be eliminated in compiled code.

Small edit:

```java
static volatile Object published;

static int publishedScore(int x) {
    Pair p = new Pair(x, x * 2);
    published = p;
    return p.left + p.right;
}
```

This is an illustrative snippet in a single class. Writing the reference to a **static volatile field** causes the object to **be published outside the local scope**, usually preventing allocation elimination via the same scalar replacement strategy. The difference can involve a whole cascade:

- Heap allocations.
- TLAB refills and the allocation fast path.
- Garbage generation / GC work.
- Write barriers and volatile memory-ordering costs.
- CPU cache traffic and memory bandwidth.

**Be careful:** do not claim every `new Pair` creates a physical object in every JVM / every path; nor say the local version is guaranteed to be scalar-replaced. This is an **optimization opportunity dependent on C2/JDK/profile**.

### HotSpot EA does not mean automatic stack allocation

HotSpot EA documentation describes **scalar replacement**; one should not claim HotSpot C2 in JDK 17 performs **general-purpose stack allocation** of all non-escaping objects by default. "The allocation disappeared" may be because fields were replaced by scalars/optimized operations, not because the object simply moved its allocation site from the heap to the stack.

### `volatile` is not the only thing that causes escape

An object can escape through:

- Returning the object reference.
- Writing into a field of a long-lived object or a static field.
- Putting it into a collection held from outside.
- Passing it through a call where the JIT cannot prove the receiver/callee does not retain the reference.
- Native/JNI interaction.
- Concurrent/shared state structures.

Even so, **returning an object** does not automatically mean the allocation definitely exists after the caller inlines it; the compiler can analyze across methods in an optimized context. Escape must be viewed **within the compiled scope**, not just a single Java statement.

## 7. Dead-code elimination: the measurement looks fast because the work was deleted

A naive microbenchmark:

```java
static int pure(int x) {
    return x * x + 1;
}

static void suspicious() {
    for (int i = 0; i < 1_000_000; i++) {
        pure(42);
    }
}
```

These are two illustrative methods in a class. The result of each `pure(42)` call **is not used**, and `pure` has no side effects. The JVM/JIT can eliminate the computation along with most or all of the loop when it observes that it does not affect program behavior.

If one benchmark version **prints the result** while the other **discards the result**, the speed difference can be huge because **they are no longer measuring the same work**. Claiming "version B runs 1,000 times faster" in that case does not prove algorithm B is better at all.

### How to fix this when benchmarking

- The result must be **consumed** in a way the harness handles properly.
- With **JMH**, you can **return the result** from `@Benchmark` or use `Blackhole.consume(result)`.
- Do not rush to use a `volatile` store **every iteration** to "prevent DCE" and forget that you just added synchronization/memory-ordering cost to the measurement.
- Input data must vary according to realistic cases, not just a literal the compiler can constant-fold.
- Read the official JMH samples on **Dead Code Elimination** and **Constant Folding**.

**Avoid over-interpreting:** just because you "use the result" in Java source does not mean the benchmark is already correct. The JIT can still determine the output is a constant or hoist work out of the measured region. JMH helps design the harness, but **does not replace verification thinking**.

## 8. Constant folding and constant propagation: even a small literal makes a difference

Example:

```java
static int calculate(int x) {
    return (x * 31 + 7) & 1023;
}

static int constantInput() {
    return calculate(42);
}
```

This is an illustrative snippet in a class. If the compiler inlines `calculate`, the constant input `42` allows the expression to be computed **right at compile time**; the running program afterward no longer executes that multiplication/addition on the hot path.

Replacing `42` with a runtime field:

```java
static volatile int changingInput = 42;

static int runtimeInput() {
    return calculate(changingInput);
}
```

A `volatile` read must obey the Java Memory Model, as the value can be changed by another thread. The compiler cannot turn every read into a literal if doing so would change semantics.

**The two versions are no longer measuring the same computation conditions.** If the purpose is to measure the cost of `calculate` with runtime inputs, use a non-constant `@State` in JMH, and avoid designing a loop that lets the JIT accidentally infer an invariant input.

### `final` and compile-time constants

`static final int VALUE = 42;` is a **constant variable** eligible for Java constant expressions and can be inlined at the bytecode level at call sites. However, **not every `final` field is a compile-time constant**: a `final Object`, a `final` field initialized at runtime, or a value obtained from I/O has different semantics.

**Be careful when benchmarking:** "just adding `final`" sometimes enables constant propagation, but the effect depends on the data, how it is initialized, the compiled method scope, and the JIT.

## 9. Loop transformations: a single branch or alias changes vectorization

Transformations that can be applied to loops include:

- **Loop unrolling**: processing multiple iterations per pass.
- **Loop invariant code motion**: moving invariant expressions outside the loop.
- **Range-check elimination**: removing bounds checks proven redundant.
- **SuperWord/vectorization**: potentially using SIMD instructions when access patterns/data dependencies are suitable.
- **Strength reduction**: transforming expensive operations into a suitable form.
- **Auto-vectorization constraints**: aliasing, dependencies, exception semantics, and the CPU instruction set.

Example:

```java
static void addArrays(int[] a, int[] b, int[] out) {
    for (int i = 0; i < out.length; i++) {
        out[i] = a[i] + b[i];
    }
}
```

This is a method that can compile when placed in a class, but **it is only valid if a/b have length at least equal to out**. The VM must preserve the ability to throw `ArrayIndexOutOfBoundsException` when inputs are short. Checks must not be removed unless proven safe under exception-ordering rules.

Editing the loop:

```java
static void addArraysWithSideEffect(int[] a, int[] b, int[] out) {
    for (int i = 0; i < out.length; i++) {
        out[i] = a[i] + b[i];
        counter++;
    }
}
```

This is a snippet; `counter` must be a declared field. With a normal `counter`, the JIT can merge/move some updates if interleaved observation is not possible. With a `volatile counter`, each iteration carries different semantics, complicating vectorization/hoisting and increasing memory-ordering cost.

**Do not claim** the first loop is always vectorized and the second is always scalar: you need to check the CPU, compiler logs/assembly, array aliasing, hotness, and JDK build. Changing just one line can **remove the precondition for applying** an optimization, rather than guaranteeing a single instruction is turned on or off.

### Loop-carried dependencies

`out[i] = out[i - 1] + x` creates a loop-carried dependency (with i starting from 1). It differs from a loop where each element is independent. A refactor changing how reads/writes are done can introduce a data dependency that makes SIMD no longer suitable, even with very few lines.

## 10. Branch prediction and input data

A small change in an `if` condition can:

- Turn the hot path into a hard-to-predict branch.
- Change the number of CPU branch mispredictions.
- Change the code layout after JIT.
- Change opportunities for hoisting/inlining/loop predication.
- Make the profile during warm-up unrepresentative of production.

Illustrative example:

```java
static int countPositive(int[] values) {
    int count = 0;
    for (int value : values) {
        if (value > 0) {
            count++;
        }
    }
    return count;
}
```

If 99.9% of values are positive, the branch has a different distribution from 50/50 random data. The CPU and compiler can behave differently, even when the source **does not change**.

### "Just changing one comparison" does not prove branch misprediction

The compiler may use branchless operations, vectorize, or swap branch order. In practice:

1. Ensure both versions process **the same inputs and the same semantic workload**.
2. Profile with JFR/async-profiler/perf (if permitted), comparing CPU hotspots/counters.
3. Inspect compiled code if needed to distinguish branch / conditional move / vector instructions.
4. Measure after sufficient warm-up and across multiple runs.

**Do not use a rule-of-thumb table like "if/else is always slower than ternary"**; HotSpot decides codegen, and the CPU predictor decides the cost based on the data pattern.

## 11. Cache locality and data structures

Changing `int[]` to `List<Integer>` may look like editing just a signature, yet it affects all of:

- Whether elements are stored directly or via object references.
- Boxing/unboxing (which may be optimized on some paths but should not be assumed).
- Memory footprint / header / padding of boxed values.
- Object graph and GC scanning.
- CPU cache misses, prefetching, and pointer chasing.
- Allocation rate and retained heap.

Conceptual example:

```java
int[] numbers = new int[1000];
java.util.List<Integer> boxed = new java.util.ArrayList<>();

for (int i = 0; i < numbers.length; i++) {
    numbers[i] = i;
    boxed.add(i);
}
```

This is a snippet inside a method. `boxed` holds references to `Integer` objects; there may be a boxing cache for some values, but one must not infer that every element creates a separate object or that `boxed` is always slower in every operation.

### A small edit changes the allocation pattern

In a hot loop, replacing `new StringBuilder()` per iteration with a reused instance can reduce allocations; however, if the instance is long-lived and held across threads/shared state, it can increase footprint, contention, or introduce bugs. You must evaluate **ownership and thread safety**, not just the number of `new` calls.

## 12. `volatile`, synchronization, and lock elision

A normal field and a `volatile` field have different Java Memory Model semantics. Changing the declaration:

```java
int counter;
```

to:

```java
volatile int counter;
```

can affect memory ordering, CPU cache coherence, and the compiler's opportunities to optimize reads/writes. However, **you should not remove `volatile` just because a benchmark is slow**: if multiple threads need visibility/happens-before, that is a correctness requirement.

**Important point:** `volatile++` is **not atomic** when multiple threads update concurrently; the read-modify-write operation can still lose updates. If an atomic increment is needed, use `AtomicInteger.incrementAndGet()` or appropriate synchronization.

### Lock elimination

If the compiler proves an object does not escape and synchronization on the object cannot affect other threads, HotSpot can perform appropriate lock elision. However, a refactor that puts the object into a static shared field/collection can lose that proof, making synchronization genuinely expensive.

**Do not quantify in advance** "synchronized adds exactly X ns"; contention, biased/modern locking implementation, monitor inflation, safepoints, and JVM release all have an effect.

## 13. GC, allocation, and safepoints amplify differences

A small increase in allocation per request sometimes changes speed significantly because it:

- Increases Eden/TLAB refill rate.
- Causes Young GC to occur more frequently.
- Increases promotion pressure, straining the old generation.
- Adds more references in the object graph, increasing tracing work.
- Causes safepoint pauses to hit request latency.
- Causes GC threads' CPU usage to compete with application/JIT threads.

For example, if a refactor creates 50,000 temporary objects per request and the load is 100 requests/second, allocations increase with the workload: **5 million objects/second** from that source alone, before counting other allocations. This is a conditional multiplication, **not automatic proof of how many times GC pause increases**, because object sizes/lifetimes/collector/JIT can differ.

### Do not guess GC as the cause from a single measurement

A run showing "version A 20 ms, version B 50 ms" might only differ in GC timing. Multiple iterations/forks and GC logs are needed to distinguish:

- Actual code execution time.
- GC pauses occurring during measurement.
- JIT compilation during measurement.
- Allocation pressure / heap state.
- OS scheduling, CPU frequency, and thermal throttling.

**Lower heap used** also does not automatically mean higher end-to-end throughput: different collectors may retain committed memory for later use, and RSS is not identical to live-set.

## 14. Code cache and compilation budget

HotSpot generates C1/C2 machine code in the **code cache** (native executable memory), separate from the Java heap. A small source change can:

- Cause the JIT to inline more or fewer methods.
- Produce larger or smaller nmethods.
- Change the number of compiled variants and OSR entries.
- Increase compilation CPU/time.
- Change pressure on profiled/non-profiled code heaps.
- In extreme cases, contribute to filling the code cache and restricting compilation.

**More C2 compilation is not always better**: increased code size can cause instruction-cache misses or compilation overhead greater than the runtime benefit.

If the code cache is full, the JVM may print a related warning:

```text
CodeCache is full. Compiler has been disabled.
```

This is a **pattern you may encounter**, not a guaranteed log. To verify, you need to check `Compiler.codecache`, flags, and compilation logs rather than relying on a single low-throughput symptom.

## 15. Runnable Java 17+ example: same logical result, different optimization opportunities

Create the file **`HotSpotSmallChangeDemo.java`**:

```java
public class HotSpotSmallChangeDemo {
    interface Operation {
        int apply(int x);
    }

    static final class AddOne implements Operation {
        @Override
        public int apply(int x) {
            return x + 1;
        }
    }

    static final class TimesTwo implements Operation {
        @Override
        public int apply(int x) {
            return x * 2;
        }
    }

    static final class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }

        int score() {
            return x + y;
        }
    }

    // Keeps the object reference outside the local scope.
    static volatile Point published;

    static int call(Operation operation, int value) {
        return operation.apply(value);
    }

    static long monomorphic(int count) {
        Operation add = new AddOne();
        long sum = 0;

        for (int i = 0; i < count; i++) {
            sum += call(add, i % 10);
        }
        return sum;
    }

    static long polymorphic(int count) {
        Operation add = new AddOne();
        Operation times = new TimesTwo();
        long sum = 0;

        for (int i = 0; i < count; i++) {
            Operation target = (i & 1) == 0 ? add : times;
            sum += call(target, i % 10);
        }
        return sum;
    }

    static long localPoints(int count) {
        long sum = 0;

        for (int i = 0; i < count; i++) {
            int value = i % 7;
            Point point = new Point(value, value * 2);
            sum += point.score();
        }
        return sum;
    }

    static long publishedPoints(int count) {
        long sum = 0;

        for (int i = 0; i < count; i++) {
            int value = i % 7;
            Point point = new Point(value, value * 2);
            published = point;
            sum += point.score();
        }
        return sum;
    }

    public static void main(String[] args) {
        long mono = monomorphic(100_000);
        long poly = polymorphic(100_000);
        long local = localPoints(70_000);
        long escaped = publishedPoints(70_000);

        System.out.println("monomorphic: " + mono);
        System.out.println("polymorphic: " + poly);
        System.out.println("local points: " + local);
        System.out.println("published points: " + escaped);
        System.out.println("equal point results: " + (local == escaped));
        System.out.println("last published x: " + published.x);
    }
}
```

### Compile and run

```bash
javac -encoding UTF-8 HotSpotSmallChangeDemo.java
java HotSpotSmallChangeDemo
```

**Deterministic standard output, without compiler/GC logging enabled:**

```text
monomorphic: 550000
polymorphic: 750000
local points: 630000
published points: 630000
equal point results: true
last published x: 6
```

**Why the numbers are correct:**

- `i % 10` cycles through 0..9, summing to 45; `AddOne` adds 1 each time, so one cycle sums to 55. There are 10,000 cycles: `55 × 10,000 = 550000`.
- In `polymorphic`, even indices have inputs 0,2,4,6,8, `AddOne` produces sum 1+3+5+7+9 = **25** per cycle. Odd indices have inputs 1,3,5,7,9; `TimesTwo` produces sum 2+6+10+14+18 = **50**. Total per cycle is 75, repeated 10,000 times: **750000**.
- `Point(value, value * 2)` gives `score = 3 × value`. For value 0..6, one cycle sum = `3 × 21 = 63`. There are 10,000 cycles: **630000** in both local and published versions.
- On the last iteration `i = 69999`, `i % 7 = 6`, so `published.x` is **6**.

### What does this demo prove?

1. Runtime dispatch selects the right method when the call site receives one or two implementation types.
2. Two bodies differ in object publication while keeping **the same arithmetic result** for the input sequence.
3. Writing a reference to a `volatile` field has observable semantics; the local path does not automatically force the object to escape.
4. Correct output can be verified on Java 17+ independently of JIT policy.

### What does the demo NOT prove?

- **Does not prove** the monomorphic path is definitely faster than the polymorphic path: the two operations in the example also perform different arithmetic, so total time cannot be used to isolate dispatch cost.
- **Does not prove** `localPoints` never allocates: it still depends on the JIT, inlining/EA, and runtime version.
- **Does not prove** `publishedPoints` definitely causes N GC collections: timing and heap ergonomics are not deterministic.
- **Does not prove** adding 1 line changes speed by X times: to draw performance conclusions, you need a benchmark that isolates workload and measurement conditions.
- **Does not prove** the JIT must compile `call` at level 4: the code may remain in the interpreter/C1 or be inlined into the caller.

**This is a correctness test and an explanation of optimization opportunities, not a proper microbenchmark.**

## 16. Observing JIT behavior with the same program

On HotSpot JDK 17+:

```bash
java -XX:+PrintCompilation HotSpotSmallChangeDemo
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintCompilation -XX:+PrintInlining HotSpotSmallChangeDemo
```

You may also see compiler activity for the Java standard library; logging may interleave with output from `System.out.println`. Look for method names such as:

```text
HotSpotSmallChangeDemo::call
HotSpotSmallChangeDemo::localPoints
HotSpotSmallChangeDemo::publishedPoints
HotSpotSmallChangeDemo$Point::score
```

These are **suggested names to filter logs**, not a guarantee that all four are compiled or that the name format is identical across all JDKs/vendors.

### Indicators to distinguish

| Indicator | Correct interpretation |
| --- | --- |
| New Compile ID for a method | HotSpot recorded a compilation event according to the JVM format |
| Level 3/4 | Tiered compilation policy placed the method at the appropriate level |
| `inline (hot)` | A compilation context chose to inline the target |
| `virtual call` | In that context it may not have been inlined / general dispatch is still needed |
| `made not entrant` | A compiled version no longer accepts new entries |
| `%` mark on a compilation event | Usually indicates OSR compilation |
| Method not shown | Does not necessarily mean the method was not optimized; it may have been inlined into the caller, not yet hot, or logs did not appear as expected |

**Do not conclude DCE/EA/vectorization solely from `PrintCompilation`:** this tool reports compilation events and does not prove which machine instructions still exist.

### Running different JIT modes

```bash
java -Xint HotSpotSmallChangeDemo
java -XX:TieredStopAtLevel=1 HotSpotSmallChangeDemo
java -XX:+PrintCompilation HotSpotSmallChangeDemo
java -XX:-TieredCompilation HotSpotSmallChangeDemo
```

If the binary supports these HotSpot flags, **computed stdout must still remain the same**. However, execution mode, compile activity, and timing may differ. **`-XX:-TieredCompilation` does not mean `-Xint`**: it changes the policy rather than disabling the JIT completely.

### Inspecting bytecode, not confusing it with machine code

```bash
javap -c -p HotSpotSmallChangeDemo
```

`javap` reads bytecode in the class file: `invokeinterface`, `new`, `getfield`, `putstatic`, etc. can still be seen even if compiled machine code has inlined or scalar-replaced them. Do not use the presence of a `new` opcode as proof that physical allocation definitely occurs during optimized execution.

## 17. How to design a real benchmark with JMH

**Java Microbenchmark Harness (JMH)** is an OpenJDK project designed to run and analyze nano/micro/milli benchmarks, helping control warm-up, forks, iterations, and common JIT pitfalls. However, a benchmark using JMH **can still be wrong** if it compares two workloads with different meanings or if the JIT optimizes away the work intended to be measured.

### Setting up the project

The recommended approach is to use the **official JMH Maven archetype**, configuring the dependency and annotation processor for the JMH version you choose. Check the project README to get the **latest archetype version actually available in your build environment**, avoiding guessing versions:

- https://github.com/openjdk/jmh
- https://github.com/openjdk/jmh/tree/master/jmh-samples

After creating a standard JMH project (which already has a valid `pom.xml`), add the following class to the appropriate source package.

### JMH example: separating benchmark methods

Create `DispatchBench.java` in package `org.sample` of the configured JMH project:

```java
package org.sample;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Fork;
import org.openjdk.jmh.annotations.Measurement;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.annotations.Warmup;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 3, time = 1)
@Measurement(iterations = 5, time = 1)
@Fork(2)
public class DispatchBench {
    interface Op {
        int apply(int x);
    }

    static final class AddOne implements Op {
        public int apply(int x) {
            return x + 1;
        }
    }

    static final class TimesTwo implements Op {
        public int apply(int x) {
            return x * 2;
        }
    }

    private Op first;
    private Op second;
    private int counter;

    @Setup
    public void setup() {
        first = new AddOne();
        second = new TimesTwo();
        counter = 0;
    }

    private static int call(Op op, int value) {
        return op.apply(value);
    }

    @Benchmark
    public int oneReceiverType() {
        int x = counter++;
        return call(first, x & 31);
    }

    @Benchmark
    public int alternatingTypes() {
        int x = counter++;
        Op op = (x & 1) == 0 ? first : second;
        return call(op, x & 31);
    }
}
```

**The code above requires the JMH library** and a project with annotation processing; it **must not** be run with plain `javac DispatchBench.java` without dependencies. It is designed to be compiled in a Maven JMH archetype project.

Build/run in the JMH project:

```bash
mvn -q clean package
java -jar target/benchmarks.jar DispatchBench
```

**There is no fixed stdout in nanoseconds.** Results depend on CPU/JDK/GC/environment, harness forks, and optimizations in each benchmark. It should only be used as a starting point to **observe behavior**, not yet sufficient to prove the isolated cost of interface dispatch.

### Important limitation of this benchmark example

The two different methods do not perform the same operation per iteration: `alternatingTypes` has receiver selection and sometimes multiplication instead of addition. Therefore, if the timing results differ, **you cannot yet attribute the entire difference to devirtualization**.

To isolate the hypothesis, you need to design controls with the same operations, inspect profiles/compiled code, and change only one factor; for example, two implementations with the **same math** but different concrete classes, then benchmark target selection overhead independently. Even then, there are still effects from branch selection, class loading, and JIT inlining context.

### Important JMH principles

- **`@State`:** carries runtime inputs instead of letting everything become compile-time constants.
- **`@Benchmark` returns a result:** the harness consumes it to reduce DCE risk.
- **`@Warmup`:** gives the compiler time to profile/compile; the number of iterations must fit the workload.
- **`@Fork`:** separates JVM processes, avoiding compiled state contamination between cases.
- **`@Measurement`:** measures multiple iterations after warm-up, reporting distribution/error.
- **`@Param`:** useful for testing multiple input distributions, but does not automatically solve every alias/profile issue.
- **`Blackhole`:** use when needing to consume multiple outputs; do not overuse inside inner loops if its own overhead skews the result.
- **Test setup:** avoid object creation/file I/O inside `@Benchmark` if the goal is only to measure pure computation and setup can be validly separated.

**Do not use a "faster is better" benchmark if optimization eliminates work so the two versions no longer have the same semantics**. Always have an independent correctness oracle.

## 18. A/B methodology to find the real cause

When changing a few lines causes a large timing shift, follow this sequence:

### Step 1 — Lock down the metric

Are you measuring **startup**, **time to first request**, **steady-state throughput**, **allocation rate**, **GC pause p99**, **request latency p99**, or **CPU cycles on the hot path**? The same code can be good on one metric and poor on another.

### Step 2 — Keep conditions stable

- Same **JDK vendor, build, JVM flags, garbage collector**.
- Same OS, CPU architecture, core availability, power plan/frequency, container CPU/memory limits.
- Same input data and receiver type distribution.
- Same heap, cache warm state, and resource limits when appropriate.
- Same concurrency/thread count selection criteria.
- Measure across multiple runs/forks, looking at variability/error bars rather than just the best value.

### Step 3 — Verify result correctness

Both versions must have the same **semantics and side effects** under business requirements. Equal arithmetic results are not enough if the new version removed logging, locking, I/O, or necessary error handling.

### Step 4 — Check codegen/JIT evidence

Use compilation/inlining logs, JFR, perf profiler, or assembly (when available) to check:

- Do the methods reach the same compilation level?
- Does the inlining tree differ?
- Are there deopts/uncommon traps or class hierarchy invalidations?
- Does escape analysis/scalar replacement make a difference?
- Do allocation counts, GC cycles, or code cache growth differ?
- Do branch/cache misses differ when the profiler supports them?

### Step 5 — Verify the hypothesis with small transformations

For example, if you suspect lost inlining, inspect the bytecode body with `javap -c`, inlining logs, then split out a small change to isolate it. If you suspect escape, use an allocation profiler and local vs published cases. If you suspect cache locality, change container/data layout with the same workload.

**Avoid "shotgun tuning"**—changing 10 flags simultaneously and then not knowing what made the difference.

### Step 6 — Evaluate under representative load

A 25% win in a microbenchmark is not enough to prove service throughput will increase by 25%. When most of the time is spent waiting on I/O, database, lock contention, or GC, optimizing one method may not affect the end-to-end goal.

## 19. Tools by cause category

| Need to verify | Tool/method | Caution |
| --- | --- | --- |
| How source changes bytecode | `javap -c -p`, `javap -v` | Does not reflect JIT-compiled native code |
| Which level a method is compiled at | `-XX:+PrintCompilation` | Logs vary by JVM/run |
| Whether caller/callee inline | `-XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining` | Inlining context and formatting are complex |
| Need JIT details | `-XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation` | Can generate large logs |
| Actual machine code | `PrintAssembly` with matching `hsdis` binary, JIT analyzers | Absence of hsdis does not mean JIT is not running |
| Allocation pressure | JFR allocation events, async-profiler, GC logs | Sampling/overhead and attribution must be checked |
| GC pause/throughput | `-Xlog:gc*`, JFR, production telemetry | Do not confuse GC duration with end-to-end latency |
| Code cache/queues | `jcmd PID Compiler.codecache`, `Compiler.queue` | Real PID, tool availability |
| CPU hot paths | JFR, async-profiler, or OS perf tools | May require special privileges |
| Microbenchmark | JMH warm-up/forks/Blackhole | A good harness does not fix flawed benchmark design |
| Retaining paths | Heap dump + dominator analysis | Live set differs from allocation rate |
| Hardware memory/cache | Hardware PMU counters when permitted | CPU/OS-specific and prone to noise |

Some HotSpot JDK 17 diagnostics:

```bash
java -XX:+PrintCompilation HotSpotSmallChangeDemo
java -XX:+UnlockDiagnosticVMOptions -XX:+PrintInlining HotSpotSmallChangeDemo
java -Xlog:gc*:info HotSpotSmallChangeDemo
jcmd -l
jcmd PID Compiler.queue
jcmd PID Compiler.codecache
```

**Replace `PID` with the actual process ID** of a running JVM. A short demo may exit before `jcmd` attaches. These commands/JVM flags may differ between vendors/builds and must not be copied blindly to OpenJ9 or Native Image.

### Diagnostic flags can change the measurement itself

Enabling `PrintInlining`, `LogCompilation`, heavy JFR events, or profiler instrumentation can add overhead and alter timing. Use them to **explain** compiler decisions; do not use timings from a run with heavy logging to conclude production speed.

## 20. "Small change, large difference" can also be statistics

Suppose you measure two versions:

```text
Run 1: A=18 ms, B=26 ms
Run 2: A=22 ms, B=17 ms
Run 3: A=20 ms, B=19 ms
```

These are **hypothetical numbers for reasoning practice**, not a real benchmark result. If you only take Run 1, the reader sees B is 44% slower and easily draws the wrong conclusion. Yet later runs reverse the order, showing the environment or JVM state is noisy.

When analyzing, you must report:

- Number of forks/iterations, warm-up and measurement duration.
- Center estimates (mean/median) along with variability/error bars.
- Distribution/percentiles if measuring latency.
- Input distributions and CPU/runtime configuration.
- Whether there are outliers, GC events, compiler transitions, or OS interference.
- Impact on resource footprint and semantics.

**Do not cherry-pick** the best-looking run, and do not use a single microbenchmark median to promise that p99 request latency will match.

### Amdahl's Law: optimizing a hot path may not change total throughput much

If a method accounts for only 1% of total request time, making that method 10x faster can only yield a small improvement in end-to-end time (ignoring other system interactions). Conversely, a change that causes leaks/GC pauses can make p99 spike even if average CPU on the hot method only shifts slightly.

**Measure the real bottleneck** before editing source to make the JIT "happier".

## 21. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Fewer lines of code is definitely faster." | Bytecode, JIT, allocations, and the CPU path are what decide |
| "Same algorithm means same performance." | Data layout, profiling, cache, and compiler differ |
| "`javap` showing `new` means the object is definitely physically allocated." | The JIT can scalar-replace it if eligible |
| "Adding an `if` always slows code down." | The branch can be folded, predicted, hoisted, or optimized |
| "`final` always makes methods faster." | It can create opportunities, but does not guarantee a win |
| "Interface calls must always do virtual dispatch." | The JIT can devirtualize/inline them |
| "Adding bytecode to a method always makes it lose inlining." | Thresholds are heuristic; logs and compile context are needed |
| "C1/C2 compiles a method right when called exactly N times." | Tiered policy/queues/counters are more complex |
| "OSR only appears after a method returns." | It can switch code inside a currently running loop |
| "A monomorphic profile will stay mono forever." | Traffic/class loading changes; guards/deopts exist |
| "A deopt is a JIT bug." | Speculation has a bailout mechanism to preserve semantics |
| "`volatile` is only a hint to the compiler." | It is a Java Memory Model constraint |
| "`volatile++` is already atomic." | No, increment consists of read-modify-write |
| "Disabling inlining means disabling the JIT." | No, they are different mechanisms |
| "`-XX:-TieredCompilation` = `-Xint`." | False, one changes policy, the other runs interpreter-only |
| "Nanosecond output in benchmarks must be fixed." | Timing depends on many runtime/OS/CPU factors |
| "Using `System.nanoTime()` automatically measures correctly." | It does not fix warm-up, DCE, and constant folding |
| "`Blackhole` guarantees a benchmark cannot be wrong." | Proper workload/methodology is still required |
| "GC pause is the entire service time." | It is one source of latency; correlate with traces |
| "With JIT logging enabled and the method missing, there must be no optimization." | It may be inlined into the caller, not yet hot, or use a different log format |
| "Microbenchmark 2x faster → service also 2x faster." | The end-to-end bottleneck may be elsewhere |
| "Changing Java source is the only cause." | CPU quota, heap, flags, thermals, and data may differ |

## 22. Exercises with answers

**Exercise 1.** A method only grows by a few bytecodes, yet a hot caller suddenly slows down. What JIT cause could there be?  
**Answer:** Losing an inlining decision, losing cross-method optimizations; verify with `PrintInlining` and a benchmark with sufficient warm-up.

**Exercise 2.** Why can a million-iteration loop with an unused result be "absurdly fast"?  
**Answer:** Dead-code elimination/constant folding can delete the work. Use JMH result consumption/Blackhole and runtime inputs.

**Exercise 3.** Changing `calculate(42)` to `calculate(dynamicValue)` increases execution time. Is the dynamic version definitely worse?  
**Answer:** No. The literal version can be constant-folded, so the two tests are not measuring the same work.

**Exercise 4.** An interface has 20 concrete classes, but at the call site only one type is received. Is the site megamorphic?  
**Answer:** No. The profile follows receiver types observed **at the call site**.

**Exercise 5.** A new type appears after warm-up; what impact can it have?  
**Answer:** Guard failure/fallback, deopt, or recompile; dynamic dispatch semantics must not be broken.

**Exercise 6.** Is C1 level 3 always faster than C1 level 2?  
**Answer:** No. Level 3 collects richer profiles and has instrumentation costs.

**Exercise 7.** Can a method called once with a very long loop be JIT-compiled?  
**Answer:** Yes, via OSR and backedge counters.

**Exercise 8.** Why can writing an object to a static volatile field increase allocation cost?  
**Answer:** It escapes the local scope, usually preventing scalar replacement and adding volatile semantics/write barrier.

**Exercise 9.** Does escape analysis mean every non-escaping object moves to the stack?  
**Answer:** No. HotSpot C2 has scalar replacement; do not describe it as general-purpose stack allocation.

**Exercise 10.** In the demo, what does `monomorphic(100000)` return?  
**Answer:** **550000**, each cycle 0..9 plus 1 sums to 55.

**Exercise 11.** In the demo, what does `polymorphic(100000)` return?  
**Answer:** **750000**, each cycle has even-plus-one sum 25 and odd-times-two sum 50.

**Exercise 12.** What number do the two Point variants in the demo return?  
**Answer:** Both **630000**, because the sum of 0..6 times 3 is 63, repeated for 10,000 cycles.

**Exercise 13.** Is changing `int` to `volatile int` just changing one word without affecting correctness?  
**Answer:** No. It changes memory-visibility/ordering semantics; both concurrency correctness and performance must be evaluated.

**Exercise 14.** Where can code accessing `int[]` and `List<Integer>` differ in memory behavior?  
**Answer:** Direct primitive storage versus boxing/references and backing arrays/objects, GC, and cache locality.

**Exercise 15.** Does the JIT not inlining a method make the program's logic wrong?  
**Answer:** No. The call mechanism differs, while semantics must remain unchanged.

**Exercise 16.** Can we assert a loop with an `if` is never vectorized?  
**Answer:** No. Compiler/CPU/version/data dependencies decide.

**Exercise 17.** Does a GC log appearing during a slow measurement prove the new code is worse?  
**Answer:** Not yet. Multiple runs and checks of allocation rate/live set/GC causality are needed.

**Exercise 18.** What is the use of `-Xint` in diagnostics?  
**Answer:** Comparing with an interpreter-only path for correctness/performance; it does not represent production JIT throughput.

**Exercise 19.** Why is `javap -c` not enough to confirm C2 vectorized a loop?  
**Answer:** It only prints JVM bytecode, not JIT-compiled machine code.

**Exercise 20.** Does a 20% microbenchmark win guarantee API p99 latency also improves by 20%?  
**Answer:** No. End-to-end includes I/O, queues, GC, locks, and other bottlenecks.

**Exercise 21.** Why fork the JVM when measuring with JMH?  
**Answer:** To reduce state contamination between benchmark runs, differing warm-up/compiler profiles/GC; proper input design is still needed.

**Exercise 22.** With a 200 ms startup target, should you warm up for 30 minutes and only measure steady-state?  
**Answer:** No. You must measure the real target, which is startup/time-to-ready, alongside steady-state if needed.

**Exercise 23.** `System.nanoTime()` returns very different results after enabling `PrintInlining`; what is the conclusion?  
**Answer:** Diagnostics have overhead and can alter scheduling. Do not use a logging-heavy run as a performance baseline.

**Exercise 24.** Should interfaces be changed to concrete classes before measuring to avoid virtual dispatch?  
**Answer:** Not by default; the JIT can devirtualize and OO design has value. Profile to prove the bottleneck before changing the API.

## 23. Practical checklist before trusting a large "speedup"

- [ ] Are the **functional results and side effects** the same?
- [ ] Are you measuring **startup, warm-up, steady-state, throughput, or latency**?
- [ ] Have JVM vendor, version, collector, flags, and CPU/memory constraints been kept identical?
- [ ] Are runtime inputs sufficiently varied, avoiding unintended constant folding?
- [ ] Is result consumption/Blackhole used to avoid DCE?
- [ ] Are warm-up/forks/measurement iterations sufficient, and are error margins reported?
- [ ] Were JIT compilation levels, `PrintInlining`, and deopts checked when needed?
- [ ] Was interface-call cost distinguished from operation/branch cost?
- [ ] Were allocation profiler/GC logs checked if the code creates many objects?
- [ ] Was an escape analysis opportunity distinguished from a measured physical allocation?
- [ ] Were vectorization/aliasing/CPU instruction availability considered?
- [ ] Were concurrency semantics checked when adding/removing `volatile` or locks?
- [ ] Were the workload's input distribution/receiver types recorded?
- [ ] Was the benchmark run on the same machine/power/CPU throttling conditions?
- [ ] Were logging/profiling runs separated from timing baselines?
- [ ] Was end-to-end impact measured after the microbenchmark?
- [ ] Was confidence/variance analyzed instead of just comparing two numbers?
- [ ] Was experimental rationale documented before changing production JIT flags?

## 24. Summary

**A small change in Java source does not mean a small change at runtime.** HotSpot is a workload-adaptive compiler, so a small diff can change **when a method is compiled, the call site profile, inlining eligibility, escape, constant folding, dead-code elimination, vectorization, branch prediction, code cache, and GC behavior**. Many optimizations interact in a chain, so speed can change in **step jumps** rather than proportionally to diff length.

At the same time, a benchmark can "get faster" simply because it **no longer performs the work being measured**. A large speed result is only meaningful after verifying **the same semantics, the same workload, an equivalent JIT phase, and controlled system conditions**.

### References

- **OpenJDK Java Microbenchmark Harness (JMH)** — how to build and run JVM benchmarks: https://github.com/openjdk/jmh
- **OpenJDK JMH Sample 08 — Dead Code Elimination:** https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java
- **OpenJDK JMH Sample 10 — Constant Folding:** https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java
- **Oracle JDK 17 — The java Command** (TieredCompilation, PrintCompilation, PrintInlining, Inline, Code Cache): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK — HotSpot Escape Analysis and Scalar Replacement Status:** https://cr.openjdk.org/~cslucas/escape-analysis/EscapeAnalysis.html
- **OpenJDK — JEP 197 Segmented Code Cache:** https://openjdk.org/jeps/197
- **Oracle JDK 17 — HotSpot GC Tuning Guide:** https://docs.oracle.com/en/java/javase/17/gctuning/
- **OpenJDK JMH Blackhole source:** https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/infra/Blackhole.java

**Final takeaway:** a large regression or speedup after a short refactor **is a signal to investigate the mechanism, not proof that shorter code or a specific keyword is faster**. Use JMH and appropriate JIT/GC tools to inspect what the JVM actually did, then evaluate the result across the entire application.