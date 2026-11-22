# Distinguishing javac Transformations from JVM Optimizations

When compiling Java, we often see what looks like a simple pipeline: `.java` → `javac` → `.class` → `java`. However, there are **two very different stages of program transformation**. `javac` processes source code and generates bytecode before execution. The JVM receives bytecode and can then interpret it or compile parts of it into **machine code optimized using actual runtime data**, typically via a JIT (Just-In-Time) compiler.

This distinction explains why high-level Java constructs no longer appear in their original form in `javap`, why long-running programs can become faster than during startup, why the JVM can optimize differently on two machines even when using the exact same `.class` file, and why you should not conclude JIT optimization is happening just from inspecting bytecode.

This lesson belongs to the **Code Transformations** group of `Java Advance - compilation`. The goal is to separate responsibilities, inputs, outputs, observability, and limits of `javac` versus the JVM/JIT. Examples use Java 17+; details about tiered compilation, C1/C2, and some diagnostic flags refer to **HotSpot** in common OpenJDK/JDK distributions and do not automatically apply to every JVM.

## 1. One Program, Two Processing Layers

~~~text
                 COMPILE TIME
 .java source + classpath/module path + options
                       │
                       ▼
        javac: parse / semantic checks
                       │
                       ▼
    javac: desugar / lower / emit bytecode
                       │
                       ▼
                   .class
                       │
         ──────────────┼──────────────
                       │
                    RUNTIME
                       ▼
        JVM: load, verify, link classes
                       │
                       ▼
               Interpreter / JIT
                       │
             profiling / hot code
                       │
                       ▼
            optimized machine code
                       │
                       ▼
         CPU executes program behavior
~~~

This is a conceptual diagram. The JVM may start by interpreting and then compile to machine code; decisions are repeated, upgraded, or revoked at runtime. Some JVMs have different strategies from HotSpot, while activities such as garbage collection operate alongside execution. There is no fixed linear path forcing every method to pass through every single block in the diagram.

Quick comparison:

| Question | `javac` | JVM / JIT |
| --- | --- | --- |
| **When?** | Before execution, during source compilation | While loading and executing classes, depending on the JVM |
| **Primary input?** | Java source, dependencies, compiler options | Bytecode, runtime classes, profiling data, and CPU environment |
| **Primary output?** | `.class` files (bytecode + metadata) | Program execution; may generate machine code in memory |
| **Goal?** | Java semantic correctness, compatible class file format | Execute bytecode semantically accurately and improve runtime performance |
| **Knows actual runtime data beforehand?** | Generally no | Can observe call counts, branch frequencies, type profiles, etc. |
| **Inspection tools?** | `javap`, `javac -verbose`, class-file inspection | JFR, JIT logs, JITWatch, profilers, JVM flags |
| **Do `.class` files change when JIT runs?** | Created or updated when recompiling | Typically no; JIT code lives in JVM memory |

**Core point:** do not equate **“javac lowered source constructs”** with **“the JVM optimized execution speed”**. A compiler transformation may help the runtime optimize later, yet those remain two distinct responsibilities.

## 2. What javac Does Before the Program Runs

`javac` must produce an executable representation following Java rules. At a high level, the work consists of:

1. Reading source, tokenizing, and parsing into a syntax tree.
2. Recording declarations, resolving names, checking types, access, overloads, definite assignment, and other constraints.
3. Running annotation processors when configured; processors can generate additional source or metadata, which is not the same as JIT.
4. Transforming high-level language constructs into representations suitable for the JVM.
5. Emitting class files containing bytecode, the constant pool, and required metadata.

Step 4 is commonly called **desugaring/lowering**. A language construct does not necessarily have a direct corresponding JVM instruction; the compiler must express that behavior using combinations of instructions, methods, classes, or metadata. Examples:

