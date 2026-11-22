# Type Parameter, Type Argument, Type Variable, and Parameterized Type in Java

## 1. Goal and Big Picture

Generics make it possible to describe relationships between types directly in class, interface, constructor, and method declarations. Instead of writing a data structure that only operates on `Object` and casting at every usage site, we declare a “placeholder” for a type and let the compiler verify operations against that type.

After this lesson, you should accurately recognize the four terms **type parameter**, **type argument**, **type variable**, and **parameterized type**; read nested generic declarations; distinguish generic classes from generic methods; understand what wildcards/bounds are; and know which aspects exist only at compile time.

A short example:

~~~java
class Box<T> {
    T value;
}

Box<String> title = new Box<>();
~~~

- **Box<T>** in the declaration line: **T** is declared as a *type parameter*, and at the same time creates a *type variable* named T within the scope of the class.
- **Box<String>** at the usage site: **String** is the *type argument* passed to the T position; the entire **Box<String>** is a *parameterized type*.
- **new Box<>()**: the diamond operator (**diamond operator**) allows Java to infer the type argument from the assignment context, which here is String.
- The name **Box** is the generic class declaration name; using **Box** without arguments in a type context usually produces a *raw type*, which must be distinguished from **Box<?>**.

The four concepts are related, yet answer four different questions: **where is the slot that accepts a type declared?** (type parameter), **what is the placeholder type name inside the declaration?** (type variable), **which type is supplied to that slot?** (type argument), and **what type is formed after applying the type argument?** (parameterized type).

## 2. Type Parameter

A *type parameter* appears in the angle-bracket list right after a class/interface name, or right before the return type of a generic method. It declares a placeholder name for a type that will be used consistently across related positions.

~~~java
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
~~~

**K** and **V** are two independent type parameters; their declaration syntax is **<K, V>**. The compiler uses this relationship to guarantee that `key()` returns the exact type for that specific pair, and similarly for `value()`. Using two different letters indicates that they are not required to be the same type.

Common declaration positions:

| Position | Example | Meaning |
| --- | --- | --- |
| Generic class | class Box<T> | T belongs to the class declaration |
| Generic interface | interface Repository<ID, E> | ID and E belong to the interface |
| Generic method | static <T> T identity(T value) | T belongs only to the method |
| Generic constructor | <U> Holder(U source) | U belongs to the constructor |
| Parameter with upper bound | <T extends Number> | T must satisfy the Number constraint |
| Multiple upper bounds | <T extends Number & Comparable<T>> | T must satisfy both constraints |

In method syntax, **<T>** is placed **before the return type**. For example, **static <T> T identity(T value)** has type parameter T, returns T, and takes a value of type T. If you write **static T identity(T value)** inside a class that does not declare T, the compiler does not know what T is.

The type parameter list also expresses constraints:

~~~java
class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double doubleValue() {
        return value.doubleValue();
    }
}
~~~

Here **T extends Number** means the supplied type must be Number or a subtype of Number, such as Integer or Double. The `extends` keyword applies to both classes and interfaces in generic bounds; there is no **<T implements Runnable>** syntax. When there are multiple bounds, the class bound (if any) must come first; subsequent bounds are interfaces joined by **&**. You cannot declare two different classes as bounds.

Common naming conventions: **T** (Type), **E** (Element), **K** (Key), **V** (Value), **R** (Result), **U** (another type). These are merely conventions, not Java keywords. Longer names can be used, though recognizable single letters help read API signatures faster.

## 3. Type Variable

A *type variable* is the name **T**, **K**, **V**, or another identifier declared by a type parameter. It is used as a **type** within its valid scope, not as a runtime variable holding a value.

~~~java
class CacheEntry<K, V> {
    private K key;
    private V cachedValue;

    CacheEntry(K key, V cachedValue) {
        this.key = key;
        this.cachedValue = cachedValue;
    }

    V read() {
        return cachedValue;
    }
}
~~~

In this example, K and V are used in the type positions of fields, constructor parameters, and return type. They are not two runtime objects named K and V; you cannot assign **T = String** or print T as a value just because **<T>** was declared. When using `CacheEntry<String, Integer>`, the compiler checks that `key` is a `String` and `cachedValue` is an `Integer`.

