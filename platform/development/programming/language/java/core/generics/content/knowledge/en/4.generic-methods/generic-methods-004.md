# Type Relationships Between Multiple Arguments and Return Value in Java Generic Methods

Generic methods do more than let you write a single method that works across multiple data types. Their greater value is **expressing type relationships between parameters and the result right in the signature**, so the Java compiler can verify every call. A method `static <T> T first(T a, T b)` shares the type variable `T` across both arguments and the result. A method `static <A, B, R> R combine(A a, B b, BiFunction<A, B, R> f)` allows the two inputs to have different types while still binding the result type to the transformation.

This lesson shows how to read, design, and verify those relationships using Java 17+: **shared type variables, multiple independent type variables, type inference, target typing, bounded type parameters, wildcards, collections, method references, runtime limitations, and common mistakes**. The focus is on the **generic method** signature and how a call constrains the compiler to find a valid type assignment.

## 1. What Does a Generic Method Actually "Link"?

Declaration structure:

```java
static <T> T method(T first, T second)
```

This is an illustrative signature without a body. Split it into four parts:

- `static`: method modifier.
- `<T>`: declares a **type parameter** named `T` for the method itself.
- `T` in the return type position: the result is treated as having type `T` at the call site.
- `T first, T second`: two parameters referencing the same type variable `T`.

This creates compile-time type constraints. It does **not** promise that the two arguments share the same runtime class, does not promise which argument the result equals, and does not make `T` exist as a specialized class in the JVM.

Compare with:

```java
static Object selectObject(Object first, Object second)
```

The `Object` signature only guarantees a return type of `Object`; callers do not retain a relationship to an inferred type variable. Therefore:

```java
String a = select("Lan", "Mai");      // With <T> T select(T,T), valid.
Object b = selectObject("Lan", "Mai"); // Valid.
// String c = selectObject("Lan", "Mai"); // Error without a cast.
```

These lines illustrate usage, assuming `select`/`selectObject` have been defined with those signatures.

### Generic Methods Differ from Generic Classes

`class Box<T>` has its `T` tied to usages like `Box<String>` or `Box<Integer>`. By contrast, `static <T> T identity(T x)` declares `T` for **each invocation**. The same method can be called sequentially with `String` and then `Integer`. You do not need `Box<T>` or a generic class to write a generic method.

## 2. Runnable Example: One `T` Linking Two Arguments and the Result

Create `ChooseDemo.java`:

```java
public class ChooseDemo {
    static <T> T first(T left, T right) {
        return left;
    }

    static <T> T last(T left, T right) {
        return right;
    }

    public static void main(String[] args) {
        String name = first("Lan", "Mai");
        Integer count = last(10, 20);

        System.out.println(name);
        System.out.println(count);
    }
}
```

Compile and run:

```bash
javac ChooseDemo.java
java ChooseDemo
```

`stdout`:

```text
Lan
20
```

Trace the types of the first call:

1. Read the `<T>` declaration: the method's type parameter.
2. Both arguments `"Lan"` and `"Mai"` have type `String`.
3. The target type of the assignment expression is also `String`.
4. `javac` can choose `T = String` to satisfy the constraints.
5. The expression `first(...)` is typed as `String`; no explicit cast is needed.

The call `last(10, 20)` uses two primitive `int`s; boxing and type inference allow the result to be used as `Integer`. No separate "Integer-specialized version of last" is generated as generic specialization.

**Point to distinguish:** because `first`'s body actually executes `return left`, the result equals the value of `left`. The signature `<T> T first(T,T)` by itself only guarantees **the type of the result**, not that the result must equal `left`. A different implementation could return `right` or throw an exception.

## 3. "Same `T`" Does Not Mean Arguments Must Have the Exact Same Runtime Class

A common misconception is thinking `<T> T choose(T a, T b)` only accepts two objects of the exact same class. In reality, **method type inference solves a system of type constraints**; Java can find a common supertype or an appropriate intersection type for the passed expressions.

Example:

```java
static <T> T chooseFirst(T a, T b) {
    return a;
}

Number number = chooseFirst(1, 2.5);
```

This is an illustrative snippet placed inside a class; `1` is boxed to the appropriate type, `2.5` to `Double`. The `Number` type on the left-hand side is a valid target type; the compiler does not require `Integer.class == Double.class`. The actual runtime value of `number` is still the object holding the value `1`.

### When Arguments Differ and There Is No Specific Target Type

Given:

```java
var value = chooseFirst("hello", 42);
```

