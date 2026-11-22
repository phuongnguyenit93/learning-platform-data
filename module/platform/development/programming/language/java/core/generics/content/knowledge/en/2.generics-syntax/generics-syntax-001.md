# Declaring One or More Type Parameters in Java Generics

## 1. Objectives

Java Generics allows declaring a class, interface, record, method, or constructor with **one or more type parameters**. Type parameters are placeholder names for data types that will be chosen when using the API. They help the compiler check the relationship between input values, stored values, and returned results without manual casting.

After this lesson, you will be able to:

- Write the correct **<T>**, **<K, V>**, and **<I, O>** syntax for each kind of declaration.
- Identify which position is a **declaration** of type parameters and which position is **passing type arguments**.
- Distinguish class-level type parameters from type parameters specific to a method or constructor.
- Understand independence, ordering, scope, and basic bounds of multiple type parameters.
- Apply Java 17+ syntax in a compilable, runnable program and avoid common mistakes.

First, compare two declarations:

~~~java
class Box<T> {
    private T value;
}

class Pair<K, V> {
    private K key;
    private V value;
}
~~~

**Box<T>** declares **one** type parameter T. **Pair<K, V>** declares **two** type parameters K and V. A letter such as T, K, or V is only the *name* of a type parameter: it does not represent String, Integer, or any particular class on its own until it appears in a concrete usage context.

## 2. Declaration Grammar: Angle Brackets

Basic form:

~~~text
class ClassName<T> { ... }
class ClassName<K, V> { ... }
interface InterfaceName<I, O> { ... }
record RecordName<A, B>(A first, B second) { ... }

<T> ReturnType methodName(... ) { ... }
<A, B> ReturnType methodName(... ) { ... }
~~~

Syntax rules:

1. The list of type parameters is enclosed in **<...>** and separated by **commas**. There is no trailing comma after the last parameter: **<K, V>** is valid; **<K, V,>** is invalid.
2. Each type parameter name must be a valid Java identifier and is case-sensitive. For example, T and t are two different names, even though convention usually writes T, E, K, and V in uppercase.
3. Within a single list, names must be **distinct**: **<T, T>** is invalid because of duplicate declarations.
4. The angle brackets in a class/interface/record declaration come **immediately after the type name**; the list for a generic method comes **before the return type**; the list for a generic constructor comes **before the constructor name**.
5. You can declare one, two, three, or more type parameters—there is no fixed syntactic limit of just one T; use the exact number needed to express meaningful type relationships.
6. The type parameter list is a **type** declaration, not a value parameter list. For example, the constructor **Pair(K key, V value)** has two value parameters named key and value, whereas **class Pair<K, V>** has two type parameters K and V.

A readable example:

~~~java
class Triple<A, B, C> {
    private final A first;
    private final B second;
    private final C third;

    Triple(A first, B second, C third) {
        this.first = first;
        this.second = second;
        this.third = third;
    }

    A first() { return first; }
    B second() { return second; }
    C third() { return third; }
}
~~~

A, B, and C are three independent type names; they can be assigned the same type or different types at each usage of Triple. Added complexity does not automatically improve API quality: if all attributes always share the same type and role, a single type parameter T may express the design better than three independent names.

## 3. Declaring One Type Parameter for a Class

The most common declaration is **class Box<T>**: one type T is used consistently for the value passed in, stored, and retrieved.

~~~java
class Box<T> {
    private T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    void set(T value) {
        this.value = value;
    }
}
~~~

In **class Box<T>**, T is **declared**. Then:

- **private T value**: a field of type T.
- **Box(T value)**: the constructor's value parameter must have type T.
- **T get()**: a method returning T.
- **void set(T value)**: a method accepting a value of type T.

When using it, we pass a *type argument* into the declared slot:

~~~java
// Illustration inside a method body or block:
Box<String> label = new Box<>("Java");
Box<Integer> counter = new Box<>(10);

String text = label.get();
Integer number = counter.get();
~~~

**String** and **Integer** here are *type arguments*, while **Box<String>** and **Box<Integer>** are *parameterized types*. The class declaration is written only once; the compiler applies its type relationships across many usages.

