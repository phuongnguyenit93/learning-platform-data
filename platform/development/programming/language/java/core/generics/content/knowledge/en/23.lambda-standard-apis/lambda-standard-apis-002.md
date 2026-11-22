# API Methods Taking `? super T` or `? extends R`: Lambdas and Java Generics

## Lesson Objectives

When reading the Java Standard API, you often encounter signatures like:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

This is not arbitrary verbosity. The two wildcards **`? super T`** and **`? extends R`** allow the method to accept more valid callbacks while preserving type safety.

After this lesson, you will be able to:

- Read `Function<? super T, ? extends R>` accurately in terms of **input consumption direction** and **output production direction**.
- Explain why a `Function<Animal, StringBuilder>` can be passed into a method transforming `Dog` into `CharSequence`.
- Understand **contravariance** on input, **covariance** on output, and distinguish them from the **invariance** of `Function<A,B>` / ordinary Java generics.
- Read common signatures of `Stream.map`, `Stream.flatMap`, `Stream.filter`, `Iterable.forEach`, `List.sort`, `Function.compose`, `Function.andThen`, `Consumer.andThen`, and `Predicate.and/or`.
- Know when a wildcard belongs to a callback parameter versus a collection, and why you should not replace them with raw types.
- Write your own generic API combining `List<? extends T>` and `Function<? super T, ? extends R>`.
- Read compiler errors, resolve type inference issues, and choose an appropriate lambda or method reference.
- Recognize the limits: wildcards **broaden the kinds of callbacks accepted**, they do not convert `Consumer<T>` into a different generic type, nor do they add new runtime subtype checks.

The complete examples here use **Java 17 or later**, have been compiled with `javac -Xlint:all`, and run to verify stdout. Snippets marked as “illustrative” must be placed inside an appropriate class/method, not run as standalone programs.

## 1. First, understand `Function<T,R>`

`Function<T,R>` represents a transformation with **one input `T` and one result `R`**; its abstract method is `R apply(T value)`. Example:

```java
Function<String, Integer> length = String::length;
Integer count = length.apply("Java"); // 4
```

What is needed for a **callback API signature** is distinguishing the usage direction: the caller passes in a `T`, while the callback can accept a **supertype of `T`**; the caller receives an `R`, while the callback can produce a **subtype of `R`**. Hence the more general pattern is:

```java
Function<? super T, ? extends R>
```

The `Dog extends Animal` and `StringBuilder implements CharSequence` scenario in the next section demonstrates both sides simultaneously, rather than merely repeating the four-interface table from the introductory lesson.

## 2. Why does `Function<Animal, StringBuilder>` work for `Dog -> CharSequence`?

Suppose we have an inheritance hierarchy:

```text
    Object                  CharSequence
      |                          ^
    Animal                        |
      ^                      StringBuilder
      |
     Dog
```

`Dog extends Animal`, and `StringBuilder implements CharSequence`.

Now consider the callback:

```java
Function<Animal, StringBuilder> label =
        animal -> new StringBuilder(animal.name());
```

This function accepts **any `Animal`**, so it can certainly accept a `Dog`. It returns a `StringBuilder`, and a `StringBuilder` can be used as a `CharSequence`. Therefore, in the context `T = Dog`, `R = CharSequence`, that callback satisfies:

```java
Function<? super Dog, ? extends CharSequence>
```

There is no need to rewrite it as a `Function<Dog, CharSequence>` just to match the exact type.

Table:

| Callback component | Actual type | Required API type | Why is it valid? |
| --- | --- | --- | --- |
| Input | `Animal` | `? super Dog` | `Animal` is a supertype of `Dog` |
| Output | `StringBuilder` | `? extends CharSequence` | `StringBuilder` implements `CharSequence` |
| Full callback | `Function<Animal,StringBuilder>` | `Function<? super Dog,? extends CharSequence>` | Both directions are safe |

**Do not reverse the directions:**

- A callback that only accepts `Dog` **cannot** be used to process all `Animal` instances, because it might encounter a `Cat`.
- A callback that only promises to return `Object` **cannot** automatically be used where a `String` is required, because an `Object` might not be a `String`.

Wildcards do not “coerce” an object into an appropriate subtype. They describe **type-safe relationships** already proven by the compiler.

## 3. The PECS principle for a two-type-parameter functional interface

Quick mnemonic **PECS — Producer Extends, Consumer Super**:

- **`? super T`**: a component that **consumes** `T` values (consumer) is allowed to accept a supertype of `T`.
- **`? extends R`**: a component that **produces** values used as `R` (producer) can return a subtype of `R`.

For `Function<A,B>`, `A` is in the parameter position of `apply` so it is an input, while `B` is the return value of `apply` so it is an output.

