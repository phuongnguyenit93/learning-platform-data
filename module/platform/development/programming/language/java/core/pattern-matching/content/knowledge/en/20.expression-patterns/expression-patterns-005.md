# Arrow expressions and side effects when combining patterns (Java 21+)

## 1. What is an arrow rule in pattern matching?

In Java, a `case Pattern -> ...` label is a **switch rule** using the arrow symbol `->`. When combined with a **switch expression**, each selected branch produces a value (or throws an exception). When combined with a **switch statement**, the selected branch executes an action without needing to produce a return value for the entire `switch`.

Example with a pattern and guard:

```java
record Order(String category, int amount) {}

static String classify(Object value) {
    return switch (value) {
        case Order(var category, int amount) when amount >= 100 ->
                "Large: " + category;
        case Order(var category, int amount) ->
                "Normal: " + category;
        case String s -> "Text: " + s;
        case null -> "Missing";
        default -> "Other";
    };
}
```

In this example:

- `Order(var category, int amount)` is a **record pattern**: it checks the record and extracts its two components.
- `when amount >= 100` is a **guard**: it checks an additional condition after the record pattern matches.
- `->` opens the body of the switch rule. The first branch returns a string starting with `Large`, and the second branch returns a `Normal` string.
- `case null` handles a null selector; `default` handles the remaining values.

The `->` symbol here is **different from a lambda** (`x -> x + 1`). Both syntaxes share the same symbol, but they belong to two different language mechanisms.

A **side effect** is a state change observable outside the expression's value, such as logging, mutating a variable or collection, updating a database, emitting an event, or performing I/O. In a `switch` using patterns, side effects can occur when evaluating the **selector**, invoking a **record accessor**, checking a **guard**, or executing the **arrow branch body**. This lesson focuses on execution order and how to limit unintended effects.

**Version note:** Switch expressions have been standard since Java 14. Pattern matching for `switch` (JEP 441) and record patterns (JEP 440) were standardized in **Java 21**; all examples combining `when`/record patterns below use JDK 21+ and do not require `--enable-preview`.

## 2. Evaluation order of selector, pattern, guard, and arrow

Consider a switch expression:

```java
String result = switch (source()) {
    case Order(String name, int amount)
            when eligible(name, amount) ->
            processLarge(name);

    case Order(String name, int amount) ->
            processRegular(name);

    default -> "Other";
};
```

Processing flow description (`source`, `eligible`, and `processLarge`/`processRegular` are hypothetical illustrative methods):

1. Java evaluates the **selector `source()` exactly once** per execution of the `switch`. If `source()` increments a counter or logs something, this effect happens before finding a branch.
2. Pattern labels are tested to find a matching branch. Record patterns may invoke record accessors to extract components. This does not mean the entire matching process is side-effect-free.
3. If a branch's pattern with `when` matches, Java evaluates the guard. A guard returning `false` causes that branch not to be selected, and the search for a matching branch continues. **Side effects that already occurred in the guard are not automatically rolled back.**
4. Only the `->` body of the selected branch runs. There is no **fall-through** from one arrow branch to the next.
5. For a switch expression, the result is obtained from the expression in the branch, a block's `yield`, or termination via an exception.

Important note: **“the selector is evaluated once” does not mean every accessor/guard is called exactly once**. While trying multiple patterns, custom record accessors may be invoked during different match attempts. Do not write business logic that depends on how many times an accessor is called.

## 3. Runnable program: tracing the order of side effects

