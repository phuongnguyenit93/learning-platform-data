# How the Compiler Analyzes Patterns

## 1. Distinguishing what the compiler checks from what runtime decides

Pattern matching in Java does more than shorten type casts. A pattern establishes a **contract on type and data structure**. The compiler (`javac`) must verify that the pattern syntax is valid, that bound variables have appropriate types, and that every `switch` branch satisfies the rules of the language.

Example:

```java
Object input = "Java";

if (input instanceof String text && text.length() >= 4) {
    System.out.println(text.toUpperCase());
}
```

At **compile time**, Java checks the following:

1. The static type of `input` is `Object`, and the `instanceof String` test is meaningful in terms of types.
2. `text` is a pattern variable with static type `String`.
3. After the `&&` operator, `text` is only used if the pattern on the left has matched; the calls `text.length()` and `text.toUpperCase()` are both type-valid.
4. The entire `if` condition has type `boolean`, and the body uses variables that are in scope.

At **runtime**, the program actually checks whether the real object is a `String` and whether its length is at least `4`, and then prints `JAVA`. The compiler does not pre-evaluate expressions against every possible input that might appear in the future.

You can think of the compiler's work in layers of checks: **pattern syntax → type compatibility → variable types and scoping → branch reachability → switch exhaustiveness**. This is a mental model for learning the language, not a guarantee that every compiler executes its internal phases in this exact order.

## 2. Checking type compatibility

A pattern must make sense for the **static type of the expression being tested**. The compiler does not wait until runtime to accept a type test that is guaranteed to be impossible according to Java's allowed type conversion rules.

Valid example:

```java
Object input = 42;
if (input instanceof Integer number) {
    System.out.println(number + 1);
}
```

`input` has static type `Object`, which may be pointing to an `Integer`. When it matches, `number` has static type `Integer`, so the example prints `43` thanks to unboxing.

Invalid example:

```java
String text = "abc";

// DOES NOT COMPILE: String and Integer are final types
// that cannot be converted under this type test.
// if (text instanceof Integer number) {
//     System.out.println(number);
// }
```

There is no valid `instanceof` test from `String` to `Integer` in this case: the compiler detects **incompatible types**, rather than letting the program always return `false` at runtime.

An important distinction: the compiler relies on **static type declarations** and the language's conversion rules. It does not guess that an `Object` variable will only hold a `String` based on assignments observed in an example snippet.

### Patterns are not the same as manual casting

Before pattern matching, the common way to write this was:

```java
if (input instanceof String) {
    String text = (String) input;
    System.out.println(text.length());
}
```

With a type pattern:

```java
if (input instanceof String text) {
    System.out.println(text.length());
}
```

The compiler both checks whether the test is applicable and establishes that `text` has type `String` in the matched branch. The body does not need a separate `(String) input` cast.

## 3. How the compiler determines the types of pattern variables

Given:

```java
record Point(int x, int y) {}
```

The record pattern:

```java
if (input instanceof Point(int x, int y)) {
    System.out.println(x + y);
}
```

requires the compiler to check against the record declaration. `Point` has exactly two components of types `int` and `int`; therefore `x` and `y` are `int` variables in the part of the program where the pattern has matched.

Java 21 also allows component type inference:

```java
if (input instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Here, `var` does not mean the variables are untyped. The compiler infers each variable as `int` from the corresponding component of `Point`.

Examples of syntax/type errors when matching a record:

```java
// DOES NOT COMPILE: Point has two components, not one.
// if (input instanceof Point(int x)) { }

// DOES NOT COMPILE: Point's components are int, not String.
// if (input instanceof Point(String x, String y)) { }
```

A record pattern must match the exact **number of components** and use patterns compatible with each component's type. Variable names in the pattern do not override the declaration order. For example, `Point(int y, int x)` may be valid, yet `y` receives the first component—a semantic mistake that the compiler cannot know whether the author intended or not.

### Nested patterns

Suppose:

```java
record Segment(Point start, Point end) {}
```

The pattern:

```java
if (input instanceof Segment(
        Point(int x1, int y1),
        Point(int x2, int y2))) {
    System.out.println(x2 - x1);
}
```

is analyzed at compile time based on the declared structure of `Segment`: it has two components of type `Point`; each `Point` in turn has two components of type `int`. The compiler checks compatibility and determines the variables `x1`, `y1`, `x2`, `y2`.

**At runtime**, matching the entire pattern also depends on the value of each component. If `start` or `end` is `null`, the `Point(...)` pattern at that position does not match; the entire nested `Segment(...)` pattern does not match. A record pattern does not invoke constructors, create new objects, or turn all components into non-`null` values.

## 4. Pattern variable scope: flow scoping and definite match

A particularly important point is that the compiler does not only look at curly brace positions. It also analyzes **control flow paths** to know where a pattern variable is definitely bound (*flow scoping*).

### Valid case with &&

```java
if (input instanceof String text && !text.isBlank()) {
    System.out.println(text.length());
}
```

`&&` is short-circuiting: the right-hand side is evaluated only when the left-hand side is true. Therefore, when evaluating `text.isBlank()`, the compiler can prove that `text` has been produced by the pattern. Inside the `if` body, the overall condition is also true, so the variable remains in scope.

### Invalid case with ||

```java
// DOES NOT COMPILE:
// The right-hand side of || runs when the pattern on the left does NOT match,
// so the variable text is not guaranteed to exist.
// if (input instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

