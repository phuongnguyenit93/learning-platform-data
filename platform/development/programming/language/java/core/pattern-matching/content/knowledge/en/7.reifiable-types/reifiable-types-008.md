# Type argument inference in patterns — Java Generics, reifiable types, and record patterns

With Java Generics, an easy-to-confuse question is: **can the compiler automatically infer the type argument in a pattern, and if so, does that mean Java checks the type argument at runtime?** These two things are different.

In **Java 21+**, a *generic record pattern* such as `Box(var value)` can be inferred by the compiler as a pattern corresponding to `Box<String>` if the value being matched already has the **static type** `Box<String>`. In that case, the component variable `value` has the static type `String` and can use `String` methods. However, this mechanism **does not recover type arguments erased at runtime**: if you only have a reference of type `Object`, Java cannot automatically guess that a `Box` currently holds a `String` and treat `value` as `String`.

This lesson distinguishes four concepts:

1. **Type argument**: a type passed to a generic type, such as `String` in `Box<String>`.
2. **Type inference**: the compiler infers an appropriate type from *compile-time* information.
3. **Reifiable type**: a type that retains enough necessary information to be checked at runtime, for example `String` or `List<?>`.
4. **Pattern matching**: testing a value against a pattern, and binding pattern variables when it matches.

The focus is on type argument inference for **record patterns**, not a general runtime check for all generic types.

## 1. Background: Generics and type erasure

For example, declare a generic record:

```java
record Box<T>(T value) {}
```

You can create:

```java
Box<String> names = new Box<>("Java");
Box<Integer> numbers = new Box<>(21);
```

`T` is the **type parameter** of `Box`. `String` and `Integer` are **type arguments** at each use site. The compiler uses this information to check assignments and method calls:

```java
String text = names.value();
Integer count = numbers.value();
```

At runtime, due to **type erasure**, the `String`/`Integer` information of an ordinary parameterized type is not present as a "complete type tag" that can be tested with `instanceof`. The JVM knows the object belongs to the `Box` class, but cannot rely solely on the object to safely prove that it is `Box<String>` rather than `Box<Integer>`.

The following example **does not compile** when the input variable has static type `Object`:

```java
Object unknown = java.util.List.of("Java");

// ERROR: cannot safely check List<String> from Object.
// if (unknown instanceof java.util.List<String> strings) {
//     System.out.println(strings.get(0));
// }
```

For the type `List<String>`, this test requires information about `String` that is not retained for checking the full type parameter at runtime. The valid approach from `Object` is to check with `List<?>` and then check each element if needed:

```java
if (unknown instanceof java.util.List<?> values) {
    for (Object item : values) {
        if (item instanceof String text) {
            System.out.println(text.toUpperCase());
        }
    }
}
```

`List<?>` is a **reifiable type** under Java's rules; `List<String>` in general is **not** reifiable. Type inference in the compiler does not change that fact.

## 2. Why are generic record patterns inferred in Java 21?

Consider again:

```java
record Box<T>(T value) {}
```

Starting in Java 21, you can write a record pattern with an explicit type argument:

```java
static void explicit(Box<String> box) {
    if (box instanceof Box<String>(String text)) {
        System.out.println(text.toUpperCase());
    }
}
```

Here, the static type of the tested target is already `Box<String>`; matching the record pattern can perform the appropriate check **without needing an unchecked conversion** from the input type to `Box<String>`.

The compiler can also infer the type argument when you **omit `<String>`** in the record pattern:

```java
static void inferred(Box<String> box) {
    if (box instanceof Box(var text)) {
        System.out.println(text.toUpperCase());
    }
}
```

In this example, the compiler contextually infers the record pattern `Box(var text)` to the type corresponding to `Box<String>`, and then infers that the component variable `text` has static type `String`.

**Two different levels of inference:**

- **Type argument inference of the record pattern:** from the static type of `box` being `Box<String>`, the compiler infers the type argument `String` for `Box(...)`.
- **Type inference of the component pattern `var text`:** after knowing the record pattern's type, the compiler knows the component `value` has type `String`; the variable `text` is also treated as `String`.

`var` here is a *type pattern in a record component list*; it is not a default `Object` variable, nor does it invoke a method that guesses the type at runtime.

