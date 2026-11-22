# Adding New Type Parameters in a Subclass with Java Generics Inheritance

A subclass of a generic class **can declare more type parameters than its superclass**. The subclass decides which type parameters are passed to the superclass and which type parameters are used for its own additional data/behavior. For example, if `Box<T>` holds a value `T`, the subclass `TaggedBox<T, M>` can inherit that value and add a marker (metadata) of type `M`.

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

class TaggedBox<T, M> extends Box<T> {
    private final M marker;

    TaggedBox(T value, M marker) {
        super(value);
        this.marker = marker;
    }

    M marker() {
        return marker;
    }
}
```

These are **two illustrative class definitions**, without a `main` method yet. The core relationship is on the line `class TaggedBox<T, M> extends Box<T>`:

- `<T, M>` declares **two type parameters of the subclass**. `T` is the value type, and `M` is the marker type added by the subclass.
- `extends Box<T>` passes **only `T`** for the superclass's type parameter. `Box<T>` does not automatically know about `M`.
- `super(value)` calls the superclass constructor to set up the `T` state.
- `marker` and `marker()` are the extensions tied to the subclass's own type parameter `M`.
- `TaggedBox<String, Integer>` is a subtype of `Box<String>` because it `extends Box<T>` with `T = String`; it is not a subtype of `Box<Integer>`.

This design is very useful when a subtype needs to attach extra information such as an identifier, label, unit of measurement, status type, or processing policy, while still reusing the superclass's general contract.

## 1. General Syntax: Subclass Declares Types and Maps to the Superclass

A common form:

```java
class Parent<A> {
    // Members based on A
}

class Child<A, B> extends Parent<A> {
    // Can use A inherited according to the relationship with Parent<A>
    // and add state/behavior based on B
}
```

The example above only illustrates **inheritance syntax**, without functionality for the pair `A`, `B`. The key points are:

1. The `<A, B>` list after `Child` **declares** `Child`'s type parameters.
2. The `<A>` list after `Parent` in `extends Parent<A>` contains **the type arguments** passed to the superclass.
3. The compiler applies that mapping to determine the types of `Parent`'s members when viewed from `Child`.
4. The extra type parameter `B` in the subclass does not have to play any role in the superclass; it can serve only the new fields and methods.

`extends` describes the **class inheritance relationship**, whereas `<...>` describes **type parameterization**. There is no rule saying the subclass must use only the exact number of type parameters of the superclass, nor is it required to keep the same type parameter names or order.

An example with a different mapping:

```java
class Parent<T> { }

class Child<K, V> extends Parent<V> { }
```

This subclass sends **`V`** to `Parent`'s `T`, leaving `K` for the subclass's own functionality. With `Child<String, Integer>`, the parameterized supertype is `Parent<Integer>`, **not `Parent<String>`**. The names `K` and `V` are only conventions: the actual relationship is determined by `extends Parent<V>`.

## 2. Subclass Preserves Parent Type and Adds a New Type

Suppose the superclass manages an element `T`, and the subclass needs to add metadata of type `M`:

```java
class Item<T> {
    private final T data;

    Item(T data) {
        this.data = data;
    }

    T data() {
        return data;
    }
}

class LabeledItem<T, M> extends Item<T> {
    private final M label;

    LabeledItem(T data, M label) {
        super(data);
        this.label = label;
    }

    M label() {
        return label;
    }
}
```

These two classes are **alternative illustrative definitions**; do not name them identically to classes in the same package if those already exist. When used inside a method:

```java
LabeledItem<String, Integer> item =
        new LabeledItem<>("book", 101);

String value = item.data();
Integer label = item.label();
```

Thanks to `extends Item<T>`, the return type of the inherited method `data()` is `String` on `LabeledItem<String, Integer>`, not `Object`. Meanwhile, `label()` has type `Integer` thanks to the new type parameter `M`.

If you declare `LabeledItem<String, Integer>` and then pass a `Boolean` in position `M`, the compiler catches the error immediately. You also do not need to cast an `Integer` label to the right type after reading it.

Prerequisite: type arguments passed to the parent class/interface must satisfy **all upper bounds** in the parent's declaration. For example, if the parent is `class Parent<T extends Number>`, the subclass cannot simply write `class Child<T, M> extends Parent<T>` with a completely unbounded `T`; it must ensure `T` satisfies `Number`.

## 3. A Subclass Can Fix the Parent Type While Still Adding Its Own Type

Not every type parameter of a subclass needs to be passed to the superclass. For example:

```java
class Base<T> {
    private final T value;

