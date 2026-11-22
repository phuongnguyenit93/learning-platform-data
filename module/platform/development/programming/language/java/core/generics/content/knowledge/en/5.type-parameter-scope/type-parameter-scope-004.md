# Static Methods Declaring Their Own Type Parameters in Java Generics

When a Java class has the form `class Container<T>`, the type parameter `T` belongs to **a usage of the generic class** such as `Container<String>` or `Container<Integer>`. Yet a `static` method belongs to **the class**, called without selecting a specific `Container<T>` object. Therefore, a static method **cannot directly use the type parameter `T` declared at the class level**. If a static method needs to work generically across data types, it must **declare its own type parameter**, for example:

```java
class Container<T> {
    static <U> U identity(U value) {
        return value;
    }
}
```

Here `T` is the type parameter of **the class**, while `U` is the type parameter of **the static method**. They have different scopes and are not tied to one another. The key syntax is **`static <U> ReturnType methodName(...)`**, placing the `<U>` declaration after the `static` modifier and before the return type.

## 1. Two Kinds of Type Parameters with Different Scopes

Consider the following class declaration:

```java
class Holder<T> {
    private final T stored;

    Holder(T stored) {
        this.stored = stored;
    }

    T get() {
        return stored;
    }

    static <U> U echo(U value) {
        return value;
    }
}
```

This is a **standalone class definition for illustration**; if used in another runnable file, place it in the same package or inside an enclosing class as appropriate.

- `class Holder<T>`: the class declares the type parameter `T`. The instance field `stored`, the constructor, and the instance method `get()` can all use `T`.
- `static <U> U echo(U value)`: the static method **declares its own** type parameter `U`. It can be called as `Holder.echo("hello")` or `Holder.echo(123)`.
- `U` is only in effect within the signature and body of the `echo` method; it does not automatically appear in fields, constructors, or other methods of `Holder`.
- When you have `Holder<String> textHolder`, `T = String` belongs to that object's type. It **does not force** `U` in `Holder.echo(123)` to become `String`.
- An instance method can also declare `<U>`; the core difference is that an instance method has access to **both** the class's type parameter `T` and the method's own type parameter `U`.

Comparison table:

| Declaration site | Example | Valid usage scope |
|---|---|---|
| Class type parameter | `class Holder<T>` | **Instance** fields and methods, constructors, and declarations allowed within the generic type's context |
| Static method type parameter | `static <U> U echo(U x)` | Signature and body of **that static method itself** |
| Instance method type parameter | `<U> U change(U x)` | Signature and body of the method; can also use the class's `T` where appropriate |
| Static factory type parameter | `static <U> Holder<U> of(U x)` | `U` belongs to the factory; the result is a `Holder<U>` object |
| Static nested class type parameter | `static class Node<U>` | `U` belongs to `Node`, not taken from an enclosing class instance's `T` |

An easy point to remember: **`static` belongs to the class level, whereas the type argument `T` of `Holder<T>` is chosen for a parameterized type at use time**. There is no single `T` value applying to all `Holder<String>` and `Holder<Integer>` instances existing simultaneously.

## 2. Why Doesn't a Static Method Directly Use the Class's `T`?

A generic class can be used with multiple types:

```java
Holder<String> words = new Holder<>("Java");
Holder<Integer> count = new Holder<>(7);
```

The lines above are **usage examples** of `Holder<T>`; they need to be placed inside a method or valid variable-declaration context.

The same `Holder` class has parameterizations `Holder<String>` and `Holder<Integer>`. If there were a `static T current()` method, when calling `Holder.current()`, Java would have **no object** to determine whether `T` is `String` or `Integer`. Hence Java forbids directly using a class-level type parameter in a static context.

Example that **does not compile**:

```java
class InvalidBox<T> {
    // static T last;              // Wrong: static field uses the class's T.
    // static T getLast() {        // Wrong: static method uses the class's T.
    //     return null;
    // }
    // static void save(T value) { // Wrong: parameter uses the class's T.
    // }
}
```

The erroneous lines are commented out for presentation; if uncommented, those declarations will be rejected by the compiler for referencing a generic class's type variable from a static context.

The right solution is to **declare the type parameter on the method itself**:

```java
class ValidBox<T> {
    static <U> U identity(U value) {
        return value;
    }

    static <U> ValidBox<U> of(U value) {
        return new ValidBox<>();
    }
}
```

