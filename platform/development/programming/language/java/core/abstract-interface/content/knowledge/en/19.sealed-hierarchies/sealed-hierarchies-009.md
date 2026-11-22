# Pattern matching switch and exhaustiveness of sealed hierarchies

Java 21 and later allow using **pattern matching in `switch`** to check the type and extract data from an object directly in each branch. When the type being examined is a **sealed hierarchy** (a closed class/interface hierarchy), the compiler can check whether the branches cover every valid type in the hierarchy. This helps write safer `switch` expressions and exposes cases that need to be handled when the data model changes.

Two ideas work together:

- **Pattern matching switch** selects a branch based on the type or structure of a value, and can bind a name to the matched data.
- **Sealed type** restricts which classes or interfaces are allowed to directly extend or implement the parent type. The subtypes are declared in `permits`, or inferred when they reside in the same source file according to Java's rules.

## 1. Pattern matching in switch

With traditional `switch`, labels are typically constants such as `case 1`, enum values, or strings. Pattern matching allows labels to describe the type of an object:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Chuỗi dài " + text.length();
        case Integer number -> "Số nguyên " + number;
        case null -> "Giá trị null";
        default -> "Kiểu khác";
    };
}
~~~

When the value is a `String`, the first branch matches and the pattern variable `text` has type `String` inside that branch. Similarly, the `Integer` branch provides the variable `number`. There is no need to check manually with `instanceof` and then cast.

The example above is an illustrative snippet, not a standalone program. Pattern matching switch was finalized in **Java 21**. If you use an older Java version, this syntax may not be supported yet or may require preview flags in earlier preview releases.

### Switch expressions and switch statements

A `switch` expression produces a value and is often used in an assignment or a `return` statement:

~~~java
String label = switch (status) {
    case ACTIVE -> "Đang hoạt động";
    case INACTIVE -> "Đã dừng";
};
~~~

A `switch` statement performs an action in each branch. Java requires `switch` expressions to be exhaustive, meaning every possible value must match a branch. A `switch` statement that uses pattern labels must also be exhaustive. For other traditional forms of `switch`, whether a default branch is needed depends on the type of switch and the processing purpose.

## 2. Which types does a sealed hierarchy close?

A type declared as `sealed` restricts the direct subtypes permitted to extend or implement it. For example:

~~~java
sealed interface Shape permits Circle, Rectangle, Triangle {}

record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}
record Triangle(double base, double height) implements Shape {}
~~~

This is an illustrative structure. Within the same Java file, the subtypes can be declared alongside the parent type. In real programs, these types can also be organized into separate files following the rules for sealed types.

A permitted direct subtype of a sealed class/interface must declare one of three modifiers:

- `final`: does not allow further inheritance.
- `sealed`: further restricts the list of its direct subtypes.
- `non-sealed`: reopens that branch so that other types can extend or implement it.

Records are `final` by default, so they are suitable as leaf branches of a sealed hierarchy. If a sub-branch is `sealed`, the compiler can continue examining that branch's sub-hierarchy. If a branch is `non-sealed`, there may be new subtypes that the current source code does not list; a pattern matching that branch type itself can cover all of its subtypes.

A sealed hierarchy creates a set of types that can be analyzed at compile time. This is the foundation for the compiler to verify the exhaustiveness of a pattern switch.

## 3. Exhaustiveness of switch over a sealed hierarchy

Suppose `Shape` permits only three direct subtypes: `Circle`, `Rectangle`, and `Triangle`. When handling all three types in a switch expression, `default` may not be needed:

~~~java
static double area(Shape shape) {
    return switch (shape) {
        case Circle c -> Math.PI * c.radius() * c.radius();
        case Rectangle r -> r.width() * r.height();
        case Triangle t -> rBaseArea(t.base(), t.height());
    };
}

static double rBaseArea(double base, double height) {
    return base * height / 2.0;
}
~~~

