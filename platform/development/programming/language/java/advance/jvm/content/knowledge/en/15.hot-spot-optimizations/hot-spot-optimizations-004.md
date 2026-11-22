# Loop Optimization and Redundant Check Elimination Under Appropriate Conditions

## 1. The problem: Java must be safe, but does not necessarily re-check the same thing on every iteration

Loops over arrays are among the most frequently executed pieces of code in Java. At the semantic level, each access `a[i]` must obey the rules **must not read a null array** and **the index must be within `[0, a.length)`**. If violated, the program must exhibit the appropriate exception (`NullPointerException` or `ArrayIndexOutOfBoundsException`) according to Java behavior. However, if the compiler can **prove** a set of checks is redundant, it may omit performing all of those checks in the optimized machine code.

Example:

~~~java
static long sum(int[] a) {
    long result = 0;
    for (int i = 0; i < a.length; i++) {
        result += a[i];
    }
    return result;
}
~~~

This is an **illustrative method snippet**, without `main`. Logically:

- `i` starts at `0`.
- The continuation condition `i < a.length` provides the upper bound of the index.
- `i` increments by exactly one unit.
- The length of **an array object** does not change during the lifetime of the array.
- If `a` is `null`, obtaining `a.length` must still fail according to Java rules.

A qualifying HotSpot **C2** can leverage this shape to reduce or eliminate **array bounds checks** in the body of an execution path that has been proven safe. This is a classic example of **Range Check Elimination (RCE)** — eliminating array bounds checks based on index range analysis.

**Important to remember:** optimization is a prerogative of the JVM implementation, **not a Java language promise**. Bytecode still usually has `iaload`/`iastore`; the JVM must preserve **observable behavior** such as values, exceptions, side effects, and valid ordering. `javap` shows bytecode, **not proof** that native code still contains every check before reading the array.

## 2. Which checks commonly appear on the hot path?

| Check / condition | Why is it there? | When can it be optimized? |
| --- | --- | --- |
| **Null check** on array/object | `a.length`, `a[i]`, method call on null must follow NPE semantics | When non-null has been proven, or the JVM uses a valid implicit null check |
| **Array bounds check** | `i` must belong to `[0, a.length)` | When the compiler proves the entire loop range is valid or generates an appropriate guard/slow path |
| **Loop termination check** | Determines whether more iterations remain | Frequency can be reduced via unrolling or counted-loop handling |
| **Loop-invariant branch** | For example `if (enabled)` unchanged across iterations | Hoist or **loop unswitching** if useful and valid |
| **Repeated arithmetic** | For example computing an expression depending only on invariant data | Loop-invariant code motion, common subexpression elimination |
| **Type/subtype check** | Polymorphism, array store check for reference arrays | May be omitted if type information/proofs are strong enough |
| **Synchronization and memory effects** | Java Memory Model and shared state across threads | Must not be moved against semantics; `volatile`/locks are real constraints |

Not every check is an optimization candidate. A `getInt` operation on a buffer, a `List.get(i)` on a resizable list, a method call with side effects, or an index computed through overflow may require completely different analysis from a basic array counted-loop.

### "Eliminating checks" does not mean turning off safety

Correct optimization must ensure **all valid and invalid inputs** still behave according to the Java contract. Code running fast on valid inputs does not allow the JVM to arbitrarily read `a[-1]` or `a[a.length]`. If the compiler chooses a **fast path** with fewer checks, it must prove that path is safe or preserve **guards, uncommon traps, deoptimization, and slow paths** when assumptions do not hold.

That is why RCE is not equivalent to manually writing native pointer arithmetic without bounds checking.

## 3. Counted loop: a shape easy for C2 to analyze

A **counted loop** has an induction variable, a starting point, a limit, a step increment/decrement, and an iteration count that the compiler can infer under appropriate conditions.

~~~java
for (int i = 0; i < n; i++) {
    use(i);
}
~~~

This snippet is illustrative only; `n` and `use` are defined elsewhere. In theory it is easy to reason about:

- `init = 0`
- `limit = n`
- `stride = +1`
- the index range is `0 .. n-1` when `n > 0`.

However, **seeing a `for` loop does not automatically mean the compiler has a complete counted loop**. Calls to `use`, `break`, `continue`, side effects, overflow, changing limits, nested loops, control-flow graph complexity, and practical profitability all matter.

Compare three shapes:

~~~java
// A: index follows array length; easy to prove.
for (int i = 0; i < a.length; i++) {
    total += a[i];
}

// B: bounds passed from outside; may need a guard.
for (int i = from; i < to; i++) {
    total += a[i];
}

// C: index depends on data values, hard to infer range.
for (int i = 0; i < positions.length; i++) {
    total += a[positions[i]];
}
~~~

The snippets above are illustrative within a method having `a`, `positions`, `total`, `from`, `to`. For A, proving `0 ≤ i < a.length` is straightforward. For B, without guaranteeing `from ≥ 0` and `to ≤ a.length`, the JVM must preserve error behavior when the range actually exceeds the array. For C, the compiler cannot infer that every element `positions[i]` is valid solely from `i < positions.length`; the check on `a[positions[i]]` usually remains important.

