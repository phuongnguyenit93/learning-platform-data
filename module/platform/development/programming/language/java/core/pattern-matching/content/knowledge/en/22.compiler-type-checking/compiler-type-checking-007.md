# Redundant Casts After Pattern Matching in Java: How to Identify and Remove Them Properly

## 1. The problem: type already checked, why still cast?

Before Java supported **pattern matching for `instanceof`**, the familiar way to access members of a subtype was to **check the type and then perform an explicit cast**:

```java
static String oldStyle(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        return text.strip().toUpperCase(java.util.Locale.ROOT);
    }
    return "Không phải chuỗi";
}
```

Since Java 16, **type patterns** allow combining the type check and the declaration of a properly typed variable in a single step:

```java
static String modernStyle(Object value) {
    if (value instanceof String text) {
        return text.strip().toUpperCase(java.util.Locale.ROOT);
    }
    return "Không phải chuỗi";
}
```

**`text` already has static type `String`.** Therefore, there is no need to write `(String) text`, nor is there any need to declare `String text = (String) value` inside the matching branch. The compiler knows the pattern has matched and allows calling `String` methods directly through the variable `text`.

However, we should distinguish between two cases:

- **Truly redundant cast:** casting from an expression that already has the desired type, such as `(String) text` when `text` is a `String`.
- **Cast replaceable by a pattern variable:** `(String) value` inside the `value instanceof String text` branch. Here, `value` **still has static type `Object`**. The cast on `value` may be needed for that specific expression, but it is better to use `text`, which has already been checked and bound.

Not every cast that appears "after a pattern match" is wrong. Some casts still **change a required static type**, **narrow to a deeper subtype**, **perform a numeric conversion**, or **select a different overload**. This lesson covers how to recognize those differences so you can remove casts properly without changing behavior.

### Java versions

- **Pattern matching for `instanceof`** (JEP 394): standard since **Java 16**.
- **Record patterns** (JEP 440) and **pattern matching for `switch`** (JEP 441): standard since **Java 21**.
- The complete program examples use **JDK 21+**, without needing `--enable-preview`. Java 17 can run examples that only use `instanceof String text`, but cannot use stable record patterns or pattern `switch` as shown in this lesson.

## 2. Understanding the compiler: static type of expressions and pattern success

Consider:

```java
Object value = "Java";

if (value instanceof String text) {
    System.out.println(text.length());
    // System.out.println(value.length()); // Does NOT compile.
}
```

In the matching branch:

- `value` is still **declared** as `Object`. The actual object it references is a `String`, but that does not automatically change the static type of the variable `value` to `String`.
- `text` is a **pattern variable** with static type `String`; the compiler knows `value` matches `String` before allowing `text` to be used.
- `text.length()` is valid because `String` declares the `length()` method.
- `value.length()` is invalid because the static type `Object` does not declare `length()`.

From this, compare the three lines:

```java
if (value instanceof String text) {
    int a = text.length();           // RECOMMENDED: use the pattern variable.
    int b = ((String) value).length(); // Works, but repeats the check's intent.
    int c = ((String) text).length();  // Redundant String -> String cast.
}
```

Line `b` still requires the cast syntax **if you insist on calling `length()` on `value`**, but the equivalent result can be achieved more simply with `text.length()`. Line `c` performs no useful type change because `text` is already a `String`.

**Practical rule:** After a pattern binds a variable, **use the pattern variable instead of continuing to cast the input object**. Do not mechanically delete the cast without switching the reference to the properly typed variable.

### Pattern matching is not the same as a runtime cast

A pattern checks a type condition and binds a variable within a valid scope. You do not have to write the cast yourself; the compiler performs the appropriate checks and bindings according to Java semantics. That does not mean any Java value can become the desired subtype: if the object is incompatible, the pattern **does not match**, rather than converting the data.

For example, `"42"` does not match `Integer i`. To convert a string to an integer, you must use parsing such as `Integer.parseInt`, not remove or add a cast.

