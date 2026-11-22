# Checking Generics, Type Inference, and Uninferable Cases in Java

Java checks type validity at **compile time**. With generics, this task is not merely comparing two class names: the compiler must also determine **type arguments**, apply **bounds**, check assignment/argument compatibility, resolve overloads, and often automatically find the type arguments of a generic method or constructor call. That automatic discovery process is called **type inference**.

When inference succeeds, the program is usually concise and still type-safe. When it fails, `javac` may report `cannot infer type arguments`, `cannot infer type-variable(s)`, or `inference variable ... has incompatible bounds`. To fix it properly, you must know which constraints the compiler is collecting and why no type satisfies them.

This lesson uses Java 17+ and the rules of the Java Language Specification (JLS). Intentionally erroneous examples are marked separately; do not put them into the same runnable program.

## 1. What are generics and what does the compiler check?

A generic declaration declares **type parameters** to define a class, interface, record, or method generically:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T` is the *type parameter* of `Box`. When using `Box<String>`, `String` is the *type argument*. The compiler knows that `get()` returns `String` at the call site, instead of forcing the programmer to cast from `Object`.

Generics help check relationships such as:

- `Box<String>` accepts `String` upon creation and returns results of type `String`.
- `List<Integer>` cannot be assigned directly to `List<Number>` because normal generic types are **invariant**.
- `<T extends Number>` only allows type arguments satisfying the `Number` bound.
- `List<? extends Number>` and `List<? super Integer>` describe sets of types with different relationships; how you read from and write to them differs.
- Overloads, generic methods, lambdas, and method references may need a **target type** to determine a valid expression.

The fact that a call does not have `<String>` or `<Integer>` written explicitly **does not** mean type checking is skipped. The compiler must infer the type arguments so that the call's constraints are satisfied.

## 2. Distinguishing three things: declared type, inferred type, and runtime type

```java
List<String> words = new ArrayList<>();
```

`List<String>` is the declared type of the variable. `ArrayList<>` uses the **diamond operator**, letting the compiler infer the type argument matching the context, which here is `String`.

```java
var words = new ArrayList<String>();
```

`var` lets the compiler infer the **local variable type** from the initializer expression; the result here is `ArrayList<String>`. `var` does not create a "dynamic" variable and does not disable generic checking.

```java
var values = new ArrayList<>();
values.add("A");
values.add(10);
```

Without a more specific target type, the diamond constructor in this example infers the element type `Object`. Both `String` and `Integer` can be assigned to `Object`. The compiler does not change the type argument of `values` to `String` just because it later sees `add("A")`.

Finally, the runtime JVM uses **type erasure** for most generic type parameters. Static type information is checked by the compiler before generating bytecode; this does not mean each `List<String>` has a different runtime class from `List<Integer>`. Therefore `instanceof List<String>` is invalid: this specific element check is not guaranteed at runtime due to erasure.

**Three different questions:** what is the declared type; which type argument did the compiler infer; what class/object does runtime actually carry? Do not mix these three layers when interpreting errors.

## 3. Generic methods and sources of constraints for inference

A generic method declares type parameters before the return type:

```java
static <T> T identity(T value) {
    return value;
}
```

In the call `String name = identity("Lan");`, the compiler finds `T` such that the argument `"Lan"` is valid for parameter `T`, while the result is usable where `String` is expected. In this case, `T = String` is a suitable choice.

There are three common sources of constraints:

1. **Passed arguments:** `identity(42)` creates a relationship from the `Integer` type of the argument expression to parameter `T`.
2. **Declared bounds:** `<T extends Number>` requires the inferred type to fall within the type range permitted by `Number`.
3. **Result context (*target type*):** assignments, `return`, certain argument contexts, and lambdas can constrain the return type of a generic invocation.

Example:

```java
static <T> List<T> singleton(T element) {
    return List.of(element);
}

List<String> a = singleton("x");
List<Number> b = singleton(42);
```

In `b`, the compiler can use the target type `List<Number>` to choose `T = Number`, while still accepting the argument `Integer` because `Integer` is a subtype of `Number`. **There is no general rule that inference always picks the exact runtime class of the argument as `T`.** Target types, bounds, and type compatibility all participate in the decision.

The JLS describes the generic method inference algorithm via forming and solving constraint systems in ``18`. This is a rule-based mechanism, not the compiler guessing from variable names or runtime data.

