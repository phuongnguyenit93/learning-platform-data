# Inferring Type Arguments from Invocation Arguments in Java Generics

## 1. The problem: why can we call a generic method without writing `<T>`?

In Java, a generic method declares type parameters inside `<...>` before the return type:

```java
static <T> T identity(T value) {
    return value;
}
```

We can specify `T` explicitly:

```java
String result = Example.<String>identity("Java");
```

However, usually we only need:

```java
String result = Example.identity("Java");
```

The compiler looks at the **actual arguments of the invocation** (here, the expression `"Java"`) and the formal parameter type (here, `T`) to infer how to use the type parameter `T`. This mechanism is called *method type inference* or *invocation type inference*.

In the simple example, `T` can be inferred as compatible with `String`. With the call `identity(42)`, the expression `42` has the primitive type `int` and can be boxed to `Integer`, allowing an appropriate reference type argument to be inferred.

**Key point:** the compiler infers from the **static types of the argument expressions**, the **constraints imposed by the method signature**, and sometimes the **target type of the invocation context**. It does not inspect the actual elements inside a list at runtime to guess `T`.

This lesson focuses on the constraints originating from **parameters and arguments of an invocation**, while also explaining cases where the target type can participate to avoid incorrect inference.

## 2. Three roles to distinguish

Consider the declaration:

```java
static <T> void append(List<T> destination, T value) {
    destination.add(value);
}
```

In the call:

```java
List<String> names = new ArrayList<>();
append(names, "An");
```

the roles are:

| Component | Example | Meaning |
| --- | --- | --- |
| **Type parameter** | `T` in `<T>` | Type variable declared by the method |
| **Formal parameter** | `List<T> destination`, `T value` | Position and type expected by the method |
| **Actual argument** | `names`, `"An"` | Expression passed when calling the method |
| **Inferred type argument** | Type compatible with `String` | Result of solving the constraints applied to `T` |

You should not call `"An"` a "type parameter". It is an **argument value**; from its static type, the compiler establishes conditions for the type parameter `T`.

A type parameter can appear in multiple positions in the signature, so inference **does not happen independently for each position**. The same `T` must satisfy all relevant conditions.

## 3. Basic case: one T parameter, one argument

Example:

```java
static <T> T echo(T value) {
    return value;
}
```

Calls:

```java
String text = echo("hello");
Integer number = echo(10);
```

In the first call, the argument is an expression of type `String`, so the compiler finds a suitable `T` so that the method can receive `String`. In the context of assigning to `String`, the call is valid and the return value remains compatible with `String`.

In the second call, `10` has type `int`; since generics cannot use primitive types as type arguments, boxing allows the wrapper type `Integer` to be used.

Other cases:

```java
Object object = echo("hello"); // Valid
Number value = echo(10);       // Valid
```

You should not claim that `T` is **always** exactly the most specific type of the argument. The target context `Object` or `Number` can add constraints, and Java's inference algorithm can find a broader suitable type when needed.

Type inference is the process of solving valid conditions according to the language rules, not a fixed lookup table saying "if the argument is X, then T must be X".

## 4. When the same T appears in multiple parameters

Consider:

```java
static <T> T choose(T first, T second, boolean pickFirst) {
    return pickFirst ? first : second;
}
```

With two arguments of the same type:

```java
String selected = choose("A", "B", true);
```

Both `"A"` and `"B"` are compatible with `String`, so inference is straightforward.

With two arguments of different types:

```java
Number selected = choose(1, 2.5, true);
```

`1` is boxed to `Integer`; `2.5` is boxed to `Double`. Both belong to the `Number` family, so a suitable type `T` can satisfy the necessary conditions in this call.

However:

```java
Integer selected = choose(1, 2.5, true); // COMPILE ERROR
```

There is no reason to guarantee the result is always `Integer` when the branch could return `Double`. The target type `Integer` adds a condition incompatible with accepting both arguments.

**Note on common types:** in complex cases, Java may use the *least upper bound* allowed by type relationships and *intersection types*. Therefore, do not manually interpret type `T` as one specific superclass when compile-time information is not clear enough. What matters is whether the expression is compatible with the target type and the bounds.

