# Generics with Abstract Classes, Final Classes, and Sealed Hierarchies in Java

In Java, **generics** describe type relationships using parameters such as `T`, `E`, `K`, or `V`. Meanwhile, **`abstract`**, **`final`**, and **`sealed`** control how a class can be instantiated or inherited. They solve different problems and can therefore work together in the same hierarchy.

For example, `abstract class Repository<T>` allows defining a shared contract while disallowing direct instantiation of the abstract repository; `final class MemoryRepository<T> extends Repository<T>` completes the contract and forbids further subclassing; `sealed abstract class Result<T> permits Success, Failure` restricts the set of **direct subclasses** permitted to inherit from it.

**Key point:** `abstract`, `final`, and `sealed` do not eliminate genericity. Type information is still checked at compile time, while inheritance rules continue to follow Java's rules.

## 1. The Three Mechanisms: What Do abstract, final, and sealed Solve?

| Mechanism | Can be declared generic? | Can be `new`ed directly? | Is further inheritance allowed? |
|---|---|---|---|
| `abstract class Base<T>` | Yes | No | Yes, unless restricted by other rules |
| `final class Value<T>` | Yes | Yes, if constructor is accessible | No; all direct subtypes are prohibited |
| `sealed class Base<T> permits A, B` | Yes | Yes, if not also `abstract` and constructor is valid | Only the permitted direct subclasses |
| `abstract sealed class Base<T> permits A, B` | Yes | No | Only the permitted direct subclasses |
| `non-sealed class A<T> extends Base<T>` | Yes | Yes, if not `abstract` | Reopens inheritance for subsequent subclasses |

`non-sealed` only makes sense when a class or interface is **directly inheriting a sealed class/interface** (at a permitted position in the hierarchy). It is not a modifier to apply arbitrarily to a class that has no direct sealed supertype.

A **direct permitted subclass** of a sealed class must specify one of three directions for continuing the hierarchy: `final`, `sealed`, or `non-sealed`. `abstract` can be combined with `sealed` or `non-sealed`; `abstract` cannot be combined with `final`. A `final` class closes that branch completely. A `sealed` class restricts the next branch further. A `non-sealed` class opens that branch to subclasses not listed in the grandparent's `permits` list.

Since **Java 17**, sealed classes and sealed interfaces are a standard feature, with no preview flags required. By contrast, certain forms of *pattern matching for switch* in Java 17 were still in preview; do not confuse the two features.

## 2. Generic Abstract Classes: A Type Contract Without Abstract Instances

An `abstract` class is commonly used when we want to share common state and behavior while requiring subclasses to implement remaining operations:

```java
abstract class AbstractStore<T> {
    private final T initial;

    protected AbstractStore(T initial) {
        this.initial = initial;
    }

    public T initial() {
        return initial;
    }

    public abstract String describe(T value);
}
```

This is an **illustrative class definition**, without `main`. Key points:

- `<T>` belongs to the **class**. The `initial` field, constructor, `initial()` method, and `describe(T)` all refer to type `T` of each parameterization.
- You cannot write `new AbstractStore<String>("x")` to directly instantiate an abstract class.
- The constructor of an abstract class **still executes** when a subclass calls `super(...)`. `abstract` does not mean "has no constructor".
- The method `abstract String describe(T value)` has only a signature and no body; a concrete subclass must implement this method or inherit a valid implementation.
- A generic abstract class can contain both abstract and concrete methods as well as shared state.

A subclass fixing `T`:

```java
final class StringStore extends AbstractStore<String> {
    StringStore(String initial) {
        super(initial);
    }

    @Override
    public String describe(String value) {
        return "text=" + value;
    }
}
```

Here the compiler knows `T = String`, so the abstract signature `describe(T)` becomes `describe(String)` under source-level type relationships. `StringStore` is not generic, yet extends a **parameterized generic superclass**.

Another subclass preserving the type parameter:

```java
final class SimpleStore<E> extends AbstractStore<E> {
    SimpleStore(E initial) {
        super(initial);
    }

    @Override
    public String describe(E value) {
        return "item=" + value;
    }
}
```

`SimpleStore<Integer>` is a subtype of `AbstractStore<Integer>`. The letter `E` does not have to match `T`: the relationship lies in `extends AbstractStore<E>`. Both `StringStore` and `SimpleStore<E>` are **two illustrative designs that can sit together in an appropriate package**; they are not two branches of a sealed hierarchy.

