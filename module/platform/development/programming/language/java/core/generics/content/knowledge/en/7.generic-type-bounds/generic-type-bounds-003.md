# Multiple Bounds with `<T extends A & B>` in Java Generics

A generic type parameter is often declared simply as `<T>`. However, in many APIs, "`T` can be any reference type" is too broad: an algorithm may need an object that simultaneously inherits from a base class, implements an interface providing a name, and implements an interface supporting auditing. **Multiple bounds** solve this case with the syntax `<T extends A & B>`: a valid type argument must satisfy **all bounds simultaneously**.

For example, `<T extends Identified & Named & Auditable>` allows the code to use the members published by the contracts of `Identified`, `Named`, and `Auditable`, without manual casting. This is a form of **intersection type** at the type parameter level: `T` must belong to the intersection of the type sets described by the bounds.

This lesson focuses on the syntax, validity conditions of bounds, class/interface bound ordering, how the compiler checks and infers types, designing classes/methods using multiple bounds, common mistakes, and the effects of *type erasure*.

## 1. From a Single Bound to Multiple Bounds

Declaration without an explicit bound:

```java
class Box<T> {
    private final T value;

    Box(T value) {
        this.value = value;
    }
}
```

Here `T` has no special requirements beyond the general rules of Java Generics. You cannot call `value.name()` or `value.audit()` from this declaration, because the compiler does not know that every type `T` has those methods.

A single bound:

```java
interface Named {
    String name();
}

class NamedBox<T extends Named> {
    private final T value;

    NamedBox(T value) {
        this.value = value;
    }

    String name() {
        return value.name();
    }
}
```

`T extends Named` requires the type argument to implement `Named`. Even though `Named` is an **interface**, the type parameter bound syntax **still uses the `extends` keyword**, not `implements`.

If the algorithm also needs auditing capability:

```java
interface Auditable {
    void audit();
}

class NamedAuditedBox<T extends Named & Auditable> {
    private final T value;

    NamedAuditedBox(T value) {
        this.value = value;
    }

    void showAndAudit() {
        System.out.println(value.name());
        value.audit();
    }
}
```

Here `T` must satisfy both `Named` **and** `Auditable`. The calls `name()` and `audit()` are valid because the compiler knows both contracts apply to `T`.

The three declaration groups in this section are **illustrative snippets** that can be placed in a Java file with appropriate class naming rules; the following sections provide standalone `main` programs to run.

## 2. Standard Syntax of Multiple Bounds

General pattern of a type parameter:

```java
<T extends FirstBound & SecondBound & ThirdBound>
```

This is a **syntax pattern**, not a standalone Java statement.

Meaning:

- `T` is the name of the declared **type parameter**.
- `extends` introduces the list of *upper bounds*.
- `&` joins the bounds. Here `&` is **not a bitwise/boolean AND operator being evaluated**, but a separator in an *intersection bound* of types.
- Every bound must hold **at the same time**, not "satisfy A **or** B".
- The bound list applies to **one** type parameter `T`; it is different from declaring multiple independent type parameters `<T, U>`.

Valid forms:

```java
<T extends Named & Auditable>
<T extends Identified & Named>
<T extends Identified & Named & Auditable>
<T extends Number & Comparable<T>>
```

These are **declaration patterns**, and must be placed inside an appropriate generic class, interface, constructor, or method declaration context.

Several mandatory rules:

1. **At most one concrete or abstract class as a class bound**. If there is a class bound alongside interfaces, **the class bound must come first**.
2. The remaining bounds can be valid interfaces; Java does not allow a class to inherit from two unrelated classes simultaneously as a way of "multiple class inheritance".
3. Bounds can contain generic arguments, such as `Comparable<T>`.
4. Avoid repeating the same interface with conflicting parameterizations, because Java's type hierarchy does not allow a single type to inherit two different parameterizations of the same generic interface.
5. The compiler only accepts a set of bounds that can coexist under Java's inheritance and method-signature rules.

**Specifically:** if only interfaces are used, an interface can come first without needing to add `Object`. For example, `<T extends Named & Auditable>` is completely valid.

## 3. One Class Bound and Additional Interfaces

With `<T extends BaseEntity & Named & Auditable>`, `BaseEntity` is the **class bound** so it must come first; `Named` and `Auditable` are the **interface bounds**. The compiler allows calling accessible members provided by all three contracts:

```java
static <T extends BaseEntity & Named & Auditable>
void process(T entity) {
    System.out.println(entity.id());
    System.out.println(entity.name());
    entity.audit();
}
```

This snippet is an **illustrative method**: `BaseEntity`, `Named`, and `Auditable` must be declared with their corresponding methods, and the method must reside in a valid class. If only the `name()` and `audit()` capabilities are needed, you can write `<T extends Named & Auditable>` without requiring a class bound.

The lesson here is **combining multiple contracts to solve an algorithm**. Advanced structural rules—class order, final bounds, conflicting methods, duplicate generic interfaces after erasure—must be reviewed before publishing a public API, rather than assuming any list of bounds is valid.

## 4. Complete Java 17 Example: A Class Bound and Two Interfaces

Save the entire program as **`MultipleBoundsDemo.java`**:

```java
public class MultipleBoundsDemo {
    static abstract class Identified {
        private final String id;

        Identified(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }
    }

    interface Named {
        String name();
    }

    interface Auditable {
        void audit();
    }

    static final class Customer extends Identified
            implements Named, Auditable {
        private final String name;

        Customer(String id, String name) {
            super(id);
            this.name = name;
        }

        @Override
        public String name() {
            return name;
        }

        @Override
        public void audit() {
            System.out.println("audit:" + id());
        }
    }

    static <T extends Identified & Named & Auditable>
    String process(T value) {
        value.audit();
        return value.id() + "|" + value.name();
    }

    public static void main(String[] args) {
        Customer customer = new Customer("C-17", "An");
        System.out.println(process(customer));
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 MultipleBoundsDemo.java
java MultipleBoundsDemo
```

Exact output (`stdout`):

```text
audit:C-17
C-17|An
```

Read the example in order:

- `Identified` is the base class with the `id()` method.
- `Named` and `Auditable` are interfaces.
- `Customer extends Identified implements Named, Auditable` **satisfies all three conditions**.
- `<T extends Identified & Named & Auditable>` constrains a type parameter of **the `process` method**, without requiring the `MultipleBoundsDemo` class to become generic.
- From a variable `T value`, the compiler allows calling `value.id()`, `value.name()`, and `value.audit()`.
- When calling `process(customer)`, the `Customer` argument is a valid candidate for `T`.

This is the main benefit of multiple bounds: **avoiding using `Object` and manually casting to each interface** every time a behavior is needed.

## 5. "Satisfy Simultaneously" Differs from a Broad Contract

Suppose there is a class implementing only `Named`:

```java
// Illustrative snippet in the same scope as the Named interface:
final class ShortLabel implements Named {
    @Override
    public String name() {
        return "Short";
    }
}
```

`ShortLabel` does not automatically satisfy `Auditable`. If you call the method:

```java
// process(new ShortLabel()); // Compile error: does not satisfy all bounds
```

the compiler rejects it, even though the object has a completely valid `name()` method. The object must also extend `Identified` and implement `Auditable` if using the `process` version from the previous example.

Similarly, if a class extends `Identified` and implements `Auditable` but does not implement `Named`, it is still incompatible.

Multiple bounds do not check method names via *duck typing*: **there must genuinely be a Java type relationship** with the declared bounds. A class that happens to have a `name()` method but **does not `implements Named`** still does not satisfy the `Named` bound.

On the other hand, if the class bound is an abstract class, the type argument `T` can be a compatible concrete subclass. `T` does not have to match the exact class name in the bound clause.

## 6. Multiple Interfaces Without a Class Bound

A common case is needing two capabilities represented by two interfaces:

```java
interface Named {
    String name();
}

interface Coded {
    String code();
}

static <T extends Named & Coded> String format(T item) {
    return item.name() + "#" + item.code();
}
```

The snippet above consists of interface declarations and **an illustrative method placed inside a class**. `T` can be any class or type satisfying both interfaces simultaneously, without having to inherit from a common application-defined base class.

### Complete program

Create the file **`InterfaceBoundsDemo.java`**:

```java
public class InterfaceBoundsDemo {
    interface Named {
        String name();
    }

    interface Coded {
        String code();
    }

    record Product(String name, String code)
            implements Named, Coded { }

    static <T extends Named & Coded> String format(T item) {
        return item.name() + "#" + item.code();
    }

    public static void main(String[] args) {
        Product product = new Product("Pen", "P01");
        System.out.println(format(product));
    }
}
```