## 5. `List<T>` creates tighter constraints than a single T argument

Method:

```java
static <T> void append(List<T> destination, T value) {
    destination.add(value);
}
```

When calling:

```java
List<Integer> numbers = new ArrayList<>();
append(numbers, 7); // Valid
```

`destination` has type `List<Integer>`, so the `List<T>` position creates a strict constraint that `T` must match the list's type argument. The argument `7` can be boxed to `Integer`, so the conditions are compatible.

Conversely:

```java
List<Integer> numbers = new ArrayList<>();
Number value = 2.5;
append(numbers, value); // COMPILE ERROR
```

If the compiler treats `T` as `Integer`, the argument `value` with static type `Number` is not guaranteed to be an `Integer`. If it treats `T` as `Number`, `List<Integer>` does not convert to `List<Number>`, because generics are **invariant** by default.

The `javac` error typically looks like:

```text
reason: inference variable T has incompatible bounds
```

Along with conditions like "equality constraints: Integer" and "lower bounds: Number". This is a technical description of conflicting inference constraints, not meaning `T` was declared with `<T super Number>` syntax.

Meanwhile:

```java
List<Number> numbers = new ArrayList<>();
append(numbers, 7);   // Valid: Integer is a Number
append(numbers, 2.5); // Valid: Double is a Number
```

`List<Number>` requires the type parameter `T` to be compatible with `Number`; both `Integer` and `Double` arguments can convert to `Number`. This is a very important difference between **the type of a value argument** and **the type argument of a List**.

## 6. Method bounds also contribute to inference

Not every `T` is unbounded. Consider:

```java
static <T extends Number> double average(T left, T right) {
    return (left.doubleValue() + right.doubleValue()) / 2;
}
```

Valid calls:

```java
double a = average(2, 4);
double b = average(2, 4.5);
```

With `average(2, 4.5)`, the compiler must find a `T` compatible with the arguments `Integer`, `Double`, and the upper bound `Number`. The values are used as `Number` in the method body, so `doubleValue()` can be called on both arguments.

Invalid call:

```java
average("2", "4"); // ERROR: String does not satisfy the Number bound
```

With a more complex bound:

```java
static <T extends Comparable<? super T>> int compare(T a, T b) {
    return a.compareTo(b);
}
```

The compiler must ensure that type `T` also satisfies the comparability required by the bound. Having any arbitrary common supertype for the two arguments is not enough.

An important rule: **the common type must satisfy all declared bounds**. If the set of constraints has no valid solution, the call will not compile even if at runtime both objects could be stored under `Object`.

## 7. The static type of the argument matters more than the runtime value

```java
static <T> T identity(T value) {
    return value;
}
```

Example:

```java
Number n = Integer.valueOf(10);
Number result = identity(n);
```

The argument expression `n` has the **declared type `Number`**. The compiler does not infer the type by checking whether the current object is an `Integer`. At runtime, `n` could hold an `Integer`, a `Double`, or another subclass of `Number`.

Therefore:

```java
Integer i = identity(n); // Does not compile: Number does not guarantee Integer
```

To get an `Integer`, the input needs an appropriate static type or an explicit type-checking step:

```java
if (n instanceof Integer i) {
    Integer copy = identity(i); // Valid: i has type Integer after pattern matching
}
```

`instanceof` here is a runtime check to safely narrow the type; it does **not** mean generics re-infer types from runtime objects.

## 8. Arguments are not the only source of constraints

Invocation arguments provide initial information about T, but in a **poly method invocation**, the target type can also add conditions. Example:

```java
static <T> List<T> box(T value) {
    return new ArrayList<>(List.of(value));
}

List<Integer> a = box(42);
List<Number> b = box(42);
List<Object> c = box(42);
```

All three calls use the same value 42, but the target `List<T>` differs. For `b`, the target type forces the result to be compatible with `List<Number>`; the Integer argument can still be assigned to Number. That does **not** mean an already-created `List<Integer>` can be assigned to `List<Number>`.

