# Pattern Applicability at Compile Time (Java 21)

## Objectives and Scope

Within **Compiler and type checking**, a key question in Pattern Matching is: **does the compiler allow applying a pattern to a value whose static type is already known?** That property is called pattern *applicability* at compile time.

After this lesson, you will be able to:

- Distinguish **applicability (valid at compile time)** from **matching (matching at runtime)**.
- Predict whether code will compile based on the static type of the expression and the type in the pattern.
- Check applicability for **type patterns**, **record patterns**, and **nested component patterns**.
- Identify errors involving types that cannot be safely cast, component counts, primitive types, generics/erasure, and duplicate variable names.
- Distinguish other compiler checks such as *dominance*, *exhaustiveness*, and *scope*.

**Version:** examples use **Java 21**. Record Patterns (JEP 440) and Pattern Matching for `switch` (JEP 441) are finalized in Java 21, requiring no `--enable-preview`. In particular, do not apply pattern-extension rules for primitive types from newer/preview Java versions retroactively to Java 21.

## 1. Applicability Is a Compile-Time Check

Example:

```java
Object obj = "hello";
if (obj instanceof String text) {
    System.out.println(text.length());
}
```

The compiler sees the **static type** of the expression `obj` as `Object` and the pattern `String text`. It determines whether a value of type `Object` can undergo a **checked cast** to `String`. It can, so the pattern is **applicable** and the statement is valid.

At **runtime**, the JVM then checks whether the actual value of `obj` is a non-`null` `String`. For `"hello"`, the pattern matches; for `Integer.valueOf(5)`, the pattern does not match. Both cases **compile** as long as the static type of `obj` remains `Object`.

Conversely:

```java
String name = "hello";
if (name instanceof Integer number) {
    System.out.println(number);
}
```

The snippet above **does not compile** in Java 21: the static type `String` has no valid checked cast conversion to `Integer`. The compiler rejects it before execution, even though the author intended it as a condition inside `if`.

**Do not conflate them:** `pattern not applicable` ⇒ compile-time error; `pattern applicable but value does not match` ⇒ the program still runs, the `instanceof` expression typically evaluates to `false`, or `switch` evaluates another branch.

## 2. Exact Definition According to the Java 21 JLS

According to [JLS §14.30.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3), a pattern `p` is *applicable at type T* when it satisfies one of the following rules.

| Pattern kind | Condition to be applicable at static type `T` |
|---|---|
| **Reference type pattern** declaring a variable of type `U` | `T` is a reference type and there is a **checked cast conversion** from `T` to `U` (JLS §5.5) |
| **Primitive type pattern** declaring a variable of primitive type `P` | In Java 21, this pattern is applicable at the exact primitive type `P` |
| **Record pattern** with record type `R` and component patterns | (1) `T` is checked-cast-convertible to `R`; **and** (2) **each** component pattern is applicable at the **declared type of the corresponding component** in `R` |

The definition of a record pattern is **recursive**: if a component contains another record pattern, the compiler continues checking the applicability of the nested pattern against the component type at that level.

Example:

```java
record Duo(Object first, Number second) {}
Object value = new Duo("A", 7);

if (value instanceof Duo(String label, Integer score)) {
    System.out.println(label + ": " + score);
}
```

The compiler performs the type checks in this order:

1. `T = Object` has a checked cast conversion to record `R = Duo`.
2. Component `first` is declared as `Object`; type pattern `String label` is applicable at `Object`.
3. Component `second` is declared as `Number`; type pattern `Integer score` is applicable at `Number`.
4. All conditions are valid; the code compiles. At runtime, the record is `Duo`, the first component is `String`, and the second component is `Integer`, so the entire pattern matches.

The cast condition here is **checked**: it must not rely on an unchecked generic cast due to erasure. Beyond applicability, a record pattern must also satisfy other syntactic/type constraints such as the exact number of components, non-duplicate variable names, and `R` actually being a record class.

## 3. Static Type Determines What Code Is Allowed

Consider the same intent of checking `String`:

| Expression static type | Pattern | Compile time | Runtime |
|---|---|---|---|
| `Object` | `String s` | Valid | Matches if the value is a non-null `String` |
| `Number` | `Integer i` | Valid | Matches if the value is a non-null `Integer` |
| `String` | `Integer i` | **Error** | Does not run because the types are not cast-compatible |
| `String` | `CharSequence cs` | **Valid in Java 21** | Matches if `String` is non-null |
| `Duo` | `Duo(var a, var b)` | Valid | Matches if `Duo` is non-null and component patterns match |
| `Object` | `Duo(var a, var b)` | Valid | Matches if the value is a matching `Duo`; `null` does not match |

A common misconception: **Java 21 allows a type pattern where the static type is already a subtype of the pattern type**, provided the applicability condition is met. The following example **compiles** with `javac --release 21`:

```java
String text = "abc";
boolean a = text instanceof CharSequence cs;
boolean b = text instanceof String s;
```

Both boolean variables are `true` because `text` is non-null. If `text == null`, both `instanceof` expressions above evaluate to `false`. Some documentation for older Java versions describes "always true" `instanceof` patterns as errors; always check the exact JLS version you are using. **Applicability does not guarantee a runtime match**, especially when the value may be null.

For two **`final` classes** without a compatible checked cast conversion, such as `String` and `Integer`, the compiler can conclude they can never match and reject the code. Do not assume that any two types with different names are inapplicable: interfaces and non-`final` classes can have a valid cast relationship even without sharing an explicit inheritance chain.

## 4. Record Patterns: The Compiler Checks Each Component

Suppose:

```java
record Duo(Object first, Number second) {}
```

Analyzing the patterns:

| Record pattern | Compile time | Explanation |
|---|---|---|
| `Duo(String a, Integer b)` | Valid | `Object → String` and `Number → Integer` are valid checked cast conversions |
| `Duo(String a, Long b)` | Valid | `Number → Long` is valid; at runtime it may not match if `second` is actually an `Integer` |
| `Duo(var a, var b)` | Valid | `a` is inferred as `Object`, `b` as `Number` |
| `Duo(String a, String b)` | **Error** | `Number → String` is not checked-cast-convertible |
| `Duo(var a)` | **Error** | `Duo` has two components, but the pattern list has only one |
| `Duo(var a, var a)` | **Error** | Declares the same pattern variable name twice in a single record pattern |

Note: the rows above are **pattern fragments** and must be placed in a context such as `instanceof` or a `case` branch to be used in practice.

**From `var` to the inferred type:** `Duo(var a, var b)` does not mean the compiler picks the runtime type of the components. `a` is determined from the declared type `Object` and `b` from `Number`. To use an API that only exists on `Integer`, you need the corresponding pattern `Integer b` or an additional check.

### Primitive Components Must Match the Exact Type in Java 21

```java
record Point(int x, int y) {}
```

- `Point(int x, int y)`: valid, both components are declared as `int`.
- `Point(var x, var y)`: valid, the compiler infers both variables as type `int`.
- `Point(long x, int y)`: **invalid in Java 21**: the first component has type `int`, but the primitive pattern `long x` is not applicable at `int`, even though normal assignment from `int` to `long` allows widening.

**Pitfall:** Widening in assignments or arithmetic operations does **not** automatically grant permission to use any primitive type pattern in Java 21. In this version, the applicability rule for primitive patterns requires the **exact type `P`**. Also, `instanceof` requires the left-hand expression to be of a reference type or the null type in Java 21, so you cannot write `5 instanceof int i`.

## 5. Nested Record Patterns: Applicability Is Checked Recursively

Add the following declarations:

```java
record Address(String city, Point point) {}
record Customer(Address address) {}
```

For the pattern:

```java
Customer(Address(String city, Point(int x, int y)))
```

the compiler checks:

1. Whether the selector expression has a checked cast conversion to `Customer`.
2. Component `Customer.address` has type `Address`; whether record pattern `Address(...)` is applicable at `Address`.
3. Component `Address.city` is declared as `String`; `String city` is applicable at `String`.
4. Component `Address.point` is declared as `Point`; `Point(int x, int y)` is applicable at `Point`.
5. Both components `Point.x` and `Point.y` are declared as `int`, matching the primitive patterns `int x` and `int y`.

If even **one** component pattern is not applicable, the **entire** nested record pattern is invalid at compile time. For example, replacing `Point(int x, int y)` with `Point(long x, int y)` immediately causes an error at the inner primitive pattern.