Scope is very important:

- A type variable declared on a class can be used in instance fields, instance methods, and appropriate type declarations within the class.
- A type variable declared by a method exists only within that method's signature and body; two methods both named with **T** can have two distinct type variables.
- A static member of a generic class cannot directly use the class's T, because `static` belongs to the class as a whole rather than specifically to `Box<String>` or `Box<Integer>`. A static method that wants to use T must **declare its own** type parameter.

~~~java
class Helper<T> {
    T echo(T input) {          // Class's T
        return input;
    }

    static <U> U identity(U input) { // Static method's own U
        return input;
    }
}
~~~

There is a subtle point that easily causes confusion: **type parameter** emphasizes *the declaration site* **<T>**, whereas **type variable** emphasizes *the already-declared name T used as a type*. They are closely related, but a “type variable” is not a type passed in from outside.

Even the exact same symbol T can play two roles at two levels: in **class Box<T>**, T is the name of the type parameter; in **List<T> values**, T is a *type variable* being used as a *type argument* to the generic interface `List`. The role of an expression depends on **the context where it appears**, not just the character it contains.

## 4. Type Argument

A *type argument* appears inside **<...> at the usage site of a generic type**. It specifies the type that a type parameter slot represents in that usage.

~~~java
Pair<String, Integer> age = new Pair<>("Lan", 24);
Pair<Long, Long> range = new Pair<>(100L, 200L);
java.util.List<String> names = java.util.List.of("An", "Binh");
java.util.Map<String, java.util.List<Integer>> marks =
        java.util.Map.of("java", java.util.List.of(8, 9));
~~~

Reading each line in turn:

- `Pair<String, Integer>` has **String** as the argument for K, and **Integer** as the argument for V.
- `Pair<Long, Long>` passes the same `Long` type into two *different* positions; there is no rule forcing K and V to differ.
- `List<String>` passes `String` for parameter E of `List<E>`.
- `Map<String, List<Integer>>` passes `String` for K and **the entire type `List<Integer>`** for V; inside `List<Integer>`, `Integer` is in turn the type argument.
- Regular type arguments are reference types, including interfaces, classes, array types, and parameterized types. **List<int>** is an error; use **List<Integer>**. **List<int[]>**, however, is valid because `int[]` is a reference type.

Concrete class names are not the only type arguments. Wildcards are also a form of type argument:

~~~java
java.util.List<?> unknown;
java.util.List<? extends Number> numbers;
java.util.List<? super Integer> integerConsumers;
~~~

Here **?**, **? extends Number**, and **? super Integer** are *wildcard type arguments*. They describe a family of compatible types rather than declaring a newly named type variable. **?** is not an alias for T, and you cannot declare **class Box<?>** in place of **class Box<T>**.

Whenever you see **<T>**, ask whether it is **declaring** the name T or **passing** T as an argument to another generic type: **class Box<T>** declares it; **List<T>** inside `Box` uses T as an argument.

## 5. Parameterized Type

A *parameterized type* is formed when a generic declaration is used with a list of type arguments, such as **List<String>**, **Map<String, Integer>**, **Box<T>**, or **List<?>**. This concept refers to **the entire type**, whereas type argument refers only to the component passed in.

| Expression | Classification | Reason |
| --- | --- | --- |
| List<E> in the declaration `interface List<E>` | Generic interface declaration with type parameter E | Introducing E |
| List<String> | Parameterized type | Using List with argument String |
| Map<String, List<Integer>> | Nested parameterized type | V is another parameterized type |
| List<T> inside a class with `<T>` | Parameterized type using a type variable | T is in scope and passed to List |
| List<?> | Parameterized type using a wildcard | Exact type argument is unknown |
| List (without angle brackets in a type position) | Raw type | Omits List's type argument |
| String | Ordinary class type | String is not a generic class |

Distinguish between a **generic type declaration** and a **parameterized type**: **interface List<E>** is the generic declaration; **List<String>** is one usage with arguments supplied. A single generic declaration can have many valid parameterized types, and they differ in compile-time type checking.

