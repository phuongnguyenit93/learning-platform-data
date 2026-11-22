# Does pattern matching replace all optimizations? (Java 21)

## 1. Short answer and learning objectives

**No. Pattern matching in Java is a tool for expressing and checking data structures more safely and clearly; it does not automatically replace choosing algorithms, data structures, I/O organization, reducing allocations, optimizing queries, or measuring performance.**

For example, replacing:

```java
if (value instanceof String) {
    String text = (String) value;
    return text.strip();
}
```

with:

```java
if (value instanceof String text) {
    return text.strip();
}
```

eliminates the manual cast and prevents the `text` variable from being used on the wrong program path. However, from these two snippets, you cannot conclude that the second version **always runs faster**, consumes less memory, or has solved every bottleneck.

In Java 21, pattern matching also appears in `switch` and record patterns:

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "text:" + s.strip();
    case Integer n -> "number:" + n;
    case null -> "null";
    default -> "other";
};
```

This is **a clear way to describe control-flow branches**, not a guarantee that the JVM generates the most optimal machine code for all data.

After this lesson, you will be able to:

- Distinguish **readability/type safety** benefits from **measured** performance improvements.
- Understand the interaction between `javac`, bytecode, HotSpot/JIT, and how the compiler optimizes based on runtime conditions.
- Identify costs from `when` guards, record deconstruction/accessors, regex, allocation, memory, I/O, and data structures.
- Know why changing an algorithm can yield greater benefits than changing syntax.
- Design **JMH** experiments and measure real systems without misinterpreting results.
- Prove that a refactored version preserves behavior before comparing performance.

**Versions:** `instanceof` patterns are standard since Java 16; pattern matching for `switch` (JEP 441) and record patterns (JEP 440) are standard since Java 21. The complete examples use `javac --release 21`, with no preview features required.

## 2. What does pattern matching optimize in source code?

Pattern matching primarily helps express type and structural checks and value extraction:

1. **Type pattern:** `obj instanceof String s` checks if the object is a `String` and binds the variable `s`.
2. **Pattern switch:** `case String s -> ...` classifies values by pattern, optionally adding `when` to filter with business conditions.
3. **Record pattern:** `case Point(var x, var y) -> ...` extracts components of a record, which can be nested with other records.
4. **Flow scoping:** the pattern variable is only in scope on paths where the compiler proves the match succeeds.

Commonly observed benefits during code review: fewer repetitive casts, fewer nested branches, explicit type boundaries, and dominance or missing-branch errors that can be caught by the compiler. **These are design quality and correctness benefits**, not proof of performance by themselves.

Two statements need to be distinguished:

- "The new code is **shorter/more readable**" — can be confirmed from source code and review.
- "The new code is **faster/allocates less**" — must be measured on a representative workload, after ensuring both versions produce equivalent results and side effects.

Without a benchmark, the accurate statement is usually: *Patterns help describe the problem more clearly; performance may be equivalent, better, or worse depending on usage, workload, and the JVM.*

## 3. From Java syntax to execution speed: many layers remain

A Java program typically goes through these layers:

```text
Java Code -> javac -> bytecode (.class)
                   -> JVM/HotSpot -> interpreter/JIT -> machine code
                   -> CPU, memory, GC, OS, I/O
```

Pattern matching is syntax/semantics at the **language layer**. `javac` compiles it into valid bytecode; HotSpot can perform profiling, method inlining, check/cast optimization, eliminate some allocations, or specialize hot execution paths. The outcome depends on the JDK version, JVM flags, data types, warm-up history, and method contents.

### 3.1. "Fewer casts" does not automatically mean "less CPU cost"

The legacy snippet:

```java
if (value instanceof Integer) {
    Integer number = (Integer) value;
    return number + 1;
}
```

and the refactored snippet:

```java
if (value instanceof Integer number) {
    return number + 1;
}
```

both require checking the type and reading the value to compute. The JVM can exploit the same type information from the `instanceof` branch in both approaches. You cannot use line count as a measure of CPU cycles or claim that a cast instruction is completely eliminated at runtime.

**Key takeaway:** Bytecode may differ and the JIT may optimize; semantic equivalence does not guarantee equal instruction counts in all situations. Do not declare victory merely because you removed a cast using new syntax.

### 3.2. A pattern `switch` is not inherently faster than an `if/else` chain

```java
static String classify(Object value) {
    if (value instanceof String s) return "string";
    if (value instanceof Integer n) return "integer";
    return "other";
}
```

and:

```java
static String classifySwitch(Object value) {
    return switch (value) {
        case String s -> "string";
        case Integer n -> "integer";
        case null -> "other";
        default -> "other";
    };
}
```

can produce the same result over a defined input domain. However, how the JVM implements branch dispatch, inlining levels, value type distribution, and program profiles may differ. **There is no general rule** that one statement form is always faster than the other.

Do not forget `null` equivalence: `instanceof` with `null` returns `false`, whereas a pattern `switch` wanting to keep the old fallback usually needs `case null`. If you accidentally change an exception or result, the benchmark is comparing **two programs doing different work**.

## 4. Cost of branches, guards, and evaluation order

A pattern can match multiple types or positions in a structure. In a `switch`, Java evaluates `case` labels according to branch selection logic; a `when` guard is only evaluated when its corresponding pattern matches.

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s when expensiveBusinessRule(s) -> "special";
    case String s -> "normal";
    case null -> "null";
    default -> "other";
};
```

