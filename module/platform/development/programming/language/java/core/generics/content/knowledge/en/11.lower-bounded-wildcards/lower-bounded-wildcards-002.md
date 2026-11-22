# Accepting a collection of T or a supertype of T with `? super T`

When a method needs to **put values of type `T` into a collection supplied by the caller**, the destination collection does not necessarily have to be declared as exactly `Collection<T>`. It may store elements under a broader type, such as `Number` or `Object` for `Integer`. Java Generics expresses this need with a **lower-bounded wildcard**:

~~~java
Collection<? super Integer> destination;
~~~

The type above accepts collections whose type argument is **`Integer` or a supertype of `Integer`**, such as `Collection<Integer>`, `Collection<Number>`, and `Collection<Object>`. The method can safely add `Integer` to all of those collections.

To understand the rule properly, distinguish between **the element type of the actual collection**, **the static type of the wildcard reference**, and **the direction in which data flows**. Also remember that `Collection` only has `iterator()` to retrieve elements; it does not provide `get(index)` like `List`.

## 1. Why do we need to accept collections broader than a fixed `Collection<T>`?

A `Collection<Integer>` is **not** a `Collection<Number>`, even though `Integer` is a subtype of `Number`. If direct assignment were possible, a method receiving `Collection<Number>` could add a `Double` into a structure that the caller considers to hold only `Integer`.

~~~java
Collection<Integer> integers = new ArrayList<>();
// Collection<Number> wrong = integers; // Rejected by the compiler.

Collection<Number> numbers = new ArrayList<>();
Collection<Object> objects = new ArrayList<>();
numbers.add(10);
objects.add(10);
~~~

Although invariant collection types cannot be interchanged, **both destinations can accept `Integer`**. An API that only needs to insert `Integer` should describe *the capability to accept values*, rather than demanding one exact type argument: `Collection<? super Integer>`. This is the practical reason to use a lower-bounded wildcard with the **`Collection` interface**, not just with `List`.

## 2. What does `? super T` mean?

In `Collection<? super T>`:

- `Collection` is the general collection interface in Java.
- `?` is a wildcard representing a specific **unnamed** type.
- `super T` sets a **lower bound**: that hidden type must be `T` or a **supertype** of `T`.
- Because the actual collection can store `T` under `T` itself or a broader type, adding a `T` value to it is safe.

Example with `T = Integer`:

| Actual collection type | Assignable to `Collection<? super Integer>`? | Reason |
| --- | --- | --- |
| `Collection<Integer>` | Yes | Type argument equals the lower bound |
| `Collection<Number>` | Yes | `Number` is a supertype of `Integer` |
| `Collection<Object>` | Yes | `Object` is a supertype of `Integer` |
| `Collection<Double>` | No | `Double` is not a supertype of `Integer` |
| `Collection<String>` | No | `String` is not a supertype of `Integer` |

Beyond the class inheritance chain `Integer → Number → Object`, a compatible supertype can also be an **interface** implemented by `Integer`, such as `Serializable`. Therefore `Collection<? super Integer>` is not limited to only the three types in the table: the table illustrates the common cases.

It can be understood equivalently at the semantic level:

> “I do not need to know the exact type argument the collection stores, as long as that type argument accepts any `Integer`.”

Note: `? super T` is used in wildcards. Java **does not** allow declaring a type parameter using `<T super Number>`. When a type parameter needs a constraint, the standard syntax is an upper bound, such as `<T extends Number>`; lower bounds are expressed at wildcard positions.

## 3. Java 17+ example: a method adding numbers to three collection types

