# Comparing Pattern Matching vs. Polymorphic Dispatch: Performance and Design Choices (Java 21+)

## 1. The Main Question: Should You Use a `switch` Pattern or Polymorphic Method Calls?

In Java, the same operation can be selected based on an object's **runtime type** using two design approaches:

- **Polymorphic dispatch**: declare a method on a parent interface/class; each subtype provides an implementation and you call `obj.method()`. The JVM selects the appropriate implementation for the receiver object.
- **Pattern matching dispatch**: place the logic in an external handler function, using `switch (obj)` with `case Type(...)` or `case Type variable`; Java selects a case by type/structure and `when` condition, then executes the corresponding logic.

The two approaches do not only differ in syntax. They involve trade-offs in **where behavior lives**, **extensibility**, **number of type-check steps**, **JIT optimization potential**, and the cost of coordinating with actual computations/data reads.

**There is no universal rule that patterns are always faster than polymorphism, or vice versa.** HotSpot can optimize both; results depend on object types at the call site, the number of subtypes observed, branch logic, data, JDK version, warm-up time, and execution environment. Without running a proper benchmark, a statement like "A is X% faster than B" has no basis.

This article uses Java **21+** because `record patterns` and `pattern matching for switch` have been finalized since Java 21. We will write both approaches with **equivalent semantics**, verify correctness first, and design a measurement using **JMH** (Java Microbenchmark Harness).

## 2. Two Dispatch Models Seen from Code

Suppose a system receives three kinds of operations: a constant value, addition, and multiplication.

### Approach A — Polymorphism: Behavior Lives Inside Each Subtype

~~~java
sealed interface Operation permits Value, Add, Multiply {
    int viaMethod();
}

record Value(int number) implements Operation {
    public int viaMethod() { return number; }
}
record Add(int left, int right) implements Operation {
    public int viaMethod() { return left + right; }
}
record Multiply(int left, int right) implements Operation {
    public int viaMethod() {
        return left == 0 || right == 0 ? 0 : left * right;
    }
}
~~~

When calling:

~~~java
Operation operation = new Add(2, 3);
int result = operation.viaMethod(); // 5
~~~

The caller only knows the `Operation` interface. The JVM must execute the implementation method corresponding to the **runtime type of the receiver**. This is dynamic dispatch through an interface (at the bytecode level, typically `invokeinterface`); it is not a manually written chain of `instanceof` checks in source code.

### Approach B — Pattern Switch: Behavior Lives in a Handler Function

~~~java
static int viaPattern(Operation operation) {
    return switch (operation) {
        case Value(var number) -> number;
        case Add(var left, var right) -> left + right;
        case Multiply(var left, var right)
                when left == 0 || right == 0 -> 0;
        case Multiply(var left, var right) -> left * right;
    };
}
~~~

In this approach:

1. `switch` selects a case based on the subtype of `Operation`.
2. A `record pattern` extracts the components, e.g., `Add(var left, var right)`.
3. The `when` guard checks the condition only when the corresponding pattern matches.
4. The case returns the result of the switch expression.

Because `Operation` is `sealed` and all three subtypes are listed, the switch expression can be **exhaustive** without a `default` branch. The guarded case for `Multiply` is placed before the general case of the same record to avoid dominance errors.

**Design difference:** polymorphism distributes behavior branches across each subtype; pattern switch centralizes an operation at a single dispatch point. Nothing in these two code snippets alone proves which one runs faster after JIT compilation.

## 3. Comparison from the JVM and JIT Perspective

### 3.1. Polymorphic Dispatch Does Not Necessarily Always Cost an Expensive "Virtual Jump"

At the bytecode level, a call through an interface typically uses `invokeinterface`; a call through a class can use `invokevirtual`. However, when the JVM executes a hot path, HotSpot can rely on profiling and type analysis to optimize:

- **Monomorphic call site:** mostly/only one receiver type is observed at a call site. The JIT can infer the target, perform *devirtualization*, and **inline** the implementation.
- **Bimorphic call site:** two receiver types are commonly encountered. The JVM can optimize certain situations based on dominant types and profiling.
- **Megamorphic call site:** many receiver types appear. Inlining each target may be limited; however, the degree of impact still depends on the code, profile, and JIT.

Once a method is inlined, the dispatch overhead can practically disappear from the hot path. Therefore, saying "a virtual call is always slower than a chain of type checks" is inaccurate.