**Key condition:** the value range of the **actual index expression** must be proven to lie within the valid range of the **actual array being accessed**.

## 4. What is the idea behind Range Check Elimination (RCE)?

One way to reason at a high level:

1. Identify the induction variable and iteration range.
2. Collect the array accesses, e.g. `a[i]`, `a[i+1]`, `b[2*i]`.
3. Derive the **conditions** for all indices to be valid for the optimizable portion of the loop.
4. Prove those conditions from loop bounds/array lengths or place **guards** protecting the fast path.
5. Move/eliminate repeated checks on the path proven safe.
6. Keep a slow path, pre/post loop, traps, or deoptimization if the general path does not satisfy the proof.

Conceptual diagram:

~~~text
Original loop
  each iteration: test loop limit, access a[i] → runtime bounds semantics
                          |
                          v
C2 analyzes induction variable and array length
                          |
               is index range guaranteed valid?
                   /                   \
                 Yes                  Not proven
                 |                          |
       Optimized path can              Keep checks, create guards,
       omit check in body              split loop, or fallback
                          |
             Both must have the same Java semantics
~~~

**RCE is a capability of C2 optimization, not a claim that the JVM always deletes exactly N instructions.** HotSpot has multiple interacting passes: loop optimization, loop predication, range-check analysis, IGVN, inlining, alias analysis, unrolling, and backend instruction selection.

### 4.1. With a fixed array length, what is truly "invariant"?

`a.length` does not change for a given array object. However, **the reference variable `a` may be reassigned in code**, or a field holding an array may be modified by other code. The compiler must not arbitrarily hoist the length check of **object A** and use it as if it were always the length of **object B**.

~~~java
for (int i = 0; i < holder.values.length; i++) {
    consume(holder.values[i]);
}
~~~

Here `holder.values` is a field, and `consume` is an illustrative method. If the object field can change between reads, turning it into a local snapshot **can change semantics**, especially under concurrency or side effects. C2 may only eliminate loads/checks for which it has sufficient proof regarding memory effects and aliasing under the Java Memory Model.

For APIs that allow a snapshot, the programmer can intentionally write:

~~~java
int[] local = holder.values;
for (int i = 0; i < local.length; i++) {
    consume(local[i]);
}
~~~

This is a **different semantic design**: intentionally fixing the reference for the entire loop. Do not say the two snippets are always equivalent if `holder.values` can be modified.

### 4.2. With external bounds, where is the proof placed?

Suppose:

~~~java
static long sumRange(int[] a, int from, int to) {
    long sum = 0;
    for (int i = from; i < to; i++) {
        sum += a[i];
    }
    return sum;
}
~~~

It cannot be assumed that `from` and `to` are always valid. If `from = -2` or `to > a.length`, at least one iteration may access an out-of-bounds index and must obey the corresponding AIOOBE. HotSpot may find a common-case path with guarded conditions, but it does not simply drop checks for all inputs.

Therefore, if the **API contract** clearly defines the valid range, express it clearly and validate at the boundary. However, see section 8: adding explicit validation **can change exceptions and the order of side effects** compared to the original version.

## 5. Loop predication: moving conditions before the loop

**Loop predication** is a HotSpot C2 technique that can create a **predicate/guard** at the loop entry, instead of keeping the same invariant check in every iteration. The idea observed from OpenJDK documentation: for affine indices like `i * scale + offset`, conditions on start, limit, stride, and array length can be formed to safely select the optimized path.

A conceptual illustration:

~~~text
Input: a, from, to

If the body's index range is proven to be within [0, a.length):
    Fast loop: proceed with fewer range checks in the body
Otherwise:
    Fallback preserving semantics, possibly using trap/deoptimization or slow loop
~~~

This pseudo-code only explains the idea; it is **not** Java code that can be used to implement RCE manually.

### Speculative guard and uncommon trap

The JIT can specialize native code for observed profiles: for example, hot calls usually have `from=0` and `to=a.length`. A predicate can guard the assumption about the index range; if the condition no longer holds, the JVM must retain the ability to execute general code, possibly falling back to the interpreter or another compiler tier via **deoptimization**.

**Do not think "deoptimization is a bug."** It is the mechanism that allows speculative optimization to still preserve Java semantics when the profile changes.

**Not every guard failure needs to create a Java exception immediately at the guard.** The JVM can transition to the general execution path and then perform operations in source order to determine whether an actual exception occurs.

### Avoid confusing guards with manual validation

A **compiler guard** is an internal optimization step and must preserve the program's observable behavior. **Manual validation** added by the programmer can intentionally change the API contract; that is a source-level change.

Therefore, the statement "move all array bounds checks to the beginning of the method" is **not automatically valid** if the source has I/O, side effects, `break`, or only part of the loop might execute.

## 6. Loop peeling, pre/main/post, and index boundaries

A loop may have a start/end region where safety is hard to guarantee for every iteration, while a middle region is definitely valid. The JVM can **peel/split** loops:

~~~text
Source:
 for i = begin ... end:
    use(a[i + 1])

A possible native organization:
 [pre-loop]      handles first few iterations / necessary checks
 [main-loop]     range proven safe, checks reduced
 [post-loop]     handles remainder / tail with necessary checks