Save the following code to **`ArrowPatternEffectsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class ArrowPatternEffectsDemo {
    record Order(String category, int amount) {}

    static int sourceCalls;

    static Object source(Object input) {
        sourceCalls++;
        return input;
    }

    static boolean premium(
            String category, int amount, List<String> trace) {
        trace.add("guard(" + category + "," + amount + ")");
        return amount >= 100;
    }

    static String arm(String value, List<String> trace) {
        trace.add("arm(" + value + ")");
        return value;
    }

    static String categorize(Object input, List<String> trace) {
        return switch (source(input)) {
            case Order(String category, int amount)
                    when premium(category, amount, trace) ->
                    arm("priority:" + category, trace);

            case Order(String category, int amount) -> {
                trace.add("block(" + category + ")");
                yield "regular:" + category + ":" + amount;
            }

            case String text -> arm("text:" + text, trace);
            case null -> arm("null", trace);
            default -> arm("other", trace);
        };
    }

    static void show(Object input) {
        sourceCalls = 0;
        List<String> trace = new ArrayList<>();
        String result = categorize(input, trace);

        System.out.println(
                result + " | source=" + sourceCalls
                        + " | trace=" + trace);
    }

    static void statement(Object input) {
        List<String> steps = new ArrayList<>();

        // Switch statement: branch executes an action.
        switch (input) {
            case Order(var kind, int amount)
                    when amount >= 100 ->
                    steps.add("large:" + kind);

            case Order(var kind, int amount) ->
                    steps.add("small:" + kind);

            case null -> steps.add("missing");
            default -> steps.add("unknown");
        }

        System.out.println("statement: " + steps);
    }

    public static void main(String[] args) {
        show(new Order("book", 150));
        show(new Order("book", 20));
        show("hi");
        show(null);
        show(17);
        statement(new Order("pen", 3));
    }
}
```

Compile and run:

```bash
javac --release 21 ArrowPatternEffectsDemo.java
java ArrowPatternEffectsDemo
```

Stdout:

```text
priority:book | source=1 | trace=[guard(book,150), arm(priority:book)]
regular:book:20 | source=1 | trace=[guard(book,20), block(book)]
text:hi | source=1 | trace=[arm(text:hi)]
null | source=1 | trace=[arm(null)]
other | source=1 | trace=[arm(other)]
statement: [small:pen]
```

Analysis:

1. For `new Order("book", 150)`, `source` increments the counter to 1; the `Order(...)` pattern matches and the `premium` guard runs, recording `guard(book,150)`; since the guard is true, `arm` runs and records `arm(priority:book)`. The second `Order` branch does not run.
2. For `new Order("book", 20)`, the guard still records `guard(book,20)` **even though it returns false**. Java moves on to the unguarded `Order` branch, records `block(book)`, and uses `yield` to produce `regular:book:20`.
3. For `"hi"`, `null`, and `17`, the `Order` pattern does not match, so `premium` is not called. Each value selects the `String`, `null`, or `default` branch respectively.
4. In `statement`, `steps.add(...)` is the action of the switch statement. The program does not take a value from the `switch` as a whole; the `List` object changes because exactly one branch executes.

The `sourceCalls` variable is for illustration purposes only. It is shared `static` state without concurrency protection; in multithreaded code, do not use this counter as a thread-safe metric.

## 4. Three important forms of arrow rule bodies

### 4.1. Returning a value directly from a switch expression

```java
String description = switch (input) {
    case String s -> s.toUpperCase();
    case Integer n -> "Number: " + n;
    case null -> "Null";
    default -> "Other";
};
```

The expression to the right of `->` in the selected branch is evaluated and produces the value for the entire switch expression. Only one branch is selected, so the expressions in the other branches do **not** run.

A method call here can have side effects. For example, `case String s -> logAndFormat(s)` will both log and return a string if `logAndFormat` is designed to do both. Do not assume that a value-producing branch is pure.

### 4.2. Multiple statements in a block: using `yield`

```java
int[] counter = {0};

String label = switch (input) {
    case String s -> {
        counter[0]++;           // Side effect.
        String result = s.strip();
        yield "Text: " + result;
    }
    case null -> "Missing";
    default -> "Other";
};
```

A `-> { ... }` branch of a **switch expression** requires `yield expression;` if it completes normally with a result. `yield` produces a value for the `switch`, rather than `return`ing from the enclosing method.

Conceptually invalid:

```java
// DOES NOT COMPILE: switch expression block completes
// without producing a value.
// String label = switch (input) {
//     case String s -> {
//         counter[0]++;
//     }
//     default -> "Other";
// };
```

If a branch needs to terminate with an exception, use `throw` instead of returning a value:

```java
int normalized = switch (input) {
    case Integer n when n >= 0 -> n;
    case Integer n ->
            throw new IllegalArgumentException("Negative: " + n);
    case null -> 0;
    default -> 0;
};
```

When the `throw` branch runs, the switch expression does not produce a value for `normalized`; the exception propagates outward.

### 4.3. Arrow rules in a switch statement

```java
switch (input) {
    case String s -> System.out.println("Text: " + s);
    case Integer n -> System.out.println("Number: " + n);
    case null -> System.out.println("Null");
    default -> System.out.println("Other");
}
```

