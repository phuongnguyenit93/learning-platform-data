# Patterns in Java's `switch expression`

A **`switch expression`** selects a branch based on an input value **and produces a result value**. When combined with **pattern matching**, each `case` branch can check a **type**, **record structure**, and **additional conditions** instead of only comparing against constants. This style is well suited for data transformation, result classification, message construction, value computation, and handling different object types.

This lesson uses stable syntax from **Java 21**: **pattern matching for `switch`** (JEP 441) and **record patterns** (JEP 440). The main examples compile with `javac` on JDK 21 and later, without needing `--enable-preview`.

## 1. Why use patterns in a `switch expression`?

Before Java 21, when a variable of type `Object` held multiple value types, the common approach was `if/else` combined with `instanceof`:

```java
// Illustrative snippet; 'input' is already declared as Object.
String result;
if (input instanceof String text) {
    result = "Văn bản: " + text;
} else if (input instanceof Integer number) {
    result = "Số: " + number;
} else {
    result = "Kiểu khác";
}
```

With Java 21+, you can write a single expression directly:

```java
// Illustrative snippet; 'input' is already declared as Object.
String result = switch (input) {
    case String text -> "Văn bản: " + text;
    case Integer number -> "Số: " + number;
    case null -> "Không có dữ liệu";
    default -> "Kiểu khác";
};
```

Each branch `case String text` or `case Integer number` both **checks the runtime type** of the object and **declares a pattern variable** (`text`, `number`) to use immediately in the result. The result of the `switch` is a `String`, so it can be assigned to `result` or written as `return switch (...)` inside a method.

### General structure

```java
// Syntax template, not a standalone program.
ResultType result = switch (selector) {
    case SomeType value when condition -> resultExpression;
    case AnotherType value -> otherResultExpression;
    case null -> nullResultExpression;
    default -> fallbackExpression;
};
```

Meaning:

- `selector`: the input expression evaluated before selecting a branch.
- `case SomeType value`: **type pattern**; checks whether the object has a matching type and binds the variable `value`.
- `when condition`: **guard**; checks an additional Boolean condition once the pattern matches.
- `-> resultExpression`: the expression producing the value for the branch; **no `break` needed**.
- `case null`: explicitly handles a `null` selector, if the domain logic allows it.
- `default`: handles the remaining values when the branches above do not cover everything.

The **final `;`** terminates the entire `switch expression` in an assignment statement; individual `case ... ->` branches do not end with their own semicolon.

## 2. Type patterns in `case`

A type pattern has the form `case Type variableName -> ...`. For `Object input`, for example:

```java
// Illustrative snippet.
String category = switch (input) {
    case String s -> "String dài " + s.length();
    case Integer n -> n >= 0 ? "Số không âm" : "Số âm";
    case Boolean flag -> flag ? "Đúng" : "Sai";
    case null -> "Không có giá trị";
    default -> "Đối tượng khác";
};
```

`String s`, `Integer n`, and `Boolean flag` are distinct patterns. Inside the `String s` branch, Java has already verified that `input` matches `String`, so `s.length()` can be called without casting.

Important points about types:

- An `Object` selector can hold a string, an `Integer` object, a `Boolean`, a record, or any reference object.
- `case Integer n` is a pattern for the **wrapper type `Integer`**. In this Java 21 example, do not replace it with `case int n` for an `Object` selector; proposals extending primitive patterns belong to other versions/features.
- The type pattern `case String s` does not match a `null` selector. If you need to accept `null`, use `case null`.
- When the selector is `Object`, having only a few specific `case` branches usually requires `default` in a `switch expression` to guarantee a result for all other types.

### Result type

The result types of all branches must be compatible with the surrounding context. For example:

```java
// Snippet: returns int; all branches produce an int value.
int length = switch (input) {
    case String text -> text.length();
    case java.util.Collection<?> items -> items.size();
    case null -> 0;
    default -> -1;
};
```

A branch returning `String` inside an expression used as `int` will cause a compile-time error. Do not confuse the **type of the selector** with the **type of the value produced by the `switch expression`**.

