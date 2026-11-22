# Performance vs. Readability Trade-offs in Java Pattern Matching

**Topic:** Java Core Pattern Matching — Performance. This lesson focuses on choosing between `if-else`, `instanceof` type patterns, `switch` with record patterns, and polymorphism in **Java 21 and later**. Type patterns for `instanceof` have been stable since Java 16; record patterns (JEP 440) and pattern matching for `switch` (JEP 441) became standard in Java 21.

## 1. Asking the Right Question: Are Readability and Speed Always Opposed?

When facing a chain of type-based branches, we can write the same business logic in several ways:

- `instanceof` followed by a manual cast in the old Java style;
- `instanceof T value` to test and bind a type pattern;
- a `switch` expression with type patterns or record patterns;
- calling a polymorphic method on the object, if the behavior belongs to the subtype.

The goal of optimization is not to write the shortest code, nor to assume that a new pattern-based construct will run faster. A good approach must satisfy **correctness**, **maintainability**, **actual performance characteristics**, and **testability**. In most cases, clarity and correctness should be the default; only trade off clarity when measurement data shows that a hot path genuinely needs optimization.

More readable code also has technical value: catching missing branches, wrong guards, unhandled nulls, or un-updated changes when adding a subtype early. The cost of those bugs can exceed the few nanoseconds saved by an unmeasured micro-optimization.

**Principle:** Pattern matching is a **tool for expression and type checking**. It is not a guarantee of throughput, latency, memory usage, or higher speed than every other way of writing code.

## 2. Ways to Branch for the Same Business Logic

Consider a closed operation type:

~~~java
sealed interface Operation permits Add, Multiply, Reset {}

record Add(int left, int right) implements Operation {}
record Multiply(int left, int right) implements Operation {}
record Reset() implements Operation {}
~~~

We need to compute the result:

- Add returns the sum of the two numbers.
- Multiply returns the product of the two numbers.
- Reset returns 0.
- A null input returns -1 according to the illustrative contract.

Depending on the data types and project history, there are three ways to implement this.

### 2.1. `instanceof` and Manual Cast

~~~java
static int legacy(Operation operation) {
    if (operation instanceof Add) {
        Add a = (Add) operation;
        return a.left() + a.right();
    } else if (operation instanceof Multiply) {
        Multiply m = (Multiply) operation;
        return m.left() * m.right();
    } else if (operation instanceof Reset) {
        return 0;
    }
    return -1;
}
~~~

This approach is valid but repeats the type check and cast. Maintainers must verify that the cast matches the `instanceof` condition. `instanceof` returns false for null, so null falls through to `return -1`.

### 2.2. Type Patterns in `instanceof`

~~~java
static int typed(Operation operation) {
    if (operation instanceof Add a) {
        return a.left() + a.right();
    } else if (operation instanceof Multiply m) {
        return m.left() * m.right();
    } else if (operation instanceof Reset) {
        return 0;
    }
    return -1;
}
~~~

**Readability advantage:** The variables `a` and `m` are bound as soon as the type check succeeds; there is no more manual casting. This is often the lowest-risk choice when refactoring an old if-else chain while keeping the same control-flow shape.

**On speed:** Removing the cast syntax does not by itself prove that runtime decreases. The compiler and JVM may already have optimized away redundant casts in the legacy code. To draw a conclusion, you must measure the versions under the same conditions, not infer from the number of Java source lines.

### 2.3. `switch` Expression with Record Patterns

~~~java
static int switched(Operation operation) {
    return switch (operation) {
        case Add(int left, int right) -> left + right;
        case Multiply(int left, int right) -> left * right;
        case Reset() -> 0;
        case null -> -1;
    };
}
~~~

`switch` gathers all variants into a single value-returning expression. A record pattern such as `Add(int left, int right)` both checks the record type and extracts its components. Because `Operation` is a sealed interface and all three subtypes are covered, no `default` is needed. The `case null` branch preserves the null policy of the two if-else versions.

