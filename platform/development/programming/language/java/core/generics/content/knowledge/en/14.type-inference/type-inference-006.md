# Type Inference in Java Generics: Upper Bounds, Lower Bounds, and Least Upper Bound

## 1. Why does Java need type inference?

When calling a generic method, Java typically infers type arguments instead of forcing the programmer to specify them explicitly. Example:

~~~java
static <T> T first(T a, T b) {
    return a;
}

String word = first("Java", "Generics");
Number number = first(10, 2.5);
~~~

In the first call, both arguments have type `String`. In the second call, `10` and `2.5` are boxed to `Integer` and `Double`, respectively, when used in inference with `T` as a reference type. Java must choose a `T` that satisfies the conditions of **both arguments**, while also considering the context of assigning the result to `Number`.

This lesson focuses on three components:

1. **Lower bound:** types of which an inference variable must be a *supertype*; usually arising from passed arguments.
2. **Upper bound:** types of which an inference variable must be a *subtype*; can come from `extends` in the declaration or type conditions at the usage site.
3. **Least upper bound (LUB):** helps find a sufficiently specific common supertype to represent multiple different input types.

Do not confuse **type inference algorithm bounds** with wildcards `? extends T` and `? super T`. Wildcards are type constructs in the program; the inference algorithm collects bounds on inference variables to decide which concrete types can substitute for them. The two mechanisms are related, not identical.

## 2. Terminology: `T` in code and inference variable `α` in the compiler

A generic method declares a **type parameter** `T`:

~~~java
static <T extends Number> T laterNumber(T a, T b) {
    return b;
}
~~~

When calling `laterNumber(10, 2.5)` without writing an explicit type argument, the compiler replaces `T` with a temporary **inference variable** (often written `α` in the JLS description). After solving the constraints, the compiler selects a suitable type or type relationship and checks the entire call.

The notation in the following table is a **mathematical model**, not Java syntax:

| Bound | How to read? | Example meaning |
| --- | --- | --- |
| `Integer <: α` | `α` must be a supertype of `Integer` | An `Integer` argument must be passable to type parameter `T`. |
| `Double <: α` | `α` must be a supertype of `Double` | A `Double` argument must also be valid. |
| `α <: Number` | `α` must be `Number` or a subtype | The `<T extends Number>` declaration sets an upper bound. |
| `α = Integer` | `α` is constrained to equal `Integer` | A concrete type argument/invariant relationship may require this. |

`A <: B` means `A` is a subtype of `B`. Therefore, pay close attention to the direction:

- **A lower bound of `α` is `Integer`** means `Integer <: α`, *not* that `α` must be smaller than `Integer`.
- **An upper bound of `α` is `Number`** means `α <: Number`, *not* that `α` must be wider than `Number`.

A valid solution must satisfy those bounds **simultaneously**. With `Integer <: α <: Number`, either `Integer` or `Number` can be compatible depending on other conditions of the call. Java must also handle equality bounds, *intersection types*, capture conversion, target typing, and many specialized rules; you cannot infer a unique type simply by looking at one `extends` keyword.

## 3. How are lower bounds created from arguments?

Consider:

~~~java
static <T> T choose(T left, T right) {
    return left;
}

Number n = choose(10, 2.5);
~~~

The argument `10` has primitive type `int` and `2.5` has primitive type `double`. In a generic context requiring reference types, the compiler can apply boxing to `Integer` and `Double`. The two core conditions are:

~~~text
Integer <: α
Double  <: α
~~~

This means `α` must accept both arguments. The fact that `Integer` and `Double` share the parent `Number` makes `Number` **a compatible type** for the receiving site.

**Do not conclude that the internal inferred type is always strictly `Number`.** According to JLS §4.10.4, LUB in Java can be an *intersection type* consisting of shared interfaces such as `Comparable<?>` together with a common class; target context can also influence the solution. API users should rely on declared types and valid assignments rather than guessing the exact type name chosen by the compiler in every case.

### 3.1. Case where arguments have the same type

~~~java
String label = choose("A", "B");
Integer id = choose(7, 9);
~~~

In these simple situations, `T` can be inferred as `String` and `Integer`, respectively. No cast needed, no need to write `MyClass.<String>choose(...)`.

### 3.2. When multiple sources need a common supertype

~~~java
Number number = choose(10, 2.5);     // Valid.
Object object = choose("text", 42);   // Valid.
~~~