## 3. Generic Final Classes: Locking Inheritance, Not Type Parameters

A `final class` cannot be a superclass of another class, yet **can still be generic**:

```java
final class ResultBox<T> {
    private final T value;

    ResultBox(T value) {
        this.value = value;
    }

    T get() {
        return value;
    }
}
```

You can use `ResultBox<String>`, `ResultBox<Integer>`, or `ResultBox<List<String>>`. The `final` modifier **does not restrict the kinds of type arguments**. It only prohibits anyone from declaring `class SpecialBox extends ResultBox<String>`.

Distinguish three different meanings of the keyword `final`:

1. **`final class`**: prohibits subclassing.
2. **`final` on a method**: prevents overriding that method in valid subclasses.
3. **`final` on a field**: prevents reassigning the field after proper initialization; **does not guarantee the object the field points to is deeply immutable**.

For example, `final class Data<T>` having `private final List<T> items` can still expose a mutable `ArrayList<T>` externally; callers can modify elements through the list reference. If the goal is an immutable value object, you must design the data and API appropriately alongside the `final` modifier.

In generic design, `final class` is especially suitable for value classes, concrete helpers, or a **terminal** branch of a sealed hierarchy. It does not mean "a class disallowed from polymorphism": an object of a final class can still be viewed through a **superclass** or **interface** it implements.

## 4. Generic Sealed Classes/Interfaces: Restricting the Set of Direct Subclasses

A sealed generic class can name the classes permitted to extend it directly:

```java
abstract sealed class Result<T> permits Success, Failure {
    public abstract T orElse(T fallback);
}

final class Success<T> extends Result<T> {
    private final T value;

    Success(T value) {
        this.value = value;
    }

    @Override
    public T orElse(T fallback) {
        return value;
    }
}

final class Failure<T> extends Result<T> {
    @Override
    public T orElse(T fallback) {
        return fallback;
    }
}
```

These are **three illustrative class declarations**, not a standalone runnable program. `Success<T>` and `Failure<T>` are the two **direct** subclasses of `Result<T>` and are both `final`, so this branch allows no further inheritance through those two types.

**Core rules of `sealed`:**

- The parent uses `sealed` and typically writes `permits` to list direct subclasses.
- Every permitted direct subclass must have a valid **`extends`** relationship with the sealed superclass (or **`implements`** for a sealed interface).
- Direct subclasses must explicitly be declared `final`, `sealed`, or `non-sealed`.
- In a **named module**, permitted subclasses must reside in the **same module** as the sealed parent. In an **unnamed module**, they must reside in the **same package**. This condition does not say the entire codebase must have only one package.
- The `permits` list contains **names of permitted classes/interfaces**, not parameterizations like `Success<String>`. For instance, `permits Success, Failure`, not `permits Success<T>, Failure<T>`.
- When all direct subclasses reside in the **same compilation unit**, the compiler can infer the permitted subclasses if `permits` is omitted; writing `permits` explicitly is usually clearer in documentation.
- `sealed` restricts **direct inheritance structure**, and does not by itself restrict the set of **type arguments** a generic class can accept.

Between `Result<String>` and `Result<Integer>`, Java still applies generic type checking as usual. `sealed` does not make two parameterizations subtypes of one another.

### `sealed interface` Can Also Be Generic

```java
sealed interface Response<T> permits Ok, Error {
    T orElse(T fallback);
}

record Ok<T>(T value) implements Response<T> {
    @Override
    public T orElse(T fallback) {
        return value;
    }
}

record Error<T>(String message) implements Response<T> {
    @Override
    public T orElse(T fallback) {
        return fallback;
    }
}
```

This is **a separate illustrative hierarchy** for Java 17. Records (`record`) are implicitly `final`, so they can be direct implementors of a sealed interface. `Ok<String>` and `Error<String>` are both `Response<String>`, whereas `Error<Integer>` is `Response<Integer>`. A record cannot `extends` another class because it already inherits from `java.lang.Record`, but it can `implements` a generic sealed interface.

The two branches `Ok<T>` and `Error<T>` should reside in the same package/module as `Response<T>` per sealed rules; the example is written in the same compilation unit for readability. This is a design example of a **sum type for success/failure cases**, not a mandatory runtime exception pattern.

