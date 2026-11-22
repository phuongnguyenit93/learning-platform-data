# Bounds Referencing Another Type Parameter in Java Generics

## 1. Problem and Objectives

In Java, a generic type parameter can be bounded (*bounded type parameter*) by a concrete class or interface, such as `<T extends Number>`. However, many algorithms need to express **a relationship between two or more type parameters**, rather than bounding each parameter in isolation:

```java
// Illustrative snippet placed inside a Java class.
static <Super, Sub extends Super> Super choose(
        boolean useSub, Super first, Sub second) {
    return useSub ? second : first;
}
```

Here `Sub extends Super` states that **type argument `Sub` must be a subtype of type argument `Super`**. Both `Super` and `Sub` are type parameters of the same method. With `Super = Number` and `Sub = Integer`, the compiler proves that an `Integer` can be used where a `Number` is required. Attempting to pick `Super = String` and `Sub = Integer` violates the bound.

Another example:

```java
static <T extends Comparable<? super T>> T maximum(
        java.util.Collection<? extends T> source) {
    // Full implementation in a later section.
    throw new UnsupportedOperationException();
}
```

`T` in `Comparable<? super T>` is used **right inside the bound of `T` itself**. This is an example of a self-referential bound (*recursive/F-bound*), combined with a wildcard so a type can be compared via an interface supported by itself or a parent type.

After this lesson, you should be able to:

- Read and write `<A, B extends A>`, `<T extends Comparable<T>>`, and `<T extends Comparable<? super T>>`.
- Accurately identify **which parameter is the bound source**, which parameter is bounded, and which subtype relationship must be proven.
- Understand references to another type parameter in **generic classes, generic methods, generic constructors, and self-referential bounds**.
- Distinguish `extends` in a **type parameter declaration** from wildcards `? extends ...`/`? super ...`.
- Know when type inference has enough information and when to use a type witness or an explicit target type declaration.
- Avoid confusing subtype relationships with covariance of `List<T>`, and avoid raw types/unchecked casts to bypass bound errors.

This article targets Java **17+**, including illustrative snippets and a complete `DependentBoundsDemo.java` file that has been compiled and tested.

## 2. Foundational Syntax: Bound of a Single Type Parameter

A simple bound is usually written as:

```java
class NumericBox<T extends Number> {
    private final T value;

    NumericBox(T value) {
        this.value = value;
    }

    double asDouble() {
        return value.doubleValue();
    }
}
```

`T extends Number` means the actual type argument for `T` must be `Number` or a subtype of `Number`. Thus `NumericBox<Integer>` and `NumericBox<Double>` are valid, whereas `NumericBox<String>` is invalid.

Whether `Number` is a class or the bound is an interface such as `Comparable<T>`, Java always uses **the `extends` keyword** in the type parameter declaration list. Do not write `<T implements Interface>`.

A type parameter can have **multiple bounds**:

```java
// Declaration snippet inside a Java class or method.
static <T extends Number & Comparable<T>> boolean greater(T a, T b) {
    return a.compareTo(b) > 0;
}
```

A class bound (if present) must come first, with interfaces following `&`. For example, `Integer` is both a `Number` and implements `Comparable<Integer>`, so it satisfies this bound. You cannot combine multiple class bounds: Java does not support multiple class inheritance.

When a bound references **another type parameter** instead of a concrete class/interface name, the principle remains checking the subtype relationship at compile time.

## 3. Two Mutually Dependent Type Parameters: `<Super, Sub extends Super>`

Generic class example:

```java
class Pair<Super, Sub extends Super> {
    private final Super first;
    private final Sub second;

    Pair(Super first, Sub second) {
        this.first = first;
        this.second = second;
    }

    Super first() {
        return first;
    }

    Sub second() {
        return second;
    }
}
```

`Pair<Number, Integer>` is valid because `Integer` is a subtype of `Number`. `Pair<CharSequence, String>` is valid because `String` implements `CharSequence`. However, `Pair<String, Integer>` is invalid because `Integer` is not a subtype of `String`.