`expensiveBusinessRule(s)` is a hypothetical boolean helper. This example illustrates syntax, not a standalone program.

### 4.1. Guards can be the most expensive part

If a guard calls a regex, looks up a large data structure, calls an external API, or reads from disk, that cost can be **far greater** than the type-check cost. Replacing `if (x instanceof String)` with `case String s` does not magically turn the guard into a cheap operation.

In controlled code, you can place a **cheap and safe** check before an expensive one to leverage `&&` short-circuiting:

```java
case String s when !s.isBlank() && isEligibleByRules(s) -> "eligible";
```

However, **do not reorder arbitrarily** if a rule has side effects, throws exceptions, or computes different state. Preserving behavior is more important than speculative optimization.

### 4.2. Case ordering affects more than performance

Placing a broad type pattern branch before a narrower subtype branch may be rejected by the compiler due to **dominance**:

```java
// INTENTIONALLY WRONG in Java 21:
return switch (value) {
    case CharSequence c -> "sequence";
    case String s -> "string"; // dominated
    default -> "other";
};
```

Placing `String` before `CharSequence` is required to be valid. In structures with guards, changing the order can alter **business results**. Optimizing case order must prioritize correct semantics and dominance rules first, and only then measure performance.

### 4.3. Data distribution matters greatly

A workload with 99% `String` and 1% `Integer` has different branch behavior than a workload evenly distributed across many types. JVM/CPU branch prediction and profiling can affect runtime. A benchmark using only one fixed input type is **not representative** if production sees multiple types with different frequencies.

Do not impose a fixed "optimal case order" for every system. Keep the order correct and easy to understand, test with realistic input distributions, and only change the design when evidence is strong enough.

## 5. Record patterns: convenience can carry extra accessor work

A record pattern does not just check the outer type; it also **reads components via accessors** to match nested patterns.

```java
record Point(int x, int y) {}
record Box(Point point) {}

boolean justType = obj instanceof Box;
boolean nested = obj instanceof Box(Point(var x, var y));
```

Both snippets are illustrations in a scope where `obj` and the declared records exist. The second branch needs to access the `Box.point()` component and then deconstruct `Point`; the first branch only needs to check the `Box` type. Thus, if you only want to know whether `obj` is a `Box`, the nested pattern is **expressively unnecessary work**.

### 5.1. Custom accessors and side effects

Java allows records to override accessors:

```java
record Metered(int value) {
    static int reads;
    @Override public int value() {
        reads++;
        return value;
    }
}
record Envelope(Metered measurement) {}
```

When used:

```java
static boolean typeOnly(Object input) {
    return input instanceof Envelope;
}

static boolean deconstruct(Object input) {
    return input instanceof Envelope(Metered(var n)) && n >= 0;
}
```

With `new Envelope(new Metered(7))`:

- `typeOnly` returns true and does not need to call `Metered.value()`.
- `deconstruct` reads the nested value, so `Metered.value()` can run; in the demo, the counter increments once.
- If `measurement == null`, the nested `Metered(...)` does not match, because **record patterns do not match null**.
- If an accessor has side effects or throws an exception, changing a type check into deconstruction can alter both semantics and cost.

You should not conclude that record patterns are always "slow"; when business logic **needs** the components, deconstruction is the appropriate way to express it and the JVM can optimize the common case. The key point is to **avoid deconstructing unused data**, and not to assume shorter syntax always performs fewer operations.

### 5.2. Null semantics matter even more than speed

`null instanceof Box(Point(var x, var y))` is `false`, but `null` reference components and nested type patterns have their own matching rules. When converting from `if` to `switch` or from a type pattern to a nested record pattern, test `null` at the selector and at each record level to avoid changing behavior or causing exceptions. **Benchmarks must be run on correct code.**

## 6. Allocation, GC, and escape analysis

