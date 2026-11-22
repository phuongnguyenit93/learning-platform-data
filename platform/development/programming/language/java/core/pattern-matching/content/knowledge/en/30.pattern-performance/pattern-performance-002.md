# Accessor cost in record patterns

## 1. Record patterns are more concise, but not "free"

Since Java 21, **record patterns** allow checking a record's type and deconstructing its components in a single expression. For example:

```java
record Point(int x, int y) {}

static int sum(Object value) {
    if (value instanceof Point(int x, int y)) {
        return x + y;
    }
    return 0;
}
```

This is a valid illustrative snippet when placed alongside the record declaration, not a standalone program class. When `value` is a `Point`, Java checks the structure and retrieves the two component values to bind `x` and `y`.

An important point about performance: **record patterns do not read components directly by zero-cost magic**. According to the Java 21 specification, the value of each component during record deconstruction is determined by **invoking the corresponding accessor**. For `Point`, those are `x()` and `y()`. Therefore, behind the syntax:

```java
value instanceof Point(int x, int y)
```

you can picture operations involving determining whether the object has the right record type, retrieving component values via accessors, and matching the subpatterns.

However, you must not conclude that writing with a record pattern is **always slower** than code that calls accessors manually. When an accessor simply returns a field and the code runs hot enough, the JIT can inline or optimize those calls. Actual cost depends on the **accessor**, **pattern shape**, **number of match attempts**, **guard**, input data, and JVM optimizations.

This article answers four questions:

1. When are accessors invoked in a record pattern?
2. Why can custom accessors or repeated patterns increase cost?
3. When should you use a record pattern, a type pattern, or local variables?
4. How do you measure properly instead of optimizing by intuition?

## 2. What is an accessor in a record?

A record declares a fixed set of components:

```java
record Product(String code, int price) {}
```

Java provides accessor methods named after each component:

```java
Product product = new Product("P-1", 150);
String code = product.code();
int price = product.price();
```

For a simple record, the auto-generated accessor simply returns the corresponding field. A record also allows the author to **declare a custom accessor** matching the component's return type:

```java
record NormalizedName(String raw) {
    public String raw() {
        return raw == null ? "" : raw.strip();
    }
}
```

This is an illustrative example of a custom accessor. The value received via `raw()` can differ from the original field representation. More importantly, a custom accessor can perform additional operations: computation, formatting, validation, recording call counts, or even throwing an exception.

Because a record pattern calls accessors to determine component values, replacing a simple pattern with a deconstructing pattern can pull in the **cost of accessor logic**. This holds true even when the external syntax is only a few characters longer.

**Recommendation:** design record accessors to be simple, stable, and free of side effects or expensive operations. Having to read files, call remote APIs, or access a database inside an accessor is usually a sign of misplaced responsibility, not something to accept by default just because a record pattern will call it.

## 3. Comparing type patterns and record patterns

### 3.1. Type pattern: only checks type and binds the object

```java
if (value instanceof Product product) {
    System.out.println(product.code());
}
```

Here, `instanceof Product product` is a **type pattern**, not a record pattern. The type check itself does not need to deconstruct all components of `Product`. The `code()` accessor is only called when the body invokes it.

### 3.2. Record pattern: deconstructs components

```java
if (value instanceof Product(String code, int price)) {
    System.out.println(code);
}
```

Here we have a **record pattern**. To match the pattern, Java retrieves the components according to the record's contract and matches them against the component patterns. We only use `code` afterward, yet the pattern still lists `price` as well because the record structure has two components.

For a record with many components and expensive custom accessors, deconstructing every component just to use one value may not be the best choice. A type pattern with only the necessary accessor calls can be easier to control:

```java
if (value instanceof Product product) {
    String code = product.code();
    System.out.println(code);
}
```