## 5. Three Paths of a Sealed Branch: `final`, `sealed`, `non-sealed`

A direct subclass of a sealed class must choose one of three directions:

```java
sealed abstract class Node<T> permits Leaf, Branch, OpenNode {
    protected final T value;

    Node(T value) {
        this.value = value;
    }
}

final class Leaf extends Node<String> {
    Leaf(String value) {
        super(value);
    }
}

sealed class Branch<T> extends Node<T> permits FinalBranch {
    Branch(T value) {
        super(value);
    }
}

final class FinalBranch extends Branch<Integer> {
    FinalBranch(Integer value) {
        super(value);
    }
}

non-sealed class OpenNode<T> extends Node<T> {
    OpenNode(T value) {
        super(value);
    }
}

final class CustomOpenNode extends OpenNode<Long> {
    CustomOpenNode(Long value) {
        super(value);
    }
}
```

This is **an illustrative Java 17 class diagram**. Relationships of the branches:

- `Leaf` is `final`: terminates the `Node<String>` branch.
- `Branch<T>` is `sealed`: it opens one more classification level while permitting only `FinalBranch` to extend it directly; `FinalBranch` uses `T = Integer`.
- `OpenNode<T>` is `non-sealed`: from here, subtypes do not have to be listed by `Node<T>` in `permits`. `CustomOpenNode` is valid when writing `extends OpenNode<Long>`.
- `final class CustomOpenNode` is **not** a direct subclass of `Node`, so it does not need to appear in `Node`'s `permits Leaf, Branch, OpenNode`.
- `sealed` and `non-sealed` do not alter generic relationships: `OpenNode<Long>` is a subtype of `Node<Long>`, not implicitly a subtype of `Node<Object>`.

Closedness of a hierarchy must be understood accurately: if there is a `non-sealed` branch, **the set of all indirect subclasses is no longer closed**. `permits` only closes the set of **direct** subclasses of that sealed parent. Therefore, when designing an API that needs to know every possible subtype to handle each branch, you must weigh the impact of `non-sealed`.

## 6. Complete Java 17 Example: Generic, Abstract, Final, and Sealed Together

The program below illustrates a single generic hierarchy. The root `Item<T>` is both `abstract` and `sealed`. It has three direct permitted subclasses: `TextItem` closes its branch, `NumberItem<N>` reopens its branch, and `FlagItem` stays sealed for two flag kinds.

Save all code as **`SealedGenericHierarchyDemo.java`**:

```java
import java.util.List;

public class SealedGenericHierarchyDemo {

    static abstract sealed class Item<T>
            permits TextItem, NumberItem, FlagItem {

        private final T value;

        protected Item(T value) {
            this.value = value;
        }

        public final T value() {
            return value;
        }

        public abstract String kind();

        public String describe() {
            return kind() + ":" + value;
        }
    }

    static final class TextItem extends Item<String> {
        TextItem(String text) {
            super(text);
        }

        @Override
        public String kind() {
            return "text";
        }

        int length() {
            return value().length();
        }
    }

    static non-sealed class NumberItem<N extends Number>
            extends Item<N> {
        NumberItem(N number) {
            super(number);
        }

        @Override
        public String kind() {
            return "number";
        }

        double doubled() {
            return value().doubleValue() * 2;
        }
    }

    static final class IntegerItem extends NumberItem<Integer> {
        IntegerItem(Integer number) {
            super(number);
        }

        @Override
        public String kind() {
            return "integer";
        }
    }

    static abstract sealed class FlagItem
            extends Item<Boolean> permits OnFlag, OffFlag {

        protected FlagItem(Boolean value) {
            super(value);
        }

        @Override
        public String kind() {
            return "flag";
        }
    }

    static final class OnFlag extends FlagItem {
        OnFlag() {
            super(true);
        }
    }

    static final class OffFlag extends FlagItem {
        OffFlag() {
            super(false);
        }
    }

    static <T> T unwrap(Item<T> item) {
        return item.value();
    }

    static void printAll(List<? extends Item<?>> items) {
        for (Item<?> item : items) {
            System.out.println("item: " + item.describe());
        }
    }

    public static void main(String[] args) {
        TextItem text = new TextItem("Java");
        IntegerItem concreteNumber = new IntegerItem(21);
        Item<String> textView = text;
        Item<Integer> numberView = concreteNumber;
        Item<Boolean> flagView = new OnFlag();

        System.out.println("text value: " + unwrap(textView));
        System.out.println("text length: " + text.length());
        System.out.println("twice: " + concreteNumber.doubled());
        System.out.println("flag value: " + unwrap(flagView));
        System.out.println("dispatch: " + numberView.describe());

        NumberItem<Double> fractional = new NumberItem<>(2.5);
        System.out.println("open branch: " + fractional.describe());
        System.out.println("off branch: " + new OffFlag().describe());

        List<Item<?>> items = List.of(
                textView, numberView, flagView);
        printAll(items);
    }
}
```