`||` is also short-circuiting, but the condition that triggers the right-hand side is **the opposite of `&&`**: the right-hand side is evaluated when the left-hand side is false. Hence `text` cannot be used there. You should not fix this by changing it to `|` or `&`; those two boolean operators evaluate both sides.

### Guard clauses keep the variable valid afterward

```java
static int lengthOrZero(Object input) {
    if (!(input instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

The negated branch ends with `return`. Every execution path that reaches `return text.length()` has passed the `instanceof` test; the compiler allows using `text`.

Conversely:

```java
// DOES NOT COMPILE if you try to use text after the if:
// if (!(input instanceof String text)) {
//     System.out.println("Không phải chuỗi");
// }
// System.out.println(text.length());
```

Here, the branch where the pattern **did not match** can still continue past the `if`. The compiler cannot guarantee that `text` is bound at the statement below. This is about flow analysis, not just `{}` block scope.

### Scope across switch branches

```java
return switch (input) {
    case String text -> "Chuỗi: " + text.length();
    case Integer number -> "Số: " + number;
    case null -> "Không có dữ liệu";
    default -> "Loại khác";
};
```

Here `text` is only in scope in the `String` branch, and `number` in the `Integer` branch. You cannot carry `text` over into the `Integer` branch and expect the compiler to know that the value has type `String`. A pattern's variables are only meaningful in the branch where that pattern matches.

## 5. How the compiler analyzes cases, guards, and dominance in switch

Pattern matching for `switch` in Java 21 allows each branch to express a data type or record structure. The compiler checks the **selector type**, the **validity of each branch**, and whether a later branch is completely covered by an earlier branch (*dominance*).

Example of an error due to branch ordering:

```java
// DOES NOT COMPILE: a general branch appears before a specific branch.
// return switch (input) {
//     case Object any -> "Bất kỳ object không null";
//     case String text -> "Chuỗi: " + text;
//     case null -> "null";
// };
```

`case Object any` matches every non-`null` object, including `String`. Therefore the subsequent `case String text` branch can never be selected, and the compiler detects that the branch is dominated.

Proper ordering:

```java
return switch (input) {
    case String text -> "Chuỗi: " + text;
    case Integer number -> "Số: " + number;
    case null -> "Không có dữ liệu";
    default -> "Loại khác";
};
```

A **`when` guard** adds a condition after the pattern matches:

```java
return switch (input) {
    case Integer number when number > 0 -> "Số dương";
    case Integer number -> "Số nguyên không dương";
    case null -> "Không có dữ liệu";
    default -> "Loại khác";
};
```

The compiler knows that `number` in `when number > 0` has type `Integer` as bound by the pattern. Whether `number > 0` actually evaluates to true or false is determined at runtime.

**Place specific branches with `when` before an unguarded `Integer` branch.** If an unguarded `case Integer number` comes first, a later branch of the same type can be **dominated**. Do not assume the compiler understands arbitrary mathematical or logical relationships between two `when` expressions. The language's dominance rules are based on what the compiler is specified to prove, not a general solver for arbitrary business predicates.

### A guard does not mean the pattern is exhaustive

```java
// Having only a positive-number branch makes the switch expression non-exhaustive:
// return switch (input) {
//     case Integer n when n > 0 -> "Dương";
// };
```

Because `input` might not be an `Integer`, or might be a non-positive integer, this expression does not cover all cases. Adding `default` or the appropriate remaining branches resolves the issue.

## 6. Exhaustiveness: how the compiler proves a switch expression covers all cases

A **switch expression** must cover all selector values required by the language rules. For `Object`, which has an unbounded set of types, `default` is usually necessary.

With **sealed types**, the compiler has additional information about the permitted subtypes, allowing it to check exhaustiveness without a catch-all `default` for non-`null` values:

```java
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
```

A complete example:

```java
static String shapeKind(Shape shape) {
    return switch (shape) {
        case Circle(double radius) -> "Tròn: " + radius;
        case Rectangle(double width, double height) ->
                "Chữ nhật: " + width + " x " + height;
        case null -> "Không có hình";
    };
}
```

The compiler can determine the non-`null` forms of `Shape` from the `sealed` declaration and the two permitted record types. `case null` handles a `null` selector explicitly. In this example, no `default` is needed.

When using guards, you must add a branch to handle values that **do not satisfy the guard**:

```java
return switch (shape) {
    case Circle(double radius) when radius > 0 -> "Tròn hợp lệ";
    case Circle(double radius) -> "Tròn bán kính không dương";
    case Rectangle(double width, double height) ->
            "Chữ nhật";
    case null -> "Không có hình";
};
```

The second `case Circle(double radius)` branch covers `Circle` values that fail the first guard. If there were only `Circle(...) when radius > 0`, circles with radius `0` or negative radius would not be handled; a branch with an arbitrary guard cannot be treated as covering the entire `Circle` type.

**Note:** `default` should not be assumed to automatically catch a `null` selector in pattern matching for `switch`. If the selector can be `null` and you want to return a dedicated result, use `case null`. Without a matching `null` handler, `switch` can throw `NullPointerException` at runtime even when non-`null` type coverage is exhaustive.

## 7. Generic record patterns and the limits of type erasure

The compiler must also understand generic types of records:

```java
record Box<T>(T value) {}