- With `Integer` and `Double`, there are useful common supertypes that allow returning `Number`.
- With `String` and `Integer`, `Object` is a common supertype. They can also share interfaces, so the exact LUB is not necessarily just `Object`.

**Note:** `choose("text", 42)` still returns **the exact chosen object**; type inference does not convert `Integer` into `String` or turn two values into a new runtime kind.

## 4. Upper bounds from `extends` declarations restrict solutions

A method can require the type argument to belong to the `Number` branch:

~~~java
static <T extends Number> T laterNumber(T a, T b) {
    return b;
}
~~~

When calling:

~~~java
Number result = laterNumber(10, 2.5);
~~~

The compiler combines:

~~~text
Integer <: α
Double  <: α
α       <: Number
~~~

It must find a solution satisfying all three. This is an example with **lower bounds from arguments** and an **upper bound from the type parameter declaration**.

With a single `String` argument, the constraints conflict:

~~~java
static <T extends Number> T bounded(T value) {
    return value;
}

// DOES NOT compile:
Number invalid = bounded("text");
~~~

At its core, `String <: α` and `α <: Number` **cannot hold simultaneously**; `String` is not a subtype of `Number`.

### 4.1. Multiple upper bounds with `&`

Java allows declaring a type parameter with multiple bounds, for example:

~~~java
static <T extends Number & Comparable<T>> T maximum(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

- `T extends Number` allows calling `Number` methods.
- `T extends Comparable<T>` ensures two values of the same `T` are comparable.
- With `maximum(3, 9)`, `T = Integer` satisfies the conditions, returning `Integer 9`.

**Do not interpret `<T extends Number & Comparable<T>>` as Java accepting any pair of differently typed numbers.** For instance, `Integer` and `Double` implement `Comparable` with **their own type arguments**, so `maximum(3, 9.5)` does not automatically satisfy the "compare the same `T`" contract. To compare different numeric types by numeric value, you must design a specific comparison criterion and clarify conversion/precision.

### 4.2. Rules for multiple interface bounds

In a type parameter declaration, if one bound is a class, it must come first; interfaces follow `&`:

~~~java
<T extends Number & Comparable<T>>
~~~

The actual type must satisfy all bounds, not just any single one. If the bound set conflicts, the compiler reports an error rather than dropping constraints to let the program run.

## 5. LUB: what is the "least information-losing" common supertype?

The **least upper bound (LUB)** of a set of reference types is a common supertype computed according to the JLS §4.10.4 algorithm so as not to pick an unnecessarily broad supertype.

Simple intuition for two types:

~~~text
      Object
        |
      Number
       /  \
  Integer  Double
~~~

`Number` is the closest common superclass in the class hierarchy of `Integer` and `Double`. Looking solely at this class hierarchy, `Number` carries more information than `Object`. Thus we can treat both values as `Number`.

However, **LUB in the JLS is not just finding the nearest common superclass in a tree**:

- A class can implement multiple interfaces. Two different classes may share multiple important interfaces.
- Java has *intersection types*, such as a type simultaneously satisfying `Number` and shared interfaces.
- For generic types, Java must account for type arguments, erasure, wildcards, and least containing parameterization rules.
- LUB is one part of resolution; it does not replace upper bounds, equality constraints, or target type contexts.

Therefore, an accurate statement to apply is: **LUB helps find a suitable common type from lower bounds; the compiler still needs to check all other constraints.**

### 5.1. How does the JLS use LUB when lower bounds exist?

In the simple case of resolving an inference variable with **proper lower bounds** `L1, L2, ...`, JLS §18.4 describes the candidate solution as:

~~~text
α := lub(L1, L2, ...)
~~~

That candidate is also checked against the constraint set for consistency. If it conflicts with an upper bound or another relationship, inference may fail or require further steps in the standard algorithm. You cannot simply spot LUB and ignore all other bounds.

### 5.2. "Greatest lower bound" is not LUB

In JLS resolution, if there are no proper lower bounds, a candidate can be formed from the **greatest lower bound (GLB)** of the proper upper bounds. This is a different concept from LUB:

- `lub(Integer, Double)` finds a sufficiently specific **common supertype** of two types.
- `glb(Upper1, Upper2)` considers combining type requirements that **must lie below** multiple upper bounds, often related to intersection types.

Do not confuse "a lower bound of an inference variable" with "the greatest lower bound of multiple types". Both phrases use the word *lower* but refer to different conceptual levels.

## 6. Equality constraints and invariance of generic arguments

The compiler cannot always widen a type argument to a common supertype. Generic types like `List<Integer>` and `List<Number>` are normally **invariant**:

~~~java
List<Integer> ints = List.of(1, 2);
// DOES NOT compile:
List<Number> numbers = ints;
~~~

If the context requires an exact generic argument, the compiler can have an **equality constraint**, such as `α = Integer` rather than only `Integer <: α`.

Look at the call:

~~~java
// DOES NOT compile:
List<Integer> values = List.of(1, 2.5);
~~~

In `List.of(E, E)`, the target type `List<Integer>` requires type argument `E` to match `Integer`, while the arguments require `E` to accept both `Integer` and `Double`. Java reports incompatible bounds (typically including `equality constraints: Integer` and `lower bounds: Double,Integer`). It cannot simply pick `Number` because `List<Number>` is not `List<Integer>`.

Conversely:

~~~java
List<Number> numbers = List.of(1, 2.5); // Valid.
~~~

The `List<Number>` context allows `Integer` and `Double` values to coexist as elements of a list with type argument `Number`. The assignment above **does not create a List<Integer> and then turn it into a List<Number>**. The compiler uses the target type when inferring `E` for the list creation call.

**Lesson:** Having a common superclass is not enough to prove two **concrete parameterized types** have a subtype relationship. You must track both invariance and equality constraints arising from context.

## 7. Target type adds conditions for inference variables

For a method returning `List<T>`, the target type can create an **equality constraint** in a poly invocation context, alongside lower/upper bounds from arguments:

```java
static <T> List<T> singleton(T value) {
    return List.of(value);
}
List<Number> numbers = singleton(7);
```

`Number` is introduced from the target type `List<Number>`, while Integer from argument 7 must be accepted as T. The compiler finds a solution satisfying both; the target does not change the type of an existing `List<Integer>`.

If you need to state intent right at the call:

```java
Number value = InferenceBoundsDemo.<Number>first(1, 2.5);
```

This is an example with the `first` method from the program in section 9. With `var values = List.of(1, 2.5)`, there is no explicit `List<Number>` target; the LUB algorithm may produce a composite type more complex than a single superclass. Here, **the lower/equality/upper bounds model** is the main topic; poly expression context rules are explored in depth in the next lesson.

## 8. Wildcards `extends`/`super` in multi-parameter methods

PECS (*Producer Extends, Consumer Super*) is often used alongside type inference, for instance:

~~~java
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~

When calling:

~~~java
List<Integer> source = List.of(2, 4);
List<Number> destination = new ArrayList<>(List.of(1.5));
appendAll(source, destination);
~~~

The compiler needs to find a `T` such that:

- `source` supplies elements assignable to `T` (`Integer` fits `T`).
- `destination` can accept values of type `T` (`T` must fit destination's element type `Number`).

For this simple case, you can picture the conditions as:

~~~text
Integer <: T
T       <: Number
~~~

There are one or more choices of `T` satisfying both constraints; the compiler applies generic wildcard, capture, and inference rules to validate the call. No cast is needed, and the two lists do not need the same type argument. This is a **relationship between source and destination**, rather than merely finding an arbitrary common supertype.

### 8.1. When two types have no safe transfer relationship

~~~java
List<String> strings = List.of("A", "B");
List<Integer> integers = new ArrayList<>();

// CANNOT use appendAll(strings, integers) to put Strings into List<Integer>.
~~~

The call will not compile: there is no `T` simultaneously satisfying the constraints to transfer from `String` to a list accepting only `Integer`, unless you change the contract/destination type. Avoid raw types and unchecked casts to "force" the compiler to accept unsafe data transfers.

### 8.2. Constraints from callbacks and multi-variable relationships

In transformation APIs, one type parameter can serve as input while another serves as output:

~~~java
static <T, R> List<R> transform(
        List<? extends T> input,
        java.util.function.Function<? super T, ? extends R> mapper) {
    List<R> output = new ArrayList<>();
    for (T item : input) {
        output.add(mapper.apply(item));
    }
    return output;
}
~~~

This is **an illustrative method** that needs to be placed inside a class importing `List` and `ArrayList`. The compiler must infer constraints connecting `T`, `R`, the source, and `mapper`. This is a case where a single upper/lower bound cannot tell the whole story of how inference works; inference order and dependencies between inference variables also play a role.

## 9. Complete Java 17+ program compiled and run

Create the file **InferenceBoundsDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class InferenceBoundsDemo {
    static <T> T first(T a, T b) {
        return a;
    }

    static <T extends Number> T laterNumber(T first, T second) {
        return second;
    }

    static <T> List<T> singleton(T value) {
        return List.of(value);
    }

    static <T> void appendAll(List<? extends T> source, List<? super T> destination) {
        for (T element : source) {
            destination.add(element);
        }
    }

    static <T extends Number & Comparable<T>> T maximum(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        String word = first("Java", "Generics");
        System.out.println("same type: " + word);

        Number common = first(10, 2.5);
        System.out.println("common: " + common);

        Number last = laterNumber(10, 2.5);
        System.out.println("bounded: " + last);

        List<Number> numbers = List.of(10, 2.5);
        System.out.println("target typed: " + numbers);

        List<Number> one = singleton(7);
        System.out.println("singleton: " + one);

        List<Integer> source = List.of(2, 4);
        List<Number> destination = new ArrayList<>(List.of(1.5));
        appendAll(source, destination);
        System.out.println("combined: " + destination);

        Integer max = maximum(3, 9);
        System.out.println("max: " + max);

        Number explicit = InferenceBoundsDemo.<Number>first(1, 2.5);
        System.out.println("explicit: " + explicit);
    }
}
~~~

Compile and run with Java 17 or newer:

~~~bash
javac --release 17 -Xlint:all InferenceBoundsDemo.java
java InferenceBoundsDemo
~~~

**Exact stdout**:

~~~text
same type: Java
common: 10
bounded: 2.5
target typed: [10, 2.5]
singleton: [7]
combined: [1.5, 2, 4]
max: 9
explicit: 1
~~~

Tested with `javac --release 17 -Xlint:all` and executed; the example compiles cleanly with no unchecked warnings. Explanation:

1. Two `String`s give a `first` call with result used as `String`.
2. `Integer` and `Double` supply lower bounds so the result can be used as `Number`.
3. `laterNumber` adds an upper bound `Number`.
4. `List.of(...)` and `singleton(...)` receive constraints from target type `List<Number>`.
5. `appendAll` allows transferring `Integer` to a `Number` destination list.
6. `maximum` forces `T` to satisfy both `Number` and `Comparable<T>`.
7. Explicit witness `<Number>` clarifies the type argument of the last call.

## 10. Deliberately invalid file to read `javac` diagnostics

Create a separate file **InvalidInference.java** as follows. **This file is designed to fail compilation**, not to be part of the runnable program in section 9:

~~~java
import java.util.List;

class InvalidInference {
    static <T extends Number> T bounded(T value) { return value; }
    static <T> T choose(T a, T b) { return a; }

    static void broken() {
        Number no = bounded("text");
        Integer incompatible = choose(1, 2.5);
        List<Integer> ints = List.of(1, 2.5);
    }
}
~~~

Compile:

~~~bash
javac --release 17 -Xdiags:verbose InvalidInference.java
~~~

**Expected:** the command exits with a non-zero exit code and three errors. Typical diagnostic excerpts verified with `javac`:

~~~text
inference variable T has incompatible bounds
  upper bounds: Number
  lower bounds: String
...
inferred type does not conform to upper bound(s)
...
inference variable E has incompatible bounds
  equality constraints: Integer
  lower bounds: Double,Integer
3 errors
~~~

The lines above are **abbreviated excerpts**, not the full stderr; inference variable names, intersection types, paths, and line positions may vary across environments.

These three errors illustrate three failure modes:

- `bounded("text")` creates lower bound `String`, conflicting with upper bound `Number`.
- `Integer incompatible = choose(1, 2.5)` requires the result to be usable as `Integer`, but the mixed-type arguments are incompatible with that requirement. The compiler may show an intersection type in the error.
- `List<Integer> ints = List.of(1, 2.5)` has a target parameterization requiring `Integer`, while the input list also contains `Double`; equality and lower bounds conflict.

Do not suppress error signals with raw types, `@SuppressWarnings("unchecked")`, or unfounded casts. These errors stem from **no valid type solution existing**, not from a missing syntactic cast.

## 11. Guide to reading type inference errors

When `javac` reports "`inference variable ... has incompatible bounds`", check in order:

1. **Identify the inference variable:** check which `<T>`, `<E>`, `<T,R>`, or bounds the generic method declares.
2. **Find lower bounds:** list the types the inference variable must accept from arguments (e.g., `Integer`, `Double`, `String`).
3. **Find upper bounds:** read `extends`, callback constraints, and target contexts constraining the output.
4. **Check equality/invariance:** is a `List<Integer>` being asked to receive a generic type with a different type argument?
5. **Check if a suitable common supertype exists:** if so, does that common supertype satisfy **all** remaining conditions? Merely having `Object` as a common parent does not automatically make every program valid.
6. **Consider target type and overloads:** is the call in an assignment, `return`, another method's parameter, or inferred standalone with `var`?
7. **Fix the contract in the right place:** change the output to `Number` when the domain genuinely permits multiple numeric types; use `extends`/`super` wildcards if source and destination have a safe variance relationship; use a type witness when expressing an intended type.
8. **Compile with clear diagnostics:** use `javac -Xdiags:verbose`; not every "incompatible bounds" error has the same root cause.

One warning sign to watch out for is casting `(List<Integer>)` onto a collection already containing `Double`. That can lead to heap pollution and `ClassCastException` later, rather than creating a valid inference solution.

## 12. Common misconceptions

| Misconception | Correct understanding |
| --- | --- |
| "Lower bound means `α <: Lower`." | A lower bound `L` of `α` means `L <: α`. |
| "Upper bound means `Upper <: α`." | An upper bound `U` of `α` means `α <: U`. |
| "Having `Object` as a common parent makes any inference valid." | `extends` bounds, equality, invariance, and target typing constraints must still be satisfied. |
| "The LUB of `Integer` and `Double` is always strictly `Number`." | The JLS can represent intersection types/interfaces, not just a single superclass. |
| "`<T extends Number>` automatically converts `String` to a number." | No. If an input does not satisfy `Number`, the compiler reports an error. |
| "Two `List<T>` can always share `T` because both are Lists." | Type arguments are invariant; a genuine matching constraint must hold between them. |
| "`List<Integer>` is a subtype of `List<Number>` because Integer extends Number." | No. You need an appropriate wildcard or a new collection with the right type argument. |
| "`var` always infers the exact parent type I envision." | `var` uses the initializer's type; that type may be an intersection or complex parameterized type. |
| "Upper/lower bounds messages are runtime errors." | These are **compile-time** diagnostics about type consistency. |
| "`@SuppressWarnings("unchecked")` fixes a missing inference solution." | No. It only affects certain unchecked warnings and does not validate invalid types. |

## 13. Self-check questions

1. With `<T extends Number> T f(T x)` and argument `Integer`, what is the constraint direction? **`Integer <: α <: Number`**.
2. Why is `f("hello")` invalid? **Because `String` is not under `Number` and no solution satisfies both conditions.**
3. What do lower bounds `Integer` and `Double` suggest finding? **A suitable common supertype; the JLS can compute the LUB of reference types.**
4. Is LUB always a simple class? **No.** It can involve intersection types and parameterized types.
5. Why is `List<Integer> ints = List.of(1, 2.5)` invalid even though `Number` is a common parent? **The target type creates a constraint forcing the type argument to match `Integer`, conflicting with the `Double` argument.**
6. Is `List<Number> ns = List.of(1, 2.5)` valid? **Yes.** The target type is compatible with both numeric types.
7. Does `<T> void append(List<? extends T>, List<? super T>)` require both lists to have the same type argument? **No.** It only requires a safe `T` transfer relationship from source to destination.
8. Why is explicit `<Number>` sometimes useful? **It supplies an explicit, intentional type argument to the method, provided arguments and bounds match.**

## 14. Standard references

- [JLS Java SE 17 §18.1.3 — Bounds](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.1.3): defines upper, lower, equality, capture, and `throws` bounds.
- [JLS Java SE 17 §18.4 — Resolution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.4): how `lub` from proper lower bounds and `glb` from proper upper bounds are used when resolving inference variables.
- [JLS Java SE 17 §18.5 — Uses of Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html#jls-18.5): method applicability, invocation type inference, and target type effects.
- [JLS Java SE 17 §4.10.4 — Least Upper Bound](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.10.4): LUB of reference types accounting for generic declarations, intersection types, and supertypes.
- [JLS Java SE 17 §4.5.1 — Type Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.1): wildcard containment and invariance of parameterized types.
- [JLS Java SE 17 §15.12 — Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): contexts and rules for method invocations, including generic methods.