Using pattern matching **does not automatically eliminate** objects created by the logic inside a branch. For example:

```java
case String s -> new StringBuilder(s).reverse().toString();
```

In source code, there is still logic creating a `StringBuilder` and the resulting string. The JVM may optimize parts of this in specific cases, but there is no language guarantee that all allocations will disappear. If the code is on a hot path, you need to check **allocation rate**, **GC pressure**, and actual memory usage.

Common allocation sources worth checking:

- Intermediate strings from concatenation/formatting/regex.
- Temporary collections, boxing/unboxing, wrapper objects.
- Repeatedly creating matchers or exceptions in high-frequency branches.
- Object mapping/serialization, DTOs, and new records.
- Lazy vs eager computation when guards have different costs.

**Distinguish record patterns from record construction:** `case Point(var x, var y)` deconstructs an existing `Point` object; the match itself **does not implicitly construct a new `Point`**. However, code inside the branch may create new objects, or the runtime may do other work depending on the JIT. Do not count allocations merely by counting parentheses in a pattern.

### 6.1. Escape analysis is not a promise

HotSpot can perform escape analysis and scalar replacement in some cases. Effectiveness depends on whether methods are inlined, whether objects "escape" through other APIs, profiling, and runtime version. You cannot conclude from using a record pattern that allocations have been eliminated; measure with appropriate profiling/benchmarking tools.

## 7. Practical example: reusing a compiled regex instead of changing syntax

Compare two ways of checking the same identifier rule ("two uppercase letters and three digits"):

```java
static boolean slowRegex(String text) {
    return text != null && text.matches("[A-Z]{2}[0-9]{3}");
}
```

and:

```java
private static final java.util.regex.Pattern CODE_PATTERN =
        java.util.regex.Pattern.compile("[A-Z]{2}[0-9]{3}");

static boolean cachedRegex(String text) {
    return text != null && CODE_PATTERN.matcher(text).matches();
}
```

The Java API specifies that `String.matches(regex)` produces the same result as `Pattern.matches(regex, string)`. Using a precompiled `Pattern` **avoids recompiling the regular expression on every call**, an optimization worth considering when the regex is fixed and called frequently.

**Do not infer** from this that the second approach is always faster for every input or scale: creating a `Matcher` still has a cost; JIT, call count, caching, and data affect the result. Benchmark when performance actually matters.

Once compiled, `Pattern` is immutable and can be safely shared; `Matcher` is stateful and **must not be shared concurrently** across threads without proper synchronization. Therefore, a new matcher is typically created per use rather than trying to use a `static Matcher` to "eliminate allocation" and introducing a race condition.

**Connection to pattern matching:** Putting regex validation code in `case String s when ...` still carries the same business cost to consider. The improvement may lie in **reusing the regex** rather than replacing `if` with `switch`.

## 8. Optimizing algorithms and data structures matters more than changing syntax

Suppose you need to detect duplicate elements in a list. Using nested loops to compare each pair:

```java
static boolean quadraticDuplicate(List<String> values) {
    for (int i = 0; i < values.size(); i++) {
        for (int j = i + 1; j < values.size(); j++) {
            if (java.util.Objects.equals(values.get(i), values.get(j))) {
                return true;
            }
        }
    }
    return false;
}
```

With an `ArrayList` or a list with O(1) indexed access, this algorithm can require **O(n²)** comparisons in the worst case when there are no duplicates. No `instanceof`/`switch` pattern will change that complexity on its own.

Another approach:

```java
static boolean hashedDuplicate(List<String> values) {
    return new java.util.HashSet<>(values).size() != values.size();
}
```

With properly implemented `hashCode`/`equals` contracts and reasonable hash distribution, using `HashSet` typically has **O(n) average time** to build the set and check its size, at the cost of **O(n)** auxiliary memory. This is an **algorithm and data structure** optimization, independent of pattern matching.

**Conditions to keep in mind:**

- Both approaches in the example use `equals` equality and can handle `null` elements (`HashSet` allows `null`).
- You must choose the right business definition of "duplicate": by identity, by a key field, case-insensitive, or by a comparator? Not all strategies are equivalent.
- For very small lists, the cost of creating a `HashSet` may outweigh the benefit of fewer comparisons; measure it.
- Average hashing performance depends on element count, hash quality, and the runtime; it is **not a worst-case O(n) guarantee** for all data types.
- For lists where `get(i)` is not constant-time (e.g., `LinkedList`), cost analysis of the loop version must also include positional access complexity.
- If elements or hashes can be mutated during inspection, using a `Set` requires clear immutability/synchronization contracts.

