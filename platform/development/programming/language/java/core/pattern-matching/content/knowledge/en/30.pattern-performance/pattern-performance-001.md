# Runtime Cost of Type Checks in Java Pattern Matching

## 1. Are Type Checks “Expensive”?

In Java, runtime type checking occurs when using `instanceof`, casts (`(SomeType) object`), type patterns (`instanceof SomeType value`), or when a `switch` needs to classify a selector by type. With **record patterns**, Java may also need to read components through accessors, check further nested patterns, and evaluate `when` guards.

The right answer to “are type checks expensive?” is not a fixed number of nanoseconds:

- A simple type check typically has a very short execution path on an optimized JVM, and **does not allocate new objects on its own** just from using `instanceof`.
- However, a real processing flow may consist of **multiple checks**, branches, reading object/record components, calling user-defined accessors, guards with expensive logic, building result strings, or triggering allocations.
- The HotSpot JIT can optimize, inline, change representations, or eliminate certain checks when correctness can be proven. What is observed in bytecode does not necessarily equal the cost of machine code in a warmed-up state.
- Speed also depends on the **actual subtype distribution**, pattern depth, branch predictability, cache state, JDK/JVM, hardware, deoptimization points, and GC pressure.
- `sealed` and exhaustive `switch` provide **compile-time type guarantees**, not a promise that runtime dispatch has zero cost.

Therefore, for most application code, prioritize **semantics, clarity, and a sound domain structure**. Only conclude that one style is faster after measuring a **representative workload** with tools such as JMH and/or a profiler.

**Version scope:** `instanceof` with type patterns has been a standard feature since Java 16. Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) have been standard features since **Java 21**, without requiring `--enable-preview`. This lesson uses JDK 21 or later and refers to HotSpot as a common implementation example, without treating all JVMs as identical.

After this lesson, you will be able to distinguish the costs of **type checking**, **record deconstruction**, **guards**, **case selection**, and **code inside a case**, design proper experiments, and avoid inferring performance solely from Java line count or bytecode.

## 2. What Should Be Measured? Five Parts of a Pattern Operation

Consider this illustrative snippet:

```java
// event has type Object or a common interface:
switch (event) {
    case Text(String text) when text.length() >= 4 ->
        processLongText(text);
    case Text(String text) ->
        processShortText(text);
    default ->
        processOther(event);
}
```

If this is a `switch` statement using pattern matching, the runtime work can be broken down into the following layers:

1. **Obtaining the selector:** Reading or computing `event`. If written as `switch (loadEvent())`, the cost of `loadEvent()` is not the pure cost of the type check.
2. **Type compatibility check:** Determining whether the object matches `Text`. Tests for `null` and subtypes also belong to the classification phase.
3. **Record deconstruction:** If the pattern `Text(String text)` matches the outer record, the runtime needs the component value to continue matching. With record patterns, the accessor may be invoked to retrieve the component. An overridden accessor may contain arbitrary logic or even throw an exception.
4. **Guard:** `text.length() >= 4` is evaluated once the associated pattern has matched. A simple guard is completely different from a guard that queries a database or calls a complex function.
5. **Case body:** `processLongText(...)` may perform I/O, allocations, or synchronization locking. When comparing two dispatch approaches, do not confuse this cost with the type check alone.

Two programs with the same type check but different bodies can have vastly different runtimes; conversely, the same body with different guards cannot measure the cost of a “pure” type check either.

### Cost Breakdown Table

| Component | What to observe | Interpretation principle |
| --- | --- | --- |
| `instanceof SomeType` | Dynamic type check of a reference | Usually cheap, but there is no universal nanosecond number across all JVMs |
| `checkcast` or bound pattern variable | Ensuring the reference has the required type | The JIT can leverage type information and eliminate redundant checks when valid |
| `switch` with type patterns | Selecting a branch for a type/value | Lowering form and machine code are implementation details |
| `Record(T x)` | Checking the record and retrieving the component | May invoke the accessor; accessor cost is not automatically zero |
| Nested record pattern | Additional record/component checks across levels | Matching and non-matching paths execute different numbers of operations |
| `when predicate` | Checking an additional condition | Cost depends on the expression; the guard only applies when the pattern matches |
| String creation, boxing, streams, logging in the body | Business/consumer behavior | Typically excluded from “type check cost” during analysis |

