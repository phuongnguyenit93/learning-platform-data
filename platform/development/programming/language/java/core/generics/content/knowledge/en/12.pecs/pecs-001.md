# The PECS Rule: Use `extends` for Producers and `super` for Consumers

When a Java Generics method works with a collection, it is important to determine **whether that collection supplies data to the method or receives data from the method**. This is the idea behind **PECS — Producer Extends, Consumer Super**:

- **Producer:** the method **reads values of type `T`** from the input object. Typically declared as `Collection<? extends T>`, `List<? extends T>`, or an equivalent generic form.
- **Consumer:** the method **writes values of type `T`** into the input object. Typically declared as `Collection<? super T>` or `List<? super T>`.

`extends` and `super` are chosen based on **the role of the parameter in the method being written**, not on whether the object supports reading and writing in general. An `ArrayList<Integer>` can be passed from a producer perspective in a sum method and from a consumer perspective in a method that adds integers.

PECS makes it possible to accept appropriate subtypes/supertypes **without breaking type safety**, especially given that Java generics are invariant in their type arguments.

## 1. The Problem: Why Not Use `List<Number>` for Everything?

Suppose you have `List<Integer>` and `List<Double>`. Since both `Integer` and `Double` are `Number`, a sum method should be able to read both lists. However, this assignment is forbidden:

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = integers; // COMPILATION ERROR.
~~~

This is an **ill-typed illustrative snippet**; it needs to be placed inside a class and import `java.util.*` if you want to try compiling it. Java does not treat `List<Integer>` as a subtype of `List<Number>`. If it were allowed, the `numbers` reference could add a `Double` to a list that only accepts `Integer`.

On the other hand, if a method only wants to **add `Integer` values**, the destination could be `List<Integer>`, `List<Number>`, or `List<Object>`: all three types can accept an `Integer`.

Two needs require two separate contracts:

~~~java
static double sum(List<? extends Number> source) {
    double total = 0.0;
    for (Number number : source) {
        total += number.doubleValue();
    }
    return total;
}

static void addDefaults(List<? super Integer> destination) {
    destination.add(10);
    destination.add(20);
}
~~~

These are **two illustrative methods**, which need to be placed in a class with `import java.util.List;`. `sum` requires a producer supplying values readable as `Number`; `addDefaults` requires a consumer capable of receiving `Integer` values. Both declare wildcards, but in opposite directions.

## 2. Producer Extends: Supplying `? extends T`

Look at the signature:

~~~java
static void printNumbers(List<? extends Number> source) {
    for (Number number : source) {
        System.out.println(number);
    }
}
~~~

This means: **the concrete type argument of the list must be `Number` or a subtype of `Number`**. Therefore `printNumbers` accepts `List<Integer>`, `List<Double>`, `List<Number>`, and other compatible numeric lists.

The compiler does not know the concrete subtype of `source`, but it knows **every element read out can be used as `Number`**:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = integers;

Number first = source.get(0); // Valid.
Object alsoFirst = source.get(0); // Valid.

// Integer exact = source.get(0); // ERROR: subtype could be Double.
// source.add(3);                // ERROR: actual subtype could be Double.
// source.add(3.5);              // ERROR: actual subtype could be Integer.
~~~

This is an **illustrative snippet that needs to be placed in a class with `import java.util.*;`**. `source` points to `List<Integer>`, yet the **static type contract** only says `List<? extends Number>`. The compiler is not allowed to use information outside this type declaration to permit adding arbitrary `Integer` values.

If `source.add(3)` were allowed, the same signature could be referencing a `List<Double>` and cause a type error. Hence, a producer is convenient for **reading**, but cannot add non-`null` values via `add`.

### Runnable Example: Reading Multiple Subtypes in One Method

Create the file **`ProducerDemo.java`**:

~~~java
import java.util.List;

public class ProducerDemo {
    private static double sum(List<? extends Number> source) {
        double total = 0.0;
        for (Number n : source) {
            total += n.doubleValue();
        }
        return total;
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(2, 4, 6);
        List<Double> doubles = List.of(1.5, 2.5);
        List<Number> mixed = List.of(3, 4.5);

        System.out.println("integers = " + sum(integers));
        System.out.println("doubles = " + sum(doubles));
        System.out.println("mixed = " + sum(mixed));
    }
}
~~~

