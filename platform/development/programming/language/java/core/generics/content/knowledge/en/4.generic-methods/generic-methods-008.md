# Designing Cast-Free Object-Creation Methods in Java Generics

## 1. Goal and Motivation

When an API needs to create objects yet callers must repeatedly cast from Object to String, Integer, or a domain type, that is usually a sign that the type relationship between input data and the return value is not clearly expressed. A **generic factory method** (an object-creation method with type parameters) turns that relationship into a contract checked by the compiler.

Compare the designs:

~~~java
// Object-based design, illustrative only:
static Object oldBox(Object value) {
    return value;
}

// At the call site:
String text = (String) oldBox("Java");
~~~

The cast in this example compiles, yet if the actual value is incompatible, the error appears only at runtime. A generic method expresses the "accept T, return T" relationship directly:

~~~java
static <T> T identity(T value) {
    return value;
}

// At the call site:
String text = identity("Java");
~~~

In practice, a factory usually creates **a new object containing T**, such as Box<T>, Pair<K,V>, or a collection, rather than merely returning the input. The key point is that **the result type is described using type parameters and input parameters**, without requiring callers to perform manual casts.

This lesson teaches you to:

- Write the syntax **static <T> Box<T> of(T value)** and distinguish the method's T from the class's T.
- Use type inference (*type inference*) and target typing (*target typing*) to receive results with exact types.
- Create generic objects holding one or more type parameters using constructors and the diamond operator.
- Design factories accepting **Supplier<? extends T>**, **Function<? super S, ? extends T>**, or **Class<T>** when a T value is not already available.
- Distinguish a genuinely type-safe API from a cast hidden behind a generic signature.
- Handle bounds, wildcards, null, generics invariance, and runtime errors that generics cannot prevent on their own.

The complete examples target Java 17 and later, with filenames, compile/run commands, and deterministic stdout.

## 2. What Is a Generic Factory Method?

A factory method is a method that creates or provides objects according to a published contract. When the method **declares one or more type parameters of its own**, we have a generic factory method.

Example of a class storing a value:

~~~java
final class Box<T> {
    private final T value;

    private Box(T value) {
        this.value = value;
    }

    T value() {
        return value;
    }

    static <U> Box<U> of(U value) {
        return new Box<>(value);
    }
}
~~~

Reading the signature **static <U> Box<U> of(U value)**:

1. **<U>** comes before the return type, declaring a type parameter **of the method of**.
2. **Box<U>** is the result type: a Box parameterized by U.
3. **U value** tells the compiler that the input value and Box's type argument share the same relationship U.
4. **new Box<>(value)** invokes the known constructor of Box, using the diamond to infer the type argument. It does **not** create an object of an unknown class named U.
5. The private constructor restricts creating Box from outside the class, making the factory the controlled entry point.

A call:

~~~java
// Illustration inside a method:
Box<String> message = Box.of("hello");
Box<Integer> quantity = Box.of(12);
~~~

The compiler infers U from the arguments and context: message is Box<String>, quantity is Box<Integer>. **No (Box<String>) cast is needed** where the result is received.

A syntax detail: T is the type parameter of **class Box<T>**, while U is the dedicated type parameter of the static method of. A static method cannot directly use the class's T:

~~~java
// Invalid inside a generic class:
static Box<T> of(T value) { ... }
~~~

If T is only declared by Box<T>, a static method must declare its own type parameter, such as **static <U> Box<U> of(U value)**. You can reuse the name T on the static method if you wish (**static <T> Box<T> of(T value)**); that is still the **method's own** T, not the class's T.

## 3. Why Is Returning Object and Casting Dangerous?

An API:

~~~java
static Object createValue(String text) {
    return text;
}
~~~

only guarantees the result is Object. Callers must write **(String) createValue("x")**. If the implementation later returns an Integer while still matching the Object signature, the cast at the caller can throw ClassCastException.

A subtler mistake is "disguising" a cast inside a generic method:

~~~java
@SuppressWarnings("unchecked")
static <T> T unsafeCreate() {
    return (T) "actually a String";
}
~~~

The signature looks generic, yet **there is no input, bound, or factory proving the result belongs to T**. The call **Integer number = unsafeCreate()** can compile and then fail when the String value is checked as an Integer at runtime. The method merely moved an unchecked risk from the caller into the implementation without **creating type safety**.

Design principle: a generic factory returning T or a type containing T needs a **source guaranteeing T**. That source can be a parameter already typed as T, a Supplier<? extends T>, a transformation Function<S,T>, a known constructor of a generic class holding T, or a Class<T> combined with appropriate runtime checking/instantiation.

**You cannot infer and construct an arbitrary instance of T solely from the signature <T> T create()**. A type parameter is a source-code constraint, not a Class object that the JVM automatically supplies to the method.

## 4. Exact Syntax and the Role of Type Inference

Common pattern:

~~~java
static <T> Box<T> box(T value) {
    return new Box<>(value);
}

static <K, V> Pair<K, V> pair(K key, V value) {
    return new Pair<>(key, value);
}
~~~

