# Reading Generic Signatures and Tracking Where Each Type Variable Is Bound in Java

A generic signature can be as short as `T get()` or as layered as `<T, R> List<R> map(List<? extends T> source, Function<? super T, ? extends R> mapper)`. What matters when reading it is not memorizing the letters `T`, `E`, `K`, and `V`: those are merely **type variable** names. What matters is identifying **where the type variable is declared, which positions share that variable, what its bounds are, and how a concrete type is assigned to it when calling the API**.

This lesson walks through a step-by-step method for reading signatures, from generic classes and generic methods to bounded types, wildcards, return types, constructors, and Java Core APIs. Complete program listings use Java 17+; standalone extracted signatures are marked as illustrative code.

## 1. Three Mandatory Questions When Encountering a Signature

For each type variable name such as `T`, trace three points:

1. **Where is it declared?** Find the `<...>` pair declaring the type variable: `class Box<T>`, `interface Converter<I, O>`, `static <T> T first(...)`, or constructor `<U> Box(U input)`. A letter `T` is only a type variable if it lies within a valid declaration scope.
2. **At which positions is it bound?** Record every place `T` appears: fields, parameters, return types, nested type arguments, bounds of other variables. The same `T` within the same scope represents **one linked type choice**, not independent type choices.
3. **What is the type choice at the usage site?** With `Box<String>`, `Box`'s type parameter is applied as `String`. With a generic method, the compiler infers from actual arguments, assignment context, and constraints, or the caller passes an explicit type witness such as `Utils.<String>identity("Java")`.

A signature expresses a **compile-time** contract. The actual runtime types of values must still obey that contract when the program runs; raw/unchecked paths can break static guarantees. There is no need to look for a “runtime variable named T” inside objects.

### Opening Example

```java
static <T> T identity(T value) {
    return value;
}
```

The signature breaks down into:

- `static`: class-level member.
- `<T>`: **declaration of type variable T** belonging specifically to the method.
- `T` before the name `identity`: **return type**, using the declared type variable.
- `T value`: **parameter type**, using that exact same type variable.
- When calling `String text = identity("Java");`, the compiler can infer `T = String`. When calling `Integer n = identity(7);`, the compiler can infer `T = Integer` (the value `7` is boxed).

This signature states: “the method accepts a `T` and returns a `T`”. It does not guarantee that the returned value is the same **object instance** as the input for every implementation sharing a similar signature; object identity holds only if the method body implements it as in the example.

## 2. Distinguishing Type Variable Declarations from Passing Type Arguments

Two uses of angle brackets `<...>` look alike yet play different roles:

| Syntax | Role | What to Track |
| --- | --- | --- |
| `class Box<T>` | Declares a class type parameter | `T` is in scope across eligible instance members of `Box` |
| `interface Pair<K, V>` | Declares two type parameters | `K` and `V` are independent until linked by signatures |
| `Box<String>` | Uses a concrete type argument | Positions of `T` in `Box` are treated as `String` at that usage site |
| `Map<String, Integer>` | Supplies two type arguments | `K = String`, `V = Integer` |
| `<T> T read(...)` | Declares a method type parameter | `T` is inferred/applied per invocation |
| `Class<T>` | Uses `T` as a type argument for `Class` | `T` must already be declared in an enclosing scope |
| `List<?>` | Wildcard, meaning an unknown element type | Does not create a named variable `T` for the author to reuse |
| `new Box<>("a")` | Diamond inference at a constructor call | Compiler infers the type argument from context/arguments |

The name `T` holds no special meaning for the JVM. You can name it `ITEM`, `ID`, or `SOURCE` if that is clearer and a valid Java identifier. Common conventions are `T` (type), `E` (element), `K` (key), `V` (value), `R` (result), and `U` (additional type).

Important rule: **two declarations sharing the same letter `T` in different scopes do not automatically bind to one another**. Conversely, occurrences of `T` within **the same declaration scope** share the same set of constraints. When locating a declaration, read backward from the usage site toward the syntax of the enclosing method, class, or interface.

## 3. Reading a Generic Class Signature from Left to Right

Consider `SignatureClassDemo.java`:

```java
public class SignatureClassDemo {
    static final class Entry<K, V> {
        private final K key;
        private V value;

        Entry(K key, V value) {
            this.key = key;
            this.value = value;
        }

        K key() {
            return key;
        }

        V value() {
            return value;
        }

        void replace(V newValue) {
            value = newValue;
        }
    }

    public static void main(String[] args) {
        Entry<String, Integer> score = new Entry<>("Lan", 8);
        score.replace(9);

        String name = score.key();
        Integer points = score.value();

        System.out.println(name + ": " + points);
    }
}
```

Compile and run:

```bash
javac SignatureClassDemo.java
java SignatureClassDemo
```

`stdout` result:

```text
Lan: 9
```

### Step 1: Identify the “Type Symbol Table”

`Entry<K,V>` declares two class-level type parameters:

| Type Variable | Declared At | Bound Positions in Class |
| --- | --- | --- |
| `K` | `Entry<K,V>` | `K key`, constructor parameter `K key`, return type `K` of `key()` |
| `V` | `Entry<K,V>` | `V value`, constructor `V value`, return type `V` of `value()`, parameter `V newValue` of `replace(...)` |

### Step 2: Substitute at a Concrete Call Site

`Entry<String, Integer>` makes the compiler check members *as if* they had the types:

```java
// Mental model of source types at the usage site, not a new class.
Entry(String key, Integer value);
String key();
Integer value();
void replace(Integer newValue);
```

There is no separate `EntryStringInteger` class generated. `score.replace("nine")` is rejected at compile time. `score.replace(9)` is permitted because boxing converts `int` to `Integer`.

### Step 3: Distinguish Type Information from Values

`K` is not a variable holding a key, and `V` is not a data value. `K`/`V` define **type relationships**; `key` and `value` are the fields holding data. An `Entry<String,Integer>` object can hold the values `"Lan"` and `9`, while the type arguments only describe types for compile-time checking.

### Step 4: Read the Constructor

`Entry(K key, V value)` uses `K` and `V` already declared on the class. There is no `<K,V>` before the constructor, so this constructor **does not declare** a new pair of type parameters. The compiler checks the constructor against the `Entry<String,Integer>` created at the call site.

## 4. Reading a Generic Method Signature

A generic method has its own type-parameter list placed **before the return type**, after any modifiers:

```java
public static <T> T first(java.util.List<T> values)
```

Breakdown: `public static` are modifiers; `<T>` is the type parameter declaration; `T` before `first` is the return type; `List<T>` uses `T` to tie the input elements and the result to the same type relationship.

### Complete Program

Create `MethodSignatureDemo.java`:

```java
import java.util.List;

public class MethodSignatureDemo {
    static <T> T first(List<T> elements) {
        if (elements.isEmpty()) {
            throw new IllegalArgumentException("Empty");
        }
        return elements.get(0);
    }

    static <T> boolean contains(List<T> elements, T wanted) {
        return elements.contains(wanted);
    }

    public static void main(String[] args) {
        String a = first(List.of("A", "B"));
        Integer n = first(List.of(10, 20));

        System.out.println(a);
        System.out.println(n);
        System.out.println(contains(List.of("A", "B"), "B"));
    }
}
```

Run:

```bash
javac MethodSignatureDemo.java
java MethodSignatureDemo
```

`stdout`:

```text
A
10
true
```

With `first(List.of("A", "B"))`, the compiler infers `T` as `String`; with `first(List.of(10, 20))`, as `Integer`. The two calls do not share a “program-wide T”. Binding occurs **independently for each invocation of the generic method**.

With `contains(List<T>, T)`, the same variable `T` appears twice; the compiler must find a way to infer a type argument satisfying constraints at the call site. **Do not assume the compiler always forces both input expressions to have the exact same runtime class**: the inference algorithm may find a common supertype if the signature and context permit. If business logic strictly requires homogeneous element types, design the API and validation appropriately; generic inference is not a runtime class-equality check.

### Common Mistake: Missing the `<T>` Declaration

```java
// Invalid if no type parameter T exists in scope:
// static T missing(T value) { return value; }

// Correct:
static <T> T identity(T value) { return value; }
```

In a generic class `Box<T>`, an **instance method** can use the class's `T` without declaring an extra parameter. However, a `static` method cannot directly use the class-level `T` because static members belong to the shared class, not to any particular `Box<String>` instantiation.

## 5. Distinguishing Class Type Parameters from Method Type Parameters

Create `ScopeDemo.java`:

```java
public class ScopeDemo {
    static final class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        <R> R convert(java.util.function.Function<? super T, ? extends R> f) {
            return f.apply(value);
        }

        static <U> U echo(U value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Holder<Integer> holder = new Holder<>(42);

        Integer original = holder.get();
        String label = holder.convert(n -> "ID-" + n);
        Boolean yes = Holder.echo(true);

        System.out.println(original);
        System.out.println(label);
        System.out.println(yes);
    }
}
```

Run:

```bash
javac ScopeDemo.java
java ScopeDemo
```

`stdout`:

```text
42
ID-42
true
```

Trace it:

- `Holder<T>` declares `T` for the **class**.
- Field `value`, constructor `Holder(T value)`, and instance method `T get()` use the class's `T`. With `Holder<Integer>`, the compiler uses `Integer` in those positions.
- `<R> R convert(...)` additionally declares `R` belonging to the **method**. Inside `convert`, `T` comes from the class (`Integer` for this receiver), while `R` is inferred when calling the method (`String` in the example).
- `Function<? super T, ? extends R>` accepts a function able to process a `T` value and produce a value compatible with `R`. Wildcards have their own semantics; `?` is not a named type variable.
- `static <U> U echo(U value)` declares `U` specifically for the static method; this method does not depend on `holder`'s `Integer` type argument. You can call `Holder.echo(true)` and the compiler infers `U=Boolean`.

