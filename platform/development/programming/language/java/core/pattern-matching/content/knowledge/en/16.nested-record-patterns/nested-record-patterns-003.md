# Combining Type Patterns and Record Patterns (Java 21)

## Objectives

In Java, a **type pattern** verifies the type of a value and binds that value to a variable, whereas a **record pattern** deconstructs the components of a record. By combining them, you can match types and traverse multi-level data structures directly within `instanceof` or `switch`, instead of writing manual casts and accessor calls.

This lesson belongs to the **Nested record patterns** group. You should understand:
- How to read a type pattern `String text` and a record pattern `Point(int x, int y)`.
- How to place a type pattern inside a record pattern, and how to nest multiple record patterns.
- How to apply them with `instanceof`, `switch`, and `when` guards.
- How to handle `null`, pattern variables, branch ordering, and `switch` exhaustiveness.

**Version:** Record patterns (JEP 440) and pattern matching for `switch` (JEP 441) are standard features starting in **Java 21**. The examples below use JDK 21 or later and do not require `--enable-preview`. Type patterns in `instanceof` have been standard since Java 16.

## 1. From Type Patterns to Nested Record Patterns

A **type pattern** checks a type and declares a variable:

```java
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Here, `String text` confirms that `value` is a `String` and provides the variable `text`; it does not deconstruct the object's fields.

A **record pattern** checks a record and matches its components in order:

```java
record Point(int x, int y) {}

// Illustrated inside a method:
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

`Point(int x, int y)` directly binds the two coordinates. With a regular type pattern `Point point`, you would have to call `point.x()` and `point.y()` to retrieve them.

Consider the following types:

```java
record Point(int x, int y) {}
record Box(Point topLeft, Point bottomRight) {}
record Packet(String id, Object payload, Box region) {}
```

You can combine all of them in a single pattern:

```java
Packet(
    String id,
    String text,
    Box(
        Point(int left, int top),
        Point(int right, int bottom)
    )
)
```

Reading from outside to inside:
1. The value must be a `Packet`.
2. `String id` binds the `id` component, which is declared as `String`.
3. `String text` checks the `payload` component whose static type is `Object`, requiring the actual runtime value to be a `String`. An `Integer` or `null` value will not match here.
4. `Box(...)` requires `region` to be a non-null `Box` and further deconstructs its two `Point`s.
5. Each `Point(int ..., int ...)` deconstructs two `int` components to extract the four coordinates.

Because **each component in a record pattern accepts a sub-pattern**, you can replace a type pattern with another record pattern when you want to go deeper into the structure. This is how type patterns and nested record patterns are combined.

## 2. Complete Program: Classifying a Packet

Create the file **`CombinedPatternDemo.java`**:

```java
public class CombinedPatternDemo {
    record Point(int x, int y) {}

    record Box(Point topLeft, Point bottomRight) {}

    record Packet(String id, Object payload, Box region) {}

    static int areaOfTextPacket(Object value) {
        if (value instanceof Packet(
                String id,
                String text,
                Box(Point(int left, int top), Point(int right, int bottom)))
                && right > left && bottom > top) {
            return (right - left) * (bottom - top);
        }
        return 0;
    }

    static String describe(Object value) {
        return switch (value) {
            case Packet(
                    String id,
                    String text,
                    Box(Point(int left, int top), Point(int right, int bottom)))
                    when right > left && bottom > top ->
                id + ": text=" + text
                    + ", area=" + ((right - left) * (bottom - top));

            case Packet(
                    String id,
                    Integer count,
                    Box(Point(var left, var top), Point(var right, var bottom)))
                    when count > 0 ->
                id + ": count=" + count
                    + ", start=(" + left + "," + top + ")";

            case Packet(var id, var payload, var region) ->
                id + ": other=" + payload;

            case null -> "null input";

            default -> "unsupported input";
        };
    }

    public static void main(String[] args) {
        Box box = new Box(new Point(1, 2), new Point(5, 7));

        System.out.println("area="
            + areaOfTextPacket(new Packet("P-1", "hello", box)));
        System.out.println(describe(new Packet("P-1", "hello", box)));
        System.out.println(describe(new Packet("P-2", 3, box)));
        System.out.println(describe(new Packet("P-3", -2, box)));
        System.out.println(describe(new Packet("P-4", "hello", null)));
        System.out.println(describe(null));
        System.out.println(describe("other"));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 CombinedPatternDemo.java
java CombinedPatternDemo
```

Stdout:

```text
area=20
P-1: text=hello, area=20
P-2: count=3, start=(1,2)
P-3: other=-2
P-4: other=hello
null input
unsupported input
```

**Explanation of each case:**

- For `P-1`, `payload` is a `String` and `region` contains two `Point(1,2)` and `Point(5,7)` instances. The coordinate condition is valid, so the area = (5 − 1) × (7 − 2) = 20. Both `instanceof` and `switch` match the type patterns inside two levels of record patterns.
- For `P-2`, `payload` is `Integer(3)`, so the `String text` branch does not match. The `Integer count` branch matches, the guard `count > 0` evaluates to true, and the variables `left`/`top` have values 1/2.
- For `P-3`, `count = -2`, so the guard `count > 0` evaluates to false; `switch` falls through to the fallback branch `Packet(var id, var payload, var region)`.
- For `P-4`, `region = null`, so `Box(Point(...), Point(...))` does not match. The fallback form `Packet(var ...)` can still handle a record containing a `null` component.
- The `null` selector matches `case null`; the string value `"other"` matches `default`.

The example uses `int` for simplicity. If coordinates are sufficiently large, subtraction or multiplication can cause integer overflow. In production systems, validate the data range and use `long` where appropriate.

