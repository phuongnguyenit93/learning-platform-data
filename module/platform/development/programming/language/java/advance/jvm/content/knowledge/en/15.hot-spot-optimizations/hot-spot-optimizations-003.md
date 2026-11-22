# Constant Folding, Dead-Code Elimination, and Measurement Impact in the HotSpot JVM

## Objectives

When programming in Java, two versions of code may look different, yet after optimization lead to **the same sequence of machine instructions**. Conversely, a computation that appears in source and even in bytecode may **no longer exist** in machine code after JIT. This is why a naive microbenchmark can report that a computation takes nearly **0 ns**, or that algorithm A is hundreds of times faster than algorithm B simply because the compiler notices that A's result is not needed.

Two central mechanisms of this lesson:

- **Constant folding:** replacing an expression whose result is already known with a fixed value, when the transformation preserves Java semantics. For example, `6 * 7` can become `42` right when compiling the source, or an expression with actual inputs known to the JIT can be precomputed in optimized code.
- **Dead-code elimination (DCE):** removing computations, assignments, branches, and even object allocations that do not affect **observable program behavior**. If the result is unused and there are no side effects/exceptions/ordering that must be preserved, the JIT can eliminate the work you thought you were measuring.

After this lesson, you can:

1. Distinguish **javac compile-time constant expressions** according to the JLS from **runtime JIT constant propagation/folding** in HotSpot.
2. Understand **dead assignments**, **unreachable branches**, **unused results**, **redundant checks**, and their interaction with inlining, common-subexpression elimination, loop invariant code motion, and escape analysis.
3. Recognize limitations imposed by **exceptions, volatile accesses, synchronization, I/O, floating-point behavior, integer overflow, aliasing, and the Java Memory Model**.
4. Use `javap -c -p` to distinguish code handled upfront by `javac` from code that still remains in bytecode but can be optimized later by the JIT.
5. Create runnable Java 17+ examples with deterministic stdout and describe what **cannot** be concluded from output alone.
6. Design benchmarks with **JMH**, using `@State`, `@Param`, return values, or `Blackhole` to limit unintended DCE/constant folding.
7. Avoid “anti-optimization” tricks that alter the measurement, such as adding `System.out.println` inside a timed loop or mechanically using volatile.
8. Interpret benchmark results in terms of **real workload**, warmup, JIT tiering, dead-code elimination, allocation rate, and diagnostic tools.

## 1. Transformation layers from Java source to CPU

~~~text
Java source
    |
    | javac
    v
.class bytecode
    |
    | HotSpot interpreter / profiling
    v
JIT intermediate representation (C1/C2 depending on build/mode)
    |
    +-- inlining
    +-- constant folding / constant propagation
    +-- branch simplification
    +-- dead-code elimination
    +-- loop optimizations
    +-- escape analysis / scalar replacement
    +-- machine-specific lowering/scheduling
    |
    v
Optimized machine code
    |
    v
Actual program behavior (must conform to Java semantics)
~~~

The stages do not necessarily happen once or in the exact simplified order above. HotSpot has multiple compiler passes, phase ordering, and recompilation; one optimization can enable another. C1/C2 and internal representations are not part of the Java SE public API.

### Two types of constant folding easily confused

**Constant folding in `javac`:**

~~~java
static final int ANSWER = 6 * 7;
static int getAnswer() {
    return ANSWER;
}
~~~

This is an illustrative class-member snippet and must be placed inside a class. `ANSWER` is a **constant variable**: `final`, primitive type, initialized by a constant expression. `javac` can place the value 42 directly into the code of the method using it. Even `getAnswer()` can have bytecode that loads a constant and executes `ireturn` without needing `getstatic ANSWER`.

**Constant folding in the HotSpot JIT:**

~~~java
static int multiply(int x) {
    return x * 7;
}

static int callWithKnownValue() {
    return multiply(6);
}
~~~

These are illustrative methods. The caller's bytecode may still contain `invokestatic multiply` and the callee's bytecode has the multiplication. However, after the JIT inlines `multiply(6)`, the compiler can know the argument is 6 and fold the multiplication into **42**. The Java source does not need to mark `x` as `final` for a JIT optimization to recognize a constant at a specific call site.

**Key takeaway:** seeing a multiplication in `javap` does not mean the CPU must execute a multiplication; conversely, `javap` only shows class-file bytecode, not the final machine code.

## 2. Constant expressions in the JLS differ from all expressions the JIT can optimize

JLS Java SE 17 §15.29 defines a set of constant expressions of **primitive** or **String** types, using literals, permitted operations, casts, and references to constant variables. This governs many language rules, such as compile-time constant variables, switch case labels, narrowing constant conversions, and class initialization.

Example:

~~~java
static final int A = 40 + 2;
static final String LABEL = "J" + "VM";
static final int B = Integer.parseInt("42");
static final Integer C = 42;
static int D = 21 * 2;
~~~

These are **illustrative class fields**, not standalone:
- `A` is a primitive constant variable.
- `LABEL` is a String constant variable.
- `B` is `final int` but **is not a constant variable under the JLS**, because the initializer calls the method `Integer.parseInt` rather than being a constant expression.
- `C` is not a constant variable under the JLS: the type `Integer` is neither primitive nor String.
- `D` is not a constant variable because it lacks `final`, even though the initializer looks computable at compile time.
- **The JIT can still infer some values** from B, C, or D if runtime conditions are strict enough, but that is **runtime inference/optimization**, and does not turn these fields into constant variables under JLS semantics.

### Java constant variables impact binary compatibility

If a public library exposes:

~~~java
public static final int TIMEOUT = 30;
~~~

and a client is compiled against that constant variable, the client code may contain the constant **30** directly instead of a runtime field read. Later, if the library changes to `TIMEOUT=60` without **recompiling the client**, the client may still use 30. This is **constant inlining across a compile boundary**, not a JIT bug.

If a value needs to change and clients must always read it at runtime, an API method/getter or a field not belonging to the constant-variable category may be more appropriate. You must also consider initialization, access semantics, and API binary compatibility. Do not use `static final` primitive constants as “dynamic configuration”.

### Compile-time unreachable code differs from JIT DCE

A piece of source code can be rejected by the Java compiler due to the **unreachable statements** rules in the JLS. That is a **compile-time error**. Meanwhile, HotSpot DCE mainly removes nodes/instructions from machine code after source and bytecode are already valid; the Java source still compiles normally.

Do not assume `javac` will perform every optimization that the JIT performs, and do not assume the JVM has the right to change observable semantics for performance.

## 3. Complete Java 17+ example: distinguishing folding and dead expression

Create the file **`FoldingAndDceDemo.java`**:

~~~java
public class FoldingAndDceDemo {
    private static final int ANSWER = 6 * 7;

    private static final int RUNTIME_VALUE =
            Integer.parseInt("42");

    private static volatile int observed;

    static int compileTimeConstant() {
        return ANSWER;
    }

    static int runtimeField() {
        return RUNTIME_VALUE;
    }

    static int unusedArithmetic(int x) {
        int temporary = (x + 2) * (x + 2);
        return x + 1;
    }

    static int mayThrow(int divisor) {
        int unused = 100 / divisor;
        return 7;
    }

    static int visibleWrite(int x) {
        observed = x * 2;
        return 1;
    }

