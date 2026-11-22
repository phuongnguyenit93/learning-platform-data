# Generic Class Inheritance with Fixed Type Arguments in Java

## 1. The Problem and Core Idea

A generic class declares a type parameter, such as `Storage<T>`, so that the same storage structure can serve multiple data types. When creating a **subclass**, Java allows choosing a concrete type for the superclass's parameter right in the `extends` clause:

```java
// Syntax example; the declarations reside in an appropriate Java file.
class Storage<T> {
    private final T value;

    Storage(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class TextStorage extends Storage<String> {
    TextStorage(String text) {
        super(text);
    }
}
```

`TextStorage extends Storage<String>` states that:

- `Storage<T>` is the **generic superclass**.
- `TextStorage` is a **non-generic subclass**, because the class name does not declare `<...>`.
- `String` is the **fixed type argument** bound to `T` of the superclass.
- From `TextStorage`'s perspective, the inherited method `get()` has return type **`String`**; the parent constructor `Storage(T)` receives corresponding data of type **`String`**.
- Every instantiation `new TextStorage(...)` follows the same `Storage<String>` contract. Callers cannot turn it into `Storage<Integer>` by adding type arguments.

The purpose of this inheritance style is to turn a general abstraction into **a subtype with a specific role**: for example storing strings, integer data, a list of names, or records of a particular domain type. The compiler preserves the type relationship between parent and child, so users do not have to manually cast from `Object`.

This article uses Java **17+**, covering syntax and type checking mechanisms through overriding, constructor chaining, polymorphism, wildcards, and common errors. Section 12 includes a standalone Java file that has been compiled and executed for verification.

## 2. Declaring a Generic Superclass and a Fixed-Type Subclass

General syntax:

```java
class Parent<T> {
    // T can appear in instance fields, constructors, methods...
}

class Child extends Parent<ConcreteType> {
    // No longer declares type parameter T for Child itself.
}
```

`ConcreteType` must be a valid reference type and satisfy the **bounds** of the superclass's type parameter. For example, `String`, `Integer`, `User`, and `List<String>` can all be type arguments if they do not violate bounds; `int` and `boolean` cannot serve directly as generic type arguments.

An example of a superclass with a getter and setter:

```java
class Cell<T> {
    private T data;

    Cell(T data) {
        this.data = data;
    }

    T read() {
        return data;
    }

    void replace(T next) {
        data = next;
    }
}

final class StringCell extends Cell<String> {
    StringCell(String text) {
        super(text);
    }
}

// Inside a Java method:
StringCell cell = new StringCell("Java");
String value = cell.read();
cell.replace("Generics");
// cell.replace(100); // Compile error: StringCell extends Cell<String>.
```

`StringCell` does not need to declare `read()` or `replace(...)` itself: once `T` is fixed to `String` in the `extends` clause, the compiler checks the inherited methods with the corresponding types.

**Remember:** In a subclass declaration, `extends Cell<String>` means fixing the type argument of the **superclass**. This is not syntax for declaring a new type parameter. Compare:

```java
class A extends Cell<String> { // A is not generic.
    A() { super("fixed"); }
}

class B<U> extends Cell<U> {    // B remains generic and passes U to the parent.
    B(U initial) { super(initial); }
}
```

`A` has a single contract `Cell<String>`. `B<Integer>` uses `Cell<Integer>`, while `B<String>` uses `Cell<String>`, depending on the type argument at the use site of `B<U>`.

## 3. Type Parameter Mapping Table Across Inheritance

When encountering `class Child extends Parent<String>`, you should inspect all positions where `T` is used in the superclass API, not just a single getter:

| Member declared in `Parent<T>` | Perspective from `Child extends Parent<String>` |
| --- | --- |
| `private T value;` | Internal data in the parent is constrained to `String` |
| `Parent(T initial)` | Parent constructor requires data compatible with `String` |
| `T get()` | When called on `Child`, the result is `String` |
| `void set(T item)` | When called on `Child`, the argument must be compatible with `String` |
| `List<T> all()` | When called on `Child`, the result has type `List<String>` |
| `Optional<T> find()` | When called on `Child`, the result has type `Optional<String>` |
| `<R> R map(Function<? super T,? extends R> f)` | The function's input parameter fits `String`, while `R` is still inferred separately by the method |
| `static <U> U echo(U value)` | `U` belongs to the static method; it is not fixed to `String` |

