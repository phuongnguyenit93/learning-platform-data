# Generic Classes in Java: Type Bounds with `extends` and Multiple Bounds

## 1. Why Do Generics Need Type Bounds?

A generic class can be written as:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

The code above is a valid class declaration. With an unbounded `T`, the compiler does not know whether an object of type `T` has methods such as `doubleValue()`, `compareTo()`, or a business interface `code()`. The compiler only has the general capabilities of `Object`.

If the class actually needs to handle an **object belonging to a specific type family**, we declare an **upper bound**:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    double doubled() {
        return value.doubleValue() * 2;
    }
}
```

Here `T extends Number` means **the type argument T must be a subtype of Number**, so inside the class body we can call the methods that the Number type grants access to. The `extends` keyword is used for both a **class bound** and an **interface bound** of a type parameter, even when the actual type implements an interface using `implements`.

When a type must satisfy **multiple contracts at once**, Java supports **multiple bounds**:

```java
class RankedBox<T extends Number & Comparable<T>> {
    private final T value;

    RankedBox(T value) {
        this.value = value;
    }

    int compareTo(T other) {
        return value.compareTo(other);
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

`T` here must both be a `Number` and satisfy `Comparable<T>`. Because of that, the class can **call methods of both bound types** without manual casting.

> **Key takeaway:** A type bound does not “take an object and attach extra capabilities” at runtime. It is a **compile-time contract**: only matching type arguments are allowed to be used, and the compiler permits access to the members guaranteed by the bound.

This lesson focuses on the `extends` syntax, valid type argument conditions, **multiple bounds `A & B & C`**, class/interface ordering, usage in generic classes and methods, along with consequences for erasure, variance, API design, and common errors. The complete programs compile with Java 17+.

## 2. First Runnable Example: A Single Type Bound Using a Class

Create the file **`BoundedNumberBoxDemo.java`**:

```java
class NumberBox<T extends Number> {
    private final T number;

    NumberBox(T number) {
        this.number = number;
    }

    double twice() {
        return number.doubleValue() * 2;
    }

    T get() {
        return number;
    }
}

public class BoundedNumberBoxDemo {
    public static void main(String[] args) {
        NumberBox<Integer> integers = new NumberBox<>(7);
        NumberBox<Double> decimals = new NumberBox<>(2.5);

        System.out.println(integers.twice());
        System.out.println(decimals.twice());
        System.out.println(integers.get());
    }
}
```

Compile/run:

```bash
javac BoundedNumberBoxDemo.java
java BoundedNumberBoxDemo
```

Standard output:

```text
14.0
5.0
7
```

### Analysis

- `Integer` and `Double` are both subclasses of `Number`, so they are valid type arguments for `NumberBox<T extends Number>`.
- `T get()` still returns the exact type argument at the call site: `Integer` or `Double`; the bound does not lose static generic type information.
- Inside the class, `number.doubleValue()` is valid because the method is guaranteed by `Number`.
- `new NumberBox<>(7)` uses the diamond operator so the compiler infers the type argument.
- `String` is not a subtype of `Number`, so `NumberBox<String>` is **invalid**.

### A Bound Is a Type Condition, Not a Value Condition

`NumberBox<Integer>` accepts Integer values of varying magnitudes, including negative ones; the `extends Number` bound **does not automatically check** range, overflow, positivity, or business rules. To impose value conditions, add constructor validation or a separate domain value object.

## 3. Case Without a Bound: The Compiler Does Not Know the Method

The following code **intentionally does not compile**:

```java
class BadBox<T> {
    T value;

    double twice() {
        return value.doubleValue() * 2;
        // Error: Object does not guarantee doubleValue().
    }
}
```

Fix it by declaring `class GoodBox<T extends Number>` and writing the corresponding body. The compiler then allows `doubleValue()`.

You **should not** use a cast `((Number) value).doubleValue()` on an unbounded `T` if the class only makes sense for Number. Casting pushes errors to runtime and leaves the API signature lacking information. A proper bound moves most of that checking to compile time.

## 4. `extends` with an Interface Does Not Mean a Java Class Must `extends` the Interface

Declaration:

```java
class Holder<T extends Comparable<T>> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    boolean lessThan(T other) {
        return value.compareTo(other) < 0;
    }
}
```

`Comparable<T>` is an **interface**, but the bound must still be written with `extends`, **not `implements`**, in the type parameter list.

A concrete class such as `String` implements `Comparable<String>`, so `Holder<String>` is valid.

Create **`InterfaceBoundDemo.java`**:

```java
class Holder<T extends Comparable<T>> {
    private final T value;

    Holder(T value) {
        this.value = value;
    }

    boolean comesBefore(T other) {
        return value.compareTo(other) < 0;
    }
}

public class InterfaceBoundDemo {
    public static void main(String[] args) {
        Holder<String> words = new Holder<>("apple");
        Holder<Integer> numbers = new Holder<>(2);

        System.out.println(words.comesBefore("banana"));
        System.out.println(numbers.comesBefore(1));
    }
}
```

```bash
javac InterfaceBoundDemo.java
java InterfaceBoundDemo
```

```text
true
false
```

### Meaning

`T extends Comparable<T>` constrains `T` to be comparable with **the same T** via `compareTo(T)`. Each method call is still checked by the compiler for the corresponding type parameter.

Not every class that “has a concept of comparison” implements `Comparable<T>`. If the domain uses an external `Comparator<T>` instead of natural order, the design should accept a comparator and may not need a comparable bound.

## 5. When There Are Multiple Bounds, Use `&` Instead of a Comma

Syntax:

```java
class Example<T extends BaseClass & InterfaceOne & InterfaceTwo> {
}
```

This is a **syntax pattern**; the types are given suitable placeholder names.

The `&` symbol represents an **intersection of constraints**: a type argument must satisfy **all** bound types **simultaneously**. This is **not a bitwise AND operation** at runtime, even though it also uses the `&` character.

**Do not use**:

```java
// class Wrong<T extends Number, Comparable<T>> { }
// Error: a comma separates type parameters,
// not the bounds of a single type parameter.
```

Correct syntax:

```java
class NumericComparable<T extends Number & Comparable<T>> {
}
```

Multiple separate type parameters can be written using commas, with each parameter having its own bound:

```java
class Pair<K extends Comparable<K>, V extends Number> {
}
```

### Distinguishing the Symbols

- `,` between `K` and `V`: **two different type parameters**.
- `&` between Number and Comparable: **multiple bounds of the same T**.
- `extends` appears **once before the bound list of each type parameter**.

## 6. Runnable Example: Number and Comparable Together

Create **`MultipleBoundsDemo.java`**:

```java
class NumericRange<T extends Number & Comparable<T>> {
    private final T minimum;
    private final T maximum;

    NumericRange(T minimum, T maximum) {
        if (minimum.compareTo(maximum) > 0) {
            throw new IllegalArgumentException(
                    "min must not exceed max");
        }
        this.minimum = minimum;
        this.maximum = maximum;
    }

    boolean contains(T value) {
        return minimum.compareTo(value) <= 0
                && value.compareTo(maximum) <= 0;
    }

    double widthAsDouble() {
        return maximum.doubleValue()
                - minimum.doubleValue();
    }
}

public class MultipleBoundsDemo {
    public static void main(String[] args) {
        NumericRange<Integer> integers =
                new NumericRange<>(1, 5);
        NumericRange<Double> decimals =
                new NumericRange<>(1.5, 4.0);

        System.out.println(integers.contains(3));
        System.out.println(integers.contains(9));
        System.out.println(decimals.widthAsDouble());
    }
}
```

```bash
javac MultipleBoundsDemo.java
java MultipleBoundsDemo
```

```text
true
false
2.5
```

Explanation:

1. `Integer` and `Double` are both subtypes of Number and implement `Comparable` with their respective types.
2. `minimum.compareTo(maximum)` uses the contract from `Comparable<T>`.
3. `doubleValue()` uses the contract from `Number`.
4. The compiler checks both requirements **on the same type argument**.
5. The constructor also checks the **value condition** `minimum <= maximum`. The bound only checks the type, so constructor validation is still needed.

### Limitations of the Example

`doubleValue()` can lose precision for some Number subtypes. `widthAsDouble` here is an illustrative measurement, not an exact algorithm for all numeric domains, currency, or big integers. Generic bounds do not guarantee no overflow, no NaN, or no arithmetic errors.

## 7. Important Ordering Rule: The Class Bound Must Come First

If a type parameter has both a class bound and interface bounds, **the class bound must be the first element**:

```java
class Good<T extends Number & Comparable<T>> {
}
```

The following snippet is **intentionally incorrect**:

```java
// class Bad<T extends Comparable<T> & Number> { }
// Error: Number is a class, yet it comes after an interface.
```

The compiler does not allow placing a class type in the additional bounds after `&`.

**There can be only interfaces:**

```java
class Worker<T extends Runnable & AutoCloseable> {
}
```

This is a valid declaration: Runnable and AutoCloseable are both interfaces, even though the actual class providing their implementations may be complex.

**Two arbitrary superclasses cannot be used:**

```java
// class Impossible<T extends java.util.ArrayList<String>
//                    & java.util.HashSet<String>> { }
// Error: there cannot be a second class bound after &.
```

Java only allows one class bound at the front; additional bounds must be interface types. This aligns with Java's principle that **multiple inheritance of classes is not supported**.

## 8. Why Only One Class Bound but Multiple Interfaces?

A Java class can extend only **one class** at a time, but it can implement multiple interfaces. Multiple bounds express the same rule at the type parameter level.

For example, `T extends AbstractEntity & Auditable & Serializable` means:

- T is a subtype of AbstractEntity.
- T also implements Auditable.
- T also satisfies Serializable.
- The compiler can use the members accessible from those bounds.

The signature does not require T to be AbstractEntity itself; a **subclass** of AbstractEntity implementing the appropriate interfaces is also accepted.

**Do not confuse with composition:** Multiple bounds only describe type capabilities; they do not automatically generate objects, add methods, or inject services.

## 9. Complete Example: One Class Bound and Two Interface Bounds

Create **`EntityBoundsDemo.java`**:

```java
import java.io.Serializable;

abstract class BaseEntity {
    private final long id;

    BaseEntity(long id) {
        this.id = id;
    }

    public long id() {
        return id;
    }
}

interface Named {
    String name();
}

final class Customer extends BaseEntity
        implements Named, Serializable {
    private static final long serialVersionUID = 1L;

    private final String name;

    Customer(long id, String name) {
        super(id);
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}

class EntityBox<
        T extends BaseEntity & Named & Serializable> {
    private final T value;

    EntityBox(T value) {
        this.value = value;
    }

    String summary() {
        return value.id() + ":" + value.name();
    }

    boolean isSerializable() {
        return value instanceof Serializable;
    }
}

public class EntityBoundsDemo {
    public static void main(String[] args) {
        EntityBox<Customer> box =
                new EntityBox<>(new Customer(7, "An"));

        System.out.println(box.summary());
        System.out.println(box.isSerializable());
    }
}
```

```bash
javac EntityBoundsDemo.java
java EntityBoundsDemo
```

```text
7:An
true
```

**Reading the bound part by part:**

- `BaseEntity` is the **class bound**, placed first.
- `Named` is an interface with `name()`.
- `Serializable` is a marker interface; it has no business methods to call, yet it still constrains type arguments.
- `Customer` extends BaseEntity and implements Named/Serializable, so it is valid.
- In `summary()`, `value.id()` and `value.name()` are permitted by the compiler.
- `instanceof Serializable` is only an illustrative check; the generic declaration already guarantees that the type parameter satisfies this interface at compile time under type-safe usage.

**Be careful with Serializable:** Implementing Serializable does not automatically mean serializing every object will succeed. The object graph and specific serialization rules still determine runtime behavior.

## 10. Multiple Interface Bounds: Intersection of Capabilities

If no class bound is needed, we can write:

```java
class Screen<T extends Named & Described> {
}
```

The two interfaces can be used in any valid order (subject to constraints regarding erasure/conflicts and generic signatures), but **the first bound still matters in type erasure**, which will be discussed later.

Create **`InterfaceIntersectionDemo.java`**:

```java
interface Named {
    String name();
}

interface Described {
    String description();
}

record Product(String name, String description)
        implements Named, Described {
}

class DetailView<T extends Named & Described> {
    private final T value;

    DetailView(T value) {
        this.value = value;
    }

    String render() {
        return value.name() + " - "
                + value.description();
    }
}

public class InterfaceIntersectionDemo {
    public static void main(String[] args) {
        DetailView<Product> view = new DetailView<>(
                new Product("Book", "Java"));

        System.out.println(view.render());
    }
}
```

```bash
javac InterfaceIntersectionDemo.java
java InterfaceIntersectionDemo
```

```text
Book - Java
```

`Product` is a final record implementing both interfaces. `DetailView<T>` does not need to know the concrete class Product to call `name()` or `description()`.

**Design benefit:** Instead of creating a combined interface just to use in one place, intersection bounds can express “must satisfy both contracts” directly in the generic API. However, if that combination is a **recurring domain concept**, a named interface such as `CatalogItem extends Named, Described` may be easier to read and maintain.

## 11. An Intersection Bound Differs from Choosing One of Two Types

`T extends A & B` means T must satisfy **A and B**, not A **or** B. Java generics do not have union syntax such as:

```java
// class Either<T extends A | B> { }
// There is no such union type parameter syntax.
```

If the API accepts two independent kinds, consider a common interface, overloads, a sealed hierarchy, or designing two generic methods.

### Visualizing with a Table

| Type argument | Implements A | Implements B | Valid for `T extends A & B` |
| --- | --- | --- | --- |
| First | Yes | Yes | Yes |
| Second | Yes | No | No |
| Third | No | Yes | No |
| Fourth | No | No | No |

**Usefulness:** The compiler prevents creating `DetailView<Something>` if Something does not provide both capabilities.

## 12. A Bound Does Not Automatically Guarantee Every Method Is Public

A bound grants access to members that are actually **accessible** at the location where the generic class is used. A private method of a bound class does **not** become callable merely because T extends that class.

Example:

```java
class Base {
    public void open() {
    }

    private void secret() {
    }
}

class Wrapper<T extends Base> {
    void invoke(T value) {
        value.open();
        // value.secret(); // Error: private method.
    }
}
```

This is a valid declaration as long as the erroneous line remains commented out.

Access modifiers on methods/fields still apply in full. **Bounds do not bypass encapsulation**.

For interface methods, the contract is usually public; a concrete class implementing the interface must provide a public implementation for public methods.

## 13. A Type Argument Must Satisfy the Entire Bound, Not Just Part of It

Given:

```java
class NumericComparable<T extends Number & Comparable<T>> {
}
```

Commonly valid arguments:

- `Integer`: extends Number, implements Comparable<Integer>.
- `Double`: extends Number, implements Comparable<Double>.
- `Long`: extends Number, implements Comparable<Long>.
- `BigDecimal`: extends Number, implements Comparable<BigDecimal>.

Invalid arguments:

- `String`: implements Comparable<String> but does not extend Number.
- `Number`: is the class bound, yet **does not implement Comparable<Number>**.
- A Number subclass that only implements Comparable with a type incompatible with `T` may fail to satisfy this bound.

**Intentional error examples:**

```java
// NumericComparable<String> first; // String is not a Number.
// NumericComparable<Number> second; // Number is not a Comparable<Number>.
```

Note that having `Number` as a bound does not mean **Number itself** necessarily satisfies all the interface bounds. The compiler checks the type argument **across the entire intersection**.

## 14. Bounds on Generic Methods, Not Just Classes

A generic method can declare a type parameter right before the return type:

```java
static <T extends Comparable<T>> T larger(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

This is an **illustrative method snippet** inside a class.

`<T extends Comparable<T>>` is the method's generic type parameter declaration. It is **not** part of the return type T and is not a cast.

Create **`BoundedMethodDemo.java`**:

```java
public class BoundedMethodDemo {
    static <T extends Number & Comparable<T>>
    T larger(T left, T right) {
        return left.compareTo(right) >= 0 ? left : right;
    }

    public static void main(String[] args) {
        System.out.println(larger(7, 3));
        System.out.println(larger(2.5, 4.0));
    }
}
```

```bash
javac BoundedMethodDemo.java
java BoundedMethodDemo
```

```text
7
4.0
```

At each call, the compiler infers an appropriate T from the arguments and the bound. The method uses Comparable<T>; the Number bound in this example also expresses the numeric type domain, even though the body currently only needs compareTo. If you are only comparing generic objects, you can use a Comparable bound without Number.

### Note on Inference

If you pass two objects of different types such as Integer and Double, the compiler does **not** automatically guarantee that it will find a common T satisfying `Comparable<T>` for the call to be valid. Define clearly whether comparing different numeric types is accepted. Mixed-type comparisons may require `Comparator<Number>` or conversion to a common type with an explicit precision policy.

## 15. Static Methods Have Their Own Type Parameter and Do Not Use Class-Level T

A generic class:

```java
class Box<T extends Number> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    // static T twice(T input) { return input; }
    // Error: a static context cannot use class-level T.

    static <U extends Number> double twice(U input) {
        return input.doubleValue() * 2;
    }
}
```

The static method `twice` declares its own `U`, because a static member exists at the class level rather than being tied individually to each `Box<Integer>` or `Box<Double>`.

Create **`StaticBoundedMethodDemo.java`**:

```java
class Box<T extends Number> {
    private final T value;

