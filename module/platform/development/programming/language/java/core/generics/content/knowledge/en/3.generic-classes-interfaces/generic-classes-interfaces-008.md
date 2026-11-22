# Distinguishing a Generic Declaration from Each Use of That Type

In Java Generics, **declaring a generic type** and **using that generic type with a concrete type argument** are two different things. When we write `class Box<T>`, we define a type-contract template parameterized by `T`. When we write `Box<String>` or `Box<Integer>`, we use that same template in two differently type-checked ways.

Recognizing this distinction helps you read `<T>`, `<String>`, and `<>` accurately, know where a type parameter is declared versus where a type argument is supplied, and avoid mistakenly thinking Java creates a brand-new JVM class on every generic use.

## 1. One Generic Declaration Can Be Used in Many Ways

The following class definition only needs to be written **once**:

```java
public final class Box<T> {
    private final T value;

    public Box(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }
}
```

This is the entire content of `Box.java`. `T` is a **type parameter** declared in the class header: `Box<T>`. It represents an unfixed reference type in the declaration. Every use of `T` in the field, constructor, or getter refers to that class's type parameter.

In calling code, we can write:

```java
Box<String> title = new Box<>("Java");
Box<Integer> year = new Box<>(2026);
Box<Double> ratio = new Box<>(0.75);
```

These are three **uses** of the single `Box<T>` declaration. In each *parameterized type*:

- `Box<String>`: `String` is the **type argument** corresponding to `T`.
- `Box<Integer>`: `Integer` is the type argument corresponding to the same `T` position.
- `Box<Double>`: `Double` is another type argument; Java does not require creating a new class declaration just to change the stored data type.

The lines above are a code snippet **inside a method** and require `Box.java` in the same compilation unit/directory. The result of `title.get()` has static type `String`, while `year.get()` has static type `Integer`.

| Element | Generic Declaration | A Use of Generics |
|---|---|---|
| Example | `class Box<T>` | `Box<String>` |
| Role in program | Defines the reusable class and type contract | Specifies how to view a generic type at a use site |
| Name inside angle brackets | `T` is a **type parameter** | `String` is a **type argument** |
| Where does it appear? | Declaration of a generic `class`, `interface`, or `record` | Variable type, parameter, return type, `new`, parameterized supertype, etc. |
| How many times written | One declaration can serve many places | The same generic type can be used with many different arguments |
| Type checking | Describes relationships among positions using `T` | The compiler applies those relationships to the chosen type argument |

**Key takeaway:** `Box<T>` is a **declaration** when writing `class Box<T>`. `Box<String>` is **a parameterized type** when using that class. Do not call every sequence inside `<...>` a "generic declaration."

## 2. Reading Four Easily Confused Forms Correctly

### 2.1. `class Box<T>`: Declaring a Type Parameter

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T` is **introduced** for the first time in the class declaration. Inside this class, the compiler recognizes `T` as a valid type parameter and allows using it in corresponding instance members.

If `T` were consistently replaced with the name `E` throughout the declaration, the meaning would essentially stay unchanged. Names like `T`, `E`, `K`, and `V` are merely readable naming conventions, not special keywords.

### 2.2. `Box<String>`: Using a Concrete Type Argument

```java
// Illustrative snippet placed in a method body:
Box<String> message;
```

This line **declares a variable** `message` of type `Box<String>`; it **does not declare a new generic class** and has not yet created an object because there is no `new`.

`String` is an existing type. It is passed in the type argument position, while the name `T` does not need to appear at the use site.

### 2.3. `new Box<String>("hello")`: Instantiating with an Explicit Type Argument

```java
// Illustrative snippet placed in a method body:
Box<String> message = new Box<String>("hello");
```

The two `<String>` positions have related yet distinct roles: the left expresses the reference variable's type, while the right specifies the type for the object creation expression.

`"hello"` inside parentheses is a **value argument to the constructor**, not a type argument. If the constructor accepts `T`, then when `T` corresponds to `String`, the value argument must have a type compatible with `String`.

### 2.4. `new Box<>("hello")`: Instantiating with Diamond

```java
// Illustrative snippet placed in a method body:
Box<String> message = new Box<>("hello");
```

The empty `<>` is the **diamond operator**. It tells the compiler to infer the type argument of the `new` expression from the context and constructor arguments. Here the target type `Box<String>` lets it infer `String`.

**Diamond does not mean the declared class no longer has type parameters.** `Box` is still a generic class declared as `Box<T>`; Java merely shortens how type arguments are specified at the use site.

## 3. A Runnable Example: One Declaration, Multiple Uses

Save as **`GenericDeclarationDemo.java`**:

```java
import java.util.List;

