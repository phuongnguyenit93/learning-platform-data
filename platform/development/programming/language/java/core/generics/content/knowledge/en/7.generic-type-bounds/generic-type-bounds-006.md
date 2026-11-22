# Intersection Types and Member Access in Java Generics

In Java Generics, a type parameter does not have to be constrained by only a single class or interface. You can require the actual type to **simultaneously satisfy multiple bounds** using the `&` operator. These constraints form an **intersection type**: a value must conform to all components of the intersection.

Example:

```java
interface Named {
    String name();
}

interface Versioned {
    int version();
}

static <T extends Named & Versioned> String describe(T item) {
    return item.name() + "@" + item.version();
}
```

The two interfaces and method above are **illustrative code**, and must be placed inside a suitable class before compiling. The signature `<T extends Named & Versioned>` guarantees that **any accepted actual type `T`** can be used through both the `Named` and `Versioned` contracts. Therefore, inside the method body, the compiler allows calling both `item.name()` and `item.version()` without casting.

**Core idea:** for a type variable `T extends A & B`, **the set of members accessible at compile time is determined by the valid members of bounds `A` and `B`**, along with Java's access control, inheritance, and method resolution rules. Not every method of the runtime class is automatically visible.

## 1. What Does an Intersection Type Mean?

In Java's type theory, the intersection `A & B` expresses the requirement that a value must simultaneously conform to `A` **and** `B`. It does not create a new Java interface named `A&B`; it is a **combined type description** allowed in specific syntactic contexts.

Imagine:

- `Named` is an interface granting the `name()` capability.
- `Versioned` is an interface granting the `version()` capability.
- `Document` is a class implementing both `Named` and `Versioned`.

When `Document implements Named, Versioned`, a `Document` object can be used where `Named` is required, where `Versioned` is required, or where a type parameter must satisfy **both** interfaces simultaneously.

```java
class Document implements Named, Versioned {
    @Override
    public String name() {
        return "Java";
    }

    @Override
    public int version() {
        return 17;
    }
}
```

This is an **illustrative class definition** based on the two previously declared interfaces. `Document` satisfies `<T extends Named & Versioned>`; a class that only `implements Named` does not satisfy it, even though it has a `name()` method.

Distinguish from ordinary inheritance:

| Declaration | Compile-time constraint | Callable on type variable `T` |
|---|---|---|
| `<T>` | No explicit bound; implicit upper bound is `Object` | Accessible members of `Object` |
| `<T extends Named>` | `T` conforms to `Named` | `name()` and valid members from the bound |
| `<T extends Named & Versioned>` | `T` conforms to both | `name()` **and** `version()` |
| `<T extends Asset & Named & Versioned>` | `T` is a subtype of `Asset` and conforms to both interfaces | Accessible members of `Asset`, `Named`, and `Versioned` |

**Note:** `extends` in a generic bound declaration is used for both **class bounds** and **interface bounds**, even though Java uses the `implements` keyword in `class Document implements Named`.

## 2. Recognizing Intersection Syntax for Type Analysis

A type parameter uses `&` to combine multiple upper bounds:

```java
<T extends Named & Versioned>
<T extends Asset & Named & Versioned>
```

These are **declaration patterns** placed in a suitable class or generic method, not standalone Java statements. If `Asset` is a class, it must come first; the remaining bounds are interfaces. `T` must satisfy **all** bounds. A comma `,` separates **different type parameters**, whereas `&` represents the intersection of requirements on **one** parameter.

In this article, more important than syntax is: at each use site of `T`, which members from `Named`, `Versioned`, and `Asset` does the compiler allow calling? For instance, `<T extends Named & Versioned>` alone **does not allow calling** an `id()` specific to `Asset`, even if the actual object might be a subclass of `Asset`. You must explicitly specify the bound providing that method and respect access modifiers.

Bounds must be compatible; interfaces with conflicting signatures/return types or incompatible instantiations of the same generic interface do not form a valid intersection. When considering runtime, distinguish **intersection bounds in declarations** from **intersection casts** with corresponding type checks.

## 3. Why Does an Intersection Bound Change Member Access Rights?

Consider two methods taking the same kind of runtime object but having different type contracts:

```java
static <T extends Named> String oneCapability(T item) {
    return item.name();
}

static <T extends Named & Versioned> String twoCapabilities(T item) {
    return item.name() + "@" + item.version();
}
```

