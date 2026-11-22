# Wildcards `? super` and `? extends` in Function-Accepting Java APIs

## 1. Objectives

In Java, methods that accept a lambda, method reference, or functional interface object often use types such as:

~~~java
Function<? super T, ? extends R>
Consumer<? super T>
Predicate<? super T>
Comparator<? super T>
Supplier<? extends T>
~~~

The wildcards here **are not syntactic decoration**. They describe the valid type relationship between **the data an API passes into a function** and **the result the API receives from the function**.

After this lesson, you will be able to:

- Explain why Java generics are **invariant** by default, even when component types have an inheritance relationship.
- Read `? super` and `? extends` correctly according to the **PECS** rule (Producer Extends, Consumer Super).
- Choose wildcards for the **input and output** of `Function<T,R>`, `BiFunction<T,U,R>`, `Consumer<T>`, `Predicate<T>`, `Comparator<T>`, and `Supplier<T>`.
- Understand the signatures in `Stream.map`, `Stream.filter`, `Iterable.forEach`, `Function.andThen`, and `Function.compose`.
- Explain how **target typing**, generic method inference, and explicit type witnesses help compile calls with wildcards.
- Avoid raw types, unsafe casts, and reversed wildcards.

## 2. From Inheritance Relationships to Generic Invariance

Suppose we have a class `Animal` and a class `Dog extends Animal`. A `Dog` can be used wherever an `Animal` is required:

~~~java
Dog dog = new Dog("Milo");
Animal animal = dog;
~~~

This snippet assumes `Animal` and `Dog` have appropriate constructors; the complete program appears in Section 8.

With generic types, however, that relationship **does not automatically lift**:

~~~java
List<Dog> dogs = new ArrayList<>();
// List<Animal> animals = dogs; // Does not compile.
~~~

If the assignment above were allowed, a caller could add a `Cat` through the `animals` variable, even though the underlying list is actually `List<Dog>`. Java prevents this error through **invariance**: `List<Dog>` is not a subtype of `List<Animal>`.

Similarly:

~~~java
Function<Animal, String> label = animal -> "pet";
// Function<Dog, CharSequence> f = label; // Does not compile.
~~~

In terms of capability, a function accepting an **Animal** naturally accepts a `Dog`, and a `String` is a **CharSequence**. However, the two concrete generic types `Function<Animal,String>` and `Function<Dog,CharSequence>` have no direct subtyping relationship.

**Wildcards** allow defining a target type that describes **a family of compatible generic types**, instead of forcing an invariant assignment to succeed.

## 3. Producer Extends and Consumer Super (PECS)

The PECS rule is oriented from the perspective of where **values are used**:

- If a structure **produces** values of type `T` for you to read out, typically use **`? extends T`**.
- If a structure **consumes** values of type `T` that you pass in, typically use **`? super T`**.

Let's examine `List` before moving on to functions.

### 3.1. `? extends`: Reading Out as a Supertype

~~~java
List<Integer> integers = List.of(2, 4, 6);
List<? extends Number> numbers = integers;
Number first = numbers.get(0); // 2

// numbers.add(7); // Does not compile.
~~~

`? extends Number` could represent `Integer`, `Double`, or another subtype of `Number`. You are guaranteed to read out a `Number`, but **you do not know the exact subtype**, so you cannot add an arbitrary `Integer` through that reference. Adding `null` is a type-checking exception, though the concrete `List` implementation may still reject mutation.

### 3.2. `? super`: Passing a `T` Value In

~~~java
List<Number> storage = new ArrayList<>();
List<? super Integer> target = storage;

target.add(10);            // Valid.
target.add(20);            // Valid.
Object first = target.get(0); // The only guaranteed type is Object.
~~~

`? super Integer` could be `Integer`, `Number`, or `Object`. Putting an `Integer` in is always safe; conversely, reading out through the wildcard only guarantees the general type `Object`. You cannot arbitrarily put a `Double` in, because the actual type could be `List<Integer>`.

