# Generic Methods in a Generic Class or a Regular Class (Java)

## 1. Concept and Purpose

A **generic method** (*generic method*) is a method that **declares its own one or more type parameters**, such as `<T>`, `<K,V>`, or `<T extends Number>`. That type parameter is scoped only to the method declaration and is inferred or specified by the compiler on each call. A generic method can reside in:

- A regular class (without class-level type parameters);
- A generic class, either using or not using the class's type parameter;
- A utility class with `static` methods;
- An interface (including abstract, default, or static methods), as long as the signature is valid.

Representative example:

```java
// Illustrative snippet; place inside a class with import java.util.List.
static <T> T first(List<T> items) {
    if (items.isEmpty()) {
        throw new java.util.NoSuchElementException("Empty list");
    }
    return items.get(0);
}
```

The `<T>` notation **comes before the return type** `T`. It **declares** the method's type parameter. `List<T>` links the input type with the result type: passing a `List<String>` yields a `String`; passing a `List<Integer>` yields an `Integer`. The compiler checks these relationships before runtime.

```java
// Inside a Java method/program:
String name = first(List.of("Lan", "Mai"));
Integer score = first(List.of(8, 9));
// String wrong = first(List.of(8, 9)); // Error because it is incompatible with String.
```

In the snippet above, `first` does not need to know whether its enclosing class is generic. What matters is that **the method itself declares `<T>`**. Conversely, a method that merely references `T` declared by the class does not automatically become a generic method.

This lesson uses syntax runnable on **Java 17+**, distinguishing illustrative snippets from the complete example `GenericMethodLesson.java` in section 11.

## 2. Syntax: Type Parameters, Return Type, and Parameter List

A method can declare type parameters regardless of whether **its enclosing class has `<T>` or not**:

```java
static <T> T first(java.util.List<T> xs) {
    return xs.get(0);
}

static <K, V> java.util.Map.Entry<K, V> pair(K k, V v) {
    return java.util.Map.entry(k, v);
}
```

In both signatures, the `<...>` placed before the return type **belongs specifically to the method**. Do not confuse `List<T>`/`Map.Entry<K,V>` with a type parameter declaration: those are type variable usage sites. The next focus is where the method is placed — a regular class, generic class, or interface — and the scope of each type variable.

## 3. Generic Methods in a Regular Class

A class without type parameters can still own multiple generic methods, with each method deciding its own parameters. This approach fits utility operations, factories, or data transformations.

```java
import java.util.*;

final class CollectionTools {
    private CollectionTools() {}

    static <T> List<T> singletonMutable(T element) {
        List<T> result = new ArrayList<>();
        result.add(element);
        return result;
    }

    static <K, V> Map<K, V> oneEntry(K key, V value) {
        Map<K, V> result = new LinkedHashMap<>();
        result.put(key, value);
        return result;
    }

    static <T> T last(List<T> values) {
        if (values.isEmpty()) {
            throw new NoSuchElementException("Empty list");
        }
        return values.get(values.size() - 1);
    }
}
```

Calls:

```java
List<String> words = CollectionTools.singletonMutable("java");
List<Integer> numbers = CollectionTools.singletonMutable(42);
Map<String, Integer> stock = CollectionTools.oneEntry("book", 5);
String lastWord = CollectionTools.last(List.of("A", "B")); // "B"
```

`singletonMutable` returns a mutable list, unlike `List.of(element)` which is a factory producing an unmodifiable list. Constructing `new ArrayList<>()` remains type-safe: the method's type `T` provides the constraint for the new list.

`oneEntry` shows why multiple type parameters matter: `K` (key) and `V` (value) are inferred independently. If we declared `Map<T,T>` instead of `Map<K,V>`, we would lose the ability to clearly express two different types or force the compiler to find a broader common type.

A regular class can also have **generic instance methods**:

```java
class Formatter {
    <T> String describe(T item) {
        return "Value: " + item;
    }
}

String s = new Formatter().describe(100); // "Value: 100"
```

`Formatter` does not have `<T>` after the class name, yet `describe` has `<T>` before `String`, so it is still a generic method. Here the type parameter is not required to produce the string because `Object` could be accepted; if no type constraint is needed, choosing `Object` can be simpler. Generics bring the highest value when **linking multiple type positions** or allowing a bound to guarantee a required operation.

## 4. Three Kinds of Methods Possible in a Generic Class

In a generic class, you can encounter three cases:

```java
class Container<T> {
    private final T value;
    Container(T value) { this.value = value; }

    T get() { return value; }                  // Uses the class's T.
    <U> U echo(U input) { return input; }       // Declares U itself.
    static <V> V staticEcho(V x) { return x; }  // Static generic method.
}
```

| Form | Type Variable Scope | Notable Point |
|---|---|---|
| `T get()` | Class's `T` | Does **not** declare a generic method itself |
| `<U> U echo(U)` | Method's `U` | Call can infer `U` independently of `T` |
| `static <V> V staticEcho(V)` | Method's `V` | Cannot directly use the class's instance type variable |

Therefore, `Container<String>` can call `echo(42)`, yet `get()` still returns static type `String`. This comparison is essential to continue reading examples in **regular classes** and **generic classes** without mixing up scopes.

## 5. Do Not Confuse the Class's `T` with the Method's `T`

A method can declare a type parameter with **the same name** as the class's type parameter. Inside that method, the new name shadows the name in the class scope:

```java
class ConfusingBox<T> {
    T original;
    ConfusingBox(T value) { original = value; }
    <T> T echo(T input) { return input; }
}
```

`ConfusingBox<String>` still stores a `String` in `original`, while `echo(123)` can infer `Integer` for the **method-level `T`**. This does not change the class's type. In production code, choose a name like `<U>` for the method to avoid confusion. The scope-comparison lesson in this chapter also analyzes combining the class's `T` and the method's `R` in detail.

## 6. Type Parameter Inference at Each Call Site

The compiler inspects **argument types** and, where appropriate, the **target type** to infer a generic method's type parameters:

```java
static <T> java.util.List<T> singleton(T x) {
    return java.util.List.of(x);
}
java.util.List<String> a = singleton("Java");
java.util.List<Number> b = singleton(42);
```

Both assignments illustrate target typing; place the calls inside a method and declare `singleton` in an appropriate class. When inference does not express the desired type clearly, the caller can specify a type witness such as `SomeClass.<Number>singleton(42)` (assuming the right class name). Specifying `<Number>` does not cast an incompatible object into a `Number`.

What matters for this lesson: **method type inference does not depend on whether its enclosing class is generic**. The syntax and scenarios for using explicit type arguments are covered separately in this chapter.

## 7. Bounded Generic Methods: Constraining the Capabilities of `T`

The method `<T> T identity(T value)` only assumes `T` is a reference type. If an algorithm needs to call a specific API, declare an **upper bound**:

```java
import java.util.*;

final class NumberMath {
    static <T extends Number> double sum(Collection<T> values) {
        double total = 0;
        for (T v : values) {
            total += v.doubleValue();
        }
        return total;
    }
}

// Inside a method:
double a = NumberMath.sum(List.of(1, 2, 3));      // 6.0
double b = NumberMath.sum(List.of(1.5, 2.5));     // 4.0
// NumberMath.sum(List.of("A", "B"));              // Bound error.
```

`T extends Number` guarantees `doubleValue()` exists. Even though `Number` is a class, the type parameter list still uses the `extends` keyword. If multiple bounds are needed, such as `<T extends Number & Comparable<T>>`, the class bound must precede the interfaces.

### Finding the Maximum by Natural Order

```java
// Illustration; inside a Java class with import java.util.*.
static <T extends Comparable<? super T>> T maximum(Collection<? extends T> items) {
    Iterator<? extends T> it = items.iterator();
    if (!it.hasNext()) {
        throw new NoSuchElementException("Empty collection");
    }
    T best = it.next();
    while (it.hasNext()) {
        T next = it.next();
        if (next.compareTo(best) > 0) {
            best = next;
        }
    }
    return best;
}

// Integer highest = maximum(List.of(4, 9, 3)); // 9
```

`Comparable<? super T>` is more flexible than `Comparable<T>` when a subtype inherits comparability defined for a supertype. `Collection<? extends T>` allows reading elements that are `T` or subtypes; here they are only iterated, not added to the source. If the usual need is simply getting the max, use the standard API `Collections.max`.

Do not add bounds merely to avoid writing a cast when the design is unclear: a bound should express **the behavior the algorithm actually requires**.

## 8. Generic Methods and Wildcards: Expressing Data Flow

When a method only reads from a source and writes data to a destination, you can combine a type parameter with wildcards:

```java
// Illustration inside a class with import java.util.List.
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}

List<Integer> numbers = List.of(1, 2);
List<Number> results = new ArrayList<>();
appendAll(numbers, results);  // results = [1, 2].
```

This is the **PECS — Producer Extends, Consumer Super** principle:

- `source` only supplies `T` elements: `? extends T` allows the source to contain elements of a subtype of `T`;
- `destination` receives `T` elements: `? super T` allows the target to hold `T` or an appropriate supertype;
- the type parameter `<T>` connects the relationship between both sides, allowing the compiler to verify the copy operation.

You cannot directly substitute `List<Integer>` for `List<Number>` because Java generics are **invariant** by default: even though `Integer extends Number`, `List<Integer>` does not inherit from `List<Number>`.

### When to Use a Type Parameter, When to Use a Wildcard?

Compare these two signatures:

```java
static void printEach(List<?> items) {
    for (Object item : items) {
        System.out.println(item);
    }
}

static <T> T getFirst(List<T> items) {
    if (items.isEmpty()) throw new NoSuchElementException();
    return items.get(0);
}
```

`printEach` does not need to preserve a type relationship between input and output, so `List<?>` is clear enough. `getFirst` needs to guarantee that the return type matches the input element type, so it uses `<T>`.

A practical rule: **declare a type parameter when there is a relationship to preserve**, such as between two parameters, between input and result, or when a bound needs to constrain the API. If you only read a collection of unknown type and handle elements as `Object`, a wildcard is usually simpler.

## 9. Generic Methods in Interfaces, Implementing, and Overriding

An interface **does not need to be generic** to contain a generic method:

```java
interface Converter {
    <T> String stringify(T value);

    static <T> T keep(T value) {
        return value;
    }
}

final class DefaultConverter implements Converter {
    @Override
    public <T> String stringify(T value) {
        return String.valueOf(value);
    }
}
```

The signature `<T> String stringify(T value)` belongs to each call; an implementation must obey the generic contract when overriding. For this example, since the result is always `String` and the logic only needs `Object`, an interface method `String stringify(Object value)` would also be a reasonable design if keeping a generic contract is unnecessary; the illustration here emphasizes that **an ordinary interface is still allowed to declare a generic method**.

A generic interface can also have methods using the interface's type parameter alongside its own generic method:

```java
interface Processor<T> {
    T read();

    <R> R transform(java.util.function.Function<? super T, ? extends R> mapper);
}

final class FixedProcessor<T> implements Processor<T> {
    private final T value;

    FixedProcessor(T value) { this.value = value; }

    @Override
    public T read() { return value; }

    @Override
    public <R> R transform(java.util.function.Function<? super T, ? extends R> mapper) {
        return mapper.apply(value);
    }
}
```

In `FixedProcessor<String>`, `read()` returns `String`; `transform(String::length)` infers `R = Integer`. Overriding must preserve the type parameter relationships in the signature. Replacing with raw types or unchecked casts can cause unchecked warnings and runtime errors.

### Can You Overload by `T`?

You cannot declare both simultaneously in the same class:

```java
// Invalid: after type erasure both have the same runtime signature.
// static void process(List<String> values) {}
// static void process(List<Integer> values) {}
```

Generics use **type erasure**, so the two overloads cause a *name clash*. If the logic is genuinely different, give the methods different names or add a meaningful distinguishing parameter; if the logic is the same, use a single generic method, such as `static <T> void process(List<T> values)`.

## 10. Type Erasure, Static, and Implementation Limitations

For a method declaring `<T>`, Java 17 checks generic constraints at the source level and then uses **type erasure** in bytecode. An unbounded `T` is typically erased to `Object`; a bounded `T` uses the appropriate bound. This brings several limitations relevant across all kinds of classes:

- You cannot use `new T()`, `T.class`, or directly create `new T[n]` when `T` is non-reifiable. You can pass a `Supplier<T>`, `Class<T>`, or array factory.
- Type arguments do not create distinct overloads if they share **the same erased parameter signature**.
- Generic varargs with non-reifiable types require attention to heap pollution and compiler warnings.
- Inside a generic class, a `static` method cannot directly use the **class's** type parameter, but it can declare its own `<U>`.

These points help you read compiler diagnostics, yet **do not define a generic method by its enclosing class**: a generic method is still a method that declares its own type parameters, whether it is in a regular class, a generic class, or an interface.

## 11. Complete Program Running on Java 17+