The two methods are **illustrative snippets** that must be placed in a class with `Named` and `Versioned` in scope.

In `oneCapability`, the compiler only has the guarantee `T extends Named`. It permits calling `name()`, but has no basis to allow `item.version()`, **even if the caller later passes a `Document` that has both methods**.

In `twoCapabilities`, the compiler knows both bounds simultaneously and therefore accepts both calls. This is the difference between **static type** and **runtime class**:

- The runtime class of the object may be `Document`, `Deployment`, or any class implementing both interfaces.
- **The static type `T` together with the bounds in the signature** determines which methods can be validly called inside the generic method body.
- Runtime dynamic dispatch still selects the object's proper implementation when the method is invoked.

The following code **does not compile**, even though actual calls might only pass `Document`:

```java
// static <T extends Named> int invalid(T item) {
//     return item.version(); // No version() in bound Named.
// }
```

A good solution is to add `& Versioned` when the API **genuinely needs** both capabilities, or accept a single interface that already describes the full contract. Do not use arbitrary casts inside a generic method to "patch" an insufficiently strong bound: casting shifts errors from compile time to runtime if the object does not meet the condition.

## 4. Class Bound First, Interface Bounds Following

When you need both behavior from a base class and multiple interfaces:

```java
class Asset {
    private final String id;

    Asset(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }
}

interface Named {
    String name();
}

interface Versioned {
    int version();
}

static <T extends Asset & Named & Versioned> String describe(T item) {
    return item.id() + ":" + item.name() + "@" + item.version();
}
```

This is an **illustrative group of declarations**: the interfaces, class, and method must be placed in valid locations (the method inside a class) before compiling into a program. The bound provides three capabilities:

- `Asset` grants access to `id()`.
- `Named` grants access to `name()`.
- `Versioned` grants access to `version()`.

An actual type `Document extends Asset implements Named, Versioned` satisfies all of them. However, `Document` is not necessarily the only class satisfying that constraint.

**You cannot reorder to `<T extends Named & Asset & Versioned>`** if `Asset` is a class; the class-first ordering is a Java syntax/type rule, not merely a formatting convention. If all bounds are interfaces, Java allows placing an interface first, yet **order can still matter for erasure and binary compatibility** (see Section 9).

Access inside the generic method body is also governed by Java access control: `private`, package-private, `protected`, and `public` are not bypassed by an intersection type. For example, a `private` field in `Asset` does not become accessible from another class merely because `T extends Asset`. Use valid access APIs like `id()`.

## 5. Standalone Runnable Java 17 Example

Save the entire program below into the file **`IntersectionBoundsDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class IntersectionBoundsDemo {

    interface Named {
        String name();
    }

    interface Versioned {
        int version();
    }

    static class Asset {
        private final String id;

        Asset(String id) {
            this.id = id;
        }

        public String id() {
            return id;
        }
    }

    static final class Document extends Asset
            implements Named, Versioned {
        private final String title;
        private final int revision;

        Document(String id, String title, int revision) {
            super(id);
            this.title = title;
            this.revision = revision;
        }

        @Override
        public String name() {
            return title;
        }

        @Override
        public int version() {
            return revision;
        }
    }

    static final class Deployment implements Named, Versioned {
        private final String environment;
        private final int release;

        Deployment(String environment, int release) {
            this.environment = environment;
            this.release = release;
        }

        @Override
        public String name() {
            return environment;
        }

        @Override
        public int version() {
            return release;
        }
    }

    static final class NamedOnly implements Named {
        private final String text;

        NamedOnly(String text) {
            this.text = text;
        }

        @Override
        public String name() {
            return text;
        }
    }

    static <T extends Named & Versioned> String label(T item) {
        return item.name() + "#" + item.version();
    }

    static <T extends Asset & Named & Versioned>
            String describe(T item) {
        return item.id() + ":" + item.name() + "@"
                + item.version();
    }

    static <T extends Named & Versioned>
            List<String> labels(List<T> items) {
        List<String> result = new ArrayList<>();
        for (T item : items) {
            result.add(label(item));
        }
        return List.copyOf(result);
    }

    static <T extends Number & Comparable<T>> T larger(T a, T b) {
        return a.compareTo(b) >= 0 ? a : b;
    }

    public static void main(String[] args) {
        Document first = new Document("doc-7", "Generics", 3);
        Document second = new Document("doc-8", "Streams", 2);
        Deployment release = new Deployment("prod", 5);

        System.out.println("full: " + describe(first));
        System.out.println("interfaces: " + label(release));

        Named namedView = first;
        System.out.println("named view: " + namedView.name());
        System.out.println("cast version: "
                + ((Named & Versioned) namedView).version());

        System.out.println("bulk: " + labels(List.of(first, second)));
        System.out.println("larger: " + larger(3, 7));

        Object oneCapability = new NamedOnly("solo");
        System.out.println("has both: "
                + (oneCapability instanceof Named
                && oneCapability instanceof Versioned));

        try {
            ((Named & Versioned) oneCapability).name();
            System.out.println("unexpected");
        } catch (ClassCastException exception) {
            System.out.println("cast failed: ClassCastException");
        }
    }
}
```