**new Box<>()** uses the *diamond operator*: the constructor's type argument is inferred from context. The declaration side **class Box<T>** still must explicitly state the name T; you cannot declare a class with **class Box<>**.

In Java, a type parameter defaults to using a reference type. **Box<int>** is an error and requires **Box<Integer>**; **Box<String>**, **Box<int[]>**, and **Box<List<String>>** can all be valid if the types used are properly declared or imported.

## 4. Declaring Multiple Type Parameters for a Class

A **<K, V>** declaration typically describes two types with different roles, such as key and value. Each name is separated by a comma, and each position carries its own meaning.

~~~java
class Entry<K, V> {
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
~~~

When used:

~~~java
// Illustration inside a method body or block:
Entry<String, Integer> age = new Entry<>("Lan", 20);
Entry<Long, Long> interval = new Entry<>(100L, 200L);

String name = age.key();    // K is String
Integer years = age.value(); // V is Integer
~~~

**Positional order** matters very much. With **Entry<String, Integer>**, K corresponds to String and V corresponds to Integer; swapping to **Entry<Integer, String>** produces a different parameterized type in which the roles of the two types are also reversed.

**K and V are not required to be different**. Entry<Long, Long> is completely valid because the two *parameters* K and V are two distinct positions, even though the two *arguments* passed in are both Long.

Multiple type parameters can be nested:

~~~java
class Table<K, V> {
    private java.util.Map<K, java.util.List<V>> rows =
            new java.util.HashMap<>();
}
~~~

In **class Table<K, V>**, only **K and V** are newly declared. The expression **Map<K, List<V>>** is using K and V as type arguments for two existing generic types, Map and List; there is no additional declaration of K/V inside Map or List.

### When to Use One T vs. Multiple Names?

- **Box<T>** fits when all operations are tied to the same value type.
- **Pair<A, B>** fits when you want to carry two values where each side can have its own type.
- **Mapper<I, O>** fits when the input type may differ from the output type.
- **Repository<ID, E>** fits when the identifier key type plays a different role from the entity type.
- **Triple<A, B, C>** should appear only when there are genuinely three distinct type roles to represent.

A design with many type parameters becomes hard to read if users do not understand each name's role. Prefer clear names or API documentation and keep the number of type parameters just right.

## 5. Declaring Type Parameters on Interfaces and Records

Generics are not limited to classes. An interface can declare one or more type parameters:

~~~java
@FunctionalInterface
interface Converter<I, O> {
    O convert(I input);
}
~~~

I represents the input data type; O represents the result type. A concrete usage implementation:

~~~java
// Illustration inside a method body or block:
Converter<String, Integer> parser = Integer::parseInt;
Integer value = parser.convert("42");
~~~

At the interface declaration, I and O are not yet bound to concrete types. When assigned to Converter<String, Integer>, the relationship becomes “takes String, returns Integer”. The convert method does not need to write **<I, O>** itself, because it already has the two type variables from the interface.

Java 17 supports generic records with similar syntax:

~~~java
record Point<X, Y>(X x, Y y) {}
~~~

**Point<X, Y>** declares two type parameters for the record; the components x and y use those names as their types. For example, **Point<Integer, Integer> point = new Point<>(3, 5)** is valid. The record automatically provides the constructor, accessors, equals, hashCode, and toString per the record specification. A generic record does not change how the **<X, Y>** list is declared.

A declaration can add bounds to each parameter (see Section 9), and a generic interface can also be implemented with concrete arguments or by forwarding type variables:

~~~java
class StringLength implements Converter<String, Integer> {
    @Override
    public Integer convert(String input) {
        return input.length();
    }
}

class DelegatingConverter<I, O> implements Converter<I, O> {
    private final Converter<I, O> delegate;

    DelegatingConverter(Converter<I, O> delegate) {
        this.delegate = delegate;
    }