Create the exact file **`GenericMethodLesson.java`** below. The program compares generic methods in a regular class, generic methods in a generic class, an instance method using the class's `T`, an independent `static` method, a bounded generic method, and wildcard copying.

```java
import java.util.*;
import java.util.function.Function;

public class GenericMethodLesson {
    static final class Utility {
        private Utility() {}

        static <T> List<T> singletonMutable(T value) {
            List<T> result = new ArrayList<>();
            result.add(value);
            return result;
        }

        static <T> T first(List<T> items) {
            if (items.isEmpty()) {
                throw new NoSuchElementException("Empty list");
            }
            return items.get(0);
        }

        static <T extends Comparable<? super T>> T maximum(List<? extends T> items) {
            if (items.isEmpty()) {
                throw new NoSuchElementException("Empty list");
            }
            T best = items.get(0);
            for (T item : items) {
                if (item.compareTo(best) > 0) {
                    best = item;
                }
            }
            return best;
        }

        static <T> void copy(
                List<? extends T> source,
                List<? super T> destination) {
            for (T item : source) {
                destination.add(item);
            }
        }
    }

    static final class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        // Uses the class's type parameter T; does not declare a new <T>.
        T get() {
            return value;
        }

        // Method's own generic declaration; U is independent of T.
        <U> Holder<U> map(Function<? super T, ? extends U> mapper) {
            return new Holder<>(mapper.apply(value));
        }

        <U> U apply(Function<? super T, ? extends U> mapper) {
            return mapper.apply(value);
        }

        // Static generic method independent of Holder's type T.
        static <V> V echo(V item) {
            return item;
        }
    }

    public static void main(String[] args) {
        List<String> words = Utility.singletonMutable("Java");
        words.add("Generics");
        System.out.println("utility: " + words);
        System.out.println("first: " + Utility.first(words));

        Holder<String> original = new Holder<>("Hello");
        Holder<Integer> length = original.map(String::length);
        System.out.println("holder: " + original.get());
        System.out.println("mapped: " + length.get());
        System.out.println("applied: " + original.apply(String::toUpperCase));
        System.out.println("static: " + Holder.echo(42));

        List<Integer> scores = List.of(3, 9, 5);
        System.out.println("max: " + Utility.maximum(scores));

        List<Number> copied = new ArrayList<>();
        Utility.copy(scores, copied);
        System.out.println("copied: " + copied);
    }
}
```

Save the source code in UTF-8, compile, and run:

```bash
javac -Xlint:all GenericMethodLesson.java
java GenericMethodLesson
```

Exact expected stdout:

```text
utility: [Java, Generics]
first: Java
holder: Hello
mapped: 5
applied: HELLO
static: 42
max: 9
copied: [3, 9, 5]
```

**Analysis of each type flow:**

- `Utility` is a regular class. `singletonMutable`, `first`, `maximum`, and `copy` are all static generic methods **declaring their own type parameters**.
- `Utility.singletonMutable("Java")` infers `T = String`; `words.add("Generics")` is valid, whereas `words.add(123)` would be rejected at compile time.
- `Holder<String>` determines `T = String` for the getter `get()`. The generic method `map` has a **new type parameter `U`**, inferred as `Integer` from `String::length`, and thus returns `Holder<Integer>`.
- `original.apply(String::toUpperCase)` infers `U = String`, whereas `original.apply(String::length)` can infer `U = Integer` on another call; there is no conflict with the class's `T = String`.
- `Holder.echo(42)` infers `V = Integer` without needing a `Holder<T>` instance.
- `maximum` has the bound `Comparable<? super T>` to call `compareTo` and find the largest element.
- `copy` takes a `List<Integer>` source and writes into a `List<Number>` destination. Both wildcards keep the read/write constraints type-safe.

There are no manual casts in the program. Every constraint is expressed through class or method types; that is the biggest benefit of designing clear generic APIs.

## 12. Error Cases and How to Fix Them