Do not think of a “parameterized type” as a separate physical class generated by Java for each argument. In the JVM, type erasure causes `ArrayList<String>` and `ArrayList<Integer>` to typically use the same runtime class `ArrayList`; generics primarily enforce type relationships in source code along with the necessary compiler-inserted checks and casts.

## 6. Standalone Runnable Example: Identifying Each Role

Save as **GenericTermsDemo.java**:

~~~java
import java.util.List;

public class GenericTermsDemo {
    static final class Box<T> {
        private final T value;

        Box(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }
    }

    static <E> E first(List<E> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }
        return items.get(0);
    }

    public static void main(String[] args) {
        Box<String> greeting = new Box<>("Java generics");
        List<Integer> versions = List.of(17, 21);

        String message = greeting.get();
        int firstVersion = first(versions);

        System.out.println(message);
        System.out.println(firstVersion);
    }
}
~~~

Compile and run with JDK 17 or newer:

~~~bash
javac -encoding UTF-8 GenericTermsDemo.java
java GenericTermsDemo
~~~

Stdout:

~~~text
Java generics
17
~~~

Step-by-step explanation:

1. **Box<T>** declares a type parameter T; **T value**, **Box(T value)**, and **T get()** use the type variable T inside the class.
2. **Box<String>** is a parameterized type, and `String` is the type argument. Assigning the result of `get()` to `String` is checked at compile time.
3. **new Box<>** infers `String` from the left-hand side of the assignment; **<>** on the constructor does not declare a new type parameter.
4. **<E> E first(List<E> items)** declares a generic method. **E** is the method's type variable; **List<E>** is a parameterized type using E as its argument.
5. From the argument **List<Integer>**, the compiler infers E as `Integer` when calling `first(versions)`. `Integer` is auto-unboxed to assign to **int firstVersion**.
6. **List.of(17, 21)** creates a structurally unmodifiable list with element type `Integer`; that is a property of the `List.of` factory, not a general property of every `List<Integer>`.

If you replace the statement with **String invalid = first(versions);**, the compiler reports a type error because `Integer` cannot be used as a `String`; generics allow errors to be caught early.

## 7. Generic Class, Generic Method, and Generic Constructor

A generic class declares type parameters immediately after the class name; instance members can use these parameters. A generic method has **its own type parameter list**, placed before the return type, even when its enclosing class is not generic.

~~~java
class Samples<T> {
    T stored;

    Samples(T stored) {
        this.stored = stored;
    }

    T get() {
        return stored;           // Uses the class's T; get() itself does not declare <T>
    }

    <U> U select(U candidate) {
        return candidate;        // U belongs only to select()
    }

    static <R> R same(R value) {
        return value;            // R is declared by the static method itself
    }
}
~~~

A constructor can also declare an independent type parameter:

~~~java
class Receipt<T> {
    private final T value;

    <U> Receipt(U original, java.util.function.Function<U, T> converter) {
        this.value = converter.apply(original);
    }

    T get() { return value; }
}

// Usage example:
// Receipt<Integer> receipt = new Receipt<>("42", Integer::parseInt);
~~~

`Receipt`'s T belongs to the class; the constructor's U describes the input data type, which can differ from T. **Receipt<Integer>** is the parameterized type of the class, while the constructor call also requires the compiler to infer U as `String`.

Separate three operations that can look visually similar: declaring **<T>**; using a type **Box<T>** where T is already in scope; and inferring arguments via the diamond **new Box<>()**. They are not interchangeable.

## 8. Type Variable Bounds and Wildcards: Two Different Mechanisms

There are two kinds of bounds to read accurately:

**Type parameter bounds** are written in a generic declaration: **<T extends Number>**, **<T extends Number & Comparable<T>>**. They place a constraint on T and allow the method body to use the APIs of the known bounds, such as `Number.doubleValue()` or `Comparable.compareTo()`.

**Wildcard bounds** are written at a type usage site: **List<? extends Number>** or **List<? super Integer>**. They allow accepting a group of parameterized types without having to name a specific type variable for each list.

~~~java
import java.util.ArrayList;
import java.util.List;