## 3. `when` guards: distinguishing cases of the same type

A type pattern only checks the type. When you need finer-grained classification, attach a Boolean condition with `when`:

```java
// Illustrative snippet; 'input' has type Object.
String answer = switch (input) {
    case Integer n when n > 0 -> "Dương";
    case Integer n when n < 0 -> "Âm";
    case Integer n -> "Bằng 0";
    case null -> "Thiếu số";
    default -> "Không phải Integer";
};
```

Execution flow for `input = Integer.valueOf(-4)`:

1. The pattern `Integer n` in the first branch matches by type, but the guard `n > 0` is `false`, so that branch is not selected.
2. The second branch also matches by type and its guard `n < 0` is `true`, so the result is `"Âm"`.
3. Subsequent branches are not evaluated.

When `input = 0`, both of the first two guards are false and the final `case Integer n` branch handles `0`. Therefore, placing **specific/guarded branches before broader ones** is an important rule.

**The official syntax in Java 21 is `when`**, for example `case String s when s.isBlank() -> ...`. Do not write guards using older preview syntax if you want the program to run consistently on Java 21+.

A pattern variable declared by `case` can be used in the guard and in the result expression of that same branch. A guard does not turn a pattern variable into a shared variable across branches.

## 4. Record patterns in `switch expression`

A record pattern checks a record object and **deconstructs each component**. Given two records:

```java
record Point(int x, int y) {}
record Move(String name, Point target) {}
```

An example classifying an `Object` can be written as:

```java
// Illustrative snippet; 'input' is Object.
String label = switch (input) {
    case Point(var x, var y) when x == 0 && y == 0 ->
            "Gốc tọa độ";
    case Point(var x, var y) ->
            "Điểm (" + x + ", " + y + ")";
    case Move(var name, Point(var x, var y)) ->
            name + " tới (" + x + ", " + y + ")";
    case Move(var name, var target) ->
            name + ": không có điểm đích";
    case null -> "Không có dữ liệu";
    default -> "Đối tượng khác";
};
```

Reading `case Point(var x, var y)`: the selector must be a non-`null` `Point`; components `x` and `y` are bound to two variables of the same names, of type `int`. Pattern variable names are matched by component position, not by accessor method name, and may differ from the names declared in the record.

Reading `case Move(var name, Point(var x, var y))`: first, the selector must be a `Move`; next, its `target` component must be a non-`null` `Point`; only then are `name`, `x`, and `y` extracted. If `target == null`, this nested branch does not match and falls through to checking `Move(var name, var target)`.

**Note:** `var target` can receive `null` from a reference component; `Point(var x, var y)` does not match `null` in the `target` position. This is why an additional branch may be needed to handle incomplete data.

### Pattern variables are scoped to their branch

In `case Point(var x, var y) -> ...`, `x` and `y` are only in scope within the branch where the pattern matches (including its guard, if any). Other `case Point(var x, var y)` branches can reuse the names `x` and `y` because their scopes are independent. You cannot use `x` from any branch outside the `switch` unless you declare a separate variable and pass it out through the result value.

## 5. `switch expression` returning results with `->` and `yield`

When a branch needs only a single expression, write it directly after `->`:

```java
// Illustrative snippet.
int score = switch (input) {
    case Integer n when n > 0 -> n * 2;
    case Integer n -> 0;
    case null -> 0;
    default -> -1;
};
```

When multiple statements are needed (temporary calculations, logging, checks), use a **block** and `yield`:

```java
// Illustrative snippet.
int score = switch (input) {
    case Integer n when n > 0 -> {
        int doubled = n * 2;
        yield doubled;
    }
    case Integer n -> 0;
    case null -> 0;
    default -> -1;
};
```

`yield doubled;` supplies the **branch's value** for the entire `switch expression`. In a traditional switch statement, `break` only exits the switch statement and cannot replace `yield` to return a value. With `case ... -> expression`, you do not write `yield` because the expression on the right-hand side is already the branch result.