public class GenericDeclarationDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> language = new Box<>("Java");
        Box<Integer> quantity = new Box<>(12);
        Box<List<String>> topics = new Box<>(List.of("type", "generic"));

        String text = language.get();
        Integer count = quantity.get();
        List<String> names = topics.get();

        System.out.println(text.toUpperCase());
        System.out.println(count + 3);
        System.out.println(String.join(" / ", names));
        System.out.println(language.getClass() == quantity.getClass());
    }
}
```

Run with JDK 17 or later:

```bash
javac -encoding UTF-8 GenericDeclarationDemo.java
java GenericDeclarationDemo
```

Exact output of the program:

```text
JAVA
15
type / generic
true
```

Explanation:

1. There is only **one definition** of the nested class `Box<T>`.
2. `Box<String>` requires the getter to be used as returning `String`.
3. `Box<Integer>` requires the getter to be used as returning `Integer`. When evaluating `count + 3`, Java automatically unboxes the `Integer` value to `int`.
4. `Box<List<String>>` uses a **nested parameterized type** as the type argument; `T` corresponds to the entire `List<String>`.
5. The `getClass()` comparison evaluates to `true`: both objects still share the same runtime class `GenericDeclarationDemo.Box`. This is consistent with **type erasure** and does not contradict the compiler checking different uses separately.

No step requires creating separate `StringBox`, `IntegerBox`, or `ListBox` classes.

## 4. One Generic Declaration, Multiple Static Types in Calling Code

Distinguish between **the static type of a variable** and **the runtime class of an object**:

```java
// Illustrative snippet inside a method, assuming class Box<T> exists:
Box<String> a = new Box<>("A");
Box<Integer> b = new Box<>(5);
```

At compile time, `a` has type `Box<String>` while `b` has type `Box<Integer>`. Therefore:

```java
String first = a.get();
Integer second = b.get();

// Integer wrong = a.get(); // Compile error: String cannot be assigned to Integer
// String wrong2 = b.get(); // Compile error: Integer cannot be assigned to String
```

The erroneous lines above are commented out to illustrate compiler behavior. Changing the type argument changes **the Java source-level type contract** that callers are permitted to invoke.

However, at runtime, both `a` and `b` are instances of the `Box` class. The difference between `Box<String>` and `Box<Integer>` does not mean the JVM loads two independent class definitions.

Another important point: **declaring a variable is not creating an object**.

```java
// Declaring a local variable only:
Box<String> emptyReference;