**Applicability differs from null-matching:** Nested record patterns `Address(...)` or `Point(...)` do not match `null` at runtime, even though the compiler accepts them. A direct type pattern in the component list (such as `String city` when the component is declared `String`, or `var point` when the component is declared `Point`) can bind `null` when unconditional with respect to the component type. The compiler decides applicability based on static types, and runtime decides whether the actual value matches.

## 6. Standalone Java 21 Example: Cases Accepted by the Compiler

Create the file **`PatternApplicabilityDemo.java`** with the following complete contents:

```java
import java.util.List;

public class PatternApplicabilityDemo {
    record Duo(Object first, Number second) {}
    record Point(int x, int y) {}
    record Box<T>(T value) {}

    public static void main(String[] args) {
        Object source = "Java";
        System.out.println("Object -> String: "
                + (source instanceof String s && s.length() == 4));

        Object value = new Duo("A", Integer.valueOf(7));
        if (value instanceof Duo(String label, Integer score)) {
            System.out.println("Duo nested: " + label + "/" + score);
        }
        System.out.println("Duo component Long: "
                + (value instanceof Duo(String label, Long score)));

        Duo direct = new Duo("B", null);
        if (direct instanceof Duo(var left, var right)) {
            System.out.println("Duo typed source: " + left + "/"
                    + (right == null));
        }

        Number number = Integer.valueOf(8);
        System.out.println("Number -> Integer: "
                + (number instanceof Integer i && i > 0));

        Box<String> box = new Box<>("ok");
        if (box instanceof Box(var data)) {
            System.out.println("generic inferred: " + data.toUpperCase());
        }

        Object unknown = List.of("x");
        System.out.println("List<?>: "
                + (unknown instanceof List<?> list && list.size() == 1));

        Object missing = null;
        System.out.println("null record: "
                + (missing instanceof Duo(var a, var b)));

        Object choice = Integer.valueOf(9);
        String route = switch (choice) {
            case null -> "null";
            case String s -> "string";
            case Integer i when i > 0 -> "integer-positive";
            default -> "other";
        };
        System.out.println("switch(Object): " + route);
    }
}
```

Run on **JDK 21+**:

```bash
javac --release 21 PatternApplicabilityDemo.java
java PatternApplicabilityDemo
```

**Verified stdout:**

```text
Object -> String: true
Duo nested: A/7
Duo component Long: false
Duo typed source: B/true
Number -> Integer: true
generic inferred: OK
List<?>: true
null record: false
switch(Object): integer-positive
```

Explanation of key lines:

- `Object → String`: the compiler accepts the cast; the actual value is `String`, so the runtime condition is true.
- `Duo(String, Integer)`: each component pattern is applicable and the data also matches.
- `Duo(String, Long)`: **still compiles successfully** because `Number → Long` is a valid cast; at runtime it receives an `Integer`, so the whole pattern does not match, printing `false`.
- `Duo(var, var)`: the static type of the variable is already `Duo`, yet the record pattern is still applicable; component `second == null` is bound to variable `right`.
- `Box(var data)`: for `Box<String>`, the generic record pattern infers the component type `String`; `data.toUpperCase()` compiles.
- `List<?>`: the pattern can be checked without pretending the JVM can verify a non-reifiable generic type argument.
- `null record`: `instanceof` returns `false` at runtime; there is no applicability error.
- `switch(Object)`: `String` and `Integer` are both applicable choices at selector type `Object`; the actual branch matched is `Integer` with guard `i > 0`.

The record declarations in the example are nested types inside the Java class, so you only need to save a single file named after the public class.

## 7. Non-Compiling Examples: Understanding Each Cause

The following snippets are **intentionally incorrect**. Each snippet is standalone; do not combine them into the runnable program in section 6. All were tested with `javac --release 21` and rejected by the compiler. Exact error message wording may vary by `javac` version.

### 7.1. Source Type Cannot Be Cast to Pattern Type

```java
String value = "hi";
boolean bad = value instanceof Integer i; // COMPILE ERROR
```

`String` and `Integer` are two class types that do not have a checked cast conversion in this situation; the compiler determines that the pattern is not applicable at static type `String`. If you change the variable's static type to `Object`, checking `Integer` becomes valid, though it may return `false` at runtime.

