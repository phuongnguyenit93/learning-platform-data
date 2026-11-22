# Passing Explicit Type Arguments When Calling a Generic Method in Java

Normally, when calling a generic method, Java automatically **infers the type argument** from the passed arguments and context. However, the programmer can also **directly specify the type for the method's type parameter**. This technique is often called *explicit method type arguments* or a *type witness*.

For example, given the method:

```java
static <T> T identity(T value) {
    return value;
}
```

both of the following calls are valid when written inside a class `Demo` that declares the method above:

```java
String a = Demo.identity("Java");           // Compiler infers T = String
String b = Demo.<String>identity("Java");   // Explicitly specifies T = String
```

Point to remember: in an explicit call, **`<String>` is written after the class/object name and the dot, right before the method name**. It is a type argument for the **method**, distinct from `<T>` before the return type in the method **declaration**.

## 1. Declaring `<T>` and Passing `<String>` Are Two Different Actions

A generic method signature has a type parameter declaration:

```java
static <T> T identity(T value) {
    return value;
}
```

- `<T>`: **declares** a type parameter named `T`, used inside the method signature and body.
- `T` after `<T>`: the method's **return type**.
- `T value`: the **type of the input parameter**. Both `T` occurrences represent the same type parameter.
- `Demo.<String>identity("Hello")`: **uses** the method by supplying the type argument `String` for `T`.
- `Demo.identity("Hello")`: also uses the method, letting the compiler infer `T` based on constraints.

That is, a generic method is **declared once** and can then be called many times with different types. Specifying `<String>` does not create a separate source version or change the runtime class; ordinary Java generics still follow **type erasure**.

Comparison table:

| Context | Syntax | Role of the `<...>` Part |
|---|---|---|
| Declaring a generic method | `static <T> T identity(T value)` | Declares the type parameter name `T` |
| Calling for compiler inference | `Demo.identity("Hi")` | No type argument written; inferred at compile time |
| Calling with explicit type | `Demo.<String>identity("Hi")` | Supplies `String` for type parameter `T` |
| Declaring a generic class | `class Box<T> { ... }` | Declares `T` belonging to the class |
| Using a generic class | `Box<String> box` | Chooses `String` for the class's `T` |
| Calling a multi-type-parameter method | `Demo.<String, Integer>entry("age", 36)` | Selects in order `K = String`, `V = Integer` |

Do not call `<T>` in the signature "passing a type argument": that is **declaring a type parameter**. Conversely, `<String>` at the call site is the **explicit type argument**.

## 2. Explicit Call Syntax for `static` Methods

For a `static` generic method, the clearest and most reliable syntax is **using the class name before the dot**:

```java
Demo.<String>identity("Java");
Demo.<Integer>identity(42);
Demo.<Number>identity(42);
```

These lines are **call illustrations**; you need a class `Demo` containing `static <T> T identity(T value)` and to place the calls inside a valid method/block.

`Demo.<String>identity("Java")` means: "call `identity` and request using `T = String`". In the case `Demo.<Number>identity(42)`, the literal `42` is autoboxed to `Integer`; an `Integer` object can be used where `Number` is expected. Thus the return type at the call site is `Number`, even though the actual object is an `Integer`.

**Invalid** syntax:

```java
// Demo.identity<String>("Java"); // Wrong order in Java syntax
// Demo<String>.identity("Java"); // Invalid since class Demo is not generic
// Demo.<int>identity(42);        // Invalid: primitive is not a type argument
```

In Java, explicit type arguments are **not placed after the method name as in some other languages**. You must write `Demo.<String>identity(...)`, not `Demo.identity<String>(...)`. The type argument must also be a valid reference type; `Integer` is allowed, `int` is not.

**Is it mandatory to specify it?** No. `Demo.identity("Java")` is usually shorter, clearer, and accurately inferred by the compiler. A type witness is useful when you want to clarify type intent or when default inference does not produce the desired type.

## 3. Instance Generic Methods: Placing `<T>` After the Object's Dot

An instance method can also declare its own type parameter:

```java
class Printer {
    <T> String describe(T value) {
        return "value=" + value;
    }
}
```

When using it:

```java
Printer printer = new Printer();

String a = printer.describe(10);               // Infers T = Integer
String b = printer.<Integer>describe(10);      // Explicitly chooses T
String c = new Printer().<String>describe("x");
```

These are **combined illustrative snippets** that must be placed in an appropriate class and method context. Difference between `static` and instance:

- Static: `Utility.<T>method(...)` where the qualifier is the class name (or enclosing type).
- Instance: `receiver.<T>method(...)` where the qualifier is an object expression/reference that has that method.
- Inside an instance method of the same class, you can use `this.<T>method(...)`; for an accessible inherited method, you can use `super.<T>method(...)`.

**A type witness is attached to the method call**, not to the receiver variable's type. For example, a `Holder<String>` with method `<U> U echo(U x)` still allows `holder.<Integer>echo(5)`. `String` is the type argument of the **Holder class**, while `Integer` is the dedicated type argument of **`echo`**.

An easy mistake: writing `printer.<String>describe(10)` just because you want the result to be a String. A method's fixed String return type does not determine the type parameter `T`. When specifying `T = String`, the parameter `value` requires a String; passing an `int` does not fit. A type witness always follows **where `T` actually appears in the signature**.

## 4. Standalone Java 17 Example: Comparing Inference and Explicit Specification

Save the entire program as **`ExplicitTypeArgumentsDemo.java`**:

```java
import java.util.Collections;
import java.util.List;
import java.util.Map;

public class ExplicitTypeArgumentsDemo {
    static <T> T identity(T value) {
        return value;
    }

    static <T> List<T> two(T first, T second) {
        return List.of(first, second);
    }

    static <K, V> Map.Entry<K, V> entry(K key, V value) {
        return Map.entry(key, value);
    }

    static <T extends Number> double twice(T number) {
        return number.doubleValue() * 2;
    }

    static final class Holder<T> {
        private final T stored;

        Holder(T stored) {
            this.stored = stored;
        }

        T stored() {
            return stored;
        }

        <U> List<U> duplicate(U value) {
            return List.of(value, value);
        }
    }

    public static void main(String[] args) {
        String inferred = identity("Core");
        String explicit =
                ExplicitTypeArgumentsDemo.<String>identity("Java");
        Number widened =
                ExplicitTypeArgumentsDemo.<Number>identity(42);

        List<Number> numbers =
                ExplicitTypeArgumentsDemo.<Number>two(7, 2.5);

        Map.Entry<String, Integer> record =
                ExplicitTypeArgumentsDemo.<String, Integer>entry(
                        "age", 36);

        Holder<String> holder = new Holder<>("stored");
        List<Integer> repeated = holder.<Integer>duplicate(5);

        var inferredEmpty = Collections.emptyList();
        var typedEmpty = Collections.<String>emptyList();

        System.out.println("inferred: " + inferred);
        System.out.println("explicit: " + explicit);
        System.out.println("widened: " + widened);
        System.out.println("numbers: " + numbers);
        System.out.println("entry: " + record.getKey()
                + "=" + record.getValue());
        System.out.println("class value: " + holder.stored());
        System.out.println("method value: " + repeated);
        System.out.println("empty sizes: "
                + inferredEmpty.size() + "/" + typedEmpty.size());
        System.out.println("bound: "
                + ExplicitTypeArgumentsDemo.<Integer>twice(4));
    }
}
```

Compile and run with Java 17 or later in the directory containing the file:

```bash
javac ExplicitTypeArgumentsDemo.java
java ExplicitTypeArgumentsDemo
```

Stdout in exact order:

```text
inferred: Core
explicit: Java
widened: 42
numbers: [7, 2.5]
entry: age=36
class value: stored
method value: [5, 5]
empty sizes: 0/0
bound: 8.0
```

Analysis of the key points:

