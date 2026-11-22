# Static Nested Classes and Independent Type Parameters in Java Generics

## 1. Objectives

In Java, a class can declare another class inside its body. If that member class uses the **static** keyword, it is called a **static nested class**. When the enclosing class is generic, it is crucial to understand the boundaries of **type variables**.

Example:

~~~java
class Outer<T> {
    static class Nested<U> {
        U value;
    }
}
~~~

Here:

- **T** is declared by **Outer<T>**.
- **U** is declared by **Nested<U>**.
- **Nested** is a member class with the **static** keyword, so it **does not inherit the scope of using T in Outer's static context**.
- **Nested<U>** is a generic class in the sense of having its own type parameter U, even though it is placed inside Outer.
- Outside, the nested type is written **Outer.Nested<String>**, **Outer.Nested<Integer>**, etc. There is no need to pick **Outer<String>** first to parameterize Nested.

Learning objectives:

1. Distinguish **static nested class** and **non-static inner class** regarding their relationship with an Outer instance and ability to use T.
2. Accurately identify the scopes of **T** and **U**, avoiding the assumption that an enclosing class's type parameter automatically passes into a static nested class.
3. Use the right declaration, instantiation, and reference syntax for **Outer.Nested<U>**.
4. Design generic methods inside a static nested class when needing to work with **Outer<T>**.
5. Handle multiple type parameters, generic bounds, static members inside nested classes, and the relationship with type erasure.
6. Recognize common mistakes: referencing T out of scope, using `Outer<String>.Nested<U>` syntax, confusing constructors with outer instances, and shadowing type variable names.

Examples with filenames are written for Java 17+; erroneous snippets are noted separately so they are not confused with runnable code.

## 2. Why Does `static` Create a Type Boundary?

Let's start with an ordinary generic class:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

T belongs to the **Box<T>** declaration. Instance members such as the `value` field, constructor, and `get()` can use T because they relate to a specific use of Box<T>, such as Box<String>.

A static member of Box<T> does not belong specifically to Box<String> or Box<Integer>. It belongs to **Box** at the class level. Therefore, you cannot write:

~~~java
// Illustrating compilation errors only:
class Box<T> {
    // static T lastValue;          // Wrong: static field cannot use T.
    // static T echo(T value) {     // Wrong: static method uses the class's T.
    //     return value;
    // }
}
~~~

A static nested class follows the same principle with respect to the enclosing class's type parameter. It is declared inside Outer for name organization, yet **is not automatically attached to an Outer<T> instance**.

~~~java
class Outer<T> {
    private T instanceValue;

    static class Nested {
        // T cached; // Wrong: cannot use Outer's T here.
    }
}
~~~

Placing Nested inside Outer's braces does not turn each Nested into a "separate subclass" for each Outer<T>. **Outer.Nested** is a static member type, independent of the type argument carried by any Outer instance.

The `static` keyword here does not mean "every field inside Nested must be static". Nested can still contain normal **instance fields**, constructors, and instance methods; it is the **member type declaration Nested** itself that is static relative to Outer.

## 3. A Static Nested Class Can Declare Its Own Type Parameters

Correct syntax:

~~~java
class Outer<T> {
    static class Nested<U> {
        private final U value;

        Nested(U value) {
            this.value = value;
        }

        U get() {
            return value;
        }
    }
}
~~~

**<U>** after Nested is an independent type parameter declaration; inside Nested<U>, U can be used as the `value` field type, constructor parameter, and `get()` return type. Meanwhile, Outer's T cannot be used directly inside Nested's body merely because it was declared outside.

Using the nested class:

~~~java
// Assuming the same package and Nested has no access restriction:
Outer.Nested<String> name = new Outer.Nested<>("Java");
Outer.Nested<Integer> count = new Outer.Nested<>(21);

String text = name.get();
Integer number = count.get();
~~~

Because Nested is declared static, we write **new Outer.Nested<>(...)**. There is no need to create an Outer instance first before instantiating Nested. The diamond **<>** infers U from context and constructor arguments; it is not a new type parameter list.

If U is replaced with T:

~~~java
class Outer<T> {
    static class Nested<T> {
        private T value;
    }
}
~~~

