# Choosing a Loop When a Transformation Has Too Many Hard-to-Read Branches

## 1. Goal: Clarifying the Data Processing Flow

In Java, `Stream` is well suited for expressing clear transformations and aggregations such as `filter` → `map` → `toList`. However, when an element must pass through **multiple conditional branches, multiple rejection rules, skip points, and contextual error reporting**, cramming all the logic into a chain of lambdas can make the code hard to read and hard to test.

In those cases, a `for`/`for-each` loop with `if`, `switch`, `continue`, and clearly named operations often helps the reader see **which lines proceed, which lines are skipped, and why**. This is a choice about expressiveness, not a rule that "loops are always better than Streams."

Lesson objectives:

1. Recognize when pipelines with many `map`/`filter` calls and nested lambdas obscure the logic.
2. Convert to a loop with clear branches while preserving behavior.
3. Design `Accepted`, `Rejected`, and `Skipped` results to avoid silently dropping invalid data.
4. Maintain testability without creating hard-to-control side effects.
5. Know when to keep a Stream by extracting multi-branch logic into a separate function.

## 2. Streams Read Well When Steps Are Simple and Consistent

The following example represents a linear transformation:

```java
List<String> cleaned = names.stream()
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .map(String::toUpperCase)
        .toList();
```

Assuming `names` is a `List<String>` containing no `null` values, we read sequentially: strip whitespace, remove empty strings, convert to uppercase, and collect the result. Each line has a single responsibility, and the processing chain requires no extra control flow.

But another requirement might include:

- If a line is `null` or empty, skip it and record the reason.
- If it is a comment starting with `#`, skip it.
- If the data does not have enough fields, mark it as rejected.
- If the channel code is unsupported, mark it as rejected.
- If the quantity is not an integer, return a data error with its position.
- If the quantity is out of bounds, reject it.
- If valid, transform by channel and add a special label for bulk orders.

Putting all this logic into a single lambda inside `map` would create multiple `if` branches, temporary values, exception handling, and results of different kinds. At that point, Stream syntax no longer makes the logic simpler.

## 3. Signs to Consider a Loop

| Sign | Drawback when forcing a long lambda | How a loop helps |
| --- | --- | --- |
| Many branching conditions | `map` with nested `if`s / ternary operators | Shows branch transition points directly |
| Multiple `skip` cases | Easy to return `null` then `filter(nonNull)` | Uses `continue`, while also recording `Skipped` if the business logic needs it |
| Multiple errors needing distinct reasons | A single `Optional.empty()` easily loses the cause | Returns an explicit `Rejected(line, reason)` result |
| Need for named temporary variables | Long or nested lambdas | Declares intermediate values right next to where they are used |
| Important order of validation steps | Hard to see which error is caught first | `if` guards ordered according to business rules |
| Need to `break` on a condition | Multiple terminal operations and state flags | `break` clearly states where the loop stops |
| Need to update multiple result types | Side effects or complex collectors | Collects results in a purposeful structure |

These are **signs to consider**, not a standard measured by the number of `if` statements or line length. A pipeline can still be readable if complex branching logic is extracted into a clearly named method. Conversely, a loop can also be very hard to read if it has too many shared variables and deeply nested conditions.

## 4. Example of a Transformation Step With Too Many Branches

Suppose the input data follows a simple format:

```text
CHANNEL,PRODUCT_NAME,QUANTITY
```

Supported channels: `WEB`, `STORE`, `APP`. Illustrative rules:

- `null` strings, blank lines, and `#...` comments: `Skipped` with a reason.
- A business line must have exactly three comma-separated fields.
- Product name must not be empty and must consist only of ASCII Latin letters after uppercase normalization.
- Channel must be one of the three values above.
- Quantity must be an integer in the range `1..10`.
- Channel `WEB` is written as `ONLINE`, `STORE` stays the same, `APP` becomes `MOBILE`.
- Quantities of `5` or more get the suffix ` [BULK]`.
- Each input line produces exactly one `Outcome`: accepted, rejected, or skipped according to the rules.