```text
API's T    -----(passed in)---->  Function<? super T, ? extends R>
                                             |
                                             | apply(T)
                                             v
API's R    <----(received)-----   value is R or a subtype of R
```

Note: “consumer” and “producer” here describe **the role of a type position in the call**, not that a `Function` is only a `Consumer` or only a `Supplier`. A Function both takes an input and returns an output, so **the two wildcards can go in opposite directions**.

A common misinterpretation is looking only at the `extends`/`super` syntax while ignoring the usage position. Look at the method `R apply(T value)`: the input goes into the function, and the result comes out of the function. The direction of data determines the direction of the wildcard.

## 4. Why not simply write `Function<T,R>`?

The following signature is valid, but **too restrictive** if the API wants to accept callbacks whose input or output differs along the inheritance hierarchy:

```java
static <T, R> R strictApply(T item, Function<T, R> mapper) {
    return mapper.apply(item);
}
```

This is an illustrative method snippet and requires importing `Function`.

By default, Java generics are **invariant**. This means even though `Dog extends Animal`:

```java
// Function<Animal, StringBuilder> callback = ...;
// Function<Dog, CharSequence> exact = callback; // Does not compile.
```

The type `Function<Animal,StringBuilder>` is not a direct subtype of `Function<Dog,CharSequence>`. Java does not declare variance directly on every generic interface in a way that would let `Function` automatically swap two type arguments in that assignment.

Instead of relying on an invalid assignment, the API designs its parameter as:

```java
static <T, R> R flexibleApply(
        T item, Function<? super T, ? extends R> mapper) {
    return mapper.apply(item);
}
```

Here, a callback taking a supertype of `T` and returning a subtype of `R` can be passed in. This wildcard relationship commonly appears in **method parameters**, where the compiler knows the method will pass `T` in and get `R` out.

You should not think `Function<? super T,? extends R>` changes the definition of the `Function<T,R>` interface at runtime. It is a compile-time constraint at the use site of a generic type.

## 5. Standard API `Stream.map`: the most important pattern

Signature in `java.util.stream.Stream<T>`:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
```

Reading it semantically:

1. The current Stream provides each element of type `T`.
2. The mapper is called with `T`; if the mapper accepts `Object`, `Animal`, or an appropriate supertype of `T`, it still works.
3. Each mapper result is treated as `R`; the mapper may return a subtype of `R`.
4. The API returns `Stream<R>`. That is **the result type inferred by the compiler or requested by the caller**, not necessarily identical to the exact expression type inside the lambda.

With a stream of `Dog`:

```java
Function<Animal, StringBuilder> label = ...;
List<CharSequence> labels = dogs.stream()
        .<CharSequence>map(label)
        .toList();
```

The `.<CharSequence>map(...)` syntax is an **explicit method type argument** to select `R = CharSequence`. It is not required in every call: Java usually infers `R` from the callback and assignment context. In this deliberate example, it helps learners clearly see the `? extends R` part on the result side.

Note: `Stream.toList()` returns `List<CharSequence>` matching `Stream<CharSequence>`, and in Java 17 the resulting list does not support ordinary modification operations. Still, the wildcard on `map` concerns **callback type relationships**, not list immutability.

## 6. Java 17 Program A: Stream, Comparator, Predicate, and Consumer

Create the file **`VarianceApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Predicate;

public class VarianceApiDemo {
    static class Animal {
        private final String name;

        Animal(String name) { this.name = name; }
        String name() { return name; }
    }

    static final class Dog extends Animal {
        Dog(String name) { super(name); }
    }