## 4. Complete Java 17+ example: inference and type checking

Save the file `GenericInferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Function;

public class GenericInferenceDemo {
    static <T> List<T> singleton(T element) {
        return List.of(element);
    }

    static <T extends Number> double twice(T number) {
        return number.doubleValue() * 2;
    }

    static <T extends Comparable<? super T>> T greatest(
            List<? extends T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("empty values");
        }
        T best = values.get(0);
        for (T candidate : values) {
            if (candidate.compareTo(best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    static <T> void copy(List<? super T> destination,
                         List<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    record Pair<A, B>(A first, B second) {}

    public static void main(String[] args) {
        List<String> names = singleton("Lan");
        System.out.println("names=" + names);

        System.out.println("twice=" + twice(4));
        System.out.println("greatest=" + greatest(List.of(3, 9, 2)));

        List<Number> numbers = new ArrayList<>();
        copy(numbers, List.of(3, 5));
        System.out.println("copy=" + numbers);

        Pair<String, Integer> pair = new Pair<>("id", 7);
        System.out.println("pair=" + pair.first() + ":" + pair.second());

        List<String> empty = Collections.emptyList();
        System.out.println("emptySize=" + empty.size());

        Function<String, Integer> length = String::length;
        System.out.println("length=" + length.apply("Java"));
    }
}
```

Compile/run from the directory containing the file with JDK 17 or higher:

```bash
mkdir out
javac -encoding UTF-8 -d out GenericInferenceDemo.java
java -cp out GenericInferenceDemo
```

Exact stdout:

```text
names=[Lan]
twice=8.0
greatest=9
copy=[3, 5]
pair=id:7
emptySize=0
length=4
```

Part-by-part explanation:

- `singleton("Lan")` infers `T = String` and returns `List<String>` according to the target type.
- `twice(4)` boxes `int` to `Integer` to fit the generic type parameter `T extends Number`; the method returns primitive `double`.
- `greatest(List.of(3, 9, 2))` uses an element type comparable via `Comparable<? super T>`; the result is `9`.
- `copy` expresses the relationship of reading from `List<? extends T>` and writing into `List<? super T>`; `Integer` matches the destination `List<Number>`.
- `new Pair<>("id", 7)` uses the diamond operator to infer the type arguments of the generic record constructor in the `Pair<String, Integer>` context.
- `Collections.emptyList()` is a generic method returning `List<T>`; the target `List<String>` enables inferring `T = String` even though the method has no arguments.
- `String::length` is a method reference that needs the target functional interface `Function<String, Integer>` for the compiler to determine the call signature.

No type parameter is "discovered" by reading `List` data at runtime. Every decision in the example is checked from signatures, expression types, and compile-time context.

## 5. Bounds: mandatory conditions on type parameters

A generic declaration can restrict type arguments:

```java
static <T extends Number> double squared(T value) {
    return value.doubleValue() * value.doubleValue();
}
```

`squared(3)` and `squared(2.5)` are valid because `Integer` and `Double` inherit from `Number`. `squared("3")` is invalid: `String` does not satisfy the `Number` bound.

A bound can include one class or interface, and multiple interfaces:

```java
static <T extends Number & Comparable<T>> T retain(T value) {
    return value;
}
```

In Java, if there is a class bound, it must come before the interface bounds separated by `&`. This example can accept `Integer` because `Integer extends Number` and implements `Comparable<Integer>`; you should not conclude that every subclass of `Number` is valid for this bound.

A special commonly used form:

```java
static <T extends Comparable<? super T>> T chooseMax(
        T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

The `? super T` supports types implementing `Comparable` for an appropriate supertype. A classic example is `Collections.max`, which has a type constraint along these lines. This is a case of **a bound declared in the method signature**, distinct from a wildcard in a variable's parameter.

If the compiler reports `incompatible bounds`, do not just add a cast: ask whether the constraints from the inputs, target type, and `extends` can all hold simultaneously.

## 6. Invariance of generic types: List<Integer> is not List<Number>

`Integer` is a subtype of `Number`, yet **`List<Integer>` is not a subtype of `List<Number>`**. Intentionally non-compiling example:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = integers; // error: incompatible types
```

If the assignment were allowed, a caller could add a `Double` into a list that originally declared it only holds `Integer`. Generics block this at compile time.

Two valid designs depending on intent:

- **Read-only as Number:** accept `List<? extends Number>`. You can retrieve elements with type `Number`, but you cannot arbitrarily add an `Integer` or `Double` into the list.
- **Wanting a list storing multiple subtypes of Number:** create `List<Number> numbers = new ArrayList<>();` and add `Integer` and `Double` into that list.

Example:

```java
List<? extends Number> source = List.of(1, 2);
Number first = source.get(0); // valid
// source.add(3);              // invalid

List<Number> mixed = new ArrayList<>();
mixed.add(1);
mixed.add(2.5);
```

The snippets in this section use imports `java.util.List` and `java.util.ArrayList`; they illustrate lines inside a method, not a standalone file. Writability with a wildcard depends on both the element type and the wildcard kind, and should not be mechanically inferred from `Number` subtyping.

## 7. Wildcards, capture, and the PECS principle

A wildcard represents an unknown type subject to bounds:

| Type | Safe to read out | Safe to write in |
| --- | --- | --- |
| `List<? extends Number>` | `Number` | Cannot arbitrarily add a concrete `Number`; only `null` |
| `List<? super Integer>` | `Object` | Can add `Integer` (and appropriate subtypes) |
| `List<?>` | `Object` | Cannot add concrete values other than `null` |
| `List<Number>` | `Number` | Can add values that are subtypes of `Number` |

The mnemonic rule **PECS: Producer Extends, Consumer Super**. If a parameter mainly **produces** values of type `T` for us to read, consider `? extends T`. If a parameter mainly **consumes** values of type `T` that we write into it, consider `? super T`. This is an API design heuristic, not a replacement for checking exact read/write requirements.

A well-known error case is **capture of ?**:

```java
static void replaceFirst(List<?> values, Object element) {
    values.set(0, element); // invalid
}
```

The compiler does not know the element type represented by the wildcard. A `List<?>` might actually be a `List<String>`, so it cannot allow putting an arbitrary `Object` into it. Blind casts or switching to raw types can create runtime errors.

When you need to preserve the exact unknown element type of the same list, use a **capture helper**:

```java
import java.util.List;

public class CaptureDemo {
    static void swapFirstTwo(List<?> list) {
        swapCaptured(list);
    }

    private static <T> void swapCaptured(List<T> list) {
        T first = list.get(0);
        list.set(0, list.get(1));
        list.set(1, first);
    }

    public static void main(String[] args) {
        List<String> words = new java.util.ArrayList<>(
                List.of("a", "b", "c"));
        swapFirstTwo(words);
        System.out.println(words);
    }
}
```

Run the file `CaptureDemo.java`:

```bash
javac -encoding UTF-8 CaptureDemo.java
java CaptureDemo
```

Stdout:

```text
[b, a, c]
```

When calling `swapCaptured(list)`, the compiler treats the wildcard at that call site as a concrete but unnamed **capture type**; the `<T>` helper keeps the `get`/`set` operations consistent. The program does not insert an object of an incompatible type into the list.

Another note: the invariance of `List<T>` and differences between wildcards cannot be bypassed by inferring `T` as `Object` when a method signature requires a concrete `List<T>`.

## 8. Type inference from context: target typing and poly expressions

Consider:

```java
List<String> names = java.util.Collections.emptyList();
```

`emptyList()` has no arguments, so looking at inputs alone is not enough to determine `T`. The assignment provides the **target type** `List<String>`; the generic method invocation can use that context to choose `T = String`.

If written as:

```java
var names = java.util.Collections.emptyList();
```

there is no `List<String>` target from an explicit type declaration, so the inferred type may be `List<Object>`. Because `emptyList()` returns an immutable list, trying to `add` to it also causes `UnsupportedOperationException` at runtime; that is a **different** issue from inference.

Lambdas and method references also have the nature of **poly expressions** in contexts specified by the language:

```java
java.util.function.Function<String, Integer> length =
        text -> text.length();
```

The type of parameter `text` is determined from the target functional interface, not from a `String` annotation inside the lambda. Changing the target type can make the exact same lambda valid or invalid.

Example generic method declaration:

```java
static <T, R> R transform(
        T input,
        java.util.function.Function<? super T, ? extends R> f) {
    return f.apply(input);
}

int length = transform("Java", String::length);
```