**Maintainability benefit:** If a new permitted subtype is added and recompiled, a `switch` expression missing a case will produce an exhaustiveness error. The two if-else versions could still silently return -1 for that subtype. This is worth considering even when benchmarks show the approaches have nearly identical speed.

**On speed:** Java does not guarantee that `switch` is faster than `if-else`. The outcome depends on the selector type, case set, JDK version, JIT optimizations, input distribution, and the work performed inside each branch.

## 3. Complete Java 21 Program: Verifying Behavioral Equivalence

This example **does not claim to be a performance benchmark**. It is a more important first step: confirming that all three implementations satisfy the same contract across multiple scenarios.

Save the entire code into **PatternTradeoffDemo.java**:

~~~java
public class PatternTradeoffDemo {
    sealed interface Operation permits Add, Multiply, Reset {}

    record Add(int left, int right) implements Operation {}
    record Multiply(int left, int right) implements Operation {}
    record Reset() implements Operation {}

    static int legacy(Operation operation) {
        if (operation instanceof Add) {
            Add a = (Add) operation;
            return a.left() + a.right();
        } else if (operation instanceof Multiply) {
            Multiply m = (Multiply) operation;
            return m.left() * m.right();
        } else if (operation instanceof Reset) {
            return 0;
        }
        return -1;
    }

    static int typed(Operation operation) {
        if (operation instanceof Add a) {
            return a.left() + a.right();
        } else if (operation instanceof Multiply m) {
            return m.left() * m.right();
        } else if (operation instanceof Reset) {
            return 0;
        }
        return -1;
    }

    static int switched(Operation operation) {
        return switch (operation) {
            case Add(int left, int right) -> left + right;
            case Multiply(int left, int right) -> left * right;
            case Reset() -> 0;
            case null -> -1;
        };
    }

    public static void main(String[] args) {
        Operation[] operations = {
            new Add(2, 3),
            new Multiply(4, 5),
            new Reset(),
            null,
            new Add(-1, 1)
        };

        for (Operation operation : operations) {
            int before = legacy(operation);
            int withTypePatterns = typed(operation);
            int withSwitch = switched(operation);

            if (before != withTypePatterns || before != withSwitch) {
                throw new AssertionError("Different behavior");
            }

            System.out.println(
                    before + " | " + withTypePatterns + " | " + withSwitch);
        }
    }
}
~~~

Compile and run with **JDK 21 or newer**:

~~~bash
javac PatternTradeoffDemo.java
java PatternTradeoffDemo
~~~

Exact output:

~~~text
5 | 5 | 5
20 | 20 | 20
0 | 0 | 0
-1 | -1 | -1
0 | 0 | 0
~~~

**Interpretation:** All three approaches return the same result for Add, Multiply, Reset, null, and Add with a negative operand. Each row shows the values **legacy | typed | switched**, not time units or performance scores.

Because a null input appears in the array, the program uses `Operation[]` instead of `List.of(...)` (which does not allow null elements). Omitting `default` in `switched` is still valid because the selector is the sealed `Operation` and the null branch is handled explicitly.

This is a behavioral check for the tested samples; it **does not prove equivalence for every possible state**, and in particular does not prove which approach is faster. When refactoring real code, you should add tests for exceptions, guards, side effects, and future subtypes.

## 4. Where Does the Actual Execution Cost Lie?

Source code only describes logic; the HotSpot JVM has an interpreter, a JIT compiler, and many profile-guided optimizations. Therefore, you should not assign a fixed cost solely from the shape of a Java expression.

### 4.1. Type Checks and Casts

`instanceof` checks whether an object conforms to a type. A type pattern adds variable binding in source code, which does not mean creating a new object. A cast after a type check in the legacy version also does not necessarily mean an extra full runtime check after JVM optimization.

In a frequently called method, the JIT can leverage learned type information. The optimization potential depends on how the code is compiled, how polymorphic the inputs are, and the conditions inside the method.

### 4.2. Record Patterns and Component Access

`case Add(int left, int right)` needs to extract two components from the `Add` object through record deconstruction. **There is no requirement to create a new record** just because that pattern appears. However, matching still involves type checks and component accesses; with nested record patterns, extraction can go deeper.

