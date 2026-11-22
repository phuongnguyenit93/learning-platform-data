# Reading and Resolving `inference variable ... has incompatible bounds` Messages in Java Generics

## 1. Learning objectives

After this lesson, you will be able to:

- Identify the **type variable being inferred** (`T`, `U`, `K`, `V`, etc.) in a `javac` error message and locate the exact generic method that introduced it.
- Read the `equality constraints`, `lower bounds`, and `upper bounds` groups, and understand why they cannot be satisfied simultaneously.
- Distinguish errors caused by **target types**, passed arguments, generic bounds (`extends`), invariance of `List<T>`, and APIs using nested generics such as `Comparator.comparing` or `Collectors.toMap`.
- Fix errors by clarifying **data type semantics** or adjusting generic signatures, rather than casting blindly.

Scope: **compile-time type inference in Java 17+**. These are static type-checking errors, not errors caused by type erasure at runtime.

## 2. A typical error message

Consider the file `Broken.java`:

```java
import java.util.List;

public class Broken {
    static <T> List<T> singleton(T value) {
        return List.of(value);
    }

    public static void main(String[] args) {
        List<String> words = singleton(42); // Does not compile
    }
}
```

Run:

```bash
javac Broken.java
```

The core part of the `javac` message looks like this (formatting, full class names, and line numbers may vary across JDK versions):

```text
incompatible types: inference variable T has incompatible bounds
    equality constraints: java.lang.String
    lower bounds: java.lang.Integer
```

Do not read only the "incompatible types" line. Read all three parts:

| Component | How to interpret in the example |
| --- | --- |
| `inference variable T` | `T` in the declaration `<T> List<T> singleton(T value)`, the unknown the compiler needs to solve for. |
| `equality constraints: String` | Because the result must be assigned to `List<String>`, the return signature `List<T>` forces `T` to be `String`. |
| `lower bounds: Integer` | The argument `42` is boxed to `Integer`; to pass it to parameter `T`, the argument's type must be compatible with `T` (roughly, `Integer` is a lower bound of `T`). |

Both constraints coexist, demanding that `T` both equal `String` and accept an `Integer` value. There is no choice of `T` satisfying both, so the compiler stops.

**"Bounds" here refers to constraints of the type inference problem**, not necessarily that you wrote `T extends ...`. A method declaring only `<T>` can still report `incompatible bounds`.

## 3. Where does Java infer types from?

Revisit the signature:

```java
static <T> List<T> singleton(T value)
```

At the call `singleton(42)`, the compiler considers simultaneously:

1. **Type of the argument expression**: literal `42` has type `int`; when matching a reference type parameter `T`, Java considers boxing to `Integer`.
2. **Target type**: the assignment `List<String> words = ...` requires an expression compatible with `List<String>`.
3. **Method signature**: parameter type `T` and return type `List<T>` establish relationships among the argument, result, and target type.
4. **Declared generic bounds**, if any: e.g., `<T extends Number>` adds the condition that `T` must be a subtype of `Number`.

This is a form of compile-time *constraint solving*. Java does not run the program and guess types; if inference fails, no bytecode is generated.

### 3.1. Three common constraint groups

- **Equality constraints** (`T = X`): typically appear when a parameterized structure and a target type require the exact same type argument, e.g., `List<T>` must be compatible with `List<String>`. Because Java generics are **invariant**, `List<Integer>` is not a subtype of `List<Number>`.
- **Lower bounds** (`L <: T`): `T` must be broad enough to accept type `L` of an input value; e.g., `Integer` must be compatible with `T`.
- **Upper bounds** (`T <: U`): `T` must satisfy an upper limit, such as `T extends Number` or a `Comparable` bound of an API.

Read `A <: B` as "`A` is a subtype of `B`". This is a helpful mental model when debugging; Java's actual inference algorithm also accounts for expression conversions, capture conversion, and constraint reduction steps.

### 3.2. Do not misread a type variable name as an actual class

In the message:

```text
inference variable U has incompatible bounds
```

`U` is usually just the second type parameter of a library method, **not a class named `U`**. For example, `Comparator.comparing` declares two type parameters `T` (the object to compare) and `U` (the comparison key type). To find out what `U` is, check the generic declaration of the method at the error site, not just the local variable where the `^` caret points.

## 4. Scenario 1: Target type conflicts with argument type

Invalid snippet:

```java
List<String> words = singleton(42);
```

There are at least three fixes, each carrying a different meaning:

```java
List<Integer> numbers = singleton(42);             // Want a list of numbers
List<String> words = singleton(String.valueOf(42)); // Want a list of strings
List<Number> values = singleton(42);                // Want a general numeric type
```

- Fix the **target type** if the value is truly a number.
- **Convert the data** intentionally if the domain needs a string.
- Choose a broader type (`Number`) if the API needs to accept multiple numeric types. Do not change it to `Object` just to silence the error if you still need `String`-specific operations later.

A seemingly plausible approach that is still wrong:

```java
List<String> words = Broken.<String>singleton(42); // Still an error
```

Explicitly writing `<String>` merely demands `T = String` earlier; it does not turn `Integer` into `String`.

### 4.1. Role of `var`

```java
var result = singleton(42); // Infers result as List<Integer>
```

Here there is no `List<String>` target imposed on the call, so Java can infer `T` from the argument. However, changing every declaration to `var` is not a general solution: `var` can cause the inferred type to differ from the API contract you intended. Verify the inferred type before deciding.

## 5. Scenario 2: `extends` bound conflicts with target type

A method accepting only numeric types:

```java
static <T extends Number> T keepNumber(T value) {
    return value;
}
```

The following call is invalid:

```java
String text = keepNumber(10); // Does not compile
```

We simultaneously have:

- `T` must satisfy `T extends Number` → `T` cannot be `String`.
- The expression is assigned to `String` → the target type wants a `String` result.
- The integer argument introduces a constraint from `Integer`.

Fix according to intent:

```java
Number value = keepNumber(10);               // Keep as number
String text = keepNumber(10).toString();     // Convert number to string
```

The error message may display `upper bounds: Number` (or a more complex representation when multiple bounds exist) alongside constraints from the target type. Note that not every `upper bounds` line comes from an `extends` written in your own method; it can also come from the signature of a called API.

## 6. Scenario 3: API requires a `Comparable` key, but the key is not comparable

General signature of the single-argument overload:

```java
static <T, U extends Comparable<? super U>>
Comparator<T> comparing(Function<? super T, ? extends U> keyExtractor)
```

The snippet below is invalid:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

record Packet(String id, byte[] payload) {}

List<Packet> packets = new ArrayList<>();
packets.sort(Comparator.comparing(Packet::payload)); // Does not compile
```

`Packet::payload` returns `byte[]`. In `Comparator.comparing`, `U` must be a type comparable via `Comparable<? super U>`; the array `byte[]` **does not implement `Comparable`**. Thus the compiler may report:

```text
inference variable U has incompatible bounds
    upper bounds: Comparable<? super U>
    lower bounds: byte[]
```

The fix depends on the desired **ordering rule**.

If sorting by payload length:

```java
packets.sort(Comparator.comparingInt(p -> p.payload().length));
```

`comparingInt` takes an `int` key and does not require byte arrays themselves to be `Comparable`. If the domain genuinely needs to compare byte contents, provide a `Comparator<byte[]>` with explicit semantics via the two-argument overload `Comparator.comparing(keyExtractor, keyComparator)`.

**Do not** fix by casting `(Comparable) packet.payload()` because arrays do not magically become `Comparable`; such a cast only defers the problem to a runtime error.

## 7. Scenario 4: Nested generics in Stream/Collector

Example:

```java
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

Map<String, Long> lengths = Stream.of("a", "abc")
        .collect(Collectors.toMap(Function.identity(), String::length)); // Invalid
```

`String::length` returns `int`, which is boxed to `Integer` when a reference type is needed. However, the target type requires **the `Map` values to be `Long`**. `Integer` and `Long` are two different classes; Java does not automatically perform an `int -> long -> Long` conversion chain in this generic type inference context.

To debug, separate the contracts:

```text
Target:            Map<String, Long>
toMap(keyMapper, valueMapper):
                   Map<K, U>
keyMapper:         String -> String  => K matches String
valueMapper:       String -> int     => U receives Integer (via boxing)
Target requires:   U = Long
Conflict:          Integer is incompatible with Long
```

Two proper fixes:

```java
Map<String, Integer> lengthsAsInt = Stream.of("a", "abc")
        .collect(Collectors.toMap(Function.identity(), String::length));

Map<String, Long> lengthsAsLong = Stream.of("a", "abc")
        .collect(Collectors.toMap(Function.identity(), s -> (long) s.length()));
