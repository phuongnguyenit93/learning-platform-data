# Building and Testing Reusable Transformation Pipelines in Java

## 1. The problem: from scattered steps to a single pipeline

In functional programming, a **transformation pipeline** is a chain of small functions, each accepting an input and returning a result. The output of the previous step is fed into the next step. Instead of repeating normalization, validation, and representation operations in multiple places, we combine them into a unit that can be reused and tested independently.

Suppose an application receives names or labels from users. Business requirements:

1. Strip whitespace from both ends.
2. Collapse internal whitespace runs into a single space.
3. Convert to lowercase using a rule independent of the machine's locale.
4. Accept only non-empty text consisting of ASCII letters `a-z` and spaces.
5. When valid, produce a label of the form `{content}`; `null`, empty, or rule-violating data must be rejected.
6. The same pipeline is used to process a single value or a list, with tests proving the behavior.

Conceptual flow:

```text
Input value
      │
      ▼
Strip leading/trailing whitespace (strip)
      │
      ▼
Collapse whitespace (collapse)
      │
      ▼
Lowercase (lowercase)
      │
      ▼
Validate (nonBlank AND allowedCharacters)
      ├── Invalid ─────────> No result
      │
      └── Valid ───────────> Format "{...}" ──> Result
```

Each transformation step does only one thing; the validity condition is separated from data-modifying operations. The example applied in this lesson is an **illustrative rule**; for real user names, the list of accepted characters must reflect internationalization requirements, Vietnamese diacritics, and Unicode.

## 2. Key components to understand

### `Function<T, R>` and composability

`java.util.function.Function<T, R>` has the abstract method `R apply(T value)`. A `Function<String, String>` fits an operation that takes a string and creates a new string, such as `String::strip`.

Two default methods create a new function from existing functions:

```java
Function<A, B> first = ...;
Function<B, C> second = ...;

Function<A, C> pipeline = first.andThen(second);
```

Interpretation: `pipeline.apply(a)` is equivalent to `second.apply(first.apply(a))`. `andThen` reads from left to right in execution order.

With `compose`, the order is reversed:

```java
Function<B, C> second = ...;
Function<A, B> first = ...;

Function<A, C> pipeline = second.compose(first);
```

`second.compose(first).apply(a)` also equals `second.apply(first.apply(a))`: the function passed into `compose` runs **before** the function on the left.

An example where wrong order is easy to spot:

```java
Function<Integer, Integer> addTwo = n -> n + 2;
Function<Integer, Integer> timesThree = n -> n * 3;

int leftToRight = addTwo.andThen(timesThree).apply(4); // (4 + 2) * 3 = 18
int rightToLeft = addTwo.compose(timesThree).apply(4); // (4 * 3) + 2 = 14
```

The two pipelines are not equivalent. Swapping steps is only safe when there is a business reason or an appropriate proof; many transformations are not commutative.

### `UnaryOperator<T>` and `Function.identity()`

When the input and output types are equal, `UnaryOperator<T>` is a specialization of `Function<T, T>`. Steps of the same type can be declared like:

```java
UnaryOperator<String> trim = String::strip;
UnaryOperator<String> lowercase =
        s -> s.toLowerCase(java.util.Locale.ROOT);
```

Even so, the result of `andThen` is declared in terms of `Function`, so do not assume that every composition of two `UnaryOperator<String>` instances returns a variable of type `UnaryOperator<String>`.

`Function.identity()` creates a function that preserves its input and is useful as a default value for a transformation chain:

```java
Function<String, String> unchanged = Function.identity();
System.out.println(unchanged.apply("Java")); // Java
```

### `Predicate<T>` for composing conditions

`Predicate<T>` has `boolean test(T value)` and composition operations:

- `p.and(q)` checks `p` first; if `p` returns `false`, `q` is not called.
- `p.or(q)` checks `p` first; if `p` returns `true`, `q` is not called.
- `p.negate()` inverts the result of `p`.
- `Predicate.not(p)` creates a negated predicate, often readable with method references.