Create the file **`SuperWildcardDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;

public class SuperWildcardDemo {
    private static void addDefaults(Collection<? super Integer> destination) {
        destination.add(10);
        destination.add(20);
    }

    public static void main(String[] args) {
        Collection<Integer> integers = new ArrayList<>();
        Collection<Number> numbers = new ArrayList<>();
        Collection<Object> objects = new ArrayList<>();

        addDefaults(integers);
        addDefaults(numbers);
        addDefaults(objects);

        Collection<? super Integer> sink = numbers;
        sink.add(30);

        Object first = sink.iterator().next();

        System.out.println("integers = " + integers);
        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("first = " + first);
    }
}
~~~

Compile and run on Java 17 or later:

~~~bash
javac SuperWildcardDemo.java
java SuperWildcardDemo
~~~

Exact stdout:

~~~text
integers = [10, 20]
numbers = [10, 20, 30]
objects = [10, 20]
first = 10
~~~

In this example:

1. `addDefaults` only cares about **writing two `Integer` values into the collection**. It does not need to know the exact type argument of the destination.
2. `Collection<Integer>`, `Collection<Number>`, and `Collection<Object>` are all compatible with `Collection<? super Integer>`.
3. `sink` is a reference to the same object as `numbers`; `sink.add(30)` mutates the `numbers` collection itself.
4. `sink.iterator().next()` only has `Object` as its guaranteed static type. Even though the first element in the example is an `Integer`, the compiler cannot rely on that assumption for every wildcard-compatible collection.
5. The program uses `ArrayList` so element printing order is deterministic; `Collection` in general does not promise iteration order matches insertion order.

The most important point is that the signature `Collection<? super Integer>` **broadens the accepted destination types** without losing type checking for added elements.

## 4. Type of values read through `Collection<? super T>`

A consumer only promises to **accept `T`**, not that every existing element is of type `T`. For example, a `Collection<Object>` might contain a `String` before being passed through a `Collection<? super Integer>` reference:

~~~java
Collection<Object> original = new ArrayList<>();
original.add("existing");
Collection<? super Integer> sink = original;
sink.add(7);

Object first = sink.iterator().next(); // "existing"
// Integer wrong = sink.iterator().next(); // Does not compile.
~~~

Use `iterator().next()`, **not `get(0)`**, because `Collection` does not define indexed access. The lower bound only allows `add(Integer)`; when iterating, the general safe type of `Collection<E>` is `Object`. If you need to read values back as `Integer`, you must verify each specific value or choose a differently typed source. Formal analysis of capture conversion and generic declarations with narrower bounds belongs to a separate topic on **type limits when reading**.

## 5. Choosing a `Collection` signature based on data flow

| Requirement in method (assuming `T=Number`) | Suitable parameter | Safe element read | Values that can be added type-wise |
| --- | --- | --- | --- |
| Accept only the exact collection holding `Number` | `Collection<Number>` | `Number` | `Number` |
| Read `Number` from multiple subtype collections | `Collection<? extends Number>` | `Number` | Cannot arbitrarily add non-null values |
| Add `Number` into a collection of `Number` or a supertype | `Collection<? super Number>` | `Object` | `Number` and subtypes |
| Do not care about element type | `Collection<?>` | `Object` | Cannot arbitrarily add non-null values |

`? extends` favors **sources**, `? super` favors **destinations**. With `Collection`, reading is done via `iterator()` or a for-each loop; if `get(i)`/`set(i,...)` are needed, switch to `List`. Wildcard rules only guarantee **static typing**; `add` can fail on an unmodifiable collection, or `Set.add` can return `false` when the element already exists.

Do not change `Collection<? super T>` to `Collection<Object>`: a `Collection<Object>` variable **does not** directly accept `Collection<Integer>`, even though both can consume `Integer` values supplied by the method.

## 6. Applying when `T` is a type parameter of a generic method

A method can accept any `T` and add into a destination of type `T` or a supertype of `T`:

~~~java
static <T> void addTwo(Collection<? super T> destination, T a, T b) {
    destination.add(a);
    destination.add(b);
}
~~~

This is **a method that needs to be placed inside a class and import `java.util.Collection`**. Declaring `<T>` lets the compiler infer the type from all arguments in **each call**.

Example when `T` is chosen as `Integer`:

~~~java
Collection<Number> numbers = new ArrayList<>();
Collection<Object> objects = new ArrayList<>();

addTwo(numbers, 1, 2); // Valid.
addTwo(objects, 3, 4); // Valid.
~~~

This is **a call snippet that needs to be placed in a class and import `java.util.*`**. In each call, `T` can be inferred as `Integer`, while the destination collection stores elements as `Number` or `Object`.

To see the constraint clearly, you can specify the type argument explicitly:

~~~java
MyUtils.<Integer>addTwo(numbers, 1, 2); // Valid.
MyUtils.<Integer>addTwo(objects, 3, 4); // Valid.
~~~

This is illustrative notation: assuming `addTwo` is `static` in class `MyUtils`. With `T = Integer`, `Collection<? super T>` requires the destination to have a type argument of `Integer` or one of its supertypes.

### Subtle point: do not fix `T` when the compiler needs to infer it

If `T` is a type parameter of a **method**, the compiler can choose the appropriate type for each invocation. If `T` is a type parameter of a **class** or is already explicitly fixed to a concrete type, arguments must conform to the chosen type.

For instance:

~~~java
class IntegerAppender {
    void append(Collection<? super Integer> destination) {
        destination.add(1);
    }
}
~~~

This is an **illustrative class**, requiring `import java.util.Collection`. The `append` method fixes the lower bound to `Integer`. It accepts `Collection<Integer>`, `Collection<Number>`, or `Collection<Object>`, but not `Collection<Double>`. Generic type naming and how `T` is inferred do not by themselves remove subtype constraints.

## 7. Example with custom classes and interfaces

`super` does not apply only to the three classes `Integer`, `Number`, and `Object`. Suppose a domain model has `Animal` and `Dog`, where `Dog` is a subtype of `Animal`. A collection storing `Animal` or `Object` can both hold `Dog`.

Create the file **`AnimalDestinationDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;