    Box(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }

    static <U extends Number> double twice(U input) {
        return input.doubleValue() * 2;
    }
}

public class StaticBoundedMethodDemo {
    public static void main(String[] args) {
        Box<Integer> box = new Box<>(5);

        System.out.println(box.get());
        System.out.println(Box.twice(2.5));
    }
}
```

```bash
javac StaticBoundedMethodDemo.java
java StaticBoundedMethodDemo
```

```text
5
5.0
```

**Two independent scopes:** T is the class parameter; U is the static generic method parameter. Using the same letter for both can also create hard-to-read shadowing, so name them separately when worthwhile.

## 16. A Class with Multiple Type Parameters Having Different Bounds

A class can accept multiple independent type arguments:

```java
class Pair<
        K extends Comparable<K>,
        V extends Number> {
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
```

`K` is bounded by Comparable<K>; `V` is bounded by Number; **there is no requirement that K and V be the same type**.

Create **`TwoParametersBoundDemo.java`**:

```java
class Pair<K extends Comparable<K>, V extends Number> {
    private final K key;
    private final V value;

    Pair(K key, V value) {
        this.key = key;
        this.value = value;
    }

    boolean before(K other) {
        return key.compareTo(other) < 0;
    }

    double numericValue() {
        return value.doubleValue();
    }
}

public class TwoParametersBoundDemo {
    public static void main(String[] args) {
        Pair<String, Integer> pair = new Pair<>("A", 7);

        System.out.println(pair.before("B"));
        System.out.println(pair.numericValue());
    }
}
```

```bash
javac TwoParametersBoundDemo.java
java TwoParametersBoundDemo
```

```text
true
7.0
```

Read the comma as the **boundary between two type parameters**. When you want each of the two parameters to have multiple bounds, write `K extends A & B` and `V extends C & D` inside the same angle brackets.

## 17. A Type Parameter Can Be Bounded by Another Type Parameter

An upper bound does not have to be a class or interface with a fixed name. Java supports dependent bounds:

```java
class Choice<T, U extends T> {
    private final T broad;
    private final U specific;

    Choice(T broad, U specific) {
        this.broad = broad;
        this.specific = specific;
    }

    T broad() {
        return broad;
    }

    U specific() {
        return specific;
    }
}
```

`U extends T` states that U must be a subtype of T. Here `extends T` is a single type-variable bound; it cannot be combined with multiple additional bounds afterward according to the JLS `TypeBound` syntax for a type variable.

Create **`DependentTypeParameterDemo.java`**:

```java
class Choice<T, U extends T> {
    private final T first;
    private final U second;

    Choice(T first, U second) {
        this.first = first;
        this.second = second;
    }

    T first() {
        return first;
    }

    T secondAsT() {
        return second;
    }
}

public class DependentTypeParameterDemo {
    public static void main(String[] args) {
        Choice<Number, Integer> choice =
                new Choice<>(2.5, 7);

        System.out.println(choice.first());
        System.out.println(choice.secondAsT());
    }
}
```

```bash
javac DependentTypeParameterDemo.java
java DependentTypeParameterDemo
```

```text
2.5
7
```

**Limitation:** Writing `<T, U extends T>` differs from merging two type parameters into one. U retains its own type; the compiler only knows that U belongs to the T family.

## 18. F-Bounded Polymorphism: A Bound Referencing T Itself

Common pattern:

```java
interface SelfOrdered<T extends SelfOrdered<T>> {
    int compare(T other);
}
```

This is a form of **recursive type bound** (*F-bounded polymorphism*). A type argument often has the ability to conform to a contract parameterized by itself.

A more common use case is:

```java
class SortedBox<T extends Comparable<T>> {
}
```

It tells the compiler that a T object has compareTo(T) instead of only compareTo(Object) under raw types.

### Do Not Overload the Model

A complex recursive bound can make error messages long and hard to understand. If the goal only requires a comparison based on an external ordering policy, accepting `Comparator<? super T>` can be simpler than forcing every domain type to implement Comparable.

## 19. Why Is `Comparable<? super T>` Sometimes More Flexible Than `Comparable<T>`?

A subclass can inherit the ability to compare against a **supertype**, without implementing `Comparable<Subclass>` directly.

Suppose:

```java
class Person implements Comparable<Person> {
    private final int age;

    Person(int age) {
        this.age = age;
    }

    @Override
    public int compareTo(Person other) {
        return Integer.compare(age, other.age);
    }
}

final class Student extends Person {
    Student(int age) {
        super(age);
    }
}
```

`Student` implements `Comparable<Person>` through Person, not `Comparable<Student>`.

The bound:

```java
<T extends Comparable<T>>
```

can exclude Student, whereas:

```java
<T extends Comparable<? super T>>
```

can accept Student because Comparable<Person> accepts the Person type, which is a supertype of Student.

Create **`ComparableSuperBoundDemo.java`**:

```java
class Person implements Comparable<Person> {
    private final int age;

    Person(int age) {
        this.age = age;
    }

    @Override
    public int compareTo(Person other) {
        return Integer.compare(age, other.age);
    }
}

final class Student extends Person {
    Student(int age) {
        super(age);
    }
}

public class ComparableSuperBoundDemo {
    static <T extends Comparable<? super T>>
    T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Student older = larger(new Student(22),
                               new Student(19));

        System.out.println(
                older.compareTo(new Person(20)) > 0);
    }
}
```

```bash
javac ComparableSuperBoundDemo.java
java ComparableSuperBoundDemo
```

```text
true
```

**Read the wildcard carefully here:** The bound of T still begins with `extends Comparable<...>`, while `? super T` sits **inside the type argument** of Comparable. This is not a syntax declaring `T super Person` (Java does not have such a lower-bounded type parameter form).

## 20. `T extends Number` Is Not the Same as `List<? extends Number>`

The two forms look similar, yet they solve two different kinds of problems:

- `<T extends Number>`: **declares a named type parameter T** and an upper bound.
- `List<? extends Number>`: **uses a wildcard argument** with an upper bound; the specific type name is hidden.

Example:

```java
class NumberBox<T extends Number> {
    private final T value;

    NumberBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

Alongside a method:

```java
static double sum(java.util.List<? extends Number> values) {
    double total = 0;
    for (Number number : values) {
        total += number.doubleValue();
    }
    return total;
}
```

The `sum` method can accept a `List<Integer>` or `List<Double>` and only needs to **read as Number**. However, `List<? extends Number>` does not allow adding an arbitrary Integer, because the actual list might be a List<Double>.

**Remember that `List<Integer>` is not a subtype of `List<Number>`**. Java generics are invariant with respect to type arguments; wildcards provide a way to express variance at call sites.

## 21. Program: Named Bound and Upper-Bounded Wildcard

Create **`NamedBoundVersusWildcardDemo.java`**:

```java
import java.util.List;

public class NamedBoundVersusWildcardDemo {
    static <T extends Number> double twice(T value) {
        return value.doubleValue() * 2;
    }

    static double sum(List<? extends Number> values) {
        double result = 0;
        for (Number value : values) {
            result += value.doubleValue();
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println(twice(3));
        System.out.println(sum(List.of(1, 2, 3)));
        System.out.println(sum(List.of(1.5, 2.5)));
    }
}
```

```bash
javac NamedBoundVersusWildcardDemo.java
java NamedBoundVersusWildcardDemo
```

```text
6.0
6.0
4.0
```

`twice` needs a type parameter T that can be used in multiple positions in the signature. `sum` only needs to read each element as Number, so a wildcard is convenient.

**Do not use a named T mechanically** when a method only needs a one-off wildcard. Conversely, when a type relationship between parameters/return type is needed, a named type parameter may be necessary.

## 22. `? super` Is a Wildcard Lower Bound, Not a Declaration of T

Java allows:

```java
java.util.List<? super Integer> destination;
```

It can reference List<Integer>, List<Number>, or List<Object>. We **can add Integer** to that list; reading from it only guarantees Object.

You cannot declare:

```java
// class Wrong<T super Integer> { }
// Error: type parameter declarations do not use super.
```

Create **`WildcardSuperDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WildcardSuperDemo {
    static void addNumbers(List<? super Integer> values) {
        values.add(2);
        values.add(3);
    }

    public static void main(String[] args) {
        List<Number> numbers = new ArrayList<>();
        addNumbers(numbers);

        System.out.println(numbers);
        System.out.println(numbers.get(0) instanceof Integer);
    }
}
```

```bash
javac WildcardSuperDemo.java
java WildcardSuperDemo
```

```text
[2, 3]
true
```

**PECS:** “Producer Extends, Consumer Super” is a rule of thumb for wildcards: a read-only source of the T family uses `? extends T`; a destination receiving T uses `? super T`. This is **not a replacement** for defining the type parameters of a generic class.

## 23. A Bounded Generic Class Does Not Create Inheritance Relationships Between Parameterizations

Example:

```java
class NumberBox<T extends Number> {
    T value;

    NumberBox(T value) {
        this.value = value;
    }
}
```

`Integer` is a subtype of `Number`, yet `NumberBox<Integer>` is **not** a subtype of `NumberBox<Number>`.

This matters because generic classes are **invariant** with respect to type arguments, even when the type parameter is bounded.

**Intentionally incorrect code:**

```java
NumberBox<Integer> integers = new NumberBox<>(1);
// NumberBox<Number> numbers = integers; // Error.
```

To write an API that accepts any box whose type argument belongs to Number, consider:

```java
static void inspect(NumberBox<? extends Number> box) {
    System.out.println(box.value.doubleValue());
}
```

This is an **illustrative method snippet** where the NumberBox class and field access permissions match within the same context. In a real API, you should use a getter instead of accessing a package-private field.

**In summary:** A type parameter bound restricts type arguments; a wildcard determines how **a parameterized type** can be used flexibly at the call site.

## 24. Type Erasure: The First Bound Affects Bytecode

Java generics are largely implemented through **type erasure**. When erased, a type variable is replaced by **the erasure of its leftmost bound**:

- `T` with no explicit bound → erased to `Object`.
- `T extends Number` → erased to `Number`.
- `T extends Number & Comparable<T>` → erased to `Number`.
- `T extends Named & Described` → erased to `Named` if Named is first.

When members from subsequent bounds are needed, the compiler can emit casts/bridge methods or the necessary bytecode to preserve the intended semantics.

**Important:** Multiple bounds do not cause the JVM at runtime to automatically generate a separate “NumberAndComparable” class. This is a **compile-time intersection constraint**.

The order of interfaces after the first bound does not change the requirement to “satisfy all”, but it can affect the **erased signature** if another interface becomes the leftmost bound. Do not arbitrarily reorder public bounds without considering binary/API compatibility.

## 25. Reflection Illustrating Erasure of the First Bound

Create **`BoundErasureReflectionDemo.java`**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.TypeVariable;

class NumberHolder<T extends Number & Comparable<T>> {
    T value;
}

public class BoundErasureReflectionDemo {
    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field field =
                NumberHolder.class.getDeclaredField("value");
        TypeVariable<?> parameter =
                NumberHolder.class.getTypeParameters()[0];

