# Pattern `switch` and Branch Count: Understanding Performance, Measuring Properly, and Optimizing Right

## 1. The Problem Statement

When using **pattern matching for `switch`** in Java 21, a method can classify many value types:

```java
static String kind(Object value) {
    return switch (value) {
        case String s -> "string";
        case Integer i -> "integer";
        case Long l -> "long";
        case Double d -> "double";
        case Boolean b -> "boolean";
        case null -> "null";
        default -> "other";
    };
}
```

As more `case` branches are added, a common question is: **"Is a `switch` with 20 or 50 branches slower than a `switch` with 5 branches?"** The accurate answer is: **you cannot conclude that just by counting branches**.

Actual performance also depends on:

- **Input data distribution**: frequency of hitting each type/branch, `null` data, and `default` ratio.
- **Nature of `case` labels**: type pattern, constant label, record pattern, `when` guard, or general case.
- **Order of patterns that may match the same value**: Java selects the first matching label according to `switch` semantics.
- **Intrinsic cost of guards and branch bodies**: method calls, accessor reads, allocations, I/O, data queries.
- **Static type of the selector**: `Object`, enum, sealed interface, generic type, etc.
- **`javac`, JVM, JIT, warmup state, and call-site profile**: the implementation/optimization strategy is not fixed by the number of source lines.

This lesson focuses on **performance related to branch count and structure** of pattern `switch`, and is not intended to replace the full knowledge of `switch` syntax.

**Version:** Pattern matching for `switch` and record patterns became standard in **Java 21** (JEP 441, JEP 440). The examples use `javac --release 21` with JDK 21 or later.

## 2. What Does Java Guarantee, and What Is Only an Optimization Detail?

You must separate **semantics** from **execution strategy**:

| Thing to know | What does Java guarantee? | Do not infer on your own |
| --- | --- | --- |
| Multiple `case` labels can match the same selector | Selects the first matching `case` according to matching/dominance rules | Each `case` always corresponds to an `instanceof` check executed linearly |
| `when` guard | Only evaluated when the preceding pattern matches; if the guard is false, continues searching for a suitable case | The guard is always called once for every input |
| Record pattern | Checks structure and deconstructs components according to Java rules | Component access is always free, or always more expensive than calling the accessor directly |
| Exhaustiveness | The compiler can check branch completeness for sealed/enum/generic coverage | Exhaustiveness automatically makes dispatch faster |
| `default` | Provides the remaining fallback path according to label selection rules | `default` automatically handles a `null` selector |
| Source branch count | Indicates logic complexity that needs review | Runtime is necessarily proportional to N |

`switch` has semantic ordering, but the compiler and JVM **are allowed to optimize** how branches are selected as long as observable behavior is preserved. Therefore, claims like **"20 cases = 20 type checks on every call"**, **"doubling the cases = twice as slow"**, or **"pattern switch is always faster than `if/else`"** have no basis without measuring on a specific JDK and workload.

In JDK 21, the [`java.lang.runtime.SwitchBootstraps`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/runtime/SwitchBootstraps.html) API provides bootstrap methods for `invokedynamic` call sites involved in type-based `switch` label selection. The `typeSwitch` method takes the selector, the starting index to search from, and the labels; it returns the index of the matching label, or a value indicating no label matched. This is useful information when reading bytecode, **not a JLS guarantee that every `switch` must have the same bytecode, the same algorithm, or the same complexity** across all JDKs.

## 3. More Branches Do Not Mean More Checks

For example, with the same `Object` selector, the following method has seven type pattern branches:

```java
static int dispatch(Object value) {
    return switch (value) {
        case String s -> s.length();
        case Integer n -> n;
        case Long n -> n.intValue();
        case Double n -> n.intValue();
        case Float n -> n.intValue();
        case Character c -> c;
        case Boolean b -> b ? 1 : 0;
        case null -> -1;
        default -> 0;
    };
}
```

The `case String s` branch can be selected for a string without executing the logic of the `Long`, `Double`, `Float`, etc. branches at the **semantic level**. How many physical comparisons the JVM performs is another matter, because the JIT can optimize or combine checks.

Increasing the number of cases itself can also bring **larger generated code, more labels, and more guard logic**, but the actual impact depends on scale and profile. When code grows large enough to affect inlining, the instruction cache, or JIT compilation time, you need to measure instead of guessing.

