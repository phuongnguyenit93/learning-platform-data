# Ignoring unused components in record patterns

When using **record patterns** to deconstruct a `record`, a program often needs only a few of its components. For example, `record Point(int x, int y)` has two components, `x` and `y`, but an operation may only need `x`. Starting in **Java 22**, you can place an **unnamed pattern** `_` (underscore) at the position of an unused component. The pattern still matches the record's structure, but does not create a variable to access the ignored value.

## 1. Why ignore components?

Suppose you have the following record:

```java
record OrderLine(String productCode, int quantity, String warehouse) {}
```

When you want to get the quantity without using the product code or the warehouse, the typical way to write this in Java 21 is:

```java
// Illustrative snippet; 'value' is an already-declared Object variable.
if (value instanceof OrderLine(var unusedCode, var quantity, var unusedWarehouse)) {
    System.out.println(quantity);
}
```

The two names `unusedCode` and `unusedWarehouse` are still created even though they are never used. With Java 22 and later, you can express the intent more directly:

```java
// Illustrative snippet; requires Java 22+.
if (value instanceof OrderLine(_, var quantity, _)) {
    System.out.println(quantity);
}
```

Reading the pattern `OrderLine(_, var quantity, _)` from left to right:

| Position | Record component | Component pattern | Meaning |
| --- | --- | --- | --- |
| 1 | `productCode` (`String`) | `_` | Accepts the value at this position without creating a variable |
| 2 | `quantity` (`int`) | `var quantity` | Extracts the value into the variable `quantity` |
| 3 | `warehouse` (`String`) | `_` | Accepts the value at this position without creating a variable |

Key point: **ignoring a value does not mean omitting the component position in the syntax**. If a record has three components, the record pattern must have exactly three component patterns, even if all three are `_`.

## 2. Java versions and syntax

| Version | Record patterns | `_` to ignore components |
| --- | --- | --- |
| Java 17 | No finalized record patterns syntax yet | Not available |
| Java 21 | Standard feature, no preview needed | Available as a preview feature in JEP 443; requires enabling preview when compiling and running |
| Java 22 and later | Standard feature | Standard feature in JEP 456; no preview needed |

The complete examples in this article use **JDK 22+**. On **JDK 21** specifically, if you want to use `_` in a record pattern, you must compile with `javac --enable-preview --release 21` and run with `java --enable-preview`. If a project uses Java 21 without preview enabled, use named variables such as `var unusedY`. You cannot use `_` as a regular variable name as a substitute on Java 17/21.

## 3. Rules of the unnamed pattern `_`

- `_` in a record pattern's component list **matches any value** at that position, including `null`, and **does not declare a variable**. Multiple `_` characters can be used in the same pattern.
- You must keep the exact number of positions and the exact order of components from the `record` declaration. For example, `Point(var x, _)` is valid for `record Point(int x, int y)`, whereas `Point(var x)` is invalid.
- You can combine `_` with `var name`, explicit types such as `int x`, or nested record patterns, such as `Point(var x, _)` inside another record.
- `_` is only **a component pattern** in this case. You cannot replace the entire top-level pattern with `if (obj instanceof _)`. If you want to check the type of the outermost value, you still need an appropriate record or type pattern.
- You cannot read back an ignored value: `System.out.println(_)` is invalid. When you need to use or check that value later, give the variable a name directly in the pattern.

Example with nested positions:

```java
record Point(int x, int y) {}
record TaggedPoint(String label, Point point, String tag) {}

// Illustrative snippet: ignore label, y, and tag; keep only x.
if (obj instanceof TaggedPoint(_, Point(var x, _), _)) {
    System.out.println(x);
}
```

`TaggedPoint` has three components, and `Point` has two. The outer pattern uses all three positions; the inner `Point(var x, _)` pattern uses both. There is no implicit "drop the trailing components" syntax as in some other languages.

## 4. Complete example: reading one component and ignoring the rest

Save the following code to **`IgnoreRecordComponentsDemo.java`**:

```java
public class IgnoreRecordComponentsDemo {
    record Point(int x, int y) {}
    record NamedPoint(String name, Point point, String tag) {}

    static String describe(Object input) {
        return switch (input) {
            case NamedPoint(_, Point(var x, _), _) -> "x = " + x;
            case NamedPoint(_, _, _) -> "point = null";
            case null -> "input = null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
            new NamedPoint("A", new Point(3, 9), "red")));
        System.out.println(describe(
            new NamedPoint("B", null, null)));
        System.out.println(describe(null));
        System.out.println(describe("abc"));
    }
}
```

Using **JDK 22 or later**:

```bash
javac IgnoreRecordComponentsDemo.java
java IgnoreRecordComponentsDemo
```

Expected output:

```text
x = 3
point = null
input = null
other
```

Explanation of each branch:

1. `case NamedPoint(_, Point(var x, _), _)` only matches when `input` is a `NamedPoint` and the `point` component holds a non-`null` `Point`. It ignores `name`, `tag`, and `y`, while extracting `x = 3`.
2. `case NamedPoint(_, _, _)` receives a `NamedPoint` that did not match the previous branch. In this example, `point` has the declared type `Point`, so the remaining case is `point == null`. The other two `_` patterns still accept `null` values.
3. `case null` handles the case where the `input` object itself is `null`. A component-level `_` does not make an outer record pattern match a `null` object.
4. `default` handles values that are not of type `NamedPoint`, such as the string `"abc"`.

