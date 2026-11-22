# Generic Classes and the Purpose of Type Parameterization in Java

> **Module:** Java Core – class/object  
> **Group:** Generic classes  
> **Focus topic:** Generic classes and the purpose of type parameterization  
> **Version:** Java 17+ (generics have existed since Java 5; the content applies to modern Java).

## 1. Core Problem: One Structure, Multiple Data Types, Yet Still Type-Checked

Suppose an application needs a box to hold data. The box may hold a `String`, an `Integer`, a `User` object, or a custom data type in the future.

If each type must have its own class:

~~~java
class StringBox {
    private String value;

    StringBox(String value) {
        this.value = value;
    }

    String get() {
        return value;
    }
}

class IntegerBox {
    private Integer value;

    IntegerBox(Integer value) {
        this.value = value;
    }

    Integer get() {
        return value;
    }
}
~~~

these are two **class fragments** with the same logic, differing in field type, constructor parameter, and return type. That approach causes duplication and is error-prone during maintenance.

An older approach is using `Object`:

~~~java
class ObjectBox {
    private Object value;

    ObjectBox(Object value) {
        this.value = value;
    }

    Object get() {
        return value;
    }
}
~~~

ObjectBox can hold many kinds of reference values, but the compiler does not know whether the expected value is `String` or `Integer`. The caller must cast and may encounter a `ClassCastException` at runtime.

A **generic class** solves this by **parameterizing data types**:

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

Now:

~~~java
Box<String> message = new Box<>("Hello");
String text = message.get();

Box<Integer> count = new Box<>(10);
Integer number = count.get();
~~~

The same class definition is used with multiple **type arguments**. The compiler knows that `message.get()` returns `String` and `count.get()` returns `Integer`. Many invalid type assignments are blocked **before runtime**, rather than waiting until a cast fails.

**The most important purpose of generics is not to make code look shorter; it is to express and check type relationships at compile time in reusable APIs.**

## 2. Accurate Terminology for Generic Classes

| Term | Example | Meaning |
| --- | --- | --- |
| Generic class declaration | `class Box<T>` | A class that declares type parameter T |
| Type parameter | `T` | A type variable defined in a generic declaration |
| Parameterized type | `Box<String>` | Using Box with a specific type argument |
| Type argument | `String` | The actual type supplied to T |
| Generic instance | `new Box<>("A")` | An object created from a generic class |
| Raw type | `Box raw` | Omitting type arguments, usually for legacy compatibility |
| Bounded parameter | `T extends Number` | Only type arguments satisfying the bound |
| Unbounded wildcard | `Box<?>` | A Box of an unknown type |
| Upper-bounded wildcard | `List<? extends Number>` | Uses data of a Number type or subtype |
| Lower-bounded wildcard | `List<? super Integer>` | Uses a container of Integer or supertype |
| Type erasure | `T` usually becomes bound/Object at runtime | How the compiler transforms generics into compatible bytecode |

### 2.1. The Character T Is Not a Specific Java Type

`T` is simply a name chosen by the author of the generic class for the type parameter. It does not default to a class named T, is not a runtime Class object, and is not a printable type value.

Common naming conventions:

- `T` — Type.
- `E` — Element.
- `K` — Key.
- `V` — Value.
- `R` — Result.
- `N` — Number.
- `S` or `U` — additional type parameter.

Longer names can be used, for example `class Converter<Source, Target>`; clearer names sometimes make APIs with multiple type parameters easier to read.

### 2.2. A Generic Class Is Not Source-Copied for Each Type Argument

`Box<String>` and `Box<Integer>` do not cause Java to generate two independent class definitions like two copies `StringBox` and `IntegerBox`. Java generics are implemented primarily through **type erasure**, allowing the compiler to check types and insert the necessary casts/bridges without creating a separate runtime class for each reference-type argument.

### 2.3. A Generic Parameter Is a Type, Not a Value

`Box<String>` selects the type of data to be stored; it does not require Box to hold the String "String". A type argument is not a constructor parameter like `new Box<>("Hello")`.

## 3. Complete Program 1: Object + Cast vs. Generic Class

File **`GenericVsObjectDemo.java`**:

~~~java
public class GenericVsObjectDemo {
    static final class ObjectSlot {
        private Object value;

        ObjectSlot(Object value) {
            this.value = value;
        }

        Object get() {
            return value;
        }

        void set(Object value) {
            this.value = value;
        }
    }

    static final class Slot<T> {
        private T value;

        Slot(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        void set(T value) {
            this.value = value;
        }
    }

    public static void main(String[] args) {
        ObjectSlot old = new ObjectSlot("Java");
        String first = (String) old.get();
        System.out.println("Object value = " + first);

        old.set(42);
        try {
            String wrong = (String) old.get();
            System.out.println(wrong);
        } catch (ClassCastException ex) {
            System.out.println("Wrong cast rejected");
        }

        Slot<String> safe = new Slot<>("Java");
        String second = safe.get();
        System.out.println("Generic value = " + second);

        safe.set("Core");
        System.out.println("Updated = " + safe.get());

        Slot<Integer> numeric = new Slot<>(17);
        System.out.println("Number = " + numeric.get());

        // safe.set(42); // Intentionally invalid at compile time.
    }
}
~~~

Compile and run:

~~~bash
javac -encoding UTF-8 GenericVsObjectDemo.java
java GenericVsObjectDemo
~~~

**Exact stdout:**

~~~text
Object value = Java
Wrong cast rejected
Generic value = Java
Updated = Core
Number = 17
~~~

### 3.1. Risks of ObjectSlot

`ObjectSlot` has a setter `set(Object)`, so both String and Integer are valid to the compiler. The variable `old` initially holds a String but can be assigned an Integer later. The cast `(String) old.get()` fails at runtime.

### 3.2. Value of Slot<String>

`Slot<String>` constrains `set` to accept String and `get` to return String under source-level type checking. The statement `safe.set(42)` (if uncommented) **does not compile**; the error is detected close to where the wrong data is placed into the container.

### 3.3. Generic Code Still Does Not Replace Validation

A `Slot<String>` can contain an empty string, null, or malformed data if the class/API allows it. Type safety guarantees **type scope**, and does not automatically guarantee business invariants such as length, regex, or valid state.

## 4. Syntax for Declaring a Generic Class

A generic class has the basic syntax:

~~~java
class Holder<T> {
    private T item;

    Holder(T initialValue) {
        this.item = initialValue;
    }

    public T get() {
        return item;
    }

    public void set(T next) {
        item = next;
    }
}
~~~

`<T>` after the name Holder **declares the type parameter**. T can be used in instance fields, instance methods, constructor parameters, and return types.

### 4.1. T in the Constructor Is Not a Separate Type Parameter

`Holder(T initialValue)` uses T **already declared by Holder<T>**. The constructor does not need to and should not redeclare `<T>` unless you genuinely want an independent constructor type parameter with different semantics.

### 4.2. How Is the Type Argument Chosen When Creating an Object?

~~~java
Holder<String> title = new Holder<String>("Java");
Holder<Integer> amount = new Holder<>(20);
~~~

The first form writes the type arguments explicitly in both the variable and the construction expression. The second form uses the **diamond `<>`** operator so the compiler infers the constructor type arguments from the target type and context.

### 4.3. What Scope Does a Type Parameter Have?

`T` belongs to the generic class declaration and is used for instance member signatures. It does not become a Java runtime variable.

For example, `private T item` is a field of each Holder object, not a field whose runtime type is String in Holder<String> and Integer in Holder<Integer> via class-file specialization.

### 4.4. An Arbitrary Type Cannot Be Assigned to T

`Holder<String>.set(Integer)` is not accepted just because Integer is also an Object. Type arguments must match the generic API contract. If you genuinely need to store heterogeneous values, design a `Holder<Object>` or an appropriate typed union/sealed hierarchy abstraction; understand that the compiler will have less information when reading.

## 5. Complete Program 2: Generic Box with get, set, and Factory

File **`GenericBoxDemo.java`**:

~~~java
public class GenericBoxDemo {
    static final class Box<T> {
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

