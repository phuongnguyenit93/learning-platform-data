# When Recursive Bounds Make APIs Hard to Use and How to Simplify Them

## Objectives

Recursive type bounds (*F-bounded polymorphism*), commonly written `<T extends Self<T>>`, help some APIs express a relationship with an object's own concrete type. However, applying this bound across too many classes, methods, and interfaces can make an API difficult to call, difficult to extend, and awkward when handling polymorphic collections.

After this lesson, you will be able to:

- Recognize when a recursive bound genuinely protects a necessary type relationship, and when it only makes signatures harder to read.
- Distinguish between needs for **reading properties**, **transforming while returning the exact type**, **comparing**, and **building objects** in order to pick the right constraint.
- Simplify APIs using small interfaces, `Comparator<? super T>`, `Comparable<? super T>`, callbacks (`UnaryOperator<T>`), wildcards, or deliberate overloads.
- Understand the limits of "self types" in Java, avoiding raw types, uncontrolled casts, and wrong assumptions about inheritance.

## 1. What Problem Does an F-Bound Solve?

An interface may want a method to return the exact implementing type:

```java
interface SelfNamed<S extends SelfNamed<S>> {
    String label();
    S rename(String newName);
}

record Task(String label) implements SelfNamed<Task> {
    @Override
    public Task rename(String newName) {
        return new Task(newName);
    }
}
```

This is an illustrative example; the declarations can be placed top-level in the same file or nested inside a class. `Task` supplies `S = Task`; therefore `new Task("A").rename("B")` is type-checked and inferred to return `Task`.

A reusable method is often written as:

```java
static <S extends SelfNamed<S>> S renameStrong(S value, String newName) {
    return value.rename(newName);
}
```

The signature expresses two requirements: the argument must obey the `SelfNamed<S>` contract, and the result has type `S`. This is a legitimate reason to use an F-bound **if callers genuinely need that same-type relationship**.

Yet an F-bound is designed for a specialized type relationship, not as the default rule for every object-oriented API. When a task only needs a name, display order, or a caller-provided callback, a self-referential bound is usually unnecessary.

## 2. Signs That an API Has Become Hard to Use

### 2.1. Signatures Too Deep for Actual Needs

Suppose a feature only displays a list of labels, yet the API takes:

```java
// Illustrative example inside a class:
static <S extends SelfNamed<S>> void printLabels(
        java.util.List<S> items) {
    for (S item : items) {
        System.out.println(item.label());
    }
}
```

This API forces every element to share the same self-referential type `S`, even though the operation only calls `label()`. It becomes inconvenient when the UI needs to display a mix of `Task`, `Signal`, or other labeled objects. If `S` only appears here without being used for a return type or a same-type operation, the recursive bound adds no practical value.

A smaller, better-fitting contract:

```java
interface Labelled {
    String label();
}

static void printLabels(
        java.util.List<? extends Labelled> items) {
    for (Labelled item : items) {
        System.out.println(item.label());
    }
}
```

This is an illustrative declaration pattern: place the method in a class, with object types implementing `Labelled`. The new pattern accepts `List<Task>`, `List<Signal>`, or a `List<Labelled>` containing both. The wildcard `? extends Labelled` expresses that the method **reads** elements satisfying `Labelled` without needing to know the concrete subtype.

### 2.2. Callers Hold Broad Type Variables or Heterogeneous Collections

Recursive bounds easily get awkward when code at a system boundary only knows a general interface:

```java
SelfNamed<?> item = new Task("Draft");
// renameStrong(item, "Done"); // Cannot match the S extends SelfNamed<S> relationship.
System.out.println(item.label()); // Reading the property is still valid.
```

This snippet is illustrative only within the context where `SelfNamed`, `Task`, and `renameStrong` were declared above. The wildcard says an unknown type argument exists; it does **not** say the broad reference type `SelfNamed<?>` itself is a concrete `S` satisfying `S extends SelfNamed<S>`. Therefore, do not force UI layers, loggers, or serializers to recover subtype information they do not actually need.

In these situations, a more ergonomic design is separating the read capability into a non-generic interface (`Labelled`), or keeping subtype-dependent operations where the concrete type is still known.

### 2.3. F-Bounds "Leaking" Across Multiple Layers

