# Target Types and the Effect of Assignment or Argument-Passing Contexts in Java Type Inference

## 1. The problem to solve

Java Generics allows the compiler to **infer type parameters** of generic methods, constructors using the diamond `<>`, and many other expressions from available information. A particularly important source of information is the **target type**: the type that the expression's result must be compatible with at the call or usage site.

Two lines of code look similar but can lead to different inferences:

```java
List<Number> numbers = List.of(1, 2);
var integers = List.of(1, 2);
```

In the first line, the expression `List.of(1, 2)` is used in an **assignment context** with target type `List<Number>`. The compiler can choose the type parameter `E = Number`, because `Integer` can be converted to `Number`.

In the second line, `var` does not provide a specific target type. The elements `1`, `2` are boxed to `Integer`; the type of the variable `integers` is inferred as `List<Integer>`.

This difference affects the ability to pass the result to other methods, retain type information, choose wildcards, and avoid casts.

This lesson focuses on **target types and the effect of assignment or argument-passing contexts**, in the Java Core Generics module, with examples suitable for Java 17+.

## 2. Learning objectives

After this lesson, you will be able to:

1. Distinguish **target type**, **expression type**, **declared return type**, and **runtime element type**.
2. Identify how assignment, argument-passing, `return`, lambda, and method reference contexts provide type information.
3. Explain why a generic call such as `List.of(1)` can be used as `List<Number>`, whereas a variable already typed as `List<Integer>` cannot automatically be assigned to `List<Number>`.
4. Predict the effect of `var`, diamond `<>`, type witness `<T>`, and target typing on a program.
5. Know the limits of inference: target types do not break Generics invariance, do not automatically change the type of an already-declared object, and do not replace type checking.
6. Write and verify Java 17 examples with deterministic output.

## 3. Concept: what is an expression with a target type?

An expression has a **target type** when Java uses the type requirement at the expression's location to check or infer the type of the expression itself.

Example:

```java
List<Number> values = List.of(1, 2);
```

Here:

- The left-hand side has type `List<Number>`: that is the target type.
- The right-hand side calls the generic method `List.of(E... elements)`: `E` must be inferred.
- The two integer arguments are boxed to `Integer`.
- Inference can choose `E = Number`, so that both `Integer` values are accepted and the expression is compatible with `List<Number>`.

An expression that can depend on a target type is called a **poly expression** when it meets the conditions of the Java Language Specification. Conversely, a **standalone expression** determines its own type without depending on a target type via the same mechanism.

Not every expression is a poly expression. Nor does having a type on the left-hand side mean Java automatically changes the type of every expression on the right-hand side. **The kind of expression and context rules determine** whether target type information is used.

### 3.1. Three questions to distinguish

Given:

```java
List<Number> numbers = List.of(1, 2);
```

Question: "What kind of object does the expression create at runtime?" — An implementation object of `List` holding references to `Integer` elements.

Question: "What static type does the variable `numbers` have?" — `List<Number>`.

Question: "Where does the `Number` information come from?" — From the target type of the assignment, used in generic invocation inference.

Type erasure means the JVM does not carry a `List<Number>` completely distinct from `List<Integer>` merely because of a different type argument. However, **static type checking** at compile time remains very important.

## 4. Assignment context: the left-hand type can participate in inference

Consider a conceptually standalone generic method:

```java
static <T> List<T> one(T value) {
    return List.of(value);
}
```

All of the following assignments are valid:

```java
List<Integer> a = one(1);
List<Number> b = one(1);
List<Object> c = one(1);
```

The compiler can choose a different `T` depending on the target expression's requirement. In those assignments, the call `one(1)` is not forced to have type `List<Integer>` before considering the assignment context.

**Important point:** `one(1)` is a *generic method invocation* that can participate in inference; it differs from **a variable** already declared as `List<Integer>`.

### 4.1. Assigning from a generic expression vs. assigning from an already-typed variable

