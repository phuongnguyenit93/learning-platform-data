# Types of Members Accessed Through a Raw Type in Java Generics

## 1. The Problem: Same Class, Yet the Call's Type Can Differ

Consider a generic class:

```java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T next) {
        value = next;
    }
}
```

When accessed through `Box<String>`, the compiler knows `T` corresponds to `String`: `get()` is seen as returning `String`, and `set(...)` accepts `String`.

However, if you use the **raw type** `Box` (omitting the type argument list `<...>`), the types of its members can change right during **source-level type checking at the access site**:

```java
Box<String> typed = new Box<>("Java");
Box raw = typed;

String a = typed.get();  // Valid: result has type String
Object b = raw.get();    // Valid: T erased to Object
raw.set(42);             // Compiles, but with unchecked warning
```

This is an **illustrative snippet**; place it inside a method to compile. Using raw `Box` does not create a different runtime class; it drops part of the generic guarantees the compiler has when type arguments are known.

> **Core rule:** For constructors, instance methods, and non-static fields declared directly on a generic type `C` (not members inherited from a superclass or superinterface), when accessed through the **raw type `C`**, the type of the member is computed as the **erasure** of the member's type in the generic declaration of `C`. There are important exceptions for static members and inherited members.

Therefore, the question "what type does this member have?" must consider **the static type of the receiver expression**, not just the class declaration and not just the object's runtime class.

## 2. What Is a Raw Type, and How Does It Differ from a Parameterized Type?

A declared class:

```java
class Holder<T> { }
```

Can be used in several forms:

| Usage | Meaning |
| --- | --- |
| `Holder<String>` | Parameterized type; `T` is `String` during type checking |
| `Holder<Integer>` | Parameterized type; `T` is `Integer` |
| `Holder<?>` | Parameterized type with wildcard: an unknown type argument, still preserving generic constraints |
| `Holder` | **Raw type**: omits type arguments, compatible with pre-generics Java code |
| `Holder<Object>` | Parameterized type with `T` specifically `Object`; not the same as raw `Holder` |

You cannot arbitrarily assign `Holder<String>` to `Holder<Object>`, because Java generics are **invariant** by default. Meanwhile, for legacy compatibility reasons, raw types have looser conversion rules and can generate `rawtypes` or `unchecked` warnings.

Both `Holder<?>` and raw `Holder` can read the value of `T` as `Object` when `T` is unbounded, yet they **differ sharply when calling a method taking `T`**, using a generic method, or accessing a member with its own type argument.

### Why does Java still have raw types?

Generics were added to Java after many APIs and libraries already existed. Raw types support **migration compatibility**: old code using `List`, `Map`, `Class` can continue compiling and interacting with generic code. In exchange, the compiler cannot guarantee that all such calls satisfy the new type contracts.

In new code, when the type argument is unknown, `Holder<?>` is usually more appropriate and safer than `Holder`. Raw types should mainly appear at boundaries with legacy code, when working with APIs that intentionally use raw types, or in examples explaining type erasure.

## 3. Rules for Instance Fields, Methods, and Constructors

According to Java Language Specification §4.8, for raw type `C`:

1. **Constructors of `C`** are viewed with the erased types of constructors in the generic declaration `C`.
2. **Instance methods declared by `C`**, if not inherited members, are viewed with the erasure of their method types.
3. **Non-static fields declared by `C`**, if not inherited members, are viewed with the erasure of their field types.
4. **Static methods and static fields of `C`** keep their types as in the generic declaration; they are not "raw-ified" merely because `C` is a generic class.
5. **Inherited instance methods and fields** have their own rule: the member's type is determined in *the supertype of `C` that declares that member*. Thus you must not state that every inherited member on a raw receiver automatically becomes raw in the exact same way.

Erasure of basic constructs:

| Type in declaration | Type after erasure |
| --- | --- |
| `T` for `<T>` | `Object` |
| `T` for `<T extends Number>` | `Number` |
| `T` for `<T extends Number & Comparable<T>>` | `Number` (leftmost bound) |
| `List<T>` | Raw `List` |
| `List<String>` | Raw `List` |
| `Map<String, T>` | Raw `Map` |
| `T[]` for `<T>` | `Object[]` |
| `T[]` for `<T extends Number>` | `Number[]` |
| `String` | `String` (unchanged) |
| `int` | `int` (unchanged) |

