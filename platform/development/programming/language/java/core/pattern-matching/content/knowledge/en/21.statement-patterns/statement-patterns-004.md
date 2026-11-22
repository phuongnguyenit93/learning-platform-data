# Patterns in switch statements (Java 21)

## 1. Why do we need patterns in switch statements?

In Java, a traditional `switch` usually compares a value against constants such as `int`, `String`, or `enum`. When the input is an `Object`, an interface, or a superclass containing multiple data forms, comparing constants alone is not enough. Before pattern matching for `switch`, developers typically used chains of `if / else if` and `instanceof` to classify types, then cast or called accessors to extract information.

**Pattern matching in `switch statement`** allows writing `case` branches based on the *type* and *structure* of the input. A branch can use a type pattern (`String text`), a record pattern (`Text(String content)`), a nested record pattern (`Envelope(Text(String content), String destination)`), or a `when` guard to filter conditions. When a branch matches, the pattern variables can be used directly in the handling statements.

This lesson focuses on the **`switch statement`**: a control-flow construct that executes one or more statements, such as logging, notifying, updating state, or calling a service. At the end of the lesson, we will clearly distinguish it from the **`switch expression`**, which produces a value.

**Version:** Pattern matching for `switch` was standardized in **Java 21** (JEP 441); record patterns were standardized in the same release (JEP 440). The examples use JDK 21 or later and do not require `--enable-preview`.

After this lesson, you will be able to:
- Write a `switch statement` using type patterns, record patterns, and `when` guards.
- Choose between the arrow branch syntax `->` and the colon syntax `:`.
- Understand pattern ordering, dominance, exhaustive switch, `null`, and variable scope.
- Spot common mistakes when migrating from `if/else` to `switch`.

## 2. Basic syntax: cases matching data types

Consider an input declared with type `Object`, which may hold a `String`, an `Integer`, or another type. A `switch statement` using patterns:

```java
// Illustrated inside a method with a variable value of type Object:
switch (value) {
    case String text ->
        System.out.println("Text length: " + text.length());

    case Integer number ->
        System.out.println("Integer: " + number);

    case null ->
        System.out.println("Value is null");

    default ->
        System.out.println("Another type");
}
```

Here:

1. `case String text` is a **type pattern**: it checks whether the selector has type `String` and binds the value to the variable `text`.
2. `case Integer number` checks whether the selector has type `Integer` and binds the variable `number`.
3. `case null` handles a `null` selector explicitly.
4. `default` receives the remaining objects, such as `Double`, `Long`, or a custom type.
5. Because this is a **statement**, each branch only executes a `System.out.println` call. The `switch` as a whole does not produce a value to assign.

Unlike manually writing `if (value instanceof String)` and then casting `(String) value`, the variable `text` is already typed by the compiler, so no cast is needed.

**Note:** The selector value of `switch` is evaluated upon entering the `switch`, and then the branches are matched according to Java's rules. Do not write a `switch` to replace a chain of conditions unrelated to the same selector.

## 3. Two ways to write cases in a switch statement

### 3.1. Using arrow: case ... ->

This is the preferred syntax with pattern matching when each branch needs an independent action:

```java
// Illustration:
switch (value) {
    case String text -> System.out.println(text);
    case Integer number -> System.out.println(number * 2);
    case null -> System.out.println("missing");
    default -> System.out.println("other");
}
```

Each `->` branch executes only its own action; there is **no fall-through** to the next branch. There is no need to add `break` to stop execution from continuing.

If a case consists of multiple statements, use a block:

```java
case String text -> {
    String normalized = text.trim();
    System.out.println("Length: " + normalized.length());
    System.out.println("Text: " + normalized);
}
```

This is the body of a single case placed inside a `switch statement`, not a standalone program.

### 3.2. Using colon: case ...:

Java 21 also allows the traditional-style **switch statement** with pattern labels:

