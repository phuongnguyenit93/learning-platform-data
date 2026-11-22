# Generic Constructors and Distinguishing Them from Constructors of a Generic Class in Java

## 1. Goal and Central Question

In Java, **generic classes** and **generic constructors** both use type parameters, yet they declare them in **two different scopes**:

- `class Box<T>`: `T` is a type parameter **of the class**, chosen when using types like `Box<String>`, `Box<Integer>`, etc.
- `<U> Box(U input)`: `U` is a type parameter **of the constructor itself**, inferred or specified per **object creation**.
- `class Box<T> { Box(T value) { ... } }`: the constructor uses the class's `T` but is **not a generic constructor in the sense of declaring its own type parameter**.
- A **regular class** without `<T>` can still declare a **generic constructor**.

This distinction matters when an object needs to store a type `T`, yet initialization data comes from a different type `U` and must be converted into `T`. It also clarifies why you can combine `new Holder<>(...)` with a converter function without manual casting.

This lesson focuses on **constructor syntax**, type parameter scope, type inference, bounds, overloading, and practical applications. The standalone example at the end is compatible with **Java 17+**.

## 2. First: A Generic Class's Constructor Is Not Necessarily a Generic Constructor

Consider a general class that simply holds a single value:

```java
// Illustrative snippet; place inside an appropriate Java file.
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

Box<String> greeting = new Box<>("Xin chào");
Box<Integer> quantity = new Box<>(5);
```

There are two layers to separate:

1. `<T>` after `Box` **declares the class's type parameter**.
2. The constructor `Box(T value)` **uses the already-declared parameter `T`**, without declaring any other type parameter of its own.

`Box<String>` establishes `T = String`, so the constructor accepts `String` and the getter returns `String`. `Box<Integer>` works similarly for `Integer`. If an incompatible type is passed, the compiler rejects it:

```java
// Box<Integer> wrong = new Box<Integer>("hello"); // Compile error.
```

The diamond `<>` in `new Box<>("Xin chào")` is merely notation **inferring the class's type argument** from context and constructor arguments. **Having a diamond does not mean a constructor is generic.**

Compare with a non-generic class:

```java
final class NameTag {
    private final String name;

    NameTag(String name) {
        this.name = name;
    }
}
```

`NameTag(String)` does not declare its own type parameter; `NameTag` has no type parameter either. Both `Box(T)` and `NameTag(String)` are regular constructors under the criterion of "whether the constructor declares its own type parameter".

## 3. Exact Syntax of a Generic Constructor

A constructor is called a **generic constructor** when the constructor itself has a type parameter declaration list, such as `<U>` or `<S extends Number>`, **placed before the constructor name**:

```java
import java.util.function.Function;

// Illustrative snippet.
final class ConvertedBox<T> {
    private final T value;

    <S> ConvertedBox(S source, Function<? super S, ? extends T> converter) {
        this.value = converter.apply(source);
    }

    T get() {
        return value;
    }
}
```

In the code above:

- `T` belongs to `ConvertedBox<T>`: it is the type of the stored data and the getter's return value.
- `S` belongs to the constructor `<S> ConvertedBox(...)`: it is the **source** type for a single instantiation.
- `Function<? super S, ? extends T>` expresses the conversion from source `S` to data compatible with `T`.
- After the constructor finishes, the object is simply `ConvertedBox<T>`; it **does not carry an extra class parameter `S`**.

Usage:

```java
ConvertedBox<Integer> length =
        new ConvertedBox<>("Java", String::length);
Integer n = length.get(); // 4.

ConvertedBox<String> numberText =
        new ConvertedBox<>(42, Object::toString);
String text = numberText.get(); // "42".
```

In the first call, the compiler must make `T = Integer` match the variable's target type while inferring `S = String` for the argument `"Java"`. In the second call, `T = String` and `S = Integer`. Changing the input source **does not change the meaning of the target type**.

General constructor syntax:

```java
// modifiers <type-parameters> ClassName(parameter-list) throws ExceptionType {
//     // constructor body
// }
```