These declarations assume Box<T> and Pair<K,V> have already been defined with matching constructors. They are not a standalone program; the complete program is in the next section.

Explanation of angle-bracket positions:

| Expression | Role |
|---|---|
| **<T>** before **Box<T>** | Declares a type parameter for the method |
| **Box<T>** as the return type | Uses T as Box's type argument |
| **T value** | Uses type variable T as the type of the value parameter |
| **new Box<>(value)** | Constructor invocation with diamond, inferring the type argument |
| **Box<String> b = box("x")** | Caller receives a parameterized type with String |
| **Factory.<String>box("x")** | Caller explicitly specifies method type argument String |

The compiler inspects the method signature, arguments, bounds, and target type to infer T. With **pair("lang", 21)**, the typical inferred type is Pair<String, Integer>. Boxing converts the int literal to Integer when a reference type argument is required.

Distinguish **generic factory methods** from **constructors**. A constructor has the same name as the class and declares no return type; a static factory has its own name, a return type, and can contain validation, caching, implementation selection, or conversion logic before returning the object.

Not every factory needs to be generic: if a method always creates a StringBuilder with no type relationship to its input, a simple **static StringBuilder createBuilder()** is enough.

## 5. Standalone Runnable Example: Factories for Box<T> and Pair<K,V>

Save as **GenericFactoryDemo.java**:

~~~java
public class GenericFactoryDemo {
    record Box<T>(T value) {}

    record Pair<K, V>(K key, V value) {}

    static <T> Box<T> box(T value) {
        return new Box<>(value);
    }

    static <K, V> Pair<K, V> pair(K key, V value) {
        return new Pair<>(key, value);
    }

