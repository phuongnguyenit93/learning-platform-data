# Generic Class Type Parameters Cannot Be Used Directly in Static Contexts — Java 17+

## Learning Objectives

After this lesson, you will be able to:

- Explain that `class Box<T>` declares a **class-level type parameter** `T`, which can be used in instance fields, constructors, instance methods, and certain valid nested contexts.
- Understand that **static belongs to the class**, not specifically to `Box<String>`, `Box<Integer>`, or a particular object, because parameterizations share the same runtime class.
- Identify compile-time errors when using the class's `T` directly in a **static field declaration**, **static method declaration/body**, **static initializer**, or **static nested class**.
- Distinguish between two causes: **a class type parameter has no meaning in a static context** and **a static context has no `this` or instance members**; these two errors are independent but often appear together.
- Write static generic factories/helpers by declaring a **method's own type parameter**: `static <U> Box<U> of(U value)`.
- Understand that `<U>` is placed **before the return type**, not after the method name; understand type inference and explicit invocation such as `Box.<String>of("A")`.
- Recognize that redeclaring the name `T` in a static method is a **new method type parameter**, not a way to "get" the class-level `T`; prefer using `U` or `R` to avoid name shadowing.
- Declare static constants/fields with concrete types such as `int`, `String`, `List<?>`, `Box<?>`, or static helpers with method-level generic parameters when appropriate.
- Distinguish between valid `Box.COUNT` and invalid `Box<String>.COUNT` according to the static member qualification rules for parameterized types.
- Distinguish between a **static nested class**, which cannot use the outer `T`, and a **non-static inner class**, which can use the outer `T` because it is bound to an enclosing instance/parameterization.
- Avoid confusing the inability to write `T.class`, `new T()`, `new T[10]`, or `instanceof T` with static-only errors: these are also limitations related to type erasure/reifiability even inside instance methods.
- Apply generic type tokens `Class<T>` when runtime type information is needed, instead of expecting a type parameter to exist as a runtime Class literal.
- Design a static count/cache/registry without assuming there is one copy of static state per parameterization, and identify shared mutable state/concurrency risks.
- Use bounded generic static methods, generic static factories, wildcards, and generic instance APIs in the right places.
- Compile the Java 17+ examples yourself, compare exact stdout, complete the exercises on your own, and distinguish intentionally invalid code from runnable programs.

> **Scope:** This lesson focuses solely on **the rules for using a class's type parameter in static contexts of a Java generic class**, along with the underlying mechanisms and necessary workarounds. Complete demos use JDK 17 or later. Compile-error examples are marked and typically commented out so they do not break runnable demos.

## 1. Intuition: `T` Is a Type Description **of the Instance**, Not a Separate Type for the Static Part

A generic class:

~~~java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

Example usage:

~~~java
Box<String> text = new Box<>("hello");
Box<Integer> number = new Box<>(42);
~~~

In the source code, the compiler understands:

- `text.get()` has a compile-time return type of `String`.
- `number.get()` has a compile-time return type of `Integer`.
- Inside instance methods of `Box<T>`, `T` can be used as a field type, method result/parameter type.
- However, `Box<String>` and `Box<Integer>` **are not two independent runtime classes** that create two separate sets of static members.

An instance has a **type argument from a compile-time view**. A static member is attached to the generic class declaration as a **class-level member**.

If you try to create a static field of type `T`:

~~~java
class Box<T> {
    // static T shared; // Invalid.
}
~~~

Java does not have a definite `T` to use at the time the static member is declared: is it `T` of `Box<String>` or `T` of `Box<Integer>`? Both parameterizations share **one class** definition, with no static storage per type argument.

That is the intuition; the **official language rules** are described in JLS `6.5.5.1 and `8.1.2: referencing a generic class's type parameter is restricted in a static context.

## 2. Comparison Table of Type Parameter Usage Scopes

| Location in `class Box<T>` | Can use class-level `T` directly? | Example |
| --- | --- | --- |
| Instance field | **Yes** | `private T value;` |
| Instance constructor | **Yes** | `Box(T value)` |
| Instance method signature/body | **Yes** | `T get()`, `void set(T x)` |
| Instance field initializer | **Yes**, if the code is valid | `List<T> items = new ArrayList<>();` |
| Static field declaration | **No** | `static T cached;` is invalid |
| Static method signature/body | **No** | `static T id(T x)` is invalid |
| Static initializer | **No** | `static { T x = ...; }` is invalid |
| Static nested class | **No** | `static class Node { T x; }` is invalid |
| Static method with its own `<U>` | **Can use U**, cannot use outer T | `static <U> Box<U> of(U x)` |
| Static nested class with its own `<U>` | **Can use U**, cannot use outer T | `static class Node<U> { U x; }` |
| Non-static inner class | **Yes** | `class Cell { T value; }` |
| Static field with wildcard/fixed type | **Yes** | `static Box<?> empty;` or `static int count;` |
| `T.class` | **No** | Invalid even in an instance method |

The term "static context" does not mean only a method with the `static` keyword. It includes locations specified by the language such as static field initializers, static initializer blocks, and the bodies of static methods; static nested types have their own rules because they are not bound to an enclosing instance.

### 2.1. Two Different Things That Are "Missing"

In a static method of a generic class:

1. **There is no enclosing instance `this`** of `Box`. Therefore, calling the instance method `get()` without a receiver or reading the instance field `value` directly is invalid.
2. **You cannot use the class-level type parameter `T`** as a type name in a static context. Even without touching `this`, the signature `static T copy(T x)` is still invalid.

Fix the two errors in two different ways: pass an **object** if you need instance state; declare a **new method type parameter** if you need a generic type for a utility/factory.

## 3. Program 1: Valid Instance Field, Shared Static Counter

Save **`GenericStaticCounterDemo.java`**:

~~~java
public class GenericStaticCounterDemo {
    static class Box<T> {
        private static int constructed;
        private final T value;

        Box(T value) {
            this.value = value;
            constructed++;
        }

        T value() {
            return value;
        }

        static int constructedCount() {
            return constructed;
        }
    }