Compile and run on Java 17+:

~~~bash
javac ProducerDemo.java
java ProducerDemo
~~~

Stdout:

~~~text
integers = 12.0
doubles = 4.0
mixed = 7.5
~~~

One method handles all three list types because the sum operation only uses operations guaranteed by `Number`. There are no unchecked casts or collection copies.

## 3. Consumer Super: Receiving `? super T`

Look at the signature:

~~~java
static void addNumbers(List<? super Integer> destination) {
    destination.add(5);
    destination.add(10);
}
~~~

This contract accepts `List<Integer>`, `List<Number>`, or `List<Object>` because **all three can store elements of type `Integer`**. It does not accept `List<Double>`: `Double` is another subtype of `Number`, not a supertype of `Integer`.

~~~java
List<Integer> integers = new ArrayList<>();
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

addNumbers(integers); // Valid.
addNumbers(numbers);  // Valid.
addNumbers(objects);  // Valid.

// addNumbers(new ArrayList<Double>()); // ERROR: Double is not a supertype of Integer.
~~~

The snippets above illustrate calling an already declared method; they need to be placed inside a class and import `java.util.*`.

Calling `destination.add(5)` is possible because `5` is boxed into `Integer`. However, the compiler does not allow adding an arbitrary `Number`:

~~~java
List<? super Integer> destination = new ArrayList<Number>();

destination.add(Integer.valueOf(7)); // Valid.
destination.add(8);                  // Valid via autoboxing.
destination.add(null);               // Type-valid.
// destination.add(Double.valueOf(1.5)); // ERROR.
// destination.add(new Object());       // ERROR.
~~~

This is an **illustrative snippet that needs `import java.util.*`**. The reason: the wildcard reference could point to a `List<Integer>`, so the compiler must not allow adding `Double` or `Object` to it. `null` is compatible with every reference type, though the actual collection might still forbid `null` or not support modification.

### Why Does a Consumer Only Allow Reading as `Object`?

`List<? super Integer>` can point to a `List<Object>` containing `String`, `Boolean`, or various other values, so **there is no guarantee that all existing elements are `Integer`**:

~~~java
List<Object> any = new ArrayList<>();
any.add("hello");
any.add(42);

List<? super Integer> sink = any;
sink.add(7);

Object first = sink.get(0); // Valid: actually a String.
// Integer n = sink.get(0); // COMPILATION ERROR.
// Number n = sink.get(0);  // COMPILATION ERROR.
~~~

Therefore, `super` is **strong on the `T`-writing side** but **weaker on the reading side**: the compiler only guarantees the common type `Object`. It does not infer the type of already-existing data solely from the elements a method has just added.

## 4. Java 17+ Example: Producer and Consumer in One Program