```java
// Statements that can be placed inside a Java method.
Pair<Number, Integer> numbers = new Pair<>(3.5, 7);
Number a = numbers.first();
Integer b = numbers.second();

Pair<CharSequence, String> names = new Pair<>("base", "child");
// Pair<String, Integer> wrong = new Pair<>("text", 1); // Bound error.
```

**Analysis of each position:**

| Component | Meaning |
| --- | --- |
| `Super` | Independent type parameter, with no explicit bound beyond default `Object`. |
| `Sub extends Super` | `Sub` must be a subtype of the `Super` chosen in the same parameterization. |
| `Super first` | Field accepting a value conforming to `Super`'s contract. |
| `Sub second` | Field holding a more specific type conforming to `Sub`'s contract. |
| `Super first()` | Result received by the caller is typed as `Super`. |
| `Sub second()` | Result received by the caller is typed as `Sub`; no cast from `Object` needed. |

The `Sub extends Super` relationship only constrains **types**; it does not assert that the two objects in fields `first` and `second` have the same value. Nor does it require `Sub` to be a **direct subclass**: a multi-level subtype, interface implementation, or the exact same type chosen for both parameters is also valid if the bounds are satisfied.

### Setting a type parameter equal to the other type is still valid

```java
Pair<String, String> same = new Pair<>("A", "B");
```

`String` is a subtype of itself under the reflexive subtype relation; `extends` in a bound does not require a subclass *strictly different* from the parent class.

## 4. Dependent Bounds in Generic Methods

You do not need to create a new generic class to use `Sub extends Super`. A method typically declared inside a utility class can own both type parameters itself:

```java
final class Selection {
    private Selection() {}

    static <Super, Sub extends Super> Super choose(
            boolean chooseSub, Super normal, Sub specialized) {
        return chooseSub ? specialized : normal;
    }
}
```

The method only needs to know that `specialized` can be used safely as a `Super`. For example:

```java
Number result =
        Selection.<Number, Integer>choose(true, 1.5, 9); // 9
```

The two type arguments `Number` and `Integer` appear between `<...>` in the method call: `Selection.<Number, Integer>choose(...)`. This is called an **explicit type witness**, useful when you want to see the relationship clearly. In many calls, the compiler can infer the types and the programmer simply writes `Selection.choose(...)`.

Important note: Java often has multiple valid choices for a common type. If type arguments are not specified, the compiler may infer a broader parent class/interface than intended based on the arguments and context. **Do not assume the compiler will always pick `Number`** merely because you are working with numbers. When signatures are interdependent or inference errors are confusing, provide an explicit target type or use a type witness as above.

### What does the bound enable inside the method body?

With `<Super, Sub extends Super>`, the compiler allows:

```java
static <Super, Sub extends Super> Super promote(Sub value) {
    Super upcast = value; // Valid: Sub extends Super.
    return upcast;
}
```

Conversely, the direction from `Super` to `Sub` is not guaranteed:

```java
// Invalid:
// static <Super, Sub extends Super> Sub downcast(Super value) {
//     return value; // Super is not necessarily Sub.
// }
```

This is the value of bounds: the compiler permits the proven conversion direction and rejects the unguaranteed direction, without waiting for a runtime `ClassCastException`.

## 5. Referencing a Type Parameter Declared Later

Java allows a type parameter to reference another type parameter located **later** in the same declaration list:

```java
class Forward<Sub extends Super, Super> {
    private final Sub value;

    Forward(Sub value) {
        this.value = value;
    }

    Super readAsSuper() {
        return value;
    }
}

// Forward<Integer, Number> f = new Forward<>(7);
// Number n = f.readAsSuper();
```

`Super` still belongs to the same type parameter list of `Forward`, so the bound `Sub extends Super` is valid. Similarly, a generic method can be written as:

```java
static <Sub extends Super, Super> Super up(Sub value) {
    return value;
}
```

This syntax is **supported by Java**, though writing `<Super, Sub extends Super>` is usually **easier to read** because the base type is declared first, followed by the dependent type. The natural layout helps readers quickly recognize the direction of the constraint.

Allowing forward references does not mean Java permits every circular bound. Some bound combinations are illegal due to cycle rules or failing generic conditions, and certain valid F-bound forms are explained in Section 9. Let the compiler check each declaration instead of assuming every reference cycle is permitted.