public class BoundsAndVarianceDemo {
    static <T extends Number & Comparable<T>> T largest(List<T> items) {
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty list");
        }
        T maximum = items.get(0);
        for (T item : items) {
            if (item.compareTo(maximum) > 0) {
                maximum = item;
            }
        }
        return maximum;
    }

    static double sum(List<? extends Number> source) {
        double total = 0;
        for (Number value : source) {
            total += value.doubleValue();
        }
        return total;
    }

    static void addTwo(List<? super Integer> target) {
        target.add(2);
        target.add(4);
    }

    public static void main(String[] args) {
        System.out.println(largest(List.of(3, 8, 5)));
        System.out.println(sum(List.of(1, 2, 3)));

        List<Number> destination = new ArrayList<>();
        addTwo(destination);
        System.out.println(destination);
    }
}
~~~

Save as **BoundsAndVarianceDemo.java**, run:

~~~bash
javac -encoding UTF-8 BoundsAndVarianceDemo.java
java BoundsAndVarianceDemo
~~~

Stdout:

~~~text
8
6.0
[2, 4]
~~~

Explanation: in `largest`, T is a single consistent concrete type inferred as `Integer` and has `compareTo`; whereas in `sum`, **? extends Number** allows accepting `List<Integer>`, `List<Double>`, or `List<Number>`. You can read elements at least as `Number`, but you cannot safely add a new `Integer` because the actual element type might be `Double`. In `addTwo`, **? super Integer** can represent `Integer`, `Number`, or `Object`; therefore adding an `Integer` is safe, while reading elements out only guarantees `Object`.

The **PECS** mnemonic (Producer Extends, Consumer Super): a source that produces elements uses **? extends T** when appropriate; a destination that consumes elements uses **? super T**. This is an API design guideline, not a syntax law forcing every list to be read-only or write-only. With **List<?>**, you can read as `Object`; you cannot add any element other than `null` because the actual type is unknown.

If a method needs to **link the same type** across multiple parameters or between input and output, a named type variable usually expresses the relationship better than a wildcard. For example, **static <T> T choose(T a, T b)** returns a type inferred by the compiler from both arguments; a signature using only **?** cannot use a wildcard as a standalone return type name.

## 9. Invariance: Do Not Infer Wrong Relationships

Even though **Integer extends Number**, that does **not** mean **List<Integer> extends List<Number>**. Generic parameterization is *invariant* by default.

The following snippet does not compile:

~~~java
import java.util.List;

// Illustrates a type error only; not a runnable program.
List<Integer> integers = List.of(1, 2);
List<Number> numbers = integers;  // Compile-time error
~~~

If the assignment above were allowed, someone could add a `Double` to `numbers` and then read it as an `Integer` from `integers`, breaking type safety. When you want to *read `Number` values from various kinds of lists*, use **List<? extends Number>**. When you want to *write `Integer` values into various destination lists*, use **List<? super Integer>**.

Similarly, **List<String>** is not a subtype of **List<Object>**, even though `String` is a subtype of `Object`. A method receiving **List<Object>** is allowed to add any `Object`; that method cannot do so with a `List<String>`.

Comparison of those signatures:

| Signature | Accepts List<Integer>? | Can add Integer? | Minimum read type |
| --- | --- | --- | --- |
| List<Integer> | Yes | Yes (if the list allows modification) | Integer |
| List<Number> | No | Yes | Number |
| List<? extends Number> | Yes | No, except null | Number |
| List<? super Integer> | Yes | Yes (if the list allows modification) | Object |
| List<?> | Yes | No, except null | Object |

The ability to compile an **add** call does not guarantee the list object is mutable at runtime: `List.of(...)` still throws `UnsupportedOperationException` if `add` is called, even though the type argument is valid.

## 10. Type Inference: When Type Arguments Are Not Written Explicitly

Java commonly infers generic types from the receiving variable type, passed arguments, generic bounds, and expression context.

~~~java
java.util.List<String> a = new java.util.ArrayList<String>();
java.util.List<String> b = new java.util.ArrayList<>();
java.util.List<Integer> c = java.util.List.of(1, 2, 3);
java.util.Map<String, java.util.List<Integer>> d = new java.util.HashMap<>();
~~~

