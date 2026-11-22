# Erasing Bounded Type Parameters to the Leftmost Bound in Java Generics

## 1. The problem to understand

Generics let you write a single algorithm that works across multiple types while still being type-checked by the compiler. For example:

```java
static <T extends Number> int asInt(T value) {
    return value.intValue();
}
```

`T` has an **upper bound** of `Number`: any type passed as an argument for `T` must be compatible with `Number`. Yet after compilation, the JVM does not have a separate `asInt(Integer)` version and a separate `asInt(Double)` version. The Java compiler applies **type erasure** to translate generic declarations into types representable in bytecode.

The core rule of this lesson:

> **The erased type of a type parameter is the erasure of its leftmost bound. If no bound is declared, the implicit bound is `Object`.**

Therefore:

```java
<T>                                   // T is erased to Object
<T extends Number>                    // T is erased to Number
<T extends Number & Comparable<T>>    // T is erased to Number
<T extends Comparable<T> & java.io.Serializable>
                                      // T is erased to Comparable
<T extends Runnable & AutoCloseable>  // T is erased to Runnable
```

The examples above are **generic signature snippets for analysis**, not standalone Java programs.

Note the distinction: **the first bound determines the representative type after erasure**; the remaining bounds **do not disappear from source-level type checking**. The compiler still knows `T` must satisfy *all* declared bounds.

## 2. Interpreting multiple-bound syntax

A declaration can constrain `T` with multiple types:

```java
<T extends B1 & B2 & B3>
```

Where:

- `T` is a type variable declared on a class, interface, method, or constructor.
- `B1` is the leftmost bound; `B2`, `B3` are additional bounds.
- `extends` in this position expresses subtyping constraints, covering both **classes** and **interfaces**.
- The `&` sign joins bounds into an **intersection bound**.
- A type argument supplied for `T` must satisfy **all** bounds, not just one of them.

For example:

```java
<T extends Number & Comparable<T> & java.io.Serializable>
```

A valid type argument must be a subtype of `Number`, compatible with `Comparable<T>`, and implement `Serializable`. `Integer` satisfies this set of conditions; `String` is not a subtype of `Number`.

Syntax ordering rules:

1. If there is a **class** bound, it must come **first**.
2. After the class bound, there may be interface bounds.
3. Two independent classes cannot be used as two class bounds in a single `&` list.
4. If there are only interfaces, the leftmost interface declared by the author determines erasure.
5. Types in a bound list are also subject to Java's validity rules, such as not containing bounds with the same erasure in a way forbidden by the JLS.

Valid examples:

```java
<T extends Number & Comparable<T>>
<T extends Runnable & AutoCloseable>
<T extends AutoCloseable & Runnable>
```

**Invalid** examples:

```java
<T extends Comparable<T> & Number> // Number is a class but does not come first
<T extends Number & Thread>        // There are two classes: Number and Thread
```

These two invalid examples only illustrate syntax/bound errors; do not put them into a program you want to compile.

## 3. Exact erasure rule

According to the Java Language Specification model, when erasing a type variable `T`, the compiler takes the **erasure of the leftmost bound** of `T`. Think in two steps:

1. Identify the first bound of `T`. If `<T>` has no `extends`, treat the bound as `Object`.
2. Erase the first bound's type. If that bound is already a non-parameterized class/interface, its type name stays as is; if it is a parameterized type, the generic arguments of that bound itself are also erased.

Reference table:

| Declaration | First bound | Erasure of `T` | Additional condition still checked in source code |
|---|---|---|---|
| `<T>` | Implicit `Object` | `Object` | None |
| `<T extends Object>` | `Object` | `Object` | None |
| `<T extends Number>` | `Number` | `Number` | None |
| `<T extends Number & Comparable<T>>` | `Number` | `Number` | `Comparable<T>` |
| `<T extends Comparable<T> & java.io.Serializable>` | `Comparable<T>` | `Comparable` | `Serializable` |
| `<T extends Runnable & AutoCloseable>` | `Runnable` | `Runnable` | `AutoCloseable` |
| `<T extends java.util.List<String> & java.util.RandomAccess>` | `List<String>` | `List` | `RandomAccess` |