**Note:** the `ValidBox` version above only illustrates **syntax**; because `ValidBox` defines no constructor accepting a value or field storing data, `of(U value)` returns an empty box. In real designs, there should be a storage field and a constructor accepting `U`; the complete example in a later section implements that full behavior.

You do not need to make **the entire class** generic to have a static generic method. An ordinary class can also write `static <T> T identity(T value)`. This mechanism is independent of whether the enclosing class has `<T>`.

## 3. Standard Syntax: Declaring `<U>` Before the Return Type

General form of a static generic method:

```java
[annotations] [access modifier] static <TypeParameters> ReturnType methodName(
        Parameters) {
    // Method body
}
```

The square brackets and descriptive names above **are merely explanatory notation**, not a standalone compilable Java snippet. Examples of actual syntax:

```java
public static <T> T identity(T input) {
    return input;
}

public static <E> java.util.List<E> twice(E element) {
    return java.util.List.of(element, element);
}

private static <N extends Number> double doubled(N number) {
    return number.doubleValue() * 2;
}
```

These three methods are **illustrative snippets to be placed inside a class**.

Reading the method `public static <T> T identity(T input)`:

1. `public static`: modifiers; the method belongs to the class.
2. `<T>`: **declares** a method-level type parameter.
3. `T`: return type, **using** the newly declared type parameter.
4. `identity`: method name.
5. `T input`: parameter type and input variable name, constraining input and output to share the same `T`.

A method's type parameter can appear in the return type, parameter types, bounds, or method body. The return type **does not have to be `T`**: `void`, `int`, `double`, `List<T>` can all be return types of a generic method.

A few syntax mistakes:

```java
// static T <T> identity(T input) { return input; } // Wrong order.
// static T identity(T input) { return input; }     // Wrong if T has not been declared.
// static T identity<T>(T input) { return input; }  // Java does not declare <T> after the method name.
```

Distinguish `static <T> T method(T value)` **at the declaration** from `ClassName.<String>method("x")` **at an explicit call site**. The first names a type parameter; the second supplies a type argument.

## 4. Standalone Runnable Java 17 Example: Generic Class, Static Factory, Static Generic Method

Save the entire following program as **`StaticGenericScopeDemo.java`**:

```java
import java.util.List;
import java.util.Map;

public class StaticGenericScopeDemo {

    static final class Container<T> {
        private final T value;

        private Container(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        static <U> Container<U> of(U input) {
            return new Container<>(input);
        }

        static <U> U identity(U input) {
            return input;
        }

        static <K, V> Map.Entry<K, V> entry(K key, V value) {
            return Map.entry(key, value);
        }

        <U> Map.Entry<T, U> combineWith(U other) {
            return Map.entry(value, other);
        }
    }

    static <E> List<E> repeat(E element) {
        return List.of(element, element);
    }

    static <N extends Number> double doubled(N number) {
        return number.doubleValue() * 2;
    }

    public static void main(String[] args) {
        Container<String> text = Container.of("Java");
        Container<Integer> count = Container.of(8);

        System.out.println("text: " + text.get());
        System.out.println("number: " + count.get());

        Integer inferred = Container.identity(42);
        System.out.println("inferred: " + inferred);

        Number wide = Container.<Number>identity(12);
        System.out.println("explicit: " + wide);

        Map.Entry<String, Integer> data =
                Container.<String, Integer>entry("age", 20);
        System.out.println("entry: " + data.getKey()
                + "=" + data.getValue());

        Map.Entry<String, Boolean> pair = text.combineWith(true);
        System.out.println("instance: " + pair.getKey()
                + "," + pair.getValue());

        System.out.println("repeat: " + repeat("go"));
        System.out.println("doubled: " + doubled(2.5));

        Container<String> created = Container.<String>of("OK");
        System.out.println("factory: " + created.get());
    }
}
```

Compile and run in the directory containing the file with Java 17 or newer:

```bash
javac StaticGenericScopeDemo.java
java StaticGenericScopeDemo
```

Stdout output:

```text
text: Java
number: 8
inferred: 42
explicit: 12
entry: age=20
instance: Java,true
repeat: [go, go]
doubled: 5.0
factory: OK
```

Detailed explanation of each point:

- `Container<T>` is a **generic class**. `get()` returns `T` belonging to a specific parameterization, so `text.get()` has static type `String` and `count.get()` has type `Integer`.
- `static <U> Container<U> of(U input)` is a **static generic factory method**. `U` is declared by the method itself; `Container.of("Java")` creates `Container<String>`, and `Container.of(8)` creates `Container<Integer>`. The literal `8` is boxed to `Integer` as needed.
- `static <U> U identity(U input)` does not use the class's `T`. `Container.identity(42)` infers `U = Integer`, even though no `Container<Integer>` variable participates in the call.
- `Container.<Number>identity(12)` specifies the **type argument `Number` for the static method itself**. The input object is still an `Integer` after boxing; the result is viewed through the static type `Number`.
- `static <K, V> Map.Entry<K, V> entry(...)` declares **two** type parameters; `Container.<String, Integer>entry("age", 20)` supplies both in order. `Map.entry` does not accept `null` values and returns an entry that does not support `setValue`.
- `<U> Map.Entry<T,U> combineWith(U other)` is an **instance generic method**. It is allowed to use `T` of `Container<T>` **and** `U` of the method itself. With `text` being `Container<String>` and argument `true` (boxed to `Boolean`), the result has type `Map.Entry<String, Boolean>`.
- `static <E> List<E> repeat(E element)` is declared in the **non-generic** `StaticGenericScopeDemo` class. This shows a static generic method does not have to live inside a generic class. `List.of` creates an unmodifiable list; it also rejects `null`.
- `static <N extends Number> double doubled(N number)` uses the bound `N extends Number`, so it can call `doubleValue()`. `doubled(2.5)` boxes the `double` value into `Double` and prints `5.0`.
- `Container.<String>of("OK")` specifies `U = String` for the factory. There is no concept of "assigning `T = String` for the entire `Container` class at runtime"; the result's `Container<String>` type is checked at compile time.

## 5. Static Factory: The Most Important Application of Static Generic Methods

A common pattern when building a generic class is a non-public constructor paired with a public factory that infers the type parameter for the new object:

```java
class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = value;
    }

    public static <U> Box<U> of(U value) {
        return new Box<>(value);
    }

    public T get() {
        return value;
    }
}
```

This is **another illustrative class**, independent of `Container` in the runnable program. It can be used as:

```java
Box<String> name = Box.of("Ada");
Box<Integer> points = Box.of(100);
```

Why must the factory signature be `static <U> Box<U> of(U value)`?

1. A static method cannot use the class's `T` to write `static Box<T> of(T value)`.
2. Declaring `<U>` provides a new type parameter, scoped to the factory method.
3. `Box<U>` in the return type links **the factory argument's type** to **the type of the created Box object**.
4. The compiler uses `U` to check `new Box<>(value)` and the result type.
5. Naming the method `of` is just an API choice; `from`, `create`, or a name expressing the contract could also be used.

A signature like `static <U> Box<Object> of(U value)` is still a valid static generic method, yet it **loses** the type `U` in the return type, which is usually not the desired contract. Only the `Box<U>` design preserves type safety.

Popular factories in the Java API (such as `List.of(...)`, `Map.entry(...)`, `Optional.of(...)`) all illustrate the benefits of static methods involving type parameters. Always read the **actual signature** of each API to know what type parameters the method has, how it handles nulls, and whether the result is mutable; do not infer that every factory behaves identically just from the name `of`.

## 6. Type Inference and Explicit Type Arguments of Static Methods

Java usually infers the type argument from the arguments and target type:

```java
String word = Container.identity("hello");
Integer size = Container.identity(5);
Number number = Container.<Number>identity(5);
```

The lines above use the `Container` class from the standalone runnable program and need to be placed inside a valid method.

- `Container.identity("hello")`: the `String` argument type creates sufficient constraints to infer `U = String`.
- `Container.identity(5)`: the primitive `int` value is appropriately boxed; `U` is inferred as `Integer`.
- `Container.<Number>identity(5)`: explicitly selects `U = Number`; boxing creates `Integer`, which is a subtype of `Number`.
- A type witness **is not a cast** and does not perform arbitrary conversions. `Container.<String>identity(5)` does not compile because `int` cannot be passed where `String` is required.

The syntax of a static call with explicit type arguments is:

```java
ClassName.<ConcreteType>method(arguments);
ClassName.<FirstType, SecondType>method(arguments);
```