**Quick question:** Which type variable do `get()` and `convert(...)` share? Does `echo(...)` read the class's `T`? If two calls to `convert` return `String` and `Long` respectively, is `R` chosen per call or fixed on the object? (Answer: they share the class's `T`; `echo` does not use `T`; `R` belongs to each call.)

### Generic Constructors Also Have Their Own Type Variables

A constructor can declare `<U>`, distinct from the class's type variable. Standalone declaration-level example:

```java
class Container<T> {
    final T value;

    <U> Container(U source,
                  java.util.function.Function<? super U, ? extends T> convert) {
        this.value = convert.apply(source);
    }
}
```

With `Container<Integer> x = new Container<>("123", Integer::parseInt);`, the **class** type parameter is `T=Integer`, while the **constructor** type parameter `U` can be inferred as `String`. The constructor transforms `U` into `T`, thereby preserving the type relationship between the input data and the stored field.

Do not place `<U>` as a class type argument if it is declared before the constructor. Where the declaration sits is the key to reading scope accurately.

## 6. A Method for Annotating Long Signatures

Consider a custom-designed signature:

```java
static <S, R> java.util.List<R> map(
        java.util.List<? extends S> source,
        java.util.function.Function<? super S, ? extends R> converter)
```

This is an **illustrative signature** without a method body yet. You can build a table before reading the logic:

| Symbol | Declared At | Where Constraints Appear | Role |
| --- | --- | --- | --- |
| `S` | Method `<S,R>` | `? extends S`, `? super S` | Input type of the transformation |
| `R` | Method `<S,R>` | `? extends R`, `List<R>` | Result type |
| `? extends S` | Wildcard in `List` | Depends on `S` | Source list providing `S`-compatible elements |
| `? super S` | Wildcard in `Function` | Depends on `S` | Function able to accept values of type `S` |
| `? extends R` | Wildcard in `Function` | Depends on `R` | Function producing `R`-compatible values |

Plain-English reading: “The method takes a list containing values readable as `S`, together with a transformation that accepts `S` and produces `R`; the result is a list of `R`.”

Start from the **result and relationships** before diving deep into wildcards. Do not try to assign a single fixed concrete type to each `?` symbol in your head; a wildcard is a capability bound, whereas named type parameters are the anchor points linking related positions.

### Plugging Concrete Types into the Table

If a call passes `List<Integer>` and a function converting numbers to strings, one valid inference is `S=Integer` and `R=String`. Then:

- `List<Integer>` fits `List<? extends Integer>`.
- A function accepting `Integer` fits `Function<? super Integer, ? extends String>`.
- The result `List<R>` has type `List<String>`.

Actual type inference may consider multiple candidates and pick according to constraints and context. Substituting `S=Integer`, `R=String` is a way to read one concrete invocation, not the complete `javac` algorithm.

## 7. Bounded Type Parameters: Constraints Start at the Declaration

A type parameter can carry a **bound**. Look at the example:

```java
static <T extends Number> double twice(T value)
```

Read `<T extends Number>` first: only types compatible with `Number` are accepted, allowing the method body to call `value.doubleValue()`.

### Complete Program

Create `BoundSignatureDemo.java`:

```java
public class BoundSignatureDemo {
    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2;
    }

    static <T extends Comparable<? super T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        System.out.println(twice(3));
        System.out.println(twice(1.25));
        System.out.println(larger("cat", "dog"));
    }
}
```

Run:

```bash
javac BoundSignatureDemo.java
java BoundSignatureDemo
```

`stdout`:

```text
6.0
2.5
dog
```

#### Reading `<T extends Number>`

- `T` is declared on the method and **bounded** by `Number`.
- `T value` accepts values whose type satisfies the bound.
- `double` is a concrete return type, **not** `T`. Hence calling `twice(Integer)` or `twice(Double)` both return primitive `double`.
- `twice("3")` fails the bound and does not compile.

#### Reading `<T extends Comparable<? super T>>`

- `T` is declared on the method and simultaneously appears inside **its own bound** (a recursive bound).
- `Comparable<? super T>` means values of type `T` can be compared with objects of type `T` via a `Comparable` interface accepting `T` or a suitable supertype of `T`.
- `T a` and `T b` link both arguments to the return type `T`.
- `a.compareTo(b)` is valid because the bound lets the compiler prove comparability.

The key initial takeaway is “bounds supply the operations the compiler permits on `T`”. If `Comparable<? super T>` still feels difficult, first write the simpler variant `<T extends Comparable<T>>` and test it with `String`; then revisit the lower-bounded wildcard to see why the more flexible pattern exists.

### Multiple Bounds

Syntax example:

```java
<T extends Number & Comparable<T>>
```

`T` must satisfy both bounds. If there is a **class bound**, it must come first; interfaces follow after `&`. `extends` is used even when bounds are interfaces. A type variable without an explicit `extends` defaults to an `Object` bound under standard type-parameter rules.

Do not equate `<T extends Number>` with `List<? extends Number>`:

- `<T extends Number>` **declares a named type variable** `T` along with an upper bound.
- `List<? extends Number>` **uses a wildcard** in `List`'s type argument slot; it does not create a name `T` for the author to reference elsewhere.

## 8. Type Parameters and Wildcards: Two Different Kinds of “Linking”

In a signature, `T` can appear in multiple places to assert a relationship; two `?` wildcards are not implicitly the same type.

### Comparison Example

```java
static <T> T chooseFirst(java.util.List<T> values)

static Object chooseFirstUnknown(java.util.List<?> values)
```

These are two illustrative signatures without bodies. Given `List<String>`:

- `chooseFirst` can return static type `String` because `T` links input elements and the result.
- `chooseFirstUnknown` only promises to return `Object` because it does not link the return type to the wildcard.
- `List<?>` still maintains type safety when **reading**: reading out an `Object` is safe; trying to add non-`null` elements via `add` is restricted at compile time.

### Why Not Replace Every `T` with `?`?

Syntax like `? first(List<?> values)` is **invalid**: wildcards may only be used in valid type argument positions, not in place of a standalone return type. If the return type must depend on the input type, declare a type parameter and use the same variable in both places.

### Having Both Wildcards and `T` in the Same Signature

Example:

```java
static <T> void copy(
        java.util.List<? super T> destination,
        java.util.List<? extends T> source)
```

Analysis:

- `T` is declared on the method.
- `source` is the **producer** of values readable as `T`: `? extends T`.
- `destination` is the **consumer** receiving values of type `T`: `? super T`.
- Although the two parameters are two lists with different type arguments, they both **refer to the same `T`** to guarantee safe element transfer.
- The separate wildcards on `source` and `destination` are not two new definitions of `T`.

This pattern illustrates the **PECS** rule (Producer Extends, Consumer Super). It is a tool for reading signatures, not a mandate to use wildcards in every API. If you both read and write a list whose exact type must match, `List<T>` can be simpler.

### A Wildcard Means an Unknown Type, Not `Object`

`List<?>` does not mean `List<Object>`. `List<Object>` permits adding any object, whereas `List<?>` protects a specific element type unknown to the caller. Even though the compiler can read elements of `List<?>` as `Object`, it does not permit arbitrarily adding an `Object`.

## 9. Reading Nested Type Arguments

Do not look at only one `<...>` layer. With:

```java
Map<String, List<Integer>>
```

Work from the outside in:

1. `Map<K,V>` has two type parameters; here `K=String` and `V=List<Integer>`.
2. `List<E>` sits inside `V`; here `E=Integer`.
3. `Map.put(K,V)`, after applying type arguments, requires a `String` key and a `List<Integer>` value.
4. `Map.get(Object)` accepts `Object` as the key argument per the library signature, yet the return type of `get` is still `V` (i.e., `List<Integer>`) for this Map variable; it may return `null` when no mapping exists.

Create `NestedSignatureDemo.java`:

```java
import java.util.List;
import java.util.Map;

public class NestedSignatureDemo {
    public static void main(String[] args) {
        Map<String, List<Integer>> marks = Map.of(
                "Lan", List.of(8, 9),
                "Mai", List.of(7));

        List<Integer> lanMarks = marks.get("Lan");
        Integer first = lanMarks.get(0);

        System.out.println(lanMarks);
        System.out.println(first);
    }
}
```

Run `javac NestedSignatureDemo.java`, `java NestedSignatureDemo`:

```text
[8, 9]
8
```

Trace the type of `first` backward: `Map<String,List<Integer>>` → `get("Lan")` returns `List<Integer>` → `get(0)` on List returns `Integer`. If you call `marks.put(...)` in this example, `Map.of` creates an immutable map so mutating it throws `UnsupportedOperationException` at runtime even when the key–value types are valid. **Generic type validity does not imply an object permits mutation.**

### A Generic Type Does Not Mean Every Method Parameter Is a Type Argument

In `Map<K,V>`, `get(Object key)` intentionally takes `Object` in the API. Readers must check the actual signature instead of guessing `get(K key)`. Likewise, `Collection<E>.contains(Object o)` takes `Object`. Generic signatures define what the compiler guarantees; do not extrapolate from a variable name alone.

## 10. Cases Where `T` Appears in a Superclass or Interface Type

A class can **fix** the type argument of a parent interface:

```java
interface Reader<T> {
    T read();
}

class NameReader implements Reader<String> {
    @Override
    public String read() {
        return "Lan";
    }
}
```

This is illustrative declaration code. `Reader<T>` declares variable `T`; `NameReader implements Reader<String>` supplies the type argument `String`, so the implementing method must satisfy the `String read()` contract at the source level.

A subclass can also **forward** a type parameter:

```java
class IdentityReader<T> implements Reader<T> {
    private final T value;

    IdentityReader(T value) {
        this.value = value;
    }

    @Override
    public T read() {
        return value;
    }
}
```

