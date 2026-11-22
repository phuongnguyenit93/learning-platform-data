# Type of a Variable Inferred from a Pattern in Java

## 1. The Core Question: What Type Does a Pattern Variable Have?

When using **pattern matching**, Java both checks whether a value matches a pattern and can **declare a pattern variable** to be used at locations where a match is guaranteed. One key benefit is that the compiler already knows the **static type** of that variable, so developers do not have to cast it manually.

Java 17 example:

```java
Object data = "Java";
if (data instanceof String text) {
    System.out.println(text.toUpperCase()); // JAVA
}
```

There are three kinds of types to distinguish:

- **Static type of the original expression**: the variable `data` is still declared as `Object`.
- **Static type of the pattern variable**: `text` has type `String` because the pattern explicitly specifies `String text`.
- **Actual runtime type (runtime class)**: the object referenced by `data` is currently a `String`; `instanceof` checks this type relationship to decide whether it matches.

The compiler allows calling `text.toUpperCase()` because **the static type of `text` is `String`**, not because the variable `data` automatically changes into `String` after the check. For instance, `data.toUpperCase()` is still invalid at compile time because `Object` does not declare that method.

It is important to understand the word "inferred" accurately: in the **type pattern** `String text`, the type `String` is written explicitly and the compiler takes it directly from the pattern. Only with a **record pattern** using `var` (Java 21+) does the compiler actually perform type inference for a specific component based on the record declaration and the type context. The two cases are related, but not completely synonymous.

## 2. Type Pattern: The Variable's Type Is Determined Directly from the Type Name in the Pattern

The common syntax in `instanceof` since Java 16, stable on Java 17+:

```text
expression instanceof ReferenceType variable_name
```

Example:

```java
Object input = "Hello";

if (input instanceof String text) {
    int length = text.length(); // text has type String
    System.out.println(length);
}
```

When `input` is non-`null` and its object matches `String`, the variable `text` is brought into valid scope. The variable's type is **the exact type stated in the pattern**; Java does not automatically turn that variable into a more specific subtype just because the runtime instance has that subtype.

| Type pattern | Static type of the declared variable | Can be called directly |
| --- | --- | --- |
| `String name` | `String` | `name.toUpperCase()`, `name.length()` |
| `CharSequence chars` | `CharSequence` | `chars.length()`, `chars.charAt(0)` if characters remain |
| `Number number` | `Number` | `number.intValue()`, `number.doubleValue()` |
| `Runnable job` | `Runnable` | `job.run()` |
| `java.util.List<?> items` | `List<?>` | `items.size()`; elements read out do not yet have a specific type |
| `Integer count` | `Integer` | `count.intValue()` |

The following example illustrates the limitation of the static type:

```java
Object value = "pattern";

if (value instanceof CharSequence chars) {
    System.out.println(chars.length()); // Valid: CharSequence has length()
    // chars.toUpperCase();             // Invalid: CharSequence does not have toUpperCase()
}
```

Even though the runtime object may be a `String`, **the variable `chars` has type `CharSequence`**. If you need behavior available only on `String`, use a `String` pattern or perform a further narrowing check at a valid location.

**There is no type change for the original variable:** `if (value instanceof String s)` does not change the declaration of `value` from `Object` to `String`. The compiler uses the new variable `s` to work with the determined type.

## 3. Comparison with Manual Casting

Before using pattern variables, developers typically wrote:

```java
static void before(Object value) {
    if (value instanceof String) {
        String text = (String) value;
        System.out.println(text.length());
    }
}
```

With a type pattern, declaring and assigning the reference to a variable of the appropriate type is expressed directly:

```java
static void after(Object value) {
    if (value instanceof String text) {
        System.out.println(text.length());
    }
}
```

Both approaches rely on the same runtime check. Using a pattern reduces manual casting, avoids repeating the type name, and clearly expresses the relationship: **only use `text` when the pattern has matched**. The compiler performs type checking and tracks the variable's scope. A pattern variable is not an `Object` variable dynamically cast on every method call; it already has a static type determined by the compiler.