```java
List<Number> direct = List.of(1, 2); // Valid.

List<Integer> integers = List.of(1, 2);
// List<Number> invalid = integers;   // COMPILE ERROR.
```

Why?

- `List.of(1, 2)` is a generic invocation; the target type can participate in inferring the type parameter of that call.
- `integers` is a variable expression with an **already established** static type of `List<Integer>`; assignment does not re-infer the variable's type argument.
- `List<Integer>` is not a subtype of `List<Number>`, because Java Generics is **invariant** in its type arguments.

If `integers` could be assigned to `List<Number>`, code using the new reference could add a `Double` into an `Integer` list, violating type safety.

### 4.2. How to fix it when you already have a `List<Integer>`

If you only need to **read** elements as `Number`, use a wildcard:

```java
List<Integer> integers = List.of(1, 2);
List<? extends Number> view = integers;
Number first = view.get(0);
```

If you need a **new `List<Number>`** to add multiple subtypes of `Number`, copy it:

```java
List<Integer> integers = List.of(1, 2);
List<Number> numbers = new ArrayList<>(integers);
numbers.add(2.5);
```

`new ArrayList<>(integers)` creates a new list whose type argument is inferred from the context; this is a **shallow copy**, not turning the original `integers` list into a `List<Number>`.

## 5. Argument-passing context: the method parameter type is an inference clue

Target types do not appear only on the left-hand side of `=`. When passing an expression into a method call, the **formal parameter** can also create a type context for the argument expression.

Example:

```java
static void acceptNumbers(List<Number> values) {
    System.out.println(values);
}

static <T> List<T> one(T value) {
    return List.of(value);
}
```

In the call:

```java
acceptNumbers(one(10)); // VALID.
```

The compiler knows `acceptNumbers` needs `List<Number>`. The generic call `one(10)` can be checked/inferred so that `T = Number`, even though the concrete argument `10` is boxed to `Integer`.

Contrast:

```java
List<Integer> existing = one(10);
// acceptNumbers(existing); // ERROR: List<Integer> differs from List<Number>.
```

Target type information from a method parameter helps **a nested generic call inside**, but does not automatically widen the type of an already-typed variable.

### 5.1. Distinguishing generic parameters and concrete parameters

```java
static void receiveExact(List<Number> values) { }

static void receiveProducer(List<? extends Number> values) { }
```

With `List<Integer> integers`:

```java
List<Integer> integers = List.of(1, 2);

// receiveExact(integers);    // Invalid because generics are invariant.
receiveProducer(integers);    // Valid due to extends wildcard.
receiveExact(List.of(1, 2)); // Valid due to inference with target type.
```

The three lines above illustrate **two different mechanisms**:

1. `receiveProducer(integers)`: accepts a parameter already typed as `List<Integer>` according to wildcard rules.
2. `receiveExact(List.of(1, 2))`: the `List.of` call can be inferred from the argument-passing context to produce an expression compatible with `List<Number>`.

Do not mix the two mechanisms and claim that Java has automatic covariance for `List<T>`.

### 5.2. Inference across multiple parameters

Consider:

```java
static <T> void appendAll(
        List<? super T> destination,
        List<? extends T> source) {
    destination.addAll(source);
}
```

The following call is valid:

```java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = List.of(1, 2);
appendAll(numbers, integers);
```

The compiler simultaneously solves constraints from both arguments:

- The type of `source` must be compatible with `List<? extends T>`.
- The type of `destination` must be compatible with `List<? super T>`.

For example, `T = Integer` is a suitable choice: the source has `Integer`, and the destination `Number` can accept `Integer`.

This is the PECS pattern. Generic inference can coordinate multiple constraints; each argument does not necessarily have to have the exact type `List<T>` initially.

## 6. `return` expressions: the return signature is a context

In the method:

```java
static List<Number> provideNumbers() {
    return List.of(1, 2.5);
}
```