Trace from `IdentityReader<T>` (declaration) to `Reader<T>` (usage) and then to `T read()`. The letter `T` in `Reader<T>` on the `implements` clause is a **type argument** passed to the interface, even though it shares the same name as the class's declared type parameter.

Extended example: `class Result<T> extends Container<List<T>>` means `Result`'s type parameter `T` is nested inside `List<T>`, and the whole `List<T>` serves as the type argument to the parent class `Container`. To understand inherited methods, you must trace each such type-argument mapping.

### Distinguishing Override from Overload When Reading Generic Methods

If an interface requires `T read()` and a class implements `Reader<String>`, the compiler checks `String read()` against the specialized contract. After type erasure, the compiler may generate a bridge method to preserve polymorphism; you never write bridge methods yourself. Meanwhile, two overloads `void use(List<String>)` and `void use(List<Integer>)` in the same class become indistinguishable after erasure and produce a name-clash error.

Practical tip: when an inherited method “suddenly returns String”, do not look for `<String>` on that method right away. Trace from the parent interface/class through `implements`/`extends` to see where the type variable was bound.

## 11. Reading Several Java Core Signatures Step by Step

The signatures below are presented to practice reading type relationships. Some declarations are simplified by omitting modifiers/annotations that do not govern type relationships; for the exact API docs of a specific JDK version, check the corresponding JavaDoc.

### 11.1. `List<E>`: Type Parameter on an Interface

Relevant signatures:

```java
interface List<E> {
    boolean add(E element);
    E get(int index);
}
```

This is an excerpt model for reading, not the full JDK interface.

Mapping `List<String>` → `E=String`:

| Member | Type After Applying `E=String` |
| --- | --- |
| `add(E element)` | Parameter is seen by the compiler as `String` |
| `E get(int index)` | Result is seen by the compiler as `String` |
| `int index` | Remains `int`, independent of `E` |

`List<E>` declares only **one** type parameter; it does not redeclare `E` on each method.

### 11.2. `Map<K,V>`: Two Independent Type Parameters

Selected members:

```java
V put(K key, V value);
V get(Object key);
Set<Map.Entry<K, V>> entrySet();
```

With `Map<String, Integer>`:

- `put` accepts `String` and `Integer`, and returns `Integer` (may be `null` per map behavior).
- `get` accepts `Object`, and returns `Integer` (may also be `null`).
- `entrySet` returns `Set<Map.Entry<String, Integer>>`, containing **two nested generic layers**.

If `Map.Entry<K,V>` is still unclear, continue mapping: `Entry.getKey()` has type `K`, and `Entry.getValue()` has type `V`. No new type parameter is added on `entrySet`; it reuses the pair declared on `Map`.

### 11.3. `Collections.copy`: PECS and One `T` Linking Two Lists

JDK method signature:

```java
public static <T> void copy(
        List<? super T> dest,
        List<? extends T> src)
```

- `<T>` declares one type parameter belonging to the **static method**.
- `void`: the method returns no element; `T` merely links the two parameters.
- `src` supplies elements as `T`; `dest` receives `T`.
- Do not assume “append” behavior: `Collections.copy` **overwrites** existing positions in the destination list; the destination list must be at least as long as the source, otherwise it throws `IndexOutOfBoundsException`.

Create `CopySignatureDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class CopySignatureDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4);
        List<Number> target = new ArrayList<>(
                Arrays.asList(0, 0, 0));

        Collections.copy(target, source);
        System.out.println(target);
    }
}
```

Run:

```bash
javac CopySignatureDemo.java
java CopySignatureDemo
```

`stdout`:

```text
[2, 4, 0]
```

In this invocation, `T=Integer` is a valid choice: `List<Integer>` matches `List<? extends Integer>`; `List<Number>` matches `List<? super Integer>`. `Collections.copy` replaces the first two elements and leaves the third intact. If `List.of(0,0,0)` were used as the destination, even though its size is large enough, that list does not support `set` and would fail at runtime; generic signatures do not promise mutability.

### 11.4. `Comparator.comparing`: One Method, Two Type Variables

Commonly used JDK overload signature:

```java
public static <T, U extends Comparable<? super U>>
Comparator<T> comparing(
        Function<? super T, ? extends U> keyExtractor)
```

Break down in order:

1. `<T, U extends Comparable<? super U>>` declares two **method** type parameters.
2. `U` has a bound requiring extracted keys to be comparable; `T` has no explicit bound.
3. `Function<? super T, ? extends U>` accepts an object of type `T` and produces a `U`-compatible key.
4. `Comparator<T>` is the return type, meaning a comparator for `T` objects; **not** `Comparator<U>`.
5. With `Comparator.comparing(String::length)`, the key type can be `Integer` (`U=Integer`), while the compared object type is `String` (`T=String`) when context suffices for inference.

To avoid target-typing issues with method references when testing standalone, you can write `Comparator.<String, Integer>comparing(String::length)` or `Comparator.comparing((String s) -> s.length())`. Explicit type witnesses do not create a new generic class; they only clarify type arguments for the **method call**.