The terms mono/bi/mega describe the **receiver distribution at the call site** and actual runtime diversity, not merely the number of subtypes existing in the codebase. An interface with ten implementations can still have a monomorphic call site if that code path only receives one kind of object.

### 3.2. Pattern Switch Also Does Not Have a Fixed Cost

With a pattern switch, the bytecode and how HotSpot lowers case selection depend on the compiler/JDK and pattern structure. An implementation may use type checks, a bootstrap mechanism for type switches, conditional branches, and accessor calls to deconstruct records. **Do not assume** Java always emits a literal `if (obj instanceof X)` chain, nor assume every pattern switch is an O(1) jump table.

The JIT can inline component extraction or optimize some checks, but the benefit depends on the case. With **nested record patterns**, cost may come from reading multiple components and performing additional type/guard checks. With `when`, both the pattern and the condition must be evaluated along the case's flow.

Conversely, a polymorphic method might also need those exact same checks/component reads to compute the same result. **A comparison is only fair when both variants perform the same work.**

### 3.3. Why "Number of Cases" Does Not Predict Latency

Two switches with the same number of cases can still behave differently because of:

- Whether the **frequent** branch is selected early and whether the type dispatcher is optimized.
- Whether the pattern consists only of a type test or requires **multi-level deconstruction**.
- Whether the guard is simple or calls multiple methods with side effects/high cost.
- Input distribution: 99% one subtype vs. evenly distributed across multiple subtypes.
- Internal case cost: a few arithmetic operations vs. I/O calls, parsers, or collection processing.
- Whether object allocation and GC fall inside the measured path.
- Compiler/JIT ability to inline code, speculative optimization, and deoptimization.
- JDK vendor, JVM version, CPU, warm-up, flags, and machine state.

When the handler body performs a database or network call, a difference of a few dispatch operations may be negligible compared to I/O. Only when each call performs simple arithmetic hundreds of millions of times can dispatch and inlining ability have a noticeable impact.

## 4. Fair Comparison at the Design Level

| Criterion | Polymorphic dispatch | Pattern matching dispatch |
| --- | --- | --- |
| Where behavior lives | In the class/record implementing the interface | In an external `switch` function or handler |
| Calling API | `operation.viaMethod()` | `evaluate(operation)` |
| Adding a subtype | Subtype must implement the interface behavior; with sealed, `permits` must also be updated | With sealed exhaustive switch, handler code may need a new case |
| Adding a new operation | May require changing the interface and multiple subtypes | Add a new switch function without modifying existing subtypes |
| State/encapsulation | Behavior can use internal state and invariants | External logic usually needs public accessors/components |
| Direct type checks | Source code does not need type-based cases for primary behavior | Source code explicitly exposes subtype classification |
| Record patterns, guards | Not needed for method dispatch | Convenient for record deconstruction, `when`, nested matching |
| Null input | Calling a method on null throws NPE, unless checked beforehand | Switching on a null reference selector also throws NPE if `case null` is absent |
| Performance | Can be devirtualized/inlined; depends on type profile | Can optimize case selection/deconstruction; depends on workload/JIT |
| Testing | Test each subtype's implementation and behavior through the interface | Test each pattern, guard true/false, null/nested cases |

**No row in this table is a guarantee of speed.** They describe different structures and optimization opportunities that must be measured when optimization is an important requirement.

## 5. Verify Correctness Before Measuring Performance

A benchmark is meaningless if the two approaches return different results or one omits validation. Before measuring, align on:

- **Same input:** same set of objects, same order, and same subtype distribution.
- **Same computation:** for example, with `Multiply`, both variants handle `left == 0 || right == 0` identically.
- **Same error/null handling:** do not let one approach skip an exception while the other checks the condition.
- **Same number of results:** if one approach sums 1024 elements, the other must also compute 1024 elements.
- **Do not put data setup inside one benchmark without putting it in the other.**

A practical verification should use **assertions** to prove both functions produce equal results on the same sample inputs. The example in section 7 covers regular operations, zero short-circuiting, negative numbers, and null.

Getting the right results on a sample input set is not a mathematical proof of equivalence for every `int`; however, it is an essential check to rule out configuration errors before running JMH.

## 6. Null, Exhaustiveness, and Side Effects Can Cause Divergent Semantics

### 6.1. Null Input

~~~java
Operation operation = null;

