# Type Inference with Multiple Arguments of Different Types in Java Generics

**Type inference** is the process by which the Java compiler determines generic type arguments when the program does not write them explicitly. When a method call has **multiple arguments of different types**, the compiler does not simply pick the type of the first argument: it collects constraints from all arguments, `extends` bounds, generic structure, and the expected context of the expression, then finds a valid assignment for the type parameters.

Example:

```java
static <T> T first(T a, T b) {
    return a;
}

Number result = first(10, 2.5);
```

`10` is boxed to `Integer`, and `2.5` is boxed to `Double`. Both types inherit from `Number`, so the compiler can infer a common type compatible with both and with the `Number result` context. However, the fact that two types share a supertype **does not mean** you can pass a `List<Integer>` and a `List<Double>` to any `<T>` method expecting two `List<T>`.

This lesson explains how inference works, the difference between value types and container type arguments, the effect of the result type, wildcards, type bounds, and how to design signatures so multiple arguments of different types remain safe.

## 1. Inference starts from the generic signature and the arguments

A generic method declares type parameters before the return type:

```java
static <T> T chooseFirst(T first, T second) {
    return first;
}
```

In the call `chooseFirst("a", "b")`, both arguments are `String`, so the compiler can use `T = String`. With `chooseFirst(10, 20)`, boxing produces two `Integer` values and `T` can be `Integer`.

With `chooseFirst(10, 2.5)`, the two input types are `Integer` and `Double`. The call can still be valid because the compiler looks for a common type such that:

```text
Integer  <: T
Double   <: T
```

The notation `A <: B` means `A` is a subtype of `B`. In the example, `Number` is a suitable common supertype choice.

**Do not memorize that Java always picks `Number` or `Object` for every pair of types.** For multiple reference types, the *least upper bound* (LUB) can involve complex interfaces and *intersection types*. Assignment context or method bounds can also change the inference result. What you need to know is that the compiler checks all constraints according to the language rules, rather than picking a type by looking at a single argument in isolation.

## 2. Java 17 example: two arguments of different types can still call the same `<T>`

Save the file `MixedArgumentsDemo.java`:

```java
public class MixedArgumentsDemo {
    static <T> T chooseFirst(T first, T second) {
        return first;
    }

    static <T> String describe(T first, T second) {
        return first.getClass().getSimpleName()
                + " + "
                + second.getClass().getSimpleName();
    }

    public static void main(String[] args) {
        Number number = chooseFirst(10, 2.5);
        Object object = chooseFirst("Java", 17);

        System.out.println(number);
        System.out.println(object);
        System.out.println(describe(10, 2.5));
        System.out.println(describe("Java", 17));
    }
}
```

Compile/run with Java 17 or higher:

```bash
javac MixedArgumentsDemo.java
java MixedArgumentsDemo
```

Output:

```text
10
Java
Integer + Double
String + Integer
```

Explanation:

- `Number number = chooseFirst(10, 2.5)` is valid: two arguments of different classes can still convert to a common type satisfying the `Number` context.
- `Object object = chooseFirst("Java", 17)` is valid because both `String` and `Integer` are reference types and can be viewed as `Object`.
- `describe` uses `Object`'s method `getClass()`, so it does not require knowing specifically whether `T` is `Integer`, `Double`, or `String`.
- The program prints the runtime type of each **object**, not the exact type `T` inferred by the compiler. Generics do not create a separate runtime class for `T`.

Two arguments of different types do not mean every operation specific to a subtype is valid. Inside `describe`, the compiler cannot arbitrarily call `first.intValue()` or `first.length()` because `T` is not bounded by `Number` or `String`, respectively.

## 3. From multiple arguments to a common type: the "usable together as `T`" relationship

With the signature `<T> void handle(T a, T b)`, the compiler needs to find a `T` to which **both values** can be passed. A subclass value can automatically convert up to an appropriate superclass or interface at the parameter position.

Example:

```java
static <T> void printPair(T a, T b) {
    System.out.println(a + " | " + b);
}
```

Type-valid calls:

```java
printPair(1, 2);           // Two Integers after boxing.
printPair(1, 2.5);         // Integer and Double.
printPair("hello", 2026);  // String and Integer.
```

Using the same `T` **does not require the arguments to have the exact same runtime class**. A method type variable can represent a common supertype of multiple subclasses.

Contrast two different situations:

| Case | What does the compiler check? |
| --- | --- |
| `<T> void f(T a, T b)` | Each value can convert to a common `T` |
| `<T> void f(List<T> a, List<T> b)` | Both lists have type arguments matching **the same `T`** under invariance |
| `<T> void f(List<? extends T> a, List<? extends T> b)` | Each list's element type is a subtype of `T`, and they may differ |
| `<T> void f(List<? extends T> a, List<? super T> b)` | Source readable as `T` and destination able to accept `T` |

This is the crux of inference with multiple arguments: **constraints depend on where `T` appears in the signature**, not just on the classes of the input values.

## 4. Invariant generics: why don't `List<Integer>` and `List<Double>` match two `List<T>`?

Consider:

```java
static <T> void inspectSameLists(List<T> first, List<T> second) {
    System.out.println(first.size() + second.size());
}
```

With two lists having the same type argument:

```java
List<Integer> first = List.of(1, 2);
List<Integer> second = List.of(3);
inspectSameLists(first, second); // Valid: T = Integer.
```

However, the following does not compile:

```java
List<Integer> integers = List.of(1, 2);
List<Double> doubles = List.of(2.5, 3.5);

// inspectSameLists(integers, doubles); // COMPILE ERROR.
```

Because `List<T>` is invariant, the compiler cannot arbitrarily pick `T = Number` to treat `List<Integer>` as `List<Number>`, or treat `List<Double>` as `List<Number>`.

The error message may state **inference variable `T` has incompatible equality constraints** or conflicting type requirements. This means the two `List<T>` parameters require the exact same type argument, while the caller supplies two different parameterizations.

Do not fix this by doing:

```java
// List<Number> numbers = (List<Number>) (List<?>) integers;
```

Casting around via a wildcard can cause `unchecked` warnings and break type safety. An `Integer` list could have a `Double` added through the wrongly cast reference, causing errors to surface later when reading.

**The right design** depends on the goal: if you only want to read two sources from the same type family, use `? extends T` wildcards on each source; if you need to exchange data back and forth between two lists of **the exact same element type**, keep `List<T>` so the compiler rejects incompatible sources.

## 5. The `? extends T` wildcard enables inference from multiple sources of different types

When the algorithm only **reads** elements from two lists, instead of requiring both to be exactly `List<T>`, we can write:

```java
static <T> List<T> merge(
        List<? extends T> first,
        List<? extends T> second) {
    List<T> result = new ArrayList<>();
    result.addAll(first);
    result.addAll(second);
    return result;
}
```

The compiler needs to find a `T` such that:

```text
ElementType(first)  <: T
ElementType(second) <: T
```

Each source has its **own** wildcard, so one source can be `List<Integer>` and the other `List<Double>`. Together they provide data readable as `Number`.

### Complete program

Save as `MergeDifferentTypes.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class MergeDifferentTypes {
    static <T> List<T> merge(
            List<? extends T> first,
            List<? extends T> second) {
        List<T> result = new ArrayList<>();
        result.addAll(first);
        result.addAll(second);
        return result;
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Double> doubles = List.of(2.5, 3.5);

        List<Number> numbers = merge(integers, doubles);
        System.out.println(numbers);

        List<Object> objects = merge(
                List.of("Java"),
                List.of(17));
        System.out.println(objects);

        // List<Integer> invalid = merge(integers, doubles);
        // Error: Integer result cannot accept Double.
    }
}
```

```bash
javac MergeDifferentTypes.java
java MergeDifferentTypes
```

