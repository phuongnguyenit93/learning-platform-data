# Performance Impact of Nested Deconstruction in Java Pattern Matching

**Nested deconstruction** is the use of **nested record patterns** to check and extract data from multiple record levels in a single expression, for example `Shipment(var id, Customer(var name, Address(var city, Geo(var x, var y))), var units)`. This syntax can help code express **the data shape to match** very concisely. However, when analyzing performance, one cannot conclude that "more pattern levels always mean slower execution," or that "pattern matching is always faster than manual accessor calls," based solely on the number of parentheses or lines of code.

This lesson belongs to **Java Core Pattern Matching → Performance**. We will examine the runtime work that can arise when matching nested record patterns, the effects of **accessor calls**, **failed branches**, **guards**, **fallback patterns**, JIT optimizations, and how to measure with controlled benchmarks.

**Version:** Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) are standard features since **Java 21**. The complete programs below use Java 21+ and do not require `--enable-preview`.

## 1. What does nested deconstruction actually do?

Consider the data model:

~~~java
// Java 21+ snippet, records declared in a valid scope.
record Geo(int x, int y) {}
record Address(String city, Geo geo) {}
record Customer(String name, Address address) {}
record Shipment(String id, Customer customer, int units) {}
~~~

A nested record pattern can be written as:

~~~java
// Java 21+ snippet, 'value' is an Object.
String label = switch (value) {
    case Shipment(var id,
            Customer(var name,
                Address(var city, Geo(var x, var y))),
            var units) when units > 0 ->
            id + ": " + name + " / " + city + " / " + x + "," + y;
    case Shipment(var id, var customer, var units) ->
            "Incomplete " + id;
    case null -> "No shipment";
    default -> "Other";
};
~~~

How to read it:

1. The selector must be a non-`null` `Shipment`.
2. The `customer` component must match a non-`null` `Customer` record.
3. The `address` component must match a non-`null` `Address` record.
4. The `geo` component must match a non-`null` `Geo` record.
5. The variables `id`, `name`, `city`, `x`, `y`, and `units` are bound to their corresponding components.
6. The guard `units > 0` is evaluated **after the branch's pattern has matched**. When both the pattern and the guard are true, the first branch is selected.
7. If a reference component does not match, or the guard is false, Java can evaluate the subsequent `Shipment(var id, var customer, var units)` branch.

**Note on `null`:** A reference component in a record can be `null`. `var customer` can bind a `null` value, whereas a nested record pattern `Customer(...)` does not match `null`. This is a **behavioral** difference, not just a performance one.

### What nested deconstruction does *not* do on its own

- The `var` syntax does not create a copy of the entire record.
- Pattern binding **does not automatically create new `Customer`, `Address`, or `Geo` objects**. It reads and checks existing values; any new object creation, if present, must come from elsewhere (e.g., a custom accessor or your own code).
- Nested deconstruction does not automatically query a database, deserialize JSON, or call an API. If an accessor or an outer wrapper has logic that does those things, that is the cost and side effect of that **specific data access path**.
- Pattern matching is not equivalent to calling `equals()` to compare record structures. It is a mechanism for **type checking and matching component patterns**, not comparing two records with `equals()`.

Therefore, when comparing performance, you must clearly separate **the cost that may arise from retrieving and checking components** from **the cost of record instantiation, building result strings, I/O, or business logic**.

## 2. Potential sources of runtime cost

| Cost source | Why it occurs | What to watch out for |
| --- | --- | --- |
| Type and shape checks | Each nested pattern level needs to match the appropriate record type | The JIT may simplify part of this when runtime types are clear |
| Reading component accessors | Record patterns retrieve component values to continue matching | Default accessors are usually simple; custom-written accessors may do more work |
| Chain of `null` checks | A `null` reference component causes the nested pattern not to match | Which level fails affects how many steps were executed |
| Trying the next case | A failed branch may cause `switch` to evaluate a fallback pattern | May redo checks/component reads that the previous branch already performed |
| `when` guard | Runs only after the record pattern before the guard has matched | A guard at the end of a deep pattern may be evaluated too late for inputs that are frequently rejected |
| Input distribution | Ratio of complete data, missing components, other types, or guard-rejected inputs | Affects branch prediction, optimized code, and hot paths |
| Custom accessors | A record can define its own accessor instead of merely returning a field | Accessor side effects, exceptions, or cost can dominate the entire matching path |
| Branch result | String concatenation, object allocation, or service calls in the body | Can be much larger than the cost of deconstruction itself |

