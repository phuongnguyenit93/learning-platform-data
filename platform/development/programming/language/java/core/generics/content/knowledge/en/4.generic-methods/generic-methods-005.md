# `static` Generic Methods and Utility Functions in Java

In Java, many operations do not need to be tied to a specific object: getting the first element of a list, swapping two elements, creating a key–value pair, returning the input data, or finding the maximum value. These operations are well suited to **`static` generic methods** (*static generic methods*): methods that can apply to many data types while the compiler still verifies type relationships between arguments and results.

This lesson progresses from `static <T>` syntax to how to design a utility class, how Java infers type arguments at each call site, declaring multiple type parameters, type bounds (`bound`), collection rules, and mistakes involving `static`, raw types, and type erasure.

## 1. What Is a `static` Generic Method?

Consider a method that returns the exact object passed to it:

```java
public static <T> T identity(T value) {
    return value;
}
```

How to read it from left to right:

- `public`: the method can be called from other classes.
- `static`: the method belongs to the **declaring class**, so it can be called via the class name without creating an object holding the method.
- `<T>`: **declares the method's own type parameter**. This is the marker that makes the method generic.
- `T` before `identity`: the method's return type.
- `T value`: the value parameter's type. The same symbol `T` establishes the compile-time contract "returns the same type it received".

If the method is placed inside the `GenericUtils` class, it can be called as:

```java
// Illustrative snippet inside another method:
String language = GenericUtils.identity("Java");
Integer version = GenericUtils.identity(17);
```

The compiler infers `T = String` in the first call and `T = Integer` in the second call. These are **two usages of the same method**; there is no need to define separate `identity(String)` and `identity(Integer)` methods.

An ordinary `static` method without `<T>`:

```java
public static String upper(String value) {
    return value.toUpperCase();
}
```

This method only accepts `String`, so it is not a generic method.

The main difference lies in **declaring the method's type parameter** and how that parameter links positions in the signature, rather than in the `static` keyword itself.

## 2. Exact Position of `<T>` in a Method Declaration

General syntax:

```java
[modifiers] <TypeParameters> ReturnType methodName(parameters) {
    // body
}
```

This is a **syntax template**, not a standalone compilable Java snippet. For a concrete `static` method:

```java
static <T> T first(T a, T b) {
    return a;
}
```

Other forms are also valid:

```java
static <T> void consume(T item) {
    System.out.println(item);
}

static <K, V> String describe(K key, V value) {
    return key + "=" + value;
}

static <N extends Number> double twice(N value) {
    return value.doubleValue() * 2;
}
```

All three are **illustrative methods** and must be placed inside the body of a valid class or record.

| Syntax | Meaning |
|---|---|
| `static <T> T first(T a, T b)` | One type parameter `T`; result and both arguments are linked via `T`. |
| `static <T> void consume(T item)` | Method is still generic even though it returns `void`. |
| `static <K,V> String describe(K key,V value)` | Two independent type parameters, result is `String`. |
| `static <N extends Number> double twice(N value)` | `N` must satisfy the type bound `Number`. |

You cannot omit `<T>` and write `static T identity(T x)` if `T` has not been validly declared in scope. Having the letter `T` in a parameter or return type does not automatically declare a type parameter.

In the declaration, the `<T>` list must come **before the return type** and after modifiers such as `public static`. For a generic method, `<T>` belongs to that method, unlike `class Box<T>` which declares a type parameter for the entire class.

## 3. Utility Classes: Why Use `final` and a `private` Constructor?

A class grouping shared `static` helper functions can take the form:

```java
public final class GenericUtils {
    private GenericUtils() {
        throw new AssertionError("Utility class");
    }

    public static <T> T identity(T value) {
        return value;
    }
}
```

This is a complete class, though it currently has only one method. The design decisions:

1. `public final class`: the class is a container for utility functions, not intended for extension via inheritance.
2. `private` constructor: external code cannot instantiate `GenericUtils` just to call `static` functions; throwing an error inside the constructor reinforces the intent against unintended calls from inside the class itself.
3. `static` method: called via `GenericUtils.identity(...)`, without needing `new GenericUtils()`.
4. Type parameter `<T>`: scoped to each method. You **do not need** to declare `class GenericUtils<T>` to write generic utility methods.