1. `identity("Core")`: the compiler infers `T = String` from the argument without needing a type witness. `ExplicitTypeArgumentsDemo.<String>identity("Java")` states the same constraint explicitly.
2. `<Number>identity(42)`: the type witness **sets the static return type to `Number`**. The input `42` is boxed into an `Integer` and can be passed to a `Number` parameter. The type witness does not turn the runtime object into a plain `Number` object; it remains an `Integer` instance.
3. `<Number>two(7, 2.5)` chooses a common type `Number` for both elements. `7` and `2.5` are boxed into `Integer` and `Double` respectively, and are then used via type `Number`. `List.of` here does not allow modifying contents via add/remove methods.
4. `<String, Integer>entry("age", 36)` supplies **two type arguments in the order** of the `<K, V>` declaration. `Map.entry` creates an entry that does not accept `null` and does not support changing `value` via `setValue`.
5. `Holder<String>` has class type parameter `T = String`. Meanwhile, `holder.<Integer>duplicate(5)` chooses `U = Integer` for the method, completely independent of the class's type parameter.
6. `Collections.emptyList()` returns an immutable empty list with method signature `<T> List<T> emptyList()`. When using `var inferredEmpty`, there is no concrete target type forcing `T = String`, so type inference picks `Object` in this example. `var typedEmpty = Collections.<String>emptyList()` keeps the variable's compile-time type as `List<String>`. Both lists have size 0; the difference does not show up in stdout, but lies in the **static type**.
7. `<Integer>twice(4)` sets `T = Integer`, a subtype of `Number`; `doubleValue()` returns `4.0`, which multiplied by 2 gives `8.0`.

**Note:** the fact that a method allows specifying a wider type (`<Number>`) does not mean any arbitrary type is valid. `<String>twice("4")` is invalid because `String` does not satisfy the bound `T extends Number`.

## 5. When Are Explicit Type Arguments Truly Useful?

### 5.1. When There Are No Arguments to Infer `T`

A classic example from Java Collections:

```java
List<String> a = Collections.emptyList();         // Inferred from target type
var b = Collections.<String>emptyList();         // Explicitly chooses type
```

These two lines are **illustrative snippets** requiring `List` and `Collections` imports inside a method. Both have type `List<String>`. On the first line, **target typing** from the left provides the constraint; on the second line, `<String>` provides the constraint right at the call site even though the variable's type is inferred via `var`.

This is especially useful when a generic method **returns a type involving `T` without taking any parameter carrying `T`**, such as `Collections.<String>emptyList()`. If you merely call `Collections.emptyList()` in a context that does not require a specific element type, the compiler may choose `Object`.

### 5.2. When You Intentionally Want the API to Return a Wider Type

```java
List<Number> values =
        ExplicitTypeArgumentsDemo.<Number>two(7, 2.5);
```

In the example, `Integer` and `Double` are both usable as `Number`. Writing a type witness clearly expresses **the decision to use a common type**. Without it, the compiler can still infer an appropriate common type (depending on constraints/target type); an explicit type argument mainly clarifies or locks in intent.

`<Number>` does not automatically coerce arbitrary values into valid numbers: calling `two("seven", 2.5)` when requiring `T = Number` will not compile.

### 5.3. When Context Makes Inference Hard to Read or Fails to Reach the Needed Type

A nested call can involve multiple inference constraints at once. If the compiler infers something unintended, specifying a type witness **at the relevant generic method itself** shows both readers and the compiler the target type. For example:

```java
static <T> List<T> empty() {
    return List.of();
}

// When used:
var texts = Helper.<String>empty();
```

This is an **illustration**, assuming `empty` is in class `Helper` with `List` imported. `texts` will have type `List<String>`, instead of letting the compiler pick a type parameter from an information-poor context.

Before adding an explicit type argument, also consider **declaring the variable with an explicit target type**:

```java
List<String> texts = Helper.empty();
```

With a target type available, the compiler usually infers it and the call is shorter. A type witness does not always make a program better.

### 5.4. When Writing Tutorial Examples or Testing Generic APIs

In API documentation or compile-time tests, `Utility.<Long>identity(1L)` helps show that the method was invoked with `T = Long`. In production code, however, if `Utility.identity(1L)` is already clear and safe, inference is usually preferred.

## 6. Explicit Type Arguments Must Obey the Method Signature

**A type witness is not a cast** and cannot be used to bypass the type contract.

Consider `static <T> T identity(T input)`, using the example file with class `ExplicitTypeArgumentsDemo`:

```java
String text =
        ExplicitTypeArgumentsDemo.<String>identity("hello"); // Valid

Number number =
        ExplicitTypeArgumentsDemo.<Number>identity(12); // Valid

// String invalid =
//         ExplicitTypeArgumentsDemo.<String>identity(12); // Does not compile
```

In the error case, `<String>` requires the input parameter to be `String`, yet `12` is an `int` and there is no valid invocation conversion from `int` to `String`. You cannot "command the compiler" to treat any argument as a `String` merely via `<String>` syntax.

If the type parameter has a bound:

```java
static <T extends Number> double twice(T value) {
    return value.doubleValue() * 2;
}
```

then only type arguments satisfying the bound are valid:

```java
double ok = ExplicitTypeArgumentsDemo.<Integer>twice(3);
double alsoOk = ExplicitTypeArgumentsDemo.<Number>twice(3);

// double wrong =
//         ExplicitTypeArgumentsDemo.<String>twice("3"); // Violates bound
```

These snippets are **illustrative code**; the `twice` method in the standalone runnable example already has its proper body. Note that `T = Number` is still valid because `Number` satisfies the upper bound `Number`.

Similarly, if a method has **two type parameters** `<K, V>`, an explicit call must supply both type arguments in the exact order: `ClassName.<String, Integer>entry(...)`. You cannot write only `ClassName.<String>entry(...)` and ask the compiler to fill in `V` separately within that type argument list; Java does not allow mixing a partial explicit type argument list with inference for the remaining parts in that way.

## 7. Contexts to Distinguish

### Generic Methods Differ from Generic Classes

```java
class Store<T> {
    T read() {
        return null;
    }

    <U> U echo(U value) {
        return value;
    }
}
```

In the illustrative class, `read()` returns `T` belonging to **class `Store<T>`** and does not declare a new type parameter of its own. Therefore `store.<String>read()` is **not a way to re-specify the class's `T`**. The type of `T` is chosen when declaring the variable/object, such as `Store<Integer> store = new Store<>();`.

Conversely, `store.<String>echo("x")` specifies a separate type argument for the generic method `echo`, and it can differ from `Store`'s type argument `Integer`.

### Generic Methods with a Fixed Return Type

```java
static <T> void print(T value) {
    System.out.println(value);
}
```

You can call `Utility.<String>print("Hi")` (assuming the method is in `Utility`). Returning `void` does not prevent it from being a generic method; the type witness still applies to the **input parameter**. Conversely, a type witness **does not change** the method's return type: if a method returns `int`, choosing `<String>` does not make it return `String`.

### Generic Constructors

A constructor can have its own type parameter; however, **the syntax for passing a type argument to a constructor** is not like calling a method after a dot. In a generic constructor call, type arguments can be placed after `new` and before the class name:

```java
class Message {
    <T> Message(T input) {
        System.out.println(input);
    }
}

// new <String> Message("Hi");
```

This is an **illustration**, not part of the `ExplicitTypeArgumentsDemo` program. The syntax `new <String> Message("Hi")` belongs to a generic constructor, whereas `Utility.<String>method("Hi")` belongs to a generic method. Do not mix up these two declaration/specification positions.

### Generic Type Arguments and Primitives

You cannot supply `int` as a type argument: `Utility.<int>identity(5)` is invalid, while `Utility.<Integer>identity(5)` is valid. If you call `identity(5)` for compiler inference, autoboxing allows `T` to be represented by the wrapper type `Integer`, not the primitive `int`.

## 8. Syntax When Calling an Instance Method via `this`, `super`, or an Expression

Besides a class name (`static` call), a call with a receiver also accepts a type witness:

```java
class Base {
    <T> T copy(T value) {
        return value;
    }
}

class Child extends Base {
    String example() {
        String viaThis = this.<String>copy("one");
        String viaSuper = super.<String>copy("two");
        return viaThis + "/" + viaSuper;
    }
}
```

Both classes above are **illustrative snippets**. `Child.example()` returns `"one/two"`. `this.<String>copy(...)` calls through the current receiver; `super.<String>copy(...)` calls the accessible superclass implementation under normal `super` rules. A type witness does not alter inheritance or dispatch mechanisms; it only specifies the type for the generic method.

An expression returning an object can also serve as the receiver:

```java
String a = new Printer().<String>echo("A");
```

