# Generics Combined with Classes, Interfaces, Methods, and Collections in Java

Generics allow classes, interfaces, and methods to accept **data types as parameters**. Because of this, the same structure or algorithm can serve many types while still being checked for correctness by the compiler. In Java Core, generics are especially important when designing `List<E>`, `Set<E>`, `Map<K, V>`, data wrapper classes, repository interfaces, and collection-processing methods.

This lesson uses syntax compatible with **Java 17+**. Short snippets illustrate individual rules; at the end is a standalone `GenericsGuide.java` program that compiles and runs.

## 1. Foundational Thinking: Type Parameters Instead of `Object`

A class using only `Object` can hold many kinds of values, but callers must cast and easily encounter `ClassCastException` at runtime:

```java
// Illustrates the legacy style without generics.
class ObjectBox {
    Object value;
    ObjectBox(Object value) { this.value = value; }
    Object get() { return value; }
}

// String name = (String) new ObjectBox(123).get();
// Compiles, but casting Integer to String fails at runtime.
```

With class `Box<T>`, `T` stands for the type chosen at the usage site:

```java
// Illustrative snippet, placed in an appropriate Java file.
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

Box<String> title = new Box<>("Java");
String text = title.get();           // No cast needed.
Box<Integer> count = new Box<>(12);
Integer number = count.get();
// Box<String> wrong = new Box<>(12); // Compile-time error immediately.
```

In `Box<String>`, parameter `T` is substituted with `String` in how the compiler checks call sites. Checking happens **at compile time**; it is not a promise that Java generates a separate new runtime class for every `T`.

Common naming conventions: `T` (type), `E` (element), `K` (key), `V` (value), `R` (result), `S` (source). These letters are type parameter names, not keywords. Use clearer descriptive names if multiple parameters are needed at once.

**Type parameters must be reference types**: use `List<Integer>` instead of `List<int>`, `Box<Boolean>` instead of `Box<boolean>`. Autoboxing can convert `int` to `Integer` when adding elements.

## 2. Generics on Classes: One or Multiple Type Parameters

Declaring `class ClassName<T>` puts `T` in scope for the class's instance members. When a relationship between two types is needed, declare multiple parameters:

```java
// Illustrates an immutable class with two type parameters.
final class Pair<L, R> {
    private final L left;
    private final R right;

    Pair(L left, R right) {
        this.left = left;
        this.right = right;
    }

    L left() { return left; }
    R right() { return right; }
}

Pair<String, Integer> score = new Pair<>("Lan", 9);
String student = score.left();
int point = score.right();
```

`L` and `R` can be the same or different. The diamond operator `<>` in `new Pair<>(...)` lets the compiler infer types from context. Since Java 16, a pair of values can be expressed more concisely with `record Pair<L, R>(L left, R right) {}` when it fits an immutable data design.

A generic class can inherit from or extend a generic structure in two ways:

```java
// Passes the type parameter from the superclass down to the subclass.
class NamedBox<T> extends BoxBase<T> {
    NamedBox(T item) { super(item); }
}

// Fixes the superclass's type argument.
class StringBox extends BoxBase<String> {
    StringBox(String item) { super(item); }
}

class BoxBase<T> {
    private final T item;
    BoxBase(T item) { this.item = item; }
    T get() { return item; }
}
```

In `NamedBox<Integer>`, `BoxBase<T>`'s type corresponds to `Integer`; in `StringBox`, `String` is fixed. A generic class cannot use the class's own type parameter in a `static` field or a `static` method unless that method declares its own type parameter: `T` depends on each parameterized usage of the class, whereas `static` members belong to the class as a whole.

### Constraining Type Parameters with `extends`

If an algorithm needs operations available only on a certain kind of object, place an **upper bound**:

```java
// Illustrates a generic method with a bound.
static <T extends Number> double total(java.util.Collection<T> items) {
    double sum = 0;
    for (T item : items) {
        sum += item.doubleValue();
    }
    return sum;
}
```

`T extends Number` accepts `Integer`, `Long`, `Double`, etc., and allows calling `doubleValue()`. Even though `Number` is a class, the keyword is still `extends`; for interfaces it also uses `extends`, such as `<T extends Comparable<T>>`.