If we try to force everything into `Stream<String>` and return `null` on bad data, such as:

```java
// Design anti-pattern: simulates silently dropping errors.
// Requires List<String> rows and java.util.* imports.
List<String> labels = rows.stream()
        .map(raw -> {
            if (raw == null || raw.isBlank()) {
                return null;
            }
            String[] fields = raw.split(",");
            if (fields.length != 3) {
                return null;
            }
            try {
                int quantity = Integer.parseInt(fields[2].strip());
                return fields[1].strip() + " x" + quantity;
            } catch (NumberFormatException ignored) {
                return null;
            }
        })
        .filter(java.util.Objects::nonNull)
        .toList();
```

The snippet above **does not fully implement the business rules** and is an example of what to avoid, not a solution. It loses the position, the rejection reason, and several validation conditions. Adding all the remaining branches into the same lambda would make it even harder to understand. When no errors appear in the output, you cannot tell whether there truly were no errors or whether errors were silently discarded.

We will use a loop with explicit outcomes so that every branch can be verified.

## 5. Categorizing the Output Before Writing the Loop

Instead of returning `String` or `null`, use a result type with three variants:

```text
Line i
    │
    ├── null/empty/comment ──────────────> Skipped(i, reason)
    │
    ├── invalid structure/channel/quantity ─> Rejected(i, reason)
    │
    └── valid ───────────────────────────> Accepted(i, label)
```

In Java 17, `sealed interface` and `record` describe the contract concisely:

```java
sealed interface Outcome permits Accepted, Rejected, Skipped {}

record Accepted(int line, String label) implements Outcome {}
record Rejected(int line, String reason) implements Outcome {}
record Skipped(int line, String reason) implements Outcome {}
```

This is an **illustrative declaration snippet**, placed in full inside the program's class in the next section. The `record` types automatically provide accessors, `equals`, `hashCode`, and `toString` based on their components; as a result, tests can compare outcomes without writing much boilerplate code.

You do not always need three variants: if empty data is an error, return `Rejected` instead of `Skipped`. What matters is that the business contract distinguishes between "skipped by rule" and "failed."

## 6. Complete Java 17 Program: Multi-Branch Loop Kept Clear