Here assume `Printer` has a generic instance method `<T> T echo(T value)`. The key position is still **after the dot and before the method name**. Do not write `new Printer()<String>.echo("A")`; that is not valid method invocation syntax.

## 9. Type Inference and Overloads: Do Not Use a Type Witness to Force Overload Selection

When multiple methods share the same name, Java uses **overload resolution** rules (considering argument types, applicability, specificity, etc.) to select a method at compile time. Explicit generic type arguments can affect whether a generic candidate is applicable, yet **do not guarantee forcing any arbitrary overload** when other overloads exist.

If you encounter an ambiguous call or an unexpected overload choice, you should:

1. Check the **signatures** and bounds of the generic methods sharing that name.
2. Inspect the **static** types of arguments and the return context.
3. Try a valid type witness if the goal is to set a type argument for a generic candidate.
4. When you need to select an overload by a clear parameter type, consider changing the argument expression to a valid type, renaming the method, or redesigning the overloads to avoid ambiguity.

For instance, `<T>` on a method does not carry its own runtime identity to overload against `Object`. These two signatures in the same class **collide after type erasure**, so they do not compile:

```java
void log(Object value) { }

<T> void log(T value) { }
```

This is a **separate error example**: unbounded `T` erases to `Object`, so the two methods have the same JVM signature. Calling with `<String>` cannot fix a signature collision at the declaration level.

## 10. Type Erasure: Specifying `<T>` Does Not Store the Type at Runtime

When writing:

```java
String value = Utility.<String>identity("x");
```

the compiler understands `T = String` for the call, using it to check parameters and return type. However, generic methods in Java are typically implemented via **type erasure**:

- An unbounded type parameter like `T` is typically erased to `Object`.
- The compiler checks constraints and may insert casts where the result is consumed.
- No separate `identity<String>` and `identity<Integer>` are generated at runtime just because the type witnesses differ.
- You cannot directly ask an instance: "which `T` was this method just called with?" unless that information is carried by another mechanism.
- A type witness does not make a wrong cast safe; type errors are caught at compile time whenever possible.

To know a runtime class explicitly, an API can accept `Class<T>`:

```java
static <T> T checkedCast(Class<T> type, Object value) {
    return type.cast(value);
}
```

This is an **illustrative method** that must be declared inside a class. The call `Utility.<String>checkedCast(String.class, someObject)` both specifies the type argument `String` and passes the **runtime type token** `String.class`; `Class.cast` itself checks the object at runtime. A type witness alone does not perform that runtime check. When `T` represents types with nested generic type arguments, `Class<T>` also does not retain every type argument such as `List<String>`; a suitable type token design is needed if requirements are more complex.

## 11. Common Syntax and Usage Mistakes

**Mistake 1: Placing the type argument after the method name.** `Utility.identity<String>("x")` is invalid Java syntax. Fix it to `Utility.<String>identity("x")`.

**Mistake 2: Confusing class type arguments with method type arguments.** `Holder<String>` picks the type for the class; `holder.<Integer>duplicate(5)` picks a separate type for the method. You cannot use a type witness at a call site to change the type parameter of an existing class instance.

**Mistake 3: Specifying a primitive as a type argument.** `Utility.<int>identity(5)` is invalid. Use `<Integer>` or omit the type witness so the compiler infers it via boxing.

**Mistake 4: Specifying only part of a multi-type-parameter method's type arguments.** If `<K, V>` is declared, you must write all of `<String, Integer>` when writing explicitly; do not write only `<String>`. If you want both inferred, omit the entire explicit list.

**Mistake 5: Choosing a type argument incompatible with the input type.** `Utility.<String>identity(42)` is invalid because `42` cannot be passed to a `String` parameter. A type witness is not a cast.

**Mistake 6: Choosing a type argument that violates a bound.** Given `<T extends Number>`, `<String>` is invalid. Bounds are still fully checked by the compiler even when the type argument is written explicitly.

**Mistake 7: Adding type witnesses to every call without benefit.** `Utility.<String>identity("x")` is valid, yet `Utility.identity("x")` is usually clear enough. Explicit type arguments should clarify or solve a genuine type need rather than cluttering code.