Do not turn this table into a fixed additive time formula: the JIT can inline and optimize across multiple steps, making boundaries in machine code differ from the source-level diagram.

## 3. How Do `instanceof`, Type Patterns, and Casts Work?

### 3.1. Dynamic Type Checking

`instanceof` returns `true` when the reference is non-null and the object can be checked against the specified type; compatible subtypes are also accepted. For example:

```java
// Illustrative snippet:
Object value = "java";
boolean text = value instanceof CharSequence; // true
boolean number = value instanceof Number;      // false
boolean missing = null instanceof String;      // false
```

The JVM must distinguish the object's runtime type from the target type being checked. The exact mechanism depends on the JVM; HotSpot maintains class/interface metadata and optimized check paths. Do not assume all `instanceof` checks perform the same number of comparisons, or have invariant complexity/latency across every inheritance hierarchy.

### 3.2. A Type Pattern Is Not Necessarily “Two Checks”

`if (value instanceof String text)` combines the type check and binding the variable `text`:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Compared to older code:

```java
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Both share the same goal: ensuring `value` is a `String` before using it. Do not conclude the pattern version is “twice as fast” because it removes one cast line, nor conclude it is “twice as slow” because the bytecode may contain both `instanceof` and `checkcast`. The compiler/JIT can take advantage of the fact that a successful check has already established the type.

**Key point:** Type patterns improve flow scoping and eliminate manual casts in source code; performance benefits must be measured, not inferred from syntactic brevity.

### 3.3. `getClass() == T.class` Is Not a Direct Replacement for `instanceof`

`obj.getClass() == SomeClass.class` checks for the **exact runtime class** and does not match subclasses; `obj instanceof SomeClass` accepts compatible subtypes. Moreover, `obj.getClass()` throws `NullPointerException` when `obj` is null, whereas `null instanceof SomeClass` returns false.

Even if a microbenchmark occasionally shows class-equality comparison to be cheaper in a specific scenario, **do not replace `instanceof` with `getClass()` if the semantics require accepting subtypes**. Changing business logic to save a few nanoseconds is not a valid optimization.

## 4. Is a Type Pattern in `switch` Always Faster Than `if/else`?

Both constructs can express the same classification algorithm:
- A chain of `if (event instanceof ...)`.
- `switch (event)` with type/record patterns and guards.

There is no rule in the Java Language Specification guaranteeing that a pattern `switch` is faster than `if` across all inputs and JDKs.

### Factors That Commonly Cause Differences

**Input distribution:** If 95% of messages fall into the first case, an `if/else` chain placing the common branch first may behave differently from a workload where every subtype appears equally often. The CPU branch predictor, JVM profiling, and compiler code layout can all have an impact.

**Number of subtypes and call-site stability:** Two stable subtypes, dozens of constantly changing subtypes, or a newly loaded subtype can all affect optimization differently. Do not infer from the number of `case` clauses that the runtime always scans the entire list linearly.

**Type hierarchy:** A sealed hierarchy helps the compiler understand the set of subtypes, but it does not mean `switch` must be compiled into a constant jump table like `switch(int)`. The Java compiler/JVM is free to use appropriate dispatch mechanisms. In modern JDKs, pattern `switch` may use `invokedynamic` with a bootstrap for type-based switches; that alone does not determine post-JIT cost.

**Multiple cases for the same subtype:** Guards can split one subtype into multiple branches. If the first guard does not apply, another case may still be evaluated. The total cost is not just the type check.

**Nature of the body:** If each branch invokes multiple methods or allocates objects, dispatch may be a tiny fraction of the total cost. Do not redesign an entire domain model based solely on the timing of a cheap check.

### Case Ordering Must Satisfy Semantics First

General cases can **dominate** specific cases and be rejected by `javac`:

```java
// Intentionally invalid example when placed in the same switch:
case CharSequence value -> handleText(value);
case String text -> handleString(text); // dominated
```

Even if you want a common branch first, **you must not violate the dominance rules of pattern `switch`**. With guards, place guarded cases before unguarded cases when needed:

```java
case Text(String text) when text == null -> ...;
case Text(String text) -> ...;
```

Do not reorder cases to “optimize” if doing so changes the result or causes a compilation error.

## 5. Record Patterns: Cost Does Not Stop at the Type Check

Type patterns and record patterns perform different work.

```java
// Illustrative snippet, value has type Object:
boolean isText = value instanceof Text;
boolean deconstructed = value instanceof Text(String s);
```

The first line only needs to determine the object's type. The second line also requires the record component value `s` to complete matching. Under Java 21 semantics, when deconstructing a record, the corresponding accessor may be invoked.

With a nested pattern:

```java
// Illustrative snippet, value has type Object:
boolean wrapped =
    value instanceof Wrapper(Text(String s));