        System.out.println(field.getType() == Number.class);
        System.out.println(parameter.getBounds().length);
        System.out.println(
                parameter.getBounds()[0] == Number.class);
    }
}
```

```bash
javac BoundErasureReflectionDemo.java
java BoundErasureReflectionDemo
```

```text
true
2
true
```

- The field declared with type variable T has runtime raw field type `Number` when observed via `Field.getType()`.
- Reflection can still read the generic declaration using `getTypeParameters/getBounds`.
- Two bounds exist in the generic metadata: Number and Comparable<T>, while the erased field type is the leftmost Number.

Do not confuse **runtime erasure** with **compile-time generic type checking**. The compiler still flags `NumberHolder<String>` as invalid even though the field's runtime metadata does not store each concrete type argument.

## 26. Bound Ordering Can Affect Method Overloading After Erasure

Look at the following two methods:

```java
class ErasureClash {
    <T extends Number> void process(T value) {
    }

    // void process(Number value) {
    // }
}
```

This is an **illustrative snippet**: if the second method is uncommented, the two signatures clash after erasure, because the first generic method erases parameter T to Number.

**Do not solve this by renaming T to U**. Erasure is based on bounds and signatures, not type parameter names.

### How to Fix

- Use different method names when the two operations have different semantics.
- Or choose a design with only a single valid overload.
- Avoid creating a generic method merely because it “looks flexible” when its erased signature collides with a needed method.

**Review principle:** For public APIs, bounds can affect overloaded methods, bridge methods, and compatibility; the impact is not limited to the source level.

## 27. `new T()` Remains Invalid Even When T Has a Class Bound

Even when:

```java
class Factory<T extends Number> {
    // T create() {
    //     return new T(); // Error.
    // }
}
```

the compiler does not know which constructor a concrete T has, and erasure does not preserve the type information needed for instantiation. A bound does **not** create a constructor guarantee.

### Approach with `Supplier<T>`

Create **`BoundedFactoryDemo.java`**:

```java
import java.util.Objects;
import java.util.function.Supplier;

class Factory<T extends Number> {
    private final Supplier<? extends T> creator;