Create `ComparatorSignatureDemo.java`:

```java
import java.util.Comparator;
import java.util.List;

public class ComparatorSignatureDemo {
    public static void main(String[] args) {
        Comparator<String> byLength =
                Comparator.comparing((String s) -> s.length());

        String longest = List.of("go", "java", "api")
                .stream()
                .max(byLength)
                .orElseThrow();

        System.out.println(longest);
    }
}
```

Run `javac ComparatorSignatureDemo.java` and `java ComparatorSignatureDemo`:

```text
java
```

Keep two separate columns: `T=String` represents the objects being compared; `U=Integer` represents the extracted comparison key. Do not conflate `T` and `U` just because they belong to the same method.

### 11.5. `Optional.map`: Class Type Parameter Plus Method Type Parameter

JDK signature:

```java
public <U> Optional<U> map(
        Function<? super T, ? extends U> mapper)
```

This signature is an **instance method inside `Optional<T>`**:

- `T` comes from the **class** declaration `Optional<T>`; it is not declared by `map`.
- `<U>` is the type variable declaration **of the `map` method**.
- `mapper` accepts `T` and produces a `U`-compatible value.
- The result `Optional<U>` holds the transformed value's type, distinct from the input `Optional<T>`.

Create `OptionalSignatureDemo.java`:

```java
import java.util.Optional;

public class OptionalSignatureDemo {
    public static void main(String[] args) {
        Optional<Integer> length = Optional.of("Java")
                .map(String::length);

        System.out.println(length.orElse(0));
    }
}
```

Run `javac OptionalSignatureDemo.java`, `java OptionalSignatureDemo`:

```text
4
```

`Optional.of("Java")` creates an `Optional<String>`; at the `map` invocation, `T=String` and `U=Integer`. `map` returns `Optional<Integer>`; `orElse(0)` returns `Integer`, which is printed. If the mapper returns `null`, `Optional.map` produces an empty optional per the JDK contract rather than turning into `Optional<null>`.

## 12. Method Type Inference: Constraints at the Call Site

At this point, separate **declaration** from **application**. Given:

```java
static <T> T pick(T first, T second) {
    return first;
}
```

The signature has one `T`, yet the compiler does not always infer types simply by requiring “the runtime classes of both arguments must match”. For example, `pick(10, 20)` can use `T=Integer`; a call with different value types can infer an appropriate supertype or intersection type depending on context. Thus “same T” means the expressions must **jointly satisfy the constraints for the type variable**, not necessarily share the exact same runtime class.

### Target Context Can Affect Inference

```java
import java.util.Collections;
import java.util.List;

public class InferenceDemo {
    static <T> T identity(T value) {
        return value;
    }

    public static void main(String[] args) {
        List<String> empty = Collections.emptyList();
        String word = InferenceDemo.<String>identity("typed");
        System.out.println(empty.size());
        System.out.println(word);
    }
}
```

Run `javac InferenceDemo.java` and `java InferenceDemo`:

```text
0
typed
```

`Collections.emptyList()` declares the generic method `<T> List<T> emptyList()`; even though no arguments are passed, the target type `List<String>` helps infer `T=String`. `InferenceDemo.<String>identity("typed")` passes an explicit type witness. If a type is supplied that violates the method parameter or bound, the compiler rejects it.

### Diamond and `var` Are Not the Same

`List<String> words = new ArrayList<>();` infers type arguments for the constructor/class from the target. `var words = new ArrayList<String>();` asks the compiler to infer the **local variable type** from the initializer. `var` does not declare a new type parameter; it only asks the compiler to deduce a static type at the declaration point. Expressions lacking context can cause the inferred type to be broader than intended; inspect what the IDE/compiler actually infers instead of blindly assuming `String`.

### Overload Resolution and Generics

When overloads exist, the compiler uses static types, inference, applicability rules, and specificity to select a method. Do not look at a single `<T>` in isolation and assert which overload will be chosen before checking the calls and other overloads. In the same class, two methods differing only by `List<String>` vs. `List<Integer>` collide due to type erasure; generics do not permit creating such overloads.

## 13. Scope and Binding Points: Do Not Confuse Where Names Appear

Common declaration locations:

| Location | Syntax | Typical Scope of Use |
| --- | --- | --- |
| Class | `class Box<T> { ... }` | Instance members and declarations within eligible inner scope |
| Interface | `interface Repository<ID,E> { ... }` | Interface methods/return types and implementing subtypes |
| Record | `record Pair<K,V>(K key, V value) {}` | Components, accessors, and instance behavior |
| Method | `<T> T method(T x)` | Parameters, return type, throws/body as eligible |
| Constructor | `<U> Box(U x)` | That constructor |
| Generic supertype usage | `implements Reader<String>` | Binds `Reader<T>`'s `T` to `String` for the subtype |
| Type argument usage | `Class<T> token` | Uses `T` already in scope as an argument to another generic |

A practical tracking approach using a “type-variable ledger”:

```text
Signature:
class Cache<K, V> {
    V put(K key, V value)
    <R> R convert(V value, Function<? super V, ? extends R> f)
}

Var    Declared At     Bound Positions in Signature
K      Cache<K,V>      key of put
V      Cache<K,V>      value/return of put;
                      parameter value and input of f in convert
R      <R> convert     output of f and return of convert
```

This listing is a **signature diagram**, not a standalone runnable Java class. When reading `Cache<String,Integer>`, fill in `K=String`, `V=Integer`. One invocation of `convert` can pick `R=String`, while another invocation can pick `R=Long` on the very same `Cache<String,Integer>` object. That is why you must record the **Declared At** column instead of just writing “T is a data type”.

### Warning on Shadowing

Type parameter names can become misleading when multiple scope levels reuse the same short letter. In production code, choose distinct names (class's `T`, method's `R`) to avoid misreading. A second type variable with a different name is **not** automatically linked to the first just because both have an `Object` bound or appear in the same signature.

A method call may infer two type parameters to the same concrete type, yet that is an **invocation solution**, not proof that the two parameters were declared identical. If the author wants a fixed identity type relationship, use the same named type parameter in all required positions.

## 14. Type Erasure: Track Constraints at Compile Time, Do Not Assume a “Runtime Type `T`”

In Java, type variables and type arguments are mostly handled by **type erasure**:

- An unbounded `T` typically erases to `Object`.
- `T extends Number` erases to `Number`.
- With multiple bounds, the erasure of `T` is based on the **first bound**.
- The compiler may insert casts and bridge methods.
- `List<String>` and `List<Integer>` share the same runtime class `ArrayList` if both are instantiated with `ArrayList`.

Create `SignatureRuntimeDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class SignatureRuntimeDemo {
    public static void main(String[] args) {
        List<String> strings = new ArrayList<>();
        List<Integer> integers = new ArrayList<>();

        System.out.println(strings.getClass() == integers.getClass());
        System.out.println(strings instanceof List<?>);
    }
}
```

Run:

```bash
javac SignatureRuntimeDemo.java
java SignatureRuntimeDemo
```

`stdout`:

```text
true
true
```

This does not invalidate the type relationships the compiler just checked. It only shows that ordinary runtime objects do not store `String`/`Integer` as separate type arguments for the JVM to check per collection.

Distinguish metadata of a **declaration** from type arguments of an **instance**. `Field.getGenericType()` can read generic signature metadata stored in a class file for a field; `new ArrayList<String>().getClass()` does not automatically return “ArrayList of String”. In APIs involving reflection or data serialization, developers sometimes pass `Class<T>`, `Type`, or a type token to carry extra type descriptions into runtime.

### Example of a Constraint Being Bypassed

```java
List<String> labels = new ArrayList<>();
List raw = labels;
raw.add(17);
String label = labels.get(0);
```

This snippet is for illustration only and must be placed inside a method with imports before running. `raw.add(17)` causes an unchecked warning yet passes the compiler; using `labels.get(0)` as a `String` can throw `ClassCastException` from the runtime cast. Trace back from the failing cast to the raw alias to find where the `List<String>` contract was broken. Using `javac -Xlint:rawtypes -Xlint:unchecked` helps surface dangerous paths.

## 15. Inference Mistakes When Reading Signatures

| Misreading | Why It Is Wrong | Correct Reading |
| --- | --- | --- |
| “`T` is a concrete class.” | `T` is a type variable declared in source. | Locate `<T>` and where the type argument is supplied/inferred. |
| “Two methods both writing `<T>` share the same T.” | Method scopes are independent. | Build a separate table for each method. |
| “`List<?>` is `List<Object>`.” | The wildcard protects an unknown element type. | Reading as `Object` is safe; arbitrary additions are forbidden. |
| “`<T extends Number>` and `<? extends Number>` are the same.” | One declares a named type parameter, the other uses a wildcard. | Check whether `<...>` is in declaration position or argument position. |
| “`List<Integer>` is a `List<Number>`.” | Generic type arguments are invariant by default. | Use `? extends Number` when only reading from the source. |
| “`? super Integer` allows reading directly as Integer.” | The actual list could be `List<Object>`. | The safe common read type is `Object`. |
| “A generic method must use `T` in its return type.” | `<T>` might only constrain parameters, or return `void`. | Track every position where `T` actually appears. |
| “`Map<K,V>.get` must take `K`.” | Specific APIs may declare `get(Object)`. | Check the member signature; do not guess from the container type. |
| “A `static` method in `Box<T>` automatically uses the class's T.” | Class-level `T` belongs to instance context; static has no instance-specific instantiation. | Declare `static <U> U ...` separately if needed. |
| “Values passed to the same T must have the exact same runtime class.” | Type inference can pick a suitable supertype. | Read compile-time constraints; do not equate with `getClass()` equality. |
| “`Collections.copy` appends lists.” | Type signatures do not describe full behavior. | Read the API contract for size/mutation/indexing rules. |
| “No runtime checks are needed because generics are used.” | Raw/unchecked/reflection/external data can violate the contract. | Validate data at boundaries and watch compiler warnings. |