## 4. Complete Java 17 Example: Same `Object` Input, Multiple Pattern Variable Types

Save the following code as **PatternVariableTypeDemo.java** and compile with Java 17 or later:

```java
public class PatternVariableTypeDemo {
    interface Label {
        String label();
    }

    record Ticket(String value) implements Label {
        @Override
        public String label() {
            return "T#" + value;
        }
    }

    static String describe(Object value) {
        if (value instanceof String text && !text.isBlank()) {
            return "String:" + text.toUpperCase();
        }

        if (value instanceof Label item) {
            return "Label:" + item.label();
        }

        if (value instanceof CharSequence chars) {
            return "Chars:" + chars.length();
        }

        return "Other";
    }

    static String guard(Object value) {
        if (!(value instanceof String word)) {
            return "not String";
        }
        return "Length:" + word.length();
    }

    public static void main(String[] args) {
        System.out.println(describe("java"));
        System.out.println(describe(new Ticket("7")));
        System.out.println(describe(new StringBuilder("abc")));
        System.out.println(describe(null));
        System.out.println(guard("pattern"));
        System.out.println(guard(42));
    }
}
```

Compile and run:

```bash
javac PatternVariableTypeDemo.java
java PatternVariableTypeDemo
```

Exact output:

```text
String:JAVA
Label:T#7
Chars:3
Other
Length:7
not String
```

Variable breakdown:

1. `text` in `String text` has type `String`, so `toUpperCase()` can be called.
2. `item` in `Label item` has type **interface `Label`**, even though the actual object is `Ticket`. The compiler allows calling `label()` because the interface declares that method.
3. `chars` in `CharSequence chars` has type `CharSequence`. `StringBuilder` implements this interface, so `chars.length()` is valid. You must not assume `chars` has all methods specific to `StringBuilder`.
4. `word` in `String word` has type `String` and is used after the early-return branch `if (!(...)) return ...`; the compiler knows that when execution continues, the pattern has matched.
5. `null` does not match the `instanceof` type pattern; `Integer` from `42` also does not match `String`. Therefore, the fallback branches are used.

This example uses **type patterns**, which have been stable since Java 16 (JEP 394). No preview features need to be enabled when running on Java 17.

## 5. The Compiler Knows the Type, but Also Needs to Know Whether the Variable Is in Valid Scope

**Static type** and **usage scope** are two different concerns. Although `String text` establishes the type `String`, the compiler only allows referencing `text` on control-flow paths where the pattern is guaranteed to match (flow scoping).

### The true branch of `if`

```java
static void show(Object input) {
    if (input instanceof String text) {
        System.out.println(text.length()); // Valid
    }
    // text.length();                     // Invalid: text is not in scope here
}
```

### The short-circuiting `&&` operator

```java
static void printNonBlank(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        System.out.println(text.toUpperCase());
    }
}
```

The right-hand side is evaluated only when the left-hand side is true. The compiler knows that when reading `text.isBlank()`, `text` is a matched `String`. That is why no cast is needed.

Be careful with the `||` operator:

```java
// Invalid: on the right-hand side, input may NOT match String.
// if (input instanceof String text || text.isBlank()) { ... }
```

If the left-hand side returns `false`, `||` must evaluate the right-hand side; at that point, `text` has not been declared on a valid path.

### Negating a pattern and early exit

```java
static int lengthOrMinusOne(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length(); // Valid: all remaining paths have already matched
}
```

In this example, after the `if`, the compiler deduces that the variable `text` is definitely assigned from the pattern. A variable's scope is not simply "from the first curly brace to the last curly brace"; it depends on control-flow analysis.

**Conclusion on scope:** the type of a pattern variable is defined by the pattern, whereas whether a line of code **is allowed to use** that variable is determined by flow scoping analysis.

## 6. Interface Patterns: The Variable Type Does Not Automatically Become the Runtime Class

An interface often has multiple implementations. When writing:

```java
interface Drawable {
    void draw();
}

class Circle implements Drawable {
    @Override
    public void draw() {
        System.out.println("circle");
    }

    public double radius() {
        return 2.5;
    }
}
```