Conversely, not every expression receives a target type and the compiler does not guess runtime intent. If `T` only appears in parameters, follow the static type of each argument; if it also appears in the return type, consider the return context and bounds as well. Assignment contexts, argument passing, and poly expression boundaries are analyzed in depth in the next **target type** lesson.

## 9. Explicit type arguments can be passed when control is needed

Syntax:

```java
List<Number> numbers = Example.<Number>box(42);
```

`<Number>` in this position is an **explicit type argument of the generic method invocation**, not a new type parameter declaration.

For a static method, write `Example.<Number>box(42)`. For a direct call within the same class, you can write `Example.<Number>box(42)` or another appropriate form depending on the call site.

Upper bound example:

```java
static <T extends Number> T same(T value) {
    return value;
}
```

Valid:

```java
Number n = Example.<Number>same(1);
```

Invalid:

```java
Example.<String>same("x"); // String does not satisfy the Number bound
```

Specifying `T` explicitly **does not bypass type safety rules**. If the choice does not satisfy the bound or the passed argument cannot be converted to the required type, the call is still rejected.

Usually you should let the compiler infer; specify type arguments explicitly only when it clarifies the contract or helps handle a hard-to-read situation.

## 10. Interaction with wildcards in parameter positions

When the source and destination have different roles, a generic method may need wildcards:

```java
static <T> void copyAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}
```

Example:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>();
copyAll(integers, numbers);
```

The compiler can choose a `T` such that `List<Integer>` matches `List<? extends T>`, while `List<Number>` matches `List<? super T>`.

This is the **PECS** (*Producer Extends, Consumer Super*) rule applied together with `T` inference.

Conversely, if declared too strictly:

```java
static <T> void copyStrict(List<T> source, List<T> destination) {
    destination.addAll(source);
}
```

The call `copyStrict(List<Integer>, List<Number>)` is invalid, because `List<Integer>` and `List<Number>` do not have the same type argument. Inference does not turn generics covariant; the compiler must respect the invariance of `List<T>`.

### Wildcard capture case

```java
static <T> T first(List<T> values) {
    return values.get(0);
}

List<? extends Number> source = List.of(3, 5);
Number n = first(source);
```

The compiler can *capture* the unknown wildcard in `source` to infer an appropriate `T` at the call `first(source)`. The returned element can still be safely used as `Number`.

You cannot conclude from this that any `Number` can be added to `source`; the wildcard only guarantees **reading** with an upper bound.

## 11. Boxing, primitive types, and varargs

Java generic type arguments must be **reference types**:

```java
static <T> T echo(T value) {
    return value;
}