## 6. Bounding via an Interface: One Type Parameter Uses an API Parameterized by Another

A bound can use a generic interface carrying another type parameter. For example:

```java
import java.util.function.Function;

final class Converter<Source, Target> {
    private final Function<? super Source, ? extends Target> function;

    Converter(Function<? super Source, ? extends Target> function) {
        this.function = function;
    }

    Target convert(Source value) {
        return function.apply(value);
    }
}
```

`Converter<Source, Target>` links source and target through a generic functional interface, yet **places no subtype bound between the two parameters**. This is a transformation contract, not `Target extends Source`. Two kinds of relationships must be distinguished:

1. **Subtype relationship**: `<Parent, Child extends Parent>` asserts that every `Child` value can be used as `Parent`.
2. **Transformation function relationship**: `Function<? super Source, ? extends Target>` asserts there is an operation turning source into result, even when `Source` and `Target` have no inheritance relationship.

If a type must support comparison with another type, the bound can reference a generic interface:

```java
// Illustrative signature snippet inside a Java class:
static <Other, T extends Comparable<Other>> int compare(
        T left, Other right) {
    return left.compareTo(right);
}
```

`T extends Comparable<Other>` guarantees `left.compareTo(right)` is valid, because `left` can be compared with `Other`. `T` does not have to be the same type as `Other`. When choosing arguments, there must be a real implementation satisfying `Comparable<Other>`.

### Different from simply using multiple types in a method

```java
static <A, B> String describe(A a, B b) {
    return String.valueOf(a) + "/" + String.valueOf(b);
}
```

This method simply declares two independent type parameters; **there is no cross-referencing bound**. Not every method using multiple type parameters is a method with dependent bounds.

## 7. Recursive Bound — Self-Referential Type Parameter

A bound type can refer to the very parameter being declared:

```java
class OrderedBox<T extends Comparable<T>> {
    private final T value;

    OrderedBox(T value) {
        this.value = value;
    }

    boolean isLessThan(T other) {
        return value.compareTo(other) < 0;
    }
}
```

Here `T` must be a type implementing `Comparable<T>`. For example, `String implements Comparable<String>` and `Integer implements Comparable<Integer>`, so `OrderedBox<String>` and `OrderedBox<Integer>` satisfy the bound.

The `<T extends Comparable<T>>` pattern is also called **F-bounded polymorphism** in the context of a type constrained by a generic construct containing itself. A common purpose is modeling the ability to "compare against the same type".

```java
OrderedBox<String> text = new OrderedBox<>("A");
boolean result = text.isLessThan("B"); // true.
```

Do not confuse this bound with direct self-inheritance syntax:

```java
// Invalid: a class cannot extend itself.
// class Loop extends Loop {}
```

In `T extends Comparable<T>`, `T` does not extend itself in the sense of a superclass declaration; it must implement **a generic interface** whose type argument points back to `T` itself.

## 8. Why Is `Comparable<? super T>` More Flexible Than `Comparable<T>`?

Consider the relationship:

```java
class Animal implements Comparable<Animal> {
    private final String name;

    Animal(String name) {
        this.name = name;
    }

    @Override
    public int compareTo(Animal other) {
        return name.compareTo(other.name);
    }
}

class Dog extends Animal {
    Dog(String name) {
        super(name);
    }
}
```

`Dog` inherits `Animal`'s comparison logic. Because `Animal implements Comparable<Animal>`, a `Dog` can be compared with other `Animal`s — yet `Dog` **does not automatically become `Comparable<Dog>`**. Java generics are not covariant: `Comparable<Animal>` and `Comparable<Dog>` are two distinct parameterized types.

Therefore, the narrow bound:

```java
// Can exclude Dog in the example above:
// static <T extends Comparable<T>> T max(Collection<T> items) { ... }
```

is less flexible than:

```java
static <T extends Comparable<? super T>> T max(
        java.util.Collection<? extends T> items) {
    java.util.Iterator<? extends T> iterator = items.iterator();
    if (!iterator.hasNext()) {
        throw new java.util.NoSuchElementException("Empty collection");
    }

    T best = iterator.next();
    while (iterator.hasNext()) {
        T candidate = iterator.next();
        if (candidate.compareTo(best) > 0) {
            best = candidate;
        }
    }
    return best;
}
```