Not every API of the superclass has all type parameters replaced with `String`. Only **references to the class's `T`** are mapped according to `extends Parent<String>`. A generic method's own type parameter, such as `<R>`, remains independent.

In particular, the subclass **cannot directly access the parent's `private T value` field**, even after fixing `T` to `String`. Generics do not alter `private`/`protected` access rules. Use getters, protected methods, or the parent constructor instead of breaking encapsulation.

## 4. Subclass Constructors and `super(...)` Calls

Constructors are **not inherited**. Even if the subclass fixes the type argument, it still needs its own constructor to initialize the parent part. If the superclass has no accessible no-argument constructor, the subclass must call an appropriate constructor using `super(...)`:

```java
class Parent<T> {
    private final T data;

    Parent(T data) {
        this.data = java.util.Objects.requireNonNull(data);
    }

    T get() {
        return data;
    }
}

final class EmailValue extends Parent<String> {
    EmailValue(String email) {
        super(email); // T of Parent<T> is fixed to String.
    }
}
```

In Java 17, the `super(email)` call must be the first statement of the constructor (except for additional syntax permitted by newer Java versions). The call to `Parent(T)` is effectively type-checked by the compiler with `T = String` when passing through `Parent<String>`.

A common mistake:

```java
final class Wrong extends Parent<String> {
    // Wrong() {} // Error if Parent<T> has no accessible no-arg constructor.
    Wrong(String text) {
        super(text);
    }
}
```

Do not write `super<String>(text)` to specify the superclass's type argument. The `String` type has already been chosen in the **extends clause**. `super(text)` is a constructor call, not a place to repeat `Parent<String>`.

### Reusing Superclass Invariant Checks

A superclass can reject null or validate data directly inside its constructor:

```java
class NonNullValue<T> {
    private final T value;

    NonNullValue(T value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    T get() { return value; }
}

final class NonNullTitle extends NonNullValue<String> {
    NonNullTitle(String title) {
        super(title);
    }
}
```

`NonNullTitle` inherits the parent's rule disallowing `null`. However, generics **do not forbid null by themselves**: if the parent constructor does not check, passing `null` can be valid with respect to types. Distinguish **type safety** from **data validation**.

## 5. Overriding Methods After Fixing the Type Argument

If the parent has a method `T get()`, the subclass `extends Parent<String>` can override it with a method returning `String`:

```java
import java.util.Locale;

class Base<T> {
    private final T value;

    Base(T value) {
        this.value = value;
    }

    public T get() {
        return value;
    }
}

final class UppercaseText extends Base<String> {
    UppercaseText(String value) {
        super(value);
    }

    @Override
    public String get() {
        return super.get().toUpperCase(Locale.ROOT);
    }
}
```

In `UppercaseText`, `T` of `Base<T>` is fixed to `String`, so `@Override public String get()` matches the contract. `@Override` helps the compiler catch name/signature mistakes when the author thinks they are overriding while actually overloading.

For example, if the superclass has a setter `void set(T value)`, then the fixed-type subclass must override it with the corresponding `void set(String value)` (with the same or broader access modifier, and following checked exception rules). An overload taking `Object` is usually a different method, or causes an erasure clash depending on the signature: do not use `Object` to bypass generic constraints.

### Bridge Methods and Type Erasure

In the `Base<T>.get()` example, type erasure makes the underlying JVM signature of the parent getter correspond to a return type of `Object` (when `T` is unbounded). The overridden getter in `UppercaseText` has return type `String`. The compiler may generate an additional **bridge method** to preserve polymorphism at the bytecode level. Bridges are an implementation detail handled by the compiler; learners **should not write** bridge methods manually.