    public static void main(String[] args) {
        List<Dog> dogs = new ArrayList<>(
                List.of(new Dog("Luna"), new Dog("Milo")));

        Function<Animal, StringBuilder> label =
                animal -> new StringBuilder(
                        animal.name().toUpperCase(Locale.ROOT));

        List<String> labels = dogs.stream()
                .<CharSequence>map(label)
                .map(CharSequence::toString)
                .toList();
        System.out.println("labels: " + labels);

        Comparator<Animal> byName =
                Comparator.comparing(Animal::name);
        dogs.sort(byName);
        System.out.println("sorted: "
                + dogs.stream().map(Dog::name).toList());

        Predicate<Animal> startsWithM =
                animal -> animal.name().startsWith("M");
        System.out.println("predicate: "
                + dogs.stream()
                        .filter(startsWithM)
                        .map(Dog::name)
                        .toList());

        Consumer<Animal> anyAnimal = animal ->
                System.out.println("consume: " + animal.name());
        Consumer<Dog> dogOnly = d ->
                System.out.println("dog: " + d.name());

        Consumer<Dog> combined = dogOnly.andThen(anyAnimal);
        combined.accept(dogs.get(0));
    }
}
```

Compile and run:

```bash
javac -Xlint:all VarianceApiDemo.java
java VarianceApiDemo
```

**Verified stdout:**

```text
labels: [LUNA, MILO]
sorted: [Luna, Milo]
predicate: [Milo]
dog: Luna
consume: Luna
```

The program was verified with `-Xlint:all` without any compiler warnings.

### Reading the `map` part correctly

`dogs.stream()` has type `Stream<Dog>`. The callback `label` takes `Animal`, and `Animal` is a supertype of `Dog`, so it satisfies `? super Dog`.

The callback returns `StringBuilder`, which is a subtype of `CharSequence`, so it satisfies `? extends CharSequence`. The line `.<CharSequence>map(label)` requests the resulting stream to have elements of type `CharSequence`. Next, `map(CharSequence::toString)` produces a stream of `String`, and `toList()` yields a list of `String`.

This is a practical example of **both variance directions in the same callback**, not an unsafe cast.

### Reading the `sort` part correctly

`List<E>.sort` takes:

```java
void sort(Comparator<? super E> c);
```

The list `dogs` has `E = Dog`, while `byName` has type `Comparator<Animal>`. A comparator that knows how to compare any `Animal` can certainly compare any `Dog`.

`? super E` appears here because the comparator **consumes** two values of type `E` to compare them. `List<Dog>.sort(Comparator<Animal>)` is valid; there is no need to rewrite a `Dog`-typed comparator.

### Reading the `filter` part correctly

`Stream<T>.filter` takes:

```java
Stream<T> filter(Predicate<? super T> predicate);
```

A `Predicate<Animal>` can test any `Dog`, so it works with `Stream<Dog>`. The result remains `Stream<Dog>`: `filter` only selects elements and does not create a new result type `R`.

This is why `filter` only needs `? super T` on the predicate parameter and has no `? extends R` in the callback signature.

### Reading the `Consumer.andThen` part correctly

`Consumer<T>.andThen` takes `Consumer<? super T>` but **returns `Consumer<T>`**, without automatically narrowing or widening the receiver's type parameter.

With `dogOnly: Consumer<Dog>`, the call:

```java
Consumer<Dog> combined = dogOnly.andThen(anyAnimal);
```

is valid because `anyAnimal: Consumer<Animal>` can accept any `Dog`. The two consumers are called in order: `dogOnly` first, followed by `anyAnimal`.

Do not confuse this with:

```java
// INVALID:
// Consumer<Dog> wrong = anyAnimal.andThen(dogOnly);
```

The receiver `anyAnimal` is `Consumer<Animal>`, so `andThen` there requires a `Consumer<? super Animal>`. `Consumer<Dog>` only knows how to accept `Dog` and cannot safely handle an arbitrary `Animal`. The compiler rejects it. The `andThen` signature **does not automatically turn `Consumer<Animal>` into `Consumer<Dog>`** just because you assign it to that variable.

## 7. Other standard signatures to read accurately

This table is based on signatures verified using `javap` from the Java 17 JDK:

| API | Key signature | Role of wildcard |
| --- | --- | --- |
| `Stream<T>.map` | `<R> Stream<R> map(Function<? super T, ? extends R>)` | Callback takes T, produces R |
| `Stream<T>.flatMap` | `<R> Stream<R> flatMap(Function<? super T, ? extends Stream<? extends R>>)` | Callback takes T, produces stream of elements used as R |
| `Stream<T>.filter` | `Stream<T> filter(Predicate<? super T>)` | Predicate takes T |
| `Iterable<T>.forEach` | `void forEach(Consumer<? super T>)` | Consumer takes T |
| `List<E>.sort` | `void sort(Comparator<? super E>)` | Comparator compares E's |
| `Consumer<T>.andThen` | `Consumer<T> andThen(Consumer<? super T>)` | Next consumer takes T |
| `Predicate<T>.and` | `Predicate<T> and(Predicate<? super T>)` | Other predicate takes T |
| `Predicate<T>.or` | `Predicate<T> or(Predicate<? super T>)` | Other predicate takes T |
| `Function<T,R>.compose` | `<V> Function<V,R> compose(Function<? super V, ? extends T>)` | Preceding function takes V and produces T |
| `Function<T,R>.andThen` | `<V> Function<T,V> andThen(Function<? super R, ? extends V>)` | Following function takes R and produces V |

**Read signatures as contracts.** A `Predicate<? super T>` or `Consumer<? super T>` only consumes `T`; there is no return type `R` to express in the generic parameters of `Predicate`/`Consumer`.

A `Function` both consumes and returns a result, so it has both a super input and an extends output.

A `Comparator` passed to `sort` also consumes `E` values, but produces a fixed `int` per the `compare` contract, so it does not need `? extends R`.

## 8. `Function.compose` and `Function.andThen`: observing data direction

Take `Function<T,R> f`. Intuitively:

```text
compose(before):
    V ---> before ---> T ---> f ---> R