Thus, "depth of 3" does not correspond to a fixed number of nanoseconds. Actual time depends on **the data, compiler/JVM, accessor style, runtime profile, and work outside the pattern**.

### Do not read pattern nesting depth as the number of allocated objects

In the example:

~~~java
case Shipment(var id,
        Customer(var name, Address(var city, Geo(var x, var y))),
        var units) -> ...
~~~

The names `id`, `name`, `city`, `x`, and `y` are **pattern variables** holding extracted values, not clones of the records. If a benchmark constructs `new Shipment(new Customer(...))` in every measured iteration, the results may reflect **input data allocation**, rather than deconstruction cost alone.

## 3. Comparison with explicit accessor calls

Another way to write this is to check the top-level type first, then step through each accessor with `null` guards:

~~~java
// Snippet inside a method returning String, 'value' is an Object.
if (value == null) return "No shipment";
if (!(value instanceof Shipment shipment)) return "Other";

Customer customer = shipment.customer();
if (customer == null) return "Incomplete " + shipment.id();

Address address = customer.address();
if (address == null) return "Incomplete " + shipment.id();

Geo geo = address.geo();
if (geo == null || shipment.units() <= 0) {
    return "Incomplete " + shipment.id();
}

return "OK " + shipment.id() + ": " + customer.name()
        + " to " + address.city() + " (" + geo.x() + "," + geo.y()
        + ") x" + shipment.units();
~~~

Compared to nested record patterns:

- **Nested pattern:** the structure to match sits right inside the `case`. It can be very readable when the data domain is straightforward and you mainly care about the success branch.
- **Explicit accessors:** the check steps and guard order are explicit; each value can be stored in a local variable when you want to reuse it multiple times.
- **Both:** can be optimized by the JIT; you should not claim one is faster solely based on syntax.
- **Important:** when refactoring code, you must preserve `null` semantics, check ordering, exception types, and results for non-matching cases.

Accessing components via accessors is part of the record protocol. If a default accessor simply returns a field, the JVM has opportunities to inline it. If an accessor is custom-defined with side effects, those effects still belong to the program; you must not assume the compiler will eliminate them.

## 4. Special example: fallbacks can read accessors multiple times

A record **can define its own component accessor**. When it does, the number of accessor calls becomes observable behavior. Consider this illustration:

~~~java
record Geo(int x, int y) {}

record Tracked(Geo geo) {
    static int reads;

    public Geo geo() {
        reads++;       // For observation only, not a production design.
        return geo;
    }
}
~~~

And the branching:

~~~java
// Snippet in a class containing Tracked and Geo as above.
static String trace(Object value) {
    return switch (value) {
        case Tracked(Geo(var x, var y)) -> "Point " + x + "," + y;
        case Tracked(var geo) -> "Missing point";
        case null -> "Null";
        default -> "Other";
    };
}
~~~

If `Tracked.geo()` returns a valid `Geo`, the first branch matches. If it returns `null`, the nested `Geo(...)` does not match; Java proceeds to try `case Tracked(var geo)`. **Trying the second case may invoke the accessor again**.

In the complete program in Section 6, under the verified environment (JDK 24), the observed results are:

- `Tracked(new Geo(1, 2))`: `reads = 1`.
- `Tracked(null)`: `reads = 2`, because the first nested match fails and the fallback case reads the component again.

**Do not generalize the numbers 1 and 2 to every program or JDK.** They are the result of this exact code structure and the accessor with side effects in the example. The compiler, JIT, case structure, and pattern kinds affect how code is executed; when comparing actual performance, measure the running code.

### Why are custom accessors worth noting?

- They can contain computation, allocation, or even side effects.
- They can throw exceptions; a failing accessor does not automatically equate to "pattern does not match."
- Repeated reads can increase cost or make results depend on external state.
- Accessor code should generally be **simple and stable**; if there is complex business logic, an explicitly called method outside the pattern is easier to understand.

**Design tip:** Do not put network calls, audit logging, or domain state mutations inside a record accessor just because it is called "like a getter." With nested matching, the timing and number of reads are not an appropriate place to encode business logic with side effects.

## 5. Optimizing common failure paths before deep deconstruction