If a record has custom accessors, those accessors may contain logic or side effects. Therefore, do not claim that all deconstruction is free, nor assume that using a record pattern necessarily causes allocation. You need to inspect bytecode/profiles and measure on real data.

### 4.3. Switch Dispatch and `if-else` Chains

An `if-else` chain evaluates each condition in order, though the JIT may alter how it executes optimizations as long as semantics are preserved. A `switch` with patterns has its own branch-selection mechanism and is not automatically equivalent to a `switch` on integers or enums at the machine-code level.

Effectiveness depends on **common inputs**. If 99% of values are `Add` and the `Add` branch comes first, a short `if-else` chain can perform well. If inputs are diverse, with many subtypes and many branches, the cost can change. There is no fixed case-count threshold at which `switch` always becomes faster.

### 4.4. Conditions When Matching a Case

A guard such as:

~~~java
// Illustrates only the switch branch for the Add record.
case Add(int left, int right) when left > 0 && right > 0 ->
        left + right;
case Add(int left, int right) ->
        0;
~~~

performs additional comparisons and has a fallback branch. Guards can help code express rules more clearly, but they do not automatically make code faster. At the same time, the more specific guarded case must precede the general case to avoid dominance errors.

If the same expensive check is repeated across multiple guards, you can consider normalizing the data or extracting a clearly named method. However, only optimize once tests confirm that results, evaluation order, and exception behavior remain unchanged.

### 4.5. Work Inside a Case Often Matters More

If a case performs a database query, parses large JSON, reads a file, or makes a network call, the dispatch cost may be tiny compared to I/O. In that situation, prioritizing query time, batching, valid caching, or reducing the number of calls can have a far greater impact than changing `instanceof` syntax to `switch`.

Conversely, in a method processing millions of small events per second, branching and component access can be worth measuring. **Only profiling tells you which path is actually hot.**

## 5. What Indirect Performance Benefits Does Readability Bring?

An easy-to-understand code path helps developers optimize **in the right place**:

| Criterion | `if-else` with type pattern | `switch` with type/record pattern |
| --- | --- | --- |
| Two or three independent checks | Usually very readable | Can feel slightly over-structured |
| Classifying many subtypes that all return a value | Can become long or repeat `return` | Branches are in one place, easy to review |
| Each subtype has record data to extract | Uses accessors after variable binding | Record pattern expresses shape directly |
| Need to preserve null behavior like legacy `if-else` | `instanceof` naturally returns false for null | Requires an explicit `case null` decision |
| Sealed type domain, want to catch missing subtypes | Does not enforce exhaustiveness automatically | `switch` expression without `default` checks exhaustiveness |
| Long branch logic / many side effects | Can extract methods or keep `if-else` | Should extract bodies into dedicated methods |
| Hot path with a benchmarked difference | May be the right choice | May be the right choice |
| Optimizing without measurement | Do not conclude it is faster | Do not conclude it is faster |

An **exhaustive switch** makes the compiler warn when a subtype is added, which is valuable because it prevents operational bugs and reduces code-review burden. Conversely, cramming deeply nested record patterns into a single case can make reasoning about the logic harder. Clarity, bug detection, and execution speed must be balanced according to context.

## 6. When Is Polymorphism Clearer Than `switch`?

Suppose every subtype of `Operation` is responsible for computing a value **from its own data**. You can design an interface with behavior:

~~~java
// Illustrates an alternative design; not combined with the code in section 3.
sealed interface Calculable permits Sum, Product {
    int evaluate();
}

record Sum(int left, int right) implements Calculable {
    @Override
    public int evaluate() {
        return left + right;
    }
}

record Product(int left, int right) implements Calculable {
    @Override
    public int evaluate() {
        return left * right;
    }
}
~~~

The caller only needs **value.evaluate()**. This can make sense if `evaluate` is core behavior of each type and you add new subtypes more often than you add new operations.