**Common pitfall:** An instance method in `Box<T>` with return type `List<String>` can still be seen as returning raw `List` when accessed through raw `Box`. The rule does not only erase places containing `T`; it applies erasure to **the type of the member** in the raw-type context.

At the same time, the compiler seeing the erasure at the call site does not rewrite the source declaration of `Box<T>` and does not alter other places using `Box<String>`.

## 4. Runnable Example: Same Object via Typed and Raw Receivers

Create file `RawMemberTypesDemo.java`:

```java
import java.util.List;

public class RawMemberTypesDemo {

    static class Box<T> {
        private T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T next) {
            value = next;
        }

        List<String> fixedLabels() {
            return List.of("A", "B");
        }

        <U> U ownEcho(U value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> typed = new Box<>("start");

        String first = typed.get();
        List<String> labels = typed.fixedLabels();
        String echo = typed.ownEcho("hello");

        System.out.println(first);
        System.out.println(labels.get(1));
        System.out.println(echo);

        Box raw = typed;

        Object rawValue = raw.get();
        List rawLabels = raw.fixedLabels();
        Object rawEcho = raw.ownEcho("hello");

        System.out.println(rawValue);
        System.out.println(rawLabels.get(0));
        System.out.println(rawEcho);

        raw.set(123);
        System.out.println(raw.get());

        try {
            String result = typed.get();
            System.out.println(result);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac RawMemberTypesDemo.java
java RawMemberTypesDemo
```

Stdout:

```text
start
B
hello
start
A
hello
123
ClassCastException
```

The program may display a note about unchecked operations during compilation. To ask the compiler to print detailed raw/unchecked warnings, run:

```bash
javac -Xlint:rawtypes -Xlint:unchecked RawMemberTypesDemo.java
```

The line `Box raw = typed;` uses a raw type. The line `raw.set(123)` is a dangerous call because `set(T)` has parameter type `Object` after erasure; the compiler no longer checks that `123` is compatible with `String` that `typed` was intended to hold.

### Step-by-step explanation

**Phase using receiver `typed`:**

- `typed` has type `Box<String>`.
- `typed.get()` has static type `String`.
- `typed.fixedLabels()` has static type `List<String>`.
- `typed.ownEcho("hello")` is a generic method call; the compiler can infer `U = String`, so the result is `String`.

**Phase using receiver `raw`:**

- `raw` has raw type `Box`.
- `raw.get()` has static type `Object` because the erasure of unbounded `T` is `Object`.
- `raw.fixedLabels()` has raw type `List`, even though the source method declares `List<String>`.
- `raw.ownEcho("hello")` has type `Object`; type inference `U = String` for the generic instance method declared by the class is no longer provided in the raw receiver context.

**Phase causing runtime failure:**

- `raw.set(123)` writes an `Integer` into the same object referenced by `typed`.
- `raw.get()` returns `Object`, so it can print `123`.
- When the program assigns `typed.get()` to `String`, the compiler compiled the call using `Box<String>` and inserted a check/cast for `String`.
- The actual stored object is `Integer`, so the cast fails with `ClassCastException`.

This is an example of **heap pollution**: the runtime state no longer matches the generic contract of the `Box<String>` reference. The raw type lets the bug slip past compilation, but does not magically turn an `Integer` into a `String`.

## 5. Why Can a Method That Does Not Use `T` Still Be Raw-ified?

This is the part that surprises people most.

Consider the declaration:

```java
class Repository<T> {
    java.util.List<String> names() {
        return java.util.List.of("Lan", "Mai");
    }
}
```

This is a valid class without `main`. The method `names()` **does not use `T` in its return type**, so why does accessing it through raw `Repository` still have type `List` instead of `List<String>`?

Because the raw member rule examines **the type of the instance method** in the generic class declaration. The erasure of return type `List<String>` is raw `List`. The compiler applies erasure to the method's corresponding signature when the receiver is raw `Repository`.

Distinguish:

```java
Repository<Integer> typed = new Repository<>();
java.util.List<String> good = typed.names(); // Valid

Repository raw = typed;
java.util.List unchecked = raw.names();      // Static type raw List
```