The result at the source-code level remains guaranteed:

```java
Base<String> base = new UppercaseText("java");
String text = base.get(); // "JAVA" due to dynamic dispatch.
```

The type of the variable `base` is `Base<String>`; the method selected at runtime is the overridden implementation in `UppercaseText`. Generic type checking and dynamic dispatch work together.

## 6. Polymorphism: A Subclass Can Be Referenced by Its Fixed Superclass Type

The valid inheritance relationship is:

```java
class Parent<T> {
    Parent(T value) {}
}

class TextChild extends Parent<String> {
    TextChild() {
        super("text");
    }
}

// Parent<String> one = new TextChild(); // Valid.
// Parent<Integer> two = new TextChild(); // Compile error.
```

`TextChild` is a subtype of `Parent<String>`, **not** a subtype of `Parent<Integer>` or `Parent<Object>`.

A very important principle: even though `String extends Object`, the type `Parent<String>` **does not inherit from** `Parent<Object>`. Java generics are **invariant**. For example, the compiler must reject:

```java
Parent<String> s = new TextChild();
// Parent<Object> o = s; // Invalid: incompatible type arguments.
```

If this assignment were allowed, APIs accepting `Parent<Object>` could put a type other than `String` into a structure committed to storing strings. Java enforces the constraint by rejecting this type conversion.

### Wildcard References When the Type Argument Is Not Yet Needed

If you only want to iterate over objects belonging to multiple generic parent types, use a wildcard:

```java
// Example inside a method, assuming the parent has get().
Parent<?> a = new TextChild();
Object value = a.get();
```

`Parent<?>` accepts a `Parent<String>`, `Parent<Integer>`, etc. However, `get()` can only be treated as returning `Object` at compile-time (unless a bound provides a specific type), and write operations into the unknown parameter will be restricted.

When designing APIs, **keep `Parent<String>` if you need to know the exact data type**; use `Parent<?>` if you only need to handle the object as an arbitrary instance of the abstraction.

## 7. How Does a Non-Generic Subclass Differ from a Generic Subclass?

Three common strategies:

```java
class Holder<T> {
    private final T value;

    Holder(T value) { this.value = value; }

    T get() { return value; }
}

// (1) Fix T to String.
class StringHolder extends Holder<String> {
    StringHolder(String value) { super(value); }
}

// (2) Keep type parameter U for the subclass, forwarding U to the parent.
class ForwardHolder<U> extends Holder<U> {
    ForwardHolder(U value) { super(value); }
}

// (3) Generic subclass, but parent is fixed to String.
class TaggedStringHolder<K> extends Holder<String> {
    private final K tag;

    TaggedStringHolder(K tag, String value) {
        super(value);
        this.tag = tag;
    }

    K tag() { return tag; }
}
```

Comparison table:

| Subclass type | Superclass type | Inherited getter type | Meaning |
| --- | --- | --- | --- |
| `StringHolder` | `Holder<String>` | `String` | The subclass completely fixes the value type. |
| `ForwardHolder<Integer>` | `Holder<Integer>` | `Integer` | The subclass remains generic in `U`. |
| `TaggedStringHolder<Long>` | `Holder<String>` | `String` | Parent data remains a string, while `K` is only for the subclass's tag. |

A subclass **can be generic** while still using a fixed type argument for the parent. Do not assume "the subclass has `<K>`, so the parent's type argument must be `K`": the two decisions are independent.

### Fixing Some Parameters and Keeping Others

With a superclass that has two type parameters:

```java
class Pair<A, B> {
    private final A first;
    private final B second;

    Pair(A first, B second) {
        this.first = first;
        this.second = second;
    }

    A first() { return first; }
    B second() { return second; }
}

// Fix A, keep B declared by the subclass.
class NamedPair<V> extends Pair<String, V> {
    NamedPair(String name, V value) {
        super(name, value);
    }
}

// NamedPair<Integer> score = new NamedPair<>("Lan", 9);
// score.first() is String; score.second() is Integer.
```