`List<Number>` in the method declaration is the target type of the `return` expression. The `List.of` call can infer `E = Number` to accept both `Integer` and `Double`.

Similarly:

```java
static Optional<CharSequence> provideText() {
    return Optional.of("Java");
}
```

`Optional.of(T value)` is a generic call, and `Optional<CharSequence>` is the target type in the `return` context.

Do not confuse this with:

```java
static List<Number> invalid() {
    List<Integer> local = List.of(1, 2);
    // return local; // Error: local has fixed type List<Integer>.
    return new ArrayList<>(local); // Valid: creates a new List<Number>.
}
```

The return type can guide inference **in the return expression**, but does not change the static type of `local`.

## 7. `var` changes the source providing the target type

`var` infers the **local variable** type from the initializer, rather than passing an explicit contract such as `List<Number>` down to the call on the right-hand side:

```java
List<Number> widened = List.of(1, 2); // E can be Number.
var narrowed = List.of(1, 2);         // List<Integer>.
```

The type of `narrowed` is fixed right at declaration. It does not become `List<Number>` when used later. `var` still has a static type, not a dynamic type.

A call with no data arguments shows the difference even more clearly:

```java
List<String> texts = Collections.emptyList(); // T is String.
var unknown = Collections.emptyList();        // List<Object>.
```

In the `var` case, there is no String target type, so default inference can use Object. When an element contract is needed, declare the variable explicitly or choose a type witness at the creation site.

## 8. Diamond `<>` is also affected by context

```java
List<Number> numbers = new ArrayList<>(); // ArrayList<Number>.
var objects = new ArrayList<>();          // ArrayList<Object>.
var strings = new ArrayList<>(List.of("A")); // ArrayList<String>.
```

Diamond does not mean Object: a constructor argument like `List.of("A")` can constrain the type parameter even when using `var`. Distinguish diamond `<>` (requesting inference when creating an object) from wildcard `<?>` (an unknown type argument in a used type); `new ArrayList<?>()` is invalid. The **Diamond** lesson covers additional constructors and nested generic classes; the **var with diamond** lesson delves into cases where missing information causes the type to become Object.

## 9. Generic method invocations: target type participates alongside arguments

Definition:

```java
static <T> T choose(T left, T right) {
    return left;
}
```

A call such as:

```java
Number n = choose(1, 2.5);
```

has the constraints:

- `Integer` (after boxing) must be accepted as `T`.
- `Double` must be accepted as `T`.
- The return result `T` must be compatible with the target type `Number`.

The compiler can infer a `T` that satisfies the conditions, and `n` has the declared type `Number`.

Conversely:

```java
// Integer i = choose(1, 2.5); // Error: Double cannot become Integer.
```

A target type **cannot force** a call to accept incompatible arguments. Inference must simultaneously satisfy constraints from parameters, generic bounds, and the target type.

### 9.1. Type witness: specifying explicit type arguments

When you want to clarify intent or handle a hard-to-read inference case, you can write a type witness:

```java
List<Number> numbers = List.<Number>of(1, 2.5);
Number value = TargetTypingDemo.<Number>choose(1, 2.5);
```

Here `TargetTypingDemo` is the name of the class containing the `static choose` method, fully defined in the program in section 13.

The type witness `<Number>` requires the type argument of the generic call to be `Number`. It is **different** from the diamond `<>` on a constructor: one specifies a type, while the other requests inference.

Do not use a type witness to mask a poorly typed API. If a method inherently returns a fixed `List<Integer>`, writing a type witness at the caller does not magically turn it into `List<Number>`.

## 10. Lambdas: the target type determines the functional interface

A lambda **requires a type context** (the target type is a functional interface), for example:

```java
Function<String, Integer> length = text -> text.length();
```

The target type `Function<String, Integer>` provides:

- The type of the lambda parameter `text`: `String`.
- The result type that the lambda body must be compatible with: `Integer`.
- The functional method contract `apply`.

Therefore:

```java
int n = length.apply("Java"); // 4
```

Conversely:

```java
// var lambda = value -> value; // COMPILE ERROR
```

A lambda by itself does not determine which functional interface it implements; `var` in a variable declaration does not provide a corresponding target functional interface.

### 10.1. Lambdas in argument-passing contexts

```java
static void useText(Function<String, Integer> fn) {
    System.out.println(fn.apply("Java"));
}

useText(text -> text.length()); // Valid.
```

At the call, the parameter type `Function<String, Integer>` creates a target type for the lambda. The compiler understands `text` has type `String` even without declaring the type inside the lambda.

This is an important illustration that **argument-passing contexts can affect not only generic methods but also the types of lambdas**.

### 10.2. Lambdas as inputs to generic methods

```java
static <T, R> R transform(T value, Function<? super T, ? extends R> fn) {
    return fn.apply(value);
}

Integer size = transform("Java", text -> text.length());
```

The compiler uses the `String` type of argument `"Java"`, the `Integer` target of the assignment, and the signature `Function<? super T, ? extends R>` to find suitable constraints for `T` and `R`.

If you need to understand an inference error, look at **all positions contributing constraints**: the type of the input argument, the functional parameter, the lambda result expression, and the target type of the overall call.

## 11. Method references also receive types from context

Example:

```java
Function<String, Integer> length = String::length;
Supplier<List<String>> emptyStrings = Collections::emptyList;
```

`String::length` matches a functional interface taking `String` and returning `Integer` (the `int` value is boxed as needed). `Collections::emptyList` is a method reference to a generic method; the functional interface `Supplier<List<String>>` provides the constraint for inferring `T = String`.

```java
List<String> result = emptyStrings.get();
```

However:

```java
// var ref = String::length; // ERROR: method reference requires a target type.
```

Without a concrete functional interface, the compiler cannot determine the type of a method reference from the syntax `String::length` alone.

## 12. Conditional expressions `?:` and target types

In an assignment context, a **reference conditional expression** can be a poly expression. The target type can be used when checking each branch:

```java
boolean enabled = true;

List<Number> result = enabled
        ? List.of(1, 2)
        : List.of(2.5, 3.5);
```

Here, both `List.of(...)` branches are generic calls that can be compatible with the target `List<Number>`. Even though one branch contains `Integer` and the other contains `Double`, the assignment is valid.

Do not assume that **every** `?:` expression works via target types. Java rules distinguish conditional expressions into boolean/numeric/reference kinds, and only certain reference conditional expressions in appropriate contexts are poly expressions.

### 12.1. When using `var` with a conditional expression

```java
var result = enabled
        ? List.of(1, 2)
        : List.of(2.5, 3.5);
```

The variable `result` has no explicit `List<Number>` target type, so the compiler determines the type from the branches using the corresponding type combination (*least upper bound*) rules. Do not claim the final type is always `List<Number>`; it may be a more complex composite type containing wildcards/intersections.

If the API requires `List<Number>`, declare the target type explicitly to keep the contract clear:

```java
List<Number> values = enabled
        ? List.of(1, 2)
        : List.of(2.5, 3.5);
```

## 13. Complete, runnable Java 17+ program

Save the following snippet as **`TargetTypingDemo.java`**. The code intentionally demonstrates assignment, argument-passing, `return`, diamond, lambda, method reference, and `var` contexts.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Function;
import java.util.function.Supplier;

public class TargetTypingDemo {
    static <T> List<T> one(T value) {
        return List.of(value);
    }

    static <T> T choose(T left, T right) {
        return left;
    }

    static void acceptNumbers(List<Number> values) {
        System.out.println("argument=" + values);
    }

    static List<Number> returnedNumbers() {
        return List.of(3, 4.5);
    }

    static void useText(Function<String, Integer> lengthFn) {
        System.out.println("lambda=" + lengthFn.apply("Java"));
    }