public class AnimalDestinationDemo {
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

    static void addDogs(Collection<? super Dog> destination) {
        destination.add(new Dog("Bim"));
        destination.add(new Dog("Milo"));
    }

    public static void main(String[] args) {
        Collection<Dog> dogs = new ArrayList<>();
        Collection<Animal> animals = new ArrayList<>();
        Collection<Object> objects = new ArrayList<>();

        addDogs(dogs);
        addDogs(animals);
        addDogs(objects);

        System.out.println("dogs = " + dogs);
        System.out.println("animals = " + animals);
        System.out.println("objects = " + objects);
    }
}
~~~

Run:

~~~bash
javac AnimalDestinationDemo.java
java AnimalDestinationDemo
~~~

Exact stdout:

~~~text
dogs = [Bim, Milo]
animals = [Bim, Milo]
objects = [Bim, Milo]
~~~

Explanation:

- `Collection<Dog>` accepts `Dog` instances directly.
- `Collection<Animal>` accepts `Dog` because `Dog` extends `Animal`.
- `Collection<Object>` accepts `Dog` because every `Dog` object is an `Object`.
- There are no unchecked casts. Each collection keeps its originally declared type argument.
- Each `addDogs` call creates two new `Dog` objects in the corresponding collection; the three collections do not share a list structure.

If there is a subtype `Poodle extends Dog`, an expression creating a `Poodle` can also be inserted through `Collection<? super Dog>` because every `Poodle` is a `Dog`. However, an arbitrary `Animal` object that is not a `Dog` cannot be inserted, because the destination might actually be a `Collection<Dog>`.

## 8. Copying from a subtype collection into a supertype collection

A familiar requirement is **reading data from a source and writing to a destination**. For example, the source has `Integer` while the destination stores `Number`; or the source has `Dog` while the destination stores `Animal`.

You can declare the method:

~~~java
static <T> void appendAll(Collection<? extends T> source,
                          Collection<? super T> destination) {
    for (T element : source) {
        destination.add(element);
    }
}
~~~

This is **a method that needs to be placed inside a class and import `java.util.Collection`**.

- `source` is a **producer**: its elements have type `T` or a subtype of `T`; reading as `T` is valid.
- `destination` is a **consumer**: that collection has type argument `T` or a supertype of `T`; adding a `T` element is valid.