With real-world data, the `"point = null"` message in the second branch is only accurate when you know that the component's declared type is `Point` and the first branch has already covered every non-`null` `Point`.

## 5. Distinguishing "ignoring" from "checking a condition"

Suppose `record Parcel(String id, Object payload) {}`. The following two patterns **do not have the same meaning**:

```java
// Illustrative snippet used in 'instanceof' or a 'case' branch.
Parcel(var id, _)          // any payload, including null
Parcel(var id, String _)   // payload must match the String type pattern
```

The first pattern completely ignores the value of `payload`. The second pattern does not name `payload`, but still requires the object to match the `String` type; for a component declared as `Object`, an `Integer` or `null` will not match the second branch.

Similarly, if the business logic needs to verify `quantity > 0`, you **cannot** replace `var quantity` with `_` and then use `quantity` in the condition. Extract the exact variable you need to check:

```java
// Illustrative snippet; 'value' is already declared.
if (value instanceof OrderLine(_, var quantity, _) && quantity > 0) {
    System.out.println("Valid quantity: " + quantity);
}
```

In a `switch`, you can check an extracted variable via `when`, such as `case Point(var x, _) when x >= 0 -> ...`. Conversely, a component that only uses `_` provides no name to reference in a guard or branch body.

## 6. `null`, type checking, and accessor execution

You need to distinguish between two levels of matching:

- **Outer object:** `null instanceof Point(var x, _)` is `false`, because the input value itself is not a `Point` object. For a `switch` that handles `null`, use `case null` where appropriate.
- **Inner component:** if the input is a non-`null` record, `_` accepts a component that holds `null`. However, a nested record pattern such as `Point(var x, _)` still requires that component to actually be a `Point` object to continue deconstructing it.

Ignoring with `_` means **not creating a name binding** for the component; it does not make the component disappear from the record or alter its structure. The record-pattern matching process still follows the semantics of accessing components and checking matches; you should not rely on `_` to guarantee that a component's accessor will not be invoked or to optimize performance.

## 7. Common mistakes

| Code | Problem | Fix |
| --- | --- | --- |
| `Point(var x)` with `record Point(int x, int y)` | Missing a component position | `Point(var x, _)` |
| `if (obj instanceof _)` | `_` is invalid as a top-level pattern | Use `obj instanceof Point(_, _)` or an appropriate type pattern |
| `Point(var x, _)` followed by accessing `_` in the `if` body | There is no variable named `_` to reference | Use `Point(var x, var y)` if `y` is needed |
| Compiling code that uses `_` on Java 21 without enabling preview | Java 21 only supports this feature in preview mode | Enable preview on JDK 21 specifically, or use JDK 22+ |
| Using `_` to ignore an entire nested record level even though inner type/value checks are needed | Does not perform checks inside that level | Write a nested pattern, e.g. `Point(_, var y)` |
| Assuming `_` only matches when the component is non-`null` | Misunderstanding null-matching behavior | If type/non-`null` checks are needed, use an appropriate pattern and condition |

Do not invent names like `ignored1` and `ignored2` just to satisfy the component count when the project supports Java 22+: `_` makes it clear to readers which components do not participate in the computation. However, naming a variable is still the right choice when that value is actually used to produce a result or validate data.

## 8. Self-practice

Given the following two records:

```java
record Payment(String id, long amount, String currency, boolean refunded) {}
record Wrapper(String label, Payment payment) {}
```

**Exercise 1.** Write a record pattern that extracts `amount` from `Payment`, ignoring `id`, `currency`, and `refunded`.

**Answer:** `Payment(_, var amount, _, _)`.

**Exercise 2.** Write a record pattern for `Wrapper`, ignoring `label` and all components of `Payment` except `amount`.

**Answer:** `Wrapper(_, Payment(_, var amount, _, _))`. The pattern only matches when `payment` is non-`null` and of type `Payment`.

**Exercise 3.** Can `Payment(_, var amount, _, _)` be shortened to `Payment(_, var amount)`?

**Answer:** No. `Payment` has four components, so the record pattern must also provide exactly four component patterns.

## 9. Key takeaways and references

- To ignore a component in a record pattern on **Java 22+**, write `_` at that component's **exact position**.
- To use a component, bind a name with `var name` or an appropriate type pattern.
- `_` matches `null` as well at the component level and does not declare a variable; it does not change the number of components, does not replace a top-level pattern, and is not a technique for skipping accessor invocation.
- Java 21 already supports stable record patterns, but `_` is only in preview; choose the syntax according to your project's JDK version and compiler configuration.

Official documentation:
- [Oracle — Record Patterns (Java 21)](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Oracle — Unnamed Patterns and Variables (Java 21, preview)](https://docs.oracle.com/en/java/javase/21/language/unnamed-variables-and-patterns.html).
- [Oracle — Java SE 22 Language Changes](https://docs.oracle.com/en/java/javase/22/language/java-language-changes.html).
- [Java Language Specification — Unnamed Variables and Patterns (Java 22)](https://docs.oracle.com/en/java/javase/22/docs/specs/unnamed-jls.html).