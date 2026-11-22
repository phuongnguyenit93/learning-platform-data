# Passing Type Arguments and Creating Parameterized Type Objects in Java Generics

When using **Java Generics**, you can write a shared class or interface for multiple data types, then **pass type arguments** at usage sites. For example, `Box<String>` denotes a `Box` holding a value of type `String`, while `Box<Integer>` denotes a `Box` holding a value of type `Integer`. The compiler relies on type arguments to check assignments, method calls, and returned data types.

This lesson covers the syntax for passing type arguments, how to instantiate objects with or without the **diamond operator** (`<>`), how Java infers types from context, and common mistakes when instantiating generics.

## 1. Distinguishing Type Parameters from Type Arguments

Consider the following class declaration:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Here:

- `Box` is the generic class name.
- `T` is a **type parameter**, declared inside `<T>`; it is a placeholder name for a reference type that the usage site will specify.
- `Box<String>` is a **parameterized type**, in which `String` is the concrete **type argument** passed into the position of `T`.
- `Box<Integer>` is another usage of the same `Box<T>` declaration, with `T` corresponding to `Integer`.

General syntax:

```java
class Container<T> { /* declaration using T */ }

// Example placed inside a method:
Container<String> textContainer;    // Passing type argument String
Container<Integer> numberContainer; // Passing type argument Integer
```

The `<T>` part appears **when declaring** a generic; `<String>` or `<Integer>` appears **when using** a generic. These are two different roles, even though both use angle brackets `<...>`.

Multiple type parameters can be declared, separated by commas:

```java
class Pair<K, V> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() { return key; }
    V value() { return value; }
}
```

When using `Pair<String, Integer>`, parameter `K` is bound to `String`, and `V` to `Integer`. **The order of type arguments must match the order of type parameters** in the declaration. Names like `T`, `K`, and `V` are readability conventions; the compiler does not require using those exact letters.

## 2. Full Syntax When Creating Generic Objects

A `Box<String>` object can be created by stating the type argument in both the variable declaration and the `new` expression:

```java
Box<String> title = new Box<String>("java");
```

How to read it:

1. `Box<String>` on the left declares the **type of the reference variable** `title`.
2. `new Box<String>("java")` on the right calls `Box`'s constructor and specifies the type argument `String` for the created object.
3. `"java"` is the value passed to the constructor; since `T` is specified as `String`, it matches the constructor parameter of type `T`.
4. `title.get()` has compile-time expression type `String`, so `toUpperCase()` can be called directly.

The type argument is passed to the **generic type**; it is not a value parameter of the constructor. For example, `new Box<String>("java")` has the **type argument** `String` and the **constructor argument** `"java"`.

If the class defines a no-argument constructor, you can write `new ClassName<Type>()`; if the constructor requires parameters, corresponding value arguments must be supplied. Generics do not automatically generate constructors or bypass constructor constraints.

### Complete Runnable Java 17 Example

Save the following program as `TypeArgumentsDemo.java`:

```java
public class TypeArgumentsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static final class Pair<K, V> {
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

    public static void main(String[] args) {
        Box<String> title = new Box<String>("java");
        Box<Integer> quantity = new Box<Integer>(3);
        Pair<String, Integer> version = new Pair<String, Integer>("JDK", 17);

        System.out.println(title.get().toUpperCase());
        System.out.println(quantity.get() + 2);
        System.out.println(version.key() + " " + version.value());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 TypeArgumentsDemo.java
java TypeArgumentsDemo
```

Expected output (`stdout`):

```text
JAVA
5
JDK 17
```

In `Box<Integer>`, the type parameter uses `Integer` (the wrapper class for `int`). Java automatically boxes the number `3` into an `Integer` when passing it to the constructor and unboxes it when performing addition in `quantity.get() + 2`. The `Pair<String, Integer>` type lets the compiler check both constructor arguments in order.

## 3. Using the Diamond Operator `<>` So Java Infers Type Arguments

Since Java 7, when creating a generic object, you can usually replace the type arguments after `new` with the **diamond** `<>`:

```java
Box<String> title = new Box<>("java");
Box<Integer> quantity = new Box<>(3);
Pair<String, Integer> version = new Pair<>("JDK", 17);
```