This is a **descriptive syntax template**; replace the class name, types, method, and arguments before use. Do not write `ClassName.method<ConcreteType>(...)` out of habit from other languages.

A common example of target typing with a method taking no arguments:

```java
static <T> List<T> empty() {
    return List.of();
}
```

With the `empty()` method placed inside a `CollectionsHelper` class, callers can write:

```java
List<String> texts = CollectionsHelper.empty();
var explicit = CollectionsHelper.<String>empty();
```

Both calls produce static type `List<String>`; the first line infers it via the target type, the second via a type witness. If you write `var inferred = CollectionsHelper.empty();` in a context without enough information, the type is typically inferred broadly such as `List<Object>`. The `<T>` belongs to the `empty` method and does not rely on an enclosing generic class.

## 7. Static Methods with Multiple Type Parameters and Constraints

A static method can declare multiple type parameters:

```java
public static <K, V> java.util.Map.Entry<K, V> entry(K key, V value) {
    return java.util.Map.entry(key, value);
}
```

`K` and `V` are scoped **within the same method**; they are independent of each other. You can call `ClassName.<String, Integer>entry("age", 20)`, or let the compiler infer them. When specifying explicitly, you must provide all type arguments in the exact order.

A type parameter can also have a bound:

```java
public static <N extends Number> double doubled(N value) {
    return value.doubleValue() * 2;
}
```

The `<N extends Number>` part requires the type argument to be `Number` or a suitable subtype. `doubled(4)` is valid via `Integer`; `doubled("4")` is rejected at compile time. An `extends` bound **does not turn the method into an instance method** and does not grant the static method permission to use the class-level `T`.

Multiple bounds can be chained:

```java
public static <T extends Number & Comparable<T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

The method above is an **illustrative template** to be placed inside a class. `Integer` satisfies both `Number` and `Comparable<Integer>`. In multiple-bound syntax, if one bound is a class it must appear first, followed by interfaces separated by `&`. You cannot declare a lower bound `<T super Number>`; `? super T` is wildcard syntax at a type-use site, not a new type parameter declaration.

## 8. Distinguishing Static Generic Methods from Instance Methods Using the Class's Type

Suppose a generic class declares:

```java
class Shelf<T> {
    private T item;

    Shelf(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }

    void set(T next) {
        this.item = next;
    }

    <U> String describeWith(U label) {
        return label + "=" + item;
    }