**PECS describes the direction of data flow at an API**, not that every generic variable should contain wildcards. When creating a concrete structure, usually use an exact type such as `List<Dog>`.

## 4. Functional Interfaces Have Two Data Directions

`Function<T,R>` declares the SAM:

~~~java
R apply(T value);
~~~

Thus:

- `T` is the **input** supplied by the caller to the function: the function **consumes** `T`.
- `R` is the **output** created by the function: the function **produces** `R`.

An API that wants to pass `T` into a function and receive `R` back can declare:

~~~java
Function<? super T, ? extends R>
~~~

Read aloud:

> Accept a function that accepts `T` or a supertype of `T`, and returns `R` or a subtype of `R`.

For example:

~~~java
Function<Animal, String> animalLabel =
        animal -> animal.name();

Function<? super Dog, ? extends CharSequence> dogLabel =
        animalLabel;

CharSequence result = dogLabel.apply(new Dog("An"));
~~~

Valid because **Animal** is a supertype of `Dog` on the **input** side, and **String** implements `CharSequence` on the **output** side.

You cannot assign directly:

~~~java
// String exact = dogLabel.apply(new Dog("An")); // Does not compile.
~~~

At this point the compiler only knows the result can be used as a `CharSequence`. The actual type could be `String`, `StringBuilder`, or another `CharSequence` subtype, rather than necessarily `String`.

**Note:** wildcards do not turn `Function<Animal,String>` into a subtype of `Function<Dog,CharSequence>`; they express a target type that accepts `Function` instances with matching input/output types.

## 5. Designing a Mapper-Accepting API

A list-transforming method can use:

~~~java
static <T, R> List<R> transform(
        List<T> items,
        Function<? super T, ? extends R> mapper) {
    return items.stream()
            .<R>map(mapper)
            .toList();
}
~~~

This is an **illustrative method**, which must be placed in a class with `List` and `Function` imported.

At the call site, if `items` is `List<Dog>`, the caller can pass `Function<Animal,String>`; if the result is needed as `List<CharSequence>`, you can also declare:

~~~java
List<Dog> dogs = List.of(new Dog("Milo"));
Function<Animal, String> label = Animal::name;

List<CharSequence> text = transform(dogs, label);
~~~

`Animal` accepts `Dog`, and `String` is a `CharSequence`. **Type inference** infers `T` and `R` from the arguments and the requested result type.

### 5.1. Why Does the Implementation Write `.<R>map(mapper)`?

`Stream.map` has its own type parameter `<R>` independent of the `transform` method. When `mapper` has type `Function<? super T,? extends R>`, some inference combinations cause the compiler to hold the result type of `map` as a specific **capture** of `? extends R`; calling `.toList()` might not be seen as `List<R>` if left entirely to inference.

Writing:

~~~java
items.stream().<R>map(mapper).toList()
~~~

is an **explicit type witness**, instructing `map` to use `transform`'s exact type `R`. It remains type-safe because `mapper` promises to return a value usable as `R`; no cast or raw type is needed. This is an example of a place where **Java's type inference** may need assistance from the author.

Conversely, in simple calls such as:

~~~java
List<String> labels = dogs.stream()
        .map(label)
        .toList();
~~~

if `mapper` has type `Function<Animal,String>`, the compiler typically infers `R = String` directly and no type witness is needed.

### 5.2. Why Not Write `Function<T,R>`?

If the API wrote `Function<T,R>`, then `Function<Animal,String>` would not necessarily match `T=Dog` and `R=CharSequence` exactly. When you genuinely need **a function accepting a supertype and returning a subtype**, wildcards in **the parameter signature** express the contract better.

Do not add wildcards to every ordinary variable declaration. A concrete implementation should usually have a clear type:

~~~java
Function<Animal, String> label = Animal::name;
~~~

Only widen at the API position that needs to **accept a family of functions**.

## 6. Standard APIs Using `? super`

### 6.1. `Stream.filter`: `Predicate` Accepting an Element