// Creating an object and assigning the reference:
Box<String> initialized = new Box<>("ready");
```

The local variable `emptyReference` has not been assigned, so it cannot be read before assignment even though the type `Box<String>` is completely valid. When using generics, distinguish type syntax, variable declaration syntax, and actually invoking a constructor.

## 5. Declaring Multiple Type Parameters and Using Them in Position

A generic type does not have to have only one parameter:

```java
final class Pair<K, V> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() {
        return key;
    }

    V value() {
        return value;
    }
}
```

In the **declaration** `Pair<K, V>`, `K` and `V` are two distinct type parameters. At **use sites**:

```java
// Illustrative snippet inside a method:
Pair<String, Integer> stock = new Pair<>("book", 10);
Pair<Integer, String> directory = new Pair<>(404, "Not Found");
```

With `Pair<String, Integer>`, `K = String` and `V = Integer`. With `Pair<Integer, String>`, the positions are swapped. The compiler does not automatically treat those two uses as equivalent.

| Usage | `K` Corresponds To | `V` Corresponds To | Type of `key()` | Type of `value()` |
|---|---|---|---|---|
| `Pair<String, Integer>` | `String` | `Integer` | `String` | `Integer` |
| `Pair<Integer, String>` | `Integer` | `String` | `Integer` | `String` |
| `Pair<String, String>` | `String` | `String` | `String` | `String` |

The **number and order** of type arguments must match the declaration. You cannot use `Pair<String>` if `Pair` requires two type parameters, nor can you form `Pair<String, Integer, Long>` from this declaration.

### Complete Example for `Pair<K, V>`

Save the file **`PairUsageDemo.java`**:

```java
public class PairUsageDemo {
    static final class Pair<K, V> {
        private final K key;
        private final V value;

        Pair(K key, V value) {
            this.key = key;
            this.value = value;
        }

        K key() { return key; }
        V value() { return value; }
    }