```java
Predicate<String> nonBlank = Predicate.not(String::isBlank);
Predicate<String> onlyAsciiLettersAndSpaces =
        s -> s.matches("[a-z ]+");

Predicate<String> accepted = nonBlank.and(onlyAsciiLettersAndSpaces);
```

The `accepted` condition should be called **after** normalization because the normalization step converts uppercase letters to lowercase and trims whitespace. If checked before, the same data could yield a different result. `Predicate.and`/`or` short-circuit like the corresponding logical operators; predicates with side effects can make behavior hard to understand.

### `Optional<T>` for representing presence/absence of a result

`Optional.ofNullable(input)` creates `Optional.empty()` if `input == null`, thereby avoiding calling `String` methods on `null`.

They can be chained:

```java
Optional.ofNullable(raw)
        .map(normalize)
        .filter(accepted)
        .map(format);
```

- `map(normalize)` transforms if a value is present.
- `filter(accepted)` keeps the value when valid; when false, returns empty.
- `map(format)` formats only after passing validation.

`Optional` is a way to represent an operation that may produce no result in this case. If the business needs to report a specific failure **reason** (e.g., empty, forbidden characters, too long), you need a result type carrying error info or separate validation; `Optional.empty()` does not store the cause.

## 3. Designing a reusable pipeline

To keep a pipeline clear, define the **contract** of each step:

| Component | Type | Responsibility | Example |
| --- | --- | --- | --- |
| `STRIP` | `Function<String, String>` | Strip leading/trailing whitespace | `" Java "` → `"Java"` |
| `COLLAPSE_SPACES` | `Function<String, String>` | Collapse whitespace matching regex | `"Java   API"` → `"Java API"` |
| `LOWER` | `Function<String, String>` | Convert to lowercase using `Locale.ROOT` | `"Java"` → `"java"` |
| `NORMALIZE` | `Function<String, String>` | Compose the three steps in order | `" JAVA   API "` → `"java api"` |
| `VALID` | `Predicate<String>` | Decide whether normalized text is valid | `"java api"` → `true` |
| `PROCESS` | `Function<String, Optional<String>>` | Check `null`, normalize, filter, format | `" JAVA "` → `Optional[{java}]` |

Some design principles:

- **One step, one responsibility:** changing the space-collapsing rule does not force rewriting the validation step.
- **Explicit input/output types:** transformation steps are composed with `Function.andThen` when the previous step's result type is compatible with the next step's input type.
- **No shared mutable state:** each function computes its result from its argument; avoid shared counters or `StringBuilder` inside lambdas.
- **Do not mutate inputs:** `String` is immutable, so the example returns new values. For mutable objects, clearly state the policy for copying or in-place mutation.
- **Explicit error rules:** `null` inputs and invalid data return `Optional.empty()`; programming errors or system errors should not be caught broadly and silently turned into empty.
- **Reusable across contexts:** a shared `PROCESS` keeps single-item and batch processing consistent; direct unit tests on each function are still needed to isolate bugs.

## 4. Complete Java 17+ example

Create `ReusablePipelineDemo.java` with the following content. This is a standalone program using only the Java Standard Library; `verify()` acts as a minimal automated test suite, running without JUnit or enabling the `-ea` flag.

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Optional;
import java.util.function.Function;
import java.util.function.Predicate;

public final class ReusablePipelineDemo {
    private static final Function<String, String> STRIP = String::strip;

    private static final Function<String, String> COLLAPSE_SPACES =
            s -> s.replaceAll("\\s+", " ");

    private static final Function<String, String> LOWER =
            s -> s.toLowerCase(Locale.ROOT);

    private static final Function<String, String> NORMALIZE =
            STRIP.andThen(COLLAPSE_SPACES).andThen(LOWER);

    private static final Predicate<String> VALID =
            Predicate.not(String::isBlank)
                    .and(s -> s.matches("[a-z ]+"));

    private static final Function<String, Optional<String>> PROCESS =
            raw -> Optional.ofNullable(raw)
                    .map(NORMALIZE)
                    .filter(VALID)
                    .map(s -> "{" + s + "}");