Run:

```bash
javac -encoding UTF-8 InterfaceBoundsDemo.java
java InterfaceBoundsDemo
```

`stdout`:

```text
Pen#P01
```

A Java `record` automatically generates `public` accessors `name()` and `code()`, satisfying the signatures of both interfaces. The `Product` type does not need to extend a specific class bound. This is a clean way to express "having both capabilities".

When an algorithm needs a new capability, you can often add an interface to the bounds instead of forcing every domain class into a deep class inheritance hierarchy.

## 7. Bounds Can Also Be Used in Generic Classes and Instance Methods

Multiple bounds are not only for `static` methods. You can constrain the type parameter of an entire class:

```java
interface Named {
    String name();
}

interface Auditable {
    void audit();
}

final class AuditedStore<T extends Named & Auditable> {
    private final T value;

    AuditedStore(T value) {
        this.value = value;
    }

    String describe() {
        value.audit();
        return value.name();
    }

    T get() {
        return value;
    }
}
```

This is an illustrative group of Java declarations. When writing `AuditedStore<Customer>`, the `Customer` type must satisfy both `Named` and `Auditable`. The constructor accepts `T`, the getter returns `T`, and instance methods are allowed to invoke both contracts.

Distinguish the two bound positions:

| Declaration | Scope of the constraint |
|---|---|
| `class AuditedStore<T extends Named & Auditable>` | Every valid use of `T` inside `AuditedStore`, including fields and instance methods. |
| `static <T extends Named & Auditable> void audit(T v)` | Only the type parameter `T` declared specifically for the `audit` method. |
| `<U extends Named & Auditable> U pick(U a, U b)` | Only the type parameter `U` of the instance method `pick`. |
| `interface Combined<T extends Named & Auditable>` | The type parameter contract of the `Combined` interface. |

A `static` method in a generic class **cannot directly use the class's type parameter**; if a static method needs type bounds, declare `<U extends ...>` on that method.

## 8. Combined Example: Generic Class and Generic Static Method

Create the file **`StoreBoundsDemo.java`**:

```java
public class StoreBoundsDemo {
    interface Named {
        String name();
    }

    interface Auditable {
        void audit();
    }

    record Entry(String name) implements Named, Auditable {
        @Override
        public void audit() {
            System.out.println("checked:" + name);
        }
    }

    static final class Store<T extends Named & Auditable> {
        private final T value;

        Store(T value) {
            this.value = value;
        }

        T get() {
            return value;
        }

        String verify() {
            value.audit();
            return value.name();
        }

        static <U extends Named & Auditable> Store<U> of(U value) {
            return new Store<>(value);
        }
    }

    public static void main(String[] args) {
        Store<Entry> store = Store.of(new Entry("invoice"));
        System.out.println(store.verify());
        System.out.println(store.get().name());
    }
}
```

Commands:

```bash
javac -encoding UTF-8 StoreBoundsDemo.java
java StoreBoundsDemo
```

`stdout`:

```text
checked:invoice
invoice
invoice
```

`T` of `Store<T>` and `U` of `Store.of(...)` are **two independent type parameters**, even though both have the `Named & Auditable` bound. The `of` factory can infer `U = Entry` and construct `Store<Entry>`.

The example also shows that placing multiple bounds on a class makes sense when **most of the class's behavior** requires those capabilities; placing them on a method can be more suitable when **only one algorithm** needs the combined capabilities.

## 9. Type Bounds Using Generic Interfaces

A bound itself can be a **parameterized generic interface**. For example, `Comparable<T>` expresses the ability to compare objects:

```java
static <T extends Number & Comparable<T>>
T max(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

This is an **illustrative method**, which must be placed in a valid class. `Number` is the class bound and **precedes** `Comparable<T>`, which is the interface bound.

The method can accept `Integer` or `Double` because both extend `Number` and implement `Comparable` with the matching type. However, the parameter type is not an arbitrary `Number`: abstract `Number` does not itself implement `Comparable<Number>`.

### Complete program

Create the file **`NumericBoundsDemo.java`**:

```java
public class NumericBoundsDemo {
    static <T extends Number & Comparable<T>> T max(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Integer greatestInt = max(3, 7);
        Double greatestDouble = max(2.5, 1.25);

        System.out.println(greatestInt);
        System.out.println(greatestDouble);
    }
}
```

Run:

```bash
javac -encoding UTF-8 NumericBoundsDemo.java
java NumericBoundsDemo
```

`stdout`:

```text
7
2.5
```

You cannot call `max("A", "B")` with this signature because `String` is not a `Number`. At the same time, calls with two incompatible numeric types can cause type inference to fail; express the contract explicitly instead of using casts or raw types.

### More flexible variant with `? super T`

In real-world APIs, the bound `Comparable<? super T>` is often more flexible:

```java
static <T extends Comparable<? super T>>
T maxComparable(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

`? super T` allows an object of type `T` to use a comparison contract with a compatible supertype. This is still **one bound on type parameter `T`**, containing a wildcard inside `Comparable`'s type argument. Do not confuse a wildcard **inside** a bound with the `&` multiple-bounds syntax.

## 10. Type Inference and Static Types of Expressions

The compiler checks multiple bounds based on **static types**, not merely the runtime type of an object:

```java
interface Named {
    String name();
}

interface Auditable {
    void audit();
}

static <T extends Named & Auditable> void use(T value) {
    System.out.println(value.name());
    value.audit();
}
```

Suppose `Customer` implements both `Named` and `Auditable`. When the variable is declared as `Customer`:

```java
Customer customer = /* a valid Customer */;
use(customer);
```

This is an illustrative snippet; the initialization must be replaced by an actual `Customer` constructor.

However, if **that exact same object** is held in a variable typed only as the `Named` interface:

```java
Named named = customer;
// use(named); // Compile error: static type Named does not guarantee Auditable
```

The error is logical: the compiler only knows `named` is `Named`; it cannot automatically deduce that every `Named` is also `Auditable`.

A better design is to preserve the concrete type until the call site, or introduce a meaningful combined business interface. If data comes from an untrusted source, validate it before casting; do not use an unchecked cast to "convince" the compiler that an object has unproven capabilities.

### A combined interface can simplify the API

```java
interface Named {
    String name();
}

interface Auditable {
    void audit();
}

interface AuditedNamed extends Named, Auditable { }

static <T extends AuditedNamed> void useCombined(T value) {
    System.out.println(value.name());
    value.audit();
}
```

The code group above is an **illustrative example**, in which `useCombined` must reside in a class. If the system has a stable business concept of "an object that is both named and auditable", defining `AuditedNamed` can make the API easier to read. However, Java enforces **nominal typing**: a class that only `implements Named, Auditable` does not automatically become `AuditedNamed`; to be used with `<T extends AuditedNamed>`, the class must implement that combined interface (directly or via inheritance).

This is the difference between multiple bounds (requiring multiple supertypes simultaneously without declaring a combined interface) and a newly named interface.

## 11. Multiple Bounds and Intersection Types

A parameter with `<T extends Named & Auditable>` is constrained by an **intersection type**. That means the compiler allows using operations from all bounds according to Java's rules.

However, **not every type position in Java allows writing `A & B` directly**:

```java
// Valid: list of bounds in a type parameter declaration.
static <T extends Named & Auditable> void inspect(T value) { }

// Invalid: wildcards do not support this multiple-bounds syntax.
// List<? extends Named & Auditable> items;
```

These are **illustrative declaration snippets**; the method must be placed in a class with the corresponding interfaces. If you want to accept a list containing only values satisfying both interfaces, you can declare a generic method:

```java
static <T extends Named & Auditable>
void inspectAll(java.util.List<T> values) {
    for (T value : values) {
        System.out.println(value.name());
        value.audit();
    }
}
```

This method uses `T` to maintain both constraints on the list elements simultaneously. It does not require Java to support the invalid `List<? extends Named & Auditable>` syntax.

Java also has **intersection cast** syntax such as `(Named & Auditable) object` in appropriate situations. A cast is a check/conversion in an expression and can fail at runtime if the object does not satisfy the required types; that is a different concept from bounding a type parameter so the compiler guarantees API calls.

## 12. Impact of Bound Order on Type Erasure

Java Generics are primarily checked at **compile time** and use **type erasure**. When a type parameter `T` has multiple bounds, **the erasure of `T` is the erasure of its first bound**.

Example:

```java
static <T extends Number & Comparable<T>> double asDouble(T value) {
    return value.doubleValue();
}
```

The first bound is `Number`, so the erasure of `T` is `Number`. The JVM-level signature of the corresponding parameter is essentially `Number`, even though the compiler at the source level also knows about the `Comparable<T>` requirement.

If there are only interfaces:

```java
static <T extends Named & Auditable> String label(T value) {
    return value.name();
}
```

the erasure of `T` is `Named` because it is the first bound. If an API is rewritten as `<T extends Auditable & Named>`, the erasure can change to `Auditable`. This affects the method descriptor/binary compatibility and can involve bridge methods when compiling class hierarchies.

### Do not arbitrarily reorder interface bounds in a public API

Consider two declarations:

```java
<T extends Named & Auditable>
<T extends Auditable & Named>
```

Both have the same logical intent "`T` must satisfy both interfaces", and both can be valid if the two interfaces are compatible. However, **the first bound differs**, so the erasure differs. In a published library, changing the order can produce differences in the JVM signatures of methods using `T`, causing issues when older client code is not recompiled.

When designing a public API, choose a meaningful order, keep it stable, and treat changing bounds as something that can affect compatibility, not just a cosmetic tweak.

Note that Java still stores generic signature information in the `Signature` attribute metadata of the class file for the compiler and other tools to inspect; "erasure" **does not mean all generic information is completely deleted from every part of the `.class` file**.

## 13. Bounds That Cannot Be Combined

Multiple bounds do not unconditionally permit any combination of types.

### 13.1. Two class bounds

```java
class ParentA { }
class ParentB { }

// Invalid: Java does not support two class bounds.
// class Invalid<T extends ParentA & ParentB> { }
```

If capabilities from multiple sources are needed, use appropriate interfaces or composition instead of trying to model multiple class inheritance.

### 13.2. Class bound not first

```java
interface Named {
    String name();
}

class Base { }

// Invalid: class bound Base must come first.
// class Invalid<T extends Named & Base> { }
```

The valid form is `<T extends Base & Named>`, provided the bounds can be satisfied together.

### 13.3. Two conflicting parameterizations of the same generic interface

```java
interface Handler<T> {
    void handle(T value);
}

// Invalid: two different parameterizations of the same Handler.
// class Invalid<T extends Handler<String> & Handler<Integer>> { }
```

A single Java type cannot simultaneously inherit `Handler<String>` and `Handler<Integer>`. Swapping the order of the two bounds cannot fix the error: the inheritance relationship itself is contradictory.

### 13.4. Incompatible method contracts

```java
interface TextResult {
    String result();
}

interface NumberResult {
    Integer result();
}

// Invalid: requires two methods with the same name/parameters but
// incompatible return types.
// class Invalid<T extends TextResult & NumberResult> { }
```

The two `result()` methods have the same name and parameter list, yet return types `String` and `Integer` have no compatible covariant return relationship. The compiler cannot define a `T` satisfying both method contracts validly.

The examples in this section are **error-demonstrating code**, not programs to run. Only uncomment them when you want to observe the compiler messages yourself.

## 14. Syntax Errors and How to Fix Them

| Mistake or misconception | Problem | How to fix |
|---|---|---|
| `<T implements A & B>` | Type parameter bound declarations do not use `implements`. | `<T extends A & B>`. |
| `<T extends A, B>` when wanting `T` to satisfy both A and B | Commas separate **multiple type parameters**, not multiple bounds. | `<T extends A & B>`. |
| `<T extends InterfaceA & ClassB>` | The class bound must come first. | `<T extends ClassB & InterfaceA>` if the types are compatible. |
| `<T extends ClassA & ClassB>` | At most one class bound is allowed. | Use one base class + interfaces. |
| Thinking `A & B` allows A **or** B | This is the intersection of both contracts. | The type argument must satisfy **both**. |
| A class has all the methods but does not `implements` the interface | Java uses nominal typing, not duck typing. | Declare the proper `implements`/`extends` relationships. |
| `List<? extends A & B>` | Wildcard bounds do not allow writing multiple bounds directly. | Use a method `<T extends A & B> void f(List<T>)`. |
| Calling a generic method via a variable typed only as `A` when `A & B` is required | The static type does not prove bound `B`. | Keep the concrete type, or use an API with an appropriate contract. |
| Arbitrarily changing the order of interface bounds in a library | The first bound determines erasure, which can affect binary compatibility. | Keep bound order stable in public APIs. |
| Using raw types/unchecked casts to bypass errors | Loses type safety and can cause runtime errors. | Design proper bounds and choose valid types. |

## 15. Practical Design Scenario: Auditing Named Entities

Suppose an application has many objects such as `Customer`, `Invoice`, or `Job`. Not every kind needs the same parent class, yet common operations like "display name" and "write audit log" are capabilities that can be defined with interfaces.

There are three reasonable designs:

1. **Bound by two interfaces**: `<T extends Named & Auditable> void run(T value)`. Suitable when the algorithm needs both capabilities and does not care about a specific base class.
2. **Bound by class + interfaces**: `<T extends Identified & Named & Auditable> void run(T value)`. Suitable when the algorithm actually needs access to the `Identified` base class API alongside the interfaces.
3. **Define a combined business interface**: `interface AuditedNamed extends Named, Auditable {}` and then use `<T extends AuditedNamed>`. Suitable if "named and auditable object" is a stable domain concept and the relevant classes can publicly implement that shared interface.

Do not use multiple bounds just to show off writing complex syntax. If the algorithm only needs `Named.name()`, use a single bound `<T extends Named>` or accept `Named` directly. Every added bound **narrows the set of valid types** that callers can pass to the API.

When operating on multiple elements:

```java
static <T extends Named & Auditable> void auditAll(
        java.util.List<T> items) {
    for (T item : items) {
        System.out.println(item.name());
        item.audit();
    }
}
```

This is an **illustrative method inside a class**. With a single bound on `T`, the compiler checks every element in the list without needing to cast individually to `Named` or `Auditable`.

## 16. Checklist for Applying Multiple Bounds

When faced with a task to "design `<T extends A & B>`", follow these steps in order:

1. **Identify the capabilities genuinely needed**: which APIs will the method call from `A` and from `B`? If `B` is unused, that bound may not be needed.
2. **Determine whether A and B are classes or interfaces**: if there is a class bound, put it first; do not try to put two classes in the list.
3. **Check contract compatibility**: can the bounds legally be implemented together by a single type? Are there conflicting methods or generic superinterfaces?
4. **Place `<T extends ...>` in the right position**: after the class name when declaring a generic class, or before the return type when declaring a generic method.
5. **Preserve type relationships at call sites**: use concrete arguments satisfying all bounds; avoid losing the type into an overly broad interface before calling.
6. **Distinguish bounds from wildcards**: `<T extends A & B>` is valid; `? extends A & B` is not valid wildcard syntax.
7. **Mind erasure in public APIs**: the first bound determines the erased type; do not arbitrarily flip the order in a released API.
8. **Compile with Java 17+**, check for `rawtypes`/`unchecked` warnings when integrating legacy code, and test both valid cases and compile-time errors as a learning exercise.

## 17. Self-Check

**Question 1.** In `<T extends Named & Auditable>`, can a type that only implements `Named` be used as the type argument `T`? Why?

**Question 2.** Which declaration is valid if `Base` is a class and `Named`, `Auditable` are interfaces: `<T extends Named & Base & Auditable>` or `<T extends Base & Named & Auditable>`?

**Question 3.** Why does `<T extends Number & Comparable<T>>` support numeric comparison algorithms, whereas `<T extends Number>` is not enough to call `compareTo(T)`?

**Question 4.** Does Java accept `List<? extends Named & Auditable>`? To process a list of objects having both capabilities, how can a generic method be declared?

**Question 5.** In the method `static <T extends Named & Auditable> void f(T value)`, does `T` belong to the class or to the method?

**Question 6.** Why can reversing `Named & Auditable` to `Auditable & Named` matter at the class-file level even though both require the same two interfaces?

**Answer hints:** (1) No, the type argument must satisfy all bounds. (2) The second form, because the class bound must come first. (3) `Number` itself does not declare `compareTo`; the `Comparable<T>` bound provides the required comparison contract. (4) No; use, for example, `static <T extends Named & Auditable> void f(List<T> items)`. (5) `T` belongs solely to the generic method. (6) The erasure of `T` is taken from the first bound, so the method descriptor can change.

**Key takeaway:** Multiple bounds in Java use the syntax **`<T extends A & B>`**, indicating that **T must satisfy both A and B simultaneously**. If there is a class bound, it must **come first** and there can be only one class bound; subsequent bounds are interfaces. The compiler allows calling APIs of all bounds on `T`, while rejecting non-conforming types at compile time. Remember that the order of the first bound matters for type erasure and distinguish type parameter bounds from wildcards.