| Aspect | `switch statement` | `switch expression` |
| --- | --- | --- |
| Main purpose | Execute statements per branch | Compute a value per branch |
| Producing a result | Usually assign to a variable, call a method, or `return` from a method | Assign directly, `return switch (...)`, or nest inside another expression |
| Block after `->` | Contains statements | Must supply a value via `yield` if it completes normally |
| Exhaustiveness | Not required for all traditional statements | **Required** so every value has a result branch |
| `case ... ->` | No fall-through | No fall-through |

In a `switch expression`, a branch may throw an exception instead of producing a value, for example `default -> throw new IllegalArgumentException("Unsupported");`. That exception causes the expression to complete abruptly rather than returning a value.

## 6. Complete Java 21+ example

Create the file **`SwitchPatternExpressionDemo.java`**:

```java
public class SwitchPatternExpressionDemo {
    record Order(String customer, int itemCount, boolean paid) {}

    static String describe(Object value) {
        return switch (value) {
            case Order(var customer, var count, var paid)
                    when paid && count >= 3 ->
                    "Đơn lớn đã thanh toán: " + customer + " (" + count + ")";
            case Order(var customer, var count, var paid)
                    when !paid ->
                    "Đơn chưa thanh toán: " + customer;
            case Order(var customer, var count, var paid) ->
                    "Đơn đã thanh toán: " + customer + " (" + count + ")";
            case String text when text.isBlank() -> "Chuỗi trắng";
            case String text -> "Văn bản: " + text.trim();
            case Integer number when number > 0 -> "Số dương: " + number;
            case Integer number -> "Số khác: " + number;
            case null -> "Không có dữ liệu";
            default -> "Kiểu khác: " + value.getClass().getSimpleName();
        };
    }

    static int calculatePoints(Object value) {
        return switch (value) {
            case Order(var customer, var itemCount, var paid) -> {
                int validCount = Math.max(itemCount, 0);
                yield paid ? validCount * 10 : 0;
            }
            case Integer number -> number;
            case null -> 0;
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Order("Mai", 3, true)));
        System.out.println(describe(new Order("Nam", 2, false)));
        System.out.println(describe(new Order("An", 1, true)));
        System.out.println(describe("   "));
        System.out.println(describe("  java  "));
        System.out.println(describe(5));
        System.out.println(describe(-2));
        System.out.println(describe(null));
        System.out.println(describe(3.14));

        System.out.println("Điểm: " + calculatePoints(new Order("Mai", 3, true)));
        System.out.println("Điểm: " + calculatePoints(new Order("Nam", 2, false)));
        System.out.println("Điểm: " + calculatePoints(4));
        System.out.println("Điểm: " + calculatePoints("abc"));
        System.out.println("Điểm: " + calculatePoints(null));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac -encoding UTF-8 SwitchPatternExpressionDemo.java
java SwitchPatternExpressionDemo
```

Expected output:

```text
Đơn lớn đã thanh toán: Mai (3)
Đơn chưa thanh toán: Nam
Đơn đã thanh toán: An (1)
Chuỗi trắng
Văn bản: java
Số dương: 5
Số khác: -2
Không có dữ liệu
Kiểu khác: Double
Điểm: 30
Điểm: 0
Điểm: 4
Điểm: -1
Điểm: 0
```

### Step-by-step analysis

**`describe` method:**

1. When `value` is `Order("Mai", 3, true)`, the record pattern matches and the guard `paid && count >= 3` is true, so the first branch is selected.
2. `Order("Nam", 2, false)` does not pass the first guard, but the `when !paid` branch is true. `Order("An", 1, true)` does not pass either of the first two guards and falls into the third `Order(...)` branch.
3. A whitespace-only string matches `String text` and `text.isBlank()`. The string `"  java  "` is not blank, so it matches the remaining `String text` branch and is trimmed with `trim()`.
4. The numbers `5` and `-2` become `Integer` when passed to the `Object` parameter (autoboxing), so they match the two different `Integer` branches.
5. `null` is handled by `case null`. The floating-point literal `3.14` becomes `Double` when passed as `Object`, so it goes to `default`.