Create the file `BranchingTransformationDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class BranchingTransformationDemo {
    sealed interface Outcome permits Accepted, Rejected, Skipped {}

    record Accepted(int line, String label) implements Outcome {}
    record Rejected(int line, String reason) implements Outcome {}
    record Skipped(int line, String reason) implements Outcome {}

    static List<String> sampleRows() {
        // Arrays.asList allows null elements to test missing data.
        return Arrays.asList(
                "# daily export",
                " WEB,alpha,3 ",
                "STORE,beta,0",
                "APP,gamma,5",
                "OTHER,delta,2",
                "WEB,epsilon,not-a-number",
                "WEB,zeta,12",
                null,
                "STORE,eta,1",
                "WEB,,2",
                "");
    }

    static List<Outcome> transform(List<String> rows) {
        Objects.requireNonNull(rows, "rows");
        List<Outcome> outcomes = new ArrayList<>();

        for (int index = 0; index < rows.size(); index++) {
            int line = index + 1;
            String raw = rows.get(index);

            // Guard 1: cases allowed to be skipped.
            if (raw == null) {
                outcomes.add(new Skipped(line, "missing line"));
                continue;
            }

            String trimmed = raw.strip();
            if (trimmed.isEmpty()) {
                outcomes.add(new Skipped(line, "blank"));
                continue;
            }

            if (trimmed.startsWith("#")) {
                outcomes.add(new Skipped(line, "comment"));
                continue;
            }

            // Guard 2: validate input field structure.
            String[] fields = trimmed.split(",", -1);
            if (fields.length != 3) {
                outcomes.add(new Rejected(line, "expected 3 fields"));
                continue;
            }

            String channel = fields[0].strip()
                    .toUpperCase(Locale.ROOT);
            String product = fields[1].strip()
                    .toUpperCase(Locale.ROOT);
            String quantityText = fields[2].strip();

            if (product.isEmpty()) {
                outcomes.add(new Rejected(line, "missing product"));
                continue;
            }
            if (!product.matches("[A-Z]+")) {
                outcomes.add(new Rejected(line, "invalid product"));
                continue;
            }

            // Guard 3: determine display label by channel.
            String channelLabel;
            if (channel.equals("WEB")) {
                channelLabel = "ONLINE";
            } else if (channel.equals("STORE")) {
                channelLabel = "STORE";
            } else if (channel.equals("APP")) {
                channelLabel = "MOBILE";
            } else {
                outcomes.add(new Rejected(line, "unsupported channel"));
                continue;
            }

            // Guard 4: catch only the expected parse exception.
            int quantity;
            try {
                quantity = Integer.parseInt(quantityText);
            } catch (NumberFormatException cause) {
                outcomes.add(new Rejected(line, "invalid quantity"));
                continue;
            }

            if (quantity < 1 || quantity > 10) {
                outcomes.add(new Rejected(line, "quantity out of range"));
                continue;
            }

            // Success branch at the end, without deep nesting.
            String suffix = quantity >= 5 ? " [BULK]" : "";
            String label = channelLabel + ":" + product
                    + " x" + quantity + suffix;
            outcomes.add(new Accepted(line, label));
        }

        return List.copyOf(outcomes);
    }

    static void check(Object expected, Object actual, String description) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    description + ": expected=" + expected
                            + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<Outcome> actual = transform(sampleRows());
        List<Outcome> expected = List.of(
                new Skipped(1, "comment"),
                new Accepted(2, "ONLINE:ALPHA x3"),
                new Rejected(3, "quantity out of range"),
                new Accepted(4, "MOBILE:GAMMA x5 [BULK]"),
                new Rejected(5, "unsupported channel"),
                new Rejected(6, "invalid quantity"),
                new Rejected(7, "quantity out of range"),
                new Skipped(8, "missing line"),
                new Accepted(9, "STORE:ETA x1"),
                new Rejected(10, "missing product"),
                new Skipped(11, "blank"));

        check(expected, actual, "all outcomes and positions");
        check(sampleRows().size(), actual.size(), "one result per input");

        long accepted = actual.stream()
                .filter(Accepted.class::isInstance).count();
        long rejected = actual.stream()
                .filter(Rejected.class::isInstance).count();
        long skipped = actual.stream()
                .filter(Skipped.class::isInstance).count();

        check(3L, accepted, "accepted count");
        check(5L, rejected, "rejected count");
        check(3L, skipped, "skipped count");

        check(List.of(), transform(List.of()), "empty input");
        check(List.of(new Rejected(1, "expected 3 fields")),
                transform(List.of("WEB,alpha")), "missing field");
        check(List.of(new Rejected(1, "invalid product")),
                transform(List.of("WEB,alpha-1,2")), "product rule");
        check(actual, transform(sampleRows()), "repeatable result");
    }

    public static void main(String[] args) {
        runTests();
        System.out.println("tests=PASS");

        List<Outcome> outcomes = transform(sampleRows());
        for (Outcome outcome : outcomes) {
            if (outcome instanceof Accepted accepted) {
                System.out.println("OK " + accepted.line()
                        + ": " + accepted.label());
            } else if (outcome instanceof Rejected rejected) {
                System.out.println("ERROR " + rejected.line()
                        + ": " + rejected.reason());
            } else if (outcome instanceof Skipped skipped) {
                System.out.println("SKIP " + skipped.line()
                        + ": " + skipped.reason());
            }
        }

        long accepted = outcomes.stream()
                .filter(Accepted.class::isInstance).count();
        long rejected = outcomes.stream()
                .filter(Rejected.class::isInstance).count();
        long skipped = outcomes.stream()
                .filter(Skipped.class::isInstance).count();
        System.out.println("accepted=" + accepted
                + " rejected=" + rejected
                + " skipped=" + skipped);
    }
}
```