    Factory(Supplier<? extends T> creator) {
        this.creator = Objects.requireNonNull(creator);
    }

    T create() {
        return creator.get();
    }
}

public class BoundedFactoryDemo {
    public static void main(String[] args) {
        Factory<Integer> factory = new Factory<>(() -> 7);

        System.out.println(factory.create());
    }
}
```

```bash
javac BoundedFactoryDemo.java
java BoundedFactoryDemo
```

```text
7
```

`Supplier<? extends T>` represents a source returning T or a subtype of T. The `T extends Number` constraint is still preserved; the factory does not need reflection or an assumption of a no-argument constructor.

## 28. `instanceof T` Is Also Not a Usable Runtime Check

The following code is **intentionally incorrect**:

```java
class Tester<T extends Number> {
    boolean accepts(Object value) {
        // return value instanceof T; // Error: T is not reifiable.
        return value instanceof Number;
    }
}
```

`value instanceof Number` is valid because Number is a class type that exists at runtime, yet it only checks **Number**, without distinguishing `T=Integer` from `T=Double`.

### When You Need to Check the Exact T at Runtime

One design is to accept a `Class<T>` token:

Create **`RuntimeTypeTokenDemo.java`**:

```java
import java.util.Objects;

class TypedBox<T extends Number> {
    private final Class<T> type;

    TypedBox(Class<T> type) {
        this.type = Objects.requireNonNull(type);
    }

    boolean accepts(Object candidate) {
        return type.isInstance(candidate);
    }
}

public class RuntimeTypeTokenDemo {
    public static void main(String[] args) {
        TypedBox<Integer> box = new TypedBox<>(Integer.class);

        System.out.println(box.accepts(5));
        System.out.println(box.accepts(5.0));
    }
}
```

```bash
javac RuntimeTypeTokenDemo.java
java RuntimeTypeTokenDemo
```

```text
true
false
```

A Class token works well when T is a reifiable class type like Integer. It does not fully solve checking `List<String>` vs `List<Integer>` at runtime due to type erasure of nested generic arguments.

## 29. Array Creation with T Remains Restricted

Invalid code:

```java
class ArrayFactory<T extends Number> {
    // T[] create(int size) {
    //     return new T[size]; // Error: generic array creation.
    // }
}
```

A bound does not turn T into a reifiable runtime array component type. You can use an `IntFunction<T[]>` provided by the caller, or controlled reflection.

Create **`BoundedArrayFactoryDemo.java`**:

```java
import java.util.function.IntFunction;

class ArrayFactory<T extends Number> {
    private final IntFunction<T[]> maker;

    ArrayFactory(IntFunction<T[]> maker) {
        this.maker = maker;
    }

    T[] create(int size) {
        return maker.apply(size);
    }
}

public class BoundedArrayFactoryDemo {
    public static void main(String[] args) {
        ArrayFactory<Integer> factory =
                new ArrayFactory<>(Integer[]::new);

        Integer[] values = factory.create(3);

        System.out.println(values.length);
        System.out.println(
                values.getClass().getComponentType()
                        == Integer.class);
    }
}
```

```bash
javac BoundedArrayFactoryDemo.java
java BoundedArrayFactoryDemo
```

```text
3
true
```

The method reference `Integer[]::new` carries the runtime array component type information, whereas `new T[size]` is invalid.

## 30. Primitives Cannot Directly Serve as Generic Type Arguments

Invalid code:

```java
// NumberBox<int> box;
// Generic arguments do not accept primitive int.
```

Use the `Integer` wrapper:

```java
NumberBox<Integer> box = new NumberBox<>(5);
```

This is an illustrative snippet within a scope where NumberBox is already declared. Autoboxing converts primitive `5` into Integer.

**Bound limitation:** `Integer extends Number` satisfies the upper bound, yet `int` still cannot be used directly as a type argument. Generic type arguments are reference types.

## 31. Bounds Can Be Practically Empty Even When Syntactically Valid

A syntactically valid declaration can be so narrow that virtually no concrete type satisfies all constraints.

Example:

```java
class Strange<T extends Number & Runnable> {
}
```

This class+interface multiple-bound declaration is structurally valid, yet standard numeric wrappers such as Integer/Double do not implement Runnable. The API may have no useful type argument in the domain.

**Do not assume the compiler generates an implementation for a missing capability.** A candidate type must genuinely be a subtype of all bounds.

### Use Interfaces Purposefully

If you only want a number that can convert to double, `T extends Number` is enough. If ordering is also needed, add a Comparable bound. If auditing is needed, add an Auditable interface. **Each bound should express an actual usage requirement**, not decoration.

## 32. Two Interface Bounds Can Conflict with Each Other

The compiler does not allow a type variable to be forced to become a subtype of two incompatible parameterizations of **the same generic interface**.

**Intentionally incorrect** code:

```java
// class Bad<T extends Comparable<String>
//             & Comparable<Integer>> {
// }
```

The same generic interface `Comparable` appears with different type arguments, leading to erasure and contract conflicts.

Similarly, you cannot duplicate interface bounds where the compiler sees that they share the same erasure.

### How to Handle It

- Choose **one unified Comparable contract**.
- Or accept an external `Comparator` for the comparison policy.
- If the domain truly has two different comparisons, create **two differently named interfaces** with differently named methods.

You cannot “force the compiler to accept it” using raw types or unchecked casts while preserving type safety.

## 33. A Bound Is Satisfied Directly or Indirectly

If class `Employee` extends `PersonBase` and `PersonBase` implements `Named`, then Employee is still a subtype of Named even without writing `implements Named` directly on the Employee declaration.

A bound checks the **subtype relationship**, without requiring the text in the class declaration to directly contain the name of every interface.

Create **`InheritedInterfaceBoundDemo.java`**:

```java
interface Named {
    String name();
}

class PersonBase implements Named {
    private final String name;

    PersonBase(String name) {
        this.name = name;
    }

