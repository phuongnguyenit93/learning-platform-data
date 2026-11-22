# Class-First Rule and Compatible Bounds in Java Generics

## 1. Lesson Objectives

In Java Generics, a **type bound** specifies which types a type parameter is allowed to represent and which methods can be invoked on it. A type parameter `T` can have **multiple upper bounds**, but this list must follow mandatory rules:

1. If there is a **class bound**, that class **must come first** in the list.
2. A type parameter cannot declare **two independent class bounds**.
3. The remaining bounds after the class bound must be **interface types**; they are joined by **&**, not a comma.
4. The bounds must be **compatible with each other**: they must follow Java inheritance rules and must not cause conflicts between specializations that cannot coexist or methods without compatible signatures.
5. Every actual type argument must satisfy **all** declared bounds.
6. **The first bound** plays a special role in **type erasure**; changing the order of bounds can have binary compatibility consequences.

Valid example:

~~~java
static <T extends Number & Comparable<T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

`T` must both be a subtype of `Number` and implement `Comparable<T>`. An `Integer` satisfies both conditions; a general `Number` does not automatically guarantee implementing `Comparable<Number>`.

This lesson focuses on **declaration rules, compatibility, and technical effects of multiple bounds**, and does not replace the full chapters on wildcards, PECS, or variance.

## 2. Type Bound Syntax

General syntax:

~~~text
<T extends FirstBound & Interface2 & Interface3>
~~~

Where:

- **T** is the declared type parameter.
- **extends** is the keyword used for **every upper bound**, whether that bound is a class or an interface.
- **FirstBound** can be a class or an interface.
- If there is a class bound, it **must be the first bound**.
- After the first bound, any additional bounds must be interface types.
- **&** joins bounds belonging to **the same** type parameter.

Examples:

~~~java
class NumericValue<T extends Number> {
    T value;
}

class SortedNumber<T extends Number & Comparable<T>> {
    T value;
}

class Exportable<T extends Number & Comparable<T> & java.io.Serializable> {
    T value;
}
~~~

All the declarations above are valid. In `SortedNumber`, `T` has both `Number` methods like `doubleValue()` and `compareTo(T)` from `Comparable<T>`.

A comma has a **different** meaning from `&`:

~~~java
class Pair<A extends Number, B extends CharSequence> {
    A first;
    B second;
}
~~~

**<A extends Number, B extends CharSequence>** declares **two type parameters** with separate bounds. It is not equivalent to **<T extends Number & CharSequence>**, which declares **one T** that must satisfy both `Number` and `CharSequence`.

| Syntax | Meaning |
| --- | --- |
| **<T>** | `T` has an implicit upper bound of `Object` |
| **<T extends Number>** | One `T`, class bound `Number` |
| **<T extends Runnable>** | One `T`, interface bound `Runnable` |
| **<T extends Number & Comparable<T>>** | One `T`, both `Number` and `Comparable<T>` |
| **<T extends Runnable & AutoCloseable>** | One `T`, satisfying two interfaces |
| **<A extends Number, B extends CharSequence>** | Two independent type parameters `A` and `B` |

## 3. If There Is a Class Bound, the Class Must Come First

Java specifies that in an intersection of bounds declared for a type parameter, a class can only appear in the **first position**. For example:

~~~java
// Valid:
class Good<T extends Number & Comparable<T>> {}
~~~

Reversing the two bounds to put the class second is invalid:

~~~java
// Compile error illustration:
class Wrong<T extends Comparable<T> & Number> {}
~~~

**Comparable<T>** is an interface; **Number** is a class and appears after `&`. This is a syntax/bound-structure error, not an error that only appears when applying a type argument.

The fix is to reverse the order:

~~~java
class Correct<T extends Number & Comparable<T>> {}
~~~

Nor can you write:

~~~java
// Compile error illustration:
class TwoClasses<T extends Number & Thread> {}
~~~

Both `Number` and `Thread` are classes. The fact that Java does not support a class inheriting from two independent superclasses simultaneously is also reflected in how type bounds are specified: **there is no list of two class bounds**.

**Important note:** if **there is no class bound**, an interface can come first. The following form is valid:

~~~java
class WorkItem<T extends Runnable & AutoCloseable> {
    T task;
}
~~~

Both `Runnable` and `AutoCloseable` are interfaces. Interface order may not matter for the "class comes first" rule, but the first bound can still affect erasure and bytecode; therefore do not arbitrarily change the order in a released public API.

## 4. `extends` Is Still Used When the Bound Is an Interface

In a type parameter declaration, Java only uses `extends`, even when the bound is an interface:

~~~java
class Runner<T extends Runnable> {
    private final T task;
    Runner(T task) { this.task = task; }
    void execute() { task.run(); }
}
~~~

Do not write `<T implements Runnable>`: `implements` is only used when declaring a class implementing an interface, not in a type-parameter bound. If combining a class and an interface, write `<T extends Thread & Runnable>` with `Thread` first; this bound makes `Runnable` somewhat redundant since `Thread` already implements that interface.

After getting the syntax right, the part worth evaluating more carefully is **whether the set of bounds can be satisfied simultaneously**. For instance, `String & Runnable` has no valid type argument because `String` is final and does not implement `Runnable`.

## 5. Bounds Must Have a Simultaneously Implementing Type

Read **<T extends A & B>** as a combined requirement:

~~~text
T must be a subtype of A
AND
T must be a subtype of B
~~~

It does **not** mean `T` gets to pick one of `A` or `B`.

Example:

~~~java
interface Printable {
    String print();
}

interface Identified {
    long id();
}

class Ticket implements Printable, Identified {
    private final long number;

    Ticket(long number) {
        this.number = number;
    }

    @Override
    public String print() {
        return "ticket-" + number;
    }

    @Override
    public long id() {
        return number;
    }
}
~~~

A generic method can require both interfaces:

~~~java
static <T extends Printable & Identified> String describe(T item) {
    return item.id() + ":" + item.print();
}
~~~

**Ticket** is a valid type argument because it implements both `Printable` and `Identified`. A type that implements only `Printable` and not `Identified` is invalid. Even though there is no class bound in the example, the compiler still allows calling both `print()` and `id()` on variable `T`.

**Compatibility has two levels that must be kept distinct:**

- **At the bound declaration:** The bounds must not contradict Java's type rules (for example, repeating the same generic interface with two different type arguments).
- **At the type-argument application site:** The concrete type passed in must satisfy all bounds. The fact that an arbitrary interface does not yet have an implementing class right at the declaration site **does not by itself make the intersection invalid**; a class can later implement multiple compatible interfaces at the same time.

Do not confuse "no satisfying class found yet" with "the bounds contradict each other".

## 6. Complete Runnable Example: Combining Multiple Interface Bounds

Save as **InterfaceBoundsDemo.java**:

~~~java
public class InterfaceBoundsDemo {
    interface Printable {
        String print();
    }

    interface Identified {
        long id();
    }

    static final class Ticket implements Printable, Identified {
        private final long number;

        Ticket(long number) {
            this.number = number;
        }

        @Override
        public String print() {
            return "ticket-" + number;
        }

        @Override
        public long id() {
            return number;
        }
    }

    static <T extends Printable & Identified> String describe(T item) {
        return item.id() + ":" + item.print();
    }