Method reference `String::length`, input type `String`, return type `int`, and assignment to `int` enable the compiler to determine the appropriate types, including boxing when needed. Do not treat generic method inference and overload resolution as two processes that are always independent: rules on applicability and target typing can interact across multiple steps.

## 9. Overloading and inference interact with each other

A method name can have multiple overloads. Before choosing a valid call, the compiler evaluates candidate applicability, conversions, generic bounds, and specificity (*most specific*).

Simple example:

```java
static String show(Integer value) {
    return "Integer";
}

static String show(Number value) {
    return "Number";
}

// Inside a method:
String result = show(3); // "Integer"
```

The call using literal `3` can box to `Integer`, making the `show(Integer)` overload more specific than `show(Number)` for this example. With generic overloads and lambdas, candidate selection becomes even more complex; inference can participate in stages that determine applicability and results.

An **ambiguous** case that intentionally fails to compile:

```java
static void pick(java.io.Serializable value) {}
static void pick(Cloneable value) {}

// pick(null); // error: ambiguous reference
```

`null` can convert to both reference types, and in this situation neither candidate is more specific than the other. This is an overload resolution error; not every "cannot infer" error is caused by missing generic type arguments.

One way to fix it is to clarify intent:

```java
pick((java.io.Serializable) null);
```

In real code, casts should appear only when they reflect the true contract. Do not add casts to mask an ambiguous overload API.

## 10. Why does the compiler report it cannot infer?

Below are common error categories. Each snippet is marked **intentionally non-compiling**; the compiler may use different diagnostic phrasing across versions.

### 10.1 Constraints from List<T> and conflicting arguments

```java
static <T> void addValue(List<T> target, T value) {
    target.add(value);
}

// Inside a method:
List<String> words = new ArrayList<>();
addValue(words, 123); // invalid
```

From `List<String>`, the compiler has a constraint forcing `T` to match element `String`. Argument `123` requires boxing to `Integer` and demands compatibility with `T`. There is no single `T` satisfying both when the signature uses invariant `List<T>`. Choosing `T = Object` does not turn `List<String>` into `List<Object>`.

If a method only reads a set of elements and accepts values compatible at a supertype level, redesign the signature to match that need. If the method genuinely adds `Integer`, you must pass a list capable of holding `Integer`; do not switch `List<String>` to a raw type to "force past" the error.

### 10.2 Type argument violates bound

```java
static <T extends Number> T same(T value) {
    return value;
}

String text = same("hello"); // invalid
```

Type `String` does not satisfy `T extends Number`; target type `String` cannot make the bound disappear either. The fix is to pass a data type within the bound, or change the method's contract when the business logic truly does not require `Number`.

### 10.3 Result incompatible with target type

```java
static <T> T identity(T value) {
    return value;
}

String text = identity(123); // invalid
```

The argument passed in is `Integer`; the result is assigned to `String`. No valid conversion satisfies that requirement. This is a reasonable type error, not a lack of "hints" for the compiler. Writing `GenericClass.<String>identity(123)` (if the method belongs to the corresponding class) still does not turn an integer into a string.

### 10.4 Wildcard capture forbids writing an arbitrary value

```java
List<? extends Number> numbers = List.of(1, 2);
numbers.add(3); // invalid
```

`? extends Number` could represent `Integer`, `Double`, or another subtype. The compiler cannot guarantee that the value `3` is always compatible with the actual list. Use a read-only API, or change the destination type to `List<Number>` if it needs to accept multiple subtypes.

### 10.5 Missing a sufficiently specific target type

```java
var list = new ArrayList<>();
```

This snippet is **valid**, yet the compiler infers `ArrayList<Object>`, which may be broader than what the author intended. If the goal is a list holding only `String`, write:

```java
List<String> list = new ArrayList<>();
// Or, when wanting the variable to have type ArrayList<String>:
var other = new ArrayList<String>();
```

**Lacking a target type does not necessarily cause a compile error; sometimes it results in an overly broad inferred type.** Inspect the inference result in your IDE or rely on an appropriate assignment, rather than assuming the compiler will guess from subsequent statements.

### 10.6 Lambdas and method references lacking a functional context

```java
// var action = x -> x.toString(); // invalid
```

A lambda does not have an independent type of its own for `var` to adopt from the initializer. A target functional interface is required:

```java
java.util.function.Function<Object, String> action =
        x -> x.toString();
```