Analysis:

- `T extends Comparable<? super T>`: type `T` must be comparable against `T` **or a parent type of `T`**.
- `Collection<? extends T>`: the source collection holds `T` or compatible subtypes of `T`, so iterating and reading as `T` is safe.
- `candidate.compareTo(best)`: verified by the compiler via the `Comparable<? super T>` bound.
- The return value is `T`: preserves the element type by contract instead of falling back to `Object`.

```java
// With List<Dog> and Dog extends Animal implements Comparable<Animal>:
List<Dog> dogs = List.of(new Dog("Bim"), new Dog("An"));
Dog selected = max(dogs); // Bim because "Bim" > "An" by String.compareTo.
```

This is an example of **a bound referencing a type parameter inside a wildcard of a bound**. The `? super T` part sits **inside the type argument of the `Comparable` interface**, and is not a direct "lower bound" declaration on `T`.

If you do not need to write the algorithm yourself, `Collections.max(...)` already provides a standard method with a similar contract and handles empty collections with an appropriate exception.

## 9. F-Bound in a Superclass: `N extends Node<N>`

Another advanced pattern is a **self-referential type parameter** for fluent APIs or object trees:

```java
abstract class Node<N extends Node<N>> {
    abstract N self();

    N touch() {
        return self();
    }
}

final class TaskNode extends Node<TaskNode> {
    @Override
    TaskNode self() {
        return this;
    }

    String finish() {
        return "done";
    }
}
```

`Node<N extends Node<N>>` means type `N` must belong to the `Node<N>` family. The subclass chooses `N = TaskNode` because `TaskNode extends Node<TaskNode>`:

```java
TaskNode node = new TaskNode();
String result = node.touch().finish(); // "done".
```

Thanks to the bound, `touch()` returns `N` instead of `Node<?>`, allowing code to continue calling methods on the concrete class without casting.

**Limitation to understand:** This pattern does not automatically prove at runtime that every subtype will choose itself as the type argument. Java allows certain inheritance patterns contrary to the designer's intent if the hierarchy is not controlled. When strictness is required, make concrete subclasses `final` or design appropriate interfaces/factories, while weighing the complexity of self-bounds.

### Self-referential bound of `Enum`

Java defines the enum concept using the base type `Enum<E extends Enum<E>>`. A generic method working with enums can use the bound:

```java
static <E extends Enum<E>> String enumName(E value) {
    return value.name();
}
```

`E` is both the concrete enum type and referenced back inside `Enum<E>`. For example, with `enum Status { NEW, DONE }`:

```java
// enumName(Status.DONE) returns "DONE".
```

This is a common application of F-bounds in the standard library, not a project-specific trick.

## 10. Class, Method, and Constructor Bounds

Dependent bounds are declared in the **type parameter list matching each scope**.

### 10.1. On a generic class

```java
class ParentChild<Parent, Child extends Parent> {
    private final Child child;

    ParentChild(Child child) {
        this.child = child;
    }

    Parent asParent() {
        return child;
    }

    Child child() {
        return child;
    }
}
```

`Parent` and `Child` belong to the class's scope; instance methods use them without redeclaring `<Parent, Child>`.

### 10.2. On a generic method inside an ordinary class

```java
class RelationalTools {
    static <Base, Derived extends Base> Base viewAsBase(Derived item) {
        return item;
    }
}
```

The two parameters belong only to the method; a non-generic class is completely allowed to declare this method. Because the `static` method has its own type parameters, it does not depend on any type argument of the enclosing class.

### 10.3. On a generic constructor

```java
class Description {
    private final String text;

    <Base, Derived extends Base> Description(
            Base general, Derived specialized) {
        this.text = general + " -> " + specialized;
    }

    String text() {
        return text;
    }
}
```

`Description` is not a generic class, yet its constructor **declares** `<Base, Derived extends Base>`. The subtype relationship is checked at each constructor call. A constructor in `class Holder<T>` can combine the class's `T` with a new type parameter:

```java
class Holder<T> {
    private final T value;

    <S extends T> Holder(S source) {
        this.value = source;
    }

    T get() {
        return value;
    }
}

// Holder<Number> h = new Holder<>(7); // S can be inferred as Integer.
```

Here `T` belongs to the `Holder<T>` **class**; `S` belongs to the **constructor** and is bounded by `T`. Do not redeclare `<T>` on the constructor: that would create a duplicate name shadowing the class's `T`.

Notice that a generic constructor places the type parameter list before the constructor name, with no return type.

## 11. Type Inference and Invariance of Generic Containers

When multiple parameters depend on each other, the compiler solves a system of constraints at each call site. You can write:

```java
// Class with static <Base, Item extends Base> List<Base> widen(...):
List<Number> values =
        DependentBoundsDemo.<Number, Integer>widen(List.of(1, 2));
```

Here the caller explicitly specifies `Base = Number` and `Item = Integer`; the compiler verifies `Integer extends Number` and returns `List<Number>`.

Meanwhile, the following assignment is **invalid**:

```java
List<Integer> ints = List.of(1, 2);
// List<Number> nums = ints; // Invalid: List<Integer> is not List<Number>.
```

The relationship `Integer extends Number` does not make `List<Integer> extends List<Number>`. If Java allowed it, a user of `List<Number>` could insert a `Double` into an object that promised to hold only `Integer`s.

### Use a wildcard when the source only produces data

```java
static <Base, Item extends Base> List<Base> widen(
        java.util.Collection<? extends Item> items) {
    java.util.List<Base> result = new java.util.ArrayList<>();
    result.addAll(items);
    return result;
}
```

`Collection<? extends Item>` guarantees elements can be read as `Item`; `Item extends Base` further permits adding each element into `List<Base>`. This is how to combine a **dependent type bound** and an **upper-bounded wildcard** without unchecked casts.

The bound in `<Base, Item extends Base>` creates a relationship between **type parameters**; the wildcard `? extends Item` in the method parameter enables **a specific collection value** to be passed in. Both use the `extends` keyword, but their scope and effect differ.

### Type witnesses and inference capability

A call like `widen(List.of(1, 2))` can be inferred by the compiler depending on context; sometimes `Base` may be chosen as a broader or unexpected type. To preserve a readable contract, declare the left-hand type explicitly or use a type witness `ClassName.<Number,Integer>method(...)`. Do not rely on raw `List` or unchecked casts to force the compiler's result.

## 12. Bound Ordering and Invalid Syntaxes

Comparison table of forms:

| Declaration | Status | Meaning |
| --- | --- | --- |
| `<A, B extends A>` | Valid | `B` is a subtype of `A`. |
| `<B extends A, A>` | Valid | Forward reference to `A` declared in the same list. |
| `<T extends Comparable<T>>` | Valid | `T` supports comparison with `T` itself. |
| `<T extends Comparable<? super T>>` | Valid | `T` supports comparison with `T` or a supertype. |
| `<E extends Enum<E>>` | Valid | Common recursive bound of enums. |
| `<A, B super A>` | Invalid | Type parameter declarations do not use `super` like wildcards. |
| `<A, B implements A>` | Invalid | Bounds use `extends`, not `implements`. |
| `<T extends Number & Comparable<T>>` | Valid | Class bound followed by interface bound. |
| `<T extends Comparable<T> & Number>` | Invalid | If `Number` is a class bound, it must precede interfaces. |
| `<T extends String>` | Syntactically valid, but no other reference type argument is valid | `String` is final; no new subtype can be created beyond `String` itself. Using `T = String` is still valid. |

**Note on the last row:** `<T extends String>` is a valid generic bound declaration (though rarely useful), because `T` can still be assigned `String` itself. Do not interpret `extends` as requiring a strict subtype; `String` satisfies its own `String` bound.

Example of multiple dependent bounds:

```java
// This is an illustrative signature.
static <T extends Number & Comparable<T>, U extends T>
        T chooseNumber(T general, U specific) {
    return specific;
}
```

`T` must first be a subtype of `Number` and implement `Comparable<T>`; next, `U` must be a subtype of `T`. Each bound adds a condition, without changing the meaning of `U extends T`.