Run with **JDK 17 or higher** in the directory containing the file:

```bash
javac SealedGenericHierarchyDemo.java
java SealedGenericHierarchyDemo
```

**Expected stdout:**

```text
text value: Java
text length: 4
twice: 42.0
flag value: true
dispatch: integer:21
open branch: number:2.5
off branch: flag:false
item: text:Java
item: integer:21
item: flag:true
```

### Explaining Each Relationship

**Generic abstract sealed root:** `Item<T>` declares `T` for the entire class. It has a `protected Item(T value)` constructor, a method returning `T`, an abstract method `kind()`, and a concrete method `describe()`. You cannot do `new Item<String>("x")` because the class is abstract. Any class outside the `permits` list cannot directly `extends Item<...>`.

**Fixed-type final branch:** `TextItem extends Item<String>`. The inherited `value()` method returns `String`, so `text.length()` can call `value().length()` without casting. The `final` modifier forbids any class from further `extends TextItem`.

**Non-sealed branch still generic:** `NumberItem<N extends Number> extends Item<N>` preserves type parameter `N` and sets bound `Number`. Because it is `non-sealed`, `IntegerItem extends NumberItem<Integer>` is allowed without appearing in `Item<T>`'s `permits`. It is an **indirect subclass** of the root, going through the direct subclass `NumberItem`.

**Second-level sealed branch:** `FlagItem extends Item<Boolean> permits OnFlag, OffFlag` fixes `T = Boolean` and restricts direct subclasses to `OnFlag` and `OffFlag`. `FlagItem` remains abstract; both subclasses are `final` and inherit `kind()` already implemented by `FlagItem`.

**Generic method reading parent type:** `<T> T unwrap(Item<T> item)` has its own method type parameter. It accepts `Item<String>` or `Item<Boolean>` without losing the return type. When calling `unwrap(textView)`, the result has type `String`; when calling `unwrap(flagView)`, it has type `Boolean`. This method type parameter is not declared by `Item`.

**Polymorphism and dispatch:** variable `numberView` has static type `Item<Integer>`, yet points to `IntegerItem`. Calling `numberView.describe()` executes `Item`'s inherited `describe()` method; inside it, calling `kind()` is a virtual call to the overridden `IntegerItem.kind()`, producing `integer:21`. Generics and dynamic dispatch complement each other; they are not the same mechanism.

**Mixed-type list:** `List<Item<?>>` can contain multiple `Item<T>` instances with different `T`s. `printAll(List<? extends Item<?>>)` only reads and prints each item, without assuming all share a concrete value type. Conversely, `List<Item<String>>` cannot be assigned directly from `List<TextItem>` due to generic collection *invariance*.

## 7. Relationship Between Sealed Hierarchies and Type Parameters

The subtype set is governed by **class names**, whereas type arguments are governed by **generics contracts**. Example:

```java
// Root:
abstract sealed class Event<T> permits TextEvent, GenericEvent { }

// Fixed branch:
final class TextEvent extends Event<String> { }

// Parameter-preserving branch:
final class GenericEvent<U> extends Event<U> { }
```

These three declarations are **a standalone example** separate from the `Item<T>` program above. `TextEvent` is a subtype of `Event<String>`; `GenericEvent<Integer>` is a subtype of `Event<Integer>`. The name `U` differs from the parent's `T`, yet the mapping `extends Event<U>` is what defines the type relationship.

You cannot write:

```java
// sealed class Event<T> permits TextEvent<String> { }
// Invalid: permits requires class names, not parameterized types.
```

