# Limitations on Creating `new T()`, Generic Arrays, and Runtime Type Checks — Java 17+

A generic type parameter such as `T` helps the compiler check types, but **does not behave like a concrete class that can be instantiated or fully checked at runtime**. In Java 17, generics primarily use **type erasure**; therefore, three groups of limitations are closely related:

1. You cannot directly write `new T()`, `T.class`, or `new T[n]`.
2. You cannot create most arrays with a **non-reifiable component type**, for example `new List<String>[10]`.
3. You cannot require the runtime to check the exact erased type argument, for example `obj instanceof List<String>` when `obj` has type Object.

Minimal example of a generic class:

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    // T value2 = new T();           // Compilation error.
    // T[] values = new T[10];       // Compilation error.
    // boolean test(Object x) {
    //     return x instanceof T;    // Compilation error.
    // }
}
~~~

However, Java **provides type-safe alternatives**: passing a value or a `Supplier<? extends T>` factory, passing `Class<T>` to create an object/array via reflection when appropriate, passing an `IntFunction<T[]>` array factory, or using `List<T>` and collection APIs instead of generic arrays.

This is a standalone knowledge README belonging to **Java Core — Class & Object / Generic Classes**, focusing on the topic **“Limitations on Creating new T(), Generic Arrays, and Runtime Type Checks”**. Complete programs use **Java 17+**, with filenames, `javac --release 17`, `java` commands, and expected stdout. Intentionally invalid code is commented out and analyzed separately, not mixed with runnable examples.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain why `new T()` is invalid even if `T` is bounded by a class.
- Distinguish **compile-time type parameter** from **runtime class identity**.
- Understand **type erasure** and the erasure of an unbounded or bounded `T`.
- Design `Supplier<? extends T>`, `Factory<T>`, and `Class<T>` to create objects.
- Understand the limitations of public/no-argument constructors and checked exceptions in reflection.
- Distinguish `T.class` from a `Class<T>` token that can be passed by the caller.
- Understand why you cannot create `new T[n]` or `new List<String>[n]`.
- Distinguish **reifiable** and **non-reifiable** types.
- Recognize how `String[]`, `List<?>[]`, and `List<String>[]` differ.
- Understand **array covariance** and runtime `ArrayStoreException`.
- Understand **generic invariance** and the limitations of type checks after erasure.
- Build `T[]` using an `IntFunction<T[]>` array factory when an array with the exact runtime component type is truly needed.
- Know how to use `Array.newInstance(Class<T>, size)`, and the type-guarantee limitations of this approach.
- Understand why casting `Object[]` to `T[]` easily causes problems.
- Identify **heap pollution**, raw types, and unchecked warnings.
- Identify the risks of generic varargs and use `@SafeVarargs` in the appropriate context.
- Use `List<T>` to avoid many of the problems of generic arrays.
- Know why `instanceof T` and `instanceof List<String>` are invalid when a runtime test for a non-reifiable type is needed.
- Use `instanceof List<?>`, `Class.isInstance`, and `Class.cast` for their intended purposes.
- Understand that a simple `Class<T>` type token cannot fully describe `List<String>`.
- Distinguish `Type`, `ParameterizedType`, and type reference libraries.
- Use bounds/wildcards without wrongly inferring runtime checking capabilities.
- Avoid passing incorrect assertions into production via casts/suppress warnings.
- Write tests demonstrating compile-time errors, `ClassCastException`, and `ArrayStoreException`.
- Design generic APIs properly according to requirements for object creation, holding collections, data checking, and metadata.

## 2. Root Cause: Compile-Time Generics Differ from Runtime Representation

Suppose:

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

At the usage site:

~~~java
Box<String> text = new Box<>("Java");
String s = text.get();
~~~

The compiler relies on `Box<String>` to check that `get()` returns String at the source-level. However, at runtime there is usually no separate `Box<String>` class distinct from the `Box<Integer>` class. Both instantiations use the **same class declaration** `Box`.

For `T` **without a bound**, the erasure of T is Object. At the bytecode-level, places using T can be represented as Object; the compiler inserts casts when needed to preserve the behavior of typed callers.

For `T extends Number`, the erasure of T is the appropriate bound, usually Number. Erasure does **not** mean Java does not check types; on the contrary, the compiler performs many checks before execution.

## 3. Runnable Program: `Box<String>` and `Box<Integer>` Share the Same Class Object

Create **`ErasureClassDemo.java`**:

~~~java
public class ErasureClassDemo {
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
        Box<String> first = new Box<>("Java");
        Box<Integer> second = new Box<>(17);