**Mistake 8: Thinking a type witness changes a fixed return type.** Given `<T> int size(List<T> input)`, the return type is always `int`; `Utility.<String>size(...)` does not turn the return type into `String`.

**Mistake 9: Confusing `var` with explicit type arguments.** `var x = Collections.emptyList()` lets the compiler infer the variable type from the call; `var x = Collections.<String>emptyList()` specifies `String` for the method. `var` does not automatically mean "`T = String`".

**Mistake 10: Misunderstanding that `List<Integer>` is converted to `List<Number>` by a witness.** Generics are generally invariant. `List<Integer> integers` cannot be directly assigned to `List<Number>`. A type witness on a method creating a new list can help design a matching **result type**, yet it does not change the subtyping relationship between two existing list types.

**Mistake 11: Thinking an explicit type argument makes the runtime object change class.** `<Number>identity(42)` returns a reference viewed as `Number` at compile time; the object still belongs to class `Integer`. There is no behavior turning `Integer` into a separate `Number` instance.

**Mistake 12: Thinking every method accepts `.<T>`.** Not every method declares its own type parameter. If there is only `class Box<T>` and `T get()` has no `<U>`, you cannot use `box.<String>get()` to override the class's `T`. Identify the **generic method declaration** properly before calling.

## 12. Self-Check Practice Exercises

**Question 1.** Given `static <T> T identity(T x)`. How do you explicitly pass `T = String` through class name `Util`?  
**Answer:** `Util.<String>identity("abc")`.

**Question 2.** Does `Util.identity("abc")` differ from `Util.<String>identity("abc")` in return value in this case?  
**Answer:** no; both return the string `"abc"` and have the appropriate static type `String`. The first call uses inference; the second specifies explicitly.

**Question 3.** Why is `Util.<int>identity(5)` invalid?  
**Answer:** a generic method's type argument in Java 17 must be a reference type; use `Integer`.

**Question 4.** Given `static <K, V> Map.Entry<K, V> entry(K k, V v)`, how do you write it if you want `K = String`, `V = Long`?  
**Answer:** `Util.<String, Long>entry("id", 1L)`.

**Question 5.** `Holder<String>` has a method `<U> U echo(U x)`. Can you call `holder.<Integer>echo(10)`?  
**Answer:** yes; the method's type parameter `U` is independent of the Holder class's type parameter `T`.

**Question 6.** Why does `var xs = Collections.<String>emptyList()` preserve `String` in its static type?  
**Answer:** `<String>` selects `T = String` for the method `<T> List<T> emptyList()`; `var` takes the resulting expression's type `List<String>`.

**Question 7.** Can you write `Util.<String>identity(42)` so the compiler automatically converts `42` to a string?  
**Answer:** no; there is no valid parameter-passing conversion from `int` to `String`.

**Question 8.** Given `static <T extends Number> double twice(T value)`, is `Util.<Number>twice(5)` valid?  
**Answer:** yes. `Number` satisfies the bound; `5` is boxed into `Integer`, which can be used as `Number`.

**Question 9.** Does `<String>` in `Util.<String>identity(...)` create a separate runtime class/method?  
**Answer:** no; ordinary Java generics use type erasure. Type witnesses serve compile-time type checking and inference.

**Question 10.** When should you omit a type witness?  
**Answer:** when the compiler infers accurately and the call is unambiguous, such as `identity("abc")`. Specify explicitly when you need to preserve a particular type, clarify intent, or help satisfy constraints.

**Question 11.** Where is an explicit type argument placed when calling an instance method?  
**Answer:** after the receiver expression and the dot, right before the method name: `obj.<String>echo("abc")`.

**Question 12.** Can a method `static List<String> words()` accept `Util.<Integer>words()` just because its return type is generic `List<String>`?  
**Answer:** there is no method type parameter to set to `Integer`; the signature `words()` returns a fixed `List<String>`.

Remember the two distinct patterns: **declaration** `static <T> T method(T x)` and **explicit call** `ClassName.<String>method("x")`. One defines the type parameter; the other chooses the type argument for a single call. In most cases, the compiler infers well on its own; when choosing explicitly, the chosen type must still satisfy all parameters, bounds, and Java's type-safety rules.