Create the program **`CollectionTransferDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class CollectionTransferDemo {
    private static <T> void appendAll(
            Collection<? extends T> source,
            Collection<? super T> destination) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        Collection<Integer> small = List.of(1, 2);
        Collection<Double> decimals = List.of(3.5, 4.5);

        Collection<Number> numbers = new ArrayList<>();
        Collection<Object> objects = new ArrayList<>();

        appendAll(small, numbers);
        appendAll(decimals, numbers);
        appendAll(numbers, objects);

        System.out.println("numbers = " + numbers);
        System.out.println("objects = " + objects);
        System.out.println("small = " + small);
    }
}
~~~

Compile and run:

~~~bash
javac CollectionTransferDemo.java
java CollectionTransferDemo
~~~

Stdout:

~~~text
numbers = [1, 2, 3.5, 4.5]
objects = [1, 2, 3.5, 4.5]
small = [1, 2]
~~~

The example proves that the `super` wildcard **puts elements into the destination via valid operations**. It does not convert `Collection<Integer>` into `Collection<Number>` and requires no casts.

The standard library already supports this pattern. For instance, `Collection.addAll(Collection<? extends E>)` allows adding elements from a source with a compatible subtype; and the utility `Collections.addAll(Collection<? super T>, T...)` allows adding multiple objects of type `T` into a destination with type argument `T` or its supertype.

For `List`, `Collections.copy(List<? super T> dest, List<? extends T> src)` also demonstrates PECS, but differs from `appendAll`: it **overwrites existing positions** and requires `dest` to already be large enough. Do not use `Collections.copy` as a way to automatically append to the end of a list.

## 9. Allowed operations and risks when reading

Consider a variable:

~~~java
Collection<? super Integer> destination = new ArrayList<Number>();
~~~

The following operations are valid generically:

~~~java
destination.add(10);
destination.add(Integer.valueOf(20));
destination.addAll(List.of(30, 40));
destination.add(null); // Compiles, though the actual destination may forbid null.

boolean hasTen = destination.contains(10);
int size = destination.size();

for (Object item : destination) {
    System.out.println(item);
}

destination.remove(10);
destination.clear();
~~~

This is **an illustrative snippet requiring `import java.util.*` and placement inside a class**. `Collection.addAll` accepts a source with a compatible element type; `contains` and `remove(Object)` do not require knowing the collection's element type. Therefore the compiler allows them.

Conversely:

~~~java
// destination.add(2.5); // ERROR: Double is not Integer.
// destination.add("x"); // ERROR: String is not Integer.

// Integer first = destination.iterator().next(); // ERROR.
// Number first = destination.iterator().next();  // ERROR.
Object first = destination.iterator().next(); // Valid if non-empty.
~~~

`iterator().next()` can throw `NoSuchElementException` if the collection is empty; the comment “Valid” above refers only to **compilation and return type**, not a promise that the collection has elements. When safe handling is needed, check `iterator.hasNext()` first.

Moreover, `? super T` **is not a guarantee that the collection is mutable**. For example, `List.of(1, 2)` has type `List<Integer>` and can be assigned to `Collection<? super Integer>`, but adding an element will throw `UnsupportedOperationException`. Ability to add **by type** and mutability of the **actual object** are two independent things.

### Why might a read result not be `Integer`?

The program below runs:

~~~java
import java.util.ArrayList;
import java.util.Collection;

public class SuperReadDemo {
    public static void main(String[] args) {
        Collection<Object> objects = new ArrayList<>();
        objects.add("text");
        objects.add(99);

        Collection<? super Integer> sink = objects;
        sink.add(100);

        for (Object item : sink) {
            System.out.println(item);
        }
    }
}
~~~

Running `javac SuperReadDemo.java` and `java SuperReadDemo` produces stdout:

~~~text
text
99
100
~~~

The `sink` reference is allowed to add `Integer` into `Collection<Object>`, but previously existing elements can still be `String`. Therefore, reading through `sink` as `Integer` would be an unguaranteed promise.

## 10. Compared with `List<? super T>`: same type relationship, different container API

This lesson uses `Collection<? super T>` to talk about **collections in general**. If an API needs positional access by index, the same wildcard can be applied to `List<? super T>`:

~~~java
List<? super Integer> destination = new ArrayList<Number>();
destination.add(1);
destination.add(2);

Object first = destination.get(0); // Valid.
// Integer n = destination.get(0); // COMPILE-TIME ERROR.
~~~

This is **an illustrative snippet requiring `import java.util.*` and placement inside a class**. The difference between `Collection` and `List` lies in the interface methods: `List` has `get(index)`, `set(index, element)`; `Collection` does not have `get(index)`.

Do not confuse wildcard types with implementation names:

- `Collection<? super Integer>` **can point to `ArrayList<Integer>`, `HashSet<Number>`, or another collection** if the type argument matches.
- `List<? super Integer>` can only point to objects implementing `List` with a matching type argument, not directly to a `HashSet`.

Need to add elements without caring about order/index: prefer a `Collection<? super T>` parameter so the API accepts more implementations. Need `List`-specific functionality: use `List<? super T>`. A `Set`-type collection may reject adding an element because it already exists, so `add` returns `false`; this is part of the `Collection` contract, not a wildcard error.

## 11. Common mistakes to avoid

### Mistake 1. Using `Collection<T>` when only adding `T` is needed

~~~java
static void addAnswer(Collection<Integer> destination) {
    destination.add(42);
}
~~~

This is an **illustrative method**. If the caller has a `Collection<Number>`, the method rejects the input even though that collection can store `Integer`. If the method only adds integers, a better signature is:

~~~java
static void addAnswer(Collection<? super Integer> destination) {
    destination.add(42);
}
~~~

### Mistake 2. Confusing `super` with allowing every element to be read as `T`

`Collection<? super Integer>` can reference a `Collection<Object>`. Old elements of this collection can be any `Object`, so a loop `for (Integer x : collection)` **does not compile**. Use `Object` for reading, or redesign the API if stronger type information is truly needed.

### Mistake 3. Thinking `? super T` allows adding any supertype of `T`

When `T = Integer`, `Double` and `Number` are **not** guaranteed to be addable to `Collection<? super Integer>`. The destination might be `Collection<Integer>`. Only adding values compatible with `Integer` (including `null` if the collection supports it) is valid.

### Mistake 4. Confusing wildcard flexibility with generic subtype assignment

~~~java
Collection<Integer> xs = new ArrayList<>();
Collection<? super Integer> allowed = xs; // Yes.
// Collection<Number> wrong = xs;          // No.
~~~

`allowed` is only **a view using a wildcard**. It does not change the type argument of `xs` to `Number`.

### Mistake 5. Unchecked casts to achieve the same goal

~~~java
Collection<Integer> integers = new ArrayList<>();
@SuppressWarnings("unchecked")
Collection<Number> forged = (Collection<Number>) (Collection<?>) integers;
forged.add(2.5); // Can pollute Integer-typed data.
~~~

This is **warning-worthy code, not a solution**. Unchecked casts can cause a collection to hold elements violating its contract and trigger `ClassCastException` on future reads. In an API that only needs to insert integers, `Collection<? super Integer>` expresses the real requirement without needing casts.

### Mistake 6. Using `? extends T` for a parameter that only acts as a destination

~~~java
static void badSink(Collection<? extends Number> values) {
    // values.add(123); // COMPILE-TIME ERROR.
}
~~~

In this case `extends` is designed for a **read source**, and does not guarantee that `Integer` can be added. If you only need to insert `Integer`, choose `Collection<? super Integer>`; if you need to insert any `Number`, choose `Collection<? super Number>`.

### Mistake 7. Ignoring constraints of the actual container

A call `destination.add(1)` may **compile** yet still fail because the collection is unmodifiable, rejects `null`, or enforces uniqueness rules. Generics ensure **type compatibility**, not that every mutation call will succeed. Read the implementation's documentation when runtime behavior matters.

## 12. Self-check

Suppose the following variables are declared inside a method, with `import java.util.*;`:

~~~java
Collection<Integer> ints = new ArrayList<>();
Collection<Number> numbers = new ArrayList<>();
Collection<Object> objects = new ArrayList<>();
Collection<Double> doubles = new ArrayList<>();
Collection<? super Integer> sink = numbers;
~~~

Predict whether the following statements **compile**:

| Standalone expression | Compiles? | Explanation |
| --- | --- | --- |
| `Collection<? super Integer> a = ints;` | Yes | Type argument is `Integer` |
| `Collection<? super Integer> a = numbers;` | Yes | `Number` is a supertype of `Integer` |
| `Collection<? super Integer> a = objects;` | Yes | `Object` is a supertype of `Integer` |
| `Collection<? super Integer> a = doubles;` | No | `Double` is not a supertype of `Integer` |
| `sink.add(123);` | Yes | Integer literal autoboxes to `Integer` |
| `sink.add(2.5);` | No | `Double` is not guaranteed to be compatible |
| `sink.add((Number) 123);` | No | Static type of the expression is `Number`, which might not be `Integer` |
| `Object x = sink.iterator().next();` | Yes | Guaranteed type when reading is `Object` |
| `Integer x = sink.iterator().next();` | No | Actual type argument of the collection is unknown |
| `sink.addAll(List.of(1, 2));` | Yes | Source collection supplies `Integer` |
| `sink.size();` | Yes | Does not depend on element type |
| `sink.clear();` | Yes | Valid type-wise; runtime depends on mutability |

The statements in the table are **independent scenarios** and must not be combined into a single compiled method because some rows are intentionally ill-typed and the variable name `a` is repeated.

A conceptual question: if `Collection<Object> objects` already holds the string `"hello"`, and is then used as `Collection<? super Integer>`, why is `add(7)` allowed while `Integer i = iterator().next()` is forbidden? Because **adding `Integer`** is safe for every destination with a compatible supertype, whereas **reading every element as `Integer`** is wrong for old values.

## 13. Applying the rule in API design

Choose the generic parameter according to the specific operational need:

1. **Only need to add `T` values into the caller's collection:** choose `Collection<? super T>`. This is the main case of this lesson.
2. **Only need to read values as `T` from the caller's collection:** choose `Collection<? extends T>`.
3. **Both read and write the exact same type `T`, needing to maintain type relationships across multiple parameters/return values:** consider `Collection<T>` or a generic method with an explicit type parameter.
4. **Do not care about element type and do not need to add specific elements:** `Collection<?>` is suitable for counting, checking status, or iterating as `Object`.
5. **Need to preserve order and operate by index:** choose `List` instead of `Collection`, while keeping the `? super T` principle when it is a consuming destination.

**Conclusion:** `Collection<? super T>` means “I can accept a collection of `T` or a supertype of `T` to **safely write `T` values**”. This is the **Consumer Super** piece of the PECS principle. In return, you must not assume retrieved elements have type `T`; the general guarantee is `Object`. Choosing the right signature makes the API flexible for callers while preserving Java Generics' type-checking barrier.