These three expressions express the same type intent as the explicit form in the previous example. The diamond asks the compiler to **infer** type arguments based on available information, including the `target type` and the types of constructor arguments.

Comparison:

| Explicit Form | Using Diamond | Intended Result |
|---|---|---|
| `new Box<String>("java")` | `new Box<>("java")` | Instantiates `Box<String>` in a matching context |
| `new Box<Integer>(3)` | `new Box<>(3)` | Instantiates `Box<Integer>` in a matching context |
| `new Pair<String, Integer>("JDK", 17)` | `new Pair<>("JDK", 17)` | Instantiates `Pair<String, Integer>` in a matching context |

**The diamond is written only as `<>`, not `<T>`.** In `new Box<>()`, Java is responsible for inferring the type argument; in `new Box<String>()`, the programmer specifies `String` directly.

The diamond reduces repetition and is usually preferred when the inferred result matches the intended contract. There are contexts with insufficient information or complex constructor arguments where the inferred type is broader than expected; in such cases, stating types explicitly gives better control.

## 4. The Left-Hand Variable Type Can Determine the Right-Hand Inferred Type

Consider a collection declaration:

```java
import java.util.ArrayList;
import java.util.List;

List<String> names = new ArrayList<>();
names.add("An");
String firstName = names.get(0);
```

This is an **illustrative code snippet inside a method body**; it requires imports as shown above. `List<String>` is a parameterized type of the `List` **interface**; `ArrayList` is the implementation class being instantiated. The compiler infers `String` for `new ArrayList<>()` thanks to the target type `List<String>`.

Practical benefits:

- The API of the variable `names` represents a list that only accepts `String` elements through type-checked operations.
- When calling `names.add("An")`, the value is valid because it is a `String`.
- When calling `names.get(0)`, the expression type is `String`; there is no need to write `(String)`.
- If you add `names.add(42)`, the compiler reports an error because `int` is boxed to `Integer`, which does not match the `String` type parameter.

Because `List` is an interface, you cannot write `new List<String>()` directly; you must pick an implementation class, such as `ArrayList`. The variable's parameterization syntax and the instantiation syntax occupy two independent positions: a variable can be declared with an interface, while the object is instantiated from an implementation class.

### Example with Nested Types

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

// Placed inside a method:
Map<String, List<Integer>> scores = new HashMap<>();
scores.put("Java", new ArrayList<>());
scores.get("Java").add(10);
```

Here `Map<String, List<Integer>>` has two outer type arguments: key `String` and value `List<Integer>`. `List<Integer>` is itself a parameterized type. The `>>` at the end of the declaration closes two nested pairs of angle brackets; in modern Java, no space is needed to separate them.

Do not confuse the different kinds of brackets:

- `<String, Integer>`: **type** arguments.
- `("Java", 17)`: **value** arguments to a constructor or method.
- `<>`: diamond to **infer** type arguments during instantiation.

## 5. `var` Combined with Diamond: Recognizing the Inferred Type

`var` lets the compiler infer the **static type of a local variable** from its initializer. If the initializer is an empty generic constructor with the diamond and no specific target type, inference can produce `Object` as the element type:

```java
List<String> a = new ArrayList<>();     // Target type allows inferring String.
var b = new ArrayList<>();              // b has type ArrayList<Object>.
var c = new ArrayList<String>();        // c has type ArrayList<String>.
```

Important distinction: `ArrayList<Object>` is still a **parameterized type**, not a raw `ArrayList`. `var` does not make the variable dynamically typed. When a call needs `String` elements, prefer writing `List<String> names = new ArrayList<>();` or `var names = new ArrayList<String>();`. In-depth analysis of diamond/var, raw warnings, and heap pollution examples belongs to the dedicated lesson on the diamond operator.

## 6. Passing Type Arguments to a Generic Method

Type arguments can also be passed when calling a **generic method**. In a method declaration, the type parameter list `<T>` stands **before the return type**:

```java
static <T> T echo(T value) {
    return value;
}
```

At call sites, Java usually infers `T` from the value argument and target type:

```java
String result = echo("Java");
```

You can also specify the type argument **explicitly** with the syntax `ClassName.<Type>method(...)`:

```java
String result = TypeMethodDemo.<String>echo("Java");
```

In a generic method call, `<String>` appears **immediately before the method name**, not after `new`. This syntax differs from the diamond in a constructor instantiation expression.

Complete runnable example, save as `TypeMethodDemo.java`:

```java
public class TypeMethodDemo {
    static <T> T echo(T value) {
        return value;
    }