```java
switch (value) {
    case String text:
        System.out.println("Text: " + text);
        break;

    case Integer number:
        System.out.println("Integer: " + number);
        break;

    case null:
        System.out.println("missing");
        break;

    default:
        System.out.println("other");
}
```

In the `:` form, `break` exits the `switch statement`. For pattern cases that bind variables, **do not rely on fall-through** between branches: Java enforces compile-time restrictions to prevent falling into a branch whose pattern variable has not been properly bound. When migrating legacy code to pattern switch, add appropriate `break` statements or convert the entire `switch` to the `->` form.

A switch block must consistently use either **`case ... ->`** or **`case ...:`**; do not mix the two forms within the same block.

### 3.3. Switch statement vs. switch expression

| Criterion | `switch statement` | `switch expression` |
| --- | --- | --- |
| Purpose | Perform actions, control program flow | Compute and return a value |
| Example | `switch (value) { case String s -> log(s); ... }` | `String result = switch (value) { case String s -> s; ... };` |
| `->` branch | Can use a statement expression, a block, or `throw` | Uses a value expression, a block with `yield`, or `throw` |
| `break` | Used to exit the switch, typically in `case ...:` form | Not used to return a value |
| `yield` | Not used to produce a result from a switch statement | Used inside a switch expression block to produce a result |
| Exhaustiveness with pattern cases | An enhanced switch statement must cover all possible selector values | A switch expression must also be exhaustive |

Example using an **expression** for comparison, not the approach of this lesson:

```java
// value has type Object:
String description = switch (value) {
    case String text -> "Text: " + text;
    case Integer number -> "Integer: " + number;
    case null -> "Missing";
    default -> "Other";
};
```

In a `switch statement` with `->`, writing `case String text -> "Text: " + text;` just to construct a string is not a valid statement expression. If you want to return the string, switch to a `switch expression` or call a method that performs an action, such as `System.out.println`.

## 4. Complete example: type pattern, record pattern, when, and null

Suppose an application receives three kinds of messages: text, sum, and an envelope sending text to a destination. We declare a `sealed interface Message` with three child records. The benefit of this structure is that the compiler can verify whether the `switch` branches cover every subtype.

Create the file **`SwitchStatementPatternDemo.java`**:

```java
public class SwitchStatementPatternDemo {

    sealed interface Message permits Text, Sum, Envelope {}

    record Text(String content) implements Message {}

    record Sum(int left, int right) implements Message {}

    record Envelope(Text text, String destination) implements Message {}

    static void handle(Message message) {
        switch (message) {
            case Text(String content) when content == null ->
                System.out.println("TEXT_NULL");

            case Text(String content) when content.isBlank() ->
                System.out.println("TEXT_EMPTY");

            case Text(String content) ->
                System.out.println("TEXT "
                    + content.toUpperCase(java.util.Locale.ROOT));

            case Sum(int left, int right)
                    when left < 0 || right < 0 ->
                System.out.println("SUM_INVALID");

            case Sum(int left, int right) ->
                System.out.println("SUM " + (left + right));

            case Envelope(Text(String content), String destination) ->
                System.out.println("SEND " + content
                    + " -> " + destination);

            case Envelope(var text, var destination) ->
                System.out.println("ENVELOPE_INCOMPLETE");

            case null ->
                System.out.println("NULL");
        }
    }

    static void inspect(Object value) {
        switch (value) {
            case String text:
                System.out.println("STRING " + text.length());
                break;

            case Integer number:
                System.out.println("INTEGER " + number);
                break;

            case null:
                System.out.println("OBJECT_NULL");
                break;

            default:
                System.out.println("OTHER");
        }
    }

    public static void main(String[] args) {
        handle(new Text("hello"));
        handle(new Text(""));
        handle(new Text(null));
        handle(new Sum(2, 5));
        handle(new Sum(-1, 8));
        handle(new Envelope(new Text("ping"), "ops"));
        handle(new Envelope(null, "ops"));
        handle(null);

        inspect("java");
        inspect(42);
        inspect(3.14);
        inspect(null);
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 SwitchStatementPatternDemo.java
java SwitchStatementPatternDemo
```

