# Naming Component Variables When Deconstructing Records in Java

A **record pattern** allows checking the record type of a value and then **deconstructing its components into named variables** for immediate use. Choosing good names for those variables determines whether the code is easy to understand, especially when a record contains multiple components of the same type or has nested records.

In the context of **Java Core Pattern Matching → Deconstruction**, this article explains how to name **component pattern variables**, use `var` or explicit types, variable scoping, naming guidelines, and common mistakes. Record patterns have been a standard feature since **Java 21** (JEP 440), without requiring preview flags in Java 21 or later.

## 1. Distinguishing Record Component Names from Component Variable Names

Consider the record declaration:

```java
record Point(int x, int y) {}
```

Here, `x` and `y` are **record components**. They define the record's data and generate the `x()` and `y()` accessors. When deconstructing a `Point`, we can choose new variable names:

```java
// Illustrative snippet: 'input' is an already-declared Object.
if (input instanceof Point(var horizontal, var vertical)) {
    System.out.println(horizontal + ", " + vertical);
}
```

In `Point(var horizontal, var vertical)`:

- `Point` is the record type to check.
- `var horizontal` is the first **component pattern**, binding the `x` component into a **pattern variable** named `horizontal`.
- `var vertical` is the second component pattern, binding the `y` component into a pattern variable named `vertical`.
- The names `horizontal` and `vertical` **do not have to match** the component names `x` and `y`. Mapping is based on the **order** in which components are declared, not on variable names.
- The record still retains its `x()` and `y()` accessors; naming variables in a pattern does not change the structure or component names of the record.

Another example using names based on usage context:

```java
record Range(int startInclusive, int endExclusive) {}

// Snippet: 'candidate' has type Object.
if (candidate instanceof Range(var from, var to)) {
    System.out.println("[" + from + ", " + to + ")");
}
```

Here `from` binds `startInclusive` and `to` binds `endExclusive`. Because the variables are used in the context of forming a range, we choose short yet readable names; however, avoid choosing names that mislead readers about inclusive/exclusive bounds.

## 2. Syntax: `var` or Explicit Types

There are two common ways to declare variable names in a record pattern:

```java
record Point(int x, int y) {}

// Option 1: var — the compiler infers the variable type from the component.
if (input instanceof Point(var px, var py)) {
    int sum = px + py;
}

// Option 2: explicit type.
if (input instanceof Point(int px, int py)) {
    int sum = px + py;
}
```

Both examples are snippets where an `input` variable of type `Object` has already been declared. For `Point(int x, int y)`, `px` and `py` both have type `int` in either form.

**Choose `var` when** the component's type is already clear from the record name, the context is concise, and no narrower type check is needed. **Choose an explicit type when** you need to emphasize or check a specific type for the component.

Example of a component declared with a broader type than the type you want to handle:

```java
record Message(Object content) {}

// Snippet; 'input' has type Object.
if (input instanceof Message(String text)) {
    System.out.println(text.toUpperCase());
}
```

`Message(String text)` matches only when `content` holds a non-`null` `String` object. `text` has type `String`, so calling `toUpperCase()` is permitted by the compiler. If you use `Message(var text)` instead, `text` is inferred as `Object`; you cannot call `toUpperCase()` directly without checking or casting to the appropriate type first.

**Note:** `var` in a record pattern is syntax for **declaring a pattern variable**, not a place to omit or freely rearrange components. There must be exactly one component pattern for each position to be deconstructed.

## 3. Naming by Order and by Role

In the record:

```java
record Transfer(String sender, String receiver, long amount) {}
```

There are three positions, in order: `sender`, `receiver`, `amount`. The following pattern is valid:

```java
// Snippet; 'item' has type Object.
if (item instanceof Transfer(var fromAccount, var toAccount, var cents)) {
    System.out.println(fromAccount + " -> " + toAccount + ": " + cents);
}
```

The variables are bound **positionally**: `fromAccount ← sender`, `toAccount ← receiver`, `cents ← amount`. There is no name-based binding mechanism. If you swap the positions of `fromAccount` and `toAccount`, the compiler will still accept it because both components are `String`, but the business meaning will be reversed. Therefore:

- Keep the exact order from the `record` declaration.
- Use short names when expressions are simple (`x`, `y`, `id`), and role-descriptive names when multiple values share the same type (`fromAccount`, `toAccount`).
- When the component name is already clear and there is no new context, use names close to the component names (`sender`, `receiver`, `amount`) for easy lookup.
- Avoid names that misrepresent units (`cents` should only be used if `amount` is actually stored in cents; if the unit is unknown, use `amount` or `amountValue`).

A pattern for a record with three components must have exactly three component patterns; **you cannot write only two variables to skip the third component**.

## 4. Naming in Nested Record Patterns

Consider two records:

```java
record Point(int x, int y) {}
record Shipment(String trackingCode, Point destination, int boxes) {}
```

You can deconstruct both `Shipment` and `Point` in a single expression:

```java
// Snippet; 'input' has type Object.
if (input instanceof Shipment(var tracking, Point(var destX, var destY),
                              var boxCount)) {
    System.out.println(tracking + ": " + destX + ", " + destY
            + "; boxes=" + boxCount);
}
```

Variable names and data sources:

| Pattern variable | Data source | Inferred type |
| --- | --- | --- |
| `tracking` | `Shipment.trackingCode` | `String` |
| `destX` | `Shipment.destination.x` | `int` |
| `destY` | `Shipment.destination.y` | `int` |
| `boxCount` | `Shipment.boxes` | `int` |

Notice that `destination` is a component of `Shipment`, but in this pattern it is further deconstructed with `Point(var destX, var destY)`, so **no `destination` variable is automatically created**. If you need to reference the entire `Point` object, use a separate pattern variable at the second position:

```java
// Alternative snippet: captures the destination object without deconstructing x/y.
if (input instanceof Shipment(var tracking, var destination, var boxCount)) {
    if (destination != null) {
        System.out.println(destination.x() + ", " + destination.y());
    }
}
```

Both approaches are useful. Which variable naming you choose depends on whether subsequent steps need **the whole record object** or only **some of its inner components**.

## 5. Scope of Component Pattern Variables

Pattern variables are governed by **flow scoping** (the control flow that proves the pattern matched).

### In `if` and the `&&` Operator

```java
record Point(int x, int y) {}

// Snippet; 'input' is Object.
if (input instanceof Point(var px, var py) && px >= 0 && py >= 0) {
    System.out.println("First quadrant or axes: " + px + ", " + py);
}
```

When evaluating the right-hand side of `&&`, the pattern has already matched, so `px` and `py` are in scope. If you replace `&&` with `||` and reference `px` on the right-hand side, the compiler cannot guarantee the pattern matched; that results in a scoping error.

Inside the `if` branch, you can use the bound variables. After a normal `if` block, do not assume they remain in scope: when the check does not match, they are not created.

### In `switch` and `when`

```java
// Snippet; 'input' is Object.
String result = switch (input) {
    case Point(var px, var py) when px == py -> "Diagonal: " + px;
    case Point(var px, var py) -> "Point: " + px + ", " + py;
    case null -> "No point";
    default -> "Other";
};
```

- `px` and `py` exist within **the matching case branch** and can be used in the `when` guard.
- Two separate `case` branches can use the same names `px` and `py` because each branch has its own scope.
- The first branch matches a `Point` satisfying `px == py`; the next branch handles remaining `Point` values.
- `case null` handles a `null` selector; the record pattern `Point(...)` itself does not match a `null` object.

A pattern variable name in one branch does not become a shared variable across all other branches.

## 6. Complete Java 21+ Example: Variable Names in Deconstruction

Create the file **`ComponentVariableNamesDemo.java`**:

```java
public class ComponentVariableNamesDemo {
    record Point(int x, int y) {}
    record Shipment(String trackingCode, Point destination, int boxes) {}
    record Message(Object content) {}

    static String describe(Object input) {
        return switch (input) {
            case Shipment(var code, Point(var destX, var destY), var count)
                    when count >= 2 ->
                    code + ": " + destX + "," + destY + " (" + count + " boxes)";

            case Shipment(var code, Point(var x, var y), var count) ->
                    code + ": " + x + "," + y + " (" + count + " box)";

            case Shipment(var code, var destination, var count) ->
                    code + ": destination missing";

            case Message(String text) ->
                    "message: " + text.toUpperCase();

            case Message(var value) ->
                    "message content: " + value;

            case null -> "null input";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(
                new Shipment("S-10", new Point(12, 34), 3)));
        System.out.println(describe(
                new Shipment("S-11", new Point(5, 8), 1)));
        System.out.println(describe(
                new Shipment("S-12", null, 2)));
        System.out.println(describe(new Message("fragile")));
        System.out.println(describe(new Message(404)));
        System.out.println(describe(new Message(null)));
        System.out.println(describe(null));
        System.out.println(describe(42));
    }
}
```

Compile and run with **JDK 21 or later**:

```bash
javac ComponentVariableNamesDemo.java
java ComponentVariableNamesDemo
```

Output:

```text
S-10: 12,34 (3 boxes)
S-11: 5,8 (1 box)
S-12: destination missing
message: FRAGILE
message content: 404
message content: null
null input
other
```

Explanation of the matching flow:

1. `Shipment("S-10", Point(12, 34), 3)` matches the first branch; `destX = 12`, `destY = 34`, `count = 3`, and the condition `count >= 2` is true.
2. `Shipment("S-11", Point(5, 8), 1)` does not pass the first guard but matches the second branch; the names `x` and `y` in this branch are **different** variables from `destX` and `destY` in the first branch.
3. `Shipment("S-12", null, 2)` does not match the two nested record patterns, because `Point(...)` does not match a `destination == null` component. The third branch uses `var destination` and receives `null`.
4. For `Message("fragile")`, `Message(String text)` checks that the component has type `String` and creates the variable `text`; for `404` or `null`, the `Message(var value)` branch receives the value without requiring type `String`.
5. `case null` handles a `null` input; `default` handles the integer `42` because it is neither a `Shipment` nor a `Message`.

This example shows that **variable names are chosen locally to explain their role**: `code`, `destX`, `destY`, `count`, or `text`. None of these names change how Java stores the record components.

## 7. Naming Rules and Edge Cases

### Every Variable Needs a Valid, Unique Name Within the Same Pattern

Within a single record pattern, you cannot declare two pattern variables with **the same name**:

```java
record Point(int x, int y) {}

// INVALID: duplicate name x in the same record pattern.
if (input instanceof Point(var x, var x)) {
    System.out.println(x);
}
```

Use `Point(var x, var y)` or distinct names like `Point(var left, var right)`. A pattern variable also cannot redeclare the name of an existing local variable in an overlapping scope.

Names must follow Java's identifier rules; avoid keywords, confusing names, and overly generic names like `a`, `b` in complex situations.

### Components Can Be `null`

`var` captures the value and inferred static type; it **does not automatically guarantee non-`null`** for reference-type components:

```java
record User(String displayName) {}

// Snippet; 'input' has type Object.
if (input instanceof User(var name)) {
    String shown = name == null ? "(unnamed)" : name;
    System.out.println(shown);
}
```

If the component is primitive `int`, `var quantity` has type `int`, so `quantity == null` is not possible. If the component is `String`, the variable has type `String` but can still hold `null`, depending on the actual data.

### Pattern Variables Differ from `record component` Names

Naming the variable extracted from `User.displayName` as `userName` **does not change** the accessor to `userName()`. Given a `User user`, the accessor is still `user.displayName()`. A pattern variable is only a local name bound upon matching; that name does not become a field, accessor, or new member of the record.

### What If You Don't Need a Component?

If you need to **ignore** a component, the appropriate syntax depends on the Java version:

```java
record Point(int x, int y) {}

// Java 21: use a name indicating the value is unused.
if (input instanceof Point(var x, var ignoredY)) {
    System.out.println(x);
}

// Java 22+: unnamed pattern '_' is a standard feature.
if (input instanceof Point(var x, _)) {
    System.out.println(x);
}
```

These two snippets are **independent illustrations for different Java versions**, not code that compiles together on Java 21. Java 21 only supports `_` as a preview feature under JEP 443; starting in Java 22, `_` is a standard feature under JEP 456. Unlike `var ignoredY`, `_` **does not declare a named variable to access**.