Then **Nested<T>'s T is a new type parameter**, independent of Outer<T>'s T. Within Nested's declaration, the new name T hides the identically named outer one, though in a static nested class using the outer type parameter would be invalid anyway. This syntax is valid yet **discouraged** because readers easily think both are the same T. Names like **U**, **E**, **K**, or **V** usually help clarify the two scopes.

## 4. Standalone Runnable Example: Outer<T> and Nested<U>

Save as **StaticNestedDemo.java**:

~~~java
public class StaticNestedDemo<T> {
    private final T outerValue;

    StaticNestedDemo(T outerValue) {
        this.outerValue = outerValue;
    }

    T getOuterValue() {
        return outerValue;
    }

    static final class Nested<U> {
        private final U item;

        Nested(U item) {
            this.item = item;
        }

        U get() {
            return item;
        }
    }

    public static void main(String[] args) {
        StaticNestedDemo<String> outer =
                new StaticNestedDemo<>("outer-data");

        StaticNestedDemo.Nested<Integer> count =
                new StaticNestedDemo.Nested<>(42);

        StaticNestedDemo.Nested<String> label =
                new StaticNestedDemo.Nested<>("nested-data");

        System.out.println(outer.getOuterValue());
        System.out.println(count.get());
        System.out.println(label.get());
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 StaticNestedDemo.java
java StaticNestedDemo
~~~

Exact stdout:

~~~text
outer-data
42
nested-data
~~~

Observe the three type choices:

- **StaticNestedDemo<String>** chooses String for Outer's T.
- **StaticNestedDemo.Nested<Integer>** chooses Integer for Nested's U.
- **StaticNestedDemo.Nested<String>** chooses String for U on another Nested instance.

There is no mandatory relationship between outer's **T = String** and count's **U = Integer**. They are type arguments on independent declarations. Code can create `count` and `label` without an outer; the program creates `outer` only to illustrate parallel existence.

Thanks to the return type **U get()**, the compiler knows `count.get()` is Integer and `label.get()` is String, requiring no manual casts.

## 5. Reference Syntax: Outer.Nested<U>, Not Outer<T>.Nested<U>

Given:

~~~java
class Outer<T> {
    static class Nested<U> {}
}
~~~

The syntax describing the nested class type at the use site is:

~~~java
// Illustrative usage inside a method:
Outer.Nested<String> a = new Outer.Nested<>();
Outer.Nested<Integer> b = new Outer.Nested<>();
~~~

**Outer.Nested<String>** means the member type Nested<String> declared inside Outer. The name Outer serves as the qualifier for the class containing the static member; there is no need to parameterize Outer first.

A common misconception:

~~~java
// Invalid, for illustration only:
// Outer<String>.Nested<Integer> value;
~~~

You cannot select a static member class from a parameterized Outer<String> form as you would with a non-static inner class. The **<String>** after Outer here has no role for Nested. The right form is **Outer.Nested<Integer>**.

The dot in **Outer.Nested** qualifies a class member, without implying an Outer object holding a reference to Nested. A static nested class can be imported by its qualified name or via an appropriate static import under Java's import rules; in study materials, writing the full form Outer.Nested<U> makes the declaration site easy to see.

If Nested is declared **private**, code outside Outer cannot directly use that type name even with valid generic syntax. Access modifiers such as public, protected, private, and package-private still apply normally; type variable scope and access control are two different rules.

## 6. Sufficient Comparison to Distinguish from Non-Static Inner Classes

A **non-static inner class** has an enclosing instance, so it can use `Outer<T>`'s `T`; a **static nested class** has no such implicit link. Consider a minimal example:

~~~java
class Outer<T> {
    private final T value;
    Outer(T value) { this.value = value; }

    class Inner<U> {
        U extra;
        Inner(U extra) { this.extra = extra; }
        T outerValue() { return value; }
    }

    static class Nested<U> {
        U extra;
        Nested(U extra) { this.extra = extra; }
    }
}
~~~

~~~java
Outer<String> owner = new Outer<>("parent");
Outer<String>.Inner<Integer> inner = owner.new Inner<>(5);
Outer.Nested<Integer> nested = new Outer.Nested<>(5);
~~~

The usage statements above must sit inside a method or valid variable declaration context. The result `inner.outerValue()` has type `String`; `nested` has no implicit outer object.

| Comparison point | Static nested | Non-static inner |
| --- | --- | --- |
| Reference type | `Outer.Nested<U>` | `Outer<T>.Inner<U>` |
| Implicit enclosing instance | No | Yes |
| Directly uses outer's `T` | No | Yes, when not shadowed |
| Instantiation from outside outer | `new Outer.Nested<>(...)` | `owner.new Inner<>(...)` |
| Its own instance fields | Yes | Yes |

This distinction is enough to identify the boundary of **outer's `T`**. Inner instantiation cases, `Outer.this`, lifecycles, and aliasing belong to the dedicated lesson on non-static inner classes; here we continue analyzing **generic APIs inside static nested types**.

## 7. Why Can't a Static Nested Class Use Outer's T in a Field?

Suppose we want to write:

~~~java
// Does not compile:
class Holder<T> {
    static class Entry {
        // T data;  // Error: non-static type variable T in static context
    }
}
~~~

If Entry could use T directly, the question would be: "Which T?". **Holder<String>.Entry** and **Holder<Integer>.Entry** are not two static member types parameterized by Holder. The T of a specific Holder<T> is not in usable scope inside the static Entry declaration.

Fixing according to intent:

**If Entry needs data of an arbitrary type, declare U itself:**

~~~java
class Holder<T> {
    static class Entry<U> {
        U data;

        Entry(U data) {
            this.data = data;
        }
    }
}
~~~

**If Entry must be tied to a specific Holder<T>, turn it into an inner class:**

~~~java
class Holder<T> {
    class Entry {
        T data;

        Entry(T data) {
            this.data = data;
        }
    }
}
~~~

**If you want Entry to stay static yet link types with another Holder, pass that relationship explicitly:**

~~~java
class Holder<T> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    static class Entry<U> {
        private final Holder<U> owner;

        Entry(Holder<U> owner) {
            this.owner = owner;
        }

        U read() {
            return owner.value;
        }
    }
}
~~~

In the final example, U belongs to Entry<U>. The field **Holder<U> owner** states clearly that owner must be a Holder carrying the exact same U, and `read()` returns U. There is no need to access the enclosing class's T from a static context; the type relationship is established via **Holder<U>** as an explicit parameterized type.

## 8. A Static Nested Class Can Have Its Own Generic Methods

A method's type parameter differs from the type parameter of the class containing the method.

~~~java
class Outer<T> {
    static class Nested<U> {
        private final U value;

