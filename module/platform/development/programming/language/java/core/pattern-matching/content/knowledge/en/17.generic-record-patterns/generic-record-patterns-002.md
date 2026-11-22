# Type Argument Inference in Record Patterns (Java 21+)

## 1. The problem: how do you deconstruct a record with type parameters?

In Java, a `record` can declare type parameters, just like a regular generic class:

```java
record Box<T>(T value) {}
record Pair<L, R>(L left, R right) {}
```

`Box<String>` holds a component whose **declared type is `String`**, while `Box<Integer>` holds a component whose declared type is `Integer`. When reading the contents via `box.value()`, the compiler uses the type argument of the `box` variable to determine the result type.

Since Java 21, **record patterns** allow testing and extracting record components directly in `instanceof` or `switch`. With generic record patterns, Java also supports **type argument inference**: if the static type of the expression provides enough information, you can omit the `<...>` list on the record name in the pattern and let the compiler determine the appropriate type argument.

```java
Box<String> box = new Box<>("hello");

if (box instanceof Box(var text)) {
    // The compiler knows text has type String.
    String upper = text.toUpperCase();
    System.out.println(upper);
}
```

Output:

```text
HELLO
```

In the pattern `Box(var text)`, the parentheses enclose the **record component pattern list**. `var text` is a type-inferred variable declaration pattern. The name `Box` has no `<String>`, yet the type of `text` is still `String` because the input type is already known to be `Box<String>`.

These are two related but distinct inference steps:

1. **Record pattern type argument inference:** from `Box<String>`, determine that the type parameter `T` of `Box<T>` corresponds to `String`.
2. **Type inference for the `var` variable:** from the record component `T value` after `T` has been determined, determine that the variable `text` is `String`.

**Version:** Record patterns, including type argument inference and nested patterns, were standardized in **Java 21 (JEP 440)**. The examples in this article use Java 21+, without needing to enable preview features.

## 2. Compile-time inference mechanism

Suppose:

```java
record Box<T>(T value) {}

Box<String> textBox = new Box<>("Java");
```

When the compiler encounters:

```java
if (textBox instanceof Box(var text)) {
    String copy = text;
}
```

It has two sources of information: (a) the static type of `textBox` is `Box<String>`, and (b) the record component of `Box<T>` has type `T`. In this context, the compiler determines the corresponding generic type and checks the component pattern against that type; `text` is treated as `String`.

To make the syntax clear, when the type is already known it can also be written explicitly:

```java
if (textBox instanceof Box<String>(var text)) {
    String copy = text;
}
```

Both examples above use `Box<String>` as input, and both give `text` the type `String`. The shorthand `Box(var text)` reduces type-argument repetition when the context already supplies enough information.

**Syntax note:** `Box(var text)` is how you omit the type argument of a *record pattern*. **`Box<>(var text)` is not valid record pattern syntax in Java 21**. The diamond operator `<>` appears in object creation expressions such as `new Box<>("hello")`, not here.

### Inference table by input type

| Static type of the expression | Example pattern | Usable type of the component variable | Key takeaway |
| --- | --- | --- | --- |
| `Box<String>` | `Box(var value)` | `String` | Can call `value.toUpperCase()` after checking for `null` |
| `Box<Integer>` | `Box(var value)` | `Integer` | Can be assigned to `Integer` or unboxed to `int` if non-`null` |
| `Box<? extends Number>` | `Box(var value)` | A type upper-bounded by `Number` | Can be assigned to `Number`; does not infer `Integer` |
| `Box<?>` | `Box(var value)` | No more specific type guaranteed than `Object` | Cannot be assumed assignable to `String` |
| `Object` (holding a `Box` inside) | `Box(var value)` | No more specific type guaranteed than `Object` | The actual generic type is not "discovered" from the object at runtime |

The table describes **compiler guarantees**, not predictions of the runtime class of an individual value. For example, a variable declared as `Box<? extends Number>` might hold an `Integer`, `Long`, or another subtype of `Number`; you should only write code against the guaranteed type bound.