    Base(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class TextMetadata<M> extends Base<String> {
    private final M metadata;

    TextMetadata(String text, M metadata) {
        super(text);
        this.metadata = metadata;
    }

    M metadata() {
        return metadata;
    }
}
```

These are **two standalone illustrative classes**. `TextMetadata<M>` has exactly one type parameter `M` of its own, yet extends `Base<String>` with **fixed type argument `String`**, without sending `M` to the parent.

When called:

```java
TextMetadata<Long> entry = new TextMetadata<>("hello", 99L);

String text = entry.get();
Long meta = entry.metadata();
```

`get()` always returns `String` for any `TextMetadata<M>`, while `metadata()` changes type according to `M`. Therefore:

- `TextMetadata<Long>` is a subtype of `Base<String>`.
- `TextMetadata<Boolean>` is also a subtype of `Base<String>`.
- `TextMetadata<Long>` does not automatically become a subtype of `Base<Long>`.

This is a good design when the subtype represents **a specialized kind of the parent's data**, while the additional data still needs to remain generic.

## 4. Standalone Java 17 Example: Three Ways to Add Subclass Type Parameters

Save the entire following program as **`ExtraSubclassTypeParameterDemo.java`**:

```java
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

public class ExtraSubclassTypeParameterDemo {
    static class Box<T> {
        private final T value;

        protected Box(T value) {
            this.value = value;
        }

        public T get() {
            return value;
        }

        public String describe() {
            return "Box(" + value + ")";
        }
    }

    static final class TaggedBox<T, M> extends Box<T> {
        private final M marker;

        private TaggedBox(T value, M marker) {
            super(value);
            this.marker = marker;
        }

        static <V, L> TaggedBox<V, L> of(V value, L marker) {
            return new TaggedBox<>(value, marker);
        }

        public M marker() {
            return marker;
        }

        @Override
        public String describe() {
            return "Tagged(" + get() + ", " + marker + ")";
        }

        public <U> TaggedBox<U, M> mapValue(
                Function<? super T, ? extends U> mapper) {
            Objects.requireNonNull(mapper, "mapper");
            return TaggedBox.of(mapper.apply(get()), marker);
        }
    }

    static final class TextTagged<M> extends Box<String> {
        private final M metadata;

        TextTagged(String text, M metadata) {
            super(text);
            this.metadata = metadata;
        }

        M metadata() {
            return metadata;
        }
    }

    interface Identifiable<ID> {
        ID id();
    }

    static final class Identified<T, ID>
            extends Box<T> implements Identifiable<ID> {
        private final ID id;

        Identified(T value, ID id) {
            super(value);
            this.id = id;
        }

        @Override
        public ID id() {
            return id;
        }
    }

    static final class NumericTagged<N extends Number, M>
            extends Box<N> {
        private final M marker;

        NumericTagged(N value, M marker) {
            super(value);
            this.marker = marker;
        }

        double twice() {
            return get().doubleValue() * 2;
        }

        M marker() {
            return marker;
        }
    }

    public static void main(String[] args) {
        TaggedBox<String, Integer> tagged = TaggedBox.of("Java", 7);
        System.out.println("tagged: " + tagged.describe());
        System.out.println("types: " + tagged.get().toUpperCase()
                + "/" + (tagged.marker() + 1));

        Box<String> parentView = tagged;
        System.out.println("upcast: " + parentView.get());
        System.out.println("dispatch: " + parentView.describe());

        TaggedBox<Integer, Integer> mapped =
                tagged.mapValue(String::length);
        System.out.println("mapped: " + mapped.describe());

        TextTagged<Long> fixed = new TextTagged<>("Hi", 99L);
        System.out.println("fixed: " + fixed.get()
                + "/" + fixed.metadata());

        Identified<List<Integer>, String> identified =
                new Identified<>(List.of(2, 4, 6), "batch-1");
        System.out.println("identified: " + identified.id()
                + "=" + identified.get());

        Identifiable<String> interfaceView = identified;
        System.out.println("interface: " + interfaceView.id());

        NumericTagged<Integer, String> numeric =
                new NumericTagged<>(8, "units");
        System.out.println("numeric: " + numeric.twice()
                + "/" + numeric.marker());

        List<Box<String>> boxes = List.of(tagged, fixed);
        System.out.println("boxes: " + boxes.size());
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac ExtraSubclassTypeParameterDemo.java
java ExtraSubclassTypeParameterDemo
```

Stdout in exact order:

```text
tagged: Tagged(Java, 7)
types: JAVA/8
upcast: Java
dispatch: Tagged(Java, 7)
mapped: Tagged(4, 7)
fixed: Hi/99
identified: batch-1=[2, 4, 6]
interface: batch-1
numeric: 16.0/units
boxes: 2
```

### Example Analysis

**Case A — `TaggedBox<T, M> extends Box<T>`.** The subclass keeps the parent's value type via `T`, then adds marker `M`. When `T = String`, `get()` returns `String`; when `M = Integer`, `marker()` returns `Integer`. The expression `tagged.marker() + 1` is valid thanks to wrapper unboxing.

**Case B — upcasting preserves the exact parent type.** `Box<String> parentView = tagged;` is valid because `TaggedBox<String, Integer>` extends `Box<String>`. Through `parentView`, the compiler still knows `get()` returns `String`, but does not allow calling `marker()` directly because that method is not declared on `Box<String>`. Calling `parentView.describe()` still performs **dynamic dispatch** to `TaggedBox`'s override, so the output is `Tagged(Java, 7)`.

**Case C — an independent generic method inside a generic subclass.** `mapValue` declares `<U>` on the **method**, independent of `T` and `M` on the **class**. It transforms the value from type `T` to `U` while keeping the marker `M`. Thus `TaggedBox<String, Integer>` becomes `TaggedBox<Integer, Integer>` when mapped with `String::length`. The wildcard `Function<? super T, ? extends U>` lets the function consume a broader type than `T` and produce a result of an appropriate subtype of `U`.

**Case D — `TextTagged<M> extends Box<String>`.** The parent's data type is **fixed** to `String`; `M` is solely for the subclass's metadata. `TextTagged<Long>` is still a `Box<String>`, not a `Box<Long>`.

**Case E — `Identified<T, ID> extends Box<T> implements Identifiable<ID>`.** The subclass passes `T` to the superclass and `ID` to the interface. A subclass can extend **one class** and implement **multiple interfaces**; the type arguments in each relationship are checked against the corresponding declaration. Here `Identified<List<Integer>, String>` stores a list of integers and a string identifier; through `Identifiable<String>`, method `id()` still returns `String`.

**Case F — `NumericTagged<N extends Number, M>`.** The subclass enforces the bound `N extends Number` to use `doubleValue()`. The `Number` bound also ensures `N` is suitable as a type argument for `Box<N>`. `NumericTagged<Integer, String>` is valid, whereas `NumericTagged<String, Integer>` will not compile.

**Case G — collection of the parent type.** `List<Box<String>> boxes = List.of(tagged, fixed);` is valid because **both objects** have supertype `Box<String>` and the target context matches. This does not mean you can directly assign an entire `List<TaggedBox<String, Integer>>` to `List<Box<String>>`: Java generic collections remain **invariant**, as discussed below.

## 5. Type Parameter Mappings Between Parent and Child Do Not Require Matching Names

The compiler does not rely on the names `T`, `U`, `K`, `V` to connect parent and child types. It relies on **the type argument expression in the `extends` clause**.

```java
class Parent<P> {
    P get() {
        return null;
    }
}

class Child<A, B> extends Parent<B> {
    private A extra;
}
```

These are **illustrative classes**—do not use `null` as a production contract value; the body only serves to show the return type. `Child<String, Integer>` extends `Parent<Integer>` and `get()` returns type `Integer`, while `extra` is `String`.

A compound type can be used as the parent's type argument:

```java
class Parent<T> { }

class Aggregated<A, B> extends Parent<java.util.List<A>> {
    private final B metadata;

    Aggregated(B metadata) {
        this.metadata = metadata;
    }
}
```

With `Aggregated<String, Long>`, its supertype is `Parent<List<String>>`. Thus, a subclass **does not have to** pass a bare type parameter directly; it can pass a parameterized type constructed from the subclass's type parameters. However, every type in the declaration must be valid and satisfy the parent's bounds.

**Recognizing the proper scope:** symbols in `class Child<A,B>` are declared by the subclass; `Parent<B>` uses that symbol `B` as a type argument. `Parent` does not "gain" a type parameter `A`; the subtype itself is what owns the extra information.

## 6. Adding a New Type to Implement a Generic Interface

The general inheritance pattern also appears when a subclass implements an interface:

```java
interface HasKey<K> {
    K key();
}

class ValueHolder<T> {
    private final T value;

    ValueHolder(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}

class KeyedHolder<T, K> extends ValueHolder<T>
        implements HasKey<K> {
    private final K key;

    KeyedHolder(T value, K key) {
        super(value);
        this.key = key;
    }

    @Override
    public K key() {
        return key;
    }
}
```

These are **three illustrative declarations**, without needing to combine them with the `Box` class in the full runnable program. When using `KeyedHolder<String, Long>`:

- Superclass relationship: `ValueHolder<String>`, so `get()` returns `String`.
- Interface relationship: `HasKey<Long>`, so `key()` returns `Long`.
- Both `T` and `K` are declared on the subclass, then passed into **two different contracts**.

A `KeyedHolder<String, Long>` object can be assigned to a variable of type `ValueHolder<String>` or `HasKey<Long>`. However, through the interface-typed variable, only the methods declared by the interface are visible.

If an interface itself extends another generic interface, it can also **declare additional type parameters**:

```java
interface Reader<T> {
    T read();
}

interface AuditedReader<T, AUDIT> extends Reader<T> {
    AUDIT audit();
}
```

`AuditedReader<String, Integer>` is a subtype of `Reader<String>`, and also has `audit()` returning `Integer`. This is **interface inheritance**, not class inheritance; the syntax still uses similar type parameter mapping.

## 7. Type Bounds When a Subclass Adds Type Parameters

If the superclass has a bound:

```java
class NumericBox<N extends Number> {
    private final N number;

    NumericBox(N number) {
        this.number = number;
    }

    double value() {
        return number.doubleValue();
    }
}
```

then a subclass forwarding one of its type parameters to the parent must declare a compatible bound:

```java
class Measured<N extends Number, UNIT> extends NumericBox<N> {
    private final UNIT unit;

    Measured(N number, UNIT unit) {
        super(number);
        this.unit = unit;
    }

    UNIT unit() {
        return unit;
    }
}
```

These are two valid illustrative classes placed in an appropriate context. `Measured<Integer, String>` is valid; `Measured<String, String>` is invalid because `String` is not a subtype of `Number`.

Invalid version:

```java
// class WrongMeasured<N, UNIT> extends NumericBox<N> { }
// Does not compile: N is not bounded as a subtype of Number.
```

The subclass can also place bounds on **the new type parameter** if needed, for example `<T, M extends Comparable<M>>`, provided the bounds and types are used appropriately. There is no need to attach a bound just for adding a parameter: an unbounded `M` is valid if the API does not require specialized operations on `M`.

### Multiple Bounds and Combined Constraints

A type parameter can have multiple bounds such as `<X extends Number & Comparable<X>>`. When there is a class bound, it must come before interface bounds, followed by interfaces separated by `&`. Do not write `<X super Number>` to declare a lower bound; `? super X` is a wildcard at the use site of a generic type.

Subclass type parameters can relate to one another via bounds, though adding too many constraints makes signatures hard to read. Add bounds to reflect genuinely needed operations, not merely to increase complexity.

## 8. Checking Subtyping Accurately per Type Argument

`TaggedBox<String,Integer> extends Box<String>`, so such a `TaggedBox` object can be used wherever `Box<String>` is accepted; the type argument **M=Integer** serves only the subclass's metadata part.

```java
TaggedBox<String, Integer> tagged = TaggedBox.of("x", 1);
Box<String> base = tagged;
// Box<Object> tooWide = tagged; // Invalid.
List<? extends Box<String>> view = List.of(tagged);
```

**Distinguish two levels of invariance:** `Box<String>` is not `Box<Object>`; similarly, `List<TaggedBox<String,Integer>>` is not automatically `List<Box<String>>`. If only reading elements, a bounded wildcard like `List<? extends Box<String>>` expresses the relationship accurately; it does not grant permission to write an arbitrary `Box` into it. This is a restriction on **type arguments at the use site**, and does not negate the fact that `TaggedBox` itself extends `Box<String>`.

## 9. Java's Limitations When Designing Generic Subclasses

### 9.1. Java Supports Only a Single Superclass

A Java class can `extends` only **one** class, though it can `implements` multiple interfaces. Therefore, to integrate multiple type contracts, choose one superclass and add generic interfaces, or favor composition where appropriate. Adding new type parameters does not turn Java into a language with multiple class inheritance.

### 9.2. Cannot Inherit Two Parameterizations of the Same Interface

A subtype cannot simultaneously inherit `Holder<String>` and `Holder<Integer>` of the same declaration `Holder<T>`, even when inheritance paths go through intermediate interfaces. This is Java's superinterface consistency rule, **not merely** an overload conflict due to erasure; even an empty marker interface `Marker<T>` is subject to that restriction.

If a class needs both to hold a value `T` and provide an ID, two **different interfaces** like `ValueSource<T>` and `Identifiable<ID>` (used in sections 4/6) express those roles more clearly. If two instantiations of the **same** interface are needed, create two objects and coordinate them via composition rather than forcing one class to inherit both.

### 9.3. Raw Types Lose Type Checking

Writing `extends Base` instead of `extends Base<String>` when `Base` is a generic class can lead to using **raw types** and losing type guarantees. Do not omit `<...>` just to make the compiler accept legacy code. In most modern programs, the subclass should **pass an appropriate type argument** to its generic superclass.

Example:

```java
// Avoid: class RawChild<X> extends Box { ... }
// Prefer: class TypedChild<X> extends Box<X> { ... }
```

The two lines are **syntax sketches**, not complete class definitions. Raw types can cause unchecked warnings, compiler-inserted casts, and runtime `ClassCastException` risks.

### 9.4. Type Erasure and the Inability to Check Specific Type Arguments at Runtime

`TaggedBox<String, Integer>` and `TaggedBox<Integer, String>` are both parameterizations of the same class `TaggedBox`, not two separate runtime classes.

Valid example:

```java
if (obj instanceof TaggedBox<?, ?>) {
    System.out.println("some tagged box");
}
```

This is an illustrative snippet requiring a variable `obj` of an appropriate type inside a method. Do not write `obj instanceof TaggedBox<String, Integer>` as if the JVM could check every erased type argument. The result of `instanceof TaggedBox<?, ?>` safely confirms the raw class type for a general pattern, **not** that `T = String` and `M = Integer`.

Note: using `@Override` on genuinely overridden methods helps the compiler verify signatures. With generic inheritance, bridge methods may be generated by the compiler after erasure to preserve overriding; you should not write bridge methods manually or rely on their existence as a public API.

## 10. Subclass Type Parameters vs. Independent Method Type Parameters

Inside `TaggedBox<T, M>`, you can declare a separate generic method:

```java
public <U> TaggedBox<U, M> mapValue(
        Function<? super T, ? extends U> mapper) {
    return TaggedBox.of(mapper.apply(get()), marker);
}
```

This is a **method excerpt** from the `TaggedBox<T,M>` example; it requires `Function`, access to `get()`, the `marker` field, and an appropriate `of` factory in the enclosing class.

Three distinct type scopes:

- `T`: class type parameter passed to superclass `Box<T>`.
- `M`: additional class type parameter of the subclass, preserved in the result.
- `U`: **new method type parameter** describing the type of the transformed value.

Calling `TaggedBox<String, Integer>.mapValue(String::length)` does not mutate `T` of the existing object. It **creates a new `TaggedBox<Integer, Integer>`** in the example, while the old object still holds `String`. This is an advantage of immutable design: the transformation returns a new object with the relationship among type parameters expressed explicitly.

A static factory belonging to `TaggedBox<T, M>` must declare its own **method** type parameters, because a static context cannot directly use the class's type parameters. Example:

```java
static <V, L> TaggedBox<V, L> of(V value, L marker) {
    return new TaggedBox<>(value, marker);
}
```

The letters `V` and `L` are chosen to emphasize that they belong exclusively to the factory; they do not "borrow" `T` and `M` from an instance. You could name the factory parameters `<T, M>` under shadowing rules, but doing so easily causes confusion in a lesson on type scoping.

## 11. Common Mistakes When Adding Type Parameters in a Subclass

**Mistake 1 — Confusing the number of type parameters of parent and child.** If the parent is `Box<T>`, the child can still be `TaggedBox<T, M>`. However, the `extends Box<T>` clause must pass **exactly one** valid type argument for `Box`; do not write `extends Box<T, M>` if `Box` only declares one type parameter.

**Mistake 2 — Forgetting to pass a type parameter to the superclass.** `extends Box` uses a raw type; `extends Box<T>` preserves type safety and the return type relationships of inherited methods.

**Mistake 3 — Assuming `M` automatically exists in the superclass.** `TaggedBox<T, M> extends Box<T>` does not make `Box<T>` aware of `M`. To use `M` through a variable typed as `Box<T>`, design an additional API on the superclass, another interface, or a safe check/cast when justified.

**Mistake 4 — Failing to call an appropriate parent constructor.** If `Box<T>` only has constructor `Box(T value)`, the subclass constructor must call `super(value)` as its first action or use valid constructor delegation. There is no default `Box()` constructor for the compiler to invoke automatically.

**Mistake 5 — Passing the wrong type parameter to the parent.** `Child<A,B> extends Parent<B>` means the parent type is `Parent<B>`. If you intended to keep type `A` but wrote `Parent<B>`, inherited methods will have types that do not match the intended contract.

**Mistake 6 — Forgetting bounds when the parent has bounds.** `Base<N extends Number>` does not accept a completely unbounded `N` from the subclass; declare `<N extends Number, M>` or use a type argument that satisfies the constraint.

**Mistake 7 — Confusing subtyping with variance.** `TaggedBox<String, Integer>` is a subtype of `Box<String>`, but not of `Box<Object>` or `TaggedBox<Object, Integer>`. An appropriate wildcard is needed if an API only wants to read at a broader type.

**Mistake 8 — Thinking a subclass with `<T, M>` must always use `T` as the parent's type.** Not required. `class Child<T, M> extends Parent<M>` and `class Child<M> extends Parent<String>` can both be valid designs; choose the mapping according to data semantics.

**Mistake 9 — Confusing class and method type parameters.** `<U> TaggedBox<U, M> mapValue(...)` declares `U` on the method; `U` does not alter the type of an existing `TaggedBox<T, M>` object.

**Mistake 10 — Trying to use the class's `T` or `M` in a static factory without declaring them separately.** A static method must have its own type parameters such as `static <V,L> TaggedBox<V,L> of(...)`.

**Mistake 11 — Using raw types and casting arbitrarily.** If forced to interoperate with legacy Java code, isolate raw types and validate data at the boundary; do not use unchecked casts as a general inheritance solution.

**Mistake 12 — Assuming `final` makes fields of types `T` and `M` deeply immutable.** `private final T value` only prevents reassigning the reference. If `T` or `M` points to a mutable list, the list's internal state can still change.

**Mistake 13 — Creating multiple inheritance paths to the same generic interface with conflicting type arguments.** Java does not allow inheriting that same interface under two different parameterizations simultaneously in a single hierarchy. Fix the model or use an interface with multiple type parameters.

## 12. How to Decide Whether to Add a Type Parameter in a Subclass

When designing an API, check four questions:

1. **Does the new data have an independent type that remains stable throughout the object's lifetime?** For example, `TaggedBox<T, M>` needs to retain the label's type, so `M` adds value.
2. **What part does the superclass already describe?** If the parent only manages `T`, the subclass should only add what lies outside that contract; do not unexpectedly change the meaning of `T`.
3. **Does `extends Parent<...>` preserve the right inherited types?** Filling in `T`, `M`, `List<T>`, or a fixed type should follow business semantics, not symbol names.
4. **Is inheritance needed?** If the new type is just a combined data component rather than genuinely a subtype of the parent, composition may be simpler.

An example replacing inheritance with composition when there is no true "is-a" relationship:

```java
final class Annotated<T, M> {
    private final T value;
    private final M metadata;

    Annotated(T value, M metadata) {
        this.value = value;
        this.metadata = metadata;
    }

    T value() {
        return value;
    }

    M metadata() {
        return metadata;
    }
}
```

This is **an illustrative class** that does not extend `Box<T>`; it bundles two components under one type rather than creating a subtype. If API callers do not need to pass `Annotated<T, M>` wherever `Box<T>` is expected, this can be an easier option to maintain.

## 13. Self-Check Questions with Answers

**Question 1.** How many type parameters does `class Child<T, M> extends Parent<T>` declare on the subclass?  
**Answer:** Two: `T` and `M`. Only `T` is passed as the type argument to `Parent<T>`.

**Question 2.** With `Child<String, Integer>` from `class Child<T,M> extends Parent<T>`, what is the parameterized supertype?  
**Answer:** `Parent<String>` when declared specifically as `class Child<T,M> extends Parent<T>`.

**Question 3.** Given `class Child<K,V> extends Parent<V>` and `Child<String,Long>`, what type does `Parent` have?  
**Answer:** `Parent<Long>`. The mapping is determined by `extends Parent<V>`.

**Question 4.** Does `TextTagged<Long> extends Box<String>` become `Box<Long>`?  
**Answer:** No. The parent class is fixed at `String`; `Long` is only the type argument for the subclass's metadata.

**Question 5.** Can `TaggedBox<String,Integer>` be assigned to `Box<String>`?  
**Answer:** Yes, due to inheritance; however, it cannot automatically be assigned to `Box<Object>`.

**Question 6.** If `Box<T>` has constructor `Box(T value)` and no no-arg constructor, what should the subclass constructor do?  
**Answer:** Call `super(value)` or use appropriate constructor delegation to initialize the parent part.

**Question 7.** Is `class Measured<N,UNIT> extends NumericBox<N>` valid if `NumericBox<N extends Number>`?  
**Answer:** No. You need the constraint `N extends Number` on the subclass or to pass a type argument that already satisfies the bound.

**Question 8.** Can a class simultaneously `extends Box<T>` and `implements Identifiable<ID>`?  
**Answer:** Yes. A class has only one superclass, but can implement generic interfaces with independent type arguments.

**Question 9.** Which type scopes does `<U> TaggedBox<U,M> mapValue(...)` belong to?  
**Answer:** `U` belongs to the method, while `T` and `M` belong to the class. The result can carry a new value type `U` and preserve metadata of type `M`.

**Question 10.** Is `List<TaggedBox<String,Integer>>` a subtype of `List<Box<String>>`?  
**Answer:** No. If only reading, consider `List<? extends Box<String>>`.

**Question 11.** Why can't `instanceof TaggedBox<String,Integer>` be used to verify both type arguments?  
**Answer:** Because of type erasure; checking that specific parameterized type is invalid in ordinary Java runtime code.

**Question 12.** When should you create `Annotated<T,M>` with composition instead of `TaggedBox<T,M> extends Box<T>`?  
**Answer:** When data only needs to combine two components without needing an "is-a Box" subtype contract; composition avoids unnecessary inheritance coupling.

**Question 13.** Must the new type parameter `M` have a different type from `T`?  
**Answer:** No. `TaggedBox<String,String>` is still valid; these are two independent type roles, not a requirement for two distinct classes.

**Question 14.** If a subclass has `static <V,L> TaggedBox<V,L> of(V value,L tag)`, are `V` and `L` the instance class's `T` and `M`?  
**Answer:** No; they are declared separately on the static method and are used to infer the type of the created `TaggedBox<V,L>` object.

**Question 15.** If `Box<String> parentView` points to a `TaggedBox<String,Integer>`, which version does `parentView.describe()` invoke?  
**Answer:** Since `describe()` is an overridden instance method, Java uses dynamic dispatch to `TaggedBox`'s overridden version; meanwhile, the static type `Box<String>` determines which methods can be called directly.

**Summary:** a generic subclass **is allowed to add new type parameters** without changing the number of type parameters of its parent. What matters is declaring `<...>` on the subclass, clearly mapping types in `extends Parent<...>` and `implements Interface<...>`, and preserving proper bounds, constructors, subtype relationships, and invariance limits. When the inheritance relationship genuinely makes sense, this design allows extending data and behavior while preserving compile-time type checking.