    public static void main(String[] args) {
        System.out.println("constant=" + compileTimeConstant());
        System.out.println("runtime=" + runtimeField());
        System.out.println("unused=" + unusedArithmetic(7));

        try {
            mayThrow(0);
            System.out.println("unexpected");
        } catch (ArithmeticException ex) {
            System.out.println("division=ArithmeticException");
        }

        visibleWrite(5);
        System.out.println("volatile=" + observed);
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 FoldingAndDceDemo.java
java FoldingAndDceDemo
~~~

**Exact stdout:**

~~~text
constant=42
runtime=42
unused=8
division=ArithmeticException
volatile=10
~~~

Explanation:

1. `ANSWER` belongs to the compile-time constant-variable category. `javac` can place `42` into the bytecode of `compileTimeConstant`.
2. `RUNTIME_VALUE` is initialized by a method call, therefore it is not a compile-time constant variable. `runtimeField` normally reads the field with `getstatic` in bytecode, although the HotSpot runtime may optimize further when appropriate.
3. `unusedArithmetic(7)` declares a local `temporary` but **does not use it** to produce the return value. HotSpot can eliminate the entire computation of `(x+2)*(x+2)` because integer arithmetic here produces no observable side effects/exceptions.
4. `mayThrow(0)` performs integer division by 0. Even though the variable `unused` is never read, the expression **must still throw ArithmeticException**. The JIT is not allowed to delete an operation if deleting it makes an observable exception disappear in the same context.
5. `visibleWrite(5)` writes to a **volatile field** and then main reads it back, so the result 10 must be preserved. Do not assume that assigning to a volatile field turns into a harmless “dead store”.

### Comparing bytecode

~~~bash
javap -c -p FoldingAndDceDemo
~~~

Looking at `compileTimeConstant`, you will typically see an instruction pushing 42 directly followed by `ireturn`. In `runtimeField`, you will typically see `getstatic RUNTIME_VALUE`. In `unusedArithmetic`, `javac` bytecode may still contain the multiplication and an `istore` to a temporary local. In `mayThrow`, you will typically see `idiv` — the division that can throw an exception.

**Do not treat bytecode offsets/constant-pool indexes as constants.** Different compiler builds can produce different output. `javap` is **not sufficient** to prove that C2 removed a computation from machine code; it only shows the step after `javac`, before JIT optimization.

## 4. Dead-code elimination: what does “unused result” mean?

A computation can be removed when **the value produced does not contribute to observable behavior**, and computing it carries no side effects/exceptions/ordering that must be kept.

~~~java
static void example(int x) {
    int a = x * 31;
    int b = a + 7;
    // Neither a nor b is used.
}
~~~

This is an **illustrative method**. An appropriate optimization can remove the assignments and arithmetic instructions. If a benchmark calls `example(123)` many times and measures elapsed time, it is very likely that the expected “math” no longer exists at the machine-code level.

### Side effects and control flow must be preserved

Operations that usually must be considered:
- `volatile` reads/writes under the Java Memory Model.
- Monitor locking with `synchronized` and synchronization order.
- I/O operations with external effects, such as printing to console or writing files.
- Memory writes that may be accessed from other code paths or other threads according to semantics.
- Observable exceptions, such as `ArithmeticException`, `NullPointerException`, `ArrayIndexOutOfBoundsException`, and certain errors at appropriate points.
- Native calls or JNI code with side effects.
- Object identity, locking, references escaping the method, finalization/reference-processing constraints where applicable.

**Not** every one of these operations must remain intact instruction-for-instruction in machine code. The JIT only needs to preserve **Java-level observable behavior**, and can combine or eliminate redundant operations if proven valid.

### DCE differs from compile-time dead branch pruning

~~~java
static int choose(int x) {
    if (x > 0) {
        return 1;
    }
    return 2;
}
~~~

This is a valid method. If the JIT sees a caller always passing x=5 and inlines it, it can conclude `x>0` is always true at **the specialized call site** and drop the other branch. However, for a general caller passing negative x, the compiler cannot turn the entire method into returning 1 unless a guard/deoptimization ensures correct semantics.

**Constant propagation can pave the way for DCE:** when a condition is proven true, the false branch becomes dead; consequently, computations belonging only to the false branch are also eliminated.

## 5. Constant folding is an equivalence-preserving substitution, not “simplification regardless of semantics”

Example with integers:

~~~java
static int zeroProduct(int x) {
    return x * 0 + 9;
}
~~~

For `int`, multiplying by 0 always yields 0 under Java rules, even when x is negative or another multiplication could overflow. Therefore this method's result is always 9; the compiler can fold it into a constant if there are no side effects in reading x.

However, for `double`:

~~~java
static double floatingZero(double x) {
    return x * 0.0d;
}
~~~

It **must not** be turned into the literal `0.0d` for all x:
- `Double.POSITIVE_INFINITY * 0.0` is **NaN**.
- `-3.0d * +0.0d` is **-0.0d**.
- NaN propagation and signed zero must be respected.
- Java 17+ strict floating-point semantics forbid transformations that lose these observable results just because “multiplying by 0 equals 0”.

### Runnable example: integers and IEEE 754 zero sign

Create the file **`SemanticBoundaryDemo.java`**:

~~~java
public class SemanticBoundaryDemo {
    static int zeroInt(int x) {
        return x * 0 + 9;
    }

    static double zeroDouble(double x) {
        return x * 0.0d;
    }

    public static void main(String[] args) {
        System.out.println("int=" + zeroInt(Integer.MIN_VALUE));

        double infinityResult =
                zeroDouble(Double.POSITIVE_INFINITY);
        System.out.println("infinityNaN=" +
                Double.isNaN(infinityResult));

        double negativeZero = zeroDouble(-3.0d);
        System.out.println("negativeZeroBits=" +
                Long.toHexString(
                        Double.doubleToRawLongBits(negativeZero)));
    }
}
~~~

Compile/run:

~~~bash
javac --release 17 SemanticBoundaryDemo.java
java SemanticBoundaryDemo
~~~

**Exact stdout:**

~~~text
int=9
infinityNaN=true
negativeZeroBits=8000000000000000
~~~

The hex value `8000000000000000` is the bit pattern of **-0.0d** in IEEE 754 double. This is why algebraic rules of integers must not be applied mechanically to floating-point operations.

### Integer overflow is also a boundary

Java `int` arithmetic overflows according to two's-complement wraparound rules for standard operations; infinite-precision integers must not be assumed. The transformation `(a+b)-b → a` may still hold modulo 2^32 for int, whereas rearrangements or transformations involving division, shifts, comparisons, and casts can differ. The compiler must prove correctness under Java rules, not rely on real-number algebra and ignore overflow.

## 6. How do constant propagation and inlining make a benchmark “disappear”?

A computation whose input is not constant in the source method can still be seen as constant by the JIT **after inlining**.

~~~java
static int expensive(int x) {
    int y = x;
    for (int i = 0; i < 10; i++) {
        y = y * 31 + i;
    }
    return y;
}

static int benchmarkLike() {
    return expensive(7);
}
~~~

These are **two illustrative methods**. At `benchmarkLike`, the JIT can inline `expensive(7)`, know x and the loop bounds in advance, and fold/unroll/constant-propagate enough to obtain a fixed result. A very fast measurement at this point reflects an optimized **constant call site**, not performance on varying production inputs.

If you intentionally measure `expensive(7)` to evaluate **that specific caller with a constant input**, the optimization is reasonable. If the goal is to measure the computation with unpredictable inputs, the benchmark models the workload incorrectly.

### How to protect fairness when inputs must vary

- Provide inputs via **`@State` fields** in JMH so you are not merely passing a fixed literal.
- Use `@Param` to run multiple representative scenarios.
- If a broad input distribution or per-operation variation is needed, manage a dataset and indexing in a controlled way.
- Do not use `final int x=7` in the benchmark body if the goal is to measure the dynamic-input path.
- **Do not overuse Random.nextInt() inside the timed region** if the goal is only the computation; RNG cost can dominate the operation being measured.
- Do not try to “hide” data using reflection/volatile/synchronized if production does not pay a similar cost.

**Lesson:** the JIT's job is to optimize executing code, not to serve the expectation that a microbenchmark must run every instruction in the source verbatim.

## 7. Loop-invariant code motion and loop elimination

In addition to constant folding/DCE, the JIT can **hoist** computations that do not change across iterations outside the loop (loop-invariant code motion) or transform loops when semantics allow.

Example:

~~~java
static long sum(int n, int factor) {
    long total = 0L;
    for (int i = 0; i < n; i++) {
        int repeated = factor * factor;
        total += repeated;
    }
    return total;
}
~~~

This is an illustrative method. `factor*factor` does not depend on `i`; if there is no exception/side effect to preserve on each iteration, the compiler can compute it once and use it in the loop. This is a **valid** optimization, but if you want to measure “the cost of a million multiplications”, this code does not necessarily measure what you think.

### Cases where loops can be aggressively reduced

~~~java
static long sumNumbers(int n) {
    long s = 0L;
    for (int i = 0; i < n; i++) {
        s += 1L;
    }
    return s;
}
~~~

Mathematically, when n is non-negative and there are no relevant side effects, the result equals n. The compiler **may** recognize simple patterns and transform the loop. Do not promise that HotSpot **always** turns every loop into a formula; optimizations depend on the JDK, compiler, profile, data types, loop shape, and constraints.

Do not tailor a benchmark to the point where the loop only tests whether the compiler recognizes an identity, unless that itself is the research goal. Real workloads have data dependencies, branches, arrays, and cache behavior that must be reproduced.

### Loop body with no observable effect

~~~java
static void pointless(int n) {
    for (int i = 0; i < n; i++) {
        int tmp = i * 17;
    }
}
~~~

This is illustrative code. If the JIT can eliminate the loop while preserving relevant Java constraints, the code can become nearly empty. However, do not claim that **every loop without side effects can always be deleted without considering termination/safepoints/runtime constraints**. Non-terminating loops, potential exceptions, or VM progress/safepoint requirements can restrict the transformation.

## 8. DCE is not the same as escape analysis, but they work together

Consider this code:

~~~java
static int calculate(int a, int b) {
    Pair pair = new Pair(a, b);
    return pair.left + pair.right;
}
~~~

This is an illustrative method and requires defining a `Pair` class with appropriate fields/constructor. With HotSpot, **escape analysis** can prove `pair` does not escape; **scalar replacement** can represent its fields as scalar values and eliminate the **physical allocation** when semantics allow.

This is not merely deleting “the `new` instruction because the result is unused”: the field values **still** contribute to the return value. The optimization keeps the necessary computation and eliminates the intermediate object representation.

| Mechanism | Example of eliminated work | Why it is valid |
| --- | --- | --- |
| Constant folding | `6*7` becomes `42` | Result is deterministic, no behavior lost |
| Constant propagation | Passing known values across assignments/calls | Value can be proven at the point of use |
| Dead-code elimination | Deleting computation that only produces an unused result | No observable side effect/exception needs to be kept |
| Common-subexpression elimination | Reusing the result of a repeated expression | Dependencies/aliasing/side effects allow it |
| Loop-invariant code motion | Moving an invariant computation outside a loop | Does not alter ordering/exceptions/side effects |
| Escape analysis/scalar replacement | Eliminating allocation of a temporary object | Identity/escape does not require physical representation |
| Inlining | Replacing a method call with the callee's logic | Enables optimizations across method boundaries |
| Branch pruning | Dropping a branch known to be impossible | Backed by guard/profile or proof from inputs |

**Do not** treat DCE and escape analysis as the same optimization just because both can reduce the allocation count reported by a profiler.

### Object identity and synchronization limit optimization

If an object is published to global state, used as a lock, has its identity hash taken, or is observed by JNI code, the compiler must preserve behavior. Conversely, an object that merely holds two numbers inside a method does not necessarily need to exist physically if nothing can distinguish it.

HotSpot state can be reconstructed via **deoptimization** if optimized assumptions no longer hold; the JIT must ensure correctness even when falling back to the interpreter.

## 9. Computations that cannot be deleted due to observable exceptions

Consider:

~~~java
static int division(int denominator) {
    int ignored = 100 / denominator;
    return 7;
}
~~~

With `denominator=0`, the method **must throw ArithmeticException**, not return 7. Even though `ignored` is never read, the division still has observable exceptional behavior.

Similar cases:

~~~java
static int arrayRead(int[] array, int i) {
    int unused = array[i];
    return 7;
}

static int dereference(String text) {
    int unused = text.length();
    return 7;
}
~~~

These are method snippets. If `array` is null or the index is out of bounds, the array read can throw `NullPointerException`/`ArrayIndexOutOfBoundsException`. If `text` is null, `text.length()` throws NPE. The compiler **cannot arbitrarily delete** these checks if callers can observe the exception.

However, at a call site where the JIT proves `array != null` and the index is valid, or `text != null`, the checks can be eliminated/hoisted under those conditions. **Correctness is evaluated across the entire execution path and guarded assumptions**, not on an isolated statement.

### Exception order also matters

Java specifies evaluation order for expressions and method calls. Swapping the order of two computations can change which exception occurs first or alter side effects. The JIT may only reorder when **observable behavior** still conforms to Java semantics. This explains why an operation that looks unused may still be impossible to delete.

## 10. Volatile: “prevents DCE” but can change the problem being measured

A common trick:

~~~java
static volatile long sink;

static void measuredOperation(int x) {
    long result = x * 31L;
    sink = result;
}
~~~

A `volatile` field write carries ordering/visibility semantics; writing makes the result more “observable” to the optimizer. However, **every iteration now includes a volatile memory operation**, so you are no longer measuring the multiplication alone. On multi-core hardware and under contention, the overhead of store/visibility/ordering can dominate.

Therefore:
- With **JMH**, prefer `return result` from the benchmark method or use **`Blackhole.consume(result)`**.
- Do not add a `System.out.println` after every operation: console I/O is slow and highly variable.
- If production actually has a volatile write, it **is part of the workload** and should be measured.
- A shared sink can also cause contention/false sharing, distorting comparisons.
- A volatile field does not “disable all constant folding”; the compiler can still fold the computation producing the result before the volatile write if the inputs are known.

**There is no way to ask the JIT to do extra work just to make a benchmark look nice and still call that measuring production code.** A benchmark should be designed so that the computation is meaningful and inputs/outputs reflect the workload.

## 11. JMH: controlling DCE and constant folding

**JMH (Java Microbenchmark Harness)** is an OpenJDK tool for writing microbenchmarks on the JVM. It supports warmup, measurement iterations, forks, states, parameters, result consumption, and mechanisms to mitigate several JVM/compiler pitfalls.

### Bad benchmark: result is discarded

~~~java
@Benchmark
public void discarded() {
    expensive(42);
}
~~~

This is an **illustrative JMH fragment**; it requires JMH imports/project setup and an `expensive` method. If the callee has no observable side effects and the result is ignored, the compiler can remove most of the code after inlining. The measured time may be nearly just call/framework overhead or an operation optimized to nothing.

### Better: return or Blackhole

~~~java
@Benchmark
public int returned() {
    return expensive(value);
}

@Benchmark
public void consumed(Blackhole bh) {
    bh.consume(expensive(value));
}
~~~

This is an **illustrative JMH fragment**; `value` must belong to JMH state. JMH consumes the returned result or `Blackhole.consume` to limit DCE at the benchmark boundary. However:

- **Returning a result does not by itself prevent constant folding** if the input is still a constant.
- Blackhole does not guarantee every instruction in the source remains intact; the JIT still validly optimizes intermediate parts.
- Blackhole has overhead, so use it according to the JMH contract.
- Do not write your own method named `blackhole()` and assume it has the same effect as the JMH utility.
- If a benchmark creates an object but only consumes a scalar field, escape analysis can still eliminate the physical object allocation; that is a valid optimization for **the exact workload being measured**.

### @State and @Param solve the constant-input trap

To avoid passing a fixed literal at the call site, create a state with fields and receive parameters from the JMH harness. Use parameter values representative of production, rather than always picking the same 7 if the system runs across varied distributions.

## 12. Complete JMH example (Java 17+) to study folding

Place the file **`FoldingBench.java`** in **a JMH project already configured with the JMH library** under package `org.example`:

~~~java
package org.example;

import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.BenchmarkMode;
import org.openjdk.jmh.annotations.Mode;
import org.openjdk.jmh.annotations.OutputTimeUnit;
import org.openjdk.jmh.annotations.Param;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.State;
import org.openjdk.jmh.infra.Blackhole;

import java.util.concurrent.TimeUnit;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class FoldingBench {
    @Param({"11", "17", "103"})
    public int input;

    static int transform(int x) {
        int result = x;
        for (int i = 0; i < 8; i++) {
            result = result * 31 + i;
        }
        return result;
    }

    @Benchmark
    public int stateInput() {
        return transform(input);
    }

    @Benchmark
    public int constantInput() {
        return transform(11);
    }

    @Benchmark
    public void blackholeInput(Blackhole bh) {
        bh.consume(transform(input));
    }
}
~~~

**Compilation requirement:** this class has dependencies on `jmh-core` and the JMH annotation processor from the **JMH Maven archetype** or an equivalently configured JMH project. It cannot be compiled standalone using `javac FoldingBench.java` with plain Java SE because the annotations/JMH runtime are external libraries outside the JDK.

A common workflow after generating a JMH project with the official Maven archetype:
1. Use JDK 17+ and a compatible Maven version.
2. Add the file under the matching package in `src/main/java/org/example/FoldingBench.java`.
3. Build the artifact with `mvn clean verify` from the JMH project directory containing `pom.xml`.
4. Run the JMH runner from the project's JAR:

~~~bash
mvn clean verify
java -jar target/benchmarks.jar FoldingBench -wi 5 -i 5 -f 2
~~~

The options `-wi 5`, `-i 5`, `-f 2` are **examples of warmup iterations, measurement iterations, and forks**. Check `java -jar target/benchmarks.jar -h` for details specific to your JMH version. **Do not provide a table of “exact” measurement numbers** because ns/op depends on CPU, JDK, optimization, load, and noise.

### How to read the three benchmarks

- `stateInput`: input is read from a non-final JMH state field. That makes proving a single constant harder at typical optimization points and reflects multiple @Param scenarios.
- `constantInput`: calls `transform(11)` with a literal. This measures the **fixed-input** scenario; the JIT can inline/fold aggressively.
- `blackholeInput`: the same dynamic-input path, but consumes the result with Blackhole. Measuring its overhead and comparing against `stateInput` helps understand how JMH keeps the result observable; do not assume the two paths have identical nanoseconds.

**A subtle detail:** `@Param` assigns values before the benchmark run, so each fork/iteration may see a stable value; the JIT can still infer further if state and code shape allow. @State is not a guarantee of “no optimizations”, but a design that limits **the benchmark accidentally collapsing into a constant calculation**. To measure inputs that change per operation, you can use an array dataset and an appropriate iterator/index state.

### Why not put a 100-million-iteration loop inside @Benchmark?

If you place a fixed for-loop directly inside and measure the average time of the whole loop, the JIT can aggressively unroll/hoist/fold, making the inner work different from what you expected. Moreover, one JMH invocation no longer aligns with one logical operation. If you need to measure a batch, inspect JMH mechanisms like `@OperationsPerInvocation` or batch size with appropriate semantics and clearly document the measurement unit.

## 13. Benchmark traps: known input sources and dead outputs

Common cases:

| Benchmark body | Risk | Adjustment |
| --- | --- | --- |
| `void bench(){ expensive(10); }` | Result discarded, DCE may delete it | Return result or use Blackhole |
| `int bench(){ return expensive(10); }` | Result used, but constant input causes folding | Use JMH @State/@Param if dynamic input is needed |
| `int bench(){ return expensive(state.value); }` | Better, but profile may still specialize | Ensure dataset/parameter distribution reflects production |
| `void bench(){ sink = expensive(value); }` with volatile sink | Volatile store alters the workload | Avoid if you only want to measure the computation |
| `void bench(){ System.out.println(expensive(value)); }` | I/O dominates CPU, unintended side effects | Do not print inside the timed section |
| `int bench(){ return cachedValue; }` | Measures field load/cache hit instead of algorithm | Separate setup/caching and define the goal |
| `Object bench(){ return new Tiny(); }` | Allocation may optimize differently when result escapes | Benchmark allocation semantics vs object construction/capture clearly |

**For a real service**, an unused result is sometimes just a benchmark bug; however, in production logic, if a result is **truly unneeded**, the JIT eliminating the computation is an optimization success, not a bug. Measure what the system **actually needs to do**.

## 14. Official JMH samples: JMHSample_08 and JMHSample_10

OpenJDK JMH has two very relevant reference examples:
- **`JMHSample_08_DeadCode`** illustrates a benchmark whose discarded result gets optimized away and how returning the result/consuming it mitigates DCE.
- **`JMHSample_10_ConstantFold`** illustrates a computation with constant inputs being folded and how using **non-final instance fields in JMH @State** reduces the trap.

Lesson from both: **keeping the output alone is not enough if the input is still constant; using varying inputs is not enough if the output is not consumed**. A benchmark can fail at both ends.

You should understand the purpose of the JMH APIs:
- `@Benchmark` marks a method measured by the harness.
- `@State(Scope.Thread)` creates per-thread benchmark state.
- `@Param` supplies configuration values for state.
- `Blackhole.consume` prevents the optimizer from undesirably discarding a result at the benchmark boundary.
- The return value of `@Benchmark` is consumed appropriately by JMH according to harness behavior.

Source references:
- https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java
- https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java
- https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/infra/Blackhole.java

## 15. JMH still has limits: benchmarks must represent the workload

A clean microbenchmark does not guarantee results that predict latency in a web/server application:
- The JIT may inline code differently when called from a real application.
- Production has concurrency, lock contention, CPU throttling, GC, cache misses, and I/O.
- Branch predictability and object lifetimes differ from benchmark inputs.
- Optimizations can depend on call-site profiles, type distribution, escape behavior, and steady-state warmup.
- Benchmarking a pure arithmetic method does not represent a request processing JSON, network, and database calls.
- How data is laid out in memory can dominate cost more than the number of multiplications.

**Prefer both microbenchmarks and workload benchmarks:**
1. Microbenchmarks test **a clear optimization hypothesis** (e.g., constant folding, branch elimination).
2. Macro/load tests confirm **throughput, end-to-end p95/p99, and CPU/GC** of the real service.
3. All results should include **exact JDK build**, JVM flags, CPU quota/hardware, JMH version, forks, input distribution, and error bars.

### Confusing a benchmark result with the cost of a single statement

If JMH reports under one nanosecond/op:
- It may be throughput amortization or a folded operation.
- JMH may be counting “operations” differently from intuitive instruction counts.
- CPU pipelining, vectorization, and measuring many iterations together can yield ns/op smaller than the latency of an individual machine instruction.
- Do not conclude “the CPU executes 1 division in 0 ns”. Inspect the mode, code shape, and generated assembly/IR when truly needed.

## 16. Other valid optimizations that confuse measurements

### Common subexpression elimination (CSE)

~~~java
int left = x * 31;
int right = x * 31;
return left + right;
~~~

This is a snippet inside a method, assuming x is an int variable. The compiler may compute `x*31` only once and reuse the result. If a benchmark places two multiplications to measure “two multiplications”, the JIT may end up measuring one multiplication.

### Algebraic simplification

~~~java
int y = x + 0;
int z = y * 1;
return z;
~~~

This can simplify to return x. Do not claim the compiler must keep the addition/multiplication because the source has two operators.

### Branch folding

~~~java
if (false) {
    System.out.println("unreachable branch");
}
~~~

This is a snippet. `javac` or the JIT may omit executing the unreachable branch. However, do not place unreachable statements after `return` if the Java source would fail to compile under reachability rules.

### Loop unrolling and vectorization

A loop iterating over a primitive array can be unrolled or vectorized by the JIT if supported and allowed by dependence/aliasing constraints. Then “one scalar operation per iteration” no longer corresponds one-to-one with machine instructions.

### Strength reduction

Replacing a multiplication/index calculation with a shift/lea or suitable arithmetic is a target-CPU-dependent optimization. Do not use the operator count in source to infer runtime cycles.

### Escape analysis

An object created inside a loop that does not escape can be scalar-replaced, making the allocation rate in a profiler lower than the number of `new` expressions. If the goal is to measure allocation/GC pressure, the benchmark must make the object **genuinely escape in a way matching production semantics**, not merely contain the word `new`.

## 17. Profile-guided inlining and specialization can lead to deoptimization

C2 can use observed type profiles to specialize a call path. For example, a virtual call that usually sees the same receiver type can be inlined with a guard. When a different type appears, the optimized assumption is no longer valid.

To preserve Java semantics, HotSpot can:
1. Guard runtime assumptions.
2. Execute the optimized path when the assumption holds.
3. Perform deoptimization/uncommon trap or take a fallback path when the assumption fails.
4. Continue in the interpreter or appropriate compiled version, possibly recompiling later.

**This does not make folding/DCE incorrect.** Optimizations are only applied within the valid domain of conditions; guards/fallbacks preserve behavior outside that domain.

Under a benchmark workload containing only a single input/receiver type, the JIT can generate heavily specialized code. In production with multiple types and different input distributions, branch prediction, guard misses, and deoptimization overhead can significantly change performance. Therefore, benchmarks need **type diversity** and representative parameters.

## 18. Relationship to the Java Memory Model and multithreading

The JIT is not free to delete operations that carry **happens-before/ordering semantics** under the Java Memory Model. For `volatile`, synchronization, thread start/join, or atomic APIs, observable constraints must be preserved.

Example:

~~~java
final class Shared {
    volatile boolean ready;
    int payload;

    void publish() {
        payload = 42;
        ready = true;
    }
}
~~~

This is an illustrative class. In the case where another thread reads `ready` as true via an appropriate volatile read, the Java Memory Model supports the visibility of writes preceding the volatile write. The JIT cannot delete/reorder in a way that breaks this guarantee.

**However**, in a single-threaded benchmark without synchronization, the compiler can optimize more aggressively. Do not extrapolate from a concurrency-free microbenchmark to the behavior of code shared across threads.

A normal non-volatile variable **does not mean the JVM is free to return wrong results in all cases**; the difference lies in Java Memory Model constraints and permitted observable program behaviors. When designing concurrent benchmarks, properly model data races, atomicity, and synchronization instead of guessing what the JIT will do.

## 19. Using javap, PrintCompilation, JFR, and assembly carefully

### Step 1: bytecode with javap

~~~bash
javac --release 17 FoldingAndDceDemo.java
javap -c -p FoldingAndDceDemo
~~~

Inspect `compileTimeConstant` and `unusedArithmetic`. If bytecode contains redundant arithmetic while an optimized run is still fast, that **may** be due to the JIT; additional evidence from generated code is needed, and you must not conclude solely from timing.

### Step 2: compilation events

~~~bash
java -XX:+PrintCompilation FoldingAndDceDemo
~~~

HotSpot can print compiler events, including library methods. **There is no fixed log/compile ID/output order** because it depends on JDK build, warmup, compiler queue, and workload. Very short programs may not compile some methods before exiting.

### Step 3: JFR

Compiler/GC/CPU events can be collected with JFR depending on the JDK:

~~~bash
java -XX:StartFlightRecording=filename=jit-folding.jfr,dumponexit=true,settings=profile FoldingAndDceDemo
~~~

The recording may miss events if the program is too short, and **JFR does not directly prove that an expression was constant-folded**. JFR is useful for seeing JIT/CPU/GC context and finding hotspots.

### Step 4: generated machine code

To prove a computation was removed from optimized code, use appropriate tools to inspect native instructions or JIT compiler IR:
- HotSpot `-XX:+PrintAssembly` when a suitable disassembler/hsdis is available, along with the corresponding unlock flags.
- JITWatch, which reads compilation logs and visualizes compiler decisions.
- Async-profiler/perf disassembly with debug information where supported by the environment.
- Ideal Graph Visualizer or debug/JIT diagnostic facilities in supported environments.

**These tools are not always preinstalled or functional on every JDK/platform.** Do not write `-XX:+PrintAssembly` as a mandatory requirement to run Java code.

### LogCompilation for deeper optimizer study

~~~bash
java -XX:+UnlockDiagnosticVMOptions -XX:+LogCompilation -XX:LogFile=jit.xml FoldingAndDceDemo
~~~

This is a HotSpot diagnostic option whose XML format/version is implementation-dependent. JITWatch can help inspect inlining, compilation tiers, and traps. Do not confuse compiler IR with Java bytecode or assume a source statement corresponds to a single instruction.

## 20. Why is timing once with System.nanoTime() error-prone?

A measurement:

~~~java
long start = System.nanoTime();
// call work() many times
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
~~~

is an **illustrative snippet**, not yet a reliable benchmark. Sources of distortion:

1. **Dead-code elimination:** if the work result is unused, the work is deleted.
2. **Constant folding:** if inputs are known, the result can be precomputed.
3. **JIT warmup/tiering:** early iterations run in interpreter/C1, later iterations in C2, with OSR in between.
4. **Loop optimizations:** unrolling, LICM, vectorization, loop removal.
5. **Timer overhead/resolution:** the timing call itself has cost and noise.
6. **GC activity:** allocations or logging cause pauses/churn.
7. **OS scheduling/CPU frequency:** threads get preempted, thermal throttling occurs.
8. **CPU caches/TLB:** hot vs. cold data behave differently.
9. **Concurrent load:** other processes contend for CPU/memory bandwidth.
10. **Benchmark unit/normalization:** elapsed time of a loop is not automatically the latency of one operation in an application.

Even if you repeat 100 times and take the median, if the benchmark body was folded/DCE'd, you are only measuring a workload that was optimized away from your target.

### A valid microbenchmark checklist

- **State the hypothesis:** measuring multiplication with runtime inputs or constant-input?
- **Ensure inputs:** use state/datasets and sufficiently representative parameters.
- **Ensure outputs are used:** return, Blackhole, or observable application semantics.
- **Do not add dominating artificial work:** console I/O, random number generation, synchronization absent in production.
- **Warmup/forks:** JMH helps control this and measure multiple times.
- **JIT version/flags:** record JDK build, tiered mode, and compiler version.
- **Compare like-for-like:** same data, same correctness, and same tool settings.
- **Monitor CPU/GC:** do not extrapolate total service performance from ns/op.
- **Verify optimizations:** when suspecting DCE/folding, inspect appropriate compiler logs/assembly/IR.
- **Report variance:** not just a single best number.

## 21. Self-check exercises

**Question 1.** With `static final int X = 6*7`, at which layer can constant folding happen?

**Answer:** `javac` can fold it directly in bytecode because `X` is a JLS constant variable; the JIT also has other forms of runtime folding/propagation.

**Question 2.** Is `static final int Y = Integer.parseInt("42")` a compile-time constant variable?

**Answer:** **No** under the JLS; the initializer is a method call, even though the field is declared final.

**Question 3.** What are the two risks of a benchmark that only calls `compute(10)` and discards the result?

**Answer:** **Constant folding** on the literal input and **DCE** because the output is unused.

**Question 4.** Is returning the result in JMH enough to prevent constant folding?

**Answer:** Not yet. JMH keeps the output more observable, but a literal input can still be folded.

**Question 5.** Why should `System.out.println` not be used inside a timed benchmark?

**Answer:** Console I/O has large/variable overhead, mistakenly measuring screen printing instead of the calculation.

**Question 6.** Why can a volatile sink distort a benchmark?

**Answer:** It adds memory-ordering/visibility overhead and contention; it is a new operation not necessarily present in the real workload.

**Question 7.** Can `int ignored = 100/x; return 7;` always have the division removed?

**Answer:** No. If x=0, it must throw `ArithmeticException`.

**Question 8.** Can `return x*0+9;` become 9 when x is an int?

**Answer:** Yes, if the compiler proves there are no additional side effects; integer multiplication by zero is 0 under Java semantics.

**Question 9.** Can `return x*0.0d;` always become +0.0d?

**Answer:** No. Infinity×0 is NaN, and negative×positive zero can be -0.0.

**Question 10.** Does seeing `imul` in `javap` mean the CPU must execute a multiply instruction?

**Answer:** No. `javap` displays bytecode; the JIT can fold or remove it at the native level.

**Question 11.** Does a non-escaping object created with `new` necessarily incur heap allocation in optimized execution?

**Answer:** No. Escape analysis/scalar replacement can eliminate the physical allocation while preserving semantics.

**Question 12.** Why is a non-final `@State` field better than a fixed literal in a constant-folding benchmark?

**Answer:** The input is fetched from state rather than being a direct constant at the call site, reducing the chance the benchmark accidentally turns into a constant path; runtime optimizations still need to be checked.

**Question 13.** Does hoisting a computation outside a loop break Java semantics?

**Answer:** If the JIT proves it preserves side effects, exception order, and semantics, it is a valid optimization; if not proven, it must not be hoisted.

**Question 14.** If a benchmark reports 0.2 ns/op, does the CPU definitely execute the operation in 0.2 ns?

**Answer:** No. You must consider loop amortization, compiler optimization, pipelining, and measurement mode.

**Question 15.** If the source has `new Object()` but a profiler shows no corresponding allocation, is the profiler definitely wrong?

**Answer:** No. The JIT can eliminate physical allocation of a non-escaping/unobservable object.

**Question 16.** Will a good JMH benchmark accurately predict REST API p99 latency?

**Answer:** No. You must test application workloads, I/O, concurrency, GC, and tail latency.

## 22. Memory map

~~~text
JAVA SOURCE
   |
   +--> JAVAC COMPILE-TIME
   |      constant expressions
   |      constant variables (final primitive/String)
   |      -> bytecode may contain constant
   |
   v
HOTSPOT / INTERPRETER / JIT
   |
   +--> inlining + profile
   +--> constant propagation/folding
   +--> dead branch/code removal
   +--> loop invariant hoisting
   +--> scalar replacement / allocation elimination
   |
   v
MACHINE CODE (not 1-1 with source statements)
   |
   +--> must preserve Java semantics:
   |      exceptions, volatile/synchronization, I/O,
   |      floating-point, overflow, observable effects
   |
   v
BENCHMARK RISK
   |
   +-- constant input?        -> code is folded
   +-- output discarded?      -> code is eliminated by DCE
   +-- unrepresentative input? -> benchmark measures wrong workload
   +-- volatile/print?        -> measures new overhead
   |
   v
JMH @State + @Param + return/Blackhole
   |
   +-- warmup + forks + measurements
   +-- compiler logs / IR / assembly when needed
   +-- verify correctness and production relevance
   |
   v
MORE RELIABLE BENCHMARK
~~~

**Conclusion:** Folding and DCE are **valid and beneficial** optimizations of `javac`/HotSpot JIT, but they can cause a microbenchmark to **no longer execute the work the author thinks is being measured**. Distinguish JLS constant expressions from runtime JIT optimization, do not ignore exceptions/side effects/IEEE 754, and control **both input and output** in benchmarks using JMH. The goal of measurement is not to preserve source instructions at all costs, but to accurately represent **the actual work of the application**.

## References

- [JLS Java SE 17 — §15.29 Constant Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.29).
- [JLS Java SE 17 — §4.12.4 final Variables, Constant Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.12.4).
- [JLS Java SE 17 — §13.1 binary compatibility and constant variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1).
- [JLS Java SE 17 — §15.7 Evaluation Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.7).
- [JLS Java SE 17 — §17.4 Java Memory Model](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4).
- [OpenJDK Java Microbenchmark Harness](https://openjdk.org/projects/code-tools/jmh/).
- [JMH — JMHSample_08_DeadCode](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_08_DeadCode.java).
- [JMH — JMHSample_10_ConstantFold](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_10_ConstantFold.java).
- [JMH — Blackhole implementation/documentation](https://github.com/openjdk/jmh/blob/master/jmh-core/src/main/java/org/openjdk/jmh/infra/Blackhole.java).
- [Oracle JDK 17 — javap tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [Oracle JDK 17 — Java launcher and JIT diagnostic options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html).
- [OpenJDK HotSpot C2 optimizer source](https://github.com/openjdk/jdk/tree/master/src/hotspot/share/opto).
