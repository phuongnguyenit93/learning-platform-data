# Break and continue in pattern branches (Java 21+)

## 1. Does a pattern branch change the meaning of break/continue?

In Java, a “pattern branch” usually refers to a branch selected by **pattern matching**, such as `case Data(var amount)` in a `switch` or an `if (value instanceof String text)` branch. This is a way of describing a program branch, not a new Java keyword. The pattern determines **when the branch matches**, while `break` and `continue` still follow the control-flow rules of the enclosing statement.

Keep three points in mind before reading the code:

- An unlabeled `break;` terminates the **nearest enclosing loop or switch statement**. When a `switch` is inside a `for` loop, `break;` in a `case` only exits the `switch` and then continues with **the remainder of the same iteration**.
- An unlabeled `continue;` jumps to the **next iteration of the nearest enclosing loop**. It does not move to another `case`. A `switch` itself is not a loop.
- `break outer;` and `continue outer;` use labels to control an outer construct: `break` can exit a matching labeled statement; `continue` must target a labeled **loop**.

**Version:** Type patterns in `instanceof` were standardized in Java 16 (JEP 394); record patterns and pattern matching for `switch` in **Java 21** (JEP 440/441). All examples with patterns in `switch` below use **JDK 21+**, without needing `--enable-preview`.

## 2. Comparison table of control statements

| Statement | Effect | Inside a pattern branch |
| --- | --- | --- |
| `break;` | Exits the nearest loop or `switch statement` | Usually exits the `switch`, while the outer `for` loop keeps running |
| `continue;` | Jumps to the next iteration of the nearest loop | Skips the rest of the loop body |
| `break label;` | Exits the labeled statement | Exits the outer loop completely if the label points to that loop |
| `continue label;` | Continues the labeled loop | Useful when there are multiple nested loops |
| `return;` / `return value;` | Terminates the method | Does not return to process subsequent events |
| `yield value;` | Produces a value for a `switch expression` | Used with a switch expression block; does not replace `break` in a loop |

A `switch statement` is a **statement**; a `switch expression` produces a **value**. This distinction is especially important when using `case ... -> { ... }` branches.

## 3. Modeling events with a sealed interface and records

Suppose we process a stream of events, where each event has one of the following forms:

```java
sealed interface Event permits Data, Skip, Stop {}
record Data(int amount) implements Event {}
record Skip() implements Event {}
record Stop() implements Event {}
```

- `Data` carries an `amount` component.
- `Skip` requests skipping the remaining work for the current iteration.
- `Stop` requests exiting the loop iterating over the events completely.

The types declared in the example are semantically self-contained, but these illustrative snippets need to reside inside an appropriate class or Java file when compiled. The complete runnable program is in section 6.

## 4. break in a switch statement pattern case

```java
for (Event event : events) {
    switch (event) {
        case Data(var amount) -> {
            System.out.println("data:" + amount);
            break;
        }
        default -> System.out.println("other");
    }
    System.out.println("after-switch");
}
```

This is an illustrative snippet using a declared `events` variable. For `Data(3)`, `case Data(var amount)` matches the record and extracts `amount = 3`. After printing `data:3`, `break;` exits the **switch statement**. Java continues executing `System.out.println("after-switch")` within the **same iteration** of the `for` loop. It only moves on to the next event after finishing this iteration.

**Why can `break;` be omitted here?** The branch uses the arrow syntax `->`, which does not automatically fall through to the next case. `break;` explicitly illustrates the jump target, but in a block that only has a print statement before the branch ends, it is usually unnecessary.

If another loop is nested directly inside the `case` block, a `break;` placed **inside that inner loop** will exit the inner loop first. You need to look at the enclosing structure, not just the pattern name.

## 5. continue in a pattern case and when guard

```java
for (Event event : events) {
    switch (event) {
        case Data(var amount) when amount < 0 -> {
            System.out.println("ignore:" + amount);
            continue;
        }
        default -> System.out.println("handled");
    }
    System.out.println("after-switch");
}
```