**Do not declare a return type for a constructor**, not even `void`. The form `<U> Box(U source)` is still a constructor because `<U>` is followed by the **class name** `Box`, with no return type.

## 4. A Regular Class Can Still Have a Generic Constructor

A class does not need to declare `<T>` in order to declare a constructor with `<U>`. For example, a class that only wants to store a descriptive string from many kinds of sources:

```java
import java.util.function.Function;

// Illustrative snippet.
final class DisplayText {
    private final String content;

    <S> DisplayText(S source, Function<? super S, String> formatter) {
        this.content = formatter.apply(source);
    }

    String content() {
        return content;
    }
}

// Inside a Java method:
DisplayText count = new DisplayText(123, Object::toString);
DisplayText upper = new DisplayText("java", String::toUpperCase);
```

`DisplayText` is a **regular class**, with no type parameter on the class name. `S` exists only in the constructor declaration. Because `formatter` produces a `String`, the final data is always stored in the `String content` field.

Application scenario: the constructor accepts **multiple sources of different types**, while the resulting object has a fixed structure. In some APIs, a clearly named `static` factory or generic method can be easier to read than a general constructor; choose based on the actual initialization contract.

### A Constructor Can Use Multiple Type Parameters

```java
import java.util.function.BiFunction;

final class RenderedText {
    private final String rendered;

    <A, B> RenderedText(
            A first,
            B second,
            BiFunction<? super A, ? super B, String> format) {
        rendered = format.apply(first, second);
    }

    String value() {
        return rendered;
    }
}

// RenderedText view = new RenderedText("Lan", 9,
//         (name, score) -> name + ": " + score);
// view.value() is "Lan: 9".
```

`A` and `B` are two type parameters **of the constructor**; they can differ. Thus `<A,B>` expresses the contract more accurately than forcing both arguments into a single `T`. For the converter, `? super A` and `? super B` allow the function to accept appropriate supertypes, while the `BiFunction` output is `String`.

## 5. A Generic Class Can Have Both Regular and Generic Constructors

A class can declare two different constructors, each serving a separate initialization path:

```java
import java.util.Objects;
import java.util.function.Function;

final class Holder<T> {
    private final T value;

    // Regular constructor: only uses the class's T.
    Holder(T initial) {
        this.value = Objects.requireNonNull(initial);
    }

    // Generic constructor: also declares S belonging to the constructor itself.
    <S> Holder(S source, Function<? super S, ? extends T> mapper) {
        this.value = Objects.requireNonNull(mapper.apply(source));
    }

    T get() {
        return value;
    }
}
```

Calling both overloads:

```java
Holder<String> simple = new Holder<>("Lan");

Holder<Integer> transformed =
        new Holder<>("Spring", String::length);

String a = simple.get();        // "Lan".
Integer b = transformed.get();  // 6.
```

With the `Holder(T initial)` overload, the input already has a compatible type `T`, so no converter is needed. With `<S> Holder(S, Function<...>)`, the source can differ from the target type and needs an explicit conversion function.

A generic constructor **does not make the entire class generic in a new parameter**. The class only has `T`; the constructor's `S` cannot be accessed in getters or other methods unless they declare their own appropriate type parameters.

### Why Should You Not Declare `<T>` with the Same Name as the Class's `T`?

The following syntax may be valid yet causes confusion:

```java
class Confusing<T> {
    private final T value;

    // <T> on the constructor is a NEW T, shadowing the class's T in this signature.
    <T> Confusing(T input) {
        // this.value = input; // Invalid: the two Ts are not guaranteed to be the same.
        this.value = null; // Illustrates the design flaw only.
    }
}
```

Two identical `T` names do not mean they are the same type parameter. The `<T>` declared by the constructor **shadows** the class's type parameter `T` inside the constructor scope, breaking the safe relationship between `input` and the `value` field. In practice, **do not write** constructors like this; use `<S>` if you need a separate parameter, or omit `<...>` if the input must have the exact class type `T`.

## 6. How the Compiler Infers the Class Type and Constructor Type

When encountering:

```java
Holder<Integer> result = new Holder<>("Java", String::length);
```