Compile and run with JDK 17 or newer:

```bash
javac BranchingTransformationDemo.java
java BranchingTransformationDemo
```

Expected stdout:

```text
tests=PASS
SKIP 1: comment
OK 2: ONLINE:ALPHA x3
ERROR 3: quantity out of range
OK 4: MOBILE:GAMMA x5 [BULK]
ERROR 5: unsupported channel
ERROR 6: invalid quantity
ERROR 7: quantity out of range
SKIP 8: missing line
OK 9: STORE:ETA x1
ERROR 10: missing product
SKIP 11: blank
accepted=3 rejected=5 skipped=3
```

In the example, `runTests()` throws an `AssertionError` if any result differs from the expectation; it does not require the `-ea` JVM flag. If the program prints `tests=PASS`, all assertions have passed.

### Why Does a Loop Make This Example Clearer?

Each `if` at the top of the loop is a **guard**: when the condition holds, it adds an outcome and `continue`s to the next line. Therefore, the success branch is not deeply nested inside `else` blocks.

The line `line = index + 1` preserves the original position for traceability, even when a line is skipped. `split(",", -1)` preserves trailing empty fields; default `split(",")` drops trailing empty strings, making missing fields harder to distinguish. `Locale.ROOT` avoids machine-locale dependency when converting to uppercase.

The `try/catch` wraps **only** `Integer.parseInt`: a conversion failure is an expected data error, represented as `Rejected`. Do not catch a broad `Exception` that could hide programming or system errors. The success path runs only after all conditions have passed.

`List.copyOf(outcomes)` creates an unmodifiable result list, which is convenient for the return contract. All list elements are `record`s containing `int` and `String`, so there is no mutable internal state in this example. The input is not modified.

The Stream calls at the end to count `Accepted`, `Rejected`, and `Skipped` are **very readable**, because each operation has only a single predicate. You can use a loop for the branching step and Streams for the aggregation step; you do not have to pick a single style for the entire program.

## 7. Do Not Use `continue` to Lose Error Data

There are two different ways to use `continue`:

```java
// Questionable if the contract requires error reporting:
if (invalid) {
    continue;
}

// Explicit about the reason:
if (invalid) {
    outcomes.add(new Rejected(line, "invalid input"));
    continue;
}
```

The two snippets above are illustrative code assuming `invalid`, `outcomes`, and `line` are already declared in the enclosing context. In the first snippet, the input is not recorded in the output list. This is only valid if the contract **allows complete omission** and needs no traceability. In the second snippet, every line still has a corresponding outcome.

Do not confuse three concepts:

- `continue` skips the rest of the **current iteration** and moves to the next iteration.
- `break` exits the nearest enclosing loop; use it when the requirement is genuinely to stop processing.
- `return` exits the enclosing method; placing it inside a loop can cause the entire batch to stop early.

Inside a Stream lambda, `return` only returns a value from the **lambda body**, not a `continue` of an outer loop or a `return` from the enclosing method. Mixing up these semantics is a common source of bugs when mechanically translating a complex loop into `map`/`forEach`.

## 8. When Can You Keep a Stream by Extracting a Function?

Having multiple branches does not necessarily make a Stream unreadable. An alternative is to move the rules for **a single element** into a `transformOne(line, raw)` method whose contract returns `Outcome`:

```java
// Structural illustration: transformOne must be implemented
// with the exact business rules described in section 6.
List<Outcome> outcomes = java.util.stream.IntStream
        .range(0, rows.size())
        .mapToObj(i -> transformOne(i + 1, rows.get(i)))
        .toList();
```

