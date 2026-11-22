# Self-Referential Type Bounds and F-Bounded Polymorphism in Java Generics

## 1. The Problem: Constraining a Type by Itself

With an ordinary generic declaration such as `Box<T>`, Java knows nothing about `T`'s behavior beyond the behaviors of `Object`. Type bounds (`bounded type parameter`) let you express the requirement that a passed-in type must satisfy a specific inheritance relationship or implement a given interface.

There are relationships where the type parameter itself appears **inside its own bound**:

```java
interface Self<S extends Self<S>> {
    S copy();
}
```

This is a **self-referential type bound** or a form of **F-bounded polymorphism**. Read it as: "`S` must be a type that implements `Self<S>`". Here, `Self` acts as a type structure applied back onto `S`.

An example implementation:

```java
final class Document implements Self<Document> {
    @Override
    public Document copy() {
        return new Document();
    }
}
```

Thanks to that constraint, the `copy()` operation is known to return `Document` when working with `Self<Document>`, rather than returning only `Object` or an overly general interface.

**Key point:** An F-bound expresses a *compile-time type relationship*. It does not create a recursive loop at runtime, nor does it automatically guarantee that the parameter `S` is the very class being written.

## 2. Reading the Syntax and Type-Checking Mechanism Correctly

A typical form:

```java
abstract class Base<S extends Base<S>> {
    abstract S next();
}

final class Concrete extends Base<Concrete> {
    @Override
    Concrete next() {
        return this;
    }
}
```

Breakdown:

- `S` is the type parameter of `Base`.
- `extends Base<S>` is the **upper bound** of `S`. The `extends` keyword in generics works for both classes and interfaces.
- `Base<S>` on the right is a *parameterized type*; `S` is used as a type argument right inside `S`'s own bound declaration.
- `Concrete extends Base<Concrete>` is valid because `Concrete` is indeed a subtype of `Base<Concrete>`.
- The `next()` method in `Base<Concrete>` has a return type seen by the compiler as `Concrete`, so calling code can continue using `Concrete`'s own API without manual casting.

You can visualize the relationship as:

```text
S satisfies condition: S <: Base<S>
                           │
Concrete <: Base<Concrete>
                           │
Base<Concrete>.next() returns Concrete
```

The notation `<:` means "is a subtype of". The compiler checks this relationship using the generic type system; there is no need to generate infinitely many classes `Base<Base<Base<...>>>`.

### Two Declarations to Distinguish

```java
interface Comparable<T> {
    int compareTo(T other);
}
```

On its own, `Comparable<T>` does **not** declare a recursive bound: `T` is unconstrained. An F-bound appears when another declaration specifies:

```java
static <T extends Comparable<T>> T choose(T first, T second) {
    return first.compareTo(second) >= 0 ? first : second;
}
```

In that case, `T` must be capable of comparing itself with an object of type `T`. By contrast, writing `<T extends Comparable<?>>` only says that `T` is comparable to *some type*, which is not enough to prove that `first.compareTo(second)` is valid.

## 3. Application 1: Generic Algorithms Requiring Comparison

A method that finds the maximum element needs to be certain that `compareTo` accepts elements from the same group being processed. In the Java library, the more broadly applicable version of the bound is `Comparable<? super T>`:

```java
import java.util.List;

public class BoundMaxDemo {
    static <T extends Comparable<? super T>> T max(List<T> values) {
        if (values.isEmpty()) {
            throw new IllegalArgumentException("Danh sách không được rỗng");
        }

        T best = values.get(0);
        for (int i = 1; i < values.size(); i++) {
            T current = values.get(i);
            if (current.compareTo(best) > 0) {
                best = current;
            }
        }
        return best;
    }

    public static void main(String[] args) {
        System.out.println(max(List.of(3, 8, 5)));
        System.out.println(max(List.of("An", "Binh", "Chi")));
    }
}
```

Compile and run with Java 17 or later:

```bash
javac BoundMaxDemo.java
java BoundMaxDemo
```

Output:

```text
8
Chi
```

Why the method is type-safe:

1. `values` holds elements of type `T`; `best` and `current` both have type `T`.
2. The bound confirms that `T` implements `Comparable<X>` for some type `X` that is `T` or a **supertype of `T`**.
3. Therefore `current.compareTo(best)` is valid: the argument `best` has type `T`, which can be passed into a parameter expecting `X`.
4. The return value retains type `T`, without being downgraded to `Object`.

`? super T` is a **lower-bounded wildcard**; it makes the bound more flexible than `Comparable<T>`. For example, `Student` extends `Person`, while `Person` implements `Comparable<Person>`. `Student` can participate in an algorithm bounded by `Comparable<? super Student>` thanks to the comparison mechanism inherited from `Person`; a `Comparable<Student>` bound would be too strict in that case.

The program above assumes that elements are non-`null`, which is guaranteed by the `List.of(...)` examples. For input from other sources, a clear `null`-handling policy must be defined. The empty-list case is explicitly guarded so `get(0)` is not accessed improperly.

**Note:** This algorithm example is an application of recursive bounds via `Comparable<? super T>`; it does not require every chosen class to write `implements Comparable<Itself>` directly. This is why the `super` wildcard is useful in API design.

## 4. Application 2: Preserving Concrete Types in Fluent APIs

In a builder with inheritance, a setter defined on the parent class but declared to return the parent class itself can lose the subclass's specific methods when chaining calls. A self-referential bound lets you declare **the builder type to return** as a named parameter:

```java
abstract class Builder<B extends Builder<B>> {
    private String name;

    B name(String value) {
        name = value;
        return self();
    }

    protected abstract B self();
}

final class UserBuilder extends Builder<UserBuilder> {
    UserBuilder age(int years) { return this; }

    @Override
    protected UserBuilder self() { return this; }
}
```

When calling `new UserBuilder().name("Mai").age(20)`, the compiler knows `name(...)` returns `UserBuilder`, so it can find the `age(...)` method. A generic class cannot directly write `return this` with type `B`: `this` is only known to be `Builder<B>`. An abstract `self()` shifts the responsibility of returning the right type to the leaf class, avoiding an unchecked cast `(B)this` in the base class.

This is a **snippet illustrating the complete class declarations**, not an example with `main`. With multi-level builders, intermediate classes also have to forward the `B` parameter unchanged to the parent class, and the leaf builder overrides `build()` with the right product type. The dedicated lesson on builders with inheritance practices multi-level chaining, per-call return types, validation, and mutable state. What to retain here is: **an F-bound links fluent return types, without automatically guaranteeing that every subclass chooses the right self-type**.

## 5. Application 3: `Enum<E extends Enum<E>>` in Standard Java

An important example of an F-bound is `java.lang.Enum<E extends Enum<E>>`: given `enum Priority { LOW, MEDIUM, HIGH }`, Java establishes the corresponding type relationship `Priority extends Enum<Priority>`. Because of this, `Priority.LOW.compareTo(Priority.HIGH)` is valid, while direct comparison with a constant of another enum is rejected by generic type checking.

A reusable method for any enum that still preserves the exact `E`:

```java
static <E extends Enum<E>> E lastDeclared(Class<E> enumType) {
    E[] values = enumType.getEnumConstants();
    if (values == null || values.length == 0) {
        throw new IllegalArgumentException("Không có enum constants");
    }
    return values[values.length - 1];
}
```

When calling `lastDeclared(Priority.class)`, the result has type `Priority`; with the constants declared above, the result is `HIGH`. `Class<E>` carries the enum type information needed to retrieve the constants; `E.values()` is invalid because `values()` is a method generated by the compiler specifically for *each* concrete enum. You cannot manually write a regular class that `extends Enum`.

`EnumSet<E>` and `EnumMap<E,V>` also rely on recursive bounds, though there are many additional cases to distinguish: `Enum.valueOf`, declaration order, constant-specific class bodies, `getClass()` differing from `getDeclaringClass()`, and null policies. Those enum-specific behaviors are covered in detail in a dedicated lesson; this section illustrates **how F-bounds appear in a real JDK API**.

## 6. Static Guarantees and the Limits of the “Self Type”

Consider `abstract class Base<S extends Base<S>>`. The compiler proves that **`S` is a subtype of `Base<S>`**, not that `S` always equals the class declaring `extends Base<S>`.