Output:

```text
[1, 2, 2.5, 3.5]
[Java, 17]
```

The context `List<Number> numbers = ...` helps constrain the result type to `List<Number>`; the two source lists have elements that are subtypes of `Number`. Similarly, `List<Object>` can hold both `String` and `Integer`.

**Limitation of reading from `? extends T`:** you cannot arbitrarily add an object `T` into `first` or `second`. For example, `first.add((T) someValue)` is unsafe; they may actually be distinct `List<Integer>` or `List<Double>` instances. In the example, only `result`, which is `List<T>`, is allowed to receive elements from both sources.

## 6. Combining producer and consumer for inference across multiple arguments

PECS (*Producer Extends, Consumer Super*) helps express **the direction of data flow**. A method taking two sources of different types and a common destination can be written as:

```java
static <T> void appendAll(
        List<? extends T> left,
        List<? extends T> right,
        List<? super T> destination) {
    destination.addAll(left);
    destination.addAll(right);
}
```

Constraints for the compiler:

- The element type of `left` must match `T` or a subtype of `T`.
- The element type of `right` must match `T` or a subtype of `T`.
- The destination must be able to accept values of type `T` according to the type system.

Therefore:

```java
List<Integer> ints = List.of(1, 2);
List<Double> doubles = List.of(2.5, 3.5);
List<Number> output = new ArrayList<>();

appendAll(ints, doubles, output); // Valid.

// List<Integer> onlyInts = new ArrayList<>();
// appendAll(ints, doubles, onlyInts); // Does not compile.
```

The compiler can select `T = Number` for the first case. In the `List<Integer>` destination case, there is no `T` that can both accept a `Double` source and be safely added to a destination accepting only `Integer`.

### Runnable Java 17 example

Save as `MultipleInputPecs.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class MultipleInputPecs {
    static <T> void appendAll(
            List<? extends T> first,
            List<? extends T> second,
            List<? super T> destination) {
        destination.addAll(first);
        destination.addAll(second);
    }

    public static void main(String[] args) {
        List<Number> numbers = new ArrayList<>();
        appendAll(List.of(1, 2), List.of(3.5, 4.5), numbers);
        System.out.println(numbers);

        List<Object> objects = new ArrayList<>();
        appendAll(List.of("A"), List.of(7), objects);
        System.out.println(objects);

        List<Integer> integers = new ArrayList<>();
        appendAll(List.of(1), List.of(2), integers);
        System.out.println(integers);
    }
}
```

```bash
javac MultipleInputPecs.java
java MultipleInputPecs
```

Output:

```text
[1, 2, 3.5, 4.5]
[A, 7]
[1, 2]
```

The destination uses `ArrayList`, so `addAll` is permitted. The `? super T` wildcard only guarantees **type safety of the added elements**, not mutability of the destination: an unmodifiable collection can still throw `UnsupportedOperationException`.

## 7. Target type as another constraint in multi-argument invocations

When a generic call returns `List<T>`, the assignment context can also constrain T, in addition to conditions from arguments:

```java
static <T> List<T> one(T value) {
    return new ArrayList<>(List.of(value));
}

List<Integer> a = one(10);
List<Number> b = one(10);
List<Object> c = one(10);
// List<String> wrong = one(10); // Conflict between Integer and String.
```

The same Integer can go into calls with different Ts, yet a variable already declared as `List<Integer>` does not automatically convert to `List<Number>`. When there are **multiple arguments of different types**, the target type must be checked together with constraints from all inputs; it cannot be used to force a Double to become an Integer.

## 8. `var` keeps the type inferred right at the initializer

```java
var inferred = one(10);        // List<Integer>.
List<Number> wider = one(10);   // List<Number>.
```