        Nested(U value) {
            this.value = value;
        }

        U get() {
            return value;
        }

        static <X> X identity(X input) {
            return input;
        }
    }
}
~~~

Here:

- **T** of Outer<T> is not directly usable in Nested.
- **U** of Nested<U> is usable in instance fields and the instance method `get()`.
- **X** of the static generic method `identity` is **the method's own** type parameter, unrelated to T or U.

Even though Nested<U> is a generic class, a static method inside it **cannot use the class's U as an undeclared standalone type**:

~~~java
// Does not compile:
class Outer<T> {
    static class Nested<U> {
        // static U last;                 // Wrong: static field uses Nested's U.
        // static U echo(U input) {       // Wrong: static method uses Nested's U.
        //     return input;
        // }
    }
}
~~~

The right choice is **static <X> X echo(X input)**. When needing to return Nested<X> from a static factory:

~~~java
class Outer<T> {
    static final class Nested<U> {
        private final U value;

        private Nested(U value) {
            this.value = value;
        }

        static <X> Nested<X> of(X value) {
            return new Nested<>(value);
        }

        U get() {
            return value;
        }
    }
}
~~~

The factory **Nested.of("abc")** has type parameter X declared by **the `of` method itself**. When called from outside Outer, the qualified form is **Outer.Nested.of("abc")**. The method does not use U from a prior Nested instance; it creates a new Nested<X> instance.

In an ordinary generic class as well: **static <X> Box<X> of(X value)** is a generic static factory with an independent type parameter; it does not directly use Box<T>'s type parameter T.

## 9. Linking Outer<T> and Nested<U> via a Generic Method

Sometimes you want Nested to stay static to avoid an implicit dependency on an outer instance, yet still want to convert data from Outer<T> into Nested<T>. That relationship can be expressed via a **generic method** accepting Outer<X> and returning Nested<X>.

~~~java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    static final class Nested<U> {
        private final U item;

        private Nested(U item) {
            this.item = item;
        }

        U get() {
            return item;
        }

        static <X> Nested<X> fromOuter(Outer<X> outer) {
            return new Nested<>(outer.value);
        }
    }
}
~~~