// Polymorphism: operation.viaMethod() -> NullPointerException.
// Pattern switch without case null -> NullPointerException.
~~~

Both calls can throw NPE, but **the message, throw site, and stack trace are not necessarily identical**. In the complete example, we use `Objects.requireNonNull(operation, "operation")` in both methods to declare the same precondition.

If one method returns a default result for null using `case null` while the other throws NPE, the two methods are **not equivalent**. You must not include that discrepancy in a benchmark as if only the dispatch technique differed.

### 6.2. Sealed and Exhaustive Switch

~~~java
sealed interface Operation permits Value, Add, Multiply {}
~~~

If all subtypes are listed in a pattern switch, the compiler can check exhaustiveness. Adding a new subtype can make the switch non-exhaustive and require updating it. However, an interface containing the `viaMethod()` method also forces a new concrete subtype to implement that method. **Both provide compile-time checking**, differing only in where behavior is placed and which point needs updating.

If you use `default` in a switch to swallow new subtypes, you may lose an important compile-time signal. When the domain requirement is "every subtype must be handled intentionally," prefer an exhaustive switch over a sealed hierarchy where appropriate.

### 6.3. Side Effects

If a polymorphic method performs logging, mutation, caching, lazy-loading, or clock reads, while the switch only computes numbers, **they are not the same business logic**. A record pattern can invoke accessors; a custom-defined accessor can contain behavior and is not always a "free field read."

To measure dispatch in isolation, prefer pre-initialized data, pure computations, and no I/O. To evaluate *end-to-end performance*, measure in the context of a real use case where side effects are a required part of the business logic.

## 7. Complete Java 21+ Program: Same Results, Two Dispatch Approaches

Save as **`PatternVsDispatchDemo.java`**:

~~~java
import java.util.Objects;

public class PatternVsDispatchDemo {
    sealed interface Operation permits Value, Add, Multiply {
        int viaMethod();
    }

    record Value(int number) implements Operation {
        public int viaMethod() { return number; }
    }

    record Add(int left, int right) implements Operation {
        public int viaMethod() { return left + right; }
    }

    record Multiply(int left, int right) implements Operation {
        public int viaMethod() {
            return left == 0 || right == 0
                    ? 0 : left * right;
        }
    }

    static int viaPolymorphism(Operation operation) {
        Objects.requireNonNull(operation, "operation");
        return operation.viaMethod();
    }

    static int viaPattern(Operation operation) {
        Objects.requireNonNull(operation, "operation");
        return switch (operation) {
            case Value(var number) -> number;
            case Add(var left, var right) -> left + right;
            case Multiply(var left, var right)
                    when left == 0 || right == 0 -> 0;
            case Multiply(var left, var right) -> left * right;
        };
    }

    public static void main(String[] args) {
        Operation[] operations = {
            new Value(7), new Add(2, 3), new Multiply(4, 5),
            new Multiply(0, 9), new Multiply(8, 0),
            new Value(-3), new Add(-5, 1), new Multiply(-2, 3)
        };

        int totalVirtual = 0, totalPattern = 0;
        for (Operation operation : operations) {
            int virtualResult = viaPolymorphism(operation);
            int patternResult = viaPattern(operation);

            if (virtualResult != patternResult) {
                throw new AssertionError(operation + " -> "
                        + virtualResult + " != " + patternResult);
            }

            System.out.println(
                    operation.getClass().getSimpleName()
                    + ": " + virtualResult + " = " + patternResult);

            totalVirtual += virtualResult;
            totalPattern += patternResult;
        }

        System.out.println("Tổng: "
                + totalVirtual + " = " + totalPattern);

        try {
            viaPolymorphism(null);
        } catch (NullPointerException ex) {
            System.out.println("Virtual null: " + ex.getMessage());
        }

        try {
            viaPattern(null);
        } catch (NullPointerException ex) {
            System.out.println("Pattern null: " + ex.getMessage());
        }
    }
}
~~~

Compile/run with JDK 21 or later:

~~~bash
javac --release 21 PatternVsDispatchDemo.java
java PatternVsDispatchDemo
~~~

Output:

~~~text
Value: 7 = 7
Add: 5 = 5
Multiply: 20 = 20
Multiply: 0 = 0
Multiply: 0 = 0
Value: -3 = -3
Add: -4 = -4
Multiply: -6 = -6
Tổng: 19 = 19
Virtual null: operation
Pattern null: operation
~~~