Do not assume `value` is guaranteed to have type `String` or `Integer`. Type inference may pick a suitable common supertype or intersection type, depending on the invocation's constraints and how types are represented. With `var`, the variable's type is inferred from the initializer expression, not from a generic type argument you pre-specified.

If business logic requires "both arguments must have the exact same runtime class", a signature sharing `T` is **not** a class-identity check. You need clearer domain constraints or proper validation; even a shared `<T>` can be inferred as a supertype of both inputs.

### Limits of Type Inference

Type inference operates on the **static types** of expressions, subtyping rules, method applicability, and the expected target type. It does not inspect string contents, does not know that a `Number` was previously assigned an `Integer` in order to "auto-decide" a specific domain type, and does not iterate through a collection's data to guarantee element homogeneity.

## 4. If You Want Two Independent Arguments, Declare Two Type Variables

The signature:

```java
static <A, B> String describe(A first, B second)
```

allows two parameters to have independent types. `A` and `B` are each declared separately; the concrete return type is `String` and therefore does not depend on the choice of `A`/`B`.

If the result also needs to be parameterized:

```java
static <A, B> Pair<A, B> pair(A first, B second)
```

then the return type **preserves both relationships**. With `pair("Lan", 9)`, the compiler infers `A=String`, `B=Integer`, and the result has type `Pair<String,Integer>`.

### Complete Program: Two Inputs, Two Components in the Result

Create `PairFactoryDemo.java`:

```java
public class PairFactoryDemo {
    record Pair<A, B>(A first, B second) {
    }

    static <A, B> Pair<A, B> pair(A first, B second) {
        return new Pair<>(first, second);
    }

    public static void main(String[] args) {
        Pair<String, Integer> score = pair("Lan", 9);
        Pair<Long, Boolean> status = pair(100L, true);

        System.out.println(score.first());
        System.out.println(score.second() + 1);
        System.out.println(status.first() + ": " + status.second());
    }
}
```

Run:

```bash
javac PairFactoryDemo.java
java PairFactoryDemo
```

`stdout`:

```text
Lan
10
100: true
```

Constraint table:

| Position | Declaration | When Calling `pair("Lan", 9)` |
|---|---|---|
| `A` | Method `<A,B>` | `String` |
| `B` | Method `<A,B>` | `Integer` |
| `A first` | First parameter | Receives `String` |
| `B second` | Second parameter | Receives `Integer` |
| `Pair<A,B>` | Return type | `Pair<String,Integer>` |

The record's `Pair<A,B>` and the static method's `<A,B>` are **two different declaration sites**; the names coincide only by naming convention in the example. In `Pair<A,B>` inside the method, `A`/`B` are type arguments passed to the record, taken from the **method's** type parameters.

## 5. Linking Inputs and Output with Three Type Variables: A, B, R

Many algorithms transform **two inputs into one result**. If the result does not share the same type as either input, declare a dedicated type parameter for the result type.

Foundational signature:

```java
static <A, B, R> R combine(
        A first,
        B second,
        java.util.function.BiFunction<? super A, ? super B, ? extends R> operation)
```

Meaning:

- `A`: type of the first input.
- `B`: type of the second input.
- `R`: type of the result.
- `operation`: a function accepting `A`, `B` values and returning a value compatible with `R`.
- `R combine(...)`: the call result preserves the exact type `R` inferred by the compiler.

Create `CombineDemo.java`:

```java
import java.util.function.BiFunction;

public class CombineDemo {
    static <A, B, R> R combine(
            A first,
            B second,
            BiFunction<? super A, ? super B, ? extends R> operation) {
        return operation.apply(first, second);
    }

    public static void main(String[] args) {
        String label = combine("ID-", 17, (prefix, number) -> prefix + number);
        Integer total = combine(4, 7, Integer::sum);

        System.out.println(label);
        System.out.println(total);
    }
}
```

Compile and run:

```bash
javac CombineDemo.java
java CombineDemo
```

`stdout`:

```text
ID-17
11
```

In the first call, a natural solution is `A=String`, `B=Integer`, `R=String`. In the second call, `A=Integer`, `B=Integer`, `R=Integer`. The same method applies to two different type relationships.

### Why `BiFunction<? super A, ? super B, ? extends R>` Instead of `BiFunction<A,B,R>`?

Both can describe the basic relationship. Wildcards increase flexibility to accept functions with wider parameter types or a narrower return type:

- `? super A`: the function can accept `A` or an appropriate supertype of `A`.
- `? super B`: likewise for the second input.
- `? extends R`: the function produces a value of type `R` or a subtype of `R`.