    @Override
    public O convert(I input) {
        return delegate.convert(input);
    }
}
~~~

In StringLength, String and Integer are concrete type arguments. In DelegatingConverter, **<I, O>** is a new declaration belonging to the class, and **implements Converter<I, O>** passes those two type variables as arguments to the interface. The names I and O in the two declarations are not a “global variable”; they are linked through the implements signature.

## 6. Declaring a Generic Method: `<...>` Precedes the Return Type

A generic method declares its own type parameters, regardless of whether its enclosing class is generic. Correct syntax:

~~~java
static <T> T identity(T value) {
    return value;
}

static <A, B> String format(A first, B second) {
    return String.valueOf(first) + " / " + String.valueOf(second);
}

static <T> void show(T value) {
    System.out.println(value);
}
~~~

The component order when declaring a static method is **static → <T> → return type → method name → (value parameters)**. For an instance method, omit static or place modifiers such as public before **<T>**:

~~~java
public <E> E choose(E first, E second) {
    return first;
}
~~~

**<E>** is the type parameter list. The next **E** is the return type; **E first** and **E second** are value parameters of type E.

Here is a very common mistake:

~~~java
// Code illustrating incorrect syntax/context:
static T identity(T value) {
    return value;
}
~~~

If T has not been declared in a valid scope, the compiler cannot find type T. Fix it to **static <T> T identity(T value)**. The **<T>** declaration is required even when the compiler can infer T at the call site.

With multiple type parameters, each name can be attached to different return types or parameters:

~~~java
static <K, V> java.util.Map<K, V> singletonMap(K key, V value) {
    return java.util.Map.of(key, value);
}
~~~

**K** and **V** are declared for the method; Map<K, V> is the return type using those two declared names; K key and V value are the two value parameters. When calling **singletonMap("ready", true)**, the compiler usually infers K as String and V as Boolean.

Method type arguments can be **inferred** or **written explicitly**:

~~~java
// Assuming we are in the same class as the static identity method:
String a = identity("abc");
String b = GenericMethods.<String>identity("abc");
~~~

The call with **<String>** after the class name/dot passes the *method type argument* String; it is not declaring a new type parameter. For the call in this example to compile, the identity method must be declared as static in a class named GenericMethods and be accessible at the call site.

## 7. Declaration Scope: Class Type Parameters vs. Method Type Parameters

Observe a class that has both a class-level type parameter and its own generic methods:

~~~java
class Holder<T> {
    private final T stored;

    Holder(T stored) {
        this.stored = stored;
    }

    T read() {
        return stored;
    }

    <U> U echo(U input) {
        return input;
    }

    static <R> R same(R input) {
        return input;
    }
}
~~~

There are three type variables serving three roles:

- **T** is declared on **Holder<T>**; used in the instance field stored, the constructor, and the instance method read().
- **U** is declared by **<U> U echo(...)**; U is scoped only to the echo method and can be completely different from T.
- **R** is declared by **static <R> R same(...)**; this is the static method's type parameter, not Holder's T.

You cannot directly use a generic class's T in a **static field** or **static method** like this:

~~~java
class Wrong<T> {
    // static T cached;          // Compile-time error
    // static T reuse(T input) { // Compile-time error
    //     return input;
    // }
}
~~~

Reason: static members belong to the single shared Wrong class, whereas usages such as Wrong<String> and Wrong<Integer> are the exact same class at runtime. If you need a generic static method, declare **static <U> U reuse(U input)** yourself. If you need to use the class's T, use an instance method.

A generic class containing an instance method **T read()** does not mean read is a *generic method* declaring a new parameter: read merely **uses** the T already declared by the class. A true generic method has a type parameter list belonging to the **method itself**.

Name scoping also explains why you should not shadow names confusingly. For example, a method **<T> T convert(T x)** inside **class Wrapper<T>** has its own T, which can shadow the class's T within the method's scope. Code may still compile depending on usage, but you should use a different name such as U to avoid misunderstandings about type relationships.

## 8. Generic Constructors with One or More Type Parameters

A constructor can declare its **own** type parameter list, immediately before the constructor name, even when the class is not generic:

~~~java
class Receipt {
    private final String description;

    <T> Receipt(T source) {
        description = String.valueOf(source);
    }