Here `switch` is a **statement**, whose purpose is to execute statements. Arrow rule branches may contain a statement expression, a block, or `throw`; no `yield` is needed to produce a value for the whole `switch`. Once a branch finishes, it does not fall through to the next branch (unlike the classic bug of forgetting `break` in `case ...:`).

## 5. Why `when` guards with side effects are error-prone

A guard can call any valid Boolean expression, including methods that log, increment counters, or mutate state:

```java
static boolean checked(int amount, List<String> trace) {
    trace.add("checked:" + amount);
    return amount > 0;
}

// Illustrative label of a switch expression:
case Order(var category, int amount)
        when checked(amount, trace) ->
        "Accepted:" + category;
```

If the pattern matches, `checked` runs. For `amount == 0`, it appends `checked:0` to `trace` **before** returning `false`. A later branch may be selected, but `trace` has already been modified.

Two different guards might access the same mutable state. If the first guard modifies state that the second guard relies on, the evaluation order and classification result become unpredictable. In business applications, try to keep guards **pure**: only read data and return `true/false`. Move state-updating operations into the body of the selected branch or a business method called from that branch.

Safer guard example with a null check:

```java
case Order(var category, int amount)
        when category != null
                && category.startsWith("VIP")
                && amount > 0 ->
        "VIP order";
```

`&&` short-circuits from left to right. If `category == null`, `startsWith` is not called. If `Order(...)` does not match, the entire guard does not run.

**An exception in a guard is not “guard false”.** If `checked` throws an exception, Java propagates the exception outward rather than silently continuing to a fallback branch.

## 6. Where should side effects be placed?

A switch expression branch can both call a side-effecting method and produce a value, but you must clearly define consistency when errors occur.

Illustrative **(non-standalone)** code example:

```java
case Order(var category, int amount) -> {
    charge(amount);             // Suppose the payment has been charged.
    yield createReceipt();      // Suppose this may throw an error.
}
```

`charge` and `createReceipt` are hypothetical methods, not part of the demo program. If `charge` has already updated the system and `createReceipt` throws an exception, Java **does not automatically roll back** the charge just because the `switch` as a whole has not returned a result. Arrow rules do not automatically provide transactions, idempotency, or safe retry mechanisms.

Practical choices:

- **Classification/data transformation expressions:** use a switch expression, preferring branch bodies that compute results purely.
- **Tasks whose primary goal is side effects:** use a switch statement or delegate the operation to a dedicated business method such as `processOrder(order)`.
- **Both processing and returning a result:** you can use a `-> { ... yield result; }` block; clearly define transactions, rollback/compensation, exception handling, and whether retrying is safe.
- **Observability/logging:** decide whether to log when checking the guard or only when the branch is selected; the two moments have different meanings.

## 7. Pattern variable scope and short-circuiting outside `switch`

In a branch:

```java
case Order(String category, int amount)
        when amount >= 100 ->
        category + ":" + amount;
```

`category` and `amount` are bound when the pattern succeeds, so they can be used in the guard and branch body. They do not automatically exist outside the `switch` or in another `case` branch.

With `instanceof`, do not use `when`; use `&&` instead:

```java
boolean eligible = input instanceof Order(var category, int amount)
        && category != null
        && amount >= 100;
```

Conditions after `&&` are evaluated only when the preceding conditions are true. The compiler knows `category` and `amount` are bound if `instanceof` returns true.

You can combine patterns with the ternary operator:

```java
String category = input instanceof Order(var kind, int amount)
        ? kind
        : "unknown";
```

In the true branch of `?:`, the variable `kind` is in scope. The false branch cannot depend on that variable.

Invalid example (illustrative code that does not compile):

```java
// if (input instanceof Order(var kind, int amount) || amount > 0) {
//     System.out.println(kind);
// }
```

When the left side of `||` is false, the right side is evaluated, but the pattern variables have not been bound. Therefore, the compiler does not allow using `amount` there.

## 8. Nulls, record accessors, and subtle effects

### Selector null and component null

