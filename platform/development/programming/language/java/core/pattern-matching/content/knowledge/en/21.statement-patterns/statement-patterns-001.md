# Patterns in if Statements (Java 21+)

In Java, the `if` statement does not only test ordinary Boolean expressions. You can place a **pattern** inside an `instanceof` check to both verify the shape/type of data and create type-bound variables. As a result, the `if` branch can work with an object or a record's components without manual casting.

**Version scope:** type patterns with `instanceof` have been a standard feature since **Java 16** (JEP 394). **Record patterns** used with `instanceof` were standardized in **Java 21** (JEP 440). The complete program examples in this lesson are compiled with `javac --release 21`, without needing `--enable-preview`.

## 1. Why do we need patterns in if?

Suppose an input has type `Object` but at runtime may hold a `String`, an `Integer`, or another object. Before Java 16, the common approach was to check the type and then cast:

```java
Object input = "Java";

if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.length()); // 4
}
```

With a **type pattern**, the check and variable declaration are combined into a single expression:

```java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text.length()); // 4
}
```

In `input instanceof String text`, the `String text` part is a **type pattern**. If `input` has an actual runtime type compatible with `String` and is non-`null`, the condition is true; the variable `text` has static type `String` and can be used safely inside the true branch. There is no need to write the cast `(String) input` again.

Common form:

```text
if (expression instanceof Type variable) {
    // variable can be used when the pattern has matched.
}
```

This is still a normal `if` statement: the condition must have type `boolean`. The pattern appears inside an **`instanceof` expression**, not standalone in place of the condition.

## 2. Type patterns in if / else if branches

You can handle multiple different data types in order:

```java
static String label(Object input) {
    if (input instanceof String s) {
        return "Chuỗi dài " + s.length();
    } else if (input instanceof Integer n) {
        return "Số nguyên " + n;
    } else {
        return "Kiểu khác";
    }
}
```

This is **an illustrative method** and needs to be placed inside a Java class. For `label("abc")` the result is `Chuỗi dài 3`; for `label(10)` it is `Số nguyên 10`; for `label(null)` it is `Kiểu khác`.

Key points to remember:

- Only the branch whose condition is true is executed. `s` is in scope where matching `String` succeeded; `n` is in scope where matching `Integer` succeeded.
- `if`/`else if` branches are evaluated sequentially. Subsequent branches are not run if an earlier branch was chosen.
- `null instanceof String s` and `null instanceof Integer n` are both `false`; `null` is never assigned to a top-level type pattern variable.
- Use the type appropriate to the problem; when an object already has a specific type, there is no need to use a pattern instead of calling methods directly.

## 3. Flow scoping: variable scope based on match results

Unlike some ordinary variable declarations, the scope of a **pattern variable** is determined by *flow scoping*: the compiler analyzes control flow to know at which locations the pattern has *definitely matched*.

```java
Object input = "Hello";

if (input instanceof String s) {
    System.out.println(s.toUpperCase()); // HELLO
} else {
    System.out.println("Not a String");
}

// Cannot arbitrarily use s here: the compiler does not guarantee it matched.
```

With the non-negated condition `input instanceof String s`, `s` definitely exists inside the true `if` branch; the `else` branch is not guaranteed to have `s`.

### Combining with the && operator

`&&` performs **short-circuiting** from left to right. Because of this, you can use the newly bound variable on the right-hand side:

```java
Object input = "  Java  ";

if (input instanceof String s && !s.isBlank()) {
    System.out.println(s.trim()); // Java
}
```

When the right-hand side `!s.isBlank()` is evaluated, the left-hand side was already true, meaning `s` has type `String` and is non-`null`. You can combine multiple additional checks:

```java
if (input instanceof String s && s.length() >= 3 && s.startsWith("J")) {
    System.out.println("Chuỗi bắt đầu bằng J");
}
```

Note: Java does not have syntax like `if (input instanceof String s when ...)`. **`when` is a guard used with `case` branches in a `switch` with patterns**; in `if`, use Boolean operators such as `&&`.

### Why you must be careful with ||

Consider the intent “allow a String or another condition”:

```java
// WRONG example if you need to use s in the true branch:
// if (input instanceof String s || allowOther) {
//     System.out.println(s.length()); // Not guaranteed that s matched!
// }
```