Main signature:

~~~java
Stream<T> filter(Predicate<? super T> predicate)
~~~

If a stream contains `Dog`, a `Predicate<Animal>` can inspect each `Dog`:

~~~java
Predicate<Animal> hasName = animal -> animal.name() != null;
List<Dog> namedDogs = dogs.stream()
        .filter(hasName)
        .toList();
~~~

`Predicate` **consumes `T`**, then returns a primitive `boolean`, so the input `? super T` is appropriate. It does not **produce a `T`**.

### 6.2. `Iterable.forEach`: `Consumer` Accepting an Element

~~~java
void forEach(Consumer<? super T> action)
~~~

With `List<Dog>`:

~~~java
Consumer<Animal> logAnimal =
        animal -> System.out.println(animal.name());

dogs.forEach(logAnimal);
~~~

Any action that handles `Animal` can handle `Dog`. **`forEach` can produce side effects**, and how the callback runs depends on the implementing API; wildcards only speak to types, not ordering or concurrency guarantees.

### 6.3. `Comparator<T>`: Accepting Two `T` Values

APIs such as `Stream<T>.sorted` or `List<T>.sort` accept `Comparator<? super T>`.

~~~java
Comparator<Animal> byName =
        Comparator.comparing(Animal::name);

List<Dog> sorted = dogs.stream()
        .sorted(byName)
        .toList();
~~~

A `Comparator<Animal>` can compare two `Dog` instances. The `Comparator` must uphold its contract regarding sign, transitivity, and consistency; wildcards do not fix a broken comparator or handle data mutated during sorting.

### 6.4. `Stream.map`: Input and Output

`Stream<T>.map` declares:

~~~java
<R> Stream<R> map(
        Function<? super T, ? extends R> mapper)
~~~

The function **accepts element `T`** and **returns a result of type `R`**: matching the pattern of `super` on input, `extends` on output. With `Function<Animal,String>` on `Stream<Dog>`, `.map(label)` is usually enough to infer `Stream<String>`. When you want to pin `R` to `CharSequence`:

~~~java
List<CharSequence> result = dogs.stream()
        .<CharSequence>map(label)
        .toList();
~~~

`Stream.toList()` since Java 16 returns a list that does not support mutation; it does not make mutable elements deeply immutable.

## 7. Result-Producing Sources Using `? extends`

`Supplier<T>` has SAM `T get()`: it **only produces values**, accepting no arguments from the caller at the `get` call.

An API that wants to create an `Animal` can accept:

~~~java
static Animal create(
        Supplier<? extends Animal> source) {
    return source.get();
}
~~~

A `Supplier<Dog>` can be passed in because `Dog` is an `Animal`. At the **function output** position, using `? extends Animal` increases reusability.

Conversely, `Supplier<? super Dog>` only guarantees the result is an unknown supertype of `Dog`; you cannot conclude the result is always an `Animal` if the actual type could be `Object`.

Note: wildcards **do not guarantee non-null**. A type-valid `Supplier` can return `null` if the contract permits it.

## 8. Complete Java 17: Putting the Wildcards Together

This example demonstrates a `List<T>` transformation API, using a comparator and consumer accepting a supertype, a supplier returning a subtype, and a `BiFunction` with two inputs.

Create the file **WildcardFunctionDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.function.BiFunction;
import java.util.function.Consumer;
import java.util.function.Function;
import java.util.function.Supplier;