Create the file **`PecsBasicsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PecsBasicsDemo {
    private static void printAll(List<? extends Number> source) {
        for (Number n : source) {
            System.out.print(n + " ");
        }
        System.out.println();
    }

    private static void appendIds(List<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    public static void main(String[] args) {
        List<Integer> ids = new ArrayList<>(List.of(1, 2));
        List<Number> numbers = new ArrayList<>(List.of(3.5));
        List<Object> objects = new ArrayList<>();

        printAll(ids);
        printAll(numbers);

        appendIds(ids);
        appendIds(numbers);
        appendIds(objects);

        System.out.println("ids = " + ids);
        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
    }
}
~~~

Compile and run:

~~~bash
javac PecsBasicsDemo.java
java PecsBasicsDemo
~~~

Exact stdout:

~~~text
1 2 
3.5 
ids = [1, 2, 10, 20]
numbers = [3.5, 10, 20]
objects = [10, 20]
~~~

The trailing spaces on the first two lines come from `System.out.print(n + " ")`. If you do not want trailing spaces, you can switch the loop to `StringJoiner`; that is unrelated to PECS.

The example uses the same `List<Integer> ids` as a **producer** in `printAll(ids)` and as a **consumer** in `appendIds(ids)`. The role depends on **what the function does**, not on any fixed nature of the `ids` object.

The `numbers` list already holds a `Double`, yet still receives additional `Integer` values via `appendIds`. This is safe for `List<Number>` and illustrates why `? super Integer` is useful.

## 5. Combining Both Directions to Transfer Elements from Source to Destination

The quintessential use case of PECS is **transferring/copying elements with a specific subtype into a collection that accepts a broader type**.

General signature:

~~~java
static <T> void appendAll(
        Collection<? extends T> source,
        Collection<? super T> destination) {
    for (T item : source) {
        destination.add(item);
    }
}
~~~

This is **a method that needs to be placed in a class with `import java.util.Collection;`**. `T` represents the type we want to pass across the source–destination boundary.

- `Collection<? extends T>` guarantees that every element read from `source` can be used as `T`.
- `Collection<? super T>` guarantees that every element of type `T` can be added to `destination`.
- The method does not need to know the concrete subtype of the source or the concrete supertype of the destination.
- `T` can be inferred by the compiler at each call site or explicitly specified by the caller with the `<T>` syntax.

### Runnable Program: Transferring `Integer` and `Double` into `Number`

Create **`PecsTransferDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class PecsTransferDemo {
    private static <T> void appendAll(
            Collection<? extends T> source,
            Collection<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> integers = List.of(1, 2);
        List<Double> doubles = List.of(3.5, 4.5);
        List<Number> numbers = new ArrayList<>();
        List<Object> objects = new ArrayList<>();

        appendAll(integers, numbers);
        appendAll(doubles, numbers);
        appendAll(numbers, objects);

        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("integers = " + integers);
        System.out.println("doubles = " + doubles);
    }
}
~~~

Compile and run:

~~~bash
javac PecsTransferDemo.java
java PecsTransferDemo
~~~

Stdout:

~~~text
numbers = [1, 2, 3.5, 4.5]
objects = [1, 2, 3.5, 4.5]
integers = [1, 2]
doubles = [3.5, 4.5]
~~~

The first and second calls feed `Integer`/`Double` elements into `List<Number>` without ever assigning `List<Integer>` directly to `List<Number>`. The third call feeds `Number` elements into `List<Object>`. Each destination collection has its own structure; adding elements does not mutate the source collection.

**Note on aliasing:** the demonstration assumes source and destination are distinct. When source and destination point to **the same mutable collection**, a loop adding to the collection while iterating over it may throw `ConcurrentModificationException` or exhibit implementation-dependent behavior. If an API needs to support this case, it can take a temporary snapshot before adding, for example `destination.addAll(new ArrayList<T>(source))` inside the generic method; the contract should be defined clearly rather than implicitly assumed always safe.

## 6. Example with Domain Inheritance Relationships

PECS is not limited to numeric types. Suppose `Dog` and `Cat` are subtypes of `Animal`. We want to take animals from a species-specific list and add them into a combined list.