The syntax `Box(var text)` in a pattern position **is not a constructor call**, and omitting `<String>` **does not mean intentionally using a raw type in an unchecked way**. Java defines a dedicated type argument inference for record patterns when type arguments are not written explicitly.

## 3. Reading an inference step by step

Consider the Java 21 program:

```java
Box<String> source = new Box<>("Java");

if (source instanceof Box(var text)) {
    System.out.println(text.length());
}
```

This can be analyzed as follows:

| Step | Information the compiler has | Consequence |
| --- | --- | --- |
| 1. Target | `source` has static type `Box<String>` | The compiler knows the parameterized type of the variable at the use site |
| 2. Record pattern | Syntax `Box(var text)` does not write a type argument | The compiler examines generic record `Box<T>` against the target type |
| 3. Type argument inference | Compatibility constraint from `Box<String>` | Infers the appropriate type argument is `String` |
| 4. Component pattern | Component `value` of `Box<String>` has type `String` | `var text` introduces variable `text` with static type `String` |
| 5. Flow scoping | The `if` branch runs only when the pattern matches | `text.length()` is valid and produces `4` |

Model:

```text
Static type of target: Box<String>
                |
                v
        record Box<T>(T value)
                |
                v
      pattern: Box(var text)
                |
                v
  infer T from context -> String
                |
                v
  infer component type -> String text
                |
                v
  runtime match succeeds -> bind text
                |
                v
     text.length() is valid
```

The **type inference** part belongs to the **compiler**. The **pattern testing and value binding** part happens at execution time. Do not reverse the order and assume Java inspects the object at runtime, sees a `String`, and reconstructs the type argument `T = String` from runtime.

## 4. Complete example: inferring one, two, and nested levels of type arguments

Save the following content to **`RecordInferenceDemo.java`**. The program uses Java 21+:

```java
record Box<T>(T value) {}
record Pair<T, U>(T first, U second) {}

public class RecordInferenceDemo {
    static void one(Box<String> source) {
        if (source instanceof Box(var text)) {
            System.out.println("upper=" + text.toUpperCase());
            System.out.println("length=" + text.length());
        }
    }

    static void two(Pair<String, Integer> pair) {
        if (pair instanceof Pair(var label, var count)) {
            System.out.println("pair=" + label.toUpperCase() + ":" + (count + 1));
        }
    }

    static void nested(Box<Box<String>> outer) {
        if (outer instanceof Box(Box(var text))) {
            System.out.println("nested=" + text.length());
        }
    }

    static void unknown(Object source) {
        if (source instanceof Box(var value)) {
            Object kept = value;
            System.out.println("runtime=" + kept.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        one(new Box<>("java"));
        two(new Pair<>("java", 4));
        nested(new Box<>(new Box<>("Java")));
        unknown(new Box<>("actual String"));
    }
}
```

Compile and run with JDK 21 or later:

```bash
javac RecordInferenceDemo.java
java RecordInferenceDemo
```

Output:

```text
upper=JAVA
length=4
pair=JAVA:5
nested=4
runtime=String
```

Explanation:

- **`one`:** the parameter `Box<String>` allows the compiler to infer `Box(var text)` as the type corresponding to `Box<String>`; `text` has static type `String`.
- **`two`:** from `Pair<String, Integer>`, the compiler simultaneously infers two type arguments `T = String` and `U = Integer`. Therefore, both `label.toUpperCase()` and `count + 1` are valid.
- **`nested`:** from `Box<Box<String>>`, the compiler infers the nested record patterns, going from the outer `Box` to the inner `Box` and finally inferring `text` as `String`.
- **`unknown`:** the target is declared as `Object`. The record pattern can still match a `Box` object, but the compiler **cannot infer the specific type argument `String` from static type `Object`**. The component variable `value` only has a type that can be safely used as `Object`. The `getClass().getSimpleName()` line returns `String` at runtime, but that is an observation of the value's actual class, not proof that the compiler inferred `T = String`.

An expression with the exact same runtime value can still lead to **different type inference capabilities** if viewed through different static types. This is a normal characteristic of Java's type system.

## 5. Fundamental difference: is the target `Box<String>` or `Object`?

Compare:

```java
Box<String> typed = new Box<>("Java");
Object unknown = typed;

if (typed instanceof Box(var text)) {
    System.out.println(text.toUpperCase()); // Valid: text has type String
}

if (unknown instanceof Box(var item)) {
    System.out.println(item);                // Valid
    // System.out.println(item.toUpperCase()); // ERROR if uncommented
}
```