    public static void main(String[] args) {
        List<Number> assigned = one(1);
        System.out.println("assignment=" + assigned);

        acceptNumbers(one(2));
        System.out.println("return=" + returnedNumbers());

        Number selected = choose(5, 6.5);
        System.out.println("choose=" + selected);

        List<Number> diamond = new ArrayList<>();
        diamond.add(7);
        diamond.add(2.5);
        System.out.println("diamond=" + diamond);

        var integers = List.of(8, 9);
        List<Number> copied = new ArrayList<>(integers);
        copied.add(10.5);
        System.out.println("var=" + integers);
        System.out.println("copy=" + copied);

        useText(text -> text.length());

        Function<String, Integer> length = String::length;
        System.out.println("reference=" + length.apply("abcd"));

        Supplier<List<String>> empty = Collections::emptyList;
        System.out.println("empty=" + empty.get().size());

        boolean flag = true;
        List<Number> conditional = flag
                ? List.of(11)
                : List.of(12.5);
        System.out.println("conditional=" + conditional);
    }
}
```

Compile and run:

```bash
javac TargetTypingDemo.java
java TargetTypingDemo
```

Exact stdout:

```text
assignment=[1]
argument=[2]
return=[3, 4.5]
choose=5
diamond=[7, 2.5]
var=[8, 9]
copy=[8, 9, 10.5]
lambda=4
reference=4
empty=0
conditional=[11]
```

Explanation in order:

1. `assigned` has target type `List<Number>`, helping the call `one(1)` infer a compatible type parameter.
2. `acceptNumbers(one(2))` uses the `List<Number>` argument-passing context for the call `one(2)`.
3. `returnedNumbers()` has `return List.of(...)` checked against `List<Number>`.
4. `choose(5, 6.5)` combines constraints from `Integer`, `Double`, and target `Number`; the method returns the first argument so it prints `5`.
5. `new ArrayList<>()` receives element type `Number` from the declaration `List<Number> diamond`.
6. `var integers` has type `List<Integer>` from the initializer `List.of(8, 9)`; the `List<Number>` copy is a different collection and accepts an added `Double`.
7. Lambda `text -> text.length()` is typed according to the parameter `Function<String, Integer>`.
8. Method reference `String::length` matches the functional interface `Function<String, Integer>`.
9. `Collections::emptyList` receives the target `Supplier<List<String>>`.
10. The conditional expression containing two `List.of` calls is checked against target `List<Number>`; `flag = true` so the result is `[11]`.

**Note on mutability:** `List.of` returns an unmodifiable list. The fact that `List.of` is inferred as `List<Number>` does not mean `add` will succeed; with `List.of`, mutating operations can still throw `UnsupportedOperationException`. Only the `new ArrayList<>(...)` copy in the example is mutable.

## 14. Why does the compiler not always infer "what we intended"?

### 14.1. Target types do not break invariance

```java
List<Integer> source = List.of(1);
// List<Number> target = source; // Error.
```

Target `List<Number>` cannot change `source` from `List<Integer>` to `List<Number>`. This is an assignment between two already-determined types, not a generic call needing inference.

### 14.2. Target types do not "fix" incompatible arguments

```java
static <T extends Number> T identity(T value) {
    return value;
}

// Number invalid = identity("text"); // Error because String is not a Number.
```

Even though target `Number` looks broad, the bound `T extends Number` and argument `String` conflict. There is no valid choice for `T`.

### 14.3. Not every generic API returns a `T` that needs inference

```java
static List<Integer> fixed() {
    return List.of(1, 2);
}