## 3. Pattern variables have flow-determined scope

A cast can be removed when the pattern variable **is in scope** and already has the appropriate type. In Java, the scope of a pattern variable depends on **control flow** (flow scoping), not just curly braces.

### 3.1. Inside a matching `if` branch

```java
static int lengthOrMinusOne(Object value) {
    if (value instanceof String text) {
        return text.length();
    }
    return -1;
}
```

If `value` is not a `String` or is `null`, `instanceof` evaluates to false; the `if` body does not execute. The variable `text` cannot be used on the failure path.

Old style:

```java
if (value instanceof String) {
    return ((String) value).length();
}
```

New style:

```java
if (value instanceof String text) {
    return text.length();
}
```

Both return the expected result for a `String` object, but the new style eliminates the repeated cast and makes the intent clearer.

### 3.2. Conditions joined with `&&`

```java
if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 3) {
    System.out.println(text.strip());
}
```

The `&&` operator uses **short-circuiting**: the right-hand side is evaluated only when the left-hand side is true. Therefore, `text` is already bound when the compiler needs to check `text.isBlank()` or `text.length()`.

Do not write:

```java
// Does NOT compile: the right-hand side of || can run when the pattern is false.
if (value instanceof String text || text.isEmpty()) {
    System.out.println("...");
}
```

A `||` operator does not by itself guarantee that the pattern matched. Conversely, `||` inside a group after `&&` can be valid:

```java
if (value instanceof String text
        && (text.startsWith("J") || text.startsWith("K"))) {
    System.out.println(text);
}
```

In this example, both conditions inside the parentheses are evaluated only after `value` matches `String`.

### 3.3. Early return after negation

```java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "Không phải chuỗi";
    }
    return text.strip(); // text remains in scope on the success path.
}
```

If execution reaches `return text.strip()`, the non-matching branch has already terminated with `return`, so the compiler knows `text` exists. No additional cast is needed after the `if`.

A **non-equivalent** example:

```java
if (!(value instanceof String text)) {
    System.out.println("Không phải chuỗi");
}
// Cannot use text here: the failure path can still fall through.
```

**The prerequisite for removing a cast is knowing for sure that the pattern variable is usable at that location.** If the variable is not yet in scope, restructure the code using branches or an early return; do not move the pattern variable into a place where the compiler cannot guarantee a match.

## 4. `switch` pattern matching: each `case` already carries the appropriate type

Since Java 21, you can handle multiple types using `switch`:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "Giá trị null";
        case String text when !text.isBlank() ->
            "Chuỗi: " + text.strip();
        case String text ->
            "Chuỗi trắng hoặc rỗng";
        case Integer number ->
            "Số nguyên: " + (number + 1);
        default -> "Kiểu khác";
    };
}
```

In the `case String text` branch, `text` **already has type `String`**. There is no need to write:

```java
// EXAMPLE OF A REDUNDANT CAST inside a pattern branch:
case String text -> "Chuỗi: " + ((String) text).strip();
```

And there is no need to go back to the selector either:

```java
// If the selector is named value, this repeats the cast:
case String text -> "Chuỗi: " + ((String) value).strip();
```

Use `text.strip()` instead. With `case Integer number`, call `number.intValue()` or use `number + 1`; not `((Integer) number).intValue()`.

**A `when` guard also has the pattern variable in scope:**

```java
case String text when text.length() > 10 ->
    "Chuỗi dài: " + text;