    public static void main(String[] args) {
        Pair<String, Integer> stock = new Pair<>("book", 10);
        Pair<Integer, String> code = new Pair<>(404, "Not Found");

        System.out.println(stock.key() + "=" + stock.value());
        System.out.println(code.key() + ": " + code.value());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 PairUsageDemo.java
java PairUsageDemo
```

`stdout`:

```text
book=10
404: Not Found
```

This continues to be **one declaration** `Pair<K, V>` with two uses having different type argument orders.

## 6. Generic Interface Declarations and Ways to Implement and Use Them

Interfaces can also declare type parameters:

```java
interface Reader<T> {
    T read();
}
```

`Reader<T>` is a **generic interface declaration**. The following types are **uses**:

```java
// Illustrative snippet in class declarations:
final class StringReader implements Reader<String> {
    @Override
    public String read() {
        return "Java";
    }
}

final class IntegerReader implements Reader<Integer> {
    @Override
    public Integer read() {
        return 21;
    }
}
```

`StringReader` fixes `Reader`'s type argument to `String`, while `IntegerReader` fixes it to `Integer`. Both implement **the same declaration** `Reader<T>` under two different type contracts.

Another class can remain generic:

```java
final class FixedReader<T> implements Reader<T> {
    private final T value;

    FixedReader(T value) {
        this.value = value;
    }

    @Override
    public T read() {
        return value;
    }
}
```

Here `FixedReader<T>` **declares the class's own type parameter** and **forwards that type parameter** to the `Reader<T>` interface. Call sites choose:

```java
// Illustrative snippet inside a method:
Reader<String> title = new FixedReader<>("Java");
Reader<Integer> age = new FixedReader<>(20);
```

Therefore, distinguish three cases:

- `interface Reader<T>`: **declares** a generic interface.
- `class StringReader implements Reader<String>`: a normal class **using** the interface with a concrete type argument.
- `class FixedReader<T> implements Reader<T>`: a **new generic class declaration**, while simultaneously using the generic interface via the class's type parameter.

Keeping the name `T` on both the class and the interface does not mean they automatically share a pre-existing type variable. Each declaration has its own type parameter scope; the `implements Reader<T>` clause specifies how the new class links its type parameter to the interface.

## 7. Declaring a Generic Method Also Differs from Calling That Method

Generics is not limited to classes and interfaces. A **generic method** declares its own type parameter at the start of its signature:

```java
static <T> T echo(T value) {
    return value;
}
```

`<T>` before the return type is the **method's type parameter declaration**. The following calls are **uses** of the same method:

```java
// Example inside a method of the class containing echo:
String text = echo("Hi");
Integer number = echo(9);
```

The compiler infers `T = String` for the first call and `T = Integer` for the second. No new method definition is created in source code on each call.

When needed, you can **specify the explicit type argument** right before the method name:

```java
String text = GenericMethodDemo.<String>echo("Hi");
```

This syntax differs from the object creation syntax `new Box<String>(...)`. A `static` method cannot directly grab a generic class's type parameter, so it usually needs to declare its own `<U>` or `<T>`.

### Runnable Program

Save as **`GenericMethodDemo.java`**:

```java
public class GenericMethodDemo {
    static <T> T echo(T value) {
        return value;
    }

    static final class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        static <U> Holder<U> of(U value) {
            return new Holder<>(value);
        }
    }

    public static void main(String[] args) {
        String a = echo("Java");
        Integer b = GenericMethodDemo.<Integer>echo(17);
        Holder<String> c = Holder.of("Generics");

        System.out.println(a);
        System.out.println(b + 1);
        System.out.println(c.get());
    }
}
```

Run:

```bash
javac -encoding UTF-8 GenericMethodDemo.java
java GenericMethodDemo
```

`stdout`:

```text
Java
18
Generics
```

Reading the positions:

- `class Holder<T>`: declares the **class's** type parameter.
- `static <U> Holder<U> of(U value)`: declares the **static method's** own type parameter.
- `Holder<String> c`: uses the **class** with type argument `String`.
- `Holder.of("Generics")`: uses the **method**; the compiler infers `U` from the argument and context.

## 8. Type Boundaries: One Use Cannot Arbitrarily Become Another Use

A major misconception is thinking `Box<String>` is a subtype of `Box<Object>` because `String` is a subtype of `Object`. Java generics are **invariant** by default:

```java
// Example placed in a method, assuming Box<T> is declared:
Box<String> strings = new Box<>("hello");

// Box<Object> objects = strings; // Does not compile
```

Even though both variables reference parameterizations of the same `Box` class, Java disallows that assignment. If allowed, APIs with `Object`-typed write operations could place non-string objects into a box promised to hold `String`.

For collections, the consequence is even clearer:

```java
import java.util.ArrayList;
import java.util.List;

// Illustrative snippet inside a method:
List<String> names = new ArrayList<>();
names.add("An");

// List<Object> values = names; // Does not compile
```

If `List<Object> values = names` were permitted, `values.add(123)` would break the `List<String>` contract that `names` must preserve. That is precisely why the compiler blocks the assignment immediately.

### Wildcards Used When a Concrete Type Argument Is Unknown

A method that **only reads** the value inside a box can accept:

```java
// Placed inside a class where Box<T> is available:
static void print(Box<?> box) {
    System.out.println(box.get());
}
```

`Box<?>` is still **a use** of the `Box` type, except the type argument is a wildcard denoting an unknown type. It does not declare a type parameter named `?`, and does not assert that the inner value is `String` or `Integer`.

Both calls `print(new Box<>("A"))` and `print(new Box<>(5))` are valid. Because the concrete type is unknown, the read result can safely be used as `Object`. If an API needs to preserve type relationships across multiple parameters and the return value, a generic method `<T>` with its own type parameter name can express that relationship more clearly.

**Distinguish:** `Box<T>` can be a valid use **inside a scope where `T` has been declared**, such as `class Container<T> { Box<T> box; }`. Outside that scope, `T` has no automatic meaning. Do not use the letter `T` as a symbol for "any type" without a valid declaration.

## 9. A Declaration Can Place Bounds on a Type Parameter

The following declaration requires `T` to be `Number` or a subtype of it:

```java
final class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double doubleValue() {
        return value.doubleValue();
    }
}
```

Valid uses:

```java
// Illustrative snippet inside a method:
NumericBox<Integer> whole = new NumericBox<>(4);
NumericBox<Double> decimal = new NumericBox<>(2.5);
```

Invalid use:

```java
// NumericBox<String> bad = new NumericBox<>("x"); // Violates bound T extends Number
```

Here **the bound is written once in the declaration** `NumericBox<T extends Number>`, and then applies to every type argument at use sites. `<T extends Number>` in the declaration plays a different role from `<Integer>` in a use.

Another point: a type argument must be a **reference type**. Therefore `Box<int>` is invalid; `Box<Integer>` is valid. Java can automatically box integers when passing values to an object parameterized by `Integer`.

## 10. Diamond and `var`: Same Declaration, Yet Types Are Inferred at Use Sites

Java often infers type arguments during object creation:

```java
import java.util.ArrayList;
import java.util.List;