Meanwhile, if the same data must be processed by many independent operations (for example, auditing, reporting, conversion, scoring), consumers using `switch` over a sealed hierarchy can be clearer, avoiding pushing every external concern into the domain model.

**On performance:** polymorphic calls are not inherently slow. The JIT can optimize or inline calls based on profiles, though there is no guarantee they are always better than `switch`. Do not replace a clean domain design with a series of switches just to avoid a virtual method call without data.

## 7. Proper Microbenchmarking: Measure Before Concluding

Timing a Java loop directly with `System.nanoTime()` and taking a single result is an easy way to reach wrong conclusions. The JVM needs **warmup** and may recompile code once it collects profiles; GC, the scheduler, dead-code elimination, constant folding, and variations in data distribution all change timings significantly.

For comparing `legacy`, `typed`, and `switched`, the standard tool is **JMH (Java Microbenchmark Harness)**. JMH is a separate library, **not built into the JDK**; running it requires configuring dependencies/annotation processors and a benchmark project.

A meaningful experimental design:

1. **Fix the behavior:** all three approaches return the same value for the same input; run tests before benchmarking.
2. **Generate data outside the measured region:** do not include the cost of `new Add(...)`, array creation, `println`, or `String` creation if the goal is only dispatch cost.
3. **Use multiple subtype distributions:** e.g., 90% `Add`, balanced across all three subtypes, and data that causes guards to evaluate to false; each distribution produces a different result.
4. **Warmup, measurement, forks:** run multiple independent iterations to avoid overvaluing a lucky run.
5. **Prevent the compiler from eliminating work:** return the result to the benchmark framework or use `Blackhole` appropriately.
6. **Choose the right metric:** throughput or average time, while also checking allocation, GC, and CPU profiles if they affect the system.
7. **Control the environment:** same JDK version, JVM flags, hardware, GC configuration, and background load; do not compare runs across different configurations.
8. **Report result variance:** check error margins/confidence intervals; small differences may lie within measurement noise.

### Illustrative JMH Harness

The following snippet is **illustrative code that depends on the JMH library**, not a standalone program that only needs the JDK. It uses the methods from the `PatternTradeoffDemo` class in section 3; a JMH-configured project is required. Sample data is created in setup rather than on every measured invocation.

~~~java
import org.openjdk.jmh.annotations.Benchmark;
import org.openjdk.jmh.annotations.Level;
import org.openjdk.jmh.annotations.Scope;
import org.openjdk.jmh.annotations.Setup;
import org.openjdk.jmh.annotations.State;

@State(Scope.Thread)
public class PatternBenchmark {
    private PatternTradeoffDemo.Operation[] samples;
    private int index;

    @Setup(Level.Trial)
    public void setup() {
        samples = new PatternTradeoffDemo.Operation[] {
            new PatternTradeoffDemo.Add(2, 3),
            new PatternTradeoffDemo.Multiply(4, 5),
            new PatternTradeoffDemo.Reset()
        };
        index = 0;
    }

    private PatternTradeoffDemo.Operation next() {
        PatternTradeoffDemo.Operation sample = samples[index];
        index = (index + 1) % samples.length;
        return sample;
    }

    @Benchmark
    public int legacy() {
        return PatternTradeoffDemo.legacy(next());
    }

    @Benchmark
    public int typed() {
        return PatternTradeoffDemo.typed(next());
    }

    @Benchmark
    public int switched() {
        return PatternTradeoffDemo.switched(next());
    }
}
~~~

This layout is only a **test harness**. `next()` and the modulo operation are shared overhead measured alongside dispatch; very small benchmarks can have differences obscured by that shared overhead. You must design baselines and test multiple distribution patterns before extrapolating to real system performance. A good benchmark does not just "run": it must measure the right hypothesis.

**There are no fixed timing numbers in this article** because a single number run on another machine does not reflect your JDK, hardware, real workload, or case complexity in the application.

## 8. Common Mistakes When Measuring Pattern Matching

### 8.1. Comparing Non-Equivalent Code

For example, the `switch` version checks an extra guard while the `if-else` version does not; or the record pattern version extracts two components while the old version only checks the type. The resulting timings then do not reflect branching syntax alone.