```

The `when` condition is evaluated only after `case String text` matches, so a cast is unnecessary inside the guard.

**Case order and dominance:** place guarded/more specific branches before general branches. For example, placing `case String text -> ...` **before** `case String text when text.length() > 10 -> ...` makes the guarded branch unreachable. Do not confuse a dominance error with a cast or scope error.

## 5. Record patterns and deconstruction: no casting per component

With Java 21, record patterns extract components typed according to the record declaration:

```java
record Point(int x, int y) {}
record Parcel(String code, Point destination) {}
```

Example:

```java
if (value instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

`x` and `y` are inferred as `int` from the components of `Point`, so there is no need to cast to `Integer`, nor to call `((Point) value).x()` or `((Point) value).y()`.

With nested records:

```java
if (value instanceof Parcel(var code, Point(var x, var y))) {
    System.out.println(code + " -> (" + x + ", " + y + ")");
}
```

- `Parcel(...)` checks that the outermost object is a non-null `Parcel`.
- `var code` receives the `String code` component.
- `Point(var x, var y)` checks that `destination` is a non-null `Point` and then extracts `int x` and `int y`.
- The variables `code`, `x`, and `y` already have the right types inside the branch; `(String) code` or `(Integer) x` is not needed.
- If `destination == null`, the nested `Point(...)` does not match, so the entire `Parcel(...)` does not match. There is no partial binding where `x` and `y` hold partial values for use.

### Stop deconstruction at the level you actually need

If you only need the code and destination without needing the coordinates:

```java
if (value instanceof Parcel(var code, var destination)) {
    // destination has type Point, but may be null.
    if (destination != null) {
        System.out.println(code + ": x=" + destination.x());
    }
}
```

`var destination` infers the type `Point` from the component, so `((Point) destination).x()` is redundant. However, the null check is still needed if the component can be null: **having the right static type does not mean non-null**.

For a record whose component is declared with a broader type, you must distinguish:

```java
record Envelope(Object payload) {}

if (value instanceof Envelope(var payload)) {
    // payload has static type Object, not String.
    if (payload instanceof String text) {
        System.out.println(text.length()); // No cast needed.
    }
}
```

Because `Envelope.payload` is declared as `Object`, `var payload` has type `Object`. To call `String.length()`, you must **check the subtype**. You must not assume that "once deconstructed, every component automatically gets a more specific type" and remove a cast without checking.

## 6. Complete Java 21 program: removing casts while preserving behavior

Create the file **`RedundantCastPatternDemo.java`**:

```java
public class RedundantCastPatternDemo {
    record Point(int x, int y) {}
    record Parcel(String code, Point destination) {}
    record Envelope(Object payload) {}

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "Văn bản: " + text.strip()
                    .toUpperCase(java.util.Locale.ROOT);
        }

        if (value instanceof Parcel(
                var code, Point(var x, var y))) {
            return "Kiện " + code + " -> (" + x + ", " + y + ")";
        }

        if (value instanceof Number number) {
            return "Số: " + number.doubleValue();
        }

        return "Không phù hợp";
    }

    static String route(Object value) {
        return switch (value) {
            case null -> "Không có dữ liệu";

            case String text when !text.isBlank() ->
                "Chuỗi: " + text.strip();

            case String text ->
                "Chuỗi trắng hoặc rỗng";

            case Point(var x, var y) when x == 0 && y == 0 ->
                "Gốc tọa độ";

            case Point(var x, var y) ->
                "Điểm: " + (x + y);

            case Integer number ->
                "Số nguyên: " + (number + 1);

            case Number number ->
                "Số khác: " + number.doubleValue();

            default -> "Kiểu khác";
        };
    }

    static int payloadLength(Object value) {
        if (value instanceof Envelope(var payload)
                && payload instanceof String text) {
            return text.length();
        }
        return -1;
    }

    public static void main(String[] args) {
        System.out.println(describe(" Java "));
        System.out.println(describe(
            new Parcel("PK-7", new Point(4, 6))));
        System.out.println(describe(new Parcel("PK-8", null)));
        System.out.println(describe(12));
        System.out.println(describe(null));

        System.out.println(route(null));
        System.out.println(route(" Hi "));
        System.out.println(route("  "));
        System.out.println(route(new Point(0, 0)));
        System.out.println(route(new Point(2, 3)));
        System.out.println(route(7));
        System.out.println(route(2.5));
        System.out.println(route(new Object()));

        System.out.println("Payload length: "
            + payloadLength(new Envelope("abcd")));
        System.out.println("Payload length: "
            + payloadLength(new Envelope(123)));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 -encoding UTF-8 RedundantCastPatternDemo.java
java RedundantCastPatternDemo
```

Expected output:

```text
Văn bản: JAVA
Kiện PK-7 -> (4, 6)
Không phù hợp
Số: 12.0
Không phù hợp
Không có dữ liệu
Chuỗi: Hi
Chuỗi trắng hoặc rỗng
Gốc tọa độ
Điểm: 5
Số nguyên: 8
Số khác: 2.5
Kiểu khác
Payload length: 4
Payload length: -1
```

### Key points analysis

1. `describe(" Java ")`: `String text` is already typed and bound. There is no `(String) value`; the string is stripped with `strip()` and converted to uppercase.
2. `describe(Parcel(...))`: the nested record pattern directly extracts `code`, `x`, and `y`. It does not call `((Parcel)value).destination()` and then cast to `Point`.
3. `describe(new Parcel("PK-8", null))`: `Point(...)` does not match because `destination` is null. The remaining branches do not match either; it returns `Không phù hợp`.
4. `describe(12)`: `Integer` is a `Number`, so `Number number` matches and uses `doubleValue()` directly.
5. `route`: the variable in each `case` already has the corresponding type; `when` uses that variable without needing a cast. The `Integer` branch is placed before the general `Number` branch.
6. `payloadLength`: `Envelope(var payload)` only extracts an `Object`, so it must further check `payload instanceof String text`. After matching `String`, it uses `text.length()` without casting.

This example demonstrates two distinct actions at the same time: **removing redundant casts** where a properly typed pattern variable already exists, and **keeping necessary type checks** when a component still has only a broader type.

## 7. When is a cast after a pattern match NOT redundant?

### 7.1. The pattern checks a supertype, while the logic needs a subtype

```java
if (value instanceof Number number) {
    System.out.println(number.doubleValue()); // Safe for Number.
}
```

`number` has static type `Number`; not every case is an `Integer`:

```java
// Not a redundant cast: narrowing from Number to Integer.
// However, it can throw ClassCastException if value is a Double.
if (value instanceof Number number) {
    Integer whole = (Integer) number;
}
```

If the business logic definitely requires an `Integer`, check the exact subtype up front:

```java
if (value instanceof Integer whole) {
    System.out.println(whole.intValue());
}
```

**Do not remove `(Integer) number` on your own** if the code relies on `Integer`-specific behavior. Replace it with a more specific pattern only when the logic truly intends to accept `Integer` and that change is confirmed appropriate.

### 7.2. An interface type does not guarantee a concrete implementation

```java
if (value instanceof CharSequence sequence) {
    System.out.println(sequence.length());
}
```

`sequence` could be a `String`, `StringBuilder`, or another type implementing `CharSequence`. Casting to `String` is not redundant:

```java
// Still a downcast, and can fail.
String text = (String) sequence;
```

If you need a `String`, use a `value instanceof String text` pattern (or an additional match afterward), rather than assuming the interface is synonymous with a specific implementation.

### 7.3. Numeric types: a cast may be a lossy conversion

```java
if (value instanceof Number number) {
    int truncated = (int) number.doubleValue();
    System.out.println(truncated);
}
```

`(int)` converts a `double` value to `int` according to Java's rules, which may discard the fractional part or change the value when outside the `int` range. This is a **numeric conversion** with its own semantics, not a redundant object cast to delete just because `Number` was matched.

For example, `Double.valueOf(2.9)` yields `truncated == 2`; if you remove `(int)`, assigning `double` to `int` is invalid. The variable name `truncated` reflects truncation of the fractional part, not rounding.

### 7.4. Generic types and type erasure

Not every generic cast can be replaced with `instanceof List<String> items`:

```java
// Does NOT compile when obj has type Object: the generic type
// List<String> is not reifiable for instanceof.
if (obj instanceof java.util.List<String> items) {
    // ...
}
```

You can check the raw type at runtime using a wildcard:

```java
if (obj instanceof java.util.List<?> items) {
    for (Object item : items) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase(
                java.util.Locale.ROOT));
        }
    }
}
```

`List<?>` proves it is a `List`, **not that every element is a `String`**. Using the `String text` pattern on each element is one way to avoid an unchecked cast. The cast `(List<String>) obj`, if used, is a separate issue: it can produce an unchecked warning and cannot verify the generic type argument at runtime. Removing it requires redesigning the type contract rather than relying solely on `instanceof List<?>`.

### 7.5. A cast can affect overload selection

Overloading is resolved based on the **static type of the expression**:

```java
static String format(Object value) { return "Object"; }
static String format(String value) { return "String"; }

// Illustrative snippet inside another method.
Object value = "hello";
if (value instanceof String text) {
    System.out.println(format(value));        // Object
    System.out.println(format((String) value)); // String
    System.out.println(format(text));         // String
}
```

If you only **delete the cast** in `format((String) value)` to make it `format(value)`, the selected overload **changes**. If the goal is to avoid the cast while **preserving behavior**, replace the entire argument expression with `text`.

This is an important example for code reviews: do not call a cast "harmless to delete" when it directly affects overload resolution. Consider replacing it with the properly typed pattern variable instead of removing only the cast parentheses.

## 8. Common misconceptions about `null`

### `instanceof` with null

```java
Object value = null;
if (value instanceof String text) {
    // Does not execute.
}
```

Null does not match a type pattern at this level. You do not need to write `value != null` before `instanceof` just to guard against errors in the example above.

### Record components can still be null

```java
record Note(String text) {}

if (value instanceof Note(var text)) {
    // text has type String, but may be null.
    if (text != null) {
        System.out.println(text.length());
    }
}
```

The record pattern `Note(var text)` can still match when `Note.text() == null`: `var text` is an unconditional pattern for the component type, allowing null to be preserved. A cast `(String) text` does **not** turn null into a valid string, nor does it replace the `text != null` check.

### Nested records require non-null child records

```java
record Wrapper(Note note) {}

if (value instanceof Wrapper(Note(var text))) {
    // Wrapper.note() must be a non-null Note.
    // However, text inside Note can still be null.
}
```

**Distinguish clearly:** having the right static type, whether a value can be null, and whether a pattern matches are three separate questions. Removing a redundant cast does not automatically solve null-safety.

## 9. Before/after refactoring comparisons

### Case A: replacing a cast with a type pattern variable

**Before:**

```java
if (value instanceof String) {
    String text = (String) value;
    consume(text);
}
```

**After:**

```java
if (value instanceof String text) {
    consume(text);
}
```

This is a straightforward refactor. When the compiler can verify the structure and variable usage, it eliminates the need to write a cast and reduces boilerplate.

### Case B: avoiding repeated casts when calling multiple methods

**Before:**

```java
if (value instanceof String) {
    System.out.println(((String) value).length());
    System.out.println(((String) value).strip());
}
```

**After:**

```java
if (value instanceof String text) {
    System.out.println(text.length());
    System.out.println(text.strip());
}
```

The refactored version clearly expresses a single type check and uses a single typed variable. No re-casting is needed on each line.

### Case C: changing where the type check happens, not just deleting the cast

**Error-prone:**

```java
if (value instanceof Number number) {
    Integer count = (Integer) number; // Not guaranteed if Number is a Double.
    System.out.println(count + 1);
}
```

**If only integers should be accepted:**

```java
if (value instanceof Integer count) {
    System.out.println(count + 1);
}
```

This is **not** a strictly equivalent refactor for all inputs: the original version can throw `ClassCastException` when the input is a `Double`, whereas the latter simply skips the branch. Determine the desired behavior for non-`Integer` inputs before choosing the approach.

### Case D: not losing information when handling records

**Before:**

```java
if (value instanceof Parcel) {
    Parcel parcel = (Parcel) value;
    Point destination = parcel.destination();
    if (destination != null) {
        System.out.println(destination.x());
    }
}
```

**After:**

```java
if (value instanceof Parcel(var code, var destination)
        && destination != null) {
    System.out.println(destination.x());
}
```

In both snippets, `value` must be a `Parcel` and `destination` must be non-null to print the coordinate. The latter removes the cast and manual `Point` declaration while keeping the null guard. Note that `code` is only extracted because the record has two components; if deconstruction is not needed, `value instanceof Parcel parcel` and `parcel.destination()` is also a clear option.

## 10. How can the compiler help detect redundant casts?

When analyzing a cast, check two things: **does the code compile** and **does removing the cast preserve behavior**.

- `javac` checks static types, pattern variable accessibility via flow scoping, matching conditions in `switch`, and conversion rules.
- Depending on the compiler version and configuration, you can enable warnings for redundant casts with `-Xlint:cast`; IDEs can also suggest "redundant cast".
- A warning does not prove that a mechanical change preserves behavior in every expression. For overloads, generics, and narrowing casts, you must verify static types and runtime semantics.
- Do not delete an unchecked generic cast without fixing the type contract. A generic cast that looks "unnecessary" on the current path may still indicate a lack of type safety in the API.

Example command to run the program from section 6 with warnings enabled:

```bash
javac --release 21 -encoding UTF-8 -Xlint:cast RedundantCastPatternDemo.java
java RedundantCastPatternDemo
```

The goal of `-Xlint:cast` is to help spot cases that can be simplified. **Not every expression that can be improved produces a warning**, especially when `(String) value` is repeated while `text` already exists and `value` is still declared as `Object`. Semantic review remains important.

If an IDE suggests removing a cast, inspect the surrounding expression: which overload is selected, what type each variable has, and whether a numeric conversion or subtype narrowing is taking place.

## 11. Review checklist for casts after pattern matching

| Question | How to check | Decision |
| --- | --- | --- |
| Has the pattern already declared a variable of the right subtype? | Check `instanceof T t`, `case T t`, or `Record(var component)` | Use `t`/component instead of casting where appropriate |
| Is the pattern variable still in scope? | Check `if`/`else`, `&&`, early return, and each `case` branch | Only use the variable in branches guaranteed to match |
| Is the cast applied to the pattern variable or the original variable? | Compare static types of `t` and `value` | `(T) t` is usually redundant; `(T) value` can be replaced by `t` |
| Does the cast narrow to a deeper subtype than the pattern? | E.g., `Number` to `Integer` | Check the subtype or keep the cast intentionally, accounting for failure |
| Is the cast a numeric conversion? | `(int) doubleValue()` | Check whether narrowing and data loss are intended |
| Does a generic cast produce an unchecked warning? | `List<?>` vs. `List<String>` | Adjust the API or check elements instead of deleting blindly |
| Does the overload change? | Compare static argument types before/after | Use the properly typed pattern variable to preserve the overload if needed |
| Can the component be null? | Check the record/constructor contract | A cast cannot replace a null guard |
| Is a `switch` branch shadowed? | Check the order of type patterns and guards | Place specific branches before general branches |
| Have different-typed cases been tested? | String, Integer, Double, null, null child record | Verify results and exceptions against business requirements |

A good decision separates **type safety** from **code quality**. A cast may be syntactically valid yet poorly expressed because it fails to leverage a pattern variable; conversely, a cast may be necessary when the chosen pattern is not specific enough.

## 12. Common mistakes

| Mistake or misconception | Cause | How to fix |
| --- | --- | --- |
| `value instanceof String text` followed by `String s = (String) text` | `text` is already a `String` | Use `text` directly; remove the duplicate declaration |
| Deleting `(String) value` while still calling `value.length()` | `value` has static type `Object` | Switch to `text.length()` |
| Assuming `n` is `Integer` after `instanceof Number n` | The match only proves `Number` | Use `instanceof Integer i` if `Integer` is required |
| Using `var payload` in a record with `Object payload` and calling `payload.length()` | `var` infers `Object`, not the runtime subtype | Use `payload instanceof String text` |
| Thinking a cast and a null check are equivalent | Casting a null reference still returns null; calling a method on null throws NPE | Check for null separately |
| Using a pattern variable outside flow scoping | The pattern might not have matched on some path | Reorganize `if`/`else`/early return |
| Using `||` after `instanceof` and reading the pattern variable | The right-hand side can run when the pattern is false | Use `&&` when the condition depends on a successful match |
| Removing a numeric narrowing cast because "already `instanceof Number`" | `Number` does not turn a `double` into an `int` | Keep the conversion and make truncation clear |
| Using `instanceof List<String>` instead of a generic cast | Type erasure; parameterized types are not reifiable | Use `List<?>` + element checks or redesign the generic API |
| Removing a cast on an argument changes the overload | Overload resolution relies on static types | Replace the entire argument with the properly typed pattern variable |
| Placing `case Number n` before `case Integer i` | The later case is dominated | Put `Integer` before `Number` |
| Removing a cast without running tests | Refactoring may alter output/exceptions | Compile and test edge cases |

## 13. Practice exercises

**Exercise 1 — Identifying redundant casts.** Given `Object value`, consider:

```java
if (value instanceof String text) {
    int a = ((String) text).length();
    int b = ((String) value).length();
    int c = text.length();
}
```

Which is the best way to write it? **Hint:** `c`. Line `a` casts a variable that is already a String; line `b` only needs the cast because it calls the method on the `Object` variable, which can be replaced with `text`.

**Exercise 2 — Overloading.** Given `format(Object)` and `format(String)`, explain why `format(value)` and `format(text)` select different overloads even though `value` and `text` may reference the same string. Answer: **static type** determines overload resolution at compile time.

**Exercise 3 — Supertype/subtype.** Why does `Number n` not automatically prove the object is an `Integer`? Write code that handles `Integer` and `Double` in two separate `switch` branches without casting.

**Exercise 4 — Broadly typed record component.** Given `record Envelope(Object payload)`, write an `if` statement that returns the length if `payload` is a `String`. Hint: use nested matching `value instanceof Envelope(var payload) && payload instanceof String text`.

**Exercise 5 — Null.** Given `record Note(String text)`, write handling that does not throw an NPE if the `text` component is null. Hint: after `Note(var text)`, check `text != null` before calling `text.length()`.

**Exercise 6 — Compiling and classifying.** Run `RedundantCastPatternDemo.java`, then try swapping `case Integer number` and `case Number number`. How does the compiler react? Explain using **dominance**.

**Exercise 7 — Verified refactoring.** Convert a manual type check + cast snippet in your own code to a pattern variable; test with matching subtype data, non-matching subtype data, and null. If there is an overload or narrowing conversion, note why you kept or replaced the cast.

## 14. Summary

**Removing redundant casts after a pattern match is the result of using the variable whose type the compiler has already verified**, not blindly deleting every `(Type)` in code that happens to contain an `instanceof` or `case`.

- `instanceof T t` and `case T t` give `t` the static type `T` within the valid matching scope.
- `Record(var x, ...)` infers the type of `x` from the declared component; nested record patterns can extract down to leaf types.
- Using the pattern variable directly usually eliminates the type check → cast → auxiliary variable chain.
- The original variable still retains its declared static type; if you continue using it, a cast may still be required in that expression. Replacing it with the pattern variable is usually clearer.
- Subtype-narrowing casts, numeric conversions, generic casts, and casts affecting overload resolution may carry real meaning; do not remove them without understanding why they are there.
- Flow scoping, nullability, and `switch case` ordering are independent factors to check when refactoring.

### References

- [Oracle Java 21 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-instanceof.html)
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