**Explanation:**

- `Value` returns its integer component; `Add` returns the sum; `Multiply` performs a guard/short-circuit for zero arguments.
- In `viaPolymorphism`, the call site uses `operation.viaMethod()`. For each different record, the JVM selects the corresponding implementation.
- In `viaPattern`, `switch` uses record patterns; the `when` guard is evaluated before the general `Multiply` branch.
- Both return the same results across eight inputs, including negative numbers and zero, and print a sum of 19.
- Both execute `Objects.requireNonNull` to declare the same null policy.
- The output above is a **correctness check**, not timing data.

## 8. Why Shouldn't You Use `System.nanoTime()` in a Simple Loop Yourself?

An unreliable example:

~~~java
long started = System.nanoTime();
for (int i = 0; i < 100_000; i++) {
    result += operation.viaMethod();
}
long elapsed = System.nanoTime() - started;
System.out.println(elapsed);
~~~

Problems:

1. HotSpot **warm-up** and profiling can change machine code after many executions; initial measurements do not represent steady state.
2. The compiler may recognize redundant work, constants, or unused results and perform **constant folding / dead-code elimination**.
3. `System.nanoTime()` only measures a time interval; it does not provide statistical design, forks, or benchmark error control.
4. GC, OS scheduling, CPU frequency, machine temperature, and background activity introduce noise.
5. If the input set consists entirely of one subtype, the result does not represent a mixed-subtype call site.
6. Placing data allocation inside the loop can cause you to measure allocation/GC instead of just dispatch.
7. A single run might happen to be faster by luck without **statistical significance**.

The recommended tool is **JMH** from the OpenJDK project. JMH helps manage warm-up, measurement iterations, JVM forks, benchmark arguments/parameters, and result consumption. However, JMH **does not automatically make a measurement design valid**: the test workload must still be representative and benchmark code needs to be reviewed.

## 9. JMH Design: Keep the Computation Constant and Vary the Subtype Distribution

For a relatively fair comparison, the benchmark should:

- Initialize instances before measurement using `@Setup(Level.Trial)`.
- Have **both benchmarks** iterate over the same `Operation[]` array and compute the same sum.
- Return the sum so JMH consumes the result, reducing the risk of work being eliminated.
- Test multiple distributions: **monomorphic** (one subtype), **bimorphic** (two subtypes), and **mixed** (three subtypes, alternating zero/nonzero).
- Choose the same warm-up, measurement, fork, and JVM parameters for both methods.
- Run **separate correctness tests**; JMH results cannot replace assertions.
- Do not put `System.out.println` or per-item allocations inside the `@Benchmark` region.

### A Self-Contained Benchmark

In a JMH project with package `bench`, place the file **`src/main/java/bench/PatternDispatchBenchmark.java`**:

~~~java
package bench;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 7, time = 1)
@Fork(3)
@State(Scope.Thread)
public class PatternDispatchBenchmark {
    sealed interface Op permits V, A, M {
        int eval();
    }

    record V(int n) implements Op {
        public int eval() { return n; }
    }

    record A(int x, int y) implements Op {
        public int eval() { return x + y; }
    }

    record M(int x, int y) implements Op {
        public int eval() {
            return x == 0 || y == 0 ? 0 : x * y;
        }
    }

    @Param({"mono", "bi", "mixed"})
    public String distribution;

    private Op[] inputs;

    @Setup(Level.Trial)
    public void prepare() {
        inputs = new Op[1024];

        for (int i = 0; i < inputs.length; i++) {
            inputs[i] = switch (distribution) {
                case "mono" -> new V(i);

                case "bi" -> (i & 1) == 0
                        ? new V(i) : new A(i, 1);

                case "mixed" -> switch (i & 3) {
                    case 0 -> new V(i);
                    case 1 -> new A(i, 1);
                    case 2 -> new M(i, 0);
                    default -> new M(i, 3);
                };

                default -> throw new IllegalArgumentException(
                        "Unknown distribution");
            };
        }
    }

    static int viaPattern(Op op) {
        return switch (op) {
            case V(var n) -> n;
            case A(var x, var y) -> x + y;
            case M(var x, var y) when x == 0 || y == 0 -> 0;
            case M(var x, var y) -> x * y;
        };
    }