**Exact stdout:**

```text
TEXT HELLO
TEXT_EMPTY
TEXT_NULL
SUM 7
SUM_INVALID
SEND ping -> ops
ENVELOPE_INCOMPLETE
NULL
STRING 4
INTEGER 42
OTHER
OBJECT_NULL
```

The program is divided into two scenarios:

- **`handle(Message message)`** uses `case ... ->` and combines record patterns with `when` guards. This is a `switch statement` that performs the action of printing messages; it does not need to assign or return a result.
- **`inspect(Object value)`** uses `case ...:`, type patterns, and `break` to illustrate the traditional statement style. It has a `default` branch because `Object` can be many types besides `String` and `Integer`.

### Explaining the Text case group

`Text` is a record with a `String content` component. In the record pattern `Text(String content)`, the type pattern `String content` is **unconditional** for a component declared as `String`, so it can also bind a component value that is `null`. This differs from using `null instanceof String` at the top level, which is always false.

Therefore, the first case handles a null component:

```java
case Text(String content) when content == null ->
    System.out.println("TEXT_NULL");
```

The second case handles an empty/blank string:

```java
case Text(String content) when content.isBlank() ->
    System.out.println("TEXT_EMPTY");
```

Because the `content == null` branch is checked first, `content.isBlank()` is only called for the remaining `Text` instances whose content is non-null, avoiding a `NullPointerException`. Finally, the unguarded `Text(String content)` case handles all other `Text` cases.

If you change the order—for example, placing the unguarded `Text(String content)` case first—it will cover the more specific `Text` cases that follow and cause a dominance error.

### Explaining the Sum case group

`Sum(int left, int right)` extracts the two integer components from the record. The guard:

```java
case Sum(int left, int right) when left < 0 || right < 0 ->
    System.out.println("SUM_INVALID");
```

filters out additions with negative numbers according to the illustrative rule. For the remaining data, the unguarded `Sum(int left, int right)` case prints the result. This is only a hypothetical business rule: negative numbers are completely valid in mathematical addition; a real system needs to clearly define what data is considered invalid.

### Explaining the nested record pattern

`Envelope(Text(String content), String destination)` only matches when the `text` component holds a **non-null `Text` record**, from which `content` is extracted directly. If `text == null`, the nested `Text(...)` does not match.

The subsequent `Envelope(var text, var destination)` branch catches any `Envelope` that did not match the specific branch, such as `new Envelope(null, "ops")`. Here `var text` can bind a null component: a record pattern does not automatically require every reference component to be non-null.

### Explaining case null

`case null` in `handle` catches the selector `message == null` and prints `NULL`; `case null` in `inspect` catches `value == null` and prints `OBJECT_NULL`. Without this branch, a `switch` on a null reference typically throws a `NullPointerException`, even when `default` is present.

## 5. The when guard and case ordering

A guard is used to add a condition after Java has matched the pattern. For example:

```java
case String text when text.length() > 10 ->
    System.out.println("Long text");

case String text ->
    System.out.println("Short or medium text");
```

These are two illustrative branches in the same `switch`. For a `String` selector longer than 10 characters, the first case runs; other strings are handled by the second case. If the selector value is not a `String`, neither case matches.

**Order matters:**
1. The case's pattern is checked.
2. If the pattern matches, the `when` guard (if present) is evaluated.
3. If the guard is true, the selected branch executes; if the guard is false, matching continues with subsequent cases.
4. A general unguarded case can cause more specific cases after it to be dominated.

**Incorrect example (intentionally does not compile):**

```java
case String text ->
    System.out.println("Any string");

case String text when text.isBlank() ->
    System.out.println("Blank string");
```

The first case already covers every non-null `String`, so the second case can never be selected. Fix this by placing the guarded case first, or by splitting the logic with an `if` inside one case if that is easier to read.