andThen(after):
    T ---> f ---> R ---> after ---> V
```

Therefore the signature of `compose`:

```java
<V> Function<V, R> compose(
        Function<? super V, ? extends T> before)
```

The `before` function accepts `V` and returns a valid value to serve as input `T` for the current function. This is why the wildcard pair is attached to **V** and **T**, rather than **R**.

And `andThen`:

```java
<V> Function<T, V> andThen(
        Function<? super R, ? extends V> after)
```

The `after` function consumes the result `R` of the current function and produces a value compatible with `V`. The wildcard pair therefore sits on **R** and **V**.

This symmetry helps you remember the API without memorizing every `<` `>`. Draw **the path of the value** in execution order.

## 9. Java 17 Program B: Compose, andThen, and flatMap

Create the file **`FunctionCompositionDemo.java`**:

```java
import java.util.List;
import java.util.function.Function;
import java.util.stream.Stream;

public class FunctionCompositionDemo {
    public static void main(String[] args) {
        Function<Number, String> stringify =
                n -> "n=" + n.intValue();
        Function<CharSequence, Integer> length =
                CharSequence::length;

        Function<String, String> compose =
                stringify.compose(length);
        System.out.println("compose: " + compose.apply("Java"));

        Function<CharSequence, Integer> count =
                CharSequence::length;
        Function<Number, Integer> after =
                stringify.andThen(count);
        System.out.println("andThen: " + after.apply(17));

        Function<CharSequence, Stream<String>> split =
                input -> Stream.of(input.toString().split(" "));
        List<CharSequence> tokens =
                List.of("red blue", "green")
                        .stream()
                        .<CharSequence>flatMap(split)
                        .toList();
        System.out.println("flatMap: " + tokens);
    }
}
```

Commands:

```bash
javac -Xlint:all FunctionCompositionDemo.java
java FunctionCompositionDemo
```

**Verified stdout:**

```text
compose: n=4
andThen: 4
flatMap: [red, blue, green]
```

The program compiled with no warnings under `-Xlint:all`.

### `compose` step by step

The receiver `stringify` has type `Function<Number,String>`, meaning `T=Number`, `R=String`. The `before` callback is `length: Function<CharSequence,Integer>`.

We want the composed function to accept `String`, so `V=String`.

- `length` accepts `CharSequence`, a supertype of `String`, thus satisfying `? super V`.
- `length` returns `Integer`, a subtype of `Number`, thus satisfying `? extends T`.
- The resulting `Function<String,String>` takes `"Java"`, computes length `4`, and produces `"n=4"`.

There is no unsafe `CharSequence -> String` cast; the callback accepts a broader type, so it is safe.

### `andThen` step by step

The receiver is still `stringify: Function<Number,String>`. The following callback is `count: Function<CharSequence,Integer>`. We choose `V=Integer`.

- `count` accepts `CharSequence`, a supertype of `String`, thus satisfying `? super R`.
- `count` returns `Integer`, matching `? extends V`.
- `stringify.apply(17)` gives `"n=17"`, which has four characters.
- `count.apply("n=17")` gives `4`.

The resulting `Function<Number,Integer>` does not change the input type `Number` of the receiver `stringify`.

### `flatMap` and nested wildcards

`Stream<T>.flatMap` takes:

```java
Function<? super T, ? extends Stream<? extends R>>
```

Reading from the inside out:

1. `Stream<? extends R>`: a stream containing values that can be used as `R`.
2. `? extends Stream<? extends R>`: the callback may return an appropriate implementation/subtype of that stream.
3. `? super T`: the callback may accept `T` or a supertype.

In the example `T=String`, `R=CharSequence`:

- `Function<CharSequence,Stream<String>> split` takes `CharSequence`, a supertype of `String`.
- The result is `Stream<String>`, whose `String` elements can be used as `CharSequence`.
- The method `.<CharSequence>flatMap(split)` produces `Stream<CharSequence>`, and after `toList()` it is `List<CharSequence>`.

The nested wildcard levels are **not independent compilation steps for separate real classes**; they are a type mechanism to maintain safety when flattening streams returned by callbacks.

## 10. Distinguishing callback wildcards from collection wildcards

These two expressions are related, yet describe **two different things**:

```java
List<? extends Animal> source;
Function<? super Animal, ? extends CharSequence> mapper;
```

In the **source collection**, `? extends Animal` means the elements read out can be used as `Animal`; however, you cannot arbitrarily add an `Animal` to the list because the actual element type might be `Dog`.

In the **callback**, `? super Animal` means the mapper can accept an `Animal` (or a supertype of `Animal`). Meanwhile, `? extends CharSequence` is a promise that the mapper's result can be used as `CharSequence`.

When designing a method yourself, you often need both:

```java
static <T, R> List<R> mapInto(
        List<? extends T> source,
        Function<? super T, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (T item : source) {
        result.add(mapper.apply(item));
    }
    return result;
}
```

This is an illustrative method and requires importing the appropriate types. Because `source` is a **producer** of `T`, we accept `List<? extends T>`; because `mapper` is a **consumer of T** and **producer of R**, we use `Function<? super T,? extends R>`.

You do not always need all wildcards as above. An API that simply takes `List<T>` can also be valid and sufficient for its needs. However, understanding the role of types helps you choose flexible signatures without introducing unchecked casts.

## 11. Java 17 Program C: writing your own API with both `extends` and `super`

Create the file **`OwnFlexibleApiDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class OwnFlexibleApiDemo {
    static class Base {
        private final String code;

        Base(String code) { this.code = code; }
        String code() { return code; }
    }

    static final class Entry extends Base {
        Entry(String code) { super(code); }
    }

    static <T, R> List<R> mapInto(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        Objects.requireNonNull(source);
        Objects.requireNonNull(mapper);

        List<R> result = new ArrayList<>();
        for (T item : source) {
            result.add(mapper.apply(item));
        }
        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<Entry> entries =
                List.of(new Entry("A"), new Entry("BC"));
        Function<Base, StringBuilder> asLabel =
                b -> new StringBuilder(b.code());

        List<CharSequence> labels = OwnFlexibleApiDemo
                .<Base, CharSequence>mapInto(entries, asLabel);

        System.out.println("labels: " + labels);
        System.out.println("types: "
                + labels.get(0).getClass().getSimpleName());
    }
}
```

Compile and run:

```bash
javac -Xlint:all OwnFlexibleApiDemo.java
java OwnFlexibleApiDemo
```

**Verified stdout:**

```text
labels: [A, BC]
types: StringBuilder
```

### Complete analysis of the three type parameters

The call:

```java
OwnFlexibleApiDemo.<Base, CharSequence>mapInto(entries, asLabel)
```

specifies `T=Base`, `R=CharSequence`.

**Parameter 1: `List<? extends T> source`.**

`entries` has type `List<Entry>`; since `Entry extends Base`, this list is a valid argument for `List<? extends Base>`. The method **only iterates and reads** `Base` elements, without attempting to insert a `Base` into a list that might actually hold only `Entry`.

**Parameter 2: `Function<? super T, ? extends R> mapper`.**

`asLabel` has type `Function<Base,StringBuilder>`. The input `Base` matches `? super Base`, and the output `StringBuilder` is a subtype of `CharSequence`, matching `? extends CharSequence`.

**Return type: `List<R>`.**

The method adds `StringBuilder` values into `List<CharSequence>`; this is safe because every `StringBuilder` is a `CharSequence`. The runtime object remains `StringBuilder` as shown by the `types` line, not transformed into a new class.

**Why use explicit `.<Base,CharSequence>`?**

To clearly show the choice of `T`/`R` in the lesson. Java has type inference for generic methods so many contexts can omit explicit type arguments, but when the compiler infers a narrower type or there are complex overloads, an explicit type witness makes the intended contract clear.

Do not use explicit type witnesses on every call if the compiler already infers cleanly and the code becomes verbose; prefer readability and add them only when you need to control the target type.

## 12. The difference between `? super` in `Function` and a wildcard on the return type

A misleading statement: “`map` returns `Stream<? extends R>` because mapper has `? extends R`”. **False.**

The real signature of `Stream.map` is:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper);
```