Multiple bounds can be specified: `<T extends Number & Comparable<T>>`. If there is a class bound, the class must come before the interfaces. A bound does not turn `List<Integer>` into `List<Number>`; that is a variance issue, covered separately in Section 6.

## 3. Generics on Interfaces: Typed API Contracts

Generic interfaces describe operations independently of key and data types while preserving the link between inputs and results:

```java
// The snippets in this block illustrate the same API.
interface Repository<ID, E> {
    void save(ID id, E entity);
    java.util.Optional<E> findById(ID id);
}

final class InMemoryRepository<ID, E> implements Repository<ID, E> {
    private final java.util.Map<ID, E> data = new java.util.HashMap<>();

    @Override
    public void save(ID id, E entity) {
        data.put(id, entity);
    }

    @Override
    public java.util.Optional<E> findById(ID id) {
        return java.util.Optional.ofNullable(data.get(id));
    }
}

Repository<Long, String> repo = new InMemoryRepository<>();
repo.save(1L, "Lan");
String found = repo.findById(1L).orElse("Không tìm thấy");
// repo.save("sai kiểu khóa", "Lan"); // Compile error.
```

`ID` ensures the keys used in `save` and `findById` have the same type; `E` ensures the stored value and the value inside `Optional<E>` have the same type. `Optional<E>` represents the possible absence of a result, helping the API avoid returning `null` directly.

A class can also fix types right when implementing, such as `UserRepository implements Repository<Long, User>`. In that case, the method signatures must match `Long` and `User`.

Standard interfaces such as `Comparable<T>`, `Comparator<T>`, `Iterable<T>`, `Function<T, R>`, and `Predicate<T>` all apply the same principle: declare the type relationship at the design site so usage sites are checked consistently.

## 4. Generics on Methods: Per-Call Type Scope

A generic method declares `<T>` **before the return type**, regardless of whether its enclosing class is generic:

```java
// Illustrates methods in a utility class.
static <T> T first(java.util.List<T> items) {
    if (items.isEmpty()) {
        throw new java.util.NoSuchElementException("empty list");
    }
    return items.get(0);
}

static <A, B> java.util.Map.Entry<A, B> entry(A key, B value) {
    return new java.util.AbstractMap.SimpleImmutableEntry<>(key, value);
}
```

When calling `first(List<String>)`, the return type is inferred as `String`; when calling `first(List<Integer>)`, the return type is inferred as `Integer`. A `static` method can certainly be generic because it **declares its own** `<T>`.

```java
// Illustrates calls inside a Java method/program.
String a = first(java.util.List.of("A", "B"));
Integer b = first(java.util.List.of(3, 4));
java.util.Map.Entry<String, Integer> grade = entry("Lan", 9);
```

The compiler usually infers type parameters, though they can be specified explicitly when needed: `Collections.<String>emptyList()`. Note the distinction:

- `class Box<T>`: `T` belongs to the class, fixed per `Box<String>` or `Box<Integer>`.
- `<T> T first(List<T> xs)`: `T` belongs solely to the method and is inferred for each call.
- `static <T> ...`: valid; `static T get()` inside `class Box<T>` is invalid because `T` belongs to the class's instance context.

When elements need to be compared in natural order, the bound `<T extends Comparable<? super T>>` is more useful than casting every element to `Object`:

```java
// Illustrates a generic method.
static <T extends Comparable<? super T>> T maximum(
        java.util.List<? extends T> values) {
    if (values.isEmpty()) {
        throw new java.util.NoSuchElementException("empty list");
    }
    T best = values.get(0);
    for (T value : values) {
        if (value.compareTo(best) > 0) {
            best = value;
        }
    }
    return best;
}
```

`Comparable<? super T>` also handles the case where an object of type `T` implements comparability on a superclass of `T`. In real applications, prefer the library method `Collections.max(...)` when it meets the requirement.

## 5. Generics with the Java Collections Framework

Collections are where learners encounter generics most frequently. Type parameters make data constraints part of the API:

| Structure | Typical Declaration | Characteristics |
| --- | --- | --- |
| `List<E>` | `List<String>` | Positional order, allows duplicate elements; indexed access. |
| `Set<E>` | `Set<Long>` | Contains no duplicate elements per `equals`/`hashCode` or the implementation's comparator. |
| `Queue<E>` | `Queue<Task>` | Queue model; retrieval order depends on the implementation. |
| `Collection<E>` | `Collection<Number>` | General interface for a group of elements; no general indexed access. |
| `Map<K, V>` | `Map<String, Integer>` | Maps keys to values; **`Map` does not inherit from `Collection`**. |

Example of working with typed collections:

```java
// Illustrates calls assuming java.util.* is imported.
List<String> names = new ArrayList<>();
names.add("Lan");
names.add("Minh");
// names.add(42); // Compile error: element must be String.
String firstName = names.get(0);

Set<String> tags = new LinkedHashSet<>(List.of("java", "core", "java"));
// LinkedHashSet preserves insertion order; printed output: [java, core].

Map<String, List<Integer>> scores = new HashMap<>();
scores.computeIfAbsent("Lan", key -> new ArrayList<>()).add(9);
scores.computeIfAbsent("Lan", key -> new ArrayList<>()).add(8);
List<Integer> lanScores = scores.get("Lan"); // [9, 8]
```

`Map<String, List<Integer>>` is **nested generics**: keys must be `String`, and each value is a `List` of `Integer`. `computeIfAbsent` returns the existing value or creates a new value when the key is absent (or mapped to `null`), after which `add` can be called on the corresponding list.

Several properties of factories and implementations directly affect how examples are written:

- `List.of(...)`, `Set.of(...)`, and `Map.of(...)` create **unmodifiable** collections; these factories do not accept `null` elements (and `Set.of` does not accept duplicates).
- `new ArrayList<>(List.of(...))` creates a modifiable list. `Arrays.asList(...)` creates a fixed-size list: elements can be replaced with `set`, but `add/remove` cannot change its size.
- `HashMap` and `HashSet` do not guarantee iteration order; `LinkedHashMap` and `LinkedHashSet` preserve insertion order; `TreeMap` and `TreeSet` sort according to natural order or an appropriate comparator.
- `Map.get(key)` returns `null` when there is no mapping, though it can also return `null` if the map allows `null` values. Use `containsKey` when you need to tell them apart.

When you only need interface behavior, declare the left-hand side as `List<E>`, `Set<E>`, or `Map<K,V>`, and choose the implementation class on the right-hand side. This keeps the API easy to change.

## 6. Invariance, Wildcards, and the PECS Principle

Java generics are **invariant**: even though `Integer extends Number`, `List<Integer>` is **not** a `List<Number>`:

```java
List<Integer> integers = new ArrayList<>();
// List<Number> numbers = integers; // Compile error.
```

If that assignment were allowed, `numbers.add(3.14)` would insert a `Double` into a list meant to hold only `Integer`. Instead of relaxing the rule unsafely, Java provides wildcards:

| Parameter Type | Safely Readable As | Directly Addable |
| --- | --- | --- |
| `List<T>` | `T` | Values of type `T` |
| `List<? extends Number>` | `Number` | Cannot add concrete `Number` values; `null` can be added |
| `List<? super Integer>` | `Object` | `Integer` and subclasses of `Integer` (in practice `Integer` is final); `null` |
| `List<?>` | `Object` | Cannot add any non-`null` element |

### `? extends T`: Source to Read From

```java
// Illustrates a method reading from various numeric collections.
static double sumNumbers(List<? extends Number> source) {
    double result = 0;
    for (Number number : source) {
        result += number.doubleValue();
    }
    return result;
}

// sumNumbers(List.of(1, 2, 3));     // List<Integer>
// sumNumbers(List.of(1.5, 2.5));     // List<Double>
```

`source` can be `List<Integer>`, `List<Double>`, or `List<Number>`. You cannot call `source.add(1)` because the list's actual element type might be `Double`. Even `Number` is not specific enough to determine what type may be added.

### `? super T`: Destination to Write To