## 3. Complete, compilable, and runnable example

Save the following complete program to a file named **`GenericRecordPatternDemo.java`**:

```java
public class GenericRecordPatternDemo {
    record Box<T>(T value) {}
    record Pair<L, R>(L left, R right) {}
    record Parcel<T>(String id, Box<T> content) {}

    // Box<String> lets the compiler infer that text has type String.
    static String upper(Box<String> box) {
        if (box instanceof Box(var text)) {
            String typed = text; // Valid: typed is String.
            return typed == null ? "Null content" : typed.toUpperCase();
        }
        return "Not a Box";
    }

    // The two type parameters L and R are inferred independently.
    static String showPair(Pair<String, Integer> pair) {
        if (pair instanceof Pair(var name, var quantity)) {
            String label = name;       // String
            Integer amount = quantity; // Integer
            return label + ": " + amount;
        }
        return "Not a Pair";
    }

    // From Parcel<String>, infer Box<String>, then infer text as String.
    static String showParcel(Parcel<String> parcel) {
        if (parcel instanceof Parcel(var id, Box(var text))) {
            String content = text;
            return id + " -> " + content;
        }
        return "Missing parcel content";
    }

    // Type Object does not guarantee that Box has type argument String.
    static String inspect(Object obj) {
        if (obj instanceof Box(String text)) {
            return "Text: " + text;
        }
        if (obj instanceof Box(var value)) {
            Object untyped = value;
            return "Box value: " + untyped;
        }
        return "Not a Box";
    }

    // Upper-bounded wildcard: the value can be used as a Number.
    static String showNumber(Box<? extends Number> box) {
        if (box instanceof Box(var value)) {
            Number number = value;
            return "Number: " + number.intValue();
        }
        return "Not a Box";
    }

    // When the static type is compatible, the type argument can be written explicitly.
    static String explicit(Box<String> box) {
        if (box instanceof Box<String>(var text)) {
            return "Explicit: " + text;
        }
        return "Not a Box";
    }

    public static void main(String[] args) {
        System.out.println(upper(new Box<>("hello")));
        System.out.println(showPair(new Pair<>("items", 3)));
        System.out.println(showParcel(
                new Parcel<>("PK-01", new Box<>("book"))));
        System.out.println(inspect(new Box<>(42)));
        System.out.println(showNumber(new Box<>(7)));
        System.out.println(explicit(new Box<>("world")));
        System.out.println(upper(new Box<>(null)));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac --release 21 GenericRecordPatternDemo.java
java GenericRecordPatternDemo
```

Output:

```text
HELLO
items: 3
PK-01 -> book
Box value: 42
Number: 7
Explicit: world
Null content
```

The program demonstrates six inference cases: from a single-parameter record; from a record with two type parameters; from nested generic records; from data declared only as `Object`; from a bounded wildcard; and explicitly specifying `Box<String>` in the pattern.

## 4. Inference in nested record patterns

Consider two types:

```java
record Box<T>(T value) {}
record Parcel<T>(String id, Box<T> content) {}
```

A `Parcel<String>` has a `content` component of type `Box<String>`. When you write:

```java
Parcel<String> parcel =
        new Parcel<>("PK-01", new Box<>("book"));

if (parcel instanceof Parcel(var id, Box(var text))) {
    String message = text;
    System.out.println(id + " -> " + message);
}
```

Output:

```text
PK-01 -> book
```

Inference flow according to the declared structure:

```text
parcel: Parcel<String>
  │
  ├── Parcel<T>  =>  T corresponds to String
  │
  ├── component id: String  =>  id has type String
  │
  └── component content: Box<T>  =>  Box<String>
        │
        └── pattern Box(var text)  =>  text has type String
```

At the inner level, you do not have to repeat `<String>`. That does not mean Java reads type arguments from object memory at runtime; the compiler already has the relationship `Parcel<T>` containing `Box<T>` in the **type declaration**.