~~~

This is a diagram, **not a guarantee** that C2 will always generate exactly three loops. Splitting a loop increases code size and adds branch/guard overhead; for very short loops, that optimization may **not be worthwhile**.

For example, index `i + 1` requires proving `0 ≤ i + 1 < a.length`. Simply having `i < a.length` true is **not sufficient** to prove `i+1` is valid on the last iteration. Learners need to look at the **index expression**, not just the loop condition.

Case with two arrays:

~~~java
for (int i = 0; i < a.length; i++) {
    sum += a[i] + b[i];
}
~~~

`a[i]` is bounded by `a.length`; whereas `b[i]` is only valid on every iteration if `b` is long enough. Additional safety conditions may be `b != null` and `b.length >= a.length`. The JVM must not silently omit the check on `b[i]` when `b` is shorter.

## 7. Other loop transformations that often accompany RCE

### 7.1. Loop-invariant code motion — LICM

An expression that depends only on data invariant throughout the loop, and has no side effects or exception/memory ordering constraints to preserve, can be moved outside the loop.

~~~java
int scale = config.scale();
for (int i = 0; i < a.length; i++) {
    result += a[i] * scale;
}
~~~

This snippet intentionally calls `config.scale()` **before the loop**. If the original source called `config.scale()` **inside the loop**, moving the call outside is only valid if the call has no side effects, does not change its value, and changing the number/timing of calls does not alter semantics. With `volatile`, locks, I/O, or stateful methods, it must not be arbitrarily hoisted.

**LICM reduces repeated work when safe**, but sometimes increases register pressure or executes a computation before the loop even when the loop has zero iterations; the compiler must weigh validity and profitability.

### 7.2. Loop unswitching

If there is a branch that **does not change across iterations**:

~~~java
for (int i = 0; i < a.length; i++) {
    if (enabled) {
        sum += a[i];
    }
}
~~~

C2 can create two versions of the loop:

~~~text
if (enabled):
    for (...) sum += a[i]
else:
    for (...) [other body or no sum update]
~~~

The idea: check `enabled` only once instead of on every iteration. However, duplication increases code size, which can impact the instruction cache. **There is no promise C2 will always unswitch**; the JIT uses a cost model/compile budget. If `enabled` is a value that can change per iteration (e.g. a `volatile` re-read), it must not be treated as unconditionally invariant.

### 7.3. Loop unrolling

Unrolling duplicates the body multiple times:

~~~text
Originally:
  for i: process(a[i])

After unroll 4:
  process a[i], a[i+1], a[i+2], a[i+3]
  then i += 4
  remainder uses tail path
~~~

Benefits can include lower branch overhead and more opportunities for instruction-level parallelism/RCE/vectorization. However, a larger body puts pressure on the code cache/instruction cache; very short loops or complex bodies may not benefit.

**The remainder must not be skipped:** if array length = 9 and unroll factor = 4, the program must still process all 9 elements (e.g. 4 + 4 + 1), not read up to the 12th element.

### 7.4. Auto-vectorization / SuperWord

Once C2 sees independent operations on adjacent elements, it may use SIMD instructions to process multiple data elements at once; HotSpot has **SuperWord** vectorization. Not every Java loop with an array gets vectorized.

Typical conditions/barriers:

- Regular/contiguous memory accesses with sufficiently clear dependencies.
- No aliasing that would cause incorrect read/write ordering.
- Operations whose semantics permit vectorization (mind floating point, strict ordering, overflow, and reductions).
- Hardware/CPU instruction set support and appropriate VM flags.
- No branch/call/exception ordering that would make the vectorized path incorrect.

**SIMD is not synonymous with the Java Vector API.** Auto-vectorization is a JIT optimization; the Java Vector API in Java 17 is an incubator module and is not a dependency of the code examples in this article.

### 7.5. Induction-variable simplification

C2 can canonicalize index expressions, eliminate computations derivable from the induction variable, and replace repeated multiplications with increments when semantically valid. However, with `int` arithmetic, Java overflow **wraps around modulo 2^32**, so loop logic must not be changed based solely on infinite-precision arithmetic intuition.

### 7.6. Common subexpression elimination

If two identical computations use unchanged operands, with no memory aliasing or side effects to account for, the compiler can reuse the result instead of recomputing it. For array loads, it must check **whether any store or call could modify the data between the two reads**.

## 8. Be careful: Java exceptions and side effects must not be arbitrarily reordered

Consider an illustrative method:

~~~java
static int useRange(int[] a, int from, int to) {
    int sum = 0;
    for (int i = from; i < to; i++) {
        System.out.println("VISITED=" + i);
        sum += a[i];
    }
    return sum;
}
~~~

If `a.length=3`, `from=1`, `to=5`, the source will print `VISITED=1`, `VISITED=2`, and `VISITED=3` before accessing `a[3]` throws `ArrayIndexOutOfBoundsException`. If the programmer moves **all validation** to the top of the method and throws immediately when `to > a.length`, those `println` outputs before the error will disappear.

This is a **change in observable behavior**. C2 must also not optimize away side effects that must occur before an exception under Java semantics.

