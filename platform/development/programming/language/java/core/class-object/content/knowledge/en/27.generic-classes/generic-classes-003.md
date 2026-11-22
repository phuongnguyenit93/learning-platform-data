# Creating Objects with Type Arguments and the Diamond Operator (`<>`) — Java 17

## Objectives

When working with generic classes in Java, developers often encounter two ways to create an object that look nearly identical:

```java
Box<String> explicit = new Box<String>("Java");
Box<String> inferred = new Box<>("Java");
```

The first way **explicitly specifies the type argument** `String` in the `new` expression. The second way uses the **diamond operator `<>`** so the Java compiler **infers the type argument** based on the context and constructor arguments. Both are `Box` objects; the diamond does not create a special class or defer type resolution until runtime.

This lesson provides a complete guide to writing a generic class, passing type arguments when creating objects, target typing, diamond inference, the relationship with `var`, constructors, generic constructors, bounds, wildcards, invariance, collections, anonymous classes since Java 9, errors caused by raw types/unchecked conversions, type erasure, API extensibility, testing techniques, and Java 17 exercises. All examples are labeled **standalone program** or **illustrative snippet** so that intentionally broken code is not confused with runnable code.

**Key takeaways from the start:**

- `Box<T>`: **`T` is a type parameter** in the generic class declaration.
- `Box<String>`: **`String` is a type argument** when using the class.
- `new Box<String>(...)`: **explicitly** specifies the type argument at the object creation site.
- `new Box<>(...)`: uses the diamond to **infer** the type argument, not a raw type.
- `new Box(...)`: omitting all type arguments on a generic class is a **raw-type use**, completely different from the diamond; it can produce unchecked warnings and reduce type checking.
- Whether written explicitly or with the diamond, **Java generics are primarily checked at compile time and use type erasure at runtime**.

## 1. Declaring a generic class

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

Here `T` is a **type parameter**, declared in `class Box<T>`. Inside the class body, the compiler uses `T` as a type with certain bounds, not a `Class` object and not a String of the type name.

An instance can be used like this:

```java
Box<String> words = new Box<String>("hello");
Box<Integer> count = new Box<Integer>(17);
```

The compiler ensures:
- `words.get()` has compile-time type `String`.
- `count.get()` has compile-time type `Integer`.
- `new Box<String>(123)` does not match the constructor accepting `String`.
- You do not need to cast `words.get()` to String in the code that uses it.

**A generic class does not duplicate itself into a separate JVM class for each type.** Java applies type erasure to most generic type information at runtime.

## 2. Runnable: creating objects with explicit type arguments

Save **`ExplicitTypeArgumentsDemo.java`**:

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