Integer x = echo(1);  // int is boxed to Integer
Double y = echo(2.5); // double is boxed to Double
```

You cannot write:

```java
// Invalid:
List<int> numbers = new ArrayList<>();
// Similarly, <int>echo(1) is not a valid generic type argument.
```

You also need to distinguish generic varargs methods:

```java
@SafeVarargs
static <T> List<T> asList(T... values) {
    return List.of(values);
}
```

For example, this method is `static` and can be annotated with `@SafeVarargs` when the method body genuinely does not corrupt the varargs array type; however, the annotation is a **promise by the author**, not a mechanism that automatically makes generic varargs safe. Varargs methods with `T...` can trigger warnings about arrays with non-reifiable element types. When you just need to create a list, prefer `List.of(...)` or standard APIs.

Inferring `T` in a varargs invocation must consider the type of each argument, any passed array type, and fixed-arity/variable-arity applicability rules. Do not infer from syntactic similarity that an arbitrary `T[]` array is created at runtime.

## 12. Complete Java 17+ program and exact output

Create the file `InferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class InferenceDemo {
    static <T> List<T> box(T value) {
        return new ArrayList<>(List.of(value));
    }

    static <T> void append(List<T> destination, T value) {
        destination.add(value);
    }

    static <T> T pickFirst(List<T> list) {
        return list.get(0);
    }

    static <T> T choose(T left, T right, boolean pickLeft) {
        return pickLeft ? left : right;
    }

    static <T extends Number> double average(T a, T b) {
        return (a.doubleValue() + b.doubleValue()) / 2;
    }

    static <T> void copyAll(
            List<? extends T> source,
            List<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<String> words = box("Java");
        System.out.println("Words: " + words);

        List<Number> fromTarget = box(42);
        System.out.println("Target: " + fromTarget);

        List<Number> numbers = new ArrayList<>();
        append(numbers, 7);
        append(numbers, 2.5);
        System.out.println("Appended: " + numbers);

        List<? extends Number> source = List.of(3, 5);
        Number first = pickFirst(source);
        System.out.println("First: " + first);

        Number chosen = choose(1, 2.5, true);
        System.out.println("Chosen: " + chosen);

        System.out.println("Average: " + average(2, 4.5));

        copyAll(List.of(10, 20), numbers);
        System.out.println("Copied: " + numbers);

        List<Number> explicit = InferenceDemo.<Number>box(99);
        System.out.println("Explicit: " + explicit);
    }
}
```

Compile and run in the directory containing the file:

```bash
javac -encoding UTF-8 InferenceDemo.java
java InferenceDemo
```

Output:

```text
Words: [Java]
Target: [42]
Appended: [7, 2.5]
First: 3
Chosen: 1
Average: 3.25
Copied: [7, 2.5, 10, 20]
Explicit: [99]
```

**Detailed analysis:**

1. `box("Java")` creates a list containing `String` and is assigned to `List<String>`.
2. Putting `box(42)` into `List<Number>` is valid because the compiler combines the constraint from the argument with the target type; it does not turn an existing `List<Integer>` into a `List<Number>`.
3. `append(numbers, 7)` and `append(numbers, 2.5)` both work with the same `List<Number>` because each call must be compatible with `T` in the signature.
4. `pickFirst(source)` performs wildcard capture to read an element as `Number`.
5. `choose(1, 2.5, true)` accepts two different numeric types and the result is compatible with `Number`.
6. `average(2, 4.5)` satisfies `T extends Number`; the value `3.25` is the average of `2.0` and `4.5`.
7. `copyAll` leverages PECS: the source supplies `Integer` and the destination can accept `Number`.
8. `InferenceDemo.<Number>box(99)` demonstrates the explicit type argument syntax.

## 13. Common type inference error messages

### 13.1. `inference variable T has incompatible bounds`

```java
static <T> void append(List<T> target, T value) {
    target.add(value);
}

List<Integer> integers = new ArrayList<>();
Number n = 1.5;
append(integers, n); // Does not compile
```

The `List<T>` position forces `T` to match `Integer`, while the argument `n` has static type `Number`. Due to generics invariance, the compiler cannot find a choice of `T` that satisfies both.

**Fix:** pass a value that is genuinely an `Integer`, change the target type to `List<Number>` if it needs to hold multiple numeric types, or redesign the API using wildcards when appropriate for the domain contract. Do not blindly cast to `Integer`.

### 13.2. `inferred type does not conform to upper bound`

```java
static <T extends Number> T same(T value) {
    return value;
}

String s = same("hello"); // Does not compile
```

`String` is not a `Number`. This is a bound violation, not an error caused by missing information about `T`.

### 13.3. Misunderstanding the return value

```java
static <T> T choose(T a, T b, boolean left) {
    return left ? a : b;
}