For example, a repository layer only needs to read labels, yet the repository interface defines `Repository<T extends SelfNamed<T>>`, then the service uses `Service<T extends SelfNamed<T>>`, and the controller continues with `Controller<T extends SelfNamed<T>>`. All three layers end up carrying the bound even though only one internal operation needs a self type. Every new class brings long generic declarations, hard-to-read type inference errors, and extra coupling to the `SelfNamed` mechanism.

Ask: **Does this layer actually call `rename(...)` with the same S, compare two S instances, or return S?** If not, have that layer depend on the smallest appropriate interface, or just parameterize `<T>` if pass-through typing is needed.

### 2.4. Inheritance, Subclasses, and Non-Uniform Comparison Types

An overly strict bound like `<T extends Comparable<T>>` can exclude valid subtypes that only implement `Comparable<Base>` via a parent class. That is not necessarily a reason to abandon generics; sometimes it only requires a more accurate bound: `<T extends Comparable<? super T>>`. Section 5 illustrates this clearly.

## 3. Choose the Design Based on What the API Actually Needs to Do

| Need | Ergonomic signature | Is an F-bound needed? |
| --- | --- | --- |
| Read common labels/info | `void print(List<? extends Labelled> items)` | No; use a small capability interface. |
| Preserve the passed-in type across a caller-supplied transformation | `<T> T transform(T value, UnaryOperator<T> op)` | No; the callback is responsible for producing `T`. |
| Compare by rules decided by the caller | `<T> T greater(T a, T b, Comparator<? super T> cmp)` | No; ordering lives in the comparator. |
| Compare by the object's natural ordering | `<T extends Comparable<? super T>> T max(...)` | Needs a bound on `Comparable`, though `? super T` should usually be allowed. |
| Call a self-typed method and preserve the exact result type | `<S extends SelfNamed<S>> S rename(S value, ...)` | An F-bound may be needed. |
| Implement a generic policy keyed by enum type | `<E extends Enum<E>> ...` | Yes; matches Java library bounds. |
| A concrete builder with no builder hierarchy | `final class UserBuilder { UserBuilder name(...); }` | No; a concrete return type is enough. |

Do not replace every F-bound with `Object`, raw types, or casts: those throw away type checking. A good simplification replaces an **overly strong contract** with one that still expresses all the behavior actually required.

## 4. Complete Java 17 Example: Multiple Strategies in One Program

**File `SimplerBoundsDemo.java`:**

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.function.UnaryOperator;

public class SimplerBoundsDemo {
    interface Labelled {
        String label();
    }

    interface SelfNamed<S extends SelfNamed<S>> extends Labelled {
        S rename(String newName);
    }

    record Task(String label, int urgency) implements SelfNamed<Task> {
        @Override
        public Task rename(String newName) {
            return new Task(newName, urgency);
        }
    }

    record Signal(String label, int level) implements SelfNamed<Signal> {
        @Override
        public Signal rename(String newName) {
            return new Signal(newName, level);
        }
    }

    static <S extends SelfNamed<S>> S strongRename(S item, String name) {
        return item.rename(name);
    }

    static List<String> labels(List<? extends Labelled> values) {
        List<String> result = new ArrayList<>();
        for (Labelled value : values) {
            result.add(value.label());
        }
        return result;
    }

    static <T> T transform(T value, UnaryOperator<T> operation) {
        return operation.apply(value);
    }

    static <T> T greater(T left, T right, Comparator<? super T> order) {
        return order.compare(left, right) >= 0 ? left : right;
    }

    static class Document implements Comparable<Document> {
        final int rank;

        Document(int rank) {
            this.rank = rank;
        }

        @Override
        public int compareTo(Document other) {
            return Integer.compare(rank, other.rank);
        }
    }

    static final class SignedDocument extends Document {
        SignedDocument(int rank) {
            super(rank);
        }
    }

    static <T extends Comparable<? super T>> T maxNatural(
            List<? extends T> values) {
        return Collections.max(values);
    }