Each branch handles one permitted subtype, so the switch expression is exhaustive. In this example, `rBaseArea` merely extracts the triangle area calculation into a small function to clarify how to write it; the complete program below uses that formula directly.

If you omit the `Triangle` branch, the compiler reports an error because it cannot prove that the switch expression returns a value for every case of `Shape`. The error is caught at compile time instead of waiting until data of the missing type appears in production.

### How does the compiler determine exhaustiveness?

For a sealed type, the compiler examines its permitted subtypes:

1. If a subtype is `final`, it is a closed branch.
2. If a subtype is itself `sealed`, the compiler can examine its permitted subtypes.
3. If a subtype is `non-sealed`, the hierarchy is open at that branch. A pattern matching the branch's type can cover its subclasses; listing only some known subclasses is not enough to prove exhaustiveness.
4. Every possible value of the selector type must be covered by at least one applicable label.

A parent-type pattern can cover its subtypes as well. For example, the branch `case Shape s` matches any non-null object whose type is compatible with `Shape`; however, placing such a broad branch before `Circle`, `Rectangle`, or `Triangle` branches makes the subsequent branches unreachable and causes a dominance error.

## 4. Complete example with Java 21+

The example below uses a sealed interface, records, record patterns, `when` guards, and switch expressions. Three records represent three shapes; both processing methods cover the hierarchy exhaustively without needing `default`.

Save the entire contents to the file `SealedSwitchDemo.java`:

~~~java
import java.util.List;
import java.util.Locale;

public class SealedSwitchDemo {
    sealed interface Shape permits Circle, Rectangle, Triangle {}

    record Circle(double radius) implements Shape {}
    record Rectangle(double width, double height) implements Shape {}
    record Triangle(double base, double height) implements Shape {}

    static double area(Shape shape) {
        return switch (shape) {
            case Circle(double radius) -> Math.PI * radius * radius;
            case Rectangle(double width, double height) -> width * height;
            case Triangle(double base, double height) -> base * height / 2.0;
        };
    }

    static String kind(Shape shape) {
        return switch (shape) {
            case Circle(double radius) when radius == 0.0 -> "Đường tròn suy biến";
            case Circle(double radius) -> "Đường tròn";
            case Rectangle(double width, double height) when width == height -> "Hình vuông";
            case Rectangle(double width, double height) -> "Hình chữ nhật";
            case Triangle(double base, double height) -> "Tam giác";
        };
    }

    public static void main(String[] args) {
        List<Shape> shapes = List.of(
            new Circle(2.0),
            new Rectangle(3.0, 3.0),
            new Triangle(4.0, 5.0)
        );

        for (Shape shape : shapes) {
            System.out.printf(Locale.ROOT, "%s: %.2f%n", kind(shape), area(shape));
        }
    }
}
~~~

Compile and run using JDK 21 or later:

~~~text
javac SealedSwitchDemo.java
java SealedSwitchDemo
~~~

Expected output:

~~~text
Đường tròn: 12.57
Hình vuông: 9.00
Tam giác: 10.00
~~~

Explanation:

- `Shape` restricts the permitted subtypes to three records.
- Record patterns such as `Circle(double radius)` both check the type and extract the `radius` component from the record.
- `area` computes the area based on the shape type and must handle all three types.
- In `kind`, labels with a `when` guard check special cases first. The subsequent unguarded `Circle(double radius)` label handles the remaining circles. Similarly, a rectangle whose width equals its height is described as a square before checking a regular rectangle.
- Types nested inside a public class can reside in the same file; the file name must match the `public SealedSwitchDemo` class.

## 5. Guards, dominance, and label ordering

A `when` guard adds a condition to a pattern. It is useful when the type already matches, but behavior needs to be distinguished based on the data:

~~~java
return switch (shape) {
    case Rectangle(double w, double h) when w == h -> "Hình vuông";
    case Rectangle(double w, double h) -> "Hình chữ nhật";
    case Circle(double r) -> "Hình tròn";
    case Triangle(double b, double h) -> "Tam giác";
};
~~~