// List<Number> result = fixed(); // Error.
```

The method `fixed()` explicitly declares returning a concrete `List<Integer>`. The compiler cannot change the signature to `List<Number>` just because the caller wants it.

### 14.4. Target types do not change the runtime subtype

```java
List<Number> values = List.of(1, 2);
Number n = values.get(0); // Holds a reference to an Integer object.
```

Having `Number` on variable `n` does not imply the object turned into a different instance. **Static type** and **runtime class** are two different concepts.

### 14.5. Do not use raw types and unchecked casts

```java
List<Integer> integers = List.of(1, 2);
// List<Number> unsafe = (List<Number>) (List<?>) integers;
```

Unchecked casts can bypass compile-time errors but break the type contract, especially when new elements are added through the `List<Number>` reference. If you need to adapt an already-typed list, prefer a read-only wildcard or create a new appropriate list.

## 15. Interaction between type inference and overload resolution

With multiple overloaded methods of the same name, the compiler must also choose the appropriate overload. Type context and inference interact, but **you should not predict overload selection solely from the left-hand type**.

For example, two overloads can genuinely be distinguished by parameter count:

```java
static void log(String text) {
    System.out.println(text);
}

static void log(String text, int count) {
    System.out.println(text + ":" + count);
}
```

Here the overload is determined simply by the argument list. However, if multiple overloads take functional interfaces or generic types, lambdas, method references, and inference can create complex constraints or ambiguity.

In particular, you cannot declare two overloads that differ only in generic type arguments after erasure:

```java
// static void consume(List<Integer> values) {}
// static void consume(List<Number> values) {}
```

Both signatures have the same erasure `consume(List)`; Java reports a name clash. Target typing does not overcome the limits of type erasure.

When encountering an ambiguous overload, instead of guessing that the compiler looks at the result variable's type and picks the "right" one, inspect each signature, applicability and most-specific rules, or use explicit types/type witnesses where justified.

## 16. Target typing with nested generics

Context can assist inference across multiple generic levels:

```java
List<List<Number>> matrix = List.of(
    List.of(1, 2),
    List.of(3.5, 4.5)
);
```

The left-hand side requires `List<List<Number>>`; the inner `List.of` expressions are checked in the corresponding context to build a matching structure.

Contrast:

```java
List<List<Integer>> matrixOfIntegers =
        List.of(List.of(1, 2));