This is a **design convention**, not a mandatory language rule. A stateful application class can still contain `static` generic methods. Only use the utility-class pattern when the operations genuinely do not depend on object state.

## 4. A Complete Java 17 Utility Set

Create the file **`GenericUtils.java`**:

```java
import java.util.List;
import java.util.Map;

public final class GenericUtils {
    private GenericUtils() {
        throw new AssertionError("Utility class");
    }

    // Preserves the type relationship between input and result.
    public static <T> T identity(T value) {
        return value;
    }

    // Creates a single-element list; null elements are not allowed.
    public static <T> List<T> only(T value) {
        return List.of(value);
    }

    // Accepts a list containing T or a subtype of T; read-only.
    public static <T> T firstOrThrow(List<? extends T> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }
        return items.get(0);
    }

    // Swaps elements in a mutable list.
    public static <T> void swap(List<T> items, int left, int right) {
        T previous = items.get(left);
        items.set(left, items.get(right));
        items.set(right, previous);
    }

    // Compares according to natural order.
    public static <T extends Comparable<? super T>> T maximum(
            List<? extends T> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }

        T best = items.get(0);
        for (int i = 1; i < items.size(); i++) {
            T candidate = items.get(i);
            if (candidate.compareTo(best) > 0) {
                best = candidate;
            }
        }
        return best;
    }

    // Two independent type parameters.
    public static <K, V> Map.Entry<K, V> entry(K key, V value) {
        return Map.entry(key, value);
    }
}
```

This is a **real utility class that compiles on Java 17**. The methods hold no state and do not require creating a `GenericUtils` instance.

### How to Run and Output