The method returns **`Stream<R>`**. The wildcard `? extends R` is **on the type of the passed-in callback**. It merely allows the callback to return a subtype of `R` while the method builds a result stream of type `R`.

Similarly:

```java
<V> Function<T, V> andThen(Function<? super R, ? extends V> after)
```

Returns `Function<T,V>`, **not** `Function<? super T,? extends V>`.

When reading Java APIs, distinguish three layers:

1. **Method parameter type** — e.g., `Function<? super T,? extends R>`.
2. **Method return type** — e.g., `Stream<R>`.
3. **Declared type of the receiving variable** — e.g., `List<CharSequence>`.

Wildcards do not automatically “propagate” from a method parameter to every type argument of the returned value.

## 13. `? super T` does not mean you can read an arbitrary value of type `T`

In `List<? super T>`:

```java
List<? super Dog> sink = new ArrayList<Animal>();
sink.add(new Dog("Milo"));  // Valid.
Object value = sink.get(0); // Only guaranteed to be Object.
```

This is an illustrative snippet assuming `Dog` and `Animal` classes corresponding to Program A.

The reason: the actual list could be `List<Animal>` or `List<Object>`. When you read from `List<? super Dog>`, the compiler only knows an element retrieved is `Object` (aside from `null`), and cannot be sure it is a `Dog`.