The `List<String>` row highlights an easily overlooked point: erasure does not keep the `<String>` argument. That is why `T` ends up represented by `java.util.List`, not `List<String>` in the regular bytecode descriptor sense.

**Do not** interpret the rule as "`T` becomes `Object` in every case". That is only true for an unbounded type parameter or one whose first bound erases to `Object`.

### Scope of application

This rule applies to **type variables** in many positions:

```java
class Holder<T extends Number & Comparable<T>> {
    T value;

    T get() {
        return value;
    }

    void set(T newValue) {
        value = newValue;
    }
}
```

This is a valid class snippet; it has no `main` method, so it is not yet a runnable program. In bytecode type descriptions, the field `value`, parameter of `set`, and return value of `get` use the representative type `Number`. Generic information such as `T` and its bounds can be retained in the `Signature` attribute for tools and reflection to read, yet that is **not** a mechanism where the JVM creates multiple classes for different `T` types.

## 4. Runnable example: class first and additional interface

Create the file `LeftmostBoundDemo.java`:

```java
public class LeftmostBoundDemo {

    static <T extends Number & Comparable<T>> String compare(T left, T right) {
        int first = left.intValue();
        int second = right.intValue();
        boolean greater = left.compareTo(right) > 0;
        return first + " vs " + second + " => " + greater;
    }

    static <T extends Runnable & AutoCloseable> void execute(T task)
            throws Exception {
        task.run();
        task.close();
    }

    static final class Task implements Runnable, AutoCloseable {
        @Override
        public void run() {
            System.out.println("run");
        }

        @Override
        public void close() {
            System.out.println("close");
        }
    }

    public static void main(String[] args) throws Exception {
        System.out.println(compare(9, 4));
        execute(new Task());
    }
}
```

Compile and run with Java 17 or later:

```bash
javac LeftmostBoundDemo.java
java LeftmostBoundDemo
```

Stdout:

```text
9 vs 4 => true
run
close
```

### Analyzing `compare`

```java
static <T extends Number & Comparable<T>> String compare(T left, T right)
```

- The leftmost bound of `T` is `Number`.
- `T` is erased to `Number`.
- Both method parameters are represented by `Number` after erasure.
- `intValue()` exists on `Number`, so calling this member directly matches the capability provided by the first bound.
- `compareTo(T)` comes from `Comparable<T>`, which is the **second bound**. Even though `Number` itself does not declare `compareTo`, the call is still valid in source code because the compiler checks all bounds.

To execute a call to a method from an additional bound in bytecode, the compiler can insert a cast to the appropriate interface (here `Comparable`) before invoking the interface method. Erasing `T` to `Number` **does not forbid calling `compareTo`**.

### Analyzing `execute`

```java
static <T extends Runnable & AutoCloseable> void execute(T task)
```

Both `Runnable` and `AutoCloseable` are interfaces. Since `Runnable` comes first, the erasure of `T` is `Runnable`; the compiler still checks `task.close()` thanks to the second bound `AutoCloseable`. Similarly, a cast can appear in bytecode before calling `close()`.

Calling `execute(new Task())` is valid only because `Task` implements **both** interfaces. An object that implements only `Runnable` without implementing `AutoCloseable` will not satisfy the method's bound.

A specific note about the example: the method calls `run()` and `close()` sequentially to illustrate two bounds. If `run()` throws an exception, `close()` in the example might not be called; in real resource-management code, design proper error handling and resource closing, such as `try/finally` or `try-with-resources` where applicable.

## 5. Observing erased types with `javap`

The JDK includes `javap` to inspect signatures and bytecode. After compiling `LeftmostBoundDemo.java`, run:

```bash
javap -p -s LeftmostBoundDemo
```