If you write:

```java
// Example compiling with an unchecked conversion warning.
java.util.List<String> risky = raw.names();
```

Java may allow an **unchecked conversion** from raw `List` to `List<String>` and emit a warning; there is no runtime proof that all elements are `String`. Even though `names()` actually returns strings here, the compiler applies the general raw type rule.

Do not remove warnings with `@SuppressWarnings("unchecked")` just to keep builds "clean". Fix the type flow so you continue using a parameterized receiver.

## 6. A Generic Instance Method Declaring Its Own `<U>` Is Also Affected

A generic method can declare its own type parameter, independent of the class's type parameter:

```java
class Converter<T> {
    <U> U identity(U value) {
        return value;
    }
}
```

On a `Converter<String>` receiver:

```java
Converter<String> typed = new Converter<>();
String text = typed.identity("abc"); // U is inferred as String
```

On a raw `Converter` receiver:

```java
Converter raw = typed;
Object result = raw.identity("abc"); // Result after erasure is Object
```

These lines are illustrative only and must be placed inside a suitable class/method to run. The key point is that a method **declared by the generic class `Converter<T>`** falls under the raw member rule, even though `<U>` does not depend on `T`.

The generic method's own type parameter is also erased in this context. If `<U>` is unbounded, `U` erases to `Object`; if the method declares `<U extends Number>`, `U` erases to `Number`.

**Predicting types before writing code** is a useful skill:

| Expression | Static type of result |
| --- | --- |
| `typed.identity("abc")` | `String` (compiler infers `U`) |
| `raw.identity("abc")` | `Object` |
| `typed.identity(12)` | `Integer` |
| `raw.identity(12)` | `Object` |

Using explicit type arguments is not a fix for raw-type design:

```java
// Intentionally invalid: instance generic method of raw receiver has been erased.
String s = raw.<String>identity("abc");
```

The proper approach is to keep a parameterized reference when possible, such as `Converter<?>`, or extract the generic algorithm into an appropriate utility.

## 7. Bounded Type Variables: The Result Is Not Necessarily `Object`

The anchor point of erasure is the **leftmost bound** of the type variable. Unbounded `<T>` defaults to `Object`, whereas `<T extends Number>` erases to `Number`.

Runnable program example, file `BoundedRawMemberDemo.java`:

```java
public class BoundedRawMemberDemo {

    static class NumberBox<T extends Number> {
        private T value;

        NumberBox(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }

        double doubled() {
            return value.doubleValue() * 2;
        }
    }

    public static void main(String[] args) {
        NumberBox<Integer> typed = new NumberBox<>(5);
        NumberBox raw = typed;

        Number number = raw.get();
        System.out.println(number.intValue());
        System.out.println(raw.doubled());

        raw.set(2.5);
        System.out.println(raw.get().doubleValue());

        try {
            Integer integer = typed.get();
            System.out.println(integer);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Compile and run:

```bash
javac BoundedRawMemberDemo.java
java BoundedRawMemberDemo
```

Stdout:

```text
5
10.0
2.5
ClassCastException
```

Explanation:

- With `T extends Number`, raw `NumberBox` views `get()` as returning `Number` and `set(...)` as taking `Number`.
- Even though `typed` is `NumberBox<Integer>`, `raw.set(2.5)` passes the `Number` parameter (with an unchecked warning). The `Integer` contract is broken.
- `raw.get()` yields `Number` and can call `doubleValue()` directly.
- `typed.get()` in source is seen as `Integer`; when a cast is needed, the runtime discovers the actual value is `Double` and throws `ClassCastException`.

If the bound is `<T extends Number & Comparable<T>>`, erasure is still `Number`. The `Comparable<T>` interface in the subsequent position of the intersection bound does not change the erased type of `T` to `Comparable`.

Do not conclude from the first example that raw `get()` **always** returns `Object`; you must check the type variable's bound.

## 8. Constructors Viewed via Erasure When Creating Objects with a Raw Type

Constructors are a common case when migrating legacy code. If a class declares:

```java
class Envelope<T> {
    Envelope(T content) {
    }
}
```

Then creation with a declared type argument:

```java
Envelope<String> typed = new Envelope<>("hello");
```

lets the compiler check `T = String`. Conversely:

```java
Envelope raw = new Envelope("hello");
```

uses raw `Envelope`. The constructor taking `T` is viewed through erasure as taking `Object`, and the compiler may warn on the call because the formal parameter changed under erasure.

Do **not misunderstand** that `new Envelope("hello")` creates a different runtime class than `new Envelope<String>("hello")`. Both are instances of `Envelope` described by the same class name. The difference is whether the compiler still tracks the generic type argument.

For constructors with their own generic type parameters, the same erasure logic applies in the appropriate raw `Envelope` cases; static factory methods do not follow this exact rule merely by living inside a generic class—see the next section on static members.

## 9. Static Fields and Static Methods: An Important Exception

A static member does not depend on any individual generic instance. Java also forbids static members from directly referencing the enclosing class's type parameter `T` as an instance-specific type.

Consider the program `RawStaticMemberDemo.java`:

```java
import java.util.List;