## 3. When to Use instanceof vs. switch?

**`instanceof`** is suited for a single targeted check. You can chain `&&` after the pattern: the pattern variables are only in scope when matching succeeds.

```java
if (value instanceof Packet(
        String id, String text,
        Box(Point(int left, int top), Point(int right, int bottom)))
        && right > left && bottom > top) {
    // text, left, top, right, bottom are in scope here.
}
```

If the outermost value has the wrong type, `payload` is not a `String`, or `region` lacks the required structure, the `if` branch does not execute.

**`switch`** is suited when you need to classify multiple variants. A single branch can check types, deconstruct records, and add a `when` guard:

```java
case Packet(
        String id, Integer count,
        Box(Point(var left, var top), Point(var right, var bottom)))
        when count > 0 ->
    id + ": count=" + count
        + ", start=(" + left + "," + top + ")";
```

This is a `case` snippet from the complete program, not a standalone program. `when` is evaluated only after the pattern matches. When the guard is false, subsequent cases can still be considered.

In `Point(var left, var top)`, `var` is a type pattern whose type is inferred from the component; here both variables have type `int`. It avoids repeating an already obvious type and is not an arbitrary runtime check.

## 4. Rules, Limitations, and Common Pitfalls

### 4.1. Each Component Pattern Must Be Compatible with Its Static Type

`Packet` declares `payload` as `Object`, so `String text` or `Integer count` are valid type-filtering patterns at this position.

Conversely, using `String text` at the `region` position (static type `Box`) or at an `int` coordinate position is type-incompatible. The compiler checks the validity of every sub-pattern, even when deeply nested.

Record patterns only deconstruct **record classes**. For ordinary classes, use a type pattern such as `SomeClass obj` and the class's accessors/methods; you cannot apply `SomeClass(component1, component2)` syntax directly.

### 4.2. Distinguishing null for the Selector, Record, and Components

- `value instanceof ...` returns `false` when `value == null`; a `null` value does not match any record pattern.
- `Box(Point(...), Point(...))` does not match when the `region` component itself is `null`.
- A type pattern nested inside a record **can match null** if it is *unconditional* for the declared component type. Therefore, `Packet(var id, var payload, var region)` can bind both `payload == null` and `region == null`.
- `String id` placed at a component declared as `String` is unconditional and can accept `null`. By contrast, `String text` at a component of type `Object` does not match `null` because it requires an actual runtime value of type `String`.
- For a `switch` on a `null` reference, use `case null` if you want to handle this value. A regular `default` does not replace `case null`; without null handling, a `NullPointerException` can occur.

### 4.3. Specific Cases Must Appear Before General Cases

Example that is **intentionally invalid and will not compile** if placed in a `switch`:

```java
case Packet packet -> "any packet";
case Packet(String id, String text, var region) -> "text packet";
```

`Packet packet` already accepts every non-null `Packet`, so the subsequent `Packet(String id, String text, ...)` branch is *dominated*. The compiler detects that the branch can never be selected.

Place branches that check `String`/`Integer` and deeply nested record patterns first, and place the `Packet(var id, var payload, var region)` fallback afterward. A `when` guard can prevent a branch from being selected, so you should also account for the case where the guard is false.

### 4.4. switch Expressions Must Be Exhaustive

A `switch` expression is **exhaustive** when its branches cover every type the selector can take. In `describe(Object value)`, the `Packet` branches do not handle `String` or `Long`, so `default` is required. `case null` handles null input separately.

When the selector is a sealed hierarchy or a record with record patterns that cover all cases, the compiler can prove exhaustiveness without `default`. Even then, consider the possibility of `null` input separately.

### 4.5. Pattern Variables Are Scoped to the Match Result

Variables such as `text`, `left`, and `right` can be used in the body of the matched branch, in that branch's `when` guard, and on the appropriate side of `&&`. They are not in scope in a failed branch or anywhere the compiler cannot guarantee they have been bound.

Do not declare two pattern variables with the same name within a single nested record pattern. To compare two coordinates, give them distinct names and use `when left == right` or an equivalent conditional expression.

### 4.6. Deconstruction Does Not Mean Creating or Modifying Objects

`Point(int x, int y)` retrieves values from the record's component accessors; it does not create a new `Point`. A record's component fields are final; however, if a component holds a reference to a mutable object, the record is not automatically deeply immutable.

## 5. How to Apply and Exercise

A practical workflow for writing combined patterns:
1. Identify the outermost record and the type of each component.
2. Only deconstruct the data levels you actually need; if you only need the whole object, `Packet packet` is simpler.
3. Place type patterns at polymorphic components, such as `String text` and `Integer count` for `Object payload`.
4. Use `&&` or `when` for business conditions instead of trying to turn every condition into a type check.
5. Order cases from specific to general and handle null/fallback cases completely.
6. Extract helper methods when patterns become too deeply nested or have complex guards.

**Exercise:** Add a branch to `describe` that handles a `Packet` whose `payload` is a `Long` greater than 10 and whose `region` contains two `Point`s. Place `Long amount` at the payload position, use nested `Box(Point(...), Point(...))`, and add the guard `when amount > 10`. Add this branch **before** the `Packet(var ...)` fallback, then test with `11L`, `9L`, and `null`: only `11L` should enter the new branch; the other two cases should go to the fallback.

**Takeaway:** A type pattern filters types and binds variables; a record pattern traverses and binds record structure. Combining them makes the accepted data shape explicit directly in the syntax, reduces manual casts, and keeps multi-level structure handling under control.

## Official References

- Oracle Java SE 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java SE 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- OpenJDK JEP 440: https://openjdk.org/jeps/440
- OpenJDK JEP 441: https://openjdk.org/jeps/441