// List<List<Number>> invalid = matrixOfIntegers; // Error.
```

A `List<List<Integer>>` variable already has a concrete static type. It is not automatically compatible with `List<List<Number>>` merely because `Integer <: Number`, since invariance exists at each generic level.

If only reading:

```java
List<? extends List<? extends Number>> view = matrixOfIntegers;
Number first = view.get(0).get(0);
```

This is how wildcards are used at **the exact levels** needing variance without creating a copy. Meanwhile, when calling a fresh generic factory within a target type, the compiler can infer the type arguments from the outset.

## 17. Type witnesses, target types, and API design

### 17.1. When an API is well-written, callers rarely have to intervene

A generic factory:

```java
static <T> List<T> singleton(T value) {
    return List.of(value);
}
```

allows:

```java
List<Number> a = singleton(1);
List<Integer> b = singleton(1);
List<Object> c = singleton(1);
```

The caller can choose a valid target type matching its usage requirement.

### 17.2. When an API needs to establish the relationship between source and target

Example:

```java
static <T> List<T> copyOf(Iterable<? extends T> source) {
    List<T> result = new ArrayList<>();
    for (T item : source) {
        result.add(item);
    }
    return result;
}
```

Call:

```java
List<Integer> ints = List.of(1, 2);
List<Number> nums = copyOf(ints);
```

The compiler coordinates the source's `? extends T` bound with the result's `List<Number>` target. Returning a **new copy** allows choosing a genuine `List<Number>`, while the method still accepts an `Iterable<Integer>` source.

If the API merely returned the same `List<Integer>` reference under type `List<Number>`, that would be unsafe. Generic design must not confuse copying behavior with aliasing.

### 17.3. When you want context-independent typing, state the type argument explicitly

```java
var numbers = List.<Number>of(1, 2.5);
var sink = new ArrayList<Number>();
```

Even though `var` is used, the initializers in these examples explicitly state `Number`, so the inferred types for the corresponding variables have the type argument `Number`.

Use such declarations when a broader type is meaningful for the API, rather than expecting the compiler to guess intent from variable names.

## 18. Quick comparison table

| Situation | Is there useful target type information? | Key takeaway |
| --- | --- | --- |
| `List<Number> x = List.of(1)` | Yes, from assignment | Can infer `E = Number` |
| `acceptNumbers(List.of(1))` | Yes, from `List<Number>` parameter | Nested generic call is compatible |
| `return List.of(1)` in a function returning `List<Number>` | Yes, from declared return type | Generic expression is checked against `List<Number>` |
| `var x = List.of(1)` | No explicit `List<Number>` | `x` is inferred as `List<Integer>` |
| `List<Number> x = new ArrayList<>()` | Yes, for diamond | Infers `ArrayList<Number>` |
| `var x = new ArrayList<>()` | No `Number` target type | Infers `ArrayList<Object>` when no other constraints exist |
| `Function<String,Integer> f = s -> s.length()` | Yes, functional interface | `s` has type `String` |
| `var f = s -> s.length()` | No | Error: lambda needs a target functional interface |
| `Supplier<List<String>> f = Collections::emptyList` | Yes | Method reference is typed appropriately |
| `var f = String::length` | No | Error: method reference needs a target |
| `List<Number> y = existingListOfInteger` | Target exists but source is fixed | Invariance error |
| `List<Number> y = new ArrayList<>(existingListOfInteger)` | Yes, and creates a new copy | Valid |

The results in the table are based on JDK 17 and valid imports, with variable/method names defined with the appropriate types.

## 19. Common mistakes and self-diagnosis

### Mistake A — Confusing "inference" with "casting"

A generic factory call can choose `T = Number` from the start. That is inference **when the expression is checked**, not a cast from `List<Integer>` to `List<Number>` after the type is already determined.

### Mistake B — Believing `var` always chooses the "best type"

`var` infers based on the initializer and does not automatically know that business logic wants `List<Number>`. If the program later needs a broader target type, express that intent via an explicit declaration or a type witness.

### Mistake C — Changing `? extends T` to `List<T>` arbitrarily

If a method receives an actual `List<Integer>` reference, turning it into `List<Number>` via a cast is unsafe. Use wildcards for read views, or create a new copy with the broader type.

### Mistake D — Assuming every `?:` or method call expression is a poly expression

Java rules have specific conditions. Only certain forms of generic method invocations, reference conditional expressions, lambdas, method references, diamonds, etc., use target typing as described. Do not conclude that assignment can transform the static type of arbitrary expressions.

### Mistake E — Forgetting boxing/unboxing

Primitive `int` is not a subtype of `Number`. However, `1` can box to `Integer`, and then `Integer <: Number`. When reading generic errors involving primitive literals, account for boxing conversion.

### Mistake F — Confusing inference results with collection mutability

`List<Number> list = List.of(1,2)` is valid, but `list.add(3.5)` still throws `UnsupportedOperationException`. To actually add elements, use a mutable implementation such as `ArrayList`.

## 20. Self-check exercises

### Exercise 1 — Predict valid/invalid

```java
static <T> List<T> box(T item) {
    return List.of(item);
}

static void takeNumbers(List<Number> values) {}