The snippet below has two different type levels:

```java
Object shape = new Circle();

if (shape instanceof Drawable drawable) {
    drawable.draw(); // Valid: Drawable declares draw()
    // drawable.radius(); // Invalid: Drawable does not declare radius()
}
```

`drawable` has type `Drawable`, not `Circle`. The runtime type may be `Circle`, but that does not make the compiler automatically expose `radius()`. If you need methods specific to `Circle`, you can check with `shape instanceof Circle circle` in an appropriate branch.

This principle also applies to superclasses: `Number n` does not automatically become `Integer` even if the actual object is an `Integer`. Conversely, interface/superclass patterns are a good way for code to depend only on the behaviors exposed by the needed type.

## 7. Generics: The Compiler Cannot Infer All Type Arguments from a Runtime Object

Java generics use **type erasure**. A runtime check for `java.util.List<?>` confirms that the object is a `List`, but cannot verify whether its elements are `String` or `Integer` solely from `instanceof`.

```java
import java.util.List;

static void showFirst(Object input) {
    if (input instanceof List<?> items && !items.isEmpty()) {
        Object first = items.get(0); // Static type Object
        if (first instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

- `items` has static type `List<?>`, matching the pattern.
- `items.get(0)` can only be safely treated as `Object` in this code.
- Only `text` has static type `String` because the next pattern is `String text`.

Do not write:

```java
// Invalid for an Object input value:
// if (input instanceof List<String> names) { ... }
```

The type argument `String` of `List<String>` cannot be directly verified from an object of type `Object` using `instanceof` in this case. Use `List<?>` and then check elements as needed.

An object may hold generic data, but the compiler determines the type of a pattern variable based on **static types and Java's rules**, without "reading back" generic parameters that were erased at runtime.

## 8. Java 21+: `var` in Record Patterns Actually Infers Component Types

This is a clearer case of **type inference**. Record patterns were standardized in **Java 21 (JEP 440)**, and `var` can be declared in the component pattern list.

Suppose:

```java
record Point(int x, int y) {}
record Segment(Point start, Point end) {}
```

When writing:

```java
if (data instanceof Segment(Point(var x, var y), var end)) {
    int sum = x + y;
    Point last = end;
}
```

The compiler knows:

- `Segment.start()` has type `Point`, so it can continue matching the record pattern `Point(...)`.
- The two components `Point.x()` and `Point.y()` have type `int`, so **`x` and `y` are inferred as `int`**.
- The component `Segment.end()` has type `Point`, so **`end` is inferred as `Point`**.

The types of `x`/`y`/`end` are not decided from specific runtime values like 2, 3, or 4. They come from **the record's component declarations and the compile-time type context**. If a record has an interface-typed component, the corresponding `var` variable takes that interface type.

### Standalone Java 21 Example

Save as **RecordPatternTypeDemo.java**:

```java
public class RecordPatternTypeDemo {
    record Point(int x, int y) {}
    record Segment(Point start, Point end) {}
    record Box<T>(T value) {}

    static void show(Object data) {
        if (data instanceof Segment(Point(var x, var y), var end)) {
            int sum = x + y;
            Point last = end;
            System.out.println("startSum:" + sum);
            System.out.println("end:" + last.x() + "," + last.y());
        }
    }

    static void showGeneric(Box<String> box) {
        if (box instanceof Box(var text)) {
            String upper = text.toUpperCase();
            System.out.println("text:" + upper);
        }
    }

    public static void main(String[] args) {
        show(new Segment(new Point(2, 3), new Point(4, 5)));
        showGeneric(new Box<>("hello"));
    }
}
```

Compile and run with **JDK 21 or later** (without enabling preview):

```bash
javac RecordPatternTypeDemo.java
java RecordPatternTypeDemo
```

Output:

```text
startSum:5
end:4,5
text:HELLO
```

The generic `Box<T>` case demonstrates the role of **type context**: in `showGeneric(Box<String> box)`, the compiler knows `T` is `String`; therefore `Box(var text)` infers `text` as `String`, and `toUpperCase()` is valid.

However, if the original expression only has type `Object`:

```java
Object unknown = new Box<>("hello");