If a new `case` almost never matches in a typical workload, the impact may differ from adding a case that handles a type accounting for most requests. **Input type distribution is part of the benchmark**, not a secondary factor.

## 4. Runnable Example: Multiple Type Patterns with Deterministic Results

Save to `TypeSwitchDemo.java`:

```java
import java.util.List;

public class TypeSwitchDemo {
    record Point(int x, int y) {}

    static String classify(Object value) {
        return switch (value) {
            case String s -> "String:" + s;
            case Integer n -> "Integer:" + n;
            case Long n -> "Long:" + n;
            case Double d -> "Double:" + d;
            case Boolean b -> "Boolean:" + b;
            case Point(var x, var y) -> "Point:" + (x + y);
            case List<?> xs -> "List:" + xs.size();
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
            "x", 3, 4L, 2.5, true,
            new Point(2, 3), List.of(1, 2),
            null, new Object()
        };

        for (Object value : values) {
            System.out.println(classify(value));
        }
    }
}
```

Compile/run:

```bash
javac --release 21 TypeSwitchDemo.java
java TypeSwitchDemo
```

Stdout:

```text
String:x
Integer:3
Long:4
Double:2.5
Boolean:true
Point:5
List:2
null
other
```

The program has many different labels, including type patterns (`String`, `Integer`, etc.), a **record pattern** (`Point(var x, var y)`), a type pattern with a **generic wildcard** (`List<?>`), `case null`, and `default`.

The branches have very different intrinsic costs: concatenating strings to build output, adding two `int` values, calling `size()` on a collection, etc. If you put `classify` as a whole into a benchmark and see differences between inputs, **you cannot automatically attribute all of that difference to case position**. The cost of the executing branch body itself is already different.

**Generic note:** `case List<?> xs` only verifies at runtime that the value is a `List`; it does not check the type argument of each element. Do not replace it with a raw `List` to "optimize" type erasure.

## 5. Pattern Ordering: Prioritize Correctness Before Speed

Patterns in a parent–child type relationship can match the same object. Java has **dominance** rules to prevent branches that are guaranteed to be unreachable.

The following snippet **intentionally does not compile**:

```java
static String wrong(Object value) {
    return switch (value) {
        case CharSequence seq -> "sequence";
        case String text -> "string"; // Dominated by the case above.
        default -> "other";
    };
}
```

`String` implements `CharSequence`, so if an unguarded `CharSequence` case comes first, a `String` value is always matched by that case. The compiler reports an error that `case String` is dominated.

The valid way is to place the **more specific type before the more general type**:

```java
static String correct(Object value) {
    return switch (value) {
        case String text -> "string";
        case CharSequence seq -> "sequence";
        default -> "other";
    };
}
```

These two snippets are **illustrations inside an existing class context**, not two standalone Java files.

You should not try to move a general type earlier to "increase cache hits" if doing so breaks logic or is rejected by the compiler. Ordering must satisfy **subtype relationships**, **dominance**, specific constants, and **business semantics** first. Only after that should you optimize where a real performance issue exists.

For unrelated types (`String` and `Integer`), changing the order can preserve the result, but **there is no guarantee that reordering will improve throughput**: you need to measure with a realistic distribution on the target JDK.

## 6. `when` Guards: Which Branch Incurs the Cost?

A guard is evaluated only when **the corresponding pattern has matched**. A guard can be as simple as `s.length() >= 4` or as expensive as a method performing regex matching, lookups, or complex computation.

Save to `GuardOrderDemo.java`:

```java
public class GuardOrderDemo {
    static int checks = 0;

    static boolean isLong(String text) {
        checks++;
        return text.length() >= 4;
    }

    static String classify(Object value) {
        return switch (value) {
            case String text when isLong(text) ->
                    "long:" + text;

            case String text ->
                    "short:" + text;

            case Integer number ->
                    "int:" + number;

            case Long number ->
                    "long-number:" + number;

            case null ->
                    "null";

            default ->
                    "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify("java") + " checks=" + checks);
        System.out.println(classify("go") + " checks=" + checks);
        System.out.println(classify(7) + " checks=" + checks);
        System.out.println(classify(null) + " checks=" + checks);
    }
}
```

```bash
javac --release 21 GuardOrderDemo.java
java GuardOrderDemo
```