The line **static <X> Nested<X> fromOuter(Outer<X> outer)** makes clear:

- **X** is a type parameter declared specifically for the static method.
- The `outer` parameter has type **Outer<X>**, so the field `outer.value` has type X in that context.
- The constructor receives X, creating **Nested<X>**.
- Callers need no cast from Object to X; the compiler checks the relationship through the method signature.

Example:

~~~java
// Illustrative usage inside a method:
Outer<String> source = new Outer<>("abc");
Outer.Nested<String> copy = Outer.Nested.fromOuter(source);
String result = copy.get();
~~~

A static nested class is allowed to access private members of the enclosing class through **an explicit outer reference** when Java access rules allow; nested classes belonging to the same nest scope can access corresponding private members. What matters is that **outer is passed in** rather than implicitly present.

### Runnable Example: Static Factory Preserving the Exact Type Parameter

Save as **NestedFactoryDemo.java**:

~~~java
public class NestedFactoryDemo<T> {
    private final T stored;

    NestedFactoryDemo(T stored) {
        this.stored = stored;
    }

    static final class Result<U> {
        private final U value;

        private Result(U value) {
            this.value = value;
        }

        U get() {
            return value;
        }

        static <X> Result<X> from(NestedFactoryDemo<X> source) {
            return new Result<>(source.stored);
        }

        static <X> Result<X> of(X value) {
            return new Result<>(value);
        }
    }