`var` does not propagate a Number target type down into the initializer and does not automatically widen `inferred` into `List<Number>` when a later statement uses it. If the result needs to hold multiple Number subtypes, express that contract directly in the declaration or via a valid type witness. In this lesson, the main point remains **collecting multiple lower/equality constraints from arguments**, not `var` syntax: read the types of `List<T>`, `List<? extends T>`, and `List<? super T>` before choosing a fix.

## 9. Boxing, primitives, and mixing numeric types

Generic type parameters accept only **reference types**, not primitives like `int` or `double`. Therefore:

```java
static <T> T first(T a, T b) {
    return a;
}

Number n = first(10, 2.5);
```

primitive numeric expressions are **boxed** to `Integer` and `Double` when participating in generics. The compiler then evaluates reference type constraints.

This differs from applying the primitive addition operator:

```java
double sum = 10 + 2.5; // Primitive numeric conversion, result 12.5.
```

Generics do not automatically support `Integer + Double` for an arbitrary `T`. If you need to sum multiple numeric types, add a bound to the type parameter:

```java
static <T extends Number> double sum(T first, T second) {
    return first.doubleValue() + second.doubleValue();
}
```

Then `sum(10, 2.5)` compiles because both `Integer` and `Double` belong to the `Number` family, and the compiler knows `doubleValue()` can be called on `T`.

A complete example:

```java
public class BoundedInferenceDemo {
    static <T extends Number> double sum(T a, T b) {
        return a.doubleValue() + b.doubleValue();
    }

    public static void main(String[] args) {
        System.out.println(sum(10, 2.5));
        System.out.println(sum(1L, 3));

        // sum("10", 2.5); // Does not compile: String does not extend Number.
    }
}
```

Save as `BoundedInferenceDemo.java`:

```bash
javac BoundedInferenceDemo.java
java BoundedInferenceDemo
```

Output:

```text
12.5
4.0
```

The `T extends Number` bound does not force both arguments to share the exact same subclass; it only forces the inferred common type to lie within the `Number` family. At the same time, it rejects calls containing incompatible arguments such as `String`.

**Arithmetic limitation:** `Number.doubleValue()` can lose precision with large numeric types or in financial calculations. The example focuses on illustrating type inference, not replacing rules on exact arithmetic or `BigDecimal` in real applications.

## 10. Multiple bounds can leave inference with no solution

With:

```java
static <T extends Number> T choose(T first, T second) {
    return first;
}
```

The call:

```java
Number n = choose(10, 2.5); // Valid.
```

can infer a `T` compatible with the `Number` bound. However:

```java
// String s = choose("text", 2.5); // Does not compile.
```

because `String` is not a subtype of `Number`. The compiler cannot ignore one argument to find a type fitting the remaining arguments.

Similarly, an overly narrow return type requirement can make the constraint system unsolvable:

```java
// Integer impossible = choose(10, 2.5); // Does not compile.
```

A `Double` cannot automatically convert to `Integer` merely via a generic type parameter; type inference does not perform arbitrary numeric conversions.

When encountering "incompatible bounds" or "inference variable has incompatible bounds" errors, analyze the full set of requirements:

1. Which type does each actual argument supply, after boxing if needed?
2. Which `extends` or intersection bounds does the type parameter have?
3. Does `T` appear in a single-value position, `List<T>`, `? extends T`, or `? super T`?
4. Does the result usage context demand a specific type?
5. Does there exist a `T` satisfying all conditions simultaneously?

Compiler feedback depends on the exact signature; do not assume every pair of differently typed arguments will successfully infer to `Object`.

## 11. Two identical wildcards do not mean two arguments share the same element type

Consider:

```java
static void printTwo(
        List<? extends Number> first,
        List<? extends Number> second) {
    Number a = first.get(0);
    Number b = second.get(0);
    System.out.println(a + " " + b);
}
```

A call with `List<Integer>` and `List<Double>` is accepted, because each list has elements viewable as `Number`. However, the first wildcard and the second wildcard can be **captured by the compiler as two different types**.

Therefore, this snippet is invalid:

```java
static void wrongCopy(
        List<? extends Number> first,
        List<? extends Number> second) {
    // second.add(first.get(0)); // Does not compile.
}
```

`first` could be `List<Integer>`, and `second` could be `List<Double>`. Sharing the same upper bound `Number` does not make their captured types identical.

To copy values from a source to a destination, constrain the receiving parameter:

```java
static <T> void copyValues(
        List<? extends T> source,
        List<? super T> destination) {
    destination.addAll(source);
}
```

Or, if **the exact same type argument** is required and you must write back and forth between two lists, use `List<T>` for both parameters. What decides is the type relationship the API intends to express.

## 12. Distinguishing a common type for value arguments vs. container type relationships

The following two examples reflect two different classes of checks:

**Single values:**

```java
static <T> void accept(T a, T b) { }

accept(1, 2.5); // Valid: compiler finds a common type.
```

**Invariant containers:**

```java
static <T> void acceptLists(List<T> a, List<T> b) { }

List<Integer> ints = List.of(1);
List<Double> doubles = List.of(2.5);

// acceptLists(ints, doubles); // Does not compile.
```

You cannot argue "`Integer extends Number` and `Double extends Number`, so both `List`s automatically become `List<Number>`." Java generics are not covariant in type arguments.

However:

```java
static <T> void acceptSources(
        List<? extends T> a,
        List<? extends T> b) { }

acceptSources(ints, doubles); // Valid.
```

Because the contract now only asks for two sources supplying values that the algorithm can view as `T`. The compiler can choose a common type satisfying both constraints without pretending the two lists share the same type argument.

The snippets in this section illustrate signature structures; place them inside a class with `import java.util.List;` and a `main` method if you want to compile/run them standalone.

## 13. When is an explicit type argument needed at the call site?

Java supports providing type arguments for a **generic method** before the method name, for example:

```java
List<Number> numbers = MergeDifferentTypes.<Number>merge(
        List.of(1, 2),
        List.of(2.5, 3.5));
```

This is illustrative syntax when `merge` is a static method in the `MergeDifferentTypes` class defined in section 5. `<Number>` tells the compiler to use `T = Number` in that call.

In most cases, the compiler infers well enough on its own and we only need:

```java
List<Number> numbers = MergeDifferentTypes.merge(
        List.of(1, 2),
        List.of(2.5, 3.5));
```

Explicit type arguments are useful when you want to state API intent clearly or resolve a situation where inference context does not express your wish. They **do not** let you bypass type-safety errors:

```java
// List<Integer> wrong = MergeDifferentTypes.<Integer>merge(
//         List.of(1), List.of(2.5));
// Does not compile: Double does not satisfy ? extends Integer.
```

Distinguish explicit type arguments from a **cast**: `<Number>` supplies a constraint for the compiler to check from the start; it does not turn a `Double` object into an `Integer`, does not skip generic safety checks, and cannot rescue an unsolvable constraint set.

## 14. Common mistakes when inferring across multiple types

### Mistake 1: thinking the compiler only looks at the first argument

```java
static <T> T first(T a, T b) {
    return a;
}

Number value = first(10, 2.5);
```

The compiler considers both arguments and the result context. It does not "lock" `T` to `Integer` upon seeing `10` and ignore `Double`.

### Mistake 2: thinking a common superclass is enough to pass two `List<T>`

`List<Integer>` and `List<Double>` do not automatically match two `List<T>`. If the method only reads, express the parameters as `List<? extends T>`.

### Mistake 3: using `List<Object>` for any differently typed source

```java
static void readObjects(List<Object> source) { }
```

The signature above does not directly accept `List<String>` or `List<Integer>`. If you only need to read elements as `Object`, `List<?>` is more suitable; if you need to preserve a common type across multiple sources, use a generic method with appropriate wildcards.

### Mistake 4: misusing `var` and assuming dynamic typing