    public static void main(String[] args) {
        String inferred = echo("Java");
        String explicit = TypeMethodDemo.<String>echo("JDK");

        System.out.println(inferred);
        System.out.println(explicit);
    }
}
```

Commands:

```bash
javac -encoding UTF-8 TypeMethodDemo.java
java TypeMethodDemo
```

`stdout`:

```text
Java
JDK
```

Normally, you should let the compiler infer method type arguments when the intent is clear. Explicit specification syntax is useful when you want to clarify a specific type or resolve a difficult inference case.

**An important note:** a class's type parameter and a method's type parameter are two separate declarations. A `static` method cannot directly use `T` declared only on `class Box<T>`; it must declare its own type parameter, for example `static <U> U identity(U value)`.

## 7. Conditions That Type Arguments Must Satisfy

### 7.1. A Type Argument Must Be a Reference Type

Java Generics does not accept `primitive types` as type arguments:

```java
Box<int> counter;       // Incorrect: int is not a reference type
Box<Integer> counter2;  // Correct: Integer is a reference type
```

Common pairs include `int`/`Integer`, `long`/`Long`, `double`/`Double`, and `boolean`/`Boolean`. Autoboxing/unboxing makes code convenient, but it does not make `Box<int>` valid.

### 7.2. A Type Argument Must Satisfy Its Bound (If Any)

Suppose a class declares:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

`T extends Number` requires the type argument to be `Number` or a subtype of `Number`. Therefore:

```java
NumberBox<Integer> integers = new NumberBox<>(5); // Correct
NumberBox<Double> decimals = new NumberBox<>(1.5); // Correct
// NumberBox<String> text = new NumberBox<>("x"); // Incorrect: String does not extend Number
```

This is an **illustrative code snippet** and must be placed inside a method body alongside the `NumberBox` declaration above. A type inferred via the diamond must still satisfy the declared bound.

### 7.3. Generics Are Invariant by Default

Even though `Integer` is a subtype of `Number`, the following two parameterized types do **not** have a subtype relationship in the same direction:

```java
// List<Number> numbers = new ArrayList<Integer>(); // Incorrect: incompatible
```

If a developer needs to work with a family of types related by inheritance, wildcards such as `? extends Number` or `? super Integer` may fit, though they come with their own read/write rules. Do not replace `<Integer>` with `<Number>` or assume arbitrary assignment just because the two type arguments are related by inheritance.

### 7.4. A Single Specific Type Cannot Be Inferred from Every Context

The diamond uses facts from the program and does not know business intent. If the facts only allow inferring `Object`, the program may still be valid yet lose the desired constraint. It is best to write sufficiently clear target types at API boundaries and check compiler warnings.

## 8. Distinguishing Parameterized Types from Raw Types When Creating Objects

`Box<String> value = new Box<>("Java")` uses the generic type argument `String` and the diamond for type inference; whereas `Box raw = new Box("Java")` intentionally omits the type argument for legacy code compatibility. Raw types can cause the compiler to emit `rawtypes` or `unchecked` warnings and lose element checking in subsequent operations. Do not equate a **raw type** with `Box<?>`: a wildcard is still a type-safe way of expressing that the type argument is unknown.

```java
Box<String> safe = new Box<>("Java");
Box<?> unknown = safe;
// Box<?> does not allow setting an arbitrary String value
// if the Box class has a setter taking the type parameter T itself.
```

Even when declaring `Box<String>`, the JVM normally does not create a separate runtime class `Box<String>`; this is an effect of **type erasure**, not a reason to use raw types. Details on diamond vs. raw types, warnings, and migrating legacy code are covered in depth in the next dedicated lesson.

## 9. Common Syntax and Design Mistakes

| Incorrect or Misleading Code | Problem | How to Fix |
|---|---|---|
| `new Box<T>("x")` in code that never declared `T` | `T` does not automatically stand for any type in every scope. | Use `new Box<String>("x")` or `new Box<>("x")` when context is clear enough. |
| `Box<int> b` | Primitive types cannot be used as generic type arguments. | `Box<Integer> b`. |
| `Box<String> b = new Box<>(123)` | Constructor argument is incompatible with target type `String`. | Pass a `String` or change the contract to the type actually needed. |
| `Box<String> b = new Box<Integer>(123)` | The two parameterized types are incompatible. | Use consistent type arguments on both sides. |
| `List<String> x = new List<>()` | `List` is an interface and cannot be instantiated directly. | `List<String> x = new ArrayList<>();`. |
| `var x = new ArrayList<>()` expecting it to hold only strings | Inferred type is `ArrayList<Object>`, allowing many kinds of elements. | Write `var x = new ArrayList<String>()` or `List<String> x = new ArrayList<>();`. |
| `Box b = new Box("x")` | Raw type bypasses type parameter checking; warnings may appear. | `Box<String> b = new Box<>("x");`. |
| Trying to use `Box<String>` as a subtype of `Box<Object>` | Generics are invariant. | Design the API with proper types; consider wildcards if needed. |

The compilation-error examples in the table are meant for **recognizing and fixing errors**, not as source code to run as-is.

## 10. Workflow for Applying This in Real Code

When creating a generic object, check each step in order:

1. **Determine the type contract:** must the data be `String`, `Integer`, a domain type like `Order`, or a `K, V` pair?
2. **Read the generic declaration:** how many type parameters does the class/interface have, in what order, and are there any `extends` bounds?
3. **Write a readable target type:** e.g., `List<Order> orders` or `Box<String> label`. Prefer interfaces as variable types when the API design fits.
4. **Instantiate with the right constructor:** `new ArrayList<>()`, `new Box<>("Java")`, or `new Pair<>("key", 10)`. Prefer the diamond when the compiler can infer the desired type.
5. **Avoid raw types and unchecked casts:** watch for `-Xlint:rawtypes,unchecked` warnings when integrating legacy code; do not use raw types to dodge generic errors.
6. **Review inference when using `var`:** with empty constructors and the diamond, explicitly write the type arguments after `new` if a narrower type than `Object` is needed.

A readable, common pattern in Java projects:

```java
// Inside a method, with List and ArrayList imported:
List<String> tags = new ArrayList<>();
tags.add("generics");