        System.out.println("same class=" +
                (first.getClass() == second.getClass()));
        System.out.println("text=" + first.get());
        System.out.println("number=" + second.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ErasureClassDemo.java
java ErasureClassDemo
~~~

Stdout:

~~~text
same class=true
text=Java
number=17
~~~

**Conclusion:** The type arguments String and Integer carry great meaning at compile time, but they do not produce two independent runtime Class objects.

## 4. Why Is `new T()` a Compilation Error?

You might write:

~~~java
class Box<T> {
    // T create() {
    //     return new T(); // Invalid.
    // }
}
~~~

`T` is a **type variable**, not the name of a concrete class for which the compiler can emit bytecode calling the appropriate constructor.

The issues include:

- Runtime erasure does not determine the actual class of T from an ordinary generic method.
- There is no promise that every type argument has a **public no-arg constructor**.
- T can be an interface, an abstract class, or a class that cannot be directly instantiated.
- The constructor might have parameters, restricted accessibility, or throw checked exceptions.
- `T extends SomeBase` only indicates a subtype relation and accessible inherited APIs; it does **not** indicate which constructor to call.
- Java generics do not have a C#-style constructor constraint such as `where T : new()`.

For example, `class Maker<T extends Number>` still cannot write `new T()`. If you know specifically that you want `new Integer(...)`, that is the constructor or factory of a concrete type, not an operation on an arbitrary T.

## 5. Simplest Approach: Let the Caller Pass an Already Created Object

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

The caller is responsible for creating/providing the object:

~~~java
Box<StringBuilder> box =
        new Box<>(new StringBuilder("Java"));
~~~

Advantages:
- no reflection needed;
- supports arbitrary constructors at the caller;
- the compiler checks the type argument;
- code is easy to test because dependencies/value creation are explicit.

Disadvantages:
- Box cannot proactively create another T on its own if that behavior is a business requirement.

If Box needs to create a new instance when calling a method, pass a factory or supplier.

## 6. Runnable Program: Passing an Object into a Generic Constructor

Create **`PassedValueDemo.java`**:

~~~java
public class PassedValueDemo {
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
        StringBuilder created = new StringBuilder("Java");
        Box<StringBuilder> box = new Box<>(created);

        System.out.println(box.get());
        System.out.println("same reference=" +
                (box.get() == created));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 PassedValueDemo.java
java PassedValueDemo
~~~

Stdout:

~~~text
Java
same reference=true
~~~

Box does not clone StringBuilder. That is normal reference semantics; **type safety does not imply deep immutability**.

## 7. Recommended Approach for Creating New Instances: `Supplier<? extends T>`

`java.util.function.Supplier<T>` is a functional interface with a `T get()` method. The caller passes a lambda or method reference to specify **how to create the object**:

~~~java
class Maker<T> {
    private final java.util.function.Supplier<? extends T> factory;

    Maker(java.util.function.Supplier<? extends T> factory) {
        this.factory = java.util.Objects.requireNonNull(factory);
    }

    T create() {
        return factory.get();
    }
}
~~~

Example:

~~~java
Maker<StringBuilder> maker =
        new Maker<>(StringBuilder::new);
StringBuilder value = maker.create();
~~~

`StringBuilder::new` specifies the actual constructor, so there is no `new T()`.

### Why `? extends T`?

A factory can create a subtype of T. For example, when T is CharSequence, a Supplier<StringBuilder> can also be a suitable producer. If the API does not need that flexibility, `Supplier<T>` is still a valid signature.

## 8. Runnable Program: Factory Creating an Object Each Time

Create **`SupplierFactoryDemo.java`**:

~~~java
import java.util.Objects;
import java.util.function.Supplier;

public class SupplierFactoryDemo {
    static final class Maker<T> {
        private final Supplier<? extends T> factory;

        Maker(Supplier<? extends T> factory) {
            this.factory = Objects.requireNonNull(factory);
        }

        T create() {
            return factory.get();
        }
    }

    public static void main(String[] args) {
        Maker<StringBuilder> maker =
                new Maker<>(StringBuilder::new);

        StringBuilder one = maker.create();
        StringBuilder two = maker.create();

        one.append("Java");
        two.append("Core");

        System.out.println(one);
        System.out.println(two);
        System.out.println("same reference=" + (one == two));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SupplierFactoryDemo.java
java SupplierFactoryDemo
~~~

Stdout:

~~~text
Java
Core
same reference=false
~~~

Each call to the Supplier in the example creates a new StringBuilder. However, **a Supplier is not required to always create a new object**; the caller can pass a supplier returning a singleton, so document the contract if a fresh instance is needed.

## 9. Constructors Requiring Arguments: Using a Factory Lambda

A caller-provided factory can capture or receive arguments:

~~~java
Maker<StringBuilder> maker =
        new Maker<>(() -> new StringBuilder("initial"));
~~~

If inputs differ on each call, use `Function<A,T>` instead of Supplier:

~~~java
static <A, T> T create(
        A argument,
        java.util.function.Function<? super A, ? extends T> factory) {
    return factory.apply(argument);
}
~~~

For example, `create("Java", StringBuilder::new)`.

### Benefits

- Does not assume a no-arg constructor.
- Type inference checks the source/target relationship.
- Does not have to convert checked reflection exceptions into unchecked ones.
- The factory can create an immutable value, record, class, or proxy according to policy.
- Tests can provide a fake factory.

## 10. Runnable Program: Function as a Constructor Factory

Create **`ParameterizedFactoryDemo.java`**:

~~~java
import java.util.function.Function;

public class ParameterizedFactoryDemo {
    static <A, T> T create(
            A argument,
            Function<? super A, ? extends T> factory) {
        return factory.apply(argument);
    }

    public static void main(String[] args) {
        StringBuilder builder =
                create("Java", StringBuilder::new);

        System.out.println(builder);
        System.out.println(builder.length());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ParameterizedFactoryDemo.java
java ParameterizedFactoryDemo
~~~

Stdout:

~~~text
Java
4
~~~

`StringBuilder::new` here is a constructor reference matching a String input; compile-time type checking is still applied.

## 11. `Class<T>`: Runtime Type Token

If you truly need to know the runtime class of T, **require the caller to pass a token**:

~~~java
class TypedBox<T> {
    private final Class<T> type;

    TypedBox(Class<T> type) {
        this.type = java.util.Objects.requireNonNull(type);
    }
}
~~~

Caller:

~~~java
TypedBox<String> text = new TypedBox<>(String.class);
TypedBox<Integer> numbers = new TypedBox<>(Integer.class);
~~~

This token is a `Class<T>` object with the specific runtime class information of a **reifiable class** chosen by the caller.

It solves several problems:
- runtime `type.isInstance(obj)`;
- runtime cast `type.cast(obj)`;
- creating objects/arrays by class via reflection;
- logging/validating the class name.

However, `Class<T>` **cannot by itself fully represent `List<String>`**. `List.class` exists; `List<String>.class` is not valid syntax.

## 12. `Class<T>` and Reflection Object Creation

One alternative to `new T()` is:

~~~java
T create() throws ReflectiveOperationException {
    return type.getDeclaredConstructor().newInstance();
}
~~~

It requires a matching no-argument constructor; reflection must also satisfy accessibility/module rules. The method can throw:
- `NoSuchMethodException` if the constructor does not exist;
- `InstantiationException` if the type cannot be instantiated;
- `IllegalAccessException` due to access restrictions;
- `InvocationTargetException` if the constructor body throws an exception.

`ReflectiveOperationException` is the common checked superclass for many reflection errors.

**Do not use** `Class.newInstance()` for new code: that API is deprecated, and constructor invocation via `getDeclaredConstructor().newInstance()` or `getConstructor().newInstance()` expresses it better.

## 13. Runnable Program: Creating via `Class<T>`

Create **`ReflectionFactoryDemo.java`**:

~~~java
import java.lang.reflect.ReflectiveOperationException;
~~~

The import snippet above is **intentionally not runnable code** because `ReflectiveOperationException` belongs to `java.lang`, not `java.lang.reflect`. The full correct program below does not have that wrong import.

Create the exact contents of the file **`ReflectionFactoryDemo.java`**:

~~~java
public class ReflectionFactoryDemo {
    static final class Maker<T> {
        private final Class<T> type;

        Maker(Class<T> type) {
            this.type = java.util.Objects.requireNonNull(type);
        }

        T create() throws ReflectiveOperationException {
            return type.getDeclaredConstructor().newInstance();
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Maker<StringBuilder> maker =
                new Maker<>(StringBuilder.class);

        StringBuilder value = maker.create();
        value.append("Java");

        System.out.println(value);
        System.out.println(value.getClass().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReflectionFactoryDemo.java
java ReflectionFactoryDemo
~~~

Stdout:

~~~text
Java
StringBuilder
~~~

The example runs because `StringBuilder` has a public no-arg constructor. In common APIs, **Supplier** is usually simpler, easier to test, and less coupled to reflection.

## 14. Why Does a Bound Not Make `new T()` Valid?

~~~java
abstract class Shape {}

class ShapeBox<T extends Shape> {
    // T create() { return new T(); } // Still invalid.
}
~~~

Even though the compiler knows T is a subclass of Shape:
- the actual concrete subtype could be Circle, Rectangle, etc.;
- Shape can be abstract;
- there is no contract guaranteeing that every subclass has the same constructor signature;
- constructors are not inherited like instance methods.

The bound `T extends Shape` is used to **access APIs available on Shape**, not to “discover constructors”.

If you know you need some Shape via a factory, use `Supplier<? extends T>` or an abstract factory interface, as above.

## 15. Runnable Program: Bounded T and Supplier

Create **`BoundedSupplierDemo.java`**:

~~~java
import java.util.function.Supplier;

public class BoundedSupplierDemo {
    static abstract class Shape {
        abstract int sides();
    }

    static final class Triangle extends Shape {
        @Override
        int sides() {
            return 3;
        }
    }

    static final class Maker<T extends Shape> {
        private final Supplier<? extends T> factory;

        Maker(Supplier<? extends T> factory) {
            this.factory = factory;
        }

        T create() {
            return factory.get();
        }
    }

    public static void main(String[] args) {
        Maker<Triangle> maker = new Maker<>(Triangle::new);
        Triangle triangle = maker.create();

        System.out.println(triangle.sides());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoundedSupplierDemo.java
java BoundedSupplierDemo
~~~

Stdout:

~~~text
3
~~~

The bound guarantees that the returned T has the `sides()` method; the Supplier decides the actual constructor.

## 16. There Is No `T.class`

In generic code:

~~~java
class Inspector<T> {
    // Class<T> type() { return T.class; } // Compile error.
}
~~~

A class literal must be a type that can be represented by the appropriate class literal syntax, for example `String.class`, `int.class`, `String[].class`, or `List.class`. The type variable `T` is not a concrete class literal expression.

Similarly:

~~~java
// Class<List<String>> t = List<String>.class; // Invalid.
~~~

Instead:
- accept `Class<T> type` from the caller;
- accept `java.lang.reflect.Type`/a type descriptor if you need to represent a parameterized type;
- or do not use runtime type inspection if a compile-time API is already sufficient.

## 17. Arrays in Java Have a Runtime Component Type

Arrays differ from generic collections in how Java checks types:

~~~java
String[] words = new String[2];
words[0] = "Java";
~~~

The runtime knows the `String` component type of the array object. Therefore, the code:

~~~java
Object[] objects = words;
objects[0] = Integer.valueOf(17);
~~~

**Compiles**, because arrays are **covariant**: String[] is a subtype of Object[]. However, the assignment into the actual String[] array is rejected by the runtime with an `ArrayStoreException`.

This is a type of runtime check that erased generic type arguments cannot similarly provide.

## 18. Runnable Program: `ArrayStoreException`

Create **`ArrayCovarianceDemo.java`**:

~~~java
public class ArrayCovarianceDemo {
    public static void main(String[] args) {
        String[] names = {"Mai", "An"};
        Object[] objects = names;

        System.out.println("before=" + names[0]);

        try {
            objects[0] = Integer.valueOf(17);
        } catch (ArrayStoreException ex) {
            System.out.println("wrong array element type");
        }

        System.out.println("after=" + names[0]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ArrayCovarianceDemo.java
java ArrayCovarianceDemo
~~~

Stdout:

~~~text
before=Mai
wrong array element type
after=Mai
~~~

The runtime array component check protects String[] from storing an Integer, even when the reference is viewed as Object[].

## 19. Why Is `new T[n]` Not Allowed?

In a generic class:

~~~java
class Store<T> {
    // T[] items = new T[10]; // Compile error: generic array creation.
}
~~~

If the compiler allowed it, what would the runtime array component class be? With `Store<String>` it might need String[], with `Store<Integer>` it might need Integer[], yet T is erased.

Arrays have runtime element-type checks, whereas generic T does not provide a concrete runtime component class. Therefore, Java forbids creating an array directly with the type variable T.

**Do not confuse:** You can declare a field/parameter of type `T[]`; what is restricted is **creating a new array with `T`**.

~~~java
class Store<T> {
    private T[] items; // Valid type declaration.
}
~~~

If the caller passes an existing T[] or a factory provides an appropriate array, you can store the reference in a type-safe manner.

## 20. Safe Approach: Caller Passes an Existing Array

~~~java
class ArrayBox<T> {
    private final T[] values;

    ArrayBox(T[] values) {
        this.values = values;
    }
}
~~~

The caller creates a concrete array:

~~~java
ArrayBox<String> words =
        new ArrayBox<>(new String[]{"A", "B"});
~~~

**However,** storing the array reference directly causes aliasing: the caller can modify the array; a getter that returns the array directly also exposes mutable state. If you want a snapshot, clone both input and output.

Note that `T[]#clone()` has the same array class as its runtime result, and array cloning is **shallow** for reference elements.

## 21. Runnable Program: Accepting T[] and Two-Way Copying

Create **`InputArrayBoxDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;

public class InputArrayBoxDemo {
    static final class ArrayBox<T> {
        private final T[] values;

        ArrayBox(T[] input) {
            values = Objects.requireNonNull(input, "input").clone();
        }

        T[] copyValues() {
            return values.clone();
        }

        T at(int index) {
            return values[index];
        }
    }

    public static void main(String[] args) {
        String[] source = {"A", "B"};
        ArrayBox<String> box = new ArrayBox<>(source);

        source[0] = "X";
        String[] out = box.copyValues();
        out[1] = "Y";

        System.out.println("source=" + Arrays.toString(source));
        System.out.println("snapshot=" +
                Arrays.toString(box.copyValues()));
        System.out.println("first=" + box.at(0));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InputArrayBoxDemo.java
java InputArrayBoxDemo
~~~

Stdout:

~~~text
source=[X, B]
snapshot=[A, B]
first=A
~~~

Array cloning helps avoid structural aliasing between input/output and the internal array, though if the elements are mutable objects, they can still be shared.

## 22. Why Is `new List<String>[n]` Not Allowed?

The type `List<String>` is **non-reifiable**: the runtime does not fully retain the String argument to verify whether an arbitrary List is actually a `List<String>`.

Therefore:

~~~java
// List<String>[] lists = new List<String>[3]; // Compile error.
~~~

If Java allowed creating an actual array with runtime component type “List<String>”, the runtime would have to check the generic type arguments on every array element assignment, but Java arrays do not support checking that.

Do not confuse this error with:

~~~java
java.util.List<String> list = new java.util.ArrayList<>();
~~~

That is **creating an object from a generic class using a concrete class constructor**, which is completely valid. The error is creating an **array with a non-reifiable component type**.

## 23. What Is a Reifiable Type?

A type is called **reifiable** when enough information about that type is present at runtime to check it accurately in the ways Java allows. Common examples:

| Type | Reifiable? | Notes |
| --- | --- | --- |
| `String` | Yes | Concrete runtime class |
| `String[]` | Yes | Reifiable array component |
| `int[]` | Yes | Primitive array |
| `List` (raw) | Yes | Only checks raw List |
| `List<?>` | Yes | Unbounded wildcard parameterization |
| `List<String>` | No | Runtime does not fully check the String argument |
| `Map<?, ?>` | Yes | All type arguments are unbounded wildcards |
| `Map<String, Integer>` | No | Concrete generic arguments are erased |
| `T` as a type variable | Usually no | No reified actual type argument |
| `List<String>[]` | No | Non-reifiable array component |

**Key point:** `List<?>` still does not tell whether elements are specifically Object, String, or Integer. It only represents a List with an unknown element type, checked at runtime against the raw List class.

## 24. You Can Create `new List<?>[n]`

The unbounded wildcard parameterization `List<?>` is a reifiable type, so:

~~~java
java.util.List<?>[] items =
        new java.util.List<?>[2];
~~~

is valid. Each array element can hold a reference to some List, regardless of its specific element type argument.

~~~java
items[0] = java.util.List.of("Java");
items[1] = java.util.List.of(17);
~~~

Reading `items[0].get(0)` gives an Object-typed result; you must not infer String without an appropriate check.

This is **not** a workaround for getting a “fully checked List<String> array”. The type arguments of each List remain unknown.

## 25. Runnable Program: A Valid `List<?>[]` Array

Create **`WildcardArrayDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;

public class WildcardArrayDemo {
    public static void main(String[] args) {
        List<?>[] groups = new List<?>[2];

        groups[0] = List.of("Java", "Core");
        groups[1] = List.of(17, 21);

        System.out.println(groups[0]);
        System.out.println(groups[1]);

        Object first = groups[0].get(0);
        System.out.println("first=" + first);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 WildcardArrayDemo.java
java WildcardArrayDemo
~~~

Stdout:

~~~text
[Java, Core]
[17, 21]
first=Java
~~~

The program does not assert that elements in every list are String. It merely holds an array of Lists with unknown generic arguments.

## 26. Why Is Casting `Object[]` to `T[]` Risky?

A commonly encountered pattern:

~~~java
@SuppressWarnings("unchecked")
T[] values = (T[]) new Object[n];
~~~

The compiler allows the unchecked cast in a generic context after a warning/suppression, but **the runtime array object is still Object[]**, not a real String[].

A generic method might inadvertently return `T[]` in source, but when the caller expects `String[]`, the compiler-generated cast at the use site will throw `ClassCastException`.

Beyond the cast issue, this cast also hides type assumptions that could be violated. If you do not have a clear invariant and do not know the exact runtime class, **avoid using it as the default solution**.

## 27. Runnable Program: Unchecked Array Cast Fails

Create **`UnsafeGenericArrayDemo.java`**:

~~~java
public class UnsafeGenericArrayDemo {
    @SuppressWarnings("unchecked")
    static <T> T[] badArray(int size) {
        return (T[]) new Object[size];
    }

    public static void main(String[] args) {
        try {
            String[] strings = UnsafeGenericArrayDemo.<String>badArray(2);
            System.out.println(strings.length);
        } catch (ClassCastException ex) {
            System.out.println("Object[] is not String[]");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 UnsafeGenericArrayDemo.java
java UnsafeGenericArrayDemo
~~~

Stdout:

~~~text
Object[] is not String[]
~~~

Unchecked suppression does not create a real String[]. Retrieving the value at a `String[]` target causes the runtime check to distinguish the actual Object[].

## 28. Replace Generic Arrays with `List<T>` When Appropriate

This is the simplest option for multi-element generic data:

~~~java
class Store<T> {
    private final java.util.List<T> values =
            new java.util.ArrayList<>();

    void add(T value) {
        values.add(value);
    }

    T get(int index) {
        return values.get(index);
    }
}
~~~

`ArrayList` internally may rely on an Object[] implementation detail, but the library maintains the generic API contract. Users of Store do not have to cast arrays themselves or suffer unchecked array creation.

### Benefits

- No need to know the runtime `Class<T>`.
- Supports a variable number of elements.
- Methods accepting/returning T are checked by the compiler.
- Easy to copy an unmodifiable snapshot with List.copyOf.
- No generic array casts needed in application code.

### Limitations

A List<T> still does not check the actual type argument T at runtime when abused via raw types/unchecked casts. Generic APIs provide compile-time checks when used properly.

## 29. Runnable Program: `Store<T>` Using ArrayList

Create **`ListStoreDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ListStoreDemo {
    static final class Store<T> {
        private final List<T> values = new ArrayList<>();

        void add(T value) {
            values.add(value);
        }

        T get(int index) {
            return values.get(index);
        }

        int size() {
            return values.size();
        }
    }

    public static void main(String[] args) {
        Store<String> store = new Store<>();

        store.add("Java");
        store.add("Generics");

        System.out.println("size=" + store.size());
        System.out.println(store.get(0));
        System.out.println(store.get(1));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ListStoreDemo.java
java ListStoreDemo
~~~

Stdout:

~~~text
size=2
Java
Generics
~~~

For an ordinary generic container, List<T> is usually easier to design and maintain than T[].

## 30. Need the Exact Runtime Array Type: Use `IntFunction<T[]>`

`java.util.function.IntFunction<T[]>` takes a length and creates an array of the exact type chosen by the caller:

~~~java
static <T> T[] makeArray(
        int size,
        java.util.function.IntFunction<T[]> arrayFactory) {
    return arrayFactory.apply(size);
}
~~~

Caller:

~~~java
String[] values = makeArray(3, String[]::new);
~~~

The compiler checks that the factory returns `String[]`; the runtime array object actually has component type String.

### Compared to `new T[n]`

- `new T[n]`: the generic implementation tries to deduce runtime T itself, which is not allowed.
- `String[]::new`: the caller knows the concrete component type and passes the factory explicitly.
- `IntFunction<T[]>`: a generic abstraction receiving the capability to create an array of the exact runtime type.

Validate size/null factory and consider ownership when returning the array externally.

## 31. Runnable Program: Array Factory via Constructor Reference

Create **`ArrayFactoryDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Objects;
import java.util.function.IntFunction;

public class ArrayFactoryDemo {
    static <T> T[] create(
            int length,
            IntFunction<T[]> factory) {
        if (length < 0) {
            throw new IllegalArgumentException("length");
        }
        return Objects.requireNonNull(factory, "factory")
                .apply(length);
    }

    public static void main(String[] args) {
        String[] words = create(3, String[]::new);

        words[0] = "Java";
        words[1] = "17";
        words[2] = "Generics";

        System.out.println(Arrays.toString(words));
        System.out.println(words.getClass().getComponentType()
                .getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ArrayFactoryDemo.java
java ArrayFactoryDemo
~~~

Stdout:

~~~text
[Java, 17, Generics]
String
~~~

String[]::new provides the exact runtime component class, with no hidden generic array cast.

## 32. Using `Array.newInstance(Class<T>, int)`

When the caller has a Class<T> token, Java reflection can create an array with runtime component type T:

~~~java
@SuppressWarnings("unchecked")
static <T> T[] createArray(Class<T> type, int size) {
    return (T[]) java.lang.reflect.Array.newInstance(type, size);
}
~~~

Here the cast is still **unchecked** according to the compiler, but it can be justified by an invariant: `Array.newInstance(type,size)` creates an array whose runtime component class comes from the token itself, and the method only returns that created array. When the caller uses a token matching T, the result has the desired runtime array type.

### Cautions

- `Class<T>` must be an appropriate, non-null token.
- The token can point to an interface/abstract class; creating an *array of that type* is still valid even though you cannot `new` an instance directly.
- You cannot create an array with a non-reifiable component `List<String>` using only `List.class`.
- Primitive Class tokens are a special case to consider: a generic API T is a reference type, so this example uses a reference component token.
- SuppressWarnings should be placed right on **the audited cast**, not arbitrarily on the entire class.
- The caller can still break invariants via raw/unchecked code; no API protects against every unchecked misuse.

## 33. Runnable Program: The Array Is Truly `String[]`

Create **`ReflectArrayDemo.java`**:

~~~java
import java.lang.reflect.Array;
import java.util.Arrays;
import java.util.Objects;

public class ReflectArrayDemo {
    static <T> T[] create(Class<T> type, int size) {
        Objects.requireNonNull(type, "type");
        if (size < 0) {
            throw new IllegalArgumentException("size");
        }

        @SuppressWarnings("unchecked")
        T[] result = (T[]) Array.newInstance(type, size);
        return result;
    }

    public static void main(String[] args) {
        String[] values = create(String.class, 2);

        values[0] = "A";
        values[1] = "B";

        System.out.println(Arrays.toString(values));
        System.out.println("component=" +
                values.getClass().getComponentType().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ReflectArrayDemo.java
java ReflectArrayDemo
~~~

Stdout:

~~~text
[A, B]
component=String
~~~

For a simple runtime reference component type, token + Array.newInstance is a reasonable solution if the API requires an array.

## 34. Using `Collection.toArray(IntFunction<T[]>)`

A generic collection can be converted into an array using a caller-provided factory:

~~~java
List<String> words = List.of("Java", "Core");
String[] array = words.toArray(String[]::new);
~~~

Java 11+ supports the `Collection.toArray(IntFunction<T[]>)` overload. In Java 17, this is a concise way to avoid writing casts yourself.

### Runnable Program

Create **`ToArrayDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;

public class ToArrayDemo {
    public static void main(String[] args) {
        List<String> words = List.of("Java", "Core");
        String[] copy = words.toArray(String[]::new);

        System.out.println(Arrays.toString(copy));
        System.out.println("type=" +
                copy.getClass().getComponentType().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ToArrayDemo.java
java ToArrayDemo
~~~

Stdout:

~~~text
[Java, Core]
type=String
~~~

The factory determines the runtime component type; the Collection only supplies the elements. This is a good pattern when interfacing with APIs that require arrays.

## 35. Generic Invariance Differs from Array Covariance

Suppose Integer extends Number.

**Array:**

~~~java
Integer[] integers = {1, 2};
Number[] numbers = integers; // Valid (covariance).
// numbers[0] = 2.5;       // Runtime ArrayStoreException.
~~~

**Generic List:**

~~~java
List<Integer> integers = List.of(1, 2);
// List<Number> numbers = integers; // Compile error.
~~~

Java generic parameterized types are **invariant**: `List<Integer>` is not a subtype of `List<Number>`.

If the goal is to read Numbers:

~~~java
List<? extends Number> numbers = integers;
~~~

When using an extends wildcard, you cannot add an arbitrary Number because the actual element type could be Integer, BigDecimal, etc.

**Motivation:** Java generics check many misuses at compile time instead of relying on runtime array store checks.

## 36. Runnable Program: Covariance and Invariance Side by Side

Create **`ArrayVsGenericsDemo.java`**:

~~~java
import java.util.List;

public class ArrayVsGenericsDemo {
    public static void main(String[] args) {
        Integer[] integers = {1, 2};
        Number[] numbers = integers;

        try {
            numbers[0] = 2.5;
        } catch (ArrayStoreException ex) {
            System.out.println("array store rejected");
        }

        List<Integer> integerList = List.of(1, 2);
        List<? extends Number> numberList = integerList;

        System.out.println("list first=" + numberList.get(0));
        System.out.println("array first=" + integers[0]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ArrayVsGenericsDemo.java
java ArrayVsGenericsDemo
~~~

Stdout:

~~~text
array store rejected
list first=1
array first=1
~~~

A Number[] reference does not change the runtime Integer component type of the array object.

## 37. What Is Heap Pollution?

**Heap pollution** occurs when a variable of a **parameterized type** refers to an object that does not belong to the parameterization expected by the source code.

Common sources:
- raw types/unchecked conversions;
- unchecked casts;
- generic varargs;
- legacy APIs or unvalidated reflection.

Dangerous example:

~~~java
List<String> words = new ArrayList<>();
List raw = words;
raw.add(42); // Unchecked warning.
String first = words.get(0); // Possible ClassCastException.
~~~

Although List<String> has a String contract at the source level, the raw reference allowed inserting an Integer into the same List object.

### How Heap Pollution Differs from ArrayStoreException

- A String[] array knows its runtime String component; assigning an Integer via Object[] is immediately blocked with ArrayStoreException.
- After erasure, List<String> does not check String at runtime on every add if a raw caller bypasses the generic API; the error usually appears later when reading a String.

## 38. Runnable Program: Raw List Causes `ClassCastException`

Create **`HeapPollutionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class HeapPollutionDemo {
    @SuppressWarnings({"rawtypes", "unchecked"})
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List raw = words;

        raw.add(42);

        try {
            String word = words.get(0);
            System.out.println(word);
        } catch (ClassCastException ex) {
            System.out.println("heap pollution detected");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 HeapPollutionDemo.java
java HeapPollutionDemo
~~~

Stdout:

~~~text
heap pollution detected
~~~

@SuppressWarnings only hides the warning in the illustration; it does not fix the data. Production code should remove the unchecked boundary or validate/copy right at the boundary.

## 39. Generic Varargs: Convenient Syntax, Needs Caution

A Java varargs method such as:

~~~java
static <T> void process(List<T>... lists) {}
~~~

uses an array at runtime to hold the arguments. However, `List<T>` is non-reifiable, so generic varargs can lead to a compiler warning and a risk of heap pollution if the method:
- casts the array to Object[];
- writes a list of the wrong type into it;
- exposes the array externally so the caller can mutate it;
- assumes the array contents are fully reified.

The compiler may emit a warning such as `[varargs] Possible heap pollution from parameterized vararg type`. Treat the warning as a signal to audit, not a request to “add SuppressWarnings to make it clean”.

## 40. Runnable Program: Heap Pollution via Varargs Array

Create **`UnsafeVarargsDemo.java`**:

~~~java
import java.util.List;

public class UnsafeVarargsDemo {
    @SafeVarargs
    static void unsafe(List<String>... groups) {
        Object[] asObjects = groups;
        asObjects[0] = List.of(17);

        try {
            String first = groups[0].get(0);
            System.out.println(first);
        } catch (ClassCastException ex) {
            System.out.println("polluted varargs array");
        }
    }

    public static void main(String[] args) {
        unsafe(List.of("Java"));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 UnsafeVarargsDemo.java
java UnsafeVarargsDemo
~~~

Stdout:

~~~text
polluted varargs array
~~~

**Important:** `@SafeVarargs` here is **intentionally misused with respect to the safety guarantee** to prove that a compiler annotation does not by itself turn unsafe code into safe code; do not copy this pattern into production. Javac may warn further about unsafe operations in the method body depending on flags.

## 41. When Is `@SafeVarargs` Used?

The `@SafeVarargs` annotation is a **promise by the method author** that the method does not perform unsafe operations on the generic varargs parameter.

In Java 17, the annotation can be applied to eligible kinds such as:
- static methods;
- final instance methods;
- private instance methods;
- constructors.

It does **not** make a public non-final overridable instance method safe or allow it to be annotated arbitrarily. The compiler may emit warnings if the method body performs dangerous operations despite the annotation.

To use it properly:
- do not write elements of the wrong type into the varargs array;
- do not return/escape the varargs array in a way the caller can mutate unsafely;
- do not assume component type arguments remain at runtime;
- only read references through typed signatures;
- verify nested mutable element data if required by the domain.

## 42. Runnable Program: Safe Generic Varargs (Read-Only)

Create **`SafeVarargsDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeVarargsDemo {
    @SafeVarargs
    static <T> List<T> combine(
            List<? extends T>... groups) {
        List<T> result = new ArrayList<>();

        for (List<? extends T> group : groups) {
            result.addAll(group);
        }

        return List.copyOf(result);
    }

    public static void main(String[] args) {
        List<String> merged = combine(
                List.of("Java"), List.of("Core"));

        System.out.println(merged);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 SafeVarargsDemo.java
java SafeVarargsDemo
~~~

Stdout:

~~~text
[Java, Core]
~~~

The method does not mutate/escape the varargs array and creates its own result. `List.copyOf` creates an unmodifiable structural snapshot and forbids null elements, which is a specific policy of the example.

## 43. Want to Avoid Generic Varargs Entirely?

You can accept `List<? extends List<? extends T>>` or `Collection<? extends List<? extends T>>`:

~~~java
static <T> List<T> combine(
        List<? extends List<? extends T>> groups) {
    List<T> output = new ArrayList<>();
    for (List<? extends T> group : groups) {
        output.addAll(group);
    }
    return output;
}
~~~

When the caller already has a collection of groups, this form can be easier to understand and does not need a generic varargs array.

Tradeoff: the call site is longer when there are only a few literal groups, but the interface semantics are clear.

### Decision

- Varargs when the API is ergonomic and the code has been properly audited.
- Collection-of-collections when the data is already grouped in that structure, or when you want to eliminate the warning/caveat.

## 44. `instanceof T`: Why Is It Invalid?

In a generic class:

~~~java
class Inspector<T> {
    boolean test(Object value) {
        // return value instanceof T; // Compile error.
        return false;
    }
}
~~~

`instanceof` requires a runtime-checkable target type according to Java rules. `T` is not reified into the exact actual parameterization of every Inspector<T> instance, so the compiler does not allow checking directly against a type variable.

A plain cast `(T) obj` is also usually **unchecked** when the compiler cannot verify the concrete T. If the code keeps raw/unchecked paths, the error can surface at the call site.

### Two Standard Solutions

1. If only checking the generic **shape**, use `instanceof Box<?>` or `instanceof List<?>`.
2. If checking the concrete runtime class, accept `Class<T>` and use `isInstance/cast`.

Do not use `getClass().getTypeParameters()` to infer the actual String argument from an arbitrary Box<String> object: it does not store the argument that way.

## 45. `instanceof List<String>` Differs from `instanceof List<?>`

Suppose:

~~~java
Object candidate = java.util.List.of("Java");
~~~

Not allowed:

~~~java
// boolean result = candidate instanceof List<String>;
~~~

because the String type argument in the target `List<String>` is not fully checked by the runtime.

Allowed:

~~~java
boolean result = candidate instanceof java.util.List<?>;
~~~

`List<?>` is a reifiable parameterization. However, a true result only confirms that candidate is a List at runtime; it does not prove every element is a String.

A cast `(List<String>) candidate` can compile with an unchecked warning, but it does not turn the list into a checked String list. When reading an element, the compiler-inserted cast can throw ClassCastException.

## 46. Runnable Program: `instanceof List<?>` Does Not Prove the Element Type

Create **`InstanceofWildcardDemo.java`**:

~~~java
import java.util.List;

public class InstanceofWildcardDemo {
    static String classify(Object candidate) {
        if (candidate instanceof List<?> values) {
            return "list size=" + values.size();
        }
        return "not list";
    }

    public static void main(String[] args) {
        System.out.println(classify(List.of("Java")));
        System.out.println(classify(List.of(17)));
        System.out.println(classify("Java"));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 InstanceofWildcardDemo.java
java InstanceofWildcardDemo
~~~

Stdout:

~~~text
list size=1
list size=1
not list
~~~

Both List<String> and List<Integer> pass the List<?> runtime test; the element type remains unknown.

## 47. Check Each Element Instead of Trusting the Generic Type Argument

If input from an untyped external source must genuinely be a list of Strings, you can:
1. check that the outer object is a `List<?>`;
2. check each element with `instanceof String`;
3. copy into a new `List<String>`.

Do not use an unchecked cast `(List<String>) raw` as a validator.

### Runnable Program

Create **`ValidatedStringListDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ValidatedStringListDemo {
    static List<String> parseStrings(Object input) {
        if (!(input instanceof List<?> values)) {
            throw new IllegalArgumentException("not a list");
        }

        List<String> copy = new ArrayList<>();
        for (Object item : values) {
            if (!(item instanceof String text)) {
                throw new IllegalArgumentException(
                        "non-string element");
            }
            copy.add(text);
        }
        return List.copyOf(copy);
    }

    public static void main(String[] args) {
        System.out.println(parseStrings(
                List.of("Java", "Core")));

        try {
            parseStrings(List.of("Java", 17));
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValidatedStringListDemo.java
java ValidatedStringListDemo
~~~

Stdout:

~~~text
[Java, Core]
rejected=non-string element
~~~

After validating each element, the method returns a typed immutable snapshot. This is a reliable pattern when input comes from JSON parsers, reflection, or raw legacy APIs.

## 48. Runtime `Class.isInstance` and `Class.cast`

With a `Class<T>` token, you can:

~~~java
boolean valid = type.isInstance(value);
T checked = type.cast(value);
~~~

- `isInstance(null)` returns false.
- `cast(null)` returns null; if the API forbids null, `Objects.requireNonNull` is needed.
- `Class.cast` checks runtime class assignability, throwing ClassCastException when incompatible.
- `Class<T>` with String.class checks String; Number.class accepts Integer/Double objects according to the subtype relation.
- The token `List.class` only knows raw List and does not validate String elements.

### Do Not Confuse with `obj.getClass() == type`

`getClass()==type` requires the exact runtime class; `type.isInstance(obj)` accepts matching subclasses/implementations. Most runtime assignability checks should use `isInstance` rather than equality of Class objects.

## 49. Runnable Program: Runtime Check with `Class<T>`

Create **`ClassTokenCheckDemo.java`**:

~~~java
public class ClassTokenCheckDemo {
    static <T> T checked(Class<T> type, Object value) {
        if (!type.isInstance(value)) {
            throw new IllegalArgumentException("wrong type");
        }
        return type.cast(value);
    }

    public static void main(String[] args) {
        String text = checked(String.class, "Java");
        Number number = checked(Number.class, 17);

        System.out.println(text);
        System.out.println(number);

        try {
            checked(String.class, 17);
        } catch (IllegalArgumentException ex) {
            System.out.println("rejected=" + ex.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ClassTokenCheckDemo.java
java ClassTokenCheckDemo
~~~

Stdout:

~~~text
Java
17
rejected=wrong type
~~~

Null is rejected because the method uses `isInstance(null)`, which is false. If null is valid, handle it separately.

## 50. A Bounded T Does Not Make a Generic Argument Reifiable

Example:

~~~java
class Numbers<T extends Number> {
    // boolean test(Object o) {
    //     return o instanceof T; // Still invalid.
    // }
}
~~~

The bound guarantees that the compiler allows calling Number methods on T variables, but T can be Integer, Double, or BigDecimal depending on the actual type argument.

Upon erasure, T is represented by the upper bound Number in many places. However, “obj is a Number” **is not enough to prove obj is the actual T**, for example Integer must be distinct from Double.

Therefore:
- Use `obj instanceof Number` if the domain only needs Number.
- Use a `Class<T>` token if a runtime concrete subtype is needed.
- Use a typed API if a compile-time relationship is already sufficient.

## 51. Runnable Program: Runtime Token for a Bounded T

Create **`BoundedTokenDemo.java`**:

~~~java
import java.util.Objects;

public class BoundedTokenDemo {
    static final class NumberChecker<T extends Number> {
        private final Class<T> type;

        NumberChecker(Class<T> type) {
            this.type = Objects.requireNonNull(type);
        }

        boolean accepts(Object value) {
            return type.isInstance(value);
        }
    }

    public static void main(String[] args) {
        NumberChecker<Integer> integers =
                new NumberChecker<>(Integer.class);

        System.out.println(integers.accepts(7));
        System.out.println(integers.accepts(7.5));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BoundedTokenDemo.java
java BoundedTokenDemo
~~~

Stdout:

~~~text
true
false
~~~

The `Class<Integer>` token restores the exact desired runtime check in this API; the Number bound alone cannot do it.

## 52. Checking `getClass()` on a Generic Object Does Not Reveal T

~~~java
Box<String> words = new Box<>("Java");
Box<Integer> numbers = new Box<>(17);
~~~

`words.getClass()` and `numbers.getClass()` are the same Box class. `getClass().getTypeParameters()` describes **the declaration of type variable T on the Box class**; it does not store the String/Integer of individual values.

If Box holds a non-null object, `box.get().getClass()` can indicate the runtime class of the **value**, but:
- value can be null;
- the declared T can be an interface/supertype different from the runtime concrete class;
- value can be a generic List<String>, yet getClass only reveals the List implementation class, not the String arguments;
- it cannot be used to determine the full declared type argument T.

If you need the type identity of T, store an explicit token.

## 53. Runnable Program: Runtime Class of Value Differs from Generic Declaration

Create **`ValueClassNotTypeArgumentDemo.java`**:

~~~java
public class ValueClassNotTypeArgumentDemo {
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
        Box<Number> number = new Box<>(17);

        System.out.println("box class=" +
                number.getClass().getSimpleName());
        System.out.println("value class=" +
                number.get().getClass().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ValueClassNotTypeArgumentDemo.java
java ValueClassNotTypeArgumentDemo
~~~

Stdout:

~~~text
box class=Box
value class=Integer
~~~

The declared type parameter is Number, the runtime value class is Integer, and the generic Box class does not remember the Number argument on its own.

## 54. `Class<T>` Does Not Fully Represent `List<String>`

Valid class literal:

~~~java
Class<?> rawListClass = java.util.List.class;
~~~

There is no:

~~~java
// Class<List<String>> t = List<String>.class;
~~~

A `Class` entity represents a **runtime class/interface**, and does not contain arbitrary full parameterized type arguments in an expression like `List<String>.class`.

If a framework/deserializer needs to represent `List<String>`, Java Reflection provides interfaces:
- `java.lang.reflect.Type`;
- `ParameterizedType`;
- `TypeVariable`;
- `WildcardType`;
- `GenericArrayType`.

Some frameworks provide a **type token/type reference** to retain generic type information from a reflectable *declaration/signature*.

**Do not conclude that all generic information disappears completely at runtime**: some generic signatures exist in class/method/field declarations and Reflection can read them. What does not exist is a reified `List<String>` runtime class for every ordinary instance.

## 55. Runnable Program: Reflection Reads a Parameterized Field Declaration

Create **`GenericFieldReflectionDemo.java`**:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;

public class GenericFieldReflectionDemo {
    static final class Holder {
        List<String> values;
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field field = Holder.class.getDeclaredField("values");
        Type declaredType = field.getGenericType();

        System.out.println("parameterized=" +
                (declaredType instanceof ParameterizedType));

        ParameterizedType type =
                (ParameterizedType) declaredType;
        System.out.println("raw=" + type.getRawType());
        System.out.println("argument=" +
                type.getActualTypeArguments()[0]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericFieldReflectionDemo.java
java GenericFieldReflectionDemo
~~~

Stdout:

~~~text
parameterized=true
raw=interface java.util.List
argument=class java.lang.String
~~~

Reflection here reads the **field signature** `List<String>`; it does not check actual elements in an arbitrary List object.

## 56. TypeReference Retains Declared Parameterization via an Anonymous Subclass

A common Java idiom:

~~~java
abstract class TypeRef<T> {
    // Read the generic superclass signature of the anonymous subclass.
}
~~~

The caller creates:

~~~java
new TypeRef<List<String>>() {};
~~~

The anonymous subclass declaration contains a generic-superclass signature that Reflection can read as a `ParameterizedType`.

This is **type information capture from a class declaration**, not Java replacing type erasure with reified generic runtime instances. Framework APIs (Jackson, Guava, Spring...) have similar abstractions, though details depend on the library/version.

### Runnable Program

Create **`TypeReferenceDemo.java`**:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;

public class TypeReferenceDemo {
    static abstract class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType p)) {
                throw new IllegalStateException("parameterized subclass");
            }
            type = p.getActualTypeArguments()[0];
        }

        Type type() {
            return type;
        }
    }

    public static void main(String[] args) {
        TypeRef<List<String>> reference =
                new TypeRef<List<String>>() {};

        Type type = reference.type();
        ParameterizedType listType = (ParameterizedType) type;

        System.out.println("raw=" + listType.getRawType());
        System.out.println("argument=" +
                listType.getActualTypeArguments()[0]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 TypeReferenceDemo.java
java TypeReferenceDemo
~~~

Stdout:

~~~text
raw=interface java.util.List
argument=class java.lang.String
~~~

A type reference is useful for serializers and reflective generic metadata, but it does **not** make the JVM prevent inserting an Integer into a raw List at runtime.

## 57. Runtime Cast with `(T)` and Where an Exception Can Be Thrown

In a generic method:

~~~java
@SuppressWarnings("unchecked")
static <T> T unsafe(Object value) {
    return (T) value;
}
~~~

With an unbounded T, the cast in the method body may only remain at the Object level after erasure, but the compiler will apply the appropriate type check at the **caller assignment/use site**:

~~~java
String text = unsafe(17);
~~~

At execution time, casting to String can throw ClassCastException.

Do not confuse the fact that a generic method return compiles with the runtime having verified the actual type T. **An unchecked cast shifts the responsibility of proving safety from the compiler to the programmer**.

If a `Class<T>` token is available, `type.cast` is a clearer choice for checking the real type at the boundary.

## 58. Runnable Program: Wrong `(T)` Causes an Error at the Caller

Create **`UncheckedCastDemo.java`**:

~~~java
public class UncheckedCastDemo {
    @SuppressWarnings("unchecked")
    static <T> T unsafe(Object value) {
        return (T) value;
    }

    public static void main(String[] args) {
        try {
            String text = UncheckedCastDemo.<String>unsafe(17);
            System.out.println(text);
        } catch (ClassCastException ex) {
            System.out.println("caller cast failed");
        }
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 UncheckedCastDemo.java
java UncheckedCastDemo
~~~

Stdout:

~~~text
caller cast failed
~~~

Unchecked casts should only appear at boundaries with documented and tested proofs/invariants, not as a way to silence the compiler when an API is poorly designed.

## 59. Type-Safe Heterogeneous Container Using a Class Key

A pattern that is sometimes useful is `Map<Class<?>, Object>`: each Class token is associated with a value checked by the token.

~~~java
final class Favorites {
    private final Map<Class<?>, Object> values = new HashMap<>();

    public <T> void put(Class<T> type, T value) {
        values.put(type, type.cast(value));
    }

    public <T> T get(Class<T> type) {
        return type.cast(values.get(type));
    }
}
~~~

This pattern lets multiple **concrete class tokens** share one heterogeneous store, but does not support distinguishing `List<String>` from `List<Integer>` using only List.class. In addition, the constructor/put policy must decide null, mutable values, and concurrency.

## 60. Runnable Program: Type-Safe Favorites with a Class Token

Create **`ClassKeyStoreDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ClassKeyStoreDemo {
    static final class Store {
        private final Map<Class<?>, Object> values =
                new HashMap<>();

        <T> void put(Class<T> type, T value) {
            Objects.requireNonNull(type, "type");
            values.put(type, type.cast(value));
        }

        <T> T get(Class<T> type) {
            return type.cast(values.get(type));
        }
    }

    public static void main(String[] args) {
        Store store = new Store();
        store.put(String.class, "Java");
        store.put(Integer.class, 17);

        System.out.println(store.get(String.class));
        System.out.println(store.get(Integer.class));
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ClassKeyStoreDemo.java
java ClassKeyStoreDemo
~~~

Stdout:

~~~text
Java
17
~~~

This is runtime-checked heterogeneous storage by **Class keys**; it is not a generic-array solution.

## 61. A Generic Array Field Can Be Valid Even Though `new T[]` Is Invalid

A declaration:

~~~java
class ArrayHolder<T> {
    private final T[] values;

    ArrayHolder(T[] values) {
        this.values = values.clone();
    }

    T at(int index) {
        return values[index];
    }
}
~~~

is valid, because the constructor **receives an array created by the caller**; it does not write `new T[n]` itself.

Do not confuse:
- `T[]` in a declaration/parameter/return → can be valid.
- `new T[10]` → invalid.
- `String[]::new` or `Array.newInstance(String.class,10)` → valid when the caller provides a concrete runtime component type.

To protect the internal array, the constructor should copy it and getters should return a copy or controlled methods; mutable elements can still alias.

## 62. The “Generic Array Creation” Error Has Many Forms

Invalid snippets:

~~~java
class Holder<T> {
    // T[] first = new T[2];
    // List<T>[] second = new List<T>[2];
}

// List<String>[] names = new List<String>[2];
// Map<String,Integer>[] maps = new Map<String,Integer>[2];
~~~

However, valid forms include:

~~~java
String[] strings = new String[2];
List<?>[] anyLists = new List<?>[2];
List<String> names = new ArrayList<>();
~~~

With `List<String>[]`, you may encounter legacy code creating a raw List[] and then doing an unchecked cast; do not treat that as equivalent to a runtime-checked List<String>[].

## 63. The Checked Runtime Component of an Array Does Not Check List Elements

Suppose:

~~~java
List<?>[] groups = new List<?>[2];
groups[0] = List.of("Java");
groups[1] = List.of(17);
~~~

The runtime array knows the component is a raw/reifiable List type. It can prevent assigning a String object directly into `groups[0]` via Object[]:

~~~java
Object[] objects = groups;
// objects[0] = "not a list"; // Runtime ArrayStoreException.
~~~

However, it does **not** prevent groups[0] from holding `List<Integer>` instead of `List<String>` because the array component has no String type argument.

This is where two layers must be distinguished:
1. the array stores list object references;
2. each list stores elements with generic compile-time contracts.

## 64. Runnable Program: The Array Only Protects the Outer Layer

Create **`ListArrayComponentDemo.java`**:

~~~java
import java.util.List;

public class ListArrayComponentDemo {
    public static void main(String[] args) {
        List<?>[] groups = new List<?>[2];
        groups[0] = List.of("Java");
        groups[1] = List.of(17);

        Object[] objects = groups;

        try {
            objects[0] = "wrong outer type";
        } catch (ArrayStoreException ex) {
            System.out.println("outer type rejected");
        }

        System.out.println(groups[0]);
        System.out.println(groups[1]);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 ListArrayComponentDemo.java
java ListArrayComponentDemo
~~~

Stdout:

~~~text
outer type rejected
[Java]
[17]
~~~

The runtime array check recognizes List references but does not check element parameterization.

## 65. `T...` Varargs Can Be Declared, but Do Not “Reify T”

A generic method:

~~~java
@SafeVarargs
static <T> void printAll(T... values) {
    for (T value : values) {
        System.out.println(value);
    }
}
~~~

is valid syntax when complying with `@SafeVarargs` restrictions. The caller can pass an actual array created by the compiler with a reifiable component type at the call site; however, the implementation must still not treat T as a reliable runtime class token.

If the varargs component type is non-reifiable, the compiler usually warns. Do not use the `values` array itself to store unrelated objects or assume safety when references escape.

### Runnable Program

Create **`GenericVarargsReadDemo.java`**:

~~~java
public class GenericVarargsReadDemo {
    @SafeVarargs
    static <T> void printAll(T... values) {
        for (T value : values) {
            System.out.println(value);
        }
    }

    public static void main(String[] args) {
        printAll("A", "B");
        printAll(1, 2);
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericVarargsReadDemo.java
java GenericVarargsReadDemo
~~~

Stdout:

~~~text
A
B
1
2
~~~

Generic varargs can be useful when only reading and not leaking the array; annotating does not replace proof that the code is safe.

## 66. Using `@SuppressWarnings("unchecked")` Properly

Use suppression in the smallest scope:

~~~java
@SuppressWarnings("unchecked")
T[] array = (T[]) Array.newInstance(type, length);
~~~

The author must have an invariant proving:
- the array is created from the exact runtime type token of T;
- references are not altered across raw/unchecked boundaries;
- methods do not return the wrong type;
- the caller must not pass a type token that does not match the intended T via unchecked code.

**Do not:**

~~~java
// @SuppressWarnings("unchecked") // placed on the entire class just to silence all warnings
class HugeGenericUtility {
    // many unverified casts...
}
~~~

A compiler warning is a signal that the design has limitations; suppression is only an annotation, not a runtime validator.

## 67. When a Generic Interface/Class Uses a Bound, Erasure Affects Casting

With:

~~~java
class NumberBox<T extends Number> {
    private T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
~~~

The erasure of T is Number. The compiler allows calling `get().doubleValue()` in methods because Number has that API. However, the runtime does not automatically know which String/Integer/Double type arguments were used for each NumberBox instance.

If you try to cast NumberBox<Double> to NumberBox<Integer> through raw code, the invariant can still be broken and ClassCastException occurs at the typed use site.

**Bounds increase compile-time expressiveness**; they do not provide reification.

## 68. Runnable Program: Bounded Getter Using the Number API

Create **`NumberBoundErasureDemo.java`**:

~~~java
public class NumberBoundErasureDemo {
    static final class NumberBox<T extends Number> {
        private final T value;

        NumberBox(T value) {
            this.value = value;
        }

        double valueAsDouble() {
            return value.doubleValue();
        }
    }

    public static void main(String[] args) {
        NumberBox<Integer> integer = new NumberBox<>(7);
        NumberBox<Double> decimal = new NumberBox<>(2.5);

        System.out.println(integer.valueAsDouble());
        System.out.println(decimal.valueAsDouble());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 NumberBoundErasureDemo.java
java NumberBoundErasureDemo
~~~

Stdout:

~~~text
7.0
2.5
~~~

You cannot write `new T()` inside NumberBox merely because of the Number upper bound.

## 69. Generics and Overloading: Erasure Affects Method Signatures

Two overloads differing only in type arguments can have a **name clash**:

~~~java
// void process(List<String> words) {}
// void process(List<Integer> numbers) {}
~~~

They share the same erased parameter type List, so two methods with such signatures cannot be placed in the same class.

Similarly:
- overloading `accept(T)` and `accept(Object)` in an unbounded generic class can collide after erasure;
- arrays and varargs also need erased signatures considered;
- a generic method declaration does not create a distinct JVM-level overload solely due to type arguments.

This is a **different** limitation from new T()/generic arrays, though from the same root cause of type erasure.

### How to Fix

- give different method names if the semantics differ;
- use one generic method with the right relationship;
- use a parameterized strategy/factory;
- or pass a `Class<T>` token if runtime selection is needed.

## 70. Bridge Methods: The Compiler Preserves Overriding After Erasure

Example:

~~~java
interface Getter<T> {
    T get();
}

class StringGetter implements Getter<String> {
    @Override
    public String get() {
        return "Java";
    }
}
~~~

After erasure, the interface method has a descriptor similar to Object get(), while the implementation returns String. The compiler can generate a **bridge method** to maintain polymorphism/binary overriding according to Java semantics.

Bridge methods are a compiler/runtime detail supporting generics. You do not have to write them yourself for ordinary correct code.

### Do Not Confuse

A bridge method does not restore a reified runtime T, does not allow `new T()`, and does not make `instanceof List<String>` valid.

## 71. Runnable Program: Generic Interface Dispatch via Bridge

Create **`BridgeDispatchDemo.java`**:

~~~java
public class BridgeDispatchDemo {
    interface Getter<T> {
        T get();
    }

    static final class StringGetter implements Getter<String> {
        @Override
        public String get() {
            return "Java";
        }
    }

    public static void main(String[] args) {
        Getter<String> getter = new StringGetter();

        System.out.println(getter.get());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 BridgeDispatchDemo.java
java BridgeDispatchDemo
~~~

Stdout:

~~~text
Java
~~~

The compiler preserves the contract of Getter<String> with StringGetter even though the erased signatures need additional handling.

## 72. Do Not Use Generic Type Parameters to Extend Throwable

Java restricts classes with type parameters when extending Throwable:

~~~java
// class Failure<T> extends Exception {} // Invalid.
~~~

Because exception catch/throws matching has runtime semantics, while a generic class parameter is not fully reifiable. Although this is not a generic array, it belongs to the same group of **reifiable runtime typing** limitations.

You can still:
- define ordinary exception classes;
- return a generic Result<T> to represent success/failure using values;
- write generic methods throwing a declared checked exception parameter according to appropriate Java rules.

### Do Not Try to Write `catch (T ex)`

A type variable T cannot be used as an exception handler target like a runtime exception class.

## 73. Decision Table: Which Alternative Is Right?

| Need | Should not write | Appropriate option |
| --- | --- | --- |
| Receive a value of type T | `new T()` | Constructor receiving T |
| Create T according to caller logic | `new T()` | `Supplier<? extends T>` |
| Create T needing an argument | Assuming no-arg constructor | `Function<A, ? extends T>` / factory |
| Create T by runtime class | `T.class` | `Class<T>` + reflection if appropriate |
| Create array of exact concrete type | `new T[n]` | `IntFunction<T[]>` or `Array.newInstance` |
| Hold generic sequence | `new T[n]` | `List<T>` |
| Array of List<String> | `new List<String>[n]` | `List<List<String>>` |
| Array of lists regardless of element type | Generic array cast | `new List<?>[n]` if truly needed |
| Check runtime String | `instanceof T` | `String.class.isInstance` or token |
| Check outer List | `instanceof List<String>` | `instanceof List<?>` |
| Check List<String> from Object | Unchecked cast | Validate each element then copy |
| Retain metadata `List<String>` | `List<String>.class` | Type/ParameterizedType/type reference |
| Generic varargs | Trusting annotation as guarantee | Audit; `@SafeVarargs` only when method is safe |
| Share heterogeneous values | Raw Box | `Class<T>` key + checked cast |
| Refactor warning | Suppressing all warnings | Fix design or local documented proof |

## 74. Common Compile-Time Errors

| Invalid syntax/idea | Reason |
| --- | --- |
| `new T()` | Type variable is not a concrete class constructor target |
| `new T[10]` | Generic array creation prohibited |
| `new List<String>[10]` | Component type is non-reifiable |
| `T.class` | Type variable has no class literal |
| `List<String>.class` | Parameterized type has no class literal |
| `value instanceof T` | Runtime does not check actual T |
| `obj instanceof List<String>` | List<String> non-reifiable target |
| `Box<int>` | Generic type argument must be a reference type |
| `Box<Object> obj = new Box<String>()` | Generic invariance |
| `void f(List<String>)` and `void f(List<Integer>)` | Erased signatures collide |
| `static T field` in Box<T> | Class type parameter cannot be used in static context |
| `new T[]{...}` | Generic array creation |
| `class Failure<T> extends Exception` | Generic Throwable subclass is forbidden |
| `@SafeVarargs` on ordinary overridable instance method | Annotation is invalid for that kind of declaration |

**Remember:** “Compiler rejects” differs from “runtime throws an exception”. Write negative examples as separate code when you truly need to observe javac diagnostics; do not copy them into runnable programs.

## 75. Common Runtime Failures

| Exception/consequence | Cause |
| --- | --- |
| `ArrayStoreException` | Writing wrong runtime component type into array via covariant supertype reference |
| `ClassCastException` | Unchecked generic cast or polluted raw/varargs data read as String/typed value |
| `NullPointerException` | Unboxing null, null token, or unvalidated factory/array input |
| `ReflectiveOperationException` subclasses | Constructor reflection lookup/access/instantiation/invocation errors |
| `IllegalArgumentException` | Invalid `Array.newInstance`/input size depending on API, or domain validation |
| Corrupt logical data | Raw collections/unchecked aliases break declared parameterized type invariant |
| Mutable aliasing | Object[]/T[]/List<T> shared without an ownership/copying policy |

### Distinguishing Where Failures Are Detected

- The compiler catches mismatches in typed generic source.
- Runtime array component checks catch array store mismatches.
- A typed getter/use site can throw ClassCastException when heap pollution has already occurred.
- A reflection cast/token can verify the runtime concrete class but does not validate the contents of nested generic collections.

## 76. Anti-Patterns to Avoid

**Class-wide SuppressWarnings:** Hides places where invariants have not been proven.

**Manually casting Object[] to T[]:** Easily blows up at a String[] call site, creating a false sense of type safety.

**Using raw List/Box as the interoperability default:** Strips the compiler of its ability to protect code.

**Using `getClass().getTypeParameters()` to infer caller T:** This is declaration metadata, not the actual per-instance type argument.

**Using `(List<String>) obj` instead of validation:** The runtime does not check the String element type in an unchecked cast.

**Assuming `List<?>` contains arbitrary Objects you can add to:** Reading works, but you cannot add arbitrary non-null elements because the captured element type is unknown.

**Passing Class<List<String>> via `List.class` and trusting it provides full generics:** A Class token does not represent the String argument.

**Using @SafeVarargs while still writing into the backing varargs array:** The annotation is a promise; it does not make the method safe.

**Using reflection for every constructor:** Reflection has checked errors, accessibility/module restrictions, and unnecessary complexity; Supplier/factory is usually better.

**Treating ArrayStoreException as validation of List<String> elements:** Array stores only know the matching runtime component class and do not check nested generic arguments.

**Building your own concurrent generic array holder with unsafe casts:** Has both type safety issues and concurrency/ownership policy issues.

**Not testing negative paths:** Generic APIs involving raw boundaries need to test ClassCastException, ArrayStoreException, null, and incorrect factories.

## 77. Exercise 1 — Why Is `new T()` Invalid?

A generic class:

~~~java
class Maker<T> {
    // T create() { return new T(); }
}
~~~

**Answer:** T is an erased type variable and does not specify a concrete constructor; Java has no constructor constraint guaranteeing a no-arg constructor. Pass Supplier<? extends T>, a factory Function, or Class<T> for appropriate reflection needs.

## 78. Exercise 2 — Supplier or Class Token?

You need to create StringBuilder via a no-arg constructor while wanting an API that is easy to test and does not depend on reflection.

**Answer:** Supplier<StringBuilder> with `StringBuilder::new` is usually better. Reflection Class<T> is useful when the class is selected by a runtime token and reflective discovery is needed.

## 79. Exercise 3 — Can You Create `new List<String>[3]`?

**Answer:** No, because List<String> is non-reifiable and an array requires runtime component checks. Use `List<List<String>>` if you want 3 groups of String values, or `List<?>[]` when you only need an array of arbitrary Lists.

## 80. Exercise 4 — Reifiable Classification

`String[]`, `List<?>`, `List<String>`, `Map<?,?>`, `T`.

**Answer:** String[], List<?>, and Map<?,?> are reifiable in standard cases; List<String> and type variable T are not fully reifiable.

## 81. Exercise 5 — Array Covariance

~~~java
Integer[] ints = {1};
Number[] nums = ints;
// nums[0] = 2.5;
~~~

**Answer:** The last line compiles, but if executed it will throw ArrayStoreException because the actual array is Integer[].

## 82. Exercise 6 — Generic Invariance

Can `List<Integer>` be assigned directly to `List<Number>`?

**Answer:** No. Java generic parameterizations are invariant. Use `List<? extends Number>` if you only need to read Numbers.

## 83. Exercise 7 — Casting Object[] to String[]

In a generic method, `return (T[]) new Object[2]` with @SuppressWarnings unchecked. The caller receives `String[]`.

**Answer:** Runtime Object[] does not become String[], so the cast at the call site can throw ClassCastException. Use `String[]::new` or Class<String>+Array.newInstance.

## 84. Exercise 8 — `Class<T>` Token

Write a function accepting Object and Class<T>, returning T only if it matches at runtime.

**Suggested answer:**

~~~java
static <T> T checked(Class<T> type, Object value) {
    if (!type.isInstance(value)) {
        throw new IllegalArgumentException("wrong type");
    }
    return type.cast(value);
}
~~~

Note that isInstance(null) returns false; validate the null policy intentionally.

## 85. Exercise 9 — Array via Constructor Reference

Create String[3] in a generic method using IntFunction<T[]>.

**Suggested answer:**

~~~java
static <T> T[] make(int count,
                     java.util.function.IntFunction<T[]> maker) {
    return maker.apply(count);
}

String[] names = make(3, String[]::new);
~~~

The factory creates a real String[] with runtime component class String.

## 86. Exercise 10 — Outer vs. Inner Runtime Type

`obj instanceof List<?>` is true for `List.of(17)`. Can you assert that the list contains Strings?

**Answer:** No. The runtime test only confirms the outer List. To ensure List<String>, check each element and create a validated typed copy.

## 87. Exercise 11 — Complete Type Token

Why is `Class<List<String>> clazz = List<String>.class` invalid?

**Answer:** There is no parameterized class literal. `List.class` only knows raw List. Use Reflection Type/ParameterizedType or a framework type reference to express the generic signature, along with separate validation.

## 88. Exercise 12 — Heap Pollution

A raw List reference adds an Integer into a List<String>. Does the error happen at the add or get step?

**Answer:** Raw add can run with an unchecked warning without checking String. The typed get/use site can throw ClassCastException due to the compiler-inserted cast.

## 89. Exercise 13 — Generic Varargs

A static method accepts `List<String>...`, casts the varargs array to Object[], and writes `List.of(42)`.

**Answer:** Unsafe; heap pollution can occur. Do not attach @SafeVarargs to “shield” it; the annotation is a promise, and the method is still wrong. Avoid writing into the varargs array.

## 90. Exercise 14 — `List<T>` or `T[]`?

A Store<T> needs add/get/size and a variable number of elements.

**Answer:** `List<T>`/ArrayList<T> is usually easier and more type-safe than creating T[] yourself via a cast. If interfacing with an API that requires an array of the exact component type, accept an array factory or a Class<T> token.

## 91. Exercise 15 — Generic Bound

Can `class Maker<T extends Number>` write `new T()`?

**Answer:** No. The bound only tells that T is a subtype of Number; it does not promise a concrete constructor. Provide a Supplier/Function/Class token.

## 92. Exercise 16 — `Class.cast`

What does `String.class.cast("Java")` return? What happens with `String.class.cast(17)`?

**Answer:** Returns String "Java" in the first case; the latter case throws ClassCastException. `String.class.cast(null)` returns null, so if null is forbidden, validate it separately.

## 93. Exercise 17 — Compiler and Runtime Responsibilities

State the difference between `List<String>` type safety and `String[]` store checks.

**Answer:** Generic List<String> checks compile-time type arguments in typed code, whereas runtime erasure does not check String for raw writes. String[] has runtime component type String, so writing the wrong object via Object[] causes ArrayStoreException immediately.

## 94. Exercise 18 — Generic Reflection

A field declaration is `List<String> values`. Can Reflection read the String argument from the field signature? Does this prove that an arbitrary List instance contains Strings?

**Answer:** Field.getGenericType can return ParameterizedType with the String argument; that is **declaration** metadata, not runtime element validation. Do not infer the quality of data in an arbitrary instance.

## 95. Safe API Selection Workflow

**Step 1 — Identify the requirement.** Do you need to create a new T object, create a T[] array, or simply hold a list of values? These are three different needs.

**Step 2 — If only holding values, prefer List<T>.** There is no requirement to build a T[].

**Step 3 — If creating a new object, prefer Supplier/Function.** The caller specifies the real constructor/factory.

**Step 4 — If the runtime class is selected dynamically, consider Class<T>.** Handle reflection failures and accessibility/module policies.

**Step 5 — If an array with the exact component type is needed, pass IntFunction<T[]>.** The caller writes `String[]::new`.

**Step 6 — If using Array.newInstance, maintain the token invariant.** Suppress the unchecked cast in the right place, and test the String[] runtime class.

**Step 7 — If receiving an unknown Object, check the outer shape.** Use `instanceof List<?>`, do not blindly cast to List<String>.

**Step 8 — Validate nested elements.** A runtime Class token only confirms the concrete class at the layer with the token; List<String> must validate each element if the input is untyped.

**Step 9 — Avoid raw/unchecked boundaries.** Place the conversion at a narrow boundary with a proof.

**Step 10 — For generic varargs, audit the method body.** Do not corrupt/escape the array; use @SafeVarargs only when truly safe.

**Step 11 — Distinguish type-safe from immutable.** Array/List may be mutable; define ownership and defensive copying.

**Step 12 — Test both compile time and runtime.** Positive examples + negative compiler fixtures + ClassCastException/ArrayStoreException cases.

## 96. End-of-Lesson Checklist

- [ ] I understand that Java 17 generic type parameters primarily undergo type erasure.
- [ ] I know that `Box<String>` and `Box<Integer>` do not have separate runtime classes.
- [ ] I know why `new T()` is forbidden.
- [ ] I know that `T extends Number` still does not allow `new T()`.
- [ ] I use a constructor receiving an object when I do not need to create T myself.
- [ ] I know `Supplier<? extends T>` to create T via a factory.
- [ ] I know `Function<A,? extends T>` for a constructor needing an argument.
- [ ] I understand Supplier is not required to always create a fresh object if the contract does not specify it.
- [ ] I know the `Class<T>` type token.
- [ ] I understand reflection instance creation has checked exceptions and accessibility rules.
- [ ] I do not use `T.class`.
- [ ] I do not use `List<String>.class`.
- [ ] I know `new T[n]` is forbidden.
- [ ] I know `new List<String>[n]` is forbidden.
- [ ] I distinguish reifiable and non-reifiable types.
- [ ] I know `List<?>[]` can be created when appropriate.
- [ ] I distinguish array covariance from generic invariance.
- [ ] I can explain runtime ArrayStoreException.
- [ ] I do not arbitrarily cast Object[] to T[].
- [ ] I know `IntFunction<T[]>`/`String[]::new`.
- [ ] I know `Array.newInstance(Class<T>,length)` and the invariant of the cast.
- [ ] I prefer `List<T>` for a generic dynamic collection.
- [ ] I know `Collection.toArray(String[]::new)`.
- [ ] I identify heap pollution from raw types/casts/varargs.
- [ ] I know generic varargs can emit unchecked warnings.
- [ ] I know `@SafeVarargs` is a promise and does not make a method safe by itself.
- [ ] I do not use `instanceof T`.
- [ ] I do not use `obj instanceof List<String>` when the target is non-reifiable.
- [ ] I know `instanceof List<?>` checks the outer list, not the String elements.
- [ ] I know to validate each element when input data is not type-checked.
- [ ] I know `Class.isInstance` and `Class.cast`.
- [ ] I know `isInstance(null)` is false and `cast(null)` returns null.
- [ ] I understand `getClass()` does not reveal the per-instance generic type argument.
- [ ] I know Reflection `ParameterizedType` can read declared generic metadata.
- [ ] I distinguish a type reference from a reified generic object type.
- [ ] I know a bounded T is still not reified.
- [ ] I do not use broad unchecked suppression without a proof.
- [ ] I understand bridge methods relate to erasure but do not solve new T().
- [ ] I understand generics type safety differs from immutability and concurrency safety.
- [ ] I can predict stdout and analyze compile errors of examples.

**Conclusion:** The restrictions on `new T()`, `new T[]`, and `instanceof T` all stem from the difference between **generic types checked at compile time** and **runtime type information** in Java. Arrays check their component class at runtime and therefore cannot safely represent an array with a non-reifiable `List<String>` component. Let the **caller provide a factory or type token** when creating objects/arrays is necessary, use **`List<T>`** when an array is not truly needed, check unknown input via **`List<?>` + element validation**, and use unchecked casts/`@SafeVarargs` only when the invariant has been proven. These choices keep Java 17's type safety without pretending that type erasure has disappeared.