Similarly, a method reference needs a target functional interface or a generic invocation context that can supply it. Explicitly writing lambda parameter types, or placing the result in an explicitly typed variable, can help the compiler resolve the reference.

## 11. How to fix by root cause: signature, target type, or explicit type witness?

Do not assume every inference error should be solved by casting. Try principled approaches in order:

**A. Fix the input types to match the contract.** For `<T extends Number>`, pass `Integer`/`Double` instead of `String`. For `List<String>`, add only `String`.

**B. Use a concrete target type when needed.** Change `var empty = Collections.emptyList()` to `List<String> empty = Collections.emptyList()` if the goal is a list of `String`.

**C. Write an explicit type witness.** Sometimes a generic method cannot derive the type argument you intend to use from context alone:

```java
List<String> names = java.util.Collections.<String>emptyList();
```

The `ClassName.<Type>method(...)` form can make intent explicit. With static imports or complex method calls, qualifiers and syntax must follow Java grammar. A type witness is only valid when **all bounds and arguments remain compatible**; it has no power to bypass type checking.

**D. Redesign the generic method.** If a method both reads from a source list and writes into a destination with a subtype relationship, you should normally use:

```java
static <T> void copy(List<? super T> target,
                     List<? extends T> source) {
    for (T item : source) {
        target.add(item);
    }
}
```

With Java Collections, an equivalent utility often already exists like `Collections.copy`, though the contract of `Collections.copy` also requires the destination size to be at least the source size and **overwrites positions** rather than appending. The custom method here is solely to illustrate PECS/inference; do not equate the behavior of the two APIs.

**E. Split large expressions into typed intermediate variables.** Especially useful for Stream pipelines, `Comparator.comparing`, lambdas, and method references. Declaring `Function<Person, String> keyExtractor = Person::name;` can help pinpoint exactly which part the compiler cannot infer.

**F. Check overloads and imports.** If there are multiple valid/ambiguous candidates, fix the signature, rename the method, or specify the target explicitly instead of adding generic casts in unrelated places.

## 12. Stream, Comparator, and method references: practical cases

A standalone Java 17+ example:

```java
import java.util.Comparator;
import java.util.List;

public class ComparatorInferenceDemo {
    record Person(String name, int age) {}

    public static void main(String[] args) {
        List<Person> people = List.of(
                new Person("Minh", 23),
                new Person("Lan", 21)
        );

        List<String> names = people.stream()
                .sorted(Comparator.comparingInt(Person::age))
                .map(Person::name)
                .toList();

        System.out.println(names);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ComparatorInferenceDemo.java
java ComparatorInferenceDemo
```

Stdout:

```text
[Lan, Minh]
```

Because the Stream has element type `Person`, the compiler can infer that `Person::age` is a function extracting an `int` from a `Person`. `Comparator.comparingInt` provides the target functional interface, `sorted` accepts a valid comparator for stream elements, `map(Person::name)` produces `Stream<String>`, and `toList()` returns `List<String>` (which must not be used to add new elements later because this list does not support modification operations).

If you replace `Person::age` with a method reference whose parameter or return type does not match, the compiler may report an inference error on an "outer" call even when the cause is a method reference deep inside. In that case, split the chain into multiple explicitly typed declarations:

```java
Comparator<Person> byAge = Comparator.comparingInt(Person::age);
List<Person> sorted = people.stream().sorted(byAge).toList();
```

These are two illustrative statements **inside a method that has the `people` variable**, not a standalone file. Splitting makes diagnostics more accurate and easier to understand, without changing the computation intent.

## 13. Unchecked errors, raw types, and limitations due to type erasure

There are cases where code compiles with warnings yet does not guarantee type safety:

```java
import java.util.ArrayList;
import java.util.List;

public class RawTypeDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List raw = words;      // raw type: loses String element type checking
        raw.add(123);         // unchecked call, compiler may emit a warning

        String first = words.get(0); // ClassCastException at runtime
        System.out.println(first);
    }
}
```

This program **intentionally causes a runtime error** and has no successful stdout. `raw.add(123)` may compile with an *unchecked warning*, yet it has put an `Integer` into something viewed as `List<String>`. When retrieving the element via a reference typed generically as `List<String>`, the implicit cast to `String` fails.

To see the warnings more clearly, run:

```bash
javac -Xlint:rawtypes,unchecked RawTypeDemo.java
java RawTypeDemo
```