static void show(Box<String> box) {
    if (box instanceof Box(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

In Java 21, the compiler can **infer type arguments** for a record pattern when the static context is clear enough. For `Box<String>` in the example above, the component `text` is inferred as `String`. Thus, writing `Box(var text)` does not mean using a raw type.

However, Java uses **type erasure** for generics: do not assume that testing an `Object` instance will verify the exact `String` type argument of `Box<String>` at runtime. If the input has an unknown type, check the actual component type:

```java
static String readBox(Object input) {
    if (input instanceof Box(var value) && value instanceof String text) {
        return text.toUpperCase();
    }
    return "Không phải Box chứa String";
}
```

The key takeaways are:

- The compiler checks **static type validity and type inference**.
- Runtime checks whether the concrete object and its components match the pattern.
- Do not use raw types or unchecked casts as a way to bypass the generic contract; they can produce warnings and defer risks to runtime.

## 8. Complete runnable Java 21 program

Create the file **`CompilerPatternAnalysisDemo.java`**:

```java
public class CompilerPatternAnalysisDemo {
    sealed interface Shape permits Circle, Rectangle {}
    record Circle(double radius) implements Shape {}
    record Rectangle(double width, double height) implements Shape {}

    record Point(int x, int y) {}
    record LabelledPoint(String label, Point point) {}

    static String inspect(Object value) {
        if (value instanceof LabelledPoint(
                String label, Point(int x, int y))
                && x >= 0 && y >= 0) {
            return "Point " + label + "=(" + x + "," + y + ")";
        }

        if (value instanceof LabelledPoint point) {
            return "LabelledPoint chưa phù hợp";
        }

        return "Không phải LabelledPoint";
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case Circle(double r) when r > 0 ->
                    "Tròn hợp lệ: " + r;
            case Circle(double r) ->
                    "Tròn không hợp lệ: " + r;
            case Rectangle(double w, double h) when w > 0 && h > 0 ->
                    "Chữ nhật hợp lệ: " + (w * h);
            case Rectangle(double w, double h) ->
                    "Chữ nhật không hợp lệ";
            case null ->
                    "Không có hình";
        };
    }

    public static void main(String[] args) {
        System.out.println(inspect(
                new LabelledPoint("A", new Point(2, 3))));
        System.out.println(inspect(new LabelledPoint("B", null)));
        System.out.println(inspect("khác"));

        System.out.println(kind(new Circle(2)));
        System.out.println(kind(new Circle(0)));
        System.out.println(kind(new Rectangle(3, 4)));
        System.out.println(kind(new Rectangle(3, -1)));
        System.out.println(kind(null));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac CompilerPatternAnalysisDemo.java
java CompilerPatternAnalysisDemo
```

Output on standard output:

```text
Point A=(2,3)
LabelledPoint chưa phù hợp
Không phải LabelledPoint
Tròn hợp lệ: 2.0
Tròn không hợp lệ: 0.0
Chữ nhật hợp lệ: 12.0
Chữ nhật không hợp lệ
Không có hình
```

Analysis of what the compiler must check in this program:

1. `LabelledPoint(String label, Point(int x, int y))` must match the record structure: the first component is `String`; the second component is `Point`, which has two `int` components.
2. Variables `x` and `y` are in scope in the `&&` operands after the matched pattern and in the `if` body; the `>= 0` comparison is valid for `int`.
3. The subsequent `instanceof LabelledPoint point` branch is a separate test: a value can be a `LabelledPoint` while missing a nested component, such as `point == null` inside the record.
4. The `switch` selector has type `Shape`. The compiler sees that `Shape` is `sealed`, permitting only `Circle` and `Rectangle` in the declared hierarchy.
5. The `case ... when ...` branches appear before the unguarded branches of the same record, so they are not dominated by broader branches.
6. The unguarded `Circle` and `Rectangle` branches ensure every non-`null` case for both shapes has a branch; `case null` handles a `null` selector.

Analysis of runtime behavior:

- `LabelledPoint("A", Point(2, 3))` matches both the nested pattern and `x >= 0 && y >= 0`, returning `Point A=(2,3)`.
- `LabelledPoint("B", null)` does not match `Point(int x, int y)`, yet still matches the general type pattern `LabelledPoint point`.
- `"khác"` is not a `LabelledPoint`, so it returns the final message.
- `Circle(2)` has radius `2.0`, matching the guard `r > 0`; `Circle(0)` fails the guard but still matches the next `Circle` branch.
- `Rectangle(3, 4)` has two positive dimensions, giving area `12.0`; `Rectangle(3, -1)` fails the guard and selects the fallback branch.
- `null` is handled explicitly by `case null`.

The program does not depend on the runtime order of objects for the compiler to determine the types of pattern variables; type checking and exhaustiveness rules are applied directly from the program's type declarations.

## 9. Common errors detected by the compiler

| Case | What the compiler checks / reports | How to fix |
| --- | --- | --- |
| `String text` tested with `instanceof Integer number` | The type test is incompatible with the value's static type. | Test against a type compatible with the input's domain. |
| `Point(int x)` when `Point` has two components | Record pattern has the wrong number of components. | Provide all two component patterns in the exact order. |
| `Point(String x, String y)` for `int` components | Component patterns are type-incompatible. | Use `int` or `var` appropriately. |
| Using a pattern variable on the right-hand side of `\|\|` | The left-hand pattern might not have matched when the right-hand side is evaluated. | Use `&&` when there is a dependency, or extract a guard clause. |
| Using a pattern variable after a negated branch without `return` | Cannot prove the variable is bound on all paths. | Only use the variable where flow scoping permits. |
| Placing `case Object any` before `case String text` | The `String` branch is completely dominated by the earlier branch. | Place specific branches before general branches. |
| Having only `case Circle(...) when r > 0` for all `Circle` values | The guard does not cover non-positive radii; the switch may be non-exhaustive. | Add an unguarded `Circle` branch or appropriate cases. |
| Extracting a `String` from a `Box<?>` without checking | The generic type argument is not proven to be `String`. | Preserve the type parameter in the API or check the component type. |

The compiler **cannot** prove all program correctness: it does not guarantee that a radius is always positive, that a string is valid per business rules, that data is never `null`, or that called methods never throw exceptions. Those require runtime checks, data contracts, tests, and application code.

## 10. Self-check

Given the declarations:

```java
record Task(String title, int priority) {}
Object input = new Task("Fix", 3);
```

**Question 1:** Can the compiler determine the types of `title` and `priority` in the following pattern?

```java
if (input instanceof Task(var title, var priority)
        && priority >= 2) {
    System.out.println(title + ": ưu tiên");
}
```

**Answer:** Yes. `Task` declares component `title` as `String` and `priority` as `int`, so `var` is inferred accordingly. `priority` is used validly after `&&`. With the example data, it prints `Fix: ưu tiên`.

**Question 2:** What happens if `&&` is changed to `||` while still using `priority` on the right-hand side?

**Answer:** It will not compile due to pattern variable scoping: the right-hand side of `||` can execute when the record pattern did not match.

**Question 3:** If `Task` is made a permitted subtype of a sealed interface and a `switch` is used to classify it, is writing only `case Task(var title, var priority) when priority > 0` enough to cover all `Task` values?

**Answer:** No. The guard `priority > 0` can evaluate to false, so an additional branch is needed for the remaining `Task` values. In addition, the `switch` must cover any other permitted subtypes, and handle `null` if the problem needs to accept a `null` input.

**Key takeaway:** With pattern matching, the compiler checks **type and structural validity, the types and scopes of bound variables, dominance, and switch exhaustiveness**. Runtime decides **whether a concrete value matches the pattern and guard**. Distinguishing these two layers of checks helps you read `javac` error messages more accurately and write safe, maintainable Java 21 patterns.