Suppose `units <= 0` is common and is already enough to reject a shipment, yet the first pattern checks all the way down to `Geo` before evaluating `when units > 0`. You can place a branch that **checks the simple value first**:

~~~java
// Java 21+, snippet in a switch expression on Object value.
String outcome = switch (value) {
    case Shipment(var id, var customer, var units) when units <= 0 ->
            "Invalid count " + id;

    case Shipment(var id,
            Customer(var name, Address(var city, Geo(var x, var y))),
            var units) ->
            "OK " + id + ": " + name + " / " + city + " / " + x + "," + y;

    case Shipment(var id, var customer, var units) ->
            "Incomplete " + id;

    case null -> "No shipment";
    default -> "Other";
};
~~~

From top to bottom:

1. The first case matches `Shipment` but only extracts direct components, checks `units <= 0`, and handles it early.
2. If the count is positive, Java then evaluates the nested branch to fully check `Customer → Address → Geo`.
3. If the nested data does not match, the `Shipment(...)` fallback handles the incomplete shipment.

**This is a change in the order of work, not a speed guarantee.** If the count is valid almost all the time, the extra case may add an additional check; if most inputs are rejected early, it can avoid deep deconstruction. Only a benchmark with a realistic data distribution can answer this.

**Watch out for semantics:** The snippet above returns `"Invalid count"` for a shipment that both has `units <= 0` and is missing `customer`, whereas the `nested` version in the main example returns `"Incomplete"`. That is a **change in error precedence**. When optimizing, clearly define which error takes priority when an input violates multiple conditions; tests must cover that case. Do not reorder cases just because it looks faster and accidentally alter the business contract.

### Small standalone prefilter example

Create `PrefilterDemo.java` if you want to try case ordering yourself:

~~~java
public class PrefilterDemo {
    record Node(String code) {}
    record Box(String id, Node node, int count) {}

    static String classify(Object value) {
        return switch (value) {
            case Box(var id, var node, var count) when count <= 0 ->
                    "Invalid count " + id;
            case Box(var id, Node(var code), var count) ->
                    "OK " + id + ":" + code;
            case Box(var id, var node, var count) ->
                    "Missing node " + id;
            case null -> "Null";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(new Box("A", new Node("N"), 0)));
        System.out.println(classify(new Box("B", new Node("N"), 2)));
        System.out.println(classify(new Box("C", null, 1)));
    }
}
~~~

Run commands:

~~~bash
javac --release 21 PrefilterDemo.java
java PrefilterDemo
~~~

Output:

~~~text
Invalid count A
OK B:N
Missing node C
~~~

The first guarded branch does not **dominate** the subsequent nested branch because it only accepts inputs with `count <= 0`, not all `Box` instances. Even so, the **unguarded catch-all `Box` case** is placed last, after the specific cases.

## 6. Complete Java 21+ program: comparing results and counting accessor calls

Create the file **`NestedDeconstructionPerformanceDemo.java`**:

~~~java
public class NestedDeconstructionPerformanceDemo {
    record Geo(int x, int y) {}
    record Address(String city, Geo geo) {}
    record Customer(String name, Address address) {}
    record Shipment(String id, Customer customer, int units) {}

    static String nested(Object value) {
        return switch (value) {
            case Shipment(var id, Customer(var name,
                    Address(var city, Geo(var x, var y))), var units)
                    when units > 0 ->
                    "OK " + id + ": " + name + " to " + city
                    + " (" + x + "," + y + ") x" + units;

            case Shipment(var id, var customer, var units) ->
                    "Incomplete " + id;

            case null -> "No shipment";
            default -> "Other";
        };
    }

    static String explicit(Object value) {
        if (value == null) return "No shipment";
        if (!(value instanceof Shipment shipment)) return "Other";

        Customer customer = shipment.customer();
        if (customer == null) return "Incomplete " + shipment.id();

        Address address = customer.address();
        if (address == null) return "Incomplete " + shipment.id();

        Geo geo = address.geo();
        if (geo == null || shipment.units() <= 0) {
            return "Incomplete " + shipment.id();
        }

        return "OK " + shipment.id() + ": " + customer.name()
                + " to " + address.city() + " (" + geo.x() + "," + geo.y()
                + ") x" + shipment.units();
    }

    record Tracked(Geo geo) {
        static int reads;

        public Geo geo() {
            reads++;
            return geo;
        }
    }