This is why **well-directed optimization** usually starts by asking: "How is the data accessed?" rather than "Is there a prettier way to write `case`?".

## 9. Other optimizations that pattern matching cannot replace

| Real-world bottleneck | Why patterns cannot solve it | Approaches to evaluate |
| --- | --- | --- |
| Repeated per-item database queries | Patterns only classify data after it arrives; they do not reduce round trips | Batch queries, indexes, DB-side filtering, avoid N+1 |
| Slow file or HTTP I/O | I/O and network costs exceed type-check operations in many applications | Batching, timeouts, pooling, controlled caching |
| Deeply nested loop algorithms | Complexity scales with data size | Change algorithm/data structure, indexing/hashing |
| Excessive object allocation | Patterns do not automatically make results allocation-free | Profile allocations, reduce intermediate data |
| GC pauses or heap pressure | Branch dispatch does not change object retention policies | Inspect lifetimes, heap, GC logs, and allocations |
| Lock contention | `switch` does not automatically remove thread contention | Shrink critical sections, measure locks, redesign concurrency |
| Cache misses and poor locality | Record patterns do not change object memory layout | Choose data structures/locality suited to the workload |
| Repeated regex/JSON parsing | Patterns still invoke heavy helpers | Precompile/reuse appropriate parsers, cache valid results |
| Multiple data transformations | Using `case` does not prevent repeated mapping/serialization | Design pipelines, eliminate redundant steps |
| Throwing exceptions as regular control flow | Patterns do not handle the entire API contract by themselves | Optimize control flow when business rules allow, preserving semantics |

**Prioritize by evidence:** For a high-latency API, the first step is determining whether time is spent in DB, network, CPU, GC, or contention. If 90% of the time is in external I/O, debating between `instanceof` and `switch` usually has little impact on end-to-end latency, though it still has readability value.

## 10. Measuring performance properly: a benchmark is not a one-off stopwatch

### 10.1. Why a hand-rolled `System.nanoTime()` loop is error-prone

A questionable example:

```java
long start = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    classifyFixedObject();
}
long elapsed = System.nanoTime() - start;
```

In this snippet, `classifyFixedObject()` is a hypothetical helper. The experiment can be skewed by:

- Insufficient JVM warm-up; the method is not yet JIT-compiled.
- **Dead-code elimination:** if the result is unused, the JVM may eliminate side-effect-free computation.
- **Constant folding:** fixed inputs may be optimized differently than production workloads.
- GC, turbo boost, CPU frequency, background processes, thermal state.
- A single measurement has no variance or confidence interval.
- The benchmark mixes data initialization with the code under test.
- Identical bytecode can have different branch profiles across runs.

Such measurements can be useful for preliminary diagnosis, but they are **not enough to claim a change is faster by a specific percentage**.

### 10.2. Using JMH for microbenchmarks

OpenJDK's **JMH (Java Microbenchmark Harness)** is a tool specifically designed for measuring Java/JVM code at nano/micro/millisecond scales, supporting warm-up, forks, iterations, measurement modes, and mechanisms to mitigate several optimizer pitfalls.

Example benchmark harness comparing **the same classification logic** of the `legacy` and `modern` methods from the full file in Section 12:

```java
import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
public class DispatchBenchmark {
    @Param({"string", "integer", "point", "other"})
    public String type;

    private Object input;

    @Setup(Level.Trial)
    public void setup() {
        input = switch (type) {
            case "string" -> " java ";
            case "integer" -> 42;
            case "point" -> new PatternOptimizationDemo.Point(3, 4);
            default -> new Object();
        };
    }

    @Benchmark
    public String legacy() {
        return PatternOptimizationDemo.legacy(input);
    }

    @Benchmark
    public String patterns() {
        return PatternOptimizationDemo.modern(input);
    }
}
```

**Important note:** This is an **illustrative JMH class**, not standalone code runnable with plain JDK `javac`. You need to create a JMH benchmark project with its dependencies and annotation processor following the official guide, and include `PatternOptimizationDemo` on the classpath. The goal is to show how to structure inputs and two implementations, not to publish unmeasured nanosecond numbers.

This harness measures **each input type separately**. If production has a mixed distribution, you must also benchmark representative mixed data rather than drawing conclusions from a single homogeneous group. Return values are consumed by JMH as observed outputs, but you still need to watch for constant folding, dead-code elimination, and semantic changes. Consult the JMH Samples before integrating into CI.

### 10.3. Conditions for a fair comparison

A reliable benchmark for legacy casts vs pattern matching requires:

1. **Same result contract:** both classify identically, preserving `null`, exceptions, guards, whitespace, and branch order.
2. **Same workload:** data types, sizes, branch distributions, blank strings, nested records, and call frequencies.
3. **Same environment:** CPU, RAM, JDK/JVM vendor/version, heap/GC flags, OS, and CPU frequency all matter.
4. **Warm-up and forks:** do not measure only the first invocation; separate independent runs when needed.
5. **Exclude unrelated setup costs:** create data outside the measured region unless data creation is part of the real problem.
6. **Multiple samples:** inspect error margins, variance, and outliers; avoid concluding from small differences within noise.
7. **Observe allocation/GC:** two approaches may be similar in CPU time yet differ in allocations.
8. **Profile before and after:** use Java Flight Recorder (JFR), profilers, GC logs, or existing observability to pinpoint real hotspots.
9. **Verify per version:** results on JDK 21 do not automatically apply to other JDKs or CPU architectures.
10. **Measure at production level:** p50/p95/p99 latency, throughput, error rate, and CPU/GC must reflect end-to-end experience, not just nanoseconds of one helper.

**Do not fabricate illustrative numbers as real measurements.** If you have not run JMH or profiling, only describe the hypothesis and verification plan.

## 11. Building a practical optimization workflow

A sound workflow typically follows this order:

### Step 1 — Define a measurable goal

For example: reduce an endpoint's p95 latency under a defined load, reduce peak CPU usage, or reduce allocation rate on a hot path. Do not use a vague target like "cleaner code" as a substitute for a performance goal.

### Step 2 — Record a baseline

Record the workload, code/JDK version, system, outputs, important exceptions, and metrics before changes. Without a baseline, it is hard to tell which improvement had an effect or which change broke behavior.

### Step 3 — Profile and target the real hotspot

Use a profiler/JFR to confirm where time is spent. In data-processing systems, look for loops, collection operations, regex, serialization, locks, or I/O. Do not assume an `instanceof` chain is the hotspot just because it looks verbose.

### Step 4 — Optimize one evidence-backed cause

For example: reuse a compiled regex, change a duplicate-detection algorithm, reduce DB round trips, or avoid intermediate allocations. You can refactor with pattern matching to make code clearer, but **separate PRs/commits** if you want to measure the impact of a real optimization.

### Step 5 — Test equivalence before benchmarking

Preserve inputs/outputs, `null`, exceptions, side effects, and branch order. If a business behavior change is intentional, document and test it separately before comparing performance.

### Step 6 — Microbenchmark and system-level testing

JMH helps test CPU-level hypotheses with appropriate inputs. Load tests, integration tests, and production metrics verify end-to-end impact. When the two disagree, investigate why rather than picking the nicer-looking number.

### Step 7 — Monitor after deployment, ready to roll back

Compare latency, throughput, CPU, GC, and error rates over a representative time/load window. If an optimization trades resources for latency (e.g., adding a `HashSet` increases memory), evaluate the trade-off against system requirements. If a regression occurs, revert or restore the verified logic.

## 12. Complete Java 21 program: three verification groups

Create the file **`PatternOptimizationDemo.java`** below. This program is **not a speed benchmark**: it verifies three meaningful ideas before measuring:

- **Syntax refactor:** `legacy(Object)` uses `instanceof` + cast; `modern(Object)` uses pattern `switch`. Both must return the same result for the same input.
- **Separate optimization:** `slowRegex` and `cachedRegex` check the same regex; they differ only in how `Pattern` is prepared.
- **Algorithmic difference:** O(n²) duplicate detection vs `HashSet`-based O(n) average cost, comparing results.
- **Record deconstruction:** counts accessor calls to show that deep matching can perform extra work.

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.regex.Pattern;

public class PatternOptimizationDemo {
    record Point(int x, int y) {}
    record Metered(int value) {
        static int reads;
        @Override public int value() {
            reads++;
            return value;
        }
    }
    record Envelope(Metered measurement) {}

    private static final Pattern CODE_PATTERN =
            Pattern.compile("[A-Z]{2}[0-9]{3}");