`||` can evaluate to true because of the right-hand side when the pattern on the left did **not** match. Therefore, you cannot assume `s` always has a value in this `if` branch. This is an important difference between `&&` and `||` when using pattern variables. Split the condition or design a separate check branch if you need to use `s`.

## 4. Negation !, else branches, and early return

When testing a negated condition, the meaning of variable scope changes:

```java
Object input = "Hello";

if (!(input instanceof String s)) {
    System.out.println("Not a String");
} else {
    System.out.println(s.length()); // 5
}
```

The expression `!(input instanceof String s)` is true when the pattern does not match. Therefore, `s` is only guaranteed in the `else` branch, where the negated condition is false—meaning the original pattern matched.

A very useful idiom is **early return**:

```java
static String firstCharacter(Object input) {
    if (!(input instanceof String s)) {
        return "Không phải chuỗi";
    }
    if (s.isEmpty()) {
        return "Chuỗi rỗng";
    }
    return s.substring(0, 1);
}
```

Once execution passes the first `if` without returning, the compiler knows `input` must have matched `String s`. Thus `s` can be used in the rest of the method. For `firstCharacter("Java")` the result is `J`, while `firstCharacter(42)` returns `Không phải chuỗi`.

**Do not guess scope by eye:** where a pattern variable is allowed to be used depends on the condition structure and which branches actually complete abruptly/terminate. A negated branch that does not exit early does not guarantee the variable can be used immediately after the `if`.

## 5. Record patterns in if since Java 21

With records, `if` can check the record type and **deconstruct its components** directly.

```java
record Point(int x, int y) {}
```

If you only need to keep the whole object, use a **type pattern**:

```java
Object input = new Point(2, 3);

if (input instanceof Point p) {
    System.out.println(p.x() + p.y()); // 5
}
```

If you need to use the components directly inside the branch, use a **record pattern**:

```java
Object input = new Point(2, 3);

if (input instanceof Point(int x, int y)) {
    System.out.println(x + y); // 5
}
```

Here:

- `Point(...)` is a record pattern: it matches a non-`null` `Point` object and extracts the two components in declaration order.
- `int x` and `int y` are component type patterns, creating variables `x` and `y` respectively.
- You can use `Point(var x, var y)` so the compiler infers both variables have type `int`. `var` does not make the types dynamic.
- The number of component patterns must equal the number of components in the record. `Point(int x)` is invalid for `record Point(int x, int y)`.
- Deconstruction reads the record's components; it does not mutate the `Point` object.

Because a record pattern is placed in `instanceof`, it can be combined with additional conditions just like a type pattern:

```java
if (input instanceof Point(var x, var y) && x >= 0 && y >= 0) {
    System.out.println("Tọa độ không âm: " + x + ", " + y);
}
```

If either coordinate is negative, the pattern `Point(var x, var y)` still **matches**, but the **entire `if` condition is false** due to the additional condition. Distinguishing failure of the *pattern* from failure of the *entire Boolean expression* helps you write `else if` branches accurately.

## 6. Combining if / else if with multiple record patterns

One record pattern can be used to classify a specific case, while another branch handles the remaining cases:

```java
static String describePoint(Object value) {
    if (value instanceof Point(int x, int y) && x >= 0 && y >= 0) {
        return "Non-negative point: (" + x + "," + y + ")";
    } else if (value instanceof Point(var x, var y)) {
        return "Other point: (" + x + "," + y + ")";
    }
    return "Not a point";
}
```

`describePoint(new Point(2, 3))` returns `Non-negative point: (2,3)`, whereas `describePoint(new Point(-2, 3))` returns `Other point: (-2,3)`. In the first branch, the variables `x` and `y` belong to the first pattern; in the `else if` branch, the variables named `x` and `y` are bindings of the second pattern. These bindings cannot be used outside the valid scope of each respective branch.

Using record patterns also avoids repeated casts and accessor calls when you actually need multiple components of a record.

## 7. Nested patterns in if conditions

A record can contain another record:

```java
record Shipment(String code, Point destination) {}
```

Suppose `Shipment` has a shipment code and a destination. You can match and deconstruct two levels of structure directly in `if`:

```java
Object input = new Shipment("S1", new Point(7, 8));

if (input instanceof Shipment(var code, Point(var x, var y))) {
    System.out.println(code + " to (" + x + "," + y + ")");
    // S1 to (7,8)
}
```

The order of checks is: the outer object must be a non-`null` `Shipment`; the `destination` component must be a non-`null` `Point`; then the two components `x` and `y` are extracted.

If `destination == null`, the pattern `Point(var x, var y)` does not match, so the `if` body does not run. To handle the missing-destination case specifically, **stop deconstructing** at the `var destination` level:

```java
if (input instanceof Shipment(var code, var destination)
        && destination == null) {
    System.out.println(code + " missing destination");
}
```

Here `var destination` receives the component of type `Point`, even when that component is `null`. The outer record pattern still must match a non-`null` `Shipment` object.

## 8. Understanding null in if with patterns

There are two levels of `null` to distinguish:

| Input value | Check condition | Result |
| --- | --- | --- |
| `null` | `value instanceof String s` | `false` |
| `null` | `value instanceof Point p` | `false` |
| `null` | `value instanceof Point(var x, var y)` | `false` |
| `new Shipment("S1", null)` | `value instanceof Shipment(var c, Point(var x, var y))` | `false` |
| `new Shipment("S1", null)` | `value instanceof Shipment(var c, var destination)` | `true` |
| `new Box(null)` with `record Box(String label) {}` | `value instanceof Box(var label)` | `true`; `label == null` |

Reason: a top-level type pattern or record pattern in an `instanceof` expression does not match a `null` object. However, an **unconditional component type pattern** for the declared type of a record component can match a `null` component; `var label` is an example. `Box(var label)` matching does not guarantee that `label` is non-`null`.

Therefore, inside a successful `if` branch, check extracted reference values before calling methods on them:

```java
Object value = new Box(null);

if (value instanceof Box(var label)) {
    String printable = label == null ? "(missing)" : label.trim();
    System.out.println(printable); // (missing)
}
```

This is valid Java 21 syntax when the `Box` record is declared as above. Java does not automatically add a "disallow null" rule to ordinary record constructors; if business logic requires it, you can validate with `Objects.requireNonNull` in the constructor.

## 9. Complete Java example: if with type and record patterns

Save the following content to **`IfPatternDemo.java`**:

```java
public class IfPatternDemo {
    record Point(int x, int y) {}
    record Shipment(String code, Point destination) {}
    record Box(String label) {}

    static String describe(Object value) {
        if (value instanceof Point(int x, int y) && x >= 0 && y >= 0) {
            return "Non-negative point: (" + x + "," + y + ")";
        } else if (value instanceof Point(var x, var y)) {
            return "Other point: (" + x + "," + y + ")";
        }
        return "Not a point";
    }

    static String shipmentTarget(Object value) {
        if (value instanceof Shipment(var code, Point(var x, var y))) {
            return code + " to (" + x + "," + y + ")";
        }
        if (value instanceof Shipment(var code, var destination)
                && destination == null) {
            return code + " missing destination";
        }
        return "Not a shipment with usable destination";
    }

    static String afterGuard(Object value) {
        if (!(value instanceof Point p)) {
            return "Missing point";
        }
        return "Point x=" + p.x();
    }

    static String classify(Object value) {
        if (value instanceof String s && !s.isBlank()) {
            return "Text: " + s.trim();
        } else if (value instanceof Integer n && n > 0) {
            return "Positive number: " + n;
        }
        return "Other value";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 3)));
        System.out.println(describe(new Point(-2, 3)));
        System.out.println(describe("x"));
        System.out.println(shipmentTarget(
                new Shipment("S1", new Point(7, 8))));
        System.out.println(shipmentTarget(new Shipment("S2", null)));
        System.out.println(shipmentTarget(null));
        System.out.println(afterGuard(new Point(4, 5)));
        System.out.println(afterGuard(null));
        System.out.println(classify("  Java  "));
        System.out.println(classify(10));
        System.out.println(classify(0));
        Object boxed = new Box(null);
        if (boxed instanceof Box(var label)) {
            System.out.println("Label is null: " + (label == null));
        }
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac --release 21 -encoding UTF-8 IfPatternDemo.java
java IfPatternDemo
```

**Expected output (stdout):**