- `Data(var amount)` is a **record pattern**: it checks that the event is of type `Data` and extracts the `amount` component.
- `when amount < 0` is the case **guard**: it is evaluated only after the pattern matches; the `amount` variable is in scope within the guard.
- When the amount is negative, `continue;` jumps to the **next iteration of the `for` loop**. The `after-switch` statement is skipped for this iteration.
- If there is no enclosing `for`, `while`, or `do` loop, placing `continue;` in a `case` is a **compile-time error**: `switch` is not a loop.

`continue;` never means “try the next case”. Case selection follows the matching rules of `switch`; once a branch is executing and hits `continue`, control returns to the loop.

**Case ordering:** When using `case Data(var n) when n < 0` alongside an unguarded `case Data(var n)`, place the specific guarded case **before** the general case. If the general case comes first, the compiler will determine that the guarded case below it is *dominated*.

## 6. Complete, runnable Java program

Create the file **`PatternBranchControlFlowDemo.java`**:

```java
public class PatternBranchControlFlowDemo {
    sealed interface Event permits Data, Skip, Stop {}
    record Data(int amount) implements Event {}
    record Skip() implements Event {}
    record Stop() implements Event {}

    static void process(java.util.List<Event> events) {
        int total = 0;

        outer: for (Event event : events) {
            switch (event) {
                case Data(var amount) when amount < 0 -> {
                    System.out.println("ignore:" + amount);
                    continue;
                }

                case Data(var amount) -> {
                    System.out.println("data:" + amount);
                    total += amount;
                    break;
                }

                case Skip s -> {
                    System.out.println("skip");
                    continue;
                }

                case Stop s -> {
                    System.out.println("stop");
                    break outer;
                }
            }

            System.out.println("after-switch");
        }

        System.out.println("total:" + total);
    }

    static void scan(java.util.List<Object> values) {
        for (Object value : values) {
            if (!(value instanceof String text)) continue;
            if (text.equals("END")) break;
            if (text.isBlank()) continue;
            System.out.println("text:" + text.toUpperCase());
        }
    }

    static String describe(Object value) {
        return switch (value) {
            case Integer n when n < 0 -> "negative:" + n;
            case Integer n -> {
                yield "integer:" + n;
            }
            case String s -> "string:" + s;
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        process(java.util.List.of(
            new Data(3), new Data(-2), new Skip(),
            new Data(4), new Stop(), new Data(100)
        ));

        scan(java.util.Arrays.asList("hi", 15, " ", "END", "later"));
        System.out.println(describe(-1));
        System.out.println(describe(7));
        System.out.println(describe(null));
    }
}
```

**Compile and run with JDK 21 or later:**

```bash
javac --release 21 PatternBranchControlFlowDemo.java
java PatternBranchControlFlowDemo
```

**Exact stdout:**

```text
data:3
after-switch
ignore:-2
skip
data:4
after-switch
stop
total:7
text:HI
negative:-1
integer:7
null
```

The output above was run and verified on JDK 24; the program uses syntax available since Java 21.

### Breakdown of each event in `process`

1. `Data(3)`: the unguarded case adds `3`, prints `data:3`, and `break;` exits the `switch`. Since we are still inside the `for` loop, `after-switch` is printed next.
2. `Data(-2)`: the negative guard case matches, prints `ignore:-2`, and `continue;` moves to the next event; `after-switch` is **not printed**.
3. `Skip()`: the `Skip s` type pattern branch is selected, prints `skip`, and `continue;`; the rest of the iteration is skipped.
4. `Data(4)`: adds `4` making the total `7`, prints `data:4`, `break;` exits the `switch`, and prints `after-switch`.
5. `Stop()`: prints `stop` and `break outer;` exits the labeled `for` loop. The trailing `Data(100)` does not run; the final total is `7`.