    public static void main(String[] args) {
        Box<String> language = box("Java");
        Box<Integer> version = box(21);
        Pair<String, Integer> release = pair("jdk", 17);

        Box<Number> number = GenericFactoryDemo.<Number>box(3);

        System.out.println(language.value());
        System.out.println(version.value());
        System.out.println(release.key() + ":" + release.value());
        System.out.println(number.value());
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac -encoding UTF-8 GenericFactoryDemo.java
java GenericFactoryDemo
~~~

Exact stdout:

~~~text
Java
21
jdk:17
3
~~~

Explanation:

- **record Box<T>** is a generic record. The factory box(T) creates Box<T> without casting.
- **pair(K,V)** connects two independent type arguments accurately into Pair<K,V>; the result's type arguments are not collapsed to Object.
- **Box<String> language** causes calling value() to return static type String; **Box<Integer> version** returns Integer.
- **GenericFactoryDemo.<Number>box(3)** provides an **explicit type witness**: T is chosen as Number, 3 is boxed into Integer and assigned to Number. The actual data inside is still an Integer, while the result's published type is Box<Number>.
- If the type witness is omitted, **Box<Number> number = box(3)** is also a case where the compiler can infer the appropriate type thanks to assignment context. A type witness is useful when you want to explicitly state a type choice rather than relying completely on inference.

Here, the record and method names serve only as examples. An API can pick clearer names such as **of**, **from**, **create**, **empty**, **copyOf**, or **parse**, depending on each factory's semantics.

## 6. Using a Static Method to Create an Instance of a Generic Class

A common pattern is placing the factory method directly inside the class:

~~~java
final class Envelope<T> {
    private final T content;

    private Envelope(T content) {
        this.content = content;
    }

    public T content() {
        return content;
    }

    public static <U> Envelope<U> of(U content) {
        return new Envelope<>(content);
    }
}
~~~

Callers can write:

~~~java
// Illustration inside a method body:
Envelope<String> text = Envelope.of("hello");
Envelope<Integer> count = Envelope.of(8);
~~~

This is a **static generic factory method**. It avoids calling **new Envelope<String>(...)** directly, keeps instantiation centralized, and can validate data:

~~~java
public static <U> Envelope<U> nonNull(U content) {
    return new Envelope<>(java.util.Objects.requireNonNull(content, "content"));
}
~~~

The nonNull version differs only in its null contract. It still neither casts nor loses U. **Objects.requireNonNull** has a generic overload that preserves the parameter's static type.

If you want to allow null, a factory **ofNullable** can be named and designed separately; however, do not infer solely from the name that every factory returns Optional<T>. For a factory returning Envelope<U> itself, the name, return type, and contract must be consistent.

When a constructor needs strict validation or implementation selection, a static factory is usually more helpful than simply exposing a constructor. Still, a factory does not automatically make every object immutable or thread-safe; those properties depend on object structure, fields, and implementation.

## 7. Multiple Type Parameters: From Input Data to Result Object

A generic factory can declare multiple type parameters to represent multiple roles:

~~~java
record Entry<K, V>(K key, V value) {}

static <K, V> Entry<K, V> entry(K key, V value) {
    return new Entry<>(key, value);
}
~~~

Caller:

~~~java
// Illustration:
Entry<String, Integer> e = entry("age", 20);
Entry<Long, String> other = entry(5L, "value");
~~~

K and V are inferred separately. For e, K is String and V is Integer; for other, K is Long and V is String. No cast is needed in the returning method or at the caller.

Input/output type parameters can be used:

~~~java
static <I, O> O convert(I input,
                         java.util.function.Function<? super I, ? extends O> mapper) {
    return mapper.apply(input);
}
~~~

**Function<? super I, ? extends O>** lets the transformer accept I or a wider type than I, and return O or a subtype of O. This is a useful form of variance so the factory/converter does not force callers to write lambdas matching only one exact type.

In a call:

~~~java
// Illustration inside a method:
Integer length = convert("Java", String::length);
~~~

The compiler infers I = String and O compatible with Integer; String::length returns int and is boxed to Integer inside Function.

When designing, ask yourself **where each type parameter appears**. If a method declares <T> yet T cannot connect to any input parameter, target type, or real creation source, that is a sign the signature may create a false sense of safety.

## 8. Using Supplier When the Factory Must Create T Without an Existing T Value

Sometimes callers want a method to create a new object instead of wrapping an existing one. Java does not allow writing **new T()** with a type variable T because concrete constructor information cannot be inferred from T at runtime. Instead, the caller supplies a **Supplier** that creates the object.

~~~java
static <T> T create(java.util.function.Supplier<? extends T> supplier) {
    return supplier.get();
}
~~~

Internally, the compiler knows **supplier.get()** returns T or a subtype of T, so it is assignable to T. Users can pass a constructor reference:

~~~java
// Illustration:
StringBuilder builder = create(StringBuilder::new);
~~~

No cast. The static type of the result is established through Supplier and the target-type context. This approach also avoids requiring every T to have a public no-arg constructor.

You can add runtime conditions:

~~~java
static <T> T createNonNull(
        java.util.function.Supplier<? extends T> supplier) {
    java.util.Objects.requireNonNull(supplier, "supplier");
    return java.util.Objects.requireNonNull(supplier.get(), "created object");
}
~~~

The factory here guarantees non-null **after the function succeeds**; it does not guarantee that the constructor reference/lambda will not throw an exception, will create a fresh object on each call, or has no side effects. Those depend on the Supplier provided by the caller.

## 9. Standalone Runnable Example: Supplier and Function

Save as **SupplierFactoryDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;
import java.util.function.Supplier;

public class SupplierFactoryDemo {
    interface Animal {
        String sound();
    }

    static final class Dog implements Animal {
        @Override
        public String sound() {
            return "woof";
        }
    }

    static <T> T create(Supplier<? extends T> supplier) {
        Objects.requireNonNull(supplier, "supplier");
        return Objects.requireNonNull(supplier.get(), "result");
    }

    static <T> List<T> createMany(int count, Supplier<? extends T> supplier) {
        if (count < 0) {
            throw new IllegalArgumentException("Negative count");
        }
        List<T> result = new ArrayList<>();
        for (int i = 0; i < count; i++) {
            result.add(create(supplier));
        }
        return result;
    }

    static <S, T> T convert(S source,
                            Function<? super S, ? extends T> mapper) {
        return Objects.requireNonNull(mapper, "mapper").apply(source);
    }

    public static void main(String[] args) {
        Animal first = create(Dog::new);
        List<Animal> group = createMany(2, Dog::new);
        Integer length = convert("Java", String::length);

        System.out.println(first.sound());
        System.out.println(group.size());
        System.out.println(group.get(0).sound());
        System.out.println(length);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 SupplierFactoryDemo.java
java SupplierFactoryDemo
~~~

Stdout:

~~~text
woof
2
woof
4
~~~

Points to observe:

1. **Dog::new** is a constructor reference; it provides a way to create a Dog. The create method neither knows nor needs new T().
2. **Animal first** is assigned from a factory using Supplier<Dog>. The generic bound **? extends T** allows the result to be a subtype of the target type.
3. **List<Animal> group = createMany(2, Dog::new)** keeps the published element type as Animal even though the created objects are Dog.
4. **convert("Java", String::length)** links source type String and result type Integer; no **(Integer)** or **(String)** cast is needed at the conversion site.
5. createMany() rejects negative counts; this validation belongs to the factory contract, not determined by generics.
6. A Supplier could return null; create checks and rejects that case. Function in convert does not check whether the result value is null, so the method only promises the static type rather than implicitly guaranteeing non-null.

To build a production-grade API, clearly specify whether the factory creates a fresh instance every time or may reuse instances, whether null is accepted, and which checked/unchecked exceptions can escape.

## 10. Using Class<T> When Runtime Creation or Type Checking Is Needed

There are situations where you need the concrete class to instantiate or verify an Object. **Class<T>** is a *type token* with a generic relationship to T.

When you need to check whether an Object has the expected type:

~~~java
static <T> T checked(Object source, Class<T> type) {
    return type.cast(source);
}
~~~

**Class.cast** performs a runtime cast check based on the class token. Caller:

~~~java
// Illustration:
String label = checked("Java", String.class);
Integer answer = checked(42, Integer.class);
~~~

Here there is no cast at the caller and no unchecked cast inside the method. If source is not a compatible instance, **type.cast(source)** throws ClassCastException. Note that **Class.cast(null)** returns null; it is not a non-null check.

A form that creates objects via reflection:

~~~java
static <T> T construct(Class<T> type)
        throws ReflectiveOperationException {
    return type.getDeclaredConstructor().newInstance();
}
~~~

The method uses Class<T> to find a no-argument constructor and invoke it. It works only if an appropriate constructor is accessible in the runtime context; not every T has a no-arg constructor. Reflection can throw exceptions related to constructors, access, or instantiation. In simple cases with a known constructor, **Supplier<T>** is usually clearer and easier to test than reflection.

**Class<T> does not fully recover nested type arguments**: at runtime, **List<String>** and **List<Integer>** can be the same ArrayList class. There is no **List<String>.class** class literal. If you need to describe complex types at runtime, you must use a dedicated type-token/Type mechanism and appropriate validation process, beyond what Class<T> alone guarantees.

## 11. Standalone Runnable Example: Type Tokens and Cast-Free Instantiation

Save as **ClassTokenFactoryDemo.java**:

~~~java
public class ClassTokenFactoryDemo {
    static <T> T checked(Object value, Class<T> type) {
        return type.cast(value);
    }

    static <T> T construct(Class<T> type)
            throws ReflectiveOperationException {
        return type.getDeclaredConstructor().newInstance();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        String language = checked("Java", String.class);
        System.out.println(language);

        try {
            Integer invalid = checked("not an integer", Integer.class);
            System.out.println(invalid);
        } catch (ClassCastException exception) {
            System.out.println("type mismatch");
        }

        StringBuilder builder = construct(StringBuilder.class);
        builder.append("created");
        System.out.println(builder);
    }
}
~~~

Compile/run commands:

~~~bash
javac -encoding UTF-8 ClassTokenFactoryDemo.java
java ClassTokenFactoryDemo
~~~

Stdout:

~~~text
Java
type mismatch
created
~~~

Explanation:

- **checked("Java", String.class)** returns String; the relationship between Class<String> and return type T is verified by the compiler.
- **checked("not an integer", Integer.class)** compiles, yet Class.cast detects the type mismatch at runtime. The program catches ClassCastException and prints a fixed message.
- **construct(StringBuilder.class)** works because StringBuilder has an accessible no-argument constructor; return type StringBuilder is inferred from Class<StringBuilder>.
- Reflection may not work if the class is abstract, an interface, lacks a no-arg constructor, has an inaccessible constructor, or its constructor throws an exception. It is not a magical factory capable of creating "any T".

Type tokens are useful when input data initially only has type Object (e.g., plugin systems, runtime parsers, reflection integration) and needs safe verification. For data that already has full generic types at compile time, prefer preserving type relationships from the start instead of widening to Object and re-checking later.

## 12. Distinguishing a Factory Returning T from a Factory Returning Container<T>

Two signatures look similar yet have different capabilities:

~~~java
static <T> T create(Supplier<? extends T> supplier) {
    return supplier.get();
}

static <T> Box<T> wrap(T value) {
    return new Box<>(value);
}
~~~

**create** requires a source that produces T itself (Supplier). It cannot do new T() from the signature alone. **wrap** can use new Box<>(...) because class Box is a known type with a matching constructor; T only determines *the element type inside Box*.

A common mistake:

~~~java
// Intentionally invalid, does not compile:
static <T> T impossible() {
    // return new T();
    return null;
}
~~~

The return null line compiles, yet it is not a useful factory and creates no object. The **new T()** part is commented out because Java forbids directly instantiating a type variable. The real design question is *which source guarantees the returned value is actually a T?*

A generic factory can also return an interface for a concrete implementation:

~~~java
interface Repository<ID, E> {
    E find(ID id);
}

class MapRepository<ID, E> implements Repository<ID, E> {
    private final java.util.Map<ID, E> values;

    MapRepository(java.util.Map<ID, E> values) {
        this.values = values;
    }

    @Override
    public E find(ID id) {
        return values.get(id);
    }
}

class RepositoryFactory {
    static <ID, E> Repository<ID, E> fromMap(
            java.util.Map<ID, E> data) {
        return new MapRepository<>(data);
    }
}
~~~

The factory publishes **Repository<ID,E>** instead of the concrete class **MapRepository<ID,E>**. Callers can program against the interface with exact type arguments, without needing casts between implementation and interface. Note that Map.get can return null when a key is missing, so a type-safe relationship does not mean non-null.

## 13. Target Typing and Calling a Method with Explicit Type Arguments

Normally the compiler infers type arguments from method arguments and target type:

~~~java
static <T> java.util.List<T> one(T element) {
    return java.util.List.of(element);
}
~~~

Inside a method:

~~~java
java.util.List<String> names = one("An");
java.util.List<Number> amounts = one(3);
~~~

The compiler can use both the input expression's type and the target type List<Number> to pick an appropriate T. This does not mean runtime changed the actual type of the number 3: boxing creates an Integer and that value can be viewed as Number.

When you want to state the type argument explicitly, use an **explicit method type argument** after the dot:

~~~java
java.util.List<Number> amounts = SomeFactories.<Number>one(3);
~~~

The snippet above is an illustration assuming method **one** is accessible in class SomeFactories. Writing **<Number>** does not declare a new parameter; it merely selects T at the call site.

### When Using var

~~~java
var words = java.util.List.of("A", "B");
var numbers = java.util.List.of(1, 2);
~~~

The compiler infers the static type from the initializer. In this example, words is List<String> and numbers is List<Integer>. Using var does not bypass generic type safety.

For a factory with no parameter supplying the type, pay attention to context:

~~~java
static <T> java.util.List<T> emptyMutableList() {
    return new java.util.ArrayList<>();
}
~~~

Usages:

~~~java
java.util.List<String> names = emptyMutableList();
var unknown = emptyMutableList();
~~~

In the first case, the target type helps infer T as String. In the var case, without another input/target constraint, the compiler typically infers the upper bound Object for T, so unknown has type List<Object>. That is why target typing can change inference outcomes; APIs must be read alongside their context.

Do not try to patch an API with broken type relationships using casts: if callers must write **(List<String>)**, first check whether the generic signature properly links input and output.

## 14. Collection-Creating Factories: Preserving Element Types and Handling Variance

Collection-copying factories are a practical example of methods using type parameter T and wildcards.

~~~java
static <T> java.util.List<T> mutableCopy(
        java.util.Collection<? extends T> source) {
    return new java.util.ArrayList<>(source);
}
~~~

**Collection<? extends T>** allows reading elements of T or a subtype of T. For example, if source is List<Integer>, the caller can request a List<Number> result. **ArrayList<>(source)** has a constructor taking a compatible collection and creating a new list.

If the method accepted **Collection<T>** instead of **Collection<? extends T>**, it would be less flexible when converting subtype elements into a collection of a supertype. Even though Integer extends Number, **List<Integer> is not a List<Number>** due to invariant generics.

For a structurally unmodifiable copy, you can use **List.copyOf**:

~~~java
static <T> java.util.List<T> immutableCopy(
        java.util.Collection<? extends T> source) {
    return java.util.List.copyOf(source);
}
~~~

**List.copyOf** creates or reuses an appropriate unmodifiable list; it rejects null elements. If you need a snapshot guaranteed independent of source mutations, check the specific contract of the factory and source object rather than guessing solely from the name "copy". Unmodifiable does not mean the element objects inside become immutable.

## 15. Standalone Runnable Example: Type-Safe Collection Copying

Save as **CollectionFactoryDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

public class CollectionFactoryDemo {
    static <T> List<T> mutableCopy(Collection<? extends T> source) {
        return new ArrayList<>(source);
    }

    static <T> List<T> immutableCopy(Collection<? extends T> source) {
        return List.copyOf(source);
    }

    public static void main(String[] args) {
        List<Integer> source = List.of(1, 2);
        List<Number> numbers = mutableCopy(source);
        numbers.add(3.5);

        List<Number> fixed = immutableCopy(source);

        System.out.println(numbers);
        System.out.println(fixed);
        System.out.println(source);
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 CollectionFactoryDemo.java
java CollectionFactoryDemo
~~~

Stdout:

~~~text
[1, 2, 3.5]
[1, 2]
[1, 2]
~~~

**Points to verify:** source has type List<Integer>, yet both mutableCopy and immutableCopy can return List<Number> thanks to the generic signature and assignment context. There are no unchecked casts. **numbers.add(3.5)** is valid because numbers is declared as List<Number>; source still contains only 1, 2. The fixed list created by List.copyOf does not permit adding elements, even though it also has static type List<Number>.

### Null and Collection Factories

**new ArrayList<>(source)** accepts null elements if the source collection contains null; however, **List.copyOf(source)** throws NullPointerException when the source is null or contains a null element. Do not assume every generic factory has the same null policy. Method names, contracts, and API documentation must state this clearly.

**Collections.emptyList()** and **List.of()** are standard generic factory examples returning empty collections. They can infer the element type from the target type:

~~~java
java.util.List<String> emptyA = java.util.Collections.emptyList();
java.util.List<Integer> emptyB = java.util.List.of();
~~~

Both are valid without casts. However, the list returned by List.of does not allow structural modifications, so pick the factory matching your mutability requirements.

## 16. Bounded Factories: Constraining Input Types to Exact Needs

A factory sometimes needs a specific API on T. If the method merely places a T value into Box<T>, no bound is usually needed. If it needs Number.doubleValue() or Comparable.compareTo(), declare a bound:

~~~java
record Measured<T extends Number>(T original, double amount) {}

static <T extends Number> Measured<T> measured(T number) {
    return new Measured<>(number, number.doubleValue());
}
~~~

With **measured(12)**, T is inferred as Integer and the result is Measured<Integer>. **measured("12")** is invalid because String is not a subtype of Number.

Multiple bounds:

~~~java
static <T extends Number & Comparable<T>> T greater(T left, T right) {
    return left.compareTo(right) >= 0 ? left : right;
}
~~~

The **&** joins the class bound Number with the interface bound Comparable<T>; the compiler permits calling compareTo, which an unbounded T does not guarantee.

When a method needs to compare under multiple strategies, it can **accept Comparator<? super T>** instead of requiring T to implement Comparable<T>:

~~~java
static <T> T choose(
        T left, T right, java.util.Comparator<? super T> comparator) {
    return comparator.compare(left, right) >= 0 ? left : right;
}
~~~

Comparator supplies comparison logic via an explicit argument. This allows the factory/selection method to work with types lacking natural ordering. Thanks to type parameter T, the result keeps its relationship to the chosen arguments' type without casting.

### Bounds in Factories Returning an Interface

A factory can hide the implementation while still enforcing bounds:

~~~java
interface SortedHolder<T> {
    T greatest();
}

class SingleSortedHolder<T extends Comparable<? super T>>
        implements SortedHolder<T> {
    private final T value;

    SingleSortedHolder(T value) {
        this.value = value;
    }

    @Override
    public T greatest() {
        return value;
    }
}

class SortedHolders {
    static <T extends Comparable<? super T>> SortedHolder<T> of(T value) {
        return new SingleSortedHolder<>(value);
    }
}
~~~

The method's bound suffices so the implementation class/constructor can be instantiated with the exact T. Returning **SortedHolder<T>** lets callers depend on the interface contract. For null values, code can still construct a holder if the constructor allows it; a Comparable bound does not automatically forbid null.

## 17. Well-Designed APIs Have No Unchecked Casts

A generic method preserves type relationships best when **its body also has compiler-verified type evidence**. Examples:

~~~java
static <T> java.util.Optional<T> optional(T value) {
    return java.util.Optional.ofNullable(value);
}

static <T> java.util.List<T> singleton(T value) {
    return java.util.List.of(value);
}

static <K, V> java.util.Map<K, V> singletonMap(K key, V value) {
    return java.util.Map.of(key, value);
}
~~~

None of these methods contain **(T)** or **@SuppressWarnings("unchecked")**. The compiler knows:

- **Optional.ofNullable** returns Optional<T> matching the input value; given null, it returns Optional.empty().
- **List.of(value)** returns a single-element list with the corresponding type argument, and **rejects null**.
- **Map.of(key, value)** returns a structurally unmodifiable map with type arguments K,V; null keys/values are rejected.

What matters is that not every factory handles null identically. State the contract clearly when naming the method and choosing the implementation.

The following method still lacks type evidence:

~~~java
// Anti-pattern; illustrative only:
@SuppressWarnings("unchecked")
static <T> java.util.List<T> unsoundList() {
    return (java.util.List<T>) (java.util.List<?>) java.util.List.of("A");
}
~~~

If a caller assigns it to List<Integer>, the String data inside can cause ClassCastException when retrieving an element as Integer. The method merely hid an unchecked cast without converting String to Integer.

A runtime-checked cast such as **Class<T>.cast** is a different case: it uses a class token to verify compatibility at runtime and throws an exception if invalid. However, Class<T> is insufficient to verify arbitrary nested parameterized types due to erasure.

## 18. A Domain Example: Typed Response Factory

Suppose an application needs to wrap data and status into a common result. A generic record is a concise choice:

~~~java
record Response<T>(boolean success, T data, String message) {}

class Responses {
    static <T> Response<T> success(T data) {
        return new Response<>(true, data, "OK");
    }

    static <T> Response<T> failure(String message) {
        return new Response<>(false, null, message);
    }
}
~~~

With success(data), the compiler infers T from data. With failure(message), there is no T input, so the **target type** or a type witness plays a key role:

~~~java
// Illustration inside a method:
Response<String> one = Responses.success("saved");
Response<String> two = Responses.failure("not found");
Response<Integer> three = Responses.<Integer>failure("invalid");
~~~

The signature **failure(String message)** can return Response<T> with data = null, because null is assignable to any reference type T. It **does not fabricate a T**, and the contract should clearly state that data is absent when success = false. Such an API expresses the type relationship on the result without forcing callers to cast.

A design question is whether to allow **success(null)**. If success means "data is present", you can use Objects.requireNonNull(data) when creating Response. If null is a valid state, express the condition clearly and avoid conflating null with failure. Generics do not decide this business policy.

## 19. Type Inference Does Not Replace API Design Review

A factory may compile yet still mislead callers:

~~~java
static <T> T fallback(T preferred, T alternative) {
    return preferred != null ? preferred : alternative;
}
~~~

The method has type parameter T linking both arguments to the return type. Yet a caller can pass **String** and **Integer**, causing the compiler to infer a common supertype. Then the result type is not necessarily the concrete type the author expected.

Safe example:

~~~java
String name = fallback(null, "anonymous");
~~~

Example worth reconsidering intent:

~~~java
Object mixed = fallback("text", 123);
~~~

Java can pick an appropriate common type so the result is assignable to Object. This is not a type-safety violation; it merely shows that **a generic method does not guarantee the two runtime arguments have the same class**. If domain rules require stricter type equality, design a tighter contract/input and add boundary validation if needed.

Nor should you assume **var result = factory(...)** always yields the desired type. The inferred type depends on the initializer; for factories with only a return-type T and no input type information, an explicit target type can make the result clearer.

## 20. Null, Exceptions, and Mutability in Object-Creation Methods

**Type safety** and **runtime policy** are two independent dimensions. A generic factory can validly return Box<String> while still holding null; a properly typed List<Integer> may forbid add; a Supplier<T> may throw an exception.

You should explicitly decide the following contracts during design:

| Question | Approach |
|---|---|
| Is a null input valid? | Use requireNonNull or allow and document clearly |
| Can the factory return null? | Consider avoiding null or document clearly; Optional when appropriate |
| Create a fresh object every time? | Document if required; factory may cache or reuse |
| Does the constructor have side effects? | Supplier and reflection can execute constructor logic |
| Is the result mutable? | Determined by type/implementation, not by T |
| Are there checked exceptions in reflection? | Declare/handle ReflectiveOperationException appropriately |
| Is runtime type checking needed? | Class<T>.cast when checking a concrete class; understand erasure limits |
| Which type is returned? | Signature should keep type parameters linked to inputs/result |

Example API accepting Supplier while forbidding null results:

~~~java
static <T> T newRequired(java.util.function.Supplier<? extends T> factory) {
    java.util.Objects.requireNonNull(factory, "factory");
    return java.util.Objects.requireNonNull(factory.get(), "factory returned null");
}
~~~

If factory.get() creates a valid object, the return type preserves T; if it returns null, the method throws NPE with the declared message. This is an enforcement implemented by runtime code, not an automatic property of <T> syntax.

With Optional.ofNullable, null is encoded as Optional.empty() instead of throwing. The two approaches have different contracts; no single rule applies to every factory.

## 21. How to Read and Build a Generic Factory Method

When faced with a requirement to "create objects without casting", follow this sequence:

1. **Identify the result to be created.** Is it T itself, a Box<T>, a List<T>, Pair<K,V>, a Repository<K,V> interface, or a typed response?
2. **Find the source guaranteeing type arguments.** An input value T, Supplier<T>, Function<S,T>, a source collection, a Class<T> type token, or an existing implementation?
3. **Declare type parameters in the right place.** For static methods: **static <T> ReturnType method(...)**. If multiple independent type relationships exist, declare <K,V> or <S,T>.
4. **Bind type variables into input and output signatures.** For example, <T> Box<T> of(T value) or <S,T> T map(S source, Function<? super S, ? extends T> mapper).
5. **Write an implementation whose types the compiler can prove on its own.** Use new Box<>(value), supplier.get(), function.apply(), Class.cast, etc. Avoid unchecked casts or raw types.
6. **Test calls against concrete target types.** Assign to Box<String>, Box<Integer>, List<Number>, etc., and verify the compiler checks them.
7. **Specify runtime policies.** Null handling, mutability, instance creation count, exceptions, and reflection limits.
8. **Specify type arguments explicitly when needed.** Use TypeName.<T>method(...) or an explicit target variable if inference does not express intent.

A signature should let readers immediately see what is guaranteed. For example, **<T> Box<T> of(T value)** directly states that Box holds the same type as value. **<T> T create()** with no source of T should appear only when the implementation has a real mechanism guaranteeing the returned type; otherwise, add an appropriate Supplier or Class token.

## 22. Common Mistakes

### Mistake 1 — Forgetting to Declare <T> on a Static Factory

~~~java
class BadBox<T> {
    // Invalid: static method cannot directly use the class's T.
    // static BadBox<T> of(T value) { return new BadBox<>(); }
}
~~~

Fix it to **static <U> BadBox<U> of(U value)** with the matching constructor signature. The class's T is not in scope for a static context in that way.

### Mistake 2 — Believing Return Type T Permits new T()

~~~java
// Invalid, illustrative only:
static <T> T create() {
    // return new T();
    return null;
}
~~~

Type erasure means T does not supply a concrete constructor. Use Supplier<? extends T> or Class<T> with conditional reflection, depending on the contract.

### Mistake 3 — Hiding a Cast with @SuppressWarnings("unchecked")

~~~java
@SuppressWarnings("unchecked")
static <T> T misleading(Object value) {
    return (T) value;
}
~~~

This is simply a cast unverified by the compiler. Callers can still request a T incompatible with the object, leading to runtime failure. If the target type needs checking, accept **Class<T>** and use **type.cast(value)**.

### Mistake 4 — Returning Object Instead of Preserving the Type Parameter

~~~java
static Object wrap(Object input) {
    return input;
}
~~~

This method loses the type relationship callers need. If the requirement is to preserve the input type as the return type, use **static <T> T identity(T input)** or a container with **<T> Box<T> of(T input)**.

### Mistake 5 — Using Raw Types Inside a Factory

~~~java
// Discouraged:
static <T> java.util.List<T> broken() {
    java.util.List raw = new java.util.ArrayList();
    // return raw; // Unchecked conversion.
    return new java.util.ArrayList<>();
}
~~~

Raw types weaken type safety. Declare **List<T> result = new ArrayList<>()** directly, or create and return new ArrayList<T>() with proper type relationships.

### Mistake 6 — Equating Generic Type with Collection Mutability

**List<T>** only states the element type. **List.of(...)** returns an unmodifiable list; **new ArrayList<>(...)** returns a mutable list. A factory must choose the right implementation for the need, not rely solely on the symbol T.

### Mistake 7 — Forgetting Null Checks

**List.of(value)**, **Map.of(key,value)**, and **List.copyOf(source)** can throw NPE on null per their contracts. Meanwhile, **Optional.ofNullable(value)** intentionally accepts null. Callers cannot deduce null policy from type parameter T alone.

### Mistake 8 — Confusing Class<T> with Full Nested Type Verification

**Class<List<String>>** has no corresponding class literal; normally only **List.class** exists carrying raw class information. Class<T>.cast checks the runtime class, not the String element type of an arbitrary List.

### Mistake 9 — Writing Wildcards in an Unresolved Type-Parameter Position

Wildcards are used at generic type use sites, such as **List<? extends Number>**, and have their own read/write rules. Do not declare a method as **static <?> ...** instead of **static <T> ...**. To name a relationship between input and result, declare a type parameter T.

### Mistake 10 — Overusing One T for Two Unrelated Roles

If a factory takes source type S and returns target type T after a transformation, using **<S,T>** is usually clearer than forcing both sides to share one T. For example, **<S,T> T convert(S value, Function<? super S, ? extends T> mapper)** accurately expresses a cross-type conversion.

## 23. Self-Check

**Question 1.** In **static <T> Box<T> of(T value)**, what roles do the first <T>, Box<T>, and T value play?

**Answer:** <T> declares the method's type parameter; Box<T> uses T as the type argument of the returned container; T value is a value parameter of type T. The signature links the type of value and the element type of Box.

**Question 2.** Why can **String text = Box.of("Java").value()** work without a cast?

**Answer:** The compiler infers the type argument of the generic factory and Box from the "Java" argument and context, so value() has static type String. It is not an unchecked conversion from Object.

**Question 3.** Why is **static <T> T create() { return new T(); }** invalid?

**Answer:** Java does not allow instantiating a type variable with new T() due to type erasure and because no constructor is guaranteed for every T. You need a creation source such as Supplier<T> or Class<T> with appropriate instantiation preconditions.

**Question 4.** What is the difference between **Supplier<T>** and **Class<T>** for a factory?

**Answer:** Supplier provides a caller-specified behavior to create T; Class<T> carries a runtime class token usable for cast checks or reflection. Both have their own limits/contracts; Class<T> cannot verify nested type arguments on its own.

**Question 5.** In **static <K,V> Pair<K,V> pair(K k,V v)**, what type is typically inferred for pair("x", 1)?

**Answer:** Pair<String, Integer>, because the literal 1 is boxed into Integer.

**Question 6.** Why does **@SuppressWarnings("unchecked")** not automatically make a T-returning factory type-safe?

**Answer:** The annotation only hides the warning; an unproven cast can fail at runtime. A safe factory needs a genuine type relationship between its inputs/creation source and its result.

**Question 7.** Why can **mutableCopy(Collection<? extends T>)** help create a List<Number> from a List<Integer>?

**Answer:** The upper-bounded wildcard allows the source collection to contain T or a subtype of T; the ArrayList constructor copies elements into a list whose result type T is inferred by the compiler from context.

**Question 8.** Does **List.copyOf** share the same null and mutability contract as **new ArrayList<>(source)**?

**Answer:** No. List.copyOf returns an unmodifiable list and rejects null elements. A new ArrayList can contain null and allows structural modifications.

**Question 9.** Given **static <T> Response<T> failure(String message)** storing only null in data, how can it be assigned to Response<String>?

**Answer:** Use **Response<String> r = Responses.failure("error")** via target typing, or **Responses.<String>failure("error")**. The factory does not create a String; it creates a Response parameterized with the desired type and null data.

**Question 10.** When should you keep the return type as a generic interface instead of an implementation class?

**Answer:** When callers only need the interface contract and you may change the implementation later. For example, **Repository<K,V> fromMap(Map<K,V>)** preserves full type arguments without tying callers to MapRepository.

## 24. Core Takeaways

A **type-safe** generic factory method does not just have **<T>** in its signature; it must have a way to verify or create an object compatible with T. The forms **<T> Box<T> of(T value)**, **<T> T create(Supplier<? extends T>)**, **<S,T> T convert(S, Function<? super S,? extends T>)**, and **<T> T checked(Object, Class<T>)** demonstrate four ways to preserve or establish type relationships without requiring callers to cast.

Prefer letting the compiler prove most relationships from the signature and implementation; use runtime checks only when data genuinely originates outside the type system (such as Object from an untrusted source). Define null, exception, mutability, and object-lifecycle policies separately. With that design, callers immediately see what type the result carries, and type mismatches are caught early rather than hidden inside an unchecked cast.