if (unknown instanceof Box(var item)) {
    Object value = item; // Valid
    // item.toUpperCase(); // Invalid: item does not have static type String
}
```

Here, the compiler has no static type evidence that `Box` contains a `String`, even though the actual runtime object was created with `new Box<>("hello")`. In this broad context, the variable `item` is not automatically promoted to `String`. To call string-specific methods, check `item instanceof String text` or pass the input as an appropriately verified generic type.

**Syntax note:** `var` does not replace every type pattern. For example, writing `obj instanceof var x` is not a valid general type pattern to use instead of `obj instanceof String x` in Java 17/21. The `var` in this article belongs to **record component patterns**; this syntax requires Java 21+.

## 9. Distinguishing Local Variable `var` from Record Pattern `var`

The two examples have different sources of inference information:

```java
Object raw = "hello";
var copy = raw; // copy has type Object, taken from the static type of raw

if (raw instanceof String text) {
    // text has type String as specified by the type pattern
    System.out.println(text.length());
}
```

With local `var` in Java 10+, the compiler infers the variable's type from **the initializer expression** `raw` (which has static type `Object`). Meanwhile, `String text` takes its type from **the type name written in the pattern**.

With the record pattern `Box(var text)`, the compiler infers the variable's type from **the corresponding record component after considering the generic context**. You should not generalize that the compiler "looks at the runtime object and guesses the type" for all three cases.

| Syntax | Applicable version | Basis for determining type |
| --- | --- | --- |
| `var local = expression;` | Java 10+ | Static type of the initializer expression |
| `x instanceof String text` | Java 16+ | The `String` type stated in the type pattern |
| `x instanceof CharSequence seq` | Java 16+ | The `CharSequence` type stated in the type pattern |
| `x instanceof Point(var px, var py)` | Java 21+ | Types of the components `Point.x()`, `Point.y()` |
| `box instanceof Box(var value)` | Java 21+ | Type of component `value`, which may depend on the generic context |

If your practice runs on Java 17, use type patterns such as `String s`, `Number n`, and `List<?> items`. Examples of record patterns with `var` require switching to Java 21+.

## 10. `null`, Primitive Types, and Compile-Time Conditions

**When the expression is `null`:**

```java
Object input = null;
System.out.println(input instanceof String); // false
```

The type pattern `String s` does not match `null`; therefore, the variable `s` has no value to be used in the true branch. No object is created by `instanceof`.

**Regarding primitives:** `instanceof` type patterns in Java 17/21 target **reference types**. Do not use `obj instanceof int n` for Java 17/21 exercises; if an `Object` holds a boxed integer, use `obj instanceof Integer n`. Conversely, a record pattern `Point(var x, var y)` in Java 21 can infer `x` and `y` as `int` because they come from primitive components of the record.

**Checks may be rejected at compile time:** the compiler does not accept every pair of types in `instanceof` if the conversion relationship is impossible. For example, if a variable has the type of a `final` class that does not implement the target interface at all, that check has no chance of succeeding and may be treated as a type error. At the same time, Java 17 does not accept certain *unconditional type patterns* when the static type of the expression is already a subtype of the pattern type (for example, matching a `String` variable directly to `String`). When you only want to know whether a variable already declared as `String` is non-`null`, use `s != null`.

**Valid scope does not guarantee that a method will not throw an exception:** the compiler knows `text` is a `String` and `text.length()` is valid; with an interface such as `service.process()`, exceptions caused by method logic can still occur. Pattern matching solves **type safety**, not business logic verification or error-freeness of every method.

## 11. Common Mistakes and Fixes

1. **Confusing the runtime class with the pattern variable type.** `value instanceof CharSequence cs` does not turn `cs` into a `String` just because the runtime instance happens to be `String`. Use the `CharSequence` API or match `String` if you need its specific API.
2. **Assuming the original variable changes type.** `Object value` remains `Object` after the check; only the new variable `String text` has `String` methods.
3. **Using the variable outside the matching flow.** A variable is only considered definitely assigned by the compiler on paths guaranteed to have succeeded in matching the pattern. Avoid calling it after an `if` without a valid control-flow structure.
4. **Mistaking the variable name as the source of type inference.** `value instanceof String number` still creates a **String** variable, even though its name is `number`. Choose meaningful names, but the type in the pattern is what decides.
5. **Assuming `List<?>` infers `String`.** You cannot call `items.get(0).toUpperCase()` solely from `List<?>`; you need to check the element or have stronger type information.
6. **Using the runtime value to guess the type of `var`.** `Box(var x)` on an expression of type `Object` does not automatically infer `x` as `String`, even when it holds a string at runtime.
7. **Using record patterns on JDK 17 without preview enabled.** Record patterns were standardized in Java 21; choose JDK 21+ for `Point(var x, var y)`.
8. **Using primitive `instanceof` as if Java 21 broadly supported it.** On stable Java 17/21, `Integer n` is the corresponding type pattern for boxed values; primitive components in records are a separate mechanism.
9. **Assuming `instanceof` treats `null` as a successful match.** With type patterns in `instanceof`, `null` always returns `false`; write a separate branch if needed.

## 12. Self-Check

### Exercise 1 — Predict the type

```java
Object value = new StringBuilder("abc");
if (value instanceof CharSequence chars) {
    System.out.println(chars.length());
}
```

**Answer:** `chars` has static type `CharSequence`, not `StringBuilder`; prints `3`. The call `chars.length()` is declared by the `CharSequence` interface, so it is valid.

### Exercise 2 — Determine the scope

```java
static int size(Object data) {
    if (!(data instanceof String text)) {
        return 0;
    }
    return text.length();
}
```

**Answer:** valid on Java 17+. After the branch returning `0`, every path reaching `text.length()` has matched `String text`. The method returns the length if `data` is a string, otherwise `0`.

### Exercise 3 — Component-based `var` inference

Given Java 21:

```java
record Temperature(double celsius, String unit) {}