Because `Event` is a sealed interface and the three types `Data`, `Skip`, and `Stop` are its permitted subtypes, the corresponding unguarded cases cover all event types that need handling. The first `Data` branch has a guard; the second `Data` branch covers the remaining values. Therefore, no `default` is needed in this example to cover additional valid subtypes.

**Note on `null`:** `switch (event)` can throw a `NullPointerException` if the selector is `null` without a `case null`. `List.of(...)` in the example does not contain `null`, and `Event` does not guarantee that any reference value is non-null. Unlike `switch`, `value instanceof String text` always returns `false` when `value == null`.

### Breakdown of `scan`

`scan` iterates over the list `"hi"`, `15`, `" "`, `"END"`, and `"later"`:

- `"hi"` matches `String text`, is not empty/blank, and prints `text:HI`.
- `15` is not a `String`, so `continue` skips that iteration.
- `" "` is a blank string, so it is also skipped by `continue`.
- `"END"` triggers `break;`, exiting **the `for` loop of `scan`**; `"later"` is not processed.

There is no `switch` inside `scan`. Thus `break;` exits the nearest `for` loop. Its meaning changes according to the enclosing control structure, **not according to how the branch was matched by a pattern**.

## 7. Flow scoping when combining instanceof with continue

Java applies **flow scoping** to pattern variables: a variable is only in scope at locations where control flow guarantees the pattern has matched. Look at the runnable example in `scan`:

```java
for (Object value : values) {
    if (!(value instanceof String text)) continue;

    // Here text is definitely assigned from a String.
    if (text.equals("END")) break;
    if (text.isBlank()) continue;
    System.out.println(text.toUpperCase());
}
```

If `value` is not a `String`, the negated branch is true and `continue` ends the iteration immediately. Every path reaching the statements below the `if` must pass through a successful `instanceof String text`, so Java allows `text` to be used.

If you replace `continue;` in the negated branch with a print statement that does not terminate the flow, the variable `text` is **no longer definitely assigned** on the following lines and will cause a compile-time error. This is a matter of **flow-based scoping**, distinct from the jump target of `continue`.

In code using `&&`, you can check additional conditions on the matched variable:

```java
if (value instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

Conversely, you cannot read `text` on the right-hand side of `||` when the left-hand side is `value instanceof String text`, because the right-hand side of `||` runs only when the left-hand side may have failed.

## 8. When do you need break outer or continue outer?

`break;` targets the nearest breakable construct. To exit a loop outside a `switch statement`, use a label:

```java
outer: for (Event event : events) {
    switch (event) {
        case Stop s -> {
            break outer;
        }
        default -> System.out.println("processing");
    }
}
System.out.println("finished");
```

`break outer;` exits the statement labeled `outer`, so the loop stops and the program continues at `finished`. This snippet illustrates code inside a method with a declared `events` variable and the `Event` and `Stop` types already defined.

With nested loops, you can use `continue outer;` to jump to a new iteration of the outer loop:

```java
outer: for (Object item : items) {
    if (!(item instanceof String text)) continue outer;

    for (char ch : text.toCharArray()) {
        if (ch == '!') {
            continue outer; // Skip the remainder of the current item.
        }
        System.out.println(ch);
    }
}
```

Compare this with using `break;` at that spot: because the statement is inside the `for (char ch : ...)` loop, `break;` only exits **the character loop**, then moves on to any remaining statements in the outer loop. The `continue outer;` statement jumps straight to the next `item` iteration. The label of `continue` must point to an appropriate loop.

## 9. How do switch statement and switch expression differ?

### Switch statement

```java
switch (value) {
    case Integer n -> {
        if (n < 0) {
            System.out.println("negative");
            break; // Exit the switch statement.
        }
        System.out.println("non-negative");
    }
    default -> System.out.println("other");
}
```

This is an illustrative snippet **inside a method with a `value` variable**. A `switch statement` executes the statements in the selected branch. `break;` can exit the `switch`. Arrow rules do not automatically fall through, so `break` is not needed solely to prevent falling through to the next branch.

### Switch expression

```java
static String describe(Object value) {
    return switch (value) {
        case Integer n when n < 0 -> "negative:" + n;
        case Integer n -> {
            yield "integer:" + n;
        }
        case String s -> "string:" + s;
        case null -> "null";
        default -> "other";
    };
}
```

A `switch expression` must produce a value on all normal completion paths. For an arrow rule containing an expression, that expression's value becomes the result. For an arrow rule containing a **block** that needs to return a value, use `yield value;`. Do not use `break;` as a way to “return a result” from a `switch expression`; `yield` and `break` serve different purposes.

In the example, `describe(-1)` returns `negative:-1`, `describe(7)` returns `integer:7`, and `describe(null)` returns `null` thanks to `case null`. The pattern variable `n` is only in scope within the matched guard/branch. The unguarded `Integer n` case is placed after the guarded case of the same type.

Also distinguish `return`: it terminates the current method. `yield` only supplies a result for the enclosing `switch expression`; the expression can then be assigned to a variable or used in a method's `return`.

## 10. Common pitfalls and how to avoid them

| Pitfall | Explanation and how to handle it |
| --- | --- |
| Using `break;` in a `case` and thinking the outer `for` loop also stops | `break` normally exits the nearest `switch statement`. Use `break outer;` when you want to terminate a labeled outer loop. |
| Using `continue;` to move to the next case | `continue` jumps to a **new loop iteration**, not to another switch branch. |
| Writing `continue;` in a `switch` not inside a loop | There is no loop target, causing a compile-time error. |
| Using `break;` to return a string from a `switch expression` | Use `yield "value";` in a block or directly `case ... -> "value"`. |
| Placing a general `Data(var n)` case before a case with `when n < 0` | The specific branch below may be dominated. Place the specific guard first. |
| Using a pattern variable outside a branch where it is guaranteed to match | Pattern variables have **flow scoping**; only read them where every path to that point guarantees a match. |
| Forgetting `null` in a pattern `switch` | A `null` selector reference must be handled appropriately, usually with `case null` or a check before `switch`. |
| Trying to prevent fall-through with `break` in every arrow rule | With `->`, rules do not fall through; only use `break` if you need to exit the switch early. |
| Using `break;` inside a nested inner loop and expecting it to exit the outer switch | `break` selects the nearest breakable construct, which is usually the inner loop. |

**`case ... :` syntax:** The examples prefer `case ... ->` because it is clear and has no fall-through. With colon-style syntax, statement grouping rules and pattern variable scoping have additional restrictions. You should not rely on fall-through between branches with patterns.

## 11. Exercise: predict the output before running

Suppose the following three records are declared:

```java
sealed interface Action permits Value, Ignore, Halt {}
record Value(int number) implements Action {}
record Ignore() implements Action {}
record Halt() implements Action {}
```

Create a list containing `Value(2)`, `Ignore()`, `Value(5)`, `Halt()`, and `Value(99)`. Use `switch` with record/type patterns so that:

1. `Value` adds `number` to the sum and still prints `visited` after exiting `switch`.
2. `Ignore` skips printing `visited` using `continue;`.
3. `Halt` exits the entire `for` loop using a label; `Value(99)` must not be processed.
4. The final sum must equal `7`.

Suggested solution (placed inside a method, with `actions` as `List<Action>`):

```java
int sum = 0;
outer: for (Action action : actions) {
    switch (action) {
        case Value(var number) -> {
            sum += number;
            break;
        }
        case Ignore ignored -> {
            continue;
        }
        case Halt halted -> {
            break outer;
        }
    }
    System.out.println("visited");
}
System.out.println(sum); // 7
```

The expected output is two lines of `visited` (for `Value(2)` and `Value(5)`), followed by one line `7`. Try changing `break;` in the `Value` case to `continue;` to verify why the two `visited` lines disappear even though the sum remains `7`.

## 12. References

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Java Language Specification 21 — Statements (`14)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)