```

In the second approach, `(long) s.length()` produces a `long` value, which is then boxed to `Long`. Converting at the **value-producing expression** keeps the contract clearer than casting after collecting.

When an error appears right at `.collect(...)`, `.map(...)`, or `Comparator.comparing(...)`, trace back into the lambda/method reference inside. The error caret may point to the outermost call while the conflict lies in the type returned by the callback.

## 8. Scenario 5: Invariance and `extends`/`super` wildcards

Suppose we have the method:

```java
static <T> void copy(List<T> target, List<T> source) {
    target.addAll(source);
}
```

This call is invalid:

```java
List<Number> target = new ArrayList<>();
List<Integer> source = List.of(1, 2);
copy(target, source); // Cannot infer a single T
```

Even though `Integer extends Number`, Java does **not** treat `List<Integer>` as `List<Number>`. When both parameters have the form `List<T>`, the method forces both arguments to match **the exact same** `T`. You may see messages about `incompatible bounds`, `incompatible equality constraints`, or "cannot infer type-variable(s)" depending on the context and compiler version.

If the true intent is *reading elements from source and adding them to target*, wildcard notation makes the contract accurate:

```java
static <T> void copy(
        List<? super T> target,
        List<? extends T> source) {
    for (T item : source) {
        target.add(item);
    }
}
```

When called with `List<Number>` and `List<Integer>`, `T = Integer` can be chosen:

- `source` of type `List<? extends Integer>`: elements can be read as `Integer`.
- `target` of type `List<? super Integer>`: `Integer` elements can be added to `List<Number>`.

This is the **PECS** rule: *Producer Extends, Consumer Super*. Do not replace `List<T>` with wildcards mechanically. Only use wildcards when they accurately express the data direction and read/write permissions the API intends to support.

## 9. Systematic debugging workflow

When you get the message, trace from the error site to the constraints:

1. **Keep the failing example intact** and run `javac -Xdiags:verbose Broken.java` when more detail about methods/overloads is needed. Use a JDK and compiler options consistent with your project.
2. **Identify the generic method** appearing in the failing expression. Find the `<T>` or `<T,U>` declaration, parameter types, return type, and `extends` bounds. For library APIs, check the signature in Javadoc or the corresponding JDK source.
3. **Pinpoint the exact inference variable** mentioned by the compiler, such as `U` in `Comparator.comparing` being the key type; do not confuse it with `T`, the element type.
4. **Note the target type** at the assignment, enclosing method parameter, or lambda return type. A generic expression may be constrained by its outer context.
5. **Note the actual types** of each argument and lambda/method reference: primitives, boxing, array types, generic types, wildcards, `null`, and overloads can all affect selection.
6. **Lay the three constraint groups side by side**: equality, lower, upper. Find the incompatible pair: `String`/`Integer`, `Long`/`Integer`, or `byte[]`/`Comparable`.
7. **Choose a fix that matches data semantics**: change the target type, convert at the source, select an overload taking a `Comparator`, adjust generics/wildcards, or fix the API if poorly designed. Then recompile and verify behavior.

Quick reference table:

| Symptom | Where to check first | Typical fix direction |
| --- | --- | --- |
| `equality constraints: String`, `lower bounds: Integer` | Target type and generic method arguments | Align types or convert the data. |
| `upper bounds: Comparable...`, `lower bounds: byte[]` | Key type returned by the key extractor | Change key to an orderable type or pass an explicit `Comparator`. |
| `U` inferred as `Integer` while target requires `Long` | Value-transforming function in Stream/Collector | Intentionally produce `long`/`Long` in the mapper. |
| Two `List`s carrying different element types | Signature using `List<T>` in multiple positions | Determine whether `? extends T`/`? super T` is needed. |
| Error points to a lambda or outer method call | Parameter types and return value inside the lambda | Add explicit local types or split the expression to isolate the conflict. |

### 9.1. Technique for splitting complex expressions

When code is long, declare an explicit type at an intermediate step to clarify where the constraint arises:

```java
Function<String, Long> lengthMapper = s -> (long) s.length();

Map<String, Long> lengths = Stream.of("a", "abc")
        .collect(Collectors.toMap(Function.identity(), lengthMapper));