Choosing wildcards is flexible API design following **consumer super, producer extends**. At a foundational level, first recognize `A,B,R` linking three positions; analyze variance next.

### Is R Completely Independent?

`R` is declared independently yet constrained by the return type of `operation` and the target type of the whole call. If the function returns `String`, you cannot arbitrarily assign the result directly to `Integer` without a valid conversion. Generics do not automatically turn a `String` into an `Integer` just because the caller asks for `R=Integer`.

## 6. Input–Output Relationships in Generic Methods Working with List

Generic methods are very useful when an input container and an output container must preserve a type relationship.

### 6.1. Returning an Element While Preserving the Source Type

```java
static <T> T first(java.util.List<T> source) {
    if (source.isEmpty()) {
        throw new java.util.NoSuchElementException("Empty list");
    }
    return source.get(0);
}
```

This is an illustrative method to place inside a class. With `List<String>`, the return type at the call site is `String`; with `List<Integer>`, it is `Integer`. If you replaced the signature with `Object first(List<?> source)`, callers would only receive `Object` and lose the input–output type link.

### 6.2. Two Lists with the Same T: Adding Values from Source to Destination

A simple version:

```java
static <T> void appendSame(
        java.util.List<T> target,
        java.util.List<T> source) {
    target.addAll(source);
}
```

This signature demands a tighter type relationship than necessary. If the source is `List<Integer>` and the destination is `List<Number>`, the business logic can still add `Integer` into `Number`, yet two `List<T>` parameters sharing one `T` reject those two generic instantiations because `List<Integer>` and `List<Number>` are invariant.

Flexible version:

```java
static <T> void append(
        java.util.List<? super T> target,
        java.util.List<? extends T> source) {
    for (T item : source) {
        target.add(item);
    }
}
```

`source` supplies elements compatible with `T`; `target` receives `T` elements. The same named type parameter `T` **connects two different wildcards**.

Create `AppendDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class AppendDemo {
    static <T> void append(
            List<? super T> target,
            List<? extends T> source) {
        for (T item : source) {
            target.add(item);
        }
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4, 6);
        List<Number> target = new ArrayList<>();
        target.add(1.5);

        append(target, source);
        System.out.println(target);
    }
}
```

Run:

```bash
javac AppendDemo.java
java AppendDemo
```

`stdout`:

```text
[1.5, 2, 4, 6]
```

What matters is the **relationship allowing safe element transfer**, not forcing every element to become the exact same runtime class. In this call, `T=Integer` can be chosen; `List<Integer>` acts as producer and `List<Number>` as consumer. `target` is mutable, while `source` is immutable from `List.of` yet only read from, so it fits.

### 6.3. Input List of Type T, Output List of Type R

When transforming each element, the right relationship is `List<T>` → `List<R>` through a function `T → R`.

Create `MapListDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Function;

public class MapListDemo {
    static <T, R> List<R> map(
            List<? extends T> source,
            Function<? super T, ? extends R> mapper) {
        List<R> result = new ArrayList<>();
        for (T item : source) {
            result.add(mapper.apply(item));
        }
        return result;
    }

    public static void main(String[] args) {
        List<Integer> numbers = List.of(3, 5, 8);
        List<String> labels = map(numbers, n -> "n=" + n);
        List<Integer> lengths = map(List.of("Java", "API"), String::length);

        System.out.println(labels);
        System.out.println(lengths);
    }
}
```

Run:

```bash
javac MapListDemo.java
java MapListDemo
```

`stdout`:

```text
[n=3, n=5, n=8]
[4, 3]
```

What the signature expresses:

| Symbol | Where Declared | Constrained Positions |
|---|---|---|
| `T` | Method's `<T,R>` | Element read from `source`; input parameter of `mapper` |
| `R` | Method's `<T,R>` | Result of `mapper`; element of returned `List<R>` |
| `? extends T` | Wildcard used in List | Allows source to have an element type compatible with `T` |
| `? super T` | Wildcard used in Function | Allows mapper to handle a `T` |
| `? extends R` | Wildcard used in Function | Allows mapper to produce a subtype of `R` |

A way to ask yourself: "If the caller passes `List<Integer>` and the mapper produces `String`, does my return type preserve `List<String>`?" With `List<R>`, yes. If you declared `List<Object>`, the type relationship information is lost.

## 7. Relating Multiple Arguments to a Return Value Using a Record

Sometimes you want to keep both input values plus the computed result. Each part can have its own type; a composite record lets you express that relationship clearly.