In `Function<? super Dog, ? extends CharSequence>`, the same rule applies to the **Function's input**: you can call `apply` with a `Dog`, because every type `? super Dog` can accept a `Dog`. Yet you cannot deduce that the actual callback type is `Function<Dog, ...>`; it might be `Function<Animal,...>` or `Function<Object,...>`.

Precisely by respecting this information boundary, wildcards remain **type-safe**, unlike raw `Function` or unchecked casts.

## 14. Type inference and lambdas: read the context before guessing types

In `Stream<String>`, `map` gives the compiler a known `T` of `String`, then infers `R` from the mapper and result context:

```java
List<String> words = List.of("a", "bb");
List<Integer> lengths = words.stream()
        .map(String::length)
        .toList();
```

A function taking a **supertype** also works:

```java
Function<CharSequence, Integer> count = CharSequence::length;
List<Integer> lengths = words.stream().map(count).toList();
```

These two snippets are separate examples placed in a method with appropriate imports; do not declare two `lengths` variables in the same block. When you need to fix the output to a supertype, use a type witness:

```java
List<CharSequence> names = words.stream()
        .<CharSequence>map(s -> new StringBuilder(s))
        .toList();
```

Do not cast blindly when inference looks confusing. Determine `T`/`R` from **the `Stream.map` signature and the specific mapper**. A later lesson on inference analyzes the entire mechanism of target typing, generic methods, and overloads.

## 15. Lambdas and method references: the same target typing principle

A callback does not inherently carry a single functional interface type when detached from context. For example, `Animal::name` can be used when the target descriptor accepts `Animal` or compatible subtype cases.

In the `VarianceApiDemo` program above:

```java
Comparator<Animal> byName = Comparator.comparing(Animal::name);
dogs.sort(byName);
```

`Comparator.comparing` infers types from the method reference; `List<Dog>.sort` accepts `Comparator<? super Dog>`, so a `Comparator<Animal>` is valid. **This wildcard lives in the API signature**, not because `Comparator<Animal>` turned into `Comparator<Dog>`.

If a callback is reused multiple times, declaring `Function<Animal,StringBuilder>` or `Comparator<Animal>` explicitly helps verify type relationships. When dealing with complex overloads/target typing, read the dedicated lesson on inference and overloads instead of treating lambdas as a “special type” that bypasses the compiler.

## 16. When is `? extends R` not enough?

A callback required to return `String`:

```java
Function<? super Dog, ? extends String> callback
```

**does not** arbitrarily accept `Function<Dog,Object>`: an `Object` could be an `Integer`, `Dog`, `List`, etc., with no guarantee of being a `String`.

For a method requiring `R=String`, the compiler is responsible for rejecting a callback that only promises to return `Object`:

```java
// Illustrates a compile-time error:
Function<Dog, Object> tooBroad = dog -> dog.name();
// Stream<String> out = dogs.stream().<String>map(tooBroad); // Error.
```

Even though **at runtime** the lambda in the example actually returns a `String`, **the declared type of the callback** is only `Function<Dog,Object>`. The method must not rely on inspecting implementation bodies to infer a generic output `String`.

If the callback truly always returns a string, declare `Function<Dog,String>` or `Function<Animal,String>` appropriately. Do not use an unchecked cast from `Function<Dog,Object>` to `Function<Dog,String>` because it can hide risk and push errors to runtime.

Similarly, a `Function<Dog,R>` cannot be used where **every `Animal`** must be handled, because the input might be another kind of `Animal`. This reflects the **`? super T` input direction**.

## 17. Common mistakes when reading API signatures

**Mistake 1 — Reversing `super`/`extends`.** Input going **into** the callback: `? super T`; result coming **out** of the callback: `? extends R`. Do not use `? extends T` for a callback consuming `T` without another reason.

**Mistake 2 — Thinking `Function<Animal,StringBuilder>` is a direct subtype of `Function<Dog,CharSequence>`.** Generics are invariant. It is **the wildcard on the method accepting the callback** that makes the call valid.

**Mistake 3 — Thinking `? super T` “converts” a function's generic type.** The wildcard allows **using** a callback with a wider input, without changing the declared type or runtime class of the callback itself.

**Mistake 4 — Thinking the mapper result must be the exact runtime class `R`.** `StringBuilder` can be used as `CharSequence`; an `? extends R` output accepts subtypes.

**Mistake 5 — Thinking the mapper's wildcard is the wildcard of the resulting `Stream<R>`.** `Stream.map` returns `Stream<R>`, not `Stream<? extends R>` as an automatic side effect.

**Mistake 6 — Thinking `Consumer.andThen` can arbitrarily change the receiver's type parameter.** The method returns `Consumer<T>`; for example, `Consumer<Animal>.andThen(Consumer<Dog>)` is invalid.