    String description() {
        return description;
    }
}
~~~

Here **<T> Receipt(T source)** is a generic constructor of a non-generic class. T is used only inside the constructor; **Receipt** does not become a parameterized type just because its constructor is generic. Usages like **new Receipt(123)** or **new Receipt("invoice")** are both valid.

A generic class can still have a generic constructor with a type parameter **different** from the class's:

~~~java
class Parsed<T> {
    private final T value;

    <S> Parsed(S raw, java.util.function.Function<S, T> parser) {
        value = parser.apply(raw);
    }

    T get() {
        return value;
    }
}
~~~

For example, **Parsed<Integer> n = new Parsed<>("12", Integer::parseInt)**: the class's **T** is Integer; the constructor's **S** is inferred as String from the raw argument and the method reference. This illustration is placed inside a valid method with the Parsed class present in scope.

With multiple constructor type parameters:

~~~java
class Summary {
    private final String text;

    <A, B> Summary(A left, B right) {
        text = left + " | " + right;
    }

    String text() {
        return text;
    }
}
~~~

In **<A, B> Summary(A left, B right)**, A and B are type parameters *of the constructor*, independent of the fact that Summary is not a generic class. The text() method returns a fixed String.

When you need to preserve type relationships across the **entire state and API** of an object, declare parameters at the class level; when you only need input flexibility for **a single object instantiation**, a generic constructor may fit well. Where you place a type parameter determines the scope in which that name can be used.

## 9. Constraining Each Type Parameter with `extends`

By default, a type parameter without an explicit bound has **Object** as its upper bound. We can restrict the set of type arguments using **extends**.

One bounded parameter:

~~~java
class Metric<T extends Number> {
    private final T number;

    Metric(T number) {
        this.number = number;
    }

    double asDouble() {
        return number.doubleValue();
    }
}
~~~

**T extends Number** requires T to be Number or a subtype of Number. Therefore Metric<Integer> and Metric<Double> are valid, while Metric<String> is invalid. The compiler knows T has the methods of Number, so calling **number.doubleValue()** is checked safely.

Two parameters with separate bounds:

~~~java
class IndexedValue<K extends Comparable<K>, V extends Number> {
    private final K key;
    private final V value;

    IndexedValue(K key, V value) {
        this.key = key;
        this.value = value;
    }