Focus on the two method descriptors (extracting only the relevant part, not the entire `javap` output):

```text
compare(java.lang.Number, java.lang.Number)
  descriptor: (Ljava/lang/Number;Ljava/lang/Number;)Ljava/lang/String;

execute(java.lang.Runnable)
  descriptor: (Ljava/lang/Runnable;)V
```

Because `compare` returns `String`, the return type in the descriptor is `String`. `execute` is `void`, so its descriptor ends with `V`. These descriptors show that the leftmost bound determines the type of positions holding type variable `T` in the erased signature.

To observe the invocation instructions and compiler-generated casts, run:

```bash
javap -p -c LeftmostBoundDemo
```

Detailed output has instruction offsets and constant-pool indices depending on your JDK/compiler version. Key things to look for include:

- The call to `Number.intValue()` from the first bound.
- The appropriate conversion to `Comparable` and call to `Comparable.compareTo(...)` when using the additional bound.
- The call to `Runnable.run()` and interaction with `AutoCloseable.close()` in `execute`.

Do not memorize bytecode offsets; compare **descriptors** and the **owning type of each call**. That explains both compile-time results and how the JVM executes the program.

## 6. When the first bound is an interface

Suppose a method needs parameters that are both comparable and serializable:

```java
static <T extends Comparable<T> & java.io.Serializable> T choose(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

This is a **method snippet** and must be placed inside a class to compile. Here:

- The first bound is `Comparable<T>`, a parameterized interface.
- The erasure of `Comparable<T>` is the raw interface `Comparable`.
- Therefore, the erasure of type variable `T` is `Comparable`.
- Positions of type `T` in the method descriptor use `Comparable`.
- `Serializable` remains a mandatory compile-time requirement on type arguments.

The corresponding erased descriptor signature is:

```text
(Ljava/lang/Comparable;Ljava/lang/Comparable;)Ljava/lang/Comparable;
```

**Interface order matters for erasure.** Although syntactically both declarations below are valid:

```java
<T extends Runnable & AutoCloseable>
<T extends AutoCloseable & Runnable>
```

the first erases `T` to `Runnable`, whereas the second erases `T` to `AutoCloseable`. The set of constraints to satisfy in source code may be identical, yet the **representative type in the erased signature** differs.

### Why not reorder bounds just for aesthetics?

If a generic declaration appears in a public API and you reorder the interfaces in the bound list, the descriptors of fields/methods using that type variable can change. This can affect the binary compatibility of the library, previously compiled classes, and how bridge methods are generated.

Therefore, bound order is not merely a formatting choice. When designing APIs, choose the first bound deliberately, especially if the class/interface is used by other modules or published as a library.

## 7. Class bounds must come before interfaces

For example:

```java
static <T extends Number & Comparable<T> & java.io.Serializable>
T pick(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

With `<T extends Number & ...>`, `Number` is a class bound and must come first. You **cannot** reorder it to `<T extends Comparable<T> & Number>` to force the erasure of `T` to switch to `Comparable`; Java rejects the declaration because the class bound is in the wrong position.

If you truly do not need members of `Number`, you can design a different API based solely on interfaces:

```java
static <T extends Comparable<T> & java.io.Serializable>
T pickComparable(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Removing `Number` changes the **input contract**: the method can now accept non-number types satisfying both interfaces, such as `String`. This is an API design change, not merely an erasure change.

## 8. How does erasure affect methods, fields, and overloading?

### Fields, parameters, return values

Consider the class:

```java
class NumberHolder<T extends Number & Comparable<T>> {
    T item;

    NumberHolder(T item) {
        this.item = item;
    }

    T get() {
        return item;
    }
}
```

When types are erased, the relevant uses of `T` are represented by `Number`:

```java
// Model illustrating the result after erasure; not Java code directly
// emitted by javac and does not replace the original generic class.
class NumberHolderErasedModel {
    Number item;

    NumberHolderErasedModel(Number item) {
        this.item = item;
    }

    Number get() {
        return item;
    }
}
```

These are **two distinct classes for comparison**, not a requirement to create two files when using `NumberHolder`. The compiler/JVM actually uses the erased type descriptions in bytecode, while the compiler can generate casts and bridge methods as needed to preserve generic behavior.

When calling:

```java
NumberHolder<Integer> holder = new NumberHolder<>(12);
Integer value = holder.get();
```

The source code above has a checked result type of `Integer`; in bytecode, if needed, the compiler can insert a cast from `Number` to `Integer` at the receiving site. There are not two different runtime copies for `NumberHolder<Integer>` and `NumberHolder<Double>`.

### Cannot overload if erased signatures collide

**Invalid** example, used solely to analyze compile-time errors:

```java
class BadOverload {
    static <T extends Number & Comparable<T>> void log(T value) {}

    static void log(Number value) {} // name clash due to identical erasure
}
```

In the first method, `T` is erased to `Number`. Both declarations end up with the same name `log` and the same parameter list after erasure, so they cannot coexist as two valid overloads in the same class. The compiler reports a **name clash** error.

How to fix it depends on your goal: use different method names, unify into a single generic method, or change the parameter contract in a way that yields genuinely distinct signatures. Do not assume two different bounds or two different generic arguments are always enough to overload.

### Type erasure vs. source-level overload resolution

The compiler first checks validity and resolves calls according to Java's type system; erasure serves bytecode generation and preserves the compatibility model. You should not reason as if "every type variable was already `Number` from the beginning" while reading Java source code. In source code, the compiler still knows `T` is the same type in two parameters and must satisfy all bounds.

## 9. Bridge methods: preserving overriding behavior after erasure

An instructive consequence is the **bridge method**. Create the file `LeftmostBridgeDemo.java`:

```java
public class LeftmostBridgeDemo {

    static class Store<T extends Number & Comparable<T>> {
        T next(T value) {
            return value;
        }
    }

    static final class IntegerStore extends Store<Integer> {
        @Override
        Integer next(Integer value) {
            return value + 1;
        }
    }

    public static void main(String[] args) {
        Store<Integer> store = new IntegerStore();
        System.out.println(store.next(10));

        @SuppressWarnings("rawtypes")
        Store rawStore = new IntegerStore();

        try {
            rawStore.next(2.5);
        } catch (ClassCastException ex) {
            System.out.println("ClassCastException");
        }
    }
}
```

Compile and run:

```bash
javac LeftmostBridgeDemo.java
java LeftmostBridgeDemo
```

Stdout:

```text
11
ClassCastException
```

`Store<T>.next(T)` has an erasure corresponding to `Number next(Number)`, because `Number` is the first bound. Meanwhile, `IntegerStore.next(Integer)` accepts and returns `Integer`. So that calls through a variable of type `Store<Integer>` still dispatch to `IntegerStore`'s override, `javac` can generate a bytecode-level bridge method in the subclass whose signature matches `next(Number)`; this bridge performs the appropriate cast and then calls `next(Integer)`.

You can inspect the subclass information with:

```bash
javap -p -s 'LeftmostBridgeDemo$IntegerStore'
javap -p -v 'LeftmostBridgeDemo$IntegerStore'
```

Put single quotes around the nested class name so the `$` character is preserved in common shells (including PowerShell and bash). In the printed output, look for two `next` methods with descriptors corresponding to `Integer` and `Number`; the bridge version is marked `ACC_BRIDGE` and `ACC_SYNTHETIC`.

`rawStore` is a **raw type** and intentionally omits the generic argument to illustrate the limits of type safety when mixing legacy code. In the call `rawStore.next(2.5)`, the `Double` argument is still a `Number`, so it can pass through the erased signature `next(Number)`. However, `IntegerStore`'s bridge needs to cast the argument to `Integer`; the cast fails and throws `ClassCastException`. This scenario is something to **avoid** in normal applications, not a recommended way to use generics.

Compiler warnings about raw/unchecked usage may appear when lint flags are enabled, though the program still compiles with the syntax above. Do not swallow `ClassCastException` in business logic; this is strictly a controlled demonstration.

## 10. Are all trailing bounds completely discarded?

No. Three perspectives must be distinguished.

### Perspective 1: source-level type system

Given:

```java
<T extends Number & Comparable<T>>
```

The compiler knows `T` has behavior from `Number` **and** `Comparable<T>`. It rejects any type argument that does not satisfy both. Using `Number` as the representative type during erasure does not cancel checking `Comparable<T>`.

### Perspective 2: JVM type descriptors and bytecode

For positions of type `T` in a field descriptor or method descriptor, the JVM sees the erased type according to the leftmost bound. Instructions that need to invoke via a secondary bound may include a corresponding `checkcast`. Where a generic type is specialized, the compiler can emit additional casts and bridge methods.

This is not a transformation you can perform accurately by simply deleting `<...>` strings from source code. Java's erasure is a rule-based compilation mechanism covering type variables, parameterized types, arrays, method signatures, overriding, and necessary type conversions.

### Perspective 3: generic metadata and reflection

Generic declaration information can still be stored in the class file, such as the `Signature` attribute. Reflection calls like `TypeVariable.getBounds()` can return the declared list of bounds in order. Seeing that metadata **does not mean** the JVM stores full runtime type arguments for every generic instance.

Standalone example in `BoundsReflectionDemo.java`:

```java
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;

public class BoundsReflectionDemo {

    static class Sample<T extends Number & Comparable<T>> {}

    public static void main(String[] args) {
        TypeVariable<?> type = Sample.class.getTypeParameters()[0];
        System.out.println(type.getName());
        for (Type bound : type.getBounds()) {
            System.out.println(bound.getTypeName());
        }
    }
}
```

Compile and run:

```bash
javac BoundsReflectionDemo.java
java BoundsReflectionDemo
```

Stdout on typical JDK 17+:

```text
T
java.lang.Number
java.lang.Comparable<T>
```

Metadata shows `T` declares **two** bounds; the erasure rule still picks the first bound, `Number`. Looking at `getBounds()` alone does not prove a specific instance of `Sample<Integer>` retains `Integer` as a runtime argument. Nor can you write `new T()` or `T.class` in regular generic code.

## 11. Connection to `Comparable` and generic APIs

A common pattern when writing comparison algorithms:

```java
static <T extends Comparable<? super T>> T greater(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Here the first bound is `Comparable<? super T>`, so the erasure of `T` is **raw `Comparable`**. `? super T` widens acceptance to a type whose comparison is defined on a supertype of `T`, without changing the erasure rule for type variable `T`.

Another signature:

```java
static <T extends Number & Comparable<? super T>>
T greaterNumber(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

Here the first bound is `Number`, so the erasure of `T` is **`Number`**, even though the comparison operation itself is provided by the second bound. These are two different generic contracts.

For general-purpose algorithms, do not pick the first bound just to get a shorter descriptor. Choose the right constraints for your API's input domain; among the orderings Java permits, care about keeping the order stable once an API has been published.

## 12. Common misconceptions

**Misconception 1 — "The last bound determines erasure."** False. With `<T extends Number & Comparable<T>>`, the erasure of `T` is `Number`. All bounds are checked at compile time, but the **leftmost bound** determines the representative type when erased.

**Misconception 2 — "Interfaces after `&` can no longer be used."** False. `LeftmostBoundDemo` successfully called both `compareTo` and `close` from secondary bounds. The compiler can emit casts in bytecode to access the appropriate interface.

**Misconception 3 — "The first bound must always be a class."** False. If there is no class bound, an interface can come first. For example, `<T extends Runnable & AutoCloseable>` has erasure `Runnable`.

**Misconception 4 — "Reordering bounds never affects a library."** False. With interfaces, changing the first bound can change field/method descriptors or related bridges. If a public class/method is already used by other binaries, binary compatibility must be evaluated before changing it.

**Misconception 5 — "Type erasure happens first, so the compiler doesn't know about the other bounds."** False. The compiler analyzes and checks the generic type system, and then generates bytecode according to erasure. Needed casts can be inserted during code generation.

**Misconception 6 — "Every generic erases to `Object`."** False. `<T>` normally erases to `Object`, whereas `<T extends Number>` erases to `Number`, and `<T extends Comparable<T>>` erases to `Comparable`.

**Misconception 7 — "Generic metadata means type arguments exist per instance at runtime."** False. You can read declared bounds of a class/method via reflection, yet type arguments of an ordinary instance are not fully reconstructed merely because generic metadata exists.

**Misconception 8 — "The bound `<T extends Number & Comparable<T>>` is equivalent to two overloads."** False. This is a single generic method with one type variable that must satisfy both constraints; the compiler does not create one overload for `Number` and another for `Comparable`.

## 13. Steps to inspect a generic signature

When you need to predict the erasure of an API:

1. Find the type parameter declaration, such as `<T extends Number & Comparable<T>>`.
2. Identify the **leftmost bound**: here it is `Number`.
3. Erase the first bound type itself if it has generic arguments, e.g., `List<String>` becomes `List`.
4. Replace positions using type variable `T` in descriptors with the corresponding erased type.
5. Check the remaining bounds to see why the source method can invoke their members.
6. If there is overriding with concrete type arguments, check for potential bridge method generation.
7. If there are overloads, check for signature collisions after erasure.
8. If a public API changes bound ordering, evaluate compatibility with already-compiled clients.

Self-practice examples:

**Scenario A**

```java
<T extends java.util.List<String> & java.util.RandomAccess>
```

Answer: the first bound is `List<String>`, so the erasure of `T` is `java.util.List`. `RandomAccess` remains a requirement on type arguments.

**Scenario B**

```java
<T extends AutoCloseable & Runnable>
```

Answer: the erasure of `T` is `AutoCloseable`. If reversed to `Runnable & AutoCloseable`, the erasure switches to `Runnable`.

**Scenario C**

```java
<T extends Object & Runnable>
```

Answer: the erasure of `T` is `Object`, even though in source code `T` must also implement `Runnable`. This is an example showing that choosing `Object` as the first bound can produce a different descriptor compared to `<T extends Runnable>`.

**Scenario D**

```java
<T extends Number & java.io.Serializable>
```

Answer: the erasure of `T` is `Number`. `Serializable` is an additional constraint; it does not override the first bound.

**Scenario E**

```java
<T extends Comparable<T> & java.io.Serializable>
```

Answer: the erasure of `T` is raw `Comparable`. The `<T>` inside `Comparable<T>` is also erased from the descriptor representation.

## 14. Key takeaways and reference materials

The statement to remember is that **the erasure of a type variable is based on the erasure of its leftmost bound**. If no bound is written, `Object` is the implicit bound. A class bound, if present, always precedes interfaces; if there are only interfaces, the first interface determines the representative type. Subsequent bounds remain in effect for source-level type checking.

From this small rule follow very practical consequences: field/method descriptors use the erased type, the compiler can insert casts to use additional interfaces, overriding methods may require bridge methods, and two overloads can be rejected due to identical erased signatures. When designing libraries, treat bound order as part of the signature that can affect binary compatibility.

Standard references for further lookup:

- [Java Language Specification, §4.4 — Type Variables](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4): syntax, validity, and meaning of bounds.
- [Java Language Specification, §4.6 — Type Erasure](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erasure rules for parameterized types, type variables, and method signatures.
- [Java Language Specification, §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.8.3): rules related to overriding and name clashes.
- The JDK `javap` tool: use `-s` to inspect descriptors, `-c` to view bytecode, and `-v` to inspect metadata such as `Signature` or bridge method flags.