    static <U> U echo(U input) {
        return input;
    }
}
```

This is a **standalone illustrative class**.

| Member | Declares its own type parameter? | Uses the class's `T`? | Meaning |
|---|---|---|---|
| `T get()` | No | Yes | Reads the element according to `Shelf<T>`'s type |
| `void set(T next)` | No | Yes | Replaces the element according to the instance's type |
| `<U> String describeWith(U label)` | Yes (`U`) | Yes, via `item` | Instance method combining both the class's type and the method's type |
| `static <U> U echo(U input)` | Yes (`U`) | No | Static method with an independent type parameter |

Given `Shelf<String> shelf = new Shelf<>("book")`:

- `shelf.set("new book")` is valid, because `T = String` in the instance type.
- `shelf.describeWith(42)` is valid, because the instance method infers `U = Integer`, while the `item` field remains `String`.
- `Shelf.echo(42)` is valid. **No** `Shelf<Integer>` object is needed to choose `U = Integer`.
- `shelf.set(42)` is invalid: `set` uses `T = String` from the class, with no new type parameter.
- Do not call a static method via an instance expression (`shelf.echo(...)`) even though some Java syntax permits it: it misleads readers into thinking the method depends on object state. Use the class name.

Important distinction: `get()` **is not a generic method declaring its own type parameter**, even though its return type is `T`; it uses the type parameter **declared by the class**. By contrast, `static <U> U echo(U input)` is a true generic method.

## 9. Static Nested Class: Same Static Rule, but Type Parameter at the Nested Class Level

A `static nested class` can itself be generic without **carrying the outer class's type parameter**. For instance:

~~~java
class Outer<T> {
    static final class Nested<U> {
        private final U data;
        Nested(U data) { this.data = data; }
        U get() { return data; }
    }
}
~~~

`Outer.Nested<String>` is valid; `Outer<String>.Nested<Integer>` is not valid parameterization syntax for a static member type. `U` belongs to `Nested` itself, while `T` cannot be used directly in that static context.

A static method **inside** `Nested<U>` must also declare its own type parameter if it wants to be generic, such as `static <X> X identity(X input)`; it cannot directly use `Nested`'s `U`. This continues the static method rule; details on inner classes, nested factories, bounds, and enclosing instances belong to the nested classes topic.

## 10. Avoid Shadowing the Class's `T` with a New Type Parameter

Java allows writing `class Wrapper<T> { static <T> T echo(T input) { return input; } }`. Though valid, **the method's `T` is not the class's `T`**; the matching name creates the illusion that the method depends on a `Wrapper<T>` instance.

If the two scopes are independent, write `static <U> U echo(U input)`. Renaming does not alter runtime behavior, yet immediately distinguishes the declaration sites. If the method truly needs the value inside a `Wrapper<T>`, accept `Wrapper<U>` as a parameter or turn it into an instance method; do not use an unchecked cast to bridge two unrelated `T`s.

The shadowing mechanism, differing bounds across two declarations, and setter/return-type bugs from reusing the name `T` need to be analyzed separately; the goal here is simply designing clear **static generic method** signatures.

## 11. Why Doesn't Type Erasure Eliminate Compile-Time Type Checking?

Generic static methods participate in Java's **type erasure** mechanism just like other generic methods:

```java
static <U> U identity(U value) {
    return value;
}
```

With unbounded `U`, the representative type after erasure is usually `Object`. The compiler checks calls like `String s = identity("x")` and can insert appropriate casts in bytecode. This explains why the same static method can handle `String`, `Integer`, and other reference types without the runtime generating multiple distinct versions.

Consequences:

- You cannot use `new U()` simply because the method declares `<U>`: no runtime constructor is inferred from a type parameter.
- You cannot directly use `U.class` or `obj instanceof U` for an ordinary non-reifiable type variable.
- You cannot pass primitives such as `<int>`; `<Integer>` or autoboxing is the appropriate approach in Java 17.
- Calling `Container.<String>identity("x")` neither creates a `Container<String>` object nor mutates the state of any `Container`; only a factory call returning `Container<U>` creates an object per the factory body.
- Bridge methods may be generated when needed to preserve override semantics in generics and inheritance cases, yet the presence of `<U>` on a static method **does not create dynamic dispatch on its own**.

If you need to **create a `U` object**, design an explicit factory using `Supplier<U>`:

```java
static <U> U create(java.util.function.Supplier<U> factory) {
    return java.util.Objects.requireNonNull(factory).get();
}
```

This is an **illustrative method** to be placed inside a class. A call `create(StringBuilder::new)` can return a `StringBuilder`; the creation instructions are supplied by `Supplier<U>`, not because `U` itself carries a constructor.

## 12. Common Mistakes with Static and Generic Type Parameters

**Mistake 1 — Static method using the class's `T`.** In `class Box<T>`, declaring `static T identity(T x)` is wrong because `T` belongs to the instance scope of the generic class. Fix it to `static <U> U identity(U x)` if the method is independent of the class's type.

**Mistake 2 — Static field having the class's type `T`.** `static T lastValue;` is invalid. If the data actually belongs to each object, use an instance field `private T lastValue;`. If the data is class-wide, choose a concrete static type or design an appropriate store.

**Mistake 3 — Forgetting `<U>` before the return type.** `static U echo(U input)` does not compile if `U` has not been declared in the right scope. Write `static <U> U echo(U input)`.

**Mistake 4 — Placing `<U>` after the method name.** `static U echo<U>(U input)` is invalid Java syntax. Place `<U>` after modifiers and before the return type.

**Mistake 5 — Thinking `Container<String>` determines `U` for a static method.** `Container.identity(7)` is inferred from the call; no `Container<Integer>` needs to be created. Static calls are written via the class name to make this clear.

**Mistake 6 — Not distinguishing a static factory from an instance method.** `static <U> Box<U> of(U value)` creates a new `Box<U>`; `T get()` reads the value of a `Box<T>` instance. The two signatures use type parameters from two different scopes.

**Mistake 7 — Using `<U>` yet returning `Box<Object>`.** If the contract requires preserving the argument's type, return `Box<U>`. Returning `Box<Object>` discards needed type information, even though it may still compile.

**Mistake 8 — Assuming a static generic method has a separate runtime version per `U`.** Normally Java uses erasure. `identity("x")` and `identity(1)` invoke the same static method definition, without generating specialized source/bytecode per type argument.

**Mistake 9 — Using the same name `T` on the class and method without noticing shadowing.** `static <T> T echo(T x)` has its own `T`; choose `U` when distinguishing from `class Wrapper<T>`.

**Mistake 10 — Misunderstanding that a static nested class inherits the outer class's type.** `static class Nested<U>` has an independent `U` and cannot directly use `Outer<T>`'s `T`. Do not use `Outer<String>.Nested<Integer>` as with inner class declarations.

**Mistake 11 — Overusing generic methods when no type relationship is needed.** If only printing data, `static void print(Object x)` can be clear enough; `static <T> void print(T x)` is valid yet creates no type-safety benefit when `T` is not tied to another position.

**Mistake 12 — Confusing `static <T>` with arbitrary conversion.** `Container.<String>identity(123)` still does not compile; the method is constrained by the specified type argument. A type witness cannot automatically turn an integer into a string.

## 13. Self-Check with Answers

**Question 1.** Why is `class Box<T> { static T get(); }` wrong?  
**Answer:** A static method has no specific instance parameterization to use the class's `T`; it needs a concrete type or the method's own type parameter.

**Question 2.** Is `class Box<T> { static <U> U echo(U x) { return x; } }` valid?  
**Answer:** Valid; `U` belongs to the static method.

**Question 3.** Given `Box<String> b`, when calling `Box.echo(10)`, what is `U`?  
**Answer:** `U = Integer` can be inferred via boxing of `10`; `b` having `T = String` has no effect.

**Question 4.** What benefit does `static <U> Box<U> of(U value)` provide compared to returning `Box<Object>`?  
**Answer:** Preserves the type relationship between the passed-in argument and the returned `Box<U>` object.

**Question 5.** Is `static <U> void log(U x)` a generic method even though it returns `void`?  
**Answer:** Yes. A generic method is identified by declaring its own type parameter `<U>`, regardless of return type.

**Question 6.** Does `static <N extends Number> double doubled(N n)` accept `String`?  
**Answer:** No. `String` does not satisfy the `Number` bound.

**Question 7.** Can an instance method simultaneously use the class's type and a type it declares itself?  
**Answer:** Yes, for example `<U> Map.Entry<T, U> combineWith(U value)` in `Container<T>`.

**Question 8.** Is `Outer<T>.Nested<U>` the syntax to use when `Nested` is declared static?  
**Answer:** No. A static nested class does not depend on a parameterized outer instance; use `Outer.Nested<U>`.

**Question 9.** Can a static generic method declare two independent types?  
**Answer:** Yes: `static <K,V> Map.Entry<K,V> entry(K k,V v)`.

**Question 10.** How does `Container.<Integer>identity(7)` differ from `Container.identity(7)`?  
**Answer:** The first call specifies the type argument explicitly; the second lets the compiler infer it. In the example, both are valid and return `7` with the appropriate static type.

**Question 11.** Why is `new U()` not permitted solely by declaring `static <U>`?  
**Answer:** Type parameters are erased and provide no runtime constructor; a factory/`Supplier<U>` is needed if an object must be created.

**Question 12.** When is it unnecessary to write `<U>` on a method in a generic class?  
**Answer:** If an instance method only needs to use the class's `T`, such as `T get()`; or if a static method only handles concrete types and needs no independent type parameter.

**Question 13.** Why is `static <T> T echo(T value)` inside `class Box<T>` confusing even though it can be valid?  
**Answer:** The method's `T` shadows the class's `T`; consider using `<U>` to express the two scopes clearly.

**Question 14.** If `static <U> List<U> repeat(U value)` receives a `String`, what is the result type?  
**Answer:** With `U = String`, the result is `List<String>`; the call `repeat("hi")` can infer that at compile time.

Core rule: **a generic class's type parameter is tied to instance types, whereas a static generic method's type parameter is declared right on the method and is independent of any instance**. Read the signature `static <U> ...` as a new contract, not as a way to "borrow" `T` from `class Container<T>`. Once you understand the scope properly, you can write safe static factories, utility functions, and generic APIs without hitting the `non-static type variable cannot be referenced from a static context` error.