**How to avoid:** test identical behavior and ensure the same logic, same inputs, and same side effects before measuring.

### 8.2. Using Only One Fixed Object

~~~java
// Not a reliable benchmark:
Operation input = new Add(2, 3);
for (int i = 0; i < 1_000_000; i++) {
    switched(input);
}
~~~

This code is very easily optimized away by the optimizer, or its result goes unused. It also represents a single branch rather than reflecting a system with multiple subtypes. If you need to measure the `Add` branch alone, define a benchmark intentionally for that branch; if you need to evaluate a real workload, you must use data with a realistic distribution.

### 8.3. Comparing Timings from a Single Run

A single `nanoTime` call before and after a loop can include startup, JIT, GC, or interference from other processes. A single result is not enough basis to declare a winner.

### 8.4. Ignoring Allocation and Memory

If one approach creates `String`s, collections, or intermediate objects inside a case, their cost can dwarf dispatch. When the goal is only to compare patterns, remove non-equivalent work. When the goal is end-to-end, **keep** realistic allocations and measure GC too, because that is the cost the system cares about.

### 8.5. Confusing Microbenchmark Results with Application Results

A method may be slightly faster in a microbenchmark yet fail to improve end-to-end latency if time is mostly spent on I/O. Conversely, a tiny method on a path processing billions of records can matter. Use a profiler to confirm hotness and run integration tests under near-real load.

## 9. Guards, Nested Patterns, and Readability

Pattern matching is very flexible, but expressing every condition in a single case is not always best.

~~~java
// Sketch when selecting the Add branch: the guarded case must precede the general case.
case Add(int left, int right) when left > 0 && right > 0 ->
        left + right;
case Add(int left, int right) ->
        0;
~~~

Here the two cases have different **business meaning**. The guarded branch only matches when both numbers are positive, so an unguarded case is needed to cover the remaining `Add` values.

If a condition is long, has many method calls, or has side effects, consider extracting it:

~~~java
// Snippet: assumes Operation and Add have already been declared.
static int checkedAdd(Add add) {
    return add.left() > 0 && add.right() > 0
            ? add.left() + add.right()
            : 0;
}

static int calculate(Operation operation) {
    return switch (operation) {
        case Add add -> checkedAdd(add);
        case Multiply(var left, var right) -> left * right;
        case Reset() -> 0;
        case null -> -1;
    };
}
~~~

Then `switch` focuses on **subtype selection**, while `checkedAdd` expresses the **business rule** with a meaningful name. This is not inherently slower: the JVM can inline small methods under the right conditions, though inlining and actual cost must be measured rather than assumed absolutely.

Similarly, deeply nested record patterns like `Route(Start(...), End(...))` can make code shorter, but when there are many nesting levels or complex null checks, named variables and separate methods are often easier to review. Do not prioritize "fewer source tokens" over the ability to explain the logic.

## 10. Choosing Based on Problem Characteristics

A practical way to decide:

| Situation | Initial preference | What to measure if on a hot path |
| --- | --- | --- |
| Two subtypes, a few simple conditions | `instanceof` type patterns | Branch checks and input distribution |
| Many subtypes of a sealed hierarchy returning a value | Exhaustive `switch` expression | Dispatch, deconstruction, branch behavior |
| Need clear record deconstruction | Moderately deep record patterns | Accessor/guard cost and related allocations |
| Behavior naturally belongs to each subtype | Polymorphism | Inlining/dispatch profile and call counts |
| A case performs heavy I/O | Clear code, separated services | I/O, batching, timeouts, serialization |
| Multi-branch logic with side effects | Named methods or `switch` statement | End-to-end latency and correctness |
| Subtypes change frequently | Weigh exhaustive `switch` vs. polymorphism | Maintenance and regression cost, not just CPU |
| Noisy measurements or tiny difference | Keep the most readable version | Improve benchmark quality before deciding |

The choices are not mutually exclusive. A method can use **`switch` with type patterns** instead of record patterns; a `switch` branch can call a **polymorphic method**; and a system can use a sealed hierarchy at the boundary while entities carry their own behavior internally.