```

The runtime requires the outer `Wrapper` record to be non-null, its `value` component to match the inner `Text` record, and then the `String s` component to be bound according to pattern rules. If the nested record component is null, the nested record pattern does not match normally. If a record's accessor is overridden and is expensive or throws an exception, behavior will differ significantly from a pure type check.

**Note:** Deconstruction via a record pattern does not require “allocating a new object to hold a tuple”; the pattern typically just binds the component values. However, user code placed in an accessor or body can still allocate. The language does not promise that any arbitrary record pattern is zero-cost.

## 6. Complete Java 21 Example: Verify Logic First, Then Observe the Steps

The example below **does not measure ns/op**. It verifies that two classification approaches produce the same result, while counting how many times the guard is called and how many times a custom record accessor is evaluated. This is evidence of **observable behavior of this program**, not a throughput benchmark.

Create the file **`TypeCheckRuntimeCostDemo.java`**:

```java
public class TypeCheckRuntimeCostDemo {
    sealed interface Event permits Text, Quantity, Wrapper {}

    record Text(String text) implements Event {}
    record Quantity(int amount) implements Event {}
    record Wrapper(Text value) implements Event {}

    record Traced(String value) {
        static int reads;

        @Override
        public String value() {
            reads++;
            return value;
        }
    }

    static int guardCalls;

    static boolean longText(String value) {
        guardCalls++;
        return value.length() >= 4;
    }

    static String bySwitch(Event event) {
        return switch (event) {
            case Text(String s) when s == null -> "TEXT_NULL";
            case Text(String s) when longText(s) -> "TEXT_LONG";
            case Text(String s) -> "TEXT_SHORT";

            case Quantity(int amount) when amount < 0 -> "NEGATIVE";
            case Quantity(int amount) -> "QUANTITY";

            case Wrapper(Text(String s)) -> "WRAPPED";
            case Wrapper(var value) -> "WRAPPER_EMPTY";

            case null -> "NULL";
        };
    }

    static String byIf(Event event) {
        if (event == null) return "NULL";

        if (event instanceof Text(String s)) {
            if (s == null) return "TEXT_NULL";
            if (longText(s)) return "TEXT_LONG";
            return "TEXT_SHORT";
        }

        if (event instanceof Quantity(int amount)) {
            return amount < 0 ? "NEGATIVE" : "QUANTITY";
        }

        if (event instanceof Wrapper(Text(String s))) {
            return "WRAPPED";
        }
        if (event instanceof Wrapper(var value)) {
            return "WRAPPER_EMPTY";
        }

        throw new AssertionError("Unknown subtype");
    }

    static int cases;