Here `rows` is a `List<String>`, and `transformOne(int, String)` is an application-defined method returning `Outcome`. This snippet illustrates the design, not a standalone file. The Stream becomes concise: it simply iterates over positions and maps each line to an outcome. The multi-branch logic lives in a named function that can be tested independently.

If the pipeline's behavior is essentially mapping each element independently, this approach is often good. If the task needs to **stop entirely upon meeting a condition**, has multiple state update points during traversal, or depends on loop control flow, `for` may still be more direct.

A useful technique is extracting small steps such as `parseFields`, `validateQuantity`, and `formatLabel`. Do not create dozens of functions just to avoid a simple `if` statement; extract when each function has clear business meaning and can be tested independently.

## 9. Preserving Semantics When Switching From a Stream to a Loop

When refactoring, check the following important differences.

| Aspect | Questions to check |
| --- | --- |
| Element order | Did the old pipeline have an encounter order? Did it use `sorted`, `unordered`, or a parallel Stream? |
| Data filtering | Which elements were dropped? Do `Skipped`/`Rejected` traces need to be kept? |
| `null` values | Did the old Stream accept, drop, or throw on them? The loop must preserve the chosen policy |
| Error handling | Should exceptions propagate or become contextual data errors? |
| Result | `Stream.toList()` produces an unmodifiable List; a loop returns a mutable `ArrayList` by default unless wrapped |
| Short-circuiting | Were there `findFirst`, `anyMatch`, `limit`, or `takeWhile` equivalents to `break`? |
| Laziness | Intermediate Stream operations might not execute yet; a loop runs immediately when called |
| Side effects | Was there file/DB writing or logging inside lambdas? Are ordering and retries well-defined? |
| Performance | Do we need to build a result collection? Can we process line by line without holding all data? |

With `Stream.toList()` (Java 16+), the result is unmodifiable. When replacing it with `ArrayList`, if you need to maintain the unmodifiable contract, return `List.copyOf(...)` or an appropriate structure. `List.copyOf(...)` does not allow null elements; check the data contract before using it.

### Do Not Assume Loops Are Always Faster

Speed differences also depend on data types, boxing, allocation, JIT optimizations, I/O operations, and the cost of the transformation itself. In a pipeline with heavy regex, parsing, and validation, runtime may be dominated by those operations rather than the loop syntax. Prioritize correct and understandable code; if performance is a specific requirement, measure with a suitable benchmark (such as JMH), using a realistic workload and data.

### `parallelStream()` Is Not a Substitute for a Multi-Branch Loop

Switching to parallel execution can make side effects more unpredictable and is unsuitable if processing depends on order or shared state. A sequential loop has a clear order; if you want concurrent processing, you must establish element independence, thread safety, error policy, and result ordering. Do not choose a Stream just because `.parallel()` exists.

## 10. Testing to Prove the Refactored Code Is Correct

In the section 6 example, the test suite does not only compare the success count; it compares **every outcome and line number**. Checks you should include:

1. **Valid branch for each channel**: `WEB`, `STORE`, `APP` have their corresponding labels.
2. **Bulk quantity branch**: quantity `5` has `[BULK]`; smaller quantities do not.
3. **Quantity boundaries**: `1` and `10` are valid, `0` and `11` are rejected.
4. **Malformed input formats**: missing fields, extra fields, empty product name, disallowed characters, unparseable quantity.
5. **`null` and blank**: produce `Skipped` as specified, without throwing an accidental `NullPointerException`.
6. **Position**: each line has exactly one outcome and error lines point to the right `line`.
7. **Order**: output results preserve the input data order.
8. **Repeatability**: calling with the same data twice produces equal results when there is no external state.
9. **Input immutability**: the `String`s in the input list are not altered and no elements are removed from the source.
10. **Out-of-contract exceptions**: if a programming or infrastructure error occurs, it must not be masked by a fake success fallback.