Similarly, a sealed parent cannot "permit `Event<String>` while forbidding `Event<Integer>`" merely by listing type arguments in `permits`. If the data domain needs fixed-type branches, design concrete subclasses like `TextEvent extends Event<String>`; if types need to be restricted by bounds, use generic bounds; if runtime data conditions are needed, validate in constructors/factories.

Java still preserves **invariance**: even though `String` is a subtype of `Object`, `Event<String>` is not automatically a subtype of `Event<Object>`. You can use `Event<?>` when only observing an arbitrary event or `Event<? extends CharSequence>` when reading values satisfying a broader contract.

## 8. Sealed and Pattern Matching: Handling by Set of Branches

When a hierarchy is closed, the compiler has more information about possible subclasses. This helps pattern matching, branch analysis, and API maintenance tools.

For example, a `Result<T>` branch has only `Success` and `Failure`: readers can design handling for those two cases. However, distinguish clearly:

- **Java 17:** sealed classes/interfaces are a standard feature. Pattern matching for `instanceof` is already available in Java 17. However, **pattern matching for `switch`** in Java 17 is a preview feature, so do not blindly copy a `switch` example based on sealed patterns and expect `javac File.java` to run without preview flags.
- **Java 21 and later:** pattern matching for `switch` is standardized; certain forms of handling sealed hierarchies can check exhaustiveness at compile time, depending on selector type and patterns. Exact syntax/conditions must match the JDK version in use.
- **Presence of `non-sealed`:** even if the root lists a `non-sealed` direct subclass, unknown subtypes may exist beneath that branch; do not infer that the entire set of concrete classes is finite solely from `permits`.

In Java 17, one way to inspect branches without preview features is `instanceof` patterns with **reifiable** types:

```java
static String category(Object obj) {
    if (obj instanceof SealedGenericHierarchyDemo.TextItem) {
        return "text";
    }
    if (obj instanceof SealedGenericHierarchyDemo.NumberItem<?>) {
        return "numeric";
    }
    if (obj instanceof SealedGenericHierarchyDemo.FlagItem) {
        return "flag";
    }
    return "other";
}
```

This is an **illustrative method** that can be placed in a class with access to `SealedGenericHierarchyDemo`'s nested types (e.g., inside that class itself). `NumberItem<?>` has an unbounded wildcard, so checking `instanceof` with that type is valid. Do not use `obj instanceof NumberItem<Integer>` to check a specific type argument; that form is not reifiable under Java erasure.

## 9. Abstract + Sealed, Final + Generic, and Non-Sealed Can Work Together

Do not treat these three modifiers as mutually exclusive choices across an entire hierarchy:

- **`abstract sealed` root**: cannot be instantiated directly and restricts direct subclasses.
- **`final` branch**: a concrete type completing the contract and stopping inheritance.
- **`sealed` branch**: continues constraining its own sub-branches; can also be `abstract`.
- **`non-sealed` branch**: reopens the ability to create subtypes. Can be concrete or abstract; reopening works according to the direct sealed supertype rule.
- **Generics at each level**: root `Base<T>`, branch `Branch<U> extends Base<U>`, branch `Fixed extends Base<String>`, or type-adding branch `Tagged<T, M> extends Base<T>` are all checked by the compiler independently of sealed modifiers.

A class **cannot be both `final` and `abstract`** because `abstract` requires the class to be subclassable for implementation, whereas `final` forbids subclassing. A class also cannot combine `final` with `sealed` or `non-sealed` as if describing three inheritance modes at once; a direct permitted subclass must choose one valid mode.

A `protected` constructor of a sealed abstract class allows permitted subclasses to initialize the parent part with `super(...)`, yet does not grant `extends` permission to a class excluded from `permits`. Access modifiers and sealed restrictions are two separate layers of checking.

## 10. Common Mistakes and How to Fix Them

**Mistake 1 — Thinking `final` forbids generics.** `final class Box<T>` is valid. `final` forbids class inheritance, not passing `Box<String>` or `Box<Integer>`.

**Mistake 2 — Directly calling `new` on an abstract generic class.** `new AbstractStore<String>(...)` is invalid; create a concrete subclass matching the constructor and implementing abstract methods, or provide a factory returning an appropriate subclass.

**Mistake 3 — Forgetting to implement an abstract generic method.** If the parent has `abstract T read()`, a concrete subclass must implement the method with a return type satisfying the type relationship after substituting type arguments; merely declaring `class Child extends Parent<String>` does not implement the method automatically.