public class RawStaticMemberDemo {

    static class Container<T> {
        static List<String> labels = List.of("red", "blue");

        static <U> U staticEcho(U value) {
            return value;
        }

        <U> U instanceEcho(U value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Container raw = new Container();

        List<String> names = Container.labels;
        String first = Container.staticEcho("hello");

        Object instanceResult = raw.instanceEcho("hello");

        System.out.println(names.get(0));
        System.out.println(first);
        System.out.println(instanceResult);
    }
}
```

Compile and run:

```bash
javac RawStaticMemberDemo.java
java RawStaticMemberDemo
```

Stdout:

```text
red
hello
hello
```

`Container.labels` continues to have type `List<String>`, and `Container.staticEcho("hello")` continues to use the generic method so the compiler infers `U = String`. Meanwhile, `raw.instanceEcho("hello")` returns `Object` under the raw instance method rule.

Accurate conclusion:

- **A raw receiver** changes the types of certain **instance members** falling under §4.8.
- **Static members** of a generic class are not further erased just because you used a raw receiver.
- Static fields/methods still undergo erasure in bytecode under the general rules of Java Generics, yet in **source code** callers still receive the full generic declaration of the static member.

Access static members by class name `Container.staticEcho(...)`, not through an instance variable: this is clearer and avoids confusion about the receiver.

## 10. Inherited Members: You Cannot Apply One Blanket "Erase Everything" Rule

JLS §4.8 specifies separately that the type of an **inherited instance method or non-static field** must be determined in **the supertype of raw `C` that declares that member**. This creates situations where an inherited generic method retains its generic signature.

Create file `InheritedRawMemberDemo.java`:

```java
public class InheritedRawMemberDemo {

    static class Base {
        <U> U inheritedEcho(U input) {
            return input;
        }
    }

    static class Container<T> extends Base {
        <U> U ownEcho(U input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Container raw = new Container();

        String inherited = raw.inheritedEcho("kept");
        Object own = raw.ownEcho("erased");

        System.out.println(inherited);
        System.out.println(own);
    }
}
```

Run:

```bash
javac InheritedRawMemberDemo.java
java InheritedRawMemberDemo
```

Stdout:

```text
kept
erased
```

`inheritedEcho` is declared in `Base`, which is a **non-generic superclass**. Having a receiver of raw type `Container` does not force this generic method to become raw, because the member inherited via supertype `Base` keeps `Base`'s own generic contract.

Conversely, `ownEcho` is declared **on the generic class `Container<T>`**: when using raw `Container`, the method type is viewed via erasure, so `raw.ownEcho("erased")` returns `Object`.

### When the superclass itself is generic

Do not deduce that every inherited generic method always stays unchanged. Consider:

```java
class Parent<X> {
    X read() {
        return null;
    }
}

class Child<T> extends Parent<T> {
}
```

This is a valid class snippet without `main`. If you use raw `Child`, the corresponding supertype of `Parent<T>` is also erased under the supertypes rule for raw types. Therefore, the `read()` member inherited from `Parent` in that context can be seen via the erasure of `Parent`, which here is `Object`.

**Proper checking method:** Find the class/interface that **originally declares** the member, then check the corresponding supertype of the receiver. Do not assume that merely knowing the receiver is raw means every inherited generic method loses its type parameters.

## 11. Comparing a Raw Receiver with Wildcard `<?>`

Raw `Box` and parameterized `Box<?>` can both read `get()` as `Object` when `T` is unbounded. However, the wildcard still protects generic consistency.

File `WildcardInsteadOfRawDemo.java`:

```java
import java.util.List;

public class WildcardInsteadOfRawDemo {

    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        List<String> fixedLabels() {
            return List.of("A", "B");
        }