Stdout:

```text
long:java checks=1
short:go checks=2
int:7 checks=2
null checks=2
```

This is an example that **counts how many times the guard is called**, not a timing benchmark. For `"java"` and `"go"`, the `String` pattern matches, so the guard runs; for `Integer` or `null`, the `isLong` guard does not run. The value `"go"` fails the guard, so it is handled by the general `String` branch.

**Performance lessons:**

- A heavy guard placed on a high-frequency branch can cost more than type selection itself.
- A guard that does not match causes the engine to continue evaluating subsequent labels.
- Putting guards with side effects in production code usually makes `switch` hard to understand, hard to benchmark, and hard to maintain. `checks++` here is **only an illustrative device**.
- Two guards for the same type that check different conditions must preserve the order and results required by business logic.

If an unguarded general case precedes a specific case, the specific case can be dominated. Conversely, for a guarded pattern where the compiler cannot prove the guard is always true, branch selection depends on the runtime guard result.

## 7. Multiple Guards for the Same Type: Optimize Logic Instead of Just Adding `case`s

Example:

```java
static String rate(Object value) {
    return switch (value) {
        case Integer n when n >= 100 -> "high";
        case Integer n when n >= 50 -> "medium";
        case Integer n when n >= 0 -> "low";
        case Integer n -> "negative";
        default -> "not-an-integer";
    };
}
```

Here, for `Integer`, guards are used to group values into buckets. The number of branches increases, but the primary goal is **defining non-overlapping ranges without errors**. `n=120` must be `"high"`; `n=70` is `"medium"`; `n=20` is `"low"`; `n=-2` is `"negative"`.

If there are hundreds of thresholds, declaring hundreds of `case` branches can make the source hard to read. In that situation, consider an **explicit search algorithm / range table**, or a single `case Integer n` branch calling a classification helper. Only choose a new structure after considering table-lookup cost, locality, dynamic thresholds, and benchmark results.

Note: converting from multiple `case ... when` branches to a helper changes program structure. You need to test boundary values and preserve priority order so behavior is not accidentally altered.

## 8. Record Patterns: Cost Also Lies in Deconstruction

A `switch` with a record pattern both selects a subtype and extracts components:

```java
record Price(long cents) {}
record Invoice(String id, Price price) {}

static String describe(Object value) {
    return switch (value) {
        case Invoice(var id, Price(var cents)) ->
                id + ":" + cents;

        case Invoice invoice ->
                "missing-price:" + invoice.id();

        default ->
                "other";
    };
}
```

The snippets above are **illustrative code placed together in one class/scope**, not standalone files.

With an `Invoice` containing a `Price`, the JVM needs to perform matching and retrieve the components requested by the pattern. If the `Price` component is `null`, the nested pattern `Price(var cents)` does not match, so the subsequent `Invoice invoice` branch can run.

Regarding performance:

- A record pattern **does not automatically create a copy** of the record in order to deconstruct it.
- Java may have to **invoke component accessors**. If an accessor is overridden with expensive logic, that logic itself affects performance.
- Deeply nested record patterns can add more matching/component reads, especially when encountering many nulls or mismatches at deep levels.
- However, the equivalent code written with `instanceof` and manual accessor calls **may also have to do similar work**. You cannot conclude that record patterns are always faster or slower than manual code based on syntax alone.

If a pattern is too long, consider extracting it into a helper, or using a type pattern and handling components in a controlled way. Splitting is only worth calling a performance optimization when a difference is measured on a real workload.

## 9. Sealed Hierarchies Help Control Branches, Not Guarantee Speed

`sealed` restricts the permitted direct subtypes. Combining it with an exhaustive `switch` keeps source code clear and forces updates when a new subtype is added.

Save to `SealedRoutingDemo.java`:

```java
public class SealedRoutingDemo {
    sealed interface Event
            permits Created, Charged, Cancelled, Failed {}

    record Created(String id) implements Event {}
    record Charged(String id, long cents) implements Event {}
    record Cancelled(String id) implements Event {}
    record Failed(String id, String reason) implements Event {}

    static String route(Event event) {
        return switch (event) {
            case Created(var id) ->
                    "created:" + id;

            case Charged(var id, var cents) when cents >= 1000 ->
                    "large-charge:" + id;

            case Charged(var id, var cents) ->
                    "charge:" + id + ":" + cents;

            case Cancelled(var id) ->
                    "cancelled:" + id;

            case Failed(var id, var reason) ->
                    "failed:" + id + ":" + reason;

            case null ->
                    "null";
        };
    }

    public static void main(String[] args) {
        Event[] events = {
            new Created("O1"),
            new Charged("O2", 500),
            new Charged("O3", 1500),
            new Cancelled("O4"),
            new Failed("O5", "limit"),
            null
        };

        for (Event event : events) {
            System.out.println(route(event));
        }
    }
}
```

```bash
javac --release 21 SealedRoutingDemo.java
java SealedRoutingDemo
```

Stdout:

```text
created:O1
charge:O2:500
large-charge:O3
cancelled:O4
failed:O5:limit
null
```

Here, `switch` does not need `default` because it handles all subtypes of `Event` and includes `case null`. If a `Refunded` subtype is added later, the compiler can require updating the `switch` on rebuild.

This is a **completeness guarantee for domain design**. It does not mean a sealed hierarchy necessarily dispatches faster than an open interface or `if/else`. Sealing may enable some optimizations in specific contexts, but **it does not turn exhaustiveness into a runtime-speed guarantee**.

When adding a subtype, both the number of branches and the data frequency of each branch can change. To compare before and after, you need to **normalize the workload or clearly report the new distribution**.

## 10. Comparing `switch` with `if/else instanceof`: Don't Compare Different Logic

The two approaches below are equivalent in result for the normal inputs shown:

```java
static int byIf(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    if (value instanceof Integer number) {
        return number;
    }
    return 0;
}

static int bySwitch(Object value) {
    return switch (value) {
        case String text -> text.length();
        case Integer number -> number;
        default -> 0;
    };
}
```

These are **two illustrative methods in the same class**, not standalone files. When `value == null`, `byIf` returns `0`, whereas `bySwitch` without `case null` can throw `NullPointerException`! Therefore, to be **fully equivalent** with `null`, you must add:

```java
case null -> 0;
```

to `bySwitch`, or enforce non-null inputs and only benchmark valid inputs according to the contract.

A fair benchmark must ensure both methods:

- Accept the same set of inputs.
- Return the same results for inputs in the workload.
- Have the same `null`, error, and validation policies.
- Perform the same amount of real work inside the branch bodies.

If one side allocates strings while the other only returns an integer, the measured result **does not reflect dispatch-cost difference**. If one side adds `default` and drops a business check, it is no longer the same logic either.

## 11. Distinguishing Pattern `switch`, Enum `switch`, and Constants

A `switch` over an `enum` or `int`/`String` constants typically has **different** conditions and optimization opportunities than a pattern `switch` with type checks and guards. For example:

```java
enum State { NEW, RUNNING, DONE }

static int simple(State state) {
    return switch (state) {
        case NEW -> 1;
        case RUNNING -> 2;
        case DONE -> 3;
    };
}
```

When comparing performance, do not treat a `switch` on an enum that already has a discriminant as a "same problem" control against `switch(Object)` that must distinguish runtime types on its own. The two problems have **different input type information**.

If a domain is already well modeled by enum constants with no per-variant payload, an enum may be the right structure. If variants carry different data and behavior, a sealed interface + records + pattern `switch` can provide a more type-safe model. Design decisions should not be driven by an uncontrolled microbenchmark.

In addition, `case "READY"` (constant label) is not the same as `case String text` (type pattern): one classifies a **constant value**, while the other matches **any string**. Do not treat them as equivalent branches just because both involve `String`.

## 12. JIT, Data Profiles, and Why Short Benchmarks Are Misleading

The JVM can observe selector types during execution and optimize hot code (*hot code*). Results can change depending on:

- JDK vendor/version and JVM flags.
- Warmup level and when tiered compilation/JIT kicks in.
- Frequency of each type at the call site (*type profile*).
- Method size, ability to inline helpers and branch bodies.
- Hot/cold data distribution and CPU branch prediction behavior.
- GC, temporary allocations, caches, OS, and machine environment.

Therefore, a test loop like:

```java
long started = System.nanoTime();
for (int i = 0; i < 1_000_000; i++) {
    dispatch("hello");
}
System.out.println(System.nanoTime() - started);
```