**Mistake 7 — Using `List<Object>` when you need to accept `List<Dog>`.** `List<Dog>` is not a `List<Object>`. For a read-only source, consider `List<? extends Animal>`, `List<?>`, or a generic method with a type variable.

**Mistake 8 — Using raw `Function` or raw `List` to bypass compiler errors.** Raw types lose generic guarantees, leading to unchecked warnings and runtime errors. Proper wildcards/type inference are the right fix.

**Mistake 9 — Putting wildcards on every type argument unnecessarily.** An API that uses an exact `Function<T,R>` in an internal context may not need widening. Use wildcards when they meaningfully increase reusability while accurately describing roles.

**Mistake 10 — Assuming `? super T` always returns `T` when reading a collection.** With `List<? super T>`, read results are only guaranteed as `Object`; a super wildcard is suited for consuming/writing `T`, not guaranteeing reading `T`.

**Mistake 11 — Equating source-level variance with runtime type specialization.** `Function`, `Stream`, and `List` still use type erasure; wildcards do not generate new classes per parameterization.

**Mistake 12 — Inferring solely from generic parameter names.** `T`, `R`, `V` are just names. Read whether the method actually **passes to the parameter** or **returns the result**, then determine data direction.

## 18. How to verify signatures yourself via the JDK

These commands let you inspect the APIs directly from the JDK:

```bash
javap -p java.util.stream.Stream
javap -p java.util.function.Function
javap -p java.util.function.Consumer
javap -p java.util.function.Predicate
javap -p java.util.List
javap -p java.lang.Iterable
```

Look for `map`, `flatMap`, `filter`, `compose`, `andThen`, `sort`, and `forEach`. `javap` can display generic signatures so you can inspect wildcards alongside type variables.

For the `OwnFlexibleApiDemo.java` program, run:

```bash
javap -p -s OwnFlexibleApiDemo
```

Verified output excerpt:

```text
static <T, R> java.util.List<R> mapInto(
    java.util.List<? extends T>,
    java.util.function.Function<? super T, ? extends R>);
  descriptor: (Ljava/util/List;Ljava/util/function/Function;)Ljava/util/List;
```

The distinction here is important:

- **The generic signature** displayed by `javap` in the declaration retains wildcards `? extends T`, `? super T`, `? extends R` as metadata.
- **The JVM descriptor** uses the erased classes `List` and `Function`. There is no separate runtime class for `Function<Animal,StringBuilder>` versus `Function<Dog,CharSequence>`.
- The validity of passing the callback is checked by the compiler based on the Java generic type system, not via arbitrary runtime casts between forms of `Function`.

If you want to observe the exact bytecode of the `apply` call, use `javap -p -c OwnFlexibleApiDemo`. However, to verify the core question about **wildcard signatures**, `javap -p` and the JDK source are already the most direct and readable evidence.

## 19. Workflow for choosing wildcards when designing your own API

For a method accepting a generic callback, follow these steps:

1. **Identify what data the API actively feeds into the callback.** If the API calls `mapper.apply(item)` with `item: T`, the callback is a **consumer of `T`**, so it can accept `? super T`.
2. **Identify what result type the API needs from the callback.** If the API wants a result used as `R`, the callback is a **producer of `R`**, so it can return `? extends R`.
3. **Check the method's return signature.** If the method returns `List<R>` or `Stream<R>`, do not turn the output into a wildcard unnecessarily.
4. **Evaluate collection sources.** If only reading `T` values from a list, `List<? extends T>` may be suitable. If writing `T` into a destination, `Collection<? super T>` may be suitable.
5. **Test with real subtypes/supertypes.** Create a callback taking a supertype and returning a subtype; test with a source list of subtype elements.
6. **Run `javac -Xlint:all` with the target Java version.** Fix generic errors with proper type relationships, not raw types just to “make it compile”.
7. **Verify with `javap` if needed:** distinguish generic metadata from the JVM descriptor after erasure.
8. **Keep the design readable.** Wildcards serve flexibility when data direction is right; do not complicate every parameter if the benefit is minor.

For callbacks, a very effective quick question is: *“Can I pass a T to this function without casting? And can the function's return value be treated as R?”* If both are yes, the signature `Function<? super T,? extends R>` is doing its job properly.

## 20. Exercises with answers

### Exercise 1 — Choosing callbacks for a stream

Given `Stream<Dog>`, `Dog extends Animal`, and needing a result stream of type `CharSequence`. Which callbacks can be used with `map` for `R=CharSequence`?

```java
Function<Animal, String> a = Animal::name;
Function<Dog, StringBuilder> b = d -> new StringBuilder(d.name());
Function<Object, CharSequence> c = Object::toString;
```