## 16. Six-Step Process for Reading an Unfamiliar Signature

When encountering a signature in documentation or an IDE, process it in this order:

1. **Copy the full signature, keeping all `<...>` brackets intact.** Separate modifiers, class/method name, return type, and parameter list. Do not drop `extends`/`super` bounds.
2. **Mark every declaration site.** Note `class/interface/record <...>`, `method <...>`, `constructor <...>`; distinguish type-parameter lists from type-argument lists.
3. **Draw a ledger for each named type variable.** For `K`, `V`, `T`, `U`, record its bound (if any), and occurrences in parameters, return type, supertypes, and nested generics.
4. **Isolate wildcards separately.** Read `? extends X` as elements supplied under upper bound `X`; `? super X` as a consumer able to accept `X`; `?` as an unknown type. Then tie wildcards back to named type parameter `X` if present.
5. **Apply a concrete call site.** Write down `K=String`, `V=Integer` or an inferred solution `T=Integer`, `R=String`. Translate the signature into the types the caller sees; avoid thinking the JVM generates a new generic class.
6. **Separate type constraints from runtime behavior.** Signatures tell you which calls are type-valid; Javadoc or implementation bodies tell you about mutability, `null` handling, exceptions, copying, and ordering.

Only after completing all six steps should you begin optimizing or simplifying an API. Many bugs stem from skimming `T` and missing whether it was declared on the class or on the method.

## 17. Self-Check Practice Exercises

### Exercise 1 — Underline Declaration Sites

Given:

```java
class Store<K, V> {
    V get(K key) { return null; }
    <R> R convert(V value, java.util.function.Function<V, R> f) {
        return f.apply(value);
    }
}
```

Questions:

1. Where are `K`, `V`, and `R` declared?
2. With `Store<String,Integer>`, what does `get` accept and what does it return?
3. Can `convert` on this Store return `String`? What condition must `Function` satisfy?

Answers: `K,V` on the class; `R` on the `convert` method; `get` accepts `String` and returns `Integer`; `convert` can return `String` when passed a function matching type `Function<Integer,String>`. The illustrative `get` method currently returns `null`; the signature does not automatically provide actual storage.

### Exercise 2 — Locate Where Type Inference Acts

Given:

```java
static <T> java.util.List<T> one(T value) {
    return java.util.List.of(value);
}
```

Predict the expression types:

```java
java.util.List<String> a = one("X");
java.util.List<Integer> b = one(7);
```

Answers: `T=String` and `T=Integer` in the two invocations. `List.of` rejects `null` elements under its runtime contract; generic type `T` is not an automatic null-check.

### Exercise 3 — Distinguish Named Type Parameters from Wildcards

Given three signatures:

```java
static <T> T first(java.util.List<T> list)
static Object any(java.util.List<?> list)
static void receive(java.util.List<? super Integer> list)
```

Question: which signature links the return type to the element type; which only reads safely as `Object`; and which permits adding `Integer`? Answers: respectively `first`, `any`, `receive`. These are **extracted signatures** without bodies, so they do not compile on their own as standalone programs.

### Exercise 4 — Trace Nested Types

With `Map<String, List<Long>>`, deduce:

- `K=String`, `V=List<Long>`.
- `map.entrySet()` has type `Set<Map.Entry<String,List<Long>>>`.
- `entry.getValue()` has type `List<Long>`.
- `entry.getValue().get(0)` has type `Long`.

If you accidentally read `V=Long`, return to the step of reading from the outside in.

### Exercise 5 — Read a Method with Two Type Variables and a Bound

Given:

```java
static <T, U extends Comparable<? super U>>
java.util.Comparator<T> by(
        java.util.function.Function<? super T, ? extends U> extractor)
```

Ask which variable is the object being compared, which is the comparison key, where the bound sits, and what the return type is. Answers: `T` is the object type; `U` is the key type; `U` has bound `Comparable<? super U>`; the result is `Comparator<T>`. This signature mirrors the relationships of `Comparator.comparing`, without an implementation body.

## 18. Summary for Immediate Application

Whenever reading a generic signature, build a short map following this template:

```text
Definition:    <T, R extends SomeInterface> ...
Source of T:   class or method? Where does T appear?
Source of R:   class or method? What is R's bound?
Wildcard:      ? extends T / ? super T / ?
Call site:     What type is T, what type is R?
Result:        What expression type does the caller receive?
Runtime:       Does the signature promise mutation/null/order/validation?
```

Read `T` as **a relationship to trace**, not as the name of some arbitrary standalone type. Read `<T>` as a declaration site, `<String>` as a type argument when using a generic, and `<?>` as an unknown type argument. For class-level and method-level type parameters, always mark scope clearly; for long signatures, build the constraint table before inferring. Once you do that, you can go from `List<E>` to `Optional.map` or `Comparator.comparing` and accurately understand what the compiler is protecting.