**`calculatePoints` method:**

- The `Order(...)` branch uses a block `-> { ... yield ...; }` to clamp the item count to at least `0` and then compute points if paid.
- The `Integer` branch returns the input number itself as points.
- `case null` returns `0`; all other types return `-1`.
- The `customer` variable in the record pattern is named to illustrate deconstructing the entire record; only `itemCount` and `paid` are needed for computing points. On Java 22+, you can use the unnamed pattern `_` for unused components. The code above remains compatible with Java 21 because it does not use `_`.

From a design standpoint, choose result values with consistent meaning across branches. For example, `-1` is used as an "unsupported" signal in this demo program; a real system might use a result type such as an enum or record to represent errors more clearly.

## 7. Exhaustiveness and `sealed` types

The compiler requires a `switch expression` to **cover all possible cases** according to the possible types. With an `Object` selector, branches for `String`, `Integer`, and `Order` do not cover all types; `default` is usually required.

With a **sealed interface**, the compiler knows the exact set of permitted direct subtypes, so it can verify exhaustiveness without `default`:

```java
// Non-standalone example: declarations placed in the same file within an appropriate scope.
sealed interface Shape permits Circle, Rectangle {}
record Circle(double radius) implements Shape {}
record Rectangle(double width, double height) implements Shape {}

static double area(Shape value) {
    return switch (value) {
        case Circle(var radius) -> Math.PI * radius * radius;
        case Rectangle(var width, var height) -> width * height;
        case null -> 0.0;
    };
}
```

This is an **illustrative snippet**, not a standalone Java file because `static double area` must reside inside a class, record, or valid declaration context. The pattern does not need `default` because `Circle` and `Rectangle` cover all declared implementations of `Shape`; `case null` additionally handles `null` if passed in.

If the sealed hierarchy later adds another permitted type, the compiler can require adding a branch for that type upon recompilation. This is the benefit of letting the compiler check the required branches instead of immediately writing `default` for everything.

**Subtle point:** Exhaustiveness primarily concerns non-`null` values that can match according to the type system; a `switch` with a `null` selector still needs separate consideration. Without `case null` (or a valid `null`-handling label), evaluating the expression with `null` normally throws `NullPointerException`, even when `default` is present.

## 8. Branch ordering, dominance, and variable scope

### Broad branches can dominate narrower ones

Java checks **dominance** of case patterns. If you place a general branch before a narrower one, the narrower branch can never be selected and **the compiler reports an error**:

```java
// WRONG: snippet does not compile.
String output = switch (input) {
    case CharSequence text -> "Chuỗi ký tự";
    case String text -> "String cụ thể"; // dominated by case CharSequence.
    case null -> "Null";
    default -> "Khác";
};
```

How to fix: place the specific `String` branch first:

```java
// VALID for Object input.
String output = switch (input) {
    case String text -> "String cụ thể";
    case CharSequence text -> "Chuỗi ký tự";
    case null -> "Null";
    default -> "Khác";
};
```

Similarly, if you write `case String s -> ...` before `case String s when s.isBlank() -> ...`, the guarded branch becomes unreachable. Place specialized guarded branches before unguarded branches of the same type.

### Pattern variable scope

The name in `case String text` is in scope in `when` and in the body of that same branch. You can use the same name `text` in other branches as long as their scopes do not overlap, but you cannot reference it directly outside the `switch`.

Choose more meaningful names than `x` or `obj` when data has multiple levels: `customer`, `count`, and `paid` are easier to understand in an `Order` domain. For nested records, names are bound at each corresponding component; there is no automatic "extract all fields by name" mechanism.

### Arrows prevent fall-through

`case ... ->` executes the selected branch and produces the result. It does not fall through to the next branch like the `case:` syntax of a traditional switch statement. With `switch expression`, prefer arrows so readers can immediately see which branch produces which result.