        static <E> Box<E> of(E value) {
            return new Box<>(value);
        }
    }

    public static void main(String[] args) {
        Box<String> word = Box.of("Java");
        Box<Integer> year = Box.of(17);

        System.out.println("Word = " + word.get());
        System.out.println("Year = " + year.get());

        word.set("Generics");
        year.set(year.get() + 1);

        System.out.println("Updated word = " + word.get());
        System.out.println("Updated year = " + year.get());
        System.out.println("Word length = " + word.get().length());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericBoxDemo.java
java GenericBoxDemo
~~~

**Exact stdout:**

~~~text
Word = Java
Year = 17
Updated word = Generics
Updated year = 18
Word length = 8
~~~

### 5.1. Static Factory Does Not Use the Class's T

`static <E> Box<E> of(E value)` declares a **separate method type parameter E**. A static method does not have a specific Box<T> instance to use the class's T, so it must declare its own type parameter if a generic factory is desired.

### 5.2. Where Does the Compiler Infer Types?

`Box.of("Java")` infers E = String; `Box.of(17)` applies autoboxing to Integer. The target variable type also provides context for inference. In complex code, you can write `Box.<String>of("Java")` to supply an explicit method type argument.

### 5.3. Why Is `word.get().length()` Valid?

The compiler knows the return type of `word.get()` is String, so the `String.length()` method can be called directly without casting. With `Box<Object>`, calling `get().length()` does not compile because Object does not declare a length() method.

### 5.4. Adding Validation in a Generic Constructor

A Box can reject null with `Objects.requireNonNull(value)` if the contract requires it. However, you should not force every generic Box to be non-null by default if use cases need to represent an empty optional state. Choose the invariant and document it in the API.

## 6. A Class with Multiple Type Parameters: `Pair<K,V>`

Generics are not limited to a single type parameter:

~~~java
class Pair<K, V> {
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
~~~

`Pair<String,Integer>` means key String, value Integer. `Pair<Integer,String>` is a different parameterized type for type checking, even though both use the same generic class Pair at runtime after erasure.

### 6.1. Why Are Two Parameters Needed?

A Map entry container, tuple, converter, result wrapper, or message envelope often has two or more components of different types. Writing `Pair<Object,Object>` loses the type relationship of each position, forcing the caller to cast.

### 6.2. K and V Are Independent

`K` is not required to be the same as `V`. Two type parameters allow the compiler to check key and value separately. You can also declare `Pair<String,String>` if both positions are String.

### 6.3. When to Use a Record Instead of a Class?

In Java 17:

~~~java
record Pair<K, V>(K key, V value) {
}
~~~

is a **generic record**, with a canonical constructor, component accessors `key()`/`value()`, and generated equality/hashCode/toString. If a simple data carrier and value-style semantics fit, a generic record can be more concise than an ordinary generic class.

However, if the holder needs mutable setters/lifecycle, an ordinary generic class may be more suitable.

## 7. Complete Program 3: Generic Pair and Generic Record

File **`GenericPairDemo.java`**:

~~~java
public class GenericPairDemo {
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

        Pair<V, K> swapped() {
            return new Pair<>(value, key);
        }
    }

    record Entry<K, V>(K key, V value) {
    }

    public static void main(String[] args) {
        Pair<String, Integer> score = new Pair<>("Lan", 9);
        Pair<Integer, String> inverse = score.swapped();

        System.out.println("Key = " + score.key());
        System.out.println("Value = " + score.value());
        System.out.println("Swapped = " + inverse.key()
                + ":" + inverse.value());

        Entry<String, Boolean> flag = new Entry<>("ready", true);
        System.out.println("Record = " + flag);
        System.out.println("Record key = " + flag.key());
        System.out.println("Record value = " + flag.value());
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericPairDemo.java
java GenericPairDemo
~~~

**Exact stdout:**

~~~text
Key = Lan
Value = 9
Swapped = 9:Lan
Record = Entry[key=ready, value=true]
Record key = ready
Record value = true
~~~

### 7.1. `swapped()` Preserves the Exact Type Relationship

For `Pair<K,V>`, the method returns `Pair<V,K>`. When called on `Pair<String,Integer>`, the compiler infers the return type `Pair<Integer,String>`. No casting, and no runtime type tag handling.

### 7.2. Generic Records Also Have Type Arguments

`Entry<String,Boolean>` has K String and V Boolean. The record's fields are still final; if K/V is a mutable object, the record does not automatically deep-copy it.

### 7.3. What Types Can Be Passed as a Type Argument?

Reference types such as String, Integer, Boolean, List<String>, User, Interface, and parameterized types are all valid if they satisfy the bounds. Primitive types `int`, `boolean` cannot directly be type arguments; use wrappers and autoboxing where appropriate.

## 8. Compile-Time Type Safety — The Number-One Purpose

The strength of a generic class does not lie in the JVM creating some “ultra-safe” kind of object, but in **the compiler consistently checking type arguments across related positions**.

For example:

~~~java
Box<String> title = Box.of("Core");
// title.set(123);          // Does not compile: Integer is not a String.
String text = title.get();  // No cast needed.

Box<Integer> count = Box.of(5);
// String wrong = count.get(); // Does not compile.
~~~

The error lines are all compile-time type mismatches.

### 8.1. Does Not Replace Runtime Business Validation

`Box<String>` can still hold a malformed string; generics do not check "Account number must have 10 digits". Use validation, value objects, or constructor invariants for business constraints.

### 8.2. Eliminating Unnecessary Casts

With an Object container, every time a value is read, you need to know the external convention and then cast. A generic container puts the data type information into the API, reducing casts and the risk of `ClassCastException` due to mismatched expectations.

### 8.3. “Compile-Time Safe” Does Not Mean Absolutely Infallible

Raw types, unchecked casts, reflection, and uncontrolled deserialization can create **heap pollution**: a parameterized variable pointing to an object containing data of the wrong type argument. Therefore, avoid unchecked operations or keep them within a controlled and tested boundary.

### 8.4. A Type Parameter Differs from a Generic Declaration of Value Restrictions

An API `Repository<ID,Entity>` can express that save(ID,Entity) must coordinate the right ID/Entity types; however, it does not guarantee that the ID exists, which customer the Entity belongs to, or that the database transaction succeeds. Compile-time type constraints are one layer of correctness.

## 9. Generic Classes and Generic Methods Are Two Different Concepts

`class Box<T>` declares a **class-level type parameter** T. All instance methods/fields related to T on that object are based on Box's type argument.

A **generic method** has its own type parameter:

~~~java
static <U> U identity(U value) {
    return value;
}
~~~

This method can appear in a generic or non-generic class. `<U>` precedes the return type and belongs to the scope of the method declaration.

### 9.1. A Method Using T from the Class

~~~java
class Envelope<T> {
    private final T value;

    Envelope(T value) {
        this.value = value;
    }

    T read() {
        return value;
    }
}
~~~

`read()` does not need `<T>` in its declaration, because T is already a class type parameter.

### 9.2. A Method with an Independent U

~~~java
class Envelope<T> {
    private final T value;

    Envelope(T value) {
        this.value = value;
    }

    <U> String joinWith(U other) {
        return value + "|" + other;
    }
}
~~~

Here T is determined by the Envelope instance, while U is inferred from each `joinWith` invocation. It can be a String, Integer, or arbitrary reference type across different calls.

### 9.3. Static Methods Do Not Use the Class's T

A static method belongs to the class, not specifically to a `Box<String>` or `Box<Integer>` instance; therefore, you **cannot use the unbound class type parameter T** in a static method/field declaration.

Wrong:

~~~java
class Invalid<T> {
    static T current; // Does not compile.
    static T create() { return null; } // Does not compile.
}
~~~

The right way is to create a **method type parameter**:

~~~java
class Factory {
    static <T> T first(T left, T right) {
        return left;
    }
}
~~~

## 10. Complete Program 4: Class and Method Type Parameters

File **`GenericMethodScopeDemo.java`**:

~~~java
public class GenericMethodScopeDemo {
    static final class Envelope<T> {
        private final T item;

        Envelope(T item) {
            this.item = item;
        }

        T read() {
            return item;
        }

        <U> String join(U other) {
            return item + "|" + other;
        }

        static <E> Envelope<E> of(E item) {
            return new Envelope<>(item);
        }
    }

    static <A> A choose(boolean pickFirst, A first, A second) {
        return pickFirst ? first : second;
    }

    public static void main(String[] args) {
        Envelope<String> letter = Envelope.of("A");

        System.out.println("Item = " + letter.read());
        System.out.println("Join number = " + letter.join(3));
        System.out.println("Join text = " + letter.join("B"));
        System.out.println("Choose = "
                + choose(false, "left", "right"));

        Envelope<Integer> count = Envelope.of(9);
        System.out.println("Count = " + count.read());
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericMethodScopeDemo.java
java GenericMethodScopeDemo
~~~

**Exact stdout:**

~~~text
Item = A
Join number = A|3
Join text = A|B
Choose = right
Count = 9
~~~

### 10.1. U Changes per Method Invocation

An Envelope<String> can call `join(3)` with U=Integer and `join("B")` with U=String. This does not turn Envelope<String> into Envelope<Object>.

### 10.2. The Static Factory's E Is Independent

The factory uses `<E>` to choose the type argument for the created object. There is no `this` or instance T in a static method.

### 10.3. A Generic Method Can Exist Outside a Generic Class

`choose` declares `<A>` in the ordinary class GenericMethodScopeDemo; the wrapper class does not need to be generic itself. This is why “generic class” and “generic method” must be distinguished.

## 11. Bounded Type Parameters: Restricting T to a Group of Types

An unbounded `T` is treated as having a default upper bound of Object. The compiler only allows calling methods guaranteed by the bound, not methods specific to an arbitrary type.

Wrong example:

~~~java
class Metric<T> {
    double twice(T value) {
        return value.doubleValue() * 2; // Does not compile.
    }
}
~~~

`T` is not guaranteed to have `doubleValue()`. To constrain T to Number or a subtype:

~~~java
class Metric<T extends Number> {
    private final T number;

    Metric(T number) {
        this.number = number;
    }

    double twice() {
        return number.doubleValue() * 2;
    }
}
~~~

### 11.1. `extends` in a Generic Bound Also Works with Interfaces

The syntax `T extends Comparable<T>` does not mean T must extend a class named Comparable; Comparable is an interface. `extends` in a type bound expresses a subtype constraint for a class **or interface**.

### 11.2. Multiple Bounds

~~~java
class OrderedNumber<T extends Number & Comparable<T>> {
    private final T value;

    OrderedNumber(T value) {
        this.value = value;
    }

    boolean greaterThan(T other) {
        return value.compareTo(other) > 0;
    }
}
~~~

The first bound can be a class, subsequent bounds must be interfaces, and the class bound, if present, must precede the interface bounds. T must simultaneously be a Number subtype and implement Comparable<T>.

### 11.3. A Bound Is Not a Type Argument

`<T extends Number>` is a **type parameter declaration** with a bound, not `<Number>` at the usage site. A client can pass Integer, Double, or a Number subtype that satisfies the bound.

### 11.4. A Bound Does Not Mean Every Number Is Comparable

`Number` does not declare `compareTo`. If an algorithm genuinely needs ordering comparison, add a Comparable bound or pass a Comparator; do not arbitrarily cast Number and rely on the runtime type.

## 12. Complete Program 5: Number Bound and Multiple Bounds

File **`GenericBoundedDemo.java`**:

~~~java
public class GenericBoundedDemo {
    static final class NumericBox<N extends Number> {
        private final N number;

        NumericBox(N number) {
            this.number = number;
        }

        double doubled() {
            return number.doubleValue() * 2;
        }
    }

    static <N extends Number & Comparable<N>>
    N larger(N left, N right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        NumericBox<Integer> integer = new NumericBox<>(7);
        NumericBox<Double> decimal = new NumericBox<>(2.5);

        System.out.println("Integer doubled = " + integer.doubled());
        System.out.println("Double doubled = " + decimal.doubled());
        System.out.println("Larger int = " + larger(4, 9));
        System.out.println("Larger decimal = " + larger(3.0, 1.5));

        // NumericBox<String> bad = new NumericBox<>("7");
        // Does not compile: String does not extend Number.
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericBoundedDemo.java
java GenericBoundedDemo
~~~

**Exact stdout:**

~~~text
Integer doubled = 14.0
Double doubled = 5.0
Larger int = 9
Larger decimal = 3.0
~~~

### 12.1. Double and Integer Are Both Reference Types

`NumericBox<Integer>` and `NumericBox<Double>` are valid; `NumericBox<int>` is invalid because a primitive cannot be a type argument. Autoboxing converts `7` to Integer when creating the object.

### 12.2. Type Inference of larger

When calling `larger(4,9)`, the compiler selects Integer, which satisfies Number and Comparable<Integer>. For `larger(3.0,1.5)`, it selects Double.

### 12.3. Why Does `doubleValue()` Not Return an Exact Monetary Amount?

Number.doubleValue can lose precision for certain types/values. For money, use BigDecimal and appropriate domain-specific operations. The example only illustrates bounds and method access, not a monetary calculation library.

## 13. Inheritance Relationships: A Subtype Does Not Automatically Become a Subtype of a Generic Class

One of the most important rules of Java generics is **invariance**:

~~~java
Integer integer = 1;
Number number = integer; // Valid: Integer extends Number.
~~~

but:

~~~java
java.util.List<Integer> integers =
        new java.util.ArrayList<>();

java.util.List<Number> numbers = integers; // Intentionally does not compile.
~~~

Even though Integer is a subtype of Number, **List<Integer> is not a subtype of List<Number>**.

### 13.1. Why Does Java Disallow This?

Suppose the code above were allowed:

~~~java
List<Integer> ints = new ArrayList<>();
List<Number> nums = ints; // False assumption.
nums.add(3.14);           // Double is also a Number.
Integer value = ints.get(0); // At this point type safety is broken!
~~~

Invariance prevents putting a Double into a List<Integer> through a List<Number> alias. This is a logical reason, not merely compiler inconvenience.

### 13.2. A Generic Class of a Subtype and Class Inheritance Are Two Different Axes

`Integer extends Number` belongs to the type argument hierarchy. `Box<Integer>` and `Box<Number>` are different parameterized types and do not automatically have a subclass relationship.

You can create an ordinary subclass:

~~~java
class IntegerBox extends Box<Integer> {
    IntegerBox(Integer value) {
        super(value);
    }
}
~~~

This is a fragment with Box having an accessible constructor. IntegerBox **is-a Box<Integer>**, not Box<Number>.

### 13.3. Using Wildcards for Variance at API Boundaries

If a method only reads Number data:

~~~java
static double sum(List<? extends Number> items)
~~~

it can accept List<Integer>, List<Double>, List<BigDecimal>... without requiring List<Number>.

If a method needs a destination to receive Integer:

~~~java
static void addOne(List<? super Integer> destination)
~~~

it can accept List<Integer>, List<Number>, or List<Object>. The next section explains this in detail.

## 14. Wildcards and the PECS Rule: Producer Extends, Consumer Super

A **wildcard** `?` is not the name of a type parameter like T; it is an **unknown type argument** with a bound depending on the case.

Three commonly used forms:

- `List<?>`: A List of an unknown element type. Elements can be read as type Object; an arbitrary non-null element cannot be added because of the unknown element type.
- `List<? extends Number>`: A List of some subtype of Number. Reading elements as Number is safe; an arbitrary Number cannot be added.
- `List<? super Integer>`: A List of some supertype of Integer. An Integer can be added; the most general type that can be read safely is Object.

### 14.1. Producer Extends

When an API **reads values** from a source container:

~~~java
static double sum(List<? extends Number> source) {
    double result = 0;
    for (Number n : source) {
        result += n.doubleValue();
    }
    return result;
}
~~~

If source is List<Integer> or List<Double>, the compiler still knows all elements are Number subtypes, so `Number.doubleValue()` is valid.

**Cannot freely add Number**:

~~~java
List<? extends Number> source = new ArrayList<Integer>();
// source.add(3.14); // Does not compile.
~~~

The compiler does not know whether the actual element type is Integer, Double, or another subtype. Allowing a Double to be added to a List<Integer> would break type safety.

### 14.2. Consumer Super

When an API **writes Integer values** into a destination:

~~~java
static void addDefaults(List<? super Integer> destination) {
    destination.add(1);
    destination.add(2);
}
~~~

`List<Integer>`, `List<Number>`, and `List<Object>` can all accept Integer. However, reading `destination.get(0)` can only be treated as Object if the exact type argument is unknown.

### 14.3. Unbounded Wildcard

`List<?>` is suitable for APIs that only need iteration, size, or contains and do not need to assume an element type. It is not synonymous with `List<Object>`.

### 14.4. PECS Does Not Replace All T

Wildcards are especially useful in method signatures. If a method needs to establish a relationship between two type positions (for example, source and target sharing the same T), a **named type parameter `<T>`** expresses the relationship more clearly than independent `?`.

## 15. Complete Program 6: Reading and Writing with Wildcards

File **`GenericVarianceDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class GenericVarianceDemo {
    static double sum(List<? extends Number> values) {
        double result = 0;
        for (Number value : values) {
            result += value.doubleValue();
        }
        return result;
    }

    static void addIntegers(List<? super Integer> output) {
        output.add(3);
        output.add(4);
    }

    static <T> void copy(
            List<? super T> destination,
            List<? extends T> source) {
        for (T value : source) {
            destination.add(value);
        }
    }

    public static void main(String[] args) {
        List<Integer> ints = List.of(1, 2);
        List<Number> numbers = new ArrayList<>();

        addIntegers(numbers);
        System.out.println("After add = " + numbers);
        System.out.println("Sum integers = " + sum(ints));

        copy(numbers, ints);
        System.out.println("After copy = " + numbers);
        System.out.println("Total = " + sum(numbers));

        List<Object> objects = new ArrayList<>();
        copy(objects, ints);
        System.out.println("Objects = " + objects);
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericVarianceDemo.java
java GenericVarianceDemo
~~~

**Exact stdout:**

~~~text
After add = [3, 4]
Sum integers = 3.0
After copy = [3, 4, 1, 2]
Total = 10.0
Objects = [1, 2]
~~~

### 15.1. Why Does copy Need Both extends and super?

`source` produces T values → `? extends T`. `destination` receives T values → `? super T`. This is a practical application of **PECS** in a generic method. Both args do not always have to have an exact type parameter like `List<T>`.

### 15.2. Why Does `numbers` Hold Integer in List<Number>?

Integer is a subtype of Number, so adding an Integer to a List<Number> is valid. However, a List<Integer> reference cannot be directly assigned to a List<Number> variable. **Adding a subtype element** is completely different from **converting a parameterized container type**.

### 15.3. A Wildcard Is Not an Immutable View

A `List<? extends Number>` variable cannot arbitrarily call add(Number), yet the referent list can still be mutable through another alias, and some operations like remove/clear may still be valid. Being read-only due to a generic add restriction **does not mean the List object is immutable**.

## 16. Generic Class Inheritance and Implementing Generic Interfaces

Generic type parameters can be **retained**, **specialized**, or **forwarded to a generic superclass/interface**.

### 16.1. Inheriting While Remaining Generic

~~~java
class Base<T> {
    T value;

    Base(T value) {
        this.value = value;
    }
}

class Child<T> extends Base<T> {
    Child(T value) {
        super(value);
    }
}
~~~

Child<T> continues to be a generic class. `Child<String>` is a subtype of `Base<String>`.

### 16.2. Inheriting with a Fixed Type Argument

~~~java
class TextChild extends Base<String> {
    TextChild(String text) {
        super(text);
    }
}
~~~

TextChild is not generic; it fixes the superclass type argument to String. A `TextChild` can be assigned to `Base<String>`, not `Base<Integer>`.

### 16.3. Generic Interface

~~~java
interface Repository<ID, ENTITY> {
    ENTITY find(ID id);
}

class UserRepository implements Repository<Long, User> {
    @Override
    public User find(Long id) {
        return ...;
    }
}
~~~

This is a **conceptual fragment**, where the ellipsis represents an unwritten body so it is not standalone. The meaning is that UserRepository fixes ID=Long and ENTITY=User when implementing the interface; `find` uses Long input and User output. A full runnable program in a later section uses Optional and Map.

### 16.4. Cannot Implement the Same Generic Interface with Two Incompatible Args

A class cannot simultaneously implement `Comparable<String>` and `Comparable<Integer>` as two independent instantiations if that causes a same-erasure/interface conflict. The Java type system prevents an object from having two conflicting specialized methods on the same erased signature.

## 17. Complete Program 7: Generic Inheritance

File **`GenericInheritanceDemo.java`**:

~~~java
public class GenericInheritanceDemo {
    static class Store<T> {
        private final T value;

        Store(T value) {
            this.value = value;
        }

        T read() {
            return value;
        }
    }

    static final class TextStore extends Store<String> {
        TextStore(String value) {
            super(value);
        }

        int length() {
            return read().length();
        }
    }

    static final class FlexibleStore<T> extends Store<T> {
        FlexibleStore(T value) {
            super(value);
        }
    }

    public static void main(String[] args) {
        Store<String> text = new TextStore("Core");
        Store<Integer> count = new FlexibleStore<>(7);

        System.out.println("Text = " + text.read());
        System.out.println("Integer = " + count.read());
        System.out.println("Length = "
                + new TextStore("Java").length());
        System.out.println("Different runtime classes = "
                + (text.getClass() != count.getClass()));
    }
}
~~~

Compile/run:

~~~bash
javac -encoding UTF-8 GenericInheritanceDemo.java
java GenericInheritanceDemo
~~~

**Exact stdout:**

~~~text
Text = Core
Integer = 7
Length = 4
Different runtime classes = true
~~~

### 17.1. Two Different Runtime Classes Because of **Two Class Declarations**

TextStore and FlexibleStore are different classes. That **does not negate type erasure**. If you create `new FlexibleStore<String>` and `new FlexibleStore<Integer>`, both have the same raw runtime class FlexibleStore.

### 17.2. Compile-Time Inherited Return Type

`Store<String>.read()` is type-checked as returning String, even though the erased method implementation may use Object. The compiler adds bridges/casts when needed to guarantee type system semantics.

### 17.3. Cannot Assign Between Two Store Argument Types

`Store<String>` and `Store<Object>` do not automatically have a subtype relation. If you want a read-only API to accept multiple Store<T> types, you can use `Store<?>` or a generic bound, depending on the operation.

## 18. Type Erasure: One Declaration, Many Type Arguments

With Java generics, the compiler **checks types at compile time**, then performs *type erasure*. `Box<String>` and `Box<Integer>` do not become two different Java runtime classes. An unbounded `T` is usually erased to `Object` in field/method signatures; an appropriate bound can change the erased type. The compiler may insert casts and bridge methods to preserve semantics; generic metadata on declarations can still be read via reflection.

## 19. Runnable Program: Observing the Runtime Class of Two Boxes

Save **`GenericRuntimeBasicsDemo.java`**:

~~~java
import java.lang.reflect.Field;

public class GenericRuntimeBasicsDemo {
    static final class Box<T> {
        private final T value;
        Box(T value) { this.value = value; }
        T get() { return value; }
    }

    public static void main(String[] args) throws Exception {
        Box<String> text = new Box<>("Java");
        Box<Integer> number = new Box<>(17);
        Field field = Box.class.getDeclaredField("value");

        System.out.println(text.get());
        System.out.println(number.get());
        System.out.println(text.getClass() == number.getClass());
        System.out.println(field.getType().getSimpleName());
    }
}
~~~

~~~bash
javac --release 17 -encoding UTF-8 GenericRuntimeBasicsDemo.java
java GenericRuntimeBasicsDemo
~~~

~~~text
Java
17
true
Object
~~~

Because the field has an unbounded type variable `T`, the reflective erased field type is `Object`. Even though the runtime class of both Boxes is the same, the compiler still knows `text.get()` returns `String` and `number.get()` returns `Integer` from the type arguments in the source. Reflection can tell that the class **declares T**, but cannot infer the individual type argument of a plain Box instance via `getClass()` alone.

## 20. Raw Types and Unchecked Operations Are Risky Shortcuts

`Box raw = typedBox` uses a *raw type* for legacy code compatibility. Through the raw alias, a call such as `raw.set(42)` can produce an unchecked warning and insert the wrong element type into a Box that was being used through `Box<String>`. A `ClassCastException` may appear later at a typed read. `Box<?>` represents a box with an unknown element type in a more type-safe way than a raw Box when you only need to read as Object; it **does not** fix previously polluted data.

## 21. Checking Warnings Before Suppressing Type Checking

Use `javac -Xlint:rawtypes -Xlint:unchecked File.java` to see where unsafe legacy APIs occur. Only use `@SuppressWarnings("unchecked")` in a narrow scope when the invariant has been proven at the boundary and there are tests for mistyped data. The mechanisms of bridge methods, raw invocation, erasure, and heap pollution have many edge cases studied in depth separately; in this introductory lesson, what matters is that **compile-time generic safety differs from runtime class identity**.

## 22. Some Important Syntax Limitations of Generic Classes

Type arguments must be reference types: `Box<Integer>` is valid while `Box<int>` is invalid. Java does not allow using an erased type variable `T` directly as a runtime constructor/class literal/array component:

~~~java
class Invalid<T> {
    // T obj = new T();                      // Compile error.
    // T[] arr = new T[5];                   // Compile error.
    // Class<T> type = T.class;              // Compile error.
    // static T shared;                      // Compile error.
}
// List<String>[] a = new List<String>[3];   // Compile error.
~~~

This is a **snippet illustrating commented-out invalid cases**, not a runnable program demonstrating compiler errors. Solutions depend on the need: accept an already-created object, pass a `Supplier<? extends T>` or factory, use `List<T>`, an array factory, or a `Class<T>` type token. A generic method in a static context needs its **own** type parameter (`static <U> U identity(U x)`). `instanceof List<String>` cannot be used as a general runtime element-type check either.

## 23. Runtime Type Token: Choose When Accepting External Object Input

If an API truly needs runtime validation, it can accept `Class<T>` and use `type.cast(candidate)`:

~~~java
final class CheckedBox<T> {
    private final T value;
    CheckedBox(Class<T> type, Object candidate) {
        this.value = type.cast(candidate);
    }
    T get() { return value; }
}
~~~

This is a **declaration fragment**, without `main`. The token `String.class` can check String, but `Class<List<String>>` does not have a runtime Class object that reifies nested generic arguments. More complex reflection/type descriptors are only needed when the use case demands them. A type token **does not disable type erasure**; it adds a check according to the API contract. The restrictions around `new T()`, generic arrays, `T.class`, and runtime checks will be explored in depth in a separate lesson, whereas the basic Box example only requires knowing **when you cannot rely on T at runtime**.

## 24. Generic API: Repository, ID, and Entity

A common use case in domain services:

~~~java
interface Repository<ID, ENTITY> {
    void save(ID id, ENTITY entity);
    java.util.Optional<ENTITY> find(ID id);
}
~~~

Two type parameters allow the compiler to constrain:

- ID type, for example Long or String.
- ENTITY type, for example User or Order.
- `save` accepts the right pair of types.
- `find` returns Optional<ENTITY>, not Object.
- The caller does not need to cast from Object to User.

### 24.1. Why Use Optional<ENTITY>?

An ID lookup might not find an object. Returning Optional describes a missing value directly in the API instead of using an ambiguous null. This is a design choice; not every generic repository is required to use Optional.

### 24.2. When Should Bounds Be Added?

If all IDs must be Comparable, you can declare `ID extends Comparable<ID>`, but only add a bound if the implementation actually needs compareTo. If using HashMap ID keys, the appropriate requirement is equals/hashCode semantics on the keys, not necessarily Comparable.

### 24.3. Generic Type Safety Does Not Fix Business Ownership

Repository<String,User> guarantees the types of ID and Entity at compile time; it does not automatically guarantee user access permissions, transaction boundaries, or entity lifecycle. Those concerns require application/services policy.

## 25. Complete Program 11: Generic Repository<ID,ENTITY>

File **`GenericRepositoryDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

public class GenericRepositoryDemo {
    interface Repository<ID, ENTITY> {
        void save(ID id, ENTITY entity);
        Optional<ENTITY> find(ID id);
    }

    static final class MemoryRepository<ID, ENTITY>
            implements Repository<ID, ENTITY> {
        private final Map<ID, ENTITY> rows = new HashMap<>();

        @Override
        public void save(ID id, ENTITY entity) {
            rows.put(id, entity);
        }

        @Override
        public Optional<ENTITY> find(ID id) {
            return Optional.ofNullable(rows.get(id));
        }
    }

    record User(String name) {
    }

    public static void main(String[] args) {
        Repository<String, User> users = new MemoryRepository<>();

        users.save("u-1", new User("Lan"));

        System.out.println("Found = " + users.find("u-1"));
        System.out.println("Missing = " + users.find("u-2"));

        User result = users.find("u-1").orElseThrow();
        System.out.println("Name = " + result.name());

        // users.save(1, new User("An")); // Does not compile.
        // users.save("u-3", "An"); // Does not compile.
    }
}
~~~

Run:

~~~bash
javac -encoding UTF-8 GenericRepositoryDemo.java
java GenericRepositoryDemo
~~~

**Exact stdout:**

~~~text
Found = Optional[User[name=Lan]]
Missing = Optional.empty
Name = Lan
~~~

### 25.1. ID and ENTITY Have Separate Roles

`Repository<String,User>` defines ID=String and ENTITY=User. Both `save` and `find` use the same ID type and ENTITY type in the API; changing ID to Integer or Entity to String is rejected by the compiler.

### 25.2. The Implementation Remains Generic

`MemoryRepository<ID,ENTITY>` keeps both type parameters, and `Map<ID,ENTITY>` uses the same type relationship. You can create another repository for `Long,Order` without copying the implementation source.

### 25.3. Output Does Not Depend on HashMap Iteration Order

The demo only performs `get` by exact keys and does not iterate over HashMap entries. The result is therefore deterministic for the stored data.

### 25.4. Null Behavior

`Optional.ofNullable(rows.get(id))` returns empty if the mapping is absent or the value is null. HashMap can store null, yet the API here might want to reject null entities in `save` to distinguish missing from present-null. A production repository should state this invariant clearly.

## 26. Reusing Generic Code Still Requires Good Object Design

A generic class should carry **a real abstraction**, not just wrap every object in `Holder<T>` regardless of purpose.

### 26.1. Controlled Reuse

Example of a reusable cache interface:

~~~java
interface Cache<K, V> {
    void put(K key, V value);
    V get(K key);
}
~~~

This is a fragment. The generic type parameters describe the key→value relation. Concerns such as eviction, expiry, null contract, and concurrency still need to be defined in the implementation.

### 26.2. Do Not Use Object When Generics Can Express the Type Relationship

A `Map<Object,Object>` can hold anything, but weakens checks. If the domain has String IDs and User entities, using `Map<String,User>` helps prevent passing the wrong key/value.

### 26.3. Do Not Make Domain Classes Generic Without Reason

`class Invoice<T>` makes no sense if T is not used to express a real invariant/capability. Every type parameter makes the API more complex and can lead to difficult inference and long error messages. A type parameter should exist only when **different types still share a sensible abstraction**.

### 26.4. Generic at the Boundary, Domain Inside

You can use generic framework classes (`Repository<ID,T>`, `Result<T>`), while domain models `User`/`Order` still have their own fields and business rules. Do not force every domain class to extend a generic base with unnecessary state/lifecycle.

### 26.5. Constructor Validation and Defensive Copying

A `Container<List<String>>` does not automatically take a snapshot; a generic class can hold a mutable List reference as usual. If a snapshot is needed, use `List.copyOf` at the API boundary, watching out for mutable elements. Generics check **type**, and do not guarantee **immutability**.

## 27. Generic Class, Record, Interface, and Enum in Java 17

### 27.1. Generic Record

~~~java
record Response<T>(int status, T body) {
}
~~~

Valid. `Response<String>` holds a String body; `Response<User>` holds a User.

### 27.2. Generic Interface

~~~java
interface Mapper<S, T> {
    T map(S source);
}
~~~

Valid. A class can implement `Mapper<String,Integer>` and return an Integer from a String according to its logic.

### 27.3. Enums Do Not Declare Generic Type Parameters

You cannot declare `enum State<T> { ... }` as a generic enum type in Java. Enum constants are a set of values of a fixed enum type. However, an enum can still implement a **generic interface with concrete type arguments**, if valid:

~~~java
interface Coded<T> {
    T code();
}

enum Flag implements Coded<Integer> {
    OFF(0), ON(1);

    private final int value;

    Flag(int value) {
        this.value = value;
    }

    public Integer code() {
        return value;
    }
}
~~~

This is a declaration fragment. Flag does not become `Flag<Integer>`; it only implements the Coded<Integer> contract.

### 27.4. A Generic Class Can Be sealed or final

~~~java
sealed interface Result<T> permits Success, Failure {
}

record Success<T>(T value) implements Result<T> {
}

record Failure<T>(String error) implements Result<T> {
}
~~~

This is a fragment illustrating a **generic sealed interface** with generic record variants. The Java type parameter T handles the payload; `sealed` handles direct subtype permissions. The two mechanisms are independent.

### 27.5. Generic Bounds with Interfaces and Records

Record `Success<T>` can have T as an arbitrary reference type; if Number-specific behavior is needed, a bound `T extends Number` will restrict clients. No bound is needed merely because the type is a record.

## 28. Type Inference, Diamond, and Target Typing

Java can infer generic type arguments when there is sufficient context.

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
java.util.Map<String, Integer> counts =
        new java.util.HashMap<>();
~~~

`<>` is the diamond operator. It reduces repeating String/Integer on both sides, while the type relationship does not change.

### 28.1. `var` Does Not Lose the Generic Type

In Java 17:

~~~java
var names = new java.util.ArrayList<String>();
names.add("Lan");
~~~

Compiler inference gives names the type `ArrayList<String>`. It does not become a raw ArrayList just because of `var`.

However:

~~~java
var names = new java.util.ArrayList<>();
~~~

does not have a sufficiently specific target type, so the type may be inferred as `ArrayList<Object>`. If you want String, write an explicit constructor type argument or a typed target declaration.

### 28.2. `List.of` Is a Generic Static Factory

~~~java
var names = java.util.List.of("Lan", "Mai");
~~~

The compiler can infer List<String>. This is an unmodifiable List according to the `List.of` API, not because generics automatically make the List immutable.

### 28.3. Target Typing Supports Lambdas

Generic methods and functional interfaces often infer type arguments from the target type:

~~~java
java.util.function.Function<String, Integer> length =
        String::length;
~~~

This is a broader use case of Java type inference. Parameterized generic classes give method references and lambdas typed signatures, reducing casts in pipelines.

### 28.4. Inference Has Limits

An expression with many overloads, wildcards, and nested generics may prevent the compiler from finding a suitable type argument. You can declare local variables with explicit types or use explicit method type arguments instead of forcing the compiler to guess.

## 29. Common Mistakes When First Using Generic Classes

1. **Using `Object` even when the API has a clear type relationship:** loses compile-time checks.
2. **Assuming type parameter T is a runtime Class object:** generics are mainly erased.
3. **Assuming creating `Box<String>` generates a separate runtime class:** not true for ordinary Java generics.
4. **Using primitive `int` as a type argument:** invalid; use Integer.
5. **Forgetting the diamond operator:** not wrong, but repeats type info unnecessarily.
6. **Using diamond without a clear target type and expecting String:** inference may choose Object.
7. **Calling a String-specific method on an unbounded T:** the compiler only knows the bound Object.
8. **Writing `static T field` in a generic class:** the class T cannot be used in a static context.
9. **Not distinguishing between generic class T and method U:** causes confusing API signatures.
10. **Writing `new T()`:** not possible due to erased type.
11. **Writing `new T[10]` or `new List<String>[10]`:** generic array creation restrictions.
12. **Using `instanceof List<String>`:** the type argument is not reifiable.
13. **Reading List<?> and casting arbitrarily:** the wildcard does not guarantee the element type.
14. **Assigning `List<Integer>` to `List<Number>`:** invariance prevents heap pollution.
15. **Misusing `? extends T` and trying to add T:** the compiler does not know the actual producer element subtype.
16. **Using `? super T` and reading T directly:** can only be read safely as Object if no other information is available.
17. **Misunderstanding PECS as immutable/mutable:** wildcards restrict type-safe operations; they do not make an object immutable.
18. **Using raw types to avoid compiler errors:** creates unchecked risks.
19. **Suppressing all unchecked warnings:** hides where heap pollution occurs.
20. **Using a generic interface twice with conflicting type arguments:** erasure conflicts.
21. **Overloading methods only by List<String>/List<Integer>:** same erasure.
22. **Using T for every type parameter even when roles differ:** Pair should clearly use K,V.
23. **Making domain entities generic without reason:** increases complexity.
24. **Assuming `Box<String>` cannot hold null:** the null contract is independent of the generic type.
25. **Assuming generics automatically defensive-copy a mutable List:** they do not.
26. **Assuming a generic record is deeply immutable:** only the component fields are final; a mutable referent can still change.
27. **Relying on getClass() to find T=String from a Box<String> instance:** the runtime class does not carry a reified type arg.
28. **Using Class<List<String>> as a runtime type literal:** there is no List<String>.class.
29. **Forgetting type bounds when Comparable/Number operations are needed:** code fails to compile or requires improper casts.
30. **Adding unnecessarily tight bounds:** reduces API reusability.
31. **Not distinguishing runtime exceptions from compile errors:** type safety reduces errors, without eliminating all runtime faults.
32. **Not writing tests for raw/legacy boundaries:** external data needs validation.
33. **Not thinking about equality/hash semantics of keys when building Map<K,V>:** a generic K does not guarantee value semantics.
34. **Using mutable objects as map keys:** changing state can break lookups even though the type remains valid.
35. **Using unchecked casts as the default solution:** prefer a typed factory, Class<T>, bounds, or explicit converters when needed.

## 30. Decision Table: Which Kind of API Should You Choose?

| Problem | Usually Reasonable Design | Reason |
| --- | --- | --- |
| Box for a chosen reference type | `Box<T>` | Preserves the type relationship between set/get |
| Key/value pair of different types | `Pair<K,V>` / generic record | Checks types at each position |
| Storing User by String ID | `Repository<String,User>` | Typed IDs/entities |
| Method copying between subtype-related Lists | `<T> copy(List<? super T>, List<? extends T>)` | PECS |
| Method that only reads Number values | `List<? extends Number>` | Accepts multiple Number subtypes |
| Method that only adds Integer | `List<? super Integer>` | Accepts multiple consumers |
| A List with an unknown element type | `List<?>` | Safer than raw List |
| Numeric wrapper needing `doubleValue` | `T extends Number` | Compiler knows Number's API |
| Static utility choosing a value | `static <T> T choose(...)` | Method-specific parameter |
| Runtime check of candidate Object | `Class<T>` token with `cast` | Explicit validation at boundary |
| Immutable result payload | `record Result<T>(T value)` | Generic value-style record |
| Heterogeneous hierarchy with finite variants | Sealed interface + typed records | Closed variants and typed payload |
| Runtime-configurable arbitrary type IDs | Interface/value class/registry | Generic enum is not allowed |
| Primitive numeric hot path | `int[]` / primitive-specialized APIs | Avoids boxing overhead when needed |

The table is a heuristic, not a compiler rule for every architecture. Evaluate state ownership, lifecycle, extensibility, null contracts, and actual performance.

## 31. Self-Check Exercises with Answers

**Question 1.** What is the primary purpose of `class Box<T>`?

**Answer:** Allowing one implementation to work with multiple reference types while maintaining compile-time relationships between fields/method inputs/outputs, reducing casts and type errors.

**Question 2.** Can `Box<String>` call `set(123)` if the setter accepts T?

**Answer:** No; 123 is boxed into Integer, not String.

**Question 3.** Does `Box<Integer>` share the same class source with `Box<String>`?

**Answer:** Yes; one generic class declaration is parameterized with different type arguments.

**Question 4.** Is `T` in `Box<T>` a String object or a type parameter?

**Answer:** Type parameter.

**Question 5.** What is the type argument in `Box<User>`?

**Answer:** User.

**Question 6.** Is `Box<int>` valid?

**Answer:** No; type arguments must be appropriate reference types. Use Box<Integer>.

**Question 7.** Is `Box<?>` the same as a raw Box?

**Answer:** No; the wildcard still preserves generic safety with an unknown type, whereas raw drops type information and carries unchecked risks.

**Question 8.** Do you need to cast `(String) box.get()` when box has type Box<String>?

**Answer:** No, not in normal source code, because the compiler knows the return type is String.

**Question 9.** Can a static method use T of `class Box<T>` directly?

**Answer:** No. A static generic method declares its own type parameter, for example `static <E> Box<E> of(E e)`.

**Question 10.** Can `class Pair<K,V>` have K=String and V=Integer?

**Answer:** Yes, the type parameters are independent.

**Question 11.** Which parameterized type does method `Pair<V,K> swapped()` of Pair<String,Integer> return?

**Answer:** Pair<Integer,String>.

**Question 12.** How does a generic method differ from a generic class?

**Answer:** A method declares `<U>` for an invocation; a class declares `<T>` used across the instance API.

**Question 13.** Why is `T extends Number` useful?

**Answer:** The compiler knows T is a Number subtype, so doubleValue/intValue and Number members can be called.

**Question 14.** Does `T extends Comparable<T>` mean T must extend a Comparable class?

**Answer:** No; Comparable is an interface, and `extends` is also used for interface bounds.

**Question 15.** Can `List<Integer>` be assigned to `List<Number>`?

**Answer:** No, generic parameterized types are invariant with respect to this relationship.

**Question 16.** Why is List<Integer> not a List<Number>?

**Answer:** If it were allowed, a Double could be added through a List<Number> alias into a List<Integer>, breaking type safety.

**Question 17.** When reading Number values from multiple numeric List types, what should you use?

**Answer:** `List<? extends Number>`.

**Question 18.** Can you arbitrarily add a Double to `List<? extends Number>`?

**Answer:** No, the actual element subtype could be Integer.

**Question 19.** When adding Integer to List<Integer>, List<Number>, or List<Object>, what should you use?

**Answer:** `List<? super Integer>`.

**Question 20.** Under what type is reading an element from `List<? super Integer>` generally safe?

**Answer:** Object.

**Question 21.** Does `List<?>` allow adding an arbitrary String?

**Answer:** No, because the actual element type argument is unknown.

**Question 22.** What does `? extends T` mean in PECS?

**Answer:** A container that produces values typed as T (or subtypes), suitable for reading.

**Question 23.** What does `? super T` mean in PECS?

**Answer:** A container that consumes and can accept T values, suitable for writing.

**Question 24.** Does `Box<String>.getClass()` differ from `Box<Integer>.getClass()`?

**Answer:** No, for instances of the same generic Box class, due to type erasure.

**Question 25.** What is an unbounded T usually erased to?

**Answer:** Object.

**Question 26.** Does reflection `Box.class.getTypeParameters()` reveal T=String on an instance?

**Answer:** No; it reveals that the class declares a type variable T.

**Question 27.** Can you create `new T()`?

**Answer:** No; you need a Supplier<T>/factory/Class<T> token depending on the purpose.

**Question 28.** Can you create `new List<String>[10]`?

**Answer:** No, due to generic array creation restrictions with non-reifiable parameterized types.

**Question 29.** Can you use `value instanceof List<String>`?

**Answer:** No; you can check `List<?>` and validate elements separately.

**Question 30.** Can a raw `List` cause a List<String> to contain an Integer?

**Answer:** Yes, via unchecked operations/heap pollution; reading a String later may throw ClassCastException.

**Question 31.** Does `@SuppressWarnings("unchecked")` check runtime types?

**Answer:** No; it only suppresses compiler warnings in the applied scope.

**Question 32.** Is a generic record valid in Java 17?

**Answer:** Yes, for example `record Result<T>(T data) {}`.

**Question 33.** Is a generic enum `enum E<T>` valid?

**Answer:** No, but an enum can implement a generic interface with concrete arguments.

**Question 34.** Is `var list = new ArrayList<String>()` a raw List?

**Answer:** No; the compiler infers ArrayList<String>.

**Question 35.** What can `var list = new ArrayList<>()` infer without a typed target context?

**Answer:** Usually ArrayList<Object>; write the type explicitly if you want String.

**Question 36.** Does a generic class automatically make a List component immutable?

**Answer:** No; generic type safety and mutability/ownership are two different concerns.

**Question 37.** Does `Repository<String,User>` guarantee the user has permission to access the entity?

**Answer:** No; it only checks the ID and entity type relationship. Authorization is business logic.

**Question 38.** When you need a runtime check that an Object candidate is a String, what can you use?

**Answer:** `String.class.cast(candidate)` or a Class<T> token with a cast/validation boundary.

**Question 39.** Can `Class<List<String>>` be represented by `List<String>.class`?

**Answer:** No; nested type arguments are not reified via a class literal like that.

**Question 40.** What is the most important takeaway when learning generic classes?

**Answer:** Type parameters make a class reusable while still linking the types of inputs/outputs at compile time, reducing casts and avoiding mixing incompatible data; use bounds/wildcards when flexibility is needed, avoid raw types, and understand type erasure.

## 32. Progressive Practical Exercises

### Exercise 1 — Build Your Own Box<T>

Create `Box<T>` with a constructor, `get`, `set`, and `map(Function<? super T,? extends R>)` returning Box<R>. Write a demo Box<String> → Box<Integer> using String.length. Verify compile errors when trying to set an Integer into Box<String>.

**Hint:** `<R> Box<R> map(...)` is a generic instance method with an independent R. The Function upper/lower wildcards help accept consumers/producers of types flexibly.

### Exercise 2 — Key/Value Typed Pair

Write `Pair<K,V>` with `swap()` returning Pair<V,K>. Create Pair<String,Boolean>, swap, and read both component values without casting.

**Hint:** Keep K/V on fields, constructor, and return type; do not use Object in the public API.

### Exercise 3 — Multi-Entity Repository

Implement generic `Repository<ID,T>` with Map<ID,T>. Create a Repository<String,User> and a Repository<Long,Order>. Verify that the compiler blocks save(Integer,User) on the first repository.

**Hint:** Avoid iteration order dependency; check missing values with Optional.

### Exercise 4 — Bounds

Write `NumericSummary<N extends Number>` returning a double sum for List<N>. Try Integer/Double, and observe that String does not satisfy the bound. State the precision risk when doubleValue is used for money.

**Hint:** Use List<? extends Number> if the method only reads and does not need the class to have a fixed N.

### Exercise 5 — Invariance and PECS

Given List<Integer>, List<Number>, and List<Object>. Write a generic copy method accepting producer/consumer wildcards. Try assigning List<Integer> to List<Number> and explain the compile error.

**Hint:** `<T> copy(List<? super T>, List<? extends T>)`.

### Exercise 6 — Runtime Token

Build `CheckedBox<T>` holding Class<T> and use cast at the boundary accepting Object. Test valid/invalid cases and analyze why you cannot simply use T.class.

**Hint:** `Class<T>.cast` and catch ClassCastException in the right place.

### Exercise 7 — Legacy Raw Type Audit

Take a raw List API and add generic type arguments where a contract exists. Use `javac -Xlint:unchecked` to inspect warnings and replace raw references with `List<?>`/typed List where appropriate.

**Hint:** Do not use suppressWarnings as the first step; find where the data type relation is lost.

### Exercise 8 — Generic Type Erasure

Create Box<String> and Box<Integer>, compare getClass, and inspect `Box.class.getDeclaredField("value").getType()`. Explain why `getTypeParameters()` metadata still has T while an instance does not inherently know its concrete T.

**Hint:** Distinguish the generic declaration signature from the runtime object class.

## 33. Checklist for Reviewing a Generic Class Before Using It in a Project

1. Does the class have a genuinely shared abstraction to parameterize?
2. Is the type parameter T/K/V named to reflect its role?
3. Are one or multiple independent type parameters needed?
4. Do input/output fields/methods use the right type relationships?
5. Are there Object types and casts in the public API that generics can replace?
6. Are there raw types or unchecked operations that need to be isolated?
7. Have you tested misuse compilation to ensure the API blocks wrong data types?
8. Are bounds added only when the implementation needs the corresponding methods?
9. Are wildcards used when a method needs variance?
10. Are producer extends and consumer super distinguished?
11. Do you avoid assigning List<Integer> to List<Number>?
12. Do you understand that wildcards do not make a List immutable?
13. Do you know that static methods need their own type parameters?
14. Do you avoid static T fields and new T()?
15. Are primitive types handled with wrappers or primitive-specialized structures?
16. Do you remember that generics are erased and avoid misusing instanceof on parameterized types?
17. Do you avoid generic arrays and uncontrolled casts?
18. Is there a runtime Class<T> token when validation from Object is truly needed?
19. Are type inference/diamond used clearly without unintentionally creating ArrayList<Object>?
20. Do you know that the type parameters of a generic class and a generic method are independent?
21. Is a clear null contract designed, without assuming generics are non-null?
22. Is defensive copying performed if the class holds mutable data and needs a snapshot?
23. Are equals/hashCode controlled for generic key types when using Map<K,V>?
24. Has thread-safety of a mutable generic container been checked?
25. Are overloads that cause a same-erasure clash avoided?
26. Are compile errors in code used to teach type safety instead of ignoring compiler warnings?
27. Are there integration tests for the boundary between typed Java code and raw/legacy deserialization?
28. Can a generic record be used for a simple value carrier?
29. Do you know that an enum cannot be generic even though it can implement a generic interface?
30. Do you avoid making a domain class generic when it has no genuine need for parameterization?

## Conclusion

**Generic classes in Java allow a class to represent a reusable abstraction across multiple reference types, while linking the types of input data, fields, and return values through compile-time checking.** `Box<T>`, `Pair<K,V>`, and `Repository<ID,ENTITY>` all demonstrate that purpose more clearly than `Object` + casts.

Understanding generic classes must come with their limitations: type arguments are **reference types**, parameterized classes are **invariant** with respect to the inheritance of type arguments, `extends`/`super` wildcards support flexible APIs according to PECS, and type erasure explains why runtime does not usually carry the type arguments of each generic instance. Bounded parameters restrict T so specific methods can be called; generic methods have their own type parameters; raw types/unchecked operations can break type guarantees.

Generics **do not automatically make data immutable, non-null, business-valid, or thread-safe**. They solve a specific yet critically important problem: **reusing program structure without losing type safety**. When the right generic abstraction is chosen, the API is both flexible and catches errors early, reducing duplication, casts, and runtime `ClassCastException` in Java 17+.