If the compiler reports `type argument is not within bounds`, inspect each parameter's type argument in order. For example, `Pair<String,Integer>` fails because `Integer` is outside the domain permitted by `Sub extends Super` when `Super = String`.

## 13. Limitations: Raw Types, Type Erasure, Static Context

Type bounds are checked at compile time. Java generics primarily use **type erasure**, so runtime does not usually retain a separate class for each parameterization such as `Pair<Number,Integer>` or `Pair<CharSequence,String>`.

```java
// Generic types cannot be directly instantiated or checked at runtime:
// T value = new T();            // Invalid with T as a type parameter.
// Class<T> clazz = T.class;     // Invalid.
// if (object instanceof Pair<Number, Integer>) { } // Invalid: non-reifiable type arguments.
```

You can check `object instanceof Pair<?, ?>` to verify the class shape, but that check does not prove the specific type arguments or the actual data types stored in each field. When receiving data from external sources, values must still be validated if wrong-type data is a risk.

### Raw types can break a bound's promise

```java
Pair<Number, Integer> correct = new Pair<>(1.5, 4);
// Pair raw = correct; // Raw form loses information about both type arguments.
```

Do not use raw `Pair` and cast to `Pair<String,Integer>` to bypass compiler bounds. Raw types and unchecked conversions can cause **heap pollution**, leading to `ClassCastException` later when values are read. Bounds are not a runtime data validation mechanism replacing validation.

### Static members cannot borrow the class's type parameters

```java
class Container<Base, Item extends Base> {
    // static Item last; // Invalid: Item belongs to the class, not a static member.

    static <X, Y extends X> X promote(Y value) {
        return value;
    }
}
```

`Base`/`Item` are type parameters of `Container`, so they are used in instance fields/methods. A static generic method must **declare its own `<X,Y extends X>`**; the two new parameters are independent of the class's type parameters.

## 14. Complete, Tested Java 17+ Program

Create the file **`DependentBoundsDemo.java`** with the exact contents below. The code illustrates:

- A bound between two type parameters on class `Pair<Super, Sub extends Super>`.
- A subclass fixing type arguments `NumberPair extends Pair<Number,Integer>`.
- Generic methods `choose` and `widen` using `Sub extends Super`.
- Self-referential bound `Comparable<? super T>` via `Dog extends Animal implements Comparable<Animal>`.
- F-bounds `E extends Enum<E>` and `N extends Self<N>`.

```java
import java.util.*;

public class DependentBoundsDemo {
    static class Animal implements Comparable<Animal> {
        private final String name;

        Animal(String name) { this.name = name; }
        String name() { return name; }

        @Override
        public int compareTo(Animal other) {
            return name.compareTo(other.name);
        }
    }

    static final class Dog extends Animal {
        Dog(String name) { super(name); }
    }

    static class Pair<Super, Sub extends Super> {
        private final Super first;
        private final Sub second;

        Pair(Super first, Sub second) {
            this.first = first;
            this.second = second;
        }

        Super first() { return first; }
        Sub second() { return second; }
    }

    static final class NumberPair extends Pair<Number, Integer> {
        NumberPair(Number first, Integer second) {
            super(first, second);
        }
    }

    static <Super, Sub extends Super> Super choose(
            boolean useSub, Super first, Sub second) {
        return useSub ? second : first;
    }

    static <T extends Comparable<? super T>> T max(
            Collection<? extends T> source) {
        Iterator<? extends T> iterator = source.iterator();
        if (!iterator.hasNext()) {
            throw new NoSuchElementException("empty");
        }

        T best = iterator.next();
        while (iterator.hasNext()) {
            T value = iterator.next();
            if (value.compareTo(best) > 0) {
                best = value;
            }
        }
        return best;
    }

    static <E extends Enum<E>> String enumName(E value) {
        return value.name();
    }

    enum Status { NEW, DONE }

    static abstract class Self<N extends Self<N>> {
        abstract N self();

        N fluent() {
            return self();
        }
    }

    static final class Task extends Self<Task> {
        @Override
        Task self() { return this; }

        String finish() { return "done"; }
    }

    static <Base, Item extends Base> List<Base> widen(
            Collection<? extends Item> items) {
        List<Base> result = new ArrayList<>();
        result.addAll(items);
        return result;
    }

    public static void main(String[] args) {
        Pair<Number, Integer> pair = new Pair<>(3.5, 7);
        System.out.println("pair: " + pair.first() + " / " + pair.second());

        System.out.println("choice: " +
                DependentBoundsDemo.<Number, Integer>choose(true, 1.5, 9));

        List<Dog> dogs = List.of(new Dog("Bim"), new Dog("An"));
        System.out.println("max dog: " + max(dogs).name());

        System.out.println("enum: " + enumName(Status.DONE));
        System.out.println("self: " + new Task().fluent().finish());

        List<Number> numbers =
                DependentBoundsDemo.<Number, Integer>widen(List.of(2, 4));
        System.out.println("widen: " + numbers);

        NumberPair np = new NumberPair(1.2, 3);
        System.out.println("fixed: " + np.second());
    }
}
```