```java
abstract class Base<S extends Base<S>> {
    abstract S next();
}

final class Right extends Base<Right> {
    @Override Right next() { return this; }
}

final class Wrong extends Base<Right> {
    @Override Right next() { return new Right(); }
}
```

Both `Right` and `Wrong` are valid: when declaring `Wrong extends Base<Right>`, the type `Right` still satisfies the condition `Right extends Base<Right>`. The result of `new Wrong().next()` has type `Right` and is a `Right` object, **not** `Wrong`; the F-bound does not promise that `next()` returns `this`.

If the base class tries `return (S)this`, the cast is **unchecked** and can lead to a `ClassCastException` when the caller expects a concrete type after erasure. The practical approach is to factor out an abstract `self()`, constrain the hierarchy with `final`/`sealed` where appropriate, and review each subclass's generic type argument — though each measure still has limits. The topic **limits of self-referential types** presents counterexamples with mismatched subclass types, grandchild classes, cast insertion in bytecode, and the actual scope of protection of sealed hierarchies.

## 7. F-Bounds and Type Erasure

Java generics are checked primarily at compile time. In bytecode, type parameters undergo **type erasure** according to their bounds:

- If `T` is unbounded, its erasure is usually `Object`.
- With `<S extends Base<S>>`, the erasure of `S` is `Base`.
- With `<T extends Comparable<? super T>>`, the erasure of `T` is `Comparable`.

Therefore, an F-bound does not generate a new copy of bytecode for each `Concrete`. The compiler may insert casts at use sites and generate *bridge methods* to preserve polymorphic compatibility when an overriding method has a specialized return type. That explains why generic checking is very useful at compile time yet cannot verify an unchecked cast from `this` to a type parameter after erasure.

Practical consequences:

- You cannot write `new S()` simply because `S extends Base<S>`; the bound does not provide a constructor that can be invoked via a type parameter.
- You cannot directly use `S.class`; concrete type information is not available as a class literal of a type parameter.
- You should not use the raw type `Base`, as it bypasses most generic checks and can lead to unchecked warnings.
- Do not infer that F-bounds turn Java into a system with *dependent types* or exact runtime type checking of the receiver.

If you need to create an instance of `S`, accept a `Supplier<S>`, `Class<S>`, or an appropriate factory from outside; each approach has its own contract and limitations.

## 8. Comparison with Similar Mechanisms

| Declaration | Meaning | When to Use |
|---|---|---|
| `<T>` | Any valid reference type | No need to invoke specialized behavior of `T` |
| `<T extends Number>` | `T` is a subtype of `Number` | General handling of numeric types |
| `<T extends Comparable<T>>` | `T` is comparable to `T` | Symmetric relationship on the exact type under consideration |
| `<T extends Comparable<? super T>>` | `T` is comparable to `T` or a supertype of `T` | More flexible comparison algorithms, usually suitable for general APIs |
| `<S extends Base<S>>` | `S` is a subtype of `Base<S>` | Preserving concrete types when inheriting fluent APIs or recursive type operations |
| `<? extends Base<?>>` | An unknown type that is a subtype of `Base<?>` | Reading objects without needing to retain the identity of a specific type parameter |

**Note the difference between a type parameter and a wildcard.** `S` is a named type variable: the same `S` can be used consistently across inputs, outputs, and bounds. `?` is an unknown type in a generic argument position; it does not by itself create a shared name usable across multiple positions in the same signature. When an API needs to express "accept two arguments of the same `S` and return `S`", a type parameter usually communicates the intent more clearly.

F-bounds also do not make Java generics covariant: `List<Cat>` is still not a subtype of `List<Animal>` merely because `Cat extends Animal`. Generic invariance rules and `extends`/`super` wildcards are a separate issue from recursive bounds.

### Intersection Bounds

Java can combine an F-bound with additional interfaces:

```java
static <T extends Comparable<T> & java.io.Serializable>
T preferred(T a, T b) {
    return a.compareTo(b) >= 0 ? a : b;
}
```

This is a **method illustration snippet** and must be placed inside a class to run. A type parameter can have multiple intersection bounds, with at most one class bound, and the class bound (if present) must come first. The remaining bounds are typically interfaces.

## 9. API Design Rules and Common Pitfalls