When you still need to use the component, give it a meaningful name. Do not use `_` and then try to reference the ignored value.

## 8. Common Mistakes

| Situation | Why it is wrong or misleading | How to fix |
| --- | --- | --- |
| `Point(var y, var x)` while treating `x` as the first coordinate | Binding is positional; swapped names cause confusion | `Point(var x, var y)` if you want to preserve original component meaning |
| `Point(var x)` for `record Point(int x, int y)` | Missing a component pattern | `Point(var x, var y)` or `Point(var x, _)` on Java 22+ |
| `Point(var x, var x)` | Duplicate name in the same pattern | Use two distinct names |
| Referencing `x` after `if (obj instanceof Point(var x, var y))` without guaranteed match | Flow scoping does not guarantee `x` exists at that point | Use `x` inside the matching branch, or restructure the condition |
| Calling `text.toUpperCase()` from `Message(var text)` when the component is declared as `Object` | `text` has type `Object`, which lacks that method | Use `Message(String text)` or perform an explicit type check |
| Assuming `var name` guarantees a reference value is non-`null` | `var` only binds the value; it does not check for `null` | Check `name != null` before calling methods |
| Using `_` in Java 21 code without enabling preview | Unnamed patterns are only standard from Java 22 onward | Use a name like `ignoredY` on Java 21 or use JDK 22+ |
| Renaming a pattern variable and calling the accessor with the new name | Record component names do not change | Call the accessor defined in the record declaration |

## 9. Practice Exercises

Given three records:

```java
record Dimensions(int width, int height) {}
record Product(String sku, Dimensions size, long priceInCents) {}
record Reply(Object payload) {}
```

**Exercise 1.** Given `Object input`, write a pattern that extracts `width` and `height` from `Dimensions` and names them `w` and `h`. What types do both have?

**Answer:**

```java
if (input instanceof Dimensions(var w, var h)) {
    System.out.println(w * h);
}
```

Both `w` and `h` have type `int`.

**Exercise 2.** Write a nested pattern for `Product` to extract `sku` as `productCode`, `size.width` as `w`, `size.height` as `h`, and `priceInCents` as `price`.

**Answer:**

```java
if (input instanceof Product(var productCode,
                             Dimensions(var w, var h), var price)) {
    System.out.println(productCode + ": " + w + "x" + h + " @ " + price);
}
```

`productCode` has type `String`, `w` and `h` have type `int`, and `price` has type `long`. The nested pattern does not match if `Product.size` is `null`.

**Exercise 3.** Given `Reply(Object payload)`, how do you match when `payload` is actually a `String` and create a variable `text` of type `String`?

**Answer:** `if (input instanceof Reply(String text)) { ... }`. `Reply(var text)` only infers `text` as `Object`.

**Exercise 4.** Should you name the second variable `height` in `Dimensions(var width, var height)` if subsequent code only uses `width`?

**Answer:** Naming it `height` is still valid and readable on Java 21. If running on Java 22+ and the second value is truly unused, you can write `Dimensions(var width, _)` to avoid creating an unused variable. You must keep both component positions.

## 10. Key Takeaways

- `Point(var left, var right)` creates the **component pattern variables** `left` and `right`. Variable names are local to the pattern and do not need to match the original component names.
- The **order** of record components determines which value is bound; choose clear names to avoid mixing up components of the same type.
- `var` lets the compiler infer the type from the record declaration; an explicit type such as `Message(String text)` can also check the runtime type of the component.
- Pattern variables can only be used where control flow guarantees the pattern matched. In `switch`, each branch has its own variable scope; in `if`, variables can be used on the right-hand side of `&&` and inside the matching branch.
- For nested records, place names at the appropriate deconstruction level; a `null` component can prevent a nested pattern from matching.
- Record patterns have been stable since **Java 21**; the unnamed pattern `_` has been a standard feature since **Java 22**.

Official documentation: [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle — Record Patterns (Java 21)](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JEP 456 — Unnamed Variables and Patterns](https://openjdk.org/jeps/456).