## 9. Common mistakes

| Mistake | Why it happens | How to fix |
| --- | --- | --- |
| Missing `default` when switching on `Object` with a few specific types | The `switch expression` is not exhaustive | Add `default` or a valid general type pattern |
| Assuming `default` always handles `null` | A `null` selector has separate semantics | Write `case null` if the input can be `null` |
| Placing `case String s` before `case String s when s.isBlank()` | The guarded branch is dominated | Move the guarded branch earlier |
| Placing `case CharSequence c` before `case String s` | The `String` branch is dominated by its supertype | Place `String` before `CharSequence` |
| Using `break value;` inside a switch expression block | Not valid syntax to return a value from a switch expression | Use `yield value;` |
| Writing `case Point(var x)` when the record has two components | Missing a component pattern | Write all components: `Point(var x, var y)` |
| Using `case String s` and assuming `s` can be `null` | A type pattern does not match `null` | Handle a `null` selector in its own branch; `var` components can be `null` |
| Referencing a pattern variable outside the case | The variable is only in scope inside the matched branch | Compute the value inside the branch and return it via the `switch expression` |
| Returning incompatible result types | Cannot produce a value matching the target type | Align branch result types or design a clear result type |
| Using old preview `switch` syntax on Java 21 | The feature changed before finalization | Use `case Type v when condition -> ...` |

Another semantic pitfall to avoid is that a `var` variable in a record pattern can receive a **`null` reference component**. For example, `case Order(var customer, var count, var paid)` can bind `customer == null`; do not call `customer.length()` without handling that possibility.

## 10. Practice exercises

Given the record:

```java
record Temperature(double celsius, String city) {}
```

**Exercise 1.** For `Object input`, write a `switch expression` returning `String`: `"Nóng"` if it is a `Temperature` with `celsius >= 35`, `"Bình thường"` if it is any other `Temperature`, `"Thiếu dữ liệu"` if `null`, and `"Không phải nhiệt độ"` for any other type.

**Answer:**

```java
// Illustrative snippet.
String result = switch (input) {
    case Temperature(var degrees, var city) when degrees >= 35 -> "Nóng";
    case Temperature(var degrees, var city) -> "Bình thường";
    case null -> "Thiếu dữ liệu";
    default -> "Không phải nhiệt độ";
};
```

**Exercise 2.** Rewrite the first branch to use a block and `yield` with a temporary variable `String message`.

**Answer:**

```java
case Temperature(var degrees, var city) when degrees >= 35 -> {
    String message = "Nóng";
    yield message;
}
```

This is a **`case` branch snippet** and must be placed inside a `switch expression` with the remaining corresponding branches. `yield` supplies `message` as the expression's value.

**Exercise 3.** What happens if you place `case Temperature(var degrees, var city) -> "Bình thường";` before the `when degrees >= 35` branch?

**Answer:** The guarded branch is dominated by the more general `Temperature` branch; the compiler does not allow dominated case patterns. Place the specific guarded branch first.

**Exercise 4.** Why can you omit `default` in a `switch expression` that branches on all permitted subtypes of a sealed interface, but usually cannot omit it when the selector is `Object`?

**Answer:** With a sealed hierarchy, the compiler knows the list of permitted subtypes to verify coverage. With `Object`, there are many unlisted runtime types, so a catch-all branch (usually `default`) is required. Handling `null` remains a separate decision.

## 11. Practical summary

- Use a **`switch expression`** when you need **a single result value** from classifying data.
- `case Type variable` checks the type and brings the variable into scope in that branch; `case Record(var a, var b)` deconstructs record components.
- Add `when` to distinguish different conditions on the same type; place guarded branches and narrower types **before** more general branches.
- Use `-> expression` for short branches; use `-> { ... yield value; }` when multiple statements are needed.
- Ensure all cases are covered; add `default` for open selectors like `Object`, and use sealed types when you want the compiler to check an explicit set of types.
- Handle `null` intentionally and keep branch results type-compatible.

**Official references:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html).