Run in the directory containing the file, with JDK 17 or newer:

```bash
javac IntersectionBoundsDemo.java
java IntersectionBoundsDemo
```

**Stdout output:**

```text
full: doc-7:Generics@3
interfaces: prod#5
named view: Generics
cast version: 3
bulk: [Generics#3, Streams#2]
larger: 7
has both: false
cast failed: ClassCastException
```

### Analyzing the mechanism from the output

1. **`describe(first)` requires three bounds:** `Document` is a subtype of `Asset` and also implements `Named` and `Versioned`. The body of `describe` calls `id()`, `name()`, and `version()` validly; result is `doc-7:Generics@3`.
2. **`label(release)` requires only two interfaces:** `Deployment` does not extend `Asset`, yet is still valid for `<T extends Named & Versioned>`. It returns `prod#5`. Calling `describe(release)` would be rejected by the compiler because `Deployment` does not satisfy the `Asset` class bound.
3. **`Named namedView = first;` loses static access to `version()`:** through this variable only the `Named` contract is visible. `namedView.name()` is valid; `namedView.version()` will not compile even though the actual object is a `Document`.
4. **`((Named & Versioned) namedView)` is an intersection cast:** it requires the runtime object to conform to **both** interfaces; `first` satisfies the condition and allows calling `version()`, printing `3`.
5. **`labels(List.of(first, second))` keeps `T = Document`:** the list of `Document`s satisfies both bounds; the loop in the generic method can call both `name()` and `version()`, returning the string list `[Generics#3, Streams#2]`.
6. **`larger(3, 7)` demonstrates an intersection of a class and a generic interface:** `T` is inferred as `Integer` via boxing; `Integer` is a subtype of `Number` and implements `Comparable<Integer>`. `compareTo` picks `7`.
7. **`NamedOnly` satisfies only one bound:** the expression `instanceof Named && instanceof Versioned` returns `false`. The intersection cast in the final example fails to pass both runtime checks and throws `ClassCastException`, which is caught to print a deterministic line.

**Distinguish clearly:** type bounds in generic methods check **before running**; an intersection cast `(A & B) object` performs an **explicit type conversion with runtime checking**. Both mechanisms relate to the idea of intersecting contracts, but do not replace each other.

## 6. Intersection Bounds in Generic Classes and Interfaces

Not only methods—generic classes and generic interfaces can also declare multiple bounds:

```java
interface Named {
    String name();
}

interface Versioned {
    int version();
}

final class Registry<T extends Named & Versioned> {
    private final T item;

    Registry(T item) {
        this.item = item;
    }

    String describe() {
        return item.name() + "@" + item.version();
    }

    T get() {
        return item;
    }
}
```

This is a **separate illustrative definition**; do not duplicate identically named interfaces into the same scope as earlier declarations. With `Registry<Document>`, assuming `Document` implements both interfaces:

- When constructing `Registry<Document>`, type argument `Document` must satisfy both bounds.
- Inside `Registry`, the field `item` has static type `T`, so both `name()` and `version()` can be called.
- The `get()` method returns **exact `T`**, preserving the object's concrete type for the caller.
- For a class implementing only `Named`, `Registry<NamedOnly>` will not compile.

A generic interface can also declare bounds itself:

```java
interface Inspector<T extends Named & Versioned> {
    String inspect(T item);
}
```

This is an illustrative interface; a class implementing `Inspector<Document>` will use `T = Document` in its signature. If a generic subclass extends or implements a bounded type, the subclass must pass a type argument satisfying all constraints of the supertype; for example, `class AdvancedRegistry<U extends Named & Versioned> extends Registry<U>` is valid with respect to bounds only if `Registry` is designed for inheritance (not `final`) and has the necessary constructor/methods.