Create `EvaluationDemo.java`:

```java
import java.util.function.BiFunction;

public class EvaluationDemo {
    record Evaluation<A, B, R>(A first, B second, R result) {
    }

    static <A, B, R> Evaluation<A, B, R> evaluate(
            A first,
            B second,
            BiFunction<? super A, ? super B, ? extends R> function) {
        return new Evaluation<>(first, second, function.apply(first, second));
    }

    public static void main(String[] args) {
        Evaluation<String, Integer, String> e =
                evaluate("item-", 5, (s, n) -> s + n);

        System.out.println(e.first());
        System.out.println(e.second());
        System.out.println(e.result());
    }
}
```

Run:

```bash
javac EvaluationDemo.java
java EvaluationDemo
```

`stdout`:

```text
item-
5
item-5
```

`Evaluation<A,B,R>` **preserves all three relationships** between the input arguments and the result. Distinguish `<A,B,R>` in the method declaration from `<A,B,R>` in the record declaration: they are declared in separate scopes; the method uses its own type variables as type arguments when constructing `Evaluation`.

The advantage of the `Evaluation<A,B,R>` signature over `Object[]` or `Map<String,Object>` is that callers see the exact type of each component via `first()`, `second()`, `result()` without guessing and casting.

## 8. Bounded Type Parameters: Linking Types and Capabilities

A type parameter can be bounded by a class/interface. Then the compiler both tracks the type relationship across multiple arguments and knows which operations are permitted.

Signature:

```java
static <T extends Comparable<? super T>> T max(T left, T right)
```

Meaning:

- `T` is a named type variable declared on the method.
- The bound `Comparable<? super T>` allows comparing one `T` with another `T` via `compareTo`.
- Both arguments `left`, `right`, and the result share `T`.
- Not every object satisfies the bound; the compiler rejects invocations for which no valid type argument can be found.

Create `GenericMaxDemo.java`:

```java
public class GenericMaxDemo {
    static <T extends Comparable<? super T>> T max(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        Integer largerNumber = max(7, 12);
        String laterWord = max("apple", "banana");

        System.out.println(largerNumber);
        System.out.println(laterWord);
    }
}
```

Run:

```bash
javac GenericMaxDemo.java
java GenericMaxDemo
```

`stdout`:

```text
12
banana
```

For `Integer`, `compareTo` compares numerically; for `String`, it compares lexicographically according to `String.compareTo`. The compiler uses the bound to permit `left.compareTo(right)`. The type contract **does not guarantee the ordering fits every business rule**: the actual comparison comes from the `Comparable` implementation.

### When the Result Should Be Number, Not T

Compare these two signatures:

```java
static <T extends Number> T choose(T a, T b)
static <T extends Number> double average(T a, T b)
```

These are two illustrative signatures. In `choose`, the result type is tied to `T`. In `average`, the result is always primitive `double`, even though the compiler only accepts inputs that are subtypes of `Number`. Choose the return type according to **the real contract**; do not write `T` just because the method already has `<T>`.

When there are multiple numeric inputs of different types, `<T extends Number>` can find a common type solution; if the algorithm only needs to call `doubleValue()` and always returns `double`, a signature `double average(Number a, Number b)` can be simpler. Do not make a method generic when no type relationship needs to be preserved.

## 9. Target Type Participating in Return Type Inference

A generic method can take no arguments yet still infer its type parameter from the expression's **expected type**.

For example, the JDK's `Collections.emptyList()` has a signature close to:

```java
public static <T> java.util.List<T> emptyList()
```

When writing:

```java
java.util.List<String> names = java.util.Collections.emptyList();
```

the compiler uses the target type `List<String>` to infer `T=String`. The method does not need to take a `String` parameter to know `T` in this invocation.

Create `TargetTypingDemo.java`:

```java
import java.util.Collections;
import java.util.List;

public class TargetTypingDemo {
    static <T> List<T> none() {
        return Collections.emptyList();
    }

    static <T> T require(T value) {
        if (value == null) {
            throw new IllegalArgumentException("null");
        }
        return value;
    }

    public static void main(String[] args) {
        List<String> words = none();
        List<Integer> numbers = TargetTypingDemo.<Integer>none();
        String value = require("Java");

        System.out.println(words.size());
        System.out.println(numbers.size());
        System.out.println(value);
    }
}
```

Run:

```bash
javac TargetTypingDemo.java
java TargetTypingDemo
```

`stdout`:

```text
0
0
Java
```

Points to remember:

1. `none()` declares `<T>` and returns `List<T>`.
2. In `List<String> words = none();`, the target type helps infer `T=String`.
3. The syntax `TargetTypingDemo.<Integer>none()` passes an explicit **type witness**; this is an option at the invocation site.
4. `require("Java")` infers `T=String` from the argument.
5. A generic signature does not automatically forbid null; `require` checks for null using its own runtime logic.

### When Is an Explicit Type Witness Needed?

You can write `SomeClass.<String>method(args)` to force the method's type parameter to take `String`. Usually the compiler can infer it, so a type witness is only useful for clarity or handling complex constraint cases. If the witness does not satisfy the bound or arguments, compilation fails.

### `var` and Context

`var x = none();` has no target type `List<String>` to constrain `T` as in the example above; the compiler may infer `List<Object>` when the type is not specifically constrained. Do not rely on `var` to preserve a desired element type when the initializer lacks information; use an explicit `List<String>` declaration or a type witness if needed.

## 10. Distinguishing "T Is Linked" from "The Method Actually Transforms Correctly"

A generic method can have a valid signature yet wrong logic. For example:

```java
static <T> T choose(T first, T second, boolean pickFirst) {
    return pickFirst ? first : second;
}
```

The method returns the right type `T`, yet the signature does not say which value should be chosen. Only the implementation defines the rule. Therefore, when reading an API, separate:

- **Type constraints:** which argument types and result type the compiler accepts.
- **Data constraints:** which value is chosen, null conditions, collection size, ordering, equals semantics, exceptions.
- **Runtime properties:** mutable/immutable, side effects, thread-safety, and type erasure.

Generics help the compiler prove a set of type relationships; they do not prove that the business algorithm is correct.

## 11. The Role of Wildcards When Linking Multiple Kinds of Arguments

Generic methods and wildcards are two complementary tools.

### 11.1. Type Parameter Connecting Positions

```java
static <T> void move(
        java.util.List<? super T> destination,
        java.util.List<? extends T> source)
```

`T` is the **bridge**: elements read from source must be safely passable into destination. The two wildcards can stand for two different concrete type arguments.

### 11.2. A Wildcard Is Not a Named Type Variable

`List<?>` indicates that the elements have an unknown type; two uses of `?` in two parameters do not automatically mean the same type. If a method needs to relate multiple positions to the same type, naming a type parameter is usually clearer.

Compare:

```java
static <T> T getFirst(java.util.List<T> list)
static Object getFirstUnknown(java.util.List<?> list)
```

The first signature preserves the relationship between element type and return type. The second only guarantees returning `Object`, because a wildcard cannot appear as a named variable in the return type. Both signatures are illustrative and need method bodies to compile standalone.

### 11.3. PECS Is Not a "Make Every Parameter a Wildcard" Rule

If a method needs to both take elements out of and put elements into a container of exact type `T`, `List<T>` may be more appropriate. If a method only takes a source for reading and a destination for writing, `extends`/`super` usually makes the API accept more type arguments while remaining safe.

A method can combine a named type parameter for the **result** and wildcards for the **inputs**. The key is each parameter's producer/consumer role, not making the signature as long as possible.

## 12. JDK APIs: Reading Signatures Relating Multiple Arguments and Results

### 12.1. `Collections.max` and Comparator

An important overload of `Collections.max` has the form:

```java
public static <T> T max(
        java.util.Collection<? extends T> coll,
        java.util.Comparator<? super T> comp)
```

Meaning: the collection supplies elements of a type compatible with `T`; the comparator can compare `T` or an appropriate supertype; the result is an element viewed as `T` at compile time. If the collection is empty, the method throws `NoSuchElementException`; if the comparator does not match business logic, generic types cannot fix the comparison algorithm.

Create `CollectionsMaxDemo.java`:

```java
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public class CollectionsMaxDemo {
    public static void main(String[] args) {
        List<String> words = List.of("tea", "java", "coffee");
        Comparator<String> byLength = Comparator.comparingInt(String::length);

        String longest = Collections.max(words, byLength);
        System.out.println(longest);
    }
}
```

Run `javac CollectionsMaxDemo.java` and `java CollectionsMaxDemo`:

```text
coffee
```

`T=String` links the collection, comparator, and result. The signature does not say the comparator must compare alphabetically; `Comparator.comparingInt(String::length)` defines ordering by length.

### 12.2. `Collections.copy`

Signature:

```java
public static <T> void copy(
        java.util.List<? super T> dest,
        java.util.List<? extends T> src)
```