```java
// Illustrates a writing method.
static void addDefaults(List<? super Integer> target) {
    target.add(1);
    target.add(2);
}

// addDefaults(new ArrayList<Integer>());
// addDefaults(new ArrayList<Number>());
// addDefaults(new ArrayList<Object>());
```

A `List<? super Integer>` destination accepts `Integer`, but when retrieving elements out of it, you can only assume `Object` because the list might have been declared as `List<Object>`.

**PECS = Producer Extends, Consumer Super**: a parameter that supplies objects of type `T` should consider `? extends T`; a parameter that receives objects of type `T` should consider `? super T`.

An example combining both sides:

```java
// Illustrates a copy method that does not modify the source.
static <T> void appendAll(
        List<? extends T> source,
        List<? super T> target) {
    for (T item : source) {
        target.add(item);
    }
}

// List<Integer> src = List.of(1, 2);
// List<Number> dst = new ArrayList<>();
// appendAll(src, dst); // dst contains [1, 2].
```

If two parameters must share **the same type relationship** or a method must **return that exact type**, use a named type parameter `<T>` like `appendAll` and `first`. If you only read/print data without linking types across positions, `List<?>` is often simpler:

```java
static void printAll(List<?> values) {
    for (Object item : values) {
        System.out.println(item);
    }
}
```

Wildcards are not a mechanism for “allowing every operation”. They describe what an API knows about a type, so the compiler restricts read and write operations for safety.

## 7. Collections and Functions Taking/Returning Generics: Practical API Design

Suppose you need to transform a list of `S` into a list of `R`. A flexible signature often combines method type parameters with wildcards on `Function`:

```java
// Illustrative method; import java.util.* and java.util.function.*.
static <S, R> List<R> mapEach(
        Collection<? extends S> source,
        Function<? super S, ? extends R> mapper) {
    List<R> result = new ArrayList<>();
    for (S element : source) {
        result.add(mapper.apply(element));
    }
    return result;
}

// List<Integer> lengths = mapEach(List.of("a", "java"), String::length);
// lengths equals [1, 4].
```

The source produces `S`, the mapping function can accept `S` or a supertype of `S`, and the function result is `R` or a subtype of `R`. This is why `Function<? super S, ? extends R>` appears in many standard APIs.

When returning collections from public APIs, consider:

1. If callers only need to read, return an interface type like `List<E>` and clarify whether it is modifiable; for instance, `List.copyOf(source)` creates an unmodifiable copy and does not accept `null`.
2. If a method only iterates over elements, accept `Iterable<? extends T>` or `Collection<? extends T>` depending on the operations actually needed; avoid forcing everything to be `ArrayList<T>`.
3. If key/value relationships are needed, use `Map<K,V>` and do not replace it with `Map<Object,Object>`.
4. If sorting is needed, consider `Comparator<? super T>` to accept comparators of supertypes, or the bound `Comparable<? super T>` for natural ordering.
5. Choose meaningful type parameters, and avoid declaring `<T>` if it does not appear in inputs/outputs or express any type relationship.

Transformations with Streams also preserve generics throughout:

```java
// Illustrative snippet assuming java.util.* is imported.
List<String> words = List.of("A", "Java");
List<Integer> lengths = words.stream()
        .map(String::length)
        .toList(); // [1, 4], unmodifiable List from Stream.toList().
```

Here `Stream<String>` goes through `map` to become `Stream<Integer>`. `toList()` (Java 16+) creates an unmodifiable list; if you need a modifiable copy, use `collect(Collectors.toCollection(ArrayList::new))`.

## 8. Type Erasure: How Do Generics Exist at Runtime?

Java implements most of generics using **type erasure** (erasing type argument information in ordinary runtime representations). The compiler checks types, inserts necessary casts, and maps type parameters to appropriate bounds; for instance, an unbounded `T` usually erases to `Object`, while `T extends Number` usually erases to `Number`. The compiler may generate **bridge methods** to preserve polymorphism after erasure.

Important consequences:

- `new ArrayList<String>().getClass() == new ArrayList<Integer>().getClass()` is `true`: both parameterizations use the same runtime class `ArrayList`.
- You cannot check `value instanceof List<String>`; you can check `value instanceof List<?>` because the `String` argument cannot be verified at runtime.
- You cannot write `new T()`, `new T[10]`, or directly create generic arrays `new List<String>[10]` in ordinary cases. If you need to create `T` instances, pass an appropriate `Supplier<T>` factory or `Class<T>`.
- You cannot overload methods that differ only by type arguments erasing to the same type; for example, two methods `process(List<String>)` and `process(List<Integer>)` with the same name will collide after erasure.
- A `static` field cannot have type `T` from the class's type parameter; each parameterization does not get its own copy of `static` fields.

**Erasure does not mean every trace of generics disappears from metadata.** For example, reflection can read generic declaration types on fields, methods, and superclasses via APIs such as `getGenericType()` or `getGenericSuperclass()`; however, the specific type argument of an ordinary `new ArrayList<String>()` does not become a runtime property that can be checked with `instanceof`.

### Raw Types and Unchecked Warnings

```java
// Illustrates legacy code, should not be put into new APIs.
List raw = new ArrayList();
raw.add("Java");
raw.add(42);
List<String> names = raw; // Unchecked conversion warning.
String second = names.get(1); // ClassCastException at runtime.
```

A raw type (`List` instead of `List<String>`) bypasses part of generic checking and is normally needed only when interacting with legacy code. **`List<?>` differs from raw `List`**: `List<?>` still maintains type-safe constraints and prevents adding arbitrary objects. Do not use `@SuppressWarnings("unchecked")` to hide design flaws; use it only when you have verifiable justification and limit the warning scope.

## 9. Complete Example: Class + Interface + Method + Collection

Create a file named **`GenericsGuide.java`** containing the exact program below. The `static` nested classes here are used to provide a single standalone runnable file and clearly show how the parts connect.

```java
import java.util.*;
import java.util.function.Function;

public class GenericsGuide {
    static final class Box<T> {
        private final T value;

        Box(T value) { this.value = value; }

        T get() { return value; }

        <R> Box<R> map(Function<? super T, ? extends R> f) {
            return new Box<>(f.apply(value));
        }
    }

    interface Repository<ID, E> {
        void save(ID id, E value);
        Optional<E> findById(ID id);
    }

    static final class MemoryRepository<ID, E> implements Repository<ID, E> {
        private final Map<ID, E> data = new LinkedHashMap<>();

        @Override
        public void save(ID id, E value) {
            data.put(id, value);
        }

        @Override
        public Optional<E> findById(ID id) {
            return Optional.ofNullable(data.get(id));
        }
    }

    static <T> T first(List<T> values) {
        if (values.isEmpty()) {
            throw new NoSuchElementException("empty list");
        }
        return values.get(0);
    }

    static <T extends Number> double sum(Collection<T> values) {
        double result = 0;
        for (T value : values) {
            result += value.doubleValue();
        }
        return result;
    }

    static <T> void appendAll(List<? extends T> source, List<? super T> target) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        Box<String> word = new Box<>("Java");
        Box<Integer> length = word.map(String::length);
        System.out.println("Box: " + word.get() + " -> " + length.get());

        Repository<Long, String> users = new MemoryRepository<>();
        users.save(10L, "Lan");
        System.out.println("Repository: " + users.findById(10L).orElse("unknown"));

        List<Integer> scores = List.of(2, 3, 5);
        System.out.println("First: " + first(scores));
        System.out.println("Sum: " + sum(scores));
        List<Number> numbers = new ArrayList<>();
        appendAll(scores, numbers);
        System.out.println("Copied: " + numbers);

        Set<String> tags = new LinkedHashSet<>(List.of("java", "generics", "java"));
        System.out.println("Set: " + tags);
        Map<String, List<Integer>> grades = new LinkedHashMap<>();
        grades.put("Lan", List.of(8, 9));
        System.out.println("Map: " + grades.get("Lan"));
    }
}
```

Compile and run in the directory containing the file:

```bash
javac GenericsGuide.java
java GenericsGuide
```

**Exact** stdout output (verified with Java 21, syntax valid from Java 17):