    @Override
    public String name() {
        return name;
    }
}

final class Employee extends PersonBase {
    Employee(String name) {
        super(name);
    }
}

class NameBox<T extends Named> {
    private final T value;

    NameBox(T value) {
        this.value = value;
    }

    String show() {
        return value.name();
    }
}

public class InheritedInterfaceBoundDemo {
    public static void main(String[] args) {
        NameBox<Employee> box =
                new NameBox<>(new Employee("Lan"));

        System.out.println(box.show());
    }
}
```

```bash
javac InheritedInterfaceBoundDemo.java
java InheritedInterfaceBoundDemo
```

```text
Lan
```

`Employee` satisfies Named through its superclass PersonBase. This is a normal inheritance relationship; the type argument does not need to implement the interface **directly** on the same source line.

## 34. Bounds Are Not Per-Instance Runtime Validation

Even when `T extends Number`, code can pass `null` at runtime:

```java
NumberBox<Integer> box = new NumberBox<>(null);
```

This is a valid statement if the NumberBox constructor does not forbid null. Later calling `box.twice()` can throw a `NullPointerException` because it accesses a method on null.

**A bound does not guarantee non-null.** When the domain forbids null, use `Objects.requireNonNull(value)` in the constructor.

Similarly, a Number object can contain NaN/Infinity if the type and value permit them. `T extends Number & Comparable<T>` does not verify precision, range, or business invariants.

### Data Types and Validation Have Different Responsibilities

- Bound → **which types can be used**.
- Constructor validation → **which values are valid**.
- Immutability/copying → **from where state can change**.
- Domain methods → **business logic**.

Do not replace validation with an overly general generic bound.

## 35. When Is an Interface Bound Alone Enough?

If the API only calls `name()`, use:

```java
interface Named {
    String name();
}

class NamePrinter<T extends Named> {
    void print(T value) {
        System.out.println(value.name());
    }
}
```

Instead of requiring `T extends SomeBaseClass & Named` when SomeBaseClass serves no purpose, an interface bound is lighter, allowing implementations to be records/final classes or subclasses of a different superclass.

**API benefit:** An interface targets capability and avoids locking down the user's class inheritance tree. In Java, a class has only one superclass, so adding a class bound to a public API can significantly restrict clients.

## 36. When Are Multiple Bounds More Useful Than Creating a New Interface?

Suppose a helper only operates on objects that are both `Named` and `Timed`. If the requirement appears in only a few generic methods, write:

```java
static <T extends Named & Timed> String label(T value) {
    return value.name() + ":" + value.time();
}
```

This is an **illustrative code snippet**, requiring the `Named` and `Timed` interfaces in the application.

If many APIs all need that same combination, you can define:

```java
interface TimedNamed extends Named, Timed {
}
```

Then use `T extends TimedNamed`.

**Design note:** The two approaches are not completely interchangeable in terms of the set of accepted type arguments. `T extends Named & Timed` accepts any class implementing both Named and Timed, **without needing** to declare that it implements TimedNamed. Conversely, `T extends TimedNamed` only accepts types belonging to the TimedNamed interface. Choose based on contract meaning and applicability.

## 37. Multiple Bounds and Dependencies on Implementations from Other Libraries

Suppose a library publishes:

```java
class Handler<T extends FrameworkBase & PluginCapability> {
}
```

This is an **illustrative pattern** with FrameworkBase as a class and PluginCapability as an interface.

It requires plugin objects to both extend FrameworkBase and implement PluginCapability. This can make things difficult for clients if a plugin class already needs to extend another superclass.

A less restrictive approach:

```java
class Handler<T extends PluginCapability> {
}
```

or a non-generic interface parameter if no return-type relationship is needed.

**API design rule:** Do not add a class bound merely to use a convenience method of that class if an interface can express the right capability and keep the API more flexible.

## 38. Overly Strong Bounds Can Cause Type Inference to Fail

Suppose a method requires:

```java
static <T extends Number & Comparable<T>>
T min(T first, T second) {
    return first.compareTo(second) <= 0 ? first : second;
}
```

`min(1,2)` is valid because both are Integer. `min(1.5,2.0)` is valid because both are Double. However, for the call `min(1,2.0)`, you cannot assume the compiler will automatically choose a common T that satisfies all the bounds; type inference may report an error.

**Do not solve this with a raw type cast** to bypass type safety. If the business logic needs mixed numeric types, choose a common representation and a concrete conversion policy:

- Convert to `BigDecimal` if appropriate decimal semantics are required and the inputs have conversion rules.
- Use `double` if precision loss and special NaN/Infinity values are acceptable.
- Accept a `Comparator` and a fixed domain data type if ordering is not natural.

Generic bounds only state that **a type satisfies a contract**; they do not perform numeric promotion like primitive arithmetic expressions in all cases.

## 39. Generic Methods with `Comparator<? super T>` Instead of a Comparable Bound

When a type has no natural ordering, the caller can supply the comparison.

Create **`ComparatorAlternativeDemo.java`**:

```java
import java.util.Comparator;

record Task(String title, int priority) {
}

public class ComparatorAlternativeDemo {
    static <T> T larger(T a, T b,
                         Comparator<? super T> comparator) {
        return comparator.compare(a, b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Comparator<Task> byPriority =
                Comparator.comparingInt(Task::priority);

        Task result = larger(
                new Task("A", 2),
                new Task("B", 5),
                byPriority);

        System.out.println(result.title());
    }
}
```

```bash
javac ComparatorAlternativeDemo.java
java ComparatorAlternativeDemo
```

```text
B
```

`Task` does not implement Comparable. The `larger` method still works because the caller provides Comparator<? super T>. Type parameter T **does not need to extend Comparable<T>**.

**Design comparison:**

- `Comparable` bound: requires a **natural order** defined on the type.
- `Comparator` parameter: allows **multiple ordering policies** external to the type.
- With multiple views/orderings, Comparator can be clearer and avoids forcing domain classes to implement an unnecessary interface.

## 40. Bounded Generic Constructors Also Exist

Not only classes and methods have type parameters; a constructor can declare its own generic parameter.

Create **`GenericConstructorDemo.java`**:

```java
class Reading {
    private final double number;

    <T extends Number> Reading(T number) {
        this.number = number.doubleValue();
    }