Compile and run on JDK 17+:

```bash
javac --release 17 -Xlint:all DependentBoundsDemo.java
java DependentBoundsDemo
```

**Exact stdout** (run with `--release 17`-compatible `javac`, zero warnings from `-Xlint:all`):

```text
pair: 3.5 / 7
choice: 9
max dog: Bim
enum: DONE
self: done
widen: [2, 4]
fixed: 3
```

Output explanation:

1. `Pair<Number,Integer>` stores `3.5` as `Number` and `7` as `Integer`, due to the bound `Integer extends Number`.
2. The type witness `<Number,Integer>` on `choose` makes the relationship explicit; the function returns the second branch `9` with result type `Number`.
3. `Dog` inherits `Comparable<Animal>` via `Animal`; the `Comparable<? super Dog>` bound matches, so `max(dogs)` returns a `Dog`. `"Bim"` is greater than `"An"` per `String.compareTo`.
4. `Status.DONE` is an enum value satisfying `E extends Enum<E>`; `enumName` returns the constant name `DONE`.
5. `Task extends Self<Task>`, so `fluent()` has type `Task`; the chained call `finish()` succeeds.
6. `widen` copies an `Integer` source into a new `List<Number>`. It does not attempt to cast an existing `List<Integer>` to `List<Number>`.
7. `NumberPair` extends the generic class with fixed type arguments and its `second()` getter returns `Integer`.

## 15. Common Errors and How to Fix Them

| Symptom | Explanation | Solution |
| --- | --- | --- |
| `Pair<String,Integer>` reports a bound violation | `Integer` is not a subtype of `String` | Choose type arguments that actually have a subtype relationship. |
| `<Super, Sub super Super>` does not compile | Type parameter bound declarations do not use `super` | Write `<Super, Sub extends Super>`. |
| `<T implements Comparable<T>>` does not compile | Type parameter bounds use `extends` even for interfaces | Write `<T extends Comparable<T>>`. |
| `List<Integer>` cannot be assigned to `List<Number>` | Generic type arguments are invariant | Use `List<? extends Number>` for reading, or copy into a suitable target list. |
| `<T extends Comparable<T>>` rejects some subtypes | A subtype may only implement `Comparable<Supertype>` | Consider `<T extends Comparable<? super T>>`. |
| `static Sub method(...)` inside `class Pair<Super,Sub>` fails | Static members cannot reference class type parameters | Declare new type parameters on the static method. |
| Trying `new T()` in a generic method | Erasure does not provide `T`'s constructor | Accept `Supplier<? extends T>`/a factory. |
| Using raw `Pair` to drop warnings | Removes generic checks instead of solving the bound properly | Keep parameterized types; validate legacy data at the boundary. |
| Assuming `Sub extends Super` must be a direct subclass | Subtyping can span multiple levels or be the same type | Rely on the subtype relation checked by the compiler. |
| Reading `Comparable<? super T>` as "T has a super bound" | `super` belongs to the wildcard inside `Comparable` | Separate the syntactic layers: bound `extends Comparable<...>` and wildcard `? super T`. |
| Arbitrary circular bounds causing errors | Not every dependency cycle is valid | Use well-understood F-bound patterns and avoid overly complex type hierarchies. |
| Compiler infers a different target type than intended | Multiple type argument assignments satisfy the bounds | Specify an explicit target type or an explicit type witness. |