public class WildcardFunctionDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        String name() {
            return name;
        }
    }

    static final class Dog extends Animal {
        Dog(String name) {
            super(name);
        }
    }

    static <T, R> List<R> transform(
            List<T> items,
            Function<? super T, ? extends R> mapper) {
        return items.stream().<R>map(mapper).toList();
    }

    static void observeDogs(
            List<Dog> dogs,
            Consumer<? super Dog> observer) {
        dogs.forEach(observer);
    }

    static Animal createAnimal(
            Supplier<? extends Animal> source) {
        return source.get();
    }

    public static void main(String[] args) {
        List<Dog> dogs = List.of(
                new Dog("Milo"),
                new Dog("An")
        );

        Function<Animal, String> label =
                animal -> "pet:" + animal.name();
        Comparator<Animal> byName =
                Comparator.comparing(Animal::name);
        Consumer<Animal> observer =
                animal -> System.out.println("seen " + animal.name());

        List<String> labels = transform(
                dogs.stream().sorted(byName).toList(),
                label
        );
        System.out.println("labels: " + labels);

        List<CharSequence> asText = transform(dogs, label);
        System.out.println("first text: " + asText.get(0));

        observeDogs(dogs, observer);

        Supplier<Dog> dogFactory = () -> new Dog("Zoe");
        Animal created = createAnimal(dogFactory);
        System.out.println("created: " + created.name());

        BiFunction<Animal, Integer, String> indexed =
                (animal, index) -> animal.name() + "#" + index;
        BiFunction<? super Dog, ? super Integer,
                ? extends CharSequence> adapter = indexed;
        CharSequence code = adapter.apply(dogs.get(0), 3);
        System.out.println("code: " + code);

        Function<CharSequence, Integer> length =
                CharSequence::length;
        Function<Animal, Integer> labelLength =
                label.andThen(length);
        System.out.println("length: " + labelLength.apply(dogs.get(1)));
    }
}
~~~

Compile and run:

~~~bash
javac WildcardFunctionDemo.java
java WildcardFunctionDemo
~~~

**Exact output:**

~~~text
labels: [pet:An, pet:Milo]
first text: pet:Milo
seen Milo
seen An
created: Zoe
code: Milo#3
length: 6
~~~

**Explanation:**

1. `Comparator<Animal>` works in `Stream<Dog>` because `sorted` accepts `Comparator<? super Dog>`. The `labels` result is ordered ascending by name: `An` before `Milo`.
2. `Function<Animal,String>` works as a mapper for `Dog` thanks to `? super Dog`; the `String` output can be used as `CharSequence` thanks to `? extends CharSequence`.
3. `List<CharSequence> asText` is validly inferred when `transform` has a type witness on `map`. `asText.get(0)` is the string created from Milo: `pet:Milo`.
4. `Consumer<Animal>` is passed to `observeDogs`, which requires `Consumer<? super Dog>`. It iterates the original list in order `Milo` then `An`, not using the sorted `labels` list.
5. `Supplier<Dog>` is passed to `createAnimal` because the method only needs to read an `Animal` from the source. The result has name `Zoe`.
6. `BiFunction<Animal,Integer,String>` is compatible with `BiFunction<? super Dog,? super Integer,? extends CharSequence>`, so the result is `Milo#3`.
7. `label.andThen(length)` is valid because `label` returns `String` and `length` accepts `CharSequence`. The string `pet:An` is 6 UTF-16 code units long.

The program requires no casts or raw types. Console printing is an intentional side effect; wildcards themselves do not guarantee purity, thread safety, or absence of exceptions.

## 9. `andThen` and `compose` on `Function`

For `Function<T,R>`, the simplified signatures are:

~~~java
<V> Function<T,V> andThen(
        Function<? super R, ? extends V> after)

<V> Function<V,R> compose(
        Function<? super V, ? extends T> before)
~~~

For **`andThen`**, the current function produces `R`; the `after` function must **consume `R`**, so it uses `? super R`, and produce `V`, so it uses `? extends V`.

For **`compose`**, `before` runs first; it must produce something usable as `T`, so it uses `? extends T`. The new composed function accepts `V`, so `before` must consume `V` or a supertype, namely `? super V`.

For example:

~~~java
Function<Animal, String> name = Animal::name;
Function<CharSequence, Integer> length = CharSequence::length;

Function<Animal, Integer> count = name.andThen(length);
~~~