| Symptom | Cause | Fix |
|---|---|---|
| `static T first(T value)` in a regular class reports `T` not found | Method has not declared a type parameter | Write `static <T> T first(T value)`. |
| `static T get()` in `class Box<T>` does not compile | Class type parameter cannot be used in a static context | Have the method declare its own type parameter or use a concrete type. |
| `<T> T echo(T value)` inside `Box<T>` causes confusion | Method's `T` shadows the class's `T` | Rename the method's type parameter to `<U>`. |
| Caller has to cast after calling a function returning `Object` | Signature does not preserve input–output type relationship | Use `<T> T first(List<T>)` if the goal requires returning the exact element type. |
| Call `List<Number> xs = List<Integer>` fails | Generics are invariant | Use wildcards `? extends T`/`? super T` according to data flow direction. |
| Generic method calls `t.compareTo(x)` and compiler says it does not exist | `T` lacks a bound guaranteeing `Comparable` | Declare `<T extends Comparable<? super T>>` appropriately. |
| Method creating `new T()` fails | Type erasure does not provide `T`'s constructor | Accept `Supplier<? extends T>` or another factory. |
| Overloads `method(List<String>)` and `method(List<Integer>)` cause a name clash | Same signature after erasure | Rename, design genuinely distinct overloads, or unify logic. |
| Generic method returns `null`, caller hits `NullPointerException` | Type parameter does not guarantee non-null | Define a clear null contract; use validation or `Optional<T>` where meaningful. |
| Compiler emits unchecked warning when using raw `List` | Type parameter lost at some point in the data flow | Use `List<T>`, `List<?>`, or validate/convert legacy data. |
| Generic varargs emits warning | Arrays and generics have different reification rules | Prefer collections or safe varargs design; evaluate `@SafeVarargs` under valid conditions. |
| Method `<T> void print(T value)` causes confusion without creating a type relationship | Type parameter may be redundant | Use `Object` if only handling general objects; keep generics when there is a real constraint/relationship. |

### Step-by-Step Procedure for Reading a Generic Signature

Given the following method:

```java
static <T extends Number, R> List<R> mapNumbers(
        List<? extends T> values,
        Function<? super T, ? extends R> converter);
```

Read from left to right:

1. `<T extends Number, R>` declares **two type parameters belonging to the method**; `T` is a subtype of `Number`.
2. `List<R>` is the return type; each resulting element has type `R`.
3. `List<? extends T>` is the source, only needing to be read as `T`.
4. `Function<? super T, ? extends R>` accepts a `T` value (or an appropriate supertype) and returns `R` (or a subtype).
5. The compiler connects the constraints on a specific call; for example, a `List<Integer>` source with converter `Number::doubleValue` can produce a result typed with `Double`.

You do not need to memorize every library type at once. Look for where the type parameter is **declared**, where it is **used**, and which relationship the compiler is enforcing.

## 13. Practice Exercises

**Exercise 1 — Regular class, generic method.** In a non-generic class `ArrayTools`, write `static <T> T last(List<T> items)` with an empty-list check. Call it with `List<String>` and `List<Long>`. Explain why a regular class does not prevent a method from declaring `<T>`.

**Exercise 2 — Class type and method type.** Write `Result<T>` with `T value`, `T get()`, and `<R> Result<R> map(Function<? super T, ? extends R>)`. With a `Result<String>` holding `"123"`, transform it using `Integer::parseInt` and check that the result has type `Result<Integer>`. Clearly state where `T` and `R` belong.

**Exercise 3 — Static generic method.** Create `static <K,V> Map<K,V> singleMap(K key, V value)`. Call it with a `String` key and `Integer` value. Explain why you do not need to pass `Map<Object,Object>` and then cast.

**Exercise 4 — Bounded type.** Write `static <T extends Comparable<? super T>> T min(List<? extends T> items)` returning the smallest element of a non-empty list. Use `compareTo` and test with `List<Integer>` and `List<String>`.

**Exercise 5 — PECS.** Write `static <T> void moveAll(Collection<? extends T> from, Collection<? super T> into)`. Use `Collection<Integer>` as the source and `Collection<Number>` as the destination. Ask why `Collection<Number>` cannot directly accept a `Collection<Integer>` in every API.

**Exercise 6 — Error analysis.** Predict what happens with this snippet:

```java
class Box<T> {
    T value;
    Box(T value) { this.value = value; }

    <T> T echo(T item) { return item; }
    // static T missing() { return null; }
}

Box<String> b = new Box<>("Java");
Integer i = b.echo(10);
```

Guidance: `b.echo(10)` is valid because the method's `T` is a new type parameter; `missing` (if uncommented) will not compile because it uses the class's `T` in a `static` context.

By the end of this section, make sure you can explain three cases on your own: **a method using `T` already declared by the class**, **a method declaring its own independent `<U>`**, and **a `static` generic method in a regular or generic class**. This is the key to writing reusable functions where the compiler still verifies type relationships.