**is not enough to conclude** whether `switch` is fast or slow: the call may be inlined, the result may be eliminated if unused, the input has only one type, the benchmark mixes loop/timing overhead, or the JVM has not warmed up.

For Java microbenchmarks, you should use OpenJDK's **JMH (Java Microbenchmark Harness)** to control forks, warmup, measurement, and result consumption. There is no "universal" nanosecond number for branch count; measurements are only meaningful together with the environment and workload.

## 13. Designing a JMH Benchmark Comparing 2 vs. 7 Type Patterns

A well-defined experiment keeps the same inputs (`String` and `Integer`) while varying **the number of additional cases**. In this experiment, both methods return **the same result** for every benchmarked input.

The goal is not to prove speed always increases or decreases with N; it is to answer: "With a current workload consisting only of `String`/`Integer`, does adding five patterns for rare types measurably change performance?"

Below is an example **for use in a JMH project with annotation processing configured**, not a standalone class compiled with only the JDK. Place it in package `org.sample` of a JMH project and configure the compiler target to **Java 21**.

`BranchCountBenchmark.java`:

```java
package org.sample;

import java.util.concurrent.TimeUnit;
import org.openjdk.jmh.annotations.*;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Warmup(iterations = 5)
@Measurement(iterations = 5)
@Fork(2)
public class BranchCountBenchmark {
    @Param({"STRING_HEAVY", "INTEGER_HEAVY"})
    public String distribution;

    private Object[] inputs;
    private int index;

    @Setup(Level.Trial)
    public void setup() {
        inputs = new Object[1024];

        for (int i = 0; i < inputs.length; i++) {
            boolean useString =
                    distribution.equals("STRING_HEAVY")
                            ? i % 8 != 0
                            : i % 8 == 0;

            inputs[i] = useString
                    ? "word-" + i
                    : Integer.valueOf(i);
        }
    }

    private Object next() {
        return inputs[(index++) & (inputs.length - 1)];
    }

    @Benchmark
    public int twoPatterns() {
        return dispatch2(next());
    }

    @Benchmark
    public int sevenPatterns() {
        return dispatch7(next());
    }

    private static int dispatch2(Object value) {
        return switch (value) {
            case String text -> text.length();
            case Integer number -> number.intValue();
            default -> 0;
        };
    }

    private static int dispatch7(Object value) {
        return switch (value) {
            case String text -> text.length();
            case Integer number -> number.intValue();
            case Long number -> number.intValue();
            case Double number -> number.intValue();
            case Float number -> number.intValue();
            case Character ch -> ch;
            case Boolean flag -> flag ? 1 : 0;
            default -> 0;
        };
    }
}
```

**Experiment conditions:**

- `inputs` is created in `@Setup(Level.Trial)`, outside the measured methods.
- `@Param` varies the frequency of the two input types without changing correctness.
- `@State(Scope.Thread)` avoids sharing `index` across benchmark threads in a shared state.
- Both methods return `int`, and JMH manages consuming the benchmark method's return value to limit dead-code elimination.
- The additional cases in `dispatch7` **do not match the experiment's inputs**. Therefore, the results only evaluate the impact of extra cases in a **workload that mostly hits the first two cases**, and do not prove anything about all scenarios.
- There are no `null` inputs; both `switch` expressions have identical behavior for all inputs used. If you want to benchmark `null`, add the same `case null` to both methods and include `null` in the workload.