**There is no absolute conclusion about speed.** If all accessors are tiny getters and the JVM can inline them well, the difference between the two approaches may be negligible. If an accessor performs heavy work, the difference can be very noticeable. Look at the **logic that must execute**, not just the number of parentheses.

## 4. When a switch tries multiple guarded record patterns

Consider this classification expression:

```java
return switch (value) {
    case Product(String code, int price) when price >= 100 ->
            "Giá cao: " + code;
    case Product(String code, int price) ->
            "Giá thấp: " + code;
    case null ->
            "Không có sản phẩm";
    default ->
            "Không phải sản phẩm";
};
```

This is an illustrative snippet inside a method returning `String`, with `value` already declared.

If the object is a `Product` and `price >= 100`, the first case is selected. But if `price < 100`:

1. The record pattern of the first case matches, so the guard `price >= 100` is evaluated and returns `false`.
2. Java moves on to consider the next case.
3. The second `Product(String code, int price)` case performs record matching again to select the `Giá thấp` branch.

With accessors that have observable side effects, these separate match attempts can lead to **repeated accessor calls**. Some optimizations can reduce execution cost for pure getters, but you should not rely on assuming the JVM will eliminate work with side effects or calls whose results might change.

If you only need to classify by price, writing a single type pattern and computing the price **once** in a block can be more transparent:

```java
return switch (value) {
    case Product product -> {
        int price = product.price();
        String code = product.code();
        yield price >= 100
                ? "Giá cao: " + code
                : "Giá thấp: " + code;
    }
    case null -> "Không có sản phẩm";
    default -> "Không phải sản phẩm";
};
```

This is also an illustrative snippet, not a standalone runnable file. The second approach clearly expresses that **we intentionally read each needed component only once** in the case body. It does not mean you must rewrite every pair of record patterns on sight: keep the more readable version when benchmarks show no practical benefit and the accessors are already cheap enough.

## 5. Custom accessors make the cost observable

A record can declare an accessor that counts how many times it is read:

```java
record Metered(int units, String label) {
    private static int accessCount;

    public int units() {
        accessCount++;
        return units;
    }

    static void reset() {
        accessCount = 0;
    }

    static int calls() {
        return accessCount;
    }
}
```

This is illustrative Java 21 code, assuming the record is declared in an allowed scope. The counter is used to observe **how many times the `units()` accessor is called**, not to measure nanoseconds.

With two cases for the same record:

```java
static String repeatedPattern(Object input) {
    return switch (input) {
        case Metered(int units, var label) when units >= 10 ->
                "EXPRESS " + label;
        case Metered(int units, var label) ->
                "STANDARD " + label;
        case null -> "NONE";
        default -> "OTHER";
    };
}
```

If `Metered` has `units = 5`, the first case matches the record, but the guard fails; the second case is tried next. In this example with a counting accessor, `units()` is called in both match attempts, so the counter increases by **2**. With `units = 12`, the first case is selected immediately, so the counter increases by **1**.

The approach that only checks the type and then uses accessors in a controlled way:

```java
static String typePattern(Object input) {
    return switch (input) {
        case Metered value -> {
            int units = value.units();
            yield (units >= 10 ? "EXPRESS " : "STANDARD ")
                    + value.label();
        }
        case null -> "NONE";
        default -> "OTHER";
    };
}
```

The code above reads `units()` **once** when the object is a `Metered`, then uses the local variable to make the decision. In a real system, if an accessor has expensive logic, storing the read value can both clarify intent and reduce repeated work.

**Important:** the `static` counter in this example is not thread-safe. It is only for a sequentially executed demonstration program; do not use this measurement technique to draw performance conclusions in a multithreaded application. Accessor calls with side effects are something to recognize, not a technique to encourage in ordinary record design.

## 6. Nested record patterns: cost accumulates with structure

Suppose a domain has nested records:

```java
record Address(String city, String street) {}
record Customer(String id, Address address) {}
record Order(String code, Customer customer, int total) {}
```

A deep pattern:

```java
if (input instanceof Order(
        var code,
        Customer(var id, Address(var city, var street)),
        var total)) {
    System.out.println(code + ": " + city);
}
```

Java must process the structure of `Order`, `Customer`, and `Address` to determine whether the entire record pattern matches. This process invokes accessors at every deconstructed record level. If there are many levels, many components, complex accessors, or frequent match failures, the work can be noticeably higher than a type pattern that only fetches the exact values needed.

Alternatively, when only the city is needed:

```java
if (input instanceof Order order) {
    Customer customer = order.customer();
    if (customer != null && customer.address() != null) {
        String city = customer.address().city();
        System.out.println(order.code() + ": " + city);
    }
}
```

The illustrative snippet above can still **call `customer.address()` twice**, so it is not necessarily better! If the `address()` accessor is expensive or has side effects, you can store it in a temporary variable:

```java
if (input instanceof Order order) {
    Customer customer = order.customer();
    if (customer != null) {
        Address address = customer.address();
        if (address != null) {
            String city = address.city();
            System.out.println(order.code() + ": " + city);
        }
    }
}
```

In this version, each call—`order.customer()`, `customer.address()`, and `address.city()`—is written **once**. This is one reason to split up the logic when the structure is too deep. Even so, in real code, prioritize correctness, `null` handling, and readability; only optimize after confirming that an accessor actually causes significant cost.

Beyond cost, remember that **a `null` selector does not match a record pattern**. If a nested record is required to match but the component at that position is `null`, the nested pattern fails. Rewriting with a type pattern plus guards/`null` checks must preserve the same behavior if used for refactoring.

## 7. Accessors throwing exceptions: not a false guard

An easily overlooked aspect is that an accessor **can throw an exception**, especially when explicitly declared.

According to **Java Language Specification 21, section 14.30.2**, if an accessor invocation for matching a record pattern completes abruptly with an exception, the record pattern matching completes abruptly with a **`MatchException`**, whose `cause` is the original error.

For example:

```java
record Fragile(int value) {
    public int value() {
        throw new IllegalStateException("Accessor failed");
    }
}
```

When run:

```java
static String inspectFragile(Object input) {
    return switch (input) {
        case Fragile(int value) -> "VALUE=" + value;
        case null -> "NULL";
        default -> "OTHER";
    };
}
```

If the input is `new Fragile(9)`, the object itself matches the `Fragile` type, but when the record pattern calls `value()`, the accessor throws `IllegalStateException`. Matching throws a `MatchException` whose cause is `IllegalStateException`. **Java does not treat an exception from an accessor as a false pattern match to fall through to `default`.**

Compare with:

```java
static String accessDirectly(Object input) {
    if (input instanceof Fragile fragile) {
        return "VALUE=" + fragile.value();
    }
    return "OTHER";
}
```

Here `Fragile fragile` is only a **type pattern**. Calling `fragile.value()` is an ordinary method invocation inside the `if` body, so the exception is thrown directly according to method invocation rules (in this example, `IllegalStateException`), not wrapped by record-pattern matching.

**Implication:** Before replacing manual accessor-reading code with a record pattern, check whether the accessor has custom logic or can throw an exception. Refactoring may preserve success values while **changing the surfaced exception type**, affecting error handling and tests. In a healthy domain model, pure, stable getters/accessors make both patterns and APIs easier to use.

## 8. Complete runnable Java 21 program

Create the file **`RecordAccessorCostDemo.java`**:

```java
public class RecordAccessorCostDemo {
    record Metered(int units, String label) {
        private static int accessCount;

        public int units() {
            accessCount++;
            return units;
        }

        static void reset() {
            accessCount = 0;
        }

        static int calls() {
            return accessCount;
        }
    }

    record Fragile(int value) {
        public int value() {
            throw new IllegalStateException("Accessor failed");
        }
    }

    static String repeatedPattern(Object input) {
        return switch (input) {
            case Metered(int units, var label) when units >= 10 ->
                    "EXPRESS " + label;
            case Metered(int units, var label) ->
                    "STANDARD " + label;
            case null -> "NONE";
            default -> "OTHER";
        };
    }

    static String typePattern(Object input) {
        return switch (input) {
            case Metered metered -> {
                int units = metered.units();
                yield (units >= 10 ? "EXPRESS " : "STANDARD ")
                        + metered.label();
            }
            case null -> "NONE";
            default -> "OTHER";
        };
    }

    static String inspectFragile(Object input) {
        return switch (input) {
            case Fragile(int value) -> "VALUE=" + value;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    static String accessDirectly(Object input) {
        if (input instanceof Fragile fragile) {
            return "VALUE=" + fragile.value();
        }
        return "OTHER";
    }

    public static void main(String[] args) {
        Metered low = new Metered(5, "A");
        Metered high = new Metered(12, "B");

        Metered.reset();
        System.out.println("record low: " + repeatedPattern(low));
        System.out.println("record calls: " + Metered.calls());

        Metered.reset();
        System.out.println("record high: " + repeatedPattern(high));
        System.out.println("record calls: " + Metered.calls());

        Metered.reset();
        System.out.println("type low: " + typePattern(low));
        System.out.println("type calls: " + Metered.calls());

        Metered.reset();
        System.out.println("other: " + repeatedPattern("not metered"));
        System.out.println("other calls: " + Metered.calls());

        try {
            inspectFragile(new Fragile(9));
        } catch (MatchException ex) {
            System.out.println("record exception: "
                    + ex.getClass().getSimpleName());
            System.out.println("record cause: "
                    + ex.getCause().getClass().getSimpleName());
        }

        try {
            accessDirectly(new Fragile(9));
        } catch (IllegalStateException ex) {
            System.out.println("direct exception: "
                    + ex.getClass().getSimpleName());
        }
    }
}
```

Compile and run with **JDK 21 or later** (no `--enable-preview` needed):

```bash
javac -encoding UTF-8 RecordAccessorCostDemo.java
java RecordAccessorCostDemo
```

Expected output:

```text
record low: STANDARD A
record calls: 2
record high: EXPRESS B
record calls: 1
type low: STANDARD A
type calls: 1
other: OTHER
other calls: 0
record exception: MatchException
record cause: IllegalStateException
direct exception: IllegalStateException
```

Output explanation:

- **Record pattern, units = 5:** the `Metered` pattern matches in the first case, the `units()` accessor increments the counter, and the guard `units >= 10` is false. Java checks the second `Metered` case, calls the accessor again, and returns `STANDARD A`. The read count is **2**.
- **Record pattern, units = 12:** the first case matches and the guard is true; no need to try the next case. The read count is **1**.
- **Type pattern, units = 5:** the `Metered metered` case only checks the type; the body calls `metered.units()` once, then uses the local variable to classify. The read count is **1**.
- **Other input type:** `"not metered"` does not match either `Metered` case, so the `units()` accessor is not called; the result is `OTHER`, and the counter is **0**.
- **Accessor throws in a record pattern:** `inspectFragile` produces a `MatchException` with `cause` `IllegalStateException`. A guard or `default` does not turn this error into "no match".
- **Accessor called directly:** `accessDirectly` throws `IllegalStateException` directly because it is an ordinary method call, not part of record-pattern matching.

The counter-based example only serves to **demonstrate accessor invocation behavior**. It does not measure time and does not prove that record patterns are "twice as slow" in a real application. Observable call count and actual CPU cost are two different quantities. A complex accessor with side effects can also affect correctness when called multiple times, not just performance.

## 9. Proper benchmarking: do not take a single System.nanoTime as proof

For auto-generated accessors that simply return a field, the JVM can inline them; a benchmark without warm-up easily compares **unoptimized bytecode** against **optimized machine code** and leads to false conclusions.