// Inside a method:
List<String> labels = new ArrayList<>();
```

The target type `List<String>` lets the expression `new ArrayList<>()` be inferred as `ArrayList<String>`. That is still a **use of the declared generic class `ArrayList<E>`**, not a new type declaration.

With `var`, pay attention to context:

```java
// Inside a method:
var names = new ArrayList<String>();
var unknown = new ArrayList<>();
```

- `names` has static type `ArrayList<String>` because the creation expression's type argument is explicitly stated.
- `unknown` has static type `ArrayList<Object>` in this context, because there is no more specific information to infer the type parameter. Consequently both `unknown.add("x")` and `unknown.add(123)` can compile.

The `var` syntax **does not create dynamic typing**. The compiler still fixes a static type at the local variable declaration. If the goal is a list of strings, use `List<String> names = new ArrayList<>();` or `var names = new ArrayList<String>();`.

## 11. Type Erasure: Uses Do Not Generate Independent JVM Classes

The most common source of confusion lies in the difference between **the compile-time type contract** and **the actual class at runtime**.

Suppose:

```java
// Illustrative snippet inside a method:
Box<String> text = new Box<>("Java");
Box<Integer> number = new Box<>(42);

System.out.println(text.getClass() == number.getClass());
```

The result is `true`. Java uses **type erasure** for most generic parameter information; both objects use the same runtime class `Box`. At compile time, the compiler still checks the two parameterized types as distinct.

This explains why the following syntax is **invalid**:

```java
// Object item = ...;
// if (item instanceof Box<String>) { } // Does not compile
```

The JVM does not retain type argument information in a way that can be checked with `instanceof Box<String>`. You can use `instanceof Box<?>` to test whether an object is a `Box`, yet that check **does not prove** the inner data is `String`.

### Raw Types Do Not Equal Type-Safe Checked Uses

When writing:

```java
// Inside a method:
Box raw = new Box("Java");
```

`Box` without type arguments is a **raw type**. This form exists for compatibility with legacy Java code, loses part of generics' protection, and typically triggers `rawtypes` or `unchecked` warnings.

Do not confuse:

| Expression/Type | Meaning |
|---|---|
| `Box<T>` in `class Box<T>` | Generic declaration, introducing parameter `T`. |
| `Box<String>` | Parameterized type using argument `String`. |
| `Box<?>` | Parameterized type with an unknown wildcard argument. |
| `Box` | Raw type, omitting type argument information. |
| `new Box<>("value")` | Object creation expression with inferred type argument. |

Raw types can cause `ClassCastException` when reading data through a parameterized API, especially if unsafe code inserted the wrong kind of object into the data structure. Generics reduces type errors via compile-time checking, yet does not automatically validate data coming from external sources or code using unchecked casts.

## 12. Common Mistakes When Distinguishing Declaration and Use

| Code or Assumption | Problem | Correct Understanding |
|---|---|---|
| "`Box<String>` is a newly defined Java class." | It is merely a parameterization of the same `Box<T>` declaration. | Define the class at `class Box<T>`; use it at `Box<String>`. |
| "`T` in `Box<T>` is always replaced with `Object` in source code." | `T` is a scoped type parameter and may have bounds. | In type-checked calling code, `Box<String>` carries a `String` contract. |
| Writing `Box<T> b` in a method where `T` is not declared | The name `T` is not yet in scope. | Use a concrete type, a wildcard, or declare a type parameter on the class/method. |
| Writing `new Box<>()` and thinking generics are not used | Diamond still infers the type argument. | Specify a target type or verify the inferred type. |
| Thinking `Box<String>` is a subtype of `Box<Object>` | Generics are invariant by default. | Do not assign directly between those two parameterized types. |
| Using `Box<int>` | Generics do not accept primitive types as type arguments. | Use `Box<Integer>`. |
| Using raw `Box` like `Box<?>` | Raw types bypass checks; wildcards preserve many generic typing rules. | Use `Box<?>` when the type argument is unknown. |
| Using `instanceof Box<String>` | Cannot check that type argument with `instanceof` due to erasure. | Use `instanceof Box<?>` if you only need to know whether the object is a Box. |
| Thinking each type argument creates a separate runtime class | Incorrect under Java's current generics mechanism. | One class declaration is used with many compile-time type contracts. |
| Using `var values = new ArrayList<>()` and expecting `List<String>` | There is no target type forcing the type argument to be `String`. | Explicitly state the type argument in at least one appropriate place. |

## 13. Checklist for Reading and Writing Generics Correctly

When you see `<...>` syntax, ask yourself:

1. **Am I at a declaration or a use site?** After `class`/`interface` and in `<T>` is a type parameter declaration; in `Box<String>` at a variable type position is a supplied type argument.
2. **Has the name inside angle brackets been declared?** `T` is a type parameter name, valid only within an appropriate declaration scope.
3. **How many type parameters are there, and in what order?** With `Pair<K,V>`, `Pair<String,Integer>` binds in exact order.
4. **What are the type bounds?** If `T extends Number` is declared, `String` cannot be used as a type argument.
5. **Does the expression create an object?** `Box<String> ref;` only declares a variable; `new Box<>("x")` creates the object.
6. **Does diamond have enough context for inference?** An explicit target type keeps code readable, whereas `var` may cause `Object` to be inferred.
7. **Am I mixing different parameterized types?** `Box<String>` cannot be directly assigned to `Box<Object>`.
8. **Am I confusing compile time with runtime?** One runtime class `Box` can be used with many type arguments in source code.

### Self-Check

**Question 1.** Identify where a type parameter is declared and where a type argument is used:

```java
class Holder<T> {
    private final T value;