    @Benchmark
    public int polymorphic() {
        int sum = 0;
        for (Op op : inputs) {
            sum += op.eval();
        }
        return sum;
    }

    @Benchmark
    public int patternSwitch() {
        int sum = 0;
        for (Op op : inputs) {
            sum += viaPattern(op);
        }
        return sum;
    }
}
~~~

The snippet above requires the JMH dependency, annotation processor, and build setup; it **cannot** be compiled with just `javac` on a single file without JMH on the classpath. It is a **benchmark example to run inside a JMH project**, unlike the complete Java program in section 7 which was verified directly with the JDK.

Each time JMH invokes a `@Benchmark` method, the code inside iterates over **1024 elements**. Therefore, the `ns/op` unit printed by JMH is **nanoseconds per benchmark method invocation**, not nanoseconds per individual dispatch. You can roughly divide by 1024 to see the average cost per element, but that number still includes loop overhead, array reads, summation, and general optimizations—not "pure dispatch latency."

**Important:** both JMH methods return the same sum, yet the JIT is free to inline/transform the code differently. That is precisely what is worth observing; you should not force the JVM to disable normal optimizations unless you are studying a specific aspect.

## 10. Create a JMH Project with Maven and Run the Benchmark

According to the official OpenJDK guide, you should use the JMH **Maven archetype** to get the proper build configuration and annotation processor, rather than just adding the `jmh-core` jar to a project without the generator.

Example creating a project with JMH **1.37** (a released version available on Maven Central):

~~~bash
mvn archetype:generate -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DarchetypeVersion=1.37 \
  -DgroupId=bench \
  -DartifactId=dispatch-bench \
  -Dversion=1.0-SNAPSHOT
~~~

On **PowerShell**, write the command on **one line** or use PowerShell's line-continuation character (backtick); the trailing `\` above is Bash line continuation. Set the Maven compiler release to **21** in the project's `pom.xml` if the generated configuration does not already use Java 21:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

The XML snippet only illustrates the required properties, not a standalone `pom.xml`. If the project configures the compiler in a separate plugin, adjust the source version in the right place so Java 21 features are accepted.

Place the benchmark class in package `bench` just as in the example in section 9, then:

~~~bash
mvn clean package
java -jar target/benchmarks.jar PatternDispatchBenchmark
~~~

JMH will run measurements for each `distribution` value and both benchmark methods. Execution time can be noticeable because the configuration includes warm-up, measurement, and 3 forks. This is intentional to reduce noise; do not strip everything down to a single measurement to draw conclusions.

To export machine-readable data, you can use:

~~~bash
java -jar target/benchmarks.jar PatternDispatchBenchmark \
  -rf json -rff results.json
~~~

For PowerShell, write it on one line. The commands and paths above are guidance configurations; **this article does not present fabricated JMH numbers**.

## 11. Reading a JMH Report Properly

With `@BenchmarkMode(Mode.AverageTime)` and `@OutputTimeUnit(TimeUnit.NANOSECONDS)`, the report shows the average time per **benchmark invocation**, typically in `ns/op`. **A smaller value** means lower time per invocation, provided all comparison conditions are equivalent.

Information that must be read together:

- **Benchmark name**: `polymorphic` or `patternSwitch`.
- **Parameter `distribution`**: `mono`, `bi`, or `mixed`. Do not compare across mismatched distributions.
- **Score**: average `ns/op` time per benchmark method call.
- **Error/CI**: margin of error and variability (depending on report mode); a difference that is tiny relative to noise is not enough to draw conclusions.
- **Fork/iterations/JDK**: execution conditions; the same test on a different JDK or with different flags can yield different results.
- **Multiple runs**: check stability, rather than cherry-picking a single run with nice numbers.

A **completely hypothetical example** to practice interpreting differences (not actual benchmark results):

~~~text
Hypothetical example for the same distribution:
polymorphic     1200 ns/op
patternSwitch   1260 ns/op
Difference      60 ns per traversal of 1024 elements
~~~

Here `patternSwitch` is about **5%** higher on the total-per-invocation metric (60/1200). However, you cannot conclude that polymorphism is statistically significantly faster without examining the error, forks, data, and measurement environment. Simply switching the test set to `mixed` or upgrading the JDK could change the order.

When possible, cross-check microbenchmarks with a profiler/JFR and end-to-end latency/throughput of the real use case before deciding to change architecture for performance.