Another completely valid way to design an API:

~~~java
Objects.checkFromToIndex(from, to, a.length);
for (int i = from; i < to; i++) {
    process(a[i]);
}
~~~

However, **that is a new API contract with upfront checking**, not automatically equivalent to all legacy code, especially when the loop has zero iterations or when there are side effects/exception ordering. `Objects.checkFromToIndex` is a Java 9+ API and is usable on Java 17.

### The zero-iteration loop case

If:

~~~java
for (int i = 0; i < 0; i++) {
    sum += a[i];
}
~~~

The body does not run; if `a` is null, this loop **does not necessarily throw NPE** because there is no dereference inside the body. However, if changed to `Objects.requireNonNull(a);` before the loop, it will throw NPE immediately.

Conversely, the condition `i < a.length` **does dereference `a` when checking the condition**, even if the body does not run when length is 0. Each expression in the condition determines the semantics.

### Range check elimination does not allow "ignoring rare exceptions"

If an out-of-range index occurs in production, Java must continue throwing the right error when the code performs the invalid access. The JIT may use guards and fallbacks instead of keeping the check in the hot body, but **must not drop validation in an unsafe native style**.

## 9. Runnable Java 17 example: clear index ranges and deterministic output

Create file **`LoopOptimizationDemo.java`**:

~~~java
import java.util.Objects;

public final class LoopOptimizationDemo {
    static long sumRange(int[] values, int from, int to) {
        Objects.requireNonNull(values, "values");
        Objects.checkFromToIndex(from, to, values.length);
        long total = 0;
        for (int i = from; i < to; i++) {
            total += values[i];
        }
        return total;
    }

    static long sumIfEnabled(int[] values, boolean enabled) {
        long total = 0;
        for (int i = 0; i < values.length; i++) {
            if (enabled) {
                total += values[i];
            }
        }
        return total;
    }

    static long sumShifted(int[] values) {
        long total = 0;
        for (int i = 0; i + 1 < values.length; i++) {
            total += values[i + 1];
        }
        return total;
    }

    static int firstAtLeast(int[] values, int threshold) {
        for (int i = 0; i < values.length; i++) {
            if (values[i] >= threshold) {
                return i;
            }
        }
        return -1;
    }