**Mistake 4 — Using `permits` with type arguments.** `permits Good<String>` is wrong. The `permits` list names **declared subtypes**, such as `permits Good, Bad`.

**Mistake 5 — Direct permitted subclass omitting `final`, `sealed`, or `non-sealed`.** For a class directly extending a sealed parent, `class Good extends Parent` alone is insufficient; you must specify the appropriate modifier such as `final class Good...`, `sealed class Good...`, or `non-sealed class Good...`.

**Mistake 6 — Assuming any class anywhere can use `non-sealed`.** `non-sealed` has specific contextual rules and requires a direct sealed supertype. Do not add it to an ordinary class just to say that the class is "extensible".

**Mistake 7 — Placing a direct permitted subclass in the wrong module/package.** With named modules, they must be in the same module; with unnamed modules, in the same package. Simply declaring `permits` does not bypass location constraints or access checks.

**Mistake 8 — Thinking every indirect subclass must be in the root's `permits`.** If the root permits `non-sealed NumberItem`, class `IntegerItem extends NumberItem<Integer>` is not a direct subclass of the root and does not need to be named in the root's `permits`.

**Mistake 9 — Thinking `sealed` closes all subclasses below a `non-sealed` branch.** Once a valid branch is marked `non-sealed`, it can be extended later; classification designs must account for this possibility.

**Mistake 10 — Confusing class inheritance with generic type covariance.** `TextItem extends Item<String>` does not imply `Item<String> extends Item<Object>`. Use wildcards like `Item<?>` or `Item<? extends CharSequence>` when wanting to accept multiple parameterizations.

**Mistake 11 — Calling a subclass method through a superclass-typed variable.** `Item<String> item = new TextItem("x");` does not allow calling `item.length()` directly if `Item<T>` does not declare `length()`. The static type determines which methods can be called; runtime dispatch only selects the overridden implementation of an existing method.

**Mistake 12 — Thinking type arguments are preserved at runtime because of `sealed`.** `sealed` controls inheritance relationships; ordinary Java generics are still erased. Do not check `instanceof Item<String>`; use `Item<?>` where appropriate or pass a runtime type token if the problem requires it.

**Mistake 13 — Depending on Java 17 preview `switch`.** If you use pattern `switch` from newer documentation, verify your JDK and preview flags before running; complete examples in this article avoid requiring preview features.

**Mistake 14 — Using `final` as a promise of deep immutability.** A `final` generic class with `final` fields can still hold a mutable object. For safe value objects, consider defensive copying, read-only APIs, and explicitly defining whether state can change.

**Mistake 15 — Opening too many `non-sealed` branches when wanting finite sum-type data.** If exhaustive handling of a closed set of states is required, use genuine `final`/`sealed` branches; only use `non-sealed` when there is a real reason to give others an extension point.

## 11. When to Choose Which Design?

| Scenario | Suggested design | Reason |
|---|---|---|
| Sharing state and requiring subclasses to implement operations | `abstract class Base<T>` | Provides constructors, fields, shared methods, and abstract methods |
| Generic value object with no intent to extend via inheritance | `final class Value<T>` or `record Value<T>(T x)` | Reduces extension surface; records automatically provide components with record semantics |
| Only a fixed set of direct variants is allowed | `sealed interface Result<T> permits ...` | Clearly shapes the hierarchy of cases |
| Needing an abstract root, some concrete branches, and some further-classified branches | `abstract sealed class Node<T> permits ...` | Combines contract, state, and branch restriction |
| Wanting one branch to be extensible by third parties | Direct `non-sealed` subclass | Reopens inheritance at that branch |
| Adding data without a true "is-a" relationship | Composition such as `record Tagged<T, M>(T data, M metadata)` | Avoids unnecessary inheritance coupling |

Choose `sealed` when the closedness/openness of the hierarchy is an **intentional contract**, not merely to limit class count. If code outside the module/package needs to add variants itself, a completely closed sealed hierarchy may not fit. On the other hand, when modeling well-defined states such as success/failure or fixed node kinds, `sealed` makes the contract easier to read and control.

Do not use `sealed` as a substitute for runtime data validation: `sealed` does not ensure a `Result<String>` holds a valid string, does not guard against `null`, and does not make objects thread-safe on its own.

## 12. Self-Check Exercises with Answers