```text
Non-negative point: (2,3)
Other point: (-2,3)
Not a point
S1 to (7,8)
S2 missing destination
Not a shipment with usable destination
Point x=4
Missing point
Text: Java
Positive number: 10
Other value
Label is null: true
```

Explanation:

1. `describe` uses a record pattern and `&&` to distinguish a point with non-negative coordinates, other points, and data that is not a `Point`.
2. `shipmentTarget` deconstructs two record levels when the destination exists; when the destination is `null`, the first branch does not match and the `var destination` branch handles it.
3. `afterGuard` demonstrates flow scoping with negation `!` and early return. After passing the first `if`, `p` is always a valid `Point`.
4. `classify` uses two type patterns (`String s` and `Integer n`) with additional conditions. The value `0` fails `n > 0` and therefore falls through to the remaining branch.
5. `Box(var label)` still matches when the `label` component is `null`; the program explicitly checks for it.

The program is a standalone Java file (with records declared nested inside the class) and has been verified with `javac --release 21`. The stdout section above accurately reflects the execution output.

## 10. Common mistakes

1. **Writing a redundant type check and manual cast.** If you are using `instanceof` only to cast immediately in the true branch, consider `obj instanceof Type variable`.
2. **Using a pattern variable out of scope.** `s` after `if (obj instanceof String s)` does not automatically exist after the `if` or inside `else`.
3. **Using `||` as if it were `&&`.** The overall condition being true because of another branch does not guarantee the type pattern matched. Do not read a pattern variable when the compiler cannot prove it matched.
4. **Confusing negation with a successful match.** When the condition is `!(obj instanceof String s)`, the variable `s` is not available in the true branch of the negated condition; however, it can be used in `else` or after a guard that exits early.
5. **Using `when` in `if`.** Java 21 uses Boolean operators to combine `if` conditions; `when` belongs to the case guard syntax in pattern-matching `switch`.
6. **Confusing a record pattern with a type pattern.** `Point p` captures the whole record; `Point(int x, int y)` deconstructs its components. Choose whichever is clearer and fits your needs.
7. **Wrong number, type, or order of component patterns.** `Point` has two `int` components, so a direct deconstruction pattern must also match two positions with compatible types.
8. **Assuming a record pattern matches a `null` record.** `null instanceof Point(var x, var y)` is `false`. On the other hand, a reference component extracted with `var` can still hold `null`.
9. **Calling methods on a reference component without checking it first.** A matched pattern can bind `label == null`; `label.length()` can still cause a `NullPointerException`.
10. **Trying to run record patterns on JDK 17 as a stable feature.** Code using `Point(var x, var y)` in this lesson requires JDK 21+; some older JDK releases only had preview support or do not support this syntax at all.
11. **Confusing `instanceof` with a standalone pattern statement.** Write `if (obj instanceof Point p)` or `if (obj instanceof Point(var x, var y))`; do not write `if (Point p)`.

## 11. Self-check exercises

**Exercise 1.** Given `Object value = "Hello";`, is the condition `value instanceof String s && s.length() == 5` true? Can `s` be read inside the `if` branch?

*Answer:* True. The pattern `String s` matches, `s.length()` equals `5`; the variable `s` is in valid scope inside the true branch.

**Exercise 2.** Given `Object value = new Point(-1, 4);`, is the condition `value instanceof Point(var x, var y) && x >= 0` true or false?

*Answer:* **False** because `x >= 0` is false, even though the record pattern `Point(var x, var y)` itself matches.

**Exercise 3.** Given `Object value = new Shipment("S3", null);`, does the pattern `Shipment(var c, Point(var x, var y))` match? What can you write to handle a missing destination?

*Answer:* No; the record pattern `Point(...)` does not match `null`. Use `Shipment(var c, var destination) && destination == null`.

**Exercise 4.** Why can `p.x()` be used after `if (!(value instanceof Point p)) return "Missing point";`?

*Answer:* Because every non-matching branch terminated with `return`. When execution continues past it, the compiler proves `Point p` has definitely matched.

**Exercise 5.** Does `Box(var label)` match a `Box` where `label == null`?

*Answer:* Yes. The outer `Box` record is non-`null`; `var label` is a component pattern that can receive a `null` component. You must check `label` yourself before calling methods on it.

**Official references:** [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Java Language Specification 21 – `14.30 Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