In the `unknown` branch, the compiler does not have information that the object is being viewed under the type `Box<String>`. The variable `item` does not have a `toUpperCase()` method in the static type inferred by the compiler. To use it as `String`, you must check the component:

```java
if (unknown instanceof Box(var item) && item instanceof String text) {
    System.out.println(text.toUpperCase());
}
```

This approach **does not claim** the entire object has the parameterized type `Box<String>`; it only checks that the object is a `Box` matching the record pattern and that the component value is actually a `String`.

This is especially useful for objects coming from deserialization, APIs without precise generic declarations, or a collection of different types. Infer from **the static type actually present in signatures and variables**, then check at runtime on the specific data you need to use.

## 6. Why can't you arbitrarily write a `Box<String>` pattern on `Object`?

The following syntax is **invalid** for a target of type `Object`:

```java
Object unknown = new Box<>("Java");

// Wrong: checking Box<String> from Object requires an unchecked conversion.
// if (unknown instanceof Box<String>(var text)) {
//     System.out.println(text.length());
// }
```

The compiler is not allowed to turn a runtime type test that only knows the object belongs to `Box` into a safe assertion that the object belongs to `Box<String>`. A concrete parameterized type is not something the JVM checks completely via `instanceof`.

Even though the concrete object in the example **currently holds a string**, `unknown` still has the static type `Object`. Another program could pass `new Box<>(42)`, and Java cannot rely on erased types to distinguish `Box<String>` from `Box<Integer>` as a whole.

**Rule on checked casts:** for a generic record pattern with explicit type arguments, the check is only valid if the target can be converted to the record pattern's type via a **checked cast conversion**, without requiring an unchecked conversion. Therefore:

- From `Box<String>` to a matching record pattern `Box<String>(...)`: the necessary static type information is present, so it can be valid.
- From `Object` or raw `Box` to `Box<String>(...)`: cannot assert the concrete type argument via a checked cast; the compiler rejects it in the examples above.
- From `Object` to `Box(var item)`: can be valid, but the inferred type argument must reflect the amount of static type information actually available; it does not magically become `String`.

Note: do not conclude that every piece of code containing `instanceof SomeGeneric<Concrete>` is always forbidden in every context. Java considers **the static type of the target and whether the conversion is checked**. Standard `Object instanceof List<String>` is unsafe, but patterns with parameterized types compatible with a known target can be accepted. You must read the **context**, not just look at `<...>`.

## 7. Type argument inference and `var` type inference are not a single step

The two constructs:

```java
Box<String> box = new Box<>("Hi");

if (box instanceof Box(var value)) {
    System.out.println(value.length());
}
```

raise two different questions:

1. **How is `Box<T>` specialized in the pattern?** The compiler infers the type argument of the record pattern from the input type `Box<String>`.
2. **What type does `var value` have?** After inferring the record pattern, the compiler looks at the declared type of the corresponding record component; here `T` corresponds to `String`, so `value` has type `String`.

If the input is `Pair<String, Integer>`, each component can have a different type. If the input is `Box<Box<String>>`, inference applies across the pattern levels. If the input is `Object`, there is no basis to automatically infer `String`.

`var` in the component list of a record pattern **is not an "arbitrary runtime type-guessing" check**, nor does it allow writing `if (obj instanceof var x)` as a standalone type pattern. `var` here has a special role in component patterns.

Do not confuse it with the constructor diamond operator `<>`:

```java
Box<String> box = new Box<>("Java");
```

In this line, `new Box<>(...)` uses **diamond inference during object creation**. In `box instanceof Box(var text)`, the compiler applies **record pattern type inference during data matching**. Both places involve generic inference, but their contexts and rules differ.

## 8. Inference in `switch` also works (Java 21+)

Record pattern type inference is not limited to `instanceof`. The following `switch` expression example infers the component variables from the static type `Pair<String, Integer>`:

```java
record Pair<T, U>(T first, U second) {}

static String describe(Pair<String, Integer> pair) {
    return switch (pair) {
        case null -> "missing";
        case Pair(var label, var number) -> label.toUpperCase() + ":" + (number + 1);
    };
}
```