The compiler has two related yet distinct tasks:

1. Find the type argument for the **class** `Holder<T>`, matching the target context `Holder<Integer>`, which means `T = Integer`.
2. Find the type argument for the **generic constructor** `<S> Holder(S, Function<? super S, ? extends T>)`, matching the source string and mapper, which means `S = String`.

The compiler checks whether `String::length` can be used to produce a result of type `Integer` for `Function.apply`. `String.length()` returns primitive `int`, which is boxed into `Integer` as needed.

### Diamond `<>` Applies to the Class's Type Parameters

```java
Holder<String> first = new Holder<>("Hi");
Holder<String> second = new Holder<String>("Hi");
```

`new Holder<>()` avoids repeating `String` on the right when the compiler has enough context. This is the **diamond operator**, not a constructor type parameter list. Whether selecting the generic overload or the regular overload, the `new` expression creates an object of class type `Holder<T>`.

### When Using `var`, Check What Type Is Inferred

```java
var text = new Holder<>("Java");
var length = new Holder<>("Java", String::length);
```

On the first line, the compiler can infer `Holder<String>` from the constructor receiving `"Java"`. On the second line, the mapper signature and lack of an explicit target type create a harder inference problem; do not assume the compiler will always infer the exact final type you want. To state the desired data contract clearly, declare the target type explicitly:

```java
Holder<Integer> length = new Holder<>("Java", String::length);
```

If inference becomes hard to read or the compiler reports it cannot solve the type constraints, you can supply an explicit type argument for the class or design a factory method with a clearer signature.

### Specifying Constructor Type Arguments Explicitly

Generic constructors support **explicit constructor type arguments** in the following form:

```java
// Assume class Holder<T> has generic constructor <S> Holder(S, Function<...>).
Holder<Integer> length =
        new <String> Holder<Integer>("Java", String::length);
```

`<String>` **placed after `new` and before the class name** is the type argument **of the constructor** `S`. `<Integer>` following `Holder` is the type argument **of the class** `T`. This syntax differs from calling a **generic method** like `Collections.<String>emptyList()`. Normally let Java infer constructor type arguments for conciseness; only write them explicitly when it genuinely helps diagnostics or clarifies the signature.

Do not use the form `new Holder<String><Integer>(...)`: Java does not place a constructor's type argument list after the type name. When specifying constructor type arguments explicitly, choose valid syntax like `new <String> Holder<Integer>(...)`.

## 7. Generic Constructors with Bounded Type Parameters

When object construction needs an operation available only on certain data types, add an upper bound right on the constructor's type parameter:

```java
import java.util.Collection;

final class NumericSummary {
    private final double total;

    <N extends Number> NumericSummary(Collection<N> values) {
        double result = 0;
        for (N value : values) {
            result += value.doubleValue();
        }
        this.total = result;
    }

    double total() {
        return total;
    }
}

// NumericSummary ints = new NumericSummary(List.of(1, 2, 3));
// NumericSummary doubles = new NumericSummary(List.of(1.5, 2.5));
// new NumericSummary(List.of("a", "b")); // Does not satisfy the Number bound.
```

`<N extends Number>` means **only the constructor** requires a source belonging to `Number` or a subtype; `NumericSummary` is not a generic class. The compiler permits calling `doubleValue()` because the bound guarantees that operation exists. Interface bounds also use the `extends` keyword, such as `<S extends CharSequence>`.

If multiple bounds are needed, use `<N extends Number & Comparable<N>>`; the class bound, if present, must precede the interfaces. Choose bounds sufficient for the constructor's operations, avoiding casts that can cause errors.

### A Bounded Constructor Is Not a Bounded Class

The two designs differ:

```java
// Class preserves numeric type T throughout the object's lifetime.
final class NumberHolder<T extends Number> {
    private final T value;
    NumberHolder(T value) { this.value = value; }
    T get() { return value; }
}

// Non-generic class; constructor temporarily uses N to read a numeric value.
final class DoubleSnapshot {
    private final double value;
    <N extends Number> DoubleSnapshot(N source) {
        value = source.doubleValue();
    }
    double get() { return value; }
}
```