    public static void main(String[] args) {
        Box<String> first = new Box<>("Java");
        Box<Integer> second = new Box<>(17);

        System.out.println("first=" + first.value());
        System.out.println("second=" + second.value());
        System.out.println("counter=" + Box.constructedCount());
        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericStaticCounterDemo.java
java GenericStaticCounterDemo
~~~

**Stdout:**

~~~text
first=Java
second=17
counter=2
same class=true
~~~

### 3.1. Why Does It Produce This Result?

- The two `new Box<>(...)` calls create **two different objects**.
- `value` is a separate field for each object, with a compile-time type appropriate for each parameterization.
- `constructed` is **a single static int** attached to the runtime Box class. Both constructor calls increment the **same counter**.
- `first.getClass() == second.getClass()` is true because the runtime class of both objects is the same Box declaration.
- `Box.constructedCount()` is called using the **generic class name**, not `Box<String>.constructedCount()`.

**Note:** the static counter in this example is not thread-safe: `constructed++` is not atomic. Multithreaded code needs `AtomicInteger`/synchronization if you truly want accurate counting. This is independent of generic typing.

## 4. Static Declarations Using Outer `T` That Are Rejected by the Compiler

Suppose:

~~~java
class Repository<T> {
    private T current;

    // static T cached;             // Invalid: static field type.
    // static java.util.List<T> xs; // Invalid: T in static field type.
    // static T getCached() {       // Invalid: static return type.
    //     return null;
    // }
    // static void put(T value) { } // Invalid: static parameter type.

    T getCurrent() {               // Valid: instance method.
        return current;
    }

    void setCurrent(T value) {      // Valid: instance method.
        current = value;
    }
}
~~~

The erroneous lines are commented out; this is a **snippet**, not a runnable file with main.

**Conclusion:** having the outer `T` appear in any corresponding type position of a static field/static method is prohibited, even when the static method body does not access any data.

### 4.1. A Question That Causes Confusion

> "If I only write `static T identity(T x) { return x; }` without using any field, why is it still invalid?"

Because the symbol `T` is **referring to the generic class's type parameter**, and the static method declaration position is not allowed to reference it. To have an independent generic function, you must declare a type parameter **of the method itself**: `static <U> U identity(U x)`.

## 5. Static Generic Methods With **Their Own Type Parameter**

Important syntax:

~~~java
static <U> U identity(U input) {
    return input;
}
~~~

`<U>` must appear **after the modifiers (`static`, `public` if present)** and **before the return type**. `U` is a type parameter of the **method**, created per the **method declaration**, not a way to "reach out" to the outer T.

Comparison:

~~~java
class Box<T> {
    T instanceEcho(T x) {
        return x;
    }

    // static T wrong(T x) { return x; } // Invalid, outer T.

    static <U> U staticEcho(U x) {
        return x;
    }
}
~~~

### 5.1. Scope and Shadowing

Java allows a generic method to declare the name `<T>` identical to the outer `T` in certain valid scope cases; in that case, **method T shadows outer T**. Even though written with the same name, they are two **different** declarations. For example, to avoid confusion, `<U>`, `<R>`, or a meaningful symbol like `<E>` for element is typically used.

### 5.2. No Box Instance Is Needed to Call It

A generic static method can be used like `Box.staticEcho("A")`. The compiler infers `U = String` at the corresponding invocation; calling `Box.staticEcho(10)` infers `U = Integer`. That is not the outer class parameterization `Box<String>` or `Box<Integer>`.

## 6. Program 2: Static Generic Utility Independent of Outer `T`

Save **`GenericStaticMethodDemo.java`**:

~~~java
public class GenericStaticMethodDemo {
    static class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T value() {
            return value;
        }

        static <U> U echo(U input) {
            return input;
        }

        static <U> String label(U input) {
            return "value=" + input;
        }
    }

    public static void main(String[] args) {
        String text = Box.echo("Java");
        Integer number = Box.echo(17);

        System.out.println("text=" + text);
        System.out.println("number=" + number);
        System.out.println(Box.label(true));

        Box<Long> instance = new Box<>(5L);
        System.out.println("instance=" + instance.value());
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericStaticMethodDemo.java
java GenericStaticMethodDemo
~~~

Output:

~~~text
text=Java
number=17
value=true
instance=5
~~~

- `echo` and `label` have a **method-owned `U`**.
- `Box<Long> instance` retains the outer type parameter Long in instance methods.
- Just because `instance` is Box<Long> does not mean `echo` is restricted to using Long.
- All `Box.echo(...)` calls are static method calls on the Box class.

### 6.1. Explicit Type Argument for a Static Generic Method

You can explicitly specify the method's type argument:

~~~java
String s = Box.<String>echo("Java");
Integer n = Box.<Integer>echo(17);
~~~

This is a snippet placed in code where Box declares a matching echo method. `Box.<String>echo(...)` specifies **U of echo**, without creating the class parameterization `Box<String>`.

## 7. Static Factory for a Generic Class: `static <U> Box<U> of(U value)`

Common API pattern:

~~~java
class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = value;
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
~~~

**Reading the signature accurately:**

- `static`: the method belongs to the Box class.
- `<U>`: the method declares its own type variable U.
- `Box<U>`: the return type is Box parameterized by the **method U**.
- `of(U value)`: the input uses the same U.
- `new Box<>(value)`: the compiler infers the appropriate type argument.

**Incorrect:**

~~~java
// static Box<T> of(T value) { return new Box<>(value); }
// Cannot use outer T in a static signature/body.
~~~

### 7.1. Why Does the Factory Need Its Own Type Parameter?

At the time the caller invokes `Box.of("abc")`, the compiler infers `U = String`, with return type `Box<String>`. When the caller invokes `Box.of(100)`, U = Integer, with return type `Box<Integer>`. **One method declaration** is used across two compile-time type instantiations; there is no "separate factory for Box<String>" in the runtime class.

## 8. Program 3: Factory With Type Inference

Save **`GenericFactoryDemo.java`**:

~~~java
public class GenericFactoryDemo {
    static final class Box<T> {
        private final T value;

        private Box(T value) {
            this.value = value;
        }

        static <U> Box<U> of(U value) {
            return new Box<>(value);
        }

        T get() {
            return value;
        }
    }

    public static void main(String[] args) {
        Box<String> first = Box.of("ready");
        Box<Integer> second = Box.of(42);
        Box<Number> third = Box.<Number>of(3.5);

        System.out.println("first=" + first.get());
        System.out.println("second=" + second.get());
        System.out.println("third=" + third.get());
        System.out.println("runtime same=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericFactoryDemo.java
java GenericFactoryDemo
~~~

Output:

~~~text
first=ready
second=42
third=3.5
runtime same=true
~~~

`Box.<Number>of(3.5)` is an **explicit method type argument** setting U = Number; `3.5` autoboxes to Double and can be passed when the method parameter type is Number.

`Box.of` is a readable name for a static factory, without attaching `<String>` to the class name for static access.

## 9. Static Methods Have No `this`

Another static ≠ instance error:

~~~java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    // static Object wrong() {
    //     return this.value;   // Invalid: there is no this in a static method.
    // }

    // static Object alsoWrong() {
    //     return get();       // Invalid: instance method lacks a receiver.
    // }
}
~~~

Even if you changed the field to `Object value` instead of `T value`, a static method still **has no receiver** to read that field directly.

### 9.1. How to Fix It If Instance State Is Needed

Pass an **instance** into the static method; use a wildcard if the helper does not need to know the argument type:

~~~java
static Object readAsObject(Holder<?> source) {
    return source.get();
}
~~~

`Holder<?>` is a valid reference type in a static method signature because it **does not reference the outer class type parameter T**. The helper receives a concrete object and then calls the instance method `get()` through the receiver `source`.

If you want type safety that preserves the exact type of the input, use a method-owned U:

~~~java
static <U> U read(Holder<U> source) {
    return source.get();
}
~~~

## 10. Program 4: Passing a Receiver to a Static Helper

Save **`GenericStaticReceiverDemo.java`**:

~~~java
public class GenericStaticReceiverDemo {
    static class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        static Object asObject(Holder<?> source) {
            return source.get();
        }

        static <U> U read(Holder<U> source) {
            return source.get();
        }
    }

    public static void main(String[] args) {
        Holder<String> text = new Holder<>("Hello");
        Holder<Integer> number = new Holder<>(10);

        String keptString = Holder.read(text);
        Integer keptNumber = Holder.read(number);

        System.out.println("text=" + keptString);
        System.out.println("number=" + keptNumber);
        System.out.println("object=" + Holder.asObject(text));
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericStaticReceiverDemo.java
java GenericStaticReceiverDemo
~~~

Output:

~~~text
text=Hello
number=10
object=Hello
~~~

Although the helper is static, it can read data **of the passed-in object**, not an implicit `this`. `Holder.read` uses the method's own U, so the result retains the compile-time type of source.

## 11. What Types Should Static Fields Use?

Valid patterns:

~~~java
class Registry<T> {
    private static int count;
    private static final String VERSION = "1";
    private static final java.util.List<?> EMPTY =
            java.util.List.of();
    private static final java.util.Map<String, Integer> CODES =
            java.util.Map.of("OK", 200);

    // private static T last;            // Invalid.
    // private static java.util.List<T> cache; // Invalid.
}
~~~

`List<?>` describes a list with an unknown element type in a static declaration. `Map<String,Integer>` describes a static map with **concrete type arguments**, without using T of Registry.

Static fields do not "change type" per parameterization. `Registry<String>.last` and `Registry<Integer>.last` are not two stores with type-safe separation.

### 11.1. When Is a Wildcard Right?

If a static field genuinely holds **heterogeneous generic instances** and callers only need to inspect data through a safe API, `List<Box<?>>` can be an appropriate representation. Just because `Box<?>` accepts multiple concrete parameterizations does not mean you can infer they are all `Box<T>` of the current object; the wildcard expresses an **unknown element type**.

### 11.2. If You Need an Empty Collection Per Type

Instead of storing `static final List<T> EMPTY` (invalid), a static generic factory can return an empty list with an independent U:

~~~java
static <U> java.util.List<U> emptyList() {
    return java.util.List.of();
}
~~~

`List.of()` is a library static generic factory with suitable type inference; there is no need to create a separate mutable static List<T> field.

## 12. Program 5: Static Constant, Wildcard, and Generic Empty Factory

Save **`GenericStaticCollectionsDemo.java`**:

~~~java
import java.util.List;

public class GenericStaticCollectionsDemo {
    static class Store<T> {
        private static final List<?> EMPTY = List.of();

        static int emptySize() {
            return EMPTY.size();
        }

        static <U> List<U> emptyList() {
            return List.of();
        }
    }

    public static void main(String[] args) {
        List<String> words = Store.emptyList();
        List<Integer> numbers = Store.emptyList();

        System.out.println("words size=" + words.size());
        System.out.println("numbers size=" + numbers.size());
        System.out.println("static empty=" + Store.emptySize());

        System.out.println("words add supported=" +
                canAddWord(words));
    }

    static boolean canAddWord(List<String> list) {
        try {
            list.add("X");
            return true;
        } catch (UnsupportedOperationException expected) {
            return false;
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericStaticCollectionsDemo.java
java GenericStaticCollectionsDemo
~~~

Output:

~~~text
words size=0
numbers size=0
static empty=0
words add supported=false
~~~

A method-owned U allows `Store.emptyList()` to return List<String>/List<Integer> in different target contexts. `List.of()` returns an unmodifiable List, so attempting to add throws `UnsupportedOperationException`.

**Do not confuse:** `EMPTY` is a static List<?> that is safe in its declaration; Java does not guarantee always creating a new object when calling `List.of()`, and in this lesson that is not needed either.

## 13. Static Initializers Also Do Not Have Outer `T`

A static initializer runs when **class initialization** takes place, not separately for `Box<String>` or `Box<Integer>`. Inside this initializer, the outer class type parameter cannot be used as a type name.

~~~java
class Example<T> {
    private static int initialized;

    static {
        initialized = 1;
        // T value = null; // Invalid: class T in static context.
    }

    static int status() {
        return initialized;
    }
}
~~~

If the block needs to process type-specific data, it does not have a concrete T to decide on. It is better to:

- Use concrete static metadata independent of T.
- Pass a type token or object into a **method** at runtime.
- Place per-instance data in instance fields.
- If generic processing is needed, use separate static method type parameters.

### 13.1. Initialization Order

Class initialization only occurs according to JVM class initialization rules. Static fields/blocks are not recreated whenever a different parameterization is formed. Constructors run **each time an object is created**, whereas static initializers run according to the class initialization lifecycle.

## 14. Program 6: Static Block Once for Multiple Parameterizations

Save **`GenericStaticInitDemo.java`**:

~~~java
public class GenericStaticInitDemo {
    static class Box<T> {
        private static int sequence;

        static {
            System.out.println("Box static initialized");
        }

        private final int id;
        private final T value;

        Box(T value) {
            this.value = value;
            id = ++sequence;
            System.out.println("constructed " + id);
        }

        int id() {
            return id;
        }

        T value() {
            return value;
        }
    }

    public static void main(String[] args) {
        System.out.println("before");
        Box<String> first = new Box<>("A");
        Box<Integer> second = new Box<>(2);

        System.out.println("first=" + first.id() + ":" + first.value());
        System.out.println("second=" + second.id() + ":" + second.value());
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericStaticInitDemo.java
java GenericStaticInitDemo
~~~

Output:

~~~text
before
Box static initialized
constructed 1
constructed 2
first=1:A
second=2:2
~~~

In a fresh JVM, the static initializer prints **once** when Box is first initialized. `sequence` increments across both objects, even though their type arguments differ. If constructors run across multiple threads, `++sequence` needs synchronization/an atomic counter to ensure unique IDs; this example is intentionally single-threaded.

## 15. Static Nested Classes Do Not Capture Outer Generic `T`

A generic outer class:

~~~java
class Container<T> {
    static class Slot<U> {
        U value;
    }

    class Inner {
        T value;
    }
}
~~~

- `Slot<U>` is a **static nested class**: it has no enclosing `Container<T>` instance, so it **cannot directly use the outer T** in its declaration/body.
- It can declare its own **type parameter U** on Slot itself.
- `Inner` is a **non-static inner class**: it is bound to an enclosing Container<T> instance, so it can use the outer T.
- Even if `Slot` has an instance method, it still does **not** see the outer T because of that. This is a common mistake: an "instance" of Slot is not an instance of Container.

Invalid:

~~~java
class Container<T> {
    static class Wrong {
        // T field; // Compile-time error: outer T is not usable.
    }
}
~~~

Valid:

~~~java
class Container<T> {
    static class Slot<U> {
        U field;
    }
}
~~~

### 15.1. Nested Class Type Parameters Differ From Outer Class

`Container.Slot<Integer>` uses U=Integer. It does **not** use T from `Container<String>`. Static nested classes do not attach the enclosing class's generic parameterization to the type name when accessed.

## 16. Program 7: Static Nested and Non-Static Inner

Save **`GenericNestedClassesDemo.java`**:

~~~java
public class GenericNestedClassesDemo {
    static class Envelope<T> {
        private final T item;

        Envelope(T item) {
            this.item = item;
        }

        class Inner {
            T readOuter() {
                return item;
            }
        }

        static class Slot<U> {
            private final U value;

            Slot(U value) {
                this.value = value;
            }

            U value() {
                return value;
            }
        }
    }

    public static void main(String[] args) {
        Envelope<String> envelope = new Envelope<>("hello");
        Envelope<String>.Inner inner = envelope.new Inner();

        Envelope.Slot<Integer> slot =
                new Envelope.Slot<>(17);

        System.out.println("inner=" + inner.readOuter());
        System.out.println("slot=" + slot.value());
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericNestedClassesDemo.java
java GenericNestedClassesDemo
~~~

Output:

~~~text
inner=hello
slot=17
~~~

### 16.1. Why the Syntax Differs

`Envelope<String>.Inner` is an inner type bound to `Envelope<String>`; the expression `envelope.new Inner()` provides the enclosing instance.

`Envelope.Slot<Integer>` is a static nested type, accessed through the **raw outer class name used as a qualifier**, not through an instance and without attaching the String type argument of the outer Envelope.

**Do not write** `Envelope<String>.Slot<Integer>`: a static member type of a generic class cannot be qualified by a parameterized outer type.

## 17. Nested Records and Nested Enums Are Also Implicitly Static

Java 17 specifies particular static semantics for member/local records and enums. A **member record** inside a generic class:

~~~java
class Table<T> {
    record Row<U>(U value) {
    }

    // record Invalid(T value) {} // Invalid: cannot use outer T directly.
}
~~~

`Row<U>` declares its own U. It does not capture a Table<T> instance and has no default field storing the outer T.

A **member enum** is also implicitly static and cannot use the outer type parameter T directly in its body. An enum cannot declare its own generic type parameters such as `enum E<T>`, so if you need stored state that is generic per caller, an enum cannot replace a generic class/record.

### 17.1. Program 8: Nested Record With Its Own Generic Parameter

Save **`GenericNestedRecordDemo.java`**:

~~~java
public class GenericNestedRecordDemo {
    static class Table<T> {
        record Row<U>(U value, int index) {
        }
    }

    public static void main(String[] args) {
        Table.Row<String> first = new Table.Row<>("A", 0);
        Table.Row<Integer> second = new Table.Row<>(20, 1);

        System.out.println("first=" + first);
        System.out.println("second=" + second);
        System.out.println("same row class=" +
                (first.getClass() == second.getClass()));
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericNestedRecordDemo.java
java GenericNestedRecordDemo
~~~

Output:

~~~text
first=Row[value=A, index=0]
second=Row[value=20, index=1]
same row class=true
~~~

`Table.Row` does not require `new Table<?>` first. Two parameterizations of the static nested record Row still share the runtime Row class; the Row instances themselves hold different U values.

## 18. Type Erasure Explains Why Static State Is Not Specialized by T

Java generics use **type erasure**. For example:

~~~java
Box<String> text = new Box<>("A");
Box<Integer> number = new Box<>(1);
~~~

Type checking of `Box<String>`/`Box<Integer>` happens at compile time. At runtime, the same generic class declaration Box is used by the JVM for both objects (within the same defining class loader). The JVM does not create separate BoxOfString and BoxOfInteger classes with their own static storage.

The differences between `String` and `Integer` still have huge compile-time significance: the compiler prevents passing Box<Integer> to an API requiring Box<String>, and can generate appropriate casts after erasure. However, **runtime class identity** does not depend on those generic type arguments.

### 18.1. Do Not Assume That Generic T Is Always Object

If `class Numeric<T extends Number>`, the erasure of T is the first bound `Number` rather than always Object. Therefore, generic erasure should not be described as "every T becomes Object". The rule that the type parameter is unavailable in static contexts still holds, regardless of the bound.

### 18.2. Where Are Static Fields Stored?

Semantically, static fields belong to one runtime class, not to individual instances. JVM initialization/field layout details are an implementation concern; do not assume different class files for each parameterized type.

## 19. Program 9: Type Erasure and Class Identity

Save **`GenericErasureStaticDemo.java`**:

~~~java
public class GenericErasureStaticDemo {
    static class Pair<T> {
        private static int total;
        private final T value;

        Pair(T value) {
            this.value = value;
            total++;
        }

        T value() {
            return value;
        }

        static int total() {
            return total;
        }
    }

    public static void main(String[] args) {
        Pair<String> a = new Pair<>("A");
        Pair<Double> b = new Pair<>(2.5);

        System.out.println("same runtime type=" +
                (a.getClass() == b.getClass()));
        System.out.println("shared total=" + Pair.total());
        System.out.println("a=" + a.value());
        System.out.println("b=" + b.value());
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericErasureStaticDemo.java
java GenericErasureStaticDemo
~~~

Output:

~~~text
same runtime type=true
shared total=2
a=A
b=2.5
~~~

Again we see shared static state for two parameterizations. This is **one runtime class**, with two objects having different compile-time generic views.

## 20. Do Not Qualify Static Members With a Parameterized Class Name

Invalid in Java source:

~~~java
// int count = Pair<String>.total();
//              ^^^^^^^^^^^^ cannot use
// a parameterized type to qualify a static member.
~~~

Valid:

~~~java
int count = Pair.total();
~~~

Both lines are snippets with `Pair` having a valid static method `total()`. JLS `4.5.2 specifies that a static member declared in a generic type is referenced via the **generic class/interface name**, not via a parameterized type.

The same applies to:

- Static field `Box.COUNT`.
- Static method `Box.of(...)`.
- Static nested type `Box.Nested<U>`.
- Do not write `Box<String>.COUNT` or `Box<String>.of(...)`.
- An instance is not needed to access a static member; although Java allows some forms of access via an expression, that approach easily misleads readers and usually produces an IDE warning.

**Pay special attention:** `Box.<String>of(...)` **differs from** `Box<String>.of(...)`. Type arguments **after the dot and before the method name** are an explicit **generic method invocation**; type arguments **attached to the class name** form a parameterized outer type, which is invalid when qualifying a static member.

## 21. Class Type Parameter With Runtime `Class<T>`

Another error:

~~~java
class TypeBox<T> {
    // Class<T> cannot be declared as a static field using outer T.
    // static Class<T> TOKEN; // Invalid.

    // T.class is also invalid, because T is not a reifiable type.
}
~~~

### 21.1. `T.class` Is Not Allowed, Even in an Instance Method

~~~java
class TypeBox<T> {
    // Class<?> rawType() {
    //     return T.class; // Compile-time error.
    // }
}
~~~

The reason is not just static/instance; the type variable T does not have a valid class literal under type erasure.

### 21.2. Passing an Explicit `Class<T>` Token

Typical approach:

~~~java
class TypedBox<T> {
    private final Class<T> type;

    TypedBox(Class<T> type) {
        this.type = type;
    }

    T cast(Object input) {
        return type.cast(input);
    }
}
~~~

The caller passes `String.class` when creating `TypedBox<String>`, letting the runtime know the expected raw Class type. However, a `Class<T>` token **does not retain all generic type arguments** of nested structures like `List<String>` because `List.class` does not represent detailed parameterized types.

## 22. Program 10: Generic Static Factory and Type Token

Save **`GenericTypeTokenDemo.java`**:

~~~java
public class GenericTypeTokenDemo {
    static final class TypeBox<T> {
        private final Class<T> type;

        private TypeBox(Class<T> type) {
            this.type = type;
        }

        static <U> TypeBox<U> of(Class<U> type) {
            return new TypeBox<>(type);
        }

        T cast(Object input) {
            return type.cast(input);
        }

        String typeName() {
            return type.getSimpleName();
        }
    }

    public static void main(String[] args) {
        TypeBox<String> strings = TypeBox.of(String.class);
        TypeBox<Integer> integers = TypeBox.of(Integer.class);

        System.out.println("string type=" + strings.typeName());
        System.out.println("integer type=" + integers.typeName());
        System.out.println("cast string=" + strings.cast("ready"));
        System.out.println("cast integer=" + integers.cast(17));

        try {
            integers.cast("not an integer");
        } catch (ClassCastException expected) {
            System.out.println("wrong type rejected");
        }
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericTypeTokenDemo.java
java GenericTypeTokenDemo
~~~

Output:

~~~text
string type=String
integer type=Integer
cast string=ready
cast integer=17
wrong type rejected
~~~

The static factory `TypeBox.of(Class<U>)` has its own `<U>`, while each object stores `Class<T> type` as an **instance field**. `Class.cast` checks the runtime raw class when needed, without using `T.class`.

## 23. `new T()`, `T[]`, and `instanceof T` Are Not Ways to Work Around the Static Restriction

Sometimes beginners think: "If T cannot be used in static, just turn the method into an instance method and call `new T()`." That is still invalid under other rules.

~~~java
class Example<T> {
    // T create() {
    //     return new T(); // Invalid due to erasure/type variable.
    // }

    // T[] createArray() {
    //     return new T[10]; // Invalid: generic array creation.
    // }

    // boolean matches(Object input) {
    //     return input instanceof T; // Invalid: T is not reifiable.
    // }
}
~~~

`T` is usable as a field/parameter/return type in an instance context, **but** not every operation that requires a runtime concrete type is valid with T.

**Workarounds:**

- Pass a `Supplier<T>` if you need to create values using a factory.
- Pass a `Class<T>` and use `type.cast(...)` when a runtime raw type check is sufficient.
- Use a `List<T>` collection instead of a generic array if the algorithm permits.
- Use `instanceof Box<?>` for a wildcard-reifiable type instead of `instanceof Box<String>` when the generic parameterization is not reifiable.

### 23.1. Do Not Mix Up the Two Categories of Errors

| Code | Why is it invalid? |
| --- | --- |
| `static T x;` | Outer T is not usable in a static context |
| `static T copy(T x)` | Outer T is not usable in a static method signature |
| `static Object f() { return this; }` | Static method has no `this` |
| `static Object f() { return value; }` | Instance field requires a receiver |
| `T.class` in an instance method | Class literal requires a reifiable type; a type variable does not satisfy this |
| `new T()` in an instance method | Cannot directly instantiate a type variable |
| `new T[10]` | Generic array creation restriction |
| `input instanceof T` | Type variable is not reifiable |
| `Box<String>.count` | Static member cannot be qualified with a parameterized type |
| `static <U> U copy(U x)` | **Valid**, U belongs to the generic method |

Understanding the cause helps you fix the right place, instead of randomly switching between static and instance.

## 24. Bounded Generic Classes and Bounded Static Methods

A generic class with a bound:

~~~java
class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double doubleValue() {
        return value.doubleValue();
    }

    // static T zero() { ... } // Still invalid.
}
~~~

`T extends Number` does not create a "fixed T" for static members. A bounded type parameter of the **class** is still not usable in a static context.

A static method can declare **its own bounded type variable**:

~~~java
static <N extends Number> double twice(N number) {
    return number.doubleValue() * 2;
}
~~~

`N` belongs to the method and has the bound Number, so the code can call `doubleValue()`.

## 25. Program 11: Bounded Generic Static Method

Save **`GenericStaticBoundDemo.java`**:

~~~java
public class GenericStaticBoundDemo {
    static class NumericBox<T extends Number> {
        private final T number;

        NumericBox(T number) {
            this.number = number;
        }

        double instanceValue() {
            return number.doubleValue();
        }

        static <N extends Number> double twice(N input) {
            return input.doubleValue() * 2.0;
        }
    }

    public static void main(String[] args) {
        NumericBox<Integer> first = new NumericBox<>(7);
        NumericBox<Double> second = new NumericBox<>(2.5);

        System.out.println("first=" + first.instanceValue());
        System.out.println("second=" + second.instanceValue());
        System.out.println("twice 7=" + NumericBox.twice(7));
        System.out.println("twice 2.5=" + NumericBox.twice(2.5));
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericStaticBoundDemo.java
java GenericStaticBoundDemo
~~~

Output:

~~~text
first=7.0
second=2.5
twice 7=14.0
twice 2.5=5.0
~~~

`N extends Number` is a **method-owned N**, not the outer `T extends Number`. At each invocation, the compiler infers a valid N.

## 26. Generic Static Methods With Multiple Type Parameters

A static method can declare `<K, V>` to return a pair of values:

~~~java
static <K, V> Pair<K, V> pair(K key, V value) {
    return new Pair<>(key, value);
}
~~~

The outer class `Factory<T>`, if present, is still unrelated to K/V of the static method.

### 26.1. Program 12: Pair Factory

Save **`GenericStaticPairFactoryDemo.java`**:

~~~java
public class GenericStaticPairFactoryDemo {
    record Pair<K, V>(K key, V value) {
    }

    static class Factory<T> {
        static <K, V> Pair<K, V> pair(K key, V value) {
            return new Pair<>(key, value);
        }
    }

    public static void main(String[] args) {
        Pair<String, Integer> age = Factory.pair("Lan", 20);
        Pair<Integer, String> code = Factory.pair(200, "OK");

        System.out.println("age=" + age);
        System.out.println("code=" + code);
        System.out.println("key=" + age.key());
        System.out.println("value=" + code.value());
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericStaticPairFactoryDemo.java
java GenericStaticPairFactoryDemo
~~~

Output:

~~~text
age=Pair[key=Lan, value=20]
code=Pair[key=200, value=OK]
key=Lan
value=OK
~~~

`Pair<K,V>` is a generic record with its own type parameters, while `Factory<T>` carries no type information for the static `pair`. The static factory method still returns a strongly typed Pair.

## 27. Generic Interfaces Also Have Similar Static Restrictions

Not just generic classes: generic interfaces have interface-level type parameters.

~~~java
interface Converter<T> {
    T convert(String input);

    // static T wrong(String s) { return null; }
    // Invalid: a static method of a generic interface cannot use outer T.
}
~~~

A static method of an interface can have its own type parameter:

~~~java
interface Converter<T> {
    T convert(String input);

    static <U> U identity(U value) {
        return value;
    }
}
~~~

In an interface, fields are always implicitly `public static final`, so you cannot directly have an interface field of type outer T. Static interface methods are also not inherited like instance methods through implementing classes.

### 27.1. Program 13: Interface Instance + Generic Static Helper

Save **`GenericInterfaceStaticDemo.java`**:

~~~java
public class GenericInterfaceStaticDemo {
    interface Transformer<T> {
        T transform(T input);

        static <U> U echo(U input) {
            return input;
        }
    }

    static class Uppercase implements Transformer<String> {
        @Override
        public String transform(String input) {
            return input.toUpperCase(java.util.Locale.ROOT);
        }
    }

    public static void main(String[] args) {
        Transformer<String> converter = new Uppercase();

        System.out.println("instance=" +
                converter.transform("hello"));
        System.out.println("static string=" +
                Transformer.echo("ready"));
        System.out.println("static integer=" +
                Transformer.echo(17));
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericInterfaceStaticDemo.java
java GenericInterfaceStaticDemo
~~~

Output:

~~~text
instance=HELLO
static string=ready
static integer=17
~~~

The interface method `transform(T)` uses the type parameter T because it is an instance contract. Static `echo<U>` declares its own U and is called via `Transformer.echo(...)`. Do not use `Transformer<String>.echo(...)`.

## 28. Shared Mutable Static Cache: A Common Design Mistake

Suppose a generic repository holds:

~~~java
class Cache<T> {
    static Object last;
}
~~~

This is a **valid** declaration because Object is not the outer T. However, it is **not type-safe per T**: all `Cache<String>` and `Cache<Integer>` instances share one static field `last`.

If the code retrieves `last` and casts it according to the expected T, the programmer can trigger a `ClassCastException` at runtime or leak data between logical types. Replacing `Object` with a raw `List` can also introduce unchecked warnings/heap pollution.

### 28.1. Anti-Pattern Code You Should Not Use

~~~java
class UnsafeCache<T> {
    private static Object last;

    void remember(T value) {
        last = value;
    }

    @SuppressWarnings("unchecked")
    T getLast() {
        return (T) last; // Unchecked cast, no per-T isolation.
    }
}
~~~

The code above **can compile**, but it does not prove safety. After type erasure, the cast at the call site can fail when writes and reads come from different parameterizations.

**Fix according to the actual problem:**

- If the cache belongs to **each object**, use an instance field `private T last`.
- If the cache belongs to an application scope, use an external typed service or a complete key with an appropriate type token/checks.
- If the cache is shared read-only and independent of T, use a static immutable constant with a concrete/wildcard type.
- If caching truly needs to be per-type, explicitly design a `Map<Class<?>, ...>` and runtime type checks/ownership; do not assume generic parameterizations automatically provide separate static fields.

## 29. Program 14: Using an Instance Field to Separate State by T

Save **`GenericInstanceCacheDemo.java`**:

~~~java
public class GenericInstanceCacheDemo {
    static class Cache<T> {
        private T last;

        void remember(T value) {
            last = value;
        }

        T last() {
            return last;
        }
    }

    public static void main(String[] args) {
        Cache<String> text = new Cache<>();
        Cache<Integer> numbers = new Cache<>();

        text.remember("A");
        numbers.remember(99);

        System.out.println("text=" + text.last());
        System.out.println("numbers=" + numbers.last());
        System.out.println("same runtime cache class=" +
                (text.getClass() == numbers.getClass()));
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericInstanceCacheDemo.java
java GenericInstanceCacheDemo
~~~

Output:

~~~text
text=A
numbers=99
same runtime cache class=true
~~~

The runtime class of the two Caches is the same, **but** each instance holds its own `last` field. `T` in the instance context gives the compiler compile-time type safety for each reference.

### 29.1. If You Need "One Cache Per T", Is an Instance Field Enough?

Not necessarily: each Cache<T> instance has its own state, rather than all Cache<String> instances sharing one cache by default. If you genuinely want a shared cache per logical type, you need an **explicit registry design** appropriate for lifecycle, key identity, and concurrency; static fields of a generic class do not do that automatically.

## 30. Token-Keyed Static Registry: A Powerful Solution Requiring Caution

A type-aware registry typically uses `Class<?>` as keys:

~~~java
java.util.Map<Class<?>, Object> values =
        new java.util.HashMap<>();
~~~

This separates keys like `String.class` and `Integer.class` at runtime, but:

- `Class<List<String>>` has no separate literal; `List.class` does not carry the full nested parameterization.
- `Object` values require a runtime cast/validation on read.
- If the global registry involves concurrency, it needs a thread-safe data structure/atomicity convention.
- Shared static state creates lifetime/cleanup concerns.
- A class token can differ across class loaders even with the same textual name.
- A `Class<T>` token helps check the raw class, rather than automatically guaranteeing all nested generic arguments.

Therefore, you should not recommend "just using `Map<Class<?>, Object>` gives a completely safe generic cache". For business data, it may be better to use an object-scoped instance cache or a dependency injection service.

## 31. Static Singletons for Generic Classes Have Type Limitations

A pattern people often try:

~~~java
class Service<T> {
    // static final Service<T> INSTANCE = new Service<>();
    // Invalid: outer T in static field type.
}
~~~

If all instances are truly identical, you can have:

~~~java
class Service<T> {
    private static final Service<?> SHARED = new Service<>();

    private Service() {
    }
}
~~~

However, converting `Service<?>` into `Service<T>` arbitrarily **is not automatically type-safe**. If Service holds mutable state depending on T, sharing a singleton between String and Integer is error-prone. A generic factory can safely create a new instance on each call:

~~~java
static <U> Service<U> create() {
    return new Service<>();
}
~~~

If the type has no instance state depending on U and the API genuinely uses a stateless singleton, a carefully encapsulated cast may be acceptable in library internals, but it must be justified; do not apply it merely to "keep the compiler quiet".

## 32. Static Methods and Overload Resolution/Type Inference

A static generic method can infer U based on arguments and the target type. For example:

~~~java
static <U> java.util.List<U> singleton(U element) {
    return java.util.List.of(element);
}
~~~

Call:

~~~java
java.util.List<String> words = Box.singleton("A");
java.util.List<Integer> nums = Box.singleton(1);
~~~

U is inferred per method invocation. No static storage "belonging to String" or "belonging to Integer" is created because of inference; there is only one static method declaration.

### 32.1. Inference Errors Should Not Be Fixed With Raw Types

If the compiler reports that it cannot infer U, check constraints, overloads, target type, and bounds. Using raw `Box` or unchecked casts may silence warnings but creates heap pollution. You can explicitly specify the method type argument such as `Box.<Number>singleton(1)` when the API allows it.

### 32.2. A Generic Method Type Variable Does Not Have to Be Class T

Even inside `class Box<T>`, an instance method can also declare its own `<U>`; that is the flexibility of Java generics, not a static-only feature.

## 33. Comparison: Same Letter `T`, Different Declarations

~~~java
class Example<T> {
    private T value;

    T instanceIdentity(T item) {
        return item;
    }

    static <U> U staticIdentity(U item) {
        return item;
    }

    static <T> T confusing(T item) {
        return item;
    }
}
~~~

The whole block is a valid class snippet (placed in an appropriate file/scope). In `static <T> T confusing(T item)`, the letter T is a **method type parameter**, shadowing the class T. Although the compiler allows it, style typically uses `<U>` for the method to avoid confusing it with the outer/class generic state.

**Do not write:**

~~~java
// static T missing(T item) { return item; }
// Because the method does NOT declare <T>, the letter T refers to the outer T.
~~~

This is a small syntactic difference that determines compile-time correctness.

## 34. Program 15: A Method-Owned T With the Same Name Still Does Not Use Outer T

Save **`GenericStaticShadowDemo.java`**:

~~~java
public class GenericStaticShadowDemo {
    static class Holder<T> {
        private final T value;

        Holder(T value) {
            this.value = value;
        }

        T instanceValue() {
            return value;
        }

        static <T> T echo(T value) {
            return value;
        }
    }

    public static void main(String[] args) {
        Holder<String> holder = new Holder<>("outer");

        System.out.println("instance=" + holder.instanceValue());
        System.out.println("static integer=" + Holder.echo(10));
        System.out.println("static text=" + Holder.echo("inner"));
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericStaticShadowDemo.java
java GenericStaticShadowDemo
~~~

Output:

~~~text
instance=outer
static integer=10
static text=inner
~~~

Even though Holder declares outer T and echo declares method T with the same letter, the static method echo remains independent and cannot "read T=String from holder". Naming the type parameters differently makes the intent even clearer.

## 35. Generic Class Inheritance and Static Members

Suppose:

~~~java
class Parent<T> {
    static int count;
}

class Child<U> extends Parent<U> {
}
~~~

`Parent.count` is a static field of the Parent generic declaration. Even though Child extends Parent<U>, it does not create a separate count for Parent<String> or Parent<Integer>. Static fields can be **inherited/hidden** according to Java rules, but that is not per-type-parameter storage.

When reading code, you should use the **declaring class name** `Parent.count` to indicate the source of the static field clearly, rather than accessing it through an instance/derived name that causes confusion about member resolution.

If a subclass declares a static field with the same name, that is **field hiding** (unlike instance polymorphism), not generic type specialization. Avoid using identical names when not necessary.

## 36. Table of Common Errors and Fixes

| Misconception or erroneous code | Fix / correct interpretation |
| --- | --- |
| `static T cache;` in `class Box<T>` | Outer T is not usable in a static context; use an instance field or a concrete/wildcard type |
| `static List<T> items;` | Using outer T as a type argument in a static declaration is prohibited |
| `static T create(T x)` | Declare `static <U> U create(U x)` if the method is independent |
| `static Box<T> of(T x)` | Use `static <U> Box<U> of(U x)` |
| `static T get() { return null; }` | The signature is already invalid even though the body does not access an instance |
| `static Object f(){ return this; }` | There is no `this` in a static method |
| `static Object f(){ return value; }` | An instance field requires a concrete receiver |
| `static { T x = ...; }` | Static initializer cannot use outer T |
| `static class Node { T data; }` | Static nested class cannot use outer T; declare `Node<U>` |
| `record Entry(T value)` nested inside a generic class | Member record is implicitly static; declare `Entry<U>` |
| `static final List<T> EMPTY` | Use `List<?>` or a static generic method returning `List<U>` |
| `Box<String>.count` | Qualify the static member with `Box.count` |
| `Box<String>.of(x)` | Use `Box.of(x)` or `Box.<String>of(x)` |
| "`Box<String>` has its own static field" | No; one runtime class, shared static state |
| `new T()` in an instance method | Invalid due to type variable/reifiability, not just static |
| `T.class` in an instance method | Not allowed; pass a `Class<T>` token when needed |
| `instanceof T` | Not allowed; use an appropriate reifiable target/check |
| `Box<List<String>>.getClass()` returns a separate Class | Runtime raw class identity is shared |
| "`T extends Number` makes static T valid" | No, the bound does not remove the static-context restriction |
| "`static <T>` is the outer T" | No, a new method type parameter shadows the outer T |
| "Static counter is thread-safe because it is generic" | No; `++` needs concurrency control if multithreaded |
| "`Object` static cache works for every T" | The compiler may allow it, but type safety can be lost |
| "`Class<T>` token retains all nested generics" | No; the token represents the raw runtime class, and nested arguments undergo erasure |

## 37. Code Review Checklist

- [ ] For a class with type parameter `<T>`, which fields are instance fields and which are static?
- [ ] Does outer T appear in any static field declaration?
- [ ] Does outer T appear in any static method signature/body?
- [ ] Does outer T appear in any static initializer?
- [ ] Does any static nested class/record/enum accidentally reference outer T?
- [ ] Does each static generic utility declare its own `<U>` before the return type?
- [ ] Are method and class type parameters given the same letter in a misleading way?
- [ ] If a static method needs instance data, does it accept an appropriate object receiver?
- [ ] Are static members qualified with the generic class name rather than a parameterized name?
- [ ] Is the code relying on an assumption that static fields are duplicated per `Box<String>` and `Box<Integer>`?
- [ ] If storing static shared mutable state, how are concurrency/ownership/lifetime handled?
- [ ] Are justified `List<?>` or concrete static types used instead of raw types?
- [ ] If type-specific state is needed, is an instance field or an explicit type-keyed service more appropriate?
- [ ] Are `new T()`/`T.class`/`instanceof T` mistakenly assumed to be fixable by making the method non-static?
- [ ] Does a bounded static generic helper declare its own bounds, such as `<U extends Number>`?
- [ ] Does the constructor/factory have a `Box<U>` return type compatible with compiler inference?
- [ ] Does the static nested class declare its own type parameter if it needs to store generic values?
- [ ] Does the inner class truly need the enclosing instance lifetime and outer T?
- [ ] Do generic interface static methods have their own type parameters according to the rules?
- [ ] Do unit tests running on Java 17+ avoid relying on fixed warning/error wording?
- [ ] Are class identity and static count checked across two parameterizations in the same JVM?
- [ ] If a `Class<T>` token is needed, are nested generic type limitations handled properly?

## 38. Exercises and Answers

**Question 1.** In `class Box<T>`, is `static T value;` valid?  
**Answer:** No. The outer class T is not usable in a static field declaration.

**Question 2.** Why does Java not store separate static values for Box<String>/Box<Integer>?  
**Answer:** Parameterizations share the same runtime class, and static state is attached to the class declaration, not to each type argument.

**Question 3.** Is the instance method `T get()` valid?  
**Answer:** Yes.

**Question 4.** Is `static T get()` valid even if the method only does `return null;`?  
**Answer:** No. The static return type T is still the outer class type parameter.

**Question 5.** Write a static generic identity method.  
**Answer:** `static <U> U identity(U input) { return input; }`.

**Question 6.** Does `<U>` appear before or after the return type?  
**Answer:** After the modifiers, before the return type.

**Question 7.** Does `static <T> T copy(T value)` in `class Box<T>` use the outer T?  
**Answer:** No; the method T is a new declaration that shadows the outer T.

**Question 8.** Does `Box.<String>of("A")` specify a type argument for the class or the method?  
**Answer:** For the static generic method `of`.

**Question 9.** Is `Box<String>.of("A")` valid for calling a static member?  
**Answer:** No; a static member cannot be qualified through a parameterized type.

**Question 10.** How do `Box.count` and `Box<Integer>.count` differ?  
**Answer:** The first is valid; the second cannot be used as a qualifier for a static member.

**Question 11.** If a static helper wants to read the value of Box<T>, can it accept `Box<?> input`?  
**Answer:** Yes, and then call the instance accessor on the receiver.

**Question 12.** How do you preserve the exact return type U when reading Holder<U> from a static method?  
**Answer:** `static <U> U read(Holder<U> h) { return h.get(); }`.

**Question 13.** Is `static final List<?> EMPTY = List.of()` valid?  
**Answer:** Yes, it does not use outer T.

**Question 14.** Is `static final List<T> EMPTY` in Box<T> valid?  
**Answer:** No; it uses the outer class's T in a static declaration.

**Question 15.** Can a static nested class inside Generic<T> use T directly?  
**Answer:** No.

**Question 16.** Can a non-static inner class inside Generic<T> use T?  
**Answer:** Yes when rules/scope allow it, because it is bound to an enclosing instance.

**Question 17.** Can `static class Slot<U>` declare a type parameter U?  
**Answer:** Yes; U belongs to the nested class.

**Question 18.** Can a member record inside Generic<T> use outer T in its header?  
**Answer:** No, a member record is implicitly static; it must declare its own type parameter.

**Question 19.** Can a generic class's static initializer use T as a local variable type?  
**Answer:** No.

**Question 20.** If Box<T> only holds `static int count`, is count separated between String and Integer?  
**Answer:** No, the static count is shared.

**Question 21.** Is `T.class` valid inside an instance method?  
**Answer:** No, T is not a reifiable type.

**Question 22.** Is `new T()` valid inside an instance constructor?  
**Answer:** No, a type variable cannot be instantiated directly.

**Question 23.** How can you obtain a runtime Class<T>?  
**Answer:** You can pass a `Class<T>` token from the caller via a constructor/factory, depending on the domain.

**Question 24.** Does a `Class<T>` token distinguish `List<String>` and `List<Integer>` at runtime?  
**Answer:** Not with List.class; nested generic arguments are not preserved in a reified form like that.

**Question 25.** Can a bounded class `Numeric<T extends Number>` declare `static T zero`?  
**Answer:** No.

**Question 26.** Is the bounded static method `static <U extends Number> double twice(U x)` valid?  
**Answer:** Yes.

**Question 27.** Is `static Object last` in Cache<T> type-safe per T?  
**Answer:** No, the static object is shared; reading with the wrong type easily causes ClassCastException.

**Question 28.** What should you do when you need to store separate state per Cache<T> object?  
**Answer:** Use a `private T last` instance field.

**Question 29.** If you need a shared cache per logical runtime type, can generics handle it automatically?  
**Answer:** No; you need explicit registry/ownership/type checks, taking class tokens into consideration.

**Question 30.** Can a static method in a generic interface use the interface type parameter?  
**Answer:** No; declare its own generic method parameter if needed.

**Question 31.** Does static method type inference mean the JVM generates a separate method for each type argument?  
**Answer:** No, it is compile-time inference, with a shared runtime class/method declaration.

**Question 32.** If a generic class has instance methods using T and static methods using U, is that a design flaw?  
**Answer:** No; that is a normal pattern when each method has a clear responsibility.

**Question 33.** Is `Pair<K,V>` returned from `static <K,V> Pair<K,V> pair(K k,V v)` type-safe?  
**Answer:** Yes, when the type declarations and overloads are valid.

**Question 34.** What is the biggest mistake to remember?  
**Answer:** There is no definite class-level `T` for a **static context**; use instance members, method-owned generics, or explicit runtime type information depending on your goal.

## 39. Comprehensive Test Program

Save **`GenericStaticContractTest.java`**:

~~~java
public class GenericStaticContractTest {
    static class Box<T> {
        private static int created;
        private final T value;

        private Box(T value) {
            this.value = value;
            created++;
        }

        static <U> Box<U> of(U input) {
            return new Box<>(input);
        }

        T value() {
            return value;
        }

        static int count() {
            return created;
        }

        static <U> U read(Box<U> box) {
            return box.value();
        }
    }

    static void check(boolean ok, String label) {
        if (!ok) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Box<String> words = Box.of("JDK");
        Box<Integer> digits = Box.of(17);

        check(words.value().equals("JDK"), "word value");
        check(digits.value() == 17, "integer value");
        check(Box.count() == 2, "one shared static count");
        check(words.getClass() == digits.getClass(),
                "one runtime class");
        check(Box.read(words).equals("JDK"),
                "static method owns U");

        System.out.println("generic static checks passed");
    }
}
~~~

Run:

~~~bash
javac --release 17 GenericStaticContractTest.java
java GenericStaticContractTest
~~~

**Stdout:**

~~~text
generic static checks passed
~~~

The `check` method always performs the check even though Java `assert` is disabled by default unless `-ea` is enabled. The program uses **one shared static field**, two generic instance values, one generic factory, and one generic static read helper.

## 40. Official References

- [Java Language Specification SE 17 `8.1.2 — Generic Classes and Type Parameters`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.2): class type parameters, sharing runtime class across parameterizations.
- [JLS `8.1.3 — Inner Classes and Enclosing Instances`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.3): static nested/inner distinctions.
- [JLS `6.5.5.1 — Simple Type Names`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5.5.1): prohibition on class type parameter references in static context and nested static types.
- [JLS `4.5.2 — Members and Constructors of Parameterized Types`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.5.2): static members must be qualified with the generic type declaration name, not through a parameterized type.
- [JLS `8.4.4 — Generic Methods`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.4): syntax and method-owned type parameters.
- [JLS `4.6 — Type Erasure`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6): erased runtime representation.
- [JLS `8.3 — Field Declarations`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.3): static/instance fields.
- [JLS `8.7 — Static Initializers`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.7): static blocks.
- [JLS `15.8.2 — Class Literals`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.8.2): why `T.class` cannot be used.
- [JLS `15.20.2 — Type Comparison Operator instanceof`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): reifiable type restrictions.
- [JLS `9.1.2 — Generic Interfaces`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.2): similar interface-level generic restrictions.
- [Java SE 17, Class.cast](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#cast(java.lang.Object)): runtime casting with explicit Class token.
- [Java SE 17, List.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#of()): type-inferred unmodifiable collection factory.
- [Oracle Java Tutorial — Generic Methods](https://docs.oracle.com/javase/tutorial/java/generics/methods.html): method type parameter declaration and type inference (tutorial examples are historically Java 8; JLS 17 above is the standard for this lesson).

## Summary

In `class Box<T>`, **T is a class-level type parameter describing instance-typed data/behavior**. `static` belongs to the generic class declaration, not specifically to `Box<String>` or `Box<Integer>`; parameterizations share a single runtime class. Therefore, Java **does not allow using the outer `T` directly in static fields, static methods, static initializers, or static nested classes**.

The fix depends on your goal:

1. If the data belongs to each object, use an **instance field/method** with T.
2. If you need a generic static factory/helper, declare a **method-owned type parameter**: `static <U> Box<U> of(U input)`.
3. If you need shared static metadata, declare a concrete/wildcard type and do not expect static state to separate automatically by T.
4. If you need runtime type handling, pass an explicit `Class<T>` token or a typed factory, while remembering that erasure does not preserve all nested generic arguments.
5. If a static method needs instance data, accept an object parameter and call through the receiver instead of writing `this`.
6. For a static nested class/record, declare its own generic type parameters instead of referencing the outer class T.
7. Do not use a parameterized class name to qualify static members: `Box.count` or `Box.<String>of(...)` are the corresponding valid forms.

**One-sentence takeaway:** *A class's type parameter T is tied to instance usage at compile time; for a static context to be generic, it must declare its own method/type parameter rather than borrowing T directly from the outer class.*