    public static void main(String[] args) {
        Ticket ticket = new Ticket(17);
        System.out.println(describe(ticket));

        Printable asPrintable = ticket;
        System.out.println(asPrintable.print());
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 InterfaceBoundsDemo.java
java InterfaceBoundsDemo
~~~

Exact stdout:

~~~text
17:ticket-17
ticket-17
~~~

In `describe(T)`, the compiler allows calling **item.id()** and **item.print()** because `T` has both interface bounds. When a variable is declared simply as `Printable`, the `id()` method does not appear in that variable type's contract; member access in source code depends on the **static type**, not only on the runtime object.

## 7. Combining a Class Bound with Multiple Interface Bounds

A practical scenario is wanting to work with numbers while also comparing and serializing that numeric type:

~~~java
import java.io.Serializable;

class NumericEntry<T extends Number & Comparable<T> & Serializable> {
    private final T number;

    NumericEntry(T number) {
        this.number = number;
    }

    double asDouble() {
        return number.doubleValue();
    }

    boolean isGreaterThan(T other) {
        return number.compareTo(other) > 0;
    }
}
~~~

Explanation:

- **Number** is the class bound, so it comes first.
- **Comparable<T>** is an interface bound, allowing `compareTo` with `T`.
- **Serializable** is an additional interface bound, without directly introducing new public methods to call on `T`.
- **Integer**, **Long**, and **Double** are examples of wrapper classes that can satisfy these bounds with appropriate type arguments.
- **String** does not satisfy `Number` even though `String` has `Comparable<String>` and `Serializable`.

Note that **Number itself already implements Serializable**; in this specific case, adding `Serializable` is redundant as a necessary condition. This is an intentional example to illustrate the three-bound syntax; in a real API, consider removing redundant bounds.

Do not think of a class bound as "converting `T` into a primitive". **T remains a reference type variable**, so **a + b** syntax for two `T` variables is not permitted like generic numeric addition. To add as `double`, you can take **a.doubleValue() + b.doubleValue()** and accept the numeric precision consequences.

An abstract class can also serve as a class bound, and the actual type argument can be a corresponding concrete subclass. A class bound does not have to be a concrete class with a no-arg constructor.

## 8. Complete Runnable Example: `Number`, `Comparable`, and `Serializable`

Save as **ClassFirstBoundsDemo.java**:

~~~java
import java.io.Serializable;

public class ClassFirstBoundsDemo {
    static final class NumericEntry<T extends Number & Comparable<T> & Serializable> {
        private final T value;

        NumericEntry(T value) {
            this.value = value;
        }

        double twice() {
            return value.doubleValue() * 2.0;
        }

        boolean greaterThan(T other) {
            return value.compareTo(other) > 0;
        }
    }

    static <T extends Number & Comparable<T>> T maximum(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        NumericEntry<Integer> entry = new NumericEntry<>(8);
        System.out.println(entry.twice());
        System.out.println(entry.greaterThan(3));
        System.out.println(maximum(4, 9));
        System.out.println(maximum(2.5, 1.5));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 ClassFirstBoundsDemo.java
java ClassFirstBoundsDemo
~~~

Stdout:

~~~text
16.0
true
9
2.5
~~~

Analysis:

1. **NumericEntry<Integer>** is valid because `Integer` extends `Number` and implements `Comparable<Integer>` and `Serializable`.
2. **twice()** uses `Number.doubleValue()`, returning `double`.
3. **greaterThan(3)** invokes `Comparable<Integer>.compareTo` with an `Integer` value after autoboxing.
4. In **maximum(4, 9)**, the matching type is inferred as `Integer`.
5. In **maximum(2.5, 1.5)**, the matching type is `Double`; the result is printed in standard `Double` format.

The `maximum` method uses `T` for both parameters and the return value so the compiler preserves the type relationship. The bounds permit calling `compareTo`; no cast from `Object` is needed.

## 9. What Are Incompatible Bounds?

There are several real kinds of conflicts to recognize.

### 9.1. Two class bounds are not allowed

~~~java
// Intentionally invalid:
class Invalid<T extends Number & Thread> {}
~~~

This violates the class bound rule, even if we could imagine a type satisfying both. A class bound, if any, must come first, and the rest must be interface types.

### 9.2. A `final` class and an interface that cannot be satisfied together

Illustrative example:

~~~java
// Intentionally invalid:
class Impossible<T extends String & Runnable> {}
~~~

`String` is a **final class** and does not implement `Runnable`. No subtype of `String` can be created to add `Runnable`; these bounds can never have a satisfying type argument. The compiler detects the contradiction. Conversely, if a class bound is not final, the fact that the class itself does not yet implement an interface does not necessarily make the declaration invalid; a subclass can add the interface.

### 9.3. The same generic interface required with two different specializations

Consider:

~~~java
interface TextComparable extends Comparable<String> {}

interface NumberComparable extends Comparable<Integer> {}

// Invalid:
// class Conflict<T extends TextComparable & NumberComparable> {}
~~~

A type `T` satisfying both `TextComparable` and `NumberComparable` would simultaneously be **Comparable<String>** and **Comparable<Integer>**. Java does not allow a subtype to inherit the same generic interface with two different type arguments. This is a generic supertype conflict that cannot be fixed with casts.

A more direct form:

~~~java
// Error illustration:
class ConflictDirect<T extends Comparable<String> & Comparable<Integer>> {}
~~~

`&` cannot be used to "merge" two versions of `Comparable` with conflicting type arguments.

### 9.4. Duplicate method signatures with incompatible return types

Two separate interfaces can declare the same method signature but with return types that cannot be satisfied together:

~~~java
interface StringReader {
    String read();
}

interface IntegerReader {
    Integer read();
}

// Conflicting bounds illustration:
// class ImpossibleReader<T extends StringReader & IntegerReader> {}
~~~

No zero-argument `read()` method can simultaneously return both `String` and `Integer` under both override contracts, because `String` and `Integer` are final classes without the needed subtype relationship.

If two interfaces have methods with the same signature and **covariant-compatible return types**, they can be implemented together by an appropriate class. For instance, one interface specifies `Object read()` and another specifies `String read()`; the implementing class can return `String`, since `String` is a subtype of `Object`.

**Practical rule:** when multiple bounds have methods with the same name, you must examine **erased signatures, return-type substitutability, default methods, and override rules**. Do not just see two differently named interfaces and conclude the intersection is valid.

### 9.5. Method name clash after type erasure

Example of contracts with the same erasure but different type arguments:

~~~java
interface Strings {
    void accept(java.util.List<String> values);
}

interface Integers {
    void accept(java.util.List<Integer> values);
}

// A type parameter trying to combine these bounds cannot
// assume there will be two independent overloads named accept(List<...>).
~~~

The two methods **accept(List<String>)** and **accept(List<Integer>)** have the same erasure for the `List` parameter. An implementing class generally cannot write two separate overloads differing only in type argument. Depending on the relationship between the declarations, the compiler may report a name clash or inheritance conflict. When designing intersection bounds, avoid placing contracts that cannot be implemented together on the same type parameter.

## 10. "Compatible" Does Not Mean the Interfaces Must Have a Parent–Child Relationship

A type can implement multiple independent interfaces:

~~~java
interface Auditable {
    String audit();
}

interface Validatable {
    boolean valid();
}

class Event implements Auditable, Validatable {
    @Override
    public String audit() {
        return "event";
    }

    @Override
    public boolean valid() {
        return true;
    }
}
~~~

The two interfaces do not have to extend one another. As long as a type argument satisfies both simultaneously and no member conflicts arise, the declaration:

~~~java
static <T extends Auditable & Validatable> boolean process(T item) {
    return item.valid() && !item.audit().isEmpty();
}
~~~

makes sense and the compiler allows both operations.

If interface `A` extends `B`, the bound **T extends A & B** may be redundant because satisfying `A` already implies satisfying `B`. Redundancy does not automatically make the API syntactically invalid, but it makes it harder for readers to see which constraint actually matters. Simplify the list when possible.

## 11. When There Are Only Interface Bounds, Order Still Has Technical Significance

The following two declarations both require type `T` to satisfy both `Serializable` and `Comparable<T>`:

~~~java
class First<T extends java.io.Serializable & Comparable<T>> {}

class Second<T extends Comparable<T> & java.io.Serializable> {}
~~~

At the level of the relationship "`T` must satisfy both", their conditions are equivalent. However, **the first bound** determines the type erasure of type variable `T` (when the first bound is an interface, the erasure is that interface):

- In `First`, the erasure of `T` is **Serializable**.
- In `Second`, the erasure of `T` is **Comparable**.

Therefore, changing the order of interface bounds in an already compiled and released API **can alter bytecode signatures** of fields/methods using `T` and affect binary compatibility. When designing a public library, do not treat reordering as a purely cosmetic change.

Example with a class bound:

~~~java
class ClassFirst<T extends Number & Comparable<T>> {
    T item;
}
~~~

The erasure of `T` is `Number`, because the first bound is `Number`. For an unbounded `T`, the erasure is usually `Object`. With the interface-only bound **<T extends Runnable & AutoCloseable>**, the first bound `Runnable` determines that `T` erases to `Runnable`.

**Important:** "erasure uses the first bound" is a rule describing the JVM representation level. In Java source code, the compiler still permits using methods guaranteed by **all bounds**, not only the first bound.

## 12. Complete Runnable Example: Interface Bound Order and Method Calling Rights

Save as **InterfaceOrderDemo.java**:

~~~java
public class InterfaceOrderDemo {
    interface Named {
        String name();
    }

    interface Scored {
        int score();
    }

    static final class Student implements Named, Scored {
        private final String name;
        private final int score;

        Student(String name, int score) {
            this.name = name;
            this.score = score;
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public int score() {
            return score;
        }
    }

    static <T extends Named & Scored> String first(T value) {
        return value.name() + ":" + value.score();
    }

    static <T extends Scored & Named> String second(T value) {
        return value.name() + ":" + value.score();
    }

    public static void main(String[] args) {
        Student student = new Student("Lan", 95);
        System.out.println(first(student));
        System.out.println(second(student));
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 InterfaceOrderDemo.java
java InterfaceOrderDemo
~~~

Stdout:

~~~text
Lan:95
Lan:95
~~~

Both generic methods can be called with `Student` because `Student` implements both `Named` and `Scored`. **first** has `Named` as its first bound; **second** has `Scored` as its first bound. The compiler still allows both methods to call `name()` and `score()` because the interface bounds are valid. The runtime output is identical, yet the erasure of `T` in the two method signatures can differ.

## 13. Type Bounds Are an Intersection, Not a Union

Understand these expressions clearly:

~~~java
<T extends Runnable & AutoCloseable>
~~~

This means `T` must **simultaneously** be `Runnable` and `AutoCloseable`. It does not accept any arbitrary `Runnable` *or* any arbitrary `AutoCloseable`.

The `&` here represents an intersection of conditions. Generic method example:

~~~java
static <T extends Runnable & AutoCloseable> void executeAndClose(T resource)
        throws Exception {
    try (resource) {
        resource.run();
    }
}
~~~

The example above is for Java 17+, where `resource` is an effectively final parameter in try-with-resources; a parameter is effectively final when it is not reassigned. `AutoCloseable.close` can throw `Exception`, so the method declares `throws Exception`. `Runnable.run` has no checked exception in its signature.

An object used with `executeAndClose` must implement both `Runnable` and `AutoCloseable`. Do not mistakenly pass a class that only implements `Runnable` to this method.

### Do not confuse with an intersection cast

Java also allows intersection types in casts, for example:

~~~java
// Only illustrating a cast expression:
Object source = /* compatible object */ null;
// Runnable task = (Runnable & AutoCloseable) source;
~~~

A cast performs corresponding runtime checks and can throw `ClassCastException` when the object does not implement the required types. This is **not** a substitute design for generic bounds when you want the compiler to verify type relationships in a method signature. If you are unsure about the runtime object, you should not cast merely to "push it through" a tightly bounded API.

## 14. When a Class Bound Is `final`: Check Compatibility with Interfaces

If a class bound is `final`, no new subclass can extend it. Therefore it must **satisfy** any additional interface bounds by itself; otherwise there will be no valid type argument.

Valid example:

~~~java
class TextComparable<T extends String & Comparable<String>> {
    T value;
}
~~~

`String` is `final` yet **already implements `Comparable<String>`**, so **String** can be a type argument. This is only an example of valid bounds, not a recommendation to create a type parameter `T` when the actual type can only be `String`. In that case, using `String` directly is usually simpler.

Invalid example:

~~~java
// String is final and does not implement Runnable:
// class TextRunnable<T extends String & Runnable> {}
~~~

Conversely, with a non-final class bound, a subclass can implement additional compatible interfaces:

~~~java
abstract class BaseJob {
    abstract String label();
}

interface Schedulable {
    void schedule();
}

class ScheduledJob extends BaseJob implements Schedulable {
    @Override
    String label() {
        return "scheduled";
    }

    @Override
    public void schedule() {}
}

class JobHolder<T extends BaseJob & Schedulable> {
    T job;
}
~~~

`ScheduledJob` satisfies both the class bound `BaseJob` and the interface bound `Schedulable`. `BaseJob` does not have to implement `Schedulable` beforehand.

## 15. Generic Methods Applying Multiple Bounds to Their Own Parameters

Bounds are not only used on generic classes:

~~~java
static <T extends Number & Comparable<T>> T min(T left, T right) {
    return left.compareTo(right) <= 0 ? left : right;
}
~~~

The type parameter `T` here belongs to the **generic method**, not an enclosing class. Any call site must supply type arguments satisfying the bounds. The method can reside in a non-generic class or a generic class.

If a generic class has an unbounded `T`, a `static` method inside cannot "borrow the class's `T`" to add bounds. The static method must declare its own type parameter:

~~~java
class Holder<T> {
    static <U extends Number & Comparable<U>> U max(U a, U b) {
        return a.compareTo(b) >= 0 ? a : b;
    }
}
~~~

`U` is independent of `Holder`'s `T`. Any use of `Holder<String>` or `Holder<Integer>` does not change the contract of the static method `max`.

### A method using multiple type parameters with different bounds

~~~java
static <A extends Number, B extends CharSequence> String summarize(A a, B b) {
    return b.length() + ":" + a.doubleValue();
}
~~~

The comma separates **A** and **B**, not two bounds on the same parameter. A call `summarize(3, "abcd")` can infer `A = Integer`, `B = String`. Inside the body, the compiler allows `doubleValue()` on `A` and `length()` on `B` according to their respective bounds.

## 16. Bound Compatibility Also Depends on Generic Type Arguments

Compatibility does not examine interface names alone. Type arguments used within bounds can introduce conflicts.

A valid example of F-bounded polymorphism:

~~~java
interface HasOrder<T> {
    int compareTo(T other);
}

class OrderedValue<T extends HasOrder<T>> {
    private final T value;

    OrderedValue(T value) {
        this.value = value;
    }

    boolean greaterThan(T other) {
        return value.compareTo(other) > 0;
    }
}
~~~

The bound **T extends HasOrder<T>** requires `T` to implement the very interface parameterized with `T` as its type argument. Referencing `T` inside its own bound **is not an automatic cyclic error**. This form is common in `Comparable<T>`, `Enum<E extends Enum<E>>`, or "self type" APIs.

A more complex bound:

~~~java
class OrderedNumber<T extends Number & Comparable<? super T>> {
    private final T value;

    OrderedNumber(T value) {
        this.value = value;
    }

    int compare(T another) {
        return value.compareTo(another);
    }
}
~~~

**Comparable<? super T>** allows `T` to be comparable with `T` or a suitable supertype of `T`. This is a broader expression than **Comparable<T>**, though it requires understanding variance and the actual `Comparable` contract.

Valid self-referential forms do not mean every circular bound is valid. For example, **<T extends T>** is an invalid cyclic bound with no valid basis, unlike **<T extends Comparable<T>>** where the bound is built on a concrete interface.

## 17. Erasure Collision Rules for Generic Interfaces to Watch Out For

Type erasure removes type argument information in many bytecode locations. Thus interface instantiations such as **Comparable<String>** and **Comparable<Integer>** have the same raw interface `Comparable` after erasure.

A class cannot inherit two different specializations of the same generic interface:

~~~java
interface One extends Comparable<String> {}
interface Two extends Comparable<Integer> {}

// Invalid:
// class Both implements One, Two {}
~~~

The bound form **<T extends One & Two>** likewise cannot produce a type argument `T` capable of following both inheritance paths.

Similarly, for a class or interface that already has a generic contract, avoid methods that differ only in type arguments:

~~~java
// Intentionally invalid:
class InvalidOverload {
    // void handle(java.util.List<String> a) {}
    // void handle(java.util.List<Integer> b) {}
}
~~~

After erasure, both overloads have parameter `List`; the compiler cannot distinguish them by the required runtime signature.

Do not work around this with raw types: raw types only weaken type checking and can introduce unchecked warnings without making two specializations compatible contracts.

## 18. First Bound, Erasure, and Binary Compatibility

An important rule in Java: the erasure of a type variable is the erasure of its **first bound**; if there is no bound, the erasure is usually `Object`.

Example:

~~~java
class A<T> {
    T get() { return null; }
}

class B<T extends Number> {
    T get() { return null; }
}

class C<T extends Runnable & AutoCloseable> {
    T get() { return null; }
}
~~~

At the erased signature level:

| Declaration | Erasure of `T` |
| --- | --- |
| A<T> | Object |
| B<T extends Number> | Number |
| C<T extends Runnable & AutoCloseable> | Runnable |

For **C**, the compiler still checks both `Runnable` and `AutoCloseable` when using a value of `T`. However, bytecode signatures involving `T` use the erasure `Runnable`, i.e., the first bound.

This can affect linking against previously compiled code if a library's public API changes the order of interface bounds and alters the erased method descriptor. Therefore, when maintaining a library, **changing bound order must be treated as a potential ABI-impacting change**, not merely rewording.

You can use **javap -p -s** to inspect descriptors after compilation. Generic syntax seen in source code and runtime descriptors are not completely identical. The compiler may add bridge methods in generic override scenarios to preserve dispatch behavior; that is a related detail, though it does not change the "class-first" declaration rule this lesson focuses on.

## 19. Runnable Example: Both `AutoCloseable` and `Runnable` Required

Save as **CombinedResourceDemo.java**:

~~~java
public class CombinedResourceDemo {
    static final class Task implements Runnable, AutoCloseable {
        private final String name;

        Task(String name) {
            this.name = name;
        }

        @Override
        public void run() {
            System.out.println("run:" + name);
        }

        @Override
        public void close() {
            System.out.println("close:" + name);
        }
    }

    static <T extends Runnable & AutoCloseable> void execute(T task)
            throws Exception {
        try (task) {
            task.run();
        }
    }

    public static void main(String[] args) throws Exception {
        execute(new Task("compile"));
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 CombinedResourceDemo.java
java CombinedResourceDemo
~~~

Stdout:

~~~text
run:compile
close:compile
~~~

Here **Task** implements both `Runnable` and `AutoCloseable`. The generic method `execute` knows `task` has `run()` and `close()` thanks to the two bounds. The try-with-resources block calls `close()` after the `try` body finishes. Because `AutoCloseable.close` is permitted to throw `Exception`, `execute` and `main` declare `throws Exception`.

Note that exceptions can occur at runtime in `run()`/`close()` with other implementations, though this demo program prints two deterministic lines and throws no error.

## 20. Common Compile Errors and Misconceptions

### Error 1: Placing an interface before a class bound

~~~java
// Invalid:
class Bad<T extends Comparable<T> & Number> {}
~~~

**Fix:** **class Good<T extends Number & Comparable<T>> {}**.

### Error 2: Declaring multiple class bounds

~~~java
// Invalid:
class Bad<T extends Number & Thread> {}
~~~

A type parameter can have at most one class bound, and the class bound must come first.

### Error 3: Using a comma instead of `&` to join multiple bounds of `T`

~~~java
// Invalid for the intended meaning:
// <T extends Number, Comparable<T>>
~~~

Commas separate type parameters. To give a single `T` two bounds, write **<T extends Number & Comparable<T>>**.

### Error 4: Using `implements` in a type bound

~~~java
// Invalid:
class Bad<T implements Runnable> {}
~~~

**Fix:** **class Good<T extends Runnable> {}**.

### Error 5: Assuming satisfying one bound is enough

~~~java
class Pair<T extends Number & Comparable<T>> {
    T value;
}
~~~

A subclass of `Number` that **does not** implement a matching `Comparable` cannot be used as `T`. Every type argument must satisfy **all** bounds.

### Error 6: Using a `final` class that does not satisfy an additional interface

~~~java
// Invalid:
class Bad<T extends String & Runnable> {}
~~~

`String` is final and does not implement `Runnable`. There is no way to subclass `String` to add `Runnable`.

### Error 7: Combining two `Comparable` paths with different type arguments

~~~java
// Invalid:
// <T extends Comparable<String> & Comparable<Integer>>
~~~

This is a conflict of the same generic interface with two different specializations.

### Error 8: Assuming differently named interfaces are always compatible

Two interfaces can declare the same method with conflicting return types, or inherit the same generic interface through incompatible type arguments. You must check **inheritance contracts, signatures, and erasure**, not just interface names.

### Error 9: Thinking a `Number` bound allows addition on `T`

~~~java
// Invalid:
static <T extends Number> T add(T a, T b) {
    // return a + b;
    return a;
}
~~~

The line is commented out because the arithmetic **+** operator is not defined on type variable `T`. The sample body only returns `a` so the code is valid if compiled; it does not perform addition. If you want to compute a sum as `double`, use **a.doubleValue() + b.doubleValue()** with return type `double` and accept precision limits.

### Error 10: Treating a bound as a non-null guarantee

A `T extends Number` can still be `null`. Calling `doubleValue()` when the receiver is `null` throws `NullPointerException`. Bounds check **static types**, and do not automatically force a **runtime value** to exist.

### Error 11: Thinking interface order can always be changed without consequence

When there is no class bound, the first interface determines the erasure of `T`. Changing the order can change erased descriptors, which is especially important in released libraries.

### Error 12: Interpreting `&` in a generic bound as a bitwise operator

Here **&** is an intersection-bound connector in a type declaration. It is different from the bitwise AND operator on integer values and boolean expressions.

### Error 13: Assuming an interface bound lets you write `new T()`

A bound allows accessing members declared by the bound; it **does not** guarantee a specific constructor or make **new T()** valid. When you need to create an object, pass `Supplier<? extends T>`, a factory, or a type token with an appropriate contract.

### Error 14: Using a lower bound with `super` in a type parameter declaration

~~~java
// Invalid:
// class Bad<T super Number> {}
~~~

The **super** keyword belongs to **lower-bounded wildcards** such as **List<? super Integer>**, not type parameter declarations. For type parameters, use **extends** for upper bounds.

## 21. API Design Guidelines with Multiple Bounds

Declaring multiple bounds is not always best. Start from the operations actually needed:

- If you only call **doubleValue()**, **<T extends Number>** is enough.
- If you need to call **compareTo(T)**, consider **<T extends Comparable<T>>** or the appropriate **Comparable<? super T>** variant.
- If you need both `doubleValue` and `compareTo`, **<T extends Number & Comparable<T>>** expresses the contract.
- If you need two independent behaviors, you can use **<T extends InterfaceA & InterfaceB>**.
- If ordering or behavior strategy varies by call site, sometimes **passing a `Comparator`, `Function`, or strategy object** is clearer and more flexible than forcing `T` to implement additional interfaces.
- If a class bound is too restrictive and prevents the API from accepting other useful types, consider redesigning around a shared interface or an adapter.

Example replacing a `Comparable` requirement with a `Comparator`:

~~~java
static <T extends Number> T greater(
        T first, T second,
        java.util.Comparator<? super T> comparator) {
    return comparator.compare(first, second) >= 0 ? first : second;
}
~~~

The method keeps `T extends Number`, while the comparison behavior is passed in. Callers can choose a comparator without forcing `T` itself to implement `Comparable<T>`. That is a design choice, not a way to "bypass" the compiler: the method signature still fully expresses the required data and behavior.

### Checklist before declaring multiple bounds

1. Is `T` one type parameter, or do you actually need multiple separate type parameters?
2. Are the bounds joined by **&** with only one **extends** after `T`?
3. If there is a class bound, is it first?
4. Did you accidentally put two class types in the list?
5. Do the interfaces share generic supertypes parameterized with different type arguments?
6. Are there method signatures/return types that cannot be implemented together?
7. Does a `final` class force an interface it does not implement?
8. Do expected type arguments such as `Integer`, `Double`, or custom classes satisfy all bounds?
9. Are the bounds redundant or making the API harder to use than necessary?
10. Will changing the order of interface bounds alter the erasure of an existing public API?

## 22. Self-Check Practice

**Question 1.** Why is **<T extends Number & Comparable<T>>** valid while **<T extends Comparable<T> & Number>** is not?

**Answer:** `Number` is a class bound, so it must come first in the list. `Comparable<T>` is an interface and can come afterward.

**Question 2.** Can you write **<T extends Runnable & AutoCloseable>** when there is no class bound?

**Answer:** Yes. These are two interface bounds; `T` must implement both.

**Question 3.** How many type parameters does **<A extends Number, B extends CharSequence>** have?

**Answer:** Two: `A` and `B`. The comma separates two declarations; it does not join multiple bounds of a single parameter.

**Question 4.** Can `String` be used with **<T extends Number & Comparable<T>>**?

**Answer:** No. `String` has `Comparable<String>`, but does not extend `Number`.

**Question 5.** Can a class that extends `Number` but does not implement `Comparable<?>` be used for `T` in Question 4?

**Answer:** No. It is missing the corresponding `Comparable<T>` bound.

**Question 6.** If **<T extends Runnable & AutoCloseable>**, does the compiler allow calling `run()` and `close()` on `T`?

**Answer:** Yes. However, `close()` per `AutoCloseable` can throw `Exception` and must be handled/declared properly.

**Question 7.** Why is **<T extends String & Runnable>** contradictory?

**Answer:** `String` is final and does not implement `Runnable`; there can be no other subtype of `String` to satisfy the interface.

**Question 8.** Can a type variable have two class bounds like `Number & Thread`?

**Answer:** No. Java allows at most one class bound, in the first position.

**Question 9.** Can two separate interfaces that inherit `Comparable<String>` and `Comparable<Integer>` be used together as bounds?

**Answer:** No. A single type argument cannot have the same generic superinterface `Comparable` with two different specializations.

**Question 10.** With **<T extends Serializable & Comparable<T>>**, what is the erasure of `T`?

**Answer:** `Serializable`, because it is the first bound. If `Comparable<T>` is moved first, the erasure is typically `Comparable`.

**Question 11.** With **<T extends Number & Comparable<T>>**, must `T` always be non-null?

**Answer:** No. Type bounds do not guarantee non-null; another runtime check or contract is needed.

**Question 12.** Is the bound **<T extends Comparable<T>>** a circular reference error because `T` appears twice?

**Answer:** No. This is a valid self-referential/F-bound form requiring `T` to have a comparison contract with `T`. It is not the same as an invalid cyclic bound like `T extends T`.

**Question 13.** Why shouldn't you reorder interfaces in a public generic API just to tidy it up?

**Answer:** The first bound determines erasure, which can affect JVM signatures and binary linking with already-compiled code.

**Question 14.** If you only need an optional comparison strategy for `Number`s, do you have to use **<T extends Number & Comparable<T>>**?

**Answer:** No. You can use **<T extends Number>** together with a passed-in `Comparator<? super T>`, if that is a better-fitting contract.

## 23. Summary

For multiple type bounds, Java uses the form **<T extends ClassBound & InterfaceA & InterfaceB>**. **A class bound, if present, must come first; subsequent bounds are interfaces.** The condition across bounds is **AND**, meaning a type argument must satisfy all of them.

The bounds must also be **type-system compatible**: they cannot require a `final` class to implement an interface it does not support, cannot inherit the same generic interface with conflicting type arguments, and cannot create method contracts that cannot be implemented together. In source code, the compiler allows calling members guaranteed by all bounds; in bytecode, **the first bound** determines the erasure of the type variable. Understanding both layers helps you write generics that are syntactically valid, type-safe, and stable when designing APIs with complex inheritance.