## 7. Intersection Casts and Runtime Checking

Java allows certain cast expressions to use multiple reference bounds:

```java
Object object = new Document("doc-1", "Intro", 1);
Named named = (Named & Versioned) object;
String title = named.name();
```

These are **illustrative lines**, assuming `Document`, `Named`, and `Versioned` exist as in the standalone runnable example and are placed inside a method. The cast ensures the runtime object satisfies both `Named` and `Versioned`, yet the variable `named` **is declared as `Named`**, so afterward only `Named`'s methods exist on the variable's static type.

If you want to call both right inside one expression, use the cast as the receiver's type:

```java
int version = ((Named & Versioned) object).version();
```

Notice the parentheses: `(Named & Versioned)` is the type part of the cast; `((Named & Versioned) object)` is the cast object expression. If the object does not implement both interfaces, the cast can throw `ClassCastException` at runtime.

Before casting, you can check separately:

```java
if (object instanceof Named named
        && object instanceof Versioned versioned) {
    System.out.println(named.name() + "@" + versioned.version());
}
```

Pattern `instanceof` in the example above is available in Java 17. It establishes two pattern variables with two separate static types; it does not create a variable declared using `Named & Versioned` syntax as a normal type name.

**Distinguish syntactic positions:**

| Position | Allowed? | Notes |
|---|---|---|
| Type parameter declaration `<T extends A & B>` | Yes | Primary way to use intersection bounds in generic APIs |
| Cast `(A & B) object` | Yes if bounds/cast are compatible | Runtime check; may throw `ClassCastException` |
| Variable declaration `A & B value` | No | Not ordinary direct variable declaration syntax |
| Type argument `List<A & B>` | No | Type arguments cannot be written directly as such an intersection |
| Wildcard `List<? extends A & B>` | No | Wildcard bounds in Java do not use this multi-component intersection syntax |
| Type check `object instanceof A & B` | No | Check both types separately with `&&` or appropriate patterns |

Even though you cannot write `List<A & B>`, you can write a generic method taking `List<T>` with `<T extends A & B>`, such as `labels(List<T>)` in the example. The name `T` is how you express the type-safe relationship between the input list and the members allowed to be accessed.

## 8. Conflicting Interfaces: Not Every Intersection Is Valid

Two bounds must be compatible with respect to inherited methods. Consider two incompatible interfaces:

```java
interface A {
    String read();
}

interface B {
    Integer read();
}

// static <T extends A & B> T invalid(T value) { return value; }
```

This is an **error example**, in which two interfaces have methods with the same name and parameter list, but return types that cannot both be satisfied by a valid implementation. You cannot just add `&` and automatically "combine" two return types. Java applies method/return-type conflict rules when checking bounds or declaring an implementing class; designs should avoid mutually exclusive contracts.

Another kind of conflict involves **default methods**:

```java
interface Left {
    default String tag() {
        return "L";
    }
}

interface Right {
    default String tag() {
        return "R";
    }
}

// class Ambiguous implements Left, Right { }
// Invalid without resolving the two conflicting default tag() methods.

final class Resolved implements Left, Right {
    @Override
    public String tag() {
        return Left.super.tag() + Right.super.tag();
    }
}
```

This is an **illustrative group of declarations**, not part of `IntersectionBoundsDemo.java`. `Resolved.tag()` returns `"LR"` via explicit override. In bound design, do not treat `<T extends Left & Right>` as a way to automatically resolve conflicting default methods; examine the validity of the combined interfaces and provide a conflict-free contract.

One case to distinguish: two interfaces declaring **a compatible abstract method** can be implemented by **one** method on a class. Therefore, "two interfaces have a method with the same name" **is not automatically an error**; errors occur when the contracts conflict under Java's rules, such as incompatible return types or ambiguous default implementations.

Marker interfaces like `java.io.Serializable` can participate in bounds without adding any business methods to call. For example, `<T extends Named & java.io.Serializable>` requires both `name()` and the serialization marker, without adding a `serialize()` method on `T`.

## 9. Type Erasure: The First Bound Affects Compiled Representation

Ordinary Java generics use **type erasure**. For an unbounded type parameter, erasure is typically `Object`; for a type parameter with multiple bounds, **the erasure of the type variable is determined by the first bound**.

Example:

```java
static <T extends Asset & Named & Versioned> String describe(T item) {
    return item.id() + item.name() + item.version();
}
```