The first two lines create the same parameterized type **List<String>** on the variable side; the second line uses the diamond to avoid repeating `String`. In **List.of(1, 2, 3)**, the `int` literals are boxed into `Integer` and the generic factory infers the appropriate type. The static type of the left-hand variable still matters: for example, a variable declared as **List<String>** does not automatically become **ArrayList<String>**, even if the object is an `ArrayList`.

You can specify the type argument explicitly when calling a generic method if needed:

~~~java
String x = java.util.Objects.<String>requireNonNull("ok");
~~~

The **<String>** after the dot here is an **explicit method type argument**, not a type parameter declaration. Similarly, **var names = java.util.List.of("A", "B");** infers the variable's type from the initializer without removing generic rules. Use type inference when it is clear; write the type explicitly when it helps readers understand intent or resolves unexpected inference.

## 11. Raw Types and Type Erasure

A **raw type** uses a generic name without passing type arguments, such as **List** instead of **List<String>** or **List<?>**. Raw types exist primarily for compatibility with older Java code, bypass necessary type checks, and can trigger *unchecked* warnings.

~~~java
// Illustrates the risk, not recommended to run:
java.util.List<String> safe = new java.util.ArrayList<>();
java.util.List raw = safe;      // Raw type
raw.add(123);                  // Unchecked call; causes heap pollution
String value = safe.get(0);    // ClassCastException at runtime
~~~

Difference from **List<?>**: `List<?>` still represents a list with an unknown element type and the compiler prevents adding arbitrary values; raw `List` loses many of those checks. Avoid raw types in new code; if you must work with legacy APIs, isolate the unchecked region and validate data at the boundary.

**Type erasure** is the mechanism Java uses to implement generics. During compilation, most type variables are replaced by their upper bound (or `Object` if unbounded), the compiler adds necessary casts, and may generate bridge methods to preserve polymorphism. Consequently, generics do not create a separate class per type argument.

Save as **ErasureDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ErasureDemo {
    public static void main(String[] args) {
        List<String> words = new ArrayList<>();
        List<Integer> counts = new ArrayList<>();

        System.out.println(words.getClass().equals(counts.getClass()));
    }
}
~~~

Run:

~~~bash
javac ErasureDemo.java
java ErasureDemo
~~~

Stdout:

~~~text
true
~~~

Both objects are `ArrayList` at runtime. However, **do not conclude that all generic information is erased from all metadata**: generic signatures are stored in certain class/method metadata and reflection can read them. What normally cannot be done from an arbitrary `ArrayList` instance alone is reliably recovering whether the variable pointing to it had type argument `String` or `Integer`.

Practical consequences:

- Do not write **new T()** or **new T[10]** with an ordinary type variable: the runtime has no concrete `Class` of T to instantiate directly. Typically pass a **Supplier<T>**, a **Class<T>**, or a factory when object creation is needed.
- Do not directly create **new List<String>[10]**: arrays check their component type at runtime while this parameterized type is non-reifiable. A collection of collections can be used instead.
- Do not use **List<String>.class** or **instanceof List<String>** to check the type argument of an instance. **List.class** and **instanceof List<?>** are the valid forms in the corresponding situations.
- Do not declare two overloads differing only by **List<String>** and **List<Integer>** at the same parameter position because after erasure they have the same signature.
- An **unchecked** warning is a sign that the compiler cannot prove type safety; do not casually hide it with `@SuppressWarnings` without controlling casts and data sources.

## 12. Common Identification Mistakes and How to Fix Them

**Confusing type parameter with type argument.** In **class Result<T>**, T is declared; in **Result<String>**, `String` is passed in. In **List<T>** appearing inside the declaration of `Result<T>`, T was already declared outside and is acting as an argument to `List`.

**Thinking T is a runtime value.** T is a compile-time type name. It does not hold a corresponding `Class` object; pass a **Class<T>**, `Supplier<T>`, or factory separately when an API requires runtime creation or checking information.

**Using a type variable out of scope.** Writing `static T transform(T x)` in class `Generic<T>` is invalid if T belongs only to the class. Fix it to **static <U> U transform(U x)** or use an instance method with the class's T.