The snippet above assumes `shape` has type `Shape` as in the example. The guarded rectangle branch must appear before the general branch for `Rectangle`; if the order is reversed, the general branch will catch every rectangle and the guarded branch will never execute.

**Dominance** is a situation where a preceding label already covers all values that a subsequent label could match. For example, an unguarded `Shape`-type label placed before subtype labels causes the subtype labels to be dominated. The compiler detects this case to prevent dead branches.

Practical guidelines:

- Place narrower or more specifically conditioned branches before broader ones.
- After a guarded branch, an unguarded branch is usually needed to handle the remaining values of the same type.
- Do not add `default` just to mask a missing-branch error if the goal is for the compiler to detect that the sealed hierarchy has changed.
- Use guards only for business-meaningful conditions; avoid duplicating complex logic across multiple labels.

## 6. Null values and the default branch

Exhaustiveness of a sealed hierarchy describes objects belonging to the types in the hierarchy. It does not automatically mean that `null` is handled. With a pattern switch, if the selector is `null` and there is no `case null` label, the switch throws `NullPointerException`.

If `null` is a valid input, handle it explicitly:

~~~java
static String describe(Shape shape) {
    return switch (shape) {
        case null -> "Không có hình";
        case Circle(double radius) -> "Hình tròn";
        case Rectangle(double width, double height) -> "Hình chữ nhật";
        case Triangle(double base, double height) -> "Tam giác";
    };
}
~~~

Here, `case null` handles the null value separately; the remaining labels still exhaustively cover the subtypes of `Shape`.

`default` is useful when an intentional fallback branch is needed, such as handling unknown types in an open API. However, with a sealed hierarchy, a `default` branch can prevent the compiler from reporting a missing new type when the `permits` list changes. If you want to leverage safety as the hierarchy evolves, list the specific branches and let the compiler check them.

If components are compiled separately and a version of the sealed hierarchy changes without recompiling the switch code, the exhaustiveness assumption may no longer hold at runtime. With a switch expression, a case where no branch matches can lead to `MatchException`. Related modules should be recompiled when changing the list of permitted subtypes.

## 7. When to use and common pitfalls

Use pattern matching switch with a sealed hierarchy when:

- A parent type represents a finite set of business cases, such as order states, AST expressions, protocol messages, or geometric shapes.
- Each subtype requires a dedicated handling branch.
- You want data model changes to cause the compiler to point out the places that need updating.
- You need to extract record components without writing multiple `instanceof` statements and casts.

Common pitfalls:

1. **Omitting a subtype:** an incomplete switch expression will not compile. Add the missing branch or an intentional fallback branch.
2. **Using `default` too early:** the code still compiles when a new subtype is added, but the business logic may not have been updated yet. Prefer listing known subtypes when the hierarchy is truly closed.
3. **Confusing sealed with final:** `sealed` does not mean there are no subclasses; it means the direct subtypes are controlled by the permitted list. A subtype can be `sealed`, `final`, or `non-sealed`.
4. **Forgetting a `non-sealed` open branch:** if you only list known subclasses of an open branch, new types may not be covered. Use a pattern for the open branch type itself or default when justified.
5. **Confusing null with a subtype:** null does not match a type pattern. If null needs to be supported, add `case null` and clearly decide the behavior.
6. **Ordering labels incorrectly:** a general branch can dominate a specific branch that follows it. Place specific patterns and guards before broad patterns.
7. **Compiling with a JDK that is too old:** the examples using record patterns and pattern matching switch require JDK 21 or later. Check `java -version` and `javac -version` to ensure the compiler matches.

When adding a new subtype to a sealed hierarchy, find the switches handling the parent type, update the necessary branches, and then recompile and rerun the tests. This turns data model changes into compile-time errors that can be caught early, rather than letting a new case silently fall into inappropriate logic.