### 7.2. Component Pattern Is Not Applicable

```java
record Duo(Object first, Number second) {}
Object source = new Duo("A", 7);
boolean bad = source instanceof Duo(String first, String second); // ERROR
```

The outer record level may be applicable, but the second component is declared as `Number`, while the pattern requires `String`. Because `Number` is not checked-cast-convertible to `String`, the entire record pattern is rejected.

### 7.3. Wrong Component Count and Duplicate Variable Names

```java
// Given record Duo(Object first, Number second) {}:
boolean wrongCount = source instanceof Duo(var a);          // ERROR
boolean repeated = source instanceof Duo(var x, var x);     // ERROR
```

`Duo` has two components, so two component patterns must be declared. Two pattern variables with the same name cannot be declared in the same record pattern. These are **compile-time well-formedness** conditions and should be distinguished from pure cast/applicability rules.

### 7.4. Primitive Pattern Does Not Match Component Type

```java
record Point(int x, int y) {}
Object source = new Point(1, 2);
boolean bad = source instanceof Point(long x, int y); // ERROR Java 21
```

The first component has type `int`, whereas the primitive type pattern is `long`. In Java 21, this pattern is not applicable at type `int`. Fix it to `Point(int x, int y)` or `Point(var x, var y)`.

### 7.5. Generic Pattern Requires an Unchecked Conversion

```java
record Box<T>(T value) {}
Box raw = new Box("hello");
boolean bad = raw instanceof Box<String>(var text); // ERROR
```

The static type `Box` is a **raw type**. Converting to `Box<String>` in the pattern requires generic type argument information that cannot undergo a corresponding checked cast; the compiler rejects it. Use `Box<String>` in the variable's declared type if the system knows it beforehand, or use another pattern whose cast can be safely checked.

Similarly:

```java
Object o = List.of("hello");
boolean bad = o instanceof List<String> xs; // ERROR
```

From `Object` to `List<String>` there is no safe checked cast conversion (the type argument `String` is erased). However, `o instanceof List<?> xs` is valid; afterward, check **the elements** with a separate pattern if you need to verify their types.

**Note:** Do not work around generic errors by forcing a raw/unchecked cast and treating the data as safe; that shifts the risk to runtime. Design your API types to preserve generic information that can be proven at compile time.

## 8. Applicability in switch and Other Checks

When writing:

```java
Object item = Integer.valueOf(9);
String route = switch (item) {
    case null -> "null";
    case String s -> "text";
    case Integer n when n > 0 -> "positive-int";
    default -> "other";
};
```

The compiler relies on the **static type `Object` of the selector `item`** to evaluate the applicability of each pattern. Both `String s` and `Integer n` are applicable at `Object`. At runtime, only the `Integer` branch whose guard is true is selected.

However, in `switch`, the compiler also checks properties **beyond applicability**:

- **Dominance:** a `case Object any -> ...` branch placed before `case String s -> ...` dominates the `String` branch, causing the `String` branch to be rejected. `String s` itself is still applicable at `Object`.
- **Exhaustiveness:** a `switch` expression must have branches covering every possibility required by the language. An individually applicable pattern does not by itself make the entire `switch` exhaustive.
- **Guards and scope:** the variable `n` is bound when `case Integer n` matches and can be used in `when n > 0`. Referencing `n` outside the branch is invalid.
- **Null:** `case null` handles a `null` selector; `default` alone does not automatically cover `null` in a pattern `switch`. This is runtime behavior, not a checked cast condition of a pattern.
- **Pattern list:** multiple `case`s that are each individually applicable can still cause dominance or duplicate-label errors when placed together.

**Draw the boundary:** a `case` must first be **applicable** before matching is even considered; after that, the entire `switch` is still subject to other checks for branch reachability and exhaustiveness.

## 9. Workflow for Diagnosing Pattern Errors Reported by javac