`NamedPair<V> extends Pair<String,V>` is an example of **partial specialization** of a generic superclass. `String` is fixed for parameter `A`; the subclass's `V` is forwarded into the parent's parameter `B`.

## 8. Multi-Level Inheritance

Fixing a type argument can happen at an intermediate level and remain in effect at subsequent levels:

```java
class Base<T> {
    private final T value;
    Base(T value) { this.value = value; }
    T get() { return value; }
}

class TextBase extends Base<String> {
    TextBase(String value) { super(value); }
}

final class LocalizedText extends TextBase {
    LocalizedText(String value) { super(value); }
}

// String s = new LocalizedText("Xin chào").get();
```

`LocalizedText` does not write `extends Base<String>` directly, yet through `TextBase` it still inherits the getter typed as `String`. A type argument fixed along an inheritance branch continues to constrain subclasses beneath it.

Subclasses can also implement additional interfaces or new methods, but cannot "change" the type already fixed in the parent to a different type simply via a new declaration:

```java
// There is no point and no valid syntax to write:
// class Broken extends TextBase<Integer> {}
// TextBase is not a generic class in the first place.
```

If you need a version holding `Integer`, create another subclass directly from `Base<Integer>`, or design a subclass that stays generic like `ForwardHolder<U>`.

## 9. Fixing Types When Inheriting from a Bounded Class

A superclass can restrict its type argument:

```java
class NumericHolder<T extends Number> {
    private final T number;

    NumericHolder(T number) {
        this.number = number;
    }

    T get() { return number; }

    double asDouble() {
        return number.doubleValue();
    }
}

class IntegerHolder extends NumericHolder<Integer> {
    IntegerHolder(Integer value) {
        super(value);
    }
}

// IntegerHolder ok = new IntegerHolder(7);
// class Bad extends NumericHolder<String> { } // Violates Number bound.
```

`Integer` extends `Number`, so `NumericHolder<Integer>` is valid. `String` does not extend `Number`, so `NumericHolder<String>` does not compile.

An interface bound works similarly:

```java
class SortedValue<T extends Comparable<T>> {
    private final T value;

    SortedValue(T value) {
        this.value = value;
    }

    boolean before(T other) {
        return value.compareTo(other) < 0;
    }
}

class TextOrder extends SortedValue<String> {
    TextOrder(String value) {
        super(value);
    }
}
```

`String` implements `Comparable<String>`, thus satisfying the constraint of `SortedValue<T>`. Bounds require the **subclass's fixed type** to fulfill the APIs that the superclass uses.

When choosing a type argument, check the bounds from the parent's signature first; do not use raw types or unchecked casts to bypass compiler errors.

## 10. The Fixed Type Argument Can Be Another Generic Type

`ConcreteType` in `extends Parent<ConcreteType>` does not have to be a simple type like `String`; it can be a fully parameterized type:

```java
import java.util.*;

class Value<T> {
    private final T value;
    Value(T value) { this.value = value; }
    T get() { return value; }
}

final class NameListValue extends Value<List<String>> {
    NameListValue(Collection<String> names) {
        super(List.copyOf(names));
    }
}

// NameListValue people = new NameListValue(List.of("Lan", "Mai"));
// List<String> names = people.get();
```

With `NameListValue`, the parent's type argument `T` is fixed to **`List<String>`**, not just `String`. The parent's getter has return type `List<String>`.

Here `List.copyOf` intentionally creates an unmodifiable list containing no `null` elements. This property comes from the factory, **not automatically guaranteed by generic inheritance**. If a class needs to control mutable data shared via aliases, design defensive copies or a clear data ownership policy.

You can extend this pattern to `Map<String, Integer>`, `Optional<User>`, or a domain record. However, subclassing merely to create a shorter alias can bloat the class hierarchy; consider whether the subclass adds real semantics, validation, or behavior.

## 11. Combining a Fixed-Type Subclass with a Generic Interface

A subclass can fix its superclass while simultaneously implementing a generic interface. Both relationships must be checked separately:

```java
interface Formatter<T> {
    String format(T value);
}

class Box<T> {
    private final T value;
    Box(T value) { this.value = value; }
    T get() { return value; }
}

final class PrintableText extends Box<String> implements Formatter<String> {
    PrintableText(String value) {
        super(value);
    }

    @Override
    public String format(String value) {
        return "[" + value + "]";
    }
}
```

`Box<String>` ensures the inherited data is `String`. `Formatter<String>` ensures the `format(String)` signature conforms to the interface contract. These are two ways of using fixed type arguments that can be combined on the same subclass.

Conversely, declaring `implements Formatter<Integer>` will require an implementation of `format(Integer)`, without automatically changing the parent type `Box<String>`. Java allows different type arguments when two abstractions express independent roles, provided their signatures and inheritance relationships do not conflict.

**Limitation:** a class cannot inherit the same generic interface with two different type arguments through two conflicting inheritance paths (for example, trying to achieve both `Comparable<String>` and `Comparable<Integer>` simultaneously). Overlap after type erasure and inheritance rules prevent such a design.

## 12. Complete and Verified Java 17+ Program

Create the file **`FixedTypeInheritanceDemo.java`** with the exact content below. The file brings together examples of a generic superclass, a subclass with a fixed type argument, a subclass that stays generic, overriding, and a fixed-type interface. The code has no intentional errors or dependencies outside the JDK.

```java
import java.util.List;
import java.util.Locale;
import java.util.Objects;

public class FixedTypeInheritanceDemo {
    static abstract class Storage<T> {
        private final T value;

        protected Storage(T value) {
            this.value = Objects.requireNonNull(value);
        }

        public T get() {
            return value;
        }

        public abstract String describe();
    }

    static final class TextStorage extends Storage<String> {
        TextStorage(String text) {
            super(text);
        }

        @Override
        public String get() {
            return super.get().toUpperCase(Locale.ROOT);
        }

        @Override
        public String describe() {
            return "Text(" + get() + ")";
        }
    }

    static final class NumberStorage extends Storage<Integer> {
        NumberStorage(Integer number) {
            super(number);
        }

        @Override
        public String describe() {
            return "Integer(" + get() + ")";
        }
    }

    static final class GenericStorage<U> extends Storage<U> {
        GenericStorage(U value) {
            super(value);
        }

        @Override
        public String describe() {
            return "Generic(" + get() + ")";
        }
    }

    interface Formatter<T> {
        String format(T value);
    }

    static final class TextFormatter implements Formatter<String> {
        @Override
        public String format(String value) {
            return value + "!";
        }
    }

    static void display(Storage<?> storage) {
        System.out.println(storage.describe());
    }

    public static void main(String[] args) {
        Storage<String> text = new TextStorage("java");
        Storage<Integer> count = new NumberStorage(7);
        Storage<Double> pi = new GenericStorage<>(3.14);

        System.out.println("get: " + text.get());
        System.out.println("count: " + count.get());
        System.out.println("pi: " + pi.get());

        for (Storage<?> item : List.of(text, count, pi)) {
            display(item);
        }

        Formatter<String> formatter = new TextFormatter();
        System.out.println("format: " + formatter.format("hello"));
        System.out.println("same class: " +
                (new GenericStorage<>("x").getClass()
                        == new GenericStorage<>(10).getClass()));
    }
}
```

Save the file in UTF-8. Compile with JDK 17 or higher:

```bash
javac --release 17 -Xlint:all FixedTypeInheritanceDemo.java
java FixedTypeInheritanceDemo
```

Exact **stdout output** (compiled with `--release 17` mode and run successfully):

```text
get: JAVA
count: 7
pi: 3.14
Text(JAVA)
Integer(7)
Generic(3.14)
format: hello!
same class: true
```

**Execution flow explanation:**