```

If the `Function<String, Long>` declaration line fails to compile, the issue is inside the lambda. If that declaration works while `.collect` fails, inspect the signatures of `collect`, `toMap`, the stream element type, and the target type.

You can try a **type witness** to test a hypothesis:

```java
List<Integer> numbers = Broken.<Integer>singleton(42);
```

A type witness only specifies the type to infer; it **does not cure semantic conflicts**. If you choose `<String>` while passing `42`, the error remains valid.

## 10. Complete, runnable Java 17+ example

The following example shows intentional fixes for each scenario: choosing the right target type, `copy` with PECS, comparing by an `int` key, and converting `int` to `long` when building a `Map`.

Create the file `InferenceBoundsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class InferenceBoundsDemo {
    record Packet(String id, byte[] payload) {}

    static <T> List<T> singleton(T value) {
        return List.of(value);
    }

    static <T> void copy(List<? super T> target, List<? extends T> source) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        List<String> names = singleton("Java");
        List<Integer> ids = singleton(42);

        List<Number> numbers = new ArrayList<>();
        copy(numbers, List.of(1, 2));

        List<Packet> packets = new ArrayList<>(List.of(
                new Packet("long", new byte[] {1, 2, 3}),
                new Packet("short", new byte[] {7})
        ));
        packets.sort(Comparator.comparingInt(p -> p.payload().length));

        Map<String, Long> lengths = Stream.of("a", "abc")
                .collect(Collectors.toMap(Function.identity(), s -> (long) s.length()));

        System.out.println(names);
        System.out.println(ids);
        System.out.println(numbers);
        System.out.println(packets.stream().map(Packet::id).toList());
        System.out.println(lengths.get("abc"));
    }
}
```

Compile/run from the directory containing the file:

```bash
javac InferenceBoundsDemo.java
java InferenceBoundsDemo
```

Exact output:

```text
[Java]
[42]
[1, 2]
[short, long]
3
```

Explanation: `names` and `ids` have element types matching their inputs; `copy` allows placing `Integer` into `List<Number>`; `packets` sorts by payload element count so `short` precedes `long`; the value for key `"abc"` is a `Long` representing length 3.

## 11. Other "fixes" that easily cause bugs

- **Raw/unchecked casts** like `(List<String>) (List<?>) someList` can hide data mismatches, generate unchecked warnings, and cause `ClassCastException` when elements are used. They do not prove generic constraints were properly resolved.
- **Using raw types** (`List` instead of `List<String>`) loses compile-time type checking. Only use them when interoperating with legacy APIs with explicit warning handling, not as a normal fix for inference errors.
- **Adding `<Object>` everywhere** may make code compile, but discards type information, forces casts on reads, and masks flawed API designs.
- **Concluding that `List.of(1, "a")` always fails** is wrong: Java can infer a common supertype for different arguments when context permits. The question is whether the inferred type satisfies a specific contract (such as `List<String>`).
- **Assuming boxing means all numeric conversions are valid** is wrong: `Integer` is not a subtype of `Long`, and generic type inference does not automatically convert an `Integer` object into a `Long` object.
- **Fixing only the line underlined by the compiler** can miss the root cause inside a lambda, method reference, or return type of a deeply nested call.

## 12. Self-check comprehension

**Exercise 1.** Given `static <T> List<T> singleton(T value)`, why does `List<String> names = singleton(7)` fail while `List<Integer> ids = singleton(7)` is valid?

<details>
<summary>Answer hint</summary>

The first target type sets `T = String`, whereas the argument supplies `Integer`. The second target type sets `T = Integer`, matching the boxed argument. The fix depends on intent: `singleton("7")` if strings are wanted, or `List<Integer>` if numbers are wanted.

</details>

**Exercise 2.** Why cannot `Comparator.comparing(Packet::payload)` be used directly when `payload()` returns `byte[]`? If you only need to sort by byte count, what should replace it?

<details>
<summary>Answer hint</summary>

`comparing` requires key `U` to implement `Comparable<? super U>`; `byte[]` does not implement that interface. Use `Comparator.comparingInt(p -> p.payload().length)` to sort by length.

</details>

**Exercise 3.** Which method parameters should `List<Number> target` and `List<Integer> source` go with when only copying elements from `source` to `target`?

<details>
<summary>Answer hint</summary>

You can declare `<T> void copy(List<? super T> target, List<? extends T> source)` and add each element read from the source into the target. In this case, inferring `T = Integer` is suitable. Make sure you clearly understand producer/consumer roles before applying wildcards.

</details>

## 13. Takeaways for real-world projects

A type inference variable cannot have a valid solution if it is simultaneously forced to equal one type, required to accept an incompatible argument type, and/or required to satisfy an unachievable upper bound. Read **type variable name → declaration site → equality/lower/upper bounds → target type and arguments → data semantics**, then fix the constraint that is actually wrong.

The `inference variable ... has incompatible bounds` message is the compiler's **clue for solving the type puzzle**. Once each clue is translated into relationships between concrete types, a seemingly cryptic error usually turns into a very clear design mismatch or data conversion issue.