    private static final Function<Integer, Integer> ADD_TWO =
            n -> n + 2;

    private static final Function<Integer, Integer> TIMES_THREE =
            n -> n * 3;

    private ReusablePipelineDemo() {
    }

    private static List<String> processBatch(List<String> values) {
        return values.stream()
                .map(PROCESS)
                .flatMap(Optional::stream)
                .toList();
    }

    private static void expect(
            Object expected, Object actual, String caseName) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    caseName + ": expected=" + expected + ", actual=" + actual);
        }
    }

    private static void verify() {
        expect("java lambda", NORMALIZE.apply("  JAVA   LAMBDA "),
                "normalize whitespace and case");
        expect("api", NORMALIZE.apply("\tAPI  "),
                "normalize tab and surrounding spaces");

        Function<String, String> sameSequence =
                LOWER.compose(COLLAPSE_SPACES).compose(STRIP);
        expect(NORMALIZE.apply(" JAVA   API "),
                sameSequence.apply(" JAVA   API "), "compose equivalence");

        expect(Optional.of("{java lambda}"),
                PROCESS.apply(" JAVA  Lambda "), "valid input");
        expect(Optional.empty(), PROCESS.apply(" \t "), "blank input");
        expect(Optional.empty(), PROCESS.apply(" Java17 "), "invalid characters");
        expect(Optional.empty(), PROCESS.apply(null), "null input");

        expect(List.of("{java lambda}", "{new api}"),
                processBatch(List.of(
                        "  JAVA   LAMBDA ", "  ", " New   API ", "Java17")),
                "batch reuse");

        expect(18, ADD_TWO.andThen(TIMES_THREE).apply(4),
                "andThen order");
        expect(14, ADD_TWO.compose(TIMES_THREE).apply(4),
                "compose order");

        System.out.println("tests=PASS");
    }

    public static void main(String[] args) {
        verify();

        System.out.println(
                "andThen=" + ADD_TWO.andThen(TIMES_THREE).apply(4));
        System.out.println(
                "compose=" + ADD_TWO.compose(TIMES_THREE).apply(4));
        System.out.println(
                "one=" + PROCESS.apply("  JAVA   LAMBDA ").orElse("<invalid>"));
        System.out.println(
                "blank=" + PROCESS.apply(" \t ").orElse("<invalid>"));
        System.out.println(
                "batch=" + processBatch(List.of(
                        "  JAVA   LAMBDA ", "  ", " New   API ", "Java17")));
    }
}
```

Compile and run (JDK 17 or newer):

```bash
javac ReusablePipelineDemo.java
java ReusablePipelineDemo
```

Exact stdout when tests succeed:

```text
tests=PASS
andThen=18
compose=14
one={java lambda}
blank=<invalid>
batch=[{java lambda}, {new api}]
```

If a test fails, `expect` throws `AssertionError` with the test case name and both values for comparison; the program stops before printing `tests=PASS`. Using such an explicit check method is more reliable than Java's `assert` statement when you are unsure whether the runner has `-ea` enabled.

### Why does the example handle `null`?

`PROCESS` starts with `Optional.ofNullable(raw)`. When `raw` is `null`, the result is empty and `NORMALIZE`, `VALID`, and formatting do not run. However, calling `NORMALIZE.apply(null)` directly still throws `NullPointerException`; the `null`-handling contract belongs to the **overall pipeline**, not every component function.

### Why does batch processing not duplicate logic?

`processBatch` reuses `PROCESS` for each element. `Optional::stream` yields 0 elements if empty and 1 element if present, so `flatMap(Optional::stream)` filters out rejected values. `Stream.toList()` returns a list that does not allow structural modification; in Java 17 this result is suitable if the purpose is read-only.

`List.of(...)` does not accept `null` elements. If an actual input list may contain `null`, choose a data source that permits `null` (such as `Arrays.asList(...)`) and still pass each element through `PROCESS`. `PROCESS` will filter out `null` values as verified in the separate test.

## 5. Testing the pipeline layer by layer

A good test must verify **observable behavior** and **boundary contracts**, not merely call a function and print output. There are three important levels.

### Testing each transformation

Test normal inputs and tricky variants:

| Case | Input | Expected after `NORMALIZE` |
| --- | --- | --- |
| Whitespace and uppercase | `"  JAVA   LAMBDA "` | `"java lambda"` |
| Leading/trailing tab | `"\tAPI  "` | `"api"` |
| Empty string | `""` | `""` |
| Only whitespace | `"   "` | `""` |
| Already normalized | `"java api"` | `"java api"` |

The **order** of steps must be tested. `STRIP.andThen(COLLAPSE_SPACES).andThen(LOWER)` and `LOWER.compose(COLLAPSE_SPACES).compose(STRIP)` must produce the same result on the same data. When two different ways of writing it produce different results, there may be an ordering bug or a bug in one step.

### Testing validity conditions and overall output

| Input to `PROCESS` | Result |
| --- | --- |
| `" JAVA  Lambda "` | `Optional.of("{java lambda}")` |
| `" \t "` | `Optional.empty()` |
| `" Java17 "` | `Optional.empty()` |
| `null` | `Optional.empty()` |
| `"a b"` | `Optional.of("{a b}")` |
| `"..."` | `Optional.empty()` |

Also test cases rejected after normalization. For example `Java17` becomes `java17`, but the regex `"[a-z ]+"` does not accept digits so it must return empty.

For multi-step pipelines, edge cases matter more than dozens of identical cases: empty data, null, invalid characters, various whitespace types, already-normalized data, large lengths (if there is a business limit), and Unicode cases when the product supports internationalization.

### Testing reusability

A reusable pipeline must give consistent results when:

- Called multiple times with the same input.
- Used directly on a single value and indirectly in a `Stream`.
- Used on different elements without "leaking" state from a previous call to the next call.
- Executing steps in the published order.

In the example, `PROCESS` is a stateless function. `Function` and `Predicate` are interfaces and do not guarantee purity by themselves; consistency comes from how we implement the lambdas.

## 6. Worthwhile pipeline properties to test

Beyond comparing a few concrete outputs, you can define **invariants** according to business requirements.

**Idempotence of normalization:**

```java
String once = NORMALIZE.apply("  JAVA   API ");
String twice = NORMALIZE.apply(once);
expect(once, twice, "normalization is idempotent");
```

With the three transformations chosen in this lesson, normalizing an already-normalized value does not change it. This must be re-verified when adding new steps, such as character replacement or adding a prefix, because not every pipeline is idempotent.

**Valid results satisfy the condition:**

```java
String normalized = NORMALIZE.apply(" JAVA   API ");
if (!VALID.test(normalized)) {
    throw new AssertionError("normalized sample should be valid");
}
```

When `PROCESS` returns a value, it means `VALID` returned `true` on the normalized string before adding `{...}`. Do not apply `VALID` to the **post-formatting** label, because `{}` characters are not accepted by the regex.

**Original input is not mutated:**

```java
String raw = " JAVA ";
String transformed = NORMALIZE.apply(raw);
expect(" JAVA ", raw, "input remains unchanged");
expect("java", transformed, "new value");
```

This is a natural property of immutable `String`. If a pipeline processes mutable DTOs or modifiable collections, explicitly test which steps copy and which steps may mutate state.

## 7. Common pitfalls

### Wrong order of `compose` and `andThen`

`f.andThen(g)` means `g(f(x))`; whereas `f.compose(g)` means `f(g(x))`. When steps are non-commutative, mixing them up changes the result. A self-check method is writing the nested expression or testing with operations that give clearly distinct results, such as add 2 and multiply by 3.

### Composing incompatible types

A `Function<String, Integer>` step cannot be chained directly into a `Function<String, String>` step via `andThen`, because the second step demands a `String` input while the first step produces `Integer`. Design compatible output/input types or add a meaningful type-conversion step.

### Validating data at the wrong time

If the regex `[a-z ]+` is checked before converting to lowercase, `"JAVA"` is rejected. The order normalize → validate must be reflected in the pipeline structure and proven with tests.

### Not defining a `null` and error policy

`String::strip`, `String::isBlank`, and `String::length` all require a non-`null` receiver. `Optional.ofNullable` protects the current path; directly called steps may still throw errors. Do not `catch (Exception)` and treat every failure as "invalid data", as that hides programming or infrastructure bugs.

### Using lambdas with side effects

The following example is unsuitable as a reusable transformation step across multiple threads:

```java
// Illustration of problematic code: uses external state.
int[] counter = {0};
Function<String, String> withCounter = s -> {
    counter[0]++;
    return counter[0] + ":" + s;
};
```

The same string produces different results across calls, and there is a risk of race conditions when run in parallel. It is better to separate sequence numbers from normalization rules, pass context explicitly, or keep stateful steps in the orchestration layer.

### Using text rules unsuitable for real data

`strip()` uses `Character.isWhitespace` whitespace criteria; `replaceAll("\\s+", " ")` uses Java regex's `\s` class with default behavior; the two criteria are not uniform across all of Unicode. The regex `[a-z ]+` also only accepts lowercase ASCII letters and spaces. The example is intentionally limited this way for easy testing, **not as a multilingual personal-name normalizer**.

If the product needs to support Vietnamese diacritics, Unicode, and other business rules, redesign the acceptance condition, whitespace handling, and test suite; do not just swap the regex while keeping old assumptions.

### Premature optimization and inappropriate Stream usage

`String.matches` compiles the regular expression on every call; if the record count is large, consider `Pattern.compile(...)` once and using `pattern.matcher(s).matches()`, after profiling. For business steps with I/O or checked exceptions, a simple pure `Function` may not suffice: you need an error policy and an appropriate functional interface. Only use Streams when they make flow clearer; ordinary loops remain the right choice in situations needing fine-grained control or detailed error reporting.

## 8. Extending toward configuration and maintainable tests

As a pipeline grows, you can encapsulate steps in a service class or factory receiving `Function` and `Predicate` via constructor. That way, tests can swap out individual normalization, validation, or formatting rules without duplicating the entire pipeline.

Standalone composed function example:

```java
static <T, U> Function<T, Optional<U>> validatedTransform(
        Function<T, U> transform,
        Predicate<? super U> valid) {
    return input -> Optional.ofNullable(input)
            .map(transform)
            .filter(valid);
}
```

This snippet is an **illustrative method**, placed inside a Java class importing `Function`, `Predicate`, `Optional`; it is not a standalone source file. `Function<T, U>` allows the output type to differ from the input type; the predicate is tested on the `U` value. The `null` policy still relies on `Optional` and `Optional.map`: if input is null or transform returns null, the result is empty. If you need to distinguish those two cases, replace `Optional` with a return structure carrying a reason.

Function composition tests should focus on contracts and error cases, rather than inspecting internal details of every lambda. For example, with a configurable factory, tests prove: transform is called once on valid data, predicate receives the transformed output, null input does not trigger transform, and rejected values do not reach the formatting step.

## 9. Self-practice exercises

1. Add a normalized length limit using `Predicate<String> withinLimit = s -> s.length() <= 20;`, then compose `VALID.and(withinLimit)`. Write tests for exact lengths of 20 and 21 characters.
2. Replace `{...}` with an identifier `"id:" + normalized`, then ensure both single-item processing and `processBatch` use the new format without duplicating logic.
3. Write a loop test calling `PROCESS` with the same input 100 times and assert the result is always identical.
4. Try Vietnamese text with diacritics, such as `"  Tiếng Việt  "`; predict why the current rule rejects it. Then design a realistic valid-character rule and add corresponding Unicode test cases.
5. Explain using nested expressions why `ADD_TWO.andThen(TIMES_THREE)` gives 18, while `ADD_TWO.compose(TIMES_THREE)` gives 14 for input 4.

When doing the exercises, explicitly state what each step takes, what it returns, whether it handles `null`, which step it runs before/after, and which condition is tested. A truly reusable pipeline is one with a **clear contract, exact order, consistent error policy, and a test suite that catches behavioral changes**.