1. **Identify the Java version**: compile with `javac --release 21` to enforce Java 21 rules; do not use newer preview examples to reason backward.
2. **Determine the static type T** of the selector/expression from its declaration, expression type inference, or generic type. Do not guess from the runtime value's type.
3. **Identify the pattern kind**: reference type pattern, primitive type pattern, or record pattern.
4. **Check for a checked cast** from `T` to the pattern's type. If the compiler proves the cast is disallowed or would be unchecked, fix the type or pattern.
5. **For a record pattern**, check each component against its **declared type in the record**, recursing into nested records. Verify the exact component count and no duplicate variable names.
6. **For generics**, determine which type information actually exists at compile time and which is erased. Consider wildcards or changing the API to provide a typed record.
7. **For switch**, if each pattern is valid on its own yet the overall code still fails, check dominance, exhaustiveness, guards, and variable scope.
8. **Once the compiler accepts the code**, check runtime cases: mismatched actual types, `null` at the root or nested components, false guards, and fallback branches.

A useful trick is to pin the static type in place:

```java
Object broad = "abc";
String narrow = "abc";

// broad instanceof Integer i  -> valid, but false at runtime.
// narrow instanceof Integer i -> not applicable, compile-time error.
```

This is a **comparison illustration**, so do not combine both expressions in the same class, as declaring the variable `i` twice can lead to a different error. The key takeaway is that changing the declared type of the selector can change **whether the code compiles**, even when the observed value is identical.

## 10. Self-Check Exercises

Use:

```java
record Pair(Object left, Number right) {}
Object obj = new Pair("x", Integer.valueOf(3));
Pair pair = new Pair("x", Integer.valueOf(3));
```

Predict compile-time behavior first, and only if it compiles, evaluate runtime behavior:

| Expression | Compile time | Runtime result / explanation |
|---|---|---|
| `obj instanceof Pair(String s, Integer n)` | Valid | `true` for the given data |
| `obj instanceof Pair(String s, Long n)` | Valid | `false` because `second` is actually `Integer` |
| `obj instanceof Pair(Integer s, Integer n)` | Valid | `false` because `first` is actually `String`, even though `first` is declared as `Object` |
| `obj instanceof Pair(String s, String n)` | **Error** | Component `second` is declared as `Number`, which cannot be cast to `String` |
| `pair instanceof Pair(var a, var b)` | Valid | `true`; the type of `a` is `Object`, and `b` is `Number` |
| `obj instanceof Pair(var a)` | **Error** | Wrong arity: the record has two components |
| `obj instanceof Pair(var a, var a)` | **Error** | Duplicate pattern variable name in the same record pattern |

Follow-up questions:

1. Why does the compiler accept `Pair(String, Long)` even though the value of `second` is an `Integer`? Because it checks the **declared type `Number`**, which has a checked cast conversion to `Long`; a runtime mismatch is a separate matter.
2. Why is `pair instanceof Pair(var a, var b)` valid even though `pair` already has static type `Pair`? Because a record pattern still requires runtime deconstruction and is not considered unconditional—in particular, the root value can be `null`.
3. If `String name = null`, is `name instanceof CharSequence cs` valid? **Valid in Java 21**, though it returns `false` at runtime because the root value is `null`.
4. Why does `Box raw instanceof Box<String>(var v)` fail? Because the generic conversion requires an unchecked cast, violating the checked cast condition of record patterns.
5. When an applicable pattern is placed after `case Object any` in `switch(Object)`, why can it still fail? Because **dominance** is an independent compile-time check.

## Key Takeaways

**Applicability is the static type-checking gate before a program runs.** For a reference type pattern, there must be a checked cast conversion from the expression type `T` to the pattern type `U`. For a record pattern, there must be a checked cast to the record **and** each component pattern must be applicable at its declared component type, including across multiple nested levels. For a primitive pattern in Java 21, the type must match exactly.

An applicable pattern can still **fail to match at runtime** due to a mismatched actual type, `null`, or a non-matching nested component. And a construct made of applicable patterns can still **fail to compile** due to arity, a generic unchecked cast, duplicate variable names, dominance, or exhaustiveness. Always check **static type → applicability → remaining constraints → runtime matching** in that exact order.

## Official References

- [JLS Java SE 21 — §14.30.3 Properties of Patterns (applicability, unconditional, dominance)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [JLS Java SE 21 — §14.30.1 Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.1)
- [JLS Java SE 21 — §15.20.2 The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [JLS Java SE 21 — §5.5 Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5)
- [Oracle Java 21 — Record Patterns, Generic Records, Type Inference](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