The snippet above is a **method illustration**, assuming `Pair` is declared in the program. When called with `new Pair<>("java", 4)`, the return value is `"JAVA:5"`; with `null`, it returns `"missing"`. The pattern `Pair(var label, var number)` can be inferred from the selector type `Pair<String, Integer>`.

Key points:

- The compiler infers the types of `label` and `number` from the selector/record type, not from the string content that the `switch` branch will produce.
- A record pattern **does not match `null` for the record object itself**; the example has a separate `case null`.
- The `case` condition is checked first, and only then is the expression on the right-hand side of `->` evaluated. The two phases—pattern matching and expression evaluation—are distinct.

**JDK 21+** is required because both record patterns and pattern matching for `switch` were standardized in Java 21. Do not bring this syntax into a project compiled with `--release 17`.

## 9. How do type erasure, reifiable types, and wildcards relate?

Clearly separate the examples:

| Syntax / type | Can be checked directly as in the example? | Meaning |
| --- | --- | --- |
| `obj instanceof String text` with `obj` of type `Object` | Yes (Java 17+) | `String` is a determinable runtime type; when matched, `text` is `String` |
| `obj instanceof List<?> list` with `obj` of type `Object` | Yes (Java 17+) | Checks whether the object is a `List`; elements can only be used safely as `Object` |
| `obj instanceof List<String> list` with `obj` of type `Object` | No | Cannot check the full `String` type argument at runtime from `Object` |
| `box instanceof Box(var s)` with `box` of type `Box<String>` | Yes (Java 21+) | Generic record pattern inferred thanks to the target's static type; `s` is `String` |
| `obj instanceof Box(var s)` with `obj` of type `Object` | Yes (Java 21+) | Matches the record, but there is no basis to infer `s` as `String` |
| `obj instanceof Box<String>(var s)` with `obj` of type `Object` | No | Requires an unchecked conversion to assert a concrete generic type |

**Reifiable type** refers to runtime information available for type testing; **type inference** refers to the compiler solving type constraints at compile time. A pattern can have an inferred generic type argument **without the JVM suddenly retaining the erased type argument**.

If code checks `List<?>` and then retrieves elements, only use the `String` type after checking each element; do not blindly cast the entire list to `List<String>`.

### Runnable Java 17+ example without record patterns

Save **`GenericBoundaryDemo.java`**:

```java
public class GenericBoundaryDemo {
    static void inspect(Object source) {
        if (source instanceof java.util.List<?> values) {
            System.out.println("size=" + values.size());
            if (!values.isEmpty() && values.get(0) instanceof String text) {
                System.out.println("first=" + text.toUpperCase());
            }
        }
    }

    public static void main(String[] args) {
        inspect(java.util.List.of("java", "core"));
    }
}
```

```bash
javac GenericBoundaryDemo.java
java GenericBoundaryDemo
```

Output:

```text
size=2
first=JAVA
```

This example relies only on `List<?>` and the `instanceof` type pattern `String text`, so it works in Java 17. This is the practical choice when initial data only has type `Object` and the application must check it safely.

## 10. Limits of type inference when using wildcards, raw types, and bounds

Suppose:

```java
Box<?> wildcardBox = new Box<>("Java");
Object any = wildcardBox;
```

Neither `wildcardBox` nor `any` allows the compiler to **assert that the concrete type argument is `String`**, even though the current content is a string. With `Box<?>`, the component type is constrained by the wildcard information; with `Object`, there is even less information about the generic record. The fact that `new Box<>("Java")` appears in a particular execution path does not replace the static type of the variable where the pattern is written.

With a bounded type, such as:

```java
record NumericBox<T extends Number>(T value) {}
```

the compiler can use the constraints of `T extends Number` during inference. However, the bound **`Number` does not mean `Integer`**: without `Integer` information from an appropriate static type, you must not call `Integer`-specific methods as if the compiler had inferred that exact type.

**Raw types** (for example declaring `Box raw`) lose generic type checking. Avoid using raw types to "work around" record pattern compile errors. If data comes from a legacy library via a raw type, upgrade the generic signature if possible or check the component with an appropriate pattern before processing.

More complex inference scenarios can arise with `? extends ...`, `? super ...`, capture conversion, or generic interfaces that a record implements. Java uses static type constraints, bounds, and JLS inference rules to find a valid type; it does not necessarily always yield a single concrete class. The safe rule remains: **only use methods declared on the type that the compiler actually inferred**.