1. `TextStorage extends Storage<String>` fixes the type argument, so the variable `Storage<String> text` can hold a `TextStorage` instance. The overridden `get()` returns the uppercase string `JAVA`.
2. `NumberStorage extends Storage<Integer>` is another fixed-type subclass of the same superclass; `count.get()` is understood by the compiler as `Integer`.
3. `GenericStorage<U> extends Storage<U>` **does not fix the type argument in the class declaration**, because `U` continues to be chosen at each use of `GenericStorage<U>`. `new GenericStorage<>(3.14)` creates a `GenericStorage<Double>` compatible with `Storage<Double>`.
4. `List.of(text, count, pi)` and the loop use `Storage<?>` to iterate over objects with different type arguments. The `display` method only calls `describe()`, without needing to know each object's data type.
5. `TextFormatter implements Formatter<String>` illustrates a generic interface fixed to `String`; the compiler checks `format(String)`.
6. The two parameterizations `GenericStorage<String>` and `GenericStorage<Integer>` share the same runtime `Class` because of type erasure; therefore the last line prints `true`. This does not eliminate compile-time generic checking.

In the program, the nested classes are declared `static` to keep the file standalone and easy to run. Type arguments of `Storage<T>` are still checked on instance fields/methods; the `static` keyword here only describes the **nesting of the classes** inside `FixedTypeInheritanceDemo`.

## 13. Common Misconceptions and Compiler Errors

| Mistake / scenario | Problem | How to handle |
| --- | --- | --- |
| `class Child extends Parent` | Uses a **raw superclass**, losing type argument information | Declare `extends Parent<String>` or an appropriate type argument. |
| `class Child extends Parent<>` | Diamond `<>` cannot be used in an `extends` clause | Write a concrete type argument: `extends Parent<String>`. |
| `class Child<T> extends Parent<T>` while expecting the parent to always hold `String` | `T` is still chosen by users of `Child` | If you want it fixed: `class Child extends Parent<String>`. |
| `class Child extends Parent<String>` then passing `Integer` to `super(...)` | Parent constructor requires `String` | Intentionally convert the input before calling `super(...)`. |
| Superclass has no no-arg constructor, subclass omits `super(...)` | No matching parent constructor to invoke implicitly | Declare a subclass constructor and call `super(value)`. |
| Overriding `T get()` with an incompatible type after fixing `T` | Overriding signature does not match return type | For `Parent<String>`, return `String` or a valid covariant return type. |
| Assigning `Parent<String>` to `Parent<Object>` | Java generics are invariant | Keep the exact type argument or use `Parent<?>` if only general reading is needed. |
| Writing `extends Parent<int>` | Primitives cannot be generic type arguments | Use `Integer`. |
| `extends NumericParent<String>` with `T extends Number` | Does not satisfy the superclass bound | Choose `Integer`/`Double` or a numeric type satisfying the bound. |
| Inside subclass, trying to access parent's `private T value` | `private` does not change because of generic inheritance | Use an accessor or a clearly designed API. |
| Inheriting the same generic interface via two conflicting type arguments | Java disallows inconsistent inheritance types | Separate abstractions or unify the contract. |
| `instanceof Parent<String>` | Type argument `String` is not checked by ordinary `instanceof` | Use `instanceof Parent<?>` and then validate contents if needed. |
| Thinking `extends Parent<String>` creates a separate runtime class for `Parent<String>` | Generic type arguments are mostly erased | Distinguish compile-time source types from runtime `Class`. |
| Using raw types or unchecked casts to bypass compiler errors | Risks heap pollution and `ClassCastException` | Redesign type relationships, using wildcards/bounds in their proper roles. |

### Using `@Override` to Catch Errors Early

Always consider adding `@Override` when a fixed-type subclass overrides a method from its parent:

```java
class Parent<T> {
    public T get() { return null; }
}

class Child extends Parent<String> {
    @Override
    public String get() {
        return "ok";
    }
}
```

If you accidentally write `get(String arg)`, the `@Override` annotation will help reveal that it is not an override of `get()`. This is good practice when generic substitution makes inherited signatures easy to misread.

## 14. When Should You Fix the Type, and When Should You Keep the Subclass Generic?