    double number() {
        return number;
    }
}

public class GenericConstructorDemo {
    public static void main(String[] args) {
        Reading a = new Reading(5);
        Reading b = new Reading(2.5);

        System.out.println(a.number());
        System.out.println(b.number());
    }
}
```

```bash
javac GenericConstructorDemo.java
java GenericConstructorDemo
```

```text
5.0
2.5
```

The constructor `<T extends Number> Reading(T number)` has its own type parameter T. The Reading class itself is **not generic**. This is a useful mechanism when only the initialization operation needs a type constraint; there is no need to turn the entire class into `Reading<T>`.

## 41. Type-Variable Bounds and Boxing at the Call Site

Java generic classes do not accept primitive type arguments:

```java
// NumberBox<int> invalid; // Error.
NumberBox<Integer> valid = new NumberBox<>(7);
```

In the program, autoboxing allows the int expression `7` to be boxed into Integer when passed to the constructor expecting T = Integer.

**Do not infer that generic T becomes a primitive at runtime.** Generics still use reference types and have type erasure, even though the compiler can support boxing/unboxing at the call site.

If processing large quantities of primitives where performance matters, consider primitive-specialized APIs such as `IntStream` or specialized collections, rather than expecting bounded generics to avoid boxing on their own.

## 42. Self-Referential Type Parameters and Subclasses: Be Careful with Semantics

The pattern:

```java
class Base<T extends Base<T>> {
    T self() {
        throw new UnsupportedOperationException();
    }
}
```

is a syntactically valid self-referential bound. It expresses a restriction on the type relationship, but it does not automatically guarantee that every subclass will “declare itself” in the ideal way if the author intentionally chooses another type argument that still satisfies the bound.

When building public APIs, do not use F-bounded generics as a runtime proof that `T` equals the actual subclass. It is a static relation, not a type token or reflection proof.

**Responsible usage guideline:** Only choose a recursive bound when it genuinely makes a fluent builder/comparison API more type-safe and tests ensure class-specific behavior.

## 43. Intersection Bounds Can Appear Alongside Wildcards

Example:

```java
class Summary<T extends Number & Comparable<T>> {
    // ...
}
```

At places receiving generic instances, an appropriate wildcard can still be used:

```java
static void show(Summary<?> summary) {
    // T is hidden at the call site, but T is still bounded at the declaration.
}
```

These are **illustrative snippets**; the Summary class must be completely declared when running.

Wildcards do not remove the bounds already defined on T: `Summary<String>` is still invalid. However, from the perspective of a method receiving `Summary<?>`, not knowing the exact T reduces the type-safe operations that can be performed with T.

**Bottom line:** A bound checks type arguments right at the generic declaration; a wildcard controls how parameterized types are used at the call site. The two mechanisms work together rather than replacing each other.

## 44. Common Mistakes and How to Fix Them

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| `class C<T implements Runnable>` | A type parameter bound uses `extends` | `T extends Runnable` |
| `T extends A, B` | Commas separate type parameters | `T extends A & B` |
| `T extends Runnable & Number` | Class bound Number is placed afterward | `T extends Number & Runnable` |
| `T extends ClassA & ClassB` | Cannot have a second class after `&` | One class first, additional interfaces |
| `T super Number` | There is no lower-bounded type parameter | `? super Number` for a wildcard in an appropriate position |
| `NumberBox<String>` | String is not a subtype of Number | Use an appropriate type argument |
| `NumericComparable<Number>` | Number does not implement Comparable<Number> | Use Integer/Double or change the bound |
| `new T()` | T is erased and its constructor is unknown | `Supplier<T>` or a factory |
| `new T[10]` | Cannot directly create a generic array | `IntFunction<T[]>` or controlled reflection |
| `x instanceof T` | T is not reifiable | Use a runtime type token |
| `static T method(...)` with class-level T | Static members are not tied to a parameterization | Create `static <U extends ...>` |
| Expecting List<Integer> to be assignable to List<Number> | Generics are invariant | Use an appropriate wildcard/API |
| Treating `? extends Number` as identical to `T extends Number` | Wildcard and type parameter have different roles | Choose based on whether types need to be linked |
| Adding Comparable when only Number methods are needed | Unnecessary bounds make the API less flexible | Minimal bound |
| Multiple bounds with conflicting generic interfaces | Erasure/generic contracts conflict | Use a single suitable contract |
| Arbitrarily changing the leftmost bound | Can alter the erased signature | Check compatibility |
| Using raw types to bypass a bound | Loses compile-time checking / unchecked warnings | Keep parameterized types |
| Expecting a Number bound to validate values automatically | A bound only checks the type | Validate null/range/domain |
| Using a Comparable<T> bound when a subclass compares via its parent | Stricter than necessary | Consider Comparable<? super T> |
| Expecting mixed Integer and Double to compare automatically | No simple common T fits | Choose a conversion/comparator policy |
| Using a class bound when an interface suffices | Locks down the client's superclass | Small capability interface |
| Assuming erasure removes all compile-time safety | The compiler still checks generic declarations/usages | Distinguish compile time from runtime |

## 45. Self-Test: Verifying a Generic Type with Multiple Bounds

Create **`MultipleBoundsSelfTest.java`**:

```java
class Range<T extends Number & Comparable<T>> {
    private final T low;
    private final T high;

    Range(T low, T high) {
        if (low.compareTo(high) > 0) {
            throw new IllegalArgumentException("invalid");
        }
        this.low = low;
        this.high = high;
    }

    boolean contains(T value) {
        return low.compareTo(value) <= 0
                && value.compareTo(high) <= 0;
    }

    double width() {
        return high.doubleValue() - low.doubleValue();
    }
}

public class MultipleBoundsSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Range<Integer> a = new Range<>(2, 8);
        Range<Double> b = new Range<>(1.5, 4.0);

        check(a.contains(5), "integer in range");
        check(!a.contains(9), "integer out of range");
        check(b.contains(2.5), "double in range");
        check(b.width() == 2.5, "width");

        boolean invalid = false;
        try {
            new Range<>(5, 2);
        } catch (IllegalArgumentException ex) {
            invalid = true;
        }
        check(invalid, "constructor validation");

        System.out.println("multiple bounds PASS");
    }
}
```

```bash
javac MultipleBoundsSelfTest.java
java MultipleBoundsSelfTest
```

```text
multiple bounds PASS
```

`check` throws AssertionError directly when false, without needing to enable JVM `-ea`. The test uses the Double value 2.5, which has an exact binary representation, so as not to introduce rounding pitfalls into the example's comparisons.

**Additional checks to consider:** null policy, NaN/Infinity with Double, other type arguments, benchmarks if the doubleValue conversion matters, and testing methods that require specific interface capabilities.

## 46. Exercise 1: Adding an Interface Bound

Requirement: a `Report<T>` only accepts a type that has both `title()` and `score()`. There is no common superclass.

### Runnable Reference Solution

Create **`ReportIntersectionExercise.java`**:

```java
interface Titled {
    String title();
}

interface Scored {
    int score();
}

record Exam(String title, int score)
        implements Titled, Scored {
}

class Report<T extends Titled & Scored> {
    private final T value;

    Report(T value) {
        this.value = value;
    }

    String summary() {
        return value.title() + ":" + value.score();
    }
}

public class ReportIntersectionExercise {
    public static void main(String[] args) {
        Report<Exam> report =
                new Report<>(new Exam("Java", 9));

        System.out.println(report.summary());
    }
}
```

```bash
javac ReportIntersectionExercise.java
java ReportIntersectionExercise
```

```text
Java:9
```

**Explanation:** Exam implements both interfaces. Report does not need to know Exam specifically while still calling the members guaranteed by the intersection bound.

If a class only implements Titled without Scored, `Report<ThatClass>` does not compile.

## 47. Exercise 2: Finding Errors in Three Declarations

Examine the **intentionally incorrect** lines:

```java
// class A<T implements Runnable> {}
// class B<T extends Runnable & Number> {}
// class C<T extends Number, Comparable<T>> {}
```

Fix:

```java
class A<T extends Runnable> {}

class B<T extends Number & Runnable> {}

class C<T extends Number & Comparable<T>> {}
```

The three resulting declarations are **syntactically valid**; supplying a concrete type argument must still satisfy each bound.

**Reason:** Type parameters use extends; if there is a class bound, it comes first; multiple bounds for a single T are joined with `&`, not `,`.

## 48. Exercise 3: Choosing the Minimal Bound

A class only needs the `close()` method. Options:

```java
class A<T extends java.io.Closeable> {}
class B<T extends java.io.Closeable
        & java.io.Serializable> {}