- A `null` selector does not match a record pattern; handle it with `case null` if needed.
- In a pattern matching switch, `default` does not generally replace a null-handling branch. Without a matching label, a null selector can cause a `NullPointerException`.
- A record can contain a null component, for example `new Order(null, 10)`. For a `String` component, the nested pattern `String category` in a record pattern can be *unconditional* for the component type and bind null as well. A guard calling `category.length()` must therefore check for null when needed.
- With nested record patterns, if the **nested record itself** is null, the nested record pattern does not match and that branch's guard does not run. You need a branch covering that case.

### Record accessors can be customized

Java allows a record to declare explicit accessors:

```java
record Token(String value) {
    @Override
    public String value() {
        System.out.println("accessor invoked");
        return value;
    }
}
```

When processing `case Token(var text) -> ...`, Java may call `value()` to extract the component before evaluating the guard or the arrow body. Thus, **pattern testing is not necessarily completely free of side effects**. A custom accessor can log or throw an exception; when an exception occurs, it is not treated as simply “pattern did not match”.

Good design keeps accessors simple, consistent with the record's data, and avoids depending on how many times an accessor is called during pattern matching.

## 9. Exhaustiveness, branch order, and domination

A **switch expression** must cover all applicable cases of the selector. For `Object`, `default` is usually required. For a sealed hierarchy, the compiler can determine that branches cover all permitted subtypes, but a `case Pattern when condition` typically handles only **a subset** of values of that type.

Correct order:

```java
return switch (input) {
    case Order(var category, int amount) when amount >= 100 ->
            "large";
    case Order(var category, int amount) ->
            "regular";
    case null -> "null";
    default -> "other";
};
```

If you place the **unguarded** `Order(...)` branch first, it will cover `Order` instances with large amounts, causing the guarded branch below it to be **dominated**; the compiler may reject it. Place specific conditions first, and broader catch-all branches afterward.

On the other hand, a guard `when amount >= 100` does not make the switch handle every `Order`, because `Order(..., 20)` can still appear. Always provide a branch for cases that do not pass the guard.

## 10. Common mistakes and how to fix them

1. **Confusing arrow rules with lambdas.** `case Pattern -> expression` is a switch branch, whereas `x -> x + 1` is a lambda.
2. **Believing only the arrow body can have side effects.** Selectors, record accessors, and guards can all have effects before a branch is chosen.
3. **Assuming a false guard rolls back state.** Side effects in a guard persist; prefer pure guards.
4. **Missing `yield` in a switch expression block.** If a branch completes normally and must supply a result, use `yield value;`.
5. **Using `return`/`break` like `yield`.** They have different control-flow semantics and do not replace yielding a value from a switch expression.
6. **Confusing switch expressions and switch statements.** The expression form produces a value; the statement form executes actions. Both use arrow rules, but they produce results differently.
7. **Assuming fall-through between arrow rules.** A selected `->` branch does not automatically run the next `->` branch.
8. **Placing a general pattern before a specialized pattern.** This can cause the later branch to be dominated or unreachable.
9. **Not checking for null in a guard.** A record component can be null even though the pattern matched.
10. **Assuming returning a value is a transaction.** If a call before `yield` mutates state and then an error occurs, Java does not automatically undo the change.
11. **Assuming the guard is called for every input.** A guard is evaluated only after its corresponding `case` label pattern matches.
12. **Using pattern variables out of scope.** Variables are bound in the matching guard/branch body and are not available by default in other branches.

## 11. Design checklist

When combining patterns, guards, and arrow rules, check yourself against these questions:

- Does the selector have side effects, and should fetching the data be extracted into a local variable before the `switch`?
- Does the guard only perform a Boolean check without mutating state? If it has side effects, has the case where the guard returns false been accounted for?
- Is the branch body responsible for returning a value or performing an action? Are `yield`/`throw` used correctly?
- Are branches ordered from specific to general, avoiding domination and ensuring exhaustiveness?
- Are selector nulls, component nulls, and exceptions from accessors/guards handled appropriately?
- If I/O or external updates are involved, are error handling and atomicity guaranteed at the business layer?

**Remember:** A pattern defines **structural matching**; `when` further filters by **value conditions**; `->` executes **the body of a selected branch**. Side effects can happen across all three phases: checking the input, evaluating the guard, and running the branch. Keep guards and accessors simple, use arrow expressions for clear data transformations, and place state updates where error handling is properly managed.

### References

- JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Oracle Java 21 — Switch Expressions: https://docs.oracle.com/en/java/javase/21/language/switch-expressions.html