List<Number> a = box(1); // (1)
takeNumbers(box(2));     // (2)
List<Integer> b = box(3);
// takeNumbers(b);       // (3)
```

**Answer:** (1) valid thanks to target `List<Number>`; (2) valid thanks to the `List<Number>` argument-passing context; (3) invalid because variable `b` already has type `List<Integer>`, not `List<Number>`.

### Exercise 2 — Types of `var` variables

```java
var a = List.of(1, 2);
var b = new ArrayList<>();
List<Number> c = new ArrayList<>();
```

**Answer:** `a` is `List<Integer>` (because of the `Integer` elements); `b` is `ArrayList<Object>` when no other constraints exist; `c` has declared type `List<Number>`, with diamond inferring the implementation's type argument from the target.

### Exercise 3 — Target of `return`

```java
static List<CharSequence> load() {
    return List.of("A", "B");
}
```

**Answer:** Valid. `List.of` can infer type argument `CharSequence`, accepting `String` values as subtypes of `CharSequence`. If returning a **variable** already declared as `List<String>`, direct assignment is invalid due to invariance.

### Exercise 4 — Lambda and method reference

```java
Function<String, Integer> a = text -> text.length();
Function<String, Integer> b = String::length;
// var c = text -> text.length();
```

**Answer:** `a` and `b` are valid because they have a target functional interface; `c` is invalid because `var` does not provide the required target type for a lambda.

### Exercise 5 — When should wildcards be used?

A method receives a `List<Integer>` already created by the caller, but only needs to read elements as `Number`:

```java
static double sum(List<? extends Number> values) {
    double result = 0;
    for (Number number : values) {
        result += number.doubleValue();
    }
    return result;
}
```

**Answer:** `? extends Number` allows passing `List<Integer>`, `List<Double>`, or `List<Number>`. Target typing of **factory calls** cannot replace wildcards when **the source variable already has a concrete type**.

### Exercise 6 — Evaluating a `?:` expression

```java
boolean flag = false;
List<Number> values = flag ? List.of(1) : List.of(2.5);
```

**Answer:** Valid thanks to target type `List<Number>` in the assignment context of a reference conditional expression; at runtime, `flag = false` so the element is a `Double` with value `2.5`. Do not conclude the same for a variable already typed as `List<Integer>` placed in a branch: the variable's static type is not re-inferred.

## 21. Analysis process when the compiler reports "incompatible types"

1. Determine what type **the entire expression** needs and where the target type information comes from: assignment, argument passing, `return`, or target functional interface.
2. Check whether the inner expression actually belongs to a kind that uses **target typing**.
3. If it is a generic method, locate the type parameters `<T>`, input types, return type, bounds, and the constraints that must be satisfied simultaneously.
4. If it is a constructor with `<>`, check whether the target type helps infer the type arguments.
5. If a variable is declared with `var`, determine the initializer's type right at declaration; do not assume intent from the variable name.
6. If the source is already `List<Integer>` and the target requires `List<Number>`, review invariance; consider `? extends Number` or creating a copy.
7. For lambdas/method references, check the functional interface in the target context, parameter types, and result type.
8. If inference is ambiguous, try specifying explicit `<Number>` type arguments **when valid**, or simplify the expression using an intermediate variable with an explicit type.
9. After compilation, evaluate runtime contracts separately: mutability, null, checked/unchecked exceptions.

## 22. References

- [Java Language Specification 17 — §15.12 Method Invocation Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12): inference in method invocations and applicability.
- [Java Language Specification 17 — §18 Type Inference](https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html): constraints, reduction, and generic type inference.
- [Java Language Specification 17 — §15.2 Poly Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.2): poly expression concept and type contexts.
- [Java Language Specification 17 — §15.25 Conditional Operator](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.25): typing rules for conditional expressions.
- [Java Language Specification 17 — §15.27 Lambda Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.27): lambdas and target functional interfaces.
- [Java Language Specification 17 — §15.13 Method Reference Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.13): method references and type contexts.
- [Java Language Specification 17 — §14.4 Local Variable Declaration Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.4): inference for local variables using `var`.
- [Java Tutorials — Type Inference](https://docs.oracle.com/javase/tutorial/java/generics/genTypeInference.html): overview examples of type inference.

**Conclusion:** The target type is a source of constraints that helps Java infer type arguments in eligible expressions, especially when **assigning the result of a generic call, passing a generic expression as an argument, or returning from a method with a declared type**. It does not turn an existing `List<Integer>` into `List<Number>`, does not make `var` automatically know the desired domain type, and does not eliminate Generics safety checks.