        <U> U echo(U input) {
            return input;
        }
    }

    public static void main(String[] args) {
        Box<String> strings = new Box<>("Java");
        Box<?> unknown = strings;

        Object value = unknown.get();
        List<String> labels = unknown.fixedLabels();
        String echoed = unknown.echo("safe");

        System.out.println(value);
        System.out.println(labels.get(1));
        System.out.println(echoed);
    }
}
```

Run:

```bash
javac WildcardInsteadOfRawDemo.java
java WildcardInsteadOfRawDemo
```

Stdout:

```text
Java
B
safe
```

Practical differences:

- `Box<?>` is still a **parameterized type**, so `fixedLabels()` retains type `List<String>`.
- Its own generic method `<U> U echo(U)` still allows inferring `U = String`.
- `get()` has type `Object` when `T` is unbounded, because the actual argument for `T` is unknown.
- If `Box<T>` has `void set(T)`, on `Box<?>` the compiler **refuses** arbitrary `"hello"` or `123` arguments passed to `set`, because it cannot prove they match the type represented by the wildcard. Normally only `null` can be passed to `set(T)` in this context.

A snippet that intentionally **does not compile**:

```java
Box<?> unknown = new Box<String>("Java");
unknown.set("other"); // Actual T is unknown
```

`Box<?>` preserves safety when `T` is unknown; raw `Box` drops the type barrier and may permit incompatible writes with an unchecked warning. Thus wildcards are better when an API simply wants "any Box" and does not need to assign new elements.

## 12. Field Access Cases: Reading, Assigning, and Warnings

A field declared with `T` or `List<T>` is also subject to raw member typing when accessed through a raw receiver.

```java
import java.util.List;

class Row<T> {
    T item;
    List<T> items;
    List<String> names;
}
```

This is a valid class snippet for analysis, without `main`.

With `Row<Integer> typed`:

- `typed.item` has type `Integer`.
- `typed.items` has type `List<Integer>`.
- `typed.names` has type `List<String>`.

With `Row raw`:

- `raw.item` has type `Object` due to erasure of `T`.
- `raw.items` has raw type `List` due to erasure of `List<T>`.
- `raw.names` also has raw type `List`, even though it does not directly depend on `T`.

Warning scenarios are not identical:

1. **Assigning to a field of a raw receiver** such as `raw.item = "text"` or `raw.items = someList` can be reported as an unchecked operation if erasure alters the field type.
2. **Calling a method on a raw receiver** can produce unchecked warnings when erasure alters the method's formal parameter types, such as `raw.set("text")` when declared as `set(T)`.
3. **Reading a raw value and assigning it to a parameterized type**, for example `List<String> names = raw.names`, can trigger an **unchecked conversion** from raw `List` to `List<String>`.
4. Not **every** operation on a raw receiver always emits an `unchecked` warning. Reading a result erased to `Object` often simply yields type `Object`; the compiler may warn at the raw-type declaration (`rawtypes`), which is a different warning category.

The distinction between `rawtypes` and `unchecked` is helpful when fixing code: one reports **omitted type arguments**, while the other usually points to **an operation not fully verified by the compiler**. Suppress warnings only after proving a legacy boundary safe and keeping scope minimal.

## 13. Method Return Types and Parameter Types Can Be Affected Differently

Consider the declaration:

```java
class Service<T> {
    T get() {
        return null;
    }

    void accept(T input) {
    }

    java.util.List<String> names() {
        return java.util.List.of();
    }