    static String trace(Object value) {
        return switch (value) {
            case Tracked(Geo(var x, var y)) -> "Point " + x + "," + y;
            case Tracked(var geo) -> "Missing point";
            case null -> "Null";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        Object[] samples = {
                new Shipment("S-1",
                        new Customer("Mai", new Address("Hue", new Geo(12, 34))), 3),
                new Shipment("S-2", new Customer("An", null), 2),
                new Shipment("S-3", null, 1),
                new Shipment("S-4",
                        new Customer("Bao", new Address("Da Nang", new Geo(5, 6))), 0),
                null,
                "text"
        };

        for (Object sample : samples) {
            String a = nested(sample);
            String b = explicit(sample);
            System.out.println(a + " | equal=" + a.equals(b));
        }

        Tracked.reads = 0;
        System.out.println(trace(new Tracked(new Geo(1, 2)))
                + " | reads=" + Tracked.reads);

        Tracked.reads = 0;
        System.out.println(trace(new Tracked(null))
                + " | reads=" + Tracked.reads);
    }
}
~~~

Compile and run:

~~~bash
javac --release 21 -encoding UTF-8 NestedDeconstructionPerformanceDemo.java
java NestedDeconstructionPerformanceDemo
~~~

Expected output:

~~~text
OK S-1: Mai to Hue (12,34) x3 | equal=true
Incomplete S-2 | equal=true
Incomplete S-3 | equal=true
Incomplete S-4 | equal=true
No shipment | equal=true
Other | equal=true
Point 1,2 | reads=1
Missing point | reads=2
~~~

### Result analysis

- **`S-1`** has all nested records present and `units > 0`. Both approaches return the same string.
- **`S-2`** is missing `Address`; the nested pattern does not match and selects the fallback. The explicit accessor version stops after the `address == null` check.
- **`S-3`** is missing `Customer`; the nested pattern fails earlier.
- **`S-4`** has the complete structure but `units == 0`, so the nested case's guard is false; the fallback returns `Incomplete`. The manual version also rejects the same input.
- **`null`** and a non-`Shipment` string are handled identically by both methods.
- **`Tracked(new Geo(1, 2))`** matches the first pattern, so the accessor is read once in the demo.
- **`Tracked(null)`** does not match the nested `Geo(...)`; the next pattern reads the component again. The demo records two reads.

**This test verifies equivalence across 6 sample inputs and counts accessor calls on 2 instrumented inputs. It is not a speed benchmark.** Both `nested` and `explicit` construct result strings, and `Tracked.reads` is a static variable with side effects, so these output lines cannot be used to conclude which approach is faster in production.

## 7. How to benchmark properly: prefer JMH, do not measure with a short loop

To measure the impact of nested deconstruction, you should use **JMH (Java Microbenchmark Harness)** instead of timing a few iterations once with `System.nanoTime()`. The JVM has **warmup, tiered compilation, JIT inlining, escape analysis, dead-code elimination**, and other characteristics that make manual microbenchmarks error-prone.

Recommended process:

1. **Choose the right question.** Do you want to measure the cost of *matching and extracting components* or the entire string-building method? If you only want the pattern part, avoid putting string concatenation or new record creation inside `@Benchmark`.
2. **Prepare inputs outside the measured section.** Use `@State` and `@Setup` in JMH to pre-create objects. The cases being compared should receive inputs with the same semantics.
3. **Separate data distributions.** Measure separately: successful nested match; null at `Customer`; null at `Address`; null at `Geo`; guard failure; wrong selector type. You can also add a mixed workload matching production ratios.
4. **Use the same output work.** Both approaches must return the same value and follow the same processing rules. You can return a small `int` derived from the components instead of a long `String`. JMH will consume the benchmark return value; or use `Blackhole` to prevent dead-code elimination.
5. **Use warmup, measurement iterations, and forks.** Measure multiple times across independent JVMs and observe the distribution rather than a single number.
6. **Lock down comparison conditions.** Same JDK/vendor, JVM flags, machine, configuration, same data, and same run mode. If you use `--release 21` to compile on a newer JDK, note that Java 21-compatible bytecode/source **does not mean the runtime is JVM 21**.
7. **Do not put counters with side effects into the speed benchmark itself.** Counters can block optimizations that would normally apply to pure accessors; for example, `Tracked` in Section 6 is for observing **call counts**, not measuring final optimized cost.
8. **Interpret results according to your use case.** If a nested pattern makes code clearer and the difference is within noise or does not affect the system profile, keep the readable solution. Only change when data proves it is a hot path with a real benefit.

### JMH conceptual skeleton

This is an **illustrative skeleton, not a standalone file**: you need to add the JMH dependency, move the demo classes into an appropriate package, declare benchmark state, and use the JMH launcher/plugin according to your project's setup.

~~~java
// Conceptual template once JMH is configured, with input created in @Setup.
@Benchmark
public String nestedPattern() {
    return NestedDeconstructionPerformanceDemo.nested(input);
}

@Benchmark
public String explicitAccessors() {
    return NestedDeconstructionPerformanceDemo.explicit(input);
}
~~~

If the goal is to benchmark pure matching cost, create two versions that **return a cheap result such as an integer**, rather than only comparing the two string-building methods above. The result string itself and its allocation can overshadow pattern/accessor cost.

**Units of measurement must be stated clearly:** ns/op, ops/s, or allocation bytes/op depending on the mode. Publish the JDK, number of iterations/forks, data distribution, and variance. Do not claim "nested pattern is N% faster" without specific, reproducible measurements.

## 8. What metrics should you observe besides latency?

When a method runs frequently, you can also observe:

- **CPU profile:** is hot time spent in matching, custom accessors, guards, or branch body logic?
- **Allocation profile:** are new objects/strings allocated inside the body or accessors?
- **Branch distribution:** does most data match immediately, or does it frequently fall through to a fallback after traversing deep?
- **Method inlining / compilation:** does the JIT inline simple accessors? Do not interpret JIT output as a guarantee across JVMs.
- **GC pressure:** how much allocation comes from constructing inputs and results?
- **Tail latency:** do rare but expensive failure paths affect p95/p99?

For real systems, it is usually best to **profile the whole service** first to find where optimization is needed, and only then use JMH to isolate a matching snippet. A deconstruction method taking a tiny fraction of CPU should not become a refactoring target just to "have fewer accessor calls."

## 9. Common pitfalls when reasoning about performance

| Misconception / pitfall | Why it is wrong or incomplete | What to do instead |
| --- | --- | --- |
| "4 levels of deconstruction allocate 4 objects" | Pattern binding does not automatically copy records | Separate input allocation from matching |
| "Record patterns are definitely slower than manual accessors" | The JIT can inline and optimize both | Benchmark on your actual JDK and workload |
| "Nested patterns are definitely faster because the code is shorter" | Line count does not reflect accessor/branch count | Profile and inspect case/fallback behavior |
| "A failing guard has zero cost" | The pattern must match before the guard runs | Check which level the guard is at and the input distribution |
| "Fallbacks are free" | Subsequent cases tried later may re-read components | Verify with tracing or a profiler |
| "Accessors are always pure field getters" | Records can declare custom accessors | Read the implementation and avoid side effects |
| "Counter increasing by 2 means double the time" | Call count does not reflect the full pipeline/JIT/CPU | Distinguish call counting from timing |
| "A single `System.nanoTime()` run is enough" | JVM warmup/optimizations and noise skew results | Use JMH with multiple forks/iterations |
| "Testing 1 input represents production" | Error branches, nulls, and other types have different distributions | Benchmark multiple shapes and realistic ratios |
| "Refactor for optimization without testing semantics" | Reordering guards/fallbacks can change error messages | Test cases that violate multiple rules |
| "`--release 21` fixes performance to JVM 21" | It sets the compile target, not the runtime JVM | Specify the exact JVM used to run the benchmark |

## 10. When to keep nested deconstruction and when to split steps

**Keep nested record patterns** when the data structure is stable, nesting depth is moderate, `null` behavior is clear, and the pattern expresses "it must have this exact shape to be processed" well. In particular, with a sealed hierarchy having several variants, an exhaustive `switch` is often more maintainable than a long chain of casts.

**Consider splitting steps/accessors** when:

- There are many nesting levels and you want to report failure reasons at each level.
- You need to reuse a component multiple times and want to avoid repeated calls to a custom accessor.
- A cheap condition can filter out most inputs before deep deconstruction.
- Business conditions or side effects are too complex to live inside `when`/patterns.
- Benchmarks/profilers show the matcher is a real hotspot, and the split-step version brings a measurable benefit while preserving semantics.

**Do not split just because you assume every accessor is expensive.** For records holding a few immutable values with default accessors, nested code can be very clean, and the JIT has many opportunities to optimize it. Conversely, do not keep an overly deep pattern if readers struggle to understand it, even if benchmarks show no issue.

### Choosing by goal

| Priority goal | Design approach to try |
| --- | --- |
| Express the data shape to match | Clear nested record pattern |
| Report detailed errors for missing components | Step-by-step accessors/guards, validation result |
| Preserve type safety for a closed set of variants | Sealed types + exhaustive switch |
| Avoid re-invoking a custom accessor | Extract into a local variable and reuse explicitly |
| Hot path with many early-failing inputs | Check cheap conditions first, then benchmark |
| Understand runtime differences | JMH + profiler + correctness tests |
| Perform I/O or transactions | Dedicated service, not hidden in record accessors/guards |

## 11. Practice exercises

### Exercise 1 — Analyzing the match path

Given:

~~~java
record Inner(String code) {}
record Outer(Inner inner) {}
~~~

With `Object input`, consider:

~~~java
String label = switch (input) {
    case Outer(Inner(var code)) -> "Code: " + code;
    case Outer(var inner) -> "Missing inner";
    case null -> "Null";
    default -> "Other";
};
~~~

If `input = new Outer(null)`, what is the result? Will `var inner` create a new `Inner`?

**Answer:** The nested `Inner(var code)` does not match the `null` component, so `case Outer(var inner)` is selected and the result is `"Missing inner"`. `var inner` simply binds the existing component (which is `null`); it does not create an `Inner` object.

### Exercise 2 — Comparing accessor call counts

With `Tracked` and `trace` in Section 6, why does `new Tracked(null)` produce `reads=2` in the demo run?

**Answer:** The first pattern `Tracked(Geo(...))` needs to call the accessor to get `geo`, but the `null` value does not match `Geo(...)`; Java proceeds to check the fallback case `Tracked(var geo)` and reads the accessor again. This is the observed behavior in the example, not a nanosecond timing measurement.

### Exercise 3 — An optimization that can change the result

With `Shipment("S-4", Customer(...), 0)`, the original `nested` version returns `"Incomplete S-4"`. If you place `case ... when units <= 0 -> "Invalid count"` before it, does the result change?

**Answer:** Yes. The result becomes `"Invalid count S-4"`. This is a **change in the output contract**, not just a change in speed. You need to decide from a business perspective which message is desired and update tests accordingly.

### Exercise 4 — Designing a fair benchmark

Someone writes a loop of 1 million iterations, creating new nested records on every iteration, concatenating strings, calling `nested`, and timing it with `System.nanoTime()`. Can they conclude that patterns are slow because it takes a long time?

**Answer:** No. The measurement mixes **object instantiation, memory allocation, string concatenation, and pattern matching**, and is also subject to warmup/JIT and noise. You should separate input preparation from measurement, ensure both methods return equivalent results, use JMH with multiple forks/iterations, and profile when needed.

### Exercise 5 — Choosing a maintainable style

An API needs to validate `Order`, `Customer`, and `Address` and return a **distinct error code** for each missing component. Should you use a very deep nested pattern or guarded steps?

**Answer:** Step-by-step access/guard checks or a validation result usually express error reasons more clearly. Nested patterns fit best when you only need to know whether the entire structure matches. Optimize for clarity first, and only refactor for performance after you have measurements.

## 12. Summary and references

- Nested record patterns perform **multi-level checking and data extraction**; they do not automatically clone or allocate a new record per level.
- Actual cost relates to **type checks, accessor calls, guards, fallbacks, input distribution**, and the code inside each branch.
- When a nested pattern fails and `switch` tries the next case, **accessors may be called again**; you can instrument to inspect behavior, but do not infer timing from call counts.
- **The JIT can optimize simple accessors and pattern checks**, but there is no universal rule that nested or explicit is always faster.
- Checking cheap conditions before deep deconstruction **can** help, but reordering cases can change semantics; correctness tests are mandatory.
- Benchmark with **JMH**, pre-built inputs, warmup/forks, multiple data shapes, and compare two truly equivalent implementations. Use a profiler to confirm the hot path.
- Prioritize readable and business-correct code; only trade clarity for optimization if there is performance evidence on a realistic workload.

**Official documentation:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440); [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441); [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html); [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html); [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/).