**Confusing a wildcard with a type parameter declaration.** **List<?>** represents a usage form of a list, not a reusable declared name. **<T> void copy(List<T> a, List<T> b)** links two lists of the same type T; whereas **void inspect(List<?> a)** fits when you only need a list of any type.

**Using List<Object> instead of List<?>.** A function that only needs to iterate over any kind of list can take `List<?>`; `List<Object>` will not accept `List<String>`. To operate on a shared element type, consider a generic method or a bounded wildcard.

**Believing the diamond changes type meaning.** **new Box<>()** does not create a raw `Box`; it asks the compiler to infer type arguments from context. **new Box()** is the constructor call through the raw type in that context.

**Ignoring collection mutability.** A type argument describes the element type, not whether the list can be modified. For example, `List.of` returns an unmodifiable list.

**Ignoring unchecked warnings.** An assignment or call through a raw API can compile yet fail late with `ClassCastException`; handle it where data transitions from an untrusted type into a concrete generic type.

## 13. Process for Reading a Generic Signature

When encountering a complex API, read in this order:

1. Find **the type parameter declaration**: for example **<T extends Number>** or **<K, V>**. Identify its scope (class or method) and bounds.
2. Find where the type variable appears in **input parameters, return type, and nested types** to see how the API links those positions.
3. At the call site, identify **the actual type arguments** or the types the compiler will infer.
4. Examine the **full parameterized type** and check invariance and any wildcard upper/lower bounds.
5. Distinguish what **the compiler guarantees** from what needs checking at runtime (erasure, raw types, collection mutability).

Example signature:

~~~java
static <T extends Number> void collect(
        java.util.List<? extends T> input,
        java.util.List<? super T> output) {
    output.addAll(input);
}
~~~

- **<T extends Number>**: declares type parameter T with upper bound `Number`.
- **List<? extends T>**: parameterized type using an upper-bounded wildcard, allowing reading elements guaranteed compatible with T.
- **List<? super T>**: parameterized type using a lower-bounded wildcard, serving as a destination capable of accepting T.
- **T** appearing in the wildcard bounds is the *type variable* declared outside; it is not a new type parameter.
- **output.addAll(input)** is valid because the wildcards and the signature of `addAll` work together to verify the type relationship.

## 14. Self-Check

**Question 1.** In **class Mapper<S, R>**, which part are type parameters? In **Mapper<String, Integer>**, which part are type arguments and which part is the parameterized type?

**Answer:** S and R are type parameters; they create type variables S and R. `String` and `Integer` are type arguments; the whole `Mapper<String, Integer>` is a parameterized type.

**Question 2.** Why does **List<Number> n = new ArrayList<Integer>();** not compile even though `Integer` inherits from `Number`?

**Answer:** `List` is invariant in its type argument; an actual `List<Number>` is needed, or use **List<? extends Number>** if the goal is reading `Number` values from an `Integer` list.

**Question 3.** In **static <T> List<T> singleton(T value)**, what is T in the three positions?

**Answer:** T in **<T>** is the declared type parameter name; T in **List<T>** is a type variable used as the type argument of `List`; T in **(T value)** is a type variable used as the type of parameter `value`. The entire `List<T>` is a parameterized type.

**Question 4.** Which parameter does a method need if it wants to add `Integer` to both `List<Integer>` and `List<Number>`?

**Answer:** **List<? super Integer>**; because both `Integer` and `Number` are supertypes (meaning equal to or broader than) of `Integer`. The method can call `add(Integer)`, but must not assume elements read back are guaranteed to be `Integer`.

**Question 5.** Compare **List**, **List<?>**, and **List<String>**.

**Answer:** `List` is a raw type lacking type arguments and reducing type safety; `List<?>` is a parameterized type with a wildcard for an unknown element type; `List<String>` is a parameterized type with argument `String`, and the compiler checks elements against `String`.

Once you clearly distinguish *parameter declaration*, *type variable name*, *passed-in argument*, and *resulting formed type*, subsequent topics such as generic APIs, type bounds, wildcard variance, and type erasure become much easier to read: they all build on the relationships among these four core components.