Do not expect verbatim diagnostics or stack traces to be identical across all JDKs. An `unchecked` warning means: the compiler cannot prove part of a conversion/method call is type-safe.

Another example due to erasure: you cannot write `new T[10]` inside a generic method body in the ordinary way; you cannot use `new List<String>[10]` or `instanceof List<String>` because those parameterized types are not reifiable. There are exceptions/safe alternatives using collections, `Class<T>` tokens, array factories, or generic helpers, but you should not mask limitations with unconditional raw casts.

**Key point:** generic inference operates at compile time, while the JVM needs to check the runtime types it actually retains. That is why many operations that seem natural for generic arrays or runtime type checks are rejected.

## 14. Type inference is not "finding an arbitrary common type"

In multi-argument calls, the compiler can find a common supertype or an *intersection type* while solving constraints. However, you cannot assume every pair of arguments should collapse to `Object`: the result is still constrained by the method signature, type bounds, generic invariance, and target context.

Example:

```java
static <T> List<T> pair(T left, T right) {
    return List.of(left, right);
}

// Can choose T wide enough to accept both Integer and Double:
List<Number> values = pair(1, 2.5);
```

This call is **valid**: the compiler can choose a `T` compatible with both arguments and the target `List<Number>`. This differs from the `addValue(List<String>, 123)` example because `List<String>` in the invariant input position constrains the type argument more tightly.

If you write `List<String> values = pair(1, 2.5);`, you cannot use target `String` alone to make both `Integer` and `Double` compatible with `String`.

With bounded type parameters, the compiler must also ensure the subtype relationship with the upper bound. For example, `<T extends Number>` will not be inferred as `Object` to accept arbitrary arguments, because `Object` does not satisfy the `Number` bound.

## 15. Generic API signatures can make inference easy or hard

Consider two ways of declaring a function that reads elements:

```java
static <T> void printAll(List<T> values) {
    for (T value : values) {
        System.out.println(value);
    }
}

static void printNumbers(List<? extends Number> values) {
    for (Number value : values) {
        System.out.println(value);
    }
}
```

`printAll` can accept different `List<T>` types in **each call**. Yet if the method does not need to express or link `T` elsewhere in the signature, the wildcard `List<?>` can also express read-only intent. `printNumbers` accepts only lists whose elements fit Number; the wildcard allows `List<Integer>` or `List<Double>`.

Practical design rules:

- Use a **type parameter `<T>`** when you need to maintain a type relationship between two or more positions (parameters, result, callback, destination, source) or when the body logic needs that type name.
- Use a **wildcard** when you need to express read/write direction or acceptance of a family of types without needing to name the relationship.
- Avoid **raw types** unless interacting with legacy APIs with proper checking/isolation measures.
- Choose **bounds that are genuinely needed**; `<T extends Comparable<? super T>>` provides comparability, while also narrowing the usable types.
- Do not use `<T> T convert(Object value)` and cast inside as if the compiler could guarantee a real conversion. A generic signature with no link between input and output can hide runtime risks.

Good types give inference enough information and make errors appear in the right place. Ambiguous signatures force the compiler to pick a broader type than intended or fail to find a solution.

## 16. How to read `javac` errors along the semantic checking process

When encountering an inference-related message, look at these components:

| Diagnostic component | Question to answer |
| --- | --- |
| `required` / `found` | What type did the compiler expect, and what type is the expression providing? |
| `cannot infer type-variable(s)` | Which type parameters of the generic method/constructor need to be solved? |
| `inference variable T has incompatible bounds` | Which upper/lower/equality constraints conflict? |
| `equality constraints` | Which relationship forces a type variable to match a specific type argument? |
| `upper bounds` | Which types must the inferred type be a subtype of? |
| `lower bounds` | Which types must the inferred type be a supertype of? |
| `capture of ?` | Is a wildcard representing a specific yet unnamed type? |
| `reference to ... is ambiguous` | Are there multiple overloads where the compiler cannot determine one optimal candidate? |
| `unchecked conversion` | Is the compiler lacking type-safe proof due to raw types/erasure? |

Illustrative example of an inference error:

```java
static <T> void addValue(List<T> list, T value) {
    list.add(value);
}

List<String> words = new ArrayList<>();
addValue(words, 123);
```