`var` is **static type inference for local variables**. After the compiler picks a type, subsequent assignments/operations must obey that type. `var` does not "automatically widen" a `List<Integer>` when you later want to add a `Double`.

### Mistake 5: ignoring the destination type in PECS constraints

Two sources `Integer` and `Double` need a common type, but the destination must also be safe. If the destination is only `List<Integer>`, a `Double` cannot be placed into it. Check producer and consumer simultaneously.

### Mistake 6: treating type inference as numeric value conversion

`T` matching `Number` does not mean Java automatically converts `Double` to `Integer`. Boxing, primitive conversions, and reference conversions have their own rules; generic inference does not replace intentional data conversions.

### Mistake 7: casting generics to "fix" inference errors

Raw/unchecked casts may silence warnings at the call site while causing data errors later. Replace them with `<T>`, `? extends T`, `? super T` signatures or design an actual data conversion step when needed.

### Mistake 8: assuming inference guarantees a mutable collection

The fact that the compiler allows `destination.addAll(source)` by type does not mean runtime will support `addAll`. `List.of(...)` is unmodifiable; a collection with a `null` policy or other restriction can also reject elements.

## 15. Self-check questions

**Question 1.** Why can `chooseFirst(10, 2.5)` be valid with `static <T> T chooseFirst(T a, T b)`?

Because both arguments can be viewed as objects of a common reference type, and the compiler can pick `T` satisfying the input constraints along with the result usage context.

**Question 2.** Can `List<Integer>` and `List<Double>` be passed to `static <T> void f(List<T> a, List<T> b)`?

**No**, because `List<T>` is invariant and the two lists are parameterized by different types.

**Question 3.** What if the signature is changed to `static <T> void f(List<? extends T> a, List<? extends T> b)`?

**Yes**, because each source can use its own element type that is a subtype of `T`, such as reading both as `Number`.

**Question 4.** Can `List<Integer>` and `List<Double>` sources be transferred into `List<Number>` via `<T> void appendAll(List<? extends T>, List<? extends T>, List<? super T>)`?

**Yes.** `T = Number` satisfies the conditions for both producers and the consumer.

**Question 5.** What if the destination is `List<Integer>`?

**No**, because that destination cannot accept every `Double` from the second source.

**Question 6.** Why can `List<Number> numbers = one(10)` compile even though `10` is `Integer`?

Because the `List<Number>` return context together with the `Integer` argument can lead the compiler to choose `T = Number`.

**Question 7.** With `<T extends Number> double sum(T a, T b)`, how do `sum(10, 2.5)` and `sum("10", 2.5)` differ?

The first call is compatible because `Integer` and `Double` are both `Number`. The second call is rejected because `String` does not satisfy the `T extends Number` bound.

## 16. Process for choosing a signature when multiple input types exist

When designing or fixing a generic method, follow this order:

1. **List the actual types** that can come from each argument after allowed Java conversions such as boxing.
2. **Determine the role of each parameter:** read-only, write-only, or needing both reading and writing with the exact same type.
3. **Introduce a shared `<T>`** if multiple positions need a consistent type relationship or the result must preserve the element type.
4. **Use `? extends T` for sources** if sources can contain different subtypes of `T`.
5. **Use `? super T` for destinations** when passing `T` elements into a compatible receiver.
6. **Use `List<T>`** when lists must genuinely share the exact same type argument and interact bidirectionally.
7. **Add a bound `<T extends Base>`** if the algorithm needs methods or capabilities of `Base`.
8. **Check the expected result type**; with `var`, remember an explicit assignment target context is absent.
9. **Check all constraints together**, not just a common superclass of two values.

**Remember:** generic inference for multiple arguments is finding a solution for the type constraints of **the entire invocation**. Two values `Integer` and `Double` can share a `T` such as `Number`, whereas two lists `List<Integer>` and `List<Double>` do not automatically become two `List<Number>`. Wildcards and PECS are the way to express the exact relationship needed so the compiler stays both flexible and type-safe.