    public static void main(String[] args) {
        int[] a = {3, 5, 7, 11, 13, 17};
        System.out.println("full=" + sumRange(a, 0, a.length));
        System.out.println("middle=" + sumRange(a, 1, 5));
        System.out.println("empty=" + sumRange(a, 4, 4));
        System.out.println("enabled=" + sumIfEnabled(a, true));
        System.out.println("disabled=" + sumIfEnabled(a, false));
        System.out.println("shifted=" + sumShifted(a));
        System.out.println("firstAtLeast12=" + firstAtLeast(a, 12));
        try {
            sumRange(a, 2, 7);
            System.out.println("unexpected");
        } catch (IndexOutOfBoundsException expected) {
            System.out.println("badRangeRejected=true");
        }
        try {
            sumRange(null, 0, 0);
            System.out.println("unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }
    }
}
~~~

Run with JDK 17+:

~~~bash
javac --release 17 LoopOptimizationDemo.java
java LoopOptimizationDemo
~~~

**Stdout compiled/run and verified on HotSpot/OpenJDK 24 with Java 17 target:**

~~~text
full=56
middle=36
empty=0
enabled=56
disabled=0
shifted=53
firstAtLeast12=4
badRangeRejected=true
nullRejected=true
~~~

### Scope-accurate analysis

- `sumRange`: `Objects.checkFromToIndex` checks the **range contract `[from,to)`** before the loop. Within the valid range, the counted-loop has clear bounds, making it favorable for the optimizer to infer `from ≤ i < to ≤ values.length`.
- `sumIfEnabled`: `enabled` is a parameter not reassigned in the method, so it is a loop-invariant candidate. C2 **may** unswitch or optimize the false path, but the output `enabled=56`/`disabled=0` **does not prove native code unswitched**.
- `sumShifted`: the condition `i+1 < values.length` protects the actual index `i+1`; the sum 53 is 56 minus the first element 3. Writing clear boundaries makes the code easy to review.
- `firstAtLeast`: has a `return` mid-loop. With threshold 12, the first matching element is 13 at index 4. Having an early exit may reduce opportunities for vectorization or certain loop transformations; do not claim C2 will refuse all optimizations.
- Invalid range is rejected before the loop by `Objects.checkFromToIndex`; the method throws an `IndexOutOfBoundsException` subtype, caught in main.
- `null` is rejected by `Objects.requireNonNull` even when `[from,to)` is empty. That is an explicit choice of this API, not the default behavior of every Java loop.

**Note:** the program only calls each method a few times, usually **not enough** for C2 to JIT-compile them. This output verifies **semantics**, not RCE throughput or proof of vector instructions.

## 10. Inspection and optimization operate at two different layers

### `javap` sees bytecode, not C2 native machine code

After compiling:

~~~bash
javap -classpath . -c -p LoopOptimizationDemo
~~~

You will typically see instructions such as `arraylength`, `iaload`, `iinc`, `if_icmpge`, `goto`, and calls to `Objects.checkFromToIndex` in the corresponding bytecode.

Logical example:

~~~text
arraylength   → get array length
if_icmpge     → branch when index exceeds loop limit
iaload        → read int element at index
iinc          → increment induction variable
goto          → loop backedge
~~~

`javap` does not tell you whether the C2 compiler has eliminated implicit bounds checks in **native code**. This is a common diagnostic mistake: seeing `iaload` in bytecode and concluding "every iteration still runs the exact same array bounds check" is an overreach.

### JIT code can change within the same JVM process

Initially a method is interpreted, then C1, then C2, or deoptimized/recompiled again. A benchmark that starts measuring from the very first call may include **compilation/profiling** in the runtime and yield different conclusions from steady state.

## 11. Runnable Java 17: creating a hot loop and viewing JIT compilation logs

Create file **`LoopWarmupProbe.java`**:

~~~java
public final class LoopWarmupProbe {
    private static volatile long published;

    static long sumArray(int[] values) {
        long sum = 0;
        for (int i = 0; i < values.length; i++) {
            sum += values[i];
        }
        return sum;
    }

    public static void main(String[] args) {
        int[] values = {3, 5, 7, 11, 13, 17};
        long checksum = 0;

        for (int k = 0; k < 100_000; k++) {
            checksum += sumArray(values);
        }

        published = checksum;
        System.out.println("rounds=100000");
        System.out.println("checksum=" + published);
    }
}
~~~

Compile:

~~~bash
javac --release 17 LoopWarmupProbe.java
~~~

Normal run:

~~~bash
java LoopWarmupProbe
~~~

**Fixed stdout:**

~~~text
rounds=100000
checksum=5600000
~~~

Since each round sums `3+5+7+11+13+17 = 56`, 100,000 rounds yield 5,600,000. The result was actually run on JDK 24 with Java 17 target.

Enable HotSpot diagnostic printing:

~~~bash
java -XX:+PrintCompilation LoopWarmupProbe
~~~

**An actual observation** when running on HotSpot 24 showed relevant compilation lines:

~~~text
LoopWarmupProbe::sumArray ... level 3
LoopWarmupProbe::sumArray ... level 4
LoopWarmupProbe::main ... OSR/normal compilation
~~~

The three lines above are a **summary of the meaning of the diagnostic output**, not a verbatim copy of the JVM format. Compilation IDs, timings, flags, and tier activity may differ on Java 17, OS, and across runs. In the test run, the JVM did record `sumArray` at compilation level 3 and then level 4; this proves it was **compiled**, **not proof** of specifically how many range checks were eliminated in native code.

### `-Xint` for semantics comparison

~~~bash
java -Xint LoopWarmupProbe
~~~

Interpreter-only still prints the **same** `rounds=100000` and `checksum=5600000`. This is a behavior check. **Do not turn a single `-Xint` vs. JIT run into a production-valid speedup conclusion**: timing requires warm-up/forks, multiple samples, and avoiding dead-code elimination.

### Do not equate `PrintCompilation` with `PrintInlining`

On HotSpot, `-XX:+PrintCompilation` reports compilation events, while `-XX:+PrintInlining` may require unlocking diagnostic options:

~~~bash
java -XX:+UnlockDiagnosticVMOptions \
     -XX:+PrintInlining -XX:+PrintCompilation \
     LoopWarmupProbe
~~~

This is Bash syntax. Logs can be large and create overhead. `PrintInlining` reports **inlining** decisions, **not** a complete, formal report that bounds-check elimination succeeded.

## 12. Proving native optimization is harder than looking at latency

There are different levels of evidence:

| Level | Evidence | What can be concluded? |
| --- | --- | --- |
| 1 | Code still returns right results under `java` or `java -Xint` | **Semantics** correct on tested inputs |
| 2 | `javap -c -p` shows `iaload`, loop branches | **Bytecode** has array operations; optimized native code unknown |
| 3 | `-XX:+PrintCompilation` shows C2 level 4 | Hot method has native compilation; specific RCE/LICM/unswitch unknown |
| 4 | JFR/method profiler shows time/counters changed | Observable performance difference; which transformation caused it unknown |
| 5 | C2 Ideal graph/assembly analysis (if tools and build support it) | Can inspect guards/checks/vector ops in a specific **compiled version** |
| 6 | Proper benchmark with multiple forks/inputs and profiling | Data to evaluate performance, but does not imply identical codegen on every JVM |

**Assembly/Ideal graph is not available by default.** Depending on the HotSpot build, printing disassembly may require `hsdis` or specialized tools. Flags like `TraceLoopOpts`/`TraceLoopPredicate` in HotSpot source may be **develop-only** and not run in product release builds; do not paste them arbitrarily onto a production JVM promising they are always supported.

### C2 graph analysis

OpenJDK has related source in `opto/loopnode.cpp`, `loopTransform.cpp`, `loopPredicate.cpp`, and compiler flags. However, source structure varies across JDK branches. Reading the code helps understand the algorithms, but proving a specific compiled method version requires checking the corresponding build/flags/profile.

Signs of JIT loop optimization to look for in assembly/IR include:

- Is there still an array bounds comparison for **each iteration** in the main loop?
- Is there a **pre-loop/guard/predicate** replacing per-element checks?
- Is there a tail loop after unrolling/vectorization to handle the remainder?
- Do null/bounds guards exist at the fast path entrance or fallback?
- Which assumptions do deoptimization entries/uncommon traps protect?
- Was that compiled code version actually used in the measured workload?

It is **not enough** to look only at a machine loop with no comparison branch while ignoring the prologue, versioning guard, or uncommon trap at another address.

## 13. Common barriers to RCE, LICM, and vectorization

### 13.1. Non-linear or data-dependent index expressions

~~~java
for (int i = 0; i < indexes.length; i++) {
    total += values[indexes[i]];
}
~~~

`i` is valid for `indexes`, but `indexes[i]` can be any `int`, including negative or exceeding `values.length`. An optimizer must not omit the bounds check for `values[indexes[i]]` unless it has an appropriate proof/range.

### 13.2. Changing references or aliasing

~~~java
for (int i = 0; i < holder.data.length; i++) {
    callback(holder);
    sum += holder.data[i];
}
~~~

`callback` may change `holder.data`, update state, or throw. `holder.data` cannot be assumed to always point to the same array. If a snapshot contract is desired, intentionally change the source and check thread safety.

### 13.3. Volatile and synchronization

`volatile` reads or entering/exiting `synchronized` have memory ordering semantics; the JIT must not drop required reads/writes claiming "the value barely changes." With an unmodified `boolean enabled` parameter, unswitching may be more applicable than with a `volatile boolean enabled` read inside the loop.

### 13.4. Side effects before an access that may throw an exception

If `log(i)` or `counter++` must occur before a failing array access, all validation cannot be moved to the top to throw before those side effects while still calling the two source versions equivalent.

### 13.5. Early exits and exception paths

`break`, `continue`, `return`, `throw` mid-loop can create complex control flow, limiting certain transformations. Do not claim "having `break` means the JIT won't optimize" — partial optimization is still possible in practice.

### 13.6. Overflow in the induction variable

With `int` addition/subtraction under Java semantics, values can overflow. An **unsafe** example:

~~~java
for (int i = start; i <= end; i++) {
    process(i);
}
~~~

If `end == Integer.MAX_VALUE` and the loop reaches `i == MAX_VALUE`, `i++` wraps to `Integer.MIN_VALUE` and the condition `i <= end` remains true; the loop may never terminate. This is not just a performance issue, it is a **logic bug**.

For constructs that might hit integer maximum, design appropriate bounds and index types, avoid overflow, or use a loop exit condition proven safe. **Do not mechanically change `<=` to `<`** if doing so drops the last element required by business logic.

### 13.7. Floating-point reductions

Summing `double` across iterations may not be associative under IEEE 754; reordering or vectorizing reductions must obey the floating-point semantics constraints of the Java version/VM. Do not assume C2 is free to reorder addition as with ideal mathematical real numbers.

### 13.8. Short loops and code size

Hoist/predicate/unroll have entry costs and increase code size. A loop of only 2–3 iterations may run faster with simple checks without creating multiple versions. The **cost model** is why the compiler sometimes does not optimize a loop that looks eligible in theory.

## 14. Designing source to help the compiler: clear contracts, not "forcing the JIT"

### 14.1. Use bounds matching the actual data

Usually prefer:

~~~java
for (int i = 0; i < a.length; i++) {
    use(a[i]);
}
~~~

rather than computing the length from an unrelated source. This lets readers immediately see the safe access range, and provides an easy-to-analyze loop form for the JIT.

### 14.2. Validate at the API boundary when that is the intended contract

If the method requires `[from,to)` to be valid **before any side effect**, check explicitly:

~~~java
Objects.requireNonNull(a);
Objects.checkFromToIndex(from, to, a.length);
for (int i = from; i < to; i++) {
    sum += a[i];
}
~~~

`Objects.checkFromToIndex` (Java 9+) clarifies the API contract, making code safe and easy to review. Even so, it **does not guarantee C2 has eliminated every internal check**, and adding validation to an existing method with side effects can change semantics as shown in section 8.

### 14.3. Use a local reference when the contract wants a snapshot

~~~java
int[] snapshot = holder.data;
for (int i = 0; i < snapshot.length; i++) {
    process(snapshot[i]);
}
~~~

If the goal is to process **a fixed version of the array reference**, this expresses the intent. If the goal is to observe field changes immediately inside the loop, a local snapshot is **not equivalent**.

### 14.4. Do not hand-unroll before benchmarking

Manually writing 8 accesses per iteration complicates code, invites tail/overflow bugs, and can hurt the optimizer or waste instruction cache. Give the JIT a chance to do it via a canonical loop first; only manually optimize if measurements/JMH + inspection prove it and tests protect it.

### 14.5. Do not drop checks using `Unsafe` just for benchmarks

Converting a Java array to a raw native pointer to bypass bounds safety is a very different step regarding safety/lifetime and can cause memory corruption. Internal `Unsafe` flags/module access are not a general solution for a slow loop. Optimize algorithms, data layout, allocation, concurrency, and I/O before breaking the memory safety contract.

## 15. Benchmarking properly: warm, long enough, avoiding compiler magic

A `System.nanoTime()` loop wrapping 5 iterations is not enough to conclude `a[i]` received RCE. Confounding factors:

- JIT is not hot enough yet, or is transitioning C1→C2/OSR.
- GC occurs during the measurement window.
- CPU turbo, thermal throttling, and OS thread scheduling.
- Data is too small, fitting entirely in cache; memory bandwidth is not tested.
- JIT constant-folds or dead-code eliminates a computation whose result is unused.
- Branch predictability, aliasing, and vectorization depend on input shape.
- `nanoTime()` overhead dominates very short work.
- The benchmark tool has **coordinated omission** if used for server request latency.
- Rare exceptions and slow paths are not tested.

### JMH is preferred for microbenchmarks

Java Microbenchmark Harness (JMH) from the OpenJDK project manages **forks, warm-up iterations, measurement iterations, state, parameterization, result consumption**, and statistics. Example JMH structure:

~~~java
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
public class SumBenchmark {
    @Param({"64", "4096"})
    public int size;

    int[] values;

    @Setup(Level.Trial)
    public void setUp() {
        values = new int[size];
        for (int i = 0; i < size; i++) values[i] = i;
    }

    @Benchmark
    public long sumRange() {
        return LoopOptimizationDemo.sumRange(values, 0, values.length);
    }
}
~~~

**This is not a program compiled with bare `javac`**: it requires JMH dependencies/plugin and the benchmark class in the same package or adjusted visibility for `LoopOptimizationDemo.sumRange`. `@Param` tests multiple array sizes instead of a single length favorable to the compiler. Still, JMH does not replace end-to-end load testing with a real request mix.

Do not compare loops solely by "lowest ns/op" if one version does less work, drops exception behavior, or uses data with a different layout. You need the same correctness, same setup, same CPU/JDK flags, and representative warm-up conditions.

### A rigorous A/B comparison method

1. Keep the JDK build, `-Xms/-Xmx`, CPU quota, and machine workload identical.
2. Use representative lengths (0, 1, 2, 3, 64, 4096, millions of elements).
3. Test invalid ranges, null, early returns, negative/positive data, and overflow edges.
4. Warm up sufficiently for the methods/branches under test, verifying compilation mode via logs.
5. Use multiple independent process forks, varying candidate order when needed.
6. Measure throughput/latency, errors, and GC/allocation, not just average timing.
7. If claiming **actual RCE**, inspect optimized IR/native code on the specific build.
8. Report results within their exact limits: "the experiment showed faster" differs from "every JVM drops checks."

## 16. Do these optimizations still hold when a method is deoptimized?

JIT code is an **implementation choice** of the JVM. If a guard assumption no longer holds, HotSpot can **deoptimize** and resume at an equivalent bytecode-level state, then let the interpreter or another compiler handle it.

A hypothetical example:

~~~text
Warm-up:
  99.99% of calls have from=0, to=a.length, a non-null
              |
              v
C2 uses profile/guards to create optimized path
              |
              v
Production:
  occasionally to > a.length
              |
              v
guard/trap/fallback must preserve exceptions and side effects
              |
              v
may deoptimize or take slower path
~~~

Do not say that `Objects.checkFromToIndex` will always be turned into a trap, or that every invalid call definitely deoptimizes. The compiler has many options depending on code shape, profile, and JDK build.

**Correctness is preserved at every tier.** Java does not allow a program to produce wrong results just because code became "hot." That is why a test passing at JIT level 4 is not proof of a specific performance optimization, though it is a prerequisite for evaluating correctness.

## 17. Checklist when a Java loop appears slow

- [ ] Identify **the actual hot loop** using a profiler, do not guess from code review.
- [ ] Check O(N) algorithm, data volume, and memory locality before blaming bounds checks.
- [ ] Inspect source indices: are there `i`, `i+1`, `2*i`, `positions[i]`, and multiple different arrays?
- [ ] Check **actual bounds**: is it proven on the index expression/array actually being used?
- [ ] Check potential integer overflow/negative indices.
- [ ] Check if array reference is stable, and whether there are calls/side effects/volatile/aliasing in the body.
- [ ] Check if early break/return or error behavior constrains transformations.
- [ ] Do not manually move null/bounds checks before side effects if it changes the contract.
- [ ] Use `javap` to understand bytecode; use compilation logs to see JIT activity.
- [ ] Do not treat `PrintCompilation` as a report of RCE or vectorization.
- [ ] When optimization confirmation is needed, use IR/native assembly tools with a suitable build.
- [ ] Benchmark with JMH, multiple forks/iterations, and representative inputs.
- [ ] Use `-Xint` for semantics comparison when helpful, do not call it "simulating cold JIT."
- [ ] Measure both performance and correctness of invalid/null/overflow edge cases.
- [ ] If manually changing loop structure, keep tests comparing before/after versions across multiple random seeds.
- [ ] Keep safe APIs unless there is a genuine native memory reason and a separate audit.

## 18. Self-check: predict what gets optimized under appropriate conditions?

### Question 1

In `for (int i=0; i<a.length; i++) sum+=a[i]`, which check **has a chance** of being reduced? **Array bounds checks** on the compiled path proven safe, not an obligation guaranteeing the runtime will do so.

### Question 2

Is `a[i+1]` with loop limit `i<a.length` allowed to drop the check unconditionally? **No**, the last iteration may access out of bounds; a proper condition/handling strategy is needed.

### Question 3

With two arrays `a`, `b` and loop limit `a.length`, can the `b[i]` bounds check be dropped because `a[i]` is valid? **No**, `b` may be shorter or null; separate proof is required.

### Question 4

Does `values[indexes[i]]` belong to a counted loop easy for RCE? **Not by default**, because values in `indexes` can be outside the range of `values`.

### Question 5

When C2 moves a condition before the loop, can it change the thrown exception or omit required side effects? **No**.

### Question 6

Does `Objects.checkFromToIndex` exist in Java 17? **Yes**, since Java 9.

### Question 7

If `checkFromToIndex(2,7,6)` throws an exception before the loop, did the JIT "detect the bug"? **No**, that is validation required by the source API.

### Question 8

If `iaload` appears in `javap`, does C2 native code definitely run a check for every `iaload`? **No**, bytecode differs from optimized native code.

### Question 9

`PrintCompilation` shows level 4; can we conclude RCE occurred? **No**, only that compilation occurred at the corresponding tier.

### Question 10

Does loop unswitching apply to `if (enabled)` when `enabled` is a stable parameter? **Possibly**, if the compiler finds it worthwhile and valid.

### Question 11

Can a `volatile` field read in the body be unconditionally treated as constant throughout the loop? **No**, memory semantics may require those reads.

### Question 12

Can an unroll factor of 4 on array length 9 skip the last element? **No**, there must be a path handling the remainder or an equivalent organization.

### Question 13

Are RCE and auto-vectorization a single optimization? **No**; RCE handles checks, while vectorization combines operations using SIMD under appropriate conditions.

### Question 14

Does `-Xint` producing the same output but slower prove that optimized native code vectorized? **No**.

### Question 15

Why is `for (int i=start; i<=Integer.MAX_VALUE; i++)` dangerous? **`int` overflow** on increment, which can prevent the loop from terminating.

### Question 16

If a loop has `break`, does C2 definitely optimize nothing? **No**, it may still partially optimize, though control flow is more complex.

### Question 17

If `holder.array` changes between iterations, does a local snapshot always preserve the old semantics? **No**, only do so when the contract allows fixing the reference.

### Question 18

Can benchmarking a 1-element array conclude good optimization for a 1-million-element array? **No**, memory bandwidth/cache/branching and transformation profitability differ.

### Question 19

If a speculative guard assumption fails, what is the compiler allowed to do? **Choose a valid fallback/deoptimization**, still preserving Java semantics.

### Question 20

What is most important when modifying code for performance? **Measure the right bottleneck and do not alter correctness**, including exception ordering and side effects.

## 19. References for deeper study

- **Java Language Specification 17**, §15.10 Array Access Expressions (access conditions/exceptions): https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.10.4
- **JVMS 17**, bytecode `iaload`, `iastore`, array access instructions: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-6.html
- **Java SE 17 `Objects.checkFromToIndex`**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html#checkFromToIndex(int,int,int)
- **Oracle JDK 17 `javap` disassembler**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html
- **Oracle JDK 17 `java` launcher** (`-Xint`, diagnostic compilation flags, JIT tooling): https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- **OpenJDK JDK 17u, HotSpot C2 compiler flags** (e.g. LoopUnroll, UseLoopPredicate, LoopUnswitching, SuperWord): https://github.com/openjdk/jdk17u/blob/master/src/hotspot/share/opto/c2_globals.hpp
- **OpenJDK HotSpot loop optimizations** — documentation explaining counted loops, loop predication, and range-check elimination: https://wiki.openjdk.org/display/HotSpot/Loop+optimizations+in+Hotspot+Server+VM+Compiler+(C2)
- **Red Hat Developer, Range check elimination in loops in OpenJDK's HotSpot JVM** (2022): https://developers.redhat.com/articles/2022/03/16/range-check-elimination-loops-openjdks-hotspot-jvm
- **OpenJDK JMH** — a more reliable Java benchmarking methodology than manual `nanoTime` loops: https://openjdk.org/projects/code-tools/jmh/

**Conclusion:** HotSpot C2 can improve loops by proving **index ranges**, eliminating redundant **array bounds/null checks**, generating **loop predicates**, splitting **pre/main/post**, hoisting invariant conditions, **unswitching**, **unrolling**, or **vectorizing** under appropriate conditions. However, **every step is constrained by Java semantics**: null, array bounds, overflow, exceptions, side effects, aliasing, concurrency, and termination conditions must remain correct. Write source with clear contracts, choose readable canonical loops, measure with JMH/real workloads, and only assert a specific JIT transformation after inspecting the **optimized IR/assembly** of that exact JVM build — do not infer it from `javap`, a `PrintCompilation` line, or a fast benchmark run.