    public static void main(String[] args) {
        NestedFactoryDemo<String> text =
                new NestedFactoryDemo<>("hello");

        NestedFactoryDemo.Result<String> fromOuter =
                NestedFactoryDemo.Result.from(text);

        NestedFactoryDemo.Result<Integer> independent =
                NestedFactoryDemo.Result.of(99);

        System.out.println(fromOuter.get());
        System.out.println(independent.get());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 NestedFactoryDemo.java
java NestedFactoryDemo
~~~

Stdout:

~~~text
hello
99
~~~

**from(text)** infers X = String via the `NestedFactoryDemo<X>` parameter. Meanwhile **of(99)** infers X = Integer via the `int` argument boxed to Integer. Both factories live in the static nested `Result<U>`; X is not the U of any pre-existing Result instance.

## 10. Option to Use Multiple Independent Type Parameters

A static nested generic class can declare multiple type parameters:

~~~java
class Context<T> {
    static final class Entry<K, V> {
        private final K key;
        private final V value;

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
    }
}
~~~

Both **K and V** are declared separately on Entry; **T** of Context is not automatically linked to K or V.

In the same package:

~~~java
Context.Entry<String, Integer> entry =
        new Context.Entry<>("count", 5);

String name = entry.key();
Integer number = entry.value();
~~~

A static nested class can also use a type parameter like U to parameterize other generic types:

~~~java
class Library<T> {
    static class Group<U> {
        private final java.util.List<U> items =
                new java.util.ArrayList<>();

        void add(U item) {
            items.add(item);
        }

        java.util.List<U> snapshot() {
            return java.util.List.copyOf(items);
        }
    }
}
~~~

T in Library<T> is not directly used in Group<U>. Group<U> declares U, then uses U as the type argument for List<U>. **List.copyOf** does not accept null elements; that is a policy of List.copyOf, not a limitation specific to static nested classes.

There is no requirement that Outer and Nested have the same number of parameters. Outer<T> can contain Nested<U>, Nested<K,V>, or a non-generic static nested class depending on responsibility. Good design uses the exact number of type parameters needed to express real type relationships.

## 11. Type Bounds: Constraints on U Are Independent of Constraints on T

An enclosing class having a bound does not implicitly propagate that bound into a static nested class.

~~~java
class NumericOuter<T extends Number> {
    static class Holder<U> {
        private final U item;

        Holder(U item) {
            this.item = item;
        }

        U get() {
            return item;
        }
    }
}
~~~

**T extends Number** only constrains type arguments of NumericOuter<T>. It **does not constrain U** of NumericOuter.Holder<U>. Therefore:

~~~java
// Illustration:
NumericOuter.Holder<String> words =
        new NumericOuter.Holder<>("hello");
~~~

is valid; String does not need to be a Number to serve as U.

If the nested class itself needs to operate on Number, declare the bound directly on U:

~~~java
class NumericOuter<T extends Number> {
    static class NumericHolder<U extends Number> {
        private final U item;

        NumericHolder(U item) {
            this.item = item;
        }

        double asDouble() {
            return item.doubleValue();
        }
    }
}
~~~

**NumericOuter.NumericHolder<Integer>** is valid; **NumericOuter.NumericHolder<String>** is invalid. U is constrained because of the **U extends Number** declaration on Nested, not because of T extends Number on Outer.

You cannot reference Outer's T in the bound of a static nested class:

~~~java
// Does not compile:
class Outer<T> {
    // static class Nested<U extends T> {}
}
~~~

To express a relationship between U and another type, declare all needed type parameters on the nested class and place bounds between them:

~~~java
class Outer<T> {
    static class Related<X, Y extends X> {
        private final X parentValue;
        private final Y detail;

        Related(X parentValue, Y detail) {
            this.parentValue = parentValue;
            this.detail = detail;
        }
    }
}
~~~

X and Y are type parameters of Related; **Y extends X** is a valid bound relationship because both X and Y lie in the nested class's own scope. It still does not automatically link to Outer's T. Any relationship with a concrete Outer<X> must be established via an appropriate parameter, field, or method.

## 12. Static Fields of a Nested Class Remain Shared Across All `U`s

A `static nested class` can contain both an **instance field of type `U`** and a **static field of a concrete type**:

~~~java
class Outer<T> {
    static class Counter<U> {
        private static int created;
        private final U value;

        Counter(U value) {
            this.value = value;
            created++;
        }

        U get() { return value; }
        static int createdCount() { return created; }
    }
}
~~~

If you create one `Outer.Counter<String>` and one `Outer.Counter<Integer>`, each object holds its own `value` yet both increment the shared `Counter.created` field; the value returned by `Outer.Counter.createdCount()` is `2` if no other creations occurred. There is **no** separate counter automatically generated by Java per type argument `U`.

You cannot write `static U lastValue` inside `Counter<U>` because `U` belongs to the generic class, whereas a static field does not carry a per-instance `U`. With multiple threads, `created++` is non-atomic: use `AtomicInteger` or synchronization when accurate counting is needed. If per-type statistics are required, design a map with grouping keys yourself; type erasure does not create separate static state per parameterization.

The point to learn here is **two layers of static boundaries**: `Nested<U>` cannot borrow `T` from outer, and `Nested<U>`'s own static members cannot borrow `U` from nested instances either. Details on class loading, `Class<T>` as keys, and concurrency belong to a separate topic on shared static state.

## 13. Do Not Directly Use Outer Instance Members from Nested

A static nested class can still reference **static members** of Outer subject to access rights. It cannot read **instance members** of Outer without an outer reference.

~~~java
class Outer<T> {
    private static final String PREFIX = "item:";
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    static class Nested<U> {
        private final U item;

        Nested(U item) {
            this.item = item;
        }

        String describe() {
            return PREFIX + item; // Valid: PREFIX is static.
        }

        // T readOuter() { return value; } // Wrong: T and instance value are not automatically available.
    }
}
~~~

To read an outer value inside Nested, pass an Outer<X>:

~~~java
class Outer<T> {
    private final T value;

    Outer(T value) {
        this.value = value;
    }

    static class Nested<U> {
        static <X> X read(Outer<X> outer) {
            return outer.value;
        }
    }
}
~~~

Here **X** is the type parameter of the `read` method, not Outer's T or Nested's U. It binds to the type of the passed-in Outer<X>. No implicit outer reference is created.

One confusion to avoid is assuming that because a nested class has access to Outer's private members, it can invoke instance members without an instance. **Access control** and **having a receiver/type variable in the right scope** are two independent issues.

## 14. Nested Classes Inside Interfaces and Records

Certain nested type declarations in Java are implicitly static under language rules even without writing the `static` keyword.

### Class Declared Inside an Interface

~~~java
interface Source<T> {
    T read();

    class Metadata<U> {
        private final U information;

        public Metadata(U information) {
            this.information = information;
        }

        public U information() {
            return information;
        }
    }
}
~~~

The member class Metadata inside an interface is treated as **public static** (per the implicit rule for interface member types). It cannot directly use `Source<T>`'s type parameter T; hence it declares its own U.

Example usage:

~~~java
Source.Metadata<String> metadata =
        new Source.Metadata<>("details");
~~~

Do not write **Source<String>.Metadata<String>** to pick a type for Source's T, because Metadata is not tied to a Source<String> instance.

### Member Record Nested Inside a Generic Class

Since Java 16, a record is a data structure with components and generated methods. A member record is implicitly static, so it declares its own type parameter if needed:

~~~java
class Container<T> {
    record Entry<U>(U value) {}
}
~~~

The valid type at the use site is **Container.Entry<Integer>**. Container<T>'s T cannot be used directly in Entry's component; U belongs to the `record Entry<U>` declaration.

What it shares with static nested classes is the scope boundary on outer's type variable. If a record needs to wrap a value of type T from a specific Container<T>, you can create a generic factory accepting Container<X> and returning Entry<X>, or pass the data into Entry<X>'s constructor as a parameter.

## 15. Type Erasure and Identity of a Static Nested Generic Class

Generics in Java are primarily a compile-time type-checking construct. Creating objects:

~~~java
Outer.Nested<String> words = new Outer.Nested<>("A");
Outer.Nested<Integer> counts = new Outer.Nested<>(1);
~~~

does not create two different runtime classes for String and Integer. Normally both objects have the same runtime Class `Outer.Nested`, with type argument information already checked in source code.

For a static nested class, the bytecode name typically has the form **Outer$Nested.class**. This is the class name generated by javac when compiling a member nested class; the **$** sign in the class file is not the separator used in Java source syntax. In Java source, the reference is **Outer.Nested<U>**.

Using reflection, the runtime can read generic metadata of the nested class **declaration** (such as the type parameter name U). However, you cannot conclude that calling `getClass()` on an arbitrary object will reveal the full type argument U of the variable pointing to that object. To check whether runtime data is String or Integer, you need appropriate checking info/values, such as a separately passed `Class<U>` or a dedicated type token mechanism.

Do not use **new U()**, **U.class**, or **new U[10]** inside Nested<U> as if U were a concrete runtime class. The fundamental limits of type erasure apply to U just like other type variables.

## 16. Common Mistakes and How to Fix Them

### Mistake 1: Using Outer's T in a Static Nested Class

~~~java
// Intentionally wrong:
class Outer<T> {
    static class Nested {
        // T item; // Error: cannot reference T from static context.
    }
}
~~~

**Fix:** Have Nested declare **<U>** itself, or remove `static` if an inner class attached to Outer<T> is genuinely needed. If passing data once is needed, put it in a constructor or generic factory.

### Mistake 2: Using Outer<String>.Nested<Integer>

~~~java
class Outer<T> {
    static class Nested<U> {}
}

// Intentionally wrong:
// Outer<String>.Nested<Integer> entry;
~~~

**Fix:** **Outer.Nested<Integer> entry;**. A static nested class has no outer instance type argument T.

### Mistake 3: Instantiating a Static Nested Class via outer.new

~~~java
class Outer<T> {
    static class Nested<U> {}
}

// Invalid:
// Outer<String> owner = new Outer<>();
// var n = owner.new Nested<String>();
~~~

**Fix:** **new Outer.Nested<String>()** or **new Outer.Nested<>()** when the compiler can infer U. The syntax **owner.new Inner<>(...)** is only suitable for non-static inner classes.

### Mistake 4: Using Nested's U in a Static Method

~~~java
class Outer<T> {
    static class Nested<U> {
        // static U copy(U value) { return value; }
    }
}
~~~

**Fix:** **static <X> X copy(X value)** or use an instance method allowed to use U.

### Mistake 5: Keeping the Same Name T and Assuming Two Type Variables Are Linked

~~~java
class Outer<T> {
    static class Nested<T> {
        T item;
    }
}
~~~

T inside Nested<T> is **a new declaration**. Even though it uses the same symbol T, Nested<T> has no type relationship with Outer<T>. **Fix:** use **Nested<U>** for clarity or design a field **Outer<U> owner** if a relationship is genuinely needed.

### Mistake 6: Mistaking Outer's Upper Bound for Nested's Bound

~~~java
class Outer<T extends Number> {
    static class Nested<U> {}
}
~~~

**Outer.Nested<String>** can still be valid. If U must be a Number, write **static class Nested<U extends Number>** explicitly.

### Mistake 7: Referencing Outer's Instance Field Without an Object

~~~java
class Outer<T> {
    private T value;

    static class Nested<U> {
        // Object read() { return value; } // Wrong, missing outer instance.
    }
}
~~~

**Fix:** accept an **Outer<X> outer** as a parameter in a generic method or store an appropriate `Outer<U>` reference in the nested object.

### Mistake 8: Believing a Static Nested Class Has No Instance State

~~~java
class Outer<T> {
    static class Nested<U> {
        private U value; // Completely valid.
    }
}
~~~

The `static` keyword at the member class level only defines the relationship with the enclosing class. Nested is still a normal class with objects, constructors, instance fields, and instance methods.

### Mistake 9: Believing a Static Field Splits by Type Argument U

~~~java
class Outer<T> {
    static class Nested<U> {
        static int count;
    }
}
~~~

Both Nested<String> and Nested<Integer> share the static field `count`. If per-runtime-type data is needed, design a separate identification mechanism and map; do not rely on U after erasure.

### Mistake 10: Using Object and Casting to Bypass the Boundary

~~~java
// Type-unsafe design, for illustration:
class Outer<T> {
    static class Nested {
        Object data;
    }
}
~~~

When callers receive Object and cast manually, type safety drops. If nested holds specifically typed data, prefer **Nested<U>**, **U get()**, a generic factory, or **Outer<U> owner** so the compiler checks the relationship.

### Mistake 11: Treating Static Nested as a Subclass of Outer

**Outer.Nested<U>** does not automatically extend Outer<T>; it is merely declared inside Outer. Subtyping relationships only arise when Nested explicitly has **extends SomeClass** or **implements SomeInterface**. Access rights between nested classes are not equivalent to inheritance.

### Mistake 12: Instantiating an Inner Class While Forgetting Outer's Type Arguments

For an inner class using Outer's T, the external type name is **Outer<String>.Inner<Integer>**, created via **outer.new Inner<>(...)**. Using raw Outer or arbitrarily dropping type information can trigger warnings or lose type precision. When an outer reference is needed, declare the outer variable with its full parameterized type.

## 17. Choosing Between Static Nested Class and Inner Class

Neither choice is universally better. Examine the real relationship:

- **Choose a static nested class** when the data type/helper organizationally belongs to Outer yet each instance needs no implicit outer instance. Its type parameters should be declared separately, such as **Outer.Entry<K,V>** or **Outer.Result<U>**.
- **Choose a non-static inner class** when each inner instance needs to access instance state of a specific Outer<T> and that link is intrinsic to the model. Then outer's T can be used directly and the external type name is **Outer<T>.Inner<U>**.
- **Choose a static nested class + explicit Outer<U> reference** if you want the relationship expressed clearly in a field/constructor, control the lifecycle, and avoid an automatic enclosing-instance reference.
- **Choose a top-level class** if the type does not genuinely have an organizational or API tie to Outer; nesting classes is not a prerequisite for generics.
- **Choose a generic method inside the nested class** when the type link is only needed for one operation, such as **static <X> Nested<X> from(Outer<X> source)**; there is no need to force every Nested instance to carry the same outer object.

When designing APIs, check whether the type name appearing at use sites is easy to understand. **Outer.Nested<U>** helps group related types; yet if nesting grows too deep, generic signatures can become harder to read than a clearly named top-level type.

## 18. Self-Check Practice

**Question 1.** In **class Outer<T> { static class Nested<U> {} }**, do T and U share the same scope?

**Answer:** No. T belongs to Outer<T>, and U belongs to Nested<U>. A static nested class cannot automatically use outer's T in its body; U is used in Nested's instance members.

**Question 2.** Can you declare a variable **Outer<String>.Nested<Integer> v**?

**Answer:** No. For a static nested class, write **Outer.Nested<Integer> v**. Outer<String>'s type argument String plays no role on this static member type.

**Question 3.** Is an Outer instance required before calling **new Outer.Nested<String>()**?

**Answer:** No. A static nested class has no implicit enclosing instance, so it can be instantiated via the type name Outer.Nested.

**Question 4.** Why can **static class Nested<T>** inside Outer<T> still use the symbol T?

**Answer:** Because Nested declares **a new type parameter T** of its own. It is independent of the T declared by Outer, despite having the same letter name.

**Question 5.** If you want Nested to use T of a specific Outer<String> and carry an implicit outer reference, which class kind should you choose?

**Answer:** A **non-static inner class**, such as **class Inner<U>** inside Outer<T>. Use the type **Outer<String>.Inner<Integer>** and instantiate with **outer.new Inner<>(...)**.

**Question 6.** If a static nested class needs to read a value from an Outer<T> without being implicitly attached to an outer instance, what should you do?

**Answer:** Pass an **Outer<X>** into a constructor or generic method, use X as a local type parameter of the nested class/method, and declare the exact type relationship.

**Question 7.** Inside **static class Nested<U>**, can you write **static U get(U input)**?

**Answer:** No, because U belongs to the generic class and is unavailable from a static context. Write **static <X> X get(X input)** if the method needs independent generics.

**Question 8.** Does `Outer<T extends Number>` force `Nested<U>` to accept only `U extends Number`?

**Answer:** No. U is independent. To constrain it, explicitly write **static class Nested<U extends Number>**.

**Question 9.** Does Nested<U>'s static field **count** have one copy for Nested<String> and another copy for Nested<Integer>?

**Answer:** No. Uses with different type arguments share the static state of the same nested runtime class.

**Question 10.** Why can **Outer.Nested<String>** and **Outer.Nested<Integer>** use the same runtime class?

**Answer:** Java generics use type erasure; the compiler checks type arguments in source code without generating distinct runtime classes for each U.

**Question 11.** Is a nested class located inside a generic interface implicitly static?

**Answer:** Yes. A member class in an interface is public static, so it does not automatically inherit the enclosing interface's type variable; it must declare its own type parameter or receive types via a method/constructor.

**Question 12.** Can a member record declared inside Outer<T> directly use T as a record component type?

**Answer:** No. A member record is static; if flexible component types are desired, declare **record Entry<U>(U value)** and use Outer.Entry<U>.

## 19. Checklist When Reading or Writing Code

1. **Check the `static` keyword.** Is the member type **static class Nested** or **class Inner**?
2. **Identify the owner of each type variable.** T belongs to Outer, U belongs to Nested, X belongs to a generic method.
3. **Verify the type name used externally.** Static: **Outer.Nested<U>**. Inner: **Outer<T>.Inner<U>**.
4. **Verify instantiation syntax.** Static: **new Outer.Nested<>(...)**. Inner: **outer.new Inner<>(...)**.
5. **Check outer data sources.** If Nested needs instance members of Outer, is there an explicit outer reference?
6. **Check static members inside Nested<U>.** They cannot use Nested's U as a type variable in a static context.
7. **Check bounds.** Constraints on outer's T do not automatically apply to nested's U.
8. **Check design after erasure.** Do not expect static state or runtime classes to be split per type argument.
9. **Check access modifiers.** A private static nested class cannot be used directly from outside the declaring class even with valid generic syntax.
10. **Prefer explicit types.** If a link to Outer<T> is needed, express it in a method signature or a field of type Outer<U>, avoiding raw types and unchecked casts.

## 20. Conclusion

**A static nested class can be generic, yet its type parameters are independent of the generic outer class.** With **class Outer<T> { static class Nested<U> {} }**, T belongs to Outer while U belongs to Nested. The usage syntax is **Outer.Nested<U>** and it can be instantiated with **new Outer.Nested<>(...)** without needing an Outer instance.

When you genuinely need to bind to the same type as a specific Outer<T>, choose a **non-static inner class** or introduce the relationship explicitly via **Outer<X>** and a generic method/constructor. Properly understanding this static boundary helps avoid scope errors, maintain type safety, and design clear nested APIs in Java.