    void print(String message) {
        System.out.println(message);
    }
}
```

The entries below are for type reasoning and should be placed in an appropriate method.

| Member | Via `Service<String>` | Via raw `Service` |
| --- | --- | --- |
| `get()` | Returns `String` | Returns `Object` |
| `accept(...)` | Accepts `String` | Accepts `Object` |
| `names()` | Returns `List<String>` | Returns raw `List` |
| `print(...)` | Accepts `String` | Still accepts `String` |
| `getClass()` | Returns `Class<? extends ...>` per `Object.getClass()` rules | Per inherited declaration from `Object`, does not mechanically apply raw member rules of `Service` |

For `print(String)`, the erasure of `String` is still `String`, so the call does not turn into `print(Object)`.

An API can lose its **generic return type** even when the method takes no parameters; meanwhile, an unchecked warning on a **method invocation** under raw-type rules relates directly to erasure altering **formal parameter types**. Thus, seeing no warning on `raw.names()` **does not prove** the result is still `List<String>`.

## 14. Type Erasure in Bytecode vs. Type at the Call Site

Distinguish two stages:

1. **Source code:** The compiler knows whether the receiver is `Box<String>`, `Box<?>`, or raw `Box`, thereby determining expression static types and allowed operations.
2. **Bytecode:** Generic types are represented via erasure in descriptors, together with appropriate cast instructions; the compiler can record generic `Signature` metadata for tools/reflection to inspect declaration info.

Example declarations in `Box<T>`:

```java
T get() { return value; }
void set(T value) { this.value = value; }
java.util.List<String> fixedLabels() {
    return java.util.List.of("A", "B");
}
```

With unbounded `<T>`, the corresponding JVM descriptors are:

```text
get:         ()Ljava/lang/Object;
set:         (Ljava/lang/Object;)V
fixedLabels: ()Ljava/util/List;
```

If you compile `RawMemberTypesDemo` from the earlier section, you can run:

```bash
javap -p -s 'RawMemberTypesDemo$Box'
javap -p -v 'RawMemberTypesDemo$Box'
```

`javap -s` shows the descriptors. `javap -v` can show the generic `Signature` preserving traces of `T` and `List<String>` in the declaration. Constant pool `#` indices or instruction offsets may vary between JDK versions; what to observe is **the relationship between erased descriptors and generic metadata**.

The exact same descriptor `get(): Object` in the class file can still be seen as `String` in Java source when the receiver is `Box<String>`, thanks to compile-time type checking and casts inserted at the use site. With raw `Box`, `String` information has been dropped from the receiver expression's type, so the compiler will not assign the result to a `String` variable without an explicit cast.

**There is no separate copy of `get()` generated for each `T`** just because it is called through `Box<String>` or `Box<Integer>`. It is whether the compiler retains or drops generic information at the call site that makes the difference.

## 15. Connection to Bridge Methods and Overriding

Raw types can allow a call whose parameters were erased to enter a **bridge method** generated by the compiler to preserve override behavior after generic erasure. A clear example:

Create `RawBridgeDemo.java`:

```java
public class RawBridgeDemo {

    static class Parent<T> {
        void save(T value) {
            System.out.println("parent");
        }
    }

    static final class StringChild extends Parent<String> {
        @Override
        void save(String value) {
            System.out.println(value.toUpperCase());
        }
    }

    public static void main(String[] args) {
        Parent<String> typed = new StringChild();
        typed.save("ok");

        Parent raw = typed;
        try {
            raw.save(42);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Compile and run:

```bash
javac RawBridgeDemo.java
java RawBridgeDemo
```

Stdout:

```text
OK
ClassCastException
```

Explanation:

- `Parent<T>.save(T)` is erased to a method taking `Object`.
- `StringChild.save(String)` is a valid override with respect to `Parent<String>`.
- The compiler can generate a **bridge method** in `StringChild` accepting `Object`, casting to `String`, and forwarding to `save(String)`.
- When calling through raw `Parent`, the compiler permits `raw.save(42)` against the `Object` parameter with an unchecked warning; at runtime the bridge must cast `Integer` to `String`, resulting in `ClassCastException`.

Bridge methods are **not a bug in Java Generics**, nor do they make raw types safer. They preserve Java polymorphism where a call compiled legitimately; a raw reference can let a value violating the generic contract reach the runtime cast.

To inspect the bridge, run:

```bash
javap -p -v 'RawBridgeDemo$StringChild'
```

Look for `save(java.lang.Object)` marked `ACC_BRIDGE` and `ACC_SYNTHETIC` alongside `save(java.lang.String)`.

## 16. How to Read Compiler Errors and Fix the Root Cause

### Error "Object cannot be converted to String"

Intentionally invalid code:

```java
Box raw = new Box("abc");
String text = raw.get();
```

Assuming `Box<T>` has `T get()`, `raw.get()` being viewed as `Object` explains the error. **Fix the root cause** by declaring the receiver's type:

```java
Box<String> box = new Box<>("abc");
String text = box.get();
```

Both snippets need the `Box<T>` definition and must sit inside a method; they illustrate the error and fix rather than forming standalone programs.

### Warning "unchecked call to set(T)"

Raw code:

```java
Box raw = new Box("abc");
raw.set(99);
```

The compiler no longer knows `T = String`; calling `set(...)` with erased parameter `Object` triggers an unchecked warning. It cannot be fundamentally fixed by **arbitrarily casting values** or suppressing warnings.

Change to:

```java
Box<String> box = new Box<>("abc");
box.set("new value");
```

which lets the compiler check the call. `box.set(99)` will be rejected.

### Warning "unchecked conversion" when assigning a raw collection

Code:

```java
java.util.List<String> labels = raw.fixedLabels();
```

when `raw` is `Box` and `fixedLabels()` is an instance method of a generic class, the static result type is raw `List`. The compiler allows converting to `List<String>` in certain contexts but **cannot verify it**, so it emits an unchecked warning.

Fix by using a parameterized receiver:

```java
Box<String> box = new Box<>("abc");
java.util.List<String> labels = box.fixedLabels();
```

### Trap: "I added generics to the method, so it will be safe"

Code:

```java
class Api<T> {
    <U> U convert(U input) {
        return input;
    }
}
```

Through raw `Api`, this generic instance method can be viewed via erasure. Adding `<U>` to the declaration **cannot restore** type `String` at `raw.convert("abc")`. Fix the receiver type or move the method to a static generic utility if the design contract allows.

## 17. Step-by-Step Procedure for Analyzing Member Types on a Raw Receiver

When evaluating a Java snippet that uses raw types, follow this order:

1. **Determine the static type of the receiver**, not the runtime class of the object. `Box<String>` and `Box` follow different member-typing rules.
2. **Check whether the receiver is truly raw**; `Box<?>` is not raw.
3. **Locate where the member is declared.** Is it an instance method/field declared directly on `Box`, an inherited member from a superclass/interface, or a static member?
4. **If it falls under raw members of that class, apply erasure to the member's type.** Do not merely replace `T` with `Object`; parameterized types like `List<String>` are erased too.
5. **If a type variable has bounds**, use the erasure of the leftmost bound, e.g., `<T extends Number>` yields `Number`.
6. **If it is an inherited member**, examine the member in the corresponding supertype that declares it; do not guess mechanically from the raw receiver.
7. **If static**, use the normal generic declaration of the static member without erasing it further due to a raw receiver.
8. **Check read/write directions.** Reads may yield `Object`/`List`, while writes or calls to methods whose parameters were erased can generate unchecked warnings and break generic contracts.
9. **Distinguish compile time from runtime.** Raw types do not create runtime type arguments; casts and bridge methods can throw `ClassCastException` later.
10. **Prefer fixing the API/type declarations**, replacing raw types with `Box<T>`, `Box<?>`, or an appropriate abstraction instead of suppressing warnings.

Quick-reference table:

| Expression | Main result / conclusion |
| --- | --- |
| `Box<String> b; b.get()` | `String` when `T` is unbounded |
| `Box b; b.get()` | `Object` when `T` is unbounded |
| `NumberBox b; b.get()` | `Number` if `T extends Number` |
| `Box b; b.fixedLabels()` | Raw `List` even though return declaration is `List<String>` |
| `Box<?> b; b.fixedLabels()` | `List<String>` is preserved |
| `Box<?> b; b.echo("x")` | Generic method can still infer `U = String` |
| `Box b; b.echo("x")` | Generic method declared by `Box` is viewed via erasure |
| `Container.staticEcho("x")` | Static generic method remains generic |
| `Container raw; raw.inheritedEcho("x")` | Check type in superclass declaring the method |
| `Box raw; raw.set("x")` | May cause unchecked warning and heap pollution |

## 18. Exercises with Answers

**Exercise 1 — Method return type**

```java
class C<T> {
    java.util.List<String> result() {
        return java.util.List.of("x");
    }
}
```

With `C<Integer> typed`, what type does `typed.result()` have? With raw `C raw`, what type does `raw.result()` have?

**Answer:** `List<String>` and raw `List`, respectively. The fact that the method does not mention `T` does not exempt it from the raw instance member rules of class `C<T>`.

**Exercise 2 — How do bounds affect erasure?**

```java
class C<T extends Number & Comparable<T>> {
    T value;
    T get() { return value; }
}
```

With raw `C`, what is the type of `get()`?

**Answer:** `Number`, which is the erasure of the leftmost bound `T extends Number & ...`.

**Exercise 3 — Generic method declaring its own type parameter**

```java
class C<T> {
    <U> U identity(U input) { return input; }
}
```

Are `String x = new C<String>().identity("a")` and `String y = new C().identity("a")` equally valid?

**Answer:** The first line is valid via inference `U = String`. The second line cannot directly assign a result viewed as `Object` to `String` in Java source.

**Exercise 4 — Inherited method**

```java
class Base {
    <U> U keep(U value) { return value; }
}
class Child<T> extends Base { }
```

With raw `Child raw = new Child();`, is `String s = raw.keep("a")` valid?

**Answer:** Yes. `keep` is declared in the non-generic superclass `Base`, so a raw `Child` receiver does not automatically erase this method the way instance methods declared directly on `Child<T>` are erased.

**Exercise 5 — Static field**

```java
class C<T> {
    static java.util.List<String> defaults = java.util.List.of("ok");
}
```

Does `C.defaults` still have type `List<String>` in source code?

**Answer:** Yes; static members retain their declared types. The compiler still uses erasure in the class file's field descriptor per JVM rules, but this is not "raw member conversion" caused by an instance receiver.

**Exercise 6 — Choosing a solution**

You receive `Box<?> unknown` and want to log all data without needing to add elements. Should you cast to raw `Box` to avoid casts?

**Answer:** No. Use `Box<?>` to read as `Object` and work with generic members still intact. Switching to raw only causes the compiler to drop type-checking guardrails unnecessarily.

**Exercise 7 — Predicting runtime failure**

Given `Box<String> typed = new Box<>("a")`, followed by `Box raw = typed; raw.set(1);`. When assigning `String s = typed.get();`, what can happen?

**Answer:** After the unchecked call via the raw receiver, the object stores an `Integer`. The typed call can throw `ClassCastException` when the result is checked as `String`.

## 19. Summary and Official References

Raw types are a compatibility tool for legacy Java code, yet they change how the compiler determines **the types of certain members**. For constructors, instance methods, and non-static fields declared directly on a generic class/interface, accessing them through a raw type causes member types to be viewed via **erasure**; consequences can include return types dropping from `T` to `Object`/bound or from `List<String>` to raw `List`, along with unchecked warnings when writing or calling methods whose parameters lost type checking.

Two exceptions to always remember: **static members are not raw-ified by a receiver**, and **inherited members must be evaluated in the supertype that declares them**. Compared to raw types, a wildcard like `Box<?>` preserves generic relationships and is usually safer when the type parameter is unknown.

Reference documents:

- [Java Language Specification §4.8 — Raw Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.8): official rules for types of constructors, instance fields/methods, inherited/static members, and unchecked warnings.
- [Java Language Specification §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): how erasure is computed for type variables, parameterized types, and method signatures.
- [Java Language Specification §4.5.2 — Members and Constructors of Parameterized Types](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.2): members of parameterized types.
- [Java Language Specification §5.1.9 — Unchecked Conversion](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html#jls-5.1.9): conversions that cannot be fully verified at compile time.
- JDK tools `javac` with `-Xlint:rawtypes -Xlint:unchecked` and `javap -p -s/-v`: helpful for inspecting actual warnings, descriptors, and bridge methods.