Create **`PecsAnimalsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class PecsAnimalsDemo {
    static class Animal {
        private final String name;

        Animal(String name) {
            this.name = name;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    static class Dog extends Animal {
        Dog(String name) {
            super(name);
        }
    }

    static class Cat extends Animal {
        Cat(String name) {
            super(name);
        }
    }

    private static <T> void copyInto(
            List<? extends T> source,
            List<? super T> destination) {
        destination.addAll(source);
    }

    public static void main(String[] args) {
        List<Dog> dogs = List.of(new Dog("Bim"), new Dog("Milo"));
        List<Cat> cats = List.of(new Cat("Miu"));
        List<Animal> animals = new ArrayList<>();
        List<Object> everything = new ArrayList<>();

        PecsAnimalsDemo.<Animal>copyInto(dogs, animals);
        PecsAnimalsDemo.<Animal>copyInto(cats, animals);
        PecsAnimalsDemo.<Animal>copyInto(animals, everything);

        System.out.println("animals = " + animals);
        System.out.println("everything = " + everything);
    }
}
~~~

Run:

~~~bash
javac PecsAnimalsDemo.java
java PecsAnimalsDemo
~~~

Exact stdout:

~~~text
animals = [Bim, Milo, Miu]
everything = [Bim, Milo, Miu]
~~~

In the calls above, we explicitly choose `T = Animal`:

- `List<Dog>` and `List<Cat>` match the source parameter `List<? extends Animal>`.
- `List<Animal>` and `List<Object>` match the destination parameter `List<? super Animal>`.
- The `copyInto` method uses `List.addAll(Collection<? extends E>)` to add elements from the source without altering the type of the original list.
- The destination collections hold **references to the same Animal objects** copied from the source; they do not automatically make deep copies of each object.

If someone wanted to pass `List<Dog>` as **the destination for arbitrary `Animal` values**, the compiler must reject it: a list of dogs must not promise to accept a `Cat`. That is the very type-safety boundary PECS preserves.

## 7. PECS Appears Right in the Java Standard Library

The rule is not just a mnemonic trick. Many Java Collections Framework signatures apply wildcards in both directions.

### 7.1. `Collection.addAll(Collection<? extends E>)`

Suppose you have `Collection<Number> destination`. The `addAll` method needs to **read** elements from the argument and add them to the destination collection, so the source parameter has the form `Collection<? extends E>`:

~~~java
List<Number> numbers = new ArrayList<>();
List<Integer> integers = List.of(1, 2);

numbers.addAll(integers); // Valid.
numbers.add(3.5);
System.out.println(numbers); // [1, 2, 3.5]
~~~

This is an **illustrative snippet that needs to be placed in a class with `import java.util.*;`**. `numbers` has `E = Number`, so the source `Collection<? extends Number>` can be `List<Integer>`.

### 7.2. `Collections.addAll(Collection<? super T>, T...)`

The utility method `Collections.addAll` adds multiple values of type `T` into a destination collection. Because that collection **consumes** values of type `T`, it uses `Collection<? super T>`:

~~~java
Collection<Number> numbers = new ArrayList<>();
Collections.addAll(numbers, 1, 2, 3);
System.out.println(numbers); // [1, 2, 3]
~~~

This is an **illustrative snippet that needs `import java.util.*`**. The `T...` part is a varargs parameter of type `T`; in the example, `Integer` values are inserted into a `Collection<Number>`.

### 7.3. `Collections.copy`: A Consumer Populated by Index

The signature of `Collections.copy` also has a `List<? extends T>` source and a `List<? super T>` destination, except **the destination comes first**:

~~~java
// Standard API signature for reference, not a method to redeclare:
static <T> void copy(List<? super T> dest, List<? extends T> src)
~~~

The source supplies `T`; the destination receives `T` via **`set` operations at existing positions**. Therefore `Collections.copy` does not append elements, and `dest.size()` must be at least `src.size()`; the destination must also support overwriting. If the goal is to append, use `destination.addAll(source)`. Size and mutability conditions are runtime contracts, distinct from PECS type guarantees.

### 7.4. `Comparator<? super T>`: A Non-Collection Consumer

A `Comparator<T>` **takes two `T` values** to invoke `compare`, so `List<Integer>.sort(...)` can accept a `Comparator<Number>` via `Comparator<? super Integer>`. No elements are stored in the comparator: “consumer” here means it **takes values of type `T` as input**.

These two API examples connect PECS to the standard library; the lesson on reading the signatures of `Collections.copy`, `addAll`, and `Comparator` goes deeper into overloads, output, compiler warnings, and runtime exceptions.


## 8. When PECS Should Not Be Applied Mechanically

PECS is a principle for designing **API signatures**; it does not mean every generic parameter must be a wildcard.

### 8.1. When Both Reading and Writing the Exact Same Type `T`

~~~java
static <T> void replaceFirst(List<T> list, T replacement) {
    if (!list.isEmpty()) {
        T previous = list.set(0, replacement);
        System.out.println("old = " + previous);
    }
}
~~~

This is an **illustrative method that needs to be placed in a class with `import java.util.List;`**. `List<T>` links the type of the element read out with the type of the new value written in. Using `List<? extends T>` would block `set` with an arbitrary `T` value; using `List<? super T>` would prevent reading the element out as `T` as written.

Thus, if an API genuinely **both reads and writes under a single specific type contract**, `List<T>` may be more appropriate.

### 8.2. When the Element Type Does Not Need to Be Known

A method that only prints the list size or checks whether it is empty can use `List<?>`:

~~~java
static boolean hasItems(List<?> values) {
    return !values.isEmpty();
}
~~~

This is an illustrative method that needs `import java.util.List`. It accepts any list and does not require a specific type bound `T`. Using `List<? extends Object>` in ordinary cases has nearly the same meaning as `List<?>`, with no clear benefit over the shorter form.

### 8.3. Be Careful When `T` Is Inferred by the Compiler

Look at:

~~~java
static <T> void show(List<T> input) {
    System.out.println(input.size());
}
~~~

This generic method can accept `List<Integer>` and `List<String>` in turn at **separate call sites**, because `T` can be inferred differently. Therefore one should not make the absolute claim that “a `List<T>` signature can never accept different types.”

The distinction to keep in mind:

- When `T` **is already fixed as `Number`**, `List<T>` is only directly compatible with `List<Number>`, whereas `List<? extends T>` accepts `List<Integer>`, `List<Double>`, and so on.
- When `T` is a type parameter **inferred on each call**, `List<T>` can still be used with different type arguments, provided the constraints of the entire call fit.
- Wildcards are especially useful when a method needs to **accept a subtype source and a supertype destination related through the same `T`**.

Do not replace every `List<T>` with `List<? extends T>` merely for the appearance of “flexibility”; look at the actual operations.

## 9. Limitations on Mutability and `null`

`? extends T` is often described as a **read-only view**, but that phrasing is only accurate if understood as “you cannot arbitrarily write a new value of a concrete type.”

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2));
List<? extends Number> source = numbers;

source.remove(0); // Type-valid.
source.clear();    // Type-valid.
source.add(null);  // Type-valid; the actual collection may reject it.
~~~

This is an **illustrative snippet that needs `import java.util.*`**. There is no requirement to supply a `Number` or `Integer` to perform `remove`/`clear`, so the compiler allows them. For a structurally unmodifiable list like `List.of(1, 2)`, mutating operations may throw `UnsupportedOperationException`.

`? super T` also **does not guarantee that the actual collection is modifiable**:

~~~java
List<Integer> fixed = List.of(1, 2);
List<? super Integer> sink = fixed;
// sink.add(3); // Compiles, but throws UnsupportedOperationException at runtime.
~~~

This snippet is illustrative; the call line is commented out to prevent the program from failing. Java Generics controls **data types**; mutability, `null` policy, deduplication, and element ordering are additional properties of the implementation.

Another detail: `? super T` allows adding values of **`T` and subtypes of `T`**, not adding every supertype of `T`. With `? super Integer`, adding an `Integer` is valid, whereas adding a `Number` with a wider static type is not guaranteed.

## 10. Common PECS Misconceptions

**Misconception 1: “`extends` only accepts `T` itself.”** False. `List<? extends Number>` accepts both `List<Integer>` and `List<Double>` because those are sources whose elements are subtypes of `Number`.

**Misconception 2: “`super` accepts a list of any subtype.”** False. `List<? super Integer>` accepts type argument `Integer` and its supertypes, not `List<Double>` and not `List<Dog>` unless `Dog` is a supertype of `Integer`.

**Misconception 3: “If you can read as `T`, you can add `T`.”** False for `? extends T`. The compiler does not know what the actual concrete subtype is; writing a general `T` could violate the source's contract.

**Misconception 4: “If you can add `T`, reading must yield `T`.”** False for `? super T`. The destination collection could be a `List<Object>` holding existing elements that are not `T`; reading through the wildcard only guarantees `Object`.

**Misconception 5: “`extends` and `super` turn `List<A>` into `List<B>`.”** False. Wildcards provide a view with assignments and operations proven safe; they do not convert data, copy the list, or alter the object's type argument.

**Misconception 6: “Using an unchecked cast solves it.”** Unsafe. Casting a `List<Integer>` to `List<Number>` through a raw type or wildcard and then adding a `Double` can cause heap pollution and a `ClassCastException` when reading as `Integer`. Use wildcards according to their role or create a new collection if it needs to hold broader types.

**Misconception 7: “`super` always allows adding and `extends` can never mutate.”** This confuses **type checking** with **runtime mutability**. An unmodifiable collection can still be a type-compatible argument for `? super T`; `? extends T` can still call `clear` on a collection that allows modification.

**Misconception 8: “`Collections.copy` automatically grows the destination.”** False. It overwrites elements at existing positions; it does not append automatically. Use `addAll` when you want to increase the number of elements.

## 11. Type-Checking Self-Test Exercises

Suppose the following variables are declared inside a method with `import java.util.*;`:

~~~java
List<Integer> integers = new ArrayList<>(List.of(1, 2));
List<Double> doubles = new ArrayList<>(List.of(1.5, 2.5));
List<Number> numbers = new ArrayList<>();
List<Object> objects = new ArrayList<>();

List<? extends Number> producer = integers;
List<? super Integer> consumer = numbers;
~~~

Consider **each statement independently**:

| Expression | Compiles? | Why? |
| --- | --- | --- |
| `producer = doubles;` | Yes | `Double` is a subtype of `Number` |
| `producer = objects;` | No | `Object` is not a subtype of `Number` |
| `Number n = producer.get(0);` | Yes | Producer guarantees reading as `Number` |
| `producer.add(42);` | No | Actual subtype of producer is unknown |
| `producer.add(null);` | Yes | `null` is reference-type compatible; runtime may reject it |
| `consumer = objects;` | Yes | `Object` is a supertype of `Integer` |
| `consumer = doubles;` | No | `Double` is not a supertype of `Integer` |
| `consumer.add(42);` | Yes | Consumer accepts `Integer` |
| `consumer.add(2.5);` | No | Destination might be `List<Integer>` |
| `Object x = consumer.get(0);` | Yes | Consumer only guarantees `Object` when reading |
| `Integer x = consumer.get(0);` | No | Collection might be `List<Object>` |
| `numbers.addAll(integers);` | Yes | `addAll` reads a `<? extends Number>` source |
| `Collections.copy(numbers, integers);` | Yes | Signature follows PECS; destination must have enough elements at runtime |

The call `Collections.copy(numbers, integers)` while **`numbers` is empty** compiles, but throws `IndexOutOfBoundsException` at runtime. The questions “does it compile?” and “does it succeed at runtime?” must be kept distinct.

Answer one more for yourself: can a method taking `Collection<? super Animal>` add `Dog` and `Cat`? **Yes**, as long as `Dog` and `Cat` extend `Animal`. Can it read every element as `Animal`? **No**, because the destination could be a `Collection<Object>` holding other kinds of objects.

## 12. Data-Flow Signature Design Process

When writing a generic API, you can follow four steps:

1. **Determine whether `T` values flow out of the parameter or into the parameter.** If the parameter mainly supplies values, it is a producer. If the parameter mainly receives values, it is a consumer.
2. **Choose the appropriate wildcard bound.** For a producer that needs to be read as `T`, use `? extends T`. For a consumer that needs to accept `T`, use `? super T`.
3. **Check the actual operations in the method body.** If you have `extends` and need to add an arbitrary `T`, or have `super` and need to read reliably as `T`, the current signature does not match the need; adjust the contract, use `List<T>`, or use a generic method that ties the types together.
4. **Check runtime requirements.** Is the collection modifiable, does it accept `null`, does it preserve order or deduplicate, can source and destination be the same object? These concerns fall outside PECS guarantees.

Summary cheat sheet:

| Role of parameter in function | Typical type | What is guaranteed |
| --- | --- | --- |
| Read elements as `T` | `Collection<? extends T>` | Every element retrieved is `T` or a subtype of `T` |
| Write `T` elements | `Collection<? super T>` | The collection accepts `T` values and its subtypes |
| Need both reading and writing the same type `T` | `Collection<T>`, `List<T>` | One concrete type argument ties the operations together |
| Do not need to know element type | `Collection<?>` | Can iterate elements as `Object` and use type-independent operations |

**PECS = Producer Extends, Consumer Super.** Sources use `extends` to pass `T` out safely; destinations use `super` to receive `T` safely. Both wildcard directions expand API reusability while preserving Java's generic invariance.