Do not trust a measurement pattern like:

```java
long start = System.nanoTime();
// Call the function once.
long elapsed = System.nanoTime() - start;
System.out.println(elapsed);
```

This is an illustrative measurement snippet, not a reliable benchmark for very small differences. The recorded time includes many factors such as clock resolution, startup overhead, system noise, JIT, GC, and surrounding overhead.

For serious measurement, consider **JMH (Java Microbenchmark Harness)**:

1. Use the **same workload**, same subtype distribution, and same data for both the record pattern and type pattern versions.
2. Place inputs in `@State` or an equivalent JMH mechanism; avoid having the benchmark mainly measure object allocation.
3. Include **warm-up**, **measurement iterations**, and multiple forks where appropriate.
4. Use `Blackhole` or return the benchmark result to prevent *dead-code elimination*.
5. Compare simple getters, custom getters with real computation, and both false and true guard cases.
6. Check both throughput and latency if relevant to production requirements; observe GC/allocation when objects are created.
7. Evaluate variance, result reliability, and practical impact rather than looking at a single number on a development machine.

The **JMH conceptual skeleton** below is **not a standalone runnable file**: it requires JMH dependencies and build plugin/configuration:

```java
@State(Scope.Thread)
public class AccessorBenchmark {
    Object input = new Product("P-1", 150);

    @Benchmark
    public Object recordPattern() {
        return input instanceof Product(var code, var price)
                ? code : null;
    }

    @Benchmark
    public Object typePattern() {
        return input instanceof Product product
                ? product.code() : null;
    }
}
```

The code above assumes `Product` is declared and `org.openjdk.jmh.annotations` is available. The purpose is to show two equivalent operations to measure on the same input. If the logic on the two sides differs (one parses a string, the other only returns a field), the measurement no longer answers "how much overhead does a record pattern have".

**Prioritize measuring on real workloads:** if profiling shows that record deconstruction accounts for only a tiny fraction compared to I/O, network, or business processing, tweaking pattern syntax may bring no meaningful benefit even if the number of accessor calls drops.

## 10. When should you optimize the code?

| Situation | Decision to consider | Why |
| --- | --- | --- |
| Small record, default accessors, and only one case | Keep the clear record pattern. | Can be inlined by the JIT; little reason for manual optimization. |
| Two or more cases of the same record with guards failing in sequence | Check for repeated deconstruction; benchmark if needed. | Accessor calls may repeat across match attempts. |
| Only one component needed from a record with many components | Consider a type pattern and call the needed getter. | Avoids deconstructing components that do not serve the task. |
| Explicitly declared accessor performs heavy computation | Separate responsibilities or cache values according to contract. | Reduces work that depends on match count. |
| Multi-level nested record pattern | Inspect the structure and inner accessors. | Cost can grow with real data and deconstruction depth. |
| Accessor has side effects or can throw exceptions | Redesign the accessor; write clear behavior tests. | Can affect correctness and the surfaced exception type. |
| Time is spent mainly in I/O/DB/network | Optimize bottlenecks confirmed by a profiler. | Changing pattern syntax may be negligible. |

Additional note: **caching data** does not mean blindly caching results for every input. If an accessor's value is designed to depend on external state, caching the result can change behavior. An ordinary record should represent stable, transparent data; if a getter is unstable, fix the API design before looking at speed.

## 11. Common misconceptions

### 11.1. "A record pattern is just a faster instanceof"

Incorrect. `instanceof Product product` is only a type pattern that checks the type and binds the object; `instanceof Product(var code, var price)` is a record pattern, which also deconstructs components via accessors. The two have different semantics and amounts of work.

### 11.2. "Counting two calls means twice as slow"

Incorrect. If a getter is inlined and has negligible cost, two calls can be cheap; if an accessor parses, allocates, or synchronizes, the cost is different. A counter with side effects also makes the workload different from a pure getter; do not use it as a timing benchmark.