`NumberHolder<Integer>.get()` returns `Integer` per the class's generic contract. `DoubleSnapshot.get()` always returns `double`; parameter `N` only has meaning **during initialization**. A generic constructor fits when data from multiple types is normalized into a single representation.

## 8. Constructor Chaining: `this(...)` and `super(...)`

A constructor can invoke another constructor of the same class with `this(...)` or a superclass constructor with `super(...)`. With generic classes, types passed between steps must be checked by the compiler.

```java
import java.util.function.Function;

class BaseBox<T> {
    private final T value;
    BaseBox(T value) { this.value = value; }
    T get() { return value; }
}

final class ConvertedChild<T> extends BaseBox<T> {
    <S> ConvertedChild(S source, Function<? super S, ? extends T> converter) {
        super(converter.apply(source));
    }
}

// ConvertedChild<Integer> c =
//         new ConvertedChild<>("hello", String::length);
```

Here `T` comes from the subclass and passes onward to superclass `BaseBox<T>`; `S` belongs only to the constructor, used to convert the source. Calling `super(...)` as the first statement of the constructor on Java 17 follows standard syntax.

An example delegating between overloads:

```java
import java.util.function.Function;

final class Payload<T> {
    private final T value;

    Payload(T direct) {
        this.value = direct;
    }

    <S> Payload(S source, Function<? super S, ? extends T> converter) {
        this(converter.apply(source));
    }

    T get() { return value; }
}
```

The generic constructor calls the regular constructor once it has a `T` value. This avoids duplicating field-assignment logic and invariant checks; if you want to reject `null`, check in the primary constructor, e.g., `this.value = Objects.requireNonNull(direct)`.

Remember: every constructor must finish with all `final` fields assigned exactly once across valid initialization paths. Using generics does not change Java's definite assignment rules.

## 9. When to Use a `static` Generic Factory Instead of a Generic Constructor?

A generic constructor makes sense when object creation can be clearly expressed via the signature. However, the compiler sometimes struggles to infer the relationship between source and target types with diamond, especially when there are multiple overloads. A **`static` generic factory method** is often an easier-to-read alternative:

```java
import java.util.function.Function;

final class Result<T> {
    private final T value;

    private Result(T value) {
        this.value = value;
    }

    static <T> Result<T> of(T value) {
        return new Result<>(value);
    }

    static <S, T> Result<T> from(
            S source,
            Function<? super S, ? extends T> converter) {
        return new Result<>(converter.apply(source));
    }

    T get() { return value; }
}

// Result<Integer> length = Result.from("Java", String::length);
// Result<String> rawValue = Result.of("Java");
```

In `Result.from`, both `S` and `T` are type parameters **of the factory method**. In `ConvertedBox<T>`'s generic constructor, `T` belongs to the class while `S` belongs to the constructor. Both approaches can be type-safe; the method name `from` clearly states the **conversion** operation and makes the API easier to extend or document validation rules.

A factory also allows returning subtypes, cached instances, singletons, or other specific variants when the contract allows; a constructor always instantiates the concrete class written after `new`.

### Distinguishing Generic Factories from the Diamond Operator

```java
Result<String> one = Result.of("abc");    // Generic method inference.
Result<String> two = new Result<>("abc"); // Valid only if the constructor is accessible.
```

If the constructor is `private` as in the `Result` example above, the second line is **invalid outside the class**. It only illustrates that these are two different mechanisms: `of` is a generic method, whereas `new Result<>(...)` is an instantiation expression with diamond governed by access modifiers. Do not put erroneous lines into a runnable program.

## 10. Generic Constructors in Records and Constructor Calling Rules

In a generic `record`, the class type parameter still belongs to the record:

```java
record Item<T>(T value) {
    // Regular constructor equivalent to the canonical constructor with respect to type T.
}
```

A non-canonical constructor in a record must **delegate directly or indirectly to the canonical constructor via `this(...)`**. It can also declare its own type parameter:

```java
import java.util.function.Function;

record ValueRecord<T>(T value) {
    <S> ValueRecord(S source, Function<? super S, ? extends T> converter) {
        this(converter.apply(source));
    }
}

// ValueRecord<Integer> n = new ValueRecord<>("Java", String::length);
// n.value() returns Integer 4.
```

`T` belongs to the record; `S` belongs to the auxiliary constructor. This applies the same idea as in a regular generic class, while obeying `record` constructor rules. Do not introduce a constructor taking an arbitrary source type when a `static` factory has a clearer name and avoids overload ambiguity.

## 11. Type Parameters Do Not Exist as Runtime Values

Java generics primarily use **type erasure**: type parameters are checked at compile time and then replaced by their appropriate bounds in normal runtime representation. This holds true for generic constructors as well.

```java
// Illustrative snippet inside a constructor <S> or method <S>:
// S instance = new S();       // Invalid: actual constructor of S is unknown.
// Class<S> clazz = S.class;    // Invalid: there is no S.class.
// boolean ok = source instanceof S; // Invalid for a non-reifiable type parameter.
```

If you need to **instantiate a new `S`** inside a constructor, pass a factory or appropriate type information:

```java
import java.util.function.Supplier;

final class ProducedText {
    private final String text;

    <S> ProducedText(Supplier<S> factory) {
        S source = factory.get();
        this.text = String.valueOf(source);
    }

    String text() { return text; }
}

// ProducedText view = new ProducedText(StringBuilder::new);
```

Object creation is delegated to `Supplier<S>` instead of trying to call `new S()`. `String.valueOf(null)` returns `"null"`, unlike `Objects.requireNonNull` which throws `NullPointerException`; choose a clear policy based on API requirements.

### Overloads by Type Parameter Can Collide Under Erasure

The following two constructors **cannot be declared simultaneously**:

```java
// Example intentionally does not compile.
class Invalid {
    <S> Invalid(java.util.List<S> items) {}
    Invalid(java.util.List<String> items) {}
}
// Both signatures take List after erasure, causing a name clash.
```

Similarly, `<S> Invalid(S item)` after erasure typically has parameter `Object` if `S` is unbounded; do not rely on a generic parameter to distinguish overloads that share the same erased signature.

## 12. Standalone Runnable Java 17+ Program

Create the file **`GenericConstructorDemo.java`** with the following content. The program illustrates a regular constructor taking the class's `T`, a generic constructor taking its own `S`, a generic constructor in a regular class, bounds, and constructor chaining.

```java
import java.util.*;
import java.util.function.Function;

public class GenericConstructorDemo {
    static final class Holder<T> {
        private final T value;

        Holder(T direct) {
            this.value = Objects.requireNonNull(direct);
        }

        <S> Holder(S source, Function<? super S, ? extends T> mapper) {
            this(mapper.apply(source));
        }

        T get() {
            return value;
        }
    }

    static final class DisplayText {
        private final String text;

        <S> DisplayText(S source, Function<? super S, String> format) {
            text = Objects.requireNonNull(format.apply(source));
        }

        String value() {
            return text;
        }
    }

    static final class NumericSummary {
        private final double total;

        <N extends Number> NumericSummary(Collection<N> numbers) {
            double sum = 0;
            for (N number : numbers) {
                sum += number.doubleValue();
            }
            total = sum;
        }

        double total() {
            return total;
        }
    }

    static class BaseBox<T> {
        private final T value;

        BaseBox(T value) {
            this.value = Objects.requireNonNull(value);
        }

        T get() {
            return value;
        }
    }

    static final class ChildBox<T> extends BaseBox<T> {
        <S> ChildBox(S source, Function<? super S, ? extends T> mapper) {
            super(mapper.apply(source));
        }
    }

    record RecordValue<T>(T value) {
        <S> RecordValue(S source, Function<? super S, ? extends T> mapper) {
            this(mapper.apply(source));
        }
    }

    public static void main(String[] args) {
        Holder<String> direct = new Holder<>("Lan");
        Holder<Integer> converted = new Holder<>("Generics", String::length);
        Holder<String> explicit =
                new <Integer> Holder<String>(42, Object::toString);
        System.out.println("direct: " + direct.get());
        System.out.println("converted: " + converted.get());
        System.out.println("explicit: " + explicit.get());

        DisplayText label = new DisplayText(2026, n -> "Year-" + n);
        System.out.println("display: " + label.value());

        NumericSummary numbers = new NumericSummary(List.of(1, 2, 3));
        System.out.println("sum: " + numbers.total());

        ChildBox<Integer> child =
                new ChildBox<>("Java", String::length);
        System.out.println("child: " + child.get());

        RecordValue<Integer> record =
                new RecordValue<>("Spring", String::length);
        System.out.println("record: " + record.value());
    }
}
```