| Source Java Construct | Commonly Seen Result in Bytecode or Class File |
| --- | --- |
| Enhanced `for` over an array | Index variable and equivalent loop |
| Enhanced `for` over an `Iterable` | Calls to `iterator()`, `hasNext()`, `next()` |
| `try`-with-resources | Resource-closing control flow and suppressed exception handling per the JLS |
| Generic `List<String>` | Erasure in descriptors and signature metadata when needed |
| Lambda / method reference | Typically `invokedynamic` and bootstrap metadata in OpenJDK `javac` |
| Dynamic string concatenation with `+` | Typically uses `invokedynamic`/`StringConcatFactory` in Java 17 |
| `record` | Class with fields, accessors, constructor, and members per record rules |
| `switch` expression | Control flow and returning appropriate values, possibly combining `tableswitch`/`lookupswitch` or other structures |

This is a **language-compliant executable form**, not a guarantee that the compiler achieved peak execution speed optimization. The compiler can still perform simple transformations such as **constant folding** and transformations specified for constant expressions; however, you should not expect `javac` to perform full inlining, escape analysis, or HotSpot JIT–style profile-guided optimization.

**Note on “javac optimizations”:** there is no need to deny all compile-time optimizations. Some constant computations really are precomputed; the difference is that `javac` generally lacks hot/cold data, common branches, or the actual runtime classes of objects in a future run, so it cannot make the same kinds of decisions as a runtime compiler.

## 3. First Example: High-Level Source Lowered into Bytecode

Create file **`SourceTransformDemo.java`**:

~~~java
public class SourceTransformDemo {
    static int sum(int[] numbers) {
        int total = 0;
        for (int number : numbers) {
            total += number;
        }
        return total;
    }

    static String greet(String name) {
        return "Hello, " + name;
    }