## 11. A nuance about `null` in record patterns

**If the outermost record object is `null`**, it will not match a record pattern:

```java
Object source = null;
// source instanceof Box(var content) evaluates to false.
```

However, **a component inside the record can be `null`**. With an unconditional component pattern, `var` in a record component list can bind a `null` value:

```java
Box<String> box = new Box<>(null);
if (box instanceof Box(var content)) {
    System.out.println(content == null); // true
}
```

This is valid in Java 21: the outer record `box` is not `null` and the record pattern matches; `content` is bound to the component's `null` value. **Inferring that `content` has type `String` does not guarantee that the runtime value is non-null.** Do not call `content.length()` without checking for null if the record may contain null.

This nuance reiterates that **type inference** determines the static type; **null-safety** is a separate checking requirement. You should not assume data is non-null just because the compiler inferred the type argument.

## 12. Common mistakes

1. **Confusing generic inference with runtime type inspection.** `Box(var value)` can infer `String` from `Box<String>` at compile time; it does not have the ability to "read" the `String` type argument from any `Box` object at runtime.
2. **Ignoring the static type of the target.** `Object obj = new Box<>("Java")` is not equivalent to `Box<String> obj = new Box<>("Java")` in terms of the information the compiler uses at the pattern.
3. **Assuming `var` always infers the runtime class of the component.** With an `Object` target, the component variable only has a contextually safe type, not automatically `String` even if the object currently holds a string.
4. **Testing non-reifiable types from `Object`.** `instanceof List<String>` or `instanceof Box<String>(...)` does not become checked just because you write the type argument explicitly.
5. **Confusing `Box(var x)` with a constructor or raw cast.** In a record pattern position, Java contextually infers the type argument and matches record components.
6. **Using methods beyond the inferred type.** When a variable has type `Object`, do not call `toUpperCase()` directly; you must add `instanceof String text` or change the input signature to preserve the type information.
7. **Using raw types to bypass the compiler.** Raw types increase the risk of heap pollution and unchecked operations; they do not provide runtime verification of generic arguments.
8. **Ignoring component nullability.** A pattern variable of type `String` can still receive a `null` component in a matching record pattern.
9. **Confusing version milestones.** Java 17 supports type patterns for `instanceof` but does not support finalized record patterns; the `Box(var x)` syntax and record patterns in `switch` in this lesson require Java 21+.
10. **Over-interpreting printed output.** `value.getClass() == String.class` only proves the runtime class of a component value; it does not prove that `Box` carries the `String` type argument in a way the JVM fully checks.

## 13. How to decide when writing code

When you want to use generics in pattern matching, proceed in order:

1. **Determine the static type of the target at the check site.** Is it `Box<String>`, `Box<?>`, raw `Box`, `Object`, or some generic interface?
2. **Determine the pattern kind.** Is it a regular type pattern or a record pattern with components? Finalized record patterns are only in Java 21+.
3. **If it is a generic record pattern:** is the type argument declared explicitly or does the compiler need to infer it? Do the constraints from the target and bounds provide enough information to infer?
4. **Inspect the actual type the compiler assigns to the component variable.** Is it `String`, `Integer`, `Object`, or a bounded/wildcard type? Only call APIs present on that type.
5. **Check for checked conversions.** Do not force an `Object` target into a concrete generic record type if it requires an unchecked conversion.
6. **Check nullability and flow scope.** A pattern variable is only valid when the pattern matches and within the allowed control-flow scope; a component inside a record can still be `null`.
7. **Run on the right Java version.** Java 17 projects should use `instanceof List<?>`/regular type patterns and check each component; Java 21+ can use record pattern inference.

A quick test to verify inference yourself: change the target declaration from `Box<String> box` to `Object box` and see whether the call `text.toUpperCase()` is still accepted by the compiler. If not, that shows **the generic information came from the static type of the target**, not from "detecting" `String` at runtime.

## Official references

- [Oracle Java SE 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html): generic records, type inference, `var`, and nested record patterns.
- [Java Language Specification 21 — `18.5.5 Record Pattern Type Inference`](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html#jls-18.5.5): type argument inference rules for generic record patterns.
- [Oracle Java 21 — Java Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): milestone standardizing record patterns and pattern matching for `switch`.