Create another file **`GenericUtilsDemo.java`** in the same directory:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class GenericUtilsDemo {
    public static void main(String[] args) {
        String name = GenericUtils.identity("spring");
        Integer count = GenericUtils.identity(7);
        List<String> one = GenericUtils.only("lesson");
        String first = GenericUtils.firstOrThrow(
                List.of("core", "generics"));

        List<String> colors = new ArrayList<>(
                List.of("red", "blue"));
        GenericUtils.swap(colors, 0, 1);

        Integer biggestNumber = GenericUtils.maximum(
                List.of(9, 4, 11));
        String biggestWord = GenericUtils.maximum(
                List.of("Go", "Java", "Kotlin"));

        Map.Entry<String, Integer> version =
                GenericUtils.entry("JDK", 17);

        System.out.println(name.toUpperCase());
        System.out.println(count);
        System.out.println(one);
        System.out.println(first);
        System.out.println(colors);
        System.out.println(biggestNumber);
        System.out.println(biggestWord);
        System.out.println(version.getKey() + "=" + version.getValue());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 GenericUtils.java GenericUtilsDemo.java
java GenericUtilsDemo
```

`stdout`:

```text
SPRING
7
[lesson]
core
[blue, red]
11
Kotlin
JDK=17
```

Because `List.of(...)` returns a list whose structure and elements cannot be modified via `set`, the example creates `new ArrayList<>(...)` before calling `swap`. If you pass `List.of("red", "blue")` directly to `swap`, the compiler still accepts the `List<String>` type, yet the program throws `UnsupportedOperationException` when calling `set`. **Generics check element types; they do not guarantee a collection is mutable.**

The utilities `only` and `entry` use `List.of` and `Map.entry` in the JDK. Those two factories reject `null` arguments and produce unmodifiable objects respectively; if `null` is passed, the call can throw `NullPointerException`. Input preconditions should be documented explicitly in the API rather than assuming generics check them.

## 5. How Does Each Call Infer Type Arguments?

When seeing:

```java
String text = GenericUtils.identity("Java");
Integer number = GenericUtils.identity(42);
```

the compiler analyzes the signature `<T> T identity(T value)` along with the argument type and the **target type** where the result is used. In these two examples, it infers `T` as `String` and `Integer`, respectively.

You can specify the type argument explicitly with a **type witness**:

```java
String text = GenericUtils.<String>identity("Java");
Integer number = GenericUtils.<Integer>identity(42);
```

The `<String>` part is placed **right before the method name**, after the dot following the class name. This syntax differs from `new Box<String>(...)` on a constructor and `new Box<>(...)` using the diamond operator.

An erroneous example:

```java
// Integer broken = GenericUtils.<Integer>identity("Java");
```

This is commented-out erroneous code: if you explicitly force `T = Integer` while still passing a string, the compiler rejects it because `String` is incompatible with parameter `Integer`.

### When Should You Write a Type Witness?

In most cases it is **unnecessary** because Java infers the type. A type witness helps illustrate or disambiguate a call with complex inference context, especially with multiple generic parameters, method overloads, or type bounds. Do not write type witnesses on every call merely to repeat information the compiler already knows.

Example of a value with a wide type:

```java
Object value = "Java";
Object same = GenericUtils.identity(value);
```

At the call site, the **static type** of `value` is `Object`, so the type relationship is inferred as `Object`; the method does not automatically recognize that it is definitely `String` just because the runtime object's class is `String`.

## 6. Distinguishing Class Type Parameters from `static` Method Type Parameters

A generic class has its own type parameter:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T` is tied to **a parameterization of the class**, such as `Box<String>`. A `static` method belongs to the **declaring class**, not specifically to `Box<String>` or `Box<Integer>`. Therefore, inside a generic class, you cannot directly use the class's `T` in a `static` member:

```java
// Illustrates invalid declarations when placed inside class Box<T>:
// private static T shared;
// static T readShared() { return null; }
```

To build a `static` factory method for the box, declare a **dedicated type parameter** for the method:

```java
static <U> Box<U> of(U value) {
    return new Box<>(value);
}
```

Here `<U>` belongs to the `of` method, while `Box<U>` describes the return type. The class does not need to use the same symbol `U`; a name like `TValue` is also valid as long as it is used consistently.

### Runnable Factory Method

Create the file **`StaticFactoryDemo.java`**:

```java
public class StaticFactoryDemo {
    static final class Box<T> {
        private final T value;

        private Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }
    }

    public static void main(String[] args) {
        Box<String> language = Box.of("Java");
        Box<Integer> year = Box.of(2026);

        System.out.println(language.get().toUpperCase());
        System.out.println(year.get() + 1);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 StaticFactoryDemo.java
java StaticFactoryDemo
```

`stdout`:

```text
JAVA
2027
```

The `of` method can create `Box<String>` or `Box<Integer>` from the same definition. This is a classic case of a **generic static factory method**. In library design, a factory method can also validate inputs, return different implementations, or reuse instances when the contract allows; those behaviors must be explicitly implemented and do not come automatically from generics.

## 7. Utility Methods with Multiple Type Parameters

Not every utility only needs `T`. To create a key–value pair:

```java
public static <K, V> Map.Entry<K, V> entry(K key, V value) {
    return Map.entry(key, value);
}
```

`<K, V>` **declares two independent type parameters**. With `GenericUtils.entry("JDK", 17)`:

- `K` corresponds to `String`.
- `V` corresponds to `Integer`.
- The return type is `Map.Entry<String, Integer>`.

Here `Map.Entry` is a nested interface in the `java.util.Map` API, usable as the result object for a key–value pair. The JDK factory `Map.entry(...)` returns an entry that cannot be modified via `setValue` and does not allow `null` keys or values.

If a utility uses one type for both arguments:

```java
public static <T> boolean sameReference(T left, T right) {
    return left == right;
}
```

this is an **illustrative method snippet**, returning a **reference-equality** check rather than content equality like `Objects.equals`. The compiler can infer a common supertype for two arguments of different types; using the same letter `T` does not by itself guarantee the two objects share the same runtime class.

Only introduce multiple type parameters when you need to express **meaningful type relationships**. Generics are unnecessary if a function neither passes through nor uses type information:

```java
public static int countCharacters(String text) {
    return text.length();
}
```

The function above only handles `String`; making it generic brings no natural benefit.

## 8. Type Bounds for Algorithms Requiring Comparability

A method like `identity(T)` requires no specific operations on `T`. However, an algorithm finding the maximum value needs a way to compare. The signature in `GenericUtils`:

```java
public static <T extends Comparable<? super T>> T maximum(
        List<? extends T> items)
```

This is an **illustrative signature**; the method body is already in `GenericUtils.java`.

Components:

1. `<T extends Comparable<? super T>>` is a **bounded type parameter**: type `T` must be comparable against values of type `T` through an appropriate `Comparable` contract.
2. `List<? extends T>` lets the method **read** values compatible with `T`. It does not allow freely adding an arbitrary `T` into the source list.
3. `T maximum(...)` returns a value of type `T` determined by the compiler from the call context.
4. `candidate.compareTo(best) > 0` expresses the natural order provided by the object type itself.

Examples:

```java
Integer largest = GenericUtils.maximum(List.of(3, 8, 5));
String latest = GenericUtils.maximum(
        List.of("Alpha", "Beta", "Gamma"));
```

This snippet belongs inside a method using `GenericUtils.java` above; `java.util.List` must be imported. `largest` is `8`, `latest` is `"Gamma"` by the lexicographical order of `String.compareTo`. If you pass a type of object that does not implement an appropriate `Comparable` relationship, the compiler rejects the call under this signature.

### When There Is No Natural Order

If the data type does not implement `Comparable` or the user wants a different ordering rule, the utility can take a **`Comparator<? super T>`** instead of requiring `T` to have a natural order:

```java
import java.util.Comparator;
import java.util.List;

public final class ComparisonUtils {
    private ComparisonUtils() { }

    public static <T> T maximumBy(
            List<? extends T> items,
            Comparator<? super T> comparator) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }

        T best = items.get(0);
        for (int i = 1; i < items.size(); i++) {
            T candidate = items.get(i);
            if (comparator.compare(candidate, best) > 0) {
                best = candidate;
            }
        }
        return best;
    }
}
```

This is a complete class in **`ComparisonUtils.java`**, independent of the other examples. Example call inside a method after importing `java.util.List` and `java.util.Comparator`:

```java
String longest = ComparisonUtils.maximumBy(
        List.of("A", "Java", "Code"),
        Comparator.comparingInt(String::length));
```

`longest` has the value `"Java"`: both `"Java"` and `"Code"` are 4 characters long, yet the algorithm only replaces `best` when the comparison value is **strictly greater** (not on equality), so the earlier element is retained.

This is still a **static generic utility** with type parameter `<T>`. Using `Comparator` decouples the **algorithm** from the **comparison rule**, fitting reusable utilities.

## 9. Types at Read Sites and Write Sites: Why Utilities Should Think About Wildcards

Consider two different operations:

- `firstOrThrow(List<? extends T>)` only needs to **read** an element and return `T`.
- `swap(List<T>, int, int)` needs to both read and **write back** elements in the same list.

In the first utility, the wildcard `? extends T` expresses a source that only needs to supply values of `T` or a subtype. In the second utility, we use `List<T>` to read and put back values of the exact same type linked to the list.

A method copying elements from source to target can use the familiar principle **PECS: Producer Extends, Consumer Super**:

```java
public static <T> void copyAll(
        List<? extends T> source,
        List<? super T> target) {
    for (T item : source) {
        target.add(item);
    }
}
```

This is an **illustrative method snippet**; it must be declared inside a valid class with `java.util.List` imported. Example:

```java
List<Integer> numbers = List.of(1, 2, 3);
List<Number> output = new ArrayList<>();

copyAll(numbers, output);
System.out.println(output); // [1, 2, 3]
```

The lines above must sit inside a method of the class containing `copyAll`, with `List` and `ArrayList` imported. `source` supplies `Integer`, while `target` accepts `Number`. As for the utility's responsibility, tying the type relationship with `<T>` lets the compiler verify compatibility without requiring callers to cast.

Do not apply wildcards mechanically. If an API requires one exact type `T` in multiple positions, `List<T>` may be clearer; if it only reads or only writes along a subtype hierarchy, wildcards broaden the valid usage range.

## 10. Java Already Has Many Generic Static Utilities

Before reimplementing a utility, check whether the JDK already provides it:

| API | Usage Example | Purpose |
|---|---|---|
| `Collections.emptyList()` | `List<String> xs = Collections.emptyList();` | Empty list with inferred element type; unmodifiable. |
| `Collections.singletonList("x")` | `List<String> xs = Collections.singletonList("x");` | Single-element list, unmodifiable. |
| `List.of("a", "b")` | `List<String> xs = List.of("a", "b");` | Factory creating an unmodifiable list; rejects `null` elements. |
| `Map.entry("k", 1)` | `Map.Entry<String, Integer> e = Map.entry("k", 1);` | Creates an entry with two inferred type arguments. |
| `Comparator.comparingInt(...)` | `Comparator<String> c = Comparator.comparingInt(String::length);` | Creates a comparator from an int key extractor. |
| `Optional.ofNullable(x)` | `Optional<String> o = Optional.ofNullable(x);` | Creates an optional with or without a value, allowing `null` input. |

The calls in the table are **illustrative snippets inside a method**, with the necessary imports from `java.util`. These are JDK factory or utility APIs; many declare their own type parameters so they are inferred at the call site.

Note: `List.of(...)` and `Map.entry(...)` were introduced in Java 9, so they are available in Java 17. Utilities may return **unmodifiable** structures, and not every factory collection supports in-place add/remove/sort. Read the API's mutability contract before using it.

## 11. `static` Generic Methods and Method References

A `static` generic method can also be used via a **method reference** if the context provides a target functional type.

Create the file **`MethodReferenceDemo.java`**:

```java
import java.util.function.Function;

public class MethodReferenceDemo {
    static <T> T identity(T value) {
        return value;
    }

    public static void main(String[] args) {
        Function<String, String> textIdentity =
                MethodReferenceDemo::identity;
        Function<Integer, Integer> numberIdentity =
                MethodReferenceDemo::identity;

        System.out.println(textIdentity.apply("Java"));
        System.out.println(numberIdentity.apply(17) + 1);
    }
}
```

Run:

```bash
javac -encoding UTF-8 MethodReferenceDemo.java
java MethodReferenceDemo
```

`stdout`:

```text
Java
18
```

`Function<String, String>` and `Function<Integer, Integer>` are **two different target types** for the same method reference `MethodReferenceDemo::identity`. The compiler uses the target type to infer the type parameter for the respective usage.

A generic utility is valuable when callers have different data types yet share the same computational rule. However, do not use generics to obscure domain meaning: for instance, a method that genuinely only supports strings is usually clearer with a concrete `String` signature than `<T>` combined with casting.

## 12. Limitations and Common Mistakes

### 12.1. `static` Cannot Use an Instance Class Type Parameter

Invalid:

```java
class Box<T> {
    // static T cached;               // Invalid
    // static T createDefault() { ... } // Invalid
}
```

A `static` method must declare its own type parameter (such as `static <U> Box<U> of(U x)`) or work with concrete types. The reason is not a missing constructor, but that `Box<T>`'s `T` belongs to each parameterized use of the class, whereas a `static` member is not tied to any single parameterization.

### 12.2. Cannot Create Objects with `new T()` or Arrays Directly with `new T[n]`

Because Java uses type erasure, a generic method does not know `T`'s constructor from the type parameter alone:

```java
// Inside a method declaring <T>:
// T object = new T();  // Invalid
// T[] values = new T[3]; // Invalid
```

If you genuinely need to create objects of type `T`, you can accept a factory such as `Supplier<? extends T>` from the caller. Example method:

```java
public static <T> T create(
        java.util.function.Supplier<? extends T> factory) {
    return factory.get();
}
```

The method above needs to be placed inside a class; callers provide a constructor reference or lambda capable of creating the appropriate type. Issues around creating generic arrays usually need to be handled via runtime-checked arrays, collection APIs, or appropriate factories; do not write unchecked array casts merely to silence a compile error.

### 12.3. Signature Collision After Type Erasure

The following two methods **cannot be declared together** in one class:

```java
// Error example, do not place in runnable code:
static <T> void show(T value) { }
static void show(Object value) { }
```

Because unbounded `T` is erased to `Object`, the two JVM signatures collide after *type erasure*. Another example:

```java
// Error example: both erase to List.
static void process(List<String> input) { }
static void process(List<Integer> input) { }
```

The compiler detects a **name clash**. To handle multiple data types, choose non-conflicting API signatures, distinct method names, or an appropriate generic design. You cannot use differing generic type arguments alone as an overloading criterion at runtime.

### 12.4. `List.of(...)` Cannot Be Used with List-Mutating Utilities

```java
// GenericUtils.swap(List.of("A", "B"), 0, 1);
```

The line above is valid in terms of **type relationships**, yet at runtime it throws `UnsupportedOperationException` because the list does not support `set`. To use `swap` in this example, create a mutable list:

```java
List<String> values = new ArrayList<>(List.of("A", "B"));
GenericUtils.swap(values, 0, 1);
```

These two lines need `List` and `ArrayList` imported and run with the `GenericUtils` class defined earlier. Generics guarantee type relationships, not mutability or index validity. If `left` or `right` is out of bounds, `get`/`set` throws `IndexOutOfBoundsException`.

### 12.5. Primitives and `null` Still Require Attention

You cannot use `<int>` as a type argument because primitives are invalid in generics; normally you use `Integer` and Java performs autoboxing/unboxing.

Meanwhile, `identity(null)` can be valid when the compiler can infer an appropriate type, and `identity` returns `null`. Conversely, `only(null)` calls `List.of(null)` and therefore throws `NullPointerException`. Both methods are generic, yet **the implementation and API contract** determine how they handle `null`.

### 12.6. Raw Types and Unsafe Casts

Code using raw `List` or unchecked casts can break element constraints, causing `ClassCastException` on reads. You should compile with appropriate warnings enabled, such as:

```bash
javac -Xlint:rawtypes,unchecked GenericUtils.java GenericUtilsDemo.java
```

This command does not change how the utility runs; it asks the compiler to report unsafe generic operations more clearly if any exist.

## 13. Process for Designing a Generic Static Utility

When writing a function reusable across multiple types, you can follow this order:

1. **Identify a state-independent operation:** e.g., reading the first element, swapping, creating a pair, finding the maximum value.
2. **Determine type relationships in the API:** do input and output share `T`, or should there be two parameters `<K,V>`?
3. **Place `<T>` before the return type:** `static <T> T identity(T value)`. Even if the method returns `void`, still declare `<T>`.
4. **Add bounds when the algorithm genuinely needs them:** `<T extends Comparable<? super T>>` for natural ordering; do not add bounds arbitrarily.
5. **Consider collection read/write direction:** use `? extends T` for a read source and `? super T` for a write target when appropriate.
6. **Put runtime conditions into the contract:** can the list be empty, must it be mutable, must indices be valid, can values be `null`?
7. **Prefer existing JDK APIs:** `Collections`, `List.of`, `Map.entry`, or other utilities before writing duplicates.
8. **Keep signatures simple and check compiler diagnostics:** avoid raw types, unchecked casts, and post-erasure overload collisions.
9. **Use the class name at call sites:** `GenericUtils.swap(...)` makes clear the method belongs to a utility class, aiding search and maintenance.

You do not need to convert every `static` method into a generic one. If a function only handles `String` or `int` by domain logic, a concrete-type signature can be more accurate and easier to understand.

## 14. Self-Check

**Question 1.** In the signature `static <T> T identity(T value)`, why do both `<T>` and `T` appear before the method name?

**Question 2.** Why do `GenericUtils.identity("Java")` and `GenericUtils.identity(42)` use the same method definition yet yield results with different static types?

**Question 3.** Given `class Holder<T>`, why can you not declare `static T value;` yet you can declare `static <U> Holder<U> of(U value)`?

**Question 4.** What is the benefit of the signature `copyAll(List<? extends T> source, List<? super T> target)`?

**Question 5.** Why does `GenericUtils.swap(List.of("a", "b"), 0, 1)` fail at runtime even though Java Generics accept the `List<String>` type?

**Question 6.** Why cannot `static <T> void show(T value)` and `static void show(Object value)` coexist in the same class?

**Answer hints:** (1) `<T>` declares the method's type parameter; `T` before the name is the return type. (2) Java infers `T` separately for each call based on arguments and context. (3) A `static` member does not belong to a specific parameterization of the class; `<U>` is the factory's independent type parameter. (4) It expresses a type relationship allowing copying from a source supplying `T` into a target accepting `T`, even across valid supertype–subtype relationships. (5) `List.of` creates an unmodifiable list; generics do not guarantee `set` support. (6) After type erasure, unbounded `T` erases to `Object`, causing a signature collision.

**Key takeaway:** A `static` generic method combines **an instance-independent function** with **compile-time type-relationship checking**. The `static <T>` syntax lets each call use an appropriate type without creating separate classes or overloads; the quality of a utility lies in a clear type contract, transparent runtime preconditions, and reusability without losing type safety.