Compile and run commands (in the directory containing the file):

```bash
javac -Xlint:all GenericConstructorDemo.java
java GenericConstructorDemo
```

Program stdout:

```text
direct: Lan
converted: 8
explicit: 42
display: Year-2026
sum: 6.0
child: 4
record: 6
```

Output explanation:

1. `direct` calls the regular constructor `Holder(T)`; `T = String` is chosen from the `Holder<String>` type.
2. `converted` calls the generic constructor `<S> Holder(S, Function<...>)`; the input's `S = String` differs from the object's `T = Integer`. `"Generics".length()` equals `8`.
3. `explicit` explicitly specifies `S = Integer` via `new <Integer> Holder<String>(...)`; `T = String` still belongs to the class.
4. `DisplayText` is not generic, yet constructor `<S> DisplayText(...)` infers `S = Integer` and converts it to a string.
5. `NumericSummary` takes data bounded by `N extends Number` to sum via `doubleValue()`.
6. `ChildBox<T>` uses its own `S` in the constructor and then passes the `T` value to the superclass's `super(...)`.
7. `RecordValue<T>` has a generic constructor and must delegate to the canonical constructor with `this(...)`.

The compile-error examples in this lesson are separately commented out; they are not calls to run in the complete program.

## 13. How to Choose Between a Regular Constructor, Generic Constructor, and Factory

| Situation | Appropriate Expression | Reason |
|---|---|---|
| Object stores the exact passed `T` value | `class Box<T> { Box(T value) {} }` | Regular constructor, direct type relationship, easy to understand |
| Input is `S` of a different type than `T`, with a converter to produce `T` | `<S> Box(S source, Function<? super S, ? extends T> f)` | Generic constructor bridges temporary source type with result type |
| Non-generic class whose source data can have multiple types | `class Label { <S> Label(S source, Function<? super S, String> f) {} }` | `S` is only needed during initialization |
| Want to express `from`/`parse`/`of` clearly and avoid confusing overloads | `static <S,T> Result<T> from(S, Function<...>)` | `static` generic factory has a descriptive name |
| Only accepts `Number` and converts to `double` | `<N extends Number> Summary(N value)` | Bound guarantees the API needed during conversion |
| Need to create data of type `S` inside | Pass `Supplier<S>` or a factory | Erasure forbids `new S()` |
| Input data already matches the stored type | Constructor `Box(T)` | No need to add a second type parameter |

A design principle: do not declare a generic constructor just to avoid writing `Object`. If `S` neither connects input positions nor is used by a bound/callback to provide useful type checking, a constructor taking an appropriate concrete type or a simpler `static` factory may be clearer.

## 14. Common Mistakes