Integer result = choose(1, 2.5, true); // Does not compile
```

You need to choose a target type that can represent both branches, such as `Number`. The fact that at runtime the `true` branch returns an `Integer` does not allow the call to return the static type `Integer` when the other branch could be a `Double`.

### 13.4. Using raw types or unchecked casts to bypass inference

```java
List<Integer> values = new ArrayList<>();
List raw = values;
raw.add("bad");
```

This is not a way to "fix inference errors". Raw types lose generic checking, can cause *heap pollution*, and then lead to a `ClassCastException` at read sites.

You should not add `@SuppressWarnings("unchecked")` just to hide a warning for an unproven cast.

### 13.5. Assuming `var` chooses the type the way you want

```java
var values = List.of(1, 2, 3);
```

`var` infers the type of a **local variable** from the result type of the initializer expression. This is a different step from inferring type arguments of the `List.of(...)` call. Do not assume `var` always produces `List<Number>` or always picks the programmer's desired type for every mixed set of arguments.

When an API needs a specific contract, declare the target type explicitly:

```java
List<Number> values = List.of(1, 2.5);
```

## 14. Exercises: from which arguments is inference performed?

The following snippets are **independent**, assuming `java.util.*;` is imported. `static` methods must be placed inside a valid class. Determine whether each compiles or not.

**A — Same T across List and value**

```java
static <T> void add(List<T> list, T value) {
    list.add(value);
}
List<String> texts = new ArrayList<>();
add(texts, "Java");
```

**B — Static type Number into List<Integer>**

```java
List<Integer> integers = new ArrayList<>();
Number n = 5;
add(integers, n);
```

**C — Static type Integer into List<Number>**

```java
List<Number> numbers = new ArrayList<>();
add(numbers, Integer.valueOf(5));
```

**D — Two numeric types and Number result**

```java
static <T> T pick(T x, T y) {
    return x;
}
Number n = pick(10, 3.5);
```

**E — Number bound with String**

```java
static <T extends Number> T unchanged(T x) {
    return x;
}
String s = unchanged("10");
```

**F — Target type of List<T>**

```java
static <T> List<T> singleton(T value) {
    return new ArrayList<>(List.of(value));
}
List<Number> numbers = singleton(10);
```

**G — Wildcard source and type inference**

```java
static <T> T first(List<T> values) {
    return values.get(0);
}
List<? extends Number> source = List.of(1, 2);
Number result = first(source);
```

**H — Two invariant List<T>**

```java
static <T> void merge(List<T> source, List<T> target) {
    target.addAll(source);
}
List<Integer> ints = List.of(1);
List<Number> nums = new ArrayList<>();
merge(ints, nums);
```

**Answers and explanations:**

- **A:** Valid, the constraints match `String`.
- **B:** Invalid: static type `Number` does not guarantee `Integer`; `List<Integer>` cannot be treated as `List<Number>`.
- **C:** Valid: `Integer` can convert to `Number`, and the destination is `List<Number>`.
- **D:** Valid: a common type compatible with `Integer`, `Double`, and the target type `Number` can be used.
- **E:** Invalid: `String` does not satisfy `T extends Number`.
- **F:** Valid: the target type `List<Number>` participates alongside the input constraint.
- **G:** Valid: wildcard capture allows the generic method to read an element as `Number`.
- **H:** Invalid: the same `List<T>` cannot be both `List<Integer>` and `List<Number>`. Use `List<? extends T>` for the source and `List<? super T>` for the target if you want that relationship.

## 15. Process for reading signatures when the compiler fails to infer T

Check in order:

1. **Locate the `<T>` declaration** and its bounds, e.g., `<T extends Number>`.
2. **Note every occurrence of `T`** in the formal parameters: `T`, `List<T>`, `List<? extends T>`, `List<? super T>`.
3. **Determine the static types of the actual arguments**, including boxing, reference conversions, and wildcards; do not rely on runtime values.
4. **Check whether there is a target type**, such as assigning the result to `List<Number>` or `Integer`, and whether that context participates in inference.
5. **Check whether the constraints conflict**. `List<Integer>` requires the exact type argument `Integer`, whereas a value argument of type `Number` may be too broad.
6. **Check the bounds**, e.g., `T extends Number`: an inferred solution that violates a bound is still rejected.
7. If the API describes **source/destination with different roles**, consider the `? extends T` / `? super T` pair instead of forcing all parameters to use the same `List<T>`.
8. Only write explicit type arguments when they represent a valid choice; do not use unchecked casts to bypass errors.

### Remember

**Inferring type arguments from invocation arguments** is how the compiler combines the static types of arguments with the structure of formal parameters to solve a system of constraints for `T`. The same `T` must satisfy all usage sites and bounds; in appropriate contexts, the target type can also add conditions. This mechanism allows calling generic methods concisely while preserving type safety without casts or raw types.