Valid because `String` implements `CharSequence`. Do not confuse **`compose`** with **`andThen`** in order of execution: `f.andThen(g)` is **`f` then `g`**; `f.compose(g)` is **`g` then `f`**.

## 10. `BiFunction` with Two Inputs

`BiFunction<T,U,R>` has the signature `R apply(T t,U u)`. Both **`T` and `U` are consumed**, while `R` is produced. Therefore the flexible parameter pattern is:

~~~java
BiFunction<? super T, ? super U, ? extends R>
~~~

For example:

~~~java
BiFunction<Animal, Number, String> display =
        (animal, number) -> animal.name() + number;

BiFunction<? super Dog, ? super Integer,
        ? extends CharSequence> compatible = display;
~~~

`Animal` accepts `Dog`; `Number` accepts `Integer`; `String` is a `CharSequence`. These are three safe relationships simultaneously.

If an API needs primitive numeric types without boxing, check the built-in specializations in `java.util.function` such as `ToIntFunction<T>`; primitive `int` cannot be placed as a generic type argument. Choose the interface kind by contract first, then measure performance if needed.

## 11. When Should You Not Use Wildcards?

An API that needs functions with exact types can choose `Function<T,R>`. Wildcards are useful when you genuinely want to accept **broader inputs** or **narrower outputs**. Using them everywhere can make code harder to read and make type inference more difficult.

For example, declare concrete implementations specifically:

~~~java
Function<Animal, String> name = Animal::name;
~~~

Then let the API widen its parameter itself:

~~~java
static <T,R> R applyOne(
        T item,
        Function<? super T, ? extends R> mapper) {
    return mapper.apply(item);
}
~~~

No cast is needed. If you declare the `mapper` variable as `Function<? super Dog, ? extends CharSequence>` from the start, the return value is only guaranteed to be `CharSequence`; you may lose the specific `String` type that callers want to use.

## 12. Common Misconceptions

| Misconception | Accurate Explanation |
| --- | --- |
| `Function<Animal,String>` is a subtype of `Function<Dog,CharSequence>` | Generics are invariant; assignment works through a compatible wildcard target type |
| `? super Dog` means the output is `Animal` | `super` on input allows passing `Dog`; it says nothing about output |
| `? extends Animal` means you can add `Dog` | With `List<? extends Animal>`, you cannot arbitrarily add `Dog` |
| Using `? extends T` on a mapper's input is always better | Does not guarantee the function accepts an arbitrary `T` |
| Using `? super R` on a mapper's output | Can only guarantee the result is `Object`, not `R` |
| Type inference will always understand every wildcard automatically | Some situations require explicit types or `.<R>map(...)` |
| Wildcards automatically check `null`, side effects, or concurrency | They are only compile-time type-compatibility rules |
| Using raw `Function` will solve the error | Drops type safety, easily causes unchecked warnings and runtime errors |

### 12.1. Reversing the Wildcard on Input

Suppose:

~~~java
Function<? extends Dog, ? extends CharSequence> wrong;
~~~

The actual input type could be a very narrow subtype of `Dog`. Therefore the compiler cannot allow you to call `wrong.apply(new Dog("An"))` in general. When the API needs to **pass `Dog` to the mapper**, it must be `Function<? super Dog, ? extends CharSequence>`.

### 12.2. Reversing the Wildcard on Output

~~~java
Function<? super Dog, ? super CharSequence> wrongOutput;
~~~

On output, `? super CharSequence` could be `CharSequence` or `Object`, so the caller can only rely on `Object`. If you want to guarantee reading as `CharSequence`, use `? extends CharSequence`.

### 12.3. Wildcard Capture

Each `?` corresponds to an **unknown** type that the compiler can represent via **capture conversion**. For example, `List<?>` reads out as `Object`, but you cannot arbitrarily add `Object` because the actual element type is unknown.

If you encounter a capture error, identify the relationship that needs constraining, name the type via a **generic helper**, or use a type witness and an intermediate variable with a concrete type. Do not fix it with raw types or unchecked casts just to silence the error.