Similarly, placing `case Message msg` before `case Sum(int a, int b)` is invalid if the selector belongs to the same type hierarchy: the parent case covers `Sum` and makes the leaf case unreachable.

**Rule:** Put specific patterns and cases with necessary guards first, followed by general or fallback cases.

## 6. Exhaustiveness: some switch statements must cover all types

A common point of confusion is that **a switch statement with patterns in Java 21 is not entirely identical to a traditional switch statement**. An **enhanced switch statement** (for example, one with pattern `case` labels or `case null`) must have branches covering all valid selector values, just like a switch expression.

In `handle(Message message)`, the compiler knows `Message` is `sealed` and has only three subtypes: `Text`, `Sum`, and `Envelope`. The three unguarded record pattern branches at the end of each group cover these subtypes, and `case null` handles null input. Therefore, this `switch` compiles **without needing `default`**.

In contrast, `inspect(Object value)` requires `default`: the input could be a `Double`, a `Boolean`, or any other object besides `String`/`Integer`. Having only two type pattern cases is not exhaustive.

### When adding a new subtype

If you add `record Alert(String title) implements Message {}`, you must add `Alert` to `Message`'s `permits` clause. When recompiling, `handle` is no longer exhaustive until a branch handling `Alert` is added. The compiler helps detect missing logic when a closed type hierarchy is extended.

If the hierarchy has a `non-sealed` branch, the compiler cannot rely solely on the list of currently known subclasses to conclude that branch is covered. You will typically need a type pattern that accepts the entire open branch or an appropriate `default`.

Do not add `default` just to hide the requirement to update handlers when the codebase wants to enforce coverage of all permitted subtypes; the choice depends on the API design intent.

## 7. Variable scope and rules when using pattern cases

### 7.1. Pattern variables are only in scope in the matching branch

In `case String text -> ...`, the variable `text` is bound and accessible in the case body; in `case ... when ...`, the variable is also available in the guard. It is not in scope in other cases or after the `switch`.

Separate cases can use the same pattern variable name, such as `case Text(String content)` repeated in the example, because they belong to different branches.

### 7.2. Do not confuse a null selector with a null component

- In `switch (value)`, `case null` handles **the selector itself** being null.
- In `case Envelope(Text(String content), ...)`, if the `text` component is null, the nested record pattern does not match.
- In `case Text(String content)`, the `content` component has declared type `String` and an unconditional pattern, so `content` can still be null.
- An outermost record pattern does not match a null selector; do not expect `case Text(var content)` to handle `message == null`.

If a field must be non-null, enforce it when creating the record (for example, using `Objects.requireNonNull` in a compact constructor) or validate it at an appropriate boundary; pattern matching does not replace all data invariants.

### 7.3. Do not mix arrow and colon in the same switch block

A `switch` uses either all `->` or all `:`. In the example, `handle` uses arrows; `inspect` uses colons. You can have multiple switches in the two different styles within the same class, but do not mix the two label forms in **a single** switch block.

### 7.4. Be careful with fall-through in colon-style switch statements

With `case ...:` labels, if you omit `break`, control flow can continue into the next section just like in a traditional switch. However, Java restricts fall-through when a subsequent branch declares a pattern variable; you cannot assume execution can pass through a `case String text:` label without initializing `text`.

A common mistake when migrating from a constant switch to a pattern switch is keeping fall-through without reconsidering variable scope. The `->` form avoids this issue and usually makes the logic clearer.

### 7.5. Side effects and case evaluation order

The `when` guard is used to **decide which branch handles the value**, so keep checks easy to understand and free of unnecessary side effects. Do not assume Java will invoke the guards of all cases; only a case whose pattern matches needs its guard evaluated. When logging or mutating state, place those actions in the appropriate case body.

Avoid repeating expensive or side-effecting accessor calls across multiple guards if they can be extracted into a small classification method or normalized data.