    Holder(T value) { this.value = value; }
    T get() { return value; }
}

// Inside a method:
Holder<String> h = new Holder<>("Hello");
```

**Question 2.** Why does the same `Pair<K,V>` class allow both `Pair<String,Integer>` and `Pair<Integer,String>`, yet not mean those two types are interchangeable?

**Question 3.** Does `class StaticReader implements Reader<String>` declare a type parameter on the `StaticReader` class itself?

**Question 4.** How do `Box<?>` and `Box` differ?

**Question 5.** Why can `new Box<>("x")` infer `Box<String>`, while `var list = new ArrayList<>()` typically infers the type argument as `Object`?

**Suggested answers:** (1) `<T>` after `Holder` is a declaration, `<String>` in `Holder<String>` is a type argument, and `<>` in `new Holder<>()` is diamond for inference. (2) Type arguments bind to different positions; Java generics are invariant by default. (3) No, `StaticReader` is a non-generic class and only uses the `Reader<String>` interface. (4) `Box<?>` remains a parameterized type with an unknown argument; `Box` is a raw type. (5) The first case has a target type and constructor argument, whereas the second lacks information to infer a narrower type.

**Remember:** A **generic declaration** builds a reusable type contract, while **each generic use** specifies or infers type arguments for that contract. The compiler clearly distinguishes `Box<String>`, `Box<Integer>`, and `Box<?>` in source code, even though their objects normally share the same runtime class after type erasure.