**Fix the type in `extends` when** the subclass carries a specialized meaning and every valid instance of it needs the same kind of data. For example, `TextStorage` needs to operate on strings, and `IntegerHolder` provides logic for integer values. The subclass can add validation, formatting, domain methods, or optimizations while still reusing the general abstraction.

**Stay generic** with `class ForwardStorage<U> extends Storage<U>` when the new behavior still applies to multiple data types. Do not create fixed-type subclasses if their only job is calling `super(...)` without adding modeling or API value.

If you only want to give a name to a common generic combination such as `List<String>`, consider keeping the explicit type in the API, using a meaningful record/domain object, or using composition. Extending a collection implementation such as `HashMap<String,Integer>` solely to create a shorter name can make classes harder to maintain, especially when the object is not genuinely a subtype with its own behavior.

An appropriate domain design example:

```java
record UserId(String value) {
    UserId {
        java.util.Objects.requireNonNull(value);
    }
}

class Identifier<T> {
    private final T value;

    Identifier(T value) {
        this.value = java.util.Objects.requireNonNull(value);
    }

    T get() { return value; }
}

final class UserIdentifier extends Identifier<UserId> {
    UserIdentifier(UserId id) {
        super(id);
    }
}
```

`UserIdentifier` fixes the parent's type to a concrete domain record `UserId`. This design makes sense if the system's API wants to distinguish user IDs from other IDs and apply dedicated behavior/validation.

## 15. Exercises and Self-Assessment Criteria

**Exercise 1 — Getter with a fixed type.** Write `class Box<T>` holding `T value` and getter `T get()`. Create `class LongBox extends Box<Long>`; design a constructor calling `super(Long)`. Try assigning `LongBox` to `Box<Long>`, then try assigning it to `Box<Number>` and explain why the second assignment fails.

**Exercise 2 — Overriding.** Write `class MessageBox extends Box<String>`, overriding the getter to prepend `"Message: "`. Use `Box<String> ref = new MessageBox("Hi")` and call `ref.get()`; explain how type checking and dynamic dispatch work together.

**Exercise 3 — Keeping a type parameter.** Write `class History<T> extends Box<List<T>>`. Why is the subclass **still generic**, even though the parent's type is `Box<List<T>>`? Verify that `History<Integer>` has a getter returning `List<Integer>`. If `T` is replaced with `String`, describe how the subclass is fixed to `Box<List<String>>`.

**Exercise 4 — Bounds.** Write `class PositiveInteger extends NumericHolder<Integer>` accepting only positive numbers. Put the validation in the constructor or a clearly named factory. Verify that callers cannot create an object containing a `String` and explain the two independent layers of protection: **generic bound** and **positive-value business rule**.

**Exercise 5 — Inheritance chain.** Create `Base<T> → FixedBase extends Base<String> → FinalText extends FixedBase`. What type does the getter in `FinalText` return? Is it valid to declare `FinalText extends FixedBase<Integer>`? Why?

**Exercise 6 — Generic interface.** Create `interface Serializer<T>` with `String serialize(T item)`. Write `UserSerializer implements Serializer<User>` with record `User(String name)`; state the required parameter type of the overridden method. If it also extends `Box<String>`, what roles do the two generic constraints play?

**Exercise 7 — Reflection and runtime.** Predict the result of checking `new GenericStorage<>("a").getClass() == new GenericStorage<>(1).getClass()`. Why does the result not mean Java allows assigning `GenericStorage<String>` to `GenericStorage<Integer>`?

**Exercise 8 — API design.** A team only needs a function `display(Storage<?> storage)` to print a description. When should it accept the wildcard `Storage<?>`, and when should it keep `Storage<String>` to call string-specific methods? Relate the API's purpose to the safety of the operations.

You have mastered the lesson when you can answer: **whether the subclass declares a new type parameter or not; which parameter of the superclass is fixed; what the types of the constructor/getter/setter are after fixing; and why `Parent<String>` does not mean `Parent<Object>`**. Understanding the exact type mapping across `extends` helps build reusable inheritance hierarchies while still guaranteeing compile-time type safety.