| Mistake | What Happens | Fix |
|---|---|---|
| Thinking `Box(T)` is a generic constructor because `Box<T>` is generic | Confusing type parameter scope | A constructor is generic only when it **declares its own** `<S>` or similar type parameter |
| Writing `Box<T>(T input)` as the constructor name | Invalid Java constructor syntax | Declare `Box(T input)` |
| Writing `<S> void Box(S input)` thinking it is a constructor | Has return type `void`, so it is a **method**, not a constructor | Remove the return type: `<S> Box(S input)` |
| Using `<T> Box(T input)` inside `class Box<T>` thinking it is the same `T` | Constructor's `T` shadows the class's `T` | Use `Box(T)` or name a separate parameter `<S>` |
| Failing to distinguish `new Box<>()` from `<S> Box(...)` | Diamond is for class type arguments at the call site; `<S>` declares the constructor's parameter | Identify where each symbol belongs |
| Calling `new T()` or `new S()` inside a constructor | No runtime constructor information from a type parameter | Pass `Supplier<T>` or a factory |
| Constructor `<N extends Number>` given `String` data | Fails the upper bound | Pass a `Number` source or change the conversion API |
| Overloading constructors by `List<String>` and `List<Integer>` | Name clash after type erasure | Change the actual signature, use named factories, or use one generic constructor |
| Generic constructor using raw types and unchecked casts | Can break type safety of the object after creation | Keep parameterization on both source and converter; validate legacy data |
| Constructor assigning a `final` field along inconsistent paths | Definite assignment error or logic bug | Delegate with `this(...)` or assign the field exactly once on every path |
| Record with an auxiliary constructor not calling `this(...)` | Violates non-canonical record constructor rules | Use `this(converted)` |
| Compiler cannot infer with too many overloads | Undetermined or ambiguous type constraints | Specify the target type explicitly, adjust the API, or add a type witness if appropriate |

### Reading a Signature Without Confusion

Given:

```java
class Result<T> {
    <S extends CharSequence> Result(
            S input,
            Function<? super S, ? extends T> transformer) {
        // ...
    }
}
```

Ask:

1. **What is the class type?** `T` after `Result<T>`, determined by `Result<Integer>`, `Result<String>`, etc.
2. **What is the constructor's own type?** `S` in `<S extends CharSequence>`.
3. **What does the bound guarantee?** `S` has the behaviors of `CharSequence`.
4. **How are source and target connected?** `transformer` accepts `S` and returns a value compatible with `T`.
5. **What type does the data have after the constructor finishes?** The object's field carries the `T` contract; parameter `S` participates only during construction.

## 15. Practice Exercises

**Exercise 1 — Classifying constructors.** Given the code:

```java
class Sample<T> {
    Sample(T input) {}
    <U> Sample(U input, java.util.function.Function<U, T> convert) {}
}
```

Identify which constructor is generic under the definition of declaring its own type parameter. Distinguish the class's `T` from the constructor's `U`.

**Exercise 2 — Non-generic class.** Design `CsvText` holding only a `String`. Create a generic constructor `<S> CsvText(S source, Function<? super S,String> encoder)`. Use it with `Integer` and with a record `Person(String name)`. Check the inferred source type on each call.

**Exercise 3 — Bounds.** Write `RangeSummary` with `double min` and `double max`. The generic constructor `<N extends Number> RangeSummary(Collection<N> values)` must verify the collection is non-empty and use `doubleValue()` to compute the results. Describe the contract for `NaN` and `null` if you want to support floating-point data.

**Exercise 4 — Constructor chaining.** Write `Box<T>` with constructor `Box(T direct)` and constructor `<S> Box(S source, Function<? super S, ? extends T> mapper)`. Use `this(mapper.apply(source))`, testing a `"123"` string source and `Integer::parseInt` to build `Box<Integer>`. Try omitting the converter when the source does not match and observe the compile error message.

**Exercise 5 — Converting to a factory.** Convert `<S> Box(S source, Function<...>)` into a `static` factory `static <S,T> Box<T> from(S source, Function<? super S,? extends T> mapper)`. Compare the readability of `Box.from("123", Integer::parseInt)` with `new Box<>("123", Integer::parseInt)`.

**Exercise 6 — Explaining `String` and `Integer`.** Analyze:

```java
Holder<Integer> h =
        new <String> Holder<Integer>("Java", String::length);
```

The `String` after `new` indicates the **constructor's** type argument; the `Integer` after `Holder` indicates the **class's** type argument. Explain why `h.get()` returns `Integer`.

After studying, verify yourself by finding **where the type parameter is declared**: after the class name is the **object's** type, while right before the constructor name is a type **belonging only to that instantiation**. When both appear together, the two parameters can be linked via a converter while retaining separate scopes. This is the foundation for reading and building clear, type-safe generic constructor APIs in Java.