### 11.3. "Every record accessor just returns a field"

False. A record can have explicit accessors with author-supplied logic. You need to understand the accessor's contract when using record patterns in performance- or exception-sensitive code.

### 11.4. "A false guard means no accessor cost at all"

False. For a record pattern, the `when` guard is evaluated **after the pattern matches**, so accessors may already have been called to retrieve components before the guard returns false. If the pattern fails at the type check, that record's accessors are not called.

### 11.5. "An exception from an accessor is equivalent to pattern mismatch"

Wrong. An accessor throwing an error while matching a record pattern causes matching to complete abruptly with a `MatchException` wrapping the original cause; it does not jump to `default`. You should have unit tests for failure behavior when an accessor is not guaranteed to be pure.

### 11.6. "Extracting a component with var always excludes null"

False. For reference components, `var` in a record pattern can bind a `null` value. You must check for null before calling methods on that variable. Meanwhile, **a `null` selector value does not match a record pattern**; these are two different situations.

### 11.7. "Optimizing getters always makes code faster"

Not necessarily. Significant cost may lie in object allocation, network operations, queries, locks, or algorithms. Profile to see which parts are actually hot, and optimize only what makes an impact.

## 12. Exercises and self-check questions

Given the record:

```java
record Report(String id, int score, String note) {}
```

**Question 1.** If you only need `id` and the pattern has three components, should you choose:

```java
if (input instanceof Report(var id, var score, var note)) {
    System.out.println(id);
}
```

or:

```java
if (input instanceof Report report) {
    System.out.println(report.id());
}
```

**Answer:** Both can be valid. If you only use `id` and the other accessors have significant cost, a type pattern can make the amount of work easier to control. If the record is simple and the record pattern communicates intent well, the performance difference may be negligible; measure on real data.

**Question 2.** Given:

```java
case Report(var id, var score, var note) when score >= 80 -> "PASS";
case Report(var id, var score, var note) -> "RETRY";
```

what will an input with `score = 79` go through?

**Answer:** The first pattern can match and then the guard fails; Java proceeds to evaluate the second pattern. The accessors needed for each deconstruction may be called repeatedly. If an accessor does expensive work, consider a single type pattern and reading the component once inside a block.

**Question 3.** If an explicit accessor `score()` throws `IllegalStateException` while a record pattern is matching, will `default` receive that input?

**Answer:** No. An accessor error causes pattern matching to complete abruptly; in Java 21, `MatchException` is thrown with `cause` set to the original error. This is not a "pattern did not match" outcome.

**Question 4.** A single `System.nanoTime()` measurement shows a record pattern is 20% slower than a type pattern. Is that enough to rewrite the entire codebase?

**Answer:** Not yet. You must control for JIT warm-up, rule out dead-code elimination, use an equivalent workload, take multiple measurements, and assess practical significance. JMH and a profiler are better suited for performance decisions.

## 13. Summary and background references

**Remember:** A record pattern is syntax for checking a type and **deconstructing a record through its accessors**, not a zero-cost field read. Default accessors are usually tiny and can be optimized by the JVM. Cost matters when **custom accessors are expensive**, **patterns repeat after false guards**, **multiple levels of records are nested**, or **exceptions/side effects** alter behavior. Keep code readable, read data once when there is a concrete reason, and **measure with a benchmark/profiler** before optimizing.

Official references for semantics:

- **Java Language Specification 21, `14.30.2 – Pattern Matching:`** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.2
- **JEP 440 – Record Patterns (Java 21):** https://openjdk.org/jeps/440
- **Oracle Java – Record Patterns:** https://docs.oracle.com/en/java/javase/21/language/record-patterns.html

This article uses record patterns and pattern matching for `switch` syntax that became standard in **Java 21**; the main program examples target JDK 21 or later and do not require preview mode.