Here `T` has erasure `Asset`, because `Asset` is the first bound. This **does not remove the right to call** `name()` and `version()` during compilation: the compiler already knows the intersection bounds, validates the calls, and emits appropriate bytecode, which may include interface casts to invoke methods.

If there are only interface bounds:

```java
static <T extends Named & Versioned> String label(T item) {
    return item.name() + item.version();
}
```

the erasure of `T` is `Named` (the first bound). The compiler still enforces that `T` satisfies `Versioned` at compile time.

**API design consequence:** the order of **interface bounds**, even when preserving the same constraint semantics at the source level, can change erasure and the signature represented in bytecode. Reordering bounds in the public API of an already-compiled library can affect binary compatibility. Do not reorder bounds casually just to make code look nicer; evaluate compatibility impacts when releasing libraries.

Erasure also explains why:

- You cannot directly check `obj instanceof T` with an ordinary type variable `T`.
- You cannot instantiate `new T()` from a bound alone.
- You cannot use `T.class` to query the full actual passed type.
- You cannot overload solely by changing type parameters/bounds if **erased signatures collide**.
- An intersection bound **does not** generate a special runtime class combining `Named` and `Versioned`.

If runtime type information is needed, an API can require `Class<T>` or a suitable type token mechanism, though adding a runtime token **does not replace** full type-relationship checking in the generic signature.

## 10. Intersection Types and Type Inference

Beyond bound declarations and intersection casts, Java's type system also uses intersection types during type inference in certain contexts (such as computing the **least upper bound** for multiple input types). This helps express shared capabilities across branches or arguments.

As an illustration of the idea: if two independent classes both implement `Named` and `Versioned`, the compiler may find a common type combining those interfaces when analyzing a suitable expression. However, the **exact inferred type** depends on context, Java's rules, and other supertypes; you should not assume every `var x = condition ? a : b` has the exact static type `Named & Versioned`.

To make a public method's contract clear, explicit bound declarations are usually easier to understand:

```java
static <T extends Named & Versioned> String label(T item) {
    return item.name() + "@" + item.version();
}
```

Java can infer `T` when calling `label(document)` or `label(deployment)`, provided the argument type satisfies the bounds. This also lets the compiler report an error early if `NamedOnly` (having only `Named`) is passed.

Notably, type parameters in a generic method can relate to one another:

```java
static <T extends Named & Versioned, R> R map(
        T source,
        java.util.function.Function<? super T, ? extends R> mapper) {
    return mapper.apply(source);
}
```

This is an **illustrative method** that must be placed in a class with both interfaces in scope. `T` requires `source` to satisfy both interfaces, while `R` describes the mapper's output type and does not itself have to satisfy `T`'s bounds. The comma between `T` and `R` **differs** from the `&` joining multiple bounds on the same `T`.

If you need to compute over a list of heterogeneous values, you must choose among **a homogeneous element type with explicit bounds**, **a reading wildcard**, and **a shared wrapper/interface**. Broad inference at one call site does not make arbitrary writes into a collection valid.

## 11. Member Access: Important Limitations

### 11.1. Only members guaranteed by the bounds are accessible

`<T extends Named & Versioned>` does not allow directly calling `item.id()`, even if the actual object might be a `Document extends Asset`. If the method needs `id()`, add the `Asset` bound first or add `id()` to an appropriate interface.

### 11.2. Bounds do not exclude `null`

`T extends Named & Versioned` guarantees the **static type**, and does not mean `item` is guaranteed non-null. Passing `null` can be accepted if there is no separate nullness constraint; then `item.name()` can throw `NullPointerException`. When `null` must be forbidden, use `Objects.requireNonNull(item)` or an appropriate nullness check/contract.

### 11.3. Java access control still applies

A class bound having a `private` field does not mean every generic method in another class can access that field. Type bounds check **type capabilities**, whereas access modifiers check **access rights by code location**.

### 11.4. Multiple bounds do not create multiple class inheritance

`<T extends Base & I1 & I2>` allows at most **one class bound** in the first position, followed by interface bounds. It does not allow `T` to inherit from two independent classes simultaneously. If two forms of state reuse are needed, consider composition and interfaces.

### 11.5. You cannot turn `List` elements into an intersection type by casting the list