## 12. When Does Pattern Switch Have a Design Advantage?

Pattern matching is often a good fit when:

1. **Closed data types**: a small sealed interface/record hierarchy controlled by your own module.
2. **A new operation needs to handle multiple subtypes**: adding a single switch function can be cleaner than modifying every subtype.
3. **Transformation/formatting/serialization/projection**: the logic naturally fits "classify data by structure and then transform."
4. **Nested record patterns**: deconstructing structured data without multi-level casts.
5. **Exhaustiveness**: wanting the compiler to warn when a subtype is added and an operation has not handled it completely.

Example:

~~~java
sealed interface Payment permits Cash, Card {}
record Cash(int amount) implements Payment {}
record Card(int amount, String last4) implements Payment {}

static String label(Payment payment) {
    return switch (payment) {
        case Cash(var amount) -> "Cash: " + amount;
        case Card(var amount, var last4) -> "Card ****" + last4;
    };
}
~~~

This example is a **label formatting** operation by subtype. It does not prove pattern switch is faster than `payment.label()`. The clearer benefit lies in **adding a data-presentation operation** without having to modify the data records.

If data comes from outside the module and uncontrolled subtypes may be added, a sealed hierarchy and exhaustive switch can introduce constraints that must be considered upfront.

## 13. When Does Polymorphic Dispatch Have a Design Advantage?

Polymorphism is often a good fit when:

1. **Behavior is an intrinsic part of the object**: for example, tax calculation strategies, compression algorithms, or pricing methods.
2. **Each subtype maintains its own invariants/encapsulation**, without wanting to expose implementation details to an external switch.
3. **The set of subtypes is extensible**, provided by plugins or independent modules.
4. **Multiple call sites invoke the same operation**: an interface method serves as a clear contract so callers do not duplicate switches.
5. **The processing flow mainly invokes behavior**, rather than externally transforming data structures.

Example:

~~~java
interface Discount {
    int apply(int price);
}

final class FixedDiscount implements Discount {
    public int apply(int price) {
        return Math.max(0, price - 100);
    }
}

final class PercentDiscount implements Discount {
    public int apply(int price) {
        return price * 90 / 100;
    }
}

static int discountedPrice(Discount discount, int price) {
    return discount.apply(price);
}
~~~

In this example, "how to calculate a discount" is a clear contract belonging to each strategy. A switch classifying by concrete class would couple the code to the implementations and could reduce extensibility.

Note: interface methods can be inlined on hot paths; do not replace them with pattern matching just because you assume interface calls are always slow.

## 14. Common Benchmarking Mistakes

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Measuring a single `nanoTime` loop | Results affected by JIT warm-up, noise, GC | Use JMH warm-up, measurement, forks |
| Benchmarking only one subtype when production has many | Results favor monomorphic call sites | Measure multiple `distribution` values representing the workload |
| One approach performs validation/caching while the other does not | Comparing different work | Standardize semantics, assert output/exceptions |
| Creating objects inside one benchmark, but outside measurement in the other | Unfairly measuring allocation/GC | Set up the same data before the benchmark |
| Not using the computed result | JIT may eliminate the work | Return the result or use JMH `Blackhole` |
| Printing logs inside `@Benchmark` | I/O dominates total time | Do not log inside the timed region |
| Treating `ns/op` as nanoseconds per element | Each invocation loops over 1024 elements | State the unit clearly, divide cautiously, and account for overhead |
| Looking only at score, ignoring error and variance | Small differences may just be noise | Check variation, CI, multiple forks/runs |
| Measuring on one JDK and claiming Java always behaves that way | JIT/compiler/JDK can change | Record JDK/version/flags, re-measure on target environment |
| Changing architecture over a tiny microbenchmark | Benefit may be negligible end-to-end | Profile and measure real use cases |
| Ignoring `null`/exception paths | Two implementations may diverge in contract | Test behavior and preconditions separately |
| Assuming sealed exhaustive guarantees speed | It is a compile-time completeness check | Evaluate design and performance separately |

## 15. Project Decision Checklist

When reviewing a PR that changes `operation.viaMethod()` to `switch (operation)`, ask in order:

1. **Same semantics?** Are multiple subtypes, guard true/false, null, errors, and edge cases tested?
2. **What are the data and extension models?** Closed sealed/record data types or an open interface for plugins?
3. **Who owns the logic?** Behavior encapsulated in subtypes or an external transformation over subtypes?
4. **Is this actually a bottleneck?** Profile CPU/allocations before optimizing by intuition.
5. **Is the benchmark fair?** Same work, input distribution, no skewed I/O/allocations, sufficient warm-up/forks.
6. **Is the difference stable and significant?** Check score, error, multiple runs, and the same environment.
7. **Is the design change worth it?** Readability, maintainability, exhaustiveness, and extensibility usually matter more than micro-optimization when dispatch time does not dominate.

**Practical conclusion:** without clear performance evidence, prefer the model with clear behavioral ownership and easier maintainability. Only change the dispatch approach for speed when a representative benchmark shows meaningful impact on the real use case.

## 16. Practice Exercises

**Exercise 1 — Design.** Given `sealed interface Event permits Created, Deleted {}` and three operations: formatting to text, saving audit logs, and applying business rules. Which operation is suitable for an external pattern switch, and which should live in a service or subtypes? Explain based on encapsulation and extensibility.

**Exercise 2 — Distribution.** A method calls `work.eval()` 1 million times, with 99.9% of receivers being `Value`. Another benchmark uses `Value`, `Add`, and `Multiply` in roughly equal proportions. Why might they yield different relative results?

**Exercise 3 — Benchmark.** Analyze the flaw of a `nanoTime` loop that calls `new Add(1,2).viaMethod()` every iteration while the pattern benchmark uses a pre-initialized array of `Add`. Do the two snippets measure the same work?

**Exercise 4 — Units.** JMH runs a benchmark method processing an array of 1024 elements and displays `2000 ns/op`. Can you say each dispatch takes 2000 ns? If you simply divide by 1024 to get ~1.95 ns/item, what other costs are mixed in?

**Exercise 5 — Correctness.** In the section 7 example, if you remove `when left == 0 || right == 0` while still using `left * right`, do the `int` results remain the same? If so, why can changing the guard expression still affect a microbenchmark, and why must the code express the **same logic path** before measuring?

**Hints:**

- Exercise 1: formatting to text is often convenient with a pattern switch on a closed hierarchy; business rules and auditing also depend on context and transactions/authorization, so consider a service; there is no single answer for every domain.
- Exercise 2: the JIT optimizes call sites based on type profiles, and a pattern switch has different classification paths when the distribution changes.
- Exercise 3: no; one benchmark also measures object allocation/GC while the other does not; initialize outside the timed region or measure allocation in both.
- Exercise 4: no, `ns/op` is for the **entire invocation**. Dividing by 1024 only approximates the average cost including loop overhead, array reads, computation, dispatch, and general optimizations.
- Exercise 5: with pure `int` multiplication, multiplying by zero still yields zero so the results may match. However, the number of conditions/paths and JIT optimization opportunities differ; a benchmark must clearly decide whether it is comparing the same algorithm or two **different ways of writing the business logic**.

## 17. Chapter Summary

- **Polymorphic dispatch** places behavior in subtypes and calls `obj.method()`; HotSpot can devirtualize/inline depending on the type profile.
- **Pattern dispatch** selects branches using `switch`/record patterns/`when`; convenient when data is closed and multiple external transformations are needed.
- **Do not** attribute higher speed to either approach based solely on syntax, number of subtypes, or number of cases. JIT cost, deconstruction, guards, inlining, and workload can determine the outcome.
- **Test correctness** first, **benchmark with JMH** using the same data and computation next, and then confirm impact with profiling/end-to-end measurements.
- If speed is not a bottleneck, choose the design that protects invariants, reduces coupling, and scales with the project's requirements.

### References

- [OpenJDK — JMH project](https://openjdk.org/projects/code-tools/jmh/): how to create a Maven benchmark, why to use the archetype, and pitfalls to note.
- [Oracle — Avoiding Benchmarking Pitfalls on the JVM](https://www.oracle.com/technical-resources/articles/java/architect-benchmarking.html): JIT, dead-code elimination, warm-up, JMH.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): type patterns, record patterns in switch, guards, and exhaustiveness (Java 21).
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): deconstruction and nested record patterns.
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): record patterns/switch pattern matching as finalized features.
- [OpenJDK HotSpot — C2 call optimization source](https://github.com/openjdk/jdk/blob/master/src/hotspot/share/opto/doCall.cpp): call optimization/inlining source by receiver profile (implementation details are not a performance guarantee).