Box<String> label = new Box<>("Java");
String text = label.get();
```

In the final example, `tags` uses the interface type `List<String>` while the object is an `ArrayList<String>`; `label` and the `Box` object share the same type argument `String`. Types are checked at compile time, catching mismatched data early.

## 11. Self-Check

**Question 1.** In `Pair<String, Integer> pair = new Pair<>("A", 1);`, which are type parameters, which are type arguments, and which are constructor arguments?

**Question 2.** Why is `List<String> words = new ArrayList<>();` valid while `List<String> words = new List<>();` is invalid?

**Question 3.** Do the two variables below have the same type?

```java
var a = new ArrayList<>();
var b = new ArrayList<String>();
```

**Question 4.** Which declaration is valid for integers: `Box<int>` or `Box<Integer>`? Why?

**Suggested Answers:** (1) `K` and `V` are type parameters in the `Pair<K,V>` declaration; `String` and `Integer` are type arguments; `"A"` and `1` are constructor arguments. (2) `List` is an interface, whereas `ArrayList` is an instantiable class. (3) No; `a` is typically `ArrayList<Object>` while `b` is `ArrayList<String>`. (4) `Box<Integer>` because generics accept reference types, not the primitive `int`.

**Key Takeaway:** Supply type arguments to clearly express the data contract; use `new GenericClass<Type>(...)` when you want explicit specification and `new GenericClass<>(...)` when type inference is clear enough. When using `var`, empty constructors, raw types, or bounded generics, carefully verify the actual type the compiler determines.