    static void verify(Event event) {
        guardCalls = 0;
        String viaSwitch = bySwitch(event);
        int switchGuards = guardCalls;

        guardCalls = 0;
        String viaIf = byIf(event);
        int ifGuards = guardCalls;

        if (!viaSwitch.equals(viaIf) || switchGuards != ifGuards) {
            throw new AssertionError("Implementations differ");
        }

        cases++;
        System.out.println(viaSwitch + " | guards=" + switchGuards);
    }

    public static void main(String[] args) {
        verify(new Text("java"));
        verify(new Text("go"));
        verify(new Text(null));
        verify(new Quantity(-2));
        verify(new Quantity(3));
        verify(new Wrapper(new Text("x")));
        verify(new Wrapper(new Text(null)));
        verify(new Wrapper(null));
        verify(null);

        Object probe = new Traced("yes");
        System.out.println("typeOnly="
            + (probe instanceof Traced)
            + ", reads=" + Traced.reads);
        System.out.println("deconstruct="
            + (probe instanceof Traced(String s) && !s.isEmpty())
            + ", reads=" + Traced.reads);

        Object other = new Object();
        System.out.println("wrongType="
            + (other instanceof Traced(String s))
            + ", reads=" + Traced.reads);

        System.out.println("CASES=" + cases);
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 TypeCheckRuntimeCostDemo.java
java TypeCheckRuntimeCostDemo
```

**Exact stdout:**

```text
TEXT_LONG | guards=1
TEXT_SHORT | guards=1
TEXT_NULL | guards=0
NEGATIVE | guards=0
QUANTITY | guards=0
WRAPPED | guards=0
WRAPPED | guards=0
WRAPPER_EMPTY | guards=0
NULL | guards=0
typeOnly=true, reads=0
deconstruct=true, reads=1
wrongType=false, reads=1
CASES=9
```

### 6.1. Both Classification Approaches Produce the Same Result

`verify` calls `bySwitch` and `byIf` with **the same Event**, comparing the return value and the number of times the guard was called. If they differ, the program throws `AssertionError` instead of printing a fake “PASS”.

The nine values cover:
- Long text: `Text("java")`.
- Short text: `Text("go")`.
- Text with a null component: `Text(null)`.
- Negative and non-negative numbers: `Quantity(-2)`, `Quantity(3)`.
- Wrapper containing normal Text and Text with a null component.
- Wrapper with a null child record component.
- Null `Event` selector.

For `Text(null)`, the `Text(String s) when s == null` case is selected; the `longText(s)` guard is not called. For `Text("java")` and `Text("go")`, the guard is evaluated once per processing path; either the long or short case is selected depending on the result.

**Note:** `Wrapper(new Text(null))` still matches the nested `Text(String s)`: at the component position declared as `String`, an unconditional pattern can bind null. Conversely, `Wrapper(null)` does not match the nested record pattern `Text(...)` and enters the `Wrapper(var value)` case.

### 6.2. Type-Only Does Not Call the Record Accessor; Deconstruction Can

The `Traced` part is a separate record with an overridden accessor that increments a counter:

```java
record Traced(String value) {
    static int reads;

    @Override
    public String value() {
        reads++;
        return value;
    }
}
```

- `probe instanceof Traced` only checks the type, so `reads=0`.
- `probe instanceof Traced(String s)` requires deconstructing the record and invokes `Traced`'s accessor; after that, `reads=1`.
- `other instanceof Traced(String s)` fails immediately because `other` is not a `Traced`; the accessor is not called, and the read count remains 1.

The takeaway is **not** “a record pattern is always slower by exactly one method call.” When an accessor is simple, the JIT can inline it; when an accessor has side effects, its behavior cannot arbitrarily disappear; when a nested pattern fails to match early, subsequent steps do not need to run. Treat the call count here as **a tool to illustrate extra work**, not a unit of time.

### 6.3. Guards Can Dominate the Cost of the Type Check

`longText` only calls `String.length()` and increments a counter. If replaced with a network lookup, complex regex parsing, or allocating auxiliary objects, the guard's execution time can dwarf the type check. Keep guards clear, free of unnecessary side effects, and avoid repeating expensive logic across cases.

### 6.4. This Is Not a Performance Benchmark

The two approaches are called sequentially, with counter resets and string output generation. The time for `System.out.println`, string concatenation, object instantiation, class loading, and warm-up is not isolated. The output above proves **identical semantics for the test cases**, and does not prove that `switch` is faster or slower than `if`.

## 7. How Can HotSpot/JIT Change Runtime Cost?

Java source is compiled to bytecode, and then the JVM can dynamically execute/compile hot paths. In HotSpot, key optimizations may include:

- **Inlining:** Removing the overhead of small method calls when appropriate, including record accessors or guard helpers.
- **Redundant type-check elimination:** When the compiler infers or proves that a value already has a compatible type, some redundant checks can disappear in machine code.
- **Type profiling and devirtualization:** The JVM observes runtime types at call sites and optimizes common paths, with fallback mechanisms that preserve semantics if assumptions no longer hold.
- **Escape analysis/scalar replacement:** Allocations of related objects may be optimized away if the compiler proves their scope of use; this is not a guarantee for every record or every pattern.
- **Branch optimization:** How branches are laid out after compilation, local profiles, and CPU branch predictor behavior affect performance on a given dataset.

These optimizations make “counting statements in source” or “seeing a `checkcast` opcode” insufficient to infer the latency of a hot path.

### Cold Path, Warm-Up, Steady State, and Deoptimization

- **Cold start:** Initial execution may include class loading, bootstrapping, interpreter execution, and compiler activity.
- **Warm-up:** Code runs enough times for the JIT to collect profiles and optimize. There is no fixed warm-up iteration count valid for every program.
- **Steady state:** Measuring under more stable conditions, though still subject to GC, CPU frequency, contention, and data effects.
- **Deoptimization:** If runtime assumptions of optimized code no longer hold (for example, the type distribution changes), the JVM can fall back to another execution path and re-optimize.

A benchmark that repeatedly uses a single `Text` object makes it easy for the JVM to optimize for an extremely narrow profile; the result may not reflect a real system receiving all subtypes. Conversely, randomly mixing too many types that never occur together in production also produces an unrepresentative workload.

### Inspecting Bytecode: Useful, Not a Stopwatch

You can inspect the compiled bytecode of a program:

```bash
javap -c -p TypeCheckRuntimeCostDemo
```

In modern JDKs, you may see `instanceof`, `checkcast`, or mechanisms like `invokedynamic` for pattern switches. The bytecode shape depends on the JDK version and compiler, and the VM can optimize quite differently when running hot.

**Do not** take “more bytecode instructions” as proof of proportionally slower speed. `javap` helps you understand translation, whereas JMH and profilers help you observe runtime behavior.

## 8. Costs Related to Null, Branching, and Input Data

### 8.1. Null Checks Are Not the Same as Record Deconstruction

`null instanceof T` is false. A `switch` that receives `null` needs an appropriate case or handling policy; a standalone `default` does not catch `null` in a pattern switch.

Null handling may be just a simple check, but what matters most is **semantics**. Do not omit `case null` to “speed things up” if null inputs must be handled.

### 8.2. Type Distribution and Branch Prediction

If data consistently enters the same branch, the CPU can predict control flow more favorably than with an unpredictable distribution. However, this also depends on how the compiler/JIT lowers `switch` to machine code, branch layout, and workload type.

Therefore, benchmarks should test at least:
- Most inputs belonging to one subtype.
- Subtypes appearing in a relatively balanced mix.
- Guards mostly true versus guards mostly false.
- Non-matching and null cases if production actually sees them.

Do not compare two solutions under different distributions and attribute the difference to syntax.

### 8.3. Depth of Record Patterns

Nested patterns may require more levels of checks and accessor calls than a type-only match. Even so, a match that fails early generally does not need to continue checking deeper components. Nesting depth, null distribution, accessors, and guards all matter.

Do not write overly deep nested patterns just to reduce line count if the code becomes hard to read or deals with complex data. You can split it into a type-pattern case and call a clear handler method, **as long as semantics are preserved**.

### 8.4. GC and Allocation Are Separate Concerns

`instanceof` does not allocate an object just to return a boolean. A record pattern also does not inherently allocate another record when deconstructing components. However, the body may allocate strings/DTOs, box primitives, create collections, or throw exceptions; furthermore, input objects are usually already allocated before matching.

When profiling, check allocation rate and GC to see whether the main cost actually lies in dispatch or in creating/processing data. A microbenchmark that allocates a new object on every call may end up mostly measuring allocation rather than type checks.

## 9. Comparison with Polymorphism and Interface Dispatch

Another option is to move behavior onto the type itself:

```java
// Design illustration snippet, not combined into the section 6 program:
interface Describable {
    String describe();
}

final class TextMessage implements Describable {
    private final String text;

    TextMessage(String text) {
        this.text = text;
    }

    @Override
    public String describe() {
        return "TEXT:" + text;
    }
}
```

The caller uses `message.describe()` instead of a `switch` classifying types to build the message.

Regarding performance:
- Virtual/interface dispatch also has runtime cost, though the JIT can inline/devirtualize under suitable conditions.
- An `instanceof` chain or pattern `switch` can also be heavily optimized.
- Results depend on type profiles, number of implementations, method behavior, and runtime data.
- Switching to polymorphism does **not** guarantee a speedup; it is usually chosen primarily for encapsulation and behavior ownership.

**Design first, optimize with evidence later:** If every consumer duplicates the same business rule using a `switch`, prefer centralizing the logic in a domain method/service for maintainability. If an operation is an external mapping over a sealed hierarchy, a pattern `switch` can be a great fit. Only compare speeds if a profiler shows dispatch is genuinely a hotspot.

## 10. Proper Benchmarking with JMH Instead of Manual `nanoTime` Loops

### 10.1. Why Naive Microbenchmarks Easily Mislead

Code like the following can produce misleading results:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    boolean ok = fixedValue instanceof Text;
}
System.out.println(System.nanoTime() - start);
```

The compiler can eliminate unused computations, optimize known types, or measure mostly loop/JIT warm-up overhead. In some cases, the local variable `ok` is never even read. The result cannot be treated as “the true cost of `instanceof`.”

Other issues include short timing windows, class loading, CPU throttling, GC, benchmark code being compiled differently from production code, constant folding, inlining, and the lack of independent forks.

### 10.2. JMH: Benchmarks with Warm-Up, Forks, and Observable Results

**JMH (Java Microbenchmark Harness)** is the OpenJDK toolkit for microbenchmarking on the JVM. JMH is not a standard library bundled with the JDK: a project must declare the appropriate JMH dependencies/plugin or archetype.

A JMH skeleton illustrating the same workload for two branching styles:

```java
// File TypeCheckBenchmark.java in a JMH-configured project.
// Dependencies outside the JDK: org.openjdk.jmh:jmh-core and
// annotation processor org.openjdk.jmh:jmh-generator-annprocess.
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Fork(2)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@State(Scope.Thread)
public class TypeCheckBenchmark {
    sealed interface E permits A, B {}
    record A(int n) implements E {}
    record B(int n) implements E {}

    @Param({"50_50", "90_10"})
    public String mix;

    private E[] input;
    private int index;

    @Setup(Level.Trial)
    public void setup() {
        input = new E[1024];
        for (int i = 0; i < input.length; i++) {
            boolean chooseA = mix.equals("90_10")
                ? i % 10 != 0
                : i % 2 == 0;
            input[i] = chooseA ? new A(i) : new B(i);
        }
    }

    @Benchmark
    public int withInstanceof() {
        E e = input[(index++) & 1023];
        if (e instanceof A a) return a.n();
        if (e instanceof B b) return b.n();
        throw new AssertionError("Unexpected type");
    }

    @Benchmark
    public int withSwitch() {
        E e = input[(index++) & 1023];
        return switch (e) {
            case A(int n) -> n;
            case B(int n) -> n;
        };
    }
}
```

**This is a JMH skeleton**, not a snippet that can be run with plain JDK `javac` alone. You must configure the JMH dependency and annotation processor and run it via the JMH runner/CI. No hypothetical benchmark numbers are provided because JMH has not been executed here.

**What the skeleton attempts to control:**
- Input objects are prepared in `@Setup`, avoiding including `new A`/`new B` allocations in the main measurement.
- Both benchmarks read inputs from the same `50_50` or `90_10` distribution.
- Returning an `int` result lets JMH observe it, preventing an unused expression from being eliminated.
- Warm-up and forks are configured; run conditions should be recorded alongside the JDK, hardware, and JVM flags.

**Limitations of the skeleton itself:** It measures **the entire operation**, including incrementing the index, reading the array, classifying the type, and reading the component; it is not an isolated measurement of just the `instanceof` instruction. You also need to control input size/diversity, state effects, and inspect generated code/profiler output if differences are very small. The parameters and iterations above are only a starting point, not a substitute for your project's statistical criteria.

### 10.3. How to Read Results

If JMH reports `ns/op` or `ops/s`, recognize that this is a **measurement point for that specific benchmark**, not a fixed cost of the Java feature. You should:
1. Compare within the same environment and JDK.
2. Run multiple forks/iterations, and check variance and appropriate confidence intervals.
3. Break down results by subtype distribution and guards.
4. Ensure both implementations have identical semantics on identical data.
5. Also test production-like workloads, not only tiny microbenchmarks.
6. Verify changes after optimizing; avoid optimizing a part that accounts for a negligible share.

Do not conclude “Java 21 pattern switch is X% faster” without reliable direct measurement data.

## 11. Profile the Application Before Refactoring

If an application is slow, start at the **system level**:
- CPU profile / wall-clock profile: Which methods consume the time? Is it dispatch or the body?
- Allocation profile: Which objects/strings/DTOs are allocated heavily? Is it from post-match processing?
- GC and latency: Are pause times or GC load delaying requests?
- Input distribution: Which subtypes appear most often, and what are the null/guard hit rates?
- JDK and environment: Are JIT tiering, heap, CPU, and contention consistent across runs?

Tools you can use include **Java Flight Recorder (JFR)**, **JDK Mission Control (JMC)**, async-profiler, `jcmd`, and JMH. These are profiling/benchmarking options; you do not need to deploy all of them for a small optimization.

### A Responsible Optimization Workflow

1. Form a concrete hypothesis, e.g., “the handler repeatedly checks 15 subtypes in a hot loop.”
2. Verify it with a profiler and input statistics.
3. Write tests ensuring old and new behavior are equivalent, covering null, nested records, guards, and exception behavior.
4. Design a benchmark containing representative subtypes and frequencies.
5. Try **one change**: factor out an expensive guard, reduce unnecessary repeated deconstruction, cache normalized data, or adjust dispatch structure if appropriate.
6. Re-measure in the same environment; do not keep changes that hurt readability if the gain is not statistically significant or does not improve SLOs.

Do not try to “optimize” `instanceof` with unchecked casts or by breaking the coverage of a sealed switch. The cost of a bug is usually far greater than a few type comparisons.

## 12. Common Misconceptions

| Misconception | Issue | Accurate understanding |
| --- | --- | --- |
| “`instanceof` is slow and must be avoided everywhere” | No evidence for real workloads | Simple type checks are usually cheap; measure if it is a bottleneck |
| “Pattern `switch` is always faster than `if/else`” | Syntax does not guarantee runtime speed | JIT and subtype distribution determine the outcome |
| “Fewer Java lines mean fewer instructions and faster code” | JIT/bytecode lowering differs from source | Compare behavior and measure runtime, do not count lines |
| “`sealed` eliminates all runtime type checks” | Exhaustiveness is a static check | Runtime still classifies objects; optimization depends on compiler/JVM |
| “Record deconstruction is free” | May invoke accessors and nested patterns | Cost depends on accessors, depth, and optimizations |
| “When a guard is false, the compiler tries the next one for free” | Guards themselves have a cost | A false guard only skips selecting the case; it is not free |
| “A one-million-iteration `System.nanoTime` loop gives accurate ns” | Warm-up, DCE, constant folding, OS noise | Use JMH with a valid workload |
| “Seeing `invokedynamic` means `switch` is slow” | Bytecode is not final machine code | The JIT can optimize dynamic linkage |
| “Replacing `instanceof T` with `getClass() == T.class` is safe” | Different semantics for subclasses and null | Only switch when the domain truly requires an exact-class check |
| “Record patterns always allocate extra objects” | Deconstruction does not inherently allocate a tuple | Find actual allocations with a profiler |
| “No warnings means optimal” | Compiler type-safety is not a performance report | Use a profiler/JMH separately |
| “A 1 ns difference in a benchmark is definitely meaningful” | Noise and machine differences can dominate | Check variance, confidence, and end-to-end impact |

## 13. Practice Exercises

### Exercise 1 — Verify Semantics Before Speed

Run `TypeCheckRuntimeCostDemo`. Add `Text("")`, `Quantity(0)`, and `Wrapper(new Text("long"))`. Predict the output and the number of times `longText` is called. Ensure `bySwitch` and `byIf` still produce the same result in every case.

### Exercise 2 — Check Nested Pattern Short-Circuiting

Increment a counter in `Wrapper`'s accessor or create a `TracedWrapper` record with its own accessor. Compare how many times the accessor is called when the outer record does not match the type, when the nested component is null, and when the component is present. Do not use execution time to infer call counts; use counters/assertions as in the example.

### Exercise 3 — Create a Guard with Significant Cost

Replace `longText` with a deterministic CPU-bound computation on the string (no I/O), then use a profiler/JMH to see how much time is spent in the guard versus type dispatch. Do not let the guard produce different results between the two implementations when benchmarking.

### Exercise 4 — Compare Input Distributions

Using the JMH skeleton, run both `50_50` and `90_10` on the same JDK/hardware; record throughput or ns/op along with variance. Also try a 99% `A` scenario, but do not generalize measurements from one workload to every application.

### Exercise 5 — Exact Type Differences

Create `class Base {}` and `class Child extends Base {}`. Compare `child instanceof Base` with `child.getClass() == Base.class`, as well as the null-reference case. Explain why relying solely on a benchmark to change semantics is wrong.

### Exercise 6 — Categorize Costs

Given a `switch` over a sealed hierarchy with deeply nested record patterns and a guard calling a regex, list which costs belong to type checking, accessors, guards, and the body. Propose a plan to measure each part without changing behavior. Name at least two benchmarking pitfalls you will avoid.

## 14. Summary

**Runtime type checking is a common and usually cheap operation, but the observed cost of pattern matching can come from multiple sources:** selector evaluation, type compatibility, record accessors, nested matching, guards, branching, and code inside the case body. Pattern `instanceof` and pattern `switch` have no Java-guaranteed speed ranking; the HotSpot JIT can optimize both based on profiles and workload.

**Good performance practice:** preserve semantics, keep code readable, identify hot paths with a profiler, design proper JMH benchmarks, test realistic subtype distributions, and evaluate end-to-end impact before refactoring. Do not sacrifice type safety, exhaustive switches, or domain model clarity out of concern for type-check cost.

## References

- Java SE 21, Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java SE 21, Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Java Language Specification SE 21, `instanceof` expression (15.20.2): https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2
- Java SE 21, Java Virtual Machine Specification, Instructions `instanceof` and `checkcast`: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-6.html
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JMH — Java Microbenchmark Harness: https://github.com/openjdk/jmh