**1.** Can `abstract class Store<T>` have constructors and concrete methods?  
**Answer:** Yes. `abstract` prevents direct instantiation of the class and allows abstract methods, while constructors and concrete methods are completely valid.

**2.** Can `final class Box<T>` accept `String` and `Integer` as type arguments?  
**Answer:** Yes, `final` does not prohibit parameterizing `T`.

**3.** Does `sealed abstract class Result<T> permits Ok, Error` allow `class Other extends Result<String>` in the same package?  
**Answer:** No, if `Other` is not included in the set of direct permitted subclasses. Being in the same package only satisfies one location condition, not a substitute for `permits`.

**4.** Which modifiers must a direct permitted subclass use?  
**Answer:** One of `final`, `sealed`, or `non-sealed` matching how the hierarchy continues.

**5.** Can `non-sealed class NumberItem<N extends Number> extends Item<N>` have `final class IntegerItem extends NumberItem<Integer>`?  
**Answer:** Yes. `IntegerItem` is a subclass of the non-sealed branch and does not need to appear in the root `Item`'s `permits`.

**6.** Given `TextItem extends Item<String>`, is `Item<Object> o = new TextItem("x");` valid?  
**Answer:** No. `TextItem` is a subtype of `Item<String>`, not `Item<Object>` due to generic invariance.

**7.** Can you write `permits Ok<String>, Error<Integer>` to close a generic hierarchy by type arguments?  
**Answer:** No. `permits` lists direct subclasses by declaration name and does not accept parameterized types.

**8.** Why is `Item<Boolean> b = new OnFlag()` valid?  
**Answer:** `OnFlag extends FlagItem` and `FlagItem extends Item<Boolean>`; transitive inheritance preserves the exact type argument `Boolean`.

**9.** Does `final` on a class mean a field of type `List<T>` inside it cannot be modified?  
**Answer:** No. `final class` forbids subclassing; it does not automatically make elements and inner objects immutable.

**10.** In Java 17, does a sealed class require `--enable-preview`?  
**Answer:** No. Sealed classes/interfaces are standard; only certain pattern `switch` syntaxes in Java 17 were preview.

**11.** Can the generic method `<T> T unwrap(Item<T> x)` work across multiple branches of a sealed hierarchy?  
**Answer:** Yes, provided each branch has an appropriate `Item<T>` supertype; `T` is inferred or specified per call.

**12.** When does a `non-sealed` branch reduce the ability to finitely enumerate all subtypes?  
**Answer:** When that branch allows further indirect subtypes not listed in the root `permits`, so the entire tree is no longer closed.

**13.** Can a `record R<T>(T value)` implement a sealed interface?  
**Answer:** Yes, if it is a valid direct permitted implementor. Records are implicitly `final` and cannot extend arbitrary classes.

**14.** Should you combine `abstract` + `final` to mean "cannot be instantiated and cannot be inherited"?  
**Answer:** No. Those two modifiers conflict on a class; for a utility class, use a normal/`final` class with a `private` constructor when needed, while an `abstract` class is meant to be a superclass.

**15.** Does `sealed` eliminate type erasure?  
**Answer:** No. The two mechanisms are independent: `sealed` restricts direct subtypes, while generic erasure affects type argument information at runtime.

**16.** To allow a permitted subclass of a sealed parent to restrict one more level, which modifier should be chosen?  
**Answer:** `sealed` with that branch's own permitted subclasses; branches at the next level again choose `final`, `sealed`, or `non-sealed`.

**17.** In the example, why does `numberView.describe()` print `integer:21` even though `describe()` is defined on the root?  
**Answer:** `describe()` calls `kind()`, and `kind()` is overridden in `IntegerItem`. Runtime dynamic dispatch selects that `kind()` implementation.

**18.** If you want a pair of data with generic types without needing an is-a hierarchy, what should you consider?  
**Answer:** Composition, such as `record Pair<A,B>(A first, B second)`, rather than creating a subclass just to hold extra fields.

In summary, **generics govern type relationships**, whereas **`abstract`/`final`/`sealed` govern class instantiation and extension contracts**. With Java 17, you can use a generic abstract sealed root, branch with `final`/`sealed`/`non-sealed`, preserve type arguments safely across inheritance, and add behavior per subtype. A design is sound when the subtype set is controlled according to real requirements, without sacrificing clarity just to stack multiple modifiers.