`List<Named>` and `List<Versioned>` remain invariant; you cannot cast `List<Named>` to `List<Named & Versioned>` because intersection type argument syntax is invalid. If you need an API reading a collection of elements satisfying both bounds, use `<T extends Named & Versioned> void work(List<T> items)` with a list that already has a compatible element type.

### 11.6. Adding an interface bound can make an API stricter

Changing `<T extends Named>` to `<T extends Named & Versioned>` makes **some previously valid calls invalid** (types that only implement `Named`). That is an API contract change, not a free improvement. Weigh the impact on client code and binary compatibility.

## 12. Common Mistakes and How to Fix Them

**Mistake 1 — Using a comma instead of `&`.** `<T extends Named, Versioned>` does not express two bounds for `T`; it does not properly declare the type parameter list. Write `<T extends Named & Versioned>`.

**Mistake 2 — Repeating the `extends` keyword.** `<T extends Named extends Versioned>` is invalid syntax. Use only one `extends`, joined with `&`.

**Mistake 3 — Placing a class bound after an interface bound.** `<T extends Named & Asset>` is invalid if `Asset` is a class. Write `<T extends Asset & Named>`.

**Mistake 4 — Thinking only the first bound's methods can be called.** With `<T extends Asset & Named & Versioned>`, the method can use accessible members from **all three** bounds; erasure to `Asset` does not prevent the compiler from checking `name()` and `version()`.

**Mistake 5 — Thinking a runtime object having enough capabilities lets a generic method call them.** In `<T extends Named>`, `item.version()` still fails to compile if the bound does not guarantee `version()`. Upgrade the contract to `Named & Versioned` instead of relying on objects that happen to be passed at runtime.

**Mistake 6 — Thinking `<T extends A & B>` requires `A` and `B` to be two classes.** Java allows multiple interface bounds; if there is a class, it must be first and unique.

**Mistake 7 — Using `List<A & B>`.** This is not valid type argument syntax. Design a generic method taking `List<T>` with `T extends A & B`.

**Mistake 8 — Thinking `? extends A & B` works as a wildcard bound.** Java does not allow direct wildcard intersection bounds like that. Declare a named type parameter to express the relationship you need to preserve.

**Mistake 9 — Using `(A & B)` cast instead of static type bounds without checking.** A cast can throw `ClassCastException`; generic bounds enforce compatible argument types at compile time and should usually be preferred in API design.

**Mistake 10 — Misunderstanding `extends Serializable` as adding methods.** `Serializable` is a marker interface; it restricts accepted types but adds no `serialize()` member to call.

**Mistake 11 — Forgetting to check conflicts between interfaces.** Two bounds having methods with the same signature and incompatible return types, or multiple unresolvable default methods, can make an intersection invalid. Fix the contracts or separate the requirements.

**Mistake 12 — Confusing type erasure with losing type checking.** Erasure is a runtime/bytecode strategy; the compiler still verifies every bound and member access at the source level before emitting bytecode.

**Mistake 13 — Reordering interface bounds arbitrarily in a released library.** The first bound determines the erasure of the type variable, which can affect binary API compatibility. Review the contract carefully before modifying.

**Mistake 14 — Forgetting nullness and accessibility.** Multiple bounds do not prevent `NullPointerException` and do not bypass `private`/`protected`/package visibility. Design appropriate validation and access levels yourself.

**Mistake 15 — Writing `instanceof A & B`.** Java has no such type-check syntax in `instanceof` expressions. Use `obj instanceof A && obj instanceof B` or separate pattern `instanceof` checks for each interface.

## 13. API Design Guidelines Using Intersection Bounds

Consider multiple bounds when **one parameter genuinely needs multiple independent capabilities simultaneously**. For example, a processor needs objects that are both named and versioned, without creating a new interface solely to group those two capabilities:

```java
static <T extends Named & Versioned> String keyOf(T value) {
    return value.name() + ":" + value.version();
}
```

This design lets classes without a shared business superclass — such as `Document` and `Deployment` — participate as long as they satisfy the contract.

However, if the `Named + Versioned` capability pair appears repeatedly in the domain, you can consider a combined interface:

```java
interface NamedVersioned extends Named, Versioned { }

static String keyOf(NamedVersioned value) {
    return value.name() + ":" + value.version();
}
```

These are **two illustrative declarations**. A combined interface creates a clear domain name, yet classes that only `implements Named, Versioned` **are not automatically considered implementations of `NamedVersioned`** unless they declare or inherit that interface. This is a practical distinction:

- **Intersection bound `T extends Named & Versioned`** accepts any type satisfying both interfaces, without requiring a new subinterface declared on the class.
- **Named interface `NamedVersioned`** requires classes to declare the appropriate `implements NamedVersioned` relationship; in return, the API gets an easy-to-reference contract name.

Use a named type parameter when you need to preserve the type relationship in the result, such as `static <T extends Named & Versioned> T verified(T item)` returning the exact `T`. If only the behavior is needed and the concrete type does not need to be preserved, a domain interface may be simpler.

## 14. Self-Check Questions with Answers

**1.** What does `<T extends Named & Versioned>` require?  
**Answer:** Type argument `T` must conform to both interfaces; inside the method, valid members from both `Named` and `Versioned` can be called.

**2.** Why don't you write `<T extends Named extends Versioned>`?  
**Answer:** Java uses only one `extends` in a bound declaration and joins subsequent bounds with `&`.

**3.** If `Asset` is a class, what is the correct order among `Asset`, `Named`, and `Versioned`?  
**Answer:** `<T extends Asset & Named & Versioned>`; the class bound must come first.

**4.** With `<T extends Named>`, can you call `item.version()` if the caller passes a `Document` implementing both interfaces?  
**Answer:** No. The signature only guarantees `Named`; the compiler does not inspect runtime objects at call sites to unlock extra members.

**5.** With `<T extends Asset & Named & Versioned>`, which methods can be called from the three illustrative contracts?  
**Answer:** `id()`, `name()`, and `version()`, provided all those methods are accessible at that code location.

**6.** Can `NamedOnly` be passed to a `<T extends Named & Versioned>` method?  
**Answer:** No, because it lacks `Versioned`.

**7.** Does the intersection cast `((Named & Versioned) obj)` guarantee success for every `Named` object?  
**Answer:** No; the object must also satisfy `Versioned`. Otherwise, the cast can throw `ClassCastException`.

**8.** Can a variable `Named named = (Named & Versioned) obj;` directly call `named.version()`?  
**Answer:** No, because the variable's static type is `Named`; to access `version()`, use an API preserving both capabilities or cast in an expression when safe.

**9.** Is `List<Named & Versioned>` valid?  
**Answer:** No. Use a named type parameter `<T extends Named & Versioned>` with `List<T>`.

**10.** Does `<T extends Number & Comparable<T>>` accept `Integer`?  
**Answer:** Yes, because `Integer` is a `Number` and implements `Comparable<Integer>`.

**11.** What does the first bound affect when compiling generics?  
**Answer:** The erasure of the type variable; for example, in `T extends Asset & Named`, the erasure is `Asset`.

**12.** Can you use two class bounds like `<T extends Asset & AnotherClass>`?  
**Answer:** No. Java does not support multiple class inheritance; after a class bound, additional bounds must be interfaces.

**13.** Does `Serializable` in a bound automatically grant business methods on variable `T`?  
**Answer:** No; it is a marker interface with no business methods of its own.

**14.** Does `T extends Named & Versioned` exclude `null`?  
**Answer:** No; separate validation/nullness rules are needed if the API does not accept `null`.

**15.** Does a type variable with intersection bounds cause Java to keep all type arguments intact at runtime?  
**Answer:** No. Ordinary Java generics still use type erasure, even though the compiler checks every bound during compilation.

**16.** Should you use a new `NamedVersioned` interface or an intersection bound?  
**Answer:** An intersection bound is convenient when you want to accept any type that independently implements both interfaces; a new interface fits when you want a clear shared contract name and classes actively declare it.

**17.** Is `instanceof Named & Versioned` valid?  
**Answer:** No. Use `obj instanceof Named && obj instanceof Versioned` or two appropriate pattern `instanceof` checks.

**18.** Why can reordering interface bounds in a library be risky even when source code looks equivalent?  
**Answer:** The first bound determines erasure and can alter bytecode signatures, affecting binary compatibility.

**Summary:** An intersection type expresses a **combined contract**: `T` must satisfy multiple bounds simultaneously. From there, the compiler permits reading/calling members allowed by **all type and access rules**. The proper syntax is typically `<T extends ClassBound & Interface1 & Interface2>` or `<T extends Interface1 & Interface2>`. Distinguish bound declarations (compile-time type safety) from intersection casts (runtime checks), remember that the first bound affects erasure, and use intersection types when multiple capabilities genuinely belong in a single API signature.