**1. Start from the behavior that needs to be preserved.** An F-bound makes sense when there is a real benefit, such as `copy()` returning a concrete type, a builder inheriting a fluent API without losing subclass methods, or an algorithm needing `compareTo` with a clear type relationship. Do not add self-reference just to make a signature look "stronger" when no contract requires it.

**2. Choose the right bound for comparisons.** For utilities accepting types that inherit a parent class's `Comparable` implementation, you should generally consider `Comparable<? super T>` instead of `Comparable<T>`. The wildcard part does not weaken the requirement on the argument type `compareTo` can accept; it allows that argument type to be a supertype of `T`.

**3. Avoid misbinding the type parameter.** `class Wrong extends Base<Right>` can be valid Java even though it breaks the "self type" convention. In hierarchies you control, mark leaf classes `final` when extension is unnecessary and review each subclass's `extends Base<...>` clause.

**4. Distinguish static types from runtime objects.** Return type `S` states that the result conforms to the `S` type contract; it does not automatically mean the result is `this`, that a new object is created, or that every subclass is bound properly.

**5. Minimize raw types and unchecked casts.** Raw `Base` discards type parameters; an `(S) this` cast relies solely on the author's promise if the compiler cannot verify it. An unchecked warning is a signal that an invariant needs proof, not automatic evidence that code is wrong or right.

**6. Keep complexity proportional.** In systems with many inheritance levels, signatures like `Child<C extends Child<C, ...>>` easily become hard to read and make type error messages complex. Consider preferring composition, separate builders per type, interfaces separating capabilities, or covariant return types when they meet the requirements more simply.

**7. Do not confuse generic bounds with algorithmic recursion.** An F-bound is a constraint in a type definition, not a recursive function call. There is no rule requiring self-calling methods or tree-shaped data to use it.

## 10. How to Self-Check an F-Bound Design

When encountering a new declaration, answer these questions in order:

1. **What is the type variable?** In `<S extends Base<S>>`, it is `S`.
2. **What is the validity condition?** Candidate `X` must be a subtype of `Base<X>`.
3. **Who supplies the type?** A subclass, e.g. `Concrete extends Base<Concrete>`, or a generic method call.
4. **What is the compile-time benefit?** Methods taking/returning `S` retain that exact concrete static type.
5. **Is there a self-identity loophole?** Check whether another class could use `Base<Concrete>`; enforce the convention if identity is essential.
6. **Can it be made simpler?** If fluent inheritance or self-typing is not needed, a plain interface or explicit overloads may suffice.

### Practice Exercises

**Exercise 1 — Predict the type:** Given `class CarBuilder extends BaseBuilder<CarBuilder>`, if method `name(...)` is declared to return `B`, what is the static type of the result when called on `CarBuilder`? Why can `CarBuilder`'s own methods be chained afterward? **Reference hint:** `B` is substituted with `CarBuilder`.

**Exercise 2 — Evaluate the bound:** Explain why `Student extends Person` and `Person implements Comparable<Person>` can satisfy the bound `Comparable<? super Student>` without automatically satisfying `Comparable<Student>`. **Reference hint:** generics are invariant; `Person` is a supertype of `Student`.

**Exercise 3 — Spot the mistake:** A developer writes `class A extends Base<B>` where `B extends Base<B>` and claims the Java compiler will always reject it because `A` differs from `B`. Is this claim true or false? **Answer:** false. The F-bound checks the condition on parameter `B`, not whether the inheriting class's name matches `B`.

**Exercise 4 — Choose an approach:** Creating a `withName` API for a single-class builder that will never be subclassed. Do you need `<B extends Builder<B>>`? **Hint:** usually no; returning `Builder` itself is enough.

## 11. Key Takeaways

F-bounded polymorphism uses a type parameter directly inside its own bound, typically `<S extends Base<S>>`. This technique helps Java express the relationship between a concrete type and operations that accept or return that exact concrete type. It is especially useful in `Comparable`-based algorithms, the JDK's enum system, and fluent APIs with inheritance hierarchies.

The strength of an F-bound lies in **compile-time type safety**; its important limitations are that it cannot force `S` to match the current subclass, does not replace designing a `self()` contract, and does not eliminate type erasure. Use it when this type relationship yields a clear API benefit, while checking that subclasses adhere to the chosen convention.