`src` produces `T` values, `dest` consumes `T`. The signature returns `void`, meaning **not every generic links `T` to a return type**. The behavior of `Collections.copy` is to overwrite corresponding positions in the destination list, provided the destination is large enough; it does not automatically append into an empty list like `addAll`.

### 12.3. `Optional.map`

Inside `Optional<T>` is a method of the form:

```java
public <U> java.util.Optional<U> map(
        java.util.function.Function<? super T, ? extends U> mapper)
```

`T` belongs to the **generic class** `Optional<T>`, while `U` belongs to the **method** `map`. An `Optional<String>` instance calling `map(String::length)` can return `Optional<Integer>`. If the mapper returns null, `Optional.map` produces an empty Optional per the API; generic types do not automatically forbid null.

### 12.4. `Map.computeIfAbsent`

`Map<K,V>` has the method `V computeIfAbsent(K key, Function<? super K, ? extends V> mappingFunction)`.

- `K` and `V` are **Map's** type parameters, not declared by this method.
- The `key` parameter has type `K`; the mapping function consumes `K` and produces a result compatible with `V`.
- The method returns `V` according to the current Map's type argument.

For example, `Map<String,Integer> counts` can use `computeIfAbsent("key", String::length)` to create an Integer if no matching mapping exists yet. Storing the result, handling null, and invoking the mapping function follow the `Map`/implementation contract; the type signature does not fully describe side effects.

### 12.5. `Comparator.comparing`

Common overload:

```java
public static <T, U extends Comparable<? super U>>
java.util.Comparator<T> comparing(
        java.util.function.Function<? super T, ? extends U> keyExtractor)
```

`T` is the type of objects being compared, `U` is the extracted key type. `U` must be self-comparable via the bound. The result is `Comparator<T>`, because the comparator applies to the **source objects**, not to the key `U`. Separating each variable's role lets you read APIs with two or three type parameters without confusing the input type with the result.

## 13. Compile Errors Illustrating Type Relationships

Do not run the error snippets directly alongside working examples; the following lines are commented out to show how the compiler reacts.

### Error 1: Forgetting `<T>`

```java
// static T identity(T value) { return value; } // T is not declared.
static <T> T identity(T value) { return value; }
```

When a type parameter is not declared on a class/interface/method or valid scope, the name `T` has no meaning.

### Error 2: Demanding a Different Result Type Not Permitted by the Signature

```java
static <T> T identity(T value) { return value; }

// Integer n = String.valueOf(identity("hello")); // Invalid: String cannot be assigned to Integer.
```

You must use a real conversion if you want `String` → `Integer`; do not expect generic inference to perform data conversion.

### Error 3: Assigning Two Invariant Lists

```java
java.util.List<Integer> ints = java.util.List.of(1, 2);
// java.util.List<Number> nums = ints; // Invalid.
java.util.List<? extends Number> numsView = ints;
```

`Integer extends Number` does not make `List<Integer>` a subtype of `List<Number>`. The wildcard `? extends Number` allows reading each element as `Number`.

### Error 4: Misunderstanding a Function's Return Type

If `Function<T,R>` returns `R`, you cannot expect `List<R>` to automatically become `List<T>` when `R` differs from `T`. Check where the type variable is shared between the mapper and the result: a proper `map` API must use the same `R` in both `Function` and `List<R>`.

### Error 5: Assigning the Class's `T` to a Static Method

```java
class Holder<T> {
    // static T echo(T value) { return value; } // Cannot use the class's T.
    static <U> U echo(U value) { return value; }
}
```

The class's `T` belongs to an instance-parameterized context; a static method must declare its own `<U>` if it needs a type parameter.

### Error 6: Raw Types and Unchecked Conversions

```java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.List raw = names;
raw.add(123);
```

This snippet can compile with a warning, yet puts an `Integer` into a structure callers believe holds `String`. Reading an element out as `String` can throw `ClassCastException`. Avoid raw types so you do not break the type relationships generic methods rely on.

## 14. Type Erasure and Limits of Type Relationships

Java generics primarily use type erasure: an unbounded type variable is typically erased to `Object`, a variable with an upper bound is erased to its first bound; the compiler inserts casts where needed and may generate bridge methods.

Example:

```java
static <T> T first(T a, T b) { return a; }
```

In terms of interpretation, the post-erasure runtime signature uses `Object` in the relevant positions, even though callers are checked by the compiler with concrete type arguments. Therefore a single generic method can share bytecode for `String` and `Integer` invocations without creating two runtime copies.

Consequences:

- `<T>` does not create `T.class` or permit `new T()`.
- You cannot rely on `instanceof List<String>` to verify a List's type argument at runtime; use `List<?>` to check the class/structure and then validate data if needed.
- The compiler can catch type errors at the method call site, yet runtime `ClassCastException` can still occur when the contract is broken by raw types, unchecked casts, reflection, or external data.
- Generic metadata on **declarations** can be inspected via Reflection; that is different from each List instance carrying its own runtime type argument.

An API receiving unverified external data should not merely write a cast `(List<String>) value` and consider it safe. You need to inspect actual elements, build a cleanly typed collection, or use an appropriate runtime-checked mechanism.

## 15. When to Use Shared T, When to Use Independent A/B/R?

This is the most important design choice of the lesson.

| Goal | Suitable Signature | Reason |
|---|---|---|
| Take a value and return the same type | `<T> T identity(T value)` | Connects input and result via `T` |
| Pick one of two compatible values | `<T> T choose(T a, T b)` | Both parameters and result share one type solution `T` |
| Package two values of different types | `<A,B> Pair<A,B> pair(A a, B b)` | Keeps the two types distinct in the result |
| Produce a result from two input types | `<A,B,R> R combine(A a,B b,BiFunction<? super A,? super B,? extends R> fn)` | Result `R` is linked to the mapper |
| Transform List<T> to List<R> | `<T,R> List<R> map(List<? extends T> src,Function<? super T,? extends R> fn)` | T holds input, R holds output |
| Move elements from source to destination | `<T> void append(List<? super T> dst,List<? extends T> src)` | T connects producer/consumer |
| Compute average of numbers | `double average(Number a,Number b)` | No need for generics if return type does not need linking to inputs |
| Compare two comparable objects | `<T extends Comparable<? super T>> T max(T a,T b)` | Bound provides `compareTo` and preserves result type |

**Reading rule:** if the same name `T` appears in multiple positions, identify the **relationship** it expresses. If three type parameters `A,B,R` are declared, identify their **independent roles** and which arguments/functions connect them. If there is no relationship to protect, a concrete type may be clearer than generics.

## 16. Six-Step Method for Analyzing Long Signatures

Take the signature:

```java
static <A, B, R> java.util.List<R> zip(
        java.util.List<? extends A> left,
        java.util.List<? extends B> right,
        java.util.function.BiFunction<? super A, ? super B, ? extends R> merger)
```

This is an illustrative signature for an algorithm pairing two lists position by position; it needs a method body to run.

**Step 1 — locate the declaration:** `<A,B,R>` belongs to the method `zip`. They are independent at the start of the declaration.

**Step 2 — locate each occurrence:** `A` in `left` and the first input of `merger`; `B` in `right` and the second input; `R` in the output of `merger` and the element type of the returned list.

**Step 3 — determine wildcard roles:** `left` and `right` are producers; `merger` consumes an `A` and a `B`, then produces an `R`. The `extends` wildcard on List and `super` on the function inputs express the exact data flow direction.

**Step 4 — apply a concrete call:** If `left` is `List<String>`, `right` is `List<Integer>`, and merger produces `String`, a valid solution is `A=String`, `B=Integer`, `R=String`.

**Step 5 — inspect the target type:** Callers can receive `List<String>` without a cast. The return type is not `List<Object>`, because `R` keeps the relationship with the mapper.

**Step 6 — do not infer behavior beyond the signature:** The signature does not state whether, if the two lists have different lengths, `zip` stops at the shorter one, throws an exception, or pads default elements. That must be defined by the implementation and API documentation. The type system does not prescribe a length policy on its own.

### Complete `zip` Program

Create `ZipDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.BiFunction;

public class ZipDemo {
    static <A, B, R> List<R> zip(
            List<? extends A> left,
            List<? extends B> right,
            BiFunction<? super A, ? super B, ? extends R> merger) {
        int size = Math.min(left.size(), right.size());
        List<R> result = new ArrayList<>(size);

        for (int i = 0; i < size; i++) {
            result.add(merger.apply(left.get(i), right.get(i)));
        }
        return result;
    }

    public static void main(String[] args) {
        List<String> names = List.of("Lan", "Mai", "An");
        List<Integer> scores = List.of(8, 9);
        List<String> summaries = zip(
                names, scores,
                (name, score) -> name + "=" + score);

        System.out.println(summaries);
    }
}
```

Run:

```bash
javac ZipDemo.java
java ZipDemo
```

`stdout`:

```text
[Lan=8, Mai=9]
```