public class ExplicitTypeArgumentsDemo {
    public static void main(String[] args) {
        Box<String> text = new Box<String>("Java");
        Box<Integer> number = new Box<Integer>(17);

        String a = text.get();
        Integer b = number.get();

        System.out.println(a);
        System.out.println(b);
        System.out.println(text.getClass() == number.getClass());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ExplicitTypeArgumentsDemo.java
java ExplicitTypeArgumentsDemo
```

Stdout:

```text
Java
17
true
```

The last line is important: at runtime, both objects have the same runtime class `Box`. The `String`/`Integer` difference is compile-time information that aids type checking; there are not necessarily two separate runtime classes.

## 3. Diamond operator syntax

Explicit form:

```java
List<String> names = new ArrayList<String>();
```

Diamond form:

```java
List<String> names = new ArrayList<>();
```

The `<>` syntax consists of **the two angle brackets of the generic type argument list without writing any type argument names between them**. The compiler infers the appropriate arguments based on the constraints from the expression, constructor arguments, and target type, if present.

Do not confuse this with:

```java
List names = new ArrayList();
```

The latter uses raw `List` and raw `ArrayList`, bypassing important type checking from generics.

**How to remember:** the diamond **asks the compiler to infer the types**, whereas a raw type **intentionally or unintentionally omits full generic type checking**.

## 4. Runnable: explicit and diamond produce the same result

Save **`DiamondBasicsDemo.java`**:

```java
final class Holder<T> {
    private final T item;

    Holder(T item) {
        this.item = item;
    }

    T item() {
        return item;
    }
}

public class DiamondBasicsDemo {
    public static void main(String[] args) {
        Holder<String> first = new Holder<String>("hello");
        Holder<String> second = new Holder<>("hello");

        System.out.println(first.item());
        System.out.println(second.item());
        System.out.println(first.item().equals(second.item()));
        System.out.println(first == second);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondBasicsDemo.java
java DiamondBasicsDemo
```

Stdout:

```text
hello
hello
true
false
```

`first` and `second` are two distinct objects created by two `new` expressions; the compiler does not share a single instance because they have the same generic type.

## 5. Distinguishing the three places where types are written

```java
class Pair<K, V> {
    Pair(K key, V value) {
    }
}
```

And:

```java
Pair<String, Integer> p =
        new Pair<String, Integer>("age", 20);
```

There are three levels of information:
1. `<K,V>` after the **class name in the declaration** are the **formal type parameters**.
2. `<String,Integer>` on the left of `p` is the **parameterized type** of the variable.
3. `<String,Integer>` on the right, after `new Pair`, are the **explicit type arguments** for creating the instance.

Replacing the right side with the diamond:

```java
Pair<String, Integer> p = new Pair<>("age", 20);
```

The compiler infers them. You have not removed generic typing from the object.

### Two type parameters can differ

`Pair<String,Integer>` differs from `Pair<Integer,String>` at compile time; `Pair<String,Integer>` is not automatically compatible with `Pair<Object,Object>`. This is the **invariance** of ordinary generic type arguments in Java.

## 6. Runnable: multiple type arguments

Save **`DiamondPairDemo.java`**:

```java
record Pair<K, V>(K key, V value) {
}

public class DiamondPairDemo {
    public static void main(String[] args) {
        Pair<String, Integer> first =
                new Pair<String, Integer>("age", 20);
        Pair<String, Integer> second =
                new Pair<>("height", 180);

        System.out.println(first);
        System.out.println(second.key());
        System.out.println(second.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondPairDemo.java
java DiamondPairDemo
```

Stdout:

```text
Pair[key=age, value=20]
height
180
```

The record `Pair<K,V>` in Java 17 is also a generic class. The record's constructor is associated with the components `K key` and `V value`. Diamond inference works for generic record class instance creation.

## 7. Diamond does not mean runtime automatically recognizes type arguments

If you write:

```java
Box<String> box = new Box<>("A");
```

the compiler determines the appropriate `T` at compile time. At runtime, the JVM does not “look at the String object and pick a Box<String> version” using a per-class specialization model.

Generic type information is typically erased:
- At runtime, `box.getClass()` is `Box.class`, not a `Box<String>.class`.
- `instanceof Box<String>` is invalid because a parameterized generic type is non-reifiable.
- `instanceof Box<?>` can be used to check the matching runtime shape, but it does not validate the type of the data inside.
- If you must validate the element type at runtime, pass an appropriate `Class<T>` or type token and check it explicitly.

`<>` is syntax for **compile-time inference**, not a runtime reflection feature.

## 8. Historical purpose and practical benefits

Before the diamond (added in Java 7), users of generic collections often repeated all the arguments:

```java
Map<String, List<Integer>> map =
        new HashMap<String, List<Integer>>();
```

With the diamond:

```java
Map<String, List<Integer>> map = new HashMap<>();
```

Benefits:
- Less repetition of long type names.
- Less chance of mistyping type arguments between the two sides.
- When changing the target type, you may only need to update the declaration side.
- Improves readability of generic constructors/collections.

However, the diamond is not an end in itself. If inference is unclear or a developer needs to see a specific type choice at the call site, **explicit type arguments remain completely valid**.

## 9. What is target typing?

Some Java expressions are **poly expressions**, meaning that type inference can be influenced by a **target type** in contexts such as an assignment, initializer, method invocation, or return statement.

Example:

```java
List<String> names = new ArrayList<>();
```

The target type `List<String>` provides a constraint for the compiler to infer the type argument `String` for `ArrayList`.

Another example:

```java
Box<Number> box = new Box<>(Integer.valueOf(7));
```

Even though the argument value has compile-time type `Integer`, the target type can cause the generic class type argument to be `Number`, provided all constraints are valid.

**Do not assume the compiler simply “looks at the object passed inside the parentheses” and always picks that object’s exact concrete class.** Inference combines target typing and applicability constraints according to JLS `18`.

## 10. Runnable: target type affects inference

Save **`DiamondTargetTypingDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondTargetTypingDemo {
    public static void main(String[] args) {
        Box<Number> number = new Box<>(Integer.valueOf(7));
        Box<String> word = new Box<>("Java");

        Number n = number.value();
        String s = word.value();

        System.out.println(n.intValue());
        System.out.println(s.length());
        System.out.println(n.getClass().getSimpleName());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondTargetTypingDemo.java
java DiamondTargetTypingDemo
```

Stdout:

```text
7
4
Integer
```

The static type of `n` is `Number`, while the object inside is an `Integer`. **Static generic type** and **runtime concrete object class** are two different layers of information.

## 11. Inference can rely on constructor arguments

If there is no specific target type, the compiler can infer from the argument passed to the constructor:

```java
var text = new Box<>("Java");
```

In Java 17, `var` infers the compile-time type of a local variable from its initializer expression. In this example, the argument `"Java"` allows inference toward `Box<String>`.

With:

```java
var count = new Box<>(42);
```

The argument `42` is a primitive `int`; generic type arguments must be reference types, so boxing enables inference involving `Integer`.

### Not runtime “automatic casting”

`var` is also compile-time local variable type inference, not dynamic typing. After the compiler infers the type of `text`, you are still subject to Java static type checking.

## 12. Runnable: diamond combined with `var`

Save **`DiamondVarDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondVarDemo {
    public static void main(String[] args) {
        var title = new Box<>("Java");
        var count = new Box<>(17);

        String word = title.value();
        Integer number = count.value();

        System.out.println(word.toUpperCase());
        System.out.println(number + 1);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondVarDemo.java
java DiamondVarDemo
```

Stdout:

```text
JAVA
18
```

If you change it to `var title = new Box<>(17)` and then try `String word = title.value()`, the compiler rejects it; `var` does not make assignment to an arbitrary type valid.

## 13. Diamond with a constructor that takes no arguments

Consider:

```java
class Bag<T> {
    Bag() {
    }
}
```

When writing:

```java
Bag<String> a = new Bag<>();
```

there is no constructor argument to indicate `T`. However, the target type `Bag<String>` is a constraint that helps the compiler infer `String`.

Conversely:

```java
var b = new Bag<>();
```

has no target parameterized type from `var`, nor any arguments constraining `T`. For a generic type parameter without other bounds, the compiler can infer `Object`.

### Major pitfall

Do not write `var list = new ArrayList<>()` and assume `list` is `ArrayList<String>` just because you plan to add Strings later. The variable already gets its static type from its **initializer**, independent of code that appears afterward.

## 14. Runnable: empty diamond and `var`

Save **`DiamondEmptyConstructorDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondEmptyConstructorDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");

        var mixed = new ArrayList<>();
        mixed.add("Java");
        mixed.add(17);

        System.out.println(names);
        System.out.println(mixed);
        System.out.println(mixed.get(1) instanceof Integer);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondEmptyConstructorDemo.java
java DiamondEmptyConstructorDemo
```

Stdout:

```text
[An]
[Java, 17]
true
```

In this example, `mixed` is inferred as `ArrayList<Object>` (no narrower bounds and no specific target context), so adding both a String and an Integer is valid. If the intention is a list that holds only Strings, write `List<String> mixed = new ArrayList<>()` or `var mixed = new ArrayList<String>()`.

## 15. `var` is not a replacement for every explicit type argument

Comparison:

| Syntax | Notable static type | Meaning |
| --- | --- | --- |
| `List<String> xs = new ArrayList<>();` | Variable of type `List<String>` | Clear target typing, interface abstraction |
| `var xs = new ArrayList<String>();` | `ArrayList<String>` | Inference of `var` from a parameterized expression |
| `var xs = new ArrayList<>();` | Typically `ArrayList<Object>` | No String constraint when the constructor is empty |
| `var xs = new ArrayList<>(List.of("A"));` | Inference based on the String source | Has a useful constructor argument |
| `List xs = new ArrayList();` | Raw `List` | Loses type checking for elements |

**Recommendation:** when a constructor takes no arguments and the element type matters, make the type explicit on **at least one side** of the declaration.

## 16. Diamond with collection constructors

Common classes:

```java
List<String> list = new ArrayList<>();
Set<Integer> numbers = new HashSet<>();
Map<String, Integer> counts = new HashMap<>();
Deque<String> queue = new ArrayDeque<>();
```

These are **snippets**; add `import java.util.*;` and calling code if you need them to be runnable.

Notes:
- `List`/`Set`/`Map`/`Deque` are interfaces and generally **cannot be instantiated directly via new**.
- `ArrayList`/`HashSet`/`HashMap`/`ArrayDeque` are concrete generic classes with suitable constructors.
- The diamond is attached to the **class being instantiated**, not the type of the variable on the left.
- Inference can produce a subtype-specific parameterization compatible with the target interface type.

### Can you write `new List<>()`?

No. `List` is an interface. The error comes from trying to instantiate an interface, **not** from the diamond. Choose an implementation such as `new ArrayList<>()`.

## 17. Runnable: collections with diamond

Save **`DiamondCollectionsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class DiamondCollectionsDemo {
    public static void main(String[] args) {
        List<String> names = new ArrayList<>();
        names.add("An");
        names.add("Binh");

        Map<String, Integer> scores = new HashMap<>();
        scores.put("An", 8);
        scores.put("Binh", 9);

        System.out.println(names);
        System.out.println(scores.get("An"));
        System.out.println(scores.get("Binh"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondCollectionsDemo.java
java DiamondCollectionsDemo
```

Stdout:

```text
[An, Binh]
8
9
```

The code does not print the entire `HashMap` directly to avoid accidentally depending on iteration order. `get(key)` explicitly returns the inserted values.

## 18. Invariance: `Box<Integer>` is not a subtype of `Box<Number>`

Even though `Integer extends Number`, the following two parameterized types do **not** have a subtype relationship in the way many people guess:

```java
Box<Integer> ints = new Box<>(7);

// Compile-negative:
// Box<Number> numbers = ints;
```

Ordinary Java generic classes are **invariant** in their type arguments. If that assignment were allowed, a caller could pass a Double through `Box<Number>` into a place where only Integer should be permitted (with a mutable Box), breaking type safety.

How to accept any Box containing a subtype of Number:

```java
Box<? extends Number> view = new Box<Integer>(7);
```

`? extends Number` is a wildcard with an upper bound; you can read a Number from it, but it cannot be treated as a place to freely write any Number because the underlying Box might be a Box<Integer>.

### The diamond still works with a wildcard target

```java
Box<? extends Number> view = new Box<>(7);
```

The compiler selects a parameterization compatible with the constructor arguments/target. The wildcard is in the **target type**; it does not mean you asked to create an object with runtime element class “?” or bypassed type safety.

## 19. Runnable: wildcard target and diamond

Save **`DiamondWildcardDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondWildcardDemo {
    public static void main(String[] args) {
        Box<? extends Number> number = new Box<>(7);
        Number n = number.value();

        System.out.println(n.intValue());
        System.out.println(number.value().getClass().getSimpleName());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondWildcardDemo.java
java DiamondWildcardDemo
```

Stdout:

```text
7
Integer
```

`? extends Number` allows a consumer to read a Number. It does not turn the wildcard into a concrete argument type that can be arbitrarily written after `new Box<? extends Number>`.

## 20. Bounded type parameters constrain inference

A generic class can require `T` to be a subtype of a class/interface:

```java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

`T extends Number` is a **bound**. The diamond must infer a type argument that satisfies that bound:

```java
NumericBox<Integer> a = new NumericBox<>(10);
NumericBox<Double> b = new NumericBox<>(2.5);
```

Invalid:

```java
// Compile-negative:
// NumericBox<String> c = new NumericBox<>("bad");
```

`String` does not extend Number. The diamond does not bypass bounds.

### A bound is type checking, not data coercion

Java does not automatically parse the String `"10"` into a Number to satisfy a bound. To convert data, call `Integer.parseInt` or a factory/constructor that takes a String and parses it according to its own contract.

## 21. Runnable: diamond preserves generic bounds

Save **`DiamondBoundsDemo.java`**:

```java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}

public class DiamondBoundsDemo {
    public static void main(String[] args) {
        NumericBox<Integer> count = new NumericBox<>(10);
        NumericBox<Double> price = new NumericBox<>(2.5);

        System.out.println(count.asDouble());
        System.out.println(price.asDouble());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondBoundsDemo.java
java DiamondBoundsDemo
```

Stdout:

```text
10.0
2.5
```

The compiler infers `Integer` and `Double` so that the `extends Number` constraint holds in both cases. The runtime `doubleValue()` operation is supported by the Number API.

## 22. Generic class parameters differ from generic constructor parameters

Consider:

```java
class Box<T> {
    <U extends Number> Box(T item, U initialCount) {
        // ...
    }
}
```

Here:
- `T` is the type parameter of the **class**.
- `U` is the type parameter of the **constructor itself**.
- Creating `new Box<String>("A", 3)`: `T=String` comes from the class type argument, while `U` can be inferred as Integer from the constructor argument `3`.
- `new Box<>("A", 3)`: the compiler must also infer the **class type argument** from the diamond along with the generic constructor's type variable.

**Do not confuse** `new Box<String>(...)` with **explicit type arguments of a generic constructor**; they appear in different syntactic positions and serve different purposes. The diamond `<>` after the class name is a way to infer the **class parameterization**.

### A non-generic constructor still accepts T

`Box(T item)` is not itself a generic constructor just because its parameter type is `T`. It uses the class type parameter already declared in `class Box<T>`.

## 23. Runnable: class type variable and constructor type variable

Save **`GenericConstructorDiamondDemo.java`**:

```java
final class Entry<T> {
    private final T value;
    private final Number weight;

    <U extends Number> Entry(T value, U weight) {
        this.value = value;
        this.weight = weight;
    }

    T value() {
        return value;
    }

    Number weight() {
        return weight;
    }
}

public class GenericConstructorDiamondDemo {
    public static void main(String[] args) {
        Entry<String> first = new Entry<>("A", 7);
        Entry<Integer> second = new Entry<>(42, 2.5);

        System.out.println(first.value() + ":" + first.weight());
        System.out.println(second.value() + ":" + second.weight());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 GenericConstructorDiamondDemo.java
java GenericConstructorDiamondDemo
```

Stdout:

```text
A:7
42:2.5
```

The compiler checks `T` for value and infers `U` bounded by Number for weight. It is not the same type variable governing both positions.

## 24. How do constructor overload resolution and the diamond interact?

Generic constructors of a generic class can be overloaded. When encountering `new Container<>(args)`, the compiler needs to consider:
1. Arguments of the `new` expression.
2. Applicable constructors (arity/types, widening, boxing, varargs).
3. Bounds and type inference variables.
4. The target type when the expression is a poly expression.
5. The most-specific overload and potential ambiguity.

Do not assume `<>` causes overloads to be chosen based on the **runtime class** of the arguments. The choice is determined at compile time.

### Null can cause ambiguity

If a class has `Container(String)` and `Container(Integer)`:
- `new Container<>("A")` selects String if valid.
- `new Container<>(1)` selects Integer if valid.
- `new Container<>(null)` can be ambiguous because String and Integer do not have a suitable subtype relationship.

Fixes include casting `(String) null` or using a named factory with clear semantics, rather than dropping the diamond for a raw type.

## 25. Compile-negative example: ambiguity between constructors

This is an **intentionally non-compiling snippet**:

```java
class Choice<T> {
    Choice(String label) { }
    Choice(Integer count) { }
}

Choice<Object> c = new Choice<>(null);
```

`null` matches both overloads. The compiler cannot choose a single most-specific constructor between String and Integer.

Fix:

```java
Choice<Object> c = new Choice<>((String) null);
```

Or design an API that does not require passing null to select semantics, such as `Choice.fromLabel(...)` and `Choice.fromCount(...)`.

**Takeaway:** the issue is **constructor overload ambiguity**, not the diamond itself.

## 26. Do not pass a primitive type as a generic type argument

Valid:

```java
Box<Integer> count = new Box<>(3);
Box<Double> price = new Box<>(2.5);
```

Invalid:

```java
// Compile-negative:
Box<int> primitive = new Box<int>(3);
```

Java generics use **reference types** as type arguments. Primitives such as `int`, `double`, and `boolean` cannot be written inside `<...>` as type arguments.

Autoboxing can convert an `int` argument to `Integer` when needed, but it does not create `Box<int>`.

### Costs to consider

Boxing creates/uses wrapper objects under certain conditions. For large primitive datasets where performance is sensitive, consider primitive arrays or specialized APIs such as `IntStream`. Do not choose a raw type to “optimize boxing”; raw types do not make Java generics support primitive type arguments.

## 27. Not every generic syntax after `new` is valid

The following are **compile-negative snippets**:

```java
// An interface cannot be instantiated:
List<String> a = new List<>();

// Invalid primitive type argument:
Box<int> b = new Box<int>(1);

// Cannot create an array of a generic parameterized type:
List<String>[] c = new List<String>[3];

// T is not a concrete class that can be directly instantiated with new:
class Factory<T> {
    T create() {
        return new T();
    }
}
```

Replace them with:
- `new ArrayList<>()` instead of `new List<>()`.
- `Integer` instead of `int`.
- `List<List<String>>` or a collection/typed-array strategy instead of generic array creation when appropriate.
- `Supplier<T>`, `Class<T>`/reflection, or a factory object when you must create a value of type T.

The diamond does not lift any of the fundamental constraints of Java generics.

## 28. A wildcard is not the same as the diamond

Both `?` and `<>` appear in generics documentation, yet the two mechanisms are completely different:

- `<>` after a generic class name in `new X<>(...)` is **diamond type inference**.
- `?` in `List<?>` is a **wildcard type argument**, representing an unknown element type with constraints.
- `? extends Number` and `? super Integer` describe read/write relationships from parameterized references.
- `?` does not represent a Java class that can be arbitrarily used as a concrete type when creating an object.

Example:

```java
List<? extends Number> source = new ArrayList<Integer>();
List<? super Integer> sink = new ArrayList<Number>();
```

With the diamond, you usually write it more concisely:

```java
List<? extends Number> source = new ArrayList<>();
List<? super Integer> sink = new ArrayList<>();
```

In special cases, constraints from the wildcard target and constructor arguments can yield inference results different from casual guesswork, so the compiler is the ultimate authority.

## 29. Runnable: PECS with explicit type arguments

Save **`WildcardBoxDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardBoxDemo {
    public static void main(String[] args) {
        List<? extends Number> source =
                new ArrayList<Integer>(List.of(1, 2));

        List<? super Integer> sink =
                new ArrayList<Number>();

        Number first = source.get(0);
        sink.add(3);
        sink.add(4);

        System.out.println(first.intValue());
        System.out.println(sink);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 WildcardBoxDemo.java
java WildcardBoxDemo
```

Stdout:

```text
1
[3, 4]
```

The **PECS** rule: Producer Extends, Consumer Super. This is a rule for using wildcard references; it is **different** from deciding whether to write `<>` or explicit type arguments in a new expression.

## 30. Diamond when passed to a method parameter

Target typing can also occur when creating an object directly as an argument to a method:

```java
static void printNames(List<String> names) {
    System.out.println(names);
}

printNames(new ArrayList<>());
```

This is a **snippet** inside an appropriate class/method. The compiler knows the method parameter requires `List<String>` and can use that constraint when inferring types for `new ArrayList<>()`.

Benefit: you are not required to declare an intermediate variable solely to specify the type argument when the context is already clear.

### However, method overloading can complicate inference

If two overloads have closely related parameterized types, constructor argument inference and method overload resolution interact, which can cause ambiguity or complex compiler diagnostics. When the source becomes hard to read, separate them:

```java
List<String> names = new ArrayList<>();
printNames(names);
```

An explicit type on an intermediate variable often helps both human readers and analysis tools.

## 31. Runnable: target type via a method parameter

Save **`DiamondMethodArgumentDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondMethodArgumentDemo {
    static void inspect(List<String> values) {
        values.add("Java");
        System.out.println(values);
    }

    public static void main(String[] args) {
        inspect(new ArrayList<>());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondMethodArgumentDemo.java
java DiamondMethodArgumentDemo
```

Stdout:

```text
[Java]
```

When compiling the method call, the parameter type `List<String>` helps constrain inference for the diamond creation expression.

## 32. Diamond in a return statement

Example:

```java
static List<String> makeNames() {
    return new ArrayList<>();
}
```

The target type of `return` is `List<String>`, helping the compiler infer the type arguments for `ArrayList`.

The same applies to:
- Generic record: `return new Pair<>(left,right);`.
- Value-holding class: `return new Box<>(value);`.
- Mapping: `return new HashMap<>();`.

**Do not assume every new expression is always a poly expression**. Java has specific rules for the diamond and target typing. Distinguish between standalone and poly contexts according to JLS 15.9 and JLS 18.

## 33. Runnable: target typing in return

Save **`DiamondReturnDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondReturnDemo {
    static List<String> makeNames() {
        return new ArrayList<>();
    }

    public static void main(String[] args) {
        List<String> names = makeNames();
        names.add("An");

        System.out.println(names);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondReturnDemo.java
java DiamondReturnDemo
```

Stdout:

```text
[An]
```

There is no need to write `new ArrayList<String>()`, because the method return type already declares `List<String>`.

## 34. Diamond and anonymous classes: changes since Java 9

Since Java 9, the diamond can be used when creating an **anonymous class** under valid inference conditions.

Java 17 allows:

```java
java.util.function.Supplier<String> supplier =
        new java.util.function.Supplier<>() {
            @Override
            public String get() {
                return "Java";
            }
        };
```

The compiler infers the type arguments for the `Supplier` interface, while the anonymous class implements `Supplier<String>`.

### Does this differ from Java 7 and Java 8?

Yes. Older versions did not allow using the diamond with anonymous class declarations; explicit type arguments had to be written at the `new` site. When reading older tutorials that state “the diamond cannot be used with anonymous classes,” check the version. For Java 17, that absolute claim is **no longer accurate**.

### Notable limitation

When using the diamond with an anonymous class, Java applies an additional rule to methods declared in the anonymous body: a non-private method must override/implement a method from the supertype. If you only want an internal helper, consider declaring it `private`, or use a suitable named implementation.

## 35. Runnable: diamond + anonymous implementation

Save **`DiamondAnonymousDemo.java`**:

```java
import java.util.function.Supplier;

public class DiamondAnonymousDemo {
    public static void main(String[] args) {
        Supplier<String> supplier = new Supplier<>() {
            @Override
            public String get() {
                return "hello";
            }

            private String helper() {
                return "internal";
            }
        };

        System.out.println(supplier.get());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondAnonymousDemo.java
java DiamondAnonymousDemo
```

Stdout:

```text
hello
```

`get()` is an overridden method of Supplier. `helper()` is private and does not affect the external contract. There is no need to depend on the compiler-generated name of the anonymous class.

## 36. Compile-negative: non-private extra method in a diamond anonymous body

This is an **intentionally invalid snippet**:

```java
import java.util.function.Supplier;

Supplier<String> supplier = new Supplier<>() {
    @Override
    public String get() {
        return "hello";
    }

    public String extra() {
        return "not an override";
    }
};
```

In an anonymous declaration using the diamond, `extra()` is non-private yet does not override/implement a method of Supplier, so Java 17 rejects it. Change it to `private String extra()` if it is only a helper, or write a named class when an extended API is needed.

**Distinction:** this issue does not mean all anonymous classes forbid new methods; this is a constraint **specific to anonymous classes using the diamond**. If explicit generic type arguments are used, the rules can differ.

## 37. Anonymous subclass of a generic class

Besides interfaces, you can create an anonymous subclass of a generic superclass:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

Holder<String> value = new Holder<>("Java") {
    @Override
    String value() {
        return super.value().toUpperCase();
    }
};
```

This is a valid **snippet** for Java 17 if placed in the same compilation context as class Holder. The constructor argument is passed to the superclass constructor, while the diamond infers the class type arguments at anonymous subclass creation.

Caveats:
- The generic superclass must allow subclassing; it must not be final.
- The superclass constructor must be accessible.
- An anonymous class does not declare its own named constructor in source code.
- Non-private methods in the diamond anonymous body are subject to the override rule mentioned above.
- Type argument information does not turn into a new runtime Class version for String.

## 38. Runnable: anonymous generic superclass with diamond

Save **`DiamondAnonymousSubclassDemo.java`**:

```java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondAnonymousSubclassDemo {
    public static void main(String[] args) {
        Holder<String> value = new Holder<>("java") {
            @Override
            String value() {
                return super.value().toUpperCase();
            }
        };

        System.out.println(value.value());
        System.out.println(value.getClass() == Holder.class);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondAnonymousSubclassDemo.java
java DiamondAnonymousSubclassDemo
```

Stdout:

```text
JAVA
false
```

The runtime class differs from `Holder.class` because this is an anonymous subclass instance. This is because the **anonymous class** creates a subtype, not because the diamond creates a generic class specialization.

## 39. Inferred type arguments must be denotable in the specified contexts

Java imposes conditions on **denotable types** and accessibility when inferring types for an anonymous class using the diamond. Some type inference results that are too complex or cannot be denoted under the language rules will cause compilation to fail.

An introductory lesson does not need to predict every capture/intersection type of JLS `18`. When encountering an error:
1. Check the compiler diagnostic with `javac --release 17`.
2. Add an explicit target type on the variable/argument.
3. Write explicit type arguments in `new Generic<Args>(...)` if that is clearer.
4. Replace the anonymous class with a named class or a lambda (if compatible with functional interface semantics).
5. Reduce overload ambiguity or wildcard nesting.

**Do not fix it with a raw type to “suppress” the warning/error**: a raw type can erase the type-safety benefits the compiler is trying to protect.

## 40. Raw types and unchecked warnings

Consider:

```java
List values = new ArrayList();
values.add("A");
values.add(12);
```

`List`/`ArrayList` here are raw types. The compiler can warn about unchecked operations when adding elements. Retrieving them in a context expecting String may result in a `ClassCastException` at runtime.

Compare:

```java
List<String> values = new ArrayList<>();
values.add("A");
// values.add(12); // Compile error.
```

The diamond preserves static type checking for `String`. Raw types forfeit most generic safety.

### Using compiler flags to inspect warnings

```bash
javac --release 17 -Xlint:rawtypes,unchecked -encoding UTF-8 RawExample.java
```

Specific warning messages may vary by JDK/build/line numbers; you should not treat the entire diagnostic output as fixed stdout.

## 41. Runnable: using diamond instead of raw types

Save **`DiamondTypeSafetyDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class DiamondTypeSafetyDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        words.add("Java");
        words.add("Generics");

        String first = words.get(0);

        System.out.println(first);
        System.out.println(words.size());
    }
}
```

```bash
javac --release 17 -Xlint:rawtypes,unchecked -encoding UTF-8 DiamondTypeSafetyDemo.java
java DiamondTypeSafetyDemo
```

Stdout:

```text
Java
2
```

In this valid example there is no raw/unchecked conversion; the lint flags help detect other places in a project where type safety may be lost.

## 42. When does heap pollution occur?

**Heap pollution** is a situation in which a variable of a parameterized type refers to an object that is not compatible with its declared parameterization, usually through raw/unchecked code or unsafe varargs.

The diamond **does not inherently create heap pollution**. Conversely, using raw types to bypass a generic compiler error makes it easy to put mistyped data into a collection and fail at the read site.

Illustrative example that compiles with an unchecked warning:

```java
import java.util.ArrayList;
import java.util.List;

List raw = new ArrayList();
raw.add(123);

List<String> strings = raw; // Unchecked conversion warning.
String text = strings.get(0); // Possible ClassCastException.
```

This is a **snippet** inside a valid scope. Do not treat a warning as normal in production code when a clear parameterized-type solution exists.

## 43. Type erasure: does `new Box<String>()` differ from `new Box<Integer>()` at runtime?

In standard Java generics, type arguments do not create a separate class at runtime:

```java
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(1);

System.out.println(a.getClass() == b.getClass());
```

The result is true for an ordinary `Box` (not anonymous subclasses). The two objects are **different**, but their runtime class identity is the same.

Consequences:
- You cannot write `Box<String>.class`.
- You cannot write `new T()` based solely on a generic parameter.
- You cannot rely on `instanceof Box<String>`.
- When runtime type validation is needed, pass in a `Class<T>` or an explicit factory/type token.
- Java still inserts casts/checks where needed to preserve type semantics after erasure.

`<>` does not make type arguments “disappear one more time”; type erasure is the general semantics of Java generics.

## 44. Runnable: type erasure does not lose the actual values

Save **`DiamondErasureDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class DiamondErasureDemo {
    public static void main(String[] args) {
        Box<String> text = new Box<>("A");
        Box<Integer> count = new Box<>(1);

        System.out.println(text.getClass() == count.getClass());
        System.out.println(text.value());
        System.out.println(count.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 DiamondErasureDemo.java
java DiamondErasureDemo
```

Stdout:

```text
true
A
1
```

Compile-time typing still yields `String` and `Integer` when calling `value()` on appropriately parameterized references.

## 45. Object creation vs. generic factory methods

Two syntaxes can produce similar results:

**Constructor + diamond:**

```java
List<String> names = new ArrayList<>();
```

**Generic factory method:**

```java
List<String> names = List.of();
```

`List.of` is a generic **method** and applies method type inference, not the diamond operator. In Java 17, `List.of()` returns an unmodifiable list; `new ArrayList<>()` creates a mutable ArrayList. Therefore, **choosing a different API means choosing different semantics**, not just syntax.

For Map:
- `new HashMap<>()` is mutable.
- `Map.of()` returns an unmodifiable map.
- `Map.copyOf(map)` creates an unmodifiable map from a source according to its contract.

Do not replace a constructor with a factory just to make it “shorter” if mutability, null allowance, ordering, performance, and ownership differ.

## 46. Runnable: List factory differs from a mutable list

Save **`FactoryVsDiamondDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class FactoryVsDiamondDemo {
    public static void main(String[] args) {
        List<String> mutable = new ArrayList<>();
        List<String> fixed = List.of("A", "B");

        mutable.add("C");

        System.out.println(mutable);
        System.out.println(fixed);

        try {
            fixed.add("D");
        } catch (UnsupportedOperationException error) {
            System.out.println("unmodifiable");
        }
    }
}
```

```bash
javac --release 17 -encoding UTF-8 FactoryVsDiamondDemo.java
java FactoryVsDiamondDemo
```

Stdout:

```text
[C]
[A, B]
unmodifiable
```

The factory API semantics differ from the constructor, even though both use generic type inference in different ways.

## 47. A generic constructor does not automatically create an object of a type argument

A generic wrapper:

```java
final class FactoryBox<T> {
    private final T value;

    FactoryBox(T value) {
        this.value = value;
    }
}
```

To automatically create an instance of T without an argument, you **cannot** write `new T()` because T is a type variable, not a concrete class token/constructor reference at runtime.

A clearer approach:

```java
static <T> T create(java.util.function.Supplier<T> factory) {
    return factory.get();
}
```

The caller can pass an appropriate constructor reference/lambda:

```java
java.util.ArrayList<String> list =
        create(java.util.ArrayList::new);
```

This snippet does not directly rely on `<>`; generic inference on the `create` method together with target typing of the method reference does the work.

**Separate the two questions:** “What static type do I want the object to have?” is different from “How do I actually allocate an object of type T at runtime?”.

## 48. Runnable: Supplier instead of `new T()`

Save **`GenericFactorySupplierDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

public class GenericFactorySupplierDemo {
    static <T> T create(Supplier<T> constructor) {
        return constructor.get();
    }

    public static void main(String[] args) {
        List<String> values = create(ArrayList::new);
        values.add("Java");

        System.out.println(values);
    }
}
```

```bash
javac --release 17 -encoding UTF-8 GenericFactorySupplierDemo.java
java GenericFactorySupplierDemo
```

Stdout:

```text
[Java]
```

You cannot replace the body of `create` with `return new T();`. Supplier supplies the behavior that constructs the concrete object.

## 49. Diamond with an interface reference: static API vs. implementation

```java
List<String> list = new ArrayList<>();
```

The static type of the variable is `List<String>`; the concrete class created is `ArrayList`. This is the approach of programming against an interface abstraction.

Conversely:

```java
var list = new ArrayList<String>();
```

The static type of `list` is `ArrayList<String>`. In a large API, this can cause callers to accidentally depend on methods available only on the concrete implementation.

**There is no single answer that is always right**. If the API/caller only needs List operations, declaring the interface type provides flexibility to swap implementations later. For very short-lived local variables or when concrete methods are needed, `var` can keep the code concise.

### Do not confuse target type with runtime object type

Even when the declared type is `List<String>`, the runtime instance is still `ArrayList` if created with `new ArrayList<>()`. The diamond does not instantiate the interface.

## 50. Diamond with nested generic types

Nested parameterized types can be used:

```java
Map<String, List<Integer>> grouped =
        new HashMap<>();
```

When adding values:

```java
grouped.put("A", new ArrayList<>());
grouped.get("A").add(1);
```

The compiler can infer the element type of the new ArrayList from the `put` method invocation/target argument type.

### Runnable

Save **`NestedDiamondDemo.java`**:

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class NestedDiamondDemo {
    public static void main(String[] args) {
        Map<String, List<Integer>> grouped =
                new HashMap<>();

        grouped.put("A", new ArrayList<>());
        grouped.get("A").add(1);
        grouped.get("A").add(2);

        System.out.println(grouped.get("A"));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NestedDiamondDemo.java
java NestedDiamondDemo
```

Stdout:

```text
[1, 2]
```

This is an example of nested type inference, yet it is quite clear because the map value type has already been declared as `List<Integer>`.

## 51. Common pitfalls when combining `<>` and `null`

```java
Box<String> a = new Box<>(null);
```

If the `Box(T)` constructor permits null, the compiler can infer `T=String` from the target type even though the null argument expression itself provides no concrete type.

Conversely:

```java
var b = new Box<>(null);
```

has no explicit target parameterized type. With an unbounded T, the inferred type can be `Object`; do not assume `String` simply because you intend to handle text.

If the class has multiple constructors accepting unrelated reference types, `null` can also make the constructor call ambiguous.

### Rules for readable code

- If a null value has domain meaning, specify the target type explicitly.
- Better yet, avoid null through validation or a factory.
- If `null` is passed to choose an overload, cast to a concrete reference type or revise the API to avoid ambiguity.
- Do not use a raw type to “solve” inference: it simply removes checks.

## 52. Runnable: null constrained by target type

Save **`NullDiamondDemo.java`**:

```java
final class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }
}

public class NullDiamondDemo {
    public static void main(String[] args) {
        Box<String> text = new Box<>(null);

        System.out.println(text.value() == null);
        System.out.println(text.getClass().getSimpleName());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 NullDiamondDemo.java
java NullDiamondDemo
```

Stdout:

```text
true
Box
```

The target type preserves the compile-time intent `Box<String>`, while the runtime class is still `Box`. Do not invoke a method on `text.value()` if it may be null.

## 53. Diamond and deeply nested type arguments

A declaration such as:

```java
Map<String, Map<Long, List<String>>> index =
        new HashMap<>();
```

is valid. The diamond only shortens the current **class instance creation**; it does not remove parameterizations from the target type.

If there are not enough constraints at the constructor argument or with `var`, the compiler may infer different types than a reader expects. In complex code, explicit generic types at method/field boundaries often help preserve the API contract.

### When are explicit type arguments preferable to the diamond?

- When you need to make an API guarantee visible right at the call site.
- When a compiler error is hard to understand due to nested inference.
- When mixed numeric types may infer a broad common supertype.
- When `var` and a no-arg constructor make the inferred type too broad.
- When you want reviewers to easily spot mutable vs. immutable collections, constructor overloads, and target contracts.

There is no rule to “always use the diamond” regardless of readability.

## 54. Method overloads cannot differ only by generic type arguments due to erasure

The following snippet is intentionally invalid:

```java
class BadOverload {
    void handle(java.util.List<String> strings) {
    }

    void handle(java.util.List<Integer> integers) {
    }
}
```

Both methods have the same erased signature corresponding to `handle(List)`, so Java does not allow overloading that differs only by generic type arguments in this way.

This is **not a flaw of the diamond**. If you encounter a compiler diagnostic due to generic erasure, change the overloaded API by using different method names, parameter types that genuinely differ after erasure, or an appropriately designed generic method.

Clear example:

```java
void handleStrings(List<String> strings) { ... }
void handleIntegers(List<Integer> integers) { ... }
```

The lines above are pseudocode snippets with abbreviated method bodies, not standalone Java programs.

## 55. Do not create a generic array with the diamond

```java
// Compile-negative:
List<String>[] rows = new ArrayList<>[5];
```

Java array creation does not support the diamond syntax `new ArrayList<>[5]`. Creating an array of a non-reifiable parameterized type is also restricted by generic array creation rules.

If you want a collection of collections:

```java
List<List<String>> rows = new ArrayList<>();
rows.add(new ArrayList<>());
```

This is usually a safer choice: an outer list manages a collection of inner lists, rather than forcing generic array creation that is difficult to type-check at runtime.

### The array `new String[5]` is still valid

Arrays and generic collections have different type rules. `String[]` is a reifiable array element type; `List<String>[]` cannot simply be created in an equivalent way.

## 56. A `Class<T>` token is a solution for runtime type requirements

If an API genuinely needs to guarantee that an object holds a runtime value of type T, it can accept a `Class<T>`:

```java
final class TypedBox<T> {
    private final Class<T> type;
    private final T value;

    TypedBox(Class<T> type, T value) {
        this.type = type;
        this.value = type.cast(value);
    }
}
```

`String.class` is the class token `Class<String>`. The token exists at runtime; the diamond by itself does not place a token into the object.

### Note on nested generics

`Class<List<String>>` cannot be written as `List<String>.class`. A Class token for the raw runtime `List.class` does not validate the type of every element in the list. To validate `List<String>`, you must inspect the elements or use an appropriate type-token framework.

## 57. Runnable: `Class<T>` with diamond

Save **`ClassTokenDiamondDemo.java`**:

```java
final class TypedBox<T> {
    private final Class<T> type;
    private final T value;

    TypedBox(Class<T> type, T value) {
        this.type = type;
        this.value = type.cast(value);
    }

    T value() {
        return value;
    }

    String typeName() {
        return type.getSimpleName();
    }
}

public class ClassTokenDiamondDemo {
    public static void main(String[] args) {
        TypedBox<String> text =
                new TypedBox<>(String.class, "Java");

        System.out.println(text.typeName());
        System.out.println(text.value());
    }
}
```

```bash
javac --release 17 -encoding UTF-8 ClassTokenDiamondDemo.java
java ClassTokenDiamondDemo
```

Stdout:

```text
String
Java
```

The class token has its own role: runtime validation/metadata. The diamond handles class type inference at compile time.

## 58. When refactoring constructor signatures, inference can change

Code today:

```java
Box<String> box = new Box<>("A");
```

When modifying class `Box` to add a constructor overload or generic bounds, the compiler may select a different overload, report ambiguity, or apply different inference constraints. Therefore:
- Each overload with its own contract must be tested.
- Do not rely on ambiguous inference when multiple `null` arguments are present.
- In public libraries, adding overloads can affect source compatibility.
- If you want distinct semantics, name factory methods explicitly.
- Use `javac --release 17 -Xlint:all` in CI where appropriate (without requiring every project to enable all warnings immediately).

The diamond is not a “black box that automatically picks the intended constructor”; the compiler selects according to static language rules.

## 59. Should you write explicit type arguments or diamond in real-world code?

**Generally prefer the diamond** when the target type is clear:

```java
List<String> names = new ArrayList<>();
Map<String, Long> prices = new HashMap<>();
Box<Integer> value = new Box<>(7);
```

**Prefer explicit type arguments** when inference could obscure intent:

```java
var names = new ArrayList<String>();
var box = new Box<Integer>(7);
```

**You can use `var` with the diamond** when the constructor argument clearly constrains the type:

```java
var box = new Box<>("hello");
```

**Avoid raw types:**

```java
Box box = new Box("hello");
```

### Expose the abstraction on the variable when appropriate

`List<String> names = new ArrayList<>()` can be a better choice than `var names = new ArrayList<String>()` if the rest of the code should depend on the List API rather than the ArrayList implementation.

## 60. Exercise 1 — Identify the type parameter

```java
class Cache<K, V> {
}
```

**Question:** Are `K`, `V` type parameters or type arguments?

**Answer:** Type parameters in the generic class declaration.

## 61. Exercise 2 — Explicit type arguments

```java
Cache<String, Integer> cache;
```

**Answer:** String and Integer are type arguments of the parameterized type `Cache<String,Integer>`.

## 62. Exercise 3 — Meaning of the diamond

```java
List<String> names = new ArrayList<>();
```

Does the compiler skip generic checking because `<>` is empty?

**Answer:** No. The compiler infers the type arguments matching the target; this differs from raw `new ArrayList()`.

## 63. Exercise 4 — Raw type

```java
List values = new ArrayList();
```

**Answer:** This is raw-type usage, not the diamond. It reduces compile-time element type checks and can produce warnings.

## 64. Exercise 5 — Type after `var`

```java
var names = new ArrayList<>();
```

There are no constructor arguments or target parameterized type. What type is `names` inferred as?

**Answer:** Typically `ArrayList<Object>` for ArrayList without narrower bounds.

## 65. Exercise 6 — Explicit type when using `var`

If you want var, but the list should hold only String:

```java
var names = new ArrayList<String>();
```

**Answer:** Valid; the inferred static type is `ArrayList<String>`.

## 66. Exercise 7 — Boxing

```java
var box = new Box<>(17);
```

In an unbounded Box accepting T, what type is T inferred toward?

**Answer:** `Integer` (boxed int), not `int` as a generic type argument.

## 67. Exercise 8 — Primitive generic argument

Is `Box<int> box = new Box<int>(1);` valid?

**Answer:** No. Generic type arguments must be reference types; use `Integer`.

## 68. Exercise 9 — Invariance

`Box<Integer> ints = new Box<>(7);`. Can it be assigned directly to `Box<Number>`?

**Answer:** No. `Box<Integer>` is not a subtype of `Box<Number>` due to invariance.

## 69. Exercise 10 — Wildcard

Can `Box<? extends Number> n = new Box<>(7);` read a `Number` from `n.value()`?

**Answer:** Yes, according to the upper bound; it should not be treated as a mutable Box that can accept any Number.

## 70. Exercise 11 — Generic bound

`NumericBox<T extends Number>`. Can you use `new NumericBox<String>("A")`?

**Answer:** No; String does not satisfy the Number bound, with or without the diamond.

## 71. Exercise 12 — Instantiating an interface

Does `List<String> xs = new List<>();` compile?

**Answer:** No. List is an interface; use a concrete implementation such as ArrayList.

## 72. Exercise 13 — Target typing

`List<String> xs = new ArrayList<>();`, with no elements passed. Where does the compiler get the String information from?

**Answer:** From the target type `List<String>` of the assignment.

## 73. Exercise 14 — Method argument

A method accepts `List<String>`, and the caller passes `new ArrayList<>()`. Can the diamond infer String?

**Answer:** Yes, when the method invocation and constraints match; the target parameter type participates in inference.

## 74. Exercise 15 — Return context

A method declares `List<String> create()` and returns `new ArrayList<>()`.

**Answer:** Valid; the return target type assists inference.

## 75. Exercise 16 — Separate generic constructor

`class Entry<T> { <U extends Number> Entry(T value,U weight){} }`.

**Answer:** T belongs to the class; U belongs to the constructor. The diamond on `Entry` resolves the class type argument T, and constructor inference resolves U according to the corresponding rules.

## 76. Exercise 17 — Null and target

`Box<String> box = new Box<>(null);`, where constructor Box(T) allows null.

**Answer:** Can be valid; the target `Box<String>` guides T=String despite the null argument.

## 77. Exercise 18 — Null and overloads

Both `Choice(String)` and `Choice(Integer)` exist, and `new Choice<>(null)` is called.

**Answer:** It can be ambiguous; cast `(String)null` or use a named factory.

## 78. Exercise 19 — Runtime class

Do `new Box<String>("x")` and `new Box<Integer>(1)` have separate runtime classes for the two type arguments?

**Answer:** No, under normal Java generics erasure; both instances have runtime `Box.class`.

## 79. Exercise 20 — `instanceof` with a parameterized type

Is `obj instanceof Box<String>` valid?

**Answer:** No, because `Box<String>` is not a reifiable type in an instanceof check with this syntax. Use `Box<?>` if you only want to check for a matching raw runtime class.

## 80. Exercise 21 — Generic array

Is `new List<String>[3]` valid?

**Answer:** No; generic array creation is forbidden by Java for non-reifiable parameterized element types.

## 81. Exercise 22 — `new T()`

Is `class Factory<T> { T create(){ return new T(); } }` valid?

**Answer:** No. The type variable T does not directly provide a concrete constructor/runtime class; use a Supplier/factory.

## 82. Exercise 23 — Anonymous diamond since which Java version?

Is the syntax `new Supplier<>() { @Override public String get(){return "A";} }` supported in Java 17?

**Answer:** Yes, the diamond in an anonymous class has been allowed since Java 9 with appropriate restrictions.

## 83. Exercise 24 — Custom anonymous method

In a diamond anonymous class, can you add a completely new public method that does not override/implement anything?

**Answer:** No, in contexts governed by the Java 17 rules; non-private methods must override/implement appropriate supertype methods. Use a private helper or a named class.

## 84. Exercise 25 — Anonymous subclass runtime

Does `new Holder<>("A") { @Override String value(){...} }` have a runtime class equal to `Holder.class`?

**Answer:** No. This is an anonymous subclass; its runtime class is different. The difference is due to the anonymous subclass declaration, not the diamond.

## 85. Exercise 26 — `List.of` and `new ArrayList<>()`

Both expressions use generic type inference, but do they provide the same mutability semantics?

**Answer:** No. `List.of` produces an unmodifiable list per the JDK contract; ArrayList is mutable.

## 86. Exercise 27 — Nested generics

In `Map<String,List<Integer>> map = new HashMap<>();`, do you need to repeat `<String,List<Integer>>` after HashMap?

**Answer:** No, when the compiler can infer it from the target type; the diamond helps avoid repetition.

## 87. Exercise 28 — Generic erasure overload

Can you overload `handle(List<String>)` and `handle(List<Integer>)` in the same class?

**Answer:** No; both erase to `handle(List)` and collide in signature.

## 88. Exercise 29 — Class token

Does the diamond automatically carry a `Class<String>` runtime token into the object?

**Answer:** No. If a runtime type token is needed, explicitly pass `String.class`/a factory or an appropriate type-token abstraction.

## 89. Exercise 30 — Choosing the optimal syntax

You need an empty list of Strings, the API only operates on List, and the code must be type-safe and clear.

**Answer:** `List<String> values = new ArrayList<>();` is a common choice. Do not use raw `List` or `var values = new ArrayList<>()` if you want the String element type to be explicit from the start.

## 90. Exercise 31 — Purpose of the target type

`Box<Number> box = new Box<>(Integer.valueOf(3));`. Why shouldn't you always assume T=Integer?

**Answer:** The target type `Box<Number>` also participates in constraints; the compiler can infer a parameterization compatible with Number, while the runtime value remains Integer.

## 91. Exercise 32 — Reading compiler diagnostics

The compiler reports that type inference failed on `new Pair<>(...)` with wildcards and complex overloads.

**Answer:** Check constructor overloads/bounds/target; extract an intermediate variable, write explicit type arguments, or revise the API. Do not rush to switch to raw types or unchecked casts.

## 92. Exercise 33 — True/False Questions

1. `<>` is a raw type.
2. `new Box<String>("A")` explicitly specifies the class type argument.
3. Diamond inference depends only on the runtime class of the object passed in.
4. `var xs = new ArrayList<>()` always infers String because of the variable name xs.
5. Type arguments of generics can use the primitive `int`.
6. `Box<Integer>` is not automatically a subtype of `Box<Number>`.
7. `List<String> xs = new ArrayList<>()` is parameterized and type-safe.
8. Java 17 allows the diamond with anonymous classes under valid conditions.
9. `new T()` is valid when T is a generic type variable.
10. Two Boxes with different type arguments can have the same runtime class due to erasure.
11. `List.of()` and `new ArrayList<>()` always have the same mutability.
12. Bounded generic type inference must satisfy the bounds.

**Answer:** 1 false; 2 true; 3 false; 4 false; 5 false; 6 true; 7 true; 8 true; 9 false; 10 true; 11 false; 12 true.

## 93. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Treating `new Box<>()` as a raw type | Misunderstanding compiler inference | Distinguish from `new Box()` |
| Treating the diamond as a runtime dynamic type | Wrong expectations for type validation/runtime classes | Understand static inference + erasure |
| `var xs = new ArrayList<>()` and assuming String | Inference widens to Object | `var xs = new ArrayList<String>()` or `List<String> xs = new ArrayList<>()` |
| `new List<>()` | Cannot instantiate interface | `new ArrayList<>()` |
| `new Box<int>()` | Invalid primitive type argument | Use Integer |
| `Box<Number> x = new Box<Integer>(1)` | Generic invariance | Create `new Box<Number>(1)` or wildcard when reading |
| `new T()` | T is erased and is not a concrete type | Supplier/Factory/Class token |
| `new List<String>[3]` | Generic array creation error | List of lists or valid array design |
| `new Box<>(null)` and expecting String without target | Type inference may widen or overloads may be ambiguous | Target/explicit type/cast/factory |
| Assuming `Supplier<>` anonymous is always forbidden | Applying Java 7/8 rules to Java 17 | Check Java 9+ support/constraints |
| Non-private new method in anonymous diamond | May be rejected by the compiler | Private helper/override/named class |
| Using raw to bypass bounds errors | Loses type safety/unchecked warnings | Fix actual generic constraints |
| Thinking `<>` has runtime `Class<T>` | Cannot runtime-validate T as desired | Pass Class token separately |
| Treating factory `List.of` like ArrayList constructor | Confuses immutable/unmodifiable/mutable behavior | Read the API contract |
| Overloading methods differing only by `List<String>`/`List<Integer>` | Erasure signature clash | Change method names or API design |
| Not testing inference after changing constructors | Different source compatibility/overload behavior | Compiler/CI tests with the exact JDK release |

## 94. Code review checklist

- [ ] Generic class declares the formal type parameters and bounds properly.
- [ ] Explicit type arguments are used at appropriate `Class<Type>` positions.
- [ ] The diamond is written accurately as `<>` at class instance creation.
- [ ] Raw `new Generic()` is not confused with diamond `new Generic<>()`.
- [ ] The target type is clear when constructor arguments are insufficient for inference.
- [ ] If `var` is used with a no-arg diamond, the expected inferred type has been confirmed.
- [ ] If `var` is used with arguments, the inferred class/element type is checked.
- [ ] No primitive type is passed as a generic type argument.
- [ ] Generic bounds are satisfied by the chosen type arguments.
- [ ] Invariance `Generic<Sub>` vs. `Generic<Super>` is not violated.
- [ ] Wildcards `extends`/`super` are chosen according to producer/consumer behavior.
- [ ] Wildcard `?` is not confused with diamond `<>`.
- [ ] Constructor overloads are not ambiguous with `null`.
- [ ] Static types of arguments and target context are considered, rather than relying on the runtime class.
- [ ] Interfaces/abstract classes are not instantiated directly when invalid.
- [ ] `new T()` is not used without a factory/runtime type mechanism.
- [ ] No array of a non-reifiable parameterized type is created.
- [ ] Generic type arguments are not used with the expectation of runtime subclass specialization.
- [ ] Non-reifiable `instanceof Generic<String>` is not used.
- [ ] If runtime validation is needed, an appropriate Class token/checked mapper is present.
- [ ] Generic constructor type variables and generic class type variables are distinguished.
- [ ] Diamond with an anonymous class adheres to Java 9+ restrictions.
- [ ] Non-private methods in an anonymous diamond body actually override/implement.
- [ ] If an anonymous class is chosen, subclass access, constructor, and maintainability have been considered.
- [ ] If raw types are used due to a legacy API, warnings/unchecked casts are isolated and verified.
- [ ] No heap pollution occurs from uncontrolled raw assignments.
- [ ] Collections choose constructors or factories with contract-matching mutability/ownership.
- [ ] For mutable collections, defensive copying has been considered if required.
- [ ] Method parameter/return target typing does not make API overloading confusing.
- [ ] If inference is hard to read, explicit types are added at boundaries or local variables.
- [ ] Methods are not overloaded differing only by generic args whose signatures collide after erasure.
- [ ] Code does not depend on generated runtime class names to determine a type argument.
- [ ] Source builds/tests use `javac --release 17`.
- [ ] Every runnable example has a file name matching its public class and deterministic stdout.
- [ ] Compile-negative snippets are clearly distinguished.
- [ ] API consumers are checked when adding/modifying constructor overloads/generic bounds.

## 95. Summary

**When creating a generic object in Java 17**, you can explicitly write the type argument:

```java
Box<String> a = new Box<String>("A");
```

or use the diamond for the compiler to infer it:

```java
Box<String> b = new Box<>("B");
```

The diamond is appropriate when the context already provides sufficient constraints, such as a target type `List<String>`, constructor arguments, or a method return/argument context. However, with `var` and an empty constructor, inference may select a broad type such as Object, so the type should be made explicit if the intent is not obvious.

**An essential distinction:** `new Box<>()` is **not** raw `new Box()`. Generics and type checking remain active. The diamond also does not restore concrete type arguments at runtime after erasure, does not allow primitive type arguments, does not bypass bounds, does not instantiate interfaces, and does not permit `new T()`.

For anonymous classes, Java 17 supports the diamond according to the rules since Java 9, along with notable restrictions on non-private methods. For collections/factories, always consider type safety, mutability, and API semantics rather than focusing solely on shorter syntax.

**How to remember:** `<>` means **“compiler, infer valid type arguments from the existing constraints”**; it does not mean **“skip generic typing”** or **“let the runtime guess the type”**.

## Java SE 17 Authoritative References

- **JLS `15.9 — Class Instance Creation Expressions`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9
- **JLS `15.9.1 — Determining the Class being Instantiated`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.1
- **JLS `15.9.3 — Choosing the Constructor and its Arguments`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.3
- **JLS `15.9.5 — Anonymous Class Declarations`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.9.5
- **JLS `18 — Type Inference`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-18.html
- **JLS `4.5 — Parameterized Types`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5
- **JLS `4.8 — Raw Types`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8
- **JLS `4.6 — Type Erasure`**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6