    static String legacy(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return text.isBlank() ? "blank" : "text:" + text.strip();
        }
        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return number >= 0 ? "non-negative:" + number : "negative:" + number;
        }
        if (value instanceof Point) {
            Point point = (Point) value;
            return "point:" + point.x() + "," + point.y();
        }
        return "other";
    }

    static String modern(Object value) {
        return switch (value) {
            case String text when text.isBlank() -> "blank";
            case String text -> "text:" + text.strip();
            case Integer number when number >= 0 -> "non-negative:" + number;
            case Integer number -> "negative:" + number;
            case Point(var x, var y) -> "point:" + x + "," + y;
            case null -> "other";
            default -> "other";
        };
    }

    static boolean slowRegex(String text) {
        return text != null && text.matches("[A-Z]{2}[0-9]{3}");
    }

    static boolean cachedRegex(String text) {
        return text != null && CODE_PATTERN.matcher(text).matches();
    }

    static boolean typeOnly(Object input) {
        return input instanceof Envelope;
    }

    static boolean deconstruct(Object input) {
        return input instanceof Envelope(Metered(var n)) && n >= 0;
    }

    static boolean quadraticDuplicate(List<String> values) {
        for (int i = 0; i < values.size(); i++) {
            for (int j = i + 1; j < values.size(); j++) {
                if (Objects.equals(values.get(i), values.get(j))) {
                    return true;
                }
            }
        }
        return false;
    }

    static boolean hashedDuplicate(List<String> values) {
        return new HashSet<>(values).size() != values.size();
    }

    public static void main(String[] args) {
        Object[] values = {
            " java ", "", "  ", 9, -2, new Point(3, 4),
            new Point(-1, 5), new StringBuilder("abc"), null
        };
        for (Object value : values) {
            String expected = legacy(value);
            String actual = modern(value);
            if (!expected.equals(actual)) {
                throw new AssertionError("classification mismatch: " + value);
            }
            System.out.println(actual);
        }
        System.out.println("PARITY PASS: " + values.length);

        String[] codes = { "AB123", "XY999", "ab123", "AB12", "AB1234", null };
        for (String code : codes) {
            boolean expected = slowRegex(code);
            boolean actual = cachedRegex(code);
            if (expected != actual) {
                throw new AssertionError("regex mismatch: " + code);
            }
            System.out.println("regex " + code + "=" + actual);
        }
        System.out.println("REGEX PARITY PASS: " + codes.length);

        Envelope valid = new Envelope(new Metered(7));
        System.out.println("type only=" + typeOnly(valid) + ", reads=" + Metered.reads);
        System.out.println("deconstruct=" + deconstruct(valid) + ", reads=" + Metered.reads);
        System.out.println("missing nested=" + deconstruct(new Envelope(null))
                + ", reads=" + Metered.reads);
        System.out.println("negative=" + deconstruct(new Envelope(new Metered(-1)))
                + ", reads=" + Metered.reads);

        List<List<String>> duplicateSamples = List.of(
            List.of("A", "B", "C"),
            List.of("A", "B", "A"),
            Arrays.asList(null, "X", null),
            List.of("A"),
            List.of()
        );
        for (int i = 0; i < duplicateSamples.size(); i++) {
            List<String> sample = duplicateSamples.get(i);
            boolean expected = quadraticDuplicate(sample);
            boolean actual = hashedDuplicate(sample);
            if (expected != actual) {
                throw new AssertionError("duplicate mismatch: " + sample);
            }
            System.out.println("duplicates " + i + "=" + actual);
        }
        System.out.println("DUPLICATES PARITY PASS: " + duplicateSamples.size());
        System.out.println("ALL CHECKS PASSED");
    }
}
```

**Compile and run:** from the directory containing the file using JDK 21+.

```bash
javac --release 21 PatternOptimizationDemo.java
java PatternOptimizationDemo
```

**Exact stdout output:**

```text
text:java
blank
blank
non-negative:9
negative:-2
point:3,4
point:-1,5
other
other
PARITY PASS: 9
regex AB123=true
regex XY999=true
regex ab123=false
regex AB12=false
regex AB1234=false
regex null=false
REGEX PARITY PASS: 6
type only=true, reads=0
deconstruct=true, reads=1
missing nested=false, reads=1
negative=false, reads=2
duplicates 0=false
duplicates 1=true
duplicates 2=true
duplicates 3=false
duplicates 4=false
DUPLICATES PARITY PASS: 5
ALL CHECKS PASSED
```

### 12.1. Explaining the output

- **`PARITY PASS: 9`:** nine inputs produce identical results between legacy code and pattern switch, including `null`, `StringBuilder`, negative integers, and the `Point` record. No runtime numbers are recorded here, so **you cannot claim either version is faster**.
- **`REGEX PARITY PASS: 6`:** six identifier samples produce equivalent results between `String.matches` and a matcher from a precompiled `Pattern`. The test only proves correctness on these cases; verifying caching effectiveness requires measuring with real call counts and data.
- **`type only=true, reads=0`:** checks only `Envelope`, without deconstructing `Metered`.
- **`deconstruct=true, reads=1`:** the nested record pattern reads the `Metered.value()` component once in this case.
- **`missing nested=false, reads=1`:** a `null` nested record does not match and does not increment accessor reads.
- **`negative=false, reads=2`:** the record is still deconstructed, then the `n >= 0` guard fails; the accessor still ran.
- **`DUPLICATES PARITY PASS: 5`:** both duplicate-detection algorithms agree on normal lists, lists with duplicates, lists with `null`, single-element lists, and empty lists. The complexity difference is not inferred from the output; it comes from loop structure vs hashing and requires benchmarking to evaluate constant-factor costs.

**Correctness caveat:** If inputs have different structures or behaviors than the examples (broken custom `equals/hashCode` contracts, mutable structures, special subtypes, accessor exceptions), test them separately. The example's goal is to **illustrate how to think**, not to claim two approaches are always equivalent for every possible object.

## 13. Designing tests before concluding an optimization

An optimization that breaks behavior is a regression, even if it makes a benchmark faster. At a minimum, verify:

| Group | Data / scenario | Expectation |
| --- | --- | --- |
| Common type match | String, Integer, Point | Same output/branch |
| Blank/whitespace strings | `""`, `"  "`, `" java "` | Same normalization rule |
| Boundary numbers | 0, -1, large numbers | No change in branch/overflow behavior |
| Null selector | `null` | Same fallback or approved exception |
| Other types | StringBuilder, Object | Not captured by overly broad type branches |
| Guard true/false | Data passing/failing guards | Same branch selection order |
| Nested null | Envelope(null), null record component | No accidental deconstruction/null-dereference |
| Custom accessor | With counter/exception | Check side effects if contract depends on them |
| Valid/invalid regex | Valid/invalid format strings, null | Both approaches return the same boolean |
| Empty, single-item, duplicate, null collections | Representative lists | Both algorithms yield the same result |
| Data scale | Small, medium, large | Measure latency/allocations after correctness PASS |
| JDK environment | Java 21 and real runtime | Build + test on target configuration |

You should have **unit tests** and **differential tests** for both versions, along with benchmarks on representative mixed loads. For performance, state a clear hypothesis to prove: *"on system X, input distribution Y, the new code reduces p95 CPU without increasing GC or errors"* rather than *"using patterns will be faster"*.

If logic performance depends on only a few inputs, you can benchmark them individually to understand per-type costs; however, you must also measure end-to-end with production data and behavior.

## 14. Common misconceptions

### Misconception 1 — "Patterns are always faster than casts"

There is no such language guarantee. Legacy code with `instanceof` + cast can be very well optimized by the JIT. Patterns help avoid manual casts and clarify scope, but performance must be measured.

### Misconception 2 — "Every `switch` expression is more efficient than `if/else`"

Not necessarily. When a `switch` adds guards, record deconstruction, or allocations, the total work can differ. Given identical behavior, only a benchmark can answer the specific question.

### Misconception 3 — "Using `record Point(var x, var y)` eliminates all object allocations"

A record pattern is **not** a mechanism that automatically applies scalar replacement to every object. It reads the structure of an existing object. The JIT may optimize in certain cases, with no guarantee for all.

### Misconception 4 — "Switching to patterns removes the need for profiling"

If the goal is performance, profiling remains the step to identify hotspots. Pattern matching is a coding tool, not a profiler.

### Misconception 5 — "A one-off `nanoTime` benchmark in `main` is enough"

That measurement is easily skewed by warm-up, dead-code elimination, and noise. JMH and end-to-end telemetry are better suited when reliable conclusions are needed.

### Misconception 6 — "Precompiling regex always makes every call faster by a fixed percentage"

Reusing `Pattern` avoids repeated regex compilation, but there are still matcher creation costs, initialization, usage patterns, and JIT effects. There is no universal speedup figure.

### Misconception 7 — "Speeding up CPU is enough; no need to test null and exceptions"

You can accidentally change `null` results when converting `instanceof` to `switch`. If semantics differ, benchmark results are no longer comparing the same problem.

### Misconception 8 — "Fewer lines of code means fewer allocations"

A single line like `stream.map(...).collect(...)` or `case String s -> expensiveTransform(s)` can still create many objects and do heavy work. Count objects, profile the heap, and check algorithms instead of just counting lines.

### Misconception 9 — "Using HashSet is always optimal"

`HashSet` trades memory and hashing cost to reduce repeated linear scans. For small inputs, a simple loop may be more suitable. If equality semantics differ or `hashCode` is broken, a `Set` can even produce wrong results.

### Misconception 10 — "The JIT will automatically fix every O(n²) algorithm"

The JIT can optimize many low-level operations, but it makes no promise to replace a pairwise comparison algorithm with a `HashSet` according to business semantics. Choosing the right algorithm remains the designer's responsibility.

## 15. Performance review checklist

- [ ] Distinguish **readability/type safety goals** from **performance goals**.
- [ ] Confirmed code runs on target JDK source/release; Java 21 record/switch patterns need no preview.
- [ ] Have a baseline and measurable goals (latency, throughput, CPU, allocation, GC, error rate).
- [ ] Have profiler/JFR or evidence identifying the actual hotspot.
- [ ] Pattern `switch` and legacy code have identical behavior for `null`, wrong types, guards, and case order.
- [ ] No dominated branches, exhaustive `switch` expressions, and no accidental exception changes.
- [ ] Record deconstruction only reads components that are actually needed; custom accessors have been evaluated.
- [ ] Short-circuiting is not altered, and computations with side effects are not pulled out of guards.
- [ ] Considered allocations, temporary collections, regex, I/O, DB, locks, and data conversion costs.
- [ ] For large data structures, compared algorithmic complexity before micro-optimizing.
- [ ] Have regression/differential tests before measuring, without adjusting expected outputs just to make tests pass.
- [ ] Benchmarks use representative input/branch distributions, warm-up, forks, iterations, and guard against dead-code elimination.
- [ ] Measurement results specify JDK/OS/hardware/config and variance metrics; do not report speedup figures without measuring.
- [ ] Measured end-to-end (p95/p99, throughput, memory/GC).
- [ ] Reviewed CPU/memory/code-complexity trade-offs and have a rollback plan if results degrade.

**DONE criteria:** Code is easy to understand and adheres to its contract; performance is evaluated from **metrics suited to the workload and environment**, not from pattern matching syntax. If no meaningful improvement is found, you can still keep the refactor for readability/type safety benefits, but **do not claim an unproven performance optimization**.

## 16. Self-check questions

**1. Does pattern matching replace choosing a good algorithm?**  
No. Patterns help check/extract values, while algorithmic complexity and data organization still must be designed separately.

**2. Why isn't `instanceof String s` guaranteed to be faster than `instanceof String` followed by a cast?**  
The JVM/JIT can optimize the old approach using the same type information; there is no speed guarantee from line count or syntax alone.

**3. Does `case String s when expensiveRule(s)` automatically make `expensiveRule` cheaper?**  
No. The guard is an actual call/expression that still consumes time and can produce side effects.

**4. Does `case Box(Point(var x,var y))` need to read components?**  
Yes. A nested record pattern deconstructs data; if you only need to know the outer type, a type pattern may suffice.

**5. What part does caching `Pattern` optimize?**  
It avoids compiling the regex repeatedly for a fixed rule; a matcher is still needed and must be measured with a real workload.

**6. Should a single `static Matcher` be shared across all threads?**  
No. `Matcher` is stateful and not thread-safe. You can share a compiled `Pattern`, while matchers should be per-operation or have explicit synchronization.

**7. Why is JMH better than just `nanoTime()` in a loop?**  
JMH supports warm-up/forks/iterations and mechanisms to avoid JVM pitfalls; even so, you must still design a valid benchmark yourself.

**8. Why does switching an O(n²) loop to a HashSet usually matter more than switching `if` to `switch`?**  
Because it changes how the number of operations grows with data size, not just how control flow is written; in return, it requires memory and hashing.

**9. When is a pattern refactor still worth doing if benchmarks are not faster?**  
When it improves type safety, readability, and maintainability without changing behavior and with acceptable performance cost. Call it what it is: a code-quality refactor.

**10. Why do you need to check `null` before comparing performance of `if instanceof` and `switch`?**  
Because `instanceof` does not match `null`, whereas a pattern `switch` usually needs `case null` to preserve the fallback; otherwise, the code may throw an NPE and is no longer equivalent.

**11. Is a JMH benchmark for `String` enough to draw conclusions for `Point`, `Integer`, and mixed cases?**  
No. Profiling/JIT/branch behavior and the work inside each case differ; you need to represent the actual input distribution.

**12. What should be reported if real measurements have not been taken yet?**  
State the hypothesis, code changes, theoretical impact (e.g., average complexity), parity tests, and benchmark plan; **do not report unverified numbers or speedup figures**.

## Official references

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Oracle Java SE 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html)
- [Oracle Java SE 21 — String.matches](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html#matches(java.lang.String))
- [Oracle Java SE 21 — java.util.regex.Pattern](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Pattern.html)
- [Oracle Java SE 21 — java.util.regex.Matcher](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/regex/Matcher.html)
- [OpenJDK — Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
- [Oracle JDK — Java Flight Recorder](https://docs.oracle.com/en/java/javase/21/jfapi/)
- [JLS SE 21 §14.30.2 — Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2)