## 13. Testing Function-Accepting APIs

You should test meaningful contracts:

1. Mapper accepting a **supertype**: `Function<Animal,String>` processing `List<Dog>`.
2. Mapper returning a **subtype**: `String` read as `CharSequence`.
3. `Consumer`/`Predicate` accepting a supertype and processing `Dog`.
4. `Comparator<Animal>` sorting `Dog` by the right criterion, including equal keys.
5. `Supplier<Dog>` producing a value used as `Animal`.
6. Functions throwing exceptions or returning `null`: wildcards do not handle these automatically.
7. Type inference working with the desired target types; helper with explicit type witness when needed.

The following manual check snippet is placed in a context that has `applyOne`, `Animal`, and `Dog`:

~~~java
Function<Animal, String> name = Animal::name;
Dog dog = new Dog("An");
CharSequence result = applyOne(dog, name);

if (!result.toString().equals("An")) {
    throw new AssertionError("Unexpected result");
}
~~~

Runtime tests only verify a few concrete inputs; type-safe relationships are primarily verified by the compiler when compiling the source code.

## 14. Exercises

**Exercise 1 — Choosing parameter types.** An API processing `Student` needs a logging callback that returns no result. Should you declare `Consumer<Student>`, `Consumer<? super Student>`, or `Consumer<? extends Student>`?

**Answer:** `Consumer<? super Student>` is the most flexible within this contract. It allows `Consumer<Student>`, `Consumer<Person>`, or `Consumer<Object>` when compatible. `Consumer<Student>` is valid but narrower.

**Exercise 2 — Passing arguments and reading results.** With `Function<? super Dog,? extends Animal>`, can you pass a `Dog`, pass an `Animal`, or read the result as an `Animal`?

**Answer:** you can pass a `Dog`, and you can read the result as an `Animal`. You are not guaranteed to be able to pass an arbitrary `Animal`, because the actual input type could be `Dog` itself.

**Exercise 3 — `Supplier` or `Consumer`?** One API requires a source that creates animals; another passes a `Dog` to a callback that prints data. Which parameter forms do you choose?

**Answer:** creation source `Supplier<? extends Animal>`, action receiving `Dog` `Consumer<? super Dog>`.

**Exercise 4 — Fixing a generic signature:**

~~~java
static <T,R> List<R> mapAll(
        List<T> source,
        Function<T,R> mapper) {
    return source.stream().map(mapper).toList();
}
~~~

Write a version that accepts `Function<Animal,String>` to process `List<Dog>`, with output usable as `List<CharSequence>`.

**Answer:**

~~~java
static <T,R> List<R> mapAll(
        List<T> source,
        Function<? super T, ? extends R> mapper) {
    return source.stream().<R>map(mapper).toList();
}
~~~

**Exercise 5 — Explaining the type witness.** Why is `.<R>map(mapper)` useful in the implementation of `mapAll` even though `mapper` already has type `? extends R`?

**Answer:** the type witness forces the generic method `Stream.map` to use `mapAll`'s exact result type `R`; it avoids cases where inference resolves to an unknown captured subtype of `R` such that `toList()` is not seen as `List<R>`. Specifying `R` remains safe under the `? extends R` contract.

## 15. Takeaways

**`Function<? super T, ? extends R>`** is the most important pattern when a Java API **accepts a function**: the caller passes `T` in, the function can accept a supertype of `T`, and the result can be used as `R`.

**`Consumer / Predicate / Comparator<? super T>`** have inputs that consume `T`; **`Supplier<? extends T>`** produces a value of `T` or a subtype; **`BiFunction<? super T, ? super U, ? extends R>`** has two consumed inputs and one produced output.

Decide wildcards by the direction values move, not by class names or syntactic habit. Concrete generic types remain invariant; wildcards widen **function-accepting contracts** without losing type safety. If the compiler struggles with capture and inference, use a generic helper, explicit types, or an appropriate explicit type witness instead of raw types or unsafe casts.