A notable invariant in this design is:

```text
acceptedCount + rejectedCount + skippedCount == inputCount
```

The invariant holds because each iteration adds only **one** `Outcome` and then `continue`s, or adds one `Accepted` at the end. If a new branch is added and forgets to record an outcome, a total-count test will catch the discrepancy. However, comparing totals alone is not enough: two misclassified outcomes could still produce the right sum; you must check the contents and reasons.

### Testing Branches Shadowed by Guard Order

For example, `"OTHER,,abc"` has an invalid name, invalid channel, and invalid quantity all at once. The section 6 program reports `missing product` first, because the product guard runs before the channel and quantity guards. This is a **first-error-wins policy**, not an immutable rule of Java.

If the business requirement wants to return all errors for a record, a `continue`-on-first-error structure is not enough: you need a list of violations to collect multiple errors, or a separate validator. Choosing a loop only helps express the policy more clearly; it does not decide the policy itself.

## 11. Common Mistakes When Switching to a Loop

**Mistake 1: replacing a messy Stream with a loop that has deeply nested `if`s.** If the loop still has five levels of `if/else`, readability does not improve. Use guard clauses, name your conditions, and extract business methods.

**Mistake 2: using `continue` to silently drop errors.** If `Rejected` is not recorded, invalid data can disappear from statistics. Do not turn `continue` into the loop equivalent of `filter(Objects::nonNull)` hiding errors.

**Mistake 3: using unnecessary shared mutable variables.** Variable names should have tight scope, avoiding carrying state from the previous element; especially when considering moving to parallel processing.

**Mistake 4: lumping business errors into overly broad exceptions.** Only `catch NumberFormatException` around the parse step when it is an expected error. Do not `catch (Exception ignored)` and continue just to hide bugs.

**Mistake 5: changing the output contract.** For example, switching from `Stream.toList()` to returning an `ArrayList` makes the result modifiable. If callers rely on immutability, that is a behavioral change that must be reviewed.

**Mistake 6: replacing short-circuiting operations with full traversal.** If the old Stream used `findFirst` and processing is expensive, the loop should consider `break` once a result is found. Conversely, `findAny` in a parallel Stream does not guarantee order like "the first element."

**Mistake 7: assuming conditions are always independent.** The order of input checks, parsing, classification, and formatting can change which error is reported. Always have tests for data violating multiple rules at once.

**Mistake 8: focusing on style instead of the contract.** There is no rule saying "if there are three branches, you must use `for`." The best approach is the one where a reader can accurately determine the intent, error flow, and results without having to mentally simulate a chain of nested lambdas.

## 12. Practice Exercises

1. Add the `PARTNER` channel with the label `EXTERNAL`. Add tests for the new channel and verify existing channels remain unchanged.
2. Allow quantities from 1 to 20, but only attach `[BULK]` for quantities of 10 or more. Write tests for the boundaries 9, 10, 20, and 21.
3. Extract the entire processing of one line into `static Outcome transformOne(int line, String raw)`. Compare the `for` loop calling that helper with `IntStream.range(...).mapToObj(...)`. Both versions must produce the same `Outcome` list.
4. Change the `null` policy from `Skipped` to `Rejected`. State which tests must change and explain why this is a business change, not merely a refactor.
5. If `raw` contains sensitive data, design error messages that include only the line number, error code, and reason, avoiding logging the raw input verbatim.
6. Write tests for input with multiple simultaneous errors, such as `"OTHER,,abc"`, and determine whether a first-error-wins policy is appropriate or if a list of errors should be returned.

When choosing between a Stream and a loop, ask yourself: **Can a reader easily see each branch, exit point, failure cause, and final outcome?** If most answers are "no," consider a clear loop or extracting the logic into small functions before keeping the pipeline.