It can be interpreted as: `List<T>` needs to be compatible with `List<String>` (tying `T` tightly to `String`), while argument `123` has type `int` and is boxed to `Integer`, which cannot be assigned to `String`. The actual error message text may vary, yet the type conflict lies in this exact relationship.

Do not fix it by removing generics, adding raw casts, or disabling warnings. Fix the **data logic** or API signature to match the desired type relationship.

## 17. A step-by-step inference debugging approach

1. **Minimize the failing call.** Keep one generic method/constructor and the relevant argument expressions; remove unnecessary chains and annotations.
2. **Write down the full signature.** List type parameters, upper bounds, each parameter's type, and the return type.
3. **Write down the static type of each argument.** Distinguish primitive literals, boxing, wildcards, raw types, generic parameters, lambdas, and method references.
4. **Write down the target type if present.** Assignment `List<String> x = ...` differs from `var x = ...`; calling a generic method inside another method's argument can have its own context.
5. **Test concrete type arguments on paper.** For example, does `T = String` satisfy the bounds and all arguments? Does `T = Number` break `List<String>` invariance?
6. **Check wildcards/capture.** Are you trying to write into a `? extends T` producer or extract an overly specific type from a `? super T` consumer?
7. **Split lambdas, method references, and chains.** Use typed intermediate variables to isolate which layer fails.
8. **Specify a type witness when the intent is valid.** If the compiler still reports an error with a type witness, it may be a real conflict rather than "poor inference."
9. **Enable appropriate warnings.** `javac -Xlint:unchecked,rawtypes` can pinpoint code that loses type safety.
10. **Check JDK version and compiler configuration.** Target typing mechanisms and library APIs evolve across Java versions; always compile with the project's exact `--release`/toolchain before concluding.

## 18. Self-check exercises

**Exercise 1.** Why is `List<Number> n = new ArrayList<Integer>();` invalid? Because generic types are invariant; if allowed, the `List<Number>` reference could insert a `Double` into a list that only holds `Integer`.

**Exercise 2.** Given `static <T> T identity(T value)`, is `String s = identity(42);` valid? No. The argument type and the target type are not simultaneously compatible with a `T` satisfying the signature's conversions.

**Exercise 3.** Does `List<String> xs = Collections.emptyList();` require writing `<String>` before `emptyList`? No, target typing is usually sufficient. Explicitly writing `Collections.<String>emptyList()` is still valid.

**Exercise 4.** Why does `List<? extends Number>` forbid adding an `Integer`? Because the wildcard could actually represent `Double` or another subtype of `Number`; only reading as `Number` is safe.

**Exercise 5.** Predict the output of `GenericInferenceDemo`: a single-name list, `twice(4) = 8.0`, `greatest` returns `9`, destination gets `3` and `5` appended, the record holds `id:7`, the empty list has size `0`, and `"Java".length() = 4`.

**Exercise 6.** When an API only wants to accept source `List<Integer>` and write results into destination `List<Number>`, should you use `<T> void copy(List<? super T>, List<? extends T>)` or `<T> void copy(List<T>, List<T>)`? Choose the first signature if the contract is genuinely producer/consumer copying; the second signature is restricted by invariance for lists with different type arguments.

## 19. Takeaways and authoritative documentation

Type inference only automatically finds type arguments for a **static constraint system**. Those constraints come from declared types, arguments, upper bounds, wildcards, target types, lambdas/method references, and overloads. The compiler is under no obligation to pick the type "the author seemed to intend" if there is insufficient evidence; even less can it bypass invariance, bounds, or type safety.

When a generics-related error appears, ask in order: **what type relationship does the generic method/class require; what does the compiler know about arguments and target; which constraints conflict; do we need to fix the data, the signature, or the context?** The answer is often clearer after splitting the call into a few explicitly typed variables.

References for checking official rules:

- [JLS `4 — Types, Values, and Variables](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html): type parameters, type arguments, wildcards, erasure, reifiable types.
- [JLS `5 — Conversions and Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html): conversions in assignments and method invocations.
- [JLS `15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12): applicability, overloading, target typing.
- [JLS `18 — Type Inference](https://docs.oracle.com/javase/specs/jls/se21/html/jls-18.html): forming, reducing, and solving constraint systems.
- [Java Tutorial — Wildcards](https://docs.oracle.com/javase/tutorial/java/generics/wildcards.html): producer/consumer and wildcard capture examples; consult the JLS as the authoritative semantic specification.