```

If you are not storing the object using Java serialization or do not have a contract requiring Serializable, **A is usually better**: fewer constraints and it accepts more type arguments.

However, if serialization is an important API requirement (and is thoroughly designed/tested), B can make sense. The marker interface is only part of the condition; it does not guarantee that serializing all nested state will succeed.

## 49. Exercise 4: Handling a Subtype with Parent's Comparable

Given `Person implements Comparable<Person>` and `Student extends Person`. The bound `<T extends Comparable<T>>` may fail to accept Student. A more flexible formulation is:

```java
<T extends Comparable<? super T>>
```

**Why?** Comparable<Person> still accepts Student when calling compareTo because Student is a subtype of Person. The wildcard lower bound is inside the type argument of Comparable, not lower-bound syntax for T itself.

## 50. Checklist for Reviewing Generic Bounds

- [ ] Does the API really need a bound, or is an unbounded `T` sufficient?
- [ ] Is the bound a **class** or an **interface**, and is `extends` used properly?
- [ ] If there are multiple bounds, is `&` used?
- [ ] If there is a class bound, is the class **first**, followed only by interfaces?
- [ ] Are there no two class bounds or conflicting generic interfaces?
- [ ] Do sample type arguments satisfy **all** constraints?
- [ ] Can the compiler call the exact methods guaranteed by the bounds?
- [ ] Are private/protected methods accessed according to Java access rules?
- [ ] Is it understood that a bound does not automatically validate `null` or value ranges?
- [ ] Are you avoiding expecting `new T()`, `new T[]`, or `instanceof T` to work?
- [ ] If runtime type is needed, have you considered `Class<T>` or a factory?
- [ ] If arrays are needed, have you considered `IntFunction<T[]>`?
- [ ] If it is a static generic method, has it declared **its own type parameter**?
- [ ] If a method only reads from a collection, have you considered the `? extends` wildcard?
- [ ] If a method only writes to a collection, have you considered `? super`?
- [ ] Is it understood that `List<Integer>` is not a subtype of `List<Number>`?
- [ ] Is a `Comparable<T>` bound overly strict compared to `Comparable<? super T>`?
- [ ] If ordering is a changeable strategy, should it accept `Comparator<? super T>`?
- [ ] Does the order of the first bound affect the erased signature?
- [ ] Is there a risk of a method signature clash after erasure?
- [ ] Does each additional bound truly serve a necessary capability?
- [ ] Is the API locked to an overly specific superclass?
- [ ] Are there practical valid type arguments, without creating useless constraints?
- [ ] Are there unit tests for both type relationships and runtime invariants?
- [ ] Does the complete code have the right file name/public class, `javac`/`java` commands, and stable stdout?

## 51. Review Questions with Answers

**1.** What does `<T extends Number>` restrict?

*It only allows type arguments that are subtypes of Number; inside the generic body, accessible members of Number can be used.*

**2.** Can you write `<T implements Runnable>`?

*No. A type parameter bound must use extends, even when the bound is an interface.*

**3.** What symbol connects multiple bounds for the same T?

*The `&` symbol.*

**4.** If there are both a class bound and interface bounds, what is the order?

*The class bound must come first; the remaining bounds must be interfaces.*

**5.** Can you write `T extends ClassA & ClassB` with two classes?

*No.*

**6.** Does `T extends A & B` mean A or B?

*No; both must be satisfied.*

**7.** Why is `NumberBox<String>` wrong?

*String is not a subtype of Number.*

**8.** Why is `NumberBox<Integer>` valid?

*Integer extends Number.*

**9.** Is `NumericComparable<Number>` guaranteed to be valid?

*No; Number does not implement Comparable<Number>.*

**10.** What method does `T extends Comparable<T>` allow calling?

*`compareTo(T)` according to the interface contract and access rules.*

**11.** Can you have multiple type parameters with different bounds?

*Yes, for example `<K extends Comparable<K>, V extends Number>`.*

**12.** What is the syntax for declaring a bound on a generic method?

*`<T extends Bound> ReturnType method(T value)`.*

**13.** Can a static method directly use a generic class's T?

*No. A static generic method must declare its own type parameter if needed.*

**14.** Can a bounded T do `new T()`?

*No.*

**15.** Is `instanceof T` valid?

*No, because the type variable T is not reifiable.*

**16.** Is `new T[10]` valid?

*No; an array factory or a different design is needed.*

**17.** How do `T extends Number` and `? extends Number` differ?

*T declares a named type parameter; the wildcard represents an unknown type argument at the usage site.*

**18.** Is `List<Integer>` a subtype of `List<Number>`?

*No, due to generic invariance.*

**19.** What is `? super Integer` used for?

*A wildcard lower bound, convenient when a consumer needs to accept Integer.*

**20.** Can you declare `<T super Integer>`?

*No.*

**21.** What is the erasure of `T extends Number & Comparable<T>`?

*Number, the leftmost bound.*

**22.** What is the erasure of T without an explicit bound?

*Object.*

**23.** What can changing the order of interface bounds affect?

*Leftmost erasure and binary signatures, in addition to source constraints.*

**24.** Does a class implementing two interfaces through a superclass satisfy an intersection bound?

*Yes, if it is truly a subtype of both.*

**25.** When is `Comparable<? super T>` useful?

*When T can be compared using a supertype's Comparable, such as Student inheriting Comparable<Person>.*

**26.** When should `Comparator<? super T>` be used?

*When the ordering is defined by the caller, without wanting to force the type to have Comparable.*

**27.** Does a bound prevent null?

*No; the constructor/logic must validate it.*

**28.** Does a bound guarantee a positive Number?

*No, a bound only checks the type.*

**29.** Is a Serializable bound needed just to call name()?

*No; the Named interface is enough.*

**30.** What is the primary goal of multiple bounds?

*To ensure at compile time that a type argument simultaneously satisfies multiple capabilities, so the generic implementation can safely call members without casting.*

## 52. Standard References

- *Java Language Specification, Java SE 17, `4.4 Type Variables`*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.4 — defines bounds, multiple bounds, canonical grammar, and members of a type variable.
- *Java Language Specification, Java SE 17, `4.6 Type Erasure`*: https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6 — the leftmost bound determines erasure.
- *Oracle Java Tutorials, Bounded Type Parameters:* https://docs.oracle.com/javase/tutorial/java/generics/bounded.html — basic examples of extends/multiple bounds (older tutorial; check the Java 17 JLS for version-specific details).

---

**End-of-lesson takeaway:** For a generic class/method, **`<T extends Bound>`** requires the type argument to satisfy the **upper bound** and tells the compiler which members can be used on T. If a single T must satisfy multiple contracts, use **`T extends ClassBound & InterfaceA & InterfaceB`**: every condition must hold, **the class bound comes first** if present, and additional bounds are interfaces. The `&` symbol joins bounds of a single parameter; `,` separates multiple type parameters. Bounds do not instantiate objects on their own, do not guarantee valid values, do not make generics covariant, and are still subject to **type erasure**, where the **leftmost bound** determines the erased type. Distinguish a **named type parameter `T extends`** from the wildcards **`? extends`/`? super`** at the usage site, and impose only the bounds truly needed by the API to preserve type safety without overly restricting users.