If `parcel.content()` is `null`, then `Box(var text)` does not match because there is no `Box` object to deconstruct. If `content` is a `Box<String>` whose `content.value()` is `null`, then the pattern `Box(var text)` can still match and `text` has the value `null`. Distinguish between an absent nested record and a `null` component inside the record.

## 5. Inference and generic type erasure do not conflict

Generic type arguments are primarily used by the compiler for type checking. Java applies **type erasure**: the object `new Box<>("abc")` does not store a reliable runtime marker indicating that it was created as `Box<String>`. Therefore:

```java
Object unknown = new Box<>("abc");

if (unknown instanceof Box(var value)) {
    Object anyValue = value; // Safe.
    System.out.println(anyValue);
}
```

The code prints `abc`, but from the **static type `Object`**, Java cannot guarantee that `value` is a `String`. In this same context, writing the following test is a **compile-time error**:

```java
Object unknown = new Box<>("abc");

// WRONG: cannot safely check type argument String from Object.
if (unknown instanceof Box<String>(var value)) {
    System.out.println(value);
}
```

The typical error message is `Object cannot be safely cast to Box<String>`. **Generic record pattern syntax does not bypass `instanceof` type-safety rules**.

If you want to check that the **component** of `Box` is actually a string, you can use a **component type pattern**:

```java
Object unknown = new Box<>("abc");

if (unknown instanceof Box(String value)) {
    System.out.println(value.toUpperCase());
}
```

The output is `ABC`. Here, `String value` is a pattern that tests the type of the **component value**, not a check that "the `Box` object has runtime type argument `String`". For `new Box<>(42)`, the pattern `Box(String value)` does not match.

**Important distinction:**
- `Box(var value)`: declares a variable whose type is inferred from the record context; does not require the component to have runtime class `String`.
- `Box(String value)`: uses a `String` component pattern; when the component type is not already proven to be `String`, it checks the runtime type of the component value.
- `Box<String>(var value)`: explicitly specifies the type argument of the record pattern; valid only when overall type-checking rules permit it.

### Advanced note: effect of static type on null

A record pattern can contain an *unconditional component pattern* when the compiler already knows the component has that type. The following example illustrates how static type also affects component pattern matching:

```java
record Box<T>(T value) {}

Box<String> typed = new Box<>(null);
Object unknownView = typed;

System.out.println(typed instanceof Box(String text));       // true
System.out.println(unknownView instanceof Box(String text)); // false
```

When the variable has type `Box<String>`, the `value` component is known to be `String`, so `String text` is an unconditional pattern for that component, matching even `null`. When viewing the same object through `Object`, Java must check the component's type at runtime, and a conditional type pattern does not match `null`. Neither case checks a runtime type argument on `Box`; the difference comes from **the type information available at compile time**.

Practical rule: do not rely on a pattern match to guarantee that every field is non-`null`. Check business conditions right after deconstruction.

## 6. Multiple type arguments, wildcards, and type bounds

### 6.1. Two independent generic parameters

```java
record Pair<L, R>(L left, R right) {}

Pair<String, Integer> pair = new Pair<>("score", 10);

if (pair instanceof Pair(var label, var points)) {
    String name = label;
    Integer count = points;
    System.out.println(name + ": " + count);
}
```

Output: `score: 10`. Type `L` corresponds to `String`, and type `R` corresponds to `Integer`. Using `var` in both patterns does not mean both variables share the same type; each position takes its type from the corresponding record component.

### 6.2. Upper bound `? extends Number`

```java
Box<? extends Number> numeric = new Box<>(37);

if (numeric instanceof Box(var value)) {
    Number n = value;
    System.out.println(n.intValue());
}
```

Output: `37`. The compiler knows `value` is a type compatible with the `Number` bound, so it can be assigned to `Number`; it cannot be assumed assignable to `Integer` because the record might hold another subtype of `Number`.

### 6.3. Wildcard `?` and raw types

With `Box<?>`, the type argument is not specifically determined. `Box(var value)` can still deconstruct the record, but it does not guarantee that `value` is `String` or `Integer`. Any handling that requires a narrower type must include appropriate checks.