## 8. Common mistakes and how to fix them

| Mistake | Result | Fix |
| --- | --- | --- |
| Using `case String s -> "text";` as a statement | A string expression is not a valid action for a switch statement | Call a method with a side effect or convert to a switch expression |
| Placing a general pattern before a specific pattern | Subsequent cases become dominated | Put cases with guards/specific structures first |
| Only having `case String` and `case Integer` on `Object` | The enhanced switch statement is not exhaustive | Add `default` or a case covering the remaining types |
| Assuming `default` automatically handles null | A null selector may throw `NullPointerException` | Use `case null` when you want to handle null explicitly |
| Calling `content.isBlank()` before handling a null component | May throw `NullPointerException` | Handle null first or use a null-safe guard |
| Overusing fall-through with colon labels | Easy to fall into a flow with an unbound pattern variable; may cause a compile error | Use `break` or arrow syntax |
| Mixing `->` and `:` in one switch block | Syntax/compiler check error | Choose one label style for the entire block |
| Using `yield` to return a result from a switch statement | Confusing with the switch expression mechanism | Use a switch expression when a value is needed |
| Using a record pattern for a regular class | Record deconstruction applies only to records | Use a type pattern and the class's methods |
| Failing to handle a new subtype of a sealed hierarchy | The switch lacks coverage after updating the type | Add a case and recompile |

## 9. When should you use a pattern switch statement?

**Well-suited** when the application receives messages of multiple types and needs to perform actions per variant: handling events, dispatching commands, logging, updating statistics, validating, or forwarding information. The `case` branches make each type and data condition quick to read.

**Consider alternatives** when:
- There is only a single simple `instanceof` check: `if` may be shorter and clearer.
- The goal is to compute a value: a `switch expression` or a method returning a result may be more natural.
- The behavior is an intrinsic responsibility of each subtype and can be expressed via a common polymorphic interface method: virtual dispatch may be a better fit.
- A case is too long or contains many complex guards: extract the processing into small methods and keep the switch as the dispatcher.

Pattern matching primarily improves **how type and structural selection is expressed**; it does not guarantee being faster than every `if/else` chain. For performance requirements, benchmark on real data rather than inferring from syntax.

## 10. Self-check exercises

**Exercise 1 — Add a pattern and guard.** Add `record Product(String sku, int quantity) implements Message {}` to the sealed hierarchy and add `Product` to `Message`'s `permits` clause. Write a case that prints `LOW_STOCK` when `quantity < 5` and a general case that prints `STOCK_OK` for the remaining quantities. Place the guarded case before the general case; compile to verify the switch is exhaustive.

**Exercise 2 — Add null handling.** Try passing `new Envelope(new Text(null), "ops")`. The nested pattern branch in the example still matches because the `Text.content` component can be null, so the printed output contains the string `null` during string concatenation. If business rules do not allow null content, add a guarded branch before the regular send case or validate at `Text` creation time.

**Exercise 3 — Convert colon to arrow.** Rewrite `inspect` using only `case ... ->` branches. Keep all 4 cases (`String`, `Integer`, `null`, `default`) and verify that stdout is unchanged. When using arrow syntax, remove the unnecessary `break` statements.

**Exercise 4 — Intentional error.** Place a general case `case Message msg -> System.out.println("MESSAGE");` at the top of `handle`, then compile. Observe the dominance error for the specialized cases below it; fix it by moving the general branch to the end or removing it when all subtypes are already covered.

**Takeaway:** Patterns in a **`switch statement`** let you branch on data type and structure while performing actions. Java 21 supports type patterns, record patterns, and `when` guards; put specific cases before general ones, check exhaustiveness, handle null selectors and null components separately, and use `->` when fall-through is not needed.

## References

- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification SE 21, `14.11 — The switch Statement: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11
- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- OpenJDK JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441
- OpenJDK JEP 440 — Record Patterns: https://openjdk.org/jeps/440