    K key() { return key; }
    V value() { return value; }
}
~~~

**K extends Comparable<K>** is an interface bound for K; **V extends Number** is a class bound for V. Each position must satisfy its respective bound; the same bound is not shared across both parameters.

One parameter with **multiple upper bounds**:

~~~java
static <T extends Number & Comparable<T>> T maximum(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
~~~

The syntax uses **&** to join bounds of *the same T*, while using **commas** to separate *different type parameters*. This is an important distinction to remember:

| Syntax | Meaning |
| --- | --- |
| <A, B> | Declares two independent type parameters A and B |
| <T extends Number> | One parameter T bounded by Number |
| <K extends Comparable<K>, V> | Two parameters; only K has an explicit bound |
| <T extends Number & Comparable<T>> | One T that must satisfy both Number and Comparable<T> |
| <A extends Number, B extends Number> | Two parameters, each bounded by Number |

When both class and interface bounds are present, the class bound, if present, must come before the interface bounds; you cannot declare two different class bounds. Use **extends** for both class bounds and interface bounds—do not write **<T implements Comparable<T>>**. You cannot declare a lower bound with **<T super Number>**; **super** appears in a *wildcard type argument*, such as List<? super Integer>, not in a type parameter declaration.

### Relationships Between Multiple Type Parameters

One parameter can reference another parameter in its bound. For example:

~~~java
class Registry<K, V extends java.io.Serializable> {
    // K has no explicit bound; V must implement Serializable.
}

class DirectedPair<A, B extends A> {
    private final A source;
    private final B detail;

    DirectedPair(A source, B detail) {
        this.source = source;
        this.detail = detail;
    }
}
~~~

In DirectedPair, B must be A or a subtype of A. Such a bound expresses a type relationship checked by the compiler; if no constraint is genuinely needed, using a simple <A, B> will be clearer.

## 10. Complete Runnable Example: One, Two, and Multiple Type Parameters

Save as **GenericDeclarationsDemo.java**. This is a standalone program on Java 17+:

~~~java
public class GenericDeclarationsDemo {
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

    @FunctionalInterface
    interface Converter<I, O> {
        O convert(I input);
    }

    static <T> T first(T left, T right) {
        return left;
    }

    static <A, B> Pair<B, A> swap(Pair<A, B> original) {
        return new Pair<>(original.value(), original.key());
    }

    public static void main(String[] args) {
        Box<String> language = new Box<>("Java");
        Pair<String, Integer> release = new Pair<>("version", 21);

        Pair<Integer, String> swapped = swap(release);
        Converter<String, Integer> parser = Integer::parseInt;

        System.out.println(language.get());
        System.out.println(release.key() + ": " + release.value());
        System.out.println(swapped.key() + " -> " + swapped.value());
        System.out.println(first("left", "right"));
        System.out.println(parser.convert("17") + 4);
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 GenericDeclarationsDemo.java
java GenericDeclarationsDemo
~~~

Exact stdout:

~~~text
Java
version: 21
21 -> version
left
21
~~~

Key points to observe:

1. **Box<T>** declares **one** type parameter. In Box<String>, String is the type argument bound to T.
2. **Pair<K, V>** declares **two** type parameters. Pair<String, Integer> sets K = String, V = Integer.
3. **Converter<I, O>** is an interface with two type parameters serving different roles. Converter<String, Integer> takes a string and returns an Integer.
4. **static <T> T first(...)** declares its own T; it does not depend on Box's T.
5. **static <A, B> Pair<B, A> swap(Pair<A, B> original)** declares A and B to express the relationship between the *input type* and the *output type*. In the call swap(release), the compiler infers A = String, B = Integer; the return type is Pair<Integer, String>.
6. The diamond operator **new Pair<>(...)** relies on the constructor/target type context so there is no need to repeat the type argument list.
7. **Integer::parseInt** is chosen as the implementation of Converter<String, Integer>; the expression **parser.convert("17") + 4** uses unboxing from Integer to int to add 4.

Note: a case like **Pair<String, Integer>** does not generate a new class at runtime for each type combination; generics check type safety primarily at compile time.

## 11. Complete Runnable Example: Bounding Multiple Parameters

Save as **BoundedParametersDemo.java**:

~~~java
public class BoundedParametersDemo {
    static final class NumberPair<A extends Number, B extends Number> {
        private final A left;
        private final B right;

        NumberPair(A left, B right) {
            this.left = left;
            this.right = right;
        }

        double sum() {
            return left.doubleValue() + right.doubleValue();
        }
    }

    static <T extends Number & Comparable<T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        NumberPair<Integer, Double> pair = new NumberPair<>(3, 2.5);
        Integer best = larger(7, 12);

        System.out.println(pair.sum());
        System.out.println(best);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 BoundedParametersDemo.java
java BoundedParametersDemo
~~~

Exact stdout:

~~~text
5.5
12
~~~

In **NumberPair<A extends Number, B extends Number>**, two type parameters have two separately declared bounds. Both Integer and Double are subtypes of Number, so **NumberPair<Integer, Double>** is valid.

In **<T extends Number & Comparable<T>>**, there is only **one** T, but it satisfies two bounds. In the call larger(7, 12), the two int values are boxed into Integer; the inferred type is Integer, which is both a Number and implements Comparable<Integer>. Therefore the compareTo call is valid.

## 12. Where Do Type Parameters Differ from Type Arguments and Wildcards?

When reading angle brackets, always examine the **position where they appear**:

~~~java
class Repository<ID, E> {                  // Type parameter declaration
    java.util.List<E> items;                // E is a type argument of List

    void save(E entity) {}                  // E is the value parameter type
}

// Inside a method body or block:
// Repository<Long, String> repo;             // Long/String are type arguments
// java.util.List<?> unknown;                // ? is a wildcard type argument
~~~

- **<ID, E>** immediately after Repository is the list of declared **type parameters**.
- **List<E>** is a **parameterized type** using the declared E. In the position of List<E>, E acts as the *type argument* for List.
- **Repository<Long, String>** is another parameterized type: Long and String are the two type arguments substituting for ID and E.
- **List<?>** denotes a list with an unknown element type. The **?** symbol does not declare a new name; you cannot use **?** like T, and you cannot declare **class Repository<?>**.

A **type parameter name** can be used as a type in fields, parameters, return types, or nested generic types within valid scope. A **type argument** specifies how a particular generic type is used.

One more contrasting example:

~~~java
static <T> java.util.List<T> singleton(T value) {
    return java.util.List.of(value);
}
~~~

In the signature above, **<T>** is the declaration; **List<T>** is a parameterized type whose argument is the type variable T; **T value** uses T as the type of the value parameter. Having T appear multiple times is how we express that the output element type must relate to the type of the input value.

## 13. Type Parameter Names and Order: Remembering How to Read the Syntax

Type parameter names are **conventions that help convey roles**, not Java keywords. Within a `<...>` list, each name is declared once; at usage sites, type arguments are assigned **by position**. For example, `Pair<String, Integer>` differs from `Pair<Integer, String>` even though both use the same two types, and `Pair<String, String>` is still valid.

| Common Name | Suggested Role |
| --- | --- |
| `T` | General type |
| `E` | Element of a collection |
| `K`, `V` | Key and value |
| `I`, `O` or `R` | Input, output, or result |
| `U`, `S` | Another type distinct from `T` when differentiation is needed |

The names `K` and `V` do not automatically impose bounds or force the two types to differ. Use **the same type variable** when you need to constrain positions to share the same type relationship; use multiple names when the positions are genuinely independent. The lesson on naming conventions examines in detail choosing short symbols vs. descriptive names, scope, and Javadoc; here it suffices to master declaration syntax and type argument ordering.

## 14. Common Compilation Errors

### Forgetting a Comma or Declaring Duplicate Names

~~~java
// Invalid examples, for illustration only:
class Bad<A B> {}       // Missing comma
class Bad2<T, T> {}     // Duplicate declaration of T
class Bad3<K, V,> {}    // Trailing comma
~~~

Fix this to **class Good<A, B> {}** or other lists of unique names.

### Placing the Type Parameter in the Wrong Spot in a Generic Method

~~~java
// Incorrect: the compiler has no declaration of T yet:
class Broken {
    // static T copy(T value) { return value; }
}

// Correct:
class Correct {
    static <T> T copy(T value) {
        return value;
    }
}
~~~

The method's **<T>** must be placed before the return type.

### Assuming Type Parameters Are Runtime Values

~~~java
class Example<T> {
    // T = String;       // Incorrect: T is not a value variable
    // T item = new T(); // Incorrect: cannot directly instantiate a type variable with new
}
~~~

A type variable describes a static type and does not hold a Class<T> object at runtime. When you need to instantiate T, you can pass an appropriate Supplier<T> or factory; when you need to know Class<T>, you must obtain a Class<T> reference from another source.

### Using Raw Types Instead of Full Declarations

~~~java
java.util.List<String> safe = new java.util.ArrayList<>();
java.util.List raw = safe; // Raw type: loses type argument information
~~~

Use **List<String>** when the element type is known or **List<?>** when it is unknown. Raw types can lead to unchecked operations and runtime casting errors.

### Passing the Wrong Number of Type Arguments

~~~java
class Pair<A, B> {}

// Incorrect: Pair<String> supplies only one argument for two parameters.
// Correct: Pair<String, Integer> or Pair<String, String>.
~~~

The number of type arguments must normally match the number of declared parameters. **new Pair<>()** is syntax for inferring type arguments at a constructor call; it does not turn Pair into a generic class with only one parameter.

### Using Primitives Directly

~~~java
// List<int> bad; // Incorrect: int is a primitive type
java.util.List<Integer> good = java.util.List.of(1, 2);
~~~

Generic type arguments require reference types; primitives typically use their corresponding wrappers (int → Integer, long → Long, boolean → Boolean). Arrays of primitives such as **int[]** are reference types and can serve as type arguments, for example List<int[]>.

### Confusing `extends` and `implements` in Bounds

~~~java
// Incorrect: class Bad<T implements Runnable> {}
// Correct:
class Task<T extends Runnable> {
    private final T action;

    Task(T action) {
        this.action = action;
    }

    void run() {
        action.run();
    }
}
~~~

Even though Runnable is an interface, a generic bound still uses the **extends** keyword.

### Assuming a Type Parameter Supports Arbitrary Operators

~~~java
class Numbers<T extends Number> {
    T add(T a, T b) {
        // return a + b; // Incorrect: no general + operator for T
        throw new UnsupportedOperationException("Chưa định nghĩa phép cộng cho T");
    }
}
~~~

The **Number** bound guarantees methods like doubleValue(), not that the **+** operator works directly on type variable T. If the problem requires arithmetic, you must choose appropriate conversions or an operations interface.

### Mixing Up the Order of Two Types and Expecting the Compiler to Swap Them

~~~java
// Assuming class Pair<K,V> and accessors already exist:
Pair<String, Integer> source = new Pair<>("x", 1);
// Pair<Integer, String> wrong = source; // Incorrect: different parameterized type.
~~~

The type Pair<String, Integer> does not automatically become Pair<Integer, String> just because the names K/V are flexible. To swap the two positions, you must create a new value with the two type arguments in the corresponding order.

## 15. Quick Knowledge Check

**Question 1:** Which part declares the two type parameters in **class Pair<K, V>**? What role does **Pair<String, Integer>** play?

**Answer:** **<K, V>** is the declaration list of two type parameters. Pair<String, Integer> is a parameterized type, with String as the type argument for K and Integer for V.

**Question 2:** Why is **class Pair<T, T>** invalid, whereas **Pair<String, String>** is valid?

**Answer:** You cannot declare two type parameters with the same name in the same list; the two type argument positions at a usage site, however, can both be String.

**Question 3:** What is the difference between **class Holder<T> { T get() {...} }** and **static <T> T identity(T value)**?

**Answer:** The T in get() belongs to the scope of class Holder<T>; the get method does not declare a new type parameter. In contrast, identity is a generic method that declares its own T, so it can be used even inside a non-generic class.

**Question 4:** In **<T extends Number & Comparable<T>>**, how many type parameters and how many bounds are there?

**Answer:** One type parameter T, with two bounds: Number and Comparable<T>. The **&** symbol joins bounds, unlike the comma between multiple type parameters.

**Question 5:** When calling **static <A, B> Pair<B, A> swap(Pair<A, B> input)** with Pair<String, Integer>, what is the result type?

**Answer:** Pair<Integer, String>. The compiler infers A = String and B = Integer from input, then substitutes the positions in the return type Pair<B, A>.

**Question 6:** If **Converter<I, O>** takes a String and returns an Integer, how should a variable at the usage site be declared?

**Answer:** **Converter<String, Integer>**. I corresponds to String and O corresponds to Integer, following the exact declaration order.

## 16. Checklist Before Completing a Generic Declaration

Before writing or reviewing a declaration with angle brackets, ask yourself:

1. Do the types really need to be parameterized? Is a single T sufficient, or do roles like K, V or I, O need to be independent?
2. Is the **<...>** list placed in the right position for a class, interface, record, method, or constructor?
3. Are the parameter names unique within the list and easy to understand?
4. Is the type variable used within a valid scope and does it accurately express the type relationships among fields, parameters, and return values?
5. Are the bounds with extends in the right order and genuinely needed?
6. At usage sites, do the type arguments have the right count, correct order, and satisfy the bounds?
7. Have type argument, diamond, wildcard, and raw type syntax been clearly distinguished from **declaration** syntax?

The core point of the syntax is that **<T>** introduces one type name reused in multiple positions; **<K, V>** introduces two independent type names. It is the scope and reuse of these names that determine how the compiler checks relationships between values in a program.