    public static void main(String[] args) {
        Task draft = new Task("Draft", 3);
        Signal signal = new Signal("Disk", 8);

        System.out.println(strongRename(draft, "Released").label());
        System.out.println(labels(List.of(draft, signal)));

        Task updated = transform(draft, t -> t.rename("Reviewed"));
        System.out.println(updated.label());

        Task chosen = greater(
                draft,
                new Task("Urgent", 7),
                Comparator.comparingInt(Task::urgency));
        System.out.println(chosen.label());

        SignedDocument result = maxNatural(
                List.of(new SignedDocument(2), new SignedDocument(5)));
        System.out.println(result.rank);
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 SimplerBoundsDemo.java
java SimplerBoundsDemo
```

**Stdout (verified by running):**

```text
Released
[Draft, Disk]
Reviewed
Urgent
5
```

Analysis:

1. `strongRename` still uses an F-bound because it has to call `rename` and keep the result under the exact type `Task`.
2. `labels` drops the self-referential bound. It reads a list containing both `Task` and `Signal`, since both implement `Labelled`. The result is `[Draft, Disk]`.
3. `transform` does not know which methods the object has; `UnaryOperator<T>` is passed from a place that knows `Task`, so the result is still inferred as `Task`. A transformation may return a different reference and carries no immutability guarantee unless the type/callback itself ensures it.
4. `greater` uses `Comparator<? super T>` so callers choose the ranking criterion. For `Task`, we use `urgency`; there is no need to force `Task` to declare `Comparable<Task>`.
5. `SignedDocument` inherits `Comparable<Document>` through `Document`. The `Comparable<? super T>` bound enables comparing `SignedDocument` instances based on the relationship with parent class `Document`. The maximum value has `rank = 5`.

Note in the code: `List.of(...)` creates an unmodifiable list; `labels` only reads. Do not infer from `List<? extends Labelled>` that any `Labelled` can be added to the list: the actual element type may be narrower.

## 5. Relaxing Natural-Ordering Bounds Without Giving Up Type Safety

If `Document implements Comparable<Document>` and `SignedDocument extends Document`, then `SignedDocument` inherits `Comparable<Document>`; it is **not** automatically `Comparable<SignedDocument>`. A `<T extends Comparable<T>>` bound can be too tight when an algorithm needs to return `SignedDocument` directly.

The standard signature should usually be:

```java
static <T extends Comparable<? super T>> T maxNatural(
        List<? extends T> values) {
    return java.util.Collections.max(values);
}
```

`Comparable<? super T>` allows the comparison to accept a supertype of `T`, while `List<? extends T>` allows reading compatible elements. This is a **controlled relaxation**, not dropping the F-bound or using raw `Comparable`. The runnable example in section 4 demonstrated calling it with `List<SignedDocument>` while preserving the `SignedDocument` result.

If multiple different orderings are needed, there is no natural order, or the criterion belongs to the caller's context, pick `Comparator<? super T>` and **remove the Comparable bound from T altogether**. The design decision here is knowing when to *relax the bound* and when to *move behavior into a strategy*, rather than re-analyzing comparison inheritance details.

## 6. Separating Read Capabilities from Self-Typed Capabilities

An interface containing both display data and operations returning the subtype often forces read-only layers to carry a self-referential bound. Split it into two roles:

```java
interface Labelled {
    String label();
}

interface SelfNamed<S extends SelfNamed<S>> extends Labelled {
    S rename(String newName);
}
```

A display API only references `Labelled`:

```java
static String display(Labelled value) {
    return value.label();
}
```

An API performing operations that return a new subtype requires `SelfNamed<S>`:

```java
static <S extends SelfNamed<S>> S renameAndReturn(
        S value, String newName) {
    return value.rename(newName);
}
```

The illustrative methods above are placed inside a class and the interfaces are declared in an appropriate shared scope.

The advantage is that complex type relationships stay strictly where they are needed. A component that only receives `Labelled` does not need to understand F-bounds, generic capture, or the concrete type of `rename`. If `Signal` is added later, the display logic continues working with no signature changes.

If renaming is actually an **application-specific task** rather than an intrinsic behavior of the object, you can remove `SelfNamed` from the domain model and pass a `UnaryOperator<T>` from the responsible layer. This keeps a model from having to implement an interface merely to serve an external utility.

## 7. Using Callbacks to Preserve T Without Self-Constraining

The `transform` method example in the program:

```java
static <T> T transform(T value, java.util.function.UnaryOperator<T> operation) {
    return operation.apply(value);
}
```

The caller decides the transformation:

```java
Task task = new Task("Draft", 3);
Task reviewed = transform(task, value -> value.rename("Reviewed"));
```

This call resides in `SimplerBoundsDemo`, where `Task` and `transform` are already defined. The compiler infers `T = Task`. The `transform` function does not force every data type to implement a generic interface.

Other callback shapes can be used matching the data direction:

- `Function<? super T, ? extends R>` when reading a T to produce an R, such as mapping a domain object to a DTO.
- `Consumer<? super T>` when only processing T with no return value.
- `Predicate<? super T>` when filtering/testing T.
- `Comparator<? super T>` when comparing two T instances.
- `UnaryOperator<T>` when transforming and returning the same type T.

Callbacks do not always replace F-bounds. If the core contract genuinely requires every implementation to provide `rename`, having the compiler enforce that contract is the value of an interface. Callbacks fit when behavior can be supplied externally or varies by context.

## 8. Do Not Treat an F-Bound as a Guarantee That `S` Is the Receiver

`interface SelfNamed<S extends SelfNamed<S>>` only requires `S` to satisfy `SelfNamed<S>`. It does not forbid another class from implementing `SelfNamed<Task>` if `Task` is a valid argument.

```java
// With Task(String label) implements SelfNamed<Task> from section 1:
record Alias(String label) implements SelfNamed<Task> {
    @Override public Task rename(String value) {
        return new Task(value);
    }
}
```

`Alias` can return `Task` per its signature, yet it does not become `SelfNamed<Alias>`; therefore `Alias` cannot be used as `S=Alias` in `renameStrong(S,...)`. Stronger contracts require careful class/constructor design, `final`/`sealed` classes, or controlled factories and dedicated tests. Likewise, `return (S)this` in a generic base class is an unchecked cast, not automatically safe.

When the goal is simply reading a `label()` or transforming via a caller-supplied callback, the `Labelled` interface or `UnaryOperator<T>` in earlier sections is simpler without promising an unproven "self type". Mismatched self-types, grandchild classes inheriting a fixed `S`, and erasure-related exceptions are demonstrated thoroughly in the lesson on F-bound limitations.

## 9. Builders: A Frequent Case of F-Bound Overuse

In frameworks with many inheriting builders, F-bounds can preserve the builder type across chained calls. Yet for a single concrete builder, all you may need is:

```java
final class UserBuilder {
    private String name;

    UserBuilder name(String value) {
        this.name = value;
        return this;
    }

    String buildName() {
        return name;
    }
}
```

This snippet illustrates a standalone class declaration. With `new UserBuilder().name("An").buildName()`, the concrete return type already suffices for chaining without creating `Builder<B extends Builder<B>>`.

Add F-bounds to a builder hierarchy only when there is a **real builder-inheritance requirement**, such as parent-class methods needing to return the child builder type so child methods can be chained next. In that case, you must weigh cast risks, subclass constraints, and constructor/protected-method design. Many APIs can avoid that complexity through composition or independent builders.

## 10. Handling Wildcards/Capture and Type Inference Errors

Several compiler errors frequently encountered with recursive bounds:

| Symptom | Cause | How to resolve |
| --- | --- | --- |
| `inference variable ... has incompatible bounds` | The compiler cannot find a single T satisfying all type constraints simultaneously. | Check whether T really needs to appear in every parameter; extract read tasks into a small interface. |
| `capture of ?` or `CAP#1` | A wildcard holds an unknown type; the compiler cannot assume two wildcards represent the same type. | Keep a named T across the same generic method if a relationship is truly needed; or use only subtype-independent operations. |
| `List<Child>` does not match `List<Parent>` | Java generic collections are **invariant**, even when `Child extends Parent`. | Read-only: `List<? extends Parent>`; if adding Parent is needed, reconsider an API taking `List<? super Parent>` and how elements are consumed. |
| `Comparable<Child>` does not match inherited `Comparable<Parent>` | Bound is too tight while the comparison takes a matching supertype. | Use `Comparable<? super Child>` or a `Comparator`. |
| `rawtypes`/`unchecked` warnings | Dropping generic arguments or casting to get past inference errors. | Redesign bounds, overloads, or callbacks; avoid silencing warnings just to "make it run". |

A useful habit: **start from the operation actually needed**, not from the most general bound. If a method only needs `label()`, use `Labelled`. If it only compares, take a comparator. If it must call `S rename(...)` and preserve returning `S`, an F-bound may be the right choice.

When processing a list of multiple subtypes where each element has its own transformation, do not force everything into one type parameter S and cast each element. Instead, let each component create/update objects where the concrete type is still known, then pass results to the presentation layer via a shared interface. This separation of responsibilities makes the API easier to test and avoids tricking the compiler.

## 11. How to Refactor a Complex API

Suppose an interface is used across many modules:

```java
interface Entity<E extends Entity<E>> {
    String id();
    E refresh();
}
```

If most callers only need `id()`, you can refine it in steps:

1. **Inventory caller needs:** which callers only read `id()`, which need `refresh()` and the exact E back, and which merely pass objects across layers.
2. **Extract a small contract:** add `Identified { String id(); }` and have `Entity<E> extends Identified`. Read-only APIs switch to accepting `Identified` or `List<? extends Identified>`.
3. **Keep the self-typed bound where necessary:** a `refresh` feature can still use `<E extends Entity<E>> E reload(E value)`. For service-driven refresh flows, consider `<T> T refresh(T value, UnaryOperator<T> strategy)`.
4. **Adjust comparisons separately:** if an API picks the "best" entity, use `Comparator<? super T>` instead of forcing every entity to have `Comparable<Entity<?>>` or a recursive bound.
5. **Evaluate compatibility:** overloads taking a wider interface are often convenient, yet Java has type erasure; two overloads differing only between `List<Entity<?>>` and `List<Identified>` can collide in signature after erasure. In that case, rename the method or use genuinely distinct signatures. Re-test existing call sites before releasing the library.

The declarations/methods in this section are **illustrative design patterns**, not meant to be pasted verbatim into `SimplerBoundsDemo` to run. The core idea: keep complex bounds only at points where they protect meaningful behavior or type relationships.

## 12. When Should You Keep an F-Bound?

**Keep it** when an API needs one of the following:

- Interaction between two values of **the exact same concrete type**, such as `Comparable<T>`.
- Methods on the model itself that produce/return the subtype declared via parameter S; results must retain that type across generic classes.
- Contracts tied to concrete enums: `<E extends Enum<E>>` working with `EnumSet<E>`, `EnumMap<E, V>`, or `Enum.valueOf(Class<E>, ...)`.
- A library with a controlled type hierarchy that accepts the implementation cost and verifies self-type validity.

**Simplify it** when the operation only needs to read shared data, apply custom transformations, compare by external criteria, provide a standalone builder, or pass an object of type T through a service without using F-bound behavior.

Do not use signature length as the sole criterion: a longer bound that proves an important invariant is still better than a short API forced into unsafe casts. Conversely, a bound that contributes no guarantee should be removed from the public surface.

## 13. Exercises and Answers

**Exercise 1.** A UI table only needs to display `id()` of `List<Order>` and `List<Customer>`. Should both be required to implement `Entity<E extends Entity<E>>`?

**Answer:** Not necessary if both only share `id()`. Extract `Identified` and accept `List<? extends Identified>` in the display layer.

**Exercise 2.** Why can `<T extends Comparable<T>>` be too strict when a subtype inherits `Comparable<Parent>`?

**Answer:** The subtype does not necessarily implement `Comparable<Subtype>`. `Comparable<? super T>` accurately expresses the need: the comparison can accept a parent type of T.

**Exercise 3.** Need a function returning exact T after the caller decides how to modify it. Is `T extends Self<T>` mandatory?

**Answer:** No. `<T> T transform(T value, UnaryOperator<T> op)` preserves T and lets the caller supply the behavior.

**Exercise 4.** Does `interface Self<T extends Self<T>>` guarantee `class A implements Self<A>` and prevent all other variants?

**Answer:** No. A class can choose another T as long as T satisfies the bound; a stronger self-type design requires controlling implementations, class structure, and related logic.

**Exercise 5.** A single final builder has a `name(...)` method returning the builder itself. Is `Builder<B extends Builder<B>>` needed?

**Answer:** Usually no. Directly returning the concrete builder type is sufficient and makes the API easier to read.

---

**Conclusion:** F-bounds are useful when the dependency between the current type and parameter/return types is an essential part of the contract. To keep Java APIs easy to use, keep that constraint where preserving the same type is necessary; for reading, comparing, transforming, and simple object construction, prefer small interfaces, appropriate wildcards, and strongly typed callbacks.