Avoid using the raw type `Box` when you can write `Box<String>`, `Box<Number>`, or `Box<?>`. Raw types discard type-checking information, often trigger unchecked warnings, and do not make record pattern inference any stronger.

## 7. Common mistakes

1. **Assuming `var` reads generic types at runtime.** It uses type constraints known to the compiler. The same object can be referenced as `Box<String>` or `Object` and carry different levels of type information.
2. **Writing `Box<>(var x)` in a pattern.** The `<>` diamond is for `new Box<>(...)`, whereas record pattern inference syntax is `Box(var x)`.
3. **Forcing `Box<String>` onto `Object` data just because the test value is a string.** Type erasure prevents checking generic arguments this way. Use `Box(String x)` if the goal is to check a `String` component value.
4. **Misunderstanding generic invariance.** `Box<Integer>` is not a subtype of `Box<Number>`. If you only need to read numbers across multiple subtypes, consider `Box<? extends Number>`.
5. **Confusing record type with component type.** `Box(String x)` can check that the component is a `String`, but it does not turn every `Box<?>` into a `Box<String>`.
6. **Forgetting `null` checks.** The pattern `Box(var value)` can bind `value == null`. With nested patterns, a `null` outer record component causes the inner record pattern not to match.
7. **Over-inferring from wildcards.** `Box<? extends Number>` only allows using the value as a `Number`; the concrete value may be any of several subtypes.
8. **Using a JDK older than Java 21 without considering preview features.** The examples in this article use standard Java 21 syntax, so check `javac -version` and `java -version`.

## 8. Choosing a pattern when designing code

| Need | Expression | Reason |
| --- | --- | --- |
| Variable already declared as `Box<String>` and need the string | `Box(var text)` | Infers type from context with less repetition |
| Want the pattern's type argument shown explicitly | `Box<String>(var text)` when valid | Keeps generic information visible in source code |
| Variable is `Object`; need to check a string component | `Box(String text)` | Checks the component instead of trying to guess runtime generics |
| Want to handle any kind of `Box` | `Box(var value)`, treating it as `Object` | Makes no narrower type assumptions |
| Nested generic records | `Parcel(var id, Box(var text))` | Inferred types propagate through component declarations |
| Only know the component is a numeric type | `Box(var number)` with `Box<? extends Number>` | Preserves the type bound declared by the API |

## 9. Practice exercises and self-check questions

**Exercise 1 — Predict the types.** Given `Pair<String, Long> pair`, write `pair instanceof Pair(var label, var count)`. What is the type of `label`? What is the type of `count`? Answer: `String` and `Long`.

**Exercise 2 — Two-level inference.** Given `Parcel<Integer> parcel` and the declaration `record Parcel<T>(String id, Box<T> content)`, what type can the variable `payload` in `Parcel(var id, Box(var payload))` be assigned to? Answer: `Integer`, provided the nested pattern matches; if `content == null`, that branch is not entered.

**Exercise 3 — Identify the error.** Why is `Object value = new Box<>("hello"); if (value instanceof Box<String>(var text)) { ... }` rejected? Answer: there is no safe runtime check for the `String` type argument on an object declared only as `Object`. Replace it with `Box(String text)` if the goal is to check the component type.

**Exercise 4 — Missing data.** Given `Box<String> box = new Box<>(null)`, does `box instanceof Box(var text)` match? Answer: **yes**; `text` is inferred as `String`, but its value can be `null`. Add `text != null` before calling string methods.

**Exercise 5 — Type bounds.** Why does `Box<? extends Number>` allow `Number n = value` in `Box(var value)` but does not always allow `Integer n = value`? Answer: the wildcard only guarantees a subtype of `Number`, not specifically `Integer`.

**Remember:** Type argument inference in generic record patterns is a **compiler mechanism** based on the static type of the expression and the declarations of the record components. It combines naturally with `var` and nested record patterns to reduce repetitive type annotations, while still obeying type erasure, wildcard bounds, and `null`-matching rules.

**Official references:** [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [Java Language Specification 21 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).