**Answer:** all three satisfy `Function<? super Dog,? extends CharSequence>` (assuming the `Animal`/`Dog` classes from the example). `Animal`, `Dog`, and `Object` can all accept `Dog` under the type relationship; `String`, `StringBuilder`, and `CharSequence` can all be used as `CharSequence`.

### Exercise 2 — Why is this callback wrong?

```java
Function<Animal, Object> broadResult = animal -> animal.name();
// Stream<String> out = dogs.stream().<String>map(broadResult);
```

**Answer:** `Object` is not a subtype of `String`. Even though the lambda actually returns a string at runtime, the callback's declared type only promises `Object`; `? extends String` does not accept it.

### Exercise 3 — Which type does `Consumer.andThen` preserve?

Given `Consumer<Dog> dogOnly` and `Consumer<Animal> allAnimals`, what type does `dogOnly.andThen(allAnimals)` have?

**Answer:** `Consumer<Dog>`. The next consumer accepts `Animal`, matching `? super Dog`, while the return type of `andThen` remains `Consumer<T>` with `T=Dog`.

### Exercise 4 — Comparator by supertype

Why is `List<Dog>.sort(Comparator<Animal>)` valid?

**Answer:** `List<E>.sort` takes `Comparator<? super E>`; `Comparator<Animal>` can compare two `Dog` instances because every `Dog` is an `Animal`.

### Exercise 5 — In what order does `compose` run?

Given `Function<Number,String> f` and `Function<CharSequence,Integer> before`, is calling `f.compose(before)` to produce `Function<String,String>` valid?

**Answer:** valid. `before` accepts `String` because `CharSequence` is a supertype, and returns `Integer` because `Integer` is a subtype of `Number`; then `f` accepts the result as `Number`.

### Exercise 6 — Which wildcards does `flatMap` have?

Why does `Stream.flatMap` take `Function<? super T,? extends Stream<? extends R>>` instead of just `Function<T,Stream<R>>`?

**Answer:** so the callback can accept a supertype of `T` and return a stream of elements that are subtypes of `R`, while the API safely flattens them into `Stream<R>`.

### Exercise 7 — Reading/writing wildcard collections

If a method only needs to iterate over `List<Dog>` to obtain `Animal` elements, how does `List<? extends Animal>` help? Does it allow calling `list.add(new Animal(...))`?

**Answer:** it accepts many kinds of lists of `Animal` subtypes for safe **reading**. You cannot add an arbitrary `Animal`, because the actual list might only permit `Dog` or another subtype.

### Exercise 8 — Generic output type

With mapper `Function<Animal,StringBuilder>` and source `Stream<Dog>`, if left to default compiler inference, the result element type may be `StringBuilder`. How do you explicitly choose `R=CharSequence`?

**Answer:** use `.<CharSequence>map(mapper)` or an appropriate generic target-typing context where the compiler can infer it. The explicit form is the easiest to verify in this example.

### Exercise 9 — Distinguishing generic methods from runtime

Running `javap -s` shows the descriptor `(List,Function)List` for `mapInto`, despite the generic signature having multiple wildcards. Does that mean the compiler ignores `? super`/`? extends` type checking?

**Answer:** no. The compiler checks the generic constraints in source code and emits the erased descriptor for the JVM; generic signature metadata and compile-time checking are separate layers from the erased runtime descriptor.

## 21. Checklist before using wildcards in an API

- [ ] Identify **which `T` is passed into** the callback and **which `R` is received back**.
- [ ] If the callback accepts `T`, consider `? super T`.
- [ ] If the callback returns a subtype compatible with `R`, consider `? extends R`.
- [ ] Distinguish the variance of **callback parameters** from **the API's return type**.
- [ ] Read the exact signatures of `Stream.map`, `flatMap`, `filter`, `Consumer.andThen`, and `Function.compose/andThen`.
- [ ] Do not confuse generic invariance with use-site wildcard capability.
- [ ] Do not use raw types or unchecked casts to bypass a variance-direction error.
- [ ] If generic inference is complex, try meaningful explicit method type arguments.
- [ ] Test both input-subtype and output-subtype cases with a runnable example.
- [ ] Remember `getClass()`/erasure does not generate separate runtime classes for each generic callback.

## Conclusion

**`Function<? super T, ? extends R>`** is how the Java Standard API expresses a flexible yet safe callback contract: the function can **consume T via a supertype** and **produce R via a subtype**. The same reasoning appears in `Stream.map`, `flatMap`, `Predicate<? super T>`, `Consumer<? super T>`, `Comparator<? super T>`, `Function.compose`, and `Function.andThen`.

Read **the direction of data flow**, rather than just memorizing wildcard syntax. When a callback receives a value, think `super`; when a callback returns a value used as the target type, think `extends`. That is the foundation for writing reusable Java lambdas, method references, and generic APIs without sacrificing type safety.