```text
Box: Java -> 4
Repository: Lan
First: 2
Sum: 10.0
Copied: [2, 3, 5]
Set: [java, generics]
Map: [8, 9]
```

Explaining the relationships in the program:

- `Box<T>` is a generic class: `Box<String>` holds a word; generic method `<R> map(...)` returns `Box<Integer>` when given `String::length`.
- `Repository<ID,E>` is a generic interface; `MemoryRepository<ID,E>` implements the contract using `Map<ID,E>`; `Optional<E>` preserves the type of the found data.
- `first` is a generic method with no bound; `sum` requires `T extends Number` because it uses `doubleValue()`.
- `appendAll` uses `? extends T` for the `List<Integer>` source and `? super T` for the `List<Number>` destination. This applies PECS for safe copying.
- `List<Integer>`, `Set<String>`, and `Map<String,List<Integer>>` demonstrate type parameters across storing, reading, iterating, and mapping operations.

Note: `Set` prints in a deterministic order in this example because it uses `LinkedHashSet`; `List.of` is an unmodifiable list, yet it can still be read and copied normally.

## 10. Common Mistakes and How to Fix Them

| Symptom | Cause | How to Fix |
| --- | --- | --- |
| `List<Number> x = new ArrayList<Integer>()` errors | Generics are invariant | Use `List<? extends Number>` if reading only, or declare a consistent element type. |
| Cannot call `add(1)` on `List<? extends Number>` | Specific subtype of the list is unknown | Use `List<? super Integer>` as a write target, or `List<Number>` when multiple number types need to be stored. |
| `new T()` does not compile | Type erasure; no way to construct `T` | Pass a `Supplier<T>`, factory, or appropriate constructor. |
| `List<int>` is invalid | Generics require reference types | Use `List<Integer>`. |
| `List raw` works but triggers an unchecked warning | Type parameter checking was bypassed | Change to `List<E>`, or `List<?>` if `E` is unknown. |
| Casting `(List<String>)` from `List<?>` | Does not prove elements are actually `String` | Check/convert each element intentionally; do not blindly cast the collection. |
| Calling `add` on `List.of(...)` throws `UnsupportedOperationException` | The factory returns an unmodifiable list | Create `new ArrayList<>(List.of(...))` if modification is needed. |
| `static T value` inside `class Box<T>` errors | The class's type parameter does not belong to `static` context | Use a concrete type or let a `static` method declare its own `<T>`. |
| Adding the wrong-type element to a raw list causes errors later | Loss of compile-time checks, causing heap pollution | Avoid raw types and unchecked casts; fix the API at the source. |

Do not use wildcards everywhere just because they look flexible. If a `List<T>` genuinely needs both reading and adding `T`, the exact type `List<T>` usually expresses the contract more clearly. On public methods, place bounds where needed and let the rest be inferred naturally.

## 11. Practice Exercises and Self-Check

**Exercise 1 — Class:** Write `Result<T>` containing `T data` and `String message`. Create `Result<String>` and `Result<Integer>`. Self-check question: why does a getter returning `T` avoid casting?

**Exercise 2 — Interface:** Design `Cache<K,V>` with `put(K,V)` and `Optional<V> get(K)`. Implement it with `HashMap<K,V>`; create `Cache<String, Long>` and try passing an `Integer` key to observe the compile error.

**Exercise 3 — Method + collection:** Write `static <T> List<T> reversed(List<? extends T> source)` that creates a new list in reverse order. Test with `List<String>` and `List<Integer>`. Do not modify the source; distinguish how this behaves compared to `Collections.reverse`, which mutates the passed-in list.

**Exercise 4 — Choosing signatures:** When transferring data from `List<Integer>` into a `List<Number>`, should each side accept `List<Integer>`, `List<Number>`, `List<? extends Number>`, or `List<? super Integer>`? Explain in terms of read and write operations, then compare your solution with the signature of `appendAll`.

To evaluate yourself, a sound solution should demonstrate: **type parameters flowing through classes/interfaces/methods**, **compile-time type safety**, **collection invariance**, and **choosing `extends`/`super` according to data direction**. This is the foundation for reading generic APIs in the Java standard library and designing reusable collection APIs.