### Debugging workflow for calls with dependent bounds

1. Identify the type parameter declaration list: after a class name, before a method/constructor name, or inside a generic interface?
2. Sketch the `Sub <: Super` relationship for `Sub extends Super`, and identify the concrete types the caller wants to pass.
3. For `T extends Comparable<? super T>`, check whether `T` implements `Comparable` for itself or for a supertype.
4. If collections are involved, separate **type parameter relationships** from **collection parameterization relationships**: `List<Integer>` differs from `List<Number>`.
5. If inference is confusing, add a type witness at the call site or declare the result type explicitly; read compiler diagnostics instead of hiding errors with casts.
6. For legacy/raw code, validate data before passing it into generic APIs so heap pollution does not spread.

## 16. Practice Exercises

**Exercise 1 — Two-parameter bound.** Write `class Holder<Base, Child extends Base>` with `Child get()` and `Base asBase()`. Construct `Holder<Number,Integer>`, try `Holder<CharSequence,String>`, and analyze why `Holder<String,Integer>` fails.

**Exercise 2 — Forward reference.** Write a class `Forward<A extends B,B>` and method `static <A extends B,B> B promote(A input)`. Compile on Java 17 and explain why `B` appearing afterward is still accepted. Then reorder to `<B,A extends B>` to improve readability.

**Exercise 3 — Recursive bound.** Write `static <T extends Comparable<? super T>> T min(Collection<? extends T> values)`, handling an empty collection explicitly. Test with `List<Integer>`, `List<String>`, and a subclass of a parent class implementing `Comparable<Parent>`.

**Exercise 4 — Enum F-bound.** Write `static <E extends Enum<E>> boolean sameName(E a, E b)` comparing `a.name()` and `b.name()`. Explain how `E` constrains both parameters to the same enum type in the signature (a caller cannot normally pass two different enum types to a single `E`).

**Exercise 5 — Self-bound.** Write `abstract class Fluent<S extends Fluent<S>>` with method `S configure()` relying on `S self()`; create a concrete class `Query extends Fluent<Query>`. Test `new Query().configure().execute()` where `execute()` belongs to `Query`.

**Exercise 6 — Invariance and copying.** Create `List<Integer> input = List.of(1,2,3)`. Demonstrate that it cannot be assigned directly to `List<Number>`; use `widen` with `<Number,Integer>` to obtain a wider numeric list. Try adding a `Double` to the result and explain why this does not mutate the original source.

**Exercise 7 — API design.** A system has `class Animal` and `class Dog extends Animal`. You need a function taking a `Collection<Dog>` source and returning `List<Animal>`. Compare a signature using two type parameters `<Base,Derived extends Base>` with a signature using only `Collection<? extends Animal>`. When does a dependent bound actually bring benefits, and when does it only add complexity?

## 17. Summary

**Bounds referencing another type parameter** let you express relationships that Java can prove at compile time:

- `<A, B extends A>`: `B` is a valid subtype of `A`; usable in classes, generic methods, or constructors.
- `<T extends Comparable<T>>`: `T` is comparable with type `T` itself via the interface.
- `<T extends Comparable<? super T>>`: a more flexible version when a type inherits comparability with a supertype.
- `<E extends Enum<E>>`, `<N extends Node<N>>`: self-referential **F-bounds**, useful for enums and self-typed APIs.
- Dependent bounds and wildcards are related but not identical; Java generics are **invariant** by default, so `List<Derived>` is not automatically `List<Base>`.
- Type inference, erasure, and static contexts do not erase the meaning of bounds: use accurate declared types and let the compiler protect subtype relationships.

When encountering a hard-to-read generic signature, identify each parameter, each bound, and the direction data flows through the API. The most important question is **"Can a value of this type parameter be safely used where the other type parameter is required?"**. If you can express the answer using a bound such as `Sub extends Super` or `T extends Comparable<? super T>`, you are using generics for their true purpose: **reusing algorithms while preserving type safety**.