## 11. Evidence-Based Optimization Workflow

Before turning an easy-to-understand piece of code into a harder-to-read expression for performance:

1. **Define the problem:** do you need to reduce CPU, throughput, p95/p99 latency, or allocation? Tie the goal to a real requirement.
2. **Measure holistically and profile:** confirm that branching actually accounts for a significant share; otherwise, optimizing elsewhere may be more effective.
3. **Lock down current behavior with tests:** test every subtype, null, guard boundary values, exceptions, and side effects.
4. **Create at least one clear version:** pick a type pattern or `switch` that fits the semantics, without optimizing by intuition.
5. **Benchmark properly:** use JMH for microbenchmarks and test under a workload representative of the application.
6. **Analyze multiple metrics:** balance throughput, latency, GC/allocation, complexity, and maintainability.
7. **Accept the trade-off only when the gain is significant and repeatable:** record the JDK, environment, and results; avoid deciding from a single measurement.
8. **Keep regression tests:** optimization refactors must still preserve results and error contracts.
9. **Re-evaluate when upgrading the JDK or when workloads change:** compiler/JIT optimizations and subtype distributions can invalidate old results.

Note on measurement goals: if you are only testing *dispatch*, the benchmark should not accidentally measure data creation and console printing. If the goal is end-to-end experience, do not strip out the system's real work.

## 12. Misconceptions to Avoid

**"Pattern matching is always faster than casting."** There is no guarantee. The clearest benefits are usually type safety and reduced boilerplate.

**"Switch always runs faster than if-else."** There is no guarantee. Speed depends on the selector type, branches, data, and JVM; you must benchmark.

**"Record patterns create a copy of the record."** That is not a necessary consequence of record patterns. They deconstruct the matched object; there is no automatic reason to conclude a new record will be created.

**"Sealed makes every case faster."** `sealed` provides a statically analyzable set of subtypes, supporting exhaustiveness and some optimization opportunities, but does not by itself dictate runtime performance.

**"Without default, null is handled automatically."** No. A `switch` that is exhaustive over subtypes still needs an appropriate null policy; without `case null`, null can lead to a `NullPointerException`.

**"Shorter code means more readable code."** A multi-level record pattern with a long guard can be harder to understand than a separate, well-named method.

**"If the microbenchmark is fast, production will definitely be fast."** No. You must check the actual share of time the code path takes in the application and under representative workload conditions.

**"Tests can be skipped because the compiler checks exhaustiveness."** The compiler does not know whether arithmetic results or business logic are right or wrong. Tests are still needed for guards, negative numbers, overflow if it matters, null, and side effects.

## 13. Code Review Checklist

- [ ] Do the alternatives return **equivalent results** over the same data domain?
- [ ] Is the current branching form **easier to understand** for maintainers?
- [ ] If migrating from `instanceof` to `switch`, does null change behavior?
- [ ] Are subtype branches complete, free of dominance issues, and handling false guards properly?
- [ ] Are there deeply nested record patterns or accessors with cost/side effects to watch out for?
- [ ] Is `default` hiding a missing new subtype in a sealed hierarchy?
- [ ] If called very frequently, has profiling confirmed this is a **hot path**?
- [ ] Did the benchmark warm up, use representative inputs, prevent dead-code elimination, run multiple forks, and report error margins?
- [ ] Were allocation, GC, and end-to-end latency measured if those metrics are what actually matter?
- [ ] Did we avoid a minor optimization that makes the code harder to read, harder to test, and more error-prone?

**Conclusion:** In Java Pattern Matching, prioritize **clear code, safe type checking, and proven behavior**. `instanceof` type patterns are often suitable for small refactors; exhaustive `switch` excels at sealed-hierarchy completeness; record patterns are convenient when deconstruction is needed; polymorphism fits behavior tied to subtypes. Only trade readability for speed when **profiling and benchmarking under appropriate conditions** show a significant, reproducible benefit sufficient to offset maintenance costs.