**Project setup:** following the [official JMH guide](https://github.com/openjdk/jmh), you can generate a project from the Maven archetype:

```bash
mvn archetype:generate \
  -DinteractiveMode=false \
  -DarchetypeGroupId=org.openjdk.jmh \
  -DarchetypeArtifactId=jmh-java-benchmark-archetype \
  -DgroupId=org.sample \
  -DartifactId=branch-bench \
  -Dversion=1.0
```

After generating the project, configure `maven-compiler-plugin` so the benchmark code is compiled with **JDK 21+** and `release` set to **21**. Example plugin configuration snippet:

```xml
<configuration>
    <release>21</release>
</configuration>
```

This is **a configuration snippet inside the Maven plugin**, not a complete `pom.xml` file. Make sure other source/target settings in the template do not conflict and that the JMH project still has annotation processing properly configured.

Add the benchmark class under `src/main/java/org/sample/`, then:

```bash
cd branch-bench
mvn clean verify
java -jar target/benchmarks.jar BranchCountBenchmark
```

The build/run commands require Maven and JMH dependencies; this benchmark code **has not been verified as executed here**. The goal is to provide a clear fixture for measuring on your target machine and JDK. Results include time/operation, error margin, forks, and parameters; **do not fill in hypothetical numbers**.

## 14. Interpreting Benchmarks Correctly

Suppose JMH reports numbers for `twoPatterns` and `sevenPatterns`. Before claiming one is faster, check:

1. Do both produce the **same result** across all selected inputs?
2. How large is the time/operation difference compared to the **error interval** and stability across forks?
3. Is the result consistent between `STRING_HEAVY` and `INTEGER_HEAVY`, or does the difference flip direction?
4. Was there enough warmup for the JIT to stabilize? Are there signs of GC or other system processes consuming resources?
5. Does the conclusion still hold when adding workloads with **types near the end**, `default`, `null`, and true/false guards?
6. Are you accidentally comparing against a method that actually does more work in its body?
7. Is the result reproducible on the **deployment JDK version**?

JMH measures microbenchmarks on the JVM and may not reflect total real-request latency. A service may be dominated by database, network, or JSON parsing; in that case, optimizing a type dispatch by a few nanoseconds has virtually no impact on end-to-end latency.

**Metrics to record:** JDK/vendor/version, CPU, OS, JVM mode, fork count, warmup/measurement, input distribution, unit of measurement, estimate, and uncertainty. Do not save just a single number and treat it as a permanent rule.

## 15. When You Want to Measure "Late Branches" or "default"

The 2-vs-7 benchmark above only uses two common types. To evaluate other scenarios, design dedicated fixtures:

- **Late-match:** inputs hit a type pattern located near the end in source order; keep output logic identical when changing unrelated case placement.
- **No-match:** inputs match no pattern and fall into `default`.
- **Guard-hit:** inputs match the type and the guard evaluates to true.
- **Guard-miss:** inputs match the type but the guard evaluates to false, requiring evaluation of subsequent cases.
- **Record-nested:** inputs are records with matching/non-matching nested components or `null`.
- **Polymorphic mix:** multiple runtime types appear at the same call site in realistic proportions.
- **Null:** measure only when the API actually allows `null`, and all compared methods handle it identically.

**Do not just change the inputs and still interpret the benchmark as the pure effect of case count**. Changing the input distribution can simultaneously alter branch-body cost, classification path, branch prediction, and JIT profiles.

If you need to benchmark dispatch cost in isolation, have each branch return a small integer and ensure identical return values for identical inputs across variants. If you need an end-to-end benchmark, keep real business logic in the branches, then analyze case-selection cost separately from work done inside the case.

## 16. Reading Bytecode: Useful for Diagnostics, Not a "Speed Leaderboard"

After compiling a Java 21 example, you can inspect:

```bash
javap -c -p TypeSwitchDemo
```

This command requires the compiled class in the current directory. You can see structures related to `invokedynamic`/`SwitchBootstraps`, bytecode branches, and component extraction depending on the `switch` shape and JDK.

Reading bytecode is useful for asking questions:

- How does `javac` emit the call site or labels?
- Where is the guard evaluated?
- Where does `null` handling live?
- Which accessor calls or casts appear?
- How does code size change as cases are added?

However, **bytecode is not the final machine code**: the JIT can inline, eliminate, reorder, or optimize checks while preserving semantics. Thus, `javap` is a tool for explaining structure, while **JMH/profilers** provide evidence of performance on the running JVM.

Nor should you take the internal algorithm of one JDK release and assume it applies to every future release. `SwitchBootstraps` is the runtime API of a given deployment release, not an immutable performance formula.

## 17. Optimizations Worth Considering When `switch` Is Truly a Hotspot

**1. Keep conditions cheap and free of side effects.** Guards run on the matching path. If a guard performs I/O, heavy regex, or external data access, that cost is usually worth checking before optimizing case order.

**2. Separate heavy work from classification logic when appropriate.** A lightweight classification method that calls specialized helpers can be easier to profile and test, though it may also change inlining behavior. Measure before and after.

**3. Reduce unnecessary repeated accessor/parsing work.** If multiple branches use the same computed result, you can precompute it once **when doing so does not perform wasted work for other cases**. Do not hoist an expensive computation before the entire `switch` if only a few branches need it.

**4. Keep static types as precise as possible.** If the selector is already a sealed interface or enum, do not widen it to `Object` and add a series of unnecessary type checks. Preserving types lets the compiler verify exhaustiveness and can make code easier to optimize, though it does not guarantee a speedup.

**5. When the number of "business cases" is very large and dynamic:** consider a lookup table, handler registry, enum mapping, or polymorphic dispatch **if it fits the domain**. A registry/map has its own lookup, allocation, and indirection costs; it is not faster than `switch` by default.

**6. Do not use `default` just to shorten the case list of a sealed hierarchy.** It can hide missing handling for new subtypes; correctness and domain evolvability matter more than a few lines of code.

**7. Check `null` and error paths.** Add `case null` only when the API policy requires it; do not accidentally change `NullPointerException` behavior during refactoring.

None of the optimizations above should be declared "faster" until benchmarks prove it under appropriate conditions.

## 18. Common Pitfalls

| Misconception | Why it is wrong or incomplete | How to handle it |
| --- | --- | --- |
| "N cases always run N `instanceof` checks" | Not a JLS contract; JIT can optimize | Measure under target workload and JVM |
| "Adding cases always slows down linearly" | Depends on data types, matching cases, guards, generated code | Compare using JMH |
| "Putting broad types first is faster" | Can cause dominance errors or change results | Keep specific subtypes before general types |
| "Guards are negligible" | Guards can invoke expensive code | Profile guard cost, test true/false paths |
| "Record patterns are always free syntax" | Matching may access components/accessors | Measure the actual path, do not assume |
| "Exhaustive sealed `switch` is a speed optimization" | Exhaustiveness is a coverage-checking property | Treat it as a correctness guarantee; measure performance separately |
| "`default` handles null too" | `null` usually needs its own case or throws NPE | Test `null` policy |
| "Comparing `switch(Object)` with `switch(enum)` is fair" | Different selector types, data, and work | Use a control solving the same problem |
| "Timing 1 million iterations with `nanoTime` is enough" | Warmup/JIT/dead-code elimination skews results | Use JMH, forks, and varied inputs |
| "If a benchmark is faster, refactor immediately" | End-to-end impact may be tiny | Profile production, weigh complexity |
| "With many cases, replace immediately with `HashMap`" | Lookup maps have overhead and different semantics from patterns | Design an equivalent experiment before switching |
| "Branch count is the only performance metric" | Case bodies, allocations, I/O, and input distribution matter | Measure the full path and separate costs |

## 19. Checklist for Reviewing a Pattern `switch` with Many Branches

Before deciding to optimize, confirm:

- Are you on **Java 21 or another version**? Does the benchmark match the deployment JDK?
- Does the selector have a specific static type or was it widened to `Object`?
- Are cases ordered properly for **dominance**, constants, guards, and subtypes?
- Are any guards expensive, performing I/O, allocating objects, or having side effects?
- Do record patterns have custom accessors or deep multi-level deconstruction?
- Which cases does data normally hit? Are there rare cases or `default`?
- Is `null` handled explicitly and identically across compared variants?
- Do benchmarked variants have **identical semantics and identical outputs** on the input set?
- Does JMH include warmup, forks, measurement, varied inputs, and result consumption?
- Is the difference stable, large enough, and meaningful in **end-to-end profiling**?
- Does changing the structure lose exhaustiveness, hide new cases, or make code harder to read?

**Conclusion:** In pattern `switch`, **branch count is a variable to measure, not a formula for predicting performance**. Use accurate domain types, preserve matching order and behavior, keep guards reasonable, and measure with JMH on a representative workload. Only optimize the structure when measurements show `switch` is truly a bottleneck and the benefit justifies the added complexity.

## Official References

- [JEP 441 — Pattern Matching for `switch`](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [Oracle Java SE 21 — Pattern Matching for `switch` (guard, dominance, type coverage)](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java SE 21 JLS §14.11 — `switch` Statements](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §15.28 — `switch` Expressions](https://docs.oracle.com/en/java/javase/21/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java SE 21 API — `SwitchBootstraps`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/runtime/SwitchBootstraps.html)
- [OpenJDK JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh)