    public static void main(String[] args) {
        System.out.println(sum(new int[] {1, 2, 3}));
        System.out.println(greet("Java"));
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 SourceTransformDemo.java
java SourceTransformDemo
~~~

Exact stdout:

~~~text
6
Hello, Java
~~~

Inspect the class file:

~~~bash
javap -c -p SourceTransformDemo
~~~

In source there is `for (int number : numbers)`, yet in bytecode you will see the corresponding steps to iterate over the array, fetch each element, add it, and check the loop condition. This is **lowering** from language syntax to bytecode, not proof that the loop is being optimized using runtime profiles.

For `"Hello, " + name`, modern OpenJDK `javac` targeting Java 17 typically emits an `invokedynamic` call site backed by `StringConcatFactory`. `javap -c` can show the `invokedynamic` instruction and `javap -v` shows the bootstrap metadata. This mechanism from JEP 280 lets the runtime choose an appropriate concatenation strategy; **it does not mean javac pre-concatenated a `name` only known at runtime**.

The `javap` command reads the contents of compiled class files. It tells you **what the compiler emitted**, not a snapshot of machine code after the JVM applies JIT optimization.

### When Should You Inspect Bytecode?

- When you want to understand how a language construct is lowered.
- When checking `--release`, debug info, synthetic/bridge methods, or generic descriptors.
- When a bytecode tool, coverage tool, instrumentation agent, or reflection behaves differently from what you expect from Java source.

Do not use the instruction count printed by `javap -c` as a direct measure of execution speed: one instruction can be fused by the JIT with many others; runtime cost also depends on caches, data, branches, and environment.

## 4. javac Constant Folding Differs from Runtime Optimization

Consider file **`CompileTimeConstantDemo.java`**:

~~~java
public class CompileTimeConstantDemo {
    static final int LIMIT = 40 + 2;

    public static void main(String[] args) {
        System.out.println(LIMIT);
        System.out.println("Ja" + "va");
    }
}
~~~

Run:

~~~bash
javac --release 17 CompileTimeConstantDemo.java
java CompileTimeConstantDemo
~~~

Stdout:

~~~text
42
Java
~~~

`40 + 2` and `"Ja" + "va"` are **constant expressions** under Java rules. The compiler can place the values `42` and `"Java"` directly into the class file; when inspecting `javap -c`, you typically do not see runtime instructions adding 40 and 2 or invoking string concatenation for those two constants.

This is **compile-time** work because the operands are already known from source. It is completely different from the JIT noticing a method repeats very frequently, predicting hot branches, and emitting optimized native code while the application is running.

Distinguish further:

~~~java
int x = 40;
int y = 2;
int answer = x + y;
~~~

You should not conclude that every program using local variables has the same instruction set as the constants in the previous example. `javac` may keep load/add operations in bytecode; the JIT can optimize later depending on available information. With varying runtime values, an addition cannot be replaced by a fixed constant while preserving correctness.

### Important Consequence: Constants Inlined Across Class Files

Create two files:

**`ConstantConfig.java`**

~~~java
public final class ConstantConfig {
    private ConstantConfig() {}

    public static final int LIMIT = 40 + 2;
}
~~~

**`ConstantConsumer.java`**

~~~java
public class ConstantConsumer {
    public static void main(String[] args) {
        System.out.println(ConstantConfig.LIMIT);
    }
}
~~~

First pass:

~~~bash
javac --release 17 ConstantConfig.java ConstantConsumer.java
java ConstantConsumer
~~~

Stdout:

~~~text
42
~~~

Now change `ConstantConfig.LIMIT` to `99`, then recompile only:

~~~bash
javac --release 17 ConstantConfig.java
java ConstantConsumer
~~~

The old `ConstantConsumer.class` **may still print `42`** because `LIMIT` is a *constant variable* whose value was embedded when the consumer compiled. To synchronize, recompile the consumer or rebuild the entire dependency set. This is a property of **separate compilation and binary compatibility** of compile-time constants, not caused by the JIT "caching the wrong value".

For `static final` referencing an object newly computed during class initialization, or an expression that is not a constant expression, field access mechanics and optimization behavior differ. Do not treat **every** `static final` field as embedded by `javac` like a primitive/String compile-time constant.

## 5. How Does the JVM Execute Bytecode?

When running:

~~~bash
java SourceTransformDemo
~~~

The JVM performs actions such as class loading, bytecode verification, linking, and initialization at the required moments. Afterward, methods may be executed by an **interpreter** or by machine code generated by the runtime compiler. On HotSpot, methods typically start in the interpreter or an appropriate code tier; the runtime gathers profiling data and can promote hot segments to compiled code.

Profiling data can include:

- Method invocation frequency and loop iteration counts.
- True/false branch frequencies at instrumented points.
- Frequently seen runtime types at polymorphic call sites.
- Properties inferred by the runtime compiler from data flow and execution history.

The JIT uses this information to make decisions `javac` could never know from source alone. Resulting machine code depends on CPU architecture, JVM version, flags, profiles, and runtime conditions; **`.class` files do not need to change**.

### Tiered Compilation on HotSpot

Common HotSpot uses **tiered compilation** to balance startup time, compilation cost, and long-term throughput. Overview:

~~~text
Bytecode
   │
   ├── Interpreter (and collects data)
   │
   ├── C1: compiles relatively fast, may support profiling
   │
   └── C2: optimizes more deeply when eligible
            │
            ▼
     Native machine code for method or loop
~~~

HotSpot tier levels 0–4 and exact paths depend on configuration and version; for example, level 0 corresponds to the interpreter, levels 1–3 usually involve C1, and level 4 usually involves C2. This is not "four javac passes" or a rule that every method must touch each level. A short, rarely used method may never be JIT-compiled; a hot loop may trigger **on-stack replacement (OSR)** during execution.

### Warm-up

A workload may run slower right after startup due to class loading, initialization, profiling, JIT compilation, and many other costs. After running for a while, hot code can become better optimized. However, **you cannot deduce a fixed warm-up speed**: small workloads, I/O-bound workloads, different JVMs, or shifting profiles can exhibit different trends; GC, caches, and CPU also have an impact.

## 6. Second Example: Same Class File, Different JVM Execution Modes

Create **`HotLoopDemo.java`**:

~~~java
public class HotLoopDemo {
    static int step(int value) {
        return value * 2 + 1;
    }

    static long calculate() {
        long total = 0;
        for (int i = 0; i < 1_000_000; i++) {
            total += step(i % 10);
        }
        return total;
    }

    public static void main(String[] args) {
        System.out.println(calculate());
    }
}
~~~

Compile once:

~~~bash
javac --release 17 HotLoopDemo.java
~~~

Run normally:

~~~bash
java HotLoopDemo
~~~

Stdout:

~~~text
10000000
~~~

Because `i % 10` repeats digits 0–9 exactly 100,000 times, each group of 10 iterations contributes `1 + 3 + ... + 19 = 100`; the total equals 10,000,000.

If using HotSpot, you can try two diagnostic commands:

~~~bash
java -Xint HotLoopDemo
java -XX:+PrintCompilation HotLoopDemo
~~~

- `-Xint` tells HotSpot to run in interpreter-only mode, useful for **comparison**, without turning the source into "a different Java".
- `-XX:+PrintCompilation` prints logs of methods JIT-compiled during execution; logs may include many JDK methods, vary across versions/environments, and do not have to list every method in the program.
- The business result of the program must still be `10000000` if it succeeds, even though extra JIT logs may be printed to the console and the output line position is not fixed.

Comparing `HotLoopDemo.class` before and after the two `java` runs (assuming no other tools intervene) shows identical contents: the JVM does not overwrite class files to persist JIT-compiled code. Optimized machine code is managed inside the JVM process, typically in the code cache, and ceases when the process exits.

Do not use the timing of a single run as proof that JIT is faster or slower. For microbenchmarks, you need warm-up, multiple forks/iterations, representative inputs, and safeguards against dead-code elimination of the workload; JMH is more appropriate than ad-hoc `System.nanoTime()` measurements.

## 7. Frequently Mentioned JIT Optimizations

**Inlining:** replacing a method call with a representation of the method body at the call site when cost/complexity is reasonable. For instance, `step(i % 10)` in `HotLoopDemo` may be inlined once the JIT has sufficient information. `javap -c HotLoopDemo` still normally shows the method call because it prints the class file, not post-inlining code.

**Dead code elimination:** removing computations that do not affect observable results within what can be proven safe. On an optimizing JVM, an unused intermediate variable may not exist as a machine-code slot. Operations with observable side effects or exceptions must not be eliminated in a way that alters program behavior.

**Runtime constant propagation / folding:** the JIT can determine that a value is constant within a region being optimized after inlining and data-flow analysis, even when `javac` could not know it was constant from source structure. This differs from Java source containing constant expressions handled by the compiler per the JLS.

**Loop optimizations:** hoisting safe work out of loops, improving loop control, or removing redundant checks depending on the case. There is no promise that every Java loop gets vectorized or has every bounds check eliminated.

**Range-check elimination:** if the JIT proves an array access always remains within valid bounds in an optimized region, it can avoid some repeated bounds checks. Yet every access must still preserve the semantics of throwing `ArrayIndexOutOfBoundsException` when actually out of bounds.

**Escape analysis and scalar replacement:** if a temporary object does not "escape" the analysis scope and does not need to preserve observable object identity, the JIT may replace object accesses with scalar values. This is an **optimization capability**, not a guarantee that "writing `new` means the JVM never allocates".

**Branch prediction / profile-guided optimization:** favoring code layout and frequently taken paths based on runtime data; may apply speculative assumptions backed by guard checks.

**Devirtualization:** when runtime profiles show a receiver is usually one concrete type, the JIT may optimize an interface/virtual call into a specialized call or inline it with an appropriate guard. It does not change Java polymorphism rules; if the assumption stops holding, the runtime must handle it safely.

These terms describe *capabilities* of a runtime compiler; knowing whether a transformation occurred in a specific method requires evidence from the runtime/profiler, rather than relying on Java source "looking optimal".

## 8. Escape Analysis Example: Why You Should Not Guess from `new`

Consider the following standalone snippet — file **`PointWorkDemo.java`**:

~~~java
public class PointWorkDemo {
    static final class Point {
        final int x;
        final int y;

        Point(int x, int y) {
            this.x = x;
            this.y = y;
        }
    }

    static int result(int value) {
        Point point = new Point(value, value + 1);
        return point.x + point.y;
    }

    public static void main(String[] args) {
        System.out.println(result(10));
    }
}
~~~

~~~bash
javac --release 17 PointWorkDemo.java
java PointWorkDemo
~~~

Stdout:

~~~text
21
~~~

`javac` emits bytecode that can represent creating `Point` and reading both fields. Once the JIT inlines enough methods and proves the object does not escape, HotSpot **may** scalar-replace these values, reducing or avoiding allocation in optimized machine code.

This **does not guarantee** allocation is eliminated on every call. Escape analysis depends on the call graph, JVM version, optimization flags, object observability, and runtime state. If `Point` is returned, stored in a global field, or used in a context where identity must be preserved, the problem changes.

Do not use `javap` output to conclude "the JIT did not optimize the allocation": `javap` only sees pre-runtime bytecode. Also do not write code that depends on the JIT *having* to eliminate objects; a program must run correctly even when an interpreter executes the exact equivalent operations.

## 9. Speculative Optimization and Deoptimization

A JVM runtime compiler can make assumptions based on observed data, such as "most receivers at this call site have class `FastWorker`". When that assumption is reasonable, it can emit faster code with a **guard** checking the condition. If in the future the condition stops holding, the runtime can **deoptimize**: falling back to semantics-preserving execution, potentially reconstructing appropriate state to continue, or recompiling using the updated profile.

~~~text
Runtime data → profile: call site usually receives FastWorker
                           │
                           ▼
      JIT emits specialized machine code + guard
                           │
          ┌────────────────┴────────────────┐
          ▼                                 ▼
     Guard holds             Guard fails / assumption invalidated
      Fast path               Deoptimization / general path
          │                                 │
          └─────► Same Java semantics ◄─────┘
~~~

Do not confuse **deoptimization** with "the javac compiler edited the source file" or "the JVM altered bytecode on disk". Normally this is a change in how already-loaded code executes in memory, although tools like Java agents can perform class redefinition via a different mechanism.

HotSpot may recompile methods, invalidate compiled code, or transfer frames back to the interpreter depending on circumstances. These transitions explain why program speed can fluctuate with runtime data even when `.class` files stay unchanged.

## 10. What Is the JIT Not Allowed to Do?

Runtime optimizations must preserve **observable semantics** under the Java Language Specification and the Java Memory Model. For example:

- It must not arbitrarily reorder operations with side effects if reordering alters the observable outcome under Java semantics.
- It must not eliminate an exception required to occur on a particular execution path if removing it changes program behavior.
- It must not treat overflowing `int` arithmetic as unbounded mathematical integers; Java defines integer overflow behavior, so optimizations must preserve the corresponding result.
- It must not treat `volatile` or synchronization/thread-safety constraints as ordinary data and optimize in violation of happens-before rules.
- It must not produce results wrongly dependent on a stale type profile when a valid program executes with a new receiver; that is why guards and deoptimization are required.

A more accurate statement than "the JIT changes no results" is **the JIT must preserve specified behaviors within valid Java programs**. The physical ordering of machine instructions may differ from source, as long as observability and memory-model constraints are still satisfied. Certain things outside the semantic contract, such as execution duration or GC timing, may vary.

If a benchmark changes output when toggling JIT on/off, check for race conditions, reliance on unspecified behavior, native behavior, or a program/runtime bug before calling it "normal optimization".

## 11. String Concatenation: A Case Clarifying Both Transformation Layers

Consider:

~~~java
static String label(String name, int number) {
    return "item=" + name + ":" + number;
}
~~~

This is only an *explanatory method snippet* that needs to be placed in a Java class to compile. Java guarantees string concatenation behavior and operand evaluation order according to language semantics.

On Java 8–era OpenJDK `javac`, many string concatenation cases were lowered into chains of `StringBuilder` operations. From JDK 9 onward (JEP 280), dynamic code is typically emitted via `invokedynamic` with the `StringConcatFactory` bootstrap. This has two layers:

1. **javac chooses the bytecode form** using `invokedynamic` instead of hardcoding a particular builder strategy.
2. **The JVM/JDK runtime** links the call site and selects how to perform string concatenation, after which the JIT can also optimize the executing code.

You should not describe `invokedynamic` as "every concatenation is JIT-optimized". It is **a dynamic linking mechanism**, while performance benefits must be measured on specific workloads and JVMs. For expressions concatenating constants such as `"Ja" + "va"`, `javac` can fold them into the constant `"Java"` with no runtime concatenation needed.

To observe locally, put the method snippet in a class and use `javac --release 17`, then `javap -c -v`. The `BootstrapMethods` content typically shows metadata for `StringConcatFactory`. This form depends on compiler and options, so distinguish **Java semantic requirements** from **OpenJDK implementation details**.

## 12. Lambdas: Compiler Emits the Call Site, Runtime Implements Invocation

Complete example **`LambdaTransformDemo.java`**:

~~~java
import java.util.function.IntUnaryOperator;

public class LambdaTransformDemo {
    public static void main(String[] args) {
        IntUnaryOperator doubleIt = x -> x * 2;
        System.out.println(doubleIt.applyAsInt(21));
    }
}
~~~

Run:

~~~bash
javac --release 17 LambdaTransformDemo.java
java LambdaTransformDemo
~~~

Stdout:

~~~text
42
~~~

`javap -c -p LambdaTransformDemo` on standard `javac` will show an `invokedynamic` call site associated with instantiating the functional object, along with a helper lambda method when needed. The runtime links the call site according to the mechanism specified for lambdas. Whether a JVM generates a hidden class, allocates an object, or inlines the `applyAsInt` call is a matter of **runtime implementation and optimization**, not a mandatory conclusion from writing `x -> x * 2`.

Avoid claiming lambdas are guaranteed to be "faster than anonymous classes" or "zero-allocation". Benchmark the right workload and examine the specific runtime before concluding performance characteristics.

## 13. Inlining: Bytecode Still Has the Call, Yet Machine Code May Not

Suppose the source has:

~~~java
static int square(int value) {
    return value * value;
}

static int work(int x) {
    return square(x) + 1;
}
~~~

In `work`'s bytecode, `javac` typically emits an invocation to `square`; it is a standalone method in the class-file model. If `work` becomes hot code, the JIT may inline `square` into the native version of `work`, eliminating call overhead or further optimizing the expression.

**Both statements below can be true simultaneously:**

- `javap -c` shows the call to `square` inside `work`.
- JIT machine code for an active version of `work` **no longer contains an actual call to `square`** because the method body has been inlined.

There is no contradiction; the tools inspect **two different layers**. Confirming inlining requires JIT logs/observation (for instance, appropriate diagnostic flags on HotSpot, a profiler, or JIT analysis tools); `javap` is not enough.

Inlining also depends on code size, invocation counts, polymorphism, recursion, escape behavior, profiling, and JIT budgets. Do not assume a few-line method is **always** inlined.

## 14. Why Doesn't javac “Optimize Everything” Up Front?

A source compiler running before the application executes generally does not know:

- What values methods will receive during most invocations.
- Which branches occur most frequently under real business data.
- Which concrete object types appear at polymorphic call sites during steady-state execution.
- Which processor, cache, machine instruction set, and scheduling conditions will be used at runtime.
- Which additional classes may be loaded later, invalidating speculative optimization assumptions.

`javac` primarily needs to **produce compliant class files capable of running across compatible JVM environments**. The JIT can defer choices until real profiles/CPU info exist, accepting measurement and compilation cost to accelerate hot code.

However, the phrase "javac does not optimize" should only be understood as **javac does not act as a general-purpose optimizing native runtime compiler like the HotSpot JIT**. It still performs constant folding, language-mandated transformations, and bytecode choices that affect performance. Saying "all optimizations happen in the JVM" is too extreme.

## 15. Distinguishing JVM/JIT from Other Runtime Components

**Interpreter:** directly executes bytecode via interpretation; this is an execution mode for bytecode, not a translator from Java source to class files.

**JIT compiler:** produces machine code for selected code inside a JVM runtime. Not every JVM shares the same JIT or heuristics.

**Class loader and verifier:** load and verify class files; not the same as JIT optimizing methods. A class not found at runtime is a loading/linking/runtime-dependency issue, not proof that javac optimized wrongly.

**Garbage collector:** manages memory regions and reclaims unreachable objects. Escape analysis can affect allocation pressure, yet GC is not a "javac bytecode optimization pass".

**AOT/native-image compiler:** can compile part or all of a program to machine code ahead of execution using each tool's specific mechanism. That is a different pipeline from the standard `javac .java → .class → HotSpot JIT` example; do not force every Java application into a single model.

**Build tool:** Gradle/Maven manages classpaths, tasks, and incremental compilation, and may cache outputs. Skipping a build task is not JIT optimization; even without re-invoking `javac`, the JVM can still JIT-compile when running the program.

## 16. Observing the Right Layer with the Right Tool

| What You Want to Answer | Use | Do Not Infer |
| --- | --- | --- |
| How did the compiler emit the class file? | `javac` and `javap -c -p -v` | The JIT has already inlined methods |
| Was a constant expression folded? | Inspect bytecode/constant pool and JLS | Every computation is folded before runtime |
| Where do compile-time errors appear? | Diagnostics from `javac` | Runtime will have no exceptions |
| Which methods are JIT-compiled? | `-XX:+PrintCompilation` logs on HotSpot | All methods are optimized equally |
| Did the JIT actually inline / perform escape analysis? | JIT diagnostics, disassembly, or a suitable profiler | Reading source or `javap` alone is enough |
| Did steady-state speed and latency improve? | JMH/JFR/profiler, controlled measurements | A single `nanoTime` measurement settles it |
| Is behavior right under concurrency? | Tests and JMM/happens-before rules | The JIT fixes race conditions automatically |

### Reference Inspection Commands

In the directory containing `HotLoopDemo.java`:

~~~bash
javac -version
java -version
javac --release 17 HotLoopDemo.java
javap -c -p HotLoopDemo
java -Xint HotLoopDemo
java -XX:+PrintCompilation HotLoopDemo
~~~

On HotSpot, also use Java Flight Recorder (JFR) or a profiler when you need to find hot methods, allocations, and latency. Syntax, availability, and log volume depend on the JDK/JVM. For instance, `-XX:+PrintCompilation` adds many diagnostic lines alongside business stdout, so you cannot expect the entire screen to show only the line `10000000`.

You can compare `javap` on the same class before and after a long run. Unless recompiled or modified by a bytecode tool, the class file contents remain unchanged; the JIT does not persist machine code by overwriting `.class` files.

### Do Not Turn Debug Flags into a “New Optimization”

Flags like `-Xint`, `-XX:+PrintCompilation`, or inlining-info options primarily alter execution or diagnostic modes. They are not annotations for `javac`, do not modify Java source, and do not provide uniform optimization outcomes across every JVM vendor. Record exact VM versions and flags before comparing numbers.

## 17. Practical Scenarios: Identifying Misattributed Causes

### Scenario A — “javap shows invokevirtual so the method wasn't inlined”

**This judgment is false.** `javap` sees the call in the bytecode emitted by `javac`. The JIT can inline the method in machine code. Runtime evidence is required to know whether it occurred.

### Scenario B — “The JIT changed the constant result 42 after editing ConstantConfig”

If you recompile only the class containing `static final int LIMIT = ...` without recompiling the consumer, the consumer may retain the value inlined at compile time. First check **existing binaries and dependency rebuilds**, rather than immediately blaming the JIT.

### Scenario C — “There is new in Java source so it definitely allocates on the heap”

Not always true. The JIT may eliminate some allocations via escape analysis/scalar replacement. Yet you also cannot assert the compiler is forced to do so; measure/observe at runtime.

### Scenario D — “The second run is faster because of javac”

If class files did not change, `javac` did not run again. The difference may relate to JVM warm-up, JIT, caches, OS, GC, or measurement noise. Multi-measurement experiments are needed to isolate it.

### Scenario E — “Using --release 17 forces the JIT to use only Java 17 strategies”

`--release 17` controls **language/API/class-file format at compile time**. A newer JVM version can still run Java 17 class files with its own JIT and optimization algorithms. Do not equate bytecode target with the runtime VM version or machine configuration.

### Scenario F — “String + is always optimized into StringBuilder by javac”

Since JDK 9, compiling dynamic string concatenation on OpenJDK typically uses `invokedynamic`; constant concatenation may fold completely. Inspect bytecode generated by the actual compiler version rather than applying an older model to every JDK.

## 18. Checklist for Responsible Performance Analysis

1. **Identify the layer:** syntax/semantic error, bytecode shape, class loading, JIT, allocation, GC, or I/O? Each layer has different tools.
2. **Pin environment info:** `javac -version`, `java -version`, `--release`, OS, CPU, and flags.
3. **Verify behavior first:** inputs, outputs, exceptions, and concurrency semantics must be right before discussing optimization.
4. **Inspect bytecode if the question belongs to the compiler:** `javap -c -p -v`, check signatures, call sites, constants, and control flow.
5. **Observe runtime if the question belongs to the JIT:** warm-up, compilation logs, JFR/JMH, and profiling on a real JVM.
6. **Distinguish capability from evidence:** “the JIT can inline” differs from “this method was inlined in this run”.
7. **Measure before editing:** avoid rewriting Java source just from imagining that fewer objects or fewer method calls are guaranteed to be faster.
8. **Ensure reproducibility:** use the same class files, inputs, flags, and measurement procedure when comparing runtime configurations.

## 19. Self-Check

**Question 1.** `javap -c` shows `invokestatic SomeClass.helper`. Can we conclude HotSpot has not inlined that method?  
**Answer:** No. `javap` inspects bytecode; the JIT can inline the call inside compiled machine code.

**Question 2.** Can `System.out.println(40 + 2);` print `42` without adding at runtime?  
**Answer:** Yes. This is a constant expression that `javac` can fold before emitting bytecode.

**Question 3.** When `Point point = new Point(...)` creates a temporary object, is the JIT forced to allocate the object?  
**Answer:** Not necessarily; escape analysis/scalar replacement may reduce allocation. However, elimination is not guaranteed under all conditions.

**Question 4.** One class file runs at different speeds on two machines. Must this be because `javac` compiled it differently?  
**Answer:** No. JVM, JIT, CPU, workload, GC, and environment differ even with identical bytecode.

**Question 5.** Why does Java 17 `javac` typically emit `invokedynamic` for dynamic string concatenation?  
**Answer:** It is the mechanism from JEP 280 to decouple choosing how string concatenation is implemented from a fixed builder bytecode pattern, allowing flexible runtime linking and optimization.

**Question 6.** Why is the JIT allowed to perform speculative inlining without breaking polymorphism?  
**Answer:** The runtime uses appropriate guards/conditions and can deoptimize or fall back to general execution when assumptions stop holding.

**Question 7.** Do `java -Xint` and `java -XX:+PrintCompilation` alter `.class` files on disk?  
**Answer:** Typically no; these are HotSpot runtime/diagnostic options. They are not source-recompilation commands.

## 20. Key Takeaways

- `javac` **checks language rules and generates bytecode**, including desugaring/lowering and certain compile-time processing such as constant folding. Its output is class files.
- The JVM **loads and executes bytecode**. On HotSpot, the JIT can compile hot code regions into machine code based on profiling and runtime data.
- **Inlining, escape analysis, loop optimizations, tiered compilation, and deoptimization** are important runtime concepts. You cannot confirm they occurred from `javap` alone.
- The exact same `.class` file can be executed by an interpreter or different versions of machine code while still preserving Java semantics.
- Use `javap` to answer **what the compiler generated**, and runtime profiling/JIT diagnostics to answer **how the JVM executed and optimized it**.

### References

- [Javac command — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html).
- [Javap command — Oracle JDK 17](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
- [JEP 280 — Indify String Concatenation](https://openjdk.org/jeps/280).
- [Java SE 17 JLS: Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html).
- [Java SE 17 JVM Specification](https://docs.oracle.com/javase/specs/jvms/se17/html/index.html).
- [HotSpot Tiered Compilation — Microsoft Java Engineering](https://devblogs.microsoft.com/java/how-tiered-compilation-works-in-openjdk/).