static void read(Object input) {
    if (input instanceof Temperature(var c, var u)) {
        double converted = c + 1.0;
        String upperUnit = u.toUpperCase();
        System.out.println(converted + " " + upperUnit);
    }
}
```

**Answer:** `c` has type `double` and `u` has type `String` because `Temperature` declares the components `double celsius` and `String unit`. With `new Temperature(20, "c")`, the output is `21.0 C`. If `unit` is `null`, `u.toUpperCase()` can cause a `NullPointerException`; the static type `String` does not automatically guarantee non-null for a `var` component.

### Exercise 4 — Reading generic information

Why is the following snippet not guaranteed to allow calling `toUpperCase()`?

```java
Object raw = new java.util.ArrayList<String>();
if (raw instanceof java.util.List<?> items) {
    // items.get(0).toUpperCase(); // Invalid with respect to static type
}
```

**Answer:** `items` is `List<?>`, and `items.get(0)` only has static type `Object`. The compiler does not infer that the element is a `String` from runtime generics; add an element check before calling `String`-specific methods. Additionally, on an empty list, calling `get(0)` will throw `IndexOutOfBoundsException`; checking the size is an issue independent of type inference.

## 13. Summary of Rules

**The type of a pattern variable is determined by the pattern and the compile-time type context.** With `instanceof String s`, `s` is `String`; with `instanceof CharSequence s`, `s` is `CharSequence` even if the runtime object is `String`. The compiler only allows using the variable on paths where the pattern is guaranteed to match.

With Java 21+ record patterns, `var` receives its type from **the corresponding record component**, taking the generic context into account. This feature makes code more concise, but cannot read erased generic parameters from runtime. When you want to call a type-specific method, ensure that **the static type of the pattern variable** declares that method.

Official documentation for reference:
- [Oracle Java 17 — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [Java SE 17 Language Specification — Patterns](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.30)