Here **the method body** explicitly uses `Math.min` and only pairs elements at indices present in both lists. This pattern shows clearly: the signature guarantees the type relationship between sources and result; the implementation decides how to handle size mismatches.

## 17. Evaluating Signature Quality When Designing APIs

When writing a generic method with multiple arguments, ask yourself:

1. How many **independent data types** need to be represented? If inputs are genuinely different kinds, do not force them into the same `T` unnecessarily.
2. Must the result have the same type as an input? If yes, connect them using the same `T`. If the result is a new type, consider `R`.
3. Is a parameter a producer or consumer? Choose `? extends T`/`? super T` for directional flexibility when needed.
4. What capabilities does the algorithm require on `T`? If `compareTo` or `doubleValue` is needed, use an appropriate bounded type parameter.
5. Is the return type specific enough that callers avoid unchecked casts? An unnecessary `Object` return is often a sign of lost information.
6. Does it depend on collection subtyping/invariance? `List<Integer>` is not a `List<Number>`.
7. Does the API need runtime validation independent of generic types (null, size, mutability, external data)?
8. Is `<T>` being used just to overcomplicate a method returning a concrete type? If there is no real type relationship, dropping generics may be better.

Do not optimize to make a signature "look clever"; prefer constraints that callers can understand and the compiler can enforce.

## 18. Self-Check Exercises with Solutions

### Exercise 1 — Identifying T

```java
static <T> T second(T a, T b) {
    return b;
}
```

Question: Is `String word = second("A","B")` valid? What about `Integer number = second(1,2)`? What are the results? Both are valid; `T` is inferred as `String`, `Integer` respectively; the results are `"B"` and `2`. `return b` is the meaning of the method body, separate from the signature's contract.

### Exercise 2 — Two Type Variables or One?

With the goal of keeping a `String` and an `Integer` together in a result with properly typed accessors, should you use `<T> T choose(T,T)` or `<A,B> Pair<A,B> pair(A,B)`? Choose `pair`: the two values have independent types and are kept in two separate components, whereas `choose` only returns one result of type `T`.

### Exercise 3 — Finding an Inference Solution

```java
static <T> T first(T a, T b) { return a; }
Number result = first(1, 2.5);
```

These are illustrative snippets. Why is it not required for both arguments to have the same runtime class? The compiler finds a `T` satisfying the static types of both arguments and the target type `Number`; numeric wrappers can both be compatible with `Number`. Equal runtime classes are not required.

### Exercise 4 — Linking Collections

The function `append` takes `List<? super T>` and `List<? extends T>`. Can it be called with destination `List<Number>` and source `List<Integer>`? Yes. What if replaced with two `List<T>` parameters? Because of invariance, that flexibility can no longer be expressed directly.

### Exercise 5 — New Result Type

```java
static <T, R> java.util.List<R> map(
        java.util.List<T> src,
        java.util.function.Function<T, R> f)
```

Question: with `List<String>` and `String::length`, what is the result type? The compiler can infer `T=String`, `R=Integer`, returning `List<Integer>`. Using `List<? extends T>` and `Function<? super T,? extends R>`, the API accepts more subtype variants while preserving the result relationship.

### Exercise 6 — Bounded T

Why can `<T extends Comparable<? super T>> T max(T,T)` call `compareTo`, whereas `<T> T max(T,T)` is not guaranteed by the compiler? Because the bound provides the `Comparable` contract. Without the bound, `T` could be a type lacking `compareTo`.

### Exercise 7 — Reading a Long Signature

For `<A,B,R> List<R> zip(List<? extends A>,List<? extends B>,BiFunction<? super A,? super B,? extends R>)`, write down separately: the source of `A`, the source of `B`, where `R` appears, the data-flow direction of each wildcard, and what the API does **not** yet guarantee (e.g., handling lists of different lengths). Cross-check against `ZipDemo`.

## 19. Conclusion

A generic method can express type relationships that concrete types or `Object` cannot: **a single `T` links multiple parameters to the result; `A` and `B` keep distinct input types; `R` connects a mapper's output to the return type; wildcards widen safely passable argument domains; bounds enable operations on type variables**.

When reading a signature, always locate **where each type variable is declared, every position where it appears, and the type inference solution at a specific call site**. When designing, preserve the exact relationships the compiler needs to enforce, document runtime behavior separately, and avoid assuming "same T" means the same runtime class. By doing so, you can confidently write APIs from `identity`, `pair`, `combine` to `append`, `map`, and `zip` where callers receive exact types without manual casting.